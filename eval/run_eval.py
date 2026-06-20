"""Run the eval suite and produce EVAL.md.

For each question: run the agent (tighter eval budget), collect the final answer +
the evidence it actually retrieved, score it with a CROSS-PROVIDER judge panel, and save
the full per-question trace + scores to eval/results/ for hand spot-checking.

    python -m eval.run_eval            # all questions
    python -m eval.run_eval q01 q05    # a subset
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import yaml

from agent import config
from agent.loop import run_agent
from eval.judges import available_panel, judge_answer

HERE = Path(__file__).parent
RESULTS = HERE / "results"
EVAL_MD = HERE.parent / "EVAL.md"


def _evidence_from_trace(trace) -> str:
    """Reconstruct what the agent actually saw, for faithfulness grounding."""
    chunks = []
    for e in trace.events:
        if e.kind == "observation":
            chunks.append(
                f"[{e.data.get('tool')} · {e.data.get('quality')}] {e.data.get('summary', '')}"
            )
    return "\n\n".join(chunks)


def run_one(q: dict) -> dict:
    print(f"\n=== {q['id']}: {q['goal']} ===")
    t0 = time.time()
    result = run_agent(q["goal"], budget=config.EVAL_BUDGET)
    evidence = _evidence_from_trace(result["trace"])
    answer = result["answer"]
    cites = result["citations"]

    scores = judge_answer(q["goal"], q["expected"], answer, evidence, q.get("keywords", []))
    has_cites = bool(cites) or bool(re.search(r"\[\d+\]", answer))
    scores["cited"] = bool(scores.get("cited")) or has_cites

    record = {
        "id": q["id"],
        "goal": q["goal"],
        "kind": q["kind"],
        "expected": q["expected"],
        "answer": answer,
        "citations": cites,
        "confidence": result["confidence"],
        "scores": scores,
        "stopped_reason": result["stopped_reason"],
        "steps": result["steps"],
        "reads": result.get("reads"),
        "tool_calls": result["tool_calls"],
        "apify_runs": result["apify_runs"],
        "tokens": result["tokens"],
        "elapsed": round(time.time() - t0, 1),
    }
    RESULTS.mkdir(exist_ok=True)
    with open(RESULTS / f"{q['id']}.json", "w") as f:
        json.dump(record, f, indent=2, default=str)
    result["trace"].save_jsonl(str(RESULTS / f"{q['id']}.trace.jsonl"))

    s = scores
    panel = "/".join(j["judge"] for j in s.get("per_judge", []) if "error" not in j)
    print(
        f"  -> {s.get('verdict_median', '?')}/{s.get('verdict_mean', '?')} (med/mean)  "
        f"correct={s.get('correct_median')}/{s.get('correct_mean')} "
        f"faithful={s.get('faithful_median')}/{s.get('faithful_mean')} "
        f"prec={s.get('precision_median')}/{s.get('precision_mean')} "
        f"cited={s.get('cited')} kw={s.get('keyword_hit')} "
        f"[panel: {panel or 'NONE'}] ({record['steps']} steps, "
        f"{record['reads']} reads, {record['tokens']} tok)"
    )
    return record


def write_eval_md(records: list[dict]) -> None:
    n = len(records)

    def avg(k):
        return sum(r["scores"].get(k, 0) for r in records) / max(n, 1)

    def pass_rate(vkey):
        return sum(1 for r in records if r["scores"].get(vkey) == "PASS")

    cited = sum(1 for r in records if r["scores"].get("cited")) / max(n, 1)
    pass_med, pass_mean = pass_rate("verdict_median"), pass_rate("verdict_mean")
    kw = sum(1 for r in records if r["scores"].get("keyword_hit")) / max(n, 1)
    total_tok = sum(r["tokens"] for r in records)
    panel_labels = [f"{m[2]} ({m[0]})" for m in available_panel()]

    lines = [
        "# Eval results",
        "",
        f"_Generated {time.strftime('%Y-%m-%d %H:%M')} · "
        f"control={config.CONTROL_MODEL} · extract={config.EXTRACT_MODEL}_",
        "",
        f"**Judge panel (cross-provider):** {', '.join(panel_labels) or 'NONE AVAILABLE'}. "
        "Each answer is scored by every available judge; we report **both the median and the "
        "mean** across the panel (median is robust to one outlier judge; mean is conservative). "
        "We deliberately do not hide panel disagreement behind a single number.",
        "",
        "## Summary",
        "",
        f"- Questions: **{n}**",
        f"- PASS rate: **median agg {pass_med}/{n} ({pass_med / max(n, 1) * 100:.0f}%)**, "
        f"mean agg {pass_mean}/{n} ({pass_mean / max(n, 1) * 100:.0f}%)",
        f"- Avg correctness (median/mean): **{avg('correct_median'):.2f}** / {avg('correct_mean'):.2f}",
        f"- Avg faithfulness (median/mean): **{avg('faithful_median'):.2f}** / {avg('faithful_mean'):.2f}  "
        "_(grounded in retrieved evidence)_",
        f"- Avg precision (median/mean): **{avg('precision_median'):.2f}** / {avg('precision_mean'):.2f}  "
        "_(no wrong/hallucinated entities)_",
        f"- Cited: **{cited * 100:.0f}%**",
        f"- Keyword-match (programmatic): **{kw * 100:.0f}%**",
        f"- Total agent tokens: **{total_tok:,}**",
        "",
        "_Values shown as median/mean. Where the two verdicts differ, the panel disagreed; "
        "see the per-judge votes in `eval/results/<id>.json`._",
        "",
        "## Per-question",
        "",
        "| ID | Question | Verdict med/mean | Correct med/mean | Faithful med/mean | "
        "Prec med/mean | Cited | KW | Steps | Reads | Tok |",
        "|----|----------|------------------|------------------|-------------------|"
        "---------------|-------|----|-------|-------|-----|",
    ]
    for r in records:
        s = r["scores"]
        goal = r["goal"].replace("—", ", ").replace(" – ", ", ")
        q = goal if len(goal) < 46 else goal[:43] + "..."
        vm, vmn = s.get("verdict_median", "?"), s.get("verdict_mean", "?")
        vcell = vm if vm == vmn else f"{vm}/{vmn}"
        lines.append(
            f"| {r['id']} | {q} | {vcell} | "
            f"{s.get('correct_median')}/{s.get('correct_mean')} | "
            f"{s.get('faithful_median')}/{s.get('faithful_mean')} | "
            f"{s.get('precision_median')}/{s.get('precision_mean')} | "
            f"{'✓' if s.get('cited') else '✗'} | {'✓' if s.get('keyword_hit') else '✗'} | "
            f"{r['steps']} | {r.get('reads', '?')} | {r['tokens']} |"
        )
    lines += [
        "",
        "## Notes",
        "",
        "- Full per-question traces + every judge's individual vote + reasoning: "
        "`eval/results/<id>.json` and `<id>.trace.jsonl`.",
        "- **Median vs mean**: median = majority of the panel (robust to one harsh/lenient "
        "judge); mean = average (conservative). A row where they differ is a row the "
        "judges disagreed on; read the per-judge reasoning.",
        "- **faithful** is judged against the evidence the agent actually retrieved "
        "(grounding), not the judges' own knowledge. This is what catches "
        "answering-from-memory.",
        "- **precision** penalizes wrong/hallucinated entities so listing many names "
        "can't win on keyword recall alone.",
        "- **Reads** = pages actually fetched and read (not just searched); the agent is "
        "blocked from concluding until it has read at least 1 supporting source. Forcing a "
        "read trades extra tokens/latency for genuine grounding, a deliberate choice for a "
        "research agent.",
        "- The three issues this eval surfaced (a real agent error, a stale ground-truth, "
        "and a bug in this judge harness) are written up in `CASE_STUDY.md`.",
        "",
    ]
    EVAL_MD.write_text("\n".join(lines))
    print(f"\nWrote {EVAL_MD}")


def main() -> None:
    questions = yaml.safe_load((HERE / "questions.yaml").read_text())
    wanted = set(sys.argv[1:])
    if wanted:
        questions = [q for q in questions if q["id"] in wanted]
    if not available_panel():
        print(
            "WARNING: no judge API keys found — set OPENAI_API_KEY / GEMINI_API_KEY / "
            "ANTHROPIC_API_KEY. Scoring will fail."
        )
    records = [run_one(q) for q in questions]
    write_eval_md(records)


if __name__ == "__main__":
    main()
