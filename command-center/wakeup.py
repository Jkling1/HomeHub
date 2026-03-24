#!/usr/bin/env python3
"""
Jordan Smart Hub — Morning Wake-Up Routine
Runs as a standalone script via launchd at the scheduled time.

Sequence:
  0:00  — Lights: warm white at bri=1 (nearly off), begin 10-min hardware fade to bri=254
  0:00  — Music: start morning playlist at volume 20
  1:30  — Music: volume → 35
  3:00  — Music: volume → 45
  4:30  — Music: volume → 55
  6:00  — Music: volume → 65
  8:00  — Music: volume → 72
 10:00  — Send morning briefing + greeting via Telegram
"""

import os
import sys
import time
import subprocess
import requests
from pathlib import Path
from datetime import datetime

# ── Load env ──────────────────────────────────────────────────────────────────
ENV_PATH = Path(__file__).parent / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

HUE_BRIDGE        = os.environ.get("HUE_BRIDGE", "192.168.12.225")
HUE_KEY           = os.environ.get("HUE_KEY", "")
TELEGRAM_TOKEN    = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID  = os.environ.get("TELEGRAM_CHAT_ID", "")
SCRIPT_DIR        = Path(__file__).parent

# ── Config (can be overridden by wakeup_config.json) ─────────────────────────
CONFIG_PATH = SCRIPT_DIR / "wakeup_config.json"

DEFAULT_CONFIG = {
    "enabled": True,
    "wake_time": "07:00",
    "fade_minutes": 10,
    "playlist_query": "Come Together",
    "volume_start": 20,
    "volume_end": 72,
    "send_briefing": True,
}


def load_config() -> dict:
    import json
    if CONFIG_PATH.exists():
        try:
            saved = json.loads(CONFIG_PATH.read_text())
            return {**DEFAULT_CONFIG, **saved}
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(cfg: dict):
    import json
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


# ── Telegram ──────────────────────────────────────────────────────────────────
def telegram_send(text: str, parse_mode: str = "MarkdownV2"):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured — skipping message")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": parse_mode},
            timeout=10,
        )
    except Exception as e:
        print(f"Telegram error: {e}")


# ── Hue lights ────────────────────────────────────────────────────────────────
def hue_put(lid: str, state: dict):
    try:
        requests.put(
            f"http://{HUE_BRIDGE}/api/{HUE_KEY}/lights/{lid}/state",
            json=state, timeout=5,
        )
    except Exception as e:
        print(f"Hue error light {lid}: {e}")


def lights_sunrise(fade_minutes: int):
    """
    Step 1: Snap all color lights to warm white at bri=1 (instant).
    Step 2: Send a single fade command with transitiontime = fade_minutes * 600
            (Hue transitiontime unit = 100ms, so 600 = 60s = 1 minute).
    Result: a perfectly smooth hardware-level sunrise, no polling needed.
    """
    try:
        lights = requests.get(
            f"http://{HUE_BRIDGE}/api/{HUE_KEY}/lights", timeout=5
        ).json()
    except Exception as e:
        print(f"Could not reach Hue bridge: {e}")
        return

    # Warm sunrise color
    WARM = {"hue": 7000, "sat": 220}
    transition_units = fade_minutes * 600  # 1 min = 600 units

    for lid, info in lights.items():
        is_color = "color" in info.get("type", "").lower()

        # Step 1: snap to on + bri=1 + warm (instant, transitiontime=1)
        snap_state = {"on": True, "bri": 1, "transitiontime": 1}
        if is_color:
            snap_state.update(WARM)
        hue_put(lid, snap_state)

    # Brief pause so snap completes before fade starts
    time.sleep(0.5)

    for lid, info in lights.items():
        is_color = "color" in info.get("type", "").lower()

        # Step 2: smooth fade to full brightness over fade_minutes
        fade_state = {"bri": 254, "transitiontime": transition_units}
        if is_color:
            fade_state.update(WARM)
        hue_put(lid, fade_state)

    print(f"☀️  Sunrise fade started — {fade_minutes} minutes to full brightness")


# ── Apple Music ───────────────────────────────────────────────────────────────
def osascript(script: str) -> str:
    r = subprocess.run(["osascript", "-e", script],
                       capture_output=True, text=True, timeout=10)
    return r.stdout.strip()


def music_start(query: str, volume: int):
    """Start playlist at low volume."""
    safe = query.replace('"', "'")
    osascript('tell application "Music" to activate')
    time.sleep(1)

    script = f'''
    tell application "Music"
        set sound volume to {volume}
        set allTracks to tracks of playlist "Library"
        repeat with t in allTracks
            set tname to name of t
            set lname to do shell script "echo " & quoted form of tname & " | tr '[:upper:]' '[:lower:]'"
            set lq to do shell script "echo " & quoted form of "{safe}" & " | tr '[:upper:]' '[:lower:]'"
            if lname contains lq or (artist of t) contains "{safe}" then
                play t
                return (name of t) & "|||" & (artist of t)
            end if
        end repeat
        -- fallback: just play library
        play playlist "Library"
        return "Library"
    end tell
    '''
    out = osascript(script)
    parts = out.split("|||")
    track = parts[0].strip() if parts else query
    artist = parts[1].strip() if len(parts) > 1 else ""
    print(f"🎵  Playing: {track}{' — ' + artist if artist else ''} at vol {volume}")
    return track, artist


def music_set_volume(volume: int):
    osascript(f'tell application "Music" to set sound volume to {volume}')
    print(f"🔊  Volume → {volume}")


# ── Briefing ──────────────────────────────────────────────────────────────────
def get_briefing() -> str:
    try:
        result = subprocess.run(
            ["python3", str(SCRIPT_DIR / "briefing_telegram.py")],
            capture_output=True, text=True, timeout=30,
        )
        return result.stdout.strip()
    except Exception as e:
        return f"Briefing unavailable: {e}"


# ── Main routine ──────────────────────────────────────────────────────────────
def run_wakeup():
    cfg = load_config()
    fade_minutes  = cfg["fade_minutes"]
    playlist      = cfg["playlist_query"]
    vol_start     = cfg["volume_start"]
    vol_end       = cfg["volume_end"]
    send_briefing = cfg["send_briefing"]

    now = datetime.now().strftime("%I:%M %p")
    print(f"\n🌅 Wake-up routine started at {now}")
    print(f"   Fade: {fade_minutes} min | Playlist: {playlist} | Vol: {vol_start}→{vol_end}\n")

    # 1. Start sunrise lights
    lights_sunrise(fade_minutes)

    # 2. Start music at low volume
    track, artist = music_start(playlist, vol_start)

    # 3. Volume fade schedule over fade_minutes
    #    Steps: evenly distribute volume_start → volume_end across the fade window
    total_seconds = fade_minutes * 60
    steps = [
        (total_seconds * 0.15, int(vol_start + (vol_end - vol_start) * 0.20)),
        (total_seconds * 0.30, int(vol_start + (vol_end - vol_start) * 0.40)),
        (total_seconds * 0.45, int(vol_start + (vol_end - vol_start) * 0.58)),
        (total_seconds * 0.60, int(vol_start + (vol_end - vol_start) * 0.74)),
        (total_seconds * 0.78, int(vol_start + (vol_end - vol_start) * 0.90)),
        (total_seconds * 0.95, vol_end),
    ]

    last_sleep = 0
    for (t, vol) in steps:
        sleep_for = t - last_sleep
        if sleep_for > 0:
            time.sleep(sleep_for)
        music_set_volume(vol)
        last_sleep = t

    # Wait for remainder
    remaining = total_seconds - last_sleep
    if remaining > 0:
        time.sleep(remaining)

    # 4. Send Telegram greeting + briefing
    print("\n📱  Sending morning briefing to Telegram...")

    greeting_lines = [
        f"🌅 *Good morning, Jordan\\.*",
        f"",
        f"Your wake\\-up routine just finished\\.",
        f"Lights are at full sunrise warmth\\.",
        f"▶️ {track.replace('.','\\.')} is playing\\.",
        f"",
        f"Here's your briefing 👇",
    ]
    telegram_send("\n".join(greeting_lines))
    time.sleep(2)

    if send_briefing:
        briefing = get_briefing()
        if briefing:
            telegram_send(briefing)

    print("\n✅  Wake-up routine complete.\n")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--config":
        # Print current config
        import json
        print(json.dumps(load_config(), indent=2))
    else:
        run_wakeup()
