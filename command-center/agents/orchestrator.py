#!/usr/bin/env python3
"""
Agent 5: Adler's Brain — The Orchestrator
A true agentic loop. Give it a mission in natural language.
It reasons, selects tools, executes, observes results, and iterates
until the mission is complete. Reports back via Telegram.

Usage:
  python3 -m agents.orchestrator "run my deep work protocol"
  python3 -m agents.orchestrator "optimize my evening"
  python3 -m agents.orchestrator "check everything and give me a status"
"""

import sys, json
from agents.base import *
from agents import adler_memory, calendar as adler_calendar

AGENT = "orchestrator"

MAX_ITERATIONS = 10

# ── Tool definitions ────────────────────────────────────────────────────────
TOOLS = [
    {
        "name": "get_status",
        "description": "Get current hub status: lights, music (track/artist/playing/volume), time, date.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_weather",
        "description": "Get current weather in Rockford, IL.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "set_lights",
        "description": "Set Philips Hue lights to a color and brightness.",
        "input_schema": {
            "type": "object",
            "properties": {
                "color":      {"type": "string",  "description": "Color: red/orange/yellow/green/cyan/blue/purple/pink/warm/white/cool/off"},
                "brightness": {"type": "integer", "description": "0-254"},
            },
            "required": ["color"],
        },
    },
    {
        "name": "play_music",
        "description": "Play music by artist or song on Apple Music.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Artist, song, or genre to play"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "music_control",
        "description": "Control music playback: pause, resume, skip, back, or set volume.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "enum": ["pause", "resume", "skip", "back", "stop"]},
                "volume":  {"type": "integer", "description": "Volume 0-100 (optional)"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "get_ironmind",
        "description": "Get Jordan's IronMind data: today's metrics, day score, streaks, and plan.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "send_telegram",
        "description": "Send a message to Jordan via Telegram. Use for reports, summaries, or alerts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Plain text or HTML message to send"},
            },
            "required": ["message"],
        },
    },
    {
        "name": "run_command",
        "description": "Send any natural language command to the hub (lights, music, briefing, weather, stock, etc).",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Natural language command"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "get_stock_snapshot",
        "description": "Get current prices and % change for NVDA, AAPL, TSLA, MSFT, META, AMZN, GOOGL.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "remember_fact",
        "description": "Store a fact, preference, or observation about Jordan in long-term memory. Use this when Jordan tells you something explicitly or when you observe something worth remembering.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fact": {"type": "string", "description": "The fact or observation to remember"},
                "category": {"type": "string", "enum": ["fact", "preference_lights", "preference_music", "pattern", "note"], "description": "Category of memory"},
                "context": {"type": "string", "description": "Context key (e.g. 'focus', 'morning') — required for preference categories"},
            },
            "required": ["fact", "category"],
        },
    },
    {
        "name": "recall_memory",
        "description": "Read Adler's full memory — all known facts, preferences, patterns, and past mission outcomes.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_calendar",
        "description": "Get today's calendar events from Apple Calendar, including upcoming meetings and their times.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "mission_complete",
        "description": "Signal that the mission is complete and provide a final summary.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "What was accomplished"},
            },
            "required": ["summary"],
        },
    },
]

BASE_SYSTEM = """You are Adler — the autonomous AI brain of Jordan's Smart Hub in Rockford, IL.
You have tool access to everything: lights, music, IronMind data, weather, stocks, Telegram, calendar, and your own persistent memory.

When given a mission:
1. Read your memory first (recall_memory) if context would help
2. Check calendar if timing matters
3. Gather current state, then act decisively
4. If Jordan tells you something explicitly (a preference, a fact), use remember_fact to store it
5. Call mission_complete when done with a sharp, specific summary

Memory: You have a persistent memory that grows over missions. Use it. Update it. You get smarter every time.
Calendar: You know Jordan's schedule. Don't schedule focus music if he has a meeting in 10 minutes.

Be decisive. Never ask for clarification — reason from context and act. You know Jordan well."""


# ── Tool executor ───────────────────────────────────────────────────────────
def execute_tool(name: str, inputs: dict) -> str:
    log(AGENT, f"Tool: {name}({json.dumps(inputs)[:80]})")

    try:
        if name == "get_status":
            s = hub_status()
            m = s.get("music", {})
            l = s.get("lights", {})
            return (f"Time: {s.get('time')} {s.get('date')}\n"
                    f"Music: {'playing' if m.get('playing') else 'stopped'} — {m.get('track','?')} by {m.get('artist','?')} vol {m.get('volume','?')}%\n"
                    f"Lights: {l.get('color','?')} brightness {l.get('brightness','?')} {'on' if l.get('power') else 'off'}")

        elif name == "get_weather":
            return hub_weather() or "Weather unavailable"

        elif name == "set_lights":
            bri = inputs.get("brightness", 200)
            result = hub_set_lights(inputs["color"], bri)
            return result or f"Lights set to {inputs['color']}"

        elif name == "play_music":
            result = hub_play_music(inputs["query"])
            return result or f"Playing {inputs['query']}"

        elif name == "music_control":
            cmd = inputs["command"]
            vol = inputs.get("volume")
            if vol is not None:
                r = requests.post(f"{HUB_BASE}/music",
                                  json={"command": "volume", "volume": vol}, timeout=10)
                return r.json().get("result", f"Volume → {vol}%")
            r = requests.post(f"{HUB_BASE}/music", json={"command": cmd}, timeout=10)
            return r.json().get("result", f"Music: {cmd}")

        elif name == "get_ironmind":
            log_data = hub_ironmind_log()
            streaks  = hub_ironmind_streaks()
            try:
                plan_r = requests.get(f"{HUB_BASE}/ironmind/plan", timeout=10)
                plan   = plan_r.json().get("result", {})
            except:
                plan = {}
            streak_str = ", ".join(f"{s['name']} {s['current']}d" for s in streaks if s.get("current", 0) > 0)
            return (f"Day score: {log_data.get('score', 0)}/10\n"
                    f"Workout: {'done' if log_data.get('workout_done') else 'not logged'}\n"
                    f"Mood: {log_data.get('mood') or 'not logged'}/10\n"
                    f"Hydration: {log_data.get('hydration_oz') or 'not logged'} oz\n"
                    f"Protein: {log_data.get('protein_g') or 'not logged'} g\n"
                    f"Streaks: {streak_str or 'none active'}\n"
                    f"Plan priorities: {plan.get('priority_1','?')} / {plan.get('priority_2','?')}\n"
                    f"Theme: {plan.get('mental_theme','?')}")

        elif name == "send_telegram":
            ok = telegram_send(inputs["message"])
            return "Telegram sent" if ok else "Telegram send failed"

        elif name == "run_command":
            d = hub_command(inputs["text"])
            return d.get("result", "Command executed")

        elif name == "get_stock_snapshot":
            try:
                import yfinance as yf
                watchlist = ["NVDA", "AAPL", "TSLA", "MSFT", "META", "AMZN", "GOOGL"]
                lines = []
                for sym in watchlist:
                    try:
                        t = yf.Ticker(sym)
                        info = t.fast_info
                        price = float(getattr(info, "last_price", 0) or 0)
                        prev  = float(getattr(info, "previous_close", 0) or 0)
                        if price and prev:
                            pct = (price - prev) / prev * 100
                            lines.append(f"{sym}: ${price:.2f} ({pct:+.2f}%)")
                    except:
                        continue
                return "\n".join(lines) or "No data available"
            except Exception as e:
                return f"Stock error: {e}"

        elif name == "remember_fact":
            fact = inputs["fact"]
            category = inputs.get("category", "fact")
            context = inputs.get("context", "")
            if category == "fact":
                adler_memory.add_fact(fact)
            elif category == "pattern":
                mem = adler_memory.load()
                mem["patterns"].append(fact)
                mem["patterns"] = mem["patterns"][-20:]
                adler_memory.save(mem)
            elif category == "note":
                mem = adler_memory.load()
                mem["notes"].append(fact)
                mem["notes"] = mem["notes"][-20:]
                adler_memory.save(mem)
            elif category.startswith("preference_"):
                cat = category.replace("preference_", "")
                adler_memory.update_preference(cat, context or "general", fact)
            return f"Memory updated: [{category}] {fact}"

        elif name == "recall_memory":
            mem = adler_memory.load()
            return adler_memory.format_for_prompt(mem)

        elif name == "get_calendar":
            return adler_calendar.get_context_string()

        elif name == "mission_complete":
            return f"MISSION_COMPLETE: {inputs['summary']}"

        else:
            return f"Unknown tool: {name}"

    except Exception as e:
        log(AGENT, f"Tool error {name}: {e}")
        return f"Error: {e}"


# ── Agent loop ──────────────────────────────────────────────────────────────
def build_system_prompt() -> str:
    """Build Adler's full system prompt: base + memory snapshot + calendar."""
    parts = [BASE_SYSTEM, ""]
    try:
        mem = adler_memory.load()
        parts.append(adler_memory.format_for_prompt(mem))
    except Exception as e:
        parts.append(f"[Memory unavailable: {e}]")
    try:
        cal = adler_calendar.get_context_string()
        parts.append("\n" + cal)
    except Exception as e:
        parts.append(f"[Calendar unavailable: {e}]")
    return "\n".join(parts)


def run_mission(mission: str, notify_telegram: bool = True) -> str:
    log(AGENT, f"=== Mission: {mission} ===")

    if notify_telegram:
        telegram_send(f"🤖 <b>Adler activated</b>\nMission: <i>{mission}</i>")

    system_prompt = build_system_prompt()
    messages = [{"role": "user", "content": mission}]
    final_summary = ""
    iterations = 0
    tools_used = []

    while iterations < MAX_ITERATIONS:
        iterations += 1
        log(AGENT, f"Iteration {iterations}")

        response = claude_tools(messages, TOOLS, system=system_prompt,
                                model="claude-haiku-4-5-20251001", max_tokens=1500)

        stop_reason = response.get("stop_reason")
        content     = response.get("content", [])

        # Add assistant turn to messages
        messages.append({"role": "assistant", "content": content})

        if stop_reason == "end_turn":
            # Extract any text response
            for block in content:
                if block.get("type") == "text":
                    final_summary = block["text"]
            log(AGENT, f"Agent finished naturally: {final_summary[:80]}")
            break

        if stop_reason != "tool_use":
            log(AGENT, f"Unexpected stop_reason: {stop_reason}")
            break

        # Execute tool calls
        tool_results = []
        mission_done = False

        for block in content:
            if block.get("type") != "tool_use":
                continue

            tool_name   = block["name"]
            tool_inputs = block.get("input", {})
            tool_use_id = block["id"]

            result = execute_tool(tool_name, tool_inputs)
            tools_used.append(tool_name)
            log(AGENT, f"  → {result[:100]}")

            tool_results.append({
                "type":        "tool_result",
                "tool_use_id": tool_use_id,
                "content":     result,
            })

            if tool_name == "mission_complete":
                final_summary = tool_inputs.get("summary", "Mission complete.")
                mission_done = True

        # Add tool results to conversation
        messages.append({"role": "user", "content": tool_results})

        if mission_done:
            break

    log(AGENT, f"=== Mission complete after {iterations} iterations ===")
    log(AGENT, f"Summary: {final_summary}")

    # Record to Adler's memory
    try:
        adler_memory.record_mission(mission, final_summary, tools_used)
    except Exception as e:
        log(AGENT, f"Memory record error: {e}")

    if notify_telegram and final_summary:
        telegram_send(
            f"✅ <b>Mission complete</b>\n\n{final_summary}\n\n"
            f"<i>{iterations} steps · {len(tools_used)} tool calls</i>"
        )

    return final_summary


def run():
    """CLI entrypoint: python3 -m agents.orchestrator 'your mission'"""
    if len(sys.argv) < 2:
        print("Usage: python3 -m agents.orchestrator 'your mission'")
        print("\nExamples:")
        print("  python3 -m agents.orchestrator 'run my morning protocol'")
        print("  python3 -m agents.orchestrator 'optimize my evening'")
        print("  python3 -m agents.orchestrator 'check everything and report'")
        print("  python3 -m agents.orchestrator 'deep work mode'")
        sys.exit(1)

    mission = " ".join(sys.argv[1:])
    result = run_mission(mission, notify_telegram=True)
    print(f"\nResult: {result}")


if __name__ == "__main__":
    run()
