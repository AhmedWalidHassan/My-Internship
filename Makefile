# One-command entry points (run from the repo root).
# Uses week1/.venv if it exists, otherwise whatever `python` is on PATH.
# Override with e.g.  make check PY=python3

PY ?= $(if $(wildcard week1/.venv/bin/python),week1/.venv/bin/python,python)
APP := week1/capstone_internal_docs_assistant/app.py

.PHONY: help check check-live test-durations run run-dev run-ui run-ui-capstone bench-api up down logs eval cost fmt

help:
	@echo "make check       lint + fast tests   (no API key, no network, < 5s)"
	@echo "make check-live  live golden-path tests (real model calls; needs week1/.env + model server)"
	@echo "make run         start the API on http://127.0.0.1:8000  (docs at /docs)"
	@echo "make run-ui      start the Streamlit UI (talks to the API over HTTP)"
	@echo "make bench-api   p50/p95 latency of /chat and /chat/stream against a running API"
	@echo "make up / down   API + UI in docker compose (week2/task_04_containerize/), logs: make logs"
	@echo "make eval        run the LangSmith eval suite"
	@echo "make fmt         autofix lint"

# --- Task 2 ---------------------------------------------------------------
check:
	$(PY) -m ruff check .
	$(PY) -m pytest -m "not live" -q

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

eval:
	$(PY) $(APP) eval

# --- Task 5 (not built yet) -----------------------------------------------
cost:
	$(PY) scripts/cost_report.py
