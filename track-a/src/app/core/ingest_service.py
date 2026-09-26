"""Ingestion service: parse -> chunk -> embed -> upsert (ADR 001 pipeline).

Tracks per-stage latency so Day-3 measurements can report ingest p95 and
throughput by span (parse / chunk / embed / upsert).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from qdrant_client import QdrantClient, models

from ..schemas.common import ChunkStatus, DocumentFormat
from ..schemas.documents import DocumentUpload, IngestResponse
from .chunker import chunk_source
from .embeddings import EmbeddingBackend
from .parsers import ParsedDocument
from .qdrant import ensure_collection


@dataclass(slots=True)
class IngestStats:
    """Per-stage ingest timing + quality counters (fed into Day-3 measurements)."""

    parse_ms: float = 0.0
    chunk_ms: float = 0.0
    embed_ms: float = 0.0
    upsert_ms: float = 0.0
    total_ms: float = 0.0
    chunks_created: int = 0
    table_chunks: int = 0
    source_tokens: int = 0
    parse_failed: bool = False
    error: str | None = None


@dataclass
class IngestResult:
    response: IngestResponse
    stats: IngestStats
    parsed: ParsedDocument | None = None
    chunk_ids: list[UUID] = field(default_factory=list)


def load_source(source_uri: str, data_dir: str = "data") -> str:
    """Load document text from a local path, ``file://`` URI or ``data/`` relative name."""
    raw = source_uri
    if raw.startswith("file://"):
        raw = raw[len("file://"):]
    path = Path(raw)
    if not path.exists():
        candidate = Path(data_dir) / raw
        if candidate.exists():
            path = candidate
        else:
            raise FileNotFoundError(f"source_uri not found: {source_uri}")
    return path.read_text(encoding="utf-8", errors="replace")


def _format_from_uri(uri: str, fallback: DocumentFormat) -> DocumentFormat:
    lower = uri.lower()
    if lower.endswith((".md", ".markdown")):
        return DocumentFormat.MARKDOWN
    if lower.endswith((".htm", ".html", ".xhtml")):
        return DocumentFormat.PDF  # SEC-style HTML routed through the layout-aware path
    if lower.endswith(".txt"):
        return DocumentFormat.DOCX  # plain-text path until the docx strategy lands
    return fallback


def count_text_tokens(text: str) -> int:
    """Whitespace token count for a raw source string."""
    return len(text.split())


class IngestService:
    """Runs the full ADR-001 pipeline for one document."""

    def __init__(
        self,
        client: QdrantClient,
        embedder: EmbeddingBackend,
        settings=None,
    ) -> None:
        self.client = client
        self.embedder = embedder
        from ..config import get_settings

        self.settings = settings or get_settings()

    def ingest(self, payload: DocumentUpload, source_text: str | None = None) -> IngestResult:
        settings = self.settings
        stats = IngestStats()
        started = time.perf_counter()
        source_format = _format_from_uri(payload.source_uri, payload.source_format)

        try:
            if source_text is None:
                source_text = load_source(payload.source_uri, settings.data_dir)

            t0 = time.perf_counter()
            parsed, chunks = chunk_source(
                source_text,
                payload.title,
                payload.document_id,
                source_format,
                target_tokens=settings.chunk_target_tokens,
                overlap_tokens=settings.chunk_overlap_tokens,
            )
            stats.parse_ms = (time.perf_counter() - t0) * 1000
            stats.chunks_created = len(chunks)
            stats.table_chunks = sum(1 for c in chunks if c.is_table)
            stats.source_tokens = count_text_tokens(source_text)

            if not chunks:
                stats.total_ms = (time.perf_counter() - started) * 1000
                return IngestResult(
                    response=IngestResponse(
                        document_id=payload.document_id,
                        status=ChunkStatus.FAILED,
                        chunks_created=0,
                    ),
                    stats=stats,
                    parsed=parsed,
                )

            t1 = time.perf_counter()
            embed_texts = [
                f"{c.contextual_header}\n\n{c.text}" if c.contextual_header else c.text
                for c in chunks
            ]
            dense = self.embedder.embed_dense(embed_texts)
            sparse = self.embedder.embed_sparse(embed_texts)
            stats.embed_ms = (time.perf_counter() - t1) * 1000

            t2 = time.perf_counter()
            ensure_collection(self.client, settings)
            points = [
                models.PointStruct(
                    id=str(c.chunk_id),
                    vector={"dense": dense[i], "sparse": models.SparseVector(**sparse[i])},
                    payload={
                        "chunk_id": str(c.chunk_id),
                        "document_id": str(c.document_id),
                        "document_title": payload.title,
                        "text": c.text,
                        "contextual_header": c.contextual_header or "",
                        "start_index": c.start_index,
                        "end_index": c.end_index,
                        "token_count": c.token_count or 0,
                        "is_table": c.is_table,
                        "table_rows": c.table_rows,
                        "metadata": c.metadata,
                    },
                )
                for i, c in enumerate(chunks)
            ]
            self.client.upsert(collection_name=settings.qdrant_collection, points=points)
            stats.upsert_ms = (time.perf_counter() - t2) * 1000
            stats.total_ms = (time.perf_counter() - started) * 1000

            return IngestResult(
                response=IngestResponse(
                    document_id=payload.document_id,
                    status=ChunkStatus.EMBEDDED,
                    chunks_created=len(chunks),
                ),
                stats=stats,
                parsed=parsed,
                chunk_ids=[c.chunk_id for c in chunks],
            )
        except Exception as exc:  # parse failures are a measured quality metric
            stats.parse_failed = True
            stats.error = f"{type(exc).__name__}: {exc}"
            stats.total_ms = (time.perf_counter() - started) * 1000
            return IngestResult(
                response=IngestResponse(
                    document_id=payload.document_id,
                    status=ChunkStatus.FAILED,
                    chunks_created=0,
                ),
                stats=stats,
            )
