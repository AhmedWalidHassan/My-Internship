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

| | Mean latency | p95 latency | Mean cost / question | Total run cost |
|---|---:|---:|---:|---:|
| Cold cache (no reuse) | | | | |
| Warm cache (second run) | | | | |
| **Delta** | | | | |

**Cache hit rate:** `___`

**Was it worth it?** One honest paragraph — including the cases where caching is
the wrong answer:

>

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

| | Value |
|---|---:|
| Max LLM calls in one request (show the arithmetic) | |
| Worst-case cost of one request | |
| Worst-case latency (with timeouts) | |

---

## Task 8 stretch — Load test (50 requests over 30 s)

| p50 | p95 | Error rate | Point where it degrades |
|---:|---:|---:|---|
| | | | |

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
| #6 | Task 6 caching | | | |
| #7 | Task 7 eval gate | n/a | | CI run cost per PR |
| #8 | Task 8 resilience | | | retries add cost on failure paths |

---

## The question to be able to answer on Friday

> *"If Northwind rolls this out to 200 employees asking 5 questions a day, what
> does it cost per month, and what's the first thing you'd optimise?"*

>
