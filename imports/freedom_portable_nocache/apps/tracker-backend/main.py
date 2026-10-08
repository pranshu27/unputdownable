"""Portfolio Tracker persistence backend.

Stores the complete tracker state as a single JSONB blob in PostgreSQL.
Supports optimistic concurrency so unsynced local edits are not silently lost.

Endpoints
---------
GET  /api/health      liveness
GET  /api/state       return stored tracker state + version metadata
PUT  /api/state       save full tracker state with optional expected_version
"""

from __future__ import annotations

import json
import logging
import os
import socket
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tracker_backend")

# Reach the existing pgvector container via Docker host bridge on Windows
POSTGRES_URL = os.getenv(
    "POSTGRES_URL",
    "postgresql://raguser:ragpass@host.docker.internal:5433/ragdb",
)

FALLBACK_STATE_FILE = Path(os.getenv("TRACKER_FALLBACK_STATE_FILE", "/tmp/tracker_state.json"))

_workspace_root_env = os.getenv("TRACKER_WORKSPACE_ROOT")
if _workspace_root_env:
    WORKSPACE_ROOT = Path(_workspace_root_env).resolve()
else:
    _main_path = Path(__file__).resolve()
    WORKSPACE_ROOT = _main_path.parents[2] if len(_main_path.parents) > 2 else _main_path.parent
PROJECT_LLD_REGISTRY: dict[int, dict[str, Any]] = {
    1: {
        "title": "P1 - Production-Grade RAG System LLD",
        "path": WORKSPACE_ROOT / "rag-system" / "SYSTEM_E2E_FLOW.md",
    },
    2: {
        "title": "P2 - Local AI Assistant + Benchmarking LLD",
        "path": WORKSPACE_ROOT / "documents" / "lld" / "P2_LOCAL_BENCHMARKING_LLD.md",
    },
    3: {
        "title": "P3 - Observability and Monitoring LLD",
        "path": WORKSPACE_ROOT / "documents" / "lld" / "P3_OBSERVABILITY_LLD.md",
    },
    4: {
        "title": "P4 - Fine-Tuning with Measurable Gain LLD",
        "path": WORKSPACE_ROOT / "documents" / "lld" / "P4_FINE_TUNING_LLD.md",
    },
    5: {
        "title": "P5 - Realtime Multimodal App LLD",
        "path": WORKSPACE_ROOT / "documents" / "lld" / "P5_REALTIME_MULTIMODAL_LLD.md",
    },
}


def _conn() -> psycopg.Connection:
    try:
        return psycopg.connect(POSTGRES_URL, autocommit=True)
    except psycopg.OperationalError as exc:
        if "host.docker.internal" not in POSTGRES_URL.lower():
            raise
        if "Network is unreachable" not in str(exc):
            raise

        ipv4_host = socket.gethostbyname("host.docker.internal")
        logger.warning("Retrying PostgreSQL connection via IPv4 hostaddr=%s", ipv4_host)
        return psycopg.connect(POSTGRES_URL, autocommit=True, hostaddr=ipv4_host)


def _workspace_rel_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(WORKSPACE_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path.resolve()).replace("\\", "/")


def _to_iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None


def _state_payload(row: tuple[Any, ...] | None) -> dict[str, Any]:
    if not row:
        return {"data": {}, "version": 0, "updated_at": None}
    return {
        "data": row[0] or {},
        "version": int(row[1] or 0),
        "updated_at": _to_iso(row[2]),
    }


def _read_fallback_state() -> dict[str, Any]:
    if not FALLBACK_STATE_FILE.exists():
        return {"data": {}, "version": 0, "updated_at": None}
    try:
        payload = json.loads(FALLBACK_STATE_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to read fallback state file: %s", exc)
        return {"data": {}, "version": 0, "updated_at": None}
    if not isinstance(payload, dict):
        return {"data": {}, "version": 0, "updated_at": None}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    version = int(payload.get("version") or 0)
    updated_at = payload.get("updated_at") if isinstance(payload.get("updated_at"), str) else None
    return {"data": data, "version": version, "updated_at": updated_at}


def _save_fallback_state(data: dict[str, Any], expected_version: int | None) -> dict[str, Any] | JSONResponse:
    current = _read_fallback_state()
    current_version = int(current.get("version") or 0)
    if expected_version is not None and expected_version != current_version:
        return JSONResponse(
            status_code=409,
            content={
                "status": "conflict",
                "detail": "Version mismatch",
                "server": current,
            },
        )

    updated_at = datetime.utcnow().isoformat() + "Z"
    next_payload = {
        "data": data,
        "version": current_version + 1,
        "updated_at": updated_at,
    }
    FALLBACK_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    FALLBACK_STATE_FILE.write_text(json.dumps(next_payload), encoding="utf-8")
    return {
        "status": "saved",
        "version": next_payload["version"],
        "updated_at": updated_at,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tracker schema + table on startup if they don't exist."""
    try:
        with _conn() as conn:
            conn.execute("CREATE SCHEMA IF NOT EXISTS tracker")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tracker.state (
                    id         TEXT PRIMARY KEY DEFAULT 'default',
                    data       JSONB NOT NULL,
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    version    BIGINT NOT NULL DEFAULT 1
                )
                """
            )
            # Backward compatibility for older table shape.
            conn.execute(
                "ALTER TABLE tracker.state "
                "ADD COLUMN IF NOT EXISTS version BIGINT NOT NULL DEFAULT 1"
            )
        logger.info("tracker.state table ready")
    except Exception as exc:
        logger.warning("DB init failed (will retry on request): %s", exc)
    yield


app = FastAPI(title="Tracker API", version="1.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tightened in prod; fine for local dev
    allow_methods=["GET", "PUT", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/project-lld/{project_id}")
def get_project_lld(project_id: int) -> dict[str, Any]:
    record = PROJECT_LLD_REGISTRY.get(project_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Unknown project_id: {project_id}")

    lld_path = Path(record["path"])
    if not lld_path.exists():
        return {
            "project_id": project_id,
            "title": record["title"],
            "path": _workspace_rel_path(lld_path),
            "exists": False,
            "updated_at": None,
            "content": "# LLD not available yet\n\nThis project does not have a committed LLD file yet.",
        }

    try:
        content = lld_path.read_text(encoding="utf-8", errors="replace")
        stat = lld_path.stat()
        updated_at = datetime.fromtimestamp(stat.st_mtime).isoformat()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read LLD: {exc}") from exc

    return {
        "project_id": project_id,
        "title": record["title"],
        "path": _workspace_rel_path(lld_path),
        "exists": True,
        "updated_at": updated_at,
        "content": content,
    }


@app.get("/api/state")
def get_state() -> dict[str, Any]:
    """Return stored state with version metadata.

    Shape:
        {"data": <dict>, "version": <int>, "updated_at": <iso-or-null>}
    """
    try:
        with _conn() as conn:
            row = conn.execute(
                "SELECT data, version, updated_at FROM tracker.state WHERE id = 'default'"
            ).fetchone()
        return _state_payload(row)
    except Exception as exc:
        logger.error("GET /api/state failed: %s", exc)
        return _read_fallback_state()


@app.put("/api/state")
async def put_state(request: Request):
    """Persist tracker state with optional optimistic concurrency.

    Accepted request formats:
    - Legacy: { ...state }
    - Versioned: {"data": { ...state }, "expected_version": <int>}
    """
    body = await request.json()
    if not isinstance(body, dict):
        return JSONResponse(
            status_code=400,
            content={"status": "error", "detail": "JSON object required"},
        )

    expected_version = body.get("expected_version") if "expected_version" in body else None
    if expected_version is not None and (not isinstance(expected_version, int) or expected_version < 0):
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "detail": "expected_version must be a non-negative integer",
            },
        )

    payload = body.get("data") if "data" in body and isinstance(body.get("data"), dict) else body
    encoded = json.dumps(payload)

    try:
        with _conn() as conn:
            # Legacy blind upsert (kept for compatibility).
            if expected_version is None:
                row = conn.execute(
                    """
                    INSERT INTO tracker.state (id, data, updated_at, version)
                    VALUES ('default', %s::jsonb, NOW(), 1)
                    ON CONFLICT (id) DO UPDATE
                        SET data = EXCLUDED.data,
                            updated_at = NOW(),
                            version = tracker.state.version + 1
                    RETURNING version, updated_at
                    """,
                    (encoded,),
                ).fetchone()
                return {
                    "status": "saved",
                    "version": int(row[0]),
                    "updated_at": _to_iso(row[1]),
                }

            row = conn.execute(
                """
                UPDATE tracker.state
                   SET data = %s::jsonb,
                       updated_at = NOW(),
                       version = version + 1
                 WHERE id = 'default'
                   AND version = %s
             RETURNING version, updated_at
                """,
                (encoded, expected_version),
            ).fetchone()

            # First write when caller expects an empty server state.
            if row is None and expected_version == 0:
                row = conn.execute(
                    """
                    INSERT INTO tracker.state (id, data, updated_at, version)
                    VALUES ('default', %s::jsonb, NOW(), 1)
                    ON CONFLICT (id) DO NOTHING
                    RETURNING version, updated_at
                    """,
                    (encoded,),
                ).fetchone()

            if row is None:
                current = conn.execute(
                    "SELECT data, version, updated_at FROM tracker.state WHERE id = 'default'"
                ).fetchone()
                return JSONResponse(
                    status_code=409,
                    content={
                        "status": "conflict",
                        "detail": "Version mismatch",
                        "server": _state_payload(current),
                    },
                )

        return {
            "status": "saved",
            "version": int(row[0]),
            "updated_at": _to_iso(row[1]),
        }
    except Exception as exc:
        logger.error("PUT /api/state failed: %s", exc)
        logger.warning("Falling back to local file persistence: %s", FALLBACK_STATE_FILE)
        return _save_fallback_state(payload, expected_version)
