"""
debug_collector.py — Pipeline checkpoint writer for PBIP converter.

Writes input/output pairs at each meaningful pipeline function to:
    debug/{ReportName}/{YYYYMMDD_HHMMSS}/

Files are written immediately (not buffered), so partial results
survive pipeline crashes. Import and call log_* functions from any module.

Folder layout per run:
    01_parse/
        01_detect_source.json
        02_column_type_normalization.json
        03_visual_type_normalization.json
        04_intermediate_full.json
    02_map/
        01_dax_conversions.json
        02_type_inferences.json
        03_visual_type_resolutions.json
        04_relationship_resolution.json
        05_mapped_full.json
    03_semantic_model/
        01_sum_column_upgrades.json
        02_tmdl_tables/{TableName}.json
        03_field_parameter_tables/{TableName}.json
        04_relationships_tmdl.json
    04_report/
        00_field_param_separation.json
        pages/{PageName}/visuals/{VisualTitle}/
            00_input.json
            01_agg_decisions.json
            02_query_state.json
            03_visual_json.json
"""
import json
import os
import re
import threading
from datetime import datetime

_local = threading.local()


def _get():
    return getattr(_local, "session", None)


def init(debug_base_dir: str, report_name: str) -> str:
    """Initialize a debug session for a single pipeline run.

    Returns the debug directory path (e.g. debug/MyReport/20250513_142301/).
    Call once at the start of each run before any pipeline stage executes.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = re.sub(r'[\\/:*?"<>|]', "_", report_name or "MyReport")
    debug_dir = os.path.join(debug_base_dir, safe, ts)
    _local.session = _Session(debug_dir)
    return debug_dir


def is_active() -> bool:
    return _get() is not None


def _write_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _safe(name: str) -> str:
    """Sanitize a string for use as a file/folder name.

    Replaces Windows-illegal characters AND control characters (newlines,
    tabs, etc.) — without the control-char strip a multi-line title would
    crash os.makedirs with WinError 3. Also caps length so the resulting
    path stays under Windows' 260-char MAX_PATH limit.
    """
    s = re.sub(r'[\\/:*?"<>|\r\n\t\x00-\x1f]', "_", str(name))
    s = re.sub(r'_+', "_", s).strip("_ .")
    return (s[:80] or "unnamed")


class _Session:
    def __init__(self, d: str):
        self.d = d
        # Accumulators for per-item logs (flushed once at end of each stage)
        self._col_types: list = []
        self._vis_types: list = []
        self._dax: list = []
        self._type_infs: list = []
        self._vis_res: list = []
        self._rel_res: list = []
        self._sum_upgrades: list = []


# ── Stage 1: Parse ────────────────────────────────────────────────────────────

def log_detect_source(data_source_ids: list, detected: str):
    """Log detect_source() result: which IDs were present and what was detected."""
    s = _get()
    if not s:
        return
    _write_json(
        os.path.join(s.d, "01_parse", "01_detect_source.json"),
        {"data_source_ids": data_source_ids, "detected": detected},
    )


def log_norm_type(table: str, column: str, raw: str, normalized: str):
    """Accumulate one _norm_type() before/after entry (flushed at parse end)."""
    s = _get()
    if s:
        s._col_types.append({
            "table": table,
            "column": column,
            "raw_type": raw,
            "normalized_type": normalized,
        })


def flush_parse_types():
    """Write accumulated column type normalization entries to disk."""
    s = _get()
    if s and s._col_types:
        _write_json(
            os.path.join(s.d, "01_parse", "02_column_type_normalization.json"),
            s._col_types,
        )


def log_norm_visual_type(page: str, visual_id: str, title: str,
                         raw: str, normalized: str, in_map: bool):
    """Accumulate one _norm_visual_type() before/after entry (flushed at parse end)."""
    s = _get()
    if s:
        s._vis_types.append({
            "page": page,
            "visual_id": visual_id,
            "title": title,
            "raw_type": raw,
            "normalized_type": normalized,
            "in_hardcoded_map": in_map,
        })


def flush_parse_visual_types():
    """Write accumulated visual type normalization entries to disk."""
    s = _get()
    if s and s._vis_types:
        _write_json(
            os.path.join(s.d, "01_parse", "03_visual_type_normalization.json"),
            s._vis_types,
        )


def log_intermediate(intermediate: dict):
    """Write the complete intermediate dict produced by parse_common_model()."""
    s = _get()
    if s:
        _write_json(
            os.path.join(s.d, "01_parse", "04_intermediate_full.json"),
            intermediate,
        )


# ── Stage 2: Map ──────────────────────────────────────────────────────────────

def log_dax(table: str, measure: str, raw: str, llm_out: str, fixed: str):
    """Accumulate one DAX conversion entry: raw → LLM output → post-fix result."""
    s = _get()
    if s:
        s._dax.append({
            "table": table,
            "measure": measure,
            "raw_expression": raw,
            "llm_output": llm_out,
            "final_after_fix": fixed,
            "fix_changed": llm_out != fixed,
        })


def flush_map_dax():
    s = _get()
    if s and s._dax:
        _write_json(
            os.path.join(s.d, "02_map", "01_dax_conversions.json"),
            s._dax,
        )


def log_type_inf(table_col: str, raw: str, inferred: str, llm_called: bool):
    """Accumulate one TypeInferenceAgent result: original type → inferred type."""
    s = _get()
    if s:
        s._type_infs.append({
            "table_column": table_col,
            "raw_type": raw,
            "inferred_type": inferred,
            "llm_called": llm_called,
            "changed": raw != inferred,
        })


def flush_map_types():
    s = _get()
    if s and s._type_infs:
        _write_json(
            os.path.join(s.d, "02_map", "02_type_inferences.json"),
            s._type_infs,
        )


def log_visual_res(page: str, vid: str, raw: str, resolved: str, method: str):
    """Accumulate one VisualMapperAgent result: raw_type → resolved visualType + how."""
    s = _get()
    if s:
        s._vis_res.append({
            "page": page,
            "visual_id": vid,
            "raw_type": raw,
            "resolved_type": resolved,
            "method": method,  # "hardcoded_map"|"intermediate_passthrough"|"llm"|"fallback_tableEx"
        })


def flush_map_visuals():
    s = _get()
    if s and s._vis_res:
        _write_json(
            os.path.join(s.d, "02_map", "03_visual_type_resolutions.json"),
            s._vis_res,
        )


def log_rel_res(orig_from: str, res_from: str, orig_to: str, res_to: str, skipped: bool):
    """Accumulate one relationship table-name resolution entry."""
    s = _get()
    if s:
        s._rel_res.append({
            "original_from_table": orig_from,
            "resolved_from_table": res_from,
            "original_to_table": orig_to,
            "resolved_to_table": res_to,
            "skipped": skipped,
        })


def flush_map_rels():
    s = _get()
    if s and s._rel_res:
        _write_json(
            os.path.join(s.d, "02_map", "04_relationship_resolution.json"),
            s._rel_res,
        )


def log_mapped(mapped: dict):
    """Write the complete mapped dict produced by map_intermediate()."""
    s = _get()
    if s:
        _write_json(
            os.path.join(s.d, "02_map", "05_mapped_full.json"),
            mapped,
        )


# ── Stage 3: Semantic Model ───────────────────────────────────────────────────

def log_sum_upgrade(table: str, sum_cols: set, upgraded: list):
    """Accumulate one _collect_sum_columns() result: which string cols were upgraded to double."""
    s = _get()
    if s:
        s._sum_upgrades.append({
            "table": table,
            "sum_cols_found_in_measures": sorted(sum_cols),
            "string_cols_upgraded_to_double": upgraded,
        })


def flush_sum_upgrades():
    s = _get()
    if s and s._sum_upgrades:
        _write_json(
            os.path.join(s.d, "03_semantic_model", "01_sum_column_upgrades.json"),
            s._sum_upgrades,
        )


def log_tmdl_table(name: str, col_count: int, measure_count: int,
                   has_csv: bool, tmdl: str):
    """Write _tmdl_table() output: metadata + full TMDL text for one table."""
    s = _get()
    if not s:
        return
    _write_json(
        os.path.join(s.d, "03_semantic_model", "02_tmdl_tables", f"{_safe(name)}.json"),
        {
            "table_name": name,
            "column_count": col_count,
            "measure_count": measure_count,
            "has_csv_source": has_csv,
            "tmdl_text": tmdl,
        },
    )


def log_field_param_table(name: str, measure_count: int, tmdl: str):
    """Write _tmdl_field_parameter_table() output for one field parameter table."""
    s = _get()
    if not s:
        return
    _write_json(
        os.path.join(s.d, "03_semantic_model", "03_field_parameter_tables",
                     f"{_safe(name)}.json"),
        {
            "table_name": name,
            "measure_count": measure_count,
            "tmdl_text": tmdl,
        },
    )


def log_relationships_tmdl(count: int, tmdl: str):
    """Write _tmdl_relationships_file() output: count + full TMDL text."""
    s = _get()
    if not s:
        return
    _write_json(
        os.path.join(s.d, "03_semantic_model", "04_relationships_tmdl.json"),
        {"relationship_count": count, "tmdl_text": tmdl},
    )


# ── Stage 4: Report / Visual ──────────────────────────────────────────────────

def log_fp_separation(measure_fp: list, dim_fp: list):
    """Write field parameter table separation: measure-type vs dimension-type lists."""
    s = _get()
    if not s:
        return
    _write_json(
        os.path.join(s.d, "04_report", "00_field_param_separation.json"),
        {
            "measure_type_parameter_tables": measure_fp,
            "dimension_type_parameter_tables": dim_fp,
        },
    )


def log_visual(page: str, vis_title: str, vis_idx: int,
               input_dict: dict, agg_decisions: list,
               query_state: dict, visual_json: dict):
    """Write all four checkpoint files for a single visual:
    00_input, 01_agg_decisions, 02_query_state, 03_visual_json.
    """
    s = _get()
    if not s:
        return
    safe_title = _safe(vis_title or f"visual_{vis_idx}")
    base = os.path.join(
        s.d, "04_report", "pages", _safe(page), "visuals", safe_title
    )
    _write_json(os.path.join(base, "00_input.json"), input_dict)
    _write_json(os.path.join(base, "01_agg_decisions.json"), agg_decisions)
    _write_json(os.path.join(base, "02_query_state.json"), query_state)
    _write_json(os.path.join(base, "03_visual_json.json"), visual_json)
