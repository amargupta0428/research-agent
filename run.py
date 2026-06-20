"""CLI entry point.

    python run.py "competitive brief on Notion: who competes and how do they price?"

Streams the trace to the terminal as it happens and saves the full run
(trace JSONL + markdown) under runs/.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from agent.loop import run_agent
from agent.trace import TraceEvent

RUNS_DIR = Path(__file__).parent / "runs"

# ANSI colors for a legible live trace
C = {
    "dim": "\033[2m",
    "b": "\033[1m",
    "cyan": "\033[36m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "mag": "\033[35m",
    "reset": "\033[0m",
}


def _print_event(ev: TraceEvent) -> None:
    d = ev.data
    if ev.kind == "goal":
        print(f"{C['b']}🎯 GOAL:{C['reset']} {d['goal']}")
        print(
            f"{C['dim']}   apify={'on' if d['apify'] else 'off'}  "
            f"budget={d['budget']}{C['reset']}\n"
        )
    elif ev.kind == "plan":
        print(f"{C['cyan']}{C['b']}── Step {ev.step} · PLAN ──{C['reset']}")
        if d.get("evaluation"):
            print(f"{C['dim']}{d['evaluation']}{C['reset']}")
    elif ev.kind == "tool_call":
        inp = {k: v for k, v in d["input"].items() if k not in ("subquestion", "rationale")}
        print(f"{C['mag']}  ▶ ACT {d['tool']}{C['reset']} {inp}")
        if d.get("subquestion"):
            print(f"{C['dim']}    ↳ sub-q: {d['subquestion']}{C['reset']}")
    elif ev.kind == "observation":
        col = C["green"] if d["quality"] == "ok" else C["yellow"]
        summary = d["summary"]
        summary = summary if len(summary) < 600 else summary[:600] + "…"
        print(f"{col}  ◀ OBSERVE [{d['quality']}]{C['reset']} {summary}")
    elif ev.kind == "recovery":
        print(
            f"{C['yellow']}{C['b']}  ♻ RE-ROUTE:{C['reset']} {C['yellow']}{d['reason']}{C['reset']}"
        )
    elif ev.kind == "budget":
        print(f"{C['red']}{C['b']}  ⛔ BUDGET:{C['reset']} {d['reason']}")
    elif ev.kind == "error":
        print(f"{C['red']}  ⚠ ERROR: {d['message']}{C['reset']}")
    elif ev.kind == "finish":
        print(f"\n{C['green']}{C['b']}══ FINAL ANSWER ══{C['reset']}")
        print(d.get("answer", ""))
        if d.get("citations"):
            print(f"\n{C['b']}Sources:{C['reset']}")
            for c in d["citations"]:
                print(f"  [{c.get('id')}] {c.get('title', '')} — {c.get('url', '')}")
        print(
            f"\n{C['dim']}confidence={d.get('confidence', '')}  "
            f"gaps={d.get('open_gaps', '')}{C['reset']}"
        )
        print(
            f"{C['dim']}steps={ev.step} tokens={d.get('tokens')} "
            f"tool_calls={d.get('tool_calls')} apify={d.get('apify_runs')} "
            f"elapsed={d.get('elapsed')}s  stop={d.get('stopped_reason')}{C['reset']}"
        )


def main() -> None:
    if len(sys.argv) < 2:
        print('Usage: python run.py "<research goal>"')
        sys.exit(1)
    goal = " ".join(sys.argv[1:])

    result = run_agent(goal, sink=_print_event)

    # Persist the run.
    RUNS_DIR.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    slug = "".join(c if c.isalnum() else "-" for c in goal.lower())[:40].strip("-")
    base = RUNS_DIR / f"{stamp}-{slug}"
    result["trace"].save_jsonl(str(base) + ".jsonl")
    with open(str(base) + ".md", "w") as f:
        f.write(result["trace"].to_markdown())
    print(f"\n{C['dim']}Saved: {base}.md / .jsonl{C['reset']}")


if __name__ == "__main__":
    main()
