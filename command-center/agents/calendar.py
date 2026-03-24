#!/usr/bin/env python3
"""
Calendar awareness for Adler.
Reads Apple Calendar via osascript to get today's events.
"""

import subprocess
import json
from datetime import datetime
from agents.base import log

AGENT = "calendar"

APPLESCRIPT = '''
tell application "Calendar"
    set todayStart to current date
    set time of todayStart to 0
    set todayEnd to current date
    set time of todayEnd to 86399

    set eventList to {}
    repeat with cal in calendars
        set evts to every event of cal whose start date >= todayStart and start date <= todayEnd
        repeat with evt in evts
            set evtStart to start date of evt
            set evtEnd to end date of evt
            set h to hours of evtStart
            set m to minutes of evtStart
            set eh to hours of evtEnd
            set em to minutes of evtEnd
            set evtTitle to summary of evt
            set end of eventList to (h * 100 + m) & "," & (eh * 100 + em) & "," & evtTitle
        end repeat
    end repeat
    return eventList
end tell
'''


def get_today_events() -> list[dict]:
    """Returns list of today's calendar events sorted by start time."""
    try:
        result = subprocess.run(
            ["osascript", "-e", APPLESCRIPT],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return []

        raw = result.stdout.strip()
        if not raw:
            return []

        events = []
        # osascript returns comma-separated items as a string list
        # Format: "startHHMM, endHHMM, Title, startHHMM, endHHMM, Title..."
        items = [x.strip() for x in raw.split(",")]
        i = 0
        while i + 2 < len(items):
            try:
                start_hhmm = int(items[i])
                end_hhmm   = int(items[i+1])
                title      = items[i+2]
                start_h, start_m = divmod(start_hhmm, 100)
                end_h, end_m     = divmod(end_hhmm, 100)
                events.append({
                    "title": title,
                    "start": f"{start_h:02d}:{start_m:02d}",
                    "end":   f"{end_h:02d}:{end_m:02d}",
                    "start_min": start_h * 60 + start_m,
                })
                i += 3
            except (ValueError, IndexError):
                i += 1

        return sorted(events, key=lambda x: x["start_min"])

    except Exception as e:
        log(AGENT, f"Calendar read error: {e}")
        return []


def format_for_prompt(events: list[dict]) -> str:
    """Format events into a concise string for Adler's context."""
    if not events:
        return "No calendar events today."

    now = datetime.now()
    now_min = now.hour * 60 + now.minute

    lines = [f"Today's calendar ({now.strftime('%A, %B %d')}):"]
    for evt in events:
        mins_until = evt["start_min"] - now_min
        if mins_until < 0:
            relative = "past"
        elif mins_until < 60:
            relative = f"in {mins_until}min"
        else:
            hours = mins_until // 60
            relative = f"in {hours}h"
        lines.append(f"  • {evt['start']}–{evt['end']}  {evt['title']}  ({relative})")

    # Flag upcoming events in next 30 min
    imminent = [e for e in events if 0 <= e["start_min"] - now_min <= 30]
    if imminent:
        lines.append(f"\n⚠️ Imminent: {imminent[0]['title']} starts in {imminent[0]['start_min'] - now_min} min")

    return "\n".join(lines)


def get_context_string() -> str:
    """Full calendar context string ready to inject into prompt."""
    try:
        events = get_today_events()
        return format_for_prompt(events)
    except Exception as e:
        return f"Calendar unavailable: {e}"
