"""
Task 1 — run the Week 3 seed set (40) through the Week 2 system and score it by category.

Not a second eval runner: every example goes through Week 2's own
`week2/task_07_eval_gate/scripts/run_eval.py::score_example` (the graph with no answer
cache, the Week 2 correctness + groundedness judges, per-node cost telemetry). This file
only adapts the Week 3 example format to it and adds two things Week 2 didn't have:

  * the deterministic scorer, week3/eval/scoring.py::check_answer (the holdout's rules);
  * a document-level retrieval signal: was a gold document indexed at all, was it in the
    raw search results, and did it survive the relevance grader. That's the evidence for
    the PR question "retrieval or generation?" until Task 2 builds proper metrics.

The corpus is whatever DATA_DIR points at (the only thing Task 1 is allowed to change):

    # W2 as shipped: the unchanged loader on week3/corpus (indexes 1 file)
    DATA_DIR=$PWD/week3/corpus INDEX_PATH=... python .../run_seed_eval.py --label literal --out ...
    # W2 loader fed every .md/.txt (see corpus_view.py)
    DATA_DIR=$(python .../corpus_view.py) INDEX_PATH=... python .../run_seed_eval.py --label recursive ...

`user_id` is ignored (Week 2 has no notion of a user), so `access` and `personalized`
examples are asked anonymously: that is the baseline Task 6 fixes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
TASK_DIR = Path(__file__).resolve().parents[1]
SEED = REPO_ROOT / "week3" / "eval" / "seed_eval.jsonl"
for p in (REPO_ROOT, REPO_ROOT / "week3", REPO_ROOT / "week2" / "task_07_eval_gate" / "scripts"):
    sys.path.insert(0, str(p))

import run_eval as w2  # noqa: E402  (Week 2's eval runner: score_example, git_sha)
from eval.scoring import check_answer, load_examples  # noqa: E402  (week3/eval/scoring.py)

CATEGORIES = ("factual", "table", "keyword", "version", "conflict", "draft", "multi_hop", "multi_part",
              "ambiguous", "long_doc", "cross_lingual", "follow_up", "personalized", "access", "out_of_scope")


def history_pairs(history: list[dict]) -> list[tuple[str, str]]:
    """[{"role": "user", ...}, {"role": "assistant", ...}, ...] -> [(user, assistant), ...]"""
    pairs, user = [], None
    for turn in history:
        if turn["role"] == "user":
            user = turn["content"]
        elif user is not None:
            pairs.append((user, turn["content"]))
            user = None
    return pairs


def to_w2(ex: dict) -> dict:
    """The Week 3 seed format, in the shape Week 2's score_example expects."""
    return {"id": ex["id"], "category": ex["category"], "question": ex["question"],
            "reference": ex["reference_answer"], "expect_refusal": ex["expect_refusal"],
            "sources": [Path(g).name for g in ex["gold_docs"]], "facts": [],
            "history": history_pairs(ex["history"])}


class Recorder:
    """Passes through to the Assistant and keeps the last `final` event (chunk ids, path)."""

    def __init__(self, assistant):
        self.assistant = assistant
        self.sessions = assistant.sessions
        self.last = None

    def stream(self, *args, **kwargs):
        self.last = None
        for ev in self.assistant.stream(*args, **kwargs):
            if ev["event"] == "final":
                self.last = ev
            yield ev


def _files(ids: list[str]) -> set[str]:
    return {i.split("::")[0].split("#")[0] for i in ids or []}


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 4) if xs else None


def summarise(rows: list[dict]) -> dict:
    by = defaultdict(list)
    for r in rows:
        by[r["category"]].append(r)

    def block(rs):
        answerable = [r for r in rs if r["gold_docs"]]
        return {"n": len(rs),
                "deterministic": mean([float(r["deterministic"]["passed"]) for r in rs]),
                "correctness": mean([r["scores"]["correctness"] for r in rs]),
                "groundedness": mean([r["scores"]["groundedness"] for r in rs]),
                "refused": mean([float(r.get("refused", False)) for r in rs]),
                "gold_indexed": mean([float(r["gold_indexed"]) for r in answerable]),
                "gold_retrieved": mean([float(r["gold_retrieved"]) for r in answerable]),
                "gold_kept": mean([float(r["gold_kept"]) for r in answerable]),
                "mean_llm_calls": mean([r.get("llm_calls") for r in rs]),
                "mean_latency_s": mean([r.get("latency_s") for r in rs])}

    return {"all": block(rows), "by_category": {c: block(by[c]) for c in CATEGORIES if by.get(c)}}


def fmt(x, pct=False):
    if x is None:
        return "–"
    return f"{x:.0%}" if pct else f"{x:.2f}"


def markdown(result: dict) -> str:
    m, s = result["meta"], result["summary"]
    L = [f"# Seed eval — {m['label']}", "",
         f"- date {m['date']}, git `{m['git_sha'][:7]}`, dataset `{m['dataset_version']}` ({m['n']} examples)",
         f"- corpus `{m['data_dir']}`: **{m['indexed_files']} files, {m['indexed_chunks']} chunks indexed**",
         f"- model {m['model']}, judge {m['judge']}, wall clock {m['wall_clock_s']:.0f} s", "",
         "| Category | n | Deterministic pass | Correctness | Groundedness | Refused | Gold doc indexed | "
         "Gold doc retrieved | Gold doc kept by grader |",
         "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for c, v in list(s["by_category"].items()) + [("**All**", s["all"])]:
        L.append(f"| {c} | {v['n']} | {fmt(v['deterministic'], True)} | {fmt(v['correctness'])} | "
                 f"{fmt(v['groundedness'])} | {fmt(v['refused'], True)} | {fmt(v['gold_indexed'], True)} | "
                 f"{fmt(v['gold_retrieved'], True)} | {fmt(v['gold_kept'], True)} |")
    L += ["", "## Per example", "",
          "| id | category | det | C | G | gold idx/ret/kept | path | answer (start) | det. reasons |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in result["examples"]:
        path = " → ".join(n.replace("_question", "").replace("grade_", "g_") for n in r.get("node_path", []))
        ans = (r.get("answer") or r.get("error") or "").replace("\n", " ").replace("|", "/")[:90]
        flags = "/".join("✓" if r[k] else "✗" for k in ("gold_indexed", "gold_retrieved", "gold_kept")) \
            if r["gold_docs"] else "–"
        L.append(f"| {r['id']} | {r['category']} | {'✓' if r['deterministic']['passed'] else '✗'} | "
                 f"{r['scores']['correctness']} | {r['scores']['groundedness']} | {flags} | {path} | {ans} | "
                 f"{'; '.join(r['deterministic']['reasons'])} |")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", type=Path, default=SEED)
    ap.add_argument("--label", required=True, help="e.g. literal / recursive")
    ap.add_argument("--out", type=Path, required=True, help="results JSON")
    ap.add_argument("--md", type=Path, help="markdown report (default: --out with .md)")
    ap.add_argument("--ids", nargs="*", help="only these example ids")
    args = ap.parse_args(argv)

    from app.capstone import load_capstone
    from app.config import get_settings

    cap = load_capstone()
    cap.setup_logging()
    settings = get_settings()
    examples = [e for e in load_examples(args.dataset) if not args.ids or e["id"] in args.ids]

    backend = cap.Backend()                                  # the real index, retriever, graph and model
    indexed = set(backend.files)
    evaluators = cap.make_evaluators(backend.llm)            # Week 2 judges: the generator judges itself
    recorder = Recorder(backend.assistant)
    run_tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    print(f"Seed eval [{args.label}]: {len(examples)} examples, {len(indexed)} files / {backend.n_chunks} "
          f"chunks indexed from {settings.data_dir}, model {settings.llm_label}", flush=True)

    rows, t0 = [], time.perf_counter()
    for ex in examples:
        row = w2.score_example(recorder, evaluators, to_w2(ex), settings, run_tag)
        final = recorder.last or {}
        gold = [Path(g).name for g in ex["gold_docs"]]
        retrieved, kept = _files(final.get("retrieved_ids")), _files(final.get("kept_ids"))
        row.update(
            user_id=ex["user_id"], gold_docs=ex["gold_docs"],
            deterministic=check_answer(ex, row.get("answer", "")),
            gold_indexed=any(g in indexed for g in gold),
            gold_retrieved=any(g in retrieved for g in gold),
            gold_kept=any(g in kept for g in gold),
            retrieved_files=sorted(retrieved), kept_files=sorted(kept))
        rows.append(row)
        print(f"  {ex['id']:>4} {ex['category']:13s} det {'✓' if row['deterministic']['passed'] else '✗'} "
              f"C{row['scores']['correctness']} G{row['scores']['groundedness']} "
              f"gold idx/ret/kept {int(row['gold_indexed'])}{int(row['gold_retrieved'])}{int(row['gold_kept'])} "
              f"{row['latency_s']:5.1f}s  {(row.get('answer') or row.get('error', ''))[:70]!r}", flush=True)
    wall = time.perf_counter() - t0

    result = {
        "meta": {"label": args.label, "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "git_sha": w2.git_sha(), "dataset": str(args.dataset.relative_to(REPO_ROOT)),
                 "dataset_version": hashlib.sha256(args.dataset.read_bytes()).hexdigest()[:12],
                 "n": len(rows), "data_dir": str(settings.data_dir), "indexed_files": len(indexed),
                 "indexed_chunks": backend.n_chunks, "model": settings.llm_label,
                 "judge": f"{settings.llm_label} (same model as the generator: the Week 2 judges)",
                 "retriever_k": settings.retriever_k, "max_docs_to_grade": settings.max_docs_to_grade,
                 "chunking": f"{settings.chunk_size}/{settings.chunk_overlap}", "wall_clock_s": round(wall, 1),
                 "cost": {"mean_cost_usd": mean([r["cost_usd"] for r in rows]),
                          "mean_llm_calls": mean([r["llm_calls"] for r in rows]),
                          "mean_latency_s": mean([r["latency_s"] for r in rows])}},
        "summary": summarise(rows),
        "examples": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    md = args.md or args.out.with_suffix(".md")
    md.write_text(markdown(result), encoding="utf-8")
    a = result["summary"]["all"]
    print(f"\n[{args.label}] deterministic {a['deterministic']:.0%}  correctness {a['correctness']:.2f}  "
          f"groundedness {a['groundedness']:.2f}  ({len(rows)} examples, {wall:.0f} s)\nwrote {args.out} and {md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
