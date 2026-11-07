"""Agentic RAG graph (Task 8) with conversation memory (Task 5).

    condense -> route -+-> smalltalk ----------------------------+
                       |                                         |
                       +-> retrieve -> grade -+-> generate -> check -+-> finalize
                              ^               |        ^        |
                              |               |        +--------+ (regenerate once)
                              +--- rewrite <--+ (nothing relevant)
                                              +-> refuse ---------+

Prompts return plain text ("yes"/"no", "route: docs") and are parsed leniently,
because small local models are unreliable at strict JSON / structured output.
"""
from __future__ import annotations

import re
from typing import Annotated, TypedDict

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

import settings

IDK = "I don't know based on the available documents."
REFUSAL = (
    "I couldn't find a reliable answer to that in the Northwind internal documents, "
    "so I won't guess. Try rephrasing, or ask HR / IT directly."
)


class GraphState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]  # per-session memory
    question: str       # what the user typed
    standalone: str     # self-contained version (follow-ups resolved)
    search_query: str   # what we actually send to the retriever
    route: str          # docs | smalltalk
    category: str       # metadata filter chosen by the router (or "any")
    documents: list[Document]  # retrieved
    relevant: list[Document]   # survived grading
    rewrites: int
    attempts: int
    answer: str
    grounded: bool
    refused: bool
    sources: list[str]


# ------------------------------------------------------------------- prompts
def _chain(system: str, human: str, llm):
    prompt = ChatPromptTemplate.from_messages([("system", system), ("human", human)])
    return prompt | llm | StrOutputParser()


def clean(text: str) -> str:
    """Strip <think> blocks some local models emit, plus whitespace."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL)
    return text.replace("<think>", "").strip()


def _yes(text: str) -> bool:
    return clean(text).lower().lstrip("*\"' ").startswith("yes")


def _format_history(messages: list[BaseMessage]) -> str:
    lines = []
    for m in messages:
        role = "User" if m.type == "human" else "Assistant"
        lines.append(f"{role}: {m.content}")
    return "\n".join(lines)


def _format_context(docs: list[Document]) -> str:
    return "\n\n".join(
        f"[{i}] file: {d.metadata.get('source')} | section: {d.metadata.get('section')}\n{d.page_content}"
        for i, d in enumerate(docs, 1)
    )


def build_graph(llm, retriever, checkpointer=None):
    condense_chain = _chain(
        "Rewrite the user's latest message as ONE standalone question using the chat history "
        "to resolve pronouns and references. If it is already standalone, repeat it unchanged. "
        "Output only the question.",
        "Chat history:\n{history}\n\nLatest message: {question}\n\nStandalone question:",
        llm,
    )
    router_chain = _chain(
        "You route messages for a company-internal assistant that answers from the employee "
        "handbook and HR policies (PTO, leave, remote work, expenses, travel, reviews, benefits), "
        "the IT help-desk FAQ (passwords, VPN, laptops, software), and product specs for the "
        "company's robots.\n"
        "Reply with exactly two lines:\n"
        "route: docs | smalltalk      (smalltalk = greetings/thanks/chit-chat about the assistant itself; "
        "everything else, including off-topic questions, is docs)\n"
        "category: hr | it | product | any   (pick one only if the question clearly belongs to a "
        "single area; use any if unsure or it spans several)",
        "{question}",
        llm,
    )
    smalltalk_chain = _chain(
        "You are the Northwind Internal Docs Assistant. Reply to the message in one or two "
        "friendly sentences and mention you can answer questions about HR policies, IT "
        "procedures and product specs. Do not answer factual questions.",
        "{question}",
        llm,
    )
    grade_chain = _chain(
        "You grade retrieved passages. Answer 'yes' if the passage contains information that "
        "helps answer the question, even partially. Otherwise answer 'no'. Reply with one word.",
        "Question: {question}\n\nPassage:\n{context}\n\nRelevant (yes/no):",
        llm,
    )
    rewrite_chain = _chain(
        "Rewrite the question as a short keyword-style search query for a company document "
        "search. Use likely synonyms and the formal terms a policy document would use. "
        "Output only the query.",
        "Original question: {question}\nPrevious query that found nothing useful: {query}\n\nNew query:",
        llm,
    )
    generate_chain = _chain(
        "You answer employee questions using ONLY the numbered context passages.\n"
        "Rules:\n"
        "- Use only facts that are literally in the context. Do not add outside knowledge.\n"
        "- Be concise and include specific numbers/dates when present.\n"
        "- After each claim cite the file in square brackets, e.g. [hr_policies.md].\n"
        f"- If the context does not contain the answer, reply exactly: {IDK}\n"
        "{extra}",
        "Context:\n{context}\n\nQuestion: {question}\n\nAnswer:",
        llm,
    )
    hallucination_chain = _chain(
        "You check whether an answer is supported by the context. Answer 'yes' if every claim in "
        "the answer is stated in the context or follows directly from it by simple reasoning "
        "(for example, 'first month' is within 'first 90 days'). Answer 'no' only if the answer "
        "states a fact that is not in the context or contradicts it. Ignore citation formatting. ",
        "Reply with one word.",
        llm,
    )

    # --------------------------------------------------------------- nodes
    def condense(state: GraphState):
        question = state["question"]
        history = state["messages"][:-1]  # everything before the new user message
        if not history:
            return {"standalone": question, "search_query": question}
        out = clean(condense_chain.invoke({"history": _format_history(history[-6:]), "question": question}))
        out = out.splitlines()[0] if out else question
        return {"standalone": out or question, "search_query": out or question}

    def route(state: GraphState):
        raw = clean(router_chain.invoke({"question": state["standalone"]})).lower()
        m_route = re.search(r"route\s*:\s*(docs|smalltalk)", raw)
        m_cat = re.search(r"category\s*:\s*(hr|it|product|any)", raw)
        return {
            "route": m_route.group(1) if m_route else "docs",
            "category": m_cat.group(1) if m_cat else "any",
        }

    def smalltalk(state: GraphState):
        return {"answer": clean(smalltalk_chain.invoke({"question": state["question"]})), "sources": []}

    def retrieve(state: GraphState):
        docs = retriever.retrieve(
            state["search_query"], k=settings.RETRIEVE_K, category=state.get("category")
        )
        return {"documents": docs}

    def grade(state: GraphState):
        docs = state.get("documents", [])
        if not docs:
            return {"relevant": []}
        verdicts = grade_chain.batch(
            [{"question": state["standalone"], "context": d.page_content} for d in docs],
            config={"max_concurrency": settings.GRADE_CONCURRENCY},
        )
        return {"relevant": [d for d, v in zip(docs, verdicts) if _yes(v)]}

    def rewrite(state: GraphState):
        new_query = clean(
            rewrite_chain.invoke({"question": state["standalone"], "query": state["search_query"]})
        )
        new_query = new_query.splitlines()[0] if new_query else state["standalone"]
        # Drop the metadata filter too: a wrong router guess is a common cause of misses.
        return {"search_query": new_query, "rewrites": state.get("rewrites", 0) + 1, "category": "any"}

    def generate(state: GraphState):
        attempts = state.get("attempts", 0)
        extra = (
            "- IMPORTANT: a previous draft contained unsupported claims. Copy facts verbatim "
            "from the context and leave out anything you are unsure of.\n"
            if attempts
            else ""
        )
        answer = clean(
            generate_chain.invoke(
                {"context": _format_context(state["relevant"]), "question": state["standalone"], "extra": extra}
            )
        )
        return {"answer": answer, "attempts": attempts + 1}

    def check(state: GraphState):
        verdict = hallucination_chain.invoke(
            {"context": _format_context(state["relevant"]), "answer": state["answer"]}
        )
        return {"grounded": _yes(verdict)}

    def refuse(state: GraphState):
        return {"answer": REFUSAL, "refused": True, "sources": []}

    def finalize(state: GraphState):
        answer = state["answer"]
        sources: list[str] = []
        if not state.get("refused") and state.get("route") != "smalltalk":
            relevant = state.get("relevant", [])
            cited = {f.lower() for f in re.findall(r"\[([\w./\- ]+\.(?:md|txt))\]", answer)}
            pool = [d for d in relevant if d.metadata["source"].lower() in cited] or relevant
            for d in pool:
                label = f"{d.metadata['source']} › {d.metadata['section']}"
                if label not in sources:
                    sources.append(label)
        return {"messages": [AIMessage(content=answer)], "sources": sources}

    # --------------------------------------------------------------- edges
    def after_route(state: GraphState):
        return "smalltalk" if state["route"] == "smalltalk" else "retrieve"

    def after_grade(state: GraphState):
        if state["relevant"]:
            return "generate"
        return "rewrite" if state.get("rewrites", 0) < settings.MAX_REWRITES else "refuse"

    def after_generate(state: GraphState):
        return "refuse" if re.search(r"i don.t know based on", state["answer"], re.I) else "check"

    def after_check(state: GraphState):
        if state["grounded"]:
            return "finalize"
        return "generate" if state["attempts"] < settings.MAX_GENERATIONS else "refuse"

    g = StateGraph(GraphState)
    for name, fn in [
        ("condense", condense), ("route", route), ("smalltalk", smalltalk), ("retrieve", retrieve),
        ("grade", grade), ("rewrite", rewrite), ("generate", generate), ("check", check),
        ("refuse", refuse), ("finalize", finalize),
    ]:
        g.add_node(name, fn)

    g.add_edge(START, "condense")
    g.add_edge("condense", "route")
    g.add_conditional_edges("route", after_route, {"smalltalk": "smalltalk", "retrieve": "retrieve"})
    g.add_edge("retrieve", "grade")
    g.add_conditional_edges("grade", after_grade, {"generate": "generate", "rewrite": "rewrite", "refuse": "refuse"})
    g.add_edge("rewrite", "retrieve")
    g.add_conditional_edges("generate", after_generate, {"check": "check", "refuse": "refuse"})
    g.add_conditional_edges("check", after_check, {"finalize": "finalize", "generate": "generate", "refuse": "refuse"})
    g.add_edge("smalltalk", "finalize")
    g.add_edge("refuse", "finalize")
    g.add_edge("finalize", END)
    return g.compile(checkpointer=checkpointer)


MERMAID = """```mermaid
flowchart TD
    U[User question] --> C[condense<br/>resolve follow-ups using session memory]
    C --> R{route}
    R -- smalltalk --> S[smalltalk] --> F
    R -- docs + category --> RT[retrieve<br/>hybrid BM25 + MMR, metadata filter]
    RT --> G[grade passages]
    G -- some relevant --> GEN[generate with citations]
    G -- none, retries left --> RW[rewrite query, drop filter] --> RT
    G -- none, no retries --> X[refuse]
    GEN -- says 'I don't know' --> X
    GEN --> H{hallucination check}
    H -- grounded --> F[finalize: answer + sources]
    H -- not grounded, retries left --> GEN
    H -- not grounded --> X
    X --> F
```"""
