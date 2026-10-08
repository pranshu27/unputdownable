"""
create_databricks_tmp_tables.py
================================
Creates realistic-named copy tables from real source tables in Databricks.

On each run:
  Step 1 -- Drop all existing copy tables (legacy _tmp and realistic-named)
  Step 2 -- Create fresh realistic-named copies from originals

Originals are NEVER touched or dropped.

For each table:
  - Simple copy       ->  CREATE OR REPLACE TABLE ... AS SELECT * FROM original
  - With dummy cols   ->  CREATE OR REPLACE TABLE ... AS SELECT *, <cols> FROM original

Functions
---------
  get_connection()                  - open Databricks SQL connection
  get_tables_to_drop()              - list of (schema, table) to DROP IF EXISTS
  drop_old_tables(cursor)           - drop all old copies before recreating
  get_tmp_table_definitions()       - full config of all copy tables (40 tables)
  build_create_tmp_sql(...)         - generate CREATE OR REPLACE TABLE SQL
  create_tmp_table(cursor, ...)     - execute the CREATE for one table
  verify_tmp_table(cursor, ...)     - SELECT COUNT(*) to confirm rows loaded
  run_all_tmp_tables(cursor)        - drop old + loop and create all new copies
  main()                            - entry point
"""

import os
import re
from databricks import sql as databricks_sql

# Duplicate-literal constants
_SUFFIX_DATABRICKS_SM = "_databricks.SemanticModel"
_SUFFIX_SM = ".SemanticModel"

# ── Databricks connection constants ───────────────────────────────────────────
DATABRICKS_HOST       = os.getenv("DATABRICKS_WORKSPACE_URL", "dbc-9064b591-ac6c.cloud.databricks.com")
DATABRICKS_TOKEN      = os.getenv("DATABRICKS_ACCESS_TOKEN", "")
DATABRICKS_CLUSTER_ID = os.getenv("DATABRICKS_CLUSTER_ID",   "0206-091900-f4nnmzzq")
DATABRICKS_HTTP_PATH  = os.getenv("DATABRICKS_HTTP_PATH",
                                   f"/sql/protocolv1/o/0/{os.getenv('DATABRICKS_CLUSTER_ID', '0206-091900-f4nnmzzq')}")
CATALOG               = "genai_demo"
INPUT_DIR             = os.path.join(os.path.dirname(__file__), "pbib_input_files")


def _sanitize(name: str) -> str:
    """Lowercase + replace non-alphanumeric runs with underscores."""
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", "_", name).strip("_")
    return name or "table"


def _stem_from_sm_entry(entry: str) -> str:
    """Strip SemanticModel suffixes from a folder name to get the project stem."""
    stem = entry
    for suffix in (_SUFFIX_DATABRICKS_SM, _SUFFIX_SM):
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


def _find_sm_in_subfolder(entry_path: str) -> str:
    """Return the stem of the first .SemanticModel subfolder found, or empty string."""
    for sub in os.listdir(entry_path):
        if sub.endswith(_SUFFIX_SM) and os.path.isdir(os.path.join(entry_path, sub)):
            return _stem_from_sm_entry(sub)
    return ""


def get_active_schemas() -> set:
    """
    Scan pbib_input_files/ and return the set of Databricks schema names
    for PBIP projects that are actually present.
    """
    schemas = set()
    if not os.path.isdir(INPUT_DIR):
        return schemas

    for entry in os.listdir(INPUT_DIR):
        entry_path = os.path.join(INPUT_DIR, entry)
        if not os.path.isdir(entry_path):
            continue

        if entry.endswith(_SUFFIX_SM):
            # Case A: entry IS the SemanticModel folder
            schemas.add(_sanitize(_stem_from_sm_entry(entry)))
        else:
            # Case B: look one level deeper
            stem = _find_sm_in_subfolder(entry_path)
            if stem:
                schemas.add(_sanitize(stem))

    return schemas


# ─────────────────────────────────────────────────────────────────────────────
# 1. CONNECTION
# ─────────────────────────────────────────────────────────────────────────────

def get_connection():
    """Open and return a Databricks SQL connection."""
    return databricks_sql.connect(
        server_hostname=DATABRICKS_HOST,
        http_path=DATABRICKS_HTTP_PATH,
        access_token=DATABRICKS_TOKEN,
        _socket_timeout=600,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. DROP LIST
# ─────────────────────────────────────────────────────────────────────────────

def get_tables_to_drop() -> list:
    """
    Return list of (schema, table) tuples to DROP IF EXISTS before recreating.

    Includes:
      - All realistic copy tables from current definitions (dropped + recreated each run)
      - All legacy _tmp tables (one-time cleanup of old naming convention)

    Originals are NEVER in this list.
    """
    # Current realistic copy tables — dropped then recreated fresh on every run
    to_drop = [(d["schema"], d["tmp_table"]) for d in get_tmp_table_definitions()]

    # Legacy _tmp tables from old naming — clean up
    legacy_tmp = [
        ("report",                             "claims_tmp"),
        ("report",                             "policies_tmp"),
        ("insurance_data_project",             "insurancedata_tmp"),
        ("insurance_data_project",             "sheet1_tmp"),
        ("data_analyst_project_2_insurance",   "insurancedata_tmp"),
        ("insurance_analysis",                 "brokerage_tmp"),
        ("insurance_analysis",                 "fees_tmp"),
        ("insurance_analysis",                 "individual_budge_tmp"),
        ("insurance_analysis",                 "invoice_tmp"),
        ("insurance_analysis",                 "meeting_list_tmp"),
        ("insurance_analysis",                 "opportunity_tmp"),
        ("insurance_analysis",                 "placed_achivement_tmp"),
        ("insurance_cliam_power_bi",           "insurance_tmp"),
    ]
    to_drop.extend(legacy_tmp)
    return to_drop


def drop_old_tables(cursor, active_schemas: set = None) -> None:
    """
    DROP IF EXISTS every copy table for active schemas.
    If active_schemas is provided, only drops tables whose schema is in the set.
    Originals are never dropped.
    """
    all_tables = get_tables_to_drop()
    tables = [(s, t) for s, t in all_tables
              if active_schemas is None or s in active_schemas]
    print(f"Dropping {len(tables)} old copy tables (DROP IF EXISTS) ...")
    for schema, table in tables:
        try:
            cursor.execute(f"DROP TABLE IF EXISTS `{CATALOG}`.`{schema}`.`{table}`")
            print(f"  Dropped : {schema}.{table}")
        except Exception as e:
            print(f"  [WARN]  Could not drop {schema}.{table}: {e}")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# 3. TABLE DEFINITIONS  (40 tables across 16 schemas)
# ─────────────────────────────────────────────────────────────────────────────

def get_tmp_table_definitions() -> list:
    """
    Return the full list of realistic copy tables to create.

    Each entry:
      schema          : Databricks schema (inside genai_demo)
      original_table  : source table — NEVER modified
      tmp_table       : realistic name of the copy to create
      dummy_columns   : list of (col_name, col_type, sql_value)
                        Empty list = simple copy with no extra columns.

    Tables WITH dummy columns
    -------------------------
      report                           : claims_processed (2), policies_active (3)
      insurance_data_project           : insurance_core_records (3), policy_import_data (2)
      data_analyst_project_2_insurance : insurance_analyst_dataset (3)  [user requested]
      insurance_analysis               : all 7 tables get QA dummy cols  [user requested]

    All other tables are simple copies (no dummy columns).
    """
    return [
        # ── report ────────────────────────────────────────────────────────────
        {
            "schema":         "report",
            "original_table": "claims",
            "tmp_table":      "claims_processed",
            "dummy_columns": [
                ("claims_test_flag",    "STRING", "'Y'"),
                ("claims_dummy_amount", "DOUBLE", "0.0"),
            ],
        },
        {
            "schema":         "report",
            "original_table": "policies",
            "tmp_table":      "policies_active",
            "dummy_columns": [
                ("policies_test_flag",      "STRING", "'Y'"),
                ("policies_dummy_category", "STRING", "'TEST'"),
                ("policies_dummy_score",    "DOUBLE", "0.0"),
            ],
        },

        # ── insurance_data_project ────────────────────────────────────────────
        {
            "schema":         "insurance_data_project",
            "original_table": "insurancedata",
            "tmp_table":      "insurance_core_records",
            "dummy_columns": [
                ("insurancedata_test_flag",    "STRING", "'Y'"),
                ("insurancedata_review_score", "INT",    "0"),
                ("insurancedata_batch_id",     "STRING", "'BATCH_001'"),
            ],
        },
        {
            "schema":         "insurance_data_project",
            "original_table": "sheet1",
            "tmp_table":      "policy_import_data",
            "dummy_columns": [
                ("sheet1_test_flag",  "STRING", "'Y'"),
                ("sheet1_source_tag", "STRING", "'EXCEL_DUMMY'"),
            ],
        },

        # ── data_analyst_project_2_insurance ─────────────────────────────────
        {
            "schema":         "data_analyst_project_2_insurance",
            "original_table": "insurancedata",
            "tmp_table":      "insurance_analyst_dataset",
            "dummy_columns": [
                ("analyst_test_flag",    "STRING", "'Y'"),
                ("analyst_review_score", "INT",    "0"),
                ("analyst_batch_id",     "STRING", "'ANALYST_001'"),
            ],
        },

        # ── insurance_analysis (all 7 tables get QA dummy columns) ────────────
        {
            "schema":         "insurance_analysis",
            "original_table": "brokerage",
            "tmp_table":      "brokerage_performance",
            "dummy_columns": [
                ("brokerage_qa_flag",      "STRING", "'Y'"),
                ("brokerage_review_score", "DOUBLE", "0.0"),
            ],
        },
        {
            "schema":         "insurance_analysis",
            "original_table": "fees",
            "tmp_table":      "fee_schedule",
            "dummy_columns": [
                ("fees_qa_flag",         "STRING", "'Y'"),
                ("fees_adjusted_amount", "DOUBLE", "0.0"),
            ],
        },
        {
            "schema":         "insurance_analysis",
            "original_table": "individual_budge",
            "tmp_table":      "individual_budget_plan",
            "dummy_columns": [
                ("budget_qa_flag",  "STRING", "'Y'"),
                ("budget_variance", "DOUBLE", "0.0"),
            ],
        },
        {
            "schema":         "insurance_analysis",
            "original_table": "invoice",
            "tmp_table":      "invoice_records",
            "dummy_columns": [
                ("invoice_qa_flag",  "STRING", "'Y'"),
                ("invoice_audit_id", "STRING", "'AUDIT_001'"),
            ],
        },
        {
            "schema":         "insurance_analysis",
            "original_table": "meeting_list",
            "tmp_table":      "agent_meeting_log",
            "dummy_columns": [
                ("meeting_qa_flag", "STRING", "'Y'"),
            ],
        },
        {
            "schema":         "insurance_analysis",
            "original_table": "opportunity",
            "tmp_table":      "sales_opportunity_pipeline",
            "dummy_columns": [
                ("opportunity_qa_flag",        "STRING", "'Y'"),
                ("opportunity_priority_score", "DOUBLE", "0.0"),
            ],
        },
        {
            "schema":         "insurance_analysis",
            "original_table": "placed_achivement",
            "tmp_table":      "placement_achievement_records",
            "dummy_columns": [
                ("achievement_qa_flag", "STRING", "'Y'"),
            ],
        },

        # ── insurance_cliam_power_bi ──────────────────────────────────────────
        {
            "schema":         "insurance_cliam_power_bi",
            "original_table": "insurance",
            "tmp_table":      "insurance_claims_summary",
            "dummy_columns": [],
        },

        # ── carpro_auto_insurance_dashboard  (no dummy — user specified) ──────
        {
            "schema":         "carpro_auto_insurance_dashboard",
            "original_table": "worksheet",
            "tmp_table":      "carpro_policy_records",
            "dummy_columns": [],
        },

        # ── dashboard  (no dummy — user specified) ────────────────────────────
        {
            "schema":         "dashboard",
            "original_table": "worksheet",
            "tmp_table":      "dashboard_policy_data",
            "dummy_columns": [],
        },

        # ── insurance_and_sentiment_analysis ──────────────────────────────────
        {
            "schema":         "insurance_and_sentiment_analysis",
            "original_table": "insurancedata",
            "tmp_table":      "sentiment_insurance_data",
            "dummy_columns": [],
        },
        {
            "schema":         "insurance_and_sentiment_analysis",
            "original_table": "sheet1",
            "tmp_table":      "sentiment_policy_sheet",
            "dummy_columns": [],
        },

        # ── insurance_claim_analysis ──────────────────────────────────────────
        {
            "schema":         "insurance_claim_analysis",
            "original_table": "insurance",
            "tmp_table":      "claim_analysis_records",
            "dummy_columns": [],
        },

        # ── insurance_claims ──────────────────────────────────────────────────
        {
            "schema":         "insurance_claims",
            "original_table": "insurance_data",
            "tmp_table":      "claims_insurance_data",
            "dummy_columns": [],
        },
        {
            "schema":         "insurance_claims",
            "original_table": "processed_insurance_data",
            "tmp_table":      "claims_processed_records",
            "dummy_columns": [],
        },

        # ── insurance_dashboard ───────────────────────────────────────────────
        {
            "schema":         "insurance_dashboard",
            "original_table": "insurancedata",
            "tmp_table":      "dashboard_insurance_data",
            "dummy_columns": [],
        },
        {
            "schema":         "insurance_dashboard",
            "original_table": "sheet1",
            "tmp_table":      "dashboard_policy_sheet",
            "dummy_columns": [],
        },

        # ── insurance_data_analysis ───────────────────────────────────────────
        {
            "schema":         "insurance_data_analysis",
            "original_table": "insurance",
            "tmp_table":      "data_analysis_insurance",
            "dummy_columns": [],
        },

        # ── insurance_data_analysis_project ───────────────────────────────────
        {
            "schema":         "insurance_data_analysis_project",
            "original_table": "insurancedata",
            "tmp_table":      "analysis_project_insurance",
            "dummy_columns": [],
        },

        # ── shield_insurance ──────────────────────────────────────────────────
        {
            "schema":         "shield_insurance",
            "original_table": "dim_customer",
            "tmp_table":      "shield_customer_dim",
            "dummy_columns": [],
        },
        {
            "schema":         "shield_insurance",
            "original_table": "dim_date",
            "tmp_table":      "shield_date_dim",
            "dummy_columns": [],
        },
        {
            "schema":         "shield_insurance",
            "original_table": "dim_policies",
            "tmp_table":      "shield_policies_dim",
            "dummy_columns": [],
        },
        {
            "schema":         "shield_insurance",
            "original_table": "fact_premiums",
            "tmp_table":      "shield_premiums_fact",
            "dummy_columns": [],
        },
        {
            "schema":         "shield_insurance",
            "original_table": "fact_settlements",
            "tmp_table":      "shield_settlements_fact",
            "dummy_columns": [],
        },

        # ── tru_secure_credebit_dashboard ─────────────────────────────────────
        {
            "schema":         "tru_secure_credebit_dashboard",
            "original_table": "dm_customer_detail_table",
            "tmp_table":      "tru_customer_details",
            "dummy_columns": [],
        },
        {
            "schema":         "tru_secure_credebit_dashboard",
            "original_table": "dm_insurance_agent_table",
            "tmp_table":      "tru_insurance_agents",
            "dummy_columns": [],
        },
        {
            "schema":         "tru_secure_credebit_dashboard",
            "original_table": "dm_policy_protection_plan",
            "tmp_table":      "tru_policy_protection",
            "dummy_columns": [],
        },
        {
            "schema":         "tru_secure_credebit_dashboard",
            "original_table": "dm_policy_type",
            "tmp_table":      "tru_policy_types",
            "dummy_columns": [],
        },
        {
            "schema":         "tru_secure_credebit_dashboard",
            "original_table": "dm_regional_manager",
            "tmp_table":      "tru_regional_managers",
            "dummy_columns": [],
        },
        {
            "schema":         "tru_secure_credebit_dashboard",
            "original_table": "dm_zonal_manager",
            "tmp_table":      "tru_zonal_managers",
            "dummy_columns": [],
        },
        {
            "schema":         "tru_secure_credebit_dashboard",
            "original_table": "fct_insurance_policy_table",
            "tmp_table":      "tru_insurance_policies",
            "dummy_columns": [],
        },
        {
            "schema":         "tru_secure_credebit_dashboard",
            "original_table": "hirarachy_table",
            "tmp_table":      "tru_hierarchy_data",
            "dummy_columns": [],
        },
        {
            "schema":         "tru_secure_credebit_dashboard",
            "original_table": "region",
            "tmp_table":      "tru_region_data",
            "dummy_columns": [],
        },

        # ── worksafebc_dashboard ──────────────────────────────────────────────
        {
            "schema":         "worksafebc_dashboard",
            "original_table": "all_reported_fatalities_and_inj",
            "tmp_table":      "wsbc_fatalities_injuries",
            "dummy_columns": [],
        },
        {
            "schema":         "worksafebc_dashboard",
            "original_table": "claims_by_regional_district_2017",
            "tmp_table":      "wsbc_regional_claims_2017",
            "dummy_columns": [],
        },
        {
            "schema":         "worksafebc_dashboard",
            "original_table": "claims_cost_by_sector_and_subsector_2017",
            "tmp_table":      "wsbc_sector_claims_cost",
            "dummy_columns": [],
        },
        {
            "schema":         "worksafebc_dashboard",
            "original_table": "numbe_of_claims_and_days_lost_2017",
            "tmp_table":      "wsbc_claims_days_lost_2017",
            "dummy_columns": [],
        },
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 4. SQL BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_create_tmp_sql(catalog: str, schema: str,
                          original_table: str, tmp_table: str,
                          dummy_columns: list) -> str:
    """
    Build CREATE OR REPLACE TABLE ... USING DELTA ... AS SELECT ... SQL.

    Delta Column Mapping (mode=name) is always enabled so columns with
    spaces or special characters are preserved exactly from the source.

    Simple copy:      SELECT * FROM genai_demo.<schema>.<original>
    With dummy cols:  SELECT *, 'Y' AS flag, 0.0 AS score FROM ...
    """
    src  = f"`{catalog}`.`{schema}`.`{original_table}`"
    dest = f"`{catalog}`.`{schema}`.`{tmp_table}`"

    if dummy_columns:
        extra = ", ".join(f"{val} AS `{col}`" for col, _, val in dummy_columns)
        select_clause = f"SELECT *, {extra}"
    else:
        select_clause = "SELECT *"

    return (
        f"CREATE OR REPLACE TABLE {dest}\n"
        f"USING DELTA\n"
        f"TBLPROPERTIES (\n"
        f"  'delta.columnMapping.mode' = 'name',\n"
        f"  'delta.minReaderVersion' = '2',\n"
        f"  'delta.minWriterVersion' = '5'\n"
        f")\n"
        f"AS {select_clause}\n"
        f"FROM {src}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. CREATE ONE TABLE
# ─────────────────────────────────────────────────────────────────────────────

def create_tmp_table(cursor, catalog: str, schema: str,
                      original_table: str, tmp_table: str,
                      dummy_columns: list) -> None:
    """Execute CREATE OR REPLACE TABLE for one copy table."""
    label = "simple copy" if not dummy_columns else f"{len(dummy_columns)} dummy col(s)"
    print(f"    Creating `{schema}`.`{tmp_table}` ({label}) ...")
    sql = build_create_tmp_sql(catalog, schema, original_table, tmp_table, dummy_columns)
    cursor.execute(sql)
    print(f"    OK -- `{schema}`.`{tmp_table}` created.")


# ─────────────────────────────────────────────────────────────────────────────
# 6. VERIFY ONE TABLE
# ─────────────────────────────────────────────────────────────────────────────

def verify_tmp_table(cursor, catalog: str, schema: str, tmp_table: str) -> int:
    """Run SELECT COUNT(*) and return row count. Returns -1 on failure."""
    try:
        cursor.execute(f"SELECT COUNT(*) FROM `{catalog}`.`{schema}`.`{tmp_table}`")
        row = cursor.fetchone()
        return int(row[0]) if row else 0
    except Exception as e:
        print(f"    [WARN] Could not verify `{schema}`.`{tmp_table}`: {e}")
        return -1


# ─────────────────────────────────────────────────────────────────────────────
# 7. RUN ALL
# ─────────────────────────────────────────────────────────────────────────────

def run_all_tmp_tables(cursor) -> dict:
    """
    Step 1: Drop all old copy tables (legacy _tmp + existing realistic copies).
    Step 2: Create all realistic copy tables fresh from originals.

    Returns summary dict: {"created": [...], "failed": [...]}.
    """
    # Detect which schemas have active PBIP input files — only process those
    active_schemas = get_active_schemas()
    print(f"Active schemas from pbib_input_files/ : {sorted(active_schemas)}\n")

    # Step 1 — drop old copies for active schemas only
    drop_old_tables(cursor, active_schemas)

    # Step 2 — create fresh copies for active schemas only
    definitions = [d for d in get_tmp_table_definitions()
                   if d["schema"] in active_schemas]
    summary = {"created": [], "failed": []}
    print(f"Total copy tables to create: {len(definitions)}\n")

    for defn in definitions:
        schema         = defn["schema"]
        original_table = defn["original_table"]
        tmp_table      = defn["tmp_table"]
        dummy_columns  = defn["dummy_columns"]

        print(f"  [{schema}]  {original_table} -> {tmp_table}")
        try:
            create_tmp_table(cursor, CATALOG, schema,
                             original_table, tmp_table, dummy_columns)
            row_count = verify_tmp_table(cursor, CATALOG, schema, tmp_table)
            print(f"    Verified: {row_count:,} rows\n")
            summary["created"].append((schema, tmp_table, row_count))
        except Exception as e:
            msg = str(e)
            print(f"    ERROR: {msg}\n")
            summary["failed"].append((schema, tmp_table, msg))

    return summary


# ─────────────────────────────────────────────────────────────────────────────
# 8. MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("Databricks Copy Table Creator")
    print("=" * 70)
    print(f"Host    : {DATABRICKS_HOST}")
    print(f"Catalog : {CATALOG}")
    print()

    connection = get_connection()
    cursor     = connection.cursor()

    try:
        summary = run_all_tmp_tables(cursor)
    finally:
        cursor.close()
        connection.close()

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Created : {len(summary['created'])}")
    print(f"  Failed  : {len(summary['failed'])}")

    if summary["created"]:
        print("\n  Created tables:")
        for schema, table, rows in summary["created"]:
            row_str = f"{rows:,}" if rows >= 0 else "unknown"
            print(f"    + {schema}.{table}  ({row_str} rows)")

    if summary["failed"]:
        print("\n  Failed tables:")
        for schema, table, err in summary["failed"]:
            print(f"    x {schema}.{table}  -- {err}")

    print("=" * 70)


if __name__ == "__main__":
    main()
