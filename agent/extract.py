"""Cheap-tier extraction (Haiku).

When a page is fetched/scraped we do NOT dump raw HTML/text into the expensive
control model. Instead Haiku condenses the page *with respect to the current
sub-question* into a tight, source-grounded note. This is the deliberate cost
tiering: the control loop reasons over small distilled observations, not raw pages.
"""

from __future__ import annotations

import json

from . import config
from .llm import TokenMeter, call

_SYS = (
    "You extract facts from a single web page for a research agent. "
    "You are given the page text and the sub-question the agent is trying to answer. "
    "Return ONLY a compact JSON object with keys: "
    '"relevant" (bool: does this page actually help with the sub-question), '
    '"summary" (2-5 sentences of the most relevant, concrete facts — names, numbers, '
    "dates, quotes — grounded strictly in the page; no speculation), "
    '"key_facts" (array of <=6 short factual strings, each independently citable). '
    "If the page is an error/blocked/empty/captcha/login wall, set relevant=false and "
    "say so in summary. Never invent facts not present in the text."
)


def extract_page(page_text: str, subquestion: str, url: str, meter: TokenMeter) -> dict:
    text = (page_text or "").strip()
    if not text:
        return {
            "relevant": False,
            "summary": "Page returned no extractable content.",
            "key_facts": [],
        }
    text = text[: config.FETCH_MAX_CHARS]
    prompt = (
        f"SUB-QUESTION: {subquestion}\n\nURL: {url}\n\nPAGE TEXT:\n{text}\n\n"
        "Return the JSON object now."
    )
    try:
        resp = call(
            config.EXTRACT_MODEL,
            meter=meter,
            max_tokens=config.EXTRACT_MAX_TOKENS,
            system=_SYS,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(b.text for b in resp.content if b.type == "text").strip()
        # tolerate code fences
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = raw[raw.find("{") :]
        data = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
        data.setdefault("relevant", True)
        data.setdefault("summary", "")
        data.setdefault("key_facts", [])
        return data
    except Exception as e:
        # Degrade to a truncated raw snippet rather than failing the whole step.
        return {
            "relevant": True,
            "summary": text[:600],
            "key_facts": [],
            "extract_error": str(e),
        }
