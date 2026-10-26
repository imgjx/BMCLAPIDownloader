"""自动识别本机的 Minecraft 游戏目录（.minecraft）。

支持的识别来源：
1. 官方启动器：%APPDATA%\\.minecraft
2. PCL2：启动器所在目录下的 .minecraft（PCL 为绿色版，目录跟着 exe 走）
3. HMCL：启动器所在目录下的 .minecraft
4. 由 launcher_profiles.json 里记录的 gameDir 反查
5. 全盘浅层扫描（深度有限，自动跳过系统目录，避免卡死）

判定依据不只靠文件夹名字，还看内部特征（versions / assets / launcher_profiles.json），
这样即使用户把目录改名成 "MC" 也能认出来。
"""

from __future__ import annotations

import json
import os
import string
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

# 扫描时直接跳过的目录名（小写比较），避免拖慢速度或触发权限错误
SKIP_DIRS = {
    "windows", "program files", "program files (x86)", "programdata",
    "$recycle.bin", "system volume information", "recovery", "perflogs",
    "appdata", "node_modules", ".git", ".svn", "__pycache__", "windows.old",
    "documents and settings", "intel", "nvidia", "amd", "drivers",
    "python311", "python312", "python313", "site-packages", ".cache",
    "temp", "tmp", "cache", "venv", ".venv", "anaconda3", "miniconda3",
}

# 已知启动器可执行文件名（小写），用于给目录打标签
PCL_MARKS = {"pcl.exe", "pcl2.exe", "plain craft launcher 2.exe"}
HMCL_MARKS = {"hmcl.exe"}


@dataclass
class GameDir:
    """一个被识别出来的游戏目录。"""

    path: Path
    source: str = "未知"           # 官方启动器 / PCL2 / HMCL / 手动添加
    versions: int = 0              # 已安装版本数量
    mods: int = 0
    has_json: bool = False
    score: int = 0                 # 排序权重

    def __post_init__(self) -> None:
        self.versions_dir = self.path / "versions"
        self.mods_dir = self.path / "mods"

    # ---- 展示用 ----
    @property
    def title(self) -> str:
        return f"{self.path}"

    @property
    def subtitle(self) -> str:
        bits = [self.source]
        if self.versions:
            bits.append(f"{self.versions} 个版本")
        if self.mods:
            bits.append(f"{self.mods} 个模组")
        if not self.path.exists():
            bits.append("目录不存在")
        return " · ".join(bits)

    def exists(self) -> bool:
        try:
            return self.path.is_dir()
        except OSError:
            return False


def is_mc_dir(path: Path) -> bool:
    """判断一个目录是否是 .minecraft 数据目录（看内部特征，不只看名字）。"""
    if not path.is_dir():
        return False
    markers = ("versions", "assets", "launcher_profiles.json",
               "libraries", "mods", "saves", "options.txt")
    hits = 0
    for m in markers:
        try:
            if (path / m).exists():
                hits += 1
        except OSError:
            continue
    # 至少要命中 2 个特征，或者标准的 versions 目录存在
    return hits >= 2 or (path / "versions").is_dir()


def _count_dirs(p: Path) -> int:
    try:
        return sum(1 for x in p.iterdir() if x.is_dir())
    except (OSError, PermissionError):
        return 0


def _launcher_kind(mc_dir: Path) -> str:
    """根据 .minecraft 内部的启动器痕迹判断归属。"""
    try:
        if (mc_dir / "PCL").is_dir():
            return "PCL2"
        if (mc_dir / "HMCL").is_dir():
            return "HMCL"
        # PCL 会在 .minecraft 下写 PCL 相关配置
        for name in ("PCL.ini", "pcl.ini"):
            if (mc_dir / name).exists():
                return "PCL2"
    except OSError:
        pass
    return "未知"


def make_gamedir(path: Path, source: str | None = None) -> GameDir:
    path = Path(path)
    src = source or _launcher_kind(path)
    if src == "未知":
        # 官方启动器默认位置
        appdata = os.environ.get("APPDATA")
        if appdata and path.resolve() == (Path(appdata) / ".minecraft").resolve():
            src = "官方启动器"
        else:
            src = "其他启动器"
    g = GameDir(path=path, source=src)
    g.versions = _count_dirs(path / "versions")
    g.mods = len(list((path / "mods").glob("*.jar"))) if (path / "mods").is_dir() else 0
    g.has_json = (path / "launcher_profiles.json").exists()
    g.score = g.versions * 10 + (5 if g.has_json else 0) + (3 if g.mods else 0)
    return g


def _profiles_game_dirs() -> list[Path]:
    """从官方启动器 / 部分第三方启动器的 launcher_profiles.json 里挖 gameDir。"""
    out: list[Path] = []
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return out
    for rel in (".minecraft/launcher_profiles.json",
                ".minecraft/launcher_profiles_microsoft_store.json"):
        f = Path(appdata) / rel
        if not f.is_file():
            continue
        try:
            data = json.loads(f.read_text("utf-8", errors="ignore"))
        except Exception:
            continue
        for prof in (data.get("profiles") or {}).values():
            gd = prof.get("gameDir")
            if gd:
                out.append(Path(gd))
    return out


def quick_candidates() -> list[Path]:
    """不需要扫描就能拿到的候选路径。"""
    cands: list[Path] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        cands.append(Path(appdata) / ".minecraft")
    home = Path.home()
    cands += [
        home / ".minecraft",
        home / "Desktop" / ".minecraft",
        home / "Documents" / ".minecraft",
        home / "Minecraft",
        home / "Downloads" / ".minecraft",
    ]
    # 各盘根目录
    for letter in string.ascii_uppercase:
        root = Path(f"{letter}:/")
        try:
            if not root.exists():
                continue
        except OSError:
            continue
        cands += [root / ".minecraft", root / "Minecraft" / ".minecraft",
                  root / "Games" / ".minecraft", root / "游戏" / ".minecraft"]
    cands += _profiles_game_dirs()
    return cands


def _fixed_drives() -> list[Path]:
    drives: list[Path] = []
    if os.name != "nt":
        return [Path.home()]
    for letter in string.ascii_uppercase:
        root = Path(f"{letter}:/")
        try:
            if root.exists() and os.access(root, os.R_OK):
                drives.append(root)
        except OSError:
            continue
    return drives


def scan(depth: int = 3,
         report: Callable[[str], None] | None = None,
         stop: threading.Event | None = None) -> list[GameDir]:
    """浅层扫描全盘，找 .minecraft 目录与 PCL/HMCL 启动器目录。

    depth 表示从盘符往下的最大层级，3 层足以覆盖绝大多数人的目录结构，
    同时能在普通机械盘上把耗时控制在几秒内。
    """
    found: dict[str, GameDir] = {}

    def add(p: Path, source: str | None = None) -> None:
        key = str(p.resolve()).lower()
        if key in found:
            return
        g = make_gamedir(p, source)
        found[key] = g
        if report:
            report(f"发现 {g.source}：{p}")

    # 第一轮：已知位置
    for c in quick_candidates():
        try:
            if c.is_dir() and is_mc_dir(c):
                add(c)
        except OSError:
            continue

    if report:
        report("正在扫描磁盘上的 PCL / HMCL 启动器目录…")

    # 第二轮：从盘符开始广度受限地走
    for drive in _fixed_drives():
        if stop and stop.is_set():
            break
        base_depth = len(drive.parts)
        for cur, dirnames, filenames in os.walk(drive, topdown=True):
            if stop and stop.is_set():
                break
            cur_path = Path(cur)
            try:
                rel_depth = len(cur_path.parts) - base_depth
            except Exception:
                rel_depth = 0
            if rel_depth >= depth:
                dirnames[:] = []

            lower_names = {d.lower() for d in dirnames}
            file_lower = {f.lower() for f in filenames}

            # 命中 .minecraft 目录
            if ".minecraft" in lower_names:
                add(cur_path / ".minecraft")

            # 命中 PCL / HMCL 启动器本体 → 同目录（或其下）的 .minecraft
            is_pcl = bool(PCL_MARKS & file_lower) or "pcl" in lower_names
            is_hmcl = bool(HMCL_MARKS & file_lower) or any(
                n.startswith("hmcl") and n.endswith(".jar") for n in file_lower
            )
            if is_pcl or is_hmcl:
                kind = "PCL2" if is_pcl else "HMCL"
                for sub in (".minecraft",):
                    p = cur_path / sub
                    if p.is_dir():
                        add(p, kind)

            # 剪枝
            dirnames[:] = [
                d for d in dirnames
                if d.lower() not in SKIP_DIRS and not d.startswith("$")
            ]

    result = sorted(found.values(), key=lambda g: (-g.score, str(g.path)))
    if report:
        report(f"扫描完成，共找到 {len(result)} 个候选目录")
    return result


def detect_best() -> GameDir | None:
    """快速给出一个最可能的目标目录（用于启动时预填）。"""
    quick: list[GameDir] = []
    for c in quick_candidates():
        try:
            if c.is_dir() and is_mc_dir(c):
                quick.append(make_gamedir(c))
        except OSError:
            continue
    if not quick:
        return None
    return max(quick, key=lambda g: g.score)


def ensure_mc_dir(path: Path) -> Path:
    """确保目录是一个可用的 .minecraft 结构。"""
    path = Path(path)
    for sub in ("versions", "libraries", "assets"):
        (path / sub).mkdir(parents=True, exist_ok=True)
    return path


def installed_versions(game_dir: Path) -> list[str]:
    """列出已安装的版本 id（有 json 才算）。"""
    vdir = Path(game_dir) / "versions"
    if not vdir.is_dir():
        return []
    out: list[str] = []
    try:
        for sub in vdir.iterdir():
            if sub.is_dir() and (sub / f"{sub.name}.json").is_file():
                out.append(sub.name)
    except OSError:
        pass
    return sorted(out, reverse=True)
