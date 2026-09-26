"""Document ingestion endpoints."""

from fastapi import APIRouter, status

from ...schemas.common import ChunkStatus
from ...schemas.documents import DocumentUpload, IngestResponse

router = APIRouter()


@router.post(
    "",
    response_model=IngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a document for ingestion",
)
async def ingest_document(payload: DocumentUpload) -> IngestResponse:
    """Accept a document and (eventually) run it through the parsing + chunking pipeline.

    Skeleton stub: parsing, semantic chunking, contextual headers and table-aware
    rules are implemented on Week 1 Day 3 (per ``daily-goals.md``).
    """
    return IngestResponse(
        document_id=payload.document_id,
        status=ChunkStatus.PENDING,
        chunks_created=0,
    )
