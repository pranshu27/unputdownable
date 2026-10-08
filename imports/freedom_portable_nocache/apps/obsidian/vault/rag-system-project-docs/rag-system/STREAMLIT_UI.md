# Streamlit UI for RAG System

This project now includes a Streamlit UI so you can learn the RAG behavior interactively.

File:
- streamlit_chat_ui.py

The UI connects to existing API endpoints:
- GET /health
- GET /agent/context
- POST /chat/sessions
- GET /chat/sessions/{session_id}
- PUT /chat/sessions/{session_id}/summary
- DELETE /chat/sessions/{session_id}/summary
- GET /chat/sessions/{session_id}/messages
- POST /chat/sessions/{session_id}/messages

## Why this helps learning

- You can see the full chat response and the answer metadata side-by-side.
- You can toggle retrieval and generation controls (mode, rerank, graph, relevancy boost) and observe behavior changes.
- You can inspect session memory summary and test follow-up behavior.
- You can inspect evidence list and retrieval plan telemetry.

## Setup

From rag-system root:

1) Install UI dependency:

```powershell
pip install -e .[ui]
```

2) Start the API (example):

```powershell
$env:PYTHONPATH = "src"
python -m uvicorn rag_system.api.app:app --host 0.0.0.0 --port 8000 --reload
```

3) Connect KB if needed:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/connect?background=false" -Method POST
```

4) Run Streamlit:

```powershell
streamlit run streamlit_chat_ui.py
```

Open the browser URL printed by Streamlit (usually http://localhost:8501).

## Concrete usage examples

Example A: capability discovery
- Click Load /agent/context
- Observe indexed snapshot summary and context inventory JSON.

Example B: SQL override retrieval
- Mode: bm25
- Query: Find SQL override in wf_4202_fnd_rltinteraction.XML
- Inspect Answer debug to compare evidence hits and retrieval plan.

Example C: usage query guardrail
- Mode: hybrid
- Query: Where is BeginInteractionGroup_Id used?
- Verify answer mentions the entity and includes chunk_id citations.

Example D: compare orchestration
- Ask same query twice:
  - once with Use Graph Orchestration enabled
  - once disabled
- Compare answer_strategy, llm_error, and retrieval_plan.

## Notes

- If API is unreachable, use Health in the sidebar to verify connectivity.
- If chat returns KB-not-built errors, run /connect first.
- The UI stores current chat session id in Streamlit session state.
