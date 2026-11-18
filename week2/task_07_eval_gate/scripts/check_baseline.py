"""
Task 7 — the threshold gate: compare an eval run with the committed baseline.

    python week2/task_07_eval_gate/scripts/check_baseline.py \
        --results eval_results.json --baseline week2/task_07_eval_gate/eval_baseline.json \
        --report regression_report.md

Exit 1 (the job goes red) if, versus the baseline:
  * correctness or groundedness dropped by MORE than the committed tolerance, or
  * mean cost per question rose by more than the cost tolerance (stretch: +20%).
Otherwise exit 0. A dataset change is not a failure, but the report says the
baseline should be refreshed.

The report (markdown, posted as the PR comment) shows the overall scores, the
CATEGORY SPLIT (the roadmap a blended average hides) and, most importantly, WHICH
examples flipped verdict: "#7 and #22 went correct -> incorrect" is actionable,
"0.90 -> 0.85" is not.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

GATED = ("correctness", "groundedness")
ARCHIVED_BASELINES = {"eval_baseline_w2.json"}     # Week 3 Task 1: kept for history, never a gate
SHOWN = ("correctness", "groundedness", "deterministic", "retrieval_hit")   # whichever the run has


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fmt(x) -> str:
    return "–" if x is None else f"{x:.2f}"


def delta(a, b) -> str:
    if a is None or b is None:
        return ""
    d = b - a
    return "±0.00" if abs(d) < 0.005 else f"{d:+.2f}"


def check(results: dict, baseline: dict) -> tuple[bool, list[str], dict]:
    """(passed, reasons it failed, details for the report)."""
    tol = baseline["tolerance"]
    failures = []
    for m in GATED:
        floor = baseline["scores"][m] - tol[m]
        if results["scores"][m] < floor - 1e-9:
            failures.append(f"**{m}** {results['scores'][m]:.3f} is below the baseline "
                            f"{baseline['scores'][m]:.3f} minus the tolerance {tol[m]:.3f} (floor {floor:.3f})")
    cost_tol = tol.get("cost_increase")
    base_cost = (baseline.get("cost") or {}).get("mean_cost_usd")
    now_cost = (results.get("cost") or {}).get("mean_cost_usd")
    if cost_tol is not None and base_cost and now_cost is not None and now_cost > base_cost * (1 + cost_tol):
        failures.append(f"**mean cost per question** ${now_cost:.6f} is more than {cost_tol:.0%} above the "
                        f"baseline ${base_cost:.6f}")

    base_ex = {e["id"]: e for e in baseline["examples"]}
    flips = {"regressed": [], "improved": []}
    for r in results["examples"]:
        b = base_ex.get(r["id"])
        if not b:
            continue
        for m in GATED:
            was, now = b["scores"][m], r["scores"][m]
            if was != now:
                (flips["regressed"] if now < was else flips["improved"]).append(
                    {"id": r["id"], "category": r["category"], "metric": m, "question": r["question"],
                     "comment": r["comments"].get(m, ""), "flaky_in_baseline": b.get("flaky", {}).get(m, False),
                     "answer": (r.get("answer") or "")[:160]})
    return not failures, failures, {"flips": flips, "base_cost": base_cost, "now_cost": now_cost}


def report(results: dict, baseline: dict, passed: bool, failures: list[str], details: dict) -> str:
    rm, bm = results["meta"], baseline["meta"]
    tol = baseline["tolerance"]
    L = [f"## Eval gate: {'✅ passed' if passed else '❌ FAILED'}", ""]
    if failures:
        L += ["**Why it failed:**", *[f"- {f}" for f in failures], ""]
    if rm.get("dataset_version") != bm.get("dataset_version"):
        L += [f"> ⚠️ Dataset changed since the baseline ({bm.get('dataset_version')} → {rm.get('dataset_version')}). "
              "Compared on the examples both have; refresh the baseline in the PR that changes the dataset.", ""]
    L += ["| Metric | Baseline | This run | Δ | Tolerance |", "|---|---:|---:|---:|---:|"]
    for m in [m for m in SHOWN if m in results["scores"] or m in baseline["scores"]]:
        L.append(f"| {m} | {fmt(baseline['scores'].get(m))} | {fmt(results['scores'].get(m))} | "
                 f"{delta(baseline['scores'].get(m), results['scores'].get(m))} | {fmt(tol.get(m)) if m in GATED else 'not gated'} |")
    if details["base_cost"] and details["now_cost"] is not None:
        change = details["now_cost"] / details["base_cost"] - 1
        L.append(f"| mean cost / question | ${details['base_cost']:.6f} | ${details['now_cost']:.6f} | "
                 f"{change:+.0%} | +{tol.get('cost_increase', 0):.0%} |")
    L += ["", "**By category** (correctness / groundedness):", "",
          "| Category | n | Baseline | This run |", "|---|---:|---:|---:|"]
    for cat, now in results["by_category"].items():
        base = baseline["by_category"].get(cat, {})
        L.append(f"| {cat} | {now['n']} | {fmt(base.get('correctness'))} / {fmt(base.get('groundedness'))} | "
                 f"{fmt(now['correctness'])} / {fmt(now['groundedness'])} |")
    flips = details["flips"]
    L += ["", f"**Examples that changed verdict vs the baseline:** {len(flips['regressed'])} regressed, "
              f"{len(flips['improved'])} improved", ""]
    for title, items, arrow in (("Regressed", flips["regressed"], "1 → 0"), ("Improved", flips["improved"], "0 → 1")):
        if not items:
            continue
        L += [f"<details{' open' if title == 'Regressed' else ''}><summary>{title} ({len(items)})</summary>", "",
              "| # | Category | Metric | Question | Judge / reason |", "|---:|---|---|---|---|"]
        for f in items:
            flaky = " *(flaky in baseline)*" if f["flaky_in_baseline"] else ""
            L.append(f"| {f['id']} | {f['category']} | {f['metric']} {arrow}{flaky} | {f['question']} | "
                     f"{f['comment'].replace('|', '/')[:180]} |")
        L += ["", "</details>", ""]
    L += [f"<sub>Run: {rm.get('n')} examples, model `{rm.get('model')}`, judge `{rm.get('judge')}`, "
          f"{rm.get('runner')}, {rm.get('wall_clock_s')} s, commit `{str(rm.get('git_sha'))[:8]}`"
          + (f", [LangSmith experiment]({rm['experiment_url']})" if rm.get("experiment_url") else "")
          + f". Baseline: {bm.get('date', '')[:10]}, dataset {bm.get('dataset_version')}.</sub>"]
    return "\n".join(L)


def check_retrieval(run: dict, baseline: dict) -> tuple[bool, list[str], str]:
    """Week 3 Task 4: the retrieval gate. `run` is a --retrieval-only results file, `baseline` the
    eval_baseline.json with a "retrieval" section. Red if recall@5 or MRR fell by more than its
    tolerance (derived from the noise floor: week3/EXPERIMENTS.md). Lists every question that left
    the top 5, even when the drop is within the tolerance."""
    base = baseline.get("retrieval")
    if not base:
        return True, [], "*(no retrieval baseline: retrieval not gated)*"
    now = run["retrieval"]
    tol = base["tolerance"]
    failures = []
    for m in ("recall@5", "mrr"):
        floor = base["scores"][m] - tol[m]
        if now["overall"][m] < floor - 1e-9:
            failures.append(f"**retrieval {m}** {now['overall'][m]:.3f} is below the baseline {base['scores'][m]:.3f} "
                            f"minus the tolerance {tol[m]:.3f} (floor {floor:.3f})")
    if run["meta"].get("dataset_version") != base.get("dataset_version"):
        failures.append(f"retrieval run is on dataset {run['meta'].get('dataset_version')}, the baseline on "
                        f"{base.get('dataset_version')}: refresh the retrieval baseline")
    lost = [k for k, v in now["per_example"].items() if base["per_example"].get(k, 0) == 1 and v["recall@5"] == 0]
    gained = [k for k, v in now["per_example"].items() if base["per_example"].get(k, 1) == 0 and v["recall@5"] == 1]
    L = ["", "**Retrieval** (dev, no LLM; tolerance from the noise floor):", "",
         "| Metric | Baseline | This run | Δ | Tolerance |", "|---|---:|---:|---:|---:|"]
    for m in ("recall@1", "recall@5", "mrr"):
        b, n = base["scores"].get(m), now["overall"].get(m)
        L.append(f"| {m} | {fmt(b)} | {fmt(n)} | {delta(b, n)} | {fmt(tol[m]) if m in tol else 'not gated'} |")
    L += ["", f"Questions that left the top 5: {', '.join(lost) or 'none'} · entered it: {', '.join(gained) or 'none'}"]
    return not failures, failures, "\n".join(L)


def main(argv=None) -> int:
    here = Path(__file__).resolve().parent.parent
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--results", type=Path, default=Path("eval_results.json"))
    p.add_argument("--baseline", type=Path, default=here / "eval_baseline.json")
    p.add_argument("--report", type=Path, default=Path("regression_report.md"))
    p.add_argument("--retrieval-results", type=Path, help="a --retrieval-only results file (Week 3 Task 4)")
    p.add_argument("--retrieval-only", action="store_true", help="gate retrieval only (the per-PR job: no LLM)")
    args = p.parse_args(argv)

    # Week 3 Task 1: the Week 2 baseline was measured on the 4-file Week 1 corpus and no longer
    # describes the system. It is archived (renamed, not edited) and must never gate a run again;
    # Week 3 Task 2 commits the new eval_baseline.json. Until then the gate is red, with this reason.
    problem = None
    if args.baseline.name in ARCHIVED_BASELINES:
        problem = (f"`{args.baseline.name}` is an ARCHIVED baseline (Week 2 corpus). It must not be used to "
                   "gate a run: compare against the current eval_baseline.json.")
    elif not args.baseline.exists():
        problem = (f"No current baseline at `{args.baseline}`. The Week 2 baseline was archived as "
                   "eval_baseline_w2.json in Week 3 Task 1 (it describes the old corpus); Week 3 Task 2 "
                   "sets the new one (make_baseline.py). The gate cannot vouch for quality until then.")
    if problem:
        text = f"## Eval gate: ❌ NO BASELINE\n\n{problem}"
        args.report.write_text(text + "\n", encoding="utf-8")
        print(text)
        if os.getenv("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
                f.write(text + "\n")
        return 1

    baseline = load(args.baseline)
    if args.retrieval_only:
        passed, failures, rtext = check_retrieval(load(args.retrieval_results), baseline)
        text = (f"## Retrieval gate: {'✅ passed' if passed else '❌ FAILED'}\n"
                + ("\n**Why it failed:**\n" + "\n".join(f"- {f}" for f in failures) + "\n" if failures else "")
                + rtext)
    else:
        results = load(args.results)
        passed, failures, details = check(results, baseline)
        rtext = ""
        if args.retrieval_results:
            r_ok, r_fail, rtext = check_retrieval(load(args.retrieval_results), baseline)
            passed, failures = passed and r_ok, failures + r_fail
        text = report(results, baseline, passed, failures, details) + ("\n" + rtext if rtext else "")
    args.report.write_text(text + "\n", encoding="utf-8")
    print(text)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(text + "\n")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
