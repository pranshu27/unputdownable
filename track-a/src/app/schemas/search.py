"""Hybrid search schemas."""

from uuid import UUID

from pydantic import BaseModel, Field


class SearchQuery(BaseModel):
    """Hybrid search request (dense + sparse + RRF — see ADR 002)."""

    query: str = Field(min_length=1, max_length=2048)
    top_k: int = Field(default=5, ge=1, le=100)
    use_hybrid: bool = True


class SearchResult(BaseModel):
    """A single retrieved chunk with its fusion score."""

    chunk_id: UUID
    document_id: UUID
    text: str
    score: float
    rank: int | None = None


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult] = Field(default_factory=list)
    latency_ms: float | None = None
    mode: str | None = None
    spans: dict[str, float] = Field(default_factory=dict)

