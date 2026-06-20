"""Run trace: the headline artifact.

Every meaningful moment in a run becomes a TraceEvent. Events are streamed live
(to the terminal or the web UI via a callback) AND collected so the whole run can
be rendered to readable Markdown or saved as JSONL for spot-checking.

The trace is deliberately legible: each step shows the sub-question the model
chose, the tool + input, what it observed, and — crucially — when it changed
course (recovery), because that is the proof the control flow is model-driven.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TraceEvent:
    kind: str  # goal|plan|tool_call|observation|recovery|budget|finish|error
    step: int
    data: dict[str, Any] = field(default_factory=dict)
    t: float = field(default_factory=time.time)


EventSink = Callable[[TraceEvent], None] | None


class Trace:
    def __init__(self, goal: str, sink: EventSink = None):
        self.goal = goal
        self.events: list[TraceEvent] = []
        self._sink = sink
        self._t0 = time.time()

    def emit(self, kind: str, step: int, **data) -> TraceEvent:
        ev = TraceEvent(kind=kind, step=step, data=data)
        self.events.append(ev)
        if self._sink:
            try:
                self._sink(ev)
            except Exception:
                pass  # never let UI streaming break the run
        return ev

    @property
    def elapsed(self) -> float:
        return time.time() - self._t0

    # --- serialization --------------------------------------------------
    def to_jsonl(self) -> str:
        return "\n".join(json.dumps(asdict(e), default=str) for e in self.events)

    def save_jsonl(self, path: str) -> None:
        with open(path, "w") as f:
            f.write(self.to_jsonl())

    # --- human-readable rendering ---------------------------------------
    def to_markdown(self) -> str:
        lines = ["# Research trace\n", f"**Goal:** {self.goal}\n"]
        for e in self.events:
            d = e.data
            if e.kind == "plan":
                lines.append(f"\n## Step {e.step} — Plan")
                if d.get("open_subquestions"):
                    lines.append("Open sub-questions:")
                    for q in d["open_subquestions"]:
                        lines.append(f"- {q}")
                if d.get("chosen_subquestion"):
                    lines.append(f"\n**Tackling:** {d['chosen_subquestion']}")
                if d.get("evaluation"):
                    lines.append(f"\n**Read on last result:** {d['evaluation']}")
                if d.get("reasoning"):
                    lines.append(f"\n**Why this next:** {d['reasoning']}")
            elif e.kind == "tool_call":
                inp = d.get("input", {})
                pretty = ", ".join(
                    f"{k}={v!r}" for k, v in inp.items() if k not in ("subquestion", "rationale")
                )
                lines.append(f"\n**ACT →** `{d['tool']}`({pretty})")
            elif e.kind == "observation":
                flag = d.get("quality", "")
                tag = f" _[{flag}]_" if flag else ""
                lines.append(f"**OBSERVE{tag}:** {d.get('summary', '')}")
            elif e.kind == "recovery":
                lines.append(f"\n> ♻️ **RE-ROUTE:** {d.get('reason', '')}")
            elif e.kind == "budget":
                lines.append(f"\n> ⛔ **BUDGET:** {d.get('reason', '')}")
            elif e.kind == "error":
                lines.append(f"\n> ⚠️ **ERROR:** {d.get('message', '')}")
            elif e.kind == "finish":
                lines.append("\n## Final answer\n")
                lines.append(d.get("answer", ""))
                cites = d.get("citations", [])
                if cites:
                    lines.append("\n### Sources")
                    for c in cites:
                        lines.append(f"- [{c.get('id')}] {c.get('title', '')} — {c.get('url', '')}")
                if d.get("confidence"):
                    lines.append(f"\n_Confidence: {d['confidence']}_")
                if d.get("open_gaps"):
                    lines.append(f"\n_Remaining gaps: {d['open_gaps']}_")
        return "\n".join(lines)
