"""Offline tests: no Ollama, no model downloads. A scripted fake LLM + fake
embeddings check the *wiring* of ingestion, retrieval and the agent graph.
(They say nothing about answer quality -- that's what eval/run_eval.py is for.)

    pytest capstone_internal_docs_assistant/tests -q
"""
import os
import sys
from pathlib import Path

os.environ["EMBED_PROVIDER"] = "fake"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

import settings
from backend import RagBackend

SAMPLE = Path(__file__).resolve().parents[1] / "sample_data"


class FakeLLM(BaseChatModel):
    """Answers by sniffing which prompt it received."""

    grounded: bool = True

    @property
    def _llm_type(self) -> str:
        return "fake"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        text = "\n".join(str(m.content) for m in messages)
        if "route messages" in text:
            last = messages[-1].content.lower()
            out = "route: smalltalk\ncategory: any" if "hello" in last else "route: docs\ncategory: any"
        elif "Rewrite the user's latest message" in text:
            out = "How many PTO days per year?"          # follow-up resolved
        elif "grade retrieved passages" in text:
            question, passage = text.split("Passage:")[0], text.split("Passage:")[-1]
            out = "yes" if any(k in question and k in passage for k in ("PTO", "GlobalConnect")) else "no"
        elif "short keyword-style search query" in text:
            out = "paid time off accrual"
        elif "answer employee questions" in text:
            out = "Full-time employees get 20 PTO days per year [hr_policies.md]." if "PTO" in text else "I don't know based on the available documents."
        elif "supported by the context" in text:
            out = "yes" if self.grounded else "no"
        else:
            out = "Hi! Ask me about HR, IT or product specs."
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=out))])


@pytest.fixture()
def backend(tmp_path):
    return RagBackend(llm=FakeLLM(), data_dir=SAMPLE, index_dir=tmp_path / "idx")


def test_index_is_persisted_and_not_reembedded(tmp_path):
    first = RagBackend(llm=FakeLLM(), data_dir=SAMPLE, index_dir=tmp_path / "idx")
    assert len(first.sync_report["added"]) == 5
    second = RagBackend(llm=FakeLLM(), data_dir=SAMPLE, index_dir=tmp_path / "idx")
    assert second.sync_report["added"] == [] and len(second.sync_report["unchanged"]) == 5


def test_add_document_is_incremental(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    for f in SAMPLE.glob("*.md"):
        (data / f.name).write_text(f.read_text())
    b = RagBackend(llm=FakeLLM(), data_dir=data, index_dir=tmp_path / "idx")
    before = b.stats()["chunks"]
    report = b.add_document("it_vpn_tips.md", "# VPN tips\nReboot the router before calling IT.")
    assert report["added"] == ["it_vpn_tips.md"] and len(report["unchanged"]) == 5
    assert b.stats()["chunks"] > before


@pytest.mark.parametrize("mode", ["hybrid", "mmr", "similarity"])
def test_retriever_modes_and_category_filter(backend, mode):
    backend.retriever.mode = mode
    docs = backend.retriever.retrieve("how many PTO days", k=3, category="hr")
    assert docs and all(d.metadata["category"] == "hr" for d in docs)


def test_hybrid_finds_exact_keyword(backend):
    docs = backend.retriever.retrieve("GlobalConnect", k=3)
    assert any(d.metadata["source"] == "it_faq.md" for d in docs)


def test_grounded_answer_has_citation(backend):
    res = backend.invoke("How many PTO days do I get?", "s1")
    assert not res["refused"] and "20" in res["answer"]
    assert any(s.startswith("hr_policies.md") for s in res["sources"])


def test_out_of_scope_is_refused(backend):
    res = backend.invoke("How do I cook carbonara?", "s2")
    assert res["refused"] and res["sources"] == []


def test_failed_hallucination_check_refuses(tmp_path):
    b = RagBackend(llm=FakeLLM(grounded=False), data_dir=SAMPLE, index_dir=tmp_path / "idx")
    assert b.invoke("How many PTO days do I get?", "s3")["refused"]


def test_smalltalk_skips_retrieval(backend):
    res = backend.invoke("hello", "s4")
    assert res["route"] == "smalltalk" and res["retrieved_sources"] == []


def test_memory_is_per_session(backend):
    backend.invoke("How many PTO days do I get?", "A")
    follow = backend.invoke("And after five years?", "A")
    assert follow["standalone"] == "How many PTO days per year?"      # condensed using history
    fresh = backend.invoke("And after five years?", "B")
    assert fresh["standalone"] == "And after five years?"             # session B has no history


def test_stream_yields_steps_then_final(backend):
    events = list(backend.stream("How many PTO days do I get?", "s5"))
    assert events[-1]["type"] == "final" and any(e["type"] == "step" for e in events[:-1])


def test_nested_folders_use_relative_names_and_folder_category(tmp_path):
    data = tmp_path / "data"
    (data / "hr").mkdir(parents=True)
    (data / "hr" / "leave.md").write_text("# Leave\n## PTO\nEmployees get 20 PTO days.")
    (data / ".hidden").mkdir()
    (data / ".hidden" / "x.md").write_text("# no\nignored")
    b = RagBackend(llm=FakeLLM(), data_dir=data, index_dir=tmp_path / "idx")
    assert b.sync_report["added"] == ["hr/leave.md"]
    doc = b.retriever.retrieve("PTO days", k=1)[0]
    assert doc.metadata["source"] == "hr/leave.md" and doc.metadata["category"] == "hr"
    res = b.invoke("How many PTO days do I get?", "n1")
    assert res["sources"] and res["sources"][0].startswith("hr/leave.md")
