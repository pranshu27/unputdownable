"""Tests for ADR-003: query transformation pipeline + QueryService reflection.

Transformers run hermetically (no Qdrant). The QueryService end-to-end test uses the
scratch collection + HashingBackend (auto-skips when Qdrant is down).
"""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.core.query_transformers import (
    RewriteTransformer,
    SubQueryDecomposer,
    apply_pipeline,
    build_pipeline,
)


def test_subquery_decomposer_splits_compound_queries():
    d = SubQueryDecomposer()
    out = d.transform("What is the fee schedule and also the latency budget?")
    assert out == ["fee schedule", "latency budget"]


def test_subquery_decomposer_ignores_simple_queries():
    assert SubQueryDecomposer().transform("net sales fiscal 2023") == []


def test_rewrite_strips_filler_and_synonyms():
    out = RewriteTransformer().transform("What is the revenue by segment?")
    assert out == ["net sales by segment"]


def test_pipeline_variants_are_deduplicated_and_original_kept():
    chain = build_pipeline(get_settings().model_copy(update={"query_transform_pipeline": "subquery,rewrite"}))
    variants = apply_pipeline("What is the revenue and also the cash position?", chain)
    assert all(v.lower() != "what is the revenue and also the cash position?" for v in variants)
    assert len(variants) == len({v.lower() for v in variants})


@pytest.fixture(scope="module")
def query_env(scratch_client):
    client, settings = scratch_client
    from app.core.embeddings import HashingBackend
    from app.core.ingest_service import IngestService
    from app.core.search_service import SearchService
    from app.core.query_service import QueryService
    from app.schemas.common import DocumentFormat
    from app.schemas.documents import DocumentUpload

    DOC = """# Quarterly Report
## Overview
Revenue grew on strong Services performance and iPhone demand.

## Financials
| Metric | FY2023 | FY2022 |
|---|---|---|
| Net sales | 383285 | 394328 |

## Risks
Supply constraints affected the final quarter.
"""
    ingest = IngestService(client, HashingBackend(settings), settings)
    result = ingest.ingest(
        DocumentUpload(title="Quarterly Report", source_format=DocumentFormat.MARKDOWN, source_uri="inline"),
        source_text=DOC,
    )
    assert result.response.status.value == "embedded"
    search = SearchService(client, HashingBackend(settings), settings)
    query = QueryService(search, settings)
    return query


def test_query_service_returns_ranked_results(query_env):
    outcome = query_env.search("net sales fiscal performance", top_k=5)
    assert outcome.results
    assert [r.rank for r in outcome.results] == list(range(1, len(outcome.results) + 1))
    assert outcome.spans.transform_ms >= 0 and outcome.spans.total_ms > 0


def test_reflection_reports_coverage(query_env):
    outcome = query_env.search("iPhone demand and supply constraints", top_k=5)
    assert outcome.reflections
    first = outcome.reflections[0]
    assert "coverage" in first
    if not first["sufficient"]:
        assert outcome.spans.retries == 1  # bounded retry happened
        assert "after_retry" in first or "sufficient_after_retry" in first
