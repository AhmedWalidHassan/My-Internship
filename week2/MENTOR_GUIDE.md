# Mentor Guide — Week 2: Ship It For Real

For the engineers supervising. Contains the design rationale, per-task acceptance
criteria, failure modes to watch for, and the grading rubric. As in Week 1, the
"Done when…" checklists in each task README are shared with the intern.

---

## Why this week is shaped this way

Week 1 ends with a working RAG system and an intern who can build one. Week 2
exists because building is only half the job: the other half is proving the thing
works, knowing what it costs, and handing it to someone else.

That half is a set of habits, and habits are taught by structure rather than by
advice. So the week is built so that skipping the process is *structurally
impossible* rather than something you have to keep reminding them about:

- **Every "Done when…" ends in a committed artefact containing a number.** The
  file it belongs in is named in the task. "Built but not measured" is not an
  available outcome.
- **The seam is the deliverable.** Week 1 rewards good components. Integration
  bugs live in the joints between them, so this week the grade is on the running
  system, defended by tests that exercise it end to end.
- **Everything ships behind a PR**, and by Thursday a CI gate enforces the
  quality floor automatically.

**Scaffolding:** seven of the nine tasks are spec-only. Week 1 ramps guided →
mixed → spec-only; Week 2 starts where Week 1 ended. Tasks 2 and 4 are mixed only
because they involve infrastructure conventions the intern hasn't seen before and
shouldn't have to guess at.

**Same product on purpose.** No new corpus, no new domain — they keep building on
the Northwind assistant from Week 1. Reusing a codebase they already know removes
every distraction that isn't the actual lesson.

---

## Per-task acceptance criteria & failure modes

### Task 1 — Close Week 1
- **Accept when:** the outstanding review findings are closed and *verified*, not
  just changed; the app demonstrably handles a two-turn follow-up; restarting
  does not re-embed; the outstanding Week 1 measurements are committed; the repo
  is free of build artefacts and large binaries.
- **Watch for:** fixing something and not checking it. Ask them to *show you the
  behaviour*, not the diff. Also ask why the bug survived — the answer is usually
  "I never ran it after wiring it up," and hearing them say it out loud is worth
  more than the fix itself.
- **This is a hard gate.** Nothing else starts Monday until it's closed.

### Task 2 — Test harness
- **Accept when:** `make check` is green in <5s with no API key; the regression
  test goes red when the Task 1 fix is reverted; four live golden-path tests pass
  with their runtime and cost recorded.
- **Watch for:** tests that assert on LLM *output wording* — those are flaky and
  they'll learn to ignore them. Push toward asserting on structure, routing, and
  the presence of citations and refusals.

### Task 3 — Service API
- **Accept when:** all six endpoints work; streaming visibly streams; two
  `session_id`s are independent *under test*; the Streamlit UI imports no graph
  code; p50/p95 latency recorded.
- **Watch for:** a module-level session dict that breaks with two workers. They
  don't have to solve it — they have to know it's there and say so. Also check
  that `/healthz` doesn't call the model, and that the index loads once at
  startup rather than per request.

### Task 4 — Containerize
- **Accept when:** `docker compose up` works from a clean checkout with only
  `.env` supplied; no key in any image layer; provider switchable by env var
  alone; image size recorded.
- **Watch for:** the index volume mount. Without it, every image rebuild silently
  re-embeds. Also watch for a "slim" image that installs the entire Week 1
  dependency set with no comment on the resulting size.

### Task 5 — Observability
- **Accept when:** one request produces one structured log line with every named
  field; a `request_id` leads to its LangSmith trace in under 10 seconds;
  `COST.md` reports mean/p95 latency, calls, tokens, cost per question, and a
  monthly projection.
- **Watch for:** logging that is really just printing. Also — the node-path
  distribution answers a question Week 1 leaves open: does the rewrite→retry loop
  ever actually fire? **If the data shows it never fires, that is a better finding
  than a passing checkbox** — it means the document grader is too permissive and
  the self-correction machinery is decorative. Reward reporting it.

### Task 6 — Caching
- **Accept when:** before/after latency and cost over the same 20 examples; hit
  rate on a defined workload; an invalidation test proving a stale answer isn't
  served; the semantic-cache decision argued either way.
- **Watch for:** caching a refusal. If the docs later gain the answer, a cached
  "I don't know" is actively harmful. Also watch for a cache key that ignores
  conversation context and so serves the wrong answer to a follow-up.

### Task 7 — Eval gate
- **Accept when:** a deliberately weakened prompt is blocked by a red CI build
  (shown live, then reverted); `eval_baseline.json` committed; 30 examples with
  the 10 new ones documented; scores split by category; at least one real
  weakness found by the adversarial set.
- **Watch for:** a blended average hiding everything. If refusal scores 1.0 and
  multi-hop scores 0.4, a blended 0.85 conceals the roadmap — category splits are
  the growth item here. Also watch for a threshold set below the current score so
  the gate can never actually fire.
- **This is the keystone task.** If the week slips, drop Task 8, not this.

### Task 8 — Resilience
- **Accept when:** forced provider failure returns a structured error inside the
  timeout; injection attempts don't leak the system prompt or bypass refusal;
  rate limiting triggers; the degradation table is written down.
- **Watch for:** unbounded transport retries stacked on top of the graph's
  already-bounded logical retries — the two multiply. Ask: "what happens if
  `grade_documents` times out on doc 3 of 4?" The right answer is a *decision*,
  not a shrug.

### Release — Friday
- **Accept when:** tagged `v1.0`, `CHANGELOG.md` in their own words, `RUNBOOK.md`
  written for someone else, `ARCHITECTURE.md` with a current Mermaid diagram, and
  both measurement files complete.
- **Watch for:** a runbook that documents the happy path only. Ask what it says to
  do when the eval gate goes red out of hours.

---

## Grading rubric — Week 2 (100 pts)

Deliberately re-weighted from Week 1. Answer correctness isn't a line item here —
it's protected by Task 7's automated gate instead. What carries the weight this
week is process, measurement, and whether the system can be operated by someone
who didn't build it.

| Dimension | Weight | 4 (excellent) | 3 (solid) | 2 (developing) | 1 (weak) |
|-----------|-------:|---------------|-----------|----------------|----------|
| **Service quality** | 20 | Clean API, streaming works, sessions isolated, starts from a cold checkout in one command | Works, minor rough edges | Runs but fragile or manual | Doesn't run elsewhere |
| **Evaluation as a gate** | 20 | 30-example suite, category-split scores, CI blocks regressions, adversarial cases found real bugs | Gate works, scores reported | Eval runs manually | No gate |
| **Observability & cost** | 20 | Every request traceable end to end; cost per question known; a reduction argued from data | Logging + costs reported | Some logging | Can't tell what it did |
| **Engineering process** | 20 | PR per task, tests that catch real regressions, runbook someone else could follow | Mostly consistent | Sporadic | One big commit |
| **Resilience** | 10 | Degrades gracefully, guardrails hold, failure paths tested | Handles common failures | Happy path only | Falls over |
| **Communication** | 10 | Numbers, diagrams and decisions written down as they go; demo is crisp | Documented after the fact | Thin | Undocumented |

**Scoring:** map each dimension's 1–4 to its weight (4/4 on Service quality = 20,
3/4 = 15, etc.). ~85+ exceptional · 70–85 strong · 55–70 on track · <55 needs support.

**The dimension to watch is Engineering process.** It's the one that transfers to
every future project regardless of what the project is.

---

## What to probe in the Friday demo

Run these in order; they map to the rubric.

1. **`docker compose up` from a clean checkout.** Binary — it comes up or it doesn't.
2. **Grounded question, streaming.** Tokens arrive incrementally; citation present.
3. **Out-of-scope question, then the injection attempt.** Expect refusal both times.
4. **Two-turn follow-up.** Memory works across turns and is isolated per session.
5. **Open a log line, then the LangSmith trace it points to.** Ask them to narrate
   the node path — including *why* the graph took that path for that question.
6. **Show the cost report.** Ask: what's the most expensive node, and what would
   you do about it?
7. **Open a PR that weakens the prompt, live.** Watch CI go red.
8. **Ask: "which eval category is weakest, and what's your plan?"** The best
   possible answer is specific and slightly uncomfortable.

---

## Red flags across the week

- **Numbers appearing only on Friday.** The habit is daily or it isn't a habit.
  If `RESULTS.md` is empty on Wednesday, intervene then — not at the demo.
- **A green CI gate that has never been red.** A gate nobody has watched fire is
  decoration. Make them break it on purpose.
- **"It works" without a test.** The reply is always: show me the test that fails
  if it stops working.
- **Code they can't explain line by line.** Same remedy as Week 1 — have them
  narrate it. Task 3 is the natural place to check, since it's the largest chunk
  of new code they'll write this week.
