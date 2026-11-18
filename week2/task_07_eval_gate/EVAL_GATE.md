# The eval gate in CI (Week 2, Task 7)

The brief is in [README.md](README.md). This page covers what was built, how it runs, what it
found, and the evidence for each "Done when…" item. Per-example and per-category numbers are
in [`week2/RESULTS.md`](../RESULTS.md#task-7--eval-gate).

## Where things are

| What | Where |
|---|---|
| The workflow (the README places it there) | [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml), linted with actionlint ([`.github/actionlint.yaml`](../../.github/actionlint.yaml)) |
| Dataset: 38 examples, 6 categories | [`eval_dataset.jsonl`](eval_dataset.jsonl) |
| Baseline + tolerance + justification | [`eval_baseline_w2.json`](eval_baseline_w2.json) (**archived** in Week 3 Task 1, see below), [`tolerance_justification.md`](tolerance_justification.md) |
| Eval runner (real pipeline, no cache, category split, LangSmith publish) | [`scripts/run_eval.py`](scripts/run_eval.py) |
| The gate (thresholds, cost, flips by id, report) | [`scripts/check_baseline.py`](scripts/check_baseline.py) |
| Baseline builder (majority over runs, flaky flags, noise) | [`scripts/make_baseline.py`](scripts/make_baseline.py) |
| PR comment / nightly issue | [`scripts/post_report.py`](scripts/post_report.py) |
| Fast-CI dependencies (no torch) | [`requirements-ci.txt`](requirements-ci.txt) |
| Evidence: baseline runs, CPU run, judge check | [`evidence/`](evidence/) |
| Tests of the gate itself (13) | [`tests/test_eval_gate.py`](../../tests/test_eval_gate.py) |

Run it by hand: `make eval-gate` runs the eval, then the gate, against the committed baseline.

> **Week 3 Task 1 (2026-11-18): the Week 2 baseline is archived.** It was measured on the 4-file Week 1
> corpus and no longer describes the system, so it was renamed (not edited) to `eval_baseline_w2.json`.
> `check_baseline.py` refuses to gate against it, and with no current `eval_baseline.json` the gate is
> red with the reason "NO BASELINE" rather than comparing against stale numbers. Week 3 Task 2 commits
> the new baseline (dataset v3). The Week 2 run on the new corpus is in
> [`week3/RESULTS.md`](../../week3/RESULTS.md#the-week-2-toolchain-against-the-new-corpus).

> **Week 3 Task 2 (2026-11-18): the gate now protects the Week 3 system.** `eval_baseline.json` is dataset
> `northwind-eval-v3`, dev split (70 examples), judged by `gemma3:4b` (the judge is no longer the generator).
> The runner (`scripts/run_eval.py`) gained `--split`, `--retrieval-only` and the Week 3 categories, and
> scores the deterministic floor. See [`week3/task_02_eval_at_scale/RUN.md`](../../week3/task_02_eval_at_scale/RUN.md).

## The two jobs

**`fast-checks`, on every PR and push.** `uv` (cached) installs only what the fast tests import,
then ruff and `pytest -m "not live"`. No secrets, no model, and the test step is capped at 60 s.
**Measured: 18–21 s for the whole job** on GitHub's runner, tests 6–8 s.

**`eval-gate`, nightly at 03:00 UTC, on `workflow_dispatch`, and on PRs labelled `run-eval`:**
1. checks that the laptop's Ollama is up and has the model;
2. runs all 38 examples through the real graph (`run_eval.py`; no answer cache, by construction);
3. publishes them as a LangSmith experiment;
4. runs `check_baseline.py`, which **exits 1** on a regression beyond the tolerance;
5. posts or updates one report comment on the PR, or opens an issue when a nightly run fails;
6. uploads `eval_results.json` and the report as artifacts.

**Measured: ~5.5 min per eval.**

### Where the eval runs, and why: a self-hosted runner on the laptop's GPU

First, the eval ran on GitHub's free runner with Ollama on its CPU. **Measured:** 3–11 min per
example (2 CPUs, 7 GB), so ~2.5–3 h for 38. Then *"The hosted runner lost communication with the
server"* after 67 minutes: the model starved the runner itself. Nightly runs would also have
needed ~75 h of runner time a month, against a private repo's 33 free hours.

So the job runs on a **self-hosted runner in a Docker container on the maintainer's laptop**,
calling the laptop's Ollama (`qwen3.5:4b` on the RTX 3060). That's the same model and hardware
the baseline was measured on, so CI reproduced the baseline **exactly** (0.921 / 0.974 / 1.000).

Because this executes repository code on a personal machine, it's locked down:
- **Who can trigger it:** the job runs only for events the repo owner triggers (their push or
  label, their dispatch, the schedule), never for a fork's PR. Another contributor's push can't
  start it.
- **What the container can reach:** the official `ghcr.io/actions/actions-runner:2.338.2` image,
  running as a non-root user, with no host mounts and no Docker socket. It can reach the host's
  Ollama and the internet, nothing else of the host: no home directory, `.env` or SSH keys.
  It restarts with Docker at boot.
- **The job installs nothing on the host;** it fails with a clear error if Ollama isn't running.

Operating it:

```bash
docker ps --filter name=northwind-runner                  # is the runner up?
OLLAMA_HOST=172.17.0.1:11434 ollama serve                 # Ollama must be running for evals
docker stop northwind-runner && docker rm northwind-runner && docker volume rm northwind-runner   # remove it
# then delete "laptop-gpu-docker" under Settings → Actions → Runners
```

A nightly run while the laptop is off waits in the queue (GitHub keeps self-hosted jobs queued
for up to 24 h).

### "Make it a required check": not available on this repo

GitHub only allows branch protection and rulesets on a **private** repository with GitHub Pro
(the API returns 403 "Upgrade to GitHub Pro or make this repository public"). The gate goes red
and posts on the PR, but GitHub can't technically block the merge button. To enforce it, either
upgrade or make the repo public, then add `fast-checks` and `eval-gate` as required status checks.

## The dataset: 38 examples, 6 categories

The brief asks for 30 (Week 1's 20 plus 10). The capstone eval already had 28 (24 answerable plus
4 out of scope), so 28 + 10 new = **38**. Dropping 8 tested examples just to land on 30 would
have thrown away coverage. A fast test pins the first 28 to the capstone's `EVAL_EXAMPLES`, so the
two can't drift, and checks every reference fact against the corpus.

| Category | n | What's in it |
|---|---:|---|
| factual | 19 | one fact, one document |
| multi-part | 7 | several facts asked at once (5 existing, 2 new) |
| refusal | 6 | out of scope (4 existing, 2 new **near-misses**) |
| multi-hop | 2 | new: facts from two documents |
| follow-up | 2 | new: only answerable with the earlier turn (injected into the session) |
| keyword | 2 | new: exact tokens ("Fleet Manager 4.2", "5G") |

The 10 new examples and what each is designed to break are in [RESULTS.md](../RESULTS.md#task-7--eval-gate).

## Tolerance: 0.08

The full justification is in [`tolerance_justification.md`](tolerance_justification.md), and
copied into the baseline file. In short:
- **Same hardware:** two full runs were verdict-for-verdict identical.
- **Moving to CPU and ONNX moved 3 verdicts:** correctness −2 examples, groundedness +1. A
  runtime or driver update can do the same.
- **A real regression is far bigger:** grading 1 passage instead of 6 costs 9 examples.

0.08 = 3 of 38, so the gate fires at 4 or more lost examples. Below that, the PR comment still
lists every flipped example by id. The cost gate (stretch) fails at +20% mean cost per question.

## What the gate showed

Two deliberate regressions, each opened as a throwaway PR into this task's branch with the
`run-eval` label, then closed unmerged:

| Demo PR | Change | `fast-checks` | `eval-gate` |
|---|---|---|---|
| [#7](https://github.com/AhmedWalidHassan/My-Internship/pull/7) ([run](https://github.com/AhmedWalidHassan/My-Internship/actions/runs/44258689585)) | **The brief's demo:** delete the refusal instruction (rule 3) from the generate prompt | ❌ **red**: `test_generate_prompt_contains_refusal_instruction` | ✅ passed: correctness 0.92 → 0.87 (−2 examples, #3 and #18 over-refused), +6% cost; both within tolerance |
| [#8](https://github.com/AhmedWalidHassan/My-Internship/pull/8) ([run](https://github.com/AhmedWalidHassan/My-Internship/actions/runs/44258699220)) | Grade 1 retrieved passage instead of 6 (one config default) | ❌ red (incidentally: two API tests expect the handbook citation) | ❌ **red**: correctness **0.92 → 0.68**; the comment names all **10** flipped examples; keyword and multi-hop fall to 0.00 |

**The weakened prompt is blocked by CI, but by the fast gate, not the eval, and that's the right
split.**
- **Why the eval barely moves:** without rule 3 the model still declines out-of-scope questions,
  in its own words ("The provided context does not contain…"). The fact-check rejects those
  drafts, and after two rewrites the `refuse` node outputs the canonical refusal, so all 6
  refusal examples stayed correct.
- **What's left is noise-sized:** two over-refusals elsewhere, −2 examples, the same size as
  switching from GPU to CPU. No eval with a 4B judge can attribute a 2-example change.
- **Why the test still matters:** the refusal contract is deterministic text, so a deterministic
  test guards it on every PR in 20 s, at no cost.

The eval's job is what tests can't see: demo #8, a one-number config change, cost 10 answers.
That's the regression the eval gate exists for, and it fires with a 2.4-point margin over the
floor and names every example. (The skeleton hoped for "two independent gates, both red" on the
prompt change; the measured truth is one gate per kind of regression, and #8 shows the eval gate
firing.)

## Real weaknesses the adversarial examples found

1. **#35, follow-up, "Do they carry over?" after sick days: a generation error, not retrieval.**
   - The contextualizer resolved it correctly ("Do the paid sick days carry over?") and retrieval
     ranked the Sick Leave chunk **first**.
   - But the answer was about PTO: "up to 5 days may be carried into the next calendar year". The
     PTO chunk says "carried into the next calendar year", which matches "carry over" more
     directly than sick leave's negative "does not carry over".
   - The answer is grounded (it's true of PTO), so **groundedness passed it while correctness
     failed it**: a concrete case for gating on correctness, not groundedness alone.
2. **#29, multi-hop, referral bonus + new hire's PTO: a verification error.**
   - Both chunks were retrieved and the draft answer was *correct* ("$3,000 … after 90 days …
     cannot use PTO in the first 90 days").
   - The 4B fact-check rejected it twice and the system refused: the same failure mode as Figma
     (Week 1).
3. **Hardware sensitivity of the 4B fact-check.** On CPU it also rejected two correct answers that
   it accepts on the GPU (#3, #9). The verification stage is the system's most fragile part, and
   the eval measures it.

All 6 refusal examples, including the 2 near-misses, were refused correctly; the 4 new multi-part
and keyword examples were answered correctly.

## Self-grading check

The judge is the generator's own model. I re-judged 5 non-refusal examples with `gemma3:4b`:
**1 of 10 verdicts moved**, toward *leniency* (gemma accepted the VPN answer's grounding, where
qwen flagged it). On this sample the self-judge isn't inflating scores. It's small evidence, and
the limitation is stated in the capstone's `EVAL_RESULTS.md`.
