"""离屏冒烟测试：跑起主窗口、截图、验证核心逻辑。不弹窗。

用法：
    set QT_QPA_PLATFORM=offscreen
    .venv\\Scripts\\python tools\\smoke.py
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MCDL_SKIP_SCAN", "1")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.qt import Qt, QTimer, QApplication  # noqa: E402

OUT = ROOT / "preview"
errors: list[str] = []


def check(name: str, fn) -> None:
    try:
        r = fn()
        print(f"  [OK] {name}: {r}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"{name}: {exc}")
        print(f"  [FAIL] {name}: {exc}")
        traceback.print_exc()


def main() -> int:
    from app import theme
    from app.main_window import MainWindow
    from app import net, api, paths

    app = QApplication(sys.argv)
    # 离屏环境下 QFontDatabase 是空的，手动注册系统字体才能看到文字
    try:
        from PyQt5.QtGui import QFontDatabase
        if not QFontDatabase().families():
            for p in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc",
                      "C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/arial.ttf"):
                QFontDatabase.addApplicationFont(p)
    except Exception:
        pass
    app.setStyleSheet(theme.qss())

    print("== 单元检查 ==")
    check("镜像映射 launchermeta", lambda: net.to_mirror(
        "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json"))
    check("镜像映射 libraries", lambda: net.to_mirror(
        "https://libraries.minecraft.net/com/x/y.jar"))
    check("镜像映射 assets", lambda: net.to_mirror(
        "https://resources.download.minecraft.net/ab/abcdef"))
    check("反向还原", lambda: net.to_official(
        "https://bmclapi2.bangbang93.com/maven/com/x/y.jar"))
    check("maven 路径", lambda: api.maven_path(
        "org.lwjgl:lwjgl:3.3.1:natives-windows"))
    check("rules 判断", lambda: api.library_allowed(
        {"rules": [{"action": "allow", "os": {"name": "windows"}}]}))
    check("目录识别(AppData)", lambda: [
        p for p in paths.quick_candidates() if p.is_dir()][:3])

    print("== 网络检查 ==")
    def fetch_manifest():
        c = net.Client()
        m = api.Manifest(c)
        vs = m.load()
        return f"{len(vs)} 个版本, latest release = {m.latest.get('release')}"
    check("拉取 BMCLAPI 版本清单", fetch_manifest)

    def small_download():
        from app.net import Downloader, Task
        tmp = ROOT / "preview" / "tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        dest = tmp / "1.20.1.json"
        if dest.exists():
            dest.unlink()
        tasks = [Task(url="https://bmclapi2.bangbang93.com/version/1.20.1/json",
                      dest=dest, label="1.20.1.json")]
        snap = Downloader(workers=2).run(tasks)
        return f"{dest.stat().st_size} 字节, 失败 {len(snap.failed)} 个"
    check("下载引擎（真实下载版本 json）", small_download)

    print("== UI 渲染 ==")
    win = MainWindow()
    win.resize(1160, 760)
    win.show()

    shots = []

    def grab(name: str) -> None:
        OUT.mkdir(parents=True, exist_ok=True)
        pix = win.grab()
        p = OUT / name
        pix.save(str(p), "PNG")
        shots.append(p)
        print(f"  截图 → {p}  ({pix.width()}x{pix.height()})")

    def step1() -> None:
        grab("01-download.png")
        win._nav("settings")
        win.stack.setCurrentWidget(win.page_settings)

    def step2() -> None:
        grab("02-settings.png")
        win.stack.setCurrentWidget(win.page_download)
        # 造一点进度，验证进度页排版
        win.p_title.setText("正在安装 1.20.1 · Fabric")
        win.p_stage.setText("下载游戏文件")
        win._log("版本 1.20.1 共 128 个文件，约 412.5 MB")
        win._log("资源索引 5 含 3121 个对象")
        win._log("Fabric：1.20.1 可用 12 个版本")
        for i in range(1, 41):
            win.bar.set_value(i / 60, animated=False)
            win.ring.set_value(i / 60)
        win.s_speed.setText("6.2 MB/s")
        win.s_eta.setText("1 分 12 秒")
        win.s_files.setText("37 / 128")
        win.s_size.setText("142.8 MB / 412.5 MB")
        win.stack.setCurrentWidget(win.page_progress)

    def step3() -> None:
        grab("03-progress.png")
        app.quit()

    QTimer.singleShot(7000, step1)
    QTimer.singleShot(7800, step2)
    QTimer.singleShot(8800, step3)

    app.exec_()

    print("== 结果 ==")
    if errors:
        print(f"有 {len(errors)} 项失败")
        for e in errors:
            print("  -", e)
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
