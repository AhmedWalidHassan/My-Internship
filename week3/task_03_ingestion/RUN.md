# Task 3 — what was built, and how to reproduce it

The brief is in [README.md](README.md). The numbers are in [`week3/RESULTS.md`](../RESULTS.md#task-3--ingestion),
[`week3/COST.md`](../COST.md#task-3--ingestion) and [`week3/EXPERIMENTS.md`](../EXPERIMENTS.md) (ING-01:
the hypothesis was committed and pushed in its own commit before any loader code existed).

## Where things are

Product code goes where the Week 3 README puts it (`ingest/`, `tests/`, the capstone, the container).
The write-up, the measurement script and the evidence are in this folder.

| What | Where |
|---|---|
| Loaders, normalisation, metadata, chunking, dedup | [`ingest/`](../../ingest/): `loaders.py`, `normalize.py`, `pipeline.py`, `dedup.py` |
| Why each format looks the way it does, metadata, dedup policy, incremental contract | [`LOADERS.md`](LOADERS.md) |
| Incremental ingest, skip reasons, ingestion report, JSON log line | `ingest()` / `corpus_files()` / `_write_ingestion_report()` in [`week1/capstone_internal_docs_assistant/app.py`](../../week1/capstone_internal_docs_assistant/app.py) |
| `/readyz`: corpus snapshot, document counts, index build time | [`app/main.py`](../../app/main.py), [`app/schemas.py`](../../app/schemas.py) |
| Container: corpus mounted read-only, index on the volume, loaders in the image | [`week2/task_04_containerize/`](../../week2/task_04_containerize/) (`docker-compose.yml`, `Dockerfile`, requirements, constraints) |
| Tests | [`tests/test_ingest.py`](../../tests/test_ingest.py) (loaders; the slow real-PDF ones are marked `corpus`), [`tests/test_corpus_loading.py`](../../tests/test_corpus_loading.py) (incremental re-embed + cache invalidation, skips, `/readyz`) |
| Full / incremental re-ingest cost | [`scripts/measure_ingest.py`](scripts/measure_ingest.py) → `evidence/ingest_cost_{gpu,cpu}.json` |
| Evidence | [`evidence/`](evidence/): dev retrieval after, 2 full dev runs (the new baseline), the gate against the Task 2 baseline, the ingestion report, Docker build and up logs, live tier, image sizes |
| New baseline justification | [`tolerance_justification.md`](tolerance_justification.md) |

## Reproduce

```bash
export OLLAMA_BASE_URL=http://172.17.0.1:11434 LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false
make ingest-full            # 190/190 documents, 348 chunks; writes ingestion_report.json next to the index
make eval-retrieval         # dev recall@5 0.917, MRR 0.612
make check                  # fast tier (pytest ~4.5 s)
make check-corpus           # the real-PDF loader tests and all 190 documents through the loaders (5–9 s)
make eval                   # dev, full pipeline + gemma3:4b judge (~11 min)
CACHE_ENABLED=false python week3/task_03_ingestion/scripts/measure_ingest.py --out /tmp/ingest_cost.json
make up                     # the container mounts week3/corpus read-only; a warm volume logs "Index LOADED"
curl -s localhost:8000/readyz   # corpus_snapshot, documents, documents_skipped, index_built_at, ...
```
