"""
The eval suite (Week 2 Task 7, extended in Week 3 Task 2): every example through the REAL
pipeline, scored, split by category, written to a results JSON. `make eval` is the entry point.

    make eval                    # Week 3 dataset v3, DEV split, full pipeline + judge
    make eval-retrieval          # dev, retrieval only: no LLM, seconds, ~$0
    make eval-test               # the frozen TEST split: run only to confirm a decision (committed)

    python week2/task_07_eval_gate/scripts/run_eval.py --split dev [--retrieval-only] [--ids 5 s07 n12]
    python .../run_eval.py --dataset week2/task_07_eval_gate/eval_dataset.jsonl --out x.json   # Week 2 set

Week 3 additions (Task 2):
* Dataset v3 (week3/eval/eval_v3.jsonl, `EVAL_DATASET`) with a committed dev/test split
  (`--split`, `EVAL_SPLIT`, default dev) and the 15 Week 3 categories. The Week 2 format still
  loads (it has no split: all examples run).
* `--retrieval-only`: document-level recall@1/3/5/10 and MRR straight from the retriever
  (week3/task_02_eval_at_scale/retrieval_metrics.py), no generation, no judge.
* The judge must be a DIFFERENT model from the generator (`JUDGE_MODEL`, or `--judge-model`).
  The pipeline runs over every example first, then the judge scores them all, so a 6 GB GPU
  swaps models twice per run instead of twice per example.
* The deterministic scorer (week3/eval/scoring.py) runs on every Week 3 example.
* Each run is written to week3/eval/runs/<split>/<git sha>_<split>_<mode>_<time>.json
  (`EVAL_RESULTS_DIR`). Dev runs are git-ignored; TEST runs are committed, so a reviewer can
  count how often test was used.

Unchanged from Week 2: no answer cache (examples go through the capstone Assistant directly;
`--no-cache` is accepted and is a no-op), follow-ups get their earlier turns injected into the
session, cost comes from the API's per-node telemetry, and LangSmith publishing (optional) reuses
the verdicts computed here.
"""

from __future__ import annotations

import argparse
import csv
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
W2_DATASET = TASK_DIR / "eval_dataset.jsonl"
DATASET = REPO_ROOT / os.getenv("EVAL_DATASET", "week3/eval/eval_v3.jsonl")
RUNS_DIR = REPO_ROOT / os.getenv("EVAL_RESULTS_DIR", "week3/eval/runs")
W3_TASK2 = REPO_ROOT / "week3" / "task_02_eval_at_scale"
METRICS = ("correctness", "groundedness", "retrieval_hit")           # Week 2 examples
W3_METRICS = ("correctness", "groundedness", "deterministic")         # Week 3 examples
CATEGORIES = ("factual", "multi-hop", "multi-part", "refusal", "follow-up", "keyword")
W3_CATEGORIES = ("factual", "table", "keyword", "version", "conflict", "draft", "multi_hop", "multi_part",
                 "ambiguous", "long_doc", "cross_lingual", "follow_up", "personalized", "access", "out_of_scope")
RETRIEVAL_KS = (1, 3, 5, 10)
for p in (REPO_ROOT, REPO_ROOT / "week3", W3_TASK2):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


# ---------------------------------------------------------------------------
# Dataset: Week 3 (v3) and Week 2 formats
# ---------------------------------------------------------------------------
def load_dataset(path: Path = DATASET) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def dataset_version(path: Path = DATASET) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


def is_w3(ex: dict) -> bool:
    return "reference_answer" in ex


def history_pairs(history: list) -> list[tuple[str, str]]:
    """Week 2: [[user, assistant], ...]. Week 3: [{"role": ..., "content": ...}, ...]."""
    if not history or not isinstance(history[0], dict):
        return [tuple(t) for t in history or []]
    pairs, user = [], None
    for turn in history:
        if turn["role"] == "user":
            user = turn["content"]
        elif user is not None:
            pairs.append((user, turn["content"]))
            user = None
    return pairs


def normalise(ex: dict) -> dict:
    """The fields the runner uses, for either format."""
    if not is_w3(ex):
        return {**ex, "history": history_pairs(ex.get("history")), "metrics": METRICS}
    return {**ex, "reference": ex["reference_answer"], "sources": [Path(g).name for g in ex["gold_docs"]],
            "facts": [], "history": history_pairs(ex.get("history")), "metrics": W3_METRICS}


def judge_question(ex: dict) -> str:
    """What the correctness judge sees as 'the question': follow-ups need their history."""
    pairs = history_pairs(ex.get("history"))
    if not pairs:
        return ex["question"]
    convo = " ".join(f"User asked: {u!r}; assistant answered: {a!r}." for u, a in pairs)
    return f"(Earlier in the conversation: {convo}) Follow-up question: {ex['question']}"


# ---------------------------------------------------------------------------
# Full pipeline: run, then judge
# ---------------------------------------------------------------------------
def _files(ids: list[str]) -> list[str]:
    """Chunk ids ("policies/hr/x.pdf::3") -> documents, in retrieval order."""
    out = []
    for i in ids or []:
        doc = i.split("::")[0].split("#")[0]
        if doc not in out:
            out.append(doc)
    return out


def groups_for(ex: dict, settings) -> frozenset:
    """Week 3 Task 6: the example's user_id, looked up in the directory like the API does. An example
    without one (the Week 2 set) runs as the public scope. An unknown user_id is a dataset bug: raise."""
    from common.access import PUBLIC, Directory
    if not ex.get("user_id"):
        return PUBLIC
    return Directory(settings.user_directory).lookup(ex["user_id"]).groups


def run_pipeline(assistant, ex: dict, settings, run_tag: str) -> dict:
    """Run one example through the graph. Never raises: an error is recorded on the row."""
    from app.observability import RunTelemetry

    ex = normalise(ex)
    sid = f"eval-{run_tag}-{ex['id']}-{uuid.uuid4().hex[:6]}"
    if ex["history"]:
        assistant.sessions[sid] = list(ex["history"])
    telemetry = RunTelemetry()
    t0 = time.perf_counter()
    row = {"id": ex["id"], "category": ex["category"], "question": ex["question"]}
    if is_w3(ex):
        row.update(user_id=ex.get("user_id"), split=ex.get("split"), gold_docs=ex["gold_docs"])
    try:
        final = None
        for ev in assistant.stream(ex["question"], sid, callbacks=[telemetry], groups=groups_for(ex, settings),
                                   metadata={"eval_example_id": ex["id"], "eval_category": ex["category"],
                                             "eval_run": run_tag}):
            if ev["event"] == "final":
                final = ev
        latency = time.perf_counter() - t0
        last = final["attempts"][-1] if final["attempts"] else {}
        usage = telemetry.totals()
        row.update(
            answer=final["answer"], standalone=final["standalone"], node_path=final["path"],
            retries=final["retries"], sources=final["sources"],
            refused=assistant_is_refusal(final["answer"]), latency_s=round(latency, 2),
            llm_calls=usage["llm_calls"], tokens_in=usage["tokens_in"], tokens_out=usage["tokens_out"],
            cost_usd=round(settings.cost_usd(usage["tokens_in"], usage["tokens_out"]), 6),
            retrieved_docs=_files(final.get("retrieved_ids")), kept_docs=_files(final.get("kept_ids")),
            restricted_used=bool(final.get("restricted_used")),
            rejected_attempts=[a["answer"][:200] for a in final["attempts"] if not a["ok"]],
            _outputs={"answer": final["answer"], "context": final["context"], "retrieved": final["retrieved"],
                      "kept": final["kept"], "sources": final["sources"], "path": " -> ".join(final["path"]),
                      "retries": final["retries"],
                      "last_rejected_answer": "" if (last.get("ok") or not last) else last["answer"],
                      "last_rejected_notes": "" if (last.get("ok") or not last) else last["notes"]})
    except Exception as exc:
        row.update(error=f"{type(exc).__name__}: {exc}"[:400], latency_s=round(time.perf_counter() - t0, 2),
                   llm_calls=0, tokens_in=0, tokens_out=0, cost_usd=0.0, refused=False)
    return row


def judge_row(row: dict, evaluators, ex: dict) -> dict:
    """Score a run row in place: the judges, plus the deterministic scorer for Week 3 examples."""
    ex = normalise(ex)
    metrics = ex["metrics"]
    outputs = row.pop("_outputs", None)
    if outputs is None:                                   # the pipeline failed: every metric is a 0
        row.update(scores={k: 0 for k in metrics}, comments={k: "pipeline error" for k in metrics})
        return row
    reference = {"answer": ex["reference"], "expect_refusal": ex["expect_refusal"],
                 "source": (ex["sources"] or [None])[0], "facts": ex["facts"], "fact": (ex["facts"] or [""])[0]}
    inputs = {"question": judge_question(ex)}
    correctness, groundedness, retrieval_hit = evaluators
    calls = {"correctness": lambda: correctness(inputs, outputs, reference),
             "groundedness": lambda: groundedness(inputs, outputs),
             "retrieval_hit": lambda: retrieval_hit(outputs, reference)}
    verdicts = {}
    for key in metrics:
        if key == "deterministic":
            from eval.scoring import check_answer       # week3/eval/scoring.py
            res = check_answer(ex, row.get("answer", ""))
            verdicts[key] = {"score": int(res["passed"]), "comment": "; ".join(res["reasons"])[:400]}
            continue
        try:
            res = calls[key]()
            verdicts[key] = {"score": int(res["score"]), "comment": (res.get("comment") or "")[:400]}
        except Exception as exc:                         # the judge gave no verdict, twice
            verdicts[key] = {"score": 0, "comment": f"evaluator error: {type(exc).__name__}: {exc}"[:400]}
    row.update(scores={k: v["score"] for k, v in verdicts.items()},
               comments={k: v["comment"] for k, v in verdicts.items()})
    return row


def score_example(assistant, evaluators, ex: dict, settings, run_tag: str) -> dict:
    """Run + judge one example (Week 2's one-step API, kept for callers and tests)."""
    return judge_row(run_pipeline(assistant, ex, settings, run_tag), evaluators, ex)


def assistant_is_refusal(answer: str) -> bool:
    from app.capstone import load_capstone
    return load_capstone().is_refusal(answer)


# ---------------------------------------------------------------------------
# Retrieval only
# ---------------------------------------------------------------------------
def corpus_paths(data_dir: Path) -> dict[str, str]:
    """file name -> corpus path, so chunks indexed without a `path` (old indexes) still score."""
    meta = Path(data_dir) / "_metadata.csv"
    if not meta.exists():
        return {}
    with open(meta, encoding="utf-8") as f:
        return {Path(r["path"]).name: r["path"] for r in csv.DictReader(f)}


def retrieval_query(ex: dict) -> str:
    """The query sent to the retriever. Follow-ups are prefixed with the earlier user turns: a
    deterministic stand-in for the `contextualize` LLM call, which this mode doesn't make."""
    earlier = [u for u, _ in history_pairs(ex.get("history"))]
    return " ".join(earlier + [ex["question"]])


def run_retrieval(examples: list[dict], settings, depth: int = max(RETRIEVAL_KS)) -> dict:
    """recall@k / MRR straight from the retriever: no generation, no judge, no LLM call."""
    from app.capstone import load_capstone
    from common.utils import get_embeddings
    from retrieval_metrics import score_retrieval    # week3/task_02_eval_at_scale/retrieval_metrics.py

    cap = load_capstone()
    t0 = time.perf_counter()
    store, index_stats = cap.ingest(get_embeddings(), settings.data_dir)
    retriever, name = cap.build_retriever(store, k=depth)      # the production hybrid retriever, deeper
    load_s = time.perf_counter() - t0
    by_name = corpus_paths(settings.data_dir)
    timings, queries = [], []

    def retrieve(ex):
        # Week 3 Task 6: search as the example's user, exactly like the graph's retrieve node
        q = retrieval_query(ex)
        queries.append(q)
        scoped = retriever.for_scope(groups_for(ex, settings))
        t = time.perf_counter()
        docs = scoped.invoke(q)
        timings.append(time.perf_counter() - t)
        return [d.metadata.get("path") if "/" in (d.metadata.get("path") or "")
                else by_name.get(d.metadata.get("source", ""), d.metadata.get("source", "?")) for d in docs]

    t1 = time.perf_counter()
    scored = score_retrieval(examples, retrieve, ks=RETRIEVAL_KS)
    query_s = time.perf_counter() - t1
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        q_tokens = sum(len(enc.encode(q)) for q in queries)
    except Exception:
        q_tokens = None
    timings.sort()
    return {**scored, "retriever": f"{name}, depth {depth} per retriever", "load_s": round(load_s, 2),
            "index": {"chunks": index_stats.get("chunks"), "rebuilt": index_stats.get("rebuilt"),
                      "seconds": index_stats.get("seconds"), "embedded_chunks": index_stats.get("embedded_chunks")},
            "settings": {k: getattr(settings, k) for k in ("hybrid_bm25_weight", "source_prior", "reranker_model",
                                                          "rerank_top_n", "chunk_size", "chunk_overlap",
                                                          "chunk_context_header", "hf_embed_model",
                                                          "local_embeddings_backend")},
            "query_s": round(query_s, 2), "n_queries": len(queries),
            "latency_ms_p50": round(1000 * timings[len(timings) // 2], 1) if timings else None,
            "latency_ms_p95": round(1000 * timings[int(len(timings) * 0.95)], 1) if timings else None,
            "query_embedding_tokens": q_tokens}


# ---------------------------------------------------------------------------
# Aggregation and metadata
# ---------------------------------------------------------------------------
def aggregate(rows: list[dict]) -> dict:
    def mean(xs):
        return round(sum(xs) / len(xs), 4) if xs else None

    metrics = [m for m in (*W3_METRICS, "retrieval_hit") if any(m in r["scores"] for r in rows)]
    scores = {m: mean([r["scores"][m] for r in rows if m in r["scores"]]) for m in metrics}
    by_cat = defaultdict(list)
    for r in rows:
        by_cat[r["category"]].append(r)
    order = [c for c in (*W3_CATEGORIES, *CATEGORIES) if c in by_cat] + sorted(set(by_cat) - set(W3_CATEGORIES)
                                                                                - set(CATEGORIES))
    categories = {c: {"n": len(by_cat[c]), **{m: mean([r["scores"][m] for r in by_cat[c] if m in r["scores"]])
                                              for m in metrics}} for c in order}
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


def dataset_name(path: Path) -> str:
    if os.getenv("EVAL_DATASET_NAME"):
        return os.environ["EVAL_DATASET_NAME"]
    return "northwind-eval-v3" if Path(path).stem == "eval_v3" else "northwind-eval-v2"


def default_out(split: str, mode: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return RUNS_DIR / split / f"{git_sha()[:7]}_{split}_{mode}_{stamp}.json"


def publish(rows: list[dict], meta: dict, dataset: list[dict]) -> str | None:
    """Publish the verdicts computed above as a LangSmith experiment (no re-judging)."""
    try:
        from langsmith import Client, evaluate
    except ImportError:
        return None
    if not (os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")):
        return None
    from app.capstone import load_capstone

    client = Client()
    name = meta["dataset_name"]
    version = f"v:{meta['dataset_version']}"
    if client.has_dataset(dataset_name=name):
        if version not in (client.read_dataset(dataset_name=name).description or ""):
            client.delete_dataset(dataset_name=name)
    if not client.has_dataset(dataset_name=name):
        ds = client.create_dataset(name, description=f"Northwind eval gate, {len(dataset)} examples [{version}]")
        client.create_examples(
            dataset_id=ds.id,
            inputs=[{"id": e["id"], "question": e["question"], "history": e.get("history")} for e in dataset],
            outputs=[{"answer": e.get("reference_answer", e.get("reference")), "expect_refusal": e["expect_refusal"]}
                     for e in dataset],
            metadata=[{"category": e["category"], "split": e.get("split"), "added_in": e.get("added_in")}
                      for e in dataset])
    by_id = {r["id"]: r for r in rows}
    metrics = sorted({m for r in rows for m in r["scores"]})

    def target(inputs):
        r = by_id.get(inputs["id"], {})
        return {"answer": r.get("answer", ""), "path": " -> ".join(r.get("node_path", [])),
                "category": r.get("category"), "cost_usd": r.get("cost_usd")}

    def recorded(key):
        def evaluator(inputs, outputs):
            r = by_id.get(inputs["id"])
            if r is None:
                return {"key": key, "score": None, "comment": "not run"}
            return {"key": key, "score": r["scores"].get(key), "comment": r["comments"].get(key)}
        evaluator.__name__ = key
        return evaluator

    data = [ex for ex in client.list_examples(dataset_name=name) if ex.inputs.get("id") in set(by_id)]
    results = evaluate(target, data=data, evaluators=[recorded(m) for m in metrics],
                       experiment_prefix=os.getenv("EVAL_EXPERIMENT_PREFIX", "gate"), max_concurrency=4,
                       metadata={k: v for k, v in meta.items() if isinstance(v, (str, int, float))})
    return load_capstone()._experiment_url(results)


def make_judge(model: str, settings):
    from langchain_ollama import ChatOllama
    return ChatOllama(model=model, base_url=settings.ollama_base_url, temperature=0, reasoning=False)


# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dataset", type=Path, default=DATASET)
    p.add_argument("--split", choices=("dev", "test", "all"), default=os.getenv("EVAL_SPLIT", "dev"))
    p.add_argument("--retrieval-only", action="store_true", help="recall@k / MRR only: no generation, no judge")
    p.add_argument("--out", type=Path, help="results JSON (default: week3/eval/runs/<split>/<sha>_<split>_<mode>_<time>.json)")
    p.add_argument("--limit", type=int, help="only the first N examples")
    p.add_argument("--ids", nargs="*", help="only these example ids")
    p.add_argument("--judge-model", default=os.getenv("JUDGE_MODEL"),
                   help="Ollama model that judges (JUDGE_MODEL). Must differ from the generator.")
    p.add_argument("--no-publish", action="store_true", help="don't publish to LangSmith")
    p.add_argument("--no-cache", action="store_true", help="accepted for CI; the eval never uses the cache")
    args = p.parse_args(argv)

    from app.capstone import load_capstone
    from app.config import get_settings

    cap = load_capstone()
    cap.setup_logging()
    settings = get_settings()
    dataset = load_dataset(args.dataset)
    examples = [e for e in dataset
                if (args.split == "all" or "split" not in e or e["split"] == args.split)
                and (not args.ids or str(e["id"]) in args.ids)][: args.limit or None]
    mode = "retrieval" if args.retrieval_only else "full"
    out = args.out or default_out(args.split, mode)
    meta = {"date": datetime.now(timezone.utc).isoformat(timespec="seconds"), "git_sha": git_sha(),
            "dataset": str(Path(args.dataset).resolve().relative_to(REPO_ROOT)),
            "dataset_name": dataset_name(args.dataset), "dataset_version": dataset_version(args.dataset),
            "split": args.split, "mode": mode, "n": len(examples), "data_dir": str(settings.data_dir),
            "retriever_k": settings.retriever_k, "max_docs_to_grade": settings.max_docs_to_grade,
            "chunking": f"{settings.chunk_size}/{settings.chunk_overlap}",
            "embeddings": f"{settings.embedding_provider}/{settings.local_embeddings_backend}",
            "runner": f"{platform.system()} {platform.machine()} py{platform.python_version()}"
                      + (" (GitHub Actions)" if os.getenv("GITHUB_ACTIONS") else "")}
    t0 = time.perf_counter()

    if args.retrieval_only:
        print(f"Retrieval-only eval: {len(examples)} examples ({args.split}), dataset {meta['dataset_version']}",
              flush=True)
        r = run_retrieval(examples, settings)
        meta["wall_clock_s"] = round(time.perf_counter() - t0, 2)
        result = {"meta": meta, "retrieval": r}
        o = r["overall"]
        print(f"recall@1 {o['recall@1']:.3f}  @3 {o['recall@3']:.3f}  @5 {o['recall@5']:.3f}  "
              f"@10 {o['recall@10']:.3f}  MRR {o['mrr']:.3f}  ({o['n']} answerable examples)")
        print(f"{'category':14s} {'n':>3} {'R@1':>5} {'R@3':>5} {'R@5':>5} {'R@10':>5} {'MRR':>5}")
        for c in [c for c in W3_CATEGORIES if c in r["by_category"]]:
            v = r["by_category"][c]
            print(f"{c:14s} {v['n']:>3} {v['recall@1']:>5.2f} {v['recall@3']:>5.2f} {v['recall@5']:>5.2f} "
                  f"{v['recall@10']:>5.2f} {v['mrr']:>5.2f}")
        print(f"wall clock {meta['wall_clock_s']} s (index load {r['load_s']} s, {r['n_queries']} queries "
              f"{r['query_s']} s, p50 {r['latency_ms_p50']} ms), query embedding tokens {r['query_embedding_tokens']}")
    else:
        if not args.judge_model:
            sys.exit("JUDGE_MODEL is required (Week 3): the judge must be a different model from the generator.")
        if settings.llm_provider == "ollama" and args.judge_model == settings.ollama_model:
            sys.exit(f"JUDGE_MODEL={args.judge_model} is the generator itself; pick a different model.")
        backend = cap.Backend()                  # the real index, retriever, graph and model
        run_tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        meta.update(model=settings.llm_label, judge=f"ollama:{args.judge_model}")
        print(f"Eval: {len(examples)} examples ({args.split}), model {settings.llm_label}, judge {meta['judge']}, "
              f"dataset {meta['dataset_name']} {meta['dataset_version']}, {backend.n_chunks} chunks indexed", flush=True)
        rows = []
        for ex in examples:                      # phase 1: the generator answers everything
            r = run_pipeline(backend.assistant, ex, settings, run_tag)
            rows.append(r)
            print(f"  {r['id']:>4} {r['category']:13s} {r['latency_s']:5.1f}s  {r['question'][:60]}"
                  + (f"  ERROR {r['error']}" if r.get("error") else ""), flush=True)
        pipeline_s = time.perf_counter() - t0
        print(f"pipeline done in {pipeline_s:.0f} s; judging with {args.judge_model} ...", flush=True)
        evaluators = cap.make_evaluators(make_judge(args.judge_model, settings))
        by_id = {str(e["id"]): e for e in examples}
        for r in rows:                           # phase 2: the judge scores everything
            judge_row(r, evaluators, by_id[str(r["id"])])
        meta.update(wall_clock_s=round(time.perf_counter() - t0, 1), pipeline_s=round(pipeline_s, 1))
        result = {"meta": meta, **aggregate(rows), "examples": rows}
        if not args.no_publish:
            try:
                result["meta"]["experiment_url"] = publish(rows, meta, examples)
            except Exception as exc:             # publishing is a nice-to-have, never the gate
                print(f"(LangSmith publish skipped: {type(exc).__name__}: {exc})", flush=True)
        sc = result["scores"]
        print("\n" + "  ".join(f"{k} {v:.3f}" for k, v in sc.items()) + f"   ({len(rows)} examples, "
              f"{meta['wall_clock_s']:.0f} s)")
        metrics = list(sc)
        print(f"{'category':14s} {'n':>3} " + " ".join(f"{m[:8]:>8}" for m in metrics))
        for c, v in result["by_category"].items():
            print(f"{c:14s} {v['n']:>3} " + " ".join(f"{v[m]:>8.2f}" for m in metrics))

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
