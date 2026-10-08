"""
MCP Server — exposes Linker Agent tools to Alation Agent Studio.

Tools:
  match_column_to_glossary   — 3-tier single-column match
  batch_match_columns        — bulk column match
  list_glossary_terms        — browse terms with linked columns
  get_glossary_tree          — fetch terms across a glossary + sub-glossaries
  update_term_description    — write description back to Alation
  update_custom_field_values — batch-update custom field values in Alation
"""

import asyncio
import logging

from mcp.server.fastmcp import FastMCP

from linker_agent.clients.alation_client import SwaggerAPIClient, SwaggerAPIConfig
from linker_agent.config import get_config
from linker_agent.models.curation_models import FieldUpdate
from linker_agent.services.column_matcher_service import ColumnMatcherService
from linker_agent.services.curation_service import CurationService
from linker_agent.services.enrichment_service import EnrichmentService

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "Linker Agent",
    instructions=(
        "Tools for matching database column names to business glossary terms in Alation. "
        "Uses a 3-tier pipeline: direct linkage → LLM semantic matching → LLM term generation. "
        "Also supports writing enrichment (descriptions, custom field values) back to Alation."
    ),
    host="0.0.0.0",
    port=8001,
)


# ---------------------------------------------------------------------------
# Helper: create a short-lived async client for each tool invocation
# ---------------------------------------------------------------------------

async def _with_client(coro_fn):
    """Run an async function with a fresh SwaggerAPIClient."""
    cfg = get_config()
    api_config = SwaggerAPIConfig(
        base_url=cfg.alation_base,
        api_token=cfg.alation_api_token,
    )
    async with SwaggerAPIClient(api_config) as client:
        return await coro_fn(client)


# ---------------------------------------------------------------------------
# Matching tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def match_column_to_glossary(column_name: str, glossary_id: int = 2) -> dict:
    """Match a database column name to a business glossary term in Alation.

    Uses the full 3-tier pipeline:
    1. Direct linkage — columns already linked via Data Asset field (100% confidence)
    2. LLM semantic matching — unlinked terms matched by meaning (60-100%)
    3. LLM term generation — new term suggested when no match exists

    Args:
        column_name: Database column name, e.g. "cust_addr_line1", "pol_eff_dt"
        glossary_id: Alation glossary ID to search (default: 2)

    Returns:
        {column, matched, metadata} — metadata contains term_title, confidence_score,
        linkage_type, matching_rationale, and more.
    """
    logger.info(f"MCP: match_column_to_glossary('{column_name}', glossary_id={glossary_id})")

    async def _run(client):
        service = ColumnMatcherService(client)
        result = await service.match_column(column_name, glossary_id=glossary_id)
        return {
            "column": column_name,
            "glossary_id": glossary_id,
            "matched": result is not None,
            "metadata": result,
        }

    return await _with_client(_run)


@mcp.tool()
async def batch_match_columns(column_names: list[str], glossary_id: int = 2) -> dict:
    """Match multiple database column names to glossary terms in a single call.

    Runs the full 3-tier pipeline for every column and returns aggregated results.
    Useful for bulk enrichment workflows.

    Args:
        column_names: List of column names, e.g. ["cust_name", "pol_eff_dt"]
        glossary_id: Alation glossary ID (default: 2)

    Returns:
        {total, matched, unmatched, results} — results maps each column name to
        its metadata dict or None if unmatched.
    """
    logger.info(f"MCP: batch_match_columns({len(column_names)} columns, glossary_id={glossary_id})")

    async def _run(client):
        service = ColumnMatcherService(client)
        results = await service.batch_match_columns(column_names, glossary_id=glossary_id)
        matched = sum(1 for v in results.values() if v is not None)
        return {
            "glossary_id": glossary_id,
            "total": len(column_names),
            "matched": matched,
            "unmatched": len(column_names) - matched,
            "results": results,
        }

    return await _with_client(_run)


# ---------------------------------------------------------------------------
# Glossary browse tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_glossary_terms(glossary_id: int = 2, limit: int = 50) -> dict:
    """List business glossary terms with their linked Alation column details.

    Useful for understanding what terms exist before running a match,
    or for reviewing current glossary coverage.

    Args:
        glossary_id: Alation glossary ID (default: 2)
        limit: Maximum terms to return (default: 50)

    Returns:
        {term_count, terms} — each term includes id, title, description,
        column_id, and column_name (if a Data Asset is linked).
    """
    logger.info(f"MCP: list_glossary_terms(glossary_id={glossary_id}, limit={limit})")

    async def _run(client):
        terms_raw = await client.get_terms(glossary_id=glossary_id, limit=limit)
        result = []
        for term in terms_raw:
            col_id = client.extract_data_asset_oid(term)
            col = None
            if col_id:
                try:
                    col = await client.get_column_by_id(col_id)
                except Exception:
                    pass
            from linker_agent.clients.alation_client import SwaggerAPIClient as _C
            result.append({
                "id": term["id"],
                "title": term["title"],
                "description": _C.clean_html_description(term.get("description") or ""),
                "column_id": col.get("id") if col else None,
                "column_name": col.get("name") if col else None,
            })
        return {"term_count": len(result), "terms": result}

    return await _with_client(_run)


@mcp.tool()
async def get_glossary_tree(glossary_id: int = 1) -> dict:
    """Fetch all terms from a glossary AND its sub-glossaries.

    Discovers sub-glossaries by following the ``glossary_ids`` field on terms,
    so you get complete coverage including nested glossary structures.

    Args:
        glossary_id: Root Alation glossary ID (default: 1)

    Returns:
        {status, glossary_id, term_count, terms} — terms include id, title,
        description, glossary_ids, template_id, and custom_fields.
    """
    logger.info(f"MCP: get_glossary_tree(glossary_id={glossary_id})")

    async def _run(client):
        return await client.get_glossary_tree(glossary_id=glossary_id)

    return await _with_client(_run)


# ---------------------------------------------------------------------------
# Bulk enrichment tool
# ---------------------------------------------------------------------------

@mcp.tool()
async def enrich_glossary(
    glossary_id: int = 2,
    confidence_threshold: int = 60,
    max_concurrent: int = 5,
) -> dict:
    """Process every term in a glossary through the full 3-tier matching pipeline.

    Runs all N terms — regardless of how many — through a 3-tier pipeline:
    - Tier 1: terms with existing Data Asset links (100% confidence, instant)
    - Tier 2: unlinked terms matched to existing columns by LLM semantics
      (60-100% confidence), executed concurrently up to max_concurrent at a time
    - Tier 3: terms with no column match — LLM suggests a fitting column spec
      (column name, data type, table pattern) to guide data stewards
    - Unmatched: terms where nothing clears the confidence threshold at any tier

    Returns a complete per-term report with summary statistics.

    Args:
        glossary_id: Alation glossary ID to enrich (default: 2)
        confidence_threshold: Minimum LLM confidence score to accept a Tier 2 match (default: 60)
        max_concurrent: Simultaneous LLM calls — raise for speed, lower if rate-limited (default: 5)

    Returns:
        {summary, tier1_results, tier2_results, tier3_results, unmatched_results, all_results}
        summary includes total_terms, tier1_count, tier2_count, tier3_count, match_rate_pct,
        avg_confidence, processing_time_seconds.
        tier3_results entries include suggested_column_name, suggested_data_type,
        suggested_table_pattern alongside the usual term metadata.
    """
    logger.info(
        f"MCP: enrich_glossary(glossary_id={glossary_id}, "
        f"confidence_threshold={confidence_threshold}, max_concurrent={max_concurrent})"
    )

    async def _run(client):
        service = EnrichmentService(client)
        return await service.run(
            glossary_id=glossary_id,
            confidence_threshold=confidence_threshold,
            max_concurrent=max_concurrent,
        )

    return await _with_client(_run)


# ---------------------------------------------------------------------------
# Write-back tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def update_term_description(
    term_id: int,
    description: str,
    template_id: int | None = None,
) -> dict:
    """Update a glossary term's description in Alation.

    Writes an approved description back to a specific glossary term via the
    Alation integration API. The template_id is auto-resolved from the term
    if not provided.

    Args:
        term_id: Alation glossary term ID to update.
        description: HTML-formatted description content, e.g. "<p>My definition</p>"
        template_id: Optional template ID (auto-fetched from term if omitted).

    Returns:
        {success, term_id, detail, alation_response} on success,
        or {success, detail, status_code} on error.
    """
    logger.info(f"MCP: update_term_description(term_id={term_id}, template_id={template_id})")

    async def _run(client):
        service = CurationService(client)
        result = await service.update_term_description(
            term_id=term_id,
            description=description,
            template_id=template_id,
        )
        return result.model_dump()

    return await _with_client(_run)


@mcp.tool()
async def update_custom_field_values(
    term_id: int,
    field_updates: list[dict],
    template_id: int | None = None,
) -> dict:
    """Batch-update custom field values on a glossary term in Alation.

    Writes one or more approved custom field values back to a specific term
    via the Alation custom field API. The template_id is auto-resolved if omitted.

    Args:
        term_id: Alation glossary term ID to update.
        field_updates: List of {field_id, value} dicts.
            Example: [{"field_id": 10009, "value": "Yes"}, {"field_id": 10010, "value": "Public"}]
        template_id: Optional template ID (auto-fetched from term if omitted).

    Returns:
        {success, term_id, detail, alation_response} on success,
        or {success, detail, status_code} on error.
    """
    logger.info(
        f"MCP: update_custom_field_values(term_id={term_id}, fields={len(field_updates)})"
    )

    async def _run(client):
        parsed = [FieldUpdate(field_id=fu["field_id"], value=fu["value"]) for fu in field_updates]
        service = CurationService(client)
        result = await service.update_custom_field_values(
            term_id=term_id,
            field_updates=parsed,
            template_id=template_id,
        )
        return result.model_dump()

    return await _with_client(_run)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    from starlette.applications import Starlette
    from starlette.middleware.cors import CORSMiddleware
    from starlette.routing import Route
    from starlette.responses import JSONResponse
    from starlette.requests import Request

    async def rest_health(request: Request):
        return JSONResponse({"status": "ok"})

    mcp_app = mcp.sse_app()

    app = Starlette(routes=[Route("/health", rest_health)])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/", mcp_app)

    uvicorn.run(app, host="0.0.0.0", port=8001)
