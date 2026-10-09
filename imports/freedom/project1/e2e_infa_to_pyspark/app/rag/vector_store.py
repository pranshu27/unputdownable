"""Vector stores for the RAG layer: an offline in-memory store and a pgvector store.

Both implement the same tiny interface:
- ``upsert(chunks, vectors)`` — index chunks and their embedding vectors.
- ``search(query_vector, k)`` — return the top-k nearest chunks by cosine similarity.

``InMemoryVectorStore`` is deterministic and dependency-free (used by tests and offline
runs). ``PgVectorStore`` persists vectors in Postgres using the ``pgvector`` extension and
runs nearest-neighbour search in the database with the ``<=>`` cosine-distance operator and
an IVFFlat index — the production path.
"""

from __future__ import annotations

import json
import math
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Sequence

from app.rag.chunking import Chunk
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    # vectors are stored L2-normalized, so dot product == cosine similarity
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
    dim: int

    @abstractmethod
    def upsert(self, chunks: List[Chunk], vectors: List[List[float]]) -> None:
        ...

    @abstractmethod
    def search(self, query_vector: List[float], k: int = 5) -> List[Dict[str, Any]]:
        ...

    @abstractmethod
    def count(self) -> int:
        ...


class InMemoryVectorStore(VectorStore):
    """Brute-force cosine search held in process. Deterministic, offline."""

    def __init__(self, dim: int) -> None:
        self.dim = dim
        self._chunks: List[Chunk] = []
        self._vectors: List[List[float]] = []

    def upsert(self, chunks: List[Chunk], vectors: List[List[float]]) -> None:
        self._chunks.extend(chunks)
        self._vectors.extend(vectors)

    def search(self, query_vector: List[float], k: int = 5) -> List[Dict[str, Any]]:
        scored = [
            (_cosine(query_vector, vec), chunk)
            for vec, chunk in zip(self._vectors, self._chunks)
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [_hit(chunk, score) for score, chunk in scored[:k] if score > 0]

    def count(self) -> int:
        return len(self._chunks)


class PgVectorStore(VectorStore):
    """Postgres + pgvector store. Nearest-neighbour search runs in the database.

    Schema (created on first use):
        rag_chunks(
            chunk_id text primary key,
            source_file text, node_class text, name text,
            text text, metadata jsonb,
            embedding vector(<dim>)
        )
    with an IVFFlat cosine index on ``embedding``.
    """

    def __init__(
        self, dsn: str, dim: int, table: str = "rag_chunks", schema: str = "rag"
    ) -> None:
        import psycopg  # lazy import; only needed for the pgvector backend
        from pgvector.psycopg import register_vector

        self.dim = dim
        self.schema = schema
        self.table = f"{schema}.{table}"
        self._psycopg = psycopg
        self._conn = psycopg.connect(dsn, autocommit=True)
        self._ensure_extension()
        register_vector(self._conn)
        self._ensure_schema()

    def _ensure_extension(self) -> None:
        """Enable pgvector. On managed Postgres (Azure) a non-admin cannot CREATE
        EXTENSION, but an admin may have pre-created it — so only create if missing."""
        exists = self._conn.execute(
            "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
        if exists:
            return
        self._conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

    def _ensure_schema(self) -> None:
        self._conn.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")
        self._conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.table} (
                chunk_id   text PRIMARY KEY,
                source_file text,
                node_class text,
                name       text,
                text       text,
                metadata   jsonb,
                embedding  vector({self.dim})
            )
            """
        )
        # IVFFlat index for cosine distance; safe to attempt repeatedly.
        idx = f"{self.schema}_rag_chunks_emb_idx"
        try:
            self._conn.execute(
                f"CREATE INDEX IF NOT EXISTS {idx} "
                f"ON {self.table} USING ivfflat (embedding vector_cosine_ops) "
                f"WITH (lists = 100)"
            )
        except Exception as exc:  # index optional; brute force still works
            logger.warning("pgvector index not created: %s", exc)

    def upsert(self, chunks: List[Chunk], vectors: List[List[float]]) -> None:
        import numpy as np

        rows = [
            (
                chunk.chunk_id,
                chunk.source_file,
                chunk.node_class,
                chunk.name,
                chunk.text,
                json.dumps(chunk.metadata),
                np.array(vec, dtype="float32"),
            )
            for chunk, vec in zip(chunks, vectors)
        ]
        with self._conn.cursor() as cur:
            cur.executemany(
                f"""
                INSERT INTO {self.table}
                    (chunk_id, source_file, node_class, name, text, metadata, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
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
        import numpy as np

        q = np.array(query_vector, dtype="float32")
        rows = self._conn.execute(
            f"""
            SELECT chunk_id, source_file, node_class, name, text, metadata,
                   1 - (embedding <=> %s) AS score
            FROM {self.table}
            ORDER BY embedding <=> %s
            LIMIT %s
            """,
            (q, q, k),
        ).fetchall()
        hits: List[Dict[str, Any]] = []
        for chunk_id, source_file, node_class, name, text, metadata, score in rows:
            hits.append(
                {
                    "chunk_id": chunk_id,
                    "source_file": source_file,
                    "node_class": node_class,
                    "name": name,
                    "score": round(float(score), 4),
                    "text": text,
                    "metadata": metadata or {},
                }
            )
        return hits

    def count(self) -> int:
        return self._conn.execute(f"SELECT COUNT(*) FROM {self.table}").fetchone()[0]
