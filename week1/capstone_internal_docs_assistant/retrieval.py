"""Retriever (Task 6): dense MMR + BM25 keyword search fused with RRF.

`mode` can be "hybrid" (default), "mmr" or "similarity", which makes it easy to
run the A/B comparisons you log in EVAL_RESULTS.md. An optional `category`
metadata filter is applied to every mode.
"""
from __future__ import annotations

import re

from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

RRF_C = 60


def _tokens(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def _key(doc: Document) -> tuple:
    return (doc.metadata.get("source"), doc.metadata.get("chunk"))


class HybridRetriever:
    def __init__(self, vectorstore, mode: str = "hybrid"):
        if mode not in {"hybrid", "mmr", "similarity"}:
            raise ValueError(f"Unknown retriever mode: {mode}")
        self.vs = vectorstore
        self.mode = mode
        self._docs: list[Document] = []
        self._bm25: BM25Okapi | None = None
        self.refresh()

    def refresh(self) -> None:
        """Rebuild the BM25 side. Call after the index changes."""
        self._docs = list(self.vs.docstore._dict.values())
        corpus = [_tokens(d.page_content) or ["_"] for d in self._docs]
        self._bm25 = BM25Okapi(corpus) if corpus else None

    # --------------------------------------------------------------- strategies
    def _dense(self, query: str, k: int, flt: dict | None) -> list[Document]:
        fetch_k = max(40, k * 8)  # FAISS filters *after* fetching, so over-fetch
        if self.mode == "similarity":
            return self.vs.similarity_search(query, k=k, filter=flt, fetch_k=fetch_k)
        return self.vs.max_marginal_relevance_search(query, k=k, fetch_k=fetch_k, filter=flt)

    def _sparse(self, query: str, k: int, category: str | None) -> list[Document]:
        if not self._bm25:
            return []
        scores = self._bm25.get_scores(_tokens(query))
        ranked = sorted(zip(self._docs, scores), key=lambda x: x[1], reverse=True)
        out = []
        for doc, score in ranked:
            if score <= 0:
                break
            if category and doc.metadata.get("category") != category:
                continue
            out.append(doc)
            if len(out) == k:
                break
        return out

    # ------------------------------------------------------------------- public
    def retrieve(self, query: str, k: int = 4, category: str | None = None) -> list[Document]:
        category = None if category in (None, "", "any") else category
        flt = {"category": category} if category else None

        if self.mode != "hybrid":
            return self._dense(query, k, flt)

        pool = k * 2
        fused: dict[tuple, float] = {}
        by_key: dict[tuple, Document] = {}
        for ranking in (self._dense(query, pool, flt), self._sparse(query, pool, category)):
            for rank, doc in enumerate(ranking):
                key = _key(doc)
                by_key[key] = doc
                fused[key] = fused.get(key, 0.0) + 1.0 / (RRF_C + rank + 1)
        top = sorted(fused, key=fused.get, reverse=True)[:k]
        return [by_key[key] for key in top]
