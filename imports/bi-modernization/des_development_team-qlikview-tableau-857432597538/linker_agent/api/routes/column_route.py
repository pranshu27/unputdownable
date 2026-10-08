"""Routes for column-to-glossary matching (3-tier pipeline) and bulk enrichment."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request

from linker_agent.clients.alation_client import SwaggerAPIClient
from linker_agent.config import get_config
from linker_agent.models.asset_record import AssetContext, AssetRecord, AssetType
from linker_agent.services.column_matcher_service import ColumnMatcherService
from linker_agent.services.enrichment_service import EnrichmentService


def _column_names_to_assets(column_names: List[str]) -> List[AssetRecord]:
    """Wrap bare column-name strings into AssetRecord objects for backward compat."""
    return [
        AssetRecord(
            asset_id=f"legacy_col::{name.lower().replace(' ', '_')}",
            asset_type=AssetType.COLUMN,
            name=name,
            context=AssetContext(source_tool="unknown"),
        )
        for name in column_names
    ]

router = APIRouter(prefix="/columns", tags=["columns"])


def get_client(request: Request) -> SwaggerAPIClient:
    return request.app.state.alation_client


@router.get("/match")
async def match_column(
    column: str = Query(..., description="Database column name to match"),
    glossary_id: int = Query(2, description="Alation glossary ID to search in"),
    use_cache: bool = Query(True, description="Use cached glossary index"),
    client: SwaggerAPIClient = Depends(get_client),
):
    """Match a single database column name to a business glossary term.

    Uses the 3-tier pipeline:
    1. Direct linkage (100% confidence) via Data Asset custom field
    2. LLM semantic matching (60-100% confidence)
    3. LLM term generation for columns with no existing match
    """
    service = ColumnMatcherService(client)
    result = await service.match_column(column, glossary_id=glossary_id, use_cache=use_cache)
    return {
        "column": column,
        "glossary_id": glossary_id,
        "matched": result is not None,
        "metadata": result,
    }


@router.post("/batch-match")
async def batch_match_columns(
    column_names: List[str],
    glossary_id: int = Query(2, description="Alation glossary ID to search in"),
    use_cache: bool = Query(True, description="Use cached glossary index"),
    client: SwaggerAPIClient = Depends(get_client),
):
    """Match multiple column names to business glossary terms in one call.

    Returns per-column results with match tier, confidence score, and rationale.
    """
    service = ColumnMatcherService(client)
    results = await service.batch_match_columns(
        column_names, glossary_id=glossary_id, use_cache=use_cache
    )
    matched = sum(1 for v in results.values() if v is not None)
    return {
        "glossary_id": glossary_id,
        "total": len(column_names),
        "matched": matched,
        "unmatched": len(column_names) - matched,
        "results": results,
    }


@router.post("/enrich-glossary")
async def enrich_glossary(
    glossary_id: int = Query(2, description="Alation glossary ID to enrich"),
    confidence_threshold: int = Query(
        60, ge=0, le=100, description="Minimum LLM confidence to accept a Tier 2 match"
    ),
    max_concurrent: int = Query(
        5, ge=1, le=20, description="Simultaneous LLM calls (higher = faster but more API load)"
    ),
    client: SwaggerAPIClient = Depends(get_client),
):
    """Process every term in a glossary through the full 3-tier matching pipeline.

    - **Tier 1** (instant, 100% confidence): terms already linked to a column via
      the Alation 'Data Asset' custom field.
    - **Tier 2** (LLM, 60-100% confidence): unlinked terms matched semantically
      against all available columns. Runs concurrently up to `max_concurrent`.
    - **Tier 3** (LLM suggestion): terms with no column match receive a suggested
      column spec (name, data type, table pattern) to guide data stewards.
    - **Unmatched**: terms where nothing clears `confidence_threshold` at any tier.

    Returns a full per-term report plus summary statistics (includes `tier3_results`
    with `suggested_column_name`, `suggested_data_type`, `suggested_table_pattern`).
    For large glossaries (hundreds of terms) this may take several minutes; set
    `max_concurrent` higher to trade API rate-limit headroom for speed.
    """
    cfg = get_config()
    service = EnrichmentService(client)
    return await service.run(
        glossary_id=glossary_id,
        confidence_threshold=confidence_threshold,
        max_concurrent=max_concurrent,
    )
