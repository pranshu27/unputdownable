"""Pydantic v2 schema validation tests."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.common import ChunkStatus, DocumentFormat
from app.schemas.documents import Chunk, DocumentUpload
from app.schemas.search import SearchQuery


def test_document_upload_valid():
    payload = DocumentUpload(
        title="Apple 10-K",
        source_format=DocumentFormat.PDF,
        source_uri="s3://docs/aapl-10k.pdf",
    )
    assert payload.source_format is DocumentFormat.PDF
    assert payload.document_id is not None


def test_document_upload_rejects_empty_title():
    with pytest.raises(ValidationError):
        DocumentUpload(title="", source_format="pdf", source_uri="s3://docs/x.pdf")


def test_document_upload_rejects_bad_format():
    with pytest.raises(ValidationError):
        DocumentUpload(title="x", source_format="html", source_uri="s3://docs/x")


def test_search_query_top_k_bounds():
    assert SearchQuery(query="liquidity").top_k == 5
    with pytest.raises(ValidationError):
        SearchQuery(query="x", top_k=0)
    with pytest.raises(ValidationError):
        SearchQuery(query="x", top_k=101)


def test_chunk_rejects_negative_indices():
    with pytest.raises(ValidationError):
        Chunk(document_id=uuid4(), text="x", start_index=-1, end_index=5)


def test_chunk_table_defaults():
    chunk = Chunk(document_id=uuid4(), text="| A | B |", start_index=0, end_index=10)
    assert chunk.is_table is False
    assert chunk.table_rows is None
    assert chunk.contextual_header is None
