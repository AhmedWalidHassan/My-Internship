# One-command entry points (run from the repo root).
# Uses week1/.venv if it exists, otherwise whatever `python` is on PATH.
# Override with e.g.  make check PY=python3

PY ?= $(if $(wildcard week1/.venv/bin/python),week1/.venv/bin/python,python)
APP := week1/capstone_internal_docs_assistant/app.py

.PHONY: help check check-corpus check-live test-durations run run-dev run-ui run-ui-capstone bench-api up down logs eval eval-capstone eval-retrieval eval-test ingest ingest-full cost find-trace cache-bench eval-gate injection-test load-test fmt

help:
	@echo "make check       lint + fast tests   (no API key, no network, ~5 s)"
	@echo "make check-live  live golden-path tests (real model calls; needs week1/.env + model server)"
	@echo "make run         start the API on http://127.0.0.1:8000  (docs at /docs)"
	@echo "make run-ui      start the Streamlit UI (talks to the API over HTTP)"
	@echo "make bench-api   p50/p95 latency of /chat and /chat/stream against a running API"
	@echo "make up / down   API + UI in docker compose (week2/task_04_containerize/), logs: make logs"
	@echo "make cost        cost/latency per question, per node and per path over the eval set"
	@echo "make find-trace RID=<request_id>   LangSmith trace URL for a request log line"
	@echo "make cache-bench MODE=cold-warm|workload|prewarm   prove the cache's savings"
	@echo "make injection-test   7 prompt-injection attempts against a running API, judged (leak? bypass?)"
	@echo "make load-test        50 requests over 30 s against a running API (N=, SECONDS=)"
	@echo "make eval        Week 3 eval, dev split, full pipeline + judge (JUDGE_MODEL, default gemma3:4b)"
	@echo "make eval-retrieval   dev split, retrieval only (recall@k, MRR): seconds, no LLM"
	@echo "make eval-test   the frozen TEST split: only to confirm a decision (the run is committed)"
	@echo "make ingest / ingest-full   update / rebuild the index from DATA_DIR"
	@echo "make fmt         autofix lint"

# --- Task 2 ---------------------------------------------------------------
check:
	$(PY) -m ruff check .
	$(PY) -m pytest -m "not live and not corpus" -q

check-corpus:  ## every document of the Week 3 corpus through the loaders (offline, ~5 s)
	$(PY) -m pytest -m corpus -q

check-live:
	$(PY) -m pytest -m live -q -rA --durations=5

test-durations:
	$(PY) -m pytest -m "not live" -q --durations=5

fmt:
	$(PY) -m ruff check --fix .

# --- Task 3: the service --------------------------------------------------
# Host/port come from the settings (API_HOST / API_PORT in the env or week1/.env).
# 127.0.0.1 by default: the API has no auth yet. The container sets API_HOST=0.0.0.0.
run:
	$(PY) -m app

run-dev:
	$(PY) -m app --reload

run-ui:
	$(PY) -m streamlit run app/ui.py

bench-api:
	$(PY) scripts/bench_api.py

# --- Task 4: containers (files in week2/task_04_containerize/) --------------
COMPOSE := docker compose -f week2/task_04_containerize/docker-compose.yml

up:            ## build and start API + UI (needs week1/.env)
	$(COMPOSE) up --build -d
	@echo "UI  http://localhost:8501   API http://localhost:8000/docs   (make logs / make down)"

down:          ## stop and remove the containers; the index volume is kept
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=100

# --- Capstone (Week 1) ----------------------------------------------------
run-ui-capstone:
	$(PY) -m streamlit run $(APP)

eval-capstone:  ## the Week 1 LangSmith eval of the capstone's 28 built-in examples (was `make eval`)
	$(PY) $(APP) eval

# --- Task 5: observability (files in week2/task_05_observability/) ---------
cost:          ## run the eval questions and print cost/latency per question, node and path
	$(PY) week2/task_05_observability/scripts/cost_report.py

find-trace:    ## make find-trace RID=<request_id>  ->  the LangSmith trace URL
	$(PY) week2/task_05_observability/scripts/find_trace.py $(RID)

# --- Task 7 + Week 3 Task 2: the eval (runner in week2/task_07_eval_gate/scripts/run_eval.py) ----
# Dataset v3 (week3/eval/eval_v3.jsonl) with a committed dev/test split. Results go to
# week3/eval/runs/<split>/<sha>_<split>_<mode>_<time>.json (dev ignored by git, test committed).
JUDGE_MODEL ?= gemma3:4b
EVAL := $(PY) week2/task_07_eval_gate/scripts/run_eval.py

eval:           ## dev split, full pipeline, judged by a model other than the generator
	JUDGE_MODEL=$(JUDGE_MODEL) $(EVAL) --split dev --no-publish

eval-retrieval: ## dev split, retrieval only: no LLM call, seconds, ~$0 (Week 3 Task 2)
	$(EVAL) --retrieval-only --split dev

eval-test:      ## frozen TEST split: run ONLY to confirm a decision (rule 5); commit the run file
	JUDGE_MODEL=$(JUDGE_MODEL) $(EVAL) --split test --no-cache --no-publish

eval-gate:      ## dev eval on the real model, then the gate vs eval_baseline.json (what CI runs)
	JUDGE_MODEL=$(JUDGE_MODEL) $(EVAL) --split dev --out eval_results.json --no-publish
	$(PY) week2/task_07_eval_gate/scripts/check_baseline.py --results eval_results.json --report regression_report.md

# --- Week 3: ingestion (Task 3 replaces these with its own loader) --------------
ingest:         ## incremental: re-embed only new/changed documents of DATA_DIR
	$(PY) $(APP) ingest

ingest-full:    ## rebuild the whole index from scratch
	$(PY) $(APP) ingest --rebuild

# --- Task 6: caching (files in week2/task_06_caching/) --------------------
cache-bench:   ## make cache-bench MODE=cold-warm|workload|prewarm
	$(PY) week2/task_06_caching/scripts/cache_benchmark.py $(or $(MODE),cold-warm)

# --- Task 8: resilience (files in week2/task_08_resilience/) ---------------
injection-test: ## 7 prompt-injection attempts against a running API; exit 1 if any leaks or bypasses
	$(PY) week2/task_08_resilience/scripts/injection_attempts.py

load-test:     ## make load-test N=50 SECONDS=30  (start the API with CACHE_ENABLED=false to load the graph)
	$(PY) week2/task_08_resilience/scripts/load_test.py --n $(or $(N),50) --seconds $(or $(SECONDS),30)
