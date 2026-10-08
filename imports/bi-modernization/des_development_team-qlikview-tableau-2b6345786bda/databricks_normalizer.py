"""
Normalizer: Converts each BI tool's JSON output into unified rows
for the 17 Databricks tables.
"""

import uuid
import json
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List


_KEY_DATA_MODEL = "Data Model"


def _uid() -> str:
    return str(uuid.uuid4())


def _json_str(obj) -> str:
    """Safely convert lists/dicts to JSON string, or return empty string."""
    if obj is None:
        return ""
    if isinstance(obj, (list, dict)):
        try:
            return json.dumps(obj)
        except (TypeError, ValueError):
            return json.dumps(obj, default=str)
    return str(obj)


def _source_fingerprint(source: dict) -> str:
    """Normalized hash for dedup detection across tools."""
    server = (source.get("server") or source.get("connection_details") or "").lower().split(".")[0].strip()
    database = (source.get("database_name") or source.get("database") or "").lower().strip()
    source_type = (source.get("source_type") or source.get("type") or "").lower().strip()
    canonical = f"{source_type}|{server}|{database}"
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _column_signature(fields: List[dict]) -> str:
    """Hash of sorted column names for table dedup detection."""
    if not fields:
        return ""
    names = sorted([f.get("name", "").lower().strip() for f in fields if f.get("name")])
    return hashlib.sha256("|".join(names).encode()).hexdigest()[:16]


# ============================================================
# TABLEAU NORMALIZER
# ============================================================
def normalize_tableau(json_output: dict, file_name: str) -> Dict[str, List[dict]]:
    """
    Tableau JSON structure:
    {
      "Data Sources": [...],
      "Data Model": [...],
      "Data Transformations": [...],
      "Hierarchies": [...],
      "Visualizations": [...],
      "Filters": [...],
      "Parameters or Variables": [...],
      "Sheets": [...],
      "Dashboards": [...],
      "technical_summary": "..."
    }
    """
    report_id = _uid()
    result = _empty_result()

    # bi_reports
    result["bi_reports"].append({
        "report_id": report_id,
        "tool_type": "tableau",
        "file_name": file_name,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "executive_summary": json_output.get("technical_summary", ""),
    })

    # data_sources
    for src in json_output.get("Data Sources", []):
        result["data_sources"].append({
            "source_id": _uid(),
            "report_id": report_id,
            "name": src.get("name", ""),
            "source_type": src.get("type", ""),
            "server": "",
            "database_name": "",
            "schema_name": "",
            "connection_details": src.get("connection_details", ""),
            "connection_mode": "extract" if src.get("is_extract") else "import",
            "authentication_method": src.get("authentication_method", ""),
            "gateway": "",
            "refresh_schedule": src.get("refresh_schedule", ""),
            "is_extract": src.get("is_extract", False),
            "extract_refresh_schedule": src.get("extract_refresh_schedule", ""),
            "is_published": src.get("is_published", False),
            "used_by": _json_str(src.get("used_by", [])),
            "fingerprint": _source_fingerprint(src),
        })

    # tables_model + columns_metadata
    for tbl in json_output.get(_KEY_DATA_MODEL, []):
        table_id = _uid()
        fields = tbl.get("fields", [])
        result["tables_model"].append({
            "table_id": table_id,
            "report_id": report_id,
            "table_name": tbl.get("table_name", ""),
            "source_object": "",
            "is_materialized": None,
            "row_count_estimate": None,
            "refresh_frequency": "",
            "used_by": _json_str(tbl.get("used_by", [])),
            "column_signature": _column_signature(fields),
        })
        for field in fields:
            result["columns_metadata"].append({
                "column_id": _uid(),
                "table_id": table_id,
                "report_id": report_id,
                "name": field.get("name", ""),
                "source_column": "",
                "data_type": field.get("type", ""),
                "nullable": None,
                "is_hidden": None,
                "used_in_relationships": None,
                "used_in_filters": None,
                "used_in_groupby": None,
                "used_in_calculations": None,
                "used_in_rls": None,
                "distinct_count_high": None,
                "description": "",
            })

    # relationships (Tableau stores as strings in Data Model)
    _normalize_data_model_relationships(json_output, report_id, result)

    # transformations
    for tr in json_output.get("Data Transformations", []):
        result["transformations"].append({
            "transformation_id": _uid(),
            "report_id": report_id,
            "name": tr.get("name", ""),
            "table_name": "",
            "step_type": "custom",
            "expression": tr.get("expression", ""),
            "description": tr.get("description", ""),
            "data_type": tr.get("data_type", ""),
            "role": tr.get("role", ""),
            "used_in": _json_str(tr.get("used_in", [])),
            "filters": _json_str(tr.get("filters", [])),
        })

    # dashboards + dashboard_components
    for dash in json_output.get("Dashboards", []):
        dashboard_id = _uid()
        result["dashboards"].append({
            "dashboard_id": dashboard_id,
            "report_id": report_id,
            "name": dash.get("name", ""),
            "object_id": dash.get("object_id", ""),
            "width": dash.get("width"),
            "height": dash.get("height"),
            "background_color": dash.get("background_color", ""),
        })
        for comp in dash.get("components", []):
            pos = comp.get("position", {})
            result["dashboard_components"].append({
                "component_id": _uid(),
                "dashboard_id": dashboard_id,
                "name": comp.get("name", ""),
                "object_id": comp.get("object_id", ""),
                "position_x": pos.get("x"),
                "position_y": pos.get("y"),
                "width": pos.get("width"),
                "height": pos.get("height"),
                "font_size": comp.get("font_size"),
                "color": comp.get("color", ""),
            })

    # visualizations + viz_chart_mappings + viz_table_columns + viz_data_bindings
    _normalize_visualizations(json_output.get("Visualizations", []), report_id, result)

    # filters
    for f in json_output.get("Filters", []):
        result["filters"].append({
            "filter_id": _uid(),
            "report_id": report_id,
            "object_id": f.get("object_id", ""),
            "name": f.get("name", ""),
            "scope": f.get("type", ""),
            "table_name": "",
            "column_name": "",
            "columns": _json_str(f.get("columns", [])),
            "condition": "",
            "hardcoded": None,
            "formatting": _json_str(f.get("formatting", {})),
            "background_color": f.get("background_color", ""),
        })

    # parameters_variables
    for p in json_output.get("Parameters or Variables", []):
        result["parameters_variables"].append({
            "param_id": _uid(),
            "report_id": report_id,
            "name": p.get("name", ""),
            "param_type": p.get("type", ""),
            "expression": p.get("calculation", p.get("default", "")),
        })

    # hierarchies
    for h in json_output.get("Hierarchies", []):
        result["hierarchies"].append({
            "hierarchy_id": _uid(),
            "report_id": report_id,
            "name": h.get("name", ""),
            "members": _json_str(h.get("members", [])),
        })

    return result


# ============================================================
# QLIKVIEW NORMALIZER
# ============================================================
def normalize_qlikview(json_output: dict, file_name: str) -> Dict[str, List[dict]]:
    """
    QlikView JSON structure (same keys as Tableau):
    {
      "Data Sources": [...],
      "Data Model": [...],
      "Data Transformations": [...],
      "Hierarchies": [...],
      "Visualizations": [...],
      "Filters": [...],
      "Parameters or Variables": [...],
      "Sheets": [...],
      "Dashboards": [...],
      "executivesummary": "..."
    }
    """
    report_id = _uid()
    result = _empty_result()

    # bi_reports
    result["bi_reports"].append({
        "report_id": report_id,
        "tool_type": "qlikview",
        "file_name": file_name,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "executive_summary": json_output.get("executivesummary", ""),
    })

    # data_sources
    for src in json_output.get("Data Sources", []):
        result["data_sources"].append({
            "source_id": _uid(),
            "report_id": report_id,
            "name": src.get("name", ""),
            "source_type": src.get("type", ""),
            "server": "",
            "database_name": "",
            "schema_name": "",
            "connection_details": src.get("connection_details", ""),
            "connection_mode": "extract" if src.get("is_extract") else "import",
            "authentication_method": src.get("authentication_method", ""),
            "gateway": "",
            "refresh_schedule": src.get("refresh_schedule", ""),
            "is_extract": src.get("is_extract", False),
            "extract_refresh_schedule": src.get("extract_refresh_schedule", ""),
            "is_published": src.get("is_published", False),
            "used_by": _json_str(src.get("used_by", [])),
            "fingerprint": _source_fingerprint(src),
        })

    # tables_model + columns_metadata
    for tbl in json_output.get(_KEY_DATA_MODEL, []):
        table_id = _uid()
        fields = tbl.get("fields", [])
        result["tables_model"].append({
            "table_id": table_id,
            "report_id": report_id,
            "table_name": tbl.get("table_name", ""),
            "source_object": "",
            "is_materialized": None,
            "row_count_estimate": None,
            "refresh_frequency": "",
            "used_by": _json_str(tbl.get("used_by", [])),
            "column_signature": _column_signature(fields),
        })
        for field in fields:
            result["columns_metadata"].append({
                "column_id": _uid(),
                "table_id": table_id,
                "report_id": report_id,
                "name": field.get("name", ""),
                "source_column": "",
                "data_type": field.get("type", ""),
                "nullable": None,
                "is_hidden": None,
                "used_in_relationships": None,
                "used_in_filters": None,
                "used_in_groupby": None,
                "used_in_calculations": None,
                "used_in_rls": None,
                "distinct_count_high": None,
                "description": "",
            })

    # relationships
    _normalize_data_model_relationships(json_output, report_id, result)

    # transformations
    for tr in json_output.get("Data Transformations", []):
        result["transformations"].append({
            "transformation_id": _uid(),
            "report_id": report_id,
            "name": tr.get("name", ""),
            "table_name": "",
            "step_type": "custom",
            "expression": tr.get("expression", ""),
            "description": tr.get("description", ""),
            "data_type": tr.get("data_type", ""),
            "role": tr.get("role", ""),
            "used_in": _json_str(tr.get("used_in", [])),
            "filters": _json_str(tr.get("filters", [])),
        })

    # dashboards + dashboard_components
    for dash in json_output.get("Dashboards", []):
        dashboard_id = _uid()
        result["dashboards"].append({
            "dashboard_id": dashboard_id,
            "report_id": report_id,
            "name": dash.get("name", ""),
            "object_id": dash.get("object_id", ""),
            "width": dash.get("width"),
            "height": dash.get("height"),
            "background_color": dash.get("background_color", ""),
        })
        for comp in dash.get("components", []):
            pos = comp.get("position", {})
            result["dashboard_components"].append({
                "component_id": _uid(),
                "dashboard_id": dashboard_id,
                "name": comp.get("name", ""),
                "object_id": comp.get("object_id", ""),
                "position_x": pos.get("x"),
                "position_y": pos.get("y"),
                "width": pos.get("width"),
                "height": pos.get("height"),
                "font_size": comp.get("font_size"),
                "color": comp.get("color", ""),
            })

    # visualizations
    _normalize_visualizations(json_output.get("Visualizations", []), report_id, result)

    # filters (QlikView has object_id, columns, formatting)
    for f in json_output.get("Filters", []):
        result["filters"].append({
            "filter_id": _uid(),
            "report_id": report_id,
            "object_id": f.get("object_id", ""),
            "name": f.get("name", ""),
            "scope": f.get("type", ""),
            "table_name": "",
            "column_name": "",
            "columns": _json_str(f.get("columns", [])),
            "condition": "",
            "hardcoded": None,
            "formatting": _json_str(f.get("formatting", {})),
            "background_color": f.get("background_color", ""),
        })

    # parameters_variables
    for p in json_output.get("Parameters or Variables", []):
        result["parameters_variables"].append({
            "param_id": _uid(),
            "report_id": report_id,
            "name": p.get("name", ""),
            "param_type": p.get("type", ""),
            "expression": p.get("calculation", ""),
        })

    # sheets (QlikView has sheets separately)
    # Sheets are lightweight — store as dashboards with no components
    for s in json_output.get("Sheets", []):
        # Only add if not already in dashboards
        result["dashboards"].append({
            "dashboard_id": _uid(),
            "report_id": report_id,
            "name": s.get("name", ""),
            "object_id": s.get("object_id", ""),
            "width": None,
            "height": None,
            "background_color": "",
        })

    # hierarchies
    for h in json_output.get("Hierarchies", []):
        result["hierarchies"].append({
            "hierarchy_id": _uid(),
            "report_id": report_id,
            "name": h.get("name", ""),
            "members": _json_str(h.get("members", [])),
        })

    return result


# ============================================================
# POWER BI NORMALIZER
# ============================================================
def _normalize_powerbi_sources(agent: dict, report_id: str, result: dict) -> None:
    """Append data_sources rows from agent output."""
    for src in agent.get("data_sources", []):
        result["data_sources"].append({
            "source_id": _uid(), "report_id": report_id,
            "name": src.get("name", ""), "source_type": src.get("source_type", ""),
            "server": src.get("server", ""), "database_name": src.get("database", ""),
            "schema_name": src.get("schema", ""), "connection_details": src.get("path", ""),
            "connection_mode": src.get("connection_mode", ""),
            "authentication_method": src.get("authentication_method", ""),
            "gateway": src.get("gateway", ""), "refresh_schedule": src.get("refresh_frequency", ""),
            "is_extract": False, "extract_refresh_schedule": "", "is_published": False,
            "used_by": "", "fingerprint": _source_fingerprint(src),
        })


def _normalize_powerbi_tables(agent: dict, report_id: str, result: dict) -> None:
    """Append tables_model, columns_metadata, and transformations rows."""
    for tbl in agent.get("tables", []):
        table_id = _uid()
        columns = tbl.get("columns", [])
        result["tables_model"].append({
            "table_id": table_id, "report_id": report_id,
            "table_name": tbl.get("name", ""), "source_object": tbl.get("source_data_source_id", ""),
            "is_materialized": tbl.get("is_materialized"), "row_count_estimate": tbl.get("row_count_estimate"),
            "refresh_frequency": "", "used_by": "", "column_signature": _column_signature(columns),
        })
        for col in columns:
            result["columns_metadata"].append({
                "column_id": _uid(), "table_id": table_id, "report_id": report_id,
                "name": col.get("name", ""), "source_column": col.get("name", ""),
                "data_type": col.get("data_type", ""), "nullable": col.get("nullable"),
                "is_hidden": col.get("hidden"), "used_in_relationships": col.get("used_in_relationships"),
                "used_in_filters": col.get("used_in_filters"), "used_in_groupby": col.get("used_in_groupby"),
                "used_in_calculations": col.get("used_in_calculations"), "used_in_rls": col.get("used_in_rls"),
                "distinct_count_high": col.get("distinct_count_high"), "description": col.get("description", ""),
            })
        for step in tbl.get("ingestion", {}).get("steps", []):
            result["transformations"].append({
                "transformation_id": _uid(), "report_id": report_id,
                "name": f"{tbl.get('name', '')} - step {step.get('order', '')}",
                "table_name": tbl.get("name", ""), "step_type": step.get("step_type", ""),
                "expression": step.get("native_expressions", {}).get("powerquery", ""),
                "description": step.get("description", ""),
                "data_type": "", "role": "", "used_in": "", "filters": "",
            })


def _normalize_powerbi_visual_bindings(vis: dict, viz_id: str, result: dict) -> None:
    """Append viz_data_bindings rows for a single Power BI visual."""
    for tbl_name in vis.get("tables_used", []):
        result["viz_data_bindings"].append({
            "binding_id": _uid(), "viz_id": viz_id,
            "binding_type": "table_used", "field_name": tbl_name, "expression": "",
        })
    for col_ref in vis.get("columns_used", []):
        col_name = col_ref if isinstance(col_ref, str) else f"{col_ref.get('table','')}.{col_ref.get('column','')}"
        result["viz_data_bindings"].append({
            "binding_id": _uid(), "viz_id": viz_id,
            "binding_type": "column_used", "field_name": col_name, "expression": "",
        })
    for measure in vis.get("measures_used", []):
        result["viz_data_bindings"].append({
            "binding_id": _uid(), "viz_id": viz_id,
            "binding_type": "measure", "field_name": measure, "expression": "",
        })


def _normalize_powerbi_pages(agent: dict, report_id: str, result: dict) -> None:
    """Append dashboards, visualizations, and viz_data_bindings from report_pages."""
    for page in agent.get("report_pages", []):
        dashboard_id = _uid()
        result["dashboards"].append({
            "dashboard_id": dashboard_id, "report_id": report_id,
            "name": page.get("page_name", ""), "object_id": "",
            "width": None, "height": None, "background_color": "",
        })
        for vis in page.get("visuals", []):
            viz_id = _uid()
            result["visualizations"].append({
                "viz_id": viz_id, "report_id": report_id, "dashboard_id": dashboard_id,
                "object_id": "", "name": vis.get("visual_name", ""),
                "visual_type": vis.get("visual_type", ""), "formatting": "",
            })
            _normalize_powerbi_visual_bindings(vis, viz_id, result)


def normalize_powerbi(json_output: dict, file_name: str) -> Dict[str, List[dict]]:
    """Power BI normalizer — delegates to focused helper functions."""
    agent = json_output.get("agent_result", json_output)
    report_id = _uid()
    result = _empty_result()

    result["bi_reports"].append({
        "report_id": report_id, "tool_type": "powerbi", "file_name": file_name,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "executive_summary": agent.get("executive_summary", ""),
    })

    _normalize_powerbi_sources(agent, report_id, result)
    _normalize_powerbi_tables(agent, report_id, result)

    for rel in agent.get("relationships", []):
        result["relationships"].append({
            "relationship_id": _uid(), "report_id": report_id,
            "left_table": rel.get("left_table_id", ""), "left_column": rel.get("left_column", ""),
            "right_table": rel.get("right_table_id", ""), "right_column": rel.get("right_column", ""),
            "cardinality": rel.get("cardinality", ""), "join_type": rel.get("join_type", ""),
            "is_active": rel.get("active", True),
            "bidirectional_filter": rel.get("filter_direction") == "bidirectional",
            "composite_key": None, "enforced_integrity": rel.get("enforced_integrity"),
        })

    for calc in agent.get("calculations", []):
        result["calculations"].append({
            "calculation_id": _uid(), "report_id": report_id,
            "name": calc.get("name", ""),
            "expression": calc.get("expressions", {}).get("dax", ""),
            "aggregation": calc.get("semantic_type", ""),
            "depends_on_columns": _json_str(calc.get("depends_on_columns", [])),
            "reusable_metric": calc.get("reusable", False),
        })

    _normalize_powerbi_pages(agent, report_id, result)

    for f in agent.get("filters", []):
        result["filters"].append({
            "filter_id": _uid(), "report_id": report_id, "object_id": "",
            "name": f.get("column", f.get("name", "")), "scope": f.get("scope", ""),
            "table_name": f.get("table", ""), "column_name": f.get("column", ""),
            "columns": "", "condition": f.get("condition", ""),
            "hardcoded": f.get("hardcoded"), "formatting": "", "background_color": "",
        })

    for rls in agent.get("rls_policies", []):
        result["rls_policies"].append({
            "policy_id": _uid(), "report_id": report_id,
            "role_name": rls.get("role_name", ""),
            "table_name": rls.get("table", rls.get("table_name", "")),
            "rule_expression": rls.get("rule_expression", ""),
        })

    return result


# ============================================================
# SHARED HELPERS
# ============================================================
def _empty_result() -> Dict[str, List[dict]]:
    return {
        "bi_reports": [],
        "data_sources": [],
        "tables_model": [],
        "columns_metadata": [],
        "relationships": [],
        "transformations": [],
        "calculations": [],
        "dashboards": [],
        "dashboard_components": [],
        "visualizations": [],
        "viz_chart_mappings": [],
        "viz_table_columns": [],
        "viz_data_bindings": [],
        "filters": [],
        "parameters_variables": [],
        "hierarchies": [],
        "rls_policies": [],
    }


def _normalize_data_model_relationships(json_output: dict, report_id: str, result: dict) -> None:
    """Append relationships rows from Data Model strings (shared by Tableau and QlikView)."""
    for tbl in json_output.get(_KEY_DATA_MODEL, []):
        for rel_str in tbl.get("relationships", []):
            if rel_str:
                result["relationships"].append({
                    "relationship_id": _uid(),
                    "report_id": report_id,
                    "left_table": tbl.get("table_name", ""),
                    "left_column": "",
                    "right_table": "",
                    "right_column": "",
                    "cardinality": "",
                    "join_type": "",
                    "is_active": True,
                    "bidirectional_filter": None,
                    "composite_key": None,
                    "enforced_integrity": None,
                })


def _normalize_viz_data_bindings(vis: dict, viz_id: str, result: dict) -> None:
    """Append viz_data_bindings rows for dimensions, measures, and filters."""
    for dim in vis.get("dimensions", []) or []:
        result["viz_data_bindings"].append({
            "binding_id": _uid(),
            "viz_id": viz_id,
            "binding_type": "dimension",
            "field_name": dim,
            "expression": "",
        })
    for msr in vis.get("measures", []) or []:
        result["viz_data_bindings"].append({
            "binding_id": _uid(),
            "viz_id": viz_id,
            "binding_type": "measure",
            "field_name": msr,
            "expression": "",
        })
    for flt in vis.get("filters", []) or []:
        result["viz_data_bindings"].append({
            "binding_id": _uid(),
            "viz_id": viz_id,
            "binding_type": "filter",
            "field_name": flt,
            "expression": "",
        })


def _normalize_visualizations(viz_list: list, report_id: str, result: dict):
    """Shared visualization normalizer for Tableau and QlikView."""
    for vis in viz_list:
        viz_id = _uid()
        result["visualizations"].append({
            "viz_id": viz_id,
            "report_id": report_id,
            "dashboard_id": None,
            "object_id": vis.get("object_id", ""),
            "name": vis.get("name", ""),
            "visual_type": vis.get("type", ""),
            "formatting": _json_str(vis.get("formatting", {})),
        })

        # chart_mappings
        cm = vis.get("chart_mappings")
        if cm and isinstance(cm, dict):
            result["viz_chart_mappings"].append({
                "mapping_id": _uid(),
                "viz_id": viz_id,
                "x_axis": cm.get("x_axis", ""),
                "y_axis": cm.get("y_axis", ""),
                "secondary_y_axis": cm.get("secondary_y_axis", ""),
                "color": cm.get("color", ""),
                "text": cm.get("text", ""),
                "size": cm.get("size", ""),
                "legend": cm.get("legend", ""),
                "details": cm.get("details", ""),
            })

        # straight_table_columns
        for col in vis.get("straight_table_columns", []) or []:
            result["viz_table_columns"].append({
                "column_id": _uid(),
                "viz_id": viz_id,
                "name": col.get("name", ""),
                "expression": col.get("expression", ""),
            })

        # data bindings: dimensions, measures, filters
        _normalize_viz_data_bindings(vis, viz_id, result)
