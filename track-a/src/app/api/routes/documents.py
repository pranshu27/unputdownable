"""Document ingestion endpoints — wired to the ADR-001 pipeline (Week 1 Day 3)."""

from fastapi import APIRouter, HTTPException, Request, status

from ...core.embeddings import get_embedding_backend
from ...core.ingest_service import IngestService
from ...schemas.common import ChunkStatus
from ...schemas.documents import DocumentUpload, IngestResponse

router = APIRouter()


@router.post(
    "",
    response_model=IngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest a document: parse -> semantic chunk -> embed -> upsert",
)
async def ingest_document(payload: DocumentUpload, request: Request) -> IngestResponse:
    """Run the full parsing + chunking + embedding pipeline and upsert into Qdrant.

    The pipeline is CPU-bound (embedding) so it runs in a worker thread to keep
    the event loop responsive.
    """
    import asyncio

    qdrant = request.app.state.qdrant
    if qdrant is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Qdrant unavailable; ingestion is disabled.",
        )
    embedder = get_embedding_backend(request.app.state.settings)
    service = IngestService(qdrant, embedder, request.app.state.settings)
    try:
        result = await asyncio.to_thread(service.ingest, payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result.stats.parse_failed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Ingestion failed: {result.stats.error}",
        )
    return result.response

