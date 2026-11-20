# Task 4 — how the experiments were run

The brief is in [README.md](README.md). Every experiment, with its hypothesis committed before its
result, is in [`week3/EXPERIMENTS.md`](../EXPERIMENTS.md). The outcome is in
[`week3/RESULTS.md`](../RESULTS.md#task-4--retrieval-experiments) and the costs in
[`week3/COST.md`](../COST.md#task-4--winner-vs-baseline).

## Where things are

| What | Where |
|---|---|
| The retrieval levers as settings (`HYBRID_BM25_WEIGHT`, `SOURCE_PRIOR`, `RERANKER_MODEL`, `RERANK_TOP_N`, `CHUNK_CONTEXT_HEADER`, plus `CHUNK_*` and `HF_EMBED_MODEL`) | [`week1/common/retrievers.py`](../../week1/common/retrievers.py), [`week1/common/settings.py`](../../week1/common/settings.py). Product code, as the Week 3 README requires |
| Proof that the re-implemented fusion returns the Week 2 rankings exactly | [`scripts/fusion_equivalence.py`](scripts/fusion_equivalence.py) → `evidence/fusion_equivalence.json` (70/70 identical at depth 4 and 10) |
| One experiment = one config diff, retrieval-only, compared with the baseline by category | [`scripts/run_experiment.py`](scripts/run_experiment.py) → `evidence/<ID>_dev.json` + `<ID>.md` |
| Fill an experiment's result block from its evidence | [`scripts/write_result.py`](scripts/write_result.py) |
| Generation-side runs (full pipeline + judge) and `make cost` | `evidence/dev_full_{winner,EXP-11,EXP-12}.json`, `evidence/cost_seed_{baseline,winner,EXP-11,EXP-12}.md` |
| The two test runs (baseline, winner) | [`week3/eval/runs/test/`](../eval/runs/test/) |
| The retrieval gate | `check_baseline.py --retrieval-results / --retrieval-only`, `make_baseline.py --retrieval` (week2/task_07_eval_gate/scripts), the `retrieval-gate` job in `.github/workflows/ci.yml`, [`tolerance_justification.md`](tolerance_justification.md) |
| Image size | `evidence/docker_image.log` |

Each index-changing experiment builds its own index under `indexes/`, which is git-ignored.

## Reproduce

```bash
S=week3/task_04_retrieval_experiments/scripts/run_experiment.py
python $S baseline-1                                   # noise floor: run 3 times
python $S noise-fastembed --set LOCAL_EMBEDDINGS_BACKEND=fastembed CACHE_ENABLED=false
python $S EXP-01 --set HYBRID_BM25_WEIGHT=0.3
python $S EXP-06-cpu --set RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2 --cpu
python $S EXP-09 --set HYBRID_BM25_WEIGHT=0.3 "SOURCE_PRIOR=meetings/:0.5,newsletters/:0.5" CHUNK_SIZE=400 CHUNK_OVERLAP=50
make eval-retrieval                                    # what the retrieval-gate CI job runs
python week2/task_07_eval_gate/scripts/check_baseline.py --retrieval-only --retrieval-results <run.json>
```
