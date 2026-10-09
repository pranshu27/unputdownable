"""
Power BI Extraction Prompts
Define prompts for each extraction type to guide the LLM in parsing Power BI metadata
"""

_MULTILINGUAL_PREAMBLE = """
IMPORTANT: The input may contain non-English text including Japanese (CJK characters), 
Arabic, or other Unicode scripts. You MUST:
- Preserve all non-English names (table names, column names, measure names, page titles) 
  exactly as-is in the output JSON — do NOT translate or transliterate them.
- Provide an English translation/description in the "description" field where applicable.
- Never substitute Unicode escape sequences (\\uXXXX) for actual characters — keep the 
  original Unicode characters in all string fields.
"""

EXTRACTION_PROMPTS = {
    "metadata": _MULTILINGUAL_PREAMBLE + """
You are a Power BI metadata extraction specialist.
Extract the following information from the provided Power BI metadata JSON:
- File size and model information
- Model name
- Last refresh date (if available)
- Any other relevant metadata

Return a JSON object with the following structure:
{
    "name": "model or report name extracted from metadata",
    "extracted_at": "ISO 8601 datetime of last refresh if available, else null"
}
""",

    "tables": _MULTILINGUAL_PREAMBLE + """
You are a Power BI table extraction specialist.
Extract information about all tables from the provided tables list JSON.

Return a JSON object with the following structure:
{
    "tables": [
        {
            "name": "table name",
            "source_object": "source table/view name if different",
            "is_calculated": false
        }
    ]
}
""",

    "power_query": _MULTILINGUAL_PREAMBLE + """
You are a Power Query (M code) extraction specialist.

You will receive a merged JSON containing:
- "power_query": M expressions for each table
- "m_parameters": M parameters (if present)
- "dax_tables": DAX-calculated tables. These have NO M expression because they
  are computed from DAX. You MUST still emit a synthetic data_source for each
  one (excluding auto LocalDateTable_/DateTableTemplate_ entries) so downstream
  tables[] entries with table_type "calculated" can link to it via
  source_data_source_id.

Your task is to:
1. Identify data sources (connections to databases, files, APIs, etc.)
2. Extract transformation steps applied to each table
3. Use M parameters to enrich data source information
4. For every entry in dax_tables — INCLUDING auto-date tables whose names start
   with "LocalDateTable_" or "DateTableTemplate_" (the tables_and_schema agent
   now emits these in tables[] and needs their data_source to resolve) — emit
   an additional data_sources[] entry:
     {
       "id": "ds_<snake_case_table_name>_calculated",
       "name": "<original table name> (DAX calculated)",
       "source_type": "DAX_CALCULATED",
       "connection_mode": "calculated",
       "authentication_method": null,
       "server": null, "database": null, "schema": null, "path": null,
       "gateway": null, "refresh_frequency": null
     }
   Slug rules (must match the slug used in tables_and_schema/relationships):
     1. Insert "_" at every lowercase->uppercase boundary (camelCase split)
     2. Replace spaces / non-alphanumerics with "_"
     3. Lowercase everything; collapse repeats; strip leading/trailing "_"
   e.g. "Revenue Daywise"      -> "ds_revenue_daywise_calculated"
        "CustomerCountPerDay"  -> "ds_customer_count_per_day_calculated"
   The slug must match the source_data_source_id used by the calculated table
   in the tables_and_schema output.

Do not skip any transformations for brievity

For DATA SOURCES, extract:
- name: The SHORT source name only — for files use the filename with extension
  (e.g. "dim_date.csv"), NOT the full directory path. For database sources use
  the table/view name or connection display name. The full file path or
  connection string goes in the "path" field below — never duplicate it into
  "name".
- source_type: Type of source (e.g., "SQL Server", "Snowflake", "Excel", "CSV", "Web API", "SharePoint", "Azure", "Oracle", "PostgreSQL", etc.)
- server: Server address if applicable (from connection strings or parameters)
- database: Database name if applicable
- fields : List of the columns names 
- schema: Schema name if applicable
- connection_mode: "import" (default for Power Query) or "direct_query" if specified
- authentication_method: Authentication type if mentioned (e.g., "Windows", "Database", "OAuth", "Anonymous")
- gateway: Gateway name if mentioned
- refresh_frequency: Refresh schedule if mentioned

For TRANSFORMATION STEPS, extract:
- table_name: Name of the table being transformed
- step_type: One of: "merge", "append", "filter", "derive", "aggregate", "join", "pivot", "unpivot", "group", "sort", "remove_columns", "rename", "change_type", "replace_value", "split_column", "custom"
- description: Human-readable description of what this step does
- expression: The M code expression for this step (if available)

IMPORTANT: Parse M code patterns like:
- Source = Sql.Database(...) → SQL Server data source
- Source = Snowflake.Databases(...) → Snowflake data source
- Source = Excel.Workbook(...) → Excel data source
- Source = Csv.Document(...) → CSV data source
- Source = Web.Contents(...) → Web API data source
- Source = SharePoint.Files(...) → SharePoint data source
- Source = AzureStorage.Blobs(...) → Azure Blob data source
- Table.SelectRows(...) → filter transformation
- Table.AddColumn(...) → derive transformation
- Table.Join(...) or Table.NestedJoin(...) → merge transformation
- Table.Combine(...) → append transformation
- Table.Group(...) → aggregate transformation

Use M parameters to fill in server, database, or other connection details if they reference parameters.

Return a JSON object with the following structure:
{
    "data_sources": [
        {
            "id": "ds_<lowercase_snake_case_name>",
            "name": "source name",
            "source_type": "SQL Server",
            "server": "server.database.windows.net",
            "database": "DatabaseName",
            "schema": "dbo",
            "path": null,
            "connection_mode": "import",
            "authentication_method": "Database",
            "gateway": null,
            "refresh_frequency": null
        }
    ],
    "tables": [
        {
            "name": "TableName",
            "ingestion": {
                "steps": [
                    {
                        "order": 1,
                        "step_type": "powerquery_full",
                        "description": "Full Power Query M body for this table (let ... in ...)",
                        "native_expressions": {
                            "powerquery": "let\\n    Source = Sql.Database(\\"server\\", \\"db\\"),\\n    Filtered = Table.SelectRows(Source, each [Year] >= 2020)\\nin\\n    Filtered"
                        }
                    }
                ]
            }
        }
    ]
}

CRITICAL — M BODY MUST BE A COMPLETE `let ... in ...` STRING:
Power BI tables sometimes reference OTHER tables / queries in their M (e.g.
`Source = #"Other Query"`, `Table.NestedJoin(... #"Lookup", ...)`,
`Table.Combine({...})`). These dependencies only resolve when the consumer
receives the COMPLETE `let ... in ...` body in a SINGLE string.

Do NOT split the body into per-step fragments under separate
native_expressions.powerquery values — downstream consumers overwrite
on each step and end up with only the LAST fragment, which is not a valid
M body. Result: M-referenced tables fail to load.

For EACH table from power_query.json:
  - Emit ONE ingestion.steps entry whose native_expressions.powerquery is the
    full M body for that table — verbatim from power_query.json, INCLUDING
    the surrounding `let ... in ...` wrapper.
  - step_type = "powerquery_full".
  - description = a one-line summary derived from the body.

Do not split the body for "brevity". The body must be complete and unmodified
so #"Other Query" references resolve at the consumer.

If no data sources are found, return empty array for "data_sources".
If no tables or transformation steps are found, return empty array for "tables".
""",

    "dax_calculations": _MULTILINGUAL_PREAMBLE + """
You are a DAX calculations extraction specialist.

You will receive a merged JSON containing:
- "dax_measures": DAX measures  ← YOUR INPUT
- "dax_columns": Calculated columns (provided for CONTEXT only — do NOT emit)
- "dax_tables": Calculated tables (provided for CONTEXT only — do NOT emit)
- "schema":     Column definitions with data types
- "bim_model":  BIM model with measures including exact format strings

SCOPE — what `calculations[]` contains:
  calculations[] is ONLY for MEASURES from dax_measures.json.
  DO NOT emit entries for calculated columns or calculated tables here.
    - Calculated columns are emitted on tables[<table>].columns[<col>].expression
      by the calculated_tables agent + a deterministic post-pass; they MUST NOT
      also appear in calculations[].
    - Calculated tables are emitted as full tables[] entries by the
      calculated_tables agent.
  If you emit calc-column rows in calculations[], a deterministic post-pass
  will strip them (so it's safe — but adds no signal). Don't.

Your task is to:
1. Extract every DAX measure as a calculations[] entry — one entry per
   dax_measures.json row, no duplicates, no skips.
2. Identify dependencies (which columns/measures each calculation reads).
3. Classify aggregation types (SUM, AVERAGE, COUNT, CALCULATE, etc.).
4. Determine if calculations are reusable metrics.

For each DAX MEASURE, extract:
- name: Measure name (exact from dax_measures.Name)
- home_table: The table the measure LIVES on in the model — copy verbatim from
  dax_measures.TableName for this measure. This is NOT necessarily a table
  referenced in the DAX body. Example: a measure 'TotalRevenue' may live on
  table 'CustomerCountPerDay' but reference 'Revenue Daywise'[Revenue]. The
  home_table is 'CustomerCountPerDay'. NEVER infer home_table from
  depends_on_columns — always copy from dax_measures.TableName.
- expressions.dax: Full DAX expression
- depends_on_columns: Array of "Table.Column" references used in the expression
- depends_on_measures: Array of measure names referenced via [MeasureName]
- semantic_type, aggregation_behavior: per the lists below

IMPORTANT: Parse DAX patterns to identify dependencies:
- 'TableName'[ColumnName] → dependency on TableName.ColumnName
- RELATED('TableName'[ColumnName]) → dependency via relationship
- CALCULATE(...) → complex calculation, identify all column references
- SUMX, AVERAGEX, COUNTX → iterator functions, identify table and column references
- [MeasureName] → dependency on another measure

Return a JSON object with the following structure:
{
    "calculations": [
        {
            "id": "calc_total_sales",
            "name": "Total Sales",
            "home_table": "Sales",
            "description": "Sum of all sales amounts in the filtered context",
            "semantic_type": "sum",
            "aggregation_behavior": "additive",
            "data_type": "decimal",
            "format_string": "#,##0.00",
            "is_base_measure": true,
            "reusable": true,
            "depends_on_columns": ["Sales.Amount"],
            "depends_on_measures": [],
            "display": {
                "folder": "Sales KPIs",
                "hidden": false,
                "tags": ["sales", "base"]
            },
            "expressions": {
                "dax": "SUM('Sales'[Amount])"
            }
        },
        {
            "id": "calc_sales_yoy_growth",
            "name": "Sales YoY Growth",
            "home_table": "Sales",
            "description": "Year-over-year growth rate for sales",
            "semantic_type": "ratio",
            "aggregation_behavior": "non_additive",
            "data_type": "decimal",
            "format_string": "0.00%;-0.00%;0.00%",
            "is_base_measure": false,
            "reusable": false,
            "depends_on_columns": ["Sales.Amount", "Date.Year"],
            "depends_on_measures": ["Total Sales", "Total Sales PY"],
            "display": {
                "folder": "Sales KPIs",
                "hidden": false,
                "tags": ["sales", "growth"]
            },
            "expressions": {
                "dax": "DIVIDE([Total Sales] - [Total Sales PY], [Total Sales PY])"
            }
        }
    ]
}

For semantic_type use one of: "sum", "count", "average", "min", "max", "ratio", "growth_rate", "count_distinct", "calculated", "custom"
For aggregation_behavior use one of: "additive" (safe to sum across all dimensions), "non_additive" (ratios, percentages, CAGR), "semi_additive" (only some dimensions)

FORMAT STRING — CRITICAL:
Source-of-truth priority for format_string:
  1. bim_model.json — find the measure in bim_model["tables"][*]["measures"] by name,
     copy "format_string" EXACTLY (Power BI semicolon-separated tri-part strings like
     "0.00%;-0.00%;0.00%" must keep ALL three parts — never truncate to "0.00%").
  2. dax_measures.json FormatString — only if bim_model is missing or doesn't list
     the measure. Copy verbatim.
  3. INFER from the measure when both sources are empty:
     - semantic_type ∈ {ratio, growth_rate} AND name contains "%" → "0.00%;-0.00%;0.00%"
     - semantic_type ∈ {ratio, growth_rate} (no %) → "0.00"
     - data_type == "integer" AND semantic_type ∈ {sum, count, count_distinct} → "0"
     - data_type == "decimal" AND semantic_type ∈ {sum, average, min, max} → "#,##0.00"
     - Otherwise → ""
  4. If still nothing, emit "" (empty string), not null.

SELF-CHECK before returning:
  - calculations[] contains MEASURES ONLY — no calc columns, no calc tables.
  - Every measure in dax_measures.json has exactly one entry in calculations[].
  - Every entry's `home_table` matches the dax_measures.TableName for that measure.
""",

    "tables_and_schema": _MULTILINGUAL_PREAMBLE + """
You are a Power BI table and schema extraction specialist.

You will receive a merged JSON containing:
- "tables_list": List of all tables in the model
- "schema":      Column definitions per table
- "bim_model":   BIM model with clean data types (most accurate source)

SCOPE: emit only IMPORTED / Power Query tables here (the ones that have rows
in schema.json). DAX-calculated tables — including user calc tables
(CustomerCountPerDay, Revenue Daywise, …) and auto-date tables
(LocalDateTable_<guid>, DateTableTemplate_<guid>) — are handled by a separate
'calculated_tables' agent. Do NOT emit those here.

Your task is to:
1. Create TableMetadata objects with embedded ColumnMetadata
2. Identify key columns (used in relationships, filters, grouping)
3. Classify data types correctly
4. Mark hidden columns
5. SKIP any table whose name starts with "LocalDateTable_" or
   "DateTableTemplate_" — those are auto-date tables emitted elsewhere.
6. SKIP any table not present in schema.json (those are DAX-calculated tables
   handled by the calculated_tables agent).

For each TABLE, extract:
- name: Table name
- source_object: Source table/view name if different
- row_count_estimate: Estimated row count if available
- is_materialized: Whether it's an imported table (true) or calculated (false)
- columns: Array of ColumnMetadata objects

For each COLUMN, extract:
- name: Column name
- source_column: Source column name if different
- data_type: Read from bim_model.json first (most accurate source):
  1. Find the matching table in bim_model["tables"] by table name
  2. Find the matching column by column name
  3. Use that column's "data_type" field directly — already normalised to: "integer", "decimal", "string", "datetime", "boolean", "unknown"
  4. If bim_model is absent or column not found, fall back to schema.json "data_type" field
  NEVER infer data_type from column names.
- nullable: Whether nulls are allowed
- hidden: Whether column is hidden in report view
- used_in_relationships: true if this column is part of a relationship
- used_in_filters: true if commonly used in filters
- used_in_groupby: true if commonly used for grouping
- used_in_calculations: true if referenced in DAX
- distinct_count_high: true if cardinality is high (potential key column)

Return a JSON object with the following structure:
{
    "tables": [
        {
            "id": "tbl_sales",
            "name": "Sales",
            "table_type": "fact",
            "source_data_source_id": null,
            "is_materialized": true,
            "description": "Central sales fact table",
            "columns": [
                {
                    "name": "SalesID",
                    "data_type": "integer",
                    "nullable": false,
                    "hidden": false,
                    "semantic_role": "identifier",
                    "used_in_relationships": true,
                    "used_in_filters": false,
                    "used_in_groupby": false,
                    "used_in_calculations": false,
                    "distinct_count_high": true,
                    "description": "Primary key"
                },
                {
                    "name": "Amount",
                    "data_type": "decimal",
                    "nullable": false,
                    "hidden": false,
                    "semantic_role": "measure",
                    "used_in_relationships": false,
                    "used_in_filters": false,
                    "used_in_groupby": false,
                    "used_in_calculations": true,
                    "distinct_count_high": false,
                    "description": "Sales amount"
                }
            ]
        }
    ]
}

For table_type use one of: "fact", "dimension", "bridge", "lookup", "calculated"
For semantic_role use one of: "primary_key", "foreign_key", "measure", "dimension", "date", "identifier"
""",

    "calculated_tables": _MULTILINGUAL_PREAMBLE + """
You are a Power BI CALCULATED-TABLE extraction specialist. Single focused task:
turn every entry in dax_tables.json into a tables[] entry.

You will receive a merged JSON containing:
- "dax_tables":  List of DAX-calculated tables as {"TableName": ..., "Expression": ...}.
                 Includes BOTH user calc tables (CustomerCountPerDay, Revenue Daywise, …)
                 AND Power BI auto-date tables (LocalDateTable_<guid>, DateTableTemplate_<guid>).
- "dax_columns": List of DAX-defined columns as {"TableName": ..., "ColumnName": ..., "Expression": ...}.

INVARIANT: emit ONE tables[] entry for EVERY entry in dax_tables, no exceptions,
no duplicates. The TableName field is your source of truth — use it verbatim.

For EACH dax_tables entry, emit:
{
  "id":   "tbl_<snake>",
  "name": "<TableName verbatim, including spaces and GUIDs>",
  "table_type": "calculated",
  "is_materialized": false,
  "source_data_source_id": "ds_<snake>_calculated",
  "description": "<one-line, derived from the DAX>",
  "columns": [ ...see column rules below... ],
  "hierarchies": [ ...see hierarchy rules below... ],
  "ingestion": {
    "steps": [{
      "step_type": "dax_calculated_table",
      "native_expressions": {
        "dax": "<dax_tables.Expression VERBATIM — do NOT shorten, paraphrase, or change>"
      }
    }]
  }
}

SLUG RULE for tbl_<snake> and ds_<snake>_calculated:
  1. Insert "_" at every lowercase->uppercase boundary (camelCase split)
  2. Replace spaces / non-alphanumerics with "_"
  3. Lowercase everything
  4. Collapse repeats; strip leading/trailing "_"
Examples:
  "CustomerCountPerDay"  -> "tbl_customer_count_per_day"
  "Revenue Daywise"      -> "tbl_revenue_daywise"
  "LocalDateTable_cc4a15a4-36f1-492a-91a0-f955ff637c2d"
                         -> "tbl_local_date_table_cc4a15a4_36f1_492a_91a0_f955ff637c2d"

DAX BODY RULE (issue #2 we keep hitting):
  native_expressions.dax MUST be the dax_tables.Expression value VERBATIM for
  that entry. Do not shuffle expressions across entries — each TableName has
  exactly ONE Expression in the input; copy them in the SAME pairing.
  Never emit "" for a body. Never under the key "powerquery".

COLUMNS — auto-date tables (TableName starts with "LocalDateTable_" or
"DateTableTemplate_"):
  ALWAYS emit the 7 standard columns Power BI materializes (regardless of what
  dax_columns says):
    {"name": "Date",      "data_type": "datetime", "semantic_role": "date",      "nullable": false, "hidden": false, "used_in_relationships": false, "used_in_filters": false, "used_in_groupby": false, "used_in_calculations": false, "distinct_count_high": true,  "description": "Auto-date Date"},
    {"name": "Year",      "data_type": "integer",  "semantic_role": "dimension", "nullable": false, "hidden": false, "used_in_relationships": false, "used_in_filters": true,  "used_in_groupby": true,  "used_in_calculations": false, "distinct_count_high": false, "description": "Auto-date Year"},
    {"name": "MonthNo",   "data_type": "integer",  "semantic_role": "dimension", "nullable": false, "hidden": false, "used_in_relationships": false, "used_in_filters": false, "used_in_groupby": true,  "used_in_calculations": false, "distinct_count_high": false, "description": "Auto-date Month number"},
    {"name": "Month",     "data_type": "string",   "semantic_role": "dimension", "nullable": false, "hidden": false, "used_in_relationships": false, "used_in_filters": true,  "used_in_groupby": true,  "used_in_calculations": false, "distinct_count_high": false, "description": "Auto-date Month name"},
    {"name": "QuarterNo", "data_type": "integer",  "semantic_role": "dimension", "nullable": false, "hidden": false, "used_in_relationships": false, "used_in_filters": false, "used_in_groupby": true,  "used_in_calculations": false, "distinct_count_high": false, "description": "Auto-date Quarter number"},
    {"name": "Quarter",   "data_type": "string",   "semantic_role": "dimension", "nullable": false, "hidden": false, "used_in_relationships": false, "used_in_filters": false, "used_in_groupby": true,  "used_in_calculations": false, "distinct_count_high": false, "description": "Auto-date Quarter label"},
    {"name": "Day",       "data_type": "integer",  "semantic_role": "dimension", "nullable": false, "hidden": false, "used_in_relationships": false, "used_in_filters": false, "used_in_groupby": true,  "used_in_calculations": false, "distinct_count_high": false, "description": "Auto-date Day"}

COLUMNS — user calc tables (e.g. SUMMARIZE / ADDCOLUMNS / SELECTCOLUMNS):
  Parse the DAX body. Output columns are derived from BOTH:
    a) Grouping columns: 'Table'[Col] references that appear BEFORE the first
       quoted "Name" literal. Each becomes a column with the same name; the
       data_type matches the source column's type (look it up from the
       grouping table where you can; otherwise "unknown").
    b) New columns: each quoted "Name" literal followed by an expression is a
       new column. Infer data_type from the function:
         DISTINCTCOUNT / COUNT* / COUNTROWS / COUNTX  -> integer
         SUM / SUMX                                   -> integer (or decimal if the source col is decimal)
         AVERAGE / AVERAGEX / DIVIDE                  -> decimal
         otherwise                                    -> unknown
  Example for SUMMARIZE('fact_premiums', 'fact_premiums'[date], "Revenue", SUMX(...)):
    columns: [
      {"name": "date",    "data_type": "datetime", "semantic_role": "date"},
      {"name": "Revenue", "data_type": "integer",  "semantic_role": "measure"}
    ]

COLUMNS — FIELD PARAMETER tables:
  Detect by DAX shape: the body is a brace-enclosed list of (label, NAMEOF(...), index)
  tuples, e.g.
      { ("Annual Amount Growth", NAMEOF('FCT'[Annual Amount Growth]), 0),
        ("Annual ROI",            NAMEOF('FCT'[Annual ROI]),            1) }
  Power BI Field Parameters always have the SAME 3-column canonical shape, with
  column names DERIVED FROM THE TABLE NAME (not invented by you, not "Parameter" /
  "ColumnName" / "Index"):
    1. "<TableName>"        — label column, sourceColumn lineage [Value1]
                              visible, dimension, sort_by_column = "<TableName> Order"
    2. "<TableName> Fields" — NAMEOF reference column, hidden, sort_by_column = "<TableName> Order"
                              carries parameter_metadata = {"version": 3, "kind": 2}
    3. "<TableName> Order"  — sort-order integer column, hidden, format_string "0"
  Example for table 'Visual-Parameter':
    columns: [
      {"name": "Visual-Parameter",        "data_type": "string",  "hidden": false,
       "semantic_role": "dimension", "sort_by_column": "Visual-Parameter Order"},
      {"name": "Visual-Parameter Fields", "data_type": "string",  "hidden": true,
       "semantic_role": "dimension", "sort_by_column": "Visual-Parameter Order",
       "parameter_metadata": {"version": 3, "kind": 2}},
      {"name": "Visual-Parameter Order",  "data_type": "integer", "hidden": true,
       "semantic_role": "dimension", "format_string": "0"}
    ]
  A deterministic post-pass also detects this DAX shape and rewrites the columns
  to the canonical form, so it's safe if you can't tell — but emitting the right
  shape here avoids the rewrite and preserves any column-level metadata you found.

HIERARCHIES:
  - Auto-date tables: attach exactly ONE entry — the standard Date Hierarchy:
      {
        "name": "Date Hierarchy",
        "levels": [
          {"name": "Year",    "column": "Year",    "ordinal": 0},
          {"name": "Quarter", "column": "Quarter", "ordinal": 1},
          {"name": "Month",   "column": "Month",   "ordinal": 2},
          {"name": "Day",     "column": "Day",     "ordinal": 3}
        ]
      }
  - User calc tables: no hierarchies unless evidence in dax_columns suggests one.
    Emit an empty array [] in that case.

Return shape:
{
  "tables": [ ...one entry per dax_tables entry, as specified above... ]
}

SELF-CHECK before returning:
  - len(tables) == len(dax_tables) ?
  - Every TableName from input appears once in output ?
  - Every native_expressions.dax matches the SAME entry's Expression byte-for-byte
    (modulo leading/trailing whitespace) ?
If any check fails, fix it before returning.
""",

    "dax_measures": """
You are a DAX measures extraction specialist.
Extract and analyze DAX measures from the provided JSON.

For each measure, identify:
- Measure name
- DAX expression
- Aggregation type (SUM, AVERAGE, COUNT, etc.)
- Columns/tables it depends on
- Whether it's a reusable metric

Return a JSON object with the following structure:
{
    "dax_measures": [
        {
            "name": "measure name",
            "expression": "DAX expression",
            "aggregation": "SUM/AVERAGE/COUNT/etc",
            "depends_on_columns": ["Table.Column", "Table2.Column2"],
            "reusable_metric": true/false
        }
    ]
}
""",

    "dax_columns": """
You are a DAX calculated columns extraction specialist.
Extract calculated columns from the provided JSON.

Return a JSON object with the following structure:
{
    "dax_columns": [
        {
            "table_name": "table name",
            "column_name": "column name",
            "expression": "DAX expression",
            "data_type": "integer/string/date/etc"
        }
    ]
}
""",

    "dax_tables": """
You are a DAX calculated tables extraction specialist.
Extract calculated tables from the provided JSON.

Return a JSON object with the following structure:
{
    "dax_tables": [
        {
            "name": "table name",
            "expression": "DAX expression",
            "purpose": "description of what this table does"
        }
    ]
}
""",

    "schema": """
You are a Power BI schema extraction specialist.
Extract column-level schema information from the provided JSON.

For each column, identify:
- Table name
- Column name
- Data type
- Whether it's hidden
- Whether it's used in relationships, filters, or calculations

Return a JSON object with the following structure:
{
    "schema": [
        {
            "table_name": "table name",
            "column_name": "column name",
            "data_type": "integer/decimal/string/date/datetime/boolean",
            "nullable": true/false,
            "hidden": true/false,
            "used_in_relationships": true/false,
            "used_in_filters": true/false,
            "used_in_calculations": true/false
        }
    ]
}
""",

    "relationships": """
You are a Power BI relationships extraction specialist.
Extract relationship information from the provided JSON.

You will receive relationships.json (the merged input). You should ALSO use the
companion dax_tables.json data already present in the powerbi_metadata folder
context (the orchestrator may include it inline) — it contains the DAX
expressions for every auto-generated LocalDateTable.

For each relationship, identify:
- From table and column
- To table and column
- Cardinality
- Cross-filter direction
- Whether it's active
- Whether referential integrity is enforced

IMPORTANT RULE for auto-generated Power BI date tables:
pbixray's relationships.json has a known quirk: relationships pointing at
auto-generated LocalDateTables show up with ToTableName = null and
ToColumnName = null. You MUST resolve those instead of emitting null endpoints,
because the downstream PBIP generator needs both sides fully wired so the
visual references "<base column>.Variation.Date Hierarchy.<level>" resolve.

RESOLUTION ALGORITHM (apply this exactly, in order):

STEP 1 — Build the base-column map from dax_tables.json.
For each entry whose TableName starts with "LocalDateTable_<guid>", parse its
DAX Expression. The shape is always:
    Calendar(Date(Year(MIN('<base_table>'[<base_column>])), 1, 1),
             Date(Year(MAX('<base_table>'[<base_column>])), 12, 31))
Extract the single 'base_table'[base_column] reference inside MIN/MAX. Build:
    base_table_to_ldt[<base_table>] = (<LocalDateTable_name>, <base_column>)

(DateTableTemplate_<guid> has no base-column reference — skip it.)

STEP 2 — Resolve every null-right-endpoint row in relationships.json.
For each row where ToTableName is null:
  - Look up the auto-date entry for (FromTableName, FromColumnName) in
    base_table_to_ldt.
  - COLUMN-LEVEL MATCH IS REQUIRED. A row is an auto-date stub ONLY when the
    FromColumnName matches the LocalDateTable's base column for that table.
    pbixray *sometimes* drops FromColumnName on a true auto-date stub, but
    only when no other date column on that table has its own LocalDateTable.
    Apply this rule:
       2a. If FromColumnName is non-null:
           - There must be a LocalDateTable in dax_tables whose base column is
             EXACTLY FromColumnName for FromTableName. If yes -> emit as
             auto-date (shape below). If no -> this is NOT an auto-date stub;
             keep it with right_table_id = null and let downstream handle it
             (do NOT invent a LocalDateTable target for the wrong column).
       2b. If FromColumnName is null AND the table has exactly ONE LocalDateTable
           in dax_tables, treat the null as that base column.
       2c. If FromColumnName is null AND the table has MULTIPLE LocalDateTables,
           you cannot disambiguate — emit with right_table_id = null and right_column
           = null. (This case is rare; never invent a target.)
  - When the resolution succeeds, emit FULLY WIRED:
        id              : "rel_<from_table_snake>_<localdatetable_snake>"
                          (slugs WITHOUT the `tbl_` prefix — see SLUG RULE)
        left_table_id   : "tbl_<from_table_snake>"
        left_column     : the resolved <base_column>
        right_table_id  : "tbl_<localdatetable_snake>"
        right_column    : "Date"
        cardinality     : "many_to_one"
        filter_direction: "single"
        active          : true
        relationship_type : "auto_date_relationship"
        note            : "Auto-generated Power BI local date table relationship"
    NEVER emit `cardinality: "one_to_one"` with `filter_direction: "bidirectional"`
    for an auto-date row — that shape is wrong.

STEP 3 — Fallback (rare).
Only if FromTableName has NO entry in base_table_to_ldt may you emit the row
with right_table_id = null, right_column = null, relationship_type =
"date_relationship", note = "Auto-generated Power BI local date table — no
portable equivalent".

Slug for the LocalDateTable name uses the standard rule below — e.g.
"LocalDateTable_cc4a15a4-36f1-492a-91a0-f955ff637c2d" ->
"tbl_local_date_table_cc4a15a4_36f1_492a_91a0_f955ff637c2d".

SLUG RULE — there are TWO slug forms in this output:
A. TABLE-ID slug — used for left_table_id / right_table_id:
   1. Insert "_" at every lowercase->uppercase boundary (camelCase split)
   2. Replace spaces and any non-alphanumeric characters with "_"
   3. Lowercase everything
   4. Collapse consecutive underscores; strip leading/trailing underscores
   5. Prefix with "tbl_"
   Examples:
     "Revenue Daywise"      -> "tbl_revenue_daywise"
     "CustomerCountPerDay"  -> "tbl_customer_count_per_day"
     "fact_premiums"        -> "tbl_fact_premiums"

B. REL-ID slug — used for the relationship's `id` field:
   Use the BARE per-table slug WITHOUT the "tbl_" prefix. Concatenate as:
       rel_<left_bare_slug>_<right_bare_slug>
   Optionally append a disambiguating suffix when two relationships share the
   same endpoint pair (e.g. `_age` when joining on Age vs Age Group).
   Examples:
     left=dim_date, right=LocalDateTable_9b51030c-...:
        id -> "rel_dim_date_local_date_table_9b51030c_a4ea_43d7_b503_62cd6f1cc2a4"
     left=dim_customer, right=fact_settlements (joined on Age):
        id -> "rel_dim_customer_fact_settlements"
   DO NOT emit ids like "rel_tbl_<left>_tbl_<right>" — the "tbl_" prefix
   belongs ONLY in left_table_id / right_table_id, never in the relationship id.

Both rules apply to ALL relationships including those whose FromTableName is
a DAX-calculated table (e.g. "Revenue Daywise", "CustomerCountPerDay") — those
tables are emitted by the calculated_tables agent and use the same slug.

Return a JSON object with the following structure:
{
    "relationships": [
        {
            "id": "rel_<left_bare_snake>_<right_bare_snake>",
            "left_table_id": "tbl_<lowercase_snake_case_left_table>",
            "left_column": "column name",
            "right_table_id": "tbl_<lowercase_snake_case_right_table>",
            "right_column": "column name",
            "cardinality": "many_to_one",
            "join_type": "left",
            "active": true,
            "filter_direction": "bidirectional",
            "enforced_integrity": false,
            "relationship_type": "dimension_lookup",
            "note": null
        }
    ]
}

CARDINALITY SEMANTICS (read this before assigning):
- "many_to_one" — the LEFT side is the many side (FK / fact), the RIGHT side is
  the one side (PK / dimension). This is the most common case for dim->fact joins.
- "one_to_many" — the LEFT side is the one side (PK), the RIGHT is many.
- "one_to_one"  — BOTH sides have unique values for THIS column AND the join
  semantically represents a 1:1 entity correspondence (rare). pbixray sometimes
  reports `1:1` just because the imported data happens to be unique on both
  sides — that's NOT a true one_to_one. If one side has semantic_role
  "primary_key" and the other doesn't, prefer many_to_one / one_to_many.
  A deterministic post-pass also overrides obviously-misclassified one_to_one
  rows when one side is clearly the PK.
- "many_to_many" — neither side is unique; requires a bridge table.

NEVER emit `cardinality: "one_to_one"` with `filter_direction: "bidirectional"`
for an AUTO-DATE relationship — that shape is invalid. Auto-date is always
"many_to_one" with "single" filter direction.

DUPLICATE-ROW POLICY:
Emit AT MOST ONE row per unique (left_table_id, left_column, right_table_id,
right_column) tuple. If two relationships in pbixray's input would collapse to
the same tuple, pick the one with the better shape (active over inactive,
correct cardinality over odd cardinality) and drop the other. A post-pass also
dedupes by endpoint tuple, but emitting clean is better than emitting noisy.

For cardinality use one of: "many_to_one", "one_to_one", "many_to_many", "one_to_many"
For filter_direction use one of: "bidirectional", "single"
For relationship_type use one of: "dimension_lookup", "bridge", "date_relationship", "fact_to_fact", "auto_date_relationship"
""",

    "rls": """
You are a Row-Level Security (RLS) extraction specialist.
Extract RLS policies from the provided JSON.

Return a JSON object with the following structure:
{
    "rls_policies": [
        {
            "role_name": "role name",
            "table": "table name",
            "rule_expression": "DAX filter expression"
        }
    ]
}
""",

    "statistics": """
You are a Power BI statistics extraction specialist.
Extract statistical information about columns from the provided JSON.

Return a JSON object with the following structure:
{
    "statistics": [
        {
            "table_name": "table name",
            "column_name": "column name",
            "distinct_count": 0,
            "cardinality": "high/medium/low"
        }
    ]
}
""",

    "layout_mapping": """
You are a Power BI layout extraction specialist.
You will receive a JSON with this top-level structure:
{
  "layout_datamodel_mapping": {
    "report_metadata": { "theme": ..., "total_sections": ..., "report_filters": [...] },
    "sections": [ ... ]
  }
}

Navigate to layout_datamodel_mapping.sections[] — that is the array of pages.
Each section has: page_id, display_name, width, height, filters[], visuals[].
Each visual already has: visual_id, visual_type, title, position, projections, data_transforms, filters[], bookmarks[].

CRITICAL RULES:
- You MUST include EVERY visual from EVERY page. Never skip or omit any visual for any reason.
- This includes ALL visual types: textbox, image, actionButton, shape, card, slicer, charts, and any other type.
- The visual count in your output must exactly match the visual count in the input for each page.

COPY THESE FIELDS EXACTLY AS-IS from the input — do NOT generate, infer, or modify them:
- page_id        → copy from section.page_id
- display_name   → copy from section.display_name
- width          → copy from section.width
- height         → copy from section.height
- visual_id      → copy from visual.visual_id
- visual_type    → copy from visual.visual_type
- title          → copy from visual.title exactly (keep empty string if it is empty)
- position       → copy all five values (x, y, width, height, z_order) exactly from visual.position

YOUR ONLY JOB beyond copying is to extract the `fields` array for each visual using this logic:
1. Check `projections` — it maps role names to a list of objects each with a `queryRef` string (and optionally a `displayName`, the field's user-facing label).
   - queryRef `Func(Table.Column)` → role=key, aggregation=Func, table=Table, column=Column, query_ref=original string
   - queryRef `Table.Column`       → role=key, aggregation="", table=Table, column=Column, query_ref=original string
   - if the object has a `displayName`, copy it verbatim into the field's `display_name`; otherwise set `display_name` to "".
2. If projections is empty, check `data_transforms.selects[]` — each select has `queryName` (same format) and `roles[]`.
3. If both are empty (textbox, image, actionButton, shape, etc.) → set fields to [].

Return ONLY a valid JSON object — no markdown, no extra text:
{
    "report_pages": [
        {
            "page_id": "<copied exactly>",
            "display_name": "<copied exactly>",
            "width": 1280,
            "height": 720,
            "visuals": [
                {
                    "visual_id": "<copied exactly>",
                    "visual_type": "<copied exactly>",
                    "title": "<copied exactly, including empty string>",
                    "position": {
                        "x": 0,
                        "y": 0,
                        "width": 300,
                        "height": 200,
                        "z_order": 1
                    },
                    "fields": [
                        {
                            "role": "role name from projections key",
                            "table": "TableName",
                            "column": "ColumnOrMeasureName",
                            "aggregation": "Sum / Count / Min / Max / Average / CountNonNull or empty string",
                            "query_ref": "original queryRef string",
                            "display_name": "the projection's displayName if present, else empty string"
                        }
                    ]
                }
            ]
        }
    ]
}
""",
}
