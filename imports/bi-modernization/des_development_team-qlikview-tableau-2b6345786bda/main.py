import os
import io
import json
import importlib.util
import traceback
import zipfile
import shutil
import asyncio
import aiofiles
from pathlib import Path
from datetime import datetime, timezone
 
import uuid
import uvicorn
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from typing import Any, Dict, List, Optional
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder

#import llm guard
from llm_guard_service import guard_service
def _sanitize_prompt(user_prompt: str) -> str:
    """Sanitize every outbound LLM prompt before sending it to Azure OpenAI."""
    result = guard_service.sanitize_input(user_prompt)
    safe_prompt = result["sanitized_prompt"]
    print("Original Prompt:", user_prompt)
    print("Sanitized Prompt:", safe_prompt)
    print("Is Valid:", result["is_valid"])
    print("Risk Score:", result["risk_score"])
    if not result.get("is_valid", True):
        raise HTTPException(
            status_code=400,
            detail=(
                "Prompt guard blocked unsafe prompt "
                f"(risk_score={result.get('risk_score')})."
            ),
        )
    return safe_prompt

# ── Load validator (filename contains a space, so use importlib) ──────────────
_VALIDATOR_PATH = Path(__file__).parent / "validation" / "step2_validator 4.py"
_val_spec   = importlib.util.spec_from_file_location("step2_validator", _VALIDATOR_PATH)
_val_module = importlib.util.module_from_spec(_val_spec)
_val_spec.loader.exec_module(_val_module)
_run_validation = _val_module.run_validation

# ── Load Tableau validator ────────────────────────────────────────────────────
_TABLEAU_VALIDATOR_PATH = Path(__file__).parent / "validation" / "tableau_validator.py"
_tableau_val_spec   = importlib.util.spec_from_file_location("tableau_validator", _TABLEAU_VALIDATOR_PATH)
_tableau_val_module = importlib.util.module_from_spec(_tableau_val_spec)
_tableau_val_spec.loader.exec_module(_tableau_val_module)
_run_tableau_validation = _tableau_val_module.run_validation


 
# Tableau-related imports
from sequentialworkflow import run_single_tenant_flow_processor as run_tableau_flow  # unchanged
 
# QlikView-related imports
from agents_qlikview import run_single_tenant_flow_processor as run_qlik_flow  # unchanged
 
# PowerBI-related imports
from powerbi_extractor import extract_powerbi_model
from layout_mapper import map_layout_to_datamodel
from agents_powerbi import run_single_tenant_flow_processor as run_powerbi_flow
from config import azure_client

# Image asset collection (base64-encoded, injected directly on image visuals)
from image_asset_collector import inject_inline_image_data_tableau, inject_inline_image_data_powerbi
 
# Storage imports
from databricks_normalizer import normalize_tableau, normalize_qlikview, normalize_powerbi
from postgres_writer import save_extraction_log, upsert_job_progress, lookup_by_checksum
from postgres_dedup import run_dedup_check
 
import re as _re
from pathlib import Path as _Path
import hashlib as _hashlib


def _compute_checksum(data: bytes) -> str:
    """Return the SHA-256 hex digest of *data* (raw file bytes)."""
    return _hashlib.sha256(data).hexdigest()


async def _make_ai_summary(technical_summary: str) -> str:
    """
    Use the shared azure_client (AzureOpenAIChatCompletionClient) to distil
    *technical_summary* into a coherent ≤50-word executive summary.
    Falls back to empty string on any error.
    """
    if not technical_summary or not technical_summary.strip():
        return ""
    try:
        from autogen_core.models import SystemMessage as _SystemMessage, UserMessage as _UserMessage
        messages = [
            _SystemMessage(
                content=(
                    "You are a concise business analyst. "
                    "Summarise the following BI report description in exactly 50 words or fewer. "
                    "The summary must be a single coherent paragraph that captures the report's "
                    "purpose, key metrics, and business value. "
                    "Return only the summary text — no labels, no bullet points."
                )
            ),
            _UserMessage(content=technical_summary, source="user"),
        ]
        response = await azure_client.create(messages)
        summary = response.content.strip()
        print(f"[ai_summary] Generated ({len(summary)} chars): {summary[:120]}{'…' if len(summary) > 120 else ''}")
        return summary
    except Exception as e:
        import traceback as _tb
        print(f"[ai_summary] LLM call failed: {e}\n{_tb.format_exc()}")
        return ""

 
# ---------------------------------------------------------------------------
# Log message constants (avoids SonarQube duplicate-literal warnings)
# ---------------------------------------------------------------------------
 
# ---------------------------------------------------------------------------
# In-memory job store  { job_id -> { file_name -> progress_dict } }
# Flushed to Postgres on every GET /jobs/{job_id}/progress call.
# ---------------------------------------------------------------------------
_job_store: Dict[str, Dict[str, dict]] = {}
 
 
def _init_file_progress(job_id: str, file_name: str, etltool: str) -> dict:
    """Create the initial progress record for one file in a batch job."""
    now = datetime.now(timezone.utc)
    return {
        "progress_id": str(uuid.uuid4()),
        "job_id": job_id,
        "file_name": file_name,
        "etltool": etltool,
        "status": "queued",
        "step": "Waiting to start",
        "started_at": now,
        "updated_at": now,
        "completed_at": None,
        "runtime_seconds": None,
        "error": None,
        "postgres_stored": False,
    }
 
 
def _update_progress(job_id: str, file_name: str, **kwargs: Any) -> None:
    """Mutate the in-memory record for a file. Always bumps updated_at."""
    if job_id in _job_store and file_name in _job_store[job_id]:
        _job_store[job_id][file_name].update(kwargs)
        _job_store[job_id][file_name]["updated_at"] = datetime.now(timezone.utc)
 
 
def _extract_powerbi_source(step: dict) -> str:
    """Return source file name from a PowerBI 'read' ingestion step, or empty string."""
    pq = step.get("native_expressions", {}).get("powerquery", "")
    if not pq:
        return ""
    m = _re.search(r'File\.Contents\(["\']([^"\']+)["\']', pq)
    if m:
        return _Path(m.group(1).replace("\\\\", "\\")).name
    m = _re.search(r'Source\s*=\s*#"([^"]+)"', pq)
    if m:
        return m.group(1)
    return ""
 
 
def _extract_tableau_source(step: dict) -> str:
    """Return source file name from a Tableau 'read_source' ingestion step, or empty string."""
    tq = step.get("native_expressions", {}).get("tableau", "")
    if not tq:
        return ""
    m = _re.search(r'READ FILE:\s*(.+)', tq)
    return m.group(1).strip() if m else ""
 
 
def _datasource_from_ingestion(tbl: dict) -> str:
    """Extract source file name from ingestion steps (PowerBI and Tableau formats).

    Step-type-agnostic: scans every step and lets the inner extractors decide
    whether they have a match. The inner regexes (File.Contents, READ FILE,
    Source = #"...") are uniquely identifying, so it's safe to try every step.

    The previous step_type==\"read\" filter broke when the power_query prompt
    was updated to emit step_type==\"powerquery_full\" (one step holding the
    full let..in body instead of one step per M operation). Removing the
    filter restores the linker for CSV / Excel / Web-backed tables under the
    new step naming, and preserves prior behavior for derived tables that
    only contain a `Source = #\"...\"` M reference."""
    for step in tbl.get("ingestion", {}).get("steps", []):
        result = _extract_powerbi_source(step)
        if result:
            return result
        result = _extract_tableau_source(step)
        if result:
            return result
    return ""
 
 
# Visual keys defaulted to None when the LLM omits them. Colors / fonts / borders
# are NOT here — they're filled deterministically as the per-visual `style` object
# by style_extractor.py (text_style, border_style, style_rules were removed).
_VISUAL_EXTRA_KEYS = [
    "datasource_dependencies", "content", "imageUrl", "imageId",
    "navigation_target", "button_type", "has_border",
    "mark_type", "axes", "legends", "tooltip_config", "data_labels",
    "sort_config", "reference_lines", "trend_lines", "dual_axis",
    "conditional_formatting", "annotations", "table_calc_configs",
]


class UniqueIDGenerator:
    """
    Generates structured, globally-unique IDs for every artifact produced
    during a single upload/batch processing call.

    ID format:
        {tool}(toolname)${file}(filename)${val1}({type1})$...$${hex12}(uuid)

    The UUID suffix guarantees uniqueness across upload batches so that
    re-uploading the same file never collides with IDs stored from prior
    runs.  The generator tracks every issued ID within a call and retries
    on the (astronomically unlikely) UUID hex collision.

    Sample IDs:
        powerbi(toolname)$SalesReport(filename)$Financials(datasource)$3f9a1b2c4d5e(uuid)
        tableau(toolname)$Dashboard(filename)$Orders(datasource)$LineItems(table)$a1b2c3d4e5f6(uuid)
        powerbi(toolname)$SalesReport(filename)$Financials(datasource)$Fact Sales(table)$Revenue(column)$9f8e7d6c5b4a(uuid)
    """

    def __init__(self, toolname: str, model_name: str) -> None:
        self._tool  = toolname
        self._model = model_name
        self._seen: set = set()

    # ── internal builder ──────────────────────────────────────────────────────
    def _build(self, *segments) -> str:
        """
        Each segment is a (value, type_label) tuple →  "value(type_label)".
        Empty / None values are skipped.  A UUID hex suffix is always appended.
        """
        parts = [
            f"{self._tool}(toolname)",
            f"{self._model}(filename)",
        ]
        for val, seg_type in segments:
            if val:
                safe = str(val).replace("$", "_").replace("\n", " ")[:80]
                parts.append(f"{safe}({seg_type})")
        uid = uuid.uuid4().hex[:12]
        parts.append(f"{uid}(uuid)")
        result = "$".join(parts)
        while result in self._seen:          # ultra-rare collision guard
            uid = uuid.uuid4().hex[:12]
            parts[-1] = f"{uid}(uuid)"
            result = "$".join(parts)
        self._seen.add(result)
        return result

    # ── public helpers — one per artifact type ────────────────────────────────
    def datasource(self, name: str) -> str:
        return self._build((name, "datasource"))

    def table(self, ds_name: str, tbl_name: str) -> str:
        return self._build((ds_name, "datasource"), (tbl_name, "table"))

    def column(self, ds_name: str, tbl_name: str, col_name: str) -> str:
        return self._build(
            (ds_name, "datasource"), (tbl_name, "table"), (col_name, "column")
        )

    def calculation(self, calc_name: str) -> str:
        return self._build((calc_name, "calculation"))

    def visual(self, page_name: str, visual_title: str = "") -> str:
        segs = [(page_name, "pagename")]
        if visual_title:
            segs.append((visual_title, "visual"))
        return self._build(*segs)

    def relationship(self, left_table: str, right_table: str) -> str:
        return self._build((left_table, "left_table"), (right_table, "right_table"))

    def hierarchy(self, name: str) -> str:
        return self._build((name, "hierarchy"))

    def parameter(self, name: str) -> str:
        return self._build((name, "parameter"))
 
 
def _apply_column_ids(
    columns: list,
    id_gen: "UniqueIDGenerator",
    ds_name: str,
    tbl_name: str,
) -> list:
    """Return columns list with unique ids (structured + UUID) per column."""
    new_cols = []
    for col in columns:
        col_name = col.get("name", "") or ""
        new_col = {"id": id_gen.column(ds_name, tbl_name, col_name)}
        for k, v in col.items():
            if k not in ("id", "col_id"):
                new_col[k] = v
        new_cols.append(new_col)
    return new_cols


def _ds_name_for_table(tbl: dict, data_sources: List[dict]) -> Optional[str]:
    """Resolve the datasource a table belongs to, returning the datasource name.

    Returns ``None`` when the table is not bound to any datasource in
    ``data_sources`` (typical for synthesized tables like ``Parameters``).
    Callers should treat ``None`` as "no real datasource — leave the
    source_data_source_id link empty".

    Resolution order:
      1. Match the table's source_data_source_id against any data source's id
         (covers cases where the LLM preserved the linkage on both sides).
      2. Detect a "<ds_name>.<actual_table>" prefix on the table name. The LLM
         sometimes emits prefixed names to disambiguate federation duplicates
         (e.g. "Market Basket.tbl_sales"). When the prefix matches a known
         data source's name, treat that as the resolved datasource.
      3. Match the table's name against each datasource's `paths` array — the
         path entries are table identifiers like "tbl_sales" or "tbl_sales.csv".
      4. Fall back to the single datasource if there's exactly one.
      5. Otherwise return ``None``.
    """
    tbl_name = tbl.get("name") or ""
    src_ds_id = tbl.get("source_data_source_id") or ""

    if src_ds_id:
        for ds in data_sources:
            if ds.get("id") and ds["id"] == src_ds_id:
                return ds.get("name") or None

    if tbl_name:
        for ds in data_sources:
            ds_name = ds.get("name") or ""
            if ds_name and tbl_name.startswith(ds_name + "."):
                return ds_name

    if tbl_name:
        for ds in data_sources:
            for p in (ds.get("paths") or []):
                if not p:
                    continue
                if p == tbl_name or p.split(".")[0] == tbl_name:
                    return ds.get("name") or None

    if len(data_sources) == 1:
        return data_sources[0].get("name") or None
    return None


def _apply_table_ids(
    result: dict,
    id_gen: "UniqueIDGenerator",
    data_sources: List[dict],
    ds_name_to_new_id: Dict[str, str],
) -> Dict[str, str]:
    """Mutate tables in result with unique ids (structured + UUID) and rebuild
    column ids.  Also rewrites each table's ``source_data_source_id`` to the
    canonical data-source id.

    Returns a map ``{original_table_name: new_table_id}`` for use by the
    relationship-endpoint rewrite.
    """
    name_to_new_id: Dict[str, str] = {}
    for tbl in result.get("tables", []):
        tbl_name = tbl.get("name", "") or ""
        ds_name = _ds_name_for_table(tbl, data_sources)
        if ds_name is None:
            ds_segment = (tbl.get("table_type") or "calculated").lower() or "calculated"
            ds_segment_for_column_id = ds_segment
            tbl["source_data_source_id"] = None
        else:
            ds_segment = ds_name
            ds_segment_for_column_id = ds_name
            tbl["source_data_source_id"] = ds_name_to_new_id.get(ds_name, "")
        new_id = id_gen.table(ds_segment, tbl_name)
        tbl["id"] = new_id
        tbl["columns"] = _apply_column_ids(
            tbl.get("columns", []), id_gen, ds_segment_for_column_id, tbl_name
        )
        if tbl_name:
            name_to_new_id[tbl_name] = new_id
    return name_to_new_id


def _rewrite_relationship_endpoints(result: dict, name_to_table_id: Dict[str, str]) -> None:
    """Rewrite relationships[].left_table_id and right_table_id from bare table
    names (as emitted by the LLM) to the canonical table ids minted by
    ``_apply_table_ids``. Endpoints that don't resolve are left untouched so
    they stay visible as broken references in the output for debugging."""
    unresolved: List[str] = []
    canonical_ids = set(name_to_table_id.values())
    for rel in result.get("relationships", []):
        for endpoint_key in ("left_table_id", "right_table_id"):
            ref = rel.get(endpoint_key)
            if not ref:
                continue
            if ref in name_to_table_id:
                rel[endpoint_key] = name_to_table_id[ref]
            elif ref not in canonical_ids:
                unresolved.append(ref)
    if unresolved:
        print(
            f"[apply_readable_ids] Warning: {len(unresolved)} relationship endpoint(s) "
            f"did not resolve to a known table: {sorted(set(unresolved))}"
        )
 
 
def _transform_visual(
    vis: dict,
    id_gen: "UniqueIDGenerator",
    toolname: str,
    page_name: str,
    force_source_tool: bool = False,
) -> dict:
    """Return a single visual dict with a unique id (structured + UUID)."""
    vis_title = vis.get("title") or vis.get("name") or vis.get("visual_type") or ""
    new_vis = {"id": id_gen.visual(page_name, vis_title)}
    # Preserve the ORIGINAL source visual id (the .pbix visualContainer `name`,
    # e.g. "528867b2d90c42924107"). Bookmarks key their explorationState
    # `visualContainers` by exactly this id, so the forward-engineer needs it to
    # remap a captured bookmark onto the regenerated visuals. Harmless for other
    # flows (only the bookmark emitter consumes it).
    _src_vid = vis.get("visual_id") or vis.get("id")
    if _src_vid:
        new_vis["source_visual_id"] = _src_vid
    for k, v in vis.items():
        if k not in ("id", "visual_id"):
            new_vis[k] = v
    if force_source_tool:
        new_vis["source_tool"] = toolname
    else:
        new_vis.setdefault("source_tool", toolname)
    for extra in _VISUAL_EXTRA_KEYS:
        if extra not in new_vis:
            new_vis[extra] = None
    return new_vis


def _transform_pages(
    pages: list,
    id_gen: "UniqueIDGenerator",
    toolname: str,
    force_source_tool: bool = False,
) -> list:
    """Return pages list with visuals transformed and default page keys set."""
    new_pages = []
    for page in pages:
        page_name = page.get("display_name", "")
        page["visuals"] = [
            _transform_visual(vis, id_gen, toolname, page_name, force_source_tool)
            for vis in page.get("visuals", [])
        ]
        page.setdefault("styles", None)
        page.setdefault("color_palettes", None)
        new_pages.append(page)
    return new_pages
 
 
def _has_legacy_ids(result: dict) -> bool:
    """Return True when the result was generated before UUID-based IDs were introduced.

    Any artifact whose ``id`` field lacks the ``(uuid)`` suffix is considered
    legacy.  We sample data_sources and tables; if both are absent (very small
    models) we fall back to checking calculation ids.
    """
    for ds in (result.get("data_sources") or []):
        _id = ds.get("id") or ""
        if _id:
            return "(uuid)" not in _id
    for tbl in (result.get("tables") or []):
        _id = tbl.get("id") or ""
        if _id:
            return "(uuid)" not in _id
    for calc in (result.get("calculations") or []):
        _id = calc.get("id") or ""
        if _id:
            return "(uuid)" not in _id
    return False


def apply_readable_ids(result: dict, upload_filename: str) -> dict:
    import copy
    result = copy.deepcopy(result)

    name_field = result.get("name", upload_filename)
    toolname   = "tableau" if (".twb" in name_field.lower() or ".twb" in upload_filename.lower()) else "powerbi"
    model_name = name_field

    # One generator per call — guarantees every id is unique across this batch
    id_gen = UniqueIDGenerator(toolname, model_name)

    data_sources = result.get("data_sources", []) or []

    # 1. Datasource ids — deduplicate names with an index when needed.
    ds_name_to_new_id: Dict[str, str] = {}
    used_ds_names: Dict[str, int] = {}
    for ds in data_sources:
        raw_name = ds.get("name") or "datasource"
        count = used_ds_names.get(raw_name, 0) + 1
        used_ds_names[raw_name] = count
        ds_name = raw_name if count == 1 else f"{raw_name} #{count}"
        new_id = id_gen.datasource(ds_name)
        ds["id"]   = new_id
        ds["name"] = ds_name
        ds_name_to_new_id[ds_name] = new_id

    # 2. Tables + columns + source_data_source_id rewrite.
    name_to_table_id = _apply_table_ids(
        result, id_gen, data_sources, ds_name_to_new_id
    )

    # 3. Relationships: rewrite endpoint table references to canonical ids.
    _rewrite_relationship_endpoints(result, name_to_table_id)

    # 4. Calculations: unique id per calc name.
    for calc in result.get("calculations", []):
        calc.pop("calc_id", None)
        calc_name = calc.get("name") or "calculation"
        calc["id"] = id_gen.calculation(calc_name)

    # 5. Visualizations / pages.
    if "report_pages" in result:
        raw_pages = result.pop("report_pages")
        result["visualizations"] = {
            "pages": _transform_pages(raw_pages, id_gen, toolname, force_source_tool=True)
        }
    elif "visualizations" in result:
        pages = result["visualizations"].get("pages", [])
        result["visualizations"]["pages"] = _transform_pages(pages, id_gen, toolname)

    if "technical_summary" in result:
        result["technical_summary"] = result.pop("technical_summary")

    return result
 
 
def build_kpi_lineage(data: dict) -> list:
    """Build KPI lineage from the final result JSON (after apply_readable_ids)."""
    model_name   = data.get("name", "")
    model_id     = data.get("model_id", "")
    extracted_at = data.get("extracted_at", "")
 
    _sample_id = (data.get("calculations") or [{}])[0].get("id", "")
    if "powerbi" in _sample_id.lower():
        bi_tool = "Power BI"
    elif "tableau" in _sample_id.lower():
        bi_tool = "Tableau"
    else:
        bi_tool = "Unknown"
 
    ds_lookup = {ds["name"]: ds for ds in data.get("data_sources", [])}
    table_lookup = {}
    for tbl in data.get("tables", []):
        tbl_id = tbl["id"]
        parts  = tbl_id.split("$")
        # New table-id layout: ...$<ds_name>(datasource)$<tbl_name>(table)
        # Scan for the (datasource)-suffixed segment instead of relying on
        # position, so the lookup keeps working if more segments are added.
        ds_name = None
        for seg in parts:
            if seg.endswith("(datasource)"):
                ds_name = seg[: -len("(datasource)")]
                break
        table_lookup[tbl["name"]] = {
            "table_id":   tbl_id,
            "table_type": tbl.get("table_type", ""),
            "ds_name":    ds_name,
        }
 
    kpi_index = {c["name"]: i for i, c in enumerate(data.get("calculations", []))}
 
    def resolve_column(col_ref: str) -> dict:
        try:
            dot = col_ref.index(".")
        except ValueError:
            return {"column_name": col_ref, "table_name": "", "table_id": "", "table_type": "", "data_source": {}, "report": {}}
        tbl_name = col_ref[:dot]
        col_name = col_ref[dot + 1:]
        tbl_info = table_lookup.get(tbl_name, {})
        ds_name  = tbl_info.get("ds_name")
        ds_info  = ds_lookup.get(ds_name, {}) if ds_name else {}
        src_id   = ds_info.get("id", _sample_id)
        if "powerbi" in src_id.lower():
            src_tool = "Power BI"
        elif "tableau" in src_id.lower():
            src_tool = "Tableau"
        else:
            src_tool = bi_tool
        return {
            "column_name": col_name,
            "table_name":  tbl_name,
            "table_id":    tbl_info.get("table_id", ""),
            "table_type":  tbl_info.get("table_type", ""),
            "data_source": {
                "name":            ds_info.get("name", ds_name or ""),
                "source_type":     ds_info.get("source_type", ""),
                "connection_mode": ds_info.get("connection_mode", ""),
                "path":            ds_info.get("path", ""),
            },
            "report": {
                "tool":        src_tool,
                "report_name": model_name,
                "model_id":    model_id,
            },
        }
 
    def resolve_measure(measure_name: str) -> dict:
        idx = kpi_index.get(measure_name)
        if idx is None:
            return {"kpi_name": measure_name, "found": False}
        ref = data["calculations"][idx]
        return {
            "kpi_name":             ref["name"],
            "found":                True,
            "semantic_type":        ref.get("semantic_type", ""),
            "aggregation_behavior": ref.get("aggregation_behavior", ""),
            "data_type":            ref.get("data_type", ""),
        }
 
    kpi_lineage = []
    for calc in data.get("calculations", []):
        kpi_lineage.append({
            "kpi_name":             calc["name"],
            "kpi_id":               calc["id"],
            "description":          calc.get("description", ""),
            "formula":              calc.get("expressions", {}).get("dax", ""),
            "semantic_type":        calc.get("semantic_type", ""),
            "aggregation_behavior": calc.get("aggregation_behavior", ""),
            "data_type":            calc.get("data_type", ""),
            "format_string":        calc.get("format_string", ""),
            "is_base_measure":      calc.get("is_base_measure", False),
            "reusable":             calc.get("reusable", False),
            "display":              calc.get("display", {}),
            "depends_on_columns":   [resolve_column(c) for c in calc.get("depends_on_columns", [])],
            "depends_on_measures":  [resolve_measure(m) for m in calc.get("depends_on_measures", [])],
        })
    return kpi_lineage
 
 
app = FastAPI(
    title="BI Metadata Extraction Service",
    openapi_tags=[
        {
            "name": "Health",
            "description": "Service liveness check.",
        },
        {
            "name": "Extraction",
            "description": "Upload and process BI report files (Tableau, QlikView, PowerBI).",
        },
        {
            "name": "Jobs",
            "description": "Poll batch job progress.",
        },
        {
            "name": "Reports",
            "description": "List and fetch previously extracted reports from Postgres.",
        },
        {
            "name": "Search",
            "description": "Keyword search across report metadata stored in Postgres.",
        },
        {
            "name": "Utilities",
            "description": "Helper endpoints (checksum calculation, etc.).",
        },
        {
            "name": "Validation",
            "description": (
                "Tier 1 validation — compare a homogeneous JSON extraction "
                "against its source PBIX and produce a scored Excel report."
            ),
        },
        {
            "name": "KPI Rationalization",
            "description": "AI-powered KPI rationalization across one or more BI report JSON files.",
        },
    ],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)
 
@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy"}
 
 
@app.post("/checksum/", tags=["Utilities"])
async def compute_file_checksum(file: UploadFile = File(...)):
    """
    Compute the SHA-256 checksum of an uploaded file without processing it.
    Use this to check whether a file already exists in Postgres before uploading.
    """
    data = await file.read()
    checksum = _compute_checksum(data)
    return {"file_name": file.filename, "checksum": checksum, "algorithm": "sha256"}


@app.get("/list-reports/", tags=["Reports"])
async def list_reports(tool_name: str = None):
    """
    List all successfully processed reports stored in the database.
    Optionally filter by tool_name: 'tableau-workbook', 'qlikview', or 'powerbi'.
    Use the exact file_name from this list in the /fetch-report/ endpoint.
    """
    from postgres_writer import get_db_session
    from postgres_models import ExtractionLog
 
    try:
        with get_db_session() as session:
            query = (
                session.query(
                    ExtractionLog.report_id,
                    ExtractionLog.file_name,
                    ExtractionLog.tool_type,
                    ExtractionLog.status,
                    ExtractionLog.completed_at,
                    ExtractionLog.runtime_seconds,
                    ExtractionLog.file_checksum,
                )
                .filter(ExtractionLog.status == "SUCCESS")
                .order_by(ExtractionLog.completed_at.desc())
            )
            if tool_name:
                query = query.filter(ExtractionLog.tool_type == tool_name)
 
            rows = query.all()
            return jsonable_encoder([
                {
                    "report_id": r.report_id,
                    "file_name": r.file_name,
                    "tool_type": r.tool_type,
                    "status": r.status,
                    "completed_at": r.completed_at,
                    "runtime_seconds": r.runtime_seconds,
                    "file_checksum": r.file_checksum,
                }
                for r in rows
            ])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list reports: {str(e)}")
 
 
@app.post("/fetch-report/", tags=["Reports"])
async def fetch_report(
    file_name: str = Form(..., description="Original uploaded filename e.g. 'Sample Sales Dashboard 1.twb'"),
    tool_name: str = Form(..., description="Tool type: 'tableau-workbook', 'qlikview', or 'powerbi'"),
):
    """
    Fetch the stored RE response for a previously processed file directly from
    the extraction_log table in Postgres. No re-processing — instant response.
 
    Use GET /list-reports/ first to see the exact file names available.
    """
    from postgres_writer import get_db_session
    from postgres_models import ExtractionLog
 
    # Exact match — use the filename exactly as stored (including extension)
    search_name = file_name.strip()
 
    not_found_detail = None
    response_data = None
 
    try:
        with get_db_session() as session:
            log_entry = (
                session.query(ExtractionLog)
                .filter(
                    ExtractionLog.tool_type == tool_name,
                    ExtractionLog.status == "SUCCESS",
                    ExtractionLog.file_name == search_name,
                )
                .order_by(ExtractionLog.completed_at.desc())
                .execution_options(stream_results=True)
                .first()
            )
 
            if log_entry is None:
                # Collect available files while session is still open
                available = (
                    session.query(
                        ExtractionLog.file_name,
                        ExtractionLog.status,
                        ExtractionLog.completed_at,
                    )
                    .filter(ExtractionLog.tool_type == tool_name)
                    .order_by(ExtractionLog.completed_at.desc())
                    .limit(10)
                    .all()
                )
                not_found_detail = {
                    "message": f"No successful extraction found for '{file_name}' "
                               f"with tool '{tool_name}'. File name must match exactly.",
                    "hint": "Use GET /list-reports/ to see all available file names.",
                    "available_files": [
                        {
                            "file_name": r.file_name,
                            "status": r.status,
                            "completed_at": str(r.completed_at),
                        }
                        for r in available
                    ],
                }
            elif log_entry.result is None:
                not_found_detail = {
                    "message": f"Extraction log found for '{file_name}' but the result JSON was not stored.",
                    "hint": "Re-upload the file to regenerate and store the full result.",
                    "report_id": log_entry.report_id,
                    "completed_at": str(log_entry.completed_at),
                }
            else:
                # Copy all data out while session is open
                response_data = {
                    "report_id": log_entry.report_id,
                    "file_name": log_entry.file_name,
                    "tool_type": log_entry.tool_type,
                    "status": log_entry.status,
                    "completed_at": log_entry.completed_at,
                    "runtime_seconds": log_entry.runtime_seconds,
                    "result": log_entry.result,
                }
 
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch report: {str(e)}")
 
    # Raise outside the session so get_db_session doesn't catch it
    if not_found_detail is not None:
        raise HTTPException(status_code=404, detail=not_found_detail)
 
    return jsonable_encoder(response_data)


# ---------------------------------------------------------------------------
# Search helpers
# ---------------------------------------------------------------------------

def _kw_match(value: Any, keyword: str) -> bool:
    """Return True if *keyword* appears (case-insensitive) in the string form of *value*."""
    return keyword in str(value).lower()


def _matching_fields(obj: dict, fields: List[str], keyword: str) -> List[str]:
    """Return the subset of *fields* whose value in *obj* contains *keyword*."""
    return [f for f in fields if _kw_match(obj.get(f, ""), keyword)]


def _search_result_json(result: dict, keyword: str) -> dict:
    """
    Search the stored extraction result JSON for *keyword* (case-insensitive).

    Scans five logical sections:
      data_sources   – name, source_type, server, database, schema, path, connection_mode
      tables         – table name/description/type and each column name/description/data_type
      ingestion_steps – step_type, description, native expression text per table
      kpi_lineage    – kpi_name, description, formula, semantic_type, depends_on_columns
      relationships  – left_table, left_column, right_table, right_column, note
      visualizations – page display_name and each visual's type/title

    Returns a dict with per-section hit lists and a grand total.
    """
    kw = keyword.lower().strip()

    sections: Dict[str, list] = {
        "data_sources": [],
        "tables": [],
        "ingestion_steps": [],
        "kpi_lineage": [],
        "relationships": [],
        "visualizations": [],
    }

    # ── data_sources ─────────────────────────────────────────────────────────
    ds_fields = ["name", "source_type", "server", "database", "schema", "path", "connection_mode"]
    for ds in result.get("data_sources", []):
        matched = _matching_fields(ds, ds_fields, kw)
        if matched:
            sections["data_sources"].append({
                "id": ds.get("id"),
                "name": ds.get("name"),
                "source_type": ds.get("source_type"),
                "path": ds.get("path"),
                "matched_fields": matched,
            })

    # ── tables & ingestion_steps ──────────────────────────────────────────────
    tbl_fields = ["name", "description", "table_type"]
    col_fields = ["name", "description", "data_type", "semantic_role"]
    step_text_fields = ["step_type", "description"]

    for tbl in result.get("tables", []):
        tbl_name = tbl.get("name", "")
        tbl_matched: List[str] = _matching_fields(tbl, tbl_fields, kw)

        col_hits = []
        for col in tbl.get("columns", []):
            col_matched = _matching_fields(col, col_fields, kw)
            if col_matched:
                col_hits.append({
                    "column_name": col.get("name"),
                    "data_type": col.get("data_type"),
                    "semantic_role": col.get("semantic_role"),
                    "matched_fields": col_matched,
                })

        if tbl_matched or col_hits:
            sections["tables"].append({
                "table_id": tbl.get("id"),
                "table_name": tbl_name,
                "table_type": tbl.get("table_type"),
                "description": tbl.get("description"),
                "matched_fields": tbl_matched,
                "column_hits": col_hits,
            })

        # ingestion steps for this table
        step_hits = []
        for step in tbl.get("ingestion", {}).get("steps", []):
            step_matched: List[str] = _matching_fields(step, step_text_fields, kw)
            # also scan every native expression value
            for expr_val in step.get("native_expressions", {}).values():
                if _kw_match(expr_val, kw) and "native_expression" not in step_matched:
                    step_matched.append("native_expression")
            if step_matched:
                step_hits.append({
                    "step_type": step.get("step_type"),
                    "description": step.get("description"),
                    "matched_fields": step_matched,
                })
        if step_hits:
            sections["ingestion_steps"].append({
                "table_name": tbl_name,
                "table_id": tbl.get("id"),
                "step_hits": step_hits,
            })

    # ── kpi_lineage ───────────────────────────────────────────────────────────
    kpi_fields = ["kpi_name", "name", "description", "formula", "semantic_type", "aggregation_behavior"]
    for kpi in result.get("kpi_lineage", result.get("calculations", [])):
        kpi_matched = _matching_fields(kpi, kpi_fields, kw)
        # also scan depends_on_columns (list of strings or dicts)
        for col_ref in kpi.get("depends_on_columns", []):
            ref_str = col_ref if isinstance(col_ref, str) else str(col_ref.get("column_name", ""))
            if _kw_match(ref_str, kw) and "depends_on_columns" not in kpi_matched:
                kpi_matched.append("depends_on_columns")
        if kpi_matched:
            sections["kpi_lineage"].append({
                "kpi_name": kpi.get("kpi_name") or kpi.get("name"),
                "description": kpi.get("description"),
                "formula": kpi.get("formula") or kpi.get("expressions", {}).get("dax"),
                "semantic_type": kpi.get("semantic_type"),
                "matched_fields": kpi_matched,
            })

    # ── relationships ─────────────────────────────────────────────────────────
    rel_fields = ["left_table_id", "left_column", "right_table_id", "right_column", "note"]
    for rel in result.get("relationships", []):
        rel_matched = _matching_fields(rel, rel_fields, kw)
        if rel_matched:
            sections["relationships"].append({
                "relationship_id": rel.get("id"),
                "left_table": rel.get("left_table_id"),
                "left_column": rel.get("left_column"),
                "right_table": rel.get("right_table_id"),
                "right_column": rel.get("right_column"),
                "cardinality": rel.get("cardinality"),
                "matched_fields": rel_matched,
            })

    # ── visualizations ────────────────────────────────────────────────────────
    vis_fields = ["visual_type", "title", "subtitle", "visual_sub_type"]
    for page in result.get("visualizations", {}).get("pages", []):
        page_name = page.get("display_name", "")
        page_name_hit = _kw_match(page_name, kw)
        vis_hits = []
        for vis in page.get("visuals", []):
            vis_matched = _matching_fields(vis, vis_fields, kw)
            if vis_matched:
                vis_hits.append({
                    "visual_id": vis.get("id"),
                    "visual_type": vis.get("visual_type"),
                    "title": vis.get("title"),
                    "matched_fields": vis_matched,
                })
        if page_name_hit or vis_hits:
            sections["visualizations"].append({
                "page_id": page.get("page_id"),
                "page_name": page_name,
                "page_name_matched": page_name_hit,
                "visual_hits": vis_hits,
            })

    total = sum(len(v) for v in sections.values())
    return {"total_matches": total, "results": sections}


@app.get("/search/", tags=["Search"])
async def search_report(
    file_name: List[str] = Query(
        ...,
        description="One or more exact file names as stored in Postgres, e.g. 'Sales.pbix'. "
                    "Repeat the parameter for multiple reports: ?file_name=A.pbix&file_name=B.twb",
    ),
    keyword: str = Query(..., description="Case-insensitive keyword to search across the report metadata"),
    tool_name: Optional[str] = Query(
        None,
        description="Optional tool filter: 'tableau-workbook', 'qlikview', or 'powerbi'. "
                    "When omitted, all tool types are searched.",
    ),
):
    """
    Search previously extracted report metadata by keyword across one or more reports.

    Each `file_name` is looked up in Postgres (most-recent SUCCESS record).
    Results are returned per-report and also include a grand total match count.

    Scans: **data_sources**, **tables** (columns), **ingestion_steps**,
    **kpi_lineage**, **relationships**, **visualizations**.

    Use `GET /list-reports/` to discover valid file names.
    """
    if not keyword.strip():
        raise HTTPException(status_code=400, detail="keyword must not be empty.")

    from postgres_writer import get_db_session
    from postgres_models import ExtractionLog

    file_names = [fn.strip() for fn in file_name if fn.strip()]
    if not file_names:
        raise HTTPException(status_code=400, detail="At least one non-empty file_name is required.")

    per_report: list = []
    grand_total = 0

    try:
        with get_db_session() as session:
            for fn in file_names:
                q = (
                    session.query(ExtractionLog)
                    .filter(
                        ExtractionLog.file_name == fn,
                        ExtractionLog.status == "SUCCESS",
                        ExtractionLog.result.isnot(None),
                    )
                )
                if tool_name:
                    q = q.filter(ExtractionLog.tool_type == tool_name)

                log_entry = q.order_by(ExtractionLog.completed_at.desc()).first()

                if log_entry is None:
                    per_report.append({
                        "file_name": fn,
                        "status": "not_found",
                        "message": f"No successful extraction found for '{fn}'"
                                   + (f" with tool '{tool_name}'" if tool_name else "") + ".",
                    })
                    continue

                result_json = (
                    log_entry.result
                    if isinstance(log_entry.result, dict)
                    else json.loads(log_entry.result)
                )
                search_output = _search_result_json(result_json, keyword)
                grand_total += search_output["total_matches"]
                per_report.append({
                    "file_name": fn,
                    "tool_name": log_entry.tool_type,
                    "report_id": log_entry.report_id,
                    "extracted_at": str(log_entry.completed_at),
                    **search_output,
                })

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query database: {str(e)}")

    return jsonable_encoder({
        "keyword": keyword,
        "reports_searched": len(file_names),
        "grand_total_matches": grand_total,
        "reports": per_report,
    })


@app.get("/jobs/{job_id}/progress", tags=["Jobs"])
async def get_job_progress(job_id: str):
    """
    Return the current processing progress for every file in a batch job.
    On each call the latest in-memory state is flushed to Postgres first,
    so the DB always reflects what you see here.
    """
    if job_id not in _job_store:
        raise HTTPException(404, f"Job '{job_id}' not found.")
 
    file_records = list(_job_store[job_id].values())
 
    # Flush current state to Postgres before returning
    await asyncio.to_thread(upsert_job_progress, file_records)
 
    total = len(file_records)
    completed = sum(1 for r in file_records if r["status"] == "completed")
    failed = sum(1 for r in file_records if r["status"] == "failed")
    in_progress = total - completed - failed
 
    return {
        "job_id": job_id,
        "total": total,
        "completed": completed,
        "failed": failed,
        "in_progress": in_progress,
        "overall_status": (
            "completed" if (completed + failed) == total
            else "processing"
        ),
        "files": [
            {
                "file_name": r["file_name"],
                "status": r["status"],
                "step": r["step"],
                "started_at": r["started_at"],
                "updated_at": r["updated_at"],
                "completed_at": r["completed_at"],
                "runtime_seconds": r["runtime_seconds"],
                "error": r["error"],
                "postgres_stored": r["postgres_stored"],
            }
            for r in file_records
        ],
    }
 
 
_VALID_TOOLS = {"tableau-workbook", "qlikview", "powerbi"}


@app.post(
    "/upload/batch/",
    tags=["Extraction"],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["files", "etltools"],
                        "properties": {
                            "files": {
                                "type": "array",
                                "items": {"type": "string", "format": "binary"},
                                "description": (
                                    "One or more files (.twb/.twbx, .zip, .pbix). "
                                    "Repeat this field for each file."
                                ),
                            },
                            "etltools": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": (
                                    "Tool name for each file, in the same order as 'files'. "
                                    "Click 'Add string item' once per file and type the tool name. "
                                    "If a single value is supplied it applies to all files. "
                                    "Allowed values: 'tableau-workbook' | 'qlikview' | 'powerbi'."
                                ),
                            },
                            "model": {
                                "type": "string",
                                "description": "Optional model override (Tableau only)",
                            },
                        },
                    },
                    "encoding": {
                        "files": {
                            "contentType": "application/octet-stream",
                            "style": "form",
                            "explode": True,
                        },
                        "etltools": {
                            "style": "form",
                            "explode": True,
                        },
                    },
                }
            },
        }
    },
)
async def upload_files_batch(
    files: List[UploadFile] = File(...),
    etltools: List[str] = Form(...),
    model: str = Form(None),
):
    """
    Accept multiple files of **mixed tool types** (Tableau + PowerBI, etc.) in one
    request, process them in parallel, and write each result to Postgres.

    Returns immediately with a job_id. Poll GET /jobs/{job_id}/progress to track
    per-file status — each poll also flushes the latest state to Postgres.

    Form fields
    -----------
    files     — one or more uploaded files (repeat the field for each file)
    etltools  — tool name for each file **in the same order as files** (repeat the
                field once per file).  If only one value is given it is applied to
                every file.  Allowed values: 'tableau-workbook' | 'qlikview' | 'powerbi'
    model     — optional model override (Tableau only)

    Examples
    --------
    Single tool for all files (backward-compatible):
        files=a.twb, files=b.twb, etltools=tableau-workbook

    Mixed tools:
        files=a.twb, files=report.pbix, etltools=tableau-workbook, etltools=powerbi
    """
    if not files:
        raise HTTPException(400, "No files provided.")

    # Validate and expand etltools to match files length
    if len(etltools) == 1:
        etltools = etltools * len(files)
    elif len(etltools) != len(files):
        raise HTTPException(
            400,
            f"'etltools' must have exactly 1 value (applied to all files) or one value per file "
            f"({len(files)} files supplied, {len(etltools)} etltools supplied).",
        )

    invalid = [t for t in etltools if t not in _VALID_TOOLS]
    if invalid:
        raise HTTPException(
            400,
            f"Invalid tool name(s): {invalid}. Allowed values: {sorted(_VALID_TOOLS)}.",
        )

    job_id = str(uuid.uuid4())

    # Snapshot file bytes NOW (before background task) because UploadFile
    # is request-scoped and will be closed once the response is sent.
    file_snapshots: list[dict] = []
    for f, tool in zip(files, etltools):
        content = await f.read()
        file_snapshots.append({"filename": f.filename, "content": content, "tool": tool})
        _job_store.setdefault(job_id, {})[f.filename] = _init_file_progress(
            job_id, f.filename, tool
        )

    async def _run_batch() -> None:
        async def _process_one(filename: str, content: bytes, tool: str) -> None:
            _update_progress(job_id, filename, status="extracting", step="LLM extraction")
            try:
                from fastapi import UploadFile as _UF
                import io as _io
                mock_file = _UF(filename=filename, file=_io.BytesIO(content))

                if tool == "tableau-workbook":
                    _update_progress(job_id, filename, step="Extracting Tableau model")
                    result = await _handle_tableau(mock_file, model, skip_cache=True)
                elif tool == "qlikview":
                    _update_progress(job_id, filename, step="Extracting QlikView model")
                    result = await _handle_qlikview(mock_file, skip_cache=True)
                elif tool == "powerbi":
                    _update_progress(job_id, filename, step="Extracting PowerBI model")
                    result = await _handle_powerbi(mock_file, skip_cache=True)
                else:
                    # Guarded above, but kept for safety
                    raise ValueError(f"Unsupported tool: {tool!r}")

                completed_at = datetime.now(timezone.utc)
                started_at = _job_store[job_id][filename]["started_at"]
                runtime = str(round((completed_at - started_at).total_seconds(), 2))
                _update_progress(
                    job_id, filename,
                    status="completed",
                    step="Done — results written to Postgres",
                    completed_at=completed_at,
                    runtime_seconds=runtime,
                    postgres_stored=True,
                )

            except (HTTPException, Exception) as exc:  # noqa: BLE001
                err = exc.detail if isinstance(exc, HTTPException) else str(exc)
                completed_at = datetime.now(timezone.utc)
                started_at = _job_store[job_id][filename]["started_at"]
                runtime = str(round((completed_at - started_at).total_seconds(), 2))
                _update_progress(
                    job_id, filename,
                    status="failed",
                    step=f"Failed: {err}",
                    completed_at=completed_at,
                    runtime_seconds=runtime,
                    error=err,
                )

        await asyncio.gather(
            *[_process_one(s["filename"], s["content"], s["tool"]) for s in file_snapshots]
        )

    asyncio.create_task(_run_batch())

    return {
        "job_id": job_id,
        "total_files": len(file_snapshots),
        "files": [
            {"file_name": s["filename"], "tool": s["tool"]}
            for s in file_snapshots
        ],
        "status": "processing",
        "progress_url": f"/jobs/{job_id}/progress",
    }
 
 
async def _handle_tableau(file: UploadFile, model: str, skip_cache: bool = False):
    content = await file.read()
    started_at = datetime.now(timezone.utc)
    report_id = str(uuid.uuid4())
    error_msg = None
    tb_str = None

    # ── Checksum dedup ────────────────────────────────────────────────────────
    checksum = _compute_checksum(content)
    if not skip_cache:
        cached = await asyncio.to_thread(lookup_by_checksum, checksum)
        if cached:
            if _has_legacy_ids(cached["result"]):
                print(f"[Tableau] Cache entry has legacy IDs — re-extracting with UUID-based IDs for {file.filename!r}")
                cached = None
            else:
                print(f"[Tableau] Checksum hit — returning cached result for {file.filename!r} (checksum={checksum[:12]}…)")
                return jsonable_encoder({
                    **cached["result"],
                    "_cache": {"hit": True, "checksum": checksum,
                               "cached_file": cached["file_name"],
                               "cached_at": str(cached["completed_at"])},
                })
    # ─────────────────────────────────────────────────────────────────────────
    _fmt = "twbx (packaged)" if file.filename and file.filename.lower().endswith(".twbx") else "twb (XML)"
    print(f"[Tableau] Received file: {file.filename!r} — format detected: {_fmt}")
 
    try:
        # LLM extraction
        final_json = await run_tableau_flow(content, model, file.filename)
        print("LLM processing time:", datetime.now(timezone.utc) - started_at)

        # Colors / theme / styles — deterministic parse of the .twb XML, merged
        # by page display_name + visual_id/title BEFORE apply_readable_ids drops
        # those ids. No LLM: values are copied verbatim from the workbook.
        try:
            from style_extractor import apply_tableau_styling
            apply_tableau_styling(final_json, content)
        except Exception as e:
            print(f"[Tableau] Warning: Styling extraction failed: {e}")

        completed_at = datetime.now(timezone.utc)
        runtime = str(round((completed_at - started_at).total_seconds(), 2))
        final_json = apply_readable_ids(final_json, file.filename)
        final_json["ai_summary"] = await _make_ai_summary(final_json.get("technical_summary", ""))

        # Inject image data directly on image visuals (after summary, no LLM)
        try:
            inject_inline_image_data_tableau(final_json, content, report_id or "")
        except Exception as e:
            print(f"[Tableau] Warning: Image data injection failed: {e}")

        try:
            result_to_store = json.loads(json.dumps(final_json, default=str))
        except Exception:
            result_to_store = None
        await asyncio.to_thread(
            save_extraction_log,
            report_id, "tableau-workbook", file.filename,
            "SUCCESS", started_at, completed_at, runtime,
            None, None, False, result_to_store, checksum
        )
        return jsonable_encoder(final_json)

    except Exception as e:
        error_msg = str(e)
        tb_str = traceback.format_exc()
        print(f"[Tableau] ERROR: {error_msg}")
        print(f"[Tableau] TRACEBACK:\n{tb_str}")
        completed_at = datetime.now(timezone.utc)
        runtime = str(round((completed_at - started_at).total_seconds(), 2))
        await asyncio.to_thread(
            save_extraction_log,
            report_id, "tableau-workbook", file.filename,
            "FAILED", started_at, completed_at, runtime,
            error_msg, tb_str, False, None, checksum
        )
        raise HTTPException(400, f"Error processing Tableau file: {e}")


async def _handle_qlikview(file: UploadFile, skip_cache: bool = False):
    out_dir = None
    started_at = datetime.now(timezone.utc)
    report_id = str(uuid.uuid4())
    try:
        # ── Checksum dedup ────────────────────────────────────────────────────
        zip_bytes = await file.read()
        checksum = _compute_checksum(zip_bytes)
        if not skip_cache:
            cached = await asyncio.to_thread(lookup_by_checksum, checksum)
            if cached:
                if _has_legacy_ids(cached["result"]):
                    print(f"[QlikView] Cache entry has legacy IDs — re-extracting with UUID-based IDs for {file.filename!r}")
                    cached = None
                else:
                    print(f"[QlikView] Checksum hit — returning cached result for {file.filename!r} (checksum={checksum[:12]}…)")
                    return jsonable_encoder({
                        **cached["result"],
                        "_cache": {"hit": True, "checksum": checksum,
                                   "cached_file": cached["file_name"],
                                   "cached_at": str(cached["completed_at"])},
                    })
        # ─────────────────────────────────────────────────────────────────────
        session_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        out_dir = Path("extracted_files") / f"session_{session_id}"
        out_dir.mkdir(parents=True, exist_ok=True)

        file_paths = []
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            zf.extractall(out_dir)
            for name in zf.namelist():
                p = out_dir / name
                if p.is_file():
                    file_paths.append(str(p))
 
        start = datetime.now(timezone.utc)
        result = await run_qlik_flow(file_paths)
        end = datetime.now(timezone.utc)
        print(f"QlikView processing time: {end - start}")

        completed_at = datetime.now(timezone.utc)
        runtime = str(round((completed_at - started_at).total_seconds(), 2))
        result = apply_readable_ids(result, file.filename)
        result["ai_summary"] = await _make_ai_summary(result.get("technical_summary", ""))
        try:
            result_to_store = json.loads(json.dumps(result, default=str))
        except Exception:
            result_to_store = None
        await asyncio.to_thread(
            save_extraction_log,
            report_id, "qlikview", file.filename,
            "SUCCESS", started_at, completed_at, runtime,
            None, None, False, result_to_store, checksum
        )

        return jsonable_encoder(result)

    except zipfile.BadZipFile:
        raise HTTPException(400, "Uploaded file is not a valid ZIP.")
    except Exception as e:
        print(f"[QlikView] ERROR: {e}")
        print(f"[QlikView] TRACEBACK:\n{traceback.format_exc()}")
        completed_at = datetime.now(timezone.utc)
        runtime = str(round((completed_at - started_at).total_seconds(), 2))
        await asyncio.to_thread(
            save_extraction_log,
            report_id, "qlikview", file.filename,
            "FAILED", started_at, completed_at, runtime,
            str(e), traceback.format_exc(), False, None, checksum
        )
        raise HTTPException(400, f"Error processing QlikView files: {e}")
    finally:
        # if out_dir and out_dir.exists():
        #     shutil.rmtree(out_dir)
            print(f"not Cleaning  the temporary directory: {out_dir}")
 
 
def _collect_pbix_file_paths(pbix_bytes: bytes, temp_dir: Path) -> list:
    """Extract .pbix archive into temp_dir and return list of file paths."""
    file_paths = []
    with zipfile.ZipFile(io.BytesIO(pbix_bytes)) as zf:
        zf.extractall(temp_dir)
        for name in zf.namelist():
            p = temp_dir / name
            if p.is_file():
                file_paths.append(str(p))
    return file_paths
 
 
def _find_layout_file(file_paths: list) -> str | None:
    """Return the Report/Layout file path from the extracted file list, or None."""
    for fp in file_paths:
        if "Report/Layout" in fp.replace("\\", "/"):
            return fp
    return None
 
 
async def _handle_powerbi(file: UploadFile, skip_cache: bool = False):
    temp_dir = None
    pbix_file_path = None
    started_at = datetime.now(timezone.utc)
    report_id = str(uuid.uuid4())
    try:
        # ── Checksum dedup ────────────────────────────────────────────────────
        pbix_bytes = await file.read()
        checksum = _compute_checksum(pbix_bytes)
        if not skip_cache:
            cached = await asyncio.to_thread(lookup_by_checksum, checksum)
            if cached:
                if _has_legacy_ids(cached["result"]):
                    print(f"[PowerBI] Cache entry has legacy IDs — re-extracting with UUID-based IDs for {file.filename!r}")
                    cached = None
                else:
                    print(f"[PowerBI] Checksum hit — returning cached result for {file.filename!r} (checksum={checksum[:12]}…)")
                    return jsonable_encoder({
                        **cached["result"],
                        "_cache": {"hit": True, "checksum": checksum,
                                   "cached_file": cached["file_name"],
                                   "cached_at": str(cached["completed_at"])},
                    })
        # ─────────────────────────────────────────────────────────────────────
        session_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        temp_dir = Path("extracted_files") / f"powerbi_session_{session_id}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        pbix_file_path = temp_dir / file.filename
        async with aiofiles.open(pbix_file_path, "wb") as f:
            await f.write(pbix_bytes)

        print(f"Saved .pbix file to: {pbix_file_path}")
 
        file_paths = _collect_pbix_file_paths(pbix_bytes, temp_dir)
        print(f"Extracted {len(file_paths)} files from .pbix archive")
 
        start = datetime.now(timezone.utc)
        extraction_result = extract_powerbi_model(
            pbix_path=str(pbix_file_path),
            output_dir=str(temp_dir / "powerbi_metadata"),
        )
        end = datetime.now(timezone.utc)
        print(f"PowerBI extraction time: {end - start}")
 
        layout_file = _find_layout_file(file_paths)
        if layout_file:
            print(f"Found Layout file: {layout_file}")
            mapping_output_path = temp_dir / "powerbi_metadata" / "layout_datamodel_mapping.json"
            try:
                start_mapping = datetime.now(timezone.utc)
                map_layout_to_datamodel(
                    layout_path=layout_file,
                    datamodel_folder=str(temp_dir / "powerbi_metadata"),
                    output_path=str(mapping_output_path),
                )
                print(f"Layout mapping time: {datetime.now(timezone.utc) - start_mapping}")
                print(f"Mapping saved to: {mapping_output_path}")
            except Exception as e:
                print(f"Warning: Layout mapping failed: {e}")
        else:
            print("Warning: Layout file not found in extracted files")
 
        print("\nStarting PowerBI agent processing...")
        start_agent = datetime.now(timezone.utc)
        agent_result = await run_powerbi_flow(
            extracted_metadata_folder=str(temp_dir / "powerbi_metadata"),
            source_filename=file.filename,
        )
        print(f"PowerBI agent processing time: {datetime.now(timezone.utc) - start_agent}")
 
        db_summary = {"stored": False}

        # Inject image data on image visuals BEFORE apply_readable_ids — matching
        # is done by visual_id, which apply_readable_ids drops. No LLM involved.
        try:
            inject_inline_image_data_powerbi(
                agent_result, str(temp_dir), report_id or "", layout_path=layout_file or "",
            )
        except Exception as e:
            print(f"[PowerBI] Warning: Image data injection failed: {e}")

        # Colors / theme / styles — deterministic parse of the Layout + theme JSON,
        # merged by page_id/visual_id BEFORE apply_readable_ids drops those ids.
        # No LLM: values are copied verbatim from the source files.
        try:
            from style_extractor import apply_powerbi_styling
            if layout_file:
                apply_powerbi_styling(
                    agent_result, layout_path=layout_file, report_dir=str(temp_dir),
                )
        except Exception as e:
            print(f"[PowerBI] Warning: Styling extraction failed: {e}")

        # Row-Level Security: attach RLS roles to the common model verbatim from the
        # extracted rls.json. Security-critical filter DAX is copied exactly (never via
        # an LLM) and grouped per role so the FE re-emits them as semantic-model roles.
        try:
            rls_path = temp_dir / "powerbi_metadata" / "rls.json"
            if rls_path.exists():
                rls_rows = json.loads(rls_path.read_text(encoding="utf-8"))
                roles_by_name: dict = {}
                for row in (rls_rows or []):
                    role_name = (row.get("RoleName") or "").strip()
                    if not role_name:
                        continue
                    role = roles_by_name.setdefault(
                        role_name, {"name": role_name, "table_permissions": []}
                    )
                    table_name = (row.get("TableName") or "").strip()
                    filter_expr = (row.get("FilterExpression") or "").strip()
                    if table_name:
                        role["table_permissions"].append(
                            {"table": table_name, "filter_expression": filter_expr}
                        )
                if roles_by_name:
                    agent_result["roles"] = list(roles_by_name.values())
                    print(f"[PowerBI] Attached {len(roles_by_name)} RLS role(s)")
        except Exception as e:
            print(f"[PowerBI] Warning: RLS role attach failed: {e}")

        agent_result = apply_readable_ids(agent_result, file.filename)
        agent_result["kpi_lineage"] = build_kpi_lineage(agent_result)
        agent_result["ai_summary"] = await _make_ai_summary(agent_result.get("technical_summary", ""))

        try:
            result_to_store = json.loads(json.dumps(agent_result, default=str))
        except Exception:
            result_to_store = None
        completed_at = datetime.now(timezone.utc)
        runtime = str(round((completed_at - started_at).total_seconds(), 2))
        await asyncio.to_thread(
            save_extraction_log,
            report_id, "powerbi", file.filename,
            "SUCCESS", started_at, completed_at, runtime,
            None, None, False, result_to_store, checksum
        )

        return jsonable_encoder(agent_result)

    except zipfile.BadZipFile:
        raise HTTPException(400, "Uploaded file is not a valid .pbix file.")
    except ImportError as e:
        raise HTTPException(500, f"PowerBI extractor dependency missing: {e}")
    except Exception as e:
        print(f"[PowerBI] ERROR: {e}")
        print(f"[PowerBI] TRACEBACK:\n{traceback.format_exc()}")
        completed_at = datetime.now(timezone.utc)
        runtime = str(round((completed_at - started_at).total_seconds(), 2))
        await asyncio.to_thread(
            save_extraction_log,
            report_id, "powerbi", file.filename,
            "FAILED", started_at, completed_at, runtime,
            str(e), traceback.format_exc(), False, None, checksum
        )
        raise HTTPException(400, f"Error processing PowerBI file: {e}")
    finally:
        # if temp_dir and temp_dir.exists():
        #     shutil.rmtree(temp_dir)
            print(f"not cleaning up temporary directory: {temp_dir}")

async def _handle_gapanalysis(file: dict, target_model: UploadFile):
    """
    Hybrid embedding + LLM gap analysis between an extracted source BI model JSON
    and a target data model CSV.

    Steps:
      1. Extract source tables/columns from the provided JSON object.
      2. Read the target model from the uploaded CSV.
      3. Map source tables → target entities via embeddings (LLM fallback).
      4. Map source columns → target columns per table pair via embeddings (LLM fallback).
      5. Classify each mapped pair as Mapped / Data Type Mismatch /
         Gap (Missing in Target) / Definition Conflict using GPT structured output.
    """
    import io as _io
    import numpy as np
    import pandas as pd
    from concurrent.futures import ThreadPoolExecutor, as_completed as _as_completed
    from openai import AzureOpenAI
    from pydantic import BaseModel as _BaseModel, Field as _Field
    from typing import Literal

    # ── Read source JSON object and target CSV file ───────────────────────────
    data = file
    target_bytes = await target_model.read()

    try:
        target_df = pd.read_csv(_io.BytesIO(target_bytes))
    except Exception as exc:
        raise HTTPException(400, f"Invalid target CSV: {exc}")

    # ── Azure clients (credentials from .env) ────────────────────────────────
    _gpt_client = AzureOpenAI(
        azure_endpoint=os.getenv("AZURE_OPENAI_API_BASE"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version=os.getenv("AZURE_API_VERSION", "2024-08-01-preview"),
    )
    _deployment = os.getenv("AZURE_DEPLOYMENT", "gpt-5-mini")

    # ── LLM-based header normalization ────────────────────────────────────────
    # Ask the LLM to map the actual CSV headers to the four canonical column
    # names the code relies on, so the function is column-name agnostic.
    class _HeaderMapping(_BaseModel):
        Target_Table_Name: str = _Field(
            description="Exact header from the CSV that represents the target table/entity name, or '' if absent."
        )
        Target_Column_Name: str = _Field(
            description="Exact header from the CSV that represents the target column/field name, or '' if absent."
        )
        Target_Data_Type: str = _Field(
            description="Exact header from the CSV that represents the data type of the target column, or '' if absent."
        )
        Target_Description: str = _Field(
            description="Exact header from the CSV that represents a description/definition of the target column, or '' if absent."
        )

    _actual_headers = list(target_df.columns)
    _sample_rows = target_df.head(3).to_dict(orient="records")
    _header_prompt = (
        "You are a data schema expert.\n\n"
        "Below are the column headers of a target data model CSV, along with up to 3 sample rows.\n\n"
        f"Headers: {_actual_headers}\n\n"
        f"Sample rows:\n{_sample_rows}\n\n"
        "Map each of the four canonical column roles to the single best-matching header from the list above:\n"
        "  1. Target_Table_Name  - the column holding the target table or entity name\n"
        "  2. Target_Column_Name - the column holding the target column or field name\n"
        "  3. Target_Data_Type   - the column holding the data type (optional; use '' if absent)\n"
        "  4. Target_Description - the column holding a description/definition (optional; use '' if absent)\n\n"
        "Return ONLY exact header strings from the provided list, or '' when no good match exists."
    )
    _header_safe_prompt = _sanitize_prompt(_header_prompt)
    _header_map_resp = _gpt_client.beta.chat.completions.parse(
        model=_deployment,
        messages=[{
            "role": "user",
            "content": _header_safe_prompt,
        }],
        response_format=_HeaderMapping,
        max_completion_tokens=500,
    ).choices[0].message.parsed

    _required_map = {
        _header_map_resp.Target_Table_Name: "Target_Table_Name",
        _header_map_resp.Target_Column_Name: "Target_Column_Name",
    }
    _optional_map = {
        _header_map_resp.Target_Data_Type: "Target_Data_Type",
        _header_map_resp.Target_Description: "Target_Description",
    }
    for _orig, _canon in _required_map.items():
        if not _orig:
            raise HTTPException(
                400,
                f"LLM could not identify a column for '{_canon}' in the target CSV. "
                f"Detected headers: {_actual_headers}",
            )
    _rename_map = {
        **{k: v for k, v in _required_map.items() if k and k != v},
        **{k: v for k, v in _optional_map.items() if k and k != v},
    }
    if _rename_map:
        target_df = target_df.rename(columns=_rename_map)
    # ─────────────────────────────────────────────────────────────────────────
    
    _emb_client = AzureOpenAI(
        azure_endpoint=os.getenv("AZURE_EMBEDDING_API_BASE"),
        api_key=os.getenv("AZURE_EMBEDDING_API_KEY"),
        api_version=os.getenv("AZURE_EMBEDDING_API_VERSION", "2023-05-15"),
    )
    _emb_deployment = os.getenv("AZURE_EMBEDDING_DEPLOYMENT", "ada-002")
    _EMB_THRESHOLD = 0.9
    _COL_THRESHOLD = 0.9

    # ── Pydantic schemas ──────────────────────────────────────────────────────
    class MatchResult(_BaseModel):
        best_match: str = _Field(
            description="Best matching target name from the candidates list, or 'NO MATCH' if none fits."
        )
        confidence_score: float = _Field(description="Confidence score between 0.0 and 1.0.")
        reasoning: str = _Field(description="One sentence explanation for the match.")

    class GAPResult(_BaseModel):
        gap_status: Literal[
            "Mapped",
            "Data Type Mismatch",
            "Gap (Missing in Target)",
            "Definition Conflict",
        ]
        reasoning: str = _Field(
            description=(
                "A clear, jargon-free sentence explaining the classification outcome, "
                "written for business and data stakeholders. Focus on business impact, "
                "data reliability, and any action required — avoid technical implementation details."
            )
        )

    # ── Step 1: Extract source table/column info ──────────────────────────────
    rows = []
    for table in data.get("tables", []):
        tbl_name = table.get("name", "")
        table_asset_id = table.get("id", "")
        if tbl_name.startswith("LocalDateTable_") or tbl_name.startswith("DateTableTemplate_"):
            continue
        steps = table.get("ingestion", {}).get("steps", [])
        full_script = "\n\n".join(s.get("expression", "") for s in steps)
        for col in table.get("columns", []):
            col_name = col.get("name")
            col_asset_id = col.get("id", "")
            is_derived = "No"
            transform_logic = []
            for s in steps:
                expr = s.get("expression", "")
                if f'"{col_name}"' in expr and s.get("step_type", "") in ("derive", "rename", "change_type"):
                    is_derived = "Yes"
                    transform_logic.append(expr)
            rows.append({
                "Table_Asset_ID": table_asset_id,
                "Source_Table_Name": tbl_name,
                "Column_Asset_ID": col_asset_id,
                "Source_Column_Name": col_name,
                "Source_Data_Type": col.get("data_type"),
                "Is_Derived_Field": is_derived,
                "Description": col.get("description", "N/A"),
                "Source_Transformation_Logic": "\n".join(transform_logic),
                "Full_Table_Transformations": full_script,
            })

    if not rows:
        raise HTTPException(400, "No source tables/columns found in the uploaded JSON.")

    src_df = pd.DataFrame(rows)

    # ── Embedding + similarity helpers ────────────────────────────────────────
    def _embed_batch(texts: list) -> list:
        """Embed multiple texts in one API call; chunks at 256 to respect API limits.
        Returns a list of embeddings in the same order as *texts*.
        """
        if not texts:
            return []
        CHUNK = 256
        embeddings: list = []
        for i in range(0, len(texts), CHUNK):
            batch = texts[i : i + CHUNK]
            resp = _emb_client.embeddings.create(model=_emb_deployment, input=batch)
            embeddings.extend(
                item.embedding
                for item in sorted(resp.data, key=lambda x: x.index)
            )
        return embeddings

    def _embed(text: str) -> list:
        return _embed_batch([text])[0]

    def _cosine(a, b) -> float:
        va, vb = np.asarray(a), np.asarray(b)
        return float(np.dot(va, vb) / (np.linalg.norm(va) * np.linalg.norm(vb)))

    # ── Step 2: Table-level mapping ───────────────────────────────────────────
    def _run_gap_pipeline() -> dict:
        unique_src_tables = src_df["Source_Table_Name"].dropna().unique().tolist()
        unique_tgt_entities = target_df["Target_Table_Name"].dropna().unique().tolist()

        all_names = list(set(unique_src_tables + unique_tgt_entities))
        all_vecs = _embed_batch(all_names)  # single batched API call
        emb_map = dict(zip(all_names, all_vecs))

        # Pre-compute ALL column embeddings in one batch before processing table
        # pairs. Without this, _map_columns re-embeds every column name from
        # scratch for each pair, multiplying API calls by the number of pairs.
        _all_col_names = list({
            *src_df["Source_Column_Name"].dropna().tolist(),
            *target_df["Target_Column_Name"].dropna().tolist(),
        })
        _all_col_vecs = _embed_batch(_all_col_names)
        global_col_emb: dict = dict(zip(_all_col_names, _all_col_vecs))

        src_emb = {s: emb_map[s] for s in unique_src_tables}
        tgt_emb = {t: emb_map[t] for t in unique_tgt_entities}

        def _map_table(source: str) -> dict:
            scored = sorted(
                [(t, _cosine(src_emb[source], tgt_emb[t])) for t in tgt_emb],
                key=lambda x: x[1], reverse=True,
            )
            best, score = scored[0]
            tbl_asset_id = src_df.loc[src_df["Source_Table_Name"] == source, "Table_Asset_ID"].iat[0] if not src_df[src_df["Source_Table_Name"] == source].empty else ""
            if score >= _EMB_THRESHOLD:
                return {"Table_Asset_ID": tbl_asset_id, "Source Table": source, "Mapped Target Entity": best,
                        "Confidence Score": round(score, 4), "Method": "Embedding",
                        "Reasoning": "Embedding confidence above threshold."}
            top5 = scored[:5]
            candidates_str = "\n".join(f"- {n} (embedding score: {s:.4f})" for n, s in top5)
            prompt = (
                f'You are a data mapping expert. The embedding model was not confident enough to automatically map the source table.\n\n'
                f'Source table: "{source}"\n\n'
                f'Top candidate target tables ranked by embedding similarity:\n{candidates_str}\n\n'
                f'Pick the single best matching target table. If none is a reasonable match, '
                f'set best_match to "NO MATCH" and confidence_score to 0.0.'
            )
            safe_prompt = _sanitize_prompt(prompt)
            res = _gpt_client.beta.chat.completions.parse(
                model=_deployment,
                messages=[{"role": "user", "content": safe_prompt}],
                response_format=MatchResult,
                max_completion_tokens=3000,
            ).choices[0].message.parsed
            final = res.best_match if res.confidence_score > 0.5 else "NO MATCH (Score too low)"
            return {"Table_Asset_ID": tbl_asset_id, "Source Table": source, "Mapped Target Entity": final,
                    "Confidence Score": round(res.confidence_score, 4), "Method": "LLM Fallback",
                    "Reasoning": res.reasoning}

        with ThreadPoolExecutor(max_workers=10) as ex:
            futures = {ex.submit(_map_table, s): s for s in unique_src_tables}
            tbl_mapping = [f.result() for f in _as_completed(futures)]
        tbl_mapping_df = pd.DataFrame(tbl_mapping)

        # ── Step 3: Column-level mapping ─────────────────────────────────────
        def _map_columns(table_row: pd.Series) -> list:
            src_tbl = table_row["Source Table"]
            tgt_tbl = table_row["Mapped Target Entity"]
            if str(tgt_tbl).startswith("NO MATCH"):
                return []

            src_tbl_df = src_df[src_df["Source_Table_Name"] == src_tbl].drop_duplicates("Source_Column_Name")
            src_cols = src_tbl_df["Source_Column_Name"].dropna().unique().tolist()
            src_enrich = src_tbl_df.set_index("Source_Column_Name").to_dict(orient="index")
            src_desc = {c: d.get("Description", "N/A") for c, d in src_enrich.items()}

            tgt_tbl_df = target_df[target_df["Target_Table_Name"] == tgt_tbl]
            tgt_cols = tgt_tbl_df["Target_Column_Name"].dropna().unique().tolist()
            desc_col = next((c for c in ("Description", "Target_Description") if c in tgt_tbl_df.columns), None)
            tgt_desc = (
                tgt_tbl_df.drop_duplicates("Target_Column_Name")
                .set_index("Target_Column_Name")[desc_col].fillna("N/A").to_dict()
            ) if desc_col else {}

            if not src_cols or not tgt_cols:
                return []

            # Use the pre-computed global cache; embed any stragglers on-demand.
            col_emb = global_col_emb
            missing = [c for c in src_cols + tgt_cols if c not in col_emb]
            if missing:
                col_emb = {**col_emb, **dict(zip(missing, _embed_batch(missing)))}
            tgt_col_emb = {c: col_emb[c] for c in tgt_cols if c in col_emb}
            available = set(tgt_cols)

            results = []
            for sc in src_cols:
                if not available:
                    results.append({"Source Table": src_tbl, "Target Table": tgt_tbl,
                                    "Source Column": sc, "Mapped Target Column": "NO MATCH (All targets exhausted)",
                                    "Confidence Score": 0.0, "Method": "N/A",
                                    "Reasoning": "All target columns already mapped."})
                    continue

                scored = sorted(
                    [(c, _cosine(col_emb[sc], tgt_col_emb[c])) for c in available],
                    key=lambda x: x[1], reverse=True,
                )
                best_c, best_s = scored[0]

                if best_s >= _COL_THRESHOLD:
                    final_c, final_s, method, reasoning = best_c, round(best_s, 4), "Embedding", "Embedding confidence above threshold."
                else:
                    top5 = scored[:5]
                    candidates_str = "\n".join(
                        f"- {n} (embedding score: {s:.4f}) | description: {tgt_desc.get(n, 'N/A')}"
                        for n, s in top5
                    )
                    prompt = (
                        f'You are a data mapping expert. The embedding model was not confident enough to automatically map this column.\n\n'
                        f'Source table: "{src_tbl}"\nSource column: "{sc}"\n'
                        f'Source column description: "{src_desc.get(sc, "N/A")}"\n\n'
                        f'Mapped target table: "{tgt_tbl}"\n\n'
                        f'Top candidate target columns ranked by embedding similarity (with descriptions):\n{candidates_str}\n\n'
                        f'Use both the column names and their descriptions to pick the single best matching target column.\n'
                        f'If none is a reasonable match, set best_match to "NO MATCH" and confidence_score to 0.0.'
                    )
                    safe_prompt = _sanitize_prompt(prompt)
                    res = _gpt_client.beta.chat.completions.parse(
                        model=_deployment,
                        messages=[{"role": "user", "content": safe_prompt}],
                        response_format=MatchResult,
                        max_completion_tokens=3000,
                    ).choices[0].message.parsed
                    method = "LLM Fallback"
                    final_c = res.best_match if res.confidence_score > 0.5 else "NO MATCH (Score too low)"
                    final_s = round(res.confidence_score, 4)
                    reasoning = res.reasoning

                available.discard(final_c)
                results.append({"Source Table": src_tbl, "Target Table": tgt_tbl,
                                 "Source Column": sc, "Mapped Target Column": final_c,
                                 "Confidence Score": final_s, "Method": method, "Reasoning": reasoning})
            return results

        with ThreadPoolExecutor(max_workers=15) as ex:
            pair_futures = [ex.submit(_map_columns, row) for _, row in tbl_mapping_df.iterrows()]
            col_mapping = []
            for f in _as_completed(pair_futures):
                col_mapping.extend(f.result())

        col_df = pd.DataFrame(col_mapping)
        if col_df.empty:
            return {
                "gap_analysis": [],
                "summary": {},
                "total_mappings": 0,
                "table_mappings": tbl_mapping_df.to_dict(orient="records"),
            }

        # ── Step 4: Enrich with source + target metadata ──────────────────────
        src_enrich_cols = [c for c in src_df.columns if c not in ("Source_Table_Name", "Source_Column_Name")]
        col_df = col_df.merge(
            src_df[["Source_Table_Name", "Source_Column_Name"] + src_enrich_cols].drop_duplicates(
                ["Source_Table_Name", "Source_Column_Name"]
            ),
            left_on=["Source Table", "Source Column"],
            right_on=["Source_Table_Name", "Source_Column_Name"],
            how="left",
        ).drop(columns=["Source_Table_Name", "Source_Column_Name"], errors="ignore")

        tgt_enrich_cols = [c for c in target_df.columns if c not in ("Target_Table_Name", "Target_Column_Name")]
        col_df = col_df.merge(
            target_df[["Target_Column_Name"] + tgt_enrich_cols].drop_duplicates("Target_Column_Name"),
            left_on="Mapped Target Column",
            right_on="Target_Column_Name",
            how="left",
        ).drop(columns=["Target_Column_Name"], errors="ignore")

        # ── Step 5: GAP classification (batched) ──────────────────────────────
        # Send CLASSIFY_BATCH column pairs per GPT call instead of one per call,
        # reducing total API round-trips by ~10× while preserving full per-row
        # reasoning quality.
        CLASSIFY_BATCH = 10

        class _GAPBatchItem(_BaseModel):
            row_index: int = _Field(
                description="0-based index of the pair within this batch (0 to N-1)."
            )
            gap_status: Literal[
                "Mapped",
                "Data Type Mismatch",
                "Gap (Missing in Target)",
                "Definition Conflict",
            ]
            reasoning: str = _Field(
                description=(
                    "A clear, jargon-free sentence for business and data stakeholders. "
                    "PART 1: why these columns are a match (shared business concept/purpose). "
                    "PART 2: why this specific GAP status was assigned."
                )
            )

        class _GAPBatch(_BaseModel):
            results: list[_GAPBatchItem]

        def _classify_batch(batch: list) -> list:
            """Classify a batch of (orig_idx, row_dict) pairs in one GPT call."""
            try:
                pairs_text = ""
                for local_i, (_, row) in enumerate(batch):
                    pairs_text += (
                        f"\n[Pair {local_i}]\n"
                        f"Source Table       : {row.get('Source Table', 'N/A')}\n"
                        f"Source Column      : {row.get('Source Column', 'N/A')}\n"
                        f"Source Data Type   : {row.get('Source_Data_Type', 'N/A')}\n"
                        f"Source Description : {row.get('Description', 'N/A')}\n"
                        f"Is Derived Field   : {row.get('Is_Derived_Field', 'N/A')}\n"
                        f"Target Table       : {row.get('Target Table', 'N/A')}\n"
                        f"Target Column      : {row.get('Mapped Target Column', 'N/A')}\n"
                        f"Target Data Type   : {row.get('Target_Data_Type', 'N/A')}\n"
                        f"Target Description : {row.get('Target_Description', 'N/A')}\n"
                        f"Confidence Score   : {row.get('Confidence Score', 'N/A')}\n"
                        f"Mapping Method     : {row.get('Method', 'N/A')}\n"
                        f"Mapping Reasoning  : {row.get('Reasoning', 'N/A')}\n"
                    )

                prompt = (
                    f'You are a data governance advisor helping business and data stakeholders '
                    f'understand the results of a data migration gap analysis.\n\n'
                    f'Classify each mapped column pair below into exactly one status:\n'
                    f'- "Mapped": Clean match — types compatible and definitions align.\n'
                    f'- "Data Type Mismatch": Matched but source and target data types differ.\n'
                    f'- "Gap (Missing in Target)": No suitable target column found.\n'
                    f'- "Definition Conflict": Matched but descriptions indicate different concepts.\n\n'
                    f'For each pair write a single concise sentence for "reasoning" in two parts joined naturally:\n'
                    f'  PART 1 — WHY these columns are a match (shared business concept from names/descriptions).\n'
                    f'  PART 2 — WHY this specific GAP status was assigned (cite the actual data type difference, '
                    f'missing column, conflicting descriptions, or clean alignment).\n'
                    f'Write in plain business language — no code, no schema terms. Reference actual column/table '
                    f'names, state the business impact, and end with any recommended action.\n\n'
                    f'Return results for ALL {len(batch)} pairs using row_index 0 through {len(batch) - 1}.\n'
                    f'{pairs_text}'
                )
                safe_prompt = _sanitize_prompt(prompt)

                parsed = _gpt_client.beta.chat.completions.parse(
                    model=_deployment,
                    messages=[{"role": "user", "content": safe_prompt}],
                    response_format=_GAPBatch,
                    max_completion_tokens= 3000* len(batch),
                ).choices[0].message.parsed

                result_map = {item.row_index: item for item in parsed.results}
                output = []
                for local_i, (orig_idx, _) in enumerate(batch):
                    if local_i in result_map:
                        item = result_map[local_i]
                        output.append((orig_idx, item.gap_status, item.reasoning))
                    else:
                        output.append((orig_idx, "Error", "LLM did not return a result for this pair."))
                return output
            except Exception as exc:
                return [(orig_idx, "Error", str(exc)) for orig_idx, _ in batch]

        _all_pairs = [(idx, row.to_dict()) for idx, row in col_df.iterrows()]
        _batches = [_all_pairs[i : i + CLASSIFY_BATCH] for i in range(0, len(_all_pairs), CLASSIFY_BATCH)]
        gap_results: dict = {}

        with ThreadPoolExecutor(max_workers=20) as ex:
            gap_futures = [ex.submit(_classify_batch, b) for b in _batches]
            for f in _as_completed(gap_futures):
                for orig_idx, status, rsn in f.result():
                    gap_results[orig_idx] = (status, rsn)

        gap_df = col_df.copy()
        gap_df["GAP_Status"] = [gap_results[i][0] for i in gap_df.index]
        gap_df["GAP_Reasoning"] = [gap_results[i][1] for i in gap_df.index]

        output_cols = [
            "Source Table", "Target Table","Column_Asset_ID", "Source Column", "Mapped Target Column",
            "Confidence Score", "Method", "Reasoning",
            "Source_Data_Type", "Target_Data_Type", "GAP_Status", "GAP_Reasoning",
        ]
        gap_df = gap_df[[c for c in output_cols if c in gap_df.columns]]

        return {
            "gap_analysis": gap_df.fillna("N/A").to_dict(orient="records"),
            "summary": gap_df["GAP_Status"].value_counts().to_dict(),
            "total_mappings": len(gap_df),
            "table_mappings": tbl_mapping_df.to_dict(orient="records"),
        }

    try:
        result = await asyncio.to_thread(_run_gap_pipeline)
        return jsonable_encoder(result)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Gap analysis failed: {exc}")

@app.post("/gapanalysis/", tags=["Gap Analysis"])
async def gapanalysis(
    file: str = Form(..., description="Extracted source BI model as a JSON string"),
    target_model: UploadFile = File(..., description="Target data model CSV file"),
):
    """Run a hybrid embedding + LLM gap analysis between a source BI model JSON object and a target data model CSV.

    Returns the full analysis result plus a `job_id` that can be used to retrieve
    the result later via **GET /gapanalysis/{job_id}**.
    """
    try:
        source_data = json.loads(file)
    except Exception as exc:
        raise HTTPException(400, f"Invalid source JSON: {exc}")

    target_filename = target_model.filename or "unknown.csv"
    source_model_name = source_data.get("name", "unknown")
    job_id = str(uuid.uuid4())

    result = await _handle_gapanalysis(file=source_data, target_model=target_model)

    # Persist to Postgres (non-blocking; errors are logged, not raised)
    try:
        from postgres_writer import save_gap_analysis_result
        await asyncio.to_thread(
            save_gap_analysis_result,
            job_id,
            source_model_name,
            target_filename,
            result.get("gap_analysis", []),
            result.get("summary", {}),
            result.get("table_mappings", []),
        )
    except Exception as exc:
        print(f"[gapanalysis] Warning: failed to save to Postgres: {exc}")

    return {**result, "job_id": job_id}

@app.get("/gapanalysis/{job_id}", tags=["Gap Analysis"])
async def fetch_gap_analysis_endpoint(job_id: str):
    """
    Retrieve a previously computed gap analysis result from Postgres by `job_id`.

    The `job_id` is returned in the response of **POST /gapanalysis/**.

    **Response** mirrors the POST response:
    ```json
    {
      "job_id": "...",
      "created_at": "...",
      "source_model_name": "...",
      "target_file_name": "...",
      "status": "success",
      "gap_analysis": [...],
      "summary": {...},
      "total_mappings": 42,
      "table_mappings": [...]
    }
    ```
    """
    from postgres_writer import fetch_gap_analysis_result

    try:
        result = await asyncio.to_thread(fetch_gap_analysis_result, job_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch gap analysis result: {exc}")

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No gap analysis job found with job_id='{job_id}'.",
        )

    return jsonable_encoder(result)

# KPI Rationalization

from pydantic import BaseModel
from kpi_rationalization import extract_kpi, extract_attributes, rationalize


class FileInput(BaseModel):
    content: dict[str, Any]


def _df_to_records(df):
    """Convert a DataFrame to JSON-safe records (NaN → null)."""
    return json.loads(df.to_json(orient="records", date_format="iso"))


@app.post("/rationalize", tags=["KPI Rationalization"])
async def rationalize_endpoint(files: List[FileInput]):
    """
    Pass one or more BI report JSON files and receive rationalization results.
    Results are persisted to Postgres and a `job_id` is returned so you can
    retrieve them later via **GET /rationalize/{job_id}**.

    **Request body** — JSON array, one item per file:
    ```json
    [
      { "content": { ...file contents... } },
      { "content": { ...file contents... } }
    ]
    ```

    **Response:**
    ```json
    {
      "job_id": "...",
      "rationalized_catalog": [...],
      "rationalized_overlaps_duplicates": [...],
      "rationalized_verdict_summary": [...]
    }
    ```
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    file_data = [f.content for f in files]
    job_id = str(uuid.uuid4())

    try:
        df_summary, _col_deps, _meas_deps = extract_kpi(file_data)
        _ds, _tables, df_attrs, _rels     = extract_attributes(file_data)
        # Run rationalization separately for KPIs and Attributes so each type
        # is compared only within its own domain (no cross-type noise).
        df_rat_kpi,  overlap_kpi,  verdict_kpi  = rationalize(df_summary=df_summary)
        df_rat_attr, overlap_attr, verdict_attr = rationalize(df_attrs=df_attrs)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Combine KPI and Attribute results — schema is identical so lists merge cleanly
    catalog_records = _df_to_records(df_rat_kpi)  + _df_to_records(df_rat_attr)
    overlap_records = _df_to_records(overlap_kpi) + _df_to_records(overlap_attr)
    summary_records = _df_to_records(verdict_kpi) + _df_to_records(verdict_attr)

    # Persist to Postgres asynchronously (non-blocking; errors are logged, not raised)
    try:
        from postgres_writer import save_rationalization_result
        await asyncio.to_thread(
            save_rationalization_result,
            job_id,
            len(files),
            catalog_records,
            overlap_records,
            summary_records,
        )
    except Exception as exc:
        print(f"[rationalize] Warning: failed to save to Postgres: {exc}")

    return {
        "job_id":                           job_id,
        "rationalized_catalog":             catalog_records,
        "rationalized_overlaps_duplicates": overlap_records,
        "rationalized_verdict_summary":     summary_records,
    }


@app.get("/rationalize/{job_id}", tags=["KPI Rationalization"])
async def fetch_rationalization_endpoint(job_id: str):
    """
    Retrieve a previously computed KPI rationalization result from Postgres by `job_id`.

    The `job_id` is returned in the response of **POST /rationalize**.

    **Response** mirrors the POST response:
    ```json
    {
      "job_id": "...",
      "created_at": "...",
      "file_count": 2,
      "status": "success",
      "rationalized_catalog": [...],
      "rationalized_overlaps_duplicates": [...],
      "rationalized_verdict_summary": [...]
    }
    ```
    """
    from postgres_writer import fetch_rationalization_result

    try:
        result = await asyncio.to_thread(fetch_rationalization_result, job_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch rationalization result: {exc}")

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No rationalization job found with job_id='{job_id}'.",
        )

    return jsonable_encoder(result)



# ─────────────────────────────────────────────────────────────────────────────
# Tier 1 Validation endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/validation/validate", tags=["Validation"])
async def validate_json(
    file_name: str = Form(
        ...,
        description="Exact filename as stored in Postgres e.g. 'Sample Sales Dashboard.pbix'. Use GET /list-reports/ to find it.",
    ),
    tool_name: str = Form(
        ...,
        description="Tool type: 'tableau-workbook', 'qlikview', or 'powerbi'.",
    ),
    pbix_file: UploadFile = File(
        None,
        description=(
            "Upload the source .pbix file (optional). "
            "When omitted the validator runs in cross-validation mode "
            "(validates the JSON internally without comparing to a PBIX)."
        ),
    ),
    bim_file: UploadFile = File(
        None,
        description=(
            "Upload a model.bim file exported from Tabular Editor 2 (optional). "
            "Enables full D1-D5 semantic checks even when the DataModel "
            "inside the PBIX is binary."
        ),
    ),
    twb_file: UploadFile = File(
        None,
        description=(
            "Upload the source .twb or .twbx file (required for Tableau validation). "
            "Used to run T1\u2013T18 checks comparing the Tableau workbook against the extracted JSON."
        ),
    ),
):
    """
    Run the full Tier 1 validation (D1–D7 checks).

    Fetches the extraction JSON from Postgres (same source as **POST /fetch-report/**),
    then runs all validation checks. Optionally accepts the original .pbix and/or
    model.bim as file uploads for deeper semantic comparison.

    Returns all artifacts as JSON:
    - **score** — overall validation score (0–100 %)
    - **verdict** — PASS / FAIL
    - **check_summary** — per-check (D1–D7) pass/fail breakdown
    - **gaps_count** — number of FAIL / MISSING items
    - **report** — full D1–D7 result rows
    - **gap_report** — only FAIL/MISSING rows sorted by severity
    - **excel_download_url** — URL to download the detailed Excel report
    """
    from postgres_writer import get_db_session
    from postgres_models import ExtractionLog

    # ── Fetch JSON from Postgres ──────────────────────────────────
    homo_json_dict = None
    try:
        with get_db_session() as session:
            log_entry = (
                session.query(ExtractionLog)
                .filter(
                    ExtractionLog.tool_type == tool_name,
                    ExtractionLog.status == "SUCCESS",
                    ExtractionLog.file_name == file_name.strip(),
                )
                .order_by(ExtractionLog.completed_at.desc())
                .first()
            )

            if log_entry is None:
                available = (
                    session.query(ExtractionLog.file_name, ExtractionLog.status)
                    .filter(ExtractionLog.tool_type == tool_name)
                    .order_by(ExtractionLog.completed_at.desc())
                    .limit(10)
                    .all()
                )
                raise HTTPException(
                    status_code=404,
                    detail={
                        "message": f"No successful extraction found for '{file_name}' with tool '{tool_name}'.",
                        "hint": "Use GET /list-reports/ to see available file names.",
                        "available_files": [r.file_name for r in available],
                    },
                )

            if log_entry.result is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Extraction log found for '{file_name}' but result JSON was not stored.",
                )

            homo_json_dict = dict(log_entry.result)

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch report from Postgres: {exc}")

    # ── Read uploaded file bytes ───────────────────────────────────
    pbix_bytes   = await pbix_file.read() if pbix_file and pbix_file.filename else None
    bim_bytes    = await bim_file.read()  if bim_file  and bim_file.filename  else None
    twb_bytes    = await twb_file.read()  if twb_file  and twb_file.filename  else None
    twb_filename = twb_file.filename      if twb_file  and twb_file.filename  else None

    # ── Tableau branch ────────────────────────────────────────────
    if tool_name == "tableau-workbook":
        # Allow the file to be uploaded via either twb_file or pbix_file
        if not twb_bytes and pbix_bytes:
            twb_bytes    = pbix_bytes
            twb_filename = (pbix_file.filename if pbix_file and pbix_file.filename else None)
            pbix_bytes   = None

        if not twb_bytes:
            raise HTTPException(
                status_code=400,
                detail=(
                    "A .twb or .twbx file must be uploaded via the 'twb_file' field "
                    "for Tableau validation."
                ),
            )

        def _run_tableau():
            import tempfile
            import shutil as _shutil
            import os as _os
            from dataclasses import asdict as _asdict

            # Write homo JSON to a temp file (run_validation expects a file path)
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8"
            ) as jf:
                json.dump(homo_json_dict, jf)
                json_tmp = jf.name

            # Write TWB/TWBX bytes to a temp file
            _sfx = ".twbx" if twb_filename and twb_filename.lower().endswith(".twbx") else ".twb"
            with tempfile.NamedTemporaryFile(suffix=_sfx, delete=False) as tf:
                tf.write(twb_bytes)
                twb_tmp = tf.name

            out_tmp = Path(tempfile.mkdtemp())
            try:
                report = _run_tableau_validation(twb_tmp, json_tmp, str(out_tmp))

                # Read the structured outputs written by run_validation
                stem         = Path(twb_tmp).stem
                summary_path = out_tmp / f"{stem}_validation_summary.json"
                gap_path     = out_tmp / f"{stem}_gap_report.json"

                with summary_path.open(encoding="utf-8") as f:
                    summary = json.load(f)
                with gap_path.open(encoding="utf-8") as f:
                    gap_data = json.load(f)

                report_dict = {"results": [_asdict(r) for r in report.results]}

                # ── Semantic / visual score breakdown ────────────────
                _SEMANTIC_IDS = {"T1","T2","T3","T4","T5","T8","T9","T12","T13","T14","T16","T17","T18"}
                _VISUAL_IDS   = {"T6","T7","T10","T11","T15"}
                group_scores  = summary["group_scores"]

                sem_passed = sum(v["passed"] for k, v in group_scores.items() if k in _SEMANTIC_IDS)
                sem_total  = sum(v["total"]  for k, v in group_scores.items() if k in _SEMANTIC_IDS)
                vis_passed = sum(v["passed"] for k, v in group_scores.items() if k in _VISUAL_IDS)
                vis_total  = sum(v["total"]  for k, v in group_scores.items() if k in _VISUAL_IDS)

                semantic_score   = round(sem_passed / sem_total * 100, 2) if sem_total else 0.0
                semantic_verdict = "PASS" if semantic_score >= 80.0 else "FAIL"
                visual_score     = round(vis_passed / vis_total * 100, 2) if vis_total else 0.0
                visual_verdict   = "PASS" if visual_score >= 80.0 else "FAIL"

                score_breakdown = {
                    "overall": {
                        "score":   summary["score"],
                        "verdict": summary["verdict"],
                    },
                    "semantic": {
                        "scope":          "semantic",
                        "score":          semantic_score,
                        "verdict":        semantic_verdict,
                        "checks_passed":  sem_passed,
                        "checks_total":   sem_total,
                        "checks":         {k: v for k, v in group_scores.items() if k in _SEMANTIC_IDS},
                    },
                    "visual": {
                        "scope":          "visual",
                        "score":          visual_score,
                        "verdict":        visual_verdict,
                        "checks_passed":  vis_passed,
                        "checks_total":   vis_total,
                        "checks":         {k: v for k, v in group_scores.items() if k in _VISUAL_IDS},
                    },
                }

                return {
                    "workbook_id":       Path(twb_tmp).stem[:8],
                    "score":             summary["score"],
                    "confidence_score":  summary["confidence_score"],
                    "verdict":           summary["verdict"],
                    "semantic_score":    semantic_score,
                    "semantic_verdict":  semantic_verdict,
                    "visual_score":      visual_score,
                    "visual_verdict":    visual_verdict,
                    "score_breakdown":   score_breakdown,
                    "has_critical_gaps": summary["has_critical_gaps"],
                    "total_checks":      summary["total_checks"],
                    "gaps_count":        summary["gap_count"],
                    "timestamp":         summary["timestamp"],
                    "check_summary":     group_scores,
                    "report_dict":       report_dict,
                    "gap_dict":          gap_data,
                }
            finally:
                try:
                    _os.unlink(json_tmp)
                    _os.unlink(twb_tmp)
                    _shutil.rmtree(out_tmp, ignore_errors=True)
                except Exception:
                    pass

        try:
            result = await asyncio.to_thread(_run_tableau)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Tableau validation failed: {exc}")

        return {
            "workbook_id":       result["workbook_id"],
            "file_name":         file_name,
            "tool_name":         tool_name,
            "score":             result["score"],
            "semantic_score":    result["semantic_score"],
            "semantic_verdict":  result["semantic_verdict"],
            "visual_score":      result["visual_score"],
            "visual_verdict":    result["visual_verdict"],
            "score_breakdown":   result["score_breakdown"],
            "confidence_score":  result["confidence_score"],
            "verdict":           result["verdict"],
            "has_critical_gaps": result["has_critical_gaps"],
            "total_checks":      result["total_checks"],
            "gaps_count":        result["gaps_count"],
            "timestamp":         result["timestamp"],
            "check_summary":     result["check_summary"],
            "report":            result["report_dict"],
            "gap_report":        result["gap_dict"],
            "excel_base64":      None,
        }

    # ── PowerBI / other tools branch ──────────────────────────────
    def _run():
        return _run_validation(
            homo_json_dict=homo_json_dict,
            pbix_bytes=pbix_bytes,
            bim_bytes=bim_bytes,
        )

    try:
        result = await asyncio.to_thread(_run)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Validation failed: {exc}")

    workbook_id = result["workbook_id"]

    import base64
    excel_b64 = (
        base64.b64encode(result["excel_bytes"]).decode()
        if result.get("excel_bytes") else None
    )

    return {
        "workbook_id":      workbook_id,
        "file_name":        file_name,
        "tool_name":        tool_name,
        "score":            result["score"],
        "verdict":          result["verdict"],
        "semantic_score":   result["semantic_score"],
        "semantic_verdict": result["semantic_verdict"],
        "visual_score":     result["visual_score"],
        "visual_verdict":   result["visual_verdict"],
        "score_breakdown":  result["score_breakdown"],
        "total_checks":     result["total_checks"],
        "gaps_count":       result["gaps_count"],
        "timestamp":        result["timestamp"],
        "check_summary":    result["check_summary"],
        "report":           result["report_dict"],
        "gap_report":       result["gap_dict"],
        "excel_base64":     excel_b64,
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
 
 