# Caching, and proving the savings (Week 2, Task 6)

The brief is in [README.md](README.md). This page covers what was built, the decisions behind
it, and the evidence. The numbers live in [`week2/COST.md`](../COST.md#task-6--caching-before-and-after)
and [`week2/RESULTS.md`](../RESULTS.md#task-6--caching).

## Where things are

The cache runs inside the service, so its code is in the product. Everything else is in this folder.

| What | Where |
|---|---|
| Layer 1: exact-match answer cache (key, TTLs, invalidation) | [`app/cache.py`](../../app/cache.py), used by `ChatService.events()` in [`app/service.py`](../../app/service.py) |
| Layer 2: embedding cache (`CacheBackedEmbeddings` + file store + hit counter) | [`week1/common/embedding_cache.py`](../../week1/common/embedding_cache.py), switched on in `common/utils.get_embeddings()` |
| Corpus version (changes when a document changes) | capstone `ingest()` → `ingest_stats["corpus_version"]` |
| Settings: `CACHE_ENABLED`, TTLs, size, `EMBEDDING_CACHE_PATH`, `CACHE_PREWARM`, `SEMANTIC_CACHE_ENABLED` | [`week1/common/settings.py`](../../week1/common/settings.py), documented in `week1/.env.example` |
| `cache_hit` in the log line; cache gauges in `/metrics` | `app/service.py`, [`app/observability.py`](../../app/observability.py) |
| **Benchmarks** (`make cache-bench MODE=cold-warm\|workload\|prewarm`) | [`scripts/cache_benchmark.py`](scripts/cache_benchmark.py) |
| **Semantic-cache analysis** | [`scripts/semantic_cache_analysis.py`](scripts/semantic_cache_analysis.py) |
| Evidence | [`evidence/`](evidence/) |
| Tests (18) | [`tests/test_cache.py`](../../tests/test_cache.py) |

## Layer 1: the answer cache, and its key

```
key = sha256( config fingerprint | corpus version | normalise(question) )
```

| Part | Why it is in the key |
|---|---|
| `normalise(question)` | NFKC, lowercase, collapsed whitespace, trailing `?!.` stripped: "How much PTO do I get?" = "how much pto do i get". Inner punctuation and wording are kept: no guessing |
| **corpus version** | A hash of every indexed file's hash (plus chunking and embedding model), recomputed by `ingest()`. After `add_document` the old entries **can't match**, and the cache is also emptied on the change |
| **config fingerprint** | Model, embeddings, `RETRIEVER_K`, chunking, `MAX_DOCS_TO_GRADE`, temperature, and a hash of the capstone source (prompts + graph). A new prompt or model never serves an answer the old one wrote |

**What deliberately is NOT in the key: the session. Instead, only a session's *first* question
uses the cache.** A follow-up ("Can I carry it over?") means something different in every
conversation. The only key that could capture that is the standalone question, but producing it
needs the `contextualize` LLM call, and Task 1's finding B showed that rewrite leaks facts from
the previous answer. Keying on the history text instead would almost never repeat. So turns with
history are never read from or written to the cache.

A cache hit is still written into the session's memory, so a follow-up to a cached answer
resolves correctly (tested, and seen live: Bob's follow-up after a cache hit was understood
from that turn).

**On a hit:**
- the response is the stored, already fact-checked answer and its sources, with
  `node_path: ["cache"]`, `llm_calls: 0`, `cache_hit: true` and `cached_from_trace_id`;
- `/chat/stream` sends the same event protocol (a `cache` status event, tokens, `done`);
- the request still gets its own LangSmith run (tagged `cache_hit`, pointing at the original
  trace), so "log line → trace" and `/feedback` keep working.

**Refusals: a short TTL (5 min), not "never".**
- **Why cache them at all:** refusing is the most expensive path (23 LLM calls, Task 5), and the
  trap's scenario is already handled: adding the missing document changes the corpus version, so
  the stale refusal can't be served (`test_add_document_invalidates_cached_answers`).
- **Why short:** a refusal can be a *false* one from the 4B fact-check. In the cold/warm run the
  Figma question's false refusal was cached and re-served, and 5 minutes bounds that damage.
- `CACHE_REFUSAL_TTL_SECONDS=0` turns refusal caching off entirely.

**Not served from the cache:**
- the eval: `app.py eval` calls the graph directly, so Task 7's gate measures the real pipeline
  (`test_eval_path_never_sees_the_answer_cache`);
- the Task 5 cost report (`use_cache=False`);
- anything with `CACHE_ENABLED=false`.

Storage is an in-process `cachetools.TTLCache` (LRU-bounded). Like sessions, it's per process: a
second worker would have its own cache. Redis would share it, and the key design wouldn't change.

## Layer 2: the embedding cache

`CacheBackedEmbeddings` wraps the embedding model with a `LocalFileStore` at
`EMBEDDING_CACHE_PATH`. By default that's `embedding_cache/` next to the index, which is
`/data/embedding_cache` in the container volume.
- **Keys:** sha256, namespaced by the embeddings class and model, so another model never reads
  these vectors.
- **Queries** are cached too.
- **Transparent to the index:** the index signature looks through the wrapper, so turning the
  cache on or off doesn't trigger a re-embed (tested).
- **Counted:** a small counting store feeds `northwind_embedding_cache_hits/misses`.

| Measured | Result |
|---|---|
| Full index rebuild, cold embedding cache | 20 chunks embedded, 0.678 s |
| Full index rebuild again (and again) | **0 embedded, 20 from cache, 0.004 s** |
| Query embeddings on the 120-request workload | 5 hits / 52 misses (answer-cache hits skip retrieval, so few queries repeat) |

([`evidence/embedding_cache_rebuild.txt`](evidence/embedding_cache_rebuild.txt))

## Layer 3: semantic cache, argued against

Not implemented, with measurements ([`evidence/semantic_cache_analysis.md`](evidence/semantic_cache_analysis.md)).
On this corpus no cosine threshold separates paraphrases (same answer) from near-misses (one
word apart, different answer):
- the rover's speed **with** vs **without** a load scores **0.977** (1.8 vs 2.2 m/s), above every
  true paraphrase;
- "vacation days" vs "PTO" scores 0.186.

| Threshold | Paraphrases that would hit | Near-misses served the WRONG answer |
|---:|---:|---:|
| 0.80 | 4/10 | 3/10 |
| 0.90 | 1/10 | 2/10 |
| 0.95 | 0/10 | 1/10 |

The upside is also small. Paraphrases were 3% of the workload's requests, so a perfect semantic
cache adds at most ~3 points of hit rate, and every miss pays an extra embedding. The full two
paragraphs are in [RESULTS.md](../RESULTS.md#task-6--caching). `SEMANTIC_CACHE_ENABLED=true` is
**rejected at startup** with a pointer here, not silently ignored.

## The numbers

| | Result | Evidence |
|---|---|---|
| Cold vs warm, same 20 questions | mean **3.64 s → <1 ms**, p95 **7.89 s → <1 ms**, $0.000444 → $0 per question, 255 → 0 LLM calls | [`evidence/cold_vs_warm.md`](evidence/cold_vs_warm.md) |
| Hit rate, defined workload (120 requests) | **72%**. Spend $0.0181 vs $0.0657 without (−72%) | [`evidence/workload_hit_rate.md`](evidence/workload_hit_rate.md) |
| Through the real API | miss 3.16 s → hit **1.8 ms**; the follow-up in the cached session ran the full graph with history | [`evidence/api_cache_demo.txt`](evidence/api_cache_demo.txt) |
| Pre-warm (stretch) | cold-start user p95 6.83 s → <1 ms, for 32 s of LLM work per restart (off by default) | [`evidence/prewarm.md`](evidence/prewarm.md) |
| Retrieval cache (stretch) | Not built: `retrieve` is 0.3% of time and $0 (Task 5 data). The answer cache carries the saving | RESULTS.md |

## Evidence for "Done when…"

| Check | Result |
|---|---|
| `COST.md` cold vs warm, same 20 examples | Filled in: mean, p95, cost per question and total run cost, plus the delta |
| Hit rate over a defined, described workload | 72%, with the workload described and every miss explained |
| Invalidation test, named in `RESULTS.md` | `tests/test_cache.py::test_add_document_invalidates_cached_answers`. Stale answers **and** stale refusals are never served after `add_document` |
| Semantic-cache decision with reasoning | Argued against, with measured similarities; the flag is rejected at startup |
| `cache_hit` in the log line and `/metrics` | `cache_hit`, `route: "cache"`, `cached_from_trace_id` in the line; `northwind_cache_hits_total`, `_hit_rate`, `_entries`, `_invalidations`, `_enabled`, `northwind_embedding_cache_hits/misses` |
| `CACHE_ENABLED=false` fully disables it, tested | No answer cache **and** no embedding cache; two tests prove the uncached path answers and runs the full pipeline every time |
