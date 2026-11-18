"""
Fast tier — configuration (Week 2, Task 4). No network, no real keys.

Everything deployment-specific is a setting with a default, read from the
environment: provider, model, base_url, retriever k, chunking, index path, API
host/port. Switching provider is an env change only, proven here by building the
real provider client for each preset from env vars alone.
"""

import importlib
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from common import settings as settings_mod
from common.settings import Settings

ALL_FIELDS = [name.upper() for name in Settings.model_fields]

# The .env blocks documented in week2/task_04_containerize/README.md. Keys are dummies:
# constructing a client does not call the provider.
PRESETS = {
    "openai": {"LLM_PROVIDER": "openai", "OPENAI_MODEL": "gpt-4o-mini", "OPENAI_API_KEY": "sk-dummy"},
    "openrouter": {"LLM_PROVIDER": "openai", "OPENAI_MODEL": "meta-llama/llama-3.3-70b-instruct",
                   "OPENAI_BASE_URL": "https://openrouter.ai/api/v1", "OPENAI_API_KEY": "sk-or-dummy"},
    "groq": {"LLM_PROVIDER": "groq", "GROQ_MODEL": "llama-3.3-70b-versatile", "GROQ_API_KEY": "gsk_dummy"},
    "ollama": {"LLM_PROVIDER": "ollama", "OLLAMA_MODEL": "qwen3.5:4b",
               "OLLAMA_BASE_URL": "http://host.docker.internal:11434"},
    "ollama-openai-compatible": {"LLM_PROVIDER": "openai", "OPENAI_MODEL": "qwen3.5:4b",
                                 "OPENAI_BASE_URL": "http://host.docker.internal:11434/v1",
                                 "OPENAI_API_KEY": "ollama", "OPENAI_REASONING_EFFORT": "none"},
}


@pytest.fixture
def clean_env(monkeypatch):
    """No setting in the environment, no .env file: only defaults apply."""
    for name in ALL_FIELDS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def settings(**env_file_free_kwargs):
    return Settings(_env_file=None, **env_file_free_kwargs)


def test_defaults_match_the_previous_hardcoded_values(clean_env):
    """Moving to settings must not change behaviour (or invalidate the saved index)."""
    s = settings()
    assert (s.retriever_k, s.chunk_size, s.chunk_overlap) == (4, 800, 100)
    assert s.index_path == settings_mod.CAPSTONE_DIR / "faiss_index"
    assert s.data_dir == settings_mod.WEEK1_DIR / "data"
    assert (s.api_host, s.api_port) == ("127.0.0.1", 8000)
    assert s.llm_provider == "openai" and s.openai_base_url is None


def test_every_setting_comes_from_the_environment(clean_env):
    env = {"RETRIEVER_K": "7", "CHUNK_SIZE": "600", "CHUNK_OVERLAP": "80", "INDEX_PATH": "/data/faiss_index",
           "DATA_DIR": "/app/data", "API_HOST": "0.0.0.0", "API_PORT": "9000", "LLM_PROVIDER": "Groq",
           "OPENAI_BASE_URL": "https://openrouter.ai/api/v1", "SESSION_TTL_SECONDS": "60", "LOG_LEVEL": "debug"}
    for k, v in env.items():
        clean_env.setenv(k, v)
    s = settings()
    assert (s.retriever_k, s.chunk_size, s.chunk_overlap) == (7, 600, 80)
    assert s.index_path == Path("/data/faiss_index") and s.data_dir == Path("/app/data")
    assert (s.api_host, s.api_port) == ("0.0.0.0", 9000)
    assert s.llm_provider == "groq", "provider names are case-insensitive"
    assert s.openai_base_url == "https://openrouter.ai/api/v1"
    assert s.session_ttl_seconds == 60 and s.log_level == "DEBUG"


def test_environment_beats_the_env_file(clean_env, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("RETRIEVER_K=9\nCHUNK_SIZE=1000\n", encoding="utf-8")
    clean_env.setenv("RETRIEVER_K", "3")
    s = Settings(_env_file=env_file)
    assert s.retriever_k == 3, "a real env var (docker compose) wins over the file"
    assert s.chunk_size == 1000, "the file fills in what the environment doesn't set"


@pytest.mark.parametrize("env, problem", [
    ({"LLM_PROVIDER": "olama"}, "llm_provider"),
    ({"RETRIEVER_K": "0"}, "retriever_k"),
    ({"RETRIEVER_K": "four"}, "retriever_k"),
    ({"CHUNK_SIZE": "500", "CHUNK_OVERLAP": "500"}, "CHUNK_OVERLAP"),
    ({"API_PORT": "70000"}, "api_port"),
])
def test_bad_configuration_fails_at_startup_with_a_clear_message(clean_env, env, problem):
    for k, v in env.items():
        clean_env.setenv(k, v)
    with pytest.raises(ValidationError) as err:
        settings()
    assert problem in str(err.value)


def test_blank_base_url_means_provider_default(clean_env):
    clean_env.setenv("OPENAI_BASE_URL", "")
    clean_env.setenv("OLLAMA_BASE_URL", "   ")
    s = settings()
    assert s.openai_base_url is None and s.ollama_base_url is None


def test_settings_hold_no_secrets(clean_env):
    """Keys stay with the SDKs; the settings object (which gets logged) never sees them."""
    clean_env.setenv("OPENAI_API_KEY", "sk-should-not-appear")
    s = settings()
    assert "sk-should-not-appear" not in s.model_dump_json() + s.summary()
    secret_like = [f for f in Settings.model_fields
                   if f.endswith(("_key", "_token", "_secret")) or "password" in f or "api_key" in f]
    assert not secret_like, secret_like


# ---------------------------------------------------------------------------
# Provider switch: env only
# ---------------------------------------------------------------------------
@pytest.fixture
def real_utils(clean_env, tmp_path):
    """The REAL common.utils, imported fresh, reading settings from the environment
    only (no week1/.env, so no real key is loaded into a fast test)."""
    clean_env.setattr(settings_mod, "ENV_FILE", tmp_path / "missing.env")
    clean_env.setattr(settings_mod, "get_settings", lambda: Settings(_env_file=None))
    clean_env.delitem(sys.modules, "common.utils", raising=False)
    return importlib.import_module("common.utils")


@pytest.mark.parametrize("preset", PRESETS)
def test_switching_provider_needs_only_env_changes(real_utils, clean_env, preset):
    for k, v in PRESETS[preset].items():
        clean_env.setenv(k, v)
    wrapped = real_utils.get_llm()
    # every provider is behind the resilience wrapper (Task 8): timeouts, retries, budget, breaker
    assert type(wrapped).__name__ == "ResilientLLM"
    llm = wrapped.inner
    env = PRESETS[preset]

    if env["LLM_PROVIDER"] == "openai":
        assert type(llm).__name__ == "ChatOpenAI"
        assert llm.model_name == env["OPENAI_MODEL"]
        assert llm.openai_api_base == env.get("OPENAI_BASE_URL")      # None = official API
        # sent only when configured: gpt-4o-mini would reject the parameter
        assert llm.reasoning_effort == env.get("OPENAI_REASONING_EFFORT")
        assert llm.max_retries == 0, "the SDK's own retries would multiply with ours"
        assert llm.request_timeout == 30
    elif env["LLM_PROVIDER"] == "groq":
        assert type(llm).__name__ == "ChatGroq"
        assert llm.model_name == env["GROQ_MODEL"]
    else:
        assert type(llm).__name__ == "ChatOllama"
        assert llm.model == env["OLLAMA_MODEL"] and llm.base_url == env["OLLAMA_BASE_URL"]


def test_no_provider_url_or_model_is_hardcoded_in_the_service_code():
    """The Task 4 trap: a base_url literal in common/utils.py silently breaks for
    anyone with a different key. Provider URLs belong in .env (or the docs)."""
    root = Path(__file__).resolve().parents[1]
    files = [root / "week1/common/utils.py", root / "week1/capstone_internal_docs_assistant/app.py",
             *sorted((root / "app").glob("*.py"))]
    for f in files:
        text = f.read_text(encoding="utf-8")
        for literal in ("openrouter.ai", "api.openai.com", "api.groq.com", ":11434", "gpt-4o", "qwen"):
            assert literal not in text, f"{literal!r} hardcoded in {f.relative_to(root)}"
