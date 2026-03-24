#!/usr/bin/env python3
"""
Agent 3: Cross-Signal Adaptive Engine
Runs every 15 minutes. Reads all signals — weather, time, music state,
light state, IronMind score/mood — and reasons about whether to intervene.
Fires context-aware automations without being asked.
"""

import json
from agents.base import *

AGENT = "adaptive"

# Cooldown: don't repeat the same intervention within N hours
INTERVENTION_COOLDOWN = {
    "rainy_chill":    3,
    "post_workout":   4,
    "late_night":     6,
    "low_mood":       4,
    "high_energy":    4,
    "focus_mode":     3,
    "wind_down":      5,
}

INTERVENTION_SYSTEM = """You are the adaptive automation brain for Jordan's smart home.
Analyze the current state and decide if an intervention should happen.

Available actions:
- set_lights: <color> (red/orange/yellow/green/cyan/blue/purple/pink/warm/white/cool/off)
- play_music: <query>
- send_telegram: <message>
- no_action

Rules:
- Only intervene if there's a clear signal that an action would improve Jordan's situation
- Don't intervene if he's clearly already in a good state
- Be decisive — pick ONE action or no_action
- Interventions should feel smart, not annoying

Return ONLY valid JSON like: {"action": "set_lights", "value": "warm", "reason": "rainy + evening", "label": "rainy_chill"}
Or: {"action": "no_action", "reason": "state looks good"}"""

def build_state_summary(status: dict, weather: str, log_data: dict) -> str:
    hour = now_hour()
    music = status.get("music", {})
    lights = status.get("lights", {})

    playing = music.get("playing", False)
    track = music.get("track", "nothing")
    volume = music.get("volume", 0)
    light_color = lights.get("color", "unknown")
    light_on = lights.get("power", 0)

    score = log_data.get("score", 0)
    mood = log_data.get("mood") or 0
    workout_done = log_data.get("workout_done", 0)

    time_of_day = (
        "early morning" if hour < 7 else
        "morning" if hour < 12 else
        "afternoon" if hour < 17 else
        "evening" if hour < 21 else
        "late night"
    )

    return f"""Current state:
- Time: {now_str()} ({time_of_day})
- Weather: {weather}
- Music: {"playing" if playing else "stopped"} ({track}) at volume {volume}%
- Lights: {light_color if light_on else "off"}
- IronMind score today: {score}/10
- Mood logged: {mood}/10
- Workout done: {"yes" if workout_done else "no"}"""

def decide_intervention(state_summary: str) -> dict:
    try:
        result = claude(state_summary, system=INTERVENTION_SYSTEM, max_tokens=150)
        # Extract JSON from response
        if result.startswith("```"):
            result = result.split("```")[1]
            if result.startswith("json"):
                result = result[4:]
        return json.loads(result.strip())
    except Exception as e:
        log(AGENT, f"Decision parse error: {e}")
        return {"action": "no_action", "reason": "parse error"}

def execute_intervention(decision: dict):
    action = decision.get("action")
    value  = decision.get("value", "")
    label  = decision.get("label", "adaptive")
    reason = decision.get("reason", "")

    log(AGENT, f"Executing: {action} ({label}) — {reason}")

    if action == "set_lights":
        hub_set_lights(value)
        log(AGENT, f"Lights → {value}")

    elif action == "play_music":
        hub_play_music(value)
        log(AGENT, f"Music → {value}")

    elif action == "send_telegram":
        telegram_send(f"💡 <b>Auto:</b> {value}")
        log(AGENT, f"Telegram → {value[:60]}")

    elif action == "multi":
        # Handle multi-action: {"action": "multi", "steps": [...]}
        for step in decision.get("steps", []):
            execute_intervention(step)

    mark_fired(f"{AGENT}_{label}")


def run():
    log(AGENT, "Adaptive engine tick")

    try:
        status   = hub_status()
        weather  = hub_weather()
        log_data = hub_ironmind_log()
    except Exception as e:
        log(AGENT, f"Data fetch error: {e}")
        return

    state_summary = build_state_summary(status, weather, log_data)
    log(AGENT, f"State: {state_summary[:120]}...")

    decision = decide_intervention(state_summary)
    log(AGENT, f"Decision: {decision}")

    action = decision.get("action", "no_action")
    label  = decision.get("label", "adaptive")

    if action == "no_action":
        log(AGENT, "No intervention needed.")
        return

    # Cooldown check
    cooldown_hours = INTERVENTION_COOLDOWN.get(label, 2)
    if was_fired_recently(f"{AGENT}_{label}", hours=cooldown_hours):
        log(AGENT, f"Intervention '{label}' on cooldown ({cooldown_hours}h).")
        return

    execute_intervention(decision)
    log(AGENT, "Adaptive intervention complete.")


if __name__ == "__main__":
    run()
