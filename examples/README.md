# Example run traces

These are real, unedited agent runs (observation summaries trimmed for readability; the
full machine-readable event stream is in the matching `.jsonl`). They are committed so you
can inspect how the agent behaves without paying to run it.

Each trace shows the loop the model drives itself: PLAN (open sub-questions, what it just
observed), ACT (the tool and input it chose), OBSERVE (what came back, with a quality
flag), and the RE-ROUTE notes where it abandons a dead path. The control flow is decided
by the model at runtime, not hardcoded.

## normal-plus-recovery: `notion-competitive-brief`
Goal: "competitive brief on Notion: top 3 competitors and how each prices."
9 steps, 16 tool calls, 4 re-routes. A substantive run that also recovers: it tries the
official `notion.com/pricing` and `atlassian.com` pages, hits a JS wall / bot block, and
re-routes to third-party pricing trackers instead, then cross-checks figures before
answering. The re-route moments are the proof it is reacting to what it observes.

## Divergent pair: same agent, different goals, different tool paths
The two traces below come from the same agent with no per-question configuration. They take
visibly different paths, which is what separates an agent from a fixed pipeline.

- `q06-clean-path`: "On what date did Google close its acquisition of Wiz, and the price?"
  3 steps, 0 re-routes. The first sources are clean, so it searches, reads two primary
  sources to ground the date and price, and concludes. A short, direct path.

- `q11-recovery-path`: "Compare the API input price of Gemini 2.5 Pro, Claude Opus, and the
  current GPT-5 flagship." 5 re-routes, a repeated-call block, and a budget-ceiling stop.
  The agent struggles to pin the current GPT flagship price, keeps re-routing across
  sources, never repeats a failed call, and finally answers under the budget cap. This run
  also contains the one honest eval miss (it states a price tie that is not correct), which
  is documented in CASE_STUDY.md.

Files: `<name>.md` is the readable trace, `<name>.jsonl` is the raw event stream.
