"""
Fast tier — the HTTP service (app/main.py), end to end through FastAPI, offline.

The app under test is the real one (`create_app`): real routes, real lifespan,
real capstone Backend and graph. Only the model and the embeddings are fakes, and
the backend is injected through `create_app(backend_factory=...)`.

Run with:  make check
"""

import ast
import json
import re
import threading
import time
import uuid

import pytest
from conftest import REPO_ROOT, FakeRetriever, prefix, scripted_llm, wait_until_ready
from fastapi.testclient import TestClient
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field

from app.main import create_app
from app.sessions import SessionStore

PTO_ANSWER = "Full-time employees get 20 days of PTO per year.\nSources: employee_handbook.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class StreamingScriptedLLM(BaseChatModel):
    """A real LangChain chat model, so LangGraph's token streaming sees its output,
    answering each capstone prompt from a script and streaming it word by word.

    A rule's reply may be a list: replies are used in order, the last one repeats.
    """

    rules: dict = Field(default_factory=dict)
    fallback: str = "(unscripted prompt)"
    calls: list = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted-streaming-fake"

    def _reply(self, messages) -> str:
        prompt = str(messages[-1].content)
        self.calls.append(prompt)
        for start, reply in self.rules.items():
            if prompt.startswith(start):
                if isinstance(reply, list):
                    return reply.pop(0) if len(reply) > 1 else reply[0]
                return reply
        return self.fallback

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self._reply(messages)))])

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        # langchain-core reports each chunk to the callbacks (LangGraph's token stream) itself
        for piece in re.findall(r"\S+\s*", self._reply(messages)):
            yield ChatGenerationChunk(message=AIMessageChunk(content=piece))


def streaming_llm(app, **overrides):
    """StreamingScriptedLLM with the same script as conftest's scripted_llm."""
    script = scripted_llm(app).rules
    script[prefix(app.GENERATE_PROMPT)] = overrides.pop("answer", PTO_ANSWER)
    if "grounded" in overrides:
        g = overrides.pop("grounded")
        script[prefix(app.GROUNDED_PROMPT)] = ([f"ANSWER: {v}" for v in g] if isinstance(g, list)
                                               else f"ANSWER: {g}")
    assert not overrides, overrides
    return StreamingScriptedLLM(rules=script)


def sse(response):
    """[(event, data), ...] from a text/event-stream response."""
    events, event, data = [], "message", []
    for line in response.iter_lines():
        if not line:
            if data:
                events.append((event, json.loads("\n".join(data))))
            event, data = "message", []
        elif line.startswith(":"):
            continue
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" "))
    if data:
        events.append((event, json.loads("\n".join(data))))
    return events


def stream_chat(client, question, session_id=None, **kwargs):
    body = {"question": question} | ({"session_id": session_id} if session_id else {})
    with client.stream("POST", "/chat/stream", json=body, **kwargs) as r:
        assert r.status_code == 200, r.read()
        assert r.headers["content-type"].startswith("text/event-stream")
        return sse(r)


def assert_error_shape(response, status, error):
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error", "detail", "request_id"}, body
    assert body["error"] == error
    assert body["request_id"] == response.headers["x-request-id"]
    assert "Traceback" not in response.text
    return body


@pytest.fixture
def api(start_api, app_backend):
    """The API over a Backend whose model is the scripted (non-streaming) fake."""
    client = start_api(lambda: app_backend)
    client.backend = app_backend
    return client


# ===========================================================================
# STARTUP: load once, healthz vs readyz
# ===========================================================================

def test_healthz_answers_while_loading_and_readyz_does_not(start_api, app_backend):
    """/healthz = the process is alive. /readyz = it can serve questions. During the
    index/model load the first is 200 and the second is 503, which is exactly what
    keeps a load balancer from sending traffic to an instance that can't answer."""
    release = threading.Event()

    def slow_factory():
        assert release.wait(5)
        return app_backend

    client = start_api(slow_factory, wait=False)
    assert client.get("/healthz").json() == {"status": "ok"}
    r = client.get("/readyz")
    assert_error_shape(r, 503, "not_ready")
    assert r.headers["retry-after"] == "5"
    assert_error_shape(client.post("/chat", json={"question": "How much PTO do I get?"}), 503, "not_ready")

    release.set()
    ready = wait_until_ready(client).json()
    assert ready["graph_compiled"] is True and ready["chunks"] > 0


def test_healthz_is_fast_and_never_calls_the_model(api):
    llm = api.backend.fake_llm
    before = len(llm.calls)
    timings = []
    for _ in range(20):
        t0 = time.perf_counter()
        r = api.get("/healthz")
        timings.append(time.perf_counter() - t0)
        assert r.status_code == 200 and r.json() == {"status": "ok"}
    assert len(llm.calls) == before, "/healthz must never call the model"
    assert max(timings) < 0.05, f"slowest /healthz {max(timings) * 1000:.1f} ms"


def test_startup_failure_is_reported_by_readyz_not_by_a_crash(start_api):
    def broken_factory():
        raise ConnectionError("model server unreachable")

    client = start_api(broken_factory, wait=False)
    deadline = time.monotonic() + 5
    while (r := client.get("/readyz")).json().get("error") == "not_ready" and time.monotonic() < deadline:
        time.sleep(0.01)
    body = assert_error_shape(r, 503, "startup_failed")
    assert "model server unreachable" in body["detail"]
    assert client.get("/healthz").status_code == 200


def test_index_and_graph_are_built_once_not_per_request(start_api, app_backend):
    built = []

    def counting_factory():
        built.append(1)
        return app_backend

    client = start_api(counting_factory)
    for _ in range(3):
        assert client.post("/chat", json={"question": "How much PTO do I get?"}).status_code == 200
    with client.stream("POST", "/chat/stream", json={"question": "How much PTO do I get?"}) as r:
        r.read()
    assert built == [1]


# ===========================================================================
# POST /chat
# ===========================================================================

def test_chat_returns_answer_sources_and_node_path(api):
    r = api.post("/chat", json={"question": "How much PTO do I get?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answer"] == "Full-time employees get 20 days of PTO per year."
    assert body["sources"] and all(s.startswith("employee_handbook.md") for s in body["sources"])
    assert body["node_path"] == ["contextualize", "route_question", "retrieve", "grade_documents",
                                 "generate", "grade_generation"]
    uuid.UUID(body["trace_id"])
    uuid.UUID(body["session_id"])                 # a session id is assigned when none is sent
    assert body["standalone_question"] == "How much PTO do I get?"


def test_trace_id_is_the_langsmith_root_run_id(api):
    """/feedback can only find the trace if the id we return IS the root run's id."""
    seen = {}
    graph = api.backend.assistant.graph
    real_stream = graph.stream

    def spy(inputs, config=None, **kwargs):
        seen["config"] = config
        return real_stream(inputs, config=config, **kwargs)

    graph.stream = spy
    body = api.post("/chat", json={"question": "How much PTO do I get?"}).json()
    assert str(seen["config"]["run_id"]) == body["trace_id"]
    assert seen["config"]["metadata"]["session_id"] == body["session_id"]


# ===========================================================================
# SESSIONS — the isolation proof named in week2/RESULTS.md
# ===========================================================================

def test_two_sessions_hold_independent_conversations(start_api, make_backend, app):
    """Two session_ids, interleaved, over HTTP: each conversation sees only its own
    history, a follow-up is resolved only against its own session, and clearing one
    leaves the other intact."""
    llm = scripted_llm(app, standalone="Can I carry unused PTO over to next year?")
    client = start_api(lambda: make_backend(llm))
    a, b = f"alice-{uuid.uuid4()}", f"bob-{uuid.uuid4()}"
    ctx = prefix(app.CONTEXTUALIZE_PROMPT)

    assert client.post("/chat", json={"question": "How much PTO do I get?", "session_id": a}).status_code == 200
    rb = client.post("/chat", json={"question": "Can I carry it over?", "session_id": b}).json()
    assert rb["standalone_question"] == "Can I carry it over?", "B has no history: nothing to resolve"
    assert llm.calls_to(ctx) == [], "B's first question must not be resolved against A's conversation"

    ra = client.post("/chat", json={"question": "Can I carry it over to next year?", "session_id": a}).json()
    assert ra["standalone_question"] == "Can I carry unused PTO over to next year?"
    [ctx_call] = llm.calls_to(ctx)
    assert "How much PTO do I get?" in ctx_call, "A's follow-up is resolved against A's turn 1"
    assert "Can I carry it over?" not in ctx_call.split("Latest message:")[0], "B's turn leaked into A"

    turns_a = client.get(f"/session/{a}").json()["turns"]
    turns_b = client.get(f"/session/{b}").json()["turns"]
    assert [t["question"] for t in turns_a] == ["How much PTO do I get?", "Can I carry it over to next year?"]
    assert [t["question"] for t in turns_b] == ["Can I carry it over?"]

    assert client.delete(f"/session/{a}").json() == {"session_id": a, "cleared": True}
    assert client.get(f"/session/{a}").json()["turns"] == []
    assert len(client.get(f"/session/{b}").json()["turns"]) == 1, "clearing A must not touch B"
    assert client.delete(f"/session/{a}").json() == {"session_id": a, "cleared": False}, "idempotent"


def test_session_memory_survives_across_requests_and_clients(api):
    """The conversation lives server-side: a brand-new HTTP client (a refreshed tab)
    continues it with just the session_id."""
    sid = str(uuid.uuid4())
    api.post("/chat", json={"question": "How much PTO do I get?", "session_id": sid})
    # A new client on the SAME running app (a refreshed tab). Not `with TestClient(...)`: that
    # would re-run the startup lifespan, and its request could race the background load (503).
    fresh_tab = TestClient(api.app)
    r = fresh_tab.get(f"/session/{sid}")
    assert r.status_code == 200, r.text
    assert [t["question"] for t in r.json()["turns"]] == ["How much PTO do I get?"]


# ===========================================================================
# POST /chat/stream
# ===========================================================================

def test_stream_sends_status_then_tokens_then_done(start_api, make_backend, app):
    client = start_api(lambda: make_backend(streaming_llm(app)))
    events = stream_chat(client, "How much PTO do I get?")
    kinds = [k for k, _ in events]

    assert kinds[0] == "status" and events[0][1]["node"] == "contextualize"
    assert kinds[-1] == "done" and kinds.count("done") == 1
    tokens = [d["text"] for k, d in events if k == "token"]
    assert len(tokens) > 5, "the answer must arrive in many pieces, not one lump"
    assert "".join(tokens) == PTO_ANSWER

    # tokens arrive WHILE `generate` runs: after the grading status, before generate's own status
    status_nodes = [d["node"] for k, d in events if k == "status"]
    first_token = kinds.index("token")
    generate_done = next(i for i, (k, d) in enumerate(events) if k == "status" and d["node"] == "generate")
    graded = next(i for i, (k, d) in enumerate(events) if k == "status" and d["node"] == "grade_documents")
    assert graded < first_token < generate_done

    done = events[-1][1]
    assert done["answer"] == "Full-time employees get 20 days of PTO per year."
    assert done["node_path"] == status_nodes
    assert any(s.startswith("employee_handbook.md") for s in done["sources"])
    uuid.UUID(done["trace_id"])


def test_stream_retracts_a_draft_the_fact_check_rejects(start_api, make_backend, app):
    """The graph fact-checks AFTER generating, so streamed tokens are a draft. When
    the check rejects it, the client is told to discard it before the next draft."""
    llm = streaming_llm(app, grounded=["NO", "YES"])
    llm.rules[prefix(app.GENERATE_PROMPT)] = [
        "You get 45 days of PTO.\nSources: employee_handbook.md", PTO_ANSWER]
    client = start_api(lambda: make_backend(llm))
    events = stream_chat(client, "How much PTO do I get?")
    kinds = [k for k, _ in events]

    assert kinds.count("retract") == 1
    r = kinds.index("retract")
    first_draft = "".join(d["text"] for k, d in events[:r] if k == "token")
    second_draft = "".join(d["text"] for k, d in events[r:] if k == "token")
    assert "45 days" in first_draft and "45" not in second_draft
    assert events[r - 1][0] == "status" and events[r - 1][1]["node"] == "grade_generation"
    done = events[-1][1]
    assert done["answer"] == "Full-time employees get 20 days of PTO per year."
    assert done["retries"] == 1 and "rewrite_query" in done["node_path"]


def test_refusal_streams_no_tokens_and_cites_nothing(start_api, make_backend, app):
    llm = streaming_llm(app)
    llm.rules[prefix(app.ROUTE_PROMPT)] = "DIRECT"
    client = start_api(lambda: make_backend(llm))
    events = stream_chat(client, "What is the capital of France?")
    assert "token" not in [k for k, _ in events]
    done = events[-1][1]
    assert done["answer"] == app.REFUSAL and done["sources"] == []


def test_stream_failure_ends_with_a_structured_error_event(api):
    def broken_stream(*args, **kwargs):
        yield {"event": "node", "node": "contextualize", "update": {"question": "q"}}
        raise RuntimeError("boom at /home/someone/secret/path.py line 12")

    api.backend.assistant.stream = broken_stream
    with api.stream("POST", "/chat/stream", json={"question": "How much PTO?"}) as r:
        raw = r.read().decode()
        request_id = r.headers["x-request-id"]
    events = [(m.group(1), json.loads(m.group(2)))
              for m in re.finditer(r"event: (\w+)\r?\ndata: (.*?)\r?\n", raw)]
    assert [k for k, _ in events] == ["status", "error"]
    err = events[-1][1]
    assert set(err) == {"error", "detail", "request_id"}
    assert err["error"] == "internal_error" and err["request_id"] == request_id
    assert "secret" not in raw and "Traceback" not in raw


# ===========================================================================
# ERRORS — one shape everywhere, never a stack trace
# ===========================================================================

def test_unhandled_error_returns_error_shape_not_traceback(api):
    def broken_stream(*args, **kwargs):
        raise RuntimeError("boom at /home/someone/secret/path.py line 12")
        yield

    api.backend.assistant.stream = broken_stream
    r = api.post("/chat", json={"question": "How much PTO do I get?"})
    body = assert_error_shape(r, 500, "internal_error")
    assert "secret" not in r.text and "boom" not in r.text
    assert body["request_id"]


@pytest.mark.parametrize("payload, field", [
    ({"question": ""}, "question"),
    ({"question": "   "}, "question"),
    ({"question": "x" * 2001}, "question"),
    ({}, "question"),
    ({"question": "hi", "session_id": "../../etc/passwd"}, "session_id"),
])
def test_invalid_requests_get_a_validation_error(api, payload, field):
    body = assert_error_shape(api.post("/chat", json=payload), 422, "validation_error")
    assert field in body["detail"]
    assert "x" * 100 not in body["detail"], "the input must not be echoed back"


def test_unknown_route_and_method_use_the_same_shape(api):
    assert_error_shape(api.get("/nope"), 404, "not_found")
    assert_error_shape(api.get("/chat"), 405, "method_not_allowed")


def test_request_id_is_passed_through(api):
    r = api.get("/healthz", headers={"X-Request-ID": "lb-7f3a-0001"})
    assert r.headers["x-request-id"] == "lb-7f3a-0001"
    generated = api.get("/healthz").headers["x-request-id"]
    assert re.fullmatch(r"[0-9a-f]{32}", generated)
    assert api.get("/healthz", headers={"X-Request-ID": "bad id\twith spaces"}).headers["x-request-id"] != "bad id\twith spaces"


# ===========================================================================
# POST /feedback
# ===========================================================================

class FakeLangSmith:
    def __init__(self, fail=False):
        self.feedback, self.fail = [], fail

    def create_feedback(self, **kwargs):
        if self.fail:
            raise ConnectionError("LangSmith is down")
        self.feedback.append(kwargs)


def test_feedback_is_attached_to_the_answers_trace(start_api, app_backend):
    ls = FakeLangSmith()
    client = start_api(lambda: app_backend, feedback_client_factory=lambda: ls)
    trace_id = client.post("/chat", json={"question": "How much PTO do I get?"}).json()["trace_id"]

    r = client.post("/feedback", json={"trace_id": trace_id, "rating": 1, "comment": "spot on"})
    assert r.status_code == 200 and r.json() == {"status": "recorded", "trace_id": trace_id}
    [fb] = ls.feedback
    assert str(fb["run_id"]) == trace_id
    assert fb["key"] == "user_rating" and fb["score"] == 1 and fb["comment"] == "spot on"


def test_feedback_errors(start_api, app_backend):
    tid = str(uuid.uuid4())
    no_langsmith = start_api(lambda: app_backend)
    assert_error_shape(no_langsmith.post("/feedback", json={"trace_id": tid, "rating": 1}),
                       503, "feedback_unavailable")
    assert_error_shape(no_langsmith.post("/feedback", json={"trace_id": "not-a-uuid", "rating": 1}),
                       422, "validation_error")
    assert_error_shape(no_langsmith.post("/feedback", json={"trace_id": tid, "rating": 5}),
                       422, "validation_error")
    down = start_api(lambda: app_backend, feedback_client_factory=lambda: FakeLangSmith(fail=True))
    assert_error_shape(down.post("/feedback", json={"trace_id": tid, "rating": -1}), 502, "feedback_failed")


# ===========================================================================
# DOCS, UI
# ===========================================================================

def test_openapi_lists_every_endpoint(api):
    assert api.get("/docs").status_code == 200
    spec = api.get("/openapi.json").json()
    routes = {(m.upper(), p) for p, ops in spec["paths"].items() for m in ops}
    assert {("POST", "/chat"), ("POST", "/chat/stream"), ("GET", "/healthz"), ("GET", "/readyz"),
            ("POST", "/feedback"), ("DELETE", "/session/{session_id}")} <= routes


def test_ui_talks_to_the_api_only():
    """`grep build_graph app/ui.py` finds nothing, and the UI imports nothing that
    could run the graph: only the stdlib, streamlit and an HTTP client."""
    source = (REPO_ROOT / "app" / "ui.py").read_text(encoding="utf-8")
    assert "build_graph" not in source
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= {"__future__", "json", "os", "uuid", "httpx", "streamlit"}, imported


# ===========================================================================
# LIVE — the real service, real model (make check-live)
# ===========================================================================

@pytest.mark.live
def test_live_stream_delivers_real_model_tokens():
    """The default app (real Backend, real model): the answer arrives as many token
    events from the model, then a cited `done`."""
    with TestClient(create_app()) as client:
        wait_until_ready(client, timeout=180)
        events = stream_chat(client, "How many sick days do I get per year?")
    kinds = [k for k, _ in events]
    assert kinds[-1] == "done", events[-1]
    assert kinds.count("token") > 5, f"expected a token stream, got {kinds}"
    done = events[-1][1]
    assert re.search(r"\b10\b|\bten\b", done["answer"], re.I), done["answer"]
    assert any(s.startswith("employee_handbook.md") for s in done["sources"]), done["sources"]


# ===========================================================================
# SESSION STORE (unit)
# ===========================================================================

class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_session_store_ttl_slides_with_activity():
    clock = Clock()
    store = SessionStore(ttl_seconds=60, clock=clock)
    store["a"] = [("q", "a")]
    store["b"] = [("q", "a")]
    clock.now = 50
    assert store.get("a") is not None          # touching A restarts its TTL
    clock.now = 100                            # B idle for 100 s, A for 50 s
    assert store.get("b") is None
    assert store.get("a") == [("q", "a")]
    clock.now = 161
    assert store.get("a") is None and len(store) == 0


def test_session_store_is_bounded():
    store = SessionStore(ttl_seconds=3600, max_sessions=2, clock=Clock())
    store["a"], store["b"] = [], []
    store.get("a")                             # A is now more recently used than B
    store["c"] = []
    assert set(store) == {"a", "c"}


def test_assistant_memory_works_on_the_session_store(app, sample_docs):
    store = SessionStore(ttl_seconds=60, clock=Clock())
    assistant = app.Assistant(FakeRetriever(sample_docs), scripted_llm(app), store)
    assistant.ask("How much PTO do I get?", "a")
    assistant.ask("And sick days?", "a")
    assert [q for q, _ in assistant.history("a")] == ["How much PTO do I get?", "And sick days?"]
    assistant.reset("a")
    assert assistant.history("a") == [] and len(store) == 0


def test_capstone_backend_accepts_an_external_session_store(make_backend):
    store = SessionStore()
    backend = make_backend(sessions=store)
    assert backend.assistant.sessions is store
    backend.refresh()                           # docs changed: the new Assistant keeps the same store
    assert backend.assistant.sessions is store


def test_non_streaming_llm_still_works_with_token_mode(app, sample_docs):
    """tokens=True with a model that can't stream (the plain FakeLLM) must still
    produce the final event; there are simply no token events."""
    assistant = app.Assistant(FakeRetriever(sample_docs), scripted_llm(app))
    events = list(assistant.stream("How much PTO do I get?", "s", tokens=True))
    assert events[-1]["event"] == "final"
    assert not [e for e in events if e["event"] == "token"]
