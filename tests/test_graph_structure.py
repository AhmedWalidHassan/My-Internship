"""
Fast tier — no network, no API key. Must run in under 5 seconds.

These tests assert on STRUCTURE and WIRING, never on model wording. The model is
a scripted fake (see conftest.py); what is under test is the app's own code: the
graph it builds, the edges between nodes, the prompts, memory and the index.

Run with:  make check
"""

from collections import deque

import pytest
from conftest import FakeLLM, FakeRetriever, prefix, scripted_llm

REFUSAL = "I don't know based on the provided documents."


def run_graph(app, llm, retriever, question="How much PTO do I get?", history=()):
    """Run the app's graph once and return the final state."""
    graph = app.build_graph(retriever, llm)
    return graph.invoke({"raw_question": question, "history": list(history), "path": []},
                        config={"recursion_limit": 25})


# ===========================================================================
# THE REGRESSION TEST
#
# A classic capstone bug: the app imports build_graph from the Task 8 module
# instead of the capstone's own graph. The app still runs and still answers, but
# it has no history node, so multi-turn memory is silently dead.
#
# `app_graph` is built through the app's real construction path (Backend() ->
# Assistant -> graph), so pointing the app at the wrong graph turns this RED.
# ===========================================================================

def test_app_graph_has_contextualize_node(app_graph):
    """The graph the app runs must have the history-aware node."""
    nodes = set(app_graph.get_graph().nodes)
    assert "contextualize" in nodes, (
        "The app's graph has no `contextualize` node, so follow-up questions are never "
        "resolved against the conversation. Is app.py building its Assistant from the "
        f"wrong build_graph (e.g. Task 8's)? Nodes found: {sorted(nodes)}"
    )


def test_app_graph_state_accepts_history(app_graph):
    """Without a `history` field in the state, the history the app passes in is dropped."""
    fields = app_graph.get_input_jsonschema()["properties"]
    assert "history" in fields, f"state has no `history` field: {sorted(fields)}"
    assert "raw_question" in fields


def test_app_graph_starts_by_resolving_history(app_graph):
    """contextualize must run FIRST: retrieval has to see the resolved question."""
    first = [e.target for e in app_graph.get_graph().edges if e.source == "__start__"]
    assert first == ["contextualize"]


# ===========================================================================
# GRAPH WIRING
# ===========================================================================

def test_graph_compiles(app):
    graph = app.build_graph(FakeRetriever(), FakeLLM())
    assert len(graph.get_graph().nodes) > 2


def test_every_conditional_edge_target_exists(app_graph):
    """A conditional edge pointing at a node name that doesn't exist is a runtime
    error waiting for the one question that takes that branch."""
    g = app_graph.get_graph()
    nodes = set(g.nodes)
    conditional = [e for e in g.edges if e.conditional]
    assert conditional, "expected conditional edges (routing, grading, fact-check)"
    for e in g.edges:
        assert e.source in nodes, f"edge from unknown node {e.source!r}"
        assert e.target in nodes, f"edge {e.source!r} -> unknown node {e.target!r}"


def test_all_nodes_reachable_from_start(app_graph):
    """An unreachable node is dead code you'll debug for an hour."""
    g = app_graph.get_graph()
    children = {}
    for e in g.edges:
        children.setdefault(e.source, set()).add(e.target)
    seen, todo = {"__start__"}, deque(["__start__"])
    while todo:
        for nxt in children.get(todo.popleft(), ()):
            if nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    assert set(g.nodes) - seen == set(), f"unreachable nodes: {set(g.nodes) - seen}"


def test_every_node_can_reach_end(app_graph):
    """The other half of termination: no node is a dead end."""
    g = app_graph.get_graph()
    parents = {}
    for e in g.edges:
        parents.setdefault(e.target, set()).add(e.source)
    seen, todo = {"__end__"}, deque(["__end__"])
    while todo:
        for prev in parents.get(todo.popleft(), ()):
            if prev not in seen:
                seen.add(prev)
                todo.append(prev)
    assert set(g.nodes) - seen == set(), f"nodes that can never finish: {set(g.nodes) - seen}"


# ===========================================================================
# PROMPT AND FORMATTING CONTRACTS
# ===========================================================================

def test_format_docs_tags_every_source(app, sample_docs):
    """Citations start here: the generator can only cite what it is shown."""
    text = app.format_docs(sample_docs)
    for d in sample_docs:
        assert f"[{d.metadata['source']}]" in text


def test_generate_prompt_contains_refusal_instruction(app):
    """The anti-hallucination rule is non-negotiable, so it is pinned by a test.
    If someone weakens the prompt, this goes red before any eval runs."""
    assert app.REFUSAL == REFUSAL
    assert REFUSAL in app.GENERATE_PROMPT
    assert "ONLY using the context" in app.GENERATE_PROMPT


def test_split_sources_strips_the_sources_line(app):
    answer, cited = app.split_sources(
        "You get 20 days of PTO.\nSources: employee_handbook.md, hr_policies.md")
    assert answer == "You get 20 days of PTO."
    assert cited == ["employee_handbook.md", "hr_policies.md"]


def test_no_answer_is_generated_when_nothing_is_retrieved(app):
    """When retrieval finds nothing, the graph must refuse WITHOUT asking the model
    to write an answer: no generation call, no cost, nothing to hallucinate from.

    (The capstone has no standalone `generate()` function to call directly, so this
    runs the whole graph with an empty retriever and inspects which prompts were sent.)
    """
    llm = scripted_llm(app)
    final = run_graph(app, llm, FakeRetriever(docs=[]))
    assert final["generation"] == REFUSAL
    assert final["path"][-1] == "refuse"
    assert "generate" not in final["path"]
    assert llm.calls_to(prefix(app.GENERATE_PROMPT)) == []


def test_unsupported_answer_is_never_returned(app, sample_docs):
    """If the fact-check rejects every answer, the user gets the refusal, not the
    rejected text."""
    llm = scripted_llm(app, grounded="NO", answer="You get 45 days of PTO.\nSources: x.md")
    final = run_graph(app, llm, FakeRetriever(sample_docs))
    assert final["generation"] == REFUSAL
    assert "45" not in final["generation"]


def test_smalltalk_routes_direct_without_retrieving(app, sample_docs):
    llm = scripted_llm(app, route="DIRECT", smalltalk="YES")
    llm.text = "Hi! I answer questions about Northwind policies."
    retriever = FakeRetriever(sample_docs)
    final = run_graph(app, llm, retriever, question="hello, who are you?")
    assert final["path"][-1] == "direct_answer"
    assert retriever.queries == []


def test_out_of_domain_direct_route_refuses(app, sample_docs):
    """A non-work question sent DIRECT gets the fixed refusal; the model never
    gets the chance to "helpfully" answer it."""
    llm = scripted_llm(app, route="DIRECT", smalltalk="NO")
    final = run_graph(app, llm, FakeRetriever(sample_docs), question="What is the capital of France?")
    assert final["generation"] == REFUSAL


# ===========================================================================
# MEMORY  (wiring, with a fake model)
# ===========================================================================

def test_follow_up_is_resolved_against_history_before_retrieval(app, sample_docs):
    """Turn 2 must be rewritten using turn 1, and retrieval must use the rewrite."""
    llm = scripted_llm(app, standalone="Can I carry unused PTO over to next year?")
    retriever = FakeRetriever(sample_docs)
    assistant = app.Assistant(retriever, llm)

    assistant.ask("How much PTO do I get?", "user-a")
    assert llm.calls_to(prefix(app.CONTEXTUALIZE_PROMPT)) == [], "turn 1 has no history to resolve"

    result = assistant.ask("Can I carry it over to next year?", "user-a")
    ctx_calls = llm.calls_to(prefix(app.CONTEXTUALIZE_PROMPT))
    assert len(ctx_calls) == 1
    assert "How much PTO do I get?" in ctx_calls[0], "turn 1 must be in the contextualize prompt"
    assert result["standalone"] == "Can I carry unused PTO over to next year?"
    assert retriever.queries[-1] == "Can I carry unused PTO over to next year?"


def test_sessions_do_not_share_history(app, sample_docs):
    """Session B's first question must not see session A's conversation."""
    llm = scripted_llm(app, standalone="Can I carry unused PTO over to next year?")
    assistant = app.Assistant(FakeRetriever(sample_docs), llm)

    assistant.ask("How much PTO do I get?", "user-a")
    result_b = assistant.ask("Can I carry it over?", "user-b")

    assert llm.calls_to(prefix(app.CONTEXTUALIZE_PROMPT)) == [], "B has no history, so nothing to resolve"
    assert result_b["standalone"] == "Can I carry it over?"
    assert [q for q, _ in assistant.history("user-a")] == ["How much PTO do I get?"]
    assert [q for q, _ in assistant.history("user-b")] == ["Can I carry it over?"]


def test_reset_clears_only_that_session(app, sample_docs):
    assistant = app.Assistant(FakeRetriever(sample_docs), scripted_llm(app))
    assistant.ask("How much PTO do I get?", "user-a")
    assistant.ask("How much PTO do I get?", "user-b")
    assistant.reset("user-a")
    assert assistant.history("user-a") == []
    assert len(assistant.history("user-b")) == 1


# ===========================================================================
# INDEX PERSISTENCE  (the other half of the wrong-graph bug)
# ===========================================================================

@pytest.fixture
def faiss_spy(monkeypatch):
    """Count FAISS.from_documents (= embed the corpus) and FAISS.load_local (= read
    from disk) while still calling the real methods."""
    from langchain_community.vectorstores import FAISS

    calls = {"from_documents": 0, "load_local": 0}
    real_from_documents, real_load_local = FAISS.from_documents, FAISS.load_local

    def from_documents(*args, **kwargs):
        calls["from_documents"] += 1
        return real_from_documents(*args, **kwargs)

    def load_local(*args, **kwargs):
        calls["load_local"] += 1
        return real_load_local(*args, **kwargs)

    monkeypatch.setattr(FAISS, "from_documents", from_documents)
    monkeypatch.setattr(FAISS, "load_local", load_local)
    return calls


def test_vectorstore_builds_when_index_missing(app, temp_index_dir, corpus_dir, fake_embeddings, faiss_spy):
    assert not temp_index_dir.exists()
    store, stats = app.ingest(fake_embeddings, corpus_dir)

    assert faiss_spy == {"from_documents": 1, "load_local": 0}
    assert stats["rebuilt"] is True
    assert stats["embedded_chunks"] == len(store.docstore._dict) > 0
    assert (temp_index_dir / "index.faiss").exists(), "the built index must be saved"
    assert (temp_index_dir / "manifest.json").exists()


def test_vectorstore_loads_from_disk_when_index_exists(app, temp_index_dir, corpus_dir, fake_embeddings, faiss_spy):
    first, _ = app.ingest(fake_embeddings, corpus_dir)            # cold start: builds
    faiss_spy.update(from_documents=0, load_local=0)

    second, stats = app.ingest(fake_embeddings, corpus_dir)       # warm start
    assert faiss_spy == {"from_documents": 0, "load_local": 1}, "warm start must LOAD, not embed"
    assert stats["rebuilt"] is False
    assert stats["embedded_chunks"] == 0
    assert sorted(stats["reused"]) == ["handbook.md", "it_faq.md"]
    assert len(second.docstore._dict) == len(first.docstore._dict)


def test_only_a_changed_file_is_reembedded(app, temp_index_dir, corpus_dir, fake_embeddings, faiss_spy):
    app.ingest(fake_embeddings, corpus_dir)
    (corpus_dir / "it_faq.md").write_text("# IT FAQ\n\n## VPN\nUse GlobalConnect with SSO and MFA.\n",
                                          encoding="utf-8")
    store, stats = app.ingest(fake_embeddings, corpus_dir)
    assert stats["updated"] == ["it_faq.md"]
    assert stats["reused"] == ["handbook.md"]
    texts = " ".join(d.page_content for d in store.docstore._dict.values())
    assert "GlobalConnect" in texts and "stolen laptop" not in texts


def test_changing_the_embedding_model_forces_a_rebuild(app, temp_index_dir, corpus_dir, fake_embeddings,
                                                       faiss_spy, monkeypatch):
    """Vectors from two different models in one index would be meaningless."""
    app.ingest(fake_embeddings, corpus_dir)
    monkeypatch.setattr(app, "_embedding_id", lambda _e: "some-other-model")
    _, stats = app.ingest(fake_embeddings, corpus_dir)
    assert stats["rebuilt"] is True


# ===========================================================================
# TERMINATION  (stretch)
# ===========================================================================

@pytest.mark.parametrize("failure", ["docs_always_irrelevant", "answers_always_ungrounded"])
def test_graph_terminates_at_max_retries(app, sample_docs, failure):
    """Force the worst path; the graph must still reach END, with the refusal, in
    exactly MAX_RETRIES rewrites, well inside the recursion limit."""
    if failure == "docs_always_irrelevant":
        llm = scripted_llm(app, relevant="NO", grounded="NO")
    else:
        llm = scripted_llm(app, relevant="YES", grounded="NO")
    final = run_graph(app, llm, FakeRetriever(sample_docs))   # recursion_limit=25 would raise

    assert final["path"][-1] == "refuse"
    assert final["generation"] == REFUSAL
    assert final["retries"] == app.MAX_RETRIES
    assert final["path"].count("rewrite_query") == app.MAX_RETRIES
