#!/usr/bin/env python3
"""
EVOLVE Protocol — 5:00 AM daily evolution + preparation cycle.

5 AM Phase 1 — PREPARE:
  Pull yesterday's completion/health data, generate adapted plan for today,
  store pre-built recommendations in daily_prep table for morning agent.

5 AM Phase 2 — EVOLVE (E.V.O.L.V.E.):
  E = Evaluate   → yesterday's behavior
  V = Verify     → system health check
  O = Optimize   → update memory with insights
  L = Learn      → compare plan vs reality
  V = Visualize  → build evolution report
  E = Expand     → propose 1 micro-feature

Runtime: ~60–120 seconds. Sends full report to Telegram.
"""

import json
import time
import requests as req
from datetime import datetime, timedelta
from agents.base import *
from agents import adler_memory

AGENT = "evolve"
EVOLVE_KEY = f"evolve_{today_str()}"


def confidence(evidence_count: int, consistency_days: int, impact: str = "low") -> int:
    base = min(evidence_count * 12, 60) + min(consistency_days * 8, 30)
    return max(0, min(100, base + {"low": 0, "medium": -5, "high": -15}.get(impact, 0)))


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 1: PREPARE
# ══════════════════════════════════════════════════════════════════════════════

def preparation_phase() -> dict:
    log(AGENT, "PREP — 5 AM preparation phase starting")
    from database import daily_prep_save, im_get_log, rocks_get

    yesterday  = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    today_date = today_str()

    yday_log = {}
    try:
        yday_log = im_get_log(yesterday) or {}
    except Exception as e:
        log(AGENT, f"PREP — yesterday log error: {e}")

    completion_rate = 0.0
    try:
        yday_rocks = rocks_get(yesterday)
        if yday_rocks:
            done = sum(1 for r in yday_rocks if r.get("status") == "complete")
            completion_rate = round(done / len(yday_rocks), 2)
            log(AGENT, f"PREP — rocks {done}/{len(yday_rocks)} = {int(completion_rate*100)}%")
    except Exception as e:
        log(AGENT, f"PREP — rocks error: {e}")

    sleep = yday_log.get("sleep_hours") or 0
    hrv   = yday_log.get("hrv") or 0
    fatigue_score = 0
    if sleep > 0 and sleep < 6:
        fatigue_score += 30
    elif sleep > 0 and sleep < 7:
        fatigue_score += 15
    if hrv and hrv < 40:
        fatigue_score += 20
    if yday_log.get("workout_done") == 0:
        fatigue_score += 10

    prompt = f"""You are Jordan's performance AI preparing his 7 AM briefing data at 5 AM.

Yesterday:
- Sleep: {sleep or 'no data'} hours  |  HRV: {hrv or 'no data'}
- Workout done: {bool(yday_log.get('workout_done'))}
- Rock completion: {int(completion_rate * 100)}%
- Fatigue score: {fatigue_score}/60

Today's scheduled: 6 mile run

Return JSON only:
{{
  "adapted_training": "Adjusted training recommendation (1 sentence)",
  "adapted_nutrition": "Breakfast, lunch, hydration (2 sentences)",
  "coaching_note": "One sharp tactical note based on yesterday (1 sentence)"
}}"""

    prep = {}
    try:
        raw = claude(prompt, max_tokens=250)
        if "{" in raw:
            raw = raw[raw.index("{"):raw.rindex("}")+1]
        prep = json.loads(raw)
    except Exception as e:
        log(AGENT, f"PREP — Claude error: {e}")
        prep = {
            "adapted_training": "Stay on schedule — 6 mile run at moderate pace.",
            "adapted_nutrition": "High protein breakfast. Clean lunch. 100oz water.",
            "coaching_note": "Yesterday is done. Today's execution is all that matters.",
        }

    try:
        daily_prep_save(
            today_date,
            adapted_training=prep.get("adapted_training", ""),
            adapted_nutrition=prep.get("adapted_nutrition", ""),
            fatigue_score=fatigue_score,
            completion_yesterday=completion_rate,
            notes=prep.get("coaching_note", ""),
        )
        log(AGENT, f"PREP — Stored. fatigue={fatigue_score}, completion={completion_rate}")
    except Exception as e:
        log(AGENT, f"PREP — DB save error: {e}")

    return {
        "fatigue_score": fatigue_score,
        "completion_yesterday": completion_rate,
        "adapted_training": prep.get("adapted_training", ""),
        "coaching_note": prep.get("coaching_note", ""),
    }


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2: EVOLVE
# ══════════════════════════════════════════════════════════════════════════════

def evaluate_yesterday() -> dict:
    log(AGENT, "E — Evaluating yesterday")
    try:
        rows = req.get(f"{HUB_BASE}/history", timeout=10).json()
    except Exception as e:
        log(AGENT, f"History unavailable: {e}")
        return {}

    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_rows = [r for r in rows if (r.get("ts") or "").startswith(yesterday)] or rows[:30]

    action_counts, light_colors, music_queries, peak_hours = {}, [], [], {}
    for r in yesterday_rows:
        action = r.get("action", "unknown")
        action_counts[action] = action_counts.get(action, 0) + 1
        ts = r.get("ts", "")
        if len(ts) > 13:
            try:
                h = int(ts[11:13])
                peak_hours[h] = peak_hours.get(h, 0) + 1
            except ValueError:
                pass
        intent = r.get("intent") or {}
        if action == "lights" and isinstance(intent, dict) and intent.get("color"):
            light_colors.append(intent["color"])
        if action == "music" and isinstance(intent, dict) and intent.get("query"):
            music_queries.append(intent["query"])

    return {
        "total_commands": len(yesterday_rows),
        "action_counts": action_counts,
        "top_action": max(action_counts, key=action_counts.get) if action_counts else None,
        "most_active_hour": max(peak_hours, key=peak_hours.get) if peak_hours else None,
        "favorite_light_color": max(set(light_colors), key=light_colors.count) if light_colors else None,
        "music_queries": music_queries[:5],
    }


def verify_health() -> dict:
    log(AGENT, "V — Verifying health")
    results = {}
    HUE_BRIDGE = os.environ.get("HUE_BRIDGE", "192.168.12.225")
    HUE_KEY    = os.environ.get("HUE_KEY", "")

    try:
        t0 = time.time()
        r = req.get(f"http://{HUE_BRIDGE}/api/{HUE_KEY}/lights", timeout=5)
        results["hue"] = {"ok": r.ok, "latency_ms": int((time.time()-t0)*1000), "lights": len(r.json()) if r.ok else 0}
    except Exception as e:
        results["hue"] = {"ok": False, "error": str(e)}

    try:
        t0 = time.time()
        r = req.get(f"{HUB_BASE}/status", timeout=5)
        results["hub"] = {"ok": r.ok, "latency_ms": int((time.time()-t0)*1000)}
    except Exception as e:
        results["hub"] = {"ok": False, "error": str(e)}

    try:
        t0 = time.time()
        r = req.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": "claude-haiku-4-5-20251001", "max_tokens": 5, "messages": [{"role": "user", "content": "ping"}]},
            timeout=10,
        )
        results["anthropic_api"] = {"ok": r.ok, "latency_ms": int((time.time()-t0)*1000)}
    except Exception as e:
        results["anthropic_api"] = {"ok": False, "error": str(e)}

    log_file = ROOT_DIR / "agent.log"
    error_count = 0
    if log_file.exists():
        lines = log_file.read_text().splitlines()[-200:]
        error_count = sum(1 for l in lines if "error" in l.lower())
    results["agent_errors_24h"] = error_count

    state = load_state()
    results["agents_active"] = list(set(k.split("_")[0] for k, ts in state.items() if time.time() - float(ts) < 86400))

    return results


def optimize_and_learn(evaluation: dict) -> list:
    log(AGENT, "O/L — Learning")
    proposals = []
    mem = adler_memory.load()

    fav_color = evaluation.get("favorite_light_color")
    if fav_color:
        history = mem.get("evolve_color_history", {})
        history[fav_color] = history.get(fav_color, 0) + 1
        mem["evolve_color_history"] = history
        adler_memory.save(mem)
        score = confidence(evaluation.get("total_commands", 1), history[fav_color], "low")
        proposals.append({
            "type": "preference_update",
            "description": f"Preferred light: {fav_color} ({history[fav_color]} days)",
            "action": {"category": "lights", "context": "default", "value": fav_color},
            "confidence": score,
            "auto_apply": score >= 70,
        })

    peak_hour = evaluation.get("most_active_hour")
    if peak_hour is not None:
        hour_history = mem.get("evolve_peak_hours", [])
        hour_history = (hour_history + [peak_hour])[-14:]
        mem["evolve_peak_hours"] = hour_history
        adler_memory.save(mem)
        score = confidence(len(hour_history), hour_history.count(peak_hour), "low")
        h12  = peak_hour if peak_hour <= 12 else peak_hour - 12
        ampm = "AM" if peak_hour < 12 else "PM"
        proposals.append({
            "type": "pattern_insight",
            "description": f"Most active at {h12}:00 {ampm} ({hour_history.count(peak_hour)}/{len(hour_history)} days)",
            "confidence": score,
            "auto_apply": score >= 80,
        })

    if evaluation.get("music_queries"):
        try:
            insight = claude(
                f"Jordan played: {', '.join(evaluation['music_queries'])}. One sharp behavioral insight, 15 words max.",
                max_tokens=40
            )
            proposals.append({"type": "behavioral_insight", "description": insight, "confidence": 65, "auto_apply": False})
        except Exception:
            pass

    return proposals


def expand_feature(evaluation: dict, health: dict) -> dict:
    log(AGENT, "E — Feature expansion")
    prompt = f"""EVOLVE Protocol for Jordan's Smart Hub.
Yesterday: {evaluation.get('total_commands', 0)} commands. Top: {evaluation.get('top_action', 'lights')}.
Hub: {health.get('hub',{}).get('latency_ms','?')}ms. Errors: {health.get('agent_errors_24h', 0)}.

Propose ONE small buildable micro-feature (<50 lines, non-breaking, directly useful).
JSON only:
{{"name":"5 words max","description":"1 sentence","implementation_hint":"1 sentence","confidence":75,"impact":"medium"}}"""

    try:
        raw = claude(prompt, max_tokens=150)
        if "{" in raw:
            raw = raw[raw.index("{"):raw.rindex("}")+1]
        return json.loads(raw)
    except Exception as e:
        log(AGENT, f"Feature error: {e}")
        return {"name": "Rock completion Telegram alert", "description": "Ping when all daily rocks complete.",
                "implementation_hint": "POST /rocks checks 100% completion, fires telegram_send.", "confidence": 75, "impact": "medium"}


def build_report(evaluation: dict, health: dict, proposals: list, feature: dict,
                 prep: dict, duration_s: float) -> str:
    auto_applied = [p for p in proposals if p.get("auto_apply")]
    pending      = [p for p in proposals if not p.get("auto_apply")]
    hue_ok = "✅" if health.get("hue", {}).get("ok") else "❌"
    hub_ok = "✅" if health.get("hub", {}).get("ok") else "❌"
    api_ok = "✅" if health.get("anthropic_api", {}).get("ok") else "❌"
    fatigue    = prep.get("fatigue_score", 0)
    completion = int(prep.get("completion_yesterday", 0) * 100)
    fat_label  = "🟢 Fresh" if fatigue < 20 else "🟡 Moderate" if fatigue < 40 else "🔴 High"
    feat_emoji = "🟢" if feature.get("confidence", 0) >= 70 else "🟡"

    lines = [
        "⚡ <b>EVOLVE — Daily Evolution Report</b>",
        f"<i>{datetime.now().strftime('%A, %B %d · %I:%M %p')}</i>",
        "",
        "━━━ PREPARE ━━━",
        f"Yesterday completion: <b>{completion}%</b>  ·  Fatigue: <b>{fat_label}</b>",
        f"Adapted training: {prep.get('adapted_training','—')}",
        f"💬 {prep.get('coaching_note','')}",
        "",
        "━━━ E · EVALUATE ━━━",
        f"Commands: <b>{evaluation.get('total_commands',0)}</b>  Top: <b>{evaluation.get('top_action','—')}</b>",
        f"Peak: <b>{evaluation.get('most_active_hour','—')}:00</b>  Fav lights: <b>{evaluation.get('favorite_light_color','—')}</b>",
        "",
        "━━━ V · VERIFY ━━━",
        f"{hue_ok} Hue  {hub_ok} Hub  {api_ok} Claude API",
        f"{'⚠️' if health.get('agent_errors_24h',0) > 5 else '✅'} Errors: {health.get('agent_errors_24h',0)}  ·  Active: {', '.join(health.get('agents_active',['none']))}",
        "",
        "━━━ O/L · LEARN ━━━",
    ]
    for p in auto_applied:
        lines.append(f"✅ [auto {p['confidence']}%] {p['description']}")
    for p in pending:
        lines.append(f"💡 [{p['confidence']}%] {p['description']}")
    if not proposals:
        lines.append("Building pattern history — more data needed.")
    lines += [
        "",
        "━━━ E · EXPAND ━━━",
        f"{feat_emoji} <b>{feature.get('name','—')}</b> [conf {feature.get('confidence',0)}%]",
        feature.get("description", ""),
        f"<i>{feature.get('implementation_hint','')}</i>",
        "",
        f"⏱ {duration_s:.1f}s  ·  Morning Brief fires at 7:00 AM ☀️",
    ]
    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────
def run():
    if was_fired_recently(EVOLVE_KEY, hours=20):
        log(AGENT, "Already ran today, skipping.")
        return

    log(AGENT, "=== EVOLVE Protocol starting ===")
    t_start = time.time()

    telegram_send("⚙️ <b>EVOLVE — 5 AM Protocol</b>\nPreparing today's plan + running system evolution...")

    prep       = preparation_phase()
    evaluation = evaluate_yesterday()
    log(AGENT, f"Evaluated: {evaluation.get('total_commands', 0)} commands")

    health = verify_health()
    log(AGENT, f"Health: Hue={health.get('hue',{}).get('ok')}, Hub={health.get('hub',{}).get('ok')}")

    proposals = optimize_and_learn(evaluation)

    for p in proposals:
        if p.get("auto_apply") and p.get("type") == "preference_update":
            try:
                action = p.get("action", {})
                adler_memory.update_preference(action.get("category"), action.get("context"), action.get("value"))
                log(AGENT, f"Auto-applied: {p['description']}")
            except Exception as e:
                log(AGENT, f"Auto-apply failed: {e}")

    feature  = expand_feature(evaluation, health)
    duration = time.time() - t_start
    report   = build_report(evaluation, health, proposals, feature, prep, duration)

    telegram_send(report)
    mark_fired(EVOLVE_KEY)

    try:
        adler_memory.record_mission(
            "EVOLVE daily protocol",
            f"Evolution: {evaluation.get('total_commands',0)} commands, "
            f"completion={int(prep.get('completion_yesterday',0)*100)}%, fatigue={prep.get('fatigue_score',0)}",
            ["prepare", "evaluate", "verify", "optimize", "learn", "expand"]
        )
    except Exception:
        pass

    log(AGENT, f"=== EVOLVE complete in {duration:.1f}s ===")


if __name__ == "__main__":
    run()
