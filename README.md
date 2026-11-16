# Northwind Internal Docs Assistant — AI Engineering Internship

A RAG assistant that answers questions about Northwind Robotics' internal documents
(HR policies, IT help, product specs) with citations. It refuses when the documents
don't contain the answer, and it remembers the conversation.

| Folder | What's in it |
|---|---|
| [`week1/`](week1/) | Tasks 1–8 and the capstone: [`week1/capstone_internal_docs_assistant/`](week1/capstone_internal_docs_assistant/) (see its README for **how to run the app**) |
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

## Commands (run from the repo root)

| Command | What it does | Needs |
|---|---|---|
| `make check` | Lint (ruff) plus the **fast** tests: graph wiring, prompts, memory wiring and index persistence, with a fake model. Under 5 s. Run before every PR. | Nothing: no API key, no network (the tests block both) |
| `make check-live` | The **live** golden-path tests through the real app: cited answer, refusals, two-turn follow-up, session isolation, warm start, rewrite loop. About 70 s on local Ollama. | `week1/.env` and the model server running (e.g. `ollama serve`) |
| `make run-ui` | Start the Streamlit chat UI | same as live |
| `make eval` | Run the LangSmith evaluation and update `EVAL_RESULTS.md` | same as live, plus a LangSmith key |
| `make test-durations` | The fast tier with its 5 slowest tests listed | nothing |

The regression guard is `tests/test_graph_structure.py::test_app_graph_has_contextualize_node`.
It fails if the app is ever built from a graph without the conversation-history node
(for example Task 8's graph), which would quietly switch off multi-turn memory.
