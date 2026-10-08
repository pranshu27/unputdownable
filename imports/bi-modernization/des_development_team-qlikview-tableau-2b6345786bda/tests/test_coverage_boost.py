"""
Coverage boost tests for databricks_normalizer.py, postgres_dedup.py, postgres_writer.py.
Targets uncovered paths to push each file above 80% coverage.

Run with:
    python -m coverage run -m pytest tests/ -v --tb=short
    python -m coverage report --include="databricks_normalizer.py,postgres_dedup.py,postgres_writer.py"
"""
import uuid
import json
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime, timezone


# ===========================================================================
# SECTION 1 — databricks_normalizer.py
# ===========================================================================

# ---------------------------------------------------------------------------
# Shared realistic fixtures
# ---------------------------------------------------------------------------

TABLEAU_FULL = {
    "technical_summary": "Tableau workbook with sales data",
    "Data Sources": [
        {
            "name": "Sales DB",
            "type": "SQL Server",
            "connection_details": "sqlserver://prod-db.corp.com",
            "is_extract": True,
            "extract_refresh_schedule": "Daily 2am",
            "authentication_method": "Windows",
            "refresh_schedule": "Daily",
            "is_published": True,
            "used_by": ["Sheet 1", "Dashboard 1"],
        }
    ],
    "Data Model": [
        {
            "table_name": "FactSales",
            "fields": [
                {"name": "SaleID", "type": "integer"},
                {"name": "Amount", "type": "decimal"},
                {"name": "Region", "type": "string"},
            ],
            "relationships": ["FactSales JOIN DimDate ON FactSales.DateKey = DimDate.DateKey"],
            "used_by": ["Sheet 1"],
        },
        {
            "table_name": "DimDate",
            "fields": [
                {"name": "DateKey", "type": "integer"},
                {"name": "Year", "type": "integer"},
            ],
            "relationships": [],
        },
    ],
    "Data Transformations": [
        {
            "name": "CalcProfit",
            "expression": "SUM([Amount]) - SUM([Cost])",
            "description": "Profit calculation",
            "data_type": "decimal",
            "role": "measure",
            "used_in": ["Sheet 1"],
            "filters": ["Region = 'US'"],
        }
    ],
    "Dashboards": [
        {
            "name": "Sales Overview",
            "object_id": "dash-001",
            "width": 1200,
            "height": 800,
            "background_color": "#FFFFFF",
            "components": [
                {
                    "name": "Sales Chart",
                    "object_id": "comp-001",
                    "position": {"x": 10, "y": 10, "width": 400, "height": 300},
                    "font_size": 12,
                    "color": "#000000",
                }
            ],
        }
    ],
    "Visualizations": [
        {
            "name": "Sales by Region",
            "object_id": "viz-001",
            "type": "bar_chart",
            "formatting": {"font": "Arial", "size": 12},
            "chart_mappings": {
                "x_axis": "Region",
                "y_axis": "SUM(Amount)",
                "secondary_y_axis": "",
                "color": "Category",
                "text": "",
                "size": "",
                "legend": "Category",
                "details": "",
            },
            "straight_table_columns": [
                {"name": "Region", "expression": "ATTR([Region])"},
                {"name": "Total Sales", "expression": "SUM([Amount])"},
            ],
            "dimensions": ["Region", "Category"],
            "measures": ["SUM(Amount)", "SUM(Profit)"],
            "filters": ["Year = 2024"],
        }
    ],
    "Filters": [
        {
            "name": "Region Filter",
            "object_id": "flt-001",
            "type": "global",
            "columns": ["Region"],
            "formatting": {"style": "dropdown"},
            "background_color": "#EEEEEE",
        }
    ],
    "Parameters or Variables": [
        {
            "name": "TopN",
            "type": "integer",
            "default": "10",
            "calculation": "10",
        }
    ],
    "Hierarchies": [
        {
            "name": "Date Hierarchy",
            "members": ["Year", "Quarter", "Month", "Day"],
        }
    ],
}

QLIKVIEW_FULL = {
    "executivesummary": "QlikView insurance dashboard",
    "Data Sources": [
        {
            "name": "Claims DB",
            "type": "ODBC",
            "connection_details": "DSN=ClaimsDB",
            "is_extract": False,
            "authentication_method": "SQL",
            "refresh_schedule": "Weekly",
            "is_published": False,
            "used_by": ["Sheet1"],
        }
    ],
    "Data Model": [
        {
            "table_name": "Claims",
            "fields": [
                {"name": "ClaimID", "type": "integer"},
                {"name": "PolicyNumber", "type": "string"},
                {"name": "ClaimAmount", "type": "decimal"},
            ],
            "relationships": ["Claims JOIN Policy ON Claims.PolicyNumber = Policy.PolicyNumber"],
        }
    ],
    "Data Transformations": [
        {
            "name": "TotalClaims",
            "expression": "Sum(ClaimAmount)",
            "description": "Total claims amount",
            "data_type": "decimal",
            "role": "measure",
            "used_in": ["Sheet1"],
            "filters": [],
        }
    ],
    "Dashboards": [
        {
            "name": "Claims Dashboard",
            "object_id": "dash-q1",
            "width": 1024,
            "height": 768,
            "background_color": "#F0F0F0",
            "components": [
                {
                    "name": "Claims Chart",
                    "object_id": "comp-q1",
                    "position": {"x": 0, "y": 0, "width": 500, "height": 400},
                    "font_size": 10,
                    "color": "#333333",
                }
            ],
        }
    ],
    "Visualizations": [
        {
            "name": "Claims by Policy",
            "object_id": "viz-q1",
            "type": "pie_chart",
            "formatting": {"colors": ["red", "blue"]},
            "chart_mappings": {
                "x_axis": "PolicyNumber",
                "y_axis": "Sum(ClaimAmount)",
                "secondary_y_axis": "",
                "color": "",
                "text": "ClaimID",
                "size": "",
                "legend": "",
                "details": "",
            },
            "straight_table_columns": [
                {"name": "PolicyNumber", "expression": "PolicyNumber"},
            ],
            "dimensions": ["PolicyNumber"],
            "measures": ["Sum(ClaimAmount)"],
            "filters": ["ClaimAmount > 0"],
        }
    ],
    "Filters": [
        {
            "name": "Year Filter",
            "object_id": "flt-q1",
            "type": "sheet",
            "columns": ["Year"],
            "formatting": {},
            "background_color": "",
        }
    ],
    "Parameters or Variables": [
        {
            "name": "vMaxClaims",
            "type": "string",
            "calculation": "=Max(ClaimAmount)",
        }
    ],
    "Sheets": [
        {"name": "Sheet1", "object_id": "sh-001"},
        {"name": "Sheet2", "object_id": "sh-002"},
    ],
    "Hierarchies": [
        {
            "name": "Policy Hierarchy",
            "members": ["PolicyType", "PolicyNumber"],
        }
    ],
}

POWERBI_FULL = {
    "agent_result": {
        "executive_summary": "Power BI sales report",
        "data_sources": [
            {
                "name": "Azure SQL",
                "source_type": "AzureSQL",
                "server": "myserver.database.windows.net",
                "database": "SalesDB",
                "schema": "dbo",
                "path": "",
                "connection_mode": "DirectQuery",
                "authentication_method": "OAuth2",
                "gateway": "corp-gateway",
                "refresh_frequency": "Hourly",
            }
        ],
        "tables": [
            {
                "name": "Sales",
                "source_data_source_id": "src-001",
                "is_materialized": True,
                "row_count_estimate": 500000,
                "columns": [
                    {
                        "name": "SaleID",
                        "data_type": "Int64",
                        "nullable": False,
                        "hidden": False,
                        "used_in_relationships": True,
                        "used_in_filters": False,
                        "used_in_groupby": False,
                        "used_in_calculations": False,
                        "used_in_rls": False,
                        "distinct_count_high": True,
                        "description": "Primary key",
                    },
                    {
                        "name": "Amount",
                        "data_type": "Decimal",
                        "nullable": True,
                        "hidden": False,
                        "used_in_calculations": True,
                        "description": "Sale amount",
                    },
                ],
                "ingestion": {
                    "steps": [
                        {
                            "order": 1,
                            "step_type": "Source",
                            "description": "Connect to Azure SQL",
                            "native_expressions": {"powerquery": "Sql.Database(...)"},
                        },
                        {
                            "order": 2,
                            "step_type": "Filter",
                            "description": "Remove nulls",
                            "native_expressions": {"powerquery": "Table.SelectRows(...)"},
                        },
                    ]
                },
            }
        ],
        "relationships": [
            {
                "left_table_id": "Sales",
                "left_column": "DateKey",
                "right_table_id": "Date",
                "right_column": "DateKey",
                "cardinality": "many-to-one",
                "join_type": "inner",
                "active": True,
                "filter_direction": "bidirectional",
                "enforced_integrity": False,
            }
        ],
        "calculations": [
            {
                "name": "Total Sales",
                "expressions": {"dax": "SUM(Sales[Amount])"},
                "semantic_type": "SUM",
                "depends_on_columns": ["Sales[Amount]"],
                "reusable": True,
            }
        ],
        "report_pages": [
            {
                "page_name": "Overview",
                "visuals": [
                    {
                        "visual_name": "Sales Chart",
                        "visual_type": "barChart",
                        "tables_used": ["Sales", "Date"],
                        "columns_used": [
                            "Sales[Amount]",
                            {"table": "Date", "column": "Year"},
                        ],
                        "measures_used": ["Total Sales", "YTD Sales"],
                    },
                    {
                        "visual_name": "KPI Card",
                        "visual_type": "card",
                        "tables_used": [],
                        "columns_used": [],
                        "measures_used": ["Total Sales"],
                    },
                ],
            }
        ],
        "filters": [
            {
                "column": "Year",
                "table": "Date",
                "scope": "report",
                "condition": "Year >= 2020",
                "hardcoded": False,
            }
        ],
        "rls_policies": [
            {
                "role_name": "RegionManager",
                "table": "Sales",
                "rule_expression": "[Region] = USERNAME()",
            }
        ],
    }
}


# ===========================================================================
# 1a. normalize_tableau — full realistic data
# ===========================================================================

class TestNormalizeTableauFull:
    """Exercise every loop in normalize_tableau with realistic data."""

    def test_tableau_bi_report_row(self):
        from databricks_normalizer import normalize_tableau
        result = normalize_tableau(TABLEAU_FULL, "sales.twb")
        assert len(result["bi_reports"]) == 1
        rpt = result["bi_reports"][0]
        assert rpt["tool_type"] == "tableau"
        assert rpt["file_name"] == "sales.twb"
        assert rpt["executive_summary"] == "Tableau workbook with sales data"

    def test_tableau_data_sources_populated(self):
        from databricks_normalizer import normalize_tableau
        result = normalize_tableau(TABLEAU_FULL, "sales.twb")
        assert len(result["data_sources"]) == 1
        src = result["data_sources"][0]
        assert src["name"] == "Sales DB"
        assert src["source_type"] == "SQL Server"
        assert src["is_extract"] is True
        assert src["connection_mode"] == "extract"
        assert src["is_published"] is True
        assert isinstance(src["fingerprint"], str) and len(src["fingerprint"]) == 16

    def test_tableau_tables_model_and_columns(self):
        from databricks_normalizer import normalize_tableau
        result = normalize_tableau(TABLEAU_FULL, "sales.twb")
        assert len(result["tables_model"]) == 2
        table_names = [t["table_name"] for t in result["tables_model"]]
        assert "FactSales" in table_names
        assert "DimDate" in table_names
        # FactSales has 3 columns, DimDate has 2
        assert len(result["columns_metadata"]) == 5

    def test_tableau_relationships_from_data_model(self):
        from databricks_normalizer import normalize_tableau
        result = normalize_tableau(TABLEAU_FULL, "sales.twb")
        # FactSales has 1 relationship string
        assert len(result["relationships"]) == 1
        rel = result["relationships"][0]
        assert rel["left_table"] == "FactSales"
        assert rel["is_active"] is True

    def test_tableau_transformations(self):
        from databricks_normalizer import normalize_tableau
        result = normalize_tableau(TABLEAU_FULL, "sales.twb")
        assert len(result["transformations"]) == 1
        tr = result["transformations"][0]
        assert tr["name"] == "CalcProfit"
        assert tr["step_type"] == "custom"
        assert "SUM" in tr["expression"]

    def test_tableau_dashboards_and_components(self):
        from databricks_normalizer import normalize_tableau
        result = normalize_tableau(TABLEAU_FULL, "sales.twb")
        assert len(result["dashboards"]) == 1
        dash = result["dashboards"][0]
        assert dash["name"] == "Sales Overview"
        assert dash["width"] == 1200
        assert len(result["dashboard_components"]) == 1
        comp = result["dashboard_components"][0]
        assert comp["name"] == "Sales Chart"
        assert comp["position_x"] == 10

    def test_tableau_visualizations_with_chart_mappings(self):
        from databricks_normalizer import normalize_tableau
        result = normalize_tableau(TABLEAU_FULL, "sales.twb")
        assert len(result["visualizations"]) == 1
        viz = result["visualizations"][0]
        assert viz["name"] == "Sales by Region"
        assert viz["visual_type"] == "bar_chart"
        # chart_mappings
        assert len(result["viz_chart_mappings"]) == 1
        cm = result["viz_chart_mappings"][0]
        assert cm["x_axis"] == "Region"
        assert cm["y_axis"] == "SUM(Amount)"
        assert cm["legend"] == "Category"

    def test_tableau_straight_table_columns(self):
        from databricks_normalizer import normalize_tableau
        result = normalize_tableau(TABLEAU_FULL, "sales.twb")
        assert len(result["viz_table_columns"]) == 2
        names = [c["name"] for c in result["viz_table_columns"]]
        assert "Region" in names
        assert "Total Sales" in names

    def test_tableau_viz_data_bindings_dimensions_measures_filters(self):
        from databricks_normalizer import normalize_tableau
        result = normalize_tableau(TABLEAU_FULL, "sales.twb")
        bindings = result["viz_data_bindings"]
        types = [b["binding_type"] for b in bindings]
        assert "dimension" in types
        assert "measure" in types
        assert "filter" in types
        # 2 dimensions + 2 measures + 1 filter = 5
        assert len(bindings) == 5

    def test_tableau_filters(self):
        from databricks_normalizer import normalize_tableau
        result = normalize_tableau(TABLEAU_FULL, "sales.twb")
        assert len(result["filters"]) == 1
        f = result["filters"][0]
        assert f["name"] == "Region Filter"
        assert f["scope"] == "global"

    def test_tableau_parameters_variables(self):
        from databricks_normalizer import normalize_tableau
        result = normalize_tableau(TABLEAU_FULL, "sales.twb")
        assert len(result["parameters_variables"]) == 1
        p = result["parameters_variables"][0]
        assert p["name"] == "TopN"
        assert p["param_type"] == "integer"

    def test_tableau_hierarchies(self):
        from databricks_normalizer import normalize_tableau
        result = normalize_tableau(TABLEAU_FULL, "sales.twb")
        assert len(result["hierarchies"]) == 1
        h = result["hierarchies"][0]
        assert h["name"] == "Date Hierarchy"
        members = json.loads(h["members"])
        assert "Year" in members


# ===========================================================================
# 1b. normalize_qlikview — full realistic data
# ===========================================================================

class TestNormalizeQlikviewFull:
    """Exercise every loop in normalize_qlikview with realistic data."""

    def test_qlikview_bi_report_row(self):
        from databricks_normalizer import normalize_qlikview
        result = normalize_qlikview(QLIKVIEW_FULL, "claims.qvw")
        assert len(result["bi_reports"]) == 1
        rpt = result["bi_reports"][0]
        assert rpt["tool_type"] == "qlikview"
        assert rpt["executive_summary"] == "QlikView insurance dashboard"

    def test_qlikview_data_sources(self):
        from databricks_normalizer import normalize_qlikview
        result = normalize_qlikview(QLIKVIEW_FULL, "claims.qvw")
        assert len(result["data_sources"]) == 1
        src = result["data_sources"][0]
        assert src["source_type"] == "ODBC"
        assert src["connection_mode"] == "import"  # is_extract=False

    def test_qlikview_tables_and_columns(self):
        from databricks_normalizer import normalize_qlikview
        result = normalize_qlikview(QLIKVIEW_FULL, "claims.qvw")
        assert len(result["tables_model"]) == 1
        assert result["tables_model"][0]["table_name"] == "Claims"
        assert len(result["columns_metadata"]) == 3

    def test_qlikview_relationships(self):
        from databricks_normalizer import normalize_qlikview
        result = normalize_qlikview(QLIKVIEW_FULL, "claims.qvw")
        assert len(result["relationships"]) == 1
        assert result["relationships"][0]["left_table"] == "Claims"

    def test_qlikview_transformations(self):
        from databricks_normalizer import normalize_qlikview
        result = normalize_qlikview(QLIKVIEW_FULL, "claims.qvw")
        assert len(result["transformations"]) == 1
        assert result["transformations"][0]["name"] == "TotalClaims"

    def test_qlikview_dashboards_and_components(self):
        from databricks_normalizer import normalize_qlikview
        result = normalize_qlikview(QLIKVIEW_FULL, "claims.qvw")
        # 1 dashboard + 2 sheets stored as dashboards = 3
        assert len(result["dashboards"]) == 3
        dash_names = [d["name"] for d in result["dashboards"]]
        assert "Claims Dashboard" in dash_names
        assert "Sheet1" in dash_names
        assert "Sheet2" in dash_names
        assert len(result["dashboard_components"]) == 1

    def test_qlikview_visualizations_with_chart_mappings(self):
        from databricks_normalizer import normalize_qlikview
        result = normalize_qlikview(QLIKVIEW_FULL, "claims.qvw")
        assert len(result["visualizations"]) == 1
        assert len(result["viz_chart_mappings"]) == 1
        cm = result["viz_chart_mappings"][0]
        assert cm["x_axis"] == "PolicyNumber"
        assert cm["text"] == "ClaimID"

    def test_qlikview_straight_table_columns(self):
        from databricks_normalizer import normalize_qlikview
        result = normalize_qlikview(QLIKVIEW_FULL, "claims.qvw")
        assert len(result["viz_table_columns"]) == 1
        assert result["viz_table_columns"][0]["name"] == "PolicyNumber"

    def test_qlikview_viz_data_bindings(self):
        from databricks_normalizer import normalize_qlikview
        result = normalize_qlikview(QLIKVIEW_FULL, "claims.qvw")
        bindings = result["viz_data_bindings"]
        types = {b["binding_type"] for b in bindings}
        assert "dimension" in types
        assert "measure" in types
        assert "filter" in types

    def test_qlikview_filters(self):
        from databricks_normalizer import normalize_qlikview
        result = normalize_qlikview(QLIKVIEW_FULL, "claims.qvw")
        assert len(result["filters"]) == 1
        assert result["filters"][0]["name"] == "Year Filter"

    def test_qlikview_parameters_variables(self):
        from databricks_normalizer import normalize_qlikview
        result = normalize_qlikview(QLIKVIEW_FULL, "claims.qvw")
        assert len(result["parameters_variables"]) == 1
        p = result["parameters_variables"][0]
        assert p["name"] == "vMaxClaims"
        assert "Max" in p["expression"]

    def test_qlikview_hierarchies(self):
        from databricks_normalizer import normalize_qlikview
        result = normalize_qlikview(QLIKVIEW_FULL, "claims.qvw")
        assert len(result["hierarchies"]) == 1
        assert result["hierarchies"][0]["name"] == "Policy Hierarchy"


# ===========================================================================
# 1c. normalize_powerbi — full realistic data
# ===========================================================================

class TestNormalizePowerBIFull:
    """Exercise every loop in normalize_powerbi with realistic data."""

    def test_powerbi_bi_report_row(self):
        from databricks_normalizer import normalize_powerbi
        result = normalize_powerbi(POWERBI_FULL, "sales.pbix")
        assert len(result["bi_reports"]) == 1
        rpt = result["bi_reports"][0]
        assert rpt["tool_type"] == "powerbi"
        assert rpt["executive_summary"] == "Power BI sales report"

    def test_powerbi_data_sources(self):
        from databricks_normalizer import normalize_powerbi
        result = normalize_powerbi(POWERBI_FULL, "sales.pbix")
        assert len(result["data_sources"]) == 1
        src = result["data_sources"][0]
        assert src["source_type"] == "AzureSQL"
        assert src["server"] == "myserver.database.windows.net"
        assert src["connection_mode"] == "DirectQuery"
        assert src["gateway"] == "corp-gateway"

    def test_powerbi_tables_and_columns(self):
        from databricks_normalizer import normalize_powerbi
        result = normalize_powerbi(POWERBI_FULL, "sales.pbix")
        assert len(result["tables_model"]) == 1
        tbl = result["tables_model"][0]
        assert tbl["table_name"] == "Sales"
        assert tbl["is_materialized"] is True
        assert tbl["row_count_estimate"] == 500000
        assert len(result["columns_metadata"]) == 2

    def test_powerbi_ingestion_steps_become_transformations(self):
        from databricks_normalizer import normalize_powerbi
        result = normalize_powerbi(POWERBI_FULL, "sales.pbix")
        assert len(result["transformations"]) == 2
        names = [t["name"] for t in result["transformations"]]
        assert any("step 1" in n for n in names)
        assert any("step 2" in n for n in names)
        assert result["transformations"][0]["step_type"] == "Source"

    def test_powerbi_relationships(self):
        from databricks_normalizer import normalize_powerbi
        result = normalize_powerbi(POWERBI_FULL, "sales.pbix")
        assert len(result["relationships"]) == 1
        rel = result["relationships"][0]
        assert rel["left_table"] == "Sales"
        assert rel["right_table"] == "Date"
        assert rel["bidirectional_filter"] is True
        assert rel["is_active"] is True

    def test_powerbi_calculations(self):
        from databricks_normalizer import normalize_powerbi
        result = normalize_powerbi(POWERBI_FULL, "sales.pbix")
        assert len(result["calculations"]) == 1
        calc = result["calculations"][0]
        assert calc["name"] == "Total Sales"
        assert "SUM" in calc["expression"]
        assert calc["reusable_metric"] is True

    def test_powerbi_pages_become_dashboards(self):
        from databricks_normalizer import normalize_powerbi
        result = normalize_powerbi(POWERBI_FULL, "sales.pbix")
        assert len(result["dashboards"]) == 1
        assert result["dashboards"][0]["name"] == "Overview"

    def test_powerbi_visuals_become_visualizations(self):
        from databricks_normalizer import normalize_powerbi
        result = normalize_powerbi(POWERBI_FULL, "sales.pbix")
        assert len(result["visualizations"]) == 2
        viz_names = [v["name"] for v in result["visualizations"]]
        assert "Sales Chart" in viz_names
        assert "KPI Card" in viz_names

    def test_powerbi_tables_used_become_bindings(self):
        from databricks_normalizer import normalize_powerbi
        result = normalize_powerbi(POWERBI_FULL, "sales.pbix")
        bindings = result["viz_data_bindings"]
        table_bindings = [b for b in bindings if b["binding_type"] == "table_used"]
        # Sales Chart has 2 tables_used
        assert len(table_bindings) == 2
        field_names = [b["field_name"] for b in table_bindings]
        assert "Sales" in field_names
        assert "Date" in field_names

    def test_powerbi_columns_used_string_and_dict(self):
        from databricks_normalizer import normalize_powerbi
        result = normalize_powerbi(POWERBI_FULL, "sales.pbix")
        bindings = result["viz_data_bindings"]
        col_bindings = [b for b in bindings if b["binding_type"] == "column_used"]
        # Sales Chart: 1 string col + 1 dict col = 2
        assert len(col_bindings) == 2
        field_names = [b["field_name"] for b in col_bindings]
        # String col stays as-is
        assert "Sales[Amount]" in field_names
        # Dict col becomes "table.column"
        assert "Date.Year" in field_names

    def test_powerbi_measures_used_become_bindings(self):
        from databricks_normalizer import normalize_powerbi
        result = normalize_powerbi(POWERBI_FULL, "sales.pbix")
        bindings = result["viz_data_bindings"]
        measure_bindings = [b for b in bindings if b["binding_type"] == "measure"]
        # Sales Chart: 2 measures, KPI Card: 1 measure = 3
        assert len(measure_bindings) == 3

    def test_powerbi_filters(self):
        from databricks_normalizer import normalize_powerbi
        result = normalize_powerbi(POWERBI_FULL, "sales.pbix")
        assert len(result["filters"]) == 1
        f = result["filters"][0]
        assert f["column_name"] == "Year"
        assert f["table_name"] == "Date"
        assert f["scope"] == "report"

    def test_powerbi_rls_policies(self):
        from databricks_normalizer import normalize_powerbi
        result = normalize_powerbi(POWERBI_FULL, "sales.pbix")
        assert len(result["rls_policies"]) == 1
        rls = result["rls_policies"][0]
        assert rls["role_name"] == "RegionManager"
        assert rls["table_name"] == "Sales"
        assert "USERNAME" in rls["rule_expression"]

    def test_powerbi_without_agent_result_wrapper(self):
        """normalize_powerbi should also accept flat dict (no agent_result key)."""
        from databricks_normalizer import normalize_powerbi
        flat = POWERBI_FULL["agent_result"].copy()
        result = normalize_powerbi(flat, "flat.pbix")
        assert result["bi_reports"][0]["tool_type"] == "powerbi"
        assert len(result["data_sources"]) == 1


# ===========================================================================
# 1d. Direct helper tests
# ===========================================================================

class TestNormalizePowerBIHelpers:
    """Test _normalize_powerbi_sources, _normalize_powerbi_tables, _normalize_powerbi_pages directly."""

    def _empty_result(self):
        from databricks_normalizer import _empty_result
        return _empty_result()

    def test_normalize_powerbi_sources_direct(self):
        from databricks_normalizer import _normalize_powerbi_sources
        result = self._empty_result()
        agent = POWERBI_FULL["agent_result"]
        _normalize_powerbi_sources(agent, "rpt-001", result)
        assert len(result["data_sources"]) == 1
        assert result["data_sources"][0]["report_id"] == "rpt-001"

    def test_normalize_powerbi_sources_empty(self):
        from databricks_normalizer import _normalize_powerbi_sources
        result = self._empty_result()
        _normalize_powerbi_sources({}, "rpt-002", result)
        assert len(result["data_sources"]) == 0

    def test_normalize_powerbi_tables_direct(self):
        from databricks_normalizer import _normalize_powerbi_tables
        result = self._empty_result()
        agent = POWERBI_FULL["agent_result"]
        _normalize_powerbi_tables(agent, "rpt-003", result)
        assert len(result["tables_model"]) == 1
        assert len(result["columns_metadata"]) == 2
        assert len(result["transformations"]) == 2

    def test_normalize_powerbi_tables_no_ingestion(self):
        from databricks_normalizer import _normalize_powerbi_tables
        result = self._empty_result()
        agent = {"tables": [{"name": "Simple", "columns": [{"name": "id", "data_type": "int"}]}]}
        _normalize_powerbi_tables(agent, "rpt-004", result)
        assert len(result["tables_model"]) == 1
        assert len(result["transformations"]) == 0

    def test_normalize_powerbi_pages_direct(self):
        from databricks_normalizer import _normalize_powerbi_pages
        result = self._empty_result()
        agent = POWERBI_FULL["agent_result"]
        _normalize_powerbi_pages(agent, "rpt-005", result)
        assert len(result["dashboards"]) == 1
        assert len(result["visualizations"]) == 2
        # bindings: 2 table + 2 col + 3 measure = 7
        assert len(result["viz_data_bindings"]) == 7

    def test_normalize_powerbi_pages_empty(self):
        from databricks_normalizer import _normalize_powerbi_pages
        result = self._empty_result()
        _normalize_powerbi_pages({}, "rpt-006", result)
        assert len(result["dashboards"]) == 0


class TestNormalizeVisualizations:
    """Test _normalize_visualizations directly with all branches."""

    def _empty_result(self):
        from databricks_normalizer import _empty_result
        return _empty_result()

    def test_viz_with_chart_mappings(self):
        from databricks_normalizer import _normalize_visualizations
        result = self._empty_result()
        viz_list = [
            {
                "name": "Bar Chart",
                "object_id": "v1",
                "type": "bar",
                "chart_mappings": {"x_axis": "Date", "y_axis": "Sales", "color": "Region",
                                   "secondary_y_axis": "", "text": "", "size": "", "legend": "", "details": ""},
                "straight_table_columns": [],
                "dimensions": ["Date"],
                "measures": ["Sales"],
                "filters": [],
            }
        ]
        _normalize_visualizations(viz_list, "rpt-v1", result)
        assert len(result["visualizations"]) == 1
        assert len(result["viz_chart_mappings"]) == 1
        assert result["viz_chart_mappings"][0]["x_axis"] == "Date"
        assert len(result["viz_data_bindings"]) == 2  # 1 dim + 1 measure

    def test_viz_with_straight_table_columns(self):
        from databricks_normalizer import _normalize_visualizations
        result = self._empty_result()
        viz_list = [
            {
                "name": "Table",
                "object_id": "v2",
                "type": "straight_table",
                "straight_table_columns": [
                    {"name": "Col1", "expression": "=Col1"},
                    {"name": "Col2", "expression": "=Col2"},
                ],
                "dimensions": [],
                "measures": [],
                "filters": [],
            }
        ]
        _normalize_visualizations(viz_list, "rpt-v2", result)
        assert len(result["viz_table_columns"]) == 2

    def test_viz_no_chart_mappings(self):
        from databricks_normalizer import _normalize_visualizations
        result = self._empty_result()
        viz_list = [{"name": "Text Box", "object_id": "v3", "type": "text"}]
        _normalize_visualizations(viz_list, "rpt-v3", result)
        assert len(result["visualizations"]) == 1
        assert len(result["viz_chart_mappings"]) == 0

    def test_viz_chart_mappings_not_dict(self):
        """chart_mappings that is not a dict should be skipped."""
        from databricks_normalizer import _normalize_visualizations
        result = self._empty_result()
        viz_list = [{"name": "Weird", "chart_mappings": "not-a-dict"}]
        _normalize_visualizations(viz_list, "rpt-v4", result)
        assert len(result["viz_chart_mappings"]) == 0

    def test_viz_with_filters_binding(self):
        from databricks_normalizer import _normalize_visualizations
        result = self._empty_result()
        viz_list = [
            {
                "name": "Filtered Chart",
                "filters": ["Year = 2024", "Region = US"],
                "dimensions": [],
                "measures": [],
            }
        ]
        _normalize_visualizations(viz_list, "rpt-v5", result)
        filter_bindings = [b for b in result["viz_data_bindings"] if b["binding_type"] == "filter"]
        assert len(filter_bindings) == 2

    def test_viz_empty_list(self):
        from databricks_normalizer import _normalize_visualizations
        result = self._empty_result()
        _normalize_visualizations([], "rpt-v6", result)
        assert len(result["visualizations"]) == 0


# ===========================================================================
# SECTION 2 — postgres_dedup.py (pure Python, no DB)
# ===========================================================================

class TestJaccard:
    """Test _jaccard similarity function."""

    def test_both_empty_returns_one(self):
        from postgres_dedup import _jaccard
        assert _jaccard(set(), set()) == 1.0

    def test_identical_sets(self):
        from postgres_dedup import _jaccard
        s = {"a", "b", "c"}
        assert _jaccard(s, s) == 1.0

    def test_identical_sets_copy(self):
        from postgres_dedup import _jaccard
        a = {"x", "y", "z"}
        b = {"x", "y", "z"}
        assert _jaccard(a, b) == 1.0

    def test_no_overlap(self):
        from postgres_dedup import _jaccard
        a = {"a", "b"}
        b = {"c", "d"}
        assert _jaccard(a, b) == 0.0

    def test_partial_overlap_half(self):
        from postgres_dedup import _jaccard
        a = {"a", "b", "c"}
        b = {"b", "c", "d"}
        # intersection=2, union=4 → 0.5
        result = _jaccard(a, b)
        assert abs(result - 0.5) < 1e-9

    def test_partial_overlap_one_third(self):
        from postgres_dedup import _jaccard
        a = {"a", "b", "c"}
        b = {"c", "d", "e"}
        # intersection=1, union=5 → 0.2
        result = _jaccard(a, b)
        assert abs(result - 0.2) < 1e-9

    def test_one_empty_one_not(self):
        from postgres_dedup import _jaccard
        a = {"a", "b"}
        b = set()
        # intersection=0, union=2 → 0.0
        assert _jaccard(a, b) == 0.0

    def test_single_element_match(self):
        from postgres_dedup import _jaccard
        assert _jaccard({"x"}, {"x"}) == 1.0

    def test_single_element_no_match(self):
        from postgres_dedup import _jaccard
        assert _jaccard({"x"}, {"y"}) == 0.0


class TestNormalizeCol:
    """Test _normalize_col string normalization."""

    def test_lowercase(self):
        from postgres_dedup import _normalize_col
        assert _normalize_col("MyColumn") == "mycolumn"

    def test_strips_spaces(self):
        from postgres_dedup import _normalize_col
        assert _normalize_col("  my col  ") == "mycol"

    def test_removes_underscores(self):
        from postgres_dedup import _normalize_col
        assert _normalize_col("my_column_name") == "mycolumnname"

    def test_removes_hyphens(self):
        from postgres_dedup import _normalize_col
        assert _normalize_col("my-column-name") == "mycolumnname"

    def test_mixed_case_underscores_hyphens(self):
        from postgres_dedup import _normalize_col
        assert _normalize_col("My_Column-Name") == "mycolumnname"

    def test_multiple_consecutive_separators(self):
        from postgres_dedup import _normalize_col
        assert _normalize_col("col__name--here") == "colnamehere"

    def test_already_normalized(self):
        from postgres_dedup import _normalize_col
        assert _normalize_col("mycolumn") == "mycolumn"

    def test_empty_string(self):
        from postgres_dedup import _normalize_col
        assert _normalize_col("") == ""

    def test_all_separators(self):
        from postgres_dedup import _normalize_col
        assert _normalize_col("_ - _") == ""


class TestLevel2FuzzyDuplicates:
    """Test _level2_fuzzy_duplicates with in-memory table dicts."""

    def _make_table(self, table_id, table_name, tool_type, file_name, column_names, column_signature=""):
        return {
            "table_id": table_id,
            "table_name": table_name,
            "report_id": f"rpt-{table_id}",
            "column_signature": column_signature,
            "tool_type": tool_type,
            "file_name": file_name,
            "column_names": column_names,
        }

    def test_identical_name_and_columns_detected(self):
        from postgres_dedup import _level2_fuzzy_duplicates
        tables = [
            self._make_table("t1", "FactSales", "tableau", "a.twb",
                             ["saleid", "amount", "region", "date", "category"]),
            self._make_table("t2", "FactSales", "powerbi", "b.pbix",
                             ["saleid", "amount", "region", "date", "category"]),
        ]
        result = _level2_fuzzy_duplicates(tables, set())
        assert len(result) == 1
        dup = result[0]
        assert dup["table_a_id"] == "t1"
        assert dup["table_b_id"] == "t2"
        assert dup["combined_score"] >= 0.65
        assert dup["match_reason"] == "name+columns"

    def test_same_name_high_column_overlap(self):
        from postgres_dedup import _level2_fuzzy_duplicates
        tables = [
            self._make_table("t3", "DimDate", "tableau", "a.twb",
                             ["datekey", "year", "month", "day", "quarter"]),
            self._make_table("t4", "DimDate", "qlikview", "c.qvw",
                             ["datekey", "year", "month", "day", "weeknum"]),
        ]
        result = _level2_fuzzy_duplicates(tables, set())
        assert len(result) == 1
        assert result[0]["match_reason"] == "name+columns"

    def test_no_overlap_no_duplicate(self):
        from postgres_dedup import _level2_fuzzy_duplicates
        tables = [
            self._make_table("t5", "FactSales", "tableau", "a.twb",
                             ["saleid", "amount", "region"]),
            self._make_table("t6", "DimProduct", "powerbi", "b.pbix",
                             ["productid", "productname", "category", "price", "sku"]),
        ]
        result = _level2_fuzzy_duplicates(tables, set())
        assert len(result) == 0

    def test_skip_exact_signature_duplicates(self):
        from postgres_dedup import _level2_fuzzy_duplicates
        sig = "abc123"
        tables = [
            self._make_table("t7", "FactSales", "tableau", "a.twb",
                             ["saleid", "amount", "region"], column_signature=sig),
            self._make_table("t8", "FactSales", "powerbi", "b.pbix",
                             ["saleid", "amount", "region"], column_signature=sig),
        ]
        # Both have same sig and it's in exact_signatures → should be skipped
        result = _level2_fuzzy_duplicates(tables, {sig})
        assert len(result) == 0

    def test_empty_column_set_skipped(self):
        from postgres_dedup import _level2_fuzzy_duplicates
        tables = [
            self._make_table("t9", "EmptyTable", "tableau", "a.twb", []),
            self._make_table("t10", "EmptyTable", "powerbi", "b.pbix", []),
        ]
        result = _level2_fuzzy_duplicates(tables, set())
        assert len(result) == 0

    def test_columns_only_match_high_jaccard(self):
        from postgres_dedup import _level2_fuzzy_duplicates
        # Different names but very high column overlap (>= 0.85)
        cols = ["col1", "col2", "col3", "col4", "col5", "col6", "col7", "col8", "col9", "col10"]
        tables = [
            self._make_table("t11", "TableAlpha", "tableau", "a.twb", cols),
            self._make_table("t12", "TableBeta", "powerbi", "b.pbix",
                             cols[:9] + ["col11"]),  # 9/11 overlap ≈ 0.818 < 0.85
        ]
        result = _level2_fuzzy_duplicates(tables, set())
        # 9/11 ≈ 0.818 < 0.85 threshold for columns_only, name_sim=0 → combined < 0.65
        assert len(result) == 0

    def test_columns_only_match_very_high_jaccard(self):
        from postgres_dedup import _level2_fuzzy_duplicates
        # 9 shared out of 10 total = 0.9 jaccard → columns_only match
        shared = ["col1", "col2", "col3", "col4", "col5", "col6", "col7", "col8", "col9"]
        tables = [
            self._make_table("t13", "TableAlpha", "tableau", "a.twb", shared),
            self._make_table("t14", "TableBeta", "powerbi", "b.pbix", shared),
        ]
        # jaccard = 1.0 (identical), name_sim = 0 → combined = 0.6 < 0.65
        # but col_jaccard = 1.0 >= 0.85 → columns_only
        result = _level2_fuzzy_duplicates(tables, set())
        assert len(result) == 1
        assert result[0]["match_reason"] == "columns_only"

    def test_single_table_no_pairs(self):
        from postgres_dedup import _level2_fuzzy_duplicates
        tables = [
            self._make_table("t15", "OnlyTable", "tableau", "a.twb", ["col1", "col2"]),
        ]
        result = _level2_fuzzy_duplicates(tables, set())
        assert len(result) == 0

    def test_empty_table_list(self):
        from postgres_dedup import _level2_fuzzy_duplicates
        result = _level2_fuzzy_duplicates([], set())
        assert result == []

    def test_result_fields_present(self):
        from postgres_dedup import _level2_fuzzy_duplicates
        tables = [
            self._make_table("ta", "SameTable", "tableau", "a.twb",
                             ["id", "name", "value", "date", "status"]),
            self._make_table("tb", "SameTable", "powerbi", "b.pbix",
                             ["id", "name", "value", "date", "status"]),
        ]
        result = _level2_fuzzy_duplicates(tables, set())
        assert len(result) == 1
        dup = result[0]
        expected_keys = {
            "table_a_id", "table_a_name", "table_a_tool", "table_a_file",
            "table_b_id", "table_b_name", "table_b_tool", "table_b_file",
            "combined_score", "table_name_similarity", "column_jaccard", "match_reason",
        }
        assert expected_keys.issubset(set(dup.keys()))


class TestRunDedupCheckSuccess:
    """Test run_dedup_check success path with mocked DB calls."""

    def test_run_dedup_check_success_path(self):
        from postgres_dedup import run_dedup_check
        mock_source_dups = [
            {
                "fingerprint": "abc123",
                "dup_count": 2,
                "source_ids": ["s1", "s2"],
                "source_names": ["DB1", "DB1"],
                "report_ids": ["r1", "r2"],
                "tools": ["tableau", "powerbi"],
                "file_names": ["a.twb", "b.pbix"],
                "source_type": "SQL Server",
                "server": "prod-db",
                "database_name": "SalesDB",
            }
        ]
        mock_table_dups = [
            {
                "column_signature": "sig001",
                "dup_count": 2,
                "table_ids": ["t1", "t2"],
                "table_names": ["FactSales", "FactSales"],
                "report_ids": ["r1", "r2"],
                "tools": ["tableau", "powerbi"],
                "file_names": ["a.twb", "b.pbix"],
            }
        ]
        mock_all_tables = [
            {
                "table_id": "t3",
                "table_name": "DimDate",
                "report_id": "r3",
                "column_signature": "sig002",
                "tool_type": "tableau",
                "file_name": "c.twb",
                "column_names": ["datekey", "year", "month"],
            }
        ]
        with patch("postgres_dedup._level1_data_source_duplicates", return_value=mock_source_dups), \
             patch("postgres_dedup._level1_table_structure_duplicates", return_value=mock_table_dups), \
             patch("postgres_dedup._fetch_all_tables_with_columns", return_value=mock_all_tables):
            result = run_dedup_check()

        assert "level1" in result
        assert "level2" in result
        assert "summary" in result
        assert result["summary"]["exact_duplicate_source_groups"] == 1
        assert result["summary"]["exact_duplicate_table_groups"] == 1
        assert result["summary"]["fuzzy_duplicate_pairs"] == 0
        assert result["level1"]["data_source_duplicates"] == mock_source_dups
        assert result["level1"]["table_structure_duplicates"] == mock_table_dups


# ===========================================================================
# SECTION 3 — postgres_writer.py (mocked DB)
# ===========================================================================

class TestInitDb:
    """Test init_db success and failure paths."""

    def test_init_db_success(self):
        """init_db should call engine.connect and Base.metadata.create_all."""
        from postgres_writer import init_db
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        with patch("postgres_writer.engine") as mock_engine, \
             patch("postgres_writer.Base") as mock_base:
            mock_engine.connect.return_value = mock_conn
            init_db()
            mock_engine.connect.assert_called_once()
            mock_base.metadata.create_all.assert_called_once_with(bind=mock_engine)

    def test_init_db_raises_on_connect_failure(self):
        """init_db should re-raise exceptions from engine.connect."""
        from postgres_writer import init_db
        with patch("postgres_writer.engine") as mock_engine:
            mock_engine.connect.side_effect = Exception("Connection refused")
            with pytest.raises(Exception, match="Connection refused"):
                init_db()


class TestGetDbSession:
    """Test get_db_session context manager rollback path."""

    def test_get_db_session_commits_on_success(self):
        """Session should be committed when no exception occurs."""
        from postgres_writer import get_db_session
        mock_session = MagicMock()
        with patch("postgres_writer.SessionLocal", return_value=mock_session):
            with get_db_session() as session:
                assert session is mock_session
            mock_session.commit.assert_called_once()
            mock_session.rollback.assert_not_called()
            mock_session.close.assert_called_once()

    def test_get_db_session_rollback_on_exception(self):
        """Session should be rolled back when an exception is raised inside the block."""
        from postgres_writer import get_db_session
        mock_session = MagicMock()
        with patch("postgres_writer.SessionLocal", return_value=mock_session):
            with pytest.raises(ValueError, match="test error"):
                with get_db_session() as session:
                    raise ValueError("test error")
            mock_session.rollback.assert_called_once()
            mock_session.commit.assert_not_called()
            mock_session.close.assert_called_once()

    def test_get_db_session_always_closes(self):
        """Session.close() must be called even when exception occurs."""
        from postgres_writer import get_db_session
        mock_session = MagicMock()
        with patch("postgres_writer.SessionLocal", return_value=mock_session):
            try:
                with get_db_session():
                    raise RuntimeError("boom")
            except RuntimeError:
                pass
            mock_session.close.assert_called_once()


class TestWriteToPostgres:
    """Test write_to_postgres with mocked DB session."""

    def _make_mock_session_ctx(self):
        """Return a mock context manager that yields a mock session."""
        mock_session = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_session)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        return mock_ctx, mock_session

    def test_write_to_postgres_success_with_bi_reports(self):
        """write_to_postgres should insert bi_reports rows and return stored=True."""
        from postgres_writer import write_to_postgres
        report_id = str(uuid.uuid4())
        normalized_data = {
            "bi_reports": [
                {
                    "report_id": report_id,
                    "tool_type": "tableau",
                    "file_name": "test.twb",
                    "uploaded_at": datetime.now(timezone.utc).isoformat(),
                    "executive_summary": "Test report",
                }
            ]
        }
        mock_ctx, mock_session = self._make_mock_session_ctx()
        with patch("postgres_writer.init_db"), \
             patch("postgres_writer.get_db_session", return_value=mock_ctx):
            result = write_to_postgres(normalized_data)

        assert result["stored"] is True
        assert "bi_reports" in result["tables_written"]
        assert result["row_counts"]["bi_reports"] == 1
        assert result["report_id"] == report_id
        assert len(result["errors"]) == 0
        mock_session.add_all.assert_called_once()
        mock_session.flush.assert_called_once()

    def test_write_to_postgres_multiple_tables(self):
        """write_to_postgres should handle multiple table types."""
        from postgres_writer import write_to_postgres
        report_id = str(uuid.uuid4())
        source_id = str(uuid.uuid4())
        normalized_data = {
            "bi_reports": [
                {
                    "report_id": report_id,
                    "tool_type": "powerbi",
                    "file_name": "test.pbix",
                    "uploaded_at": datetime.now(timezone.utc).isoformat(),
                    "executive_summary": "",
                }
            ],
            "data_sources": [
                {
                    "source_id": source_id,
                    "report_id": report_id,
                    "name": "Azure SQL",
                    "source_type": "AzureSQL",
                    "server": "myserver",
                    "database_name": "SalesDB",
                    "schema_name": "dbo",
                    "connection_details": "",
                    "connection_mode": "DirectQuery",
                    "authentication_method": "OAuth2",
                    "gateway": "",
                    "refresh_schedule": "",
                    "is_extract": False,
                    "extract_refresh_schedule": "",
                    "is_published": False,
                    "used_by": "",
                    "fingerprint": "abc123",
                }
            ],
        }
        mock_ctx, mock_session = self._make_mock_session_ctx()
        with patch("postgres_writer.init_db"), \
             patch("postgres_writer.get_db_session", return_value=mock_ctx):
            result = write_to_postgres(normalized_data)

        assert result["stored"] is True
        assert "bi_reports" in result["tables_written"]
        assert "data_sources" in result["tables_written"]
        assert result["row_counts"]["bi_reports"] == 1
        assert result["row_counts"]["data_sources"] == 1

    def test_write_to_postgres_unknown_table_name(self):
        """write_to_postgres should log error for unknown table names."""
        from postgres_writer import write_to_postgres
        normalized_data = {
            "unknown_table_xyz": [{"some_col": "some_val"}],
        }
        mock_ctx, mock_session = self._make_mock_session_ctx()
        with patch("postgres_writer.init_db"), \
             patch("postgres_writer.get_db_session", return_value=mock_ctx), \
             patch("postgres_writer.TABLE_NAME_TO_MODEL", {}):
            result = write_to_postgres(normalized_data)

        # No tables written, but no crash
        assert result["stored"] is True  # no errors from known tables
        assert "unknown_table_xyz" not in result["tables_written"]

    def test_write_to_postgres_skips_empty_tables(self):
        """write_to_postgres should skip tables with no rows."""
        from postgres_writer import write_to_postgres
        normalized_data = {
            "bi_reports": [],
            "data_sources": [],
        }
        mock_ctx, mock_session = self._make_mock_session_ctx()
        with patch("postgres_writer.init_db"), \
             patch("postgres_writer.get_db_session", return_value=mock_ctx):
            result = write_to_postgres(normalized_data)

        assert result["stored"] is True
        assert len(result["tables_written"]) == 0
        mock_session.add_all.assert_not_called()

    def test_write_to_postgres_filters_unknown_columns(self):
        """write_to_postgres should filter out columns not in the model."""
        from postgres_writer import write_to_postgres
        report_id = str(uuid.uuid4())
        normalized_data = {
            "bi_reports": [
                {
                    "report_id": report_id,
                    "tool_type": "tableau",
                    "file_name": "test.twb",
                    "uploaded_at": datetime.now(timezone.utc).isoformat(),
                    "executive_summary": "Test",
                    "UNKNOWN_COLUMN": "should be filtered",
                    "__tablename__": "injection_attempt",
                }
            ]
        }
        mock_ctx, mock_session = self._make_mock_session_ctx()
        with patch("postgres_writer.init_db"), \
             patch("postgres_writer.get_db_session", return_value=mock_ctx):
            result = write_to_postgres(normalized_data)

        assert result["stored"] is True
        # Verify add_all was called with instances (unknown cols filtered)
        mock_session.add_all.assert_called_once()
        instances = mock_session.add_all.call_args[0][0]
        assert len(instances) == 1

    def test_write_to_postgres_table_insert_error_continues(self):
        """write_to_postgres should continue to next table on per-table error."""
        from postgres_writer import write_to_postgres
        report_id = str(uuid.uuid4())
        normalized_data = {
            "bi_reports": [
                {
                    "report_id": report_id,
                    "tool_type": "tableau",
                    "file_name": "test.twb",
                    "uploaded_at": datetime.now(timezone.utc).isoformat(),
                    "executive_summary": "",
                }
            ]
        }
        mock_ctx, mock_session = self._make_mock_session_ctx()
        mock_session.flush.side_effect = Exception("Constraint violation")
        with patch("postgres_writer.init_db"), \
             patch("postgres_writer.get_db_session", return_value=mock_ctx):
            result = write_to_postgres(normalized_data)

        assert result["stored"] is False
        assert len(result["errors"]) > 0
        assert "bi_reports" in result["errors"][0]

    def test_write_to_postgres_init_db_failure(self):
        """write_to_postgres should return error summary when init_db fails."""
        from postgres_writer import write_to_postgres
        with patch("postgres_writer.init_db", side_effect=Exception("DB unavailable")):
            result = write_to_postgres({"bi_reports": [{"report_id": "x"}]})

        assert result["stored"] is False
        assert any("DB unavailable" in e for e in result["errors"])

    def test_write_to_postgres_no_report_id_in_summary(self):
        """write_to_postgres should not set report_id in summary if bi_reports is empty."""
        from postgres_writer import write_to_postgres
        mock_ctx, mock_session = self._make_mock_session_ctx()
        with patch("postgres_writer.init_db"), \
             patch("postgres_writer.get_db_session", return_value=mock_ctx):
            result = write_to_postgres({})

        assert "report_id" not in result


class TestSaveExtractionLog:
    """Test save_extraction_log with various result types."""

    def _make_mock_session_ctx(self):
        mock_session = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_session)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        return mock_ctx, mock_session

    def test_save_extraction_log_with_dict_result(self):
        """save_extraction_log should store dict result directly."""
        from postgres_writer import save_extraction_log
        mock_ctx, mock_session = self._make_mock_session_ctx()
        with patch("postgres_writer.get_db_session", return_value=mock_ctx):
            save_extraction_log(
                report_id="rpt-001",
                tool_type="tableau",
                file_name="test.twb",
                status="SUCCESS",
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                runtime_seconds="5.23",
                postgres_stored=True,
                result={"tables_written": ["bi_reports"], "row_counts": {"bi_reports": 1}},
            )
        mock_session.add.assert_called_once()

    def test_save_extraction_log_with_valid_json_string(self):
        """save_extraction_log should parse valid JSON string result."""
        from postgres_writer import save_extraction_log
        mock_ctx, mock_session = self._make_mock_session_ctx()
        with patch("postgres_writer.get_db_session", return_value=mock_ctx):
            save_extraction_log(
                report_id="rpt-002",
                tool_type="powerbi",
                file_name="test.pbix",
                status="SUCCESS",
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                result='{"stored": true, "tables_written": ["bi_reports"]}',
            )
        mock_session.add.assert_called_once()
        # Verify the log object was created with parsed dict
        log_obj = mock_session.add.call_args[0][0]
        assert isinstance(log_obj.result, dict)
        assert log_obj.result["stored"] is True

    def test_save_extraction_log_with_invalid_json_string(self):
        """save_extraction_log should wrap invalid JSON string in raw dict."""
        from postgres_writer import save_extraction_log
        mock_ctx, mock_session = self._make_mock_session_ctx()
        with patch("postgres_writer.get_db_session", return_value=mock_ctx):
            save_extraction_log(
                report_id="rpt-003",
                tool_type="qlikview",
                file_name="test.qvw",
                status="FAILED",
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                error="Extraction failed",
                result="this is not valid json {{{",
            )
        mock_session.add.assert_called_once()
        log_obj = mock_session.add.call_args[0][0]
        # Should be wrapped in {"raw": ...}
        assert isinstance(log_obj.result, dict)
        assert "raw" in log_obj.result
        assert log_obj.result["raw"] == "this is not valid json {{{"

    def test_save_extraction_log_with_none_result(self):
        """save_extraction_log should handle None result."""
        from postgres_writer import save_extraction_log
        mock_ctx, mock_session = self._make_mock_session_ctx()
        with patch("postgres_writer.get_db_session", return_value=mock_ctx):
            save_extraction_log(
                report_id="rpt-004",
                tool_type="tableau",
                file_name="test.twb",
                status="SUCCESS",
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                result=None,
            )
        mock_session.add.assert_called_once()

    def test_save_extraction_log_with_error_and_traceback(self):
        """save_extraction_log should store error and traceback fields."""
        from postgres_writer import save_extraction_log
        mock_ctx, mock_session = self._make_mock_session_ctx()
        with patch("postgres_writer.get_db_session", return_value=mock_ctx):
            save_extraction_log(
                report_id="rpt-005",
                tool_type="powerbi",
                file_name="fail.pbix",
                status="FAILED",
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                error="NullPointerException",
                traceback="Traceback (most recent call last):\n  ...",
                postgres_stored=False,
                result=None,
            )
        log_obj = mock_session.add.call_args[0][0]
        assert log_obj.error == "NullPointerException"
        assert log_obj.traceback is not None
        assert log_obj.status == "FAILED"
        assert log_obj.postgres_stored is False

    def test_save_extraction_log_db_failure_does_not_raise(self):
        """save_extraction_log should silently handle DB errors."""
        from postgres_writer import save_extraction_log
        with patch("postgres_writer.get_db_session", side_effect=Exception("DB down")):
            # Must not raise
            save_extraction_log(
                report_id="rpt-006",
                tool_type="tableau",
                file_name="test.twb",
                status="SUCCESS",
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
            )


# ===========================================================================
# SECTION 2b — postgres_dedup.py DB-dependent functions (mocked session)
# ===========================================================================

class TestLevel1DataSourceDuplicates:
    """Test _level1_data_source_duplicates with mocked DB session."""

    def _make_session_ctx(self, mock_session):
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_session)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        return mock_ctx

    def test_returns_empty_when_no_duplicates(self):
        from postgres_dedup import _level1_data_source_duplicates
        mock_session = MagicMock()
        # No duplicate fingerprints found
        mock_session.query.return_value.filter.return_value.group_by.return_value \
            .having.return_value.order_by.return_value.all.return_value = []
        mock_ctx = self._make_session_ctx(mock_session)
        with patch("postgres_dedup.get_db_session", return_value=mock_ctx):
            result = _level1_data_source_duplicates()
        assert result == []

    def test_returns_groups_when_duplicates_found(self):
        from postgres_dedup import _level1_data_source_duplicates
        from postgres_models import DataSource, BiReport
        mock_session = MagicMock()

        # Simulate one duplicate fingerprint group
        mock_session.query.return_value.filter.return_value.group_by.return_value \
            .having.return_value.order_by.return_value.all.return_value = [
                ("fp_abc123", 2)
            ]

        # Simulate the sources in that group
        src1 = MagicMock()
        src1.DataSource.source_id = "s1"
        src1.DataSource.name = "Sales DB"
        src1.DataSource.report_id = "r1"
        src1.DataSource.source_type = "SQL Server"
        src1.DataSource.server = "prod-db"
        src1.DataSource.database_name = "SalesDB"
        src1.BiReport.tool_type = "tableau"
        src1.BiReport.file_name = "a.twb"

        src2 = MagicMock()
        src2.DataSource.source_id = "s2"
        src2.DataSource.name = "Sales DB"
        src2.DataSource.report_id = "r2"
        src2.DataSource.source_type = "SQL Server"
        src2.DataSource.server = "prod-db"
        src2.DataSource.database_name = "SalesDB"
        src2.BiReport.tool_type = "powerbi"
        src2.BiReport.file_name = "b.pbix"

        # Second query call returns the sources
        mock_session.query.return_value.join.return_value.filter.return_value.all.return_value = [
            src1, src2
        ]

        mock_ctx = self._make_session_ctx(mock_session)
        with patch("postgres_dedup.get_db_session", return_value=mock_ctx):
            result = _level1_data_source_duplicates()

        assert len(result) == 1
        grp = result[0]
        assert grp["fingerprint"] == "fp_abc123"
        assert grp["dup_count"] == 2
        assert "s1" in grp["source_ids"]
        assert "s2" in grp["source_ids"]
        assert grp["source_type"] == "SQL Server"


class TestLevel1TableStructureDuplicates:
    """Test _level1_table_structure_duplicates with mocked DB session."""

    def _make_session_ctx(self, mock_session):
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_session)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        return mock_ctx

    def test_returns_empty_when_no_duplicates(self):
        from postgres_dedup import _level1_table_structure_duplicates
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.group_by.return_value \
            .having.return_value.order_by.return_value.all.return_value = []
        mock_ctx = self._make_session_ctx(mock_session)
        with patch("postgres_dedup.get_db_session", return_value=mock_ctx):
            result = _level1_table_structure_duplicates()
        assert result == []

    def test_returns_groups_when_duplicates_found(self):
        from postgres_dedup import _level1_table_structure_duplicates
        mock_session = MagicMock()

        mock_session.query.return_value.filter.return_value.group_by.return_value \
            .having.return_value.order_by.return_value.all.return_value = [
                ("sig_xyz789", 3)
            ]

        tbl1 = MagicMock()
        tbl1.TableModel.table_id = "t1"
        tbl1.TableModel.table_name = "FactSales"
        tbl1.TableModel.report_id = "r1"
        tbl1.BiReport.tool_type = "tableau"
        tbl1.BiReport.file_name = "a.twb"

        tbl2 = MagicMock()
        tbl2.TableModel.table_id = "t2"
        tbl2.TableModel.table_name = "FactSales"
        tbl2.TableModel.report_id = "r2"
        tbl2.BiReport.tool_type = "powerbi"
        tbl2.BiReport.file_name = "b.pbix"

        mock_session.query.return_value.join.return_value.filter.return_value.all.return_value = [
            tbl1, tbl2
        ]

        mock_ctx = self._make_session_ctx(mock_session)
        with patch("postgres_dedup.get_db_session", return_value=mock_ctx):
            result = _level1_table_structure_duplicates()

        assert len(result) == 1
        grp = result[0]
        assert grp["column_signature"] == "sig_xyz789"
        assert grp["dup_count"] == 3
        assert "t1" in grp["table_ids"]
        assert "FactSales" in grp["table_names"]


class TestFetchAllTablesWithColumns:
    """Test _fetch_all_tables_with_columns with mocked DB session."""

    def _make_session_ctx(self, mock_session):
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_session)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        return mock_ctx

    def test_returns_empty_when_no_tables(self):
        from postgres_dedup import _fetch_all_tables_with_columns
        mock_session = MagicMock()
        mock_session.query.return_value.join.return_value.all.return_value = []
        mock_ctx = self._make_session_ctx(mock_session)
        with patch("postgres_dedup.get_db_session", return_value=mock_ctx):
            result = _fetch_all_tables_with_columns()
        assert result == []

    def test_returns_tables_with_columns(self):
        from postgres_dedup import _fetch_all_tables_with_columns
        mock_session = MagicMock()

        # Mock table row
        row = MagicMock()
        row.TableModel.table_id = "t1"
        row.TableModel.table_name = "FactSales"
        row.TableModel.report_id = "r1"
        row.TableModel.column_signature = "sig001"
        row.BiReport.tool_type = "tableau"
        row.BiReport.file_name = "a.twb"

        mock_session.query.return_value.join.return_value.all.return_value = [row]

        # Mock column query
        col1 = MagicMock()
        col1.name = "SaleID"
        col2 = MagicMock()
        col2.name = "Amount"
        col3 = MagicMock()
        col3.name = None  # Should be filtered out

        mock_session.query.return_value.filter.return_value.all.return_value = [col1, col2, col3]

        mock_ctx = self._make_session_ctx(mock_session)
        with patch("postgres_dedup.get_db_session", return_value=mock_ctx):
            result = _fetch_all_tables_with_columns()

        assert len(result) == 1
        tbl = result[0]
        assert tbl["table_id"] == "t1"
        assert tbl["table_name"] == "FactSales"
        assert tbl["tool_type"] == "tableau"
        # None column should be filtered
        assert None not in tbl["column_names"]
        assert "saleid" in tbl["column_names"]
        assert "amount" in tbl["column_names"]

    def test_run_dedup_check_prints_source_dup_details(self):
        """run_dedup_check should print details for each source dup group (line 194)."""
        from postgres_dedup import run_dedup_check
        mock_source_dups = [
            {
                "fingerprint": "fp001",
                "dup_count": 2,
                "source_type": "SQL Server",
                "server": "prod-db",
                "database_name": "SalesDB",
            }
        ]
        with patch("postgres_dedup._level1_data_source_duplicates", return_value=mock_source_dups), \
             patch("postgres_dedup._level1_table_structure_duplicates", return_value=[]), \
             patch("postgres_dedup._fetch_all_tables_with_columns", return_value=[]):
            result = run_dedup_check()
        assert result["summary"]["exact_duplicate_source_groups"] == 1
        assert result["summary"]["exact_duplicate_table_groups"] == 0
