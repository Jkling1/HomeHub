#!/usr/bin/env python3
"""
Adler's Brain — Pattern Engine
Analyzes Jordan's command history to learn behavior patterns.

Usage:
  python3 pattern_engine.py           # Print full model
  python3 pattern_engine.py scenes    # Show detected scene candidates
  python3 pattern_engine.py peaks     # Show peak activity hours
"""

import sys
import json
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent


# ── History loading ────────────────────────────────────────────────────────────

def load_history(days: int = 90) -> list:
    """Load successful command history from hub.db."""
    from database import get_conn
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, input, action, result, ts FROM commands "
            "WHERE success=1 AND ts >= ? ORDER BY ts",
            (cutoff,),
        ).fetchall()

    history = []
    for r in rows:
        try:
            dt = datetime.strptime(r["ts"], "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
        history.append({
            "id":       r["id"],
            "input":    r["input"] or "",
            "action":   r["action"] or "chat",
            "result":   r["result"] or "",
            "ts":       dt,
            "hour":     dt.hour,
            "dow":      dt.weekday(),       # 0=Monday
            "dow_name": dt.strftime("%A"),
            "date":     dt.strftime("%Y-%m-%d"),
        })
    return history


# ── Session detection ──────────────────────────────────────────────────────────

def build_sessions(history: list, gap_minutes: int = 15) -> list:
    """
    Group commands into 'sessions' — bursts of activity within gap_minutes.
    Only sessions with 2+ commands are returned (single commands aren't scenes).
    """
    if not history:
        return []

    sessions = []
    current = [history[0]]

    for cmd in history[1:]:
        gap = (cmd["ts"] - current[-1]["ts"]).total_seconds() / 60
        if gap <= gap_minutes:
            current.append(cmd)
        else:
            if len(current) >= 2:
                sessions.append(_make_session(current))
            current = [cmd]

    if len(current) >= 2:
        sessions.append(_make_session(current))

    return sessions


def _make_session(cmds: list) -> dict:
    return {
        "commands":  cmds,
        "hour":      cmds[0]["hour"],
        "dow":       cmds[0]["dow"],
        "dow_name":  cmds[0]["dow_name"],
        "date":      cmds[0]["date"],
        "ts":        cmds[0]["ts"],
    }


# ── Fingerprinting ─────────────────────────────────────────────────────────────

def _extract_color(cmd: dict) -> str:
    text = (cmd["input"] + " " + cmd["result"]).lower()
    for c in ["purple", "blue", "red", "green", "orange", "yellow",
              "pink", "white", "warm", "cool", "cyan", "off", "on"]:
        if c in text:
            return c
    return "white"


def _extract_music_query(cmd: dict) -> str:
    inp = cmd["input"].lower()
    for prefix in ["play ", "playing "]:
        if prefix in inp:
            q = inp.split(prefix, 1)[1].strip()
            # Trim trailing filler
            for stop in [" please", " by", " for me"]:
                q = q.split(stop)[0].strip()
            return q[:30]
    return "music"


def session_fingerprint(session: dict) -> str:
    """Canonical fingerprint of a session — order-independent."""
    parts = set()
    for cmd in session["commands"]:
        action = cmd["action"]
        if action == "lights":
            parts.add(f"lights:{_extract_color(cmd)}")
        elif action == "music":
            if any(w in cmd["input"].lower() for w in ["play ", "playing "]):
                parts.add(f"music:{_extract_music_query(cmd)}")
            else:
                parts.add("music:control")
        elif action in ("briefing", "weather", "stock", "wakeup"):
            parts.add(action)
        # Skip 'chat' — too generic to fingerprint
    return "|".join(sorted(parts)) if len(parts) >= 2 else ""


# ── Scene naming ───────────────────────────────────────────────────────────────

def _time_bucket(hour: int) -> str:
    if 5 <= hour < 10:   return "morning"
    if 10 <= hour < 14:  return "midday"
    if 14 <= hour < 18:  return "afternoon"
    if 18 <= hour < 22:  return "evening"
    return "night"


def name_scene(fingerprint: str, avg_hour: int, common_dow: str, count: int) -> str:
    """Generate a human name for a detected scene."""
    bucket      = _time_bucket(avg_hour)
    is_weekend  = common_dow in ("Saturday", "Sunday")
    is_friday   = common_dow == "Friday"
    has_lights  = "lights:" in fingerprint
    has_music   = "music:" in fingerprint

    light_color = None
    music_query = None
    for part in fingerprint.split("|"):
        if part.startswith("lights:"):
            light_color = part.split(":", 1)[1]
        if part.startswith("music:"):
            music_query = part.split(":", 1)[1]

    if is_friday and bucket in ("evening", "night"):
        return "Friday Night"
    if is_weekend and bucket in ("evening", "night"):
        return "Weekend Night"
    if bucket == "night" and has_lights and has_music:
        return "Wind Down"
    if bucket == "morning" and count >= 4:
        return "Morning Routine"
    if bucket == "evening" and has_lights and has_music:
        return "Evening Vibe"
    if light_color in ("purple", "blue", "red") and has_music:
        return f"{light_color.capitalize()} Vibe"
    if has_lights and has_music:
        return f"{bucket.capitalize()} Scene"
    if has_lights:
        return f"{bucket.capitalize()} Lights"
    return f"{bucket.capitalize()} Session"


# ── Scene candidate detection ──────────────────────────────────────────────────

def detect_scene_candidates(sessions: list, min_count: int = 3) -> list:
    """
    Find recurring session patterns worth naming as scenes.
    Returns candidates sorted by frequency.
    """
    by_fp = defaultdict(list)
    for s in sessions:
        fp = session_fingerprint(s)
        if fp:
            by_fp[fp].append(s)

    candidates = []
    for fp, occurrences in by_fp.items():
        if len(occurrences) < min_count:
            continue

        hours     = [s["hour"] for s in occurrences]
        dows      = [s["dow_name"] for s in occurrences]
        avg_hour  = int(sum(hours) / len(hours))
        common_dow = Counter(dows).most_common(1)[0][0]
        count     = len(occurrences)

        # Best representative session = closest to average hour
        best = min(occurrences, key=lambda s: abs(s["hour"] - avg_hour))
        sample_inputs = [c["input"] for c in best["commands"]]

        name       = name_scene(fp, avg_hour, common_dow, count)
        confidence = round(min(1.0, count / 10.0), 2)

        candidates.append({
            "fingerprint":   fp,
            "name":          name,
            "count":         count,
            "avg_hour":      avg_hour,
            "time_bucket":   _time_bucket(avg_hour),
            "common_dow":    common_dow,
            "confidence":    confidence,
            "sample_inputs": sample_inputs,
            "last_seen":     occurrences[-1]["date"],
        })

    return sorted(candidates, key=lambda c: c["count"], reverse=True)


# ── Stats helpers ──────────────────────────────────────────────────────────────

def get_peak_hours(history: list) -> dict:
    return dict(sorted(Counter(c["hour"] for c in history).items()))


def get_top_music(history: list, limit: int = 10) -> list:
    queries = []
    for c in history:
        if c["action"] == "music":
            inp = c["input"].lower()
            for prefix in ["play ", "playing "]:
                if prefix in inp:
                    q = inp.split(prefix, 1)[1].strip()
                    for stop in [" please", " by "]:
                        q = q.split(stop)[0].strip()
                    if len(q) > 2:
                        queries.append(q[:30])
                    break
    return Counter(queries).most_common(limit)


def get_top_colors(history: list, limit: int = 8) -> list:
    colors = []
    for c in history:
        if c["action"] == "lights":
            color = _extract_color(c)
            if color not in ("on", "off", "white"):
                colors.append(color)
    return Counter(colors).most_common(limit)


def get_weekly_pattern(history: list) -> dict:
    days = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    counts = Counter(c["dow_name"] for c in history)
    return {d: counts.get(d, 0) for d in days}


def get_action_breakdown(history: list) -> dict:
    return dict(Counter(c["action"] for c in history).most_common())


def get_recent_drift(history: list) -> dict:
    """Compare last 14 days vs previous 14 days to detect behavior changes."""
    now = datetime.now()
    recent = [c for c in history if (now - c["ts"]).days <= 14]
    prior  = [c for c in history if 14 < (now - c["ts"]).days <= 28]

    if not recent or not prior:
        return {}

    def top_action(h):
        a = Counter(c["action"] for c in h)
        return a.most_common(1)[0][0] if a else None

    def avg_hour(h):
        return round(sum(c["hour"] for c in h) / len(h), 1) if h else 0

    return {
        "recent_count":   len(recent),
        "prior_count":    len(prior),
        "count_delta":    len(recent) - len(prior),
        "recent_top":     top_action(recent),
        "prior_top":      top_action(prior),
        "recent_avg_hour": avg_hour(recent),
        "prior_avg_hour":  avg_hour(prior),
    }


# ── Full model ─────────────────────────────────────────────────────────────────

def build_jordan_model(days: int = 90) -> dict:
    """Build a complete behavioral model from Jordan's history."""
    history = load_history(days)
    if not history:
        return {"error": "No history yet", "history_count": 0}

    sessions   = build_sessions(history)
    candidates = detect_scene_candidates(sessions)

    return {
        "history_count":    len(history),
        "days_analyzed":    days,
        "session_count":    len(sessions),
        "peak_hours":       get_peak_hours(history),
        "top_music":        get_top_music(history),
        "top_colors":       get_top_colors(history),
        "weekly_pattern":   get_weekly_pattern(history),
        "action_breakdown": get_action_breakdown(history),
        "scene_candidates": candidates,
        "recent_drift":     get_recent_drift(history),
        "generated_at":     datetime.now().isoformat(),
    }


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    model = build_jordan_model()

    if "error" in model:
        print(model["error"])
        sys.exit(0)

    if mode == "scenes":
        candidates = model["scene_candidates"]
        if not candidates:
            print("No recurring scenes detected yet (need more history).")
        else:
            print(f"\n🎭 Detected {len(candidates)} scene pattern(s):\n")
            for c in candidates:
                print(f"  {c['name']:20s}  {c['count']:3d}x  ~{c['avg_hour']:02d}:00  "
                      f"{c['common_dow']:9s}  confidence={c['confidence']:.0%}")
                for inp in c["sample_inputs"]:
                    print(f"    → \"{inp}\"")
                print()

    elif mode == "peaks":
        print(f"\n⏰ Peak activity hours (last {model['days_analyzed']} days):\n")
        peaks = model["peak_hours"]
        max_count = max(peaks.values()) if peaks else 1
        for hour, count in sorted(peaks.items()):
            bar = "█" * int(count / max_count * 20)
            ampm = f"{hour % 12 or 12}{'am' if hour < 12 else 'pm'}"
            print(f"  {ampm:5s}  {bar:<20s} {count}")
        print()

    else:
        print(f"\n🧠 Jordan Model  ({model['history_count']} commands, "
              f"{model['days_analyzed']}d)\n")
        print(f"  Sessions detected: {model['session_count']}")
        print(f"  Scene patterns:    {len(model['scene_candidates'])}")

        print(f"\n  Top colors:  {model['top_colors'][:4]}")
        print(f"  Top music:   {model['top_music'][:4]}")
        print(f"  By action:   {model['action_breakdown']}")

        drift = model["recent_drift"]
        if drift and drift.get("count_delta"):
            delta = drift["count_delta"]
            sign  = "+" if delta > 0 else ""
            print(f"\n  Recent vs prior: {sign}{delta} commands "
                  f"({drift['recent_avg_hour']}h avg → was {drift['prior_avg_hour']}h)")
        print()
