#!/usr/bin/env python3
"""
Jordan Smart Hub — FastAPI server.
Run: python3 server.py
Dashboard: http://localhost:8888
"""

import os
import json
import subprocess
import requests as req
from pathlib import Path
from datetime import datetime
import apple_music

from fastapi import FastAPI, HTTPException
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

from database import init_db, log_command, get_history, update_light_state, get_light_state, update_music_state, get_music_state

init_db()

app = FastAPI(title="Jordan Smart Hub")
app.mount("/static", StaticFiles(directory=str(SCRIPT_DIR / "static")), name="static")

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


@app.post("/command")
async def handle_command(req_body: CommandRequest):
    text = req_body.text.strip()
    if not text:
        raise HTTPException(400, "Empty command")
    try:
        intent = parse_intent(text)
        result = execute_cmd(intent)
        log_command(text, intent.get("action","?"), result)
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

    return {
        "lights": get_light_state(),
        "music":  music,
        "time":   datetime.now().strftime("%I:%M %p"),
        "date":   datetime.now().strftime("%A, %B %d"),
    }


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
    return {"ok": True, "result": result, "status": apple_music.get_status()}


@app.get("/weather")
async def get_weather():
    return {"result": exec_weather()}


@app.get("/history")
async def history():
    return get_history(50)


@app.get("/briefing")
async def briefing():
    return {"result": exec_briefing()}


@app.get("/ironmind/plan")
async def im_plan():
    import ironmind
    return {"result": ironmind.get_plan()}


@app.get("/ironmind/log")
async def im_get_log():
    import ironmind
    return {"result": ironmind.get_log()}


class IMLogRequest(BaseModel):
    metrics: dict


@app.post("/ironmind/log")
async def im_log(req_body: IMLogRequest):
    import ironmind
    return {"result": ironmind.log_metrics(req_body.metrics)}


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

    valid = {"morning", "accountability", "adaptive", "stock", "orchestrator"}
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


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return FileResponse(str(SCRIPT_DIR / "static" / "index.html"))


if __name__ == "__main__":
    print("🚀 Jordan Smart Hub starting on http://localhost:8888")
    uvicorn.run(app, host="0.0.0.0", port=8888, log_level="warning")
