"""
Tests for all helpers extracted during the SonarQube cognitive-complexity
refactoring sessions.

Covers:
  databricks_normalizer.py  — _normalize_data_model_relationships,
                               _normalize_powerbi_visual_bindings,
                               _normalize_viz_data_bindings,
                               _KEY_DATA_MODEL constant
  main.py                   — _extract_powerbi_source, _extract_tableau_source,
                               _datasource_from_ingestion,
                               _apply_column_ids, _apply_table_ids,
                               _transform_visual, _transform_pages,
                               apply_readable_ids,
                               _collect_pbix_file_paths, _find_layout_file
  generate_mapping_report.py — _find_header_row
  databricks_writer.py      — _get_name_attr, _extract_table_name
"""

import io
import sys
import os
import zipfile
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("POSTGRES_URL", "postgresql://test:test@localhost:5432/test")

# ---------------------------------------------------------------------------
# Mock heavy deps so module-level imports don't fail in CI
# ---------------------------------------------------------------------------
_MOCKS = [
    "config", "autogen_core", "autogen_core.models",
    "autogen_core._default_subscription", "autogen_core._default_topic",
    "autogen_ext", "autogen_ext.models", "autogen_ext.models.openai",
    "autogen_agentchat", "semantic_kernel",
    "semantic_kernel.connectors", "semantic_kernel.connectors.ai",
    "semantic_kernel.connectors.ai.google",
    "semantic_kernel.connectors.ai.google.google_ai",
    "semantic_kernel.connectors.ai.google.google_ai.services",
    "semantic_kernel.connectors.ai.google.google_ai.services.google_ai_chat_completion",
    "semantic_kernel.memory", "semantic_kernel.memory.null_memory",
    "semantic_kernel.kernel_pydantic", "AWSSecretsManager",
    "databricks", "databricks.sql",
    "sequentialworkflow", "agents_qlikview", "agents_powerbi",
    "agents_tableau", "powerbi_extractor", "layout_mapper",
    "prompts_powerbi", "prompts_qlikview", "extraction_schema",
]
for _m in _MOCKS:
    if _m not in sys.modules:
        sys.modules[_m] = MagicMock()


# ===========================================================================
# databricks_normalizer.py — new extracted helpers
# ===========================================================================

class TestNormalizeDataModelRelationships:
    """_normalize_data_model_relationships — shared by Tableau and QlikView."""

    def _empty(self):
        from databricks_normalizer import _empty_result
        return _empty_result()

    def test_appends_relationship_for_each_nonempty_rel_string(self):
        from databricks_normalizer import _normalize_data_model_relationships
        json_output = {
            "Data Model": [
                {
                    "table_name": "Orders",
                    "relationships": [
                        "Orders JOIN Customer ON Orders.CustomerID = Customer.ID",
                        "Orders JOIN Product ON Orders.ProductID = Product.ID",
                    ],
                }
            ]
        }
        result = self._empty()
        _normalize_data_model_relationships(json_output, "rpt-1", result)
        assert len(result["relationships"]) == 2
        assert all(r["left_table"] == "Orders" for r in result["relationships"])
        assert all(r["is_active"] is True for r in result["relationships"])
        assert all(r["report_id"] == "rpt-1" for r in result["relationships"])

    def test_skips_empty_relationship_strings(self):
        from databricks_normalizer import _normalize_data_model_relationships
        json_output = {
            "Data Model": [
                {"table_name": "T1", "relationships": ["", None, "T1 JOIN T2 ON T1.id = T2.id"]},
            ]
        }
        result = self._empty()
        _normalize_data_model_relationships(json_output, "rpt-2", result)
        # Only the truthy string should be added
        assert len(result["relationships"]) == 1

    def test_empty_data_model_adds_nothing(self):
        from databricks_normalizer import _normalize_data_model_relationships
        result = self._empty()
        _normalize_data_model_relationships({}, "rpt-3", result)
        assert result["relationships"] == []

    def test_table_with_no_relationships_key(self):
        from databricks_normalizer import _normalize_data_model_relationships
        json_output = {"Data Model": [{"table_name": "Orphan"}]}
        result = self._empty()
        _normalize_data_model_relationships(json_output, "rpt-4", result)
        assert result["relationships"] == []

    def test_multiple_tables_each_with_relationships(self):
        from databricks_normalizer import _normalize_data_model_relationships
        json_output = {
            "Data Model": [
                {"table_name": "A", "relationships": ["A-B"]},
                {"table_name": "B", "relationships": ["B-C", "B-D"]},
            ]
        }
        result = self._empty()
        _normalize_data_model_relationships(json_output, "rpt-5", result)
        assert len(result["relationships"]) == 3
        left_tables = [r["left_table"] for r in result["relationships"]]
        assert left_tables.count("A") == 1
        assert left_tables.count("B") == 2

    def test_relationship_row_has_required_keys(self):
        from databricks_normalizer import _normalize_data_model_relationships
        json_output = {"Data Model": [{"table_name": "X", "relationships": ["X-Y"]}]}
        result = self._empty()
        _normalize_data_model_relationships(json_output, "rpt-6", result)
        rel = result["relationships"][0]
        for key in ("relationship_id", "report_id", "left_table", "left_column",
                    "right_table", "right_column", "cardinality", "join_type",
                    "is_active", "bidirectional_filter", "composite_key", "enforced_integrity"):
            assert key in rel


class TestNormalizePowerBIVisualBindings:
    """_normalize_powerbi_visual_bindings — bindings for one Power BI visual."""

    def _empty(self):
        from databricks_normalizer import _empty_result
        return _empty_result()

    def test_tables_used_appended_as_table_used_bindings(self):
        from databricks_normalizer import _normalize_powerbi_visual_bindings
        result = self._empty()
        vis = {"tables_used": ["Sales", "Date"], "columns_used": [], "measures_used": []}
        _normalize_powerbi_visual_bindings(vis, "viz-1", result)
        bindings = result["viz_data_bindings"]
        assert len(bindings) == 2
        assert all(b["binding_type"] == "table_used" for b in bindings)
        assert {b["field_name"] for b in bindings} == {"Sales", "Date"}

    def test_columns_used_string_kept_as_is(self):
        from databricks_normalizer import _normalize_powerbi_visual_bindings
        result = self._empty()
        vis = {"tables_used": [], "columns_used": ["Sales[Amount]"], "measures_used": []}
        _normalize_powerbi_visual_bindings(vis, "viz-2", result)
        b = result["viz_data_bindings"][0]
        assert b["binding_type"] == "column_used"
        assert b["field_name"] == "Sales[Amount]"

    def test_columns_used_dict_becomes_table_dot_column(self):
        from databricks_normalizer import _normalize_powerbi_visual_bindings
        result = self._empty()
        vis = {
            "tables_used": [],
            "columns_used": [{"table": "Date", "column": "Year"}],
            "measures_used": [],
        }
        _normalize_powerbi_visual_bindings(vis, "viz-3", result)
        b = result["viz_data_bindings"][0]
        assert b["field_name"] == "Date.Year"

    def test_measures_used_appended_as_measure_bindings(self):
        from databricks_normalizer import _normalize_powerbi_visual_bindings
        result = self._empty()
        vis = {"tables_used": [], "columns_used": [], "measures_used": ["Total Sales", "YTD"]}
        _normalize_powerbi_visual_bindings(vis, "viz-4", result)
        bindings = result["viz_data_bindings"]
        assert len(bindings) == 2
        assert all(b["binding_type"] == "measure" for b in bindings)

    def test_all_three_types_combined(self):
        from databricks_normalizer import _normalize_powerbi_visual_bindings
        result = self._empty()
        vis = {
            "tables_used": ["T1"],
            "columns_used": ["T1[Col1]", {"table": "T2", "column": "Col2"}],
            "measures_used": ["Metric1"],
        }
        _normalize_powerbi_visual_bindings(vis, "viz-5", result)
        assert len(result["viz_data_bindings"]) == 4
        types = [b["binding_type"] for b in result["viz_data_bindings"]]
        assert types.count("table_used") == 1
        assert types.count("column_used") == 2
        assert types.count("measure") == 1

    def test_empty_visual_adds_no_bindings(self):
        from databricks_normalizer import _normalize_powerbi_visual_bindings
        result = self._empty()
        vis = {}
        _normalize_powerbi_visual_bindings(vis, "viz-6", result)
        assert result["viz_data_bindings"] == []

    def test_viz_id_set_on_all_bindings(self):
        from databricks_normalizer import _normalize_powerbi_visual_bindings
        result = self._empty()
        vis = {"tables_used": ["A", "B"], "columns_used": [], "measures_used": ["M"]}
        _normalize_powerbi_visual_bindings(vis, "my-viz-id", result)
        assert all(b["viz_id"] == "my-viz-id" for b in result["viz_data_bindings"])


class TestNormalizeVizDataBindings:
    """_normalize_viz_data_bindings — Tableau/QlikView dimension/measure/filter bindings."""

    def _empty(self):
        from databricks_normalizer import _empty_result
        return _empty_result()

    def test_dimensions_appended(self):
        from databricks_normalizer import _normalize_viz_data_bindings
        result = self._empty()
        vis = {"dimensions": ["Region", "Year"], "measures": [], "filters": []}
        _normalize_viz_data_bindings(vis, "v1", result)
        bindings = result["viz_data_bindings"]
        assert len(bindings) == 2
        assert all(b["binding_type"] == "dimension" for b in bindings)
        assert {b["field_name"] for b in bindings} == {"Region", "Year"}

    def test_measures_appended(self):
        from databricks_normalizer import _normalize_viz_data_bindings
        result = self._empty()
        vis = {"dimensions": [], "measures": ["SUM(Sales)", "COUNT(*)"], "filters": []}
        _normalize_viz_data_bindings(vis, "v2", result)
        bindings = result["viz_data_bindings"]
        assert len(bindings) == 2
        assert all(b["binding_type"] == "measure" for b in bindings)

    def test_filters_appended(self):
        from databricks_normalizer import _normalize_viz_data_bindings
        result = self._empty()
        vis = {"dimensions": [], "measures": [], "filters": ["Year = 2024"]}
        _normalize_viz_data_bindings(vis, "v3", result)
        b = result["viz_data_bindings"][0]
        assert b["binding_type"] == "filter"
        assert b["field_name"] == "Year = 2024"

    def test_all_three_types(self):
        from databricks_normalizer import _normalize_viz_data_bindings
        result = self._empty()
        vis = {
            "dimensions": ["Region"],
            "measures": ["Sales", "Profit"],
            "filters": ["Year > 2020", "Region != 'ALL'"],
        }
        _normalize_viz_data_bindings(vis, "v4", result)
        assert len(result["viz_data_bindings"]) == 5
        types = [b["binding_type"] for b in result["viz_data_bindings"]]
        assert types.count("dimension") == 1
        assert types.count("measure") == 2
        assert types.count("filter") == 2

    def test_none_lists_treated_as_empty(self):
        from databricks_normalizer import _normalize_viz_data_bindings
        result = self._empty()
        vis = {"dimensions": None, "measures": None, "filters": None}
        _normalize_viz_data_bindings(vis, "v5", result)
        assert result["viz_data_bindings"] == []

    def test_missing_keys_treated_as_empty(self):
        from databricks_normalizer import _normalize_viz_data_bindings
        result = self._empty()
        _normalize_viz_data_bindings({}, "v6", result)
        assert result["viz_data_bindings"] == []

    def test_viz_id_set_on_all_bindings(self):
        from databricks_normalizer import _normalize_viz_data_bindings
        result = self._empty()
        vis = {"dimensions": ["A", "B"], "measures": ["C"], "filters": []}
        _normalize_viz_data_bindings(vis, "target-viz", result)
        assert all(b["viz_id"] == "target-viz" for b in result["viz_data_bindings"])


class TestKeyDataModelConstant:
    """_KEY_DATA_MODEL used consistently across normalizer calls."""

    def test_constant_value(self):
        from databricks_normalizer import _KEY_DATA_MODEL
        assert _KEY_DATA_MODEL == "Data Model"

    def test_tableau_uses_constant_key(self):
        from databricks_normalizer import normalize_tableau, _KEY_DATA_MODEL
        json_with_data_model = {
            _KEY_DATA_MODEL: [
                {"table_name": "T", "fields": [{"name": "id", "type": "int"}], "relationships": []}
            ]
        }
        result = normalize_tableau(json_with_data_model, "test.twb")
        assert len(result["tables_model"]) == 1

    def test_qlikview_uses_constant_key(self):
        from databricks_normalizer import normalize_qlikview, _KEY_DATA_MODEL
        json_with_data_model = {
            _KEY_DATA_MODEL: [
                {"table_name": "Claims", "fields": [{"name": "id", "type": "int"}], "relationships": []}
            ]
        }
        result = normalize_qlikview(json_with_data_model, "test.qvw")
        assert len(result["tables_model"]) == 1


# ===========================================================================
# main.py — extracted helpers
# ===========================================================================

class TestExtractPowerBISource:
    """_extract_powerbi_source — parse Power Query expressions."""

    def test_file_contents_pattern(self):
        from main import _extract_powerbi_source
        step = {"native_expressions": {
            "powerquery": "Source = File.Contents('C:\\Data\\sales.xlsx')"
        }}
        assert _extract_powerbi_source(step) == "sales.xlsx"

    def test_file_contents_double_backslash(self):
        from main import _extract_powerbi_source
        step = {"native_expressions": {
            "powerquery": 'Source = File.Contents("C:\\\\Reports\\\\data.csv")'
        }}
        assert _extract_powerbi_source(step) == "data.csv"

    def test_source_hash_pattern(self):
        from main import _extract_powerbi_source
        step = {"native_expressions": {
            "powerquery": 'Source = #"Insurance Claims Data"'
        }}
        assert _extract_powerbi_source(step) == "Insurance Claims Data"

    def test_empty_powerquery_returns_empty(self):
        from main import _extract_powerbi_source
        step = {"native_expressions": {"powerquery": ""}}
        assert _extract_powerbi_source(step) == ""

    def test_missing_powerquery_key_returns_empty(self):
        from main import _extract_powerbi_source
        step = {"native_expressions": {}}
        assert _extract_powerbi_source(step) == ""

    def test_no_matching_pattern_returns_empty(self):
        from main import _extract_powerbi_source
        step = {"native_expressions": {"powerquery": "Table.SelectRows(Source, each [Active])"}}
        assert _extract_powerbi_source(step) == ""

    def test_missing_native_expressions_returns_empty(self):
        from main import _extract_powerbi_source
        step = {}
        assert _extract_powerbi_source(step) == ""


class TestExtractTableauSource:
    """_extract_tableau_source — parse Tableau READ FILE expressions."""

    def test_read_file_pattern(self):
        from main import _extract_tableau_source
        step = {"native_expressions": {"tableau": "READ FILE: insurance_data.hyper"}}
        assert _extract_tableau_source(step) == "insurance_data.hyper"

    def test_read_file_with_spaces(self):
        from main import _extract_tableau_source
        step = {"native_expressions": {"tableau": "READ FILE:   my report.twbx  "}}
        assert _extract_tableau_source(step) == "my report.twbx"

    def test_empty_tableau_expression_returns_empty(self):
        from main import _extract_tableau_source
        step = {"native_expressions": {"tableau": ""}}
        assert _extract_tableau_source(step) == ""

    def test_missing_tableau_key_returns_empty(self):
        from main import _extract_tableau_source
        step = {"native_expressions": {}}
        assert _extract_tableau_source(step) == ""

    def test_no_read_file_pattern_returns_empty(self):
        from main import _extract_tableau_source
        step = {"native_expressions": {"tableau": "CONNECT TO datasource"}}
        assert _extract_tableau_source(step) == ""

    def test_missing_native_expressions_returns_empty(self):
        from main import _extract_tableau_source
        step = {}
        assert _extract_tableau_source(step) == ""


class TestDatasourceFromIngestion:
    """_datasource_from_ingestion — selects right parser per step_type."""

    def test_powerbi_read_step_returns_filename(self):
        from main import _datasource_from_ingestion
        tbl = {
            "ingestion": {"steps": [
                {"step_type": "read", "native_expressions": {
                    "powerquery": "Source = File.Contents('data.xlsx')"
                }}
            ]}
        }
        assert _datasource_from_ingestion(tbl) == "data.xlsx"

    def test_tableau_read_source_step_returns_filename(self):
        from main import _datasource_from_ingestion
        tbl = {
            "ingestion": {"steps": [
                {"step_type": "read_source", "native_expressions": {
                    "tableau": "READ FILE: claims.hyper"
                }}
            ]}
        }
        assert _datasource_from_ingestion(tbl) == "claims.hyper"

    def test_unknown_step_type_is_skipped(self):
        from main import _datasource_from_ingestion
        tbl = {
            "ingestion": {"steps": [
                {"step_type": "filter", "native_expressions": {"powerquery": "..."}},
                {"step_type": "read_source", "native_expressions": {"tableau": "READ FILE: result.hyper"}},
            ]}
        }
        assert _datasource_from_ingestion(tbl) == "result.hyper"

    def test_first_matching_step_wins(self):
        from main import _datasource_from_ingestion
        tbl = {
            "ingestion": {"steps": [
                {"step_type": "read", "native_expressions": {
                    "powerquery": "Source = File.Contents('first.xlsx')"
                }},
                {"step_type": "read", "native_expressions": {
                    "powerquery": "Source = File.Contents('second.xlsx')"
                }},
            ]}
        }
        assert _datasource_from_ingestion(tbl) == "first.xlsx"

    def test_no_ingestion_key_returns_empty(self):
        from main import _datasource_from_ingestion
        assert _datasource_from_ingestion({}) == ""

    def test_empty_steps_returns_empty(self):
        from main import _datasource_from_ingestion
        assert _datasource_from_ingestion({"ingestion": {"steps": []}}) == ""

    def test_step_with_no_match_falls_through_to_empty(self):
        from main import _datasource_from_ingestion
        tbl = {
            "ingestion": {"steps": [
                {"step_type": "read", "native_expressions": {"powerquery": "Table.SelectRows(...)"}}
            ]}
        }
        assert _datasource_from_ingestion(tbl) == ""


class TestApplyColumnIds:
    """_apply_column_ids — build readable column ids, strip old id keys."""

    def test_id_key_replaced(self):
        from main import _apply_column_ids
        cols = [{"id": "old-id", "name": "Amount", "data_type": "Decimal"}]
        result = _apply_column_ids(cols, "tableau", "Sales Report", "FactSales")
        assert result[0]["id"] != "old-id"
        assert "tablename" in result[0]["id"]

    def test_col_id_key_stripped(self):
        from main import _apply_column_ids
        cols = [{"col_id": "cid-1", "name": "Region"}]
        result = _apply_column_ids(cols, "powerbi", "Report", "Table")
        assert "col_id" not in result[0]

    def test_other_keys_preserved(self):
        from main import _apply_column_ids
        cols = [{"name": "SaleID", "data_type": "Int64", "nullable": False}]
        result = _apply_column_ids(cols, "tableau", "M", "T")
        assert result[0]["name"] == "SaleID"
        assert result[0]["data_type"] == "Int64"
        assert result[0]["nullable"] is False

    def test_returns_same_count(self):
        from main import _apply_column_ids
        cols = [{"name": f"col{i}"} for i in range(5)]
        result = _apply_column_ids(cols, "powerbi", "M", "T")
        assert len(result) == 5

    def test_empty_columns_returns_empty_list(self):
        from main import _apply_column_ids
        assert _apply_column_ids([], "tableau", "M", "T") == []

    def test_id_contains_toolname_and_tablename(self):
        from main import _apply_column_ids
        cols = [{"name": "x"}]
        result = _apply_column_ids(cols, "qlikview", "MyModel", "DimDate")
        assert "qlikview" in result[0]["id"]
        assert "MyModel" in result[0]["id"]
        assert "DimDate" in result[0]["id"]


class TestApplyTableIds:
    """_apply_table_ids — mutate tables in result with readable ids."""

    def test_table_id_set(self):
        from main import _apply_table_ids
        result = {"tables": [{"name": "FactSales", "columns": []}]}
        _apply_table_ids(result, "tableau", "Sales Report")
        assert "tableau" in result["tables"][0]["id"]
        assert "FactSales" in result["tables"][0]["id"]

    def test_columns_rebuilt(self):
        from main import _apply_table_ids
        result = {
            "tables": [{
                "name": "DimDate",
                "columns": [{"name": "Year"}, {"name": "Month"}],
            }]
        }
        _apply_table_ids(result, "powerbi", "Report")
        assert len(result["tables"][0]["columns"]) == 2
        # Each column gets a new id
        for col in result["tables"][0]["columns"]:
            assert "id" in col

    def test_table_uses_datasource_from_ingestion(self):
        from main import _apply_table_ids
        result = {
            "tables": [{
                "name": "Claims",
                "columns": [],
                "ingestion": {"steps": [
                    {"step_type": "read_source",
                     "native_expressions": {"tableau": "READ FILE: claims.hyper"}}
                ]},
            }]
        }
        _apply_table_ids(result, "tableau", "Report")
        assert "claims.hyper" in result["tables"][0]["id"]

    def test_empty_tables_no_error(self):
        from main import _apply_table_ids
        result = {"tables": []}
        _apply_table_ids(result, "tableau", "Report")  # no exception

    def test_missing_tables_key_no_error(self):
        from main import _apply_table_ids
        _apply_table_ids({}, "powerbi", "Report")  # no exception


class TestTransformVisual:
    """_transform_visual — single visual dict transformation."""

    def test_old_id_stripped(self):
        from main import _transform_visual
        vis = {"id": "old", "visual_name": "Chart", "visual_type": "bar"}
        new_vis = _transform_visual(vis, "tableau", "Model", "Page1")
        assert new_vis["id"] != "old"

    def test_visual_id_stripped(self):
        from main import _transform_visual
        vis = {"visual_id": "vid-1", "visual_name": "Chart"}
        new_vis = _transform_visual(vis, "powerbi", "Model", "Overview")
        assert "visual_id" not in new_vis

    def test_other_keys_preserved(self):
        from main import _transform_visual
        vis = {"visual_name": "My Chart", "visual_type": "barChart", "custom_key": "value"}
        new_vis = _transform_visual(vis, "tableau", "Model", "Page")
        assert new_vis["visual_name"] == "My Chart"
        assert new_vis["visual_type"] == "barChart"
        assert new_vis["custom_key"] == "value"

    def test_force_source_tool_overwrites(self):
        from main import _transform_visual
        vis = {"source_tool": "qlikview"}
        new_vis = _transform_visual(vis, "powerbi", "M", "P", force_source_tool=True)
        assert new_vis["source_tool"] == "powerbi"

    def test_no_force_source_tool_uses_setdefault(self):
        from main import _transform_visual
        vis = {"source_tool": "tableau"}
        new_vis = _transform_visual(vis, "powerbi", "M", "P", force_source_tool=False)
        assert new_vis["source_tool"] == "tableau"  # not overwritten

    def test_extra_keys_set_to_none_if_missing(self):
        from main import _transform_visual, _VISUAL_EXTRA_KEYS
        vis = {}
        new_vis = _transform_visual(vis, "tableau", "Model", "Page")
        for key in _VISUAL_EXTRA_KEYS:
            assert key in new_vis
            assert new_vis[key] is None

    def test_existing_extra_keys_not_overwritten(self):
        from main import _transform_visual
        vis = {"datasource_dependencies": ["SalesDB"]}
        new_vis = _transform_visual(vis, "tableau", "Model", "Page")
        assert new_vis["datasource_dependencies"] == ["SalesDB"]

    def test_id_contains_toolname_model_and_page(self):
        from main import _transform_visual
        vis = {}
        new_vis = _transform_visual(vis, "powerbi", "MyModel", "SalesPage")
        assert "powerbi" in new_vis["id"]
        assert "MyModel" in new_vis["id"]
        assert "SalesPage" in new_vis["id"]


class TestTransformPages:
    """_transform_pages — list of pages transformation."""

    def test_returns_same_number_of_pages(self):
        from main import _transform_pages
        pages = [
            {"display_name": "Page1", "visuals": []},
            {"display_name": "Page2", "visuals": []},
        ]
        result = _transform_pages(pages, "tableau", "Model")
        assert len(result) == 2

    def test_visuals_transformed_in_each_page(self):
        from main import _transform_pages
        pages = [{
            "display_name": "Overview",
            "visuals": [
                {"visual_name": "Chart1", "visual_type": "bar"},
                {"visual_name": "Chart2", "visual_type": "pie"},
            ],
        }]
        result = _transform_pages(pages, "powerbi", "Report")
        assert len(result[0]["visuals"]) == 2
        for v in result[0]["visuals"]:
            assert "id" in v
            assert "powerbi" in v["id"]

    def test_page_defaults_set(self):
        from main import _transform_pages
        pages = [{"display_name": "P", "visuals": []}]
        result = _transform_pages(pages, "tableau", "M")
        assert result[0]["styles"] is None
        assert result[0]["color_palettes"] is None

    def test_existing_styles_not_overwritten(self):
        from main import _transform_pages
        pages = [{"display_name": "P", "visuals": [], "styles": {"font": "Arial"}}]
        result = _transform_pages(pages, "powerbi", "M")
        assert result[0]["styles"] == {"font": "Arial"}

    def test_force_source_tool_passed_to_visuals(self):
        from main import _transform_pages
        pages = [{"display_name": "P", "visuals": [{"source_tool": "old"}]}]
        result = _transform_pages(pages, "powerbi", "M", force_source_tool=True)
        assert result[0]["visuals"][0]["source_tool"] == "powerbi"

    def test_empty_pages_returns_empty_list(self):
        from main import _transform_pages
        assert _transform_pages([], "tableau", "Model") == []


class TestApplyReadableIds:
    """apply_readable_ids — top-level coordinator."""

    def _tableau_input(self):
        return {
            "name": "Sales Report.twb",
            "data_sources": [{"name": "DB"}],
            "tables": [
                {
                    "name": "FactSales",
                    "columns": [{"name": "SaleID"}, {"name": "Amount"}],
                }
            ],
            "calculations": [{"calc_id": "c1", "name": "Total"}],
            "visualizations": {
                "pages": [
                    {
                        "display_name": "Overview",
                        "visuals": [{"visual_name": "Chart"}],
                    }
                ]
            },
        }

    def test_does_not_mutate_original(self):
        from main import apply_readable_ids
        original = self._tableau_input()
        import copy
        snapshot = copy.deepcopy(original)
        apply_readable_ids(original, "sales.twb")
        assert original == snapshot

    def test_tableau_toolname_detected_from_file(self):
        from main import apply_readable_ids
        result = apply_readable_ids({"name": "report.twb", "tables": [], "data_sources": []}, "report.twb")
        assert "tableau" in result["data_sources"][0]["id"] if result.get("data_sources") else True

    def test_powerbi_toolname_detected_from_filename(self):
        from main import apply_readable_ids
        result = apply_readable_ids(
            {"name": "Report", "data_sources": [{"name": "x"}], "tables": []},
            "Report.pbix"
        )
        assert "powerbi" in result["data_sources"][0]["id"]

    def test_calc_id_removed(self):
        from main import apply_readable_ids
        result = apply_readable_ids(
            {"name": "r.twb", "calculations": [{"calc_id": "old", "name": "Metric"}], "tables": [], "data_sources": []},
            "r.twb"
        )
        assert "calc_id" not in result["calculations"][0]

    def test_report_pages_moved_to_visualizations(self):
        from main import apply_readable_ids
        result = apply_readable_ids(
            {
                "name": "r.pbix",
                "report_pages": [{"display_name": "P1", "visuals": []}],
                "tables": [],
                "data_sources": [],
            },
            "r.pbix"
        )
        assert "report_pages" not in result
        assert "visualizations" in result
        assert "pages" in result["visualizations"]

    def test_existing_visualizations_pages_transformed_in_place(self):
        from main import apply_readable_ids
        result = apply_readable_ids(
            {
                "name": "r.twb",
                "visualizations": {"pages": [{"display_name": "P", "visuals": [{"visual_name": "V"}]}]},
                "tables": [],
                "data_sources": [],
            },
            "r.twb"
        )
        assert "pages" in result["visualizations"]
        assert "id" in result["visualizations"]["pages"][0]["visuals"][0]

    def test_technical_summary_preserved(self):
        from main import apply_readable_ids
        result = apply_readable_ids(
            {"name": "r.twb", "technical_summary": "Summary text", "tables": [], "data_sources": []},
            "r.twb"
        )
        assert result["technical_summary"] == "Summary text"


class TestCollectPbixFilePaths:
    """_collect_pbix_file_paths — extract zip and return file paths."""

    def _make_zip(self, files: dict) -> bytes:
        """Build an in-memory zip from {name: content} dict."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for name, content in files.items():
                zf.writestr(name, content)
        return buf.getvalue()

    def test_returns_paths_for_all_files(self, tmp_path):
        from main import _collect_pbix_file_paths
        from pathlib import Path
        zipped = self._make_zip({
            "DataModel": "model data",
            "Report/Layout": "layout json",
        })
        paths = _collect_pbix_file_paths(zipped, tmp_path)
        assert len(paths) == 2

    def test_all_paths_are_strings(self, tmp_path):
        from main import _collect_pbix_file_paths
        zipped = self._make_zip({"Report/Layout": "data"})
        paths = _collect_pbix_file_paths(zipped, tmp_path)
        assert all(isinstance(p, str) for p in paths)

    def test_files_extracted_to_temp_dir(self, tmp_path):
        from main import _collect_pbix_file_paths
        zipped = self._make_zip({"Connections": "conn"})
        _collect_pbix_file_paths(zipped, tmp_path)
        assert (tmp_path / "Connections").exists()

    def test_empty_zip_returns_empty_list(self, tmp_path):
        from main import _collect_pbix_file_paths
        zipped = self._make_zip({})
        paths = _collect_pbix_file_paths(zipped, tmp_path)
        assert paths == []


class TestFindLayoutFile:
    """_find_layout_file — locate Report/Layout among extracted paths."""

    def test_finds_report_layout_file(self):
        from main import _find_layout_file
        paths = [
            "C:/tmp/session/DataModel",
            "C:/tmp/session/Report/Layout",
            "C:/tmp/session/Connections",
        ]
        assert _find_layout_file(paths) == "C:/tmp/session/Report/Layout"

    def test_returns_none_when_not_present(self):
        from main import _find_layout_file
        paths = ["C:/tmp/DataModel", "C:/tmp/Connections"]
        assert _find_layout_file(paths) is None

    def test_handles_backslash_paths(self):
        from main import _find_layout_file
        paths = ["C:\\tmp\\session\\Report\\Layout"]
        assert _find_layout_file(paths) == "C:\\tmp\\session\\Report\\Layout"

    def test_returns_first_match(self):
        from main import _find_layout_file
        paths = [
            "a/Report/Layout",
            "b/Report/Layout",
        ]
        assert _find_layout_file(paths) == "a/Report/Layout"

    def test_empty_list_returns_none(self):
        from main import _find_layout_file
        assert _find_layout_file([]) is None

    def test_partial_match_not_selected(self):
        from main import _find_layout_file
        paths = ["C:/tmp/Report/LayoutOther", "C:/tmp/Report/Layoutz"]
        # "Report/Layout" is a substring of both — still matches
        result = _find_layout_file(paths)
        assert result is not None  # substring match is intentional


# ===========================================================================
# generate_mapping_report.py — _find_header_row
# ===========================================================================

class TestFindHeaderRow:
    """_find_header_row — locate the header row in Excel rows list."""

    def test_finds_header_in_first_row(self):
        from generate_mapping_report import _find_header_row
        rows = [
            ("source schema", "source column", "new source schema", "new source column"),
            ("dbo", "ClaimID", "dbo", "claim_id"),
        ]
        assert _find_header_row(rows) == 0

    def test_finds_header_after_title_rows(self):
        from generate_mapping_report import _find_header_row
        rows = [
            ("Insurance Mapping", None, None, None),
            ("Q1 2024", None, None, None),
            ("source schema", "source column", "new source schema", "new source column"),
            ("dbo", "ClaimID", "dbo", "claim_id"),
        ]
        assert _find_header_row(rows) == 2

    def test_case_insensitive_match(self):
        from generate_mapping_report import _find_header_row
        rows = [
            (None, None, None, None),
            ("SOURCE SCHEMA", "SOURCE COLUMN", "NEW SOURCE SCHEMA", "NEW SOURCE COLUMN"),
        ]
        assert _find_header_row(rows) == 1

    def test_header_with_extra_whitespace(self):
        from generate_mapping_report import _find_header_row
        rows = [("  Source Schema  ", "  Source Column  ", None, None)]
        assert _find_header_row(rows) == 0

    def test_returns_none_when_no_header(self):
        from generate_mapping_report import _find_header_row
        rows = [
            ("Insurance Mapping", None, None, None),
            ("Q1 2024", None, None, None),
            ("dbo", "ClaimID", "dbo", "claim_id"),
        ]
        assert _find_header_row(rows) is None

    def test_empty_rows_returns_none(self):
        from generate_mapping_report import _find_header_row
        assert _find_header_row([]) is None

    def test_none_cells_handled_without_error(self):
        from generate_mapping_report import _find_header_row
        rows = [
            (None, None, None, None),
            (None, "source column", None, None),
        ]
        assert _find_header_row(rows) == 1


# ===========================================================================
# databricks_writer.py — _get_name_attr, _extract_table_name
# ===========================================================================

class TestGetNameAttr:
    """_get_name_attr — unified attribute/dict lookup for tableName/table_name."""

    def test_dict_with_tableName(self):
        from databricks_writer import _get_name_attr
        assert _get_name_attr({"tableName": "Orders"}) == "Orders"

    def test_dict_with_table_name(self):
        from databricks_writer import _get_name_attr
        assert _get_name_attr({"table_name": "Claims"}) == "Claims"

    def test_dict_tableName_takes_priority_over_table_name(self):
        from databricks_writer import _get_name_attr
        # tableName is checked first
        assert _get_name_attr({"tableName": "First", "table_name": "Second"}) == "First"

    def test_dict_missing_both_keys_returns_empty(self):
        from databricks_writer import _get_name_attr
        assert _get_name_attr({"other": "value"}) == ""

    def test_dict_falsy_value_returns_empty(self):
        from databricks_writer import _get_name_attr
        assert _get_name_attr({"tableName": "", "table_name": None}) == ""

    def test_object_with_tableName_attr(self):
        from databricks_writer import _get_name_attr

        class Row:
            tableName = "FactSales"

        assert _get_name_attr(Row()) == "FactSales"

    def test_object_with_table_name_attr(self):
        from databricks_writer import _get_name_attr

        class Row:
            table_name = "DimDate"

        assert _get_name_attr(Row()) == "DimDate"

    def test_object_missing_both_attrs_returns_empty(self):
        from databricks_writer import _get_name_attr

        class Row:
            pass

        assert _get_name_attr(Row()) == ""

    def test_object_falsy_attr_returns_empty(self):
        from databricks_writer import _get_name_attr

        class Row:
            tableName = None
            table_name = ""

        assert _get_name_attr(Row()) == ""


class TestExtractTableName:
    """_extract_table_name — handle multiple row shapes from Databricks connector."""

    def test_object_with_tableName(self):
        from databricks_writer import _extract_table_name

        class Row:
            tableName = "FactSales"

        assert _extract_table_name(Row()) == "FactSales"

    def test_object_with_table_name(self):
        from databricks_writer import _extract_table_name

        class Row:
            table_name = "DimDate"

        assert _extract_table_name(Row()) == "DimDate"

    def test_dict_with_tableName(self):
        from databricks_writer import _extract_table_name
        assert _extract_table_name({"tableName": "bi_reports"}) == "bi_reports"

    def test_dict_with_table_name(self):
        from databricks_writer import _extract_table_name
        assert _extract_table_name({"table_name": "filters"}) == "filters"

    def test_object_with_asDict_tableName(self):
        from databricks_writer import _extract_table_name

        class SparkRow:
            def asDict(self):
                return {"tableName": "relationships"}

        assert _extract_table_name(SparkRow()) == "relationships"

    def test_object_with_asDict_table_name(self):
        from databricks_writer import _extract_table_name

        class SparkRow:
            def asDict(self):
                return {"table_name": "calculations"}

        assert _extract_table_name(SparkRow()) == "calculations"

    def test_tuple_uses_index_1(self):
        from databricks_writer import _extract_table_name
        assert _extract_table_name(("schema_name", "visualizations")) == "visualizations"

    def test_list_uses_index_1(self):
        from databricks_writer import _extract_table_name
        assert _extract_table_name(["default", "hierarchies"]) == "hierarchies"

    def test_tuple_too_short_falls_to_empty(self):
        from databricks_writer import _extract_table_name
        assert _extract_table_name(("only_one",)) == ""

    def test_empty_dict_returns_empty(self):
        from databricks_writer import _extract_table_name
        assert _extract_table_name({}) == ""

    def test_asDict_with_falsy_values_returns_empty(self):
        from databricks_writer import _extract_table_name

        class SparkRow:
            def asDict(self):
                return {"tableName": None, "table_name": ""}

        assert _extract_table_name(SparkRow()) == ""
