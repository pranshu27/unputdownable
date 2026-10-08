import xml.etree.ElementTree as ET
import io
import os
import re
import sys
import json
import logging
import zipfile
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Set, Tuple
from copy import deepcopy


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Namespace constants
# ---------------------------------------------------------------------------
_NS_USER = "http://www.tableausoftware.com/xml/user"
_NS_USER_PREFIX = f"{{{_NS_USER}}}"

# Tableau datatype raw values are passed through as-is to the LLM.
# The LLM is responsible for mapping them to the output schema types.

# File extensions to strip from table/relation names
_TABLE_NAME_EXTENSIONS = (".csv", ".xlsx", ".xls", ".tsv", ".txt", ".hyper", ".tde")


def _clean_table_name(name: str) -> str:
    """Strip file extensions and UUID suffixes from table/relation names for clean output.
    
    'tbl_sales.csv' → 'tbl_sales'
    'tbl_sales.csv1' → 'tbl_sales1' (alias copy)
    'tbl_products.csv_CF599A5A3F3545C4B351660B4AF0B46A' → 'tbl_products'
    'My Table' → 'My Table' (no extension, unchanged)
    """
    if not name:
        return name
    # First strip UUID suffixes (32-char hex after underscore, from object-graph IDs)
    # Pattern: name_<32 hex chars> e.g. tbl_sales.csv_B77FEE5F1B494BC0A37852D73F6C1E2F
    uuid_match = re.match(r'^(.+?)_([0-9A-Fa-f]{32})$', name)
    if uuid_match:
        name = uuid_match.group(1)
    # Then strip file extensions
    for ext in _TABLE_NAME_EXTENSIONS:
        if ext in name:
            idx = name.find(ext)
            suffix = name[idx + len(ext):]  # e.g. "1" for "tbl_sales.csv1"
            base = name[:idx]
            return base + suffix
    return name

# ---------------------------------------------------------------------------
# TableauWorkbookContext  –  the typed container passed between layers
# ---------------------------------------------------------------------------

@dataclass
class TableauWorkbookContext:
    """
    Single source of truth produced by preprocess_workbook().
    Agents consume only the sub-dict they need; raw XML never leaves this module.

    Domains
    -------
    model       – semantic model metadata (Agent 1 input)
    visuals     – worksheet / dashboard layout (future Agent 2 input)
    presentation – styles, formatting, thumbnails (future agents)
    """
    model: Dict[str, Any] = field(default_factory=dict)
    visuals: Dict[str, Any] = field(default_factory=dict)
    presentation: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _log_xml_preview(label: str, xml_text: str, limit: int = 2500) -> None:
    if not xml_text:
        logger.info("%s: <empty>", label)
        return
    if len(xml_text) <= limit:
        logger.info("%s:\n%s", label, xml_text)
        return
    logger.info(
        "%s (truncated, %d chars total):\n%s\n... [truncated]",
        label,
        len(xml_text),
        xml_text[:limit],
    )


def _extract_twb_from_twbx(data: bytes) -> bytes:
    """
    If *data* is a .twbx ZIP archive, extract and return the inner .twb XML bytes.
    If *data* is already raw XML (plain .twb), return it unchanged.

    Raises ValueError if the archive contains no .twb file.
    """
    if not zipfile.is_zipfile(io.BytesIO(data)):
        # Already raw XML — nothing to do
        return data

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        twb_entries = [name for name in zf.namelist() if name.lower().endswith(".twb")]

        if not twb_entries:
            raise ValueError(
                "Uploaded .twbx archive contains no .twb workbook file. "
                "The archive may be corrupt or not a valid Tableau packaged workbook."
            )

        if len(twb_entries) > 1:
            logger.warning(
                "[Tableau] .twbx archive contains %d .twb files: %s — using the first one: %s",
                len(twb_entries),
                twb_entries,
                twb_entries[0],
            )

        twb_bytes = zf.read(twb_entries[0])
        logger.info(
            "[Tableau] Extracted .twb (%s, %d bytes) from .twbx archive",
            twb_entries[0],
            len(twb_bytes),
        )
        return twb_bytes


def _root(xml: bytes) -> ET.Element:
    try:
        return ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid XML: {exc}") from exc


def _dashboards_using_datasource(root: ET.Element, ds_caption: str) -> List[str]:
    """Return dashboard names that reference a datasource by caption."""
    used: List[str] = []
    if not ds_caption:
        return used
    for dash in root.findall("dashboards/dashboard"):
        for ds_ref in dash.findall("datasources/datasource"):
            if ds_ref.get("caption") == ds_caption:
                used.append(dash.get("name", ""))
                break
    return used


# _infer_source_type removed: the LLM categorizes source type from raw
# connection_class and filename values.


def parse_datasources(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract and format datasource info per Expected schema."""
    datasources: List[Dict[str, Any]] = []
    for ds in root.findall('datasources/datasource'):
        caption = ds.get('caption', '')
        conn_el = ds.find('connection/named-connections/named-connection/connection')
        filename = conn_el.get('filename') if conn_el is not None else ''
        # Use caption as name if available, otherwise fallback to filename
        name = caption or os.path.basename(filename)
        ds_type = 'Excel' if filename.lower().endswith(('.xlsx', '.xls')) else 'Unknown'
        extract_el = ds.find('extract')
        is_extract = bool(extract_el and extract_el.get('enabled') == 'true')
        extract_sched = extract_el.get('units') if extract_el is not None else ''
        used_by: List[str] = []
        for dash in root.findall('dashboards/dashboard'):
            for ds_ref in dash.findall('datasources/datasource'):
                if ds_ref.get('caption') == caption:
                    used_by.append(dash.get('name'))
        datasources.append({
            "name": name,
            "tool": "Tableau",
            "type": ds_type,
            "connection_details": filename,
            "authentication_method": "",
            "refresh_schedule": "",
            "used_by": used_by,
            "is_extract": is_extract,
            "extract_refresh_schedule": extract_sched or "",
            "is_published": False
        })
    return datasources


def parse_data_model(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract tables and their columns into the Expected schema format."""
    type_map = {'date':'Date','integer':'Numeric','real':'Numeric','string':'String'}
    # Fields and intermediate extract tables to drop
    drop_fields = {"Customcal", "State", "City", "Postal Code", "Grouping", "Sub-Grouping"}
    models: List[Dict[str, Any]] = []
    for ds in root.findall('datasources/datasource'):
        seen_tables: set = set()
        for rel in ds.findall(".//relation[@type='table']"):
            tbl = rel.get('name')
            # Skip unnamed, duplicate, or extract tables
            if not tbl or tbl in seen_tables or tbl == "Extract":
                continue
            seen_tables.add(tbl)
            fields: List[Dict[str, Any]] = []
            cols_el = rel.find('columns')
            if cols_el is not None:
                for col in cols_el.findall('column'):
                    nm = col.get('name')
                    dt = col.get('datatype')
                    if nm and nm not in drop_fields and not nm.startswith('<'):
                        fields.append({"name": nm, "type": type_map.get(dt, dt.title() if dt else "")})
            # handle split and calculation fields, excluding dropped names
            ns_user = 'http://www.tableausoftware.com/xml/user'
            for col in ds.findall('column'):
                name = col.get('caption') or col.get('name')
                dt = col.get('datatype')
                if not name or name in drop_fields:
                    continue
                if col.get(f'{{{ns_user}}}SplitFieldOrigin') or col.find('calculation') is not None:
                    fields.append({"name": name, "type": type_map.get(dt, dt.title() if dt else "")})
            ds_caption = ds.get('caption')
            used: List[str] = []
            for dash in root.findall('dashboards/dashboard'):
                for ds_ref in dash.findall('datasources/datasource'):
                    if ds_ref.get('caption') == ds_caption:
                        used.append(dash.get('name'))
                        break
            models.append({
                "table_name": tbl,
                "tool": "Tableau",
                "fields": fields,
                "relationships": [],
                "used_by": used
            })
    return models


def extract_semantic_roles(root: ET.Element) -> Dict[str, str]:
    """Map Tableau column names to explicit semantic-role attributes."""
    semantic_roles: Dict[str, str] = {}
    for col in root.findall(".//column"):
        semantic_role = col.get("semantic-role")
        name = col.get("name")
        if not semantic_role or not name:
            continue
        semantic_roles[name.strip("[]")] = semantic_role
    return semantic_roles


def parse_transformations(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract all explicit calculations (splits & custom) as Data Transformations."""
    type_map={'date':'Date','integer':'Numeric','real':'Numeric','string':'String'}
    def dashboards_using(caption: str) -> List[str]:
        used = []
        for dash in root.findall('dashboards/dashboard'):
            for ds_ref in dash.findall('datasources/datasource'):
                if ds_ref.get('caption') == caption:
                    used.append(dash.get('name'))
                    break
        return used
    transformations = []
    ns_user = 'http://www.tableausoftware.com/xml/user'
    for ds in root.findall('datasources/datasource'):
        for col in ds.findall('column'):
            calc = col.find('calculation')
            if calc is None:
                continue
            name = col.get('caption') or col.get('name') or ""
            dt = col.get('datatype', '')
            data_type = type_map.get(dt, dt.title())
            role = col.get('role', '')
            expression = calc.get('formula', '')
            if col.get(f'{{{ns_user}}}SplitFieldOrigin'):
                desc = f"Extracts the {name} from its combined parent field"
            else:
                desc = f"Calculates {name}"
            transformations.append({
                "name": name,
                "tool": "Tableau",
                "data_type": data_type,
                "role": role,
                "expression": expression,
                "description": desc,
                "used_in": dashboards_using(ds.get('caption', '')),
                "filters": []
            })
    return transformations


def parse_hierarchies(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract hierarchies from drill-paths definitions."""
    hierarchies: List[Dict[str, Any]] = []
    for dp in root.findall('.//drill-paths/drill-path'):
        name = dp.get('name')
        members = [f.text for f in dp.findall('field') if f.text]
        hierarchies.append({'name': name, 'members': members})
    return hierarchies


def parse_sheets(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract worksheets with object_id and name."""
    sheets = []
    for ws in root.findall('worksheets/worksheet'):
        sid = ws.find('simple-id')
        obj_id = sid.get('uuid') if sid is not None else None
        sheets.append({'object_id': obj_id, 'name': ws.get('name')})
    return sheets

def extract_visualization_snippets(root: ET.Element) -> List[Dict[str, Any]]:
    """
    Gather raw XML snippets for each chart zone to feed into an LLM, excluding filters and layout elements.
    Returns a list of dicts with object_id, name, and xml_snippet of the <table> block.
    """
    snippets=[]
    for dash in root.findall('dashboards/dashboard'):
        seen=set()
        for z in dash.findall('.//zone'):
            typ2=z.get('type-v2') or z.get('type')
            vid=z.get('id')
            name=z.get('name')
            if not vid or not name or vid in seen or typ2 in ('filter','layout-basic','title'):
                continue
            seen.add(vid)
            ws=root.find(f"worksheets/worksheet[@name='{name}']")
            if ws is None: continue
            table=ws.find('table')
            if table is None: continue
            xml_snippet=ET.tostring(table,encoding='unicode')
            snippets.append({'object_id':vid,'name':name,'xml_snippet':xml_snippet})
    return snippets


# --- New: Visualization Sections for LLM ---
def extract_visualization_sections(root: ET.Element) -> str:
    """
    Combine <worksheets> and <dashboards> XML blocks into one string
    to feed to an LLM for extracting visualizations.
    """
    parts = []
    ws = root.find('worksheets')
    db = root.find('dashboards')
    if ws is not None:
        ws_xml = ET.tostring(ws, encoding='unicode')
        print("[Tableau] Capturing <worksheets> XML block")
        _log_xml_preview("Tableau worksheets XML", ws_xml)
        parts.append(ws_xml)
    if db is not None:
        db_xml = ET.tostring(db, encoding='unicode')
        print("[Tableau] Capturing <dashboards> XML block")
        _log_xml_preview("Tableau dashboards XML", db_xml)
        parts.append(db_xml)
    return '\n'.join(parts)


def extract_full_workbook_sections(root: ET.Element) -> str:
    """
    Combine every top-level workbook section into one bundle so the LLM can
    see the full Tableau context for migration and extraction.
    """
    parts = []
    included_tags = []
    for child in list(root):
        if child.tag is None:
            continue
        included_tags.append(child.tag)
        child_xml = ET.tostring(child, encoding='unicode')
        print(f"[Tableau] Capturing top-level XML block: <{child.tag}>")
        _log_xml_preview(f"Tableau XML block <{child.tag}>", child_xml)
        parts.append(child_xml)
    logger.info("Tableau full workbook sections included: %s", included_tags)
    return '\n'.join(parts)


def get_sections_for_llm(xml: bytes) -> Dict[str, Any]:
    """
    Prepare the raw XML snippets for Tableau workbook extraction.
    Returns a dict with keys:
      - datasources: List[str] of <datasource> XML strings
      - extracts: str of the <extract> block
      - visualizations: str combining <worksheets> + <dashboards>
      - full_workbook: str combining all top-level workbook sections
    """
    root = _root(xml)
    ds_snippets = [ET.tostring(ds, encoding='unicode')
                   for ds in root.findall('datasources/datasource')]
    for idx, ds_xml in enumerate(ds_snippets, start=1):
        print(f"[Tableau] Capturing datasource snippet #{idx}")
        _log_xml_preview(f"Tableau datasource snippet #{idx}", ds_xml)
    extract_el = root.find('extract')
    extracts = ET.tostring(extract_el, encoding='unicode') if extract_el is not None else ''
    if extracts:
        print("[Tableau] Capturing <extract> XML block")
        _log_xml_preview("Tableau extract snippet", extracts)
    visualizations = extract_visualization_sections(root)
    full_workbook = extract_full_workbook_sections(root)
    semantic_roles = extract_semantic_roles(root)
    print("[Tableau] XML snippet bundle ready")
    logger.info(
        "Tableau snippet bundle prepared: datasource_snippets=%d extract_present=%s visualizations_len=%d full_workbook_len=%d semantic_roles=%d",
        len(ds_snippets),
        bool(extracts),
        len(visualizations),
        len(full_workbook),
        len(semantic_roles),
    )
    return {
        "datasources": ds_snippets,
        "extracts": extracts,
        "visualizations": visualizations,
        "full_workbook": full_workbook,
        "semantic_roles": semantic_roles,
    }


def parse_filters(root: ET.Element) -> List[Dict[str, Any]]:
    """
    Extract only dashboard filter-zone definitions (i.e. exclude worksheet-level filters),
    without hard-coding specific filter names.
    """
    filters: List[Dict[str, Any]] = []
    seen_cols: Set[str] = set()

    for z in root.findall('.//zone'):
        zid = z.get('id')
        if not zid:
            continue

        # Normalize the zone’s type attribute
        zone_type = (z.get('type-v2') or z.get('type') or '').lower()

        # Only care about filter zones
        if 'filter' not in zone_type:
            continue

        # Exclude any worksheet-level filters dynamically
        if 'worksheet' in zone_type:
            continue

        # Determine which column(s) this zone is filtering
        col_param = z.get('param') or ''
        if not col_param or col_param in seen_cols:
            continue

        # Capture style/formatting
        style = {
            fmt_el.get('attr'): fmt_el.get('value')
            for fmt_el in z.findall('zone-style/format')
        }

        # Build the filter definition
        filters.append({
            'object_id':      zid,
            'name':           z.get('name') or col_param,
            'type':           z.get('type-v2') or z.get('type'),
            'columns':        [col_param],
            'formatting':     style,
            'interactivity': {
                'filter_action':   col_param,
                'target_sheet_id': z.get('target-sheet-id')
            },
            'sorting': {
                'by':    z.get('sort-by'),
                'order': z.get('sort-order')
            },
            'background_color': style.get('background-color')
        })

        seen_cols.add(col_param)

    return filters


def parse_parameters(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract script parameters/variables."""
    parameters=[]
    for var in root.findall('variable'):
        parameters.append({'name':var.get('name'),'type':'Variable','calculation':var.get('default') or ''})
    return parameters


def parse_dashboards(root: ET.Element) -> List[Dict[str, Any]]:
    '''Extract dashboards and their components, including all filter zones (e.g., Sub-Grouping).'''
    dashboards: List[Dict[str, Any]] = []

    for dash in root.findall('dashboards/dashboard'):
        # Dashboard ID & name
        sid = dash.find('simple-id')
        object_id = sid.get('uuid') if sid is not None else None
        title_el = dash.find('layout-options/title/formatted-text/run')
        name = title_el.text.strip() if title_el is not None else dash.get('name')

        # Size & background
        size_el = dash.find('size')
        width = int(size_el.get('maxwidth')) if size_el is not None else None
        height = int(size_el.get('maxheight')) if size_el is not None else None

        components: List[Dict[str, Any]] = []
        seen_ids: Set[str] = set()

        # Include charts and all filter zones (including Sub-Grouping splits)
        for z in dash.findall('.//zone'):
            zid = z.get('id')
            if not zid or zid in seen_ids:
                continue
            seen_ids.add(zid)

            typ2 = (z.get('type-v2') or z.get('type') or '').lower()
            if 'layout' in typ2 or 'title' in typ2:
                continue

            # **Single zname assignment**: use param for any filter zone
            if 'filter' in typ2:
                zname = z.get('param')
            else:
                zname = z.get('name')

            # drop any unnamed zones
            if not zname:
                continue

            components.append({
                'name':       zname,
                'object_id':  zid,
                'position': {
                    'x':      int(z.get('x') or 0),
                    'y':      int(z.get('y') or 0),
                    'width':  int(z.get('w') or z.get('width') or 0),
                    'height': int(z.get('h') or z.get('height') or 0)
                },
                'font_size': 8,
                'color':     '#000000'
            })

        dashboards.append({
            'name':             name,
            'object_id':        object_id,
            'width':            width,
            'height':           height,
            'background_color': '#FFFFFF',
            'components':       components
        })

    return dashboards

def parse_structured_workbook(xml: bytes) -> Dict[str, Any]:
    """Legacy structured extraction (kept for backward compatibility)."""
    root = _root(xml)
    return {
        "Data Sources": parse_datasources(root),
        "Data Model": parse_data_model(root),
        "Data Transformations": parse_transformations(root),
        "Hierarchies": parse_hierarchies(root),
        "Filters": parse_filters(root),
        "Parameters or Variables": parse_parameters(root),
        "Sheets": parse_sheets(root),
        "Dashboards": parse_dashboards(root)
    }



if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python utils.py <input.twb|twbx> [output.json]")
        sys.exit(1)
    xml_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    with open(xml_path, 'rb') as f:
        content = f.read()
    parsed = parse_structured_workbook(content)
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as outf:
            json.dump(parsed, outf, indent=2)
        print(f"Results saved to {output_path}")
    else:
        print(json.dumps(parsed, indent=2))


# ===================================================================
# COMPREHENSIVE PREPROCESSING LAYER  (new)
# ===================================================================
# Every function below extracts structured metadata from the parsed
# XML tree.  Nothing below returns raw XML strings.
# ===================================================================

def _extract_named_connections(ds: ET.Element) -> List[Dict[str, Any]]:
    """Extract all named-connection entries from a datasource element."""
    conns: List[Dict[str, Any]] = []
    for nc in ds.findall("connection/named-connections/named-connection"):
        inner = nc.find("connection")
        if inner is None:
            continue
        conns.append({
            "name": nc.get("name", ""),
            "caption": nc.get("caption", ""),
            "class": inner.get("class", ""),
            "filename": inner.get("filename", ""),
            "server": inner.get("server", ""),
            "port": inner.get("port", ""),
            "dbname": inner.get("dbname", ""),
            "schema": inner.get("schema", ""),
            "username": inner.get("username", ""),
            "authentication": inner.get("authentication", ""),
            "warehouse": inner.get("warehouse", ""),
            "directory": inner.get("directory", ""),
            "sslmode": inner.get("sslmode", ""),
        })
    return conns


def _extract_datasources_comprehensive(root: ET.Element) -> List[Dict[str, Any]]:
    """Comprehensive datasource extraction for the model domain."""
    datasources: List[Dict[str, Any]] = []
    for ds in root.findall("datasources/datasource"):
        ds_name = ds.get("name", "")
        ds_caption = ds.get("caption", "")
        ds_inline = ds.get("inline", "")
        ds_version = ds.get("version", "")
        ds_hasconnection = ds.get("hasconnection", "")

        # Skip internal-only datasources (e.g. "Parameters") that have no external connection.
        # These are captured separately as calculations with semantic_type="parameter".
        if ds_hasconnection == "false" and ds_inline == "true":
            continue
        if ds_name == "Parameters" and not ds.find("connection"):
            continue

        top_conn = ds.find("connection")
        conn_class = top_conn.get("class", "") if top_conn is not None else ""
        named_conns = _extract_named_connections(ds)
        inner_conn = ds.find("connection/named-connections/named-connection/connection")
        filename = inner_conn.get("filename", "") if inner_conn is not None else ""
        server = inner_conn.get("server", "") if inner_conn is not None else ""
        dbname = inner_conn.get("dbname", "") if inner_conn is not None else ""
        schema = inner_conn.get("schema", "") if inner_conn is not None else ""
        auth = inner_conn.get("authentication", "") if inner_conn is not None else ""
        port = inner_conn.get("port", "") if inner_conn is not None else ""
        # Collect all file paths from named connections (for multi-table datasources)
        all_paths: List[str] = []
        for nc_conn in ds.findall("connection/named-connections/named-connection/connection"):
            nc_file = nc_conn.get("filename", "")
            if nc_file:
                clean = _clean_table_name(nc_file)
                if clean not in all_paths:
                    all_paths.append(clean)
        # Also collect table/relation names for multi-table datasources
        if top_conn is not None:
            for rel in top_conn.findall(".//relation[@type='table']"):
                rel_name = rel.get("name", "")
                if rel_name:
                    clean = _clean_table_name(rel_name)
                    if clean not in all_paths:
                        all_paths.append(clean)
        extract_el = ds.find("extract")
        is_extract = bool(extract_el is not None and extract_el.get("enabled") == "true")
        extract_units = extract_el.get("units", "") if extract_el is not None else ""
        extract_count = extract_el.get("count", "") if extract_el is not None else ""
        extract_conn = extract_el.find("connection") if extract_el is not None else None
        extract_conn_class = extract_conn.get("class", "") if extract_conn is not None else ""
        aliases_el = ds.find("aliases")
        aliases_enabled = aliases_el.get("enabled", "") if aliases_el is not None else ""
        used_by = _dashboards_using_datasource(root, ds_caption)
        # Extract datasource-level mark color encodings (value → hex color mappings)
        color_encodings: List[Dict[str, Any]] = []
        for rule in ds.findall("style/style-rule[@element='mark']"):
            for enc in rule.findall("encoding[@attr='color']"):
                field = enc.get("field", "")
                color_map: Dict[str, str] = {}
                for m in enc.findall("map"):
                    color = m.get("to", "")
                    bucket = m.find("bucket")
                    value = bucket.text.strip().strip('"') if bucket is not None and bucket.text else ""
                    if color and value:
                        color_map[value] = color
                if field and color_map:
                    color_encodings.append({
                        "field": field,
                        "color_assignments": color_map,
                    })
        # Extract <cols> map: field caption -> physical (table, column).
        # This is Tableau's authoritative source for resolving which physical
        # table a referenced field actually lives in.
        cols_map: Dict[str, Dict[str, str]] = {}
        for cm in ds.findall("connection/cols/map"):
            key = (cm.get("key", "") or "").strip()
            value = (cm.get("value", "") or "").strip()
            m = re.match(r"\[([^\]]+)\]\.\[([^\]]+)\]", value)
            if key and m:
                table_raw, col_raw = m.group(1), m.group(2)
                cols_map[key.strip("[]")] = {
                    "table_raw": table_raw,
                    "table": _clean_table_name(table_raw),
                    "column": col_raw,
                }
        datasources.append({
            "name": ds_caption or ds_name,
            "internal_name": ds_name,
            "caption": ds_caption,
            "version": ds_version,
            "inline": ds_inline,
            "has_connection": ds_hasconnection,
            "connection_class": conn_class,
            "server": server,
            "port": port,
            "database": dbname,
            "schema": schema,
            "path": filename or (all_paths[0] if all_paths else ""),
            "paths": all_paths if len(all_paths) > 1 else None,
            "authentication_method": auth,
            "named_connections": named_conns,
            "is_extract": is_extract,
            "extract_units": extract_units,
            "extract_count": extract_count,
            "extract_connection_class": extract_conn_class,
            "aliases_enabled": aliases_enabled,
            "used_by_dashboards": used_by,
            "is_published": False,
            "color_encodings": color_encodings if color_encodings else None,
            "cols_map": cols_map if cols_map else None,
        })
    return datasources


def _extract_tables_comprehensive(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract all physical/logical tables with full column metadata (raw values only)."""
    tables: List[Dict[str, Any]] = []
    sem_roles = extract_semantic_roles(root)
    for ds in root.findall("datasources/datasource"):
        ds_name = ds.get("name", "")
        ds_caption = ds.get("caption", "")
        seen_tables: Set[str] = set()
        for rel in ds.findall(".//relation[@type='table']"):
            tbl_name = rel.get("name", "")
            tbl_table = rel.get("table", "")
            if not tbl_name or tbl_name == "Extract":
                continue
            # Store both raw and clean names for mapping
            clean_name = _clean_table_name(tbl_name)
            # Deduplicate on clean name (same physical table may appear with different IDs)
            if clean_name in seen_tables:
                continue
            seen_tables.add(clean_name)
            columns: List[Dict[str, Any]] = []
            cols_el = rel.find("columns")
            if cols_el is not None:
                for col in cols_el.findall("column"):
                    nm = col.get("name", "")
                    if not nm or nm.startswith("<"):
                        continue
                    dt = col.get("datatype", "")
                    ordinal = col.get("ordinal", "")
                    columns.append({
                        "name": nm,
                        "datatype": dt,
                        "ordinal": ordinal,
                        "hidden": False,
                        "role": "",
                        "semantic_role": sem_roles.get(nm.strip("[]")),
                    })
            for col in ds.findall("column"):
                col_name = col.get("name", "")
                col_caption = col.get("caption", "")
                display = col_caption or col_name
                dt = col.get("datatype", "")
                role = col.get("role", "")
                col_type = col.get("type", "")
                hidden = col.get("hidden", "false") == "true"
                is_split = bool(col.get(f"{_NS_USER_PREFIX}SplitFieldOrigin"))
                has_calc = col.find("calculation") is not None
                sem = col.get("semantic-role", "")
                if is_split or has_calc:
                    columns.append({
                        "name": display.strip("[]"),
                        "internal_name": col_name,
                        "datatype": dt,
                        "role": role,
                        "type": col_type,
                        "hidden": hidden,
                        "semantic_role": sem or sem_roles.get(col_name.strip("[]")),
                        "is_split": is_split,
                        "has_calculation": has_calc,
                    })
            tables.append({
                "table_name": clean_name,
                "table_ref": tbl_table,
                "datasource_name": ds_name,
                "datasource_caption": ds_caption,
                "columns": columns,
                "used_by_dashboards": _dashboards_using_datasource(root, ds_caption),
            })
    return tables


def _extract_column_aliases(root: ET.Element) -> List[Dict[str, Any]]:
    """Map internal column names to their display captions across all datasources."""
    aliases: List[Dict[str, Any]] = []
    for ds in root.findall("datasources/datasource"):
        ds_name = ds.get("name", "")
        for col in ds.findall("column"):
            internal = col.get("name", "")
            caption = col.get("caption", "")
            if caption and internal and caption != internal:
                aliases.append({
                    "datasource": ds_name,
                    "internal_name": internal,
                    "caption": caption,
                })
    return aliases


def _extract_measure_names_aliases(root: ET.Element) -> Dict[str, Dict[str, str]]:
    """Map each [:Measure Names] pseudo-column's alias keys to their display labels.

    When a Tableau worksheet pivots several measures onto a single axis it stores
    the per-measure legend label under the [:Measure Names] column as
    ``<aliases><alias key='"<member_ref>"' value='<label>'/></aliases>``. The key
    is the fully-qualified measure reference (quoted in the XML); the value is the
    label shown for that measure.

    Returns ``{datasource_name: {member_ref: label}}`` with member_ref unquoted
    and the alias entries kept in document (declaration) order — downstream code
    relies on that ordering to lay out the synthesized measure fields.
    """
    result: Dict[str, Dict[str, str]] = {}
    for ds in root.findall("datasources/datasource"):
        ds_name = ds.get("name", "")
        for col in ds.findall("column"):
            if col.get("name", "") != "[:Measure Names]":
                continue
            aliases_el = col.find("aliases")
            if aliases_el is None:
                continue
            alias_map: Dict[str, str] = {}
            for alias in aliases_el.findall("alias"):
                key = (alias.get("key", "") or "").strip().strip('"')
                value = alias.get("value", "")
                if key and value:
                    alias_map[key] = value
            if alias_map:
                result[ds_name] = alias_map
    return result


def _extract_joins_and_relationships(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract all join clauses and relationships from datasource relation trees.

    Handles two Tableau models:
    1. Legacy joins: <connection> → <relation join="..."> elements
    2. Newer Relationships model: FCP object-graph elements containing
       <relationship> with <first-end-point>/<second-end-point> and <expression>
    """
    relationships: List[Dict[str, Any]] = []
    seen: set = set()  # Track clause expressions to deduplicate
    order = 0
    for ds in root.findall("datasources/datasource"):
        ds_name = ds.get("name", "")
        ds_caption = ds.get("caption", ds_name)

        # --- Legacy joins: search within <connection> elements ---
        conn_el = ds.find("connection")
        if conn_el is not None:
            for rel in conn_el.findall(".//relation[@join]"):
                join_type = rel.get("join", "")
                join_type_v2 = rel.get("type", "")
                # Must have at least one clause to be a valid join
                clause_els = rel.findall("clause")
                if not clause_els:
                    continue
                # Extract clause expressions — handle nested <expression op='='>
                clauses: List[Dict[str, str]] = []
                for clause in clause_els:
                    clause_type = clause.get("type", "")
                    left_col = ""
                    right_col = ""
                    eq_expr = clause.find("expression[@op='=']")
                    if eq_expr is not None:
                        inner_exprs = eq_expr.findall("expression")
                        if len(inner_exprs) >= 1:
                            left_col = inner_exprs[0].get("op", "")
                        if len(inner_exprs) >= 2:
                            right_col = inner_exprs[1].get("op", "")
                    else:
                        exprs = clause.findall("expression")
                        if len(exprs) >= 1:
                            left_col = exprs[0].get("op", exprs[0].get("value", ""))
                        if len(exprs) >= 2:
                            right_col = exprs[1].get("op", exprs[1].get("value", ""))
                    clauses.append({"type": clause_type, "left": left_col, "right": right_col})
                if not clauses:
                    continue
                # Derive table names from clause expressions
                left_table = ""
                right_table = ""
                if clauses[0]["left"]:
                    parts = clauses[0]["left"].split("].[")
                    if len(parts) == 2:
                        left_table = parts[0].lstrip("[")
                if clauses[0]["right"]:
                    parts = clauses[0]["right"].split("].[")
                    if len(parts) == 2:
                        right_table = parts[0].lstrip("[")
                if not left_table or not right_table:
                    direct_children = [ch for ch in rel if ch.tag == "relation"]
                    if not left_table and len(direct_children) > 0:
                        left_table = direct_children[0].get("name", "")
                    if not right_table and len(direct_children) > 1:
                        right_table = direct_children[1].get("name", "")
                # Deduplicate
                clause_key = tuple((c["left"], c["right"]) for c in clauses)
                dedup_key = (clause_key, join_type)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                order += 1
                relationships.append({
                    "datasource": ds_caption or ds_name,
                    "join_type": join_type,
                    "relation_type": join_type_v2,
                    "left_table": _clean_table_name(left_table),
                    "right_table": _clean_table_name(right_table),
                    "clauses": clauses,
                    "order": order,
                })

        # --- Newer Tableau Relationships model (FCP object-graph) ---
        # These are stored under tags like:
        #   _.fcp.ObjectModelEncapsulateLegacy.true...object-graph
        for child in ds:
            if "object-graph" not in child.tag:
                continue

            # Build object-id → table name mapping from <object> elements
            obj_map: Dict[str, str] = {}
            for obj in child.findall(".//object"):
                obj_id = obj.get("id", "")
                if not obj_id:
                    continue
                # Get the relation name inside the object (physical table name)
                rel_el = obj.find(".//relation")
                rel_name = rel_el.get("name", "") if rel_el is not None else ""
                obj_caption = obj.get("caption", "")
                # Prefer relation name, fallback to caption; clean extensions
                raw_name = rel_name or obj_caption or obj_id
                obj_map[obj_id] = _clean_table_name(raw_name)

            # Parse <relationship> elements
            for rel_el in child.findall(".//relationship"):
                # Extract join columns from expression tree
                expr = rel_el.find("expression")
                if expr is None:
                    continue

                # Collect all equality clauses from the expression
                rel_clauses: List[Dict[str, str]] = []
                op = expr.get("op", "")
                if op == "=":
                    # Single equality
                    inner = expr.findall("expression")
                    if len(inner) >= 2:
                        left_col = inner[0].get("op", "")
                        right_col = inner[1].get("op", "")
                        rel_clauses.append({"type": "join", "left": left_col, "right": right_col})
                elif op == "AND":
                    # Multiple conditions (compound key or inequality)
                    for sub_expr in expr.findall("expression"):
                        sub_op = sub_expr.get("op", "")
                        if sub_op == "=":
                            sub_inner = sub_expr.findall("expression")
                            if len(sub_inner) >= 2:
                                left_col = sub_inner[0].get("op", "")
                                right_col = sub_inner[1].get("op", "")
                                rel_clauses.append({"type": "join", "left": left_col, "right": right_col})
                        else:
                            # Handle FCP-namespaced operators (inequality relationships)
                            # Attributes like: _.fcp.InequalityRelationships.true...op = "<="
                            fcp_op = ""
                            for attr_name, attr_val in sub_expr.attrib.items():
                                if "InequalityRelationships.true" in attr_name and "op" in attr_name:
                                    fcp_op = attr_val
                                    break
                            if not fcp_op and sub_op:
                                fcp_op = sub_op
                            if fcp_op:
                                sub_inner = sub_expr.findall("expression")
                                left_col = ""
                                right_col = ""
                                if len(sub_inner) >= 2:
                                    # Get values from FCP attributes or standard op
                                    for attr_name, attr_val in sub_inner[0].attrib.items():
                                        if "InequalityRelationships.true" in attr_name and "op" in attr_name:
                                            left_col = attr_val
                                            break
                                    if not left_col:
                                        left_col = sub_inner[0].get("op", "")
                                    for attr_name, attr_val in sub_inner[1].attrib.items():
                                        if "InequalityRelationships.true" in attr_name and "op" in attr_name:
                                            right_col = attr_val
                                            break
                                    if not right_col:
                                        right_col = sub_inner[1].get("op", "")
                                if left_col and right_col:
                                    rel_clauses.append({"type": fcp_op, "left": left_col, "right": right_col})

                if not rel_clauses:
                    continue

                # Get endpoint object IDs to resolve table names
                first_ep = rel_el.find("first-end-point")
                second_ep = rel_el.find("second-end-point")
                left_obj_id = first_ep.get("object-id", "") if first_ep is not None else ""
                right_obj_id = second_ep.get("object-id", "") if second_ep is not None else ""

                left_table = obj_map.get(left_obj_id, left_obj_id)
                right_table = obj_map.get(right_obj_id, right_obj_id)

                # Clean column references: strip brackets [Column Name] → Column Name
                for cl in rel_clauses:
                    cl["left"] = cl["left"].strip("[]")
                    cl["right"] = cl["right"].strip("[]")

                # Deduplicate
                clause_key = tuple((c["left"], c["right"]) for c in rel_clauses)
                dedup_key = (clause_key, "relationship")
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                order += 1
                relationships.append({
                    "datasource": ds_caption or ds_name,
                    "join_type": "inner",  # Tableau relationships default to inner
                    "relation_type": "relationship",
                    "left_table": left_table,
                    "right_table": right_table,
                    "clauses": rel_clauses,
                    "order": order,
                })

    return relationships


def _extract_calculations_comprehensive(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract all calculated columns with formulas and dependencies."""
    calculations: List[Dict[str, Any]] = []
    for ds in root.findall("datasources/datasource"):
        ds_name = ds.get("name", "")
        ds_caption = ds.get("caption", "")
        for col in ds.findall("column"):
            calc_el = col.find("calculation")
            if calc_el is None:
                continue
            col_name = col.get("name", "")
            caption = col.get("caption", "")
            dt = col.get("datatype", "")
            role = col.get("role", "")
            col_type = col.get("type", "")
            hidden = col.get("hidden", "false") == "true"
            formula = calc_el.get("formula", "")
            calc_class = calc_el.get("class", "")
            is_split = bool(col.get(f"{_NS_USER_PREFIX}SplitFieldOrigin"))
            is_bin = calc_class == "bin"
            split_origin = col.get(f"{_NS_USER_PREFIX}SplitFieldOrigin", "")
            split_offset = col.get(f"{_NS_USER_PREFIX}SplitFieldOffset", "")
            split_sep = col.get(f"{_NS_USER_PREFIX}SplitFieldSeparator", "")
            depends_on: List[str] = re.findall(r"\[([^\]]+)\]", formula) if formula else []
            calculations.append({
                "datasource": ds_name,
                "datasource_caption": ds_caption,
                "internal_name": col_name,
                "caption": caption or col_name.strip("[]"),
                "datatype": dt,
                "role": role,
                "type": col_type,
                "hidden": hidden,
                "formula": formula,
                "calculation_class": calc_class,
                "is_split": is_split,
                "is_bin": is_bin,
                "split_origin": split_origin,
                "split_offset": split_offset,
                "split_separator": split_sep,
                "depends_on": depends_on,
                "used_in_dashboards": _dashboards_using_datasource(root, ds_caption),
            })
    return calculations


def _extract_parameters_comprehensive(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract Tableau parameters from the Parameters datasource and top-level variables."""
    params: List[Dict[str, Any]] = []
    for ds in root.findall("datasources/datasource"):
        if ds.get("name", "").lower() == "parameters" or ds.get("caption", "").lower() == "parameters":
            for col in ds.findall("column"):
                calc_el = col.find("calculation")
                rng = col.find("range")
                members = col.find("members")
                param: Dict[str, Any] = {
                    "name": col.get("caption", col.get("name", "")),
                    "internal_name": col.get("name", ""),
                    "datatype": col.get("datatype", ""),
                    "role": col.get("role", ""),
                    "type": col.get("type", ""),
                    "value": col.get("value", ""),
                    "formula": calc_el.get("formula", "") if calc_el is not None else "",
                    "param_domain_type": col.get("param-domain-type", ""),
                }
                if rng is not None:
                    param["range"] = {
                        "min": rng.get("min", ""),
                        "max": rng.get("max", ""),
                        "granularity": rng.get("granularity", ""),
                    }
                if members is not None:
                    param["allowed_values"] = [
                        m.get("value", "") for m in members.findall("member")
                    ]
                params.append(param)
    for var in root.findall("variable"):
        params.append({
            "name": var.get("name", ""),
            "type": "variable",
            "value": var.get("default", ""),
        })
    return params


def _extract_filters_comprehensive(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract datasource-level, shared-view, and worksheet-level filter definitions."""
    filters: List[Dict[str, Any]] = []

    def _parse_groupfilter_members(gf_el: ET.Element) -> List[str]:
        """Recursively collect member values from groupfilter trees."""
        members: List[str] = []
        member = gf_el.get("member", "")
        if member:
            members.append(member)
        for child_gf in gf_el.findall("groupfilter"):
            members.extend(_parse_groupfilter_members(child_gf))
        return members

    def _parse_filter(filt: ET.Element, scope: str, context_name: str) -> Dict[str, Any]:
        col_ref = filt.get("column", "")
        filt_class = filt.get("class", "")
        include_values: List[str] = []
        filter_config: Dict[str, Any] = {}
        for gf in filt.findall("groupfilter"):
            func = gf.get("function", "")
            include_values.extend(_parse_groupfilter_members(gf))
            # Capture top-N / order config
            if func in ("end", "order", "level-members"):
                for attr in ("count", "end", "direction", "expression", "function", "units"):
                    val = gf.get(attr)
                    if val:
                        filter_config[attr] = val
        # Capture quantitative range filters
        min_el = filt.find("min")
        max_el = filt.find("max")
        if min_el is not None and min_el.text:
            filter_config["min"] = min_el.text
        if max_el is not None and max_el.text:
            filter_config["max"] = max_el.text
        return {
            "column": col_ref,
            "class": filt_class,
            "include_values": include_values,
            "filter_config": filter_config if filter_config else None,
            "scope": scope,
            "context": context_name,
        }

    # 1. Datasource-level filters
    for ds in root.findall("datasources/datasource"):
        ds_name = ds.get("name", "")
        for filt in ds.findall(".//filter"):
            filters.append(_parse_filter(filt, "datasource", ds_name))

    # 2. Shared-view filters (workbook-level)
    for sv in root.findall("shared-views/shared-view"):
        sv_name = sv.get("name", "")
        for filt in sv.findall("filter"):
            filters.append(_parse_filter(filt, "shared_view", sv_name))

    # 3. Worksheet-level filters
    for ws in root.findall(_WORKSHEETS_PATH):
        ws_name = ws.get("name", "")
        for filt in ws.findall("table/view/filter"):
            filters.append(_parse_filter(filt, "worksheet", ws_name))
    return filters


def _parse_groupfilter_members_flat(group: ET.Element) -> List[Dict[str, Any]]:
    """Collect top-level and one level of nested groupfilter members."""
    members: List[Dict[str, Any]] = []
    for gf in group.findall("groupfilter"):
        member = gf.get("member", "")
        if member:
            members.append({"function": gf.get("function", ""), "member": member})
        for sub_gf in gf.findall("groupfilter"):
            sub_member = sub_gf.get("member", "")
            if sub_member:
                members.append({"function": sub_gf.get("function", ""), "member": sub_member})
    return members


def _extract_groups_and_sets(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract group and set definitions from datasource columns."""
    items: List[Dict[str, Any]] = []
    for ds in root.findall("datasources/datasource"):
        ds_name = ds.get("name", "")
        for group in ds.findall("group"):
            g_name = group.get("name", "")
            items.append({
                "datasource": ds_name,
                "name": group.get("caption", "") or g_name,
                "internal_name": g_name,
                "hidden": group.get("hidden", "false") == "true",
                "kind": "group",
                "members": _parse_groupfilter_members_flat(group),
            })
    return items


def _extract_metadata_records(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract metadata-record elements with remote/local name mappings."""
    records: List[Dict[str, Any]] = []
    for ds in root.findall("datasources/datasource"):
        ds_name = ds.get("name", "")
        for mr in ds.findall(".//metadata-record"):
            rec: Dict[str, Any] = {"datasource": ds_name, "class": mr.get("class", "")}
            for child in mr:
                if child.tag and child.text:
                    rec[child.tag.replace("-", "_")] = child.text.strip()
            records.append(rec)
    return records


def _extract_extract_info(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract extract/live connection details per datasource."""
    infos: List[Dict[str, Any]] = []
    for ds in root.findall("datasources/datasource"):
        ds_name = ds.get("name", "")
        extract_el = ds.find("extract")
        if extract_el is not None:
            conn = extract_el.find("connection")
            infos.append({
                "datasource": ds_name,
                "enabled": extract_el.get("enabled", "false"),
                "units": extract_el.get("units", ""),
                "count": extract_el.get("count", ""),
                "connection_class": conn.get("class", "") if conn is not None else "",
            })
        else:
            infos.append({
                "datasource": ds_name,
                "enabled": "false",
                "units": "",
                "count": "",
                "connection_class": "",
            })
    return infos


def _extract_custom_sql(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract custom SQL queries from <relation type='text'> elements."""
    queries: List[Dict[str, Any]] = []
    for ds in root.findall("datasources/datasource"):
        ds_name = ds.get("name", "")
        ds_caption = ds.get("caption", "")
        for rel in ds.findall(".//relation[@type='text']"):
            sql_text = rel.text.strip() if rel.text else ""
            rel_name = rel.get("name", "")
            connection = rel.get("connection", "")
            queries.append({
                "datasource": ds_name,
                "datasource_caption": ds_caption,
                "name": rel_name,
                "connection": connection,
                "sql": sql_text,
            })
    return queries


# Tableau user functions that signal row-level security when used in a
# calculated field (the calc-based RLS mechanism, as opposed to <user-filter>).
_TABLEAU_USER_FUNC_RE = re.compile(
    r'\b(USERNAME|FULLNAME|ISMEMBEROF|USERDOMAIN|ISUSERNAME|ISFULLNAME)\s*\(',
    re.IGNORECASE,
)


def _extract_security(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract row-level security definitions. Tableau implements RLS two ways,
    both captured here:

      1. ``<user-filter>`` — an inline mapping of user -> allowed column values.
      2. A calculated field that uses a Tableau user function (USERNAME /
         FULLNAME / ISMEMBEROF / USERDOMAIN / ...) and is applied as a
         data-source filter. This is the common "security calc + data source
         filter = TRUE" pattern. We capture the calc's raw formula so the
         downstream can translate it to a Power BI dynamic-RLS filter.
    """
    security: List[Dict[str, Any]] = []
    for ds in root.findall("datasources/datasource"):
        ds_name = ds.get("name", "")

        # (1) <user-filter> — inline user/value mapping.
        for uf in ds.findall(".//user-filter"):
            uf_name = uf.get("name", "")
            uf_column = uf.get("column", "")
            members: List[Dict[str, str]] = []
            for gf in uf.findall(".//groupfilter"):
                func = gf.get("function", "")
                member = gf.get("member", "")
                user = gf.get("user", "")
                if member or user:
                    members.append({"function": func, "member": member, "user": user})
            security.append({
                "datasource": ds_name,
                "name": uf_name,
                "column": uf_column,
                "members": members,
                "scope": "datasource",
                "kind": "user_filter",
            })

        # (2) Calculated-field RLS. First map every calc that uses a user
        # function (keyed by its internal name, which is how a <filter>
        # references it). Then any data-source <filter> on such a calc is the
        # RLS application — keep the calc's formula for translation.
        user_calcs: Dict[str, Dict[str, str]] = {}
        for col in ds.findall("column"):
            calc_el = col.find("calculation")
            if calc_el is None:
                continue
            formula = calc_el.get("formula", "") or ""
            if _TABLEAU_USER_FUNC_RE.search(formula):
                user_calcs[col.get("name", "")] = {
                    "caption": col.get("caption", "") or col.get("name", "").strip("[]"),
                    "formula": formula,
                    "datatype": col.get("datatype", ""),
                }
        seen_calc_filters: set = set()
        for filt in ds.findall(".//filter"):
            fcol = filt.get("column", "")
            if fcol in user_calcs and fcol not in seen_calc_filters:
                seen_calc_filters.add(fcol)
                calc = user_calcs[fcol]
                keep_values = [
                    gf.get("member", "")
                    for gf in filt.findall(".//groupfilter")
                    if gf.get("member")
                ]
                security.append({
                    "datasource": ds_name,
                    "name": calc["caption"],
                    "column": fcol,
                    "members": [],
                    "scope": "datasource",
                    "kind": "calculation",
                    "formula": calc["formula"],
                    "datatype": calc.get("datatype", ""),
                    "keep_values": keep_values,
                })

    # Workbook-level permission rules — Tableau Server view/edit access, NOT
    # row-level data security (no Power BI table-RLS analog).
    for perm in root.findall(".//permission-rule"):
        security.append({
            "datasource": "",
            "name": perm.get("name", ""),
            "column": "",
            "members": [],
            "scope": "workbook",
            "kind": "permission_rule",
            "rule": perm.get("rule", ""),
        })
    return security


# --- Visuals domain extractors (future Agent 2) ---

_GEO_LATLON_COLS = ("[Latitude (generated)]", "[Longitude (generated)]")
_GEO_GENERATED_FIELDS = {
    "Latitude (generated)", "Longitude (generated)", "Geometry (generated)",
}
_GEO_ROLES = {
    "[Country].[Name]", "[State].[Name]", "[City].[Name]",
    "[ZipCode].[Name]", "[County].[Name]", "[CBSA].[Name]",
    "[Congressional District].[Name]", "[Area Code].[Name]",
}
_ENCODING_TAGS = ("text", "color", "size", "shape", "detail", "tooltip", "lod", "path")


def _parse_shelves(table_el: ET.Element) -> Dict[str, List[str]]:
    """Extract rows/cols/pages shelves from a table element.
    
    Tableau shelf text contains field references like:
      [federated.xxx].[sum:payment_value:qk] [federated.yyy].[none:customer_state:nk]
    
    We split on the pattern boundary between fields ('] [' or end of string)
    to keep each full field reference intact.
    """
    shelves: Dict[str, List[str]] = {}
    view_el = table_el.find("view")
    for shelf_tag in ("rows", "cols", "pages"):
        shelf_el = table_el.find(shelf_tag)
        if shelf_el is None and view_el is not None:
            shelf_el = view_el.find(shelf_tag)
        if shelf_el is not None and shelf_el.text:
            raw_text = shelf_el.text.strip()
            # Split into complete field references
            # Each field ref is like [datasource].[agg:col:suffix] or [datasource].[col]
            # Multiple fields are space-separated after the closing ]
            fields = re.findall(r'\[[^\]]+\]\.\[[^\]]+\]', raw_text)
            if fields:
                shelves[shelf_tag] = fields
            else:
                # Fallback to original split logic for simple references
                shelves[shelf_tag] = [s.strip() + "]" for s in raw_text.split("]") if s.strip()]
    return shelves


def _parse_pane_encodings(pane: ET.Element) -> Dict[str, Any]:
    """Build an encoding info dict from a single pane element."""
    info: Dict[str, Any] = {}
    for enc in pane.findall("encodings/encoding"):
        enc_attr = enc.get("attr", "")
        if enc_attr:
            info[enc_attr] = enc.get("type", "")
    for enc_tag in _ENCODING_TAGS:
        for enc_el in pane.findall(f"encodings/{enc_tag}"):
            col = enc_el.get("column", "")
            if col:
                info[enc_tag] = col
    return info


def _parse_sorts(ws: ET.Element, table_el: ET.Element) -> List[Dict[str, Any]]:
    """Collect all sort entries (basic, measure-based, manual) for a worksheet."""
    sorts: List[Dict[str, Any]] = []
    for sort in table_el.findall(".//sort"):
        sorts.append({"column": sort.get("column", ""), "direction": sort.get("direction", "")})
    for ss in ws.findall("table/view/shelf-sorts/shelf-sort-v2"):
        sorts.append({
            "column": ss.get("dimension-to-sort", ""),
            "direction": ss.get("direction", ""),
            "sort_type": "measure",
            "measure": ss.get("measure-to-sort-by", ""),
            "shelf": ss.get("shelf", ""),
        })
    for ms in ws.findall("table/view/manual-sort"):
        ordered_values = [
            (b.text or "").strip('"')
            for b in ms.findall("dictionary/bucket")
            if (b.text or "").strip('"')
        ]
        sorts.append({
            "column": ms.get("column", ""),
            "direction": ms.get("direction", ""),
            "sort_type": "manual",
            "ordered_values": ordered_values,
        })
    return sorts


def _parse_style_rules(ws: ET.Element, table_el: Optional[ET.Element]) -> List[Dict[str, str]]:
    """Collect style rules from worksheet/style, table/style, and pane-level rules."""
    rules: List[Dict[str, str]] = []
    for style_el in [ws.find("style"), ws.find("table/style")]:
        if style_el is None:
            continue
        for rule in style_el.findall("style-rule"):
            for fmt in rule.findall("format"):
                rules.append({
                    "element": rule.get("element", ""), "attr": fmt.get("attr", ""),
                    "value": fmt.get("value", ""), "field": fmt.get("field", ""),
                    "scope": fmt.get("scope", ""),
                })
    if table_el is not None:
        for pane in table_el.findall(_ALL_PANES_PATH):
            for rule in pane.findall("style/style-rule"):
                for fmt in rule.findall("format"):
                    rules.append({
                        "element": rule.get("element", ""), "attr": fmt.get("attr", ""),
                        "value": fmt.get("value", ""), "field": fmt.get("field", ""),
                        "scope": "pane",
                    })
    return rules


def _detect_lat_lon(ws: ET.Element) -> bool:
    """Return True if the worksheet uses generated latitude/longitude columns."""
    for dep in ws.findall("table/view/datasource-dependencies"):
        for col_inst in dep.findall("column-instance"):
            if col_inst.get("column", "") in _GEO_LATLON_COLS:
                return True
        for col in dep.findall("column"):
            if col.get("name", "") in _GEO_LATLON_COLS:
                return True
    return False


def _detect_geo_fields(ws: ET.Element) -> bool:
    """Return True if any dependency column has a geographic semantic role."""
    for dep in ws.findall("table/view/datasource-dependencies"):
        for col in dep.findall("column"):
            if col.get("semantic-role", "") in _GEO_ROLES:
                return True
    return False


def _extract_worksheets_structured(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract structured worksheet metadata (no raw XML)."""
    worksheets: List[Dict[str, Any]] = []
    for ws in root.findall(_WORKSHEETS_PATH):
        ws_name = ws.get("name", "")
        sid = ws.find("simple-id")
        ds_deps = [d.get("caption", d.get("name", "")) for d in ws.findall("table/view/datasources/datasource")]
        # Build a parallel list of raw datasource ids (federated.XXX) per worksheet,
        # in the same order as ds_deps. Needed downstream to resolve federated.XXX
        # back to the friendly datasource caption when emitted in fields[].
        ds_dep_ids = [d.get("name", "") for d in ws.findall("table/view/datasources/datasource")]
        table_el = ws.find("table")
        shelves: Dict[str, List[str]] = _parse_shelves(table_el) if table_el is not None else {}
        marks = [{"class": m.get("class", ""), "value": m.get("value", "")} for m in (table_el.findall(".//mark") if table_el is not None else [])]
        panes = [_parse_pane_encodings(p) for p in (table_el.findall(_ALL_PANES_PATH) if table_el is not None else [])]
        sorts = _parse_sorts(ws, table_el) if table_el is not None else []
        slices = [sl.text or "" for sl in ws.findall("table/view/slices/column")]
        if slices:
            shelves["filters"] = slices
        # Extract blending columns from join-lod-include-overrides
        blending_columns = [
            col.text.strip() if col.text else ""
            for col in ws.findall("table/join-lod-include-overrides/column")
            if col.text
        ]
        # Identify the source column for Tableau-generated geo fields
        # (Latitude/Longitude/Geometry "(generated)"). Tableau auto-generates
        # those from the first dimension in this worksheet's
        # <datasource-dependencies> that carries a geographic semantic-role.
        geo_source_column = ""
        geo_source_datasource_id = ""
        for dep in ws.findall("table/view/datasource-dependencies"):
            ds_ref = dep.get("datasource", "")
            for col in dep.findall("column"):
                sr = col.get("semantic-role", "")
                if sr in _GEO_ROLES:
                    geo_source_column = (col.get("name", "") or "").strip("[]")
                    geo_source_datasource_id = ds_ref
                    break
            if geo_source_column:
                break
        worksheets.append({
            "name": ws_name,
            "uuid": sid.get("uuid", "") if sid is not None else "",
            "datasource_dependencies": ds_deps,
            "datasource_dependency_ids": ds_dep_ids,
            "shelves": shelves,
            "marks": marks,
            "panes": panes,
            "sorts": sorts,
            "style_rules": _parse_style_rules(ws, table_el),
            "slices": slices,
            "blending_columns": blending_columns,
            "has_generated_lat_lon": _detect_lat_lon(ws),
            "has_geographic_fields": _detect_geo_fields(ws),
            "geo_source_column": geo_source_column,
            "geo_source_datasource_id": geo_source_datasource_id,
        })
    return worksheets


def _extract_zone_formatted_text(zone: ET.Element) -> Optional[Dict[str, Any]]:
    """Extract formatted text content and styling from a dashboard zone (for textbox visuals)."""
    ft_el = zone.find("formatted-text")
    if ft_el is None:
        return None
    runs = ft_el.findall("run")
    if not runs:
        return None
    text_parts = []
    # Use the first run's attributes for styling
    first_run = runs[0]
    for run in runs:
        text_parts.append(run.text or "")
    content = "".join(text_parts).strip()
    if not content:
        return None
    return {
        "content": content,
        "fontSize": first_run.get("fontsize"),
        "fontColor": first_run.get("fontcolor"),
        "fontAlignment": first_run.get("fontalignment"),
        "fontFamily": first_run.get("fontname"),
        "fontStyle": first_run.get("fontstyle"),
        "fontWeight": first_run.get("fontweight"),
    }


def _parse_zone_style(z: ET.Element) -> Dict[str, str]:
    """Build a style dict from zone-style/format child elements."""
    return {
        fmt.get("attr", ""): fmt.get("value", "")
        for fmt in z.findall("zone-style/format")
        if fmt.get("attr", "")
    }


def _parse_structured_zone(z: ET.Element) -> Optional[Dict[str, Any]]:
    """Parse a single zone element into a structured dict, or None if id is missing."""
    zid = z.get("id", "")
    if not zid:
        return None
    return {
        "id": zid,
        "type": z.get("type-v2", z.get("type", "")),
        "name": z.get("name", ""),
        "param": z.get("param", ""),
        "x": z.get("x", "0"), "y": z.get("y", "0"),
        "w": z.get("w", z.get("width", "0")), "h": z.get("h", z.get("height", "0")),
        "style": _parse_zone_style(z),
        "formatted_text": _extract_zone_formatted_text(z),
        "image_url": z.get("src", z.get("url", "")),
    }


def _collect_dashboard_zones(dash: ET.Element) -> List[Dict[str, Any]]:
    """Collect unique structured zones from a dashboard element."""
    zones: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for z in dash.findall(_ALL_ZONES_PATH):
        zid = z.get("id", "")
        if not zid or zid in seen:
            continue
        seen.add(zid)
        zone = _parse_structured_zone(z)
        if zone is not None:
            zones.append(zone)
    return zones


def _extract_dashboard_zones_structured(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract dashboard zone layout as structured data (no raw XML)."""
    dashboards: List[Dict[str, Any]] = []
    for dash in root.findall("dashboards/dashboard"):
        sid = dash.find("simple-id")
        dash_name = dash.get("name", "")
        title_el = dash.find("layout-options/title/formatted-text/run")
        title = title_el.text.strip() if (title_el is not None and title_el.text) else dash_name
        size_el = dash.find("size")
        # Get explicit dimensions from size element
        width = int(size_el.get("maxwidth", "0") or "0") if size_el is not None else 0
        height = int(size_el.get("maxheight", "0") or "0") if size_el is not None else 0
        # Fallback: try width/height attributes if maxwidth/maxheight are 0
        if width == 0 and size_el is not None:
            width = int(size_el.get("width", "0") or "0")
        if height == 0 and size_el is not None:
            height = int(size_el.get("height", "0") or "0")
        # Check if dashboard uses automatic sizing (Tableau uses 100000-based internal coords)
        sizing_mode = size_el.get("sizing-mode", "") if size_el is not None else ""
        zones = _collect_dashboard_zones(dash)
        # For automatic-sized dashboards or when dimensions are still 0,
        # compute from zones but cap at reasonable pixel values
        if (width == 0 or height == 0 or sizing_mode == "automatic") and zones:
            max_right = 0
            max_bottom = 0
            for z in zones:
                zx = int(z.get("x", "0") or "0")
                zy = int(z.get("y", "0") or "0")
                zw = int(z.get("w", "0") or "0")
                zh = int(z.get("h", "0") or "0")
                max_right = max(max_right, zx + zw)
                max_bottom = max(max_bottom, zy + zh)
            # If coordinates are in Tableau's internal 100000-based system,
            # use a standard default size (automatic dashboards adapt to window)
            if max_right > 10000 or max_bottom > 10000:
                width = 800
                height = 600
            else:
                if width == 0:
                    width = max_right
                if height == 0:
                    height = max_bottom
        dashboards.append({
            "name": title,
            "internal_name": dash_name,
            "uuid": sid.get("uuid", "") if sid is not None else "",
            "width": width,
            "height": height,
            "zones": zones,
        })
    return dashboards


# --- Presentation domain extractors (future agents) ---

def _extract_styles(root: ET.Element) -> Dict[str, Any]:
    """Extract workbook-level preferences and formatting."""
    prefs: List[Dict[str, str]] = []
    for pref in root.findall("preferences/preference"):
        prefs.append({"name": pref.get("name", ""), "value": pref.get("value", "")})
    palettes: List[Dict[str, Any]] = []
    for cp in root.findall("preferences/color-palette"):
        colors = [c.text for c in cp.findall("color") if c.text]
        palettes.append({"name": cp.get("name", ""), "type": cp.get("type", ""), "colors": colors})
    return {"preferences": prefs, "color_palettes": palettes}


def _extract_custom_assets(root: ET.Element) -> Dict[str, Any]:
    """Extract custom shape references, registered resources, and image assets.
    
    Returns a dict with:
      - custom_shapes: list of custom shape file paths used in mark encodings
      - registered_resources: list of embedded resource file names
      - external_images: list of external image URLs referenced in dashboards
    """
    custom_shapes: List[str] = set()
    registered_resources: List[str] = []
    external_images: List[str] = []

    # Extract custom shapes from worksheet mark encodings
    for ws in root.findall("worksheets/worksheet"):
        for enc in ws.findall(".//encoding[@attr='shape']"):
            shape_map = enc.findall("map")
            for m in shape_map:
                shape_val = m.get("to", "")
                if shape_val and "/" in shape_val:
                    custom_shapes.add(shape_val)
        # Also check style-rules for shape references
        for rule in ws.findall(".//style-rule"):
            for fmt in rule.findall("format"):
                if fmt.get("attr") == "shape":
                    val = fmt.get("value", "")
                    if val and "/" in val:
                        custom_shapes.add(val)

    # Extract registered resources (embedded images/files)
    for dash in root.findall("dashboards/dashboard"):
        for zone in dash.findall(".//zone"):
            src = zone.get("src", "")
            if src:
                if src.startswith("http"):
                    external_images.append(src)
                else:
                    registered_resources.append(src)

    # Also check for shape-encoding defaults in datasources
    for ds in root.findall("datasources/datasource"):
        for rule in ds.findall(".//style-rule"):
            for fmt in rule.findall("format"):
                if fmt.get("attr") == "shape":
                    val = fmt.get("value", "")
                    if val and "/" in val:
                        custom_shapes.add(val)

    return {
        "custom_shapes": sorted(custom_shapes),
        "registered_resources": registered_resources,
        "external_images": external_images,
    }


def _extract_thumbnails_info(root: ET.Element) -> Dict[str, Any]:
    """Check for thumbnail presence (no binary data extracted)."""
    thumbs = root.find("thumbnails")
    if thumbs is None:
        return {"present": False, "count": 0}
    count = len(list(thumbs))
    return {"present": count > 0, "count": count}


def _extract_windows_info(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract window/tab layout metadata."""
    windows: List[Dict[str, Any]] = []
    for win in root.findall("windows/window"):
        windows.append({
            "class": win.get("class", ""),
            "name": win.get("name", ""),
            "maximized": win.get("maximized", ""),
            "saved_x": win.get("saved-x", ""),
            "saved_y": win.get("saved-y", ""),
        })
    return windows



# ===================================================================
# NEW VISUALS DOMAIN EXTRACTORS  (Tasks 2.1 – 2.15)
# All functions are pure: ET.Element root → structured dicts.
# No raw XML is returned; no LLM is involved.
# ===================================================================

def _get_title_text(el: ET.Element) -> str:
    """Return stripped text from a title/formatted-text/run child, or empty string."""
    title_el = el.find(_TITLE_TEXT_PATH)
    return title_el.text.strip() if (title_el is not None and title_el.text) else ""


def _collect_dual_axis_titles(panes: List[ET.Element]) -> List[str]:
    """Collect non-empty axis titles from customized-axis and axis elements."""
    titles: List[str] = []
    for pane in panes:
        for ca in pane.findall("customized-axis"):
            titles.append(_get_title_text(ca))
        for ax in pane.findall("axis"):
            title = _get_title_text(ax)
            if title:
                titles.append(title)
    return titles


def _get_row_fields(table_el: ET.Element) -> List[str]:
    """Extract row-shelf fields from the table's view element."""
    view_el = table_el.find("view")
    if view_el is None:
        return []
    rows_el = view_el.find("rows")
    if rows_el is None or not rows_el.text:
        return []
    return [f.strip() for f in rows_el.text.strip().split("]") if f.strip()]


def _is_dual_axis(panes: List[ET.Element], row_fields: List[str]) -> bool:
    """Return True if the worksheet has a dual-axis configuration."""
    if len(row_fields) >= 2:
        return True
    return any(
        p.get("type", "") == "dual" or p.find("axis[@type='dual']") is not None
        for p in panes
    )


def _extract_dual_axis(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract dual-axis (combined axis) configuration per worksheet.

    Tableau marks a dual-axis chart by placing two measures on the Rows or Cols
    shelf and using <axis type='dual'> or <pane><view><rows> with two fields.
    The secondary axis is identified by <axis> elements with ordinal > 0 or
    by <customized-axis> entries on the second pane.

    Returns one entry per worksheet that has a dual-axis configuration:
      worksheet, primary_field, secondary_field,
      primary_axis_title, secondary_axis_title,
      axes_synchronized (bool)
    """
    dual_axes: List[Dict[str, Any]] = []
    for ws in root.findall(_WORKSHEETS_PATH):
        ws_name = ws.get("name", "")
        table_el = ws.find("table")
        if table_el is None:
            continue
        panes = table_el.findall(_ALL_PANES_PATH)
        if len(panes) < 2:
            continue
        row_fields = _get_row_fields(table_el)
        if not _is_dual_axis(panes, row_fields):
            continue
        axis_titles = _collect_dual_axis_titles(panes)
        synchronized = any(
            p.find("axis[@synchronized='true']") is not None or p.get("synchronized", "false") == "true"
            for p in panes
        )
        dual_axes.append({
            "worksheet": ws_name,
            "primary_field": row_fields[0] if row_fields else None,
            "secondary_field": row_fields[1] if len(row_fields) > 1 else None,
            "primary_axis_title": axis_titles[0] if axis_titles else None,
            "secondary_axis_title": axis_titles[1] if len(axis_titles) > 1 else None,
            "axes_synchronized": synchronized,
        })
    return dual_axes


def _parse_trend_line(ws_name: str, tl: ET.Element) -> Dict[str, Any]:
    """Parse a single <trend-line> element into a structured dict."""
    fields = [
        f.get("column", f.text or "")
        for f in tl.findall("field")
        if f.get("column", f.text or "")
    ]
    return {
        "worksheet": ws_name,
        "type": "trend",
        "model_type": tl.get("type", tl.get("model-type", "linear")),
        "fields": fields,
        "confidence_bands": tl.get("show-confidence-bands", "false").lower() == "true",
        "show_recalculated": tl.get("show-recalculated-line", "false").lower() == "true",
        "forecast_periods": None,
        "forecast_granularity": None,
    }


def _parse_forecast(ws_name: str, fc_el: ET.Element) -> Dict[str, Any]:
    """Parse a <forecast> element into a structured dict."""
    opts = fc_el.find("forecast-options")
    confidence = opts.get("show-prediction-intervals", "false").lower() == "true" if opts is not None else False
    return {
        "worksheet": ws_name,
        "type": "forecast",
        "model_type": "exponential_smoothing",
        "fields": [],
        "confidence_bands": confidence,
        "show_recalculated": False,
        "forecast_periods": opts.get("forecast-forward") if opts is not None else None,
        "forecast_granularity": opts.get("forecast-granularity") if opts is not None else None,
    }


def _extract_trend_lines(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract trend line and forecast configuration per worksheet.

    Tableau stores trend lines under:
      worksheets/worksheet/table/panes/pane/trend-lines/trend-line
    Forecast is stored under:
      worksheets/worksheet/table/panes/pane/forecast/forecast-options

    Returns one entry per trend line / forecast:
      worksheet, type (trend|forecast), model_type, fields,
      confidence_bands (bool), show_recalculated (bool),
      forecast_periods, forecast_granularity
    """
    trend_data: List[Dict[str, Any]] = []
    for ws in root.findall(_WORKSHEETS_PATH):
        ws_name = ws.get("name", "")
        for pane in ws.findall(_WS_PANES_PATH):
            for tl in pane.findall("trend-lines/trend-line"):
                trend_data.append(_parse_trend_line(ws_name, tl))
            fc_el = pane.find("forecast")
            if fc_el is not None:
                trend_data.append(_parse_forecast(ws_name, fc_el))
    return trend_data


_WORKSHEETS_PATH = "worksheets/worksheet"
_WS_PANES_PATH = "table/panes/pane"
_TITLE_TEXT_PATH = "title/formatted-text/run"
_ALL_ZONES_PATH = ".//zone"
_ALL_PANES_PATH = ".//pane"

_TABLE_CALC_KEYWORDS = (
    "RUNNING_", "WINDOW_", "RANK", "LOOKUP", "FIRST(", "LAST(",
    "INDEX(", "SIZE(", "PREVIOUS_VALUE", "TOTAL(",
)

_TABLE_CALC_TYPE_MAP: List[Tuple[Tuple[str, ...], str]] = [
    (("RUNNING_SUM",), "running_total"),
    (("RUNNING_AVG",), "running_average"),
    (("WINDOW_SUM", "WINDOW_AVG"), "window_aggregate"),
    (("RANK",), "rank"),
    (("LOOKUP",), "lookup"),
    (("INDEX",), "index"),
    (("SIZE",), "size"),
    (("FIRST", "LAST"), "first_last"),
    (("TOTAL",), "total"),
]


def _infer_table_calc_type(formula_upper: str) -> str:
    """Map a formula (uppercased) to its table calculation type label."""
    for keywords, calc_type in _TABLE_CALC_TYPE_MAP:
        if any(kw in formula_upper for kw in keywords):
            return calc_type
    return "table_calculation"


def _parse_table_calc_column(
    ws_name: str,
    col: ET.Element,
    calc_el: ET.Element,
) -> Dict[str, Any]:
    """Build a table calc entry from a column + its tableau-class calculation element."""
    formula = calc_el.get("formula", "")
    addr_type = calc_el.get("addressing-type", calc_el.get("scope-isolation", ""))
    return {
        "worksheet": ws_name,
        "field_name": col.get("caption", col.get("name", "")).strip("[]"),
        "formula": formula,
        "calc_type": _infer_table_calc_type(formula.upper()),
        "addressing_fields": [f.strip() for f in calc_el.get("addressing-fields", "").split(",") if f.strip()],
        "partitioning_fields": [f.strip() for f in calc_el.get("partitioning-fields", "").split(",") if f.strip()],
        "addressing_type": addr_type or None,
    }


def _extract_table_calc_configs(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract table calculation addressing and partitioning per worksheet.

    Tableau stores table calc configuration inside <column> elements that
    reference a calculation, using <table-calc-spec> or attributes like
    'addressing-fields' and 'partitioning-fields'.

    Also captured from <pane><view><datasource-dependencies> and
    <calculation class='tableau'> with addressing/partitioning attributes.

    Returns one entry per table calc field used in a worksheet:
      worksheet, field_name, calc_type (running_total, percent_of_total,
        rank, difference, moving_average, etc.),
      addressing_fields (list — what the calc computes ACROSS),
      partitioning_fields (list — what the calc restarts FOR),
      addressing_type (table_down, table_across, pane_down, specific, etc.)
    """
    table_calcs: List[Dict[str, Any]] = []
    for ws in root.findall(_WORKSHEETS_PATH):
        ws_name = ws.get("name", "")
        for ds_dep in ws.findall("table/view/datasources/datasource"):
            ds_el = root.find(f"datasources/datasource[@name='{ds_dep.get('name', '')}']")
            if ds_el is None:
                continue
            for col in ds_el.findall("column"):
                calc_el = col.find("calculation[@class='tableau']")
                if calc_el is None:
                    continue
                formula = calc_el.get("formula", "")
                if not any(kw in formula.upper() for kw in _TABLE_CALC_KEYWORDS):
                    continue
                table_calcs.append(_parse_table_calc_column(ws_name, col, calc_el))
    return table_calcs


def _parse_color_encoding(ws_name: str, enc: ET.Element) -> Optional[Dict[str, Any]]:
    """Parse an encoding[@attr='color'] element; returns None if no field or palette."""
    field = enc.get("field", enc.get("column", ""))
    palette = enc.get("palette", "")
    if not field and not palette:
        return None
    steps = enc.get("steps", None)
    range_el = enc.find("range")
    return {
        "worksheet": ws_name,
        "field": field,
        "encoding_type": enc.get("type", "") or ("stepped" if steps else "continuous"),
        "palette_name": palette or None,
        "color_steps": int(steps) if steps else None,
        "min_value": range_el.get("min") if range_el is not None else None,
        "max_value": range_el.get("max") if range_el is not None else None,
        "mid_value": range_el.get("mid") if range_el is not None else None,
        "reversed": enc.get("reversed", "false").lower() == "true",
    }


def _parse_legacy_color_encoding(ws_name: str, ce: ET.Element) -> Optional[Dict[str, Any]]:
    """Parse a <color-encoding> element (older Tableau format); returns None if empty."""
    field = ce.get("field", ce.get("column", ""))
    palette = ce.get("palette", "")
    if not field and not palette:
        return None
    return {
        "worksheet": ws_name,
        "field": field,
        "encoding_type": "color_encoding",
        "palette_name": palette or None,
        "color_steps": None,
        "min_value": None,
        "max_value": None,
        "mid_value": None,
        "reversed": ce.get("reversed", "false").lower() == "true",
    }


def _extract_conditional_formatting(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract conditional formatting (color encoding rules) per worksheet.

    Tableau stores conditional formatting as color encodings driven by
    calculated fields or stepped/diverging color palettes on specific measures.
    These appear as <color-encoding> inside panes, or as <encoding attr='color'>
    with a calculated field that returns a color value.

    Also captures <color-palette> overrides applied to specific worksheets.

    Returns one entry per conditional formatting rule:
      worksheet, field, encoding_type (stepped|diverging|custom|calculated),
      palette_name, color_steps, min_value, max_value, mid_value,
      reversed (bool)
    """
    cf_rules: List[Dict[str, Any]] = []
    for ws in root.findall(_WORKSHEETS_PATH):
        ws_name = ws.get("name", "")
        for pane in ws.findall(_WS_PANES_PATH):
            for enc in pane.findall("encodings/encoding[@attr='color']"):
                entry = _parse_color_encoding(ws_name, enc)
                if entry is not None:
                    cf_rules.append(entry)
            ce = pane.find("color-encoding")
            if ce is not None:
                entry = _parse_legacy_color_encoding(ws_name, ce)
                if entry is not None:
                    cf_rules.append(entry)
    return cf_rules


def _extract_highlight_actions(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract worksheet-level highlight interactions from <windows>.

    Tableau stores highlight definitions under:
      windows/window[@class='worksheet']/viewpoint/highlight/color-one-way/field
    These define which fields trigger highlight behavior when a user clicks a mark.
    """
    highlights: List[Dict[str, Any]] = []
    for win in root.findall("windows/window"):
        if win.get("class", "") != "worksheet":
            continue
        ws_name = win.get("name", "")
        fields: List[str] = []
        for field in win.findall("viewpoint/highlight/color-one-way/field"):
            if field.text:
                fields.append(field.text.strip())
        if fields:
            highlights.append({
                "worksheet": ws_name,
                "highlight_fields": fields,
            })
    return highlights


def _extract_tooltips(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract custom tooltip definitions from each worksheet.

    Tableau stores tooltips under:
      worksheets/worksheet/table/view/tooltip/formatted-text/run
    """
    tooltips: List[Dict[str, Any]] = []
    for ws in root.findall(_WORKSHEETS_PATH):
        ws_name = ws.get("name", "")
        tooltip_el = ws.find("table/view/tooltip")
        if tooltip_el is None:
            continue
        # Collect all <run> text fragments
        runs = tooltip_el.findall(".//run")
        formatted_text = "".join((r.text or "") for r in runs).strip()
        if not formatted_text:
            # Try direct text content
            formatted_text = (tooltip_el.text or "").strip()
        # Extract [FieldName] references from the text
        field_refs = re.findall(r"\[([^\]]+)\]", formatted_text)
        tooltips.append({
            "worksheet": ws_name,
            "formatted_text": formatted_text,
            "field_references": field_refs,
        })
    return tooltips


def _collect_action_sheets(action: ET.Element, child_tag: str, attr_key: str) -> List[str]:
    """Collect sheet names from child elements and a comma-separated attribute."""
    sheets: List[str] = []
    for el in action.findall(child_tag):
        sheet = el.get("sheet", el.text or "")
        if sheet:
            sheets.append(sheet)
    bulk = action.get(attr_key, "")
    if bulk:
        sheets.extend(s.strip() for s in bulk.split(",") if s.strip())
    return sheets


def _parse_dashboard_action(dash_name: str, action: ET.Element) -> Dict[str, Any]:
    """Parse a single dashboard action element into a structured dict.

    Tableau XML structure:
      <action caption='Filter1' name='[Action1_...]'>
        <activation type='on-select' />
        <source dashboard='...' worksheet='...' />
        <command command='tsc:tsl-filter'>
          <param name='exclude' value='...' />
          <param name='target' value='...' />
          <param name='field-captions' value='...' />
        </command>
      </action>
    """
    # Caption is the user-friendly name; fall back to internal name
    caption = action.get("caption", "") or action.get("name", "")

    # Activation is a child element with type attribute
    activation_el = action.find("activation")
    activation = activation_el.get("type", "") if activation_el is not None else ""

    # Source element has dashboard and worksheet attributes
    source_el = action.find("source")
    source_worksheet = source_el.get("worksheet", "") if source_el is not None else ""

    # Command element determines action type
    command_el = action.find("command")
    command_type = command_el.get("command", "") if command_el is not None else ""

    # Infer action type from command
    if "tsl-filter" in command_type:
        action_type = "filter"
    elif "brush" in command_type:
        action_type = "highlight"
    elif "url" in command_type.lower():
        action_type = "url"
    elif "go-to-sheet" in command_type or "navigate" in command_type:
        action_type = "navigation"
    else:
        action_type = command_type or ""

    # Extract params from command
    target_dashboard = ""
    excluded_worksheets: List[str] = []
    field_captions: List[str] = []
    if command_el is not None:
        for param in command_el.findall("param"):
            pname = param.get("name", "")
            pvalue = param.get("value", "")
            if pname == "target":
                target_dashboard = pvalue
            elif pname == "exclude" and pvalue:
                excluded_worksheets.extend(s.strip() for s in pvalue.split(",") if s.strip())
            elif pname == "field-captions" and pvalue:
                field_captions.extend(s.strip() for s in pvalue.split(",") if s.strip())

    # Legacy field mappings (older Tableau versions)
    field_mappings = [
        {
            "source": fm.get("source-field", fm.get("source", "")),
            "target": fm.get("target-field", fm.get("target", "")),
        }
        for fm in action.findall("field-mapping")
    ]

    return {
        "dashboard": dash_name,
        "name": caption,
        "type": action_type,
        "activation": activation or None,
        "source_worksheet": source_worksheet or None,
        "target_dashboard": target_dashboard or None,
        "excluded_worksheets": excluded_worksheets,
        "fields": field_captions,
        "field_mappings": field_mappings,
    }


def _extract_dashboard_actions(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract interactivity actions from each dashboard.

    Tableau stores actions under:
      dashboards/dashboard/actions/action  (dashboard-level)
      actions/action                        (workbook root-level)
    Attributes: name, type (filter/highlight/url/set/go-to-sheet),
    source-sheet, target-sheet, url, field mappings, activation.
    """
    actions: List[Dict[str, Any]] = []
    # Dashboard-level actions
    for dash in root.findall("dashboards/dashboard"):
        dash_name = dash.get("name", "")
        for action in dash.findall("actions/action"):
            actions.append(_parse_dashboard_action(dash_name, action))
    # Workbook root-level actions (common in newer Tableau versions)
    for action in root.findall("actions/action"):
        source = action.find("source")
        dash_name = source.get("dashboard", "") if source is not None else ""
        actions.append(_parse_dashboard_action(dash_name, action))
    return actions


_REFLINE_FORMAT_ATTRS = ("line-style", "color", "thickness", "fill-above", "fill-below")


def _parse_refline_formatting(rl: ET.Element) -> Dict[str, str]:
    """Build a formatting dict from a reference-line element's attributes and child formats."""
    formatting: Dict[str, str] = {
        attr_name: rl.get(attr_name, "")
        for attr_name in _REFLINE_FORMAT_ATTRS
        if rl.get(attr_name, "")
    }
    for fmt in rl.findall("format"):
        attr = fmt.get("attr", "")
        if attr:
            formatting[attr] = fmt.get("value", "")
    return formatting


def _parse_refline(ws_name: str, rl: ET.Element) -> Dict[str, Any]:
    """Parse a single reference-line/refline element into a structured dict."""
    return {
        "worksheet": ws_name,
        "reference_type": rl.get("type", "line"),
        "axis_or_field": rl.get("column", rl.get("field", rl.get("axis", ""))),
        "value": rl.get("value", rl.get("computation", "")),
        "label": rl.get("label", ""),
        "boxplot_whisker_type": rl.get("boxplot-whisker-type", ""),
        "boxplot_mark_exclusion": rl.get("boxplot-mark-exclusion", ""),
        "probability": rl.get("probability", ""),
        "scope": rl.get("scope", ""),
        "symmetric": rl.get("symmetric", ""),
        "z_order": rl.get("z-order", ""),
        "formula": rl.get("formula", ""),
        "formatting": _parse_refline_formatting(rl),
    }


def _extract_reference_lines(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract reference lines, bands, and distributions from worksheet panes.

    Tableau stores these under:
      worksheets/worksheet/table/panes/pane/reference-line   (newer format)
      worksheets/worksheet/table/panes/pane/refline           (older format)
    """
    ref_lines: List[Dict[str, Any]] = []
    for ws in root.findall(_WORKSHEETS_PATH):
        ws_name = ws.get("name", "")
        for pane in ws.findall(_WS_PANES_PATH):
            for rl in list(pane.findall("reference-line")) + list(pane.findall("refline")):
                ref_lines.append(_parse_refline(ws_name, rl))
    return ref_lines


def _axes_from_style_rules(ws_name: str, ws: ET.Element) -> List[Dict[str, Any]]:
    """Collect axis entries from style-rule[@element='axis'] in both style locations."""
    result: List[Dict[str, Any]] = []
    for style_el in [ws.find("style"), ws.find("table/style")]:
        if style_el is None:
            continue
        for rule in style_el.findall("style-rule[@element='axis']"):
            tick_fmt: Dict[str, str] = {}
            title_val = None
            field_val = None
            scope_val = None
            for fmt in rule.findall("format"):
                attr = fmt.get("attr", "")
                val = fmt.get("value", "")
                if attr == "title":
                    title_val = val
                    field_val = fmt.get("field", "")
                    scope_val = fmt.get("scope", "")
                elif attr and val:
                    tick_fmt[attr] = val
            if title_val or tick_fmt:
                result.append({
                    "worksheet": ws_name,
                    "field": field_val or rule.get("scope", ""),
                    "title": title_val,
                    "range_min": None,
                    "range_max": None,
                    "reversed": False,
                    "logarithmic": False,
                    "tick_formatting": tick_fmt,
                    "scope": scope_val,
                })
    return result


def _axes_from_pane_axis_elements(ws_name: str, ws: ET.Element) -> List[Dict[str, Any]]:
    """Collect axis entries from <axis> elements inside panes."""
    result: List[Dict[str, Any]] = []
    for pane in ws.findall(_WS_PANES_PATH):
        for axis in pane.findall("axis"):
            title_el = axis.find(_TITLE_TEXT_PATH)
            title = title_el.text.strip() if (title_el is not None and title_el.text) else None
            range_el = axis.find("range")
            tick_fmt = {
                fmt.get("attr", ""): fmt.get("value", "")
                for fmt in axis.findall("format")
                if fmt.get("attr", "")
            }
            result.append({
                "worksheet": ws_name,
                "field": axis.get("column", axis.get("field", "")),
                "title": title,
                "range_min": range_el.get("min") if range_el is not None else None,
                "range_max": range_el.get("max") if range_el is not None else None,
                "reversed": axis.get("reversed", "false").lower() == "true",
                "logarithmic": axis.get("logarithmic", "false").lower() == "true",
                "tick_formatting": tick_fmt,
            })
    return result


def _axes_from_customized_axis(ws_name: str, ws: ET.Element) -> List[Dict[str, Any]]:
    """Collect axis entries from legacy <customized-axis> elements."""
    result: List[Dict[str, Any]] = []
    for ca in ws.findall("table/panes/pane/customized-axis"):
        range_el = ca.find("range")
        result.append({
            "worksheet": ws_name,
            "field": ca.get("column", ""),
            "title": None,
            "range_min": range_el.get("min") if range_el is not None else None,
            "range_max": range_el.get("max") if range_el is not None else None,
            "reversed": ca.get("reversed", "false").lower() == "true",
            "logarithmic": ca.get("logarithmic", "false").lower() == "true",
            "tick_formatting": {},
        })
    return result


def _extract_axes(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract axis configuration from worksheets.

    Tableau stores axis customization in:
      - <style-rule element='axis'> inside worksheets/worksheet/style
      - <pane><customized-axis> (older format)
      - <axis> elements inside panes
    """
    axes: List[Dict[str, Any]] = []
    for ws in root.findall(_WORKSHEETS_PATH):
        ws_name = ws.get("name", "")
        axes.extend(_axes_from_style_rules(ws_name, ws))
        axes.extend(_axes_from_pane_axis_elements(ws_name, ws))
        axes.extend(_axes_from_customized_axis(ws_name, ws))
    return axes


_LEGEND_ENCODING_TYPES = ("color", "size", "shape", "label", "detail")


def _collect_legend_positions(root: ET.Element) -> Dict[str, str]:
    """Return a map of worksheet-name → legend zone-type from dashboard zones."""
    positions: Dict[str, str] = {}
    for dash in root.findall("dashboards/dashboard"):
        for z in dash.findall(_ALL_ZONES_PATH):
            zone_type = (z.get("type-v2") or z.get("type") or "").lower()
            if "legend" in zone_type:
                positions[z.get("name", "")] = zone_type
    return positions


def _collect_ws_legends(
    ws_name: str,
    ws: ET.Element,
    legend_positions: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Collect legend entries for a single worksheet."""
    result: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for pane in ws.findall(_WS_PANES_PATH):
        for enc in pane.findall("encodings/encoding"):
            enc_type = enc.get("type", enc.get("attr", ""))
            if not enc_type or enc_type in seen:
                continue
            if enc_type.lower() not in _LEGEND_ENCODING_TYPES:
                continue
            seen.add(enc_type)
            result.append({
                "worksheet": ws_name,
                "encoding_type": enc_type,
                "field": enc.get("field", enc.get("column", "")),
                "title": None,
                "position": legend_positions.get(ws_name),
                "visible": True,
            })
    return result


def _extract_legends(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract legend configuration from worksheets.

    Tableau stores legend info in:
      - <encodings/encoding> within panes (encoding type + field)
      - <legend> elements in dashboards (position, visibility)
    """
    legend_positions = _collect_legend_positions(root)
    legends: List[Dict[str, Any]] = []
    for ws in root.findall(_WORKSHEETS_PATH):
        legends.extend(_collect_ws_legends(ws.get("name", ""), ws, legend_positions))
    return legends


def _collect_pane_annotations(ws_name: str, pane: ET.Element) -> List[Dict[str, Any]]:
    """Collect point/mark/area annotations from a single pane."""
    result: List[Dict[str, Any]] = []
    for ann_tag in ("point-annotation", "mark-annotation", "area-annotation"):
        for ann in pane.findall(ann_tag):
            run_el = ann.find("formatted-text/run")
            text = run_el.text.strip() if (run_el is not None and run_el.text) else ""
            result.append({
                "worksheet": ws_name,
                "type": ann_tag.replace("-annotation", ""),
                "text": text,
                "position": {"x": ann.get("x", ""), "y": ann.get("y", "")},
            })
    return result


def _collect_fmt_dict(parent: ET.Element) -> Dict[str, str]:
    """Build an attr→value dict from child <format> elements."""
    return {
        fmt.get("attr", ""): fmt.get("value", "")
        for fmt in parent.findall("format")
        if fmt.get("attr", "")
    }


def _mark_label_from_element(ws_name: str, ml_el: ET.Element) -> Dict[str, Any]:
    """Build a mark-label entry from a <mark-labels> element."""
    show = ml_el.get("show-mark-labels", ml_el.get("enabled", "false")).lower() == "true"
    return {"worksheet": ws_name, "show_mark_labels": show, "formatting": _collect_fmt_dict(ml_el)}


def _mark_label_from_style_rule(ws_name: str, rule: ET.Element) -> Optional[Dict[str, Any]]:
    """Build a mark-label entry from a style-rule, or None if mark-labels-show is not set."""
    formatting = _collect_fmt_dict(rule)
    show = any(
        fmt.get("attr") == "mark-labels-show" and fmt.get("value") == "true"
        for fmt in rule.findall("format")
    )
    if not show:
        return None
    return {"worksheet": ws_name, "show_mark_labels": True, "formatting": formatting}


def _collect_ws_mark_labels(ws_name: str, ws: ET.Element) -> List[Dict[str, Any]]:
    """Collect mark-label entries for a worksheet, preferring <mark-labels> over style rules."""
    result: List[Dict[str, Any]] = []
    found = False
    for pane in ws.findall(_WS_PANES_PATH):
        ml_el = pane.find("mark-labels")
        if ml_el is not None:
            result.append(_mark_label_from_element(ws_name, ml_el))
            found = True
        if not found:
            for rule in pane.findall("style/style-rule[@element='mark']"):
                entry = _mark_label_from_style_rule(ws_name, rule)
                if entry is not None:
                    result.append(entry)
                    found = True
    return result


def _extract_annotations(root: ET.Element) -> Dict[str, List[Dict[str, Any]]]:
    """Extract annotations and mark label configuration from worksheets.

    Returns a dict with two keys:
      - 'annotations': list of annotation dicts (point/mark/area)
      - 'mark_labels': list of mark label config dicts per worksheet
    """
    annotations: List[Dict[str, Any]] = []
    mark_labels: List[Dict[str, Any]] = []

    for ws in root.findall(_WORKSHEETS_PATH):
        ws_name = ws.get("name", "")
        for pane in ws.findall(_WS_PANES_PATH):
            annotations.extend(_collect_pane_annotations(ws_name, pane))
        mark_labels.extend(_collect_ws_mark_labels(ws_name, ws))

    return {"annotations": annotations, "mark_labels": mark_labels}


_FORMAT_ATTRS = ("format", "number-format", "date-format")


def _collect_datasource_format_overrides(root: ET.Element) -> List[Dict[str, Any]]:
    """Collect format overrides from datasource column attributes and child elements."""
    overrides: List[Dict[str, Any]] = []
    for ds in root.findall("datasources/datasource"):
        ds_name = ds.get("caption", ds.get("name", ""))
        for col in ds.findall("column"):
            col_name = col.get("caption", col.get("name", "")).strip("[]")
            fmt_attr = col.get("format", "")
            if fmt_attr:
                overrides.append({"field": col_name, "format_string": fmt_attr, "scope": "datasource", "context": ds_name})
            for fmt_el in col.findall("format"):
                fmt_str = fmt_el.get("format", fmt_el.get("value", ""))
                if fmt_str:
                    overrides.append({"field": col_name, "format_string": fmt_str, "scope": "datasource", "context": ds_name})
    return overrides


def _collect_worksheet_format_overrides(root: ET.Element) -> List[Dict[str, Any]]:
    """Collect format overrides from worksheet style-rule elements."""
    overrides: List[Dict[str, Any]] = []
    for ws in root.findall(_WORKSHEETS_PATH):
        ws_name = ws.get("name", "")
        style_el = ws.find("style")
        if style_el is None:
            continue
        for rule in style_el.findall("style-rule"):
            scope_field = rule.get("element", "")
            for fmt in rule.findall("format"):
                attr = fmt.get("attr", "")
                val = fmt.get("value", "")
                if attr in _FORMAT_ATTRS and val:
                    overrides.append({"field": scope_field, "format_string": val, "scope": "worksheet", "context": ws_name})
    return overrides


def _extract_format_overrides(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract per-field format overrides from datasources and worksheets.

    Tableau stores format overrides in:
      - datasources/datasource/column[@format] or column/format
      - worksheets/worksheet/style/style-rule[@element='cell']/format
    """
    return _collect_datasource_format_overrides(root) + _collect_worksheet_format_overrides(root)


_NON_DATA_ZONE_TYPES = {"text", "bitmap", "image", "web", "blank", "title"}


def _parse_zone_object(dash_name: str, z: ET.Element) -> Optional[Dict[str, Any]]:
    """Parse a single zone into a non-data object dict, or None if not applicable."""
    zid = z.get("id", "")
    if not zid:
        return None
    zone_type = (z.get("type-v2") or z.get("type") or "").lower()
    if zone_type not in _NON_DATA_ZONE_TYPES:
        return None
    run_el = z.find(".//formatted-text/run")
    text_content = run_el.text.strip() if (run_el is not None and run_el.text) else None
    url: Optional[str] = z.get("url") or z.get("param") or None
    return {
        "dashboard": dash_name,
        "zone_id": zid,
        "object_type": zone_type,
        "text_content": text_content,
        "url": url,
        "position": {
            "x": int(z.get("x", "0") or "0"),
            "y": int(z.get("y", "0") or "0"),
            "width": int(z.get("w", z.get("width", "0")) or "0"),
            "height": int(z.get("h", z.get("height", "0")) or "0"),
        },
    }


def _extract_dashboard_objects(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract non-data objects from dashboards (text, image, web, blank zones).

    Tableau stores these as <zone> elements with type-v2 values:
      text, bitmap, web, blank, title
    """
    objects: List[Dict[str, Any]] = []
    for dash in root.findall("dashboards/dashboard"):
        dash_name = dash.get("name", "")
        seen: Set[str] = set()
        for z in dash.findall(_ALL_ZONES_PATH):
            zid = z.get("id", "")
            if not zid or zid in seen:
                continue
            obj = _parse_zone_object(dash_name, z)
            if obj is not None:
                seen.add(zid)
                objects.append(obj)
    return objects


# ===================================================================
# preprocess_workbook helpers  –  extracted to reduce cognitive complexity
# ===================================================================

def _build_and_enrich_worksheets(
    worksheets_base: List[Dict[str, Any]],
    tooltips: List[Dict[str, Any]],
    reference_lines: List[Dict[str, Any]],
    axes: List[Dict[str, Any]],
    legends: List[Dict[str, Any]],
    annotations_data: Dict[str, Any],
    dual_axes: List[Dict[str, Any]],
    trend_lines: List[Dict[str, Any]],
    table_calc_configs: List[Dict[str, Any]],
    conditional_formatting: List[Dict[str, Any]],
    highlight_actions: List[Dict[str, Any]],
) -> None:
    """Build per-worksheet lookup maps and enrich each worksheet entry in-place."""
    _tooltip_map = {t["worksheet"]: t for t in tooltips}
    _refline_map: Dict[str, List] = {}
    for r in reference_lines:
        _refline_map.setdefault(r["worksheet"], []).append(r)
    _axes_map: Dict[str, List] = {}
    for a in axes:
        _axes_map.setdefault(a["worksheet"], []).append(a)
    _legend_map: Dict[str, List] = {}
    for lg in legends:
        _legend_map.setdefault(lg["worksheet"], []).append(lg)
    _ann_map: Dict[str, List] = {}
    for ann in annotations_data["annotations"]:
        _ann_map.setdefault(ann["worksheet"], []).append(ann)
    _ml_map = {ml["worksheet"]: ml for ml in annotations_data["mark_labels"]}
    _dual_map = {d["worksheet"]: d for d in dual_axes}
    _trend_map: Dict[str, List] = {}
    for t in trend_lines:
        _trend_map.setdefault(t["worksheet"], []).append(t)
    _tc_map: Dict[str, List] = {}
    for tc in table_calc_configs:
        _tc_map.setdefault(tc["worksheet"], []).append(tc)
    _cf_map: Dict[str, List] = {}
    for cf in conditional_formatting:
        _cf_map.setdefault(cf["worksheet"], []).append(cf)
    _hl_map: Dict[str, Dict] = {}
    for hl in highlight_actions:
        _hl_map[hl["worksheet"]] = hl

    for ws in worksheets_base:
        ws_name = ws["name"]
        ws["tooltip"] = _tooltip_map.get(ws_name)
        ws["reference_lines"] = _refline_map.get(ws_name, [])
        ws["axes"] = _axes_map.get(ws_name, [])
        ws["legends"] = _legend_map.get(ws_name, [])
        ws["annotations"] = _ann_map.get(ws_name, [])
        ws["mark_labels"] = _ml_map.get(ws_name)
        ws["dual_axis"] = _dual_map.get(ws_name)
        ws["trend_lines"] = _trend_map.get(ws_name, [])
        ws["table_calc_configs"] = _tc_map.get(ws_name, [])
        ws["conditional_formatting"] = _cf_map.get(ws_name, [])
        ws["highlight_fields"] = _hl_map.get(ws_name, {}).get("highlight_fields", [])


def _collect_color_encodings_for_visuals(datasources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Collect color_encodings from datasources and flatten for the visuals agent.

    Returns a list of {datasource, field, color_assignments} entries so the
    Visuals Agent can match them to visuals using the same field as a color encoding.
    """
    result: List[Dict[str, Any]] = []
    for ds in datasources:
        encodings = ds.get("color_encodings")
        if not encodings:
            continue
        ds_name = ds.get("name") or ds.get("caption") or ds.get("internal_name", "")
        for enc in encodings:
            result.append({
                "datasource": ds_name,
                "field": enc.get("field", ""),
                "color_assignments": enc.get("color_assignments", {}),
            })
    return result


def _enrich_dashboards(
    dashboards_base: List[Dict[str, Any]],
    dashboard_actions: List[Dict[str, Any]],
    dashboard_objects: List[Dict[str, Any]],
) -> None:
    """Build action/object lookup maps and enrich each dashboard entry in-place."""
    _action_map: Dict[str, List] = {}
    for act in dashboard_actions:
        _action_map.setdefault(act["dashboard"], []).append(act)
    _obj_map: Dict[str, List] = {}
    for obj in dashboard_objects:
        _obj_map.setdefault(obj["dashboard"], []).append(obj)

    for dash in dashboards_base:
        dash_name = dash["internal_name"]
        dash["actions"] = _action_map.get(dash_name, [])
        dash["dashboard_objects"] = _obj_map.get(dash_name, [])


def _merge_zone_worksheet_data(
    dashboards_base: List[Dict[str, Any]],
    ws_by_name: Dict[str, Dict[str, Any]],
) -> None:
    """Pre-merge worksheet data into matching dashboard zones in-place."""
    # Build a case-insensitive lookup for fallback matching
    ws_by_name_lower: Dict[str, Dict[str, Any]] = {k.lower().strip(): v for k, v in ws_by_name.items()}

    for dash in dashboards_base:
        for zone in dash.get("zones", []):
            zone_name = zone.get("name", "")
            zone_type = zone.get("type", "")
            # Skip filter zones and text zones — they don't have worksheet data
            if not zone_name or "filter" in zone_type.lower() or "text" in zone_type.lower():
                continue

            # Try exact match first, then case-insensitive/trimmed fallback
            matched_ws = ws_by_name.get(zone_name)
            if matched_ws is None:
                matched_ws = ws_by_name_lower.get(zone_name.lower().strip())

            if matched_ws is not None:
                zone["worksheet_data"] = {
                    "shelves": matched_ws.get("shelves", {}),
                    "marks": matched_ws.get("marks", []),
                    "panes": matched_ws.get("panes", []),
                    "sorts": matched_ws.get("sorts", []),
                    "style_rules": matched_ws.get("style_rules", []),
                    "datasource_dependencies": matched_ws.get("datasource_dependencies", []),
                    "tooltip": matched_ws.get("tooltip"),
                    "reference_lines": matched_ws.get("reference_lines", []),
                    "axes": matched_ws.get("axes", []),
                    "legends": matched_ws.get("legends", []),
                    "annotations": matched_ws.get("annotations", []),
                    "mark_labels": matched_ws.get("mark_labels"),
                    "dual_axis": matched_ws.get("dual_axis"),
                    "trend_lines": matched_ws.get("trend_lines", []),
                    "table_calc_configs": matched_ws.get("table_calc_configs", []),
                    "conditional_formatting": matched_ws.get("conditional_formatting", []),
                    "has_generated_lat_lon": matched_ws.get("has_generated_lat_lon", False),
                    "has_geographic_fields": matched_ws.get("has_geographic_fields", False),
                }
            elif zone_type not in ("blank", "bitmap", "paramctrl", "layout-basic"):
                logger.debug("Zone '%s' on dashboard '%s' has no matching worksheet (type=%s)",
                             zone_name, dash.get("name", ""), zone_type)


def _build_column_to_table_map(tables: List[Dict[str, Any]], calculations: List[Dict[str, Any]] = None) -> Dict[str, str]:
    """Build a mapping from column names to their source table names (clean, no extensions).
    
    Maps both raw table names (tbl_sales.csv) and clean names (tbl_sales) to columns
    so that Tableau's internal references can be resolved to clean output names.
    """
    column_to_table: Dict[str, str] = {}
    
    for tbl in tables:
        tbl_name = tbl.get("table_name", "")  # Already clean (no extension)
        if not tbl_name:
            continue
            
        for col in tbl.get("columns", []):
            col_name = col.get("name", "")
            if col_name:
                # All lookups resolve to the CLEAN table name
                column_to_table[col_name] = tbl_name
                column_to_table[col_name.lower()] = tbl_name
                column_to_table[col_name.strip("[]")] = tbl_name
                column_to_table[col_name.strip("[]").lower()] = tbl_name
    
    # Map calculation internal names to the table containing their dependencies
    if calculations:
        for calc in calculations:
            internal_name = calc.get("internal_name", "").strip("[]")
            depends_on = calc.get("depends_on", [])
            if internal_name and depends_on:
                for dep_col in depends_on:
                    dep_table = column_to_table.get(dep_col) or column_to_table.get(dep_col.lower())
                    if dep_table:
                        column_to_table[internal_name] = dep_table
                        column_to_table[internal_name.lower()] = dep_table
                        break
    
    return column_to_table


def _resolve_field_reference(field_ref: str, column_to_table: Dict[str, str], calc_id_to_caption: Dict[str, str] = None) -> str:
    """Resolve a Tableau field reference to use table name instead of datasource ID.
    
    Input format: [federated.04qgojw08er54u1635fpg1xwsnpw].[sum:payment_value:qk]
    Output format: [df_Payments.csv].[sum:payment_value:qk]
    
    Also replaces internal calculation IDs with friendly caption names:
    Input: [tbl_products.csv].[none:Calculation_1786943919561031710:nk]
    Output: [tbl_products.csv].[none:Product Description:nk]
    
    If the column cannot be resolved, returns the original reference unchanged.
    """
    # Pattern to match [datasource_id].[aggregation:column_name:suffix] or [datasource_id].[column_name]
    # Examples:
    #   [federated.xxx].[sum:payment_value:qk]
    #   [federated.xxx].[none:customer_state:nk]
    #   [federated.xxx].[tmn:order_purchase_timestamp:qk]
    pattern = r'\[([^\]]+)\]\.\[([^\]]+)\]'
    match = re.match(pattern, field_ref)
    
    if not match:
        return field_ref
    
    datasource_id = match.group(1)
    column_part = match.group(2)
    
    # Extract the actual column name from the column_part
    # Format is typically: aggregation:column_name:suffix or just column_name
    # Examples: sum:payment_value:qk, none:customer_state:nk, payment_value
    # Complex: pcto:sum:Calculation_XXX:qk (table calc wrapping another calc)
    if ':' in column_part:
        parts = column_part.split(':')
        if len(parts) >= 2:
            column_name = parts[1]  # The middle part is the column name
            # For compound references like pcto:sum:Calculation_XXX:qk,
            # the actual column/calc name is at position 2
            if len(parts) >= 4 and parts[1] in ("sum", "avg", "cnt", "cntd", "min", "max", "med"):
                column_name = parts[2]
        else:
            column_name = parts[0]
    else:
        column_name = column_part
    
    # Replace internal calc IDs with friendly caption names
    resolved_column_part = column_part
    if calc_id_to_caption and column_name.startswith("Calculation_"):
        caption = calc_id_to_caption.get(column_name) or calc_id_to_caption.get(column_name.lower())
        if caption:
            # Replace the calc ID in the column_part with the caption
            resolved_column_part = column_part.replace(column_name, caption)
            column_name = caption  # Update for table lookup too
    
    # Look up the table name for this column
    table_name = column_to_table.get(column_name) or column_to_table.get(column_name.lower())
    
    if table_name:
        # Replace datasource ID with clean table name
        return f"[{_clean_table_name(table_name)}].[{resolved_column_part}]"
    
    # If table not found but we resolved the calc ID, still return with cleaned name
    if resolved_column_part != column_part:
        cleaned_ds = _clean_table_name(datasource_id)
        return f"[{cleaned_ds}].[{resolved_column_part}]"
    
    # If we can't resolve, clean the table part if it has UUID suffix or extension
    cleaned_ds = _clean_table_name(datasource_id)
    if cleaned_ds != datasource_id:
        return f"[{cleaned_ds}].[{resolved_column_part}]"
    
    return field_ref


def _resolve_shelf_references(shelves: Dict[str, List[str]], column_to_table: Dict[str, str], calc_id_to_caption: Dict[str, str] = None) -> Dict[str, List[str]]:
    """Resolve all field references in shelves to use table names instead of datasource IDs."""
    resolved_shelves: Dict[str, List[str]] = {}
    
    for shelf_name, fields in shelves.items():
        resolved_fields = []
        for field in fields:
            resolved = _resolve_field_reference(field, column_to_table, calc_id_to_caption)
            resolved_fields.append(resolved)
        resolved_shelves[shelf_name] = resolved_fields
    
    return resolved_shelves


def _resolve_encoding_references(panes: List[Dict[str, Any]], column_to_table: Dict[str, str], calc_id_to_caption: Dict[str, str] = None) -> List[Dict[str, Any]]:
    """Resolve field references in pane encodings to use table names."""
    resolved_panes = []
    
    for pane in panes:
        resolved_pane = {}
        for key, value in pane.items():
            if isinstance(value, str) and "[" in value and "].[" in value:
                # This is a field reference like [datasource].[column]
                resolved_pane[key] = _resolve_field_reference(value, column_to_table, calc_id_to_caption)
            else:
                resolved_pane[key] = value
        resolved_panes.append(resolved_pane)
    
    return resolved_panes


# ===================================================================
# preprocess_workbook  -  the single entry point
# ===================================================================

def preprocess_workbook(xml: bytes) -> TableauWorkbookContext:
    """
    Parse a Tableau .twb or .twbx file and return a TableauWorkbookContext
    containing all extracted metadata organized by domain.

    Accepts both plain .twb XML bytes and .twbx ZIP archives.
    For .twbx files the inner .twb is extracted automatically; all other
    bundled assets (data extracts, images) are ignored.

    This is the SINGLE SOURCE OF TRUTH for all downstream agents.
    No raw XML leaves this function.
    """
    # Transparently handle .twbx (ZIP) — extracts inner .twb XML if needed
    xml = _extract_twb_from_twbx(xml)
    root = _root(xml)
    logger.info("[Tableau] Starting comprehensive workbook preprocessing")

    # --- Model domain (Agent 1) ---
    model: Dict[str, Any] = {
        "datasources": _extract_datasources_comprehensive(root),
        "tables": _extract_tables_comprehensive(root),
        "joins_and_relationships": _extract_joins_and_relationships(root),
        "calculations": _extract_calculations_comprehensive(root),
        "parameters": _extract_parameters_comprehensive(root),
        "hierarchies": parse_hierarchies(root),
        "filters": _extract_filters_comprehensive(root),
        "groups_and_sets": _extract_groups_and_sets(root),
        "column_aliases": _extract_column_aliases(root),
        "measure_names_aliases": _extract_measure_names_aliases(root),
        "semantic_roles": extract_semantic_roles(root),
        "metadata_records": _extract_metadata_records(root),
        "extract_info": _extract_extract_info(root),
        "custom_sql": _extract_custom_sql(root),
        "security": _extract_security(root),
    }

    # --- Visuals domain (Agent 2) ---
    # Build column-to-table mapping for resolving field references
    column_to_table = _build_column_to_table_map(model["tables"], model["calculations"])
    logger.info("[Tableau] Built column-to-table mapping with %d entries", len(column_to_table))

    # Build calc internal_name → caption mapping for friendly-name resolution in visuals
    # This maps e.g. "Calculation_1786943919561031710" → "Product Description"
    calc_id_to_caption: Dict[str, str] = {}
    for calc in model["calculations"]:
        internal = calc.get("internal_name", "").strip("[]")
        caption = calc.get("caption", "")
        if internal and caption and internal != caption:
            calc_id_to_caption[internal] = caption
            calc_id_to_caption[internal.lower()] = caption
    logger.info("[Tableau] Built calc-id-to-caption mapping with %d entries", len(calc_id_to_caption) // 2)

    # Resolve internal calculation IDs in formulas BEFORE sending to the LLM
    # This ensures the extraction agent sees clean formulas with friendly names
    if calc_id_to_caption:
        _resolved_formula_count = 0
        for calc in model["calculations"]:
            formula = calc.get("formula", "")
            if formula and "Calculation_" in formula:
                resolved = formula
                for internal_id, caption in calc_id_to_caption.items():
                    if internal_id.startswith("Calculation_") and internal_id in resolved:
                        resolved = resolved.replace(f"[{internal_id}]", f"[{caption}]")
                if resolved != formula:
                    calc["formula"] = resolved
                    _resolved_formula_count += 1
            # Also resolve depends_on references
            depends_on = calc.get("depends_on", [])
            if depends_on:
                calc["depends_on"] = [
                    calc_id_to_caption.get(dep.strip("[]"), dep)
                    if dep.strip("[]").startswith("Calculation_") else dep
                    for dep in depends_on
                ]
        if _resolved_formula_count:
            logger.info("[Tableau] Resolved internal IDs in %d calculation formula(s) during preprocessing", _resolved_formula_count)

    # Step 1: base worksheet and dashboard structures
    worksheets_base = _extract_worksheets_structured(root)
    
    # Step 1.5: Resolve field references in worksheets to use table names instead of datasource IDs
    for ws in worksheets_base:
        if "shelves" in ws:
            ws["shelves"] = _resolve_shelf_references(ws["shelves"], column_to_table, calc_id_to_caption)
        if "panes" in ws:
            ws["panes"] = _resolve_encoding_references(ws["panes"], column_to_table, calc_id_to_caption)
        if "slices" in ws and ws["slices"]:
            ws["slices"] = [_resolve_field_reference(s, column_to_table, calc_id_to_caption) if "[" in s and "].[" in s else s for s in ws["slices"]]
        if "blending_columns" in ws and ws["blending_columns"]:
            ws["blending_columns"] = [_resolve_field_reference(b, column_to_table, calc_id_to_caption) if "[" in b and "].[" in b else b for b in ws["blending_columns"]]

    # Step 1.5b: Collect blending info and add to model domain for the extraction agent
    blending_links: List[Dict[str, Any]] = []
    for ws in worksheets_base:
        if ws.get("blending_columns") and len(ws.get("datasource_dependencies", [])) > 1:
            blending_links.append({
                "worksheet": ws["name"],
                "datasources": ws["datasource_dependencies"],
                "blending_columns": ws["blending_columns"],
            })
    if blending_links:
        model["blending_links"] = blending_links
        logger.info("[Tableau] Found %d worksheet(s) with data blending", len(blending_links))

    dashboards_base = _extract_dashboard_zones_structured(root)

    # Step 1.6: Resolve field references in dashboard zone params (for filter/slicer zones)
    for dash in dashboards_base:
        for zone in dash.get("zones", []):
            param = zone.get("param", "")
            if param and "[" in param and "].[" in param:
                zone["param"] = _resolve_field_reference(param, column_to_table, calc_id_to_caption)

    # Step 2: run all new extraction functions
    tooltips = _extract_tooltips(root)
    dashboard_actions = _extract_dashboard_actions(root)
    reference_lines = _extract_reference_lines(root)
    axes = _extract_axes(root)
    legends = _extract_legends(root)
    annotations_data = _extract_annotations(root)
    format_overrides = _extract_format_overrides(root)
    dashboard_objects = _extract_dashboard_objects(root)
    dual_axes = _extract_dual_axis(root)
    trend_lines = _extract_trend_lines(root)
    table_calc_configs = _extract_table_calc_configs(root)
    conditional_formatting = _extract_conditional_formatting(root)
    highlight_actions = _extract_highlight_actions(root)

    # Step 3: enrich each worksheet entry
    _build_and_enrich_worksheets(
        worksheets_base, tooltips, reference_lines, axes, legends,
        annotations_data, dual_axes, trend_lines, table_calc_configs,
        conditional_formatting, highlight_actions,
    )

    # Step 3.5: Enrich worksheets with datasource-level color assignments
    # Match color_encodings from datasources to worksheets that use those fields as color encodings
    ds_color_encodings = _collect_color_encodings_for_visuals(model["datasources"])
    if ds_color_encodings:
        # Build a lookup: column_name -> color_assignments
        _color_field_map: Dict[str, Dict[str, str]] = {}
        for ce in ds_color_encodings:
            field_ref = ce.get("field", "")
            # Extract column name from field reference like [none:product_category_name:nk]
            col_name = field_ref
            if ":" in field_ref:
                parts = field_ref.strip("[]").split(":")
                if len(parts) >= 2:
                    col_name = parts[1]
            if col_name and ce.get("color_assignments"):
                _color_field_map[col_name] = ce["color_assignments"]
                _color_field_map[col_name.lower()] = ce["color_assignments"]

        for ws in worksheets_base:
            # Check if any pane has a color encoding that matches
            for pane in ws.get("panes", []):
                color_field = pane.get("color", "")
                if not color_field:
                    continue
                # Extract column name from the resolved reference like [df_Products.csv].[none:product_category_name:nk]
                col_name_from_pane = color_field
                if "].[" in color_field:
                    col_part = color_field.split("].[")[-1].rstrip("]")
                    if ":" in col_part:
                        parts = col_part.split(":")
                        if len(parts) >= 2:
                            col_name_from_pane = parts[1]
                    else:
                        col_name_from_pane = col_part
                # Look up color assignments for this column
                assignments = _color_field_map.get(col_name_from_pane) or _color_field_map.get(col_name_from_pane.lower())
                if assignments:
                    ws["conditional_formatting"].append({
                        "worksheet": ws["name"],
                        "field": color_field,
                        "encoding_type": "categorical",
                        "palette_name": None,
                        "color_assignments": assignments,
                        "color_steps": None,
                        "min_value": None,
                        "max_value": None,
                        "mid_value": None,
                        "reversed": False,
                    })

    # Step 4: enrich each dashboard entry
    _enrich_dashboards(dashboards_base, dashboard_actions, dashboard_objects)

    # Step 4.5: Resolve internal calc IDs in color_assignments keys and
    # datasource_color_encodings for the visuals agent
    if calc_id_to_caption:
        # Resolve in worksheet conditional_formatting color_assignments
        for ws in worksheets_base:
            for cf in ws.get("conditional_formatting", []):
                assignments = cf.get("color_assignments")
                if not assignments:
                    continue
                resolved_assignments = {}
                for key, color in assignments.items():
                    resolved_key = key
                    for internal_id, caption in calc_id_to_caption.items():
                        if internal_id.startswith("Calculation_") and internal_id in resolved_key:
                            resolved_key = resolved_key.replace(internal_id, caption)
                    resolved_assignments[resolved_key] = color
                cf["color_assignments"] = resolved_assignments

    visuals: Dict[str, Any] = {
        "worksheets": worksheets_base,
        "dashboards": dashboards_base,
        "sheets": parse_sheets(root),
        "dashboard_filters": parse_filters(root),
        "format_overrides": format_overrides,
        "datasource_color_encodings": _collect_color_encodings_for_visuals(model["datasources"]),
    }

    # Resolve internal calc IDs in datasource_color_encodings for the visuals agent
    if calc_id_to_caption:
        for ce in visuals.get("datasource_color_encodings", []):
            assignments = ce.get("color_assignments")
            if not assignments:
                continue
            resolved_assignments = {}
            for key, color in assignments.items():
                resolved_key = key
                for internal_id, caption in calc_id_to_caption.items():
                    if internal_id.startswith("Calculation_") and internal_id in resolved_key:
                        resolved_key = resolved_key.replace(internal_id, caption)
                resolved_assignments[resolved_key] = color
            ce["color_assignments"] = resolved_assignments

    # Step 5: Pre-merge each dashboard zone with its matching worksheet data
    # so the visuals agent doesn't have to match them (prevents worksheet mix-ups).
    ws_by_name: Dict[str, Dict[str, Any]] = {ws["name"]: ws for ws in worksheets_base}
    _merge_zone_worksheet_data(dashboards_base, ws_by_name)
    logger.info("[Tableau] Pre-merged worksheet data into %d dashboard zones",
                sum(1 for d in dashboards_base for z in d.get("zones", []) if "worksheet_data" in z))

    # --- Presentation domain (future agents) ---
    presentation: Dict[str, Any] = {
        "styles": _extract_styles(root),
        "thumbnails": _extract_thumbnails_info(root),
        "windows": _extract_windows_info(root),
        "custom_assets": _extract_custom_assets(root),
    }

    ctx = TableauWorkbookContext(model=model, visuals=visuals, presentation=presentation)

    logger.info(
        "[Tableau] Preprocessing complete: datasources=%d tables=%d relationships=%d "
        "calculations=%d parameters=%d hierarchies=%d filters=%d worksheets=%d dashboards=%d",
        len(model["datasources"]),
        len(model["tables"]),
        len(model["joins_and_relationships"]),
        len(model["calculations"]),
        len(model["parameters"]),
        len(model["hierarchies"]),
        len(model["filters"]),
        len(visuals["worksheets"]),
        len(visuals["dashboards"]),
    )
    return ctx
