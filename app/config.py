"""配置持久化：%APPDATA%/BMCLAPIDownloader/config.json"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from . import net
from . import APP_NAME

DEFAULTS: dict[str, Any] = {
    "game_dir": "",
    "workers": 16,
    "source": net.Source.AUTO,
    "verify": True,
    "with_assets": True,
    "java_path": "",
    "window": [1160, 760],
}


def _appdata() -> Path:
    return Path(os.environ.get("APPDATA") or str(Path.home()))


def config_path() -> Path:
    d = _appdata() / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d / "config.json"


def legacy_config_path() -> Path:
    """旧版本（MCDL）的配置位置，用于一次性迁移。"""
    return _appdata() / "MCDL" / "config.json"


class Config:
    def __init__(self) -> None:
        self.data: dict[str, Any] = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        p = config_path()
        migrated = False
        if not p.is_file():
            old = legacy_config_path()
            if old.is_file():
                p = old
                migrated = True
        if p.is_file():
            try:
                raw = json.loads(p.read_text("utf-8"))
                if isinstance(raw, dict):
                    self.data.update(
                        {k: v for k, v in raw.items() if k in DEFAULTS}
                    )
            except Exception:
                pass
            if migrated:
                self.save()

    def save(self) -> None:
        try:
            config_path().write_text(
                json.dumps(self.data, ensure_ascii=False, indent=2), "utf-8")
        except OSError:
            pass

    def __getitem__(self, k: str) -> Any:
        return self.data.get(k, DEFAULTS.get(k))

    def __setitem__(self, k: str, v: Any) -> None:
        self.data[k] = v

    def get(self, k: str, default: Any = None) -> Any:
        return self.data.get(k, default)
