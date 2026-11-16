# One-command entry points (run from the repo root).
# Uses week1/.venv if it exists, otherwise whatever `python` is on PATH.
# Override with e.g.  make check PY=python3

PY ?= $(if $(wildcard week1/.venv/bin/python),week1/.venv/bin/python,python)
APP := week1/capstone_internal_docs_assistant/app.py

.PHONY: help check check-live test-durations run run-ui eval cost fmt

help:
	@echo "make check       lint + fast tests   (no API key, no network, < 5s)"
	@echo "make check-live  live golden-path tests (real model calls; needs week1/.env + model server)"
	@echo "make run-ui      start the Streamlit UI"
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

# --- Capstone (Week 1) ----------------------------------------------------
run-ui:
	$(PY) -m streamlit run $(APP)

eval:
	$(PY) $(APP) eval

# --- Task 3 / Task 5 (not built yet) --------------------------------------
run:
	$(PY) -m uvicorn app.main:app --reload --host $${API_HOST:-0.0.0.0} --port $${API_PORT:-8000}

cost:
	$(PY) scripts/cost_report.py
