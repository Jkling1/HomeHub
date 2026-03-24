#!/usr/bin/env python3
"""
Centralized Apple Music controller via AppleScript.
All music commands funnel through here — used by server.py, hub.py, and Telegram.
"""

import subprocess


def _run(script: str) -> str:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=8)
    return r.stdout.strip()


def get_status() -> dict:
    """Returns current player state as a dict."""
    script = '''
    tell application "Music"
        if player state is stopped then
            return "stopped|||||||"
        end if
        set s to player state as string
        set t to ""
        set ar to ""
        set v to sound volume as string
        try
            set t to name of current track
            set ar to artist of current track
        end try
        return s & "|||" & t & "|||" & ar & "|||" & v
    end tell
    '''
    out = _run(script)
    parts = out.split("|||")
    if len(parts) < 4:
        return {"playing": False, "track": "", "artist": "", "volume": 50}
    state, track, artist, vol = parts[0], parts[1], parts[2], parts[3]
    return {
        "playing": state == "playing",
        "track": track,
        "artist": artist,
        "volume": int(vol) if vol.isdigit() else 50,
    }


def play_query(query: str) -> dict:
    """Search library for query and play first match. Returns track info or error."""
    safe = query.replace('"', "'")
    script = f'''
    tell application "Music"
        activate
        set q to "{safe}"
        set allTracks to tracks of playlist "Library"
        -- Case-insensitive search: name or artist contains query
        repeat with t in allTracks
            set tname to name of t
            set tart to artist of t
            set lname to do shell script "echo " & quoted form of tname & " | tr '[:upper:]' '[:lower:]'"
            set lq to do shell script "echo " & quoted form of q & " | tr '[:upper:]' '[:lower:]'"
            if lname contains lq or tart contains q then
                play t
                set v to sound volume as string
                return (name of t) & "|||" & (artist of t) & "|||" & v
            end if
        end repeat
        return "NOT_FOUND"
    end tell
    '''
    out = _run(script)
    if "NOT_FOUND" in out or not out:
        return {"ok": False, "error": f"'{query}' not found in library"}
    parts = out.split("|||")
    return {
        "ok": True,
        "track": parts[0].strip(),
        "artist": parts[1].strip() if len(parts) > 1 else "",
        "volume": int(parts[2].strip()) if len(parts) > 2 and parts[2].strip().isdigit() else 50,
    }


def pause() -> dict:
    _run('tell application "Music" to pause')
    s = get_status()
    return {"ok": True, "track": s["track"], "artist": s["artist"]}


def resume() -> dict:
    _run('tell application "Music" to play')
    s = get_status()
    return {"ok": True, "track": s["track"], "artist": s["artist"]}


def skip() -> dict:
    out = _run('''
    tell application "Music"
        next track
        set t to ""
        set ar to ""
        try
            set t to name of current track
            set ar to artist of current track
        end try
        return t & "|||" & ar
    end tell
    ''')
    parts = out.split("|||")
    return {"ok": True, "track": parts[0].strip(), "artist": parts[1].strip() if len(parts) > 1 else ""}


def back() -> dict:
    out = _run('''
    tell application "Music"
        previous track
        set t to ""
        set ar to ""
        try
            set t to name of current track
            set ar to artist of current track
        end try
        return t & "|||" & ar
    end tell
    ''')
    parts = out.split("|||")
    return {"ok": True, "track": parts[0].strip(), "artist": parts[1].strip() if len(parts) > 1 else ""}


def set_volume(level: int) -> dict:
    level = max(0, min(100, level))
    _run(f'tell application "Music" to set sound volume to {level}')
    return {"ok": True, "volume": level}


def stop() -> dict:
    _run('tell application "Music" to stop')
    return {"ok": True}


def handle(cmd: dict) -> str:
    """
    Main dispatch — takes a parsed music command dict and returns a human-readable result string.
    cmd: { command: play|pause|resume|skip|back|stop|volume, query: str, volume: int }
    """
    command = cmd.get("command", "play").lower()
    query   = cmd.get("query", "")
    volume  = cmd.get("volume")

    if volume is not None:
        r = set_volume(int(volume))
        return f"🔊 Volume → {r['volume']}%"

    if command == "play" and query:
        r = play_query(query)
        if r["ok"]:
            return f"▶️ {r['track']} — {r['artist']}"
        return f"🎵 {r['error']}. Add it in the Music app first."

    if command == "play":
        r = resume()
        return f"▶️ {r['track']} — {r['artist']}" if r["track"] else "▶️ Resumed"

    if command in ("pause", "stop"):
        r = pause()
        return f"⏸ Paused — {r['track']}" if r["track"] else "⏸ Paused"

    if command == "resume":
        r = resume()
        return f"▶️ {r['track']} — {r['artist']}" if r["track"] else "▶️ Resumed"

    if command == "skip":
        r = skip()
        return f"⏭ {r['track']} — {r['artist']}" if r["track"] else "⏭ Skipped"

    if command == "back":
        r = back()
        return f"⏮ {r['track']} — {r['artist']}" if r["track"] else "⏮ Previous track"

    return "🎵 Unknown music command"
