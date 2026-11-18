"""
Task 7 — run the eval suite: every example through the REAL pipeline, scored by the
capstone's evaluators, split by category, written to eval_results.json.

    python week2/task_07_eval_gate/scripts/run_eval.py --out eval_results.json
    python .../run_eval.py --limit 5 --judge-model gemma3:4b      # judge with a different model
    python .../run_eval.py --ids 29 30 31                          # a few examples

* No cache, by construction: examples go through the capstone Assistant (the graph)
  directly, never through the API's answer cache (Task 6). `--no-cache` is accepted for
  the CI skeleton's command line and is a no-op.
* Follow-up examples get their earlier turn injected into the session first.
* Cost per question comes from the same per-node telemetry as the API (Task 5).
* Scoring happens HERE (correctness + groundedness with the judge model, retrieval_hit
  without one). If LangSmith is configured, the same verdicts are then published as a
  LangSmith experiment (no re-judging), so the gate and LangSmith can't disagree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASK_DIR = HERE.parent
REPO_ROOT = TASK_DIR.parents[1]
DATASET = TASK_DIR / "eval_dataset.jsonl"
METRICS = ("correctness", "groundedness", "retrieval_hit")
CATEGORIES = ("factual", "multi-hop", "multi-part", "refusal", "follow-up", "keyword")
sys.path.insert(0, str(REPO_ROOT))


def load_dataset(path: Path = DATASET) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def dataset_version(path: Path = DATASET) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


def judge_question(ex: dict) -> str:
    """What the correctness judge sees as 'the question': follow-ups need their history."""
    if not ex.get("history"):
        return ex["question"]
    convo = " ".join(f"User asked: {u!r}; assistant answered: {a!r}." for u, a in ex["history"])
    return f"(Earlier in the conversation: {convo}) Follow-up question: {ex['question']}"


def score_example(assistant, evaluators, ex: dict, settings, run_tag: str) -> dict:
    """Run one example through the graph and score it. Never raises: an error is a 0."""
    from app.observability import RunTelemetry

    sid = f"eval-{run_tag}-{ex['id']}-{uuid.uuid4().hex[:6]}"
    if ex.get("history"):
        assistant.sessions[sid] = [tuple(t) for t in ex["history"]]
    telemetry = RunTelemetry()
    t0 = time.perf_counter()
    row = {"id": ex["id"], "category": ex["category"], "question": ex["question"]}
    try:
        final = None
        for ev in assistant.stream(ex["question"], sid, callbacks=[telemetry],
                                   metadata={"eval_example_id": ex["id"], "eval_category": ex["category"],
                                             "eval_run": run_tag}):
            if ev["event"] == "final":
                final = ev
        latency = time.perf_counter() - t0
        last = final["attempts"][-1] if final["attempts"] else {}
        outputs = {"answer": final["answer"], "context": final["context"], "retrieved": final["retrieved"],
                   "kept": final["kept"], "sources": final["sources"], "path": " -> ".join(final["path"]),
                   "retries": final["retries"],
                   "last_rejected_answer": "" if (last.get("ok") or not last) else last["answer"],
                   "last_rejected_notes": "" if (last.get("ok") or not last) else last["notes"]}
        reference = {"answer": ex["reference"], "expect_refusal": ex["expect_refusal"],
                     "source": (ex["sources"] or [None])[0], "facts": ex["facts"],
                     "fact": (ex["facts"] or [""])[0]}
        inputs = {"question": judge_question(ex)}
        correctness, groundedness, retrieval_hit = evaluators
        verdicts = {}
        for key, call in (("correctness", lambda: correctness(inputs, outputs, reference)),
                          ("groundedness", lambda: groundedness(inputs, outputs)),
                          ("retrieval_hit", lambda: retrieval_hit(outputs, reference))):
            try:
                res = call()
                verdicts[key] = {"score": int(res["score"]), "comment": (res.get("comment") or "")[:400]}
            except Exception as exc:                     # the judge gave no verdict, twice
                verdicts[key] = {"score": 0, "comment": f"evaluator error: {type(exc).__name__}: {exc}"[:400]}
        usage = telemetry.totals()
        row.update(
            answer=final["answer"], standalone=final["standalone"], node_path=final["path"],
            retries=final["retries"], sources=final["sources"],
            refused=assistant_is_refusal(final["answer"]), latency_s=round(latency, 2),
            llm_calls=usage["llm_calls"], tokens_in=usage["tokens_in"], tokens_out=usage["tokens_out"],
            cost_usd=round(settings.cost_usd(usage["tokens_in"], usage["tokens_out"]), 6),
            scores={k: v["score"] for k, v in verdicts.items()},
            comments={k: v["comment"] for k, v in verdicts.items()},
            rejected_attempts=[a["answer"][:200] for a in final["attempts"] if not a["ok"]])
    except Exception as exc:
        row.update(error=f"{type(exc).__name__}: {exc}"[:400], scores={k: 0 for k in METRICS},
                   comments={k: "pipeline error" for k in METRICS}, latency_s=round(time.perf_counter() - t0, 2),
                   llm_calls=0, tokens_in=0, tokens_out=0, cost_usd=0.0, refused=False)
    return row


def assistant_is_refusal(answer: str) -> bool:
    from app.capstone import load_capstone
    return load_capstone().is_refusal(answer)


def aggregate(rows: list[dict]) -> dict:
    def mean(xs):
        return round(sum(xs) / len(xs), 4) if xs else None

    scores = {m: mean([r["scores"][m] for r in rows]) for m in METRICS}
    by_cat = defaultdict(list)
    for r in rows:
        by_cat[r["category"]].append(r)
    categories = {c: {"n": len(by_cat[c]), **{m: mean([r["scores"][m] for r in by_cat[c]]) for m in METRICS}}
                  for c in CATEGORIES if by_cat.get(c)}
    cost = {"mean_cost_usd": round(sum(r["cost_usd"] for r in rows) / len(rows), 7) if rows else None,
            "mean_llm_calls": mean([r["llm_calls"] for r in rows]),
            "mean_latency_s": mean([r["latency_s"] for r in rows])}
    return {"scores": scores, "by_category": categories, "cost": cost}


def git_sha() -> str:
    if os.getenv("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True,
                              text=True).stdout.strip()
    except Exception:
        return "unknown"


def publish(rows: list[dict], meta: dict, dataset: list[dict]) -> str | None:
    """Publish the verdicts computed above as a LangSmith experiment (no re-judging)."""
    try:
        from langsmith import Client, evaluate
        from langsmith.utils import tracing_is_enabled  # noqa: F401
    except ImportError:
        return None
    if not (os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")):
        return None
    from app.capstone import load_capstone

    client = Client()
    name = os.getenv("EVAL_DATASET_NAME", "northwind-eval-v2")
    version = f"v:{meta['dataset_version']}"
    if client.has_dataset(dataset_name=name):
        if version not in (client.read_dataset(dataset_name=name).description or ""):
            client.delete_dataset(dataset_name=name)
    if not client.has_dataset(dataset_name=name):
        ds = client.create_dataset(name, description=f"Northwind eval gate, {len(dataset)} examples, "
                                                      f"6 categories [{version}]")
        client.create_examples(
            dataset_id=ds.id,
            inputs=[{"id": e["id"], "question": e["question"], "history": e["history"]} for e in dataset],
            outputs=[{"answer": e["reference"], "expect_refusal": e["expect_refusal"]} for e in dataset],
            metadata=[{"category": e["category"], "added_in": e["added_in"]} for e in dataset])
    by_id = {r["id"]: r for r in rows}

    def target(inputs):
        r = by_id.get(inputs["id"], {})
        return {"answer": r.get("answer", ""), "path": " -> ".join(r.get("node_path", [])),
                "category": r.get("category"), "cost_usd": r.get("cost_usd")}

    def recorded(key):
        def evaluator(inputs, outputs):
            r = by_id.get(inputs["id"])
            if r is None:
                return {"key": key, "score": None, "comment": "not run"}
            return {"key": key, "score": r["scores"][key], "comment": r["comments"][key]}
        evaluator.__name__ = key
        return evaluator

    ids = set(by_id)
    data = [ex for ex in client.list_examples(dataset_name=name) if ex.inputs.get("id") in ids]
    results = evaluate(target, data=data, evaluators=[recorded(m) for m in METRICS],
                       experiment_prefix=os.getenv("EVAL_EXPERIMENT_PREFIX", "gate"), max_concurrency=4,
                       metadata={k: v for k, v in meta.items() if isinstance(v, (str, int, float))})
    return load_capstone()._experiment_url(results)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dataset", type=Path, default=DATASET)
    p.add_argument("--out", type=Path, default=Path("eval_results.json"))
    p.add_argument("--limit", type=int, help="only the first N examples")
    p.add_argument("--ids", type=int, nargs="*", help="only these example ids")
    p.add_argument("--judge-model", help="an Ollama model to judge with (default: the generator itself)")
    p.add_argument("--no-publish", action="store_true", help="don't publish to LangSmith")
    p.add_argument("--no-cache", action="store_true", help="accepted for CI; the eval never uses the cache")
    args = p.parse_args(argv)

    from app.capstone import load_capstone
    from app.config import get_settings

    cap = load_capstone()
    cap.setup_logging()
    settings = get_settings()
    dataset = load_dataset(args.dataset)
    examples = [e for e in dataset if not args.ids or e["id"] in args.ids][: args.limit or None]

    backend = cap.Backend()                      # the real index, retriever, graph and model
    judge, judge_label = backend.llm, f"{settings.llm_label} (same model as the generator)"
    if args.judge_model:
        from langchain_ollama import ChatOllama
        judge = ChatOllama(model=args.judge_model, base_url=settings.ollama_base_url, temperature=0,
                           reasoning=False)
        judge_label = f"ollama:{args.judge_model}"
    evaluators = cap.make_evaluators(judge)
    run_tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    print(f"Eval: {len(examples)} examples, model {settings.llm_label}, judge {judge_label}, "
          f"dataset {dataset_version(args.dataset)}", flush=True)
    t0 = time.perf_counter()
    rows = []
    for ex in examples:
        r = score_example(backend.assistant, evaluators, ex, settings, run_tag)
        rows.append(r)
        s = r["scores"]
        print(f"  #{r['id']:>2} {r['category']:10s} C{s['correctness']} G{s['groundedness']} "
              f"R{s['retrieval_hit']} {r['latency_s']:5.1f}s  {r['question'][:60]}"
              + (f"  ERROR {r['error']}" if r.get("error") else ""), flush=True)
    wall = time.perf_counter() - t0

    meta = {"date": datetime.now(timezone.utc).isoformat(timespec="seconds"), "git_sha": git_sha(),
            "model": settings.llm_label, "judge": judge_label, "dataset_version": dataset_version(args.dataset),
            "n": len(rows), "retriever_k": settings.retriever_k, "max_docs_to_grade": settings.max_docs_to_grade,
            "embeddings": f"{settings.embedding_provider}/{settings.local_embeddings_backend}",
            "runner": f"{platform.system()} {platform.machine()} py{platform.python_version()}"
                      + (" (GitHub Actions)" if os.getenv("GITHUB_ACTIONS") else ""),
            "wall_clock_s": round(wall, 1)}
    result = {"meta": meta, **aggregate(rows), "examples": rows}
    if not args.no_publish:
        try:
            result["meta"]["experiment_url"] = publish(rows, meta, dataset)
        except Exception as exc:                     # publishing is a nice-to-have, never the gate
            print(f"(LangSmith publish skipped: {type(exc).__name__}: {exc})", flush=True)
    args.out.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")

    sc = result["scores"]
    print(f"\ncorrectness {sc['correctness']:.3f}  groundedness {sc['groundedness']:.3f}  "
          f"retrieval_hit {sc['retrieval_hit']:.3f}   ({len(rows)} examples, {wall:.0f} s)")
    print(f"{'category':12s} {'n':>3} {'correct':>8} {'grounded':>9}")
    for c, v in result["by_category"].items():
        print(f"{c:12s} {v['n']:>3} {v['correctness']:>8.2f} {v['groundedness']:>9.2f}")
    if result["meta"].get("experiment_url"):
        print("LangSmith:", result["meta"]["experiment_url"])
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
