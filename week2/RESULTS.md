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

Measured 2026-11-16 from the repo root. Fast tier run with an **empty environment**
(`env -i PATH=$PATH HOME=$HOME make check`): no API keys at all. The fast tier also
removes keys and blocks network connections itself (`tests/conftest.py`), so a test
that tries to reach a model fails instead of costing money.

| Tier | Tests | Wall clock | API cost |
|---|---:|---:|---:|
| Fast (`make check`, ruff + pytest) | 23 passed | **1.3–1.9 s** (4 runs; pytest alone 0.55–0.82 s) | $0.00 |
| Live (`make check-live`) | 7 passed, 1 xfail | **71 s** (pytest 68.5 s) | $0.00 (local Ollama `qwen3.5:4b`); 9 questions through the full graph |

**The regression test:** which test fails if the app is wired to the wrong graph?

> `tests/test_graph_structure.py::test_app_graph_has_contextualize_node`
>
> Its `app_graph` fixture builds the graph through the app's real path, `Backend()` → `Assistant` → `.graph`,
> with only the model and embeddings faked. It inspects the graph the app actually runs, not a graph
> the test builds the "right" way.

**Proof it goes red.** I changed `Assistant.__init__` in `app.py` to build its graph from
Task 8 (`from task_08_langgraph_agentic_rag.starter import build_graph as build_agentic_graph`,
an aliased import that ruff can't flag), then ran `make check`:

```
FAILED tests/test_graph_structure.py::test_app_graph_has_contextualize_node
FAILED tests/test_graph_structure.py::test_app_graph_state_accepts_history - ...
FAILED tests/test_graph_structure.py::test_app_graph_starts_by_resolving_history
FAILED tests/test_graph_structure.py::test_follow_up_is_resolved_against_history_before_retrieval
FAILED tests/test_graph_structure.py::test_sessions_do_not_share_history - Ke...
FAILED tests/test_graph_structure.py::test_reset_clears_only_that_session - K...
6 failed, 17 passed, 8 deselected in 0.79s

E  AssertionError: The app's graph has no `contextualize` node, so follow-up questions are never
   resolved against the conversation. Is app.py building its Assistant from the wrong build_graph
   (e.g. Task 8's)? Nodes found: ['__end__', '__start__', 'direct_answer', 'generate', ...]
```

Import restored: `23 passed, 8 deselected in 0.56s`. (The plain, non-aliased version of the
bug, `from task_08… import build_graph`, is caught even earlier: ruff fails `make check` with
`F811 Redefinition of unused build_graph`.)

**What each tier covers**

- **Fast (23):**
  - Wiring: the app's graph has `contextualize`, its state has `history`, and `contextualize` runs first.
  - Graph shape: every edge target exists, every node is reachable from START, and every node can reach END.
  - Prompts and output: `format_docs` tags every source, the refusal string is pinned in the generate prompt, and the `Sources:` line is parsed.
  - Behaviour with a scripted model: no generation call when nothing is retrieved; a rejected answer is never shown; smalltalk doesn't retrieve; out-of-domain questions are refused.
  - Memory: turn 2 is rewritten from turn 1 before retrieval, sessions don't share history, and reset clears one session only.
  - Index: build when missing, **load (not embed) when present**, re-embed only a changed file, and rebuild when the embedding model changes.
  - Stretch: the graph terminates at `MAX_RETRIES` on both worst-case paths.
- **Live (8):**
  - A cited fact (10 sick days, `employee_handbook.md`).
  - Refusals: the CEO's address, and the plausible-sounding "remote work from abroad", which correctly refused.
  - The two-turn PTO follow-up (resolves to PTO, mentions 5 days).
  - Session isolation.
  - Warm start with the real embedding model (cold 0.059 s, 20 chunks embedded; warm 0.000 s, 0 embedded).
  - The rewrite loop: `test_awkward_query_triggers_rewrite_loop` is **xfail**, and `test_unanswerable_question_exhausts_rewrites` passes.

**Rewrite loop finding (xfail, kept rather than deleted).** With the production hybrid retriever,
"time off carry rules?" finds the PTO section on the first search, so the grader keeps it and no
rewrite happens. This confirms the Task 1 finding. The loop does fire, and is bounded, on an
unanswerable question:
`… retrieve → grade_documents → rewrite_query → retrieve → grade_documents → rewrite_query → retrieve → grade_documents → generate → grade_generation → refuse`.

**`--durations=5`**

```
fast:  0.44s setup  test_app_graph_has_contextualize_node    (first Backend() build: imports FAISS + BM25)
       0.01s call   test_unsupported_answer_is_never_returned   (every other fast test is ≤ 0.01 s)
live: 28.57s call   test_grounded_answer_with_citation   (includes Ollama loading the model on first use)
       8.37s call   test_sessions_are_isolated
       7.56s call   test_two_turn_follow_up_resolves_pronoun
       6.14s setup  test_grounded_answer_with_citation   (Backend(): embedding model + index load)
       5.05s call   test_plausible_sounding_out_of_scope_is_refused
```

---

## Task 3 — Service API

Measured 2026-11-16 against `make run` (one uvicorn worker, local Ollama `qwen3.5:4b`,
`OLLAMA_NUM_PARALLEL=1`, hybrid retriever) with `make bench-api`. The questions are the
first 20 answerable questions of the capstone eval set, sent one at a time, each in a
fresh session, after one warm-up request. Raw rows:
[`evidence/task03/bench_sequential.json`](evidence/task03/bench_sequential.json).

| Endpoint | p50 latency | p95 latency | n |
|---|---:|---:|---:|
| `POST /chat` | 3.00 s | 7.93 s | 20 |
| `POST /chat/stream` (time to first token) | 1.22 s | 3.29 s | 20 |
| `POST /chat/stream` (time to last token) | 1.75 s | 6.46 s | 20 |
| `POST /chat/stream` (time to `done`: fact-checked, final) | 3.02 s | 7.95 s | 20 |
| `POST /chat/stream` (first `status` event) | 3 ms | 4 ms | 20 |

- **Streaming doesn't make the answer faster: it makes it start sooner.** `done` takes
  as long as `/chat` (3.02 s vs 3.00 s p50, mean 3.62 s vs 3.58 s), but the first words
  appear 2.5× sooner, and the first status line appears after 3 ms instead of 3 s of
  silence.
- **The gap between the last token and `done` (median 1.0 s, range 0.6–2.5 s) is the fact-check.** It runs after
  generation, so streamed tokens are a *draft*. When the check rejects one, the stream
  sends a `retract` event (protocol: [`app/README.md`](../app/README.md)). This happened
  4 times in 20 requests: once on "Can I take time off in my first months?" (the second draft
  passed) and 3 times on "Do I need approval for a Figma license?". There the user watched
  three drafts appear and vanish before the refusal. That's the known Figma fact-check
  false negative (Task 1), and with streaming it is now **visible to the user**. Holding tokens
  until the fact-check passes would remove it, but then time to first token equals time to
  `done` and streaming would gain nothing.
- **p95 is set by the rewrite loop.** 5/20 questions took a rewrite (the same 5 on both
  endpoints). The 3 where only `grade_documents` rejected the documents have a time to first
  token of 2.2–3.4 s: no token can flow until a search survives grading.
- **Restart does not re-embed.** Killed with SIGTERM and restarted: both starts log
  `Index LOADED … 0 chunks embedded` ([`evidence/task03/restart_no_reembed.log`](evidence/task03/restart_no_reembed.log)).
  Startup is 8–11 s, and almost all of it is loading the embedding model. `/healthz` answers
  during that time and `/readyz` returns 503.
- **`/healthz`:** p50 0.40 ms, p95 0.83 ms, max 1.05 ms over 200 calls; no model call
  (asserted by `tests/test_api.py::test_healthz_is_fast_and_never_calls_the_model`).
  [`evidence/task03/healthz_timing.txt`](evidence/task03/healthz_timing.txt)
- **Incremental streaming:** [`evidence/task03/curl_stream_transcript.txt`](evidence/task03/curl_stream_transcript.txt),
  the raw `curl -N` output with each line's arrival time. Status lines arrive at 0.5 / 0.7 / 0.7 /
  1.5 s, then 21 token events, about 16 ms apart, from 1.66 s to 1.98 s, then the `done` event at 2.69 s.
- **trace_id = LangSmith root run.** Verified with the LangSmith client: the run
  `af1299e1-…` from the transcript is a root `northwind_assistant` run carrying the
  `session_id` and `request_id` in its metadata. The 👍 sent through `POST /feedback` is attached to it as
  `user_rating = 1`.
- **UI over HTTP only:** `grep -r "build_graph" app/ui.py` finds nothing, and
  `test_ui_talks_to_the_api_only` pins its imports to `streamlit`, `httpx` and the stdlib. I drove
  it headlessly (Streamlit `AppTest`) against the live API: a PTO question and the follow-up
  "Can I carry it over to next year?" were answered with sources, the node path and 👍/👎 buttons.
  After a simulated page refresh (same `?session=` in the URL), the conversation was redrawn from
  `GET /session/{id}`.

**Session isolation** — the test that proves it:

> `tests/test_api.py::test_two_sessions_hold_independent_conversations`
>
> Over HTTP, two interleaved sessions: B's first question ("Can I carry it over?") is
> not rewritten (no contextualize call at all). A's follow-up is resolved using A's turn
> only, and B's question does not appear in A's prompt. `GET /session/{id}` shows each its
> own turns. `DELETE` of A clears only A, and a second `DELETE` is still a 200. (The
> live tier's `test_sessions_are_isolated` checks the same thing with the real model.)

**Concurrency (stretch):** 5 simultaneous requests — did latency degrade, and where?

> Yes, badly per request, not at all in throughput. The same 5 questions took 20.0 s one
> at a time and 18.9 s all at once. Per-request p50 went from 2.5 s to 14.2 s, and time to first
> token from 1.2 s to 6.0 s. The per-node timings (from the stream's `status` events) show where:
> every **LLM** node slowed 2.6–10× (`grade_documents` 0.79 → 3.14 s, `grade_generation`
> 1.45 → 6.11 s, `rewrite_query` 0.37 → 3.71 s), while `retrieve`, which includes the
> query embedding and the FAISS + BM25 search, stayed at 0.01–0.02 s. The session store
> doesn't show up at all. So the bottleneck is the **LLM provider**: Ollama runs with
> `OLLAMA_NUM_PARALLEL=1` and queues requests for the one loaded model. The service
> adds no lock of its own (sync endpoints run in a 40-thread pool). With a hosted provider, the
> same place would show up as rate-limit 429s instead of queueing. That's what Task 8's retry
> and backoff are for. [`evidence/task03/bench_concurrency.json`](evidence/task03/bench_concurrency.json)

**Found while doing this, not fixed (carried forward):**

- **Conversations don't survive a restart** (and wouldn't be shared by two workers):
  sessions live in the API process. See "two questions" in [`app/README.md`](../app/README.md).
- **Open finding B from Task 1 still reproduces through the UI:** the follow-up was
  understood as "Can unused PTO **up to 5 days** be carried into the next calendar year?",
  so the contextualizer still copies facts from the previous answer into the question.

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
