"""网络层：镜像映射 + 多线程下载 + 断点续传 + 哈希校验。

BMCLAPI 的核心玩法是「路径前缀替换」，所以这里把官方 URL 统一映射到镜像，
下载器本身不关心资源来自哪个源。
"""

from __future__ import annotations

import hashlib
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BMCLAPI = "https://bmclapi2.bangbang93.com"
BMCLAPI_ALT = "https://bmclapi.bangbang93.com"
ASSETS_OFFICIAL = "https://resources.download.minecraft.net"
MAVEN_OFFICIAL = "https://libraries.minecraft.net"
MOJANG_META = "https://launchermeta.mojang.com"

UA = "BMCLAPIDownloader/0.1.0 (BMCLAPI; +https://bmclapidoc.bangbang93.com)"

# 官方域名 → BMCLAPI 路径前缀映射（顺序敏感，长前缀优先）
_MIRROR_RULES: list[tuple[str, str]] = [
    ("https://launchermeta.mojang.com", BMCLAPI),
    ("http://launchermeta.mojang.com", BMCLAPI),
    ("https://launcher.mojang.com", BMCLAPI),
    ("http://launcher.mojang.com", BMCLAPI),
    ("https://piston-meta.mojang.com", BMCLAPI),
    ("https://piston-data.mojang.com", BMCLAPI),
    ("https://libraries.minecraft.net", f"{BMCLAPI}/maven"),
    ("http://libraries.minecraft.net", f"{BMCLAPI}/maven"),
    ("https://resources.download.minecraft.net", f"{BMCLAPI}/assets"),
    ("http://resources.download.minecraft.net", f"{BMCLAPI}/assets"),
    ("https://files.minecraftforge.net/maven", f"{BMCLAPI}/maven"),
    ("http://files.minecraftforge.net/maven", f"{BMCLAPI}/maven"),
    ("https://maven.minecraftforge.net", f"{BMCLAPI}/maven"),
    ("https://maven.neoforged.net/releases", f"{BMCLAPI}/maven"),
    ("https://maven.fabricmc.net", f"{BMCLAPI}/maven"),
    ("https://meta.fabricmc.net", f"{BMCLAPI}/fabric-meta"),
    ("https://meta.quiltmc.org", f"{BMCLAPI}/quilt-meta"),
    ("https://maven.quiltmc.org/repository/release", f"{BMCLAPI}/maven"),
    ("https://authlib-injector.yushi.moe", f"{BMCLAPI}/mirrors/authlib-injector"),
]


def to_mirror(url: str) -> str:
    """把官方 URL 改写成 BMCLAPI 镜像 URL。已经是镜像地址则原样返回。"""
    if not url:
        return url
    for official, mirrored in _MIRROR_RULES:
        if url.startswith(official):
            return mirrored + url[len(official):]
    return url


def to_official(url: str) -> str:
    """镜像 URL 反向还原为官方 URL（用于「官方源」模式）。"""
    for official, mirrored in _MIRROR_RULES:
        if url.startswith(mirrored):
            return official + url[len(mirrored):]
    return url


class Source:
    """下载源策略。"""

    AUTO = "auto"        # 镜像优先，失败自动回退官方
    MIRROR = "mirror"    # 只用 BMCLAPI
    OFFICIAL = "official"  # 只用官方源


def resolve(url: str, mode: str = Source.AUTO) -> tuple[str, str | None]:
    """返回 (首选URL, 回退URL)。"""
    mirrored = to_mirror(url)
    official = to_official(mirrored)
    if mode == Source.OFFICIAL:
        return official, None
    if mode == Source.MIRROR:
        return mirrored, None
    # auto：能镜像就镜像，镜像失败再回官方
    if mirrored != official:
        return mirrored, official
    return mirrored, None


# --------------------------------------------------------------------------- #
# HTTP 客户端
# --------------------------------------------------------------------------- #

def make_session(pool: int = 32) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Encoding": "gzip, deflate"})
    retry = Retry(total=3, backoff_factor=0.4,
                  status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=frozenset(["GET", "HEAD"]))
    adapter = HTTPAdapter(pool_connections=pool, pool_maxsize=pool,
                          max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


class Client:
    """同步 HTTP 客户端（JSON 接口用）。"""

    def __init__(self, mode: str = Source.AUTO, timeout: float = 20.0,
                 proxy: str | None = None):
        self.mode = mode
        self.timeout = timeout
        self.session = make_session(8)
        if proxy:
            self.session.proxies.update({"http": proxy, "https": proxy})

    def get_json(self, url: str, **kw):
        errors = []
        for candidate in [u for u in resolve(url, self.mode) if u]:
            try:
                r = self.session.get(candidate, timeout=self.timeout, **kw)
                r.raise_for_status()
                return r.json()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{candidate} → {exc}")
        raise RuntimeError("请求失败：" + " | ".join(errors))

    def get_text(self, url: str) -> str:
        errors = []
        for candidate in [u for u in resolve(url, self.mode) if u]:
            try:
                r = self.session.get(candidate, timeout=self.timeout)
                r.raise_for_status()
                return r.text
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{candidate} → {exc}")
        raise RuntimeError("请求失败：" + " | ".join(errors))

    def head_size(self, url: str) -> int:
        try:
            r = self.session.head(url, timeout=self.timeout, allow_redirects=True)
            return int(r.headers.get("Content-Length") or 0)
        except Exception:  # noqa: BLE001
            return 0


# --------------------------------------------------------------------------- #
# 下载任务
# --------------------------------------------------------------------------- #

@dataclass
class Task:
    url: str
    dest: Path
    size: int = 0
    sha1: str = ""
    label: str = ""

    def __post_init__(self) -> None:
        self.dest = Path(self.dest)
        if not self.label:
            self.label = self.dest.name


@dataclass
class ProgressSnapshot:
    total_bytes: int = 0
    done_bytes: int = 0
    total_files: int = 0
    done_files: int = 0
    speed: float = 0.0          # bytes/s
    current: str = ""
    failed: list[str] = field(default_factory=list)

    @property
    def ratio(self) -> float:
        if self.total_bytes > 0:
            return min(1.0, self.done_bytes / self.total_bytes)
        if self.total_files:
            return min(1.0, self.done_files / self.total_files)
        return 0.0


def sha1_of(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _file_ok(task: Task, verify: bool) -> bool:
    try:
        if not task.dest.is_file():
            return False
    except OSError:
        return False
    size = task.dest.stat().st_size
    if task.size and size != task.size:
        return False
    if verify and task.sha1:
        try:
            return sha1_of(task.dest) == task.sha1.lower()
        except OSError:
            return False
    return size > 0


class Downloader:
    """线程池下载器，支持断点续传、镜像回退、哈希校验。

    进度通过回调函数上报：on_progress(ProgressSnapshot)
    """

    def __init__(self, workers: int = 16, mode: str = Source.AUTO,
                 verify: bool = True, timeout: float = 30.0,
                 proxy: str | None = None):
        self.workers = max(1, min(64, workers))
        self.mode = mode
        self.verify = verify
        self.timeout = timeout
        self.session = make_session(self.workers + 8)
        if proxy:
            self.session.proxies.update({"http": proxy, "https": proxy})
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._snap = ProgressSnapshot()
        self._t0 = time.time()

    # ---- 取消 ----
    def cancel(self) -> None:
        self._stop.set()

    @property
    def cancelled(self) -> bool:
        return self._stop.is_set()

    # ---- 主入口 ----
    def run(self, tasks: Sequence[Task],
            on_progress: Callable[[ProgressSnapshot], None] | None = None,
            on_log: Callable[[str], None] | None = None) -> ProgressSnapshot:
        q: queue.Queue[Task] = queue.Queue()
        pending = [t for t in tasks if not _file_ok(t, self.verify)]
        skipped = len(tasks) - len(pending)

        total_bytes = sum(t.size for t in pending)
        # 未知大小的文件按文件名数量兜底
        if total_bytes <= 0:
            total_bytes = sum(max(t.size, 1) for t in pending)

        with self._lock:
            self._snap = ProgressSnapshot(
                total_bytes=total_bytes,
                total_files=len(pending),
                done_files=0,
            )
        self._t0 = time.time()

        if on_log and skipped:
            on_log(f"跳过 {skipped} 个已存在且校验通过的文件")
        if not pending:
            if on_progress:
                on_progress(self._snap)
            return self._snap

        for t in pending:
            q.put(t)

        def worker() -> None:
            while not self._stop.is_set():
                try:
                    task = q.get_nowait()
                except queue.Empty:
                    return
                try:
                    self._one(task, on_progress)
                except Exception as exc:  # noqa: BLE001
                    with self._lock:
                        self._snap.failed.append(f"{task.dest.name}: {exc}")
                    if on_log:
                        on_log(f"[失败] {task.label} → {exc}")
                finally:
                    with self._lock:
                        self._snap.done_files += 1
                        if task.size <= 0:
                            self._snap.done_bytes += 1
                        self._emit(on_progress)
                    q.task_done()

        threads = [threading.Thread(target=worker, daemon=True)
                   for _ in range(min(self.workers, len(pending)))]
        for th in threads:
            th.start()
        last = 0.0
        for th in threads:
            while th.is_alive():
                th.join(0.25)
                now = time.time()
                if on_progress and now - last >= 0.12:
                    self._emit(on_progress)
                    last = now
        self._emit(on_progress)
        return self._snap

    # ---- 单个文件 ----
    def _emit(self, on_progress) -> None:
        if not on_progress:
            return
        with self._lock:
            elapsed = max(1e-6, time.time() - self._t0)
            self._snap.speed = self._snap.done_bytes / elapsed
            snap = ProgressSnapshot(
                total_bytes=self._snap.total_bytes,
                done_bytes=self._snap.done_bytes,
                total_files=self._snap.total_files,
                done_files=self._snap.done_files,
                speed=self._snap.speed,
                current=self._snap.current,
                failed=list(self._snap.failed),
            )
        on_progress(snap)

    def _one(self, task: Task, on_progress) -> None:
        if _file_ok(task, self.verify):
            with self._lock:
                self._snap.done_bytes += task.size or task.dest.stat().st_size
            return

        with self._lock:
            self._snap.current = task.label

        task.dest.parent.mkdir(parents=True, exist_ok=True)
        candidates = [u for u in resolve(task.url, self.mode) if u]
        last_err: Exception | None = None

        for url in candidates:
            if self._stop.is_set():
                return
            try:
                self._fetch(url, task, on_progress)
                if self.verify and task.sha1:
                    got = sha1_of(task.dest)
                    if got.lower() != task.sha1.lower():
                        raise ValueError(f"哈希不匹配 {got[:8]}…")
                return
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                continue
        raise RuntimeError(f"所有源均失败：{last_err}")

    def _fetch(self, url: str, task: Task, on_progress) -> None:
        part = task.dest.with_suffix(task.dest.suffix + ".part")
        existing = part.stat().st_size if part.exists() else 0
        headers = {}
        if existing:
            headers["Range"] = f"bytes={existing}-"

        with self.session.get(url, stream=True, timeout=self.timeout,
                              headers=headers, allow_redirects=True) as r:
            if r.status_code == 416:      # 已经下完
                part.replace(task.dest)
                return
            if r.status_code not in (200, 206):
                r.raise_for_status()
            if existing and r.status_code == 200:
                existing = 0             # 服务端不支持断点，重头来
            mode = "ab" if existing else "wb"
            with open(part, mode) as f:
                for chunk in r.iter_content(256 * 1024):
                    if self._stop.is_set():
                        return
                    if not chunk:
                        continue
                    f.write(chunk)
                    with self._lock:
                        self._snap.done_bytes += len(chunk)
        if task.size and part.stat().st_size != task.size:
            # 尺寸不符，删掉让下次重下
            size = part.stat().st_size
            if size < task.size:
                raise IOError(f"文件不完整 {size}/{task.size}")
        part.replace(task.dest)
