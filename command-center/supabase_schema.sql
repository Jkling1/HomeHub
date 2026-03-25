-- Jordan Smart Hub — Supabase Schema
-- Run this in the Supabase SQL Editor (Dashboard → SQL Editor → New Query)

-- ── Commands (hub activity log) ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS commands (
    id         BIGSERIAL PRIMARY KEY,
    input      TEXT NOT NULL,
    action     TEXT,
    result     TEXT,
    success    BOOLEAN DEFAULT TRUE,
    intent     JSONB,
    ts         TIMESTAMPTZ DEFAULT NOW()
);

-- ── Light state (single row) ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS light_state (
    id         INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    color      TEXT DEFAULT 'white',
    brightness INTEGER DEFAULT 200,
    power      BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
INSERT INTO light_state (id) VALUES (1) ON CONFLICT DO NOTHING;

-- ── Music state (single row) ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS music_state (
    id         INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    track      TEXT DEFAULT '',
    artist     TEXT DEFAULT '',
    playing    BOOLEAN DEFAULT FALSE,
    volume     INTEGER DEFAULT 50,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
INSERT INTO music_state (id) VALUES (1) ON CONFLICT DO NOTHING;

-- ── Preferences ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS preferences (
    key   TEXT PRIMARY KEY,
    value TEXT
);
INSERT INTO preferences (key, value) VALUES ('name', 'Jordan') ON CONFLICT DO NOTHING;
INSERT INTO preferences (key, value) VALUES ('location', 'Rockford, IL') ON CONFLICT DO NOTHING;

-- ── IronMind: Daily Plan ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS im_plan (
    id               BIGSERIAL PRIMARY KEY,
    date             DATE UNIQUE NOT NULL,
    priority_1       TEXT,
    priority_2       TEXT,
    priority_3       TEXT,
    training         TEXT,
    nutrition_target TEXT,
    mental_theme     TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ── IronMind: Daily Log ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS im_log (
    id            BIGSERIAL PRIMARY KEY,
    date          DATE UNIQUE NOT NULL,
    workout_done  BOOLEAN DEFAULT FALSE,
    steps         INTEGER,
    calories      INTEGER,
    protein_g     INTEGER,
    hydration_oz  INTEGER,
    sleep_hours   NUMERIC(4,2),
    sleep_quality INTEGER,
    mood          INTEGER,
    weight_lbs    NUMERIC(5,2),
    fast_food     BOOLEAN DEFAULT FALSE,
    alcohol       BOOLEAN DEFAULT FALSE,
    notes         TEXT,
    score         NUMERIC(4,2),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- ── IronMind: Streaks ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS im_streaks (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    current     INTEGER DEFAULT 0,
    longest     INTEGER DEFAULT 0,
    last_logged DATE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
INSERT INTO im_streaks (name) VALUES ('workout')     ON CONFLICT DO NOTHING;
INSERT INTO im_streaks (name) VALUES ('clean_eating') ON CONFLICT DO NOTHING;
INSERT INTO im_streaks (name) VALUES ('no_alcohol')   ON CONFLICT DO NOTHING;
INSERT INTO im_streaks (name) VALUES ('hydration')    ON CONFLICT DO NOTHING;

-- ── IronMind: Journal ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS im_journal (
    id           BIGSERIAL PRIMARY KEY,
    date         DATE UNIQUE NOT NULL,
    went_right   TEXT,
    cut_corners  TEXT,
    tomorrow_std TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- ── IronMind: Identity Statements ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS im_identity (
    id         BIGSERIAL PRIMARY KEY,
    statement  TEXT NOT NULL,
    active     BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
INSERT INTO im_identity (statement) VALUES ('I am the type of person who does the hard thing first.') ON CONFLICT DO NOTHING;
INSERT INTO im_identity (statement) VALUES ('I am the type of person who shows up every single day.') ON CONFLICT DO NOTHING;
INSERT INTO im_identity (statement) VALUES ('I am the type of person who builds, not just consumes.') ON CONFLICT DO NOTHING;

-- ── Scenes ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scenes (
    id           BIGSERIAL PRIMARY KEY,
    name         TEXT UNIQUE NOT NULL,
    inputs       JSONB NOT NULL DEFAULT '[]',
    trigger_hour INTEGER,
    trigger_dow  TEXT,
    confidence   NUMERIC(4,3) DEFAULT 0.5,
    auto_learned BOOLEAN DEFAULT FALSE,
    times_run    INTEGER DEFAULT 0,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    last_used    TIMESTAMPTZ
);

-- ── EVOLVE Protocol Logs ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS evolve_logs (
    id          BIGSERIAL PRIMARY KEY,
    date        DATE UNIQUE NOT NULL,
    evaluation  JSONB,
    health      JSONB,
    proposals   JSONB,
    feature     JSONB,
    duration_s  NUMERIC(6,2),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── Enable Row Level Security (RLS) ──────────────────────────────────────────
-- For now, allow all operations (you're the only user).
-- When auth is added, these policies will be tightened.
ALTER TABLE commands    ENABLE ROW LEVEL SECURITY;
ALTER TABLE light_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE music_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE im_plan     ENABLE ROW LEVEL SECURITY;
ALTER TABLE im_log      ENABLE ROW LEVEL SECURITY;
ALTER TABLE im_streaks  ENABLE ROW LEVEL SECURITY;
ALTER TABLE im_journal  ENABLE ROW LEVEL SECURITY;
ALTER TABLE im_identity ENABLE ROW LEVEL SECURITY;
ALTER TABLE scenes      ENABLE ROW LEVEL SECURITY;
ALTER TABLE evolve_logs ENABLE ROW LEVEL SECURITY;

-- Allow service role (your server) full access
CREATE POLICY "service_full_access" ON commands    FOR ALL USING (true);
CREATE POLICY "service_full_access" ON light_state FOR ALL USING (true);
CREATE POLICY "service_full_access" ON music_state FOR ALL USING (true);
CREATE POLICY "service_full_access" ON preferences FOR ALL USING (true);
CREATE POLICY "service_full_access" ON im_plan     FOR ALL USING (true);
CREATE POLICY "service_full_access" ON im_log      FOR ALL USING (true);
CREATE POLICY "service_full_access" ON im_streaks  FOR ALL USING (true);
CREATE POLICY "service_full_access" ON im_journal  FOR ALL USING (true);
CREATE POLICY "service_full_access" ON im_identity FOR ALL USING (true);
CREATE POLICY "service_full_access" ON scenes      FOR ALL USING (true);
CREATE POLICY "service_full_access" ON evolve_logs FOR ALL USING (true);

-- Done. Your schema is ready.
