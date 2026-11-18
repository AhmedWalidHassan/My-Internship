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
| `week3/` | Week 3 briefs and corpus |

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
| `make check` | Lint (ruff) plus the **fast** tests: graph wiring, prompts, memory wiring, index persistence and the HTTP API (all endpoints, streaming, session isolation, error shape), with a fake model. Under 5 s. Run before every PR. | Nothing: no API key, no network (the tests block both) |
| `make check-live` | The **live** golden-path tests through the real app: cited answer, refusals, two-turn follow-up, session isolation, warm start, rewrite loop, real token streaming through the API. About 60 s on local Ollama. | `week1/.env` and the model server running (e.g. `ollama serve`) |
| `make up` / `make down` | **API + UI in Docker** (one command, from a clean checkout; the index lives in a named volume). `API_VARIANT=slim make up` for the 575 MB image. See [`week2/task_04_containerize/DEPLOY.md`](week2/task_04_containerize/DEPLOY.md) | Docker and `week1/.env` |
| `make run` | Start the API on http://127.0.0.1:8000 (OpenAPI docs at `/docs`). Host and port come from `API_HOST` / `API_PORT` | same as live |
| `make run-ui` | Start the Streamlit chat UI, which talks to the API over HTTP (start `make run` first) | a running API |
| `make bench-api` | p50/p95 latency of `/chat` and `/chat/stream` over 20 questions | a running API |
| `make cost` | Runs the eval set through the service code and prints latency, LLM calls, tokens and cost per question, per graph node and per node path, plus the monthly projection ([Task 5](week2/task_05_observability/OBSERVABILITY.md)) | same as live |
| `make find-trace RID=<request_id>` | The LangSmith trace of a request, from the `request_id` in its log line | a LangSmith key |
| `make eval-gate` | The 38-example eval on the real model, then the gate against `eval_baseline.json` (what CI's eval job runs) ([Task 7](week2/task_07_eval_gate/EVAL_GATE.md)) | same as live |
| `make cache-bench MODE=cold-warm\|workload\|prewarm` | Proves the answer cache's savings: cold vs warm, hit rate on a defined workload, startup pre-warm ([Task 6](week2/task_06_caching/CACHING.md)) | same as live |
| `make run-ui-capstone` | The Week 1 Streamlit UI that runs the graph in-process (kept for reference) | same as live |
| `make eval` | Run the LangSmith evaluation and update `EVAL_RESULTS.md` | same as live, plus a LangSmith key |
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
