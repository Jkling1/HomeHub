#!/usr/bin/env python3
"""
Agent 4: Stock Intelligence Agent
Runs every 5 minutes. Monitors alerts with context — not just price triggers,
but AI-generated actionable context. Tracks outcomes over time.
"""

import json
from datetime import datetime
from agents.base import *

AGENT = "stock"

WATCHLIST = ["NVDA", "AAPL", "TSLA", "MSFT", "META", "AMZN", "GOOGL"]
OUTCOMES_FILE = ROOT_DIR / "stock_outcomes.json"

def get_price(symbol: str) -> dict | None:
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        info = t.fast_info
        price = float(getattr(info, "last_price", 0) or 0)
        prev  = float(getattr(info, "previous_close", 0) or 0)
        if not price:
            return None
        pct = (price - prev) / prev * 100 if prev else 0
        return {"symbol": symbol, "price": price, "prev": prev, "pct_change": pct}
    except Exception as e:
        log(AGENT, f"Price error {symbol}: {e}")
        return None

def load_outcomes() -> list:
    if OUTCOMES_FILE.exists():
        try:
            return json.loads(OUTCOMES_FILE.read_text())
        except:
            pass
    return []

def save_outcomes(outcomes: list):
    OUTCOMES_FILE.write_text(json.dumps(outcomes, indent=2))

def generate_alert_context(data: dict, alert: dict, market_movers: list) -> str:
    movers_text = ", ".join(
        f"{m['symbol']} {'+' if m['pct_change'] >= 0 else ''}{m['pct_change']:.1f}%"
        for m in market_movers[:3]
    )

    prompt = f"""You are a stock intelligence agent. Jordan's alert just fired. Write a 2-sentence actionable context message. Be direct, factual, useful. No hype.

Alert: {alert['symbol']} {alert['type']} ${alert['target']}
Current price: ${data['price']:.2f}
Change today: {'+' if data['pct_change'] >= 0 else ''}{data['pct_change']:.2f}%
Market movers today: {movers_text}

Give 1 sentence of context (why this matters) and 1 sentence of what to consider. Plain text only."""

    return claude(prompt, max_tokens=120)

def get_market_snapshot() -> list:
    results = []
    for sym in WATCHLIST:
        data = get_price(sym)
        if data:
            results.append(data)
    return sorted(results, key=lambda x: abs(x["pct_change"]), reverse=True)

def check_condition(price_data: dict, alert: dict) -> bool:
    price = price_data["price"]
    pct   = price_data["pct_change"]
    atype = alert["type"]
    target = float(alert["target"])

    if atype == "above":   return price >= target
    if atype == "below":   return price <= target
    if atype == "change":  return abs(pct) >= target
    return False

def run():
    log(AGENT, "Stock intelligence tick")

    try:
        alerts = requests.get(f"{HUB_BASE}/stocks/alerts", timeout=10).json()
    except Exception as e:
        log(AGENT, f"Could not fetch alerts: {e}")
        return

    active_alerts = [a for a in alerts if not a.get("triggered")]
    if not active_alerts:
        log(AGENT, "No active alerts.")
        return

    # Get market snapshot for context
    market = get_market_snapshot()
    log(AGENT, f"Market snapshot: {len(market)} symbols")

    outcomes = load_outcomes()
    fired_this_run = []

    for alert in active_alerts:
        symbol = alert["symbol"]
        fire_key = f"{AGENT}_alert_{alert['id']}"

        if was_fired_recently(fire_key, hours=1):
            continue

        data = get_price(symbol)
        if not data:
            continue

        if not check_condition(data, alert):
            continue

        # Alert fired — generate context
        log(AGENT, f"Alert fired: {symbol} {alert['type']} ${alert['target']} (current: ${data['price']:.2f})")
        context = generate_alert_context(data, alert, market)

        direction = "▲" if data["pct_change"] >= 0 else "▼"
        color = "🟢" if data["pct_change"] >= 0 else "🔴"

        message = f"""{color} <b>STOCK ALERT: {symbol}</b>

<b>${data['price']:.2f}</b> {direction} {abs(data['pct_change']):.2f}% today
Alert: {alert['type']} ${alert['target']}

{context}

<i>Alert #{alert['id']} · {now_str()}</i>"""

        telegram_send(message)
        mark_fired(fire_key)
        fired_this_run.append(symbol)

        # Track outcome for learning
        outcomes.append({
            "id":        alert["id"],
            "symbol":    symbol,
            "type":      alert["type"],
            "target":    alert["target"],
            "fired_at":  datetime.now().isoformat(),
            "price":     data["price"],
            "pct":       data["pct_change"],
        })

    if fired_this_run:
        save_outcomes(outcomes)
        log(AGENT, f"Fired alerts: {fired_this_run}")

    # Also send daily top mover summary at market open (9:30am) if not yet sent
    market_hour_key = f"{AGENT}_daily_mover_{today_str()}"
    if now_hour() == 9 and not was_fired_recently(market_hour_key, hours=20):
        if market:
            top = market[0]
            direction = "▲" if top["pct_change"] >= 0 else "▼"
            context = claude(
                f"Top mover today: {top['symbol']} at ${top['price']:.2f}, {top['pct_change']:+.2f}%. Write one sharp sentence of market context. Plain text only.",
                max_tokens=80
            )
            telegram_send(
                f"📈 <b>Market Open — Top Mover</b>\n\n"
                f"<b>{top['symbol']}</b> ${top['price']:.2f} {direction} {abs(top['pct_change']):.2f}%\n\n"
                f"{context}"
            )
            mark_fired(market_hour_key)
            log(AGENT, f"Daily mover sent: {top['symbol']}")


if __name__ == "__main__":
    run()
