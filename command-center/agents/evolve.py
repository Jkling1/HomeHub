#!/usr/bin/env python3
"""
EVOLVE Protocol — 5:00 AM daily system evolution cycle.

E = Evaluate   → analyze yesterday's behavior
V = Verify     → system health check
O = Optimize   → update memory with behavioral insights
L = Learn      → compare plan vs reality
V = Visualize  → build evolution report
E = Expand     → propose 1 micro-feature with confidence score

Runtime: ~30–90 seconds. Sends full report to Telegram.
"""

import json
import time
import requests as req
from datetime import datetime, timedelta
from agents.base import *
from agents import adler_memory

AGENT = "evolve"
EVOLVE_KEY = f"evolve_{today_str()}"
EVOLVE_STATE_FILE = ROOT_DIR / "evolve_state.json"


# ── Confidence scoring ─────────────────────────────────────────────────────────
def confidence(evidence_count: int, consistency_days: int, impact: str = "low") -> int:
    """
    Score 0-100. Only scores ≥70 get auto-applied.
    evidence_count: how many data points support this insight
    consistency_days: how many days this pattern held
    impact: low/medium/high (higher impact = more cautious)
    """
    base = min(evidence_count * 12, 60)
    base += min(consistency_days * 8, 30)
    impact_penalty = {"low": 0, "medium": -5, "high": -15}.get(impact, 0)
    return max(0, min(100, base + impact_penalty))


# ── Phase 1: EVALUATE — yesterday's behavior ──────────────────────────────────
def evaluate_yesterday() -> dict:
    log(AGENT, "E — Evaluating yesterday's behavior")
    try:
        rows = req.get(f"{HUB_BASE}/history", timeout=10).json()
    except Exception as e:
        log(AGENT, f"History unavailable: {e}")
        return {}

    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_rows = [r for r in rows if (r.get("ts") or "").startswith(yesterday)]

    if not yesterday_rows:
        # Fall back to all recent history
        yesterday_rows = rows[:30]

    # Count action types
    action_counts = {}
    light_colors = []
    music_queries = []
    peak_hours = {}

    for r in yesterday_rows:
        action = r.get("action", "unknown")
        action_counts[action] = action_counts.get(action, 0) + 1

        ts = r.get("ts", "")
        if ts and len(ts) > 13:
            try:
                hour = int(ts[11:13])
                peak_hours[hour] = peak_hours.get(hour, 0) + 1
            except ValueError:
                pass

        intent = r.get("intent") or {}
        if action == "lights" and isinstance(intent, dict):
            col = intent.get("color")
            if col:
                light_colors.append(col)
        if action == "music" and isinstance(intent, dict):
            q = intent.get("query")
            if q:
                music_queries.append(q)

    most_active_hour = max(peak_hours, key=peak_hours.get) if peak_hours else None
    top_action = max(action_counts, key=action_counts.get) if action_counts else None
    fav_color = max(set(light_colors), key=light_colors.count) if light_colors else None

    return {
        "total_commands": len(yesterday_rows),
        "action_counts": action_counts,
        "top_action": top_action,
        "most_active_hour": most_active_hour,
        "favorite_light_color": fav_color,
        "music_queries": music_queries[:5],
        "peak_hours": peak_hours,
    }


# ── Phase 2: VERIFY — system health ───────────────────────────────────────────
def verify_health() -> dict:
    log(AGENT, "V — Verifying system health")
    results = {}

    # Check Hue bridge
    HUE_BRIDGE = os.environ.get("HUE_BRIDGE", "192.168.12.225")
    HUE_KEY    = os.environ.get("HUE_KEY", "")
    try:
        t0 = time.time()
        r = req.get(f"http://{HUE_BRIDGE}/api/{HUE_KEY}/lights", timeout=5)
        latency_ms = int((time.time() - t0) * 1000)
        light_count = len(r.json()) if r.ok else 0
        results["hue"] = {"ok": r.ok, "latency_ms": latency_ms, "lights": light_count}
    except Exception as e:
        results["hue"] = {"ok": False, "error": str(e)}

    # Check hub server
    try:
        t0 = time.time()
        r = req.get(f"{HUB_BASE}/status", timeout=5)
        latency_ms = int((time.time() - t0) * 1000)
        results["hub"] = {"ok": r.ok, "latency_ms": latency_ms}
    except Exception as e:
        results["hub"] = {"ok": False, "error": str(e)}

    # Check Anthropic API
    try:
        t0 = time.time()
        r = req.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": "claude-haiku-4-5-20251001", "max_tokens": 5, "messages": [{"role": "user", "content": "ping"}]},
            timeout=10,
        )
        latency_ms = int((time.time() - t0) * 1000)
        results["anthropic_api"] = {"ok": r.ok, "latency_ms": latency_ms}
    except Exception as e:
        results["anthropic_api"] = {"ok": False, "error": str(e)}

    # Check agent log for recent errors
    log_file = ROOT_DIR / "agent.log"
    error_count = 0
    if log_file.exists():
        lines = log_file.read_text().splitlines()[-200:]
        error_count = sum(1 for l in lines if "error" in l.lower() or "Error" in l)
    results["agent_errors_24h"] = error_count

    # Check agent state — which agents ran recently
    state = load_state()
    agents_ran = []
    for key, ts in state.items():
        if time.time() - float(ts) < 86400:
            agents_ran.append(key.split("_")[0])
    results["agents_active"] = list(set(agents_ran))

    return results


# ── Phase 3: OPTIMIZE + LEARN — memory + plan vs reality ──────────────────────
def optimize_and_learn(evaluation: dict) -> list[dict]:
    """Returns a list of proposed changes, each with a confidence score."""
    log(AGENT, "O/L — Optimizing and learning from data")
    proposals = []
    mem = adler_memory.load()

    # Insight: favorite light color
    fav_color = evaluation.get("favorite_light_color")
    if fav_color:
        history = mem.get("evolve_color_history", {})
        history[fav_color] = history.get(fav_color, 0) + 1
        mem["evolve_color_history"] = history
        adler_memory.save(mem)

        consistency = history.get(fav_color, 1)
        score = confidence(evaluation.get("total_commands", 1), consistency, "low")
        proposals.append({
            "type": "preference_update",
            "description": f"Jordan's most-used light color: {fav_color} ({consistency} days)",
            "action": {"category": "lights", "context": "default", "value": fav_color},
            "confidence": score,
            "auto_apply": score >= 70,
        })

    # Insight: peak usage hour
    peak_hour = evaluation.get("most_active_hour")
    if peak_hour is not None:
        hour_history = mem.get("evolve_peak_hours", [])
        hour_history.append(peak_hour)
        hour_history = hour_history[-14:]  # last 14 days
        mem["evolve_peak_hours"] = hour_history
        adler_memory.save(mem)

        consistency = hour_history.count(peak_hour)
        score = confidence(len(hour_history), consistency, "low")
        ampm = "AM" if peak_hour < 12 else "PM"
        h12 = peak_hour if peak_hour <= 12 else peak_hour - 12
        proposals.append({
            "type": "pattern_insight",
            "description": f"Jordan is most active at {h12}:00 {ampm} ({consistency}/{len(hour_history)} days)",
            "confidence": score,
            "auto_apply": score >= 80,
        })

    # Use Claude to analyze music patterns and generate behavioral insight
    if evaluation.get("music_queries"):
        try:
            music_text = ", ".join(evaluation["music_queries"])
            insight = claude(
                f"Jordan played: {music_text}. Write one sharp behavioral insight about his music taste or mood pattern. 15 words max.",
                max_tokens=40
            )
            proposals.append({
                "type": "behavioral_insight",
                "description": insight,
                "confidence": 65,
                "auto_apply": False,
            })
        except Exception:
            pass

    return proposals


# ── Phase 4: EXPAND — daily micro-feature ─────────────────────────────────────
def expand_feature(evaluation: dict, health: dict) -> dict:
    """Generate 1 micro-feature suggestion based on current state."""
    log(AGENT, "E — Generating feature expansion")

    top_action = evaluation.get("top_action", "lights")
    total = evaluation.get("total_commands", 0)

    prompt = f"""You are the EVOLVE Protocol for Jordan's Smart Hub.

Yesterday's usage: {total} commands. Top action: {top_action}.
System health: Hue {health.get('hue',{}).get('latency_ms','?')}ms, Hub {health.get('hub',{}).get('latency_ms','?')}ms.
Active agents: {', '.join(health.get('agents_active', []))}.

Propose ONE small, specific, buildable micro-feature that would improve Jordan's daily experience.
Requirements: implementable in <50 lines of Python or CSS, doesn't break existing code, directly useful.

Return JSON only:
{{
  "name": "Feature name (5 words max)",
  "description": "What it does (1 sentence)",
  "implementation_hint": "How to build it (1 sentence)",
  "confidence": <50-100>,
  "impact": "low|medium|high"
}}"""

    try:
        raw = claude(prompt, max_tokens=200)
        if "{" in raw:
            raw = raw[raw.index("{"):raw.rindex("}")+1]
        feature = json.loads(raw)
        return feature
    except Exception as e:
        log(AGENT, f"Feature generation error: {e}")
        return {
            "name": "Quick-access scenes button",
            "description": "Add a 1-tap scene row to the home panel for your most-used light scenes.",
            "implementation_hint": "Fetch /scenes, render as pill buttons above the feed card.",
            "confidence": 72,
            "impact": "medium",
        }


# ── Phase 5: VISUALIZE — build and send report ────────────────────────────────
def build_report(evaluation: dict, health: dict, proposals: list, feature: dict, duration_s: float) -> str:
    auto_applied = [p for p in proposals if p.get("auto_apply")]
    pending = [p for p in proposals if not p.get("auto_apply")]

    hue_ok = "✅" if health.get("hue", {}).get("ok") else "❌"
    hub_ok = "✅" if health.get("hub", {}).get("ok") else "❌"
    api_ok = "✅" if health.get("anthropic_api", {}).get("ok") else "❌"
    hue_ms = health.get("hue", {}).get("latency_ms", "?")
    hub_ms = health.get("hub", {}).get("latency_ms", "?")
    api_ms = health.get("anthropic_api", {}).get("latency_ms", "?")
    errors  = health.get("agent_errors_24h", 0)

    top_action = evaluation.get("top_action", "—")
    total_cmds = evaluation.get("total_commands", 0)
    peak_h = evaluation.get("most_active_hour")
    peak_str = f"{peak_h}:00" if peak_h is not None else "—"
    fav_color = evaluation.get("favorite_light_color", "—")

    feat_conf = feature.get("confidence", 0)
    feat_emoji = "🟢" if feat_conf >= 70 else "🟡"

    lines = [
        "⚡ <b>EVOLVE Protocol — Daily Evolution Report</b>",
        f"<i>{datetime.now().strftime('%A, %B %d · %I:%M %p')}</i>",
        "",
        "━━━ E · EVALUATE ━━━",
        f"Commands yesterday: <b>{total_cmds}</b>",
        f"Top action: <b>{top_action}</b>",
        f"Peak hour: <b>{peak_str}</b>",
        f"Favorite lights: <b>{fav_color}</b>",
        "",
        "━━━ V · VERIFY ━━━",
        f"{hue_ok} Hue Bridge — {hue_ms}ms · {health.get('hue',{}).get('lights',0)} lights",
        f"{hub_ok} Hub Server — {hub_ms}ms",
        f"{api_ok} Claude API — {api_ms}ms",
        f"{'⚠️' if errors > 5 else '✅'} Agent errors (24h): {errors}",
        f"Active agents: {', '.join(health.get('agents_active', ['none']))}",
        "",
        "━━━ O/L · OPTIMIZE + LEARN ━━━",
    ]

    for p in auto_applied:
        lines.append(f"✅ [auto-applied, conf {p['confidence']}%] {p['description']}")
    for p in pending:
        lines.append(f"💡 [conf {p['confidence']}%] {p['description']}")

    if not proposals:
        lines.append("No significant patterns yet — more data needed.")

    lines += [
        "",
        "━━━ E · EXPAND ━━━",
        f"{feat_emoji} <b>{feature.get('name', 'Feature')}</b> [conf {feat_conf}%]",
        f"{feature.get('description', '')}",
        f"<i>{feature.get('implementation_hint', '')}</i>",
        "",
        f"⏱ Evolution complete in {duration_s:.1f}s",
    ]

    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────
def run():
    if was_fired_recently(EVOLVE_KEY, hours=20):
        log(AGENT, "Already ran today, skipping.")
        return

    log(AGENT, "=== EVOLVE Protocol starting ===")
    t_start = time.time()

    telegram_send("⚡ <b>EVOLVE Protocol initiated</b>\nRunning daily system evolution...")

    # Run all phases
    evaluation = evaluate_yesterday()
    log(AGENT, f"Evaluated: {evaluation.get('total_commands', 0)} commands")

    health = verify_health()
    log(AGENT, f"Health check complete. Hue: {health.get('hue',{}).get('ok')}, Hub: {health.get('hub',{}).get('ok')}")

    proposals = optimize_and_learn(evaluation)
    log(AGENT, f"Generated {len(proposals)} proposals")

    # Auto-apply high-confidence preference updates
    for p in proposals:
        if p.get("auto_apply") and p.get("type") == "preference_update":
            try:
                action = p.get("action", {})
                adler_memory.update_preference(
                    action.get("category", "lights"),
                    action.get("context", "default"),
                    action.get("value", "")
                )
                log(AGENT, f"Auto-applied: {p['description']}")
            except Exception as e:
                log(AGENT, f"Auto-apply failed: {e}")

    feature = expand_feature(evaluation, health)
    log(AGENT, f"Feature: {feature.get('name')} [conf {feature.get('confidence')}%]")

    duration = time.time() - t_start
    report = build_report(evaluation, health, proposals, feature, duration)

    telegram_send(report)
    mark_fired(EVOLVE_KEY)

    # Record to Adler's memory
    try:
        adler_memory.record_mission(
            "EVOLVE daily protocol",
            f"Ran evolution cycle: {evaluation.get('total_commands',0)} commands analyzed, {len(proposals)} insights, feature: {feature.get('name')}",
            ["evaluate", "verify", "optimize", "learn", "expand"]
        )
    except Exception:
        pass

    log(AGENT, f"=== EVOLVE complete in {duration:.1f}s ===")


if __name__ == "__main__":
    run()
