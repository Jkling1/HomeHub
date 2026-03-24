#!/usr/bin/env python3
"""
Music Mood Lighting Agent
Polls current track every 15 seconds. When the song changes,
Claude picks the perfect light color and sets it automatically.
"""

import json
import time
from agents.base import *

AGENT = "music_mood"
STATE_KEY = "music_mood_last_track"
MOOD_COOLDOWN = 30  # seconds between light changes

# Map of keywords → instant color (fast path, no API call needed)
FAST_MAP = {
    # Energy keywords
    "trap": ("red", 220), "drill": ("red", 254), "metal": ("red", 254),
    "rage": ("red", 254), "workout": ("red", 254), "hype": ("red", 220),
    # Focus/lo-fi keywords
    "lofi": ("cool", 160), "lo-fi": ("cool", 160), "lo fi": ("cool", 160),
    "study": ("cool", 160), "focus": ("cool", 160), "ambient": ("blue", 140),
    "classical": ("cool", 180), "piano": ("cool", 160), "instrumental": ("cool", 160),
    # Chill/evening keywords
    "chill": ("blue", 150), "relax": ("purple", 140), "sleep": ("purple", 80),
    "jazz": ("warm", 160), "soul": ("warm", 180), "r&b": ("warm", 180),
    "rnb": ("warm", 180), "blues": ("blue", 150),
    # Happy/energetic
    "pop": ("cyan", 200), "happy": ("yellow", 200), "dance": ("pink", 220),
    "edm": ("cyan", 254), "house": ("cyan", 220), "disco": ("pink", 254),
    # Morning/warmup
    "morning": ("warm", 180), "sunrise": ("warm", 160), "acoustic": ("warm", 200),
    "country": ("warm", 180),
}


def fast_color_for_track(track: str, artist: str) -> tuple | None:
    """Try to determine color from keywords without calling Claude."""
    combined = (track + " " + artist).lower()
    for keyword, (color, bri) in FAST_MAP.items():
        if keyword in combined:
            return color, bri
    return None


def claude_color_for_track(track: str, artist: str, current_color: str) -> tuple:
    """Ask Claude to pick the ideal light color for this track."""
    prompt = f"""Track: "{track}" by {artist}
Current lights: {current_color}

Pick the best Philips Hue light color and brightness for this music.
Return ONLY valid JSON: {{"color": "<red|orange|yellow|green|cyan|blue|purple|pink|warm|white|cool>", "brightness": <0-254>, "reason": "<5 words>"}}

Color guide:
- red: high energy, workout, intense
- orange/yellow: happy, warm, upbeat
- cool/blue: focus, lo-fi, study, calm
- purple: chill, late night, vibe
- warm: jazz, soul, acoustic, cozy
- pink: dance, pop, fun
- cyan: EDM, electronic, energetic focus
- white: neutral, background, ambient"""

    raw = claude(prompt, max_tokens=80, model="claude-haiku-4-5-20251001")
    try:
        # Extract JSON
        if "{" in raw:
            raw = raw[raw.index("{"):raw.rindex("}")+1]
        data = json.loads(raw)
        return data.get("color", "cool"), int(data.get("brightness", 160))
    except Exception:
        return "cool", 160


def set_mood_lights(color: str, brightness: int, track: str, artist: str):
    """Set lights and log the mood change."""
    try:
        result = hub_set_lights(color, brightness)
        log(AGENT, f"🎵 {track[:30]} → {color} @ {brightness}  ({result[:40]})")
    except Exception as e:
        log(AGENT, f"Light set error: {e}")


def run():
    """Main loop — called by launchd every 15 seconds."""
    try:
        status = hub_status()
    except Exception as e:
        log(AGENT, f"Hub unreachable: {e}")
        return

    music = status.get("music", {})
    if not music.get("playing"):
        return  # Nothing playing, leave lights alone

    track  = music.get("track", "")
    artist = music.get("artist", "")

    if not track:
        return

    # Check if track changed
    state = load_state()
    last_track = state.get(STATE_KEY, "")

    if track == last_track:
        return  # Same track, no change needed

    # Track changed — determine mood
    log(AGENT, f"Track change: {track} by {artist}")

    # Respect cooldown to avoid rapid flashing
    last_change = state.get(f"{STATE_KEY}_ts", 0)
    if time.time() - last_change < MOOD_COOLDOWN:
        # Still update the last track so we don't keep checking
        state[STATE_KEY] = track
        save_state(state)
        return

    # Try fast path first
    result = fast_color_for_track(track, artist)

    if result:
        color, brightness = result
        log(AGENT, f"Fast match → {color} @ {brightness}")
    else:
        # Call Claude for unknown tracks
        current_color = status.get("lights", {}).get("color", "white")
        color, brightness = claude_color_for_track(track, artist, current_color)
        log(AGENT, f"Claude match → {color} @ {brightness}")

    set_mood_lights(color, brightness, track, artist)

    # Update state
    state[STATE_KEY] = track
    state[f"{STATE_KEY}_ts"] = time.time()
    save_state(state)


if __name__ == "__main__":
    run()
