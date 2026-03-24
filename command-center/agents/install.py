#!/usr/bin/env python3
"""Install all agent launchd daemons."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent
PYTHON = subprocess.run(["which", "python3"], capture_output=True, text=True).stdout.strip()
LAUNCH_DIR = Path.home() / "Library/LaunchAgents"
LAUNCH_DIR.mkdir(parents=True, exist_ok=True)

PLISTS = {
    "com.jordan.agent.morning": {
        "program": PYTHON,
        "args": [str(ROOT / "run_agent.py"), "morning"],
        "hour": 7, "minute": 0,
        "label": "Morning Protocol (7:00 AM daily)",
    },
    "com.jordan.agent.accountability": {
        "program": PYTHON,
        "args": [str(ROOT / "run_agent.py"), "accountability"],
        "interval": 3600,  # every hour
        "label": "IronMind Accountability (hourly)",
    },
    "com.jordan.agent.adaptive": {
        "program": PYTHON,
        "args": [str(ROOT / "run_agent.py"), "adaptive"],
        "interval": 900,  # every 15 min
        "label": "Adaptive Engine (every 15 min)",
    },
    "com.jordan.agent.stock": {
        "program": PYTHON,
        "args": [str(ROOT / "run_agent.py"), "stock"],
        "interval": 300,  # every 5 min
        "label": "Stock Intelligence (every 5 min)",
    },
}

def make_plist(plist_id: str, config: dict) -> str:
    program_args = [config["program"]] + config["args"]
    args_xml = "\n        ".join(f"<string>{a}</string>" for a in program_args)

    if "interval" in config:
        schedule_xml = f"<key>StartInterval</key>\n    <integer>{config['interval']}</integer>"
    else:
        schedule_xml = f"""<key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>{config['hour']}</integer>
        <key>Minute</key><integer>{config['minute']}</integer>
    </dict>"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{plist_id}</string>
    <key>ProgramArguments</key>
    <array>
        {args_xml}
    </array>
    {schedule_xml}
    <key>WorkingDirectory</key>
    <string>{ROOT}</string>
    <key>StandardOutPath</key>
    <string>{ROOT}/agent.log</string>
    <key>StandardErrorPath</key>
    <string>{ROOT}/agent.log</string>
    <key>RunAtLoad</key>
    <false/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>"""

def install():
    print(f"Installing Jordan Hub agents...\n")
    installed = []

    for plist_id, config in PLISTS.items():
        plist_path = LAUNCH_DIR / f"{plist_id}.plist"
        content = make_plist(plist_id, config)
        plist_path.write_text(content)

        # Unload if already loaded
        subprocess.run(["launchctl", "unload", str(plist_path)],
                       capture_output=True)
        # Load
        result = subprocess.run(["launchctl", "load", str(plist_path)],
                                capture_output=True, text=True)
        status = "✓" if result.returncode == 0 else f"✗ {result.stderr.strip()}"
        print(f"  {status} {plist_id}")
        print(f"     {config['label']}")
        installed.append(plist_id)

    print(f"\n{len(installed)} agents installed.")
    print(f"Logs: {ROOT}/agent.log")
    print(f"\nTo uninstall: launchctl unload ~/Library/LaunchAgents/com.jordan.agent.*.plist")
    print(f"To run now:   python3 run_agent.py <morning|accountability|adaptive|stock>")

if __name__ == "__main__":
    install()
