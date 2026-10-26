# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：单文件 + 无控制台窗口。

用法：
    .venv\\Scripts\\pyinstaller --noconfirm build.spec
"""

EXCLUDES = [
    # PyQt5 里用不到的模块，剔掉能省几十 MB
    "PyQt5.QtWebEngine", "PyQt5.QtWebEngineCore", "PyQt5.QtWebEngineWidgets",
    "PyQt5.QtWebKit", "PyQt5.QtWebKitWidgets", "PyQt5.QtWebSockets",
    "PyQt5.QtMultimedia", "PyQt5.QtMultimediaWidgets", "PyQt5.QtQml",
    "PyQt5.QtQuick", "PyQt5.QtQuickWidgets", "PyQt5.QtBluetooth",
    "PyQt5.QtDesigner", "PyQt5.QtHelp", "PyQt5.QtLocation", "PyQt5.QtNfc",
    "PyQt5.QtPositioning", "PyQt5.QtSerialPort", "PyQt5.QtSql",
    "PyQt5.QtTest", "PyQt5.QtXml", "PyQt5.QtDBus", "PyQt5.QtOpenGL",
    "PyQt5.QtSvg", "PyQt5.QtPrintSupport",
    # 标准库里没必要带的
    "tkinter", "unittest", "pydoc", "doctest", "xmlrpc", "pdb",
    "distutils", "setuptools", "pip",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[("assets/icon.ico", "assets"), ("assets/icon.png", "assets")],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# --------------------------------------------------------------------------- #
# 瘦身：纯 QWidget 应用用不到下面这些 Qt 组件，剔掉能省近一半体积
#   opengl32sw   Qt 的软件 OpenGL 渲染器（20 MB，只有 QtQuick/OpenGL 才用）
#   Qt5Qml / Qt5Quick / d3dcompiler_47 / libGLESv2   QML 与 ANGLE 栈
#   Qt5Network / Qt5DBus   我们不通过 Qt 联网（用的是 requests）
#   多余的平台插件与图片格式插件，只留 qwindows + qico
# --------------------------------------------------------------------------- #
_DROP_FILES = {
    "opengl32sw.dll", "d3dcompiler_47.dll", "libglesv2.dll", "libegl.dll",
    "qt5quick.dll", "qt5qml.dll", "qt5qmlmodels.dll", "qt5quickwidgets.dll",
    "qt5quickparticles.dll", "qt5network.dll", "qt5dbus.dll",
    "qt5xmlpatterns.dll", "qt5designer.dll", "qt5help.dll",
    "qt5printsupport.dll", "qt5svg.dll", "qt5multimedia.dll",
    "qt5multimediawidgets.dll", "qt5location.dll", "qt5positioning.dll",
    "qt5sensors.dll", "qt5websockets.dll", "qt5serialport.dll",
    "qt5sql.dll", "qt5test.dll", "qt5concurrent.dll",
}
_KEEP_IMAGEFORMATS = {"qico.dll", "qjpeg.dll"}
_KEEP_PLATFORMS = {"qwindows.dll", "qoffscreen.dll", "qminimal.dll"}


def _slim(entry):
    dest = entry[0].replace("\\", "/").lower()
    base = dest.rsplit("/", 1)[-1]
    if base in _DROP_FILES:
        return False
    if "/platforms/" in dest:
        return base in _KEEP_PLATFORMS
    if "/styles/" in dest:
        return "vistastyle" in base
    if "/imageformats/" in dest:
        return base in _KEEP_IMAGEFORMATS
    if "/translations/" in dest:
        return False
    if "/qml/" in dest or "/qmltooling/" in dest:
        return False
    return True


a.binaries = [x for x in a.binaries if _slim(x)]
a.datas = [x for x in a.datas if _slim(x)]

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="BMCLAPIDownloader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",
    version="assets/version_info.txt",
)
