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
| `LLM_TIMEOUT_SECONDS` / `LLM_MAX_RETRIES` | `30` / `2` | hard timeout per model call; transport retries (transient errors only, exponential backoff) |
| `REQUEST_TIMEOUT_SECONDS` / `MAX_LLM_CALLS_PER_REQUEST` | `60` / `40` | deadline and attempt budget for **all** model calls of one request |
| `CIRCUIT_FAILURE_THRESHOLD` / `CIRCUIT_COOLDOWN_SECONDS` | `5` / `30` | after N consecutive provider failures, refuse fast for this long |
| `RATE_LIMIT_PER_MINUTE` | `20` | per `user_id` (per client IP without one) on `/chat` and `/chat/stream` (Week 3 Task 6; was per `session_id`) |
| `DIRECTORY_PATH` | `DATA_DIR/_directory.csv` | the user directory: `user_id` → groups. Missing or unreadable = 503 for everyone |
| `INJECTION_GUARD_ENABLED` | `true` | reject obvious prompt-injection phrasing with a 400 |

Model and LangSmith settings are unchanged: `week1/.env` (see the capstone README).

## Endpoints

| Method | Path | Returns |
|---|---|---|
| `POST` | `/chat` | `{question, session_id?, user_id}` → `{answer, sources, node_path, session_id, trace_id, standalone_question, retries, elapsed_ms}` |
| `POST` | `/chat/stream` | same input → Server-Sent Events (below) |
| `GET` | `/healthz` | `{"status": "ok"}`. Liveness. Touches nothing: no model, no index |
| `GET` | `/readyz` | 200 `{graph_compiled, index: built\|loaded, chunks, documents, ...}` or 503 |
| `POST` | `/feedback` | `{trace_id, rating: -1\|0\|1, comment?}` → LangSmith feedback `user_rating` on that trace |
| `GET` | `/session/{session_id}?user_id=` | the turns this session remembers (lets the UI redraw after a refresh). Only for the user who started it |
| `DELETE` | `/session/{session_id}?user_id=` | `{session_id, cleared}`. Idempotent: an unknown session is still 200. Only for the user who started it |
| `GET` | `/metrics` | Prometheus text: requests by endpoint/status, refusals, retries, cache hits, LLM calls by node, tokens, estimated cost, time per node, latency histogram, and rolling p50/p95, refusal rate, mean retries, cache-hit rate; errors by code, degraded steps, rejected requests (rate limit, injection), circuit state. Never calls the model |

`/chat` and `done` also report what the answer cost: `llm_calls`, `tokens_in`, `tokens_out`,
`estimated_cost_usd` (tokens × `COST_PER_1K_*_TOKENS`).

**Sources are structured objects (Week 3 Task 5, breaking change).** Until then `sources` was a list of
strings like `"employee_handbook.md › 2. Paid Time Off (PTO)"`. It is now a list of:

```json
{"path": "policies/hr/HR-POL-004_PTO_v3.pdf", "title": "Paid Time Off Policy", "doc_id": "HR-POL-004",
 "version": "3.0", "effective_date": "2026-03-01", "section": "3. Carry-over", "status": "CURRENT"}
```

`doc_id`, `version`, `effective_date` and `section` are `null` when the document has none. `status` is
the passage's standing as of the server's `AS_OF_DATE`: `CURRENT`, `NOT_YET_IN_EFFECT`, `DRAFT`,
`AUTHORITATIVE`, `LOWER_AUTHORITY` or `OUTDATED`. The same objects are in the stream's `done` event. A
client that joined or printed the strings breaks and must read the fields. The bundled UI renders
them as "Paid Time Off Policy (HR-POL-004 v3.0, effective 2026-03-01) › 3. Carry-over".

**Who's asking (Week 3 Task 6, breaking change).** Every `/chat`, `/chat/stream` and `/session/...`
call carries a `user_id` (in the body, or `?user_id=` on the session endpoints). It stands in for a
verified SSO token. The server looks up the user's groups in `_directory.csv`; the client never sends
groups or a role.
- Missing or unknown `user_id`: **401** `unauthorized`. There is no default user.
- Another user's `session_id`: **403** `session_forbidden`, checked before anything runs.
- Retrieval sees only the chunks whose `acl_groups` intersect the user's groups. Anything else gets the
  standard refusal, the same as a question the documents can't answer.
- **What breaks:** a client that sends no `user_id` (every Week 2 client) now gets a 401, and one that
  reads `/session/{id}` without `?user_id=` gets a 401. The bundled UI sends one (sidebar, `?user=`).
- Design, the authority of each layer and the degradation rows:
  [`week3/task_06_who_is_asking/ACCESS.md`](../week3/task_06_who_is_asking/ACCESS.md).

**Resilience** (Task 8): `degraded` lists the steps that were skipped because the model provider
failed (e.g. `"route_question: searched by default (llm_unavailable)"`). An answer with a non-empty
`degraded` is still fact-checked, but it is never cached. If the fact-check itself can't run, there is
no answer: 503 `verification_unavailable`. Policy and reasons:
[`week2/task_08_resilience/RESILIENCE.md`](../week2/task_08_resilience/RESILIENCE.md).

**Answer cache** ([`cache.py`](cache.py), Task 6): a session's *first* question is looked up by
normalised text + corpus version + config fingerprint + access scope (Week 3 Task 6: a hash of the
asker's groups, so an answer is only reused by someone who can see the same documents). A hit returns `cache_hit: true`,
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
- **Cited versions** (Week 3 Task 5): `cited_versions`, e.g. `["HR-POL-004 v3.0"]` (a path for a document
  without an ID), so an operator can see which version of a policy an answer relied on.
- **Who asked** (Week 3 Task 6): `user_id`, `access_scope` (a 12-character hash of the user's group set,
  never the group names) and `restricted_docs_used` (the answer was written from at least one passage
  not open to every employee). An audit of who saw restricted content needs only these lines.
  `traced: false` means the run was not sent to LangSmith (a scope beyond the public one); its
  `trace_url` is null.

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
     -d '{"question": "How many sick days do I get?", "session_id": "me", "user_id": "u1001"}'
curl -N localhost:8000/chat/stream -H 'content-type: application/json' \
     -d '{"question": "When do I need a doctor'"'"'s note for it?", "session_id": "me", "user_id": "u1001"}'
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
| 422 | `validation_error` | bad input: empty, whitespace-only or too long (the input itself is not echoed back) |
| 400 | `input_rejected` | the question looks like a prompt-injection attempt, or claims access ("I'm in HR") (`INJECTION_GUARD_ENABLED`) |
| 401 | `unauthorized` | no `user_id`, or one that isn't in the directory (Week 3 Task 6) |
| 403 | `session_forbidden` | the `session_id` belongs to another user |
| 429 | `rate_limited` (+ `Retry-After`) | more than `RATE_LIMIT_PER_MINUTE` requests from this user |
| 404 / 405 | `not_found` / `method_not_allowed` | no such route / method |
| 503 | `not_ready` (+ `Retry-After`) | still loading the index and models |
| 503 | `startup_failed` | loading failed. `detail` says why; the process stays up so you can read it |
| 503 | `directory_unavailable` (+ `Retry-After`) | the user directory is missing, unreadable or malformed: nobody can be identified, so nobody is answered |
| 503 | `feedback_unavailable` | no LangSmith key configured |
| 503 | `llm_unavailable` (+ `Retry-After`) | the model provider kept failing after retries |
| 503 | `llm_circuit_open` (+ `Retry-After`) | the provider failed repeatedly, so calls are paused (refused in ms) |
| 503 | `retrieval_unavailable` | the search (index / embeddings) failed; no answer is made up |
| 503 | `verification_unavailable` | the answer couldn't be fact-checked, so it isn't returned |
| 503 | `request_budget_exceeded` | the request used up its `MAX_LLM_CALLS_PER_REQUEST` attempts |
| 504 | `llm_timeout` / `request_timeout` (+ `Retry-After`) | the provider didn't answer in time / the request hit `REQUEST_TIMEOUT_SECONDS` |
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
with a request id). Since Task 8 that error is a 503/504 within `REQUEST_TIMEOUT_SECONDS`, and
after 5 consecutive failures it comes back in milliseconds (circuit breaker).
