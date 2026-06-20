"""Cross-provider judge PANEL for the eval suite.

The point of a panel — and of using DIFFERENT PROVIDERS — is that Claude must not be
the only voice grading Claude. We send each answer to every available judge (OpenAI,
Gemini, Anthropic-Opus), then aggregate: mean of the numeric scores, majority verdict.
Members whose API key is missing are skipped, so the panel degrades gracefully.

Each judge scores, against the provided ground-truth and the evidence the agent actually
retrieved:
  - correct   (0..1): does the answer state the ground-truth answer?
  - faithful  (0..1): is every claim supported by the RETRIEVED evidence (not the judge's
                      own knowledge)? This is what catches answering-from-memory.
  - cited     (bool): does the answer cite sources?
  - precision (0..1): for market/list answers — are the entities correct, with no wrong or
                      hallucinated ones? (So spamming many names can't win on recall alone.)

Calls use raw httpx (no extra SDKs) for OpenAI/Gemini; Anthropic uses its SDK.
"""

from __future__ import annotations

import json
import re

import httpx

from agent import config
from agent.llm import client as anthropic_client

_SYS = (
    "You are a STRICT, independent evaluator of a research agent's answer. You are given "
    "the QUESTION, the GROUND-TRUTH answer, the agent's ANSWER, and the EVIDENCE the agent "
    "actually retrieved during its run. Return ONLY a JSON object with keys:\n"
    '{"correct": 0..1, "faithful": 0..1, "cited": true|false, "precision": 0..1, '
    '"verdict": "PASS"|"PARTIAL"|"FAIL", "reasoning": "1-3 sentences"}\n'
    "- correct: 1.0 if the answer states the ground-truth (paraphrase/extra correct detail "
    "ok), 0.5 if partial, 0.0 if wrong/missing.\n"
    "- faithful: 1.0 if ALL key claims are supported by the RETRIEVED EVIDENCE provided "
    "below — judge grounding against that evidence, NOT your own world knowledge. If the "
    "answer asserts specifics not present in the evidence, lower it. An answer that is "
    "correct but not grounded in the evidence must score LOW on faithful.\n"
    "- cited: true if the answer references sources (inline [n] and/or a sources list).\n"
    "- precision: for answers that list entities (e.g. competitors), 1.0 if all named "
    "entities are correct/relevant, lower if it includes wrong, irrelevant, or hallucinated "
    "entities. For single-fact answers where precision is N/A, set 1.0.\n"
    "- verdict: PASS only if correct>=0.9 AND faithful>=0.8 AND cited AND precision>=0.7. "
    "FAIL if correct<0.5. Otherwise PARTIAL.\n"
    "Be terse and honest."
)


def _user_prompt(question, expected, answer, evidence) -> str:
    return (
        f"QUESTION:\n{question}\n\nGROUND-TRUTH:\n{expected}\n\nAGENT ANSWER:\n{answer}\n\n"
        f"RETRIEVED EVIDENCE (what the agent actually saw):\n"
        f"{evidence[: config.JUDGE_EVIDENCE_CHARS]}\n\n"
        "Return the JSON now."
    )


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
    m = raw[raw.find("{") : raw.rfind("}") + 1]
    return json.loads(m)


# --- provider callers ----------------------------------------------------
def _call_openai(model, system, user) -> dict:
    r = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
        json={
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"},
        },
        timeout=60,
    )
    r.raise_for_status()
    return _parse_json(r.json()["choices"][0]["message"]["content"])


def _call_gemini(model, system, user) -> dict:
    r = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        params={"key": config.GEMINI_API_KEY},
        json={
            "contents": [{"role": "user", "parts": [{"text": system + "\n\n" + user}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        },
        timeout=60,
    )
    r.raise_for_status()
    parts = r.json()["candidates"][0]["content"]["parts"]
    text = "".join(p.get("text", "") for p in parts)  # Gemini may split across parts
    return _parse_json(text)


def _call_anthropic(model, system, user) -> dict:
    resp = anthropic_client().messages.create(
        model=model,
        max_tokens=config.JUDGE_MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    raw = "".join(b.text for b in resp.content if b.type == "text")
    return _parse_json(raw)


_CALLERS = {"openai": _call_openai, "gemini": _call_gemini, "anthropic": _call_anthropic}
_KEYS = {"openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}


def available_panel() -> list[tuple]:
    """Panel members whose API key is actually present."""
    return [m for m in config.JUDGE_PANEL if getattr(config, _KEYS[m[0]], None)]


def _keyword_hit(answer: str, keywords: list[str]) -> bool:
    a = (answer or "").lower()
    return bool(keywords) and all(k.lower() in a for k in keywords)


def judge_answer(question, expected, answer, evidence, keywords) -> dict:
    """Run the full cross-provider panel and aggregate."""
    system, user = _SYS, _user_prompt(question, expected, answer, evidence)
    per_judge = []
    for provider, model, label in available_panel():
        try:
            d = _CALLERS[provider](model, system, user)
            per_judge.append(
                {
                    "judge": label,
                    "provider": provider,
                    "correct": float(d.get("correct", 0)),
                    "faithful": float(d.get("faithful", 0)),
                    "cited": bool(d.get("cited", False)),
                    "precision": float(d.get("precision", 1.0)),
                    "verdict": d.get("verdict", "FAIL"),
                    "reasoning": d.get("reasoning", ""),
                }
            )
        except Exception as e:
            per_judge.append({"judge": label, "provider": provider, "error": str(e)})

    scored = [j for j in per_judge if "error" not in j]
    kw = _keyword_hit(answer, keywords)
    has_cite = bool(re.search(r"\[\d+\]", answer or ""))

    if not scored:
        return {
            "correct": 0.0,
            "faithful": 0.0,
            "cited": has_cite,
            "precision": 0.0,
            "verdict": "FAIL",
            "keyword_hit": kw,
            "per_judge": per_judge,
            "panel_size": 0,
            "note": "all judges failed",
        }

    # We report BOTH mean and median, deliberately. The mean is conservative (any
    # judge's doubt pulls it down); the median is robust to a single outlier judge.
    # Surfacing both — rather than auto-picking — keeps panel disagreement visible.
    def _mean(vals):
        return round(sum(vals) / len(vals), 3)

    def _median(vals):
        s = sorted(vals)
        n = len(s)
        return round(s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2, 3)

    def _verdict(correct, faithful, precision, cited):
        if correct < 0.5:
            return "FAIL"
        if correct >= 0.9 and faithful >= 0.8 and cited and precision >= 0.7:
            return "PASS"
        return "PARTIAL"

    cited = (sum(j["cited"] for j in scored) >= len(scored) / 2) or has_cite
    agg = {}
    for k in ("correct", "faithful", "precision"):
        vals = [j[k] for j in scored]
        agg[f"{k}_mean"] = _mean(vals)
        agg[f"{k}_median"] = _median(vals)
    # Blend high-precision keyword signal into correctness (both aggregations).
    if kw:
        agg["correct_mean"] = max(agg["correct_mean"], 0.75)
        agg["correct_median"] = max(agg["correct_median"], 0.75)

    verdict_mean = _verdict(agg["correct_mean"], agg["faithful_mean"], agg["precision_mean"], cited)
    verdict_median = _verdict(
        agg["correct_median"], agg["faithful_median"], agg["precision_median"], cited
    )

    return {
        **agg,
        # Convenience primaries = the robust (median) view; mean is alongside for audit.
        "correct": agg["correct_median"],
        "faithful": agg["faithful_median"],
        "precision": agg["precision_median"],
        "verdict": verdict_median,
        "verdict_mean": verdict_mean,
        "verdict_median": verdict_median,
        "cited": cited,
        "keyword_hit": kw,
        "panel_size": len(scored),
        "per_judge": per_judge,
    }
