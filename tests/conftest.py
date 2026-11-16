"""
Shared pytest fixtures for the Week 2 test suite.

Two tiers of test live here:
  * fast  — no network, no API key, must finish in < 5s. Runs on every PR.
  * live  — real model calls. Marked @pytest.mark.live, run on demand.

Run them with:
    make check        # lint + fast tier  (pytest -m "not live")
    make check-live   # live tier         (pytest -m live)

The capstone is one file, week1/capstone_internal_docs_assistant/app.py, and
Streamlit runs it as a script, not as a package. So the tests load it the same
way: from its file path (see `load_app`).
"""

import os
import socket
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
WEEK1 = REPO_ROOT / "week1"
APP_PATH = WEEK1 / "capstone_internal_docs_assistant" / "app.py"
DATA_DIR = WEEK1 / "data"

for p in (REPO_ROOT, WEEK1):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


# ---------------------------------------------------------------------------
# Fast-tier guard: make "no API key, no network" a fact, not a hope.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _fast_tier_is_offline(request, monkeypatch):
    """For every test NOT marked live: remove API keys, switch tracing off and
    make any network connection raise. A fast test that tries to reach a model
    fails loudly instead of quietly costing money or hanging on a timeout."""
    if request.node.get_closest_marker("live"):
        return
    for key in list(os.environ):
        if key.endswith(("_API_KEY", "_API_TOKEN")):
            monkeypatch.delenv(key)
    for key in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2"):
        monkeypatch.setenv(key, "false")

    def _no_network(self, address, *args, **kwargs):
        raise RuntimeError(f"fast tests must not touch the network (tried {address!r})")

    monkeypatch.setattr(socket.socket, "connect", _no_network)


# ---------------------------------------------------------------------------
# The app module, loaded exactly the way `streamlit run app.py` loads it.
# ---------------------------------------------------------------------------
def load_app():
    """Import week1/capstone_internal_docs_assistant/app.py from its path (once).

    Same loader as the HTTP service (app/capstone.py), so tests and service share
    one module object: monkeypatching it in a test changes what the service runs.
    """
    from app.capstone import CAPSTONE_PATH, load_capstone

    assert CAPSTONE_PATH == APP_PATH
    return load_capstone()


@pytest.fixture(scope="session")
def app():
    return load_app()


# ---------------------------------------------------------------------------
# Fake LLM — lets the fast tier run the real graph code with no network.
# ---------------------------------------------------------------------------
class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeLLM:
    """Stands in for a chat model.

    The capstone sends plain-string prompts and reads `.content`. `rules` maps the
    start of a prompt to the reply, so one fake can play router, grader, writer and
    fact-checker in the same run. Anything unmatched gets `text`.

        llm = FakeLLM(text="fallback", rules={"You route messages": "RETRIEVE"})

    `.with_structured_output(Schema)` / `.set_structured(...)` are kept for graphs
    that use structured graders.
    """

    def __init__(self, text="canned answer", rules=None):
        self.text = text
        self.rules = dict(rules or {})
        self._schema = None
        self._schema_kwargs = {}
        self.calls = []          # every prompt it was given, for assertions

    def invoke(self, prompt, *args, **kwargs):
        prompt = str(prompt)
        self.calls.append(prompt)
        if self._schema is not None:
            return self._schema(**self._schema_kwargs)
        for prefix, reply in self.rules.items():
            if prompt.startswith(prefix):
                return FakeMessage(reply)
        return FakeMessage(self.text)

    def calls_to(self, prefix):
        """The prompts that started with `prefix` (e.g. one of app's prompt constants)."""
        return [c for c in self.calls if c.startswith(prefix)]

    def with_structured_output(self, schema, **_):
        clone = FakeLLM(self.text, self.rules)
        clone.calls = self.calls          # share the call log
        clone._schema = schema
        clone._schema_kwargs = self._schema_kwargs
        return clone

    def set_structured(self, schema, **kwargs):
        self._schema = schema
        self._schema_kwargs = kwargs
        return self

    # LCEL support: `prompt | llm` needs the right-hand side to be pipeable.
    def __ror__(self, other):
        return _FakeChain(self, other)


class _FakeChain:
    def __init__(self, llm, upstream):
        self.llm = llm
        self.upstream = upstream

    def invoke(self, inputs, *args, **kwargs):
        return self.llm.invoke(str(inputs))


def prefix(template: str) -> str:
    """The fixed opening of a prompt template (the text before its first placeholder)."""
    return template.split("{", 1)[0][:60]


def scripted_llm(app, *, route="RETRIEVE", relevant="YES", grounded="YES", addresses="YES",
                 answer="Full-time employees get 20 days of PTO per year.\nSources: employee_handbook.md",
                 rewrite="paid time off policy", standalone=None, smalltalk="NO"):
    """A FakeLLM that answers each of the capstone's prompts with a fixed verdict."""
    rules = {
        prefix(app.ROUTE_PROMPT): route,
        prefix(app.GRADE_DOC_PROMPT): relevant,
        prefix(app.REWRITE_PROMPT): rewrite,
        prefix(app.GENERATE_PROMPT): answer,
        prefix(app.GROUNDED_PROMPT): f"Every sentence is checked.\nANSWER: {grounded}",
        prefix(app.ADDRESSES_PROMPT): addresses,
        prefix(app.SMALLTALK_PROMPT): smalltalk,
    }
    if standalone is not None:
        rules[prefix(app.CONTEXTUALIZE_PROMPT)] = standalone
    return FakeLLM(text="(unscripted prompt)", rules=rules)


@pytest.fixture
def fake_llm():
    """A FakeLLM you can configure per test."""
    return FakeLLM()


class FakeRetriever:
    """Returns the same documents for every query and records the queries."""

    def __init__(self, docs=()):
        self.docs = list(docs)
        self.queries = []

    def invoke(self, query, *args, **kwargs):
        self.queries.append(query)
        return list(self.docs)


# ---------------------------------------------------------------------------
# Documents & index
# ---------------------------------------------------------------------------
@pytest.fixture
def sample_docs():
    """A handful of Documents that look like the real corpus."""
    from langchain_core.documents import Document

    return [
        Document(
            page_content="Full-time employees accrue 20 days of PTO per year, "
                         "at 1.67 days per month. Up to 5 days carry over.",
            metadata={"source": "employee_handbook.md", "section": "2. Paid Time Off (PTO)"},
        ),
        Document(
            page_content="If your laptop is lost or stolen, immediately report "
                         "it to the Security team and file a ticket marked URGENT.",
            metadata={"source": "it_faq.md"},
        ),
        Document(
            page_content="The Warehouse Rover R2 has a maximum payload of 80 kg.",
            metadata={"source": "product_specs.md"},
        ),
    ]


@pytest.fixture
def temp_index_dir(app, tmp_path, monkeypatch):
    """An empty directory standing in for faiss_index/. The app's INDEX_DIR and
    MANIFEST_PATH point at it for the test, so the real index is never touched."""
    d = tmp_path / "faiss_index"
    monkeypatch.setattr(app, "INDEX_DIR", d)
    monkeypatch.setattr(app, "MANIFEST_PATH", d / "manifest.json")
    return d


@pytest.fixture
def corpus_dir(tmp_path):
    """A tiny markdown corpus on disk, for ingestion tests."""
    d = tmp_path / "data"
    d.mkdir()
    (d / "handbook.md").write_text(
        "# Handbook\n\n## PTO\nFull-time employees accrue 20 days of PTO per year. "
        "Up to 5 unused days carry over.\n\n## Sick leave\nEmployees get 10 paid sick days per year.\n",
        encoding="utf-8")
    (d / "it_faq.md").write_text(
        "# IT FAQ\n\n## Lost laptop\nReport a lost or stolen laptop to Security immediately "
        "and file an URGENT ticket.\n", encoding="utf-8")
    return d


@pytest.fixture
def fake_embeddings():
    """Deterministic offline embeddings: same text -> same vector, no model, no network."""
    from langchain_core.embeddings import DeterministicFakeEmbedding

    return DeterministicFakeEmbedding(size=32)


# ---------------------------------------------------------------------------
# The graph the APP actually uses.
# ---------------------------------------------------------------------------
@pytest.fixture
def make_backend(app, temp_index_dir, fake_embeddings, monkeypatch):
    """Build `Backend()` exactly as the UI, CLI and API create it, with the model
    (default: `scripted_llm`) and embeddings swapped for offline fakes.

    Backend imports get_llm / get_embeddings / DATA_DIR from `common.utils` when it
    is constructed, so a stand-in `common.utils` module is installed for the test.
    (The real one also loads week1/.env, which would put API keys back into the
    environment of a test that must not have any.)
    """
    def build(llm=None, **backend_kwargs):
        llm = llm if llm is not None else scripted_llm(app)
        fake_utils = types.ModuleType("common.utils")
        fake_utils.get_llm = lambda *a, **k: llm
        fake_utils.get_embeddings = lambda *a, **k: fake_embeddings
        fake_utils.DATA_DIR = DATA_DIR
        monkeypatch.setitem(sys.modules, "common.utils", fake_utils)
        backend = app.Backend(**backend_kwargs)
        backend.fake_llm = llm
        return backend

    return build


@pytest.fixture
def app_backend(make_backend):
    """`Backend()` as the app creates it, with the scripted fake model."""
    return make_backend()


@pytest.fixture
def app_graph(app_backend):
    """The compiled graph the app really runs: Backend() -> Assistant -> .graph.

    Built through the app's own construction path on purpose. If app.py ever
    builds its Assistant from a different graph (say, Task 8's), this is the graph
    that changes, and the regression test sees it.
    """
    return app_backend.assistant.graph
