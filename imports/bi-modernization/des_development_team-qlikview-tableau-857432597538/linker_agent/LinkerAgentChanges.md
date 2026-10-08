# Linker Agent — PostgreSQL Integration Implementation Plan
## New Input Source: KPI Rationalization Catalog from Postgres

---

## Context for the Implementing Agent

Linker Agent currently accepts a Common Model JSON file directly and parses it into `AssetRecord` objects via `model_parser.py`. The goal of this change is to **add a second input path**: instead of always reading from a JSON file, Linker Agent can now fetch pre-rationalized asset data from a PostgreSQL table (`kpi_rationalized_catalog`) and run the same enrichment pipeline against those records.

The JSON input path is **not removed** — it stays as-is. This is additive.

---

## What the Source Data Looks Like

The PostgreSQL table `kpi_rationalized_catalog` has one row per asset. Key fields:

```
entry_id           String PK  — unique row identifier
job_id             String     — groups all rows from one rationalization run
asset_id           Text       — RE-style asset identifier (non-unique currently, handle gracefully)
item_type          String     — "KPI" or "Attribute"
name               String     — asset name e.g. "CAGR (%)"
source_tool        String     — "Power BI", "Tableau", "Qlik"
report_name        String     — dashboard/workbook name
table_folder       String     — table or folder the asset lives in
datasource         String     — raw datasource reference (nullable)
data_type          String     — "decimal", "string", "number", etc.
semantic_type      String     — "sum", "growth_rate", "identifier", "discount", etc.
description        Text       — technical description
formula            Text       — raw formula string (null for Attributes)
normalized_formula Text       — normalized version of formula
ai_verdict         String     — initial verdict: Keep / Merge / Retire / Standardize
similarity_score   Float      — 0.0–1.0 similarity to top match
top_match          Text       — "Name [Source Tool]" of closest match
rationale          Text       — AI rationale for initial verdict
top3_matches       Text       — pipe-separated "Name [Tool] (score) | ..."
overlap_group_id   Integer    — groups semantically related assets
ai_verdict_refined String     — final verdict after GPT refinement
rationale_refined  Text       — refined rationale
is_overlap         Boolean    — true if asset is part of an overlap group
```

### Important observations from the sample data

1. **Asset IDs are still non-unique** across tools. Tableau assets use a different format (`[Calculation_xxx]$name`) than Power BI assets. Some attribute IDs are malformed (e.g. `$Customer State Hi` — missing prefix). Handle gracefully: if asset_id is malformed or empty, generate a synthetic ID from `entry_id`.

2. **item_type is either "KPI" or "Attribute"** — maps directly to our AssetType enum. KPIs map to `CALCULATION` or `KPI`. Attributes map to `COLUMN`, `DIMENSION`, or `MEASURE` based on `semantic_type`.

3. **ai_verdict_refined is the authoritative verdict** — not ai_verdict. Always use `ai_verdict_refined` when filtering or routing.

4. **overlap_group_id groups related assets** — assets with the same group ID were identified as overlapping/duplicate. This is useful context for enrichment.

5. **formula is null for Attributes** — only KPIs have formulas. Attributes have null or empty normalized_formula.

6. **source_tool can be null** (2 cases in sample) — handle with a fallback of "unknown".

---

## Changes Required

### Overview

```
BEFORE:
  POST /assets/ingest-model  ←  JSON file  →  model_parser.py  →  AssetRecord[]  →  3-tier pipeline

AFTER (additive):
  POST /assets/ingest-model  ←  JSON file  →  model_parser.py  →  AssetRecord[]  →  3-tier pipeline
  POST /assets/ingest-from-postgres  ←  job_id  →  postgres_fetcher.py  →  AssetRecord[]  →  3-tier pipeline
  GET  /assets/jobs           ←  lists available job_ids in postgres
```

---

## Files to Create

### 1. `ingestion/postgres_fetcher.py`

Fetches rows from `kpi_rationalized_catalog` by `job_id` and converts them to `AssetRecord` objects.

```python
"""
Fetches rationalized KPI catalog rows from PostgreSQL and converts
them to AssetRecord objects for the Linker Agent enrichment pipeline.

The postgres connection is configured via environment variables.
Mirrors the same output contract as model_parser.py — both produce list[AssetRecord].
"""

from __future__ import annotations
import re
import logging
from typing import Optional
import asyncpg  # or use sqlalchemy async — see config note below

from models.asset_record import (
    AssetRecord, AssetType, AssetState, AssetContext
)

logger = logging.getLogger(__name__)

# ── Asset type mapping ──────────────────────────────────────────────────────

SEMANTIC_TYPE_TO_ASSET_TYPE = {
    "growth_rate":  AssetType.KPI,
    "ratio":        AssetType.KPI,
    "cagr":         AssetType.KPI,
    "sum":          AssetType.CALCULATION,
    "count":        AssetType.CALCULATION,
    "average":      AssetType.CALCULATION,
    "min":          AssetType.CALCULATION,
    "max":          AssetType.CALCULATION,
    "discount":     AssetType.CALCULATION,
    "identifier":   AssetType.COLUMN,
    "dimension":    AssetType.DIMENSION,
    "measure":      AssetType.MEASURE,
    "date":         AssetType.COLUMN,
}

ITEM_TYPE_FALLBACK = {
    "KPI":       AssetType.CALCULATION,
    "Attribute": AssetType.COLUMN,
}

# ── Verdict to downstream state ─────────────────────────────────────────────

VERDICT_TO_NOTES = {
    "Keep":        "rationalization_verdict:keep",
    "Retire":      "rationalization_verdict:retire",
    "Merge":       "rationalization_verdict:merge",
    "Standardize": "rationalization_verdict:standardize",
}


def _resolve_asset_type(row: dict) -> AssetType:
    """Determine AssetType from semantic_type first, item_type as fallback."""
    semantic = (row.get("semantic_type") or "").lower().strip()
    if semantic and semantic in SEMANTIC_TYPE_TO_ASSET_TYPE:
        return SEMANTIC_TYPE_TO_ASSET_TYPE[semantic]
    item = row.get("item_type") or "Attribute"
    return ITEM_TYPE_FALLBACK.get(item, AssetType.COLUMN)


def _resolve_source_tool(row: dict) -> str:
    """Normalize source_tool string to lowercase slug."""
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
    Use the row's asset_id if it looks valid.
    Fall back to a synthetic ID from entry_id if malformed.

    Valid pattern: contains at least one '$' separator with a non-empty right side.
    Malformed examples: "$Customer State Hi" (missing prefix), "" (empty).
    """
    raw_id = (row.get("asset_id") or "").strip()
    entry_id = row.get("entry_id", "unknown")

    # Malformed: starts with $ (missing prefix) or empty
    if not raw_id or raw_id.startswith("$"):
        source_tool = _resolve_source_tool(row)
        name_slug = re.sub(r"[^a-z0-9]+", "_", (row.get("name") or "unknown").lower()).strip("_")
        return f"{source_tool}::catalog::{entry_id}::{name_slug}"

    return raw_id


def _parse_top3_matches(top3_str: Optional[str]) -> list[dict]:
    """
    Parse pipe-separated top3_matches string into structured list.
    Format: "Name [Tool] (score) | Name2 [Tool2] (score2) | ..."
    Returns: [{"name": ..., "tool": ..., "score": ...}, ...]
    """
    if not top3_str:
        return []
    results = []
    for part in top3_str.split("|"):
        part = part.strip()
        # Extract score
        score_match = re.search(r'\(([0-9.]+)\)\s*$', part)
        score = float(score_match.group(1)) if score_match else None
        # Extract tool from [Tool]
        tool_match = re.search(r'\[([^\]]*)\]', part)
        tool = tool_match.group(1).strip() if tool_match else ""
        # Name is everything before [Tool]
        name = re.sub(r'\[[^\]]*\].*$', '', part).strip()
        if name:
            results.append({"name": name, "tool": tool, "score": score})
    return results


def catalog_row_to_asset_record(row: dict) -> AssetRecord:
    """
    Convert a single kpi_rationalized_catalog row (as dict) to an AssetRecord.
    This is the core mapping function — all field decisions live here.
    """
    asset_id = _sanitize_asset_id(row)
    asset_type = _resolve_asset_type(row)
    source_tool = _resolve_source_tool(row)

    # Build attributes dict — type-specific fields
    attributes = {
        "data_type":           row.get("data_type"),
        "semantic_type":       row.get("semantic_type"),
        "formula":             row.get("formula"),
        "normalized_formula":  row.get("normalized_formula"),
        "item_type":           row.get("item_type"),
        # Rationalization context — carries forward into enrichment prompt
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

    # Context — what the enrichment pipeline uses for LLM prompt assembly
    context = AssetContext(
        source_tool=source_tool,
        model_id=row.get("job_id", ""),
        model_name=row.get("report_name", ""),
        table_name=row.get("table_folder"),
        domain=row.get("table_folder"),      # best proxy for domain we have
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
    verdict_filter: Optional[list[str]] = None,
    item_type_filter: Optional[str] = None,
) -> list[AssetRecord]:
    """
    Fetch all rows for a given job_id from kpi_rationalized_catalog
    and convert to AssetRecord objects.

    Args:
        job_id: The rationalization job ID to fetch.
        conn_str: PostgreSQL connection string (from config/env).
        verdict_filter: Optional list of ai_verdict_refined values to include.
                        e.g. ["Keep", "Merge", "Standardize"] to exclude Retire.
                        If None, all verdicts are included.
        item_type_filter: Optional "KPI" or "Attribute" to fetch only one type.
                         If None, both types are fetched.

    Returns:
        List of AssetRecord objects ready for the enrichment pipeline.
    """
    # Build query
    conditions = ["job_id = $1"]
    params: list = [job_id]

    if verdict_filter:
        placeholders = ", ".join(f"${i+2}" for i in range(len(verdict_filter)))
        conditions.append(f"ai_verdict_refined IN ({placeholders})")
        params.extend(verdict_filter)

    if item_type_filter:
        conditions.append(f"item_type = ${len(params)+1}")
        params.append(item_type_filter)

    where_clause = " AND ".join(conditions)
    query = f"""
        SELECT
            entry_id, job_id, asset_id, item_type, name, source_tool,
            report_name, table_folder, datasource, data_type, semantic_type,
            description, formula, normalized_formula, ai_verdict,
            similarity_score, top_match, rationale, top3_matches,
            overlap_group_id, ai_verdict_refined, rationale_refined, is_overlap
        FROM kpi_rationalized_catalog
        WHERE {where_clause}
        ORDER BY overlap_group_id NULLS LAST, item_type, name
    """

    conn = await asyncpg.connect(conn_str)
    try:
        rows = await conn.fetch(query, *params)
        logger.info(f"Fetched {len(rows)} rows for job_id={job_id}")
        records = []
        for row in rows:
            try:
                records.append(catalog_row_to_asset_record(dict(row)))
            except Exception as e:
                logger.warning(f"Skipping malformed row entry_id={row.get('entry_id')}: {e}")
        return records
    finally:
        await conn.close()


async def list_available_jobs(conn_str: str) -> list[dict]:
    """
    Return all unique job_ids in the catalog with summary stats.
    Used by the GET /assets/jobs endpoint.
    """
    query = """
        SELECT
            job_id,
            COUNT(*) as total_assets,
            COUNT(*) FILTER (WHERE item_type = 'KPI') as kpi_count,
            COUNT(*) FILTER (WHERE item_type = 'Attribute') as attribute_count,
            COUNT(DISTINCT source_tool) as source_tool_count,
            MIN(ai_verdict_refined) as sample_verdict,
            MAX(entry_id) as latest_entry
        FROM kpi_rationalized_catalog
        GROUP BY job_id
        ORDER BY latest_entry DESC
    """
    conn = await asyncpg.connect(conn_str)
    try:
        rows = await conn.fetch(query)
        return [dict(row) for row in rows]
    finally:
        await conn.close()
```

---

### 2. `ingestion/context_builder_postgres.py`

The existing `context_builder.py` branches on `asset_type`. Assets from Postgres carry additional rationalization context (verdict, overlap group, top matches) that should flow into the LLM prompt. Add a new function that extends the existing context with this data.

```python
"""
Extends context_builder.py for assets sourced from the rationalized catalog.
Adds rationalization context (verdict, overlap group, top matches) to the
LLM prompt so the enrichment agent understands the asset's governance status.

Import and call build_context_from_catalog() instead of build_context()
when the asset originated from the Postgres catalog.
"""

from ingestion.context_builder import build_context, EnrichmentContext
from models.asset_record import AssetRecord


def build_context_from_catalog(asset: AssetRecord) -> EnrichmentContext:
    """
    Build enrichment context for a catalog-sourced asset.
    Calls the base build_context() then appends rationalization context
    to the technical_description and enrichment_hint fields.
    """
    ctx = build_context(asset)
    attrs = asset.attributes

    verdict = attrs.get("ai_verdict_refined") or attrs.get("ai_verdict") or "Unknown"
    rationale = attrs.get("rationale_refined") or attrs.get("rationale") or ""
    overlap_id = attrs.get("overlap_group_id")
    top3 = attrs.get("top3_matches_parsed") or []
    is_overlap = attrs.get("is_overlap", False)
    similarity = attrs.get("similarity_score")

    # Append rationalization context to the technical description
    rationalization_context = (
        f"\n\nRationalization verdict: {verdict}. "
        + (f"Rationale: {rationale} " if rationale else "")
        + (f"Overlap group: {overlap_id}. " if overlap_id else "")
        + (f"Similarity to top match: {similarity:.2f}. " if similarity else "")
    )

    if top3:
        matches_str = " | ".join(
            f"{m['name']} ({m['tool']}, score={m['score']})" for m in top3[:3]
        )
        rationalization_context += f"Top similar assets: {matches_str}."

    # Extend the context fields
    ctx.technical_description += rationalization_context

    if is_overlap and overlap_id:
        ctx.enrichment_hint += (
            f" Note: this asset belongs to overlap group {overlap_id} with "
            f"{len(top3)} similar assets — the business definition should "
            f"clearly differentiate it from semantically similar assets."
        )

    return ctx
```

---

### 3. `api/routes/assets.py` — Add two new endpoints

Add these two endpoints to the existing `assets.py` router. Do not modify existing endpoints.

```python
# ── Add these imports at the top of assets.py ──
from ingestion.postgres_fetcher import fetch_catalog_by_job_id, list_available_jobs
from ingestion.context_builder_postgres import build_context_from_catalog
from config import get_config

# ── Add these two endpoints ──

@router.post("/ingest-from-postgres", response_model=list[AssetLinkResult])
async def ingest_from_postgres(
    job_id: str,
    verdict_filter: Optional[list[str]] = Query(
        default=None,
        description="Filter by ai_verdict_refined. Options: Keep, Merge, Retire, Standardize. "
                    "Default: all verdicts included. Recommended: exclude Retire for enrichment."
    ),
    item_type: Optional[str] = Query(
        default=None,
        description="Filter by item_type: 'KPI' or 'Attribute'. Default: both."
    ),
    service: AssetMatcherService = Depends(get_asset_matcher_service),
):
    """
    Fetch rationalized assets from the kpi_rationalized_catalog Postgres table
    by job_id, then run the full 3-tier enrichment pipeline on all fetched assets.

    Writes results to output/enrichment_results.json and appends to event_log.jsonl.

    Recommended usage: exclude 'Retire' verdicts since those assets are being
    deprecated and enrichment adds no value.
    Example: POST /assets/ingest-from-postgres?job_id=xxx&verdict_filter=Keep&verdict_filter=Merge&verdict_filter=Standardize
    """
    config = get_config()
    try:
        assets = await fetch_catalog_by_job_id(
            job_id=job_id,
            conn_str=config.postgres_conn_str,
            verdict_filter=verdict_filter,
            item_type_filter=item_type,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Postgres fetch failed: {e}")

    if not assets:
        raise HTTPException(
            status_code=404,
            detail=f"No assets found for job_id={job_id} with the given filters."
        )

    # Use catalog-aware context builder by patching the service's context fn
    # (see implementation note below for the cleaner approach)
    results = await service.enrich_batch(
        assets,
        context_builder_override=build_context_from_catalog
    )

    # Write results to output files (same as ingest-model)
    _write_enrichment_output(results)

    return results


@router.get("/jobs", response_model=list[dict])
async def list_jobs():
    """
    List all available rationalization job_ids in the Postgres catalog,
    with asset counts per job. Use this to find the job_id before calling
    /assets/ingest-from-postgres.
    """
    config = get_config()
    try:
        jobs = await list_available_jobs(config.postgres_conn_str)
        return jobs
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Postgres unavailable: {e}")
```

---

### 4. `core/asset_matcher_service.py` — Add context_builder_override parameter

The `enrich_batch()` method currently calls `build_context(asset)` directly. Add an optional parameter that allows the caller to supply a different context builder function. This avoids duplicating the batch logic.

```python
# In AssetMatcherService.enrich_batch(), change signature to:

async def enrich_batch(
    self,
    assets: list[AssetRecord],
    max_concurrent: int = 5,
    context_builder_override=None,   # ← ADD THIS
) -> list[AssetLinkResult]:
    """
    context_builder_override: optional callable(AssetRecord) -> EnrichmentContext.
    If provided, replaces the default build_context() call.
    Use build_context_from_catalog() for assets sourced from Postgres.
    """
    context_fn = context_builder_override or build_context  # ← USE THIS

    # Rest of method unchanged — just replace build_context(asset) calls
    # with context_fn(asset)
```

---

### 5. `config.py` — Add PostgreSQL connection string

```python
# Add to the existing Pydantic Settings model in config.py:

# PostgreSQL — KPI rationalization catalog
POSTGRES_HOST:     str = Field(default="localhost", env="POSTGRES_HOST")
POSTGRES_PORT:     int = Field(default=5432,        env="POSTGRES_PORT")
POSTGRES_DB:       str = Field(default="",          env="POSTGRES_DB")
POSTGRES_USER:     str = Field(default="",          env="POSTGRES_USER")
POSTGRES_PASSWORD: str = Field(default="",          env="POSTGRES_PASSWORD")
POSTGRES_SCHEMA:   str = Field(default="public",    env="POSTGRES_SCHEMA")

@property
def postgres_conn_str(self) -> str:
    return (
        f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
        f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    )
```

```env
# Add to .env:
POSTGRES_HOST=your-postgres-host
POSTGRES_PORT=5432
POSTGRES_DB=your-database
POSTGRES_USER=your-user
POSTGRES_PASSWORD=your-password
POSTGRES_SCHEMA=public
```

---

### 6. `requirements.txt` — Add asyncpg

```
asyncpg>=0.29.0
```

---

## Files to Modify (summary)

| File | Change |
|---|---|
| `ingestion/postgres_fetcher.py` | **CREATE** — full file above |
| `ingestion/context_builder_postgres.py` | **CREATE** — full file above |
| `api/routes/assets.py` | **ADD** two endpoints, two imports |
| `core/asset_matcher_service.py` | **ADD** `context_builder_override` param to `enrich_batch()` |
| `config.py` | **ADD** 6 Postgres config fields + `postgres_conn_str` property |
| `requirements.txt` | **ADD** `asyncpg>=0.29.0` |

---

## Field Mapping — Postgres Row → AssetRecord

| Postgres field | Maps to | Notes |
|---|---|---|
| `entry_id` | `attributes.entry_id` | Stable row PK, used for synthetic ID generation |
| `job_id` | `context.model_id`, `attributes.job_id` | Groups assets from same run |
| `asset_id` | `asset_id` (sanitized) | Malformed IDs get synthetic fallback |
| `item_type` | `asset_type` (with semantic_type taking precedence) | KPI → CALCULATION/KPI, Attribute → COLUMN/DIMENSION/MEASURE |
| `name` | `name` | Direct |
| `source_tool` | `context.source_tool` (normalized) | "Power BI" → "powerbi" |
| `report_name` | `context.model_name` | |
| `table_folder` | `context.table_name`, `context.domain` | Best proxy available |
| `data_type` | `attributes.data_type` | |
| `semantic_type` | `attributes.semantic_type` | Also drives asset_type resolution |
| `description` | `description`, `context.technical_summary` | |
| `formula` | `attributes.formula` | Null for Attributes |
| `normalized_formula` | `attributes.normalized_formula` | |
| `ai_verdict_refined` | `attributes.ai_verdict_refined` | **Use this, not ai_verdict** |
| `rationale_refined` | `attributes.rationale_refined` | |
| `similarity_score` | `attributes.similarity_score` | |
| `top_match` | `attributes.top_match` | |
| `top3_matches` | `attributes.top3_matches_parsed` (parsed list) | Parsed from pipe-separated string |
| `overlap_group_id` | `attributes.overlap_group_id` | |
| `is_overlap` | `attributes.is_overlap` | |

---

## What the Enrichment Pipeline Receives

The 3-tier engine is completely unchanged. It receives the same `AssetRecord` and `EnrichmentContext` objects it always has. The only difference is:

1. The records come from Postgres instead of a JSON file
2. The context includes rationalization context (verdict, overlap group, top matches) appended to the `technical_description`
3. The LLM therefore knows "this KPI has been rationalized as Standardize — give it a clear, differentiated definition"

For a **Keep** verdict asset: the enrichment produces the business definition and catalog write-back proceeds normally.

For a **Merge** verdict asset: the enrichment produces the business definition. The steward gate will show the merge recommendation alongside the enriched definition and let the steward confirm.

For a **Retire** verdict asset: **recommended to exclude from enrichment via `verdict_filter`** — enriching assets that are being retired wastes LLM calls and produces catalog entries that will be deprecated immediately.

For a **Standardize** verdict asset: the enrichment prompt should encourage a definition that clearly differentiates this asset from its top matches. The `context_builder_postgres.py` extension handles this via the enrichment_hint addition.

---

## Testing — What to Validate

### Test 1: Fetch converts all 114 rows without errors
```python
records = await fetch_catalog_by_job_id(
    job_id="06a07733-3f43-401a-b397-fee8b2457575",
    conn_str=test_conn_str
)
assert len(records) == 114
assert all(r.asset_id for r in records)
assert all("$" not in r.asset_id or not r.asset_id.startswith("$") for r in records)
```

### Test 2: Malformed IDs get synthetic fallback
```python
malformed_row = {
    "entry_id": "abc123",
    "asset_id": "$Customer State Hi",  # malformed
    "name": "Customer State Hi",
    "source_tool": "Power BI",
    # ... other fields
}
record = catalog_row_to_asset_record(malformed_row)
assert not record.asset_id.startswith("$")
assert "abc123" in record.asset_id  # entry_id used in fallback
```

### Test 3: Verdict filter works
```python
records = await fetch_catalog_by_job_id(
    job_id="...",
    conn_str=test_conn_str,
    verdict_filter=["Keep", "Merge", "Standardize"]
)
assert all(r.attributes["ai_verdict_refined"] != "Retire" for r in records)
```

### Test 4: Semantic type drives asset_type correctly
```python
kpi_row = {"semantic_type": "growth_rate", "item_type": "KPI", ...}
record = catalog_row_to_asset_record(kpi_row)
assert record.asset_type == AssetType.KPI  # semantic_type wins over item_type

attr_row = {"semantic_type": "identifier", "item_type": "Attribute", ...}
record = catalog_row_to_asset_record(attr_row)
assert record.asset_type == AssetType.COLUMN
```

### Test 5: Context builder adds rationalization context
```python
from ingestion.context_builder_postgres import build_context_from_catalog
ctx = build_context_from_catalog(record_with_merge_verdict)
assert "Rationalization verdict: Merge" in ctx.technical_description
assert "Top similar assets" in ctx.technical_description
```

### Test 6: End-to-end route test
```python
response = await client.post(
    "/assets/ingest-from-postgres",
    params={"job_id": "06a07733...", "verdict_filter": ["Keep", "Merge", "Standardize"]}
)
assert response.status_code == 200
results = response.json()
assert len(results) > 0
assert all(r["asset_id"] for r in results)
assert all(r["linkage_type"] in ("direct", "semantic", "generated", "no_match") for r in results)
```

---

## Notes for the Implementing Agent

**On the asyncpg choice:** If the codebase already uses SQLAlchemy, use `sqlalchemy.ext.asyncio` instead of raw asyncpg. The query logic is identical; only the connection and fetch calls differ. Check for existing `database.py` or `db.py` in the codebase before adding asyncpg.

**On connection pooling:** For production, wrap the connection in a pool managed by the FastAPI lifespan (same pattern as `SwaggerAPIClient` in the existing code). For the initial implementation, per-request connections are acceptable.

**On the `context_builder_override` pattern:** The cleanest way to implement this in `enrich_batch()` is a simple callable parameter with a default. Do not subclass `AssetMatcherService` for this — it adds unnecessary complexity.

**On Retire filtering:** The recommended default is to exclude Retire assets. The endpoint accepts this as a query parameter rather than hardcoding it, so callers have flexibility. But the documentation should make clear that enriching Retire assets is wasteful.

**On the `top3_matches` parsing:** The pipe-separated string `"Total Premium_Payable [Power BI] (0.89) | Total Annual_Premium [Power BI] (0.89)"` should be parsed into a list of structured dicts at ingestion time. Do not pass the raw string to the LLM prompt — parse it first and format it cleanly in the context builder.

**On schema prefix:** The Postgres schema name is configurable via `POSTGRES_SCHEMA`. The query should reference `{schema}.kpi_rationalized_catalog`. Use the `SCHEMA` variable pattern that the `KpiRationalizedCatalog` SQLAlchemy model already uses.
