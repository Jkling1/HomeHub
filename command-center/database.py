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
            -- ── IronMind ─────────────────────────────────────────────────
            CREATE TABLE IF NOT EXISTS im_plan (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                date            TEXT UNIQUE NOT NULL,
                priority_1      TEXT,
                priority_2      TEXT,
                priority_3      TEXT,
                training        TEXT,
                nutrition_target TEXT,
                mental_theme    TEXT,
                created_at      TEXT DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS im_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                date            TEXT UNIQUE NOT NULL,
                workout_done    INTEGER DEFAULT 0,
                steps           INTEGER,
                calories        INTEGER,
                protein_g       INTEGER,
                hydration_oz    INTEGER,
                sleep_hours     REAL,
                sleep_quality   INTEGER,
                mood            INTEGER,
                weight_lbs      REAL,
                fast_food       INTEGER DEFAULT 0,
                alcohol         INTEGER DEFAULT 0,
                notes           TEXT,
                updated_at      TEXT DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS im_streaks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT UNIQUE NOT NULL,
                current     INTEGER DEFAULT 0,
                longest     INTEGER DEFAULT 0,
                last_logged TEXT,
                created_at  TEXT DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS im_journal (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                date            TEXT UNIQUE NOT NULL,
                went_right      TEXT,
                cut_corners     TEXT,
                tomorrow_std    TEXT,
                created_at      TEXT DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS im_identity (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                statement   TEXT NOT NULL,
                active      INTEGER DEFAULT 1,
                created_at  TEXT DEFAULT (datetime('now','localtime'))
            );

            -- Seed default streaks
            INSERT OR IGNORE INTO im_streaks (name) VALUES ('workout');
            INSERT OR IGNORE INTO im_streaks (name) VALUES ('clean_eating');
            INSERT OR IGNORE INTO im_streaks (name) VALUES ('no_alcohol');
            INSERT OR IGNORE INTO im_streaks (name) VALUES ('hydration');

            -- Seed starter identity statements
            INSERT OR IGNORE INTO im_identity (statement) VALUES ('I am the type of person who does the hard thing first.');
            INSERT OR IGNORE INTO im_identity (statement) VALUES ('I am the type of person who shows up every single day.');
            INSERT OR IGNORE INTO im_identity (statement) VALUES ('I am the type of person who builds, not just consumes.');

            CREATE TABLE IF NOT EXISTS scenes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL UNIQUE,
                inputs      TEXT NOT NULL,
                trigger_hour INTEGER,
                trigger_dow  TEXT,
                confidence   REAL DEFAULT 0.5,
                auto_learned INTEGER DEFAULT 0,
                times_run    INTEGER DEFAULT 0,
                created_at   TEXT DEFAULT (datetime('now','localtime')),
                last_used    TEXT
            );

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


# ── IronMind helpers ──────────────────────────────────────────────────────────

def im_save_plan(date: str, **fields):
    cols = ", ".join(fields.keys())
    placeholders = ", ".join("?" * len(fields))
    updates = ", ".join(f"{k}=excluded.{k}" for k in fields)
    with get_conn() as conn:
        conn.execute(
            f"INSERT INTO im_plan (date, {cols}) VALUES (?, {placeholders}) "
            f"ON CONFLICT(date) DO UPDATE SET {updates}",
            [date] + list(fields.values()),
        )


def im_get_plan(date: str) -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM im_plan WHERE date=?", (date,)).fetchone()
    return dict(row) if row else {}


def im_upsert_log(date: str, **fields):
    existing = im_get_log(date)
    if existing:
        sets = ", ".join(f"{k}=?" for k in fields)
        sets += ", updated_at=datetime('now','localtime')"
        with get_conn() as conn:
            conn.execute(
                f"UPDATE im_log SET {sets} WHERE date=?",
                list(fields.values()) + [date],
            )
    else:
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" * len(fields))
        with get_conn() as conn:
            conn.execute(
                f"INSERT INTO im_log (date, {cols}) VALUES (?, {placeholders})",
                [date] + list(fields.values()),
            )


def im_get_log(date: str) -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM im_log WHERE date=?", (date,)).fetchone()
    return dict(row) if row else {}


def im_get_logs(limit: int = 30) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM im_log ORDER BY date DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def im_get_streaks() -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM im_streaks ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def im_update_streak(name: str, logged_today: bool, today: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM im_streaks WHERE name=?", (name,)
        ).fetchone()
        if not row:
            return
        s = dict(row)
        last = s.get("last_logged") or ""

        if logged_today:
            from datetime import datetime, timedelta
            yesterday = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
            if last == today:
                return  # Already counted today
            new_current = s["current"] + 1 if last == yesterday else 1
            new_longest = max(s["longest"], new_current)
            conn.execute(
                "UPDATE im_streaks SET current=?, longest=?, last_logged=? WHERE name=?",
                (new_current, new_longest, today, name),
            )
        else:
            from datetime import datetime, timedelta
            yesterday = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
            if last and last < yesterday:
                conn.execute(
                    "UPDATE im_streaks SET current=0 WHERE name=?", (name,)
                )


def im_save_journal(date: str, went_right: str, cut_corners: str, tomorrow_std: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO im_journal (date, went_right, cut_corners, tomorrow_std) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(date) DO UPDATE SET "
            "went_right=excluded.went_right, cut_corners=excluded.cut_corners, "
            "tomorrow_std=excluded.tomorrow_std",
            (date, went_right, cut_corners, tomorrow_std),
        )


def im_get_journal(date: str) -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM im_journal WHERE date=?", (date,)).fetchone()
    return dict(row) if row else {}


def im_get_identity() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM im_identity WHERE active=1 ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


def im_add_identity(statement: str):
    with get_conn() as conn:
        conn.execute("INSERT INTO im_identity (statement) VALUES (?)", (statement,))


def im_remove_identity(identity_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE im_identity SET active=0 WHERE id=?", (identity_id,))


def save_scene(name: str, inputs: list, trigger_hour: int = None,
               trigger_dow: str = None, confidence: float = 0.5, auto_learned: bool = False):
    import json as _json
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO scenes (name, inputs, trigger_hour, trigger_dow, confidence, auto_learned)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                 inputs=excluded.inputs, trigger_hour=excluded.trigger_hour,
                 trigger_dow=excluded.trigger_dow, confidence=excluded.confidence""",
            (name, _json.dumps(inputs), trigger_hour, trigger_dow, confidence, 1 if auto_learned else 0),
        )


def get_scenes() -> list:
    import json as _json
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM scenes ORDER BY times_run DESC, name").fetchall()
    scenes = []
    for r in rows:
        d = dict(r)
        try:
            d["inputs"] = _json.loads(d["inputs"])
        except Exception:
            d["inputs"] = []
        scenes.append(d)
    return scenes


def get_scene(name: str) -> dict:
    import json as _json
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM scenes WHERE lower(name)=lower(?)", (name,)
        ).fetchone()
    if not row:
        return {}
    d = dict(row)
    try:
        d["inputs"] = _json.loads(d["inputs"])
    except Exception:
        d["inputs"] = []
    return d


def increment_scene_run(name: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE scenes SET times_run=times_run+1, last_used=datetime('now','localtime') "
            "WHERE lower(name)=lower(?)",
            (name,),
        )


def delete_scene(name: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM scenes WHERE lower(name)=lower(?)", (name,))


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
