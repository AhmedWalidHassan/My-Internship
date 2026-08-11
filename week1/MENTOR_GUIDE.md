# Mentor Guide — RAG Internship, Week 1

This guide is for the engineers supervising the interns. It contains the intended
schedule, per-task acceptance criteria, common failure modes to watch for, and the
capstone grading rubric. Interns are not meant to read the rubric internals, but
the "Done when…" checklists in each task README are shared with them.

## How to run the week
- Interns work through Tasks 1–8, then the capstone. Tasks 1–4 are guided
  (skeleton + TODOs), 5–7 are mixed, 8 and the capstone are spec-only.
- One branch + small PR per task. Review PRs quickly — the review *is* the
  teaching moment. Keep feedback focused on RAG reasoning, not style nits.
- A 15-minute daily standup: each intern states yesterday's task, today's task,
  and one blocker. Blockers also live in each intern's `NOTES.md`.
- Pair struggling interns; the tasks are designed so a stuck intern can still
  reach the next task with a working (if imperfect) solution.

## Suggested schedule (see SCHEDULE.md for the day-by-day grid)
- **Day 1:** Tasks 1–2 (fundamentals, loading/chunking).
- **Day 2:** Tasks 3–4 (embeddings/vector store, naive RAG). First working RAG!
- **Day 3:** Tasks 5–6 (conversational RAG, advanced retrieval).
- **Day 4:** Tasks 7–8 (LangSmith eval, LangGraph agentic RAG).
- **Day 5:** Capstone build + Friday demos.

The capstone realistically spills into Day 4 evening; that's fine. If an intern is
behind, the priority order is: get Task 4 solid → Task 8 graph → capstone MVP.
Tasks 5, 6, 7 enrich the capstone but a basic version can ship without all three.

## Per-task acceptance criteria & failure modes

### Task 1 — LangChain fundamentals
- **Accept when:** all three chains run; structured chain returns a real object;
  they can explain the `|` pipe.
- **Watch for:** treating the LLM output object as a string (forgetting the output
  parser); not understanding that `with_structured_output` changes the return type.

### Task 2 — Loading & chunking
- **Accept when:** all docs load, chunk counts printed for ≥3 sizes, source
  metadata preserved, overlap explained.
- **Watch for:** losing `metadata["source"]`; thinking bigger chunks are always
  better; confusing character vs token length.

### Task 3 — Embeddings & vector store
- **Accept when:** FAISS index built, relevant results for the 3 queries, index
  saved+reloaded without re-embedding.
- **Watch for:** re-embedding every run (cost!); not understanding the distance
  metric; `allow_dangerous_deserialization` confusion on load.

### Task 4 — Naive RAG
- **Accept when:** correct grounded answer with sources; out-of-scope question hits
  the "I don't know" fallback.
- **Watch for:** the model answering from its own knowledge instead of context;
  no source attribution; prompt that doesn't forbid hallucination.
- **This is the key checkpoint.** No one should move past Day 2 without a working,
  non-hallucinating Task 4.

### Task 5 — Conversational RAG
- **Accept when:** the PTO → "can I carry it over?" follow-up resolves correctly;
  sessions are isolated.
- **Watch for:** retrieving on the raw follow-up (no contextualization); global
  memory shared across sessions; unbounded history blowing up tokens.

### Task 6 — Advanced retrieval
- **Accept when:** ≥3 strategies implemented and benchmarked; a winner identified
  with a reason.
- **Watch for:** implementing strategies but not actually comparing them; assuming
  hybrid always wins; BM25 built over the wrong (unchunked) docs.

### Task 7 — LangSmith eval
- **Accept when:** traces visible, dataset created, evaluate() runs with
  correctness + groundedness, scores recorded.
- **Watch for:** tracing env vars not set; confusing "correct" with "grounded"
  (an answer can be grounded but wrong, or right but not grounded); judging with a
  too-weak model.

### Task 8 — LangGraph agentic RAG
- **Accept when:** routing works; the grade→rewrite→retry loop demonstrably fires;
  hallucination check catches an unsupported answer; every path terminates;
  node-path is printable; Mermaid diagram included.
- **Watch for:** infinite loops (no retry cap); conditional edges wired to the
  wrong branches; graders returning free text instead of booleans; state fields
  not being updated by nodes.

## Capstone grading rubric (100 pts)

| Dimension | Weight | 4 (excellent) | 3 (solid) | 2 (developing) | 1 (weak) |
|-----------|-------:|---------------|-----------|----------------|----------|
| **Correctness & grounding** | 30 | Answers are accurate and always cite; refuses cleanly when unknown; no hallucinations found in demo | Mostly accurate, cites, rare slip | Sometimes wrong or ungrounded | Frequently hallucinates |
| **Retrieval quality** | 20 | Deliberate strategy (hybrid/rerank) justified by eval numbers | Reasonable retriever, some tuning | Default top-k only | Retrieval clearly broken |
| **Agentic design (LangGraph)** | 20 | Clean graph: routing, grading, bounded self-correction, all paths terminate | Graph works, minor rough edges | Partial graph / linear-ish | No real agentic control flow |
| **Evaluation rigor** | 15 | ≥20-example LangSmith eval, correctness+groundedness, failure analysis, an improvement experiment | Eval runs, scores + some analysis | Minimal eval | No evaluation |
| **Code quality & UX** | 15 | Modular, reuses prior tasks, clean Streamlit UX with sources+reset, clear run docs | Works, readable | Messy but runs | Hard to run |

**Scoring:** map each dimension's 1–4 to its weight (e.g. 4/4 on Correctness = 30,
3/4 = 22.5, etc.). ~85+ = exceptional intern; 70–85 = strong; 55–70 = on track;
<55 = needs support / extension.

### What to probe in the Friday demo
- Ask a question whose answer is in the docs → expect correct + cited.
- Ask something *not* in the docs → expect a refusal, not a guess.
- Ask a two-turn follow-up → expect memory to work.
- Open one LangSmith trace together → can they explain each node/step?
- Ask: "what's your worst failure case and how would you fix it?" → tests whether
  they evaluated honestly.

## Red flags across the week
- Copy-pasting course code without being able to explain it → ask them to narrate
  a chain line by line.
- "It works on my machine" with no eval → push them to Task 7 rigor early.
- Silent hallucinations → the single most important thing to stamp out; grounding
  and refusal behavior is non-negotiable.
