#!/usr/bin/env python3
"""
Jordan Smart Hub — intent parser and action executor.
Receives any natural language command, sends to Claude API,
gets structured JSON back, executes the right action(s).

Usage: python3 hub.py "turn lights blue and play Drake"
       echo "briefing" | python3 hub.py
"""

import sys
import json
import os
import subprocess
import requests
import apple_music
from pathlib import Path

# ── Load env ──────────────────────────────────────────────────────────────────
ENV_PATH = Path(__file__).parent / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
HUE_BRIDGE = os.environ.get("HUE_BRIDGE", "192.168.12.225")
HUE_KEY = os.environ.get("HUE_KEY", "B4B06IWHPqPPuV5siAJNFr-Qc7pXPe030uwdCMdp")
SCRIPT_DIR = Path(__file__).parent


SYSTEM_PROMPT = """You are the AI brain of Jordan's Smart Hub — a personal home automation assistant for a user named Jordan in Rockford, IL.

Your job is to interpret any natural language input and return ONLY a valid JSON object describing the action(s) to take. No explanation, no markdown, no prose — just JSON.

AVAILABLE ACTIONS:

1. lights — control Philips Hue lights
   { "action": "lights", "color": "<color name or 'off' or 'on' or 'white'>", "brightness": <0-254 optional> }
   Colors: red, green, blue, purple, orange, yellow, pink, white, cyan, warm, cool, off, on

2. music — control Apple Music
   { "action": "music", "command": "<play|pause|resume|skip|back|stop|volume>", "query": "<song or artist name optional>", "volume": <0-100 optional> }

3. briefing — deliver the daily command center briefing
   { "action": "briefing" }

4. weather — current weather only
   { "action": "weather" }

5. stock — stock market update
   { "action": "stock" }

6. chat — general conversation or question (not an automation command)
   { "action": "chat", "reply": "<your response as Jordan's assistant>" }

7. multi — multiple actions at once
   { "action": "multi", "commands": [ <action1>, <action2>, ... ] }

8. wakeup — manage the morning wake-up routine
   { "action": "wakeup", "command": "<set|enable|disable|status|run>", "time": "<HH:MM or 7:30am>" }

9. ironmind — personal performance system
   { "action": "ironmind", "command": "<plan|set_plan|log|get_log|streaks|coach|journal|identity|review|status>",
     optionally: "priority_1", "priority_2", "priority_3", "training", "nutrition_target", "mental_theme",
     "metrics": {"workout_done":1, "mood":8, "sleep":7, "protein":180, "steps":8000, "hydration_oz":80},
     "went_right": "...", "cut_corners": "...", "tomorrow_std": "...",
     "statement": "I am the type of person who..." }
   - "what's my plan today" / "show my mission" → plan
   - "set today's priorities: X, Y, Z" → set_plan
   - "log workout done, mood 8, sleep 7 hours" → log with metrics
   - "show today's log" / "how did I do today" → get_log
   - "show my streaks" / "streak status" → streaks
   - "coach me" / "give me feedback" / "how am I doing" → coach
   - "journal: went right X, cut corners Y, standard tomorrow Z" → journal (save)
   - "show my journal" → journal (view)
   - "show my identity" / "who am I" → identity
   - "add identity: I never miss a workout" → identity (add)
   - "weekly review" / "how was my week" → review

10. scene — run or manage smart scenes
   { "action": "scene", "command": "<run|list|save|delete|learn>", "name": "<scene name>", "inputs": ["<cmd1>", "<cmd2>"] }
   - "run my wind down scene" / "activate friday night scene" → run, name=scene name
   - "list my scenes" / "what scenes do you know" → list
   - "save this as evening vibe" → save (saves last few commands as a scene)
   - "learn my scenes" / "detect scenes" → learn (auto-detect from history)
   - "delete wind down scene" → delete

10. report — weekly life report
    { "action": "report" }
    - "weekly report" / "how was my week" / "show my stats" → report

11. patterns — show behavior insights
    { "action": "patterns" }
    - "what are my patterns" / "what do I usually do" / "show insights" → patterns

12. stock_alert — manage stock price alerts
   { "action": "stock_alert", "command": "<add|remove|list|check>", "symbol": "<ticker>", "type": "<above|below|change>", "target": <number>, "id": <alert_id optional> }
   - "alert me when NVDA hits 150" → add, symbol=NVDA, type=above, target=150
   - "alert when TSLA drops below 200" → add, symbol=TSLA, type=below, target=200
   - "alert if AAPL moves 5 percent" → add, symbol=AAPL, type=change, target=5
   - "show my stock alerts" / "list alerts" → list
   - "remove stock alert 3" → remove, id=3
   - "check stock alerts now" → check

RULES:
- Always return valid JSON, nothing else
- If the user asks for lights + music together, use "multi"
- Be tolerant of typos and casual phrasing
- "briefing", "what's my briefing", "morning update" → briefing action
- "pause", "stop music", "skip" → music action
- If unclear, use "chat" action and respond helpfully
- For "play <song/artist>", set command to "play" and query to what they want
- Volume commands: "volume 80", "louder", "quieter" → music volume action
- "set wake-up for 7am", "wake me at 7:30" → wakeup action with command=set and time extracted
- "disable wake-up", "turn off wake-up" → wakeup action with command=disable
- "wake-up status", "what time is wake-up" → wakeup action with command=status
- "run wake-up now", "test wake-up" → wakeup action with command=run"""


# ── Claude API call ───────────────────────────────────────────────────────────
def parse_intent(user_input: str) -> dict:
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 512,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_input}],
    }
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers=headers,
        json=body,
        timeout=15,
    )
    resp.raise_for_status()
    text = resp.json()["content"][0]["text"].strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


# ── Action executors ──────────────────────────────────────────────────────────

COLOR_MAP = {
    "red":    {"hue": 0,     "sat": 254},
    "orange": {"hue": 6000,  "sat": 254},
    "yellow": {"hue": 12000, "sat": 254},
    "green":  {"hue": 25000, "sat": 254},
    "cyan":   {"hue": 36000, "sat": 254},
    "blue":   {"hue": 46920, "sat": 254},
    "purple": {"hue": 48000, "sat": 254},
    "pink":   {"hue": 56000, "sat": 220},
    "warm":   {"hue": 8000,  "sat": 180},
    "cool":   {"hue": 43000, "sat": 80},
    "white":  {"hue": 41000, "sat": 20},
}

def do_lights(cmd: dict) -> str:
    color = cmd.get("color", "").lower()
    brightness = cmd.get("brightness", 200)

    if color == "off":
        state = {"on": False}
        label = "off"
    elif color in ("on", ""):
        state = {"on": True, "bri": brightness}
        label = "on"
    else:
        c = COLOR_MAP.get(color, COLOR_MAP["white"])
        state = {"on": True, "bri": brightness, **c}
        label = color

    lights = requests.get(f"http://{HUE_BRIDGE}/api/{HUE_KEY}/lights", timeout=5).json()
    ok = 0
    for lid, info in lights.items():
        # Only send color to color-capable bulbs
        if "hue" in state and info.get("type", "").lower() not in ("extended color light", "color light"):
            safe_state = {k: v for k, v in state.items() if k not in ("hue", "sat")}
        else:
            safe_state = state
        r = requests.put(f"http://{HUE_BRIDGE}/api/{HUE_KEY}/lights/{lid}/state", json=safe_state, timeout=5)
        if any("success" in str(x) for x in r.json()):
            ok += 1

    return f"💡 Lights set to {label} ({ok} lights updated)"


def do_music(cmd: dict) -> str:
    return apple_music.handle(cmd)


def do_briefing() -> str:
    out = subprocess.run(
        ["python3", str(SCRIPT_DIR / "briefing_telegram.py")],
        capture_output=True, text=True, timeout=30
    ).stdout.strip()
    return out


def do_weather() -> str:
    try:
        r = requests.get("https://wttr.in/Rockford,IL?format=j1", timeout=8,
                         headers={"User-Agent": "JordanHub/1.0"})
        d = r.json()["current_condition"][0]
        return (f"🌤 Rockford, IL: {d['weatherDesc'][0]['value']}, "
                f"{d['temp_F']}°F, feels like {d['FeelsLikeF']}°F, "
                f"humidity {d['humidity']}%")
    except Exception as e:
        return f"Weather unavailable: {e}"


def do_stock() -> str:
    try:
        import yfinance as yf
        watchlist = ["NVDA", "AAPL", "TSLA", "MSFT", "META", "AMZN", "GOOGL"]
        best = None
        best_pct = None
        for sym in watchlist:
            try:
                t = yf.Ticker(sym)
                info = t.fast_info
                price = float(getattr(info, "last_price", 0) or 0)
                prev = float(getattr(info, "previous_close", 0) or 0)
                if price and prev:
                    pct = (price - prev) / prev * 100
                    if best_pct is None or pct > best_pct:
                        best_pct = pct
                        best = {"sym": sym, "price": price, "pct": pct}
            except Exception:
                continue
        if best:
            arrow = "▲" if best["pct"] >= 0 else "▼"
            return f"📈 Top mover: {best['sym']} ${best['price']:.2f} {arrow}{abs(best['pct']):.2f}%"
        return "Market data unavailable"
    except Exception as e:
        return f"Stock data unavailable: {e}"


# ── Dispatch ──────────────────────────────────────────────────────────────────

def execute(cmd: dict) -> str:
    action = cmd.get("action", "chat")

    if action == "lights":
        return do_lights(cmd)
    elif action == "music":
        return do_music(cmd)
    elif action == "briefing":
        return do_briefing()
    elif action == "weather":
        return do_weather()
    elif action == "stock":
        return do_stock()
    elif action == "chat":
        return cmd.get("reply", "Got it.")
    elif action == "wakeup":
        return do_wakeup(cmd)
    elif action == "ironmind":
        import ironmind
        return ironmind.handle(cmd)
    elif action == "scene":
        return do_scene(cmd)
    elif action == "report":
        return do_report()
    elif action == "patterns":
        return do_patterns()
    elif action == "stock_alert":
        return do_stock_alert(cmd)
    elif action == "multi":
        results = []
        for sub in cmd.get("commands", []):
            if "type" in sub and "action" not in sub:
                sub = {**sub, "action": sub["type"]}
            results.append(execute(sub))
        return "\n".join(results)
    else:
        return f"Unknown action: {action}"


def do_scene(cmd: dict) -> str:
    from database import get_scenes, get_scene, save_scene, delete_scene, increment_scene_run
    command = cmd.get("command", "list")

    if command == "run":
        name = cmd.get("name", "")
        if not name:
            return "Which scene? Try 'list my scenes' to see what I know."
        scene = get_scene(name)
        if not scene:
            return f"❌ No scene named '{name}'. Try 'list my scenes'."
        inputs = scene.get("inputs", [])
        if not inputs:
            return f"❌ Scene '{name}' has no commands."
        increment_scene_run(scene["name"])
        results = []
        for inp in inputs:
            try:
                intent = parse_intent(inp)
                results.append(execute(intent))
            except Exception as e:
                results.append(f"Error on '{inp}': {e}")
        return f"🎭 {scene['name']} scene activated:\n" + "\n".join(results)

    elif command == "list":
        scenes = get_scenes()
        if not scenes:
            return "No scenes yet. Say 'learn my scenes' to auto-detect from your history, or say 'learn my scenes'."
        lines = ["🎭 Your scenes:"]
        for s in scenes:
            auto = " (auto)" if s.get("auto_learned") else ""
            runs = f"  ×{s['times_run']}" if s["times_run"] > 0 else ""
            lines.append(f"  • {s['name']}{auto}{runs}")
        return "\n".join(lines)

    elif command == "save":
        name   = cmd.get("name", "")
        inputs = cmd.get("inputs", [])
        if not name:
            return "What should I call this scene?"
        if not inputs:
            return "What commands should this scene run? E.g. 'purple lights, play Drake'"
        save_scene(name, inputs)
        return f"✅ Scene '{name}' saved with {len(inputs)} command(s)."

    elif command == "delete":
        name = cmd.get("name", "")
        if not name:
            return "Which scene should I delete?"
        existing = get_scene(name)
        if not existing:
            return f"No scene named '{name}'."
        delete_scene(name)
        return f"🗑 Scene '{name}' deleted."

    elif command == "learn":
        try:
            from pattern_engine import build_jordan_model
            from database import save_scene as db_save_scene
            model = build_jordan_model(days=60)
            candidates = model.get("scene_candidates", [])
            if not candidates:
                return "Not enough history to detect scenes yet. Keep using the hub!"
            saved = 0
            for c in candidates[:5]:  # save top 5 candidates
                existing = get_scene(c["name"])
                if not existing:
                    db_save_scene(
                        name=c["name"],
                        inputs=c["sample_inputs"],
                        trigger_hour=c["avg_hour"],
                        trigger_dow=c["common_dow"],
                        confidence=c["confidence"],
                        auto_learned=True,
                    )
                    saved += 1
            if saved:
                return (f"🧠 Learned {saved} scene(s) from your history:\n" +
                        "\n".join(f"  • {c['name']} (~{c['avg_hour']}:00 {c['common_dow']}, "
                                  f"{c['count']}x, {c['confidence']:.0%} confidence)"
                                  for c in candidates[:saved]))
            return "Your existing scenes are already up to date."
        except Exception as e:
            return f"Scene learning error: {e}"

    return f"Unknown scene command: {command}"


def do_report() -> str:
    try:
        result = subprocess.run(
            ["python3", str(SCRIPT_DIR / "weekly_report.py")],
            capture_output=True, text=True, timeout=15, cwd=str(SCRIPT_DIR),
        )
        return result.stdout.strip() or "Report unavailable."
    except Exception as e:
        return f"Report error: {e}"


def do_patterns() -> str:
    try:
        from pattern_engine import build_jordan_model
        model = build_jordan_model(days=60)
        if "error" in model:
            return "No history yet to analyze. Keep using the hub!"

        lines = [f"🧠 Your patterns ({model['history_count']} commands analyzed):"]

        peaks = model["peak_hours"]
        if peaks:
            peak_hour = max(peaks, key=peaks.get)
            ampm = f"{peak_hour % 12 or 12}{'am' if peak_hour < 12 else 'pm'}"
            lines.append(f"  ⏰ Most active at {ampm}")

        wp = model["weekly_pattern"]
        peak_day = max(wp, key=wp.get) if wp else "?"
        lines.append(f"  📅 Busiest day: {peak_day}")

        colors = model["top_colors"]
        if colors:
            lines.append(f"  💡 Favorite light: {colors[0][0]} ({colors[0][1]}x)")

        music = model["top_music"]
        if music:
            lines.append(f"  🎵 Top track: {music[0][0]} ({music[0][1]}x)")

        candidates = model["scene_candidates"]
        if candidates:
            lines.append(f"  🎭 {len(candidates)} scene pattern(s) detected")
            for c in candidates[:3]:
                lines.append(f"     • {c['name']} ({c['count']}x, {c['confidence']:.0%})")
            lines.append(f"  Say 'learn my scenes' to save them.")

        drift = model.get("recent_drift", {})
        if drift.get("count_delta"):
            delta = drift["count_delta"]
            sign  = "+" if delta > 0 else ""
            lines.append(f"  📈 Recent trend: {sign}{delta} commands vs prior period")

        return "\n".join(lines)
    except Exception as e:
        return f"Patterns error: {e}"


def do_stock_alert(cmd: dict) -> str:
    import stock_alerts as sa
    command = cmd.get("command", "list")

    if command == "add":
        symbol = cmd.get("symbol", "")
        kind   = cmd.get("type", "above")
        target = cmd.get("target")
        if not symbol or target is None:
            return "❌ Need a symbol and target price. E.g. 'alert when NVDA hits 150'"
        alerts = sa.load_alerts()
        alert  = {
            "id":         sa.next_id(alerts),
            "symbol":     symbol.upper(),
            "type":       kind,
            "target":     float(target),
            "triggered":  False,
            "created_at": __import__("datetime").datetime.now().isoformat(),
        }
        alerts.append(alert)
        sa.save_alerts(alerts)
        data = sa.get_price(symbol)
        price_str = f" (now ${data['price']:.2f})" if data else ""
        return f"🔔 Alert #{alert['id']} set: {symbol.upper()} {kind} {target}{price_str}"

    elif command == "remove":
        alert_id = cmd.get("id")
        if alert_id is None:
            return "❌ Which alert ID? Run 'list alerts' to see IDs."
        alerts = sa.load_alerts()
        before = len(alerts)
        alerts = [a for a in alerts if a["id"] != int(alert_id)]
        if len(alerts) == before:
            return f"❌ No alert with ID {alert_id}."
        sa.save_alerts(alerts)
        return f"🗑 Alert #{alert_id} removed."

    elif command == "check":
        fired = sa.run_check(quiet=True)
        if fired:
            return f"🔔 {len(fired)} alert(s) triggered and sent to Telegram."
        return "✅ Checked all alerts — no conditions met yet."

    else:  # list
        alerts = sa.load_alerts()
        if not alerts:
            return "No stock alerts set. Try: 'alert me when NVDA hits 150'"
        active    = [a for a in alerts if not a.get("triggered")]
        triggered = [a for a in alerts if a.get("triggered")]
        lines = [f"📊 Stock Alerts ({len(active)} active):"]
        for a in active:
            lines.append(f"  #{a['id']} {a['symbol']} {a['type']} {a['target']}")
        if triggered:
            lines.append(f"  ({len(triggered)} already triggered)")
        return "\n".join(lines)


def do_wakeup(cmd: dict) -> str:
    command = cmd.get("command", "status")
    time_str = cmd.get("time", "")
    if command == "set" and time_str:
        result = subprocess.run(
            ["python3", str(SCRIPT_DIR / "wakeup_schedule.py"), "set", time_str],
            capture_output=True, text=True, cwd=str(SCRIPT_DIR)
        )
        out = result.stdout.strip() or result.stderr.strip()
        return f"⏰ {out}"
    elif command == "disable":
        result = subprocess.run(
            ["python3", str(SCRIPT_DIR / "wakeup_schedule.py"), "disable"],
            capture_output=True, text=True, cwd=str(SCRIPT_DIR)
        )
        return result.stdout.strip() or "⏸ Wake-up disabled"
    elif command == "enable":
        result = subprocess.run(
            ["python3", str(SCRIPT_DIR / "wakeup_schedule.py"), "enable"],
            capture_output=True, text=True, cwd=str(SCRIPT_DIR)
        )
        return result.stdout.strip() or "▶️ Wake-up enabled"
    elif command == "run":
        subprocess.Popen(["python3", str(SCRIPT_DIR / "wakeup.py")],
                         cwd=str(SCRIPT_DIR))
        return "🌅 Running wake-up routine now..."
    else:
        result = subprocess.run(
            ["python3", str(SCRIPT_DIR / "wakeup_schedule.py"), "status"],
            capture_output=True, text=True, cwd=str(SCRIPT_DIR)
        )
        return result.stdout.strip()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) > 1:
        user_input = " ".join(sys.argv[1:])
    else:
        user_input = sys.stdin.read().strip()

    if not user_input:
        print("No input provided.")
        sys.exit(1)

    cmd = parse_intent(user_input)
    result = execute(cmd)
    print(result)


if __name__ == "__main__":
    main()
