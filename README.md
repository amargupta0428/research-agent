# Research Agent

An autonomous deep-research agent. You give it a goal (for example, "competitive brief on
Notion: top 3 competitors and how each prices"), and it investigates on its own using web
tools, deciding its own path, then returns a synthesized answer with inline citations plus
a full trace of how it got there.

It is a genuine agent, not a workflow. The control flow is decided by the model at runtime,
not hardcoded. The same agent, with no per-question configuration, takes different tool
paths for different goals, and it recovers when a source is blocked or useless rather than
crashing or blindly continuing. The committed example traces below are the proof.

The domain shown here is company and market research, but the core loop is domain
agnostic. The domain lives only in the eval set and the choice of scrapers.

## The eval is the headline

Most "research agent" repos have no evaluation. This one ships a 20-question suite of
deliberately un-memorizable questions (recent 2025 to 2026 funding rounds, acquisitions,
earnings figures, and multi-source pricing comparisons), each with a web-verified ground
truth, scored by a cross-provider judge panel.

| Metric | Result |
|---|---|
| PASS rate (median aggregation) | 19 / 20 (95%) |
| PASS rate (mean aggregation) | 17 / 20 (85%) |
| Avg correctness (median / mean) | 0.99 / 0.97 |
| Avg faithfulness (median / mean) | 0.99 / 0.96 |
| Avg precision (median / mean) | 0.97 / 0.95 |
| Answers cited (inline + sources) | 100% |

The judge panel is the point. Each answer is graded by three judges from three different
providers (OpenAI gpt-5.4, Google gemini-3.5-flash, Anthropic opus-4.8), so Claude is not
the only model grading Claude. We report both the median and the mean across the panel and
do not hide disagreement behind a single number. Four dimensions are scored:

- **correctness**: judge consensus plus a high-precision programmatic keyword check.
- **faithfulness**: graded against the evidence the agent actually retrieved this run, not
  the judges' own knowledge. This is what catches answering from memory.
- **precision**: penalizes wrong or hallucinated entities, so listing many names cannot win
  on keyword recall alone.
- **citation**: inline `[n]` markers plus a sources list.

Full table, methodology, and per-judge votes: [EVAL.md](EVAL.md) and `eval/results/`.

One question stays an honest PARTIAL (q11), where the agent states a price tie that is not
correct. We keep it as a PARTIAL rather than rounding to 20/20. The story of that miss, plus
two more issues this eval surfaced, is in [CASE_STUDY.md](CASE_STUDY.md).

## The agentic proof: committed run traces

These are real runs, committed so you can inspect the agent's behavior without paying to
run it. See [examples/](examples/).

- `examples/normal-plus-recovery` (Notion brief): 9 steps, 16 tool calls, 4 re-routes. It
  tries the official Notion and Atlassian pricing pages, hits a JavaScript or bot wall, and
  re-routes to third-party pricing trackers, then cross-checks figures before answering.
- A divergent pair from the same agent, showing different goals taking different paths:
  - `examples/q06-clean-path`: a Google/Wiz acquisition fact. 3 steps, 0 re-routes. Sources
    are clean, so it reads two primary sources and concludes. A short, direct path.
  - `examples/q11-recovery-path`: an API pricing comparison. 5 re-routes, a blocked repeat
    call, and a budget-ceiling stop. It struggles to pin a current price, keeps changing
    course, never repeats a failed call, and answers under the cap.

Each trace shows the loop the model drives itself: plan, act, observe, decide, and stop when
it judges it has enough.

## How the loop works

Each cycle the control model decides:

1. **Plan**: restate the open sub-questions and pick the most valuable one.
2. **Act**: choose one tool and its input. Tool choice is the model's decision, not a fixed
   order.
3. **Observe and evaluate**: read what came back and judge it (relevant, credible, enough).
4. **Decide next**: refine and retry, go deeper, switch tools or sources, or conclude.
5. **Stop** when the model judges it has enough coverage and confidence, not at a fixed step
   count. Hard ceilings (max steps, tool calls, Apify runs, tokens, wall-clock) exist only as
   a safety net; hitting one forces a graceful synthesis from what was gathered.

Robustness is built in: blocked or garbage results are detected and trigger a re-route, an
identical failed call is never repeated, and every recovery is visible in the trace.

### Tools (the agent selects; no fixed order)

- **web_search**: find sources and leads. Tavily if a key is set, else DuckDuckGo (free, no
  key). Does not consume an Apify run.
- **web_fetch**: fetch and read one URL (httpx plus trafilatura extraction). Free path.
- **apify_scrape**: structured extraction via Apify, used sparingly and capped per task.
  `mode="content"` deep-reads a specific site; `mode="serp"` returns structured Google
  results. Requires `APIFY_TOKEN`; without it the agent degrades to search and fetch.

### Model tiering (deliberate cost control)

- Control loop on `claude-sonnet-4-6`, where the agency lives.
- Per-page extraction on `claude-haiku-4-5`, so raw pages never hit the expensive model.
- Eval judges are a separate cross-provider panel, used only in evaluation.

## Reproducibility and cost (read this)

Every run hits live services (web search, web fetch, the Anthropic API, and Apify if
invoked). Runs are therefore non-deterministic and cost money. There is no replay or cached
mode; the committed traces in `examples/` and `eval/results/` are how you inspect behavior
without paying to run it.

- A single research run is roughly 95k tokens, about 130 seconds, about $0.30.
- The full 20-question eval is roughly $4 to $6 and 25 to 40 minutes (the Opus judge is the
  bulk of that).

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in ANTHROPIC_API_KEY at minimum
```

Required: `ANTHROPIC_API_KEY` (control loop, extraction, and the Opus judge). Optional:
`APIFY_TOKEN`, `TAVILY_API_KEY`, and `OPENAI_API_KEY` plus `GEMINI_API_KEY` for the full
cross-provider judge panel (the eval degrades to whichever judge keys are present).

## Run it

```bash
# CLI: streams the trace to your terminal, saves to runs/
python run.py "competitive brief on Notion: top 3 competitors and how each prices"

# Web UI: enter a goal, watch the trace stream live over SSE
uvicorn app:app --reload --port 8000   # then open http://localhost:8000

# Eval: runs the 20 questions, scores with the panel, writes EVAL.md
python -m eval.run_eval
```

The web UI runs a full live agent per query (about $0.10 to $0.30 each) and needs
`ANTHROPIC_API_KEY`.

## What is and is not claimed

- The eval is 20 questions, framed exactly that way. It is a focused, honest probe, not a
  benchmark of hundreds.
- The judge panel is the value: cross-provider grading with both aggregations reported.
- Demo grade only: no deployment, no auth, no multi-user, no public unsupervised endpoint.

## Layout

```
agent/        the agent: control loop, tools, extraction, trace, config
app.py        FastAPI streaming-trace UI
run.py        CLI entry point
eval/         the eval: judge panel, 20-question set, per-question results
examples/     committed proof traces (normal, recovery, divergent pair)
tests/        offline tests for the loop guarantees
EVAL.md       generated eval results
CASE_STUDY.md problem, approach, results, and the three issues the eval caught
```

## License

MIT, see [LICENSE](LICENSE).
