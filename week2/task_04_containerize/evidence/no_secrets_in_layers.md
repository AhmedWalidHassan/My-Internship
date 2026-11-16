# Week 2 Task 4: no secret in any image. Run 2026-11-16 against the images built
# from a fresh clone. Secret VALUES are read from week1/.env and searched for; they are never printed.
# Secret variables checked: ['LANGSMITH_API_KEY']

## northwind-api:full
- `docker history --no-trunc` (27 layers): secret values found: none
- `docker image inspect` (ENV, labels, config): secret values found: none
- whole filesystem (`docker export`, 1502 MB scanned): secret values found: none; `.env` files: none
- ENV baked in: PATH, LANG, PYTHON_VERSION, PYTHON_SHA256, PYTHONUNBUFFERED, PYTHONDONTWRITEBYTECODE, HF_HOME, HF_HUB_DISABLE_TELEMETRY, LOCAL_EMBEDDINGS_BACKEND, HF_HUB_OFFLINE, INDEX_PATH, DATA_DIR, API_HOST, API_PORT

## northwind-ui:latest
- `docker history --no-trunc` (19 layers): secret values found: none
- `docker image inspect` (ENV, labels, config): secret values found: none
- whole filesystem (`docker export`, 513 MB scanned): secret values found: none; `.env` files: none
- ENV baked in: PATH, LANG, PYTHON_VERSION, PYTHON_SHA256, PYTHONUNBUFFERED, PYTHONDONTWRITEBYTECODE, STREAMLIT_SERVER_HEADLESS, STREAMLIT_BROWSER_GATHER_USAGE_STATS, API_URL
