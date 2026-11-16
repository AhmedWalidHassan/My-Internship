"""Every request, response and stream event that crosses the API boundary.

Nothing untyped leaves the service: endpoints return these models and each SSE
event's `data` is one of them, serialised as JSON.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.config import get_settings

MAX_QUESTION_CHARS = get_settings().max_question_chars
SESSION_ID_PATTERN = r"^[A-Za-z0-9._:\-]{1,128}$"


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS,
                          examples=["How much PTO do I get?"])
    session_id: str | None = Field(
        default=None, pattern=SESSION_ID_PATTERN,
        description="Reuse it to continue a conversation. Omit it to start a new one; "
                    "the response tells you the id that was assigned.")

    @field_validator("question")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("question must not be blank")
        return v


class FeedbackRequest(BaseModel):
    trace_id: UUID = Field(description="The trace_id returned by /chat or the stream's `done` event.")
    rating: int = Field(ge=-1, le=1, description="-1 down, 0 neutral, 1 up")
    comment: str | None = Field(default=None, max_length=2000)


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------
class ChatResponse(BaseModel):
    answer: str
    sources: list[str] = Field(description="'file.md › Section' for the passages the answer used. "
                                           "Empty for a refusal.")
    node_path: list[str] = Field(description="Every graph node that ran, in order.")
    session_id: str
    trace_id: str = Field(description="LangSmith root-run id. Pass it to /feedback.")
    standalone_question: str = Field(description="The question after resolving references to "
                                                 "earlier turns (what was actually searched for).")
    retries: int = Field(description="How many times the search query was rewritten.")
    elapsed_ms: int


class ErrorResponse(BaseModel):
    """One error shape for the whole API. A client never sees a stack trace."""
    error: str = Field(description="Stable machine-readable code, e.g. not_ready, validation_error.")
    detail: str | None = None
    request_id: str | None = Field(default=None, description="Also in the X-Request-ID header. "
                                                             "Quote it when reporting a problem.")


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadyResponse(BaseModel):
    status: Literal["ready"] = "ready"
    graph_compiled: bool
    index: Literal["built", "loaded"] = Field(description="Whether this start embedded the corpus "
                                                          "or loaded the saved index.")
    chunks: int
    documents: int
    retriever: str
    active_sessions: int
    startup_seconds: float


class FeedbackResponse(BaseModel):
    status: Literal["recorded"] = "recorded"
    trace_id: str


class Turn(BaseModel):
    question: str
    answer: str


class SessionResponse(BaseModel):
    session_id: str
    turns: list[Turn]


class SessionCleared(BaseModel):
    session_id: str
    cleared: bool = Field(description="False if there was nothing to clear (still a 200).")


# ---------------------------------------------------------------------------
# Stream events (POST /chat/stream). The SSE `event:` field is the name below.
# ---------------------------------------------------------------------------
class StatusEvent(BaseModel):
    """event: status — a graph node finished. Sent while nothing can stream yet."""
    node: str
    label: str
    elapsed_ms: int


class TokenEvent(BaseModel):
    """event: token — one chunk of the answer as the model writes it (a draft)."""
    text: str


class RetractEvent(BaseModel):
    """event: retract — the fact-check rejected the draft streamed so far. Clear it."""
    reason: str


class DoneEvent(ChatResponse):
    """event: done — the authoritative answer and its metadata. Always the last event."""
