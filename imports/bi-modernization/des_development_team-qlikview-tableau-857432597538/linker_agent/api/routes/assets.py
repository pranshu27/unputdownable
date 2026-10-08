"""
/assets/* routes — generic asset enrichment endpoints.
These replace /columns/* as the primary interface.
/columns/* routes are kept as backward-compatible wrappers.
"""

import json
import logging
import time
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from linker_agent.clients.alation_client import SwaggerAPIClient
from linker_agent.config import get_config
from linker_agent.core.asset_matcher_service import AssetMatcherService
from linker_agent.core.event_log_service import get_all_events, get_events_for_asset
from linker_agent.ingestion.context_builder_postgres import build_context_from_catalog
from linker_agent.ingestion.model_parser import parse_common_model
from linker_agent.ingestion.postgres_fetcher import fetch_catalog_by_job_id, list_available_jobs
from linker_agent.models.asset_record import (
    AssetLinkResult,
    AssetRecord,
    BatchEnrichmentResponse,
    BatchJobResult,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assets", tags=["assets"])

_RESULTS_PATH = Path("./output/enrichment_results.json")


def _write_enrichment_output(results: list[AssetLinkResult]) -> None:
    """Persist enrichment results to output/enrichment_results.json. Non-fatal on error."""
    try:
        _RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_RESULTS_PATH, "w", encoding="utf-8") as f:
            json.dump([r.model_dump() for r in results], f, indent=2)
    except Exception as exc:
        logger.warning("Could not write enrichment results to disk: %s", exc)


def get_client(request: Request) -> SwaggerAPIClient:
    return request.app.state.alation_client


def get_asset_matcher_service(
    client: SwaggerAPIClient = Depends(get_client),
) -> AssetMatcherService:
    return AssetMatcherService(swagger_client=client)


@router.post("/match", response_model=AssetLinkResult)
async def match_single_asset(
    asset: AssetRecord,
    service: AssetMatcherService = Depends(get_asset_matcher_service),
):
    """Enrich a single AssetRecord with business metadata."""
    return await service.enrich_asset(asset)


@router.post("/batch-match", response_model=list[AssetLinkResult])
async def match_asset_batch(
    assets: list[AssetRecord],
    service: AssetMatcherService = Depends(get_asset_matcher_service),
):
    """Enrich a batch of AssetRecords."""
    return await service.enrich_batch(assets)


@router.post("/ingest-model", response_model=list[AssetLinkResult])
async def ingest_and_enrich_model(
    model: dict,
    service: AssetMatcherService = Depends(get_asset_matcher_service),
):
    """
    Accept a full RE Common Model JSON, parse into AssetRecords,
    and enrich all assets in one call.
    This is the primary end-to-end endpoint for the cascade.
    """
    try:
        assets = parse_common_model(model)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Model parse failed: {e}")

    results = await service.enrich_batch(assets)
    _write_enrichment_output(results)
    return results


@router.post("/ingest-from-postgres", response_model=list[AssetLinkResult])
async def ingest_from_postgres(
    job_id: str,
    verdict_filter: Optional[List[str]] = Query(
        default=None,
        description=(
            "Filter by ai_verdict_refined. Options: Keep, Merge, Retire, Standardize. "
            "Default: all verdicts included. "
            "Recommended: exclude Retire since those assets are being deprecated."
        ),
    ),
    item_type: Optional[str] = Query(
        default=None,
        description="Filter by item_type: 'KPI' or 'Attribute'. Default: both.",
    ),
    service: AssetMatcherService = Depends(get_asset_matcher_service),
):
    """
    Fetch rationalized assets from kpi_rationalized_catalog in Postgres by job_id,
    then run the full 3-tier enrichment pipeline on all fetched assets.

    Writes results to output/enrichment_results.json and appends to event_log.jsonl.

    Recommended: exclude 'Retire' verdicts to avoid enriching assets that are
    being deprecated.

    Example:
        POST /assets/ingest-from-postgres?job_id=xxx&verdict_filter=Keep&verdict_filter=Merge&verdict_filter=Standardize
    """
    config = get_config()
    try:
        assets = await fetch_catalog_by_job_id(
            job_id=job_id,
            conn_str=config.postgres_conn_str,
            schema=config.postgres_schema,
            verdict_filter=verdict_filter,
            item_type_filter=item_type,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Postgres fetch failed: {exc}")

    if not assets:
        raise HTTPException(
            status_code=404,
            detail=f"No assets found for job_id={job_id} with the given filters.",
        )

    results = await service.enrich_batch(
        assets,
        context_builder_override=build_context_from_catalog,
    )
    _write_enrichment_output(results)
    return results


@router.get("/jobs", response_model=List[dict])
async def list_jobs():
    """
    List all available rationalization job_ids in the Postgres catalog,
    with asset counts per job. Use this to discover job_ids before calling
    /assets/ingest-from-postgres.
    """
    config = get_config()
    try:
        jobs = await list_available_jobs(
            conn_str=config.postgres_conn_str,
            schema=config.postgres_schema,
        )
        return jobs
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Postgres unavailable: {exc}")


@router.post("/ingest-all-jobs", response_model=BatchEnrichmentResponse)
async def ingest_all_jobs(
    verdict_filter: Optional[List[str]] = Query(
        default=None,
        description=(
            "Filter by ai_verdict_refined applied to every job. "
            "Options: Keep, Merge, Retire, Standardize. "
            "Default: all verdicts. Recommended: exclude Retire."
        ),
    ),
    item_type: Optional[str] = Query(
        default=None,
        description="Filter by item_type: 'KPI' or 'Attribute'. Default: both.",
    ),
    service: AssetMatcherService = Depends(get_asset_matcher_service),
):
    """
    Fetch ALL available rationalization job_ids from Postgres and run the full
    3-tier enrichment pipeline on every job sequentially.

    This is the bulk enrichment endpoint for the UI showcase — one call processes
    every job in the catalog and returns per-job results plus an overall summary.

    Jobs are processed one at a time (assets within each job run concurrently).
    Results are written to output/enrichment_results_batch.json.

    Recommended: exclude 'Retire' verdicts to skip assets being deprecated.

    Example:
        POST /assets/ingest-all-jobs?verdict_filter=Keep&verdict_filter=Merge&verdict_filter=Standardize
    """
    config = get_config()
    conn_str = config.postgres_conn_str
    schema = config.postgres_schema

    # Step 1 — discover all job_ids
    try:
        job_summaries = await list_available_jobs(conn_str=conn_str, schema=schema)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Postgres unavailable: {exc}")

    if not job_summaries:
        raise HTTPException(status_code=404, detail="No jobs found in the Postgres catalog.")

    batch_start = time.time()
    job_results: List[BatchJobResult] = []
    all_results: List[AssetLinkResult] = []

    # Step 2 — enrich each job sequentially
    for summary in job_summaries:
        job_id = summary["job_id"]
        job_start = time.time()

        try:
            assets = await fetch_catalog_by_job_id(
                job_id=job_id,
                conn_str=conn_str,
                schema=schema,
                verdict_filter=verdict_filter,
                item_type_filter=item_type,
            )
        except Exception as exc:
            logger.error("Failed to fetch job_id=%s: %s", job_id, exc)
            job_results.append(BatchJobResult(
                job_id=job_id,
                total_assets=0,
                matched=0,
                match_rate_pct=0.0,
                elapsed_seconds=0.0,
                verdict_filter=verdict_filter,
                results=[],
            ))
            continue

        if not assets:
            job_results.append(BatchJobResult(
                job_id=job_id,
                total_assets=0,
                matched=0,
                match_rate_pct=0.0,
                elapsed_seconds=round(time.time() - job_start, 2),
                verdict_filter=verdict_filter,
                results=[],
            ))
            continue

        results = await service.enrich_batch(
            assets,
            context_builder_override=build_context_from_catalog,
        )

        matched = sum(
            1 for r in results
            if r.linkage_type not in ("no_match", "error", "")
        )
        total = len(results)
        elapsed = round(time.time() - job_start, 2)

        job_results.append(BatchJobResult(
            job_id=job_id,
            total_assets=total,
            matched=matched,
            match_rate_pct=round(matched / total * 100, 1) if total else 0.0,
            elapsed_seconds=elapsed,
            verdict_filter=verdict_filter,
            results=results,
        ))
        all_results.extend(results)

    # Step 3 — persist all results to disk
    try:
        batch_path = Path("./output/enrichment_results_batch.json")
        batch_path.parent.mkdir(parents=True, exist_ok=True)
        with open(batch_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "jobs": [
                        {
                            "job_id": jr.job_id,
                            "total_assets": jr.total_assets,
                            "matched": jr.matched,
                            "match_rate_pct": jr.match_rate_pct,
                            "elapsed_seconds": jr.elapsed_seconds,
                            "results": [r.model_dump() for r in jr.results],
                        }
                        for jr in job_results
                    ]
                },
                f,
                indent=2,
            )
    except Exception as exc:
        logger.warning("Could not write batch results to disk: %s", exc)

    total_processed = sum(jr.total_assets for jr in job_results)
    total_matched = sum(jr.matched for jr in job_results)

    return BatchEnrichmentResponse(
        total_jobs=len(job_results),
        total_assets_processed=total_processed,
        overall_match_rate_pct=(
            round(total_matched / total_processed * 100, 1) if total_processed else 0.0
        ),
        elapsed_seconds=round(time.time() - batch_start, 2),
        jobs=job_results,
    )


@router.get("/events/{asset_id}")
async def get_asset_events(asset_id: str):
    """Retrieve the full event log for a single asset."""
    events = get_events_for_asset(asset_id)
    if not events:
        raise HTTPException(
            status_code=404, detail=f"No events found for asset_id: {asset_id}"
        )
    return events


@router.get("/events")
async def get_all_asset_events():
    """Retrieve the full event log (for inspection/debugging)."""
    return get_all_events()
