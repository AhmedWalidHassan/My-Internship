"""
Northwind Internal Docs Assistant — HTTP service (Week 2, Task 3).

    make run                       # uvicorn app.main:app on http://127.0.0.1:8000
    open http://127.0.0.1:8000/docs

Endpoints
    POST   /chat                  question + session_id -> answer, sources, node path (JSON)
    POST   /chat/stream           same input, Server-Sent Events: status* token* retract? ... done | error
    GET    /healthz               liveness: the process is up (never touches the model or the index)
    GET    /readyz                readiness: index loaded and graph compiled, else 503
    POST   /feedback              {trace_id, rating, comment} -> LangSmith feedback on that trace
    GET    /session/{session_id}  the conversation so far (lets a UI redraw after a page refresh)
    DELETE /session/{session_id}  forget that conversation (idempotent)
    GET    /metrics               Prometheus counters: requests, refusals, retries, tokens, cost, p50/p95

The index and graph are built ONCE, at startup, in a background thread started by
the lifespan handler: the process answers /healthz immediately, and /readyz turns
200 when loading is done. Errors always have the ErrorResponse shape.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated

from fastapi import FastAPI, Request
from fastapi import Path as PathParam
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST
from sse_starlette.sse import EventSourceResponse
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.cache import AnswerCache
from app.capstone import load_capstone
from app.config import get_settings
from app.schemas import (
    SESSION_ID_PATTERN,
    ChatRequest,
    ChatResponse,
    DoneEvent,
    ErrorResponse,
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    ReadyResponse,
    RetractEvent,
    SessionCleared,
    SessionResponse,
    StatusEvent,
    TokenEvent,
)
from app.observability import Observer, configure_structlog
from app.service import ChatService
from app.sessions import SessionStore

log = logging.getLogger("northwind.api")

EVENT_NAMES = {StatusEvent: "status", TokenEvent: "token", RetractEvent: "retract", DoneEvent: "done"}
ERROR_RESPONSES = {
    422: {"model": ErrorResponse, "description": "Invalid request"},
    500: {"model": ErrorResponse, "description": "Unexpected server error"},
    503: {"model": ErrorResponse, "description": "Still starting up, or startup failed"},
}
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._\-]{1,128}$")
SessionId = Annotated[str, PathParam(pattern=SESSION_ID_PATTERN)]


# ---------------------------------------------------------------------------
# Errors — one shape everywhere
# ---------------------------------------------------------------------------
class ApiError(Exception):
    """An error we expect and can describe to the client."""

    def __init__(self, status: int, error: str, detail: str, headers: dict | None = None):
        self.status, self.error, self.detail, self.headers = status, error, detail, headers


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _error(request: Request, status: int, error: str, detail: str | None,
           headers: dict | None = None) -> JSONResponse:
    body = ErrorResponse(error=error, detail=detail, request_id=_request_id(request))
    return JSONResponse(body.model_dump(), status_code=status, headers=headers)


async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
    return _error(request, exc.status, exc.error, exc.detail, exc.headers)


async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
    return _error(request, exc.status_code, code, str(exc.detail), getattr(exc, "headers", None))


async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Only field + message: pydantic's error objects echo the input back, and the
    # input may be a 100 KB question.
    problems = []
    for e in exc.errors():
        where = ".".join(str(p) for p in e.get("loc", ()) if p not in ("body", "path", "query"))
        problems.append(f"{where}: {e.get('msg')}" if where else str(e.get("msg")))
    return _error(request, 422, "validation_error", "; ".join(problems))


class RequestIdMiddleware:
    """Pure ASGI middleware (safe for streaming responses):

    * reuses the caller's X-Request-ID (if it looks sane) or makes one, puts it on
      request.state, and echoes it in the response header;
    * is the last line of defence: an exception nobody handled is logged here with
      its traceback and the request id, and the client gets a 500 ErrorResponse.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        incoming = dict(scope.get("headers") or []).get(b"x-request-id", b"").decode("latin-1")
        request_id = incoming if _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        started = False

        async def send_with_id(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception:
            log.exception("unhandled error request_id=%s %s %s", request_id, scope.get("method"),
                          scope.get("path"))
            if started:          # headers already sent: nothing more we can tell the client
                return
            body = ErrorResponse(error="internal_error", request_id=request_id,
                                 detail="The server hit an unexpected error. Quote the request_id "
                                        "when reporting it.")
            response = JSONResponse(body.model_dump(), status_code=500,
                                    headers={"X-Request-ID": request_id})
            await response(scope, receive, send)


# ---------------------------------------------------------------------------
# Startup: build the index + graph ONCE
# ---------------------------------------------------------------------------
@dataclass
class Runtime:
    status: str = "starting"                     # starting | ready | failed
    service: ChatService | None = None
    error: str | None = None
    startup_seconds: float = 0.0


def default_backend_factory():
    """The capstone Backend (loads or builds the FAISS index, compiles the graph),
    with conversation memory in a TTL'd store."""
    capstone = load_capstone()
    settings = get_settings()
    sessions = SessionStore(ttl_seconds=settings.session_ttl_seconds, max_sessions=settings.max_sessions)
    return capstone.Backend(sessions=sessions)


def default_feedback_client():
    """A LangSmith client, or None when no LangSmith key is configured."""
    if not (os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")):
        return None
    from langsmith import Client
    return Client()


def build_cache(settings) -> AnswerCache | None:
    """The answer cache, or None with CACHE_ENABLED=false."""
    if not settings.cache_enabled:
        return None
    return AnswerCache(ttl_seconds=settings.cache_ttl_seconds,
                       refusal_ttl_seconds=settings.cache_refusal_ttl_seconds,
                       max_entries=settings.cache_max_entries)


def prewarm(service: ChatService, n: int) -> None:
    """Answer the first N answerable eval questions so the first users hit a warm cache
    (Task 6 stretch). Runs after the API is ready; each is an ordinary logged request."""
    questions = [q for q, _a, src, _f in load_capstone().EVAL_EXAMPLES if src][:n]
    t0 = time.perf_counter()
    for i, q in enumerate(questions, 1):
        try:
            service.ask(q, f"prewarm-{uuid.uuid4()}", trace_id=str(uuid.uuid4()),
                        request_id=f"prewarm-{i:02d}", endpoint="prewarm")
        except Exception as exc:
            log.warning("prewarm question %d failed: %s: %s", i, type(exc).__name__, exc)
    log.info("cache PREWARMED with %d questions in %.1fs", len(questions), time.perf_counter() - t0)


def _load(runtime: Runtime, backend_factory: Callable, observer: Observer,
          cache: AnswerCache | None) -> None:
    """Runs in a worker thread at startup. Any failure leaves the process alive but
    not ready, so /readyz can say why instead of the process crash-looping."""
    load_capstone().setup_logging()              # the capstone's "Index BUILT / LOADED" line
    settings = get_settings()
    log.info("config: %s | cache: %s", settings.summary(),
             f"on (ttl {settings.cache_ttl_seconds:.0f}s, refusals {settings.cache_refusal_ttl_seconds:.0f}s)"
             if cache is not None else "OFF")
    t0 = time.perf_counter()
    try:
        backend = backend_factory()
        # after the backend: building it loads week1/.env, which holds the LangSmith key
        observer.linker.resolve()
        runtime.service = ChatService(backend, observer, cache)
        runtime.startup_seconds = round(time.perf_counter() - t0, 2)
        runtime.status = "ready"
        log.info("API READY in %.2fs: index %s, %d chunks from %d documents, %s retriever",
                 runtime.startup_seconds, "BUILT" if backend.ingest_stats.get("rebuilt") else "LOADED",
                 backend.n_chunks, len(backend.files), backend.retriever_name)
    except Exception as exc:
        runtime.status = "failed"
        runtime.error = f"startup failed: {type(exc).__name__}: {exc}"
        log.exception("API startup FAILED; /readyz will return 503")
        return
    if cache is not None and settings.cache_prewarm:
        prewarm(runtime.service, settings.cache_prewarm)


def create_app(backend_factory: Callable | None = None,
               feedback_client_factory: Callable | None = None) -> FastAPI:
    """Factories are injectable so the fast tests can run the real app with a fake model."""
    get_settings()          # validate the configuration now: a bad .env stops startup with a clear error
    backend_factory = backend_factory or default_backend_factory
    feedback_client_factory = feedback_client_factory or default_feedback_client
    configure_structlog()
    observer = Observer()   # one per app: the request log line + the /metrics registry
    cache = build_cache(get_settings())
    observer.metrics.bind_cache(cache)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.runtime = Runtime()
        app.state.feedback_client = None
        app.state.cache = cache
        app.state.loader = asyncio.create_task(
            asyncio.to_thread(_load, app.state.runtime, backend_factory, observer, cache))
        yield
        # Nothing to flush: sessions are in memory (see app/sessions.py), and LangSmith
        # traces are sent by the SDK's own background thread.

    app = FastAPI(
        title="Northwind Internal Docs Assistant",
        version="1.0.0",
        description="Agentic RAG over Northwind's HR, IT and product docs, with citations and "
                    "per-session memory. Streaming protocol: see POST /chat/stream.",
        lifespan=lifespan,
    )
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)

    def service(request: Request) -> ChatService:
        runtime: Runtime = request.app.state.runtime
        if runtime.service is None:
            if runtime.status == "failed":
                raise ApiError(503, "startup_failed", runtime.error)
            raise ApiError(503, "not_ready", "The index and models are still loading. Retry shortly.",
                           headers={"Retry-After": "5"})
        return runtime.service

    # -- chat -----------------------------------------------------------------
    @app.post("/chat", response_model=ChatResponse, responses=ERROR_RESPONSES, tags=["chat"])
    def chat(req: ChatRequest, request: Request) -> ChatResponse:
        """Ask one question; get the answer, its sources and the node path the graph took.

        Pass the returned `session_id` with the next question to continue the conversation.
        """
        svc = service(request)
        return svc.ask(req.question, req.session_id or str(uuid.uuid4()),
                       trace_id=str(uuid.uuid4()), request_id=_request_id(request))

    @app.post("/chat/stream", tags=["chat"], responses={
        200: {"content": {"text/event-stream": {}}, "description": (
            "Server-Sent Events, each `data` is JSON:\n\n"
            "* `status` {node, label, elapsed_ms}: a graph node finished (routing, search, grading...)\n"
            "* `token` {text}: a chunk of the answer as the model writes it (a DRAFT)\n"
            "* `retract` {reason}: the fact-check rejected the draft; discard the tokens so far\n"
            "* `done` {answer, sources, node_path, session_id, trace_id, ...}: the final, "
            "authoritative answer. Always last on success.\n"
            "* `error` {error, detail, request_id}: something failed mid-stream. Always last on failure.")},
        **ERROR_RESPONSES})
    def chat_stream(req: ChatRequest, request: Request):
        """Same input as /chat; streams the answer token by token (see the 200 response)."""
        svc = service(request)                   # not ready -> a normal 503 JSON error, not a stream
        session_id = req.session_id or str(uuid.uuid4())
        trace_id, request_id = str(uuid.uuid4()), _request_id(request)

        def events():
            try:
                for ev in svc.events(req.question, session_id, trace_id=trace_id, request_id=request_id):
                    yield {"event": EVENT_NAMES[type(ev)], "data": ev.model_dump_json()}
            except Exception:
                log.exception("stream failed request_id=%s trace_id=%s", request_id, trace_id)
                err = ErrorResponse(error="internal_error", request_id=request_id,
                                    detail="The answer could not be completed. Quote the request_id "
                                           "when reporting it.")
                yield {"event": "error", "data": err.model_dump_json()}

        # A sync generator: sse-starlette pulls it in a worker thread, so the graph's
        # blocking model calls never block the event loop.
        return EventSourceResponse(events(), ping=15)

    # -- metrics --------------------------------------------------------------
    @app.get("/metrics", tags=["ops"], response_class=PlainTextResponse, responses={
        200: {"content": {"text/plain": {}}, "description": "Prometheus text format"}})
    async def metrics() -> PlainTextResponse:
        """Live counters (Prometheus text format): requests by endpoint and status,
        refusals, rewrite retries, cache hits, LLM calls by node, tokens, estimated
        cost, time per node, a latency histogram, and rolling p50/p95 latency,
        refusal rate, mean retries and cache-hit rate. Never calls the model."""
        return PlainTextResponse(observer.metrics.render(), media_type=CONTENT_TYPE_LATEST)

    # -- probes ---------------------------------------------------------------
    @app.get("/healthz", response_model=HealthResponse, tags=["ops"])
    async def healthz() -> HealthResponse:
        """Liveness: the process is up and serving HTTP. Touches nothing else: no model,
        no index, no session store. Ready or not, this is 200."""
        return HealthResponse()

    @app.get("/readyz", response_model=ReadyResponse, responses=ERROR_RESPONSES, tags=["ops"])
    async def readyz(request: Request) -> ReadyResponse:
        """Readiness: can this instance answer questions right now? 503 until the index
        is loaded and the graph compiled (or forever, with the reason, if startup failed)."""
        svc = service(request)
        backend = svc.backend
        graph_compiled = getattr(backend.assistant, "graph", None) is not None
        if not graph_compiled or backend.n_chunks == 0:
            raise ApiError(503, "not_ready", f"graph_compiled={graph_compiled}, chunks={backend.n_chunks}")
        runtime: Runtime = request.app.state.runtime
        return ReadyResponse(
            graph_compiled=graph_compiled,
            index="built" if backend.ingest_stats.get("rebuilt") else "loaded",
            chunks=backend.n_chunks, documents=len(backend.files), retriever=backend.retriever_name,
            active_sessions=len(backend.assistant.sessions), startup_seconds=runtime.startup_seconds)

    # -- feedback -------------------------------------------------------------
    @app.post("/feedback", response_model=FeedbackResponse, tags=["chat"], responses={
        **ERROR_RESPONSES, 502: {"model": ErrorResponse, "description": "LangSmith rejected it"}})
    def feedback(req: FeedbackRequest, request: Request) -> FeedbackResponse:
        """Attach a 👍/👎 (and an optional comment) to the trace of an answer, in LangSmith."""
        if request.app.state.feedback_client is None:
            request.app.state.feedback_client = feedback_client_factory()
        client = request.app.state.feedback_client
        if client is None:
            raise ApiError(503, "feedback_unavailable",
                           "LangSmith is not configured on this server (no LANGSMITH_API_KEY), "
                           "so feedback can't be recorded.")
        try:
            client.create_feedback(run_id=req.trace_id, key="user_rating", score=req.rating,
                                   comment=req.comment)
        except Exception as exc:
            log.warning("feedback rejected trace_id=%s: %s: %s", req.trace_id, type(exc).__name__, exc)
            raise ApiError(502, "feedback_failed", "LangSmith did not accept the feedback. Try again later.")
        log.info("feedback trace_id=%s rating=%+d", req.trace_id, req.rating)
        return FeedbackResponse(trace_id=str(req.trace_id))

    # -- sessions -------------------------------------------------------------
    @app.get("/session/{session_id}", response_model=SessionResponse, responses=ERROR_RESPONSES,
             tags=["sessions"])
    def get_session(request: Request, session_id: SessionId) -> SessionResponse:
        """The turns this session remembers (empty if unknown or expired)."""
        return SessionResponse(session_id=session_id, turns=service(request).history(session_id))

    @app.delete("/session/{session_id}", response_model=SessionCleared, responses=ERROR_RESPONSES,
                tags=["sessions"])
    def reset_session(request: Request, session_id: SessionId) -> SessionCleared:
        """Forget this session's conversation. Idempotent: an unknown session is still a 200."""
        return SessionCleared(session_id=session_id, cleared=service(request).reset(session_id))

    return app


app = create_app()


if __name__ == "__main__":
    from app.__main__ import main

    main()
