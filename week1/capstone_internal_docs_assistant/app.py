"""
Capstone — Northwind Internal Docs Assistant (Streamlit UI).

Run from the week-1 repo root:
    streamlit run capstone_internal_docs_assistant/app.py
"""
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # flat imports: settings, backend, ...

import streamlit as st

import settings
from backend import RagBackend


# TODO A (done): build the backend ONCE per server process, not per message.
@st.cache_resource(show_spinner="Loading models and index…")
def get_backend() -> RagBackend:
    return RagBackend()


# TODO B (done): non-streaming entry point, kept for tests/scripts. The UI below
# uses backend.stream() so the user sees each agent step as it happens.
def answer_question(backend: RagBackend, question: str, session_id: str) -> dict:
    return backend.invoke(question, session_id)


def word_stream(text: str, delay: float = 0.015):
    for word in text.split(" "):
        yield word + " "
        time.sleep(delay)


st.set_page_config(page_title="Northwind Internal Assistant", page_icon="🤖")
st.title("🤖 Northwind Internal Docs Assistant")
st.caption("Ask about HR policies, IT procedures, and product specs.")

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []
if "feedback_sent" not in st.session_state:
    st.session_state.feedback_sent = set()
if "upload_key" not in st.session_state:
    st.session_state.upload_key = 0

backend = get_backend()

with st.sidebar:
    st.write(f"Session: `{st.session_state.session_id[:8]}`")
    if st.button("🔄 Reset conversation"):
        backend.reset_session(st.session_state.session_id)
        st.session_state.messages = []
        st.session_state.feedback_sent = set()
        st.session_state.session_id = str(uuid.uuid4())
        st.rerun()

    stats = backend.stats()
    st.divider()
    st.caption(
        f"Index: {stats['files']} files / {stats['chunks']} chunks  \n"
        f"Retriever: `{stats['retriever']}`  \n"
        f"LangSmith tracing: {'🟢 on' if settings.tracing_enabled() else '⚪ off'}"
    )

    st.divider()
    st.subheader("Add a document")
    uploaded = st.file_uploader("Markdown or text", type=["md", "txt"], key=f"up_{st.session_state.upload_key}")
    if uploaded and st.button("Add to index"):
        with st.spinner("Indexing…"):
            report = backend.add_document(uploaded.name, uploaded.getvalue().decode("utf-8"))
        st.session_state.upload_key += 1
        st.toast(f"Indexed {uploaded.name} (added={report['added']}, updated={report['updated']})")
        st.rerun()

# ---------------------------------------------------------------- chat history
for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sources"):
            st.caption("📎 Sources: " + " · ".join(msg["sources"]))
        if msg["role"] == "assistant" and msg.get("run_id") and not msg.get("refused_smalltalk"):
            vote = st.feedback("thumbs", key=f"fb_{i}")
            if vote is not None and i not in st.session_state.feedback_sent:
                st.session_state.feedback_sent.add(i)
                ok = backend.feedback(msg["run_id"], score=int(vote))
                st.toast("Thanks for the feedback!" + ("" if ok else " (not logged: LangSmith tracing is off)"))

# ------------------------------------------------------------------- new input
if prompt := st.chat_input("Ask a question about company policies…"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        final = None
        with st.status("Thinking…", expanded=True) as status:
            for event in backend.stream(prompt, st.session_state.session_id):
                if event["type"] == "step":
                    st.write(event["text"])
                else:
                    final = event
            status.update(label="Done", state="complete", expanded=False)

        # The answer is streamed only after the hallucination check has passed,
        # so users never see a draft that later gets retracted.
        st.write_stream(word_stream(final["answer"]))
        if final["sources"]:
            st.caption("📎 Sources: " + " · ".join(final["sources"]))

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": final["answer"],
            "sources": final["sources"],
            "run_id": final["run_id"],
            "refused_smalltalk": final["route"] == "smalltalk",
        }
    )
    st.rerun()  # re-render so the new message gets its 👍/👎 buttons
