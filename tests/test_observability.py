"""
Fast tier — observability (Week 2, Task 5). Offline: a fake chat model that reports
token usage the way real providers do (AIMessage.usage_metadata).

What must hold:
  * one request -> exactly ONE structured log line, with every required field;
  * LLM calls and tokens are attributed to the right graph node;
  * the log line carries the ids that lead to the LangSmith trace;
  * /metrics counts live traffic.
"""

import re

import pytest
from conftest import prefix
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from structlog.testing import capture_logs
from test_api import PTO_ANSWER, StreamingScriptedLLM, sse

from app.config import get_settings
from app.observability import Metrics, RunTelemetry, _usage

REQUIRED_FIELDS = {"request_id", "session_id", "route", "node_path", "retries", "latency_ms",
                   "tokens_in", "tokens_out", "estimated_cost_usd", "refused", "cache_hit"}


class UsageLLM(StreamingScriptedLLM):
    """Scripted chat model that reports usage: input = words in the prompt, output = words in the reply."""

    def _usage_for(self, messages, reply):
        n_in, n_out = len(str(messages[-1].content).split()), len(reply.split())
        return {"input_tokens": n_in, "output_tokens": n_out, "total_tokens": n_in + n_out}

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        reply = self._reply(messages)
        msg = AIMessage(content=reply, usage_metadata=self._usage_for(messages, reply))
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        reply = self._reply(messages)
        pieces = re.findall(r"\S+\s*", reply) or [""]
        for i, piece in enumerate(pieces):
            usage = self._usage_for(messages, reply) if i == len(pieces) - 1 else None
            yield ChatGenerationChunk(message=AIMessageChunk(content=piece, usage_metadata=usage))


def usage_llm(app, **rule_overrides):
    from conftest import scripted_llm

    rules = scripted_llm(app).rules
    rules[prefix(app.GROUNDED_PROMPT)] = "Every sentence is supported.\nANSWER: YES"
    rules.update(rule_overrides)
    return UsageLLM(rules=rules)


@pytest.fixture
def api(start_api, make_backend, app):
    llm = usage_llm(app)
    backend = make_backend(llm)
    client = start_api(lambda: backend)
    client.llm, client.backend = llm, backend
    return client


def request_lines(logs):
    return [e for e in logs if e.get("event") == "request"]


# ===========================================================================
# ONE request -> ONE structured log line
# ===========================================================================

def test_one_request_produces_one_log_line_with_every_field(api):
    with capture_logs() as logs:
        r = api.post("/chat", json={"user_id": "u1001", "question": "How much PTO do I get?", "session_id": "s-1"},
                     headers={"X-Request-ID": "req-abc-123"})
    assert r.status_code == 200, r.text
    [line] = request_lines(logs)

    assert REQUIRED_FIELDS <= set(line), REQUIRED_FIELDS - set(line)
    body = r.json()
    assert line["request_id"] == "req-abc-123" == r.headers["x-request-id"]
    assert line["session_id"] == "s-1"
    assert line["trace_id"] == body["trace_id"], "the trace_id IS the LangSmith root run id"
    assert line["route"] == "retrieve" and line["refused"] is False and line["cache_hit"] is False
    assert line["node_path"] == body["node_path"] and line["retries"] == 0
    assert line["status"] == "ok" and line["endpoint"] == "chat"
    assert line["latency_ms"] >= 0
    assert line["tokens_in"] > 0 and line["tokens_out"] > 0
    s = get_settings()
    assert line["estimated_cost_usd"] == pytest.approx(s.cost_usd(line["tokens_in"], line["tokens_out"]), abs=1e-6)
    # the HTTP response reports the same usage the log line does
    assert (body["llm_calls"], body["tokens_in"], body["tokens_out"]) == \
           (line["llm_calls"], line["tokens_in"], line["tokens_out"])
    assert line["retrieved_ids"] and all("::" in i for i in line["retrieved_ids"]), "chunk ids, e.g. file.md::3"
    assert set(line["kept_ids"]) <= set(line["retrieved_ids"])


def test_llm_calls_and_tokens_are_attributed_to_the_right_node(api, app):
    """Cross-check the telemetry against the prompts the model actually received."""
    with capture_logs() as logs:
        api.post("/chat", json={"user_id": "u1001", "question": "How much PTO do I get?"})
    [line] = request_lines(logs)
    per_node, calls = line["per_node"], api.llm.calls

    expected = {
        "route_question": len([c for c in calls if c.startswith(prefix(app.ROUTE_PROMPT))]),
        "grade_documents": len([c for c in calls if c.startswith(prefix(app.GRADE_DOC_PROMPT))]),
        "generate": len([c for c in calls if c.startswith(prefix(app.GENERATE_PROMPT))]),
        "grade_generation": len([c for c in calls if c.startswith((prefix(app.GROUNDED_PROMPT),
                                                                    prefix(app.ADDRESSES_PROMPT)))]),
    }
    assert {n: per_node[n]["llm_calls"] for n in expected} == expected
    assert expected["grade_documents"] == len(line["retrieved_ids"][:app.MAX_DOCS_TO_GRADE]), \
        "one grading call per retrieved passage (up to MAX_DOCS_TO_GRADE)"
    assert per_node["retrieve"]["llm_calls"] == 0 and per_node["retrieve"]["runs"] == 1
    assert per_node["contextualize"]["llm_calls"] == 0, "turn 1 has no history: no LLM call"
    assert line["llm_calls"] == sum(n["llm_calls"] for n in per_node.values()) == len(calls)
    # every node in the path was timed
    assert set(line["node_path"]) == set(per_node)
    assert all(n["ms"] >= n["llm_ms"] >= 0 for n in per_node.values())
    # token totals are the per-node sums; generate's output = the words of the answer
    assert line["tokens_out"] == sum(n["tokens_out"] for n in per_node.values())
    assert per_node["generate"]["tokens_out"] == len(PTO_ANSWER.split())


def test_streaming_request_logs_one_line_with_time_to_first_token(api):
    with capture_logs() as logs:
        with api.stream("POST", "/chat/stream", json={"user_id": "u1001", "question": "How much PTO do I get?"}) as r:
            events = sse(r)
    [line] = request_lines(logs)
    done = events[-1][1]
    assert line["endpoint"] == "chat/stream" and line["status"] == "ok"
    assert 0 <= line["ttft_ms"] <= line["latency_ms"]
    assert line["tokens_out"] > 0, "usage is reported by streamed calls too"
    assert (done["llm_calls"], done["tokens_in"]) == (line["llm_calls"], line["tokens_in"])


def test_refusal_on_the_direct_route_is_logged_as_such(start_api, make_backend, app):
    llm = usage_llm(app, **{prefix(app.ROUTE_PROMPT): "DIRECT", prefix(app.SMALLTALK_PROMPT): "NO"})
    client = start_api(lambda: make_backend(llm))
    with capture_logs() as logs:
        client.post("/chat", json={"user_id": "u1001", "question": "What is the capital of France?"})
    [line] = request_lines(logs)
    assert line["route"] == "direct" and line["refused"] is True
    assert line["node_path"] == ["contextualize", "route_question", "direct_answer"]
    assert line["retrieved_ids"] == []


def test_failed_request_still_logs_exactly_one_line(api):
    def broken_stream(*args, **kwargs):
        yield {"event": "node", "node": "contextualize", "update": {"question": "q"}}
        raise RuntimeError("model server unreachable")

    api.backend.assistant.stream = broken_stream
    with capture_logs() as logs:
        r = api.post("/chat", json={"user_id": "u1001", "question": "How much PTO?"}, headers={"X-Request-ID": "req-err"})
    assert r.status_code == 500
    [line] = request_lines(logs)
    assert line["status"] == "error" and line["log_level"] == "warning"
    assert line["request_id"] == "req-err" and "model server unreachable" in line["error"]
    assert REQUIRED_FIELDS <= set(line)


def test_langsmith_run_is_tagged_with_request_and_session_id(api):
    """Given a log line, its trace is found by trace_id (= root run id) or by these tags."""
    seen = {}
    graph = api.backend.assistant.graph
    real = graph.stream

    def spy(inputs, config=None, **kwargs):
        seen.update(config)
        return real(inputs, config=config, **kwargs)

    graph.stream = spy
    with capture_logs() as logs:
        api.post("/chat", json={"user_id": "u1001", "question": "How much PTO?", "session_id": "s-9"},
                 headers={"X-Request-ID": "req-777"})
    [line] = request_lines(logs)
    assert seen["metadata"]["request_id"] == line["request_id"] == "req-777"
    assert seen["metadata"]["session_id"] == line["session_id"] == "s-9"
    assert str(seen["run_id"]) == line["trace_id"]


# ===========================================================================
# /metrics
# ===========================================================================

def metric(text, name, labels=""):
    m = re.search(rf"^{re.escape(name)}{re.escape(labels)} (\S+)$", text, re.M)
    return float(m.group(1)) if m else None


def test_metrics_endpoint_returns_live_counters(start_api, make_backend, app):
    llm = usage_llm(app)
    client = start_api(lambda: make_backend(llm))
    before = client.get("/metrics")
    assert before.status_code == 200 and before.headers["content-type"].startswith("text/plain")
    assert metric(before.text, "northwind_requests_total", '{endpoint="chat",status="ok"}') is None

    client.post("/chat", json={"user_id": "u1001", "question": "How much PTO do I get?"})
    client.post("/chat", json={"user_id": "u1001", "question": "How much PTO do I get?"})
    llm.rules[prefix(app.ROUTE_PROMPT)] = "DIRECT"                 # third one is refused
    client.post("/chat", json={"user_id": "u1001", "question": "What is the capital of France?"})
    calls_before_scrape = len(llm.calls)

    text = client.get("/metrics").text
    assert len(llm.calls) == calls_before_scrape, "/metrics must not call the model"
    assert metric(text, "northwind_requests_total", '{endpoint="chat",status="ok"}') == 3
    assert metric(text, "northwind_refusals_total") == 1
    assert metric(text, "northwind_refusal_rate") == pytest.approx(1 / 3)
    # the repeated first question was served from the answer cache (Task 6)
    assert metric(text, "northwind_cache_hits_total") == 1
    assert metric(text, "northwind_cache_hit_rate") == pytest.approx(1 / 3)
    assert metric(text, "northwind_mean_retries") == 0
    assert metric(text, "northwind_recent_window_requests") == 3
    assert metric(text, "northwind_latency_p50_seconds") >= 0
    assert metric(text, "northwind_latency_p95_seconds") >= metric(text, "northwind_latency_p50_seconds")
    assert metric(text, "northwind_request_latency_seconds_count") == 3
    assert metric(text, "northwind_llm_calls_total", '{node="grade_documents"}') > 0
    assert metric(text, "northwind_llm_tokens_total", '{direction="in"}') > 0
    assert metric(text, "northwind_estimated_cost_usd_total") > 0


def test_metrics_window_percentiles():
    m = Metrics(window=3)
    for ms in (1000, 2000, 3000, 4000):                            # the oldest falls out of the window
        m.observe({"endpoint": "chat", "status": "ok", "latency_ms": ms, "retries": 1, "refused": False,
                   "cache_hit": False, "tokens_in": 0, "tokens_out": 0, "estimated_cost_usd": 0,
                   "per_node": {}})
    assert m._pct(50) == 3.0 and m._pct(95) == pytest.approx(3.9)
    assert m._mean(2) == 1.0


# ===========================================================================
# Token accounting edge cases
# ===========================================================================

def test_usage_falls_back_to_llm_output_and_degrades_to_none():
    from langchain_core.outputs import Generation, LLMResult

    legacy = LLMResult(generations=[[Generation(text="x")]],
                       llm_output={"token_usage": {"prompt_tokens": 12, "completion_tokens": 3}})
    assert _usage(legacy) == (12, 3)
    assert _usage(LLMResult(generations=[[Generation(text="x")]])) is None


def test_a_call_without_usage_is_counted_not_fatal():
    import uuid

    from langchain_core.outputs import Generation, LLMResult

    t = RunTelemetry()
    rid = uuid.uuid4()
    t.on_chat_model_start({}, [[]], run_id=rid, metadata={"langgraph_node": "generate"})
    t.on_llm_end(LLMResult(generations=[[Generation(text="x")]]), run_id=rid)
    assert t.totals() == {"llm_calls": 1, "tokens_in": 0, "tokens_out": 0}
    assert t.calls_without_usage == 1
