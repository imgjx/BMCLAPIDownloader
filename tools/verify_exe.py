"""验证打包后的 exe：能否启动、是否正常初始化、有没有崩溃日志。"""
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXE = ROOT / "dist" / "BMCLAPIDownloader.exe"
APPDATA = Path(os.environ.get("APPDATA") or Path.home()) / "BMCLAPIDownloader"
CFG = APPDATA / "config.json"
CRASH = APPDATA / "crash.log"

print("exe:", EXE, f"{EXE.stat().st_size / 1048576:.1f} MB")

for f in (CFG, CRASH):
    if f.exists():
        f.unlink()

env = dict(os.environ)
env["QT_QPA_PLATFORM"] = "offscreen"
env["MCDL_SKIP_SCAN"] = "1"

proc = subprocess.Popen([str(EXE)], env=env,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
print("已启动 pid", proc.pid)

alive = None
for i in range(1, 16):
    time.sleep(1)
    alive = proc.poll() is None
    if CFG.exists() or CRASH.exists():
        break

print(f"{i} 秒后：进程存活={alive}, 退出码={proc.returncode}")
print("config.json 存在:", CFG.exists())
print("crash.log 存在:", CRASH.exists())

if CRASH.exists():
    print("--- crash.log ---")
    print(CRASH.read_text("utf-8", errors="replace")[:2000])

if CFG.exists():
    print("--- config.json ---")
    print(CFG.read_text("utf-8", errors="replace")[:400])

# 收尾
if proc.poll() is None:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    print("已结束进程")

sys.exit(0 if (alive and CFG.exists() and not CRASH.exists()) else 1)
