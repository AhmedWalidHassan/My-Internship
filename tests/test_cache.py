"""
Fast tier — caching (Week 2, Task 6). Offline, scripted model.

  * exact-match answer cache: hits on normalised repeats, never on follow-ups;
  * invalidation: add_document makes every cached answer (and refusal) unservable;
  * refusals get a short TTL; CACHE_ENABLED=false runs the real pipeline every time;
  * the eval path (Assistant.ask) never sees the cache;
  * embedding cache: identical text is embedded once, across runs, per model.
"""

import shutil
import uuid

import pytest
from conftest import DATA_DIR, FakeLLM, prefix, scripted_llm
from langchain_core.embeddings import DeterministicFakeEmbedding
from structlog.testing import capture_logs
from test_api import sse

from app.cache import AnswerCache, CachedAnswer, normalize
from common import embedding_cache
from common import settings as settings_mod

Q = "How much PTO do I get?"


@pytest.fixture
def corpus(tmp_path):
    """A writable copy of the real corpus: add_document writes into it."""
    d = tmp_path / "corpus"
    shutil.copytree(DATA_DIR, d)
    return d


@pytest.fixture
def fresh_settings(monkeypatch):
    """Re-read settings from the (monkeypatched) environment, and again afterwards."""
    settings_mod.get_settings.cache_clear()
    yield monkeypatch
    settings_mod.get_settings.cache_clear()


def llm_calls(llm):
    return len(llm.calls)


def ask(client, question=Q, session=None, **headers):
    r = client.post("/chat", json={"user_id": "u1001", "question": question, "session_id": session or str(uuid.uuid4())},
                    headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def api(start_api, make_backend, corpus, app):
    llm = scripted_llm(app)
    backend = make_backend(llm, data_dir=corpus)
    client = start_api(lambda: backend)
    client.llm, client.backend = llm, backend
    return client


# ===========================================================================
# The key
# ===========================================================================

def test_normalisation_makes_trivial_variants_one_key():
    variants = ["How much PTO do I get?", "how much pto do i get", "  How much PTO   do I get ?! ",
                "HOW MUCH PTO DO I GET.", "How much PTO do I get？"]
    assert {normalize(v) for v in variants} == {"how much pto do i get"}
    assert normalize("How much PTO do I get?") != normalize("How much sick leave do I get?")


def test_key_changes_with_corpus_config_and_access_scope():
    k = AnswerCache.key
    base = k(Q, corpus_version="c1", fingerprint="f1", scope="s1")
    assert base == k("how much pto do i get", corpus_version="c1", fingerprint="f1", scope="s1")
    assert base != k(Q, corpus_version="c2", fingerprint="f1", scope="s1"), "a document changed"
    assert base != k(Q, corpus_version="c1", fingerprint="f2", scope="s1"), "the model, prompts or k changed"
    assert base != k(Q, corpus_version="c1", fingerprint="f1", scope="s2"), "someone who sees other documents"


# ===========================================================================
# Hits, misses, and what is never cached
# ===========================================================================

def test_repeated_first_question_is_served_from_cache(api, app):
    first = ask(api)
    calls = llm_calls(api.llm)
    with capture_logs() as logs:
        second = ask(api, "  how much PTO do I get ")             # new session, different surface form
    assert llm_calls(api.llm) == calls, "a cache hit must not call the model"
    assert second["cache_hit"] is True and first["cache_hit"] is False
    assert second["answer"] == first["answer"] and second["sources"] == first["sources"]
    assert second["node_path"] == ["cache"] and second["llm_calls"] == 0
    assert second["estimated_cost_usd"] == 0
    assert second["cached_from_trace_id"] == first["trace_id"]
    assert second["trace_id"] != first["trace_id"], "every request still gets its own trace id"
    [line] = [e for e in logs if e.get("event") == "request"]
    assert line["cache_hit"] is True and line["route"] == "cache" and line["tokens_in"] == 0
    metrics = api.get("/metrics").text
    assert "northwind_cache_hits_total 1.0" in metrics and "northwind_cache_entries 1.0" in metrics


def test_follow_ups_are_never_cached(api, app):
    """'Can I carry it over?' depends on the conversation: it must always run the graph."""
    api.llm.rules[prefix(app.CONTEXTUALIZE_PROMPT)] = "Can I carry unused PTO over to next year?"
    for session in ("a", "b"):
        ask(api, Q, session)                                      # turn 1 (b: a cache hit)
        calls = llm_calls(api.llm)
        r = ask(api, "Can I carry it over?", session)             # turn 2: identical text, both sessions
        assert r["cache_hit"] is False
        assert llm_calls(api.llm) > calls
        assert "contextualize" in r["node_path"]


def test_a_cached_answer_is_remembered_for_the_follow_up(api, app):
    ask(api, Q, "first-user")
    hit = ask(api, Q, "second-user")
    assert hit["cache_hit"] is True
    assert [t["question"] for t in api.get("/session/second-user", params={"user_id": "u1001"}).json()["turns"]] == [Q]
    api.llm.rules[prefix(app.CONTEXTUALIZE_PROMPT)] = "Can I carry unused PTO over to next year?"
    ask(api, "Can I carry it over?", "second-user")
    [ctx] = api.llm.calls_to(prefix(app.CONTEXTUALIZE_PROMPT))
    assert Q in ctx, "the follow-up must see the cached turn as history"


def test_stream_serves_a_hit_with_the_same_protocol(api):
    ask(api)
    with api.stream("POST", "/chat/stream", json={"user_id": "u1001", "question": Q}) as r:
        events = sse(r)
    kinds = [k for k, _ in events]
    assert kinds[0] == "status" and events[0][1]["node"] == "cache"
    assert "token" in kinds and kinds[-1] == "done"
    assert "".join(d["text"] for k, d in events if k == "token") == events[-1][1]["answer"]
    assert events[-1][1]["cache_hit"] is True


# ===========================================================================
# Invalidation — the test named in week2/RESULTS.md
# ===========================================================================

def test_add_document_invalidates_cached_answers(start_api, make_backend, corpus, app):
    """After add_document, neither a cached answer nor a cached refusal may be served:
    the next request runs the real pipeline on the new corpus."""
    llm = scripted_llm(app, answer=f"{app.REFUSAL}")             # the documents don't answer it yet
    backend = make_backend(llm, data_dir=corpus)
    client = start_api(lambda: backend)
    question = "What dental insurance plan does Northwind offer?"

    r1 = ask(client, question)
    assert r1["answer"] == app.REFUSAL and r1["cache_hit"] is False
    r2 = ask(client, question)
    assert r2["cache_hit"] is True, "a refusal is cached (short TTL) to absorb repeats"

    # someone adds the document that answers it
    llm.rules[prefix(app.GENERATE_PROMPT)] = "Northwind offers the DentalPlus Gold plan.\nSources: benefits.md"
    stats = backend.add_document("benefits.md", b"# Benefits\n\n## Dental\nNorthwind offers the DentalPlus "
                                                b"Gold dental plan to all full-time employees.\n")
    assert stats["added"] == ["benefits.md"]
    calls = llm_calls(llm)

    r3 = ask(client, question)
    assert r3["cache_hit"] is False, "the stale refusal must not be served after add_document"
    assert llm_calls(llm) > calls, "the real pipeline ran"
    assert "DentalPlus" in r3["answer"]
    metrics = client.get("/metrics").text
    assert "northwind_cache_invalidations 1.0" in metrics
    assert ask(client, question)["cache_hit"] is True, "and the NEW answer is cached"


def test_changing_a_document_also_invalidates(api, corpus):
    ask(api)
    assert ask(api)["cache_hit"] is True
    handbook = corpus / "employee_handbook.md"
    api.backend.add_document("employee_handbook.md", handbook.read_bytes() + b"\n\n## Note\nUpdated policy.\n")
    assert ask(api)["cache_hit"] is False


# ===========================================================================
# Refusal TTL
# ===========================================================================

class Clock:
    now = 0.0

    def __call__(self):
        return self.now


def entry(refused):
    return CachedAnswer(answer="x", sources=[], node_path=[], retries=0, refused=refused, trace_id="t",
                        tokens_in=0, tokens_out=0, llm_calls=0)


def test_refusals_expire_much_sooner_than_answers():
    clock = Clock()
    c = AnswerCache(ttl_seconds=3600, refusal_ttl_seconds=300, max_entries=10, timer=clock)
    c.put("answer", entry(refused=False))
    c.put("refusal", entry(refused=True))
    clock.now = 301
    assert c.get("refusal") is None and c.get("answer") is not None
    clock.now = 3601
    assert c.get("answer") is None


def test_refusal_ttl_zero_never_caches_refusals():
    c = AnswerCache(ttl_seconds=3600, refusal_ttl_seconds=0, max_entries=10)
    assert c.put("refusal", entry(refused=True)) is False and c.get("refusal") is None


# ===========================================================================
# CACHE_ENABLED=false, and the eval path
# ===========================================================================

def test_cache_disabled_runs_the_real_pipeline_every_time(fresh_settings, start_api, make_backend, app):
    fresh_settings.setenv("CACHE_ENABLED", "false")
    llm = scripted_llm(app)
    client = start_api(lambda: make_backend(llm))
    first = ask(client)
    calls = llm_calls(llm)
    second = ask(client)
    assert first["cache_hit"] is second["cache_hit"] is False
    assert llm_calls(llm) == 2 * calls, "the full pipeline ran twice"
    assert second["answer"] == first["answer"]
    metrics = client.get("/metrics").text
    assert "northwind_cache_enabled 0.0" in metrics and "northwind_cache_hits_total 0.0" in metrics


def test_cache_disabled_also_turns_off_the_embedding_cache(fresh_settings, tmp_path):
    import importlib
    import sys

    fresh_settings.setattr(settings_mod, "ENV_FILE", tmp_path / "missing.env")
    fresh_settings.delitem(sys.modules, "common.utils", raising=False)
    fresh_settings.setenv("EMBEDDING_PROVIDER", "openai")
    fresh_settings.setenv("OPENAI_API_KEY", "sk-dummy")
    fresh_settings.setenv("EMBEDDING_CACHE_PATH", str(tmp_path / "emb"))
    utils = importlib.import_module("common.utils")

    fresh_settings.setenv("CACHE_ENABLED", "true")
    settings_mod.get_settings.cache_clear()
    assert type(utils.get_embeddings()).__name__ == "CacheBackedEmbeddings"
    fresh_settings.setenv("CACHE_ENABLED", "false")
    settings_mod.get_settings.cache_clear()
    emb = utils.get_embeddings()
    assert type(emb).__name__ == "ResilientEmbeddings" and type(emb.inner).__name__ == "OpenAIEmbeddings"


def test_eval_path_never_sees_the_answer_cache(api):
    """Task 7's gate runs `app.py eval`, which calls Assistant.ask directly: a warm API cache
    must not stand in for the real pipeline there. Same for use_cache=False (cost report)."""
    ask(api)
    assert ask(api)["cache_hit"] is True
    calls = llm_calls(api.llm)
    api.backend.assistant.ask(Q, f"eval-{uuid.uuid4()}")              # what cmd_eval's target does
    assert llm_calls(api.llm) > calls
    service = api.app.state.runtime.service
    calls = llm_calls(api.llm)
    from common.access import PUBLIC, User
    r = service.ask(Q, f"cost-{uuid.uuid4()}", user=User("u1001", PUBLIC), trace_id=str(uuid.uuid4()),
                    use_cache=False)
    assert r.cache_hit is False and llm_calls(api.llm) > calls


def test_semantic_cache_flag_is_rejected_not_ignored(fresh_settings):
    fresh_settings.setenv("SEMANTIC_CACHE_ENABLED", "true")
    with pytest.raises(Exception) as err:
        settings_mod.Settings(_env_file=None)
    assert "semantic cache" in str(err.value).lower()


# ===========================================================================
# Embedding cache
# ===========================================================================

EMBEDDED: dict[str, list] = {}      # model_name -> texts it actually embedded (outside pydantic)


class CountingEmbeddings(DeterministicFakeEmbedding):
    """Counts the texts it actually embeds, per model name."""
    model_name: str = "fake-model-a"

    def embed_documents(self, texts):
        EMBEDDED.setdefault(self.model_name, []).extend(texts)
        return super().embed_documents(texts)

    def embed_query(self, text):
        EMBEDDED.setdefault(self.model_name, []).append(text)
        return super().embed_query(text)


def test_identical_text_is_embedded_once_across_runs(tmp_path):
    EMBEDDED.clear()
    texts = ["PTO policy chunk", "Sick leave chunk", "VPN chunk"]
    before = embedding_cache.stats()
    run1 = embedding_cache.with_cache(CountingEmbeddings(size=8), tmp_path)
    v1 = run1.embed_documents(texts)
    run1.embed_documents(texts)                                   # same process, again
    run2 = embedding_cache.with_cache(CountingEmbeddings(size=8), tmp_path)
    v2 = run2.embed_documents(texts)                              # "next run": a new object, same store
    assert EMBEDDED["fake-model-a"] == texts, "each text embedded exactly once"
    assert v1 == v2
    run2.embed_query("How much PTO do I get?")
    run2.embed_query("How much PTO do I get?")
    assert EMBEDDED["fake-model-a"].count("How much PTO do I get?") == 1, "queries are cached too"
    after = embedding_cache.stats()
    assert after["misses"] - before["misses"] == 4 and after["hits"] - before["hits"] == 7


def test_another_model_never_reads_these_vectors(tmp_path):
    EMBEDDED.clear()
    embedding_cache.with_cache(CountingEmbeddings(size=8, model_name="model-a"), tmp_path).embed_documents(["same text"])
    embedding_cache.with_cache(CountingEmbeddings(size=8, model_name="model-b"), tmp_path).embed_documents(["same text"])
    assert EMBEDDED["model-b"] == ["same text"], "a different model must embed for itself"


def test_cache_wrapper_does_not_change_the_index_signature(app, temp_index_dir, corpus_dir, tmp_path):
    """Turning the embedding cache on must not trigger a re-embed of the whole index."""
    base = DeterministicFakeEmbedding(size=16)
    cached = embedding_cache.with_cache(base, tmp_path / "emb")
    assert app._embedding_id(cached) == app._embedding_id(base)
    app.ingest(base, corpus_dir)                                   # index built without the cache
    _, stats = app.ingest(cached, corpus_dir)                      # restart with the cache on
    assert stats["rebuilt"] is False and stats["embedded_chunks"] == 0


def test_cache_disabled_fake_llm_still_answers(fresh_settings, start_api, make_backend, app):
    """The uncached path with the plain (non-LangChain) fake model too: nothing depends on the cache."""
    fresh_settings.setenv("CACHE_ENABLED", "false")
    llm = FakeLLM(text="(unscripted)", rules=scripted_llm(app).rules)
    client = start_api(lambda: make_backend(llm))
    assert "20 days" in ask(client)["answer"]
