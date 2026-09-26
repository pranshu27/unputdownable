"""Hybrid search endpoint — dense + sparse + RRF fusion (ADR 002)."""

import asyncio

from fastapi import APIRouter, HTTPException, Request

from ...core.embeddings import get_embedding_backend
from ...core.search_service import SearchService
from ...schemas.search import SearchQuery, SearchResponse

router = APIRouter()


@router.post("", response_model=SearchResponse, summary="Hybrid search (dense + sparse + RRF)")
async def search(payload: SearchQuery, request: Request) -> SearchResponse:
    """Return ranked chunks for a query, fused with RRF (k=60) per ADR 002.

    ``use_hybrid=False`` falls back to dense-only retrieval so the
    Δ Recall@5 (hybrid vs. dense) can be measured against the same index.
    """
    qdrant = request.app.state.qdrant
    if qdrant is None:
        raise HTTPException(status_code=503, detail="Qdrant unavailable; search is disabled.")
    embedder = get_embedding_backend(request.app.state.settings)
    service = SearchService(qdrant, embedder, request.app.state.settings)
    mode = "hybrid" if payload.use_hybrid else "dense"
    outcome = await asyncio.to_thread(service.search, payload.query, payload.top_k, mode)
    return SearchResponse(
        query=payload.query,
        results=outcome.results,
        latency_ms=outcome.spans.total_ms,
        mode=outcome.mode,
        spans={
            "embed_ms": outcome.spans.embed_ms,
            "retrieve_dense_ms": outcome.spans.retrieve_dense_ms,
            "retrieve_sparse_ms": outcome.spans.retrieve_sparse_ms,
            "fuse_ms": outcome.spans.fuse_ms,
        },
    )

