"""Central configuration: model tiers, budget ceilings, tool settings.

Everything tunable lives here so the loop logic stays clean. Budgets are
*safety nets* — the agent is meant to stop when the model judges it has enough,
not when it hits these. They only exist so a runaway/looping run degrades
gracefully instead of burning money.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

# --- Model tiers (deliberate cost tiering) -------------------------------
# Control loop (plan / evaluate / decide) — this is where the agency lives.
CONTROL_MODEL = "claude-sonnet-4-6"
# Cheap subtasks: extract/summarize a single fetched page.
EXTRACT_MODEL = "claude-haiku-4-5"

CONTROL_MAX_TOKENS = 4096
EXTRACT_MAX_TOKENS = 1024
JUDGE_MAX_TOKENS = 1536
# Max chars of retrieved evidence shown to each judge. Must comfortably exceed a
# heavy multi-read run's total evidence, or the judge can't see grounding that
# appears late and wrongly docks faithfulness (observed on pricing/valuation Qs).
JUDGE_EVIDENCE_CHARS = 45_000

# --- Eval judge PANEL (genuinely cross-provider) -------------------------
# A multi-model, multi-PROVIDER panel scores each answer; we average the numeric
# scores and majority-vote the verdict. Cross-provider is the point: Claude must
# not be the only voice grading Claude. Each entry is (provider, model_id, label).
# Members whose API key is missing are skipped automatically (panel degrades
# gracefully to whoever is available). Model IDs are current as of June 2026 —
# verify the exact API string for your account and adjust here if needed.
JUDGE_PANEL = [
    ("openai", "gpt-5.4", "gpt-5.4"),  # cross-provider judge #1
    ("gemini", "gemini-3.5-flash", "gemini-3.5-flash"),  # cross-provider judge #2
    ("anthropic", "claude-opus-4-8", "opus-4.8"),  # tie-breaker / 3rd opinion
]


@dataclass
class Budget:
    """Hard ceilings — safety nets only. Hitting one forces graceful synthesis."""

    max_steps: int = 24  # control-model turns
    max_tool_calls: int = 30  # total tool executions
    max_apify_runs: int = 4  # Apify is the expensive path; cap it hard
    max_tokens: int = 400_000  # input+output across all Anthropic calls in a run
    max_seconds: int = 600  # wall-clock ceiling


# Tighter budget for eval runs (20 questions, keep cost sane).
EVAL_BUDGET = Budget(
    max_steps=14, max_tool_calls=16, max_apify_runs=2, max_tokens=180_000, max_seconds=300
)

# --- Tool settings -------------------------------------------------------
SEARCH_RESULTS = 8
FETCH_TIMEOUT = 25  # seconds per web_fetch
FETCH_MAX_CHARS = 16_000  # truncate extracted page text before Haiku extraction
APIFY_CONTENT_ACTOR = "apify/website-content-crawler"
APIFY_SERP_ACTOR = "apify/google-search-scraper"
APIFY_TIMEOUT = 120  # seconds to wait on an Apify run

# --- Keys ----------------------------------------------------------------
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
APIFY_TOKEN = os.getenv("APIFY_TOKEN")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
# Cross-provider judge keys (eval only; the agent itself never uses these).
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
