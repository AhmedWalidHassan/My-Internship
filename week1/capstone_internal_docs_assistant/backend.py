"""The RAG backend the Streamlit app and the eval harness both talk to."""
from __future__ import annotations

import uuid
from typing import Iterator

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

import settings
from agent_graph import build_graph
from ingestion import IndexManager
from retrieval import HybridRetriever

STEP_LABELS = {
    "condense": "Understanding the question",
    "route": "Routing",
    "smalltalk": "Replying",
    "retrieve": "Searching the documents",
    "grade": "Grading passages",
    "rewrite": "Rewriting the query",
    "generate": "Drafting an answer",
    "check": "Checking the answer against the sources",
    "refuse": "Nothing reliable found",
    "finalize": "Finalizing",
}


def _step_detail(node: str, update: dict) -> str:
    label = STEP_LABELS.get(node, node)
    if node == "route":
        return f"{label}: {update.get('route')} (filter: {update.get('category')})"
    if node == "retrieve":
        files = sorted({d.metadata["source"] for d in update.get("documents", [])})
        return f"{label}: {len(update.get('documents', []))} passages from {', '.join(files) or 'none'}"
    if node == "grade":
        return f"{label}: {len(update.get('relevant', []))} relevant"
    if node == "rewrite":
        return f"{label}: “{update.get('search_query')}”"
    if node == "check":
        return f"{label}: {'supported ✅' if update.get('grounded') else 'NOT supported ⚠️'}"
    return label


class RagBackend:
    def __init__(self, llm=None, embeddings=None, data_dir=None, index_dir=None, retriever_mode: str | None = None):
        self.llm = llm or settings.get_llm()
        self.index = IndexManager(data_dir=data_dir, index_dir=index_dir, embeddings=embeddings)
        self.sync_report = self.index.sync()
        self.retriever = HybridRetriever(self.index.vectorstore, mode=retriever_mode or settings.RETRIEVER_MODE)
        self.memory = MemorySaver()  # one thread per Streamlit session
        self.graph = build_graph(self.llm, self.retriever, self.memory)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _inputs(question: str) -> dict:
        # Per-turn fields must be reset: the checkpointer keeps the previous turn's state.
        return {
            "messages": [HumanMessage(content=question)],
            "question": question,
            "documents": [], "relevant": [], "rewrites": 0, "attempts": 0,
            "answer": "", "grounded": False, "refused": False, "sources": [], "category": "any",
        }

    @staticmethod
    def _config(session_id: str, run_id: uuid.UUID) -> dict:
        return {
            "configurable": {"thread_id": session_id},
            "run_id": run_id,
            "run_name": "northwind-internal-docs-assistant",
            "tags": ["capstone"],
            "metadata": {"session_id": session_id},
        }

    @staticmethod
    def _result(state: dict, run_id: uuid.UUID) -> dict:
        return {
            "answer": state.get("answer", ""),
            "sources": state.get("sources", []),
            "refused": bool(state.get("refused")),
            "route": state.get("route"),
            "category": state.get("category"),
            "standalone": state.get("standalone"),
            "retrieved_sources": sorted({d.metadata["source"] for d in state.get("documents", [])}),
            "contexts": [d.page_content for d in state.get("relevant", [])],
            "run_id": str(run_id),
        }

    # ---------------------------------------------------------------- public API
    def invoke(self, question: str, session_id: str) -> dict:
        run_id = uuid.uuid4()
        state = self.graph.invoke(self._inputs(question), self._config(session_id, run_id))
        return self._result(state, run_id)

    def stream(self, question: str, session_id: str) -> Iterator[dict]:
        """Yield {"type": "step", "text": ...} per graph node, then {"type": "final", **result}."""
        run_id = uuid.uuid4()
        config = self._config(session_id, run_id)
        for chunk in self.graph.stream(self._inputs(question), config, stream_mode="updates"):
            for node, update in chunk.items():
                yield {"type": "step", "node": node, "text": _step_detail(node, update or {})}
        state = self.graph.get_state(config).values
        yield {"type": "final", **self._result(state, run_id)}

    def reset_session(self, session_id: str) -> None:
        try:
            self.memory.delete_thread(session_id)
        except Exception:
            pass  # old langgraph versions: a new session_id is enough anyway

    def add_document(self, filename: str, content: str) -> dict:
        report = self.index.add_file(filename, content)
        self.retriever.refresh()
        return report

    def stats(self) -> dict:
        return {**self.index.stats(), "retriever": self.retriever.mode}

    def feedback(self, run_id: str, score: int, comment: str | None = None) -> bool:
        """Log a thumbs up/down to LangSmith. Returns False if tracing isn't configured."""
        if not settings.tracing_enabled():
            return False
        try:
            from langsmith import Client

            Client().create_feedback(run_id=run_id, key="user_score", score=score, comment=comment)
            return True
        except Exception:
            return False
