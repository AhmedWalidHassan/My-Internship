"""The service's single entry point into the graph.

`ChatService.events()` is the one place the graph is run from; `/chat` and
`/chat/stream` are both views of it, so they can't drift apart. It knows nothing
about HTTP: it turns the capstone Assistant's events into the API's typed events.
"""

from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from collections.abc import Iterator

from cachetools import TTLCache

from app.cache import AnswerCache, CachedAnswer, config_fingerprint
from app.capstone import CAPSTONE_PATH, load_capstone
from app.config import get_settings
from app.observability import Observer, RunTelemetry
from common.access import PUBLIC, User
from common.resilience import ProviderUnavailable, RequestBudget
from common.truth import cited_versions
from app.schemas import (
    ChatResponse,
    DoneEvent,
    RetractEvent,
    StatusEvent,
    TokenEvent,
    Turn,
)

RETRACT_REASON = ("The fact-check could not find this draft in the documents, "
                  "so it was discarded.")
log = logging.getLogger("northwind.api")


def _trace_cache_hit(trace_id, question, hit, request_id, session_id) -> None:
    """A cache hit gets its own small LangSmith run under the response's trace_id, so
    "log line -> trace" and /feedback still work, and it points at the original run."""
    try:
        from langsmith import trace
        from langsmith.utils import tracing_is_enabled

        if not tracing_is_enabled():
            return
        with trace("northwind_assistant", run_type="chain", run_id=uuid.UUID(str(trace_id)),
                   inputs={"raw_question": question}, tags=["capstone", "cache_hit"],
                   metadata={"request_id": request_id, "session_id": session_id, "cache_hit": True,
                             "cached_from_trace_id": hit.trace_id}) as run:
            run.end(outputs={"answer": hit.answer, "sources": hit.sources})
    except Exception as exc:                         # tracing must never fail a request
        log.debug("cache-hit trace not recorded: %s", exc)


CACHE_LABEL = "✓ Answered from cache (asked before, documents unchanged)"


class SessionForbidden(Exception):
    """This session belongs to another user (-> 403)."""


class ChatService:
    def __init__(self, backend, observer: Observer | None = None, cache: AnswerCache | None = None):
        self.backend = backend                  # capstone Backend: index + retriever + graph + memory
        self.observer = observer or Observer()  # request log line + metrics
        self.cache = cache                      # None = no answer cache (CACHE_ENABLED=false)
        self._capstone = load_capstone()
        self._fingerprint = config_fingerprint(get_settings(), CAPSTONE_PATH.read_bytes())
        # Week 3 Task 6: session_id -> the user_id that started it. It outlives the session's own TTL
        # by a margin, so an owner record never expires while the conversation it guards still exists.
        s = get_settings()
        self._owners = TTLCache(maxsize=s.max_sessions,
                                ttl=s.session_ttl_seconds + s.request_timeout_seconds + 60)
        self._owners_lock = threading.Lock()

    # -- sessions belong to the user who started them (Task 6) -----------------------
    def check_session(self, session_id: str, user: User, claim: bool) -> None:
        """403 (SessionForbidden) unless `user` owns this session, or it is new and `claim` is set.
        A conversation with no recorded owner is nobody's to take over."""
        with self._owners_lock:
            owner = self._owners.get(session_id)
            if owner is None and self.assistant.history(session_id):
                raise SessionForbidden(session_id)
            if owner is not None and owner != user.user_id:
                raise SessionForbidden(session_id)
            if owner is not None or claim:
                self._owners[session_id] = user.user_id          # (re)starts the TTL

    @property
    def assistant(self):
        # read through the backend every time: Backend.refresh() replaces the Assistant
        return self.backend.assistant

    # -- answer cache -----------------------------------------------------------
    def _cache_key(self, question: str, session_id: str, user: User) -> str | None:
        """The cache key, or None when this request must not use the cache: no cache, or a
        follow-up (the session has history, so the answer depends on the conversation)."""
        if self.cache is None or self.assistant.history(session_id):
            return None
        version = self.backend.ingest_stats.get("corpus_version", "")
        if self.cache.sync_corpus(version):
            log.info("documents changed (corpus %s): answer cache emptied", version)
        return self.cache.key(question, corpus_version=version, fingerprint=self._fingerprint, scope=user.scope)

    def _serve_from_cache(self, hit: CachedAnswer, question, session_id, *, trace_id, request_id,
                          tokens, endpoint, user: User):
        t0 = time.perf_counter()
        self.assistant.remember(session_id, question, hit.answer)   # follow-ups keep their context
        traced = user.groups <= PUBLIC                              # same rule as a live run (Task 6)
        if traced:
            _trace_cache_hit(trace_id, question, hit, request_id, session_id)
        yield StatusEvent(node="cache", label=CACHE_LABEL, elapsed_ms=int((time.perf_counter() - t0) * 1000))
        if tokens:                              # same protocol as a live answer (already fact-checked)
            for piece in re.findall(r"\S+\s*", hit.answer):
                yield TokenEvent(text=piece)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        yield DoneEvent(answer=hit.answer, sources=hit.sources, node_path=["cache"], session_id=session_id,
                        trace_id=str(trace_id), standalone_question=question, retries=0,
                        elapsed_ms=latency_ms, cache_hit=True, cached_from_trace_id=hit.trace_id)
        self.observer.request_finished({
            "request_id": request_id, "session_id": session_id, "trace_id": str(trace_id),
            "endpoint": endpoint, "status": "ok", "route": "cache", "node_path": ["cache"], "retries": 0,
            "latency_ms": latency_ms, "tokens_in": 0, "tokens_out": 0, "estimated_cost_usd": 0.0,
            "refused": hit.refused, "cache_hit": True, "llm_calls": 0, "model": get_settings().llm_label,
            "per_node": {}, "retrieved_ids": [], "kept_ids": [], "cached_from_trace_id": hit.trace_id,
            "cited_versions": cited_versions(hit.sources),
            "user_id": user.user_id, "access_scope": user.scope, "restricted_docs_used": hit.restricted_used,
            "traced": traced, "cache_age_s": round(time.time() - hit.created, 1)})

    # -- the one place the graph runs ---------------------------------------------
    def events(self, question: str, session_id: str, *, user: User, trace_id: str,
               request_id: str | None = None, tokens: bool = True, endpoint: str = "chat/stream",
               use_cache: bool = True) -> Iterator[StatusEvent | TokenEvent | RetractEvent | DoneEvent]:
        """Run the graph once, yielding status / token / retract events and a final DoneEvent.

        The graph routes and grades BEFORE it generates, so the first seconds are
        status events (one per node) and tokens only start with `generate`. Those
        tokens are a draft: `grade_generation` runs after them, and if it rejects
        the draft we say so with a RetractEvent before anything else is streamed.

        Every run reports exactly ONE record to the observer when it ends (ok, error,
        or cancelled by a client disconnect): the request's log line and metrics.

        A session's first question is looked up in the answer cache first (see
        app/cache.py); `use_cache=False` always runs the real pipeline (cost report,
        benchmarks).

        `user` (Week 3 Task 6) comes from the directory, never from the request: retrieval sees
        only what their groups may see, the cache is keyed by their access scope, and the session
        must be theirs (SessionForbidden otherwise; checked before anything runs).
        """
        self.check_session(session_id, user, claim=True)
        key = self._cache_key(question, session_id, user) if use_cache else None
        if key is not None:
            hit = self.cache.get(key)
            if hit is not None:
                yield from self._serve_from_cache(hit, question, session_id, trace_id=trace_id,
                                                  request_id=request_id, tokens=tokens, endpoint=endpoint,
                                                  user=user)
                return

        t0 = time.perf_counter()

        def ms() -> int:
            return int((time.perf_counter() - t0) * 1000)

        settings = get_settings()
        telemetry = RunTelemetry()
        # Task 8: one budget for ALL LLM calls of this request (logical x transport retries)
        budget = RequestBudget(settings.max_llm_calls_per_request, settings.request_timeout_seconds)
        drafted = False
        first_token_ms = None
        final, status, error = None, "error", None
        metadata = {"request_id": request_id, "api": True} if request_id else {"api": True}

        try:
            for ev in self.assistant.stream(question, session_id, run_id=trace_id, tokens=tokens,
                                            metadata=metadata, callbacks=[telemetry], llm_budget=budget,
                                            groups=user.groups):
                kind = ev["event"]
                if kind == "token":
                    drafted = True
                    first_token_ms = first_token_ms if first_token_ms is not None else ms()
                    yield TokenEvent(text=ev["text"])
                elif kind == "node":
                    node, update = ev["node"], ev["update"]
                    yield StatusEvent(node=node, label=self._capstone.describe_step(node, update),
                                      elapsed_ms=ms())
                    if node == "grade_generation" and drafted and not update.get("generation_ok"):
                        drafted = False
                        yield RetractEvent(reason=RETRACT_REASON)
                elif kind == "final":
                    final, status = ev, "ok"
                    usage = telemetry.totals()
                    # never cache a degraded answer (Task 8): it was made with a weaker guarantee
                    if key is not None and ev["answer"].strip() and not ev.get("degraded"):
                        self.cache.put(key, CachedAnswer(
                            answer=ev["answer"], sources=list(ev["sources"]), node_path=list(ev["path"]),
                            retries=ev["retries"], refused=self._capstone.is_refusal(ev["answer"]),
                            trace_id=str(trace_id), tokens_in=usage["tokens_in"],
                            tokens_out=usage["tokens_out"], llm_calls=usage["llm_calls"],
                            restricted_used=bool(ev.get("restricted_used"))))
                    yield DoneEvent(
                        answer=ev["answer"], sources=ev["sources"], node_path=ev["path"],
                        session_id=session_id, trace_id=str(trace_id),
                        standalone_question=ev["standalone"], retries=ev["retries"], elapsed_ms=ms(),
                        llm_calls=usage["llm_calls"], tokens_in=usage["tokens_in"],
                        tokens_out=usage["tokens_out"], degraded=ev.get("degraded", []),
                        estimated_cost_usd=round(settings.cost_usd(usage["tokens_in"], usage["tokens_out"]), 6))
        except GeneratorExit:                   # the client went away mid-stream
            status = "cancelled" if final is None else status
            raise
        except ProviderUnavailable as exc:        # Task 8: a provider failure the graph couldn't absorb
            error = f"{exc.code}: {exc}"[:300]
            raise
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:300]
            raise
        finally:
            self.observer.request_finished(self._record(
                endpoint=endpoint, status=status, error=error, final=final, telemetry=telemetry,
                latency_ms=ms(), first_token_ms=first_token_ms, request_id=request_id,
                session_id=session_id, trace_id=str(trace_id), settings=settings, budget=budget, user=user))

    def _record(self, *, endpoint, status, error, final, telemetry, latency_ms, first_token_ms,
                request_id, session_id, trace_id, settings, user: User, budget=None) -> dict:
        """The one structured log line of a request (see app/observability.py)."""
        usage = telemetry.totals()
        path = (final or {}).get("path", [])
        answer = (final or {}).get("answer", "")
        rec = {
            "request_id": request_id, "session_id": session_id, "trace_id": trace_id,
            "endpoint": endpoint, "status": status,
            "route": "direct" if "direct_answer" in path else ("retrieve" if path else None),
            "node_path": path, "retries": (final or {}).get("retries", 0),
            "latency_ms": latency_ms,
            "tokens_in": usage["tokens_in"], "tokens_out": usage["tokens_out"],
            "estimated_cost_usd": round(settings.cost_usd(usage["tokens_in"], usage["tokens_out"]), 6),
            "refused": bool(final) and self._capstone.is_refusal(answer),
            "cache_hit": False,                 # Task 6 turns this on; logged from day one
            "llm_calls": usage["llm_calls"], "model": settings.llm_label,
            "per_node": telemetry.nodes(),
            "cited_versions": (final or {}).get("cited_versions", []),   # Task 5: "HR-POL-004 v3.0"
            "retrieved_ids": (final or {}).get("retrieved_ids", []),
            "kept_ids": (final or {}).get("kept_ids", []),
            "degraded": (final or {}).get("degraded", []),
            "llm_attempts": budget.calls if budget else None,      # incl. transport retries (Task 8)
            # Week 3 Task 6: who asked, with which access (a hash, not the group names), and whether
            # the answer was written from restricted passages: an audit of who saw what, from logs alone.
            "user_id": user.user_id, "access_scope": user.scope,
            "restricted_docs_used": bool((final or {}).get("restricted_used")),
            "traced": user.groups <= PUBLIC,
        }
        if first_token_ms is not None:
            rec["ttft_ms"] = first_token_ms
        if telemetry.calls_without_usage:
            rec["llm_calls_without_usage"] = telemetry.calls_without_usage
        if error:
            rec["error"] = error
        return rec

    def ask(self, question: str, session_id: str, *, user: User, trace_id: str, request_id: str | None = None,
            use_cache: bool = True, endpoint: str = "chat") -> ChatResponse:
        """Non-streaming: the same run, keeping only the final event."""
        done = None
        for ev in self.events(question, session_id, user=user, trace_id=trace_id, request_id=request_id,
                              tokens=False, endpoint=endpoint, use_cache=use_cache):
            if isinstance(ev, DoneEvent):
                done = ev
        if done is None:                                        # the graph ended without a final event
            raise RuntimeError("the assistant returned no answer")
        return ChatResponse(**done.model_dump())

    def history(self, session_id: str, user: User) -> list[Turn]:
        self.check_session(session_id, user, claim=False)
        turns = self.assistant.sessions.get(session_id) or []
        return [Turn(question=q, answer=a) for q, a in turns]

    def reset(self, session_id: str, user: User) -> bool:
        self.check_session(session_id, user, claim=False)
        existed = self.assistant.sessions.get(session_id) is not None
        self.assistant.reset(session_id)
        with self._owners_lock:
            self._owners.pop(session_id, None)
        return existed
