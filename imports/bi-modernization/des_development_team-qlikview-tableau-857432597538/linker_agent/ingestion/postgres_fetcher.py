"""
Fetches rationalized KPI catalog rows from PostgreSQL and converts
them to AssetRecord objects for the Linker Agent enrichment pipeline.

Mirrors the same output contract as model_parser.py — both produce list[AssetRecord].
Connection is configured via POSTGRES_URL (or individual POSTGRES_* env vars) in config.py.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import asyncpg

from linker_agent.models.asset_record import AssetContext, AssetRecord, AssetState, AssetType

logger = logging.getLogger(__name__)

# ── Asset type mapping ──────────────────────────────────────────────────────

SEMANTIC_TYPE_TO_ASSET_TYPE: dict[str, AssetType] = {
    "growth_rate": AssetType.KPI,
    "ratio":       AssetType.KPI,
    "cagr":        AssetType.KPI,
    "sum":         AssetType.CALCULATION,
    "count":       AssetType.CALCULATION,
    "average":     AssetType.CALCULATION,
    "min":         AssetType.CALCULATION,
    "max":         AssetType.CALCULATION,
    "discount":    AssetType.CALCULATION,
    "identifier":  AssetType.COLUMN,
    "primary_key": AssetType.COLUMN,
    "foreign_key": AssetType.COLUMN,
    "dimension":   AssetType.DIMENSION,
    "measure":     AssetType.MEASURE,
    "date":        AssetType.COLUMN,
    "datetime":    AssetType.COLUMN,
}

ITEM_TYPE_FALLBACK: dict[str, AssetType] = {
    "KPI":       AssetType.CALCULATION,
    "Attribute": AssetType.COLUMN,
}

# ── Verdict labels (carried into attributes for downstream use) ─────────────

VERDICT_NOTES: dict[str, str] = {
    "Keep":        "rationalization_verdict:keep",
    "Retire":      "rationalization_verdict:retire",
    "Merge":       "rationalization_verdict:merge",
    "Standardize": "rationalization_verdict:standardize",
}


# ── Helper functions ────────────────────────────────────────────────────────

def _resolve_asset_type(row: dict) -> AssetType:
    """Determine AssetType from semantic_type first, item_type as fallback.
    MDX-style Tableau values (e.g. '[City].[Name]') are skipped — they don't
    map to our taxonomy and the item_type fallback is more accurate for those.
    """
    semantic = (row.get("semantic_type") or "").lower().strip()
    if semantic and not semantic.startswith("[") and semantic in SEMANTIC_TYPE_TO_ASSET_TYPE:
        return SEMANTIC_TYPE_TO_ASSET_TYPE[semantic]
    item = row.get("item_type") or "Attribute"
    return ITEM_TYPE_FALLBACK.get(item, AssetType.COLUMN)


def _resolve_source_tool(row: dict) -> str:
    """Normalize source_tool string to a lowercase slug."""
    tool = row.get("source_tool") or ""
    if not tool:
        return "unknown"
    tool_lower = tool.lower().strip()
    if "power bi" in tool_lower or "powerbi" in tool_lower:
        return "powerbi"
    if "tableau" in tool_lower:
        return "tableau"
    if "qlik" in tool_lower:
        return "qlik"
    return tool_lower.replace(" ", "_")


def _sanitize_asset_id(row: dict) -> str:
    """
    Use the row's asset_id if it looks valid; fall back to a synthetic ID
    built from entry_id when the raw ID is empty or starts with '$' (malformed).

    Malformed examples: "$Customer State Hi" (missing prefix), "" (empty).
    """
    raw_id = (row.get("asset_id") or "").strip()
    entry_id = row.get("entry_id", "unknown")

    if not raw_id or raw_id.startswith("$"):
        source_tool = _resolve_source_tool(row)
        name_slug = re.sub(
            r"[^a-z0-9]+", "_", (row.get("name") or "unknown").lower()
        ).strip("_")
        return f"{source_tool}::catalog::{entry_id}::{name_slug}"

    return raw_id


def _parse_top3_matches(top3_str: Optional[str]) -> list[dict]:
    """
    Parse the pipe-separated top3_matches string into a structured list.
    Format: "Name [Tool] (score) | Name2 [Tool2] (score2) | ..."
    """
    if not top3_str:
        return []
    results = []
    for part in top3_str.split("|"):
        part = part.strip()
        score_match = re.search(r"\(([0-9.]+)\)\s*$", part)
        score = float(score_match.group(1)) if score_match else None
        tool_match = re.search(r"\[([^\]]*)\]", part)
        tool = tool_match.group(1).strip() if tool_match else ""
        name = re.sub(r"\[[^\]]*\].*$", "", part).strip()
        if name:
            results.append({"name": name, "tool": tool, "score": score})
    return results


# ── Core mapping function ───────────────────────────────────────────────────

def catalog_row_to_asset_record(row: dict) -> AssetRecord:
    """
    Convert a single kpi_rationalized_catalog row (as dict) to an AssetRecord.
    All field mapping decisions live here.
    """
    asset_id = _sanitize_asset_id(row)
    asset_type = _resolve_asset_type(row)
    source_tool = _resolve_source_tool(row)

    attributes = {
        "data_type":           row.get("data_type"),
        "semantic_type":       row.get("semantic_type"),
        "formula":             row.get("formula"),
        "normalized_formula":  row.get("normalized_formula"),
        "item_type":           row.get("item_type"),
        # Rationalization context — flows into enrichment prompt
        "ai_verdict":          row.get("ai_verdict"),
        "ai_verdict_refined":  row.get("ai_verdict_refined"),
        "rationale_refined":   row.get("rationale_refined"),
        "similarity_score":    row.get("similarity_score"),
        "top_match":           row.get("top_match"),
        "top3_matches_parsed": _parse_top3_matches(row.get("top3_matches")),
        "overlap_group_id":    row.get("overlap_group_id"),
        "is_overlap":          row.get("is_overlap", False),
        "entry_id":            row.get("entry_id"),
        "job_id":              row.get("job_id"),
    }

    context = AssetContext(
        source_tool=source_tool,
        model_id=row.get("job_id", ""),
        model_name=row.get("report_name", ""),
        table_name=row.get("table_folder"),
        domain=row.get("table_folder"),       # best available proxy for domain
        technical_summary=row.get("description") or "",
    )

    return AssetRecord(
        asset_id=asset_id,
        asset_type=asset_type,
        name=row.get("name", ""),
        description=row.get("description"),
        state=AssetState.EXTRACTED,
        attributes=attributes,
        context=context,
    )


# ── PostgreSQL fetch functions ───────────────────────────────────────────────

async def fetch_catalog_by_job_id(
    job_id: str,
    conn_str: str,
    schema: str = "public",
    verdict_filter: Optional[list[str]] = None,
    item_type_filter: Optional[str] = None,
) -> list[AssetRecord]:
    """
    Fetch all rows for a given job_id from kpi_rationalized_catalog
    and convert them to AssetRecord objects.

    Args:
        job_id: The rationalization job ID to fetch.
        conn_str: PostgreSQL connection string (from config.postgres_conn_str).
        schema: Postgres schema name (from config.postgres_schema).
        verdict_filter: Optional list of ai_verdict_refined values to include,
                        e.g. ["Keep", "Merge", "Standardize"]. None = all verdicts.
        item_type_filter: Optional "KPI" or "Attribute". None = both.

    Returns:
        List of AssetRecord objects ready for the enrichment pipeline.
    """
    table = f"{schema}.kpi_rationalized_catalog"
    conditions = ["job_id = $1"]
    params: list = [job_id]

    if verdict_filter:
        placeholders = ", ".join(f"${i + 2}" for i in range(len(verdict_filter)))
        conditions.append(f"ai_verdict_refined IN ({placeholders})")
        params.extend(verdict_filter)

    if item_type_filter:
        conditions.append(f"item_type = ${len(params) + 1}")
        params.append(item_type_filter)

    where_clause = " AND ".join(conditions)
    query = f"""
        SELECT
            entry_id, job_id, asset_id, item_type, name, source_tool,
            report_name, table_folder, datasource, data_type, semantic_type,
            description, formula, normalized_formula, ai_verdict,
            similarity_score, top_match, rationale, top3_matches,
            overlap_group_id, ai_verdict_refined, rationale_refined, is_overlap
        FROM {table}
        WHERE {where_clause}
        ORDER BY overlap_group_id NULLS LAST, item_type, name
    """

    conn = await asyncpg.connect(conn_str)
    try:
        rows = await conn.fetch(query, *params)
        logger.info("Fetched %d rows for job_id=%s", len(rows), job_id)
        records = []
        for row in rows:
            try:
                records.append(catalog_row_to_asset_record(dict(row)))
            except Exception as exc:
                logger.warning(
                    "Skipping malformed row entry_id=%s: %s",
                    row.get("entry_id"),
                    exc,
                )
        return records
    finally:
        await conn.close()


async def list_available_jobs(conn_str: str, schema: str = "public") -> list[dict]:
    """
    Return all unique job_ids in the catalog with summary counts.
    Used by GET /assets/jobs.
    """
    table = f"{schema}.kpi_rationalized_catalog"
    query = f"""
        SELECT
            job_id,
            COUNT(*)                                          AS total_assets,
            COUNT(*) FILTER (WHERE item_type = 'KPI')        AS kpi_count,
            COUNT(*) FILTER (WHERE item_type = 'Attribute')  AS attribute_count,
            COUNT(DISTINCT source_tool)                       AS source_tool_count,
            MIN(ai_verdict_refined)                           AS sample_verdict,
            MAX(entry_id)                                     AS latest_entry
        FROM {table}
        GROUP BY job_id
        ORDER BY latest_entry DESC
    """
    conn = await asyncpg.connect(conn_str)
    try:
        rows = await conn.fetch(query)
        return [dict(row) for row in rows]
    finally:
        await conn.close()
