#!/usr/bin/env python3
"""
Agent 1: Morning Protocol Agent
Runs at 7:00 AM via launchd.

Reads pre-calculated daily_prep from 5 AM EVOLVE phase.
Generates fully adaptive 7-section briefing and sends to Telegram.
Also triggers: sunrise lights, music, dashboard update.
"""

import time, sys, threading, requests
from agents.base import *

AGENT = "morning"

MUSIC_BY_THEME = {
    "discipline":  "hardcore workout",
    "patience":    "lo-fi hip hop",
    "focus":       "instrumental beats",
    "energy":      "Drake",
    "clarity":     "ambient",
    "grind":       "Travis Scott",
    "calm":        "jazz",
    "motivation":  "Kendrick Lamar",
    "deep work":   "classical",
    "default":     "morning vibes",
}


def _sunrise_thread():
    # Starts from dark purple (pre-wake state) → warm → white over 20 min
    transitions = [
        (0,    "purple", 50),   # dark purple — wake trigger
        (60,   "purple", 80),   # purple brightening
        (180,  "warm",   130),  # shift to warm
        (360,  "warm",   190),  # warm brightening
        (540,  "white",  220),  # transition to white
        (720,  "white",  235),  # brighter
        (900,  "cool",   245),  # full daylight
        (1200, "white",  254),  # peak brightness
    ]
    start = time.time()
    for offset_s, color, bri in transitions:
        wait = offset_s - (time.time() - start)
        if wait > 0:
            time.sleep(wait)
        try:
            hub_set_lights(color, bri)
            log(AGENT, f"Sunrise: {color} bri={bri}")
        except Exception as e:
            log(AGENT, f"Sunrise error: {e}")


def get_plan_context() -> dict:
    try:
        from database import im_get_plan
        from datetime import date
        return im_get_plan(date.today().strftime("%Y-%m-%d")) or {}
    except:
        return {}


def get_daily_prep() -> dict:
    """Read 5 AM pre-calculated plan from EVOLVE preparation phase."""
    try:
        from database import daily_prep_get
        return daily_prep_get(today_str()) or {}
    except:
        return {}


def get_rocks_context() -> dict:
    try:
        from database import rocks_get
        rows = rocks_get(today_str())
        result = {"big": [], "medium": [], "small": []}
        for r in rows:
            size = r.get("size", "small")
            if size in result:
                result[size].append(r.get("title", ""))
        return result
    except:
        return {"big": [], "medium": [], "small": []}


def get_news() -> list:
    """Fetch top 3 headlines from BBC RSS with retry."""
    def _fetch():
        import xml.etree.ElementTree as ET
        r = requests.get("http://feeds.bbci.co.uk/news/world/rss.xml", timeout=8)
        root = ET.fromstring(r.text)
        items = root.findall(".//item")[:3]
        return [
            {"title": it.findtext("title", ""), "desc": it.findtext("description", "")}
            for it in items
        ]
    return fetch_with_retry(_fetch, retries=3, fallback=[])


def get_finance_tip() -> str:
    """Generate a finance/market insight via Claude."""
    try:
        from datetime import date
        prompt = f"""Today is {date.today().strftime('%B %d, %Y')}. Jordan is a young investor focused on long-term wealth building.

Give him ONE specific, actionable finance or market insight for today. Could be:
- A market trend or sector move worth watching
- A tactical reminder (rebalancing, contribution, tax consideration)
- A specific stock or crypto observation
- A principle worth applying today

2-3 sentences max. Be specific and useful, not generic."""
        return claude(prompt, max_tokens=120, model="claude-haiku-4-5-20251001")
    except Exception as e:
        log(AGENT, f"Finance tip error: {e}")
        return "Stay consistent with your investment contributions. Time in the market beats timing the market."


def pick_music(plan: dict) -> str:
    theme = (plan.get("mental_theme") or "").lower()
    for key, music in MUSIC_BY_THEME.items():
        if key in theme:
            return music
    return MUSIC_BY_THEME["default"]


def build_full_brief(weather: str, plan: dict, rocks: dict, streaks: list,
                     news: list, prep: dict, finance_tip: str) -> str:
    streak_lines = "\n".join(
        f"  • {s['name'].replace('_',' ')}: {s['current']} day streak"
        for s in streaks if s.get("current", 0) > 0
    ) or "  No active streaks yet."

    big_rocks   = ", ".join(rocks["big"])    or "Not set"
    med_rocks   = ", ".join(rocks["medium"]) or "Not set"
    small_rocks = ", ".join(rocks["small"])  or "Not set"

    news_text = "\n".join(
        f"  • {n['title']}: {n['desc'][:100]}" for n in news
    ) or "  No news available."

    training  = prep.get("adapted_training") or plan.get("training") or "No training scheduled"
    nutrition = prep.get("adapted_nutrition") or plan.get("nutrition_target") or "Clean eating — high protein, stay hydrated"
    theme     = plan.get("mental_theme") or "discipline"
    fatigue   = prep.get("fatigue_score", 0)
    yesterday = int((prep.get("completion_yesterday") or 0) * 100)
    coaching  = prep.get("notes") or ""

    prompt = f"""You are Jordan's personal AI morning briefing system. Generate his complete adaptive daily briefing.

JORDAN'S DATA:
- Weather: {weather}
- Big Rock: {big_rocks}
- Medium Rocks: {med_rocks}
- Small Rocks: {small_rocks}
- Training today: {training}
- Mental theme: {theme}
- Active streaks: {streak_lines}
- Fatigue score: {fatigue}/60 (0=fresh, 60=exhausted)
- Yesterday completion: {yesterday}%
- EVOLVE coaching note: {coaching}
- News: {news_text}
- Nutrition: {nutrition}
- Finance tip: {finance_tip}

OUTPUT — use these exact section headers, plain text, no markdown symbols, no bullet symbols except dashes:

GREETING
Good morning, Jordan. [2-3 sentences: weather-aware tone setter, energy cue based on fatigue score, attack order for the Big Rock]

ROCKS
Big Rock: {big_rocks}
Medium: {med_rocks}
Small: {small_rocks}
[1 sentence on what to hit first and why given today's energy]

TRAINING
[Specific training plan with intensity cues. Adjust if fatigue is high. Reference actual training: {training}]

NUTRITION
[Breakfast. Lunch. Hydration target. 3 lines max.]

NEWS
[3 headlines, 1-2 sentences each]

FINANCE
{finance_tip}

AFFIRMATION
[One sentence — tied to Big Rock, theme, and yesterday's completion. Make it hit hard.]"""

    return claude(prompt, max_tokens=900, model="claude-sonnet-4-6")


def run():
    # Key is date-based — resets at midnight regardless of when it last ran
    dedup_key = f"{AGENT}_morning_{today_str()}"
    if was_fired_recently(dedup_key, hours=20):
        log(AGENT, "Already ran today, skipping.")
        return

    log(AGENT, "=== Morning Protocol starting ===")

    # 1. Sunrise
    t = threading.Thread(target=_sunrise_thread, daemon=True)
    t.start()

    # 2. Gather data (with retry on weather + streaks)
    weather = fetch_with_retry(hub_weather, retries=3, fallback="Weather unavailable")
    plan    = get_plan_context()
    rocks   = get_rocks_context()
    prep    = get_daily_prep()
    streaks = fetch_with_retry(hub_ironmind_streaks, retries=3, fallback=[])
    news    = get_news()
    finance = get_finance_tip()

    log(AGENT, f"Data gathered. Fatigue={prep.get('fatigue_score',0)}, Completion={int((prep.get('completion_yesterday') or 0)*100)}%")

    # 3. Music — wake song first, then theme music
    WAKE_SONG  = "Anywhere Together"
    music_query = pick_music(plan)
    try:
        hub_play_music(WAKE_SONG)
        log(AGENT, f"Wake song: {WAKE_SONG}")
    except Exception as e:
        log(AGENT, f"Wake song error: {e}")

    # 4. Generate briefing
    brief = build_full_brief(weather, plan, rocks, streaks, news, prep, finance)
    log(AGENT, f"Brief generated ({len(brief)} chars)")

    # 5. Build streaks line
    streak_active = [s for s in streaks if s.get("current", 0) > 0]
    streak_text = "  ".join(
        f"🔥 {s['name'].replace('_',' ')} {s['current']}d" for s in streak_active
    ) or "None yet."

    # 6. Send to Telegram
    header = f"⚡ <b>MORNING PROTOCOL — {now_str()}</b>\n\n{weather}\n🎵 {music_query}  ·  {streak_text}\n"
    telegram_send(header + "\n" + brief)

    # 7. Store briefing in DB for dashboard
    try:
        from database import daily_prep_save
        daily_prep_save(today_str(), briefing_text=brief[:2000])
    except Exception as e:
        log(AGENT, f"Briefing store error: {e}")

    # 8. Send email (if configured)
    from datetime import date
    subject = f"Your Daily Protocol — {date.today().strftime('%A, %B %d')}"
    sent = send_email(subject, brief)
    if sent:
        log(AGENT, "Email sent")
    else:
        log(AGENT, "Email not configured or failed — skipping")

    mark_fired(dedup_key)
    log(AGENT, "Morning protocol complete.")

    t.join(timeout=1300)


if __name__ == "__main__":
    run()
