import json
from typing import Any


def normalize_name(name: str) -> str:
    """Normalize a table/datasource name for fuzzy matching.
    Strips .csv extension, '+ (Multiple Connections)' suffix,
    lowercases, and trims whitespace.
    """
    if not name:
        return ""
    n = name.lower()
    n = n.replace(".csv", "")
    n = n.replace("+ (multiple connections)", "")
    n = n.replace("(datasource)", "")
    n = n.strip()
    return n


def detect_tool(sample_id: str) -> str:
    """Infer BI tool from the calculation/datasource id pattern."""
    if not sample_id:
        return "Unknown"
    sid = sample_id.lower()
    if "powerbi" in sid:
        return "Power BI"
    elif "tableau" in sid:
        return "Tableau"
    elif "qlik" in sid:
        return "QlikView"
    return "Unknown"


def detect_tool_from_name(name: str) -> str:
    """Infer BI tool from the report/file name extension."""
    if not name:
        return "Unknown"
    n = name.lower().strip()
    if n.endswith(".twb") or n.endswith(".twbx"):
        return "Tableau"
    elif n.endswith(".pbip") or n.endswith(".pbix") or n.endswith(".pbit"):
        return "Power BI"
    elif n.endswith(".qvw") or n.endswith(".qvf"):
        return "QlikView"
    return "Unknown"


def build_kpi_lineage(data: dict) -> dict:
    """
    Build KPI lineage output from the extracted JSON (any tool).

    Parameters:
        data: The full extracted JSON (with data_sources, tables, calculations, etc.)

    Returns:
        A dict matching the kpi_lineage output schema.
    """

    # ── Model-level metadata ──────────────────────────────────
    model_name = data.get("name", "") or data.get("report_name", "")
    model_id = data.get("model_id", "")
    extracted_at = data.get("extracted_at", "")

    # Infer BI tool from the first calculation id
    calculations = data.get("calculations") or []
    _sample_id = calculations[0].get("id", "") if calculations else ""
    bi_tool = detect_tool(_sample_id)

    # If no calculations found or tool unknown, try data_sources id
    if bi_tool == "Unknown":
        ds_list = data.get("data_sources") or []
        if ds_list:
            bi_tool = detect_tool(ds_list[0].get("id", ""))

    # Final fallback: detect from report/file name
    if bi_tool == "Unknown":
        bi_tool = detect_tool_from_name(model_name)
    # ── Build data-source lookup (normalized keys) ────────────
    ds_list = data.get("data_sources") or []
    ds_lookup = {}          # normalized_name → ds dict
    ds_lookup_exact = {}    # exact name → ds dict
    for ds in ds_list:
        ds_lookup_exact[ds["name"]] = ds
        ds_lookup[normalize_name(ds["name"])] = ds

    # ── Build table lookup (normalized keys) ──────────────────
    # table_name → {table_id, table_type, ds_name, source_data_source_id}
    table_lookup = {}       # normalized_name → info dict
    table_lookup_exact = {} # exact name → info dict

    for tbl in data.get("tables") or []:
        tbl_id = tbl.get("id") or ""
        tbl_name = tbl.get("name") or ""
        parts = tbl_id.split("$")
        # New table-id layout: ...$<ds_name>(datasource)$<tbl_name>(table).
        # Scan for the (datasource)-suffixed segment instead of relying on
        # position, so the lookup keeps working if more segments are added.
        ds_name = None
        for seg in parts:
            if seg.endswith("(datasource)"):
                ds_name = seg[: -len("(datasource)")]
                break

        info = {
            "table_id": tbl_id,
            "table_type": tbl.get("table_type", ""),
            "ds_name": ds_name,
            "source_data_source_id": tbl.get("source_data_source_id", ""),
        }
        table_lookup[normalize_name(tbl_name)] = info
        table_lookup_exact[tbl_name] = info

    # ── Build reverse map: source_data_source_id → parent datasource ──
    # For Tableau federated datasources where multiple tables share one ds.

    ds_by_source_id = {}

    # Group tables by their source_data_source_id
    tables_by_src_id: dict[str, list] = {}
    for tbl in data.get("tables") or []:
        src_ds_id = tbl.get("source_data_source_id", "")
        if src_ds_id:
            tables_by_src_id.setdefault(src_ds_id, []).append(tbl)

    # For each group, find the best matching datasource
    for src_ds_id, tbls in tables_by_src_id.items():
        # Check if any datasource name contains one of the table names in this group
        matched_ds = None
        for ds in ds_list:
            ds_name_norm = normalize_name(ds["name"])
            for tbl in tbls:
                tbl_name_norm = normalize_name(tbl["name"])
                if tbl_name_norm in ds_name_norm or ds_name_norm in tbl_name_norm:
                    matched_ds = ds
                    break
            if matched_ds:
                break

        # Fallback: find datasource whose paths array contains the MOST tables from this group
        if not matched_ds:
            best_match_count = 0
            for ds in ds_list:
                ds_paths = ds.get("paths") or []
                ds_paths_norm = [normalize_name(p) for p in ds_paths]
                match_count = sum(1 for tbl in tbls if normalize_name(tbl["name"]) in ds_paths_norm)
                if match_count > best_match_count:
                    best_match_count = match_count
                    matched_ds = ds

        # Fallback: if source_type is federated, use that
        if not matched_ds:
            for ds in ds_list:
                if (ds.get("source_type") or "").lower() == "federated":
                    matched_ds = ds
                    break

        if matched_ds:
            ds_by_source_id[src_ds_id] = matched_ds

    # ── Build KPI name → KPI index map for resolving measure deps ─
    kpi_index = {c["name"]: i for i, c in enumerate(calculations)}

    # ── Resolution helpers ────────────────────────────────────

    def find_table_info(tbl_name: str) -> dict:
        """Find table info by exact name first, then normalized."""
        if tbl_name in table_lookup_exact:
            return table_lookup_exact[tbl_name]
        norm = normalize_name(tbl_name)
        if norm in table_lookup:
            return table_lookup[norm]
        return {}

    def find_datasource(ds_name: str, source_data_source_id: str = "") -> dict:
        """Find datasource by exact name, normalized name, or fallback to source_data_source_id."""
        # Try exact match
        if ds_name and ds_name in ds_lookup_exact:
            return ds_lookup_exact[ds_name]
        # Try normalized match
        if ds_name:
            norm = normalize_name(ds_name)
            if norm in ds_lookup:
                return ds_lookup[norm]
        # Fallback: use source_data_source_id to find parent federated ds
        if source_data_source_id and source_data_source_id in ds_by_source_id:
            return ds_by_source_id[source_data_source_id]
        # Last resort: return first datasource if only one exists
        if len(ds_list) == 1:
            return ds_list[0]
        return {}

    def resolve_column(col_ref: str) -> dict:
        """Parse 'TableName.ColumnName', walk up to data source and report."""
        if not isinstance(col_ref, str):
            col_ref = "" if col_ref is None else str(col_ref)
        # Handle table names that contain dots (e.g., "df_OrderItems.csv.price")
        # Strategy: try matching against known table names (longest match first)
        tbl_name = ""
        col_name = col_ref

        # Try to find the longest matching table name from our lookup
        # Sort by length descending to match "df_OrderItems.csv" before "df_OrderItems"
        all_table_names = sorted(
            list(table_lookup_exact.keys()) + list(table_lookup.keys()),
            key=len, reverse=True
        )
        for candidate in all_table_names:
            # Check if col_ref starts with candidate followed by a dot
            if col_ref.startswith(candidate + "."):
                tbl_name = candidate
                col_name = col_ref[len(candidate) + 1:]
                break
            # Also try normalized match
            norm_candidate = normalize_name(candidate)
            norm_ref_prefix = normalize_name(col_ref.split(".")[0] if "." in col_ref else col_ref)
            if col_ref.lower().startswith(candidate.lower() + "."):
                tbl_name = candidate
                col_name = col_ref[len(candidate) + 1:]
                break

        # Fallback: split on first dot if no table name matched
        if not tbl_name and "." in col_ref:
            dot_idx = col_ref.index(".")
            tbl_name = col_ref[:dot_idx]
            col_name = col_ref[dot_idx + 1:]
            # Check if remaining col_name still has a dot and the extended prefix matches a table
            while "." in col_name:
                extended = tbl_name + "." + col_name[:col_name.index(".")]
                if find_table_info(extended):
                    tbl_name = extended
                    col_name = col_name[col_name.index(".") + 1:]
                else:
                    break

        tbl_info = find_table_info(tbl_name)
        ds_name = tbl_info.get("ds_name", "")
        source_ds_id = tbl_info.get("source_data_source_id", "")
        ds_info = find_datasource(ds_name, source_ds_id)

        # Derive tool from the source id pattern
        src_id = ds_info.get("id", _sample_id)
        src_tool = detect_tool(src_id)
        if src_tool == "Unknown":
            src_tool = bi_tool
        if src_tool == "Unknown":
            src_tool = detect_tool_from_name(model_name)

        return {
            "column_name": col_name,
            "table_name": tbl_name,
            "table_id": tbl_info.get("table_id", ""),
            "table_type": tbl_info.get("table_type", ""),
            "data_source": {
                "name": ds_info.get("name", ds_name or ""),
                "source_type": ds_info.get("source_type", ""),
                "connection_mode": ds_info.get("connection_mode", ""),
                "path": ds_info.get("path", ""),
            },
            "report": {
                "tool": src_tool,
                "report_name": model_name,
                "model_id": model_id,
            },
        }

    def resolve_measure(measure_name: str) -> dict:
        """Return a compact reference to another KPI by name."""
        idx = kpi_index.get(measure_name)
        if idx is None:
            return {"kpi_name": measure_name, "found": False}
        ref = calculations[idx]
        return {
            "kpi_name": ref["name"],
            "found": True,
            "semantic_type": ref.get("semantic_type", ""),
            "aggregation_behavior": ref.get("aggregation_behavior", ""),
            "data_type": ref.get("data_type", ""),
        }

    def get_formula(calc: dict) -> str:
        """Get formula from expressions, trying dax → tableau → qlik."""
        expressions = calc.get("expressions") or {}
        # Try each expression type in priority order
        formula = expressions.get("dax")
        if formula:
            return formula
        formula = expressions.get("tableau")
        if formula:
            return formula
        formula = expressions.get("qlik")
        if formula:
            return formula
        return ""

    # ── Build KPI lineage entries ─────────────────────────────
    kpi_lineage = []
    for calc in calculations:
        # Handle depends_on_columns (guard against null)
        depends_cols = calc.get("depends_on_columns") or []
        # Handle depends_on_measures (guard against null)
        depends_measures = calc.get("depends_on_measures") or []

        entry = {
            "kpi_name": calc["name"],
            "kpi_id": calc["id"],
            "description": calc.get("description", ""),
            "formula": get_formula(calc),
            "semantic_type": calc.get("semantic_type", ""),
            "aggregation_behavior": calc.get("aggregation_behavior", ""),
            "data_type": calc.get("data_type", ""),
            "format_string": calc.get("format_string", ""),
            "is_base_measure": calc.get("is_base_measure", False),
            "reusable": calc.get("reusable", False),
            "display": calc.get("display", {}),
            # Direct column dependencies → table → data source → report
            "depends_on_columns": [resolve_column(c) for c in depends_cols],
            # Measure dependencies → resolved KPI references
            "depends_on_measures": [resolve_measure(m) for m in depends_measures],
        }
        kpi_lineage.append(entry)

    # ── Final output ──────────────────────────────────────────
    output = {
        "schema_version": "1.0",
        "model_id": model_id,
        "report_name": model_name,
        "tool": bi_tool,
        "extracted_at": extracted_at,
        "kpi_lineage": kpi_lineage,
    }

    return output


def append_kpi_lineage(data: dict) -> dict:
    """
    Append kpi_lineage into the extraction output JSON (in-place).

    This is the main integration point: takes the full extraction output
    (with data_sources, tables, calculations, relationships, visualizations,
    technical_summary) and adds the resolved kpi_lineage array to it.

    Parameters:
        data: The full extracted JSON dict

    Returns:
        The same dict with 'kpi_lineage' key added
    """
    lineage_result = build_kpi_lineage(data)
    data["kpi_lineage"] = lineage_result["kpi_lineage"]
    return data


def process_file(input_file: str, output_file: str = None) -> dict:
    """
    Process an extracted JSON file and append KPI lineage into it.

    Parameters:
        input_file: Path to the extracted JSON file
        output_file: Optional path to save the final output JSON
                     (full extraction + kpi_lineage appended)

    Returns:
        The full output dict with kpi_lineage included
    """
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Append kpi_lineage into the extraction output
    result = append_kpi_lineage(data)

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"KPIs processed : {len(result['kpi_lineage'])}")
        print(f"Output saved to: {output_file}")

    # Print summary
    print()
    for kpi in result["kpi_lineage"]:
        print(f"KPI: {kpi['kpi_name']}")
        if kpi["depends_on_columns"]:
            for col in kpi["depends_on_columns"]:
                print(f"  └─ column : {col['column_name']}")
                print(f"     table  : {col['table_name']}  [{col['table_type']}]")
                print(f"     source : {col['data_source']['name']}  ({col['data_source']['source_type']})")
                print(f"     report : {col['report']['tool']} → {col['report']['report_name']}")
        if kpi["depends_on_measures"]:
            for m in kpi["depends_on_measures"]:
                status = "✓" if m["found"] else "✗ (not found)"
                print(f"  └─ measure: {m['kpi_name']}  {status}")
        print()

    return result


# ── CLI usage ─────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python kpi_lineage.py <input_json> [output_json]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "kpi_lineage_output.json"

    process_file(input_path, output_path)
