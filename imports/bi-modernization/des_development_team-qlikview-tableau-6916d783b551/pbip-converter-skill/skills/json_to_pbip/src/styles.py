"""
styles.py — Translate the RE's camelCase style/colour metadata into the PBIP
formatting blocks (`visualContainerObjects`, visual `objects`, page `objects`,
report theme) that actually drive colours and themes in the rendered report.

────────────────────────────────────────────────────────────────────────────
WHY THIS MODULE EXISTS
────────────────────────────────────────────────────────────────────────────
writer.py historically emitted only structural data (position, queryState,
title literal). Every colour / font / border / axis / legend / data-label
property the source report carried was dropped at the parser and never reached
the PBIP. This module is the single place that knows how to turn the RE's
style contract into the exact JSON shapes Power BI Desktop reads.

The pipeline carries the style metadata through UNTRANSFORMED:
    RE JSON  →  parser (verbatim pass-through)  →  mapper (verbatim pass-through)
             →  writer (calls this module to emit PBIP blocks)
No LLM ever touches the style data — colours and fonts are deterministic.

────────────────────────────────────────────────────────────────────────────
THE CONTRACT  (what the RE emits — "new camelCase" schema)
────────────────────────────────────────────────────────────────────────────
This is the CORE-FIRST subset: checklist sections 1 (Canvas), 2 (General
container), 3 (Card/KPI), 6 (Charts) + 10 (Theme). Every key is OPTIONAL;
anything absent is simply not emitted (Power BI falls back to the theme
default). Unknown keys are ignored. Nothing here ever raises — a malformed
style block degrades to "no styling", never to a crash.

PAGE  (section 1 — Canvas & Environment).  Attached as `page["canvas"]`:
    {
      "pageType": "Standard" | "Tooltip" | "Drillthrough",
      "displayArea": "16:9" | "4:3" | "Letter" | "Tooltip" | "Custom",
      "verticalAlignment": "Top" | "Middle",
      "background": {"color": "#FFFFFF", "transparency": 0,
                     "image": "<url|base64>", "imageFit": "Normal|Fit|Fill"},
      "wallpaper":  {"color": "#000000", "transparency": 0, "image": "..."}
    }
  (Page image binaries pulled from Postgres still flow through the existing
   `background_image_id` / `wallpaper_image_id` path in writer.py; the `image`
   key here is for direct URL / base64 references.)

VISUAL  (sections 2, 3, 6).  Attached as `visual["formatting"]`:
    {
      # ── Section 2: General / container chrome ──────────────────────────
      "general": {
        "title":    <TEXT_STYLE> + {"show", "text", "alignment", "background"},
        "subtitle": <TEXT_STYLE> + {"show", "text", "alignment", "background"},
        "background": {"show": true, "color": "#FFFFFF", "transparency": 0},
        "border":     {"show": true, "color": "#000000", "radius": 0},
        "shadow":     {"show": true, "color": "#000000", "position": "Outer"},
        "altText":    "screen-reader description"
      },
      # ── Section 3: Card / KPI callout ──────────────────────────────────
      "callout":       <TEXT_STYLE> + {"displayUnits", "decimalPlaces"},
      "categoryLabel": <TEXT_STYLE> + {"show"},
      # ── Section 6: Chart schemas ───────────────────────────────────────
      "dataColors":  [{"series": "<name>", "color": "#118DFF"}]  |  {"color": "#118DFF"},
      "dataLabels":  <TEXT_STYLE> + {"show", "position", "displayUnits", "decimalPlaces"},
      "legend":      <TEXT_STYLE> + {"show", "position", "title"},
      "valueAxis":     <AXIS>,
      "categoryAxis":  <AXIS>,
      "linesAndMarkers": {"lineStyle": "Solid|Dashed|Dotted",
                          "markerShow": true, "markerShape": "Circle",
                          "markerSize": 5}
    }

  <TEXT_STYLE> = {"fontFamily": "Segoe UI", "fontSize": 12, "bold": false,
                  "italic": false, "underline": false, "color": "#000000"}
  <AXIS>       = {"show": true, "title": "Amount", "min": 0, "max": 100,
                  "scale": "Linear|Logarithmic|Continuous|Categorical",
                  "logarithmic": false} + <TEXT_STYLE>

REPORT  (section 10 — Theme).  Attached as `mapped["theme"]`:
    {
      "themeDataColors": ["#...", ...],   # overrides the base palette
      "name": "MyTheme",
      "visualStyles": { ... }             # raw PBI visualStyles, passed verbatim
    }
"""
from __future__ import annotations

import uuid as _uuid


# ── Value-expression primitives ─────────────────────────────────────────────
# Every formatting property value in PBIP is an expression object. Scalars are
# DAX-style literals; colours wrap a literal in a `solid.color` envelope.

def _lit_str(value) -> dict:
    """String literal: 'text' with embedded single quotes doubled."""
    s = str(value).replace("'", "''")
    return {"expr": {"Literal": {"Value": f"'{s}'"}}}


def _lit_num(value) -> dict:
    """Numeric literal. PBIP suffixes the value with `D` (double)."""
    # Keep ints clean (12 not 12.0) but still tag as D, which PBI accepts.
    if isinstance(value, bool):
        return _lit_bool(value)
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return {"expr": {"Literal": {"Value": f"{value}D"}}}


def _lit_bool(value) -> dict:
    return {"expr": {"Literal": {"Value": "true" if value else "false"}}}


def _solid(color_hex) -> dict:
    """A solid colour value — used by fill/fontColor/labelColor/etc."""
    return {"solid": {"color": _lit_str(_norm_hex(color_hex))}}


def _norm_hex(color) -> str:
    """Normalise a colour string to `#RRGGBB`. Accepts `#abc`, `abc123`,
    `#ABC123`. Leaves theme tokens / named colours untouched (PBI resolves
    a bare token name itself)."""
    if not isinstance(color, str):
        return str(color)
    c = color.strip()
    if not c:
        return c
    if c.startswith("#"):
        body = c[1:]
    elif all(ch in "0123456789abcdefABCDEF" for ch in c) and len(c) in (3, 6):
        body = c
    else:
        return c  # named colour / theme token — pass through
    if len(body) == 3:  # #abc → #aabbcc
        body = "".join(ch * 2 for ch in body)
    return "#" + body.upper()


# ── Small helpers ────────────────────────────────────────────────────────────
def _props(d: dict) -> list:
    """Wrap a properties dict in the PBIP `[{"properties": {...}}]` envelope.
    Returns [] when the dict is empty so callers can skip emitting the object."""
    return [{"properties": d}] if d else []


def _add(props: dict, key: str, value) -> None:
    """Set props[key] only when value is meaningful (not None / not '')."""
    if value is not None and value != "":
        props[key] = value


_ALIGN_MAP = {
    "left": "left", "center": "center", "centre": "center",
    "right": "right", "justify": "left",
}


def _text_props(style: dict, *, include_color_key: str = "fontColor") -> dict:
    """Build the common typography properties shared by title / labels / axis /
    legend / callout. `include_color_key` is the PBIP property name for the
    text colour (varies: `fontColor`, `labelColor`, `color`)."""
    props: dict = {}
    if not isinstance(style, dict):
        return props
    _add(props, "fontFamily", _lit_str(style["fontFamily"]) if style.get("fontFamily") else None)
    if style.get("fontSize") is not None:
        props["fontSize"] = _lit_num(style["fontSize"])
    if style.get("bold") is not None:
        props["bold"] = _lit_bool(style["bold"])
    if style.get("italic") is not None:
        props["italic"] = _lit_bool(style["italic"])
    if style.get("underline") is not None:
        props["underline"] = _lit_bool(style["underline"])
    if style.get("color"):
        props[include_color_key] = _solid(style["color"])
    return props


# ════════════════════════════════════════════════════════════════════════════
# SECTION 2 — Visual container chrome  (visual.visualContainerObjects)
# ════════════════════════════════════════════════════════════════════════════
def build_visual_container_objects(formatting: dict, fallback_title: str = "",
                                   page_ids: dict | None = None) -> dict:
    """Return the `visualContainerObjects` block (title, subTitle, background,
    border, dropShadow, general/altText, visualLink action) from `formatting`.

    `fallback_title` preserves the legacy behaviour: when the RE supplies no
    title style block but the visual has a plain title string, emit just the
    title text literal (exactly as writer.py did before this module existed).

    `page_ids` maps a page display name → its generated ReportSection id, so a
    PageNavigation / Drillthrough button can resolve its target page (section 7).
    """
    out: dict = {}
    general = (formatting or {}).get("general") if isinstance(formatting, dict) else None
    general = general if isinstance(general, dict) else {}

    # ── Title ────────────────────────────────────────────────────────────
    title_style = general.get("title")
    if isinstance(title_style, dict):
        tp = _text_props(title_style)
        if title_style.get("show") is not None:
            tp["show"] = _lit_bool(title_style["show"])
        # Dynamic title bound to a measure (expr): {"table","measure"} →
        # a Measure expression, so the title updates with the data. Falls
        # back to the static text literal when no binding is given.
        if title_style.get("measure") and title_style.get("table"):
            tp["text"] = {"expr": {"Measure": {
                "Expression": {"SourceRef": {"Entity": title_style["table"]}},
                "Property": title_style["measure"]}}}
        else:
            text = title_style.get("text", fallback_title)
            if text:
                tp["text"] = _lit_str(text)
        if title_style.get("alignment"):
            tp["alignment"] = _lit_str(_ALIGN_MAP.get(
                str(title_style["alignment"]).lower(), title_style["alignment"]))
        if title_style.get("background"):
            tp["background"] = _solid(title_style["background"])
        if tp:
            out["title"] = _props(tp)
    elif fallback_title:
        # Legacy path: title text only.
        out["title"] = _props({"text": _lit_str(fallback_title)})

    # ── Subtitle ─────────────────────────────────────────────────────────
    sub_style = general.get("subtitle") or general.get("subTitle")
    if isinstance(sub_style, dict):
        sp = _text_props(sub_style)
        if sub_style.get("show") is not None:
            sp["show"] = _lit_bool(sub_style["show"])
        if sub_style.get("text"):
            sp["text"] = _lit_str(sub_style["text"])
        if sub_style.get("alignment"):
            sp["alignment"] = _lit_str(_ALIGN_MAP.get(
                str(sub_style["alignment"]).lower(), sub_style["alignment"]))
        if sp:
            out["subTitle"] = _props(sp)

    # ── Background ───────────────────────────────────────────────────────
    bg = general.get("background")
    if isinstance(bg, dict):
        bp: dict = {}
        if bg.get("show") is not None:
            bp["show"] = _lit_bool(bg["show"])
        if bg.get("color"):
            bp["color"] = _solid(bg["color"])
        if bg.get("transparency") is not None:
            bp["transparency"] = _lit_num(bg["transparency"])
        if bp:
            out["background"] = _props(bp)

    # ── Border ───────────────────────────────────────────────────────────
    border = general.get("border")
    if isinstance(border, dict):
        brp: dict = {}
        if border.get("show") is not None:
            brp["show"] = _lit_bool(border["show"])
        if border.get("color"):
            brp["color"] = _solid(border["color"])
        if border.get("radius") is not None:
            brp["radius"] = _lit_num(border["radius"])
        if brp:
            out["border"] = _props(brp)

    # ── Drop shadow ──────────────────────────────────────────────────────
    shadow = general.get("shadow")
    if isinstance(shadow, dict):
        shp: dict = {}
        if shadow.get("show") is not None:
            shp["show"] = _lit_bool(shadow["show"])
        if shadow.get("color"):
            shp["color"] = _solid(shadow["color"])
        if shadow.get("position"):
            shp["position"] = _lit_str(shadow["position"])
        if shp:
            out["dropShadow"] = _props(shp)

    # ── Alt text (accessibility) → general.altText ───────────────────────
    alt = general.get("altText")
    if alt:
        out["general"] = _props({"altText": _lit_str(alt)})

    fmt0 = formatting if isinstance(formatting, dict) else {}

    # ── Tooltips config (section 2) → visualTooltip ──────────────────────
    # {"type": "Default|Canvas|Auto|None", "page": "<tooltip page name>"}
    tt = general.get("tooltips") or fmt0.get("tooltips")
    if isinstance(tt, dict):
        ttp: dict = {}
        if tt.get("type"):
            ttp["type"] = _lit_str(tt["type"])
        if tt.get("show") is not None:
            ttp["show"] = _lit_bool(tt["show"])
        if tt.get("page"):
            ttp["section"] = _lit_str(tt["page"])
        if ttp:
            out["visualTooltip"] = _props(ttp)

    # ── Header icons (section 2) → visualHeader ──────────────────────────
    # {"show": bool, "pin": bool, "focusMode": bool, "filter": bool,
    #  "optionsMenu": bool, "drill": bool, "background": "#..", "color": "#.."}
    hi = general.get("headerIcons") or fmt0.get("headerIcons")
    if isinstance(hi, dict):
        hp: dict = {}
        _ICON = {"show": "show", "pin": "pinIcon", "focusMode": "focusModeIcon",
                 "filter": "filterRestatementIcon", "optionsMenu": "optionsMenuIcon",
                 "drill": "drillIcon", "drillUp": "drillUpIcon", "drillDown": "drillDownIcon",
                 "tooltip": "tooltipIcon", "smartNarrative": "smartNarrativeIcon"}
        for k, prop in _ICON.items():
            if hi.get(k) is not None:
                hp[prop] = _lit_bool(hi[k])
        if hi.get("background"):
            hp["background"] = _solid(hi["background"])
        if hi.get("color"):
            hp["foreground"] = _solid(hi["color"])
        if hp:
            out["visualHeader"] = _props(hp)

    # ── Section 7: button action (visualLink) + state styling ────────────
    fmt = formatting if isinstance(formatting, dict) else {}
    action_obj = _build_action_object(fmt.get("action"), page_ids)
    if action_obj:
        out["visualLink"] = action_obj
    for _k, _v in _build_state_objects(fmt.get("stateSelector")).items():
        out.setdefault(_k, _v)

    return out


# ════════════════════════════════════════════════════════════════════════════
# SECTIONS 3 & 6 — Visual-type formatting  (visual.objects)
# ════════════════════════════════════════════════════════════════════════════
_DISPLAY_UNITS = {
    "auto": 0, "none": 1, "thousands": 1000, "millions": 1000000,
    "billions": 1000000000, "trillions": 1000000000000,
}


def _display_units_value(v):
    """Map a display-unit name/number to PBIP's numeric labelDisplayUnits."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    return _DISPLAY_UNITS.get(str(v).strip().lower())


_LEGEND_POSITION = {
    "top": "Top", "bottom": "Bottom", "left": "Left", "right": "Right",
    "topcenter": "TopCenter", "bottomcenter": "BottomCenter",
    "lefttop": "LeftTop", "leftcenter": "LeftCenter",
    "righttop": "RightTop", "rightcenter": "RightCenter",
    # Anchor aliases used by the master checklist (TopLeft / TopRight / …).
    "topleft": "TopLeft", "topright": "TopRight",
    "bottomleft": "BottomLeft", "bottomright": "BottomRight",
    "none": "None", "off": "None",
}

# Image scaling (page background / wallpaper / image visual).
_IMAGE_FIT = {"normal": "Normal", "fit": "Fit", "fill": "Fill"}

_LABEL_POSITION = {
    "insideend": "InsideEnd", "outsideend": "OutsideEnd",
    "insidecenter": "InsideCenter", "insidebase": "InsideBase",
    "center": "Center", "auto": "Auto",
}

_AXIS_SCALE = {"linear": "linear", "logarithmic": "log", "log": "log"}
_AXIS_TYPE = {
    "categorical": "Categorical", "continuous": "Continuous",
    "scalar": "Scalar",
}


def build_visual_objects(formatting: dict) -> dict:
    """Return the visual `objects` block: dataPoint (colours), labels (data
    labels), legend, valueAxis, categoryAxis, lineStyles/markers — from the
    chart-level keys of `formatting`."""
    out: dict = {}
    if not isinstance(formatting, dict):
        return out

    # ── Data colours → dataPoint ─────────────────────────────────────────
    dc = formatting.get("dataColors")
    data_points = _build_data_points(dc)
    if data_points:
        out["dataPoint"] = data_points

    # ── Data labels → labels ─────────────────────────────────────────────
    dl = formatting.get("dataLabels")
    if isinstance(dl, dict):
        lp = _text_props(dl, include_color_key="color")
        if dl.get("show") is not None:
            lp["show"] = _lit_bool(dl["show"])
        if dl.get("position"):
            lp["labelPosition"] = _lit_str(
                _LABEL_POSITION.get(str(dl["position"]).lower(), dl["position"]))
        du = _display_units_value(dl.get("displayUnits"))
        if du is not None:
            lp["labelDisplayUnits"] = _lit_num(du)
        if dl.get("decimalPlaces") is not None:
            lp["labelPrecision"] = _lit_num(dl["decimalPlaces"])
        # density — overlap threshold (section 3 clutter control).
        if dl.get("density") is not None:
            lp["labelDensity"] = _lit_num(dl["density"])
        # label background shading (section 8 — legibility over columns).
        if dl.get("backgroundColor") or dl.get("background"):
            lp["backgroundColor"] = _solid(dl.get("backgroundColor") or dl["background"])
            lp["showBackground"] = _lit_bool(True)
        if dl.get("showBackground") is not None:
            lp["showBackground"] = _lit_bool(dl["showBackground"])
        if lp:
            out["labels"] = _props(lp)

    # ── Legend ───────────────────────────────────────────────────────────
    lg = formatting.get("legend")
    if isinstance(lg, dict):
        gp = _text_props(lg, include_color_key="labelColor")
        if lg.get("show") is not None:
            gp["show"] = _lit_bool(lg["show"])
        if lg.get("position"):
            gp["position"] = _lit_str(
                _LEGEND_POSITION.get(str(lg["position"]).lower(), lg["position"]))
        if lg.get("title"):
            gp["showTitle"] = _lit_bool(True)
            gp["titleText"] = _lit_str(lg["title"])
        if gp:
            out["legend"] = _props(gp)

    # ── Callout value (card / KPI) → labels ──────────────────────────────
    # PBI's card callout value lives under the `labels` object too. Only emit
    # when no chart dataLabels were given (a visual is one or the other).
    callout = formatting.get("callout")
    if isinstance(callout, dict) and "labels" not in out:
        cp = _text_props(callout, include_color_key="color")
        du = _display_units_value(callout.get("displayUnits"))
        if du is not None:
            cp["labelDisplayUnits"] = _lit_num(du)
        if callout.get("decimalPlaces") is not None:
            cp["labelPrecision"] = _lit_num(callout["decimalPlaces"])
        if cp:
            out["labels"] = _props(cp)

    # ── Category label (card) → categoryLabels ───────────────────────────
    cat_label = formatting.get("categoryLabel")
    if isinstance(cat_label, dict):
        clp = _text_props(cat_label, include_color_key="color")
        if cat_label.get("show") is not None:
            clp["show"] = _lit_bool(cat_label["show"])
        if clp:
            out["categoryLabels"] = _props(clp)

    # ── Value axis ───────────────────────────────────────────────────────
    va = _build_value_axis(formatting.get("valueAxis"))
    if va:
        out["valueAxis"] = va

    # ── Category axis ────────────────────────────────────────────────────
    ca = _build_category_axis(formatting.get("categoryAxis"))
    if ca:
        out["categoryAxis"] = ca

    # ── Lines & markers ──────────────────────────────────────────────────
    lm = _build_lines_and_markers(formatting.get("linesAndMarkers"))
    out.update(lm)

    # ── Section 4: slicer controls (mode, selection, header, items, slider)
    for _k, _v in _build_slicer_objects(formatting).items():
        out.setdefault(_k, _v)
    # ── Section 5: table / matrix grid (grid, headers, values, banding) ───
    for _k, _v in _build_table_objects(formatting).items():
        out.setdefault(_k, _v)
    # ── Section 11: analytics overlays (reference/trend lines, forecast) ──
    for _k, _v in _build_analytics_objects(formatting).items():
        out.setdefault(_k, _v)
    # ── Sections 5/10: maps (style, bubbles, zoom, layers, legend bins) ──
    for _k, _v in _build_map_objects(formatting).items():
        out.setdefault(_k, _v)
    # ── Section 8: dual-axis / combo (secondary value axis) ──────────────
    for _k, _v in _build_combo_objects(formatting).items():
        out.setdefault(_k, _v)
    # ── Section 12: KPI / gauge / treemap specialised panels ─────────────
    for _k, _v in _build_kpi_gauge_objects(formatting).items():
        out.setdefault(_k, _v)
    # ── Section 9: advanced analytics & AI visuals (best-effort) ─────────
    for _k, _v in _build_ai_objects(formatting).items():
        out.setdefault(_k, _v)

    return out


def _build_data_points(dc) -> list:
    """dataPoint object. A single {"color": "#.."} → one default `fill`.
    A list of {"series","color"} → one entry per series with a selector."""
    if isinstance(dc, dict) and dc.get("color"):
        return _props({"fill": _solid(dc["color"])})
    if isinstance(dc, list):
        entries = []
        for item in dc:
            if not isinstance(item, dict) or not item.get("color"):
                continue
            props = {"fill": _solid(item["color"])}
            entry = {"properties": props}
            series = item.get("series")
            if series:
                # Selector binds the colour to a specific category/series value.
                entry["selector"] = {
                    "data": [{"dataViewWildcard": {"matchingOption": 0}}]
                } if series in ("*", "all") else {
                    "data": [{
                        "scopeId": {
                            "Literal": {"Value": f"'{str(series).replace(chr(39), chr(39)*2)}'"}
                        }
                    }]
                }
            entries.append(entry)
        return entries
    return []


def _build_value_axis(va) -> list:
    if not isinstance(va, dict):
        return []
    p: dict = {}
    if va.get("show") is not None:
        p["show"] = _lit_bool(va["show"])
    if va.get("min") is not None:
        p["start"] = _lit_num(va["min"])
    if va.get("max") is not None:
        p["end"] = _lit_num(va["max"])
    scale = va.get("scale") or ("Logarithmic" if va.get("logarithmic") else None)
    if scale:
        mapped = _AXIS_SCALE.get(str(scale).lower())
        if mapped:
            p["axisScale"] = _lit_str(mapped)
    title = va.get("title") or va.get("titleText")
    if title:
        p["showAxisTitle"] = _lit_bool(True)
        p["titleText"] = _lit_str(title)
    # Axis label display units / precision (section 3 axisLabels).
    du = _display_units_value(va.get("displayUnits"))
    if du is not None:
        p["labelDisplayUnits"] = _lit_num(du)
    if va.get("decimalPlaces") is not None:
        p["labelPrecision"] = _lit_num(va["decimalPlaces"])
    # Gridline control (section 3) — show/colour/thickness.
    if va.get("gridlines") is not None:
        p["gridlineShow"] = _lit_bool(va["gridlines"])
    if va.get("gridlineColor"):
        p["gridlineColor"] = _solid(va["gridlineColor"])
    p.update(_text_props(va, include_color_key="labelColor"))
    return _props(p)


def _build_category_axis(ca) -> list:
    if not isinstance(ca, dict):
        return []
    p: dict = {}
    if ca.get("show") is not None:
        p["show"] = _lit_bool(ca["show"])
    scale = ca.get("scale")
    if scale:
        mapped = _AXIS_TYPE.get(str(scale).lower())
        if mapped:
            p["axisType"] = _lit_str(mapped)
    title = ca.get("title") or ca.get("titleText")
    if title:
        p["showAxisTitle"] = _lit_bool(True)
        p["titleText"] = _lit_str(title)
    du = _display_units_value(ca.get("displayUnits"))
    if du is not None:
        p["labelDisplayUnits"] = _lit_num(du)
    p.update(_text_props(ca, include_color_key="labelColor"))
    return _props(p)


_LINE_STYLE = {"solid": "solid", "dashed": "dashed", "dotted": "dotted"}
_MARKER_SHAPE = {
    "circle": "circle", "square": "square", "diamond": "diamond",
    "triangle": "triangle", "x": "x", "plus": "plus",
}


def _build_lines_and_markers(lm) -> dict:
    """Return {} or {"lineStyles": [...], "markers": [...]}.  Best-effort —
    PBI's line/marker objects vary by visual; emit the common shape."""
    out: dict = {}
    if not isinstance(lm, dict):
        return out
    if lm.get("lineStyle"):
        style = _LINE_STYLE.get(str(lm["lineStyle"]).lower(), str(lm["lineStyle"]).lower())
        out["lineStyles"] = _props({"lineStyle": _lit_str(style)})
    mp: dict = {}
    if lm.get("markerShow") is not None:
        mp["show"] = _lit_bool(lm["markerShow"])
    if lm.get("markerShape"):
        mp["markerShape"] = _lit_str(
            _MARKER_SHAPE.get(str(lm["markerShape"]).lower(), lm["markerShape"]))
    if lm.get("markerSize") is not None:
        mp["markerSize"] = _lit_num(lm["markerSize"])
    if mp:
        out["markers"] = _props(mp)
    return out


# ════════════════════════════════════════════════════════════════════════════
# SECTION 1 — Page canvas  (page.json `objects` + type / displayOption)
# ════════════════════════════════════════════════════════════════════════════
_DISPLAY_OPTION = {
    "16:9": "FitToPage", "4:3": "FitToPage", "letter": "FitToPage",
    "custom": "ActualSize", "tooltip": "FitToPage",
    "fittopage": "FitToPage", "fittowidth": "FitToWidth",
    "actualsize": "ActualSize",
}

_PAGE_TYPE = {
    "standard": None,          # default page — no `type` key
    "tooltip": "Tooltip",
    "drillthrough": "Drillthrough",
    "preview": None,
}


def build_page_objects(canvas: dict, existing_objects: dict | None = None) -> dict:
    """Return the page.json `objects` block (background, outspace/wallpaper,
    displayArea/verticalAlignment) from `page.canvas`.

    `existing_objects` lets the caller merge image-background objects already
    produced by the Postgres image pipeline — the colour/transparency props
    from the canvas contract are layered onto the same object."""
    objects: dict = dict(existing_objects or {})
    if not isinstance(canvas, dict):
        return objects

    # ── Canvas background (page fill behind visuals) ─────────────────────
    bg = canvas.get("background")
    if isinstance(bg, dict):
        props = _page_fill_props(bg)
        if props:
            objects.setdefault("background", [{"properties": {}}])
            objects["background"][0].setdefault("properties", {}).update(props)

    # ── Wallpaper (the area OUTSIDE the canvas → `outspace`) ──────────────
    wp = canvas.get("wallpaper")
    if isinstance(wp, dict):
        props = _page_fill_props(wp)
        if props:
            objects.setdefault("outspace", [{"properties": {}}])
            objects["outspace"][0].setdefault("properties", {}).update(props)

    # ── Display area / vertical alignment ────────────────────────────────
    da_props: dict = {}
    if canvas.get("verticalAlignment"):
        da_props["verticalAlignment"] = _lit_str(canvas["verticalAlignment"])
    if da_props:
        objects["displayArea"] = _props(da_props)

    # ── Filter pane & filter cards (section 1) ───────────────────────────
    for _k, _v in _build_filter_pane_objects(canvas).items():
        objects[_k] = _v

    return objects


def _page_fill_props(fill: dict) -> dict:
    """color + transparency (+ optional image/imageFit) props shared by the
    canvas background and the wallpaper (outspace)."""
    props: dict = {}
    if fill.get("color"):
        props["color"] = _solid(fill["color"])
    if fill.get("transparency") is not None:
        props["transparency"] = _lit_num(fill["transparency"])
    # Direct image reference (public URL or Base64) — distinct from the
    # Postgres image-id pipeline, which the writer handles separately.
    img = fill.get("image")
    if img:
        scaling = _IMAGE_FIT.get(str(fill.get("imageFit") or "Fit").lower(), "Fit")
        props["image"] = {
            "name": _lit_str(fill.get("imageName") or "background"),
            "url": _lit_str(img),
            "scaling": _lit_str(scaling),
        }
    return props


# ── Filter pane (section 1) ──────────────────────────────────────────────────
# Contract (on page.canvas):
#   "filterPane": {"visibility": "Visible|Collapsed|Hidden", "width": 240,
#                  "background": "#..", "transparency": 0, "fontColor": "#..",
#                  "fontSize": 10, "borderColor": "#.."}
#   "filterCards": {"available": <CARD>, "applied": <CARD>}
#     <CARD> = {"background": "#..", "border": "#..", "fontColor": "#..",
#               "fontSize": 10, "transparency": 0}
# Per-filter `locking` (IsLocked / IsHidden) and `filterType` live on the
# filter definitions (filterConfig), not the page style objects — they are
# carried verbatim by the writer via page["filterConfig"] when the RE supplies
# them, and are out of scope for this colour/typography style layer.
def _build_filter_pane_objects(canvas: dict) -> dict:
    out: dict = {}
    fp = canvas.get("filterPane")
    if isinstance(fp, dict):
        p: dict = {}
        if fp.get("visibility"):
            # Pane shown unless explicitly Hidden.
            p["show"] = _lit_bool(str(fp["visibility"]).lower() != "hidden")
        if fp.get("width") is not None:
            p["width"] = _lit_num(fp["width"])
        if fp.get("background"):
            p["backgroundColor"] = _solid(fp["background"])
        if fp.get("transparency") is not None:
            p["transparency"] = _lit_num(fp["transparency"])
        if fp.get("fontColor"):
            p["foregroundColor"] = _solid(fp["fontColor"])
        if fp.get("fontSize") is not None:
            p["textSize"] = _lit_num(fp["fontSize"])
        if fp.get("borderColor"):
            p["borderColor"] = _solid(fp["borderColor"])
        if p:
            out["outspacePane"] = _props(p)

    cards = canvas.get("filterCards")
    if isinstance(cards, dict):
        entries = []
        # selector.id distinguishes the Available (unfiltered) vs Applied card.
        for key, sel_id in (("available", "Available"), ("applied", "Applied")):
            card = cards.get(key)
            if not isinstance(card, dict):
                continue
            cp: dict = {}
            if card.get("background"):
                cp["backgroundColor"] = _solid(card["background"])
            if card.get("border"):
                cp["borderColor"] = _solid(card["border"])
            if card.get("fontColor"):
                cp["foregroundColor"] = _solid(card["fontColor"])
            if card.get("fontSize") is not None:
                cp["textSize"] = _lit_num(card["fontSize"])
            if card.get("transparency") is not None:
                cp["transparency"] = _lit_num(card["transparency"])
            if cp:
                entries.append({"properties": cp, "selector": {"id": sel_id}})
        if entries:
            out["filterCard"] = entries
    return out


def page_display_option(canvas: dict, default: str = "FitToPage") -> str:
    """Map `canvas.displayArea` → page.json `displayOption`."""
    if isinstance(canvas, dict) and canvas.get("displayArea"):
        return _DISPLAY_OPTION.get(str(canvas["displayArea"]).lower(), default)
    return default


def page_type(canvas: dict):
    """Map `canvas.pageType` → page.json `type` (or None for a standard page)."""
    if isinstance(canvas, dict) and canvas.get("pageType"):
        return _PAGE_TYPE.get(str(canvas["pageType"]).lower())
    return None


# ════════════════════════════════════════════════════════════════════════════
# SECTION 10 — Report theme  (report.json themeCollection / custom theme file)
# ════════════════════════════════════════════════════════════════════════════
def build_custom_theme(theme: dict, base_theme: dict | None = None) -> dict | None:
    """Return a complete custom-theme JSON dict (to be written alongside the
    base theme and referenced from report.json) when the RE supplies palette
    overrides or visualStyles. Returns None when there's nothing to override.

    `base_theme` (the bundled CY22SU08) is used as the starting point so the
    custom theme inherits every token the RE didn't override."""
    if not isinstance(theme, dict):
        return None
    data_colors = theme.get("themeDataColors")
    visual_styles = theme.get("visualStyles")
    if not data_colors and not visual_styles and not theme.get("tokens"):
        return None

    out = dict(base_theme or {})
    out["name"] = theme.get("name") or "CustomTheme"
    if data_colors:
        out["dataColors"] = [_norm_hex(c) for c in data_colors]
    if isinstance(visual_styles, dict):
        # Merge over any visualStyles the base theme defined.
        merged = dict(out.get("visualStyles") or {})
        merged.update(visual_styles)
        out["visualStyles"] = merged
    # Semantic colour tokens (foreground / background / good / bad / …) override
    # the base theme's matching tokens so the brand palette fully applies.
    tokens = theme.get("tokens")
    if isinstance(tokens, dict):
        for k, v in tokens.items():
            if v:
                out[k] = _norm_hex(v)
    return out


# ════════════════════════════════════════════════════════════════════════════
# RE-SCHEMA NORMALIZERS
# The extraction engine (RE) emits a richer snake_case schema than the
# camelCase contract above, AND ships ready-made PBIP in `style.raw`
# (`objects` + `vcObjects`) per visual, `styles.raw` per page, a `theme` with
# `data_palette` / `semantic_colors`, and `bookmarks[].raw.explorationState`.
# These helpers map that real shape onto what the writer consumes. The `raw`
# PBIP is authoritative (the RE already translated colours, theme refs, fonts)
# so the writer emits it directly; we only re-shape theme + bookmarks here.
# ════════════════════════════════════════════════════════════════════════════
_SEMANTIC_TOKEN_MAP = {
    "foreground": "foreground", "background": "background",
    "foreground_neutral_secondary": "foregroundNeutralSecondary",
    "foreground_neutral_tertiary": "foregroundNeutralTertiary",
    "background_light": "backgroundLight", "background_neutral": "backgroundNeutral",
    "good": "good", "neutral": "neutral", "bad": "bad",
    "table_accent": "tableAccent", "hyperlink": "hyperlink",
    "maximum": "maximum", "minimum": "minimum", "center": "center", "null": "null",
}


def normalize_theme(re_theme: dict) -> dict | None:
    """Map the RE's `theme` ({name, data_palette[], semantic_colors{}}) — or an
    already-camelCase theme — onto the build_custom_theme contract
    ({name, themeDataColors[], tokens{}, visualStyles{}})."""
    if not isinstance(re_theme, dict):
        return None
    out: dict = {}
    if re_theme.get("name"):
        out["name"] = re_theme["name"]
    palette = re_theme.get("data_palette") or re_theme.get("themeDataColors")
    if palette:
        out["themeDataColors"] = list(palette)
    sem = re_theme.get("semantic_colors")
    if isinstance(sem, dict):
        tokens: dict = {}
        for k, v in sem.items():
            hexv = v.get("hex") if isinstance(v, dict) else v
            mapped = _SEMANTIC_TOKEN_MAP.get(k)
            if hexv and mapped:
                tokens[mapped] = hexv
        if tokens:
            out["tokens"] = tokens
    if isinstance(re_theme.get("visualStyles"), dict):
        out["visualStyles"] = re_theme["visualStyles"]
    if out.get("themeDataColors") or out.get("tokens") or out.get("visualStyles"):
        return out
    return None


def _hex_of(color):
    """Pull the hex string out of the RE's `{hex, ref, transparency}` colour
    object (or pass a plain string through). Returns None when there's no hex."""
    if isinstance(color, dict):
        return color.get("hex")
    return color


def _font_to_text_style(font: dict) -> dict:
    """Map the RE's snake_case font dict
    {family,size,bold,italic,underline,align,color,text} → the camelCase
    <TEXT_STYLE> the builders consume."""
    out: dict = {}
    if not isinstance(font, dict):
        return out
    if font.get("family"):
        out["fontFamily"] = font["family"]
    if font.get("size") is not None:
        out["fontSize"] = font["size"]
    if font.get("bold") is not None:
        out["bold"] = font["bold"]
    if font.get("italic") is not None:
        out["italic"] = font["italic"]
    if font.get("underline") is not None:
        out["underline"] = font["underline"]
    if font.get("align"):
        out["alignment"] = font["align"]
    hexv = _hex_of(font.get("color"))
    if hexv:
        out["color"] = hexv
    return out


def adapt_structured_style(style: dict) -> dict | None:
    """Map the RE's snake_case structured `style` block onto the camelCase
    `formatting` contract the builders consume.

    Used when the RE does NOT ship ready-made PBIP under `style.raw` — most
    importantly Tableau (whose `style.raw` carries Tableau-native quick-filter
    / mark metadata, not PBIP objects). For Power BI inputs (which DO ship
    `style.raw`) this is a harmless fallback: the authoritative raw still wins
    in the writer.

    Covers the colour-bearing blocks: container (title/subtitle/background/
    border/shadow/altText), callout + categoryLabel (cards), data_colors,
    data_labels, legend, and value/category axes. Slicer is best-effort.
    Every field is optional; colours are read as `.hex` from the RE's
    `{hex, ref, transparency}` objects (null hex → skipped).
    """
    if not isinstance(style, dict):
        return None
    fmt: dict = {}

    # ── General / container chrome ───────────────────────────────────────
    general: dict = {}
    title = style.get("title")
    if isinstance(title, dict):
        t = _font_to_text_style(title)
        if title.get("text"):
            t["text"] = title["text"]
        if t:
            general["title"] = t
    sub = style.get("subtitle")
    if isinstance(sub, dict):
        s = _font_to_text_style(sub)
        if sub.get("text"):
            s["text"] = sub["text"]
        if s:
            general["subtitle"] = s
    cont = style.get("container")
    if isinstance(cont, dict):
        bg = cont.get("background")
        if isinstance(bg, dict):
            b: dict = {}
            if bg.get("show") is not None:
                b["show"] = bg["show"]
            if _hex_of(bg.get("color")):
                b["color"] = _hex_of(bg["color"])
            if bg.get("transparency") is not None:
                b["transparency"] = bg["transparency"]
            if b:
                general["background"] = b
        bd = cont.get("border")
        if isinstance(bd, dict):
            b = {}
            if bd.get("show") is not None:
                b["show"] = bd["show"]
            if _hex_of(bd.get("color")):
                b["color"] = _hex_of(bd["color"])
            if bd.get("radius") is not None:
                b["radius"] = bd["radius"]
            if b:
                general["border"] = b
        sh = cont.get("shadow")
        if isinstance(sh, dict):
            b = {}
            if sh.get("show") is not None:
                b["show"] = sh["show"]
            if _hex_of(sh.get("color")):
                b["color"] = _hex_of(sh["color"])
            if sh.get("position"):
                b["position"] = sh["position"]
            if b:
                general["shadow"] = b
        if cont.get("alt_text"):
            general["altText"] = cont["alt_text"]
    if general:
        fmt["general"] = general

    # ── Card callout + category label ────────────────────────────────────
    callout = style.get("callout")
    if isinstance(callout, dict):
        c = _font_to_text_style(callout.get("value") or {})
        if callout.get("display_units"):
            c["displayUnits"] = callout["display_units"]
        if callout.get("decimal_places") is not None:
            c["decimalPlaces"] = callout["decimal_places"]
        if c:
            fmt["callout"] = c
        cl = callout.get("category_label")
        if isinstance(cl, dict):
            clp = _font_to_text_style(cl.get("font") or cl)
            if cl.get("show") is not None:
                clp["show"] = cl["show"]
            if clp:
                fmt["categoryLabel"] = clp

    # ── Data colours ─────────────────────────────────────────────────────
    dc = style.get("data_colors")
    if isinstance(dc, list):
        arr = []
        for item in dc:
            if not isinstance(item, dict):
                continue
            hexv = _hex_of(item.get("color"))
            if not hexv:
                continue
            arr.append({"series": item.get("value", "*"), "color": hexv})
        if arr:
            fmt["dataColors"] = arr

    # ── Data labels (prefer `data_labels`, fall back to generic `labels`) ─
    dl = style.get("data_labels") if isinstance(style.get("data_labels"), dict) else None
    lbls = style.get("labels") if isinstance(style.get("labels"), dict) else None
    src = dl or lbls
    if isinstance(src, dict):
        d = _font_to_text_style(src.get("font") or {})
        if src.get("show") is not None:
            d["show"] = src["show"]
        if src.get("position"):
            d["position"] = src["position"]
        if src.get("display_units"):
            d["displayUnits"] = src["display_units"]
        if src.get("decimal_places") is not None:
            d["decimalPlaces"] = src["decimal_places"]
        if src.get("background_show") is not None:
            d["showBackground"] = src["background_show"]
        if _hex_of(src.get("background_color")):
            d["backgroundColor"] = _hex_of(src["background_color"])
        if d:
            fmt["dataLabels"] = d

    # ── Legend ───────────────────────────────────────────────────────────
    lg = style.get("legend")
    if isinstance(lg, dict):
        l = _font_to_text_style(lg.get("labels") or {})
        if lg.get("show") is not None:
            l["show"] = lg["show"]
        if lg.get("position"):
            l["position"] = lg["position"]
        if lg.get("title"):
            l["title"] = lg["title"]
        if l:
            fmt["legend"] = l

    # ── Axes (category / value) ──────────────────────────────────────────
    axes = style.get("axes")
    if isinstance(axes, list):
        for ax in axes:
            if not isinstance(ax, dict):
                continue
            a = _font_to_text_style(ax.get("labels") or {})
            if ax.get("title"):
                a["title"] = ax["title"]
            if ax.get("scale"):
                a["scale"] = ax["scale"]
            if ax.get("min") is not None:
                a["min"] = ax["min"]
            if ax.get("max") is not None:
                a["max"] = ax["max"]
            if ax.get("display_units"):
                a["displayUnits"] = ax["display_units"]
            if ax.get("gridlines") is not None:
                a["gridlines"] = ax["gridlines"]
            if not a:
                continue
            name = (ax.get("name") or "").lower()
            if name in ("value", "y", "value_axis"):
                fmt["valueAxis"] = a
            elif name in ("category", "x", "category_axis"):
                fmt["categoryAxis"] = a

    # ── Slicer (best-effort) ─────────────────────────────────────────────
    sl = style.get("slicer")
    if isinstance(sl, dict):
        slicer: dict = {}
        if sl.get("type") or sl.get("slicer_type"):
            slicer["slicerType"] = sl.get("type") or sl.get("slicer_type")
        if _hex_of(sl.get("outline_color")):
            slicer["outlineColor"] = _hex_of(sl["outline_color"])
        if slicer:
            fmt["slicer"] = slicer
        hdr = sl.get("header")
        if isinstance(hdr, dict):
            h = _font_to_text_style(hdr.get("font") or hdr)
            if hdr.get("show") is not None:
                h["show"] = hdr["show"]
            if hdr.get("text") or hdr.get("title"):
                h["text"] = hdr.get("text") or hdr.get("title")
            if h:
                fmt["slicerHeader"] = h

    return fmt or None


def sanitize_raw_objects(raw: dict) -> dict:
    """Safety net for the RE's ready-made PBIP passthrough.

    Returns only well-formed object entries — each object value must be a list
    of `{properties: {...}}` dicts (the PBIP shape). Anything malformed (a
    non-list value, a non-dict entry, or an entry without a `properties`
    object) is DROPPED rather than emitted, so a single bad block from the RE
    can never make Power BI refuse to open the whole report. Worst case a
    visual loses one formatting block; the report still loads.
    """
    if not isinstance(raw, dict):
        return {}
    clean: dict = {}
    for obj_name, entries in raw.items():
        if not isinstance(entries, list):
            continue
        good = [e for e in entries
                if isinstance(e, dict) and isinstance(e.get("properties"), dict)]
        if good:
            clean[obj_name] = good
    return clean


def normalize_bookmarks(re_bookmarks) -> list | None:
    """Map the RE's `bookmarks` (snake_case + `raw.explorationState`) — or an
    already-camelCase list — onto the build_bookmark contract."""
    if not isinstance(re_bookmarks, list):
        return None
    out = []
    for bm in re_bookmarks:
        if not isinstance(bm, dict):
            continue
        raw = bm.get("raw") if isinstance(bm.get("raw"), dict) else {}
        state = bm.get("explorationState") or raw.get("explorationState")
        out.append({
            # Preserve the original bookmark id so navigation buttons that target
            # it by name still resolve in the generated report.
            "name": bm.get("name") or raw.get("name"),
            "displayName": bm.get("display_name") or bm.get("displayName") or bm.get("name"),
            "explorationState": state,
            "captureData": bm.get("capture_data", bm.get("captureData")),
            "captureDisplay": bm.get("capture_display", bm.get("captureDisplay")),
            "captureCurrentPage": bm.get("capture_current_page", bm.get("captureCurrentPage")),
        })
    return out or None


# ════════════════════════════════════════════════════════════════════════════
# SECTION 4 — Slicer controls
#   visual.objects: data (mode), general (orientation/outline), selection,
#                   header, items, slider
#
# Contract (on visual["formatting"]):
#   "slicer": {"slicerType": "VerticalList|Dropdown|Between|Tile|Slider",
#              "orientation": "Vertical|Horizontal",
#              "outlineColor": "#..", "outlineWeight": 1}
#   "selectionControls": {"singleSelect": bool, "multiSelect": bool,
#                         "showSelectAll": bool, "strictSingleSelect": bool}
#   "slicerHeader": <TEXT_STYLE> + {"show": bool, "text": "...", "background": "#.."}
#   "slicerValues": <TEXT_STYLE> + {"background": "#.."}
#   "sliderColor": "#.."  |  {"color": "#.."}
# ════════════════════════════════════════════════════════════════════════════
_SLICER_MODE = {
    "verticallist": "Basic", "list": "Basic", "basic": "Basic",
    "dropdown": "Dropdown",
    "between": "Between", "slider": "Between",
    "tile": "Basic",
}


def _build_slicer_objects(formatting: dict) -> dict:
    out: dict = {}
    if not isinstance(formatting, dict):
        return out

    slicer = formatting.get("slicer")
    st = ""
    if isinstance(slicer, dict):
        st = str(slicer.get("slicerType") or "")
        mode = _SLICER_MODE.get(st.lower())
        if mode:
            out["data"] = _props({"mode": _lit_str(mode)})
        gp: dict = {}
        orient = slicer.get("orientation") or ("Horizontal" if st.lower() == "tile" else None)
        if orient:
            gp["orientation"] = _lit_str(str(orient).lower())
        if slicer.get("outlineColor"):
            gp["outlineColor"] = _solid(slicer["outlineColor"])
        if slicer.get("outlineWeight") is not None:
            gp["outlineWeight"] = _lit_num(slicer["outlineWeight"])
        # Responsive auto-resize (section 6).
        if slicer.get("responsive") is not None:
            gp["responsive"] = _lit_bool(slicer["responsive"])
        if gp:
            out["general"] = _props(gp)

    sc = formatting.get("selectionControls")
    if isinstance(sc, dict):
        sp: dict = {}
        if sc.get("singleSelect") is not None:
            sp["singleSelect"] = _lit_bool(sc["singleSelect"])
        if sc.get("multiSelect") is not None:
            sp["singleSelect"] = _lit_bool(not sc["multiSelect"])
        if sc.get("strictSingleSelect") is not None:
            sp["strictSingleSelect"] = _lit_bool(sc["strictSingleSelect"])
        if sc.get("showSelectAll") is not None:
            sp["selectAllCheckboxEnabled"] = _lit_bool(sc["showSelectAll"])
        if sp:
            out["selection"] = _props(sp)

    hdr = formatting.get("slicerHeader")
    if isinstance(hdr, dict):
        hp = _text_props(hdr, include_color_key="fontColor")
        if hdr.get("show") is not None:
            hp["show"] = _lit_bool(hdr["show"])
        if hdr.get("text"):
            hp["text"] = _lit_str(hdr["text"])
        if hdr.get("background"):
            hp["background"] = _solid(hdr["background"])
        if hp:
            out["header"] = _props(hp)

    # clearSelection — the clear/eraser icon lives in the slicer header, so a
    # request to keep it visible implies the header is shown (section 6).
    if formatting.get("clearSelection"):
        hdr_props = out.setdefault("header", [{"properties": {}}])
        hdr_props[0].setdefault("properties", {}).setdefault("show", _lit_bool(True))

    vals = formatting.get("slicerValues")
    if isinstance(vals, dict):
        ip = _text_props(vals, include_color_key="fontColor")
        if vals.get("background"):
            ip["background"] = _solid(vals["background"])
        if ip:
            out["items"] = _props(ip)

    sld = formatting.get("sliderColor")
    color = sld.get("color") if isinstance(sld, dict) else sld
    if color:
        out["slider"] = _props({"color": _solid(color)})

    return out


# ════════════════════════════════════════════════════════════════════════════
# SECTION 5 — Table / matrix grid
#   visual.objects: grid, columnHeaders, rowHeaders, values, dataBars
#
# Contract (on visual["formatting"]):
#   "gridlines": {"horizontal": bool, "vertical": bool, "color": "#..", "weight": 1}
#   "rowPadding": 2
#   "columnHeaders"/"rowHeaders": <TEXT_STYLE> + {"background": "#..",
#                                  "alignment": "left|center|right", "wordWrap": bool}
#   "tableValues": <TEXT_STYLE> + {"backColor": "#.."}
#   "alternatingRows": {"primaryColor","secondaryColor",
#                       "primaryFontColor","secondaryFontColor"}
#   "cellElements": {"backgroundColor": "#..", "dataBars": bool,
#                    "positiveColor": "#..", "negativeColor": "#.."}  (best-effort)
# ════════════════════════════════════════════════════════════════════════════
def _header_props(hdr: dict) -> dict:
    p = _text_props(hdr, include_color_key="fontColor")
    fill = hdr.get("background") or hdr.get("backColor")
    if fill:
        p["backColor"] = _solid(fill)
    if hdr.get("alignment"):
        p["alignment"] = _lit_str(_ALIGN_MAP.get(str(hdr["alignment"]).lower(), hdr["alignment"]))
    if hdr.get("wordWrap") is not None:
        p["wordWrap"] = _lit_bool(hdr["wordWrap"])
    return p


def _build_table_objects(formatting: dict) -> dict:
    out: dict = {}
    if not isinstance(formatting, dict):
        return out

    gl = formatting.get("gridlines")
    grid: dict = {}
    if isinstance(gl, dict):
        if gl.get("horizontal") is not None:
            grid["gridHorizontal"] = _lit_bool(gl["horizontal"])
        if gl.get("vertical") is not None:
            grid["gridVertical"] = _lit_bool(gl["vertical"])
        if gl.get("color"):
            grid["gridHorizontalColor"] = _solid(gl["color"])
            grid["gridVerticalColor"] = _solid(gl["color"])
        if gl.get("weight") is not None:
            grid["gridHorizontalWeight"] = _lit_num(gl["weight"])
            grid["gridVerticalWeight"] = _lit_num(gl["weight"])
    if formatting.get("rowPadding") is not None:
        grid["rowPadding"] = _lit_num(formatting["rowPadding"])
    if grid:
        out["grid"] = _props(grid)

    ch = formatting.get("columnHeaders")
    if isinstance(ch, dict):
        p = _header_props(ch)
        if p:
            out["columnHeaders"] = _props(p)
    rh = formatting.get("rowHeaders")
    if isinstance(rh, dict):
        p = _header_props(rh)
        if p:
            out["rowHeaders"] = _props(p)

    vp: dict = {}
    tv = formatting.get("tableValues")
    if isinstance(tv, dict):
        vp.update(_text_props(tv, include_color_key="fontColor"))
        fill = tv.get("backColor") or tv.get("background")
        if fill:
            vp["backColor"] = _solid(fill)
    alt = formatting.get("alternatingRows")
    if isinstance(alt, dict):
        if alt.get("primaryColor"):
            vp["backColor"] = _solid(alt["primaryColor"])
        if alt.get("secondaryColor"):
            vp["backColorSecondary"] = _solid(alt["secondaryColor"])
        if alt.get("primaryFontColor"):
            vp["fontColor"] = _solid(alt["primaryFontColor"])
        if alt.get("secondaryFontColor"):
            vp["fontColorSecondary"] = _solid(alt["secondaryFontColor"])

    # Conditional cell elements — best-effort static colour + data-bar toggle.
    # Full rule-based conditional formatting (gradients keyed to a measure)
    # needs a field binding the style layer doesn't carry, so it is out of scope.
    ce = formatting.get("cellElements")
    if isinstance(ce, dict):
        if ce.get("backgroundColor"):
            vp["backColor"] = _solid(ce["backgroundColor"])
        if ce.get("dataBars"):
            db: dict = {"show": _lit_bool(True)}
            if ce.get("positiveColor"):
                db["positiveColor"] = _solid(ce["positiveColor"])
            if ce.get("negativeColor"):
                db["negativeColor"] = _solid(ce["negativeColor"])
            out["dataBars"] = _props(db)

    if vp:
        out["values"] = _props(vp)

    # Totals / subtotals (section 4) → `subTotals` object + `total` typography.
    totals = formatting.get("totals")
    if isinstance(totals, dict):
        sp: dict = {}
        if totals.get("rowTotals") is not None:
            sp["rowSubtotals"] = _lit_bool(totals["rowTotals"])
        if totals.get("columnTotals") is not None:
            sp["columnSubtotals"] = _lit_bool(totals["columnTotals"])
        if totals.get("rowStepping") is not None:
            sp["rowSubtotalsType"] = _lit_str("Stepped" if totals["rowStepping"] else "Adjacent")
        if totals.get("label"):
            sp["totalLabel"] = _lit_str(totals["label"])
        if sp:
            out["subTotals"] = _props(sp)
        # Total row typography (background/font) → `total` object.
        tp: dict = {}
        if totals.get("background"):
            tp["backColor"] = _solid(totals["background"])
        if totals.get("fontColor"):
            tp["fontColor"] = _solid(totals["fontColor"])
        if totals.get("bold") is not None:
            tp["bold"] = _lit_bool(totals["bold"])
        if tp:
            out["total"] = _props(tp)

    return out


# ════════════════════════════════════════════════════════════════════════════
# SECTION 11 — Analytics overlays
#   visual.objects: referenceLine (constant/avg/min/max/median), trend, forecast
#
# Contract (on visual["formatting"]):
#   "referenceLines": [{"type": "Constant|Average|Median|Min|Max|Trend",
#                       "value": 100, "label": "...", "color": "#..",
#                       "style": "Solid|Dashed|Dotted", "position": "Front|Behind"}]
#   "trendLine": {"show": bool, "color": "#..", "style": "Solid|Dashed|Dotted"}
#   "forecast":  {"show": bool, "forecastPoints": 5, "confidenceInterval": "95%"}
# ════════════════════════════════════════════════════════════════════════════
_LINE_DASH = {"solid": "solid", "dashed": "dashed", "dotted": "dotted"}
_CONFIDENCE = {
    "95%": 0.95, "99%": 0.99, "90%": 0.90, "85%": 0.85, "80%": 0.80, "75%": 0.75,
    "0.95": 0.95, "0.99": 0.99, "0.9": 0.90, "0.85": 0.85, "0.8": 0.80, "0.75": 0.75,
}


def _build_analytics_objects(formatting: dict) -> dict:
    out: dict = {}
    if not isinstance(formatting, dict):
        return out

    rlines = formatting.get("referenceLines")
    entries = []
    if isinstance(rlines, list):
        for rl in rlines:
            if not isinstance(rl, dict):
                continue
            p: dict = {}
            if rl.get("value") is not None:
                # PBI stores the constant-line value as a text literal.
                p["value"] = _lit_str(str(rl["value"]))
            label = rl.get("label") or rl.get("type")
            if label:
                p["dataLabelShow"] = _lit_bool(True)
                p["displayName"] = _lit_str(label)
            if rl.get("color"):
                p["lineColor"] = _solid(rl["color"])
            if rl.get("style"):
                p["style"] = _lit_str(_LINE_DASH.get(str(rl["style"]).lower(), str(rl["style"]).lower()))
            if rl.get("position"):
                p["position"] = _lit_str(rl["position"])
            if p:
                entries.append({"properties": p, "selector": {"id": _uuid.uuid4().hex[:12]}})
    if entries:
        out["referenceLine"] = entries

    tl = formatting.get("trendLine")
    if isinstance(tl, dict):
        tp: dict = {}
        if tl.get("show") is not None:
            tp["show"] = _lit_bool(tl["show"])
        if tl.get("color"):
            tp["lineColor"] = _solid(tl["color"])
        if tl.get("style"):
            tp["style"] = _lit_str(_LINE_DASH.get(str(tl["style"]).lower(), str(tl["style"]).lower()))
        if tp:
            out["trend"] = _props(tp)

    fc = formatting.get("forecast")
    if isinstance(fc, dict):
        fp: dict = {}
        if fc.get("show") is not None:
            fp["show"] = _lit_bool(fc["show"])
        if fc.get("forecastPoints") is not None:
            fp["forecastLength"] = _lit_num(fc["forecastPoints"])
        ci = fc.get("confidenceInterval")
        if ci is not None:
            civ = _CONFIDENCE.get(str(ci).strip().lower(),
                                  ci if isinstance(ci, (int, float)) else None)
            if civ is not None:
                fp["confidenceInterval"] = _lit_num(civ)
        if fp:
            out["forecast"] = _props(fp)

    return out


# ════════════════════════════════════════════════════════════════════════════
# SECTIONS 5 & 10 — Maps (filled / bubble / shape / Azure)
#   visual.objects: mapControls/bubbles/legend (best-effort — PBI map object
#   names vary by map type; emitted defensively).
#
# Contract (on visual["formatting"]):
#   "map": {"mapStyle": "Road|Aerial|Dark|Light|Grayscale",
#           "bubbleSizeMin": 5, "bubbleSizeMax": 30,
#           "zoomMin": 1, "zoomMax": 18, "pitchMin": 0, "pitchMax": 60,
#           "layers": ["Bubble","BarChart","Traffic"]}
#   "legendRanges": [{"from": 0, "to": 100, "color": "#.."}]  (color binning)
# NOTE: geocoding (lat/long fields) and dataCategory (City/State/Country) are
# DATA-MODEL concerns set on the column, not visual style — out of scope here.
# ════════════════════════════════════════════════════════════════════════════
_MAP_STYLE = {"road": "road", "aerial": "aerial", "dark": "dark",
              "light": "canvasLight", "grayscale": "grayscale_light",
              "canvaslight": "canvasLight", "canvasdark": "canvasDark"}


def _build_map_objects(formatting: dict) -> dict:
    out: dict = {}
    if not isinstance(formatting, dict):
        return out
    mp = formatting.get("map")
    if isinstance(mp, dict):
        controls: dict = {}
        if mp.get("mapStyle"):
            controls["mapTheme"] = _lit_str(_MAP_STYLE.get(str(mp["mapStyle"]).lower(), mp["mapStyle"]))
        if mp.get("zoomMin") is not None:
            controls["minZoom"] = _lit_num(mp["zoomMin"])
        if mp.get("zoomMax") is not None:
            controls["maxZoom"] = _lit_num(mp["zoomMax"])
        if mp.get("pitchMin") is not None:
            controls["minPitch"] = _lit_num(mp["pitchMin"])
        if mp.get("pitchMax") is not None:
            controls["maxPitch"] = _lit_num(mp["pitchMax"])
        if controls:
            out["mapControls"] = _props(controls)
        bub: dict = {}
        if mp.get("bubbleSizeMin") is not None:
            bub["minSize"] = _lit_num(mp["bubbleSizeMin"])
        if mp.get("bubbleSizeMax") is not None:
            bub["maxSize"] = _lit_num(mp["bubbleSizeMax"])
        if bub:
            out["bubbles"] = _props(bub)
        layers = mp.get("layers")
        if isinstance(layers, list) and layers:
            out["mapLayers"] = _props({"layers": _lit_str(",".join(str(x) for x in layers))})

    # Legend colour binning (fixed step colours) → fillPoint/legend ranges.
    ranges = formatting.get("legendRanges")
    if isinstance(ranges, list) and ranges:
        entries = []
        for r in ranges:
            if not isinstance(r, dict) or not r.get("color"):
                continue
            rp = {"fillColor": _solid(r["color"])}
            if r.get("from") is not None:
                rp["startValue"] = _lit_num(r["from"])
            if r.get("to") is not None:
                rp["endValue"] = _lit_num(r["to"])
            entries.append({"properties": rp, "selector": {"id": _uuid.uuid4().hex[:12]}})
        if entries:
            out["fillRules"] = entries
    return out


# ════════════════════════════════════════════════════════════════════════════
# SECTION 8 — Dual-axis / combo charts
#   visual.objects: y2Axis (secondary value axis), valueAxis.alignZeros,
#                   label shading handled in the dataLabels block above.
#
# Contract (on visual["formatting"]):
#   "secondaryValueAxis": <AXIS> + {"alignZeros": bool}
# ════════════════════════════════════════════════════════════════════════════
def _build_combo_objects(formatting: dict) -> dict:
    out: dict = {}
    if not isinstance(formatting, dict):
        return out
    sa = formatting.get("secondaryValueAxis")
    if isinstance(sa, dict):
        p: dict = {}
        if sa.get("show") is not None:
            p["secShow"] = _lit_bool(sa["show"])
        if sa.get("min") is not None:
            p["secStart"] = _lit_num(sa["min"])
        if sa.get("max") is not None:
            p["secEnd"] = _lit_num(sa["max"])
        title = sa.get("title") or sa.get("titleText")
        if title:
            p["secShowAxisTitle"] = _lit_bool(True)
            p["secTitleText"] = _lit_str(title)
        if sa.get("alignZeros") is not None:
            p["alignZeros"] = _lit_bool(sa["alignZeros"])
        if sa.get("color"):
            p["secLabelColor"] = _solid(sa["color"])
        if p:
            out["y2Axis"] = _props(p)
    return out


# ════════════════════════════════════════════════════════════════════════════
# SECTION 12 — KPI / gauge / treemap specialised panels
#
# Contract (on visual["formatting"]):
#   "kpi":     {"trendAxisShow": bool, "valueColor": "#..", "directionGoodColor": "#.."}
#   "gauge":   {"min": 0, "max": 100, "target": 80,
#               "fillColor": "#..", "targetColor": "#.."}
#   "treemap": {"maxCategories": 12}
# ════════════════════════════════════════════════════════════════════════════
def _build_kpi_gauge_objects(formatting: dict) -> dict:
    out: dict = {}
    if not isinstance(formatting, dict):
        return out

    kpi = formatting.get("kpi")
    if isinstance(kpi, dict):
        tp: dict = {}
        if kpi.get("trendAxisShow") is not None:
            tp["show"] = _lit_bool(kpi["trendAxisShow"])
        if tp:
            out["trendline"] = _props(tp)
        ip: dict = {}
        if kpi.get("valueColor"):
            ip["fontColor"] = _solid(kpi["valueColor"])
        if ip:
            out["indicator"] = _props(ip)

    gauge = formatting.get("gauge")
    if isinstance(gauge, dict):
        ax: dict = {}
        if gauge.get("min") is not None:
            ax["min"] = _lit_num(gauge["min"])
        if gauge.get("max") is not None:
            ax["max"] = _lit_num(gauge["max"])
        if gauge.get("target") is not None:
            ax["target"] = _lit_num(gauge["target"])
        if ax:
            out["axis"] = _props(ax)
        fp: dict = {}
        if gauge.get("fillColor"):
            fp["fill"] = _solid(gauge["fillColor"])
        if gauge.get("targetColor"):
            fp["target"] = _solid(gauge["targetColor"])
        if fp:
            out["dataPoint"] = _props(fp)

    tm = formatting.get("treemap")
    if isinstance(tm, dict) and tm.get("maxCategories") is not None:
        # Treemap category cap — emitted as a dataReduction hint on the visual.
        out["dataReductionCap"] = _props({"maxCategories": _lit_num(tm["maxCategories"])})
    return out


# ════════════════════════════════════════════════════════════════════════════
# SECTION 9 — Advanced analytics & AI visuals (best-effort)
#
# Contract (on visual["formatting"]):
#   "ai": {"enableAiSplits": bool,
#          "suggestedQuestions": ["...", "..."]}   # Q&A
# NOTE: Key-Influencers `analysisFields` and Smart-Narrative `dynamicValues`
# are DATA bindings (fields / DAX), not style — carried elsewhere, not here.
# ════════════════════════════════════════════════════════════════════════════
def _build_ai_objects(formatting: dict) -> dict:
    out: dict = {}
    if not isinstance(formatting, dict):
        return out
    ai = formatting.get("ai")
    if isinstance(ai, dict):
        if ai.get("enableAiSplits") is not None:
            out["analysisType"] = _props({"enabled": _lit_bool(ai["enableAiSplits"])})
        sq = ai.get("suggestedQuestions")
        if isinstance(sq, list) and sq:
            out["suggestedQuestions"] = _props({
                "questions": _lit_str("\n".join(str(q) for q in sq))})
    return out


# ════════════════════════════════════════════════════════════════════════════
# SECTION 7 — Button action (visualContainerObjects.visualLink) + visual states
#
# Contract (on visual["formatting"]):
#   "action": {"actionType": "PageNavigation|Bookmark|WebURL|Drillthrough|Back",
#              "target": "<page display name | bookmark name>",
#              "url": "https://...", "tooltip": "..."}
#   "stateSelector": {"default": {"fill": "#..", "textColor": "#.."},
#                     "hover": {...}, "press": {...}, "disabled": {...}}
# ════════════════════════════════════════════════════════════════════════════
_ACTION_TYPE = {
    "pagenavigation": "PageNavigation", "page": "PageNavigation", "navigation": "PageNavigation",
    "bookmark": "Bookmark",
    "weburl": "WebUrl", "web": "WebUrl", "url": "WebUrl",
    "drillthrough": "Drillthrough",
    "back": "Back", "qna": "QnA",
    "applyallslicers": "ApplyAllSlicers", "clearallslicers": "ClearAllSlicers",
}


def _build_action_object(action: dict, page_ids: dict | None) -> list:
    if not isinstance(action, dict):
        return []
    atype = _ACTION_TYPE.get(str(action.get("actionType") or action.get("type") or "").lower())
    if not atype:
        return []
    p: dict = {"show": _lit_bool(True), "type": _lit_str(atype)}
    target = action.get("target") or action.get("actionTarget")
    url = action.get("url") or action.get("actionUrl")
    pmap = page_ids or {}
    if atype == "Bookmark" and target:
        p["bookmark"] = _lit_str(target)
    elif atype == "PageNavigation" and target:
        p["navigationSection"] = _lit_str(pmap.get(target, target))
    elif atype == "Drillthrough" and target:
        p["drillthroughSection"] = _lit_str(pmap.get(target, target))
    elif atype == "WebUrl" and url:
        p["webUrl"] = _lit_str(url)
    if action.get("tooltip"):
        p["tooltip"] = _lit_str(action["tooltip"])
    return _props(p)


_STATE_IDS = {
    "default": "default", "hover": "hover", "press": "pressed",
    "pressed": "pressed", "disabled": "disabled", "selected": "selected",
}


def _build_state_objects(states: dict) -> dict:
    """Best-effort per-state fill / text colour for buttons & shapes (Dynamic
    Visual States). Each entry carries a `{selector:{id:<state>}}` so
    Default / Hover / Press / Disabled render distinctly."""
    out: dict = {}
    if not isinstance(states, dict):
        return out
    fills, texts = [], []
    for state_name, spec in states.items():
        if not isinstance(spec, dict):
            continue
        sid = _STATE_IDS.get(str(state_name).lower())
        if not sid:
            continue
        if spec.get("fill"):
            fills.append({"properties": {"fillColor": _solid(spec["fill"])},
                          "selector": {"id": sid}})
        if spec.get("textColor") or spec.get("color"):
            texts.append({"properties": {"fontColor": _solid(spec.get("textColor") or spec.get("color"))},
                          "selector": {"id": sid}})
    if fills:
        out["fill"] = fills
    if texts:
        out["text"] = texts
    return out


# ════════════════════════════════════════════════════════════════════════════
# SECTION 9 — Inline rich text  (textbox objects.general.paragraphs)
#
# Contract (on visual["formatting"]):
#   "richText": {"paragraphs": [{"alignment": "left|center|right",
#                "textRuns": [{"text": "...", "fontFamily": "...",
#                              "fontSize": 12, "bold": bool, "italic": bool,
#                              "underline": bool, "color": "#..", "url": "..."}]}]}
# ════════════════════════════════════════════════════════════════════════════
def build_textbox_paragraphs(formatting: dict, fallback_content: str = "") -> list:
    """Return the textbox `paragraphs` array from `formatting.richText`, with
    per-run typography (font, size, weight, colour, decoration, hyperlink).
    Falls back to splitting `fallback_content` into plain paragraphs (the
    legacy behaviour) when no richText block is supplied."""
    rt = (formatting or {}).get("richText") if isinstance(formatting, dict) else None
    if isinstance(rt, dict) and isinstance(rt.get("paragraphs"), list):
        paragraphs = []
        for para in rt["paragraphs"]:
            if not isinstance(para, dict):
                continue
            runs = [_build_text_run(r) for r in para.get("textRuns", []) if isinstance(r, dict)]
            align = para.get("alignment")
            paragraphs.append({
                "horizontalTextAlignment": _ALIGN_MAP.get(str(align).lower(), "left") if align else "left",
                "textRuns": runs,
            })
        if paragraphs:
            return paragraphs
    if fallback_content:
        return [{"horizontalTextAlignment": "left", "textRuns": [{"value": line}]}
                for line in str(fallback_content).split("\n")]
    return []


def _build_text_run(run: dict) -> dict:
    """A single rich-text run with an inline textStyle. `dynamicValue` /
    `expression` (smart-narrative DAX) is carried best-effort as plain text —
    a full data-driven binding is out of scope for the core style layer."""
    out: dict = {"value": run.get("text", run.get("value", ""))}
    ts: dict = {}
    if run.get("fontFamily"):
        ts["fontFamily"] = run["fontFamily"]
    if run.get("fontSize") is not None:
        ts["fontSize"] = f"{run['fontSize']}pt"
    if run.get("bold"):
        ts["fontWeight"] = "bold"
    if run.get("italic"):
        ts["fontStyle"] = "italic"
    if run.get("underline"):
        ts["textDecoration"] = "underline"
    if run.get("color"):
        ts["color"] = _norm_hex(run["color"])
    if ts:
        out["textStyle"] = ts
    if run.get("url"):
        out["url"] = run["url"]
    return out


# ════════════════════════════════════════════════════════════════════════════
# SECTION 8 — Edit interactions & cross-filtering  (page.json visualInteractions)
#
# Contract (on page object):
#   "interactions": [{"source": "<RE visual id>", "target": "<RE visual id>",
#                     "interactionType": "Filter|Highlight|None"}]
# `id_map` translates RE visual identifiers → generated PBIP visual names.
# (dimmingPercentage and syncSlicers are report-wide concerns handled at a
#  higher level; they are intentionally not emitted per-page here.)
# ════════════════════════════════════════════════════════════════════════════
_INTERACTION_TYPE = {
    "filter": "Filter", "datafilter": "Filter",
    "highlight": "Highlight",
    "none": "NoFilter", "nofilter": "NoFilter", "no": "NoFilter",
}


def build_visual_interactions(interactions, id_map: dict) -> list:
    out = []
    if not isinstance(interactions, list):
        return out
    for it in interactions:
        if not isinstance(it, dict):
            continue
        src = (id_map or {}).get(it.get("source"))
        tgt = (id_map or {}).get(it.get("target"))
        itype = _INTERACTION_TYPE.get(
            str(it.get("interactionType") or it.get("type") or "").lower())
        if not (src and tgt and itype):
            continue
        out.append({"source": src, "target": tgt, "type": itype})
    return out


# ════════════════════════════════════════════════════════════════════════════
# SECTION 7 — Bookmarks  (definition/bookmarks/*.bookmark.json + bookmarks.json)
#
# Contract (on mapped["bookmarks"]):
#   [{"displayName": "...", "explorationState": {...captured PBI state...},
#     "captureData": bool, "captureDisplay": bool, "captureCurrentPage": bool}]
#
# A bookmark's value is its captured `explorationState`. The style layer cannot
# synthesise a valid state from scratch (it spans the whole report), so a
# bookmark WITHOUT an `explorationState` is skipped rather than emitted broken.
# The capture flags map onto the bookmark `options`.
# ════════════════════════════════════════════════════════════════════════════
def build_bookmark(bm: dict, new_name: str) -> dict | None:
    if not isinstance(bm, dict):
        return None
    state = bm.get("explorationState")
    if not isinstance(state, dict):
        return None  # cannot fabricate a valid state — skip safely
    out = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/bookmark/1.1.0/schema.json",
        "name": new_name,
        "displayName": bm.get("displayName") or bm.get("name") or new_name,
        "explorationState": state,
    }
    opts: dict = {}
    if bm.get("captureData") is not None:
        opts["suppressData"] = not bm["captureData"]
    if bm.get("captureCurrentPage") is not None:
        opts["suppressActiveSection"] = not bm["captureCurrentPage"]
    # NOTE: `suppressVisualDisplay` is NOT a valid bookmark option in the PBIP
    # schema (Power BI rejects it: "property has not been defined and the
    # schema does not allow additional properties"). The Selection-Pane
    # visibility a bookmark captures lives inside `explorationState`, not in
    # `options`, so captureDisplay has no `options` mapping — intentionally
    # omitted.
    if opts:
        out["options"] = opts
    return out
