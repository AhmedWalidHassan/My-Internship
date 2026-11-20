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

Week 3 Task 6: `for_scope(groups)` returns the same retriever restricted to the chunks those groups may
see (common/access.py). The filter is applied INSIDE both searches, never to their results:
  * BM25: one index per access scope, built over the visible chunks only (cached per scope). A
    restricted chunk is not in the index, so it can't take a top-k slot or shape the term statistics.
  * dense: FAISS searches with an ID selector over the visible vectors, so the k nearest are the k
    nearest VISIBLE vectors. (LangChain's `filter=` does the opposite: it fetches `fetch_k` = 20 and
    filters those, so a user sees fewer than k passages whenever restricted chunks rank high.)
"""

from __future__ import annotations

import threading
import time
from typing import Any

import numpy as np

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from common.access import can_see

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
    store: Any = None                         # the FAISS store, for scoped views (Task 6)
    depth: int = 8                            # documents per retriever
    scopes: Any = None                        # {frozenset(groups): HybridRetriever}, built on first use
    scoped_only: bool = False                 # True for the production retriever: no unscoped search exists

    def for_scope(self, groups) -> "HybridRetriever":
        """This retriever over the chunks `groups` may see only (cached per group set)."""
        groups = frozenset(groups)
        if self.scopes is None:
            self.scopes = {"_lock": threading.Lock()}
        with self.scopes["_lock"]:
            if groups not in self.scopes:
                self.scopes[groups] = _scoped(self, groups)
            return self.scopes[groups]

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun):
        if self.scoped_only:
            raise RuntimeError("search through for_scope(groups): there is no search over every chunk")
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


class ScopedDense(BaseRetriever):
    """Dense search restricted to a set of FAISS positions (an ID selector): a pre-filter."""

    store: Any = None
    positions: Any = None                     # np.int64 array of the visible vectors' positions
    k: int = 8

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun):
        import faiss

        if self.positions is None or not len(self.positions):
            return []
        vector = np.array([self.store._embed_query(query)], dtype=np.float32)
        if self.store._normalize_L2:
            faiss.normalize_L2(vector)
        params = faiss.SearchParameters(sel=faiss.IDSelectorBatch(self.positions))
        _, idx = self.store.index.search(vector, min(self.k, len(self.positions)), params=params)
        docs = []
        for i in idx[0]:
            if i != -1:
                docs.append(self.store.docstore.search(self.store.index_to_docstore_id[int(i)]))
        return docs


def _scoped(full: HybridRetriever, groups: frozenset) -> HybridRetriever:
    from langchain_community.retrievers import BM25Retriever

    store = full.store
    # docstore order, as in build(): BM25 ties then break exactly as in the unscoped index
    visible_ids = [i for i, d in store.docstore._dict.items() if can_see(d.metadata, groups)]
    allowed = set(visible_ids)
    bm25 = None
    if full.bm25_weight > 0 and visible_ids:
        bm25 = BM25Retriever.from_documents([store.docstore._dict[i] for i in visible_ids])
        bm25.k = full.depth
    dense = None
    if full.bm25_weight < 1:
        positions = [pos for pos, doc_id in store.index_to_docstore_id.items() if doc_id in allowed]
        dense = ScopedDense(store=store, positions=np.array(sorted(positions), dtype=np.int64), k=full.depth)
    return HybridRetriever(bm25=bm25, dense=dense, bm25_weight=full.bm25_weight, prior=full.prior, k=full.k,
                           store=store, depth=full.depth)


class RerankRetriever(BaseRetriever):
    """Re-score the base retriever's candidates with a cross-encoder; keep the best `k`."""

    base: Any = None
    model: Any = None
    k: int = 8
    last_rerank_ms: float = 0.0

    def for_scope(self, groups) -> "RerankRetriever":
        return RerankRetriever(base=self.base.for_scope(groups), model=self.model, k=self.k)

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
    BM25Retriever  # noqa: B018  (fail here, at startup, if rank_bm25 is missing; the indexes are per scope)
    prior = parse_prior(settings.source_prior)
    # Week 3 Task 6: only per-scope views search (for_scope). This object holds the settings and the store;
    # an unscoped BM25 over every chunk is never built, and an unscoped search raises.
    fused = HybridRetriever(bm25=None, dense=None, bm25_weight=w, prior=prior, k=2 * depth, store=store,
                            depth=depth, scoped_only=True)
    name = ("hybrid (BM25 + dense)" if 0 < w < 1 and w == 0.5 else
            "dense only" if w == 0 else "BM25 only" if w == 1 else f"hybrid (BM25 {w:g} + dense {1 - w:g})")
    if prior:
        name += f", source prior {settings.source_prior}"
    if rerank:
        return RerankRetriever(base=fused, model=cross_encoder(rerank), k=k), \
            f"{name}, re-ranked by {rerank} (top {depth})"
    return fused, name
