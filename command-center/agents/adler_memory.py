#!/usr/bin/env python3
"""
Adler's persistent memory system.
Grows with every mission — preferences, outcomes, patterns, facts.
"""

import json
from datetime import datetime
from pathlib import Path
from agents.base import ROOT_DIR, claude, log

MEMORY_FILE = ROOT_DIR / "adler_memory.json"
AGENT = "memory"

DEFAULT_MEMORY = {
    "version": 1,
    "last_updated": None,
    "facts": [
        "Jordan lives in Rockford, IL.",
        "Jordan values discipline, performance, and execution above all.",
        "Jordan tracks: workout, protein, hydration, sleep, mood daily.",
        "Jordan's Philips Hue lights and Apple Music are hub-controlled.",
        "Jordan is building a business and optimizing daily performance.",
    ],
    "preferences": {
        "lights": {
            "focus": "cool white, brightness 180",
            "morning": "warm orange, brightness 120",
            "evening": "purple or blue, brightness 150",
            "workout": "red, full brightness",
        },
        "music": {
            "focus": "instrumental or lo-fi",
            "morning": "energizing, upbeat",
            "workout": "hard-hitting, rap or metal",
            "evening": "chill, R&B or jazz",
        },
    },
    "patterns": [],
    "outcomes": [],
    "notes": [],
    "mission_count": 0,
}


def load() -> dict:
    if MEMORY_FILE.exists():
        try:
            return json.loads(MEMORY_FILE.read_text())
        except Exception:
            pass
    return dict(DEFAULT_MEMORY)


def save(memory: dict):
    memory["last_updated"] = datetime.now().isoformat()
    MEMORY_FILE.write_text(json.dumps(memory, indent=2))


def format_for_prompt(memory: dict) -> str:
    """Render memory as a readable block to inject into Adler's system prompt."""
    lines = ["=== ADLER MEMORY ===\n"]

    # Facts
    if memory.get("facts"):
        lines.append("KNOWN FACTS:")
        for f in memory["facts"]:
            lines.append(f"  • {f}")
        lines.append("")

    # Preferences
    prefs = memory.get("preferences", {})
    if prefs:
        lines.append("LEARNED PREFERENCES:")
        if prefs.get("lights"):
            lines.append("  Lights:")
            for ctx, setting in prefs["lights"].items():
                lines.append(f"    {ctx}: {setting}")
        if prefs.get("music"):
            lines.append("  Music:")
            for ctx, setting in prefs["music"].items():
                lines.append(f"    {ctx}: {setting}")
        lines.append("")

    # Recent outcomes (last 10)
    outcomes = memory.get("outcomes", [])[-10:]
    if outcomes:
        lines.append("RECENT MISSION OUTCOMES:")
        for o in outcomes:
            lines.append(f"  [{o.get('date','?')}] {o.get('mission','?')} → {o.get('summary','?')}")
        lines.append("")

    # Patterns
    patterns = memory.get("patterns", [])[-5:]
    if patterns:
        lines.append("OBSERVED PATTERNS:")
        for p in patterns:
            lines.append(f"  • {p}")
        lines.append("")

    # Notes
    notes = memory.get("notes", [])[-5:]
    if notes:
        lines.append("ADLER'S NOTES:")
        for n in notes:
            lines.append(f"  • {n}")
        lines.append("")

    lines.append(f"Mission count: {memory.get('mission_count', 0)}")
    lines.append("===================")
    return "\n".join(lines)


def record_mission(mission: str, summary: str, tool_calls: list):
    """After a mission, extract learnings and update memory."""
    memory = load()

    # Record the outcome
    memory["outcomes"].append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "mission": mission[:100],
        "summary": summary[:200],
        "tools_used": [t for t in tool_calls if t],
    })
    memory["mission_count"] = memory.get("mission_count", 0) + 1

    # Keep outcomes list bounded
    if len(memory["outcomes"]) > 50:
        memory["outcomes"] = memory["outcomes"][-50:]

    # Ask Claude to extract any learnings worth keeping
    if memory["mission_count"] % 3 == 0 and summary:  # every 3 missions, consolidate
        try:
            recent_text = "\n".join(
                f"- {o['mission']} → {o['summary']}"
                for o in memory["outcomes"][-6:]
            )
            extract_prompt = f"""Based on these recent mission outcomes for Jordan's Smart Hub:

{recent_text}

Extract 1-2 specific patterns or preferences worth remembering long-term.
Return as a JSON object: {{"patterns": ["..."], "notes": ["..."]}}
Only add genuinely new insights. Return empty arrays if nothing new."""

            raw = claude(extract_prompt, max_tokens=200)
            if raw.startswith("{"):
                extracted = json.loads(raw)
                new_patterns = extracted.get("patterns", [])
                new_notes = extracted.get("notes", [])
                if new_patterns:
                    memory["patterns"].extend(new_patterns)
                    memory["patterns"] = memory["patterns"][-20:]  # keep last 20
                if new_notes:
                    memory["notes"].extend(new_notes)
                    memory["notes"] = memory["notes"][-20:]
        except Exception as e:
            log(AGENT, f"Learning extraction error: {e}")

    save(memory)
    log(AGENT, f"Memory updated. Mission #{memory['mission_count']}. Outcomes stored: {len(memory['outcomes'])}")


def add_fact(fact: str):
    """Explicitly add a fact Jordan told Adler."""
    memory = load()
    if fact not in memory["facts"]:
        memory["facts"].append(fact)
        memory["facts"] = memory["facts"][-30:]
    save(memory)


def update_preference(category: str, context: str, value: str):
    """Update a learned preference (e.g. lights, focus → cool white 180)."""
    memory = load()
    if category not in memory["preferences"]:
        memory["preferences"][category] = {}
    memory["preferences"][category][context] = value
    save(memory)
