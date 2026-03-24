#!/usr/bin/env python3
"""
Jordan Smart Hub — Stock Price Alerts
Monitors your watchlist and sends Telegram alerts when conditions are met.

Usage:
  python3 stock_alerts.py add NVDA above 150        # Alert when NVDA > $150
  python3 stock_alerts.py add TSLA below 200        # Alert when TSLA < $200
  python3 stock_alerts.py add AAPL change 5         # Alert when AAPL moves ±5% in a day
  python3 stock_alerts.py list                      # Show active alerts
  python3 stock_alerts.py remove <id>               # Remove alert by ID
  python3 stock_alerts.py check                     # Run one check cycle
  python3 stock_alerts.py run                       # Start daemon (checks every 5 min)
"""

import os
import sys
import json
import time
import requests
from pathlib import Path
from datetime import datetime

# ── Load env ──────────────────────────────────────────────────────────────────
ENV_PATH = Path(__file__).parent / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
SCRIPT_DIR       = Path(__file__).parent
CONFIG_PATH      = SCRIPT_DIR / "stock_alerts.json"
CHECK_INTERVAL   = 300  # seconds between checks


# ── Config ────────────────────────────────────────────────────────────────────

def load_alerts() -> list:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    return []


def save_alerts(alerts: list):
    CONFIG_PATH.write_text(json.dumps(alerts, indent=2))


def next_id(alerts: list) -> int:
    return max((a["id"] for a in alerts), default=0) + 1


# ── Telegram ──────────────────────────────────────────────────────────────────

def send_telegram(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[Telegram not configured] {text}")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        print(f"Telegram error: {e}")


# ── Price fetching ─────────────────────────────────────────────────────────────

def get_price(symbol: str):
    """Returns {price, prev_close, pct_change} or None on failure."""
    try:
        import yfinance as yf
        t = yf.Ticker(symbol.upper())
        info = t.fast_info
        price = float(getattr(info, "last_price", 0) or 0)
        prev  = float(getattr(info, "previous_close", 0) or 0)
        if not price:
            return None
        pct = ((price - prev) / prev * 100) if prev else 0.0
        return {"price": price, "prev_close": prev, "pct_change": pct}
    except Exception:
        return None


# ── Alert logic ───────────────────────────────────────────────────────────────

def check_condition(alert: dict, data: dict) -> bool:
    """Returns True if the alert condition is met."""
    kind   = alert["type"]
    target = float(alert["target"])
    price  = data["price"]
    pct    = abs(data["pct_change"])

    if kind == "above":
        return price >= target
    if kind == "below":
        return price <= target
    if kind == "change":
        return pct >= target
    return False


def format_alert_message(alert: dict, data: dict) -> str:
    sym    = alert["symbol"].upper()
    kind   = alert["type"]
    target = alert["target"]
    price  = data["price"]
    pct    = data["pct_change"]
    arrow  = "▲" if pct >= 0 else "▼"

    if kind == "above":
        condition = f"crossed above ${target}"
    elif kind == "below":
        condition = f"dropped below ${target}"
    else:
        condition = f"moved {arrow}{abs(pct):.2f}% today"

    return (
        f"📊 <b>Stock Alert — {sym}</b>\n"
        f"{sym} {condition}\n"
        f"Current price: <b>${price:.2f}</b>  {arrow}{abs(pct):.2f}%\n"
        f"<i>{datetime.now().strftime('%I:%M %p, %b %d')}</i>"
    )


def run_check(quiet: bool = False) -> list[str]:
    """Check all active alerts. Returns list of triggered alert messages."""
    alerts  = load_alerts()
    active  = [a for a in alerts if not a.get("triggered")]
    if not active:
        if not quiet:
            print("No active alerts.")
        return []

    fired   = []
    changed = False

    for alert in active:
        data = get_price(alert["symbol"])
        if data is None:
            if not quiet:
                print(f"  ⚠️  Could not fetch {alert['symbol']}")
            continue

        if not quiet:
            arrow = "▲" if data["pct_change"] >= 0 else "▼"
            print(f"  {alert['symbol']:6s}  ${data['price']:.2f}  {arrow}{abs(data['pct_change']):.2f}%  "
                  f"[{alert['type']} {alert['target']}]")

        if check_condition(alert, data):
            msg = format_alert_message(alert, data)
            send_telegram(msg)
            print(f"  🔔 ALERT FIRED: {alert['symbol']} {alert['type']} {alert['target']}")
            fired.append(msg)

            # Mark one-shot alerts as triggered; repeating change alerts stay active
            if alert["type"] in ("above", "below"):
                alert["triggered"] = True
                alert["triggered_at"] = datetime.now().isoformat()
                changed = True

    if changed:
        save_alerts(alerts)

    return fired


# ── CLI management ─────────────────────────────────────────────────────────────

def cmd_add(args: list):
    if len(args) < 3:
        print("Usage: add <SYMBOL> <above|below|change> <target>")
        print("  above  — alert when price rises above target")
        print("  below  — alert when price falls below target")
        print("  change — alert when daily % move exceeds target")
        return

    symbol = args[0].upper()
    kind   = args[1].lower()
    try:
        target = float(args[2])
    except ValueError:
        print("Target must be a number.")
        return

    if kind not in ("above", "below", "change"):
        print("Type must be: above, below, or change")
        return

    alerts = load_alerts()
    alert  = {
        "id":         next_id(alerts),
        "symbol":     symbol,
        "type":       kind,
        "target":     target,
        "triggered":  False,
        "created_at": datetime.now().isoformat(),
    }
    alerts.append(alert)
    save_alerts(alerts)

    data = get_price(symbol)
    price_str = f"  (current: ${data['price']:.2f})" if data else ""
    print(f"✅  Alert #{alert['id']} added: {symbol} {kind} {target}{price_str}")


def cmd_remove(args: list):
    if not args:
        print("Usage: remove <id>")
        return
    try:
        target_id = int(args[0])
    except ValueError:
        print("ID must be a number.")
        return

    alerts = load_alerts()
    before = len(alerts)
    alerts = [a for a in alerts if a["id"] != target_id]
    if len(alerts) == before:
        print(f"No alert with ID {target_id}.")
        return
    save_alerts(alerts)
    print(f"🗑  Alert #{target_id} removed.")


def cmd_list():
    alerts = load_alerts()
    if not alerts:
        print("No alerts configured.")
        return

    active    = [a for a in alerts if not a.get("triggered")]
    triggered = [a for a in alerts if a.get("triggered")]

    print(f"\n📊  Stock Alerts  ({len(active)} active, {len(triggered)} triggered)\n")
    for a in active:
        data      = get_price(a["symbol"])
        price_str = f"  now ${data['price']:.2f}" if data else ""
        print(f"  #{a['id']:2d}  {a['symbol']:6s}  {a['type']:6s}  {a['target']}{price_str}")

    if triggered:
        print("\n  — Triggered —")
        for a in triggered:
            ts = a.get("triggered_at", "")[:16].replace("T", " ")
            print(f"  #{a['id']:2d}  {a['symbol']:6s}  {a['type']:6s}  {a['target']}  ✓ {ts}")
    print()


def cmd_run():
    print(f"🔔 Stock alert daemon started (checking every {CHECK_INTERVAL}s)")
    print("   Press Ctrl+C to stop.\n")
    while True:
        now = datetime.now().strftime("%H:%M:%S")
        print(f"[{now}] Checking alerts...")
        run_check()
        time.sleep(CHECK_INTERVAL)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    command = sys.argv[1].lower()
    rest    = sys.argv[2:]

    if command == "add":
        cmd_add(rest)
    elif command == "remove":
        cmd_remove(rest)
    elif command == "list":
        cmd_list()
    elif command == "check":
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Running one check...\n")
        run_check()
    elif command == "run":
        cmd_run()
    else:
        print(__doc__)
