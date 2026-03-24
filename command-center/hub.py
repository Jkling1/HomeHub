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
    elif action == "multi":
        results = []
        for sub in cmd.get("commands", []):
            if "type" in sub and "action" not in sub:
                sub = {**sub, "action": sub["type"]}
            results.append(execute(sub))
        return "\n".join(results)
    else:
        return f"Unknown action: {action}"


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
