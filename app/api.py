"""BMCLAPI 接口封装（文档：https://bmclapidoc.bangbang93.com/）。

只做三件事：拉元数据、判断平台规则、把元数据翻译成下载任务列表。
真正的下载交给 net.Downloader。
"""

from __future__ import annotations

import json
import platform
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import net
from .net import BMCLAPI, Client, Task, to_mirror

MANIFEST_OFFICIAL = "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json"
MANIFEST_V1 = "https://launchermeta.mojang.com/mc/game/version_manifest.json"

OS_NAME = "windows" if platform.system() == "Windows" else (
    "osx" if platform.system() == "Darwin" else "linux")
OS_ARCH = "x86" if platform.machine().endswith("86") else "x64"
OS_VERSION = platform.version()


# --------------------------------------------------------------------------- #
# 规则判断
# --------------------------------------------------------------------------- #

def _rule_matches(rule: dict, os_name: str, arch: str, os_version: str) -> bool:
    cond = rule.get("os")
    if not cond:
        return True
    if cond.get("name") and cond["name"] != os_name:
        return False
    if cond.get("arch") and cond["arch"] != arch:
        return False
    if cond.get("version"):
        try:
            if not re.search(cond["version"], os_version or ""):
                return False
        except re.error:
            pass
    return True


def rules_allow(rules: list[dict] | None,
                os_name: str = OS_NAME) -> bool:
    """Minecraft 的 rules 语义：先默认不允许，按顺序匹配覆盖。"""
    if not rules:
        return True
    allowed = False
    for rule in rules:
        if _rule_matches(rule, os_name, OS_ARCH, OS_VERSION):
            allowed = rule.get("action") == "allow"
    return allowed


def library_allowed(lib: dict) -> bool:
    return rules_allow(lib.get("rules"))


def maven_path(name: str) -> str:
    """group:artifact:version[:classifier] → maven 相对路径。"""
    parts = name.split(":")
    group, artifact, version = parts[0], parts[1], parts[2]
    classifier = parts[3] if len(parts) > 3 else ""
    filename = f"{artifact}-{version}" + (f"-{classifier}" if classifier else "") + ".jar"
    return "/".join(group.split(".") + [artifact, version, filename])


# --------------------------------------------------------------------------- #
# 版本清单
# --------------------------------------------------------------------------- #

@dataclass
class VersionInfo:
    id: str
    type: str            # release / snapshot / old_beta / old_alpha
    url: str
    time: str
    release_time: str
    sha1: str = ""

    @property
    def type_label(self) -> str:
        return {
            "release": "正式版",
            "snapshot": "快照",
            "old_beta": "远古 Beta",
            "old_alpha": "远古 Alpha",
        }.get(self.type, self.type)

    @property
    def date(self) -> str:
        return (self.release_time or self.time or "")[:10]


class Manifest:
    """版本清单缓存。"""

    def __init__(self, client: Client):
        self.client = client
        self.latest: dict[str, str] = {}
        self.versions: list[VersionInfo] = []
        self._loaded = False

    def load(self, force: bool = False) -> list[VersionInfo]:
        if self._loaded and not force:
            return self.versions
        data = self.client.get_json(MANIFEST_OFFICIAL)
        self.latest = data.get("latest", {})
        out: list[VersionInfo] = []
        for v in data.get("versions", []):
            out.append(VersionInfo(
                id=v.get("id", ""),
                type=v.get("type", ""),
                url=v.get("url", ""),
                time=v.get("time", ""),
                release_time=v.get("releaseTime", v.get("time", "")),
                sha1=v.get("sha1", ""),
            ))
        self.versions = out
        self._loaded = True
        return out


def version_json_url(version: VersionInfo | None, vid: str) -> str:
    if version is not None and version.url:
        return version.url
    return f"{BMCLAPI}/version/{vid}/json"


# --------------------------------------------------------------------------- #
# 安装任务计划
# --------------------------------------------------------------------------- #

@dataclass
class Plan:
    """一次安装要做的事情。"""

    version_id: str
    tasks: list[Task] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)
    natives: list[tuple[Path, Path | None, dict]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def total_bytes(self) -> int:
        return sum(t.size for t in self.tasks)

    @property
    def file_count(self) -> int:
        return len(self.tasks)


def _artifact_task(game_dir: Path, path: str, dl: dict,
                   label: str = "") -> Task | None:
    url = dl.get("url")
    if not url:
        return None
    return Task(
        url=url,
        dest=Path(game_dir) / path / dl.get("path", ""),
        size=int(dl.get("size") or 0),
        sha1=dl.get("sha1", ""),
        label=label or dl.get("path", "").split("/")[-1],
    )


def build_vanilla_plan(game_dir: Path, version: VersionInfo,
                       client: Client,
                       with_assets: bool = True,
                       version_name: str = "") -> Plan:
    """原版安装计划：版本 json + client jar + 依赖库 + 资源文件 + 日志配置。

    version_name 为空时用官方版本 id 作为 versions 下的目录名；
    指定时会把 json 里的 id 一并改成该名字，保证目录名与 id 一致。
    """
    gd = Path(game_dir)
    detail = client.get_json(version_json_url(version, version.id))
    vid = version_name.strip() or version.id
    detail["id"] = vid
    plan = Plan(version_id=vid, detail=detail)

    vdir = gd / "versions" / vid
    vdir.mkdir(parents=True, exist_ok=True)

    # 1) 版本 json
    raw = json.dumps(detail, ensure_ascii=False, indent=2).encode("utf-8")
    (vdir / f"{vid}.json").write_bytes(raw)

    # 2) client jar
    downloads = detail.get("downloads") or {}
    client_dl = downloads.get("client")
    if client_dl:
        plan.tasks.append(Task(
            url=client_dl["url"],
            dest=vdir / f"{vid}.jar",
            size=int(client_dl.get("size") or 0),
            sha1=client_dl.get("sha1", ""),
            label=f"客户端主文件 {vid}.jar",
        ))
    else:
        plan.warnings.append("该版本没有独立的 client 文件（可能是继承型版本）")

    # 3) 依赖库
    natives_dir = vdir / f"{vid}-natives"
    lib_root = gd / "libraries"
    for lib in detail.get("libraries", []):
        if not library_allowed(lib):
            continue

        dl = lib.get("downloads") or {}
        artifact = dl.get("artifact")
        if artifact:
            task = _artifact_task(gd, "libraries", artifact, lib.get("name", ""))
            if task:
                plan.tasks.append(task)
        elif ":" in lib.get("name", "") and not dl:
            # 没有 downloads 字段的库，按 maven 规则拼
            path = maven_path(lib["name"])
            plan.tasks.append(Task(
                url=f"https://libraries.minecraft.net/{path}",
                dest=lib_root / path,
                label=path.split("/")[-1],
            ))

        # 老版本 natives（需要解压到版本目录）
        natives = lib.get("natives") or {}
        if natives:
            key = natives.get(OS_NAME)
            if key:
                key = key.replace("${arch}", "64" if OS_ARCH == "x64" else "32")
                cls = (dl.get("classifiers") or {}).get(key)
                if cls:
                    task = _artifact_task(gd, "libraries", cls,
                                          f"原生库 {lib.get('name', '')}")
                    if task:
                        plan.tasks.append(task)
                        plan.natives.append((task.dest, natives_dir,
                                             lib.get("extract") or {}))

    # 4) 资源索引 + 资源对象
    if with_assets:
        asset_index = detail.get("assetIndex")
        if asset_index:
            idx_id = asset_index.get("id") or asset_index.get("assetIndex")
            plan.tasks.append(Task(
                url=asset_index["url"],
                dest=gd / "assets" / "indexes" / f"{idx_id}.json",
                size=int(asset_index.get("size") or 0),
                sha1=asset_index.get("sha1", ""),
                label=f"资源索引 {idx_id}.json",
            ))
            plan.extra["asset_index_id"] = idx_id

    # 5) 日志配置
    logging_cfg = ((detail.get("logging") or {}).get("client") or {}).get("file")
    if logging_cfg and logging_cfg.get("url"):
        name = logging_cfg.get("id") or "client.xml"
        plan.tasks.append(Task(
            url=logging_cfg["url"],
            dest=gd / "assets" / "log_configs" / name,
            size=int(logging_cfg.get("size") or 0),
            sha1=logging_cfg.get("sha1", ""),
            label=f"日志配置 {name}",
        ))
    return plan


def assets_tasks_from_index(game_dir: Path, index_path: Path) -> list[Task]:
    """读取资源索引，生成 objects 下载任务。"""
    gd = Path(game_dir)
    try:
        data = json.loads(Path(index_path).read_text("utf-8"))
    except Exception:
        return []
    tasks: list[Task] = []
    objects = data.get("objects") or {}
    for name, obj in objects.items():
        h = obj.get("hash", "")
        if len(h) < 4:
            continue
        sub = h[:2]
        tasks.append(Task(
            url=f"https://resources.download.minecraft.net/{sub}/{h}",
            dest=gd / "assets" / "objects" / sub / h,
            size=int(obj.get("size") or 0),
            sha1=h,
            label=f"资源 {name}",
        ))
    return tasks


# --------------------------------------------------------------------------- #
# 模组加载器
# --------------------------------------------------------------------------- #

@dataclass
class LoaderVersion:
    label: str
    value: str
    stable: bool = True
    extra: dict[str, Any] = field(default_factory=dict)


def fabric_loaders(client: Client, mc: str) -> list[LoaderVersion]:
    data = client.get_json(f"{BMCLAPI}/fabric-meta/v2/versions/loader/{mc}")
    out = []
    for item in data:
        loader = item.get("loader") or {}
        ver = loader.get("version")
        if ver:
            out.append(LoaderVersion(label=ver, value=ver,
                                     stable=bool(loader.get("stable"))))
    return out


def fabric_profile(client: Client, mc: str, loader: str) -> dict:
    return client.get_json(
        f"{BMCLAPI}/fabric-meta/v2/versions/loader/{mc}/{loader}/profile/json")


def forge_builds(client: Client, mc: str) -> list[LoaderVersion]:
    data = client.get_json(f"{BMCLAPI}/forge/minecraft/{mc}")
    out = []
    for item in data:
        ver = item.get("version")
        if not ver:
            continue
        build = item.get("build")
        branch = item.get("branch")
        unstable = bool(branch)
        out.append(LoaderVersion(
            label=f"{ver}" + (f" ({branch})" if branch else ""),
            value=ver,
            stable=not unstable,
            extra={"build": build, "branch": branch, "raw": item},
        ))
    # BMCLAPI 返回的通常是最新在前，保险起见按版本号倒序
    out.sort(key=lambda x: _verkey(x.value), reverse=True)
    return out[:80]


def _verkey(s: str) -> tuple:
    return tuple(int(p) if p.isdigit() else 0 for p in re.split(r"[.\-]", s))


def neoforge_versions(client: Client, mc: str) -> list[LoaderVersion]:
    data = client.get_json(f"{BMCLAPI}/neoforge/list/{mc}")
    out = []
    for item in data if isinstance(data, list) else [data]:
        ver = item if isinstance(item, str) else item.get("version")
        if ver:
            out.append(LoaderVersion(label=ver, value=ver,
                                     stable="beta" not in ver.lower()))
    out.sort(key=lambda x: _verkey(x.value), reverse=True)
    return out


def optifine_builds(client: Client, mc: str) -> list[LoaderVersion]:
    data = client.get_json(f"{BMCLAPI}/optifine/{mc}")
    out = []
    for item in data if isinstance(data, list) else []:
        typ = item.get("type") or "HD_U"
        patch = item.get("patch") or ""
        fname = item.get("filename") or f"OptiFine_{mc}_{typ}_{patch}.jar"
        out.append(LoaderVersion(
            label=f"{typ}_{patch}",
            value=f"{typ}/{patch}",
            stable=True,
            extra={"filename": fname, "raw": item},
        ))
    return out


def neoforge_installer_url(ver: str) -> str:
    return f"{BMCLAPI}/neoforge/version/{ver}/download/installer.jar"


def forge_installer_url(mc: str, ver: str, branch: str | None = None) -> str:
    suffix = f"-{branch}" if branch else ""
    full = f"{mc}-{ver}{suffix}"
    return f"https://maven.minecraftforge.net/net/minecraftforge/forge/{full}/forge-{full}-installer.jar"


def optifine_download_url(mc: str, typ: str, patch: str) -> str:
    return f"{BMCLAPI}/optifine/{mc}/{typ}/{patch}"
