#!/usr/bin/env python3
"""Install Jordan Smart Hub server as a launchd daemon (auto-start on boot)."""

import subprocess
from pathlib import Path

ROOT   = Path(__file__).parent
PYTHON = subprocess.run(["which", "python3"], capture_output=True, text=True).stdout.strip()
LAUNCH_DIR = Path.home() / "Library/LaunchAgents"
LAUNCH_DIR.mkdir(parents=True, exist_ok=True)

PLIST_ID   = "com.jordan.hub.server"
PLIST_PATH = LAUNCH_DIR / f"{PLIST_ID}.plist"

PLIST = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{PLIST_ID}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{PYTHON}</string>
        <string>{ROOT}/server.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{ROOT}</string>
    <key>StandardOutPath</key>
    <string>{ROOT}/server.log</string>
    <key>StandardErrorPath</key>
    <string>{ROOT}/server.log</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>10</integer>
</dict>
</plist>"""

def install():
    PLIST_PATH.write_text(PLIST)
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True)
    result = subprocess.run(["launchctl", "load", str(PLIST_PATH)], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"✓ {PLIST_ID}")
        print(f"  Hub will auto-start on boot and restart on crash.")
        print(f"  Logs: {ROOT}/server.log")
        print(f"\nTo stop:    launchctl unload ~/Library/LaunchAgents/{PLIST_ID}.plist")
        print(f"To restart: launchctl unload ... && launchctl load ...")
    else:
        print(f"✗ Install failed: {result.stderr.strip()}")

def uninstall():
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True)
    if PLIST_PATH.exists():
        PLIST_PATH.unlink()
    print("✓ Server launchd entry removed.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "uninstall":
        uninstall()
    else:
        install()
