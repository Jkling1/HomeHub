#!/usr/bin/env python3
"""
Agent 2: IronMind Accountability Loop
Runs every hour via launchd. Fires targeted nudges at checkpoint times
based on what metrics are missing. Knows your streaks and calls you out.
"""

from agents.base import *

AGENT = "accountability"

CHECKPOINTS = {
    11: {
        "label": "Morning check-in",
        "metrics": ["workout_done", "steps"],
        "focus": "Did you train? Morning window is closing.",
    },
    14: {
        "label": "Midday check-in",
        "metrics": ["hydration_oz", "protein_g", "calories"],
        "focus": "Midday nutrition and hydration check.",
    },
    18: {
        "label": "Evening check-in",
        "metrics": ["workout_done", "steps", "hydration_oz"],
        "focus": "Last chance for workout and hydration.",
    },
    21: {
        "label": "Night wrap-up",
        "metrics": ["sleep_hours", "mood", "notes"],
        "focus": "Time to reflect. Log the day before it disappears.",
    },
}

METRIC_LABELS = {
    "workout_done":  "workout",
    "steps":         "steps",
    "calories":      "calories",
    "protein_g":     "protein",
    "hydration_oz":  "hydration",
    "sleep_hours":   "sleep",
    "mood":          "mood",
    "notes":         "reflection",
}

def get_missing_metrics(log_data: dict, metric_keys: list) -> list:
    missing = []
    for key in metric_keys:
        val = log_data.get(key)
        if val is None or val == 0 or val == "":
            missing.append(METRIC_LABELS.get(key, key))
    return missing

def generate_nudge(checkpoint: dict, missing: list, streaks: list, log_data: dict) -> str:
    streak_at_risk = [s for s in streaks if s.get("current", 0) > 0 and s["name"] in
                      ("workout" if "workout" in missing else "", "hydration" if "hydration" in missing else "")]
    streak_at_risk = [s for s in streaks if s.get("current", 0) > 0]

    streak_context = ""
    if streak_at_risk:
        biggest = max(streak_at_risk, key=lambda s: s["current"])
        streak_context = f"You have a {biggest['current']}-day {biggest['name'].replace('_',' ')} streak. Don't break it today."

    score = log_data.get("score", 0)

    prompt = f"""You are Jordan's IronMind accountability agent. Send a SHORT, direct Telegram nudge. Max 2 sentences. No emojis in the text itself. Be specific about the missing data. Be firm but not cruel.

Context:
- Time: {checkpoint['label']}
- Focus: {checkpoint['focus']}
- Missing metrics: {', '.join(missing)}
- Current day score: {score}/10
- Streak context: {streak_context}

Write the nudge message in plain text, conversational but firm. Reference specific missing metrics."""

    return claude(prompt, max_tokens=100)

def run():
    hour = now_hour()
    log(AGENT, f"Running at hour {hour}")

    checkpoint = CHECKPOINTS.get(hour)
    if not checkpoint:
        log(AGENT, f"No checkpoint at hour {hour}, skipping.")
        return

    fire_key = f"{AGENT}_{hour}_{today_str()}"
    if was_fired_recently(fire_key, hours=20):
        log(AGENT, f"Checkpoint {hour}h already fired today.")
        return

    # Get today's data
    log_data = hub_ironmind_log()
    streaks  = hub_ironmind_streaks()

    missing = get_missing_metrics(log_data, checkpoint["metrics"])

    if not missing:
        log(AGENT, f"Checkpoint {hour}h: all metrics logged, no nudge needed.")
        mark_fired(fire_key)
        return

    log(AGENT, f"Missing at {hour}h: {missing}")

    nudge = generate_nudge(checkpoint, missing, streaks, log_data)
    log(AGENT, f"Nudge: {nudge}")

    score = log_data.get("score", 0)
    missing_str = " · ".join(f"<code>{m}</code>" for m in missing)

    message = f"""🧠 <b>IronMind — {checkpoint['label']}</b>

{nudge}

Missing: {missing_str}
Day score: <b>{score}/10</b>

Log at localhost:8888 → IronMind"""

    telegram_send(message)
    mark_fired(fire_key)
    log(AGENT, f"Accountability nudge sent for {hour}h checkpoint.")


if __name__ == "__main__":
    run()
