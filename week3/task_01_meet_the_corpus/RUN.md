# Task 1 — how the numbers were produced

The brief is in [README.md](README.md). The numbers are in
[`week3/RESULTS.md`](../RESULTS.md#task-1--meet-the-corpus) and [`week3/COST.md`](../COST.md#task-1--embedding-the-real-corpus).
This page lists what is in this folder and how to reproduce it.

No product code was changed for the baseline. The only things that change are `DATA_DIR` and a new
`INDEX_PATH`, so the Week 2 index is left alone (reusing it would rewrite it; see
`evidence/loader_behaviour.log`).

## What's here

| File | What it is |
|---|---|
| `scripts/run_seed_eval.py` | The 40 seed examples through Week 2's own `score_example` (graph without the answer cache, Week 2 judges, per-node cost), plus the deterministic scorer (`week3/eval/scoring.py`) and a document-level signal: was a gold document indexed, retrieved, and kept by the grader. Not a second eval runner: it adapts the Week 3 format to the Week 2 one |
| `scripts/corpus_view.py` | Builds the "recursive view": a folder of symlinks to every `.md`/`.txt` in the corpus, which is what a recursive walk would feed the unchanged Week 2 loader |
| `scripts/profile_corpus.py` | Corpus profile (per document: source, format, loaded or skipped, chars, chunks, language), measured index builds and embedding tokens/cost, and the data-quality evidence |
| `docker-compose.corpus.yml` | Compose override: mounts the corpus read-only and points `DATA_DIR`/`INDEX_PATH` at it (the Week 2 compose file pins `DATA_DIR`, so `.env` can't) |
| `w2_eval_triage.jsonl` | All 38 Week 2 eval examples: verdict, updated reference answer and source document, scores in both configurations. Task 2 migrates from this file |
| `evidence/seed_eval_{literal,recursive}.{json,md,log}` | The cliff: per category and per example |
| `evidence/w2_gate_*` | The Week 2 eval gate (38 examples) on the new corpus, and its comparison with the archived baseline |
| `evidence/cost_report_seed_*` | `make cost` on the seed set: cost, per node, node-path distribution |
| `evidence/check_live_*.log` | The live tier: before the triage (shipped / recursive), and after it (Week 1 corpus / Week 3 recursive view) |
| `evidence/corpus_profile{,_cpu}.{json,md}` | Profile and index builds on the GPU and on the CPU |
| `evidence/docker_*.log` | `docker compose up` with the corpus mounted: build, first start, restart |
| `evidence/loader_behaviour.log` | What the unchanged loader does with the new path, and with the old index path |

## Reproduce

From the repo root. Ollama must be running (here it's bound to the Docker bridge, hence the base URL).

```bash
export OLLAMA_BASE_URL=http://172.17.0.1:11434 LANGSMITH_TRACING=false
T=week3/task_01_meet_the_corpus; PY=week1/.venv/bin/python
pip install -r week3/requirements.txt          # profile only (PyMuPDF, openpyxl, tiktoken, datasketch)

# 1. the system as shipped (iterdir: indexes README.md only)
export DATA_DIR=$PWD/week3/corpus INDEX_PATH=$PWD/$T/faiss_index_w2_literal
# 1'. or the recursive view (every .md/.txt)
export DATA_DIR=$($PY $T/scripts/corpus_view.py) INDEX_PATH=$PWD/$T/faiss_index_w2_recursive

$PY $T/scripts/run_seed_eval.py --label literal --out $T/evidence/seed_eval_literal.json
$PY week2/task_07_eval_gate/scripts/run_eval.py --out $T/evidence/w2_gate_results_literal.json --no-publish
EVAL_DATASET_PATH=week3/eval/seed_eval.jsonl make cost
make check-live

# profile + measured embedding (GPU; prefix CUDA_VISIBLE_DEVICES= for the CPU numbers)
$PY $T/scripts/profile_corpus.py --out $T/evidence/corpus_profile

# Docker with the corpus mounted
docker compose -f week2/task_04_containerize/docker-compose.yml -f $T/docker-compose.corpus.yml up -d --build --wait
```

Indexes and the embedding cache created under this folder are git-ignored (`week3/.gitignore`).
