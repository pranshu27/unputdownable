"""
Databricks Writer: Inserts normalized rows into Databricks Delta tables.
Auto-creates tables if they don't exist.
"""

import os
from typing import Any, Dict, List
from databricks import sql as databricks_sql
from create_databricks_tables import DDL_STATEMENTS, TABLE_NAMES

DATABRICKS_WORKSPACE_URL = os.getenv("DATABRICKS_WORKSPACE_URL", "dbc-9064b591-ac6c.cloud.databricks.com")
DATABRICKS_ACCESS_TOKEN = os.getenv("DATABRICKS_ACCESS_TOKEN", "")
DATABRICKS_CLUSTER_ID = os.getenv("DATABRICKS_CLUSTER_ID", "0206-091900-f4nnmzzq")
DATABRICKS_HTTP_PATH = os.getenv("DATABRICKS_HTTP_PATH", f"/sql/protocolv1/o/0/{DATABRICKS_CLUSTER_ID}")
CATALOG = os.getenv("DATABRICKS_CATALOG", "genai_demo")
SCHEMA = os.getenv("DATABRICKS_SCHEMA", "jnj_bi_modernization")


def _get_connection():
    return databricks_sql.connect(
        server_hostname=DATABRICKS_WORKSPACE_URL,
        http_path=DATABRICKS_HTTP_PATH,
        access_token=DATABRICKS_ACCESS_TOKEN,
        _socket_timeout=300,  # 5 min — allows cluster cold-start (~3-7 min)
    )


def _get_name_attr(obj: Any) -> str:
    """Return the first non-empty tableName/table_name value from an object or dict, or ''."""
    for key in ("tableName", "table_name"):
        value = obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)
        if value:
            return str(value)
    return ""


def _extract_table_name(row: Any) -> str:
    """Handle different row shapes returned by the Databricks SQL connector."""
    result = _get_name_attr(row)
    if result:
        return result

    if hasattr(row, "asDict"):
        result = _get_name_attr(row.asDict())
        if result:
            return result

    if isinstance(row, (tuple, list)) and len(row) >= 2:
        return str(row[1])

    return ""


def _ensure_tables_exist(cursor):
    """Check if tables exist; create any that are missing."""
    # Ensure schema exists before listing tables.
    cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")

    # Get existing tables
    cursor.execute(f"SHOW TABLES IN {CATALOG}.{SCHEMA}")
    existing_tables = {
        name.lower()
        for name in (_extract_table_name(row) for row in cursor.fetchall())
        if name
    }

    missing = [name for name in TABLE_NAMES if name.lower() not in existing_tables]

    if not missing:
        print("  All 17 tables already exist.")
        return

    print(f"  Missing {len(missing)} tables: {missing}")
    print("  Creating missing tables...")

    # Create only the missing tables
    table_ddl_map = dict(zip(TABLE_NAMES, DDL_STATEMENTS))
    failed_creates = []
    for table_name in missing:
        try:
            cursor.execute(table_ddl_map[table_name])
            print(f"    Created {table_name}")
        except Exception as e:
            msg = f"Failed to create {table_name}: {e}"
            print(f"    {msg}")
            failed_creates.append(msg)

    if failed_creates:
        raise RuntimeError("Table creation failed: " + " | ".join(failed_creates))


def _escape_sql_value(val: Any) -> str:
    """Escape a value for SQL INSERT."""
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, (int, float)):
        return str(val)
    # String — escape single quotes
    s = str(val).replace("'", "''")
    return f"'{s}'"


def _build_insert_sql(table_name: str, rows: List[dict]) -> str:
    """Build a single INSERT INTO ... VALUES (...), (...) statement."""
    if not rows:
        return ""
    columns = list(rows[0].keys())
    col_names = ", ".join(columns)

    value_rows = []
    for row in rows:
        vals = ", ".join(_escape_sql_value(row.get(c)) for c in columns)
        value_rows.append(f"({vals})")

    values_str = ",\n".join(value_rows)
    return f"INSERT INTO {CATALOG}.{SCHEMA}.{table_name} ({col_names}) VALUES\n{values_str}"


# Ordered list of tables to insert (parent tables first for FK integrity)
TABLE_INSERT_ORDER = [
    "bi_reports",
    "data_sources",
    "tables_model",
    "columns_metadata",
    "relationships",
    "transformations",
    "calculations",
    "dashboards",
    "dashboard_components",
    "visualizations",
    "viz_chart_mappings",
    "viz_table_columns",
    "viz_data_bindings",
    "filters",
    "parameters_variables",
    "hierarchies",
    "rls_policies",
]


def write_to_databricks(normalized_data: Dict[str, List[dict]]) -> Dict[str, Any]:
    """
    Insert all normalized rows into Databricks.
    If tables don't exist, creates them first.

    Args:
        normalized_data: Dict from normalizer — keys are table names, values are lists of row dicts.

    Returns:
        Summary dict with counts and status.
    """
    connection = _get_connection()
    cursor = connection.cursor()

    summary = {"stored": False, "tables_written": [], "row_counts": {}, "errors": []}

    try:
        # Step 1: Ensure all tables exist (create if missing)
        print("Checking Databricks tables...")
        _ensure_tables_exist(cursor)

        # Step 2: Insert data into tables
        for table_name in TABLE_INSERT_ORDER:
            rows = normalized_data.get(table_name, [])
            if not rows:
                continue

            try:
                # Batch inserts in chunks of 500 rows to reduce round trips
                chunk_size = 500
                total_inserted = 0
                for i in range(0, len(rows), chunk_size):
                    chunk = rows[i:i + chunk_size]
                    sql = _build_insert_sql(table_name, chunk)
                    if sql:
                        cursor.execute(sql)
                        total_inserted += len(chunk)

                summary["tables_written"].append(table_name)
                summary["row_counts"][table_name] = total_inserted
                print(f"  Inserted {total_inserted} rows into {CATALOG}.{SCHEMA}.{table_name}")
            except Exception as e:
                error_msg = f"Error inserting into {table_name}: {str(e)}"
                print(f"  {error_msg}")
                summary["errors"].append(error_msg)

        summary["stored"] = len(summary["errors"]) == 0
        report_rows = normalized_data.get("bi_reports", [])
        if report_rows:
            summary["report_id"] = report_rows[0].get("report_id", "")

    finally:
        cursor.close()
        connection.close()

    return summary
