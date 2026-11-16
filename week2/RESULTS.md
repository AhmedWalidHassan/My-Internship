# Week 2 — Results

> **Standing rule 1:** a task is done when its number is in this file (or `COST.md`).
> Fill these in as you go, not on Friday. Every heading below is required by a
> task's "Done when…" checklist.

---

## Task 1 — Week 1 closeout

All checks below were run on 2026-11-16 against the running app (local Ollama
`qwen3.5:4b` + `all-MiniLM-L6-v2` embeddings). Every command was launched from a
directory **outside** the repo to prove the scripts don't depend on the working directory.

### Week 1 review findings — closed and verified

No written mentor review was available, so findings 2–9 come from a self-review
against this task's checklist. Finding 1 was discovered while doing it.

| # | Finding | What I changed | How I verified it in the running app |
|---|---|---|---|
| 1 | **Malware in the repo.** Commit `79f36df` ("Revise README for Task 4") also added `.vscode/tasks.json` (a hidden task with `runOn: folderOpen` that runs `node …/fonts/fa-brands-400.ttf`), `.vscode/settings.json` (`task.allowAutomaticTasks: true`), and a "font" that is really obfuscated JavaScript. | Removed `.vscode/`, the fake `fonts/` folder and the `config.bat` ignore rule, in a separate commit on `security/remove-malicious-vscode-task`. Anyone who opened the repo in a trusted VS Code-based editor with `node` installed should rotate their credentials. | `git ls-files` has no `.vscode/`. `file --mime-type` over every tracked file finds no other JavaScript or executables. A grep of every tracked `.py` for `exec`/`eval(`/`base64`/`subprocess`/network calls finds none. |
| 2 | The capstone README had **no "How to run"** (Week 2 README: "that's the first finding"). The `app.py` docstring said to run "from the repo root", but the commands are relative to `week1/`. | Added a How to run section to `capstone_internal_docs_assistant/README.md`: env-var table, ingest step, run commands and the expected log lines. Fixed the docstring. | Followed the README from a clean index: `ingest`, `demo`, the Streamlit UI and `eval` all work as written. |
| 3 | **No startup log saying whether the index was built or loaded.** The `northwind` logger was never configured, so even its existing warnings were invisible. | `setup_logging()` (UI + CLI) and one `Index BUILT / LOADED / LOADED and UPDATED` line at the end of `ingest()`. | The two lines below are from two consecutive starts after deleting the index. The UI start also logs `LOADED`. |
| 4 | **Provider base URL not configurable** (needed for Task 4's container to reach Ollama or a proxy). | `OPENAI_BASE_URL` and `OLLAMA_BASE_URL` are read in `common/utils.py`; all model settings are documented in `week1/.env.example`. | `OLLAMA_BASE_URL=http://127.0.0.1:1` gives `ConnectError: Connection refused`. `OLLAMA_BASE_URL=http://localhost:11434` answers. |
| 5 | **App wired to the right graph?** The capstone could have been importing Task 8's graph. | No change needed: `app.py` builds its own graph (`run_ui → Backend → Assistant → build_graph`, all in `app.py`), with no import from `task_08_*` or `app_skeleton.py`. | In the UI, the follow-up shows the step "✓ Understanding the question" (the `contextualize` node). That node exists **only** in the capstone graph; Task 8's graph starts at `route_question`. |
| 6 | **Multi-turn memory and session isolation** | No change needed. | UI, driven through Streamlit's `AppTest` (same session): "How much PTO do I get?" → 20 days/yr; "Can I carry it over to next year?" → understood as *"Can unused PTO … be carried into the next calendar year?"* → "Yes, up to 5 days… forfeited on December 31", citing `employee_handbook.md › 2. Paid Time Off (PTO)`. CLI `demo`: the same follow-up in session B does **not** mention PTO (see open finding A). |
| 7 | **Refusal** | No change needed. | `demo`: "what's the capital of France?" → `route_question → direct_answer` → standard refusal. "What is the CEO's home address?" → 2 rewrites → `refuse`, no sources shown. |
| 8 | `EVAL_RESULTS.md` named the experiment but had **no link**, the failure-analysis placeholders were never filled, and the experiment log showed a stale row. | `eval` now writes the LangSmith experiment URL. `EVAL_RESULTS.md` points to `FAILURE_ANALYSIS.md`. Re-ran the eval. | See the eval table below. |
| 9 | **Repo hygiene:** the root `.gitignore` (the one that applies to the whole repo) only had `config.bat` (planted by the attack) and `node_modules`. | Root `.gitignore` now covers `.env`, `__pycache__/`, `*.pyc`, `**/faiss_index/`, `*.faiss`/`*.pkl` and media files. | `git ls-files -ci --exclude-standard` returns nothing. `git ls-files` shows no `__pycache__`, index or media files. |

**Open findings found during verification (not fixed in this PR; carried into Task 2/7):**

- **A. An unresolved follow-up in a fresh session gets a confident guess.** With no history, "Can I carry it over to next year?" was rewritten once and answered "No, parental leave cannot be carried over… must be taken within 12 months". The fact-check passed it, but "cannot be carried over" is an inference, not a quote. It should ask what "it" means.
- **B. The contextualizer leaks facts from the previous answer** into the standalone question ("Can unused PTO **up to 5 days** be carried…"), despite the prompt saying not to. The question then leads the model toward its previous answer.
- **C. `grade_generation` fact-checks the generator's own refusal** ("I don't know… Sources:"), "rejects" it, and loops. The CEO-address question visits 13 nodes before `refuse`. This is wasted LLM calls on every unanswerable question.

### Task 6 retrieval benchmark

`python task_06_advanced_retrieval/starter.py`, 6 questions, k = 4, 15 chunks (600/80).
MRR was added because hit-rate alone ties all four strategies.

| Strategy | Hit rate | MRR |
|---|---:|---:|
| baseline (dense similarity) | 1.00 | 1.00 |
| mmr | 1.00 | 1.00 |
| multiquery | 1.00 | 1.00 |
| hybrid (BM25 + dense) | 1.00 | 0.83 |

**Winner and why** — two sentences, tied to how the questions are phrased:

> Every question is a paraphrase of a single fact in a 15-chunk corpus ("vacation days" for PTO, "carrying a load" for "loaded", "meal budget abroad" for "international travel"), so with k = 4 every strategy retrieves the right file and hit-rate can't separate them; the winner is the plain **dense baseline** (tied with MMR), which also puts the right file first every time (MRR 1.00) at the lowest cost. Hybrid is the only one that loses rank (MRR 0.83) because BM25 matches the questions' generic words ("can", "go", "when", "what's") instead of document terms they never use, ranking `it_faq.md` first for the rover-speed question and `employee_handbook.md` first for the meal-budget question; it would only pay off on exact-token queries (error codes, product IDs), which this question set doesn't contain.

**Stretch — build the index once:** the harness built a separate FAISS index in every
`build_*_retriever` call (4 embedding passes per run). It now builds one shared store.
Measured wall clock: **34.87 s → 35.08 s, no measurable saving**: embedding 15 chunks with a
local model takes well under a second. The run time is the model load (~18 s) plus
multiquery's LLM calls (~5 s). With a paid embedding API it saves 3 corpus embeddings per run.

### Task 8 node paths — does rewrite → retry fire?

`python task_08_langgraph_agentic_rag/starter.py` (hybrid, k = 4) and `… starter.py weak` (dense, k = 1):

```
hybrid k=4  time off carry rules?   route_question -> retrieve -> grade_documents -> generate -> grade_generation           (retries 0)
weak   k=1  time off carry rules?   route_question -> retrieve -> grade_documents -> rewrite_query -> retrieve
                                    -> grade_documents -> generate -> grade_generation                                     (retries 1)
            rewritten: "Leave accrual and rollover policies, vacation time carryover rules, PTO balance transfer guidelines"
capstone    What is the CEO's home address?   … -> rewrite_query -> retrieve -> grade_documents -> rewrite_query -> retrieve -> … -> refuse (retries 2)
```

**Finding:** with the production retriever (hybrid, k = 4), the "awkward" query does **not**
trigger the loop, because retrieval is already good enough. The loop does fire in practice, but
on unanswerable or ambiguous questions (CEO address, the history-less follow-up), not on
awkward phrasings, and there it mostly adds cost before a refusal (open finding C). It only
fires on the awkward query when retrieval is deliberately weakened (k = 1).

### Capstone eval, re-run over 20 examples

`python capstone_internal_docs_assistant/app.py eval`: **28 examples** (24 answerable +
4 out-of-scope), hybrid retriever, `qwen3.5:4b` as both system and judge, 243 s.

| Metric | Score | Date | LangSmith experiment |
|---|---:|---|---|
| Correctness | 0.96 | 2026-11-16 | [`capstone-47ff55d7`](https://smith.langchain.com/o/d25a7522-0a1b-46db-9753-429d87a65bfc/datasets/24ab974a-10a4-4542-ae66-c91e12f6390c/compare?selectedSessions=c7c7d723-29c5-486d-af5f-a92c6f88ba35) |
| Groundedness | 0.96 | 2026-11-16 | [`capstone-47ff55d7`](https://smith.langchain.com/o/d25a7522-0a1b-46db-9753-429d87a65bfc/datasets/24ab974a-10a4-4542-ae66-c91e12f6390c/compare?selectedSessions=c7c7d723-29c5-486d-af5f-a92c6f88ba35) |
| Retrieval hit-rate | 1.00 | 2026-11-16 | [`capstone-47ff55d7`](https://smith.langchain.com/o/d25a7522-0a1b-46db-9753-429d87a65bfc/datasets/24ab974a-10a4-4542-ae66-c91e12f6390c/compare?selectedSessions=c7c7d723-29c5-486d-af5f-a92c6f88ba35) |

The scores and both failing examples are identical to the 2026-11-08 run (`capstone-91743e16`),
so the Task 1 changes did not move quality. The failures reproduce: **Figma** is refused
because the fact-check wrongly says the context doesn't name Figma, and **VPN** gets a
groundedness false alarm from the judge. Both trace back to the 4B model acting as its own
judge (see `FAILURE_ANALYSIS.md`).

### Multi-turn memory working

- [x] Screenshot committed at: `week1/capstone_internal_docs_assistant/screenshots/multiturn_memory.png` *(to take by hand in the Streamlit UI; the same two turns were verified headlessly through Streamlit's `AppTest`, see finding 6)*
- [x] Cold start vs warm start log lines:

```
2026-11-16 04:48:24,427 INFO northwind: Index BUILT: embedded 20 chunks from 4 files in 0.72s, saved to /mnt/games/coding/My-Internship/week1/capstone_internal_docs_assistant/faiss_index
2026-11-16 04:48:32,430 INFO northwind: Index LOADED from /mnt/games/coding/My-Internship/week1/capstone_internal_docs_assistant/faiss_index in 0.02s: 20 chunks from 4 files, 0 chunks embedded
```

---

## Task 2 — Test harness

| Tier | Tests | Wall clock | API cost |
|---|---:|---:|---:|
| Fast (`make check`) | | | $0.00 |
| Live (`make check-live`) | | | |

**The regression test:** which test fails if the app is wired to the wrong graph?

> `tests/___::___`

---

## Task 3 — Service API

| Endpoint | p50 latency | p95 latency | n |
|---|---:|---:|---:|
| `POST /chat` | | | 20 |
| `POST /chat/stream` (time to first token) | | | 20 |
| `POST /chat/stream` (time to last token) | | | 20 |

**Session isolation** — the test that proves it:

> `tests/___::___`

**Concurrency (stretch):** 5 simultaneous requests — did latency degrade, and where?

>

---

## Task 4 — Containerize

| | Value |
|---|---|
| Image size | |
| Biggest contributor to size | |
| Runs as non-root | ☐ |
| Cold-checkout `docker compose up` works | ☐ |
| Provider switchable by `.env` alone | ☐ |

---

## Task 5 — Observability

*(Latency and cost figures live in `COST.md`. This section is for behaviour.)*

**Node-path distribution over the eval set** — how often does each path actually fire?

| Path | Count | % |
|---|---:|---:|
| route→retrieve→grade→generate→check→END | | |
| …with 1 rewrite loop | | |
| …with 2 rewrite loops | | |
| route→direct→END | | |

**Does the rewrite→retry loop fire in practice?**

>

---

## Task 6 — Caching

*(Before/after cost table lives in `COST.md`.)*

| | Value |
|---|---|
| Cache hit rate on defined workload | |
| Workload used (describe it) | |
| Invalidation test | `tests/___::___` |

**Semantic cache — implemented, or argued against?** Two paragraphs either way:

>

---

## Task 7 — Eval gate

**Baseline committed in** `eval_baseline.json` — scores and date:

| Metric | Baseline | Date |
|---|---:|---|
| Correctness | | |
| Groundedness | | |

**Category-split scores** (this is the point — a blended average hides the roadmap):

| Category | n | Correctness | Groundedness |
|---|---:|---:|---:|
| Factual (single doc) | | | |
| Multi-hop (two docs) | | | |
| Multi-part answers | | | |
| Refusal / out-of-scope | | | |
| Follow-up (needs history) | | | |
| Keyword-precise | | | |

**The 10 new adversarial examples** — what each is designed to break:

| # | Question | Designed to break |
|---|---|---|
| 21 | | |
| 22 | | |
| … | | |

**The red build:** link to the CI run that blocked the deliberately-weakened prompt.

>

**Real weakness found by the adversarial set:**

>

---

## Task 8 — Resilience

**Degradation table** — what degrades to what:

| Failure | Behaviour | Tested by |
|---|---|---|
| LLM provider timeout | | |
| `grade_documents` fails mid-loop | | |
| Embedding call fails at startup | | |
| Rate limit exceeded | | |

**Prompt-injection attempts:**

| # | Attempt | Outcome |
|---|---|---|
| 1 | | |
| 2 | | |
| 3 | | |

---

## Friday — Release v1.0

- [ ] Tagged `v1.0`
- [ ] `CHANGELOG.md`
- [ ] `RUNBOOK.md`
- [ ] `ARCHITECTURE.md` with current Mermaid diagram
- [ ] `RESULTS.md` and `COST.md` complete

**The weakest part of this system, in my own words:**

>
