"""
Task 5 — Conversational RAG with memory.

This is a LIGHTER skeleton than tasks 1-4. The retriever builder is given to you;
you design the history-aware retrieval + memory yourself. Read the README first.

Run with:  python task_05_conversational_rag/starter.py
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from common.utils import get_llm, get_embeddings, DATA_DIR


def build_base_retriever(k=4):
    """Provided for you — a plain vector retriever over the corpus."""
    from langchain_community.document_loaders import TextLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_community.vectorstores import FAISS

    docs = []
    for md in sorted(DATA_DIR.glob("*.md")):
        docs.extend(TextLoader(md, encoding="utf-8").load())
    chunks = RecursiveCharacterTextSplitter(
        chunk_size=800, chunk_overlap=100).split_documents(docs)
    store = FAISS.from_documents(chunks, get_embeddings())
    return store.as_retriever(search_kwargs={"k": k})


# ---------------------------------------------------------------------------
# YOUR WORK STARTS HERE.
#
# Implement a conversational RAG chain. Suggested API (feel free to change it):
#
#   conversational_rag = build_conversational_rag(retriever, llm)
#   conversational_rag.invoke(
#       {"input": "How much PTO do I get?"},
#       config={"configurable": {"session_id": "user-123"}},
#   )
#
# Requirements:
#   - follow-up questions must be contextualized against per-session history
#   - history must be isolated per session_id
#   - out-of-scope questions must still be refused
# ---------------------------------------------------------------------------

def build_conversational_rag(retriever, llm):
    from langchain_core.chat_history import InMemoryChatMessageHistory
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
    from langchain_core.runnables import RunnableLambda, RunnablePassthrough
    from langchain_core.runnables.history import RunnableWithMessageHistory

    # --- Step 1: rewrite follow-ups into standalone questions ---------------
    contextualize_prompt = ChatPromptTemplate.from_messages([
        ("system",
         "Given the chat history and the latest user question, rewrite the "
         "question so it can be understood WITHOUT the chat history. Replace "
         "pronouns like 'it' or 'that' with what they refer to. Do NOT answer "
         "the question. If it is already standalone, return it unchanged. "
         "Output only the question."),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ])
    contextualize_chain = contextualize_prompt | llm | StrOutputParser()

    def standalone_question(x):
        # First turn: no history, so skip the extra LLM call.
        if x.get("chat_history"):
            return contextualize_chain.invoke(x)
        return x["input"]

    def format_docs(docs):
        return "\n\n".join(
            f"[{Path(d.metadata.get('source', 'unknown')).name}] {d.page_content}"
            for d in docs
        )

    # --- Step 2: answer from retrieved context + conversation ---------------
    qa_prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are Northwind Robotics' internal assistant. Answer ONLY using the "
         "context below. Use the chat history only to understand the question, "
         "never as a source of facts. If the answer is not in the context, reply "
         "only with: 'I don't know based on the provided documents.' and do not "
         "list any sources. Otherwise, after your answer, list the source files "
         "you used.\n\nContext:\n{context}"),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ])

    rag_chain = (
        RunnablePassthrough.assign(standalone=RunnableLambda(standalone_question))
        .assign(docs=lambda x: retriever.invoke(x["standalone"]))
        .assign(context=lambda x: format_docs(x["docs"]))
        .assign(answer=qa_prompt | llm | StrOutputParser())
    )

    # --- Step 3: per-session memory -----------------------------------------
    sessions = {}

    def get_session_history(session_id: str):
        if session_id not in sessions:
            sessions[session_id] = InMemoryChatMessageHistory()
        return sessions[session_id]

    return RunnableWithMessageHistory(
        rag_chain,
        get_session_history,
        input_messages_key="input",
        history_messages_key="chat_history",
        output_messages_key="answer",
    )


if __name__ == "__main__":
    retriever = build_base_retriever()
    llm = get_llm()
    bot = build_conversational_rag(retriever, llm)

    session = {"configurable": {"session_id": "demo"}}
    turns = [
        "How much PTO do I get?",
        "Can I carry it over to next year?",   # <- must resolve "it" = PTO
    ]
    for t in turns:
        print(f"\nUser: {t}")
        result = bot.invoke({"input": t}, config=session)
        # create_retrieval_chain returns a dict with an "answer" key.
        print("Bot:", result["answer"] if isinstance(result, dict) else result)
