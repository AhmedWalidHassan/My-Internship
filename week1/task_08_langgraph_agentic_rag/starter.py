"""
Task 8 — Corrective / self-correcting RAG with LangGraph.
"""

import importlib.util
import operator
import re
import sys
from pathlib import Path
from typing import Annotated, TypedDict

sys.path.append(str(Path(__file__).resolve().parents[1]))

from langchain_core.documents import Document
from langgraph.graph import END, START, StateGraph

MAX_RETRIES = 2
REFUSAL = "I don't know based on the provided documents."


# ---------------------------------------------------------------------------
# 1. State
# ---------------------------------------------------------------------------
class GraphState(TypedDict, total=False):
    question: str                    # original user question (never changes)
    rewritten_question: str          # query used for retrieval (starts = question)
    documents: list[Document]        # currently retrieved (then graded) chunks
    generation: str                  # the answer
    route: str                       # "retrieve" or "direct"
    retries: int                     # rewrite attempts so far (shared counter)
    generation_ok: bool              # grounded AND answers the question
    # `path` has a reducer: each node RETURNS ["its_name"] and LangGraph appends it,
    # which gives us the ordered list of nodes visited.
    path: Annotated[list[str], operator.add]


# ---------------------------------------------------------------------------
# Prompts (only {question}, {document}, {context}, {answer}, {previous} are
# template variables, so don't add other curly braces.)
# ---------------------------------------------------------------------------
ROUTE_PROMPT = (
    "You route questions for the internal assistant of Northwind Robotics, a "
    "robotics company. Answer YES if the question could be answered from internal "
    "company documents: HR policies (PTO, sick leave, parental leave, travel and "
    "expenses, benefits, referrals), IT help desk (passwords, laptops, VPN, "
    "accounts), or product specs and support (the Warehouse Rover R2). Answer NO "
    "for greetings, small talk, and general-knowledge questions unrelated to the "
    "company (geography, math, celebrities, news).\n\n"
    "Question: {question}\n\n"
    "Reply with exactly one word: YES or NO."
)

GRADE_DOC_PROMPT = (
    "You grade retrieved text for a question. Answer YES if the document contains "
    "information that helps answer the question, even partly. Answer NO if it is "
    "unrelated.\n\n"
    "Question: {question}\n\n"
    "Document:\n{document}\n\n"
    "Reply with exactly one word: YES or NO."
)

REWRITE_PROMPT = (
    "Rewrite the question as a clear, specific search query for a company "
    "knowledge base (HR policies, IT help desk, product specs). Spell out "
    "abbreviations, add likely synonyms and the full terms a document would use. "
    "Do NOT answer the question.\n\n"
    "Original question: {question}\n"
    "Previous query that found nothing useful: {previous}\n\n"
    "Reply with only the new query, on one line."
)

GENERATE_PROMPT = (
    "You are Northwind Robotics' internal assistant. Answer ONLY using the "
    "context below.\n\n"
    "Rules:\n"
    "1. Be complete but concise. Include the numbers, limits, deadlines, "
    "conditions and exceptions that the context gives for the question, but do "
    "not add unrelated details.\n"
    "2. If the answer is not in the context, reply only with: "
    "I don't know based on the provided documents. "
    "Do not list any sources in that case.\n"
    "3. Otherwise, end with one line in this format: Sources: followed by the "
    "names of the context files you used, separated by commas. Use the file names "
    "shown in square brackets in the context.\n\n"
    "Context:\n{context}\n\n"
    "Question: {question}"
)

GROUNDED_PROMPT = (
    "Is every factual claim in the answer supported by the context? Ignore the "
    "'Sources:' line. Answer YES if everything stated is supported, NO if the "
    "answer states anything that is not in the context.\n\n"
    "Context:\n{context}\n\n"
    "Answer:\n{answer}\n\n"
    "Reply with exactly one word: YES or NO."
)

ADDRESSES_PROMPT = (
    "Does the answer give a concrete answer to the question? Answer NO if it only "
    "says it does not know, or talks about something else.\n\n"
    "Question: {question}\n\n"
    "Answer:\n{answer}\n\n"
    "Reply with exactly one word: YES or NO."
)

SMALLTALK_PROMPT = (
    "Is this message a greeting, a thank-you, or a question about the assistant "
    "itself (who it is, what it can do)? Answer YES or NO.\n\n"
    "Message: {question}\n\n"
    "Reply with exactly one word: YES or NO."
)

SMALLTALK_REPLY = (
    "You are Northwind Robotics' internal assistant. You answer questions about HR "
    "policies, IT help and product specs using internal documents. Reply briefly "
    "and politely to this message: {question}"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ask(llm, prompt: str) -> str:
    """Call the model with a plain string and return clean text."""
    reply = llm.invoke(prompt).content
    return re.sub(r"<think>.*?</think>", "", str(reply), flags=re.S).strip()


def _yes_no(llm, prompt: str, default: bool) -> bool:
    """One-word grader. If the reply has neither YES nor NO, use `default`."""
    m = re.search(r"\b(YES|NO)\b", _ask(llm, prompt).upper())
    return default if m is None else m.group(1) == "YES"


def format_docs(docs) -> str:
    return "\n\n".join(
        f"[{Path(d.metadata.get('source', 'unknown')).name}] {d.page_content}"
        for d in docs
    )


def is_grounded(llm, context: str, answer: str) -> bool:
    return _yes_no(llm, GROUNDED_PROMPT.format(context=context, answer=answer), default=False)


def addresses_question(llm, question: str, answer: str) -> bool:
    return _yes_no(llm, ADDRESSES_PROMPT.format(question=question, answer=answer), default=False)


# ---------------------------------------------------------------------------
# 2 + 3. Nodes and edges
# ---------------------------------------------------------------------------
def build_graph(retriever, llm):
    # ---- nodes: each takes the state and returns a PARTIAL state update ----
    def route_question(state: GraphState):
        q = state["question"]
        # default=True: if the router is unsure, retrieving is the safe choice.
        company = _yes_no(llm, ROUTE_PROMPT.format(question=q), default=True)
        return {
            "route": "retrieve" if company else "direct",
            "rewritten_question": q,
            "retries": 0,
            "path": ["route_question"],
        }

    def retrieve(state: GraphState):
        docs = retriever.invoke(state["rewritten_question"])
        return {"documents": docs, "path": ["retrieve"]}

    def grade_documents(state: GraphState):
        kept = []
        for d in state["documents"]:
            # Grade against the ORIGINAL question so rewrites can't drift the goal.
            prompt = GRADE_DOC_PROMPT.format(question=state["question"], document=d.page_content)
            if _yes_no(llm, prompt, default=False):
                kept.append(d)
        return {"documents": kept, "path": ["grade_documents"]}

    def rewrite_query(state: GraphState):
        prompt = REWRITE_PROMPT.format(
            question=state["question"], previous=state["rewritten_question"]
        )
        lines = _ask(llm, prompt).splitlines()
        new_query = lines[0].strip().strip('"') if lines else ""
        return {
            "rewritten_question": new_query or state["question"],
            "retries": state["retries"] + 1,
            "path": ["rewrite_query"],
        }

    def generate(state: GraphState):
        prompt = GENERATE_PROMPT.format(
            context=format_docs(state["documents"]), question=state["question"]
        )
        return {"generation": _ask(llm, prompt), "path": ["generate"]}

    def grade_generation(state: GraphState):
        context = format_docs(state["documents"])
        ok = is_grounded(llm, context, state["generation"]) and addresses_question(
            llm, state["question"], state["generation"]
        )
        return {"generation_ok": ok, "path": ["grade_generation"]}

    def direct_answer(state: GraphState):
        q = state["question"]
        if _yes_no(llm, SMALLTALK_PROMPT.format(question=q), default=False):
            text = _ask(llm, SMALLTALK_REPLY.format(question=q))
        else:
            # Out-of-domain factual question: a fixed refusal, never an LLM answer,
            # so the model cannot "helpfully" answer "Paris".
            text = REFUSAL
        return {"generation": text, "path": ["direct_answer"]}

    def refuse(state: GraphState):
        return {"generation": REFUSAL, "path": ["refuse"]}

    # ---- conditional edges: plain functions that return a label --------------
    def after_route(state: GraphState) -> str:
        return state["route"]

    def after_grading(state: GraphState) -> str:
        if state["documents"]:
            return "generate"
        if state["retries"] < MAX_RETRIES:
            return "rewrite_query"
        return "refuse"

    def after_generation(state: GraphState) -> str:
        if state["generation_ok"]:
            return "end"
        if state["retries"] < MAX_RETRIES:
            return "rewrite_query"
        return "refuse"

    # ---- wire it up ---------------------------------------------------------
    g = StateGraph(GraphState)
    for fn in (route_question, retrieve, grade_documents, rewrite_query,
               generate, grade_generation, direct_answer, refuse):
        g.add_node(fn.__name__, fn)

    g.add_edge(START, "route_question")
    g.add_conditional_edges(
        "route_question", after_route,
        {"retrieve": "retrieve", "direct": "direct_answer"},
    )
    g.add_edge("retrieve", "grade_documents")
    g.add_conditional_edges(
        "grade_documents", after_grading,
        {"generate": "generate", "rewrite_query": "rewrite_query", "refuse": "refuse"},
    )
    g.add_edge("rewrite_query", "retrieve")
    g.add_edge("generate", "grade_generation")
    g.add_conditional_edges(
        "grade_generation", after_generation,
        {"end": END, "rewrite_query": "rewrite_query", "refuse": "refuse"},
    )
    g.add_edge("direct_answer", END)
    g.add_edge("refuse", END)
    return g.compile()


def ask(app, question: str) -> dict:
    """Run one question; the returned state includes the ordered node `path`."""
    return app.invoke(
        {"question": question, "path": []},
        config={"recursion_limit": 25},   # safety net on top of MAX_RETRIES
    )


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------
def _load_task6():
    """Task 6 is also called starter.py, so load it by explicit path."""
    path = Path(__file__).resolve().parents[1] / "task_06_advanced_retrieval" / "starter.py"
    spec = importlib.util.spec_from_file_location("task06_retrieval", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def demo_hallucination_check(llm):
    """Feed grade_generation's checks a FABRICATED answer and see if it is caught."""
    context = "[employee_handbook.md] Full-time employees accrue 1.67 days of PTO per month (20 days per year)."
    fake = "Full-time employees get 45 days of PTO per year, plus unlimited sick leave."
    print("\n=== Hallucination check on a fabricated answer ===")
    print("Fabricated:", fake)
    print("grounded?  ", is_grounded(llm, context, fake), "(expected False)")


def main():
    from common.utils import get_llm

    t6 = _load_task6()
    llm = get_llm()
    if len(sys.argv) > 1 and sys.argv[1] == "weak":
        retriever = t6.build_baseline_retriever(k=1)   # one chunk only: easier to miss
    else:
        retriever = t6.build_hybrid_retriever(k=4)
    app = build_graph(retriever, llm)

    # Diagram: print the Mermaid text, save it, and try a PNG (needs internet).
    mermaid = app.get_graph().draw_mermaid()
    out_dir = Path(__file__).resolve().parent
    (out_dir / "graph.mmd").write_text(mermaid, encoding="utf-8")
    print(mermaid)
    try:
        (out_dir / "graph.png").write_bytes(app.get_graph().draw_mermaid_png())
    except Exception as e:  # PNG rendering calls an online service
        print(f"(PNG skipped: {type(e).__name__}; paste graph.mmd into a Mermaid viewer)")

    questions = [
        "How much PTO do I get?",
        "hello, who are you?",
        "time off carry rules?",
        "what's the capital of France?",
        "What is the payload capacity of the Warehouse Rover R2?",
    ]
    for q in questions:
        final = ask(app, q)
        print("\n" + "=" * 70)
        print("Q:      ", q)
        print("Path:   ", " -> ".join(final["path"]))
        print("Retries:", final.get("retries", 0), "| rewritten:", final.get("rewritten_question"))
        print("Answer: ", final["generation"])

    demo_hallucination_check(llm)


if __name__ == "__main__":
    main()