#!/usr/bin/env python3
"""
IronMind Ironman Daily Mission Agent — 5:00 AM daily.

Automatically generates and saves:
  1. Today's IronMind Plan (priorities, training, mental theme)
  2. Today's Ironman Training Protocol (swim/bike/run mission)
  3. Sends the full Daily Mission to Telegram

Uses yesterday's logged data + day-of-week phase structure to adapt.
"""

import json
import requests as req
from datetime import datetime, timedelta
from agents.base import *

AGENT = "ironman_daily"

# ── Phase + weekly structure ───────────────────────────────────────────────────
# Race: Ironman Florida, ~November 2026
# Phase 1: March–June 2026   (months 7-5)  Base Endurance & Technique
# Phase 2: July–August 2026  (months 4-3)  Volume & Race-Specific Intensity
# Phase 3: Sept–Nov 2026     (months 2-1)  Peak & Taper

RACE_DATE = datetime(2026, 11, 7)  # Ironman Florida approximate date

# Weekly focus by day (0=Mon, 1=Tue, ..., 6=Sun)
PHASE1_WEEKLY = {
    0: ("Recovery + Mobility",        "rest",        "Recover and restore. Mobility work only."),
    1: ("Swim Technique + Light Run",  "swim_run",    "Swim drill work + easy aerobic run."),
    2: ("Bike Endurance + Strength",   "bike_str",    "Long Zone 2 bike. Core and glute strength."),
    3: ("Run Endurance + Mobility",    "run",         "Easy run build. Hip and hamstring mobility."),
    4: ("Swim + Optional Brick",       "swim_brick",  "Swim technique. Optional short bike→run brick."),
    5: ("Long Bike",                   "long_bike",   "This is your long ride. Build the engine."),
    6: ("Long Run",                    "long_run",    "Long slow run. Aerobic base. Don't race it."),
}

PHASE2_WEEKLY = {
    0: ("Active Recovery + Mobility",  "rest",        "Recover. Short walk or yoga only."),
    1: ("Swim Intervals + Run Tempo",  "swim_run",    "Swim intervals. Tempo run effort."),
    2: ("Long Bike + Strength",        "bike_str",    "Long bike with moderate intensity. Upper body."),
    3: ("Tempo Run + Swim Technique",  "run",         "Tempo run. Easy technique swim."),
    4: ("Brick: Bike → Run",           "brick",       "60 min bike into 20 min run. Practice transitions."),
    5: ("Long Bike (progressive)",     "long_bike",   "Distance increases weekly. Stay disciplined."),
    6: ("Long Run (progressive)",      "long_run",    "Push the long run. Practice nutrition."),
}

PHASE3_WEEKLY = {
    0: ("Recovery + Mobility",         "rest",        "Full recovery. Protect the legs."),
    1: ("Swim Race Pace + Run Intervals","swim_run",  "Race-pace swim. Short sharp run intervals."),
    2: ("Long Bike (90-100 mi peak)",   "long_bike",   "Longest rides of the cycle. Trust the training."),
    3: ("Recovery Run or Brick",        "run",         "Easy run or short brick. Listen to the body."),
    4: ("Swim + Brick",                 "swim_brick",  "Race-pace swim. Brick session."),
    5: ("Long Bike + Run (Brick)",      "brick",       "Long brick. Simulate race transitions."),
    6: ("Long Run (16-20 miles peak)",  "long_run",    "Peak long run. Nutrition and pacing practice."),
}

MENTAL_THEMES = {
    "rest":       "Recovery is training. Protect it.",
    "swim_run":   "Water first. Technique before speed.",
    "bike_str":   "Build the engine. Strength endures.",
    "run":        "Foot strike to finish line. Consistency.",
    "swim_brick": "Two disciplines. One mindset.",
    "brick":      "The brick makes you stronger. Embrace the grind.",
    "long_bike":  "Miles in the saddle. Trust the process.",
    "long_run":   "Slow is smooth. Smooth is fast. Endure.",
}


def get_phase_and_focus() -> tuple:
    """Returns (phase_num, phase_name, day_focus, day_key, day_note)."""
    now = datetime.now()
    months_to_race = max(0, (RACE_DATE.year - now.year) * 12 + (RACE_DATE.month - now.month))
    dow = now.weekday()  # 0=Mon

    if months_to_race >= 5:
        phase_num = 1
        phase_name = "Phase 1 – Base Endurance & Technique"
        weekly = PHASE1_WEEKLY
    elif months_to_race >= 3:
        phase_num = 2
        phase_name = "Phase 2 – Volume & Race-Specific Intensity"
        weekly = PHASE2_WEEKLY
    else:
        phase_num = 3
        phase_name = "Phase 3 – Peak & Taper"
        weekly = PHASE3_WEEKLY

    focus, key, note = weekly[dow]
    return phase_num, phase_name, focus, key, note, months_to_race


def get_yesterday_data() -> dict:
    """Fetch yesterday's training log if available."""
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        r = req.get(f"{HUB_BASE}/ironmind/training?date={yesterday}", timeout=10)
        d = r.json()
        return d.get("data", {}) or {}
    except Exception:
        return {}


def generate_plan_and_mission(phase_name: str, focus: str, key: str, note: str,
                               months_left: int, yesterday: dict) -> dict:
    """Call Claude to generate today's IronMind plan + training mission."""
    dow_name = datetime.now().strftime("%A")
    date_str = datetime.now().strftime("%B %d, %Y")

    yesterday_summary = ""
    if yesterday:
        yesterday_summary = (
            f"\nYesterday's data: run={yesterday.get('run_distance','?')}mi, "
            f"bike={yesterday.get('cycle_distance','?')}mi, "
            f"swim={yesterday.get('swim_distance','?')}m, "
            f"fatigue={yesterday.get('fatigue_level','?')}/10, "
            f"sleep={yesterday.get('sleep_hours','?')}h, "
            f"effort={yesterday.get('effort_level','?')}/10"
        )

    prompt = f"""You are Jordan's Ironman performance coach generating today's daily mission.

Date: {dow_name}, {date_str}
Months to Ironman Florida: {months_left}
Phase: {phase_name}
Today's Focus: {focus}
Focus note: {note}
{yesterday_summary}

Return STRICT JSON only — no prose, no markdown fences:
{{
  "plan": {{
    "priority_1": "<primary mission today — 1 short sentence>",
    "priority_2": "<secondary focus — 1 short sentence>",
    "priority_3": "<recovery or nutrition focus>",
    "training": "<specific workout summary, e.g. '30 min Z2 run + core 15 min'>",
    "mental_theme": "<3-6 word theme, e.g. 'Consistency Over Intensity'>"
  }},
  "training": {{
    "swim": {{"distance": "<e.g. 1200m or Rest>", "time": "<e.g. 30 min>", "effort": "<zone or technique note>"}},
    "bike": {{"distance": "<e.g. 20 mi or Rest>", "time": "<e.g. 60 min>", "effort": "<zone>"}},
    "run":  {{"distance": "<e.g. 4 miles or Rest>","time": "<e.g. 38 min>","effort": "<zone>"}},
    "strength_mobility": "<e.g. Core 20 min + hip mobility>"
  }},
  "nutrition": {{
    "calories": "<target range>",
    "protein_g": "<target>",
    "hydration_oz": "<target>",
    "fuel_timing": "<brief practical note>"
  }},
  "recovery": {{
    "sleep_target": "<e.g. 8 hrs>",
    "actions": ["<action 1>", "<action 2>"]
  }},
  "mission_statement": "<1 punchy motivating sentence for today>",
  "mission_adjustments": "<what to do if fatigued or behind — 1 sentence>"
}}"""

    raw = claude(prompt, max_tokens=800, model="claude-sonnet-4-6")
    if "{" in raw:
        raw = raw[raw.index("{"):raw.rindex("}")+1]
    return json.loads(raw)


def save_plan(plan_fields: dict):
    """POST today's plan to the hub."""
    req.post(
        f"{HUB_BASE}/ironmind/plan",
        json=plan_fields,
        headers={"Content-Type": "application/json"},
        timeout=10,
    )


def save_training_protocol(training: dict, nutrition: dict, recovery: dict,
                            mission_statement: str, phase_name: str, focus: str,
                            mission_adjustments: str):
    """Save today's pre-generated protocol directly to the DB (no redundant AI call)."""
    protocol = {
        "readiness_score": 72,  # default — no Apple Health data yet
        "phase": phase_name,
        "week_day_focus": focus,
        "mission_statement": mission_statement,
        "training_mission": training,
        "nutrition_mission": nutrition,
        "recovery_mission": recovery,
        "focus_metrics": [
            f"Complete: {training.get('run',{}).get('distance','--')} run",
            f"Complete: {training.get('bike',{}).get('distance','--')} bike",
            "Log tonight's data before bed",
        ],
        "race_readiness": {
            "weekly_trend": "Building base — Phase 1, week in progress",
            "confidence": "Building",
        },
        "mission_adjustments": mission_adjustments,
        "risk_flags": [],
    }

    import sys as _sys
    _sys.path.insert(0, str(ROOT_DIR))
    from database import ironman_save
    ironman_save(today_str(), protocol=json.dumps(protocol),
                 notes="Auto-generated by IronMind Daily Agent")
    log(AGENT, "Protocol saved to DB")


def build_telegram_message(result: dict, phase_name: str, focus: str,
                            months_left: int) -> str:
    plan = result.get("plan", {})
    training = result.get("training", {})
    nutrition = result.get("nutrition", {})
    recovery = result.get("recovery", {})
    adj = result.get("mission_adjustments", "")

    def sport_line(emoji, label, obj):
        if not obj or obj.get("distance") in ("Rest", "--", None):
            return f"{emoji} {label}: Rest"
        return f"{emoji} {label}: {obj.get('distance','')} · {obj.get('time','')} · {obj.get('effort','')}"

    dow_name = datetime.now().strftime("%A")
    date_str = datetime.now().strftime("%B %d")
    days_to_race = (RACE_DATE - datetime.now()).days

    lines = [
        f"🏁 <b>IronMind Daily Mission — {dow_name}, {date_str}</b>",
        f"<i>{phase_name} · {days_to_race} days to Ironman Florida</i>",
        "",
        f"⚡ <b>{result.get('mission_statement','')}</b>",
        "",
        f"📋 <b>Today's Focus: {focus}</b>",
        f"1️⃣ {plan.get('priority_1','')}",
        f"2️⃣ {plan.get('priority_2','')}",
        f"3️⃣ {plan.get('priority_3','')}",
        f"🧘 Theme: {plan.get('mental_theme','')}",
        "",
        "🎯 <b>Training Mission:</b>",
        sport_line("🏊", "Swim", training.get("swim")),
        sport_line("🚴", "Bike", training.get("bike")),
        sport_line("🏃", "Run",  training.get("run")),
        f"💪 {training.get('strength_mobility','')}",
        "",
        "🥗 <b>Nutrition:</b>",
        f"  🔥 {nutrition.get('calories','')}  🥩 {nutrition.get('protein_g','')}  💧 {nutrition.get('hydration_oz','')}",
        f"  ⏰ {nutrition.get('fuel_timing','')}",
        "",
        f"😴 <b>Recovery:</b> {recovery.get('sleep_target','')} sleep",
    ]

    for action in (recovery.get("actions") or []):
        lines.append(f"  • {action}")

    if adj:
        lines.append(f"\n⚡ <b>If fatigued:</b> {adj}")

    lines.append(f"\n<i>Log your data tonight → IronMind → Training Protocol</i>")

    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────
def run():
    fire_key = f"ironman_daily_{today_str()}"
    if was_fired_recently(fire_key, hours=20):
        log(AGENT, "Already ran today, skipping.")
        return

    log(AGENT, "=== IronMind Daily Mission Agent starting ===")

    phase_num, phase_name, focus, key, note, months_left = get_phase_and_focus()
    log(AGENT, f"Phase: {phase_num} | Focus: {focus} | Months left: {months_left}")

    yesterday = get_yesterday_data()
    log(AGENT, f"Yesterday data: {bool(yesterday)}")

    try:
        result = generate_plan_and_mission(phase_name, focus, key, note, months_left, yesterday)
        log(AGENT, "Plan + mission generated OK")
    except Exception as e:
        log(AGENT, f"Generation error: {e}")
        telegram_send(f"⚠️ IronMind Daily Agent error: {e}")
        return

    # Save plan to IronMind panel
    try:
        save_plan(result.get("plan", {}))
        log(AGENT, "Plan saved")
    except Exception as e:
        log(AGENT, f"Plan save error: {e}")

    # Save training protocol
    try:
        save_training_protocol(
            result.get("training", {}),
            result.get("nutrition", {}),
            result.get("recovery", {}),
            result.get("mission_statement", ""),
            phase_name, focus,
            result.get("mission_adjustments", ""),
        )
        log(AGENT, "Training protocol saved")
    except Exception as e:
        log(AGENT, f"Training protocol save error: {e}")

    # Send Telegram
    msg = build_telegram_message(result, phase_name, focus, months_left)
    telegram_send(msg)
    log(AGENT, "Telegram sent")

    mark_fired(fire_key)
    log(AGENT, "=== IronMind Daily Mission Agent complete ===")


if __name__ == "__main__":
    run()
