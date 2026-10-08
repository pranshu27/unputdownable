"""
push_pbix_to_databricks.py
==========================
Reads every .pbix file in input_files/, creates a per-file catalog in
Databricks, and pushes all real source tables as Delta tables.

Layout in Databricks
--------------------
  <catalog_name>              ← sanitized file name  (CREATE CATALOG IF NOT EXISTS)
    └── raw_data              ← fixed schema          (CREATE SCHEMA IF NOT EXISTS)
          ├── dim_customer
          ├── fact_premiums
          └── ...             ← one table per real table in the .pbix

System-table detection
-----------------------
Power BI auto-generates two families of internal tables — they are always
identifiable by their name prefix and are NEVER created by report authors:
  • DateTableTemplate_<uuid>  – 1-row stub; only used to bootstrap LocalDateTable
  • LocalDateTable_<uuid>     – auto date/time hierarchy; managed inside the .pbix

Both families are skipped.  Every other table is treated as a real source table.

Idempotency
-----------
  • CATALOG  → CREATE CATALOG IF NOT EXISTS  (skipped if already present)
  • SCHEMA   → CREATE SCHEMA  IF NOT EXISTS  (skipped if already present)
  • TABLE    → created on first run; TRUNCATED + re-inserted on subsequent runs
                so re-running always refreshes data without duplicating it.
"""

import os
import re
import sys
import traceback
from typing import Optional

import pandas as pd
from pbixray import PBIXRay
from databricks import sql as databricks_sql

# ── Credentials ──────────────────────────────────────────────────────────────
DATABRICKS_WORKSPACE_URL = os.getenv(
    "DATABRICKS_WORKSPACE_URL", "dbc-9064b591-ac6c.cloud.databricks.com"
)
DATABRICKS_ACCESS_TOKEN = os.getenv(
    "DATABRICKS_ACCESS_TOKEN", ""
)
DATABRICKS_CLUSTER_ID = os.getenv(
    "DATABRICKS_CLUSTER_ID", "0206-091900-f4nnmzzq"
)
DATABRICKS_HTTP_PATH = os.getenv(
    "DATABRICKS_HTTP_PATH",
    f"/sql/protocolv1/o/0/{DATABRICKS_CLUSTER_ID}",
)

INPUT_DIR = os.path.join(os.path.dirname(__file__), "input_files")
# Use existing catalog — Databricks requires a storage location to CREATE new catalogs.
# We create one schema per .pbix file inside genai_demo instead.
CATALOG = "genai_demo"

# Prefixes that identify Power BI-internal auto-generated tables
_SYSTEM_PREFIXES = ("DateTableTemplate_", "LocalDateTable_")


# ── Helpers ───────────────────────────────────────────────────────────────────

def is_system_table(name: str) -> bool:
    """Return True if *name* is a Power BI auto-generated internal table."""
    return name.startswith(_SYSTEM_PREFIXES)


def sanitize_identifier(name: str) -> str:
    """
    Convert any string to a safe Databricks identifier.
    Lowercases, replaces spaces / special chars with underscores,
    collapses runs of underscores, strips leading digits/underscores.
    """
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    name = name.strip("_")
    # identifiers cannot start with a digit
    if name and name[0].isdigit():
        name = "t_" + name
    return name or "table"


def pandas_dtype_to_spark(dtype) -> str:
    """Map a pandas dtype to a Databricks/Spark SQL type name."""
    if pd.api.types.is_bool_dtype(dtype):
        return "BOOLEAN"
    if pd.api.types.is_integer_dtype(dtype):
        return "BIGINT"
    if pd.api.types.is_float_dtype(dtype):
        return "DOUBLE"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "TIMESTAMP"
    return "STRING"


def escape_sql_value(val) -> str:
    """Render a Python value as a SQL literal."""
    # Catch all NA-like values first (None, NaN, NaT, pd.NA)
    try:
        if val is None or pd.isna(val):
            return "NULL"
    except (TypeError, ValueError):
        pass
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, (int, float)):
        return str(val)
    # Timestamp / date objects — guard against NaT.isoformat() raising
    if hasattr(val, "isoformat"):
        try:
            iso = val.isoformat()
            return f"TIMESTAMP '{iso}'"
        except Exception:
            return "NULL"
    s = str(val).replace("'", "''")
    # Reject literal 'NaT' / 'nan' strings that slipped through
    if s in ("NaT", "nan", "None", "<NA>"):
        return "NULL"
    return f"'{s}'"


def build_create_or_replace_ddl(catalog: str, schema: str, table: str, df: pd.DataFrame) -> str:
    """
    Build a CREATE OR REPLACE TABLE statement from a DataFrame.
    Column names are kept exactly as in the .pbix file (backtick-quoted).
    Delta Column Mapping (mode=name) is enabled so spaces and special characters
    in column names are fully supported — matching the original Power BI visuals.
    """
    cols = []
    for col in df.columns:
        spark_type = pandas_dtype_to_spark(df[col].dtype)
        safe_col = col.replace("`", "")   # only strip backticks, keep everything else
        cols.append(f"  `{safe_col}` {spark_type}")
    col_defs = ",\n".join(cols)
    return (
        f"CREATE OR REPLACE TABLE `{catalog}`.`{schema}`.`{table}`\n"
        f"(\n{col_defs}\n)\nUSING DELTA\n"
        f"TBLPROPERTIES (\n"
        f"  'delta.columnMapping.mode' = 'name',\n"
        f"  'delta.minReaderVersion' = '2',\n"
        f"  'delta.minWriterVersion' = '5'\n"
        f")"
    )


def insert_dataframe(cursor, catalog: str, schema: str, table: str, df: pd.DataFrame,
                     chunk_size: int = 500) -> int:
    """Insert all rows of *df* into the Delta table; return row count inserted.
    Column names are sanitized to match the CREATE TABLE schema.
    """
    if df.empty:
        return 0

    # Use original column names — must match what CREATE OR REPLACE TABLE used
    col_list = ", ".join(f"`{c.replace('`', '')}`" for c in df.columns)
    total = 0

    for start in range(0, len(df), chunk_size):
        chunk = df.iloc[start : start + chunk_size]
        value_rows = []
        for _, row in chunk.iterrows():
            vals = ", ".join(escape_sql_value(v) for v in row)
            value_rows.append(f"({vals})")
        values_str = ",\n".join(value_rows)
        sql = (
            f"INSERT INTO `{catalog}`.`{schema}`.`{table}` ({col_list})\n"
            f"VALUES\n{values_str}"
        )
        cursor.execute(sql)
        total += len(chunk)

    return total


def table_exists(cursor, catalog: str, schema: str, table: str) -> bool:
    """Check whether a table already exists."""
    try:
        cursor.execute(f"SHOW TABLES IN `{catalog}`.`{schema}` LIKE '{table}'")
        return len(cursor.fetchall()) > 0
    except Exception:
        return False


# ── Core logic ────────────────────────────────────────────────────────────────

def process_pbix(cursor, pbix_path: str) -> dict:
    """
    Load one .pbix file and push all its real source tables to Databricks.
    Layout: genai_demo.<file_schema>.<table>
    Returns a summary dict.
    """
    fname = os.path.basename(pbix_path)
    stem = os.path.splitext(fname)[0]
    schema = sanitize_identifier(stem)   # one schema per file inside genai_demo

    print("\n" + "="*70)
    print(f"FILE   : {fname}")
    print(f"CATALOG: {CATALOG}  |  SCHEMA: {schema}")
    print("="*70)

    summary = {
        "file": fname,
        "schema": schema,
        "tables_pushed": [],
        "tables_skipped_system": [],
        "tables_failed": [],
        "errors": [],
    }

    # ── Load pbix ────────────────────────────────────────────────────────────
    try:
        model = PBIXRay(pbix_path)
        all_tables = list(model.tables)
    except Exception as e:
        msg = f"Failed to load {fname}: {e}"
        print(f"  ERROR: {msg}")
        summary["errors"].append(msg)
        return summary

    print(f"  Total tables found by pbixray : {len(all_tables)}")

    real_tables = [t for t in all_tables if not is_system_table(t)]
    sys_tables  = [t for t in all_tables if is_system_table(t)]
    summary["tables_skipped_system"] = sys_tables

    print(f"  Real source tables            : {len(real_tables)}")
    print(f"  System tables (skipped)       : {len(sys_tables)}")

    if not real_tables:
        print("  No real tables to push -- skipping file.")
        return summary

    # ── Create schema (idempotent — catalog already exists) ──────────────────
    try:
        cursor.execute(f"CREATE SCHEMA IF NOT EXISTS `{CATALOG}`.`{schema}`")
        print(f"  Schema `{CATALOG}`.`{schema}` ready.")
    except Exception as e:
        msg = f"Could not create schema `{CATALOG}`.`{schema}`: {e}"
        print(f"  ERROR: {msg}")
        summary["errors"].append(msg)
        return summary

    # ── Push each real table ──────────────────────────────────────────────────
    for tname in real_tables:
        safe_tname = sanitize_identifier(tname)
        print(f"\n  Table: {tname!r}  =>  `{safe_tname}`")

        try:
            df = model.get_table(tname)
        except Exception as e:
            msg = f"  get_table failed for {tname!r}: {e}"
            print(f"    ERROR: {msg}")
            summary["tables_failed"].append(tname)
            summary["errors"].append(msg)
            continue

        if df is None or df.empty:
    print("    SKIP — empty / None dataframe")
            summary["tables_failed"].append(tname)
            continue

        print(f"    Rows: {len(df):,}  |  Cols: {len(df.columns)}")

        # For object columns with mixed types, keep as-is and let escape_sql_value handle each value.
        # For datetime columns, keep as datetime so escape_sql_value can render TIMESTAMP literals.
        # Drop any unnamed index columns that sneak in.
        df = df.loc[:, ~df.columns.str.match(r'^Unnamed')]

        try:
            # CREATE OR REPLACE TABLE — works on new and existing tables alike.
            # Does NOT require MANAGE/DROP privilege; only CREATE TABLE on schema.
            ddl = build_create_or_replace_ddl(CATALOG, schema, safe_tname, df)
            cursor.execute(ddl)
            print("    Table created/replaced.")

            rows_inserted = insert_dataframe(cursor, CATALOG, schema, safe_tname, df)
            print(f"    Inserted {rows_inserted:,} rows. OK")
            summary["tables_pushed"].append(safe_tname)

        except Exception as e:
            msg = f"Push failed for {tname!r}: {e}"
            print(f"    ERROR: {msg}")
            summary["tables_failed"].append(tname)
            summary["errors"].append(msg)
            traceback.print_exc()

    return summary


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    pbix_files = sorted(
        os.path.join(INPUT_DIR, f)
        for f in os.listdir(INPUT_DIR)
        if f.lower().endswith(".pbix")
    )

    if not pbix_files:
        print(f"No .pbix files found in {INPUT_DIR}")
        sys.exit(1)

    print(f"Found {len(pbix_files)} .pbix files in {INPUT_DIR}")
    print(f"Connecting to Databricks: {DATABRICKS_WORKSPACE_URL}\n")

    connection = databricks_sql.connect(
        server_hostname=DATABRICKS_WORKSPACE_URL,
        http_path=DATABRICKS_HTTP_PATH,
        access_token=DATABRICKS_ACCESS_TOKEN,
        _socket_timeout=600,
    )
    cursor = connection.cursor()

    all_summaries = []
    try:
        for pbix_path in pbix_files:
            summary = process_pbix(cursor, pbix_path)
            all_summaries.append(summary)
    finally:
        cursor.close()
        connection.close()

    # ── Final report ──────────────────────────────────────────────────────────
    print("\n\n" + "="*70)
    print("FINAL SUMMARY")
    print("="*70)
    total_pushed = 0
    total_failed = 0
    for s in all_summaries:
        pushed = len(s["tables_pushed"])
        failed = len(s["tables_failed"])
        skipped = len(s["tables_skipped_system"])
        total_pushed += pushed
        total_failed += failed
        status = "OK" if not s["errors"] else "PARTIAL" if pushed else "FAILED"
        print(
            "  [%s]  %s  =>  schema: %s  |  pushed: %d  |  failed: %d  |  sys-skipped: %d"
            % (status, s["file"], s.get("schema", "?"), pushed, failed, skipped)
        )
        for t in s["tables_pushed"]:
            print(f"           + {t}")
        for t in s["tables_failed"]:
            print(f"           x {t}  (failed)")
        for err in s["errors"]:
            print(f"           ! {err}")

    print(f"\nTotal tables pushed : {total_pushed}")
    print(f"Total tables failed : {total_failed}")
    print(f"Files processed     : {len(all_summaries)}")
    print("="*70)


if __name__ == "__main__":
    main()
