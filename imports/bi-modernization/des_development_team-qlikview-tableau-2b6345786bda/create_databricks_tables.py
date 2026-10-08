"""
Catalog: genai_demo
Schema: jnj_bi_modernization

"""

import os
from databricks import sql as databricks_sql

DATABRICKS_WORKSPACE_URL = os.getenv("DATABRICKS_WORKSPACE_URL", "dbc-9064b591-ac6c.cloud.databricks.com")
DATABRICKS_ACCESS_TOKEN = os.getenv("DATABRICKS_ACCESS_TOKEN", "")
DATABRICKS_CLUSTER_ID = os.getenv("DATABRICKS_CLUSTER_ID", "0206-091900-f4nnmzzq")
DATABRICKS_HTTP_PATH = os.getenv("DATABRICKS_HTTP_PATH", f"/sql/protocolv1/o/0/{DATABRICKS_CLUSTER_ID}")
CATALOG = os.getenv("DATABRICKS_CATALOG", "genai_demo")
SCHEMA = os.getenv("DATABRICKS_SCHEMA", "jnj_bi_modernization")

DDL_STATEMENTS = [

    # 1. bi_reports — Master table (one row per uploaded file)
    f"""
    CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.bi_reports (
        report_id           STRING      NOT NULL COMMENT 'Primary key (UUID)',
        tool_type           STRING      NOT NULL COMMENT 'tableau / qlikview / powerbi',
        file_name           STRING      COMMENT 'Original uploaded filename',
        uploaded_at         TIMESTAMP   COMMENT 'Upload timestamp',
        executive_summary   STRING      COMMENT 'Generated executive summary text'
    )
    USING DELTA
    COMMENT 'Master table — one row per uploaded BI file'
    """,

    # 2. data_sources — All data sources across all tools
    f"""
    CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.data_sources (
        source_id                STRING      NOT NULL COMMENT 'Primary key (UUID)',
        report_id                STRING      NOT NULL COMMENT 'FK to bi_reports',
        name                     STRING      COMMENT 'Source name',
        source_type              STRING      COMMENT 'SQL Server / Excel / Snowflake / etc.',
        server                   STRING      COMMENT 'Server address',
        database_name            STRING      COMMENT 'Database name',
        schema_name              STRING      COMMENT 'Schema name',
        connection_details       STRING      COMMENT 'Full connection string (QlikView/Tableau)',
        connection_mode          STRING      COMMENT 'import / direct_query / live / extract',
        authentication_method    STRING      COMMENT 'Auth type',
        gateway                  STRING      COMMENT 'Gateway name (Power BI)',
        refresh_schedule         STRING      COMMENT 'Refresh frequency',
        is_extract               BOOLEAN     COMMENT 'Whether its an extract',
        extract_refresh_schedule STRING      COMMENT 'Extract refresh schedule (QlikView)',
        is_published             BOOLEAN     COMMENT 'Whether source is published (QlikView)',
        used_by                  STRING      COMMENT 'JSON array of dashboards/components using this source',
        fingerprint              STRING      COMMENT 'Normalized hash for dedup detection'
    )
    USING DELTA
    COMMENT 'All data sources across Tableau, QlikView, and Power BI'
    """,

    # 3. tables_model — All tables / data model entries
    f"""
    CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.tables_model (
        table_id            STRING      NOT NULL COMMENT 'Primary key (UUID)',
        report_id           STRING      NOT NULL COMMENT 'FK to bi_reports',
        table_name          STRING      COMMENT 'Table name',
        source_object       STRING      COMMENT 'Original source table/view name (Power BI)',
        is_materialized     BOOLEAN     COMMENT 'Imported vs calculated (Power BI)',
        row_count_estimate  BIGINT      COMMENT 'Estimated row count (Power BI)',
        refresh_frequency   STRING      COMMENT 'Refresh frequency (Power BI)',
        used_by             STRING      COMMENT 'JSON array of dashboards using this table',
        column_signature    STRING      COMMENT 'Hash of sorted column names for dedup detection'
    )
    USING DELTA
    COMMENT 'All tables/data model entries across all BI tools'
    """,

    # 4. columns_metadata — All columns / fields
    f"""
    CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.columns_metadata (
        column_id              STRING      NOT NULL COMMENT 'Primary key (UUID)',
        table_id               STRING      NOT NULL COMMENT 'FK to tables_model',
        report_id              STRING      NOT NULL COMMENT 'FK to bi_reports',
        name                   STRING      COMMENT 'Column name',
        source_column          STRING      COMMENT 'Original source column name (Power BI)',
        data_type              STRING      COMMENT 'Data type',
        nullable               BOOLEAN     COMMENT 'Whether nulls allowed (Power BI)',
        is_hidden              BOOLEAN     COMMENT 'Hidden in report view (Power BI)',
        used_in_relationships  BOOLEAN     COMMENT 'Part of a relationship',
        used_in_filters        BOOLEAN     COMMENT 'Used in filters',
        used_in_groupby        BOOLEAN     COMMENT 'Used for grouping (Power BI)',
        used_in_calculations   BOOLEAN     COMMENT 'Referenced in calculations',
        used_in_rls            BOOLEAN     COMMENT 'Used in row-level security (Power BI)',
        distinct_count_high    BOOLEAN     COMMENT 'High cardinality — potential key (Power BI)',
        description            STRING      COMMENT 'Column description (Power BI)'
    )
    USING DELTA
    COMMENT 'All columns/fields across all BI tools'
    """,

    # 5. relationships — All relationships
    f"""
    CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.relationships (
        relationship_id       STRING      NOT NULL COMMENT 'Primary key (UUID)',
        report_id             STRING      NOT NULL COMMENT 'FK to bi_reports',
        left_table            STRING      COMMENT 'Left/from table',
        left_column           STRING      COMMENT 'Left/from column',
        right_table           STRING      COMMENT 'Right/to table',
        right_column          STRING      COMMENT 'Right/to column',
        cardinality           STRING      COMMENT '1:1 / 1:M / M:M',
        join_type             STRING      COMMENT 'inner / left / right / full / cross',
        is_active             BOOLEAN     COMMENT 'Whether relationship is active',
        bidirectional_filter  BOOLEAN     COMMENT 'Bidirectional cross-filter (Power BI)',
        composite_key         BOOLEAN     COMMENT 'Part of composite key (Power BI)',
        enforced_integrity    BOOLEAN     COMMENT 'Referential integrity enforced (Power BI)'
    )
    USING DELTA
    COMMENT 'All relationships across all BI tools'
    """,

    # 6. transformations — All transformations (Power Query steps, Tableau calcs, QlikView script)
    f"""
    CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.transformations (
        transformation_id   STRING      NOT NULL COMMENT 'Primary key (UUID)',
        report_id           STRING      NOT NULL COMMENT 'FK to bi_reports',
        name                STRING      COMMENT 'Transformation name',
        table_name          STRING      COMMENT 'Target table',
        step_type           STRING      COMMENT 'filter / derive / merge / split / aggregate / custom / etc.',
        expression          STRING      COMMENT 'Formula or expression',
        description         STRING      COMMENT 'Human-readable description',
        data_type           STRING      COMMENT 'Result data type (QlikView/Tableau)',
        role                STRING      COMMENT 'dimension / measure (QlikView/Tableau)',
        used_in             STRING      COMMENT 'JSON array of components using this (QlikView/Tableau)',
        filters             STRING      COMMENT 'JSON array of filters on this transformation (QlikView)'
    )
    USING DELTA
    COMMENT 'All transformations — Power Query steps, Tableau calcs, QlikView script transforms'
    """,

    # 7. calculations — DAX measures and calculated columns (Power BI specific)
    f"""
    CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.calculations (
        calculation_id       STRING      NOT NULL COMMENT 'Primary key (UUID)',
        report_id            STRING      NOT NULL COMMENT 'FK to bi_reports',
        name                 STRING      COMMENT 'Calculation name',
        expression           STRING      COMMENT 'Full DAX expression',
        aggregation          STRING      COMMENT 'SUM / AVG / COUNT / CALCULATE / etc.',
        depends_on_columns   STRING      COMMENT 'JSON array — e.g. ["Sales.Amount", "Date.Year"]',
        reusable_metric      BOOLEAN     COMMENT 'Whether this is a base metric reused by others'
    )
    USING DELTA
    COMMENT 'DAX measures and calculated columns (primarily Power BI)'
    """,

    # 8. dashboards — All dashboards / report pages
    f"""
    CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.dashboards (
        dashboard_id      STRING      NOT NULL COMMENT 'Primary key (UUID)',
        report_id         STRING      NOT NULL COMMENT 'FK to bi_reports',
        name              STRING      COMMENT 'Dashboard / page name',
        object_id         STRING      COMMENT 'Original object ID (e.g. SH01, uuid)',
        width             INT         COMMENT 'Canvas width',
        height            INT         COMMENT 'Canvas height',
        background_color  STRING      COMMENT 'Background color'
    )
    USING DELTA
    COMMENT 'All dashboards and report pages across all BI tools'
    """,

    # 9. dashboard_components — Components within dashboards
    f"""
    CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.dashboard_components (
        component_id   STRING      NOT NULL COMMENT 'Primary key (UUID)',
        dashboard_id   STRING      NOT NULL COMMENT 'FK to dashboards',
        name           STRING      COMMENT 'Component name',
        object_id      STRING      COMMENT 'Original object ID (e.g. CH01, LB01)',
        position_x     INT         COMMENT 'X position on dashboard',
        position_y     INT         COMMENT 'Y position on dashboard',
        width          INT         COMMENT 'Component width',
        height         INT         COMMENT 'Component height',
        font_size      INT         COMMENT 'Font size (QlikView)',
        color          STRING      COMMENT 'Color (QlikView)'
    )
    USING DELTA
    COMMENT 'Visual components placed within dashboards'
    """,

    # 10. visualizations — All visualizations / visuals
    f"""
    CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.visualizations (
        viz_id               STRING      NOT NULL COMMENT 'Primary key (UUID)',
        report_id            STRING      NOT NULL COMMENT 'FK to bi_reports',
        dashboard_id         STRING      COMMENT 'FK to dashboards (nullable)',
        object_id            STRING      COMMENT 'Original object ID',
        name                 STRING      COMMENT 'Visual name',
        visual_type          STRING      COMMENT 'bar_chart / pie_chart / table / card / etc.',
        formatting           STRING      COMMENT 'JSON — fonts, sizes, colors, captions'
    )
    USING DELTA
    COMMENT 'All visualizations across all BI tools'
    """,

    # 11. viz_chart_mappings — Chart axis/encoding mappings
    f"""
    CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.viz_chart_mappings (
        mapping_id        STRING      NOT NULL COMMENT 'Primary key (UUID)',
        viz_id            STRING      NOT NULL COMMENT 'FK to visualizations',
        x_axis            STRING      COMMENT 'Field mapped to X axis',
        y_axis            STRING      COMMENT 'Field mapped to Y axis',
        secondary_y_axis  STRING      COMMENT 'Field mapped to secondary Y axis',
        color             STRING      COMMENT 'Color encoding field (Tableau)',
        text              STRING      COMMENT 'Text overlay field (Tableau)',
        size              STRING      COMMENT 'Size encoding field (QlikView)',
        legend            STRING      COMMENT 'Legend field (QlikView)',
        details           STRING      COMMENT 'Details field (QlikView)'
    )
    USING DELTA
    COMMENT 'Chart axis and encoding mappings for visualizations'
    """,

    # 12. viz_table_columns — Straight table column definitions
    f"""
    CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.viz_table_columns (
        column_id    STRING      NOT NULL COMMENT 'Primary key (UUID)',
        viz_id       STRING      NOT NULL COMMENT 'FK to visualizations',
        name         STRING      COMMENT 'Column name',
        expression   STRING      COMMENT 'Column expression or formula'
    )
    USING DELTA
    COMMENT 'Straight table column definitions within visualizations'
    """,

    # 13. viz_data_bindings — What data each visualization uses
    f"""
    CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.viz_data_bindings (
        binding_id    STRING      NOT NULL COMMENT 'Primary key (UUID)',
        viz_id        STRING      NOT NULL COMMENT 'FK to visualizations',
        binding_type  STRING      COMMENT 'dimension / measure / filter / table_used / column_used',
        field_name    STRING      COMMENT 'The field/column/measure name',
        expression    STRING      COMMENT 'Full expression if applicable'
    )
    USING DELTA
    COMMENT 'Data bindings — dimensions, measures, filters per visualization'
    """,

    # 14. filters — All standalone filters
    f"""
    CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.filters (
        filter_id         STRING      NOT NULL COMMENT 'Primary key (UUID)',
        report_id         STRING      NOT NULL COMMENT 'FK to bi_reports',
        object_id         STRING      COMMENT 'Filter object ID (QlikView: LB01)',
        name              STRING      COMMENT 'Filter name',
        scope             STRING      COMMENT 'dataset / page / visual (Power BI) or filter type (QlikView)',
        table_name        STRING      COMMENT 'Table being filtered (Power BI)',
        column_name       STRING      COMMENT 'Column being filtered (Power BI)',
        columns           STRING      COMMENT 'JSON array of columns (QlikView)',
        condition         STRING      COMMENT 'Filter condition/expression (Power BI)',
        hardcoded         BOOLEAN     COMMENT 'Whether filter is hardcoded (Power BI)',
        formatting        STRING      COMMENT 'JSON — font, size, bold, italic, underline (QlikView)',
        background_color  STRING      COMMENT 'Background color (QlikView)'
    )
    USING DELTA
    COMMENT 'All standalone filters across all BI tools'
    """,

    # 15. parameters_variables — All parameters and variables
    f"""
    CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.parameters_variables (
        param_id     STRING      NOT NULL COMMENT 'Primary key (UUID)',
        report_id    STRING      NOT NULL COMMENT 'FK to bi_reports',
        name         STRING      COMMENT 'Parameter/variable name',
        param_type   STRING      COMMENT 'parameter / variable',
        expression   STRING      COMMENT 'Calculation or default value'
    )
    USING DELTA
    COMMENT 'All parameters and variables across all BI tools'
    """,

    # 16. hierarchies — All hierarchies
    f"""
    CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.hierarchies (
        hierarchy_id  STRING      NOT NULL COMMENT 'Primary key (UUID)',
        report_id     STRING      NOT NULL COMMENT 'FK to bi_reports',
        name          STRING      COMMENT 'Hierarchy name',
        members       STRING      COMMENT 'JSON array — ordered list of hierarchy levels'
    )
    USING DELTA
    COMMENT 'All hierarchies across all BI tools'
    """,

    # 17. rls_policies — Row-Level Security policies (Power BI)
    f"""
    CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.rls_policies (
        policy_id        STRING      NOT NULL COMMENT 'Primary key (UUID)',
        report_id        STRING      NOT NULL COMMENT 'FK to bi_reports',
        role_name        STRING      COMMENT 'RLS role name',
        table_name       STRING      COMMENT 'Table the policy applies to',
        rule_expression  STRING      COMMENT 'DAX filter expression'
    )
    USING DELTA
    COMMENT 'Row-Level Security policies (primarily Power BI)'
    """,
]

TABLE_NAMES = [
    "bi_reports", "data_sources", "tables_model", "columns_metadata",
    "relationships", "transformations", "calculations", "dashboards",
    "dashboard_components", "visualizations", "viz_chart_mappings",
    "viz_table_columns", "viz_data_bindings", "filters",
    "parameters_variables", "hierarchies", "rls_policies",
]


def _drop_only_managed_tables(cursor):
    """
    Drops ONLY the 17 managed tables listed in TABLE_NAMES.
    Does NOT drop the schema, catalog, or any other tables outside TABLE_NAMES.
    Drops in reverse order (children before parents) for FK integrity.
    """
    print(f"Dropping {len(TABLE_NAMES)} managed tables from {CATALOG}.{SCHEMA} ...")
    print("(Only these explicit tables are touched — no other tables or schemas are affected)\n")

    drop_order = list(reversed(TABLE_NAMES))
    success_count = 0
    fail_count = 0

    for i, table_name in enumerate(drop_order):
        full_name = f"{CATALOG}.{SCHEMA}.{table_name}"
        try:
            print(f"  [{i+1:2d}/{len(drop_order)}] DROP TABLE IF EXISTS {full_name}...", end=" ")
            cursor.execute(f"DROP TABLE IF EXISTS {full_name}")
            print("OK")
            success_count += 1
        except Exception as e:
            print(f"FAILED: {e}")
            fail_count += 1

    print(f"\nDrop complete. {success_count} dropped, {fail_count} failed.\n")


def _create_tables(cursor):
    """Creates all 17 managed tables using DDL_STATEMENTS."""
    cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
    print(f"Schema {CATALOG}.{SCHEMA} ready.\n")

    success_count = 0
    fail_count = 0

    for i, ddl in enumerate(DDL_STATEMENTS):
        table_name = TABLE_NAMES[i]
        try:
            print(f"  [{i+1:2d}/{len(DDL_STATEMENTS)}] Creating {CATALOG}.{SCHEMA}.{table_name}...", end=" ")
            cursor.execute(ddl)
            print("OK")
            success_count += 1
        except Exception as e:
            print(f"FAILED: {e}")
            fail_count += 1

    print(f"\nCreate complete. {success_count} created, {fail_count} failed.")


def main(drop_recreate: bool = False):
    print(f"Connecting to Databricks: {DATABRICKS_WORKSPACE_URL}")
    print(f"Catalog: {CATALOG}, Schema: {SCHEMA}\n")

    connection = databricks_sql.connect(
        server_hostname=DATABRICKS_WORKSPACE_URL,
        http_path=DATABRICKS_HTTP_PATH,
        access_token=DATABRICKS_ACCESS_TOKEN,
    )
    cursor = connection.cursor()

    try:
        if drop_recreate:
            print("=== Mode: DROP + RECREATE (only the 17 managed tables) ===\n")
            _drop_only_managed_tables(cursor)
            print("=== Recreating tables ===\n")
            _create_tables(cursor)
        else:
            print("=== Mode: CREATE IF NOT EXISTS ===\n")
            _create_tables(cursor)

        print(f"\nManaged tables in {CATALOG}.{SCHEMA}:")
        for name in TABLE_NAMES:
            print(f"  - {name}")
    finally:
        cursor.close()
        connection.close()
        print("\nConnection closed.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Manage Databricks BI metadata tables.")
    parser.add_argument(
        "--drop-recreate",
        action="store_true",
        help=(
            f"Drop and recreate only the {len(TABLE_NAMES)} managed tables in "
            f"{CATALOG}.{SCHEMA}. No other tables or schemas are affected."
        ),
    )
    args = parser.parse_args()
    main(drop_recreate=args.drop_recreate)
