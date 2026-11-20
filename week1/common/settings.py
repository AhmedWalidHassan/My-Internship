"""
Every runtime setting, in one typed object (Week 2, Task 4: "configuration is not code").

    from common.settings import get_settings
    s = get_settings()
    s.retriever_k, s.index_path, s.openai_base_url, ...

Values come from, highest priority first:
  1. real environment variables (what docker compose `env_file` / `environment` set),
  2. week1/.env (local development; read for these fields only, never copied into an image),
  3. the defaults below.

Field names map to env vars case-insensitively: `retriever_k` <- RETRIEVER_K.
Settings are validated once, at startup: a typo like LLM_PROVIDER=olama or
CHUNK_OVERLAP >= CHUNK_SIZE stops the process with a clear message instead of
failing on the first request.

Secrets (OPENAI_API_KEY, GROQ_API_KEY, LANGSMITH_API_KEY, ...) are deliberately NOT
fields here: the provider SDKs read them from the environment themselves, so they
never pass through, get logged by, or get printed with this object.

Run `python week1/common/settings.py` to print the resolved settings.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

WEEK1_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = WEEK1_DIR.parent
ENV_FILE = WEEK1_DIR / ".env"
CAPSTONE_DIR = WEEK1_DIR / "capstone_internal_docs_assistant"

LLMProvider = Literal["openai", "groq", "ollama", "huggingface"]
EmbeddingProvider = Literal["openai", "huggingface", "ollama", "groq"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8",
                                      extra="ignore", case_sensitive=False)

    # ---- providers -----------------------------------------------------------
    # OpenRouter, vLLM, LiteLLM, Azure proxies and Ollama's /v1 endpoint are all
    # "openai" with a different OPENAI_BASE_URL (+ the key that server expects).
    llm_provider: LLMProvider = "openai"
    embedding_provider: EmbeddingProvider = Field(
        "openai", description="ollama / groq / huggingface all mean the local HF_EMBED_MODEL")
    llm_temperature: float = Field(0.0, ge=0.0, le=2.0)

    openai_model: str = "gpt-4o-mini"
    openai_embed_model: str = "text-embedding-3-small"
    openai_base_url: str | None = Field(None, description="unset = the official OpenAI API")
    openai_reasoning_effort: Literal["none", "minimal", "low", "medium", "high"] | None = Field(
        None, description="unset = not sent (gpt-4o-mini rejects it). Set `none` for a thinking "
                          "model behind an OpenAI-compatible server (e.g. qwen3.5 on Ollama's /v1), "
                          "or every one-word grader call writes ~1,000 hidden reasoning tokens")
    groq_model: str = "llama-3.3-70b-versatile"
    groq_base_url: str | None = Field(None, description="unset = the official Groq API")
    ollama_model: str = "llama3.1"
    ollama_base_url: str | None = Field(None, description="unset = http://localhost:11434")
    hf_model: str = "HuggingFaceH4/zephyr-7b-beta"
    hf_embed_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    local_embeddings_backend: Literal["sentence-transformers", "fastembed"] = Field(
        "sentence-transformers",
        description="how HF_EMBED_MODEL runs locally: PyTorch (sentence-transformers) or ONNX "
                    "Runtime (fastembed, no torch; used by the slim image)")

    # ---- retrieval & index (changing chunking or the embedding model rebuilds the index) ----
    retriever_k: int = Field(4, ge=1, le=50, description="passages per retriever (BM25 and dense)")
    max_docs_to_grade: int = Field(6, ge=1, le=50, description="retrieved passages the relevance "
                                   "grader checks per search (one LLM call each)")
    # Week 3 Task 4: every retrieval lever is a setting, so an experiment is a config diff.
    # Defaults = the Week 2 / Task 3 retriever. BM25 0.3 + demoting chatter ranked better (EXP-08,
    # MRR +0.11) but answered two fewer dev questions end to end (EXP-12): not shipped, kept as levers.
    hybrid_bm25_weight: float = Field(0.5, ge=0.0, le=1.0, description="BM25 share of the hybrid fusion "
                                      "(0 = dense only, 1 = BM25 only)")
    source_prior: str | None = Field(None, description="score multipliers by path prefix or source system, "
                                     "e.g. 'meetings/:0.5,newsletters/:0.5' (unset = none)")
    reranker_model: str | None = Field(None, description="cross-encoder that re-ranks the top RERANK_TOP_N "
                                       "candidates (unset = no re-ranking)")
    rerank_top_n: int = Field(20, ge=1, le=100, description="candidates per retriever fed to the re-ranker")
    # Week 3 Task 5: "current" depends on the date. A version whose effective date is after AS_OF_DATE
    # is not in force yet. Default: the corpus snapshot date.
    as_of_date: date = Field(date(2026, 10, 1), description="the date policies are evaluated at (YYYY-MM-DD)")
    chunk_context_header: bool = Field(True, description="start every chunk with '<title> [<id> v<ver> ...] › "
                                       "<section>' (Week 3 Task 3); part of the index signature")
    # Week 3 Task 4 (week3/EXPERIMENTS.md): 400/50 won on retrieval (EXP-09) but answered worse
    # end to end (EXP-11), so the default stays 800/100.
    chunk_size: int = Field(800, ge=100, le=8000)
    chunk_overlap: int = Field(100, ge=0)
    # Week 3 Task 2: the system under test is the Week 3 corpus. It gets its OWN index path: pointing
    # an existing index at a different corpus makes the incremental ingest delete the old files from it
    # (Week 3 Task 1, loader_behaviour.log). The Week 1 corpus stays one setting away:
    # DATA_DIR=week1/data INDEX_PATH=.../faiss_index (what the Week 2 container still pins).
    index_path: Path = Field(CAPSTONE_DIR / "faiss_index_w3", description="where the FAISS index is persisted")
    data_dir: Path = Field(REPO_DIR / "week3" / "corpus", description="the corpus: a folder of .md/.txt files, "
                           "or a corpus export with _metadata.csv (documents listed there, in sub-folders)")
    # Week 3 Task 6: who's asking. user_id -> groups. Missing or unreadable = nobody can be served (503).
    directory_path: Path | None = Field(None, description="the user directory CSV; default: DATA_DIR/_directory.csv")

    @property
    def user_directory(self) -> Path:
        return Path(self.directory_path or Path(self.data_dir) / "_directory.csv")

    # ---- service -----------------------------------------------------------------
    api_host: str = Field("127.0.0.1", description="0.0.0.0 in a container; localhost otherwise (no auth yet)")
    api_port: int = Field(8000, ge=1, le=65535)
    session_ttl_seconds: float = Field(3600, gt=0)
    max_sessions: int = Field(10_000, ge=1)
    max_question_chars: int = Field(2000, ge=1)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # ---- resilience & guardrails (Task 8): see common/resilience.py ------------------
    llm_timeout_seconds: float = Field(30, gt=0, description="per LLM/embedding attempt")
    llm_max_retries: int = Field(2, ge=0, le=5, description="transport retries after the first attempt")
    llm_backoff_initial_seconds: float = Field(0.5, ge=0)
    llm_backoff_max_seconds: float = Field(4.0, ge=0)
    request_timeout_seconds: float = Field(60, gt=0, description="wall-clock budget for ONE request")
    max_llm_calls_per_request: int = Field(40, ge=1, description="attempts budget for ONE request "
                                           "(logical x transport retries never exceed it)")
    circuit_failure_threshold: int = Field(5, ge=1)
    circuit_cooldown_seconds: float = Field(30, gt=0)
    rate_limit_per_minute: int = Field(20, ge=1, description="requests per user_id (or per IP without one)")
    injection_guard_enabled: bool = True

    # ---- caching (Task 6) ------------------------------------------------------------
    cache_enabled: bool = Field(True, description="false = no answer cache AND no embedding cache")
    cache_ttl_seconds: float = Field(3600, gt=0, description="how long a cached ANSWER is served")
    cache_refusal_ttl_seconds: float = Field(
        300, ge=0, description="how long a cached REFUSAL is served (0 = never cache refusals)")
    cache_max_entries: int = Field(1000, ge=1)
    embedding_cache_path: Path | None = Field(
        None, description="file store for embeddings; default: next to INDEX_PATH (embedding_cache/)")
    cache_prewarm: int = Field(0, ge=0, le=50, description="answer the first N eval questions at "
                               "startup so the first users hit a warm cache")
    semantic_cache_enabled: bool = Field(
        False, description="deliberately NOT implemented: see week2/task_06_caching/CACHING.md")

    @field_validator("semantic_cache_enabled")
    @classmethod
    def _semantic_cache_is_a_decision(cls, v):
        if v:
            raise ValueError("SEMANTIC_CACHE_ENABLED=true: there is no semantic cache, by decision. On this "
                             "corpus near-duplicate questions have different answers; see "
                             "week2/task_06_caching/CACHING.md")
        return v

    @property
    def embedding_cache_dir(self) -> Path:
        return self.embedding_cache_path or Path(self.index_path).parent / "embedding_cache"

    # ---- cost accounting (Task 5): price per 1K tokens of the model you run. ------
    # Defaults are gpt-4o-mini's list price, so a local model still gets a projection
    # of what the same traffic would cost on a hosted one.
    cost_per_1k_input_tokens: float = Field(0.00015, ge=0)
    cost_per_1k_output_tokens: float = Field(0.0006, ge=0)

    def cost_usd(self, tokens_in: int, tokens_out: int) -> float:
        return (tokens_in / 1000) * self.cost_per_1k_input_tokens + \
               (tokens_out / 1000) * self.cost_per_1k_output_tokens

    @field_validator("llm_provider", "embedding_provider", mode="before")
    @classmethod
    def _lowercase(cls, v):
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("log_level", mode="before")
    @classmethod
    def _uppercase(cls, v):
        return v.strip().upper() if isinstance(v, str) else v

    @field_validator("openai_base_url", "groq_base_url", "ollama_base_url", "openai_reasoning_effort",
                     "source_prior", "reranker_model", mode="before")
    @classmethod
    def _blank_is_unset(cls, v):
        # `OPENAI_BASE_URL=` in a .env means "use the default", not "use the empty string"
        return None if isinstance(v, str) and not v.strip() else v

    @model_validator(mode="after")
    def _overlap_smaller_than_chunk(self):
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(f"CHUNK_OVERLAP ({self.chunk_overlap}) must be smaller than "
                             f"CHUNK_SIZE ({self.chunk_size})")
        return self

    @property
    def llm_label(self) -> str:
        """"provider:model", e.g. "ollama:qwen3.5:4b" (goes into every request log line)."""
        model = {"openai": self.openai_model, "groq": self.groq_model, "ollama": self.ollama_model,
                 "huggingface": self.hf_model}[self.llm_provider]
        return f"{self.llm_provider}:{model}"

    def summary(self) -> str:
        """One line for the startup log. No secrets live on this object."""
        base = {"openai": self.openai_base_url, "groq": self.groq_base_url,
                "ollama": self.ollama_base_url}.get(self.llm_provider)
        return (f"llm={self.llm_label} base_url={base or 'default'} "
                f"embeddings={self.embedding_provider} k={self.retriever_k} "
                f"chunks={self.chunk_size}/{self.chunk_overlap} index={self.index_path}")


@lru_cache
def get_settings() -> Settings:
    """The process-wide settings, read and validated once."""
    return Settings()


if __name__ == "__main__":
    import json

    s = get_settings()
    print(json.dumps(s.model_dump(mode="json"), indent=2))
    print(s.summary())
