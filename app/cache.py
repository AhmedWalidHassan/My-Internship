"""
Exact-match answer cache (Week 2, Task 6, layer 1).

THE KEY is the hard part. A cached answer may only be reused when the same question
would get the same answer, so the key is:

    sha256( config fingerprint | corpus version | normalised question )

* normalised question: NFKC, lowercase, collapsed whitespace, trailing punctuation
  stripped, so "How much PTO do I get?" == "how much pto do i get".
* corpus version: changes whenever a document is added, changed or removed
  (capstone ingest()), so a stale answer can never match after `add_document`.
  The cache is also emptied when it changes, to free the memory.
* config fingerprint: the model, embeddings, k, chunking, grading limit AND the
  capstone source (prompts + graph). A new prompt or model never serves old answers.

What is deliberately NOT cacheable: a turn with conversation history. "Can I carry it
over?" means something different in every conversation, and resolving it needs the
contextualize LLM call (which, Task 1 finding B, also leaks facts into its rewrite).
So only a session's FIRST question is read from or written to the cache; follow-ups
always run the graph. That loses nothing for repeated first questions (the common
case for an internal FAQ) and makes a wrong-context answer impossible.

Refusals get a SHORT TTL instead of the answer TTL: the corpus version already
invalidates a refusal when the missing document is added, and a short TTL bounds the
damage of a false refusal from the 4B fact-check (Figma), while still absorbing a burst
of the most expensive question type (23 LLM calls to refuse, Task 5).
"""

from __future__ import annotations

import hashlib
import threading
import time
import unicodedata
from dataclasses import dataclass, field

from cachetools import TTLCache

_TRAILING = " \t\n?!.,;:…。？！"


def normalize(question: str) -> str:
    q = unicodedata.normalize("NFKC", question).lower()
    q = " ".join(q.split())
    return q.rstrip(_TRAILING).strip()


@dataclass(frozen=True)
class CachedAnswer:
    answer: str
    sources: list
    node_path: list            # the path that produced it, for the record
    retries: int
    refused: bool
    trace_id: str              # trace of the run that produced it
    tokens_in: int
    tokens_out: int
    llm_calls: int
    created: float = field(default_factory=time.time)


class AnswerCache:
    def __init__(self, ttl_seconds: float, refusal_ttl_seconds: float, max_entries: int,
                 timer=time.monotonic):
        self._answers = TTLCache(maxsize=max_entries, ttl=ttl_seconds, timer=timer)
        # refusal_ttl 0 = never cache refusals
        self._refusals = (TTLCache(maxsize=max_entries, ttl=refusal_ttl_seconds, timer=timer)
                          if refusal_ttl_seconds > 0 else None)
        self._lock = threading.Lock()
        self.corpus_version: str | None = None
        self.invalidations = 0

    @staticmethod
    def key(question: str, *, corpus_version: str, fingerprint: str) -> str:
        raw = f"{fingerprint}|{corpus_version}|{normalize(question)}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def sync_corpus(self, version: str) -> bool:
        """Empty the cache if the corpus changed since the last request. True if it did."""
        with self._lock:
            if version == self.corpus_version:
                return False
            changed = self.corpus_version is not None
            self.corpus_version = version
            if changed:
                self._answers.clear()
                if self._refusals is not None:
                    self._refusals.clear()
                self.invalidations += 1
            return changed

    def get(self, key: str) -> CachedAnswer | None:
        with self._lock:
            hit = self._answers.get(key)
            if hit is None and self._refusals is not None:
                hit = self._refusals.get(key)
            return hit

    def put(self, key: str, entry: CachedAnswer) -> bool:
        with self._lock:
            if entry.refused:
                if self._refusals is None:
                    return False
                self._refusals[key] = entry
            else:
                self._answers[key] = entry
            return True

    def __len__(self) -> int:
        with self._lock:
            return len(self._answers) + (len(self._refusals) if self._refusals is not None else 0)


def config_fingerprint(settings, capstone_source: bytes) -> str:
    """Everything that changes what the pipeline answers, besides the corpus."""
    parts = [settings.llm_label, settings.embedding_provider, settings.hf_embed_model,
             settings.local_embeddings_backend, settings.retriever_k, settings.chunk_size,
             settings.chunk_overlap, settings.max_docs_to_grade, settings.openai_reasoning_effort,
             settings.llm_temperature, hashlib.sha256(capstone_source).hexdigest()]
    return hashlib.sha256(repr(parts).encode()).hexdigest()[:16]
