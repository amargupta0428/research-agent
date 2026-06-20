"""The agent control loop — model-driven, not a fixed sequence.

The control model (Sonnet) is handed the goal and the tools. Every cycle IT decides:
which sub-question to tackle, which tool to call with what input, how to read the
result, and whether to keep going or finish. Nothing here hardcodes an order of tools
or a number of steps. This module's job is only to:

  - run the native tool-use loop and execute whatever the model chooses,
  - distil each result and feed it back as the model's next observation,
  - keep the trace legible (plan / act / observe / re-route),
  - prevent loops (never re-run an identical failed call),
  - enforce budget ceilings as a safety net and degrade gracefully.
"""

from __future__ import annotations

from typing import Any

from . import config, tools
from .llm import TokenMeter, call
from .trace import Trace

SYSTEM_PROMPT = """You are an autonomous deep-research agent. You are given a research \
GOAL and a set of tools. You work in cycles and YOU decide the path.

Each cycle:
1. PLAN — In a short paragraph BEFORE you act, state the open sub-questions you still \
need to answer, pick the single most valuable one to tackle next, and briefly evaluate \
what the previous observation told you (relevant? credible? enough? did it contradict \
something or open a new lead?).
2. ACT — Call exactly one tool to make progress on that sub-question. Choose the tool \
that fits the sub-question; there is no required order. Always fill in `subquestion` and \
`rationale`.
3. After you see the result, repeat: re-evaluate and decide the next move — refine the \
query and retry, read a promising URL, go deeper on a lead, switch tools/sources, mark a \
sub-question answered, or conclude.

Tool guidance:
- web_search: find sources and leads (cheap; your default for discovery).
- web_fetch: read one specific URL you want the contents of (cheap; your default for reading).
- apify_scrape: structured extraction; use SPARINGLY and only when web_fetch was blocked \
or you need structured data from a specific site/SERP.

Robustness — this matters:
- If a result is blocked, empty, irrelevant, or low-credibility, DO NOT repeat the same \
call. Change course: reformulate, pick a different source, or switch tools.
- Never make a tool call you have already tried. Abandon dead paths.
- Prefer primary/authoritative sources; corroborate important claims across sources.

Grounding — non-negotiable:
- You are a RESEARCH agent. EVERY factual claim in your final answer must be grounded in \
content you actually FETCHED AND READ this run — never your own prior knowledge, even for \
facts you are certain of. If you "already know" the answer, you must STILL open a source \
and read it to confirm before stating it. Search snippets alone are NOT grounding — read \
the page (web_fetch, or apify_scrape mode='content').
- Do not call `finish` until you have read at least one source whose content actually \
supports your specific claims. A correct answer that isn't grounded in a page you read is \
a FAILURE.

STOP when YOU judge you have enough coverage and confidence to answer well — not at any \
fixed step count. Then call `finish` with a synthesized answer that uses inline [n] \
citations grounded ONLY in sources you actually retrieved. Do not fabricate. If you could \
not fully resolve something, say so in confidence/open_gaps rather than inventing.
"""


class AgentRun:
    def __init__(self, goal: str, sink=None, budget: config.Budget | None = None):
        self.goal = goal
        self.budget = budget or config.Budget()
        self.trace = Trace(goal, sink)
        self.meter = TokenMeter()
        self.apify_available = bool(config.APIFY_TOKEN)
        self.schemas = tools.tool_schemas(self.apify_available)

        self.messages: list[dict] = [{"role": "user", "content": f"GOAL: {goal}"}]
        self.attempts: dict[str, str] = {}  # call signature -> prior quality
        self.tool_calls = 0
        self.apify_runs = 0
        self.successful_retrievals = 0  # any ok observation (incl. search)
        self.successful_reads = 0  # ok web_fetch / apify content READS (grounding gate)
        self.step = 0
        self.last_failure: tuple[str, str] | None = None  # (tool, quality)
        self.result: dict[str, Any] | None = None
        self.stopped_reason = "model_finished"

    # --- budget ---------------------------------------------------------
    def _budget_exceeded(self) -> str | None:
        b = self.budget
        if self.step >= b.max_steps:
            return f"max steps ({b.max_steps}) reached"
        if self.tool_calls >= b.max_tool_calls:
            return f"max tool calls ({b.max_tool_calls}) reached"
        if self.meter.total >= b.max_tokens:
            return f"token budget ({b.max_tokens:,}) reached"
        if self.trace.elapsed >= b.max_seconds:
            return f"time budget ({b.max_seconds}s) reached"
        return None

    # --- main loop ------------------------------------------------------
    def run(self) -> dict[str, Any]:
        self.trace.emit(
            "goal", 0, goal=self.goal, apify=self.apify_available, budget=vars(self.budget)
        )
        while True:
            reason = self._budget_exceeded()
            if reason:
                self.trace.emit("budget", self.step, reason=reason)
                self.stopped_reason = f"budget: {reason}"
                return self._force_finish(reason)

            self.step += 1
            try:
                resp = call(
                    config.CONTROL_MODEL,
                    meter=self.meter,
                    max_tokens=config.CONTROL_MAX_TOKENS,
                    system=SYSTEM_PROMPT,
                    tools=self.schemas,
                    messages=self.messages,
                )
            except Exception as e:
                self.trace.emit("error", self.step, message=f"control model error: {e}")
                self.stopped_reason = f"control_error: {e}"
                return self._degraded_answer(f"Control model error: {e}")

            text = "".join(b.text for b in resp.content if b.type == "text").strip()
            tool_uses = [b for b in resp.content if b.type == "tool_use"]

            if text:
                first_sub = tool_uses[0].input.get("subquestion") if tool_uses else None
                self.trace.emit("plan", self.step, evaluation=text, chosen_subquestion=first_sub)

            if not tool_uses:
                # Model produced only text. Nudge it to act or finish.
                if self._is_nudge_loop():
                    self.stopped_reason = "no_tool_use"
                    return self._force_finish("model stopped without calling a tool")
                self.messages.append({"role": "assistant", "content": resp.content})
                self.messages.append(
                    {
                        "role": "user",
                        "content": "Continue: either call a tool to make progress, or call finish if you "
                        "have enough to answer.",
                    }
                )
                continue

            # Record assistant turn (with tool_use blocks) before sending results.
            self.messages.append({"role": "assistant", "content": resp.content})

            tool_results = []
            for b in tool_uses:
                if b.name == "finish":
                    # Grounding guardrail: a research agent may not answer from prior
                    # knowledge OR from thin search snippets. Block finish until the agent
                    # has actually READ at least one source (web_fetch / apify content) —
                    # a search alone is not grounding.
                    if self.successful_reads == 0:
                        self.trace.emit(
                            "recovery",
                            self.step,
                            reason="finish blocked — no source has been READ yet "
                            "(searching is not enough). Agent must fetch and "
                            "read a page that supports its answer before "
                            "concluding.",
                        )
                        tool_results.append(
                            self._tool_result_block(
                                b,
                                "BLOCKED: you have not READ any source yet — search snippets are "
                                "NOT sufficient grounding. As a research agent you must open and "
                                "read at least one page (web_fetch, or apify_scrape mode='content') "
                                "that actually supports the specific claims in your answer, then "
                                "call finish. Do not answer from prior knowledge.",
                            )
                        )
                        continue
                    return self._handle_finish(b.input)
                tool_results.append(self._execute(b))
            self.messages.append({"role": "user", "content": tool_results})

    # --- tool execution -------------------------------------------------
    def _execute(self, block) -> dict:
        name, inp = block.name, dict(block.input)
        sub = inp.get("subquestion", "")
        rationale = inp.get("rationale", "")
        sig = self._signature(name, inp)

        self.trace.emit(
            "tool_call", self.step, tool=name, input=inp, subquestion=sub, rationale=rationale
        )

        # Loop prevention: never repeat an identical call. Checked before the
        # re-route signpost so a dead-path retry shows only the block, not a
        # misleading "re-routing to <same target>".
        if sig in self.attempts:
            prev = self.attempts[sig]
            # Keep last_failure intact: the prior *executed* failure should still
            # signpost the next genuinely-different action's re-route.
            self.trace.emit(
                "recovery",
                self.step,
                reason=f"blocked a repeat of an already-tried call "
                f"({name}, prev result '{prev}'). Forcing a new approach.",
            )
            obs = (
                f"You ALREADY tried this exact call (previous result: '{prev}'). "
                f"Do not repeat it — choose a different query, source, or tool."
            )
            return self._tool_result_block(block, obs)

        # Re-route signposting: previous result was bad and we're now trying
        # a genuinely different action.
        if self.last_failure is not None:
            self.trace.emit(
                "recovery",
                self.step,
                reason=f"previous {self.last_failure[0]} came back "
                f"'{self.last_failure[1]}' — re-routing to {name}"
                f"({self._target_str(name, inp)}).",
            )
            self.last_failure = None

        self.tool_calls += 1
        result = self._dispatch(name, inp)
        self.attempts[sig] = result.quality

        if result.used_apify:
            self.apify_runs += 1

        self.trace.emit(
            "observation",
            self.step,
            tool=name,
            quality=result.quality,
            summary=result.observation,
            detail=result.detail,
        )

        if result.quality == "ok":
            self.successful_retrievals += 1
            # A "read" = actually pulling a page's content (web_fetch or apify content),
            # as opposed to a search that only returns snippets. Grounding requires a read.
            if name == "web_fetch" or (name == "apify_scrape" and inp.get("mode") == "content"):
                self.successful_reads += 1
        else:
            self.last_failure = (name, result.quality)

        return self._tool_result_block(block, result.observation)

    def _dispatch(self, name: str, inp: dict) -> tools.ToolResult:
        if name == "web_search":
            return tools.web_search(inp["query"], self.meter)
        if name == "web_fetch":
            return tools.web_fetch(inp["url"], inp.get("subquestion", ""), self.meter)
        if name == "apify_scrape":
            if self.apify_runs >= self.budget.max_apify_runs:
                self.trace.emit(
                    "budget",
                    self.step,
                    reason=f"Apify run cap ({self.budget.max_apify_runs}) reached",
                )
                return tools.ToolResult(
                    observation="Apify run cap reached for this task. Use web_search/web_fetch.",
                    quality="error",
                    detail={"reason": "apify_cap"},
                )
            return tools.apify_scrape(
                inp["mode"], inp["target"], inp.get("subquestion", ""), self.meter
            )
        return tools.ToolResult(observation=f"Unknown tool {name}", quality="error")

    # --- finish / degrade ----------------------------------------------
    def _handle_finish(self, inp: dict) -> dict[str, Any]:
        self.result = {
            "answer": inp.get("answer", ""),
            "citations": inp.get("citations", []),
            "confidence": inp.get("confidence", ""),
            "open_gaps": inp.get("open_gaps", ""),
        }
        self.trace.emit(
            "finish",
            self.step,
            **self.result,
            stopped_reason=self.stopped_reason,
            tokens=self.meter.total,
            tool_calls=self.tool_calls,
            apify_runs=self.apify_runs,
            elapsed=round(self.trace.elapsed, 1),
        )
        return self._final()

    def _append_user(self, text: str) -> None:
        """Append a user instruction, merging into the last user turn if needed so we
        never emit two consecutive user messages (the API requires alternation)."""
        block = {"type": "text", "text": text}
        if self.messages and self.messages[-1]["role"] == "user":
            content = self.messages[-1]["content"]
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
            content.append(block)
            self.messages[-1]["content"] = content
        else:
            self.messages.append({"role": "user", "content": [block]})

    def _force_finish(self, reason: str) -> dict[str, Any]:
        """Budget hit: force one finish call with whatever has been gathered."""
        self._append_user(
            f"STOP CONDITION: {reason}. You must call `finish` NOW with the best answer "
            f"you can synthesize from what you have already retrieved. Be honest about "
            f"gaps and confidence."
        )
        try:
            resp = call(
                config.CONTROL_MODEL,
                meter=self.meter,
                max_tokens=config.CONTROL_MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=self.schemas,
                tool_choice={"type": "tool", "name": "finish"},
                messages=self.messages,
            )
            for b in resp.content:
                if b.type == "tool_use" and b.name == "finish":
                    return self._handle_finish(b.input)
        except Exception as e:
            self.trace.emit("error", self.step, message=f"forced-finish failed: {e}")
        return self._degraded_answer(f"Stopped early ({reason}) and could not synthesize cleanly.")

    def _degraded_answer(self, msg: str) -> dict[str, Any]:
        self.result = {
            "answer": f"_Partial / degraded result._ {msg}",
            "citations": [],
            "confidence": "low",
            "open_gaps": msg,
        }
        self.trace.emit(
            "finish",
            self.step,
            **self.result,
            stopped_reason=self.stopped_reason,
            tokens=self.meter.total,
        )
        return self._final()

    def _final(self) -> dict[str, Any]:
        return {
            **self.result,
            "trace": self.trace,
            "meter": self.meter,
            "stopped_reason": self.stopped_reason,
            "steps": self.step,
            "tool_calls": self.tool_calls,
            "reads": self.successful_reads,
            "apify_runs": self.apify_runs,
            "tokens": self.meter.total,
            "by_model": self.meter.by_model,
        }

    # --- helpers --------------------------------------------------------
    def _signature(self, name: str, inp: dict) -> str:
        key = inp.get("query") or inp.get("url") or inp.get("target") or ""
        mode = inp.get("mode", "")
        return f"{name}|{mode}|{key.strip().lower()}"

    def _target_str(self, name: str, inp: dict) -> str:
        return (inp.get("query") or inp.get("url") or inp.get("target") or "")[:80]

    def _tool_result_block(self, block, content: str) -> dict:
        return {"type": "tool_result", "tool_use_id": block.id, "content": content}

    def _is_nudge_loop(self) -> bool:
        # If the last two assistant turns were text-only, stop nudging.
        recent = [m for m in self.messages[-4:] if m["role"] == "assistant"]
        return len(recent) >= 2


def run_agent(goal: str, sink=None, budget: config.Budget | None = None) -> dict[str, Any]:
    return AgentRun(goal, sink=sink, budget=budget).run()
