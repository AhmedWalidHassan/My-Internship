# Task 2 — what was built, and how to reproduce it

The brief is in [README.md](README.md). The numbers are in
[`week3/RESULTS.md`](../RESULTS.md#task-2--eval-at-scale) and [`week3/COST.md`](../COST.md#task-2--what-an-eval-run-costs).

## Where things are

The brief puts some pieces in fixed places: the Week 2 runner is extended rather than replaced, the
dataset sits under `week3/eval/`, the baseline sits next to the gate, and the Makefile targets are merged
into the root Makefile. Everything else is in this folder.

| What | Where |
|---|---|
| Dataset v3: 100 examples with a `split` field (dev 70 / test 30) | [`week3/eval/eval_v3.jsonl`](../eval/eval_v3.jsonl) |
| How it was built (Week 2 migration, seed merge, new examples, split) | [`build_dataset.py`](build_dataset.py) → [`dataset_report.md`](dataset_report.md) (where every example came from) |
| Synthetic candidates and their review (65 generated, 10 accepted) | [`synth/generate_candidates.py`](synth/generate_candidates.py), [`synth/candidates.jsonl`](synth/candidates.jsonl), [`synth/candidates_reviewed.jsonl`](synth/candidates_reviewed.jsonl) |
| Retrieval metrics (the provided skeleton, implemented in place) | [`retrieval_metrics.py`](retrieval_metrics.py) (`python retrieval_metrics.py` runs its self-checks) |
| The eval runner: `--split`, `--retrieval-only`, Week 3 categories, deterministic scorer, separate judge, runs named by SHA and split | [`week2/task_07_eval_gate/scripts/run_eval.py`](../../week2/task_07_eval_gate/scripts/run_eval.py) (extended, not replaced) |
| Baseline (dataset v3, dev) and its tolerance | [`week2/task_07_eval_gate/eval_baseline.json`](../../week2/task_07_eval_gate/eval_baseline.json), [`tolerance_justification_v3.md`](tolerance_justification_v3.md) |
| Judge vs human (20 labels) and the judge-prompt comparison | [`human_labels.json`](human_labels.json) (**to be confirmed by the intern**), [`judge_check.py`](judge_check.py), [`evidence/judge_check.json`](evidence/judge_check.json) |
| Evidence: retrieval-only run, dev runs 1–3 (run 1 used Week 2's judge prompt; 2 and 3 built the baseline) | [`evidence/`](evidence/) |

Dev runs made with `make eval` land in `week3/eval/runs/dev/`, which is git-ignored. The runs the baseline
was built from are copied into `evidence/` so the baseline can be traced. Test runs go to
`week3/eval/runs/test/` and are committed. **None exists yet.**

## Product changes (and why they're not in this folder)

- `week1/capstone_internal_docs_assistant/app.py`
  - `corpus_files()`: a corpus export is indexed from its `_metadata.csv`, with skips logged.
  - `chunk_file()` records the corpus `path` on every chunk.
  - The stricter `CORRECTNESS_PROMPT` (eval only).
- `week1/common/settings.py`: `DATA_DIR` defaults to `week3/corpus`, `INDEX_PATH` to `faiss_index_w3`.

Without these the baseline would have been 70 refusals. Tests: `tests/test_corpus_loading.py`, plus
`tests/test_eval_gate.py::test_runner_scores_a_week3_example_with_the_deterministic_scorer` and
`::test_v3_dataset_is_complete_and_split`.

## Reproduce

```bash
export OLLAMA_BASE_URL=http://172.17.0.1:11434 LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false
make ingest                    # 118 of 190 documents; the other 72 are listed in the warning
make eval-retrieval            # recall@k / MRR by category on dev, ~8 s
make eval                      # dev, full pipeline + gemma3:4b judge, ~9 min
make eval-gate                 # the same, then the gate against eval_baseline.json (CI's job)
python week3/task_02_eval_at_scale/build_dataset.py        # rebuild eval_v3.jsonl (must reproduce it byte for byte)
python week3/task_02_eval_at_scale/judge_check.py week3/task_02_eval_at_scale/evidence/dev_full_run1.json
# make eval-test               # ONLY to confirm a decision; commit the file it writes
```
