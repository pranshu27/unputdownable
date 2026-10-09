"""
style_extractor.py
-------------------
Deterministic colors / themes / styles extraction for the Common Model.

NO LLM. NO GUESSING. Values are copied verbatim from the source files
(PowerBI Layout + theme JSON, Tableau .twb XML). A field stays null / [] when
the source does not specify it.

Common styling shape (tool-agnostic):

    ColorRef = { "hex": "#094780",        # resolved/literal value (null if unknown)
                 "ref": "dataColors[5]@-20%",  # null when literal
                 "transparency": 0 }      # 0-100, null when unset

    Font     = { "family", "size", "bold", "italic", "underline",
                 "align", "color": ColorRef, "text" }

    theme    = { "name", "source_tool", "data_palette": [...],
                 "named_palettes": [{name,colors}], "semantic_colors": {...},
                 "text_classes": { "title":Font, ... } }

    page.styles          = { "background":Fill, "wallpaper":Fill,
                             "filter_pane": {"width", "background":Fill, "text":Font} }
    page.color_palettes  = ["#...", ...]   # distinct colors used on the page

    visual.style = { "container": {"background":Fill,"border":Border,"shadow":Shadow,"padding"},
                     "title":Font, "subtitle":Font,
                     "data_colors": [{"field","value","color":ColorRef}],
                     "labels": {"show", "font":Font} }

    Fill   = { "color":ColorRef, "transparency", "image":{source,fit} }
    Border = { "show", "color":ColorRef, "width", "style", "radius" }
    Shadow = { "show", "color":ColorRef, "blur", "offset_x", "offset_y", "transparency" }
"""

import io
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional


# ===========================================================================
# PowerBI expression decoding helpers
# ===========================================================================

def _strip_pbi_literal(value: Any) -> Any:
    """Decode a PowerBI Literal.Value string into a Python scalar.

    PowerBI encodes every literal as a string with type sigils:
      "true"/"false" -> bool
      "20D" / "65D"  -> float (D = double)         "186L" -> int (L = long)
      "'Top'" / "'#094780'" -> str (single-quoted; quotes stripped)
    """
    if not isinstance(value, str):
        return value
    v = value.strip()
    if v in ("true", "false"):
        return v == "true"
    # quoted string literal -> strip the outer single quotes
    if len(v) >= 2 and v.startswith("'") and v.endswith("'"):
        return v[1:-1]
    # numeric literal with optional D/L/M suffix
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)[DLMF]?", v)
    if m:
        num = float(m.group(1))
        return int(num) if num.is_integer() else num
    return v


def _expr_scalar(prop: Any) -> Any:
    """Pull a decoded scalar out of a `{"expr": {"Literal": {"Value": ...}}}` node."""
    if not isinstance(prop, dict):
        return None
    expr = prop.get("expr")
    if isinstance(expr, dict) and isinstance(expr.get("Literal"), dict):
        return _strip_pbi_literal(expr["Literal"].get("Value"))
    return None


def _color_ref_from_expr(expr: Any) -> Optional[Dict[str, Any]]:
    """Build a ColorRef from a PowerBI color `expr` node (Literal hex or ThemeDataColor)."""
    if not isinstance(expr, dict):
        return None
    if isinstance(expr.get("Literal"), dict):
        hexval = _strip_pbi_literal(expr["Literal"].get("Value"))
        if isinstance(hexval, str) and hexval.startswith("#"):
            return {"hex": hexval, "ref": None, "transparency": None}
        return None
    if isinstance(expr.get("ThemeDataColor"), dict):
        tdc = expr["ThemeDataColor"]
        # Structured ref so a forward agent rebuilds ThemeDataColor{ColorId,Percent}
        # exactly (or emits the resolved literal hex).
        return {
            "hex": None,
            "ref": {"palette": "dataColors", "index": tdc.get("ColorId"),
                    "percent": tdc.get("Percent") or 0},
            "transparency": None,
        }
    return None


def _color_ref(prop: Any) -> Optional[Dict[str, Any]]:
    """Build a ColorRef from a property node.

    Accepts both `{"solid": {"color": {"expr": ...}}}` (fill/color props) and a
    bare `{"expr": ...}` node.
    """
    if not isinstance(prop, dict):
        return None
    solid = prop.get("solid")
    if isinstance(solid, dict):
        color = solid.get("color")
        if isinstance(color, dict) and "expr" in color:
            return _color_ref_from_expr(color["expr"])
    if "expr" in prop:
        return _color_ref_from_expr(prop["expr"])
    return None


def _first_props(obj_list: Any) -> Dict[str, Any]:
    """Return properties dict from objects[name] = [ {"properties": {...}} ]."""
    if isinstance(obj_list, list) and obj_list:
        first = obj_list[0]
        if isinstance(first, dict):
            return first.get("properties", {}) or {}
    return {}


def _pbi_font(props: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Build a Font from a PowerBI properties dict (title/labels/header)."""
    if not props:
        return None
    font = {
        "family": _expr_scalar(props.get("fontFamily")),
        "size": _expr_scalar(props.get("fontSize")),
        "bold": _expr_scalar(props.get("bold")),
        "italic": _expr_scalar(props.get("italic")),
        "underline": _expr_scalar(props.get("underline")),
        "align": _expr_scalar(props.get("alignment")),
        "color": _color_ref(props.get("color")),
        "text": _expr_scalar(props.get("text")),
    }
    return font if any(v is not None for v in font.values()) else None


def _pbi_image_fill(props: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Decode a background/wallpaper image: {source, fit} from properties.image."""
    img = props.get("image")
    if not isinstance(img, dict):
        return None
    # image can be {image:{name/url/scaling}} (nested) or a direct expr.
    inner = img.get("image") if isinstance(img.get("image"), dict) else img
    source = None
    for key in ("url", "name"):
        d = _decode_prop(inner.get(key))
        if isinstance(d, dict):
            source = d.get("image_ref")
        elif d is not None:
            source = d
        if source:
            break
    if source is None:
        d = _decode_prop(img)
        source = d.get("image_ref") if isinstance(d, dict) else d
    fit = _expr_scalar(inner.get("scaling")) or _expr_scalar(props.get("imageFit"))
    if source is None and fit is None:
        return None
    return {"source": source, "fit": fit}


def _pbi_fill(props: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Build a Fill from a properties dict with `color`, `transparency`, `image`, `show`."""
    if not props:
        return None
    color = _color_ref(props.get("color"))
    transparency = _expr_scalar(props.get("transparency"))
    image = _pbi_image_fill(props)
    show = _expr_scalar(props.get("show"))
    if color is None and transparency is None and image is None and show is None:
        return None
    return {"color": color, "transparency": transparency, "image": image, "show": show}


def _pbi_border(props: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not props:
        return None
    border = {
        "show": _expr_scalar(props.get("show")),
        "color": _color_ref(props.get("color")),
        "width": _expr_scalar(props.get("weight")),
        "style": None,
        "radius": _expr_scalar(props.get("radius")),
    }
    return border if any(v is not None for v in border.values()) else None


def _pbi_shadow(props: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Build a Shadow from a vcObjects.dropShadow properties dict.

    PowerBI encodes the offset as position/preset/angle/distance (not x/y), so
    those are captured instead of offset_x/offset_y."""
    if not props:
        return None
    shadow = {
        "show": _expr_scalar(props.get("show")),
        "color": _color_ref(props.get("color")),
        "blur": _expr_scalar(props.get("shadowBlur") or props.get("blur")),
        "position": _expr_scalar(props.get("position")),
        "preset": _expr_scalar(props.get("preset")),
        "angle": _expr_scalar(props.get("angle")),
        "distance": _expr_scalar(props.get("shadowDistance") or props.get("distance")),
        "spread": _expr_scalar(props.get("shadowSpread")),
        "transparency": _expr_scalar(props.get("transparency")),
    }
    return shadow if any(v is not None for v in shadow.values()) else None


def _first_scalar(obj_list: Any) -> Any:
    """Return the first numeric scalar property value from an objects[name] list.

    Used for padding-style objects whose exact property key varies by visual type
    (padding / cardPadding); robust to the property name."""
    props = _first_props(obj_list)
    for v in props.values():
        s = _expr_scalar(v)
        if isinstance(s, (int, float)) and not isinstance(s, bool):
            return s
    return None


# ===========================================================================
# PowerBI theme
# ===========================================================================

def _theme_color_ref(hexval: Any) -> Optional[Dict[str, Any]]:
    if isinstance(hexval, str) and hexval.startswith("#"):
        return {"hex": hexval, "ref": None, "transparency": None}
    return None


def _theme_text_class(tc: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(tc, dict):
        return None
    return {
        "family": tc.get("fontFace"),
        "size": tc.get("fontSize"),
        "bold": None, "italic": None, "underline": None, "align": None,
        "color": _theme_color_ref(tc.get("color")),
        "text": None,
    }


def _build_powerbi_theme(theme_json: Dict[str, Any]) -> Dict[str, Any]:
    """Map a PowerBI theme JSON into the common theme shape."""
    sem_map = {
        "foreground": "foreground", "background": "background",
        "good": "good", "neutral": "neutral", "bad": "bad",
        "table_accent": "tableAccent", "hyperlink": "hyperlink",
        "maximum": "maximum", "center": "center", "minimum": "minimum",
        "null_color": "null",
    }
    semantic = {}
    for out_key, src_key in sem_map.items():
        ref = _theme_color_ref(theme_json.get(src_key))
        if ref is not None:
            semantic[out_key] = ref

    text_classes = {}
    for name, tc in (theme_json.get("textClasses") or {}).items():
        built = _theme_text_class(tc)
        if built is not None:
            text_classes[name] = built

    return {
        "name": theme_json.get("name"),
        "source_tool": "power_bi",
        "data_palette": list(theme_json.get("dataColors") or []),
        "named_palettes": [],
        "semantic_colors": semantic or None,
        "text_classes": text_classes or None,
        # Per-visual-type default style overrides (checklist sec 10). Verbatim.
        "visual_styles": theme_json.get("visualStyles") or None,
        # Verbatim full theme JSON — lets a forward agent regenerate the exact
        # theme file (every token), nothing dropped.
        "raw": theme_json,
    }


def _resolve_theme_refs(node: Any, palette: List[str]) -> None:
    """Walk a styling tree and fill ColorRef.hex for theme refs from the palette.

    Resolves to the EXACT base palette color (theme.dataColors[ColorId]); the
    shade percent is preserved verbatim in `ref` rather than approximated, so no
    color value is ever fabricated.
    """
    if isinstance(node, dict):
        ref = node.get("ref")
        if (node.get("hex") is None and isinstance(ref, dict)
                and ref.get("palette") == "dataColors"):
            idx = ref.get("index")
            if isinstance(idx, int) and 0 <= idx < len(palette):
                node["hex"] = palette[idx]
        for v in node.values():
            _resolve_theme_refs(v, palette)
    elif isinstance(node, list):
        for v in node:
            _resolve_theme_refs(v, palette)


# ===========================================================================
# PowerBI Layout loading
# ===========================================================================

def _load_layout(layout_path: str) -> Optional[Dict[str, Any]]:
    """Load the PowerBI Layout file (UTF-16-LE on disk) with encoding fallback."""
    for enc in ("utf-16-le", "utf-8", "utf-16", "utf-16-be", "latin-1"):
        try:
            with open(layout_path, "r", encoding=enc) as f:
                return json.loads(f.read())
        except (UnicodeError, json.JSONDecodeError):
            continue
    return None


def _parse_config(raw: Any) -> Dict[str, Any]:
    """A Layout `config` value is a JSON string (or already a dict)."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def _find_theme_json(report_dir: str, theme_name: Optional[str]) -> Optional[Dict[str, Any]]:
    """Locate and load the active base theme JSON inside the unzipped .pbix."""
    base = Path(report_dir)
    candidates: List[Path] = []
    if theme_name:
        candidates += list(base.rglob(f"{theme_name}.json"))
    # Fall back to any BaseThemes/*.json
    candidates += list(base.rglob("StaticResources/SharedResources/BaseThemes/*.json"))
    for p in candidates:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict) and ("dataColors" in data or "name" in data):
                return data
        except (OSError, json.JSONDecodeError, UnicodeError):
            continue
    return None


# ===========================================================================
# PowerBI visual + page styling
# ===========================================================================

def _decode_datapoint_selector(selector: Any) -> Dict[str, Optional[str]]:
    """Pull (field, value) out of a dataPoint selector's scopeId comparison."""
    out: Dict[str, Optional[str]] = {"field": None, "value": None}
    if not isinstance(selector, dict):
        return out
    for d in selector.get("data", []) or []:
        comp = (d.get("scopeId") or {}).get("Comparison") if isinstance(d, dict) else None
        if not isinstance(comp, dict):
            continue
        col = (comp.get("Left") or {}).get("Column") or {}
        entity = (((col.get("Expression") or {}).get("SourceRef")) or {}).get("Entity")
        prop = col.get("Property")
        if entity and prop:
            out["field"] = f"{entity}.{prop}"
        elif prop:
            out["field"] = prop
        right = (comp.get("Right") or {}).get("Literal") or {}
        if "Value" in right:
            out["value"] = _strip_pbi_literal(right.get("Value"))
        break
    return out


def _extract_powerbi_data_colors(objects: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build the data_colors list from objects.dataPoint[]."""
    result: List[Dict[str, Any]] = []
    for dp in objects.get("dataPoint", []) or []:
        if not isinstance(dp, dict):
            continue
        props = dp.get("properties", {}) or {}
        color = _color_ref(props.get("fill"))
        if color is None:
            continue
        sel = _decode_datapoint_selector(dp.get("selector"))
        result.append({"field": sel["field"], "value": sel["value"], "color": color})
    return result


# ---------------------------------------------------------------------------
# Generic full-coverage decoder — the guarantee that NOTHING is missed.
# Decodes every object/property in objects{}/vcObjects{} to a scalar / ColorRef /
# image-ref, verbatim. Curated typed fields (below) cover the cross-tool-meaningful
# items; `raw` covers everything else (cellElements, narrative runs, reference
# lines, forecast, cross-filter, totals, wordWrap, …) deterministically.
# ---------------------------------------------------------------------------

def _decode_prop(value: Any) -> Any:
    """Decode one PBI property value → ColorRef / scalar / {image_ref} / None."""
    c = _color_ref(value)
    if c is not None:
        return c
    s = _expr_scalar(value)
    if s is not None:
        return s
    if isinstance(value, dict) and isinstance(value.get("expr"), dict):
        rpi = value["expr"].get("ResourcePackageItem")
        if isinstance(rpi, dict):
            return {"image_ref": rpi.get("ItemName")}
    return None


def _decode_props(props: Any) -> Optional[Dict[str, Any]]:
    if not props:
        return None
    out = {}
    for k, v in props.items():
        d = _decode_prop(v)
        if d is not None:
            out[k] = d
    return out or None


def _decode_objects(objs: Any) -> Optional[Dict[str, Any]]:
    """Fully decode an objects{} / vcObjects{} block. Preserves selectors."""
    out: Dict[str, Any] = {}
    for name, entries in (objs or {}).items():
        decoded = []
        for e in entries if isinstance(entries, list) else []:
            if not isinstance(e, dict):
                continue
            item: Dict[str, Any] = {}
            dp = _decode_props(e.get("properties"))
            if dp:
                item["properties"] = dp
            if e.get("selector") is not None:
                item["selector"] = e["selector"]
            if item:
                decoded.append(item)
        if decoded:
            out[name] = decoded
    return out or None


# Canonical visual `style` key set — BOTH tools emit exactly these keys so the
# output structure is identical (PowerBI fills most; Tableau fills the subset its
# source exposes, plus `raw`).
_STYLE_KEYS = (
    "container", "title", "subtitle", "callout", "data_colors", "labels",
    "data_labels", "legend", "axes", "lines_and_markers", "slicer", "table",
    "actions", "button", "image", "raw",
)


def _normalize_style(style: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Ensure a style dict carries every canonical key (missing → None / [])."""
    if style is None:
        return None
    return {k: style.get(k, [] if k == "data_colors" else None) for k in _STYLE_KEYS}


# Canonical page.styles key set — identical across both tools.
# NOTE: page width/height are intentionally NOT here — they already live on the
# page object (page.width/page.height), so duplicating them in styles is dedup.
_PAGE_STYLE_KEYS = (
    "page_type", "display_option", "vertical_alignment",
    "background", "wallpaper", "filter_pane", "filters", "interactions", "raw",
)


def _normalize_page_styles(styles: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Ensure page.styles carries every canonical key (missing → None)."""
    styles = styles or {}
    return {k: styles.get(k) for k in _PAGE_STYLE_KEYS}


# ---------------------------------------------------------------------------
# Curated tool-agnostic typed helpers (verified shapes).
# ---------------------------------------------------------------------------

def _font_from(props: Dict[str, Any], family="fontFamily", size="fontSize",
               color="color", text=None) -> Optional[Dict[str, Any]]:
    """Font from arbitrary property key names (axes/legend use labelColor etc.)."""
    if not props:
        return None
    return _pbi_font({
        "fontFamily": props.get(family), "fontSize": props.get(size),
        "bold": props.get("bold"), "italic": props.get("italic"),
        "underline": props.get("underline"), "alignment": props.get("alignment"),
        "color": props.get(color),
        "text": props.get(text) if text else None,
    })


def _pbi_axis(props: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not props:
        return None
    grid = {
        "show": _expr_scalar(props.get("gridlineShow")),
        "color": _color_ref(props.get("gridlineColor")),
        "width": _expr_scalar(props.get("gridlineThickness")),
        "style": _expr_scalar(props.get("gridlineStyle")),
    }
    grid = grid if any(v is not None for v in grid.values()) else None
    axis = {
        "labels": _font_from(props, color="labelColor"),
        "title": _font_from(props, family="titleFontFamily", size="titleFontSize",
                            color="titleColor", text="titleText"),
        "show_title": _expr_scalar(props.get("showAxisTitle")),
        "scale": _expr_scalar(props.get("axisScale")),
        "min": _expr_scalar(props.get("start")),
        "max": _expr_scalar(props.get("end")),
        "synced": None,
        "display_units": _expr_scalar(props.get("labelDisplayUnits")),
        "gridlines": grid,
    }
    return axis if any(v is not None for v in axis.values()) else None


# Canonical axis entry shape, shared by both tools. `style.axes` is a LIST of
# these (PowerBI: category/value; Tableau: one per workbook axis).
def _axis_entry(name: str, axis: Dict[str, Any]) -> Dict[str, Any]:
    return {"name": name, **axis}


def _pbi_axes(objects: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    out = []
    # value2/y2Axis = the secondary axis on combo / dual-axis charts.
    for name, key in (("category", "categoryAxis"), ("value", "valueAxis"),
                      ("value2", "y2Axis"), ("value2", "secValueAxis")):
        a = _pbi_axis(_first_props(objects.get(key)))
        if a:
            out.append(_axis_entry(name, a))
    return out or None


def _text_only_font(text: Any) -> Optional[Dict[str, Any]]:
    """A Font carrying only literal text (used for axis/legend titles)."""
    if not text:
        return None
    return {"family": None, "size": None, "bold": None, "italic": None,
            "underline": None, "align": None, "color": None, "text": text}


def _pbi_legend(props: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not props:
        return None
    legend = {
        "show": _expr_scalar(props.get("show")),
        "position": _expr_scalar(props.get("position")),
        "show_title": _expr_scalar(props.get("showTitle")),
        "title": _font_from(props, family="titleFontFamily", color="titleColor", text="titleText"),
        "labels": _font_from(props, color="labelColor"),
    }
    return legend if any(v is not None for v in legend.values()) else None


def _pbi_data_labels(obj_list: Any) -> Optional[Dict[str, Any]]:
    props = _first_props(obj_list)
    if not props:
        return None
    dl = {
        "show": _expr_scalar(props.get("show")),
        "position": _expr_scalar(props.get("labelPosition")),
        "display_units": _expr_scalar(props.get("labelDisplayUnits")),
        "decimal_places": _expr_scalar(props.get("labelPrecision")),
        "orientation": _expr_scalar(props.get("labelOrientation")),
        "background_show": _expr_scalar(props.get("enableBackground")),
        "background_color": _color_ref(props.get("backgroundColor")),
        "font": _pbi_font(props),
    }
    return dl if any(v is not None for v in dl.values()) else None


def _pbi_callout(objects: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """KPI / card callout value + category label (sections 3, 7)."""
    val = _first_props(objects.get("labels"))
    cat = _first_props(objects.get("categoryLabels"))
    gen = _first_props(objects.get("general"))
    blank_fallback = None
    if val:
        blank_fallback = _expr_scalar(val.get("noDataMessage"))
    if blank_fallback is None and gen:
        blank_fallback = _expr_scalar(gen.get("noDataText") or gen.get("noDataMessage"))
    if not (val or cat or blank_fallback is not None):
        return None
    callout = {
        "value": _pbi_font(val) if val else None,
        "display_units": _expr_scalar(val.get("labelDisplayUnits")) if val else None,
        "decimal_places": _expr_scalar(val.get("labelPrecision")) if val else None,
        "category_label": _pbi_font(cat) if cat else None,
        "blank_fallback": blank_fallback,
    }
    return callout if any(v is not None for v in callout.values()) else None


def _pbi_header_style(props: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not props:
        return None
    hs = {
        "font": _font_from(props, color="fontColor"),
        "background": _color_ref(props.get("backColor") or props.get("background")),
        "alignment": _expr_scalar(props.get("alignment")),
    }
    return hs if any(v is not None for v in hs.values()) else None


def _pbi_slicer(objects: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    data = _first_props(objects.get("data"))
    sel = _first_props(objects.get("selection"))
    hdr = _first_props(objects.get("header"))
    items = _first_props(objects.get("items"))
    slider = _first_props(objects.get("slider"))
    header = None
    if hdr:
        header = {"show": _expr_scalar(hdr.get("show")), "font": _pbi_font(hdr),
                  "background": _color_ref(hdr.get("background") or hdr.get("backColor"))}
        header = header if any(v is not None for v in header.values()) else None
    s = {
        "type": _expr_scalar(data.get("mode")) if data else None,
        "single_select": _expr_scalar(sel.get("singleSelect")) if sel else None,
        "strict_single_select": _expr_scalar(sel.get("strictSingleSelect")) if sel else None,
        "multi_select_with_ctrl": _expr_scalar(sel.get("multiSelectWithCtrl")) if sel else None,
        "show_select_all": _expr_scalar(sel.get("selectAllCheckboxEnabled")) if sel else None,
        "header": header,
        "items": _pbi_font(items) if items else None,
        "slider_color": _color_ref(slider.get("color")) if slider else None,
    }
    return s if any(v is not None for v in s.values()) else None


def _pbi_table(objects: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    vals = _first_props(objects.get("values"))
    sub = _first_props(objects.get("subTotals") or objects.get("subtotals"))
    subtotals = None
    if sub:
        subtotals = {
            "row_subtotals": _expr_scalar(sub.get("rowSubtotals")),
            "column_subtotals": _expr_scalar(sub.get("columnSubtotals")),
            "stepping": _expr_scalar(sub.get("rowSubtotalsPosition") or sub.get("perRowLevel")),
        }
        subtotals = subtotals if any(v is not None for v in subtotals.values()) else None
    alternating = None
    if vals:
        alternating = {
            "primary": _color_ref(vals.get("backColorPrimary")),
            "secondary": _color_ref(vals.get("backColorSecondary")),
        }
        alternating = alternating if any(v is not None for v in alternating.values()) else None
    # Total label text override (objects.subTotals/total.totalLabel/labelText).
    total_props = _first_props(objects.get("total") or objects.get("totals"))
    total_label = (_expr_scalar(total_props.get("totalLabel") or total_props.get("labelText"))
                   if total_props else None)
    if total_label is None and sub:
        total_label = _expr_scalar(sub.get("totalLabel") or sub.get("labelText"))
    # Conditional cell elements (background gradient / font color / data bars /
    # icons). These are complex FillRule/Gradient expr trees that don't decode to
    # scalars, so promote them verbatim into a named field (instead of raw-only).
    conditional = None
    for src in (vals, _first_props(objects.get("cellControl"))):
        if not src:
            continue
        cond = {k: v for k, v in src.items()
                if isinstance(v, dict) and _decode_prop(v) is None}
        if cond:
            conditional = (conditional or {})
            conditional.update(cond)
    t = {
        "column_headers": _pbi_header_style(_first_props(objects.get("columnHeaders"))),
        "row_headers": _pbi_header_style(_first_props(objects.get("rowHeaders"))),
        "values": _decode_props(vals),
        "totals": _pbi_header_style(total_props),
        "grid": _decode_props(_first_props(objects.get("grid"))),
        "subtotals": subtotals,
        "alternating_rows": alternating,
        "total_label": total_label,
        "conditional": conditional,
    }
    return t if any(v is not None for v in t.values()) else None


def _pbi_lines_markers(objects: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    p = _first_props(objects.get("lineStyles"))
    if not p:
        return None
    lm = {
        "stroke_show": _expr_scalar(p.get("strokeShow")),
        "line_style": _expr_scalar(p.get("lineStyle")),
        "show_marker": _expr_scalar(p.get("showMarker")),
        "marker_shape": _expr_scalar(p.get("markerShape")),
        "marker_size": _expr_scalar(p.get("markerSize")),
    }
    return lm if any(v is not None for v in lm.values()) else None


def _pbi_image_meta(objects: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    gen = _first_props(objects.get("general"))
    source = None
    if gen:
        d = _decode_prop(gen.get("imageUrl"))
        source = d.get("image_ref") if isinstance(d, dict) else d
    scale = _expr_scalar(_first_props(objects.get("imageScaling")).get("imageScalingType")
                         if objects.get("imageScaling") else None)
    if source is None and scale is None:
        return None
    return {"source": source, "scale": scale}


def _pbi_button(objects: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    shape = _first_props(objects.get("shape"))
    icon = _first_props(objects.get("icon"))
    text_font = text_content = None
    states: List[str] = []
    # State selectors (Default/Hover/Press/Disabled) live on ANY of the button's
    # styling objects, not just text — scan them all so the state list is complete.
    for obj_name in ("text", "fill", "outline", "icon", "shape", "glow"):
        for e in objects.get(obj_name) or []:
            if not isinstance(e, dict):
                continue
            sid = (e.get("selector") or {}).get("id")
            if sid and sid not in states:
                states.append(sid)
            if obj_name == "text":
                props = e.get("properties", {}) or {}
                if text_content is None and props.get("text") is not None:
                    text_content = _expr_scalar(props.get("text"))
                if text_font is None:
                    text_font = _pbi_font(props)
    b = {
        "shape": _expr_scalar(shape.get("tileShape")) if shape else None,
        "icon": _expr_scalar(icon.get("shapeType")) if icon else None,
        "text": text_font, "text_content": text_content,
        "states": states or None,
    }
    return b if any(v for v in b.values()) else None


def _pbi_actions(vc: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    out = []
    for e in vc.get("visualLink") or []:
        if not isinstance(e, dict):
            continue
        props = e.get("properties", {}) or {}
        atype = _expr_scalar(props.get("type"))
        target = _expr_scalar(props.get("bookmark") or props.get("navigationSection"))
        url = _expr_scalar(props.get("webUrl") or props.get("webURL"))
        if atype or target or url:
            out.append({"type": atype, "target": target, "url": url})
    return out or None


def _pbi_tooltip(vc: Dict[str, Any], objects: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Visual tooltip config: Default vs custom report-page tooltip."""
    props = _first_props(vc.get("visualTooltip")) or _first_props(objects.get("tooltip"))
    if not props:
        return None
    t = {
        "show": _expr_scalar(props.get("show")),
        "type": _expr_scalar(props.get("type")),
        "page": _expr_scalar(props.get("section")),
    }
    return t if any(v is not None for v in t.values()) else None


def _pbi_max_categories(single_visual: Dict[str, Any]) -> Any:
    """Category cap (treemap/charts) from prototypeQuery DataReduction Top/Window count."""
    dr = (single_visual.get("prototypeQuery") or {}).get("DataReduction") or {}
    for side in ("Primary", "Secondary"):
        algos = dr.get(side) or {}
        if not isinstance(algos, dict):
            continue
        for algo in ("Top", "Bottom", "Window", "Sample", "BinnedLineSample"):
            a = algos.get(algo)
            if isinstance(a, dict) and a.get("Count") is not None:
                return a.get("Count")
    return None


def _build_powerbi_visual_style(single_visual: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Build the full common `style` from a PowerBI singleVisual config.

    Curated typed fields cover the cross-tool-meaningful checklist items; `raw`
    is a complete verbatim decode of every object/property (the catch-all that
    guarantees the whole checklist is captured)."""
    objects = single_visual.get("objects") or {}
    vc = single_visual.get("vcObjects") or {}

    # Sec 2 — container
    header_icons = _decode_props(_first_props(vc.get("visualHeader")))
    alt_text = _expr_scalar(_first_props(objects.get("general")).get("altText")) \
        if objects.get("general") else None
    container = {
        "background": _pbi_fill(_first_props(vc.get("background"))),
        "border": _pbi_border(_first_props(vc.get("border"))),
        "shadow": _pbi_shadow(_first_props(vc.get("dropShadow"))),
        "padding": _first_scalar(objects.get("padding")) or _first_scalar(objects.get("cardPadding")),
        "header_icons": header_icons,
        "alt_text": alt_text,
        "tooltip": _pbi_tooltip(vc, objects),
        "max_categories": _pbi_max_categories(single_visual),
        # Generic text wrapping (cards + tables) — a general container property,
        # not table-specific, so it lives here (avoids phantom style.table on cards).
        "word_wrap": (_expr_scalar(_first_props(objects.get("wordWrap")).get("show"))
                      if objects.get("wordWrap") else None),
    }
    container = container if any(v is not None for v in container.values()) else None

    # Sec 6 — labels kept as the cross-tool simple field too
    labels_props = _first_props(objects.get("labels") or objects.get("dataLabels"))
    labels = None
    if labels_props:
        labels = {"show": _expr_scalar(labels_props.get("show")), "font": _pbi_font(labels_props)}
        labels = labels if any(v is not None for v in labels.values()) else None

    style = {
        # sec 2
        "container": container,
        "title": _pbi_font(_first_props(vc.get("title"))),
        "subtitle": _pbi_font(_first_props(vc.get("subTitle") or vc.get("subtitle"))),
        # sec 3
        "callout": _pbi_callout(objects),
        # sec 6
        "data_colors": _extract_powerbi_data_colors(objects),
        "labels": labels,
        "data_labels": _pbi_data_labels(objects.get("labels") or objects.get("dataLabels")),
        "legend": _pbi_legend(_first_props(objects.get("legend"))),
        "axes": _pbi_axes(objects),
        "lines_and_markers": _pbi_lines_markers(objects),
        # sec 4
        "slicer": _pbi_slicer(objects),
        # sec 5
        "table": _pbi_table(objects),
        # sec 7
        "actions": _pbi_actions(vc),
        "button": _pbi_button(objects),
        # sec 10
        "image": _pbi_image_meta(objects),
        # Verbatim source objects — exact PBI Layout blocks (expr trees, sigils
        # preserved). Lets a forward agent write them straight back to PowerBI
        # losslessly, and guarantees EVERY source detail is captured.
        "raw": {"objects": objects or None, "vcObjects": vc or None},
    }
    if not any(v for v in style.values()):
        return None
    return style


_DISPLAY_OPTION = {0: "ActualSize", 1: "FitToPage", 2: "FitToWidth"}


def _pbi_page_filters(section: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """Per-page filters: column, type, and locking flags (IsLocked/IsHidden)."""
    raw = section.get("filters")
    if isinstance(raw, str) and raw.strip():
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            raw = []
    out = []
    for f in raw if isinstance(raw, list) else []:
        if not isinstance(f, dict):
            continue
        gen = _first_props((f.get("objects") or {}).get("general"))
        expr = f.get("expression") if isinstance(f.get("expression"), dict) else {}
        col = (expr.get("Column") or {}).get("Property") or (expr.get("Measure") or {}).get("Property")
        entry = {
            "column": col,
            "filter_type": f.get("type"),
            "locked": _expr_scalar(gen.get("isLockedInViewMode")) if gen else None,
            "hidden": _expr_scalar(gen.get("isHiddenInViewMode")) if gen else None,
        }
        if any(v is not None for v in entry.values()):
            out.append(entry)
    return out or None


def _pbi_interactions(section: Dict[str, Any], page_config: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """Cross-visual edit-interactions (Filter/Highlight/None) + dimming, when the
    report customizes them away from defaults."""
    cands = None
    for src in (page_config.get("visualInteractions"), section.get("visualInteractions"),
                page_config.get("relationships")):
        if isinstance(src, list):
            cands = src
            break
    if not cands:
        return None
    out = []
    for it in cands:
        if not isinstance(it, dict):
            continue
        out.append({
            "source": it.get("source") or it.get("sourceVisual"),
            "target": it.get("target") or it.get("targetVisual"),
            "type": it.get("type"),
            "dimming": it.get("dimmingPercentage"),
        })
    return out or None


def _build_powerbi_page_styles(section: Dict[str, Any], page_config: Dict[str, Any],
                               top_objects: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Build page-level styles (checklist sec 1) from a section + its config.objects."""
    objs = page_config.get("objects") or {}

    sect_props = _first_props(objs.get("section") or top_objects.get("section"))
    vertical_alignment = _expr_scalar(sect_props.get("verticalAlignment")) if sect_props else None

    fp_props = _first_props(objs.get("outspacePane") or top_objects.get("outspacePane"))
    fc_props = _first_props(objs.get("outspaceFilterCard") or top_objects.get("outspaceFilterCard"))
    filter_pane = None
    if fp_props or fc_props:
        fp = {
            "visibility": _expr_scalar(fp_props.get("visible")) if fp_props else None,
            "expanded": _expr_scalar(fp_props.get("expanded")) if fp_props else None,
            "width": _expr_scalar(fp_props.get("width")) if fp_props else None,
            "background": _pbi_fill(fp_props) if fp_props else None,
            "card_state": _decode_props(fc_props) if fc_props else None,
        }
        filter_pane = fp if any(v is not None for v in fp.values()) else None

    do = section.get("displayOption")
    styles = {
        "page_type": section.get("type"),
        "display_option": _DISPLAY_OPTION.get(do, do),
        "vertical_alignment": vertical_alignment,
        "background": _pbi_fill(_first_props(objs.get("background"))),
        "wallpaper": _pbi_fill(_first_props(objs.get("wallpaper"))),
        "filter_pane": filter_pane,
        "filters": _pbi_page_filters(section),
        "interactions": _pbi_interactions(section, page_config),
        # Verbatim section objects — exact source, lossless reconstruction.
        "raw": objs or None,
    }
    return styles if any(v is not None for v in styles.values()) else None


def _collect_palette(node: Any, sink: List[str]) -> None:
    """Collect distinct literal hex values from a styling subtree (order-preserving)."""
    if isinstance(node, dict):
        hexval = node.get("hex")
        if isinstance(hexval, str) and hexval.startswith("#") and hexval not in sink:
            sink.append(hexval)
        for v in node.values():
            _collect_palette(v, sink)
    elif isinstance(node, list):
        for v in node:
            _collect_palette(v, sink)


def _extract_powerbi_bookmarks(top_config: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """Report-level bookmarks (checklist sec 7)."""
    out = []
    for bm in top_config.get("bookmarks", []) or []:
        if not isinstance(bm, dict):
            continue
        es = bm.get("explorationState") or {}
        if isinstance(es, str):
            try:
                es = json.loads(es)
            except (json.JSONDecodeError, TypeError):
                es = {}
        sections = es.get("sections") if isinstance(es, dict) else None
        opts = bm.get("options") or {}
        out.append({
            "name": bm.get("name"),
            "display_name": bm.get("displayName"),
            "active_page": es.get("activeSection") if isinstance(es, dict) else None,
            "capture_data": bool(isinstance(es, dict) and es.get("filters")),
            "capture_display": bool(sections),
            "capture_current_page": bool(isinstance(es, dict) and es.get("activeSection")),
            # Scope: which visuals the bookmark applies to (apply-to-selected).
            "target_visuals": opts.get("targetVisualNames"),
            "apply_only_to_target_visuals": opts.get("applyOnlyToTargetVisuals"),
            # Verbatim bookmark (full explorationState) for lossless reconstruction.
            "raw": bm,
        })
    return out or None


def extract_powerbi_styling(layout_path: str, report_dir: str) -> Optional[Dict[str, Any]]:
    """Parse a PowerBI Layout + theme into the common styling overlay.

    Returns:
        {
          "theme": {...},
          "bookmarks": [...],
          "pages": { "<page_id>": {"styles": {...}, "color_palettes": [...],
                                   "visuals": {"<visual_id>": {style}}} }
        }
    or None when the layout can't be read.
    """
    layout = _load_layout(layout_path)
    if not layout:
        return None

    top_config = _parse_config(layout.get("config"))
    top_objects = top_config.get("objects") or {}
    theme_name = (((top_config.get("themeCollection") or {}).get("baseTheme")) or {}).get("name")

    theme = None
    theme_json = _find_theme_json(report_dir, theme_name)
    if theme_json:
        theme = _build_powerbi_theme(theme_json)
    palette = (theme or {}).get("data_palette") or []

    bookmarks = _extract_powerbi_bookmarks(top_config)

    pages: Dict[str, Any] = {}
    for section in layout.get("sections", []) or []:
        page_id = section.get("name", "")
        page_config = _parse_config(section.get("config"))
        page_styles = _build_powerbi_page_styles(section, page_config, top_objects)

        visuals: Dict[str, Any] = {}
        field_params: Dict[str, Any] = {}
        page_colors: List[str] = []
        for vc in section.get("visualContainers", []) or []:
            cfg = _parse_config(vc.get("config"))
            single_visual = cfg.get("singleVisual") or {}
            visual_id = cfg.get("name")
            if not visual_id:
                continue
            style = _build_powerbi_visual_style(single_visual)
            if style is not None:
                visuals[visual_id] = style
                _collect_palette(style, page_colors)
            # Field-parameter bindings (role -> driving field parameter). These
            # decide which field a field-parameter slicer feeds into this visual.
            # Captured deterministically by visual_id here because the LLM visual
            # extraction does not preserve this nested structure.
            qfp = single_visual.get("queryFieldParametersByRole")
            if qfp:
                field_params[visual_id] = qfp

        if page_styles:
            _collect_palette(page_styles, page_colors)

        pages[page_id] = {
            "styles": page_styles,
            "color_palettes": page_colors or None,
            "visuals": visuals,
            "field_parameters": field_params or None,
        }

    overlay = {"theme": theme, "bookmarks": bookmarks, "pages": pages}
    # Resolve theme-data-color refs to exact palette hexes (no shade math).
    _resolve_theme_refs(overlay, palette if palette else [])
    return overlay


def apply_powerbi_styling(agent_result: Dict[str, Any], layout_path: str, report_dir: str) -> None:
    """Merge deterministic PowerBI styling into a common-model result in place.

    Runs AFTER the agent flow (report_pages already carries page_id / visual_id)
    and BEFORE apply_readable_ids (which drops those ids). No LLM involved.
    """
    overlay = extract_powerbi_styling(layout_path, report_dir)
    if not overlay:
        return

    if overlay.get("theme"):
        agent_result["theme"] = overlay["theme"]
    # Always set bookmarks (None when the report has none) so the key is uniform.
    agent_result["bookmarks"] = overlay.get("bookmarks")

    pages_overlay = overlay.get("pages", {})
    for page in agent_result.get("report_pages", []) or []:
        po = pages_overlay.get(page.get("page_id"))
        if not po:
            continue
        page["styles"] = _normalize_page_styles(po.get("styles"))
        if po.get("color_palettes") is not None:
            page["color_palettes"] = po["color_palettes"]
        vis_overlay = po.get("visuals", {})
        fp_overlay = po.get("field_parameters") or {}
        for vis in page.get("visuals", []) or []:
            style = vis_overlay.get(vis.get("visual_id"))
            if style is not None:
                vis["style"] = _normalize_style(style)
            # Re-attach the field-parameter binding (dropped by the LLM visual
            # extraction) by visual_id, before apply_readable_ids drops the id.
            qfp = fp_overlay.get(vis.get("visual_id"))
            if qfp:
                vis["field_parameters_by_role"] = qfp


# ===========================================================================
# Tableau (.twb XML) — emits the SAME overlay shape as PowerBI
# ===========================================================================

def _twb_bytes(data: bytes) -> bytes:
    """Return inner .twb XML bytes, unwrapping a .twbx ZIP archive if needed."""
    if zipfile.is_zipfile(io.BytesIO(data)):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            twb = next((n for n in zf.namelist() if n.lower().endswith(".twb")), None)
            if twb:
                return zf.read(twb)
    return data


def _load_twb_root(xml: bytes) -> Optional[ET.Element]:
    """Parse .twb/.twbx bytes, recovering from a truncated trailing <thumbnails>
    block (huge base64 previews that are irrelevant to styling)."""
    xml = _twb_bytes(xml)
    try:
        return ET.fromstring(xml)
    except ET.ParseError:
        try:
            txt = xml.decode("utf-8", "replace")
            i = txt.find("<thumbnails")
            if i != -1:
                txt = txt[:i] + "</workbook>"
                return ET.fromstring(txt.encode("utf-8"))
        except (ET.ParseError, UnicodeError):
            return None
    return None


def _clean_tab_field(field: Optional[str]) -> Optional[str]:
    """Reduce a Tableau field ref like ``[none:Category:nk]`` to its column name."""
    if not field:
        return None
    inner = field[field.rfind("[") + 1:].rstrip("]")
    parts = inner.split(":")
    if len(parts) >= 3:
        return parts[-2]
    return inner or None


def _tab_color_ref(hexval: Optional[str], ref: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not hexval:
        return None
    hexval = hexval.strip()
    if not hexval.startswith("#"):
        return None
    # Structured ref (palette name only for Tableau — the map already gives the
    # literal hex, so there's no index/percent). Same ColorRef shape as PowerBI.
    structured = {"palette": ref, "index": None, "percent": None} if ref else None
    return {"hex": hexval, "ref": structured, "transparency": None}


_TAB_ALIGN = {"0": "left", "1": "center", "2": "right"}


def _tab_font_from_run(run: Optional[ET.Element]) -> Optional[Dict[str, Any]]:
    """Build a Font from a formatted-text <run> element (dashboard text zones)."""
    if run is None:
        return None
    font = {
        "family": run.get("fontname"),
        "size": _num(run.get("fontsize")),
        "bold": _tab_bool(run.get("bold")),
        "italic": _tab_bool(run.get("italic")),
        "underline": _tab_bool(run.get("underline")),
        "align": _TAB_ALIGN.get(run.get("fontalignment")),
        "color": _tab_color_ref(run.get("fontcolor")),
        "text": (run.text or "").strip() or None,
    }
    return font if any(v is not None for v in font.values()) else None


def _tab_font_from_formats(fmts: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Build a Font from a worksheet style-rule's <format attr=.. value=..> map."""
    if not fmts:
        return None
    font = {
        "family": fmts.get("font-family"),
        "size": _num(fmts.get("font-size")),
        "bold": (fmts.get("font-weight") == "bold") if "font-weight" in fmts else None,
        "italic": (fmts.get("font-style") == "italic") if "font-style" in fmts else None,
        "underline": None,
        "align": fmts.get("text-align"),
        "color": _tab_color_ref(fmts.get("color") or fmts.get("text-color")),
        "text": None,
    }
    return font if any(v is not None for v in font.values()) else None


def _num(value: Optional[str]) -> Any:
    if value is None:
        return None
    try:
        n = float(value)
        return int(n) if n.is_integer() else n
    except ValueError:
        return None


def _tab_bool(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    return value == "true"


def _rule_formats(rule: ET.Element) -> Dict[str, str]:
    return {f.get("attr"): f.get("value") for f in rule.findall("format") if f.get("attr")}


def _parse_worksheet_data_colors(ws: ET.Element) -> List[Dict[str, Any]]:
    """Extract per-value color maps from a worksheet's mark color encodings."""
    out: List[Dict[str, Any]] = []
    for enc in ws.findall(".//style-rule[@element='mark']/encoding[@attr='color']"):
        field = _clean_tab_field(enc.get("field"))
        palette = enc.get("palette")
        for m in enc.findall("map"):
            hexval = m.get("to")
            color = _tab_color_ref(hexval, ref=palette)
            if color is None:
                continue
            for b in m.findall("bucket"):
                value = (b.text or "").strip().strip('"')
                out.append({"field": field, "value": value or None, "color": color})
    return out


def _parse_datasource_color_encodings(root: ET.Element):
    """Tableau assigns per-value colors at the DATASOURCE level (shared by every
    worksheet that uses the field). Returns ({field: [{value,color}]}, {palette: [hex]})."""
    by_field: Dict[str, List[Dict[str, Any]]] = {}
    palettes: Dict[str, List[str]] = {}
    for ds in root.findall("datasources/datasource"):
        for enc in ds.findall(".//style-rule[@element='mark']/encoding[@attr='color']"):
            field = _clean_tab_field(enc.get("field"))
            palette = enc.get("palette")
            assigns: List[Dict[str, Any]] = []
            for m in enc.findall("map"):
                hexval = m.get("to")
                color = _tab_color_ref(hexval, ref=palette)
                if color is None:
                    continue
                if palette:
                    palettes.setdefault(palette, [])
                    if hexval not in palettes[palette]:
                        palettes[palette].append(hexval)
                for b in m.findall("bucket"):
                    val = (b.text or "").strip().strip('"')
                    assigns.append({"value": val or None, "color": color})
            if field and assigns:
                by_field.setdefault(field, []).extend(assigns)
    return by_field, palettes


def _ws_raw(ws: ET.Element) -> Optional[Dict[str, Any]]:
    """Verbatim catch-all of every worksheet style-rule: {element: {attr: value}}.

    Tableau parallel to the PowerBI `raw` decode — guarantees no worksheet styling
    is dropped even when it isn't mapped to a typed field."""
    raw: Dict[str, Dict[str, str]] = {}
    for sr in ws.findall(".//style/style-rule"):
        el = sr.get("element")
        fmts = _rule_formats(sr)
        if el and fmts:
            raw.setdefault(el, {}).update(fmts)
    return raw or None


def _tab_encoding_axes(ws: ET.Element) -> Dict[str, Dict[str, Any]]:
    """Axis bounds / scale / synchronize from <encoding type='space'>.

    Tableau stores a fixed axis range AND the 'Synchronize axis' flag on the
    space encoding (NOT on <axis> elements that the utils parsers read), so this
    is the only place these live. Keyed by scope ('cols'/'rows')."""
    out: Dict[str, Dict[str, Any]] = {}
    for enc in ws.findall("table/style/style-rule/encoding[@type='space']"):
        mn, mx = enc.get("min"), enc.get("max")
        synced, rng = enc.get("synchronized"), enc.get("range-type")
        if mn is None and mx is None and synced is None and not rng:
            continue
        e = out.setdefault(enc.get("scope") or "axis", {})
        if mn is not None:
            e["min"] = _num(mn)
        if mx is not None:
            e["max"] = _num(mx)
        if synced is not None:
            e["synced"] = synced == "true"
        if rng and rng != "automatic":
            e["scale"] = rng  # e.g. 'fixed'
        fld = enc.get("field")
        if fld:
            e["field"] = _clean_tab_field(fld)
    return out


def _tab_axes(ws_name: str, ws: ET.Element) -> Optional[List[Dict[str, Any]]]:
    """Map a worksheet's axes into the common `style.axes` list shape.

    Combines utils' deterministic axis parsers (style-rule titles + pane <axis>
    range) with <encoding type='space'> bounds/scale/synchronize."""
    try:
        from utils import (_axes_from_style_rules, _axes_from_pane_axis_elements,
                           _axes_from_customized_axis)
        raw = (_axes_from_style_rules(ws_name, ws)
               + _axes_from_pane_axis_elements(ws_name, ws)
               + _axes_from_customized_axis(ws_name, ws))
    except Exception:
        raw = []

    by_scope: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []

    def _blank(name):
        return {"name": name, "labels": None, "title": None, "show_title": None,
                "scale": None, "min": None, "max": None, "synced": None,
                "display_units": None, "gridlines": None}

    for a in raw:
        scope = a.get("scope") or a.get("field") or "axis"
        if scope not in by_scope:
            by_scope[scope] = _blank(a.get("field") or a.get("scope") or "axis")
            order.append(scope)
        ent = by_scope[scope]
        ent["title"] = ent["title"] or _text_only_font(a.get("title"))
        if a.get("logarithmic"):
            ent["scale"] = "Logarithmic"
        if a.get("range_min") is not None:
            ent["min"] = a.get("range_min")
        if a.get("range_max") is not None:
            ent["max"] = a.get("range_max")

    # Overlay <encoding type='space'> bounds/scale/sync (the only home for these).
    for scope, e in _tab_encoding_axes(ws).items():
        if scope not in by_scope:
            by_scope[scope] = _blank(e.get("field") or scope)
            order.append(scope)
        ent = by_scope[scope]
        for k in ("min", "max", "synced"):
            if e.get(k) is not None:
                ent[k] = e[k]
        if e.get("scale") and not ent.get("scale"):
            ent["scale"] = e["scale"]

    out = [by_scope[s] for s in order
           if any(v for k, v in by_scope[s].items() if k != "name")]
    return out or None


def _tab_data_labels(rules: Dict[str, Dict[str, str]]) -> Optional[Dict[str, Any]]:
    """Map mark/label style-rules into the common `style.data_labels` shape."""
    mark = rules.get("mark", {})
    label = rules.get("label", {})
    show = None
    if "mark-labels-show" in mark:
        show = mark["mark-labels-show"] == "true"
    elif "display" in label:
        show = label["display"] == "true"
    dl = {
        "show": show,
        "position": mark.get("mark-labels-mode"),
        "display_units": None,
        "decimal_places": None,
        "font": _tab_font_from_formats(label),
    }
    return dl if any(v is not None for v in dl.values()) else None


def _tab_legend(ws: ET.Element, ws_name: str,
                legend_positions: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Map a worksheet's color legend into the common `style.legend` shape.

    Field comes from the mark color encoding; position from the dashboard's
    legend zone (if any) for this worksheet."""
    field = None
    for enc in ws.findall(".//style-rule[@element='mark']/encoding[@attr='color']"):
        field = _clean_tab_field(enc.get("field"))
        break
    position = legend_positions.get(ws_name)
    if not (field or position):
        return None
    return {
        "show": True,
        "position": position,
        "show_title": None,
        "title": _text_only_font(field),
        "labels": None,
    }


def _parse_worksheet_style(ws: ET.Element, ws_name: str = "",
                           legend_positions: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
    """Build a common visual `style` from a Tableau worksheet."""
    legend_positions = legend_positions or {}
    rules: Dict[str, Dict[str, str]] = {}
    for sr in ws.findall(".//style/style-rule"):
        el = sr.get("element")
        if el and el not in rules:
            rules[el] = _rule_formats(sr)

    ws_fmts = rules.get("worksheet", {})
    background = _tab_color_ref(ws_fmts.get("background-color"))
    container = None
    if background is not None:
        container = {
            "background": {"color": background, "transparency": None, "image": None, "show": None},
            "border": None, "shadow": None, "padding": None,
        }

    title_run = ws.find("layout-options/title//run")
    title = _tab_font_from_run(title_run)

    data_colors = _parse_worksheet_data_colors(ws)

    label_fmts = rules.get("label", {})
    mark_fmts = rules.get("mark", {})
    labels = None
    show = None
    if "mark-labels-show" in mark_fmts:
        show = mark_fmts["mark-labels-show"] == "true"
    label_font = _tab_font_from_formats(label_fmts)
    if show is not None or label_font is not None:
        labels = {"show": show, "font": label_font}

    style = {
        "container": container, "title": title, "subtitle": None,
        "data_colors": data_colors, "labels": labels,
        # Chart formatting in the SAME home as PowerBI (style.*), deterministic.
        "axes": _tab_axes(ws_name, ws),
        "legend": _tab_legend(ws, ws_name, legend_positions),
        "data_labels": _tab_data_labels(rules),
        "raw": _ws_raw(ws),
    }
    if not any(v for v in style.values()):
        return None
    return style


def _zone_container(zone: ET.Element) -> Optional[Dict[str, Any]]:
    """Build container border/padding from a dashboard zone's <zone-style>."""
    fmts = {f.get("attr"): f.get("value")
            for f in zone.findall("zone-style/format") if f.get("attr")}
    if not fmts:
        return None
    border = {
        "show": None,
        "color": _tab_color_ref(fmts.get("border-color")),
        "width": _num(fmts.get("border-width")),
        "style": fmts.get("border-style"),
        "radius": None,
    }
    if not any(v is not None for v in border.values()):
        border = None
    padding = _num(fmts.get("margin"))
    if border is None and padding is None:
        return None
    return {"background": None, "border": border, "shadow": None, "padding": padding}


def _tab_dashboard_background(dash: ET.Element) -> Optional[Dict[str, Any]]:
    """Read a dashboard's background-color from its <style> element, as a Fill."""
    st = dash.find("style")
    if st is None:
        return None
    for sr in st.findall("style-rule"):
        if sr.get("element") not in (None, "dashboard", "worksheet"):
            continue
        for f in sr.findall("format"):
            if f.get("attr") == "background-color":
                ref = _tab_color_ref(f.get("value"))
                if ref is not None:
                    return {"color": ref, "transparency": None, "image": None, "show": None}
    return None


_TAB_SKIP_ZONES = {"layout-basic", "layout-flow", "flipboard", "empty"}


def extract_tableau_styling(xml: bytes) -> Optional[Dict[str, Any]]:
    """Parse a Tableau .twb into the common styling overlay (same shape as PBI).

    Returns:
        { "theme": {...},
          "pages": { "<dashboard_name>": {"background": Fill|None,
                                          "visuals": {"<zone_id>": style}} },
          "worksheets": { "<worksheet_name>": style } }
    """
    root = _load_twb_root(xml)
    if root is None:
        return None

    # Legend positions (worksheet name -> dashboard legend zone type), deterministic.
    try:
        from utils import _collect_legend_positions
        legend_positions = _collect_legend_positions(root)
    except Exception:
        legend_positions = {}

    # Worksheet styles, keyed by worksheet name.
    worksheets: Dict[str, Any] = {}
    ws_root = root.find("worksheets")
    if ws_root is not None:
        for ws in ws_root.findall("worksheet"):
            name = ws.get("name")
            if not name:
                continue
            style = _parse_worksheet_style(ws, name, legend_positions)
            if style is not None:
                worksheets[name] = style

    # Datasource-level per-value color assignments (shared across worksheets).
    ds_colors, ds_palettes = _parse_datasource_color_encodings(root)

    # Theme: Tableau has no semantic theme; surface workbook + encoding palettes.
    named_palettes: List[Dict[str, Any]] = []
    prefs = root.find("preferences")
    if prefs is not None:
        for cp in prefs.findall("color-palette"):
            colors = [c.text for c in cp.findall("color") if c.text]
            if colors:
                named_palettes.append({"name": cp.get("name"), "colors": colors})
    for pname, cols in ds_palettes.items():
        named_palettes.append({"name": pname, "colors": cols})
    theme = {
        "name": None, "source_tool": "tableau",
        "data_palette": named_palettes[0]["colors"] if named_palettes else [],
        "named_palettes": named_palettes,
        # semantic_colors / text_classes / visual_styles / raw have no single
        # Tableau theme-file equivalent — null so the theme key set matches PowerBI.
        "semantic_colors": None, "text_classes": None, "visual_styles": None,
        "raw": None,
    }

    # Dashboard pages: zone container styles, keyed by zone id.
    pages: Dict[str, Any] = {}
    dash_root = root.find("dashboards")
    if dash_root is not None:
        for dash in dash_root.findall("dashboard"):
            dash_name = dash.get("name")
            if not dash_name:
                continue
            visuals: Dict[str, Any] = {}
            for zone in dash.findall(".//zone"):
                if zone.get("type-v2") in _TAB_SKIP_ZONES:
                    continue
                zid = zone.get("id")
                if not zid:
                    continue
                container = _zone_container(zone)
                ft_run = zone.find("formatted-text/run")
                ft_title = _tab_font_from_run(ft_run)
                if not (container or ft_title):
                    continue
                style = {
                    "container": container, "title": ft_title, "subtitle": None,
                    "data_colors": [], "labels": None,
                }
                visuals[zid] = style
            pages[dash_name] = {
                "background": _tab_dashboard_background(dash),
                "visuals": visuals,
            }

    return {"theme": theme, "pages": pages, "worksheets": worksheets,
            "datasource_colors": ds_colors}


def _merge_visual_styles(zone_style: Optional[Dict[str, Any]],
                         ws_style: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Combine a dashboard zone's container/title with its worksheet's data styling."""
    if zone_style is None and ws_style is None:
        return None
    base = dict(ws_style) if ws_style else {
        "container": None, "title": None, "subtitle": None,
        "data_colors": [], "labels": None,
    }
    if zone_style:
        zc = zone_style.get("container")
        if zc:
            if base.get("container"):
                # Worksheet supplies background; zone supplies border/padding.
                merged = dict(base["container"])
                for k in ("border", "padding"):
                    if zc.get(k) is not None:
                        merged[k] = zc[k]
                base["container"] = merged
            else:
                base["container"] = zc
        if not base.get("title") and zone_style.get("title"):
            base["title"] = zone_style["title"]
    return base


def _datasource_colors_for_visual(vis: Dict[str, Any],
                                  ds_colors: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Return data_color entries for any datasource-encoded field this visual uses."""
    if not ds_colors:
        return []
    out: List[Dict[str, Any]] = []
    for f in vis.get("fields", []) or []:
        col = (f.get("column") or "").strip()
        assigns = ds_colors.get(col)
        if not assigns:
            continue
        for a in assigns:
            entry = {"field": col, "value": a["value"], "color": a["color"]}
            if entry not in out:
                out.append(entry)
    return out


def apply_tableau_styling(final_json: Dict[str, Any], xml: bytes) -> None:
    """Merge deterministic Tableau styling into a common-model result in place.

    Runs AFTER run_tableau_flow (visualizations.pages carry visual_id + title)
    and BEFORE apply_readable_ids. No LLM involved.
    """
    overlay = extract_tableau_styling(xml)
    if not overlay:
        return

    if overlay.get("theme"):
        final_json["theme"] = overlay["theme"]
    # Tableau has no bookmarks; set the key to None so the structure matches PBI.
    final_json["bookmarks"] = None

    dash_overlay = overlay.get("pages", {})
    ws_overlay = overlay.get("worksheets", {})
    ds_colors = overlay.get("datasource_colors", {})

    pages = (final_json.get("visualizations") or {}).get("pages", [])
    for page in pages:
        dash = dash_overlay.get(page.get("display_name"))
        zone_visuals = dash.get("visuals", {}) if dash else {}

        page_colors: List[str] = []
        for vis in page.get("visuals", []) or []:
            vid = str(vis.get("visual_id") or "")
            title = vis.get("title")
            zone_style = zone_visuals.get(vid)
            ws_style = ws_overlay.get(title) if title else None
            style = _merge_visual_styles(zone_style, ws_style)

            # Attach datasource-level per-value colors to visuals that use the
            # encoded field (matched by the visual's field column names).
            ds_data_colors = _datasource_colors_for_visual(vis, ds_colors)
            if ds_data_colors:
                if style is None:
                    style = {"container": None, "title": None, "subtitle": None,
                             "data_colors": [], "labels": None}
                existing = style.get("data_colors") or []
                for entry in ds_data_colors:
                    if entry not in existing:
                        existing.append(entry)
                style["data_colors"] = existing

            if style is not None:
                vis["style"] = _normalize_style(style)
                _collect_palette(style, page_colors)

        # Always set the new shape so every page is uniform (overwrites the
        # LLM's old StylePreference/ColorPalette-shaped values). Same key set as PBI.
        page["styles"] = _normalize_page_styles(
            {"background": dash.get("background") if dash else None}
        )
        page["color_palettes"] = page_colors or None
