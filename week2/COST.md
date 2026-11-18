# Week 2 — Cost & Latency

> **Standing rule 3:** every PR states what it cost. This file is where those
> numbers accumulate. Measure over the same 20-example eval set every time so the
> rows are comparable.

Model / provider used for these figures: `qwen3.5:4b` on local Ollama (actual spend **$0**); tokens are Ollama's own counts
Pricing assumed: `$0.00015 / 1K input tokens`, `$0.0006 / 1K output tokens` (gpt-4o-mini list price, `COST_PER_1K_*_TOKENS`), so "cost" below means **what the same traffic would cost on gpt-4o-mini**

---

## Baseline — the agentic graph as it stands after Task 1

Measured 2026-11-16 with `make cost` (Task 5), over the **28-example eval set**: the 20-question set
grew to 24 answerable + 4 out-of-scope in Week 1, and the out-of-scope ones matter here because
refusals are the expensive path. Every question runs in a fresh session; one warm-up first; k = 4,
`MAX_DOCS_TO_GRADE=6`. Report: [`task_05_observability/evidence/cost_report.md`](task_05_observability/evidence/cost_report.md).

| Metric | Value |
|---|---:|
| Mean latency per question | 3.28 s |
| p95 latency per question | 6.89 s |
| Mean LLM calls per question | 12.8 (p95 24, max 25; 9.8 when answered first time) |
| Mean tokens per question (in / out) | 2,381 / 127 |
| Mean cost per question | $0.000433 |
| **Projected monthly cost @ 1,000 questions/day** | **$12.99** (gpt-4o-mini prices; $0 as run locally) |

### Cost by node

Which node is actually spending the money? `grade_documents` calls the LLM once
*per retrieved document*, so start by checking whether it dominates.

| Node | Calls per question | Tokens (in / out per question) | Cost per question | % of total | Time per question |
|---|---:|---:|---:|---:|---:|
| `contextualize` (or your history node) | 0.00 | 0 / 0 | $0 | 0% | 0.00 s |
| `route_question` | 1.00 | 147 / 5 | $0.000025 | 5.8% | 0.18 s |
| `grade_documents` | **8.29** | **1,442 / 17** | **$0.000226** | **52.2%** | 1.08 s |
| `rewrite_query` | 0.50 | 52 / 6 | $0.000012 | 2.7% | 0.13 s |
| `generate` | 1.04 | 340 / 37 | $0.000073 | 16.8% | 0.71 s |
| `grade_generation` | 1.86 | 395 / 62 | $0.000097 | 22.3% | 1.16 s |
| `direct_answer` (small-talk check) | 0.07 | 5 / 0 | $0.000001 | 0.2% | 0.01 s |

(`contextualize` is 0 because every eval question starts a fresh session: no history, no call. In a
real conversation, a follow-up adds one call of ~150 tokens. The rows sum to 12.8 calls.)

**Most expensive node:** `grade_documents`: **52% of spend, 8.3 of the 12.8 LLM calls per question**
(one per graded passage, up to 6 per search, and again after every rewrite). The most expensive
*time* is `grade_generation` (35%: two judge calls with longer outputs).

**One concrete idea for reducing it:**

> **Grade all the passages of a search in ONE call** (list them numbered, ask which numbers are
> relevant) instead of one call per passage. Each call today is ~174 input tokens, of which ~90
> are the same instructions and question repeated 6 times. Batched, one search costs about
> 80 + 6 × 90 ≈ 620 tokens instead of ~1,040, and 1 call instead of 6. Estimate: the node goes
> from $0.000226 to ~$0.00013 per question (total −22%), and from 8.3 to ~1.4 calls. It's not
> measured yet, and correctness would need re-checking, because a 4B model grading 6 passages at
> once may judge worse.
>
> **What NOT to do, measured** (Task 5 stretch, [`grading_experiment.md`](task_05_observability/evidence/grading_experiment.md)):
> simply grading fewer passages (`MAX_DOCS_TO_GRADE=2`) cuts cost **36%** ($0.000433 → $0.000278,
> 12.8 → 7.6 calls, mean latency 3.28 → 2.46 s), but **correctness falls 0.96 → 0.82**. Three
> answerable questions became refusals (R2 weight, R2 outdoors, meal limit) and one got a wrong
> answer. Retrieval still found every answer (hit rate 1.00); the right chunk was just outside the
> top 2 (R2 outdoors: 4th). Saving $4.66/month at 1,000 questions/day isn't worth 1 in 7 answers.

---

## Task 6 — Caching, before and after

Same 20 examples, cold cache vs warm cache.

Measured 2026-11-16 with `make cache-bench MODE=cold-warm`: the first 20 answerable eval
questions, each in a fresh session, through the service code path (`ChatService`) on local
`qwen3.5:4b`, priced at gpt-4o-mini rates. Pass 1 started with an empty answer cache and a fresh
embedding cache; pass 2 reused what pass 1 left. Write-up:
[`task_06_caching/CACHING.md`](task_06_caching/CACHING.md).

| | Mean latency | p95 latency | Mean cost / question | Total run cost |
|---|---:|---:|---:|---:|
| Cold cache (no reuse) | 3.64 s | 7.89 s | $0.000444 | $0.008886 (255 LLM calls) |
| Warm cache (second run) | <1 ms (1.8 ms over HTTP) | <1 ms | $0 | $0 (0 LLM calls) |
| **Delta** | **−3.64 s (−100%)** | **−7.89 s** | **−$0.000444** | **−$0.008886** |

**Cache hit rate:** **72%** (87 of 120) on a repeated-question workload I defined: Zipf-like
popularity over the 28 eval questions; 60% exact wording, 25% trivial variants, 15% paraphrases;
10% follow-ups. Every miss is explained:
- first time a question was asked: 15%;
- follow-ups, which are never cached by design: 9%;
- paraphrases, which only a semantic cache could catch: 3%.

LLM spend on that workload: **$0.0181 with the cache vs $0.0657 without (−72%)**. Applied to the
Task 5 projection, $12.99/month at 1,000 questions/day would become about **$3.60/month**, *if*
real traffic repeats as much as this workload does ([`evidence/workload_hit_rate.md`](task_06_caching/evidence/workload_hit_rate.md)).

**Was it worth it?** One honest paragraph — including the cases where caching is
the wrong answer:

> **Yes, the answer cache, because what it saves is the whole pipeline.** A hit replaces 9–25 LLM
> calls and 2–8 s with a sub-millisecond lookup, so savings track the hit rate almost one to one
> (72% → −72% spend). The pipeline is so expensive that even modest repetition pays. But the number
> is only as good as the workload: 28 questions repeated 120 times is kinder than 200 employees
> phrasing things their own way, and **paraphrases and follow-ups never hit**. Caching is the
> **wrong answer** in three places:
> 1. **Follow-ups.** "Can I carry it over?" means something different in every conversation, so
>    only a session's first question is cacheable.
> 2. **False refusals.** In the cold/warm run the Figma question's false refusal (a 4B fact-check
>    error) was cached and re-served. Refusals therefore get a 5-minute TTL instead of an hour, and
>    any document change invalidates everything.
> 3. **Semantic matching on this corpus.** "rover speed *with* a load" vs "*without* a load" scores
>    0.977 cosine (1.8 vs 2.2 m/s), higher than every true paraphrase. "vacation days" vs "PTO"
>    scores 0.186.
>
> The **embedding cache** is a different story. Locally it barely matters: queries rarely repeat
> once the answer cache absorbs repeats (5 hits / 52 misses), and the index is already persisted.
> Its job is rebuilds: a full `--rebuild` went from 20 embeddings (0.68 s) to **0** (0.004 s).
> With a paid embedding API, that's every rebuild's embedding bill.

---

## Task 3 — Streaming vs non-streaming, as the user experiences it

Measured 2026-11-16, 20 answerable eval questions, one at a time, local Ollama
`qwen3.5:4b` (details and raw rows: `RESULTS.md` Task 3). p50 / p95.

| | Time to first token | Time to complete | Perceived improvement |
|---|---:|---:|---|
| `POST /chat` | n/a (whole answer at 3.00 s / 7.93 s) | 3.00 s / 7.93 s | baseline: 3 s of silence, then the answer |
| `POST /chat/stream` | 1.22 s / 3.29 s (first status line: 3 ms) | 3.02 s / 7.95 s (`done`) | First words 2.5× sooner, and a status line per graph step from 3 ms. The total is unchanged (+20 ms p50, within noise), and the cost is identical: the same graph, the same LLM calls. Downside: 4 of 20 answers streamed a draft that the fact-check then retracted |

---

## Task 2 — Cold vs warm start

Measured in Week 2 Task 1 (2026-11-16), `python capstone_internal_docs_assistant/app.py ingest`
run from an unrelated directory, local `all-MiniLM-L6-v2` embeddings. "Wall clock" is the whole
process; the index step itself is in brackets.

| | Wall clock | Embedding calls |
|---|---:|---:|
| Cold start (index built) | 15.47 s (index step 0.72 s) | 20 chunks embedded |
| Warm start (index loaded) | 6.71 s (index step 0.02 s) | 0 |

Most of both wall clocks is Python imports and loading the embedding model, not embedding:
20 chunks with a local model is cheap. With a paid embedding API, the cold-start cost is
these 20 chunks once per rebuild, and $0 on every warm start.

---

## Task 8 — Worst case for a single request

Logical retries (`MAX_RETRIES`) × transport retries (`LLM_MAX_RETRIES`) × LLM calls per path.
Design: [`task_08_resilience/RESILIENCE.md`](task_08_resilience/RESILIENCE.md).

**Logical worst path** (no provider failure, the documents just never satisfy the graders):
a follow-up question, every passage graded, every draft rejected, so it runs all 3 rounds
(1 + `MAX_RETRIES`=2 rewrites):

| Step | Calls |
|---|---:|
| `contextualize` (follow-ups only) | 1 |
| `route_question` | 1 |
| per round: `grade_documents` (`MAX_DOCS_TO_GRADE`=6) + `generate` (1) + `grade_generation` (grounded: 1, re-asked once if the verdict is unparseable = 2; addresses: 1) | 6 + 1 + 3 = 10 |
| × 3 rounds | 30 |
| `rewrite_query` × 2 | 2 |
| **Total logical calls** | **34** |

Every call can then take up to 1 + `LLM_MAX_RETRIES` = **3 transport attempts**:
34 × 3 = **102 attempts uncapped**, each up to 30 s, so ≈ 51 min of waiting in theory.
That is why the **total** is capped per request: `MAX_LLM_CALLS_PER_REQUEST=40` attempts
(the 34-call logical path plus a few retries) and `REQUEST_TIMEOUT_SECONDS=60`.

| | Value |
|---|---:|
| Max LLM calls in one request (show the arithmetic) | **40 attempts** (hard cap). Uncapped it would be 34 logical × 3 transport = 102. Observed max in the Task 5 cost run: 25 calls |
| Worst-case cost of one request | **≤ $0.0041** = 40 attempts × $0.000102 (the most expensive call measured: `generate`, ~400 in / 70 out tokens, gpt-4o-mini prices), counting every attempt as billed (a timed-out call may still be billed). The 34-call logical path without failures ≈ $0.0016. Mean question: $0.000433, so the worst case is **~9.5× the mean** |
| Worst-case latency (with timeouts) | **≈ 60 s** (`REQUEST_TIMEOUT_SECONDS`): every attempt's timeout is `min(30 s, time left)`. Measured: hanging provider → 504 at **61.8 s** (2 × 30 s attempts + retrieval/overhead). Down provider: 503 in 6.3 s, then **18 ms** while the circuit is open |

What a bad day costs at 1,000 questions/day: if *every* question hit the cap, $4.10/day
instead of $0.43/day. That's 9.5× the bill, but bounded, and the circuit breaker stops the
retries after 5 consecutive failures, so a provider outage costs ~7 attempts once per 30 s,
not 40 per question.

---

## Task 8 stretch — Load test (50 requests over 30 s)

Answer cache off (every request runs the full graph), local GPU Ollama `qwen3.5:4b`, one
session per request, questions cycling through the 24 answerable eval questions.
[Evidence](task_08_resilience/evidence/load_test.md).

| p50 | p95 | Error rate | Point where it degrades |
|---:|---:|---:|---|
| 63.6 s (successful requests) | 77.3 s | **70%** (35/50: 24 `request_timeout`, 11 `verification_unavailable`) | **request #3**, sent 1.2 s in (~2.5 req/s offered so far): `request_timeout` after 60.8 s. Requests 1–2: 4.2 s, 12.9 s |

The model server answers one call at a time: ~3.3 s and ~10 calls per question, so
**~0.3 questions/s (~18/min) capacity**. 1.67 req/s is 5.5× that. Calls from all in-flight
requests interleave, so overload slows *every* request, and they hit the 60 s deadline
together. Served throughput fell to 0.14 answers/s, below capacity, because abandoned calls
still occupy the GPU. The fact-check fails closed under the deadline (11 ×
`verification_unavailable`), so no unchecked answer went out.

**Can we roll out to 200 people?** 1,000 questions/day. Even with 20% in the peak hour,
that's 0.06 questions/s, a fifth of capacity, and the answer cache takes most repeats. So
yes for steady load on this setup. Not for bursts above ~0.3 questions/s. The first fix is
admission control (cap in-flight graphs at the model server's concurrency, 503 +
`Retry-After` immediately beyond a short queue). A hosted provider moves the limit to its
rate limits and to cost.

---

## Running log — cost impact per PR

Fill one row per merged PR. "No change" is a valid and useful entry.

| PR | Change | Latency impact | Cost impact | Notes |
|---|---|---|---|---|
| #1 | Task 1 closeout | none per question (one log line at startup); warm start 6.7 s vs cold 15.5 s | none (Task 6 harness now embeds the corpus 1× instead of 4×: 34.9 s → 35.1 s locally, i.e. no measurable saving with local embeddings; 3 fewer embedding passes per run with a paid API) | timed by hand |
| #2 | Task 2 test harness | n/a (no app behaviour change) | n/a | `make check` 1.3–1.9 s, $0, runs on every PR; `make check-live` 71 s, 9 questions, $0 on local Ollama |
| #3 | Task 3 service API | per question: none (`/chat` p50 3.00 s, `/chat/stream` `done` p50 3.02 s; HTTP layer ≈ 0.4 ms, see `/healthz`). Time to first token 1.22 s instead of 3.00 s. Startup 8–11 s, still no re-embed on restart. 5 concurrent requests: per-request p50 2.5 s → 14.2 s (the Ollama queue) | none: same graph, same LLM calls per question ($0 locally, unchanged with a paid provider). Benchmark runs: 41 questions + 11 for the concurrency test, $0 on local Ollama | timed with `make bench-api`; per-node timing comes from the stream's `status` events |
| #4 | Task 4 containerize | per question: none (same graph; 2.2–2.3 s for "sick days" in the container vs 2.05 s for the same question in Task 3's local benchmark). Startup: full image ready in 9–10 s (torch import), slim image 1.2 s. First `up` on a new volume embeds 20 chunks once (0.34 s) | none per question. Same LLM calls; settings defaults equal the old hardcoded values, so the index wasn't invalidated. Gotcha: a thinking model behind an OpenAI-compatible URL costs ~1,000 extra hidden tokens per call unless `OPENAI_REASONING_EFFORT=none` | images: 489 MB download (full), 241 MB (slim). Clean build 157 s; code-only rebuild 3.6 s. Verification run: ~10 questions on local Ollama, $0 |
| #5 | Task 5 observability | **+0.43 ms per request** (callbacks on every node and LLM call + one log line + metrics; median over 400 runs with an instant fake model, so ≈0.01% of a 3.3 s answer). Startup: one extra LangSmith call to build trace links | none: no extra LLM calls. Now **measured**: $0.000433/question, $12.99/month at 1,000/day (gpt-4o-mini prices) | verification: 2 × 28-question cost reports, 2 × 28-example evals (judge included) and ~6 demo requests, all on local Ollama, $0 |
| #6 | Task 6 caching | **hit: <1 ms in-process / 1.8 ms over HTTP instead of 3.6 s mean (7.9 s p95)**. Miss: unchanged (one hash + dict lookup). Index rebuild with a warm embedding cache: 0.68 s → 0.004 s | **hit: $0 instead of $0.000444**. Workload: −72% spend at a 72% hit rate (~$3.60/month instead of $12.99 at 1,000/day, if traffic repeats like the workload). Optional pre-warm costs ~32 s of LLM work per restart for 10 questions | verification: cold/warm (40 requests), workload (120), pre-warm (30), API demo (3); local Ollama, $0 |
| #7 | Task 7 eval gate | none at runtime (CI only). **Fast CI: 18–21 s per PR**, free. **Eval CI: ~5.5 min** on the self-hosted GPU runner, for `run-eval`-labelled PRs and nightly | **$0 per eval run** (local model on the laptop: ~510 pipeline LLM calls + ~100 judge calls per run). On gpt-4o-mini pricing the 38 pipeline runs would be ~$0.018 + judge calls. GitHub minutes: fast tier only (~0.35 min/PR) | the free GitHub CPU runner was tried first: 11/38 examples in 67 min, then the runner crashed. Nightly there would have needed ~75 h/month of the 33 free |
| #8 | Task 8 resilience | **none on the happy path**: **+24 µs per LLM call** (timeout thread hand-off + retry loop; median of 3,000 calls on an instant fake), so ≈ +0.24 ms per 10-call question (0.007% of 3.3 s); the input guard is one regex pass. On failure: **bounded** at 60 s per request (was unbounded: a hanging provider held the request ~5 min, the client's timeout); provider down → 503 in 6.3 s, then 18 ms with the circuit open. Load (50 req/30 s, cache off): p50 63.6 s, 70% errors, degrades from request #3 | none per question on the happy path (same calls). Failure paths: ≤ 40 attempts per request (≤ $0.0041, ~9.5× the $0.000433 mean) instead of up to 102. Degraded answers are not cached (a cache miss next time). Over-refusal: injection-like real questions are refused by design (#6) | retries add cost on failure paths. Verification: ~25 live requests (provider down/hang, 2 × 7 injections × 2 runs, 22 rate-limit), 50-request load test; local Ollama, $0 |

---

## The question to be able to answer on Friday

> *"If Northwind rolls this out to 200 employees asking 5 questions a day, what
> does it cost per month, and what's the first thing you'd optimise?"*

>
