"""
Task 5 — cost report: run the eval questions with instrumentation on and print
what they cost, per question, in aggregate, per graph node, and by node path.

    make cost                                           # all eval questions
    python week2/task_05_observability/scripts/cost_report.py --n 5
    MAX_DOCS_TO_GRADE=2 make cost                       # cost side of the grading experiment

It runs the SAME code path as the API (`ChatService` from app/, with the same
per-node telemetry that writes the request log lines), minus HTTP, so these numbers
and the production log lines can't disagree. Each question gets a fresh session.

Pricing: COST_PER_1K_INPUT_TOKENS / COST_PER_1K_OUTPUT_TOKENS (settings, .env).
Tokens are counted by the model that ran, from the provider's own usage report.

The output fills in week2/COST.md and the node-path table in week2/RESULTS.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from app.capstone import load_capstone  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.observability import Observer, percentile  # noqa: E402

QUESTIONS_PER_DAY = 1000
NODE_ORDER = ["contextualize", "route_question", "retrieve", "grade_documents", "rewrite_query",
              "generate", "grade_generation", "direct_answer", "refuse"]


# Week 3 Task 6: every request is someone's. A question without a user_id is asked by an ordinary employee.
DEFAULT_USER = "u1001"


def load_questions(n: int | None) -> list[dict]:
    """EVAL_DATASET_PATH (jsonl with a "question" field) if set and present, else the
    capstone's own eval set (the one `make eval` runs: 24 answerable + 4 out-of-scope)."""
    path = os.getenv("EVAL_DATASET_PATH")
    if path and (REPO_ROOT / path).exists():
        with open(REPO_ROOT / path, encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
        qs = [{"question": r["question"], "out_of_scope": bool(r.get("expect_refusal")),
               "user_id": r.get("user_id") or DEFAULT_USER} for r in rows]
    else:
        qs = [{"question": q, "out_of_scope": src is None, "user_id": DEFAULT_USER}
              for q, _ans, src, _fact in load_capstone().EVAL_EXAMPLES]
    return qs[:n] if n else qs


class CollectingObserver(Observer):
    """Keeps every request record (the exact dict the API logs) instead of only logging it."""

    def __init__(self):
        super().__init__()
        self.records: list[dict] = []

    def request_finished(self, rec: dict) -> None:
        self.records.append(dict(rec))


# ---------------------------------------------------------------------------
# Path classification: how often does each path fire, and who triggers a rewrite?
# ---------------------------------------------------------------------------
def classify(path: list[str]) -> str:
    if "direct_answer" in path:
        return "route → direct → END"
    rewrites = path.count("rewrite_query")
    end = "refused" if path and path[-1] == "refuse" else "answered"
    if rewrites == 0:
        return f"route → retrieve → grade → generate → check → END ({end})" if "generate" in path \
            else f"route → retrieve → grade → refuse ({end})"
    return f"…with {rewrites} rewrite loop{'s' if rewrites > 1 else ''} ({end})"


def rewrite_triggers(path: list[str]) -> list[str]:
    """For each rewrite_query: which check sent the graph there."""
    out = []
    for i, node in enumerate(path):
        if node == "rewrite_query" and i > 0:
            out.append({"grade_documents": "doc grader rejected every passage",
                        "grade_generation": "fact-check rejected the answer"}.get(path[i - 1], path[i - 1]))
    return out


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def fmt_usd(x: float) -> str:
    return f"${x:.6f}" if x < 0.01 else f"${x:,.2f}"


def build_report(runs: list[dict], settings, wall_s: float) -> tuple[str, dict]:
    n = len(runs)
    ok = [r for r in runs if r["status"] == "ok"]
    lat = sorted(r["latency_ms"] / 1000 for r in ok)
    mean = lambda xs: sum(xs) / len(xs) if xs else 0.0  # noqa: E731
    mean_cost = mean([r["estimated_cost_usd"] for r in ok])
    agg = {
        "n": n, "ok": len(ok), "errors": n - len(ok),
        "mean_latency_s": mean(lat), "p50_latency_s": percentile(lat, 50), "p95_latency_s": percentile(lat, 95),
        "mean_llm_calls": mean([r["llm_calls"] for r in ok]),
        "p95_llm_calls": percentile(sorted(r["llm_calls"] for r in ok), 95),
        "max_llm_calls": max((r["llm_calls"] for r in ok), default=0),
        "mean_tokens_in": mean([r["tokens_in"] for r in ok]), "mean_tokens_out": mean([r["tokens_out"] for r in ok]),
        "mean_cost_usd": mean_cost, "total_cost_usd": sum(r["estimated_cost_usd"] for r in ok),
        "projected_monthly_usd_at_1000_per_day": mean_cost * QUESTIONS_PER_DAY * 30,
        "refusal_rate": mean([float(r["refused"]) for r in ok]),
        "mean_retries": mean([r["retries"] for r in ok]),
        "wall_clock_s": wall_s, "model": settings.llm_label,
        "price_per_1k": [settings.cost_per_1k_input_tokens, settings.cost_per_1k_output_tokens],
        "max_docs_to_grade": settings.max_docs_to_grade, "retriever_k": settings.retriever_k,
    }

    # per node
    per = defaultdict(lambda: Counter())
    for r in ok:
        for node, s in r["per_node"].items():
            c = per[node]
            c["llm_calls"] += s["llm_calls"]
            c["tokens_in"] += s["tokens_in"]
            c["tokens_out"] += s["tokens_out"]
            c["ms"] += s["ms"]
            c["llm_ms"] += s["llm_ms"]
            c["runs"] += s["runs"]
    total_cost = sum(settings.cost_usd(c["tokens_in"], c["tokens_out"]) for c in per.values()) or 1e-12
    total_ms = sum(c["ms"] for c in per.values()) or 1e-12
    nodes = []
    for node, c in per.items():
        cost = settings.cost_usd(c["tokens_in"], c["tokens_out"])
        nodes.append({"node": node, "calls_per_q": c["llm_calls"] / len(ok), "runs_per_q": c["runs"] / len(ok),
                      "tokens_in_per_q": c["tokens_in"] / len(ok), "tokens_out_per_q": c["tokens_out"] / len(ok),
                      "cost_per_q": cost / len(ok), "pct_cost": 100 * cost / total_cost,
                      "ms_per_q": c["ms"] / len(ok), "pct_time": 100 * c["ms"] / total_ms})
    nodes.sort(key=lambda x: -x["cost_per_q"])

    # paths
    paths = Counter(classify(r["node_path"]) for r in ok)
    triggers = Counter(t for r in ok for t in rewrite_triggers(r["node_path"]))
    fired = sum(1 for r in ok if "rewrite_query" in r["node_path"])

    L = []
    L.append(f"Model: {settings.llm_label}   pricing: ${settings.cost_per_1k_input_tokens}/1K in, "
             f"${settings.cost_per_1k_output_tokens}/1K out   k={settings.retriever_k}   "
             f"MAX_DOCS_TO_GRADE={settings.max_docs_to_grade}")
    L.append(f"{n} questions ({sum(r['out_of_scope'] for r in runs)} out-of-scope), "
             f"{len(ok)} ok, {n - len(ok)} errors, wall clock {wall_s:.0f} s\n")

    L.append("## 1. Per question\n")
    L.append("| # | Question | Latency | LLM calls | Tokens in / out | Cost | Path len | Rewrites | Refused |")
    L.append("|---:|---|---:|---:|---:|---:|---:|---:|---|")
    for i, r in enumerate(runs, 1):
        q = r["question"] if len(r["question"]) <= 48 else r["question"][:45] + "…"
        if r["status"] != "ok":
            L.append(f"| {i} | {q} | ERROR | | | | | | {r.get('error', '')[:60]} |")
            continue
        L.append(f"| {i} | {q} | {r['latency_ms'] / 1000:.1f} s | {r['llm_calls']} | "
                 f"{r['tokens_in']:,} / {r['tokens_out']:,} | {fmt_usd(r['estimated_cost_usd'])} | "
                 f"{len(r['node_path'])} | {r['retries']} | {'yes' if r['refused'] else ''} |")

    L.append("\n## 2. Aggregate\n")
    L.append("| Metric | Value |\n|---|---:|")
    L.append(f"| Mean latency per question | {agg['mean_latency_s']:.2f} s |")
    L.append(f"| p95 latency per question | {agg['p95_latency_s']:.2f} s |")
    L.append(f"| Mean LLM calls per question | {agg['mean_llm_calls']:.1f} (p95 {agg['p95_llm_calls']:.0f}, "
             f"max {agg['max_llm_calls']}) |")
    L.append(f"| Mean tokens per question (in / out) | {agg['mean_tokens_in']:,.0f} / {agg['mean_tokens_out']:,.0f} |")
    L.append(f"| Mean cost per question | {fmt_usd(agg['mean_cost_usd'])} |")
    L.append(f"| **Projected monthly cost @ 1,000 questions/day** | **{fmt_usd(agg['projected_monthly_usd_at_1000_per_day'])}** |")
    L.append(f"| Refusal rate / mean rewrites | {agg['refusal_rate']:.0%} / {agg['mean_retries']:.2f} |")

    L.append("\n## 3. Per node (sorted by cost)\n")
    L.append("| Node | LLM calls / question | Tokens in / out per question | Cost / question | % of spend | Time / question | % of time |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for x in nodes:
        L.append(f"| `{x['node']}` | {x['calls_per_q']:.2f} | {x['tokens_in_per_q']:,.0f} / {x['tokens_out_per_q']:,.0f} | "
                 f"{fmt_usd(x['cost_per_q'])} | {x['pct_cost']:.1f}% | {x['ms_per_q'] / 1000:.2f} s | {x['pct_time']:.1f}% |")

    L.append("\n## 4. Node-path distribution\n")
    L.append("| Path | Count | % |\n|---|---:|---:|")
    for label, c in sorted(paths.items(), key=lambda kv: -kv[1]):
        L.append(f"| {label} | {c} | {100 * c / len(ok):.0f}% |")
    L.append("")
    if fired == 0:
        L.append("**THE REWRITE LOOP NEVER FIRED (0 of %d).** The doc grader never rejects a retrieval and "
                 "the fact-check never rejects an answer: the self-correction machinery is decorative on this set."
                 % len(ok))
    else:
        L.append(f"Rewrite loop fired on **{fired} of {len(ok)}** questions ({100 * fired / len(ok):.0f}%), "
                 f"{sum(triggers.values())} rewrites in total. What triggered them:")
        for t, c in triggers.most_common():
            L.append(f"- {t}: {c}")

    agg.update(nodes=nodes, paths=dict(paths), rewrite_triggers=dict(triggers), rewrite_fired=fired)
    return "\n".join(L), agg


# ---------------------------------------------------------------------------
def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--n", type=int, help="only the first N questions")
    p.add_argument("--out", type=Path, help="write the report (markdown) here")
    p.add_argument("--json", type=Path, help="write the summary + every request record (JSON) here")
    args = p.parse_args(argv)

    from app.main import default_backend_factory
    from app.service import ChatService

    settings = get_settings()
    questions = load_questions(args.n)
    load_capstone().setup_logging()
    print(f"Loading index and models ({settings.summary()}) ...", flush=True)
    backend = default_backend_factory()                 # the API's own startup path
    observer = CollectingObserver()
    service = ChatService(backend, observer)
    from common.access import Directory
    directory = Directory(settings.user_directory)

    print("Warm-up (not counted) ...", flush=True)
    service.ask("How many sick days do I get?", f"warmup-{uuid.uuid4()}", user=directory.lookup(DEFAULT_USER),
                trace_id=str(uuid.uuid4()), request_id="cost-report-warmup")
    observer.records.clear()

    t0 = time.perf_counter()
    for i, q in enumerate(questions, 1):
        rid = f"cost-report-{i:02d}"
        try:
            service.ask(q["question"], f"cost-{uuid.uuid4()}", user=directory.lookup(q["user_id"]),
                        trace_id=str(uuid.uuid4()), request_id=rid)
        except Exception as exc:                         # a failed question degrades the report, not kills it
            print(f"  {i:2d}. ERROR {type(exc).__name__}: {exc}", flush=True)
        rec = observer.records[-1]
        rec.update(question=q["question"], out_of_scope=q["out_of_scope"])
        if rec["status"] == "ok":
            print(f"  {i:2d}. {rec['latency_ms'] / 1000:5.1f}s {rec['llm_calls']:3d} calls "
                  f"{rec['tokens_in'] + rec['tokens_out']:6,d} tok  {q['question']}", flush=True)
    wall = time.perf_counter() - t0

    report, summary = build_report(observer.records, settings, wall)
    print("\n" + report)
    total = summary["total_cost_usd"]
    print(f"\nThis run: {summary['n']} questions, {sum(r['llm_calls'] for r in observer.records)} LLM calls, "
          f"{sum(r['tokens_in'] + r['tokens_out'] for r in observer.records):,} tokens, "
          f"estimated {fmt_usd(total)} at the configured price ({settings.llm_label} actually ran it).")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(f"# Cost report — {time.strftime('%Y-%m-%d %H:%M')}\n\n{report}\n", encoding="utf-8")
        print(f"wrote {args.out}")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({"summary": summary, "requests": observer.records}, indent=1,
                                        default=str), encoding="utf-8")
        print(f"wrote {args.json}")


if __name__ == "__main__":
    main()
