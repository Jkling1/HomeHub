#!/usr/bin/env python3
"""
Jordan Smart Hub — FastAPI server.
Run: python3 server.py
Dashboard: http://localhost:8888
"""

import os
import json
import asyncio
import subprocess
import requests as req
from pathlib import Path
from datetime import datetime
from typing import Set
import apple_music

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
import uvicorn

# ── Load env ──────────────────────────────────────────────────────────────────
ENV_PATH = Path(__file__).parent / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
HUE_BRIDGE = os.environ.get("HUE_BRIDGE", "192.168.12.225")
HUE_KEY    = os.environ.get("HUE_KEY", "")
SCRIPT_DIR = Path(__file__).parent

from database import init_db, log_command, get_history, update_light_state, get_light_state, update_music_state, get_music_state, get_conn

init_db()

app = FastAPI(title="Jordan Smart Hub")
app.mount("/static", StaticFiles(directory=str(SCRIPT_DIR / "static")), name="static")

# ── WebSocket broadcast manager ───────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket):
        self.active.discard(ws)

    async def broadcast(self, data: dict):
        dead = set()
        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        self.active -= dead

ws_manager = ConnectionManager()

# ── Intent parser ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are the AI brain of Jordan's Smart Hub — a personal home automation assistant for Jordan in Rockford, IL.

Interpret any natural language input and return ONLY valid JSON. No prose, no markdown fences.

AVAILABLE ACTIONS:

{ "action": "lights", "color": "<red|green|blue|purple|orange|yellow|pink|white|cyan|warm|cool|on|off>", "brightness": <0-254> }

{ "action": "music", "command": "<play|pause|resume|skip|back|stop|volume>", "query": "<song or artist>", "volume": <0-100> }

{ "action": "briefing" }

{ "action": "weather" }

{ "action": "stock" }

{ "action": "chat", "reply": "<response>" }

{ "action": "multi", "commands": [ ...actions... ] }

RULES:
- Return ONLY JSON
- "briefing" / "morning update" / "daily update" → briefing action
- Music without query → resume/pause as appropriate
- "lights off" → lights action color=off
- Multiple requests → multi action
- Typos are fine, infer intent"""


def parse_intent(text: str) -> dict:
    resp = req.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 300,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": text}],
        },
        timeout=15,
    )
    resp.raise_for_status()
    raw = resp.json()["content"][0]["text"].strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


# ── Color map ─────────────────────────────────────────────────────────────────
COLOR_MAP = {
    "red":    {"hue": 0,     "sat": 254},
    "orange": {"hue": 6000,  "sat": 254},
    "yellow": {"hue": 12000, "sat": 254},
    "green":  {"hue": 25000, "sat": 254},
    "cyan":   {"hue": 36000, "sat": 254},
    "blue":   {"hue": 46920, "sat": 254},
    "purple": {"hue": 48000, "sat": 254},
    "pink":   {"hue": 56000, "sat": 220},
    "warm":   {"hue": 8000,  "sat": 180},
    "cool":   {"hue": 43000, "sat": 80},
    "white":  {"hue": 41000, "sat": 20},
}

# ── Action executors ──────────────────────────────────────────────────────────
def exec_lights(cmd: dict) -> str:
    color = cmd.get("color", "white").lower()
    bri   = int(cmd.get("brightness", 200))

    if color == "off":
        state = {"on": False}
        update_light_state("off", bri, False)
    elif color in ("on", ""):
        state = {"on": True, "bri": bri}
        update_light_state("white", bri, True)
    else:
        c = COLOR_MAP.get(color, COLOR_MAP["white"])
        state = {"on": True, "bri": bri, **c}
        update_light_state(color, bri, True)

    try:
        lights = req.get(f"http://{HUE_BRIDGE}/api/{HUE_KEY}/lights", timeout=5).json()
        ok = 0
        for lid, info in lights.items():
            if "hue" in state and "color" not in info.get("type","").lower():
                safe = {k: v for k, v in state.items() if k not in ("hue","sat")}
            else:
                safe = state
            r = req.put(f"http://{HUE_BRIDGE}/api/{HUE_KEY}/lights/{lid}/state", json=safe, timeout=5)
            if any("success" in str(x) for x in r.json()):
                ok += 1
        return f"💡 Lights → {color} ({ok} updated)"
    except Exception as e:
        return f"Lights error: {e}"


def exec_music(cmd: dict) -> str:
    result = apple_music.handle(cmd)
    # Sync DB state after any music command
    s = apple_music.get_status()
    update_music_state(s["track"], s["artist"], s["playing"], s["volume"])
    return result


def exec_briefing() -> str:
    out = subprocess.run(
        ["python3", str(SCRIPT_DIR / "briefing_telegram.py")],
        capture_output=True, text=True, timeout=30
    ).stdout.strip()
    # Strip MarkdownV2 escapes for clean display
    return out.replace("\\.", ".").replace("\\!", "!").replace("\\-", "-").replace("\\'", "'").replace("\\+", "+").replace("\\(", "(").replace("\\)", ")").replace("\\[", "[").replace("\\]", "]").replace("\\,", ",").replace("\\/", "/").replace("\\?", "?")


def exec_weather() -> str:
    try:
        r = req.get("https://wttr.in/Rockford,IL?format=j1", timeout=8,
                    headers={"User-Agent": "JordanHub/1.0"})
        d = r.json()["current_condition"][0]
        return (f"🌤 {d['weatherDesc'][0]['value']}, {d['temp_F']}°F, "
                f"feels like {d['FeelsLikeF']}°F, humidity {d['humidity']}%")
    except Exception as e:
        return f"Weather unavailable: {e}"


def exec_stock() -> str:
    try:
        import yfinance as yf
        watchlist = ["NVDA","AAPL","TSLA","MSFT","META","AMZN","GOOGL"]
        best = None; best_pct = None
        for sym in watchlist:
            try:
                t = yf.Ticker(sym)
                info = t.fast_info
                price = float(getattr(info,"last_price",0) or 0)
                prev  = float(getattr(info,"previous_close",0) or 0)
                if price and prev:
                    pct = (price-prev)/prev*100
                    if best_pct is None or pct > best_pct:
                        best_pct = pct; best = {"sym":sym,"price":price,"pct":pct}
            except: continue
        if best:
            a = "▲" if best["pct"] >= 0 else "▼"
            return f"📈 {best['sym']} ${best['price']:.2f} {a}{abs(best['pct']):.2f}%"
        return "Market data unavailable"
    except Exception as e:
        return f"Stock error: {e}"


def execute_cmd(cmd: dict) -> str:
    action = cmd.get("action","chat")
    if action == "lights":   return exec_lights(cmd)
    if action == "music":    return exec_music(cmd)
    if action == "briefing": return exec_briefing()
    if action == "weather":  return exec_weather()
    if action == "stock":    return exec_stock()
    if action == "chat":     return cmd.get("reply","Got it.")
    if action == "multi":
        results = []
        for sub in cmd.get("commands",[]):
            if "type" in sub and "action" not in sub:
                sub = {**sub, "action": sub["type"]}
            results.append(execute_cmd(sub))
        return "\n".join(results)
    return f"Unknown action: {action}"


# ── API routes ────────────────────────────────────────────────────────────────

class CommandRequest(BaseModel):
    text: str


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep alive; client pings
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@app.post("/command")
async def handle_command(req_body: CommandRequest):
    text = req_body.text.strip()
    if not text:
        raise HTTPException(400, "Empty command")
    try:
        intent = parse_intent(text)
        result = execute_cmd(intent)
        log_command(text, intent.get("action","?"), result)
        payload = {"type": "command", "action": intent.get("action"), "result": result, "input": text, "ts": datetime.now().strftime("%H:%M")}
        asyncio.create_task(ws_manager.broadcast(payload))
        return {"ok": True, "action": intent.get("action"), "result": result, "intent": intent}
    except Exception as e:
        log_command(text, "error", str(e), False)
        raise HTTPException(500, str(e))


@app.get("/status")
async def get_status():
    try:
        music = apple_music.get_status()
        update_music_state(music["track"], music["artist"], music["playing"], music["volume"])
    except Exception:
        music = get_music_state()

    status = {
        "lights": get_light_state(),
        "music":  music,
        "time":   datetime.now().strftime("%I:%M %p"),
        "date":   datetime.now().strftime("%A, %B %d"),
    }
    asyncio.create_task(ws_manager.broadcast({"type": "status", **status}))
    return status


class MusicRequest(BaseModel):
    command: str
    query: str = ""
    volume: int = None


@app.post("/music")
async def music_endpoint(req_body: MusicRequest):
    """Direct music control endpoint — routes through apple_music module."""
    cmd = {"command": req_body.command, "query": req_body.query}
    if req_body.volume is not None:
        cmd["volume"] = req_body.volume
    result = exec_music(cmd)
    log_command(f"{req_body.command} {req_body.query}".strip(), "music", result)
    status = apple_music.get_status()
    asyncio.create_task(ws_manager.broadcast({"type": "music", "result": result, "status": status}))
    return {"ok": True, "result": result, "status": status}


@app.get("/weather")
async def get_weather():
    return {"result": exec_weather()}


@app.get("/history")
async def history():
    return get_history(50)


@app.get("/briefing")
async def briefing():
    return {"result": exec_briefing()}


@app.get("/news")
async def get_news():
    import urllib.request
    import xml.etree.ElementTree as ET
    feeds = [
        ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
        ("BBC Tech",  "https://feeds.bbci.co.uk/news/technology/rss.xml"),
    ]
    articles = []
    for source, url in feeds:
        try:
            r = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(r, timeout=6) as resp:
                root = ET.fromstring(resp.read().decode("utf-8"))
            channel = root.find("channel")
            for item in (channel.findall("item") if channel is not None else [])[:4]:
                pub = item.findtext("pubDate", "")
                articles.append({
                    "title":       (item.findtext("title") or "").strip(),
                    "description": (item.findtext("description") or "").strip()[:140],
                    "url":         item.findtext("link") or "",
                    "source":      source,
                    "pub_date":    pub,
                })
        except Exception:
            pass
    return {"articles": articles[:8]}


@app.get("/ironmind/plan")
async def im_plan():
    import ironmind
    return {"result": ironmind.get_plan()}


class IMPlanRequest(BaseModel):
    date: str = None
    priority_1: str = None
    priority_2: str = None
    priority_3: str = None
    training: str = None
    mental_theme: str = None
    notes: str = None

@app.post("/ironmind/plan")
async def im_save_plan_endpoint(req: IMPlanRequest):
    from database import im_save_plan
    from datetime import date as _date
    d = req.date or _date.today().strftime("%Y-%m-%d")
    fields = {k: v for k, v in req.dict().items() if k != "date" and v is not None}
    im_save_plan(d, **fields)
    return {"result": "saved", "date": d}


@app.get("/ironmind/log")
async def im_get_log(raw: bool = False):
    from database import im_get_log as db_get_log
    import ironmind
    from datetime import date as _date
    today = _date.today().strftime("%Y-%m-%d")
    if raw:
        row = db_get_log(today) or {}
        row["score"] = ironmind._compute_score(row) if row else 0
        return row
    return {"result": ironmind.get_log()}


class IMLogRequest(BaseModel):
    metrics: dict


@app.post("/ironmind/log")
async def im_log(req_body: IMLogRequest):
    import ironmind
    return {"result": ironmind.log_metrics(req_body.metrics)}


def _parse_health_export(raw: dict) -> dict:
    """Parse Health Auto Export v2 nested JSON into a flat dict keyed by date."""
    # Health Auto Export v2 format: {"data": {"metrics": [{"name": ..., "data": [...]}]}}
    metrics_list = (raw.get("data") or {}).get("metrics") or []
    if not metrics_list:
        return {}  # not Health Auto Export format

    # metric_name → canonical key + which value field to use
    NAME_MAP = {
        "active_energy":                   ("active_calories", "qty"),
        "step_count":                      ("steps",           "qty"),
        "heart_rate_variability_sdnn":     ("hrv",             "avg"),
        "resting_heart_rate":              ("resting_hr",      "qty"),
        "weight_body_mass":                ("weight_lbs",      "qty"),
        "sleep_analysis":                  ("sleep_hours",     "asleep"),
        "cycling_distance":                ("cycle_distance",  "qty"),
        "walking_running_distance":        ("run_distance",    "qty"),
        "swimming_distance":               ("swim_distance",   "qty"),
        "basal_energy_burned":             ("calories_burned", "qty"),
        "dietary_protein":                 ("protein_g",       "qty"),
        "heart_rate":                      ("heart_rate_avg",  "avg"),
    }

    by_date = {}
    for metric in metrics_list:
        raw_name = metric.get("name", "").lower().replace(" ", "_")
        if raw_name not in NAME_MAP:
            continue
        key, val_field = NAME_MAP[raw_name]
        for entry in (metric.get("data") or []):
            date = str(entry.get("date", ""))[:10]
            val = entry.get(val_field) or entry.get("qty") or entry.get("avg")
            if date and val is not None:
                by_date.setdefault(date, {})[key] = val
    return by_date


@app.post("/health/sync")
async def health_sync(request: Request):
    from database import im_upsert_log, ironman_save
    from datetime import date as _date

    raw = await request.json()

    # Detect Health Auto Export v2 format
    by_date = _parse_health_export(raw)

    if by_date:
        # Bulk import — one row per date
        results = []
        for date, fields in sorted(by_date.items()):
            im_f, tr_f = {}, {}
            for k, v in fields.items():
                if k in ("steps", "sleep_hours", "sleep_quality", "calories", "weight_lbs", "protein_g"):
                    im_f[k] = int(v) if k in ("steps",) else v
                if k in ("resting_hr", "hrv", "active_calories", "steps", "weight",
                         "run_distance", "cycle_distance", "swim_distance", "calories_burned"):
                    tr_f[k] = v
            # active_calories → calories in im_log
            if "active_calories" in fields: im_f["calories"] = int(fields["active_calories"])
            if "weight_lbs" in fields:      tr_f["weight"]   = fields["weight_lbs"]
            if im_f: im_upsert_log(date, **im_f)
            if tr_f: ironman_save(date, **tr_f)
            results.append(date)
        return {"ok": True, "format": "health_auto_export", "dates_synced": len(results), "dates": results[-5:]}

    # Flat format (manual / Shortcut)
    today = raw.get("date") or _date.today().strftime("%Y-%m-%d")
    im_f, tr_f = {}, {}
    if raw.get("steps")           is not None: im_f["steps"]         = int(raw["steps"])
    if raw.get("sleep_hours")     is not None: im_f["sleep_hours"]   = raw["sleep_hours"]
    if raw.get("sleep_quality")   is not None: im_f["sleep_quality"] = raw["sleep_quality"]
    if raw.get("active_calories") is not None: im_f["calories"]      = int(raw["active_calories"])
    if raw.get("weight_lbs")      is not None: im_f["weight_lbs"]    = raw["weight_lbs"]
    if raw.get("resting_hr")      is not None: tr_f["resting_hr"]    = raw["resting_hr"]
    if raw.get("hrv")             is not None: tr_f["hrv"]           = raw["hrv"]
    if raw.get("active_calories") is not None: tr_f["active_calories"] = int(raw["active_calories"])
    if raw.get("steps")           is not None: tr_f["steps"]         = int(raw["steps"])
    if raw.get("weight_lbs")      is not None: tr_f["weight"]        = raw["weight_lbs"]
    if im_f: im_upsert_log(today, **im_f)
    if tr_f: ironman_save(today, **tr_f)
    return {"ok": True, "format": "flat", "date": today, "synced": {**im_f, **tr_f}}


@app.get("/ironmind/streaks")
async def im_streaks():
    from database import im_get_streaks
    return im_get_streaks()


@app.get("/ironmind/coach")
async def im_coach():
    import ironmind
    return {"result": ironmind.get_coaching()}


@app.get("/ironmind/review")
async def im_review():
    import ironmind
    return {"result": ironmind.weekly_review()}


@app.get("/ironmind/identity")
async def im_identity():
    from database import im_get_identity
    return im_get_identity()


@app.get("/ironmind/journal")
async def im_journal():
    import ironmind
    return {"result": ironmind.get_journal()}


class JournalRequest(BaseModel):
    went_right:   str = ""
    cut_corners:  str = ""
    tomorrow_std: str = ""

@app.get("/ironmind/protocol")
async def im_get_protocol():
    from database import daily_prep_get
    from datetime import date as _date
    today = _date.today().strftime("%Y-%m-%d")
    return daily_prep_get(today) or {}


@app.post("/ironmind/journal")
async def im_save_journal(body: JournalRequest):
    from database import im_save_journal as db_save
    from datetime import date as _date
    today = _date.today().strftime("%Y-%m-%d")
    db_save(today, body.went_right, body.cut_corners, body.tomorrow_std)
    log_command("daily reflection", "journal", f"Saved reflection for {today}", True)
    return {"ok": True, "date": today}


class TrainingDataRequest(BaseModel):
    date: str = ""
    weight: float = None
    sleep_hours: float = None
    resting_hr: int = None
    hrv: float = None
    calories_burned: int = None
    active_calories: int = None
    steps: int = None
    run_distance: float = None
    cycle_distance: float = None
    swim_distance: float = None
    workouts: list = []
    effort_level: int = None
    fatigue_level: int = None
    notes: str = ""


@app.post("/ironmind/training")
async def im_training_log(req_body: TrainingDataRequest):
    import ironmind
    from datetime import date as _date
    date_str = req_body.date or _date.today().strftime("%Y-%m-%d")
    data = {k: v for k, v in req_body.dict().items() if v is not None and v != "" and v != []}
    data["date"] = date_str
    protocol = ironmind.save_training_data(data, date_str)
    return {"protocol": protocol, "date": date_str}


@app.get("/ironmind/training")
async def im_training_get(date: str = ""):
    import ironmind
    from datetime import date as _date
    date_str = date or _date.today().strftime("%Y-%m-%d")
    return ironmind.get_training_protocol(date_str)


@app.get("/ironmind/training/history")
async def im_training_history():
    import ironmind
    return ironmind.get_training_history(14)


@app.get("/scenes")
async def list_scenes():
    from database import get_scenes
    return get_scenes()


class SceneSaveRequest(BaseModel):
    name: str
    inputs: list


@app.post("/scenes")
async def save_scene_endpoint(req_body: SceneSaveRequest):
    from database import save_scene
    save_scene(req_body.name, req_body.inputs)
    return {"ok": True, "name": req_body.name}


@app.post("/scenes/{scene_name}/run")
async def run_scene_endpoint(scene_name: str):
    from database import get_scene
    scene = get_scene(scene_name)
    if not scene:
        raise HTTPException(404, f"Scene '{scene_name}' not found")
    result = execute_cmd({"action": "scene", "command": "run", "name": scene_name})
    return {"ok": True, "result": result}


@app.delete("/scenes/{scene_name}")
async def delete_scene_endpoint(scene_name: str):
    from database import get_scene, delete_scene
    if not get_scene(scene_name):
        raise HTTPException(404, f"Scene '{scene_name}' not found")
    delete_scene(scene_name)
    return {"ok": True}


@app.get("/patterns")
async def get_patterns():
    from pattern_engine import build_jordan_model
    return build_jordan_model(days=60)


@app.get("/report")
async def get_report():
    from weekly_report import generate_report
    return {"result": generate_report(send=False)}


@app.get("/stocks/alerts")
async def stock_alerts_list():
    import stock_alerts as sa
    alerts = sa.load_alerts()
    enriched = []
    for a in alerts:
        data = sa.get_price(a["symbol"])
        enriched.append({**a, "current_price": data["price"] if data else None,
                         "pct_change": data["pct_change"] if data else None})
    return enriched


class StockAlertRequest(BaseModel):
    symbol: str
    type: str = "above"
    target: float


@app.post("/stocks/alerts")
async def stock_alert_add(req_body: StockAlertRequest):
    import stock_alerts as sa
    from datetime import datetime as dt
    alerts = sa.load_alerts()
    alert  = {
        "id":         sa.next_id(alerts),
        "symbol":     req_body.symbol.upper(),
        "type":       req_body.type,
        "target":     req_body.target,
        "triggered":  False,
        "created_at": dt.now().isoformat(),
    }
    alerts.append(alert)
    sa.save_alerts(alerts)
    return {"ok": True, "alert": alert}


@app.delete("/stocks/alerts/{alert_id}")
async def stock_alert_remove(alert_id: int):
    import stock_alerts as sa
    alerts = sa.load_alerts()
    before = len(alerts)
    alerts = [a for a in alerts if a["id"] != alert_id]
    if len(alerts) == before:
        raise HTTPException(404, f"No alert with ID {alert_id}")
    sa.save_alerts(alerts)
    return {"ok": True}


@app.get("/stocks/check")
async def stock_check():
    import stock_alerts as sa
    fired = sa.run_check(quiet=True)
    return {"ok": True, "fired": len(fired)}


@app.get("/agents/status")
async def agents_status():
    from pathlib import Path
    import json
    state_file = SCRIPT_DIR / "agent_state.json"
    state = {}
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
        except:
            pass
    log_file = SCRIPT_DIR / "agent.log"
    recent_logs = []
    if log_file.exists():
        lines = log_file.read_text().splitlines()
        recent_logs = lines[-30:]
    return {"state": state, "recent_logs": recent_logs}


class AgentRunRequest(BaseModel):
    agent: str
    mission: str = ""


@app.post("/agents/run")
async def run_agent(req_body: AgentRunRequest):
    import asyncio, subprocess
    agent = req_body.agent
    mission = req_body.mission

    if agent == "orchestrator" and not mission:
        raise HTTPException(400, "Orchestrator requires a mission")

    valid = {"morning", "accountability", "adaptive", "stock", "orchestrator", "music_mood", "evolve"}
    if agent not in valid:
        raise HTTPException(400, f"Unknown agent: {agent}")

    # Run in background subprocess so it doesn't block
    args = ["python3", str(SCRIPT_DIR / "run_agent.py"), agent]
    if mission:
        args.append(mission)

    subprocess.Popen(args, cwd=str(SCRIPT_DIR),
                     stdout=open(str(SCRIPT_DIR / "agent.log"), "a"),
                     stderr=subprocess.STDOUT)
    return {"ok": True, "agent": agent, "mission": mission or None}


@app.get("/agents/log")
async def agents_log():
    log_file = SCRIPT_DIR / "agent.log"
    if not log_file.exists():
        return {"lines": []}
    lines = log_file.read_text().splitlines()
    return {"lines": lines[-100:]}


# ── Rocks ──────────────────────────────────────────────────────────────────────

class RockCreate(BaseModel):
    date: str
    size: str       # big | medium | small
    title: str
    category: str = "training"
    sort_order: int = 0

class RockUpdate(BaseModel):
    status: str = None
    title: str = None
    category: str = None
    notes: str = None

@app.get("/rocks")
async def get_rocks(date: str = None):
    from database import rocks_get
    from datetime import date as _date
    d = date or _date.today().strftime("%Y-%m-%d")
    return rocks_get(d)

@app.post("/rocks")
async def create_rock(body: RockCreate):
    from database import rock_create, rocks_get
    if body.size not in ("big", "medium", "small"):
        raise HTTPException(400, "size must be big, medium, or small")
    rock_id = rock_create(body.date, body.size, body.title, body.category, body.sort_order)
    return {"id": rock_id, **rocks_get(body.date)}

@app.patch("/rocks/{rock_id}")
async def update_rock(rock_id: int, body: RockUpdate):
    from database import rock_update
    fields = {k: v for k, v in body.dict().items() if v is not None}
    rock_update(rock_id, **fields)
    return {"ok": True}

@app.delete("/rocks/{rock_id}")
async def delete_rock(rock_id: int):
    from database import rock_delete
    rock_delete(rock_id)
    return {"ok": True}

@app.get("/rocks/week")
async def rocks_week(start: str = None):
    from database import rocks_get_week
    from datetime import date as _date, timedelta
    s = start or (_date.today() - timedelta(days=6)).strftime("%Y-%m-%d")
    return rocks_get_week(s, days=7)


# ── Log Hub ────────────────────────────────────────────────────────────────────

@app.get("/logs/workout")
async def logs_workout(limit: int = 60, offset: int = 0):
    from database import ironman_get_history
    rows = ironman_get_history(limit + offset)[offset:]
    entries = []
    for r in rows:
        protocol = {}
        if r.get("protocol"):
            try:
                import json as _json
                protocol = _json.loads(r["protocol"])
            except Exception:
                pass
        entries.append({
            "ts":           r.get("date", ""),
            "type":         "workout",
            "run_mi":       r.get("run_distance"),
            "bike_mi":      r.get("cycle_distance"),
            "swim_m":       r.get("swim_distance"),
            "effort":       r.get("effort_level"),
            "fatigue":      r.get("fatigue_level"),
            "phase":        protocol.get("phase", ""),
            "focus":        protocol.get("week_day_focus", ""),
            "readiness":    protocol.get("readiness_score"),
            "notes":        r.get("notes", ""),
        })
    return {"entries": entries, "total": len(entries)}


@app.get("/logs/nutrition")
async def logs_nutrition(limit: int = 60, offset: int = 0):
    from database import im_get_logs
    rows = im_get_logs(limit + offset)[offset:]
    entries = []
    for r in rows:
        if not any([r.get("calories"), r.get("protein_g"), r.get("hydration_oz")]):
            continue
        entries.append({
            "ts":           r.get("date", ""),
            "type":         "nutrition",
            "calories":     r.get("calories"),
            "protein_g":    r.get("protein_g"),
            "hydration_oz": r.get("hydration_oz"),
            "fast_food":    bool(r.get("fast_food")),
            "alcohol":      bool(r.get("alcohol")),
            "score":        None,
        })
    return {"entries": entries, "total": len(entries)}


@app.get("/logs/recovery")
async def logs_recovery(limit: int = 60, offset: int = 0):
    from database import im_get_logs
    rows = im_get_logs(limit + offset)[offset:]
    entries = []
    for r in rows:
        entries.append({
            "ts":            r.get("date", ""),
            "type":          "recovery",
            "sleep_hours":   r.get("sleep_hours"),
            "sleep_quality": r.get("sleep_quality"),
            "mood":          r.get("mood"),
            "weight_lbs":    r.get("weight_lbs"),
            "notes":         r.get("notes", ""),
        })
    return {"entries": entries, "total": len(entries)}


@app.get("/logs/system")
async def logs_system(limit: int = 200):
    log_file = SCRIPT_DIR / "agent.log"
    lines = []
    if log_file.exists():
        raw = log_file.read_text().splitlines()
        for line in raw[-limit:]:
            level = "error" if "error" in line.lower() else "info"
            lines.append({"ts": line[:19] if len(line) > 19 else "", "level": level, "msg": line})
    from database import get_history
    cmds = get_history(50)
    cmd_entries = [{"ts": c.get("ts",""), "level": "cmd",
                    "msg": f"[cmd] {c.get('input','')[:60]} → {c.get('action','')}"} for c in cmds]
    all_entries = sorted(lines + cmd_entries, key=lambda x: x["ts"], reverse=True)
    return {"entries": all_entries[:limit]}


@app.get("/logs/export")
async def logs_export(type: str = "workout", format: str = "json"):
    import json as _json
    from fastapi.responses import PlainTextResponse
    if type == "workout":
        data = (await logs_workout(limit=500)).get("entries", [])
    elif type == "nutrition":
        data = (await logs_nutrition(limit=500)).get("entries", [])
    elif type == "recovery":
        data = (await logs_recovery(limit=500)).get("entries", [])
    else:
        data = (await logs_system(limit=500)).get("entries", [])

    if format == "csv":
        if not data:
            return PlainTextResponse("no data")
        keys = list(data[0].keys())
        rows = [",".join(keys)]
        for row in data:
            rows.append(",".join(str(row.get(k, "")) for k in keys))
        return PlainTextResponse("\n".join(rows), media_type="text/csv",
                                 headers={"Content-Disposition": f"attachment; filename={type}_log.csv"})
    return data


class BroadcastRequest(BaseModel):
    type: str = "agent"
    data: dict = {}


@app.post("/broadcast")
async def broadcast_event(req_body: BroadcastRequest):
    """Agents call this to push events to connected dashboard clients."""
    await ws_manager.broadcast({"type": req_body.type, **req_body.data})
    return {"ok": True, "clients": len(ws_manager.active)}


@app.get("/adler/memory")
async def adler_memory_get():
    from agents import adler_memory
    return adler_memory.load()


class MemoryFactRequest(BaseModel):
    fact: str
    category: str = "fact"
    context: str = ""


@app.post("/adler/memory/fact")
async def adler_memory_add(req_body: MemoryFactRequest):
    from agents import adler_memory
    if req_body.category == "fact":
        adler_memory.add_fact(req_body.fact)
    elif req_body.category.startswith("preference_"):
        cat = req_body.category.replace("preference_", "")
        adler_memory.update_preference(cat, req_body.context or "general", req_body.fact)
    return {"ok": True}


@app.get("/adler/calendar")
async def adler_calendar_get():
    from agents import calendar as adler_cal
    events = adler_cal.get_today_events()
    return {"events": events, "formatted": adler_cal.format_for_prompt(events)}


# ── Coach Chat ────────────────────────────────────────────────────────────────

class CoachChatRequest(BaseModel):
    message: str
    history: list = []


@app.post("/coach/chat")
async def coach_chat(req_body: CoachChatRequest):
    from database import im_get_logs, im_get_streaks, im_get_plan
    import json as _json

    from datetime import date as _date
    today_str = _date.today().strftime("%Y-%m-%d")
    logs    = im_get_logs(7)
    streaks = im_get_streaks()
    plan    = im_get_plan(today_str)

    streak_summary = ", ".join(
        f"{s['name'].replace('_',' ')}: {s['current']}d" for s in streaks
    ) if streaks else "no streaks yet"

    log_lines = []
    for log in logs[:5]:
        from ironmind import _compute_score
        score = _compute_score(log)
        log_lines.append(
            f"  {log['date']}: score={score}/10, workout={'yes' if log.get('workout_done') else 'no'}, "
            f"mood={log.get('mood','?')}/10, sleep={log.get('sleep_hours','?')}h"
        )

    race_date = _date(2026, 11, 7)
    days_out  = (race_date - _date.today()).days

    athlete_ctx = f"""Jordan's IronMind data — {today_str} ({days_out} days to Ironman Florida):

Streaks: {streak_summary}
Recent logs:
{chr(10).join(log_lines) if log_lines else '  no logs yet'}
Today's plan: {_json.dumps(plan) if plan else 'not set'}"""

    system_prompt = (
        "You are IronMind Coach — Jordan's elite triathlon and performance coach. "
        "Jordan is training for Ironman Florida on November 7, 2026. "
        "You are direct, specific, and invested. No motivational fluff. "
        "Reference Jordan's actual data in your responses. "
        "Keep responses to 2-4 sentences unless a detailed question is asked. "
        "Systems over goals. Consistency over intensity."
    )

    messages = []
    for h in req_body.history[-6:]:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": f"{athlete_ctx}\n\nJordan: {req_body.message}"})

    try:
        resp = req.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key":         ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            },
            json={
                "model":      "claude-haiku-4-5-20251001",
                "max_tokens": 500,
                "system":     system_prompt,
                "messages":   messages,
            },
            timeout=25,
        )
        resp.raise_for_status()
        reply = resp.json()["content"][0]["text"].strip()
        return {"reply": reply}
    except Exception as e:
        return {"reply": f"Coach offline: {e}"}


# ── DJ Remix ──────────────────────────────────────────────────────────────────

SPORT_VIBES = {
    "SWIM":     {"default":   {"bpmRange": "125–145", "seedGenres": "electronic, trance, progressive house", "energy": 7}},
    "BIKE":     {
        "easy":      {"bpmRange": "120–135", "seedGenres": "indie rock, classic rock, alternative", "energy": 5},
        "moderate":  {"bpmRange": "130–150", "seedGenres": "rock, pop punk, alternative", "energy": 7},
        "hard":      {"bpmRange": "145–175", "seedGenres": "EDM, metal, drum and bass, hardstyle", "energy": 9},
        "intervals": {"bpmRange": "155–185", "seedGenres": "EDM, hip hop, metal, hardstyle", "energy": 10},
        "recovery":  {"bpmRange": "90–110",  "seedGenres": "lo-fi, acoustic, chill", "energy": 3},
    },
    "RUN":      {
        "easy":      {"bpmRange": "140–155", "seedGenres": "pop, indie, funk, soul", "energy": 5},
        "moderate":  {"bpmRange": "155–170", "seedGenres": "hip hop, pop, dancehall", "energy": 7},
        "hard":      {"bpmRange": "170–185", "seedGenres": "hip hop, EDM, trap, rap", "energy": 9},
        "intervals": {"bpmRange": "175–190", "seedGenres": "trap, drill, EDM, hardstyle", "energy": 10},
        "recovery":  {"bpmRange": "120–135", "seedGenres": "lo-fi hip hop, jazz, acoustic", "energy": 3},
    },
    "STRENGTH": {
        "default":   {"bpmRange": "125–150", "seedGenres": "hip hop, metal, rock, trap", "energy": 8},
        "easy":      {"bpmRange": "115–130", "seedGenres": "hip hop, R&B, funk", "energy": 6},
        "hard":      {"bpmRange": "140–160", "seedGenres": "metal, hardcore, trap, rap", "energy": 10},
        "intervals": {"bpmRange": "145–165", "seedGenres": "metal, hardstyle, trap", "energy": 10},
    },
    "MOBILITY": {"default":   {"bpmRange": "60–85",  "seedGenres": "ambient, new age, classical, nature", "energy": 2}},
    "RECOVERY": {"default":   {"bpmRange": "60–90",  "seedGenres": "lo-fi, ambient, jazz, acoustic, chillhop", "energy": 2}},
}


class DJRequest(BaseModel):
    sport: str = "RUN"
    intensity: str = "moderate"
    durationMin: int = 60


@app.post("/coach/dj")
async def coach_dj(req_body: DJRequest):
    sport     = req_body.sport.upper()
    intensity = req_body.intensity.lower()
    sport_map = SPORT_VIBES.get(sport, SPORT_VIBES["RUN"])
    vibe      = sport_map.get(intensity) or sport_map.get("default") or list(sport_map.values())[0]

    prompt = f"""You are a DJ and Ironman triathlon coach. Generate a perfect workout playlist vibe.

SESSION:
- Sport: {sport}
- Intensity: {intensity}
- Duration: {req_body.durationMin} minutes
- Target BPM: {vibe['bpmRange']}
- Genres: {vibe['seedGenres']}
- Energy level: {vibe['energy']}/10

Return ONLY valid JSON — no markdown, no explanation:
{{
  "vibeName": "short punchy name (e.g. 'Asphalt Heat')",
  "tagline": "one-line hype, max 10 words",
  "bpmRange": "{vibe['bpmRange']}",
  "energyLevel": {vibe['energy']},
  "genres": ["genre1", "genre2", "genre3"],
  "tracks": [
    {{"title": "Song Title", "artist": "Artist", "bpm": 175, "why": "5 words why"}},
    {{"title": "Song Title", "artist": "Artist", "bpm": 180, "why": "5 words why"}},
    {{"title": "Song Title", "artist": "Artist", "bpm": 172, "why": "5 words why"}},
    {{"title": "Song Title", "artist": "Artist", "bpm": 178, "why": "5 words why"}},
    {{"title": "Song Title", "artist": "Artist", "bpm": 182, "why": "5 words why"}},
    {{"title": "Song Title", "artist": "Artist", "bpm": 170, "why": "5 words why"}}
  ],
  "coachNote": "one sentence connecting music to this session"
}}

Use real, well-known songs. Match BPM to target range. Be specific and creative."""

    try:
        resp = req.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key":         ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            },
            json={
                "model":      "claude-haiku-4-5-20251001",
                "max_tokens": 800,
                "temperature": 1.0,
                "messages":   [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        resp.raise_for_status()
        raw  = resp.json()["content"][0]["text"].strip()
        import json as _json, re as _re
        # strip markdown code fences if present
        clean = _re.sub(r'^```(?:json)?\s*', '', raw, flags=_re.MULTILINE)
        clean = _re.sub(r'\s*```$', '', clean, flags=_re.MULTILINE).strip()
        data = _json.loads(clean)
        first_genre    = data.get("genres", ["workout"])[0]
        spotify_query  = f"{data.get('vibeName','')} {first_genre} workout".strip()
        data["spotifyUrl"] = f"https://open.spotify.com/search/{spotify_query.replace(' ', '%20')}"
        return data
    except Exception as e:
        return {"error": str(e)}


@app.get("/music/info")
async def music_info():
    """Generate song + artist info for the currently playing track via Claude. Caches by track."""
    import sqlite3, time
    status = get_music_state()
    track  = status.get("track", "").strip()
    artist = status.get("artist", "").strip()
    if not track or not artist or track == "":
        return {"track": track, "artist": artist, "cached": False}

    # Check cache in DB (simple key-value in preferences table)
    cache_key = f"music_info::{artist}::{track}"
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM preferences WHERE key=?", (cache_key,)).fetchone()
    if row:
        import json as _json
        return {**_json.loads(row[0]), "cached": True}

    # Generate via Claude
    try:
        import requests as _req, json as _json
        prompt = f"""Music expert task: provide info about "{track}" by {artist}.

Respond with ONLY valid JSON, no markdown fences, no explanation:
{{"track":"{track}","artist":"{artist}","album":"album name","year":"release year","genre":"genre","story":"2-3 sentences about this song's story or inspiration","fun_fact":"one interesting fact about this song","artist_bio":"1-2 sentences about {artist}"}}"""
        r = _req.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": os.environ.get("ANTHROPIC_API_KEY",""), "anthropic-version":"2023-06-01","content-type":"application/json"},
            json={"model":"claude-haiku-4-5-20251001","max_tokens":500,"messages":[
                {"role":"user","content":prompt},
                {"role":"assistant","content":"{"}
            ]},
            timeout=20
        )
        text = "{" + r.json()["content"][0]["text"].strip()
        if "}" in text:
            text = text[:text.rindex("}")+1]
        data = _json.loads(text)
        # Cache it
        with get_conn() as conn:
            conn.execute("INSERT OR REPLACE INTO preferences (key,value) VALUES (?,?)",
                         (cache_key, _json.dumps(data)))
        return {**data, "cached": False}
    except Exception as e:
        return {"track": track, "artist": artist, "error": str(e), "cached": False}


@app.get("/music/mood-queue")
async def music_mood_queue(mood: str = "focus"):
    """Generate a 5-song mood-based playlist via Claude."""
    import requests as _req, json as _json
    MOOD_CONTEXTS = {
        "focus":     "deep focus and concentration, no lyrics preferred, instrumental or minimal vocals",
        "hype":      "high energy workout, aggressive beats, trap/hip-hop/rock, gets you fired up",
        "chill":     "relaxed and mellow, winding down, lo-fi or R&B or acoustic",
        "deep work": "long sustained focus session, ambient or classical, no distractions",
        "sleep":     "falling asleep or meditating, very calm, ambient or soft piano",
    }
    context = MOOD_CONTEXTS.get(mood.lower(), MOOD_CONTEXTS["focus"])
    prompt = f"""You are a music curator. Jordan wants a {mood} playlist: {context}.

Give him exactly 5 song recommendations. Respond with ONLY valid JSON:
{{"mood":"{mood}","tracks":[{{"title":"song title","artist":"artist name","reason":"one sentence why this fits the {mood} vibe"}}]}}"""
    try:
        r = _req.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": os.environ.get("ANTHROPIC_API_KEY",""), "anthropic-version":"2023-06-01","content-type":"application/json"},
            json={"model":"claude-haiku-4-5-20251001","max_tokens":600,"messages":[
                {"role":"user","content":prompt},
                {"role":"assistant","content":"{"}
            ]},
            timeout=20
        )
        text = "{" + r.json()["content"][0]["text"].strip()
        if "}" in text:
            text = text[:text.rindex("}")+1]
        return _json.loads(text)
    except Exception as e:
        return {"mood": mood, "tracks": [], "error": str(e)}


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return FileResponse(str(SCRIPT_DIR / "static" / "index.html"))


# ══════════════════════════════════════════════════════════════════════════════
# NUTRITION
# ══════════════════════════════════════════════════════════════════════════════

from database import recipe_save, recipe_list, recipe_delete, recipe_favorite, \
                     grocery_list_get, grocery_add, grocery_toggle, grocery_delete, grocery_clear_checked

class RecipeGenerateRequest(BaseModel):
    goal: str = "endurance"
    cook_time: str = "quick"
    ingredients: str = ""
    calories: int = 600

class RecipeSaveRequest(BaseModel):
    name: str
    calories: int = 0
    protein_g: int = 0
    carbs_g: int = 0
    fats_g: int = 0
    ingredients: list = []
    instructions: str = ""
    why: str = ""
    tags: list = []

class GroceryAddRequest(BaseModel):
    item: str
    quantity: str = ""

@app.post("/nutrition/recipe/generate")
async def nutrition_generate(req: RecipeGenerateRequest):
    import requests as _req, json as _json
    ingredients_hint = f"using some of these: {req.ingredients}" if req.ingredients.strip() else "any ingredients"
    prompt = f"""You are a sports nutritionist for an Ironman triathlete named Jordan.
Generate ONE recipe for him: goal={req.goal}, cook time={req.cook_time}, target ~{req.calories} calories, {ingredients_hint}.

Respond with ONLY valid JSON:
{{"name":"recipe name","calories":{req.calories},"protein_g":0,"carbs_g":0,"fats_g":0,"ingredients":["item1","item2"],"instructions":"step by step instructions","why":"1-2 sentences on why this supports his training","tags":["tag1"]}}"""
    try:
        r = _req.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": "claude-haiku-4-5-20251001", "max_tokens": 700, "messages": [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": "{"}
            ]},
            timeout=25
        )
        text = "{" + r.json()["content"][0]["text"].strip()
        if "}" in text:
            text = text[:text.rindex("}")+1]
        return _json.loads(text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/nutrition/recipes")
async def nutrition_save_recipe(req: RecipeSaveRequest):
    rid = recipe_save(req.dict())
    return {"id": rid, "ok": True}

@app.get("/nutrition/recipes")
async def nutrition_get_recipes():
    return recipe_list()

@app.delete("/nutrition/recipes/{recipe_id}")
async def nutrition_delete_recipe(recipe_id: int):
    recipe_delete(recipe_id)
    return {"ok": True}

@app.post("/nutrition/recipes/{recipe_id}/favorite")
async def nutrition_favorite(recipe_id: int, state: int = 1):
    recipe_favorite(recipe_id, state)
    return {"ok": True}

@app.post("/nutrition/recipes/{recipe_id}/grocery")
async def nutrition_add_to_grocery(recipe_id: int):
    recipes = recipe_list()
    recipe = next((r for r in recipes if r["id"] == recipe_id), None)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    added = 0
    for ing in recipe.get("ingredients", []):
        grocery_add(ing)
        added += 1
    return {"added": added}

@app.get("/nutrition/grocery")
async def nutrition_grocery_get():
    return grocery_list_get()

@app.post("/nutrition/grocery")
async def nutrition_grocery_add(req: GroceryAddRequest):
    gid = grocery_add(req.item, req.quantity)
    return {"id": gid, "ok": True}

@app.patch("/nutrition/grocery/{item_id}")
async def nutrition_grocery_toggle(item_id: int, checked: int = 1):
    grocery_toggle(item_id, checked)
    return {"ok": True}

@app.delete("/nutrition/grocery/{item_id}")
async def nutrition_grocery_delete(item_id: int):
    grocery_delete(item_id)
    return {"ok": True}

@app.delete("/nutrition/grocery")
async def nutrition_grocery_clear():
    grocery_clear_checked()
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# STOCKS
# ══════════════════════════════════════════════════════════════════════════════

_stocks_cache = {"data": [], "ts": 0}
DEFAULT_TICKERS = ["AAPL", "NVDA", "TSLA", "AMZN", "MSFT", "META", "SPY"]

@app.get("/stocks/watchlist")
async def stocks_watchlist():
    import time, yfinance as yf
    now = time.time()
    if now - _stocks_cache["ts"] < 300 and _stocks_cache["data"]:  # 5-min cache
        return {"stocks": _stocks_cache["data"]}
    try:
        results = []
        for ticker in DEFAULT_TICKERS:
            t = yf.Ticker(ticker)
            info = t.fast_info
            price  = round(float(info.last_price or 0), 2)
            prev   = round(float(info.previous_close or price), 2)
            change = round(price - prev, 2)
            pct    = round((change / prev * 100) if prev else 0, 2)
            trend  = "Uptrend" if pct > 1 else "Downtrend" if pct < -1 else "Flat"
            buy_score = min(10, max(1, round(5 + (pct * 0.8) + (1 if pct > 0 else -1))))
            results.append({
                "ticker": ticker,
                "price": price,
                "change": change,
                "pct": pct,
                "trend": trend,
                "buy_score": buy_score,
            })
        results.sort(key=lambda x: x["buy_score"], reverse=True)
        _stocks_cache["data"] = results
        _stocks_cache["ts"]   = now
        return {"stocks": results}
    except Exception as e:
        return {"stocks": [], "error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# APPLE CALENDAR
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/calendar/today")
async def calendar_today():
    from datetime import date
    today = date.today().strftime("%Y-%m-%d")
    script = f'''
tell application "Calendar"
    set todayStart to current date
    set hours of todayStart to 0
    set minutes of todayStart to 0
    set seconds of todayStart to 0
    set todayEnd to todayStart + (86399)
    set evtList to {{}}
    repeat with cal in (every calendar whose name is in {{"Home", "Work", "Jordan's Bills", "Scheduled Reminders"}})
        repeat with evt in (every event of cal whose start date >= todayStart and start date <= todayEnd)
            set evtTitle to summary of evt
            set evtStart to start date of evt
            set evtEnd to end date of evt
            set end of evtList to (evtTitle & "|" & (evtStart as string) & "|" & (evtEnd as string))
        end repeat
    end repeat
    return evtList
end tell'''
    try:
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        raw = result.stdout.strip()
        events = []
        if raw and raw != "{}":
            for item in raw.split(", "):
                parts = item.strip().split("|")
                if len(parts) >= 2:
                    events.append({"title": parts[0], "start": parts[1], "end": parts[2] if len(parts) > 2 else ""})
        return {"date": today, "events": events}
    except Exception as e:
        return {"date": today, "events": [], "error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# HYDRATION
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/hydration/today")
async def hydration_today():
    from database import im_get_log
    from datetime import date
    today = date.today().strftime("%Y-%m-%d")
    log = im_get_log(today) or {}
    oz = log.get("hydration_oz") or 0
    goal = 100  # oz daily goal
    return {"oz": oz, "goal": goal, "pct": round(oz / goal * 100) if goal else 0}

@app.post("/hydration/log")
async def hydration_log(req: Request):
    from database import im_save_log
    from datetime import date
    body = await req.json()
    oz = int(body.get("oz", 8))
    today = date.today().strftime("%Y-%m-%d")
    from database import im_get_log
    current = (im_get_log(today) or {}).get("hydration_oz") or 0
    im_save_log(today, hydration_oz=current + oz)
    return {"ok": True, "total_oz": current + oz}


if __name__ == "__main__":
    print("🚀 Jordan Smart Hub starting on http://localhost:8888")
    uvicorn.run(app, host="0.0.0.0", port=8888, log_level="warning")
