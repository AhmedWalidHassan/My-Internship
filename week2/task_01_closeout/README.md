# Task 1 — Close Week 1, and Prove It

**Focus:** finishing what's open, and verifying rather than assuming.
**Scaffolding:** 🔴 Spec-only.
**Time budget:** half a day (Monday AM).
**Branch:** `week2/task-01-closeout`

---

## Why this task

Shipping new features on top of a broken integration is how a small bug becomes an
architectural one. Your capstone has one blocking defect and three unfinished
measurements. All four are minutes of work.

What this task actually tests is whether you can take a review and close it
**completely** rather than partially — which is most of what code review is, for
the rest of your career.

---

## What to fix

### 1. The app is wired to the wrong graph — this is the blocker

`capstone_internal_docs_assistant/app_skeleton.py:21` imports `build_graph` from
`week1.task_08_langgraph_agentic_rag.starter` instead of from your own `Graph.py`.

Two things break as a result, and both are required capabilities:

- **Multi-turn memory doesn't work.** You build a per-session `history` list and
  pass it in with a comment saying it's "used by the `contextualize` node" — but
  the Task 8 graph has no `contextualize` node and no `history` field in its
  state. Every follow-up is treated as a fresh question.
- **The persisted index is bypassed.** The Task 8 retriever calls
  `FAISS.from_documents(...)` unconditionally, so `ingest.py` — your best module —
  is dead code, and the corpus re-embeds on every app start.

Fix the import. Then **run the app and check**, because the point of this task is
the checking.

### 2. Make it runnable by someone else

- Rename `app_skeleton.py` → `app.py`.
- Add a **How to run** section to `capstone_internal_docs_assistant/README.md`:
  required env vars, the ingest step, the run command. That file is currently
  byte-identical to the brief you were handed.

### 3. Fix the hardcoded path

`capstone_internal_docs_assistant/eval.py:26` sets the dataset path to a relative
Windows string with an invalid `\c` escape (Python emits a SyntaxWarning for it).
It only resolves when run from the repo root, on Windows. Use
`Path(__file__).resolve().parent / "eval_dataset.jsonl"` — the pattern you used
correctly in every other module.

### 4. Run the two measurements you never ran

- **Task 6 benchmark.** The harness prints a hit-rate table. Run it, commit the
  table to `week2/RESULTS.md`, and write two sentences naming the winner and *why* —
  tie it to how the questions are phrased.
- **Capstone eval.** Your dataset has 20 examples but `EVAL_RESULTS.md` reports
  scores from the old 10-example run. Re-run over all 20 and update the file.

### 5. Clean the repo

Add to `.gitignore`: `__pycache__/`, `**/faiss_index/`, `*.mp4`, `*.pyc`.
Then remove the 33 MB `project.mp4`, both index folders, and the `__pycache__`
directories from tracking (`git rm -r --cached`). Keep the video somewhere it
belongs — a shared drive, a release asset — and link to it from the README.

---

## Done when…

- [ ] The app answers *"How much PTO do I get?"*, then *"Can I carry it over?"*, and
      the second answer resolves "it" correctly **without you repeating the word
      PTO**. Screenshot committed.
- [ ] Restarting the app twice does not re-embed. Prove it with a startup log line
      that says whether the index was **loaded** or **built** — and paste both
      lines into `week2/RESULTS.md`.
- [ ] `week2/RESULTS.md` contains the Task 6 hit-rate table plus your two-sentence
      explanation of the winner.
- [ ] `EVAL_RESULTS.md` reports correctness and groundedness over **20** examples,
      dated, with the LangSmith experiment link.
- [ ] `python capstone_internal_docs_assistant/eval.py` runs from any directory.
- [ ] `git ls-files` shows no `.mp4`, no `__pycache__`, no index files.
- [ ] One PR, reviewed and merged, before you start Task 2.

---

## A question to answer in the PR description

Why did the import bug survive all week? Write one honest sentence. It's not a
trick question and there's no wrong answer — but the answer is the reason Task 2
exists, and rule 2 of this week's standing rules.

---

## Stretch

- Your Task 6 harness rebuilds the FAISS index inside every `build_*_retriever`
  call, so running it embeds the corpus **four times**. Build it once and pass it
  in. Note the time saved in `week2/RESULTS.md` — it's your first cost measurement
  of the week.
