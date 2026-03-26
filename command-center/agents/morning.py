#!/usr/bin/env python3
"""
Agent 1: Morning Protocol Agent
Runs at 7:00 AM via launchd.
- Sunrise light fade (warm → white over 20 min)
- Reads IronMind plan, picks music to match mental theme
- Generates personalized briefing
- Fires everything to Telegram as your daily mission brief
"""

import time, sys, threading
from agents.base import *

AGENT = "morning"

MUSIC_BY_THEME = {
    "discipline":    "hardcore workout",
    "patience":      "lo-fi hip hop",
    "focus":         "instrumental beats",
    "energy":        "Drake",
    "clarity":       "ambient",
    "grind":         "Travis Scott",
    "calm":          "jazz",
    "motivation":    "Kendrick Lamar",
    "deep work":     "classical",
    "default":       "morning vibes",
}

def sunrise_fade():
    """Fade lights from warm → white over 20 minutes in background."""
    log(AGENT, "Starting sunrise fade (warm → white, 20 min)")
    steps = [
        ("warm",  180, 0),      # start: warm, dim
        ("warm",  210, 120),    # brighten warm
        ("white", 220, 300),    # transition to white
        ("white", 230, 480),    # brighter
        ("cool",  240, 720),    # full daylight
        ("white", 254, 1200),   # peak brightness
    ]
    for color, bri, delay_s in steps:
        time.sleep(delay_s if delay_s == 0 else (steps[steps.index((color, bri, delay_s))][2] -
            steps[steps.index((color, bri, delay_s)) - 1][2] if steps.index((color, bri, delay_s)) > 0 else 0))
        try:
            hub_set_lights(color, bri)
            log(AGENT, f"  Light step: {color} bri={bri}")
        except Exception as e:
            log(AGENT, f"  Light step error: {e}")

def _sunrise_thread():
    """Run sunrise fade in a background thread with proper timing."""
    transitions = [
        (0,    "warm",  150),
        (180,  "warm",  190),
        (360,  "warm",  220),
        (540,  "white", 220),
        (720,  "white", 235),
        (900,  "cool",  245),
        (1200, "white", 254),
    ]
    start = time.time()
    for offset_s, color, bri in transitions:
        wait = offset_s - (time.time() - start)
        if wait > 0:
            time.sleep(wait)
        try:
            hub_set_lights(color, bri)
            log(AGENT, f"Sunrise: {color} bri={bri}")
        except Exception as e:
            log(AGENT, f"Sunrise error: {e}")

def get_plan_context() -> dict:
    """Fetch today's IronMind plan as a raw dict."""
    try:
        from database import im_get_plan
        from datetime import date
        return im_get_plan(date.today().strftime("%Y-%m-%d")) or {}
    except:
        return {}

def pick_music(plan: dict) -> str:
    theme = (plan.get("mental_theme") or "").lower()
    for key, music in MUSIC_BY_THEME.items():
        if key in theme:
            return music
    return MUSIC_BY_THEME["default"]

def build_morning_brief(weather: str, plan: dict, streaks: list) -> str:
    streak_lines = "\n".join(
        f"  • {s['name'].replace('_',' ')}: {s['current']} day streak"
        for s in streaks if s.get("current", 0) > 0
    ) or "  No active streaks yet."

    priorities = "\n".join(filter(None, [
        f"  1. {plan.get('priority_1','')}" if plan.get("priority_1") else "",
        f"  2. {plan.get('priority_2','')}" if plan.get("priority_2") else "",
        f"  3. {plan.get('priority_3','')}" if plan.get("priority_3") else "",
    ])) or "  No plan set — set one now."

    training = plan.get("training") or "No training scheduled"
    theme = plan.get("mental_theme") or "No theme"

    prompt = f"""You are Jordan's personal morning briefing AI. Write a powerful, direct, motivating morning message — 3-4 sentences max. No fluff. Reference the actual data. Sound like a coach who knows him.

Data:
- Weather: {weather}
- Today's priorities: {priorities}
- Training: {training}
- Mental theme: {theme}
- Active streaks: {streak_lines}

Write the message in plain text, no markdown, no emojis. Direct. Punchy. Like a drill sergeant who believes in him."""

    return claude(prompt, max_tokens=200)

def run():
    if was_fired_recently(f"{AGENT}_morning", hours=20):
        log(AGENT, "Already ran today, skipping.")
        return

    log(AGENT, "=== Morning Protocol starting ===")

    # 1. Start sunrise fade in background
    t = threading.Thread(target=_sunrise_thread, daemon=True)
    t.start()

    # 2. Gather data
    weather  = hub_weather()
    plan     = get_plan_context()
    streaks  = hub_ironmind_streaks()

    # 3. Pick and play music
    music_query = pick_music(plan)
    try:
        hub_play_music(music_query)
        log(AGENT, f"Music: {music_query}")
    except Exception as e:
        log(AGENT, f"Music error: {e}")

    # 4. Generate brief
    brief = build_morning_brief(weather, plan, streaks)
    log(AGENT, f"Brief: {brief[:80]}...")

    # 5. Build full Telegram message
    priorities_text = "\n".join(filter(None, [
        f"1️⃣ {plan.get('priority_1','')}" if plan.get("priority_1") else "",
        f"2️⃣ {plan.get('priority_2','')}" if plan.get("priority_2") else "",
        f"3️⃣ {plan.get('priority_3','')}" if plan.get("priority_3") else "",
    ])) or "No plan set."

    streak_active = [s for s in streaks if s.get("current", 0) > 0]
    streak_text = "  ".join(f"🔥 {s['name'].replace('_',' ')} {s['current']}d" for s in streak_active) or "None yet."

    message = f"""⚡ <b>MORNING PROTOCOL</b>

{brief}

📋 <b>TODAY'S MISSION:</b>
{priorities_text}

🏋️ Training: {plan.get('training', 'Rest day')}
🧘 Theme: {plan.get('mental_theme', '—')}

🔥 <b>ACTIVE STREAKS:</b>
{streak_text}

{weather}

<i>Lights: sunrise fade active · Music: {music_query}</i>"""

    telegram_send(message)
    mark_fired(f"{AGENT}_morning")
    log(AGENT, "Morning protocol complete.")

    # Wait for sunrise thread to finish
    t.join(timeout=1300)


if __name__ == "__main__":
    run()
