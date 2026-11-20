"""
The production retriever, with every Week 3 Task 4 lever as a setting (so an experiment is a config
diff, not a code change):

  HYBRID_BM25_WEIGHT  share of BM25 in the fusion (0 = dense only, 1 = BM25 only; default 0.5)
  SOURCE_PRIOR        e.g. "drive/meetings:0.5,intranet:0.5": multiply a chunk's fused score by a
                      factor chosen by its path prefix or source system (default: none)
  RERANKER_MODEL      a cross-encoder (sentence-transformers) that re-scores the top RERANK_TOP_N
                      fused candidates against the query (default: none)

`HybridRetriever` is weighted reciprocal-rank fusion, the same formula and tie order as LangChain's
EnsembleRetriever (score += weight / (rank + 60), documents identified by their text, the BM25 list
first). With the defaults it returns exactly the Week 2 rankings: checked on all 60 dev questions,
week3/task_04_retrieval_experiments/evidence/fusion_equivalence.json.
"""

from __future__ import annotations

import time
from typing import Any

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

RRF_C = 60


def parse_prior(spec: str | None) -> list[tuple[str, float]]:
    """'meetings/:0.5,intranet:0.5' -> [('meetings/', 0.5), ('intranet', 0.5)]."""
    out = []
    for part in (spec or "").split(","):
        if ":" in part:
            key, val = part.rsplit(":", 1)
            out.append((key.strip(), float(val)))
    return out


def prior_factor(doc: Document, prior: list[tuple[str, float]]) -> float:
    path = doc.metadata.get("path", "")
    system = doc.metadata.get("source_system", "")
    for key, factor in prior:
        if path.startswith(key) or system == key:
            return factor
    return 1.0


class HybridRetriever(BaseRetriever):
    """Weighted RRF over a BM25 retriever and a dense retriever, then an optional source prior."""

    bm25: Any = None
    dense: Any = None
    bm25_weight: float = 0.5
    prior: list = []
    k: int = 8                                # how many fused documents to return

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun):
        lists, weights = [], []
        if self.bm25 is not None and self.bm25_weight > 0:
            lists.append(self.bm25.invoke(query))
            weights.append(self.bm25_weight)
        if self.dense is not None and self.bm25_weight < 1:
            lists.append(self.dense.invoke(query))
            weights.append(1 - self.bm25_weight)
        scores, first = {}, {}
        for docs, w in zip(lists, weights):
            for rank, d in enumerate(docs, start=1):
                key = d.page_content
                scores[key] = scores.get(key, 0.0) + w / (rank + RRF_C)
                first.setdefault(key, d)
        if self.prior:
            for key, d in first.items():
                scores[key] *= prior_factor(d, self.prior)
        ranked = sorted(first, key=lambda key: scores[key], reverse=True)   # stable: ties keep list order
        return [first[key] for key in ranked][: self.k]


class RerankRetriever(BaseRetriever):
    """Re-score the base retriever's candidates with a cross-encoder; keep the best `k`."""

    base: Any = None
    model: Any = None
    k: int = 8
    last_rerank_ms: float = 0.0

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun):
        candidates = self.base.invoke(query)
        if not candidates:
            return []
        t0 = time.perf_counter()
        scores = self.model.predict([(query, d.page_content) for d in candidates])
        self.last_rerank_ms = (time.perf_counter() - t0) * 1000
        order = sorted(range(len(candidates)), key=lambda i: float(scores[i]), reverse=True)
        return [candidates[i] for i in order][: self.k]


_CROSS_ENCODERS: dict = {}


def cross_encoder(name: str):
    """One cross-encoder per process (loading it takes seconds)."""
    if name not in _CROSS_ENCODERS:
        from sentence_transformers import CrossEncoder
        _CROSS_ENCODERS[name] = CrossEncoder(name)
    return _CROSS_ENCODERS[name]


def build(store, k: int, settings) -> tuple[BaseRetriever, str]:
    """The retriever the app uses, built from settings. `k` = documents per retriever (and
    documents returned after re-ranking)."""
    from langchain_community.retrievers import BM25Retriever

    w = settings.hybrid_bm25_weight
    rerank = settings.reranker_model
    depth = max(k, settings.rerank_top_n) if rerank else k
    docs = list(store.docstore._dict.values())
    bm25 = None
    if w > 0:
        bm25 = BM25Retriever.from_documents(docs)
        bm25.k = depth
    dense = store.as_retriever(search_kwargs={"k": depth}) if w < 1 else None
    prior = parse_prior(settings.source_prior)
    fused = HybridRetriever(bm25=bm25, dense=dense, bm25_weight=w, prior=prior, k=2 * depth)
    name = ("hybrid (BM25 + dense)" if 0 < w < 1 and w == 0.5 else
            "dense only" if w == 0 else "BM25 only" if w == 1 else f"hybrid (BM25 {w:g} + dense {1 - w:g})")
    if prior:
        name += f", source prior {settings.source_prior}"
    if rerank:
        return RerankRetriever(base=fused, model=cross_encoder(rerank), k=k), \
            f"{name}, re-ranked by {rerank} (top {depth})"
    return fused, name
