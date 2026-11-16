"""
Streamlit chat UI — a pure HTTP client of the API (Week 2, Task 3).

    make run          # the API, in one terminal
    make run-ui       # this UI, in another  (API_URL defaults to http://127.0.0.1:8000)

It imports no graph, index or model code: everything goes through POST /chat/stream,
GET/DELETE /session/{id}, POST /feedback and GET /readyz. The session id is kept in
the page URL (?session=...), so refreshing the page continues the same conversation:
the API remembers it, and the UI redraws it from GET /session/{id}.
"""

from __future__ import annotations

import json
import os
import uuid

import httpx
import streamlit as st

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000").rstrip("/")
TIMEOUT = httpx.Timeout(connect=5.0, read=180.0, write=10.0, pool=5.0)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
def api(method: str, path: str, **kwargs) -> httpx.Response:
    with httpx.Client(base_url=API_URL, timeout=TIMEOUT) as client:
        return client.request(method, path, **kwargs)


def error_text(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        return f"{body.get('error')}: {body.get('detail')} (request {body.get('request_id')})"
    except ValueError:
        return f"HTTP {resp.status_code}"


def sse_events(resp: httpx.Response):
    """Parse a text/event-stream response into (event, data-as-dict) pairs."""
    event, data = "message", []
    for line in resp.iter_lines():
        if not line:                                   # blank line = end of one event
            if data:
                yield event, json.loads("\n".join(data))
            event, data = "message", []
        elif line.startswith(":"):                     # comment / keep-alive ping
            continue
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" "))
    if data:
        yield event, json.loads("\n".join(data))


def send_feedback(trace_id: str, rating: int) -> None:
    try:
        resp = api("POST", "/feedback", json={"trace_id": trace_id, "rating": rating})
    except httpx.HTTPError as e:
        st.toast(f"Feedback not sent: {e}")
        return
    if resp.status_code == 200:
        st.session_state.rated[trace_id] = rating
        st.toast("Thanks, feedback recorded.")
    else:
        st.toast(f"Feedback not sent: {error_text(resp)}")


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Northwind Internal Assistant", page_icon="🤖")
st.title("🤖 Northwind Internal Docs Assistant")
st.caption("Ask about HR policies, IT procedures, and product specs.")

# The session id lives in the URL, so a page refresh keeps the conversation.
if "session" not in st.query_params:
    st.query_params["session"] = str(uuid.uuid4())
session_id = st.query_params["session"]

if st.session_state.get("session_id") != session_id:      # new browser session, or a refresh
    st.session_state.session_id = session_id
    st.session_state.messages = []
    st.session_state.rated = {}
    try:
        resp = api("GET", f"/session/{session_id}")
        if resp.status_code == 200:
            for turn in resp.json()["turns"]:
                st.session_state.messages += [{"role": "user", "content": turn["question"]},
                                              {"role": "assistant", "content": turn["answer"]}]
    except httpx.HTTPError:
        pass                                               # the sidebar reports the API status


def render_meta(msg: dict) -> None:
    if msg.get("sources"):
        st.caption("📎 Sources: " + " · ".join(msg["sources"]))
    if msg.get("node_path"):
        with st.expander("How this answer was produced"):
            st.code(" → ".join(msg["node_path"]))
            if msg.get("standalone") and msg["standalone"] != msg.get("question"):
                st.write(f"Understood as: *{msg['standalone']}*")
            if msg.get("retries"):
                st.write(f"Search was rephrased {msg['retries']}×.")
            st.caption(f"trace_id `{msg.get('trace_id')}` · {msg.get('elapsed_ms', 0) / 1000:.1f} s")
    trace_id = msg.get("trace_id")
    if trace_id:
        rated = st.session_state.rated.get(trace_id)
        if rated is not None:
            st.caption("Feedback: " + ("👍" if rated > 0 else "👎"))
        else:
            up, down, _ = st.columns([1, 1, 8])
            up.button("👍", key=f"up-{trace_id}", on_click=send_feedback, args=(trace_id, 1))
            down.button("👎", key=f"down-{trace_id}", on_click=send_feedback, args=(trace_id, -1))


with st.sidebar:
    st.write(f"Session: `{session_id[:8]}`")
    if st.button("🔄 Reset conversation"):
        try:
            api("DELETE", f"/session/{session_id}")
        except httpx.HTTPError:
            pass
        st.query_params["session"] = str(uuid.uuid4())
        st.rerun()
    st.divider()
    st.subheader("Service")
    try:
        ready = api("GET", "/readyz")
        if ready.status_code == 200:
            r = ready.json()
            st.caption(f"✅ ready · {r['chunks']} passages · {r['documents']} documents · {r['retriever']}")
            st.caption(f"index {r['index']} at startup · {r['active_sessions']} active sessions")
        else:
            st.warning(error_text(ready))
    except httpx.HTTPError as e:
        st.error(f"API unreachable at {API_URL}: {type(e).__name__}")
    st.caption(f"API: {API_URL}")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            render_meta(msg)

if prompt := st.chat_input("Ask a question about company policies…"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        msg = {"role": "assistant", "content": ""}
        status = st.status("Thinking…", expanded=True)
        answer_box = st.empty()
        draft = ""
        try:
            with httpx.Client(base_url=API_URL, timeout=TIMEOUT) as client:
                with client.stream("POST", "/chat/stream",
                                   json={"question": prompt, "session_id": session_id}) as resp:
                    if resp.status_code != 200:
                        resp.read()
                        raise RuntimeError(error_text(resp))
                    for event, data in sse_events(resp):
                        if event == "status":
                            status.write(data["label"])
                        elif event == "token":
                            draft += data["text"]
                            answer_box.markdown(draft + "▌")
                        elif event == "retract":
                            draft = ""
                            answer_box.empty()
                            status.write("↻ " + data["reason"])
                        elif event == "done":
                            msg.update(content=data["answer"], sources=data["sources"],
                                       node_path=data["node_path"], retries=data["retries"],
                                       standalone=data["standalone_question"], question=prompt,
                                       trace_id=data["trace_id"], elapsed_ms=data["elapsed_ms"])
                        elif event == "error":
                            raise RuntimeError(f"{data['error']}: {data['detail']} "
                                               f"(request {data['request_id']})")
            if not msg["content"]:
                raise RuntimeError("the stream ended without an answer")
            status.update(label="Done", state="complete", expanded=False)
            answer_box.markdown(msg["content"])      # the fact-checked answer replaces the draft
            render_meta(msg)
        except (httpx.HTTPError, RuntimeError) as e:
            status.update(label="Failed", state="error", expanded=False)
            msg = {"role": "assistant", "content": f"⚠️ Something went wrong: {e}"}
            answer_box.error(msg["content"])
    st.session_state.messages.append(msg)
