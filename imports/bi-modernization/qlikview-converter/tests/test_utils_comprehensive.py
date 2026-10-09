"""
test_utils_comprehensive.py — additional coverage for utils.py public & comprehensive functions.

Targets the uncovered ranges:
  - Legacy public API: _log_xml_preview, _dashboards_using_datasource, parse_datasources,
    parse_data_model, extract_semantic_roles, parse_transformations, parse_hierarchies,
    parse_sheets, extract_visualization_snippets, extract_visualization_sections,
    extract_full_workbook_sections, get_sections_for_llm, parse_filters, parse_parameters,
    parse_dashboards, parse_structured_workbook
  - Comprehensive domain extractors: _extract_named_connections, _extract_datasources_comprehensive,
    _extract_tables_comprehensive, _extract_column_aliases, _extract_joins_and_relationships,
    _extract_calculations_comprehensive, _extract_parameters_comprehensive,
    _extract_filters_comprehensive, _extract_groups_and_sets, _extract_metadata_records,
    _extract_extract_info, _extract_custom_sql, _extract_security
  - Structured extractors: _extract_worksheets_structured (slices branch),
    _extract_zone_formatted_text, _extract_dashboard_zones_structured, _extract_styles,
    _extract_thumbnails_info, _extract_windows_info
  - Visuals extractors: _extract_dual_axes, _extract_trend_lines, _extract_conditional_formatting,
    _extract_highlight_actions, _extract_tooltips, _extract_dashboard_actions,
    _extract_reference_lines, _extract_axes, _extract_legends
  - _extract_dashboard_objects, _extract_format_overrides, _extract_annotations
  - _extract_table_calc_configs, _extract_groups_and_sets
"""

import xml.etree.ElementTree as ET
import pytest

from utils import (
    _log_xml_preview,
    _dashboards_using_datasource,
    parse_datasources,
    parse_data_model,
    extract_semantic_roles,
    parse_transformations,
    parse_hierarchies,
    parse_sheets,
    extract_visualization_snippets,
    extract_visualization_sections,
    extract_full_workbook_sections,
    get_sections_for_llm,
    parse_filters,
    parse_parameters,
    parse_dashboards,
    parse_structured_workbook,
    _extract_named_connections,
    _extract_datasources_comprehensive,
    _extract_tables_comprehensive,
    _extract_column_aliases,
    _extract_joins_and_relationships,
    _extract_calculations_comprehensive,
    _extract_parameters_comprehensive,
    _extract_filters_comprehensive,
    _extract_groups_and_sets,
    _extract_metadata_records,
    _extract_extract_info,
    _extract_custom_sql,
    _extract_security,
    _extract_worksheets_structured,
    _extract_zone_formatted_text,
    _extract_dashboard_zones_structured,
    _extract_styles,
    _extract_thumbnails_info,
    _extract_windows_info,
    _extract_dual_axis,
    _extract_trend_lines,
    _extract_conditional_formatting,
    _extract_highlight_actions,
    _extract_tooltips,
    _extract_dashboard_actions,
    _extract_reference_lines,
    _extract_axes,
    _extract_legends,
    _extract_dashboard_objects,
    _extract_format_overrides,
    _extract_annotations,
    _extract_table_calc_configs,
)

# ---------------------------------------------------------------------------
# Minimal workbook XML helpers
# ---------------------------------------------------------------------------

_SIMPLE_TWB = b"""<?xml version='1.0' encoding='utf-8'?>
<workbook>
  <datasources>
    <datasource name='ds1' caption='Sales' version='18.1' inline='true'>
      <connection class='excel-direct'>
        <named-connections>
          <named-connection name='nc1' caption='NC1'>
            <connection class='excel-direct' filename='C:/data/sales.xlsx' server='' port='' dbname='SalesDB' schema='dbo' username='user' authentication='auth' warehouse='wh' directory='/tmp' sslmode='require'/>
          </named-connection>
        </named-connections>
      </connection>
      <extract enabled='true' units='hours' count='5'>
        <connection class='hyper'/>
      </extract>
      <aliases enabled='yes'/>
      <column name='[Sales]' caption='Sales' datatype='integer' role='measure' type='quantitative' format='#,##0'/>
      <column name='[Region]' caption='Region' datatype='string' role='dimension' type='nominal'/>
    </datasource>
    <datasource name='Parameters' caption='Parameters'>
      <column name='[Param1]' caption='My Param' datatype='integer' role='measure' type='quantitative' value='10' param-domain-type='range'>
        <calculation formula='10' class='tableau'/>
        <range min='0' max='100' granularity='1'/>
      </column>
      <column name='[Param2]' caption='My Enum' datatype='string' role='dimension' type='nominal' value='A' param-domain-type='list'>
        <members>
          <member value='A'/>
          <member value='B'/>
        </members>
      </column>
    </datasource>
  </datasources>
  <worksheets>
    <worksheet name='Sheet1'>
      <simple-id uuid='ws-uuid-1'/>
      <table>
        <view>
          <datasources>
            <datasource name='ds1' caption='Sales'/>
          </datasources>
          <datasource-dependencies datasource='ds1'>
            <column name='[Latitude (generated)]'/>
          </datasource-dependencies>
          <rows>[Sales]</rows>
          <cols>[Region]</cols>
          <filter class='categorical' column='[Region]'>
            <groupfilter function='member' member='West'/>
          </filter>
          <slices>
            <column>[Region]</column>
          </slices>
          <tooltip>
            <formatted-text>
              <run>Sales: [Sales]</run>
            </formatted-text>
          </tooltip>
        </view>
        <panes>
          <pane>
            <encodings>
              <encoding attr='color' field='[Region]' type='nominal' palette='tableau20'/>
            </encodings>
            <sort column='[Sales]' direction='desc'/>
            <trend-lines>
              <trend-line type='linear' show-confidence-bands='true'>
                <field column='[Sales]'/>
              </trend-line>
            </trend-lines>
            <forecast>
              <forecast-options show-prediction-intervals='true' forecast-forward='3' forecast-granularity='month'/>
            </forecast>
            <reference-line column='[Sales]' value='SUM([Sales])' label='Avg' line-style='dashed' color='red'/>
            <mark-labels show-mark-labels='true'/>
            <point-annotation x='10' y='20'>
              <formatted-text><run>Note</run></formatted-text>
            </point-annotation>
          </pane>
        </panes>
        <style>
          <style-rule element='axis'>
            <format attr='title' value='Sales Axis' field='[Sales]' scope='cols'/>
            <format attr='font-size' value='12'/>
          </style-rule>
          <style-rule element='cell'>
            <format attr='format' value='#,##0'/>
          </style-rule>
        </style>
        <marks>
          <mark class='bar'/>
        </marks>
      </table>
      <style>
        <style-rule element='cell'>
          <format attr='number-format' value='0.00'/>
        </style-rule>
      </style>
    </worksheet>
  </worksheets>
  <dashboards>
    <dashboard name='Dash1'>
      <simple-id uuid='dash-uuid-1'/>
      <layout-options>
        <title><formatted-text><run>My Dashboard</run></formatted-text></title>
      </layout-options>
      <size maxwidth='1200' maxheight='800'/>
      <datasources>
        <datasource caption='Sales'/>
      </datasources>
      <actions>
        <action name='Filter Action' type='filter' url='http://example.com' activation='select'>
          <source-sheet sheet='Sheet1'/>
          <target-sheet sheet='Sheet1'/>
          <field-mapping source-field='[Region]' target-field='[Region]'/>
        </action>
      </actions>
      <zones>
        <zone type-v2='layout-basic' id='z0' name='layout'>
          <zone type-v2='worksheet' id='z1' name='Sheet1' x='0' y='0' w='600' h='400'>
            <zone-style>
              <format attr='background' value='#fff'/>
            </zone-style>
          </zone>
          <zone type-v2='legend/color' id='z2' name='Sheet1' x='610' y='0' w='100' h='200'/>
          <zone type-v2='filter' id='z3' param='[Region]' x='0' y='410' w='200' h='30'/>
          <zone type-v2='text' id='z4' name='TextBox' x='700' y='0' w='100' h='50'>
            <formatted-text><run fontsize='14' fontcolor='#000'>Hello</run></formatted-text>
          </zone>
          <zone type-v2='web' id='z5' name='WebZone' url='http://example.com' x='700' y='60' w='100' h='50'/>
        </zone>
      </zones>
    </dashboard>
  </dashboards>
  <windows>
    <window class='worksheet' name='Sheet1' maximized='true' saved-x='10' saved-y='20'>
      <viewpoint>
        <highlight>
          <color-one-way>
            <field>[Region]</field>
          </color-one-way>
        </highlight>
      </viewpoint>
    </window>
  </windows>
  <preferences>
    <preference name='ui.encoding.shelf.height' value='24'/>
    <color-palette name='Custom' type='regular'>
      <color>#ff0000</color>
      <color>#00ff00</color>
    </color-palette>
  </preferences>
  <thumbnails>
    <thumbnail sheets='Sheet1'/>
  </thumbnails>
</workbook>"""


def _root(xml: bytes = _SIMPLE_TWB) -> ET.Element:
    return ET.fromstring(xml)


# ---------------------------------------------------------------------------
# TestLogXmlPreview
# ---------------------------------------------------------------------------

class TestLogXmlPreview:
    def test_empty_string(self):
        _log_xml_preview("label", "")

    def test_short_string(self):
        _log_xml_preview("label", "hello world")

    def test_long_string(self):
        _log_xml_preview("label", "x" * 5000)


# ---------------------------------------------------------------------------
# TestDashboardsUsingDatasource
# ---------------------------------------------------------------------------

class TestDashboardsUsingDatasource:
    def test_returns_matching_dashboard(self):
        root = _root()
        result = _dashboards_using_datasource(root, "Sales")
        assert "Dash1" in result

    def test_empty_caption_returns_empty(self):
        root = _root()
        assert _dashboards_using_datasource(root, "") == []

    def test_no_match_returns_empty(self):
        root = _root()
        assert _dashboards_using_datasource(root, "NonExistent") == []


# ---------------------------------------------------------------------------
# TestParseDatasources
# ---------------------------------------------------------------------------

class TestParseDatasources:
    def test_returns_list(self):
        root = _root()
        result = parse_datasources(root)
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_excel_type_detected(self):
        root = _root()
        result = parse_datasources(root)
        names = [d["name"] for d in result]
        assert any(n for n in names)

    def test_extract_flag(self):
        root = _root()
        result = parse_datasources(root)
        sales = next((d for d in result if d["name"] == "Sales"), None)
        assert sales is not None
        assert sales["is_extract"] is True

    def test_empty_workbook(self):
        root = ET.fromstring(b"<workbook/>")
        assert parse_datasources(root) == []


# ---------------------------------------------------------------------------
# TestParseDataModel
# ---------------------------------------------------------------------------

class TestParseDataModel:
    def test_returns_list(self):
        xml = b"""<workbook>
          <datasources>
            <datasource caption='DS'>
              <connection>
                <relation type='table' name='Orders'>
                  <columns>
                    <column name='ID' datatype='integer'/>
                    <column name='Name' datatype='string'/>
                  </columns>
                </relation>
              </connection>
            </datasource>
          </datasources>
        </workbook>"""
        root = ET.fromstring(xml)
        result = parse_data_model(root)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["table_name"] == "Orders"

    def test_skips_extract_table(self):
        xml = b"""<workbook>
          <datasources>
            <datasource caption='DS'>
              <connection>
                <relation type='table' name='Extract'/>
              </connection>
            </datasource>
          </datasources>
        </workbook>"""
        root = ET.fromstring(xml)
        result = parse_data_model(root)
        assert result == []

    def test_split_field_included(self):
        xml = b"""<workbook>
          <datasources>
            <datasource caption='DS'>
              <connection>
                <relation type='table' name='T1'/>
              </connection>
              <column name='[Split]' caption='Split' datatype='string'
                xmlns:user='http://www.tableausoftware.com/xml/user'
                user:SplitFieldOrigin='[Name]'/>
            </datasource>
          </datasources>
        </workbook>"""
        root = ET.fromstring(xml)
        result = parse_data_model(root)
        # T1 table entry exists
        assert any(r["table_name"] == "T1" for r in result)

    def test_empty_workbook(self):
        root = ET.fromstring(b"<workbook/>")
        assert parse_data_model(root) == []


# ---------------------------------------------------------------------------
# TestExtractSemanticRoles
# ---------------------------------------------------------------------------

class TestExtractSemanticRoles:
    def test_extracts_role(self):
        xml = b"""<workbook>
          <datasources>
            <datasource>
              <column name='[Country]' semantic-role='[Country].[Name]'/>
            </datasource>
          </datasources>
        </workbook>"""
        root = ET.fromstring(xml)
        result = extract_semantic_roles(root)
        assert "Country" in result
        assert result["Country"] == "[Country].[Name]"

    def test_skips_missing_name(self):
        xml = b"<workbook><datasources><datasource><column semantic-role='x'/></datasource></datasources></workbook>"
        root = ET.fromstring(xml)
        assert extract_semantic_roles(root) == {}

    def test_empty_workbook(self):
        assert extract_semantic_roles(ET.fromstring(b"<workbook/>")) == {}


# ---------------------------------------------------------------------------
# TestParseTransformations
# ---------------------------------------------------------------------------

class TestParseTransformations:
    def test_calc_field_extracted(self):
        xml = b"""<workbook>
          <datasources>
            <datasource caption='DS'>
              <column name='[Profit Ratio]' caption='Profit Ratio' datatype='real' role='measure'>
                <calculation formula='[Profit]/[Sales]'/>
              </column>
            </datasource>
          </datasources>
        </workbook>"""
        root = ET.fromstring(xml)
        result = parse_transformations(root)
        assert len(result) == 1
        assert result[0]["name"] == "Profit Ratio"
        assert "Profit" in result[0]["expression"]

    def test_split_field_extracted(self):
        xml = b"""<workbook>
          <datasources>
            <datasource caption='DS'>
              <column name='[Name 1]' caption='Name 1' datatype='string'
                xmlns:user='http://www.tableausoftware.com/xml/user'
                user:SplitFieldOrigin='[Name]'>
                <calculation formula='SPLIT([Name], " ", 1)'/>
              </column>
            </datasource>
          </datasources>
        </workbook>"""
        root = ET.fromstring(xml)
        result = parse_transformations(root)
        assert len(result) == 1
        assert "Extracts" in result[0]["description"]

    def test_empty_workbook(self):
        assert parse_transformations(ET.fromstring(b"<workbook/>")) == []


# ---------------------------------------------------------------------------
# TestParseHierarchies
# ---------------------------------------------------------------------------

class TestParseHierarchies:
    def test_extracts_hierarchy(self):
        xml = b"""<workbook>
          <drill-paths>
            <drill-path name='Location'>
              <field>[Country]</field>
              <field>[State]</field>
            </drill-path>
          </drill-paths>
        </workbook>"""
        root = ET.fromstring(xml)
        result = parse_hierarchies(root)
        assert len(result) == 1
        assert result[0]["name"] == "Location"
        assert "[Country]" in result[0]["members"]

    def test_empty(self):
        assert parse_hierarchies(ET.fromstring(b"<workbook/>")) == []


# ---------------------------------------------------------------------------
# TestParseSheets
# ---------------------------------------------------------------------------

class TestParseSheets:
    def test_extracts_sheets(self):
        root = _root()
        result = parse_sheets(root)
        assert any(s["name"] == "Sheet1" for s in result)

    def test_empty(self):
        assert parse_sheets(ET.fromstring(b"<workbook/>")) == []


# ---------------------------------------------------------------------------
# TestExtractVisualizationSnippets
# ---------------------------------------------------------------------------

class TestExtractVisualizationSnippets:
    def test_returns_snippets(self):
        root = _root()
        result = extract_visualization_snippets(root)
        assert isinstance(result, list)

    def test_empty(self):
        assert extract_visualization_snippets(ET.fromstring(b"<workbook/>")) == []


# ---------------------------------------------------------------------------
# TestExtractVisualizationSections
# ---------------------------------------------------------------------------

class TestExtractVisualizationSections:
    def test_returns_string(self):
        root = _root()
        result = extract_visualization_sections(root)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_worksheets(self):
        root = _root()
        result = extract_visualization_sections(root)
        assert "worksheet" in result.lower()

    def test_empty_workbook(self):
        result = extract_visualization_sections(ET.fromstring(b"<workbook/>"))
        assert result == ""


# ---------------------------------------------------------------------------
# TestExtractFullWorkbookSections
# ---------------------------------------------------------------------------

class TestExtractFullWorkbookSections:
    def test_returns_string(self):
        root = _root()
        result = extract_full_workbook_sections(root)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_empty_workbook(self):
        result = extract_full_workbook_sections(ET.fromstring(b"<workbook/>"))
        assert result == ""


# ---------------------------------------------------------------------------
# TestGetSectionsForLlm
# ---------------------------------------------------------------------------

class TestGetSectionsForLlm:
    def test_returns_dict_with_keys(self):
        result = get_sections_for_llm(_SIMPLE_TWB)
        assert "datasources" in result
        assert "visualizations" in result
        assert "full_workbook" in result
        assert "semantic_roles" in result

    def test_datasources_list(self):
        result = get_sections_for_llm(_SIMPLE_TWB)
        assert isinstance(result["datasources"], list)

    def test_invalid_xml_raises(self):
        with pytest.raises(ValueError):
            get_sections_for_llm(b"not xml")


# ---------------------------------------------------------------------------
# TestParseFilters
# ---------------------------------------------------------------------------

class TestParseFilters:
    def test_extracts_filter_zones(self):
        root = _root()
        result = parse_filters(root)
        assert isinstance(result, list)

    def test_filter_zone_has_columns(self):
        root = _root()
        result = parse_filters(root)
        for f in result:
            assert "columns" in f

    def test_empty(self):
        assert parse_filters(ET.fromstring(b"<workbook/>")) == []

    def test_worksheet_filter_skipped(self):
        xml = b"""<workbook>
          <zone type-v2='worksheet-filter' id='z1' param='[X]'/>
        </workbook>"""
        root = ET.fromstring(xml)
        result = parse_filters(root)
        assert result == []


# ---------------------------------------------------------------------------
# TestParseParameters
# ---------------------------------------------------------------------------

class TestParseParameters:
    def test_extracts_variables(self):
        xml = b"""<workbook>
          <variable name='MyVar' default='hello'/>
        </workbook>"""
        root = ET.fromstring(xml)
        result = parse_parameters(root)
        assert len(result) == 1
        assert result[0]["name"] == "MyVar"
        assert result[0]["calculation"] == "hello"

    def test_empty(self):
        assert parse_parameters(ET.fromstring(b"<workbook/>")) == []


# ---------------------------------------------------------------------------
# TestParseDashboards
# ---------------------------------------------------------------------------

class TestParseDashboards:
    def test_extracts_dashboard(self):
        root = _root()
        result = parse_dashboards(root)
        assert len(result) >= 1
        dash = result[0]
        assert "name" in dash
        assert "components" in dash

    def test_dashboard_name_from_title(self):
        root = _root()
        result = parse_dashboards(root)
        assert result[0]["name"] == "My Dashboard"

    def test_filter_zone_included(self):
        root = _root()
        result = parse_dashboards(root)
        names = [c["name"] for c in result[0]["components"]]
        assert "[Region]" in names

    def test_layout_zone_excluded(self):
        root = _root()
        result = parse_dashboards(root)
        names = [c["name"] for c in result[0]["components"]]
        assert "layout" not in names

    def test_empty(self):
        assert parse_dashboards(ET.fromstring(b"<workbook/>")) == []


# ---------------------------------------------------------------------------
# TestParseStructuredWorkbook
# ---------------------------------------------------------------------------

class TestParseStructuredWorkbook:
    def test_returns_dict_with_all_keys(self):
        result = parse_structured_workbook(_SIMPLE_TWB)
        for key in ("Data Sources", "Data Model", "Sheets", "Dashboards", "Filters"):
            assert key in result

    def test_invalid_xml_raises(self):
        with pytest.raises(ValueError):
            parse_structured_workbook(b"not xml")


# ---------------------------------------------------------------------------
# TestExtractNamedConnections
# ---------------------------------------------------------------------------

class TestExtractNamedConnections:
    def test_extracts_connection(self):
        root = _root()
        ds = root.find("datasources/datasource[@name='ds1']")
        result = _extract_named_connections(ds)
        assert len(result) == 1
        assert result[0]["name"] == "nc1"
        assert result[0]["class"] == "excel-direct"
        assert result[0]["sslmode"] == "require"

    def test_no_named_connections(self):
        ds = ET.fromstring(b"<datasource/>")
        assert _extract_named_connections(ds) == []


# ---------------------------------------------------------------------------
# TestExtractDatasourcesComprehensive
# ---------------------------------------------------------------------------

class TestExtractDatasourcesComprehensive:
    def test_returns_list(self):
        root = _root()
        result = _extract_datasources_comprehensive(root)
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_sales_datasource_present(self):
        root = _root()
        result = _extract_datasources_comprehensive(root)
        sales = next((d for d in result if d["caption"] == "Sales"), None)
        assert sales is not None
        assert sales["is_extract"] is True
        assert sales["extract_units"] == "hours"

    def test_used_by_dashboards(self):
        root = _root()
        result = _extract_datasources_comprehensive(root)
        sales = next((d for d in result if d["caption"] == "Sales"), None)
        assert "Dash1" in sales["used_by_dashboards"]

    def test_empty(self):
        assert _extract_datasources_comprehensive(ET.fromstring(b"<workbook/>")) == []


# ---------------------------------------------------------------------------
# TestExtractTablesComprehensive
# ---------------------------------------------------------------------------

class TestExtractTablesComprehensive:
    def test_extracts_table(self):
        xml = b"""<workbook>
          <datasources>
            <datasource name='ds1' caption='DS'>
              <connection>
                <relation type='table' name='Orders' table='[dbo].[Orders]'>
                  <columns>
                    <column name='ID' datatype='integer' ordinal='0'/>
                    <column name='&lt;system&gt;' datatype='string'/>
                  </columns>
                </relation>
              </connection>
              <column name='[Profit]' caption='Profit' datatype='real' role='measure'>
                <calculation formula='[Sales]*0.3'/>
              </column>
            </datasource>
          </datasources>
        </workbook>"""
        root = ET.fromstring(xml)
        result = _extract_tables_comprehensive(root)
        assert len(result) == 1
        assert result[0]["table_name"] == "Orders"
        col_names = [c["name"] for c in result[0]["columns"]]
        assert "ID" in col_names
        # < system > column skipped
        assert all(not n.startswith("<") for n in col_names)

    def test_calc_column_appended(self):
        xml = b"""<workbook>
          <datasources>
            <datasource name='ds1' caption='DS'>
              <connection>
                <relation type='table' name='T1'/>
              </connection>
              <column name='[Profit]' caption='Profit' datatype='real' role='measure'>
                <calculation formula='[Sales]*0.3'/>
              </column>
            </datasource>
          </datasources>
        </workbook>"""
        root = ET.fromstring(xml)
        result = _extract_tables_comprehensive(root)
        assert len(result) == 1
        col_names = [c["name"] for c in result[0]["columns"]]
        assert "Profit" in col_names

    def test_empty(self):
        assert _extract_tables_comprehensive(ET.fromstring(b"<workbook/>")) == []


# ---------------------------------------------------------------------------
# TestExtractColumnAliases
# ---------------------------------------------------------------------------

class TestExtractColumnAliases:
    def test_extracts_alias(self):
        xml = b"""<workbook>
          <datasources>
            <datasource name='ds1'>
              <column name='[ID]' caption='Customer ID'/>
            </datasource>
          </datasources>
        </workbook>"""
        root = ET.fromstring(xml)
        result = _extract_column_aliases(root)
        assert len(result) == 1
        assert result[0]["internal_name"] == "[ID]"
        assert result[0]["caption"] == "Customer ID"

    def test_skips_identical_name_caption(self):
        xml = b"""<workbook>
          <datasources>
            <datasource name='ds1'>
              <column name='Sales' caption='Sales'/>
            </datasource>
          </datasources>
        </workbook>"""
        root = ET.fromstring(xml)
        assert _extract_column_aliases(root) == []

    def test_empty(self):
        assert _extract_column_aliases(ET.fromstring(b"<workbook/>")) == []


# ---------------------------------------------------------------------------
# TestExtractJoinsAndRelationships
# ---------------------------------------------------------------------------

class TestExtractJoinsAndRelationships:
    def test_extracts_join(self):
        xml = b"""<workbook>
          <datasources>
            <datasource name='ds1'>
              <connection>
                <relation join='inner' type='join'>
                  <relation name='Orders'/>
                  <relation name='Customers'/>
                  <clause type='join'>
                    <expression op='='>
                      <expression op='[Orders].[ID]'/>
                      <expression op='[Customers].[OrderID]'/>
                    </expression>
                  </clause>
                </relation>
              </connection>
            </datasource>
          </datasources>
        </workbook>"""
        root = ET.fromstring(xml)
        result = _extract_joins_and_relationships(root)
        assert len(result) == 1
        r = result[0]
        assert r["join_type"] == "inner"
        assert r["left_table"] == "Orders"
        assert r["right_table"] == "Customers"
        assert len(r["clauses"]) == 1
        assert "[Orders].[ID]" in r["clauses"][0]["left"]

    def test_fallback_clause_parsing(self):
        xml = b"""<workbook>
          <datasources>
            <datasource name='ds1'>
              <connection>
                <relation join='left' type='join'>
                  <relation name='A'/>
                  <relation name='B'/>
                  <clause type='join'>
                    <expression op='left_col' value='lv'/>
                    <expression op='right_col' value='rv'/>
                  </clause>
                </relation>
              </connection>
            </datasource>
          </datasources>
        </workbook>"""
        root = ET.fromstring(xml)
        result = _extract_joins_and_relationships(root)
        assert result[0]["clauses"][0]["left"] == "left_col"
        assert result[0]["clauses"][0]["right"] == "right_col"

    def test_empty(self):
        assert _extract_joins_and_relationships(ET.fromstring(b"<workbook/>")) == []


# ---------------------------------------------------------------------------
# TestExtractCalculationsComprehensive
# ---------------------------------------------------------------------------

class TestExtractCalculationsComprehensive:
    def test_extracts_calc(self):
        xml = b"""<workbook>
          <datasources>
            <datasource name='ds1' caption='DS'>
              <column name='[PR]' caption='Profit Ratio' datatype='real' role='measure'>
                <calculation formula='[Profit]/[Sales]' class='regular'/>
              </column>
            </datasource>
          </datasources>
        </workbook>"""
        root = ET.fromstring(xml)
        result = _extract_calculations_comprehensive(root)
        assert len(result) == 1
        assert result[0]["caption"] == "Profit Ratio"
        assert "Profit" in result[0]["depends_on"]

    def test_split_field(self):
        xml = b"""<workbook>
          <datasources>
            <datasource name='ds1' caption='DS'>
              <column name='[Name 1]' caption='Name 1' datatype='string'
                xmlns:user='http://www.tableausoftware.com/xml/user'
                user:SplitFieldOrigin='[Name]'>
                <calculation formula='SPLIT([Name])' class='regular'/>
              </column>
            </datasource>
          </datasources>
        </workbook>"""
        root = ET.fromstring(xml)
        result = _extract_calculations_comprehensive(root)
        assert result[0]["is_split"] is True

    def test_empty(self):
        assert _extract_calculations_comprehensive(ET.fromstring(b"<workbook/>")) == []


# ---------------------------------------------------------------------------
# TestExtractParametersComprehensive
# ---------------------------------------------------------------------------

class TestExtractParametersComprehensive:
    def test_extracts_params(self):
        root = _root()
        result = _extract_parameters_comprehensive(root)
        assert any(p["name"] == "My Param" for p in result)

    def test_range_included(self):
        root = _root()
        result = _extract_parameters_comprehensive(root)
        param = next((p for p in result if p["name"] == "My Param"), None)
        assert param is not None
        assert "range" in param
        assert param["range"]["min"] == "0"

    def test_members_included(self):
        root = _root()
        result = _extract_parameters_comprehensive(root)
        param = next((p for p in result if p["name"] == "My Enum"), None)
        assert param is not None
        assert "allowed_values" in param
        assert "A" in param["allowed_values"]

    def test_variable_included(self):
        xml = b"""<workbook>
          <datasources/>
          <variable name='X' default='5'/>
        </workbook>"""
        root = ET.fromstring(xml)
        result = _extract_parameters_comprehensive(root)
        assert any(p["name"] == "X" for p in result)

    def test_empty(self):
        assert _extract_parameters_comprehensive(ET.fromstring(b"<workbook/>")) == []


# ---------------------------------------------------------------------------
# TestExtractFiltersComprehensive
# ---------------------------------------------------------------------------

class TestExtractFiltersComprehensive:
    def test_datasource_filter(self):
        xml = b"""<workbook>
          <datasources>
            <datasource name='ds1'>
              <filter class='categorical' column='[Region]'>
                <groupfilter function='member' member='West'/>
              </filter>
            </datasource>
          </datasources>
          <worksheets/>
        </workbook>"""
        root = ET.fromstring(xml)
        result = _extract_filters_comprehensive(root)
        assert len(result) == 1
        assert result[0]["scope"] == "datasource"
        assert "West" in result[0]["include_values"]

    def test_shared_view_filter(self):
        xml = b"""<workbook>
          <datasources/>
          <shared-views>
            <shared-view name='SV1'>
              <filter class='categorical' column='[Cat]'>
                <groupfilter function='member' member='A'/>
              </filter>
            </shared-view>
          </shared-views>
          <worksheets/>
        </workbook>"""
        root = ET.fromstring(xml)
        result = _extract_filters_comprehensive(root)
        assert any(f["scope"] == "shared_view" for f in result)

    def test_worksheet_filter(self):
        root = _root()
        result = _extract_filters_comprehensive(root)
        assert any(f["scope"] == "worksheet" for f in result)

    def test_quantitative_range_filter(self):
        xml = b"""<workbook>
          <datasources>
            <datasource name='ds1'>
              <filter class='quantitative' column='[Sales]'>
                <min>100</min>
                <max>500</max>
              </filter>
            </datasource>
          </datasources>
          <worksheets/>
        </workbook>"""
        root = ET.fromstring(xml)
        result = _extract_filters_comprehensive(root)
        assert result[0]["filter_config"]["min"] == "100"
        assert result[0]["filter_config"]["max"] == "500"

    def test_topn_filter_config(self):
        xml = b"""<workbook>
          <datasources>
            <datasource name='ds1'>
              <filter class='top' column='[Sales]'>
                <groupfilter function='end' count='5' direction='top'/>
              </filter>
            </datasource>
          </datasources>
          <worksheets/>
        </workbook>"""
        root = ET.fromstring(xml)
        result = _extract_filters_comprehensive(root)
        assert result[0]["filter_config"]["count"] == "5"

    def test_empty(self):
        assert _extract_filters_comprehensive(ET.fromstring(b"<workbook><worksheets/></workbook>")) == []


# ---------------------------------------------------------------------------
# TestExtractGroupsAndSets
# ---------------------------------------------------------------------------

class TestExtractGroupsAndSets:
    def test_extracts_group(self):
        xml = b"""<workbook>
          <datasources>
            <datasource name='ds1'>
              <group name='[Region Group]' caption='Region Group'>
                <groupfilter function='member' member='West'/>
                <groupfilter function='union'>
                  <groupfilter function='member' member='East'/>
                </groupfilter>
              </group>
            </datasource>
          </datasources>
        </workbook>"""
        root = ET.fromstring(xml)
        result = _extract_groups_and_sets(root)
        assert len(result) == 1
        assert result[0]["kind"] == "group"
        members = [m["member"] for m in result[0]["members"]]
        assert "West" in members

    def test_empty(self):
        assert _extract_groups_and_sets(ET.fromstring(b"<workbook/>")) == []


# ---------------------------------------------------------------------------
# TestExtractMetadataRecords
# ---------------------------------------------------------------------------

class TestExtractMetadataRecords:
    def test_extracts_record(self):
        xml = b"""<workbook>
          <datasources>
            <datasource name='ds1'>
              <connection>
                <metadata-records>
                  <metadata-record class='column'>
                    <remote-name>ID</remote-name>
                    <local-name>[ID]</local-name>
                  </metadata-record>
                </metadata-records>
              </connection>
            </datasource>
          </datasources>
        </workbook>"""
        root = ET.fromstring(xml)
        result = _extract_metadata_records(root)
        assert len(result) == 1
        assert result[0]["remote_name"] == "ID"
        assert result[0]["local_name"] == "[ID]"

    def test_empty(self):
        assert _extract_metadata_records(ET.fromstring(b"<workbook/>")) == []


# ---------------------------------------------------------------------------
# TestExtractExtractInfo
# ---------------------------------------------------------------------------

class TestExtractExtractInfo:
    def test_with_extract(self):
        root = _root()
        result = _extract_extract_info(root)
        assert any(r["enabled"] == "true" for r in result)

    def test_without_extract(self):
        xml = b"""<workbook>
          <datasources>
            <datasource name='ds_no_extract'/>
          </datasources>
        </workbook>"""
        root = ET.fromstring(xml)
        result = _extract_extract_info(root)
        assert result[0]["enabled"] == "false"

    def test_empty(self):
        assert _extract_extract_info(ET.fromstring(b"<workbook/>")) == []


# ---------------------------------------------------------------------------
# TestExtractCustomSql
# ---------------------------------------------------------------------------

class TestExtractCustomSql:
    def test_extracts_sql(self):
        xml = b"""<workbook>
          <datasources>
            <datasource name='ds1' caption='DS'>
              <connection>
                <relation type='text' name='Query1' connection='conn1'>SELECT * FROM orders</relation>
              </connection>
            </datasource>
          </datasources>
        </workbook>"""
        root = ET.fromstring(xml)
        result = _extract_custom_sql(root)
        assert len(result) == 1
        assert "SELECT" in result[0]["sql"]
        assert result[0]["name"] == "Query1"

    def test_empty(self):
        assert _extract_custom_sql(ET.fromstring(b"<workbook/>")) == []


# ---------------------------------------------------------------------------
# TestExtractSecurity
# ---------------------------------------------------------------------------

class TestExtractSecurity:
    def test_user_filter(self):
        xml = b"""<workbook>
          <datasources>
            <datasource name='ds1'>
              <user-filter name='uf1' column='[Region]'>
                <groupfilter function='member' member='West' user='alice'/>
              </user-filter>
            </datasource>
          </datasources>
        </workbook>"""
        root = ET.fromstring(xml)
        result = _extract_security(root)
        assert len(result) == 1
        assert result[0]["name"] == "uf1"
        assert result[0]["scope"] == "datasource"
        assert result[0]["members"][0]["user"] == "alice"

    def test_permission_rule(self):
        xml = b"""<workbook>
          <datasources/>
          <permission-rule name='CanEdit' rule='allow'/>
        </workbook>"""
        root = ET.fromstring(xml)
        result = _extract_security(root)
        assert any(r["scope"] == "workbook" for r in result)

    def test_empty(self):
        assert _extract_security(ET.fromstring(b"<workbook/>")) == []


# ---------------------------------------------------------------------------
# TestExtractWorksheetsStructured (slices branch)
# ---------------------------------------------------------------------------

class TestExtractWorksheetsStructuredSlices:
    def test_slices_added_as_filters(self):
        root = _root()
        result = _extract_worksheets_structured(root)
        assert len(result) >= 1
        ws = result[0]
        assert "filters" in ws["shelves"]
        assert "[Region]" in ws["shelves"]["filters"]

    def test_has_lat_lon(self):
        root = _root()
        result = _extract_worksheets_structured(root)
        assert result[0]["has_generated_lat_lon"] is True


# ---------------------------------------------------------------------------
# TestExtractZoneFormattedText
# ---------------------------------------------------------------------------

class TestExtractZoneFormattedText:
    def test_extracts_text(self):
        z = ET.fromstring(b"""<zone>
          <formatted-text>
            <run fontsize='14' fontcolor='#000'>Hello World</run>
          </formatted-text>
        </zone>""")
        result = _extract_zone_formatted_text(z)
        assert result is not None
        assert result["content"] == "Hello World"
        assert result["fontSize"] == "14"

    def test_no_formatted_text(self):
        z = ET.fromstring(b"<zone/>")
        assert _extract_zone_formatted_text(z) is None

    def test_empty_runs_returns_none(self):
        z = ET.fromstring(b"<zone><formatted-text/></zone>")
        assert _extract_zone_formatted_text(z) is None

    def test_empty_content_returns_none(self):
        z = ET.fromstring(b"<zone><formatted-text><run>   </run></formatted-text></zone>")
        assert _extract_zone_formatted_text(z) is None


# ---------------------------------------------------------------------------
# TestExtractDashboardZonesStructured
# ---------------------------------------------------------------------------

class TestExtractDashboardZonesStructured:
    def test_extracts_dashboard(self):
        root = _root()
        result = _extract_dashboard_zones_structured(root)
        assert len(result) >= 1
        d = result[0]
        assert d["name"] == "My Dashboard"
        assert d["width"] == 1200
        assert d["height"] == 800

    def test_zones_present(self):
        root = _root()
        result = _extract_dashboard_zones_structured(root)
        assert len(result[0]["zones"]) > 0

    def test_empty(self):
        assert _extract_dashboard_zones_structured(ET.fromstring(b"<workbook/>")) == []


# ---------------------------------------------------------------------------
# TestExtractStyles
# ---------------------------------------------------------------------------

class TestExtractStyles:
    def test_extracts_preferences(self):
        root = _root()
        result = _extract_styles(root)
        assert "preferences" in result
        assert len(result["preferences"]) >= 1
        assert result["preferences"][0]["name"] == "ui.encoding.shelf.height"

    def test_extracts_color_palettes(self):
        root = _root()
        result = _extract_styles(root)
        assert "color_palettes" in result
        cp = result["color_palettes"]
        assert len(cp) >= 1
        assert cp[0]["name"] == "Custom"
        assert "#ff0000" in cp[0]["colors"]

    def test_empty(self):
        result = _extract_styles(ET.fromstring(b"<workbook/>"))
        assert result["preferences"] == []
        assert result["color_palettes"] == []


# ---------------------------------------------------------------------------
# TestExtractThumbnailsInfo
# ---------------------------------------------------------------------------

class TestExtractThumbnailsInfo:
    def test_present(self):
        root = _root()
        result = _extract_thumbnails_info(root)
        assert result["present"] is True
        assert result["count"] == 1

    def test_not_present(self):
        result = _extract_thumbnails_info(ET.fromstring(b"<workbook/>"))
        assert result["present"] is False
        assert result["count"] == 0


# ---------------------------------------------------------------------------
# TestExtractWindowsInfo
# ---------------------------------------------------------------------------

class TestExtractWindowsInfo:
    def test_extracts_window(self):
        root = _root()
        result = _extract_windows_info(root)
        assert len(result) >= 1
        w = result[0]
        assert w["class"] == "worksheet"
        assert w["name"] == "Sheet1"
        assert w["maximized"] == "true"

    def test_empty(self):
        assert _extract_windows_info(ET.fromstring(b"<workbook/>")) == []


# ---------------------------------------------------------------------------
# TestExtractDualAxes
# ---------------------------------------------------------------------------

class TestExtractDualAxis:
    def test_no_dual_axis_when_single_pane(self):
        root = _root()
        result = _extract_dual_axis(root)
        assert result == []

    def test_dual_axis_detected(self):
        xml = b"""<workbook>
          <worksheets>
            <worksheet name='Chart1'>
              <table>
                <view>
                  <rows>[SUM(Sales)],[SUM(Profit)]</rows>
                </view>
                <panes>
                  <pane type='dual'><axis column='[Sales]'/></pane>
                  <pane type='dual'><axis column='[Profit]'/></pane>
                </panes>
              </table>
            </worksheet>
          </worksheets>
        </workbook>"""
        root = ET.fromstring(xml)
        result = _extract_dual_axis(root)
        assert len(result) == 1
        assert result[0]["worksheet"] == "Chart1"

    def test_empty(self):
        assert _extract_dual_axis(ET.fromstring(b"<workbook/>")) == []


# ---------------------------------------------------------------------------
# TestExtractTrendLines
# ---------------------------------------------------------------------------

class TestExtractTrendLines:
    def test_extracts_trend_line(self):
        root = _root()
        result = _extract_trend_lines(root)
        trend = next((r for r in result if r["type"] == "trend"), None)
        assert trend is not None
        assert trend["model_type"] == "linear"
        assert trend["confidence_bands"] is True

    def test_extracts_forecast(self):
        root = _root()
        result = _extract_trend_lines(root)
        fc = next((r for r in result if r["type"] == "forecast"), None)
        assert fc is not None
        assert fc["forecast_periods"] == "3"
        assert fc["forecast_granularity"] == "month"

    def test_empty(self):
        assert _extract_trend_lines(ET.fromstring(b"<workbook/>")) == []


# ---------------------------------------------------------------------------
# TestExtractConditionalFormatting
# ---------------------------------------------------------------------------

class TestExtractConditionalFormatting:
    def test_extracts_encoding(self):
        root = _root()
        result = _extract_conditional_formatting(root)
        assert any(r["field"] == "[Region]" for r in result)

    def test_legacy_color_encoding(self):
        xml = b"""<workbook>
          <worksheets>
            <worksheet name='S1'>
              <table>
                <panes>
                  <pane>
                    <color-encoding field='[Category]' palette='tableau10'/>
                  </pane>
                </panes>
              </table>
            </worksheet>
          </worksheets>
        </workbook>"""
        root = ET.fromstring(xml)
        result = _extract_conditional_formatting(root)
        assert len(result) == 1
        assert result[0]["encoding_type"] == "color_encoding"

    def test_empty(self):
        assert _extract_conditional_formatting(ET.fromstring(b"<workbook/>")) == []


# ---------------------------------------------------------------------------
# TestExtractHighlightActions
# ---------------------------------------------------------------------------

class TestExtractHighlightActions:
    def test_extracts_highlight(self):
        root = _root()
        result = _extract_highlight_actions(root)
        assert len(result) == 1
        assert result[0]["worksheet"] == "Sheet1"
        assert "[Region]" in result[0]["highlight_fields"]

    def test_non_worksheet_window_skipped(self):
        xml = b"""<workbook>
          <windows>
            <window class='dashboard' name='Dash1'>
              <viewpoint>
                <highlight><color-one-way><field>[X]</field></color-one-way></highlight>
              </viewpoint>
            </window>
          </windows>
        </workbook>"""
        root = ET.fromstring(xml)
        result = _extract_highlight_actions(root)
        assert result == []

    def test_empty(self):
        assert _extract_highlight_actions(ET.fromstring(b"<workbook/>")) == []


# ---------------------------------------------------------------------------
# TestExtractTooltips
# ---------------------------------------------------------------------------

class TestExtractTooltips:
    def test_extracts_tooltip(self):
        root = _root()
        result = _extract_tooltips(root)
        assert len(result) == 1
        assert result[0]["worksheet"] == "Sheet1"
        assert "Sales" in result[0]["formatted_text"]
        assert "Sales" in result[0]["field_references"]

    def test_empty(self):
        assert _extract_tooltips(ET.fromstring(b"<workbook/>")) == []


# ---------------------------------------------------------------------------
# TestExtractDashboardActions
# ---------------------------------------------------------------------------

class TestExtractDashboardActions:
    def test_extracts_action(self):
        root = _root()
        result = _extract_dashboard_actions(root)
        assert len(result) == 1
        a = result[0]
        assert a["name"] == "Filter Action"
        assert a["type"] == "filter"
        assert "Sheet1" in a["source_worksheets"]
        assert a["url"] == "http://example.com"

    def test_field_mappings(self):
        root = _root()
        result = _extract_dashboard_actions(root)
        assert len(result[0]["field_mappings"]) == 1
        assert result[0]["field_mappings"][0]["source"] == "[Region]"

    def test_empty(self):
        assert _extract_dashboard_actions(ET.fromstring(b"<workbook/>")) == []


# ---------------------------------------------------------------------------
# TestExtractReferenceLines
# ---------------------------------------------------------------------------

class TestExtractReferenceLines:
    def test_extracts_reference_line(self):
        root = _root()
        result = _extract_reference_lines(root)
        assert len(result) == 1
        r = result[0]
        assert r["worksheet"] == "Sheet1"
        assert r["axis_or_field"] == "[Sales]"
        assert r["formatting"]["line-style"] == "dashed"

    def test_empty(self):
        assert _extract_reference_lines(ET.fromstring(b"<workbook/>")) == []


# ---------------------------------------------------------------------------
# TestExtractAxes
# ---------------------------------------------------------------------------

class TestExtractAxes:
    def test_extracts_from_style_rules(self):
        root = _root()
        result = _extract_axes(root)
        style_axes = [a for a in result if a["title"] == "Sales Axis"]
        assert len(style_axes) == 1
        assert style_axes[0]["tick_formatting"]["font-size"] == "12"

    def test_empty(self):
        assert _extract_axes(ET.fromstring(b"<workbook/>")) == []


# ---------------------------------------------------------------------------
# TestExtractLegends
# ---------------------------------------------------------------------------

class TestExtractLegends:
    _LEGEND_XML = b"""<workbook>
      <worksheets>
        <worksheet name='S1'>
          <table>
            <panes>
              <pane>
                <encodings>
                  <encoding type='color' field='[Region]'/>
                  <encoding type='size' field='[Sales]'/>
                  <encoding type='color' field='[Region]'/>
                </encodings>
              </pane>
            </panes>
          </table>
        </worksheet>
      </worksheets>
      <dashboards>
        <dashboard name='D1'>
          <zones>
            <zone type-v2='legend/color' id='lz1' name='S1'/>
          </zones>
        </dashboard>
      </dashboards>
    </workbook>"""

    def test_extracts_legend(self):
        root = ET.fromstring(self._LEGEND_XML)
        result = _extract_legends(root)
        assert any(r["encoding_type"] == "color" for r in result)

    def test_deduplicates_encoding_type(self):
        root = ET.fromstring(self._LEGEND_XML)
        result = _extract_legends(root)
        color_count = sum(1 for r in result if r["encoding_type"] == "color")
        assert color_count == 1

    def test_position_from_dashboard_zones(self):
        root = ET.fromstring(self._LEGEND_XML)
        result = _extract_legends(root)
        color_legend = next((r for r in result if r["encoding_type"] == "color"), None)
        assert color_legend is not None
        assert color_legend["position"] is not None

    def test_empty(self):
        assert _extract_legends(ET.fromstring(b"<workbook/>")) == []


# ---------------------------------------------------------------------------
# TestExtractDashboardObjects
# ---------------------------------------------------------------------------

class TestExtractDashboardObjects:
    def test_extracts_text_zone(self):
        root = _root()
        result = _extract_dashboard_objects(root)
        text_objs = [o for o in result if o["object_type"] == "text"]
        assert len(text_objs) >= 1
        assert text_objs[0]["text_content"] == "Hello"

    def test_extracts_web_zone(self):
        root = _root()
        result = _extract_dashboard_objects(root)
        web_objs = [o for o in result if o["object_type"] == "web"]
        assert len(web_objs) >= 1
        assert web_objs[0]["url"] == "http://example.com"

    def test_non_data_type_only(self):
        root = _root()
        result = _extract_dashboard_objects(root)
        for obj in result:
            assert obj["object_type"] in {"text", "bitmap", "image", "web", "blank", "title"}

    def test_empty(self):
        assert _extract_dashboard_objects(ET.fromstring(b"<workbook/>")) == []


# ---------------------------------------------------------------------------
# TestExtractFormatOverrides
# ---------------------------------------------------------------------------

class TestExtractFormatOverrides:
    def test_datasource_format_attr(self):
        root = _root()
        result = _extract_format_overrides(root)
        ds_overrides = [o for o in result if o["scope"] == "datasource"]
        assert any(o["format_string"] == "#,##0" for o in ds_overrides)

    def test_worksheet_format_override(self):
        root = _root()
        result = _extract_format_overrides(root)
        ws_overrides = [o for o in result if o["scope"] == "worksheet"]
        assert any(o["format_string"] == "0.00" for o in ws_overrides)

    def test_empty(self):
        assert _extract_format_overrides(ET.fromstring(b"<workbook/>")) == []


# ---------------------------------------------------------------------------
# TestExtractAnnotations
# ---------------------------------------------------------------------------

class TestExtractAnnotations:
    def test_extracts_annotation(self):
        root = _root()
        result = _extract_annotations(root)
        assert "annotations" in result
        assert "mark_labels" in result
        assert any(a["type"] == "point" for a in result["annotations"])

    def test_mark_labels_present(self):
        root = _root()
        result = _extract_annotations(root)
        assert any(ml["show_mark_labels"] for ml in result["mark_labels"])

    def test_empty(self):
        result = _extract_annotations(ET.fromstring(b"<workbook/>"))
        assert result["annotations"] == []
        assert result["mark_labels"] == []


# ---------------------------------------------------------------------------
# TestExtractTableCalcConfigs
# ---------------------------------------------------------------------------

class TestExtractTableCalcConfigs:
    def test_extracts_table_calc(self):
        xml = b"""<workbook>
          <datasources>
            <datasource name='ds1' caption='DS'>
              <column name='[Running Total]' caption='Running Total' datatype='real'>
                <calculation formula='RUNNING_SUM(SUM([Sales]))' class='tableau'
                  addressing-fields='[Date]' partitioning-fields='[Region]'
                  addressing-type='table_down'/>
              </column>
            </datasource>
          </datasources>
          <worksheets>
            <worksheet name='Chart1'>
              <table>
                <view>
                  <datasources>
                    <datasource name='ds1'/>
                  </datasources>
                </view>
              </table>
            </worksheet>
          </worksheets>
        </workbook>"""
        root = ET.fromstring(xml)
        result = _extract_table_calc_configs(root)
        assert len(result) == 1
        assert result[0]["calc_type"] == "running_total"
        assert "[Date]" in result[0]["addressing_fields"]
        assert result[0]["addressing_type"] == "table_down"

    def test_empty(self):
        assert _extract_table_calc_configs(ET.fromstring(b"<workbook/>")) == []
