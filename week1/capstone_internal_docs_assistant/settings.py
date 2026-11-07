"""Central configuration + model factories for the capstone.

Everything is driven by environment variables (see .env.example) so you can swap
Ollama <-> OpenAI <-> Groq, or hybrid <-> MMR retrieval, without touching code.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT.parent / ".env")  # repo-level .env (shared with Tasks 1-8)
load_dotenv(ROOT / ".env")         # optional capstone-local override


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


# ---------------------------------------------------------------- data / index
SUPPORTED_SUFFIXES = {".md", ".txt"}

def _default_data_dir() -> Path:
    """Prefer the course corpus in ../data/; fall back to the bundled sample."""
    course = ROOT.parent / "data"
    if course.exists() and any(
        f.suffix.lower() in SUPPORTED_SUFFIXES for f in course.rglob("*") if f.is_file()
    ):
        return course
    return ROOT / "sample_data"


DATA_DIR = Path(_env("DATA_DIR")) if _env("DATA_DIR") else _default_data_dir()
INDEX_DIR = Path(_env("INDEX_DIR")) if _env("INDEX_DIR") else ROOT / ".index"

CHUNK_SIZE = int(_env("CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(_env("CHUNK_OVERLAP", "100"))

# filename-prefix -> category. Used for metadata filtering driven by the router.
# The handbook and the HR policies cover overlapping ground (e.g. PTO is in the handbook,
# expenses in hr_policies), so both are one "hr" category: a router mistake between them
# must not hide the right file.
CATEGORY_RULES = [
    ("hr", "hr"),
    ("employee", "hr"),
    ("handbook", "hr"),
    ("it", "it"),
    ("product", "product"),
]
CATEGORIES = ["hr", "it", "product"]


def category_for(rel_path: str) -> str:
    """Category from the file name prefix, or from a parent folder name (e.g. hr/leave.md)."""
    parts = [p.lower() for p in Path(rel_path).parts]
    for part in reversed(parts):  # file name first, then its folders
        for prefix, cat in CATEGORY_RULES:
            if part.startswith(prefix):
                return cat
    return "general"


# ------------------------------------------------------------------- retrieval
RETRIEVER_MODE = _env("RETRIEVER_MODE", "hybrid")  # hybrid | mmr | similarity
RETRIEVE_K = int(_env("RETRIEVE_K", "4"))
MAX_REWRITES = int(_env("MAX_REWRITES", "1"))
MAX_GENERATIONS = int(_env("MAX_GENERATIONS", "2"))
GRADE_CONCURRENCY = int(_env("GRADE_CONCURRENCY", "2"))

# ------------------------------------------------------------------------ models
LLM_PROVIDER = _env("LLM_PROVIDER", "ollama")  # ollama | openai | groq
OLLAMA_MODEL = _env("OLLAMA_MODEL", "qwen3.5:4b")
OLLAMA_BASE_URL = _env("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_NUM_CTX = int(_env("OLLAMA_NUM_CTX", "8192"))
OPENAI_MODEL = _env("OPENAI_MODEL", "gpt-4o-mini")
GROQ_MODEL = _env("GROQ_MODEL", "llama-3.3-70b-versatile")

EMBED_PROVIDER = _env("EMBED_PROVIDER", "hf")  # hf | openai | fake (tests only)
EMBED_MODEL = _env("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")


def get_llm(temperature: float = 0.0, provider: str | None = None, model: str | None = None):
    """Chat model factory. `provider`/`model` let the eval use a different judge."""
    provider = (provider or LLM_PROVIDER).lower()
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        kwargs = dict(
            model=model or OLLAMA_MODEL,
            base_url=OLLAMA_BASE_URL,
            temperature=temperature,
            num_ctx=OLLAMA_NUM_CTX,
        )
        # Qwen3-style models "think" first, which is slow for many small calls
        # (router, grader, ...). Turn it off when the installed version supports it.
        if "reasoning" in ChatOllama.model_fields:
            kwargs["reasoning"] = False
        return ChatOllama(**kwargs)
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=model or OPENAI_MODEL, temperature=temperature)
    if provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(model=model or GROQ_MODEL, temperature=temperature)
    raise ValueError(f"Unknown LLM_PROVIDER: {provider}")


def get_embeddings():
    if EMBED_PROVIDER == "hf":
        from langchain_huggingface import HuggingFaceEmbeddings

        return HuggingFaceEmbeddings(
            model_name=EMBED_MODEL, encode_kwargs={"normalize_embeddings": True}
        )
    if EMBED_PROVIDER == "openai":
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(model=EMBED_MODEL if "openai" not in EMBED_MODEL else "text-embedding-3-small")
    if EMBED_PROVIDER == "fake":
        from langchain_core.embeddings import DeterministicFakeEmbedding

        return DeterministicFakeEmbedding(size=64)
    raise ValueError(f"Unknown EMBED_PROVIDER: {EMBED_PROVIDER}")


def embedding_fingerprint() -> str:
    """Changes whenever the index would need rebuilding."""
    return f"{EMBED_PROVIDER}:{EMBED_MODEL}:{CHUNK_SIZE}:{CHUNK_OVERLAP}"


def tracing_enabled() -> bool:
    flag = (_env("LANGSMITH_TRACING") or _env("LANGCHAIN_TRACING_V2")).lower() == "true"
    return flag and bool(_env("LANGSMITH_API_KEY") or _env("LANGCHAIN_API_KEY"))
