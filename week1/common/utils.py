"""
Shared helpers used across every task and the capstone.

The point of this module is to hide provider differences behind two functions:

    get_llm()         -> a LangChain chat model
    get_embeddings()  -> a LangChain embeddings object

so the rest of your code never hard-codes OpenAI/Groq/Ollama. Which provider,
model and endpoint are used is configuration, read from the typed settings in
common/settings.py (env vars / week1/.env): switching provider is an .env edit.
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

# `python common/utils.py` runs this file as a script: make `common` importable.
_WEEK1 = Path(__file__).resolve().parents[1]
if str(_WEEK1) not in sys.path:
    sys.path.insert(0, str(_WEEK1))

from common.settings import ENV_FILE, get_settings  # noqa: E402

# Export week1/.env into the process environment for the SDKs that read their own
# keys (OPENAI_API_KEY, GROQ_API_KEY, LANGSMITH_*). Variables that are already set
# win, so in a container the values passed by docker compose are never overridden.
# A missing file is fine: in a container there is none.
load_dotenv(ENV_FILE)

DATA_DIR = get_settings().data_dir


_BREAKER = None


def _breaker(s):
    """One circuit breaker per process: every model built here shares the provider's health."""
    global _BREAKER
    if _BREAKER is None:
        from common.resilience import CircuitBreaker
        _BREAKER = CircuitBreaker(threshold=s.circuit_failure_threshold, cooldown_s=s.circuit_cooldown_seconds)
    return _BREAKER


def get_llm(temperature: float | None = None, **kwargs):
    """Return a chat model for LLM_PROVIDER (default: openai), wrapped with a per-call
    timeout, bounded retries with backoff, the request budget and the circuit breaker
    (common/resilience.py, Task 8). `.inner` is the raw provider model."""
    from common.resilience import ResilientLLM, RetryPolicy

    s = get_settings()
    return ResilientLLM(_raw_llm(s, temperature, **kwargs), RetryPolicy.from_settings(s), _breaker(s))


def _raw_llm(s, temperature=None, **kwargs):
    temperature = s.llm_temperature if temperature is None else temperature
    provider = s.llm_provider

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        # Any OpenAI-compatible server (OpenRouter, vLLM, LiteLLM, Ollama's /v1) is
        # just a different OPENAI_BASE_URL. Unset = the official API.
        if s.openai_reasoning_effort:      # only sent when set: non-reasoning models reject it
            kwargs.setdefault("reasoning_effort", s.openai_reasoning_effort)
        return ChatOpenAI(model=s.openai_model, base_url=s.openai_base_url, temperature=temperature,
                          timeout=s.llm_timeout_seconds, max_retries=0, **kwargs)
    if provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(model=s.groq_model, base_url=s.groq_base_url, temperature=temperature,
                        timeout=s.llm_timeout_seconds, max_retries=0, **kwargs)
    if provider == "ollama":
        from langchain_ollama import ChatOllama
        # In a container, OLLAMA_BASE_URL points at the host's Ollama (set by docker compose).
        return ChatOllama(model=s.ollama_model, base_url=s.ollama_base_url, temperature=temperature,
                          reasoning=False, client_kwargs={"timeout": s.llm_timeout_seconds}, **kwargs)
    if provider == "huggingface":
        from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
        endpoint = HuggingFaceEndpoint(repo_id=s.hf_model, temperature=max(temperature, 0.01))
        return ChatHuggingFace(llm=endpoint)

    raise ValueError(f"Unknown LLM_PROVIDER: {provider!r}")   # unreachable: Settings validates it


def get_embeddings(**kwargs):
    """Return an embeddings object for EMBEDDING_PROVIDER (default: openai), behind the
    on-disk embedding cache unless CACHE_ENABLED=false (Task 6)."""
    from common.resilience import ResilientEmbeddings, RetryPolicy

    s = get_settings()
    base = ResilientEmbeddings(_base_embeddings(s, **kwargs), RetryPolicy.from_settings(s))
    if not s.cache_enabled:
        return base
    from common.embedding_cache import with_cache
    return with_cache(base, s.embedding_cache_dir)


def _base_embeddings(s, **kwargs):
    if s.embedding_provider == "openai":
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(model=s.openai_embed_model, base_url=s.openai_base_url,
                                timeout=s.llm_timeout_seconds, max_retries=0, **kwargs)
    # Groq has no embeddings API, and Ollama/HF use the same free local model.
    if s.local_embeddings_backend == "fastembed":
        # Same model, run by ONNX Runtime instead of PyTorch (no 750 MB torch install).
        from langchain_community.embeddings import FastEmbedEmbeddings
        return FastEmbedEmbeddings(model_name=s.hf_embed_model, **kwargs)
    from langchain_huggingface import HuggingFaceEmbeddings
    return HuggingFaceEmbeddings(model_name=s.hf_embed_model, **kwargs)


if __name__ == "__main__":
    # Quick smoke test: `python common/utils.py`
    print(get_settings().summary())
    llm = get_llm()
    reply = llm.invoke("In one sentence, what is Retrieval-Augmented Generation?")
    print("\nModel says:", reply.content)
