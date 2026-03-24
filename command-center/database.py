#!/usr/bin/env python3
"""SQLite database for Jordan Smart Hub."""

import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "hub.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS commands (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                input     TEXT NOT NULL,
                action    TEXT,
                result    TEXT,
                success   INTEGER DEFAULT 1,
                ts        TEXT DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS light_state (
                id         INTEGER PRIMARY KEY CHECK (id = 1),
                color      TEXT DEFAULT 'white',
                brightness INTEGER DEFAULT 200,
                power      INTEGER DEFAULT 1,
                updated_at TEXT DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS music_state (
                id      INTEGER PRIMARY KEY CHECK (id = 1),
                track   TEXT DEFAULT '',
                artist  TEXT DEFAULT '',
                playing INTEGER DEFAULT 0,
                volume  INTEGER DEFAULT 50,
                updated_at TEXT DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS preferences (
                key   TEXT PRIMARY KEY,
                value TEXT
            );

            INSERT OR IGNORE INTO light_state (id) VALUES (1);
            INSERT OR IGNORE INTO music_state (id) VALUES (1);
            INSERT OR IGNORE INTO preferences (key, value) VALUES ('name', 'Jordan');
            INSERT OR IGNORE INTO preferences (key, value) VALUES ('location', 'Rockford, IL');
        """)


def log_command(input_text: str, action: str, result: str, success: bool = True):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO commands (input, action, result, success) VALUES (?, ?, ?, ?)",
            (input_text, action, result[:500], 1 if success else 0)
        )


def get_history(limit: int = 30):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM commands ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def update_light_state(color: str, brightness: int = 200, power: bool = True):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO light_state (id, color, brightness, power, updated_at)
               VALUES (1, ?, ?, ?, datetime('now','localtime'))
               ON CONFLICT(id) DO UPDATE SET
                 color=excluded.color,
                 brightness=excluded.brightness,
                 power=excluded.power,
                 updated_at=excluded.updated_at""",
            (color, brightness, 1 if power else 0)
        )


def get_light_state():
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM light_state WHERE id=1").fetchone()
    return dict(row) if row else {}


def update_music_state(track: str = "", artist: str = "", playing: bool = False, volume: int = 50):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO music_state (id, track, artist, playing, volume, updated_at)
               VALUES (1, ?, ?, ?, ?, datetime('now','localtime'))
               ON CONFLICT(id) DO UPDATE SET
                 track=excluded.track,
                 artist=excluded.artist,
                 playing=excluded.playing,
                 volume=excluded.volume,
                 updated_at=excluded.updated_at""",
            (track, artist, 1 if playing else 0, volume)
        )


def get_music_state():
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM music_state WHERE id=1").fetchone()
    return dict(row) if row else {}


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
