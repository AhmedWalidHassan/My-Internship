# ⭐ Capstone — Northwind Internal Docs Assistant

**Scaffolding:** 🔴 Spec-only. You architect and build the whole thing, reusing
everything from Tasks 1–8. A thin app skeleton is provided so you don't burn time
on plumbing; the RAG brain is yours to build.
**Time budget:** ~2 days (the back half of Week 1). Demo on Friday.

---

## How to run

Everything lives in one file, [`app.py`](app.py): ingestion, the LangGraph graph,
memory, the Streamlit UI, a CLI and the eval. Every path in it is built from
`Path(__file__)`, so the commands below work from **any** working directory. They
are written relative to `week1/`.

### 1. Install

```bash
cd week1
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # then edit .env
```

### 2. Environment variables (`week1/.env`)

| Variable | Required? | Meaning |
|---|---|---|
| `LLM_PROVIDER` | yes | `openai` \| `groq` \| `ollama` \| `huggingface` |
| `EMBEDDING_PROVIDER` | yes | `openai`, or `ollama`/`groq`/`huggingface`, which all use the local `HF_EMBED_MODEL` (default `all-MiniLM-L6-v2`) |
| `OPENAI_API_KEY` / `GROQ_API_KEY` / `HUGGINGFACEHUB_API_TOKEN` | for that provider | Ollama needs no key |
| `OPENAI_MODEL` / `GROQ_MODEL` / `OLLAMA_MODEL` | no | model name (defaults in `common/utils.py`) |
| `OPENAI_BASE_URL` / `OLLAMA_BASE_URL` | no | endpoint override; unset = provider default |
| `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`, `LANGCHAIN_PROJECT` | for tracing and `eval` | every question becomes a `northwind_assistant` trace |
| `LOG_LEVEL` | no | default `INFO` |

The reported numbers were produced fully locally with:

```bash
ollama serve &                 # in another terminal
ollama pull qwen3.5:4b
# .env: LLM_PROVIDER=ollama  EMBEDDING_PROVIDER=ollama  OLLAMA_MODEL=qwen3.5:4b
python common/utils.py         # smoke test: prints a one-line reply
```

### 3. Ingest (build the index once)

```bash
python capstone_internal_docs_assistant/app.py ingest            # build or update
python capstone_internal_docs_assistant/app.py ingest --rebuild  # force a full re-embed
```

The index is saved to `capstone_internal_docs_assistant/faiss_index/` (git-ignored)
with a manifest of file hashes. Every start logs which of these happened:

```
INFO northwind: Index BUILT: embedded 20 chunks from 4 files in 0.72s, saved to .../faiss_index
INFO northwind: Index LOADED from .../faiss_index in 0.02s: 20 chunks from 4 files, 0 chunks embedded
```

Only new or changed files in `data/` are re-embedded. Changing the chunk settings or
the embedding model triggers a full rebuild automatically. The UI starts with this
same step, so running `ingest` first is optional; it just makes the first UI start faster.

### 4. Run

```bash
streamlit run capstone_internal_docs_assistant/app.py      # chat UI on http://localhost:8501

python capstone_internal_docs_assistant/app.py ask "How much PTO do I get?"
python capstone_internal_docs_assistant/app.py chat        # terminal chat with memory (/reset, /quit)
python capstone_internal_docs_assistant/app.py demo        # cited answer, follow-up, refusals, session isolation
python capstone_internal_docs_assistant/app.py eval        # LangSmith eval -> EVAL_RESULTS.md
python capstone_internal_docs_assistant/app.py diagram     # writes graph.mmd + architecture.mmd
```

Results: [`EVAL_RESULTS.md`](EVAL_RESULTS.md) (latest scores) and
[`FAILURE_ANALYSIS.md`](FAILURE_ANALYSIS.md) (what fails and why).

---

## The brief
Build an **internal knowledge assistant** for a company (our fictional *Northwind
Robotics*, using the docs in `../data/`). An employee should be able to ask
natural-language questions about HR policies, IT procedures, and product specs and
get a **correct, grounded, cited** answer — through a simple chat UI.

This is the real job of an applied RAG engineer: not a notebook, but a small
*product* that is retrieval-quality-aware, evaluated, traceable, and honest about
what it doesn't know.

## Required capabilities (the "must-haves")
1. **Ingestion pipeline** — load the corpus, chunk it sensibly, embed it, and
   persist a vector index. Re-running the app must not re-embed from scratch.
   Support adding a new document without a full rebuild if feasible.
2. **Agentic retrieval + answering** — reuse your **LangGraph** graph from Task 8
   (routing, doc grading, query rewrite, hallucination check). The assistant must
   refuse (not hallucinate) when the answer isn't in the docs.
3. **Conversational memory** — multi-turn follow-ups work (Task 5), isolated per
   user session.
4. **Citations** — every answer shows which source file(s)/section it used.
5. **Chat UI** — a Streamlit app (`app.py`) with a chat box, streaming answers,
   visible sources, and a session reset button.
6. **Evaluation** — a LangSmith eval suite (extend Task 7's dataset to ≥20
   examples) reporting correctness + groundedness. Commit your latest scores in
   `EVAL_RESULTS.md`.
7. **Tracing** — LangSmith tracing on, so a reviewer can inspect any answer's path.

## Nice-to-haves (pick based on time / ambition)
- **Metadata filtering** (e.g. restrict to `source = it_faq.md` when the user asks
  an IT question) driven by the router.
- **Access control** demo: tag some docs "HR-only" and filter by a fake user role.
- **Streaming tokens** in the UI.
- **Feedback capture**: 👍/👎 buttons that log to LangSmith.
- **Answer caching** for repeated questions.
- **Dockerfile** so the app runs with one command.

## Architecture you should end up with
```
                 ┌─────────────┐
   documents ───▶│  Ingestion  │──▶ vector index (persisted)
                 └─────────────┘            │
                                            ▼
 user ──▶ Streamlit UI ──▶ LangGraph agentic RAG ──▶ grounded, cited answer
              ▲   │              │  (route → retrieve → grade → rewrite?
              │   │              │   → generate → hallucination-check)
              │   └── session memory        │
              └──────────── answer + sources ┘
                                            │
                              LangSmith  ◀──┘  (tracing + evaluation)
```

## Deliverables (what you hand in Friday)
1. Working `app.py` (Streamlit) + supporting modules.
2. `README` in this folder updated with **how to run it** (commands).
3. `EVAL_RESULTS.md` — your correctness/groundedness scores + a short note on the
   biggest failure mode and how you'd fix it next.
4. A **5-minute demo**: show a correct answer with citation, a refused
   out-of-scope question, and a multi-turn follow-up. Walk through one LangSmith
   trace.
5. A short architecture diagram (Mermaid is fine).

## How you'll be graded
Your mentor holds the full rubric. Headline weighting:
correctness & grounding (30%), retrieval quality (20%), agentic design (20%),
evaluation rigor (15%), code quality & UX (15%).

## Getting started
- Read `app_skeleton.py` — it has the Streamlit plumbing wired and clearly marked
  `# TODO` spots where your RAG backend plugs in. Copy it to `app.py` to begin.
- Reuse aggressively: your Task 8 `graph.py`, Task 6 retriever, Task 5 memory,
  Task 7 eval harness. The capstone is *integration*, not reinvention.
- Start with the thinnest end-to-end slice (ingest → ask → answer in the UI), get
  it working, *then* layer in grading, memory, and evaluation.
