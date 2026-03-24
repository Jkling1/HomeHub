#!/usr/bin/env python3
"""
Opens 10 curated lo-fi / focus tracks in Apple Music one by one.
For each track: Music app opens it → click 'Add to Library' → next.
Takes about 60 seconds total.
"""

import subprocess, time

TRACKS = [
    # (Apple Music URL, description)
    ("https://music.apple.com/us/album/lofi/1494204561?i=1494204561",   "Lofi — Acey"),
    ("https://music.apple.com/us/album/lofi-hip-hop/1254274451?i=1254274541", "LoFi Hip Hop — FrankJavCee"),
    ("https://music.apple.com/us/album/ambient-focus-music/1774538009?i=1774538010", "Ambient Focus Music — WorkFlow Music"),
    ("https://music.apple.com/us/album/focus-music/1246734501?i=1246734502", "Focus Music (Alpha Waves)"),
    ("https://music.apple.com/us/album/beat-of-a-retro-cafe/1883935584?i=1883935585", "Beat of a Retro Cafe — FM STAR"),
    ("https://music.apple.com/us/album/the-sound-of-rain-on-the-window/1883935584?i=1883935588", "Sound of Rain — FM STAR"),
    ("https://music.apple.com/us/album/ambient-focus/1576593417?i=1576593418", "Ambient Focus — Sleep Fruits Music"),
    ("https://music.apple.com/us/album/focus/1092948801?i=1092948802", "Focus — Deep Study"),
    ("https://music.apple.com/us/album/lofi/1493755221?i=1493755222", "Lofi — Ponder"),
    ("https://music.apple.com/us/album/lofi/1500972633?i=1500972634", "Lofi — Domknowz"),
]

print("Opening 10 lo-fi / focus tracks in Apple Music.")
print("For each one: click 'Add' or '+ Add to Library' in the Music app.\n")

for i, (url, desc) in enumerate(TRACKS, 1):
    print(f"[{i}/10] {desc}")
    subprocess.run(["open", url])
    time.sleep(4)  # Give Music app time to load each track page

print("\nDone! All 10 tracks opened. Once added to library, Adler can play them automatically.")
print("Test it: tell hub 'play lofi' or 'play ambient focus'")
