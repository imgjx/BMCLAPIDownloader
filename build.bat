@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [1/4] 检查虚拟环境...
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv || goto :err
)

echo [2/4] 安装依赖...
".venv\Scripts\python.exe" -m pip install -q requests PyQt5 pyinstaller || goto :err

echo [3/4] 生成图标...
".venv\Scripts\python.exe" tools\make_icon.py || goto :err

echo [4/4] 打包为单文件 exe...
".venv\Scripts\pyinstaller.exe" --noconfirm --clean build.spec || goto :err

echo.
echo 打包完成： dist\BMCLAPIDownloader.exe
pause
exit /b 0

:err
echo.
echo 出错了，请看上面的日志。
pause
exit /b 1
