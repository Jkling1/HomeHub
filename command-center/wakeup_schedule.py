#!/usr/bin/env python3
"""
Manage the wake-up routine's launchd schedule on macOS.
Creates/updates/removes ~/Library/LaunchAgents/com.jordan.wakeup.plist

Usage:
  python3 wakeup_schedule.py set 07:30     # Schedule for 7:30 AM daily
  python3 wakeup_schedule.py disable       # Unload without deleting
  python3 wakeup_schedule.py enable        # Re-load existing plist
  python3 wakeup_schedule.py remove        # Delete plist entirely
  python3 wakeup_schedule.py status        # Show current schedule
"""

import sys
import os
import subprocess
import json
from pathlib import Path

PLIST_LABEL = "com.jordan.wakeup"
PLIST_PATH  = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"
SCRIPT_DIR  = Path(__file__).parent
WAKEUP_PY   = SCRIPT_DIR / "wakeup.py"
CONFIG_PATH = SCRIPT_DIR / "wakeup_config.json"
LOG_PATH    = SCRIPT_DIR / "wakeup.log"


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    return {"enabled": False, "wake_time": "07:00"}


def save_config(cfg: dict):
    existing = load_config()
    existing.update(cfg)
    CONFIG_PATH.write_text(json.dumps(existing, indent=2))


def write_plist(hour: int, minute: int):
    python3 = subprocess.run(["which", "python3"], capture_output=True, text=True).stdout.strip()
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{PLIST_LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>{python3}</string>
        <string>{WAKEUP_PY}</string>
    </array>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>{hour}</integer>
        <key>Minute</key>
        <integer>{minute}</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>{LOG_PATH}</string>

    <key>StandardErrorPath</key>
    <string>{LOG_PATH}</string>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
"""
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(plist)
    print(f"✅  Plist written to {PLIST_PATH}")


def launchctl(args: list) -> bool:
    r = subprocess.run(["launchctl"] + args, capture_output=True, text=True)
    if r.returncode != 0 and r.stderr:
        print(f"launchctl: {r.stderr.strip()}")
    return r.returncode == 0


def unload():
    launchctl(["unload", str(PLIST_PATH)])


def load():
    return launchctl(["load", str(PLIST_PATH)])


def set_schedule(time_str: str):
    """Set daily wake-up time. time_str format: HH:MM (24h) or H:MMam/pm."""
    time_str = time_str.strip().lower()

    # Parse flexible time formats
    if "am" in time_str or "pm" in time_str:
        import re
        m = re.match(r"(\d+):?(\d{0,2})(am|pm)", time_str)
        if not m:
            print("❌  Could not parse time. Use formats like 7:30, 07:30, 7:30am, 7am")
            return False
        h, mn, ampm = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        if ampm == "pm" and h != 12:
            h += 12
        elif ampm == "am" and h == 12:
            h = 0
    else:
        parts = time_str.split(":")
        h, mn = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0

    if not (0 <= h <= 23 and 0 <= mn <= 59):
        print("❌  Invalid time.")
        return False

    # Unload existing if present
    if PLIST_PATH.exists():
        unload()

    write_plist(h, mn)
    success = load()

    time_display = f"{h % 12 or 12}:{mn:02d} {'AM' if h < 12 else 'PM'}"
    if success:
        save_config({"enabled": True, "wake_time": f"{h:02d}:{mn:02d}"})
        print(f"⏰  Wake-up routine scheduled for {time_display} daily")
        return True
    else:
        print(f"⚠️   Plist written but launchctl load failed. Try running manually:")
        print(f"    launchctl load {PLIST_PATH}")
        return False


def disable():
    if PLIST_PATH.exists():
        unload()
        save_config({"enabled": False})
        print("⏸   Wake-up routine disabled (plist kept, use 'enable' to restore)")
    else:
        print("No wake-up plist found.")


def enable():
    if PLIST_PATH.exists():
        success = load()
        if success:
            save_config({"enabled": True})
            print("▶️   Wake-up routine re-enabled")
    else:
        cfg = load_config()
        wake_time = cfg.get("wake_time", "07:00")
        print(f"No plist found — creating one for {wake_time}")
        set_schedule(wake_time)


def remove():
    if PLIST_PATH.exists():
        unload()
        PLIST_PATH.unlink()
        save_config({"enabled": False})
        print("🗑   Wake-up plist removed")
    else:
        print("No wake-up plist found.")


def status():
    cfg = load_config()
    wake_time = cfg.get("wake_time", "not set")
    enabled = cfg.get("enabled", False)
    playlist = cfg.get("playlist_query", "Come Together")
    fade = cfg.get("fade_minutes", 10)

    # Check if actually loaded in launchctl
    r = subprocess.run(["launchctl", "list", PLIST_LABEL], capture_output=True, text=True)
    loaded = r.returncode == 0

    print(f"\n⏰  Wake-Up Routine Status")
    print(f"   Time:     {wake_time}")
    print(f"   Enabled:  {enabled}")
    print(f"   Loaded:   {loaded}")
    print(f"   Playlist: {playlist}")
    print(f"   Fade:     {fade} minutes")
    print(f"   Plist:    {PLIST_PATH}")
    print(f"   Log:      {LOG_PATH}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        status()
        sys.exit(0)

    cmd = sys.argv[1].lower()

    if cmd == "set" and len(sys.argv) > 2:
        set_schedule(sys.argv[2])
    elif cmd == "disable":
        disable()
    elif cmd == "enable":
        enable()
    elif cmd == "remove":
        remove()
    elif cmd == "status":
        status()
    else:
        print(__doc__)
