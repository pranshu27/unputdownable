from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

import streamlit as st


def _api_call(
    method: str,
    url: str,
    payload: Optional[Dict[str, Any]] = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url=url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            if not raw.strip():
                return {}
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {"raw": parsed}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error: {exc}") from exc


def _ensure_session(base_url: str) -> str:
    session_id = st.session_state.get("session_id")
    if session_id:
        return session_id

    created = _api_call("POST", f"{base_url}/chat/sessions")
    sid = str(created.get("session_id") or "")
    if not sid:
        raise RuntimeError("Failed to create chat session")

    st.session_state["session_id"] = sid
    return sid


def _load_transcript(base_url: str, session_id: str) -> Dict[str, Any]:
    return _api_call("GET", f"{base_url}/chat/sessions/{session_id}/messages")


def _load_session_meta(base_url: str, session_id: str) -> Dict[str, Any]:
    return _api_call("GET", f"{base_url}/chat/sessions/{session_id}")


def _send_message(base_url: str, session_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    return _api_call("POST", f"{base_url}/chat/sessions/{session_id}/messages", payload=body, timeout=180)


def _update_summary(base_url: str, session_id: str, summary: str) -> Dict[str, Any]:
    return _api_call(
        "PUT",
        f"{base_url}/chat/sessions/{session_id}/summary",
        payload={"summary": summary},
    )


def _clear_summary(base_url: str, session_id: str) -> Dict[str, Any]:
    return _api_call("DELETE", f"{base_url}/chat/sessions/{session_id}/summary")


def _health(base_url: str) -> Dict[str, Any]:
    return _api_call("GET", f"{base_url}/health")


def _agent_context(base_url: str, query: str) -> Dict[str, Any]:
    q = urllib.parse.quote(query)
    return _api_call("GET", f"{base_url}/agent/context?query={q}")


def _render_answer_debug(answer: Dict[str, Any]) -> None:
    st.caption("Answer metadata")
    top = {
        "orchestration_mode": answer.get("orchestration_mode"),
        "answer_strategy": answer.get("answer_strategy"),
        "mode": answer.get("mode"),
        "llm_used": answer.get("llm_used"),
        "llm_model": answer.get("llm_model"),
        "llm_error": answer.get("llm_error"),
        "refused": answer.get("refused"),
        "reason": answer.get("reason"),
        "relevancy_boost_applied": answer.get("relevancy_boost_applied"),
    }
    st.json(top)

    evidence = answer.get("evidence") or []
    if evidence:
        table_rows = []
        for hit in evidence:
            table_rows.append(
                {
                    "chunk_id": hit.get("chunk_id"),
                    "source_file": hit.get("source_file"),
                    "node_class": hit.get("node_class"),
                    "name": hit.get("name"),
                    "score": hit.get("score"),
                }
            )
        st.caption("Evidence hits")
        st.dataframe(table_rows, use_container_width=True, hide_index=True)

    plan = answer.get("retrieval_plan") or {}
    if plan:
        st.caption("Retrieval plan")
        st.json(plan)


def main() -> None:
    st.set_page_config(page_title="RAG Streamlit Chat", page_icon="R", layout="wide")
    st.title("RAG Streamlit Chat UI")
    st.write("Interactive UI over /chat APIs so you can learn retrieval, evidence, and answer behavior.")

    default_base_url = st.session_state.get("base_url", "http://127.0.0.1:8000")

    with st.sidebar:
        st.header("Connection")
        base_url = st.text_input("API Base URL", value=default_base_url)
        st.session_state["base_url"] = base_url.rstrip("/")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Health", use_container_width=True):
                try:
                    status = _health(st.session_state["base_url"])
                    st.success("API reachable")
                    st.json(status)
                except Exception as exc:
                    st.error(str(exc))
        with col2:
            if st.button("New Session", use_container_width=True):
                st.session_state.pop("session_id", None)
                st.rerun()

        st.divider()
        st.header("Answer Controls")
        mode = st.selectbox("Mode", options=["hybrid", "vector", "bm25", "auto"], index=0)
        k = st.slider("Top K", min_value=1, max_value=20, value=6)
        rerank = st.toggle("Rerank", value=False)
        llm = st.toggle("Use LLM", value=True)
        use_graph = st.toggle("Use Graph Orchestration", value=True)
        relevancy_boost = st.toggle("Relevancy Boost", value=True)
        history_turns = st.slider("History Turns", min_value=0, max_value=12, value=4)
        llm_temperature = st.slider("LLM Temperature", min_value=0.0, max_value=1.5, value=0.0, step=0.1)
        llm_max_tokens = st.slider("LLM Max Tokens", min_value=64, max_value=4000, value=900, step=32)
        prompt_name = st.selectbox("Prompt", options=["answer_with_citations", "lineage_summary"], index=0)

    try:
        session_id = _ensure_session(st.session_state["base_url"])
    except Exception as exc:
        st.error(f"Cannot create/load session: {exc}")
        st.stop()

    st.caption(f"Session: {session_id}")

    col_left, col_right = st.columns([2.2, 1.0])

    with col_right:
        st.subheader("Session Memory")
        try:
            meta = _load_session_meta(st.session_state["base_url"], session_id)
            current_summary = str(meta.get("summary") or "")
        except Exception as exc:
            current_summary = ""
            st.error(f"Cannot load summary: {exc}")

        summary_text = st.text_area("Summary", value=current_summary, height=200)
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Save Summary", use_container_width=True):
                try:
                    _update_summary(st.session_state["base_url"], session_id, summary_text)
                    st.success("Summary saved")
                except Exception as exc:
                    st.error(str(exc))
        with col_b:
            if st.button("Clear Summary", use_container_width=True):
                try:
                    _clear_summary(st.session_state["base_url"], session_id)
                    st.success("Summary cleared")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

        st.divider()
        st.subheader("Capability Snapshot")
        if st.button("Load /agent/context", use_container_width=True):
            try:
                payload = _agent_context(st.session_state["base_url"], "what can you do and what xmls are indexed")
                st.markdown(str(payload.get("answer_text") or ""))
                with st.expander("Context inventory"):
                    st.json(payload.get("context_inventory") or {})
            except Exception as exc:
                st.error(str(exc))

    with col_left:
        st.subheader("Chat")

        try:
            transcript = _load_transcript(st.session_state["base_url"], session_id)
            messages = transcript.get("messages") or []
        except Exception as exc:
            messages = []
            st.error(f"Cannot load transcript: {exc}")

        for msg in messages:
            role = str(msg.get("role") or "assistant")
            with st.chat_message("assistant" if role != "user" else "user"):
                st.markdown(str(msg.get("text") or ""))
                meta = msg.get("meta") or {}
                if meta and role == "assistant":
                    with st.expander("Message metadata"):
                        st.json(meta)

        user_prompt = st.chat_input("Ask a question about indexed Informatica workflows")
        if user_prompt:
            with st.chat_message("user"):
                st.markdown(user_prompt)

            body = {
                "message": user_prompt,
                "k": int(k),
                "mode": str(mode),
                "rerank": bool(rerank),
                "prompt_name": str(prompt_name),
                "llm": bool(llm),
                "relevancy_boost": bool(relevancy_boost),
                "llm_temperature": float(llm_temperature),
                "llm_max_tokens": int(llm_max_tokens),
                "use_graph": bool(use_graph),
                "history_turns": int(history_turns),
            }

            with st.spinner("Generating answer..."):
                try:
                    result = _send_message(st.session_state["base_url"], session_id, body)
                except Exception as exc:
                    with st.chat_message("assistant"):
                        st.error(str(exc))
                    st.stop()

            answer = result.get("answer") or {}
            assistant_text = str((result.get("assistant_message") or {}).get("text") or answer.get("answer_text") or "")
            with st.chat_message("assistant"):
                st.markdown(assistant_text)
                with st.expander("Answer debug"):
                    _render_answer_debug(answer)

            st.rerun()


if __name__ == "__main__":
    main()
