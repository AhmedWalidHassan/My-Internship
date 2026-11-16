# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------------
# Northwind Internal Docs Assistant — container images (Week 2, Task 4)
#
# Build context = the REPO ROOT (the service imports week1/ code), so build from there:
#   docker build -f week2/task_04_containerize/Dockerfile -t northwind-api .              # API (default target)
#   docker build -f week2/task_04_containerize/Dockerfile --build-arg API_VARIANT=slim -t northwind-api:slim .
#   docker build -f week2/task_04_containerize/Dockerfile --target ui -t northwind-ui .   # Streamlit UI
# or just:  make up   (docker compose, see docker-compose.yml next to this file)
#
# What goes into the context is decided by Dockerfile.dockerignore next to this
# file: an ALLOWLIST, so .env, indexes, venvs and the rest of the repo can never be
# sent to the builder, let alone copied into a layer.
# ---------------------------------------------------------------------------
ARG PYTHON_VERSION=3.14
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
ARG API_VARIANT=full

# ---------------------------------------------------------------------------
# Build stages: install dependencies into self-contained virtualenvs, one stage per
# image (building the UI never installs torch). The runtime stages copy only the
# finished venv: no pip cache, no wheels and no build tools end up in the images.
# (No apt build dependencies needed: every package ships a manylinux wheel for
#  Python 3.14. If one ever needs compiling, install gcc HERE, never in runtime.)
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS builder-base
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY week2/task_04_containerize/constraints.txt ./

FROM builder-base AS builder-api
ARG TORCH_INDEX
# Dependencies first, source code last: editing app code must not reinstall torch.
COPY week2/task_04_containerize/requirements-api.txt ./

# API venv. torch first, from the CPU-only index: the default PyPI torch is the CUDA
# build, which drags in ~4 GB of nvidia/triton libraries that a CPU container can't use.
# Only the torch wheel comes from that index (--no-deps; it doesn't mirror every
# version of torch's dependencies). Then everything else, torch's own dependencies
# included, comes from PyPI: torch==2.15.0+cpu already satisfies the torch requirement.
# `pip check` fails the build if any dependency ended up missing.
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-deps --index-url "${TORCH_INDEX}" -c constraints.txt torch \
 && /opt/venv/bin/pip install -c constraints.txt -r requirements-api.txt \
 && /opt/venv/bin/pip check \
 && /opt/venv/bin/pip uninstall -y pip \
 && find /opt/venv -name '__pycache__' -type d -prune -exec rm -rf {} +

FROM builder-base AS builder-ui
COPY week2/task_04_containerize/requirements-ui.txt ./
# UI venv: streamlit + an HTTP client, nothing else (app/ui.py imports no RAG code).
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install -c constraints.txt -r requirements-ui.txt \
 && /opt/venv/bin/pip uninstall -y pip \
 && find /opt/venv -name '__pycache__' -type d -prune -exec rm -rf {} +


# ---------------------------------------------------------------------------
# Shared runtime base: slim Python + a non-root user. Code under /app stays
# root-owned (read-only for the app); only /data is writable.
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime-base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/opt/venv/bin:$PATH
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --create-home --home-dir /home/app --shell /usr/sbin/nologin app
WORKDIR /app


# ---------------------------------------------------------------------------
# UI image (`--target ui`)
# ---------------------------------------------------------------------------
FROM runtime-base AS ui
COPY --from=builder-ui /opt/venv /opt/venv
COPY app/ui.py /app/app/ui.py
ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    API_URL=http://api:8000
USER app
EXPOSE 8501
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=2)"]
CMD ["streamlit", "run", "app/ui.py", "--server.address=0.0.0.0", "--server.port=8501"]


# ---------------------------------------------------------------------------
# API image (the default target), in two variants: --build-arg API_VARIANT=full|slim
#   full: the local embedding model runs on PyTorch (sentence-transformers), exactly
#         what the local venv and the evals use.
#   slim: the same model on ONNX Runtime (fastembed); no torch, so roughly 1/3 the
#         size. It keeps its own index (different signature), so the two never mix vectors.
# The embedding model is baked in at build time (~90 MB): a container starts without
# reaching huggingface.co, and every container embeds with the same weights.
# Build with --build-arg PRELOAD_EMBED_MODEL= to skip it (e.g. EMBEDDING_PROVIDER=openai).
# ---------------------------------------------------------------------------
FROM builder-base AS builder-api-slim
COPY week2/task_04_containerize/requirements-api-slim.txt ./
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install -c constraints.txt -r requirements-api-slim.txt \
 && /opt/venv/bin/pip check \
 && /opt/venv/bin/pip uninstall -y pip \
 && find /opt/venv -name '__pycache__' -type d -prune -exec rm -rf {} +

FROM runtime-base AS api-full-deps
ARG PRELOAD_EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2
COPY --from=builder-api /opt/venv /opt/venv
ENV HF_HOME=/opt/hf HF_HUB_DISABLE_TELEMETRY=1 LOCAL_EMBEDDINGS_BACKEND=sentence-transformers
RUN if [ -n "${PRELOAD_EMBED_MODEL}" ]; then \
      python -c "from sentence_transformers import SentenceTransformer as S; S('${PRELOAD_EMBED_MODEL}')" \
      && find /opt/hf -name '*.lock' -delete; \
    fi

FROM runtime-base AS api-slim-deps
ARG PRELOAD_EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2
COPY --from=builder-api-slim /opt/venv /opt/venv
ENV HF_HOME=/opt/hf HF_HUB_DISABLE_TELEMETRY=1 LOCAL_EMBEDDINGS_BACKEND=fastembed \
    FASTEMBED_CACHE_PATH=/opt/fastembed
RUN if [ -n "${PRELOAD_EMBED_MODEL}" ]; then \
      python -c "from fastembed import TextEmbedding as T; T('${PRELOAD_EMBED_MODEL}')" \
      && (find /opt/hf /opt/fastembed -name '*.lock' -delete 2>/dev/null || true); \
    fi

FROM api-${API_VARIANT}-deps AS api
# Offline by default when the model is baked in; set HF_HUB_OFFLINE=0 in .env to use another model.
ENV HF_HUB_OFFLINE=1

# /data is where the FAISS index lives. docker compose mounts a named volume here; a
# new named volume copies this directory's ownership, so the non-root user can write.
RUN mkdir -p /data && chown app:app /data

# Source last (changes most often). Only what the service runs, in the repo layout
# the code expects: app/ -> week1/common -> the capstone module -> the corpus.
COPY app/ /app/app/
COPY week1/common/ /app/week1/common/
COPY week1/capstone_internal_docs_assistant/app.py /app/week1/capstone_internal_docs_assistant/app.py
COPY week1/data/ /app/week1/data/

# Container defaults for settings tied to the image layout (common/settings.py).
# Everything else (provider, model, base_url, keys, k, chunking) comes from the
# runtime environment, i.e. the .env that docker compose passes in. Never from a layer.
ENV INDEX_PATH=/data/faiss_index \
    DATA_DIR=/app/week1/data \
    API_HOST=0.0.0.0 \
    API_PORT=8000

USER app
EXPOSE 8000
# Liveness only: the process answers HTTP. (compose uses /readyz to gate the UI.)
HEALTHCHECK --interval=15s --timeout=3s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('API_PORT', '8000')}/healthz\", timeout=2)"]
# Exec form: python is PID 1 and gets SIGTERM directly, so `docker stop` shuts uvicorn
# down cleanly instead of waiting 10 s and SIGKILLing it.
CMD ["python", "-m", "app"]
