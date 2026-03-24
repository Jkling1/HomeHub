#!/usr/bin/env python3
"""
IronMind — Personal Performance System integrated into Jordan's Command Center.

Tracks the 4 things that actually move the needle:
  1. Daily Plan    — mission briefing, not a to-do list
  2. Daily Log     — 10-metric truth mirror
  3. Streaks       — consistency engine with recovery window
  4. Weekly Review — where amateurs become dangerous

Plus: AI Coach, Journaling, Identity Builder.

Usage:
  python3 ironmind.py plan                     # Show today's plan
  python3 ironmind.py log workout=1 mood=8     # Log metrics
  python3 ironmind.py streaks                  # Show streaks
  python3 ironmind.py coach                    # Get AI coaching
  python3 ironmind.py review                   # Weekly review
  python3 ironmind.py journal                  # Today's journal
  python3 ironmind.py identity                 # Show identity statements
"""

import os
import sys
import json
import requests as req
from pathlib import Path
from datetime import datetime, timedelta, date

ENV_PATH = Path(__file__).parent / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
TELEGRAM_TOKEN    = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID  = os.environ.get("TELEGRAM_CHAT_ID", "")
SCRIPT_DIR        = Path(__file__).parent

TODAY = date.today().strftime("%Y-%m-%d")


# ── Telegram ──────────────────────────────────────────────────────────────────

def send_telegram(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        req.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception:
        pass


# ── Daily Plan ────────────────────────────────────────────────────────────────

def get_plan(date_str: str = TODAY) -> str:
    from database import im_get_plan
    plan = im_get_plan(date_str)

    dow  = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A")
    dstr = datetime.strptime(date_str, "%Y-%m-%d").strftime("%B %-d")

    if not plan:
        return (
            f"📋 <b>No plan set for {dow}, {dstr}.</b>\n\n"
            f"Set it with something like:\n"
            f'  "Today my priorities are: ship the IronMind log, hit the gym, prep meals"\n'
            f'  "Training today: 5-mile run. Theme: Discipline."\n'
        )

    lines = [f"📋 <b>Mission Briefing — {dow}, {dstr}</b>", ""]

    if plan.get("mental_theme"):
        lines.append(f"🎯 Theme: <b>{plan['mental_theme'].upper()}</b>")
        lines.append("")

    lines.append("⚡ <b>Top 3 Priorities</b>")
    for i, key in enumerate(["priority_1", "priority_2", "priority_3"], 1):
        val = plan.get(key)
        if val:
            lines.append(f"  {i}. {val}")

    if plan.get("training"):
        lines.append("")
        lines.append(f"🏋️ <b>Training:</b> {plan['training']}")

    if plan.get("nutrition_target"):
        lines.append(f"🥗 <b>Nutrition:</b> {plan['nutrition_target']}")

    lines.append("")
    lines.append("<i>If it's not on this plan, it's noise.</i>")

    return "\n".join(lines)


def set_plan(fields: dict, date_str: str = TODAY) -> str:
    from database import im_save_plan
    im_save_plan(date_str, **{k: v for k, v in fields.items() if v})
    return f"✅ Plan set for {datetime.strptime(date_str, '%Y-%m-%d').strftime('%A, %B %-d')}."


# ── Daily Log ─────────────────────────────────────────────────────────────────

METRIC_ALIASES = {
    "workout":   "workout_done",
    "worked_out": "workout_done",
    "trained":   "workout_done",
    "steps":     "steps",
    "calories":  "calories",
    "cals":      "calories",
    "protein":   "protein_g",
    "water":     "hydration_oz",
    "hydration": "hydration_oz",
    "oz":        "hydration_oz",
    "sleep":     "sleep_hours",
    "slept":     "sleep_hours",
    "sleep_quality": "sleep_quality",
    "mood":      "mood",
    "weight":    "weight_lbs",
    "lbs":       "weight_lbs",
    "fast_food": "fast_food",
    "junk":      "fast_food",
    "alcohol":   "alcohol",
    "drank":     "alcohol",
    "notes":     "notes",
}

LOG_LABELS = {
    "workout_done":  ("🏋️", "Workout"),
    "steps":         ("👟", "Steps"),
    "calories":      ("🔥", "Calories"),
    "protein_g":     ("🥩", "Protein"),
    "hydration_oz":  ("💧", "Hydration"),
    "sleep_hours":   ("😴", "Sleep"),
    "sleep_quality": ("⭐", "Sleep Quality"),
    "mood":          ("🎭", "Mood"),
    "weight_lbs":    ("⚖️", "Weight"),
    "fast_food":     ("🍔", "Fast Food"),
    "alcohol":       ("🍺", "Alcohol"),
}


def log_metrics(raw: dict, date_str: str = TODAY) -> str:
    from database import im_upsert_log, im_update_streak

    fields = {}
    for alias, val in raw.items():
        key = METRIC_ALIASES.get(alias.lower(), alias)
        if key in LOG_LABELS or key == "notes":
            fields[key] = val

    if not fields:
        return "❌ No recognized metrics. Try: workout=1 mood=8 sleep=7 protein=180"

    # Coerce types
    bool_fields = {"workout_done", "fast_food", "alcohol"}
    int_fields  = {"steps", "calories", "protein_g", "hydration_oz",
                   "sleep_quality", "mood"}
    float_fields = {"sleep_hours", "weight_lbs"}

    typed = {}
    for k, v in fields.items():
        try:
            if k in bool_fields:
                typed[k] = 1 if str(v).lower() in ("1","yes","true","done","y") else 0
            elif k in int_fields:
                typed[k] = int(v)
            elif k in float_fields:
                typed[k] = float(v)
            else:
                typed[k] = v
        except Exception:
            typed[k] = v

    im_upsert_log(date_str, **typed)

    # Update streaks
    if "workout_done" in typed:
        im_update_streak("workout", typed["workout_done"] == 1, date_str)
    if "fast_food" in typed:
        im_update_streak("clean_eating", typed["fast_food"] == 0, date_str)
    if "alcohol" in typed:
        im_update_streak("no_alcohol", typed["alcohol"] == 0, date_str)
    if "hydration_oz" in typed:
        im_update_streak("hydration", typed["hydration_oz"] >= 64, date_str)

    logged = []
    for k, v in typed.items():
        if k in LOG_LABELS:
            emoji, label = LOG_LABELS[k]
            if k in bool_fields:
                logged.append(f"{emoji} {label}: {'✓' if v else '✗'}")
            elif k == "sleep_quality" or k == "mood":
                logged.append(f"{emoji} {label}: {v}/10")
            elif k == "weight_lbs":
                logged.append(f"{emoji} {label}: {v} lbs")
            elif k == "sleep_hours":
                logged.append(f"{emoji} {label}: {v}h")
            elif k == "protein_g":
                logged.append(f"{emoji} {label}: {v}g")
            elif k == "hydration_oz":
                logged.append(f"{emoji} {label}: {v}oz")
            else:
                logged.append(f"{emoji} {label}: {v}")

    return "📊 Logged:\n" + "\n".join(logged)


def get_log(date_str: str = TODAY) -> str:
    from database import im_get_log
    log = im_get_log(date_str)
    dow = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A, %B %-d")

    if not log:
        return f"📊 No log for {dow} yet.\nStart with: 'log workout done, mood 8, sleep 7 hours'"

    lines = [f"📊 <b>Daily Log — {dow}</b>", ""]

    for key, (emoji, label) in LOG_LABELS.items():
        val = log.get(key)
        if val is None:
            continue
        if key in ("workout_done", "fast_food", "alcohol"):
            display = "✓" if val else "✗"
        elif key in ("sleep_quality", "mood"):
            display = f"{val}/10"
        elif key == "weight_lbs":
            display = f"{val} lbs"
        elif key == "sleep_hours":
            display = f"{val}h"
        elif key == "protein_g":
            display = f"{val}g"
        elif key == "hydration_oz":
            display = f"{val}oz"
        else:
            display = str(val)
        lines.append(f"  {emoji} {label:<16} {display}")

    score = _compute_score(log)
    lines.append(f"\n  📈 Day score: <b>{score}/10</b>")

    if log.get("notes"):
        lines.append(f"\n  📝 {log['notes']}")

    return "\n".join(lines)


def _compute_score(log: dict) -> int:
    """Simple 10-point daily score from key metrics."""
    points = 0
    if log.get("workout_done"):          points += 2
    if not log.get("fast_food"):         points += 1
    if not log.get("alcohol"):           points += 1
    sleep = log.get("sleep_hours", 0)
    if sleep >= 7:                       points += 1.5
    elif sleep >= 6:                     points += 0.75
    hydration = log.get("hydration_oz", 0)
    if hydration >= 80:                  points += 1.5
    elif hydration >= 64:                points += 0.75
    protein = log.get("protein_g", 0)
    if protein >= 150:                   points += 1
    mood = log.get("mood", 5)
    points += (mood / 10)
    return min(10, round(points))


# ── Streaks ───────────────────────────────────────────────────────────────────

def get_streaks() -> str:
    from database import im_get_streaks
    streaks = im_get_streaks()

    lines = ["🔥 <b>IronMind Streaks</b>", ""]
    for s in streaks:
        current = s["current"]
        longest = s["longest"]
        name    = s["name"].replace("_", " ").title()

        if current >= 7:
            emoji = "🔥"
        elif current >= 3:
            emoji = "⚡"
        elif current > 0:
            emoji = "✅"
        else:
            emoji = "💀"

        fire = "🔥" * min(current, 5) if current > 0 else ""
        lines.append(f"  {emoji} <b>{name}</b>  {current}d streak  (best: {longest}d) {fire}")

    total = sum(s["current"] for s in streaks)
    lines.append(f"\n  Combined streak score: <b>{total}</b>")
    return "\n".join(lines)


# ── AI Coach ──────────────────────────────────────────────────────────────────

def get_coaching() -> str:
    from database import im_get_logs, im_get_streaks, im_get_plan

    logs    = im_get_logs(7)
    streaks = im_get_streaks()
    plan    = im_get_plan(TODAY)

    if not logs and not plan:
        return (
            "🧠 <b>IronMind Coach</b>\n\n"
            "Not enough data to coach yet. Start by:\n"
            "1. Setting today's plan\n"
            "2. Logging your first day\n\n"
            "Your coach gets sharper as you feed it data."
        )

    # Build context for Claude
    streak_summary = ", ".join(
        f"{s['name'].replace('_',' ')}: {s['current']}d" for s in streaks
    )
    log_summary = []
    for log in logs[:5]:
        score = _compute_score(log)
        log_summary.append(
            f"  {log['date']}: score={score}/10, workout={'yes' if log.get('workout_done') else 'no'}, "
            f"mood={log.get('mood','?')}/10, sleep={log.get('sleep_hours','?')}h, "
            f"fast_food={'yes' if log.get('fast_food') else 'no'}"
        )

    context = f"""Jordan's IronMind data:

Streaks: {streak_summary}

Recent logs (last {len(log_summary)} days):
{chr(10).join(log_summary)}

Today's plan: {json.dumps(plan) if plan else 'not set'}"""

    try:
        resp = req.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key":           ANTHROPIC_API_KEY,
                "anthropic-version":   "2023-06-01",
                "content-type":        "application/json",
            },
            json={
                "model":      "claude-haiku-4-5-20251001",
                "max_tokens": 400,
                "system": (
                    "You are IronMind Coach — Jordan's brutally honest personal performance coach. "
                    "You don't do motivational fluff. You deliver direct, specific, actionable feedback "
                    "based on Jordan's actual data. Be like a great coach: direct, real, invested. "
                    "3-5 sentences max. Call out exactly where Jordan is slipping and what to fix. "
                    "End with ONE clear directive for today."
                ),
                "messages": [{"role": "user", "content": context}],
            },
            timeout=20,
        )
        resp.raise_for_status()
        coaching = resp.json()["content"][0]["text"].strip()
        return f"🧠 <b>Coach</b>\n\n{coaching}"
    except Exception as e:
        return f"🧠 Coach unavailable: {e}"


# ── Journal ───────────────────────────────────────────────────────────────────

def save_journal(went_right: str, cut_corners: str, tomorrow_std: str,
                 date_str: str = TODAY) -> str:
    from database import im_save_journal
    im_save_journal(date_str, went_right, cut_corners, tomorrow_std)
    return (
        "📓 Journal saved.\n\n"
        f"✅ What went right: {went_right}\n"
        f"⚠️  Cut corners: {cut_corners}\n"
        f"🎯 Tomorrow's standard: {tomorrow_std}"
    )


def get_journal(date_str: str = TODAY) -> str:
    from database import im_get_journal
    j = im_get_journal(date_str)
    dow = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A, %B %-d")

    if not j:
        return (
            f"📓 No journal for {dow}.\n\n"
            "Reflect with:\n"
            "\"Journal: what went right: hit the gym. cut corners: skipped meal prep. "
            "standard tomorrow: prep food Sunday night\""
        )

    lines = [f"📓 <b>Journal — {dow}</b>", ""]
    if j.get("went_right"):
        lines.append(f"✅ <b>What went right:</b>\n  {j['went_right']}")
    if j.get("cut_corners"):
        lines.append(f"\n⚠️ <b>Cut corners on:</b>\n  {j['cut_corners']}")
    if j.get("tomorrow_std"):
        lines.append(f"\n🎯 <b>Tomorrow's standard:</b>\n  {j['tomorrow_std']}")
    return "\n".join(lines)


# ── Identity ──────────────────────────────────────────────────────────────────

def get_identity() -> str:
    from database import im_get_identity
    statements = im_get_identity()

    if not statements:
        return "No identity statements yet. Add one: \"I am the type of person who...\""

    lines = ["🧱 <b>Who You Are</b>", ""]
    for s in statements:
        lines.append(f"  #{s['id']}  {s['statement']}")
    lines.append("")
    lines.append("<i>You're not tracking actions — you're building a person.</i>")
    return "\n".join(lines)


def add_identity(statement: str) -> str:
    from database import im_add_identity
    # Normalize — ensure it starts with "I am..."
    if not statement.lower().startswith("i am"):
        statement = "I am the type of person who " + statement.lstrip("who ").strip(".")
    im_add_identity(statement)
    return f"🧱 Identity statement added:\n\"{statement}\""


# ── Weekly Review ─────────────────────────────────────────────────────────────

def weekly_review() -> str:
    from database import im_get_logs, im_get_streaks
    logs    = im_get_logs(7)
    streaks = im_get_streaks()

    if not logs:
        return "📊 No data for the week yet. Start logging daily to unlock your weekly review."

    # Compute week stats
    workout_days  = sum(1 for l in logs if l.get("workout_done"))
    clean_days    = sum(1 for l in logs if not l.get("fast_food"))
    sober_days    = sum(1 for l in logs if not l.get("alcohol"))
    avg_sleep     = _avg([l["sleep_hours"] for l in logs if l.get("sleep_hours")])
    avg_mood      = _avg([l["mood"] for l in logs if l.get("mood")])
    avg_protein   = _avg([l["protein_g"] for l in logs if l.get("protein_g")])
    scores        = [_compute_score(l) for l in logs]
    avg_score     = _avg(scores)
    best_day_log  = max(logs, key=_compute_score) if logs else None
    worst_day_log = min(logs, key=_compute_score) if logs else None

    def _dow(date_str):
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").strftime("%A")
        except Exception:
            return date_str

    lines = [
        "📊 <b>Weekly Review</b>",
        f"<i>{_dow(logs[-1]['date'])} – {_dow(logs[0]['date'])}</i>",
        "",
        f"🏋️ Workouts:    {workout_days}/{len(logs)} days",
        f"🍔 Clean eating: {clean_days}/{len(logs)} days",
        f"🍺 Sober days:  {sober_days}/{len(logs)} days",
    ]

    if avg_sleep:
        lines.append(f"😴 Avg sleep:   {avg_sleep:.1f}h")
    if avg_mood:
        lines.append(f"🎭 Avg mood:    {avg_mood:.1f}/10")
    if avg_protein:
        lines.append(f"🥩 Avg protein: {avg_protein:.0f}g")

    lines.append(f"\n📈 Avg day score: <b>{avg_score:.1f}/10</b>")

    if best_day_log:
        lines.append(f"🔝 Best day:  {_dow(best_day_log['date'])} ({_compute_score(best_day_log)}/10)")
    if worst_day_log and worst_day_log != best_day_log:
        lines.append(f"📉 Worst day: {_dow(worst_day_log['date'])} ({_compute_score(worst_day_log)}/10)")

    # Streaks
    lines.append("\n🔥 <b>Streaks</b>")
    for s in streaks:
        name = s["name"].replace("_", " ").title()
        lines.append(f"  {name}: {s['current']}d (best {s['longest']}d)")

    # Verdict
    lines.append("\n<b>The Standard</b>")
    if avg_score >= 8:
        lines.append("Elite week. This is who you're becoming. Keep it.")
    elif avg_score >= 6:
        lines.append("Solid week. You left points on the table — you know where.")
    elif avg_score >= 4:
        lines.append("Below standard. Identify the one thing dragging every day and fix it.")
    else:
        lines.append("Reset week. Pick ONE metric, own it completely for 7 days. Start tomorrow.")

    return "\n".join(lines)


def _avg(values: list) -> float:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else 0


# ── Unified handler (called from hub.py) ─────────────────────────────────────

def handle(cmd: dict) -> str:
    """Main entry point from hub.py."""
    command = cmd.get("command", "status")

    if command == "plan":
        return get_plan()

    elif command == "set_plan":
        fields = {k: v for k, v in cmd.items()
                  if k in ("priority_1","priority_2","priority_3",
                            "training","nutrition_target","mental_theme")}
        return set_plan(fields) + "\n\n" + get_plan()

    elif command == "log":
        metrics = cmd.get("metrics", {})
        if not metrics:
            metrics = {k: v for k, v in cmd.items()
                       if k not in ("action","command","date")}
        return log_metrics(metrics)

    elif command == "get_log":
        return get_log()

    elif command == "streaks":
        return get_streaks()

    elif command == "coach":
        return get_coaching()

    elif command == "journal":
        # If data provided, save it
        went    = cmd.get("went_right", "")
        corners = cmd.get("cut_corners", "")
        tmrw    = cmd.get("tomorrow_std", "")
        if went or corners or tmrw:
            return save_journal(went, corners, tmrw)
        return get_journal()

    elif command == "identity":
        stmt = cmd.get("statement", "")
        if stmt:
            return add_identity(stmt)
        return get_identity()

    elif command == "review":
        return weekly_review()

    elif command == "status":
        # Quick dashboard: plan + log + streaks
        parts = []
        plan_txt = get_plan()
        parts.append(plan_txt)
        parts.append("")
        parts.append(get_streaks())
        return "\n".join(parts)

    return f"Unknown IronMind command: {command}"


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    rest = sys.argv[2:]

    if cmd == "plan":
        print(get_plan())
    elif cmd == "log":
        # parse key=value pairs
        metrics = {}
        for arg in rest:
            if "=" in arg:
                k, v = arg.split("=", 1)
                metrics[k.strip()] = v.strip()
        print(log_metrics(metrics) if metrics else "Usage: log key=value ...")
    elif cmd == "streaks":
        print(get_streaks())
    elif cmd == "coach":
        print(get_coaching())
    elif cmd == "journal":
        print(get_journal())
    elif cmd == "identity":
        print(get_identity())
    elif cmd == "review":
        print(weekly_review())
    elif cmd == "score":
        from database import im_get_log
        log = im_get_log(TODAY)
        if log:
            print(f"Today's score: {_compute_score(log)}/10")
        else:
            print("No log today yet.")
    else:
        print(__doc__)
