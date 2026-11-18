"""
Task 7 — turn one or more eval runs into the committed baseline.

    python week2/task_07_eval_gate/scripts/make_baseline.py run1.json run2.json run3.json \
        --tolerance 0.08 --justification-file tolerance.md

* scores = the mean over the runs (one run's luck is not a baseline);
* each example's baseline verdict = the majority over the runs, and it is marked
  `flaky` for a metric if the runs disagreed, which the regression report then flags;
* `noise` records every run's scores, so the tolerance's justification is checkable;
* the tolerance and its justification are written INTO the file, next to the numbers.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

GATED = ("correctness", "groundedness")


def main(argv=None) -> int:
    here = Path(__file__).resolve().parent.parent
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("runs", type=Path, nargs="+")
    p.add_argument("--tolerance", type=float, required=True, help="allowed drop for correctness and groundedness")
    p.add_argument("--cost-tolerance", type=float, default=0.20, help="allowed rise in mean cost per question")
    p.add_argument("--justification-file", type=Path, required=True)
    p.add_argument("--out", type=Path, default=here / "eval_baseline.json")
    p.add_argument("--retrieval", type=Path, help="a --retrieval-only run on the same split (Week 3 Task 4)")
    p.add_argument("--retrieval-tolerance", type=float, nargs=2, metavar=("RECALL5", "MRR"),
                   default=(0.017, 0.02), help="allowed drop in recall@5 and MRR")
    args = p.parse_args(argv)

    runs = [json.loads(r.read_text(encoding="utf-8")) for r in args.runs]
    versions = {r["meta"]["dataset_version"] for r in runs}
    if len(versions) != 1:
        sys.exit(f"runs are on different datasets: {versions}")

    def mean(xs):
        return round(sum(xs) / len(xs), 4)

    # The metrics the runs have: Week 2 sets add retrieval_hit, Week 3 sets the deterministic scorer.
    METRICS = tuple(m for m in runs[0]["scores"] if all(m in r["scores"] for r in runs))

    by_id = {}
    for run in runs:
        for e in run["examples"]:
            by_id.setdefault(e["id"], []).append(e)
    examples = []
    for i, rows in sorted(by_id.items()):
        verdicts, flaky = {}, {}
        for m in METRICS:
            votes = Counter(r["scores"][m] for r in rows)
            verdicts[m] = 1 if votes[1] > votes[0] else 0           # a tie counts as a failure
            flaky[m] = len(votes) > 1
        examples.append({"id": i, "category": rows[0]["category"], "question": rows[0]["question"],
                         "scores": verdicts, "flaky": flaky, "votes": {m: [r["scores"][m] for r in rows] for m in METRICS}})

    cats = sorted({e["category"] for e in examples}, key=lambda c: list(runs[0]["by_category"]).index(c)
                  if c in runs[0]["by_category"] else 99)
    baseline = {
        "meta": {"date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "dataset_version": versions.pop(), "n": len(examples), "runs": len(runs),
                 "model": runs[0]["meta"]["model"], "judge": runs[0]["meta"]["judge"],
                 "runners": sorted({r["meta"]["runner"] for r in runs}),
                 "git_sha": runs[-1]["meta"]["git_sha"],
                 "experiment_urls": [r["meta"].get("experiment_url") for r in runs if r["meta"].get("experiment_url")],
                 "dataset_name": runs[0]["meta"].get("dataset_name"), "split": runs[0]["meta"].get("split")},
        "scores": {m: mean([r["scores"][m] for r in runs]) for m in METRICS},
        "tolerance": {"correctness": args.tolerance, "groundedness": args.tolerance,
                      "cost_increase": args.cost_tolerance},
        "tolerance_justification": args.justification_file.read_text(encoding="utf-8").strip(),
        "noise": {"per_run_scores": [{m: r["scores"][m] for m in METRICS} for r in runs],
                  "max_spread": {m: round(max(r["scores"][m] for r in runs) - min(r["scores"][m] for r in runs), 4)
                                 for m in METRICS},
                  "examples_with_disagreeing_runs": {m: [e["id"] for e in examples if e["flaky"][m]] for m in GATED}},
        "by_category": {c: {"n": runs[0]["by_category"][c]["n"],
                            **{m: mean([r["by_category"][c][m] for r in runs]) for m in METRICS}} for c in cats},
        "cost": {"mean_cost_usd": round(sum(r["cost"]["mean_cost_usd"] for r in runs) / len(runs), 7),
                 **{k: mean([r["cost"][k] for r in runs]) for k in ("mean_llm_calls", "mean_latency_s")}},
        "examples": examples,
    }
    if args.retrieval:
        r = json.loads(args.retrieval.read_text(encoding="utf-8"))
        ret = r["retrieval"]
        baseline["retrieval"] = {
            "dataset_version": r["meta"]["dataset_version"], "split": r["meta"]["split"],
            "retriever": ret["retriever"], "settings": ret.get("settings"),
            "scores": {k: ret["overall"][k] for k in ("recall@1", "recall@3", "recall@5", "recall@10", "mrr")},
            "tolerance": {"recall@5": args.retrieval_tolerance[0], "mrr": args.retrieval_tolerance[1]},
            "by_category": ret["by_category"],
            "per_example": {k: v["recall@5"] for k, v in ret["per_example"].items()}}
    args.out.write_text(json.dumps(baseline, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: baseline[k] for k in ("scores", "tolerance", "noise", "by_category", "cost")}, indent=1))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
