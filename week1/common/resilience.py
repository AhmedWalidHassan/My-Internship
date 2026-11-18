"""
Resilience for every model call (Week 2, Task 8): timeouts, bounded retries, a
request-wide budget and a circuit breaker.

    llm = ResilientLLM(get_llm_raw(), policy)        # done for you in common/utils.get_llm()
    llm.invoke("...")                                # same interface as the chat model

Layers, innermost first:

1. HARD TIMEOUT per attempt (`LLM_TIMEOUT_SECONDS`, and never past the request's
   deadline): the call runs on a worker thread and we stop waiting when time is up.
   A provider that hangs costs a timeout, never a hung request.
2. TRANSPORT RETRIES with tenacity: exponential backoff with jitter, only for errors
   that can heal (timeouts, connection errors, 429/5xx). `LLM_MAX_RETRIES` retries,
   i.e. 1 + LLM_MAX_RETRIES attempts. A 4xx (bad key, bad request) is not retried.
3. REQUEST BUDGET: the graph's LOGICAL retries (rewrite loops) multiply with these
   transport retries, so every request carries one budget: at most
   `MAX_LLM_CALLS_PER_REQUEST` attempts and `REQUEST_TIMEOUT_SECONDS` of wall clock,
   across all its nodes. Exhausted = stop calling, fail the request.
4. CIRCUIT BREAKER (process-wide): after `CIRCUIT_FAILURE_THRESHOLD` consecutive
   failed calls, refuse instantly for `CIRCUIT_COOLDOWN_SECONDS`, then let one trial
   call through. Failing in milliseconds beats failing in 30 s, and it stops
   hammering a provider that is already down.

Everything raises a subclass of ProviderUnavailable, which the graph's degradation
policy and the API's error mapping understand.
"""

from __future__ import annotations

import concurrent.futures
import contextvars
import logging
import threading
import time
from dataclasses import dataclass

from langchain_core.embeddings import Embeddings
from tenacity import (
    RetryCallState,
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

log = logging.getLogger("northwind.resilience")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class ProviderUnavailable(Exception):
    """The model provider could not give an answer. `code` is the API's error code."""
    code = "llm_unavailable"
    retry_after: float = 5.0


class LLMTimeout(ProviderUnavailable):
    code = "llm_timeout"


class BudgetExceeded(ProviderUnavailable):
    """The request used up its LLM-call or time budget."""
    code = "request_budget_exceeded"


class RequestTimeout(BudgetExceeded):
    """The request's wall-clock deadline passed (a slow or hung provider)."""
    code = "request_timeout"


class CircuitOpen(ProviderUnavailable):
    code = "llm_circuit_open"


class RetrievalUnavailable(ProviderUnavailable):
    code = "retrieval_unavailable"


class VerificationUnavailable(ProviderUnavailable):
    """The answer could not be fact-checked, so it is not returned."""
    code = "verification_unavailable"


def is_transient(exc: BaseException) -> bool:
    """Worth retrying: timeouts, connection problems, rate limits and 5xx. Not 4xx."""
    if isinstance(exc, (BudgetExceeded, CircuitOpen)):
        return False
    if isinstance(exc, (LLMTimeout, TimeoutError, ConnectionError)):
        return True
    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(status, int):
        return status == 429 or status >= 500
    name = type(exc).__name__.lower()
    return any(s in name for s in ("timeout", "connect", "network", "unavailable", "ratelimit", "apierror",
                                   "remoteprotocol", "readerror", "server"))


# ---------------------------------------------------------------------------
# Policy, budget, circuit breaker
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RetryPolicy:
    timeout_s: float = 30.0          # per attempt
    max_retries: int = 2             # transport retries after the first attempt
    backoff_initial_s: float = 0.5
    backoff_max_s: float = 4.0

    @classmethod
    def from_settings(cls, s) -> RetryPolicy:
        return cls(timeout_s=s.llm_timeout_seconds, max_retries=s.llm_max_retries,
                   backoff_initial_s=s.llm_backoff_initial_seconds, backoff_max_s=s.llm_backoff_max_seconds)


class RequestBudget:
    """Shared by every LLM call of ONE request (passed through the LangGraph config)."""

    def __init__(self, max_calls: int, timeout_s: float, clock=time.monotonic):
        self.max_calls, self._clock = max_calls, clock
        self.deadline = clock() + timeout_s
        self.calls = 0
        self._lock = threading.Lock()

    def remaining_s(self) -> float:
        return self.deadline - self._clock()

    def charge(self) -> None:
        """Count one attempt, or refuse if the budget is spent."""
        with self._lock:
            if self.remaining_s() <= 0:
                raise RequestTimeout("request deadline reached")
            if self.calls >= self.max_calls:
                raise BudgetExceeded(f"request used its {self.max_calls} LLM calls")
            self.calls += 1


class CircuitBreaker:
    def __init__(self, threshold: int = 5, cooldown_s: float = 30.0, clock=time.monotonic):
        self.threshold, self.cooldown_s, self._clock = threshold, cooldown_s, clock
        self.failures = 0
        self.opened_at: float | None = None
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self.opened_at is None:
                return "closed"
            return "open" if self._clock() - self.opened_at < self.cooldown_s else "half-open"

    def before_call(self) -> None:
        with self._lock:
            if self.opened_at is not None and self._clock() - self.opened_at < self.cooldown_s:
                err = CircuitOpen(f"provider failing: {self.failures} consecutive errors; "
                                  f"not calling it for {self.cooldown_s:.0f}s")
                err.retry_after = max(1.0, self.cooldown_s - (self._clock() - self.opened_at))
                raise err
            # closed, or half-open: let this call through as the trial

    def record(self, ok: bool) -> None:
        with self._lock:
            if ok:
                if self.opened_at is not None:
                    log.warning("circuit CLOSED again: the provider answered")
                self.failures, self.opened_at = 0, None
            else:
                self.failures += 1
                if self.failures >= self.threshold and (self.opened_at is None or
                                                        self._clock() - self.opened_at >= self.cooldown_s):
                    self.opened_at = self._clock()
                    log.error("circuit OPEN after %d consecutive provider failures (cooldown %.0fs)",
                              self.failures, self.cooldown_s)


# ---------------------------------------------------------------------------
# The wrapper
# ---------------------------------------------------------------------------
_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=16, thread_name_prefix="llm-call")


def current_budget() -> RequestBudget | None:
    """The budget of the request this call belongs to: LangGraph puts the run's config
    (including our `configurable.llm_budget`) in a contextvar for every node."""
    try:
        from langchain_core.runnables.config import var_child_runnable_config
        cfg = var_child_runnable_config.get() or {}
    except Exception:
        return None
    return (cfg.get("configurable") or {}).get("llm_budget")


def _call_with_timeout(fn, timeout_s: float):
    """Run fn() on a worker thread (same contextvars: callbacks, tracing) and stop waiting
    after timeout_s. The abandoned call finishes in the background and is discarded."""
    ctx = contextvars.copy_context()
    future = _EXECUTOR.submit(ctx.run, fn)
    try:
        return future.result(timeout=max(0.001, timeout_s))
    except concurrent.futures.TimeoutError:
        future.cancel()
        raise LLMTimeout(f"no answer within {timeout_s:.1f}s") from None


class ResilientLLM:
    """Wraps a chat model; same `.invoke`, every other attribute is the model's own."""

    def __init__(self, inner, policy: RetryPolicy, breaker: CircuitBreaker | None = None):
        self.inner, self.policy = inner, policy
        self.breaker = breaker or CircuitBreaker()
        self.attempts = 0                      # process-wide counters, for tests and metrics
        self.failures = 0

    def __getattr__(self, name):              # model, model_name, ... -> the real model
        if name == "inner":
            raise AttributeError(name)
        return getattr(self.inner, name)

    def _one_attempt(self, input, kwargs):
        budget = current_budget()
        if budget is not None:
            budget.charge()
        self.breaker.before_call()
        timeout = self.policy.timeout_s if budget is None else min(self.policy.timeout_s, budget.remaining_s())
        self.attempts += 1
        try:
            result = _call_with_timeout(lambda: self.inner.invoke(input, **kwargs), timeout)
        except Exception:
            self.failures += 1
            self.breaker.record(ok=False)
            raise
        self.breaker.record(ok=True)
        return result

    def invoke(self, input, config=None, **kwargs):
        if config is not None:
            kwargs["config"] = config

        def before_sleep(state: RetryCallState):
            exc = state.outcome.exception()
            log.warning("LLM call failed (%s: %s); retry %d/%d", type(exc).__name__, str(exc)[:120],
                        state.attempt_number, self.policy.max_retries)

        try:
            for attempt in Retrying(stop=stop_after_attempt(1 + self.policy.max_retries),
                                    wait=wait_exponential_jitter(initial=self.policy.backoff_initial_s,
                                                                 max=self.policy.backoff_max_s),
                                    retry=retry_if_exception(is_transient), before_sleep=before_sleep,
                                    reraise=True):
                with attempt:
                    return self._one_attempt(input, kwargs)
        except ProviderUnavailable:
            raise
        except Exception as exc:                # retries exhausted, or not worth retrying
            raise ProviderUnavailable(f"{type(exc).__name__}: {str(exc)[:200]}") from exc


class ResilientEmbeddings(Embeddings):
    """Same treatment for embedding calls (a hosted embeddings API can fail too)."""

    def __init__(self, inner, policy: RetryPolicy):
        self.inner, self.policy = inner, policy

    def __getattr__(self, name):
        if name == "inner":
            raise AttributeError(name)
        return getattr(self.inner, name)

    def _run(self, fn):
        try:
            for attempt in Retrying(stop=stop_after_attempt(1 + self.policy.max_retries),
                                    wait=wait_exponential_jitter(initial=self.policy.backoff_initial_s,
                                                                 max=self.policy.backoff_max_s),
                                    retry=retry_if_exception(is_transient), reraise=True):
                with attempt:
                    return _call_with_timeout(fn, self.policy.timeout_s)
        except ProviderUnavailable:
            raise
        except Exception as exc:
            raise RetrievalUnavailable(f"embedding call failed: {type(exc).__name__}: {str(exc)[:200]}") from exc

    def embed_documents(self, texts):
        return self._run(lambda: self.inner.embed_documents(texts))

    def embed_query(self, text):
        return self._run(lambda: self.inner.embed_query(text))
