"""安装流程编排：原版 / Fabric / Forge / NeoForge / OptiFine。

职责边界：把 api 层的 Plan 变成磁盘上的游戏，不碰界面。
所有过程通过回调上报给 UI，方便做进度条与日志。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import api, net
from .net import Client, Downloader, ProgressSnapshot, Source, Task

LOADERS = ["vanilla", "fabric", "forge", "neoforge", "optifine"]
LOADER_LABELS = {
    "vanilla": "原版",
    "fabric": "Fabric",
    "forge": "Forge",
    "neoforge": "NeoForge",
    "optifine": "OptiFine",
}


@dataclass
class InstallRequest:
    game_dir: Path
    mc_version: str
    loader: str = "vanilla"
    loader_version: str = ""          # fabric loader / forge build / optifine patch
    with_assets: bool = True
    workers: int = 16
    mode: str = Source.AUTO
    verify: bool = True
    java_path: str = ""
    version_name: str = ""             # versions 下的目录名，空=自动


class Cancelled(Exception):
    pass


_BAD_CHARS = set('\\/:*?"<>|')
_RESERVED = {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} \
    | {f"lpt{i}" for i in range(1, 10)}


def check_version_name(name: str) -> str | None:
    """校验 versions 下的目录名，返回错误提示；None 表示合法。"""
    if not name:
        return None
    if name in (".", ".."):
        return "名字不能是 . 或 .."
    if len(name) > 64:
        return "名字太长（最多 64 个字符）"
    bad = sorted({c for c in name if c in _BAD_CHARS} |
                 {c for c in name if ord(c) < 32})
    if bad:
        return "不能包含这些字符：" + " ".join(bad)
    if name != name.strip() or name.endswith("."):
        return "首尾不能有空格，也不能以点结尾"
    if name.split(".")[0].lower() in _RESERVED:
        return "这个名字被 Windows 保留，请换一个"
    return None


class Installer:
    def __init__(self,
                 on_stage: Callable[[str], None] | None = None,
                 on_progress: Callable[[ProgressSnapshot], None] | None = None,
                 on_log: Callable[[str], None] | None = None):
        self.on_stage = on_stage or (lambda s: None)
        self.on_progress = on_progress or (lambda p: None)
        self.on_log = on_log or (lambda s: None)
        self._downloader: Downloader | None = None
        self.cancelled = False

    # ------------------------------------------------------------------ #
    def cancel(self) -> None:
        self.cancelled = True
        if self._downloader:
            self._downloader.cancel()

    def _check(self) -> None:
        if self.cancelled:
            raise Cancelled()

    # ------------------------------------------------------------------ #
    def install(self, req: InstallRequest) -> str:
        gd = Path(req.game_dir)
        gd.mkdir(parents=True, exist_ok=True)
        for sub in ("versions", "libraries", "assets"):
            (gd / sub).mkdir(parents=True, exist_ok=True)

        self._downloader = Downloader(workers=req.workers, mode=req.mode,
                                      verify=req.verify)
        client = Client(mode=req.mode)

        # 1. 拉清单定位版本
        self.on_stage("获取版本清单")
        manifest = api.Manifest(client)
        versions = manifest.load()
        target = next((v for v in versions if v.id == req.mc_version), None)
        if target is None:
            target = api.VersionInfo(id=req.mc_version, type="release", url="",
                                     time="", release_time="")

        # 2. 原版底座（只有原版安装才允许改目录名，装载器必须沿用官方 id 以便继承）
        self.on_stage(f"解析 {req.mc_version} 版本信息")
        base_name = req.version_name if req.loader == "vanilla" else ""
        plan = api.build_vanilla_plan(gd, target, client,
                                      with_assets=req.with_assets,
                                      version_name=base_name)
        self.on_log(f"版本 {req.mc_version} 共 {plan.file_count} 个文件，"
                    f"约 {plan.total_bytes / 1048576:.1f} MB")
        for w in plan.warnings:
            self.on_log(f"提示：{w}")

        self._run_tasks(plan.tasks, "下载游戏文件")

        # 3. 资源对象（依赖索引文件，索引在第 2 步已下好）
        idx_id = plan.extra.get("asset_index_id")
        if req.with_assets and idx_id:
            idx_path = gd / "assets" / "indexes" / f"{idx_id}.json"
            asset_tasks = api.assets_tasks_from_index(gd, idx_path)
            if asset_tasks:
                self.on_log(f"资源索引 {idx_id} 含 {len(asset_tasks)} 个对象")
                self._run_tasks(asset_tasks, "下载资源文件")
            self._virtualize_assets(gd, idx_path)

        # 4. 解压 natives
        self._extract_natives(plan)

        # 5. 模组加载器
        version_id = plan.version_id
        if req.loader == "fabric":
            version_id = self._install_fabric(gd, req, client)
        elif req.loader in ("forge", "neoforge"):
            version_id = self._install_forge_like(gd, req, client)
            # 安装器自己决定目录名，用户改过名的话装完再改
            want = req.version_name.strip()
            if want and want != version_id:
                version_id = self._rename_version(gd, version_id, want)
        elif req.loader == "optifine":
            self._install_optifine(gd, req, client)
            version_id = req.mc_version

        # 6. 写启动器配置
        self._register_profile(gd, version_id, req)
        self.on_stage("安装完成")
        return version_id

    # ------------------------------------------------------------------ #
    def _run_tasks(self, tasks: list[Task], stage: str) -> None:
        if not tasks:
            return
        self.on_stage(stage)
        self.on_log(f"{stage}：{len(tasks)} 个文件")
        snap = self._downloader.run(tasks, on_progress=self.on_progress,
                                    on_log=self.on_log)
        if self.cancelled:
            raise Cancelled()
        if snap.failed:
            self.on_log(f"有 {len(snap.failed)} 个文件失败，其余已完成")

    # ------------------------------------------------------------------ #
    def _virtualize_assets(self, gd: Path, index_path: Path) -> None:
        """1.6 及更早版本的资源索引带 virtual:true，需要按原始路径铺一份。"""
        try:
            data = json.loads(Path(index_path).read_text("utf-8"))
        except Exception:
            return
        if not data.get("virtual"):
            return
        target = gd / "assets" / "virtual" / (data.get("id") or "legacy")
        objects = data.get("objects") or {}
        self.on_stage("展开虚拟资源目录")
        made = 0
        for name, obj in objects.items():
            h = obj.get("hash", "")
            if len(h) < 4:
                continue
            src = gd / "assets" / "objects" / h[:2] / h
            if not src.is_file():
                continue
            dst = target / name
            if dst.is_file():
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(src, dst)          # 硬链接，省空间
            except OSError:
                try:
                    shutil.copy2(src, dst)
                except OSError:
                    continue
            made += 1
        self.on_log(f"虚拟资源目录已展开 {made} 个文件 → {target}")

    # ------------------------------------------------------------------ #
    def _extract_natives(self, plan: api.Plan) -> None:
        if not plan.natives:
            return
        self.on_stage("解压原生库")
        for jar, dest_dir, extract in plan.natives:
            if not Path(jar).is_file() or dest_dir is None:
                continue
            Path(dest_dir).mkdir(parents=True, exist_ok=True)
            exclude = "|".join(extract.get("exclude") or []) or None
            try:
                with zipfile.ZipFile(jar) as zf:
                    for name in zf.namelist():
                        if name.endswith("/"):
                            continue
                        if exclude and re.search(exclude, name):
                            continue
                        out = Path(dest_dir) / Path(name).name
                        with zf.open(name) as src, open(out, "wb") as dst:
                            shutil.copyfileobj(src, dst)
            except Exception as exc:  # noqa: BLE001
                self.on_log(f"解压 {Path(jar).name} 失败：{exc}")
        self.on_log("原生库解压完成")

    # ------------------------------------------------------------------ #
    def _install_fabric(self, gd: Path, req: InstallRequest,
                        client: Client) -> str:
        loader = req.loader_version
        if not loader:
            items = api.fabric_loaders(client, req.mc_version)
            if not items:
                raise RuntimeError("该版本没有可用的 Fabric Loader")
            loader = items[0].value

        self.on_stage(f"安装 Fabric {loader}")
        self.on_log(f"Fabric Loader {loader} 用于 {req.mc_version}")
        profile = api.fabric_profile(client, req.mc_version, loader)

        vid = req.version_name.strip() or f"fabric-loader-{loader}-{req.mc_version}"
        vdir = gd / "versions" / vid
        vdir.mkdir(parents=True, exist_ok=True)
        profile["id"] = vid
        profile.setdefault("inheritsFrom", req.mc_version)
        profile["type"] = "release"
        (vdir / f"{vid}.json").write_text(
            json.dumps(profile, ensure_ascii=False, indent=2), "utf-8")

        tasks: list[Task] = []
        for lib in profile.get("libraries", []):
            name = lib.get("name", "")
            if ":" not in name:
                continue
            path = api.maven_path(name)
            base = lib.get("url") or "https://maven.fabricmc.net/"
            tasks.append(Task(url=base.rstrip("/") + "/" + path,
                              dest=gd / "libraries" / path,
                              label=path.split("/")[-1]))
        self._run_tasks(tasks, "下载 Fabric 依赖")
        return vid

    # ------------------------------------------------------------------ #
    def _install_forge_like(self, gd: Path, req: InstallRequest,
                            client: Client) -> str:
        java = req.java_path or find_java(gd)
        if not java:
            raise RuntimeError(
                "没找到可用的 Java，无法运行 Forge/NeoForge 安装器。\n"
                "请先安装 JDK 17+（例如 Adoptium Temurin），或在设置里手动指定 java.exe")

        tmp = Path(tempfile.mkdtemp(prefix="mcdl-"))
        try:
            if req.loader == "neoforge":
                ver = req.loader_version
                if not ver:
                    items = api.neoforge_versions(client, req.mc_version)
                    if not items:
                        raise RuntimeError("该版本没有可用的 NeoForge")
                    ver = items[0].value
                url = api.neoforge_installer_url(ver)
            else:
                ver = req.loader_version
                if not ver:
                    items = api.forge_builds(client, req.mc_version)
                    if not items:
                        raise RuntimeError("该版本没有可用的 Forge")
                    ver = items[0].value
                # BMCLAPI 有时直接返回 "1.20.1-47.2.0" 这种带 MC 前缀的写法
                if ver.startswith(req.mc_version + "-"):
                    ver = ver[len(req.mc_version) + 1:]
                url = api.forge_installer_url(req.mc_version, ver)

            installer = tmp / f"{req.loader}-{ver}-installer.jar"
            self.on_stage(f"下载 {LOADER_LABELS[req.loader]} {ver} 安装器")
            self.on_log(f"安装器来源：{url}")
            dl = Downloader(workers=4, mode=req.mode)
            dl.run([Task(url=url, dest=installer, label=installer.name)],
                   on_progress=self.on_progress, on_log=self.on_log)
            if not installer.is_file() or installer.stat().st_size < 1024:
                raise RuntimeError("安装器下载失败，请稍后重试")

            self.on_stage("运行安装器（需要一点时间）")
            self._run_java_installer(java, installer, gd)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        # 安装器会自己写 versions 目录，找出新增的那个
        return self._guess_loader_version_id(gd, req)

    def _run_java_installer(self, java: str, installer: Path, gd: Path) -> None:
        cmd = [java, "-jar", str(installer), "--installClient", str(gd)]
        self.on_log("执行：" + " ".join(cmd))
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            cwd=str(installer.parent), creationflags=flags, text=True,
            encoding="utf-8", errors="replace", bufsize=1,
            env={**os.environ, "JAVA_TOOL_OPTIONS": ""},
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                self.on_log(line)
            if self.cancelled:
                proc.kill()
                raise Cancelled()
        code = proc.wait()
        if code != 0:
            raise RuntimeError(f"安装器退出码 {code}，请查看上方日志")

    def _guess_loader_version_id(self, gd: Path, req: InstallRequest) -> str:
        vdir = gd / "versions"
        best, best_t = req.mc_version, 0.0
        try:
            for sub in vdir.iterdir():
                if not sub.is_dir():
                    continue
                if req.mc_version not in sub.name:
                    continue
                j = sub / f"{sub.name}.json"
                if not j.is_file():
                    continue
                m = j.stat().st_mtime
                if m > best_t:
                    best, best_t = sub.name, m
        except OSError:
            pass
        return best

    # ------------------------------------------------------------------ #
    def _install_optifine(self, gd: Path, req: InstallRequest,
                          client: Client) -> None:
        items = api.optifine_builds(client, req.mc_version)
        if not items:
            raise RuntimeError("该版本没有可用的 OptiFine")
        chosen = None
        if req.loader_version:
            chosen = next((i for i in items if i.value == req.loader_version), None)
        chosen = chosen or items[0]
        typ, patch = chosen.value.split("/", 1)
        url = api.optifine_download_url(req.mc_version, typ, patch)
        dest = gd / "optifine" / chosen.extra.get("filename", "OptiFine.jar")
        self.on_stage(f"下载 OptiFine {chosen.label}")
        dl = Downloader(workers=4, mode=req.mode)
        dl.run([Task(url=url, dest=dest, label=dest.name)],
               on_progress=self.on_progress, on_log=self.on_log)
        self.on_log(f"OptiFine 已下载到 {dest}")
        self.on_log("OptiFine 安装器需要图形界面，请双击运行它完成安装"
                    "（或直接把它放进 mods 文件夹配合 Forge 使用）")

    # ------------------------------------------------------------------ #
    def _rename_version(self, gd: Path, old: str, new: str) -> str:
        """把 versions/<old> 改成 versions/<new>，同时修正 json 内部的 id。

        Forge / NeoForge 的安装器自己决定版本 id，用户指定了别的名字时
        只能在装完之后整体改名。
        """
        src = gd / "versions" / old
        dst = gd / "versions" / new
        if not src.is_dir() or old == new:
            return old
        if dst.exists():
            raise RuntimeError(f"版本目录 {new} 已存在，请换一个名字")

        self.on_stage(f"重命名版本目录 {old} → {new}")
        tmp = gd / "versions" / f".{new}.tmp"
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
        src.rename(tmp)

        # 版本 json：改文件名与 id 字段
        old_json = tmp / f"{old}.json"
        if not old_json.is_file():
            cands = list(tmp.glob("*.json"))
            if cands:
                old_json = cands[0]
        if old_json.is_file():
            try:
                data = json.loads(old_json.read_text("utf-8"))
                data["id"] = new
                (tmp / f"{new}.json").write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
                if old_json.name != f"{new}.json":
                    old_json.unlink(missing_ok=True)
            except Exception as exc:  # noqa: BLE001
                self.on_log(f"改写版本 json 失败：{exc}")

        # 老版本 natives 目录也跟着改名
        for sub in tmp.iterdir():
            if sub.is_dir() and sub.name == f"{old}-natives":
                sub.rename(tmp / f"{new}-natives")

        tmp.rename(dst)
        self.on_log(f"版本目录已改名：{old} → {new}")
        return new

    # ------------------------------------------------------------------ #
    def _register_profile(self, gd: Path, version_id: str,
                          req: InstallRequest) -> None:
        """往 launcher_profiles.json 里登记一个 profile，让官方启动器也能看到。"""
        f = gd / "launcher_profiles.json"
        try:
            data = json.loads(f.read_text("utf-8")) if f.is_file() else {}
        except Exception:
            data = {}
        data.setdefault("profiles", {})
        key = f"bmclapi-{version_id}"
        label = req.mc_version
        if req.loader != "vanilla":
            label = f"{req.mc_version} - {LOADER_LABELS.get(req.loader, req.loader)}"
        data["profiles"][key] = {
            "name": label,
            "type": "custom",
            "created": data.get("profiles", {}).get(key, {}).get("created",
                                                                 "1970-01-01T00:00:00.000Z"),
            "lastUsed": "1970-01-01T00:00:00.000Z",
            "icon": "Grass",
            "lastVersionId": version_id,
            "gameDir": str(gd),
        }
        if not data.get("selectedProfile"):
            data["selectedProfile"] = key
        try:
            f.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
        except OSError as exc:
            self.on_log(f"写入启动器配置失败：{exc}")


# --------------------------------------------------------------------------- #
# Java 探测
# --------------------------------------------------------------------------- #

_JAVA_HINTS = [
    r"C:\Program Files\Java\*\bin\java.exe",
    r"C:\Program Files\Eclipse Adoptium\*\bin\java.exe",
    r"C:\Program Files\Microsoft\jdk*\bin\java.exe",
    r"C:\Program Files\Zulu\*\bin\java.exe",
    r"C:\Program Files\BellSoft\*\bin\java.exe",
    r"C:\Program Files\Amazon Corretto\*\bin\java.exe",
]


def find_java(game_dir: Path | None = None) -> str | None:
    """按优先级找一个可用的 java.exe。"""
    # 1) 环境变量 JAVA_HOME
    jh = os.environ.get("JAVA_HOME")
    if jh:
        p = Path(jh) / "bin" / "java.exe"
        if p.is_file():
            return str(p)
    # 2) PATH
    exe = shutil.which("java")
    if exe:
        return exe
    # 3) 官方启动器自带的运行时
    if game_dir:
        rt = Path(game_dir) / "runtime"
        if rt.is_dir():
            for p in rt.rglob("java.exe"):
                if "bin" in p.parts:
                    return str(p)
    # 4) 常见安装位置
    import glob
    for pat in _JAVA_HINTS:
        for hit in sorted(glob.glob(pat), reverse=True):
            if Path(hit).is_file():
                return hit
    return None


def java_version(java: str) -> str:
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        out = subprocess.run([java, "-version"], capture_output=True,
                             text=True, timeout=10, creationflags=flags)
        txt = (out.stderr or "") + (out.stdout or "")
        m = re.search(r'version "([^"]+)"', txt)
        return m.group(1) if m else txt.splitlines()[0] if txt else "未知"
    except Exception:  # noqa: BLE001
        return "未知"
