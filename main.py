"""程序入口。"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from app import APP_NAME, APP_TITLE
from app.qt import QApplication, QFont, QIcon, QMessageBox, Qt
from app.main_window import MainWindow
from app import theme


def _resource(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return base / "assets" / name


def _crash_log(text: str) -> None:
    """无控制台的 exe 里 stderr 是 None，异常信息必须先落盘。"""
    try:
        d = Path(os.environ.get("APPDATA") or Path.home()) / APP_NAME
        d.mkdir(parents=True, exist_ok=True)
        (d / "crash.log").write_text(text, "utf-8")
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    # Qt 5 的高 DPI 开关必须在创建 QApplication 之前设置
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_TITLE)
    app.setFont(QFont(theme.FONT_UI, 10))

    icon_path = _resource("icon.ico")
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))

    def hook(t, v, tb):
        text = "".join(traceback.format_exception(t, v, tb))
        _crash_log(text)
        try:
            if sys.stderr is not None:
                sys.stderr.write(text)
        except Exception:  # noqa: BLE001
            pass
        try:
            QMessageBox.critical(None, "程序异常", text[-1500:])
        except Exception:
            pass

    sys.excepthook = hook

    win = MainWindow()
    win.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
