#!/usr/bin/env python3
"""Single entrypoint for all agents. Used by launchd."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 run_agent.py <morning|accountability|adaptive|stock|orchestrator> [mission]")
        sys.exit(1)

    agent = sys.argv[1].lower()

    if agent == "morning":
        from agents.morning import run
        run()
    elif agent == "accountability":
        from agents.accountability import run
        run()
    elif agent == "adaptive":
        from agents.adaptive import run
        run()
    elif agent == "stock":
        from agents.stock_agent import run
        run()
    elif agent == "orchestrator":
        from agents.orchestrator import run
        run()
    elif agent == "music_mood":
        from agents.music_mood import run
        run()
    else:
        print(f"Unknown agent: {agent}")
        sys.exit(1)

if __name__ == "__main__":
    main()
