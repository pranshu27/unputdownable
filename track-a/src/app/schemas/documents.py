"""Document ingestion schemas."""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from .common import ChunkStatus, DocumentFormat


class DocumentUpload(BaseModel):
    """Request payload to submit a document for ingestion."""

    document_id: UUID = Field(default_factory=uuid4)
    title: str = Field(min_length=1, max_length=512)
    source_format: DocumentFormat
    source_uri: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Chunk(BaseModel):
    """A semantically coherent, self-describing chunk produced by the pipeline.

    Maps to ADR 001: semantic chunks + contextual headers + table-aware rules.
    """

    model_config = ConfigDict(from_attributes=True)

    chunk_id: UUID = Field(default_factory=uuid4)
    document_id: UUID
    text: str
    contextual_header: str | None = None
    start_index: int = Field(ge=0)
    end_index: int = Field(ge=0)
    token_count: int | None = None
    is_table: bool = False
    table_rows: list[list[str]] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestResponse(BaseModel):
    """Accepted-202 response for a document submission."""

    document_id: UUID
    status: ChunkStatus
    chunks_created: int = Field(ge=0)
    accepted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
