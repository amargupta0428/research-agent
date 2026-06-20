"""Minimal tests for the agent control loop, using a scripted fake model and fake tools
so they run offline (no API keys, no network). They lock in the two behaviors that make
this an agent rather than a pipeline: it never repeats a failed call, and it will not
conclude until it has actually read a source.
"""

import agent.loop as loop
import agent.tools as tools


class _Blk:
    def __init__(self, **k):
        self.__dict__.update(k)


class _Usage:
    input_tokens = 10
    output_tokens = 5


class _Resp:
    def __init__(self, content):
        self.content = content
        self.usage = _Usage()


def _finish(i):
    return _Blk(
        type="tool_use",
        id=f"f{i}",
        name="finish",
        input={
            "answer": "Answer grounded in a read source [1].",
            "citations": [{"id": 1, "url": "https://example.com", "title": "src"}],
            "confidence": "high",
            "open_gaps": "",
        },
    )


def _script_runner(script, monkeypatch, *, search=None, fetch=None):
    it = iter(script)

    def fake_call(model, meter=None, **kw):
        r = next(it)
        if meter is not None:
            meter.add(model, r.usage)
        return r

    monkeypatch.setattr(loop, "call", fake_call)
    monkeypatch.setattr(
        loop.tools, "web_search", search or (lambda q, meter: tools.ToolResult("hits", "ok", {}))
    )
    monkeypatch.setattr(
        loop.tools,
        "web_fetch",
        fetch or (lambda u, s, meter: tools.ToolResult("page content", "ok", {})),
    )


def test_grounding_gate_blocks_finish_until_a_read(monkeypatch):
    # The model searches (ok) then tries to finish; a search is not a read, so finish is
    # blocked. It then fetches a page and finishes successfully.
    script = [
        _Resp(
            [
                _Blk(
                    type="tool_use",
                    id="s1",
                    name="web_search",
                    input={"query": "q", "subquestion": "s", "rationale": "r"},
                )
            ]
        ),
        _Resp([_finish(1)]),  # premature: nothing read yet -> blocked
        _Resp(
            [
                _Blk(
                    type="tool_use",
                    id="r1",
                    name="web_fetch",
                    input={"url": "https://example.com", "subquestion": "s", "rationale": "r"},
                )
            ]
        ),
        _Resp([_finish(2)]),
    ]
    recoveries = []
    _script_runner(script, monkeypatch)
    res = loop.run_agent(
        "goal",
        sink=lambda e: (
            recoveries.append(e.data.get("reason", "")) if e.kind == "recovery" else None
        ),
    )
    assert res["reads"] == 1
    assert any("finish blocked" in r for r in recoveries)
    assert "grounded in a read source" in res["answer"]


def test_loop_prevention_blocks_duplicate_calls(monkeypatch):
    # The model fetches a blocked page, then tries the exact same fetch again; the second
    # identical call must be blocked from executing (not re-run).
    def fetch(url, s, meter):
        return (
            tools.ToolResult("403", "blocked", {})
            if "blocked" in url
            else tools.ToolResult("good content", "ok", {})
        )

    script = [
        _Resp(
            [
                _Blk(
                    type="tool_use",
                    id="a",
                    name="web_fetch",
                    input={"url": "https://blocked.example", "subquestion": "s", "rationale": "r"},
                )
            ]
        ),
        _Resp(
            [
                _Blk(
                    type="tool_use",
                    id="b",
                    name="web_fetch",
                    input={"url": "https://blocked.example", "subquestion": "s", "rationale": "r"},
                )
            ]
        ),
        _Resp(
            [
                _Blk(
                    type="tool_use",
                    id="c",
                    name="web_fetch",
                    input={"url": "https://good.example", "subquestion": "s", "rationale": "r"},
                )
            ]
        ),
        _Resp([_finish(1)]),
    ]
    recoveries = []
    _script_runner(script, monkeypatch, fetch=fetch)
    res = loop.run_agent(
        "goal",
        sink=lambda e: (
            recoveries.append(e.data.get("reason", "")) if e.kind == "recovery" else None
        ),
    )
    # Three tool_use blocks for fetch, but the duplicate is blocked, so only 2 execute.
    assert res["tool_calls"] == 2
    assert any("already-tried" in r for r in recoveries)
