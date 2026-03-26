#!/usr/bin/env python3
"""Shared utilities for all Jordan Smart Hub agents."""

import os, json, time, requests
from pathlib import Path
from datetime import datetime
from functools import wraps

# ── Paths ──────────────────────────────────────────────────────────────────
AGENT_DIR  = Path(__file__).parent
ROOT_DIR   = AGENT_DIR.parent
STATE_FILE = ROOT_DIR / "agent_state.json"

# ── Load env ───────────────────────────────────────────────────────────────
ENV_PATH = ROOT_DIR / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
TELEGRAM_TOKEN    = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID  = os.environ.get("TELEGRAM_CHAT_ID", "7937301907")
HUB_BASE          = "http://localhost:8888"
EMAIL_FROM        = os.environ.get("EMAIL_FROM", "")
EMAIL_TO          = os.environ.get("EMAIL_TO", "")
EMAIL_APP_PASS    = os.environ.get("EMAIL_APP_PASS", "")


# ── Claude API ─────────────────────────────────────────────────────────────
def claude(prompt: str, system: str = "", max_tokens: int = 500, model: str = "claude-haiku-4-5-20251001") -> str:
    msgs = [{"role": "user", "content": prompt}]
    body = {"model": model, "max_tokens": max_tokens, "messages": msgs}
    if system:
        body["system"] = system
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=body,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["content"][0]["text"].strip()


def claude_tools(messages: list, tools: list, system: str = "", model: str = "claude-haiku-4-5-20251001", max_tokens: int = 1000) -> dict:
    """Call Claude with tool use. Returns the full response dict."""
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "tools": tools,
        "messages": messages,
    }
    if system:
        body["system"] = system
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=body,
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


# ── Telegram ───────────────────────────────────────────────────────────────
def telegram_send(text: str, chat_id: str = None, parse_mode: str = "HTML") -> bool:
    cid = chat_id or TELEGRAM_CHAT_ID
    if not TELEGRAM_TOKEN or not cid:
        print(f"[Telegram] No token/chat_id. Message: {text[:80]}")
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": cid, "text": text, "parse_mode": parse_mode},
            timeout=10,
        )
        return r.ok
    except Exception as e:
        print(f"[Telegram] Error: {e}")
        return False


# ── Hub API ────────────────────────────────────────────────────────────────
def hub_command(text: str) -> dict:
    r = requests.post(f"{HUB_BASE}/command",
                      json={"text": text}, timeout=15)
    r.raise_for_status()
    return r.json()

def hub_status() -> dict:
    return requests.get(f"{HUB_BASE}/status", timeout=10).json()

def hub_weather() -> str:
    return requests.get(f"{HUB_BASE}/weather", timeout=10).json().get("result", "")

def hub_ironmind_log() -> dict:
    try:
        return requests.get(f"{HUB_BASE}/ironmind/log?raw=true", timeout=10).json()
    except:
        return {}

def hub_ironmind_streaks() -> list:
    try:
        return requests.get(f"{HUB_BASE}/ironmind/streaks", timeout=10).json()
    except:
        return []

def hub_set_lights(color: str, brightness: int = 200) -> str:
    d = hub_command(f"lights {color} brightness {brightness}")
    return d.get("result", "")

def hub_play_music(query: str) -> str:
    d = hub_command(f"play {query}")
    return d.get("result", "")

def hub_music_command(cmd: str) -> str:
    r = requests.post(f"{HUB_BASE}/music", json={"command": cmd}, timeout=10)
    return r.json().get("result", "")

def hub_stocks() -> list:
    try:
        return requests.get(f"{HUB_BASE}/stocks/alerts", timeout=10).json()
    except:
        return []


# ── Agent state / dedup ────────────────────────────────────────────────────
def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except:
            pass
    return {}

def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))

def was_fired_recently(key: str, hours: float = 12) -> bool:
    state = load_state()
    last = state.get(key)
    if not last:
        return False
    return (time.time() - last) < hours * 3600

def mark_fired(key: str):
    state = load_state()
    state[key] = time.time()
    save_state(state)


# ── Email ──────────────────────────────────────────────────────────────────
def send_email(subject: str, body: str, to: str = None) -> bool:
    import smtplib
    from email.mime.text import MIMEText
    recipient = to or EMAIL_TO
    if not all([EMAIL_FROM, EMAIL_APP_PASS, recipient]):
        print("[Email] Not configured — set EMAIL_FROM, EMAIL_APP_PASS, EMAIL_TO in .env")
        return False
    try:
        msg = MIMEText(body, "plain")
        msg["Subject"] = subject
        msg["From"]    = EMAIL_FROM
        msg["To"]      = recipient
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(EMAIL_FROM, EMAIL_APP_PASS)
            s.send_message(msg)
        return True
    except Exception as e:
        print(f"[Email] Error: {e}")
        return False


# ── Retry utility ──────────────────────────────────────────────────────────
def fetch_with_retry(fn, retries=3, delay=2, fallback=None):
    """Call fn() up to `retries` times with `delay` seconds between. Returns fallback on total failure."""
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                print(f"[retry] {fn.__name__ if hasattr(fn, '__name__') else 'fn'} failed after {retries} attempts: {e}")
    return fallback() if callable(fallback) else fallback


# ── Helpers ────────────────────────────────────────────────────────────────
def now_hour() -> int:
    return datetime.now().hour

def now_str() -> str:
    return datetime.now().strftime("%I:%M %p, %A %B %d")

def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def log(agent: str, msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{agent}] {msg}"
    print(line)
    log_file = ROOT_DIR / "agent.log"
    with open(log_file, "a") as f:
        f.write(line + "\n")
