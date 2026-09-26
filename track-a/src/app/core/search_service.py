"""Hybrid search service — ADR 002 (dense HNSW + sparse BM25/IDF + RRF).

Latency is decomposed into spans (embed / retrieve / fuse) so Day-3
measurements can report TTFT-equivalent time-to-first-result by span.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from qdrant_client import QdrantClient, models

from ..config import Settings, get_settings
from ..schemas.search import SearchResult
from .embeddings import EmbeddingBackend
from .rrf import reciprocal_rank_fusion


@dataclass(slots=True)
class SearchSpans:
    """Per-span latency decomposition (ms)."""

    embed_ms: float = 0.0
    retrieve_dense_ms: float = 0.0
    retrieve_sparse_ms: float = 0.0
    fuse_ms: float = 0.0
    total_ms: float = 0.0


@dataclass(slots=True)
class SearchOutcome:
    results: list[SearchResult]
    spans: SearchSpans
    mode: str


class SearchService:
    """Hybrid retrieval with RRF fusion over a single Qdrant collection."""

    def __init__(self, client: QdrantClient, embedder: EmbeddingBackend, settings: Settings | None = None) -> None:
        self.client = client
        self.embedder = embedder
        self.settings = settings or get_settings()

    def search(self, query: str, top_k: int = 5, mode: str = "hybrid") -> SearchOutcome:
        settings = self.settings
        spans = SearchSpans()
        started = time.perf_counter()

        t0 = time.perf_counter()
        dense_q = self.embedder.embed_dense([query])[0]
        sparse_q = self.embedder.embed_sparse([query])[0]
        spans.embed_ms = (time.perf_counter() - t0) * 1000

        limit = max(top_k * 4, 20)  # over-fetch so RRF has signal from both lists

        dense_hits: list[models.ScoredPoint] = []
        sparse_hits: list[models.ScoredPoint] = []

        if mode in ("hybrid", "dense"):
            t1 = time.perf_counter()
            res = self.client.query_points(
                collection_name=settings.qdrant_collection,
                query=dense_q,
                using="dense",
                limit=limit,
                with_payload=True,
            )
            dense_hits = res.points
            spans.retrieve_dense_ms = (time.perf_counter() - t1) * 1000

        if mode in ("hybrid", "sparse"):
            t2 = time.perf_counter()
            res = self.client.query_points(
                collection_name=settings.qdrant_collection,
                query=models.SparseVector(**sparse_q),
                using="sparse",
                limit=limit,
                with_payload=True,
            )
            sparse_hits = res.points
            spans.retrieve_sparse_ms = (time.perf_counter() - t2) * 1000

        t3 = time.perf_counter()
        if mode == "hybrid":
            fused = reciprocal_rank_fusion(
                [[p.id for p in dense_hits], [p.id for p in sparse_hits]],
                k=settings.rrf_k,
            )
            by_id: dict = {}
            for p in [*dense_hits, *sparse_hits]:
                by_id.setdefault(p.id, p)
            ordered = [(by_id[i], score) for i, score in fused[:top_k]]
        elif mode == "dense":
            ordered = [(p, p.score or 0.0) for p in dense_hits[:top_k]]
        else:
            ordered = [(p, p.score or 0.0) for p in sparse_hits[:top_k]]
        spans.fuse_ms = (time.perf_counter() - t3) * 1000
        spans.total_ms = (time.perf_counter() - started) * 1000

        results = []
        rank = 0
        for p, score in ordered:
            payload = p.payload or {}
            if "chunk_id" not in payload or "document_id" not in payload:
                continue  # skip malformed/legacy points without ingestion metadata
            rank += 1
            results.append(
                SearchResult(
                    chunk_id=_uuid_or_raw(payload["chunk_id"]),
                    document_id=_uuid_or_raw(payload["document_id"]),
                    text=payload.get("text", ""),
                    score=score,
                    rank=rank,
                )
            )
        return SearchOutcome(results=results, spans=spans, mode=mode)


def _uuid_or_raw(value) -> str:
    from uuid import UUID

    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError):
        return str(value)
