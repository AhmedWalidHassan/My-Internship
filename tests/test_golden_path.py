"""
Live tier — real model calls through the app's real entry point (Backend()).
Slow and, with a paid provider, costs money. Run on demand, not on every PR.

One test per capstone must-have: the things a mentor will try in the Friday demo,
so the things a machine tries first. Every assertion is on a FACT or on
STRUCTURE (a number, a cited file, the refusal string, the node path), never on
the model's wording.

Needs week1/.env configured and the model server running (e.g. `ollama serve`).
Run with:  make check-live
"""

import re
import time
import uuid

import pytest
from conftest import DATA_DIR, corpus_facts, load_app

pytestmark = pytest.mark.live

REFUSAL = "I don't know based on the provided documents."


@pytest.fixture(scope="module")
def backend():
    """The same Backend the Streamlit UI and the CLI create (loads the real index)."""
    return load_app().Backend()


def ask(backend, question, session=None):
    return backend.assistant.ask(question, session or f"test-{uuid.uuid4()}")


def cited_files(result):
    return {label.split(" › ")[0] for label in result["sources"]}


# ===========================================================================
# Must-have 1 & 4 — grounded answer, with a citation
# ===========================================================================

def test_grounded_answer_with_citation(backend):
    r = ask(backend, "How many sick days do I get per year?")
    assert re.search(r"\b10\b|\bten\b", r["answer"], re.I), r["answer"]
    # Week 1 corpus: the handbook. Week 3 corpus: the policy that is authoritative now (Task 1 triage).
    assert corpus_facts()["sick_days_source"] in cited_files(r), r["sources"]
    assert "retrieve" in r["path"]


# ===========================================================================
# Must-have 2 — refuses instead of hallucinating
# ===========================================================================

def test_out_of_scope_question_is_refused(backend):
    r = ask(backend, "What is the CEO's home address?")
    assert REFUSAL in r["answer"], r["answer"]
    assert r["sources"] == [], "a refusal must not cite sources"


def test_plausible_sounding_out_of_scope_is_refused(backend):
    """Week 1 corpus: sounds internal, but the corpus only covers remote work from HOME
    (3 days a week), not from abroad. It must refuse rather than stretch the home policy.

    Week 3 corpus (Task 1 triage, "the world changed"): HR-POL-011 Work From Abroad
    (2026-04-01) now answers it: up to 30 days a year. Refusing is now the wrong answer."""
    facts = corpus_facts()
    r = ask(backend, "What's our policy on remote work from abroad?")
    if not facts["abroad_answerable"]:
        assert REFUSAL in r["answer"], f"answered instead of refusing: {r['answer']!r} (path {r['path']})"
    else:
        assert REFUSAL not in r["answer"], f"refused a question HR-POL-011 answers (path {r['path']})"
        assert re.search(facts["abroad_fact"], r["answer"], re.I), r["answer"]
        assert facts["abroad_source"] in cited_files(r), r["sources"]


# ===========================================================================
# Must-have 3 — conversational memory
# ===========================================================================

def test_two_turn_follow_up_resolves_pronoun(backend):
    session = f"test-{uuid.uuid4()}"
    ask(backend, "How much PTO do I get?", session)
    follow_up = "Can I carry it over to next year?"
    assert "PTO" not in follow_up

    r = ask(backend, follow_up, session)
    assert re.search(r"\b(PTO|paid time off|vacation)\b", r["standalone"], re.I), (
        f"'it' was not resolved: understood as {r['standalone']!r}")
    facts = corpus_facts()       # Week 3: HR-POL-004 v3 says 3 days, not 5 (Task 1 triage)
    assert re.search(facts["pto_carry_over"], r["answer"], re.I), r["answer"]
    assert facts["pto_source"] in cited_files(r), r["sources"]


def test_sessions_are_isolated(backend):
    """Session B gets A's follow-up cold. Its question must NOT be resolved with A's
    context.

    The assertion is on what B's question was understood as, not on B's answer:
    "carry over" alone can legitimately retrieve the PTO section, so an answer
    mentioning PTO would not prove a leak, and one without it would not prove isolation.
    """
    ask(backend, "How much PTO do I get?", "user-a")
    q = "Can I carry it over?"
    r = ask(backend, q, "user-b")
    assert r["standalone"] == q, f"B's question was rewritten from someone's history: {r['standalone']!r}"
    assert [u for u, _ in backend.assistant.history("user-b")] == [q]
    assert "user-b" not in str(backend.assistant.history("user-a"))


# ===========================================================================
# Must-have 5 — the index is persisted, not rebuilt
# ===========================================================================

def test_warm_start_does_not_reembed(backend, tmp_path, monkeypatch):
    """Build into a temp dir with the REAL embedding model, then start again."""
    app = load_app()
    monkeypatch.setattr(app, "INDEX_DIR", tmp_path / "faiss_index")
    monkeypatch.setattr(app, "MANIFEST_PATH", tmp_path / "faiss_index" / "manifest.json")

    t0 = time.perf_counter()
    _, cold = app.ingest(backend.embeddings, DATA_DIR)
    t_cold = time.perf_counter() - t0
    t0 = time.perf_counter()
    _, warm = app.ingest(backend.embeddings, DATA_DIR)
    t_warm = time.perf_counter() - t0
    print(f"\ncold start: {t_cold:.3f}s, {cold['embedded_chunks']} chunks embedded | "
          f"warm start: {t_warm:.3f}s, {warm['embedded_chunks']} chunks embedded")

    assert cold["rebuilt"] and cold["embedded_chunks"] > 0
    assert not warm["rebuilt"] and warm["embedded_chunks"] == 0
    assert t_warm < t_cold


# ===========================================================================
# Agentic behaviour — does the self-correction loop actually fire?
# ===========================================================================

@pytest.mark.xfail(strict=False, reason=(
    "Finding (week2/RESULTS.md, Task 1 and Task 2): with the production hybrid "
    "retriever (BM25 + dense, k=4) the first search already finds the PTO section, "
    "so the grader keeps it and no rewrite is needed. The loop does fire on "
    "unanswerable questions; see test_unanswerable_question_exhausts_rewrites."))
def test_awkward_query_triggers_rewrite_loop(backend):
    r = ask(backend, "time off carry rules?")
    print("\npath:", " -> ".join(r["path"]))
    assert "rewrite_query" in r["path"]


def test_unanswerable_question_exhausts_rewrites(backend):
    """Where the loop really fires: nothing relevant exists, so the graph rewrites
    MAX_RETRIES times, then stops and refuses."""
    app = load_app()
    r = ask(backend, "What dental insurance plan does Northwind offer?")
    print("\npath:", " -> ".join(r["path"]))
    assert REFUSAL in r["answer"]
    assert r["path"].count("rewrite_query") <= app.MAX_RETRIES
    assert "rewrite_query" in r["path"] or r["path"][-1] == "direct_answer"
