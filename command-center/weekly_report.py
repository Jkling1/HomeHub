#!/usr/bin/env python3
"""
Adler's Brain — Weekly Life Report
Generates a personal analytics digest every Sunday.

Usage:
  python3 weekly_report.py         # Print report to terminal
  python3 weekly_report.py --send  # Generate and send via Telegram
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter

ENV_PATH = Path(__file__).parent / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
SCRIPT_DIR       = Path(__file__).parent


# ── Data loading ──────────────────────────────────────────────────────────────

def load_week(days_ago_start: int, days_ago_end: int) -> list:
    """Load commands from a date range (days ago)."""
    from database import get_conn
    now    = datetime.now()
    start  = (now - timedelta(days=days_ago_start)).strftime("%Y-%m-%d")
    end    = (now - timedelta(days=days_ago_end)).strftime("%Y-%m-%d")
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT input, action, result, ts FROM commands "
            "WHERE success=1 AND date(ts) >= ? AND date(ts) < ? ORDER BY ts",
            (end, start) if days_ago_start > days_ago_end else (start, end),
        ).fetchall()
    history = []
    for r in rows:
        try:
            dt = datetime.strptime(r["ts"], "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
        history.append({
            "input":    r["input"] or "",
            "action":   r["action"] or "chat",
            "result":   r["result"] or "",
            "ts":       dt,
            "hour":     dt.hour,
            "dow_name": dt.strftime("%A"),
        })
    return history


def _extract_color(cmd: dict) -> str:
    text = (cmd["input"] + " " + cmd["result"]).lower()
    for c in ["purple","blue","red","green","orange","yellow","pink","warm","cool","cyan"]:
        if c in text:
            return c
    return "white"


def _extract_music(cmd: dict) -> str:
    inp = cmd["input"].lower()
    for prefix in ["play ", "playing "]:
        if prefix in inp:
            q = inp.split(prefix, 1)[1].strip()
            for stop in [" please", " by "]:
                q = q.split(stop)[0].strip()
            return q[:25] if len(q) > 2 else ""
    return ""


# ── Stats builders ────────────────────────────────────────────────────────────

def compute_stats(history: list) -> dict:
    if not history:
        return {}

    total      = len(history)
    actions    = Counter(c["action"] for c in history)
    colors     = Counter(_extract_color(c) for c in history if c["action"] == "lights")
    music_plays= [_extract_music(c) for c in history
                  if c["action"] == "music" and _extract_music(c)]
    music_ctr  = Counter(music_plays)
    peak_hour  = Counter(c["hour"] for c in history).most_common(1)[0][0]
    peak_day   = Counter(c["dow_name"] for c in history).most_common(1)[0][0]
    hours      = list(Counter(c["hour"] for c in history).keys())
    active_spread = f"{min(hours) % 12 or 12}{'am' if min(hours) < 12 else 'pm'}–{max(hours) % 12 or 12}{'am' if max(hours) < 12 else 'pm'}"

    return {
        "total":          total,
        "actions":        dict(actions.most_common()),
        "top_color":      colors.most_common(1)[0] if colors else ("none", 0),
        "top_music":      music_ctr.most_common(3),
        "music_count":    sum(1 for c in history if c["action"] == "music"),
        "light_changes":  actions.get("lights", 0),
        "briefings":      actions.get("briefing", 0),
        "peak_hour":      peak_hour,
        "peak_hour_str":  f"{peak_hour % 12 or 12}{'am' if peak_hour < 12 else 'pm'}",
        "peak_day":       peak_day,
        "active_spread":  active_spread,
    }


def compute_delta(this_week: dict, last_week: dict) -> dict:
    """Compute week-over-week changes."""
    if not this_week or not last_week:
        return {}
    delta = this_week.get("total", 0) - last_week.get("total", 0)
    sign  = "+" if delta >= 0 else ""
    return {
        "commands_delta": f"{sign}{delta}",
        "trend":          "up" if delta > 0 else ("down" if delta < 0 else "flat"),
    }


# ── Formatting ────────────────────────────────────────────────────────────────

def _bar(value: int, max_val: int, width: int = 8) -> str:
    filled = int((value / max_val) * width) if max_val else 0
    return "▓" * filled + "░" * (width - filled)


def format_report_terminal(this_week: dict, last_week: dict, delta: dict) -> str:
    if not this_week:
        return "Not enough data for a weekly report yet. Keep using the hub!"

    now        = datetime.now()
    week_start = (now - timedelta(days=7)).strftime("%b %-d")
    week_end   = now.strftime("%b %-d")

    lines = []
    lines.append(f"\n📊  Jordan's Weekly Report  ·  {week_start} – {week_end}\n")
    lines.append(f"  Total commands:   {this_week['total']:>4d}  {delta.get('commands_delta','')}")
    lines.append(f"  Most active day:  {this_week['peak_day']}")
    lines.append(f"  Peak hour:        {this_week['peak_hour_str']}")
    lines.append(f"  Active window:    {this_week['active_spread']}")

    if this_week["top_color"][1] > 0:
        lines.append(f"\n  Favorite light:   {this_week['top_color'][0]}  ({this_week['top_color'][1]}x)")

    if this_week["top_music"]:
        lines.append(f"\n  Top music:")
        max_plays = this_week["top_music"][0][1]
        for track, count in this_week["top_music"]:
            lines.append(f"    {_bar(count, max_plays)}  {track}  ({count}x)")

    actions = this_week["actions"]
    if actions:
        lines.append(f"\n  Commands by type:")
        max_a = max(actions.values())
        for action, count in sorted(actions.items(), key=lambda x: -x[1])[:6]:
            lines.append(f"    {_bar(count, max_a)}  {action}  ({count})")

    lines.append("")
    return "\n".join(lines)


def format_report_telegram(this_week: dict, last_week: dict, delta: dict) -> str:
    if not this_week:
        return "📊 Not enough data for a weekly report yet. Keep using the hub — it's learning your patterns."

    now        = datetime.now()
    week_start = (now - timedelta(days=7)).strftime("%b %-d")
    week_end   = now.strftime("%b %-d")

    trend_emoji = {"up": "📈", "down": "📉", "flat": "➡️"}.get(delta.get("trend",""), "")
    total_line  = f"{this_week['total']} commands  {trend_emoji} {delta.get('commands_delta','')}" \
                  if delta else f"{this_week['total']} commands"

    lines = []
    lines.append(f"📊 <b>Jordan's Weekly Report</b>")
    lines.append(f"<i>{week_start} – {week_end}</i>")
    lines.append("")
    lines.append(f"<b>Activity</b>")
    lines.append(f"  Commands: {total_line}")
    lines.append(f"  Busiest day: {this_week['peak_day']}")
    lines.append(f"  Peak time: {this_week['peak_hour_str']}")

    if this_week["light_changes"] > 0:
        color = this_week["top_color"][0]
        lines.append("")
        lines.append(f"<b>Lights</b>")
        lines.append(f"  Changed {this_week['light_changes']}x this week")
        lines.append(f"  Favorite: {color}")

    if this_week["top_music"]:
        lines.append("")
        lines.append(f"<b>Music</b>  ({this_week['music_count']} sessions)")
        for track, count in this_week["top_music"][:3]:
            lines.append(f"  ▶ {track}  ×{count}")

    if this_week["briefings"] > 0:
        lines.append("")
        lines.append(f"<b>Briefings</b>: {this_week['briefings']}x this week")

    # Pattern insight
    lines.append("")
    lines.append("<b>Insight</b>")
    hour    = this_week["peak_hour"]
    bucket  = "morning" if hour < 12 else ("afternoon" if hour < 18 else "evening")
    lines.append(f"  You're most active in the {bucket} ({this_week['peak_hour_str']}). "
                 f"I'm learning your patterns and will suggest your favorite scenes at the right times.")

    return "\n".join(lines)


# ── Send ──────────────────────────────────────────────────────────────────────

def send_telegram(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram not configured]")
        return
    try:
        import requests
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        print(f"Telegram error: {e}")


# ── Entry point ───────────────────────────────────────────────────────────────

def generate_report(send: bool = False) -> str:
    this_history = load_week(0, 7)
    last_history = load_week(7, 14)

    this_stats = compute_stats(this_history)
    last_stats = compute_stats(last_history)
    delta      = compute_delta(this_stats, last_stats)

    if send:
        msg = format_report_telegram(this_stats, last_stats, delta)
        send_telegram(msg)
        return msg
    else:
        return format_report_terminal(this_stats, last_stats, delta)


if __name__ == "__main__":
    send_flag = "--send" in sys.argv
    report    = generate_report(send=send_flag)
    print(report)
