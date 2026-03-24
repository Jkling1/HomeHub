#!/usr/bin/env python3
"""
Jordan's Command Center — AI-powered daily briefing generator.
Generates a self-contained HTML dashboard and opens it in the browser.
"""

import subprocess
import sys
import os
from datetime import datetime, timezone

# ── Rotating content lists ────────────────────────────────────────────────────

BUILD_PROMPTS = [
    "Ship one feature end-to-end — from idea to deployed.",
    "Write a README that makes strangers want to use your project.",
    "Refactor one file until you're genuinely proud of it.",
    "Add tests to the module you're most afraid to touch.",
    "Build a CLI tool that solves a real daily annoyance.",
    "Create a reusable component and document every prop.",
    "Audit your dependencies — remove what you don't need.",
    "Record a 2-minute demo of something you built.",
    "Open-source one internal utility you use constantly.",
    "Fix the bug you've been ignoring for two weeks.",
    "Design the data model first, then write the code.",
    "Write one script that saves you an hour of manual work.",
    "Implement dark mode for a project that doesn't have it.",
    "Add a health-check endpoint to one of your services.",
    "Build a dashboard for data you already have.",
    "Create a GitHub Action that automates something tedious.",
    "Write a postmortem for a recent failure — be brutally honest.",
    "Prototype the thing you said 'someday I'll build that'.",
    "Turn your messiest notebook into a clean Python module.",
    "Deploy something. Anything. Just ship.",
]

AFFIRMATIONS = [
    "I build things that matter and I'm just getting started.",
    "Every line of code I write is one step closer to mastery.",
    "Challenges are the curriculum. I'm always in school.",
    "I solve hard problems because I've solved hard problems before.",
    "My curiosity is my competitive advantage.",
    "I ship imperfect things and improve them. That's the cycle.",
    "I don't wait for permission. I build and ask for forgiveness.",
    "The work I do today compounds into the future I want.",
    "I am capable of learning anything I decide to focus on.",
    "My best code is always the next thing I write.",
    "I embrace the discomfort of not knowing — it means I'm growing.",
    "I make deliberate decisions and own the outcomes.",
    "I have rare skills and I'm making them rarer every day.",
    "I am the kind of person who finishes what they start.",
    "I create value from nothing but ideas and execution.",
    "My consistency is more powerful than anyone's talent.",
    "I am exactly where I need to be to get where I'm going.",
    "I don't just consume technology — I create with it.",
    "Setbacks are data. I iterate, not catastrophize.",
    "I build in public, fail in public, and grow in public.",
]

QUOTES = [
    ("The best time to plant a tree was 20 years ago. The second best time is now.", "Chinese Proverb"),
    ("Move fast and break things.", "Mark Zuckerberg"),
    ("Make something people want.", "Paul Graham"),
    ("First, solve the problem. Then, write the code.", "John Johnson"),
    ("Simplicity is the soul of efficiency.", "Austin Freeman"),
    ("The function of good software is to make the complex appear simple.", "Grady Booch"),
    ("Talk is cheap. Show me the code.", "Linus Torvalds"),
    ("The most dangerous phrase in the language is: we've always done it this way.", "Grace Hopper"),
    ("It's not a bug — it's an undocumented feature.", "Anonymous"),
    ("Any fool can write code that a computer can understand. Good programmers write code that humans can understand.", "Martin Fowler"),
    ("The secret of getting ahead is getting started.", "Mark Twain"),
    ("You don't have to be great to start, but you have to start to be great.", "Zig Ziglar"),
    ("Ideas are cheap. Execution is everything.", "Chris Sacca"),
    ("Perfection is the enemy of done.", "Sheryl Sandberg"),
    ("If you're not embarrassed by the first version of your product, you've launched too late.", "Reid Hoffman"),
    ("Stay hungry, stay foolish.", "Steve Jobs"),
    ("The only way to do great work is to love what you do.", "Steve Jobs"),
    ("Programs must be written for people to read, and only incidentally for machines to execute.", "Harold Abelson"),
    ("The computer was born to solve problems that did not exist before.", "Bill Gates"),
    ("In the middle of difficulty lies opportunity.", "Albert Einstein"),
]

SKILLS = [
    "WebSockets — build a real-time feature today",
    "Docker multi-stage builds — cut your image size in half",
    "PostgreSQL window functions — analytics without a framework",
    "Python asyncio — concurrency that doesn't melt your brain",
    "Redis pub/sub — decouple your services with a message bus",
    "GitHub Actions matrix builds — test across multiple versions",
    "Terraform basics — provision cloud infra as code",
    "Nginx reverse proxy — configure upstreams and caching",
    "SQL query explain plans — find what's killing your DB",
    "Python dataclasses — replace dicts with typed structures",
    "CSS Grid layout — master two-dimensional layouts",
    "JWT auth from scratch — understand what you're signing",
    "REST API pagination — cursor vs offset, choose wisely",
    "Python logging — structured logs your future self will thank",
    "TypeScript generics — write once, type everything",
    "Git bisect — find the commit that broke everything",
    "Linux cron + systemd timers — automate your server",
    "HTTP caching headers — ETag, Cache-Control, and you",
    "Python context managers — clean resource management",
    "OpenAPI / Swagger — document your API automatically",
    "Browser DevTools performance tab — profile like a pro",
    "SSH tunneling — access anything, anywhere, securely",
    "Python comprehensions — lists, dicts, sets, generators",
    "Makefile basics — standardize your project commands",
    "Regular expressions — the skill that never goes out of style",
    "SQL indexes — know when to add them and when not to",
    "Environment variables and .env files — 12-factor app basics",
    "Python virtual environments — keep projects isolated",
    "Webhook design — push vs pull and idempotency",
    "API rate limiting — token bucket and leaky bucket patterns",
]

GOOD_DEEDS = [
    "Leave a genuine, detailed review for a tool you use daily.",
    "Answer one Stack Overflow question in your area of expertise.",
    "Share a resource that helped you with someone who's learning.",
    "Send a specific compliment to a colleague about their work.",
    "Open-source a script or snippet you use all the time.",
    "Write up and share a solution to a problem you recently solved.",
    "Mentor someone for 30 minutes — no agenda, just their questions.",
    "Contribute a docs fix to an open-source project you use.",
    "Post a tutorial on something you had to figure out the hard way.",
    "Give a thoughtful star + comment on a GitHub project you admire.",
    "Check in on someone you haven't talked to in a while.",
    "Report a bug with a proper reproduction case (the maintainer will love you).",
    "Translate a technical concept for a non-technical friend or family member.",
    "Introduce two people in your network who should know each other.",
    "Buy a coffee for someone on your team — virtually or physically.",
    "Write a LinkedIn recommendation for someone without being asked.",
    "Donate to an open-source project on GitHub Sponsors or Open Collective.",
    "Share a job opening with someone you think would crush it.",
    "Create a cheat sheet on something confusing and post it publicly.",
    "Say thank you — specifically and directly — to someone who helped you.",
]

PROCRASTINATION_NUDGES = [
    "You've been meaning to do this for days. Open the file. Right now.",
    "The perfect time is a myth. The only time is now.",
    "You're not waiting for inspiration — you're hiding from execution.",
    "Every minute you delay, someone else is shipping.",
    "Fear dressed up as 'not ready yet' is still fear.",
    "You already know what to do. That's why you're not doing it.",
    "Done is infinitely more valuable than perfect in your head.",
    "The resistance you feel right now is the signal — push through it.",
    "Close the tabs. Open the editor. Start with one line.",
    "Future you is begging present you to just start. Listen.",
]

# ── Data fetching ─────────────────────────────────────────────────────────────

def get_weather():
    """Fetch weather for Rockford, IL from wttr.in."""
    try:
        import requests
        resp = requests.get(
            "https://wttr.in/Rockford,IL?format=j1",
            timeout=8,
            headers={"User-Agent": "Jordan-Command-Center/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()
        current = data["current_condition"][0]
        temp_f = current["temp_F"]
        feels_like_f = current["FeelsLikeF"]
        humidity = current["humidity"]
        description = current["weatherDesc"][0]["value"]
        return {
            "temp": temp_f,
            "feels_like": feels_like_f,
            "humidity": humidity,
            "description": description,
            "ok": True,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_news():
    """Fetch top 5 BBC headlines via RSS."""
    headlines = []
    try:
        import urllib.request
        import xml.etree.ElementTree as ET

        url = "https://feeds.bbci.co.uk/news/rss.xml"
        req = urllib.request.Request(url, headers={"User-Agent": "Jordan-Command-Center/1.0"})
        with urllib.request.urlopen(req, timeout=8) as response:
            xml_data = response.read()

        root = ET.fromstring(xml_data)
        ns = {"media": "http://search.yahoo.com/mrss/"}
        items = root.findall(".//item")
        for item in items[:5]:
            title_el = item.find("title")
            link_el = item.find("link")
            desc_el = item.find("description")
            title = title_el.text.strip() if title_el is not None and title_el.text else "No title"
            link = link_el.text.strip() if link_el is not None and link_el.text else "#"
            desc = desc_el.text.strip() if desc_el is not None and desc_el.text else ""
            headlines.append({"title": title, "link": link, "desc": desc})
        return {"ok": True, "headlines": headlines}
    except Exception as e:
        return {"ok": False, "error": str(e), "headlines": []}


def get_top_mover():
    """Use yfinance to find the top gainer in the watchlist today."""
    watchlist = ["NVDA", "AAPL", "TSLA", "MSFT", "META", "AMZN", "GOOGL"]
    try:
        import yfinance as yf

        best = None
        best_pct = None

        for ticker in watchlist:
            try:
                t = yf.Ticker(ticker)
                info = t.fast_info
                price = getattr(info, "last_price", None)
                prev_close = getattr(info, "previous_close", None)
                if price is None or prev_close is None or prev_close == 0:
                    # fallback: try history
                    hist = t.history(period="2d")
                    if len(hist) >= 2:
                        prev_close = float(hist["Close"].iloc[-2])
                        price = float(hist["Close"].iloc[-1])
                    else:
                        continue
                else:
                    price = float(price)
                    prev_close = float(prev_close)

                pct = ((price - prev_close) / prev_close) * 100
                if best_pct is None or pct > best_pct:
                    best_pct = pct
                    best = {"ticker": ticker, "price": price, "pct": pct}
            except Exception:
                continue

        if best:
            return {"ok": True, **best}
        return {"ok": False, "error": "No data available"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── HTML generation ───────────────────────────────────────────────────────────

def escape_html(text):
    """Minimal HTML escaping."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_html(now, weather, news, mover, build_prompt, affirmation, quote, skill, good_deed, nudge):
    hour = now.hour
    if 5 <= hour < 12:
        greeting_time = "Good morning"
        greeting_emoji = "🌅"
    elif 12 <= hour < 17:
        greeting_time = "Good afternoon"
        greeting_emoji = "☀️"
    elif 17 <= hour < 21:
        greeting_time = "Good evening"
        greeting_emoji = "🌆"
    else:
        greeting_time = "Good night"
        greeting_emoji = "🌙"

    timestamp = now.strftime("%A, %B %-d, %Y at %-I:%M %p")

    # Weather card
    if weather["ok"]:
        temp = weather["temp"]
        feels = weather["feels_like"]
        humidity = weather["humidity"]
        desc = escape_html(weather["description"])
        weather_html = f"""
            <div class="stat-row">
                <span class="stat-label">Condition</span>
                <span class="stat-value">{desc}</span>
            </div>
            <div class="stat-row">
                <span class="stat-label">Temperature</span>
                <span class="stat-value accent">{temp}°F</span>
            </div>
            <div class="stat-row">
                <span class="stat-label">Feels Like</span>
                <span class="stat-value">{feels}°F</span>
            </div>
            <div class="stat-row">
                <span class="stat-label">Humidity</span>
                <span class="stat-value">{humidity}%</span>
            </div>
        """
    else:
        weather_html = '<p class="unavailable">Weather unavailable</p>'

    # News card
    if news["ok"] and news["headlines"]:
        news_items = ""
        for i, h in enumerate(news["headlines"], 1):
            title = escape_html(h["title"])
            link = escape_html(h["link"])
            news_items += f'<div class="news-item"><span class="news-num">{i:02d}</span><a href="{link}" target="_blank" class="news-link">{title}</a></div>\n'
        news_html = news_items
    else:
        news_html = '<p class="unavailable">News unavailable</p>'

    # Stock card
    if mover["ok"]:
        ticker = escape_html(mover["ticker"])
        price = f"${mover['price']:.2f}"
        pct = mover["pct"]
        pct_class = "gain" if pct >= 0 else "loss"
        pct_sign = "+" if pct >= 0 else ""
        pct_str = f"{pct_sign}{pct:.2f}%"
        stock_html = f"""
            <div class="stock-hero">
                <div class="stock-ticker">{ticker}</div>
                <div class="stock-price">{price}</div>
                <div class="stock-pct {pct_class}">{pct_str}</div>
                <div class="stock-label">Today's Top Mover</div>
            </div>
        """
    else:
        stock_html = '<p class="unavailable">Market data unavailable</p>'

    quote_text, quote_author = quote

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Jordan's Command Center</title>
<style>
  :root {{
    --bg: #0d1117;
    --bg-card: #161b22;
    --bg-card-hover: #1c2330;
    --border: #30363d;
    --accent: #00ff88;
    --accent-dim: #00cc6a;
    --accent-glow: rgba(0, 255, 136, 0.15);
    --text: #e6edf3;
    --text-muted: #8b949e;
    --text-dim: #6e7681;
    --red: #ff4d4d;
    --green: #00ff88;
    --mono: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Courier New', monospace;
    --sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    background: var(--bg);
    color: var(--text);
    font-family: var(--sans);
    min-height: 100vh;
    padding: 0;
  }}

  /* ── Header ── */
  .header {{
    background: linear-gradient(135deg, #0d1117 0%, #161b22 50%, #0d1117 100%);
    border-bottom: 1px solid var(--border);
    padding: 2rem 2.5rem 1.75rem;
    position: relative;
    overflow: hidden;
  }}

  .header::before {{
    content: '';
    position: absolute;
    top: -50%;
    left: -10%;
    width: 40%;
    height: 200%;
    background: radial-gradient(ellipse, rgba(0,255,136,0.06) 0%, transparent 60%);
    pointer-events: none;
  }}

  .header-inner {{
    max-width: 1400px;
    margin: 0 auto;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 1rem;
  }}

  .header-title {{
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }}

  .header-logo {{
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }}

  .logo-dot {{
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 12px var(--accent);
    animation: pulse 2s ease-in-out infinite;
  }}

  @keyframes pulse {{
    0%, 100% {{ opacity: 1; box-shadow: 0 0 12px var(--accent); }}
    50% {{ opacity: 0.6; box-shadow: 0 0 4px var(--accent); }}
  }}

  h1 {{
    font-size: 1.75rem;
    font-weight: 700;
    font-family: var(--mono);
    color: var(--text);
    letter-spacing: -0.02em;
  }}

  h1 span {{ color: var(--accent); }}

  .header-subtitle {{
    font-size: 0.85rem;
    color: var(--text-muted);
    font-family: var(--mono);
    letter-spacing: 0.05em;
  }}

  .header-meta {{
    text-align: right;
  }}

  .greeting {{
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--accent);
    font-family: var(--mono);
  }}

  .timestamp {{
    font-size: 0.78rem;
    color: var(--text-dim);
    font-family: var(--mono);
    margin-top: 0.3rem;
  }}

  /* ── Main grid ── */
  .main {{
    max-width: 1400px;
    margin: 2rem auto;
    padding: 0 2rem 4rem;
  }}

  .grid {{
    display: grid;
    grid-template-columns: repeat(12, 1fr);
    gap: 1.25rem;
  }}

  /* ── Cards ── */
  .card {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.5rem;
    transition: border-color 0.2s, background 0.2s;
    position: relative;
    overflow: hidden;
  }}

  .card:hover {{
    border-color: rgba(0,255,136,0.3);
    background: var(--bg-card-hover);
  }}

  .card::after {{
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 2px;
    background: linear-gradient(90deg, transparent, var(--accent), transparent);
    opacity: 0;
    transition: opacity 0.2s;
  }}

  .card:hover::after {{ opacity: 0.5; }}

  .card-icon {{
    font-size: 1.1rem;
    margin-right: 0.5rem;
  }}

  .card-label {{
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--text-dim);
    font-family: var(--mono);
    font-weight: 600;
    margin-bottom: 1rem;
    display: flex;
    align-items: center;
  }}

  /* ── Span classes ── */
  .col-4  {{ grid-column: span 4; }}
  .col-5  {{ grid-column: span 5; }}
  .col-6  {{ grid-column: span 6; }}
  .col-7  {{ grid-column: span 7; }}
  .col-8  {{ grid-column: span 8; }}
  .col-12 {{ grid-column: span 12; }}

  /* ── Stat rows (weather) ── */
  .stat-row {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem 0;
    border-bottom: 1px solid rgba(48,54,61,0.5);
  }}
  .stat-row:last-child {{ border-bottom: none; }}
  .stat-label {{
    font-size: 0.82rem;
    color: var(--text-muted);
    font-family: var(--mono);
  }}
  .stat-value {{
    font-size: 0.9rem;
    font-family: var(--mono);
    font-weight: 600;
  }}
  .stat-value.accent {{ color: var(--accent); }}

  /* ── News ── */
  .news-item {{
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
    padding: 0.6rem 0;
    border-bottom: 1px solid rgba(48,54,61,0.4);
  }}
  .news-item:last-child {{ border-bottom: none; }}
  .news-num {{
    font-size: 0.7rem;
    font-family: var(--mono);
    color: var(--accent);
    font-weight: 700;
    min-width: 20px;
    padding-top: 0.1rem;
  }}
  .news-link {{
    font-size: 0.85rem;
    color: var(--text);
    text-decoration: none;
    line-height: 1.4;
    transition: color 0.15s;
  }}
  .news-link:hover {{ color: var(--accent); }}

  /* ── Stock ── */
  .stock-hero {{
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    padding: 1.5rem 0 0.5rem;
    gap: 0.4rem;
  }}
  .stock-ticker {{
    font-size: 2rem;
    font-family: var(--mono);
    font-weight: 700;
    color: var(--text);
    letter-spacing: 0.08em;
  }}
  .stock-price {{
    font-size: 2.5rem;
    font-family: var(--mono);
    font-weight: 700;
    color: var(--accent);
    line-height: 1;
  }}
  .stock-pct {{
    font-size: 1.2rem;
    font-family: var(--mono);
    font-weight: 700;
    padding: 0.3rem 0.8rem;
    border-radius: 20px;
  }}
  .stock-pct.gain {{ color: var(--green); background: rgba(0,255,136,0.1); }}
  .stock-pct.loss {{ color: var(--red); background: rgba(255,77,77,0.1); }}
  .stock-label {{
    font-size: 0.72rem;
    color: var(--text-dim);
    font-family: var(--mono);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-top: 0.25rem;
  }}

  /* ── Quote ── */
  .quote-text {{
    font-size: 1.05rem;
    line-height: 1.65;
    color: var(--text);
    font-style: italic;
    margin-bottom: 0.75rem;
  }}
  .quote-author {{
    font-size: 0.78rem;
    font-family: var(--mono);
    color: var(--accent);
  }}

  /* ── Big text cards (affirmation, nudge) ── */
  .big-text {{
    font-size: 1rem;
    line-height: 1.6;
    color: var(--text);
  }}
  .big-text.accent-text {{
    color: var(--accent);
    font-size: 1.05rem;
  }}

  /* ── Pill cards (skill, good deed) ── */
  .pill-label {{
    display: inline-block;
    background: var(--accent-glow);
    border: 1px solid rgba(0,255,136,0.3);
    color: var(--accent);
    font-family: var(--mono);
    font-size: 0.7rem;
    padding: 0.2rem 0.6rem;
    border-radius: 20px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 0.75rem;
  }}

  /* ── Build prompt card ── */
  .build-number {{
    font-size: 3rem;
    font-family: var(--mono);
    font-weight: 700;
    color: var(--accent);
    opacity: 0.15;
    position: absolute;
    top: 1rem;
    right: 1.5rem;
    line-height: 1;
    pointer-events: none;
  }}
  .build-text {{
    font-size: 1.15rem;
    line-height: 1.5;
    font-weight: 600;
    color: var(--text);
    position: relative;
  }}

  /* ── Unavailable ── */
  .unavailable {{
    color: var(--text-dim);
    font-family: var(--mono);
    font-size: 0.85rem;
    padding: 0.75rem 0;
  }}

  /* ── Footer ── */
  .footer {{
    text-align: center;
    padding: 2rem;
    border-top: 1px solid var(--border);
    font-size: 0.75rem;
    color: var(--text-dim);
    font-family: var(--mono);
    max-width: 1400px;
    margin: 0 auto;
  }}

  /* ── Responsive ── */
  @media (max-width: 1100px) {{
    .col-4 {{ grid-column: span 6; }}
    .col-5 {{ grid-column: span 6; }}
    .col-7 {{ grid-column: span 6; }}
    .col-8 {{ grid-column: span 12; }}
  }}

  @media (max-width: 720px) {{
    .col-4, .col-5, .col-6, .col-7, .col-8 {{ grid-column: span 12; }}
    h1 {{ font-size: 1.3rem; }}
    .header {{ padding: 1.25rem; }}
    .main {{ padding: 0 1rem 3rem; }}
  }}

  /* ── Scrollbar ── */
  ::-webkit-scrollbar {{ width: 6px; }}
  ::-webkit-scrollbar-track {{ background: var(--bg); }}
  ::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 3px; }}
</style>
</head>
<body>

<header class="header">
  <div class="header-inner">
    <div class="header-title">
      <div class="header-logo">
        <div class="logo-dot"></div>
        <h1>Jordan's <span>Command Center</span></h1>
      </div>
      <div class="header-subtitle">// daily briefing &amp; operations dashboard</div>
    </div>
    <div class="header-meta">
      <div class="greeting">{greeting_emoji} {greeting_time}, Jordan</div>
      <div class="timestamp">Last refreshed: {escape_html(timestamp)}</div>
    </div>
  </div>
</header>

<main class="main">
  <div class="grid">

    <!-- Weather -->
    <div class="card col-4">
      <div class="card-label"><span class="card-icon">🌤</span> Rockford, IL — Weather</div>
      {weather_html}
    </div>

    <!-- Stock Pick -->
    <div class="card col-4">
      <div class="card-label"><span class="card-icon">📈</span> Market Spotlight</div>
      {stock_html}
    </div>

    <!-- Build Today -->
    <div class="card col-4">
      <div class="card-label"><span class="card-icon">⚡</span> What to Build Today</div>
      <div class="build-number">!</div>
      <div class="build-text">{escape_html(build_prompt)}</div>
    </div>

    <!-- News -->
    <div class="card col-7">
      <div class="card-label"><span class="card-icon">📰</span> Top Headlines — BBC News</div>
      {news_html}
    </div>

    <!-- Quote -->
    <div class="card col-5">
      <div class="card-label"><span class="card-icon">💬</span> Power Quote</div>
      <div class="quote-text">"{escape_html(quote_text)}"</div>
      <div class="quote-author">— {escape_html(quote_author)}</div>
    </div>

    <!-- Affirmation -->
    <div class="card col-6">
      <div class="card-label"><span class="card-icon">🧠</span> Daily Affirmation</div>
      <div class="big-text accent-text">{escape_html(affirmation)}</div>
    </div>

    <!-- Stop Procrastinating -->
    <div class="card col-6">
      <div class="card-label"><span class="card-icon">🔥</span> Stop Procrastinating</div>
      <div class="big-text">{escape_html(nudge)}</div>
    </div>

    <!-- Skill -->
    <div class="card col-6">
      <div class="card-label"><span class="card-icon">🎯</span> Skill to Learn Today</div>
      <div class="pill-label">Dev / Tech</div>
      <div class="big-text">{escape_html(skill)}</div>
    </div>

    <!-- Good Deed -->
    <div class="card col-6">
      <div class="card-label"><span class="card-icon">🤝</span> Good Deed of the Day</div>
      <div class="pill-label">Community</div>
      <div class="big-text">{escape_html(good_deed)}</div>
    </div>

  </div>
</main>

<footer class="footer">
  Jordan's Command Center &nbsp;·&nbsp; Generated {escape_html(timestamp)} &nbsp;·&nbsp; Powered by wttr.in · BBC RSS · yfinance
</footer>

</body>
</html>"""

    return html


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    now = datetime.now()
    day_of_year = now.timetuple().tm_yday  # 1–366

    # Rotating picks
    build_prompt = BUILD_PROMPTS[day_of_year % len(BUILD_PROMPTS)]
    affirmation  = AFFIRMATIONS[day_of_year % len(AFFIRMATIONS)]
    quote        = QUOTES[day_of_year % len(QUOTES)]
    skill        = SKILLS[day_of_year % len(SKILLS)]
    good_deed    = GOOD_DEEDS[day_of_year % len(GOOD_DEEDS)]
    nudge        = PROCRASTINATION_NUDGES[day_of_year % len(PROCRASTINATION_NUDGES)]

    print("Jordan's Command Center — building your briefing...\n")

    print("  Fetching weather...", end=" ", flush=True)
    weather = get_weather()
    print("OK" if weather["ok"] else f"FAILED ({weather.get('error', '')})")

    print("  Fetching news...", end=" ", flush=True)
    news = get_news()
    print(f"OK ({len(news['headlines'])} headlines)" if news["ok"] else f"FAILED ({news.get('error', '')})")

    print("  Fetching stock data...", end=" ", flush=True)
    mover = get_top_mover()
    if mover["ok"]:
        print(f"OK (top mover: {mover['ticker']} {mover['pct']:+.2f}%)")
    else:
        print(f"FAILED ({mover.get('error', '')})")

    print("\n  Generating HTML...", end=" ", flush=True)
    html = build_html(now, weather, news, mover, build_prompt, affirmation, quote, skill, good_deed, nudge)

    output_path = "/tmp/command_center.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print("OK")

    print(f"  Saved to {output_path}")
    print("\n  Opening in browser...")
    subprocess.run(["open", output_path])
    print("\nCommand Center is ready. Have a great day, Jordan.\n")


if __name__ == "__main__":
    main()
