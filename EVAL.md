# Eval results

_Generated 2026-06-19 19:56 · control=claude-sonnet-4-6 · extract=claude-haiku-4-5_

**Judge panel (cross-provider):** gpt-5.4 (openai), gemini-3.5-flash (gemini), opus-4.8 (anthropic). Each answer is scored by every available judge; we report **both the median and the mean** across the panel (median is robust to one outlier judge; mean is conservative). We deliberately do not hide panel disagreement behind a single number.

## Summary

- Questions: **20**
- PASS rate: **median agg 19/20 (95%)**, mean agg 17/20 (85%)
- Avg correctness (median/mean): **0.99** / 0.97
- Avg faithfulness (median/mean): **0.99** / 0.96  _(grounded in retrieved evidence)_
- Avg precision (median/mean): **0.97** / 0.95  _(no wrong/hallucinated entities)_
- Cited: **100%**
- Keyword-match (programmatic): **95%**
- Total agent tokens: **682,433**

_Values shown as median/mean. Where the two verdicts differ, the panel disagreed; see the per-judge votes in `eval/results/<id>.json`._

## Per-question

| ID | Question | Verdict med/mean | Correct med/mean | Faithful med/mean | Prec med/mean | Cited | KW | Steps | Reads | Tok |
|----|----------|------------------|------------------|-------------------|---------------|-------|----|-------|-------|-----|
| q01 | Identify the lead investor and the exact po... | PASS | 1.0/1.0 | 1.0/0.9 | 1.0/0.933 | ✓ | ✓ | 4 | 2 | 19028 |
| q02 | Determine the size, valuation, and lead inv... | PASS | 1.0/1.0 | 1.0/0.967 | 1.0/0.983 | ✓ | ✓ | 3 | 2 | 16496 |
| q03 | Find the seed round size, valuation, and le... | PASS | 1.0/1.0 | 1.0/1.0 | 1.0/0.967 | ✓ | ✓ | 4 | 2 | 21661 |
| q04 | Identify the IPO offer price per share, gro... | PASS/PARTIAL | 1.0/0.833 | 1.0/1.0 | 1.0/1.0 | ✓ | ✗ | 4 | 2 | 21024 |
| q05 | Determine the amount raised, valuation, and... | PASS | 1.0/1.0 | 1.0/1.0 | 1.0/1.0 | ✓ | ✓ | 3 | 2 | 13414 |
| q06 | On what exact date did Google complete (clo... | PASS | 1.0/1.0 | 1.0/1.0 | 1.0/1.0 | ✓ | ✓ | 3 | 2 | 15614 |
| q07 | Whom did Intel appoint as its permanent CEO... | PASS | 1.0/1.0 | 1.0/0.983 | 1.0/1.0 | ✓ | ✓ | 6 | 2 | 28043 |
| q08 | How much did OpenAI pay to acquire Jony Ive... | PASS | 1.0/1.0 | 1.0/0.983 | 1.0/1.0 | ✓ | ✓ | 5 | 4 | 32924 |
| q09 | Identify the size of Nvidia's announced inv... | PASS | 1.0/1.0 | 1.0/1.0 | 1.0/1.0 | ✓ | ✓ | 4 | 1 | 14624 |
| q10 | Compare the standard individual paid 'Pro' ... | PASS | 1.0/1.0 | 1.0/0.917 | 1.0/1.0 | ✓ | ✓ | 3 | 1 | 16746 |
| q11 | Compare the standard API input price per 1 ... | PARTIAL | 0.75/0.75 | 0.9/0.633 | 0.6/0.467 | ✓ | ✓ | 8 | 6 | 106008 |
| q12 | Compare the standard API output price per 1... | PASS | 1.0/1.0 | 1.0/0.967 | 1.0/0.933 | ✓ | ✓ | 7 | 7 | 85791 |
| q13 | Compare the most recent disclosed/reported ... | PASS | 1.0/1.0 | 0.95/0.95 | 0.975/0.975 | ✓ | ✓ | 6 | 5 | 75682 |
| q14 | Compare the entry individual paid tier mont... | PASS/PARTIAL | 1.0/0.833 | 1.0/1.0 | 0.9/0.867 | ✓ | ✓ | 8 | 6 | 73834 |
| q15 | Compare the standard individual monthly sub... | PASS | 1.0/1.0 | 1.0/0.967 | 1.0/1.0 | ✓ | ✓ | 4 | 4 | 38301 |
| q16 | Find the exact number of jobs Microsoft cut... | PASS | 1.0/1.0 | 1.0/1.0 | 1.0/1.0 | ✓ | ✓ | 4 | 2 | 20287 |
| q17 | Find Nvidia's Data Center segment revenue a... | PASS | 1.0/1.0 | 1.0/1.0 | 1.0/1.0 | ✓ | ✓ | 3 | 1 | 17813 |
| q18 | Find Spotify's Monthly Active Users (MAU) a... | PASS | 1.0/1.0 | 1.0/1.0 | 1.0/1.0 | ✓ | ✓ | 4 | 1 | 19243 |
| q19 | Find the global cloud infrastructure servic... | PASS | 1.0/1.0 | 1.0/0.95 | 1.0/1.0 | ✓ | ✓ | 3 | 2 | 16235 |
| q20 | Find Meta Platforms' 2026 capital expenditu... | PASS | 1.0/1.0 | 1.0/0.933 | 1.0/0.967 | ✓ | ✓ | 5 | 1 | 29665 |

## Notes

- Full per-question traces + every judge's individual vote + reasoning: `eval/results/<id>.json` and `<id>.trace.jsonl`.
- **Median vs mean**: median = majority of the panel (robust to one harsh/lenient judge); mean = average (conservative). A row where they differ is a row the judges disagreed on; read the per-judge reasoning.
- **faithful** is judged against the evidence the agent actually retrieved (grounding), not the judges' own knowledge. This is what catches answering-from-memory.
- **precision** penalizes wrong/hallucinated entities so listing many names can't win on keyword recall alone.
- **Reads** = pages actually fetched and read (not just searched); the agent is blocked from concluding until it has read at least 1 supporting source. Forcing a read trades extra tokens/latency for genuine grounding, a deliberate choice for a research agent.
- The three issues this eval surfaced (a real agent error, a stale ground-truth, and a bug in this judge harness) are written up in `CASE_STUDY.md`.
