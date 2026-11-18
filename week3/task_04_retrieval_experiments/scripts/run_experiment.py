"""
Task 4 — run ONE retrieval experiment: the baseline config plus one change, retrieval-only, and
compare it with the baseline overall and by category.

    python week3/task_04_retrieval_experiments/scripts/run_experiment.py baseline-1
    python .../run_experiment.py EXP-01 --set HYBRID_BM25_WEIGHT=0.3
    python .../run_experiment.py EXP-05 --set HF_EMBED_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
    python .../run_experiment.py EXP-06-cpu --set RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2 --cpu

Settings that change what gets indexed (chunking, the context header, the embedding model and its
backend) get their own index under indexes/ (git-ignored), so no experiment overwrites the
baseline index. Results: evidence/<ID>_<split>.json, plus a markdown block printed for EXPERIMENTS.md.
The baseline to compare with is evidence/baseline-1_dev.json (the first noise-floor run).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
REPO = HERE.parents[1]
INDEX_KEYS = {"CHUNK_SIZE", "CHUNK_OVERLAP", "CHUNK_CONTEXT_HEADER", "HF_EMBED_MODEL", "LOCAL_EMBEDDINGS_BACKEND"}
CATS = ("factual", "table", "keyword", "version", "conflict", "draft", "multi_hop", "multi_part", "ambiguous",
        "long_doc", "cross_lingual", "follow_up", "personalized", "access")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("id")
    ap.add_argument("--set", nargs="*", default=[], help="KEY=VALUE settings (the one change)")
    ap.add_argument("--split", default="dev")
    ap.add_argument("--cpu", action="store_true", help="hide the GPU (container-like latency)")
    ap.add_argument("--baseline", type=Path, default=HERE / "evidence" / "baseline-1_dev.json")
    args = ap.parse_args(argv)

    env = dict(os.environ, LANGSMITH_TRACING="false", LANGCHAIN_TRACING_V2="false", PYTHONWARNINGS="ignore")
    changes = dict(kv.split("=", 1) for kv in args.set)
    env.update(changes)
    if args.cpu:
        env["CUDA_VISIBLE_DEVICES"] = ""
    index_changes = {k: v for k, v in changes.items() if k in INDEX_KEYS}
    if index_changes:
        tag = hashlib.sha1(json.dumps(sorted(index_changes.items())).encode()).hexdigest()[:8]
        env["INDEX_PATH"] = str(HERE / "indexes" / f"faiss_index_{tag}")
        env["EMBEDDING_CACHE_PATH"] = str(HERE / "indexes" / "embedding_cache")
    out = HERE / "evidence" / f"{args.id}_{args.split}.json"
    t0 = time.perf_counter()
    r = subprocess.run([str(REPO / "week1" / ".venv" / "bin" / "python"),
                        str(REPO / "week2" / "task_07_eval_gate" / "scripts" / "run_eval.py"),
                        "--retrieval-only", "--split", args.split, "--out", str(out)],
                       env=env, cwd=REPO, capture_output=True, text=True)
    wall = time.perf_counter() - t0
    if r.returncode != 0:
        print(r.stdout[-2000:], r.stderr[-4000:])
        return r.returncode
    res = json.loads(out.read_text())
    res["experiment"] = {"id": args.id, "changes": changes, "cpu": args.cpu, "process_wall_s": round(wall, 1)}
    out.write_text(json.dumps(res, indent=1, ensure_ascii=False))
    now = res["retrieval"]
    base = json.loads(args.baseline.read_text())["retrieval"] if args.baseline.exists() else None

    def f(x):
        return "–" if x is None else f"{x:.3f}"

    print(f"### {args.id}  {changes or '(baseline config)'}{'  [CPU]' if args.cpu else ''}")
    print(f"retriever: {now['retriever']} | index: {now['index']} | wall {wall:.1f} s")
    print("| | Baseline | This | Delta |\n|---|---:|---:|---:|")
    for m in ("recall@1", "recall@3", "recall@5", "recall@10", "mrr"):
        b = base["overall"][m] if base else None
        print(f"| {m} | {f(b)} | {f(now['overall'][m])} | {'' if b is None else f'{now['overall'][m] - b:+.3f}'} |")
    bl = f"{base['latency_ms_p50']} / {base['latency_ms_p95']} ms" if base else "–"
    print(f"| latency p50 / p95 per query | {bl} | {now['latency_ms_p50']} / {now['latency_ms_p95']} ms | |")
    print("\n| Category | n | Baseline R@5 | This R@5 | Baseline MRR | This MRR |\n|---|---:|---:|---:|---:|---:|")
    for c in CATS:
        if c in now["by_category"]:
            x, y = (base["by_category"][c] if base else {}), now["by_category"][c]
            print(f"| {c} | {y['n']} | {f(x.get('recall@5'))} | {f(y['recall@5'])} | {f(x.get('mrr'))} | {f(y['mrr'])} |")
    if base:
        changed = [(k, base["per_example"][k]["recall@5"], v["recall@5"]) for k, v in now["per_example"].items()
                   if v["recall@5"] != base["per_example"][k]["recall@5"]]
        print("\nexamples whose recall@5 changed:", changed or "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
