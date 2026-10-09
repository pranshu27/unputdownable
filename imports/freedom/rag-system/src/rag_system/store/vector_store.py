"""Vector stores — in-memory (offline/tests) and pgvector (production).

Interface:
    upsert(chunks, vectors) — index chunks + their embedding vectors.
    search(query_vector, k) — return top-k hits by cosine similarity.
    count() — number of indexed chunks.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Sequence

from rag_system.chunking import Chunk

logger = logging.getLogger(__name__)


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    # Vectors are L2-normalized; dot product == cosine similarity.
    return sum(x * y for x, y in zip(a, b))


def _hit(chunk: Chunk, score: float) -> Dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "source_file": chunk.source_file,
        "node_class": chunk.node_class,
        "name": chunk.name,
        "score": round(float(score), 4),
        "text": chunk.text,
        "metadata": chunk.metadata,
    }


class VectorStore(ABC):
    """Abstract interface for chunk-vector indexing and retrieval backends."""

    dim: int

    @abstractmethod
    def upsert(self, chunks: List[Chunk], vectors: List[List[float]]) -> None:
        """Insert or update chunk rows with aligned embedding vectors."""
        ...

    @abstractmethod
    def search(self, query_vector: List[float], k: int = 5) -> List[Dict[str, Any]]:
        """Return top-k retrieval hits ordered by descending similarity."""
        ...

    @abstractmethod
    def count(self) -> int:
        """Return the number of indexed chunks in the store."""
        ...


class InMemoryVectorStore(VectorStore):
    """Brute-force cosine search held in process. Deterministic, dependency-free."""

    def __init__(self, dim: int) -> None:
        """Initialize an in-process storage buffer for chunks and vectors."""
        self.dim = dim
        self._chunks: List[Chunk] = []
        self._vectors: List[List[float]] = []

    def upsert(self, chunks: List[Chunk], vectors: List[List[float]]) -> None:
        """Append chunk-vector pairs to the in-memory index."""
        self._chunks.extend(chunks)
        self._vectors.extend(vectors)

    def search(self, query_vector: List[float], k: int = 5) -> List[Dict[str, Any]]:
        """Run brute-force cosine scoring and return the highest scoring hits."""
        scored = [
            (_cosine(query_vector, vec), chunk)
            for vec, chunk in zip(self._vectors, self._chunks)
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [_hit(chunk, score) for score, chunk in scored[:k] if score > 0]

    def count(self) -> int:
        """Return the number of in-memory chunk records."""
        return len(self._chunks)


class PgVectorStore(VectorStore):
    """Postgres + pgvector store. Cosine nearest-neighbour search runs in the DB.

    Schema (rag.rag_chunks):
        chunk_id text PK, source_file, node_class, name, text, metadata jsonb,
        embedding vector(<dim>)
    with an IVFFlat cosine index.

    Notes (from live validation against Azure managed Postgres):
    - Cannot CREATE EXTENSION as non-admin; skips if extension already present.
    - Uses own schema ``rag`` (cannot write to public schema as dev_user).
    - Batched executemany to avoid per-row round-trip latency over VPN.
    """

    def __init__(
        self, dsn: str, dim: int, table: str = "rag_chunks", schema: str = "rag"
    ) -> None:
        """Connect to PostgreSQL/pgvector and ensure storage schema/indexes exist."""
        import psycopg
        from pgvector.psycopg import register_vector

        self.dim = dim
        self.schema = schema
        self.table_name = table
        self.table = f"{schema}.{table}"
        self._dsn = dsn
        self._psycopg = psycopg
        self._register_vector = register_vector
        self._conn = psycopg.connect(dsn, autocommit=True)
        self._ensure_extension()
        register_vector(self._conn)
        self._ensure_schema()

    def _reconnect(self) -> None:
        """Re-open the psycopg connection and re-register vector adapters."""
        self._conn = self._psycopg.connect(self._dsn, autocommit=True)
        self._register_vector(self._conn)

    def _ensure_connection(self) -> None:
        """Ensure a live connection object is available before issuing SQL."""
        if getattr(self, "_conn", None) is None:
            self._reconnect()
            return
        if self._conn.closed:
            self._reconnect()

    def _execute(self, sql: str, params: Any = None):
        """Execute SQL with one reconnect retry on connection-closed errors."""
        for attempt in range(2):
            self._ensure_connection()
            try:
                if params is None:
                    return self._conn.execute(sql)
                return self._conn.execute(sql, params)
            except self._psycopg.OperationalError as exc:
                if attempt == 0 and (self._conn.closed or "connection is closed" in str(exc).lower()):
                    logger.warning("PgVectorStore connection closed; reconnecting and retrying query")
                    self._reconnect()
                    continue
                raise
        raise RuntimeError("Unexpected execute retry flow")

    @staticmethod
    def _env_true(name: str) -> bool:
        """Interpret environment variables using common truthy string values."""
        return os.getenv(name, "").strip().lower() in ("1", "true", "yes")

    def _existing_embedding_dim(self) -> int | None:
        """Return existing embedding vector dimensionality for the target table, if present."""
        row = self._execute(
            "SELECT to_regclass(%s)", (self.table,)
        ).fetchone()
        if not row or row[0] is None:
            return None

        row = self._execute(
            """
            SELECT format_type(a.atttypid, a.atttypmod)
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = %s
              AND c.relname = %s
              AND a.attname = 'embedding'
              AND a.attnum > 0
              AND NOT a.attisdropped
            """,
            (self.schema, self.table_name),
        ).fetchone()
        if not row or not row[0]:
            return None

        match = re.search(r"vector\((\d+)\)", str(row[0]))
        return int(match.group(1)) if match else None

    def _ensure_extension(self) -> None:
        """Ensure pgvector extension exists before vector columns are used."""
        exists = self._execute(
            "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
        if exists:
            return
        self._execute("CREATE EXTENSION IF NOT EXISTS vector")

    def _ensure_schema(self) -> None:
        """Create table/indexes and validate embedding dimension compatibility."""
        self._execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")

        existing_dim = self._existing_embedding_dim()
        if existing_dim is not None and existing_dim != self.dim:
            if self._env_true("RAG_RECREATE_TABLE_ON_DIM_MISMATCH"):
                logger.warning(
                    "Embedding dim mismatch on %s (existing=%s, expected=%s); recreating table",
                    self.table,
                    existing_dim,
                    self.dim,
                )
                self._execute(f"DROP TABLE IF EXISTS {self.table}")
            else:
                raise RuntimeError(
                    f"Embedding dimension mismatch for {self.table}: existing {existing_dim}, expected {self.dim}. "
                    "Set RAG_RECREATE_TABLE_ON_DIM_MISMATCH=true to recreate the table."
                )

        self._execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.table} (
                chunk_id    text PRIMARY KEY,
                source_file text,
                node_class  text,
                name        text,
                text        text,
                metadata    jsonb,
                embedding   vector({self.dim})
            )
            """
        )
        idx = f"{self.schema}_rag_chunks_emb_idx"
        try:
            self._execute(
                f"CREATE INDEX IF NOT EXISTS {idx} "
                f"ON {self.table} USING ivfflat (embedding vector_cosine_ops) "
                f"WITH (lists = 100)"
            )
        except Exception:
            pass  # index is optional; brute force still works

        # BM25 support: add tsvector column + GIN index if not present
        col_exists = self._execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema=%s AND table_name='rag_chunks' AND column_name='fts'",
            (self.schema,)
        ).fetchone()
        if not col_exists:
            try:
                self._execute(
                    f"ALTER TABLE {self.table} ADD COLUMN fts tsvector"
                    f" GENERATED ALWAYS AS (to_tsvector('english', coalesce(text,''))) STORED"
                )
                self._execute(
                    f"CREATE INDEX IF NOT EXISTS {self.schema}_rag_chunks_fts_idx "
                    f"ON {self.table} USING GIN (fts)"
                )
                logger.info("Added FTS column and GIN index to %s", self.table)
            except Exception as exc:
                logger.warning("FTS column creation failed (non-fatal): %s", exc)

    def upsert(self, chunks: List[Chunk], vectors: List[List[float]]) -> None:
        """Upsert chunk rows and embeddings in PostgreSQL using batched executemany."""
        import numpy as np

        rows = [
            (
                c.chunk_id, c.source_file, c.node_class, c.name, c.text,
                json.dumps(c.metadata), np.array(v, dtype="float32"),
            )
            for c, v in zip(chunks, vectors)
        ]
        with self._conn.cursor() as cur:
            cur.executemany(
                f"""
                INSERT INTO {self.table}
                    (chunk_id, source_file, node_class, name, text, metadata, embedding)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (chunk_id) DO UPDATE SET
                    source_file = EXCLUDED.source_file,
                    node_class  = EXCLUDED.node_class,
                    name        = EXCLUDED.name,
                    text        = EXCLUDED.text,
                    metadata    = EXCLUDED.metadata,
                    embedding   = EXCLUDED.embedding
                """,
                rows,
            )

    def search(self, query_vector: List[float], k: int = 5) -> List[Dict[str, Any]]:
        """Query top-k nearest neighbors using pgvector cosine distance ordering."""
        import numpy as np

        q = np.array(query_vector, dtype="float32")
        rows = self._execute(
            f"""
            SELECT chunk_id, source_file, node_class, name, text, metadata,
                   1 - (embedding <=> %s) AS score
            FROM {self.table}
            ORDER BY embedding <=> %s
            LIMIT %s
            """,
            (q, q, k),
        ).fetchall()
        return [
            {
                "chunk_id": r[0], "source_file": r[1], "node_class": r[2],
                "name": r[3], "score": round(float(r[6]), 4),
                "text": r[4], "metadata": r[5] or {},
            }
            for r in rows
        ]

    def count(self) -> int:
        """Return indexed row count from the backing pgvector table."""
        return self._execute(f"SELECT COUNT(*) FROM {self.table}").fetchone()[0]

    def search_bm25(
        self, query_text: str, k: int = 5
    ) -> List[Dict[str, Any]]:
        """BM25-style full-text search using PostgreSQL ts_rank.

        Falls back to empty list if the FTS column doesn't exist yet.
        """
        try:
            rows = self._execute(
                f"""
                SELECT chunk_id, source_file, node_class, name, text, metadata,
                       ts_rank(fts, plainto_tsquery('english', %s)) AS score
                FROM {self.table}
                WHERE fts @@ plainto_tsquery('english', %s)
                ORDER BY score DESC
                LIMIT %s
                """,
                (query_text, query_text, k),
            ).fetchall()
        except Exception:
            return []
        return [
            {
                "chunk_id": r[0], "source_file": r[1], "node_class": r[2],
                "name": r[3], "score": round(float(r[6]), 6),
                "text": r[4], "metadata": r[5] or {},
            }
            for r in rows
        ]

    def search_hybrid(
        self,
        query_vector: List[float],
        query_text: str,
        k: int = 5,
        rrf_k: int = 60,
        vector_weight: float = 0.7,
        bm25_weight: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """Hybrid retrieval: vector cosine + BM25 fused with Reciprocal Rank Fusion.

        RRF score = sum(weight / (rrf_k + rank_i)) for each list i.
        Higher rrf_k → less aggressive rank compression.

        Args:
            query_vector:   embedded query (already L2-normalised)
            query_text:     raw query string for BM25
            k:              final number of results to return
            rrf_k:          RRF damping constant (default 60, standard value)
            vector_weight:  weight for vector ranking component
            bm25_weight:    weight for BM25 ranking component
        """
        candidate_k = k * 4  # fetch more candidates than needed before fusion

        vec_hits  = self.search(query_vector, k=candidate_k)
        bm25_hits = self.search_bm25(query_text, k=candidate_k)

        # Build RRF score map  {chunk_id -> (rrf_score, hit_dict)}
        scores: Dict[str, float] = {}
        hits_by_id: Dict[str, Dict[str, Any]] = {}

        for rank, hit in enumerate(vec_hits, start=1):
            cid = hit["chunk_id"]
            scores[cid] = scores.get(cid, 0.0) + vector_weight / (rrf_k + rank)
            hits_by_id[cid] = {**hit, "vector_rank": rank, "vector_score": hit["score"]}

        for rank, hit in enumerate(bm25_hits, start=1):
            cid = hit["chunk_id"]
            scores[cid] = scores.get(cid, 0.0) + bm25_weight / (rrf_k + rank)
            if cid not in hits_by_id:
                hits_by_id[cid] = {**hit, "bm25_rank": rank, "bm25_score": hit["score"]}
            else:
                hits_by_id[cid]["bm25_rank"]  = rank
                hits_by_id[cid]["bm25_score"] = hit["score"]

        # Sort by RRF score descending, take top-k
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:k]
        return [
            {**hits_by_id[cid], "score": round(rrf_score, 6), "retrieval_mode": "hybrid"}
            for cid, rrf_score in ranked
        ]
