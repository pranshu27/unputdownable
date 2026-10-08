"""
Generates a mapping report Excel file.

Columns come from Postgres (bi_reports → tables_model → columns_metadata).
The Excel file is used purely as a lookup: (file_name, table_name, Source Column) → New Source Column.

Status per column:
  - Found     : column found in Excel AND New Source Column is non-empty
  - Not Found : column NOT found in Excel, or found but New Source Column is empty
"""

import os
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment
from datetime import datetime

from postgres_writer import get_db_session
from postgres_models import BiReport, TableModel, ColumnMetadata

EXCEL_INPUT = "insurance_mapping_consolidated.xlsx"
_NOT_FOUND = "Not Found"


def _output_file() -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"mapping_report_{ts}.xlsx"


# ── 1. Load Excel as lookup ───────────────────────────────────────────────────

def _find_header_row(rows: list) -> int | None:
    """Return the index of the first row containing 'source column', or None."""
    for i, row in enumerate(rows):
        normalized = [str(h).strip().lower() if h is not None else "" for h in row]
        if "source column" in normalized:
            return i
    return None


def load_excel_lookup(path: str) -> dict[tuple, str]:
    """
    Returns { (source_schema, source_column): new_source_column }
    Columns expected: source schema, source column, new source schema, new source column.
    Skips leading title/merged rows until the real header row is found.
    """
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))

    header_idx = _find_header_row(rows)
    if header_idx is None:
        print(f"  WARNING: Could not find header row in {path}. Lookup will be empty.")
        wb.close()
        return {}

    headers_raw = [str(h).strip() if h is not None else "" for h in rows[header_idx]]
    headers = [h.lower() for h in headers_raw]
    print(f"  Excel headers found (row {header_idx + 1}): {headers_raw}")

    lookup = {}
    for row in rows[header_idx + 1:]:
        if not any(row):
            continue
        r = dict(zip(headers, row))
        schema = str(r.get("source schema")     or "").strip()
        src    = str(r.get("source column")     or "").strip()
        new    = str(r.get("new source column") or "").strip()
        if schema and src:
            lookup[(schema, src)] = new
    wb.close()
    print(f"  Excel lookup: {len(lookup)} entries loaded from {path}")
    return lookup


# ── 2. Fetch columns from Databricks ─────────────────────────────────────────

def fetch_databricks_columns() -> dict[str, dict[str, list[str]]]:
    """
    Returns { file_name: { table_name: [col1, col2, ...] } }
    Fetches from Postgres instead of Databricks.
    """
    with get_db_session() as session:
        rows = (
            session.query(
                BiReport.file_name,
                TableModel.table_name,
                ColumnMetadata.name.label("column_name"),
            )
            .join(TableModel, TableModel.report_id == BiReport.report_id)
            .join(ColumnMetadata, ColumnMetadata.table_id == TableModel.table_id)
            .filter(
                ColumnMetadata.name.isnot(None),
                ColumnMetadata.name != "",
            )
            .order_by(BiReport.file_name, TableModel.table_name, ColumnMetadata.name)
            .all()
        )

    result: dict[str, dict[str, list[str]]] = {}
    for fn, tn, col in rows:
        fn  = str(fn  or "").strip()
        tn  = str(tn  or "").strip()
        col = str(col or "").strip()
        if not (fn and tn and col):
            continue
        if fn not in result:
            result[fn] = {}
        if tn not in result[fn]:
            result[fn][tn] = []
        result[fn][tn].append(col)

    total_cols = sum(len(cols) for tables in result.values() for cols in tables.values())
    print(f"  Postgres: {len(result)} file(s), {total_cols} column(s) fetched")
    return result


# ── 3. Determine status ───────────────────────────────────────────────────────

def get_status(_file_name: str, table_name: str, col: str, lookup: dict) -> tuple[str, str]:
    """
    Returns (new_source_col, status_label).
    Status:
      Found     — source column exists in Excel AND new source column is non-empty
      Not Found — source column not in Excel, or no new source column mapping
    Lookup key is (table_name, col) matching (source schema, source column) in Excel.
    """
    key = (table_name, col)
    if key not in lookup:
        return ("", _NOT_FOUND)
    new_src = lookup[key]
    if new_src:
        return (new_src, "Found")
    return ("", _NOT_FOUND)


# ── 4. Excel styling ──────────────────────────────────────────────────────────

HEADER_FILL  = PatternFill("solid", fgColor="2E4057")   # dark blue
FOUND_FILL     = PatternFill("solid", fgColor="D4EDDA")   # light green — Found
NOT_FOUND_FILL = PatternFill("solid", fgColor="F8D7DA")   # light red   — Not Found
TABLE_FILL     = PatternFill("solid", fgColor="E8F0FE")   # light blue  — table sub-header

WHITE_BOLD = Font(bold=True, color="FFFFFF")
DARK_BOLD  = Font(bold=True)

STATUS_FILL = {
    "Found":   FOUND_FILL,
    _NOT_FOUND: NOT_FOUND_FILL,
}


def _style_header(cell, text):
    cell.value = text
    cell.font  = WHITE_BOLD
    cell.fill  = HEADER_FILL
    cell.alignment = Alignment(horizontal="center", vertical="center")


def _write_table_subheader(ws, row_num: int, table_name: str):
    ws.row_dimensions[row_num].height = 18
    for col in range(1, 4):
        c = ws.cell(row_num, col)
        c.fill = TABLE_FILL
        c.font = DARK_BOLD
        c.alignment = Alignment(horizontal="left", vertical="center")
    ws.cell(row_num, 1).value = f"Table: {table_name}"


def _write_column_row(ws, row_num: int, col: str, new_src: str, status: str) -> None:
    """Write a single column data row with appropriate fill styling."""
    row_fill = STATUS_FILL[status]
    c1 = ws.cell(row_num, 1, col)
    c2 = ws.cell(row_num, 2, new_src)
    c3 = ws.cell(row_num, 3, status)
    for c in (c1, c2, c3):
        c.fill = row_fill
        c.alignment = Alignment(horizontal="left", vertical="center")


# ── 5. Write sheet ────────────────────────────────────────────────────────────

def write_sheet(ws, file_name: str, tables: dict[str, list[str]], lookup: dict) -> dict[str, bool]:
    """
    Writes the detail sheet and returns { table_name: ready_to_migrate }
    A table is ready to migrate only if every column is Found.
    """
    ws.column_dimensions["A"].width = 40  # Source Column
    ws.column_dimensions["B"].width = 40  # New Source Column
    ws.column_dimensions["C"].width = 20  # Status

    ws.row_dimensions[1].height = 22
    _style_header(ws.cell(1, 1), "Source Column")
    _style_header(ws.cell(1, 2), "New Source Column")
    _style_header(ws.cell(1, 3), "Status")

    current_row = 2
    readiness: dict[str, bool] = {}

    for i, (table_name, columns) in enumerate(tables.items()):
        if i > 0:
            current_row += 1

        _write_table_subheader(ws, current_row, table_name)
        current_row += 1

        all_found = True
        for col in columns:
            new_src, status = get_status(file_name, table_name, col, lookup)
            if status != "Found":
                all_found = False
            _write_column_row(ws, current_row, col, new_src, status)
            current_row += 1

        readiness[table_name] = all_found

    return readiness


# ── 6. Generate report ────────────────────────────────────────────────────────

READY_FILL     = PatternFill("solid", fgColor="C3E6CB")   # green  — Ready to Migrate
NOT_READY_FILL = PatternFill("solid", fgColor="F5C6CB")   # red    — Not Ready


def _write_migration_summary(ws, all_readiness: list[tuple[str, str, bool]]):
    """Writes the Migration Readiness summary sheet."""
    ws.column_dimensions["A"].width = 45  # File Name
    ws.column_dimensions["B"].width = 40  # Table Name
    ws.column_dimensions["C"].width = 20  # Ready to Migrate

    ws.row_dimensions[1].height = 22
    _style_header(ws.cell(1, 1), "File Name")
    _style_header(ws.cell(1, 2), "Table Name")
    _style_header(ws.cell(1, 3), "Ready to Migrate")

    for i, (file_name, table_name, ready) in enumerate(all_readiness, start=2):
        label = "Yes" if ready else "No"
        fill  = READY_FILL if ready else NOT_READY_FILL

        c1 = ws.cell(i, 1, file_name)
        c2 = ws.cell(i, 2, table_name)
        c3 = ws.cell(i, 3, label)

        for c in (c1, c2, c3):
            c.fill = fill
            c.alignment = Alignment(horizontal="left", vertical="center")


def generate_report(db_columns: dict, lookup: dict, output_path: str):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    all_readiness: list[tuple[str, str, bool]] = []  # (file_name, table_name, ready)

    for file_name, tables in db_columns.items():
        # Strip .pbix and remove characters invalid in Excel sheet names: [ ] : * ? / \
        sheet_name = file_name.replace(".pbix", "")
        for ch in r'[]:*?/\\':
            sheet_name = sheet_name.replace(ch, "")
        sheet_name = sheet_name.strip()[:31]
        ws = wb.create_sheet(title=sheet_name)
        readiness = write_sheet(ws, file_name, tables, lookup)
        for table_name, ready in readiness.items():
            all_readiness.append((file_name, table_name, ready))
        total = sum(len(c) for c in tables.values())
        print(f"  Sheet written: {sheet_name}  ({len(tables)} tables, {total} columns)")

    # Final summary sheet
    ws_summary = wb.create_sheet(title="Migration Readiness")
    _write_migration_summary(ws_summary, all_readiness)
    ready_count = sum(1 for _, _, r in all_readiness if r)
    print(f"  Summary sheet: {ready_count}/{len(all_readiness)} tables ready to migrate")

    wb.save(output_path)
    print(f"Report saved -> {output_path}")


# ── 7. Entry point ────────────────────────────────────────────────────────────

def main():
    print(f"Loading Excel lookup from {EXCEL_INPUT} ...")
    lookup = load_excel_lookup(EXCEL_INPUT)

    print("\nFetching columns from Databricks ...")
    db_columns = fetch_databricks_columns()

    output_file = _output_file()
    print(f"\nGenerating report -> {output_file} ...")
    generate_report(db_columns, lookup, output_file)


if __name__ == "__main__":
    main()
