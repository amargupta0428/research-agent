# Eval results

_Generated 2026-06-18 12:14 · control=claude-sonnet-4-6 · extract=claude-haiku-4-5 · judge=claude-opus-4-8_

## Summary

- Questions: **20**
- PASS verdicts: **16/20** (80%)
- Avg correctness: **1.00** / 1.00
- Avg faithfulness: **0.83** / 1.00
- Cited: **100%**
- Keyword-match (programmatic): **95%**
- Total tokens (agents + judge): **346,989**

## Per-question

| ID | Question | Verdict | Correct | Faithful | Cited | KW | Steps | Tok | Conf |
|----|----------|---------|---------|----------|-------|----|-------|-----|------|
| q01 | Who founded Stripe? | PASS | 1.0 | 1.0 | ✓ | ✓ | 2 | 5191 | high — |
| q02 | What year was Airbnb founded? | PARTIAL | 1.0 | 0.5 | ✓ | ✓ | 1 | 2048 | high — |
| q03 | Where is Shopify headquartered? | PASS | 1.0 | 1.0 | ✓ | ✓ | 2 | 4770 | high,  |
| q04 | Who is the current CEO of Microsoft? | PASS | 1.0 | 1.0 | ✓ | ✓ | 2 | 5125 | high - |
| q05 | Which company acquired GitHub, and in what … | PASS | 1.0 | 1.0 | ✓ | ✓ | 2 | 5003 | high — |
| q06 | Who are the main competitors of Slack in te… | PASS | 1.0 | 1.0 | ✓ | ✓ | 5 | 32786 | high — |
| q07 | What is Databricks best known for as a prod… | PASS | 1.0 | 1.0 | ✓ | ✓ | 3 | 17608 | high — |
| q08 | Name the co-founders of OpenAI. | PASS | 1.0 | 1.0 | ✓ | ✓ | 3 | 13293 | high — |
| q09 | What year did Zoom (Zoom Video Communicatio… | PASS | 1.0 | 1.0 | ✓ | ✓ | 3 | 8313 | high — |
| q10 | Which company owns Instagram? | PARTIAL | 1.0 | 0.0 | ✓ | ✓ | 2 | 4332 | high — |
| q11 | Who are Notion's primary competitors? | PASS | 1.0 | 1.0 | ✓ | ✓ | 4 | 26664 | high — |
| q12 | What is Snowflake's core product? | PASS | 1.0 | 1.0 | ✓ | ✗ | 4 | 20884 | high — |
| q13 | Who is the founder and CEO of Nvidia? | PASS | 1.0 | 1.0 | ✓ | ✓ | 2 | 5348 | high - |
| q14 | What year was SpaceX founded? | PARTIAL | 1.0 | 0.0 | ✓ | ✓ | 1 | 2021 | high — |
| q15 | Which payment companies compete most direct… | PASS | 1.0 | 0.7 | ✓ | ✓ | 10 | 101098 | high - |
| q16 | Where is Spotify headquartered? | PASS | 1.0 | 1.0 | ✓ | ✓ | 2 | 4959 | high,  |
| q17 | Which company acquired LinkedIn, and in wha… | PASS | 1.0 | 1.0 | ✓ | ✓ | 2 | 4881 | high,  |
| q18 | Besides Jira, name a major product made by … | PARTIAL | 1.0 | 0.5 | ✓ | ✓ | 3 | 11154 | high — |
| q19 | Who founded Canva? | PASS | 1.0 | 1.0 | ✓ | ✓ | 2 | 5166 | high — |
| q20 | What market does Klarna primarily operate in? | PASS | 1.0 | 1.0 | ✓ | ✓ | 3 | 12935 | high — |

## Notes

- Full per-question traces + scores: `eval/results/<id>.json` and `<id>.trace.jsonl`.
- `faithful` is judged against the evidence the agent actually retrieved (grounding), not the judge's own knowledge.
- `KW` is a high-precision programmatic check; the judge handles paraphrase and free-text correctness.
