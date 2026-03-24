#!/usr/bin/env python3
"""
Jordan's Command Center — Telegram edition.
Outputs a formatted briefing to stdout. Claude sends it as a Telegram reply.
Usage: python3 briefing_telegram.py
"""

import sys
from datetime import datetime, date

DAY = date.today().timetuple().tm_yday

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
    "Add a health-check endpoint to one of your services.",
    "Build a dashboard for data you already have.",
    "Create a GitHub Action that automates something tedious.",
    "Prototype the thing you said 'someday I'll build that'.",
    "Turn your messiest notebook into a clean Python module.",
    "Deploy something. Anything. Just ship.",
    "Set up proper logging across your main project.",
    "Write a postmortem for a recent failure — be brutally honest.",
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
    ("Talk is cheap. Show me the code.", "Linus Torvalds"),
    ("The secret of getting ahead is getting started.", "Mark Twain"),
    ("Ideas are cheap. Execution is everything.", "Chris Sacca"),
    ("Perfection is the enemy of done.", "Sheryl Sandberg"),
    ("If you're not embarrassed by the first version of your product, you've launched too late.", "Reid Hoffman"),
    ("Stay hungry, stay foolish.", "Steve Jobs"),
    ("The only way to do great work is to love what you do.", "Steve Jobs"),
    ("In the middle of difficulty lies opportunity.", "Albert Einstein"),
    ("You don't have to be great to start, but you have to start to be great.", "Zig Ziglar"),
    ("Done is better than perfect.", "Sheryl Sandberg"),
    ("Your work is going to fill a large part of your life. Make it great.", "Steve Jobs"),
    ("Simplicity is the soul of efficiency.", "Austin Freeman"),
    ("Any fool can write code a computer understands. Good programmers write code humans understand.", "Martin Fowler"),
    ("Don't worry about failure. Worry about the chances you miss when you don't even try.", "Jack Canfield"),
    ("The computer was born to solve problems that did not exist before.", "Bill Gates"),
    ("Programs must be written for people to read, and only incidentally for machines to execute.", "Harold Abelson"),
]

NUDGES = [
    "That thing you keep pushing off? Do 10 minutes of it RIGHT NOW.",
    "Close Twitter. Open your IDE. Ship something.",
    "You don't need more planning. You need more doing.",
    "The version in your head will never be as good as the one you ship.",
    "Stop consuming. Start creating.",
    "Every hour you delay is an hour your future self has to make up.",
    "What's the ONE thing that moves the needle today? Go do that.",
    "You already know what to do. Stop pretending you don't.",
    "Discipline beats motivation every single time. Get to work.",
    "Future Jordan will thank you for what you do in the next hour.",
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
    "JWT auth from scratch — understand what you're signing",
    "TypeScript generics — write once, type everything",
    "Git bisect — find the commit that broke everything",
    "Linux cron + systemd timers — automate your server",
    "HTTP caching headers — ETag, Cache-Control, and you",
    "Python context managers — clean resource management",
    "Browser DevTools performance tab — profile like a pro",
    "SSH tunneling — access anything, anywhere, securely",
    "Regular expressions — the skill that never goes out of style",
    "SQL indexes — know when to add them and when not to",
    "API rate limiting — token bucket and leaky bucket patterns",
]

GOOD_DEEDS = [
    "Leave a genuine, detailed review for a tool you use daily.",
    "Answer one Stack Overflow question in your area of expertise.",
    "Share a resource that helped you with someone who's learning.",
    "Send a specific compliment to a colleague about their work.",
    "Open-source a script or snippet you use all the time.",
    "Mentor someone for 30 minutes — no agenda, just their questions.",
    "Contribute a docs fix to an open-source project you use.",
    "Check in on someone you haven't talked to in a while.",
    "Buy a coffee for someone on your team.",
    "Introduce two people in your network who should know each other.",
    "Donate to an open-source project on GitHub Sponsors.",
    "Share a job opening with someone you think would crush it.",
    "Say thank you — specifically and directly — to someone who helped you.",
    "Write a LinkedIn recommendation for someone without being asked.",
    "Post one genuinely useful tip on social media.",
    "Report a bug with a proper reproduction case.",
    "Translate a technical concept for a non-technical friend.",
    "Create a cheat sheet on something confusing and post it publicly.",
    "Star a GitHub repo you use and actually appreciate.",
    "Write a positive comment on someone's project or post.",
]


def pick(lst):
    return lst[DAY % len(lst)]


def get_weather():
    try:
        import requests
        resp = requests.get(
            "https://wttr.in/Rockford,IL?format=j1",
            timeout=8,
            headers={"User-Agent": "Jordan-Command-Center/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()
        cur = data["current_condition"][0]
        return {
            "ok": True,
            "temp": cur["temp_F"],
            "feels": cur["FeelsLikeF"],
            "humidity": cur["humidity"],
            "desc": cur["weatherDesc"][0]["value"],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_news():
    try:
        import urllib.request
        import xml.etree.ElementTree as ET
        req = urllib.request.Request(
            "https://feeds.bbci.co.uk/news/rss.xml",
            headers={"User-Agent": "Jordan-Command-Center/1.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            xml_data = r.read()
        root = ET.fromstring(xml_data)
        items = root.findall(".//item")
        headlines = []
        for item in items[:5]:
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            headlines.append({"title": title, "link": link})
        return {"ok": True, "headlines": headlines}
    except Exception as e:
        return {"ok": False, "headlines": [], "error": str(e)}


def get_top_mover():
    try:
        import yfinance as yf
        watchlist = ["NVDA", "AAPL", "TSLA", "MSFT", "META", "AMZN", "GOOGL"]
        best = None
        best_pct = None
        for sym in watchlist:
            try:
                t = yf.Ticker(sym)
                info = t.fast_info
                price = getattr(info, "last_price", None)
                prev = getattr(info, "previous_close", None)
                if price is None or prev is None or prev == 0:
                    hist = t.history(period="2d")
                    if len(hist) >= 2:
                        prev = float(hist["Close"].iloc[-2])
                        price = float(hist["Close"].iloc[-1])
                    else:
                        continue
                else:
                    price = float(price)
                    prev = float(prev)
                pct = (price - prev) / prev * 100
                if best_pct is None or pct > best_pct:
                    best_pct = pct
                    best = {"symbol": sym, "price": price, "pct": pct}
            except Exception:
                continue
        if best:
            return {"ok": True, **best}
        return {"ok": False}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def build_message(weather, news, stock):
    now = datetime.now()
    hour = now.hour
    if 5 <= hour < 12:
        greeting = "Good morning"
        emoji = "🌅"
    elif 12 <= hour < 17:
        greeting = "Good afternoon"
        emoji = "☀️"
    elif 17 <= hour < 21:
        greeting = "Good evening"
        emoji = "🌆"
    else:
        greeting = "Good night"
        emoji = "🌙"

    ts = now.strftime("%A, %b %-d · %-I:%M %p")
    lines = []

    lines.append(f"⚡ *Jordan's Command Center*")
    lines.append(f"{emoji} {greeting}, Jordan\\. _{ts}_")
    lines.append("")

    # Weather
    lines.append("🌤 *WEATHER — Rockford, IL*")
    if weather["ok"]:
        lines.append(f"`{weather['desc']}`")
        lines.append(f"🌡 *{weather['temp']}°F* · Feels like {weather['feels']}°F · 💧 {weather['humidity']}%")
    else:
        lines.append("_Unavailable_")
    lines.append("")

    # Stock
    lines.append("📈 *MARKET SPOTLIGHT*")
    if stock["ok"]:
        arrow = "▲" if stock["pct"] >= 0 else "▼"
        sign = "+" if stock["pct"] >= 0 else ""
        lines.append(f"*{stock['symbol']}* — ${stock['price']:.2f}")
        lines.append(f"{arrow} *{sign}{stock['pct']:.2f}%* today · Top mover from watchlist")
    else:
        lines.append("_Market data unavailable_")
    lines.append("")

    # News
    lines.append("📰 *TOP HEADLINES*")
    if news["ok"] and news["headlines"]:
        for i, h in enumerate(news["headlines"], 1):
            title = h["title"].replace(".", "\\.").replace("!", "\\!").replace("-", "\\-").replace("(", "\\(").replace(")", "\\)").replace("[", "\\[").replace("]", "\\]")
            lines.append(f"{i}\\. {title}")
    else:
        lines.append("_Unavailable_")
    lines.append("")

    # Focus
    focus = pick(BUILD_PROMPTS).replace(".", "\\.").replace("!", "\\!").replace("-", "\\-").replace("'", "\\'")
    lines.append("⚡ *WHAT TO BUILD TODAY*")
    lines.append(focus)
    lines.append("")

    # Nudge
    nudge = pick(NUDGES).replace(".", "\\.").replace("!", "\\!").replace("?", "\\?").replace("-", "\\-").replace("'", "\\'")
    lines.append("🔥 *STOP PROCRASTINATING*")
    lines.append(f"_{nudge}_")
    lines.append("")

    # Quote
    qt, qa = pick(QUOTES)
    qt = qt.replace(".", "\\.").replace("!", "\\!").replace("-", "\\-").replace("'", "\\'").replace(",", "\\,")
    qa = qa.replace(".", "\\.").replace("-", "\\-")
    lines.append("💬 *POWER QUOTE*")
    lines.append(f'_"{qt}"_')
    lines.append(f"— {qa}")
    lines.append("")

    # Affirmation
    aff = pick(AFFIRMATIONS).replace(".", "\\.").replace("'", "\\'").replace("-", "\\-").replace(",", "\\,")
    lines.append("✨ *DAILY AFFIRMATION*")
    lines.append(f"*{aff}*")
    lines.append("")

    # Skill
    skill = pick(SKILLS).replace(".", "\\.").replace("-", "\\-").replace("/", "\\/")
    lines.append("🎯 *SKILL TO LEARN TODAY*")
    lines.append(skill)
    lines.append("")

    # Good Deed
    deed = pick(GOOD_DEEDS).replace(".", "\\.").replace("'", "\\'").replace("-", "\\-").replace(",", "\\,")
    lines.append("🤝 *GOOD DEED*")
    lines.append(deed)

    return "\n".join(lines)


if __name__ == "__main__":
    print("Fetching data...", file=sys.stderr)
    weather = get_weather()
    news = get_news()
    stock = get_top_mover()
    print(build_message(weather, news, stock))
