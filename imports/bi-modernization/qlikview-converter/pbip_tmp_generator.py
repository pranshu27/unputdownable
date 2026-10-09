"""
pbip_tmp_generator.py
=====================
For each PBIP project found in pbib_input_files/ this script:

  1. Copies the full project structure to pbip_output_files/<project>/
  2. For every REAL SOURCE TABLE (M-query partition):
       - Copies the original <TableName>.tmdl unchanged
       - Creates a new <TableName>_tmp.tmdl that:
           * Renames the table  ->  <TableName>_tmp
           * Renames the partition  ->  <TableName>_tmp
           * Replaces the M-query source with a DatabricksMultiCloud.Catalogs
             query pointing to genai_demo.<schema>.<tablename>_tmp
  3. Skips _tmp creation for:
       - Power BI system tables  (DateTableTemplate_*, LocalDateTable_*)
       - DAX calculated tables   (partition ... = calculated)
     These are still copied as-is.

Functions
---------
  sanitize_identifier(name)               - safe Databricks identifier
  is_system_table_file(filename)          - detect system table by filename prefix
  is_calculated_table(content)            - detect DAX calculated table by content
  extract_table_name(content)             - parse 'table <Name>' from first TMDL line
  extract_databricks_schema(content)      - pull schema from existing Databricks M source
  build_databricks_m_source(...)          - generate DatabricksMultiCloud.Catalogs M block
  replace_partition_source(...)           - swap source block inside TMDL content
  redirect_original_to_tmp(...)          - keep table name, redirect source to _tmp table
  find_pbip_projects(input_dir)           - discover all SemanticModel folders
  copy_non_table_files(src, dst)          - mirror project minus the tables/ folder
  process_table_files(...)               - handle one SemanticModel's tables/ folder
  process_pbip_project(info, output_dir)  - orchestrate one full PBIP project
  main()                                  - entry point
"""

import os
import re
import shutil
import sys
import uuid

# Duplicate-literal constants
_SUFFIX_DATABRICKS_SM = "_databricks.SemanticModel"
_SUFFIX_SM = ".SemanticModel"

# ── Databricks connection constants ───────────────────────────────────────────
DATABRICKS_HOST      = "dbc-9064b591-ac6c.cloud.databricks.com"
DATABRICKS_HTTP_PATH = "sql/protocolv1/o/845104949723771/0206-091900-f4nnmzzq"
DATABRICKS_CATALOG   = "genai_demo"

# Power BI internal table name prefixes — always skipped
_SYSTEM_PREFIXES = ("DateTableTemplate_", "LocalDateTable_")

INPUT_DIR  = os.path.join(os.path.dirname(__file__), "pbib_input_files")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "pbip_output_files")

# ── Realistic copy table name map ────────────────────────────────────────────
# Key   : (schema_name_lowercase, original_table_name_lowercase)
# Value : exact Databricks table name for the realistic copy
# Power BI UI still shows the original table name — only the source query changes.
REALISTIC_TABLE_MAP = {
    # report
    ("report",                             "claims"):                        "claims_processed",
    ("report",                             "policies"):                      "policies_active",
    # insurance_data_project
    ("insurance_data_project",             "insurancedata"):                 "insurance_core_records",
    ("insurance_data_project",             "sheet1"):                        "policy_import_data",
    # data_analyst_project_2_insurance
    ("data_analyst_project_2_insurance",   "insurancedata"):                 "insurance_analyst_dataset",
    # insurance_analysis
    ("insurance_analysis",                 "brokerage"):                     "brokerage_performance",
    ("insurance_analysis",                 "fees"):                          "fee_schedule",
    ("insurance_analysis",                 "individual_budge"):              "individual_budget_plan",
    ("insurance_analysis",                 "invoice"):                       "invoice_records",
    ("insurance_analysis",                 "meeting_list"):                  "agent_meeting_log",
    ("insurance_analysis",                 "opportunity"):                   "sales_opportunity_pipeline",
    ("insurance_analysis",                 "placed_achivement"):             "placement_achievement_records",
    # insurance_cliam_power_bi
    ("insurance_cliam_power_bi",           "insurance"):                     "insurance_claims_summary",
    # CLIENT_A_auto_insurance_dashboard
    ("CLIENT_A_auto_insurance_dashboard",    "worksheet"):                     "CLIENT_A_policy_records",
    # dashboard
    ("dashboard",                          "worksheet"):                     "dashboard_policy_data",
    # insurance_and_sentiment_analysis
    ("insurance_and_sentiment_analysis",   "insurancedata"):                 "sentiment_insurance_data",
    ("insurance_and_sentiment_analysis",   "sheet1"):                        "sentiment_policy_sheet",
    # insurance_claim_analysis
    ("insurance_claim_analysis",           "insurance"):                     "claim_analysis_records",
    # insurance_claims
    ("insurance_claims",                   "insurance_data"):                "claims_insurance_data",
    ("insurance_claims",                   "processed_insurance_data"):      "claims_processed_records",
    # insurance_dashboard
    ("insurance_dashboard",                "insurancedata"):                 "dashboard_insurance_data",
    ("insurance_dashboard",                "sheet1"):                        "dashboard_policy_sheet",
    # insurance_data_analysis
    ("insurance_data_analysis",            "insurance"):                     "data_analysis_insurance",
    # insurance_data_analysis_project
    ("insurance_data_analysis_project",    "insurancedata"):                 "analysis_project_insurance",
    # shield_insurance
    ("shield_insurance",                   "dim_customer"):                  "shield_customer_dim",
    ("shield_insurance",                   "dim_date"):                      "shield_date_dim",
    ("shield_insurance",                   "dim_policies"):                  "shield_policies_dim",
    ("shield_insurance",                   "fact_premiums"):                 "shield_premiums_fact",
    ("shield_insurance",                   "fact_settlements"):              "shield_settlements_fact",
    # tru_secure_credebit_dashboard
    ("tru_secure_credebit_dashboard",      "dm_customer_detail_table"):      "tru_customer_details",
    ("tru_secure_credebit_dashboard",      "dm_insurance_agent_table"):      "tru_insurance_agents",
    ("tru_secure_credebit_dashboard",      "dm_policy_protection_plan"):     "tru_policy_protection",
    ("tru_secure_credebit_dashboard",      "dm_policy_type"):                "tru_policy_types",
    ("tru_secure_credebit_dashboard",      "dm_regional_manager"):           "tru_regional_managers",
    ("tru_secure_credebit_dashboard",      "dm_zonal_manager"):              "tru_zonal_managers",
    ("tru_secure_credebit_dashboard",      "fct_insurance_policy_table"):    "tru_insurance_policies",
    ("tru_secure_credebit_dashboard",      "hirarachy_table"):               "tru_hierarchy_data",
    ("tru_secure_credebit_dashboard",      "region"):                        "tru_region_data",
    # worksafebc_dashboard
    ("worksafebc_dashboard",               "all_reported_fatalities_and_inj"):             "wsbc_fatalities_injuries",
    ("worksafebc_dashboard",               "claims_by_regional_district_2017"):            "wsbc_regional_claims_2017",
    ("worksafebc_dashboard",               "claims_cost_by_sector_and_subsector_2017"):    "wsbc_sector_claims_cost",
    ("worksafebc_dashboard",               "numbe_of_claims_and_days_lost_2017"):          "wsbc_claims_days_lost_2017",
}

# ── Dummy column config ───────────────────────────────────────────────────────
# Key   : (schema_name, original_table_name_lowercase)
# Value : list of (col_name, tmdl_dataType, summarizeBy)
#         tmdl_dataType matches TMDL syntax: string / double / int64
#
# These 4 tables get extra dummy columns in both Databricks (_tmp table)
# and in the generated _tmp TMDL file.  All other tables are simple copies.
DUMMY_COLUMNS_CONFIG = {
    # report
    ("report", "claims"): [
        ("claims_test_flag",    "string", "none"),
        ("claims_dummy_amount", "double", "sum"),
    ],
    ("report", "policies"): [
        ("policies_test_flag",      "string", "none"),
        ("policies_dummy_category", "string", "none"),
        ("policies_dummy_score",    "double", "sum"),
    ],
    # insurance_data_project
    ("insurance_data_project", "insurancedata"): [
        ("insurancedata_test_flag",    "string", "none"),
        ("insurancedata_review_score", "int64",  "sum"),
        ("insurancedata_batch_id",     "string", "none"),
    ],
    ("insurance_data_project", "sheet1"): [
        ("sheet1_test_flag",  "string", "none"),
        ("sheet1_source_tag", "string", "none"),
    ],
    # data_analyst_project_2_insurance  [user requested dummy cols]
    ("data_analyst_project_2_insurance", "insurancedata"): [
        ("analyst_test_flag",    "string", "none"),
        ("analyst_review_score", "int64",  "sum"),
        ("analyst_batch_id",     "string", "none"),
    ],
    # insurance_analysis  [user requested dummy cols for all 7 tables]
    ("insurance_analysis", "brokerage"): [
        ("brokerage_qa_flag",      "string", "none"),
        ("brokerage_review_score", "double", "sum"),
    ],
    ("insurance_analysis", "fees"): [
        ("fees_qa_flag",         "string", "none"),
        ("fees_adjusted_amount", "double", "sum"),
    ],
    ("insurance_analysis", "individual_budge"): [
        ("budget_qa_flag",  "string", "none"),
        ("budget_variance", "double", "sum"),
    ],
    ("insurance_analysis", "invoice"): [
        ("invoice_qa_flag",  "string", "none"),
        ("invoice_audit_id", "string", "none"),
    ],
    ("insurance_analysis", "meeting_list"): [
        ("meeting_qa_flag", "string", "none"),
    ],
    ("insurance_analysis", "opportunity"): [
        ("opportunity_qa_flag",        "string", "none"),
        ("opportunity_priority_score", "double", "sum"),
    ],
    ("insurance_analysis", "placed_achivement"): [
        ("achievement_qa_flag", "string", "none"),
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# 1. IDENTIFIER HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def sanitize_identifier(name: str) -> str:
    """
    Convert any string to a safe, lowercase Databricks identifier.
    Replaces spaces / special chars with underscores and strips leading digits.
    """
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    name = name.strip("_")
    if name and name[0].isdigit():
        name = "t_" + name
    return name or "table"


# ─────────────────────────────────────────────────────────────────────────────
# 2. TABLE CLASSIFICATION
# ─────────────────────────────────────────────────────────────────────────────

def is_system_table_file(filename: str) -> bool:
    """
    Return True when the .tmdl filename belongs to a Power BI system table.
    System tables are identified purely by their filename prefix:
      - DateTableTemplate_<uuid>.tmdl
      - LocalDateTable_<uuid>.tmdl
    """
    stem = os.path.splitext(filename)[0]
    return stem.startswith(_SYSTEM_PREFIXES)


def is_calculated_table(content: str) -> bool:
    """
    Return True when the TMDL represents a DAX calculated table.
    DAX calculated tables have a partition of type 'calculated', e.g.:
        partition calculations = calculated
    Real M-query tables always have:
        partition <name> = m
    """
    return bool(re.search(
        r'^\s*partition\s+\S.*=\s*calculated\s*$',
        content,
        re.MULTILINE
    ))


# ─────────────────────────────────────────────────────────────────────────────
# 3. TMDL CONTENT PARSING
# ─────────────────────────────────────────────────────────────────────────────

def extract_table_name(content: str) -> str:
    """
    Parse the table name from the first line of a TMDL file.
    TMDL first line format:  table <TableName>
    Returns an empty string if the line cannot be parsed.
    """
    match = re.match(r'^\s*table\s+(.+)', content)
    return match.group(1).strip() if match else ""


def extract_databricks_schema(content: str) -> str:
    """
    Extract the schema name from an existing DatabricksMultiCloud.Catalogs M source.
    Looks for the M-query pattern:
        {[Name="<schema>",Kind="Schema"]}

    Returns an empty string when the table does not already use a Databricks source
    (e.g., Sql.Database / Excel.Workbook sources).
    """
    match = re.search(r'\[Name="([^"]+)",Kind="Schema"\]', content)
    return match.group(1) if match else ""


# ─────────────────────────────────────────────────────────────────────────────
# 4. DATABRICKS M-SOURCE BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_databricks_m_source(table_name: str, schema_name: str,
                               exclude_columns: list = None) -> str:
    """
    Build the M-query 'let ... in' block for a DatabricksMultiCloud.Catalogs source.

    Parameters
    ----------
    table_name      : sanitized Databricks table name (e.g. 'claims_tmp')
    schema_name     : Databricks schema name           (e.g. 'report')
    exclude_columns : optional list of column names to strip via Table.RemoveColumns.
                      Used on the redirected original table so dummy columns from the
                      _tmp Databricks table do not appear in the original table's field list.
    """
    safe_table  = sanitize_identifier(table_name)
    safe_schema = sanitize_identifier(schema_name)

    schema_var  = f"{safe_schema}_Schema"
    table_var   = f"{safe_table}_Table"
    catalog_var = f"{DATABRICKS_CATALOG}_Database"

    T  = '\t' * 4          # 4 tabs  -- 'let' / 'in'
    TS = '\t' * 4 + '    ' # 4 tabs + 4 spaces -- variable lines

    connector = (
        f'DatabricksMultiCloud.Catalogs("{DATABRICKS_HOST}", '
        f'"{DATABRICKS_HTTP_PATH}", '
        f'[Catalog=null, Database=null, QueryTags=null, '
        f'EnableAutomaticProxyDiscovery=null, Implementation="2.0", '
        f'MetricViewBiCompatibilityMode=null])'
    )

    lines = [
        f"{T}let",
        f"{TS}Source = {connector},",
        f'{TS}{catalog_var} = Source{{[Name="{DATABRICKS_CATALOG}",Kind="Database"]}}[Data],',
        f'{TS}{schema_var} = {catalog_var}{{[Name="{safe_schema}",Kind="Schema"]}}[Data],',
        f'{TS}{table_var} = {schema_var}{{[Name="{safe_table}",Kind="Table"]}}[Data]',
    ]

    if exclude_columns:
        col_list = ", ".join(f'"{c}"' for c in exclude_columns)
        filtered_var = f"{safe_table}_Filtered"
        # Replace the last line (no trailing comma) and add RemoveColumns step
        lines[-1] = lines[-1] + ","
        lines.append(f'{TS}{filtered_var} = Table.RemoveColumns({table_var}, {{{col_list}}})')
        lines += [f"{T}in", f"{TS}{filtered_var}"]
    else:
        lines += [f"{T}in", f"{TS}{table_var}"]

    return '\n'.join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# 5. PARTITION SOURCE REPLACEMENT
# ─────────────────────────────────────────────────────────────────────────────

def replace_partition_source(content: str, new_source: str,
                              original_table_name: str, tmp_table_name: str) -> str:
    """
    Modify a TMDL string in two steps:

    Step A -- Rename the partition:
        'partition <original_table_name> = m'
        ->  'partition <tmp_table_name> = m'

    Step B -- Replace the source block:
        Scans line-by-line.  When the 'source =' line is found, it appends
        'new_source' and then skips every subsequent line that belongs to the
        old source block.  The source block ends at the first blank line
        (which in TMDL separates a partition from the next annotation).
    """
    # ── Step A: rename partition ──────────────────────────────────────────────
    content = re.sub(
        rf'(partition\s+){re.escape(original_table_name)}(\s*=\s*m\b)',
        rf'\g<1>{tmp_table_name}\g<2>',
        content
    )

    # ── Step B: replace source block line-by-line ─────────────────────────────
    lines           = content.split('\n')
    result          = []
    in_source_block = False

    for line in lines:
        if not in_source_block:
            # Detect the "source =" line (indented with one or more tabs)
            if re.match(r'^\t+source\s*=\s*$', line):
                in_source_block = True
                result.append(line)       # keep 'source ='
                result.append(new_source) # insert new M query
            else:
                result.append(line)
        else:
            # We are inside the old source block.
            # A blank line signals the end of the source block in TMDL.
            if line == '':
                in_source_block = False
                result.append(line)  # preserve the blank separator
            # Non-blank lines are old source content -- skip them.

    return '\n'.join(result)


# ─────────────────────────────────────────────────────────────────────────────
# 6a. DUMMY COLUMN TMDL BLOCK BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_dummy_column_tmdl(col_name: str, data_type: str, summarize_by: str) -> str:
    """
    Build a single TMDL column block for a dummy column.

    Example output:
        \tcolumn claims_test_flag
        \t\tdataType: string
        \t\tlineageTag: <new-uuid>
        \t\tsummarizeBy: none
        \t\tsourceColumn: claims_test_flag
        \n
        \t\tannotation SummarizationSetBy = Automatic
    """
    tag = str(uuid.uuid4())
    fmt_line = ""
    if data_type in ("double", "int64"):
        fmt_line = "\t\tformatString: 0\n"

    return (
        f"\tcolumn {col_name}\n"
        f"\t\tdataType: {data_type}\n"
        f"{fmt_line}"
        f"\t\tlineageTag: {tag}\n"
        f"\t\tsummarizeBy: {summarize_by}\n"
        f"\t\tsourceColumn: {col_name}\n"
        f"\n"
        f"\t\tannotation SummarizationSetBy = Automatic\n"
    )


def replace_all_lineage_tags(content: str) -> str:
    """
    Replace EVERY lineageTag value in a TMDL file with a fresh UUID.

    Power BI requires all lineage tags to be globally unique across the entire
    model.  When we copy a TMDL to create a _tmp version, the tags are
    identical to the original — causing a 'lineage-tag already exists' error
    when Power BI Desktop tries to load both tables.

    This replaces every occurrence of:
        lineageTag: <uuid>
    with a new randomly generated UUID, making the _tmp table fully independent.
    """
    return re.sub(
        r'(lineageTag:\s*)[0-9a-f\-]{36}',
        lambda m: m.group(1) + str(uuid.uuid4()),
        content,
    )


def strip_variation_blocks(content: str) -> str:
    """
    Remove all 'variation' blocks from TMDL content.

    Variation blocks define date hierarchy drill-down relationships that link
    a date/time column to its corresponding LocalDateTable_* via a specific
    relationship ID.  Those relationships are defined on the ORIGINAL table
    only — the _tmp table has no such relationships, so Power BI throws:
        "The relationship for Variation must be defined on the current table"

    A variation block is indented at 2 tabs inside a column (3+ tabs for body):
        \\t\\tvariation Variation
            \\t\\t\\tisDefault
            \\t\\t\\trelationship: <uuid>
            \\t\\t\\tdefaultHierarchy: LocalDateTable_xxx.'Date Hierarchy'

    The block ends at the first blank line or line with fewer than 3 tabs.
    """
    lines = content.split('\n')
    result = []
    in_variation = False

    for line in lines:
        if not in_variation:
            if re.match(r'^\t\tvariation\s', line):
                in_variation = True   # skip this line and body
            else:
                result.append(line)
        else:
            # End of variation block: blank line or back to ≤2-tab indentation
            if line == '' or not re.match(r'^\t{3}', line):
                in_variation = False
                result.append(line)
            # else: still inside variation block — skip

    return '\n'.join(result)


def get_dummy_columns_for_table(schema_name: str, original_table_name: str) -> list:
    """
    Look up DUMMY_COLUMNS_CONFIG and return the dummy column list for this table.
    Returns an empty list if the table is a simple copy with no dummy columns.

    Lookup key uses lowercase schema and original table name.
    """
    bare = (original_table_name[1:-1]
            if original_table_name.startswith("'") and original_table_name.endswith("'")
            else original_table_name)
    key = (schema_name.lower(), sanitize_identifier(bare))
    return DUMMY_COLUMNS_CONFIG.get(key, [])


# ─────────────────────────────────────────────────────────────────────────────
# 6b. ORIGINAL TABLE REDIRECT
# ─────────────────────────────────────────────────────────────────────────────

def redirect_original_to_tmp(content: str, table_name: str,
                               schema_name: str,
                               exclude_columns: list = None) -> str:
    """
    Redirect the original table's M source to its _tmp counterpart in Databricks,
    while keeping the table name and partition name UNCHANGED.

    exclude_columns: dummy column names to strip from the loaded data so they
    do not appear in the original table's field list (only the _tmp table should
    show dummy columns).
    """
    # Strip TMDL quotes before looking up: 'Placed Achivement' -> placed_achivement
    bare_name = table_name[1:-1] if (table_name.startswith("'") and table_name.endswith("'")) else table_name
    key = (schema_name.lower(), sanitize_identifier(bare_name))
    # Look up realistic copy name from map; fall back to sanitized name + "_copy"
    realistic_table = REALISTIC_TABLE_MAP.get(key, sanitize_identifier(bare_name) + "_copy")
    new_source = build_databricks_m_source(
        table_name=realistic_table,
        schema_name=schema_name,
        exclude_columns=exclude_columns or [],
    )
    # Pass original_table_name == table_name so Step A (partition rename)
    # is a no-op; only Step B (source replacement) actually runs.
    return replace_partition_source(content, new_source, table_name, table_name)


# ─────────────────────────────────────────────────────────────────────────────
# 6c. _TMP TMDL BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_tmp_tmdl(original_content: str, original_table_name: str,
                   schema_name: str) -> str:
    """
    Produce the complete TMDL content for a <TableName>_tmp table.

    What changes vs the original:
      - 'table <Name>'          ->  'table <Name>_tmp'
      - 'partition <Name> = m'  ->  'partition <Name>_tmp = m'
      - M-query source block    ->  DatabricksMultiCloud.Catalogs pointing to
                                    genai_demo.<schema>.<tablename_lowercase>_tmp

    All columns, measures, lineageTags, annotations, etc. are preserved unchanged.

    Parameters
    ----------
    original_content    : raw text of the original .tmdl file
    original_table_name : table name as written in the tmdl (exact case)
    schema_name         : Databricks schema to use (e.g. 'report', 'insurance_analysis')
    """
    # TMDL quotes names that contain spaces: 'Placed Achivement'
    # The _tmp suffix must go INSIDE the quotes: 'Placed Achivement_tmp'
    if original_table_name.startswith("'") and original_table_name.endswith("'"):
        bare_name      = original_table_name[1:-1]
        tmp_table_name = f"'{bare_name}_tmp'"
        safe_tmp_table = sanitize_identifier(bare_name + "_tmp")
    else:
        tmp_table_name = original_table_name + "_tmp"
        safe_tmp_table = sanitize_identifier(tmp_table_name)

    # 1. Replace ALL lineage tags with new UUIDs so Power BI sees them as unique
    content = replace_all_lineage_tags(original_content)

    # 2. Remove variation blocks — they reference relationships tied to the
    #    original table only; keeping them causes Power BI to reject the _tmp table
    content = strip_variation_blocks(content)

    # 3. Rename the table declaration on the very first line
    content = re.sub(
        r'^(\s*table\s+)' + re.escape(original_table_name),
        r'\g<1>' + tmp_table_name,
        content,
        count=1,
        flags=re.MULTILINE
    )

    # 3. Build the new Databricks M source for the _tmp table
    new_source = build_databricks_m_source(
        table_name=safe_tmp_table,
        schema_name=schema_name,
    )

    # 3. Replace partition name + source block
    content = replace_partition_source(
        content, new_source, original_table_name, tmp_table_name
    )

    # 4. Inject dummy column definitions just before the partition block
    dummy_cols = get_dummy_columns_for_table(schema_name, original_table_name)
    if dummy_cols:
        dummy_blocks = "".join(
            build_dummy_column_tmdl(col, dtype, sumby)
            for col, dtype, sumby in dummy_cols
        )
        # Insert before "partition <name>_tmp = m"
        content = re.sub(
            rf'(\tpartition\s+{re.escape(tmp_table_name)}\s*=\s*m)',
            dummy_blocks + r'\1',
            content,
        )

    return content


# ─────────────────────────────────────────────────────────────────────────────
# 7. PROJECT DISCOVERY
# ─────────────────────────────────────────────────────────────────────────────

def _strip_sm_suffix(name: str) -> str:
    """Strip known SemanticModel suffixes and return the bare stem."""
    for suffix in (_SUFFIX_DATABRICKS_SM, _SUFFIX_SM):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _make_project_entry(sm_dir: str, project_root: str, output_name: str, stem: str) -> dict:
    return {
        "semantic_model_dir": sm_dir,
        "project_root":       project_root,
        "output_name":        output_name,
        "schema_name":        sanitize_identifier(stem),
    }


def _find_nested_sm(entry_path: str, output_name: str) -> dict | None:
    """Case B: locate the first SemanticModel subfolder inside a project folder."""
    for sub in os.listdir(entry_path):
        if not sub.endswith(_SUFFIX_SM):
            continue
        sm_path = os.path.join(entry_path, sub)
        if os.path.isdir(sm_path):
            return _make_project_entry(sm_path, entry_path, output_name, _strip_sm_suffix(sub))
    return None


def find_pbip_projects(input_dir: str) -> list:
    """
    Discover every PBIP SemanticModel inside input_dir.

    Handles two layouts:
      Case A -- SemanticModel folder sits directly in input_dir:
                  input_dir/report.SemanticModel/

      Case B -- SemanticModel folder is nested inside a project folder:
                  input_dir/Insurance Analysis/
                      Insurance Analysis_databricks.SemanticModel/

    Returns a list of dicts:
      {
        'semantic_model_dir' : absolute path to the *.SemanticModel folder
        'project_root'       : absolute path to the outer project folder (= sm_dir for Case A)
        'output_name'        : folder name to use under OUTPUT_DIR
        'schema_name'        : Databricks schema derived from the project/model name
      }
    """
    projects = []

    for entry in os.listdir(input_dir):
        entry_path = os.path.join(input_dir, entry)
        if not os.path.isdir(entry_path):
            continue

        if entry.endswith(_SUFFIX_SM):
            # Case A: entry IS the SemanticModel folder
            projects.append(_make_project_entry(entry_path, entry_path, entry, _strip_sm_suffix(entry)))
        else:
            # Case B: entry is an outer project folder
            nested = _find_nested_sm(entry_path, entry)
            if nested:
                projects.append(nested)

    return projects


# ─────────────────────────────────────────────────────────────────────────────
# 8. FILE COPY HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def copy_non_table_files(src_model_dir: str, dst_model_dir: str) -> None:
    """
    Recursively copy every file from src_model_dir to dst_model_dir,
    SKIPPING the definition/tables/ sub-folder (processed separately).
    """
    tables_abs = os.path.join(src_model_dir, "definition", "tables")

    for root, dirs, files in os.walk(src_model_dir):
        # Skip the tables directory — processed by process_table_files()
        if os.path.abspath(root) == os.path.abspath(tables_abs):
            dirs.clear()
            continue

        rel      = os.path.relpath(root, src_model_dir)
        dst_root = os.path.join(dst_model_dir, rel)
        os.makedirs(dst_root, exist_ok=True)

        for fname in files:
            shutil.copy2(
                os.path.join(root, fname),
                os.path.join(dst_root, fname),
            )


# ─────────────────────────────────────────────────────────────────────────────
# 9. TABLE FILE PROCESSING
# ─────────────────────────────────────────────────────────────────────────────

def process_table_files(tables_src_dir: str, tables_dst_dir: str,
                        fallback_schema: str) -> dict:
    """
    Process every .tmdl file inside a SemanticModel's definition/tables/ folder.

    Rules
    -----
    - System table  (DateTableTemplate_* / LocalDateTable_*):
        Copy as-is.  No _tmp version.

    - DAX calculated table  (partition ... = calculated):
        Copy as-is.  No _tmp version.

    - Real source table  (partition ... = m):
        Copy original as-is  (sources original Databricks table — visible for comparison).
        Also write <TableName>_tmp.tmdl:
          * Table / partition renamed to <TableName>_tmp
          * Source replaced with Databricks M query pointing to <tablename>_tmp
          * Visuals should bind to this _tmp table for results

    The Databricks schema is extracted from an existing Databricks source if
    present, otherwise derived from the project folder name.

    Returns a summary dict.
    """
    os.makedirs(tables_dst_dir, exist_ok=True)
    summary = {"as_is": [], "redirected": [], "skipped": []}

    tmdl_files = sorted(f for f in os.listdir(tables_src_dir) if f.endswith(".tmdl"))

    for filename in tmdl_files:
        src_path = os.path.join(tables_src_dir, filename)

        with open(src_path, encoding="utf-8") as fh:
            content = fh.read()

        dst_path = os.path.join(tables_dst_dir, filename)

        # ── Classify table ────────────────────────────────────────────────────
        if is_system_table_file(filename):
            shutil.copy2(src_path, dst_path)
            print(f"    [SYSTEM]    {filename}  (copied as-is, no _tmp)")
            summary["as_is"].append(filename)
            continue

        if is_calculated_table(content):
            shutil.copy2(src_path, dst_path)
            print(f"    [DAX CALC]  {filename}  (copied as-is, no _tmp)")
            summary["as_is"].append(filename)
            continue

        # ── Real M-query table ────────────────────────────────────────────────
        table_name = extract_table_name(content)
        if not table_name:
            shutil.copy2(src_path, dst_path)
            print(f"    [WARN]      {filename}  -- could not parse table name, skipping _tmp")
            summary["skipped"].append(filename)
            continue

        # Prefer schema from existing Databricks source; fall back to project schema
        existing_schema  = extract_databricks_schema(content)
        effective_schema = existing_schema if existing_schema else fallback_schema

        # Redirect M source to realistic copy in Databricks; keep table name unchanged
        redirected_content = redirect_original_to_tmp(content, table_name, effective_schema)

        # If this table has dummy columns, inject their TMDL definitions
        # so they appear in the Power BI field list
        dummy_cols = get_dummy_columns_for_table(effective_schema, table_name)
        if dummy_cols:
            dummy_blocks = "".join(
                build_dummy_column_tmdl(col, dtype, sumby)
                for col, dtype, sumby in dummy_cols
            )
            redirected_content = re.sub(
                rf'(\tpartition\s+{re.escape(table_name)}\s*=\s*m)',
                dummy_blocks + r'\1',
                redirected_content,
            )

        with open(dst_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(redirected_content)

        schema_note  = existing_schema if existing_schema else f"{fallback_schema} (derived)"
        dummy_note   = f"  [{len(dummy_cols)} dummy col(s)]" if dummy_cols else ""
        print(f"    [REAL]      {filename}  (schema: {schema_note}){dummy_note}")
        summary["redirected"].append(filename)

    return summary


# ─────────────────────────────────────────────────────────────────────────────
# 10. PROJECT ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────

def process_pbip_project(project_info: dict, output_base_dir: str) -> None:
    """
    Process one complete PBIP project:

    1. Determine output paths (mirrors input structure under output_base_dir).
    2. Copy all non-table files (model.tmdl, relationships.tmdl, cultures/, etc.)
    3. Process and generate table .tmdl files (original + _tmp copies).
    4. Copy any other files at the outer project root (.pbip, Report/ folder, etc.)
    """
    sm_src        = project_info["semantic_model_dir"]
    project_root  = project_info["project_root"]
    output_name   = project_info["output_name"]
    fallback_schema = project_info["schema_name"]

    sm_folder_name = os.path.basename(sm_src)
    dst_project    = os.path.join(output_base_dir, output_name)
    dst_sm         = os.path.join(dst_project, sm_folder_name)

    print(f"  SemanticModel : {sm_src}")
    print(f"  Output path   : {dst_sm}")
    print(f"  Fallback schema: {fallback_schema}")

    # Step 1 -- Copy non-table files (model.tmdl, relationships, cultures, etc.)
    copy_non_table_files(sm_src, dst_sm)
    print("  Non-table files copied.")

    # Step 2 -- Process table files
    tables_src = os.path.join(sm_src, "definition", "tables")
    tables_dst = os.path.join(dst_sm, "definition", "tables")

    if os.path.isdir(tables_src):
        summary = process_table_files(tables_src, tables_dst, fallback_schema)
        print(f"  Tables copied as-is : {len(summary['as_is'])}")
        print(f"  Tables redirected   : {len(summary['redirected'])}")
        if summary["skipped"]:
            print(f"  Skipped             : {summary['skipped']}")
    else:
        print("  [WARN] No tables/ folder found -- nothing to process.")

    # Step 3 -- Copy any other files at the outer project root
    if os.path.abspath(project_root) != os.path.abspath(sm_src):
        for entry in os.listdir(project_root):
            src_entry = os.path.join(project_root, entry)
            dst_entry = os.path.join(dst_project, entry)
            if os.path.abspath(src_entry) == os.path.abspath(sm_src):
                continue  # already handled
            if os.path.isdir(src_entry):
                shutil.copytree(src_entry, dst_entry, dirs_exist_ok=True)
            else:
                os.makedirs(dst_project, exist_ok=True)
                shutil.copy2(src_entry, dst_entry)
        print("  Outer project files copied.")


# ─────────────────────────────────────────────────────────────────────────────
# 11. MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    projects = find_pbip_projects(INPUT_DIR)

    if not projects:
        print(f"No PBIP projects found in {INPUT_DIR}")
        sys.exit(1)

    print(f"Found {len(projects)} PBIP project(s) in {INPUT_DIR}")
    print(f"Output -> {OUTPUT_DIR}\n")

    # Clear previous output so every run is fresh
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for proj in projects:
        print("=" * 70)
        print(f"PROJECT: {proj['output_name']}")
        process_pbip_project(proj, OUTPUT_DIR)

    print("\n" + "=" * 70)
    print(f"Done.  Modified PBIP files are in: {OUTPUT_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    main()
