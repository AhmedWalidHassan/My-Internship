# Running the assistant in containers (Week 2, Task 4)

> **Week 3 Task 3:** the API now reads the Week 3 corpus export, mounted read-only from `week3/corpus` at
> `/corpus`, with its index at `/data/faiss_index_w3` on the same named volume (the Week 1 index at
> `/data/faiss_index` is left alone). The image gained PyMuPDF, openpyxl and BeautifulSoup (+285 MB).
> `/readyz` reports the corpus snapshot, document counts and index build time. See
> `week3/task_03_ingestion/RUN.md`.

The brief is in [README.md](README.md). This page covers how it was done: how to run it,
what each file is for, and the evidence for every "Done when…" item.

## Run it

```bash
git clone <repo> && cd My-Internship
cp week1/.env.example week1/.env     # the ONLY file you supply: pick a provider, add its key
make up                              # build + start API and UI
#   UI   http://localhost:8501
#   API  http://localhost:8000/docs
make logs                            # follow the logs   ·   make down: stop (the index volume is kept)
API_VARIANT=slim make up             # the under-1 GB image (same answers; see "Image size")
```

`make up` is `docker compose -f week2/task_04_containerize/docker-compose.yml up --build -d`.
The compose file lives in this folder and builds with the **repo root** as context, because
the service imports `week1/` code.

**Using a local Ollama from the containers.** The API container reaches the host through
`host.docker.internal`, which [`container.env`](container.env) points `OLLAMA_BASE_URL` at.
For that to work:

1. Ollama must listen on more than loopback: `OLLAMA_HOST=0.0.0.0 ollama serve`. Safer is
   `OLLAMA_HOST=172.17.0.1`, the Docker bridge address: reachable from containers, not from the LAN.
2. If the host runs **ufw** (it does on this machine), allow Docker networks to reach that one port:
   `sudo ufw allow from 172.16.0.0/12 to any port 11434 proto tcp comment 'docker -> ollama'`.
   Without this rule, every question times out (`httpx.ConnectTimeout` in `make logs`) while
   `/readyz` still says ready, because readiness deliberately doesn't call the model.

Hosted providers (OpenAI, OpenRouter, Groq) need neither step.

## Files

| File | What it is |
|---|---|
| [`Dockerfile`](Dockerfile) | Multi-stage, three images from one file: `api` (default target, `API_VARIANT=full\|slim`) and `ui` |
| [`Dockerfile.dockerignore`](Dockerfile.dockerignore) | An **allowlist** of the build context: everything is excluded except the files the images copy. `.env` can't reach the builder |
| [`docker-compose.yml`](docker-compose.yml) | API + UI. Named index volume, `.env` passed at runtime, ports on localhost, UI waits for API readiness |
| [`container.env`](container.env) | Container-only defaults (where the host's Ollama is). Committed, no secrets; your `.env` overrides it |
| [`requirements-api.txt`](requirements-api.txt) / [`-api-slim.txt`](requirements-api-slim.txt) / [`-ui.txt`](requirements-ui.txt) | Only what each image imports (not the Week 1 task dependencies) |
| [`constraints.txt`](constraints.txt) | Exact versions frozen from the tested venv, so the image runs what the tests ran |
| [`evidence/`](evidence/) | The verification logs referenced below |

The configuration code is in the product, not in this folder, because the brief requires
these values to stop being literals in the source:
[`week1/common/settings.py`](../../week1/common/settings.py), used by `common/utils.py`, the
capstone and `app/` (via `app/config.py`).

## Configuration: nothing in the brief's list is a literal any more

One typed `Settings` object (pydantic-settings) is read once and validated at startup.
Precedence: real environment (docker compose) > `week1/.env` > defaults. Defaults equal the old
hardcoded values, so nothing changed by moving them.

| Setting (brief) | Before | Now (env var, default) |
|---|---|---|
| Model / provider | env | `LLM_PROVIDER`, `OPENAI_MODEL` / `GROQ_MODEL` / `OLLAMA_MODEL`, `EMBEDDING_PROVIDER` |
| `base_url` | env, read in `common/utils.py` | `OPENAI_BASE_URL`, `GROQ_BASE_URL`, `OLLAMA_BASE_URL` (unset = provider default) |
| Retriever `k` | `TOP_K = 4` | `RETRIEVER_K=4` |
| Chunk size / overlap | `800, 100` | `CHUNK_SIZE=800`, `CHUNK_OVERLAP=100` (overlap ≥ size is rejected at startup) |
| Index path | derived from `__file__` | `INDEX_PATH` (default: next to the capstone; `/data/faiss_index` in docker) |
| API host / port | uvicorn CLI flags in the Makefile | `API_HOST=127.0.0.1`, `API_PORT=8000`; `make run` is now `python -m app` |
| *(also)* | | `DATA_DIR`, `SESSION_TTL_SECONDS`, `MAX_SESSIONS`, `MAX_QUESTION_CHARS`, `LOG_LEVEL`, `LLM_TEMPERATURE`, `OPENAI_REASONING_EFFORT`, `LOCAL_EMBEDDINGS_BACKEND` |

- **Keys are deliberately not settings.** The SDKs read them from the environment themselves, so
  they never sit on an object that gets logged. The startup log prints the resolved config
  (`config: llm=ollama:qwen3.5:4b base_url=… k=4 chunks=800/100 index=/data/faiss_index`)
  with no secrets in it.
- **Bad config fails at startup:** `LLM_PROVIDER=olama`, `RETRIEVER_K=0` or `CHUNK_OVERLAP=CHUNK_SIZE`
  stop the process with a pydantic error naming the field, instead of failing on the first
  question. ([`tests/test_settings.py`](../../tests/test_settings.py))
- `INDEX_PATH`, `DATA_DIR`, `API_HOST` and `API_PORT` are pinned by compose's `environment:` in
  the container: they describe the image layout, so a laptop path in `.env` can't break it.

## Switching provider = editing `.env`

| Provider | `.env` block |
|---|---|
| OpenAI | `LLM_PROVIDER=openai`, `OPENAI_API_KEY=sk-…`, `OPENAI_MODEL=gpt-4o-mini` |
| OpenRouter | `LLM_PROVIDER=openai`, `OPENAI_BASE_URL=https://openrouter.ai/api/v1`, `OPENAI_API_KEY=sk-or-…`, `OPENAI_MODEL=meta-llama/llama-3.3-70b-instruct` |
| Groq | `LLM_PROVIDER=groq`, `GROQ_API_KEY=gsk_…`, `GROQ_MODEL=llama-3.3-70b-versatile` |
| Ollama | `LLM_PROVIDER=ollama`, `OLLAMA_MODEL=qwen3.5:4b` |
| Any OpenAI-compatible server (vLLM, LiteLLM, Ollama `/v1`) | like OpenRouter, with that server's URL; add `OPENAI_REASONING_EFFORT=none` for a thinking model |

Demonstrated in the running containers ([`evidence/provider_switch.log`](evidence/provider_switch.log)).
The image was never rebuilt; each step was a `.env` edit plus `docker compose up -d`:

1. **Ollama native:** "10 paid sick days per year", cited, 2.3 s.
2. **OpenAI code path → Ollama's OpenAI-compatible `/v1`:** the same answer through `ChatOpenAI`,
   2.2 s. That is the exact mechanism OpenRouter uses.
3. **OpenRouter** and 4. **Groq:** the container logs `llm=openai:meta-llama/… base_url=https://openrouter.ai/api/v1`
   and `llm=groq:llama-3.3-70b-versatile`, and the client built inside the container points
   there. There are no OpenRouter/Groq/OpenAI keys on this machine, so no question was sent.
   That path is proven by step 2 and by `tests/test_settings.py::test_switching_provider_needs_only_env_changes`,
   which builds every provider's real client from env vars alone.

**Found while demonstrating it:** the first try of step 2 took minutes per question. Through
an OpenAI-compatible endpoint, qwen3.5 *thinks* before answering: 400–1,200+ hidden tokens for
a one-word `RETRIEVE` grader reply. The native Ollama client disables that (`reasoning=False`);
the OpenAI client had no way to. That is now a setting, `OPENAI_REASONING_EFFORT=none` (2 tokens
instead of 400+). It's sent only when set, because gpt-4o-mini rejects the parameter. Switching
provider is config-only, but the same model can behave differently behind a different API.

## Image size

| Image | On disk (files) | Download (compressed) | `docker images` "disk usage" |
|---|---:|---:|---:|
| `northwind-api:full` (default) | **1.50 GB** | 489 MB | 2.07 GB |
| `northwind-api:slim` | **575 MB** | 241 MB | 847 MB |
| `northwind-ui` | 513 MB | 163 MB | 703 MB |

("Disk usage" with Docker's containerd image store counts the unpacked files **plus** the
compressed layers it keeps, so it is not the size of anything you ship.)

**Biggest contributor: PyTorch, 747 MB of the API's 1.29 GB of Python packages, there only to
run the 90 MB MiniLM embedding model.** The default PyPI torch would have been far worse: it is
the CUDA build, with 3.0 GB of nvidia libraries plus 1.0 GB of triton (that is the local venv),
so the image installs the **CPU** wheel from pytorch.org.
Next biggest: scipy (81 MB) and transformers (58 MB), both pulled in by sentence-transformers.
In the UI image, pyarrow (166 MB, a Streamlit dependency) is the largest.

What the build leaves out:

- Only service dependencies are installed. Not unstructured, chromadb, pypdf or tiktoken (Week 1
  task dependencies), not streamlit in the API image, not pytest/ruff.
- No wheels or pip cache in any layer: venvs are built in a builder stage and only the finished
  venv is copied, and pip itself is removed from it.

**Stretch: under 1 GB.** `API_VARIANT=slim` runs the **same** model on ONNX Runtime
(fastembed) instead of PyTorch. That drops torch, sentence-transformers, transformers, scipy and
scikit-learn: 1.50 GB → **575 MB**.

- **Same embeddings:** cosine similarity 1.000000 on all 20 chunks and all 28 eval questions, and
  identical dense top-4 for 28/28 ([`evidence/slim_embeddings_equivalence.txt`](evidence/slim_embeddings_equivalence.txt)).
- **Same answers:** sick days, rover speed, and the CEO-address refusal ([`evidence/slim_variant.log`](evidence/slim_variant.log)).
- **Faster start:** ready in **1.2 s instead of 9–10 s**, because importing torch was most of
  the startup.
- **Separate index:** each variant has its own index signature and volume, so their vectors
  never mix.

It isn't the default only because the evals and tests ran on the PyTorch path. I'd switch
after one eval run on the slim image.

## Evidence for "Done when…"

| Check | Result | Evidence |
|---|---|---|
| `docker compose up` from a clean checkout, only `.env` supplied | Fresh `git clone` into an empty directory, `week1/.env` copied in, `build --no-cache` + `up --wait`: both containers healthy in 157 s. Cited answer and refusal over HTTP; UI container drives a two-turn conversation through `http://api:8000` | [`evidence/clean_checkout.log`](evidence/clean_checkout.log), [`evidence/ui_in_container.txt`](evidence/ui_in_container.txt) |
| No API key in any layer | The `LANGSMITH_API_KEY` **value** was searched for in `docker history --no-trunc`, `docker image inspect` and the entire exported filesystem of both images: not found; no `.env` file in either image. The key reaches the running container at runtime only | [`evidence/no_secrets_in_layers.md`](evidence/no_secrets_in_layers.md) |
| Provider switch by `.env` only | See above | [`evidence/provider_switch.log`](evidence/provider_switch.log) |
| Image size + biggest contributor | See above | |
| Non-root | `whoami` → `app` (uid 10001) in both containers. `/app` (code) is root-owned and read-only (`touch` → Permission denied); only `/data` is writable | [`evidence/non_root_and_contents.txt`](evidence/non_root_and_contents.txt) |
| Restart does not re-embed | First `up` on a new volume: `Index BUILT: embedded 20 chunks`. After `restart`, after `down`+`up` (containers deleted), and after a code edit + image rebuild: `Index LOADED … 0 chunks embedded` | [`evidence/volume_persistence.log`](evidence/volume_persistence.log) |

Also verified: a code-only change rebuilds in **3.6 s**, because dependency layers come before
the source. `HEALTHCHECK` is `/healthz` in the image (liveness), and compose overrides it with
`/readyz`, so `depends_on: service_healthy` means "can answer", not just "process up".

## Choices that differ from the skeleton

- **Python 3.14, not 3.12:** the version the venv and tests run. `constraints.txt` pins every
  package to the tested versions.
- **Venv copy instead of "copy wheels, install, delete":** a `COPY` of wheels is its own layer,
  so deleting them later shrinks nothing. Copying the finished venv adds exactly the installed
  packages. (Each venv is built at its final path, `/opt/venv`: a venv isn't relocatable. The
  first build put the UI's at `/opt/venv-ui` and its `streamlit` launcher failed with "no such
  file or directory".)
- **Separate UI image** (streamlit + httpx only, 513 MB) instead of running Streamlit in the API
  image: the UI imports no RAG code, so it shouldn't carry torch.
- **The embedding model is baked into the image** (`HF_HUB_OFFLINE=1`): containers start without
  internet access to huggingface.co, and every replica embeds with identical weights.
- **Ports bound to 127.0.0.1** (`API_PUBLISH` / `UI_PUBLISH` to change): the API has no auth yet.
- **`.env` stays `week1/.env`:** one file configures the CLI, `make run` and the containers.

## Known limits

- Sessions are in process memory: a container restart forgets conversations, and the index
  survives but chats don't. Same root cause as the two-worker problem in `app/README.md`.
- The compose project name is fixed (`northwind`), so two checkouts on one host share
  containers and volumes. That's intended for one deployment per host.
- `/readyz` doesn't check the model provider, so an unreachable Ollama shows up on `/chat`, not
  on readiness (Task 8: timeouts and degradation).
