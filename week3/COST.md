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
| 2026-11-18 | Task 2: 3 full dev runs (210 questions, ~3,760 pipeline LLM calls + ~420 judge calls), 2 judge replays on run 1 (~280 judge calls), synthetic generation (33 LLM calls, 65 candidates), retrieval-only runs | **$0 actual** (≈ $0.15 pipeline + ≈ $0.08 judge at gpt-4o-mini prices) | $0 (≈ $0.40) | $25.00 |
| 2026-11-18 | Task 3: 2 full dev runs (140 questions, ~1,950 pipeline LLM calls + ~280 judge calls), retrieval-only runs, live tier (9 tests), 4 full + 2 incremental re-ingests, 2 image builds + Docker smoke test | **$0 actual** (≈ $0.10 pipeline + ≈ $0.04 judge at gpt-4o-mini prices; embeddings ≈ $0.003) | $0 (≈ $0.54) | $25.00 |
| 2026-11-18 | Task 4: 18 retrieval-only runs (dev ×16, test ×2; no LLM), 4 full dev runs (280 questions, ~3,900 pipeline LLM calls + ~560 judge calls), 4 `make cost` runs (160 questions), 7 index builds, 1 image build + Docker smoke test | **$0 actual** (≈ $0.21 pipeline + ≈ $0.08 judge at gpt-4o-mini prices; retrieval runs ≈ $0.0003 of query embeddings) | $0 (≈ $0.83) | $25.00 |
| 2026-11-20 | Task 5: 2 full dev runs (TT-01, TT-02: 140 questions, ~1,920 pipeline LLM calls + ~280 judge calls), 2 `make cost` runs (80 questions, ~1,100 calls), live checks (~10 questions), `make check-live` ×1 | **$0 actual** (≈ $0.17 pipeline + ≈ $0.04 judge at gpt-4o-mini prices) | $0 (≈ $1.04) | $25.00 |
| 2026-11-20 | Task 6: 1 full dev run (70 questions, ~1,000 pipeline LLM calls + ~140 judge calls), `make cost` (40), 2 cache workloads (240 requests, ~93 misses ≈ 1,300 calls), live attack check (~10 questions), retrieval-only runs (no LLM) | **$0 actual** (≈ $0.17 pipeline + ≈ $0.02 judge at gpt-4o-mini prices) | $0 (≈ $1.23) | $25.00 |

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

Measured 2026-11-18, laptop GPU, generator `qwen3.5:4b`, judge `gemma3:4b`. Actual spend is $0 (all local).
The cost column prices the same tokens at gpt-4o-mini / text-embedding-3-small rates. Judge tokens aren't
instrumented, so the judge share is an estimate (~900 input / ~300 output tokens per example for the
two judge calls).

| Run type | Examples | Wall clock | Cost |
|---|---:|---:|---:|
| Retrieval only (dev) | 70 (60 with gold docs) | **7.5 s** (5.6 s model + index load, 0.3 s for 60 queries) | **$0** (731 query tokens = $0.000015 if hosted) |
| Full pipeline + judges (dev) | 70 | **~530 s** (pipeline 386–392 s, then ~140 s of judging) | **$0** actual · ≈ $0.048 pipeline ($0.000687 × 70, 17.9 LLM calls each) + ≈ $0.02 judge (estimated) |
| Full pipeline + judges (test) | 30 | not run: test is frozen (0 runs). Estimate ~230 s | ≈ $0.03 (estimate) |

**Runs you can afford with the remaining budget:** at hosted prices, ~**1.6 million** retrieval-only
runs (effectively unlimited), or ~**350** full dev runs (~$0.07 each). Locally both cost $0; the real
limit is time: ~9 minutes per full dev run against ~8 seconds for retrieval-only. That's the case for
doing Wednesday's experiments retrieval-first.

## Task 3 — Ingestion

Measured 2026-11-18 with [`measure_ingest.py`](task_03_ingestion/scripts/measure_ingest.py) on a temporary
copy of the corpus (the export itself is never edited), the real embedding model, and the embedding
cache **off**, so every call is real. Tokens are counted with tiktoken `cl100k_base` over exactly the
embedded texts, priced at text-embedding-3-small ($0.02 / 1M). Local spend: $0.
[GPU](task_03_ingestion/evidence/ingest_cost_gpu.json) · [CPU](task_03_ingestion/evidence/ingest_cost_cpu.json).

| | Wall clock | Embedding calls | Cost |
|---|---:|---:|---:|
| Full re-ingest | **8.8 s** GPU / **22.2 s** CPU (27.2 s inside the container, CPU), parsing all 190 documents included | 348 chunks, 30,809 tokens | **$0.00062** |
| Incremental (one changed file) | **0.04 s** GPU / 0.06 s CPU (189 documents reused by hash) | **1 chunk**, 170 tokens | **$0.0000034** |
| No change (warm start) | 0.03 s | 0 | $0 |

- **Fewer tokens than a naive extraction, despite reading all 190 documents.** Task 1's naive extraction
  of the same 190 documents was 52,609 tokens. Removing the manual's boilerplate and the wiki chrome cut
  that by **41%**.
- **PDF table detection dominates a full re-ingest's parse time** (~0.2 s a page, on pages with
  side-by-side text only). Embedding is the smaller part on the GPU.
- **Per question it got slightly cheaper in calls** (17.9 → 13.9: fewer refusals, so fewer rewrite
  loops), but each call carries more context (real documents now). Net **$0.000687 → $0.000698 (+1.7%)**,
  mean latency 5.4 → 5.9 s.
- **Docker image:** full API image **2.07 → 2.35 GB (+285 MB)**, for PyMuPDF 2.1 (110 MB) and the
  onnxruntime it now requires (63 MB); openpyxl and BeautifulSoup are ~2 MB.

## Task 4 — Winner vs baseline

Measured 2026-11-18. Retrieval latency from the dev retrieval-only runs, on the laptop GPU (CPU numbers
noted). End-to-end latency, cost and nodes from Week 2's `make cost` on the **seed set (40)**, same
questions for both, local `qwen3.5:4b`, priced at gpt-4o-mini rates. "Winner" = EXP-09, the retrieval
winner, which was **not shipped** (RESULTS.md Task 4). [Reports](task_04_retrieval_experiments/evidence/).

| | Baseline | Winner | Delta |
|---:|---:|---:|---:|
| Retrieval latency p50 | 0.6 ms (CPU 5.9 ms) | 0.7 ms | +0.1 ms |
| Retrieval latency p95 | 0.9 ms (CPU 7.9 ms) | 1.2 ms | +0.3 ms |
| End-to-end latency p50 | 4.57 s (p95 15.1 s) | 4.47 s (p95 9.9 s) | −0.1 s (p95 −5.1 s) |
| Cost per question | $0.000729 | $0.000591 | **−19%** |
| Projected monthly cost @ 1,000 questions/day | $21.86 | $17.72 | −$4.14 |

| Docker image size | Week 2: 2.07 GB (1.50 GB on disk) → Task 3: 2.35 GB | 2.35 GB (+11 KB: code only, no new dependency) | ≈ 0 |

- **Why the winner is cheaper:** its 400-character chunks make every `grade_documents` prompt shorter
  (same number of calls, fewer tokens).
- **The rejected re-ranker (EXP-06/10)** would have added **+57 ms per query on GPU, +488 ms on CPU**
  (the container), times up to 3 retrievals per answer. It needs no new package in the full image
  (torch 747 MB and sentence-transformers are already there) plus a ~90 MB model download. The slim
  image would need torch (+~750 MB, Week 2 Task 4) or a fastembed cross-encoder (not measured).
- **The rejected multilingual model (EXP-05)** is ~470 MB instead of ~90 MB and doubles index-build time.

**Cost by node — Week 2 vs now** (`make cost`; Week 2 = its 28-question set on the Week 1 corpus,
Week 3 = the seed set on the Week 3 corpus):

| Node | Week 2 % of spend | Week 3 baseline % | Week 3 winner % of spend |
|---|---:|---:|---:|
| `contextualize` (or your history node) | 0% | 0% | 0% |
| `route_question` | 5.8% | 3.5% | 4.3% |
| `grade_documents` | **52.2%** (8.3 calls/q) | **44.3%** (9.2 calls/q) | **42.9%** (9.4 calls/q) |
| `rewrite_query` | 2.7% | 2.0% | 2.6% |
| `generate` | 16.8% | 21.2% | 21.7% |
| `grade_generation` | 22.3% | 29.0% | 28.6% |

**Most expensive node now, and did your Week 2 reduction idea get tested?**

> **Still `grade_documents`** (43% of spend, 9.4 calls per question). Its share fell because generation
> now has real documents to write from: `generate` and `grade_generation` grew.
>
> Week 2 proposed *batch grading* (all passages in one call) and measured that *grading fewer* hurt.
> Here I tested *grading fewer on a better ranker*: **EXP-11, `MAX_DOCS_TO_GRADE` 6 → 3 on the winner.**
> - **Cost went down:** −29% on the seed set ($0.000591 → $0.000420, 14.4 → 9.4 calls, p50 4.5 → 3.9 s).
>   `grade_documents` drops to 31% and `grade_generation` becomes the most expensive node (34%).
> - **Answers went down too:** 5 fewer dev answers (deterministic 0.686 → 0.614).
>
> So the brief's "a re-ranker lets you grade fewer documents" did not hold here. Better *document*
> ranking does not put the right *passage* in the top 3 often enough. Batch grading is still the
> untested idea, and still the best candidate: it cuts calls without dropping passages.

**Was the quality gain worth the latency and cost?** One honest paragraph:

> **The retrieval gain was free and real, and it still wasn't worth shipping.**
> - **Free:** EXP-09 costs nothing at query time (+0.1 ms), makes answers ~19% cheaper (shorter
>   grading prompts), adds nothing to the image, and lifts MRR by 0.18 on dev and 0.14 on test.
> - **Not worth shipping:** it **answers 4 fewer dev questions** than the baseline (deterministic
>   0.743 → 0.686), because smaller chunks split facts the generator needs together. The cheaper-still
>   variant (EXP-11) loses 5 more.
> - **The re-ranker was worse on all three counts:** less quality than EXP-09, 500 ms per query on
>   CPU, and torch in any image that wants it.
>
> On this system, cost and retrieval quality are no longer what limits answers: the 4B graders, the
> fact-check and version handling are. So the $4/month saving isn't worth 6% fewer correct answers,
> and the decision was to keep the Task 3 configuration and spend the next day on Task 5. What would
> change my mind: a chunking that keeps a section's facts together while staying small (sentence
> windows, or parent-document retrieval: retrieve 400-character chunks, send their 800-character
> parents to the graph). That keeps EXP-09's ranking without its fragmentation, and is the obvious next
> experiment.

## Task 5 — Time and truth

Measured 2026-11-20. Before = the Task 3/4 system; after = what ships (TT-01). Seed set (40) from
Week 2's `make cost`, same questions both times, local `qwen3.5:4b` priced at gpt-4o-mini rates
([before](task_04_retrieval_experiments/evidence/cost_seed_baseline.md),
[after](task_05_time_and_truth/evidence/cost_seed_after.md)); dev (70) from the full eval runs.

| | Before | After |
|---|---:|---:|
| LLM calls per question | 14.1 (dev 13.9) | 14.1 (dev 13.7) |
| Cost per question | $0.000729 (dev $0.000698) | $0.000794 (dev $0.000755), **+8–9%** |
| Input / output tokens per question (seed) | 3,780 / 269 | 4,094 / 300 |
| `generate` input tokens per question (seed) | 673 | 967 (+44%) |
| End-to-end latency p50 (seed) | 4.57 s | 4.54 s |
| Curation (`curate()` in `retrieve`, dev, CPU) | – | 0.7 ms p50, 1.0 ms p95. Catalog build at startup: 0.04 ms (348 chunks) |
| Projected monthly cost @ 1,000 questions/day | $21.86 | $23.81 (+$1.95) |

**What Task 5 added per question: no LLM call, about 300 input tokens (+$0.00006).**
- **No new LLM call.** Supersession, drafts, authority and the rover ambiguity are decided from
  metadata in the `retrieve` node, in under 1 ms.
- **The cost is prompt length.** Every passage now carries a status line (`HR-POL-004 v3.0, effective
  2026-03-01: CURRENT approved version as of 2026-10-01`), and `GENERATE_PROMPT` gained rules 5–9.
  Those tokens land in `generate` (share of spend 21% → 26%) and `grade_generation`. `grade_documents`
  sees the bare passage and didn't change (2,079 → 2,048 tokens). It is still the most expensive
  node (40%).
- **Swapped-in current versions** add at most 2 passages, only when a superseded version was retrieved
  alone.
- **The reverted TT-02** cost about the same ($0.000761 seed, $0.000797 dev). It was reverted for
  quality, not cost (EXPERIMENTS.md).

## Task 6 — Access control

Measured 2026-11-20 on the laptop.
- **Retrieval latency:** the 70 dev queries ×3, each searched as its own user, compared with a scope
  that sees every chunk. That scope ranks exactly like the Week 2 retriever
  (`fusion_equivalence.py`).
- **Cache hit rate:** Week 2's own workload (`cache_benchmark.py workload`, 120 requests, `--seed 7`),
  same questions, asked by one employee vs. by the six directory users. Real model.
- **Cost:** `make cost` on the seed set (40).
- Evidence: [`task_06_who_is_asking/evidence/`](task_06_who_is_asking/evidence/).

| | Before | After |
|---|---:|---:|
| Retrieval latency p50 | 0.53 ms (p95 0.74) | 0.53 ms (p95 0.75), plus **5–9 ms once per access scope per process** (building its BM25 index) |
| Cache hit rate on the Week 2 workload | **70%** (84/120: one user, one scope) | **52%** (63/120: six users, four scopes) |
| LLM calls / cost per question (seed set) | 14.1 / $0.000794 | 14.95 / $0.000829 (+4%) |
| … the 35 seed questions outside `access` | 14.7 / $0.000846 | 14.6 / $0.000841 (unchanged) |
| Projected monthly @ 1,000 questions/day | $23.81 | $24.87 |

*(A drop in hit rate is expected: answers are now cached per access scope.)*

- **The 18-point drop is exactly the new miss reason:** 20 requests (17%) were "first time this
  question was asked *in this access scope*". The three plain employees share one scope, so most
  traffic still shares entries.
- In a real company almost everyone is in the `all`-only scope, so the drop there would be smaller
  than with this directory, where half the users are managers or HR.
- Cost without the cache, for the same workload: $0.094. With it: $0.045 (was $0.031 with one scope).
- **Per question, access control adds no LLM call and no measurable retrieval time.** Filtering
  happens inside the searches, which were already sub-millisecond.
- **The +4% on the seed set is entirely the `access` questions.** The three unauthorised ones are now
  refused instead of answered from the salary bands, and a refusal runs the whole rewrite loop
  (10 → 23 LLM calls each). Leaking was cheaper.
- **Memory:** one BM25 index per access scope (4 here, each over at most 348 chunks).
  - At 40,000 documents it is still one index per *distinct group set*, not per user. That stays
    small as long as groups are coarse.
  - With per-user ACLs it would not, and the answer then is a filtered inverted index (one BM25 with
    an ID filter, like the FAISS side) rather than a copy per scope.
- **One-off:** the first start after this change re-indexed every document (18 s), because a
  document's hash now includes its `_metadata.csv` row (an ACL change must reach the index).

---

## Running log — cost impact per PR

| PR | Change | Latency impact | Cost impact | Notes |
|---|---|---|---|---|
| (this PR) | Task 1 baseline | n/a (no product change). Measured on the new corpus: 4.05 s mean as shipped (3.28 s on the Week 2 corpus) | n/a. Measured: $0.000795 per question as shipped (+84%: every question exhausts the rewrite loop). Embedding the full corpus once: $0.00105 at text-embedding-3-small, 0.75 s GPU / 4.9 s CPU | corpus embed; all runs local, $0 actual |
| (this PR) | Task 2 eval | per question on the Week 3 corpus: 5.4 s mean (17.9 LLM calls). The loader change (118 of 190 documents instead of 1) is what moved it: 4.05 s in Task 1 → 5.4 s, because now some answers get generated and fact-checked instead of all ending in a refusal. Index build: 139 chunks in 1.0 s | $0.000687 per question at gpt-4o-mini prices (Task 1 as shipped: $0.000795). Eval: retrieval-only $0 and 7.5 s; full dev run ≈ $0.07 and ~9 min | judge is now `gemma3:4b`; all runs local, $0 actual |
| (this PR) | Task 3 ingestion | per question 5.4 → 5.9 s mean (more real context per call; fewer calls). Full re-ingest 8.8 s GPU / 22 s CPU; one changed file 0.04 s. Warm container start loads the index in 0.2 s (startup 11 s) | $0.000687 → $0.000698 per question (+1.7%; LLM calls 17.9 → 13.9). Full re-embed $0.00062, one file $0.0000034 at text-embedding-3-small | image +285 MB (PyMuPDF 2.1 + onnxruntime); all local, $0 actual |
| (this PR) | Task 4 experiments | none shipped: production keeps the Task 3 retriever (same rankings, re-implemented as weighted RRF). New per-PR `retrieval-gate` CI job: ~1–2 min of free runner time | none at runtime. Measured for the rejected winner: −19% per question; re-ranker +488 ms/query on CPU | 12 experiments, all local, $0 actual; image +11 KB |
| (this PR) | Task 5 time and truth | none measurable: curation 0.7 ms p50 per question, no LLM call; end-to-end p50 4.57 → 4.54 s (seed) | $0.000729 → $0.000794 per question (+9%, seed; dev +8%): ~300 more input tokens from status labels and generator rules, LLM calls unchanged (14.1) | API change: `sources` are objects; all runs local, $0 actual |
| (this PR) | Task 6 access | retrieval unchanged (0.53 ms p50, filtering inside the searches) + 5–9 ms once per access scope per process; one-off full re-index (18 s) | no LLM call added. Seed: $0.000794 → $0.000829 (+4%), all from 3 access questions now refused (10 → 23 calls); the other 35 unchanged. Cache hit rate on the Week 2 workload 70% → 52% with 6 users (per-scope keys) | API change: `user_id` required (401), sessions bound (403); all runs local, $0 actual |

---

## The question to be able to answer on Friday

> *"The corpus is 190 documents. The real Northwind has about 40,000. What happens
> to ingestion time, index size, retrieval latency and monthly cost — and which of
> those breaks first?"*

>
