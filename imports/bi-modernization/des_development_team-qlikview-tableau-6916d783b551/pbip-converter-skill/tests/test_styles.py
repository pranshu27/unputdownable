"""Tests for the style/colour translation layer (styles.py) and its
integration through the writer. Covers checklist sections 1 (Canvas),
2 (General container), 3 (Card/KPI), 6 (Charts), 10 (Theme), plus the
remaining sections 4 (Slicer), 5 (Table/Matrix), 7 (Actions/Bookmarks),
8 (Interactions), 9 (Rich text) and 11 (Analytics).
"""
import json
import os
import sys
import glob
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from skills.json_to_pbip.src import styles  # noqa: E402
from skills.json_to_pbip.src import writer  # noqa: E402


# ── Primitive helpers ────────────────────────────────────────────────────────
def test_norm_hex_expands_and_uppercases():
    assert styles._norm_hex("#abc") == "#AABBCC"
    assert styles._norm_hex("abc123") == "#ABC123"
    assert styles._norm_hex("#FF0000") == "#FF0000"
    # Named colours / theme tokens pass through untouched.
    assert styles._norm_hex("red") == "red"


def test_literals():
    assert styles._lit_str("O'Neill")["expr"]["Literal"]["Value"] == "'O''Neill'"
    assert styles._lit_num(14)["expr"]["Literal"]["Value"] == "14D"
    assert styles._lit_num(14.0)["expr"]["Literal"]["Value"] == "14D"
    assert styles._lit_bool(True)["expr"]["Literal"]["Value"] == "true"


# ── Section 2: container chrome ──────────────────────────────────────────────
def test_container_objects_full():
    fmt = {
        "general": {
            "title": {"show": True, "text": "T", "fontSize": 14, "bold": True,
                      "color": "#1B1B1B", "alignment": "center"},
            "background": {"show": True, "color": "#FFFFFF", "transparency": 0},
            "border": {"show": True, "color": "#000000", "radius": 8},
            "shadow": {"show": True, "color": "#888888"},
            "altText": "desc",
        }
    }
    out = styles.build_visual_container_objects(fmt, fallback_title="ignored")
    assert set(out) == {"title", "background", "border", "dropShadow", "general"}
    tprops = out["title"][0]["properties"]
    assert tprops["text"]["expr"]["Literal"]["Value"] == "'T'"
    assert tprops["fontColor"]["solid"]["color"]["expr"]["Literal"]["Value"] == "'#1B1B1B'"
    assert out["general"][0]["properties"]["altText"]["expr"]["Literal"]["Value"] == "'desc'"


def test_container_objects_fallback_title_only():
    # No formatting → legacy plain-title literal.
    out = styles.build_visual_container_objects(None, fallback_title="Plain")
    assert out == {"title": [{"properties": {"text": {"expr": {"Literal": {"Value": "'Plain'"}}}}}]}


def test_container_objects_empty_when_nothing():
    assert styles.build_visual_container_objects(None, fallback_title="") == {}


# ── Section 6: chart objects ─────────────────────────────────────────────────
def test_data_colors_single_and_series():
    single = styles.build_visual_objects({"dataColors": {"color": "#118DFF"}})
    assert single["dataPoint"][0]["properties"]["fill"]["solid"]["color"]["expr"]["Literal"]["Value"] == "'#118DFF'"

    multi = styles.build_visual_objects({"dataColors": [
        {"series": "East", "color": "#FF0000"},
        {"series": "West", "color": "#0000FF"},
    ]})
    dps = multi["dataPoint"]
    assert len(dps) == 2
    assert dps[0]["selector"]["data"][0]["scopeId"]["Literal"]["Value"] == "'East'"


def test_value_axis_and_labels():
    out = styles.build_visual_objects({
        "valueAxis": {"show": True, "title": "Amt", "min": 0, "max": 100, "scale": "Logarithmic"},
        "dataLabels": {"show": True, "displayUnits": "Thousands", "decimalPlaces": 1, "position": "OutsideEnd"},
    })
    va = out["valueAxis"][0]["properties"]
    assert va["axisScale"]["expr"]["Literal"]["Value"] == "'log'"
    assert va["start"]["expr"]["Literal"]["Value"] == "0D"
    assert va["titleText"]["expr"]["Literal"]["Value"] == "'Amt'"
    lab = out["labels"][0]["properties"]
    assert lab["labelDisplayUnits"]["expr"]["Literal"]["Value"] == "1000D"
    assert lab["labelPosition"]["expr"]["Literal"]["Value"] == "'OutsideEnd'"


# ── Section 1: page canvas ───────────────────────────────────────────────────
def test_page_objects_and_display_option():
    canvas = {"displayArea": "16:9", "verticalAlignment": "Middle",
              "background": {"color": "#F5F5F5", "transparency": 10},
              "wallpaper": {"color": "#000000"}}
    objs = styles.build_page_objects(canvas)
    assert objs["background"][0]["properties"]["transparency"]["expr"]["Literal"]["Value"] == "10D"
    assert "outspace" in objs and "displayArea" in objs
    assert styles.page_display_option(canvas) == "FitToPage"
    assert styles.page_display_option({"displayArea": "Custom"}) == "ActualSize"
    assert styles.page_type({"pageType": "Tooltip"}) == "Tooltip"
    assert styles.page_type({"pageType": "Standard"}) is None


# ── Section 10: theme ────────────────────────────────────────────────────────
def test_custom_theme_merges_over_base():
    base = {"name": "Base", "dataColors": ["#111111"], "background": "#FFFFFF"}
    theme = {"name": "Brand", "themeDataColors": ["#FF0000", "#abc"]}
    out = styles.build_custom_theme(theme, base)
    assert out["name"] == "Brand"
    assert out["dataColors"] == ["#FF0000", "#AABBCC"]
    # Inherits untouched tokens from the base.
    assert out["background"] == "#FFFFFF"


def test_custom_theme_none_when_no_overrides():
    assert styles.build_custom_theme({}, {"name": "Base"}) is None


# ── End-to-end through the writer ────────────────────────────────────────────
def _styled_mapped():
    return {
        "reportName": "StyleTest", "originalName": "Style Test", "source": "powerbi",
        "theme": {"name": "Brand", "themeDataColors": ["#FF0000", "#00FF00"]},
        "tables": [{"name": "Sales", "table_type": "fact",
                    "columns": [{"name": "Region", "dataType": "string", "sourceColumn": "Region"},
                                {"name": "Amount", "dataType": "double", "sourceColumn": "Amount"}],
                    "measures": []}],
        "relationships": [],
        "pages": [{"name": "Overview", "width": 1280, "height": 720,
                   "canvas": {"background": {"color": "#F5F5F5"}, "verticalAlignment": "Middle"},
                   "visuals": [{"visualType": "barChart", "title": "Sales",
                                "position": {"x": 0, "y": 0, "w": 400, "h": 300, "z": 0},
                                "fields": [{"role": "Category", "table": "Sales", "column": "Region", "aggregation": ""},
                                           {"role": "Y", "table": "Sales", "column": "Amount", "aggregation": "Sum"}],
                                "formatting": {
                                    "general": {"title": {"show": True, "text": "Sales", "color": "#1B1B1B"},
                                                "border": {"show": True, "color": "#000000", "radius": 8}},
                                    "dataColors": [{"series": "East", "color": "#FF0000"}],
                                    "valueAxis": {"show": True, "title": "Amount"}}}]}]}


def test_writer_emits_styles_end_to_end():
    out = tempfile.mkdtemp(prefix="pbip_style_test_")
    writer.write_pbip(_styled_mapped(), out)

    v = json.load(open(glob.glob(os.path.join(out, "**", "visual.json"), recursive=True)[0], encoding="utf-8"))
    assert "border" in v["visual"]["visualContainerObjects"]
    assert "dataPoint" in v["visual"]["objects"]
    assert "valueAxis" in v["visual"]["objects"]

    p = json.load(open(glob.glob(os.path.join(out, "**", "page.json"), recursive=True)[0], encoding="utf-8"))
    assert "background" in p["objects"]

    r = json.load(open(glob.glob(os.path.join(out, "**", "report.json"), recursive=True)[0], encoding="utf-8"))
    assert "customTheme" in r["themeCollection"]
    # PBIP schema requires reportVersionAtImport on every themeCollection entry.
    assert "reportVersionAtImport" in r["themeCollection"]["customTheme"]
    assert "reportVersionAtImport" in r["themeCollection"]["baseTheme"]
    ct = glob.glob(os.path.join(out, "**", "RegisteredResources", "*.json"), recursive=True)
    assert ct, "custom theme file not written"
    assert json.load(open(ct[0], encoding="utf-8"))["dataColors"] == ["#FF0000", "#00FF00"]


def test_writer_legacy_no_styles_unchanged():
    mapped = {
        "reportName": "Legacy", "originalName": "Legacy", "source": "powerbi",
        "tables": [{"name": "T", "table_type": "fact",
                    "columns": [{"name": "C", "dataType": "string", "sourceColumn": "C"}], "measures": []}],
        "relationships": [],
        "pages": [{"name": "P", "width": 1280, "height": 720,
                   "visuals": [{"visualType": "tableEx", "title": "Plain",
                                "position": {"x": 0, "y": 0, "w": 400, "h": 300, "z": 0},
                                "fields": [{"role": "Values", "table": "T", "column": "C", "aggregation": ""}]}]}]}
    out = tempfile.mkdtemp(prefix="pbip_legacy_test_")
    writer.write_pbip(mapped, out)
    v = json.load(open(glob.glob(os.path.join(out, "**", "visual.json"), recursive=True)[0], encoding="utf-8"))
    # Legacy title literal preserved; no objects block injected.
    assert v["visual"]["visualContainerObjects"]["title"][0]["properties"]["text"]["expr"]["Literal"]["Value"] == "'Plain'"
    assert "objects" not in v["visual"]
    p = json.load(open(glob.glob(os.path.join(out, "**", "page.json"), recursive=True)[0], encoding="utf-8"))
    assert "objects" not in p and "type" not in p
    r = json.load(open(glob.glob(os.path.join(out, "**", "report.json"), recursive=True)[0], encoding="utf-8"))
    assert list(r["themeCollection"].keys()) == ["baseTheme"]


# ── Section 4: slicer ────────────────────────────────────────────────────────
def test_slicer_objects():
    out = styles.build_visual_objects({
        "slicer": {"slicerType": "Dropdown", "outlineColor": "#ccc", "outlineWeight": 1},
        "selectionControls": {"singleSelect": False, "showSelectAll": True},
        "slicerHeader": {"show": True, "text": "Pick", "background": "#eee"},
        "slicerValues": {"fontSize": 10, "color": "#333"},
        "sliderColor": "#0078d4",
    })
    assert out["data"][0]["properties"]["mode"]["expr"]["Literal"]["Value"] == "'Dropdown'"
    assert out["selection"][0]["properties"]["selectAllCheckboxEnabled"]["expr"]["Literal"]["Value"] == "true"
    assert out["header"][0]["properties"]["text"]["expr"]["Literal"]["Value"] == "'Pick'"
    assert "items" in out and "slider" in out


def test_slicer_multiselect_inverts_singleselect():
    out = styles.build_visual_objects({"selectionControls": {"multiSelect": True}})
    assert out["selection"][0]["properties"]["singleSelect"]["expr"]["Literal"]["Value"] == "false"


# ── Section 5: table / matrix ────────────────────────────────────────────────
def test_table_objects():
    out = styles.build_visual_objects({
        "gridlines": {"horizontal": True, "vertical": False, "color": "#ddd", "weight": 1},
        "rowPadding": 3,
        "columnHeaders": {"bold": True, "color": "#fff", "background": "#1b1b1b", "alignment": "center", "wordWrap": True},
        "alternatingRows": {"primaryColor": "#ffffff", "secondaryColor": "#f3f3f3"},
        "cellElements": {"dataBars": True, "positiveColor": "#1aab40"},
    })
    grid = out["grid"][0]["properties"]
    assert grid["gridHorizontal"]["expr"]["Literal"]["Value"] == "true"
    assert grid["rowPadding"]["expr"]["Literal"]["Value"] == "3D"
    assert out["columnHeaders"][0]["properties"]["backColor"]["solid"]["color"]["expr"]["Literal"]["Value"] == "'#1B1B1B'"
    vals = out["values"][0]["properties"]
    assert vals["backColorSecondary"]["solid"]["color"]["expr"]["Literal"]["Value"] == "'#F3F3F3'"
    assert out["dataBars"][0]["properties"]["positiveColor"]["solid"]["color"]["expr"]["Literal"]["Value"] == "'#1AAB40'"


# ── Section 11: analytics ────────────────────────────────────────────────────
def test_analytics_objects():
    out = styles.build_visual_objects({
        "referenceLines": [{"type": "Average", "label": "Avg", "color": "#ff0000", "style": "Dashed"},
                           {"type": "Constant", "value": 500, "color": "#00aa00"}],
        "trendLine": {"show": True, "color": "#888", "style": "Dotted"},
        "forecast": {"show": True, "forecastPoints": 6, "confidenceInterval": "95%"},
    })
    assert len(out["referenceLine"]) == 2
    assert out["referenceLine"][1]["properties"]["value"]["expr"]["Literal"]["Value"] == "'500'"
    assert out["trend"][0]["properties"]["style"]["expr"]["Literal"]["Value"] == "'dotted'"
    fp = out["forecast"][0]["properties"]
    assert fp["forecastLength"]["expr"]["Literal"]["Value"] == "6D"
    assert fp["confidenceInterval"]["expr"]["Literal"]["Value"] == "0.95D"


# ── Section 7: actions + bookmarks ───────────────────────────────────────────
def test_action_page_navigation_resolves_page_id():
    out = styles.build_visual_container_objects(
        {"action": {"actionType": "PageNavigation", "target": "Details"}},
        page_ids={"Details": "ReportSectionABC"})
    props = out["visualLink"][0]["properties"]
    assert props["type"]["expr"]["Literal"]["Value"] == "'PageNavigation'"
    assert props["navigationSection"]["expr"]["Literal"]["Value"] == "'ReportSectionABC'"


def test_action_web_and_bookmark():
    web = styles.build_visual_container_objects({"action": {"actionType": "WebURL", "url": "https://x.com"}})
    assert web["visualLink"][0]["properties"]["webUrl"]["expr"]["Literal"]["Value"] == "'https://x.com'"
    bm = styles.build_visual_container_objects({"action": {"actionType": "Bookmark", "target": "BM1"}})
    assert bm["visualLink"][0]["properties"]["bookmark"]["expr"]["Literal"]["Value"] == "'BM1'"


def test_state_objects():
    out = styles.build_visual_container_objects(
        {"stateSelector": {"default": {"fill": "#0078d4", "textColor": "#fff"}, "hover": {"fill": "#106ebe"}}})
    fills = out["fill"]
    assert {f["selector"]["id"] for f in fills} == {"default", "hover"}


def test_build_bookmark_requires_state():
    assert styles.build_bookmark({"displayName": "No State"}, "Bookmark1") is None
    bm = styles.build_bookmark(
        {"displayName": "Focus", "explorationState": {"version": "1.0"}, "captureCurrentPage": True},
        "BookmarkABC")
    assert bm["name"] == "BookmarkABC" and bm["displayName"] == "Focus"
    assert bm["options"]["suppressActiveSection"] is False
    assert bm["explorationState"] == {"version": "1.0"}


# ── Section 8: interactions ──────────────────────────────────────────────────
def test_visual_interactions_translate_ids():
    id_map = {"v_slicer": "AAA", "v_table": "BBB"}
    out = styles.build_visual_interactions(
        [{"source": "v_slicer", "target": "v_table", "interactionType": "Filter"},
         {"source": "v_slicer", "target": "v_missing", "interactionType": "None"}],  # unresolved → dropped
        id_map)
    assert out == [{"source": "AAA", "target": "BBB", "type": "Filter"}]


# ── Section 9: rich text ─────────────────────────────────────────────────────
def test_rich_text_paragraphs():
    paras = styles.build_textbox_paragraphs({"richText": {"paragraphs": [
        {"alignment": "center", "textRuns": [
            {"text": "Bold ", "bold": True, "fontSize": 14, "color": "#1b1b1b"},
            {"text": "link", "underline": True, "url": "https://x.com"}]}]}})
    assert paras[0]["horizontalTextAlignment"] == "center"
    run0 = paras[0]["textRuns"][0]
    assert run0["value"] == "Bold " and run0["textStyle"]["fontWeight"] == "bold"
    assert run0["textStyle"]["fontSize"] == "14pt"
    run1 = paras[0]["textRuns"][1]
    assert run1["textStyle"]["textDecoration"] == "underline" and run1["url"] == "https://x.com"


def test_rich_text_fallback_to_plain_content():
    paras = styles.build_textbox_paragraphs(None, "line1\nline2")
    assert [p["textRuns"][0]["value"] for p in paras] == ["line1", "line2"]


# ── End-to-end: remaining sections through the writer ────────────────────────
def test_writer_remaining_sections_end_to_end():
    mapped = {
        "reportName": "AllSec", "originalName": "All", "source": "powerbi",
        "tables": [{"name": "Sales", "table_type": "fact",
                    "columns": [{"name": "Region", "dataType": "string", "sourceColumn": "Region"},
                                {"name": "Amount", "dataType": "double", "sourceColumn": "Amount"}], "measures": []}],
        "relationships": [],
        "bookmarks": [
            {"displayName": "Focus", "explorationState": {"version": "1.0", "activeSection": "ReportSection"},
             "captureCurrentPage": True},
            {"displayName": "NoState"},  # skipped
        ],
        "pages": [{"name": "Main", "width": 1280, "height": 720,
                   "interactions": [{"source": "v_slicer", "target": "v_table", "interactionType": "Filter"}],
                   "visuals": [
                       {"id": "v_slicer", "visualType": "slicer", "title": "Region",
                        "position": {"x": 0, "y": 0, "w": 200, "h": 400, "z": 0},
                        "fields": [{"role": "Values", "table": "Sales", "column": "Region", "aggregation": ""}],
                        "formatting": {"slicer": {"slicerType": "Dropdown"}, "selectionControls": {"showSelectAll": True}}},
                       {"id": "v_table", "visualType": "tableEx", "title": "Detail",
                        "position": {"x": 210, "y": 0, "w": 500, "h": 400, "z": 1000},
                        "fields": [{"role": "Values", "table": "Sales", "column": "Amount", "aggregation": "Sum"}],
                        "formatting": {"gridlines": {"horizontal": True, "color": "#ddd"},
                                       "alternatingRows": {"primaryColor": "#fff", "secondaryColor": "#f3f3f3"}}},
                       {"id": "v_btn", "visualType": "actionButton", "title": "Go",
                        "position": {"x": 0, "y": 410, "w": 120, "h": 40, "z": 2000}, "fields": [],
                        "formatting": {"action": {"actionType": "PageNavigation", "target": "Details"}}},
                       {"id": "v_text", "visualType": "textbox", "title": "",
                        "position": {"x": 130, "y": 410, "w": 300, "h": 100, "z": 3000}, "fields": [],
                        "formatting": {"richText": {"paragraphs": [{"alignment": "left",
                                       "textRuns": [{"text": "Hi", "bold": True}]}]}}},
                   ]},
                  {"name": "Details", "width": 1280, "height": 720, "visuals": []}],
    }
    out = tempfile.mkdtemp(prefix="pbip_remaining_")
    writer.write_pbip(mapped, out)

    vmap = {}
    for vp in glob.glob(os.path.join(out, "**", "visual.json"), recursive=True):
        vj = json.load(open(vp, encoding="utf-8"))
        vmap[vj["visual"]["visualType"]] = vj

    assert "data" in vmap["slicer"]["visual"]["objects"]          # slicer mode
    assert "grid" in vmap["tableEx"]["visual"]["objects"]          # table grid
    assert "values" in vmap["tableEx"]["visual"]["objects"]        # zebra banding
    # Button navigation target resolved to a real ReportSection id.
    nav = vmap["actionButton"]["visual"]["visualContainerObjects"]["visualLink"][0]["properties"]["navigationSection"]["expr"]["Literal"]["Value"]
    assert nav.startswith("'ReportSection")
    # Rich text paragraphs.
    assert vmap["textbox"]["visual"]["objects"]["general"][0]["properties"]["paragraphs"][0]["textRuns"][0]["value"] == "Hi"

    # Page interactions reference generated visual names (20-hex), not RE ids.
    main_page = next(json.load(open(pp, encoding="utf-8"))
                     for pp in glob.glob(os.path.join(out, "**", "page.json"), recursive=True)
                     if json.load(open(pp, encoding="utf-8"))["displayName"] == "Main")
    vi = main_page["visualInteractions"]
    assert len(vi) == 1 and vi[0]["type"] == "Filter"
    assert vi[0]["source"] != "v_slicer"  # translated to generated name

    # Bookmarks are DISABLED by default (writer._EMIT_BOOKMARKS=False) because
    # the RE's captured explorationState isn't schema-valid and references
    # source ids — emitting it blocks the whole report from opening.
    bms = glob.glob(os.path.join(out, "**", "bookmarks", "*.bookmark.json"), recursive=True)
    assert bms == []


# ════════════════════════════════════════════════════════════════════════════
# MASTER CHECKLIST — additional sections
# ════════════════════════════════════════════════════════════════════════════

# ── §1: page background image + filter pane/cards ────────────────────────────
def test_page_background_image_and_imagefit():
    objs = styles.build_page_objects({"background": {"image": "https://x/bg.png", "imageFit": "Fill"}})
    img = objs["background"][0]["properties"]["image"]
    assert img["url"]["expr"]["Literal"]["Value"] == "'https://x/bg.png'"
    assert img["scaling"]["expr"]["Literal"]["Value"] == "'Fill'"


def test_filter_pane_and_cards():
    objs = styles.build_page_objects({
        "filterPane": {"visibility": "Hidden", "width": 200, "background": "#eee", "fontSize": 10},
        "filterCards": {"available": {"background": "#fff"}, "applied": {"background": "#cde"}},
    })
    pane = objs["outspacePane"][0]["properties"]
    assert pane["show"]["expr"]["Literal"]["Value"] == "false"   # Hidden → show false
    assert pane["width"]["expr"]["Literal"]["Value"] == "200D"
    cards = objs["filterCard"]
    assert {c["selector"]["id"] for c in cards} == {"Available", "Applied"}


# ── §2: tooltips + header icons + dynamic title ──────────────────────────────
def test_tooltips_and_header_icons():
    out = styles.build_visual_container_objects({"general": {
        "tooltips": {"type": "Canvas", "page": "TT Page"},
        "headerIcons": {"show": True, "focusMode": True, "pin": False, "color": "#605E5C"}}})
    assert out["visualTooltip"][0]["properties"]["section"]["expr"]["Literal"]["Value"] == "'TT Page'"
    hp = out["visualHeader"][0]["properties"]
    assert hp["focusModeIcon"]["expr"]["Literal"]["Value"] == "true"
    assert hp["pinIcon"]["expr"]["Literal"]["Value"] == "false"


def test_dynamic_title_measure():
    out = styles.build_visual_container_objects({"general": {
        "title": {"show": True, "table": "Sales", "measure": "Total"}}})
    txt = out["title"][0]["properties"]["text"]
    assert txt["expr"]["Measure"]["Property"] == "Total"
    assert txt["expr"]["Measure"]["Expression"]["SourceRef"]["Entity"] == "Sales"


# ── §3: axis display units + data-label background ───────────────────────────
def test_axis_display_units_and_label_background():
    out = styles.build_visual_objects({
        "valueAxis": {"show": True, "displayUnits": "Millions", "gridlines": True, "gridlineColor": "#eee"},
        "dataLabels": {"show": True, "backgroundColor": "#FFFFFF", "density": 100},
    })
    va = out["valueAxis"][0]["properties"]
    assert va["labelDisplayUnits"]["expr"]["Literal"]["Value"] == "1000000D"
    assert va["gridlineShow"]["expr"]["Literal"]["Value"] == "true"
    lab = out["labels"][0]["properties"]
    assert lab["showBackground"]["expr"]["Literal"]["Value"] == "true"
    assert lab["labelDensity"]["expr"]["Literal"]["Value"] == "100D"


def test_legend_extended_positions():
    out = styles.build_visual_objects({"legend": {"show": True, "position": "TopLeft"}})
    assert out["legend"][0]["properties"]["position"]["expr"]["Literal"]["Value"] == "'TopLeft'"


# ── §4: table totals ─────────────────────────────────────────────────────────
def test_table_totals():
    out = styles.build_visual_objects({"totals": {
        "rowTotals": True, "columnTotals": False, "label": "Grand Total",
        "rowStepping": True, "background": "#0072CE", "bold": True}})
    st = out["subTotals"][0]["properties"]
    assert st["rowSubtotals"]["expr"]["Literal"]["Value"] == "true"
    assert st["columnSubtotals"]["expr"]["Literal"]["Value"] == "false"
    assert st["totalLabel"]["expr"]["Literal"]["Value"] == "'Grand Total'"
    assert st["rowSubtotalsType"]["expr"]["Literal"]["Value"] == "'Stepped'"
    assert out["total"][0]["properties"]["bold"]["expr"]["Literal"]["Value"] == "true"


# ── §6: slicer responsive + clearSelection ───────────────────────────────────
def test_slicer_responsive_and_clear():
    out = styles.build_visual_objects({"slicer": {"slicerType": "Dropdown", "responsive": True},
                                       "clearSelection": True})
    assert out["general"][0]["properties"]["responsive"]["expr"]["Literal"]["Value"] == "true"
    assert out["header"][0]["properties"]["show"]["expr"]["Literal"]["Value"] == "true"


# ── §5/§10: maps ─────────────────────────────────────────────────────────────
def test_map_objects():
    out = styles.build_visual_objects({
        "map": {"mapStyle": "Grayscale", "bubbleSizeMin": 5, "bubbleSizeMax": 30,
                "zoomMin": 1, "zoomMax": 18, "layers": ["Bubble", "Traffic"]},
        "legendRanges": [{"from": 0, "to": 50, "color": "#ff0000"}],
    })
    assert out["mapControls"][0]["properties"]["mapTheme"]["expr"]["Literal"]["Value"] == "'grayscale_light'"
    assert out["bubbles"][0]["properties"]["maxSize"]["expr"]["Literal"]["Value"] == "30D"
    assert "mapLayers" in out
    assert out["fillRules"][0]["properties"]["fillColor"]["solid"]["color"]["expr"]["Literal"]["Value"] == "'#FF0000'"


# ── §8: combo secondary axis ─────────────────────────────────────────────────
def test_combo_secondary_axis():
    out = styles.build_visual_objects({"secondaryValueAxis": {
        "show": True, "title": "Margin %", "min": 0, "max": 100, "alignZeros": True, "color": "#FF6900"}})
    y2 = out["y2Axis"][0]["properties"]
    assert y2["secShow"]["expr"]["Literal"]["Value"] == "true"
    assert y2["secTitleText"]["expr"]["Literal"]["Value"] == "'Margin %'"
    assert y2["alignZeros"]["expr"]["Literal"]["Value"] == "true"


# ── §12: KPI / gauge / treemap ───────────────────────────────────────────────
def test_kpi_gauge_treemap():
    out = styles.build_visual_objects({
        "kpi": {"trendAxisShow": False, "valueColor": "#0072CE"},
        "gauge": {"min": 0, "max": 100, "target": 80, "fillColor": "#A4D65E"},
        "treemap": {"maxCategories": 10},
    })
    assert out["trendline"][0]["properties"]["show"]["expr"]["Literal"]["Value"] == "false"
    assert out["axis"][0]["properties"]["target"]["expr"]["Literal"]["Value"] == "80D"
    assert out["dataReductionCap"][0]["properties"]["maxCategories"]["expr"]["Literal"]["Value"] == "10D"


# ── §9: AI / Q&A ─────────────────────────────────────────────────────────────
def test_ai_objects():
    out = styles.build_visual_objects({"ai": {
        "enableAiSplits": True, "suggestedQuestions": ["top regions?", "sales trend?"]}})
    assert out["analysisType"][0]["properties"]["enabled"]["expr"]["Literal"]["Value"] == "true"
    assert "suggestedQuestions" in out


# ── §13: ApplyAllSlicers / ClearAllSlicers ───────────────────────────────────
def test_apply_clear_all_slicers_actions():
    apply = styles.build_visual_container_objects({"action": {"actionType": "ApplyAllSlicers"}})
    assert apply["visualLink"][0]["properties"]["type"]["expr"]["Literal"]["Value"] == "'ApplyAllSlicers'"
    clear = styles.build_visual_container_objects({"action": {"actionType": "ClearAllSlicers"}})
    assert clear["visualLink"][0]["properties"]["type"]["expr"]["Literal"]["Value"] == "'ClearAllSlicers'"


# ════════════════════════════════════════════════════════════════════════════
# RE-SCHEMA NORMALIZATION + raw PBIP passthrough
# ════════════════════════════════════════════════════════════════════════════
def test_normalize_theme_from_re_shape():
    re_theme = {
        "name": "CY24SU10",
        "data_palette": ["#118DFF", "#12239E"],
        "semantic_colors": {
            "foreground": {"hex": "#252423"}, "background": {"hex": "#FFFFFF"},
            "table_accent": {"hex": "#118DFF"}, "bad": {"hex": "#D64554"}},
    }
    norm = styles.normalize_theme(re_theme)
    assert norm["name"] == "CY24SU10"
    assert norm["themeDataColors"] == ["#118DFF", "#12239E"]
    assert norm["tokens"]["tableAccent"] == "#118DFF"
    # Feeds build_custom_theme: tokens land as top-level theme keys.
    ct = styles.build_custom_theme(norm, {"name": "Base"})
    assert ct["dataColors"] == ["#118DFF", "#12239E"]
    assert ct["foreground"] == "#252423" and ct["tableAccent"] == "#118DFF"


def test_adapt_structured_style_tableau():
    """The snake_case structured `style` block (Tableau / Power BI) maps onto
    the camelCase formatting contract, reading colours as `.hex`."""
    style = {
        "container": {"background": {"color": {"hex": "#F5F5F5"}, "transparency": 10, "show": True},
                      "border": {"show": True, "color": {"hex": "#000000"}, "radius": 6},
                      "alt_text": "desc"},
        "title": {"family": "Segoe UI", "size": 14, "bold": True,
                  "align": "center", "color": {"hex": "#1B1B1B"}, "text": "My Title"},
        "callout": {"value": {"size": 28, "bold": True, "color": {"hex": "#0072CE"}},
                    "display_units": "Thousands", "decimal_places": 1},
        "data_colors": [{"field": "f", "value": "East", "color": {"hex": "#FF0000"}},
                        {"field": "f", "value": "West", "color": {"hex": None}}],  # null hex skipped
        "data_labels": {"show": True, "position": "OutsideEnd", "display_units": "Auto",
                        "font": {"size": 9, "color": {"hex": "#222222"}}},
        "legend": {"show": True, "position": "BottomCenter", "title": "Series",
                   "labels": {"size": 9, "color": {"hex": "#12239E"}}},
        "axes": [{"name": "category", "title": "Cat", "labels": {"color": {"hex": "#333"}}},
                 {"name": "value", "title": "Val", "min": 0, "max": 100,
                  "display_units": "Millions", "labels": {"color": {"hex": "#444"}}}],
    }
    fmt = styles.adapt_structured_style(style)
    assert fmt["general"]["title"]["text"] == "My Title"
    assert fmt["general"]["title"]["color"] == "#1B1B1B"
    assert fmt["general"]["background"]["color"] == "#F5F5F5"
    assert fmt["general"]["border"]["radius"] == 6
    assert fmt["general"]["altText"] == "desc"
    assert fmt["callout"]["displayUnits"] == "Thousands"
    assert fmt["dataColors"] == [{"series": "East", "color": "#FF0000"}]  # null-hex dropped
    assert fmt["dataLabels"]["position"] == "OutsideEnd"
    assert fmt["legend"]["title"] == "Series"
    assert fmt["valueAxis"]["title"] == "Val" and fmt["valueAxis"]["displayUnits"] == "Millions"
    assert fmt["categoryAxis"]["title"] == "Cat"
    # And it flows through the builders into real PBIP objects.
    objs = styles.build_visual_objects(fmt)
    assert "dataPoint" in objs and "labels" in objs and "valueAxis" in objs
    vco = styles.build_visual_container_objects(fmt)
    assert "title" in vco and "border" in vco


def test_adapt_structured_style_none_when_empty():
    assert styles.adapt_structured_style(None) is None
    assert styles.adapt_structured_style({"slicer": None, "table": None}) is None


def test_sanitize_raw_objects_drops_malformed():
    raw = {
        "legend": [{"properties": {"show": {"expr": {"Literal": {"Value": "true"}}}}}],  # valid
        "bad1": "not a list",                       # dropped
        "bad2": [42, {"no_properties": 1}],         # dropped (no valid entries)
        "mixed": [{"properties": {"a": 1}}, "junk"],  # keeps only the valid entry
    }
    clean = styles.sanitize_raw_objects(raw)
    assert set(clean) == {"legend", "mixed"}
    assert len(clean["mixed"]) == 1
    assert styles.sanitize_raw_objects(None) == {}


def test_normalize_bookmarks_from_re_shape():
    re_bms = [{
        "name": "bm1", "display_name": "Matrix", "capture_data": True,
        "capture_current_page": True,
        "raw": {"displayName": "Matrix", "explorationState": {"version": "1.11", "activeSection": "p1"}},
    }, {"name": "no_state"}]
    norm = styles.normalize_bookmarks(re_bms)
    assert norm[0]["displayName"] == "Matrix"
    assert norm[0]["explorationState"]["activeSection"] == "p1"
    assert norm[0]["captureCurrentPage"] is True
    # build_bookmark uses the normalized shape; second (no state) → skipped.
    assert styles.build_bookmark(norm[0], "BookmarkX")["name"] == "BookmarkX"
    assert styles.build_bookmark(norm[1], "BookmarkY") is None


def test_writer_emits_re_raw_objects():
    """A visual carrying the RE's ready-made `raw_objects`/`raw_vc_objects`
    (PBIP) emits them verbatim into objects / visualContainerObjects."""
    mapped = {
        "reportName": "RawTest", "originalName": "Raw", "source": "powerbi",
        "tables": [{"name": "T", "table_type": "fact",
                    "columns": [{"name": "C", "dataType": "string", "sourceColumn": "C"}], "measures": []}],
        "relationships": [],
        "pages": [{"name": "P", "width": 1280, "height": 720,
                   "raw_objects": {"background": [{"properties": {"transparency": {"expr": {"Literal": {"Value": "65D"}}}}}]},
                   "displayOption": "FitToPage",
                   "visuals": [{"id": "v1", "visualType": "barChart", "title": "Bar",
                                "position": {"x": 0, "y": 0, "w": 400, "h": 300, "z": 0},
                                "fields": [{"role": "Category", "table": "T", "column": "C", "aggregation": ""}],
                                "raw_objects": {"legend": [{"properties": {"position": {"expr": {"Literal": {"Value": "'BottomCenter'"}}}}}],
                                                "dataPoint": [{"properties": {"fill": {"solid": {"color": {"expr": {"ThemeDataColor": {"ColorId": 1, "Percent": 0.2}}}}}}}]},
                                "raw_vc_objects": {"title": [{"properties": {"text": {"expr": {"Literal": {"Value": "'Bar'"}}}}}],
                                                   "border": [{"properties": {"show": {"expr": {"Literal": {"Value": "true"}}}}}]}}]}],
    }
    out = tempfile.mkdtemp(prefix="pbip_raw_")
    writer.write_pbip(mapped, out)
    v = json.load(open(glob.glob(os.path.join(out, "**", "visual.json"), recursive=True)[0], encoding="utf-8"))
    # Raw objects passed straight through (incl. ThemeDataColor ref).
    assert v["visual"]["objects"]["legend"][0]["properties"]["position"]["expr"]["Literal"]["Value"] == "'BottomCenter'"
    assert v["visual"]["objects"]["dataPoint"][0]["properties"]["fill"]["solid"]["color"]["expr"]["ThemeDataColor"]["ColorId"] == 1
    assert "border" in v["visual"]["visualContainerObjects"]
    p = json.load(open(glob.glob(os.path.join(out, "**", "page.json"), recursive=True)[0], encoding="utf-8"))
    assert "background" in p["objects"]
