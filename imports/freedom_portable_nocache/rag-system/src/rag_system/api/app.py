"""FastAPI application â€” Informatica RAG retrieval service.

Endpoints
---------
GET  /health            liveness + chunk count
POST /ingest            (re)build the knowledge base from the configured XML folder
GET  /retrieve          semantic search: ?q=...&k=5&node_class=SOURCE

The knowledge base is held in process. On first startup it is NOT pre-built â€”
call POST /ingest or set AUTO_INGEST=true in the environment to build on startup.

Example
-------
    uvicorn rag_system.api.app:app --reload --port 8080

    curl "http://localhost:8080/retrieve?q=SQL+override+RLTInteraction&k=3"
    curl -X POST "http://localhost:8080/ingest"
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import threading
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List, Optional
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_API_DIR = Path(__file__).resolve().parent
_CHAT_UI_FILE = _API_DIR / "static" / "chat_ui.html"
load_dotenv(dotenv_path=_PROJECT_ROOT / ".env")
logger = logging.getLogger("rag_system.api")

# Lazy import so the module loads without heavy deps for tests
from rag_system.knowledge_base import InformaticaKnowledgeBase

@asynccontextmanager
async def _lifespan(app: FastAPI):
    try:
        _chat_db_init()
    except Exception as exc:
        logger.warning("Chat persistence init failed; continuing in memory: %s", exc)

    if os.getenv("AUTO_CONNECT", "").lower() in ("1", "true", "yes"):
        logger.info("AUTO_CONNECT=true â€” connecting to existing vector store")
        threading.Thread(target=_run_connect, daemon=True).start()
    elif os.getenv("AUTO_INGEST", "").lower() in ("1", "true", "yes"):
        folder = os.getenv("INFA_XML_FOLDER", "")
        if folder and os.path.isdir(folder):
            logger.info("AUTO_INGEST=true â€” starting background ingest from %s", folder)
            threading.Thread(target=_run_ingest, args=(folder,), daemon=True).start()
    yield


app = FastAPI(
    title="Informatica RAG Service",
    version="0.1.0",
    description="Semantic retrieval over Informatica PowerCenter XML exports.",
    lifespan=_lifespan,
)

# Shared state
_kb: Optional[InformaticaKnowledgeBase] = None
_ingest_lock = threading.Lock()
_ingest_status: Dict[str, Any] = {
    "state": "idle",
    "chunks": 0,
    "error": None,
    "lineage_coverage": {"available": False, "workflow_count": 0, "totals": {}, "workflows": []},
}
_VALID_MODES = {"hybrid", "vector", "bm25"}
_VALID_NODE_CLASSES = {"SOURCE", "TRANSFORMATION", "TARGET", "LINEAGE"}
_VALID_INTENTS = {"sql_override", "impact", "lineage", "usage", "logic", "generic"}
_INTENT_CACHE_LOCK = threading.Lock()
_INTENT_CACHE: Dict[str, str] = {}
_INTENT_CACHE_MAX = int(os.getenv("INTENT_CACHE_MAX", "1024") or 1024)

_chat_lock = threading.Lock()
_chat_sessions: Dict[str, Dict[str, Any]] = {}
_CHAT_MAX_TURNS = int(os.getenv("CHAT_MAX_TURNS", "40") or 40)
_CHAT_SUMMARY_MAX_CHARS = int(os.getenv("CHAT_SUMMARY_MAX_CHARS", "1800") or 1800)
_CHAT_PERSIST_ENABLED = os.getenv("CHAT_PERSIST_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
_CHAT_SQLITE_PATH = Path(
    os.getenv("CHAT_SQLITE_PATH", str(_PROJECT_ROOT / "chat_sessions.sqlite3"))
).resolve()


class ChatMessageRequest(BaseModel):
    """Request payload for one chat turn against the /chat message endpoint."""

    message: str = Field(..., min_length=1, description="User chat message")
    k: int = Field(default=6, ge=1, le=20)
    mode: str = Field(default="hybrid", pattern="^(hybrid|vector|bm25|auto)$")
    rerank: bool = False
    prompt_name: str = "answer_with_citations"
    llm: bool = True
    relevancy_boost: bool = True
    llm_model: Optional[str] = None
    llm_temperature: float = Field(default=0.0, ge=0.0, le=1.5)
    llm_max_tokens: int = Field(default=900, ge=64, le=4000)
    use_graph: Optional[bool] = None
    graph_max_retries: Optional[int] = Field(default=None, ge=0, le=5)
    history_turns: int = Field(default=4, ge=0, le=12)


class ChatSummaryUpdateRequest(BaseModel):
    """Request payload for manually updating persisted chat summary memory."""

    summary: str = Field(default="", max_length=12000, description="Manual session memory summary")


def _chat_db_conn() -> sqlite3.Connection:
    _CHAT_SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_CHAT_SQLITE_PATH), timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def _chat_db_init() -> None:
    if not _CHAT_PERSIST_ENABLED:
        return
    with _chat_db_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_sessions (
                session_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                message_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                text TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                meta_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(session_id) REFERENCES chat_sessions(session_id)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chat_messages_session_ts
            ON chat_messages(session_id, timestamp)
            """
        )
        conn.commit()


def _persist_create_session(session: Dict[str, Any]) -> None:
    if not _CHAT_PERSIST_ENABLED:
        return
    with _chat_db_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO chat_sessions(session_id, created_at, updated_at, summary)
            VALUES(?, ?, ?, ?)
            """,
            (
                session["session_id"],
                session["created_at"],
                session["updated_at"],
                session.get("summary") or "",
            ),
        )
        conn.commit()


def _persist_append_message(session_id: str, message: Dict[str, Any], updated_at: str) -> None:
    if not _CHAT_PERSIST_ENABLED:
        return
    with _chat_db_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO chat_messages(message_id, session_id, role, text, timestamp, meta_json)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                message["message_id"],
                session_id,
                message["role"],
                message["text"],
                message["timestamp"],
                json.dumps(message.get("meta") or {}),
            ),
        )
        conn.execute(
            "UPDATE chat_sessions SET updated_at=? WHERE session_id=?",
            (updated_at, session_id),
        )
        conn.commit()


def _persist_update_summary(session_id: str, summary: str, updated_at: str) -> None:
    if not _CHAT_PERSIST_ENABLED:
        return
    with _chat_db_conn() as conn:
        conn.execute(
            "UPDATE chat_sessions SET summary=?, updated_at=? WHERE session_id=?",
            (summary, updated_at, session_id),
        )
        conn.commit()


def _load_chat_session_from_db(session_id: str) -> Optional[Dict[str, Any]]:
    if not _CHAT_PERSIST_ENABLED:
        return None
    with _chat_db_conn() as conn:
        row = conn.execute(
            "SELECT session_id, created_at, updated_at, summary FROM chat_sessions WHERE session_id=?",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        msg_rows = conn.execute(
            """
            SELECT message_id, role, text, timestamp, meta_json
            FROM chat_messages
            WHERE session_id=?
            ORDER BY timestamp ASC
            """,
            (session_id,),
        ).fetchall()

    messages: List[Dict[str, Any]] = []
    for m in msg_rows:
        try:
            meta = json.loads(m["meta_json"] or "{}")
            if not isinstance(meta, dict):
                meta = {}
        except Exception:
            meta = {}
        messages.append(
            {
                "message_id": m["message_id"],
                "role": m["role"],
                "text": m["text"],
                "timestamp": m["timestamp"],
                "meta": meta,
            }
        )

    return {
        "session_id": row["session_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "summary": row["summary"] or "",
        "messages": messages,
    }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _elapsed_ms(started_at: float) -> int:
    return max(0, int(round((perf_counter() - started_at) * 1000)))


def _new_trace_payload(
    *,
    endpoint: str,
    query: str = "",
    intent: str = "",
    workflow_hint: str = "",
    orchestration_mode: str = "",
) -> Dict[str, Any]:
    trace: Dict[str, Any] = {
        "request_id": str(uuid4()),
        "endpoint": endpoint,
        "timestamp_utc": _utc_now_iso(),
    }
    if query:
        trace["query"] = query
    if intent:
        trace["intent"] = intent
    if workflow_hint:
        trace["workflow_hint"] = workflow_hint
    if orchestration_mode:
        trace["orchestration_mode"] = orchestration_mode
    return trace


def _answer_usage_telemetry(payload: Dict[str, Any]) -> Dict[str, Any]:
    llm_requested = bool(payload.get("llm_requested"))
    llm_used = bool(payload.get("llm_used"))
    unavailable_reason = "provider_usage_not_available"
    if not llm_requested:
        unavailable_reason = "llm_not_requested"
    elif not llm_used:
        unavailable_reason = "llm_not_used"

    return {
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "estimated_cost_usd": None,
        "unavailable_reason": unavailable_reason,
    }


def _answer_event_log(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    if payload.get("orchestration_mode") == "semantic_primary":
        events.append(
            {
                "stage": "semantic_query",
                "status": "ok" if not payload.get("refused") else "refused",
                "reason": payload.get("reason"),
            }
        )
    else:
        events.append(
            {
                "stage": "retrieval",
                "status": "ok" if payload.get("evidence") else "empty",
                "mode": payload.get("mode"),
            }
        )

    events.append(
        {
            "stage": "rerank",
            "status": (
                "ok"
                if payload.get("reranked")
                else ("error" if payload.get("rerank_error") else "skipped")
            ),
            "error": payload.get("rerank_error"),
        }
    )

    events.append(
        {
            "stage": "generation",
            "status": (
                "ok"
                if payload.get("llm_used")
                else ("skipped" if not payload.get("llm_requested") else "fallback")
            ),
            "model": payload.get("llm_model"),
            "error": payload.get("llm_error"),
        }
    )

    if payload.get("refused"):
        events.append(
            {
                "stage": "refusal",
                "status": "emitted",
                "reason": payload.get("reason"),
            }
        )

    return events


def _create_chat_session() -> Dict[str, Any]:
    session_id = str(uuid4())
    session = {
        "session_id": session_id,
        "created_at": _utc_now_iso(),
        "updated_at": _utc_now_iso(),
        "messages": [],
        "summary": "",
    }
    with _chat_lock:
        _chat_sessions[session_id] = session
    _persist_create_session(session)
    return session


def _get_chat_session(session_id: str) -> Dict[str, Any]:
    with _chat_lock:
        session = _chat_sessions.get(session_id)
        if not session:
            loaded = _load_chat_session_from_db(session_id)
            if loaded:
                _chat_sessions[session_id] = loaded
                session = loaded
    if not session:
        raise HTTPException(status_code=404, detail=f"Chat session not found: {session_id}")
    return session


def _set_chat_session_summary(session_id: str, summary: str) -> Dict[str, Any]:
    sanitized = " ".join(str(summary or "").split()).strip()
    if len(sanitized) > _CHAT_SUMMARY_MAX_CHARS:
        sanitized = sanitized[-_CHAT_SUMMARY_MAX_CHARS:]

    with _chat_lock:
        session = _chat_sessions.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Chat session not found: {session_id}")
        session["summary"] = sanitized
        session["updated_at"] = _utc_now_iso()
        _persist_update_summary(session_id=session_id, summary=session["summary"], updated_at=session["updated_at"])
        return {
            "session_id": session["session_id"],
            "created_at": session["created_at"],
            "updated_at": session["updated_at"],
            "summary": session.get("summary") or "",
            "message_count": len(session.get("messages") or []),
        }


def _append_chat_message(session_id: str, role: str, text: str, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    message = {
        "message_id": str(uuid4()),
        "role": role,
        "text": (text or "").strip(),
        "timestamp": _utc_now_iso(),
        "meta": meta or {},
    }
    with _chat_lock:
        session = _chat_sessions.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Chat session not found: {session_id}")
        session["messages"].append(message)
        # Keep rolling window by user turns (2 messages per turn typically)
        max_messages = max(2, _CHAT_MAX_TURNS * 2)
        removed: List[Dict[str, Any]] = []
        if len(session["messages"]) > max_messages:
            removed = session["messages"][:-max_messages]
            session["messages"] = session["messages"][-max_messages:]
            if removed:
                existing_summary = str(session.get("summary") or "")
                condensed = _compress_messages_to_summary(removed)
                merged = _merge_session_summary(existing_summary, condensed)
                session["summary"] = merged
        session["updated_at"] = _utc_now_iso()
        _persist_append_message(session_id=session_id, message=message, updated_at=session["updated_at"])
        if removed:
            _persist_update_summary(session_id=session_id, summary=session.get("summary") or "", updated_at=session["updated_at"])
    return message


def _compress_messages_to_summary(messages: List[Dict[str, Any]]) -> str:
    if not messages:
        return ""

    lines: List[str] = []
    for m in messages:
        role = str(m.get("role") or "").strip().lower()
        text = " ".join(str(m.get("text") or "").split()).strip()
        if not text:
            continue
        if role == "user":
            lines.append(f"User asked: {text[:220]}")
        elif role == "assistant":
            lines.append(f"Assistant answered: {text[:260]}")

    if not lines:
        return ""

    merged = "\n".join(lines)
    if len(merged) <= _CHAT_SUMMARY_MAX_CHARS:
        return merged
    return merged[-_CHAT_SUMMARY_MAX_CHARS:]


def _merge_session_summary(existing_summary: str, new_summary: str) -> str:
    existing = (existing_summary or "").strip()
    new = (new_summary or "").strip()
    if not existing:
        merged = new
    elif not new:
        merged = existing
    else:
        merged = existing + "\n" + new

    if len(merged) <= _CHAT_SUMMARY_MAX_CHARS:
        return merged
    return merged[-_CHAT_SUMMARY_MAX_CHARS:]


_FOLLOWUP_HINT_RE = re.compile(
    r"\b(it|that|this|those|these|same|above|previous|earlier|also|then|there|its|their|them)\b",
    re.IGNORECASE,
)


def _is_followup_like(message: str) -> bool:
    text = (message or "").strip()
    if len(text) <= 45:
        return True
    if _FOLLOWUP_HINT_RE.search(text):
        return True
    return False


def _compose_chat_query(message: str, session: Dict[str, Any], history_turns: int) -> tuple[str, List[Dict[str, Any]]]:
    session_summary = " ".join(str(session.get("summary") or "").split()).strip()

    if history_turns <= 0:
        if session_summary and _is_followup_like(message):
            contextual = (
                "Follow-up question with compressed session memory.\n"
                f"Memory: {session_summary}\n"
                f"Follow-up: {message}"
            )
            return contextual, []
        return message, []

    prior = list(session.get("messages") or [])
    if not prior:
        return message, []

    # Pull recent messages before the new user turn is appended.
    context_messages = prior[-history_turns * 2 :]
    if not context_messages:
        return message, []

    if not _is_followup_like(message):
        return message, context_messages

    snippets: List[str] = []
    for m in context_messages:
        role = str(m.get("role") or "").strip().lower()
        text = str(m.get("text") or "").strip()
        if not text:
            continue
        if role == "user":
            snippets.append(f"User: {text}")
        elif role == "assistant":
            compact = " ".join(text.split())
            snippets.append(f"Assistant: {compact[:320]}")

    if not snippets:
        return message, context_messages

    prefix = "Follow-up question with chat context. Resolve references using context first.\n"
    if session_summary:
        prefix += f"Compressed memory: {session_summary}\n"

    contextual_query = prefix + "\n".join(snippets) + f"\nFollow-up: {message}"
    return contextual_query, context_messages


def _chat_tool_subflow_overrides(
    user_message: str,
    mode: str,
    rerank: bool,
    k: int,
    prompt_name: str,
    llm_model: Optional[str] = None,
) -> Dict[str, Any]:
    intent = _infer_query_intent(user_message, llm_model_override=llm_model)
    resolved_mode = mode
    resolved_rerank = rerank
    resolved_k = k
    resolved_prompt = prompt_name
    subflow = "default"

    if intent == "sql_override":
        subflow = "sql_override"
        if mode in {"auto", "hybrid"}:
            resolved_mode = "bm25"
        resolved_rerank = False
        resolved_k = max(k, 6)
    elif intent == "lineage":
        subflow = "lineage"
        if mode == "auto":
            resolved_mode = "hybrid"
        resolved_rerank = True
        resolved_k = max(k, 8)
    elif intent == "usage":
        subflow = "usage"
        if mode == "auto":
            resolved_mode = "hybrid"
        resolved_rerank = True
        resolved_k = max(k, 8)
        resolved_prompt = "lineage_summary" if prompt_name == "answer_with_citations" else prompt_name
    elif intent == "impact":
        subflow = "impact"
        if mode == "auto":
            resolved_mode = "hybrid"
        resolved_rerank = False
        resolved_k = max(k, 6)
        resolved_prompt = "lineage_summary" if prompt_name == "answer_with_citations" else prompt_name

    return {
        "intent": intent,
        "subflow": subflow,
        "mode": resolved_mode,
        "rerank": resolved_rerank,
        "k": resolved_k,
        "prompt_name": resolved_prompt,
    }


def _get_xml_folder() -> str:
    folder = os.getenv("INFA_XML_FOLDER", "")
    if not folder:
        raise HTTPException(
            status_code=500,
            detail="INFA_XML_FOLDER env variable is not set.",
        )
    if not os.path.isdir(folder):
        raise HTTPException(
            status_code=500,
            detail=f"INFA_XML_FOLDER does not exist or is not a directory: {folder}",
        )
    return folder


def _run_connect() -> None:
    """Wire to an existing vector store (pgvector) without re-parsing XMLs."""
    global _kb, _ingest_status
    _ingest_status = {
        "state": "connecting",
        "chunks": 0,
        "error": None,
        "lineage_coverage": {"available": False, "workflow_count": 0, "totals": {}, "workflows": []},
    }
    try:
        kb = InformaticaKnowledgeBase()
        store = kb._make_store()
        kb._semantic_store = kb._make_semantic_store()
        count = store.count() if hasattr(store, "count") else 0
        kb._store = store
        kb._built = True
        _kb = kb
        _ingest_status = {
            "state": "connected",
            "chunks": count,
            "error": None,
            "lineage_coverage": _kb_lineage_coverage_payload(include_fields=False, max_files=12),
        }
        logger.info("Connected to vector store: %d chunks available", count)
    except Exception as exc:
        _ingest_status = {
            "state": "error",
            "chunks": 0,
            "error": str(exc),
            "lineage_coverage": {"available": False, "workflow_count": 0, "totals": {}, "workflows": []},
        }
        logger.error("Connect failed: %s", exc)


def _run_ingest(folder: str) -> None:
    global _kb, _ingest_status
    _ingest_status = {
        "state": "running",
        "chunks": 0,
        "error": None,
        "lineage_coverage": {"available": False, "workflow_count": 0, "totals": {}, "workflows": []},
    }
    try:
        kb = InformaticaKnowledgeBase()
        kb.build_from_folder(folder)
        _kb = kb
        _ingest_status = {
            "state": "done",
            "chunks": kb.count(),
            "error": None,
            "lineage_coverage": _kb_lineage_coverage_payload(include_fields=False, max_files=12),
        }
        logger.info("Ingest complete: %d chunks indexed", kb.count())
    except Exception as exc:
        _ingest_status = {
            "state": "error",
            "chunks": 0,
            "error": str(exc),
            "lineage_coverage": {"available": False, "workflow_count": 0, "totals": {}, "workflows": []},
        }
        logger.error("Ingest failed: %s", exc)


def _kb_lineage_coverage_payload(*, include_fields: bool, max_files: int) -> Dict[str, Any]:
    if _kb is None or not _kb._built:
        return {"available": False, "workflow_count": 0, "totals": {}, "workflows": []}
    if not hasattr(_kb, "lineage_coverage_snapshot"):
        return {"available": False, "workflow_count": 0, "totals": {}, "workflows": []}
    try:
        return _kb.lineage_coverage_snapshot(include_fields=include_fields, max_files=max_files)
    except Exception as exc:
        logger.warning("Failed to load lineage coverage snapshot: %s", exc)
        return {"available": False, "workflow_count": 0, "totals": {}, "workflows": []}


def _kb_semantic_layer_payload(*, max_workflows: int) -> Dict[str, Any]:
    if _kb is None or not _kb._built:
        return {"available": False, "workflow_count": 0, "workflows": []}
    if not hasattr(_kb, "semantic_layer_snapshot"):
        return {"available": False, "workflow_count": 0, "workflows": []}
    try:
        return _kb.semantic_layer_snapshot(max_workflows=max_workflows)
    except Exception as exc:
        logger.warning("Failed to load semantic layer snapshot: %s", exc)
        return {"available": False, "workflow_count": 0, "workflows": []}


def _kb_lineage_graph_payload() -> Dict[str, Any]:
    if _kb is None or not _kb._built:
        return {"available": False, "engine": "networkx", "source": "none"}
    if not hasattr(_kb, "lineage_graph_snapshot"):
        return {"available": False, "engine": "networkx", "source": "none"}
    try:
        return _kb.lineage_graph_snapshot()
    except Exception as exc:
        logger.warning("Failed to load lineage graph snapshot: %s", exc)
        return {"available": False, "engine": "networkx", "source": "error"}



@app.get("/health", summary="Liveness + KB state")
def health() -> Dict[str, Any]:
    try:
        from rag_system.prompts import list_prompts
        prompt_versions = list_prompts()
    except Exception:
        prompt_versions = {}
    return {
        "status": "ok",
        "kb_built": _kb is not None and _kb._built,
        "chunk_count": _kb.count() if _kb and _kb._built else 0,
        "ingest": _ingest_status,
        "lineage_coverage": _kb_lineage_coverage_payload(include_fields=False, max_files=20),
        "semantic_layer": _kb_semantic_layer_payload(max_workflows=20),
        "lineage_graph": _kb_lineage_graph_payload(),
        "prompt_versions": prompt_versions,
    }


@app.get("/lineage/coverage", summary="Lineage coverage telemetry by workflow")
def lineage_coverage(
    include_fields: bool = Query(False, description="Include resolved/unresolved target field names"),
    max_files: int = Query(25, ge=1, le=200, description="Max workflows to return"),
) -> Dict[str, Any]:
    request_started_at = perf_counter()
    if _kb is None or not _kb._built:
        raise HTTPException(
            status_code=503,
            detail="Knowledge base not built yet. POST /ingest or POST /connect first.",
        )
    payload = _kb_lineage_coverage_payload(include_fields=include_fields, max_files=max_files)
    trace = _new_trace_payload(
        endpoint="/lineage/coverage",
        orchestration_mode="semantic_snapshot",
    )
    return {
        "kb_built": True,
        "lineage_coverage": payload,
        "trace": trace,
        "telemetry": {
            "timing_ms": {
                "total_ms": _elapsed_ms(request_started_at),
            },
            "events": [
                {"stage": "lineage_coverage_snapshot", "status": "ok"},
            ],
        },
    }


@app.get("/semantic/model", summary="Semantic model snapshot by workflow")
def semantic_model_snapshot(
    max_workflows: int = Query(25, ge=1, le=200, description="Max workflows to return"),
) -> Dict[str, Any]:
    request_started_at = perf_counter()
    if _kb is None or not _kb._built:
        raise HTTPException(
            status_code=503,
            detail="Knowledge base not built yet. POST /ingest or POST /connect first.",
        )
    trace = _new_trace_payload(
        endpoint="/semantic/model",
        orchestration_mode="semantic_snapshot",
    )
    return {
        "kb_built": True,
        "semantic_layer": _kb_semantic_layer_payload(max_workflows=max_workflows),
        "lineage_graph": _kb_lineage_graph_payload(),
        "trace": trace,
        "telemetry": {
            "timing_ms": {
                "total_ms": _elapsed_ms(request_started_at),
                "semantic_ms": _elapsed_ms(request_started_at),
            },
            "events": [
                {"stage": "semantic_model_snapshot", "status": "ok"},
            ],
        },
    }


@app.get("/semantic/lineage", summary="Deterministic lineage query from semantic layer")
def semantic_lineage(
    workflow: str = Query(..., description="Workflow XML filename, e.g., wf_4202_fnd_rltinteraction.XML"),
    field: str = Query(..., description="Exact field token, e.g., InteractionEvent_Id"),
    limit: int = Query(20, ge=1, le=200, description="Max lineage paths to return"),
) -> Dict[str, Any]:
    request_started_at = perf_counter()
    if _kb is None or not _kb._built:
        raise HTTPException(
            status_code=503,
            detail="Knowledge base not built yet. POST /ingest or POST /connect first.",
        )
    if not hasattr(_kb, "query_semantic_lineage"):
        raise HTTPException(status_code=500, detail="Semantic query engine is not available")

    semantic_started_at = perf_counter()
    result = _kb.query_semantic_lineage(workflow_hint=workflow, field_name=field, limit=limit)
    semantic_ms = _elapsed_ms(semantic_started_at)
    trace = _new_trace_payload(
        endpoint="/semantic/lineage",
        query=field,
        intent="lineage",
        workflow_hint=workflow,
        orchestration_mode="semantic_primary",
    )
    return {
        "query": {"workflow": workflow, "field": field, "limit": limit},
        "result": result,
        "trace": trace,
        "telemetry": {
            "timing_ms": {
                "total_ms": _elapsed_ms(request_started_at),
                "semantic_ms": semantic_ms,
            },
            "events": [
                {"stage": "semantic_query", "status": result.get("status", "unknown")},
            ],
        },
    }


@app.get("/semantic/impact", summary="Deterministic impact query from semantic layer")
def semantic_impact(
    workflow: str = Query(..., description="Workflow XML filename, e.g., wf_4202_fnd_rltinteraction.XML"),
    field: str = Query(..., description="Exact field token, e.g., InteractionEvent_Id"),
    limit: int = Query(25, ge=1, le=200, description="Max supporting paths to return"),
) -> Dict[str, Any]:
    request_started_at = perf_counter()
    if _kb is None or not _kb._built:
        raise HTTPException(
            status_code=503,
            detail="Knowledge base not built yet. POST /ingest or POST /connect first.",
        )
    if not hasattr(_kb, "query_semantic_impact"):
        raise HTTPException(status_code=500, detail="Semantic query engine is not available")

    semantic_started_at = perf_counter()
    result = _kb.query_semantic_impact(workflow_hint=workflow, field_name=field, limit=limit)
    semantic_ms = _elapsed_ms(semantic_started_at)
    trace = _new_trace_payload(
        endpoint="/semantic/impact",
        query=field,
        intent="impact",
        workflow_hint=workflow,
        orchestration_mode="semantic_primary",
    )
    return {
        "query": {"workflow": workflow, "field": field, "limit": limit},
        "result": result,
        "trace": trace,
        "telemetry": {
            "timing_ms": {
                "total_ms": _elapsed_ms(request_started_at),
                "semantic_ms": semantic_ms,
            },
            "events": [
                {"stage": "semantic_query", "status": result.get("status", "unknown")},
            ],
        },
    }


@app.post("/connect", summary="Wire to existing vector store without re-parsing XMLs")
def connect(background: bool = Query(True, description="Run in background thread")) -> Dict[str, Any]:
    """Connect to an already-populated pgvector store.
    Use when the server restarted but pgvector already has indexed data."""
    if background:
        t = threading.Thread(target=_run_connect, daemon=True)
        t.start()
        return {"status": "connecting", "detail": "Check /health in a moment"}

    _run_connect()
    if _ingest_status.get("state") == "error":
        raise HTTPException(status_code=500, detail=_ingest_status.get("error") or "Connect failed")
    return {
        "status": "connected",
        "chunks": int(_ingest_status.get("chunks") or 0),
    }


@app.post("/ingest", summary="(Re)build the knowledge base from INFA_XML_FOLDER")
def ingest(background: bool = Query(True, description="Run in background thread")) -> Dict[str, Any]:
    """Trigger ingestion. Set background=false to block until complete (useful for tests)."""
    folder = _get_xml_folder()

    if not _ingest_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Ingest already running.")

    if background:
        t = threading.Thread(target=_do_ingest_locked, args=(folder,), daemon=True)
        t.start()
        return {"status": "started", "folder": folder}
    else:
        # blocking: _do_ingest_locked releases the lock in its own finally
        _do_ingest_locked(folder)
        return {"status": "done", "chunks": _kb.count() if _kb else 0}


def _do_ingest_locked(folder: str) -> None:
    """Run ingest and always release the lock (works for both background and blocking)."""
    try:
        _run_ingest(folder)
    finally:
        try:
            _ingest_lock.release()
        except RuntimeError:
            pass


def _try_rerank(query: str, hits: List[Dict[str, Any]], top_k: int) -> tuple[List[Dict[str, Any]], bool, Optional[str]]:
    """Attempt reranking and fall back to retrieval-only hits on failure."""
    if not hits:
        return [], False, None
    try:
        from rag_system.reranking.cross_encoder import rerank as do_rerank
        return do_rerank(query, hits, top_k=top_k), True, None
    except Exception as exc:
        logger.warning("Rerank unavailable; using retrieval-only hits: %s", exc)
        return hits[:top_k], False, str(exc)


def _generate_answer_openai(
    prompt: str,
    model_override: Optional[str],
    temperature: float,
    max_tokens: int,
) -> tuple[Optional[str], bool, Optional[str], Optional[str]]:
    """Generate final answer text with OpenAI chat completion.

    Returns tuple: (answer_text, llm_used, model_name, llm_error)
    """
    cfg = _resolve_llm_runtime(model_override)
    model_name = cfg["model_name"]

    if not cfg["api_key"]:
        return None, False, model_name, "Neither OPENAI_API_KEY nor AZURE_OPENAI_API_KEY is configured"
    if cfg["provider"] == "azure" and not cfg["azure_endpoint"]:
        return None, False, model_name, "AZURE_OPENAI_API_BASE (or AZURE_OPENAI_ENDPOINT) is not configured"
    if not model_name:
        return None, False, None, "No chat model/deployment configured (OPENAI_MODEL or AZURE_OPENAI_CHAT_DEPLOYMENT)"

    try:
        client = _make_openai_client(cfg)
        messages = [
            {
                "role": "system",
                "content": "You are a precise data engineering assistant. Use only provided evidence and cite chunk ids like [chunk_id].",
            },
            {"role": "user", "content": prompt},
        ]

        model_lower = (model_name or "").strip().lower()
        compact_model = model_lower.replace("-", "").replace("_", "")
        is_reasoning_style = (
            compact_model.startswith("gpt5")
            or model_lower.startswith("o1")
            or model_lower.startswith("o2")
            or model_lower.startswith("o3")
            or model_lower.startswith("o4")
            or model_lower.startswith("o5")
            or model_lower == "codex-mini"
        )

        # Empty content can happen intermittently with reasoning deployments.
        # Retry with larger completion budgets before giving up.
        raw_retry_count = os.getenv("LLM_EMPTY_RESPONSE_RETRIES", "2").strip()
        try:
            retry_count = max(0, min(int(raw_retry_count), 4))
        except ValueError:
            retry_count = 2

        token_budgets: List[int] = [max_tokens]
        while len(token_budgets) <= retry_count:
            next_budget = min(max(int(token_budgets[-1] * 1.6), token_budgets[-1] + 256), 4000)
            if next_budget == token_budgets[-1]:
                break
            token_budgets.append(next_budget)

        last_error: Optional[str] = None
        for attempt_idx, token_budget in enumerate(token_budgets, start=1):
            request_kwargs: Dict[str, Any] = {
                "model": model_name,
                "messages": messages,
            }
            if is_reasoning_style:
                request_kwargs["max_completion_tokens"] = token_budget
                request_kwargs["temperature"] = 1.0
            else:
                request_kwargs["max_tokens"] = token_budget
                request_kwargs["temperature"] = temperature

            try:
                resp = client.chat.completions.create(**request_kwargs)
                text = ""
                if resp.choices:
                    text = resp.choices[0].message.content or ""
                if text.strip():
                    return text.strip(), True, model_name, None

                last_error = (
                    f"OpenAI returned an empty response "
                    f"(attempt {attempt_idx}/{len(token_budgets)}, budget={token_budget})"
                )
                logger.warning(last_error)
            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "OpenAI generation failed on attempt %d/%d (budget=%d): %s",
                    attempt_idx,
                    len(token_budgets),
                    token_budget,
                    exc,
                )

        if not last_error:
            last_error = "OpenAI returned an empty response after retries"
        return None, False, model_name, last_error
    except Exception as exc:
        logger.warning("OpenAI generation failed: %s", exc)
        return None, False, model_name, str(exc)


def _resolve_llm_runtime(model_override: Optional[str]) -> Dict[str, Any]:
    # Re-load .env at call time so updated local credentials/endpoints are picked
    # up without requiring a process restart during iterative eval runs.
    load_dotenv(dotenv_path=_PROJECT_ROOT / ".env", override=True)

    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    azure_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()

    azure_endpoint = (
        os.getenv("AZURE_OPENAI_API_BASE", "").strip()
        or os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    ).rstrip("/")
    azure_api_version = os.getenv("AZURE_API_VERSION", "2024-12-01-preview").strip()

    provider = "openai"
    api_key = openai_key
    # Prefer Azure when Azure credentials + endpoint are configured. This avoids
    # accidental fallback to a globally-set OPENAI_API_KEY during local Azure runs.
    if azure_key and azure_endpoint:
        provider = "azure"
        api_key = azure_key

    model_name = (
        (model_override or "").strip()
        or os.getenv("OPENAI_MODEL", "").strip()
        or os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "").strip()
        or os.getenv("AZURE_CHAT_DEPLOYMENT", "").strip()
    )

    if not model_name:
        # Safe defaults by provider; Azure commonly has gpt-4o deployment while gpt-4o-mini may not exist.
        model_name = "gpt-4o" if provider == "azure" else "gpt-4o-mini"

    return {
        "provider": provider,
        "api_key": api_key,
        "model_name": model_name,
        "azure_endpoint": azure_endpoint,
        "azure_api_version": azure_api_version,
    }


def _make_openai_client(cfg: Dict[str, Any]):
    from openai import AzureOpenAI, OpenAI

    if cfg["provider"] == "azure":
        return AzureOpenAI(
            api_key=cfg["api_key"],
            api_version=cfg["azure_api_version"],
            azure_endpoint=cfg["azure_endpoint"],
        )
    return OpenAI(api_key=cfg["api_key"])


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _safe_score(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _compact_text(text: str, max_chars: int = 260) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 3].rstrip() + "..."


_WF_XML_RE = re.compile(r"(wf_[a-z0-9_]+\.xml)", re.IGNORECASE)


def _extract_source_file_hints(query: str) -> List[str]:
    hints: List[str] = []
    seen: set[str] = set()
    for match in _WF_XML_RE.findall(query or ""):
        normalized = match.strip().lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            hints.append(normalized)
    return hints


def _prefer_source_file_hits(
    hits: List[Dict[str, Any]],
    source_file_hints: List[str],
    *,
    strict: bool = False,
) -> List[Dict[str, Any]]:
    if not hits or not source_file_hints:
        return hits

    hint_set = {h.lower() for h in source_file_hints}
    scoped = [h for h in hits if str(h.get("source_file") or "").lower() in hint_set]
    if scoped:
        return scoped
    return [] if strict else hits


def _compose_evidence_blocks(evidence: List[Dict[str, Any]], max_items: int, max_chars: int) -> str:
    lines: List[str] = []
    for idx, item in enumerate(evidence[:max_items], 1):
        cid = item.get("chunk_id") or f"chunk_{idx}"
        src = item.get("source_file") or "unknown"
        nc = item.get("node_class") or ""
        name = item.get("name") or ""
        score = _safe_score(item.get("score"))
        text = _compact_text(str(item.get("cited_text") or ""), max_chars=max_chars)
        lines.append(
            f"[{cid}]\nSource: {src}  |  {nc}: {name}  |  score={score:.4f}\n{text}\n"
        )
    return "\n---\n".join(lines)


_CITATION_RE = re.compile(r"\[[^\[\]]+\]")
_USAGE_ENTITY_RE = re.compile(r"where\s+is\s+(.+?)\s+used\??", re.IGNORECASE)
_LINEAGE_FIELD_TOKEN_RE = re.compile(r"\b([A-Za-z][A-Za-z0-9_]*_[A-Za-z0-9_]+)\b")
_QUERY_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how", "in", "is", "it",
    "of", "on", "or", "that", "the", "this", "to", "was", "what", "where", "which", "with",
    "find", "exists", "logic", "records", "used",
}


def _query_keywords(query: str, max_terms: int = 10) -> List[str]:
    tokens = re.findall(r"[A-Za-z0-9_\.]+", query or "")
    out: List[str] = []
    seen: set[str] = set()
    for token in tokens:
        t = token.strip().lower()
        if not t or t in seen:
            continue
        if len(t) < 3 and not t.endswith(".xml"):
            continue
        if t in _QUERY_STOPWORDS and not t.startswith("wf_"):
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= max_terms:
            break
    return out


def _extract_lineage_anchor_terms(query: str, max_terms: int = 6) -> List[str]:
    """Extract likely field/entity anchors for lineage intent (e.g., InteractionEvent_Id)."""
    query_text = query or ""
    out: List[str] = []
    seen: set[str] = set()

    usage_entity = _extract_usage_entity(query_text).strip().lower()
    if usage_entity:
        seen.add(usage_entity)
        out.append(usage_entity)

    for token in _LINEAGE_FIELD_TOKEN_RE.findall(query_text):
        t = token.strip().lower()
        if not t or t in seen:
            continue
        if t.startswith("wf_") or t.endswith(".xml"):
            continue
        if t in _QUERY_STOPWORDS:
            continue
        # Prioritize technical identifiers that typically represent ports/fields.
        if "_" not in t:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= max_terms:
            break

    return out


def _hit_mentions_anchor_terms(hit: Dict[str, Any], anchor_terms: List[str]) -> bool:
    if not anchor_terms:
        return False
    text = " ".join(
        [
            str(hit.get("source_file") or ""),
            str(hit.get("node_class") or ""),
            str(hit.get("name") or ""),
            str(hit.get("text") or hit.get("cited_text") or ""),
        ]
    ).lower()
    return any(term in text for term in anchor_terms)


def _infer_query_intent_heuristic(query: str) -> str:
    q = (query or "").lower()
    if "sql override" in q or "sql qualifier" in q or "qualify" in q:
        return "sql_override"
    if (
        "impact" in q
        or "downstream" in q
        or "upstream dependency" in q
        or "what breaks" in q
        or "affected by" in q
        or "depends on" in q
    ):
        return "impact"
    if (
        "lineage" in q
        or "trace" in q
        or "source to target" in q
        or "where does" in q
        or "come from" in q
        or "comes from" in q
        or "across workflow" in q
        or "across workflows" in q
        or "upstream" in q
        or "downstream" in q
    ):
        return "lineage"
    if "where is" in q and "used" in q:
        return "usage"
    if "what logic" in q or "logic exists" in q:
        return "logic"
    return "generic"


def _infer_query_intent_with_openai(
    query: str,
    model_override: Optional[str],
    heuristic_intent: str,
) -> str:
    cfg = _resolve_llm_runtime(model_override)
    model_name = cfg["model_name"]

    if not cfg["api_key"]:
        return heuristic_intent
    if cfg["provider"] == "azure" and not cfg["azure_endpoint"]:
        return heuristic_intent

    try:
        client = _make_openai_client(cfg)
        messages = [
            {
                "role": "system",
                "content": (
                    "Classify user intent for an Informatica RAG assistant. "
                    "Return only JSON with keys: intent, reasoning. "
                    "intent must be one of: sql_override, impact, lineage, usage, logic, generic. "
                    "Use sql_override when user asks SQL override/source qualifier/QUALIFY logic."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Query:\n"
                    f"{query}\n\n"
                    f"Heuristic fallback intent: {heuristic_intent}"
                ),
            },
        ]

        model_lower = (model_name or "").strip().lower()
        compact_model = model_lower.replace("-", "").replace("_", "")
        is_reasoning_style = (
            compact_model.startswith("gpt5")
            or model_lower.startswith("o1")
            or model_lower.startswith("o2")
            or model_lower.startswith("o3")
            or model_lower.startswith("o4")
            or model_lower.startswith("o5")
            or model_lower == "codex-mini"
        )

        request_kwargs: Dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        if is_reasoning_style:
            request_kwargs["max_completion_tokens"] = int(
                os.getenv("INTENT_MAX_COMPLETION_TOKENS", "500") or 500
            )
            request_kwargs["temperature"] = 1.0
        else:
            request_kwargs["max_tokens"] = 200
            request_kwargs["temperature"] = 0.0

        resp = client.chat.completions.create(**request_kwargs)
        raw = resp.choices[0].message.content if resp.choices else ""
        payload = _extract_json_object(raw)
        raw_intent = str(payload.get("intent") or "").strip().lower()
        if raw_intent in _VALID_INTENTS:
            return raw_intent
        return heuristic_intent
    except Exception as exc:
        logger.warning("Intent LLM classification failed, using heuristic fallback: %s", exc)
        return heuristic_intent


def _infer_query_intent(query: str, llm_model_override: Optional[str] = None) -> str:
    heuristic_intent = _infer_query_intent_heuristic(query)
    if heuristic_intent == "sql_override":
        return heuristic_intent

    router_mode = os.getenv("INTENT_ROUTER", "llm").strip().lower()
    if router_mode in {"heuristic", "rules", "rule"}:
        return heuristic_intent

    cache_key = f"{router_mode}|{llm_model_override or ''}|{(query or '').strip().lower()}"
    with _INTENT_CACHE_LOCK:
        cached = _INTENT_CACHE.get(cache_key)
    if cached in _VALID_INTENTS:
        return cached

    resolved = _infer_query_intent_with_openai(
        query=query,
        model_override=llm_model_override,
        heuristic_intent=heuristic_intent,
    )
    if resolved not in _VALID_INTENTS:
        resolved = heuristic_intent

    with _INTENT_CACHE_LOCK:
        if len(_INTENT_CACHE) >= _INTENT_CACHE_MAX:
            _INTENT_CACHE.clear()
        _INTENT_CACHE[cache_key] = resolved
    return resolved


_CAPABILITY_PROMPT_RE = re.compile(
    r"\b(what\s+can\s+you\s+do|what\s+do\s+you\s+know|what\s+information\s+do\s+you\s+have|what\s+is\s+indexed|what\s+xmls?\s+(do\s+you\s+have|are\s+indexed)|your\s+capabilities|your\s+context)\b",
    re.IGNORECASE,
)


def _is_capability_inventory_prompt(query: str) -> bool:
    q = (query or "").strip().lower()
    if not q:
        return False
    if _CAPABILITY_PROMPT_RE.search(q):
        return True

    normalized = re.sub(r"[^a-z0-9\s]", " ", q)
    tokens = [t for t in normalized.split() if t]
    token_set = set(tokens)

    asks_what = "what" in token_set or "which" in token_set or "tell" in token_set
    refers_to_bot = any(t in token_set for t in {"you", "it", "bot", "agent", "chatbot"})
    asks_capability = "can" in token_set and "do" in token_set
    asks_knowledge = "know" in token_set or "information" in token_set
    asks_index = any(t in token_set for t in {"indexed", "index", "xml", "xmls", "files", "coverage"})

    if asks_what and refers_to_bot and asks_capability:
        return True
    if asks_what and refers_to_bot and asks_knowledge:
        return True
    if asks_what and refers_to_bot and (asks_index or "capabilities" in token_set or "context" in token_set):
        return True

    return False


def _top_counter_items(counter: Counter[str], limit: int = 8) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for key, count in counter.most_common(limit):
        if not key:
            continue
        out.append({"name": key, "count": int(count)})
    return out


def _kb_inventory_snapshot(max_items: int = 8) -> Dict[str, Any]:
    lineage_coverage = _kb_lineage_coverage_payload(include_fields=False, max_files=max_items)
    semantic_layer = _kb_semantic_layer_payload(max_workflows=max_items)
    if _kb is None or not _kb._built:
        return {
            "kb_available": False,
            "total_chunks": 0,
            "distinct_source_files": 0,
            "node_class_counts": {},
            "top_source_files": [],
            "top_mappings": [],
            "top_folders": [],
            "lineage_coverage": lineage_coverage,
            "semantic_layer": semantic_layer,
            "inventory_source": "none",
        }

    # Rich in-process inventory when chunks are loaded (ingest path).
    if getattr(_kb, "chunks", None):
        file_counts: Counter[str] = Counter()
        node_counts: Counter[str] = Counter()
        mapping_counts: Counter[str] = Counter()
        folder_counts: Counter[str] = Counter()

        for chunk in _kb.chunks:
            file_counts[str(chunk.source_file or "")] += 1
            node_counts[str(chunk.node_class or "UNKNOWN")] += 1
            meta = chunk.metadata or {}
            mapping = str(meta.get("mapping") or "").strip()
            folder = str(meta.get("folder") or "").strip()
            if mapping:
                mapping_counts[mapping] += 1
            if folder:
                folder_counts[folder] += 1

        return {
            "kb_available": True,
            "total_chunks": int(len(_kb.chunks)),
            "distinct_source_files": int(len(file_counts)),
            "node_class_counts": {k: int(v) for k, v in node_counts.items()},
            "top_source_files": _top_counter_items(file_counts, limit=max_items),
            "top_mappings": _top_counter_items(mapping_counts, limit=max_items),
            "top_folders": _top_counter_items(folder_counts, limit=max_items),
            "lineage_coverage": lineage_coverage,
            "semantic_layer": semantic_layer,
            "inventory_source": "in_memory_chunks",
        }

    # Connected pgvector path: aggregate directly from DB table.
    try:
        from rag_system.store.vector_store import PgVectorStore

        store = getattr(_kb, "_store", None)
        if isinstance(store, PgVectorStore):
            total = int(store.count())
            file_rows = store._execute(
                f"SELECT source_file, COUNT(*)::int AS c FROM {store.table} "
                "GROUP BY source_file ORDER BY c DESC LIMIT %s",
                (max_items,),
            ).fetchall()
            node_rows = store._execute(
                f"SELECT node_class, COUNT(*)::int AS c FROM {store.table} "
                "GROUP BY node_class ORDER BY c DESC"
            ).fetchall()
            mapping_rows = store._execute(
                f"SELECT metadata->>'mapping' AS mapping, COUNT(*)::int AS c FROM {store.table} "
                "WHERE COALESCE(metadata->>'mapping','') <> '' "
                "GROUP BY mapping ORDER BY c DESC LIMIT %s",
                (max_items,),
            ).fetchall()
            folder_rows = store._execute(
                f"SELECT metadata->>'folder' AS folder, COUNT(*)::int AS c FROM {store.table} "
                "WHERE COALESCE(metadata->>'folder','') <> '' "
                "GROUP BY folder ORDER BY c DESC LIMIT %s",
                (max_items,),
            ).fetchall()
            distinct_files = store._execute(
                f"SELECT COUNT(DISTINCT source_file)::int FROM {store.table}"
            ).fetchone()[0]

            return {
                "kb_available": True,
                "total_chunks": total,
                "distinct_source_files": int(distinct_files or 0),
                "node_class_counts": {str(r[0] or "UNKNOWN"): int(r[1] or 0) for r in node_rows},
                "top_source_files": [{"name": str(r[0] or ""), "count": int(r[1] or 0)} for r in file_rows if r[0]],
                "top_mappings": [{"name": str(r[0] or ""), "count": int(r[1] or 0)} for r in mapping_rows if r[0]],
                "top_folders": [{"name": str(r[0] or ""), "count": int(r[1] or 0)} for r in folder_rows if r[0]],
                "lineage_coverage": lineage_coverage,
                "semantic_layer": semantic_layer,
                "inventory_source": "pgvector_aggregates",
            }
    except Exception as exc:
        logger.warning("KB inventory snapshot failed: %s", exc)

    return {
        "kb_available": True,
        "total_chunks": int(_kb.count()) if _kb else 0,
        "distinct_source_files": 0,
        "node_class_counts": {},
        "top_source_files": [],
        "top_mappings": [],
        "top_folders": [],
        "lineage_coverage": lineage_coverage,
        "semantic_layer": semantic_layer,
        "inventory_source": "count_only",
    }


def _render_context_agent_answer(snapshot: Dict[str, Any]) -> str:
    capabilities = [
        "Deterministic semantic lineage and impact queries (workflow + field scoped)",
        "Grounded Q&A with citations to chunk ids [chunk_id]",
        "Source-to-target lineage tracing and usage lookups",
        "SQL override and transformation logic discovery",
        "Follow-up question handling with chat memory compression",
        "Session memory controls (inspect/edit/clear summary)",
    ]

    lines: List[str] = ["## What I Can Do"]
    for item in capabilities:
        lines.append(f"- {item}")

    lines.append("")
    lines.append("## Indexed knowledge snapshot")
    if not snapshot.get("kb_available"):
        lines.append("- Knowledge base is not connected yet. Run /connect or /ingest to load indexed XML context.")
        return "\n".join(lines)

    lines.append(f"- Total indexed chunks: {int(snapshot.get('total_chunks') or 0)}")
    lines.append(f"- Distinct XML files: {int(snapshot.get('distinct_source_files') or 0)}")

    node_counts = snapshot.get("node_class_counts") or {}
    if node_counts:
        node_parts = [f"{k}={int(v)}" for k, v in sorted(node_counts.items())]
        lines.append("- Node class coverage: " + ", ".join(node_parts))

    top_files = snapshot.get("top_source_files") or []
    if top_files:
        top_files_text = ", ".join(
            f"{row['name']} ({int(row['count'])})" for row in top_files[:6]
        )
        lines.append(f"- Top indexed XML files: {top_files_text}")

    top_mappings = snapshot.get("top_mappings") or []
    if top_mappings:
        top_mappings_text = ", ".join(
            f"{row['name']} ({int(row['count'])})" for row in top_mappings[:5]
        )
        lines.append(f"- Top mappings represented: {top_mappings_text}")

    top_folders = snapshot.get("top_folders") or []
    if top_folders:
        top_folders_text = ", ".join(
            f"{row['name']} ({int(row['count'])})" for row in top_folders[:5]
        )
        lines.append(f"- Top folders represented: {top_folders_text}")

    lineage_coverage = snapshot.get("lineage_coverage") or {}
    if lineage_coverage.get("available"):
        totals = lineage_coverage.get("totals") or {}
        lines.append(
            "- Lineage coverage totals: "
            f"lineage_chunks={int(totals.get('lineage_chunk_count') or 0)}, "
            f"resolved_target_fields={int(totals.get('resolved_target_field_count') or 0)}, "
            f"unresolved_target_fields={int(totals.get('unresolved_target_field_count') or 0)}"
        )

        workflows = lineage_coverage.get("workflows") or []
        if workflows:
            top_unresolved = ", ".join(
                (
                    f"{row.get('source_file')} "
                    f"(unresolved={int(row.get('unresolved_target_field_count') or 0)})"
                )
                for row in workflows[:3]
            )
            lines.append(f"- Lineage hotspots (unresolved target fields): {top_unresolved}")

    semantic_layer = snapshot.get("semantic_layer") or {}
    if semantic_layer.get("available"):
        lines.append(
            f"- Semantic model workflows: {int(semantic_layer.get('workflow_count') or 0)}"
        )

    return "\n".join(lines)


def _build_context_agent_payload(query_text: str) -> Dict[str, Any]:
    snapshot = _kb_inventory_snapshot(max_items=8)
    answer_text = _render_context_agent_answer(snapshot)
    return {
        "query": query_text,
        "effective_query": query_text,
        "refused": False,
        "reason": None,
        "detail": None,
        "prompt": "",
        "evidence": [],
        "prompt_version": None,
        "mode": "context_agent",
        "rerank_requested": False,
        "reranked": False,
        "rerank_error": None,
        "retrieval_plan": {"agent_route": "context_inventory"},
        "source_file_hints": _extract_source_file_hints(query_text),
        "answer_text": answer_text,
        "llm_requested": False,
        "llm_used": False,
        "llm_model": _resolve_llm_runtime(None).get("model_name"),
        "llm_error": "not_required_for_context_inventory",
        "relevancy_boost_requested": False,
        "relevancy_boost_applied": False,
        "answer_strategy": "agent_context_capabilities",
        "context_inventory": snapshot,
    }


def _extract_usage_entity(query: str) -> str:
    match = _USAGE_ENTITY_RE.search(query or "")
    if not match:
        return ""
    return " ".join(match.group(1).split()).strip("\"'` ")


def _evidence_match_text(item: Dict[str, Any]) -> str:
    parts = [
        str(item.get("source_file") or ""),
        str(item.get("node_class") or ""),
        str(item.get("name") or ""),
        str(item.get("text") or ""),
        str(item.get("cited_text") or ""),
    ]
    return " ".join(parts).lower()


def _query_focused_snippet(query: str, item: Dict[str, Any], max_chars: int = 220) -> str:
    raw = str(item.get("cited_text") or "")
    if not raw.strip():
        return ""

    intent = _infer_query_intent(query)
    keywords = _query_keywords(query, max_terms=8)
    usage_entity = _extract_usage_entity(query).lower()

    # Ignore structural headers so the snippet is semantic and query-focused.
    skip_prefixes = (
        "FILE:", "NODE_CLASS:", "MAPPING:", "FOLDER:", "PORTS:", "ATTRIBUTES:",
        "HOPS:", "RESOLVED:", "SOURCE_FILE:",
    )
    candidates: List[str] = []
    for line in raw.splitlines():
        line_clean = " ".join(line.split()).strip()
        if not line_clean:
            continue
        if line_clean.upper().startswith(skip_prefixes):
            continue
        candidates.append(line_clean)

    if not candidates:
        return _compact_text(raw, max_chars=max_chars)

    scored: List[tuple[float, str]] = []
    for line in candidates:
        line_lower = line.lower()
        score = 0.0

        if keywords:
            score += sum(1.0 for kw in keywords if kw in line_lower)

        if intent == "sql_override" and ("sql" in line_lower or "qualify" in line_lower):
            score += 3.0
        if intent == "lineage" and ("target:" in line_lower or "source:" in line_lower or "path:" in line_lower):
            score += 3.0
        if intent == "usage" and usage_entity and usage_entity in line_lower:
            score += 4.0

        # Prefer lines that look like actual logic over high-level labels.
        if any(tok in line_lower for tok in ("select", "join", "where", "group by", "expression", "filter")):
            score += 1.5

        scored.append((score, line))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    best = scored[0][1] if scored else candidates[0]
    return _compact_text(best, max_chars=max_chars)


def _select_query_focused_evidence(query: str, evidence: List[Dict[str, Any]], max_items: int = 4) -> List[Dict[str, Any]]:
    if not evidence:
        return []

    intent = _infer_query_intent(query)
    keywords = _query_keywords(query)
    source_hints = set(_extract_source_file_hints(query))
    usage_entity = _extract_usage_entity(query).lower()

    source_hint_list = list(source_hints)
    evidence_pool = _prefer_source_file_hits(evidence, source_hint_list)

    # For usage queries, hard-focus on chunks that explicitly contain the requested entity when possible.
    if intent == "usage" and usage_entity:
        usage_scoped = [
            item for item in evidence_pool if usage_entity in _evidence_match_text(item)
        ]
        if usage_scoped:
            evidence_pool = usage_scoped

    scored: List[tuple[float, Dict[str, Any]]] = []
    for item in evidence_pool:
        text = _evidence_match_text(item)
        score = _safe_score(item.get("score"))

        if keywords:
            overlaps = sum(1 for kw in keywords if kw in text)
            score += overlaps * 1.5

        src = str(item.get("source_file") or "").lower()
        if source_hints and src in source_hints:
            score += 6.0

        node_class = str(item.get("node_class") or "").upper()
        if intent == "lineage" and node_class == "LINEAGE":
            score += 4.0
        if intent == "sql_override" and ("sql" in text or "qualify" in text):
            score += 4.0
        if intent == "usage" and usage_entity and usage_entity in text:
            score += 5.0

        scored.append((score, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)

    selected: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for _, item in scored:
        cid = str(item.get("chunk_id") or "")
        if cid and cid in seen:
            continue
        if cid:
            seen.add(cid)
        selected.append(item)
        if len(selected) >= max_items:
            break

    return selected or evidence_pool[:max_items]


def _answer_has_citations(answer_text: str) -> bool:
    return bool(_CITATION_RE.search(answer_text or ""))


def _keyword_coverage(answer_text: str, query: str) -> int:
    answer_lower = (answer_text or "").lower()
    return sum(1 for kw in _query_keywords(query, max_terms=8) if kw in answer_lower)


def _needs_relevancy_boost(answer_text: str, query: str) -> bool:
    answer = (answer_text or "").strip()
    if not answer:
        return True
    if len(answer) < 48:
        return True
    if not _answer_has_citations(answer):
        return True
    if _keyword_coverage(answer, query) <= 0:
        return True

    answer_lower = answer.lower()
    source_hints = _extract_source_file_hints(query)
    if source_hints and not any(hint in answer_lower for hint in source_hints):
        return True

    usage_entity = _extract_usage_entity(query).lower()
    if usage_entity and usage_entity not in answer_lower:
        return True

    return False


def _maybe_rewrite_for_relevancy_openai(
    query: str,
    draft_answer: str,
    evidence: List[Dict[str, Any]],
    model_override: Optional[str],
    temperature: float,
    max_tokens: int,
) -> tuple[Optional[str], bool, Optional[str], Optional[str]]:
    focused = _select_query_focused_evidence(query, evidence, max_items=4)
    evidence_blocks = _compose_evidence_blocks(focused, max_items=4, max_chars=420)
    prompt = (
        "Rewrite the draft answer so it directly answers the question with grounded evidence.\n"
        "Rules:\n"
        "1) Use only evidence below.\n"
        "2) Include explicit citations like [chunk_id] for every claim.\n"
        "3) Keep it concise and query-focused (3-6 bullets max).\n"
        "4) Do not mention missing context unless evidence is truly insufficient.\n\n"
        "5) Explicitly mention the key query anchor terms (workflow/entity) when present.\n\n"
        f"QUESTION: {query}\n\n"
        f"DRAFT ANSWER: {draft_answer}\n\n"
        f"EVIDENCE:\n{evidence_blocks}\n\n"
        "REWRITTEN ANSWER:"
    )
    return _generate_answer_openai(
        prompt=prompt,
        model_override=model_override,
        temperature=temperature,
        max_tokens=min(max(max_tokens, 512), 1200),
    )


def _build_grounded_relevance_answer(query: str, evidence: List[Dict[str, Any]]) -> str:
    if not evidence:
        return "I cannot find sufficient evidence to answer this question."

    focused = _select_query_focused_evidence(query, evidence, max_items=3)
    intent = _infer_query_intent(query)
    source_hints = _extract_source_file_hints(query)
    usage_entity = _extract_usage_entity(query)

    if intent == "sql_override":
        lead = "Based on retrieved Informatica evidence, SQL override logic is present in the following transformation artifacts:"
    elif intent == "lineage":
        lead = "Based on retrieved Informatica evidence, lineage records supporting this request are:"
    elif intent == "usage" and usage_entity:
        lead = f"Based on retrieved Informatica evidence, {usage_entity} is used in:"
    elif intent == "logic" and source_hints:
        lead = f"Based on retrieved Informatica evidence, logic in {source_hints[0]} appears in these nodes:"
    else:
        lead = "Based on retrieved Informatica evidence, the most relevant grounded details are:"

    bullets: List[str] = []
    for item in focused:
        cid = item.get("chunk_id") or "chunk"
        src = item.get("source_file") or "unknown"
        nc = item.get("node_class") or "NODE"
        name = item.get("name") or "(unnamed)"
        snippet = _query_focused_snippet(query, item, max_chars=220)
        bullets.append(f"- {name} ({nc}, {src}): {snippet} [{cid}]")

    return lead + "\n" + "\n".join(bullets)


def _build_extractive_fallback_answer(query: str, evidence: List[Dict[str, Any]]) -> str:
    return _build_grounded_relevance_answer(query, evidence)


def _is_sql_qualifier_intent(query: str) -> bool:
    q = (query or "").lower()
    signals = [
        "sql qualifier",
        "sql qualifiers",
        "qualify",
        "sql override",
        "sql_override",
    ]
    return any(sig in q for sig in signals)


def _heuristic_retrieval_plan(query: str) -> Dict[str, Any]:
    if _is_sql_qualifier_intent(query):
        return {
            "rewritten_query": "QUALIFY SQL_OVERRIDE SQL qualifier",
            "key_terms": ["QUALIFY", "SQL_OVERRIDE", "SQL qualifier"],
            "mode_hint": "bm25",
            "node_class_hint": "TRANSFORMATION",
            "reasoning": "SQL qualifier intent detected; lexical BM25 over SQL override chunks is preferred.",
        }

    raw_terms = re.findall(r"(wf_\d{4}[A-Za-z0-9_\.]*|[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+)", query)
    key_terms: List[str] = []
    seen = set()
    for term in raw_terms:
        cleaned = term.strip(".,:;!?\"'()[]{}")
        if not cleaned or cleaned.lower() in seen:
            continue
        seen.add(cleaned.lower())
        key_terms.append(cleaned)

    lower_q = query.lower()
    node_class_hint: Optional[str] = None
    if any(tok in lower_q for tok in ["lineage", "target", "source", "path"]):
        node_class_hint = "LINEAGE"
    elif any(tok in lower_q for tok in ["sql", "join", "filter", "qualifier", "transformation"]):
        node_class_hint = "TRANSFORMATION"

    mode_hint = "hybrid"
    if key_terms and any(t.endswith(".XML") or "wf_" in t.lower() or "_Id" in t for t in key_terms):
        mode_hint = "bm25"
    elif len(query.split()) > 10 and not key_terms:
        mode_hint = "vector"

    rewritten_query = " ".join(key_terms[:6]) if key_terms else query
    return {
        "rewritten_query": rewritten_query,
        "key_terms": key_terms,
        "mode_hint": mode_hint,
        "node_class_hint": node_class_hint,
        "reasoning": "Heuristic planner fallback based on technical tokens and intent hints.",
    }


def _extract_json_object(text: str) -> Dict[str, Any]:
    body = (text or "").strip()
    if not body:
        return {}
    try:
        parsed = json.loads(body)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass

    start = body.find("{")
    end = body.rfind("}")
    if start >= 0 and end > start:
        snippet = body[start : end + 1]
        try:
            parsed = json.loads(snippet)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _plan_retrieval_with_openai(query: str, model_override: Optional[str]) -> Dict[str, Any]:
    heuristic = _heuristic_retrieval_plan(query)
    cfg = _resolve_llm_runtime(model_override)
    model_name = cfg["model_name"]

    if not cfg["api_key"]:
        return {
            **heuristic,
            "planner_used": False,
            "planner_model": model_name,
            "planner_error": "Neither OPENAI_API_KEY nor AZURE_OPENAI_API_KEY is configured",
        }
    if cfg["provider"] == "azure" and not cfg["azure_endpoint"]:
        return {
            **heuristic,
            "planner_used": False,
            "planner_model": model_name,
            "planner_error": "AZURE_OPENAI_API_BASE (or AZURE_OPENAI_ENDPOINT) is not configured",
        }

    try:
        client = _make_openai_client(cfg)
        messages = [
            {
                "role": "system",
                "content": (
                    "You optimize technical retrieval queries for Informatica/ETL corpora. "
                    "Return only a JSON object with keys: rewritten_query (string), key_terms (string[]), "
                    "mode_hint (hybrid|vector|bm25), node_class_hint (SOURCE|TRANSFORMATION|TARGET|LINEAGE|null), "
                    "reasoning (string)."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Original user query:\n"
                    f"{query}\n\n"
                    "Keep rewritten_query concise and retrieval-friendly for lexical + vector search."
                ),
            },
        ]

        model_lower = (model_name or "").strip().lower()
        compact_model = model_lower.replace("-", "").replace("_", "")
        is_reasoning_style = (
            compact_model.startswith("gpt5")
            or model_lower.startswith("o1")
            or model_lower.startswith("o2")
            or model_lower.startswith("o3")
            or model_lower.startswith("o4")
            or model_lower.startswith("o5")
            or model_lower == "codex-mini"
        )

        request_kwargs: Dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        if is_reasoning_style:
            planner_budget_raw = os.getenv("PLANNER_MAX_COMPLETION_TOKENS", "900").strip()
            try:
                planner_budget = int(planner_budget_raw)
            except ValueError:
                planner_budget = 900
            planner_budget = max(300, min(planner_budget, 4000))

            request_kwargs["max_completion_tokens"] = planner_budget
            request_kwargs["temperature"] = 1.0
        else:
            request_kwargs["max_tokens"] = 260
            request_kwargs["temperature"] = 0.0

        resp = client.chat.completions.create(**request_kwargs)

        raw = ""
        if resp.choices:
            raw = resp.choices[0].message.content or ""

        if is_reasoning_style and not raw.strip():
            retry_kwargs = dict(request_kwargs)
            retry_kwargs["max_completion_tokens"] = max(
                int(retry_kwargs.get("max_completion_tokens", 900)),
                1200,
            )
            retry_resp = client.chat.completions.create(**retry_kwargs)
            if retry_resp.choices:
                raw = retry_resp.choices[0].message.content or ""

        payload = _extract_json_object(raw)
        if not payload:
            raise ValueError("Planner returned non-JSON content")

        rewritten_query = str(payload.get("rewritten_query") or "").strip() or heuristic["rewritten_query"]
        mode_hint = str(payload.get("mode_hint") or "").strip().lower()
        if mode_hint not in _VALID_MODES:
            mode_hint = heuristic["mode_hint"]

        node_class_hint: Optional[str]
        raw_node = payload.get("node_class_hint")
        if raw_node is None:
            node_class_hint = heuristic["node_class_hint"]
        else:
            node_class_hint = str(raw_node).strip().upper() or None
            if node_class_hint not in _VALID_NODE_CLASSES:
                node_class_hint = heuristic["node_class_hint"]

        raw_terms = payload.get("key_terms")
        key_terms: List[str] = []
        if isinstance(raw_terms, list):
            for term in raw_terms:
                if isinstance(term, str) and term.strip():
                    key_terms.append(term.strip())
        if not key_terms:
            key_terms = heuristic["key_terms"]

        return {
            "rewritten_query": rewritten_query,
            "key_terms": key_terms,
            "mode_hint": mode_hint,
            "node_class_hint": node_class_hint,
            "reasoning": str(payload.get("reasoning") or "").strip() or heuristic["reasoning"],
            "planner_used": True,
            "planner_model": model_name,
            "planner_error": None,
        }
    except Exception as exc:
        logger.warning("LLM planner failed, using heuristic fallback: %s", exc)
        return {
            **heuristic,
            "planner_used": False,
            "planner_model": model_name,
            "planner_error": str(exc),
        }


def _retrieve_hits(
    q: str,
    k: int,
    node_class: Optional[str],
    mode: str,
    rerank: bool,
    use_planner: bool,
    planner_llm_model: Optional[str],
    intent_llm_model: Optional[str] = None,
) -> Dict[str, Any]:
    started_at = perf_counter()
    retrieval_ms = 0
    rerank_ms = 0
    planner_runtime = _resolve_llm_runtime(planner_llm_model)
    plan = {
        "rewritten_query": q,
        "key_terms": [],
        "mode_hint": "hybrid",
        "node_class_hint": None,
        "reasoning": "Retrieval rewrite disabled",
        "planner_used": False,
        "planner_model": planner_runtime["model_name"],
        "planner_error": None,
    }

    effective_query = q
    resolved_mode = "hybrid" if mode == "auto" else mode
    resolved_node_class = node_class
    source_file_hints = _extract_source_file_hints(q)
    intent = _infer_query_intent(q, llm_model_override=intent_llm_model)
    usage_entity = _extract_usage_entity(q)
    lineage_anchor_terms = _extract_lineage_anchor_terms(q) if intent == "lineage" else []
    strict_source_scope = bool(source_file_hints) and intent == "lineage"

    if intent == "lineage" and resolved_node_class is None:
        resolved_node_class = "LINEAGE"

    if intent == "lineage" and mode == "auto":
        resolved_mode = "hybrid"

    if intent == "lineage":
        plan["lineage_mode"] = True
        plan["lineage_anchor_terms"] = lineage_anchor_terms
        plan["strict_source_scope"] = strict_source_scope

    # SQL qualifier/source qualifier logic is lexical and transformation-centric.
    # Apply this override even when planner rewrite is disabled.
    if _is_sql_qualifier_intent(q):
        if mode in {"auto", "hybrid"}:
            resolved_mode = "bm25"
        if resolved_node_class is None:
            resolved_node_class = "TRANSFORMATION"
        plan["mode_hint"] = "bm25"
        plan["node_class_hint"] = "TRANSFORMATION"
        plan["sql_intent_override"] = True

    if use_planner:
        plan = _plan_retrieval_with_openai(q, planner_llm_model)
        if plan.get("rewritten_query"):
            effective_query = str(plan["rewritten_query"])
        if resolved_node_class is None and plan.get("node_class_hint") in _VALID_NODE_CLASSES:
            resolved_node_class = str(plan["node_class_hint"])
        if mode == "auto" and plan.get("mode_hint") in _VALID_MODES:
            resolved_mode = str(plan["mode_hint"])

    if intent == "lineage" and node_class is None and resolved_node_class != "LINEAGE":
        resolved_node_class = "LINEAGE"

    fetch_k = k * 3 if rerank else k
    if source_file_hints:
        # Fan out wider for file-scoped questions, then re-rank down to k after source-file preference.
        fetch_k = max(fetch_k, k * 8)
    if strict_source_scope:
        fetch_k = max(fetch_k, k * 10)

    def _raw_fetch(query_text: str, mode_name: str) -> List[Dict[str, Any]]:
        nonlocal retrieval_ms
        fetch_started_at = perf_counter()
        if mode_name == "hybrid":
            raw_hits = _kb.hybrid_search(query_text, k=fetch_k, filter_node_class=resolved_node_class)
            out = _prefer_source_file_hits(raw_hits, source_file_hints, strict=strict_source_scope)
            retrieval_ms += _elapsed_ms(fetch_started_at)
            return out
        if mode_name == "bm25":
            from rag_system.store.vector_store import PgVectorStore

            if isinstance(_kb._store, PgVectorStore):
                bm_hits = _kb._store.search_bm25(query_text, k=fetch_k * 3)
                if resolved_node_class:
                    bm_hits = [h for h in bm_hits if h.get("node_class") == resolved_node_class]
                out = _prefer_source_file_hits(bm_hits[:fetch_k], source_file_hints, strict=strict_source_scope)
                retrieval_ms += _elapsed_ms(fetch_started_at)
                return out
        raw_hits = _kb.search(query_text, k=fetch_k, filter_node_class=resolved_node_class)
        out = _prefer_source_file_hits(raw_hits, source_file_hints, strict=strict_source_scope)
        retrieval_ms += _elapsed_ms(fetch_started_at)
        return out

    def _hit_mentions_usage_entity(hit: Dict[str, Any], usage_entity: str) -> bool:
        if not usage_entity:
            return False
        text = " ".join(
            [
                str(hit.get("source_file") or ""),
                str(hit.get("node_class") or ""),
                str(hit.get("name") or ""),
                str(hit.get("text") or ""),
            ]
        ).lower()
        return usage_entity.lower() in text

    hits = _raw_fetch(effective_query, resolved_mode)

    if intent == "sql_override" and not hits:
        attempted_sql: set[tuple[str, str]] = {(effective_query.strip().lower(), resolved_mode)}
        stripped_query = " ".join(_WF_XML_RE.sub(" ", q or "").split()).strip()
        sql_fallback_candidates: List[tuple[str, str, str]] = []
        if stripped_query:
            sql_fallback_candidates.append((stripped_query, resolved_mode, "sql_strip_workflow_hint"))
        sql_fallback_candidates.extend(
            [
                ("sql override source qualifier", "hybrid", "sql_anchor_hybrid"),
                ("source qualifier sql override", "vector", "sql_anchor_vector"),
            ]
        )

        for candidate_query, candidate_mode, reason in sql_fallback_candidates:
            key = (candidate_query.strip().lower(), candidate_mode)
            if not candidate_query.strip() or key in attempted_sql:
                continue
            attempted_sql.add(key)

            candidate_hits = _raw_fetch(candidate_query, candidate_mode)
            if candidate_hits:
                hits = candidate_hits
                effective_query = candidate_query
                resolved_mode = candidate_mode
                plan["sql_fallback_applied"] = True
                plan["fallback_reason"] = reason
                plan["fallback_query"] = candidate_query
                plan["fallback_mode"] = candidate_mode
                break

    # Guardrail for usage questions: force an entity-centric fallback query when
    # the normal retrieval does not actually mention the requested field/entity.
    if intent == "usage" and usage_entity:
        entity_hits = [h for h in hits if _hit_mentions_usage_entity(h, usage_entity)]

        if not entity_hits:
            tried_keys = {
                (effective_query.strip().lower(), resolved_mode),
            }
            fallback_candidates: List[tuple[str, str, str]] = [
                (usage_entity, "bm25", "usage_entity_bm25"),
                (usage_entity, "hybrid", "usage_entity_hybrid"),
                (usage_entity, "vector", "usage_entity_vector"),
            ]

            for candidate_query, candidate_mode, reason in fallback_candidates:
                key = (candidate_query.strip().lower(), candidate_mode)
                if key in tried_keys:
                    continue
                tried_keys.add(key)
                candidate_hits = _raw_fetch(candidate_query, candidate_mode)
                candidate_entity_hits = [
                    h for h in candidate_hits if _hit_mentions_usage_entity(h, usage_entity)
                ]
                if candidate_entity_hits:
                    hits = candidate_entity_hits
                    effective_query = candidate_query
                    resolved_mode = candidate_mode
                    plan["usage_entity_fallback_applied"] = True
                    plan["usage_entity"] = usage_entity
                    plan["fallback_reason"] = reason
                    plan["fallback_query"] = candidate_query
                    plan["fallback_mode"] = candidate_mode
                    break

    if intent == "lineage":
        if lineage_anchor_terms:
            anchor_hits = [h for h in hits if _hit_mentions_anchor_terms(h, lineage_anchor_terms)]
            if anchor_hits:
                hits = anchor_hits
                plan["lineage_anchor_filter_applied"] = True
            else:
                hits = []
                plan["lineage_anchor_filter_applied"] = True
                plan["lineage_anchor_filter_empty"] = True

        if not hits:
            attempted: set[tuple[str, str]] = {(effective_query.strip().lower(), resolved_mode)}
            source_hint = source_file_hints[0] if source_file_hints else ""
            anchor_query = " ".join(lineage_anchor_terms[:3]).strip()

            fallback_candidates: List[tuple[str, str, str]] = []
            if anchor_query and source_hint:
                fallback_candidates.append((f"{anchor_query} {source_hint}", "bm25", "lineage_anchor_source_bm25"))
                fallback_candidates.append((f"{anchor_query} {source_hint}", "hybrid", "lineage_anchor_source_hybrid"))
            if anchor_query:
                fallback_candidates.append((anchor_query, "bm25", "lineage_anchor_only_bm25"))
                fallback_candidates.append((anchor_query, "hybrid", "lineage_anchor_only_hybrid"))
            if source_hint:
                fallback_candidates.append((source_hint, "bm25", "lineage_source_only_bm25"))

            for candidate_query, candidate_mode, reason in fallback_candidates:
                key = (candidate_query.strip().lower(), candidate_mode)
                if key in attempted:
                    continue
                attempted.add(key)

                candidate_hits = _raw_fetch(candidate_query, candidate_mode)
                if lineage_anchor_terms:
                    candidate_hits = [
                        h for h in candidate_hits if _hit_mentions_anchor_terms(h, lineage_anchor_terms)
                    ]
                if candidate_hits:
                    hits = candidate_hits
                    effective_query = candidate_query
                    resolved_mode = candidate_mode
                    plan["lineage_fallback_applied"] = True
                    plan["fallback_reason"] = reason
                    plan["fallback_query"] = candidate_query
                    plan["fallback_mode"] = candidate_mode
                    break

    # Guardrail: if planner rewrite produced no hits, retry with safer alternatives.
    # For bm25 rewrite misses, fall back to hybrid to recover semantic recall.
    if not hits and use_planner:
        fallback_mode = "hybrid" if resolved_mode == "bm25" else resolved_mode
        attempted: set[str] = {effective_query.strip().lower()}

        candidates: List[tuple[str, str]] = []
        if q.strip().lower() not in attempted:
            candidates.append((q, "planner_rewrite_no_hits"))

        key_terms = plan.get("key_terms")
        if isinstance(key_terms, list):
            compact_terms = [str(t).strip() for t in key_terms if str(t).strip()]
            if compact_terms:
                anchor_terms = [
                    t for t in compact_terms
                    if "_" in t or t.lower().startswith("wf_") or t.lower().endswith(".xml")
                ]
                for term in anchor_terms[:3]:
                    if term.strip().lower() not in attempted and term.strip().lower() != q.strip().lower():
                        candidates.append((term, "planner_rewrite_no_hits_anchor_term"))

                key_query = " ".join(compact_terms[:6])
                if key_query.strip().lower() not in attempted and key_query.strip().lower() != q.strip().lower():
                    candidates.append((key_query, "planner_rewrite_no_hits_key_terms"))

        for candidate_query, reason in candidates:
            attempted.add(candidate_query.strip().lower())
            fallback_hits = _raw_fetch(candidate_query, fallback_mode)
            if fallback_hits:
                hits = fallback_hits
                effective_query = candidate_query
                resolved_mode = fallback_mode
                plan["fallback_applied"] = True
                plan["fallback_reason"] = reason
                plan["fallback_query"] = candidate_query
                plan["fallback_mode"] = fallback_mode
                break

    reranked = False
    rerank_error: Optional[str] = None
    pre_rerank_hits = list(hits)
    if rerank and hits:
        rerank_started_at = perf_counter()
        hits, reranked, rerank_error = _try_rerank(effective_query, hits, top_k=k)
        rerank_ms += _elapsed_ms(rerank_started_at)

        # Guardrail for usage questions: if rerank dropped the requested entity,
        # restore entity-containing pre-rerank hits to keep answers grounded.
        if intent == "usage" and usage_entity:
            reranked_entity_hits = [
                h for h in hits if _hit_mentions_usage_entity(h, usage_entity)
            ]
            if not reranked_entity_hits:
                pre_entity_hits = [
                    h for h in pre_rerank_hits if _hit_mentions_usage_entity(h, usage_entity)
                ]
                if pre_entity_hits:
                    hits = pre_entity_hits[:k]
                    reranked = False
                    rerank_error = (
                        f"{rerank_error}; usage_entity_guardrail_restored_pre_rerank"
                        if rerank_error
                        else "usage_entity_guardrail_restored_pre_rerank"
                    )
                    plan["usage_entity_rerank_guardrail"] = True

        # Guardrail for lineage questions: keep anchor-aligned chunks if reranking drops them.
        if intent == "lineage" and lineage_anchor_terms:
            reranked_anchor_hits = [
                h for h in hits if _hit_mentions_anchor_terms(h, lineage_anchor_terms)
            ]
            if not reranked_anchor_hits:
                pre_anchor_hits = [
                    h for h in pre_rerank_hits if _hit_mentions_anchor_terms(h, lineage_anchor_terms)
                ]
                if pre_anchor_hits:
                    hits = pre_anchor_hits[:k]
                    reranked = False
                    rerank_error = (
                        f"{rerank_error}; lineage_anchor_guardrail_restored_pre_rerank"
                        if rerank_error
                        else "lineage_anchor_guardrail_restored_pre_rerank"
                    )
                    plan["lineage_anchor_rerank_guardrail"] = True
    else:
        hits = hits[:k]

    if strict_source_scope:
        hits = _prefer_source_file_hits(hits, source_file_hints, strict=True)

    if intent == "lineage" and lineage_anchor_terms:
        hits = [h for h in hits if _hit_mentions_anchor_terms(h, lineage_anchor_terms)]

    return {
        "hits": hits,
        "plan": plan,
        "effective_query": effective_query,
        "resolved_mode": resolved_mode,
        "resolved_node_class": resolved_node_class,
        "source_file_hints": source_file_hints,
        "reranked": reranked,
        "rerank_error": rerank_error,
        "intent": intent,
        "timing_ms": {
            "retrieval_ms": retrieval_ms,
            "rerank_ms": rerank_ms,
            "total_ms": _elapsed_ms(started_at),
        },
    }


@app.get("/retrieve", summary="Semantic search over the indexed corpus")
def retrieve(
    q: str = Query(..., description="Natural-language query"),
    k: int = Query(5, ge=1, le=50, description="Number of results"),
    node_class: Optional[str] = Query(
        None,
        description="Filter by node class: SOURCE | TRANSFORMATION | TARGET | LINEAGE",
    ),
    mode: str = Query(
        "hybrid",
        description="Retrieval mode: hybrid (BM25+vector RRF) | vector | bm25 | auto",
        pattern="^(hybrid|vector|bm25|auto)$",
    ),
    rerank: bool = Query(
        False,
        description="Apply cross-encoder reranker after retrieval (slower, higher precision)",
    ),
) -> Dict[str, Any]:
    """Return the top-k most relevant chunks for the query."""
    request_started_at = perf_counter()
    if _kb is None or not _kb._built:
        raise HTTPException(
            status_code=503,
            detail="Knowledge base not built yet. POST /ingest or POST /connect first.",
        )

    retrieval = _retrieve_hits(
        q=q,
        k=k,
        node_class=node_class,
        mode=mode,
        rerank=rerank,
        use_planner=False,
        planner_llm_model=None,
    )
    hits = retrieval["hits"]
    reranked = retrieval["reranked"]
    rerank_error = retrieval["rerank_error"]
    plan = retrieval["plan"]
    resolved_mode = retrieval["resolved_mode"]
    resolved_node_class = retrieval["resolved_node_class"]
    effective_query = retrieval["effective_query"]
    source_file_hints = retrieval.get("source_file_hints") or []
    timing_ms = dict(retrieval.get("timing_ms") or {})
    timing_ms["total_ms"] = _elapsed_ms(request_started_at)
    trace = _new_trace_payload(
        endpoint="/retrieve",
        query=q,
        intent=str(retrieval.get("intent") or ""),
        orchestration_mode="retrieve_only",
    )

    return {
        "query": q,
        "effective_query": effective_query,
        "k": k,
        "node_class_filter": resolved_node_class,
        "mode": resolved_mode,
        "rerank_requested": rerank,
        "reranked": reranked,
        "rerank_error": rerank_error,
        "retrieval_plan": plan,
        "source_file_hints": source_file_hints,
        "hits": hits,
        "trace": trace,
        "telemetry": {
            "timing_ms": timing_ms,
            "events": [
                {"stage": "retrieval", "status": "ok", "mode": resolved_mode},
                {
                    "stage": "rerank",
                    "status": ("ok" if reranked else ("error" if rerank_error else "skipped")),
                    "error": rerank_error,
                },
            ],
        },
    }


# ---------------------------------------------------------------------------
# Refusal policy helper
# ---------------------------------------------------------------------------
_REFUSAL_THRESHOLD_VECTOR = float(
    os.getenv("REFUSAL_SCORE_THRESHOLD_VECTOR", os.getenv("REFUSAL_SCORE_THRESHOLD", "0.02"))
)
_REFUSAL_THRESHOLD_BM25 = float(os.getenv("REFUSAL_SCORE_THRESHOLD_BM25", "0.02"))


def _score_and_threshold(hits: List[Dict[str, Any]], mode: str) -> tuple[float, float]:
    if mode == "bm25":
        threshold = _REFUSAL_THRESHOLD_BM25
    else:
        threshold = _REFUSAL_THRESHOLD_VECTOR

    if not hits:
        return 0.0, threshold

    top = hits[0]
    if mode == "hybrid":
        score = top.get("vector_score", top.get("score", 0.0))
    else:
        score = top.get("score", 0.0)
    return _safe_score(score), threshold


def _insufficient_evidence(hits: List[Dict[str, Any]], mode: str) -> bool:
    """Return True when top hit score is below the mode-specific refusal threshold."""
    score, threshold = _score_and_threshold(hits, mode)
    return score < threshold


def _lineage_coverage_for_hints(source_file_hints: List[str]) -> List[Dict[str, Any]]:
    if not source_file_hints or _kb is None or not _kb._built:
        return []
    if not hasattr(_kb, "lineage_coverage_snapshot"):
        return []

    try:
        snapshot = _kb.lineage_coverage_snapshot(include_fields=False)
    except Exception:
        return []

    workflows = snapshot.get("workflows") or []
    if not isinstance(workflows, list):
        return []

    by_file = {
        str(row.get("source_file") or "").lower(): row
        for row in workflows
        if isinstance(row, dict) and row.get("source_file")
    }
    out: List[Dict[str, Any]] = []
    for hint in source_file_hints:
        row = by_file.get(hint.lower())
        if row:
            out.append(row)
    return out


def _lineage_guardrail_failure(
    query: str,
    hits: List[Dict[str, Any]],
    source_file_hints: List[str],
) -> Optional[Dict[str, str]]:
    if _infer_query_intent(query) != "lineage":
        return None

    # Exploratory lineage prompts without workflow scope should use normal retrieval,
    # not hard-refuse due missing deterministic lineage chunks.
    if not source_file_hints:
        return None

    hint_set = {h.lower() for h in source_file_hints}
    lineage_hits = [h for h in hits if str(h.get("node_class") or "").upper() == "LINEAGE"]
    if hint_set:
        lineage_hits = [
            h for h in lineage_hits if str(h.get("source_file") or "").lower() in hint_set
        ]

    if not lineage_hits:
        scope_text = (
            ", ".join(sorted(hint_set))
            if hint_set
            else "the requested lineage scope"
        )
        reason = "lineage_unavailable"
        detail = (
            "No field-level LINEAGE records were retrieved for "
            f"{scope_text}."
        )

        coverage_rows = _lineage_coverage_for_hints(source_file_hints)
        if coverage_rows:
            if all(int(row.get("lineage_chunk_count") or 0) == 0 for row in coverage_rows):
                reason = "lineage_not_indexed_for_workflow"
            coverage_text = "; ".join(
                (
                    f"{row.get('source_file')}: "
                    f"lineage_chunks={int(row.get('lineage_chunk_count') or 0)}, "
                    f"resolved_target_fields={int(row.get('resolved_target_field_count') or 0)}, "
                    f"unresolved_target_fields={int(row.get('unresolved_target_field_count') or 0)}"
                )
                for row in coverage_rows
            )
            detail = f"{detail} Coverage telemetry: {coverage_text}."

        detail = f"{detail} I will not synthesize lineage from non-lineage transformation context."
        return {"reason": reason, "detail": detail}

    anchor_terms = _extract_lineage_anchor_terms(query)
    if anchor_terms:
        anchored = [h for h in lineage_hits if _hit_mentions_anchor_terms(h, anchor_terms)]
        if not anchored:
            return {
                "reason": "lineage_field_not_found",
                "detail": (
                    "Lineage records exist for the workflow scope, but none explicitly match "
                    f"the requested field anchors: {', '.join(anchor_terms)}."
                ),
            }

    return None


def _semantic_refusal_payload(
    *,
    q: str,
    reason: str,
    detail: str,
    llm: bool,
    llm_model: Optional[str],
    source_file_hints: List[str],
    retrieval_plan: Dict[str, Any],
    answer_strategy: str,
    timing_ms: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    llm_cfg = _resolve_llm_runtime(llm_model)
    return {
        "query": q,
        "effective_query": q,
        "refused": True,
        "reason": reason,
        "detail": detail,
        "prompt": "",
        "evidence": [],
        "prompt_version": "semantic_v1",
        "mode": "semantic",
        "rerank_requested": False,
        "reranked": False,
        "rerank_error": None,
        "retrieval_plan": retrieval_plan,
        "source_file_hints": source_file_hints,
        "answer_text": detail,
        "llm_requested": llm,
        "llm_used": False,
        "llm_model": llm_cfg["model_name"],
        "llm_error": "skipped_due_to_semantic_guardrail" if llm else None,
        "relevancy_boost_requested": False,
        "relevancy_boost_applied": False,
        "answer_strategy": answer_strategy,
        "_timing_ms": timing_ms or {},
    }


def _semantic_path_render(path: Dict[str, Any]) -> str:
    hops = path.get("hops") or []
    hop_render = " -> ".join(
        f"{str(h.get('instance') or '').strip()}.{str(h.get('field') or '').strip()}"
        for h in hops
        if str(h.get("instance") or "").strip() and str(h.get("field") or "").strip()
    )
    mapping = str(path.get("mapping") or "")
    target = f"{str(path.get('target_instance') or '').strip()}.{str(path.get('target_field') or '').strip()}"
    source_instance = str(path.get("source_instance") or "").strip()
    source_field = str(path.get("source_field") or "").strip()
    source = f"{source_instance}.{source_field}" if source_instance and source_field else "UNRESOLVED"
    hop_count = int(path.get("hop_count") or 0)
    workflow = str(path.get("workflow") or "").strip()
    workflow_prefix = f"WORKFLOW: {workflow}\n" if workflow else ""
    return (
        workflow_prefix
        + f"MAPPING: {mapping}\n"
        + f"TARGET: {target}\n"
        + f"SOURCE: {source}\n"
        + f"HOP_COUNT: {hop_count}\n"
        f"PATH: {hop_render}"
    )


def _render_semantic_primary_answer(
    *,
    intent: str,
    semantic_result: Dict[str, Any],
    primary_evidence: List[Dict[str, Any]],
    secondary_evidence: List[Dict[str, Any]],
) -> str:
    workflow = str(semantic_result.get("workflow") or "")
    field = str(semantic_result.get("field") or "")
    cross_workflow = bool(semantic_result.get("cross_workflow"))

    lines: List[str] = []
    if intent == "impact":
        impacted_count = int(semantic_result.get("impacted_target_count") or 0)
        if cross_workflow:
            lines.append(
                f"Deterministic cross-workflow impact from semantic graph for {field}: {impacted_count} impacted target field(s)."
            )
        else:
            lines.append(
                f"Deterministic impact from semantic layer for {field} in {workflow}: {impacted_count} impacted target field(s)."
            )
    else:
        if cross_workflow:
            wf_count = int(semantic_result.get("workflow_count") or 0)
            lines.append(
                f"Deterministic cross-workflow lineage from semantic graph for {field} across {wf_count} workflow(s):"
            )
        else:
            lines.append(
                f"Deterministic lineage from semantic layer for {field} in {workflow}:"
            )

    workflows = list(semantic_result.get("workflows") or [])
    if cross_workflow and workflows:
        lines.append("Workflows: " + ", ".join(str(w) for w in workflows[:10]))

    for row in primary_evidence[:8]:
        cid = str(row.get("chunk_id") or "")
        cited_text = str(row.get("cited_text") or "")
        source_workflow = str(row.get("source_file") or "")
        target = ""
        source = ""
        mapping = ""
        hop_count = ""
        for line in cited_text.splitlines():
            line_stripped = line.strip()
            if line_stripped.startswith("TARGET:"):
                target = line_stripped.replace("TARGET:", "").strip()
            elif line_stripped.startswith("SOURCE:"):
                source = line_stripped.replace("SOURCE:", "").strip()
            elif line_stripped.startswith("MAPPING:"):
                mapping = line_stripped.replace("MAPPING:", "").strip()
            elif line_stripped.startswith("HOP_COUNT:"):
                hop_count = line_stripped.replace("HOP_COUNT:", "").strip()
        wf_prefix = f"{source_workflow}: " if source_workflow else ""
        lines.append(f"- {wf_prefix}{target} <= {source} via {mapping} (hops={hop_count}) [{cid}]")

    if intent == "impact":
        impacted_targets = semantic_result.get("impacted_targets") or []
        if impacted_targets:
            lines.append("Impacted targets: " + ", ".join(str(t) for t in impacted_targets[:20]))

    if secondary_evidence:
        lines.append("Secondary vector context (non-authoritative, for explanation only):")
        for row in secondary_evidence[:3]:
            cid = str(row.get("chunk_id") or "")
            name = str(row.get("name") or "")
            source_file = str(row.get("source_file") or "")
            snippet = _query_focused_snippet(field, row, max_chars=170)
            lines.append(f"- {name} ({source_file}): {snippet} [{cid}]")

    return "\n".join(lines)


def _maybe_answer_from_semantic_layer(
    *,
    q: str,
    k: int,
    mode: str,
    llm: bool,
    llm_model: Optional[str],
    llm_temperature: float,
    llm_max_tokens: int,
) -> Optional[Dict[str, Any]]:
    intent = _infer_query_intent(q, llm_model_override=llm_model)
    if intent not in {"lineage", "impact"}:
        return None

    semantic_ms = 0
    secondary_retrieval_ms = 0
    generation_ms = 0

    source_file_hints = _extract_source_file_hints(q)
    field_anchors = _extract_lineage_anchor_terms(q, max_terms=4)
    retrieval_plan: Dict[str, Any] = {
        "semantic_first": True,
        "intent": intent,
        "source_file_hints": source_file_hints,
        "field_anchors": field_anchors,
    }

    if _kb is None or not _kb._built or not hasattr(_kb, "query_semantic_lineage"):
        return _semantic_refusal_payload(
            q=q,
            reason="semantic_layer_unavailable",
            detail="Semantic query engine is unavailable. Build or connect the indexed semantic model first.",
            llm=llm,
            llm_model=llm_model,
            source_file_hints=source_file_hints,
            retrieval_plan=retrieval_plan,
            answer_strategy="semantic_guardrail_refusal",
            timing_ms={
                "semantic_ms": semantic_ms,
                "secondary_retrieval_ms": secondary_retrieval_ms,
                "generation_ms": generation_ms,
            },
        )

    if not source_file_hints:
        require_scope = os.getenv("SEMANTIC_REQUIRE_WORKFLOW_HINT", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if require_scope:
            return _semantic_refusal_payload(
                q=q,
                reason="semantic_workflow_required",
                detail="Workflow-scoped deterministic answering requires an explicit workflow file hint (wf_####...XML).",
                llm=llm,
                llm_model=llm_model,
                source_file_hints=source_file_hints,
                retrieval_plan=retrieval_plan,
                answer_strategy="semantic_guardrail_refusal",
                timing_ms={
                    "semantic_ms": semantic_ms,
                    "secondary_retrieval_ms": secondary_retrieval_ms,
                    "generation_ms": generation_ms,
                },
            )

        # Cross-workflow graph tracing for lineage/impact when a clear field anchor exists.
        if not field_anchors:
            logger.info("No field anchor found for cross-workflow semantic tracing; fallback to retrieval")
            return None

    if not field_anchors:
        return _semantic_refusal_payload(
            q=q,
            reason="semantic_field_required",
            detail="Deterministic lineage/impact answering requires an explicit field/entity token in the query.",
            llm=llm,
            llm_model=llm_model,
            source_file_hints=source_file_hints,
            retrieval_plan=retrieval_plan,
            answer_strategy="semantic_guardrail_refusal",
            timing_ms={
                "semantic_ms": semantic_ms,
                "secondary_retrieval_ms": secondary_retrieval_ms,
                "generation_ms": generation_ms,
            },
        )

    workflow_hint = source_file_hints[0] if source_file_hints else ""
    allow_cross_workflow = not bool(workflow_hint)
    field_anchor = field_anchors[0]
    retrieval_plan["workflow_hint"] = workflow_hint or "*"
    retrieval_plan["field_anchor"] = field_anchor
    retrieval_plan["cross_workflow"] = allow_cross_workflow

    semantic_query_started_at = perf_counter()
    if intent == "lineage":
        semantic_result = _kb.query_semantic_lineage(
            workflow_hint=workflow_hint,
            field_name=field_anchor,
            limit=max(k, 16),
            allow_cross_workflow=allow_cross_workflow,
        )
    else:
        semantic_result = _kb.query_semantic_impact(
            workflow_hint=workflow_hint,
            field_name=field_anchor,
            limit=max(k, 20),
            allow_cross_workflow=allow_cross_workflow,
        )
    semantic_ms = _elapsed_ms(semantic_query_started_at)

    status = str(semantic_result.get("status") or "")
    retrieval_plan["semantic_status"] = status
    retrieval_plan["semantic_workflow"] = semantic_result.get("workflow")

    if status != "ok":
        if status == "workflow_not_indexed" and workflow_hint:
            detail = (
                f"Structured semantic evidence is not indexed for workflow hint '{workflow_hint}'. "
                "I will not synthesize lineage/impact from vector-only context."
            )
            reason = "semantic_workflow_not_indexed"
        elif status == "workflow_not_indexed" and not workflow_hint:
            detail = (
                f"Structured semantic evidence did not find cross-workflow occurrences for '{field_anchor}'. "
                "I will not synthesize lineage/impact from vector-only context."
            )
            reason = "semantic_field_unresolved"
        elif status == "field_not_found":
            detail = (
                f"Structured semantic evidence does not resolve field '{field_anchor}'"
                + (f" in workflow '{workflow_hint}'" if workflow_hint else " across indexed workflows")
                + ". "
                "Status: unresolved for deterministic lineage/impact."
            )
            reason = "semantic_field_unresolved"
        else:
            detail = "Structured semantic evidence is unavailable for this deterministic query."
            reason = "semantic_query_unavailable"
        return _semantic_refusal_payload(
            q=q,
            reason=reason,
            detail=detail,
            llm=llm,
            llm_model=llm_model,
            source_file_hints=source_file_hints,
            retrieval_plan=retrieval_plan,
            answer_strategy="semantic_guardrail_refusal",
            timing_ms={
                "semantic_ms": semantic_ms,
                "secondary_retrieval_ms": secondary_retrieval_ms,
                "generation_ms": generation_ms,
            },
        )

    paths = list(semantic_result.get("paths") or [])
    primary_evidence: List[Dict[str, Any]] = []
    for idx, path in enumerate(paths[: max(6, k)], start=1):
        cid = str(path.get("evidence_id") or f"semantic:{intent}:{idx}")
        target = f"{str(path.get('target_instance') or '').strip()}.{str(path.get('target_field') or '').strip()}"
        path_workflow = str(path.get("workflow") or semantic_result.get("workflow") or workflow_hint)
        primary_evidence.append(
            {
                "chunk_id": cid,
                "source_file": path_workflow,
                "node_class": "SEMANTIC_LINEAGE" if intent == "lineage" else "SEMANTIC_IMPACT",
                "name": target,
                "score": 1.0,
                "cited_text": _semantic_path_render(path),
                "evidence_source": "semantic_layer",
            }
        )

    secondary_evidence: List[Dict[str, Any]] = []
    secondary_error: Optional[str] = None
    secondary_retrieval_started_at = perf_counter()
    try:
        evidence_ids = [str(row.get("chunk_id") or "") for row in primary_evidence if str(row.get("chunk_id") or "")]
        explanation_hits: List[Dict[str, Any]] = []
        if hasattr(_kb, "search_semantic_explanations"):
            explanation_hits = _kb.search_semantic_explanations(
                query=q,
                evidence_ids=evidence_ids,
                workflow_hint=workflow_hint,
                k=min(3, max(2, k)),
            )

        if explanation_hits:
            retrieval_plan["secondary_retrieval"] = {
                "strategy": "semantic_explanation_vectors",
                "linked_evidence_ids": evidence_ids[:8],
                "hit_count": len(explanation_hits),
            }
            for hit in explanation_hits[:3]:
                secondary_evidence.append(
                    {
                        "chunk_id": str(hit.get("chunk_id") or ""),
                        "source_file": str(hit.get("source_file") or ""),
                        "node_class": str(hit.get("node_class") or ""),
                        "name": str(hit.get("name") or ""),
                        "score": _safe_score(hit.get("score")),
                        "cited_text": str(hit.get("text") or ""),
                        "evidence_source": "vector_secondary",
                    }
                )

        if not secondary_evidence:
            secondary_query = f"{workflow_hint} {field_anchor} transformation logic".strip()
            if not workflow_hint:
                secondary_query = f"{field_anchor} lineage transformation logic"
            secondary = _retrieve_hits(
                q=secondary_query,
                k=min(3, max(2, k)),
                node_class="TRANSFORMATION",
                mode="hybrid" if mode == "auto" else mode,
                rerank=False,
                use_planner=False,
                planner_llm_model=None,
                intent_llm_model=llm_model,
            )
            retrieval_plan["secondary_retrieval"] = {
                "strategy": "generic_transformation_context",
                "effective_query": secondary.get("effective_query"),
                "mode": secondary.get("resolved_mode"),
                "node_class": secondary.get("resolved_node_class"),
            }
            for hit in (secondary.get("hits") or [])[:2]:
                secondary_evidence.append(
                    {
                        "chunk_id": str(hit.get("chunk_id") or ""),
                        "source_file": str(hit.get("source_file") or ""),
                        "node_class": str(hit.get("node_class") or ""),
                        "name": str(hit.get("name") or ""),
                        "score": _safe_score(hit.get("score")),
                        "cited_text": str(hit.get("text") or ""),
                        "evidence_source": "vector_secondary",
                    }
                )
    except Exception as exc:
        secondary_error = str(exc)
        retrieval_plan["secondary_retrieval_error"] = secondary_error
    secondary_retrieval_ms = _elapsed_ms(secondary_retrieval_started_at)

    evidence = primary_evidence + secondary_evidence
    deterministic_answer = _render_semantic_primary_answer(
        intent=intent,
        semantic_result=semantic_result,
        primary_evidence=primary_evidence,
        secondary_evidence=secondary_evidence,
    )

    answer_text = deterministic_answer
    llm_used = False
    resolved_llm_model = _resolve_llm_runtime(llm_model)["model_name"]
    llm_error: Optional[str] = None
    answer_strategy = "semantic_deterministic"
    prompt_text = ""

    if llm:
        semantic_blocks = _compose_evidence_blocks(primary_evidence, max_items=min(8, len(primary_evidence)), max_chars=500)
        secondary_blocks = _compose_evidence_blocks(secondary_evidence, max_items=min(3, len(secondary_evidence)), max_chars=260)
        prompt_text = (
            "You are an Informatica lineage/impact copilot.\n"
            "Primary truth is structured semantic evidence.\n"
            "Use secondary vector context only for explanation, never to contradict primary truth.\n"
            "If primary evidence is missing, refuse instead of guessing.\n"
            "Cite every claim with [chunk_id].\n\n"
            f"QUESTION: {q}\n\n"
            f"PRIMARY_SEMANTIC_EVIDENCE:\n{semantic_blocks}\n\n"
            f"SECONDARY_VECTOR_CONTEXT:\n{secondary_blocks}\n\n"
            "ANSWER:"
        )
        generation_started_at = perf_counter()
        llm_text, llm_used, resolved_llm_model, llm_error = _generate_answer_openai(
            prompt=prompt_text,
            model_override=llm_model,
            temperature=llm_temperature,
            max_tokens=min(max(llm_max_tokens, 500), 1200),
        )
        generation_ms += _elapsed_ms(generation_started_at)
        if llm_text and _answer_has_citations(llm_text):
            answer_text = llm_text
            answer_strategy = "semantic_llm_copilot"
        else:
            llm_error = (
                f"{llm_error}; semantic_fallback_used"
                if llm_error
                else "semantic_fallback_used"
            )

    if secondary_error and not llm_error:
        llm_error = f"secondary_context_error={secondary_error}"
    elif secondary_error and llm_error:
        llm_error = f"{llm_error}; secondary_context_error={secondary_error}"

    return {
        "query": q,
        "effective_query": q,
        "refused": False,
        "reason": None,
        "detail": None,
        "prompt": prompt_text,
        "evidence": evidence,
        "prompt_version": "semantic_v1",
        "mode": "semantic",
        "rerank_requested": False,
        "reranked": False,
        "rerank_error": None,
        "retrieval_plan": retrieval_plan,
        "source_file_hints": source_file_hints,
        "answer_text": answer_text,
        "llm_requested": llm,
        "llm_used": llm_used,
        "llm_model": resolved_llm_model,
        "llm_error": llm_error,
        "relevancy_boost_requested": False,
        "relevancy_boost_applied": False,
        "answer_strategy": answer_strategy,
        "semantic_result": semantic_result,
        "_timing_ms": {
            "semantic_ms": semantic_ms,
            "secondary_retrieval_ms": secondary_retrieval_ms,
            "generation_ms": generation_ms,
        },
    }


# ---------------------------------------------------------------------------
# /answer endpoint â€” citation-backed answer generation
# ---------------------------------------------------------------------------
def _resolve_answer_orchestration_mode(use_graph: Optional[bool]) -> str:
    if use_graph is not None:
        return "graph" if use_graph else "legacy"

    configured = os.getenv("ANSWER_ORCHESTRATION_MODE", "graph").strip().lower()
    return "graph" if configured == "graph" else "legacy"


def _normalize_optional_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"true", "1", "yes", "on"}:
            return True
        if v in {"false", "0", "no", "off"}:
            return False
    return None


def _normalize_optional_int(value: Any) -> Optional[int]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        v = value.strip()
        if not v:
            return None
        try:
            return int(v)
        except ValueError:
            return None
    return None


def _build_answer_payload_from_retrieval(
    *,
    q: str,
    rerank: bool,
    prompt_name: str,
    llm: bool,
    relevancy_boost: bool,
    llm_model: Optional[str],
    llm_temperature: float,
    llm_max_tokens: int,
    hits: List[Dict[str, Any]],
    reranked: bool,
    rerank_error: Optional[str],
    plan: Dict[str, Any],
    resolved_mode: str,
    effective_query: str,
    source_file_hints: List[str],
    retrieval_timing_ms: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    llm_cfg = _resolve_llm_runtime(llm_model)
    timing_ms = dict(retrieval_timing_ms or {})
    timing_ms.setdefault("retrieval_ms", 0)
    timing_ms.setdefault("rerank_ms", 0)
    timing_ms.setdefault("generation_ms", 0)

    lineage_failure = _lineage_guardrail_failure(q, hits, source_file_hints)
    if lineage_failure:
        detail = lineage_failure["detail"]
        return {
            "query": q,
            "effective_query": effective_query,
            "refused": True,
            "reason": lineage_failure["reason"],
            "detail": detail,
            "prompt": "",
            "evidence": [],
            "prompt_version": None,
            "mode": resolved_mode,
            "rerank_requested": rerank,
            "reranked": reranked,
            "rerank_error": rerank_error,
            "retrieval_plan": plan,
            "source_file_hints": source_file_hints,
            "answer_text": detail,
            "llm_requested": llm,
            "llm_used": False,
            "llm_model": llm_cfg["model_name"],
            "llm_error": "skipped_due_to_lineage_guardrail" if llm else None,
            "relevancy_boost_requested": relevancy_boost,
            "relevancy_boost_applied": False,
            "answer_strategy": "lineage_guardrail_refusal",
            "_timing_ms": timing_ms,
        }

    if _insufficient_evidence(hits, resolved_mode):
        ref_score, threshold = _score_and_threshold(hits, resolved_mode)
        refusal_summary = (
            f"I retrieved {len(hits)} candidate chunk(s), but they are below confidence threshold "
            f"for mode={resolved_mode}."
            if hits
            else "No matching evidence was found for this request."
        )
        return {
            "query": q,
            "effective_query": effective_query,
            "refused": True,
            "reason": "insufficient_evidence",
            "detail": (
                f"Top retrieval score {ref_score:.4f} is below the "
                f"refusal threshold {threshold:.4f} for mode={resolved_mode}. Cannot provide a reliable answer."
            ) if hits else "No evidence retrieved for this query.",
            "prompt": "",
            "evidence": [],
            "prompt_version": None,
            "mode": resolved_mode,
            "rerank_requested": rerank,
            "reranked": reranked,
            "rerank_error": rerank_error,
            "retrieval_plan": plan,
            "source_file_hints": source_file_hints,
            "answer_text": None,
            "llm_requested": llm,
            "llm_used": False,
            "llm_model": llm_cfg["model_name"],
            "llm_error": "skipped_due_to_refusal" if llm else None,
            "relevancy_boost_requested": relevancy_boost,
            "relevancy_boost_applied": False,
            "answer_strategy": "refusal",
            "_timing_ms": timing_ms,
        }

    evidence_blocks_lines = []
    evidence_list = []
    for i, h in enumerate(hits, 1):
        cid = h.get("chunk_id", f"chunk_{i}")
        src = h.get("source_file", "unknown")
        nc = h.get("node_class", "")
        name = h.get("name", "")
        score = h.get("score", 0.0)
        text = h.get("text", "")
        prompt_text = _compact_text(str(text), max_chars=1200)
        evidence_blocks_lines.append(
            f"[{cid}]\nSource: {src}  |  {nc}: {name}  |  score={score:.4f}\n{prompt_text}\n"
        )
        evidence_list.append({
            "chunk_id": cid,
            "source_file": src,
            "node_class": nc,
            "name": name,
            "score": score,
            "cited_text": text,
        })

    focused_evidence = _select_query_focused_evidence(q, evidence_list, max_items=5)
    evidence_blocks = _compose_evidence_blocks(focused_evidence, max_items=5, max_chars=1200)

    try:
        from rag_system.prompts import get_prompt, render_prompt
        tmpl = get_prompt(prompt_name)
        filled_prompt = render_prompt(tmpl, query=q, evidence_blocks=evidence_blocks)
        prompt_version = tmpl.version
    except Exception as exc:
        logger.warning("Prompt load failed (%s); using inline fallback", exc)
        filled_prompt = (
            f"Answer using ONLY the evidence below. Cite sources as [chunk_id].\n\n"
            f"QUESTION: {q}\n\nEVIDENCE:\n{evidence_blocks}\n\nANSWER:"
        )
        prompt_version = "fallback"

    answer_text: Optional[str] = None
    llm_used = False
    resolved_llm_model: Optional[str] = llm_cfg["model_name"]
    llm_error: Optional[str] = None
    answer_strategy = ""
    relevancy_boost_applied = False
    if llm:
        generation_started_at = perf_counter()
        answer_text, llm_used, resolved_llm_model, llm_error = _generate_answer_openai(
            prompt=filled_prompt,
            model_override=llm_model,
            temperature=llm_temperature,
            max_tokens=llm_max_tokens,
        )
        timing_ms["generation_ms"] += _elapsed_ms(generation_started_at)
        if answer_text and llm_used:
            answer_strategy = "llm_primary"

        # Retry once with narrower evidence if the first call is empty.
        if (not answer_text or not llm_used) and evidence_list:
            retry_prompt = filled_prompt
            try:
                from rag_system.prompts import get_prompt, render_prompt

                retry_tmpl = get_prompt(prompt_name)
                compact_blocks = _compose_evidence_blocks(evidence_list, max_items=3, max_chars=500)
                retry_prompt = render_prompt(retry_tmpl, query=q, evidence_blocks=compact_blocks)
            except Exception:
                compact_blocks = _compose_evidence_blocks(evidence_list, max_items=3, max_chars=500)
                retry_prompt = (
                    f"Answer using ONLY the evidence below. Cite sources as [chunk_id].\n\n"
                    f"QUESTION: {q}\n\nEVIDENCE:\n{compact_blocks}\n\nANSWER:"
                )

            retry_started_at = perf_counter()
            retry_text, retry_used, retry_model, retry_error = _generate_answer_openai(
                prompt=retry_prompt,
                model_override=llm_model,
                temperature=llm_temperature,
                max_tokens=min(max(llm_max_tokens, 512), 1200),
            )
            timing_ms["generation_ms"] += _elapsed_ms(retry_started_at)
            if retry_text and retry_used:
                answer_text = retry_text
                llm_used = retry_used
                resolved_llm_model = retry_model
                llm_error = retry_error
                answer_strategy = "llm_retry"

        if (not answer_text or not str(answer_text).strip()) and evidence_list:
            answer_text = _build_extractive_fallback_answer(q, evidence_list)
            llm_error = f"{llm_error}; fallback_extractive" if llm_error else "fallback_extractive"
            answer_strategy = "fallback_extractive"
    elif evidence_list:
        answer_text = _build_extractive_fallback_answer(q, evidence_list)
        llm_error = "llm_disabled_extractive"
        answer_strategy = "fallback_extractive"

    if relevancy_boost and evidence_list and _needs_relevancy_boost(str(answer_text or ""), q):
        boosted_text: Optional[str] = None
        rewrite_error: Optional[str] = None

        if llm:
            rewrite_started_at = perf_counter()
            rewrite_text, rewrite_used, rewrite_model, rewrite_error = _maybe_rewrite_for_relevancy_openai(
                query=q,
                draft_answer=str(answer_text or ""),
                evidence=evidence_list,
                model_override=llm_model,
                temperature=llm_temperature,
                max_tokens=llm_max_tokens,
            )
            timing_ms["generation_ms"] += _elapsed_ms(rewrite_started_at)
            if rewrite_text and rewrite_used and not _needs_relevancy_boost(rewrite_text, q):
                boosted_text = rewrite_text
                llm_used = True
                resolved_llm_model = rewrite_model or resolved_llm_model
                answer_strategy = "llm_relevancy_rewrite"

        if not boosted_text:
            boosted_text = _build_grounded_relevance_answer(q, evidence_list)
            answer_strategy = "grounded_relevance_fallback"

        answer_text = boosted_text
        relevancy_boost_applied = True

        if rewrite_error:
            llm_error = f"{llm_error}; rewrite_failed={rewrite_error}" if llm_error else f"rewrite_failed={rewrite_error}"

    if not answer_strategy and answer_text:
        answer_strategy = "answer_ready"

    return {
        "query": q,
        "effective_query": effective_query,
        "refused": False,
        "reason": None,
        "prompt": filled_prompt,
        "answer_text": answer_text,
        "evidence": evidence_list,
        "prompt_version": prompt_version,
        "mode": resolved_mode,
        "rerank_requested": rerank,
        "reranked": reranked,
        "rerank_error": rerank_error,
        "retrieval_plan": plan,
        "source_file_hints": source_file_hints,
        "llm_requested": llm,
        "llm_used": llm_used,
        "llm_model": resolved_llm_model,
        "llm_error": llm_error,
        "relevancy_boost_requested": relevancy_boost,
        "relevancy_boost_applied": relevancy_boost_applied,
        "answer_strategy": answer_strategy,
        "_timing_ms": timing_ms,
    }


def _answer_legacy(
    *,
    q: str,
    k: int,
    mode: str,
    rerank: bool,
    prompt_name: str,
    llm: bool,
    relevancy_boost: bool,
    llm_model: Optional[str],
    llm_temperature: float,
    llm_max_tokens: int,
) -> Dict[str, Any]:
    semantic_payload = _maybe_answer_from_semantic_layer(
        q=q,
        k=k,
        mode=mode,
        llm=llm,
        llm_model=llm_model,
        llm_temperature=llm_temperature,
        llm_max_tokens=llm_max_tokens,
    )
    if semantic_payload is not None:
        semantic_payload["orchestration_mode"] = "semantic_primary"
        return semantic_payload

    retrieval = _retrieve_hits(
        q=q,
        k=k,
        node_class=None,
        mode=mode,
        rerank=rerank,
        use_planner=False,
        planner_llm_model=None,
        intent_llm_model=llm_model,
    )
    hits = retrieval["hits"]
    reranked = retrieval["reranked"]
    rerank_error = retrieval["rerank_error"]
    plan = retrieval["plan"]
    resolved_mode = retrieval["resolved_mode"]
    effective_query = retrieval["effective_query"]
    source_file_hints = retrieval.get("source_file_hints") or []

    payload = _build_answer_payload_from_retrieval(
        q=q,
        rerank=rerank,
        prompt_name=prompt_name,
        llm=llm,
        relevancy_boost=relevancy_boost,
        llm_model=llm_model,
        llm_temperature=llm_temperature,
        llm_max_tokens=llm_max_tokens,
        hits=hits,
        reranked=reranked,
        rerank_error=rerank_error,
        plan=plan,
        resolved_mode=resolved_mode,
        effective_query=effective_query,
        source_file_hints=source_file_hints,
        retrieval_timing_ms=retrieval.get("timing_ms"),
    )
    payload["orchestration_mode"] = "legacy"
    return payload


def _validate_graph_answer_payload(payload: Dict[str, Any], llm_requested: bool) -> tuple[str, Optional[str]]:
    if payload.get("refused"):
        return "retry", "insufficient_evidence"

    evidence = payload.get("evidence") or []
    if not evidence:
        return "retry", "no_evidence"

    if llm_requested:
        answer_text = str(payload.get("answer_text") or "").strip()
        if not answer_text:
            return "retry", "empty_answer"
        if "[" not in answer_text or "]" not in answer_text:
            return "retry", "missing_citations"

    return "pass", None


def _answer_graph(
    *,
    q: str,
    k: int,
    mode: str,
    rerank: bool,
    prompt_name: str,
    llm: bool,
    relevancy_boost: bool,
    llm_model: Optional[str],
    llm_temperature: float,
    llm_max_tokens: int,
    graph_max_retries: Optional[int],
) -> Dict[str, Any]:
    semantic_payload = _maybe_answer_from_semantic_layer(
        q=q,
        k=k,
        mode=mode,
        llm=llm,
        llm_model=llm_model,
        llm_temperature=llm_temperature,
        llm_max_tokens=llm_max_tokens,
    )
    if semantic_payload is not None:
        semantic_payload["orchestration_mode"] = "semantic_primary"
        semantic_payload["graph"] = {
            "retry_count": 0,
            "max_retries": int(graph_max_retries or 0),
            "validator_decision": "pass",
            "validator_reason": "semantic_primary_routed",
        }
        return semantic_payload

    from rag_system.graph import AnswerGraphCallbacks, run_answer_graph

    default_retries = int(os.getenv("GRAPH_MAX_RETRIES", "2") or 2)
    max_retries = default_retries if graph_max_retries is None else max(0, int(graph_max_retries))

    def _planner_callback(state: Dict[str, Any]) -> Dict[str, Any]:
        retrieval = _retrieve_hits(
            q=str(state["query"]),
            k=int(state["k"]),
            node_class=None,
            mode=str(state["mode"]),
            rerank=bool(state["rerank"]),
            use_planner=False,
            planner_llm_model=None,
            intent_llm_model=state.get("llm_model"),
        )
        return {
            "hits": retrieval["hits"],
            "reranked": retrieval["reranked"],
            "rerank_error": retrieval["rerank_error"],
            "plan": retrieval["plan"],
            "resolved_mode": retrieval["resolved_mode"],
            "effective_query": retrieval["effective_query"],
            "source_file_hints": retrieval.get("source_file_hints") or [],
            "retrieval_timing_ms": retrieval.get("timing_ms") or {},
        }

    def _executor_callback(state: Dict[str, Any]) -> Dict[str, Any]:
        payload = _build_answer_payload_from_retrieval(
            q=str(state["query"]),
            rerank=bool(state["rerank"]),
            prompt_name=str(state["prompt_name"]),
            llm=bool(state["llm"]),
            relevancy_boost=bool(state.get("relevancy_boost", True)),
            llm_model=state.get("llm_model"),
            llm_temperature=float(state["llm_temperature"]),
            llm_max_tokens=int(state["llm_max_tokens"]),
            hits=list(state.get("hits") or []),
            reranked=bool(state.get("reranked", False)),
            rerank_error=state.get("rerank_error"),
            plan=dict(state.get("plan") or {}),
            resolved_mode=str(state.get("resolved_mode") or state["mode"]),
            effective_query=str(state.get("effective_query") or state["query"]),
            source_file_hints=list(state.get("source_file_hints") or []),
            retrieval_timing_ms=dict(state.get("retrieval_timing_ms") or {}),
        )
        return {"answer_payload": payload}

    def _validator_callback(state: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(state.get("answer_payload") or {})
        decision, reason = _validate_graph_answer_payload(payload, llm_requested=bool(state.get("llm", False)))

        updates: Dict[str, Any] = {
            "validator_decision": decision,
            "validator_reason": reason,
        }
        if decision == "retry":
            updates["retry_count"] = int(state.get("retry_count", 0) or 0) + 1
            if reason == "insufficient_evidence":
                updates["mode"] = "hybrid"
        return updates

    initial_state: Dict[str, Any] = {
        "query": q,
        "k": k,
        "mode": mode,
        "rerank": rerank,
        "prompt_name": prompt_name,
        "llm": llm,
        "relevancy_boost": relevancy_boost,
        "llm_model": llm_model,
        "llm_temperature": llm_temperature,
        "llm_max_tokens": llm_max_tokens,
        "retry_count": 0,
        "max_retries": max_retries,
        "validator_decision": "pass",
    }

    final_state = run_answer_graph(
        initial_state=initial_state,
        callbacks=AnswerGraphCallbacks(
            planner=_planner_callback,
            executor=_executor_callback,
            validator=_validator_callback,
        ),
    )

    payload = dict(final_state.get("answer_payload") or {})
    if not payload:
        payload = _answer_legacy(
            q=q,
            k=k,
            mode=mode,
            rerank=rerank,
            prompt_name=prompt_name,
            llm=llm,
            relevancy_boost=relevancy_boost,
            llm_model=llm_model,
            llm_temperature=llm_temperature,
            llm_max_tokens=llm_max_tokens,
        )
        payload["orchestration_mode"] = "legacy_fallback"
    else:
        payload["orchestration_mode"] = "graph"
        payload["graph"] = {
            "retry_count": int(final_state.get("retry_count", 0) or 0),
            "max_retries": max_retries,
            "validator_decision": final_state.get("validator_decision"),
            "validator_reason": final_state.get("validator_reason"),
        }

    return payload


@app.get("/answer", summary="Citation-backed answer generation")
def answer(
    q: str = Query(..., description="Natural-language question"),
    k: int = Query(5, ge=1, le=20, description="Evidence chunks to retrieve"),
    mode: str = Query(
        "hybrid",
        description="Retrieval mode: hybrid | vector | bm25 | auto",
        pattern="^(hybrid|vector|bm25|auto)$",
    ),
    rerank: bool = Query(False, description="Apply cross-encoder reranker before answering"),
    prompt_name: str = Query(
        "answer_with_citations",
        description="Prompt template to use (see GET /prompts)",
    ),
    llm: bool = Query(True, description="Generate final answer text using OpenAI"),
    relevancy_boost: bool = Query(
        True,
        description="Apply query-focused grounded rewrite/fallback when the draft answer is empty or weak.",
    ),
    llm_model: Optional[str] = Query(None, description="Optional OpenAI model override for this request"),
    llm_temperature: float = Query(0.0, ge=0.0, le=1.5, description="Sampling temperature for OpenAI generation"),
    llm_max_tokens: int = Query(600, ge=64, le=4000, description="Max output tokens for OpenAI generation"),
    use_graph: Optional[bool] = Query(
        None,
        description="Use LangGraph planner/executor/validator orchestration for answering.",
    ),
    graph_max_retries: Optional[int] = Query(
        None,
        ge=0,
        le=5,
        description="Optional graph retry limit override.",
    ),
) -> Dict[str, Any]:
    request_started_at = perf_counter()
    if _kb is None or not _kb._built:
        raise HTTPException(
            status_code=503,
            detail="Knowledge base not built yet. POST /ingest or POST /connect first.",
        )

    normalized_use_graph = _normalize_optional_bool(use_graph)
    normalized_graph_max_retries = _normalize_optional_int(graph_max_retries)

    mode_name = _resolve_answer_orchestration_mode(normalized_use_graph)
    if mode_name == "graph":
        try:
            payload = _answer_graph(
                q=q,
                k=k,
                mode=mode,
                rerank=rerank,
                prompt_name=prompt_name,
                llm=llm,
                relevancy_boost=relevancy_boost,
                llm_model=llm_model,
                llm_temperature=llm_temperature,
                llm_max_tokens=llm_max_tokens,
                graph_max_retries=normalized_graph_max_retries,
            )
        except Exception as exc:
            logger.warning("Graph orchestration failed, falling back to legacy: %s", exc)
            payload = _answer_legacy(
                q=q,
                k=k,
                mode=mode,
                rerank=rerank,
                prompt_name=prompt_name,
                llm=llm,
                relevancy_boost=relevancy_boost,
                llm_model=llm_model,
                llm_temperature=llm_temperature,
                llm_max_tokens=llm_max_tokens,
            )
            payload["orchestration_mode"] = "legacy_fallback"
            payload["graph_error"] = str(exc)
    else:
        payload = _answer_legacy(
            q=q,
            k=k,
            mode=mode,
            rerank=rerank,
            prompt_name=prompt_name,
            llm=llm,
            relevancy_boost=relevancy_boost,
            llm_model=llm_model,
            llm_temperature=llm_temperature,
            llm_max_tokens=llm_max_tokens,
        )

    timing_ms = dict(payload.pop("_timing_ms", {}) if isinstance(payload.get("_timing_ms"), dict) else {})
    timing_ms["total_ms"] = _elapsed_ms(request_started_at)
    if payload.get("mode") == "semantic":
        timing_ms.setdefault("semantic_ms", 0)
        timing_ms.setdefault("secondary_retrieval_ms", 0)
    else:
        timing_ms.setdefault("retrieval_ms", 0)
        timing_ms.setdefault("rerank_ms", 0)
    timing_ms.setdefault("generation_ms", 0)

    trace = _new_trace_payload(
        endpoint="/answer",
        query=q,
        intent=str(payload.get("retrieval_plan", {}).get("intent") or ""),
        workflow_hint=(payload.get("source_file_hints") or [""])[0] if payload.get("source_file_hints") else "",
        orchestration_mode=str(payload.get("orchestration_mode") or ""),
    )
    payload["trace"] = trace
    payload["telemetry"] = {
        "timing_ms": timing_ms,
        "usage": _answer_usage_telemetry(payload),
        "events": _answer_event_log(payload),
    }
    return payload


@app.get("/prompts", summary="List available prompt templates and their versions")
def list_prompts_endpoint() -> Dict[str, Any]:
    """Return all loaded prompt names and versions from prompts/prompts.yml."""
    try:
        from rag_system.prompts import list_prompts
        return {"prompts": list_prompts()}
    except Exception as exc:
        return {"error": str(exc), "prompts": {}}


@app.get("/chat/ui", summary="Open web chat UI")
def chat_ui() -> FileResponse:
    if not _CHAT_UI_FILE.exists():
        raise HTTPException(status_code=500, detail=f"Chat UI not found: {_CHAT_UI_FILE}")
    return FileResponse(_CHAT_UI_FILE)


@app.get("/agent/context", summary="Get agent capability + indexed corpus context snapshot")
def agent_context(query: str = Query("", description="Optional user query for context routing")) -> Dict[str, Any]:
    if (_kb is None or not _kb._built) and os.getenv("AUTO_CONNECT", "").lower() not in {"1", "true", "yes"}:
        # Best-effort connect for convenience; payload still returns gracefully if unavailable.
        _run_connect()
    payload = _build_context_agent_payload(query_text=query or "what can you do?")
    payload["orchestration_mode"] = "agent_context"
    return payload


@app.post("/chat/sessions", summary="Create a chat session")
def create_chat_session() -> Dict[str, Any]:
    session = _create_chat_session()
    return {
        "session_id": session["session_id"],
        "created_at": session["created_at"],
        "updated_at": session["updated_at"],
        "summary": session.get("summary") or "",
        "message_count": 0,
    }


@app.get("/chat/sessions/{session_id}", summary="Get chat session metadata")
def get_chat_session(session_id: str) -> Dict[str, Any]:
    session = _get_chat_session(session_id)
    return {
        "session_id": session["session_id"],
        "created_at": session["created_at"],
        "updated_at": session["updated_at"],
        "summary": session.get("summary") or "",
        "message_count": len(session.get("messages") or []),
    }


@app.put("/chat/sessions/{session_id}/summary", summary="Replace compressed session memory summary")
def update_chat_session_summary(session_id: str, body: ChatSummaryUpdateRequest) -> Dict[str, Any]:
    return _set_chat_session_summary(session_id=session_id, summary=body.summary)


@app.delete("/chat/sessions/{session_id}/summary", summary="Clear compressed session memory summary")
def clear_chat_session_summary(session_id: str) -> Dict[str, Any]:
    return _set_chat_session_summary(session_id=session_id, summary="")


@app.get("/chat/sessions/{session_id}/messages", summary="Get chat transcript")
def get_chat_messages(session_id: str) -> Dict[str, Any]:
    session = _get_chat_session(session_id)
    return {
        "session_id": session["session_id"],
        "created_at": session["created_at"],
        "updated_at": session["updated_at"],
        "summary": session.get("summary") or "",
        "messages": list(session.get("messages") or []),
    }


@app.post("/chat/sessions/{session_id}/messages", summary="Chat with follow-up support")
def chat_message(session_id: str, body: ChatMessageRequest) -> Dict[str, Any]:
    session = _get_chat_session(session_id)
    user_message = body.message.strip()

    if _is_capability_inventory_prompt(user_message):
        if _kb is None or not _kb._built:
            _run_connect()

        user_event = _append_chat_message(
            session_id=session_id,
            role="user",
            text=user_message,
            meta={
                "contextual_query": user_message,
                "history_turns_used": body.history_turns,
                "context_message_count": 0,
                "subflow": {"subflow": "context_inventory", "intent": "capabilities"},
            },
        )

        payload = _build_context_agent_payload(query_text=user_message)
        payload["query_original"] = user_message
        payload["query_contextualized"] = user_message
        payload["chat_context_message_count"] = 0
        payload["chat_subflow"] = {"subflow": "context_inventory", "intent": "capabilities"}
        payload["session_summary"] = session.get("summary") or ""
        payload["orchestration_mode"] = "agent_context"

        assistant_event = _append_chat_message(
            session_id=session_id,
            role="assistant",
            text=str(payload.get("answer_text") or ""),
            meta={
                "refused": False,
                "reason": None,
                "strategy": payload.get("answer_strategy"),
                "llm_used": False,
                "llm_error": payload.get("llm_error"),
                "query_original": user_message,
                "query_contextualized": user_message,
                "subflow": payload.get("chat_subflow"),
            },
        )

        return {
            "session_id": session_id,
            "user_message": user_event,
            "assistant_message": assistant_event,
            "answer": payload,
        }

    if _kb is None or not _kb._built:
        # Conversational endpoint attempts auto-connect for better UX.
        _run_connect()
        if _kb is None or not _kb._built:
            raise HTTPException(
                status_code=503,
                detail="Knowledge base not built yet. POST /ingest or POST /connect first.",
            )

    contextual_query, context_messages = _compose_chat_query(user_message, session, body.history_turns)
    subflow = _chat_tool_subflow_overrides(
        user_message=user_message,
        mode=body.mode,
        rerank=body.rerank,
        k=body.k,
        prompt_name=body.prompt_name,
        llm_model=body.llm_model,
    )

    user_event = _append_chat_message(
        session_id=session_id,
        role="user",
        text=user_message,
        meta={
            "contextual_query": contextual_query,
            "history_turns_used": body.history_turns,
            "context_message_count": len(context_messages),
            "subflow": subflow,
        },
    )

    normalized_use_graph = _normalize_optional_bool(body.use_graph)
    normalized_graph_max_retries = _normalize_optional_int(body.graph_max_retries)
    mode_name = _resolve_answer_orchestration_mode(normalized_use_graph)

    if mode_name == "graph":
        try:
            payload = _answer_graph(
                q=contextual_query,
                k=int(subflow["k"]),
                mode=str(subflow["mode"]),
                rerank=bool(subflow["rerank"]),
                prompt_name=str(subflow["prompt_name"]),
                llm=body.llm,
                relevancy_boost=body.relevancy_boost,
                llm_model=body.llm_model,
                llm_temperature=body.llm_temperature,
                llm_max_tokens=body.llm_max_tokens,
                graph_max_retries=normalized_graph_max_retries,
            )
        except Exception as exc:
            logger.warning("Graph chat orchestration failed, falling back to legacy: %s", exc)
            payload = _answer_legacy(
                q=contextual_query,
                k=int(subflow["k"]),
                mode=str(subflow["mode"]),
                rerank=bool(subflow["rerank"]),
                prompt_name=str(subflow["prompt_name"]),
                llm=body.llm,
                relevancy_boost=body.relevancy_boost,
                llm_model=body.llm_model,
                llm_temperature=body.llm_temperature,
                llm_max_tokens=body.llm_max_tokens,
            )
            payload["orchestration_mode"] = "legacy_fallback"
            payload["graph_error"] = str(exc)
    else:
        payload = _answer_legacy(
            q=contextual_query,
            k=int(subflow["k"]),
            mode=str(subflow["mode"]),
            rerank=bool(subflow["rerank"]),
            prompt_name=str(subflow["prompt_name"]),
            llm=body.llm,
            relevancy_boost=body.relevancy_boost,
            llm_model=body.llm_model,
            llm_temperature=body.llm_temperature,
            llm_max_tokens=body.llm_max_tokens,
        )

    payload["query_original"] = user_message
    payload["query_contextualized"] = contextual_query
    payload["chat_context_message_count"] = len(context_messages)
    payload["chat_subflow"] = subflow
    payload["session_summary"] = session.get("summary") or ""

    assistant_text = str(payload.get("answer_text") or "").strip()
    if not assistant_text:
        if payload.get("refused"):
            assistant_text = str(payload.get("detail") or "I could not answer confidently from available evidence.").strip()
        else:
            assistant_text = "I could not generate a response, but I captured your question. Please retry or ask with more workflow specifics."

    assistant_event = _append_chat_message(
        session_id=session_id,
        role="assistant",
        text=assistant_text,
        meta={
            "refused": bool(payload.get("refused")),
            "reason": payload.get("reason"),
            "strategy": payload.get("answer_strategy"),
            "llm_used": bool(payload.get("llm_used")),
            "llm_error": payload.get("llm_error"),
            "query_original": user_message,
            "query_contextualized": contextual_query,
            "subflow": subflow,
        },
    )

    if payload.get("answer_text") is None or not str(payload.get("answer_text") or "").strip():
        payload["answer_text"] = assistant_text

    return {
        "session_id": session_id,
        "user_message": user_event,
        "assistant_message": assistant_event,
        "answer": payload,
    }
