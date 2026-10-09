from dataclasses import dataclass
from typing import Dict, Any, List
import json
import asyncio
import os
import uuid
from datetime import datetime, timezone

import aiofiles

from autogen_core import (
    MessageContext,
    RoutedAgent,
    SingleThreadedAgentRuntime,
    TopicId,
    message_handler,
    type_subscription,
    ClosureAgent,
    ClosureContext,
)

from autogen_core.models import SystemMessage, UserMessage
from autogen_core._default_subscription import DefaultSubscription
from autogen_core._default_topic import DefaultTopicId
from config import azure_client
from prompts_powerbi import EXTRACTION_PROMPTS

from langchain_core.output_parsers import JsonOutputParser

parser = JsonOutputParser()

# ---------------------------------------------------------------------------
# Common-model schema: keys in exact order they appear in common_model.json.
# Tuples (not frozensets) so dict comprehensions preserve this order.
# ---------------------------------------------------------------------------
_TOP_KEYS = (
    "schema_version", "model_id", "name", "extracted_at",
    "data_sources", "tables", "relationships", "calculations",
    "report_pages",      # PowerBI-specific: extracted from Report/Layout
    "roles",             # Row-Level Security roles (injected post-flow, verbatim DAX)
    # "report_filters",  # TODO: re-enable when UI supports report-level filters
)

_DATA_SOURCE_KEYS = (
    "id", "name", "source_type", "connection_mode", "authentication_method",
    "server", "database", "schema", "path", "gateway", "refresh_frequency",
)

_TABLE_KEYS = (
    "id", "name", "table_type", "source_data_source_id",
    "is_materialized", "hidden", "description", "columns", "hierarchies", "ingestion",
)

_COLUMN_KEYS = (
    "name", "data_type", "nullable", "hidden", "semantic_role",
    "used_in_relationships", "used_in_filters", "used_in_groupby",
    "used_in_calculations", "distinct_count_high", "description",
    "variations",
    # Calc-column lineage lives on the column itself — DAX expression body,
    # sort-by-column reference, format string, and Field Parameter metadata.
    # FE reads these directly off the column entry, NOT off calculations[].
    "expression", "sort_by_column", "format_string", "parameter_metadata",
)

_STEP_KEYS = (
    "order", "step_type", "description", "native_expressions",
)

_RELATIONSHIP_KEYS = (
    "id", "left_table_id", "left_column", "right_table_id", "right_column",
    "cardinality", "join_type", "active", "filter_direction",
    "enforced_integrity", "relationship_type", "note",
)

_CALCULATION_KEYS = (
    "id", "name", "home_table", "description", "semantic_type", "aggregation_behavior",
    "data_type", "format_string", "is_base_measure", "reusable",
    "depends_on_columns", "depends_on_measures", "display", "expressions",
)

_PAGE_KEYS = (
    "page_id", "display_name", "width", "height", "visuals",
    # "filters",  # TODO: re-enable when UI supports page-level filters
)

_VISUAL_KEYS = (
    "visual_id", "visual_type", "title", "position", "fields",
    # "bookmarks",  # TODO: re-enable when UI supports bookmarks
    # "filters",    # TODO: re-enable when UI supports visual-level filters
)

# _FILTER_KEYS = (  # TODO: re-enable when UI supports filters
#     "table", "column", "filter_type", "values",
# )

_POSITION_KEYS = (
    "x", "y", "width", "height", "z_order",
)

_FIELD_KEYS = (
    "role", "table", "column", "aggregation", "query_ref", "display_name",
)


# Power BI internal auto-generated tables that have no business meaning
_INTERNAL_TABLE_PREFIXES = ("LocalDateTable_", "DateTableTemplate_")


# Standard 4-level Date Hierarchy Power BI always materializes on its auto-date
# tables (LocalDateTable_* and DateTableTemplate_*). Fixed by the engine; safe
# to template.
_AUTODATE_HIERARCHY_LEVELS = (
    ("Year",    "Year",    0),
    ("Quarter", "Quarter", 1),
    ("Month",   "Month",   2),
    ("Day",     "Day",     3),
)


def _build_autodate_hierarchy() -> dict:
    return {
        "name": "Date Hierarchy",
        "levels": [
            {"name": n, "column": c, "ordinal": o}
            for (n, c, o) in _AUTODATE_HIERARCHY_LEVELS
        ],
    }


# Regex that pulls the 'base_table'[base_column] reference out of a
# LocalDateTable's Calendar(Date(Year(MIN('T'[c])), …)) expression.
import re as _re
_BASE_COLUMN_PATTERN = _re.compile(r"MIN\(\s*'([^']+)'\s*\[\s*([^\]]+?)\s*\]\s*\)")


def _slug_table(name: str) -> str:
    """Slug rule matching what the tables_and_schema / relationships prompts
    emit: insert _ at lowercase->uppercase boundaries, replace non-alphanumerics
    with _, lowercase, collapse repeats, strip, prefix 'tbl_'."""
    if not name:
        return ""
    s = _re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    s = _re.sub(r"[^A-Za-z0-9]+", "_", s).lower()
    s = _re.sub(r"_+", "_", s).strip("_")
    return f"tbl_{s}"


def _slug_datasource(name: str) -> str:
    """Same slug rule, prefix 'ds_' and suffix '_calculated'."""
    if not name:
        return ""
    s = _re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    s = _re.sub(r"[^A-Za-z0-9]+", "_", s).lower()
    s = _re.sub(r"_+", "_", s).strip("_")
    return f"ds_{s}_calculated"


def _autodate_standard_columns() -> list:
    """The 7 columns Power BI always materializes on auto-date tables."""
    def col(name, dt, role):
        return {
            "name": name, "data_type": dt, "nullable": False, "hidden": False,
            "semantic_role": role, "used_in_relationships": False,
            "used_in_filters": False, "used_in_groupby": False,
            "used_in_calculations": False, "distinct_count_high": (name == "Date"),
            "description": f"Auto-date {name}",
        }
    return [
        col("Date",      "datetime", "date"),
        col("Year",      "integer",  "dimension"),
        col("MonthNo",   "integer",  "dimension"),
        col("Month",     "string",   "dimension"),
        col("QuarterNo", "integer",  "dimension"),
        col("Quarter",   "string",   "dimension"),
        col("Day",       "integer",  "dimension"),
    ]


# Regexes for parsing user calc-table DAX bodies (SUMMARIZE / ADDCOLUMNS / ...).
_DAX_COL_REF_RE     = _re.compile(r"'([^']+)'\s*\[\s*([^\]]+?)\s*\]")
_DAX_QUOTED_NAME_RE = _re.compile(r'"([^"]+)"')


def _infer_calc_table_columns(expr: str, tables_by_name: dict) -> list:
    """Parse a SUMMARIZE/ADDCOLUMNS-style DAX expression and return column dicts.

    Grouping columns are 'Table'[Col] references appearing BEFORE the first
    quoted "Name" literal (which marks the start of the new-column section).
    Source-column data_type is looked up from tables_by_name when possible.

    New columns are the quoted "Name" literals; data_type is inferred from the
    aggregate function that follows (DISTINCTCOUNT/COUNT* -> integer,
    AVERAGE*/DIVIDE -> decimal, SUM/SUMX -> integer, otherwise unknown).
    """
    cols = []
    seen = set()

    first_quote = expr.find('"')
    grouping_section = expr if first_quote == -1 else expr[:first_quote]

    for m in _DAX_COL_REF_RE.finditer(grouping_section):
        src_table, src_col = m.group(1), m.group(2)
        if src_col in seen:
            continue
        seen.add(src_col)
        dt = "unknown"
        src_tbl = tables_by_name.get(src_table)
        if src_tbl:
            sc = next((c for c in src_tbl.get("columns", []) if c.get("name") == src_col), None)
            if sc:
                dt = sc.get("data_type") or "unknown"
        cols.append({
            "name": src_col, "data_type": dt, "nullable": False, "hidden": False,
            "semantic_role": "date" if dt == "datetime" else "dimension",
            "used_in_relationships": False, "used_in_filters": False,
            "used_in_groupby": True, "used_in_calculations": False,
            "distinct_count_high": dt == "datetime",
            "description": f"Inherited from {src_table}[{src_col}]",
        })

    for m in _DAX_QUOTED_NAME_RE.finditer(expr):
        new_name = m.group(1)
        if new_name in seen:
            continue
        seen.add(new_name)
        rest = expr[m.end(): m.end() + 80].upper()
        if any(fn in rest for fn in ("DISTINCTCOUNT", "COUNTROWS", "COUNTX", "COUNT")):
            dt = "integer"
        elif any(fn in rest for fn in ("AVERAGEX", "AVERAGE", "DIVIDE")):
            dt = "decimal"
        elif any(fn in rest for fn in ("SUMX", "SUM")):
            dt = "integer"
        else:
            dt = "unknown"
        cols.append({
            "name": new_name, "data_type": dt, "nullable": False, "hidden": False,
            "semantic_role": "measure", "used_in_relationships": False,
            "used_in_filters": False, "used_in_groupby": False,
            "used_in_calculations": True, "distinct_count_high": False,
            "description": "Computed by DAX",
        })
    return cols


def _ensure_calculated_tables_present(tables: list, tables_by_name: dict, dax_tables: list) -> None:
    """Reconcile tables[] against dax_tables.json — SAFETY NET for the LLM.

    The 'calculated_tables' section/prompt is the primary mechanism for emitting
    calculated tables. This function runs after it as a defence in depth:

      - If a dax_tables entry is missing from tables[], synthesize a
        deterministic stub with columns inferred from the DAX.
      - If a calc table is present, FORCE its native_expressions.dax to match
        dax_tables.Expression VERBATIM. dax_tables.json is the source of truth
        for this field. If the LLM emitted a wrong/shuffled body (which we've
        observed repeatedly), overwrite it here.

    Mutates `tables` and `tables_by_name` in place. Idempotent."""
    for dax_tbl in dax_tables:
        name = dax_tbl.get("TableName", "")
        expr = dax_tbl.get("Expression", "") or ""
        if not name or not expr:
            continue
        is_autodate = name.startswith(_INTERNAL_TABLE_PREFIXES)

        existing = tables_by_name.get(name)
        if existing is not None:
            ing = existing.setdefault("ingestion", {"steps": []})
            steps = ing.setdefault("steps", [])
            if not steps:
                steps.append({
                    "step_type": "dax_calculated_table",
                    "native_expressions": {"dax": expr},
                })
            else:
                step = steps[0]
                ne = step.setdefault("native_expressions", {})
                # Strip the wrong key (LLM sometimes still emits 'powerquery'
                # for calc tables) and ALWAYS overwrite from the source of truth.
                ne.pop("powerquery", None)
                ne["dax"] = expr
                step["native_expressions"] = ne
                step["step_type"] = "dax_calculated_table"
            continue

        columns = (_autodate_standard_columns() if is_autodate
                   else _infer_calc_table_columns(expr, tables_by_name))
        new_tbl = {
            "id": "",  # downstream main._apply_table_ids will overwrite
            "name": name,
            "table_type": "calculated",
            "source_data_source_id": _slug_datasource(name),
            "is_materialized": False,
            "description": ("Power BI auto-date table" if is_autodate
                            else "DAX calculated table"),
            "columns": columns,
            "ingestion": {
                "steps": [{
                    "step_type": "dax_calculated_table",
                    "native_expressions": {"dax": expr},
                }],
            },
        }
        if is_autodate:
            new_tbl["hierarchies"] = [_build_autodate_hierarchy()]
        tables.append(new_tbl)
        tables_by_name[name] = new_tbl


# ---------------------------------------------------------------------------
# Calc-column DAX return-type inference.
#
# pbixray's schema.json doesn't compute DAX return types — it reports calc
# columns as 'string' by default. The LLM doesn't infer them either. So we do
# it from the outermost DAX function. Conservative: when uncertain, leave the
# existing type alone.
# ---------------------------------------------------------------------------
_DAX_INT_FUNCS     = ("DATEDIFF", "YEAR", "MONTH", "DAY", "WEEKDAY", "WEEKNUM",
                      "QUARTER", "HOUR", "MINUTE", "SECOND",
                      "INT", "TRUNC", "ROUND",
                      "COUNTROWS", "COUNTX", "COUNT", "COUNTA", "DISTINCTCOUNT",
                      "RANK", "RANKX")
_DAX_DECIMAL_FUNCS = ("DIVIDE", "SUMX", "AVERAGEX", "AVERAGE", "MINX", "MAXX",
                      "POWER", "SQRT", "EXP", "LOG", "LN", "PI")
_DAX_STRING_FUNCS  = ("FORMAT", "CONCATENATE", "CONCATENATEX", "LEFT", "RIGHT",
                      "MID", "UPPER", "LOWER", "TRIM", "SUBSTITUTE", "REPT",
                      "FIXED")
_DAX_DATETIME_FUNCS = ("EDATE", "EOMONTH", "DATE", "DATEVALUE", "TIMEVALUE",
                       "TODAY", "NOW", "CALENDAR", "CALENDARAUTO")
_DAX_BOOL_FUNCS    = ("ISBLANK", "ISERROR", "ISNUMBER", "ISTEXT", "ISLOGICAL",
                      "HASONEVALUE", "HASONEFILTER", "CONTAINS", "ISFILTERED")


def _infer_calc_column_data_type(expr: str) -> str:
    """Return 'integer'|'decimal'|'string'|'datetime'|'boolean'|'unknown' from
    the outermost DAX function of *expr*. Conservative — only returns a known
    type when the head function is unambiguous.

    Walks past leading whitespace/newlines, then matches the first identifier
    that's followed by '('. SWITCH/IF return whatever the branches return, so
    they're explicitly NOT classified here (we leave the existing type).
    """
    if not expr:
        return "unknown"
    s = expr.lstrip()
    m = _re.match(r"([A-Z_][A-Z0-9_\.]*)\s*\(", s, _re.IGNORECASE)
    if not m:
        # Bare column ref / literal — leave it.
        return "unknown"
    head = m.group(1).upper()
    # SWITCH/IF can't be classified from the head — branches decide.
    if head in ("SWITCH", "IF", "IFERROR", "VAR"):
        return "unknown"
    if head in _DAX_INT_FUNCS:     return "integer"
    if head in _DAX_DECIMAL_FUNCS: return "decimal"
    if head in _DAX_STRING_FUNCS:  return "string"
    if head in _DAX_DATETIME_FUNCS: return "datetime"
    if head in _DAX_BOOL_FUNCS:    return "boolean"
    return "unknown"


def _backfill_calc_column_expressions_and_types(result: dict, metadata_folder) -> None:
    """For every row in dax_columns.json whose TableName is a real (non
    auto-date) table:

      - Find the matching column in tables[<TableName>].columns[] and set
        `expression` to the DAX body. Source-of-truth: dax_columns.json. If
        the LLM emitted a wrong/empty expression, overwrite it.
      - Refine the column's data_type from the DAX root function when the
        current type is 'unknown' or 'string' (pbixray's default). Never
        downgrades a more specific type (decimal -> decimal stays).

    Auto-date table calc columns (LocalDateTable_*/DateTableTemplate_*) are
    skipped — FE's writer hardcodes their canonical 7-column shape, and
    duplicating their YEAR([Date])/MONTH([Date])/... expressions in tables[]
    serves no consumer.

    Idempotent."""
    from pathlib import Path
    cols_path = Path(metadata_folder) / "dax_columns.json"
    if not cols_path.exists():
        return
    try:
        with open(cols_path, encoding="utf-8") as f:
            dax_cols = json.load(f)
    except Exception:
        return

    tables = result.get("tables", [])
    tables_by_name = {t.get("name", ""): t for t in tables}

    for dc in dax_cols:
        tbl_name = dc.get("TableName") or ""
        col_name = dc.get("ColumnName") or dc.get("Name") or ""
        expr     = (dc.get("Expression") or "").strip()
        if not tbl_name or not col_name or not expr:
            continue
        # Auto-date calc columns are FE-templated; don't pollute the JSON.
        if tbl_name.startswith(_INTERNAL_TABLE_PREFIXES):
            continue
        tbl = tables_by_name.get(tbl_name)
        if not tbl:
            continue
        col = next((c for c in tbl.get("columns", []) if c.get("name") == col_name), None)
        if not col:
            continue
        # Source of truth — always write the verbatim expression.
        col["expression"] = expr
        # Type refinement: only override the default 'unknown'/'string' that
        # pbixray emits for DAX columns it can't type. Keep specific types.
        inferred = _infer_calc_column_data_type(expr)
        if inferred != "unknown" and col.get("data_type") in (None, "", "unknown", "string"):
            col["data_type"] = inferred


def _strip_calc_column_duplicates_from_calculations(result: dict, metadata_folder) -> None:
    """Calc columns belong on tables[].columns[].expression, NOT in
    calculations[] (which is reserved for measures). Today the dax_calculations
    LLM agent emits a calculations[] entry for every dax_columns row, which:
      - pollutes the calculations list with non-measure entries,
      - collides with column names of the same table (auto-date entries
        especially), and
      - has no consumer downstream.

    This pass removes those duplicates. A calculations[] entry is treated as a
    calc-column duplicate if it matches any (TableName, ColumnName) pair in
    dax_columns.json — comparing both by exact name AND by 'TableName.ColumnName'
    composite (the LLM uses both shapes).

    Idempotent."""
    from pathlib import Path
    cols_path = Path(metadata_folder) / "dax_columns.json"
    if not cols_path.exists():
        return
    try:
        with open(cols_path, encoding="utf-8") as f:
            dax_cols = json.load(f)
    except Exception:
        return

    dup_names: set = set()
    for dc in dax_cols:
        tbl_name = (dc.get("TableName") or "").strip()
        col_name = (dc.get("ColumnName") or dc.get("Name") or "").strip()
        if not col_name:
            continue
        dup_names.add(col_name)
        if tbl_name:
            dup_names.add(f"{tbl_name}.{col_name}")

    if not dup_names:
        return

    calcs = result.get("calculations") or []
    result["calculations"] = [c for c in calcs if (c.get("name") or "") not in dup_names]


def _backfill_measure_home_tables(result: dict, metadata_folder) -> None:
    """dax_measures.json's TableName is the measure's home table (where it
    lives in the TMDL). The dax_calculations LLM doesn't carry this field on
    calculations[], so FE has to re-infer it from depends_on_columns — which
    gets it wrong when a measure lives on one table but reads from another
    (e.g. TotalRevenue lives on CustomerCountPerDay but reads Revenue Daywise).

    This pass writes the verbatim TableName from dax_measures.json onto the
    matching calculations[] entry's `home_table`. Match key: measure name.

    Idempotent. Never overwrites a value already set (so a manual upstream fix
    is respected)."""
    from pathlib import Path
    src_path = Path(metadata_folder) / "dax_measures.json"
    if not src_path.exists():
        return
    try:
        with open(src_path, encoding="utf-8") as f:
            src = json.load(f)
    except Exception:
        return

    home_by_name = {(m.get("Name") or ""): (m.get("TableName") or "") for m in src}
    for calc in result.get("calculations") or []:
        if calc.get("home_table"):
            continue
        name = calc.get("name") or ""
        home = home_by_name.get(name)
        if home:
            calc["home_table"] = home


# ---------------------------------------------------------------------------
# Field Parameter detection.
#
# Power BI Field Parameter tables are calc tables whose DAX body is a brace-
# enclosed list of (label, NAMEOF('Table'[Column or Measure]), index) tuples.
# Their canonical TMDL shape is fixed:
#   column 1: '<TableName>'              sourceColumn: [Value1]  sortBy: '<T> Order'
#   column 2: '<TableName> Fields'       sourceColumn: [Value2]  hidden, ParameterMetadata
#   column 3: '<TableName> Order'        sourceColumn: [Value3]  hidden
# The LLM doesn't know this convention, so we detect and rewrite deterministically.
# ---------------------------------------------------------------------------
_FIELD_PARAM_DAX_RE = _re.compile(
    r"^\s*\{\s*\(\s*\"[^\"]+\"\s*,\s*NAMEOF\s*\(",
    _re.IGNORECASE,
)


def _is_field_parameter_dax(expr: str) -> bool:
    """True if the DAX body matches the NAMEOF-tuple pattern Power BI emits
    for Field Parameter tables. Conservative — leading whitespace allowed,
    but the inner shape is strict."""
    if not expr:
        return False
    return bool(_FIELD_PARAM_DAX_RE.match(expr))


def _rewrite_field_parameter_columns(tbl: dict) -> None:
    """Replace whatever columns the LLM guessed with the canonical 3-column
    shape Power BI emits for Field Parameters. The table itself stays
    table_type='calculated' — the only difference vs a SUMMARIZE calc table
    is column names + the ParameterMetadata annotation on column 2."""
    name = tbl.get("name") or ""
    if not name:
        return
    label_col = name
    fields_col = f"{name} Fields"
    order_col = f"{name} Order"

    def _col(col_name, dt, hidden, role, parameter_metadata=None):
        c = {
            "name": col_name,
            "data_type": dt,
            "nullable": False,
            "hidden": hidden,
            "semantic_role": role,
            "used_in_relationships": False,
            "used_in_filters": not hidden,
            "used_in_groupby": not hidden,
            "used_in_calculations": False,
            "distinct_count_high": False,
            "description": ("Field Parameter label" if not hidden and col_name == label_col
                            else "Field Parameter NAMEOF reference" if col_name == fields_col
                            else "Field Parameter sort order"),
        }
        if col_name == label_col:
            c["sort_by_column"] = order_col
        if col_name == fields_col:
            c["sort_by_column"] = order_col
        if parameter_metadata is not None:
            c["parameter_metadata"] = parameter_metadata
        if col_name == order_col:
            c["format_string"] = "0"
        return c

    tbl["columns"] = [
        _col(label_col, "string", False, "dimension"),
        _col(fields_col, "string", True, "dimension",
             parameter_metadata={"version": 3, "kind": 2}),
        _col(order_col, "integer", True, "dimension"),
    ]


def _detect_and_rewrite_field_parameter_tables(result: dict) -> None:
    """For every calculated table whose DAX body matches the NAMEOF-tuple
    pattern, rewrite columns[] to the canonical Field Parameter shape.

    Idempotent: detects the pattern via the DAX body (not via column names),
    so re-running on already-rewritten output is a no-op for content."""
    for tbl in result.get("tables", []):
        if tbl.get("table_type") != "calculated":
            continue
        if tbl.get("name", "").startswith(_INTERNAL_TABLE_PREFIXES):
            continue
        # Pull the DAX body from ingestion.steps[0].native_expressions.dax
        steps = (tbl.get("ingestion") or {}).get("steps") or []
        dax_body = ""
        for step in steps:
            ne = step.get("native_expressions") or {}
            if ne.get("dax"):
                dax_body = ne["dax"]
                break
        if not _is_field_parameter_dax(dax_body):
            continue
        _rewrite_field_parameter_columns(tbl)


# ---------------------------------------------------------------------------
# Relationship dedup + sanity-override.
# ---------------------------------------------------------------------------

def _relationship_quality_score(rel: dict) -> tuple:
    """Higher is better. Used to pick which row survives when two relationships
    share the same endpoint tuple.

    Preferences (in priority order):
      1. auto_date_relationship type wins over any other type when one side is
         a LocalDateTable — that's the only correct shape for auto-date links.
      2. M:1 single direction over anything bidirectional when one side is
         clearly the 'one' side. (one_to_one is suspect for auto-date.)
      3. Active over inactive.
      4. Has a non-empty `id` over empty.
    """
    rt = rel.get("relationship_type") or ""
    card = (rel.get("cardinality") or "").lower()
    fdir = (rel.get("filter_direction") or "").lower()
    active = bool(rel.get("active"))
    has_id = bool(rel.get("id"))
    right_is_ldt = (rel.get("right_table_id") or "").startswith("tbl_local_date_table")
    left_is_ldt  = (rel.get("left_table_id")  or "").startswith("tbl_local_date_table")
    one_side_is_ldt = right_is_ldt or left_is_ldt

    autodate_score = 1 if (rt == "auto_date_relationship" and one_side_is_ldt) else 0
    # Prefer M:1 single over 1:1 bidi when auto-date.
    shape_score = 0
    if one_side_is_ldt:
        if card in ("many_to_one", "one_to_many") and fdir == "single":
            shape_score = 2
        elif card == "one_to_one" and fdir == "bidirectional":
            shape_score = -1
    return (autodate_score, shape_score, int(active), int(has_id))


def _dedupe_and_relink_relationships(result: dict) -> None:
    """Collapse duplicate relationship rows whose endpoint tuples match.

    For each duplicate group, pick the row with the highest quality score
    (auto-date relationships prefer M:1 single, etc.). Keep that row, drop the
    others. Then re-walk variations[] on every column: if their
    `relationship_id` referenced a dropped row, repoint to the survivor.

    Idempotent."""
    rels = result.get("relationships") or []
    if not rels:
        return

    # Group by canonical endpoint tuple. Treat auto-date relationships as
    # directed (LDT side fixed), so direction matters.
    by_endpoint: dict = {}
    for rel in rels:
        key = (rel.get("left_table_id"), rel.get("left_column"),
               rel.get("right_table_id"), rel.get("right_column"))
        by_endpoint.setdefault(key, []).append(rel)

    # Pick the best row per group; build id remap survivor table.
    id_remap: dict = {}
    survivors: list = []
    for group in by_endpoint.values():
        if len(group) == 1:
            survivors.append(group[0])
            continue
        ranked = sorted(group, key=_relationship_quality_score, reverse=True)
        keep = ranked[0]
        for dropped in ranked[1:]:
            if dropped.get("id") and keep.get("id"):
                id_remap[dropped["id"]] = keep["id"]
        survivors.append(keep)

    if len(survivors) == len(rels) and not id_remap:
        return

    # Preserve original order while removing dropped rows.
    survivor_ids = {id(r) for r in survivors}
    result["relationships"] = [r for r in rels if id(r) in survivor_ids]

    if id_remap:
        for tbl in result.get("tables", []):
            for col in tbl.get("columns", []):
                for var in col.get("variations") or []:
                    rid = var.get("relationship_id")
                    if rid in id_remap:
                        var["relationship_id"] = id_remap[rid]


def _sanity_override_cardinality(result: dict) -> None:
    """pbixray sometimes reports a relationship as 1:1 when both sides happen
    to have unique values in the imported data — semantically it's still a
    PK→FK (1:M) relationship. The LLM preserves pbixray's literal label.

    Override: if one side's column has semantic_role 'primary_key' (the PK
    side, naturally 'one'), and the other side is on a fact/non-dimension
    table, flip the cardinality to many_to_one (left→right depending on which
    side is the PK). Only acts on `one_to_one` rows — never downgrades a
    cleanly-typed many_to_one or one_to_many.

    Conservative: requires the PK column to be findable in tables[]. When
    that lookup fails, leaves the row alone. Idempotent."""
    tables = result.get("tables", []) or []
    by_name: dict = {}  # tbl_<slug>  ->  table dict
    for t in tables:
        by_name[_slug_table(t.get("name") or "")] = t

    def col_role(tbl_slug, col_name):
        t = by_name.get(tbl_slug)
        if not t:
            return None
        c = next((c for c in t.get("columns", []) if c.get("name") == col_name), None)
        return c.get("semantic_role") if c else None

    def is_dim(tbl_slug):
        t = by_name.get(tbl_slug)
        return bool(t and t.get("table_type") == "dimension")

    def is_fact(tbl_slug):
        t = by_name.get(tbl_slug)
        return bool(t and t.get("table_type") == "fact")

    for rel in result.get("relationships") or []:
        card = (rel.get("cardinality") or "").lower()
        if card != "one_to_one":
            continue
        L_tbl, L_col = rel.get("left_table_id"), rel.get("left_column")
        R_tbl, R_col = rel.get("right_table_id"), rel.get("right_column")
        L_role = col_role(L_tbl, L_col)
        R_role = col_role(R_tbl, R_col)
        # Pick the PK side. If both/neither are PKs, leave it.
        L_is_pk = L_role == "primary_key" or is_dim(L_tbl)
        R_is_pk = R_role == "primary_key" or is_dim(R_tbl)
        if L_is_pk and not R_is_pk:
            # left is PK 'one' side, right is many side
            rel["cardinality"] = "one_to_many"
            rel["note"] = (rel.get("note") or "") + " | cardinality refined from 1:1 to 1:M (left side is PK)"
        elif R_is_pk and not L_is_pk:
            rel["cardinality"] = "many_to_one"
            rel["note"] = (rel.get("note") or "") + " | cardinality refined from 1:1 to M:1 (right side is PK)"


def _drop_misclassified_autodate_stubs(result: dict, metadata_folder) -> None:
    """The relationships agent's STEP 2 algorithm resolves `ToTableName: null`
    rows by matching FromTableName to the auto-date map. But if pbixray's row
    has FromColumnName populated and that column is NOT the LocalDateTable's
    base column, the null-right-side row is a different relationship that
    happens to leave its right side null (e.g. dim_date.date → Revenue Daywise.date,
    where dim_date IS an auto-date base table via column MM, not 'date').

    Today the LLM may wrongly emit such a row as an auto-date stub pointing at
    a LocalDateTable for a DIFFERENT column. This pass detects and drops those
    misclassifications: an `auto_date_relationship` row whose left_column does
    not match any LocalDateTable's base column for that left_table is invalid
    and gets removed.

    The intentionally lost-info case (genuine `dim_date.date → null` stub for
    a relationship into another non-auto-date table) is best left as a null
    endpoint by the LLM — this pass only drops malformed auto-date rows, it
    doesn't synthesize the missing real one.

    Idempotent."""
    from pathlib import Path
    dax_path = Path(metadata_folder) / "dax_tables.json"
    if not dax_path.exists():
        return
    try:
        with open(dax_path, encoding="utf-8") as f:
            dax_tables = json.load(f)
    except Exception:
        return

    # Build base_table -> {base_column, ldt_slug} for every LocalDateTable.
    autodate_base: dict = {}  # (base_table_slug, base_column) -> ldt_slug
    for dax_tbl in dax_tables:
        name = dax_tbl.get("TableName", "")
        if not name.startswith("LocalDateTable_"):
            continue
        expr = dax_tbl.get("Expression", "") or ""
        m = _BASE_COLUMN_PATTERN.search(expr)
        if not m:
            continue
        base_tbl, base_col = m.group(1), m.group(2)
        autodate_base[(_slug_table(base_tbl), base_col)] = _slug_table(name)

    if not autodate_base:
        return

    rels = result.get("relationships") or []
    keep = []
    for rel in rels:
        if rel.get("relationship_type") != "auto_date_relationship":
            keep.append(rel)
            continue
        L_tbl = rel.get("left_table_id")
        L_col = rel.get("left_column")
        R_tbl = rel.get("right_table_id")
        expected_ldt = autodate_base.get((L_tbl, L_col))
        if expected_ldt is None or expected_ldt != R_tbl:
            # Misclassified: this row claims to be an auto-date link but the
            # left column isn't the base column for the LDT on the right.
            continue
        keep.append(rel)
    if len(keep) != len(rels):
        result["relationships"] = keep


def _recover_null_right_relationships(result: dict) -> None:
    """Recover the missing right-endpoint on relationships that pbixray
    dropped but which AREN'T auto-date stubs.

    pbixray's relationships.json sometimes emits rows with ToTableName=null
    even for genuine user-defined relationships (not just auto-date stubs).
    The `relationships` agent correctly preserves these as null-right rows.
    The auto-date safety net handles the auto-date subset. This pass picks
    up the remainder using only signals already present in `result`:

      Filter 1: candidate column must have the same NAME as left_column.
      Filter 2: skip auto-date tables, the from-table itself, and columns
                whose data_type is incompatible with the left column.
      Filter 3: skip candidates already wired to (left_table, left_column)
                via any existing relationship (in either direction).
      Filter 4: when >1 candidate remains and cardinality is one_to_one,
                prefer candidates with distinct_count_high or
                semantic_role 'primary_key'.

    Wire ONLY when exactly one candidate survives the four filters. When
    zero or multiple candidates match, leave the row as-is — never guess.
    Idempotent: re-running on already-resolved rows is a no-op (Filter 3
    will see the now-wired relationship and exclude every candidate)."""
    rels = result.get("relationships") or []
    tables = result.get("tables") or []
    if not rels or not tables:
        return

    tables_by_slug = {_slug_table(t.get("name") or ""): t for t in tables}

    # Build bidirectional already-wired set: (table_slug, col) -> {other-side slugs}.
    # Used by Filter 3.
    wired: dict = {}
    for rel in rels:
        L_tbl = rel.get("left_table_id")
        L_col = rel.get("left_column")
        R_tbl = rel.get("right_table_id")
        R_col = rel.get("right_column")
        if L_tbl and L_col and R_tbl:
            wired.setdefault((L_tbl, L_col), set()).add(R_tbl)
        if R_tbl and R_col and L_tbl:
            wired.setdefault((R_tbl, R_col), set()).add(L_tbl)

    def _col_on(tbl_slug, col_name):
        t = tables_by_slug.get(tbl_slug)
        if not t:
            return None
        return next((c for c in t.get("columns", []) if c.get("name") == col_name), None)

    for rel in rels:
        if rel.get("right_table_id"):
            continue
        L_tbl_slug = rel.get("left_table_id")
        L_col = rel.get("left_column")
        if not L_tbl_slug or not L_col:
            continue
        L_col_obj = _col_on(L_tbl_slug, L_col)
        L_col_type = (L_col_obj or {}).get("data_type") if L_col_obj else None

        # Filter 1+2: name match, exclude auto-date and from-table, type match.
        candidates = []
        for t in tables:
            tname = t.get("name") or ""
            if tname.startswith(_INTERNAL_TABLE_PREFIXES):
                continue
            t_slug = _slug_table(tname)
            if t_slug == L_tbl_slug:
                continue
            for c in t.get("columns", []):
                if c.get("name") != L_col:
                    continue
                c_type = c.get("data_type")
                if L_col_type and c_type and L_col_type != c_type:
                    continue
                candidates.append((t_slug, c))

        # Filter 3: already-wired exclusion.
        excluded = wired.get((L_tbl_slug, L_col), set())
        candidates = [c for c in candidates if c[0] not in excluded]

        # Filter 4: cardinality preference for one_to_one.
        if len(candidates) > 1:
            card = (rel.get("cardinality") or "").lower()
            if card == "one_to_one":
                pk_only = [c for c in candidates
                           if c[1].get("distinct_count_high")
                           or c[1].get("semantic_role") == "primary_key"]
                if len(pk_only) == 1:
                    candidates = pk_only

        if len(candidates) != 1:
            continue

        # Wire it up.
        R_slug, R_col_obj = candidates[0]
        rel["right_table_id"] = R_slug
        rel["right_column"] = R_col_obj.get("name")

        # Reclassify away from the null-orphan fallback type.
        if rel.get("relationship_type") in (None, "", "date_relationship"):
            rel["relationship_type"] = "dimension_lookup"

        # Append a recovery note so the provenance of the wiring is visible
        # in the JSON.
        prev_note = rel.get("note") or ""
        marker = "right-side recovered by deterministic name+exclusion match"
        if marker not in prev_note:
            rel["note"] = (prev_note + " | " + marker).strip(" |")

        # If the id encoded "_null" (the agent's fallback), regenerate it
        # using the bare slugs on both sides.
        rid = rel.get("id") or ""
        if rid.endswith("_null") or "_null_" in rid:
            L_bare = L_tbl_slug[4:] if L_tbl_slug.startswith("tbl_") else L_tbl_slug
            R_bare = R_slug[4:] if R_slug.startswith("tbl_") else R_slug
            rel["id"] = f"rel_{L_bare}_{R_bare}"

        # Update the wired set so subsequent iterations see this new wiring
        # (matters when multiple null-right rows could each resolve).
        wired.setdefault((L_tbl_slug, L_col), set()).add(R_slug)
        wired.setdefault((R_slug, R_col_obj.get("name") or ""), set()).add(L_tbl_slug)


def _apply_autodate_hidden_flags(result: dict) -> None:
    """Power BI auto-date tables are isHidden + showAsVariationsOnly, with
    every column also isHidden. RE wasn't carrying this in the common-model
    JSON, so the downstream consumer had no way to know. This pass sets
    `hidden: True` on every LocalDateTable_/DateTableTemplate_ table and on
    every column inside them.

    Idempotent."""
    for tbl in result.get("tables", []):
        if not (tbl.get("name") or "").startswith(_INTERNAL_TABLE_PREFIXES):
            continue
        tbl["hidden"] = True
        for c in tbl.get("columns", []) or []:
            c["hidden"] = True


def _fill_autodate_hierarchies_and_variations(result: dict, metadata_folder) -> None:
    """Deterministic post-processing pass that fills three pieces of Power BI
    auto-date metadata the LLM consistently misses, even when the prompt
    instructs it:

      1. hierarchies[] on each LocalDateTable_*/DateTableTemplate_* table — the
         standard Date Hierarchy with Year/Quarter/Month/Day levels. Power BI
         always materializes the same shape, so this is a fixed template.
      2. variations[] on each base date column the LocalDateTable_*s are
         linked to (parsed from each LocalDateTable's Calendar(...) DAX).
      3. Relabels ingestion.steps[].native_expressions.powerquery to .dax on
         auto-date tables — their body is pure DAX, not M.

    Idempotent and additive: never overwrites a non-empty value.
    """
    from pathlib import Path
    dax_path = Path(metadata_folder) / "dax_tables.json"
    if not dax_path.exists():
        return
    try:
        with open(dax_path, encoding="utf-8") as f:
            dax_tables = json.load(f)
    except Exception:
        return

    tables = result.get("tables", [])
    rels = result.get("relationships", [])
    tables_by_name = {t.get("name", ""): t for t in tables}

    # --- Pass 0: reconcile tables[] against dax_tables.json -------------------
    # The LLM has been dropping user calc tables (CustomerCountPerDay,
    # Revenue Daywise) and emitting auto-date tables with empty DAX bodies.
    # Synthesize anything missing and backfill empty DAX from the extractor's
    # ground-truth dax_tables.json.
    _ensure_calculated_tables_present(tables, tables_by_name, dax_tables)
    # Rebuild lookup since Pass 0 may have appended new tables.
    tables_by_name = {t.get("name", ""): t for t in tables}

    # --- Pass 1: hierarchy + DAX-key relabel on every auto-date table ----------
    for tbl in tables:
        if not tbl.get("name", "").startswith(_INTERNAL_TABLE_PREFIXES):
            continue
        if not tbl.get("hierarchies"):
            tbl["hierarchies"] = [_build_autodate_hierarchy()]
        for step in tbl.get("ingestion", {}).get("steps", []) or []:
            ne = step.get("native_expressions") or {}
            if "dax" not in ne and "powerquery" in ne:
                ne["dax"] = ne.pop("powerquery")
                step["native_expressions"] = ne

    # --- Pass 2: variations on base columns -----------------------------------
    for dax_tbl in dax_tables:
        ldt_name = dax_tbl.get("TableName", "")
        if not ldt_name.startswith("LocalDateTable_"):
            continue
        expr = dax_tbl.get("Expression", "") or ""
        match = _BASE_COLUMN_PATTERN.search(expr)
        if not match:
            continue
        base_table_name, base_column_name = match.group(1), match.group(2)
        base_tbl = tables_by_name.get(base_table_name)
        if not base_tbl:
            continue
        base_col = next(
            (c for c in base_tbl.get("columns", []) if c.get("name") == base_column_name),
            None,
        )
        if not base_col:
            continue
        # Look up the matching auto-date relationship for the relationship_id.
        # The relationships agent is responsible for emitting these rows fully
        # wired (right_table_id resolved to the LocalDateTable). If a clean
        # match isn't found, leave rel_id as None — the variation still
        # resolves visuals via default_hierarchy.
        ldt_slug = _slug_table(ldt_name)
        base_slug = _slug_table(base_table_name)
        rel_id = next(
            (r.get("id") for r in rels
             if r.get("left_table_id") == base_slug
             and r.get("left_column") == base_column_name
             and r.get("right_table_id") == ldt_slug),
            None,
        )
        variation = {
            "name": "Variation",
            "is_default": True,
            "relationship_id": rel_id,
            "default_hierarchy": f"{ldt_name}.Date Hierarchy",
        }
        existing = base_col.get("variations") or []
        # Idempotent: skip if a variation pointing at the same hierarchy is already there.
        if any(v.get("default_hierarchy") == variation["default_hierarchy"] for v in existing):
            continue
        existing.append(variation)
        base_col["variations"] = existing


def _clean_table(tbl: dict) -> dict:
    """Filter a single table dict to schema keys, cleaning columns and ingestion."""
    clean_tbl = {k: tbl[k] for k in _TABLE_KEYS if k in tbl}
    if "columns" in clean_tbl:
        clean_tbl["columns"] = [
            {k: col[k] for k in _COLUMN_KEYS if k in col}
            for col in clean_tbl["columns"]
        ]
    if "ingestion" in clean_tbl:
        clean_tbl["ingestion"] = {
            "steps": [
                {k: step[k] for k in _STEP_KEYS if k in step}
                for step in clean_tbl["ingestion"].get("steps", [])
            ]
        }
    return clean_tbl


def _clean_visual(vis: dict) -> dict:
    """Filter a single visual dict to schema keys, cleaning position, fields, and filters."""
    clean_vis = {k: vis[k] for k in _VISUAL_KEYS if k in vis}
    if "position" in clean_vis and isinstance(clean_vis["position"], dict):
        clean_vis["position"] = {
            k: clean_vis["position"][k]
            for k in _POSITION_KEYS if k in clean_vis["position"]
        }
    if "fields" in clean_vis:
        clean_vis["fields"] = [
            {k: f[k] for k in _FIELD_KEYS if k in f}
            for f in clean_vis["fields"]
        ]
    # if "filters" in clean_vis:  # TODO: re-enable when UI supports visual-level filters
    #     clean_vis["filters"] = [
    #         {k: flt[k] for k in _FILTER_KEYS if k in flt}
    #         for flt in clean_vis["filters"]
    #     ]
    return clean_vis


def _enforce_common_model_schema(result: dict) -> dict:
    """Strip every key that is not part of the common_model.json schema."""
    enforced = {k: result[k] for k in _TOP_KEYS if k in result}

    enforced["data_sources"] = [
        {k: src[k] for k in _DATA_SOURCE_KEYS if k in src}
        for src in result.get("data_sources", [])
    ]

    enforced["tables"] = [
        _clean_table(tbl)
        for tbl in result.get("tables", [])
    ]

    enforced["relationships"] = [
        {k: rel[k] for k in _RELATIONSHIP_KEYS if k in rel}
        for rel in result.get("relationships", [])
    ]

    enforced["calculations"] = [
        {k: calc[k] for k in _CALCULATION_KEYS if k in calc}
        for calc in result.get("calculations", [])
    ]

    pages = []
    for page in result.get("report_pages", []):
        clean_page = {k: page[k] for k in _PAGE_KEYS if k in page}
        # if "filters" in clean_page:  # TODO: re-enable when UI supports page-level filters
        #     clean_page["filters"] = [
        #         {k: flt[k] for k in _FILTER_KEYS if k in flt}
        #         for flt in clean_page["filters"]
        #     ]
        if "visuals" in clean_page:
            clean_page["visuals"] = [_clean_visual(vis) for vis in clean_page["visuals"]]
        pages.append(clean_page)
    enforced["report_pages"] = pages

    # enforced["report_filters"] = [  # TODO: re-enable when UI supports report-level filters
    #     {k: flt[k] for k in _FILTER_KEYS if k in flt}
    #     for flt in result.get("report_filters", [])
    # ]

    return enforced


@dataclass
class FlowRequest:
    content: str
    extraction_type: str


@dataclass
class Request:
    content: str


@dataclass
class TaskResponse:
    content: json


@dataclass
class ExecutiveSummaryResponse:
    content: str


def _make_collect_result(q: asyncio.Queue) -> object:
    """Return a closure that drains TaskResponse messages into *q*."""
    async def collect_result(
        _agent: ClosureContext, message: TaskResponse, ctx: MessageContext
    ) -> None:
        await q.put(message)
    return collect_result


def _make_save_executive_summary(q: asyncio.Queue) -> object:
    """Return a closure that drains ExecutiveSummaryResponse messages into *q*."""
    async def save_executive_summary(
        _agent: ClosureContext, message: ExecutiveSummaryResponse, ctx: MessageContext
    ) -> None:
        await q.put(message)
    return save_executive_summary


# Single Agent for all extractions
@type_subscription(topic_type="PowerBIMetadataExtractor")
class PowerBIMetadataExtractorAgent(RoutedAgent):
    def __init__(self) -> None:
        super().__init__("PowerBI Metadata Extractor Agent")

    @message_handler
    async def handle_message(self, message: FlowRequest, ctx: MessageContext) -> None:
        print(
            f"\n{'='*60}\nAgent {self.id} processing {message.extraction_type}...\n"
        )
        if ctx.topic_id is None:
            raise ValueError("Topic ID is required for broadcasting.")
        try:
            agent_prompt = EXTRACTION_PROMPTS.get(message.extraction_type)
            if not agent_prompt:
                raise ValueError(f"Unknown extraction type: {message.extraction_type}")

            messages = [
                SystemMessage(content=agent_prompt),
                UserMessage(content=message.content, source="user"),
            ]

            print("---------------------------------", agent_prompt)
            print("---------------------------------", message.content)

            response = await azure_client.create(messages=messages)
            metadata_json = response.content

            print(
                f"\n--- Extracted {message.extraction_type} Metadata ---\n{metadata_json}\n{'='*60}"
            )

            if isinstance(metadata_json, str):
                metadata_json = parser.parse(metadata_json)

            await self.publish_message(
                message=TaskResponse(content=json.dumps(metadata_json)),
                topic_id=DefaultTopicId(),
            )
        except Exception as e:
            print(f"Error in {self.id} for {message.extraction_type}: {e}")
            raise ValueError(f"Failed to process {message.extraction_type} extraction.")


executive_summary_topic_type = "ExecutiveSummaryAgent"


@type_subscription(topic_type=executive_summary_topic_type)
class ExecutiveSummaryAgent(RoutedAgent):
    def __init__(self) -> None:
        super().__init__("A Executive Summary agent.")
        self._system_messages = [
            SystemMessage(
                content="""
                Role: Data Executive Summary Specialist
                From the extraction response generated by analyzing a Power BI report, please generate an executive summary. 
                Emphasize how the report supports decision-making, what insights it reveals, and how it contributes to operational or strategic goals. Maintain a professional tone suitable for executive stakeholders.
                
                You are a business analyst skilled in interpreting BI tool configurations. Based on the provided data model, visualizations, DAX measures, and transformations from a Power BI report structure, generate an executive summary suitable for inclusion in a Business Requirements Document (BRD). 
                
                Avoid technical implementation details such as DAX syntax, M code, specific formatting parameters, or tool-specific terminology. Focus only on the business perspective: what insights are being tracked, which KPIs are being monitored, what business questions are being answered, and how the report supports decision-making.
                
                Keep it factual, organized, and insight-oriented.
                This summary captures the high-level objectives and outcomes of the data preparation process, underscoring its role in driving actionable insights and supporting informed decision-making.                    
            """
            )
        ]

    @message_handler
    async def handle_message(self, message: Request, ctx: MessageContext) -> None:
        print(
            f"\n{'='*50}\nProcessor {self.id} handling component: Creating Executive Summary"
        )
        if ctx.topic_id is None:
            raise ValueError("Topic ID is required for broadcasting.")
        try:
            flow_data = message.content
            agent_prompt = next(
                (msg.content for msg in self._system_messages), None
            )
            if not agent_prompt:
                raise ValueError("System prompt is missing for agent processing.")
            messages = [
                SystemMessage(content=agent_prompt),
                UserMessage(content=flow_data, source="user"),
            ]
            response = await azure_client.create(messages=messages)

            print(response.content)
            await self.publish_message(
                ExecutiveSummaryResponse(content=response.content),
                topic_id=DefaultTopicId(),
            )
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON format in the Power BI extraction data.")


def _build_file_groups(metadata_folder) -> dict:
    """Build the file_groups dict from the metadata folder path.

    Each section has ONE focused responsibility and reads only the files it
    needs — keeping prompts short and the LLM single-purpose per call.
    """
    return {
        # Group 1: Power Query + M Parameters → DataSource + TransformationStep
        "power_query_and_params": {
            "extraction_type": "power_query",
            "files": [
                metadata_folder / "power_query.json",
                metadata_folder / "m_parameters.json",
            ],
        },
        # Group 2: DAX Measures + Schema → CalculationMetadata (measures only).
        # Calculated tables (dax_tables) are handled by the dedicated
        # 'calculated_tables' section below — keep them out of here to avoid
        # the LLM confusing measure semantic_type with table emission.
        "dax_calculations": {
            "extraction_type": "dax_calculations",
            "files": [
                metadata_folder / "dax_measures.json",
                metadata_folder / "dax_columns.json",
                metadata_folder / "schema.json",
                metadata_folder / "bim_model.json",
            ],
        },
        # Group 3: Tables + Schema → TableMetadata for imported / Power Query
        # tables only. DAX-calculated tables are handled by the dedicated
        # 'calculated_tables' section.
        "tables_and_schema": {
            "extraction_type": "tables_and_schema",
            "files": [
                metadata_folder / "tables_list.json",
                metadata_folder / "schema.json",
                metadata_folder / "bim_model.json",
            ],
        },
        # Group 4 (NEW): Calculated tables — dedicated section so the LLM has
        # a single focused job: emit tables[] entries for every dax_tables.json
        # entry (user calc tables + auto-date LocalDateTable_*/DateTableTemplate_*)
        # with their full DAX body, columns, and hierarchies. Keeps this work
        # out of the tables_and_schema / dax_calculations agents.
        "calculated_tables": {
            "extraction_type": "calculated_tables",
            "files": [
                metadata_folder / "dax_tables.json",
                metadata_folder / "dax_columns.json",
            ],
        },
        # Group 5: Relationships. dax_tables.json is bundled here so the agent
        # can resolve auto-date LocalDateTable endpoints (pbixray reports them
        # with null ToTableName/ToColumnName) by parsing each LocalDateTable's
        # Calendar(...) expression for its base 'table'[column] reference.
        "relationships": {
            "extraction_type": "relationships",
            "files": [
                metadata_folder / "relationships.json",
                metadata_folder / "dax_tables.json",
            ],
        },
        "rls": {
            "extraction_type": "rls",
            "files": [metadata_folder / "rls.json"],
        },
        "metadata": {
            "extraction_type": "metadata",
            "files": [metadata_folder / "metadata.json"],
        },
        "layout_mapping": {
            "extraction_type": "layout_mapping",
            "files": [metadata_folder / "layout_datamodel_mapping.json"],
        },
    }


# Module-level mapping: JSON key -> aggregated_results key (for list-extend fields)
_RESULT_KEY_MAP = {
    "data_sources": "data_sources",
    "relationships": "relationships",
    "calculations": "calculations",
}


async def _read_file_group(files: list) -> tuple:
    """
    Read and merge all files in a group.
    Returns (merged_content, files_found, files_missing).
    """
    merged_content = {}
    files_found = []
    files_missing = []

    for file_path in files:
        if not file_path.exists():
            files_missing.append(str(file_path.name))
            print(f"  Warning: {file_path.name} not found, skipping this file")
            continue
        try:
            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                raw = await f.read()
                merged_content[file_path.stem] = json.loads(raw)
                files_found.append(str(file_path.name))
        except Exception as e:
            print(f"  Error reading {file_path.name}: {e}")
            files_missing.append(str(file_path.name))

    return merged_content, files_found, files_missing


async def _process_file_groups(
    file_groups: dict,
    runtime,
    topic_name: str = "PowerBIMetadataExtractor",
    source: str = "default",
) -> None:
    """Merge and publish each file group to the runtime."""
    for group_name, group_info in file_groups.items():
        extraction_type = group_info["extraction_type"]
        merged_content, files_found, files_missing = await _read_file_group(group_info["files"])

        if not merged_content:
            print(f"Skipping {group_name}: no files found")
            continue

        print(f"\nProcessing {group_name} ({extraction_type})")
        print(f"  Files found: {', '.join(files_found)}")
        if files_missing:
            print(f"  Files missing: {', '.join(files_missing)}")

        try:
            await runtime.publish_message(
                FlowRequest(content=json.dumps(merged_content, indent=2), extraction_type=extraction_type),
                topic_id=TopicId(topic_name, source=source),
            )
        except Exception as e:
            print(f"Error processing {group_name}: {e}")


def _populate_metadata_defaults(aggregated_results: dict, source_filename: str) -> None:
    """Fill model_id, name, and extracted_at if not already set."""
    from pathlib import Path
    if not aggregated_results["model_id"]:
        aggregated_results["model_id"] = str(uuid.uuid4())
    if not aggregated_results["name"] and source_filename:
        aggregated_results["name"] = Path(source_filename).stem
    if not aggregated_results["extracted_at"]:
        aggregated_results["extracted_at"] = datetime.now(timezone.utc).isoformat()


def _merge_table_entry(entry: dict, new_tbl: dict) -> None:
    """Merge a single incoming table into an existing entry in-place."""
    if "columns" in new_tbl and "columns" not in entry:
        entry["columns"] = new_tbl["columns"]
    if "ingestion" in new_tbl and "ingestion" not in entry:
        entry["ingestion"] = new_tbl["ingestion"]
    _PROTECTED = ("columns", "ingestion")
    for k, v in new_tbl.items():
        if k not in entry and k not in _PROTECTED:
            entry[k] = v


def _merge_tables(existing: list, incoming: list) -> None:
    """Merge incoming tables into existing by name, combining columns and ingestion without duplication."""
    index = {t.get("name"): t for t in existing}
    for new_tbl in incoming:
        name = new_tbl.get("name")
        if name in index:
            _merge_table_entry(index[name], new_tbl)
        else:
            existing.append(new_tbl)
            index[name] = new_tbl


async def _aggregate_queue_results(q: "asyncio.Queue[TaskResponse]", aggregated_results: dict) -> None:
    """Drain the result queue and merge each result into aggregated_results."""
    while not q.empty():
        result = await q.get()
        result_json = json.loads(result.content)

        # Top-level scalar metadata fields
        for field in ("name", "model_id", "extracted_at"):
            if result_json.get(field):
                aggregated_results[field] = result_json[field]

        # List fields — simple extend
        for src_key, dst_key in _RESULT_KEY_MAP.items():
            if src_key in result_json:
                aggregated_results[dst_key].extend(result_json[src_key])

        # Tables need merge logic (not simple extend)
        if "tables" in result_json:
            _merge_tables(aggregated_results["tables"], result_json["tables"])

        # report_pages replaces (not extends)
        if "report_pages" in result_json:
            aggregated_results["report_pages"] = result_json["report_pages"]
        # if "report_filters" in result_json:  # TODO: re-enable when UI supports report-level filters
        #     aggregated_results["report_filters"] = result_json["report_filters"]


async def _run_executive_summary(aggregated_results: dict) -> str:
    """Spin up a fresh runtime, generate the executive summary, and return it."""
    exe_queue: asyncio.Queue[ExecutiveSummaryResponse] = asyncio.Queue()
    summary_runtime = SingleThreadedAgentRuntime()
    await ExecutiveSummaryAgent.register(
        summary_runtime,
        type=executive_summary_topic_type,
        factory=lambda: ExecutiveSummaryAgent(),
    )
    await ClosureAgent.register_closure(
        summary_runtime,
        "save_executive_summary",
        _make_save_executive_summary(exe_queue),
        subscriptions=lambda: [DefaultSubscription()],
    )
    summary_runtime.start()
    await summary_runtime.publish_message(
        Request(content=json.dumps(aggregated_results)),
        topic_id=TopicId(executive_summary_topic_type, source="default"),
    )
    await summary_runtime.stop_when_idle()

    technical_summary = ""
    while not exe_queue.empty():
        data = (await exe_queue.get()).content
        technical_summary = data
        print(f"Technical summary generated ({len(technical_summary)} chars)")
    return technical_summary


async def run_single_tenant_flow_processor(extracted_metadata_folder: str, source_filename: str = None):
    """
    Process Power BI extracted metadata.

    Args:
        extracted_metadata_folder: Path to folder containing extracted JSON files
        source_filename: Original uploaded filename — used as fallback for the name field
    """
    from pathlib import Path

    metadata_folder = Path(extracted_metadata_folder)
    file_groups = _build_file_groups(metadata_folder)

    # Per-call queues — avoids cross-contamination when batch processes
    # multiple PowerBI files concurrently.
    result_queue: asyncio.Queue[TaskResponse] = asyncio.Queue()

    # Setup Autogen Core runtime
    runtime = SingleThreadedAgentRuntime()

    # Register agents
    await PowerBIMetadataExtractorAgent.register(
        runtime,
        type="PowerBIMetadataExtractor",
        factory=lambda: PowerBIMetadataExtractorAgent(),
    )
    # ExecutiveSummaryAgent runs in its own runtime inside _run_executive_summary;
    # do NOT register save_executive_summary here — it would receive TaskResponse
    # messages from the extractor agents and log spurious type-mismatch warnings.
    await ClosureAgent.register_closure(
        runtime,
        "collect_result_agent",
        _make_collect_result(result_queue),
        subscriptions=lambda: [DefaultSubscription()],
    )

    runtime.start()
    print("[agents_powerbi] Publishing all file groups to runtime...")
    await _process_file_groups(file_groups, runtime)
    print("[agents_powerbi] All groups published. Waiting for runtime to finish...")

    await runtime.stop_when_idle()
    print("[agents_powerbi] Runtime finished. Collecting results...")

    aggregated_results = {
        "schema_version": "1.0",
        "model_id": None,
        "name": None,
        "extracted_at": None,
        "data_sources": [],
        "tables": [],
        "relationships": [],
        "calculations": [],
        "report_pages": [],
        # "report_filters": [],  # TODO: re-enable when UI supports report-level filters
    }

    await _aggregate_queue_results(result_queue, aggregated_results)
    _populate_metadata_defaults(aggregated_results, source_filename)
    _fill_autodate_hierarchies_and_variations(aggregated_results, metadata_folder)
    # Calc-column lineage: write DAX onto tables[].columns[].expression and
    # remove the duplicate calculations[] entries. Must run after Pass 0
    # (calc tables present) but BEFORE anything reads calculations[].
    _backfill_calc_column_expressions_and_types(aggregated_results, metadata_folder)
    _strip_calc_column_duplicates_from_calculations(aggregated_results, metadata_folder)
    # Measure home_table: write verbatim from dax_measures.json.TableName so
    # FE doesn't have to re-infer from depends_on_columns (which fails for
    # measures that live on one table but read from another).
    _backfill_measure_home_tables(aggregated_results, metadata_folder)
    # Field Parameter calc tables: rewrite columns to canonical 3-col shape
    # with ParameterMetadata. Detection is DAX-pattern-based (NAMEOF tuples).
    _detect_and_rewrite_field_parameter_tables(aggregated_results)
    # Relationship cleanup: drop misclassified auto-date stubs, collapse
    # duplicate-endpoint rows (keep best shape), re-link variations to the
    # surviving relationship id, sanity-override pbixray's 1:1 misreads.
    _drop_misclassified_autodate_stubs(aggregated_results, metadata_folder)
    _dedupe_and_relink_relationships(aggregated_results)
    _sanity_override_cardinality(aggregated_results)
    # Recover null-right relationships pbixray dropped but which aren't auto-date
    # stubs (e.g. dim_date.date <-> Revenue Daywise.date in Shield Insurance).
    # Runs AFTER sanity override so the wired exclusion uses final cardinality.
    _recover_null_right_relationships(aggregated_results)
    # Cosmetic: surface auto-date hidden flags so the JSON matches reality.
    _apply_autodate_hidden_flags(aggregated_results)

    technical_summary = await _run_executive_summary(aggregated_results)

    enforced = _enforce_common_model_schema(aggregated_results)
    enforced["technical_summary"] = technical_summary

    from consolidated_model_builder import build_consolidated_model
    enforced["consolidated_model"] = build_consolidated_model(enforced)
    
    return enforced
