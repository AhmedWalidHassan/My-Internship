# Observability: traces, tokens, cost, latency (Week 2, Task 5)

The brief is in [README.md](README.md). This page covers what was built, how to use it,
what it measured, and the evidence for each "Done when…" item. The numbers themselves live in
[`week2/COST.md`](../COST.md) (cost and latency) and [`week2/RESULTS.md`](../RESULTS.md#task-5--observability)
(node paths and the rewrite-loop finding).

## Where things are

The README places the logging, per-node timing, LangSmith tags and `/metrics` in the running
service, so that code is in the product. Everything else is in this folder.

| What | Where |
|---|---|
| Per-node telemetry, the request log line, metrics, trace links | [`app/observability.py`](../../app/observability.py) |
| One record per request (ok / error / client disconnect) | [`app/service.py`](../../app/service.py) `ChatService.events()` |
| `GET /metrics`, structlog setup, trace-link resolution at startup | [`app/main.py`](../../app/main.py) |
| Pricing (`COST_PER_1K_*_TOKENS`) and `MAX_DOCS_TO_GRADE` as settings | [`week1/common/settings.py`](../../week1/common/settings.py) |
| Chunk ids and per-run callbacks in the graph runner | capstone `Assistant.stream()` |
| **Cost report** (`make cost`) | [`scripts/cost_report.py`](scripts/cost_report.py) (the provided skeleton, filled in) |
| **Log line → trace lookup** (`make find-trace RID=…`) | [`scripts/find_trace.py`](scripts/find_trace.py) |
| Evidence (reports, log lines, metrics, experiment) | [`evidence/`](evidence/) |
| Tests | [`tests/test_observability.py`](../../tests/test_observability.py) (10 fast tests) |

## How it works

**Per-node timing and cost, without wrapping each node by hand.** `RunTelemetry` is a LangChain
callback handler, created per request and passed into that graph run. LangGraph tags every run
inside the graph with `langgraph_node`. So:
- **graph nodes** are the chain runs whose name equals their tag, and their start/end gives each
  node's wall time;
- **LLM calls** (`on_chat_model_start` → `on_llm_end`) are attributed to the node they ran in,
  with tokens from the provider's own usage report (`usage_metadata`, or the older
  `llm_output["token_usage"]`). A provider that reports nothing is counted as
  `llm_calls_without_usage`: the report degrades rather than crashes.

Because the graph code isn't wrapped, a node added tomorrow is measured too. A test cross-checks
the attribution against the prompts the fake model actually received: grading calls equal
grading prompts, node by node.

**One log line per request.** `ChatService.events()` is the single place the graph runs for both
`/chat` and `/chat/stream`. It reports exactly one record from a `finally`, so a request that
fails, or a stream the client abandons, still logs once (`status`: `ok` / `error` /
`cancelled`). structlog renders it as one JSON object per line on stdout (the request line); the
operational logs stay on stderr.

**From a log line to the trace.** The API passes `trace_id` to LangGraph as the run id, so
**`trace_id` is the LangSmith root-run id**, and `request_id` / `session_id` are on the run as
metadata. At startup the API looks up the project's id once and puts a ready-made `trace_url`
in every line. Three ways in, fastest first:
1. click `trace_url`;
2. paste `trace_id` (a direct read);
3. `make find-trace RID=<request_id>`, a metadata search for when all you have is the
   `X-Request-ID` from a client or load balancer.

**Metrics.** `GET /metrics` is Prometheus text. Counters (all-time):
- requests by endpoint and status;
- refusals, rewrite retries and cache hits;
- LLM calls and node seconds, both by node;
- tokens in and out;
- estimated USD;
- a latency histogram.

Derived gauges over the last 1,000 requests: p50/p95 latency, refusal rate, mean retries,
cache-hit rate. `/metrics` never calls the model.

## One request → one log line

`POST /chat {"question": "How many sick days do I get per year?", "session_id": "demo-session-1"}`
with `X-Request-ID: demo-req-0001` (pretty-printed here; on stdout it's one line):

```json
{"request_id": "demo-req-0001", "session_id": "demo-session-1",
 "trace_id": "334a738a-8cf9-47c5-90a8-839f477cd0f0", "endpoint": "chat", "status": "ok",
 "route": "retrieve",
 "node_path": ["contextualize", "route_question", "retrieve", "grade_documents", "generate", "grade_generation"],
 "retries": 0, "latency_ms": 4759, "tokens_in": 1938, "tokens_out": 80, "estimated_cost_usd": 0.000339,
 "refused": false, "cache_hit": false, "llm_calls": 10, "model": "ollama:qwen3.5:4b",
 "per_node": {
   "contextualize":    {"runs": 1, "ms": 0.3,    "llm_calls": 0, "llm_ms": 0.0,    "tokens_in": 0,    "tokens_out": 0},
   "route_question":   {"runs": 1, "ms": 413.8,  "llm_calls": 1, "llm_ms": 412.2,  "tokens_in": 148,  "tokens_out": 5},
   "retrieve":         {"runs": 1, "ms": 974.1,  "llm_calls": 0, "llm_ms": 0.0,    "tokens_in": 0,    "tokens_out": 0},
   "grade_documents":  {"runs": 1, "ms": 2002.9, "llm_calls": 6, "llm_ms": 1998.2, "tokens_in": 1009, "tokens_out": 12},
   "generate":         {"runs": 1, "ms": 456.8,  "llm_calls": 1, "llm_ms": 455.9,  "tokens_in": 370,  "tokens_out": 19},
   "grade_generation": {"runs": 1, "ms": 901.2,  "llm_calls": 2, "llm_ms": 899.4,  "tokens_in": 411,  "tokens_out": 44}},
 "retrieved_ids": ["employee_handbook.md::2", "employee_handbook.md::1", "it_faq.md::3", "it_faq.md::0",
                   "hr_policies.md::3", "employee_handbook.md::3"],
 "kept_ids": ["employee_handbook.md::2", "employee_handbook.md::1"],
 "trace_url": "https://smith.langchain.com/o/d25a7522-…/projects/p/d9b175d7-…/r/334a738a-8cf9-47c5-90a8-839f477cd0f0?poll=true",
 "event": "request", "level": "info", "ts": "2026-11-16T09:19:04.760271Z"}
```

Every field the brief requires is there, plus:
- `ttft_ms` on `/chat/stream`;
- `error` when `status` isn't `ok`;
- `retrieved_ids` / `kept_ids`, the stretch item: tell **retrieval** drift from **generation**
  drift when a score moves.

The question and answer text are **not** logged: the trace has them, behind LangSmith's access control.

**Finding the trace from that line** ([`evidence/find_trace.txt`](evidence/find_trace.txt)):

```
$ make find-trace RID=demo-req-0001
found in 2.45 s via request_id metadata search
  run:        northwind_assistant  (root: True)  status: success
  trace_id:   334a738a-8cf9-47c5-90a8-839f477cd0f0
  request_id: demo-req-0001   session_id: demo-session-1
  url:        https://smith.langchain.com/o/…/r/334a738a-8cf9-47c5-90a8-839f477cd0f0?poll=true
```

## What the data says

Full report: [`evidence/cost_report.md`](evidence/cost_report.md); every request record:
[`evidence/cost_report.json`](evidence/cost_report.json).

- **12.8 LLM calls per question on average** (9.8 when answered first time, 25 at worst),
  **$0.000433 per question at gpt-4o-mini prices → $12.99/month at 1,000 questions/day.** Mean
  latency 3.28 s, p95 6.89 s.
- **`grade_documents` is 52% of spend** (8.3 calls per question: one per passage, up to 6 per
  search, repeated after every rewrite). `grade_generation` is the biggest share of *time* (35%).
- **The rewrite loop fires on 29% of questions, mostly because the grader is too strict.** 11 of 14
  rewrites were the doc grader rejecting every passage. In 3 of those 6 answerable cases, the
  answer chunk was in the first search and the fallback, not the rewrite, saved it. Only the
  meal-limit question was a real retrieval rescue. Details: [RESULTS.md](../RESULTS.md#task-5--observability).
- **Refusing is the most expensive thing the system does:** "What is the CEO's home address?"
  takes **23 LLM calls** (18 of them grading) to say "I don't know". A normal answer takes 10.

**Stretch: grade 2 passages instead of 6** ([`evidence/grading_experiment.md`](evidence/grading_experiment.md)).
`MAX_DOCS_TO_GRADE` is now a setting, so the experiment changed nothing but the environment.

| | Grade 6 (default) | Grade 2 |
|---|---:|---:|
| Correctness / groundedness / retrieval hit | **0.96** / 0.96 / 1.00 | **0.82** / 0.96 / 1.00 |
| LLM calls per question | 12.8 | 7.6 |
| Cost per question · per month at 1,000/day | $0.000433 · $12.99 | $0.000278 · $8.33 (**−36%**) |
| Mean / p95 latency | 3.28 s / 6.89 s | 2.46 s / 3.86 s |
| Refusal rate (4/28 are out of scope) | 18% | 29% |

36% cheaper and 25% faster, but **1 in 7 answers lost**:
- three answerable questions became refusals (R2 weight, R2 outdoors, meal limit) and one
  answer turned incorrect;
- retrieval still found every answer; the right chunk was just outside the top 2.

Not worth it. The cheaper fix is to grade the same 6 passages in **one** call
([COST.md](../COST.md), unmeasured estimate −22%).

## Evidence for "Done when…"

| Check | Result | Evidence |
|---|---|---|
| One request → one structured line with every field | 4 demo requests (chat, stream follow-up, direct refusal, rewrite-loop refusal) → 4 lines. Tests assert exactly one line per request, including failed requests | [`evidence/request_log_lines.jsonl`](evidence/request_log_lines.jsonl), `tests/test_observability.py` |
| `request_id` → LangSmith trace in < 10 s | `trace_url` in the line: one click. `make find-trace RID=…`: 1.6–2.5 s over 4 lookups (at most 3.2 s with Python startup) | [`evidence/find_trace.txt`](evidence/find_trace.txt) |
| `COST.md` baseline + monthly projection | mean 3.28 s, p95 6.89 s, 12.8 calls, 2,381 / 127 tokens, $0.000433, **$12.99/month** | [`evidence/cost_report.md`](evidence/cost_report.md) |
| Most expensive node + one idea | `grade_documents`, 52%. Idea: one batched grading call per search. Measured counter-example: grade fewer passages | `COST.md` |
| Node-path distribution in `RESULTS.md` | 64% straight through, 7% one loop, 21% two loops, 7% direct | `RESULTS.md` |
| `/metrics` returns live counters | after 4 requests: totals by endpoint, refusal rate 0.5, mean retries 0.5, p50/p95, LLM calls by node; also verified inside the Docker container | [`evidence/metrics_sample.txt`](evidence/metrics_sample.txt) |

**Overhead:** +0.43 ms per request (median over 400 runs with an instant fake model), about
0.01% of a real answer.

## Caveats

- **"Cost" is a projection.** The model that ran is local (`$0`); token counts are qwen's own,
  priced at gpt-4o-mini rates. A different tokenizer counts somewhat differently, so treat the
  dollar figures as order-of-magnitude until measured on the real provider. Set
  `COST_PER_1K_*_TOKENS` to your model's price.
- **Metrics are per process.** Like sessions, each uvicorn worker has its own registry;
  Prometheus would scrape and sum them per instance.
- **The eval set has no follow-ups**, so `contextualize` shows $0. In real conversations it adds one
  short call per follow-up.
