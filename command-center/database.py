#!/usr/bin/env python3
"""
Jordan Smart Hub — Database layer.

Dual-mode: uses Supabase if SUPABASE_URL + SUPABASE_KEY are set in .env,
otherwise falls back to local SQLite. Zero changes needed elsewhere.
"""

import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

# ── Load env ───────────────────────────────────────────────────────────────────
ENV_PATH = Path(__file__).parent / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
USE_SUPABASE = bool(SUPABASE_URL and SUPABASE_KEY)

DB_PATH = Path(__file__).parent / "hub.db"

# ── Supabase client (lazy-init) ───────────────────────────────────────────────
_supa = None

def _sb():
    global _supa
    if _supa is None:
        from supabase import create_client
        _supa = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supa


# ── SQLite helpers ─────────────────────────────────────────────────────────────
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    if USE_SUPABASE:
        print("[db] Using Supabase — run supabase_schema.sql if tables don't exist yet.")
        return
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
            INSERT OR IGNORE INTO im_streaks (name) VALUES ('workout');
            INSERT OR IGNORE INTO im_streaks (name) VALUES ('clean_eating');
            INSERT OR IGNORE INTO im_streaks (name) VALUES ('no_alcohol');
            INSERT OR IGNORE INTO im_streaks (name) VALUES ('hydration');
            CREATE TABLE IF NOT EXISTS ironman_training (
                date             TEXT PRIMARY KEY,
                weight           REAL,
                sleep_hours      REAL,
                resting_hr       INTEGER,
                hrv              REAL,
                calories_burned  INTEGER,
                active_calories  INTEGER,
                steps            INTEGER,
                run_distance     REAL,
                cycle_distance   REAL,
                swim_distance    REAL,
                workouts         TEXT,
                effort_level     INTEGER,
                fatigue_level    INTEGER,
                notes            TEXT,
                protocol         TEXT,
                generated_at     TEXT
            );
            CREATE TABLE IF NOT EXISTS rocks (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                date       TEXT NOT NULL,
                size       TEXT NOT NULL,
                title      TEXT NOT NULL,
                category   TEXT DEFAULT 'training',
                status     TEXT DEFAULT 'incomplete',
                sort_order INTEGER DEFAULT 0,
                notes      TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                updated_at TEXT DEFAULT (datetime('now','localtime'))
            );
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


# ══════════════════════════════════════════════════════════════════════════════
# COMMANDS
# ══════════════════════════════════════════════════════════════════════════════

def log_command(input_text: str, action: str, result: str, success: bool = True):
    if USE_SUPABASE:
        _sb().table("commands").insert({
            "input": input_text,
            "action": action,
            "result": result[:500],
            "success": success,
        }).execute()
    else:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO commands (input, action, result, success) VALUES (?, ?, ?, ?)",
                (input_text, action, result[:500], 1 if success else 0)
            )


def get_history(limit: int = 30):
    if USE_SUPABASE:
        resp = _sb().table("commands").select("*").order("id", desc=True).limit(limit).execute()
        return resp.data or []
    else:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM commands ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════════════════
# LIGHT STATE
# ══════════════════════════════════════════════════════════════════════════════

def update_light_state(color: str, brightness: int = 200, power: bool = True):
    if USE_SUPABASE:
        _sb().table("light_state").upsert({
            "id": 1, "color": color, "brightness": brightness, "power": power
        }).execute()
    else:
        with get_conn() as conn:
            conn.execute(
                """INSERT INTO light_state (id, color, brightness, power, updated_at)
                   VALUES (1, ?, ?, ?, datetime('now','localtime'))
                   ON CONFLICT(id) DO UPDATE SET
                     color=excluded.color, brightness=excluded.brightness,
                     power=excluded.power, updated_at=excluded.updated_at""",
                (color, brightness, 1 if power else 0)
            )


def get_light_state():
    if USE_SUPABASE:
        resp = _sb().table("light_state").select("*").eq("id", 1).single().execute()
        return resp.data or {}
    else:
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM light_state WHERE id=1").fetchone()
        return dict(row) if row else {}


# ══════════════════════════════════════════════════════════════════════════════
# MUSIC STATE
# ══════════════════════════════════════════════════════════════════════════════

def update_music_state(track: str = "", artist: str = "", playing: bool = False, volume: int = 50):
    if USE_SUPABASE:
        _sb().table("music_state").upsert({
            "id": 1, "track": track, "artist": artist, "playing": playing, "volume": volume
        }).execute()
    else:
        with get_conn() as conn:
            conn.execute(
                """INSERT INTO music_state (id, track, artist, playing, volume, updated_at)
                   VALUES (1, ?, ?, ?, ?, datetime('now','localtime'))
                   ON CONFLICT(id) DO UPDATE SET
                     track=excluded.track, artist=excluded.artist,
                     playing=excluded.playing, volume=excluded.volume,
                     updated_at=excluded.updated_at""",
                (track, artist, 1 if playing else 0, volume)
            )


def get_music_state():
    if USE_SUPABASE:
        resp = _sb().table("music_state").select("*").eq("id", 1).single().execute()
        return resp.data or {}
    else:
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM music_state WHERE id=1").fetchone()
        return dict(row) if row else {}


# ══════════════════════════════════════════════════════════════════════════════
# IRONMIND
# ══════════════════════════════════════════════════════════════════════════════

def im_save_plan(date: str, **fields):
    if USE_SUPABASE:
        _sb().table("im_plan").upsert({"date": date, **fields}).execute()
    else:
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
    if USE_SUPABASE:
        resp = _sb().table("im_plan").select("*").eq("date", date).single().execute()
        return resp.data or {}
    else:
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM im_plan WHERE date=?", (date,)).fetchone()
        return dict(row) if row else {}


def im_upsert_log(date: str, **fields):
    if USE_SUPABASE:
        _sb().table("im_log").upsert({"date": date, **fields}).execute()
    else:
        existing = im_get_log(date)
        if existing:
            sets = ", ".join(f"{k}=?" for k in fields)
            sets += ", updated_at=datetime('now','localtime')"
            with get_conn() as conn:
                conn.execute(f"UPDATE im_log SET {sets} WHERE date=?", list(fields.values()) + [date])
        else:
            cols = ", ".join(fields.keys())
            placeholders = ", ".join("?" * len(fields))
            with get_conn() as conn:
                conn.execute(f"INSERT INTO im_log (date, {cols}) VALUES (?, {placeholders})", [date] + list(fields.values()))


def im_get_log(date: str) -> dict:
    if USE_SUPABASE:
        resp = _sb().table("im_log").select("*").eq("date", date).single().execute()
        return resp.data or {}
    else:
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM im_log WHERE date=?", (date,)).fetchone()
        return dict(row) if row else {}


def im_get_logs(limit: int = 30) -> list:
    if USE_SUPABASE:
        resp = _sb().table("im_log").select("*").order("date", desc=True).limit(limit).execute()
        return resp.data or []
    else:
        with get_conn() as conn:
            rows = conn.execute("SELECT * FROM im_log ORDER BY date DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]


def im_get_streaks() -> list:
    if USE_SUPABASE:
        resp = _sb().table("im_streaks").select("*").order("name").execute()
        return resp.data or []
    else:
        with get_conn() as conn:
            rows = conn.execute("SELECT * FROM im_streaks ORDER BY name").fetchall()
        return [dict(r) for r in rows]


def im_update_streak(name: str, logged_today: bool, today: str):
    if USE_SUPABASE:
        resp = _sb().table("im_streaks").select("*").eq("name", name).single().execute()
        s = resp.data
        if not s:
            return
        last = s.get("last_logged") or ""
        if logged_today:
            yesterday = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
            if last == today:
                return
            new_current = s["current"] + 1 if last == yesterday else 1
            new_longest = max(s["longest"], new_current)
            _sb().table("im_streaks").update({
                "current": new_current, "longest": new_longest, "last_logged": today
            }).eq("name", name).execute()
        else:
            yesterday = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
            if last and last < yesterday:
                _sb().table("im_streaks").update({"current": 0}).eq("name", name).execute()
    else:
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM im_streaks WHERE name=?", (name,)).fetchone()
            if not row:
                return
            s = dict(row)
            last = s.get("last_logged") or ""
            if logged_today:
                yesterday = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
                if last == today:
                    return
                new_current = s["current"] + 1 if last == yesterday else 1
                new_longest = max(s["longest"], new_current)
                conn.execute("UPDATE im_streaks SET current=?, longest=?, last_logged=? WHERE name=?",
                             (new_current, new_longest, today, name))
            else:
                yesterday = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
                if last and last < yesterday:
                    conn.execute("UPDATE im_streaks SET current=0 WHERE name=?", (name,))


def im_save_journal(date: str, went_right: str, cut_corners: str, tomorrow_std: str):
    if USE_SUPABASE:
        _sb().table("im_journal").upsert({
            "date": date, "went_right": went_right,
            "cut_corners": cut_corners, "tomorrow_std": tomorrow_std
        }).execute()
    else:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO im_journal (date, went_right, cut_corners, tomorrow_std) "
                "VALUES (?, ?, ?, ?) ON CONFLICT(date) DO UPDATE SET "
                "went_right=excluded.went_right, cut_corners=excluded.cut_corners, "
                "tomorrow_std=excluded.tomorrow_std",
                (date, went_right, cut_corners, tomorrow_std),
            )


def im_get_journal(date: str) -> dict:
    if USE_SUPABASE:
        resp = _sb().table("im_journal").select("*").eq("date", date).single().execute()
        return resp.data or {}
    else:
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM im_journal WHERE date=?", (date,)).fetchone()
        return dict(row) if row else {}


def im_get_identity() -> list:
    if USE_SUPABASE:
        resp = _sb().table("im_identity").select("*").eq("active", True).order("id").execute()
        return resp.data or []
    else:
        with get_conn() as conn:
            rows = conn.execute("SELECT * FROM im_identity WHERE active=1 ORDER BY id").fetchall()
        return [dict(r) for r in rows]


def im_add_identity(statement: str):
    if USE_SUPABASE:
        _sb().table("im_identity").insert({"statement": statement}).execute()
    else:
        with get_conn() as conn:
            exists = conn.execute(
                "SELECT id FROM im_identity WHERE statement=? AND active=1", (statement,)
            ).fetchone()
            if not exists:
                conn.execute("INSERT INTO im_identity (statement) VALUES (?)", (statement,))


def im_remove_identity(identity_id: int):
    if USE_SUPABASE:
        _sb().table("im_identity").update({"active": False}).eq("id", identity_id).execute()
    else:
        with get_conn() as conn:
            conn.execute("UPDATE im_identity SET active=0 WHERE id=?", (identity_id,))


# ══════════════════════════════════════════════════════════════════════════════
# IRONMAN TRAINING
# ══════════════════════════════════════════════════════════════════════════════

def ironman_save(date: str, protocol: str = None, **fields):
    cols = ["date"]
    vals = [date]
    for k, v in fields.items():
        if v is not None:
            cols.append(k)
            vals.append(v)
    if protocol is not None:
        cols += ["protocol", "generated_at"]
        vals += [protocol, datetime.now().strftime("%Y-%m-%d %H:%M:%S")]

    placeholders = ",".join("?" * len(vals))
    col_str = ",".join(cols)
    updates = ",".join(f"{c}=excluded.{c}" for c in cols if c != "date")

    with get_conn() as conn:
        conn.execute(
            f"INSERT INTO ironman_training ({col_str}) VALUES ({placeholders}) "
            f"ON CONFLICT(date) DO UPDATE SET {updates}",
            vals,
        )


def ironman_get(date: str) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM ironman_training WHERE date=?", (date,)
        ).fetchone()
        if row:
            return dict(row)
    return {}


def ironman_get_history(limit: int = 14) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM ironman_training ORDER BY date DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════════════════
# ROCKS
# ══════════════════════════════════════════════════════════════════════════════

def rocks_get(date: str) -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM rocks WHERE date=? ORDER BY size, sort_order, id", (date,)
        ).fetchall()
    result = {"big": [], "medium": [], "small": []}
    for r in rows:
        d = dict(r)
        result.get(d["size"], result["small"]).append(d)
    return result


def rock_create(date: str, size: str, title: str, category: str = "training", sort_order: int = 0) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO rocks (date, size, title, category, sort_order) VALUES (?, ?, ?, ?, ?)",
            (date, size, title, category, sort_order),
        )
        return cur.lastrowid


def rock_update(rock_id: int, **fields):
    if not fields:
        return
    allowed = {"status", "title", "category", "notes", "sort_order"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE rocks SET {sets}, updated_at=datetime('now','localtime') WHERE id=?",
            list(fields.values()) + [rock_id],
        )


def rock_delete(rock_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM rocks WHERE id=?", (rock_id,))


def rocks_get_week(start_date: str, days: int = 7) -> list:
    """Return daily completion stats for calendar view."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT date, size, status FROM rocks WHERE date >= ? ORDER BY date",
            (start_date,),
        ).fetchall()
    from collections import defaultdict
    daily = defaultdict(lambda: {"total": 0, "complete": 0, "big_done": False})
    for r in rows:
        d = dict(r)
        daily[d["date"]]["total"] += 1
        if d["status"] == "complete":
            daily[d["date"]]["complete"] += 1
            if d["size"] == "big":
                daily[d["date"]]["big_done"] = True
    return [{"date": k, **v} for k, v in sorted(daily.items())]


# ══════════════════════════════════════════════════════════════════════════════
# SCENES
# ══════════════════════════════════════════════════════════════════════════════

def save_scene(name: str, inputs: list, trigger_hour: int = None,
               trigger_dow: str = None, confidence: float = 0.5, auto_learned: bool = False):
    if USE_SUPABASE:
        _sb().table("scenes").upsert({
            "name": name, "inputs": inputs, "trigger_hour": trigger_hour,
            "trigger_dow": trigger_dow, "confidence": confidence, "auto_learned": auto_learned
        }).execute()
    else:
        with get_conn() as conn:
            conn.execute(
                """INSERT INTO scenes (name, inputs, trigger_hour, trigger_dow, confidence, auto_learned)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET
                     inputs=excluded.inputs, trigger_hour=excluded.trigger_hour,
                     trigger_dow=excluded.trigger_dow, confidence=excluded.confidence""",
                (name, json.dumps(inputs), trigger_hour, trigger_dow, confidence, 1 if auto_learned else 0),
            )


def get_scenes() -> list:
    if USE_SUPABASE:
        resp = _sb().table("scenes").select("*").order("times_run", desc=True).execute()
        return resp.data or []
    else:
        with get_conn() as conn:
            rows = conn.execute("SELECT * FROM scenes ORDER BY times_run DESC, name").fetchall()
        scenes = []
        for r in rows:
            d = dict(r)
            try:
                d["inputs"] = json.loads(d["inputs"])
            except Exception:
                d["inputs"] = []
            scenes.append(d)
        return scenes


def get_scene(name: str) -> dict:
    if USE_SUPABASE:
        resp = _sb().table("scenes").select("*").ilike("name", name).single().execute()
        return resp.data or {}
    else:
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM scenes WHERE lower(name)=lower(?)", (name,)).fetchone()
        if not row:
            return {}
        d = dict(row)
        try:
            d["inputs"] = json.loads(d["inputs"])
        except Exception:
            d["inputs"] = []
        return d


def increment_scene_run(name: str):
    if USE_SUPABASE:
        existing = get_scene(name)
        if existing:
            _sb().table("scenes").update({
                "times_run": existing.get("times_run", 0) + 1,
                "last_used": datetime.now().isoformat()
            }).ilike("name", name).execute()
    else:
        with get_conn() as conn:
            conn.execute(
                "UPDATE scenes SET times_run=times_run+1, last_used=datetime('now','localtime') "
                "WHERE lower(name)=lower(?)", (name,)
            )


def delete_scene(name: str):
    if USE_SUPABASE:
        _sb().table("scenes").delete().ilike("name", name).execute()
    else:
        with get_conn() as conn:
            conn.execute("DELETE FROM scenes WHERE lower(name)=lower(?)", (name,))


# ══════════════════════════════════════════════════════════════════════════════
# STATUS
# ══════════════════════════════════════════════════════════════════════════════

def db_mode() -> str:
    return "supabase" if USE_SUPABASE else "sqlite"


if __name__ == "__main__":
    init_db()
    print(f"Database mode: {db_mode()}")
    if USE_SUPABASE:
        print(f"Supabase URL: {SUPABASE_URL}")
    else:
        print(f"SQLite path: {DB_PATH}")
