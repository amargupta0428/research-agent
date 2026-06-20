"""Thin Anthropic client wrapper with run-scoped token accounting.

One TokenMeter per agent run aggregates usage across the control model (Sonnet)
and the extraction model (Haiku) so the budget ceiling can be enforced.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from anthropic import Anthropic

from . import config


@dataclass
class TokenMeter:
    input_tokens: int = 0
    output_tokens: int = 0
    by_model: dict = field(default_factory=dict)

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    def add(self, model: str, usage) -> None:
        i = getattr(usage, "input_tokens", 0) or 0
        o = getattr(usage, "output_tokens", 0) or 0
        self.input_tokens += i
        self.output_tokens += o
        m = self.by_model.setdefault(model, {"input": 0, "output": 0, "calls": 0})
        m["input"] += i
        m["output"] += o
        m["calls"] += 1


_client: Anthropic | None = None


def client() -> Anthropic:
    global _client
    if _client is None:
        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in."
            )
        _client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def call(model: str, *, meter: TokenMeter | None = None, **kwargs):
    """Create a message and record token usage against the meter."""
    resp = client().messages.create(model=model, **kwargs)
    if meter is not None:
        meter.add(model, resp.usage)
    return resp
