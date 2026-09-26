"""Hybrid search endpoint."""

from fastapi import APIRouter

from ...schemas.search import SearchQuery, SearchResponse

router = APIRouter()


@router.post("", response_model=SearchResponse, summary="Hybrid search (dense + sparse + RRF)")
async def search(payload: SearchQuery) -> SearchResponse:
    """Return ranked chunks for a query.

    Skeleton stub: hybrid retrieval (dense HNSW + sparse BM25 + RRF fusion) lands in
    Week 2 (see ADR 002).
    """
    return SearchResponse(query=payload.query, results=[])
