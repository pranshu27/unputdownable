"""End-to-end ingest + hybrid search service tests.

Uses the deterministic hashing embedding backend so the suite runs without a
model download, and auto-skips when Qdrant is not reachable (same pattern as
``test_qdrant_integration.py``). Writes go to the scratch collection from ``conftest.py``.
"""

import pytest

from app.core.embeddings import HashingBackend
from app.core.ingest_service import IngestService
from app.core.search_service import SearchService
from app.schemas.common import DocumentFormat
from app.schemas.documents import DocumentUpload
from app.schemas.search import SearchQuery


DOC = """# Quarterly Report
## Overview
Revenue grew on strong Services performance and iPhone demand.

## Financials
| Metric | FY2023 | FY2022 |
|---|---|---|
| Net sales | 383285 | 394328 |
| Net income | 96995 | 99803 |
"""


@pytest.fixture(scope="module")
def env(scratch_client):
    """Ingest + search services bound to the scratch collection (never ``documents``)."""
    client, settings = scratch_client
    return (
        IngestService(client, HashingBackend(settings), settings),
        SearchService(client, HashingBackend(settings), settings),
    )


def test_ingest_and_hybrid_search_roundtrip(env):
    service, search = env
    upload = DocumentUpload(
        title="Quarterly Report",
        source_format=DocumentFormat.MARKDOWN,
        source_uri="inline",
    )
    result = service.ingest(upload, source_text=DOC)
    assert result.response.status.value == "embedded"
    assert result.response.chunks_created == 2  # 1 prose chunk + 1 atomic table chunk
    assert result.stats.table_chunks == 1  # the financial table stayed atomic

    outcome = search.search("net sales fiscal performance", top_k=5, mode="hybrid")
    assert outcome.results, "hybrid search returned no results"
    assert [r.rank for r in outcome.results] == list(range(1, len(outcome.results) + 1))
    assert outcome.spans.fuse_ms >= 0

    dense_only = search.search("net sales fiscal performance", top_k=5, mode="dense")
    assert dense_only.results


def test_sparse_mode_finds_exact_terms(env):
    service, search = env
    outcome = search.search("383285", top_k=5, mode="sparse")
    assert outcome.results
    assert "383285" in outcome.results[0].text


def test_search_query_schema_has_hybrid_flag():
    q = SearchQuery(query="revenue")
    assert q.use_hybrid is True and q.top_k == 5
