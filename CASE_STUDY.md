# Case study: a model-driven research agent and the eval that audited it

## Problem

"Research agent" is an easy thing to demo and a hard thing to prove. A scripted pipeline
that always searches, then fetches, then summarizes can look agentic in a single happy-path
run. The interesting questions are the ones a demo skips. Does the model actually decide what
to do next based on what it just saw? Does it recover when a source is blocked, or does it
fall over? And is the final answer grounded in what it retrieved, or is it the base model
reciting what it already knew?

The goal here was to build a genuine agent for company and market research, and then to
build the evaluation that would actually hold it to account.

## Approach

**A model-driven control loop.** The control model (claude-sonnet-4-6) is given the goal and
the tools and decides every step: which sub-question to tackle, which tool to call with what
input, how to judge the result, and when to stop. Nothing in the loop hardcodes an order of
tools or a number of steps. The loop code only executes the model's choices, distils each
result, keeps the trace legible, prevents repeated failed calls, and enforces budget ceilings
as a safety net.

**Deliberate cost tiering.** The control loop runs on Sonnet, where the agency lives.
Per-page extraction runs on the cheaper claude-haiku-4-5, so raw pages never reach the
expensive model. A research run is about $0.30.

**Tools the agent selects among.** web_search (Tavily or free DuckDuckGo), web_fetch (httpx
plus trafilatura), and apify_scrape for structured extraction, capped per task. The agent
reaches for Apify only when the cheaper path is blocked.

**A grounding gate.** Early on, an initial version of the eval caught the agent answering
easy questions correctly but without retrieving anything, that is, from the base model's
memory. For a research agent that is a failure even when the answer is right. The fix was a
gate: the agent cannot call finish until it has actually fetched and read a source, not just
seen a search snippet. This is enforced in code and is one of the committed tests.

**An eval built to be adversarial to the agent.** Twenty questions, all deliberately
un-memorizable: 2025 to 2026 funding rounds, acquisitions that closed, executive changes,
quarterly earnings figures, and multi-source pricing comparisons. Each has a web-verified
ground truth with source URLs. Each answer is scored by a cross-provider judge panel (OpenAI
gpt-5.4, Google gemini-3.5-flash, Anthropic opus-4.8) on correctness, faithfulness against
the retrieved evidence, precision against hallucinated entities, and citation. Scores are
reported as both a median and a mean across the panel.

## Results

| Metric | Result |
|---|---|
| PASS rate (median aggregation) | 19 / 20 (95%) |
| PASS rate (mean aggregation) | 17 / 20 (85%) |
| Avg correctness (median / mean) | 0.99 / 0.97 |
| Avg faithfulness (median / mean) | 0.99 / 0.96 |
| Avg precision (median / mean) | 0.97 / 0.95 |
| Answers cited (inline + sources) | 100% |

The agentic behavior is shown in committed traces (see `examples/`): a substantive run with
four recoveries where official pricing pages are blocked and the agent re-routes to
third-party trackers, and a divergent pair where the same agent takes a clean 3-step path for
one goal and a 5-re-route, budget-capped path for another. The control flow visibly responds
to what the agent observes.

## What the eval caught

The score is not the interesting part. The interesting part is that a full run surfaced three
distinct problems at three different levels, and each was investigated and resolved rather
than smoothed over. This is what made the eval load-bearing.

### 1. A real agent error (q11), kept as an honest PARTIAL

On a question comparing the API input price of three frontier models, the agent concluded
that Google Gemini 2.5 Pro and the current GPT-5 flagship were tied at $1.25 per million
tokens. The flagship is $5; the agent had grabbed the wrong GPT tier from a pricing page.
The panel scored it correct on the other models but flagged the false tie, and it stays a
PARTIAL. This is the eval doing its job: catching a genuine reasoning slip on a hard
multi-source question. We did not paper over it to claim 20 out of 20.

### 2. A stale ground truth, where the agent was actually right (q17)

The question asked for Nvidia's most recent quarterly Data Center and total revenue. Our
ground truth, written while building the question set, named Q4 fiscal 2026. The agent
answered with Q1 fiscal 2027 ($75.2B Data Center, $81.6B total), a later quarter reported in
May 2026. The panel disagreed: Gemini scored the agent correct, while the other two graded
against our literal ground truth and marked it wrong. That split is the tell. We checked
Nvidia's SEC filing, confirmed the agent had found the more recent and correct figures, and
fixed the ground truth. The cross-provider disagreement surfaced a bug in our own eval data,
not in the agent.

### 3. A bug in the judge harness itself (the truncation that hid grounding)

Several heavy multi-read questions came back correct but with low faithfulness, as if the
agent had asserted figures it had not retrieved. Investigating one of them, the supporting
figure ($965B for an Anthropic valuation) was present in the agent's evidence, but it sat at
character 21,502 of a 30,392-character evidence string, and the judge prompt truncated
evidence at 12,000 characters. The judges never saw the grounding and wrongly docked
faithfulness. The fix was to raise the evidence cap and re-judge the affected questions
without re-running the agent. Two questions moved from PARTIAL to PASS. The agent had been
well grounded all along; the measurement was wrong.

## Honest limitations

- The eval is 20 questions. It is a focused probe, not a benchmark of hundreds.
- Every run hits live services and is non-deterministic, so exact scores will vary run to
  run. The committed traces are a fixed snapshot.
- Pricing and "most recent quarter" questions are time sensitive; ground truths carry an
  as-of date and will eventually drift, which is partly why q17 needed correction.
- This is demo grade: no deployment, no auth, no multi-user.

## Why this is the part worth reading

Anyone can show an agent that passes. The signal of real engineering is an evaluation honest
enough to catch a reasoning error, a data error, and a flaw in its own scoring, and an author
who fixes all three and leaves the one true miss visible. That is the difference between a
demo and a system you can trust.
