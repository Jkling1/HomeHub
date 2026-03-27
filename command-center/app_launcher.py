#!/usr/bin/env python3
"""
Command Center — Native macOS app launcher.
Uses pywebview (native WebKit) — no Chrome, no browser chrome.
"""

import subprocess
import sys
import time
import threading
import requests
import webview
from pathlib import Path

ROOT = Path(__file__).parent
PORT = 8888


def wait_for_server(timeout=15):
    for _ in range(timeout):
        try:
            requests.get(f"http://localhost:{PORT}", timeout=1)
            return True
        except:
            time.sleep(1)
    return False


def start_server():
    subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server:app",
         "--host", "0.0.0.0", "--port", str(PORT)],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main():
    # Start server if not running
    try:
        requests.get(f"http://localhost:{PORT}", timeout=1)
    except:
        start_server()
        if not wait_for_server():
            print("Server failed to start")
            sys.exit(1)

    # Launch native WebKit window
    window = webview.create_window(
        title="Command Center",
        url=f"http://localhost:{PORT}",
        fullscreen=True,
        min_size=(1024, 768),
    )
    webview.start()


if __name__ == "__main__":
    main()
