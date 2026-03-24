#!/usr/bin/env python3
"""
Adler's Brain — Proactive Context Engine
Watches Jordan's patterns and environment, fires Telegram nudges before you ask.

What it does:
  • Morning context  — personalized good-morning (weather + what's on pattern)
  • Scene suggestions — "It's your usual Friday Night time, want me to set it?"
  • Cross-signal      — rain + your history = heads-up before you think to check
  • Weather warnings  — extreme conditions pushed automatically

Usage:
  python3 proactive.py run      # Daemon (checks every 15 min)
  python3 proactive.py check    # One-shot check right now
  python3 proactive.py status   # Show last nudge times
  python3 proactive.py install  # Register as launchd service
"""

import os
import sys
import json
import time
import subprocess
import requests as req
from pathlib import Path
from datetime import datetime, timedelta

# ── Load env ──────────────────────────────────────────────────────────────────
ENV_PATH = Path(__file__).parent / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
SCRIPT_DIR       = Path(__file__).parent
NUDGE_LOG_PATH   = SCRIPT_DIR / "nudge_log.json"
CHECK_INTERVAL   = 15 * 60   # 15 minutes

# Quiet hours — no nudges between these hours
QUIET_START = 23
QUIET_END   = 7


# ── Nudge log (dedup) ─────────────────────────────────────────────────────────

def load_nudge_log() -> list:
    if NUDGE_LOG_PATH.exists():
        try:
            return json.loads(NUDGE_LOG_PATH.read_text())
        except Exception:
            pass
    return []


def save_nudge_log(log: list):
    # Keep last 500 entries max
    NUDGE_LOG_PATH.write_text(json.dumps(log[-500:], indent=2))


def was_nudged_recently(nudge_type: str, hours: float = 20) -> bool:
    """Returns True if we already sent this nudge type within `hours` hours."""
    log = load_nudge_log()
    cutoff = datetime.now() - timedelta(hours=hours)
    for entry in reversed(log):
        if entry["type"] == nudge_type:
            try:
                ts = datetime.fromisoformat(entry["ts"])
                if ts > cutoff:
                    return True
            except Exception:
                pass
    return False


def record_nudge(nudge_type: str, message: str):
    log = load_nudge_log()
    log.append({
        "type": nudge_type,
        "message": message[:200],
        "ts": datetime.now().isoformat(),
    })
    save_nudge_log(log)


# ── Telegram ──────────────────────────────────────────────────────────────────

def send_telegram(text: str, parse_mode: str = "HTML") -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[Telegram not configured]\n{text}")
        return False
    try:
        r = req.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": parse_mode},
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:
        print(f"Telegram error: {e}")
        return False


# ── Weather ───────────────────────────────────────────────────────────────────

def get_weather() -> dict:
    try:
        r = req.get(
            "https://wttr.in/Rockford,IL?format=j1",
            timeout=8,
            headers={"User-Agent": "JordanHub/1.0"},
        )
        d = r.json()["current_condition"][0]
        hourly = r.json().get("weather", [{}])[0].get("hourly", [])

        # Check if rain expected today
        desc = d["weatherDesc"][0]["value"].lower()
        rain_today = any(
            "rain" in h.get("weatherDesc", [{}])[0].get("value", "").lower()
            for h in hourly
        )

        return {
            "ok":         True,
            "temp":       int(d["temp_F"]),
            "feels":      int(d["FeelsLikeF"]),
            "humidity":   int(d["humidity"]),
            "desc":       d["weatherDesc"][0]["value"],
            "rain_today": rain_today or "rain" in desc,
            "is_extreme": int(d["temp_F"]) < 10 or int(d["temp_F"]) > 95,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Scene runner ──────────────────────────────────────────────────────────────

def run_scene_inputs(inputs: list) -> str:
    """Execute a list of natural language commands through hub.py."""
    results = []
    for inp in inputs:
        try:
            r = subprocess.run(
                ["python3", str(SCRIPT_DIR / "hub.py"), inp],
                capture_output=True, text=True, timeout=20, cwd=str(SCRIPT_DIR),
            )
            out = r.stdout.strip()
            if out:
                results.append(out)
        except Exception as e:
            results.append(f"Error: {e}")
    return "\n".join(results) if results else "Scene commands sent."


# ── Nudge logic ───────────────────────────────────────────────────────────────

def check_morning_nudge(hour: int, weather: dict) -> bool:
    """Fire a personalized morning nudge at 7-9am, once per day."""
    if not (7 <= hour <= 9):
        return False
    if was_nudged_recently("morning_context", hours=20):
        return False

    now  = datetime.now()
    dow  = now.strftime("%A")
    date = now.strftime("%B %-d")

    lines = [f"☀️ <b>Good morning, Jordan.</b>  <i>{dow}, {date}</i>"]
    lines.append("")

    if weather["ok"]:
        temp  = weather["temp"]
        desc  = weather["desc"]
        emoji = "🌧" if weather["rain_today"] else ("🥶" if temp < 32 else ("🔥" if temp > 85 else "🌤"))
        lines.append(f"{emoji} <b>{desc}</b>, {temp}°F in Rockford")
        if weather["rain_today"]:
            lines.append("Rain expected today — plan accordingly.")
        elif weather["is_extreme"]:
            lines.append("⚠️ Extreme temps today, heads up.")

    lines.append("")
    lines.append("Type your briefing whenever you're ready, or just tell me what you need.")

    msg = "\n".join(lines)
    if send_telegram(msg):
        record_nudge("morning_context", msg)
        print(f"[{now.strftime('%H:%M')}] Sent morning context nudge")
        return True
    return False


def check_scene_suggestion(hour: int, dow_name: str) -> bool:
    """
    If the current time matches a known scene's historical trigger,
    suggest running it — once per day per scene.
    """
    try:
        from pattern_engine import build_jordan_model
        model = build_jordan_model(days=60)
    except Exception:
        return False

    candidates = model.get("scene_candidates", [])
    fired = False

    for scene in candidates:
        if scene["confidence"] < 0.4:
            continue

        scene_hour = scene["avg_hour"]
        scene_dow  = scene["common_dow"]

        # Match: within ±1 hour AND same day or adjacent day
        hour_match = abs(hour - scene_hour) <= 1
        dow_match  = (
            scene_dow == dow_name
            or scene_dow in ("weekday",) and dow_name not in ("Saturday", "Sunday")
            or scene_dow in ("weekend",) and dow_name in ("Saturday", "Sunday")
        )

        if not (hour_match and dow_match):
            continue

        nudge_key = f"scene_{scene['name'].lower().replace(' ', '_')}"
        if was_nudged_recently(nudge_key, hours=22):
            continue

        # Build suggestion message
        inputs_preview = " + ".join(f'"{i}"' for i in scene["sample_inputs"][:3])
        msg = (
            f"🎭 <b>{scene['name']}</b> — your usual time\n"
            f"\n"
            f"You normally do: {inputs_preview}\n"
            f"({scene['count']} times, usually ~{scene['avg_hour'] % 12 or 12}"
            f"{'am' if scene['avg_hour'] < 12 else 'pm'})\n"
            f"\n"
            f'Reply <b>"run {scene["name"].lower()} scene"</b> to activate it.'
        )

        if send_telegram(msg):
            record_nudge(nudge_key, msg)
            print(f"[{datetime.now().strftime('%H:%M')}] Suggested scene: {scene['name']}")
            fired = True
            break   # One scene suggestion per check cycle

    return fired


def check_weather_crosssignal(weather: dict, hour: int) -> bool:
    """
    Cross-signal: rain today + Jordan's historical rainy-day behavior.
    Only fires once per rainy day.
    """
    if not weather.get("ok") or not weather.get("rain_today"):
        return False
    if not (9 <= hour <= 11):
        return False
    if was_nudged_recently("rain_crosssignal", hours=20):
        return False

    msg = (
        "🌧 <b>Rain day in Rockford</b>\n"
        "\n"
        "Heads up — rain expected today. Good day to stay in and build something.\n"
        'Want your briefing? Just say "briefing".'
    )
    if send_telegram(msg):
        record_nudge("rain_crosssignal", msg)
        print(f"[{datetime.now().strftime('%H:%M')}] Sent rain cross-signal nudge")
        return True
    return False


def check_weekly_report_due(hour: int, dow_name: str) -> bool:
    """Fire the weekly report on Sunday mornings."""
    if dow_name != "Sunday" or hour != 9:
        return False
    if was_nudged_recently("weekly_report", hours=23 * 6):
        return False

    try:
        result = subprocess.run(
            ["python3", str(SCRIPT_DIR / "weekly_report.py"), "--send"],
            capture_output=True, text=True, timeout=30, cwd=str(SCRIPT_DIR),
        )
        if result.returncode == 0:
            record_nudge("weekly_report", "weekly report sent")
            print(f"[{datetime.now().strftime('%H:%M')}] Sent weekly report")
            return True
    except Exception as e:
        print(f"Weekly report error: {e}")
    return False


# ── Main check cycle ──────────────────────────────────────────────────────────

def run_check() -> int:
    """Run one check cycle. Returns number of nudges fired."""
    now      = datetime.now()
    hour     = now.hour
    dow_name = now.strftime("%A")

    # Quiet hours — no nudges
    if hour >= QUIET_START or hour < QUIET_END:
        return 0

    weather = get_weather()
    fired   = 0

    if check_morning_nudge(hour, weather):
        fired += 1

    if check_weather_crosssignal(weather, hour):
        fired += 1

    if check_scene_suggestion(hour, dow_name):
        fired += 1

    if check_weekly_report_due(hour, dow_name):
        fired += 1

    return fired


# ── Status ────────────────────────────────────────────────────────────────────

def print_status():
    log = load_nudge_log()
    if not log:
        print("No nudges sent yet.")
        return

    print(f"\n🧠 Proactive Engine — Last Nudges\n")
    recent = sorted(log, key=lambda e: e["ts"], reverse=True)[:15]
    for entry in recent:
        ts = entry["ts"][:16].replace("T", " ")
        print(f"  {ts}  [{entry['type']:30s}]  {entry['message'][:60]}")
    print()


# ── launchd install ───────────────────────────────────────────────────────────

def install_launchd():
    python3  = subprocess.run(["which", "python3"], capture_output=True, text=True).stdout.strip()
    label    = "com.jordan.proactive"
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
    log_path = SCRIPT_DIR / "proactive.log"

    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>

    <key>ProgramArguments</key>
    <array>
        <string>{python3}</string>
        <string>{SCRIPT_DIR / "proactive.py"}</string>
        <string>run</string>
    </array>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>{log_path}</string>

    <key>StandardErrorPath</key>
    <string>{log_path}</string>
</dict>
</plist>
"""
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    # Unload if already running
    subprocess.run(["launchctl", "unload", str(plist_path)],
                   capture_output=True)
    plist_path.write_text(plist)
    result = subprocess.run(["launchctl", "load", str(plist_path)],
                            capture_output=True, text=True)
    if result.returncode == 0:
        print(f"✅  Proactive engine installed and running")
        print(f"   Plist: {plist_path}")
        print(f"   Log:   {log_path}")
    else:
        print(f"⚠️  Plist written but launchctl failed:")
        print(f"   {result.stderr.strip()}")
        print(f"   Try: launchctl load {plist_path}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"

    if cmd == "run":
        print(f"🧠 Adler's proactive engine started (checking every {CHECK_INTERVAL // 60} min)")
        print("   Ctrl+C to stop.\n")
        while True:
            n = run_check()
            if n:
                print(f"  → {n} nudge(s) sent")
            time.sleep(CHECK_INTERVAL)

    elif cmd == "check":
        now = datetime.now()
        print(f"[{now.strftime('%H:%M:%S')}] Running check...")
        n = run_check()
        print(f"Done — {n} nudge(s) sent.")

    elif cmd == "status":
        print_status()

    elif cmd == "install":
        install_launchd()

    else:
        print(__doc__)
