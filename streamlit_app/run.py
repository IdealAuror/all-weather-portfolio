import subprocess
import webbrowser
import time
import urllib.request
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
APP_FILE = Path(__file__).resolve().parent / "app.py"
URL = "http://localhost:8501"

def server_ready():
    try:
        urllib.request.urlopen(URL, timeout=1)
        return True
    except Exception:
        return False

proc = subprocess.Popen(
    [sys.executable, "-m", "streamlit", "run", str(APP_FILE), "--server.headless=false"],
    cwd=str(PROJECT_DIR),
)

print(f"正在启动（PID {proc.pid}）...", flush=True)
for _ in range(60):
    if server_ready():
        webbrowser.open(URL)
        print("已打开浏览器", flush=True)
        break
    time.sleep(1)
else:
    print(f"超时，手动打开 {URL}", flush=True)

proc.wait()
