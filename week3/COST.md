# Week 3 — Cost, Latency & Budget

> **Standing rule 3:** every PR states what it cost. **Budget for the week: $25.**

Generator model: `qwen3.5:4b` (local Ollama) · Judge model: `qwen3.5:4b` in Task 1 (the Week 2 judges, unchanged; Task 2 must use a different one) · Embedding model: `all-MiniLM-L6-v2` (local)
Pricing assumed: `$0.00015 / 1K input tokens`, `$0.0006 / 1K output tokens` (gpt-4o-mini, as in Week 2), `$0.00002 / 1K embedding tokens` (text-embedding-3-small; tokens counted with tiktoken `cl100k_base`)

Everything runs locally, so **actual spend is $0**. "Cost" below is what the same tokens would cost at
those prices: the number that matters if the service moves to a hosted provider. The budget tracker
records both.

---

## Budget tracker

| Date | What ran | Cost | Running total | Remaining of $25 |
|---|---|---:|---:|---:|
| 2026-11-18 | Task 1: seed eval ×2, Week 2 eval gate ×2, `make cost` ×2 (236 questions, 4,469 pipeline LLM calls, plus judge calls that are not instrumented), live tier ×4, 5 full index builds ×2 devices, Docker smoke test | **$0 actual** (≈ $0.17 at gpt-4o-mini prices, pipeline calls only; embeddings ≈ $0.003) | $0 (≈ $0.17) | $25.00 |

---

## Task 1 — Embedding the real corpus

Measured 2026-11-18 with [`profile_corpus.py`](task_01_meet_the_corpus/scripts/profile_corpus.py): each corpus is indexed by the
real Week 2 `ingest()` (forced rebuild, embedding cache off), timed without the model load (6.7 s GPU / 3.3 s CPU),
and its chunks are counted with tiktoken. "Week 3, all 190" is every document pulled out by a reference extractor
and chunked by the Week 2 chunker (800/100): the cost of embedding the whole corpus once. The shipped loader embeds
only 7 chunks of it ([profile](task_01_meet_the_corpus/evidence/corpus_profile.md)).

| | Week 2 corpus (4 docs) | Week 3 corpus (190 docs) |
|---|---:|---:|
| Embedding tokens | 1,439 (20 chunks) | **52,609** (378 chunks). Shipped loader: 722 (7 chunks, README only); recursive: 15,184 (146) |
| Embedding cost | $0.000029 at $0.02/1M ($0 local) | **$0.00105** at $0.02/1M ($0 local) |
| Wall clock to build the index | 0.35 s GPU / 0.23 s CPU | **0.75 s GPU / 4.94 s CPU** (RTX 3060 laptop / same laptop's CPU) |
| Index size on disk | 40 KiB | **875 KiB** (FAISS + docstore) |
| Mean cost per question (`make cost`) | $0.000433 (28-question set, 12.8 LLM calls) | **$0.000795 as shipped** (21.2 calls) · $0.000668 recursive view (18.4 calls). Seed set, 40 questions |
| Mean latency per question | 3.28 s (p95 6.89 s) | **4.05 s as shipped** (p95 4.62 s) · 4.72 s recursive (p95 7.98 s) |

**Why it costs more to know less:** as shipped, every question finds nothing relevant, so it runs the whole
rewrite loop (2 rewrites, ~21 calls) before refusing: +84% cost per question for 0 correct answers.
`grade_documents` is 56% of spend in the recursive view (12.9 grading calls per question, vs 8.3 in Week 2).
Embedding is a rounding error: the whole corpus costs about a tenth of a cent to embed, less than
two questions through the graph.

## Task 2 — What an eval run costs

| Run type | Examples | Wall clock | Cost |
|---|---:|---:|---:|
| Retrieval only (dev) | | | |
| Full pipeline + judges (dev) | | | |
| Full pipeline + judges (test) | | | |

**Runs you can afford with the remaining budget:** ___ retrieval-only, or ___ full.

## Task 3 — Ingestion

| | Wall clock | Embedding calls | Cost |
|---|---:|---:|---:|
| Full re-ingest | | | |
| Incremental (one changed file) | | | |

## Task 4 — Winner vs baseline

| | Baseline | Winner | Delta |
|---|---:|---:|---:|
| Retrieval latency p50 | | | |
| Retrieval latency p95 | | | |
| End-to-end latency p50 | | | |
| Cost per question | | | |
| Projected monthly cost @ 1,000 questions/day | | | |

| Docker image size | *(W2 `RESULTS.md`)* | | |

**Cost by node — Week 2 vs now** (`make cost`, same seed set):

| Node | Week 2 % of spend | Week 3 winner % of spend |
|---|---:|---:|
| `contextualize` (or your history node) | | |
| `route_question` | | |
| `grade_documents` | | |
| `rewrite_query` | | |
| `generate` | | |
| `grade_generation` | | |

**Most expensive node now, and did your Week 2 reduction idea get tested?**

>

**Was the quality gain worth the latency and cost?** One honest paragraph:

>

## Task 5 — Time and truth

| | Before | After |
|---|---:|---:|
| LLM calls per question | | |
| Cost per question | | |

## Task 6 — Access control

| | Before | After |
|---|---:|---:|
| Retrieval latency p50 | | |
| Cache hit rate on the Week 2 workload | | |

*(A drop in hit rate is expected: answers are now cached per access scope.)*

---

## Running log — cost impact per PR

| PR | Change | Latency impact | Cost impact | Notes |
|---|---|---|---|---|
| (this PR) | Task 1 baseline | n/a (no product change). Measured on the new corpus: 4.05 s mean as shipped (3.28 s on the Week 2 corpus) | n/a. Measured: $0.000795 per question as shipped (+84%: every question exhausts the rewrite loop). Embedding the full corpus once: $0.00105 at text-embedding-3-small, 0.75 s GPU / 4.9 s CPU | corpus embed; all runs local, $0 actual |
| | Task 2 eval | n/a | | eval runs |
| | Task 3 ingestion | | | |
| | Task 4 experiments | | | |
| | Task 5 time and truth | | | |
| | Task 6 access | | | |

---

## The question to be able to answer on Friday

> *"The corpus is 190 documents. The real Northwind has about 40,000. What happens
> to ingestion time, index size, retrieval latency and monthly cost — and which of
> those breaks first?"*

>
