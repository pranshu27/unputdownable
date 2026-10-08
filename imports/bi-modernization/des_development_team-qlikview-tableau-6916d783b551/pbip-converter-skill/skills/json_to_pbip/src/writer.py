"""
writer.py — Read mapped.json and write the complete .pbip folder structure to disk.

Generates the modern PBIP format matching Power BI Desktop export:
  - Name.Report/  (with definition/ subfolder, .platform)
  - Name.SemanticModel/  (TMDL format, .platform)

Data sources:
  Source CSVs are loaded from a shared SharePoint folder (see _SHAREPOINT_SITE)
  so every team member who opens the generated PBIP can refresh the data with
  their own org account — no local `sources/` copy is required.
"""
import json, os, re, uuid, argparse, shutil, copy

try:
    from skills.json_to_pbip.src import debug_collector as _dbg
except ImportError:
    _dbg = None

# Style / colour translation layer (camelCase RE contract → PBIP objects).
# Import is tolerant of both package-relative and flat layouts so the writer
# keeps working in every entrypoint (CLI, Streamlit, server).
try:
    from skills.json_to_pbip.src import styles as _styles
except ImportError:  # pragma: no cover - fallback for flat sys.path
    try:
        import styles as _styles
    except ImportError:
        _styles = None

# Path to bundled theme assets (relative to this file)
_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "assets")

# ── Local CSV sources ──────────────────────────────────────────────────────────
_SOURCES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "sources")
)


_TABLE_EXT_RE = re.compile(r'\.(csv|xlsx|xls|parquet|json|tsv|txt)$', re.IGNORECASE)


def _strip_table_ext(name: str) -> str:
    """Strip data-file extensions from table names so TMDL identifiers are clean.
    'df_OrderItems.csv' → 'df_OrderItems'. The CSV file path in the M query is unaffected.
    """
    return _TABLE_EXT_RE.sub('', name) if name else name


def _clean_mapped_table_names(mapped: dict) -> None:
    """Strip data-file extensions from every table name reference in the mapped dict (in-place).
    Covers: table names, relationship from/to, visual field tables, measure DAX expressions.
    """
    rename = {}
    for t in mapped.get("tables", []):
        clean = _strip_table_ext(t["name"])
        if clean != t["name"]:
            rename[t["name"]] = clean

    if not rename:
        return

    for t in mapped.get("tables", []):
        t["name"] = rename.get(t["name"], t["name"])
        for m in t.get("measures", []):
            expr = m.get("expression", "")
            for orig, clean in rename.items():
                expr = expr.replace(f"'{orig}'", f"'{clean}'")
            m["expression"] = expr

    for r in mapped.get("relationships", []):
        r["fromTable"] = rename.get(r.get("fromTable", ""), r.get("fromTable", ""))
        r["toTable"]   = rename.get(r.get("toTable", ""),   r.get("toTable", ""))

    for page in mapped.get("pages", []):
        for visual in page.get("visuals", []):
            for field in visual.get("fields", []):
                if field.get("table") in rename:
                    field["table"] = rename[field["table"]]


def _norm_stem(s: str) -> str:
    s = re.sub(r"\s+\d+$", "", s)
    # Strip separators/punctuation but KEEP letters and digits of any script
    # (\w is Unicode-aware) so a Japanese table name still matches its CSV.
    # `[^a-z0-9]` previously erased every non-ASCII character, which made
    # CSV lookup impossible for non-Latin table names.
    return re.sub(r"[\W_]", "", s.lower())


def _build_csv_map() -> dict:
    result = {}
    if not os.path.isdir(_SOURCES_DIR):
        return result
    for fname in os.listdir(_SOURCES_DIR):
        if fname.lower().endswith(".csv"):
            stem = os.path.splitext(fname)[0]
            result[_norm_stem(stem)] = os.path.join(_SOURCES_DIR, fname)
    return result

_CSV_MAP = _build_csv_map()


def _refresh_csv_map():
    """Rebuild the in-memory CSV index — call after creating new CSV files at runtime."""
    global _CSV_MAP
    _CSV_MAP = _build_csv_map()


def _find_csv_file(table_name: str) -> str | None:
    stem = re.sub(r"\.(csv|twb|xlsx|parquet)$", "", table_name, flags=re.IGNORECASE)
    return _CSV_MAP.get(_norm_stem(stem))


_ONE_SIDE_DUP_CACHE: dict[tuple[str, str], bool] = {}


def _one_side_has_duplicates(table_name: str, column_name: str) -> bool:
    """Return True iff the local CSV for `table_name` has duplicate non-empty
    values in `column_name`. Used to validate the "one" side of an M:1
    relationship before TMDL emission. PBI enforces uniqueness on the one
    side at load time; if the underlying data violates it, the model refuses
    to load with `Column 'X' contains a duplicate value 'Y' and this is not
    allowed for columns on the one side of a many-to-one relationship`. The
    RE's declared cardinality can disagree with the actual data — when it
    does, we downgrade to many_to_many so the model still loads (the user
    can then tighten cardinality in Desktop once dupes are reconciled).

    Returns False when the CSV is unavailable (calc tables, missing source
    file) — those cases fall through to the RE's declared cardinality.
    """
    key = (table_name, column_name)
    if key in _ONE_SIDE_DUP_CACHE:
        return _ONE_SIDE_DUP_CACHE[key]
    csv_path = _find_csv_file(table_name)
    if not csv_path or not os.path.isfile(csv_path):
        _ONE_SIDE_DUP_CACHE[key] = False
        return False
    try:
        import csv as _csv
        with open(_long(csv_path), "r", encoding="utf-8-sig", newline="") as f:
            reader = _csv.reader(f)
            try:
                header = next(reader)
            except StopIteration:
                _ONE_SIDE_DUP_CACHE[key] = False
                return False
            try:
                idx = header.index(column_name)
            except ValueError:
                # Column name mismatch (case / whitespace / not in CSV) —
                # can't verify; trust the declared cardinality.
                _ONE_SIDE_DUP_CACHE[key] = False
                return False
            seen: set = set()
            has_dup = False
            for row in reader:
                if idx >= len(row):
                    continue
                v = row[idx]
                if v == "" or v is None:
                    continue
                if v in seen:
                    has_dup = True
                    break
                seen.add(v)
    except (OSError, UnicodeDecodeError):
        _ONE_SIDE_DUP_CACHE[key] = False
        return False
    _ONE_SIDE_DUP_CACHE[key] = has_dup
    return has_dup


_M_TYPE_MAP = {
    "string":   "type text",
    "int64":    "Int64.Type",
    "integer":  "Int64.Type",
    "decimal":  "type number",
    "number":   "type number",
    "double":   "type number",
    "float":    "type number",
    "datetime": "type datetime",
    "date":     "type date",
    "time":     "type time",
    "boolean":  "type logical",
}


# ── Cloud CSV source ────────────────────────────────────────────────────────────
# Source CSVs live in a shared cloud folder (SharePoint, OneDrive for Business,
# any HTTP(S)-accessible folder/URL) so anyone who opens the generated PBIP can
# refresh the data with their own credentials.
#
# Connector chosen by URL shape:
#   * SharePoint / OneDrive-for-Business SITE url
#     (matches `.sharepoint.com/sites/…`, `/personal/…`, `/teams/…`)
#       → SharePoint.Files(<site>) — enumerates every file in the site,
#         then `[Name="<filename>"]` picks the CSV.
#   * Anything else (generic web folder, OneDrive shared link, blob with SAS,
#     a public CSV host, etc.)
#       → Web.Contents(<base>, [RelativePath="<filename>"])
#         — direct fetch; the base URL is treated as a folder and each table
#         loads from <base>/<csv_name>.
#
# Both forms map a single base URL to per-table M. Override per-call via
# `set_data_source_url(url)` (process-level — reset in a try/finally when
# called from a multi-request server, otherwise URL leaks between requests).
_DATA_SOURCE_URL_DEFAULT = "https://dataeconomy.sharepoint.com/sites/DeliveryGovernance-JnJ"
_DATA_SOURCE_URL = _DATA_SOURCE_URL_DEFAULT


def set_data_source_url(url: str | None) -> None:
    """Override the cloud CSV folder URL used by `_csv_m_query` for the next
    `write_pbip()` call. Pass None / empty to reset to the default."""
    global _DATA_SOURCE_URL
    _DATA_SOURCE_URL = (url or "").strip() or _DATA_SOURCE_URL_DEFAULT


# True ONLY for a SharePoint / OneDrive-for-Business site root, e.g.
#   https://x.sharepoint.com/sites/Foo
#   https://x-my.sharepoint.com/personal/user_tenant_com
# A URL with a subfolder (Shared%20Documents/.../CSVFiles) goes through the
# Web.Contents branch instead — SharePoint.Files only takes a site root and
# enumerates from there, whereas big sites + nested folders frequently come
# back empty, producing the "key didn't match any rows" error at refresh.
_SHAREPOINT_SITE_ROOT_RE = re.compile(
    r"^https?://[^/]+\.sharepoint\.com/(?:sites|personal|teams)/[^/]+/?$",
    re.IGNORECASE,
)


def _is_sharepoint_site_root(url: str) -> bool:
    """True iff URL is the SharePoint / OneDrive-for-Business site root only
    (no subfolders). SharePoint.Files() handles that case."""
    return bool(_SHAREPOINT_SITE_ROOT_RE.match((url or "").strip()))


def _is_sharepoint_url(url: str) -> bool:
    """True if URL is any SharePoint / OneDrive-for-Business URL (site root
    OR a path within it). Used to route to SharePoint.Contents+navigation
    instead of Web.Contents, which Power BI's data-source firewall blocks
    on credential-required SharePoint URLs."""
    from urllib.parse import urlparse
    host = urlparse((url or "").strip()).netloc.lower()
    return host.endswith(".sharepoint.com")


def _split_sharepoint_url(url: str):
    """Return (site_url, [folder_path_components]) for a SharePoint URL.
    Path components are URL-decoded so they match the names SharePoint.Contents
    reports back (human-readable, not %-escaped)."""
    from urllib.parse import urlparse, unquote
    p = urlparse(url.strip())
    parts = [unquote(x) for x in p.path.strip("/").split("/") if x]
    if len(parts) < 2 or parts[0].lower() not in ("sites", "personal", "teams"):
        return url.rstrip("/"), []
    site_url = f"{p.scheme}://{p.netloc}/{parts[0]}/{parts[1]}"
    return site_url, parts[2:]


def _csv_m_query(csv_path: str, columns: list = None) -> str:
    """Build the Power Query (M) for a table, loading its CSV from the shared
    cloud folder set in `_DATA_SOURCE_URL`. `csv_path` may be a full local
    path or a bare table name — only the file name matters."""
    csv_name = os.path.basename(csv_path)
    if not _TABLE_EXT_RE.search(csv_name):
        csv_name += ".csv"
    name_lit = csv_name.replace('"', '""')
    url      = _DATA_SOURCE_URL

    if _is_sharepoint_site_root(url):
        # Site root only — SharePoint.Files enumerates every file in the site.
        site_lit = url.rstrip("/").replace('"', '""')
        lines = [
            "let",
            f'    Source = SharePoint.Files("{site_lit}", [ApiVersion = 15]),',
            f'    CsvFile = Source{{[Name="{name_lit}"]}}[Content],',
            '    Csv = Csv.Document(CsvFile, [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.None]),',
            "    PromotedHeaders = Table.PromoteHeaders(Csv, [PromoteAllScalars=true])",
        ]
    elif _is_sharepoint_url(url):
        # SharePoint / OneDrive-for-Business subfolder URL.
        # Use SharePoint.Contents + step-by-step folder navigation — this is
        # the canonical pattern (what Power BI Desktop's GUI emits when you
        # connect via "From SharePoint folder") and the only one whose
        # credentials flow through cleanly. Web.Contents to credential-
        # required SharePoint URLs is blocked by Power BI's data source
        # firewall and produces "credentials required" errors.
        site_url, folder_parts = _split_sharepoint_url(url)
        site_lit = site_url.replace('"', '""')
        lines = [
            "let",
            f'    Source = SharePoint.Contents("{site_lit}", [ApiVersion = 15]),',
        ]
        prev = "Source"
        for idx, comp in enumerate(folder_parts, start=1):
            step = f"F{idx}"
            comp_lit = comp.replace('"', '""')
            lines.append(f'    {step} = {prev}{{[Name="{comp_lit}"]}}[Content],')
            prev = step
        lines.append(f'    CsvFile = {prev}{{[Name="{name_lit}"]}}[Content],')
        lines.append('    Csv = Csv.Document(CsvFile, [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.None]),')
        lines.append("    PromotedHeaders = Table.PromoteHeaders(Csv, [PromoteAllScalars=true])")
    else:
        # Non-SharePoint cloud folder — public web folder, OneDrive
        # Personal shared folder, Azure Blob with SAS, etc.
        # Web.Contents fetches each file directly at `<url>/<filename>`.
        base_lit = url.rstrip("/").replace('"', '""')
        lines = [
            "let",
            "    Csv = Csv.Document(",
            f'        Web.Contents("{base_lit}", [RelativePath = "{name_lit}"]),',
            '        [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.None]),',
            "    PromotedHeaders = Table.PromoteHeaders(Csv, [PromoteAllScalars=true])",
        ]
    if columns:
        # Names of DAX-calculated columns declared on this table. The TMDL
        # emits each as `column X = <expr>`; the engine would then duplicate
        # the name if the partition ALSO surfaces a physical column named X
        # (e.g. dim_date declares `Month = MONTH(date)` and the source CSV
        # happens to have a `Month` header). Drop these defensively from
        # the partition output with MissingField.Ignore so the step is a
        # safe no-op when the source file doesn't carry the colliding name.
        calc_names = [c["name"] for c in columns if c.get("expression")]
        type_pairs = []
        for col in columns:
            if col.get("expression"):
                continue  # calculated column, not in CSV
            cname = col["name"].replace('"', '""')
            ctype = _M_TYPE_MAP.get(col.get("dataType", "string").lower(), "type text")
            type_pairs.append(f'{{"{cname}", {ctype}}}')

        last_step = "PromotedHeaders"
        if calc_names:
            remove_list = ", ".join(f'"{n.replace(chr(34), chr(34)*2)}"' for n in calc_names)
            lines[-1] += ","
            lines.append(f"    RemovedCalcCollisions = Table.RemoveColumns({last_step}, {{{remove_list}}}, MissingField.Ignore)")
            last_step = "RemovedCalcCollisions"
        if type_pairs:
            lines[-1] += ","
            lines.append(f"    ChangedType = Table.TransformColumnTypes({last_step}, {{{', '.join(type_pairs)}}})")
            last_step = "ChangedType"
        if last_step != "PromotedHeaders":
            lines.append("in")
            lines.append(f"    {last_step}")
            return "\n".join(lines)
    lines.append("in")
    lines.append("    PromotedHeaders")
    return "\n".join(lines)


# ── Helpers ────────────────────────────────────────────────────────────────────
def _safe_name(name: str) -> str:
    return re.sub(r"[^\w\-]", "_", str(name)).strip("_") or "Report"


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _new_hex(n: int = 20) -> str:
    return uuid.uuid4().hex[:n]


def _long(path: str) -> str:
    """Prefix absolute Windows paths with `\\\\?\\` to bypass MAX_PATH (260).
    PBIP folder trees stack `<ReportName>.Report\\definition\\pages\\
    ReportSection<20hex>\\visuals\\<20hex>` which crosses 260 chars for any
    report whose display name is non-trivial. The `\\\\?\\` prefix switches
    Win32 file APIs into long-path mode and is a no-op on POSIX (where the
    limit is much higher).
    """
    if os.name == "nt" and os.path.isabs(path) and not path.startswith("\\\\?\\"):
        return "\\\\?\\" + os.path.normpath(path)
    return path


def _makedirs(path: str) -> None:
    os.makedirs(_long(path), exist_ok=True)


def _write_json(path: str, data):
    _makedirs(os.path.dirname(path))
    # ensure_ascii=False — write real Unicode (Japanese visual titles, page
    # names, etc.) into the PBIP JSON instead of \uXXXX escapes. ASCII is
    # unaffected. The file is UTF-8 so Power BI reads it correctly.
    with open(_long(path), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _write_text(path: str, text: str):
    _makedirs(os.path.dirname(path))
    with open(_long(path), "w", encoding="utf-8") as f:
        f.write(text)


# ── .pbip entry point ─────────────────────────────────────────────────────────
def _write_pbip(output_dir: str, name: str):
    """PBIP entry file — `<Name>.pbip` references the `.Report` folder.

    NOTE: PBIP's `pbipProperties` schema only permits a `report` artifact —
    there is NO `dataset` artifact type. A `.pbip` ALWAYS opens a report;
    the semantic model is a child of the report project. So the dataset
    deliverable is packaged as a full PBIP whose report is empty (see
    `write_empty_report`), not as a standalone dataset `.pbip`."""
    _write_json(os.path.join(output_dir, f"{name}.pbip"), {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0",
        "artifacts": [{"report": {"path": f"{name}.Report"}}],
        "settings": {"enableAutoRecovery": True},
    })


# ── .platform files ───────────────────────────────────────────────────────────
def _write_platform(path: str, item_type: str, display_name: str):
    _write_json(path, {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": item_type, "displayName": display_name},
        "config": {"version": "2.0", "logicalId": _new_uuid()},
    })


# ── Report folder ─────────────────────────────────────────────────────────────
def _write_pbir(report_dir: str, name: str):
    _write_json(os.path.join(report_dir, "definition.pbir"), {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0",
        "datasetReference": {"byPath": {"path": f"../{name}.SemanticModel"}},
    })


def _write_version_json(report_def_dir: str):
    _write_json(os.path.join(report_def_dir, "version.json"), {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
        "version": "2.0.0",
    })


# PBI built-in visual types. Anything OUTSIDE this set is treated as a
# custom (AppSource / third-party) visual and registered in report.json's
# `publicCustomVisuals` list so PBI Desktop knows to fetch the plugin
# instead of rendering the container blank.
_BUILTIN_VISUAL_TYPES = {
    "lineChart", "areaChart", "stackedAreaChart", "barChart",
    "clusteredBarChart", "stackedBarChart", "columnChart",
    "clusteredColumnChart", "stackedColumnChart", "lineStackedColumnComboChart",
    "lineClusteredColumnComboChart", "pieChart", "donutChart", "funnel",
    "waterfallChart", "scatterChart", "treemap", "map", "filledMap",
    "shapeMap", "azureMap",
    "card", "multiRowCard", "kpi", "gauge", "scorecard",
    "tableEx", "pivotTable", "matrix",
    "slicer", "slicerVisual", "advancedSlicerVisual", "listControl",
    "hierarchySlicer",
    "image", "textbox", "actionButton", "shape", "basicShape",
    "decompositionTree", "qnaVisual", "aiNarratives",
    "ribbonChart", "comboChart",
    "esriVisual", "powerAppsVisual",
}


def _collect_custom_visual_types(mapped: dict) -> list:
    """Return de-duplicated list of non-built-in visualType strings found in
    any visual on any page. These are AppSource / third-party visuals (e.g.
    `WordCloud1447959067750`, `htmlContent443BE3...`) and must be declared
    in report.json's `publicCustomVisuals` for PBI Desktop to render them —
    otherwise the visual container appears blank with no error.
    """
    seen: set = set()
    out: list = []
    for page in mapped.get("pages", []):
        for vis in page.get("visuals", []):
            vt = vis.get("visualType") or ""
            if vt and vt not in _BUILTIN_VISUAL_TYPES and vt not in seen:
                seen.add(vt)
                out.append(vt)
    return out


# ── Image visuals ─────────────────────────────────────────────────────────────
def _safe_resource_name(image_id: str, filename: str) -> str:
    """A unique, filesystem-safe RegisteredResources item name for an image.
    Prefixed with the image id so two visuals with same-named files don't
    collide, e.g. `da90f2af_Tru_Secure_Logo.PNG`."""
    base = os.path.basename(filename or "image")
    stem, ext = os.path.splitext(base)
    ext = ext or ".png"
    stem = re.sub(r"[^A-Za-z0-9_.-]", "_", stem)[:48].strip("_") or "image"
    return f"{str(image_id)[:8]}_{stem}{ext}"


def _resolve_report_images(mapped: dict, report_dir: str) -> dict:
    """For every image visual, fetch its binary from Postgres
    (jnj_poc.report_images) and write it into the report's
    StaticResources/RegisteredResources/ folder.

    Returns a registry {imageId: resource_name}. Non-fatal — a missing image
    or a Postgres outage simply leaves that id out of the registry, and the
    image visual is then written without an image (as before)."""
    image_ids = set()
    for page in mapped.get("pages", []):
        for v in page.get("visuals", []):
            iid = v.get("imageId")
            if iid and (v.get("visualType") == "image" or v.get("imageUrl")):
                image_ids.add(str(iid))
        # Page-level images — canvas background and wallpaper.
        for k in ("background_image_id", "wallpaper_image_id"):
            if page.get(k):
                image_ids.add(str(page[k]))
    if not image_ids:
        return {}

    fetched: dict = {}
    try:
        import sys as _sys
        _pkg_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        if _pkg_root not in _sys.path:
            _sys.path.insert(0, _pkg_root)
        from integrations.image_store import fetch_images
        fetched = fetch_images(image_ids)
    except Exception:
        fetched = {}

    registry: dict = {}
    res_dir = os.path.join(report_dir, "StaticResources", "RegisteredResources")
    for iid in sorted(image_ids):
        rec = fetched.get(iid)
        if not rec or not rec.get("data"):
            continue
        res_name = _safe_resource_name(iid, rec.get("filename", ""))
        _makedirs(res_dir)
        with open(_long(os.path.join(res_dir, res_name)), "wb") as fh:
            fh.write(rec["data"])
        registry[iid] = res_name
    return registry


def _write_report_json(report_def_dir: str, report_dir: str, mapped: dict | None = None,
                       image_registry: dict | None = None):
    # Copy base theme file into StaticResources
    theme_src = os.path.join(_ASSETS_DIR, "CY22SU08.json")
    theme_dst_dir = os.path.join(report_dir, "StaticResources", "SharedResources", "BaseThemes")
    _makedirs(theme_dst_dir)
    if os.path.exists(theme_src):
        shutil.copy2(theme_src, _long(os.path.join(theme_dst_dir, "CY22SU08.json")))

    report_obj = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.1.0/schema.json",
        "themeCollection": {
            "baseTheme": {
                "name": "CY22SU08",
                "reportVersionAtImport": {
                    "visual": "1.8.71",
                    "report": "2.0.71",
                    "page": "1.3.71",
                },
                "type": "SharedResources",
            }
        },
        "resourcePackages": [
            {
                "name": "SharedResources",
                "type": "SharedResources",
                "items": [
                    {
                        "name": "CY22SU08",
                        "path": "BaseThemes/CY22SU08.json",
                        "type": "BaseTheme",
                    }
                ],
            }
        ],
        "settings": {
            "useStylableVisualContainerHeader": True,
            "exportDataMode": "AllowSummarized",
            "defaultDrillFilterOtherVisuals": True,
            "allowChangeFilterTypes": True,
            "useEnhancedTooltips": False,
        },
    }
    if mapped is not None:
        custom = _collect_custom_visual_types(mapped)
        if custom:
            report_obj["publicCustomVisuals"] = custom
    # Register the image files dropped into StaticResources/RegisteredResources/
    # so image visuals can bind to them via a ResourcePackageItem reference.
    if image_registry:
        report_obj["resourcePackages"].append({
            "name": "RegisteredResources",
            "type": "RegisteredResources",
            "items": [
                {"name": rn, "path": rn, "type": "Image"}
                for rn in sorted(set(image_registry.values()))
            ],
        })

    # Custom theme (style contract section 10) — when the RE supplies palette
    # overrides (`themeDataColors`) or `visualStyles`, build a custom theme
    # that inherits every untouched token from the bundled CY22SU08 base,
    # write it as a RegisteredResource, and layer it over the base theme via
    # themeCollection.customTheme. Visuals then pick up the brand colours
    # automatically while still falling back to base for anything unspecified.
    theme_meta = (mapped or {}).get("theme") if mapped is not None else None
    if _styles is not None and theme_meta:
        base_theme = {}
        if os.path.exists(theme_src):
            try:
                with open(_long(theme_src), "r", encoding="utf-8") as _tf:
                    base_theme = json.load(_tf)
            except (OSError, ValueError):
                base_theme = {}
        custom_theme = _styles.build_custom_theme(theme_meta, base_theme)
        if custom_theme:
            theme_name = custom_theme.get("name", "CustomTheme")
            theme_file = f"{_safe_name(theme_name)}.json"
            reg_dir = os.path.join(report_dir, "StaticResources", "RegisteredResources")
            _makedirs(reg_dir)
            _write_json(os.path.join(reg_dir, theme_file), custom_theme)
            report_obj["themeCollection"]["customTheme"] = {
                "name": theme_name,
                # `reportVersionAtImport` is REQUIRED by the report.json schema
                # for every themeCollection entry (baseTheme AND customTheme);
                # omitting it makes Power BI Desktop refuse to open the PBIP
                # with "Required properties are missing: reportVersionAtImport".
                "reportVersionAtImport": {
                    "visual": "1.8.71",
                    "report": "2.0.71",
                    "page": "1.3.71",
                },
                "type": "RegisteredResources",
            }
            # Ensure a RegisteredResources package exists, then register the
            # theme file in it (reusing the image package if already present).
            reg_pkg = next(
                (p for p in report_obj["resourcePackages"]
                 if p.get("name") == "RegisteredResources"), None)
            if reg_pkg is None:
                reg_pkg = {"name": "RegisteredResources",
                           "type": "RegisteredResources", "items": []}
                report_obj["resourcePackages"].append(reg_pkg)
            reg_pkg.setdefault("items", []).append(
                {"name": theme_name, "path": theme_file, "type": "CustomTheme"})

    _write_json(os.path.join(report_def_dir, "report.json"), report_obj)


def _write_pages_json(pages_dir: str, page_ids: list, active: str):
    _write_json(os.path.join(pages_dir, "pages.json"), {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json",
        "pageOrder": page_ids,
        "activePageName": active,
    })


def _image_value(res_name: str) -> dict:
    """The `image`-typed property value used by page background / wallpaper —
    points at a file registered in StaticResources/RegisteredResources/."""
    return {
        "image": {
            "name": {"expr": {"Literal": {"Value": f"'{res_name}'"}}},
            "url": {
                "expr": {
                    "ResourcePackageItem": {
                        "PackageName": "RegisteredResources",
                        "PackageType": 1,
                        "ItemName": res_name,
                    }
                }
            },
            "scaling": {"expr": {"Literal": {"Value": "'Fit'"}}},
        }
    }


def _page_image_objects(page: dict, image_registry: dict | None) -> dict:
    """Build the page.json `objects` block for a canvas-background image
    (`background_image_id`) and/or a wallpaper image (`wallpaper_image_id`).
    Returns {} when the page references no images / they weren't fetched."""
    reg = image_registry or {}
    objects: dict = {}
    bg_id = page.get("background_image_id")
    if bg_id and reg.get(str(bg_id)):
        objects["background"] = [{
            "properties": {
                "image": _image_value(reg[str(bg_id)]),
                "transparency": {"expr": {"Literal": {"Value": "0D"}}},
            }
        }]
    wp_id = page.get("wallpaper_image_id")
    if wp_id and reg.get(str(wp_id)):
        objects["outspace"] = [{
            "properties": {
                "image": _image_value(reg[str(wp_id)]),
                "transparency": {"expr": {"Literal": {"Value": "0D"}}},
            }
        }]
    return objects


# PBIR `page.json` requires `displayOption` to be one of these STRING enum
# values. The PowerBI Layout stores it as an INTEGER (0=FitToPage, 1=FitToWidth,
# 2=ActualSize); tooltip/other pages can carry non-standard codes (e.g. 3). Any
# integer / unknown value must be mapped to a valid string or Power BI Desktop
# refuses to open the report ("Expected String but got Integer").
_VALID_DISPLAY_OPTIONS = {"FitToPage", "FitToWidth", "ActualSize"}
_DISPLAY_OPTION_BY_INT = {0: "FitToPage", 1: "FitToWidth", 2: "ActualSize"}


def _normalize_display_option(v) -> str:
    """Coerce a page displayOption (string OR PowerBI integer enum) to a valid
    PBIR string. Unknown / non-standard values fall back to FitToPage."""
    if isinstance(v, str) and v in _VALID_DISPLAY_OPTIONS:
        return v
    if isinstance(v, bool):          # bool is an int subclass — guard first
        return "FitToPage"
    if isinstance(v, int):
        return _DISPLAY_OPTION_BY_INT.get(v, "FitToPage")
    return "FitToPage"


def _write_page(pages_dir: str, page: dict, page_id: str, measures_by_table: dict,
                col_types: dict, measure_fp: list, dim_fp: list,
                image_registry: dict | None = None,
                page_ids: dict | None = None) -> dict:
    """Write a page and its visuals. Returns {RE visual id → generated PBIP
    visual name} so the caller can resolve cross-visual references (edit
    interactions, bookmarks). `page_ids` maps page display name → ReportSection
    id, passed to visuals so navigation/drillthrough buttons can target pages."""
    page_dir = os.path.join(pages_dir, page_id)
    _makedirs(page_dir)

    # Write visuals FIRST so we can collect the RE-id → generated-name map
    # before emitting page.json (which carries visualInteractions referencing
    # the generated names).
    visuals_dir = os.path.join(page_dir, "visuals")
    id_map: dict = {}
    for vis_idx, visual in enumerate(page.get("visuals", [])):
        vid = _write_visual(visuals_dir, visual, measures_by_table, col_types,
                            measure_fp, dim_fp, page["name"], vis_idx,
                            image_registry, page_ids)
        re_id = visual.get("id") or visual.get("name")
        if re_id:
            id_map[re_id] = vid
        # Also key by the ORIGINAL source visual id (PowerBI .pbix container id)
        # so a captured bookmark — whose visualContainers are keyed by that id —
        # remaps onto this generated visual (section 7).
        src_vid = visual.get("source_visual_id")
        if src_vid:
            id_map[src_vid] = vid

    canvas = page.get("canvas") if isinstance(page.get("canvas"), dict) else None
    # displayOption: prefer a value the RE supplied directly (its `styles.
    # display_option`), else derive from the canvas sizing mode, else default.
    if page.get("displayOption"):
        display_option = page["displayOption"]
    elif _styles is not None:
        display_option = _styles.page_display_option(canvas)
    else:
        display_option = "FitToPage"
    # PBIR requires a STRING enum; the source may carry an integer (PowerBI
    # Layout) or a tooltip page's non-standard code — coerce to a valid value.
    display_option = _normalize_display_option(display_option)
    page_json = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.0.0/schema.json",
        "name": page_id,
        "displayName": page["name"],
        "displayOption": display_option,
        "height": page.get("height", 720),
        "width": page.get("width", 1280),
    }
    # Page type (Tooltip / Drillthrough) — omitted entirely for a standard page.
    if _styles is not None:
        _ptype = _styles.page_type(canvas)
        if _ptype:
            page_json["type"] = _ptype
    # Canvas background / wallpaper images (binaries fetched from Postgres),
    # then layer the canvas colour / transparency / vertical-alignment style
    # props (style contract section 1) on top of the same objects.
    page_objects = _page_image_objects(page, image_registry)
    if _styles is not None and canvas:
        page_objects = _styles.build_page_objects(canvas, existing_objects=page_objects)
    # The RE's ready-made page PBIP (`styles.raw`: background, outspace, …)
    # wins per top-level object — it already resolved colours / theme refs.
    # Sanitised first so a malformed page block can't block report load.
    raw_page_objs = (_styles.sanitize_raw_objects(page.get("raw_objects"))
                     if _styles else page.get("raw_objects"))
    if isinstance(raw_page_objs, dict) and raw_page_objs:
        page_objects = {**page_objects, **raw_page_objs}
    if page_objects:
        page_json["objects"] = page_objects
    # Edit interactions / cross-filtering (style contract section 8) — translate
    # the RE's source/target visual ids to the generated names via id_map.
    if _styles is not None and page.get("interactions"):
        vis_int = _styles.build_visual_interactions(page["interactions"], id_map)
        if vis_int:
            page_json["visualInteractions"] = vis_int
    # Filter pane filter definitions (section 1 — per-filter locking / hidden /
    # filterType). Carried verbatim in the PBIP `filterConfig` shape.
    if isinstance(page.get("filterConfig"), dict):
        page_json["filterConfig"] = page["filterConfig"]
    _write_json(os.path.join(page_dir, "page.json"), page_json)

    return id_map


def _write_visual(visuals_dir: str, visual: dict, measures_by_table: dict,
                  col_types: dict, measure_fp: list, dim_fp: list,
                  page_name: str = "", vis_idx: int = 0,
                  image_registry: dict | None = None,
                  page_ids: dict | None = None) -> str:
    vid = _new_hex(20)
    vdir = os.path.join(visuals_dir, vid)
    _makedirs(vdir)

    pos = visual.get("position", {})
    vtype = _VISUAL_TYPE_MAP.get(visual.get("visualType", "tableEx"), visual.get("visualType", "tableEx"))
    aggregate_values = vtype not in _NON_AGGREGATE_VISUALS
    # Rewrite per-visualType role names BEFORE building the queryState so the
    # field lands in the right PBI slot (e.g. `Indicator` for KPI, not the
    # generic `Values` PBI's KPI engine ignores).
    visual_fields = _remap_visual_field_roles(visual.get("fields", []), vtype, measures_by_table)
    query_state, agg_decisions = _build_query_state(
        visual_fields, measures_by_table, col_types, aggregate_values,
        is_table=(vtype in _TABLE_VTYPES),
    )

    # Inject fieldParameters — skipped for slicers/textbox/image and tables.
    # tableEx with a fieldParameter binding collapses the Values projections
    # to a single dynamic-pick row instead of rendering one row per record.
    _SKIP_FP = {"slicer", "slicerVisual", "textbox", "image", "actionButton", "tableEx"}
    if vtype not in _SKIP_FP:
        _VAL_ROLES = {"Y", "Y2", "Values", "Group", "Size", "Tooltips"}
        _DIM_ROLES = {"Category", "Rows", "Axis"}
        for fp_table, target_roles in [(t, _VAL_ROLES) for t in measure_fp] + \
                                      [(t, _DIM_ROLES) for t in dim_fp]:
            for role, role_data in query_state.items():
                n = len(role_data.get("projections", []))
                if n > 0 and role in target_roles:
                    role_data["fieldParameters"] = [{
                        "parameterExpr": {
                            "Column": {
                                "Expression": {"SourceRef": {"Entity": fp_table}},
                                "Property": fp_table,
                            }
                        },
                        "index": 0,
                        "length": n,
                    }]

    # Faithful field-parameter bindings captured from the source visual
    # (`queryFieldParametersByRole`): bind the EXACT role the parameter drives,
    # with its captured index/length. This is what makes a field-parameter slicer
    # reconfigure THIS visual (PowerBI). Takes precedence over the heuristic
    # injection above. The captured `expr` is renamed to the PBIP `parameterExpr`.
    _fp_by_role = visual.get("field_parameters_by_role")
    if isinstance(_fp_by_role, dict) and vtype not in _SKIP_FP:
        # The source role (Y/Values/Rows/Category) usually matches the queryState
        # role; tolerate the common measure/dimension aliases when it doesn't.
        _ROLE_ALIASES = {"Y": ("Y", "Values"), "Values": ("Values", "Y"),
                         "Category": ("Category", "Axis", "Rows"),
                         "Rows": ("Rows", "Category")}
        for _src_role, _binds in _fp_by_role.items():
            if not isinstance(_binds, list) or not _binds:
                continue
            role_data = next((query_state[r] for r in _ROLE_ALIASES.get(_src_role, (_src_role,))
                              if query_state.get(r, {}).get("projections")), None)
            if role_data is None:
                continue
            _out = []
            for _b in _binds:
                if not isinstance(_b, dict):
                    continue
                _expr = _b.get("parameterExpr") or _b.get("expr")
                if _expr:
                    _out.append({
                        "parameterExpr": _expr,
                        "index": _b.get("index", 0),
                        "length": _b.get("length", len(role_data["projections"])),
                    })
            if _out:
                role_data["fieldParameters"] = _out

    vis_obj = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.6.0/schema.json",
        "name": vid,
        "position": {
            "x": pos.get("x", 0),
            "y": pos.get("y", 0),
            "z": pos.get("z", 0),
            "height": pos.get("h", 300),
            "width": pos.get("w", 400),
        },
        "visual": {
            "visualType": vtype,
            "drillFilterOtherVisuals": True,
        },
    }

    if query_state:
        # Tables render row-by-row and don't need a chart-style sort binding;
        # forcing one (e.g. sort by Customer ID Descending) makes Power BI
        # reduce the table to a single row. Match the reference: omit it.
        if vtype == "tableEx":
            # Reference tableEx omits "active" on plain Column projections;
            # carrying it through prevents the renderer from materialising
            # the row data even though the column headers exist.
            for role_data in query_state.values():
                for proj in role_data.get("projections", []):
                    if "Column" in proj.get("field", {}) and "active" in proj:
                        del proj["active"]
            vis_obj["visual"]["query"] = {"queryState": query_state}
        elif vtype in ("pivotTable", "matrix"):
            # Pivots and matrices sort by their leftmost ROW header column
            # (Ascending), not by their Values. Sorting by a Measure or
            # Aggregation field — which is what the chart-style fallback
            # below does — makes PBI parse the visual successfully but
            # silently refuse to render it (the sort target can't be bound
            # to a pivot row group). Ground-truth PBIP exports always sort
            # pivots by their first Rows column ascending; match that.
            sort_field = None
            for role in ("Rows", "Category", "Axis", "Columns"):
                projs = query_state.get(role, {}).get("projections", [])
                if projs:
                    sort_field = projs[0].get("field")
                    break
            q = {"queryState": query_state}
            if sort_field and "Column" in sort_field:
                q["sortDefinition"] = {
                    "sort": [{"field": sort_field, "direction": "Ascending"}],
                }
            vis_obj["visual"]["query"] = q
        else:
            sort_field = None
            for _sort_role in ("Y", "Y2", "Values", "Size"):
                projs = query_state.get(_sort_role, {}).get("projections", [])
                if projs:
                    sort_field = projs[0].get("field")
                    break
            if sort_field:
                sort_def = {
                    "sort": [{"field": sort_field, "direction": "Descending"}],
                    "isDefaultSort": True,
                }
            else:
                sort_def = {"isDefaultSort": True}
            vis_obj["visual"]["query"] = {
                "queryState": query_state,
                "sortDefinition": sort_def,
            }

    title = visual.get("title", "")
    formatting = visual.get("formatting") if isinstance(visual.get("formatting"), dict) else None
    # Ready-made PBIP the RE produced under `style.raw` — authoritative
    # (colours, theme refs, fonts already resolved). Emitted as-is BUT first
    # run through the safety-net sanitiser so a malformed block from the RE
    # can never break the whole report (worst case: one block is dropped).
    # The camelCase `formatting` builders only fill gaps the raw doesn't cover.
    if _styles is not None:
        raw_vc = _styles.sanitize_raw_objects(visual.get("raw_vc_objects")) or None
        raw_objs = _styles.sanitize_raw_objects(visual.get("raw_objects")) or None
    else:
        raw_vc = visual.get("raw_vc_objects") if isinstance(visual.get("raw_vc_objects"), dict) else None
        raw_objs = visual.get("raw_objects") if isinstance(visual.get("raw_objects"), dict) else None
    # Container chrome — title, subtitle, background, border, drop shadow and
    # alt text (style contract section 2). When the RE supplies a
    # `formatting.general` block the styler emits the full styled chrome;
    # otherwise it falls back to a plain title literal, preserving the
    # pre-styling behaviour for inputs that carry no style metadata.
    container_objs = {}
    if _styles is not None:
        container_objs = _styles.build_visual_container_objects(
            formatting, fallback_title=title, page_ids=page_ids)
    elif title:
        # The title is emitted as a DAX-style string literal ('...'); double
        # any embedded single quote so a title like O'Neill — or a Japanese
        # title — doesn't corrupt the literal. Non-ASCII passes through fine.
        _title_lit = str(title).replace("'", "''")
        container_objs = {
            "title": [{"properties": {"text": {"expr": {"Literal": {"Value": f"'{_title_lit}'"}}}}}]}
    # RE raw vcObjects win per top-level object (already final PBIP). When the
    # raw carries no title but the visual has one, keep the fallback title.
    if raw_vc:
        container_objs = {**container_objs, **raw_vc}
    # Guarantee a title object when the visual HAS a title but neither the styler
    # nor the raw vcObjects produced one — charts were otherwise emitting
    # title=None and losing their captions (audit #29). Only fills a gap: a
    # title already present (incl. a raw_vc title with show:false) is untouched.
    if title and not container_objs.get("title"):
        _tl = str(title).replace("'", "''")
        container_objs["title"] = [{"properties": {"text": {"expr": {"Literal": {"Value": f"'{_tl}'"}}}}}]
    if container_objs:
        vis_obj["visual"]["visualContainerObjects"] = container_objs

    # Seed visual.objects with the RE's authoritative raw objects (legend,
    # dataPoint, labels, axes, slicer, grid, …) so colours/fonts render
    # exactly as the source report. Textbox/image bindings below and the
    # formatting builders all merge on top without clobbering these.
    if raw_objs:
        vis_obj["visual"].setdefault("objects", {}).update(raw_objs)

    # Textbox visual — emit `content` as the textbox body (paragraphs),
    # NOT as the title chrome. PBI's title is a single-line DAX literal
    # and can't hold multi-paragraph rich text; the textbox body uses
    # objects.general[*].properties.paragraphs which is built for it.
    # Each newline in `content` becomes its own paragraph so PBI renders
    # the line breaks (blank lines round-trip as empty paragraphs).
    if vtype == "textbox":
        content = visual.get("content")
        # Prefer the rich-text builder (style contract section 9 — per-run
        # fonts/colours/links from formatting.richText); fall back to splitting
        # plain `content` into one paragraph per line (legacy behaviour).
        if _styles is not None:
            paragraphs = _styles.build_textbox_paragraphs(formatting, content or "")
        elif content:
            paragraphs = [{"horizontalTextAlignment": "left", "textRuns": [{"value": line}]}
                          for line in str(content).split("\n")]
        else:
            paragraphs = []
        # Don't overwrite a `general` the RE's raw objects already provided
        # (it may carry the textbox content); only set ours when absent.
        if paragraphs:
            objects = vis_obj["visual"].setdefault("objects", {})
            if "general" not in objects:
                objects["general"] = [{"properties": {"paragraphs": paragraphs}}]

    # Image visual — bind it to the image file registered in the report's
    # StaticResources/RegisteredResources/ folder (binary pulled from
    # Postgres jnj_poc.report_images by `_resolve_report_images`).
    if vtype == "image":
        iid = visual.get("imageId")
        res_name = (image_registry or {}).get(str(iid)) if iid else None
        if res_name:
            objects = vis_obj["visual"].setdefault("objects", {})
            # MERGE the imageUrl binding into any `general` the raw objects
            # supplied (e.g. image scaling), so both survive.
            gen = objects.setdefault("general", [{"properties": {}}])
            if not gen:
                gen.append({"properties": {}})
            gen[0].setdefault("properties", {})["imageUrl"] = {
                "expr": {
                    "ResourcePackageItem": {
                        "PackageName": "RegisteredResources",
                        "PackageType": 1,
                        "ItemName": res_name,
                    }
                }
            }

    # Visual-type formatting — data colours, data labels, legend, value/
    # category axes, lines & markers, and card/KPI callout (style contract
    # sections 3 & 6). Merged on top of any objects already set above
    # (textbox paragraphs / image binding) with setdefault so the structural
    # bindings always win and are never clobbered by a style key.
    if _styles is not None and formatting:
        style_objs = _styles.build_visual_objects(formatting)
        if style_objs:
            objects = vis_obj["visual"].setdefault("objects", {})
            for _k, _v in style_objs.items():
                objects.setdefault(_k, _v)

    _write_json(os.path.join(vdir, "visual.json"), vis_obj)

    if _dbg:
        _dbg.log_visual(
            page=page_name,
            vis_title=title,
            vis_idx=vis_idx,
            input_dict={
                "visualType": vtype,
                "title": title,
                "position": pos,
                "fields": visual_fields,
                "aggregate_values": aggregate_values,
            },
            agg_decisions=agg_decisions,
            query_state=query_state,
            visual_json=vis_obj,
        )

    return vid


# Per-visualType role remap. The generic role names emitted by the parser
# (`Values`, `Y`, `Category`, ...) cover what chart visuals need, but a few
# visualTypes require their own role names — emitting the generic one leaves
# the slot empty in PBI Desktop even though the field is technically present.
# The KPI visual is the loudest case: it ignores `Values` / `Y` and only
# binds a field placed under `Indicator`. Add new visualTypes here as their
# role mismatches are discovered — each entry is `{ generic_role: pbi_role }`.
# Per-visualType role corrections. The generic roles produced upstream
# (Category / Values / Y / Pages / Legend / Color / Series / Size ...) do not
# all match the data-role names each Power BI visualType actually binds. A field
# placed under a role the visual does not recognise leaves that data slot EMPTY
# in Desktop even though the field is present — the visual renders with its type
# set but no rows/columns/values. The correct role names below are taken from
# real PBI conversions (the converter's own 03_visual_json.json debug captures):
#   areaChart / barChart / clusteredColumnChart / columnChart / lineChart /
#   pieChart / donutChart / text_table : Category + Y
#   map      : Category (location) + Values (measure)
#   pivotTable / matrix : Rows + Columns + Values
#   treemap  : Group + Values
#   scatterChart : X + Y (+ Details)
#   kpi      : Indicator (+ TrendLine / Goals)
#
# Mappings are additive per visualType; an entry not listed for a role leaves
# that role unchanged. PowerBI inputs already emit the correct PBI roles in most
# cases, and any role already at its target is a no-op, so this is safe for both
# Tableau and PowerBI flows.

# Cartesian "category + measure" charts: the dimension axis is Category, the
# measure axis is Y. Tableau's Pages shelf has no cartesian equivalent, so a
# field routed there must drive the Category (X) axis instead.
_CARTESIAN_CAT_Y = {
    "Values": "Y",      # measure slot must be Y, not the generic Values
    "Value":  "Y",
    "Pages":  "Category",  # Tableau Pages-shelf field -> X/Category axis
    "Axis":   "Category",
    "Series": "Legend",    # color/series dimension -> Legend
    "Color":  "Legend",
}

# Per-visualType role corrections, applied to ALL sources (source-agnostic).
# `_remap_visual_field_roles` is idempotent: a role already at its target is a
# no-op, and the pivotTable re-router fires ONLY for generic roles (no explicit
# Rows/Columns), so a source that already emits PBI-native roles (e.g. PowerBI)
# passes through unchanged while Tableau's generic shelf roles get translated.
# No source gate needed.
_VISUAL_ROLE_REMAP = {
    "kpi": {
        "Values":   "Indicator",
        "Value":    "Indicator",
        "Y":        "Indicator",
        "Tooltips": "TrendLine",
        "Goal":     "Goals",
        "Target":   "Goals",
    },
    "barChart":              dict(_CARTESIAN_CAT_Y),
    "clusteredBarChart":     dict(_CARTESIAN_CAT_Y),
    "stackedBarChart":       dict(_CARTESIAN_CAT_Y),
    "columnChart":           dict(_CARTESIAN_CAT_Y),
    "clusteredColumnChart":  dict(_CARTESIAN_CAT_Y),
    "stackedColumnChart":    dict(_CARTESIAN_CAT_Y),
    "lineChart":             dict(_CARTESIAN_CAT_Y),
    "areaChart":             dict(_CARTESIAN_CAT_Y),
    "stackedAreaChart":      dict(_CARTESIAN_CAT_Y),
    "lineStackedColumnComboChart": dict(_CARTESIAN_CAT_Y),
    "lineClusteredColumnComboChart": dict(_CARTESIAN_CAT_Y),
    "pieChart":              dict(_CARTESIAN_CAT_Y),
    "donutChart":            dict(_CARTESIAN_CAT_Y),
    "ribbonChart":           dict(_CARTESIAN_CAT_Y),
    "funnel":                dict(_CARTESIAN_CAT_Y),
    "waterfallChart":        {**_CARTESIAN_CAT_Y, "Series": "Breakdown", "Color": "Breakdown"},
    # Matrix/pivot: dimension on rows, color/series dimension on columns,
    # measures as Values.
    "pivotTable": {
        "Category": "Rows",
        "Axis":     "Rows",
        "Legend":   "Columns",
        "Series":   "Columns",
        "Color":    "Columns",
        "Y":        "Values",
    },
    # Treemap: grouping dimension under Group, measure under Values.
    "treemap": {
        "Category": "Group",
        "Axis":     "Group",
        "Y":        "Values",
    },
    # Scatter / bubble: two measures form the X/Y axes; a dimension identifies
    # the points (Details). Upstream emits the first measure as Category or Y.
    "scatterChart": {
        "Category": "Details",
        "Values":   "Y",
    },
    # Map: a location dimension under Category, the measure under Values, a
    # color dimension under Legend, a size measure under Size.
    "map": {
        "Pages":  "Category",
        "Axis":   "Category",
        "Y":      "Values",
        "Series": "Legend",
        "Color":  "Legend",
    },
    "filledMap": {
        "Pages":  "Category",
        "Axis":   "Category",
        "Y":      "Values",
        "Series": "Legend",
        "Color":  "Legend",
    },
    # Table visual: rows of columns + aggregated values. There is no Pages
    # concept — a Pages-shelf field becomes another Values column.
    "tableEx": {
        "Pages":  "Values",
        "Y":      "Values",
    },
}


def _remap_visual_field_roles(fields: list, vtype: str,
                              measures_by_table: dict | None = None) -> list:
    """Return a new field list with roles rewritten per `_VISUAL_ROLE_REMAP`.

    Source-AGNOSTIC and idempotent: a role already at its visualType's target is
    a no-op, and the pivotTable re-router fires ONLY when the visual has generic
    roles (no explicit Rows/Columns). So a source that already emits PBI-native
    matrix roles (e.g. PowerBI) passes through unchanged, while Tableau's generic
    shelf roles get translated. No source check needed. No-op for visualTypes
    without an entry. The original `fields` list is not mutated.

    `pivotTable` (Matrix) needs TYPE-AWARE routing a flat role map can't do — but
    ONLY when the input is generic:
      * a MEASURE must always land in Values — never Rows/Columns (a measure in
        a matrix Columns slot renders wrong / collapses the matrix);
      * the FIRST dimension goes to Rows, ADDITIONAL dimensions go to Columns
        (so a 2-dimension crosstab becomes a real row×column matrix).
    If the matrix ALREADY carries explicit Rows/Columns roles, they are an
    intentional layout (e.g. a multi-level row hierarchy) and are respected.
    """
    def _is_measure(f) -> bool:
        if measures_by_table is not None:
            return (f.get("column") or "") in measures_by_table.get(f.get("table") or "", set())
        # Fallback when measure index unavailable: an aggregation or a
        # value-bearing source role signals a measure.
        return bool(f.get("aggregation")) or (f.get("role") or "").lower() in (
            "values", "value", "y", "y2", "color", "size"
        )

    if vtype == "pivotTable" and not any(
            (f.get("role") or "") in ("Rows", "Columns") for f in fields):
        out, dim_seen, seen_meas = [], 0, set()
        for f in fields:
            nf = dict(f)
            if _is_measure(f):
                key = (f.get("table"), f.get("column"))
                if key in seen_meas:
                    continue  # drop duplicate measure (e.g. Values + Color same col)
                seen_meas.add(key)
                nf["role"] = "Values"
            else:
                # dimension: first -> Rows, rest -> Columns
                nf["role"] = "Rows" if dim_seen == 0 else "Columns"
                dim_seen += 1
            out.append(nf)
        return out

    remap = _VISUAL_ROLE_REMAP.get(vtype)
    if not remap:
        return fields
    out = []
    for f in fields:
        role = f.get("role", "")
        new_role = remap.get(role, role)
        if new_role == role:
            out.append(f)
        else:
            nf = dict(f)
            nf["role"] = new_role
            out.append(nf)
    return out


_VISUAL_TYPE_MAP = {
    "slicerVisual": "slicer",
    "dashboard-object": "textbox",
    # `barChart` in PBIP IS horizontal stacked bar — passing it through
    # preserves the source intent. Previously remapped to
    # `clusteredColumnChart` which flipped orientation (horizontal bars
    # rendered as vertical columns).
    "stackedBarChart": "barChart",
    "stackedColumnChart": "clusteredColumnChart",
    # `kpi_card` is Tableau's BAN tile — a single-scalar visual. It maps
    # to PBI's `card`, NOT `kpi`. PBI's `kpi` visualType is a value +
    # sparkline + goal combo and requires a TrendLine field; BANs don't
    # carry one, so PBI's KPI engine renders nothing. The writer's mapping
    # catches inputs that bypassed the parser normalisation so they still
    # land on the correct (renderable) visualType.
    "kpi_card": "card", "kpiCard": "card", "kpicard": "card", "kpi-card": "card",
    # Area chart aliases — PBI's canonical visualType is `areaChart`.
    # Without these, an input like `area_chart` falls through to custom-
    # visual registration and renders blank.
    "area_chart": "areaChart", "areachart": "areaChart",
    "stacked_area": "stackedAreaChart", "stacked_area_chart": "stackedAreaChart",
}

_ROLE_MAP = {
    "category": "Category", "axis": "Axis", "x": "Axis", "xaxis": "Axis",
    "y": "Y", "yaxis": "Y", "values": "Values", "value": "Values",
    "legend": "Legend", "color": "Legend", "size": "Size",
    "tooltips": "Tooltips", "tooltip": "Tooltips",
    "details": "Details", "detail": "Details",
    "group": "Group", "groups": "Group",
}
# Roles that display aggregated scalar values and need Aggregation wrapping for columns
_VALUE_ROLES = {"Values", "Y", "Value", "Size", "Tooltips", "Details", "Group",
                # KPI's main value slot. Without this, the role remap places
                # the field under `Indicator` but the aggregation branch in
                # _build_query_state never fires — the field gets emitted as
                # a plain Column ref (`tbl_sales.Sales`) instead of
                # `Aggregation(Sum)` (`Sum(tbl_sales.Sales)`), so PBI's KPI
                # engine shows the title chrome with no value. KPIs always
                # need their indicator field aggregated because the visual
                # displays a single scalar — there's no row context.
                "Indicator",
                # Sibling KPI slots that the role remap also produces and
                # that PBI scalarises the same way.
                "TrendLine", "Goals"}
# Visual types where fields are NOT auto-aggregated when aggregation is empty.
# Slicers list values; tableEx shows mixed rows (per-row dims + explicit aggregates).
# pivotTable/matrix is NOT here — pivots aggregate by design.
_NON_AGGREGATE_VISUALS = {
    # ONLY true value-list visuals never aggregate. tableEx was removed: a Power
    # BI table aggregates its measure/value columns (per the dimension columns)
    # and shows dimension columns plain — the per-field logic in
    # _build_query_state makes that distinction, so a table's Sum columns are no
    # longer flattened to raw rows (audit #27/#8).
    "slicer", "listControl", "advancedSlicerVisual", "hierarchySlicer",
}

# Table/matrix visuals: their non-measure columns shown without an explicit
# aggregation are raw "don't summarize" detail (so a NUMERIC column like Tenure
# stays a plain column, not Sum). Charts are NOT here, so a bare numeric value
# on a chart still defaults to Sum.
_TABLE_VTYPES = {"tableEx", "table", "pivotTable"}


_NUMERIC_TYPES = {"int64", "decimal", "number", "float", "double"}

# Aggregation Function codes used in PBIP queryState
_AGG_SUM   = 0  # numeric columns
_AGG_COUNT = 5  # CountNonNull — used for string/date columns


def _agg_function(tbl: str, col: str, col_types: dict) -> tuple:
    """Return (Function code, queryRef prefix) for a column aggregation."""
    dtype = col_types.get(tbl, {}).get(col, "string").lower()
    if dtype in _NUMERIC_TYPES:
        return _AGG_SUM, "Sum"
    return _AGG_COUNT, "CountNonNull"


_HIERARCHY_RE = re.compile(
    r'^(.+)\.([^.]+)\.(Date Hierarchy|Date hierarchy|date hierarchy)\.([^.]+)$'
)


def _parse_hierarchy(col: str):
    """Return (base_property, variation, hierarchy_name, level) if col is a date hierarchy path, else None."""
    m = _HIERARCHY_RE.match(col)
    if m:
        return m.group(1), m.group(2), m.group(3), m.group(4)
    return None


_AGG_DISPLAY_NAME = {
    0: "Sum", 1: "Average", 2: "Count", 3: "Min", 4: "Max",
    5: "Count", 6: "Median", 7: "Standard Deviation", 8: "Variance",
}


def _build_query_state(fields: list, measures_by_table: dict,
                        col_types: dict, aggregate_values: bool = True,
                        is_table: bool = False) -> tuple:
    """Build queryState matching real PBIP format.

    Returns (state_dict, decisions_list).
    """
    state: dict = {}
    decisions: list = []
    seen_first_plain_per_role: set = set()

    # Pre-scan: which roles contain at least one hierarchy-level projection?
    # Real PBIP exports mark ALL hierarchy levels in a role as `active: true`
    # (every drill level shows on the axis simultaneously) but mark any plain
    # column projection added to the SAME role as `active: false` — the plain
    # column is treated as an inactive drill target the user can switch to.
    # Our earlier rule ("first hierarchy active, rest inactive; first plain
    # active") produced visuals where, e.g., a lineChart's Category had
    # Year=active + Month=inactive + sales_mode=active. PBI then sees a
    # plain-column drill level simultaneously active with a hierarchy level
    # and refuses to render the visual until the user manually re-picks the
    # aggregation (which forces PBI to renormalise the queryState).
    roles_with_hierarchy: set = set()
    for field in fields:
        col = field.get("column") or ""
        if not col or not _parse_hierarchy(col):
            continue
        role = field.get("role", "Values")
        roles_with_hierarchy.add(_ROLE_MAP.get(role.lower(), role))

    for field in fields:
        role = field.get("role", "Values")
        pbip_role = _ROLE_MAP.get(role.lower(), role)

        tbl = field.get("table") or ""
        col = field.get("column") or ""
        if not tbl or not col:
            continue

        # `force_dimension` (set by the RE for a Tableau group/string calc bound
        # to a categorical role) forces a plain-Column projection even though the
        # name resolves to a measure — so a slicer/axis shows the category labels,
        # not an aggregated scalar.
        force_dim = bool(field.get("force_dimension"))
        is_measure = (col in measures_by_table.get(tbl, set())) and not force_dim
        is_value_role = (pbip_role in _VALUE_ROLES) and not force_dim
        # A non-measure DIMENSION on Details/Group is a grouping identifier, not a
        # value — emit it as a plain Column, never CountNonNull (audit #3 scatter
        # State, #26 treemap-by-agent).
        if pbip_role in ("Details", "Group") and not is_measure:
            is_value_role = False
        # A column the source explicitly aggregates (Sum/Avg/…) must KEEP that
        # aggregation even on a non-value role (e.g. Legend) or inside a table —
        # else the measure column renders as raw row values (audit #4/#27/#28).
        explicit_agg = (field.get("aggregation") or "").lower()
        _has_explicit_agg = explicit_agg in (
            "sum", "count", "countnonnull", "min", "minimum", "max", "maximum",
            "avg", "average", "median", "distinctcount", "countdistinct")
        col_type = col_types.get(tbl, {}).get(col, "string")
        # A non-measure column the source did NOT explicitly aggregate is a
        # "don't summarize" field — emit it as a PLAIN column, not an auto
        # aggregation. STRING fields are always plain (auto-counting a text
        # dimension like Customer ID collapses a detail table to one row). In a
        # TABLE / matrix, NUMERIC don't-summarize columns are likewise raw per-row
        # detail (e.g. Tenure, Premium Duration), so keep them plain too — only in
        # a CHART does a bare numeric value default to Sum. EXPLICIT aggregations
        # (the source's actual func) are always honoured.
        _is_string_type = col_type.lower() not in _NUMERIC_TYPES
        _plain_dont_summarize = (not is_measure and not _has_explicit_agg
                                 and (_is_string_type or is_table))

        hierarchy = _parse_hierarchy(col)

        if is_measure:
            field_obj = {
                "Measure": {
                    "Expression": {"SourceRef": {"Entity": tbl}},
                    "Property": col,
                }
            }
            query_ref = f"{tbl}.{col}"
            projection = {
                "field": field_obj,
                "queryRef": query_ref,
                "nativeQueryRef": col,
            }
            decisions.append({"role": pbip_role, "table": tbl, "column": col,
                               "col_type": col_type, "kind": "measure",
                               "fn_code": None, "fn_name": None})
        elif hierarchy:
            base_prop, variation, hier_name, level = hierarchy
            field_obj = {
                "HierarchyLevel": {
                    "Expression": {
                        "Hierarchy": {
                            "Expression": {
                                "PropertyVariationSource": {
                                    "Expression": {"SourceRef": {"Entity": tbl}},
                                    "Name": variation,
                                    "Property": base_prop,
                                }
                            },
                            "Hierarchy": hier_name,
                        }
                    },
                    "Level": level,
                }
            }
            query_ref = f"{tbl}.{col}"
            native_ref = f"{base_prop} {level}"
            # Every hierarchy level in a role is `active: true` — they are
            # the drill levels the axis is currently displaying, regardless
            # of whether they share the same base column / variation.
            projection = {
                "field": field_obj,
                "queryRef": query_ref,
                "nativeQueryRef": native_ref,
                "active": True,
            }
            decisions.append({"role": pbip_role, "table": tbl, "column": col,
                               "col_type": col_type, "kind": "hierarchy",
                               "hierarchy_level": level, "fn_code": None, "fn_name": None})
        elif (is_value_role or _has_explicit_agg) and aggregate_values and not _plain_dont_summarize:
            # Aggregate only for chart visuals. Slicers (in
            # _NON_AGGREGATE_VISUALS) always render fields as raw column values
            # — even fields with explicit aggregation in the input — so the
            # user sees one row per record instead of a single rolled-up row.
            # Aggregation Function codes used in PBIP queryState (must match
            # Power BI's QueryAggregateFunction enum). 0=Sum, 1=Avg, 2=Count,
            # 3=Min, 4=Max, 5=CountNonNull, 6=Median, 7=StdDev, 8=Var.
            # Honoring every explicit aggregation the input declares — earlier
            # only Sum/Count/CountNonNull were handled, so a field with
            # aggregation="Min" silently fell through to the default and got
            # emitted as CountNonNull, producing the wrong value in the pivot.
            explicit_agg = (field.get("aggregation") or "").lower()
            if explicit_agg == "sum":
                fn, fn_name = _AGG_SUM, "Sum"
            elif explicit_agg in ("count", "countnonnull"):
                fn, fn_name = _AGG_COUNT, "CountNonNull"
            elif explicit_agg in ("min", "minimum"):
                fn, fn_name = 3, "Min"
            elif explicit_agg in ("max", "maximum"):
                fn, fn_name = 4, "Max"
            elif explicit_agg in ("avg", "average"):
                fn, fn_name = 1, "Average"
            elif explicit_agg in ("median",):
                fn, fn_name = 6, "Median"
            elif explicit_agg in ("distinctcount", "countdistinct"):
                fn, fn_name = 2, "Count"
            else:
                fn, fn_name = _agg_function(tbl, col, col_types)
            field_obj = {
                "Aggregation": {
                    "Expression": {
                        "Column": {
                            "Expression": {"SourceRef": {"Entity": tbl}},
                            "Property": col,
                        }
                    },
                    "Function": fn,
                }
            }
            query_ref = f"{fn_name}({tbl}.{col})"
            # PBI Desktop's auto-generated friendly name for an aggregation
            # is "<UserFacingAggName> of <ColumnName>" (e.g. "Count of
            # sales_mode"). Real PBI exports use this as the nativeQueryRef
            # and OMIT `displayName` unless the user explicitly renamed the
            # field. Emitting just `col` here produced a nativeQueryRef
            # identical to a plain-column projection of the same column —
            # which made PBI silently collapse the two and the aggregated
            # column went missing from the rendered visual.
            agg_display = _AGG_DISPLAY_NAME.get(fn, fn_name)
            projection = {
                "field": field_obj,
                "queryRef": query_ref,
                "nativeQueryRef": f"{agg_display} of {col}",
            }
            decisions.append({"role": pbip_role, "table": tbl, "column": col,
                               "col_type": col_type, "kind": "aggregation",
                               "fn_code": fn, "fn_name": fn_name,
                               "explicit_agg": explicit_agg or None})
        else:
            field_obj = {
                "Column": {
                    "Expression": {"SourceRef": {"Entity": tbl}},
                    "Property": col,
                }
            }
            query_ref = f"{tbl}.{col}"
            # Active-flag rule for plain columns (matches real PBI exports):
            #   * If this role already contains a hierarchy projection, every
            #     plain column added on top is `active: false` — the hierarchy
            #     levels are the live drill targets, plain cols are inactive
            #     alternatives the user can switch to.
            #   * Otherwise (pure plain-column role), the FIRST plain column
            #     is active, subsequent same-role columns are inactive drill
            #     levels (matrix/pivot drill convention).
            if pbip_role in roles_with_hierarchy:
                is_active = False
            else:
                plain_key = ("plain_col", pbip_role)
                is_active = plain_key not in seen_first_plain_per_role
                if is_active:
                    seen_first_plain_per_role.add(plain_key)
            projection = {
                "field": field_obj,
                "queryRef": query_ref,
                "nativeQueryRef": col,
                "active": is_active,
            }
            decisions.append({"role": pbip_role, "table": tbl, "column": col,
                               "col_type": col_type, "kind": "plain_column",
                               "fn_code": None, "fn_name": None})

        # A renamed field — the source gave it a display label different from the
        # auto-generated nativeQueryRef — is emitted as the projection's
        # `displayName`, so the visual shows e.g. "No of Policies" instead of
        # "CountNonNull of Customer ID". PBIP carries displayName only for renamed
        # fields, so we add it only when it differs.
        _disp = (field.get("display_name") or "").strip()
        if _disp and _disp != projection.get("nativeQueryRef"):
            projection["displayName"] = _disp

        if pbip_role not in state:
            state[pbip_role] = {"projections": []}
        state[pbip_role]["projections"].append(projection)

    # Note: previously dropped Series when it duplicated Category's queryRefs,
    # on the assumption PBI rejects same-column subdivision. Ground-truth PBIP
    # exports prove that assumption WRONG — Power BI accepts Series=Category
    # and renders the chart with per-category color segments (e.g. a bar
    # chart of customer count by Age Group, colored by Age Group). Dropping
    # Series here silently flattened legitimate visuals to single-color
    # outputs that looked broken to the user.

    return state, decisions


# ── SemanticModel — TMDL ──────────────────────────────────────────────────────
# Captures BOTH the table identifier (quoted or bare) AND the column name
# inside any `SUM(<table>[<column>])` reference. Capturing only the column
# name (the previous behavior) made the upgrade-to-numeric logic key off
# bare column names, which cross-contaminated any other table that happened
# to have a column of the same name (e.g. `Description` on tbl_sales1 and
# tbl_products — a measure `SUM(tbl_sales1[Description])` was upgrading
# tbl_products.Description too, then M's `type number` cast failed on
# string data and the whole table refused to refresh).
_SUM_COL_RE = re.compile(
    r"\bSUM\s*\(\s*(?:'([^']*)'|(\w+))\s*\[\s*([^\]]+)\s*\]\s*\)",
    re.IGNORECASE,
)


def _collect_sum_column_pairs(measures: list) -> set:
    """Return {(table_name, column_name)} for every SUM(<table>[<column>])
    reference found in any measure expression. Both forms of table-name
    quoting are captured: `SUM('My Table'[Sales])` and `SUM(MyTable[Sales])`.
    """
    pairs = set()
    for m in measures:
        for quoted, bare, col in _SUM_COL_RE.findall(m.get("expression", "")):
            tbl = (quoted or bare).strip()
            col = col.strip()
            if tbl and col:
                pairs.add((tbl, col))
    return pairs


def _collect_sum_columns(measures: list) -> set:
    """Backwards-compatible alias: returns just the column-name set. Prefer
    `_collect_sum_column_pairs` in new code so the table context isn't lost.
    """
    return {col for _, col in _collect_sum_column_pairs(measures)}


def _collect_summed_columns_from_visuals(table_name: str, mapped: dict) -> set:
    """Return column names of `table_name` that any visual aggregates with Sum.
    A column rendered with Sum() in any visual must be numeric in TMDL."""
    cols = set()
    for page in mapped.get("pages", []):
        for v in page.get("visuals", []):
            for f in v.get("fields", []):
                if (f.get("table") == table_name
                        and (f.get("aggregation") or "").lower() == "sum"
                        and f.get("column")):
                    cols.add(f["column"])
    return cols


def _tmdl_id(name: str) -> str:
    """Quote a TMDL identifier if it contains characters outside the allowed
    unquoted set. TMDL accepts `[A-Za-z_][A-Za-z0-9_\\-]*` unquoted (dashes
    included — used by auto-date table/partition names like
    `LocalDateTable_<guid>` and `DateTableTemplate_<guid>-<partGuid>`).
    Anything else (spaces, parens, brackets, dots, single quotes, etc.)
    requires single-quote wrapping with embedded quotes doubled.
    """
    if not name:
        return "''"
    if re.match(r'^[A-Za-z_][A-Za-z0-9_\-]*$', name):
        return name
    escaped = name.replace("'", "''")
    return f"'{escaped}'"


_SUMMARIZE_BY = {
    "int64": "sum", "decimal": "sum", "integer": "sum", "number": "sum",
    "float": "sum", "double": "sum",
}

# Roles for which auto-aggregation is suppressed even on numeric columns.
# Real PBI exports set `summarizeBy: none` on PK / FK columns (so they don't
# accidentally Sum() in pivots). `measure` role is NOT here on purpose:
# integer columns the RE tags as `measure` (e.g. fact_premiums
# final_premium_amt(INR)) are legitimately auto-summed in source exports.
# Per-column suppression for percentages/ratios is best handled by the
# upstream format hint, not by the role label.
_NO_SUMMARIZE_ROLES = {"primary_key", "foreign_key", "identifier"}


def _resolve_summarize_by(col: dict, tmdl_type: str,
                          is_relationship_column: bool = False) -> str:
    """Pick the right `summarizeBy:` for a column based on role + type.

    Rules:
      - DAX calculated column → always `none` (author wrote the aggregation).
      - PK / FK / identifier → always `none` (keys never auto-sum).
      - Column used as a relationship endpoint → `none`. The RE often labels
        join columns as `dimension` rather than `foreign_key` (see
        fact_settlements.age — used on both sides of the Age and `Age Group`
        joins but tagged `dimension`). Auto-summing such columns produces
        nonsensical totals like SUM(age) in pivots; real PBI exports always
        set them to `none`.
      - Coordinate column (data_category Latitude / Longitude) → `none`.
        Map visuals require raw coords; aggregating them collapses every row
        to a single Sum and PBI refuses to render the map.
      - Numeric type → `sum` (default per _SUMMARIZE_BY).
      - Anything else → `none`.
    """
    if col.get("expression"):
        return "none"
    if col.get("semantic_role") in _NO_SUMMARIZE_ROLES:
        return "none"
    if is_relationship_column:
        return "none"
    if col.get("data_category") in ("Latitude", "Longitude"):
        return "none"
    return _SUMMARIZE_BY.get(tmdl_type, "none")
_FORMAT_STRING = {
    "int64": "0", "integer": "0",
    "decimal": "#,##0.00", "number": "#,##0.00", "float": "#,##0.00", "double": "#,##0.00",
}
_TMDL_TYPE = {
    "string": "string", "int64": "int64", "integer": "int64",
    # `decimal` is reserved for the TMDL fixed-point Currency type. Generic
    # floating-point columns map to `double` so the TMDL declaration agrees
    # with M's `type number` (also a double). A `decimal` TMDL column whose
    # M says `type number` fails to load any non-currency value.
    "decimal": "decimal", "number": "double", "float": "double", "double": "double",
    "boolean": "boolean", "dateTime": "dateTime", "datetime": "dateTime",
    "date": "dateTime", "time": "dateTime",
}


def _is_field_parameter_table(table: dict) -> bool:
    """Detect a Power BI FIELD PARAMETER table by its canonical structure, so it
    is emitted with the field-parameter machinery (ParameterMetadata,
    relatedColumnDetails, sortByColumn, [Value1]/[Value2]/[Value3] sourceColumns)
    rather than as a plain DAX calculated table. Without that machinery the
    slicer can't switch the bound visuals and Power BI shows the raw
    Value1/Value2/Value3 columns instead of the parameter's fields.

    Canonical shape (exactly what Power BI itself authors): a calculated table
    whose DAX is a row-constructor using NAMEOF(), with three columns named
    `<P>`, `<P> Fields`, `<P> Order`. Purely structural — no input-specific
    names — so it recognises any report's field parameters."""
    if table.get("type") == "fieldParameter":
        return True
    cols = [c.get("name") or "" for c in (table.get("columns") or [])]
    dax = table.get("dax_table_expression") or ""
    if len(cols) == 3 and "NAMEOF" in dax:
        p = cols[0]
        return cols[1] == f"{p} Fields" and cols[2] == f"{p} Order"
    return False


def _tmdl_field_parameter_table(table: dict) -> str:
    """Generate a field parameter table TMDL driven by table["measures"] OR by a
    captured DAX constructor in table["dax_table_expression"] (PowerBI input).

    Each measure entry must have:
      - "name"        : display name shown in the slicer
      - "sourcetable" : the table that owns the measure
      - "expression"  : (optional) the DAX measure name if different from "name"
    """
    tbl_name   = table["name"]
    tbl_id     = _tmdl_id(tbl_name)
    col_name   = tbl_name                       # e.g. "Visual-Parameter"
    fields_col = f"{tbl_name} Fields"
    order_col  = f"{tbl_name} Order"

    tbl_tag    = _new_uuid()
    col_tag    = _new_uuid()
    fields_tag = _new_uuid()
    order_tag  = _new_uuid()
    pbi_id     = uuid.uuid4().hex

    lines = [
        f"table {tbl_id}",
        f"\tlineageTag: {tbl_tag}",
        "",
        f"\tcolumn {_tmdl_id(col_name)}",
        f"\t\tlineageTag: {col_tag}",
        "\t\tsummarizeBy: none",
        "\t\tsourceColumn: [Value1]",
        f"\t\tsortByColumn: {_tmdl_id(order_col)}",
        "",
        "\t\trelatedColumnDetails",
        f"\t\t\tgroupByColumn: {_tmdl_id(fields_col)}",
        "",
        "\t\tannotation SummarizationSetBy = Automatic",
        "",
        f"\tcolumn {_tmdl_id(fields_col)}",
        "\t\tisHidden",
        f"\t\tlineageTag: {fields_tag}",
        "\t\tsummarizeBy: none",
        "\t\tsourceColumn: [Value2]",
        f"\t\tsortByColumn: {_tmdl_id(order_col)}",
        "",
        "\t\textendedProperty ParameterMetadata =",
        '\t\t\t\t{',
        '\t\t\t\t  "version": 3,',
        '\t\t\t\t  "kind": 2',
        '\t\t\t\t}',
        "",
        "\t\tannotation SummarizationSetBy = Automatic",
        "",
        f"\tcolumn {_tmdl_id(order_col)}",
        "\t\tisHidden",
        "\t\tformatString: 0",
        f"\t\tlineageTag: {order_tag}",
        "\t\tsummarizeBy: sum",
        "\t\tsourceColumn: [Value3]",
        "",
        "\t\tannotation SummarizationSetBy = Automatic",
        "",
    ]

    # Partition: prefer the captured field-parameter DAX constructor verbatim
    # (PowerBI input — it already carries the exact ("label", NAMEOF('T'[F]),
    # order) rows the report author defined). Fall back to rebuilding it from
    # `measures` (the Tableau auto-detect path). Either way the COLUMNS above map
    # to the constructor's auto-named [Value1]/[Value2]/[Value3] outputs (NOT
    # [<column name>]), so the display/Fields/Order columns resolve and the
    # slicer can actually switch the bound visuals.
    _fp_dax = (table.get("dax_table_expression") or "").strip()
    measures = table.get("measures", [])
    lines.append(f"\tpartition {tbl_id} = calculated")
    lines.append("\t\tmode: import")
    if _fp_dax:
        lines.append("\t\tsource = ```")
        for _dl in _fp_dax.splitlines():
            lines.append(f"\t\t\t\t{_dl}")
        lines.append("\t\t\t\t```")
    else:
        lines.append("\t\tsource =")
        lines.append("\t\t\t\t{")
        for i, m in enumerate(measures):
            display    = m["name"]
            src_table  = _tmdl_id(m["sourcetable"])
            measure_nm = m.get("expression", m["name"])
            comma      = "," if i < len(measures) - 1 else ""
            lines.append(
                f'\t\t\t\t    ("{display}", NAMEOF({src_table}[{measure_nm}]), {i}){comma}'
            )
        lines.append("\t\t\t\t}")
    lines += [
        "",
        f"\tannotation PBI_Id = {pbi_id}",
        "",
    ]
    tmdl_text = "\n".join(lines)
    if _dbg:
        _dbg.log_field_param_table(tbl_name, len(measures), tmdl_text)
    return tmdl_text


def _infer_calc_source_column(col_name: str, partition_dax: str) -> str:
    """For a calculated-table column, derive the correct TMDL `sourceColumn:` form.

    Two shapes exist in real PBI exports of DAX calculated tables:
      1. `sourceColumn: <SourceTable>[<col_name>]` — column was passed THROUGH
         from a source table (e.g. a SUMMARIZE groupBy column). The lineage
         tells the engine "this calc column shares identity with the source
         column", which is what lets relationships into the calc table bind.
      2. `sourceColumn: [<col_name>]` — column was INTRODUCED by the partition
         expression itself (e.g. the named expressions in SUMMARIZE's
         `"NewName", expr` pairs, or columns added by ADDCOLUMNS).

    We pick (1) iff we can find a reference like `'SourceTable'[col_name]` or
    `SourceTable[col_name]` in the partition DAX; otherwise (2). This works
    for SUMMARIZE, ADDCOLUMNS, GROUPBY, SELECTCOLUMNS, etc. — anything that
    surfaces a column by groupBy/passthrough vs. inline-naming.
    """
    if not partition_dax or not col_name:
        return f"[{col_name}]"
    # Single-quoted table name is the canonical form (`'My Table'[col]`).
    m = re.search(rf"'([^']+)'\s*\[\s*{re.escape(col_name)}\s*\]", partition_dax)
    if m:
        return f"{m.group(1)}[{col_name}]"
    # Unquoted table name is valid when the table name itself has no spaces
    # or special chars (`MyTable[col]`).
    m = re.search(rf"\b([A-Za-z_][A-Za-z0-9_]*)\s*\[\s*{re.escape(col_name)}\s*\]", partition_dax)
    if m:
        return f"{m.group(1)}[{col_name}]"
    return f"[{col_name}]"


_AUTO_DATE_LOCAL_PREFIX    = "LocalDateTable_"
_AUTO_DATE_TEMPLATE_PREFIX = "DateTableTemplate_"

# Auto date/time tables always have these seven columns in this order, with
# fixed DAX expressions, data categories and a sort-by on Month/Quarter.
# (name, expression-or-None-for-Date, dataCategory, sortByColumn, templateId)
_AUTO_DATE_COLUMNS = [
    ("Date",      None,                            "PaddedDateTableDates", None,        None),
    ("Year",      "YEAR([Date])",                  "Years",                None,        "Year"),
    ("MonthNo",   "MONTH([Date])",                 "MonthOfYear",          None,        "MonthNumber"),
    ("Month",     'FORMAT([Date], "MMMM")',        "Months",               "MonthNo",   "Month"),
    ("QuarterNo", "INT(([MonthNo] + 2) / 3)",      "QuarterOfYear",        None,        "QuarterNumber"),
    ("Quarter",   '"Qtr " & [QuarterNo]',          "Quarters",             "QuarterNo", "Quarter"),
    ("Day",       "DAY([Date])",                   "DayOfMonth",           None,        "Day"),
]


def _is_auto_date_local(table_name: str) -> bool:
    return bool(table_name) and table_name.startswith(_AUTO_DATE_LOCAL_PREFIX)


def _is_auto_date_template(table_name: str) -> bool:
    return bool(table_name) and table_name.startswith(_AUTO_DATE_TEMPLATE_PREFIX)


def _is_auto_date_table(table_name: str) -> bool:
    return _is_auto_date_local(table_name) or _is_auto_date_template(table_name)


def _tmdl_auto_date_table(table: dict) -> str:
    """Emit TMDL for a hidden LocalDateTable_<guid> or DateTableTemplate_<guid>.

    Power BI Desktop refuses to bind relationships to these tables unless the
    Date column is declared with `isNameInferred` + `sourceColumn: [Date]`
    (i.e. as a calculated column drawn from the Calendar(...) partition
    output) and the helper columns are emitted as DAX expressions.
    """
    tbl_name = table["name"]
    tbl_id = _tmdl_id(tbl_name)
    tbl_tag = _new_uuid()
    is_template = _is_auto_date_template(tbl_name)

    partition_dax = (table.get("dax_table_expression") or "").strip()
    if not partition_dax:
        partition_dax = "Calendar(Date(2015,1,1), Date(2015,1,1))"

    lines = [f"table {tbl_id}"]
    if is_template:
        lines.append("\tisPrivate")
    else:
        lines.append("\tisHidden")
        lines.append("\tshowAsVariationsOnly")
    lines.append(f"\tlineageTag: {tbl_tag}")
    lines.append("")

    for cname, expr, data_cat, sort_by, tmpl_id in _AUTO_DATE_COLUMNS:
        col_tag = _new_uuid()
        if cname == "Date":
            lines.append("\tcolumn Date")
            lines.append("\t\tisHidden")
            lines.append(f"\t\tlineageTag: {col_tag}")
            lines.append(f"\t\tdataCategory: {data_cat}")
            lines.append("\t\tsummarizeBy: none")
            lines.append("\t\tisNameInferred")
            lines.append("\t\tsourceColumn: [Date]")
            lines.append("")
            lines.append("\t\tannotation SummarizationSetBy = User")
            lines.append("")
        else:
            lines.append(f"\tcolumn {cname} = {expr}")
            lines.append("\t\tisHidden")
            lines.append(f"\t\tlineageTag: {col_tag}")
            lines.append(f"\t\tdataCategory: {data_cat}")
            lines.append("\t\tsummarizeBy: none")
            if sort_by:
                lines.append(f"\t\tsortByColumn: {sort_by}")
            lines.append("")
            lines.append("\t\tannotation SummarizationSetBy = User")
            lines.append("")
            if tmpl_id:
                lines.append(f"\t\tannotation TemplateId = {tmpl_id}")
                lines.append("")

    # Hierarchy: Year -> Quarter -> Month -> Day. Always emitted; the JSON may
    # also declare it via `hierarchies[]` but the writer can synthesise it
    # since these tables have a fixed shape.
    hier_tag = _new_uuid()
    lines.append("\thierarchy 'Date Hierarchy'")
    lines.append(f"\t\tlineageTag: {hier_tag}")
    lines.append("")
    for lvl in ("Year", "Quarter", "Month", "Day"):
        lvl_tag = _new_uuid()
        lines.append(f"\t\tlevel {lvl}")
        lines.append(f"\t\t\tlineageTag: {lvl_tag}")
        lines.append(f"\t\t\tcolumn: {lvl}")
        lines.append("")
    lines.append("\t\tannotation TemplateId = DateHierarchy")
    lines.append("")

    # Partition — calculated, with the Calendar() DAX as source. Build the
    # composite name (table + GUID suffix) FIRST, then quote it as one unit.
    # Otherwise a quoted table id followed by a raw `-<guid>` suffix produces
    # invalid TMDL like `'Table'-<guid>`, which the parser rejects with
    # "single-quote character in name must be escaped".
    part_id = _new_uuid()
    part_name = _tmdl_id(f"{tbl_name}-{part_id}")
    indented_dax = "\n".join(f"\t\t\t\t{ln}" for ln in partition_dax.splitlines())
    lines.append(f"\tpartition {part_name} = calculated")
    lines.append("\t\tmode: import")
    lines.append("\t\tsource = ```")
    lines.append(indented_dax)
    lines.append("\t\t\t\t```")
    lines.append("")

    if is_template:
        lines.append("\tannotation __PBI_TemplateDateTable = true")
        lines.append("")
        lines.append("\tannotation DefaultItem = DateHierarchy")
        lines.append("")
    else:
        lines.append("\tannotation __PBI_LocalDateTable = true")
        lines.append("")

    return "\n".join(lines)


# Power Query M source functions that read EXTERNAL data (a file, database,
# web service, …). An M expression that uses NONE of these carries its own data
# — e.g. an "Enter Data" / inline table whose rows are embedded as
# `Table.FromRows(Json.Document(Binary.Decompress(Binary.FromText("…",
# BinaryEncoding.Base64), Compression.Deflate)))`. Such a table has no backing
# file, so its M must be emitted VERBATIM or the user's manually-entered rows
# are lost. `Json.Document`/`Binary.Decompress` are internal (they parse the
# embedded blob), so they are NOT external connectors.
_M_EXTERNAL_CONNECTORS = (
    "File.Contents", "Csv.Document", "Excel.Workbook", "Web.Contents",
    "Sql.Database", "Odbc.", "OData.", "SharePoint.", "Folder.Files",
    "AzureStorage.", "Snowflake.", "PostgreSQL.", "MySql.", "MySQL.",
    "Oracle.", "Databricks.", "Xml.Tables", "Json.Document(Web",
)


def _is_self_contained_m(m: str | None) -> bool:
    """True when an M expression embeds its own data (an "Enter Data" / inline
    table built with `Table.FromRows(...)`) and reads no external source — so the
    writer must emit it verbatim instead of substituting a CSV partition."""
    if not m:
        return False
    s = m.strip()
    if not s.lower().startswith("let") or "Table.FromRows" not in s:
        return False
    return not any(conn in s for conn in _M_EXTERNAL_CONNECTORS)


def _m_undefined_query_refs(m: str, known_query_names: set) -> set:
    """Return the `#"..."` query references in an M expression that are neither a
    LOCAL `let` step nor a known model query (table). These are unresolved — e.g.
    an auto-generated "combine files" helper (`Transform File (2)`, `Sample File
    (2)`) that the extractor could not recover — and Power BI refuses to load the
    WHOLE model when one query references a missing one."""
    if not m:
        return set()
    # A QUERY reference is `#"Name"` used as a value. EXCLUDE `[#"Name"]` — that
    # is a COLUMN / field access (e.g. `each [#"Source.Name - Copy.1"]`), not a
    # query, so the negative lookbehind for `[` avoids false positives.
    refs = set(re.findall(r'(?<!\[)#"([^"]+)"', m))
    local = set(re.findall(r'#"([^"]+)"\s*=', m))      # LHS of a let step
    return {r for r in (refs - local) if r not in known_query_names}


_M_PLACEHOLDER_TYPE = {
    "string": "text", "int64": "Int64.Type", "integer": "Int64.Type",
    "double": "number", "number": "number", "float": "number",
    "decimal": "number", "currency": "number", "boolean": "logical",
    "dateTime": "datetime", "datetime": "datetime", "date": "date", "time": "time",
}


def _placeholder_table_m(columns: list) -> str:
    """An empty table with the declared schema. Used when a table's real M
    references a query we couldn't recover, so the model still LOADS and the
    table's columns / relationships / visual bindings stay intact (only its data
    is empty until the user restores the source)."""
    cols = columns or [{"name": "Column1", "dataType": "string"}]
    fields = ", ".join(
        f'#"{c.get("name", "Column1")}" = '
        f'{_M_PLACEHOLDER_TYPE.get((c.get("dataType") or "string").lower(), "text")}'
        for c in cols
    )
    return f"let\n    Source = #table(type table [{fields}], {{}})\nin\n    Source"


def _tmdl_table(table: dict, source: str, mapped: dict = None,
                rel_guid_by_input_id: dict | None = None,
                rel_guid_by_endpoint: dict | None = None,
                rel_columns: set | None = None) -> str:
    if _is_field_parameter_table(table):
        return _tmdl_field_parameter_table(table)

    if _is_auto_date_table(table.get("name", "")):
        return _tmdl_auto_date_table(table)

    tbl_name = table["name"]
    tbl_id = _tmdl_id(tbl_name)
    tbl_tag = _new_uuid()

    # Columns that appear in SUM() inside a measure must be numeric. Keyed
    # by (table, column) pair (not just column name) so a measure like
    # SUM(other_table[Description]) doesn't contaminate this table's own
    # string `Description` column.
    sum_pairs = set()
    if mapped is not None:
        for _t in mapped.get("tables", []):
            sum_pairs |= _collect_sum_column_pairs(_t.get("measures", []))
    else:
        sum_pairs = _collect_sum_column_pairs(table.get("measures", []))
    # Same applies to columns aggregated with Sum in any visual field.
    # `_collect_summed_columns_from_visuals` already filters by table_name
    # so it's safe to read as a plain column-name set scoped to this table.
    visual_sum_cols = (_collect_summed_columns_from_visuals(tbl_name, mapped)
                       if mapped is not None else set())

    # Columns whose semantic_role flags them as text-by-design (keys, IDs,
    # plain dimensions). The SUM-upgrade heuristic exists to recover RE
    # under-typing of numeric columns, but it also fires on these — and when
    # an upstream DAX translator wraps a text column in SUM(...) for a
    # row-level Tableau calc (e.g.
    #   `IF [Description]="X" THEN "Y" ELSE [Description] END`
    # → `IF(SUM('tbl_sales'[Description])="X", ...)` ) the heuristic
    # rewrites the column to `double` and the M cast to `type number`,
    # which then errors at refresh on values like "Indoor Pet Camera".
    # `measure` is intentionally NOT here — that's the legitimate target.
    _TEXT_BY_DESIGN_ROLES = {"primary_key", "foreign_key", "identifier", "dimension"}

    def _is_summed_string(col_name: str, col_meta: dict | None = None) -> bool:
        """True iff this column is referenced in a SUM() that targets
        THIS table specifically, or aggregated as Sum in a visual on THIS
        table. Pair-keyed lookup prevents cross-table contamination."""
        if col_meta and col_meta.get("semantic_role") in _TEXT_BY_DESIGN_ROLES:
            return False
        return (tbl_name, col_name) in sum_pairs or col_name in visual_sum_cols

    # Build effective column list with SUM-upgrade applied so M-query type matches.
    effective_cols = []
    for c in table.get("columns", []):
        ec = dict(c)
        if ec.get("dataType", "string").lower() == "string" and _is_summed_string(ec.get("name", ""), ec):
            ec["dataType"] = "double"
        effective_cols.append(ec)

    # Partition kind: DAX calculated table > extractor-provided M > CSV-seeded M.
    is_calculated = (table.get("table_type") == "calculated"
                     and bool(table.get("dax_table_expression")))
    dax_table_expr = (table.get("dax_table_expression") or "").strip()
    pq_expr = (table.get("powerquery_expression") or "").strip()

    csv_path = None
    if is_calculated:
        m_expr = None  # not used; calculated tables emit a different partition block
    else:
        # Partition source priority for IMPORTED tables:
        #   1. SharePoint CSV — WINS. The table's CSV is loaded by file name
        #      from the shared SharePoint site (see _csv_m_query). Every team
        #      member who opens the PBIP can refresh it with their own org
        #      account, so there is no dependence on a local `sources/` copy
        #      or on the original .pbix author's absolute path.
        #      `_find_csv_file` is still consulted ONLY to recover the exact
        #      CSV file name when a local copy happens to be present; if it
        #      isn't, the table name is used as the file name instead.
        #   2. RE-provided M expression (`let ... in ...`) — used only for
        #      tables the RE captured with a non-CSV / custom source.
        #
        # Self-join / data-source alias: when `source_derived_from_table_id` is
        # set, this imported table is the SAME physical source as the named base
        # table (a Tableau self-join uses one CSV twice under different names).
        # Resolve the CSV from the BASE name so the alias loads `<base>.csv`
        # instead of a non-existent `<alias>.csv` (which fails refresh with
        # "the key didn't match any rows in the table"). The alias keeps its own
        # real physical columns, so its self-join relationship still binds.
        csv_lookup_name = (table.get("source_derived_from_table_id") or "").strip() or tbl_name
        if _is_self_contained_m(pq_expr):
            # "Enter Data" / inline table — the rows are embedded in the M
            # itself. Emit it VERBATIM, ahead of any CSV lookup, so a
            # coincidentally-named CSV can't shadow the manually-entered data and
            # the table loads with no `sources/` file present.
            m_expr = pq_expr
        else:
            csv_path = _find_csv_file(csv_lookup_name)
            if csv_path:
                m_expr = _csv_m_query(csv_path, effective_cols)
            elif pq_expr and pq_expr.lstrip().lower().startswith("let"):
                m_expr = pq_expr
            else:
                m_expr = _csv_m_query(csv_lookup_name, effective_cols)

        # Guard: if the chosen M references a query that is neither a model table
        # nor defined locally — e.g. an auto-generated "combine files" helper
        # (`Transform File (2)`, `Sample File (2)`) the extractor couldn't recover
        # — the table, and the WHOLE model, fails to load ("the import …  matches
        # no exports"). Fall back to an empty table with the same schema so the
        # report still OPENS; columns, relationships and visual bindings are kept.
        _known_q = {t.get("name") for t in (mapped.get("tables") if mapped else [table])}
        _undef = _m_undefined_query_refs(m_expr, _known_q)
        if _undef:
            print(f"[writer] table {tbl_name!r}: M references undefined queries "
                  f"{sorted(_undef)} (unrecoverable helper queries) — emitting an "
                  f"empty-schema placeholder so the model still loads.")
            m_expr = _placeholder_table_m(effective_cols)

    lines = [f"table {tbl_id}", f"\tlineageTag: {tbl_tag}", ""]

    def _variation_lines(col, cname):
        """Emit `variation Variation { isDefault; relationship: <guid>;
        defaultHierarchy: <table>.<hier> }` blocks for a column with
        `variations[]`. Returns a list of TMDL lines (empty if no resolvable
        variations). Used by both the DAX-calc-column branch and the
        physical-column branch — variations exist on EITHER kind of column
        whenever the source PBI had an auto-date variation enabled on that
        column (e.g. `Tenure Date = EDATE(...)` is a DAX calc column with an
        auto-date variation). Skipping variations on DAX columns leaves
        their LocalDateTable orphaned, and PBI then refuses the model with
        PFE_TM_SHOW_AS_VARIATION_ONLY_TABLE_NOT_A_VARIATION_TARGET.
        """
        out: list[str] = []
        for var in (col.get("variations") or []):
            if not isinstance(var, dict):
                continue
            dh = var.get("default_hierarchy")
            if isinstance(dh, str):
                if "." not in dh:
                    continue
                dh_tbl, dh_hier = dh.split(".", 1)
            elif isinstance(dh, dict):
                dh_tbl, dh_hier = dh.get("table", ""), dh.get("hierarchy", "")
            else:
                continue
            if not dh_tbl or not dh_hier:
                continue
            # Resolve the relationship's TMDL name. Primary lookup: the
            # variation's relationship_id. Fallback (when mapper dedup
            # dropped the exact-id row but kept its sibling pointing at the
            # same endpoint): match by (this column) → (variation target
            # table, "Date"), in either direction.
            rel_input_id = var.get("relationship_id")
            rel_guid = (rel_guid_by_input_id or {}).get(rel_input_id) if rel_input_id else None
            if not rel_guid and rel_guid_by_endpoint:
                for ep in ((tbl_name, cname, dh_tbl, "Date"),
                           (dh_tbl, "Date", tbl_name, cname)):
                    if ep in rel_guid_by_endpoint:
                        rel_guid = rel_guid_by_endpoint[ep]
                        break
            if not rel_guid:
                continue
            out.append("")
            out.append(f"\t\tvariation {_tmdl_id(var.get('name') or 'Variation')}")
            if var.get("is_default", True):
                out.append("\t\t\tisDefault")
            out.append(f"\t\t\trelationship: {rel_guid}")
            out.append(f"\t\t\tdefaultHierarchy: {_tmdl_id(dh_tbl)}.{_tmdl_id(dh_hier)}")
        return out

    for col in table.get("columns", []):
        cname = col["name"]
        col_id = _tmdl_id(cname)
        raw_type = col.get("dataType", "string")
        # Upgrade string columns referenced in SUM() measures to double.
        # `_is_summed_string` keys by (table, column) so the upgrade only
        # fires when THIS table's column is the actual SUM target.
        if raw_type.lower() == "string" and _is_summed_string(cname, col):
            raw_type = "double"
        tmdl_type = _TMDL_TYPE.get(raw_type.lower(), "string")
        is_rel_col = bool(rel_columns and (tbl_name, cname) in rel_columns)
        summarize = _resolve_summarize_by(col, tmdl_type, is_rel_col)
        fmt = col.get("formatString", "") or _FORMAT_STRING.get(tmdl_type, "")
        col_tag = _new_uuid()
        dax_expr = col.get("expression", "")

        if dax_expr:
            # DAX calculated column — no dataType or sourceColumn; type is inferred by PBI
            expr_stripped = dax_expr.strip()
            if "\n" in expr_stripped:
                lines.append(f"\tcolumn {col_id} = ```")
                for expr_line in expr_stripped.splitlines():
                    lines.append(f"\t\t\t\t{expr_line}")
                lines.append(f"\t\t\t\t```")
            else:
                lines.append(f"\tcolumn {col_id} = {expr_stripped}")
            if fmt:
                lines.append(f"\t\tformatString: {fmt}")
            lines.append(f"\t\tlineageTag: {col_tag}")
            if col.get("data_category"):
                lines.append(f"\t\tdataCategory: {col['data_category']}")
            lines.append(f"\t\tsummarizeBy: {summarize}")
            # Variations live on DAX calc columns too (e.g. a calculated
            # date column like `Tenure Date = EDATE(...)` with an auto-date
            # variation). Emit the same block as the physical-column branch.
            lines.extend(_variation_lines(col, cname))
            lines.append("")
            lines.append(f"\t\tannotation SummarizationSetBy = Automatic")
            lines.append("")
        else:
            lines.append(f"\tcolumn {col_id}")
            # `dataType:` is OMITTED for calculated-table columns. The engine
            # infers the type from the partition's DAX output, and emitting
            # `dataType:` ALONGSIDE `isNameInferred` is a conflicting
            # declaration that causes the engine to silently drop the column.
            # Any relationship endpoint pointing at a dropped column then
            # fails with PFE_TM_RELATIONSHIP_END_COLUMN_INVALID at model load.
            if not is_calculated:
                lines.append(f"\t\tdataType: {tmdl_type}")
            if fmt:
                lines.append(f"\t\tformatString: {fmt}")
            lines.append(f"\t\tlineageTag: {col_tag}")
            if col.get("data_category"):
                lines.append(f"\t\tdataCategory: {col['data_category']}")
            lines.append(f"\t\tsummarizeBy: {summarize}")
            if is_calculated:
                lines.append("\t\tisNameInferred")
                # `sourceColumn:` shape depends on whether the column was
                # passed through from a source table (groupBy → needs lineage)
                # or introduced inline by the partition (bracketed name). See
                # _infer_calc_source_column for the rule.
                src_col = _infer_calc_source_column(cname, dax_table_expr)
                lines.append(f"\t\tsourceColumn: {src_col}")
            else:
                lines.append(f"\t\tsourceColumn: {cname}")
            # Auto date/time variation — emit `variation Variation { … }`
            # referencing the hidden relationship's TMDL name (a GUID
            # pre-assigned in _write_semantic_model) and the LocalDateTable's
            # Date Hierarchy. Skipped if the variation can't resolve to a
            # known relationship — better silent skip than dangling reference.
            for var in (col.get("variations") or []):
                if not isinstance(var, dict):
                    continue
                dh = var.get("default_hierarchy")
                if isinstance(dh, str):
                    if "." not in dh:
                        continue
                    dh_tbl, dh_hier = dh.split(".", 1)
                elif isinstance(dh, dict):
                    dh_tbl, dh_hier = dh.get("table", ""), dh.get("hierarchy", "")
                else:
                    continue
                if not dh_tbl or not dh_hier:
                    continue
                # Resolve the relationship's TMDL name. Primary lookup: the
                # variation's relationship_id. Fallback (when mapper dedup
                # dropped the exact-id row but kept its sibling pointing at
                # the same endpoint): match by (this column) → (variation
                # target table, "Date"), in either direction.
                rel_input_id = var.get("relationship_id")
                rel_guid = (rel_guid_by_input_id or {}).get(rel_input_id) if rel_input_id else None
                if not rel_guid and rel_guid_by_endpoint:
                    for ep in ((tbl_name, cname, dh_tbl, "Date"),
                               (dh_tbl, "Date", tbl_name, cname)):
                        if ep in rel_guid_by_endpoint:
                            rel_guid = rel_guid_by_endpoint[ep]
                            break
                if not rel_guid:
                    continue
                lines.append("")
                lines.append(f"\t\tvariation {_tmdl_id(var.get('name') or 'Variation')}")
                if var.get("is_default", True):
                    lines.append("\t\t\tisDefault")
                lines.append(f"\t\t\trelationship: {rel_guid}")
                lines.append(f"\t\t\tdefaultHierarchy: {_tmdl_id(dh_tbl)}.{_tmdl_id(dh_hier)}")
            lines.append("")
            lines.append(f"\t\tannotation SummarizationSetBy = Automatic")
            lines.append("")

    # Collision guard: TMDL rejects (1) a measure whose name matches a column
    # on the same table (PFE_XL_MEASURE_COLUMN_ALREADY_EXIST) and (2) two
    # measures with the same name on the same table. Skip duplicates and
    # measure/column collisions silently — the model still loads, and visuals
    # referencing the dropped name fail loudly rather than blocking the whole
    # report. Model-wide measure-name uniqueness is enforced separately by
    # the caller (it spans tables).
    _col_names_lc = {c["name"].lower() for c in table.get("columns", [])}
    _seen_measure_names_lc: set[str] = set()
    for meas in table.get("measures", []):
        mname = meas["name"]
        mlc = mname.lower()
        if mlc in _col_names_lc:
            if _dbg:
                _dbg.log_dax(table["name"], mname, meas.get("expression", ""),
                             "SKIPPED: measure name collides with a column", "")
            continue
        if mlc in _seen_measure_names_lc:
            if _dbg:
                _dbg.log_dax(table["name"], mname, meas.get("expression", ""),
                             "SKIPPED: duplicate measure on table", "")
            continue
        _seen_measure_names_lc.add(mlc)

        meas_id = _tmdl_id(mname)
        expr = meas.get("expression", "")
        fmt = meas.get("formatString", "")
        m_tag = _new_uuid()

        expr_stripped = expr.strip()
        if "\n" in expr_stripped:
            lines.append(f"\tmeasure {meas_id} = ```")
            for expr_line in expr_stripped.splitlines():
                lines.append(f"\t\t\t\t{expr_line}")
            lines.append(f"\t\t\t\t```")
        else:
            lines.append(f"\tmeasure {meas_id} = {expr_stripped}")
        if fmt:
            lines.append(f"\t\tformatString: {fmt}")
        lines.append(f"\t\tlineageTag: {m_tag}")
        lines.append("")

    # User-defined hierarchies — emit each as a TMDL `hierarchy <Name>` block
    # with one `level <Name>` per level. The auto-date path emits its own
    # hardcoded Date Hierarchy in _tmdl_auto_date_table; this regular path
    # honors whatever hierarchies the input JSON declares on imported /
    # dimension tables (e.g. Geography → Country > State > City).
    # Without this, visuals binding to `<table>.<hierarchy>.<level>` paths
    # find no hierarchy to resolve and paint blank.
    #
    # Driven entirely by `table["hierarchies"]` shape from the input — no
    # hardcoded names, no special-casing. Empty/malformed entries skipped
    # silently; unknown column refs are passed through so PBI surfaces the
    # error at load (better than silent drop).
    for hier in (table.get("hierarchies") or []):
        if not isinstance(hier, dict):
            continue
        hname = hier.get("name") or ""
        levels = hier.get("levels") or []
        if not hname or not levels:
            continue
        hier_tag = _new_uuid()
        lines.append(f"\thierarchy {_tmdl_id(hname)}")
        lines.append(f"\t\tlineageTag: {hier_tag}")
        lines.append("")
        for lvl in levels:
            if not isinstance(lvl, dict):
                continue
            lname = lvl.get("name") or ""
            lcol  = lvl.get("column") or ""
            if not lname or not lcol:
                continue
            lvl_tag = _new_uuid()
            lines.append(f"\t\tlevel {_tmdl_id(lname)}")
            lines.append(f"\t\t\tlineageTag: {lvl_tag}")
            lines.append(f"\t\t\tcolumn: {_tmdl_id(lcol)}")
            lines.append("")

    # Partition — DAX calculated table vs. Power Query (M) import.
    if is_calculated:
        indented_dax = "\n".join(f"\t\t\t\t{ln}" for ln in dax_table_expr.splitlines())
        lines.append(f"\tpartition {tbl_id} = calculated")
        lines.append(f"\t\tmode: import")
        lines.append(f"\t\tsource = ```")
        lines.append(indented_dax)
        lines.append(f"\t\t\t\t```")
        lines.append("")
        lines.append(f"\tannotation PBI_ResultType = Table")
        lines.append("")
    else:
        indented_m = "\n".join(f"\t\t\t\t{ln}" for ln in m_expr.splitlines())
        lines.append(f"\tpartition {tbl_id} = m")
        lines.append(f"\t\tmode: import")
        lines.append(f"\t\tsource =")
        lines.append(indented_m)
        lines.append("")
        lines.append(f"\tannotation PBI_NavigationStepName = Navigation")
        lines.append("")
        lines.append(f"\tannotation PBI_ResultType = Table")
        lines.append("")

    tmdl_text = "\n".join(lines)
    if _dbg:
        _dbg.log_tmdl_table(
            tbl_name,
            len(table.get("columns", [])),
            len(table.get("measures", [])),
            bool(csv_path),
            tmdl_text,
        )
    return tmdl_text


def _tmdl_relationships_file(relationships: list, source: str = "tableau",
                              rel_guid_by_input_id: dict | None = None,
                              tables: list | None = None) -> str:
    """Write all relationships to a standalone relationships.tmdl file.

    Emits in the ground-truth pattern: JSON's from/to direction is preserved
    verbatim, `fromCardinality: one` only when the from column is actually
    unique (PK or distinct_count_high), and `crossFilteringBehavior` is only
    emitted when bothDirections (oneDirection is PBI's default).

    `tables` is needed to look up column metadata (semantic_role,
    distinct_count_high) to decide when fromCardinality emission is safe.

    `rel_guid_by_input_id` lets the caller pre-assign relationship GUIDs so
    that variation blocks on date columns can reference them by exact match.
    """
    # Column metadata index for FROM-side uniqueness checks.
    _columns_idx_writer = {}
    _tables_idx_writer = {}
    for _t in (tables or []):
        _tables_idx_writer[_t['name']] = _t
        for _c in _t.get('columns', []):
            _columns_idx_writer[(_t['name'], _c['name'])] = _c

    def _is_unique_from_side(tbl_name: str, col_name: str) -> bool:
        """True iff the from-side column is provably unique, justifying
        `fromCardinality: one`. Real PBI exports emit fromCardinality:one
        exactly when the from-side column carries unique values (either a
        declared primary key, or a calc-table groupBy column whose values
        are inherently distinct because SUMMARIZE/GROUPBY produced them).
        Without this, bidirectional relationships sourced from a unique
        column round-trip as M:1 with no cardinality hint, which PBI then
        infers as M:M — producing wrong filter behaviour at runtime.
        """
        col_meta = _columns_idx_writer.get((tbl_name, col_name), {})
        if col_meta.get("semantic_role") == "primary_key":
            return True
        tbl_meta = _tables_idx_writer.get(tbl_name, {})
        if tbl_meta.get("table_type") == "calculated":
            # Calc-table column whose sourceColumn carries source lineage
            # (`SourceTable[col]`) was passed through from a SUMMARIZE-style
            # groupBy — those values are distinct by construction.
            dax = tbl_meta.get("dax_table_expression") or ""
            src = _infer_calc_source_column(col_name, dax)
            if src and not src.startswith("["):
                return True
        return False

    lines = []
    # Dedupe by (from_table, from_col, to_table, to_col); Power BI rejects
    # duplicate endpoint pairs at model-load time.
    seen_pairs = set()
    for rel in relationships:
        if not all([rel.get('fromTable'), rel.get('fromColumn'), rel.get('toTable'), rel.get('toColumn')]):
            continue
        endpoint = (rel['fromTable'], rel['fromColumn'], rel['toTable'], rel['toColumn'])
        endpoint_rev = (rel['toTable'], rel['toColumn'], rel['fromTable'], rel['fromColumn'])
        if endpoint in seen_pairs or endpoint_rev in seen_pairs:
            continue
        seen_pairs.add(endpoint)

        cardinality = (rel.get("cardinality_resolved") or "").lower()
        cross = rel.get("crossFilteringBehavior") or "bothDirections"

        # Validate the declared cardinality against the actual data. PBI
        # rejects the model at load when the "one" side has duplicate values
        # in the source CSV. Downgrade to many_to_many so the model still
        # loads — the RE's cardinality is sometimes wrong (e.g. a state
        # mapping table with multiple regions per state inferred as M:1).
        # Calculated/aliased tables don't have a backing CSV and the helper
        # returns False for them, so they fall through to the declared value.
        if cardinality in ("many_to_one", "one_to_many"):
            if cardinality == "many_to_one":
                one_tbl, one_col = rel.get("toTable", ""), rel.get("toColumn", "")
            else:
                one_tbl, one_col = rel.get("fromTable", ""), rel.get("fromColumn", "")
            if one_tbl and one_col and _one_side_has_duplicates(one_tbl, one_col):
                cardinality = "many_to_many"

        # TMDL relationship convention (enforced by the AS engine, error
        # PFE_TM_RELATIONSHIP_ONE_TO_MANY): `fromColumn` MUST be the MANY side
        # and `toColumn` MUST be the ONE side. `fromCardinality: one` is only
        # accepted when the relationship is genuinely 1:1 (both sides unique).
        # Any other configuration ("From end cardinality must always be set to
        # Many, unless the relationship is One-To-One") is rejected at load.
        #
        # Therefore, normalise from the input's cardinality:
        #   * many_to_one  → keep input.from as from (already many side).
        #   * one_to_many  → FLIP. Input's from is the one side; swap so the
        #                    many side (input.to) becomes from.
        #   * one_to_one   → keep direction, emit `fromCardinality: one` (the
        #                    only legal use of that keyword).
        #   * many_to_many → keep direction, emit explicit many/many.
        #
        # Auto-date hidden links keep the input direction and emit no
        # explicit cardinality — the variation machinery handles their
        # semantics, and `joinOnDateBehavior: datePartOnly` would conflict
        # with `fromCardinality: one`.
        is_auto_date_link = (rel.get("is_auto_generated")
                             or _is_auto_date_table(rel.get("toTable", ""))
                             or _is_auto_date_table(rel.get("fromTable", "")))

        if cardinality == "one_to_many":
            # Flip: emit (input.to → input.from) as the M:1 form.
            many = (rel['toTable'],   rel['toColumn'])
            one  = (rel['fromTable'], rel['fromColumn'])
            from_card = to_card = None
        elif cardinality == "one_to_one":
            many = (rel['fromTable'], rel['fromColumn'])
            one  = (rel['toTable'],   rel['toColumn'])
            from_card, to_card = "one", "one"
        elif cardinality == "many_to_many":
            many = (rel['fromTable'], rel['fromColumn'])
            one  = (rel['toTable'],   rel['toColumn'])
            from_card, to_card = "many", "many"
        else:
            # many_to_one (or unknown — defaults to M:1).
            many = (rel['fromTable'], rel['fromColumn'])
            one  = (rel['toTable'],   rel['toColumn'])
            from_card = to_card = None

        many_side = f"{_tmdl_id(many[0])}.{_tmdl_id(many[1])}"
        one_side  = f"{_tmdl_id(one[0])}.{_tmdl_id(one[1])}"

        # Prefer a caller-provided GUID (keyed by the input relationship id)
        # so variation blocks on date columns can reference this exact name.
        input_id = rel.get("input_id")
        rel_name = (rel_guid_by_input_id or {}).get(input_id) if input_id else None
        if not rel_name:
            rel_name = _new_uuid()
        lines.append(f"relationship {rel_name}")
        # Auto-date hidden links need joinOnDateBehavior emitted first.
        is_auto_date_link = (rel.get("is_auto_generated")
                             or _is_auto_date_table(rel.get("toTable", ""))
                             or _is_auto_date_table(rel.get("fromTable", "")))
        join_behavior = rel.get("joinOnDateBehavior") or ("datePartOnly" if is_auto_date_link else None)
        if join_behavior:
            lines.append(f"\tjoinOnDateBehavior: {join_behavior}")
        # Only emit `crossFilteringBehavior` when bothDirections —
        # oneDirection is PBI's default and ground-truth PBIP files omit
        # the line entirely in that case. Emitting `oneDirection` explicitly
        # was making our relationships diverge from the GT pattern.
        if cross == "bothDirections":
            lines.append(f"\tcrossFilteringBehavior: bothDirections")
        if from_card:
            lines.append(f"\tfromCardinality: {from_card}")
        if to_card:
            lines.append(f"\ttoCardinality: {to_card}")
        lines.append(f"\tfromColumn: {many_side}")
        lines.append(f"\ttoColumn: {one_side}")
        if not rel.get('active', True):
            lines.append(f"\tisActive: false")
        lines.append("")
    tmdl_text = "\n".join(lines)
    if _dbg:
        _dbg.log_relationships_tmdl(len(relationships), tmdl_text)
    return tmdl_text


def _tmdl_model(table_names: list, relationships: list = None,
                has_auto_date_tables: bool = False, role_names: list = None) -> str:
    order_list = json.dumps(table_names, ensure_ascii=False)
    lines = [
        "model Model",
        "\tculture: en-US",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        # Locale used for query rewrites (date formats, decimal separator).
        # Real PBI exports always carry this; without it M parses dates
        # using the engine's default culture which may diverge from the
        # CSV's actual format. Defaulting to en-US is the safe value when
        # the input doesn't specify a different locale.
        "\tsourceQueryCulture: en-US",
        "\tdataAccessOptions",
        "\t\tlegacyRedirects",
        "\t\treturnErrorValuesAsNull",
        "",
        f"annotation PBI_QueryOrder = {order_list}",
        "",
    ]
    # Required when the model contains LocalDateTable_/DateTableTemplate_
    # tables: this annotation tells the engine the auto-date plumbing is
    # active, which is what lights up the variation blocks on base date
    # columns. Without it, variation references resolve to nothing and any
    # visual binding to `<col>.Variation.Date Hierarchy.<level>` paints blank
    # — even though every TMDL piece is present.
    if has_auto_date_tables:
        lines.append("annotation __PBI_TimeIntelligenceEnabled = 1")
        lines.append("")
    # Marks the model as authored in DevMode (PBIP). Real exports always
    # carry it; some downstream tools refuse to round-trip a PBIP that
    # lacks it.
    lines.append('annotation PBI_ProTooling = ["DevMode"]')
    lines.append("")
    for name in table_names:
        lines.append(f"ref table {_tmdl_id(name)}")
    lines.append("")
    lines.append("ref cultureInfo en-US")
    lines.append("")
    # Row-Level Security roles are children of the model — declare a ref for each
    # so the engine loads roles/<name>.tmdl. Membership only; order is cosmetic.
    for rname in (role_names or []):
        lines.append(f"ref role {_tmdl_id(rname)}")
    if role_names:
        lines.append("")
    return "\n".join(lines)


def _tmdl_role(role: dict) -> str:
    """Render one Row-Level Security role as TMDL.

    The filter expression is emitted VERBATIM — RLS DAX is security-critical and
    must never be paraphrased or re-derived. Single-line filters go inline;
    multi-line filters use the same triple-backtick block the column/measure
    expression emitters use (property at 1 tab, body + closing fence at 4 tabs).
    """
    name = role.get("name") or "Role"
    lines = [
        f"role {_tmdl_id(name)}",
        "\tmodelPermission: read",
        "",
    ]
    for perm in (role.get("table_permissions") or []):
        table = perm.get("table") or ""
        expr = (perm.get("filter_expression") or "").strip()
        if not table or not expr:
            continue
        ref = _tmdl_id(table)
        if "\n" in expr:
            lines.append(f"\ttablePermission {ref} = ```")
            for ln in expr.split("\n"):
                lines.append(f"\t\t\t\t{ln}")
            lines.append("\t\t\t\t```")
        else:
            lines.append(f"\ttablePermission {ref} = {expr}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _tmdl_database() -> str:
    return "database\n\tcompatibilityLevel: 1600\n"


def _tmdl_culture() -> str:
    return (
        "cultureInfo en-US\n"
        "\n"
        "\tlinguisticMetadata =\n"
        "\t\t\t{\n"
        '\t\t\t  "Version": "1.0.0",\n'
        '\t\t\t  "Language": "en-US"\n'
        "\t\t\t}\n"
        "\t\tcontentType: json\n"
    )


def _dedupe_model_names(tables: list) -> None:
    """In-place: enforce three TMDL uniqueness rules across the model.

    1. Table names unique across tables[].
    2. Column names unique within each table.
    3. Measure names unique across the whole model (TMDL addresses measures
       as `[Name]` without a table prefix, so a duplicate breaks loading).

    Duplicates are dropped (first occurrence wins). This is defensive — the
    extractor or LLM occasionally emits dupes (e.g. two `Total Annual Premium`
    measures landing on different tables). Dropping is preferable to letting
    Power BI refuse to load the entire model.
    """
    # 1. table names
    seen_tables_lc: set[str] = set()
    deduped_tables = []
    for t in tables:
        tlc = (t["name"] or "").lower()
        if tlc in seen_tables_lc:
            continue
        seen_tables_lc.add(tlc)
        deduped_tables.append(t)
    if len(deduped_tables) != len(tables):
        tables[:] = deduped_tables

    # 2. column names within each table
    for t in tables:
        seen_cols_lc: set[str] = set()
        deduped_cols = []
        for c in t.get("columns", []):
            clc = (c.get("name") or "").lower()
            if clc and clc not in seen_cols_lc:
                seen_cols_lc.add(clc)
                deduped_cols.append(c)
        t["columns"] = deduped_cols

    # 3. measure names model-wide
    seen_measures_lc: set[str] = set()
    for t in tables:
        kept = []
        for m in t.get("measures", []):
            mlc = (m.get("name") or "").lower()
            if mlc and mlc not in seen_measures_lc:
                seen_measures_lc.add(mlc)
                kept.append(m)
        t["measures"] = kept


def _write_semantic_model(model_dir: str, mapped: dict, display_name: str):
    _makedirs(model_dir)
    source = mapped.get("source", "tableau")
    tables = mapped.get("tables", [])
    # Enforce TMDL uniqueness invariants before any TMDL is emitted.
    _dedupe_model_names(tables)
    table_names = [t["name"] for t in tables]

    # Row-Level Security roles (source-agnostic): any flow that populates the
    # common-model `roles` section gets PBIP roles. Keep only roles with at
    # least one valid (table + filter) permission. Drives both the `ref role`
    # lines in model.tmdl and the roles/ folder written further below.
    roles = []
    for _r in (mapped.get("roles") or []):
        if not isinstance(_r, dict) or not _r.get("name"):
            continue
        _perms = [
            p for p in (_r.get("table_permissions") or [])
            if isinstance(p, dict) and p.get("table") and (p.get("filter_expression") or "").strip()
        ]
        if _perms:
            roles.append({"name": _r["name"], "table_permissions": _perms})
    role_names = [_r["name"] for _r in roles]

    # .platform
    _write_platform(os.path.join(model_dir, ".platform"), "SemanticModel", display_name)

    # definition.pbism
    _write_json(os.path.join(model_dir, "definition.pbism"), {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.2",
        "settings": {},
    })

    # diagramLayout.json — star schema layout: FCT in center, DM tables around it
    fct_tables = [t for t in tables if t["name"].startswith("FCT")]
    dm_tables  = [t for t in tables if not t["name"].startswith("FCT")]
    nodes = []
    cx, cy = 500, 300
    nodes += [{"location": {"x": cx, "y": cy}, "nodeIndex": t["name"],
               "size": {"height": 300, "width": 234}} for t in fct_tables]
    import math
    n = len(dm_tables)
    radius = 420
    for i, t in enumerate(dm_tables):
        angle = (2 * math.pi * i / max(n, 1)) - math.pi / 2
        x = int(cx + radius * math.cos(angle))
        y = int(cy + radius * math.sin(angle))
        nodes.append({"location": {"x": x, "y": y}, "nodeIndex": t["name"],
                      "size": {"height": 300, "width": 234}})
    _write_json(os.path.join(model_dir, "diagramLayout.json"), {
        "version": "1.1.0",
        "diagrams": [{"ordinal": 0, "scrollPosition": {"x": 0, "y": 0}, "nodes": nodes}],
    })

    def_dir = os.path.join(model_dir, "definition")
    _makedirs(def_dir)

    # database.tmdl
    _write_text(os.path.join(def_dir, "database.tmdl"), _tmdl_database())

    # model.tmdl (no relationships inline — they go in relationships.tmdl)
    has_auto_date = any(_is_auto_date_table(t["name"]) for t in tables)
    _write_text(os.path.join(def_dir, "model.tmdl"),
                _tmdl_model(table_names, has_auto_date_tables=has_auto_date,
                            role_names=role_names))

    # Pre-assign a stable GUID per input relationship id so that:
    #   - the relationship row in relationships.tmdl uses that GUID as its name,
    #   - the variation block on the parent date column references the same GUID.
    relationships = mapped.get("relationships", [])
    rel_guid_by_input_id: dict[str, str] = {}
    rel_guid_by_endpoint: dict[tuple, str] = {}
    for rel in relationships:
        rid = rel.get("input_id")
        if rid and rid not in rel_guid_by_input_id:
            rel_guid_by_input_id[rid] = _new_uuid()
        # Endpoint-keyed fallback for variations whose declared input_id was
        # dropped by mapper dedup but whose endpoint survived under a sibling
        # row's id.
        ep = (rel.get("fromTable"), rel.get("fromColumn"),
              rel.get("toTable"), rel.get("toColumn"))
        guid = rel_guid_by_input_id.get(rid) if rid else None
        if guid and ep not in rel_guid_by_endpoint:
            rel_guid_by_endpoint[ep] = guid

    # relationships.tmdl — separate file, same folder as model.tmdl
    if relationships:
        _write_text(os.path.join(def_dir, "relationships.tmdl"),
                    _tmdl_relationships_file(relationships, source, rel_guid_by_input_id, tables))

    # cultures/en-US.tmdl
    cultures_dir = os.path.join(def_dir, "cultures")
    _makedirs(cultures_dir)
    _write_text(os.path.join(cultures_dir, "en-US.tmdl"), _tmdl_culture())

    # roles/*.tmdl — Row-Level Security. One TMDL per role (filter DAX verbatim).
    if roles:
        roles_dir = os.path.join(def_dir, "roles")
        _makedirs(roles_dir)
        for role in roles:
            safe_role = re.sub(r'[\\/:*?"<>|]', "_", role["name"])
            _write_text(os.path.join(roles_dir, f"{safe_role}.tmdl"), _tmdl_role(role))

    # Precompute the set of (table, column) pairs that participate as a
    # relationship endpoint. Used by the column emitter to override
    # `summarizeBy:` to `none` for join columns — even ones the RE
    # mislabelled as plain `dimension` rather than `foreign_key`.
    rel_columns: set[tuple[str, str]] = set()
    for rel in relationships:
        for tk, ck in (("fromTable", "fromColumn"), ("toTable", "toColumn")):
            t, c = rel.get(tk), rel.get(ck)
            if t and c:
                rel_columns.add((t, c))

    # tables/*.tmdl — preserve spaces in filename (only strip chars invalid on Windows)
    tables_dir = os.path.join(def_dir, "tables")
    _makedirs(tables_dir)
    for table in tables:
        safe_tbl = re.sub(r'[\\/:*?"<>|]', "_", table["name"])
        _write_text(os.path.join(tables_dir, f"{safe_tbl}.tmdl"),
                    _tmdl_table(table, source, mapped,
                                rel_guid_by_input_id, rel_guid_by_endpoint,
                                rel_columns))


# Bookmarks ARE emitted. The RE preserves each bookmark's `explorationState`
# verbatim — including the per-visual visibility (`singleVisual.display.mode`)
# and the source page/visual ids. `_write_bookmarks` remaps those ids onto the
# generated ones and drops anything that can't be bridged, so the emitted state
# references only objects that actually exist. Earlier this was OFF because the
# captured state referenced SOURCE ids that never matched the generated ids and
# `filters.byExpr[*]` could lack the required `name` (a single invalid bookmark
# blocks the whole report from opening). Both are now handled: ids are remapped
# (source page id → ReportSection, source visual id → generated visual via the
# id map seeded from `source_visual_id`), unbridgeable containers are pruned,
# filter names are backfilled, and a bookmark whose active page no longer exists
# is skipped entirely.
_EMIT_BOOKMARKS = True


def _backfill_filter_names(filters_block) -> None:
    """Power BI requires every `filters.byExpr[*]` entry to carry a `name`.
    Backfill a stable one where the capture omitted it, else the bookmark fails
    schema validation and blocks report load."""
    if not isinstance(filters_block, dict):
        return
    for f in filters_block.get("byExpr") or []:
        if isinstance(f, dict) and not f.get("name"):
            f["name"] = _new_hex(20)


def _sanitize_bookmark_visual(vc: dict) -> None:
    """Strip null entries from a bookmark visualContainer's projection arrays.

    The legacy `.pbix` Layout bookmark allows `singleVisual.projections.<role> =
    [null, ...]` (null == "inherit the visual's field for this slot"), but the
    PBIR `.bookmark.json` schema requires every projection to be an OBJECT — a
    null entry makes Power BI Desktop reject the entire report. Dropping the
    nulls (and any role left empty) preserves the bookmark's intent: an omitted
    role inherits the visual's own field, which is exactly what null meant."""
    if not isinstance(vc, dict):
        return
    sv = vc.get("singleVisual")
    if not isinstance(sv, dict):
        return
    for key in ("projections", "activeProjections"):
        block = sv.get(key)
        if not isinstance(block, dict):
            continue
        cleaned = {}
        for role, arr in block.items():
            if isinstance(arr, list):
                arr = [x for x in arr if x is not None]
                if arr:
                    cleaned[role] = arr
            elif arr is not None:
                cleaned[role] = arr
        if cleaned:
            sv[key] = cleaned
        else:
            sv.pop(key, None)


def _remap_bookmark_state(state: dict, source_page_to_id: dict,
                          visual_id_map: dict) -> dict | None:
    """Return a deep copy of a bookmark `explorationState` with every source page
    / visual id remapped to the generated id. Returns None when the state can't
    be made safe (its active page no longer exists). Visual containers whose id
    can't be bridged are dropped so the result references only emitted objects."""
    state = copy.deepcopy(state)

    act = state.get("activeSection")
    if act is not None:
        if act not in source_page_to_id:
            return None        # active page doesn't exist → unsafe to emit
        state["activeSection"] = source_page_to_id[act]

    _backfill_filter_names(state.get("filters"))        # report-level filters

    sections = state.get("sections")
    if isinstance(sections, dict):
        new_sections = {}
        for src_pid, sec in sections.items():
            new_pid = source_page_to_id.get(src_pid)
            if not new_pid or not isinstance(sec, dict):
                continue       # page not in output → drop the section
            _backfill_filter_names(sec.get("filters"))
            vcs = sec.get("visualContainers")
            if isinstance(vcs, dict):
                new_vcs = {}
                for src_vid, vc in vcs.items():
                    gen_vid = visual_id_map.get(src_vid)
                    if not gen_vid:
                        continue   # visual not in output → drop (keeps state valid)
                    if isinstance(vc, dict):
                        _backfill_filter_names(vc.get("filters"))
                        _sanitize_bookmark_visual(vc)
                    new_vcs[gen_vid] = vc
                sec["visualContainers"] = new_vcs
            new_sections[new_pid] = sec
        state["sections"] = new_sections

    return state


# ── Bookmarks ────────────────────────────────────────────────────────────────
def _write_bookmarks(report_def_dir: str, mapped: dict,
                     source_page_to_id: dict, visual_id_map: dict) -> None:
    """Write `definition/bookmarks/<name>.bookmark.json` + `bookmarks.json` from
    `mapped["bookmarks"]`, remapping each captured explorationState onto the
    generated page/visual ids (style contract section 7)."""
    if not _EMIT_BOOKMARKS:
        return
    bookmarks = mapped.get("bookmarks")
    if not bookmarks or not isinstance(bookmarks, list):
        return
    bm_dir = os.path.join(report_def_dir, "bookmarks")
    # Idempotency guard (same rationale as the pages dir): clear stale bookmark
    # files from a prior run so a locked-output re-run can't leave duplicates.
    if os.path.isdir(_long(bm_dir)):
        shutil.rmtree(_long(bm_dir), ignore_errors=True)
    items: list = []
    for bm in bookmarks:
        if not isinstance(bm, dict):
            continue
        state = bm.get("explorationState")
        if not isinstance(state, dict):
            continue
        remapped = _remap_bookmark_state(state, source_page_to_id, visual_id_map)
        if remapped is None:
            continue
        bm_name = bm.get("name") or f"Bookmark{_new_hex(20)}"
        bm_obj = {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/bookmark/1.1.0/schema.json",
            "name": bm_name,
            "displayName": bm.get("displayName") or bm.get("display_name") or bm_name,
            "explorationState": remapped,
        }
        opts: dict = {}
        if bm.get("captureData") is not None:
            opts["suppressData"] = not bm["captureData"]
        if bm.get("captureCurrentPage") is not None:
            opts["suppressActiveSection"] = not bm["captureCurrentPage"]
        if opts:
            bm_obj["options"] = opts
        _write_json(os.path.join(bm_dir, f"{bm_name}.bookmark.json"), bm_obj)
        items.append(bm_name)
    if items:
        _write_json(os.path.join(bm_dir, "bookmarks.json"), {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/bookmarksMetadata/1.0.0/schema.json",
            "items": [{"name": n} for n in items],
        })


# ── Main write orchestration ───────────────────────────────────────────────────
def write_pbip(mapped: dict, output_dir: str):
    # Strip data-file extensions (e.g. .csv) from all table name references so TMDL
    # identifiers are clean. 'df_OrderItems.csv' → 'df_OrderItems'. The M query
    # partition that reads the actual .csv file on disk is unaffected.
    _clean_mapped_table_names(mapped)

    # Data loading: tables are loaded EXCLUSIVELY from CSV files the user
    # has placed in `sources/` (path-resolved by `_find_csv_file`). If a
    # table has no matching CSV, the writer falls back to a placeholder M
    # query pointing at the expected path — the model still loads in PBI
    # Desktop, only that one table reports a refresh failure until the user
    # drops the CSV in. No auto-generation; the old csv_seeder module that
    # synthesised dummy rows for missing tables was removed because it
    # produced data that didn't respect the real model's PK/FK constraints
    # and silently masked missing-data problems.

    name = _safe_name(mapped["reportName"])
    display_name = mapped.get("originalName", name)
    report_dir = os.path.join(output_dir, f"{name}.Report")
    model_dir = os.path.join(output_dir, f"{name}.SemanticModel")
    report_def_dir = os.path.join(report_dir, "definition")

    if os.path.exists(output_dir):
        try:
            shutil.rmtree(_long(output_dir))
        except (PermissionError, OSError):
            # Output folder is locked (e.g. Power BI Desktop has it open). Don't
            # fail — but DON'T silently write on top either: each run mints fresh
            # random ReportSection ids, so writing over a stale tree DUPLICATES
            # every dashboard. Warn loudly; the per-directory clears below
            # (pages/, bookmarks/) still keep the regenerated report consistent.
            print("[writer] WARNING: could not clear the existing output folder — "
                  "is the .pbip open in Power BI Desktop? Close it and re-run to "
                  "avoid duplicated pages.")
    _makedirs(output_dir)

    # 1. .pbip entry point
    _write_pbip(output_dir, name)

    # 2. Report .platform
    _write_platform(os.path.join(report_dir, ".platform"), "Report", display_name)

    # 3. definition.pbir
    _write_pbir(report_dir, name)

    # 4. definition/version.json + report.json
    _makedirs(report_def_dir)
    _write_version_json(report_def_dir)
    # Pull image-visual binaries from Postgres into StaticResources/
    # RegisteredResources/ and register them in report.json so the image
    # visuals can bind to them.
    image_registry = _resolve_report_images(mapped, report_dir)
    _write_report_json(report_def_dir, report_dir, mapped, image_registry)

    # 5. Pages — build lookup dicts so visuals use correct field types
    tables = mapped.get("tables", [])
    measures_by_table = {t["name"]: {m["name"] for m in t.get("measures", [])} for t in tables}
    # Build col_types and upgrade string columns that are SUM'd in measures to double,
    # so _agg_function picks Sum (0) instead of CountNonNull (5) for those columns.
    # Pair-keyed (table, column) lookup: a measure on table A referencing
    # SUM(table_B[col]) used to leak the upgrade onto every table whose
    # column shared that name, which broke refresh on string-typed
    # `Description` / `Name` / `Type` columns in unrelated tables.
    all_sum_pairs = set()
    for t in tables:
        all_sum_pairs |= _collect_sum_column_pairs(t.get("measures", []))
    col_types = {}
    for t in tables:
        tname = t["name"]
        upgraded = [c["name"] for c in t.get("columns", [])
                    if c.get("dataType", "string").lower() == "string"
                    and (tname, c["name"]) in all_sum_pairs]
        if _dbg:
            _dbg.log_sum_upgrade(tname, {col for _, col in all_sum_pairs}, upgraded)
        col_types[tname] = {
            c["name"]: (
                "double"
                if c.get("dataType", "string").lower() == "string"
                   and (tname, c["name"]) in all_sum_pairs
                else c.get("dataType", "string")
            )
            for c in t.get("columns", [])
        }
    if _dbg:
        _dbg.flush_sum_upgrades()

    # Separate field parameter tables into measure-type and dimension-type.
    # Measure-type (e.g. "Visual-Parameter") → added to Y/Values roles of ALL chart visuals.
    # Dimension-type (e.g. "Row Selecting Parameter") → added to Category/Rows roles
    #   only on pages where a slicer referencing that table exists.
    _DIM_KEYWORDS = ("Row", "Column", "Dimension")
    measure_fp = [t["name"] for t in tables if t.get("type") == "fieldParameter"
                  and not any(w in t["name"] for w in _DIM_KEYWORDS)]
    dim_fp_all  = [t["name"] for t in tables if t.get("type") == "fieldParameter"
                   and any(w in t["name"] for w in _DIM_KEYWORDS)]
    if _dbg:
        _dbg.log_fp_separation(measure_fp, dim_fp_all)

    pages = mapped.get("pages", [])
    page_ids = []
    for i, page in enumerate(pages):
        pid = "ReportSection" if i == 0 else f"ReportSection{_new_hex(20)}"
        page_ids.append(pid)

    pages_dir = os.path.join(report_def_dir, "pages")
    # Idempotency guard: clear any page folders from a prior run before writing
    # this run's. The top-level rmtree normally wipes the whole output, but when
    # it is skipped (output locked by an open Power BI Desktop), writing pages
    # with fresh random ReportSection ids ON TOP of the old ones would DUPLICATE
    # every dashboard. Clearing the pages dir first keeps re-runs clean.
    if os.path.isdir(_long(pages_dir)):
        shutil.rmtree(_long(pages_dir), ignore_errors=True)
    _makedirs(pages_dir)
    _write_pages_json(pages_dir, page_ids, page_ids[0] if page_ids else "ReportSection")

    # Page display name → ReportSection id, so navigation/drillthrough buttons
    # (style contract section 7) can resolve their target page.
    page_name_to_id = {p["name"]: pid for p, pid in zip(pages, page_ids)}
    # Original source page id → ReportSection id. A bookmark's explorationState
    # keys its sections / activeSection by the source page id, so this is the
    # bridge used to remap bookmarks onto the generated pages.
    source_page_to_id = {p["page_id"]: pid for p, pid in zip(pages, page_ids)
                         if p.get("page_id")}
    # Accumulate every page's {RE visual id → generated name} map so bookmarks
    # (section 7) can resolve their captured visual references.
    global_visual_id_map: dict = {}

    for page, pid in zip(pages, page_ids):
        # Only apply dimension FP tables when their slicer is on THIS page
        page_dim_fp = [
            fp for fp in dim_fp_all
            if any(
                f.get("table") == fp
                for v in page.get("visuals", [])
                if "slicer" in v.get("visualType", "").lower()
                for f in v.get("fields", [])
            )
        ]
        id_map = _write_page(pages_dir, page, pid, measures_by_table, col_types,
                             measure_fp, page_dim_fp, image_registry, page_name_to_id)
        if id_map:
            global_visual_id_map.update(id_map)

    # 5b. Bookmarks (style contract section 7) — written after every page so
    # captured visual / page references can be resolved.
    _write_bookmarks(report_def_dir, mapped, source_page_to_id, global_visual_id_map)

    # 6. SemanticModel (TMDL)
    _write_semantic_model(model_dir, mapped, display_name)

    # 7. Collect written files. os.walk uses Win32 FindFirstFile under the
    # hood, which respects MAX_PATH (260) unless the root is given with the
    # long-path prefix. Without `_long(output_dir)` here, walks of deep
    # PBIP trees silently skip the leaf visual folders and the validator
    # then reports phantom MISSING errors.
    files = []
    _walk_root = _long(output_dir)
    for root, _, fnames in os.walk(_walk_root):
        for fn in fnames:
            # Strip the long-path prefix back off so the returned paths
            # are the normal Windows paths callers expect.
            real_root = root[4:] if root.startswith("\\\\?\\") else root
            files.append(os.path.relpath(os.path.join(real_root, fn), output_dir))
    return files


def write_empty_report(parent_dir: str, name: str, display_name: str) -> str:
    """Build a minimal, empty `<name>.Report` folder under `parent_dir` and
    return its path. One blank page, zero visuals.

    PBIP has no dataset-only `.pbip` — every `.pbip` must reference a report.
    To ship the semantic model as its own openable PBIP, it is packaged as a
    full PBIP whose report is this empty shell: opening the `.pbip` in Power
    BI Desktop loads the data model with a blank report canvas. Reuses the
    same report-writing helpers as `write_pbip` so the structure stays in
    sync with real reports.
    """
    report_dir = os.path.join(parent_dir, f"{name}.Report")
    report_def_dir = os.path.join(report_dir, "definition")
    _makedirs(report_def_dir)

    _write_platform(os.path.join(report_dir, ".platform"), "Report", display_name)
    _write_pbir(report_dir, name)
    _write_version_json(report_def_dir)
    # mapped=None → no custom-visual registration (an empty report has none).
    _write_report_json(report_def_dir, report_dir, None)

    pages_dir = os.path.join(report_def_dir, "pages")
    _makedirs(pages_dir)
    pid = "ReportSection"
    _write_pages_json(pages_dir, [pid], pid)

    page_dir = os.path.join(pages_dir, pid)
    _makedirs(page_dir)
    _write_json(os.path.join(page_dir, "page.json"), {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.0.0/schema.json",
        "name": pid,
        "displayName": "Page 1",
        "displayOption": "FitToPage",
        "height": 720,
        "width": 1280,
    })
    return report_dir


def main():
    ap = argparse.ArgumentParser(description="Write .pbip folder from mapped.json")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    with open(args.input) as f:
        mapped = json.load(f)

    files = write_pbip(mapped, args.output)
    print(f"[writer] Written {len(files)} files to {args.output}")
    for fn in files:
        print(f"  {fn}")


if __name__ == "__main__":
    main()
