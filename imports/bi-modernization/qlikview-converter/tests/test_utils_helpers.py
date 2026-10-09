"""
Tests for all helper functions introduced during the SonarQube cognitive-complexity refactor
of utils.py.  Every test builds minimal ET.Element / XML fixtures inline — no files, no mocks.

Run:
    coverage run -m pytest tests/test_utils_helpers.py -v
    coverage xml -o coverage.xml
    coverage report --include="utils.py"
"""

import xml.etree.ElementTree as ET
import pytest


# ---------------------------------------------------------------------------
# helpers to build XML quickly
# ---------------------------------------------------------------------------

def _xml(text: str) -> ET.Element:
    return ET.fromstring(text)


# ===========================================================================
# 1. MODULE-LEVEL CONSTANTS
# ===========================================================================

class TestConstants:
    def test_ws_panes_path(self):
        from utils import _WS_PANES_PATH
        assert _WS_PANES_PATH == "table/panes/pane"

    def test_title_text_path(self):
        from utils import _TITLE_TEXT_PATH
        assert _TITLE_TEXT_PATH == "title/formatted-text/run"

    def test_all_zones_path(self):
        from utils import _ALL_ZONES_PATH
        assert _ALL_ZONES_PATH == ".//zone"

    def test_all_panes_path(self):
        from utils import _ALL_PANES_PATH
        assert _ALL_PANES_PATH == ".//pane"

    def test_worksheets_path(self):
        from utils import _WORKSHEETS_PATH
        assert _WORKSHEETS_PATH == "worksheets/worksheet"

    def test_geo_latlon_cols(self):
        from utils import _GEO_LATLON_COLS
        assert "[Latitude (generated)]" in _GEO_LATLON_COLS
        assert "[Longitude (generated)]" in _GEO_LATLON_COLS

    def test_geo_roles_contains_country(self):
        from utils import _GEO_ROLES
        assert "[Country].[Name]" in _GEO_ROLES

    def test_encoding_tags(self):
        from utils import _ENCODING_TAGS
        assert "color" in _ENCODING_TAGS
        assert "text" in _ENCODING_TAGS

    def test_non_data_zone_types(self):
        from utils import _NON_DATA_ZONE_TYPES
        for t in ("text", "bitmap", "image", "web", "blank", "title"):
            assert t in _NON_DATA_ZONE_TYPES

    def test_format_attrs(self):
        from utils import _FORMAT_ATTRS
        assert "format" in _FORMAT_ATTRS
        assert "number-format" in _FORMAT_ATTRS
        assert "date-format" in _FORMAT_ATTRS

    def test_refline_format_attrs(self):
        from utils import _REFLINE_FORMAT_ATTRS
        assert "line-style" in _REFLINE_FORMAT_ATTRS
        assert "color" in _REFLINE_FORMAT_ATTRS

    def test_legend_encoding_types(self):
        from utils import _LEGEND_ENCODING_TYPES
        assert "color" in _LEGEND_ENCODING_TYPES
        assert "size" in _LEGEND_ENCODING_TYPES

    def test_table_calc_keywords(self):
        from utils import _TABLE_CALC_KEYWORDS
        assert "RUNNING_" in _TABLE_CALC_KEYWORDS
        assert "RANK" in _TABLE_CALC_KEYWORDS


# ===========================================================================
# 2. _infer_table_calc_type
# ===========================================================================

class TestInferTableCalcType:
    def _call(self, formula):
        from utils import _infer_table_calc_type
        return _infer_table_calc_type(formula.upper())

    def test_running_sum(self):
        assert self._call("RUNNING_SUM(SUM([Sales]))") == "running_total"

    def test_running_avg(self):
        assert self._call("RUNNING_AVG(SUM([Sales]))") == "running_average"

    def test_window_sum(self):
        assert self._call("WINDOW_SUM(SUM([Sales]))") == "window_aggregate"

    def test_window_avg(self):
        assert self._call("WINDOW_AVG(SUM([Sales]))") == "window_aggregate"

    def test_rank(self):
        assert self._call("RANK(SUM([Sales]))") == "rank"

    def test_lookup(self):
        assert self._call("LOOKUP(SUM([Sales]),1)") == "lookup"

    def test_index(self):
        assert self._call("INDEX()") == "index"

    def test_size(self):
        assert self._call("SIZE()") == "size"

    def test_first(self):
        assert self._call("FIRST()") == "first_last"

    def test_last(self):
        assert self._call("LAST()") == "first_last"

    def test_total(self):
        assert self._call("TOTAL(SUM([Sales]))") == "total"

    def test_fallback(self):
        assert self._call("ZN([Sales])") == "table_calculation"


# ===========================================================================
# 3. Reference line helpers
# ===========================================================================

class TestParseRefline:
    def test_parse_refline_formatting_attrs(self):
        from utils import _parse_refline_formatting
        rl = _xml('<refline type="line" color="red" line-style="dashed"/>')
        result = _parse_refline_formatting(rl)
        assert result["color"] == "red"
        assert result["line-style"] == "dashed"

    def test_parse_refline_formatting_child_formats(self):
        from utils import _parse_refline_formatting
        rl = _xml('<refline><format attr="thickness" value="2"/></refline>')
        result = _parse_refline_formatting(rl)
        assert result["thickness"] == "2"

    def test_parse_refline_empty_formatting(self):
        from utils import _parse_refline_formatting
        rl = _xml('<refline/>')
        assert _parse_refline_formatting(rl) == {}

    def test_parse_refline_full_dict(self):
        from utils import _parse_refline
        rl = _xml('<reference-line type="band" column="Sales" value="AVG" label="Average"/>')
        result = _parse_refline("Sheet1", rl)
        assert result["worksheet"] == "Sheet1"
        assert result["reference_type"] == "band"
        assert result["axis_or_field"] == "Sales"
        assert result["value"] == "AVG"
        assert result["label"] == "Average"

    def test_parse_refline_defaults(self):
        from utils import _parse_refline
        rl = _xml('<reference-line/>')
        result = _parse_refline("WS", rl)
        assert result["reference_type"] == "line"
        assert result["axis_or_field"] == ""
        assert result["label"] == ""


# ===========================================================================
# 4. Color encoding helpers
# ===========================================================================

class TestParseColorEncoding:
    def test_returns_none_when_no_field_no_palette(self):
        from utils import _parse_color_encoding
        enc = _xml('<encoding attr="color"/>')
        assert _parse_color_encoding("WS", enc) is None

    def test_returns_dict_with_field(self):
        from utils import _parse_color_encoding
        enc = _xml('<encoding attr="color" field="[Category]" palette="reds" steps="5"/>')
        result = _parse_color_encoding("WS", enc)
        assert result is not None
        assert result["field"] == "[Category]"
        assert result["palette_name"] == "reds"
        assert result["color_steps"] == 5
        assert result["worksheet"] == "WS"

    def test_stepped_fallback_when_no_type(self):
        from utils import _parse_color_encoding
        enc = _xml('<encoding attr="color" field="[Sales]" steps="3"/>')
        result = _parse_color_encoding("WS", enc)
        assert result["encoding_type"] == "stepped"

    def test_continuous_fallback_when_no_steps(self):
        from utils import _parse_color_encoding
        enc = _xml('<encoding attr="color" field="[Sales]"/>')
        result = _parse_color_encoding("WS", enc)
        assert result["encoding_type"] == "continuous"

    def test_range_values_extracted(self):
        from utils import _parse_color_encoding
        enc = _xml('<encoding attr="color" field="[Sales]"><range min="0" max="100" mid="50"/></encoding>')
        result = _parse_color_encoding("WS", enc)
        assert result["min_value"] == "0"
        assert result["max_value"] == "100"
        assert result["mid_value"] == "50"

    def test_reversed_flag(self):
        from utils import _parse_color_encoding
        enc = _xml('<encoding attr="color" field="[Sales]" reversed="true"/>')
        result = _parse_color_encoding("WS", enc)
        assert result["reversed"] is True

    def test_legacy_returns_none_when_empty(self):
        from utils import _parse_legacy_color_encoding
        ce = _xml('<color-encoding/>')
        assert _parse_legacy_color_encoding("WS", ce) is None

    def test_legacy_returns_dict(self):
        from utils import _parse_legacy_color_encoding
        ce = _xml('<color-encoding field="[Region]" palette="blues" reversed="false"/>')
        result = _parse_legacy_color_encoding("WS", ce)
        assert result["encoding_type"] == "color_encoding"
        assert result["field"] == "[Region]"
        assert result["color_steps"] is None
        assert result["reversed"] is False


# ===========================================================================
# 5. Trend line / forecast helpers
# ===========================================================================

class TestTrendLineParsing:
    def test_parse_trend_line_basic(self):
        from utils import _parse_trend_line
        tl = _xml('<trend-line type="linear" show-confidence-bands="true" show-recalculated-line="false"/>')
        result = _parse_trend_line("WS1", tl)
        assert result["worksheet"] == "WS1"
        assert result["type"] == "trend"
        assert result["model_type"] == "linear"
        assert result["confidence_bands"] is True
        assert result["show_recalculated"] is False
        assert result["fields"] == []

    def test_parse_trend_line_with_fields(self):
        from utils import _parse_trend_line
        tl = _xml('<trend-line><field column="[Sales]"/><field column="[Profit]"/></trend-line>')
        result = _parse_trend_line("WS1", tl)
        assert "[Sales]" in result["fields"]
        assert "[Profit]" in result["fields"]

    def test_parse_trend_line_default_model(self):
        from utils import _parse_trend_line
        tl = _xml('<trend-line/>')
        result = _parse_trend_line("WS", tl)
        assert result["model_type"] == "linear"

    def test_parse_forecast_with_options(self):
        from utils import _parse_forecast
        fc = _xml('<forecast><forecast-options forecast-forward="4" forecast-granularity="quarter" show-prediction-intervals="true"/></forecast>')
        result = _parse_forecast("WS", fc)
        assert result["type"] == "forecast"
        assert result["model_type"] == "exponential_smoothing"
        assert result["forecast_periods"] == "4"
        assert result["forecast_granularity"] == "quarter"
        assert result["confidence_bands"] is True

    def test_parse_forecast_without_options(self):
        from utils import _parse_forecast
        fc = _xml('<forecast/>')
        result = _parse_forecast("WS", fc)
        assert result["forecast_periods"] is None
        assert result["forecast_granularity"] is None
        assert result["confidence_bands"] is False


# ===========================================================================
# 6. Dual axis helpers
# ===========================================================================

class TestDualAxisHelpers:
    def test_get_title_text_present(self):
        from utils import _get_title_text
        el = _xml('<axis><title><formatted-text><run>My Axis</run></formatted-text></title></axis>')
        assert _get_title_text(el) == "My Axis"

    def test_get_title_text_missing(self):
        from utils import _get_title_text
        el = _xml('<axis/>')
        assert _get_title_text(el) == ""

    def test_collect_dual_axis_titles(self):
        from utils import _collect_dual_axis_titles
        pane = _xml('''<pane>
            <customized-axis><title><formatted-text><run>Primary</run></formatted-text></title></customized-axis>
            <axis><title><formatted-text><run>Secondary</run></formatted-text></title></axis>
        </pane>''')
        titles = _collect_dual_axis_titles([pane])
        assert "Primary" in titles
        assert "Secondary" in titles

    def test_collect_dual_axis_titles_skips_empty(self):
        from utils import _collect_dual_axis_titles
        pane = _xml('<pane><axis/></pane>')
        titles = _collect_dual_axis_titles([pane])
        assert titles == []

    def test_get_row_fields_with_data(self):
        from utils import _get_row_fields
        table = _xml('<table><view><rows>AGG([Sales]) AGG([Profit]</rows></view></table>')
        fields = _get_row_fields(table)
        assert len(fields) >= 1

    def test_get_row_fields_no_view(self):
        from utils import _get_row_fields
        table = _xml('<table/>')
        assert _get_row_fields(table) == []

    def test_get_row_fields_no_rows(self):
        from utils import _get_row_fields
        table = _xml('<table><view/></table>')
        assert _get_row_fields(table) == []

    def test_is_dual_axis_by_row_count(self):
        from utils import _is_dual_axis
        assert _is_dual_axis([], ["field1", "field2"]) is True

    def test_is_dual_axis_by_pane_type(self):
        from utils import _is_dual_axis
        pane = _xml('<pane type="dual"/>')
        assert _is_dual_axis([pane], []) is True

    def test_is_dual_axis_by_axis_element(self):
        from utils import _is_dual_axis
        pane = _xml('<pane><axis type="dual"/></pane>')
        assert _is_dual_axis([pane], []) is True

    def test_is_not_dual_axis(self):
        from utils import _is_dual_axis
        pane = _xml('<pane/>')
        assert _is_dual_axis([pane], ["only_one"]) is False


# ===========================================================================
# 7. Dashboard zone helpers
# ===========================================================================

class TestDashboardZonesHelpers:
    def test_parse_zone_style_builds_dict(self):
        from utils import _parse_zone_style
        z = _xml('<zone><zone-style><format attr="background-color" value="#fff"/><format attr="border" value="1"/></zone-style></zone>')
        style = _parse_zone_style(z)
        assert style["background-color"] == "#fff"
        assert style["border"] == "1"

    def test_parse_zone_style_empty(self):
        from utils import _parse_zone_style
        z = _xml('<zone/>')
        assert _parse_zone_style(z) == {}

    def test_parse_structured_zone_returns_none_for_missing_id(self):
        from utils import _parse_structured_zone
        z = _xml('<zone name="Chart1"/>')
        assert _parse_structured_zone(z) is None

    def test_parse_structured_zone_returns_dict(self):
        from utils import _parse_structured_zone
        z = _xml('<zone id="10" type-v2="text" name="Header" x="0" y="0" w="100" h="50"/>')
        result = _parse_structured_zone(z)
        assert result is not None
        assert result["id"] == "10"
        assert result["type"] == "text"
        assert result["name"] == "Header"

    def test_parse_structured_zone_position(self):
        from utils import _parse_structured_zone
        z = _xml('<zone id="5" x="10" y="20" w="200" h="100"/>')
        result = _parse_structured_zone(z)
        assert result["x"] == "10"
        assert result["w"] == "200"

    def test_collect_dashboard_zones_deduplicates(self):
        from utils import _collect_dashboard_zones
        dash = _xml('''<dashboard>
            <zone id="1" name="A"/>
            <zone id="1" name="A_dup"/>
            <zone id="2" name="B"/>
        </dashboard>''')
        zones = _collect_dashboard_zones(dash)
        ids = [z["id"] for z in zones]
        assert ids.count("1") == 1

    def test_collect_dashboard_zones_skips_missing_id(self):
        from utils import _collect_dashboard_zones
        dash = _xml('<dashboard><zone name="NoId"/><zone id="3" name="HasId"/></dashboard>')
        zones = _collect_dashboard_zones(dash)
        assert all(z["id"] for z in zones)


# ===========================================================================
# 8. Groups and sets helpers
# ===========================================================================

class TestGroupsAndSets:
    def test_parse_groupfilter_members_flat_top_level(self):
        from utils import _parse_groupfilter_members_flat
        group = _xml('<group><groupfilter function="member" member="East"/></group>')
        members = _parse_groupfilter_members_flat(group)
        assert len(members) == 1
        assert members[0]["member"] == "East"

    def test_parse_groupfilter_members_flat_nested(self):
        from utils import _parse_groupfilter_members_flat
        group = _xml('''<group>
            <groupfilter function="union">
                <groupfilter function="member" member="East"/>
                <groupfilter function="member" member="West"/>
            </groupfilter>
        </group>''')
        members = _parse_groupfilter_members_flat(group)
        member_vals = [m["member"] for m in members]
        assert "East" in member_vals
        assert "West" in member_vals

    def test_parse_groupfilter_members_flat_empty(self):
        from utils import _parse_groupfilter_members_flat
        group = _xml('<group/>')
        assert _parse_groupfilter_members_flat(group) == []

    def test_parse_groupfilter_skips_no_member(self):
        from utils import _parse_groupfilter_members_flat
        group = _xml('<group><groupfilter function="union"/></group>')
        members = _parse_groupfilter_members_flat(group)
        assert members == []


# ===========================================================================
# 9. Worksheet helpers
# ===========================================================================

class TestWorksheetHelpers:
    def test_parse_shelves_from_table_level(self):
        from utils import _parse_shelves
        table = _xml('<table><rows>AGG([Sales]</rows><cols>AGG([Cat]</cols></table>')
        shelves = _parse_shelves(table)
        assert "rows" in shelves
        assert "cols" in shelves

    def test_parse_shelves_from_view_level(self):
        from utils import _parse_shelves
        table = _xml('<table><view><rows>AGG([Sales]</rows></view></table>')
        shelves = _parse_shelves(table)
        assert "rows" in shelves

    def test_parse_shelves_empty(self):
        from utils import _parse_shelves
        table = _xml('<table/>')
        assert _parse_shelves(table) == {}

    def test_parse_pane_encodings_standard(self):
        from utils import _parse_pane_encodings
        pane = _xml('<pane><encodings><encoding attr="color" type="categorical"/></encodings></pane>')
        info = _parse_pane_encodings(pane)
        assert info.get("color") == "categorical"

    def test_parse_pane_encodings_shorthand(self):
        from utils import _parse_pane_encodings
        pane = _xml('<pane><encodings><text column="[Label]"/></encodings></pane>')
        info = _parse_pane_encodings(pane)
        assert info.get("text") == "[Label]"

    def test_parse_pane_encodings_empty(self):
        from utils import _parse_pane_encodings
        pane = _xml('<pane/>')
        assert _parse_pane_encodings(pane) == {}

    def test_parse_sorts_basic(self):
        from utils import _parse_sorts
        ws = _xml('<worksheet/>')
        table = _xml('<table><sort column="Sales" direction="desc"/></table>')
        sorts = _parse_sorts(ws, table)
        assert any(s["column"] == "Sales" for s in sorts)

    def test_parse_sorts_shelf_sort_v2(self):
        from utils import _parse_sorts
        ws = _xml('''<worksheet>
            <table><view><shelf-sorts>
                <shelf-sort-v2 dimension-to-sort="[Cat]" direction="asc" measure-to-sort-by="[Sales]" shelf="rows"/>
            </shelf-sorts></view></table>
        </worksheet>''')
        table = ws.find("table")
        sorts = _parse_sorts(ws, table)
        assert any(s.get("sort_type") == "measure" for s in sorts)

    def test_parse_sorts_manual(self):
        from utils import _parse_sorts
        ws = _xml('''<worksheet>
            <table><view><manual-sort column="[Cat]" direction="asc">
                <dictionary><bucket>"rock"</bucket><bucket>"jazz"</bucket></dictionary>
            </manual-sort></view></table>
        </worksheet>''')
        table = ws.find("table")
        sorts = _parse_sorts(ws, table)
        manual = [s for s in sorts if s.get("sort_type") == "manual"]
        assert len(manual) == 1
        assert "rock" in manual[0]["ordered_values"]

    def test_parse_style_rules_worksheet_level(self):
        from utils import _parse_style_rules
        ws = _xml('''<worksheet>
            <style>
                <style-rule element="cell">
                    <format attr="font-size" value="12"/>
                </style-rule>
            </style>
        </worksheet>''')
        rules = _parse_style_rules(ws, None)
        assert any(r["attr"] == "font-size" for r in rules)

    def test_parse_style_rules_pane_level(self):
        from utils import _parse_style_rules
        ws = _xml('<worksheet/>')
        table = _xml('''<table>
            <pane>
                <style>
                    <style-rule element="mark">
                        <format attr="mark-labels-show" value="true"/>
                    </style-rule>
                </style>
            </pane>
        </table>''')
        rules = _parse_style_rules(ws, table)
        pane_rules = [r for r in rules if r.get("scope") == "pane"]
        assert len(pane_rules) >= 1

    def test_detect_lat_lon_via_column_instance(self):
        from utils import _detect_lat_lon
        ws = _xml('''<worksheet>
            <table><view>
                <datasource-dependencies>
                    <column-instance column="[Latitude (generated)]"/>
                </datasource-dependencies>
            </view></table>
        </worksheet>''')
        assert _detect_lat_lon(ws) is True

    def test_detect_lat_lon_via_column(self):
        from utils import _detect_lat_lon
        ws = _xml('''<worksheet>
            <table><view>
                <datasource-dependencies>
                    <column name="[Longitude (generated)]"/>
                </datasource-dependencies>
            </view></table>
        </worksheet>''')
        assert _detect_lat_lon(ws) is True

    def test_detect_lat_lon_false(self):
        from utils import _detect_lat_lon
        ws = _xml('<worksheet><table><view><datasource-dependencies><column name="[Sales]"/></datasource-dependencies></view></table></worksheet>')
        assert _detect_lat_lon(ws) is False

    def test_detect_geo_fields_true(self):
        from utils import _detect_geo_fields
        ws = _xml('''<worksheet>
            <table><view>
                <datasource-dependencies>
                    <column semantic-role="[Country].[Name]"/>
                </datasource-dependencies>
            </view></table>
        </worksheet>''')
        assert _detect_geo_fields(ws) is True

    def test_detect_geo_fields_false(self):
        from utils import _detect_geo_fields
        ws = _xml('<worksheet><table><view><datasource-dependencies><column semantic-role="other"/></datasource-dependencies></view></table></worksheet>')
        assert _detect_geo_fields(ws) is False


# ===========================================================================
# 10. Format overrides helpers
# ===========================================================================

class TestFormatOverrides:
    def test_collect_datasource_format_overrides_inline(self):
        from utils import _collect_datasource_format_overrides
        root = _xml('''<workbook>
            <datasources>
                <datasource name="ds1" caption="DS One">
                    <column name="[Sales]" format="#,##0"/>
                </datasource>
            </datasources>
        </workbook>''')
        overrides = _collect_datasource_format_overrides(root)
        assert any(o["format_string"] == "#,##0" for o in overrides)
        assert all(o["scope"] == "datasource" for o in overrides)

    def test_collect_datasource_format_overrides_child_format(self):
        from utils import _collect_datasource_format_overrides
        root = _xml('''<workbook>
            <datasources>
                <datasource name="ds1" caption="DS1">
                    <column name="[Profit]">
                        <format value="0.00%"/>
                    </column>
                </datasource>
            </datasources>
        </workbook>''')
        overrides = _collect_datasource_format_overrides(root)
        assert any(o["format_string"] == "0.00%" for o in overrides)

    def test_collect_worksheet_format_overrides(self):
        from utils import _collect_worksheet_format_overrides
        root = _xml('''<workbook>
            <worksheets>
                <worksheet name="Sheet1">
                    <style>
                        <style-rule element="cell">
                            <format attr="number-format" value="$#,##0"/>
                        </style-rule>
                    </style>
                </worksheet>
            </worksheets>
        </workbook>''')
        overrides = _collect_worksheet_format_overrides(root)
        assert any(o["format_string"] == "$#,##0" for o in overrides)
        assert all(o["scope"] == "worksheet" for o in overrides)

    def test_collect_worksheet_format_overrides_skips_non_format_attrs(self):
        from utils import _collect_worksheet_format_overrides
        root = _xml('''<workbook>
            <worksheets>
                <worksheet name="Sheet1">
                    <style>
                        <style-rule element="cell">
                            <format attr="font-size" value="12"/>
                        </style-rule>
                    </style>
                </worksheet>
            </worksheets>
        </workbook>''')
        overrides = _collect_worksheet_format_overrides(root)
        assert overrides == []

    def test_collect_worksheet_format_overrides_skips_no_style(self):
        from utils import _collect_worksheet_format_overrides
        root = _xml('<workbook><worksheets><worksheet name="Sheet1"/></worksheets></workbook>')
        assert _collect_worksheet_format_overrides(root) == []


# ===========================================================================
# 11. Annotation helpers
# ===========================================================================

class TestAnnotationHelpers:
    def test_collect_fmt_dict(self):
        from utils import _collect_fmt_dict
        parent = _xml('<parent><format attr="color" value="red"/><format attr="size" value="10"/></parent>')
        d = _collect_fmt_dict(parent)
        assert d["color"] == "red"
        assert d["size"] == "10"

    def test_collect_fmt_dict_skips_empty_attr(self):
        from utils import _collect_fmt_dict
        parent = _xml('<parent><format value="red"/></parent>')
        d = _collect_fmt_dict(parent)
        assert d == {}

    def test_collect_pane_annotations_all_types(self):
        from utils import _collect_pane_annotations
        pane = _xml('''<pane>
            <point-annotation x="1" y="2"><formatted-text><run>Point</run></formatted-text></point-annotation>
            <mark-annotation x="3" y="4"><formatted-text><run>Mark</run></formatted-text></mark-annotation>
            <area-annotation x="5" y="6"><formatted-text><run>Area</run></formatted-text></area-annotation>
        </pane>''')
        anns = _collect_pane_annotations("WS1", pane)
        types = {a["type"] for a in anns}
        assert types == {"point", "mark", "area"}

    def test_collect_pane_annotations_text_extracted(self):
        from utils import _collect_pane_annotations
        pane = _xml('<pane><point-annotation><formatted-text><run>Hello</run></formatted-text></point-annotation></pane>')
        anns = _collect_pane_annotations("WS", pane)
        assert anns[0]["text"] == "Hello"

    def test_collect_pane_annotations_empty_pane(self):
        from utils import _collect_pane_annotations
        pane = _xml('<pane/>')
        assert _collect_pane_annotations("WS", pane) == []

    def test_mark_label_from_element_show_true(self):
        from utils import _mark_label_from_element
        ml = _xml('<mark-labels show-mark-labels="true"/>')
        result = _mark_label_from_element("WS", ml)
        assert result["show_mark_labels"] is True
        assert result["worksheet"] == "WS"

    def test_mark_label_from_element_show_false(self):
        from utils import _mark_label_from_element
        ml = _xml('<mark-labels enabled="false"/>')
        result = _mark_label_from_element("WS", ml)
        assert result["show_mark_labels"] is False

    def test_mark_label_from_style_rule_returns_none_when_not_shown(self):
        from utils import _mark_label_from_style_rule
        rule = _xml('<style-rule element="mark"><format attr="font-size" value="10"/></style-rule>')
        assert _mark_label_from_style_rule("WS", rule) is None

    def test_mark_label_from_style_rule_returns_dict_when_shown(self):
        from utils import _mark_label_from_style_rule
        rule = _xml('<style-rule element="mark"><format attr="mark-labels-show" value="true"/></style-rule>')
        result = _mark_label_from_style_rule("WS", rule)
        assert result is not None
        assert result["show_mark_labels"] is True

    def test_collect_ws_mark_labels_from_element(self):
        from utils import _collect_ws_mark_labels
        ws = _xml('''<worksheet name="WS">
            <table><panes>
                <pane><mark-labels show-mark-labels="true"/></pane>
            </panes></table>
        </worksheet>''')
        labels = _collect_ws_mark_labels("WS", ws)
        assert len(labels) >= 1
        assert labels[0]["show_mark_labels"] is True

    def test_collect_ws_mark_labels_fallback_to_style_rule(self):
        from utils import _collect_ws_mark_labels
        ws = _xml('''<worksheet name="WS">
            <table><panes><pane>
                <style>
                    <style-rule element="mark">
                        <format attr="mark-labels-show" value="true"/>
                    </style-rule>
                </style>
            </pane></panes></table>
        </worksheet>''')
        labels = _collect_ws_mark_labels("WS", ws)
        assert len(labels) >= 1


# ===========================================================================
# 12. Legend helpers
# ===========================================================================

class TestLegendHelpers:
    def test_collect_legend_positions(self):
        from utils import _collect_legend_positions
        root = _xml('''<workbook>
            <dashboards>
                <dashboard name="D1">
                    <zone type-v2="color-legend" name="Sheet1"/>
                </dashboard>
            </dashboards>
        </workbook>''')
        positions = _collect_legend_positions(root)
        assert "Sheet1" in positions
        assert positions["Sheet1"] == "color-legend"

    def test_collect_legend_positions_ignores_non_legend_zones(self):
        from utils import _collect_legend_positions
        root = _xml('<workbook><dashboards><dashboard><zone type-v2="text" name="T1"/></dashboard></dashboards></workbook>')
        assert _collect_legend_positions(root) == {}

    def test_collect_ws_legends_filters_types(self):
        from utils import _collect_ws_legends
        ws = _xml('''<worksheet name="WS">
            <table><panes><pane><encodings>
                <encoding type="color" field="[Cat]"/>
                <encoding type="other" field="[X]"/>
            </encodings></pane></panes></table>
        </worksheet>''')
        legends = _collect_ws_legends("WS", ws, {})
        assert all(l["encoding_type"] in ("color", "size", "shape", "label", "detail") for l in legends)

    def test_collect_ws_legends_deduplicates(self):
        from utils import _collect_ws_legends
        ws = _xml('''<worksheet name="WS">
            <table><panes>
                <pane><encodings><encoding type="color" field="[Cat]"/></encodings></pane>
                <pane><encodings><encoding type="color" field="[Cat2]"/></encodings></pane>
            </panes></table>
        </worksheet>''')
        legends = _collect_ws_legends("WS", ws, {})
        color_legends = [l for l in legends if l["encoding_type"] == "color"]
        assert len(color_legends) == 1

    def test_collect_ws_legends_includes_position(self):
        from utils import _collect_ws_legends
        ws = _xml('<worksheet name="WS"><table><panes><pane><encodings><encoding type="color" field="[C]"/></encodings></pane></panes></table></worksheet>')
        legends = _collect_ws_legends("WS", ws, {"WS": "color-legend"})
        assert legends[0]["position"] == "color-legend"


# ===========================================================================
# 13. Axes helpers
# ===========================================================================

class TestAxesHelpers:
    def test_axes_from_style_rules_title(self):
        from utils import _axes_from_style_rules
        ws = _xml('''<worksheet name="WS">
            <style>
                <style-rule element="axis">
                    <format attr="title" value="Sales Axis" field="[Sales]" scope="rows"/>
                </style-rule>
            </style>
        </worksheet>''')
        axes = _axes_from_style_rules("WS", ws)
        assert len(axes) == 1
        assert axes[0]["title"] == "Sales Axis"
        assert axes[0]["field"] == "[Sales]"

    def test_axes_from_style_rules_table_style(self):
        from utils import _axes_from_style_rules
        ws = _xml('''<worksheet name="WS">
            <table>
                <style>
                    <style-rule element="axis">
                        <format attr="title" value="Table Axis" field="[Profit]"/>
                    </style-rule>
                </style>
            </table>
        </worksheet>''')
        axes = _axes_from_style_rules("WS", ws)
        assert any(a["title"] == "Table Axis" for a in axes)

    def test_axes_from_style_rules_empty(self):
        from utils import _axes_from_style_rules
        ws = _xml('<worksheet/>')
        assert _axes_from_style_rules("WS", ws) == []

    def test_axes_from_pane_axis_elements(self):
        from utils import _axes_from_pane_axis_elements
        ws = _xml('''<worksheet name="WS">
            <table><panes><pane>
                <axis column="[Sales]" reversed="true" logarithmic="false">
                    <range min="0" max="1000"/>
                </axis>
            </pane></panes></table>
        </worksheet>''')
        axes = _axes_from_pane_axis_elements("WS", ws)
        assert len(axes) == 1
        assert axes[0]["field"] == "[Sales]"
        assert axes[0]["reversed"] is True
        assert axes[0]["range_min"] == "0"
        assert axes[0]["range_max"] == "1000"

    def test_axes_from_customized_axis(self):
        from utils import _axes_from_customized_axis
        ws = _xml('''<worksheet name="WS">
            <table><panes><pane>
                <customized-axis column="[Profit]" reversed="false" logarithmic="true">
                    <range min="-100" max="500"/>
                </customized-axis>
            </pane></panes></table>
        </worksheet>''')
        axes = _axes_from_customized_axis("WS", ws)
        assert len(axes) == 1
        assert axes[0]["field"] == "[Profit]"
        assert axes[0]["logarithmic"] is True
        assert axes[0]["range_min"] == "-100"

    def test_axes_from_pane_empty(self):
        from utils import _axes_from_pane_axis_elements
        ws = _xml('<worksheet/>')
        assert _axes_from_pane_axis_elements("WS", ws) == []


# ===========================================================================
# 14. Dashboard action helpers
# ===========================================================================

class TestDashboardActionsHelpers:
    def test_collect_action_sheets_from_children(self):
        from utils import _collect_action_sheets
        action = _xml('<action><source-sheet sheet="Sheet1"/><source-sheet sheet="Sheet2"/></action>')
        sheets = _collect_action_sheets(action, "source-sheet", "source-sheets")
        assert "Sheet1" in sheets
        assert "Sheet2" in sheets

    def test_collect_action_sheets_from_bulk_attr(self):
        from utils import _collect_action_sheets
        action = _xml('<action source-sheets="SheetA, SheetB, SheetC"/>')
        sheets = _collect_action_sheets(action, "source-sheet", "source-sheets")
        assert "SheetA" in sheets
        assert "SheetC" in sheets

    def test_collect_action_sheets_combined(self):
        from utils import _collect_action_sheets
        action = _xml('<action source-sheets="SheetX"><source-sheet sheet="SheetY"/></action>')
        sheets = _collect_action_sheets(action, "source-sheet", "source-sheets")
        assert "SheetX" in sheets
        assert "SheetY" in sheets

    def test_collect_action_sheets_empty(self):
        from utils import _collect_action_sheets
        action = _xml('<action/>')
        assert _collect_action_sheets(action, "source-sheet", "source-sheets") == []

    def test_parse_dashboard_action_full(self):
        from utils import _parse_dashboard_action
        action = _xml('''<action name="Filter1" type="filter" url="" activation="select">
            <source-sheet sheet="SheetA"/>
            <target-sheet sheet="SheetB"/>
            <field-mapping source-field="[Region]" target-field="[Region]"/>
        </action>''')
        result = _parse_dashboard_action("Dash1", action)
        assert result["dashboard"] == "Dash1"
        assert result["name"] == "Filter1"
        assert result["type"] == "filter"
        assert "SheetA" in result["source_worksheets"]
        assert "SheetB" in result["target_worksheets"]
        assert result["field_mappings"][0]["source"] == "[Region]"
        assert result["activation"] == "select"

    def test_parse_dashboard_action_none_url(self):
        from utils import _parse_dashboard_action
        action = _xml('<action name="A" type="highlight"/>')
        result = _parse_dashboard_action("D", action)
        assert result["url"] is None

    def test_parse_dashboard_action_none_activation(self):
        from utils import _parse_dashboard_action
        action = _xml('<action name="A" type="highlight"/>')
        result = _parse_dashboard_action("D", action)
        assert result["activation"] is None


# ===========================================================================
# 15. Zone object helpers
# ===========================================================================

class TestZoneObjectHelpers:
    def test_parse_zone_object_returns_none_for_missing_id(self):
        from utils import _parse_zone_object
        z = _xml('<zone type-v2="text" name="Header"/>')
        assert _parse_zone_object("Dash", z) is None

    def test_parse_zone_object_returns_none_for_non_data_type(self):
        from utils import _parse_zone_object
        z = _xml('<zone id="5" type-v2="worksheet" name="Chart"/>')
        assert _parse_zone_object("Dash", z) is None

    def test_parse_zone_object_text_zone(self):
        from utils import _parse_zone_object
        z = _xml('<zone id="1" type-v2="text" x="0" y="0" w="100" h="50"><formatted-text><run>Hello</run></formatted-text></zone>')
        result = _parse_zone_object("Dash", z)
        assert result is not None
        assert result["object_type"] == "text"
        assert result["text_content"] == "Hello"
        assert result["dashboard"] == "Dash"

    def test_parse_zone_object_web_zone_url(self):
        from utils import _parse_zone_object
        z = _xml('<zone id="2" type-v2="web" url="http://example.com" x="0" y="0" w="0" h="0"/>')
        result = _parse_zone_object("Dash", z)
        assert result["url"] == "http://example.com"

    def test_parse_zone_object_position(self):
        from utils import _parse_zone_object
        z = _xml('<zone id="3" type-v2="blank" x="10" y="20" w="300" h="150"/>')
        result = _parse_zone_object("Dash", z)
        assert result["position"]["x"] == 10
        assert result["position"]["width"] == 300


# ===========================================================================
# 16. Enrich helpers (integration)
# ===========================================================================

class TestEnrichHelpers:
    def test_build_and_enrich_worksheets_adds_keys(self):
        from utils import _build_and_enrich_worksheets
        ws = {"name": "Sheet1"}
        tooltips = [{"worksheet": "Sheet1", "formatted_text": "tip", "field_references": []}]
        annotations_data = {"annotations": [], "mark_labels": []}
        _build_and_enrich_worksheets(
            [ws], tooltips, [], [], [], annotations_data, [], [], [], [], []
        )
        assert "tooltip" in ws
        assert ws["tooltip"]["formatted_text"] == "tip"
        assert "reference_lines" in ws
        assert "axes" in ws
        assert "highlight_fields" in ws

    def test_build_and_enrich_worksheets_missing_ws(self):
        from utils import _build_and_enrich_worksheets
        ws = {"name": "OtherSheet"}
        annotations_data = {"annotations": [], "mark_labels": []}
        _build_and_enrich_worksheets([ws], [], [], [], [], annotations_data, [], [], [], [], [])
        assert ws["tooltip"] is None
        assert ws["highlight_fields"] == []

    def test_enrich_dashboards_adds_actions(self):
        from utils import _enrich_dashboards
        dash = {"internal_name": "Dash1"}
        actions = [{"dashboard": "Dash1", "name": "Filter", "type": "filter"}]
        objects = [{"dashboard": "Dash1", "zone_id": "1"}]
        _enrich_dashboards([dash], actions, objects)
        assert len(dash["actions"]) == 1
        assert len(dash["dashboard_objects"]) == 1

    def test_enrich_dashboards_empty(self):
        from utils import _enrich_dashboards
        dash = {"internal_name": "Dash1"}
        _enrich_dashboards([dash], [], [])
        assert dash["actions"] == []
        assert dash["dashboard_objects"] == []

    def test_merge_zone_worksheet_data(self):
        from utils import _merge_zone_worksheet_data
        ws_data = {"name": "Chart1", "shelves": {"rows": ["Sales"]}, "marks": [], "panes": [],
                   "sorts": [], "style_rules": [], "datasource_dependencies": [],
                   "tooltip": None, "reference_lines": [], "axes": [], "legends": [],
                   "annotations": [], "mark_labels": None, "dual_axis": None,
                   "trend_lines": [], "table_calc_configs": [], "conditional_formatting": [],
                   "has_generated_lat_lon": False, "has_geographic_fields": False}
        dash = {"internal_name": "D1", "zones": [{"name": "Chart1", "type": ""}]}
        _merge_zone_worksheet_data([dash], {"Chart1": ws_data})
        assert "worksheet_data" in dash["zones"][0]
        assert dash["zones"][0]["worksheet_data"]["shelves"] == {"rows": ["Sales"]}

    def test_merge_zone_skips_filter_zones(self):
        from utils import _merge_zone_worksheet_data
        ws_data = {"name": "Sheet1"}
        dash = {"internal_name": "D1", "zones": [{"name": "Sheet1", "type": "filter"}]}
        _merge_zone_worksheet_data([dash], {"Sheet1": ws_data})
        assert "worksheet_data" not in dash["zones"][0]

    def test_merge_zone_skips_text_zones(self):
        from utils import _merge_zone_worksheet_data
        ws_data = {"name": "Sheet1"}
        dash = {"internal_name": "D1", "zones": [{"name": "Sheet1", "type": "text"}]}
        _merge_zone_worksheet_data([dash], {"Sheet1": ws_data})
        assert "worksheet_data" not in dash["zones"][0]


# ===========================================================================
# 17. preprocess_workbook — end-to-end
# ===========================================================================

_MINIMAL_TWB = b'''<?xml version="1.0" encoding="utf-8"?>
<workbook source-build="2021.1.0">
  <datasources>
    <datasource name="ds1" caption="My Data">
      <connection class="excel-direct">
        <named-connections>
          <named-connection name="conn1">
            <connection class="excel-direct" filename="data.xlsx"/>
          </named-connection>
        </named-connections>
      </connection>
    </datasource>
  </datasources>
  <worksheets>
    <worksheet name="Sheet1">
      <simple-id uuid="{abc-123}"/>
      <table>
        <view>
          <datasources><datasource name="ds1" caption="My Data"/></datasources>
          <rows>AGG([Sales]</rows>
          <cols>AGG([Category]</cols>
        </view>
        <panes><pane/></panes>
      </table>
    </worksheet>
  </worksheets>
  <dashboards>
    <dashboard name="Dash1">
      <simple-id uuid="{dash-001}"/>
      <size maxwidth="1000" maxheight="800"/>
      <zone id="1" name="Sheet1" x="0" y="0" w="500" h="400"/>
    </dashboard>
  </dashboards>
  <windows>
    <window class="worksheet" name="Sheet1"/>
  </windows>
</workbook>'''


class TestPreprocessWorkbook:
    def test_returns_tableau_workbook_context(self):
        from utils import preprocess_workbook, TableauWorkbookContext
        ctx = preprocess_workbook(_MINIMAL_TWB)
        assert isinstance(ctx, TableauWorkbookContext)

    def test_model_has_required_keys(self):
        from utils import preprocess_workbook
        ctx = preprocess_workbook(_MINIMAL_TWB)
        for key in ("datasources", "tables", "calculations", "filters", "hierarchies"):
            assert key in ctx.model

    def test_visuals_has_required_keys(self):
        from utils import preprocess_workbook
        ctx = preprocess_workbook(_MINIMAL_TWB)
        for key in ("worksheets", "dashboards", "sheets", "dashboard_filters"):
            assert key in ctx.visuals

    def test_presentation_has_required_keys(self):
        from utils import preprocess_workbook
        ctx = preprocess_workbook(_MINIMAL_TWB)
        for key in ("styles", "thumbnails", "windows"):
            assert key in ctx.presentation

    def test_worksheets_populated(self):
        from utils import preprocess_workbook
        ctx = preprocess_workbook(_MINIMAL_TWB)
        assert len(ctx.visuals["worksheets"]) == 1
        assert ctx.visuals["worksheets"][0]["name"] == "Sheet1"

    def test_dashboards_populated(self):
        from utils import preprocess_workbook
        ctx = preprocess_workbook(_MINIMAL_TWB)
        assert len(ctx.visuals["dashboards"]) == 1

    def test_zone_worksheet_data_merged(self):
        from utils import preprocess_workbook
        ctx = preprocess_workbook(_MINIMAL_TWB)
        dash = ctx.visuals["dashboards"][0]
        zones_with_data = [z for z in dash.get("zones", []) if "worksheet_data" in z]
        assert len(zones_with_data) >= 1

    def test_invalid_xml_raises_value_error(self):
        from utils import preprocess_workbook
        with pytest.raises(ValueError, match="Invalid XML"):
            preprocess_workbook(b"not xml at all <<<")

    def test_to_dict_serializable(self):
        from utils import preprocess_workbook
        import json
        ctx = preprocess_workbook(_MINIMAL_TWB)
        d = ctx.to_dict()
        # Should be JSON-serialisable
        json.dumps(d)
