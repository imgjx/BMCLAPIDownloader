@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo 还没装依赖，先跑 build.bat
    pause
    exit /b 1
)
".venv\Scripts\python.exe" main.py
