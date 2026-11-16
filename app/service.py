"""The service's single entry point into the graph.

`ChatService.events()` is the one place the graph is run from; `/chat` and
`/chat/stream` are both views of it, so they can't drift apart. It knows nothing
about HTTP: it turns the capstone Assistant's events into the API's typed events.
"""

from __future__ import annotations

import time
from collections.abc import Iterator

from app.capstone import load_capstone
from app.config import get_settings
from app.observability import Observer, RunTelemetry
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


class ChatService:
    def __init__(self, backend, observer: Observer | None = None):
        self.backend = backend                  # capstone Backend: index + retriever + graph + memory
        self.observer = observer or Observer()  # request log line + metrics
        self._capstone = load_capstone()

    @property
    def assistant(self):
        # read through the backend every time: Backend.refresh() replaces the Assistant
        return self.backend.assistant

    def events(self, question: str, session_id: str, *, trace_id: str, request_id: str | None = None,
               tokens: bool = True, endpoint: str = "chat/stream",
               ) -> Iterator[StatusEvent | TokenEvent | RetractEvent | DoneEvent]:
        """Run the graph once, yielding status / token / retract events and a final DoneEvent.

        The graph routes and grades BEFORE it generates, so the first seconds are
        status events (one per node) and tokens only start with `generate`. Those
        tokens are a draft: `grade_generation` runs after them, and if it rejects
        the draft we say so with a RetractEvent before anything else is streamed.

        Every run reports exactly ONE record to the observer when it ends (ok, error,
        or cancelled by a client disconnect): the request's log line and metrics.
        """
        t0 = time.perf_counter()

        def ms() -> int:
            return int((time.perf_counter() - t0) * 1000)

        settings = get_settings()
        telemetry = RunTelemetry()
        drafted = False
        first_token_ms = None
        final, status, error = None, "error", None
        metadata = {"request_id": request_id, "api": True} if request_id else {"api": True}

        try:
            for ev in self.assistant.stream(question, session_id, run_id=trace_id, tokens=tokens,
                                            metadata=metadata, callbacks=[telemetry]):
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
                    yield DoneEvent(
                        answer=ev["answer"], sources=ev["sources"], node_path=ev["path"],
                        session_id=session_id, trace_id=str(trace_id),
                        standalone_question=ev["standalone"], retries=ev["retries"], elapsed_ms=ms(),
                        llm_calls=usage["llm_calls"], tokens_in=usage["tokens_in"],
                        tokens_out=usage["tokens_out"],
                        estimated_cost_usd=round(settings.cost_usd(usage["tokens_in"], usage["tokens_out"]), 6))
        except GeneratorExit:                   # the client went away mid-stream
            status = "cancelled" if final is None else status
            raise
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:300]
            raise
        finally:
            self.observer.request_finished(self._record(
                endpoint=endpoint, status=status, error=error, final=final, telemetry=telemetry,
                latency_ms=ms(), first_token_ms=first_token_ms, request_id=request_id,
                session_id=session_id, trace_id=str(trace_id), settings=settings))

    def _record(self, *, endpoint, status, error, final, telemetry, latency_ms, first_token_ms,
                request_id, session_id, trace_id, settings) -> dict:
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
            "retrieved_ids": (final or {}).get("retrieved_ids", []),
            "kept_ids": (final or {}).get("kept_ids", []),
        }
        if first_token_ms is not None:
            rec["ttft_ms"] = first_token_ms
        if telemetry.calls_without_usage:
            rec["llm_calls_without_usage"] = telemetry.calls_without_usage
        if error:
            rec["error"] = error
        return rec

    def ask(self, question: str, session_id: str, *, trace_id: str,
            request_id: str | None = None) -> ChatResponse:
        """Non-streaming: the same run, keeping only the final event."""
        done = None
        for ev in self.events(question, session_id, trace_id=trace_id, request_id=request_id,
                              tokens=False, endpoint="chat"):
            if isinstance(ev, DoneEvent):
                done = ev
        if done is None:                                        # the graph ended without a final event
            raise RuntimeError("the assistant returned no answer")
        return ChatResponse(**done.model_dump())

    def history(self, session_id: str) -> list[Turn]:
        turns = self.assistant.sessions.get(session_id) or []
        return [Turn(question=q, answer=a) for q, a in turns]

    def reset(self, session_id: str) -> bool:
        existed = self.assistant.sessions.get(session_id) is not None
        self.assistant.reset(session_id)
        return existed
