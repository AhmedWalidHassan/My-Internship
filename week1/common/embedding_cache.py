"""
Embedding cache (Week 2, Task 6, layer 2): identical text is never embedded twice,
across runs.

LangChain's CacheBackedEmbeddings in front of the real model, backed by a local file
store (one file per vector), with a hit/miss counter in between so /metrics and the
cost report can say whether it pays. The namespace is the embeddings class + model,
so a different model (or the ONNX runtime of the same model) never reads another's
vectors.

No side effects at import (unlike common/utils.py, which loads .env), so the API's
metrics can import the counters safely.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Iterator, Sequence
from pathlib import Path

from langchain_core.stores import BaseStore

STATS = {"hits": 0, "misses": 0}
_lock = threading.Lock()


class CountingStore(BaseStore[str, bytes]):
    """A ByteStore wrapper that counts cache hits and misses (an mget miss = None)."""

    def __init__(self, inner: BaseStore[str, bytes]):
        self.inner = inner

    def mget(self, keys: Sequence[str]) -> list[bytes | None]:
        values = self.inner.mget(keys)
        hits = sum(v is not None for v in values)
        with _lock:
            STATS["hits"] += hits
            STATS["misses"] += len(values) - hits
        return values

    def mset(self, key_value_pairs) -> None:
        self.inner.mset(key_value_pairs)

    def mdelete(self, keys: Sequence[str]) -> None:
        self.inner.mdelete(keys)

    def yield_keys(self, *, prefix: str | None = None) -> Iterator[str]:
        return self.inner.yield_keys(prefix=prefix)


def model_namespace(embeddings) -> str:
    """"HuggingFaceEmbeddings.sentence-transformers_all-MiniLM-L6-v2": safe as a path."""
    embeddings = embeddings.__dict__.get("inner", embeddings)   # look through the retry wrapper
    name = (getattr(embeddings, "model_name", None) or getattr(embeddings, "model", None)
            or "default")
    return re.sub(r"[^A-Za-z0-9_.-]", "_", f"{type(embeddings).__name__}.{name}")


def with_cache(embeddings, directory: Path):
    """Wrap `embeddings` so documents AND queries are cached on disk under `directory`."""
    from langchain_classic.embeddings import CacheBackedEmbeddings
    from langchain_classic.storage import LocalFileStore

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    store = CountingStore(LocalFileStore(directory))
    return CacheBackedEmbeddings.from_bytes_store(
        embeddings, store, namespace=model_namespace(embeddings) + ".",
        query_embedding_cache=True,            # the same store: a query is just text too
        key_encoder="sha256")


def stats() -> dict:
    with _lock:
        return dict(STATS)
