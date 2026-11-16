"""The service's single entry point into the graph.

`ChatService.events()` is the one place the graph is run from; `/chat` and
`/chat/stream` are both views of it, so they can't drift apart. It knows nothing
about HTTP: it turns the capstone Assistant's events into the API's typed events.
"""

from __future__ import annotations

import time
from collections.abc import Iterator

from app.capstone import load_capstone
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
    def __init__(self, backend):
        self.backend = backend                  # capstone Backend: index + retriever + graph + memory
        self._capstone = load_capstone()

    @property
    def assistant(self):
        # read through the backend every time: Backend.refresh() replaces the Assistant
        return self.backend.assistant

    def events(self, question: str, session_id: str, *, trace_id: str, request_id: str | None = None,
               tokens: bool = True) -> Iterator[StatusEvent | TokenEvent | RetractEvent | DoneEvent]:
        """Run the graph once, yielding status / token / retract events and a final DoneEvent.

        The graph routes and grades BEFORE it generates, so the first seconds are
        status events (one per node) and tokens only start with `generate`. Those
        tokens are a draft: `grade_generation` runs after them, and if it rejects
        the draft we say so with a RetractEvent before anything else is streamed.
        """
        t0 = time.perf_counter()

        def ms() -> int:
            return int((time.perf_counter() - t0) * 1000)

        drafted = False
        metadata = {"request_id": request_id, "api": True} if request_id else {"api": True}

        for ev in self.assistant.stream(question, session_id, run_id=trace_id, tokens=tokens,
                                        metadata=metadata):
            kind = ev["event"]
            if kind == "token":
                drafted = True
                yield TokenEvent(text=ev["text"])
            elif kind == "node":
                node, update = ev["node"], ev["update"]
                yield StatusEvent(node=node, label=self._capstone.describe_step(node, update),
                                  elapsed_ms=ms())
                if node == "grade_generation" and drafted and not update.get("generation_ok"):
                    drafted = False
                    yield RetractEvent(reason=RETRACT_REASON)
            elif kind == "final":
                yield DoneEvent(
                    answer=ev["answer"], sources=ev["sources"], node_path=ev["path"],
                    session_id=session_id, trace_id=str(trace_id),
                    standalone_question=ev["standalone"], retries=ev["retries"], elapsed_ms=ms())

    def ask(self, question: str, session_id: str, *, trace_id: str,
            request_id: str | None = None) -> ChatResponse:
        """Non-streaming: the same run, keeping only the final event."""
        done = None
        for ev in self.events(question, session_id, trace_id=trace_id, request_id=request_id,
                              tokens=False):
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
