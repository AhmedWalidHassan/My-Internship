"""
Task 2 — retrieval metrics skeleton.

Implemented in place (Week 3 Task 2); the eval runner imports it from here
(week2/task_07_eval_gate/scripts/run_eval.py --retrieval-only).

These are standard definitions, given here so that "recall@5" means the same thing
in your RESULTS.md as it does in every paper and blog post you'll read. The
harness around them is yours.

Everything here is DOCUMENT-level: a retrieved chunk counts as a hit if it comes
from one of the example's gold_docs. Chunk-level scoring would need gold spans,
which the dataset doesn't have.
"""

from __future__ import annotations

from statistics import mean


def doc_ranking(retrieved_paths: list[str]) -> list[str]:
    """Collapse a ranked list of chunk source paths into a ranked list of DOCUMENTS.

    The retriever returns chunks, and several chunks can come from one document.
    Keep the first occurrence of each document, in order:

        ["a.pdf", "a.pdf", "b.md", "a.pdf", "c.txt"]  ->  ["a.pdf", "b.md", "c.txt"]

    Without this, a document that fills the top 4 slots with its own chunks makes
    recall@4 look like a single result.
    """
    seen, ranked = set(), []
    for path in retrieved_paths:
        if path not in seen:
            seen.add(path)
            ranked.append(path)
    return ranked


def recall_at_k(ranked_docs: list[str], gold_docs: list[str], k: int) -> float:
    """1.0 if ANY gold document is in the top k documents, else 0.0.

    (This is "hit rate@k", which is what most RAG evals call recall@k when an
    example usually has one gold document.)

    """
    gold = set(gold_docs)
    return 1.0 if any(d in gold for d in ranked_docs[:k]) else 0.0


def reciprocal_rank(ranked_docs: list[str], gold_docs: list[str]) -> float:
    """1 / (rank of the first gold document), with ranks starting at 1. 0.0 if none appears.

    """
    gold = set(gold_docs)
    for rank, d in enumerate(ranked_docs, start=1):
        if d in gold:
            return 1.0 / rank
    return 0.0


def score_retrieval(examples: list[dict], retrieve, ks=(1, 3, 5, 10)) -> dict:
    """Score a retriever over examples. `retrieve(example) -> list[str]` returns
    ranked chunk source paths (relative to corpus/, matching gold_docs).

    Skip examples with no gold_docs (refusals, access denials) — they have nothing
    to retrieve. Score those on the generation side instead.

    Returns {"overall": {...}, "by_category": {cat: {...}}, "per_example": {id: {...}}}; each
    aggregate has "n", "recall@1", "recall@3", ..., "mrr".

    Important: pass each example's user_id through to `retrieve`. Once Task 6 is
    in place, a retriever that ignores the user will score HIGHER on recall —
    because it's retrieving documents the user isn't allowed to see. Recall that
    comes from a leak doesn't count.
    """
    per_example, groups = {}, {}
    for ex in examples:
        if not ex.get("gold_docs"):
            continue
        ranked = doc_ranking(retrieve(ex))
        row = {f"recall@{k}": recall_at_k(ranked, ex["gold_docs"], k) for k in ks}
        row["mrr"] = reciprocal_rank(ranked, ex["gold_docs"])
        row["ranked_docs"] = ranked[:max(ks)]
        per_example[ex["id"]] = row
        groups.setdefault(ex["category"], []).append(row)

    def agg(rows):
        out = {"n": len(rows)}
        for key in [f"recall@{k}" for k in ks] + ["mrr"]:
            out[key] = round(mean(r[key] for r in rows), 4) if rows else None
        return out

    return {"overall": agg(list(per_example.values())),
            "by_category": {c: agg(rows) for c, rows in groups.items()},
            "per_example": per_example}


# --- self-checks: python retrieval_metrics.py -------------------------------------
if __name__ == "__main__":
    assert doc_ranking(["a", "a", "b", "a", "c"]) == ["a", "b", "c"]
    assert recall_at_k(["x", "a", "y"], ["a"], 1) == 0.0
    assert recall_at_k(["x", "a", "y"], ["a"], 2) == 1.0
    assert recall_at_k(["x", "y"], ["a", "y"], 2) == 1.0
    assert reciprocal_rank(["x", "a", "y"], ["a"]) == 0.5
    assert reciprocal_rank(["x", "y"], ["a"]) == 0.0
    assert abs(mean([reciprocal_rank(["a"], ["a"]), reciprocal_rank(["x", "a"], ["a"])]) - 0.75) < 1e-9
    print("retrieval_metrics: all self-checks passed")
