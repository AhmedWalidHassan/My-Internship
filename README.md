# Northwind Internal Docs Assistant — AI Engineering Internship

A RAG assistant that answers questions about Northwind Robotics' internal documents
(HR policies, IT help, product specs) with citations. It refuses when the documents
don't contain the answer, and it remembers the conversation.

| Folder | What's in it |
|---|---|
| [`app/`](app/) | The **HTTP service** (FastAPI, streaming, sessions) and the Streamlit UI that calls it. See [`app/README.md`](app/README.md) for endpoints and the streaming protocol |
| [`scripts/`](scripts/) | Clients of the service, e.g. the latency benchmark |
| [`week1/`](week1/) | Tasks 1–8 and the capstone: [`week1/capstone_internal_docs_assistant/`](week1/capstone_internal_docs_assistant/), where the RAG logic (index, graph, memory) lives |
| [`week2/`](week2/) | Week 2 briefs, plus [`RESULTS.md`](week2/RESULTS.md) and [`COST.md`](week2/COST.md), where every measurement goes |
| [`tests/`](tests/) | The test suite (fast tier and live tier) |
| [`week3/`](week3/) | Week 3 briefs, the 190-document corpus (`week3/corpus/`, **the default `DATA_DIR` since Week 3 Task 2**), the eval set v3 (`week3/eval/eval_v3.jsonl`), and [`RESULTS.md`](week3/RESULTS.md) / [`COST.md`](week3/COST.md) |

## Setup

```bash
cd week1
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r ../week2/requirements.txt
cp .env.example .env        # pick a provider; see the capstone README
cd ..
```

The Makefile uses `week1/.venv` automatically when it exists (override with `make check PY=python3`).

**Configuration** is one file, `week1/.env`, read into a typed, validated settings object
([`week1/common/settings.py`](week1/common/settings.py)): provider, model, base URL, retriever `k`,
chunking, index path, API host and port. Switching provider is an `.env` edit; see
[`week1/.env.example`](week1/.env.example) for every setting and a block per provider.

## Commands (run from the repo root)

| Command | What it does | Needs |
|---|---|---|
| `make check` | Lint (ruff) plus the **fast** tests: graph wiring, prompts, memory wiring, index persistence the HTTP API (all endpoints, streaming, session isolation, error shape), and failure injection (provider down or hanging, every degradation rule, rate limit, injection guard), with a fake model. 4–5 s of tests (≈5.5 s wall). Run before every PR. | Nothing: no API key, no network (the tests block both) |
| `make check-live` | The **live** golden-path tests through the real app: cited answer, refusals, two-turn follow-up, session isolation, warm start, rewrite loop, real token streaming through the API. About 60 s on local Ollama. | `week1/.env` and the model server running (e.g. `ollama serve`) |
| `make up` / `make down` | **API + UI in Docker** (one command, from a clean checkout; the index lives in a named volume). `API_VARIANT=slim make up` for the 575 MB image. See [`week2/task_04_containerize/DEPLOY.md`](week2/task_04_containerize/DEPLOY.md) | Docker and `week1/.env` |
| `make run` | Start the API on http://127.0.0.1:8000 (OpenAPI docs at `/docs`). Host and port come from `API_HOST` / `API_PORT` | same as live |
| `make run-ui` | Start the Streamlit chat UI, which talks to the API over HTTP (start `make run` first) | a running API |
| `make bench-api` | p50/p95 latency of `/chat` and `/chat/stream` over 20 questions | a running API |
| `make cost` | Runs the eval set through the service code and prints latency, LLM calls, tokens and cost per question, per graph node and per node path, plus the monthly projection ([Task 5](week2/task_05_observability/OBSERVABILITY.md)) | same as live |
| `make find-trace RID=<request_id>` | The LangSmith trace of a request, from the `request_id` in its log line | a LangSmith key |
| `make eval` | The Week 3 eval: dataset v3, **dev** split (70), full pipeline, judged by `JUDGE_MODEL` (default `gemma3:4b`, never the generator). Per-category correctness, groundedness and the deterministic score; results in `week3/eval/runs/dev/` ([Week 3 Task 2](week3/task_02_eval_at_scale/RUN.md)) | same as live, plus the judge model pulled |
| `make eval-retrieval` | Retrieval only on dev: recall@1/3/5/10 and MRR by category, no LLM call (~8 s, $0) | the embedding model |
| `make eval-test` | The frozen **test** split (30). Run only to confirm a decision; commit the run file in `week3/eval/runs/test/` | same as `make eval` |
| `make eval-gate` | `make eval`, then the gate against `eval_baseline.json` (dataset v3, dev). What CI's eval job runs ([Task 7](week2/task_07_eval_gate/EVAL_GATE.md)) | same as `make eval` |
| `make ingest` / `make ingest-full` | Update / rebuild the index from `DATA_DIR` (logs every document it can't parse yet) | the embedding model |
| `make cache-bench MODE=cold-warm\|workload\|prewarm` | Proves the answer cache's savings: cold vs warm, hit rate on a defined workload, startup pre-warm ([Task 6](week2/task_06_caching/CACHING.md)) | same as live |
| `make injection-test` | 7 prompt-injection attempts against the running API, judged automatically: no system-prompt text leaked, no out-of-scope answer ([Task 8](week2/task_08_resilience/RESILIENCE.md)) | a running API |
| `make load-test N=50 SECONDS=30` | Load test: p50/p95, error rate by code, where it degrades. Start the API with `CACHE_ENABLED=false` to load the real graph ([Task 8](week2/task_08_resilience/RESILIENCE.md)) | a running API |
| `make run-ui-capstone` | The Week 1 Streamlit UI that runs the graph in-process (kept for reference) | same as live |
| `make eval-capstone` | The Week 1 LangSmith evaluation of the capstone's 28 built-in examples (was `make eval`) | same as live, plus a LangSmith key |
| `make test-durations` | The fast tier with its 5 slowest tests listed | nothing |

**CI** ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)):
- `fast-checks` (lint + fast tests, ~20 s) runs on every PR.
- `eval-gate` (the 38-example eval vs the committed baseline, ~5.5 min) runs nightly, on demand,
  and on PRs labelled **`run-eval`**: add that label to PRs that touch prompts, retrieval or the
  graph. It runs on a self-hosted runner on the maintainer's laptop GPU, and only for the owner's
  events; see [EVAL_GATE.md](week2/task_07_eval_gate/EVAL_GATE.md).

The regression guard is `tests/test_graph_structure.py::test_app_graph_has_contextualize_node`.
It fails if the app is ever built from a graph without the conversation-history node
(for example Task 8's graph), which would quietly switch off multi-turn memory.
