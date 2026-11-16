# Week 2 — Cost & Latency

> **Standing rule 3:** every PR states what it cost. This file is where those
> numbers accumulate. Measure over the same 20-example eval set every time so the
> rows are comparable.

Model / provider used for these figures: `___`
Pricing assumed: `$___ / 1K input tokens`, `$___ / 1K output tokens`

---

## Baseline — the agentic graph as it stands after Task 1

| Metric | Value |
|---|---:|
| Mean latency per question | |
| p95 latency per question | |
| Mean LLM calls per question | |
| Mean tokens per question (in / out) | / |
| Mean cost per question | |
| **Projected monthly cost @ 1,000 questions/day** | |

### Cost by node

Which node is actually spending the money? `grade_documents` calls the LLM once
*per retrieved document*, so start by checking whether it dominates.

| Node | Calls per question | Tokens | Cost | % of total |
|---|---:|---:|---:|---:|
| `contextualize` (or your history node) | | | | |
| `route_question` | | | | |
| `grade_documents` | | | | |
| `rewrite_query` | | | | |
| `generate` | | | | |
| `grade_generation` | | | | |

**Most expensive node:** `___`

**One concrete idea for reducing it:**

>

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

| | Time to first token | Time to complete | Perceived improvement |
|---|---:|---:|---|
| `POST /chat` | n/a | | |
| `POST /chat/stream` | | | |

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
| #3 | Task 3 service API | | | |
| #4 | Task 4 containerize | | | |
| #5 | Task 5 observability | | | instrumentation overhead? |
| #6 | Task 6 caching | | | |
| #7 | Task 7 eval gate | n/a | | CI run cost per PR |
| #8 | Task 8 resilience | | | retries add cost on failure paths |

---

## The question to be able to answer on Friday

> *"If Northwind rolls this out to 200 employees asking 5 questions a day, what
> does it cost per month, and what's the first thing you'd optimise?"*

>
