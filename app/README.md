# The service: `app/`

The Northwind assistant as an HTTP service (Week 2, Task 3). The RAG logic (index,
hybrid retriever, LangGraph graph, per-session memory) still lives in exactly one
place, [`week1/capstone_internal_docs_assistant/app.py`](../week1/capstone_internal_docs_assistant/app.py).
This package is the service around it, and the Streamlit UI is a client of the
service over HTTP.

| File | What it is |
|---|---|
| [`main.py`](main.py) | FastAPI app: routes, lifespan startup, error shape, request ids |
| [`service.py`](service.py) | `ChatService`, the **one** place the graph is run from (`/chat` and `/chat/stream` are both views of it) |
| [`schemas.py`](schemas.py) | Pydantic models for every request, response and stream event |
| [`sessions.py`](sessions.py) | Conversation memory with a sliding TTL and a size bound |
| [`capstone.py`](capstone.py) | Loads the capstone module once (shared with the tests) |
| [`ui.py`](ui.py) | Streamlit chat UI. Imports no graph code: HTTP only |

## Run it

```bash
ollama serve &              # or any provider configured in week1/.env
make run                    # API on http://127.0.0.1:8000, OpenAPI docs at /docs
make run-ui                 # UI on http://localhost:8501 (API_URL defaults to http://127.0.0.1:8000)
```

Startup builds the index and graph **once**, in a background thread started by the
lifespan handler. `/healthz` answers immediately; `/readyz` is 503 until loading is
done (about 8–11 s locally, almost all of it the embedding model loading), then 200.
The log says whether the index was built or loaded:

```
INFO northwind: Index LOADED from .../faiss_index in 0.02s: 20 chunks from 4 files, 0 chunks embedded
INFO northwind.api: API READY in 10.73s: index LOADED, 20 chunks from 4 documents, hybrid (BM25 + dense) retriever
```

Settings come from the environment or `week1/.env`, through the typed settings object in
[`week1/common/settings.py`](../week1/common/settings.py) (`app/config.py` re-exports it).

| Setting (env) | Default | Meaning |
|---|---|---|
| `API_HOST` / `API_PORT` | `127.0.0.1` / `8000` | bind address (`make run` = `python -m app`). Localhost by default: there is no auth yet |
| `SESSION_TTL_SECONDS` | `3600` | a conversation is forgotten after this long without activity |
| `MAX_SESSIONS` | `10000` | least recently used sessions are dropped beyond this |
| `MAX_QUESTION_CHARS` | `2000` | longer questions get a 422 |
| `API_URL` (UI only) | `http://127.0.0.1:8000` | where the Streamlit UI sends requests |

Model and LangSmith settings are unchanged: `week1/.env` (see the capstone README).

## Endpoints

| Method | Path | Returns |
|---|---|---|
| `POST` | `/chat` | `{question, session_id?}` → `{answer, sources, node_path, session_id, trace_id, standalone_question, retries, elapsed_ms}` |
| `POST` | `/chat/stream` | same input → Server-Sent Events (below) |
| `GET` | `/healthz` | `{"status": "ok"}`. Liveness. Touches nothing: no model, no index |
| `GET` | `/readyz` | 200 `{graph_compiled, index: built\|loaded, chunks, documents, ...}` or 503 |
| `POST` | `/feedback` | `{trace_id, rating: -1\|0\|1, comment?}` → LangSmith feedback `user_rating` on that trace |
| `GET` | `/session/{session_id}` | the turns this session remembers (lets the UI redraw after a refresh) |
| `DELETE` | `/session/{session_id}` | `{session_id, cleared}`. Idempotent: an unknown session is still 200 |
| `GET` | `/metrics` | Prometheus text: requests by endpoint/status, refusals, retries, cache hits, LLM calls by node, tokens, estimated cost, time per node, latency histogram, and rolling p50/p95, refusal rate, mean retries, cache-hit rate. Never calls the model |

`/chat` and `done` also report what the answer cost: `llm_calls`, `tokens_in`, `tokens_out`,
`estimated_cost_usd` (tokens × `COST_PER_1K_*_TOKENS`).

**Answer cache** ([`cache.py`](cache.py), Task 6): a session's *first* question is looked up by
normalised text + corpus version + config fingerprint. A hit returns `cache_hit: true`,
`node_path: ["cache"]`, `llm_calls: 0` and `cached_from_trace_id`, in under 1 ms. Follow-ups always
run the graph. Adding or changing a document invalidates every entry. Refusals expire after 5 min.
`CACHE_ENABLED=false` turns it off. Design and numbers: [`week2/task_06_caching/CACHING.md`](../week2/task_06_caching/CACHING.md).

### One log line per request

Every request (ok, error, or a stream the client abandoned) writes **one** JSON line to stdout
([`observability.py`](observability.py), structlog). It holds:
- **The ids:** `request_id`, `session_id`, `trace_id`, `trace_url`.
- **What happened:** `endpoint`, `status`, `route`, `node_path`, `retries`, `refused`, `cache_hit`.
- **The cost:** `latency_ms` (`ttft_ms` when streaming), `llm_calls`, `tokens_in`, `tokens_out`,
  `estimated_cost_usd`, `model`.
- **Per node:** `per_node` (runs, ms, LLM calls, LLM ms and tokens for each graph node).
- **Retrieval:** `retrieved_ids` and `kept_ids`, the chunk ids (`file.md::3`), to tell retrieval
  drift from generation drift.

`trace_id` is the LangSmith root-run id and `trace_url` links straight to it. The trace also
carries `request_id` and `session_id` as metadata. The per-node figures come from a LangChain
callback handler attached to each run, so the graph code itself isn't wrapped. Write-up and
measurements: [`week2/task_05_observability/`](../week2/task_05_observability/OBSERVABILITY.md).

Omit `session_id` to start a conversation; the response carries the id to send
next time. `trace_id` is the id of the LangSmith root run of that answer, so
`/feedback` needs no lookup, and every trace carries the `request_id` and
`session_id` in its metadata.

```bash
curl -s localhost:8000/chat -H 'content-type: application/json' \
     -d '{"question": "How many sick days do I get?", "session_id": "me"}'
curl -N localhost:8000/chat/stream -H 'content-type: application/json' \
     -d '{"question": "When do I need a doctor'"'"'s note for it?", "session_id": "me"}'
```

### Streaming protocol (`POST /chat/stream`)

Each event's `data` is one JSON object:

| `event:` | `data` | When |
|---|---|---|
| `status` | `{node, label, elapsed_ms}` | a graph node finished (route, search, grading, ...). Shown while nothing can stream yet |
| `token` | `{text}` | a chunk of the answer, as the model writes it. **A draft** |
| `retract` | `{reason}` | the fact-check rejected the draft streamed so far: discard it (a new draft may follow) |
| `done` | same fields as the `/chat` response | the final, fact-checked answer. Always the last event on success |
| `error` | `{error, detail, request_id}` | the answer failed mid-stream. Always the last event on failure |

The honest constraint: the graph routes and grades documents **before** it
generates, so the first ~1.2 s are `status` events only, and it fact-checks
**after** generating. Tokens are therefore streamed as a draft, and
`done.answer` is authoritative (it also has the `Sources:` line removed). A client
should render tokens as they come, clear them on `retract`, and replace them with
`done.answer` at the end. Refusals and small talk produce no tokens: their answer
is only in `done`.

An error **before** the stream starts (not ready, invalid input) is an ordinary
JSON error response with a status code, not an event.

### Errors

Every error, from any endpoint, has one shape, and never contains a stack trace:

```json
{"error": "validation_error", "detail": "question: String should have at most 2000 characters", "request_id": "5f0c..."}
```

| Status | `error` | Meaning |
|---|---|---|
| 422 | `validation_error` | bad input (the input itself is not echoed back) |
| 404 / 405 | `not_found` / `method_not_allowed` | no such route / method |
| 503 | `not_ready` (+ `Retry-After`) | still loading the index and models |
| 503 | `startup_failed` | loading failed. `detail` says why; the process stays up so you can read it |
| 503 | `feedback_unavailable` | no LangSmith key configured |
| 502 | `feedback_failed` | LangSmith rejected the feedback |
| 500 | `internal_error` | anything unexpected. The traceback is in the server log under the same `request_id` |

Every response carries an `X-Request-ID` header: the caller's own value if it sent
a sane one (so a load balancer's id flows through), otherwise a generated one.

## The two questions

**1. Where does session state live, and what breaks with two workers?**

In the API process's memory: a `SessionStore` (dict + sliding TTL) handed to the
capstone `Assistant`. With `uvicorn --workers 2` each worker has its own store, so
a follow-up that lands on the other worker has no history ("it" is never
resolved), `DELETE /session/{id}` clears only one copy, and `GET /session/{id}`
depends on which worker answers. A restart loses every conversation (verified:
after a restart `GET /session/demo-curl` is empty). Each worker also loads its own
copy of the index and the embedding model. What I'd do: move the store to Redis
(one key per session, `EXPIRE` = the TTL, or a LangGraph checkpointer with
`thread_id = session_id`). The Assistant only needs a dict-like object, so the
graph doesn't change. Sticky sessions would hide the problem but still lose every
conversation on a restart or deploy.

**2. What does `/readyz` check that `/healthz` doesn't, and why does it matter to a load balancer?**

`/healthz` only proves the process is alive and serving HTTP; it touches nothing
else, so it is ~0.4 ms and never fails because the model provider is slow.
`/readyz` checks that this instance can **answer questions**: the index is loaded
(more than 0 chunks), the graph is compiled, and startup didn't fail. A load balancer
(or Kubernetes) uses the two differently. Readiness decides whether to **send
traffic**: during the ~10 s startup, or after a failed startup, the instance is
taken out of rotation instead of returning 503s to users. Liveness decides whether to
**restart** the process. If liveness checked the index or the model, a slow
startup or a provider outage would get healthy processes killed in a loop, and
every probe would cost a model call. `/readyz` deliberately does **not** call the
LLM either. If the provider is down, the error shows up on `/chat` (structured,
with a request id); Task 8 adds timeouts and a degradation path for that.
