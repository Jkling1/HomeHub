#!/usr/bin/env python3
"""
Apple Music controller via AppleScript.
Usage: python3 music.py <command> [args]
Commands: play <query>, pause, resume, skip, back, volume <0-100>, status, stop
"""

import subprocess
import sys


def run(script):
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True
    )
    return result.stdout.strip(), result.returncode


def status():
    state, _ = run('tell application "Music" to return player state as string')
    if state == "stopped" or state == "":
        return "Nothing playing."
    try:
        track, _ = run('tell application "Music" to return name of current track')
        artist, _ = run('tell application "Music" to return artist of current track')
        vol, _ = run('tell application "Music" to return sound volume')
        return f"{'▶' if state == 'playing' else '⏸'} {track} — {artist} (vol: {vol}%)"
    except Exception:
        return f"Player is {state}."


def play_query(query):
    # Search library first
    search_script = f'''
    tell application "Music"
        set results to search playlist "Library" for "{query}"
        if length of results > 0 then
            play item 1 of results
            return (name of current track & "|||" & artist of current track)
        else
            return "NOT_FOUND"
        end if
    end tell
    '''
    out, code = run(search_script)
    if "NOT_FOUND" in out or code != 0:
        return None, None
    parts = out.split("|||")
    track = parts[0] if len(parts) > 0 else query
    artist = parts[1] if len(parts) > 1 else ""
    return track, artist


def pause():
    run('tell application "Music" to pause')


def resume():
    run('tell application "Music" to play')


def skip():
    run('tell application "Music" to next track')
    track, _ = run('tell application "Music" to return name of current track')
    artist, _ = run('tell application "Music" to return artist of current track')
    return track, artist


def back():
    run('tell application "Music" to previous track')
    track, _ = run('tell application "Music" to return name of current track')
    artist, _ = run('tell application "Music" to return artist of current track')
    return track, artist


def set_volume(level):
    run(f'tell application "Music" to set sound volume to {level}')


def stop():
    run('tell application "Music" to stop')


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(status())
        sys.exit(0)

    cmd = sys.argv[1].lower()

    if cmd == "status":
        print(status())

    elif cmd == "play":
        query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        if not query:
            resume()
            print("▶ Resumed")
        else:
            track, artist = play_query(query)
            if track:
                print(f"▶ {track} — {artist}")
            else:
                print(f"NOT_FOUND:{query}")

    elif cmd == "pause":
        pause()
        print("⏸ Paused")

    elif cmd == "resume":
        resume()
        print("▶ Resumed")

    elif cmd == "skip":
        track, artist = skip()
        print(f"⏭ {track} — {artist}")

    elif cmd == "back":
        track, artist = back()
        print(f"⏮ {track} — {artist}")

    elif cmd == "stop":
        stop()
        print("⏹ Stopped")

    elif cmd == "volume":
        level = int(sys.argv[2]) if len(sys.argv) > 2 else 50
        level = max(0, min(100, level))
        set_volume(level)
        print(f"🔊 Volume set to {level}%")

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
