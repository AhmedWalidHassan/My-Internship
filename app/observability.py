"""
Observability (Week 2, Task 5): where the time and the money go, per request.

Three pieces, wired together by `Observer`:

* RunTelemetry: a LangChain callback handler attached to ONE graph run. It times
  every graph node and attributes every LLM call (count, tokens, time) to the node
  that made it, using the `langgraph_node` tag LangGraph puts on each call. Nothing
  in the graph code is wrapped by hand, so a node added tomorrow is measured too.
* One structured JSON log line per request (structlog), with the request_id,
  session_id and trace_id that lead straight to the LangSmith trace.
* Prometheus metrics for GET /metrics: counters plus rolling p50/p95, refusal rate,
  mean retries and cache-hit rate.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from collections import deque
from typing import Any

import structlog
from langchain_core.callbacks import BaseCallbackHandler
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

log = logging.getLogger("northwind.api")
REQUEST_LOGGER = "northwind.request"


# ---------------------------------------------------------------------------
# Per-run telemetry: node timing + LLM calls/tokens per node
# ---------------------------------------------------------------------------
def _usage(response) -> tuple[int, int] | None:
    """(input_tokens, output_tokens) of one LLM result, or None if the provider didn't say.

    LangChain puts it on message.usage_metadata for most chat models (OpenAI, Groq,
    Ollama); older integrations put it in llm_output["token_usage"]."""
    tin = tout = 0
    found = False
    for gens in getattr(response, "generations", None) or []:
        for gen in gens:
            um = getattr(getattr(gen, "message", None), "usage_metadata", None)
            if um:
                tin += int(um.get("input_tokens", 0) or 0)
                tout += int(um.get("output_tokens", 0) or 0)
                found = True
    if found:
        return tin, tout
    tu = (getattr(response, "llm_output", None) or {}).get("token_usage") or {}
    if tu:
        return int(tu.get("prompt_tokens", 0) or 0), int(tu.get("completion_tokens", 0) or 0)
    return None


class RunTelemetry(BaseCallbackHandler):
    """Collects, for one graph run: per node -> runs, wall ms, LLM calls, LLM ms, tokens.

    Graph nodes are the chain runs whose name equals their `langgraph_node` tag;
    LLM calls are attributed to the node they ran in. Errors here must never break
    the request, so the handler is non-raising and every hook is defensive.
    """

    raise_error = False

    def __init__(self):
        self._lock = threading.Lock()
        self._open_nodes: dict[Any, tuple[str, float]] = {}
        self._open_llm: dict[Any, tuple[str, float]] = {}
        self.per_node: dict[str, dict] = {}
        self.calls_without_usage = 0

    def _slot(self, node: str) -> dict:
        return self.per_node.setdefault(node, {"runs": 0, "ms": 0.0, "llm_calls": 0, "llm_ms": 0.0,
                                               "tokens_in": 0, "tokens_out": 0})

    # -- graph nodes ----------------------------------------------------------
    def on_chain_start(self, serialized, inputs, *, run_id, metadata=None, name=None, **kwargs):
        node = (metadata or {}).get("langgraph_node")
        name = name or (serialized or {}).get("name")
        if node and name == node:
            with self._lock:
                self._open_nodes[run_id] = (node, time.perf_counter())

    def _close_node(self, run_id):
        with self._lock:
            opened = self._open_nodes.pop(run_id, None)
            if opened:
                node, t0 = opened
                slot = self._slot(node)
                slot["runs"] += 1
                slot["ms"] += (time.perf_counter() - t0) * 1000

    def on_chain_end(self, outputs, *, run_id, **kwargs):
        self._close_node(run_id)

    def on_chain_error(self, error, *, run_id, **kwargs):
        self._close_node(run_id)

    # -- LLM calls --------------------------------------------------------------
    def _open_call(self, run_id, metadata):
        node = (metadata or {}).get("langgraph_node") or "(outside graph)"
        with self._lock:
            self._open_llm[run_id] = (node, time.perf_counter())

    def on_chat_model_start(self, serialized, messages, *, run_id, metadata=None, **kwargs):
        self._open_call(run_id, metadata)

    def on_llm_start(self, serialized, prompts, *, run_id, metadata=None, **kwargs):
        self._open_call(run_id, metadata)

    def _close_call(self, run_id, usage):
        with self._lock:
            opened = self._open_llm.pop(run_id, None)
            if not opened:
                return
            node, t0 = opened
            slot = self._slot(node)
            slot["llm_calls"] += 1
            slot["llm_ms"] += (time.perf_counter() - t0) * 1000
            if usage is None:
                self.calls_without_usage += 1
            else:
                slot["tokens_in"] += usage[0]
                slot["tokens_out"] += usage[1]

    def on_llm_end(self, response, *, run_id, **kwargs):
        self._close_call(run_id, _usage(response))

    def on_llm_error(self, error, *, run_id, **kwargs):
        self._close_call(run_id, None)

    # -- results --------------------------------------------------------------
    def totals(self) -> dict:
        with self._lock:
            nodes = list(self.per_node.values())
        return {"llm_calls": sum(n["llm_calls"] for n in nodes),
                "tokens_in": sum(n["tokens_in"] for n in nodes),
                "tokens_out": sum(n["tokens_out"] for n in nodes)}

    def nodes(self) -> dict:
        """Per-node figures, rounded, for the log line and the cost report."""
        with self._lock:
            return {node: {"runs": s["runs"], "ms": round(s["ms"], 1), "llm_calls": s["llm_calls"],
                           "llm_ms": round(s["llm_ms"], 1), "tokens_in": s["tokens_in"],
                           "tokens_out": s["tokens_out"]}
                    for node, s in self.per_node.items()}


# ---------------------------------------------------------------------------
# Structured request log
# ---------------------------------------------------------------------------
def configure_structlog() -> None:
    """JSON, one object per line, on stdout. Not cached, so tests can capture it."""
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
            structlog.processors.JSONRenderer(sort_keys=False),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=False,
    )


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
LATENCY_BUCKETS = (0.5, 1, 2, 3, 5, 8, 13, 21, 34, 55, 90, 150)


class Metrics:
    """Prometheus registry for GET /metrics.

    Counters are all-time (since process start). The derived gauges (p50/p95,
    refusal rate, mean retries, cache-hit rate) are over the last `window`
    successful requests, computed when /metrics is scraped.
    """

    def __init__(self, window: int = 1000):
        r = self.registry = CollectorRegistry()
        self.requests = Counter("northwind_requests", "Chat requests handled", ["endpoint", "status"],
                                registry=r)
        self.refusals = Counter("northwind_refusals", "Answers that were the refusal", registry=r)
        self.cache_hits = Counter("northwind_cache_hits", "Answers served from cache", registry=r)
        self.retries = Counter("northwind_rewrite_retries", "Query rewrites, summed over requests",
                               registry=r)
        self.llm_calls = Counter("northwind_llm_calls", "LLM calls by graph node", ["node"], registry=r)
        self.tokens = Counter("northwind_llm_tokens", "LLM tokens", ["direction"], registry=r)
        self.cost = Counter("northwind_estimated_cost_usd", "Estimated LLM spend in USD", registry=r)
        self.node_seconds = Counter("northwind_node_seconds", "Wall time spent in each graph node",
                                    ["node"], registry=r)
        self.latency = Histogram("northwind_request_latency_seconds", "End-to-end latency (ok requests)",
                                 buckets=LATENCY_BUCKETS, registry=r)
        # Task 8: resilience
        self.errors = Counter("northwind_request_errors", "Failed requests by error code", ["code"], registry=r)
        self.degraded = Counter("northwind_degraded_steps", "Steps skipped because the provider failed",
                                ["step"], registry=r)
        self.rejections = Counter("northwind_rejected_requests", "Requests rejected before the model "
                                  "(rate limit, prompt-injection guard)", ["reason"], registry=r)
        self._lock = threading.Lock()
        self._recent: deque = deque(maxlen=window)        # (latency_s, refused, retries, cache_hit)
        self._cache = None
        for name, doc, fn in [
            ("northwind_latency_p50_seconds", "p50 latency over the recent window", lambda: self._pct(50)),
            ("northwind_latency_p95_seconds", "p95 latency over the recent window", lambda: self._pct(95)),
            ("northwind_refusal_rate", "Share of recent answers that were refusals", lambda: self._mean(1)),
            ("northwind_mean_retries", "Mean query rewrites per recent request", lambda: self._mean(2)),
            ("northwind_cache_hit_rate", "Share of recent answers served from cache", lambda: self._mean(3)),
            ("northwind_recent_window_requests", "Requests in the rolling window", lambda: len(self._recent)),
            # Task 6: the answer cache and the embedding cache
            ("northwind_cache_entries", "Answers currently in the answer cache",
             lambda: len(self._cache) if self._cache is not None else 0),
            ("northwind_cache_invalidations", "Times the answer cache was emptied because documents changed",
             lambda: self._cache.invalidations if self._cache is not None else 0),
            ("northwind_cache_enabled", "1 if the answer cache is on", lambda: int(self._cache is not None)),
            ("northwind_embedding_cache_hits", "Texts whose embedding came from the cache",
             lambda: _embedding_cache_stats().get("hits", 0)),
            ("northwind_embedding_cache_misses", "Texts that had to be embedded",
             lambda: _embedding_cache_stats().get("misses", 0)),
            ("northwind_llm_circuit_state", "Provider circuit breaker: 0 closed, 1 half-open, 2 open",
             _circuit_state),
        ]:
            Gauge(name, doc, registry=r).set_function(fn)

    def bind_cache(self, cache) -> None:
        self._cache = cache

    def _pct(self, p: float) -> float:
        with self._lock:
            values = sorted(x[0] for x in self._recent)
        return percentile(values, p) if values else float("nan")

    def _mean(self, i: int) -> float:
        with self._lock:
            values = [float(x[i]) for x in self._recent]
        return sum(values) / len(values) if values else float("nan")

    def observe(self, rec: dict) -> None:
        self.requests.labels(rec["endpoint"], rec["status"]).inc()
        for node, s in (rec.get("per_node") or {}).items():
            if s["llm_calls"]:
                self.llm_calls.labels(node).inc(s["llm_calls"])
            self.node_seconds.labels(node).inc(s["ms"] / 1000)
        self.tokens.labels("in").inc(rec.get("tokens_in", 0))
        self.tokens.labels("out").inc(rec.get("tokens_out", 0))
        self.cost.inc(rec.get("estimated_cost_usd", 0.0))
        for note in rec.get("degraded") or []:
            self.degraded.labels(note.split(":", 1)[0]).inc()
        if rec["status"] != "ok":
            if rec.get("error"):
                self.errors.labels(rec["error"].split(":", 1)[0]).inc()
            return
        self.latency.observe(rec["latency_ms"] / 1000)
        self.retries.inc(rec["retries"])
        if rec["refused"]:
            self.refusals.inc()
        if rec["cache_hit"]:
            self.cache_hits.inc()
        with self._lock:
            self._recent.append((rec["latency_ms"] / 1000, rec["refused"], rec["retries"], rec["cache_hit"]))

    def render(self) -> bytes:
        return generate_latest(self.registry)


def _circuit_state() -> float:
    try:
        import common.utils as utils
        breaker = getattr(utils, "_BREAKER", None)
        return {"closed": 0, "half-open": 1, "open": 2}[breaker.state] if breaker else 0
    except Exception:
        return 0


def _embedding_cache_stats() -> dict:
    try:
        from common.embedding_cache import stats
        return stats()
    except Exception:
        return {}


def percentile(values: list[float], p: float) -> float:
    """Linear interpolation between closest ranks (numpy's default). `values` sorted."""
    if not values:
        return float("nan")
    k = (len(values) - 1) * p / 100
    lo = int(k)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


# ---------------------------------------------------------------------------
# LangSmith: from a trace_id to a clickable URL
# ---------------------------------------------------------------------------
class TraceLinker:
    """Builds the LangSmith URL of a trace from its id, so the log line itself links
    to the trace. Resolved once (one API call for the project's id) in the startup
    thread; until then, or with tracing off, the log line still carries trace_id."""

    def __init__(self):
        self.template: str | None = None

    def resolve(self) -> None:
        try:
            from langsmith import Client
            from langsmith.utils import get_tracer_project, tracing_is_enabled

            if not tracing_is_enabled():
                return
            client = Client()
            project = client.read_project(project_name=get_tracer_project())
            host = getattr(client, "_host_url", None) or "https://smith.langchain.com"
            self.template = (f"{host.rstrip('/')}/o/{project.tenant_id}/projects/p/{project.id}"
                             "/r/{trace_id}?poll=true")
        except Exception as exc:                         # tracing still works; only the link is missing
            log.warning("LangSmith trace links unavailable: %s: %s", type(exc).__name__, exc)

    def url(self, trace_id: str) -> str | None:
        return self.template.format(trace_id=trace_id) if self.template else None


# ---------------------------------------------------------------------------
# Observer: one per app
# ---------------------------------------------------------------------------
class Observer:
    """What ChatService reports every finished request to: log line + metrics."""

    def __init__(self, metrics: Metrics | None = None, linker: TraceLinker | None = None):
        self.metrics = metrics or Metrics()
        self.linker = linker or TraceLinker()

    def request_finished(self, rec: dict) -> None:
        rec = dict(rec)
        # a run that was not sent to LangSmith (restricted scope, Task 6) has no trace to link to
        rec["trace_url"] = self.linker.url(rec["trace_id"]) if rec.get("traced", True) else None
        try:
            self.metrics.observe(rec)
        except Exception:                                # metrics must never fail a request
            log.exception("metrics update failed")
        logger = structlog.get_logger(REQUEST_LOGGER)
        (logger.info if rec["status"] == "ok" else logger.warning)("request", **rec)
