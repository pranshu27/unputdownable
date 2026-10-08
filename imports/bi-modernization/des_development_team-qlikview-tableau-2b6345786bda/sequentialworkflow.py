from dataclasses import dataclass
from typing import Dict, Any, List, Optional
import json
import re
import asyncio
import sys
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

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

from output_parser import workbook_parser, visuals_parser
from utils import preprocess_workbook, _GEO_GENERATED_FIELDS
from tableau_guardrails import (
    robust_llm_parse,
    QualityReport,
    validate_common_model,
    validate_visualizations,
    finalize_tableau_envelope,
    strip_agent_private_keys,
    EXTRACTION_ERROR_KEY,
    AGENT_QUALITY_KEY,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# --- Message-carrying dataclasses ---
@dataclass
class VisualizationsRequest:
    content: str
    # Which common-model section this request extracts: one of
    # "data_sources" | "tables" | "calculations" | "relationships". The single
    # registered agent picks EXTRACTION_PROMPTS[extraction_type]. Mirrors the
    # QlikView/PowerBI per-type FlowRequest.extraction_type pattern.
    extraction_type: str = "tables"

@dataclass
class VisualizationsParsed:
    content: Any

# --- Visuals Layout Agent dataclasses ---
@dataclass
class VisualsRequest:
    content: str  # JSON string of {"visuals": ..., "presentation": ...}

@dataclass
class VisualsParsed:
    content: Any  # Parsed VisualsOutput dict

# --- Technical Analysis dataclasses ---
@dataclass
class TechnicalAnalysisRequest:
    content: str

@dataclass
class TechnicalAnalysisParsed:
    content: str

# --- Topic names ---
VISUALIZATIONS_TOPIC = "VisualizationsExtraction"
TECHNICAL_TOPIC = "TechnicalAnalysis"
VISUALS_TOPIC = "VisualsLayout"

# --- Prompts ---
# ──────────────────────────────────────────────────────────────────────────────
# Data-model extraction prompts — SPLIT BY ENTITY TYPE (mirrors the PowerBI /
# QlikView flows: one agent, one focused prompt per `extraction_type`). The four
# sections — data_sources, tables, calculations, relationships — are extracted in
# four separate LLM calls and merged deterministically (_merge_extraction_results).
# A shared preamble carries every GLOBAL rule (output contract, name-required,
# constrained vocabularies, arrays-never-null, determinism) so each assembled
# prompt physically contains them. Each body owns exactly one section's rules.
# ──────────────────────────────────────────────────────────────────────────────
_EXTRACTION_PREAMBLE = """
You are a Tableau-workbook migration extractor. You convert pre-extracted
Tableau metadata into a tool-agnostic common data model that a downstream
service converts to Power BI. Your output is consumed by a deterministic parser
— it must be valid, complete, and faithful to the input.

You extract ONE SECTION of the common data model per request. The section is
named below. Return ONLY that section's key(s) — nothing else.

INPUT
You receive a structured JSON object (NOT raw XML). Depending on the section it
contains a SUBSET of these keys (only the ones this section needs are provided):

  datasources      - connection metadata: name, connection_class, server, database,
                     schema, path (filename), authentication_method, named_connections
                     (array of sub-connections), is_extract, extract_units.
  tables           - physical/logical tables with columns. Each column carries raw
                     Tableau attributes: name, datatype (raw, e.g. "string",
                     "integer", "real", "date"), role, hidden, semantic_role,
                     is_split, has_calculation.
  joins_and_relationships - join clauses: left_table, right_table, join_type,
                     clauses (each with left/right column references), order.
  calculations     - calculated fields: internal_name, caption, datatype (raw),
                     formula, role, hidden, depends_on (column references), is_split.
  parameters       - Tableau parameters: name, datatype, formula, range, allowed_values.
  hierarchies      - drill-path definitions: name, ordered members.
  filters          - datasource-level filters: column, class, include_values.
  groups_and_sets  - group definitions with members.
  column_aliases   - internal_name to caption mappings per datasource.
  semantic_roles   - column name to Tableau semantic-role attribute mapping.
  metadata_records - remote/local name mappings, aggregation info, approx_count.
  extract_info     - extract enabled/disabled, units, connection_class per datasource.
  custom_sql       - custom SQL queries: datasource, name, connection, sql text.
  security         - row-level security / user-filter definitions: column, members, scope.
  blending_links   - cross-datasource blending: worksheet, datasources involved,
                     and the linking columns.
  tables_digest    - a COMPACT, read-only list of tables and their columns (name +
                     key attributes) for cross-reference ONLY. NEVER emit it.
  calc_names       - read-only list of calculated-field names, so you never emit a
                     calculation as a physical column.
  datasource_id_map- read-only {datasource name -> data-source id} for linking.

OUTPUT CONTRACT (HARD REQUIREMENTS — the parser depends on every item)
Return ONE JSON object containing ONLY the key(s) for THIS section, as an ARRAY
(emit an empty array, never null, when the section has no entries). Do NOT add any
other top-level keys. Do NOT wrap the object in markdown.

Required, non-null fields per entity (a missing name makes the entry unusable
downstream and it will be DROPPED — always provide one):
  - every tables[] entry has a non-empty "name"
  - every tables[].columns[] entry has a non-empty "name"
  - every calculations[] entry has a non-empty "name"

Constrained vocabularies — use ONLY these literal values:
  - column.semantic_role: primary_key, foreign_key, identifier, measure, date, dimension
  - column.data_type / calculation.data_type: string, integer, real, date, datetime, boolean
  - relationship.cardinality: one_to_one, one_to_many, many_to_one, many_to_many
  - relationship.filter_direction: single, bidirectional
  - relationship.relationship_type: dimension_lookup, auto_date_relationship, blend
Any value outside these sets will be coerced or discarded downstream — do not
invent alternatives (no "fact_to_fact", "join", "many-to-many", "Text", etc.).

These collection fields MUST always be arrays (use [] when empty, never null):
  tables[].columns, tables[].hierarchies, tables[].ingestion.steps,
  calculations[].depends_on_columns, calculations[].depends_on_measures,
  relationships (top-level), columns[].variations.
Boolean fields must be true or false, never null.

DETERMINISM AND ANTI-HALLUCINATION
- Use ONLY evidence present in the input. Do NOT invent tables, columns,
  measures, relationships, paths, or values.
- If a value is genuinely absent and cannot be confidently inferred, use null for
  optional scalar fields — never a placeholder string like "unknown" or "N/A".
- Keep names tool-agnostic so the same model converts cleanly to any BI tool.
- The table named "Parameters" is the home table for all Tableau parameters.
"""

_BODY_DATA_SOURCES = """
SECTION: data_sources
INPUT FOR THIS SECTION: datasources (each with a "suggested_id"), extract_info,
custom_sql. Return ONLY: { "data_sources": [ ... ] }

- Emit one data_sources[] entry per datasource. Set "id" to that datasource's
  "suggested_id" VERBATIM (downstream links tables to this id).
- Resolve source_type from the INNER connection classes inside named_connections,
  NOT the outer "federated" wrapper (which is just Tableau internal architecture):
  * If ALL inner connections share one class, resolve from that class
    (textscan -> "csv", excel-direct -> "excel"); otherwise use the class name.
  * Use "federated" ONLY when the inner connections are a MIX of different types.
- connection_mode: "extract" when is_extract is true, else "live".
- path: the datasource's primary file path. If the datasource references several
  files/tables, also populate "paths" with all of them.
- Generate a concise, human-readable "description" for every data source.
"""

_BODY_TABLES = """
SECTION: tables
INPUT FOR THIS SECTION: tables, joins_and_relationships, filters, security,
custom_sql, hierarchies, extract_info, column_aliases, semantic_roles,
metadata_records, parameters, calc_names, datasource_id_map.
Return ONLY: { "tables": [ ... ] }

- Map raw Tableau datatypes to the constrained data_type vocabulary above.
- Cross-reference joins_and_relationships, filters and calc_names to set the
  column flags used_in_relationships / used_in_filters / used_in_calculations.
- Generate a concise, human-readable "description" for EVERY table and column.
  Never leave description null.
- set source_data_source_id from datasource_id_map (datasource name -> id).
- is_materialized on a table: true when its datasource extract_info is enabled.

semantic_role inference (apply in order; never leave null when evidence exists):
  * used_in_relationships=true AND the column is on the unique ("one") side
    (dimension table, or distinct_count_high matching row count) -> primary_key
  * used_in_relationships=true AND on the "many" side (fact referencing a
    dimension) -> foreign_key
  * data_type is date or datetime -> date
  * numeric AND used_in_calculations=true AND on a fact table -> measure
  * name contains id/code/key (case-insensitive) AND distinct_count_high=true
    -> identifier
  * otherwise -> dimension
  A Tableau geographic semantic role in the input (a bracketed role token) is NOT
  a valid output semantic_role — still resolve to one of the six values above.

distinct_count_high: true when metadata_records approx_count for the column
exceeds 1000.

CALCULATED FIELDS — NEVER emit a calculation as a physical column
Any name present in calc_names is a Tableau calculated field (emitted by the
calculations section, not here). Do NOT add it as an entry in any
tables[].columns[]. A columns[] entry with no "expression" is treated downstream
as a PHYSICAL source column that must exist in the underlying CSV/extract; a
calculated field has no such physical column, so duplicating it makes the
generated Power BI model fail to load ("column not found"). Physical columns in
tables[].columns[] are ONLY the real source columns from the input `tables`
metadata — never the calculated fields.

INGESTION STEPS (tables[].ingestion.steps[])
Each step has order, step_type, description, native_expressions (a map of
tool name -> expression; use the key "tableau" for Tableau-native syntax).
- Always begin with a "read_source" step per table.
- Add a "join" step for each join the table participates in (type + joined table
  in the description and native_expressions).
- Add a "create_extract" step when the datasource has an extract enabled.
- Add a "filter" step for each datasource-level filter on the table.
- Add a "split" step for each column with is_split=true.

TABLE NAMES AND FEDERATION DUPLICATES
- A table in the output is one logical relation. Use the bare physical relation
  name in tables[].name. Strip file extensions (.csv, .xlsx, .xls, .tsv, .hyper).
  Do NOT prefix with the datasource name.
- When the SAME physical relation is referenced from two or more datasources,
  emit ONE tables[] row, not one per datasource. Merge the columns (union; keep
  the more specific semantic_role on conflict, priority
  foreign_key > primary_key > identifier > measure > date > dimension), set
  source_data_source_id to any one participating datasource id, and union the
  ingestion steps in original order without duplicates.

SELF-JOIN ALIASES
When a datasource joins a table to itself under an alias, emit BOTH rows in
tables[]: the base table AND each alias. For the alias row, set name to the alias
used in the join, set source_derived_from_table_id to the base table's bare name,
copy the base column list, and inherit table_type and source_data_source_id. Any
alias referenced by a visual field MUST exist in tables[].

CUSTOM SQL
For each custom_sql entry, emit a tables[] row with table_type = null, a
description that summarises what the SQL does, and an ingestion step with
step_type "custom_sql" carrying the full SQL in native_expressions.tableau.

SECURITY (ROW-LEVEL)
For each security/user-filter entry, emit an ingestion step with step_type
"row_level_security" on the affected table, recording the filter column, the
affected users/groups and the scope in the description and native_expressions.
This is access control, not a calculation.

HIERARCHIES
For each hierarchy, find the table containing its member columns and add the
hierarchy to that table's hierarchies array — each entry has a name and an ordered
levels array, where each level has name, column and a 0-based ordinal. Do NOT emit
hierarchies as calculations.

FILTERS
- Datasource-level filters: emit as ingestion steps (step_type "filter") on the
  relevant table, recording the column and include_values in native_expressions.

PARAMETERS HOST TABLE
- If at least one parameter exists, also emit a tables[] row named "Parameters"
  with table_type "calculated", source_data_source_id null, is_materialized false,
  empty columns and hierarchies, and a single ingestion step of step_type
  "dax_calculated_table" whose native_expressions records a blank calculated-table
  body. This gives the parameter measures a real home table downstream. (The
  parameter measures themselves are emitted by the calculations section.)
"""

_BODY_CALCULATIONS = """
SECTION: calculations
INPUT FOR THIS SECTION: calculations, parameters, groups_and_sets, column_aliases,
measure_names_aliases, tables_digest (compact tables+columns for home_table and
dependency resolution — never emit it). Return ONLY: { "calculations": [ ... ] }

- Map raw Tableau datatypes to the constrained data_type vocabulary above.
- Generate a concise, human-readable "description" for every calculation.

CALCULATED COLUMNS
A calculated field belongs ONLY to the table(s) whose columns it actually
references in its depends_on list. Do NOT copy a calculated column into every
table of the datasource — place it (via home_table) on the table that owns its
referenced columns.

depends_on_columns vs depends_on_measures (lineage correctness)
- depends_on_columns: ONLY physical table columns that exist in tables_digest, in
  "Table.Column" form (use the table name as it appears in tables_digest).
- depends_on_measures: the NAMES of OTHER calculations/measures referenced by
  the formula (whether the formula cites them by internal id or by caption).
- NEVER place a calculation/measure reference into depends_on_columns, and never
  place a physical column into depends_on_measures.
- A formula that references another calculated field lists that field's NAME in
  depends_on_measures and only its physical columns in depends_on_columns.
- A formula that references only physical columns has depends_on_measures = [].
- A formula that references a parameter lists the parameter's name in
  depends_on_measures.

CALCULATIONS
- Use each calculation's ORIGINAL caption as its name, EXACTLY as it appears.
  Visuals reference measures by their bare name, so do not add qualifiers.
- Disambiguate ONLY when two or more DIFFERENT calculations share the exact same
  name: append the home_table once in parentheses to just the colliding ones, and
  update any depends_on_measures that referenced the old name. Never add more than
  one parenthesised suffix, and never qualify a name that is already unique.
- Infer semantic_type from the formula (sum, ratio, growth_rate, discount, split,
  parameter, group, etc.) and aggregation_behavior ("additive" for
  sums/counts/arithmetic, "non_additive" for ratios/strings).
- format_string: "#,##0.00" for numeric, "yyyy-MM-dd" for date, null for strings.
- home_table: the table whose columns the calculation primarily references; if it
  spans several tables, use the fact table. Parameters use home_table "Parameters".
- Preserve the raw Tableau formula verbatim in expressions.tableau.

PARAMETERS
- Emit each parameter as a calculations[] entry with semantic_type "parameter"
  and home_table "Parameters". Populate parameter_config with current_value (the
  default), min_value, max_value, step_size (from the range when present),
  allowed_values (for list parameters), and control_type ("slider" for numeric
  ranges, "dropdown" for lists, "type-in" for free-form).

GROUPS AND SETS
- Groups/Sets: emit as calculations[] with semantic_type "group", the members in
  the description, and the grouped column in depends_on_columns.
"""

_BODY_RELATIONSHIPS = """
SECTION: relationships
INPUT FOR THIS SECTION: joins_and_relationships, blending_links, tables_digest
(compact tables+columns with semantic_role, for cardinality — never emit it).
Return ONLY: { "relationships": [ ... ] }

Emit one relationships[] entry per join clause with left_table_id, left_column,
right_table_id, right_column (reference tables by their bare tables_digest name).
cardinality (REQUIRED, never null) — decide from join-key uniqueness on each side
(primary_key/identifier = unique; foreign_key/dimension/measure = not unique):
  * left unique, right not  -> one_to_many
  * right unique, left not  -> many_to_one  (the common fact->dimension case)
  * both unique             -> one_to_one  (requires PK/identifier on BOTH sides)
  * neither unique          -> many_to_many
  * self-join (same table both sides) -> many_to_many
  Never choose one_to_one unless both sides are PK/identifier. When genuinely
  ambiguous, default to many_to_many.
filter_direction (REQUIRED, never null):
  * many_to_one or one_to_many -> single
  * one_to_one or many_to_many -> bidirectional
relationship_type: "dimension_lookup" for ordinary cross-table joins (including
self-joins); "blend" only for cross-datasource blending (see below);
"auto_date_relationship" only for hidden date->date-table links (rare in Tableau).

DATA BLENDING
For each blending_links entry, emit a relationships[] entry with
relationship_type = "blend", join_type = "left" (Tableau blends are left-join
semantics), active = true, a note naming the worksheet where the blend is used,
and left/right table+column parsed from the blending columns. Reference tables by
their clean bare names, never by internal Tableau ids.
"""

_COMMON_TAIL = f"""
Return ONLY the raw JSON object — no markdown, no commentary, no extra keys.
{workbook_parser.get_format_instructions()}
"""

# extraction_type -> assembled system prompt (shared preamble + body + tail).
EXTRACTION_PROMPTS = {
    "data_sources":  _EXTRACTION_PREAMBLE + _BODY_DATA_SOURCES  + _COMMON_TAIL,
    "tables":        _EXTRACTION_PREAMBLE + _BODY_TABLES        + _COMMON_TAIL,
    "calculations":  _EXTRACTION_PREAMBLE + _BODY_CALCULATIONS  + _COMMON_TAIL,
    "relationships": _EXTRACTION_PREAMBLE + _BODY_RELATIONSHIPS + _COMMON_TAIL,
}

# The single key each extraction_type owns in the merged model.
_EXTRACTION_TYPE_KEY = {
    "data_sources": "data_sources", "tables": "tables",
    "calculations": "calculations", "relationships": "relationships",
}

# Per-type repair directive fed to robust_llm_parse on a parse retry.
_EXTRACTION_REPAIR = {
    "data_sources":  "Return a JSON object with a 'data_sources' array (use [] when empty).",
    "tables":        "Return a JSON object with a 'tables' array; each table has a non-empty 'name' and a 'columns' array.",
    "calculations":  "Return a JSON object with a 'calculations' array; each entry has a non-empty 'name'.",
    "relationships": "Return a JSON object with a 'relationships' array (use [] when empty).",
}

TECHNICAL_PROMPT = """
You are a Technical Analysis Agent specializing in Data Engineering and BI
migration. You are given a structured JSON extraction of a Tableau workbook
(the common data model: data_sources, tables, relationships, calculations and
visualizations). Produce a professional, document-style technical analysis
report for Data Engineers and ETL/BI Architects who will migrate or maintain it.

Cover, in clearly headed sections:
  1. Executive Summary - the workbook's purpose, source systems and overall
     architecture, in business-aware but technical language.
  2. Data Sources and Connectivity - source types, connection/extract modes,
     and what each source contributes.
  3. Data Model - tables and their roles (fact/dimension/calculated),
     relationships and cardinalities, and how the model is shaped.
  4. Transformations and Ingestion - notable ingestion steps (joins, filters,
     custom SQL, extracts, splits) and what they do.
  5. Calculations and Measures - the key calculated fields and parameters, with
     their full expanded expressions and their business meaning.
  6. Reporting Layer - the dashboards/worksheets and what they communicate.
  7. Migration Considerations - risks, tool-specific constructs, and anything an
     engineer should watch for when converting to another BI tool.

Ground every statement in the provided JSON — do not invent details that are not
present. When the JSON is incomplete for a section, say so briefly rather than
fabricating. Show full expanded expressions when you reference formulas.

Style: plain English, formal technical tone, organised with clear headings and
subheadings. Do NOT output raw JSON, code blocks, or markdown formatting —
produce a clean, human-readable narrative document.

Return ONLY the technical document as plain text.
"""

VISUALS_PROMPT = f"""
You are a Tableau Workbook Visual Layout Extractor. You convert enriched visual
metadata into a tool-agnostic COMMON VISUAL MODEL that a downstream service
converts to Power BI report pages. Your output is consumed by a deterministic
parser — it must be valid JSON and faithful to the input.

INPUT
A JSON object with two top-level keys:

  visuals       - enriched visual metadata:
    worksheets  - worksheet entries with shelves, marks, encodings, sorts,
                  style_rules, tooltip, reference_lines, axes, legends,
                  annotations, mark_labels, dual_axis, trend_lines,
                  table_calc_configs, conditional_formatting,
                  datasource_dependencies, uuid, name.
    dashboards  - dashboard entries with name, uuid, width, height, and zones
                  (each zone: id, type, name, x, y, w, h, style); each
                  worksheet zone carries a pre-merged worksheet_data object.
    sheets      - sheet entries (object_id, name).
    dashboard_filters - filter zone definitions.
    format_overrides  - per-field format overrides.
    datasource_color_encodings - explicit color-to-value mappings per datasource.
  presentation  - workbook-level styles and color palettes.

SCOPE
You are typically given ONE dashboard at a time (dashboards[] holds a single
entry) together with only the worksheets that dashboard uses. Produce exactly the
page(s) for the dashboard(s) present in THIS input — one page per dashboard — and
never invent pages for dashboards that are not in this input. Emit every
worksheet zone on the given dashboard as its own visual.

OUTPUT CONTRACT (HARD REQUIREMENTS)
Return ONE JSON object with a top-level "pages" ARRAY (emit [] if there are no
pages). Each page has page_id, display_name, width, height and a "visuals" ARRAY.
Each visual has: visual_id, visual_type, title, position, and a "fields" ARRAY.
  - position is an OBJECT with numeric x, y, width, height, z_order.
  - fields[] entries have role, table, column, aggregation, query_ref.
  - fields, visuals and pages must always be arrays, never null.
Do NOT wrap the object in markdown. Booleans must be true or false, never null.

1. PAGES: each Tableau dashboard becomes one page.
   - page_id = dashboard uuid; display_name = dashboard name.
   - width = dashboard width (pixels); height = dashboard height (pixels).
   - Do NOT emit page styles or color palettes — those are filled downstream.

2. VISUALS: each dashboard zone becomes one visual.
   - Use ONLY the worksheet_data already attached to the zone for its shelves,
     marks, encodings and styles. Do NOT look worksheets up separately.

3. POSITION CONVERSION: convert Tableau zone coordinates to pixels.
   - max_right  = max(zone.x + zone.w) across the dashboard's zones.
   - max_bottom = max(zone.y + zone.h) across the dashboard's zones.
   - scale_x = dashboard.width / max_right; scale_y = dashboard.height / max_bottom.
   - x = zone.x * scale_x; y = zone.y * scale_y;
     width = zone.w * scale_x; height = zone.h * scale_y (round to 1 decimal).
   CRITICAL: perform every calculation yourself and write the FINAL COMPUTED
   NUMBER. Each numeric field MUST be a single literal number (e.g. 214.0).
   NEVER write an arithmetic expression as a JSON value — JSON has no arithmetic
   and it makes the response impossible to parse.

4. Z_ORDER: by zone document order: first zone 0, second 1000, third 2000, etc.

5. DATA BINDINGS (fields[]): map Tableau shelves + encodings to roles.
   - columns-shelf dimension -> role "Category"
   - rows-shelf measure      -> role "Y"
   - dual-axis secondary     -> role "Y2"
   - pages shelf             -> role "Pages"
   - filters shelf           -> role "Filter"
   - color encoding (dimension) -> role "Series"
   - color encoding (measure)   -> role "Color"
   - size encoding  -> role "Size"
   - shape encoding -> role "Shape"
   - text/label encoding -> role "Values"
   - detail encoding  -> role "Detail"
   - tooltip encoding -> role "Tooltip"
   NEVER emit role "Label" — any label-like binding uses role "Values" instead
   (the downstream tool has no Label role). Put the full Tableau field reference
   in query_ref and extract table, column and aggregation from it.

   FIELD REFERENCE DECODING:
   - Prefix: none:/attr: = dimension; sum:/avg:/cnt:/cntd: = measure;
     tmn:/my:/yr: = date.
   - Suffix: nominal = dimension; quantitative = measure; ordinal = date.
   - Aggregation: sum: -> "Sum", cnt: -> "Count", avg: -> "Average",
     min: -> "Min", max: -> "Max", cntd: -> "CountDistinct", med: -> "Median",
     stdev: -> "StdDev", var: -> "Var", attr: -> "AttributeOnly";
     none:/tmn:/my:/yr:/usr: -> "" (empty).

6. VISUAL_TYPE: determine the chart type STRICTLY from structure (mark type,
   rows/columns shelves, field roles, aggregations, date fields, geographic
   roles, encodings, dual-axis, bins, table calculations). NEVER use worksheet
   names, titles or labels. Apply in order; first match wins:
   a. Non-chart zones by zone type: text/title -> "textbox"; filter -> "slicer";
      paramctrl -> "paramctrl"; bitmap -> "image"; web -> "webview";
      flipboard-nav -> "navigation".
      A zone with formatted text and no worksheet_data -> "textbox".
   b. SKIP ENTIRELY (do not emit): layout/flow/flipboard containers, empty zones,
      spacers, separators, wrappers, and any zone with no worksheet_data and no
      formatted text. Never emit a container/spacer/empty/layout visual.
   c. mark Pie -> "pie_chart"; mark Area -> "area_chart";
      mark Gantt Bar -> "gantt_chart".
   d. generated latitude AND longitude present -> "map" (not merely because a
      name contains a place).
   e. measure on BOTH rows and columns -> "scatter_plot" (with size encoding ->
      "bubble_chart"); mark Circle -> "scatter_plot".
   f. mark Square with dimensions on both axes (or one) -> "heat_map";
      mark Text with color -> "highlight_table"; mark Text without color ->
      "text_table"; an Automatic crosstab with a measure-names placeholder ->
      "text_table" (or "highlight_table" if colored). Evaluate these before bar.
   g. date/time field on the category axis + a measure -> "line_chart".
   h. dimension on one axis + measure on the other -> "bar_chart" (with a color
      dimension -> "stacked_bar_chart"). Two or more measures on the same axis
      with the SAME mark type -> "bar_chart" (grouped bars, not dual-axis).
      Mark Automatic with dimension + measure defaults to "bar_chart".
   i. dual-axis with DIFFERENT mark types -> "dual_axis_chart" (same mark type
      for all measures is NOT dual-axis). Never output "combo_chart".
   j. box-and-whisker reference metadata -> "box_whisker_chart".
   k. bin field + count -> "histogram"; square + size -> "tree_map";
      single measure, no dimensions -> "kpi_card".
   l. fallback "unknown" ONLY when there is no recognizable structure.
   NEVER output any of: blank, color, circle, square, combo_type, combo_chart,
   container, layout, group, empty, spacer, padding, separator, or any wrapper
   type. Use the mapped chart type instead, or skip the zone entirely.

7. RICH PROPERTIES: pass through directly from worksheet_data when present —
   mark_type (marks[0].mark_class), axes, legends, tooltip_config, data_labels,
   sort_config, reference_lines, trend_lines, dual_axis, conditional_formatting,
   annotations, table_calc_configs, datasource_dependencies. Copy them exactly;
   do NOT blank them to null/[] when the worksheet_data actually contains them.
   They are null for non-worksheet visuals (textbox, slicer, image).

8. STYLING: do NOT emit border_style or text_style — borders, backgrounds,
   padding and fonts are extracted deterministically downstream.

9. TEXTBOX visuals: set content to the formatted-text run text only.

10. IMAGE visuals (bitmap zones): set visual_type "image"; the imageUrl is filled
    automatically after your output.

11. SLICER visuals (filter zones): add a field with role "Values" from the param.

12. PARAMETER CONTROL visuals (paramctrl zones): set visual_type "paramctrl", add
    a field with role "Values" from the zone's parameter, and set
    datasource_dependencies to a one-element list naming the Parameters table when
    the param references a workbook parameter.

13. STANDALONE WORKSHEETS: a worksheet not referenced by any dashboard zone
    becomes its own page (page_id = worksheet uuid, display_name = worksheet name,
    width 800, height 600) with a single visual filling it.

14. source_tool: always "tableau" on every visual.

15. DASHBOARD ACTIONS: populate each page's actions array directly from the
    dashboard's pre-parsed actions (name, type, activation, source_worksheet,
    target_dashboard, excluded_worksheets, fields). The action data is already
    parsed — copy values directly; use null for actions only when there are none.

16. COLOR ASSIGNMENTS: when a visual uses a field that matches a
    datasource_color_encodings entry (match by the column-name portion of the
    Tableau reference), populate that visual's conditional_formatting with
    encoding_type "categorical" and the entry's value-to-color assignments.

DETERMINISM
- Use only what the input provides; do not invent values.
- Use null or [] for genuinely absent fields, as appropriate to the field type.

Return ONLY the raw JSON object — no markdown, no commentary, no extra keys.
{visuals_parser.get_format_instructions()}
"""

# ---------------------------------------------------------------------------
# Output sanitisation
# ---------------------------------------------------------------------------
# LLMs occasionally echo an arithmetic *expression* (e.g. 13375 * 0.016) into a
# JSON value instead of the computed number. That is invalid JSON, so the
# LangChain output parser raises OUTPUT_PARSING_FAILURE; the agent then cannot
# publish a result and the workflow hangs forever waiting on an empty queue.
# This pass evaluates such expressions back into plain numbers before parsing.
_JSON_ARITHMETIC_RE = re.compile(
    r'(:\s*)'                                      # JSON key/value separator
    r'(-?\d[\d.]*(?:\s*[*/+\-]\s*-?\d[\d.]*)+)'    # number then >=1 (operator number)
    r'(\s*[,}\]\r\n])'                             # JSON value terminator
)


def _sanitize_json_arithmetic(text: str) -> str:
    """Replace unquoted arithmetic expressions in JSON value positions with their
    evaluated numeric result.

    Only number-and-operator runs sitting directly after a ``:`` and before a
    ``,`` / ``}`` / ``]`` are touched, so quoted strings (titles, formulas) are
    never altered. Returns the text unchanged when nothing matches.
    """
    if not text:
        return text

    def _eval(m: "re.Match") -> str:
        expr = m.group(2)
        if not re.fullmatch(r'[-+*/.\d\s]+', expr):
            return m.group(0)
        try:
            value = eval(expr, {"__builtins__": {}}, {})  # digits/operators only
        except Exception:
            return m.group(0)
        if isinstance(value, float):
            value = round(value, 2)
        return f"{m.group(1)}{value}{m.group(3)}"

    sanitized = _JSON_ARITHMETIC_RE.sub(_eval, text)
    if sanitized != text:
        print("[Tableau] Sanitised arithmetic expression(s) in LLM JSON output")
        logger.warning("Sanitised arithmetic expression(s) in LLM JSON output")
    return sanitized


# --- Agents ---
@type_subscription(topic_type=VISUALIZATIONS_TOPIC)
class VisualizationsExtractorAgent(RoutedAgent):
    def __init__(self, model_client):
        super().__init__("Visualizations extractor agent")
        self._model_client = model_client

    @message_handler
    async def handle_message(self, message: VisualizationsRequest, ctx: MessageContext) -> None:
        structured_input = message.content
        etype = message.extraction_type if message.extraction_type in EXTRACTION_PROMPTS else "tables"
        system_prompt = EXTRACTION_PROMPTS[etype]
        owned_key = _EXTRACTION_TYPE_KEY[etype]
        print(f"[Tableau][ExtractionAgent:{etype}] Sending request to LLM (input size: {len(structured_input)} chars)")
        logger.info("ExtractionAgent[%s]: sending request to LLM, input_size=%d", etype, len(structured_input))
        q = QualityReport()
        parsed = await robust_llm_parse(
            self._model_client,
            system_prompt,
            structured_input,
            workbook_parser,
            label=f"extraction_{etype}",
            quality=q,
            sanitize=_sanitize_json_arithmetic,
            repair_directive=_EXTRACTION_REPAIR.get(etype, ""),
        )
        if parsed is None:
            # Do NOT silently drop. Publish a well-formed shell carrying ONLY this
            # section's empty key + an error marker so the runtime drains and the
            # merge degrades only this one section.
            parsed = {
                owned_key: [],
                EXTRACTION_ERROR_KEY: f"extraction[{etype}] produced no valid JSON after retries",
            }
        if isinstance(parsed, dict):
            parsed[AGENT_QUALITY_KEY] = q.to_list()
            # Tag the response so the order-independent collector knows which
            # section it is and takes ONLY that section's key (no cross-contamination
            # if a call accidentally echoes another section's empty key).
            parsed["__extraction_type__"] = etype
        n_owned = len(parsed.get(owned_key, []) or []) if isinstance(parsed, dict) else 0
        print(f"[Tableau][ExtractionAgent:{etype}] Parsed {owned_key}: {n_owned} entries")
        logger.info("ExtractionAgent[%s]: parsed %s=%d", etype, owned_key, n_owned)
        await self.publish_message(
            VisualizationsParsed(content=parsed),
            topic_id=DefaultTopicId()
        )


@type_subscription(topic_type=TECHNICAL_TOPIC)
class TechnicalAnalysisAgent(RoutedAgent):
    def __init__(self, model_client):
        super().__init__("Technical analysis agent")
        self._model_client = model_client
        self._system = (SystemMessage(content=TECHNICAL_PROMPT),)

    @message_handler
    async def handle_message(self, message: TechnicalAnalysisRequest, ctx: MessageContext) -> None:
        json_input = message.content
        messages = [*self._system, UserMessage(content=json_input, source="user")]
        print(f"[Tableau][TechnicalAgent] Sending request to LLM (input size: {len(json_input)} chars)")
        logger.info("TechnicalAgent: sending request to LLM, input_size=%d", len(json_input))
        summary = ""
        for attempt in range(1, 3):
            try:
                resp = await self._model_client.create(messages=messages)
                summary = resp.content if isinstance(resp.content, str) else str(resp.content or "")
                if summary.strip():
                    break
            except Exception as e:
                logger.error("TechnicalAgent: attempt %d failed: %s", attempt, e)
                print(f"[Tableau][TechnicalAgent] attempt {attempt} failed: {e}")
                summary = ""
        if not summary.strip():
            # Non-core section: never crash the whole run because the narrative
            # summary failed. Emit a placeholder; the orchestrator records the gap.
            summary = "Technical analysis unavailable (summary generation failed)."
            print("[Tableau][TechnicalAgent] summary generation failed — using placeholder")
        else:
            print(f"[Tableau][TechnicalAgent] Summary preview (first 300 chars): {summary[:300]}")
        logger.info("TechnicalAgent: response handled, output_size=%d", len(summary))
        await self.publish_message(
            TechnicalAnalysisParsed(content=summary),
            topic_id=DefaultTopicId()
        )


@type_subscription(topic_type=VISUALS_TOPIC)
class VisualsLayoutAgent(RoutedAgent):
    """Consumes the enriched visuals + presentation context and produces
    a structured VisualsOutput JSON section for the common model."""

    def __init__(self, model_client):
        super().__init__("Visuals layout agent")
        self._model_client = model_client
        self._system = (SystemMessage(content=VISUALS_PROMPT),)

    @message_handler
    async def handle_message(self, message: VisualsRequest, ctx: MessageContext) -> None:
        print(f"[Tableau][VisualsAgent] Sending request to LLM (input size: {len(message.content)} chars)")
        logger.info("VisualsAgent: sending request to LLM, input_size=%d", len(message.content))
        q = QualityReport()
        parsed = await robust_llm_parse(
            self._model_client,
            VISUALS_PROMPT,
            message.content,
            visuals_parser,
            label="visuals",
            quality=q,
            sanitize=_sanitize_json_arithmetic,
            repair_directive=(
                "The JSON object MUST contain a 'pages' array; each page has a "
                "'visuals' array; each visual has 'fields' (array) and 'position' (object)."
            ),
        )
        if parsed is None:
            parsed = {"pages": [], EXTRACTION_ERROR_KEY: "visuals agent produced no valid JSON after retries"}
        if isinstance(parsed, dict):
            parsed[AGENT_QUALITY_KEY] = q.to_list()
            pages = parsed.get("pages", []) or []
            total_visuals = sum(len(p.get("visuals", [])) for p in pages if isinstance(p, dict))
            print(f"[Tableau][VisualsAgent] Parsed output: {len(pages)} pages, {total_visuals} total visuals")
            for i, page in enumerate(pages):
                if not isinstance(page, dict):
                    continue
                vis_count = len(page.get("visuals", []))
                vis_types = [v.get("visual_type", "?") for v in page.get("visuals", []) if isinstance(v, dict)]
                print(f"[Tableau][VisualsAgent]   Page {i}: '{page.get('display_name', '?')}' — {vis_count} visuals: {vis_types}")
            logger.info("VisualsAgent: parsed %d pages, %d total visuals", len(pages), total_visuals)
        await self.publish_message(
            VisualsParsed(content=parsed),
            topic_id=DefaultTopicId()
        )


# --- Closures ---
def _make_save_viz(q: asyncio.Queue):
    async def _save_viz(_ag: ClosureContext, message: VisualizationsParsed, _ctx: MessageContext) -> None:
        await q.put(message)
    return _save_viz

def _make_save_tech(q: asyncio.Queue):
    async def _save_tech(_ag: ClosureContext, message: TechnicalAnalysisParsed, _ctx: MessageContext) -> None:
        await q.put(message)
    return _save_tech

def _make_save_visuals(q: asyncio.Queue):
    async def _save_visuals(_ag: ClosureContext, message: VisualsParsed, _ctx: MessageContext) -> None:
        await q.put(message)
    return _save_visuals

# --- Orchestration helpers ---

def _select_model_client(model: str):
    """Return the LLM client that matches the requested model name.

    Falls back to the Azure client when *model* is None or not recognised,
    so callers that omit the optional ``model`` form field still work.
    """
    if model == "gemini_1.5_pro":
        print("[Tableau] Using Gemini 1.5 Pro client")
        logger.info("Using Gemini 1.5 Pro client")
        from config import google_client as client
        return client
    # Default: Azure (covers None, "gpt4o", and any future unrecognised value)
    if model and model not in ("gpt4o", None):
        logger.warning("[Tableau] Unrecognised model %r — falling back to Azure client", model)
        print(f"[Tableau] Warning: unrecognised model {model!r}, falling back to Azure client")
    print("[Tableau] Using Azure client")
    logger.info("Using Azure client (model=%r)", model)
    from config import azure_client as client
    return client


async def _collect_visuals_result(q: asyncio.Queue) -> tuple:
    """Collect the visuals agent response; return (parsed_result, elapsed_seconds)."""
    try:
        visuals_start = time.perf_counter()
        visuals_msg = await q.get()
        visuals_parsed = visuals_msg.content
        if isinstance(visuals_parsed, str):
            visuals_parsed = json.loads(visuals_parsed)
        elapsed = time.perf_counter() - visuals_start
        print(f"[Tableau] Visuals agent response received in {elapsed:.3f}s")
        logger.info("Received Tableau visuals payload, elapsed=%.3f", elapsed)
        return visuals_parsed, elapsed
    except Exception as e:
        logger.error("[Tableau] Visuals agent failed, continuing without visualizations: %s", e)
        print(f"[Tableau] Warning: Visuals agent failed ({e}), continuing without visualizations")
        return None, 0.0


# ── Per-type data-model extraction: slice / merge / link / dump ────────────────
_TABLE_EXT_RE = re.compile(r"\.(csv|xlsx|xls|tsv|hyper|txt|json|parquet)$", re.IGNORECASE)


def _bare_table_name(name: Optional[str]) -> str:
    """Strip a trailing file extension from a relation name (same rule the prompt
    applies). Names in context.model are usually already bare; this is defensive
    so the compact digests match the table names the LLM emits."""
    return _TABLE_EXT_RE.sub("", (name or "").strip())


def _build_extraction_slices(context: Any) -> tuple:
    """Build the four per-type input slices (JSON strings) from context.model.

    Each slice carries ONLY the keys its section needs, plus compact read-only
    digests for cross-reference (so the calculations/relationships calls can
    resolve home_table / cardinality without the full table payload). Returns
    ``(slices_by_type, ds_id_by_key)`` where ds_id_by_key maps datasource
    caption/name -> a deterministic ``ds_<slug>`` id used to link tables."""
    m = getattr(context, "model", None) or {}
    datasources = m.get("datasources") or []
    tables = m.get("tables") or []
    calcs = m.get("calculations") or []

    def _slug(s: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_") or "ds"

    # Deterministic, unique ds_id per datasource; index by both caption and name.
    ds_id_by_key: Dict[str, str] = {}
    ds_with_id: List[dict] = []
    used_ids: set = set()
    for ds in datasources:
        cap = (ds.get("caption") or "").strip()
        nm = (ds.get("name") or "").strip()
        base = cap or nm or "ds"
        dsid = "ds_" + _slug(base)
        n = 1
        while dsid in used_ids:
            n += 1
            dsid = f"ds_{_slug(base)}_{n}"
        used_ids.add(dsid)
        if cap:
            ds_id_by_key[cap] = dsid
        if nm:
            ds_id_by_key[nm] = dsid
        ds_with_id.append({**ds, "suggested_id": dsid})

    calc_names = sorted({(c.get("caption") or c.get("internal_name") or "").strip()
                         for c in calcs if (c.get("caption") or c.get("internal_name"))})

    # Tableau auto-generates a HIDDEN highlight/filter set per dashboard action
    # (named "Action (...)", kind "group", hidden=true). These are NOT real
    # analytical groups/sets — the old monolithic call skipped them by judgement,
    # but the focused calculations prompt would emit each as a junk group calc
    # (home_table null, no members), polluting the model. Drop hidden ones
    # deterministically so only genuine user groups/sets reach the LLM.
    def _truthy(v) -> bool:
        return str(v).strip().lower() in ("true", "1", "yes")
    visible_groups = [g for g in (m.get("groups_and_sets") or []) if not _truthy(g.get("hidden"))]

    def _col(c: dict, extra: List[str]) -> dict:
        cc = {"name": c.get("name")}
        for f in extra:
            if c.get(f) not in (None, ""):
                cc[f] = c.get(f)
        return cc

    def _digest(extra: List[str]) -> List[dict]:
        """Compact, name-deduped tables+columns digest (read-only cross-ref)."""
        seen: Dict[str, dict] = {}
        out: List[dict] = []
        for t in tables:
            bare = _bare_table_name(t.get("table_name"))
            if not bare:
                continue
            if bare in seen:
                tgt = seen[bare]
                have = {c.get("name") for c in tgt["columns"]}
                for c in (t.get("columns") or []):
                    if c.get("name") and c["name"] not in have:
                        tgt["columns"].append(_col(c, extra))
                        have.add(c["name"])
                continue
            entry = {
                "name": bare,
                "datasource": t.get("datasource_caption") or t.get("datasource_name"),
                "columns": [_col(c, extra) for c in (t.get("columns") or []) if c.get("name")],
            }
            seen[bare] = entry
            out.append(entry)
        return out

    slices = {
        "data_sources": json.dumps({
            "datasources": ds_with_id,
            "extract_info": m.get("extract_info") or [],
            "custom_sql": m.get("custom_sql") or [],
        }, ensure_ascii=False),
        "tables": json.dumps({
            "tables": tables,
            "joins_and_relationships": m.get("joins_and_relationships") or [],
            "filters": m.get("filters") or [],
            "security": m.get("security") or [],
            "custom_sql": m.get("custom_sql") or [],
            "hierarchies": m.get("hierarchies") or [],
            "extract_info": m.get("extract_info") or [],
            "column_aliases": m.get("column_aliases") or {},
            "semantic_roles": m.get("semantic_roles") or {},
            "metadata_records": m.get("metadata_records") or [],
            "parameters": m.get("parameters") or [],
            "calc_names": calc_names,
            "datasource_id_map": ds_id_by_key,
        }, ensure_ascii=False),
        "calculations": json.dumps({
            "calculations": calcs,
            "parameters": m.get("parameters") or [],
            "groups_and_sets": visible_groups,
            "column_aliases": m.get("column_aliases") or {},
            "measure_names_aliases": m.get("measure_names_aliases") or {},
            "tables_digest": _digest(["datatype", "semantic_role"]),
        }, ensure_ascii=False),
        "relationships": json.dumps({
            "joins_and_relationships": m.get("joins_and_relationships") or [],
            "blending_links": m.get("blending_links") or [],
            "tables_digest": _digest(["datatype", "role", "semantic_role"]),
        }, ensure_ascii=False),
    }
    return slices, ds_id_by_key


def _merge_table_entry(dst: dict, src: dict) -> None:
    """Union one incoming table row into an existing same-name row."""
    cols = dst.setdefault("columns", [])
    have = {(c.get("name") or "") for c in cols}
    for c in (src.get("columns") or []):
        if (c.get("name") or "") not in have:
            cols.append(c)
            have.add(c.get("name") or "")
    hd = dst.setdefault("hierarchies", [])
    for x in (src.get("hierarchies") or []):
        if x not in hd:
            hd.append(x)
    steps = dst.setdefault("ingestion", {}).setdefault("steps", [])
    for s in ((src.get("ingestion") or {}).get("steps") or []):
        if s not in steps:
            steps.append(s)
    for k in ("table_type", "source_data_source_id", "source_derived_from_table_id",
              "is_materialized", "description"):
        if not dst.get(k) and src.get(k):
            dst[k] = src.get(k)


def _merge_tables_by_name(existing: List[dict], incoming: List[dict]) -> None:
    """Append new tables; union same-name rows (mirrors agents_powerbi._merge_tables)."""
    index = {(t.get("name") or "").strip(): t for t in existing if (t.get("name") or "").strip()}
    for nt in incoming or []:
        nm = (nt.get("name") or "").strip()
        if not nm:
            existing.append(nt)
            continue
        if nm in index:
            _merge_table_entry(index[nm], nt)
        else:
            existing.append(nt)
            index[nm] = nt


def _dedup_relationships(rels: List[dict]) -> None:
    """Drop duplicate relationships keyed by (left_table,left_col,right_table,right_col)."""
    seen: set = set()
    out: List[dict] = []
    for r in rels:
        key = tuple((str(r.get(k) or "")).strip().lower()
                    for k in ("left_table_id", "left_column", "right_table_id", "right_column"))
        if any(key) and key in seen:
            continue
        seen.add(key)
        out.append(r)
    rels[:] = out


def _merge_extraction_results(parts: List[Any]) -> dict:
    """Merge the per-type partial outputs into one common-model dict, taking ONLY
    each part's owned section key (tagged by __extraction_type__). EXTEND for
    data_sources/relationships/calculations; merge tables by name. Concatenate
    quality entries and join error markers so the orchestrator records degradation."""
    merged: Dict[str, Any] = {"data_sources": [], "tables": [], "relationships": [], "calculations": []}
    agg_quality: List[Any] = []
    errors: List[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        agg_quality.extend(part.get(AGENT_QUALITY_KEY) or [])
        if part.get(EXTRACTION_ERROR_KEY):
            errors.append(str(part.get(EXTRACTION_ERROR_KEY)))
        et = part.get("__extraction_type__")
        keys = [_EXTRACTION_TYPE_KEY[et]] if et in _EXTRACTION_TYPE_KEY else list(merged.keys())
        for k in keys:
            if k == "tables":
                _merge_tables_by_name(merged["tables"], part.get("tables") or [])
            else:
                merged[k].extend(part.get(k) or [])
    _dedup_relationships(merged["relationships"])
    if agg_quality:
        merged[AGENT_QUALITY_KEY] = agg_quality
    if errors:
        merged[EXTRACTION_ERROR_KEY] = "; ".join(errors)
    return merged


def _link_table_data_sources(merged: dict, context: Any, ds_id_by_key: Dict[str, str]) -> None:
    """Deterministically set each table's source_data_source_id from the original
    table->datasource attribution (context.model), and normalize data_sources[].id
    to the same deterministic ds_id. Robust even if the LLM omitted/mismatched it.
    Names resolve downstream by table NAME, so this only fixes the source link."""
    model = getattr(context, "model", None) or {}
    tbl_ds: Dict[str, str] = {}
    for t in (model.get("tables") or []):
        bare = _bare_table_name(t.get("table_name"))
        if not bare or bare in tbl_ds:
            continue  # first datasource wins for a federation-shared table
        key = (t.get("datasource_caption") or t.get("datasource_name") or "").strip()
        if key in ds_id_by_key:
            tbl_ds[bare] = ds_id_by_key[key]
    for t in (merged.get("tables") or []):
        nm = (t.get("name") or "").strip()
        if tbl_ds.get(nm):
            t["source_data_source_id"] = tbl_ds[nm]
    for d in (merged.get("data_sources") or []):
        for cand in ((d.get("name") or "").strip(), (d.get("caption") or "").strip()):
            if cand in ds_id_by_key:
                d["id"] = ds_id_by_key[cand]
                break


def _dump_extraction_artifacts(filename: str, slices: dict,
                               outputs_by_type: dict, merged: dict) -> None:
    """Always-write per-run debug artifacts (per-type input slices + raw LLM
    outputs + the pre-validate merged model) for inspection — parity with the
    PowerBI/QlikView per-type files. Never breaks the run on I/O failure."""
    try:
        stem = Path(filename or "workbook").stem
        base = Path(__file__).resolve().parent / "extraction_debug" / f"{stem}_{int(time.time())}"
        base.mkdir(parents=True, exist_ok=True)
        for t, s in (slices or {}).items():
            (base / f"input_{t}.json").write_text(
                s if isinstance(s, str) else json.dumps(s, ensure_ascii=False, indent=2),
                encoding="utf-8")
        for t, o in (outputs_by_type or {}).items():
            (base / f"output_{t}.json").write_text(
                json.dumps(o, ensure_ascii=False, indent=2), encoding="utf-8")
        (base / "merged.json").write_text(
            json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[Tableau] Extraction artifacts written to {base}")
        logger.info("Extraction artifacts written to %s", base)
    except Exception as e:
        logger.warning("Extraction artifact dump failed: %s", e)


async def _run_visuals_per_dashboard(runtime, q_visuals: asyncio.Queue, context: Any) -> tuple:
    """Dispatch the visuals/layout agent ONCE PER DASHBOARD (plus one grouped call
    for any loose worksheets), then merge the returned pages.

    Splitting the layout work this way keeps each LLM call small — a large
    workbook no longer overflows the model's context — and lets the prompt focus
    on a single dashboard, which the agent extracts far more reliably than one
    monolithic call. The model-extraction stage stays WHOLE (it needs every
    datasource/relationship at once); only the per-dashboard visuals are split.

    Returns ``(merged_visuals_dict, elapsed_seconds)`` shaped exactly like the
    single-call path (a dict with a "pages" list), so all downstream
    post-processing is unchanged. Falls back to one whole-context call when the
    workbook has no dashboards."""
    cvisuals = getattr(context, "visuals", None) or {}
    presentation = getattr(context, "presentation", None) or {}
    dashboards = cvisuals.get("dashboards") or []
    worksheets = cvisuals.get("worksheets") or []
    color_encodings = cvisuals.get("datasource_color_encodings") or []
    ws_by_name = {
        (w.get("name") or "").strip(): w
        for w in worksheets if (w.get("name") or "").strip()
    }

    # Build one scoped payload per dashboard (only the worksheets it places).
    # Power BI report pages mirror Tableau DASHBOARDS — worksheets that are not
    # placed on any dashboard are building blocks, not their own pages (the
    # original whole-workbook call never emitted them as pages either), so they
    # are intentionally NOT turned into chunks here. Their data still lives in
    # the model (tables/calculations).
    chunks: List[tuple] = []   # (label, payload)
    for dash in dashboards:
        names: List[str] = []
        for zone in (dash.get("zones") or []):
            zn = (zone.get("name") or "").strip()
            if zn and zn in ws_by_name and zn not in names:
                names.append(zn)
        chunks.append(((dash.get("name") or "dashboard").strip(), {
            "visuals": {
                "worksheets": [ws_by_name[n] for n in names],
                "dashboards": [dash],
                "sheets": cvisuals.get("sheets") or [],
                "dashboard_filters": cvisuals.get("dashboard_filters") or [],
                "format_overrides": cvisuals.get("format_overrides") or [],
                "datasource_color_encodings": color_encodings,
            },
            "presentation": presentation,
        }))

    # No dashboards — fall back to the original single whole call (covers
    # worksheet-only workbooks, where every worksheet legitimately is a page).
    if not chunks:
        payload = {"visuals": cvisuals, "presentation": presentation}
        await runtime.publish_message(
            VisualsRequest(content=json.dumps(payload, ensure_ascii=False)),
            topic_id=TopicId(VISUALS_TOPIC, source="default"))
        return await _collect_visuals_result(q_visuals)

    start = time.perf_counter()
    for label, payload in chunks:
        content = json.dumps(payload, ensure_ascii=False)
        print(f"[Tableau] Visuals chunk '{label}': {len(content)} chars")
        await runtime.publish_message(
            VisualsRequest(content=content),
            topic_id=TopicId(VISUALS_TOPIC, source="default"))

    # Collect exactly one result per chunk. Arrival order is not guaranteed, so
    # we merge all pages and then order them to match the source dashboard order.
    merged_pages: List[dict] = []
    agg_quality: List[Any] = []
    for _ in chunks:
        parsed, _el = await _collect_visuals_result(q_visuals)
        if isinstance(parsed, dict):
            merged_pages.extend(parsed.get("pages") or [])
            if parsed.get(AGENT_QUALITY_KEY):
                agg_quality.extend(parsed.get(AGENT_QUALITY_KEY) or [])

    # Safety net: if a dashboard's chunk produced no page (LLM call failed), add a
    # minimal page stub so the deterministic _reconcile_dashboard_visuals pass
    # synthesizes that dashboard's visuals from the source worksheets — a missing
    # dashboard would otherwise vanish entirely (worse than the single-call path).
    present_pages = {(p.get("display_name") or "").strip() for p in merged_pages}
    for dash in dashboards:
        dname = (dash.get("name") or "").strip()
        if dname and dname not in present_pages:
            stub = {"display_name": dname, "visuals": []}
            if dash.get("width"):
                stub["width"] = dash.get("width")
            if dash.get("height"):
                stub["height"] = dash.get("height")
            merged_pages.append(stub)
            logger.warning("Visuals per-dashboard: stub page added for '%s' (chunk produced no page)", dname)

    order = {(d.get("name") or "").strip(): i for i, d in enumerate(dashboards)}
    merged_pages.sort(key=lambda p: order.get((p.get("display_name") or "").strip(), len(order) + 1))

    result: Dict[str, Any] = {"pages": merged_pages}
    if agg_quality:
        result[AGENT_QUALITY_KEY] = agg_quality
    elapsed = time.perf_counter() - start
    print(f"[Tableau] Visuals (per-dashboard): {len(chunks)} call(s) -> {len(merged_pages)} page(s) "
          f"in {elapsed:.3f}s")
    logger.info("Visuals per-dashboard: chunks=%d pages=%d elapsed=%.3f",
                len(chunks), len(merged_pages), elapsed)
    return result, elapsed


def _inject_tableau_image_urls(final_parsed: dict, visuals_context: dict) -> None:
    """
    Directly inject imageUrl into Tableau visuals from zone data.

    No LLM needed — deterministic mapping from dashboard zones with type=bitmap/image
    to the corresponding visuals in the output. Matches by zone name (worksheet name)
    or zone id to visual_id.
    """
    # Build a lookup of image URLs from dashboard zones
    image_url_map: Dict[str, str] = {}  # zone_id or zone_name → image_url
    for dash in visuals_context.get("dashboards", []):
        for zone in dash.get("zones", []):
            zone_type = zone.get("type", "")
            if zone_type in ("bitmap", "image"):
                img_url = zone.get("image_url", "")
                if img_url:
                    zone_id = zone.get("id", "")
                    zone_name = zone.get("name", "")
                    if zone_id:
                        image_url_map[zone_id] = img_url
                    if zone_name:
                        image_url_map[zone_name] = img_url

    if not image_url_map:
        return

    # Also check dashboard_objects for image URLs
    for dash in visuals_context.get("dashboards", []):
        for obj in dash.get("dashboard_objects", []):
            if obj.get("object_type") in ("bitmap", "image"):
                img_url = obj.get("image_url", "")
                obj_id = obj.get("id", "")
                if img_url and obj_id:
                    image_url_map[obj_id] = img_url

    # Inject into visualizations output
    visualizations = final_parsed.get("visualizations", {})
    pages = visualizations.get("pages", []) if isinstance(visualizations, dict) else []

    injected_count = 0
    for page in pages:
        for vis in page.get("visuals", []):
            if vis.get("visual_type") == "image" and not vis.get("imageUrl"):
                vid = vis.get("visual_id", "")
                # Try matching by visual_id (which comes from zone id)
                if vid in image_url_map:
                    vis["imageUrl"] = image_url_map[vid]
                    injected_count += 1

    if injected_count:
        print(f"[Tableau] Injected imageUrl into {injected_count} image visuals (no LLM needed)")


def _build_table_columns_map(final_parsed: dict, calc_names: set) -> Dict[str, set]:
    """Map each table id to its set of non-calculated column names."""
    table_columns_map: Dict[str, set] = {}
    for tbl in final_parsed.get("tables", []):
        tbl_id = tbl.get("id", "")
        base_cols = {
            col.get("name", "")
            for col in tbl.get("columns", [])
            if col.get("name", "") not in calc_names
        }
        table_columns_map[tbl_id] = base_cols
    return table_columns_map


def _deduplicate_calculated_columns(final_parsed: dict) -> None:
    """Remove calculated columns from tables that do not own their dependencies."""
    calc_names = {calc.get("name", "") for calc in final_parsed.get("calculations", [])}
    if not calc_names:
        return

    calc_deps: Dict[str, set] = {
        calc.get("name", ""): set(calc.get("depends_on_columns") or [])
        for calc in final_parsed.get("calculations", [])
    }
    table_columns_map = _build_table_columns_map(final_parsed, calc_names)

    removed_count = 0
    for tbl in final_parsed.get("tables", []):
        tbl_id = tbl.get("id", "")
        base_cols = table_columns_map.get(tbl_id, set())
        filtered_cols = []
        for col in tbl.get("columns", []):
            col_name = col.get("name", "")
            if col_name in calc_names:
                deps = calc_deps.get(col_name, set())
                if deps and deps & base_cols:
                    filtered_cols.append(col)
                else:
                    removed_count += 1
            else:
                filtered_cols.append(col)
        tbl["columns"] = filtered_cols

    if removed_count:
        print(f"[Tableau] Post-processing: removed {removed_count} duplicated calculated column(s) from wrong tables")
        logger.info("Post-processing: removed %d duplicated calculated columns", removed_count)


def _drop_phantom_calc_columns(final_parsed: dict, context: Any = None, quality: Any = None) -> None:
    """Drop ``tables[].columns[]`` entries that are actually CALCULATED fields
    masquerading as physical source columns.

    Root cause this fixes (observed: a boolean ``NULL Invoices`` calc):
    the extraction agent sometimes emits a Tableau calculated field BOTH as a
    measure in ``calculations[]`` AND as a column on a table with
    ``expression: null``. A null-expression column is, to the downstream
    converter, a PHYSICAL ``sourceColumn`` that must exist in the source CSV /
    extract. It doesn't — so Power BI Desktop fails at load with
    "The column '<name>' of the table wasn't found." for every table.

    The authoritative "this is a calculated field, not a physical column"
    signal is the Tableau workbook itself: ``context.model['calculations']``
    lists every calculated field by caption. (Tableau forbids a physical column
    and a calculated field sharing a caption within a datasource, so a name in
    the caption set is definitively a calc, never a source column.)

    A column is dropped when ALL of:
      * its name matches a Tableau calculated-field caption, AND
      * it carries no ``expression`` of its own (so it would be emitted as a
        bare physical sourceColumn), AND
      * an equivalent measure already exists in ``calculations[]`` — matched by
        exact name OR by the ``"<caption> (<home_table>)"`` disambiguation shape
        produced by _normalize_calculation_names — so the calc's logic is not
        lost by removing the phantom column.

    When the first two hold but no measure exists (the calc was dropped from
    calculations[]), the column is KEPT and a warning is recorded, because
    silently deleting it would lose the field entirely.

    Idempotent. No-op when context is unavailable.
    """
    if context is None:
        return
    model = getattr(context, "model", None) or {}
    calc_captions = {
        (c.get("caption") or "").strip()
        for c in model.get("calculations", [])
        if (c.get("caption") or "").strip()
    }
    if not calc_captions:
        return

    measure_names = {
        (calc.get("name") or "").strip()
        for calc in final_parsed.get("calculations", [])
        if (calc.get("name") or "").strip()
    }

    def _measure_exists_for(col_name: str) -> bool:
        # Exact match, or the disambiguated "<col_name> (<home_table>)" shape.
        if col_name in measure_names:
            return True
        prefix = col_name + " ("
        return any(m.startswith(prefix) for m in measure_names)

    removed = 0
    kept_orphans = 0
    for tbl in final_parsed.get("tables", []):
        cols = tbl.get("columns", [])
        if not cols:
            continue
        filtered = []
        for col in cols:
            name = (col.get("name") or "").strip()
            has_expr = bool((col.get("expression") or "").strip())
            if name and (not has_expr) and name in calc_captions:
                if _measure_exists_for(name):
                    removed += 1
                    continue  # drop the phantom physical column
                # Calc field with no expression and no backing measure — keep it
                # rather than lose the field, but flag the gap.
                kept_orphans += 1
                if quality is not None:
                    quality.warn(
                        "phantom_calc_column",
                        f"calc field '{name}' on table '{tbl.get('name')}' has no "
                        f"expression and no matching measure; kept to avoid data loss",
                    )
            filtered.append(col)
        tbl["columns"] = filtered

    if removed:
        print(f"[Tableau] Post-processing: dropped {removed} phantom calc column(s) "
              f"(calculated fields wrongly emitted as physical source columns)")
        logger.info("Post-processing: dropped %d phantom calc columns", removed)
        if quality is not None:
            quality.repair(
                "phantom_calc_column",
                f"dropped {removed} calc field(s) duplicated as null-expression "
                f"source columns (would cause 'column ... wasn't found' at PBI load)",
            )
    if kept_orphans:
        print(f"[Tableau] Post-processing: WARNING kept {kept_orphans} calc column(s) "
              f"with no expression and no backing measure")


def _reclassify_measure_dependencies(final_parsed: dict, quality: Any = None) -> None:
    """Move physical-column names out of ``calculations[].depends_on_measures``.

    Root cause this fixes (observed: ``Profit %`` with
    ``depends_on_measures = ["Profit (Baseline)", "Sales"]`` where ``Sales`` is a
    physical column, not a measure):

    The downstream converter's mapper DROPS any measure whose
    ``depends_on_measures`` contains a bare name that resolves to neither a known
    measure nor a parameter/bracketed reference — on the assumption it points at
    a missing measure that would cause a #ERROR cascade. A physical column name
    sitting in that list is therefore fatal: the whole measure is silently
    removed and every visual bound to it renders blank.

    This pass walks every calculation and, for each ``depends_on_measures`` entry
    that is NOT a known measure name but IS a known physical column, removes it
    from ``depends_on_measures`` and adds it (qualified as ``Table.Column``) to
    ``depends_on_columns`` instead. Entries that are real measures, parameters,
    or bracket/dot-qualified references are left untouched.

    The DAX body itself is unaffected — the converter re-derives column refs from
    the expression — so this only repairs the lineage classification the mapper
    uses for its drop decision. Idempotent.
    """
    calcs = final_parsed.get("calculations") or []
    if not calcs:
        return

    measure_names = {(c.get("name") or "").strip() for c in calcs if (c.get("name") or "").strip()}

    # column name -> set of owning table names (for Table.Column qualification)
    col_owners: Dict[str, set] = {}
    for tbl in final_parsed.get("tables", []):
        tname = tbl.get("name") or ""
        for col in tbl.get("columns", []):
            cname = (col.get("name") or "").strip()
            if cname:
                col_owners.setdefault(cname, set()).add(tname)

    moved = 0
    for calc in calcs:
        dom = calc.get("depends_on_measures")
        if not isinstance(dom, list) or not dom:
            continue
        home = (calc.get("home_table") or "").strip()
        new_dom: List[str] = []
        doc = calc.get("depends_on_columns")
        doc = doc if isinstance(doc, list) else []
        doc_changed = False
        for dep in dom:
            if not isinstance(dep, str):
                new_dom.append(dep)
                continue
            d = dep.strip()
            # Keep real measures, and anything already bracket/dot-qualified
            # (parameters, external refs) — the mapper tolerates those.
            if d in measure_names or "." in d or "[" in d or "]" in d:
                new_dom.append(dep)
                continue
            owners = col_owners.get(d)
            if owners:
                # It's a physical column wrongly listed as a measure dependency.
                # Qualify against the calc's home table if it owns the column,
                # else any owning table (deterministic: sorted).
                owner = home if home in owners else sorted(owners)[0]
                qualified = f"{owner}.{d}"
                if qualified not in doc:
                    doc.append(qualified)
                    doc_changed = True
                moved += 1
                continue
            # Unknown bare name — leave it (genuinely a missing measure ref;
            # the mapper's drop is then the correct behaviour).
            new_dom.append(dep)
        calc["depends_on_measures"] = new_dom
        if doc_changed:
            calc["depends_on_columns"] = doc

    if moved:
        print(f"[Tableau] Post-processing: reclassified {moved} physical column(s) "
              f"from depends_on_measures to depends_on_columns")
        logger.info("Post-processing: reclassified %d measure-deps to column-deps", moved)
        if quality is not None:
            quality.repair(
                "measure_dependency",
                f"moved {moved} physical-column name(s) out of depends_on_measures "
                f"(would have caused the measure to be dropped downstream)",
            )


# Tableau spatial constructors. A calc whose formula STARTS with one of these
# returns a geometry/point value (Tableau datatype 'spatial'), not a string.
_SPATIAL_FUNC_RE = re.compile(
    r"^\s*(MAKEPOINT|MAKELINE|BUFFER|DISTANCE)\s*\(", re.IGNORECASE
)


def _fix_spatial_calc_types(final_parsed: dict, quality: Any = None) -> None:
    """Type spatial calculated fields as ``data_type='spatial'``.

    The extraction LLM types a ``MAKEPOINT(...)`` / ``MAKELINE(...)`` calc as
    ``string`` (its default for anything non-obvious). These produce geometry
    values, not text. The downstream converter has no DAX equivalent for spatial
    constructs and drops them, but the mislabelled type is still wrong in the
    common model and misleads any consumer reading data_type. This pass sets the
    correct ``spatial`` type from the formula head. Idempotent."""
    fixed = 0
    for calc in (final_parsed.get("calculations") or []):
        exprs = calc.get("expressions") or {}
        body = (exprs.get("tableau") or calc.get("expression") or "")
        if isinstance(body, str) and _SPATIAL_FUNC_RE.match(body):
            if (calc.get("data_type") or "").lower() != "spatial":
                calc["data_type"] = "spatial"
                fixed += 1
    if fixed:
        print(f"[Tableau] Post-processing: typed {fixed} spatial calc(s) as 'spatial'")
        logger.info("Post-processing: typed %d spatial calcs", fixed)
        if quality is not None:
            quality.repair(
                "spatial_calc_type",
                f"typed {fixed} MAKEPOINT/MAKELINE calc(s) as data_type='spatial' "
                f"(LLM had defaulted them to 'string')",
            )


_ALIAS_DIGIT_SUFFIX_RE = re.compile(r"^(?P<base>.+?)(?P<n>\d+)$")

# A DAX table identifier may be written unquoted ONLY when it is a simple
# identifier (letter/underscore start, then word chars). Anything else — spaces,
# hyphens (e.g. tbl_state-region-mapping), dots — MUST be single-quoted.
_DAX_BARE_TABLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _dax_table_ref(name: str) -> str:
    """Return a valid DAX table reference: bare when it's a simple identifier,
    single-quoted (with internal quotes doubled) otherwise."""
    n = (name or "").strip()
    if _DAX_BARE_TABLE_RE.match(n):
        return n
    return "'" + n.replace("'", "''") + "'"


def _tag_self_join_aliases(final_parsed: dict, quality: Any = None) -> None:
    """Tag Tableau self-join ALIAS tables with ``source_derived_from_table_id``
    so the downstream converter loads them from the BASE table's physical CSV.

    Root cause this addresses (observed across several runs):

    A Tableau self-join references one physical relation twice under an alias
    (``tbl_sales`` joined to ``tbl_sales1``). There is only ONE physical file
    (``tbl_sales.csv``); ``tbl_sales1`` is just ``tbl_sales`` again. The alias
    must still exist as its own TABLE because visuals and a self-join
    relationship bind to ``tbl_sales1`` columns.

    Two wrong shapes were tried and both failed:
      * imported table named tbl_sales1 → converter builds a partition that
        loads ``tbl_sales1.csv`` (does not exist) → "key didn't match any rows".
      * calculated table (``alias = base`` or SELECTCOLUMNS) → its columns are
        emitted ``isNameInferred`` (resolved only after the partition runs), but
        Power BI validates relationships BEFORE that, so a self-join relationship
        endpoint on an alias column is an "invalid column ID".

    The CORRECT shape is a PHYSICAL imported table whose partition loads the
    BASE table's CSV under the alias name. Its columns are then real physical
    columns with stable IDs — structurally identical to every other imported
    table — so relationships bind and the data loads. The only thing the alias
    must NOT do is look for its own ``<alias>.csv``.

    The converter cannot infer the base file from the alias name alone, so this
    pass records the link in the common-model field ``source_derived_from_table_id``
    (already part of the schema). The converter's writer honours that field:
    when set, it resolves the partition CSV from the base table instead of the
    alias name. PowerBI/QlikView never set this field, so the converter change
    is inert for them.

    A table T is treated as a self-join alias of base B when EITHER:
      * ``source_derived_from_table_id`` already names an existing table B
        (authoritative — the extraction agent set it per the self-join rule), OR
      * T's name matches ``<B><digits>`` where B is an existing table AND T's
        physical (non-expression) columns are a subset of B's columns — the
        standard Tableau ``<base>1`` alias convention, guarded by a schema match
        so an unrelated table that merely ends in a digit is never touched.

    For each detected alias the pass ONLY sets ``table_type='fact'`` (a real
    imported table; never 'calculated') and ``source_derived_from_table_id=B``.
    It does NOT rewrite ingestion to a DAX body — the alias stays a physical
    import. Idempotent.
    """
    tables = final_parsed.get("tables") or []
    if not tables:
        return

    by_name = {(t.get("name") or "").strip(): t for t in tables if (t.get("name") or "").strip()}

    def _physical_cols(tbl: dict) -> set:
        return {
            (c.get("name") or "").strip()
            for c in tbl.get("columns", [])
            if (c.get("name") or "").strip() and not (c.get("expression") or "").strip()
        }

    def _resolve_base(tbl: dict) -> Optional[str]:
        name = (tbl.get("name") or "").strip()
        # 1) authoritative: explicit derived-from pointer to a real, different table
        derived = (tbl.get("source_derived_from_table_id") or "").strip()
        if derived and derived in by_name and derived != name:
            return derived
        # 2) <base><digits> convention + physical-schema subset guard
        m = _ALIAS_DIGIT_SUFFIX_RE.match(name)
        if not m:
            return None
        base = m.group("base")
        if base and base in by_name and base != name:
            base_cols = _physical_cols(by_name[base])
            alias_cols = _physical_cols(tbl)
            if alias_cols and base_cols and alias_cols <= base_cols:
                return base
        return None

    tagged = 0
    for tbl in tables:
        name = (tbl.get("name") or "").strip()
        if not name:
            continue
        base = _resolve_base(tbl)
        if not base:
            continue
        # The alias must be a PHYSICAL imported table (so its columns get stable
        # IDs and relationships bind). Undo any prior calc-table conversion and
        # drop a DAX-body ingestion step if one was added by an earlier pass.
        already = (
            tbl.get("source_derived_from_table_id") == base
            and tbl.get("table_type") in ("fact", "dimension", "lookup", "bridge")
        )
        tbl["source_derived_from_table_id"] = base
        if tbl.get("table_type") in (None, "", "calculated"):
            tbl["table_type"] = "fact"
        # If a previous run made this a calculated table, strip the synthetic
        # DAX-calculated-table step so the converter treats it as an import.
        steps = (tbl.get("ingestion") or {}).get("steps", []) or []
        cleaned_steps = [
            s for s in steps
            if s.get("step_type") != "dax_calculated_table"
            and not (s.get("native_expressions") or {}).get("dax")
        ]
        if cleaned_steps != steps:
            tbl["ingestion"] = {"steps": cleaned_steps}
        if not already:
            tagged += 1

    if tagged:
        print(f"[Tableau] Post-processing: tagged {tagged} self-join alias table(s) "
              f"with source_derived_from_table_id (converter loads base CSV)")
        logger.info("Post-processing: tagged %d self-join alias tables (derived-from)", tagged)
        if quality is not None:
            quality.repair(
                "self_join_alias",
                f"tagged {tagged} self-join alias table(s) with "
                f"source_derived_from_table_id so the converter loads the base "
                f"table's CSV under the alias (real physical columns; relationships bind)",
            )


def _ensure_calculated_table_bodies(final_parsed: dict, quality: Any = None) -> None:
    """Guarantee every ``calculated`` table has a NON-EMPTY DAX body under the
    ``dax`` native-expression key.

    Why (observed: the synthesized ``Parameters`` table failing PBI refresh with
    "The key didn't match any rows in the table"):

    A calculated table's body is written VERBATIM by the downstream converter as
    the TMDL ``partition = calculated; source = <body>`` — there is NO LLM
    translation step for table bodies (unlike measures, whose Tableau syntax the
    converter's DaxConverterAgent translates). The converter reads the body from
    ``ingestion.steps[].native_expressions`` trying keys in the order
    ``dax → powerquery → powerbi → tableau``. If NO key holds a non-empty value,
    the converter cannot see a calculated body, falls back to treating the table
    as an imported CSV, and emits ``Csv.Document(... Name="<table>.csv" ...)`` —
    a file that does not exist — so refresh fails with the "key didn't match"
    error.

    The extraction agent has been observed to emit the Parameters home table with
    an EMPTY body under the wrong key (``native_expressions: {"tableau": ""}``).
    This pass repairs any calculated table whose resolved body is empty:

      * ``Parameters`` (the synthesized measure-host table) → ``ROW("Value", BLANK())``
        a minimal one-row DAX table that hosts parameter measures.
      * any other calculated table with an empty body → ``ROW("Value", BLANK())``
        as a safe non-empty placeholder so it renders as a calculated partition
        rather than a phantom CSV (and a warning is recorded so the gap is visible).

    Idempotent. A calculated table that already has a non-empty body in ANY of
    the recognised keys is left untouched.
    """
    PARAM_BODY = 'ROW("Value", BLANK())'
    repaired = 0
    for tbl in final_parsed.get("tables", []):
        if tbl.get("table_type") != "calculated":
            continue
        name = (tbl.get("name") or "").strip()
        steps = (tbl.get("ingestion") or {}).get("steps", []) or []
        # Resolve the body the converter would see (same key order it uses).
        body = ""
        for s in steps:
            ne = s.get("native_expressions") or {}
            body = (ne.get("dax") or ne.get("powerquery") or ne.get("powerbi")
                    or ne.get("tableau") or "")
            if isinstance(body, str) and body.strip():
                break
        if isinstance(body, str) and body.strip():
            continue  # already has a usable body

        tbl["ingestion"] = {
            "steps": [
                {
                    "order": 1,
                    "step_type": "dax_calculated_table",
                    "description": (
                        "Synthesized Parameters home table (hosts parameter measures)."
                        if name == "Parameters"
                        else f"Calculated table '{name}' (body backfilled)."
                    ),
                    "native_expressions": {"dax": PARAM_BODY},
                }
            ]
        }
        repaired += 1
        if name != "Parameters" and quality is not None:
            quality.warn(
                "calc_table_body",
                f"calculated table '{name}' had no body; backfilled a placeholder "
                f"DAX table so it does not fall back to a non-existent CSV",
            )

    if repaired:
        print(f"[Tableau] Post-processing: backfilled DAX body on {repaired} "
              f"calculated table(s) with an empty body (avoids phantom CSV at PBI refresh)")
        logger.info("Post-processing: backfilled %d empty calculated-table bodies", repaired)
        if quality is not None:
            quality.repair(
                "calc_table_body",
                f"backfilled a valid DAX body on {repaired} calculated table(s) "
                f"(empty body would fall back to a non-existent CSV at PBI refresh)",
            )


# Higher value wins when merging the same column from federated duplicates.
_SEMANTIC_ROLE_PRIORITY = {
    "foreign_key": 5,
    "primary_key": 4,
    "identifier":  3,
    "measure":     2,
    "date":        2,
    "dimension":   1,
}


def _read_source_path(tbl: dict) -> str:
    """Extract the physical source path from a table's read_source ingestion step."""
    for step in (tbl.get("ingestion") or {}).get("steps", []):
        if step.get("step_type") != "read_source":
            continue
        native = (step.get("native_expressions") or {}).get("tableau") or ""
        # Tableau ingestion text shape: "READ csv / path: tbl_sales.csv"
        m = re.search(r"path:\s*([^\s]+)", native)
        if m:
            return m.group(1).strip().lower()
    return ""


def _merge_duplicate_table(target: dict, dup: dict) -> None:
    """Fold *dup*'s extra information into *target* in place.

    Used when two tables[] rows describe the same physical table referenced from
    two different Tableau datasources (federation duplicate). We keep *target*
    and:
      - union the boolean usage flags on each column
      - promote each column's semantic_role to the more specific value
      - append any column the dup carries that target doesn't already have
      - append non-duplicate ingestion steps
    """
    target_cols = {(c.get("name") or ""): c for c in target.get("columns", [])}
    for col in dup.get("columns", []):
        name = col.get("name") or ""
        if not name:
            continue
        if name in target_cols:
            tcol = target_cols[name]
            for flag in (
                "used_in_relationships",
                "used_in_filters",
                "used_in_groupby",
                "used_in_calculations",
            ):
                tcol[flag] = bool(tcol.get(flag)) or bool(col.get(flag))
            existing_priority = _SEMANTIC_ROLE_PRIORITY.get(tcol.get("semantic_role"), 0)
            incoming_priority = _SEMANTIC_ROLE_PRIORITY.get(col.get("semantic_role"), 0)
            if incoming_priority > existing_priority:
                tcol["semantic_role"] = col.get("semantic_role")
        else:
            target.setdefault("columns", []).append(col)
            target_cols[name] = col

    target_steps = target.setdefault("ingestion", {}).setdefault("steps", [])
    seen_steps = {
        (
            s.get("step_type"),
            json.dumps(s.get("native_expressions") or {}, sort_keys=True),
        )
        for s in target_steps
    }
    for step in (dup.get("ingestion") or {}).get("steps", []):
        key = (
            step.get("step_type"),
            json.dumps(step.get("native_expressions") or {}, sort_keys=True),
        )
        if key not in seen_steps:
            target_steps.append(step)
            seen_steps.add(key)


def _rewrite_parameter_references(final_parsed: dict, parameters: List[Dict[str, Any]]) -> None:
    """Substitute Tableau parameter internal IDs (e.g. ``[Parameter 1]``) with
    their captions (e.g. ``[What if Quantity]``) everywhere they appear in the
    final JSON.

    Tableau stores parameters with a stable internal ``name`` (used inside every
    formula and field reference) and a human ``caption`` (shown in the UI). The
    LLM tends to register the parameter under its caption while leaving formulas
    and depends_on_measures pointing at the internal ID, which leaves downstream
    consumers with dangling references. This pass normalizes both sides to the
    caption.
    """
    alias_map: Dict[str, str] = {}
    for p in parameters or []:
        internal = (p.get("internal_name") or "").strip("[]")
        caption = p.get("name") or ""
        if internal and caption and internal != caption:
            alias_map[internal] = caption
    if not alias_map:
        return

    def rewrite(text: str) -> str:
        for internal, caption in alias_map.items():
            text = text.replace(f"[{internal}]", f"[{caption}]")
        if text in alias_map:
            return alias_map[text]
        return text

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(v, str):
                    node[k] = rewrite(v)
                else:
                    walk(v)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                if isinstance(item, str):
                    node[i] = rewrite(item)
                else:
                    walk(item)

    walk(final_parsed)


# Tableau pseudo-fields used to pivot multiple measures onto a single axis.
_AGG_TOKEN_MAP = {
    "sum": "Sum", "avg": "Average", "cnt": "Count", "cntd": "CountDistinct",
    "min": "Min", "max": "Max", "med": "Median", "stdev": "StdDev",
    "var": "Var", "attr": "AttributeOnly",
}
_FIELD_REF_SUFFIXES = {"qk", "nk", "ok"}


def _is_measure_names_field(field: Dict[str, Any]) -> bool:
    """True if a visual field is the Tableau [:Measure Names] series placeholder."""
    col = (field.get("column") or "").strip()
    qr = (field.get("query_ref") or "").strip()
    return col in ("[:Measure Names]", ":Measure Names") or qr.endswith(".[:Measure Names]")


def _is_multiple_values_field(field: Dict[str, Any]) -> bool:
    """True if a visual field is the Tableau [Multiple Values] axis placeholder."""
    col = (field.get("column") or "").strip()
    qr = (field.get("query_ref") or "").strip()
    return col == "Multiple Values" or qr.endswith(".[Multiple Values]")


def _visual_worksheet_names(visual: Dict[str, Any]) -> List[str]:
    """Collect candidate Tableau worksheet names backing a visual.

    A visual's ``title`` is usually the worksheet name, but a worksheet reused
    across dashboard zones can carry the zone's name instead (e.g. a "(small)"
    duplicate). The true worksheet name is also stamped on per-worksheet
    sub-objects (``axes``, ``reference_lines`` ...), so gather all of them.
    """
    names: List[str] = []
    title = (visual.get("title") or "").strip()
    if title:
        names.append(title)
    for key in ("axes", "reference_lines", "trend_lines", "annotations", "sort_config"):
        for item in visual.get(key) or []:
            if isinstance(item, dict):
                wn = (item.get("worksheet") or "").strip()
                if wn and wn not in names:
                    names.append(wn)
    return names


def _decode_measure_member(member_ref: str) -> Optional[Dict[str, str]]:
    """Decode a Tableau measure member reference into its parts.

    Input:  ``[federated.xxx].[cum:sum:Calculation_123:qk]``
    Returns ``{table, inner, name, aggregation}`` or None if it cannot be parsed.
    ``name`` is the raw column / calculation token; ``aggregation`` is the
    human-readable aggregation (empty for non-aggregated references).
    """
    m = re.match(r'\[([^\]]+)\]\.\[([^\]]+)\]', member_ref.strip().strip('"'))
    if not m:
        return None
    table, inner = m.group(1), m.group(2)
    segments = inner.split(":")
    body = segments[:-1] if (len(segments) > 1 and segments[-1] in _FIELD_REF_SUFFIXES) else segments
    if not body:
        return None
    name = body[-1]
    aggregation = ""
    for seg in body[:-1]:
        if seg in _AGG_TOKEN_MAP:
            aggregation = _AGG_TOKEN_MAP[seg]
            break
    return {"table": table, "inner": inner, "name": name, "aggregation": aggregation}


def _expand_measure_names_fields(final_parsed: dict, model: dict) -> None:
    """Expand Tableau [:Measure Names] / [Multiple Values] placeholder fields.

    Tableau collapses a multi-measure axis into two pseudo-fields: [Multiple
    Values] on the value shelf and [:Measure Names] on the color/series shelf.
    Power BI has no equivalent — each measure binds directly to the value
    bucket. This pass rewrites a visual's ``fields[]`` so the placeholder pair
    becomes one ``role="Y"`` field per concrete measure.

    The authoritative measure list comes from the worksheet-scoped categorical
    filter on [:Measure Names]; display labels come from the [:Measure Names]
    column aliases (falling back to calculation captions, then the raw token).

    ONLY ``fields[]`` is rewritten. ``axes[]``, ``conditional_formatting[]`` and
    ``legends[]`` keep referencing the placeholders — they remain valid there.
    A visual that already carries concrete ``role="Y"`` measures only has the
    placeholders dropped; a visual whose measures cannot be resolved is left
    untouched so it never ends up with no measure binding.
    """
    # 1. member_ref -> display label, from [:Measure Names] column aliases.
    alias_label: Dict[str, str] = {}
    for ds_map in (model.get("measure_names_aliases") or {}).values():
        for ref, label in ds_map.items():
            alias_label.setdefault(ref, label)
    alias_order = list(alias_label.keys())  # declaration order

    # 2. calc-id -> caption, used as a fallback label source.
    calc_caption: Dict[str, str] = {}
    for calc in model.get("calculations") or []:
        internal = (calc.get("internal_name") or "").strip("[]")
        caption = calc.get("caption") or ""
        if internal and caption and internal != caption:
            calc_caption[internal] = caption

    # 3. worksheet name (lowercased) -> ordered list of measure member refs.
    ws_members: Dict[str, List[str]] = {}
    for filt in model.get("filters") or []:
        if (filt.get("class") or "") != "categorical":
            continue
        if (filt.get("scope") or "") != "worksheet":
            continue
        if not (filt.get("column") or "").endswith(".[:Measure Names]"):
            continue
        ctx_name = (filt.get("context") or "").strip().lower()
        members = [
            (v or "").strip().strip('"')
            for v in (filt.get("include_values") or [])
            if (v or "").strip()
        ]
        if ctx_name and members:
            ws_members.setdefault(ctx_name, []).extend(members)

    def order_members(members: List[str]) -> List[str]:
        """Dedupe members, keeping the alias declaration order where known."""
        unique = list(dict.fromkeys(members))
        ranked = [m for m in alias_order if m in unique]
        ranked += [m for m in unique if m not in ranked]
        return ranked

    def label_for(member_ref: str, decoded: Dict[str, str]) -> str:
        if member_ref in alias_label:
            return alias_label[member_ref]
        name = decoded["name"]
        return calc_caption.get(name, name)

    expanded_visuals = 0
    synthesized_fields = 0

    for page in (final_parsed.get("visualizations") or {}).get("pages", []) or []:
        for visual in page.get("visuals", []) or []:
            fields = visual.get("fields")
            if not isinstance(fields, list) or not fields:
                continue
            if not any(_is_measure_names_field(f) for f in fields):
                continue

            kept = [
                f for f in fields
                if not _is_measure_names_field(f) and not _is_multiple_values_field(f)
            ]
            has_real_y = any((f.get("role") or "") == "Y" for f in kept)

            if has_real_y:
                # Concrete measures already present — just drop the placeholders.
                visual["fields"] = kept
                expanded_visuals += 1
                continue

            # No concrete measures — synthesize them from the worksheet filter.
            members: List[str] = []
            for ws_name in _visual_worksheet_names(visual):
                found = ws_members.get(ws_name.strip().lower())
                if found:
                    members = found
                    break
            new_y_fields: List[Dict[str, Any]] = []
            for member_ref in order_members(members):
                decoded = _decode_measure_member(member_ref)
                if not decoded:
                    continue
                label = label_for(member_ref, decoded)
                table = decoded["table"]
                friendly_inner = decoded["inner"].replace(decoded["name"], label)
                new_y_fields.append({
                    "role": "Y",
                    "table": table,
                    "column": label,
                    "aggregation": decoded["aggregation"],
                    "query_ref": f"[{table}].[{friendly_inner}]",
                })

            if new_y_fields:
                visual["fields"] = kept + new_y_fields
                synthesized_fields += len(new_y_fields)
                expanded_visuals += 1
            # else: cannot resolve measures — leave the visual untouched.

    if expanded_visuals:
        print(f"[Tableau] Post-processing: expanded Measure Names placeholders in "
              f"{expanded_visuals} visual(s), synthesized {synthesized_fields} measure field(s)")
        logger.info(
            "Post-processing: expanded Measure Names in %d visual(s), synthesized %d field(s)",
            expanded_visuals, synthesized_fields,
        )


def _fix_visual_field_tables(final_parsed: dict, context: Optional[Any] = None) -> None:
    """Re-route each visual field's ``table`` to the table that actually owns the
    referenced column or measure in the common model, then rewrite the matching
    ``query_ref`` prefix.

    Tableau encodes shelf/encoding fields as ``[<federation_id>].[<col>]`` where
    ``federation_id`` is a Tableau-internal datasource id (``federated.XXX``),
    not a physical table. The LLM tries to map these to a real table from
    ``tables[]`` but often guesses wrong for:
      - measures (which live where ``calculations[].home_table`` says),
      - columns shared by name across multiple federated datasources
        (e.g. ``Sales`` exists in both ``tbl_sales`` and ``tbl_sales1``),
      - Tableau-generated geo fields (``Latitude (generated)`` etc.), which
        have no physical column at all — they are derived per-worksheet from
        whichever dimension carries a geographic semantic-role.

    Wrong ``field.table`` leaks ``federated.XXX`` into downstream output and
    causes PBI column resolution to fail; the visual then renders blank.

    Resolution rules (in order):
      1. If column is a Tableau-generated geo field, route to the source
         worksheet's geo-rolled dimension's physical table.
      2. If column matches a calculation name, route to its ``home_table``.
      3. If current table is a ``federated.XXX`` id, resolve via the
         datasource's ``<cols>`` map (scoped to the visual's actual
         datasource — never cross-datasource).
      4. Otherwise, pick a table that owns the column AND belongs to one of
         the visual's declared datasources (prevents the cross-datasource
         phantom-table bug).
      5. Fall back to the friendly datasource caption when no physical table
         can be determined, so ``federated.XXX`` never leaks into the output.
    """
    tables = final_parsed.get("tables", []) or []

    # Column name → list of physical tables that contain it.
    column_to_tables: Dict[str, List[str]] = {}
    for t in tables:
        tn = t.get("name")
        if not tn:
            continue
        for c in t.get("columns", []) or []:
            cn = c.get("name")
            if cn:
                column_to_tables.setdefault(cn, []).append(tn)

    # Measure (calculation) name → home table.
    measure_to_table: Dict[str, str] = {}
    for calc in final_parsed.get("calculations", []) or []:
        nm = calc.get("name")
        ht = calc.get("home_table")
        if nm and ht:
            measure_to_table[nm] = ht

    # ---- Maps derived from the preprocessed context (source-of-truth XML) ----
    # federated.XXX -> friendly datasource caption
    federated_to_caption: Dict[str, str] = {}
    # caption -> {column_caption (lowercased and exact) -> physical table name}
    datasource_columns: Dict[str, Dict[str, str]] = {}
    # worksheet name -> physical table that "(generated)" geo fields belong to
    worksheet_geo_source: Dict[str, str] = {}

    if context is not None:
        for ds in (context.model.get("datasources", []) or []):
            internal = ds.get("internal_name", "") or ""
            caption = ds.get("name", "") or ds.get("caption", "") or ""
            if internal and caption:
                federated_to_caption[internal] = caption
            cmap = ds.get("cols_map") or {}
            if caption and cmap:
                ds_cols = datasource_columns.setdefault(caption, {})
                for col_caption, mapping in cmap.items():
                    phys = (mapping or {}).get("table", "")
                    if phys:
                        ds_cols[col_caption] = phys
                        ds_cols[col_caption.lower()] = phys

        for ws in (context.visuals.get("worksheets", []) or []):
            ws_name = ws.get("name", "")
            geo_col = ws.get("geo_source_column", "")
            geo_ds_id = ws.get("geo_source_datasource_id", "")
            if not (ws_name and geo_col and geo_ds_id):
                continue
            geo_ds_caption = federated_to_caption.get(geo_ds_id, "")
            if not geo_ds_caption:
                continue
            ds_cols = datasource_columns.get(geo_ds_caption, {})
            phys = ds_cols.get(geo_col) or ds_cols.get(geo_col.lower())
            if phys:
                worksheet_geo_source[ws_name] = phys

    def visual_to_worksheet_name(visual: Dict[str, Any]) -> str:
        # Visual id pattern: ...$<worksheet_name>(visual)$<uuid>(uuid)
        vid = visual.get("id", "") or ""
        m = re.search(r'\$([^$]+?)\(visual\)', vid)
        if m:
            return m.group(1)
        # Fall back to title — typically matches the worksheet name.
        return visual.get("title", "") or ""

    def resolve(field: Dict[str, Any], visual_ds_deps: List[str], ws_name: str) -> Optional[str]:
        col = field.get("column")
        cur = field.get("table") or ""
        if not col:
            return None

        # 1) Tableau-generated geo fields → worksheet's geo source physical table.
        if col in _GEO_GENERATED_FIELDS:
            phys = worksheet_geo_source.get(ws_name)
            if phys:
                return phys

        # 2) Measures resolve to their home table.
        if col in measure_to_table:
            return measure_to_table[col]

        # 3) Current table is a Tableau-internal federated id → resolve via the
        # owning datasource's cols_map; never cross datasource boundaries.
        if cur.startswith("federated."):
            caption = federated_to_caption.get(cur, "")
            if caption:
                ds_cols = datasource_columns.get(caption, {})
                phys = ds_cols.get(col) or ds_cols.get((col or "").lower())
                if phys:
                    return phys
            # Try resolving via the visual's declared datasource_dependencies.
            for dep_caption in visual_ds_deps:
                ds_cols = datasource_columns.get(dep_caption, {})
                phys = ds_cols.get(col) or ds_cols.get((col or "").lower())
                if phys:
                    return phys
            # Final fallback: friendly caption so federated.XXX never leaks.
            if caption:
                return caption
            if visual_ds_deps:
                return visual_ds_deps[0]

        # 4) Restrict the candidate owners to tables that belong to one of the
        # visual's declared datasources. This prevents the cross-datasource
        # phantom-table bug (e.g. attributing Product Sales' Sales to tbl_sales1
        # just because both datasources have a column called Sales).
        owners = column_to_tables.get(col) or []
        if owners and visual_ds_deps:
            scoped: List[str] = []
            for dep_caption in visual_ds_deps:
                ds_tables = set(datasource_columns.get(dep_caption, {}).values())
                if not ds_tables:
                    continue
                scoped.extend(o for o in owners if o in ds_tables and o not in scoped)
            if scoped:
                if cur in scoped:
                    return cur
                return scoped[0]

        # 5) No datasource scoping possible — fall back to original behavior.
        if owners:
            if cur in owners:
                return cur
            return owners[0]
        return None

    def rewrite_query_ref(qr: Optional[str], new_table: str) -> Optional[str]:
        if not qr or not isinstance(qr, str):
            return qr
        if qr.startswith("["):
            end = qr.find("]")
            if end > 0:
                return f"[{new_table}]" + qr[end + 1:]
        return qr

    # Field-reference rewriter for free-form strings (sort_config, style_rules,
    # conditional_formatting, etc.). Tableau encodes these as
    # `[<datasource>].[<encoded_column>]` where <encoded_column> can be:
    #   - a real column like `sum:Sales:qk` → resolve via cols_map to its
    #     physical table.
    #   - a generated geo field like `Latitude (generated)` → use the
    #     worksheet's geo source table.
    #   - a calc id (`none:Calculation_XXX:nk`) or a placeholder
    #     (`[:Measure Names]`, `[Multiple Values]`) → fall back to the
    #     friendly datasource caption (no physical table exists for these).
    _field_ref_pattern = re.compile(r"^\[([^\]]+)\]\.\[(.+)\]$")
    _encoded_pattern = re.compile(r"^[a-z]+:([^:]+)(?::.+)?$")

    def extract_column_name(encoded: str) -> str:
        """Pull the plain column name out of an encoded column suffix.

        Examples:
          ``sum:Sales:qk`` → ``Sales``
          ``none:Calculation_NNN:nk`` → ``Calculation_NNN``
          ``Latitude (generated)`` → ``Latitude (generated)``
          ``:Measure Names`` → ``:Measure Names``
        """
        m = _encoded_pattern.match(encoded)
        if m:
            return m.group(1)
        return encoded

    def rewrite_field_ref(field_ref: Optional[str], ws_name: str,
                          visual_ds_deps: List[str]) -> Optional[str]:
        if not field_ref or not isinstance(field_ref, str):
            return field_ref
        m = _field_ref_pattern.match(field_ref)
        if not m:
            return field_ref
        prefix, encoded_col = m.group(1), m.group(2)
        if not prefix.startswith("federated."):
            return field_ref
        column = extract_column_name(encoded_col)
        # 1) Generated geo field → worksheet's geo source physical table
        if column in _GEO_GENERATED_FIELDS and worksheet_geo_source.get(ws_name):
            return f"[{worksheet_geo_source[ws_name]}].[{encoded_col}]"
        # 2) Real column → physical table from cols_map
        caption = federated_to_caption.get(prefix, "")
        if caption:
            ds_cols = datasource_columns.get(caption, {})
            phys = ds_cols.get(column) or ds_cols.get(column.lower())
            if phys:
                return f"[{phys}].[{encoded_col}]"
        # 3) Try scoping via the visual's declared datasource_dependencies
        for dep_caption in visual_ds_deps:
            ds_cols = datasource_columns.get(dep_caption, {})
            phys = ds_cols.get(column) or ds_cols.get(column.lower())
            if phys:
                return f"[{phys}].[{encoded_col}]"
        # 4) Fall back to the friendly datasource caption (calcs, placeholders,
        # or unmapped columns). Never leak federated.XXX downstream.
        if caption:
            return f"[{caption}].[{encoded_col}]"
        if visual_ds_deps:
            return f"[{visual_ds_deps[0]}].[{encoded_col}]"
        return field_ref

    def rewrite_dict_field_keys(d: Optional[Dict[str, Any]], ws_name: str,
                                visual_ds_deps: List[str]) -> Optional[Dict[str, Any]]:
        """Rewrite the federated-id prefix in each key of a {field_ref: value}
        mapping (used for color_assignments)."""
        if not isinstance(d, dict):
            return d
        out: Dict[str, Any] = {}
        for k, v in d.items():
            new_k = rewrite_field_ref(k, ws_name, visual_ds_deps) if isinstance(k, str) else k
            out[new_k or k] = v
        return out

    for page in final_parsed.get("visualizations", {}).get("pages", []) or []:
        for visual in page.get("visuals", []) or []:
            visual_ds_deps = visual.get("datasource_dependencies", []) or []
            ws_name = visual_to_worksheet_name(visual)

            # --- fields[] ---
            for f in visual.get("fields", []) or []:
                new_table = resolve(f, visual_ds_deps, ws_name)
                if new_table and new_table != f.get("table"):
                    f["table"] = new_table
                    f["query_ref"] = rewrite_query_ref(f.get("query_ref"), new_table)

            # --- sort_config[].column and .measure ---
            for s in visual.get("sort_config", []) or []:
                if not isinstance(s, dict):
                    continue
                for key in ("column", "measure"):
                    val = s.get(key)
                    if isinstance(val, str):
                        s[key] = rewrite_field_ref(val, ws_name, visual_ds_deps)

            # --- style_rules[].field ---
            for sr in visual.get("style_rules", []) or []:
                if not isinstance(sr, dict):
                    continue
                val = sr.get("field")
                if isinstance(val, str):
                    sr["field"] = rewrite_field_ref(val, ws_name, visual_ds_deps)

            # --- conditional_formatting[].field and .color_assignments keys ---
            for cf in visual.get("conditional_formatting", []) or []:
                if not isinstance(cf, dict):
                    continue
                val = cf.get("field")
                if isinstance(val, str):
                    cf["field"] = rewrite_field_ref(val, ws_name, visual_ds_deps)
                cf["color_assignments"] = rewrite_dict_field_keys(
                    cf.get("color_assignments"), ws_name, visual_ds_deps,
                )

            # --- axes[].field, legends[].field (when present) ---
            for ax in visual.get("axes", []) or []:
                if isinstance(ax, dict) and isinstance(ax.get("field"), str):
                    ax["field"] = rewrite_field_ref(ax["field"], ws_name, visual_ds_deps)
            for lg in visual.get("legends", []) or []:
                if isinstance(lg, dict) and isinstance(lg.get("field"), str):
                    lg["field"] = rewrite_field_ref(lg["field"], ws_name, visual_ds_deps)


def _normalize_generated_geo_for_pbi(final_parsed: dict, context: Optional[Any] = None) -> None:
    """Convert Tableau's ``Latitude (generated)`` / ``Longitude (generated)`` /
    ``Geometry (generated)`` bindings into a Power-BI-renderable shape.

    Tableau's generated geo fields are virtual — they don't exist as physical
    columns. Tableau computes them at render time from whichever dimension
    carries a geographic semantic-role (State / City / Country / ...). Power BI
    has no equivalent: a Map visual needs either real coordinate columns OR a
    ``Category``-roled location dimension that Bing geocodes. Leaving the
    generated fields in ``fields[]`` produces broken visuals — PBI tries to
    bind a non-existent column and the map renders empty.

    This pass rewrites each affected visual so PBI can render it:

      1. Drops every ``(generated)`` lat/long/geometry field from ``fields[]``.
      2. Locates the geographic dimension that should act as the Category:
           a. A field already in ``fields[]`` whose column matches the
              worksheet's captured ``geo_source_column``.
           b. A field already in ``fields[]`` whose column has a geographic
              ``semantic_role`` (``primary_key`` on a state/city/country-named
              column, etc.).
           c. If neither — synthesize a new field from the worksheet's captured
              ``geo_source_column`` + resolved physical table.
      3. Promotes that dimension's role to ``Category`` (the PBI Map's
         Location vocabulary).

    Idempotent: visuals with no generated geo fields are untouched. A geo dim
    already in role ``Category`` is left as-is. Visuals where both the
    generated fields and a derivable geo source are missing are left
    untouched with a warning rather than producing a still-broken result.
    """
    if not context:
        return

    # Build maps from the preprocessed context: worksheet -> (geo_col, phys_table).
    worksheet_geo: Dict[str, Dict[str, str]] = {}
    federated_to_caption: Dict[str, str] = {}
    datasource_columns: Dict[str, Dict[str, str]] = {}

    for ds in (context.model.get("datasources", []) or []):
        internal = ds.get("internal_name", "") or ""
        caption = ds.get("name", "") or ds.get("caption", "") or ""
        if internal and caption:
            federated_to_caption[internal] = caption
        cmap = ds.get("cols_map") or {}
        if caption and cmap:
            ds_cols = datasource_columns.setdefault(caption, {})
            for col_caption, mapping in cmap.items():
                phys = (mapping or {}).get("table", "")
                if phys:
                    ds_cols[col_caption] = phys
                    ds_cols[col_caption.lower()] = phys

    for ws in (context.visuals.get("worksheets", []) or []):
        ws_name = ws.get("name", "")
        geo_col = ws.get("geo_source_column", "")
        geo_ds_id = ws.get("geo_source_datasource_id", "")
        if not (ws_name and geo_col and geo_ds_id):
            continue
        geo_ds_caption = federated_to_caption.get(geo_ds_id, "")
        if not geo_ds_caption:
            continue
        ds_cols = datasource_columns.get(geo_ds_caption, {})
        phys = ds_cols.get(geo_col) or ds_cols.get(geo_col.lower())
        if phys:
            worksheet_geo[ws_name] = {"column": geo_col, "table": phys}

    # Index columns that look like a geographic location dimension so we can
    # recognize one to promote to the Map's Category (Location) slot — even when
    # the worksheet geo-capture didn't fire. A geo dimension is recognized by
    # NAME (state/city/country/...) on a STRING column, REGARDLESS of
    # semantic_role: Tableau's geo role lands on the column whatever PK/FK/dim
    # role the RE assigned, so restricting to primary_key (the old behaviour)
    # missed the common cases (`State` as dimension, `Order State` as
    # foreign_key) and left the map with no location → blank render.
    #
    # geo_category_of: column-name -> PBI dataCategory string. Power BI geocodes
    # a Category/Location field far more reliably when the column carries the
    # right dataCategory (StateOrProvince / City / Country / ...). We stamp it on
    # both the promoted visual field and the backing table column.
    _GEO_NAME_TO_CATEGORY = (
        # (substring matched in lowercased column name, PBI dataCategory)
        # Order matters: more specific first.
        ("zip code", "PostalCode"), ("zipcode", "PostalCode"),
        ("postal", "PostalCode"), ("post code", "PostalCode"),
        ("country", "Country"), ("nation", "Country"),
        ("state", "StateOrProvince"), ("province", "StateOrProvince"),
        ("county", "County"), ("cbsa", "Place"), ("msa", "Place"),
        ("city", "City"), ("town", "City"),
        # NOTE: "region" is intentionally NOT a geo token. A Tableau "Region"
        # (e.g. South/West sales regions) is not a Bing-geocodable place, and
        # treating it as StateOrProvince both mis-tags the column (#14) and lets
        # the name-match fallback hijack a map's location away from the real
        # geo column (#1). Maps use the worksheet's captured geo_source_column.
        ("latitude", "Latitude"), ("longitude", "Longitude"),
        ("address", "Address"), ("place", "Place"),
    )

    def _geo_category_for(cname: str) -> Optional[str]:
        low = (cname or "").lower()
        for token, cat in _GEO_NAME_TO_CATEGORY:
            if token in low:
                return cat
        return None

    geo_column_set: set = set()
    geo_category_of: Dict[str, str] = {}
    for tbl in (final_parsed.get("tables") or []):
        for col in (tbl.get("columns") or []):
            cname = col.get("name") or ""
            if not cname:
                continue
            dtype = (col.get("data_type") or "").strip().lower()
            cat = _geo_category_for(cname)
            # A geographic location dimension is a STRING column whose name
            # matches a place hint (lat/long are handled separately as numeric
            # coordinates, not Category locations).
            if cat and cat not in ("Latitude", "Longitude") and dtype in ("string", "", None):
                geo_column_set.add(cname)
                geo_category_of.setdefault(cname, cat)

    def visual_to_worksheet_name(visual: Dict[str, Any]) -> str:
        vid = visual.get("id", "") or ""
        m = re.search(r'\$([^$]+?)\(visual\)', vid)
        if m:
            return m.group(1)
        return visual.get("title", "") or ""

    fixed_visuals = 0
    skipped_visuals = 0
    for page in (final_parsed.get("visualizations", {}).get("pages", []) or []):
        for visual in (page.get("visuals", []) or []):
            fields = visual.get("fields") or []
            if not fields:
                continue
            generated_idxs = [
                i for i, f in enumerate(fields)
                if isinstance(f, dict) and (f.get("column") in _GEO_GENERATED_FIELDS)
            ]
            is_map = (visual.get("visual_type") or "").strip().lower() in (
                "map", "filled_map", "filledmap", "symbol_map"
            )
            # A map visual already carrying a Category/location dimension is fine.
            has_category = any(
                isinstance(f, dict) and (f.get("role") or "").lower() == "category"
                for f in fields
            )
            # Process when there are generated geo fields to drop, OR the visual
            # is a map with no Category location yet (the case that left maps
            # blank: the location dim came through as Detail/Color, never Category).
            if not generated_idxs and not (is_map and not has_category):
                continue

            ws_name = visual_to_worksheet_name(visual)
            geo_info = worksheet_geo.get(ws_name) or {}
            expected_geo_col = geo_info.get("column", "")
            expected_geo_table = geo_info.get("table", "")

            # Step 2: find an existing field to promote to the Location/Category
            # slot. Prefer (2a) the worksheet's known geo source column, then
            # (2b) ANY field whose column is a recognized geo location dimension
            # — regardless of its current role (Detail/Color/etc.) or
            # semantic_role. This is the core fix: the location dimension is
            # usually present but mis-roled, so we re-home it to Category.
            promote_idx: Optional[int] = None
            if expected_geo_col:
                for i, f in enumerate(fields):
                    if i in generated_idxs or not isinstance(f, dict):
                        continue
                    if (f.get("column") or "") == expected_geo_col:
                        promote_idx = i
                        break
            # Name-match fallback ONLY when the worksheet captured NO geo source
            # column. When the worksheet DID capture its location (e.g. State on
            # the detail/lod shelf), we must use that — never let a name-matched
            # field (often the COLOUR dimension) hijack the location. If the
            # captured location was dropped from fields[], promote_idx stays None
            # and the synthesize branch below re-adds the true location.
            if promote_idx is None and not expected_geo_col:
                for i, f in enumerate(fields):
                    if i in generated_idxs or not isinstance(f, dict):
                        continue
                    if (f.get("column") or "") in geo_column_set:
                        promote_idx = i
                        break

            def _stamp_category(field: dict) -> None:
                """Tag the visual field AND its backing table column with the
                PBI dataCategory so the converter geocodes the location."""
                col = field.get("column") or ""
                cat = geo_category_of.get(col) or _geo_category_for(col)
                if not cat:
                    return
                field["data_category"] = cat
                tbl_name = field.get("table") or ""
                for t in (final_parsed.get("tables") or []):
                    if (t.get("name") or "") != tbl_name:
                        continue
                    for c in (t.get("columns") or []):
                        if (c.get("name") or "") == col and not c.get("data_category"):
                            c["data_category"] = cat
                    break

            # Step 3: apply the rewrite.
            if promote_idx is not None:
                # Drop generated fields, promote the geo dimension to Category.
                kept = [f for i, f in enumerate(fields) if i not in generated_idxs]
                shift = sum(1 for gi in generated_idxs if gi < promote_idx)
                new_promote_idx = promote_idx - shift
                promoted = kept[new_promote_idx]
                if (promoted.get("role") or "") != "Category":
                    promoted["role"] = "Category"
                _stamp_category(promoted)
                visual["fields"] = kept
                fixed_visuals += 1
                logger.info(
                    "Geo normalization: visual %s — dropped %d generated geo field(s); "
                    "promoted %s.%s role -> Category (data_category=%s)",
                    visual.get("id") or "?",
                    len(generated_idxs),
                    promoted.get("table") or "?", promoted.get("column") or "?",
                    promoted.get("data_category") or "-",
                )
            elif expected_geo_col and expected_geo_table:
                # Synthesize a Category field from the worksheet's captured geo source.
                kept = [f for i, f in enumerate(fields) if i not in generated_idxs]
                syn = {
                    "role": "Category",
                    "table": expected_geo_table,
                    "column": expected_geo_col,
                    "aggregation": "",
                    "query_ref": f"[{expected_geo_table}].[{expected_geo_col}]",
                }
                _stamp_category(syn)
                kept.append(syn)
                visual["fields"] = kept
                fixed_visuals += 1
                logger.info(
                    "Geo normalization: visual %s — dropped %d generated geo field(s); "
                    "synthesized Category field %s.%s (data_category=%s)",
                    visual.get("id") or "?",
                    len(generated_idxs),
                    expected_geo_table, expected_geo_col, syn.get("data_category") or "-",
                )
            elif generated_idxs:
                # Generated fields present but no resolvable location dim: drop the
                # generated fields (they reference nonexistent columns) and warn.
                visual["fields"] = [f for i, f in enumerate(fields) if i not in generated_idxs]
                skipped_visuals += 1
                logger.warning(
                    "Geo normalization: visual %s has generated geo fields but no "
                    "resolvable geo dimension (worksheet=%r); dropped generated fields",
                    visual.get("id") or "?", ws_name,
                )
            else:
                # Map with no Category and no promotable geo dim — leave as-is.
                skipped_visuals += 1

    if fixed_visuals or skipped_visuals:
        print(
            f"[Tableau] Post-processing: geo-normalized {fixed_visuals} visual(s); "
            f"{skipped_visuals} unresolved"
        )


def _deduplicate_federated_tables(final_parsed: dict) -> None:
    """Collapse tables[] rows that describe the same physical table referenced
    from multiple Tableau datasources (federation duplicates).

    Detection: two rows share the same ``name``. Guardrail: only merge when the
    column-name sets are identical AND the physical source paths (from the
    read_source ingestion step) match. If shapes diverge, the dup is still
    folded in (union of columns) but a warning is logged so the divergence is
    visible. Relationships continue to reference the table by name, so they
    automatically rebind to the surviving row.
    """
    tables = final_parsed.get("tables") or []
    if len(tables) < 2:
        return

    by_name: Dict[str, dict] = {}
    kept: List[dict] = []
    merged = 0
    for tbl in tables:
        name = tbl.get("name") or ""
        if not name:
            kept.append(tbl)
            continue
        if name in by_name:
            target = by_name[name]
            target_cols = {(c.get("name") or "") for c in target.get("columns", [])}
            dup_cols = {(c.get("name") or "") for c in tbl.get("columns", [])}
            target_path = _read_source_path(target)
            dup_path = _read_source_path(tbl)
            if target_cols != dup_cols or (target_path and dup_path and target_path != dup_path):
                logger.warning(
                    "Federation-duplicate table %r has divergent shape "
                    "(columns_match=%s, paths=%r vs %r); merging anyway with union of columns",
                    name, target_cols == dup_cols, target_path, dup_path,
                )
            _merge_duplicate_table(target, tbl)
            merged += 1
        else:
            by_name[name] = tbl
            kept.append(tbl)

    final_parsed["tables"] = kept
    if merged:
        print(f"[Tableau] Post-processing: merged {merged} federation-duplicate table row(s)")
        logger.info("Post-processing: merged %d federation-duplicate tables", merged)


def _generate_relationship_ids(final_parsed: dict) -> None:
    """Post-process relationships: generate stable IDs and fill missing defaults.

    Handles:
    - id: generates rel_<left_table>_<right_table>_<left_column> if missing
    - relationship_type: collapses anything outside {dimension_lookup,
      auto_date_relationship, blend} to "dimension_lookup" (FE-known vocabulary)
    - is_hidden: defaults to false
    - is_auto_generated: defaults to false
    - join_on_date_behavior: defaults to null
    """
    relationships = final_parsed.get("relationships", [])
    if not relationships:
        return

    seen_ids = set()
    generated_count = 0

    for rel in relationships:
        # --- 1. Generate ID if missing ---
        if not rel.get("id"):
            left_table = (rel.get("left_table_id") or "unknown").lower()
            right_table = (rel.get("right_table_id") or "unknown").lower()
            left_col = (rel.get("left_column") or "col").lower()

            # Sanitize: replace non-alphanumeric (except underscore) with underscore
            left_table_clean = re.sub(r'[^a-z0-9_]', '_', left_table).strip('_')
            right_table_clean = re.sub(r'[^a-z0-9_]', '_', right_table).strip('_')
            left_col_clean = re.sub(r'[^a-z0-9_]', '_', left_col).strip('_')

            base_id = f"rel_{left_table_clean}_{right_table_clean}_{left_col_clean}"

            # Ensure uniqueness with numeric suffix
            candidate = base_id
            suffix = 1
            while candidate in seen_ids:
                suffix += 1
                candidate = f"{base_id}_{suffix}"

            rel["id"] = candidate
            seen_ids.add(candidate)
            generated_count += 1
        else:
            seen_ids.add(rel["id"])

        # --- 2. Normalize relationship_type to FE vocabulary ---
        # Allowed values: dimension_lookup, auto_date_relationship, blend.
        # Anything else (including null, empty, "fact_to_fact", "bridge", "join",
        # "relationship") collapses to dimension_lookup. The PBI converter only
        # understands these three values.
        _ALLOWED_REL_TYPES = {"dimension_lookup", "auto_date_relationship", "blend"}
        rel_type = (rel.get("relationship_type") or "").strip()
        if rel_type not in _ALLOWED_REL_TYPES:
            rel["relationship_type"] = "dimension_lookup"

        # --- 3. Set defaults for missing fields ---
        if "is_hidden" not in rel:
            rel["is_hidden"] = False
        if "is_auto_generated" not in rel:
            rel["is_auto_generated"] = False
        if "join_on_date_behavior" not in rel:
            rel["join_on_date_behavior"] = None

    if generated_count:
        print(f"[Tableau] Post-processing: generated {generated_count} relationship ID(s)")
        logger.info("Post-processing: generated %d relationship IDs", generated_count)


_UNIQUE_SEMANTIC_ROLES = {"primary_key", "identifier"}


def _fix_one_to_one_misclassification(final_parsed: dict) -> None:
    """Override ``cardinality == one_to_one`` when the join column's semantic_role
    on the two sides contradicts the 1:1 claim.

    A true 1:1 requires uniqueness on BOTH sides of the join key. If one side's
    join column has semantic_role in {primary_key, identifier} but the other
    side's join column does NOT, the relationship is many_to_one (or
    one_to_many) — not 1:1. The LLM sometimes mislabels these as 1:1 when both
    tables happen to be classified as dimensions; the override fires only on
    that PK/non-PK contradiction, so a genuine PK-on-both-sides 1:1 is never
    touched.

    On override, filter_direction is also reset from "bidirectional" to "single"
    to match the corrected cardinality.
    """
    rels = final_parsed.get("relationships") or []
    if not rels:
        return

    # Build (table_name, column_name) -> semantic_role index. Table names in
    # relationships are stored as table IDs (uuid-suffixed). Tables are stored
    # by friendly name. We normalize the relationship's table-id by stripping
    # the "...$<name>(table)$<uuid>(uuid)" wrapper to its friendly name.
    def table_id_to_name(tid: Optional[str]) -> str:
        if not tid:
            return ""
        m = re.search(r"\$([^$]+)\(table\)", tid)
        if m:
            return m.group(1)
        # Already a plain name
        return tid

    role_index: Dict[tuple, str] = {}
    for tbl in (final_parsed.get("tables") or []):
        tname = tbl.get("name") or ""
        for col in (tbl.get("columns") or []):
            cname = col.get("name") or ""
            role = (col.get("semantic_role") or "").strip().lower()
            if tname and cname:
                role_index[(tname, cname)] = role
                role_index[(tname, cname.lower())] = role

    def role_for(table_id: Optional[str], column: Optional[str]) -> str:
        if not column:
            return ""
        tname = table_id_to_name(table_id)
        if not tname:
            return ""
        return (
            role_index.get((tname, column))
            or role_index.get((tname, (column or "").lower()))
            or ""
        )

    overridden = 0
    for rel in rels:
        if (rel.get("cardinality") or "").lower() != "one_to_one":
            continue
        left_role = role_for(rel.get("left_table_id"), rel.get("left_column"))
        right_role = role_for(rel.get("right_table_id"), rel.get("right_column"))
        left_unique = left_role in _UNIQUE_SEMANTIC_ROLES
        right_unique = right_role in _UNIQUE_SEMANTIC_ROLES
        if left_unique and right_unique:
            # Genuine 1:1 — both sides are unique on the join key. Keep as-is.
            continue
        if not left_unique and not right_unique:
            # Neither side is unique → many_to_many is the safer correction.
            new_card = "many_to_many"
            new_dir = "bidirectional"
        else:
            # Exactly one side is unique. Direction follows which side is the PK.
            if right_unique:
                new_card = "many_to_one"
            else:
                new_card = "one_to_many"
            new_dir = "single"
        prev = rel.get("cardinality")
        rel["cardinality"] = new_card
        rel["filter_direction"] = new_dir
        overridden += 1
        logger.info(
            "Cardinality override: rel %s (%s.%s → %s.%s) %s → %s (left_role=%r, right_role=%r)",
            rel.get("id") or "?",
            table_id_to_name(rel.get("left_table_id")), rel.get("left_column"),
            table_id_to_name(rel.get("right_table_id")), rel.get("right_column"),
            prev, new_card, left_role, right_role,
        )

    if overridden:
        print(f"[Tableau] Post-processing: corrected {overridden} mis-classified one_to_one relationship(s)")


def _table_name_from_id(tid: Optional[str]) -> str:
    """Relationship endpoints may be a bare name or the wrapped
    `…$<name>(table)$<uuid>` form — return the friendly table name."""
    if not tid:
        return ""
    m = re.search(r"\$([^$]+)\(table\)", tid)
    return m.group(1) if m else tid


def _fix_relationship_cardinality(final_parsed: dict) -> None:
    """Replace the LLM's blanket ``many_to_many`` with the real cardinality,
    inferred deterministically from each join key's semantic_role: a side whose
    key is primary_key/identifier is the UNIQUE ("one") side. Fact→dimension
    lookups become many_to_one (the common case); filter_direction follows.
    Self-joins are left many_to_many. Name- and value-agnostic."""
    rels = final_parsed.get("relationships") or []
    if not rels:
        return
    role = {}
    for t in (final_parsed.get("tables") or []):
        tn = t.get("name") or ""
        for c in (t.get("columns") or []):
            role[(tn, (c.get("name") or "").lower())] = (c.get("semantic_role") or "").lower()
    _UNIQUE = {"primary_key", "identifier"}
    fixed = 0
    for r in rels:
        if (r.get("relationship_type") or "") == "blend":
            continue
        lt, rt = _table_name_from_id(r.get("left_table_id")), _table_name_from_id(r.get("right_table_id"))
        lc, rc = (r.get("left_column") or "").lower(), (r.get("right_column") or "").lower()
        if lt == rt:
            continue  # self-join: leave as-is
        lu, ru = role.get((lt, lc)) in _UNIQUE, role.get((rt, rc)) in _UNIQUE
        if lu and not ru:
            card = "one_to_many"
        elif ru and not lu:
            card = "many_to_one"
        elif lu and ru:
            card = "one_to_one"
        else:
            card = "many_to_one"   # fact(left)→dimension(right) default; better than blanket m:m
        if (r.get("cardinality") or "") == "many_to_many" and card != "many_to_many":
            r["cardinality"] = card
            fixed += 1
        if r.get("cardinality") in ("many_to_one", "one_to_many"):
            r["filter_direction"] = "single"
    if fixed:
        print(f"[Tableau] Post-processing: corrected cardinality on {fixed} relationship(s) (m:m -> m:1 etc.)")


def _ensure_parameters_table(final_parsed: dict) -> None:
    """If any parameter calc exists, guarantee a 'Parameters' calculated home
    table (the LLM sometimes omits it), so parameter measures have a home."""
    calcs = final_parsed.get("calculations") or []
    if not any((c.get("semantic_type") or "") == "parameter" for c in calcs):
        return
    tables = final_parsed.setdefault("tables", [])
    if any((t.get("name") or "").strip().lower() == "parameters" for t in tables):
        return
    tables.append({
        "name": "Parameters", "table_type": "calculated", "source_data_source_id": None,
        "is_materialized": False, "columns": [], "hierarchies": [],
        "ingestion": {"steps": [{"order": 1, "step_type": "dax_calculated_table",
                                 "description": "Synthesized Parameters home table (hosts parameter measures).",
                                 "native_expressions": {"dax": 'ROW("Value", BLANK())'}}]},
    })
    print("[Tableau] Post-processing: synthesized missing 'Parameters' home table")


_GEO_NAME_CATEGORY = (
    ("zip code", "PostalCode"), ("zipcode", "PostalCode"), ("postal", "PostalCode"),
    ("country", "Country"), ("state", "StateOrProvince"), ("province", "StateOrProvince"),
    ("county", "County"), ("city", "City"), ("town", "City"),
    ("latitude", "Latitude"), ("longitude", "Longitude"), ("address", "Address"),
)


def _apply_geo_data_categories(final_parsed: dict) -> None:
    """Stamp a Power BI `data_category` on geographic columns on EVERY table
    (not just map-bound ones), so any geo field geocodes. Keyed on the column
    NAME via a generic geo vocabulary (NOT on this workbook's values; 'region'
    is intentionally excluded). Lat/Long on numeric cols, place names on strings."""
    def _cat(n):
        low = (n or "").lower()
        for tok, c in _GEO_NAME_CATEGORY:
            if tok in low:
                return c
        return None
    n = 0
    for t in (final_parsed.get("tables") or []):
        for c in (t.get("columns") or []):
            if c.get("data_category"):
                continue
            cat = _cat(c.get("name") or "")
            dt = (c.get("data_type") or "").strip().lower()
            if cat in ("Latitude", "Longitude") and dt in ("real", "double", "number", "float", "decimal", ""):
                c["data_category"] = cat; n += 1
            elif cat and cat not in ("Latitude", "Longitude") and dt in ("string", "", None):
                c["data_category"] = cat; n += 1
    if n:
        print(f"[Tableau] Post-processing: stamped data_category on {n} geo column(s)")


def _fix_calc_format_strings(final_parsed: dict) -> None:
    """Set `format_string` deterministically from `data_type` so integers aren't
    formatted with decimals and strings/groups carry no number format (#20)."""
    _FMT = {"integer": "0", "real": "#,##0.00", "date": "yyyy-MM-dd", "datetime": "yyyy-MM-dd"}
    for c in (final_parsed.get("calculations") or []):
        dt = (c.get("data_type") or "").strip().lower()
        st = (c.get("semantic_type") or "").strip().lower()
        if dt in ("string", "boolean") or st in ("group", "string", "split"):
            c["format_string"] = None
        elif dt in _FMT and (not c.get("format_string") or (dt == "integer" and c.get("format_string") == "#,##0.00")):
            c["format_string"] = _FMT[dt]


def _bare_tableau_field(ref: Optional[str]) -> str:
    """Reduce a Tableau column reference to its bare column name:
    '[datasource].[Region]' -> 'Region', '[Region]' -> 'Region', 'Region' -> 'Region'."""
    s = (ref or "").strip()
    if not s:
        return ""
    parts = re.findall(r'\[([^\[\]]+)\]', s)
    return parts[-1].strip() if parts else s


# Tableau calc constructs we will NOT auto-translate into a DAX RLS predicate.
# Their presence forces a fail-closed role (deny-all + the original formula in a
# comment) so a security boundary is never silently mistranslated.
_RLS_DAX_UNSAFE = (
    "ISMEMBEROF", "USERDOMAIN", "ISFULLNAME", "ISUSERNAME", "ELSEIF",
    "CASE ", " WHEN ", "WINDOW_", "LOOKUP(", "INDEX(", "RANK", "RUNNING_",
    "TOTAL(", "PREVIOUS_VALUE", "FIRST(", "LAST(", "{FIXED", "{EXCLUDE", "{INCLUDE",
)


def _tableau_rls_calc_to_dax(formula: str, resolve_table):
    """Best-effort DETERMINISTIC transpile of a Tableau RLS predicate calc to a
    DAX boolean expression. Returns ``(dax, confident, table)``.

    `confident` is True only when every construct is in the safe subset AND every
    field reference resolves to a single physical table. The caller fails closed
    (deny-all) otherwise, so a security boundary is never silently mistranslated.
    No LLM is involved — RLS is security-critical."""
    f = (formula or "").strip()
    if not f or any(tok in f.upper() for tok in _RLS_DAX_UNSAFE):
        return None, False, None

    # Mask string literals so keyword/operator rewrites never touch their bodies.
    literals: list = []
    def _mask(m):
        literals.append(m.group(0))
        return f"\x00{len(literals) - 1}\x00"
    work = re.sub(r'"(?:[^"]|"")*"|\'(?:[^\']|\'\')*\'', _mask, f)

    # Resolve every [field] -> 'Table'[field]; track tables + unresolved refs.
    tables_used, unresolved = set(), []
    def _sub_field(m):
        name = m.group(1).strip()
        t = resolve_table(name)
        if t:
            tables_used.add(t)
            return f"'{t.replace(chr(39), chr(39) * 2)}'[{name}]"
        unresolved.append(name)
        return m.group(0)
    work = re.sub(r'\[([^\[\]]+)\]', _sub_field, work)
    if unresolved or len(tables_used) != 1:
        return None, False, (next(iter(tables_used)) if tables_used else None)
    table = next(iter(tables_used))

    # User functions -> Power BI service identity.
    work = re.sub(r'\bUSERNAME\s*\(\s*\)', 'USERPRINCIPALNAME()', work, flags=re.IGNORECASE)
    work = re.sub(r'\bFULLNAME\s*\(\s*\)', 'USERPRINCIPALNAME()', work, flags=re.IGNORECASE)
    # Common string-function rename (Tableau CONTAINS -> DAX CONTAINSSTRING).
    work = re.sub(r'\bCONTAINS\s*\(', 'CONTAINSSTRING(', work, flags=re.IGNORECASE)
    # Single-branch IF ... THEN ... [ELSE ...] END -> IF(cond, then[, else]).
    if re.search(r'\bIF\b', work, flags=re.IGNORECASE):
        if len(re.findall(r'\bTHEN\b', work, flags=re.IGNORECASE)) != 1:
            return None, False, table
        m = re.match(r'(?is)^\s*IF\s+(.*?)\s+THEN\s+(.*?)(?:\s+ELSE\s+(.*?))?\s+END\s*$', work)
        if not m:
            return None, False, table
        cond, then_v, else_v = m.group(1), m.group(2), m.group(3)
        work = f"IF({cond}, {then_v}" + (f", {else_v})" if else_v is not None else ")")
    # Boolean keyword operators -> DAX operators.
    work = re.sub(r'\bAND\b', '&&', work, flags=re.IGNORECASE)
    work = re.sub(r'\bOR\b', '||', work, flags=re.IGNORECASE)
    # Restore masked string literals.
    work = re.sub(r'\x00(\d+)\x00', lambda mm: literals[int(mm.group(1))], work)
    return work.strip(), True, table


def _apply_tableau_rls_roles(final_parsed: dict, context: Any = None) -> None:
    """Convert Tableau row-level security into common-model `roles`, mirroring
    the Power BI RLS shape so the FE emits SemanticModel roles for the Tableau
    flow too. Tableau RLS is dynamic (evaluated per logged-in user); the faithful
    Power BI equivalent is a dynamic-RLS role keyed on `USERPRINCIPALNAME()`.

    Handles both Tableau RLS mechanisms (captured by `utils._extract_security`):

      * `user_filter` — inline user -> allowed-value mapping. Emitted as an
        OR of `( USERPRINCIPALNAME() = "<user>" && 'T'[col] = "<value>" )` terms.
      * `calculation`  — a user-function calc applied as a data-source filter.
        The calc formula is transpiled deterministically to a DAX predicate; if
        it uses a construct we can't safely translate (ISMEMBEROF, multi-branch
        CASE, …) the role is emitted FAIL-CLOSED (deny-all) with the original
        formula in a comment for manual review — never silently dropped.

    Workbook-scope permission rules (Server access control) are skipped (no PBI
    table-RLS analog). All DAX is built deterministically — never via an LLM.
    No-op when the workbook defines no RLS."""
    model = getattr(context, "model", None) or {}
    security = model.get("security") or []
    tables = final_parsed.get("tables") or []
    if not security or not tables:
        return

    def _dax_str(s: str) -> str:
        return '"' + (s or "").replace('"', '""') + '"'

    def _resolve_table(col_name: str) -> Optional[str]:
        bare = _bare_tableau_field(col_name).lower()
        if not bare:
            return None
        for t in tables:
            for c in (t.get("columns") or []):
                if (c.get("name") or "").strip().lower() == bare:
                    return t.get("name")
        return None

    def _comment(name: str, formula: str, review: bool) -> str:
        safe = (formula or "").replace("*/", "* /")
        if review:
            return (f'/* Tableau RLS "{name}" could not be safely auto-translated to DAX; '
                    f'this role DENIES ALL rows until reviewed. Source calc: {safe} */')
        return f'/* Tableau RLS "{name}" - auto-translated from Tableau. Source calc: {safe} */'

    roles, fail_closed, skipped = [], 0, 0
    for sec in security:
        kind = (sec.get("kind") or "user_filter").strip().lower()
        if (sec.get("scope") or "") == "workbook" or kind == "permission_rule":
            continue

        if kind == "calculation":
            formula = sec.get("formula") or ""
            name = (sec.get("name") or "").strip() or "RLS"
            dax, confident, table = _tableau_rls_calc_to_dax(formula, _resolve_table)
            if confident and dax and table:
                # A filter that keeps FALSE (rather than TRUE) inverts the calc.
                keep = [str(v).strip().lower() for v in (sec.get("keep_values") or [])]
                if keep and "true" not in keep and "false" in keep:
                    dax = f"NOT( {dax} )"
                filter_expr = f"{_comment(name, formula, False)}\n{dax}"
                roles.append({"name": name,
                              "table_permissions": [{"table": table, "filter_expression": filter_expr}]})
            else:
                # Fail closed: deny-all on every table the calc touches so the
                # boundary is never silently lost. Needs at least one table.
                ref_tables = {t for n in re.findall(r'\[([^\[\]]+)\]', formula)
                              if (t := _resolve_table(n))}
                if not ref_tables:
                    print(f"[Tableau] WARNING: RLS calc '{name}' references no resolvable "
                          f"table; cannot emit a role. Apply manually. Formula: {formula}")
                    skipped += 1
                    continue
                filter_expr = f"FALSE()\n{_comment(name, formula, True)}"
                roles.append({"name": name,
                              "table_permissions": [{"table": t, "filter_expression": filter_expr}
                                                    for t in sorted(ref_tables)]})
                fail_closed += 1
            continue

        # user_filter: inline user -> allowed-value mapping.
        members = sec.get("members") or []
        table = _resolve_table(sec.get("column") or "")
        if not table or not members:
            skipped += 1
            continue
        col = _bare_tableau_field(sec.get("column") or "")
        tcol = f"'{table.replace(chr(39), chr(39) * 2)}'[{col}]"
        terms = []
        for mem in members:
            func = (mem.get("function") or "member").strip().lower()
            val = (mem.get("member") or "").strip()
            user = (mem.get("user") or "").strip()
            # Only the "member" (user -> allowed value) form maps cleanly. Other
            # group-filter functions (level-members/except/union/...) would need
            # set arithmetic; skip the term rather than risk over-granting access.
            if not val or func != "member":
                continue
            if user:
                terms.append(f"( USERPRINCIPALNAME() = {_dax_str(user)} && {tcol} = {_dax_str(val)} )")
            else:
                terms.append(f"( {tcol} = {_dax_str(val)} )")
        if not terms:
            skipped += 1
            continue
        filter_expr = " ||\n".join(terms)
        role_name = (sec.get("name") or "").strip() or f"{table} RLS"
        roles.append({"name": role_name,
                      "table_permissions": [{"table": table, "filter_expression": filter_expr}]})

    if roles:
        existing = final_parsed.get("roles") or []
        existing.extend(roles)
        final_parsed["roles"] = existing
        print(f"[Tableau] Post-processing: emitted {len(roles)} RLS role(s) "
              f"({fail_closed} fail-closed pending review)")
    if skipped:
        print(f"[Tableau] Post-processing: skipped {skipped} security entr(ies) "
              f"(unresolved table/column or unsupported form)")


def _populate_calc_dependencies(final_parsed: dict, context: Any = None) -> None:
    """Best-effort populate `depends_on_columns`/`depends_on_measures` from the
    preprocessing per-calc `depends_on` list (already captured) — split a bare
    dependency into a physical "Table.Column" or another measure's name (#17)."""
    calcs = final_parsed.get("calculations") or []
    if not calcs or not (context and getattr(context, "model", None)):
        return
    raw = {}
    for c in (context.model.get("calculations", []) or []):
        for key in ((c.get("caption") or "").strip(), (c.get("internal_name") or "").strip("[]")):
            if key:
                raw[key] = c.get("depends_on") or []
    col_tbl = {}
    for t in (final_parsed.get("tables") or []):
        for c in (t.get("columns") or []):
            cn = c.get("name") or ""
            if cn:
                col_tbl.setdefault(cn, t.get("name") or "")
    names = {(c.get("name") or "") for c in calcs}
    filled = 0
    for c in calcs:
        if c.get("depends_on_columns") or c.get("depends_on_measures"):
            continue
        deps = raw.get((c.get("name") or "").strip()) or []
        if not deps:
            continue
        cols, meas = [], []
        for d in (dd.strip() for dd in deps):
            if d in names:
                meas.append(d)
            elif d in col_tbl:
                cols.append(f"{col_tbl[d]}.{d}")
        if cols or meas:
            c["depends_on_columns"], c["depends_on_measures"] = cols, meas
            filled += 1
    if filled:
        print(f"[Tableau] Post-processing: populated depends_on lineage on {filled} calc(s)")


def _normalize_calculation_names(final_parsed: dict) -> None:
    """Strip spurious ``(<datasource>)`` / ``(calc)`` suffixes the extraction agent
    appends to calculation names, and re-link every reference to the cleaned name.

    The extraction prompt asks the agent to disambiguate genuinely-colliding
    measure names by appending the home table in parentheses. In practice the
    agent over-applies this: it suffixes nearly every calculation with its
    datasource name (e.g. "COGS" -> "COGS (Product Sales)"). The visuals agent
    runs independently and keeps the bare name in visual fields[].column, so the
    measure references dangle and the visual renders empty.

    """
    calculations = final_parsed.get("calculations") or []
    if not calculations:
        return

    strip_tokens = {
        (ds.get("name") or "").strip()
        for ds in (final_parsed.get("data_sources") or [])
        if (ds.get("name") or "").strip()
    }
    strip_tokens.add("calc")

    def base_name(name: str) -> str:
        out = (name or "").strip()
        while out.endswith(")"):
            idx = out.rfind(" (")
            if idx <= 0:
                break
            inner = out[idx + 2:-1].strip()
            if inner not in strip_tokens:
                break
            out = out[:idx].strip()
        return out

    by_base: Dict[str, List[dict]] = {}
    for calc in calculations:
        b = base_name(calc.get("name") or "")
        if b:
            by_base.setdefault(b, []).append(calc)

    rename_map: Dict[str, str] = {}                     # old calc name -> new calc name
    collision_choices: Dict[str, Dict[str, str]] = {}   # base name -> {home_table: new name}
    for base, group in by_base.items():
        if len(group) == 1:
            old = group[0].get("name") or ""
            if old and old != base:
                rename_map[old] = base
            continue
        # Genuine collision: keep one home_table suffix on the colliding entries.
        used: Dict[str, int] = {}
        for calc in group:
            old = calc.get("name") or ""
            ht = (calc.get("home_table") or "").strip()
            new = f"{base} ({ht})" if ht else base
            seen = used.get(new, 0) + 1
            used[new] = seen
            if seen > 1:
                new = f"{new} {seen}"
            if old and old != new:
                rename_map[old] = new
            if ht:
                collision_choices.setdefault(base, {})[ht] = new

    if not rename_map:
        return

    # 1. Rename the calculations themselves.
    for calc in calculations:
        old = calc.get("name") or ""
        if old in rename_map:
            calc["name"] = rename_map[old]

    # 2. Rewrite depends_on_measures references.
    for calc in calculations:
        dom = calc.get("depends_on_measures")
        if isinstance(dom, list):
            calc["depends_on_measures"] = [rename_map.get(m, m) for m in dom]

    # 3. Re-link visual fields that referenced a now-disambiguated colliding name.
    #    (No-collision renames need no rewrite -- the field already carries the
    #    bare base name the calculation was renamed back to.)
    relinked = 0
    for page in (final_parsed.get("visualizations") or {}).get("pages", []) or []:
        for visual in page.get("visuals", []) or []:
            for field in visual.get("fields") or []:
                if not isinstance(field, dict):
                    continue
                col = field.get("column")
                choices = collision_choices.get(col)
                if not choices:
                    continue
                new = choices.get(field.get("table"))
                if not new or new == col:
                    continue
                qr = field.get("query_ref")
                if isinstance(qr, str) and col in qr:
                    field["query_ref"] = qr.replace(col, new)
                field["column"] = new
                relinked += 1

    print(f"[Tableau] Post-processing: normalized {len(rename_map)} calculation "
          f"name(s); re-linked {relinked} visual field(s)")
    logger.info("Post-processing: normalized %d calculation names, re-linked %d fields",
                len(rename_map), relinked)


# Map a Tableau field-reference prefix to whether it denotes a dimension or a
# measure, for synthesizing visual fields from worksheet shelves.
_MEASURE_PREFIXES = ("sum", "avg", "cnt", "cntd", "min", "max", "med", "stdev",
                     "var", "pcto", "cum")
_DATE_PREFIXES = ("tmn", "my", "yr", "qr", "mn", "dy", "wk")


def _decode_shelf_ref(ref: str) -> Optional[Dict[str, str]]:
    """Decode a Tableau shelf field reference into {table, column, aggregation,
    kind} where kind is 'measure' | 'date' | 'dimension'.

    Handles the two shapes the preprocessing emits:
      "[table].[agg:Name:suffix]"  (resolved) and a bare "[Name]".
    Reuses _decode_measure_member for the parse, then classifies by prefix/suffix.
    """
    if not ref or not isinstance(ref, str):
        return None
    parsed = _decode_measure_member(ref)
    if not parsed:
        return None
    table, name, agg = parsed["table"], parsed["name"], parsed["aggregation"]
    inner = parsed.get("inner", "")
    segs = inner.split(":")
    prefix = segs[0].lower() if segs else ""
    suffix = segs[-1].lower() if len(segs) > 1 else ""
    # Skip Tableau internal pseudo-fields (Measure Names / Multiple Values / actions).
    if name.startswith(("Action (", ":Measure Names")) or name in ("Multiple Values",):
        return None
    # Date prefix (tmn/my/yr/...) wins over the :qk suffix: a continuous date
    # like `tmn:Transaction Date:qk` is a DATE axis field, not a measure, even
    # though Tableau marks it quantitative (:qk). Checking :qk first would
    # misclassify it as a measure and collapse a time-series into a card.
    if prefix in _DATE_PREFIXES:
        kind = "date"
    elif prefix in _MEASURE_PREFIXES or suffix == "qk":
        kind = "measure"
    else:
        kind = "dimension"
    return {"table": table, "column": name, "aggregation": agg, "kind": kind}


# Tableau mark class -> common-model visual_type, mirroring the VISUALS_PROMPT
# classification (kept deterministic so a synthesized visual matches what the
# LLM would have produced on a good run).
_MARK_TO_VISUAL_TYPE = {
    "bar": "bar_chart", "line": "line_chart", "area": "area_chart",
    "pie": "pie_chart", "circle": "scatter_plot", "square": "heat_map",
    "shape": "scatter_plot", "text": "text_table", "gantt bar": "gantt_chart",
    "map": "map", "multipolygon": "map",
}


def _add_scatter_distribution_detail(visual: dict, ws: dict) -> bool:
    """Ensure a box-and-whisker rendered as a Power BI scatter carries a
    disaggregating ``Details`` dimension, so every underlying mark plots (the
    spread a box plot conveys) instead of collapsing to a single aggregated dot.

    Power BI has no native box plot, so the flow retypes it to a scatter. A
    scatter that binds only an aggregated measure renders ONE point; the fix is a
    point-identity dimension on ``Details`` (the FE passes ``Details`` through for
    scatterChart, and also remaps a ``Category`` dimension to ``Details``). We
    pick the worksheet's finest disaggregator first — a detail / LOD / path mark
    encoding — then fall back to a rows/cols axis dimension, then color/shape.

    No-op when a Details field already exists or no dimension is available
    (idempotent)."""
    if not isinstance(visual, dict) or not isinstance(ws, dict):
        return False
    fields = visual.setdefault("fields", [])
    if any(isinstance(f, dict) and (f.get("role") or "").lower() in ("details", "detail")
           for f in fields):
        return False
    existing = {(f.get("table"), f.get("column")) for f in fields if isinstance(f, dict)}

    refs: List[str] = []
    panes = ws.get("panes") or []
    for pane in panes:                                  # finest granularity first
        for key in ("detail", "lod", "path"):
            if isinstance(pane, dict) and pane.get(key):
                refs.append(pane[key])
    shelves = ws.get("shelves") or {}
    for shelf in ("rows", "cols", "columns"):           # then an axis dimension
        rr = shelves.get(shelf)
        if isinstance(rr, str):
            rr = [rr]
        for r in (rr or []):
            refs.append(r)
    for pane in panes:                                  # then color/shape encodings
        for key in ("color", "shape"):
            if isinstance(pane, dict) and pane.get(key):
                refs.append(pane[key])

    for ref in refs:
        dd = _decode_shelf_ref(ref or "")
        if dd and dd["kind"] in ("dimension", "date") and (dd["table"], dd["column"]) not in existing:
            fields.append({
                "role": "Details",
                "table": dd["table"],
                "column": dd["column"],
                "aggregation": "",
                "query_ref": f"[{dd['table']}].[{dd['column']}]",
            })
            return True
    return False


def _synthesize_visual_from_worksheet(ws: dict, page_name: str, filename: str,
                                      z_order: int) -> Optional[dict]:
    """Build a common-model visual dict from a preprocessed worksheet, used to
    recover a visual the VisualsLayout LLM dropped or emitted empty.

    Classification is structural (mark + shelves + reference lines), matching the
    VISUALS_PROMPT rules: box-and-whisker (reference-line whisker) wins; otherwise
    the mark class maps the chart type; a continuous date on cols with a measure
    is a line chart; a dimension + measure is a bar chart. Returns None when the
    worksheet has no usable data binding (so we don't emit an empty visual)."""
    name = (ws.get("name") or "").strip()
    if not name:
        return None
    shelves = ws.get("shelves") or {}

    # Collect decoded fields from rows/cols (+ pane lod/detail for category-only views).
    rows = [_decode_shelf_ref(r) for r in (shelves.get("rows") or [])]
    cols = [_decode_shelf_ref(c) for c in (shelves.get("cols") or shelves.get("columns") or [])]
    rows = [r for r in rows if r]
    cols = [c for c in cols if c]

    # Classify shelf fields by kind (we bind by kind, not by shelf, so a swapped
    # "dimension up / measure across" layout still works).
    dims = [d for d in (cols + rows) if d["kind"] in ("dimension", "date")]
    meas = [d for d in (rows + cols) if d["kind"] == "measure"]

    panes = ws.get("panes") or []

    # Pane-encoding fallbacks — two distinct recoveries:
    #   * category-only view: the dimension sits on a mark card (lod/detail/
    #     color/text) with nothing on rows/cols.
    #   * Tableau "BAN"/KPI tile: the MEASURE sits on the Text (or detail/color/
    #     size) mark card with nothing on rows/cols. Without this the worksheet
    #     yields no field, returns None, and the KPI is silently dropped.
    if not dims:
        for pane in panes:
            picked = None
            for key in ("lod", "detail", "color", "text"):
                dd = _decode_shelf_ref(pane.get(key) or "") if isinstance(pane, dict) else None
                if dd and dd["kind"] in ("dimension", "date"):
                    picked = dd
                    break
            if picked:
                dims.append(picked)
                break
    if not meas:
        for pane in panes:
            picked = None
            for key in ("text", "label", "detail", "color", "size", "lod"):
                md = _decode_shelf_ref(pane.get(key) or "") if isinstance(pane, dict) else None
                if md and md["kind"] == "measure":
                    picked = md
                    break
            if picked:
                meas.append(picked)
                break

    if not dims and not meas:
        return None  # nothing to bind — skip rather than emit an empty visual

    # --- visual_type classification ---
    reference_lines = ws.get("reference_lines") or []
    is_box = any(isinstance(r, dict) and (r.get("boxplot_whisker_type") or "").strip()
                 for r in reference_lines)
    mark = ""
    for mk in (ws.get("marks") or []):
        if isinstance(mk, dict) and mk.get("class"):
            mark = mk["class"].strip().lower()
            break
    has_date_cat = any(d["kind"] == "date" for d in (cols or []))
    has_dim = bool(dims)
    has_meas = bool(meas)

    if is_box:
        vtype = "scatter_plot"   # PBI has no native box plot
    elif mark in _MARK_TO_VISUAL_TYPE:
        vtype = _MARK_TO_VISUAL_TYPE[mark]
    elif has_date_cat and has_meas:
        vtype = "line_chart"
    elif has_dim and has_meas:
        vtype = "bar_chart"
    elif has_meas and not has_dim:
        vtype = "kpi_card"
    else:
        vtype = "bar_chart"

    # --- field binding (roles depend on the resolved type) ---
    fields: List[dict] = []

    def _add(decoded: dict, role: str):
        fields.append({
            "role": role,
            "table": decoded["table"],
            "column": decoded["column"],
            "aggregation": decoded["aggregation"],
            "query_ref": f"[{decoded['table']}].[{decoded['column']}]",
        })

    if vtype == "kpi_card":
        # A BAN renders a single aggregated number: bind the measure(s) as Values
        # (the FE maps kpi_card -> PBI `card`, whose sole required slot is Values;
        # a measure left on a generic axis role renders an empty card).
        for m in meas:
            _add(m, "Values")
    else:
        for d in dims:
            _add(d, "Category")
        for m in meas:
            _add(m, "Y")

    if not fields:
        return None

    visual = {
        "id": f"tableau(toolname)${filename}(filename)${page_name}(pagename)${name}(visual)",
        "visual_type": vtype,
        "title": name,
        "source_tool": "tableau",
        "fields": fields,
        "reference_lines": reference_lines,
        "_synthesized": True,
    }

    # Box-and-whisker → scatter: attach a disaggregating Details dimension so the
    # full distribution (spread) plots instead of one aggregated dot.
    if is_box:
        _add_scatter_distribution_detail(visual, ws)

    return visual


def _reconcile_dashboard_visuals(final_parsed: dict, context: Any, filename: str = "") -> None:
    """Make the visuals layer COMPLETE and deterministic: for every worksheet
    placed on a dashboard, ensure a corresponding visual exists in the output.

    Root cause this fixes: the VisualsLayout LLM unreliably DROPS or mangles
    visuals run-to-run (e.g. emitting a nameless empty `dual_axis_chart` instead
    of the real chart, or omitting a worksheet entirely). The deterministic
    preprocessing (``context.visuals``) always has every worksheet's shelves /
    marks / reference-lines, so we reconcile the LLM output against the dashboard
    zones:

      * Drop visuals that carry NO usable data field (empty shells the LLM
        produced — they render blank and crowd the canvas).
      * For each worksheet zone with no surviving visual on its page, synthesize
        the visual from the worksheet context (mark -> type, shelves -> fields).

    This guarantees the report shows every chart the source dashboard had, even
    when the LLM was flaky on a given run. Idempotent. No-op without context."""
    if not context:
        return
    pages = (final_parsed.get("visualizations") or {}).get("pages") or []
    if not pages:
        return

    # worksheet name -> worksheet metadata
    ws_by_name = {
        (w.get("name") or "").strip(): w
        for w in (getattr(context, "visuals", None) or {}).get("worksheets", []) or []
        if (w.get("name") or "").strip()
    }
    # dashboard name -> ordered worksheet zone names placed on it
    dash_worksheets: Dict[str, List[str]] = {}
    for dash in (getattr(context, "visuals", None) or {}).get("dashboards", []) or []:
        dname = (dash.get("name") or "").strip()
        seen: List[str] = []
        for zone in (dash.get("zones") or []):
            zn = (zone.get("name") or "").strip()
            # Only worksheet zones (a name that matches a real worksheet) — skip
            # filter/text/layout zones (their data binding is handled elsewhere).
            if zn and zn in ws_by_name and zn not in seen:
                seen.append(zn)
        dash_worksheets[dname] = seen

    def _has_usable_field(v: dict) -> bool:
        for f in (v.get("fields") or []):
            if isinstance(f, dict) and f.get("table") and f.get("column"):
                role = (f.get("role") or "").lower()
                if role not in ("filter", "label"):
                    return True
        return False

    dropped = 0
    synthesized = 0
    for page in pages:
        pname = (page.get("display_name") or "").strip()
        visuals = page.get("visuals") or []

        # 1) Drop empty-shell chart visuals (no usable data field). Keep
        #    textbox/image/slicer/paramctrl/map — they legitimately may have no
        #    fields or carry their content elsewhere.
        kept = []
        for v in visuals:
            vt = (v.get("visual_type") or "").strip().lower()
            if vt in ("textbox", "image", "slicer", "paramctrl", "navigation", "webview"):
                kept.append(v); continue
            if _has_usable_field(v):
                kept.append(v)
            else:
                dropped += 1
        visuals = kept

        # 2) Which worksheets already have a visual on this page?
        present: set = set()
        for v in visuals:
            for nm in _visual_worksheet_names(v):
                if nm in ws_by_name:
                    present.add(nm)

        # 3) Synthesize any missing worksheet zone for this dashboard page.
        wanted = dash_worksheets.get(pname, [])
        z = max((int((v.get("position") or {}).get("z_order", 0) or 0) for v in visuals), default=0)
        for wname in wanted:
            if wname in present:
                continue
            z += 1000
            syn = _synthesize_visual_from_worksheet(ws_by_name[wname], pname, filename, z)
            if syn:
                visuals.append(syn)
                synthesized += 1

        page["visuals"] = visuals

    if dropped or synthesized:
        print(f"[Tableau] Post-processing: reconciled dashboard visuals - dropped {dropped} "
              f"empty visual(s), synthesized {synthesized} missing visual(s) from source")
        logger.info("Post-processing: reconcile dropped=%d synthesized=%d", dropped, synthesized)


def _reattach_source_visual_metadata(final_parsed: dict, context: Any) -> None:
    """Re-attach worksheet metadata the VisualsLayout LLM dropped, keyed by the
    visual's source worksheet name, and correct two visual-type misclassifications
    that depend on it.

    The LLM frequently collapses a worksheet's rich ``reference_lines`` into a
    hollow stub (``[{reference_type:"line", value:"", ...}]``), discarding the
    ``boxplot_whisker_type`` / ``boxplot_mark_exclusion`` attributes that are the
    only reliable signal a view is a box-and-whisker plot. The deterministic
    preprocessing (utils._extract_reference_lines) captures these correctly, so
    we copy them back from ``context.visuals`` onto the matching visual. The
    existing _normalize_tableau_visual_type then detects the box plot.

    Two corrections, both grounded in the source worksheet (never guessed):

      1. BOX PLOT: if the source worksheet carries box-plot reference metadata,
         restore that ``reference_lines`` list on the visual (so the box-plot
         detector fires) regardless of the mark the LLM saw (Tableau box plots
         use a Circle/automatic mark, which the LLM mislabels as scatter_plot).

      2. FALSE MAP: a visual the LLM typed ``map`` whose source worksheet has NO
         generated latitude/longitude fields is NOT a geographic map — Tableau
         names like "... Map" mislead the classifier. When such a worksheet puts
         a continuous date (tmn:/my:/yr: prefix) on the column axis with a
         measure, it is a time series → ``line_chart``. The falsely-injected geo
         Category field (added by the geo pass for real maps) is also removed.

    No-op when context is unavailable or a visual has no resolvable worksheet.
    """
    if not context:
        return
    worksheets = (getattr(context, "visuals", None) or {}).get("worksheets", []) or []
    # worksheet name -> its captured metadata
    ws_reflines: Dict[str, list] = {}
    ws_has_generated_geo: Dict[str, bool] = {}
    ws_date_axis: Dict[str, bool] = {}
    for ws in worksheets:
        wname = (ws.get("name") or "").strip()
        if not wname:
            continue
        ws_reflines[wname] = ws.get("reference_lines") or []
        # Generated geo present anywhere in the worksheet's field references?
        blob = json.dumps(ws, ensure_ascii=False).lower()
        ws_has_generated_geo[wname] = ("latitude (generated)" in blob
                                       or "longitude (generated)" in blob)
        # Continuous date on the column axis (tmn:/my:/yr: = date-truncated /
        # month-year / year continuous date fields Tableau puts on a time axis).
        shelves = ws.get("shelves") or {}
        cols_refs = json.dumps(shelves.get("cols") or shelves.get("columns") or "", ensure_ascii=False)
        ws_date_axis[wname] = bool(re.search(r"\[(?:tmn|my|yr):", cols_refs))

    def _ws_name_for(visual: dict) -> str:
        vid = visual.get("id", "") or ""
        m = re.search(r"\$([^$]+?)\(visual\)", vid)
        if m and m.group(1) in ws_reflines:
            return m.group(1)
        t = (visual.get("title") or "").strip()
        return t if t in ws_reflines else ""

    boxplots = 0
    demoted_maps = 0
    for page in (final_parsed.get("visualizations", {}) or {}).get("pages", []) or []:
        for visual in page.get("visuals", []) or []:
            wname = _ws_name_for(visual)
            if not wname:
                continue

            # (1) Box-plot metadata restore. A worksheet is a box-and-whisker
            # plot iff a reference line carries a boxplot whisker type.
            src_rls = ws_reflines.get(wname) or []
            has_box = any(
                isinstance(r, dict) and (r.get("boxplot_whisker_type") or "").strip()
                for r in src_rls
            )
            if has_box:
                # Restore the rich reference lines so the downstream detector and
                # any consumer see the box-plot metadata the LLM discarded.
                visual["reference_lines"] = src_rls
                boxplots += 1

            # (2) False-map demotion → line_chart.
            if ((visual.get("visual_type") or "").strip().lower() in ("map", "filled_map", "filledmap")
                    and not ws_has_generated_geo.get(wname, False)):
                visual["visual_type"] = "line_chart" if ws_date_axis.get(wname) else "bar_chart"
                # Strip the geo Category the (real-map) geo pass may have added,
                # and any leftover generated-geo field — this isn't a map.
                kept = []
                for f in (visual.get("fields") or []):
                    col = f.get("column") or ""
                    if f.get("data_category") in ("StateOrProvince", "City", "Country",
                                                  "County", "PostalCode", "Place"):
                        continue
                    if col in _GEO_GENERATED_FIELDS:
                        continue
                    kept.append(f)
                visual["fields"] = kept
                demoted_maps += 1

    if boxplots or demoted_maps:
        print(f"[Tableau] Post-processing: restored box-plot metadata on {boxplots} visual(s); "
              f"demoted {demoted_maps} false-map visual(s) to chart")
        logger.info("Post-processing: box-plot restores=%d, false-map demotions=%d",
                    boxplots, demoted_maps)


# Tableau calc semantic_types that are row-level DIMENSIONS (categorical labels),
# not measures — a `group` is an IF/THEN bucketing of a string, a `string` calc
# returns text. When such a calc is bound to a categorical role (Category / Rows
# / a slicer's Values), it must stay a dimension; the converter otherwise treats
# any calc as a measure and drops it from axis/slicer slots (leaving the visual
# grouped by the wrong field, or a slicer showing a scalar value list).
_DIMENSION_CALC_SEMANTIC_TYPES = {"group", "string", "set", "bin", "split"}
_CATEGORICAL_ROLES_LC = {"category", "rows", "axis", "columns", "x", "series", "group", "values"}


def _fix_dashboard_visual_bindings(final_parsed: dict, context: Any = None) -> None:
    """Correct three source-grounded visual-binding defects the LLM/mapper produce.

    All three share one cause: a Tableau row-level ``group``/string calc (e.g.
    "Product Description", an IF/THEN label) is treated by the converter as a
    MEASURE, so it is dropped from any categorical (axis / slicer) slot. The
    corrections are grounded in the source worksheet's shelves (via ``context``)
    so nothing is invented.

      1. SLICER on a dimension calc: a slicer whose only field is a group/string
         calc renders a scalar value list instead of a category picker. Mark the
         field so downstream keeps it as a column dimension (handled by the
         shared dimension-calc reclassification below).

      2. CHART missing its category dimension: a bar/treemap/column whose source
         worksheet puts a dimension on rows/cols but whose emitted fields are all
         measures (the LLM dropped the dimension). Restore the dimension from the
         worksheet shelves as the Category/Group field.

      3. BOX-AND-WHISKER → scatterChart: Power BI has no native box plot. Render
         the distribution as a scatter (X = the category dimension, Y = the
         measure) — the closest native shape that stays visible.

    This pass annotates fields with ``_force_dimension=True`` for calc dimensions
    bound to categorical roles; the downstream mapper honours that flag (see
    parser/mapper) to emit them as Column (not Measure) bindings.
    """
    pages = (final_parsed.get("visualizations") or {}).get("pages") or []
    if not pages:
        return

    # Calc name -> (semantic_type, data_type), to recognise dimension calcs.
    calc_sem = {
        (c.get("name") or ""): (c.get("semantic_type") or "").strip().lower()
        for c in (final_parsed.get("calculations") or [])
    }
    calc_dtype = {
        (c.get("name") or ""): (c.get("data_type") or "").strip().lower()
        for c in (final_parsed.get("calculations") or [])
    }

    def _is_dimension_calc(col: str) -> bool:
        # A calc is a dimension when its semantic_type is a categorical kind OR
        # its output data_type is string (a row-level label). The LLM labels the
        # semantic_type inconsistently (group vs split vs string), so the
        # string-data_type check is the robust fallback.
        if calc_sem.get(col, "") in _DIMENSION_CALC_SEMANTIC_TYPES:
            return True
        return calc_dtype.get(col, "") == "string"

    # Source worksheet shelves: worksheet name -> ordered list of dimension
    # column names on a structural shelf or an encoding (so we can restore a
    # dropped category). Tableau exposes a dimension as a `none:`/`attr:`-prefixed
    # field reference; it may sit on rows/cols (axis) OR — when the worksheet has
    # no axis dimension (e.g. a treemap-style tile view) — only on a text/detail/
    # lod/color encoding. We scan rows/cols first (preferred axis dimension), then
    # the rest of the worksheet for encoding dimensions. Internal calc ids
    # ("Calculation_NNN") are resolved to their captions.
    calc_id_to_caption: Dict[str, str] = {}
    if context is not None:
        for c in (context.model.get("calculations", []) if getattr(context, "model", None) else []):
            internal = (c.get("internal_name") or "").strip("[]")
            caption = c.get("caption") or ""
            if internal and caption:
                calc_id_to_caption[internal] = caption

    def _resolve_dim_name(nm: str) -> str:
        return calc_id_to_caption.get(nm, nm)

    ws_dims: Dict[str, list] = {}
    ws_objs: Dict[str, dict] = {}      # worksheet name -> full worksheet dict (for box-plot detail)
    if context is not None:
        for ws in (getattr(context, "visuals", None) or {}).get("worksheets", []) or []:
            wname = (ws.get("name") or "").strip()
            if not wname:
                continue
            ws_objs[wname] = ws
            dims: list = []
            shelves = ws.get("shelves") or {}
            # 1) structural shelves first (true axis dimensions)
            for shelf in ("rows", "cols", "columns"):
                refs = shelves.get(shelf)
                if isinstance(refs, str):
                    refs = [refs]
                for ref in (refs or []):
                    m = re.search(r"\[(?:none|attr):([^:\]]+)", ref)
                    if m:
                        nm = _resolve_dim_name(m.group(1).strip())
                        if nm and nm not in dims:
                            dims.append(nm)
            # 2) encoding dimensions (text/detail/lod/color) — used when a view
            #    has no axis dimension (the dimension drives the marks/tiles).
            #    Scanned from the mark/encoding structures only (NOT filters,
            #    which carry Action/Reset highlight pseudo-fields, not grouping
            #    dimensions).
            enc_sources = []
            # `highlight_fields` carries the discrete pills on the marks card that
            # Tableau exposes for highlighting — i.e. the view's detail/label
            # dimensions. A worksheet can put a dimension ONLY there (e.g. a map
            # whose product label sits on Detail), so `panes` misses it and the
            # category gets dropped (#2: "Shipping Cost by Product Map" lost
            # Product Description). Measures appear with an agg prefix
            # (`sum:`/`avg:`) which the dimension regexes below don't match, so
            # only true dimensions are picked up.
            for key in ("panes", "encodings", "marks", "mark_encodings", "highlight_fields"):
                if ws.get(key):
                    enc_sources.append(json.dumps(ws.get(key), ensure_ascii=False))
            for src in enc_sources:
                # physical/dimension fields (none:/attr: prefix)
                for m in re.finditer(r"\[(?:none|attr):([^:\]]+)", src):
                    nm = _resolve_dim_name(m.group(1).strip())
                    if nm and not nm.startswith("Action (") and nm not in dims:
                        dims.append(nm)
                # CALCULATED dimension fields referenced by internal id
                # (e.g. a group/string calc "Product Description" on a text/detail
                # encoding appears as [Calculation_NNN], which the prefix regex
                # above misses). Resolve the id to its caption so a dropped calc
                # dimension is restorable (#2). Action/Reset pseudo-calcs filtered.
                for m in re.finditer(r"\[(Calculation_\d+)\]", src):
                    nm = _resolve_dim_name(m.group(1).strip())
                    if (nm and nm != m.group(1) and not nm.startswith("Action (")
                            and "reset" not in nm.lower() and nm not in dims):
                        dims.append(nm)
            ws_dims[wname] = dims

    def _ws_name_for(visual: dict) -> str:
        vid = visual.get("id", "") or ""
        m = re.search(r"\$([^$]+?)\(visual\)", vid)
        if m and m.group(1) in ws_dims:
            return m.group(1)
        return (visual.get("title") or "").strip()

    _VALUE_ROLES_LC = {"values", "value", "y", "y2", "size", "color"}
    restored = 0
    boxes = 0
    for page in pages:
        for visual in page.get("visuals", []) or []:
            vt = (visual.get("visual_type") or "").strip().lower()
            fields = visual.get("fields") or []

            # Clear any aggregation on a slicer/paramctrl field — a slicer lists
            # category values and must not aggregate. (The old `_force_dimension`
            # hack that tried to keep a calc on an axis was REMOVED: it forced
            # MEASURES onto Category axes, which Power BI rejects with
            # "Something's wrong with one or more fields". Row-level string calcs
            # like "Product Description" are now emitted by the converter as
            # calculated COLUMNS, which bind on an axis natively — no forcing.)
            for f in fields:
                if not isinstance(f, dict):
                    continue
                if vt in ("slicer", "paramctrl"):
                    f["aggregation"] = ""

            # (1b) Reset / action SHAPE buttons (#10). A Tableau worksheet whose
            # mark class is "Shape" and which displays NO aggregated measure is an
            # action/reset control (e.g. "Reset Filters"/"Reset Parameters"), not a
            # chart. The LLM types it inconsistently (scatter one run, kpi_card the
            # next) and binds the control field on a value/axis, yielding an empty
            # or nonsensical plot. Power BI has no functional filter-reset control,
            # so render it faithfully as a textbox carrying the worksheet's label.
            # Detection is purely STRUCTURAL — mark class + the absence of any
            # quantitative (`:qk`) pill in the worksheet's panes & shelves — so it
            # is immune to the LLM's volatile semantic_type labelling and never
            # keys on input-specific names. A real Shape-mark chart carries a
            # quantitative measure pill and is left untouched.
            _ws_obj = ws_objs.get(_ws_name_for(visual)) or {}
            _marks = _ws_obj.get("marks") or []
            _mark_cls = ((_marks[0].get("class") or "").strip().lower()
                         if (isinstance(_marks, list) and _marks
                             and isinstance(_marks[0], dict)) else "")
            if _mark_cls == "shape":
                _shelf_blob = (json.dumps(_ws_obj.get("panes") or [], ensure_ascii=False)
                               + json.dumps(_ws_obj.get("shelves") or {}, ensure_ascii=False))
                if ":qk" not in _shelf_blob:        # no quantitative (measure) pill
                    visual["visual_type"] = "textbox"
                    if not (visual.get("content") or "").strip():
                        visual["content"] = (visual.get("title") or _ws_name_for(visual) or "").strip()
                    visual["fields"] = []           # a textbox issues no query
                    continue

            # (3) Box-and-whisker → scatter (no native PBI box plot). Detect it
            # from the restored reference-line metadata (boxplot whisker type) —
            # this runs BEFORE _normalize_tableau_visual_types relabels it, so we
            # cannot rely on visual_type == box_whisker_chart yet. X = the category
            # dimension already present, Y = the measure.
            _is_box = (vt == "box_whisker_chart") or any(
                isinstance(r, dict) and (r.get("boxplot_whisker_type") or "").strip()
                for r in (visual.get("reference_lines") or [])
            )
            if _is_box:
                visual["visual_type"] = "scatter_plot"
                boxes += 1
                vt = "scatter_plot"
                # Disaggregate so the distribution (spread) plots rather than one
                # aggregated dot. Grounded in the source worksheet's detail/axis
                # dimensions; idempotent (no-op if a Details field already exists).
                _add_scatter_distribution_detail(visual, ws_objs.get(_ws_name_for(visual)) or {})
                fields = visual.get("fields") or []

            # (2) Restore EVERY source dimension the LLM dropped from a chart or
            # table — not just one. Tableau often puts two dimensions on a view
            # (e.g. Product Description + Category, or a 2-D crosstab); the LLM may
            # emit only one or none. We add each source dimension the model knows
            # about that isn't already on the visual, so the breakdown is faithful.
            # Grounded in the worksheet shelves; only model-known, non-control
            # dimensions (no parameter/flag/reset/action) are added. Scatter is
            # excluded (its disaggregation is handled by the box-plot detail above).
            has_dim = any(
                isinstance(f, dict) and (
                    (f.get("role") or "").lower() in ("category", "rows", "axis", "columns", "x", "series", "group", "details", "detail")
                    or _is_dimension_calc(f.get("column") or "")
                )
                for f in fields
            )
            _DIM_TYPES = ("bar_chart", "stacked_bar_chart", "column_chart",
                          "stacked_column_chart", "clustered_bar_chart", "clustered_column_chart",
                          "treemap", "tree_map", "pie_chart", "donut_chart",
                          "line_chart", "area_chart", "stacked_area_chart",
                          "text_table", "crosstab", "crosstab_table",
                          "heat_map", "square_heat_map", "highlight_table",
                          "pivot_table", "matrix")
            if vt in _DIM_TYPES:
                wname = _ws_name_for(visual)
                _BAD_DIM_SEM = {"parameter", "parameter_passthrough", "flag"}
                def _ok_dim(nm: str) -> bool:
                    if calc_sem.get(nm) in _BAD_DIM_SEM:
                        return False
                    low = nm.lower()
                    return not (low.startswith(("reset ", "action ")) or "reset" in low)
                model_cols = {
                    (c.get("name") or "")
                    for t in (final_parsed.get("tables") or []) for c in (t.get("columns") or [])
                }
                model_cols |= set(calc_sem.keys())
                src_dims = [dn for dn in (ws_dims.get(wname) or []) if _ok_dim(dn) and dn in model_cols]
                present_cols = {(f.get("column") or "") for f in fields if isinstance(f, dict)}
                missing = [dn for dn in src_dims if dn not in present_cols]

                def _owner_of(pick: str) -> str:
                    for t in (final_parsed.get("tables") or []):
                        if any((c.get("name") or "") == pick for c in (t.get("columns") or [])):
                            return t.get("name") or ""
                    return next((c.get("home_table") or "" for c in (final_parsed.get("calculations") or [])
                                 if (c.get("name") or "") == pick), "")

                prepend = not has_dim   # no dimension at all -> the first goes on the axis
                added = []
                for dn in missing:
                    owner = _owner_of(dn)
                    if owner:
                        added.append({"role": "Category", "table": owner, "column": dn,
                                      "aggregation": "", "query_ref": f"[{owner}].[{dn}]"})
                if added:
                    visual["fields"] = (added + fields) if prepend else (fields + added)
                    restored += len(added)
                    # category + size/color measure with no axis -> treemap tiles.
                    if prepend and any(isinstance(f, dict) and (f.get("role") or "").lower() == "size"
                                       for f in fields):
                        visual["visual_type"] = "tree_map"

    if restored or boxes:
        print(f"[Tableau] Post-processing: fixed visual bindings - "
              f"restored {restored} dropped category dim(s), "
              f"{boxes} box-plot to scatter")
        logger.info("Post-processing: category restored=%d, box->scatter=%d",
                    restored, boxes)


def _emit_theme_and_colors(final_parsed: dict, context: Any) -> None:
    """Surface the workbook's captured colours into the common model so the FE
    applies them. Power BI's FE already supports themes/colours; the RE simply
    never emitted them. We write only what the converter understands:

      * ``visualizations.theme.data_palette`` — a report-level colour palette,
        consumed by FE ``styles.normalize_theme`` (→ a custom Power BI theme).
      * per-visual ``style.raw.objects.dataPoint`` — category→colour bindings as
        a ready-made PBIP dataPoint (the SAME shape the PowerBI RE emits), carried
        by the parser as ``raw_objects`` and written verbatim by the FE. This is
        the proven, source-agnostic colour path (no FE selector synthesis).

    Grounded entirely in ``context`` (workbook colour palettes, datasource colour
    encodings, worksheet conditional formatting) — nothing is invented. Idempotent:
    never overwrites a theme or a visual's dataColors that is already present."""
    if not context:
        return
    viz = final_parsed.get("visualizations")
    if not isinstance(viz, dict):
        return

    styles = (getattr(context, "presentation", None) or {}).get("styles") or {}
    cvisuals = getattr(context, "visuals", None) or {}

    def _hexes(seq):
        return [c.strip() for c in (seq or [])
                if isinstance(c, str) and c.strip().startswith("#")]

    def _field_column(field: str) -> str:
        if not field:
            return ""
        dd = _decode_shelf_ref(field)
        if dd and dd.get("column"):
            return dd["column"]
        return field.strip().strip("[]")

    # ---- 1) Report-level theme palette --------------------------------------
    # Prefer the workbook colour-palette with the most discrete colours; fall
    # back to the distinct hexes used across datasource colour encodings.
    best: List[str] = []
    palette_name = ""
    for cp in (styles.get("color_palettes") or []):
        hx = _hexes(cp.get("colors"))
        if len(hx) > len(best):
            best, palette_name = hx, (cp.get("name") or "")
    palette = best
    if not palette:
        seen, acc = set(), []
        for ce in (cvisuals.get("datasource_color_encodings") or []):
            for v in (ce.get("color_assignments") or {}).values():
                if isinstance(v, str) and v.startswith("#") and v not in seen:
                    seen.add(v)
                    acc.append(v)
        palette = acc
    if palette and not viz.get("theme"):
        viz["theme"] = {
            "name": palette_name or (final_parsed.get("name") or "Tableau Theme"),
            "data_palette": palette,
        }

    # ---- 2) Per-visual category colours -------------------------------------
    # bare column name (lower) -> {category value: hex}
    field_colors: Dict[str, Dict[str, str]] = {}

    def _ingest(field, assignments):
        if not field or not isinstance(assignments, dict):
            return
        m = field_colors.setdefault(_field_column(field).lower(), {})
        for val, hexv in assignments.items():
            if isinstance(hexv, str) and hexv.startswith("#"):
                m[str(val)] = hexv

    for ce in (cvisuals.get("datasource_color_encodings") or []):
        _ingest(ce.get("field"), ce.get("color_assignments"))
    for ws in (cvisuals.get("worksheets") or []):
        for cf in (ws.get("conditional_formatting") or []):
            _ingest(cf.get("field"), cf.get("color_assignments"))

    # Per-visual category colours → a PBIP ``dataPoint`` under
    # ``style.raw.objects`` — EXACTLY the shape PowerBI's RE emits (the parser
    # maps ``style.raw.objects`` → ``raw_objects``, which the writer emits
    # verbatim). This is the proven, source-agnostic colour path: no fragile FE
    # selector synthesis. Each entry binds a category VALUE to a colour via a
    # ``Comparison`` scopeId on the visual's colour/legend/category field
    # (Entity = table, Property = column), matching Power BI's own dataPoint
    # format. Only real category values are used — measure-name field-refs are
    # dropped (they are a different, continuous-colour mechanism).
    def _q(v) -> str:
        return "'" + str(v).replace("'", "''") + "'"

    def _is_value_key(k) -> bool:
        s = str(k)
        return not (s.startswith("[") or "].[" in s)

    def _build_datapoints(table: str, column: str, assignments: Dict[str, str]) -> list:
        out = []
        for val, hexv in assignments.items():
            if not (_is_value_key(val) and isinstance(hexv, str) and hexv.startswith("#")):
                continue
            out.append({
                "properties": {"fill": {"solid": {"color": {"expr": {"Literal": {"Value": _q(hexv)}}}}}},
                "selector": {"data": [{"scopeId": {"Comparison": {
                    "ComparisonKind": 0,
                    "Left": {"Column": {"Expression": {"SourceRef": {"Entity": table}},
                                        "Property": column}},
                    "Right": {"Literal": {"Value": _q(val)}},
                }}}]},
            })
        return out

    _CATEG_ROLES = ("color", "legend", "series", "group", "category", "details")
    applied = 0
    for page in (viz.get("pages") or []):
        for visual in (page.get("visuals") or []):
            if not isinstance(visual, dict):
                continue
            existing = (((visual.get("style") or {}).get("raw") or {}).get("objects") or {})
            if existing.get("dataPoint"):
                continue  # already coloured — don't override
            # Bind to the visual's colour/legend/category field that has captured
            # colours — need a real (table, column) for the Comparison selector.
            binding = None
            for f in (visual.get("fields") or []):
                if not isinstance(f, dict):
                    continue
                col = f.get("column") or ""
                if (f.get("role") or "").lower() in _CATEG_ROLES \
                        and f.get("table") and col.lower() in field_colors:
                    binding = (f["table"], col, field_colors[col.lower()])
                    break
            if not binding:
                continue
            dps = _build_datapoints(binding[0], binding[1], binding[2])
            if dps:
                visual.setdefault("style", {}).setdefault("raw", {}).setdefault(
                    "objects", {})["dataPoint"] = dps
                applied += 1

    if (palette and viz.get("theme")) or applied:
        print(f"[Tableau] Post-processing: emitted theme palette ({len(palette)} colour(s)) "
              f"and per-visual dataColors on {applied} visual(s)")
        logger.info("Post-processing: theme_palette=%d visuals_coloured=%d", len(palette), applied)


def _normalize_tableau_visual_type(visual: dict) -> None:
    """Normalize Tableau visual_type values after model output."""
    raw_type = (visual.get("visual_type") or "").strip().lower()
    reference_lines = visual.get("reference_lines") or []

    has_boxplot_metadata = any(
        isinstance(ref_line, dict) and (
            ref_line.get("boxplot_whisker_type")
            or ref_line.get("boxplot_mark_exclusion")
        )
        for ref_line in reference_lines
    )
    if has_boxplot_metadata:
        visual["visual_type"] = "box_whisker_chart"
        return

    # A worksheet the LLM left as visual_type "unknown" (or blank) whose bound
    # fields are ALL measures (no category/axis/legend/detail dimension) is a
    # single-number BAN/KPI tile — classify it deterministically so it renders as
    # a card (not a guessed table). Purely structural (field roles), name-agnostic.
    if raw_type in ("unknown", ""):
        _usable = [f for f in (visual.get("fields") or [])
                   if isinstance(f, dict) and f.get("table") and f.get("column")]
        _DIM_ROLES = {"category", "axis", "rows", "columns", "legend",
                      "series", "group", "details", "detail"}
        if _usable and not any((f.get("role") or "").lower() in _DIM_ROLES for f in _usable):
            visual["visual_type"] = "kpi_card"
            return

    if raw_type in {"combo_type", "combo_chart", "dual_axis_line_chart"}:
        visual["visual_type"] = "dual_axis_chart"
        return

    if raw_type == "dual_axis":
        visual["visual_type"] = "dual_axis_chart"


def _normalize_tableau_visual_types(final_parsed: dict) -> None:
    """Apply Tableau-specific visual type normalization across all pages."""
    visuals_root = final_parsed.get("visualizations", {})
    pages = visuals_root.get("pages", []) if isinstance(visuals_root, dict) else []
    normalized = 0

    for page in pages:
        for visual in page.get("visuals", []):
            before = visual.get("visual_type")
            _normalize_tableau_visual_type(visual)
            after = visual.get("visual_type")
            if before != after:
                normalized += 1

    if normalized:
        print(f"[Tableau] Post-processing: normalized {normalized} visual type(s)")
        logger.info("Post-processing: normalized %d Tableau visual types", normalized)


def _inject_metadata_and_reorder(final_parsed: dict, filename: str) -> dict:
    """Inject common-model metadata and reorder top-level keys."""
    final_parsed.setdefault("schema_version", "1.0")
    final_parsed.setdefault("model_id", str(uuid.uuid4()))
    final_parsed.setdefault("name", filename)
    final_parsed.setdefault("extracted_at", datetime.now(timezone.utc).isoformat())
    print(f"[Tableau] Injected metadata -> model_id: {final_parsed['model_id']}, name: {final_parsed['name']}, extracted_at: {final_parsed['extracted_at']}")
    logger.info("Injected common-model metadata: model_id=%s, name=%s, extracted_at=%s",
                final_parsed['model_id'], final_parsed['name'], final_parsed['extracted_at'])
    _TOP_KEYS = ("schema_version", "model_id", "name", "extracted_at")
    ordered = {k: final_parsed[k] for k in _TOP_KEYS if k in final_parsed}
    ordered.update({k: v for k, v in final_parsed.items() if k not in _TOP_KEYS})
    return ordered


# --- Orchestration ---
def _make_console_encoding_safe() -> None:
    """Windows consoles default to cp1252, which raises UnicodeEncodeError when a
    diagnostic print contains characters like the non-breaking hyphen (\\u2011) —
    common in LLM summaries / visual titles. That crash kills the agent handler
    and HANGS the run on the result-queue wait. Make stdout/stderr lenient so a
    print can never break the flow. Idempotent; harmless to the other flows."""
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


async def run_single_tenant_flow_processor(xml_bytes: bytes, model: str, filename: str = "Tableau Workbook") -> Dict[str, Any]:
    workflow_start = time.perf_counter()
    _make_console_encoding_safe()
    print(f"[Tableau] Starting workbook flow processor for file: {filename}")
    logger.info("Starting Tableau workbook flow processor for file: %s", filename)

    # 1) Preprocess
    section_start = time.perf_counter()
    context = preprocess_workbook(xml_bytes)
    section_elapsed = time.perf_counter() - section_start
    print("[Tableau] Structured preprocessing complete")
    print(f"[Tableau] Preprocessing took {section_elapsed:.3f}s")
    print(f"[Tableau] Found: {len(context.model.get('datasources', []))} datasources, "
          f"{len(context.model.get('tables', []))} tables, "
          f"{len(context.model.get('joins_and_relationships', []))} relationships, "
          f"{len(context.model.get('calculations', []))} calculations")
    logger.info(
        "Preprocessed Tableau workbook: datasources=%d tables=%d relationships=%d calculations=%d",
        len(context.model.get("datasources", [])),
        len(context.model.get("tables", [])),
        len(context.model.get("joins_and_relationships", [])),
        len(context.model.get("calculations", [])),
    )
    logger.info("Tableau timing: preprocessing_seconds=%.3f", section_elapsed)

    # 2) Select model client
    client = _select_model_client(model)

    # Run-level quality report — accumulates agent retries, validator repairs and
    # any degraded sections, and is emitted on the final JSON as `quality_report`.
    quality = QualityReport()

    # Per-call queues — avoids cross-contamination when batch processes
    # multiple Tableau files concurrently.
    q_viz: asyncio.Queue = asyncio.Queue()
    q_tech: asyncio.Queue = asyncio.Queue()
    q_visuals: asyncio.Queue = asyncio.Queue()

    # 3) Register agents and start runtime
    runtime = SingleThreadedAgentRuntime()
    print("[Tableau] Registering agents...")
    await VisualizationsExtractorAgent.register(runtime, type=VISUALIZATIONS_TOPIC, factory=lambda: VisualizationsExtractorAgent(client))
    await TechnicalAnalysisAgent.register(runtime, type=TECHNICAL_TOPIC, factory=lambda: TechnicalAnalysisAgent(client))
    await VisualsLayoutAgent.register(runtime, type=VISUALS_TOPIC, factory=lambda: VisualsLayoutAgent(client))
    print("[Tableau] Agents registered: VisualizationsExtractor, TechnicalAnalysis, VisualsLayout")
    await ClosureAgent.register_closure(runtime, "save_viz", _make_save_viz(q_viz), subscriptions=lambda: [DefaultSubscription()])
    await ClosureAgent.register_closure(runtime, "save_tech", _make_save_tech(q_tech), subscriptions=lambda: [DefaultSubscription()])
    await ClosureAgent.register_closure(runtime, "save_visuals", _make_save_visuals(q_visuals), subscriptions=lambda: [DefaultSubscription()])

    runtime_start = time.perf_counter()
    runtime.start()
    runtime_elapsed = time.perf_counter() - runtime_start
    print("[Tableau] Agent runtime started")
    logger.info("Agent runtime started")
    logger.info("Tableau timing: runtime_startup_seconds=%.3f", runtime_elapsed)

    # 4) Dispatch the data-model extraction as FOUR per-ENTITY-TYPE calls
    #    (data_sources, tables, calculations, relationships) — mirrors the
    #    QlikView/PowerBI split-by-type pattern. Each call gets a focused slice +
    #    a dedicated sub-prompt; results are merged deterministically. The merged
    #    dict is shape-identical to the old monolithic output, so validate +
    #    every downstream pass is unchanged. Visuals are split per dashboard below.
    print("[Tableau] Building per-type extraction slices (data_sources, tables, calculations, relationships)")
    logger.info("Building per-type extraction slices for the Tableau data-model agent")
    extract_start = time.perf_counter()
    extraction_slices, ds_id_by_key = _build_extraction_slices(context)
    for _et, _sl in extraction_slices.items():
        print(f"[Tableau] Extraction slice '{_et}': {len(_sl)} chars")
    _EXTRACTION_ORDER = ("data_sources", "tables", "calculations", "relationships")
    for _et in _EXTRACTION_ORDER:
        await runtime.publish_message(
            VisualizationsRequest(content=extraction_slices[_et], extraction_type=_et),
            topic_id=TopicId(VISUALIZATIONS_TOPIC, source="default"))

    # Collect exactly one result per type (arrival order not guaranteed — each
    # part is tagged with __extraction_type__ so the merge takes the right key).
    _extraction_parts: List[Any] = []
    _extraction_outputs: Dict[str, Any] = {}
    for _ in _EXTRACTION_ORDER:
        viz_msg = await q_viz.get()
        _p = viz_msg.content
        if isinstance(_p, str):
            _p = json.loads(_p)
        _extraction_parts.append(_p)
        if isinstance(_p, dict) and _p.get("__extraction_type__"):
            _extraction_outputs[_p["__extraction_type__"]] = _p

    viz_parsed = _merge_extraction_results(_extraction_parts)
    _link_table_data_sources(viz_parsed, context, ds_id_by_key)
    _dump_extraction_artifacts(filename, extraction_slices, _extraction_outputs, viz_parsed)

    extract_elapsed = time.perf_counter() - extract_start
    print(f"[Tableau] Extraction (4 per-type calls) merged in {extract_elapsed:.3f}s")
    print(f"[Tableau] Extraction counts -> data_sources: {len(viz_parsed.get('data_sources', []))}, "
          f"tables: {len(viz_parsed.get('tables', []))}, "
          f"relationships: {len(viz_parsed.get('relationships', []))}, "
          f"calculations: {len(viz_parsed.get('calculations', []))}")
    logger.info("Received merged Tableau extraction with keys: %s",
                [k for k in viz_parsed.keys() if not k.startswith('__')])
    logger.info("Tableau timing: extraction_seconds=%.3f", extract_elapsed)

    # Visuals/layout: dispatched per dashboard and merged (error-resilient).
    visuals_parsed, visuals_elapsed = await _run_visuals_per_dashboard(runtime, q_visuals, context)

    # 5) Build final output
    final_parsed = viz_parsed if isinstance(viz_parsed, dict) else {}
    validation_elapsed = 0.0

    # Fold the extraction agent's own quality entries (retries, etc.) into the
    # run-level report and strip the private markers off the model dict.
    quality.merge_agent_quality(strip_agent_private_keys(final_parsed))

    # Deterministically repair the core model so the downstream converter's
    # hard invariants (tables[].name, columns[].name, calculations[].name, and
    # the constrained relationship vocabularies) always hold.
    final_parsed = validate_common_model(final_parsed, quality)

    # HARD FAIL only when the core model is empty — an empty tables AND
    # calculations set means extraction genuinely failed and downstream cannot
    # produce anything useful. Visuals / technical are non-core (warn + continue).
    if not final_parsed.get("tables") and not final_parsed.get("calculations"):
        raise ValueError(
            "Tableau extraction produced an empty core model "
            "(no tables and no calculations). quality_report="
            f"{json.dumps(quality.to_dict())}"
        )

    # Merge + validate visuals. A missing/failed visuals section is tolerable —
    # record it and continue with an empty pages list.
    if visuals_parsed is not None:
        if isinstance(visuals_parsed, dict):
            quality.merge_agent_quality(strip_agent_private_keys(visuals_parsed))
        visuals_parsed = validate_visualizations(visuals_parsed, quality)
        final_parsed["visualizations"] = visuals_parsed
        print("[Tableau] Visualizations merged into final output")
    else:
        quality.warn("visuals", "no visualizations produced (agent skipped or failed)")
        final_parsed["visualizations"] = {"pages": []}
        print("[Tableau] No visualizations in final output (agent skipped or failed)")

    # Reconcile the LLM's visuals against the source dashboard zones FIRST: drop
    # empty-shell visuals the LLM emitted and synthesize any worksheet the LLM
    # dropped (the VisualsLayout agent is unreliable run-to-run). Runs before the
    # other visual passes so synthesized visuals flow through normalization,
    # metadata reattach, geo, and field-fix exactly like LLM-emitted ones.
    _reconcile_dashboard_visuals(final_parsed, context, filename)

    # Re-attach source worksheet metadata the VisualsLayout LLM dropped (box-plot
    # reference lines) and correct two source-grounded visual-type mistakes
    # (box-and-whisker mis-typed as scatter; non-geographic "... Map" worksheet
    # mis-typed as map). Must run BEFORE _normalize_tableau_visual_types (which
    # detects the box plot from the restored metadata) and BEFORE the geo pass
    # (so a demoted false-map isn't treated as a real map).
    _reattach_source_visual_metadata(final_parsed, context)

    _normalize_tableau_visual_types(final_parsed)

    # Correct source-grounded visual-binding defects AFTER visual-type
    # normalization so the retypes here (box-and-whisker -> scatter, since PBI
    # has no native box plot; measures-only tile view -> treemap) are final and
    # not reverted. Also: a Tableau group/string calc used as a category (e.g.
    # "Product Description") is forced to stay a dimension so the converter emits
    # it as a Column (not a Measure it would drop), keeping slicers/axes correct.
    _fix_dashboard_visual_bindings(final_parsed, context)

    # Directly inject imageUrl into visuals from zone data (no LLM needed)
    _inject_tableau_image_urls(final_parsed, context.visuals)

    _deduplicate_calculated_columns(final_parsed)

    _deduplicate_federated_tables(final_parsed)

    _rewrite_parameter_references(final_parsed, context.model.get("parameters", []))

    _normalize_calculation_names(final_parsed)

    # Drop calc fields wrongly emitted as null-expression physical columns. Must
    # run AFTER _normalize_calculation_names so the disambiguated measure names
    # (e.g. "NULL Invoices (tbl_sales1)") are present for the match. Without this,
    # the converter emits a phantom sourceColumn and Power BI Desktop fails to
    # load with "The column '<name>' of the table wasn't found.".
    _drop_phantom_calc_columns(final_parsed, context, quality)

    # Move physical-column names that were wrongly placed in depends_on_measures
    # into depends_on_columns. The downstream mapper DROPS any measure whose
    # depends_on_measures lists an unresolvable bare name (e.g. "Sales" on
    # "Profit %"), silently blanking every visual bound to it.
    _reclassify_measure_dependencies(final_parsed, quality)

    # Type MAKEPOINT/MAKELINE spatial calcs as data_type='spatial' (the LLM
    # defaults them to 'string'). Cosmetic for load (the converter drops spatial
    # calcs), but keeps the common model's data types faithful to the source.
    _fix_spatial_calc_types(final_parsed, quality)

    # Tag Tableau self-join alias tables (e.g. tbl_sales1) with
    # source_derived_from_table_id so the converter loads them from the BASE
    # table's physical CSV (tbl_sales.csv) under the alias name. The alias stays
    # a PHYSICAL imported table — its columns are then real (stable IDs) so the
    # self-join relationship binds. (A calculated alias fails with
    # PFE_TM_RELATIONSHIP_END_COLUMN_INVALID; a name-derived CSV import fails with
    # "key didn't match any rows".) Must run after _drop_phantom_calc_columns so
    # an alias's extra calc column doesn't defeat the schema-subset guard.
    _tag_self_join_aliases(final_parsed, quality)

    # Ensure every calculated table (incl. the synthesized Parameters host) has a
    # non-empty DAX body. An empty body makes the converter fall back to a
    # phantom "<table>.csv" import that fails Power BI refresh ("key didn't match
    # any rows"). A table body is written verbatim as DAX (no LLM step), so the
    # body must be valid DAX under the `dax` key.
    _ensure_calculated_table_bodies(final_parsed, quality)

    _expand_measure_names_fields(final_parsed, context.model)

    _fix_visual_field_tables(final_parsed, context)

    _normalize_generated_geo_for_pbi(final_parsed, context)

    # Surface captured Tableau colours (workbook palette + per-category encodings)
    # into the model so the FE renders a matching theme + visual data colours.
    # Runs after all field/type fixes so visual fields and types are final.
    _emit_theme_and_colors(final_parsed, context)

    _generate_relationship_ids(final_parsed)

    _fix_one_to_one_misclassification(final_parsed)

    # RE-2 deterministic data-model corrections (audit fixes #13,17,19,20,21,23):
    # cardinality from join-key semantic_role, geo data_category on all geo
    # columns, format_string from data_type, Parameters home table, calc lineage.
    _fix_relationship_cardinality(final_parsed)
    _ensure_parameters_table(final_parsed)
    _apply_geo_data_categories(final_parsed)
    _fix_calc_format_strings(final_parsed)
    _populate_calc_dependencies(final_parsed, context)
    # Row-Level Security: convert Tableau user filters into common-model `roles`
    # (dynamic RLS via USERPRINCIPALNAME()) so the FE emits SemanticModel roles
    # for the Tableau flow too. No-op when the workbook has no user filters.
    _apply_tableau_rls_roles(final_parsed, context)


    # 6) Technical analysis
    print("[Tableau] Sending validated JSON to technical analysis agent")
    logger.info("Publishing validated JSON to technical analysis agent")
    technical_start = time.perf_counter()
    await runtime.publish_message(TechnicalAnalysisRequest(content=json.dumps(final_parsed)), topic_id=TopicId(TECHNICAL_TOPIC, source="default"))
    tech_msg = await q_tech.get()
    tech_summary = tech_msg.content
    technical_elapsed = time.perf_counter() - technical_start
    print(f"[Tableau] Technical analysis response received in {technical_elapsed:.3f}s")
    logger.info("Technical analysis summary received, length=%d", len(tech_summary or ""))
    logger.info("Tableau timing: technical_analysis_seconds=%.3f", technical_elapsed)

    stop_start = time.perf_counter()
    await runtime.stop_when_idle()
    stop_elapsed = time.perf_counter() - stop_start
    print("[Tableau] Agent runtime stopped")
    logger.info("Agent runtime stopped")
    logger.info("Tableau timing: runtime_shutdown_seconds=%.3f", stop_elapsed)

    final_parsed["technical_summary"] = tech_summary
    print(f"[Tableau] Technical summary length: {len(tech_summary or '')} chars")

    # 7) Inject metadata and reorder keys
    final_parsed = _inject_metadata_and_reorder(final_parsed, filename)

    # 7b) Build KPI lineage (after metadata injection so model_id/name are available)
    from kpi_lineage import build_kpi_lineage
    lineage_start = time.perf_counter()
    try:
        lineage_result = build_kpi_lineage(final_parsed)
        final_parsed["kpi_lineage"] = lineage_result.get("kpi_lineage", [])
        lineage_elapsed = time.perf_counter() - lineage_start
        print(f"[Tableau] KPI lineage built: {len(final_parsed['kpi_lineage'])} KPIs in {lineage_elapsed:.3f}s")
        logger.info("KPI lineage built: %d KPIs in %.3fs", len(final_parsed['kpi_lineage']), lineage_elapsed)
    except Exception as e:
        lineage_elapsed = time.perf_counter() - lineage_start
        print(f"[Tableau] KPI lineage failed: {e}")
        logger.warning("KPI lineage generation failed: %s", e)
        final_parsed["kpi_lineage"] = []

    # 7c) Build consolidated model + node graph
    try:
        from consolidated_model_builder import build_consolidated_model
        final_parsed["consolidated_model"] = build_consolidated_model(final_parsed)
        ng = final_parsed["consolidated_model"]["node_graph"]
        print(f"[Tableau] Node graph built: {ng['node_count']} nodes {ng['type_counts']}")
    except Exception as e:
        print(f"[Tableau] Consolidated model build failed: {e}")
        logger.warning("Consolidated model build failed: %s", e)
        final_parsed["consolidated_model"] = {}
        
    total_elapsed = time.perf_counter() - workflow_start
    print(f"[Tableau] Tableau workbook flow completed successfully in {total_elapsed:.3f}s")
    logger.info(
        "Tableau timing summary: total_seconds=%.3f preprocessing=%.3f runtime_startup=%.3f extraction=%.3f visuals=%.3f validation=%.3f technical_analysis=%.3f runtime_shutdown=%.3f",
        total_elapsed,
        section_elapsed,
        runtime_elapsed,
        extract_elapsed,
        visuals_elapsed,
        validation_elapsed,
        technical_elapsed,
        stop_elapsed,
    )
    logger.info("Tableau workbook flow completed successfully")

    # Stamp tool_type (REQUIRED by the downstream converter's detect_source) and
    # attach the run-level quality report so any degradation is explicit.
    final_parsed = finalize_tableau_envelope(final_parsed, quality)

    print(f"[Tableau] Final output keys: {list(final_parsed.keys())}")
    print(f"[Tableau] Quality report: {quality.to_dict()}")
    return final_parsed
