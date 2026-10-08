"""
parser.py — Read common-model JSON (Tableau or Power BI extraction),
optionally enrich with Postgres metadata, output normalized intermediate.json.
"""
import json, sys, argparse, os, re

sys.path.insert(0, os.path.dirname(__file__))

try:
    from skills.json_to_pbip.src import debug_collector as _dbg
except ImportError:
    _dbg = None

# Style normalisers — map the RE's snake_case style schema + ready-made PBIP
# (`style.raw`) onto what the writer consumes. Optional import so the parser
# still runs if styles.py is unavailable.
try:
    from skills.json_to_pbip.src import styles as _styles
except ImportError:  # pragma: no cover
    try:
        import styles as _styles
    except ImportError:
        _styles = None


def _canvas_from_styles(styles: dict) -> dict | None:
    """Derive the writer's `canvas` dict from the RE's snake_case page `styles`
    block. The page background/wallpaper come through as ready-made PBIP via
    `styles.raw` (carried separately), so here we only surface the bits the
    writer needs for page.json scalar fields: vertical alignment + page type."""
    if not isinstance(styles, dict):
        return None
    canvas: dict = {}
    if styles.get("vertical_alignment"):
        canvas["verticalAlignment"] = styles["vertical_alignment"]
    if styles.get("page_type"):
        canvas["pageType"] = styles["page_type"]
    return canvas or None


# ── Data-type normalisation ────────────────────────────────────────────────────
_TYPE_MAP = {
    "string": "string", "str": "string", "text": "string",
    # All floating-point types — including the RE's `decimal` — map to TMDL
    # `double`. TMDL `decimal` is the Fixed-Decimal-Number (Currency) type
    # with 4-digit precision; it is INCOMPATIBLE with M's `type number`
    # (double-precision). When the TMDL declares `decimal` but the M
    # partition emits `type number`, every non-currency value (percentages,
    # ratios, generic floats like `settlement %`) fails to coerce at load
    # time and the table refuses to refresh. Real PBI exports reserve
    # `decimal` exclusively for explicit currency columns (`currency`
    # below); generic floats use `double`. Mirroring that here.
    "number": "double", "float": "double", "double": "double",
    "decimal": "double",
    # Tableau's native floating-point type label is `real` (vs PBI's `decimal`).
    # Without this entry it falls through to the `string` default and every
    # `real` column (Sales, Unit Price, ...) gets typed as text, which then
    # breaks the M `Table.TransformColumnTypes` step on numeric source data.
    "real": "double",
    "currency": "decimal",
    "integer": "int64", "int": "int64", "int64": "int64", "whole number": "int64",
    "datetime": "dateTime", "date": "date", "time": "time",
    "boolean": "boolean", "bool": "boolean",
}


def _norm_type(t: str) -> str:
    return _TYPE_MAP.get((t or "").lower().strip(), "string")


# Strip Tableau's composite table id wrapper, e.g.
#   "tableau(toolname)$case-study1.twbx(filename)$Market Basket(datasource)$tbl_sales(table)"
#   → "tbl_sales"
#   "tableau(...)$Product Sales(datasource)$tbl_sales(table)$d2edcfdba188(uuid)"
#   → "tbl_sales"
# Why: the mapper's `_resolve_tbl` lowercases + alnum-normalizes the input and
# matches against the short names in `tables[].name`. The composite form
# normalizes to a 60-char blob that matches nothing, so EVERY tableau
# relationship gets dropped by GUARD 2 ("phantom-table check") and no
# relationships.tmdl is emitted. The `(table)` segment is NOT always last —
# newer extractor output appends a `$<hash>(uuid)` segment after it — so the
# match is NOT anchored to end-of-string. PBI relationship IDs are short to
# begin with (e.g. "tbl_dim_customer"), so this is a no-op for the PowerBI path.
_TABLEAU_TABLE_ID_RE = re.compile(r'\$([^$()]+)\(table\)')


def _strip_tableau_table_id(s: str) -> str:
    if not s:
        return s
    m = _TABLEAU_TABLE_ID_RE.search(s)
    return m.group(1) if m else s


def _recover_rel_tables_from_id(rel_id: str, table_names: list) -> tuple:
    """Recover (from_table, to_table) from a relationship id shaped like
    `rel_<from>_<to>_<column>`.

    Some extractor outputs leave `left_table` / `right_table` null and only
    populate the `id`. Without the endpoints, the mapper's GUARD 1 drops the
    relationship and no relationships.tmdl is emitted — every cross-table
    visual then renders blank because the model has no joins.

    Table names are matched by LONGEST prefix against the known model tables
    (normalised: lowercased, '-' -> '_'), so a name that is a prefix of
    another (`tbl_sales` vs `tbl_sales1`) resolves to the correct one.
    Returns (None, None) when the id doesn't parse cleanly — the caller then
    leaves the endpoints empty and the mapper drops the row as before (no
    regression for inputs that never carried this id shape).
    """
    if not rel_id or not rel_id.lower().startswith("rel_"):
        return None, None
    _norm = lambda s: s.lower().replace("-", "_")
    norm_map = {_norm(t): t for t in table_names}
    # Longest names first so `tbl_sales1` wins over `tbl_sales`.
    cands = sorted(norm_map.keys(), key=len, reverse=True)

    def _match_prefix(s: str):
        for n in cands:
            if s == n or s.startswith(n + "_"):
                return n, s[len(n):].lstrip("_")
        return None, None

    body = _norm(rel_id[4:])                       # drop the leading "rel_"
    nfrom, rest = _match_prefix(body)
    if not nfrom:
        return None, None
    nto, _ = _match_prefix(rest)
    if not nto:
        return None, None
    return norm_map[nfrom], norm_map[nto]


# ── Visual-type normalisation ──────────────────────────────────────────────────
_VISUAL_MAP = {
    "bar": "barChart", "bar_chart": "barChart", "barchart": "barChart",
    "stacked_bar": "barChart", "stacked_bar_chart": "barChart",
    "clustered_bar": "clusteredBarChart", "clustered_bar_chart": "clusteredBarChart",
    "column": "columnChart", "column_chart": "columnChart",
    "stacked_column": "columnChart", "stacked_column_chart": "columnChart",
    "clustered_column": "clusteredColumnChart", "clustered_column_chart": "clusteredColumnChart",
    "line": "lineChart", "line_chart": "lineChart", "linechart": "lineChart",
    "area": "areaChart", "area_chart": "areaChart", "areachart": "areaChart",
    "stacked_area": "stackedAreaChart", "stacked_area_chart": "stackedAreaChart",
    "pie": "pieChart", "pie_chart": "pieChart",
    "scatter": "scatterChart", "scatter_chart": "scatterChart",
    "scatter_plot": "scatterChart", "scatterplot": "scatterChart",
    "map": "map", "filled_map": "filledMap",
    # `shape` is a decorative container (rectangle, line, divider) — it is
    # NOT a geographic map. Mapping it to "map" produces a data-less map
    # widget that renders blank. PBIP's native visualType for shapes is
    # `shape`, which renders the decoration correctly.
    "shape": "shape",
    "table": "tableEx", "text": "tableEx", "crosstab": "tableEx",
    # Tableau heat maps are crosstab-style visuals with a colour-encoded
    # measure. PBI has no native heat-map visualType, so map them to the
    # Matrix visual — the closest native equivalent that preserves row/column
    # grouping plus conditional-formatting (colour) on the value cells.
    # The Matrix visual's PBIP visualType string is `pivotTable` (NOT
    # `matrix` — that string is unrecognised and Power BI falls back to a
    # plain table render).
    "heat_map": "pivotTable", "heatmap": "pivotTable", "heat-map": "pivotTable",
    # Square/highlight/text crosstab family the RE emits with varied names —
    # all are matrix-style crosstabs → pivotTable (the closest native visual
    # that preserves row/column grouping + colour-coded values).
    "square_heat_map": "pivotTable", "squareheatmap": "pivotTable",
    "highlight_table": "pivotTable", "highlighttable": "pivotTable",
    "text_table": "tableEx", "texttable": "tableEx", "crosstab_table": "tableEx",
    # Chart-type aliases the RE prompt can emit that need an explicit PBI type
    # (without these they pass through as invalid visualTypes → blank tile).
    "bubble_chart": "scatterChart", "bubblechart": "scatterChart",
    "dual_axis_chart": "lineClusteredColumnComboChart",
    "dual_axis": "lineClusteredColumnComboChart",
    "combo_chart": "lineClusteredColumnComboChart",
    "histogram": "columnChart",
    "tree_map": "treemap", "tree-map": "treemap",
    "gantt_chart": "ganttChart", "gantt": "ganttChart",
    "box_whisker_chart": "tableEx", "box_whisker": "tableEx", "boxplot": "tableEx",
    "textbox": "textbox", "text_box": "textbox",
    "blank": "textbox",
    "slicer": "slicerVisual",
    # Tableau's parameter-control widget. PBI's nearest native equivalent
    # is a slicer (binds a single field, lets the user pick from a list /
    # range). Without this map, `paramctrl` falls through to a custom-visual
    # registration that has no resolvable plugin → blank container.
    "paramctrl": "slicerVisual", "parameter": "slicerVisual",
    "parameter_control": "slicerVisual",
    # Tableau box-and-whisker. PBI has no native box plot; the least-bad
    # fallback that still shows the underlying data is `tableEx`. The user
    # can re-author it as a scatter plot or install a box-plot AppSource
    # visual after the fact; meanwhile the data isn't lost.
    "box_whisker_chart": "tableEx", "box_whisker": "tableEx",
    "boxplot": "tableEx", "box_plot": "tableEx",
    # PBIP's KPI visualType is literally `kpi` — `kpiVisual` is not a
    # recognized visualType and causes Power BI Desktop to fail to render
    # the visual (shows as broken / placeholder).
    "card": "card", "kpi": "kpi",
    # Tableau's `kpi_card` (a "BAN" — big single number) is functionally a
    # PBI `card`, not a PBI `kpi`. PBI's `kpi` visualType is a value +
    # sparkline + goal combo and REQUIRES a TrendLine field; without one
    # the engine refuses to render any value (title chrome only). Tableau
    # BANs never carry a trend axis, so map them to `card`, whose sole
    # required slot is `Values` — exactly what a BAN provides.
    "kpi_card": "card", "kpicard": "card", "kpi-card": "card", "kpiCard": "card",
    "matrix": "pivotTable",
    "funnel": "funnel",
    "gauge": "gauge",
    "waterfall": "waterfallChart",
    "ribbon": "ribbonChart",
    "treemap": "treemap",
    "donut": "donutChart",
}


def _norm_visual_type(raw: str) -> str:
    if not raw:
        return "unknown"
    return _VISUAL_MAP.get(raw.lower().replace(" ", "_"), raw)


# ── Source detection ───────────────────────────────────────────────────────────
def detect_source(data: dict) -> str:
    """Read `tool_type` from the extractor's JSON and normalise it.

    Accepted values:
      - "powerbi"                    → "powerbi"
      - "tableau" / "tableau-workbook" → "tableau"

    The RE always sets this field on the top-level dict; anything else is
    a malformed input and we fail loudly so the upstream issue is visible.
    """
    tt = (data.get("tool_type") or "").lower().strip()
    if tt == "powerbi":
        _log_detect_source(data, "powerbi")
        return "powerbi"
    if tt in ("tableau", "tableau-workbook"):
        _log_detect_source(data, "tableau")
        return "tableau"
    raise ValueError(
        f"Unknown or missing tool_type: {tt!r}. "
        f"Expected 'powerbi', 'tableau', or 'tableau-workbook'."
    )


def _log_detect_source(data: dict, detected: str):
    if _dbg:
        ids = [s.get("id", "") for s in data.get("data_sources", [])]
        _dbg.log_detect_source(ids, detected)


def _tableau_rowlevel_to_dax_column(expr: str, table: str, table_index: dict) -> str | None:
    """Convert a SIMPLE row-level Tableau string formula into a DAX calculated-
    COLUMN body (row context — bare `'table'[Col]` refs, no SELECTEDVALUE).

    Handles the common label-cleanup shape:
        IF [Description]="X" THEN "Y" ELSE [Description] END
      → IF('table'[Description]="X", "Y", 'table'[Description])
    and a bare passthrough `[Description]` → 'table'[Description].

    Conservative: returns None if the formula uses any construct we don't safely
    translate (aggregations, LOD braces, CASE, multi-branch ELSEIF, functions),
    so the caller falls back to the measure path. Only `[Col]` refs that exist on
    `table` are rewritten; an unknown ref aborts the translation (returns None).
    """
    if not expr or not table:
        return None
    s = expr.strip()
    # Reject anything beyond a simple IF/ELSE label calc or a bare column.
    low = s.lower()
    if any(tok in low for tok in ("{", "}", "elseif", "case ", "window_", "running_",
                                  "sum(", "avg(", "count(", "fixed", "include", "exclude",
                                  "lookup(", "rank(", "index(")):
        return None

    cols = {c.get("name") for c in table_index.get(table, {}).get("columns", [])}

    def _q(tbl):
        # single-quote the table name (DAX requires it for names with spaces/punct)
        return "'" + tbl.replace("'", "''") + "'"

    # Replace every [Col] reference with 'table'[Col]; abort if the column isn't
    # on this table (keeps us from inventing a binding).
    abort = {"hit": False}
    def _ref(m):
        name = m.group(1)
        if name not in cols:
            abort["hit"] = True
            return m.group(0)
        return f"{_q(table)}[{name}]"
    rewritten = re.sub(r"\[([^\]]+)\]", _ref, s)
    if abort["hit"]:
        return None

    # Bare passthrough column.
    if re.fullmatch(r"'[^']+'\[[^\]]+\]", rewritten.strip()):
        return rewritten.strip()

    # IF ... THEN ... ELSE ... END  (single branch) -> IF(cond, then, else)
    m = re.match(r"(?is)^\s*IF\s+(.+?)\s+THEN\s+(.+?)\s+ELSE\s+(.+?)\s+END\s*$", rewritten)
    if m:
        cond, then, els = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        # Tableau `=` comparison is valid DAX `=`. Collapse internal newlines.
        cond = re.sub(r"\s+", " ", cond)
        return f"IF({cond}, {then}, {els})"
    # IF ... THEN ... END (no else) -> IF(cond, then)
    m = re.match(r"(?is)^\s*IF\s+(.+?)\s+THEN\s+(.+?)\s+END\s*$", rewritten)
    if m:
        cond = re.sub(r"\s+", " ", m.group(1).strip())
        return f"IF({cond}, {m.group(2).strip()})"
    return None


# Recognise lat/long coordinate columns. These need PBI's `dataCategory:
# Latitude` / `Longitude` and `summarizeBy: none` in TMDL, plus no
# Aggregation wrap in any visual queryState that binds them — without those,
# map visuals fail at render with `DataViewMappingError_LatLongAggregateWithNoLocation`
# because PBI's default treatment of a numeric column is Sum.
_LAT_NAMES = {"latitude", "lat"}
_LON_NAMES = {"longitude", "long", "lon", "lng"}
_NUMERIC_DTYPES_FOR_COORDS = {"real", "double", "number", "float", "decimal"}

# Power BI data categories valid for geocoding a Map location field. Used to
# accept an RE-provided `data_category` on a place-name dimension (e.g. the
# Tableau geo-normalization promotes `State` to a Category with
# data_category="StateOrProvince"). Mirrors the TMDL `dataCategory:` vocabulary.
_VALID_DATA_CATEGORIES = {
    "Latitude", "Longitude", "Address", "City", "Continent", "Country",
    "County", "Place", "PostalCode", "StateOrProvince", "WebUrl", "ImageUrl",
}


def _infer_coordinate_category(col_raw: dict) -> str | None:
    """Return "Latitude" / "Longitude" / None for a column dict from the RE.

    Signals checked in priority order:
      1. `semantic_role` if the RE already tagged the column with
         "latitude"/"longitude" (PBI extractor sometimes does this).
      2. Exact column-name match against a small set of conventional spellings,
         scoped to numeric columns only — avoids false-firing on a string
         column literally named "Latitude" used as a categorical label.

    Description matching is deliberately NOT used as a signal — the RE's
    auto-generated descriptions ("Latitude coordinate for customer location")
    are unreliable across tools.
    """
    # 0. An explicit data_category provided by the RE wins. The Tableau RE's
    #    geo-normalization tags a promoted location dimension with a PBI
    #    dataCategory (StateOrProvince / City / Country / PostalCode / Place /
    #    Latitude / Longitude). Honour it so the Map visual can geocode the
    #    location column — without a dataCategory PBI cannot reliably plot a
    #    place-name dimension and the map renders empty.
    _provided = (col_raw.get("data_category") or "").strip()
    if _provided in _VALID_DATA_CATEGORIES:
        return _provided

    role = (col_raw.get("semantic_role") or "").strip().lower()
    if role == "latitude":
        return "Latitude"
    if role == "longitude":
        return "Longitude"
    dtype = (col_raw.get("data_type") or "").strip().lower()
    if dtype in _NUMERIC_DTYPES_FOR_COORDS:
        name = (col_raw.get("name") or "").strip().lower()
        if name in _LAT_NAMES:
            return "Latitude"
        if name in _LON_NAMES:
            return "Longitude"
    return None


# ── Common-model parser (both inputs share same schema) ────────────────────────
def parse_common_model(data: dict, source: str, db_rows: dict | None = None) -> dict:
    """
    Convert the normalized common-model JSON (from either Tableau or PBI extractor)
    into our intermediate format consumed by mapper.py.
    """
    # Newer extractor outputs wrap the model payload under a top-level "result"
    # envelope alongside status/runtime fields. Unwrap so downstream code sees
    # tables / relationships / calculations / visualizations at the root.
    if isinstance(data.get("result"), dict) and "tables" in data["result"]:
        data = data["result"]

    tables = []
    for t in data.get("tables", []):
        cols = []
        for c in t.get("columns", []):
            col_entry = {
                "name": c["name"],
                "dataType": _norm_type(c.get("data_type", "string")),
                "nullable": c.get("nullable", True),
                "description": c.get("description", ""),
                "used_in_relationships": c.get("used_in_relationships", False),
                "used_in_filters": c.get("used_in_filters", False),
                "distinct_count_high": c.get("distinct_count_high", False),
                "semantic_role": c.get("semantic_role"),
                # PBI data category. Coordinate columns need `dataCategory:
                # Latitude`/`Longitude` and `summarizeBy: none` for map
                # visuals to render without DataViewMappingError. The writer
                # consumes this field; absent = no category line emitted.
                "data_category": _infer_coordinate_category(c),
                # Auto date/time variation pointer — empty list for non-date cols.
                "variations": c.get("variations") or [],
            }
            dax_expr = c.get("expression") or c.get("dax_expression")
            if dax_expr:
                col_entry["expression"] = dax_expr
            if c.get("formatString"):
                col_entry["formatString"] = c["formatString"]
            cols.append(col_entry)
            if _dbg:
                _dbg.log_norm_type(t["name"], c["name"],
                                   c.get("data_type", "string"), col_entry["dataType"])

        # Ingest steps → transformations. Track the partition body separately
        # so the writer can emit the correct TMDL partition shape per table.
        #
        # `table_type` is the authority for partition kind, not the key name
        # inside `native_expressions`. TMDL has only `m` and `calculated`
        # partitions; a `calculated` table's body is DAX by definition, no
        # matter whether the extractor labeled it under `dax`, `powerquery`,
        # or anything else. So for calculated tables we pull whichever key
        # holds an expression; for imported tables we still expect M under
        # `powerquery`.
        transforms = []
        dax_table_expr = None
        powerquery_expr = None
        is_calculated_table = (t.get("table_type") == "calculated")
        for step in (t.get("ingestion") or {}).get("steps", []):
            native = step.get("native_expressions") or {}
            any_expr = (native.get("dax")
                        or native.get("powerquery")
                        or native.get("powerbi")
                        or native.get("tableau"))
            transforms.append({
                "order": step.get("order"),
                "type": step.get("step_type"),
                "description": step.get("description", ""),
                "expression": any_expr,
            })
            if is_calculated_table:
                if any_expr and not dax_table_expr:
                    dax_table_expr = any_expr
            else:
                if native.get("powerquery") and not powerquery_expr:
                    powerquery_expr = native["powerquery"]

        tables.append({
            "name": t["name"],
            "table_type": t.get("table_type", "unknown"),
            "columns": cols,
            "measures": [],       # filled from calculations block below
            "transformations": transforms,
            "dax_table_expression": dax_table_expr,   # set iff DAX calculated table
            "powerquery_expression": powerquery_expr, # set iff source has M code
            # Self-join / data-source alias link. When set, this IMPORTED table
            # is the SAME physical source as the named base table (a Tableau
            # self-join uses one CSV twice under different names). The writer
            # loads the alias's partition from the BASE table's CSV instead of a
            # non-existent "<alias>.csv". Only Tableau self-join aliases set this;
            # PowerBI/QlikView leave it None, so the behaviour is inert for them.
            "source_derived_from_table_id": t.get("source_derived_from_table_id"),
            "description": t.get("description", ""),
            # User- or auto-authored hierarchies declared on this table.
            "hierarchies": t.get("hierarchies") or [],
        })

    # Index tables by name for measure assignment
    table_index = {t["name"]: t for t in tables}

    # Calculations → measures on the appropriate table
    all_measures = []
    for calc in data.get("calculations", []):
        sem = (calc.get("semantic_type") or "").lower()
        # Tableau hierarchy drill paths have no DAX equivalent — skip them entirely.
        if sem == "hierarchy":
            continue
        # Tableau "groups" come in two flavours:
        #   1. UI value-mappings with NO formula (`expressions.* = null`).
        #      Emitting them produces an empty `measure 'X' = ` line whose
        #      next TMDL line (`lineageTag:`) is mis-parsed as the body —
        #      PBI then reports "The syntax for ':' is incorrect". Skip.
        #   2. Self-referential set/group ACTIONS like
        #      `Action (Category) = [Action (Category)]` — converting these
        #      yields a circular measure. Skip.
        # But many `group` calcs ARE real row-level formulas (e.g. a
        # `Product Description` cleanup `IF [Description]=... THEN ... END`).
        # Those must be kept, otherwise every visual field bound to them
        # resolves to nothing and the visual fails to render.
        if sem == "group":
            _g = calc.get("expressions") or {}
            _g_expr = (_g.get("dax") or _g.get("tableau") or _g.get("powerbi")
                       or calc.get("expression") or "").strip()
            if not _g_expr or _g_expr == f"[{calc.get('name', '')}]":
                continue
        # Spatial constructs (MAKEPOINT, MAKELINE, geographic DISTANCE) have
        # no DAX equivalent — the LLM produces invalid pseudo-DAX (e.g. a WKT
        # POINT string literal that downstream measures then dereference as
        # if it were a real column). Better to drop the unconvertible measure
        # so downstream dependents get caught by the missing-deps check and
        # are also dropped cleanly, instead of leaving a fan-out of broken
        # measures referencing a non-existent column.
        if (calc.get("data_type") or "").lower() == "spatial":
            continue
        if sem.startswith("spatial_") or sem.startswith("distance_"):
            continue

        # Prefer pre-translated DAX (PowerBI extractor) over raw source syntax
        # (Tableau extractor). When dax is present, mark as trusted so the
        # mapper skips the LLM and post-processing.
        exprs = calc.get("expressions") or {}
        if exprs.get("dax"):
            expr_raw = exprs["dax"]
            expression_is_dax = True
        else:
            expr_raw = exprs.get("tableau") or exprs.get("powerbi") or calc.get("expression", "")
            expression_is_dax = False

        # Home table priority:
        #   1. Explicit `home_table` from the extractor (authoritative — tells us
        #      where the measure should live in TMDL so visual queryRefs like
        #      "CustomerCountPerDay.TotalRevenue" bind to a measure on that exact
        #      table). Measures sitting on the wrong table are NOT a load error
        #      but the visual silently falls back to a non-existent column ref.
        #   2. First resolvable `<table>.<col>` in depends_on_columns — heuristic
        #      kept as fallback for older/partial JSONs without home_table.
        #   3. First table in the model — last-resort default.
        target_table = None
        home = calc.get("home_table")
        if home and home in table_index:
            target_table = home
        if not target_table:
            depends = calc.get("depends_on_columns") or []
            # Column name is always the last segment after the final '.';
            # everything before is the table name (which may itself contain '.', e.g. df_OrderItems.csv).
            for dep in depends:
                if "." in dep:
                    tbl_name, _col_name = dep.rsplit(".", 1)
                    if tbl_name in table_index:
                        target_table = tbl_name
                        break
        if not target_table and tables:
            target_table = tables[0]["name"]

        # ── Row-level STRING calc → CALCULATED COLUMN (not a measure) ──────────
        # A Tableau calc that returns a string and is computed per-row from
        # physical columns of its OWN table (e.g. a label cleanup
        #   `IF [Description]="Indoor Pet Camera (Wi-Fi)" THEN "Indoor Pet Camera"
        #    ELSE [Description] END`)
        # is a DIMENSION, not a measure. Emitting it as a measure makes it
        # impossible to place on a chart's Category/axis (Power BI rejects a
        # measure on an axis → "Something's wrong with one or more fields"). A
        # DAX *calculated column* with the same logic CAN sit on an axis. So we
        # route these to the table's columns[] with a row-context DAX body
        # (`'table'[Col]` references, no SELECTEDVALUE wrap).
        _norm_dtype = _norm_type(calc.get("data_type", "double"))
        _sem = (calc.get("semantic_type") or "").lower()
        _deps = calc.get("depends_on_columns") or []
        _target_cols = {c.get("name") for c in table_index.get(target_table, {}).get("columns", [])} \
            if target_table else set()
        # Every dependency's COLUMN NAME must exist on the target/home table. We
        # match by bare column name (not the dep's table prefix): the LLM often
        # over-lists a cross-table dep with the same column name (e.g.
        # `tbl_products.Description` alongside `tbl_sales.Description`), but the
        # row-level formula only references `[Description]`, which resolves on the
        # home table. _tableau_rowlevel_to_dax_column is the real safety net — it
        # aborts (returns None) if any `[Col]` ref isn't actually on the table.
        _deps_resolve_on_target = bool(_deps) and all(
            (dep.rsplit(".", 1)[-1] if "." in dep else dep) in _target_cols
            for dep in _deps
        )
        # A row-level STRING calc (a label / group / cleanup like
        # "Product Description") must become a calculated COLUMN, not a measure —
        # otherwise a slicer/axis bound to it gets a measure and can't list
        # values. We DON'T gate on the LLM's `semantic_type` label: it is volatile
        # across runs (the same cleanup calc came back `string_cleaning` one run
        # and `cleaning` the next, which silently dropped Product Description from
        # the product-map axis). The real guard is `_tableau_rowlevel_to_dax_column`
        # below — it returns None for ANYTHING that isn't a simple row-level
        # IF/passthrough (it rejects aggregations, LOD, window/lookup, etc.), so a
        # string-typed *measure* falls through to the measure path safely. The
        # gate is therefore purely data_type + structure driven: string output, no
        # measure dependencies, deps resolve on the home table.
        _is_rowlevel_string = (
            _norm_dtype == "string"
            and not (calc.get("depends_on_measures") or [])   # no measure refs
            and target_table is not None
            and _deps_resolve_on_target
        )
        if _is_rowlevel_string and not expression_is_dax and expr_raw:
            calc_col_dax = _tableau_rowlevel_to_dax_column(expr_raw, target_table, table_index)
            if calc_col_dax:
                # Append as a calculated column on the home table. The writer's
                # existing calc-column branch emits `column 'Name' = <dax>`,
                # which is bindable on a Category axis.
                table_index[target_table]["columns"].append({
                    "name": calc["name"],
                    "dataType": "string",
                    "nullable": True,
                    "description": "",
                    "used_in_relationships": False,
                    "used_in_filters": False,
                    "distinct_count_high": False,
                    "semantic_role": "dimension",
                    "data_category": None,
                    "variations": [],
                    "expression": calc_col_dax,   # DAX calc-column body
                })
                continue  # do NOT also emit as a measure

        measure = {
            "name": calc["name"],
            "expression_raw": expr_raw,
            "expression_is_dax": expression_is_dax,
            "expression_type": source + "_calc",
            "data_type": _norm_type(calc.get("data_type", "double")),
            "aggregation": calc.get("aggregation_behavior") or calc.get("aggregation") or "additive",
            "reusable": calc.get("reusable", False),
            "depends_on_columns": calc.get("depends_on_columns") or [],
            "depends_on_measures": calc.get("depends_on_measures") or [],
            "format_string": calc.get("format_string", "") or "",
            "semantic_type": calc.get("semantic_type"),
            # Carried for the what-if-parameter transform in the mapper (a
            # numeric-range parameter becomes a GENERATESERIES table + slicer).
            "parameter_config": calc.get("parameter_config"),
        }
        all_measures.append((target_table, measure))
        if target_table and target_table in table_index:
            table_index[target_table]["measures"].append(measure)

    # Relationships — preserve raw input fields so the mapper can do
    # cardinality inference and the writer can emit correct TMDL.
    relationships = []
    _rel_table_names = [t["name"] for t in tables]
    for r in data.get("relationships", []):
        from_tbl = _strip_tableau_table_id(r.get("left_table") or r.get("left_table_id", "")) or ""
        to_tbl   = _strip_tableau_table_id(r.get("right_table") or r.get("right_table_id", "")) or ""
        # Recover null endpoints from the relationship id (`rel_<from>_<to>_<col>`).
        # Extractors that omit left_table/right_table would otherwise have every
        # relationship dropped by the mapper, leaving the model with no joins.
        if not from_tbl or not to_tbl:
            rec_from, rec_to = _recover_rel_tables_from_id(r.get("id", ""), _rel_table_names)
            from_tbl = from_tbl or rec_from or ""
            to_tbl   = to_tbl or rec_to or ""
        relationships.append({
            "id": r.get("id"),                                  # stable input id; used to match variations
            "from_table": from_tbl,
            "from_col": r.get("left_column", ""),
            "to_table": to_tbl,
            "to_col": r.get("right_column", ""),
            "join_type": r.get("join_type", "inner"),
            "cardinality": r.get("cardinality"),               # raw, may be None
            "filter_direction": r.get("filter_direction"),     # raw, may be None
            "relationship_type": r.get("relationship_type"),
            "active": r.get("active", True),
            "is_hidden": r.get("is_hidden", False),
            "is_auto_generated": r.get("is_auto_generated", False),
            "join_on_date_behavior": r.get("join_on_date_behavior"),
        })

    # Pages / Visuals
    pages = []
    viz_data = data.get("visualizations", {})
    raw_pages = viz_data.get("pages", []) if isinstance(viz_data, dict) else []

    # Optionally merge Postgres viz data
    pg_viz_map: dict[str, dict] = {}
    if db_rows:
        for row in db_rows.get("visualizations", []):
            pg_viz_map[row.get("object_id", "")] = row

    # Build lookups so we can redirect visual-field bindings that point at a
    # non-existent table. Tableau emits visual fields against auto-generated
    # "federated.<hash>" virtual tables with columns shaped either as:
    #   * "Latitude (generated)" / "Longitude (generated)"  — coord projections
    #   * "<column> (<source>.csv)"                        — passthrough columns
    #     from a specific underlying source table
    # Neither entity exists in the PBI model, so the visual binds to nothing
    # and renders empty. We resolve via two indices:
    #   _coord_targets  : Latitude/Longitude → real (table, column), from the
    #                     `data_category` tags set by _infer_coordinate_category
    #   _table_by_norm  : normalised table name → real table name, so a
    #                     "(tbl_sales.csv)" suffix maps onto `tbl_sales`
    # and a column-set lookup per table for the cleaned column name.
    _real_tables_idx = {t["name"] for t in tables}
    _coord_targets: dict[str, tuple[str, str]] = {}
    _table_columns: dict[str, set] = {}
    for _t in tables:
        _table_columns[_t["name"]] = {_c["name"] for _c in _t.get("columns", [])}
        for _c in _t.get("columns", []):
            _dc = _c.get("data_category")
            if _dc in ("Latitude", "Longitude") and _dc not in _coord_targets:
                _coord_targets[_dc] = (_t["name"], _c["name"])

    import re as _ext_re
    _table_by_norm = {
        _ext_re.sub(r"[^a-z0-9]", "", t["name"].lower()): t["name"] for t in tables
    }
    _COL_SUFFIX_RE = _ext_re.compile(r"^(.*?)\s*\(([^)]+)\)\s*$")

    def _resolve_federated_field(role: str, tbl: str, col: str):
        """Resolve a federated-style field binding.

        Returns (role, table, column) on a real-model binding, or None when
        the field references a non-existent table and we cannot map it to
        anything in the model (Tableau-internal pseudo-fields like
        "Measure Names" / "Multiple Values" / ":Measure Names" have no PBI
        equivalent — dropping the field is the only safe option, since
        emitting `federated.<hash>` produces a permanently broken visual)."""
        if not tbl or tbl in _real_tables_idx:
            return role, tbl, col
        cl = (col or "").lower()
        # Coord projections — Tableau auto-generates Latitude/Longitude as
        # virtual columns; redirect onto the model's real lat/long columns.
        if "latitude" in cl:
            dc = "Latitude"
        elif "longitude" in cl:
            dc = "Longitude"
        else:
            dc = None
        if dc and dc in _coord_targets:
            real_tbl, real_col = _coord_targets[dc]
            return dc, real_tbl, real_col
        # "<col> (<source>.csv)" / "(<source>)" pattern — strip the suffix,
        # resolve the source table by normalised-name lookup, and rebind to
        # the matching column if it exists on that table.
        m = _COL_SUFFIX_RE.match(col or "")
        if m:
            clean_col = m.group(1).strip()
            inner = m.group(2).strip()
            inner_base = _ext_re.sub(r"\.(csv|xlsx|xls|parquet|json|tsv|txt)$",
                                     "", inner, flags=_ext_re.IGNORECASE)
            real_tbl = _table_by_norm.get(_ext_re.sub(r"[^a-z0-9]", "",
                                                      inner_base.lower()))
            if real_tbl and clean_col in _table_columns.get(real_tbl, set()):
                return role, real_tbl, clean_col
        return None

    # Tableau-only / layout / chrome zones that have NO standalone Power BI
    # visual equivalent. Emitting any of these produces a visualType that PBI
    # registers as a missing custom visual and renders as a blank tile (the
    # "type is set but nothing shows" symptom). They carry no data binding, so
    # dropping them loses nothing. The RE's visual-type classification varies
    # run-to-run (e.g. `color` vs `color_legend`, `container` vs `layout`), so
    # this set is deliberately broad and matched case-insensitively.
    _SKIP_VISUAL_TYPES = {
        "color", "color_legend", "colour_legend", "legend",
        "container", "horizontal_container", "vertical_container",
        "floating_container", "layout", "layout-basic", "layout_basic",
        "layout-flow", "layout_flow", "group", "blank", "empty",
        "spacer", "padding", "separator", "divider",
        "sheet-wrapper", "sheet_wrapper", "dashboard-wrapper",
        "dashboard_wrapper", "page-wrapper", "page_wrapper",
        "title", "flipboard", "flipboard-nav", "flipboard_nav",
        "navigation", "nav",
    }

    for pg in raw_pages:
        visuals = []
        for v in pg.get("visuals", []):
            raw_type = v.get("visual_type") or v.get("mark_type") or "unknown"
            if raw_type.strip().lower() in _SKIP_VISUAL_TYPES:
                continue
            mapped_type = _norm_visual_type(raw_type)

            pos = v.get("position") or {}
            fields = []
            for f in v.get("fields", []):
                role = f.get("role", "Values")
                # skip filter and label roles — not query bindings in PBIP
                if role.lower() in ("filter", "label"):
                    continue
                resolved = _resolve_federated_field(
                    role, f.get("table") or "", f.get("column") or "")
                if resolved is None:
                    # Dead reference (e.g. `federated.<hash>.Measure Names`)
                    # that we couldn't rebind to a real column. Drop the
                    # field — leaving it would make the entire visual fail
                    # to render. Visuals with no remaining fields are dropped
                    # downstream by the writer.
                    continue
                role, f_tbl, f_col = resolved
                fld = {
                    "role": role,
                    "table": f_tbl,
                    "column": f_col,
                    "aggregation": f.get("aggregation", ""),
                }
                # Carry the source field's display label (e.g. "No of Policies")
                # so the writer can emit it as the projection displayName.
                if f.get("display_name"):
                    fld["display_name"] = f["display_name"]
                # Preserve the RE's dimension-force flag for a Tableau group/
                # string calc bound to a categorical role, so the mapper/writer
                # emit it as a Column (dimension) rather than a Measure.
                if f.get("_force_dimension"):
                    fld["_force_dimension"] = True
                fields.append(fld)

            # Enrich with Postgres chart-mapping data if available
            obj_id = v.get("id", "")
            if obj_id in pg_viz_map:
                pg_row = pg_viz_map[obj_id]
                if pg_row.get("visual_type"):
                    mapped_type = _norm_visual_type(pg_row["visual_type"])

            vis_title = v.get("title") or ""

            visuals.append({
                "id": obj_id,
                # Original source visual-container id (PowerBI .pbix), carried so
                # the writer can remap a captured bookmark's visualContainers onto
                # the regenerated visuals (section 7). None for flows that don't
                # supply it.
                "source_visual_id": v.get("source_visual_id"),
                # Field-parameter bindings (role -> driving field parameter), so
                # the writer can re-bind the slicer to the visual it reconfigures.
                "field_parameters_by_role": v.get("field_parameters_by_role"),
                "title": vis_title,
                "type_raw": raw_type,
                "visualType": mapped_type,
                "source": source,
                "fields": fields,
                "position": {
                    "x": pos.get("x", 0),
                    "y": pos.get("y", 0),
                    "w": pos.get("width", 400),
                    "h": pos.get("height", 300),
                    "z": pos.get("z_order", 0),
                },
                "has_border": v.get("has_border", False),
                # Image visuals carry an `imageId` (Postgres key) and the
                # original `imageUrl` filename — preserved so the writer can
                # pull the binary from jnj_poc.report_images and embed it.
                "imageId":  v.get("imageId")  or v.get("image_id"),
                "imageUrl": v.get("imageUrl") or v.get("image_url"),
                # Textbox body content: Tableau text objects carry their
                # rich text in `content` (multi-line) — the writer emits
                # this into the PBI textbox's paragraphs property, NOT the
                # title chrome (which only accepts a single-line literal).
                "content": v.get("content"),
                # Style / colour metadata. Priority:
                #   1. explicit camelCase `formatting` (the contract), else
                #   2. ADAPT the RE's snake_case structured `style` block
                #      (Tableau & Power BI both emit this) → camelCase.
                # The structured-style adapter is what makes Tableau colours
                # work — Tableau ships no ready-made PBIP under `style.raw`, so
                # without this its visuals would render unstyled. For Power BI
                # the authoritative `style.raw` (below) still wins in the writer.
                "formatting": v.get("formatting") or (
                    _styles.adapt_structured_style(v.get("style"))
                    if _styles else None),
                # Ready-made PBIP emitted by the RE under `style.raw`:
                #   raw.objects   → visual.objects (legend, dataPoint, labels,
                #                   valueAxis, categoryAxis, slicer, grid, …)
                #   raw.vcObjects → visual.visualContainerObjects (title,
                #                   border, background, dropShadow, …)
                # This is the AUTHORITATIVE form (the RE already resolved
                # colours, theme refs and fonts) so the writer emits it as-is.
                # `... or {}` guards against `raw` being present-but-null (which
                # Tableau inputs emit) — `.get("raw", {})` would NOT default on
                # a null value, only on a missing key.
                "raw_objects": ((v.get("style") or {}).get("raw") or {}).get("objects"),
                "raw_vc_objects": ((v.get("style") or {}).get("raw") or {}).get("vcObjects"),
            })
            if _dbg:
                _in_map = raw_type.lower().replace(" ", "_") in _VISUAL_MAP
                _pg_name = pg.get("display_name") or pg.get("page_id", "")
                _dbg.log_norm_visual_type(_pg_name, obj_id, v.get("title", ""),
                                          raw_type, mapped_type, _in_map)

        pages.append({
            "name": pg.get("display_name") or pg.get("page_id", "Page1"),
            # Original source page id (PowerBI .pbix section name). A bookmark's
            # explorationState keys its sections / activeSection by this id, so
            # the writer needs it to remap bookmarks onto the generated pages.
            "page_id": pg.get("page_id"),
            "width": pg.get("width", 1280),
            "height": pg.get("height", 720),
            "visuals": visuals,
            # Page-level image references (Postgres image_id UUIDs) — the
            # canvas background and the wallpaper. Preserved so the writer
            # can pull the binary and apply it to the page.
            "background_image_id": pg.get("background_image_id"),
            "wallpaper_image_id":  pg.get("wallpaper_image_id"),
            # Canvas & environment style metadata (section 1 of the style
            # contract — pageType, displayArea, verticalAlignment, background
            # colour/transparency, wallpaper). Passed through VERBATIM; the
            # writer turns it into page.json `objects` + type/displayOption.
            # When the RE emits its snake_case `styles` block instead, derive a
            # canvas from it (vertical alignment) and carry the ready-made page
            # PBIP objects (`styles.raw`) + page type / display option.
            "canvas": pg.get("canvas") or _canvas_from_styles(pg.get("styles")),
            "raw_objects": (pg.get("styles") or {}).get("raw")
                           if isinstance(pg.get("styles"), dict) else None,
            "displayOption": (pg.get("styles") or {}).get("display_option")
                             if isinstance(pg.get("styles"), dict) else None,
            "pageType": (pg.get("styles") or {}).get("page_type")
                        if isinstance(pg.get("styles"), dict) else None,
            # Edit interactions / cross-filtering between visuals (section 8).
            # List of {source, target, interactionType}; the writer translates
            # the visual ids to generated names and emits page.visualInteractions.
            "interactions": pg.get("interactions"),
            # Filter definitions incl. per-filter locking (IsLocked / IsHidden)
            # and filterType (Basic/Advanced/TopN/RelativeDate) — section 1.
            # Carried VERBATIM (PBIP page.json `filterConfig` shape).
            "filterConfig": pg.get("filterConfig"),
        })

    # Synthesize calculated tables for data-source aliases that aren't backed
    # by a real `tables[]` entry. Tableau self-joins (and similar workflows in
    # other tools) declare an alias name in `data_sources[].paths` but never
    # emit a separate table block — the source is just the same CSV joined to
    # itself. Visual fields then bind to e.g. `tbl_sales1.Correlation` and PBI
    # refuses to load because no `tbl_sales1` partition exists. We resolve
    # each alias back to its base by stripping any trailing digits (the
    # standard Tableau alias convention is `<base>1`, `<base>2`, …) and, if
    # the stripped name is a real table, emit a DAX calculated table
    # `<alias> = <base>` so the alias has a backing partition. The columns and
    # measures are inherited automatically by the DAX engine because they
    # come from `<base>`.
    _existing_names = {t["name"] for t in tables}
    _alias_names: set[str] = set()
    for ds in data.get("data_sources", []) or []:
        for p in (ds.get("paths") or []):
            if isinstance(p, str) and p and p not in _existing_names:
                _alias_names.add(p)
    import re as _alias_re
    _ALIAS_SUFFIX_RE = _alias_re.compile(r"\d+$")
    for alias in sorted(_alias_names):
        base = _ALIAS_SUFFIX_RE.sub("", alias)
        if not base or base == alias or base not in _existing_names:
            continue
        base_tbl = table_index[base]
        # Copy columns shape (without expressions) so the writer & mapper see
        # the alias's column schema. The actual data comes from the DAX
        # `<alias> = <base>` partition, so the columns inherit the base's
        # types and values at runtime.
        alias_cols = []
        for _c in base_tbl.get("columns", []):
            alias_cols.append({
                "name": _c["name"],
                "dataType": _c.get("dataType", "string"),
                "nullable": _c.get("nullable", True),
                "description": _c.get("description", ""),
                "used_in_relationships": _c.get("used_in_relationships", False),
                "used_in_filters": _c.get("used_in_filters", False),
                "distinct_count_high": _c.get("distinct_count_high", False),
                "semantic_role": _c.get("semantic_role"),
                "data_category": _c.get("data_category"),
                "variations": [],
            })
        tables.append({
            "name": alias,
            "table_type": "calculated",
            "columns": alias_cols,
            "measures": [],
            "transformations": [],
            "dax_table_expression": base,
            "powerquery_expression": None,
            "description": f"Alias of {base} (synthesized for self-join / data-source alias).",
            "hierarchies": [],
        })
        _existing_names.add(alias)
        table_index[alias] = tables[-1]
        if _dbg:
            try:
                _dbg.log_alias_synth(alias, base)
            except Exception:
                pass

    # Rewrite self-referential relationships to use the alias when one exists.
    # The RE expresses Tableau self-joins as `from_table == to_table` (both
    # endpoints point at the base table id). PBI rejects a relationship that
    # joins a table to itself on the same column; once we've synthesized the
    # alias as a real table, redirect the right side to that alias so the
    # self-join becomes a legitimate cross-table relationship in the model.
    _base_to_alias: dict[str, str] = {}
    for _t in tables:
        if _t.get("table_type") != "calculated":
            continue
        _base = (_t.get("dax_table_expression") or "").strip()
        if _base and _base in _existing_names and _base != _t["name"]:
            _base_to_alias.setdefault(_base, _t["name"])
    for _r in relationships:
        if (_r.get("from_table") and _r.get("to_table")
                and _r["from_table"] == _r["to_table"]
                and _r["from_table"] in _base_to_alias):
            _r["to_table"] = _base_to_alias[_r["from_table"]]

    result = {
        "source": source,
        "report_name": data.get("name", "MyReport").replace(" ", "_").replace(".twb", "").replace(".pbix", ""),
        "original_name": data.get("name", "MyReport"),
        "model_id": data.get("model_id", ""),
        "tables": tables,
        "relationships": relationships,
        "pages": pages,
        "all_measures": [{"table": t, **m} for t, m in all_measures],
    }
    # Report-level theme / design tokens (section 10 of the style contract:
    # themeDataColors, visualStyles). Looked up in the visualizations block
    # first (where the RE attaches report-wide rendering metadata), then at
    # the model root. Passed through VERBATIM for the writer to emit as a
    # custom theme referenced from report.json.
    _theme = (viz_data.get("theme") if isinstance(viz_data, dict) else None) or data.get("theme")
    if _theme:
        # Normalise the RE's {name, data_palette, semantic_colors} (or an
        # already-camelCase theme) onto the build_custom_theme contract.
        result["theme"] = (_styles.normalize_theme(_theme) if _styles else _theme) or _theme
    # Bookmarks (section 7) — report-level list of captured states. Normalised
    # from the RE's snake_case + `raw.explorationState` shape for the writer.
    _bookmarks = (viz_data.get("bookmarks") if isinstance(viz_data, dict) else None) or data.get("bookmarks")
    if _bookmarks:
        result["bookmarks"] = (_styles.normalize_bookmarks(_bookmarks) if _styles else _bookmarks) or _bookmarks
    # Row-Level Security roles — passed through verbatim (filter DAX is
    # security-critical; never transformed). The writer emits one TMDL per role.
    # Both flows populate the common-model `roles` section (Power BI from its
    # RLS metadata, Tableau by converting user filters), so this stays
    # source-agnostic.
    _roles = data.get("roles")
    if _roles:
        result["roles"] = _roles
    if _dbg:
        _dbg.flush_parse_types()
        _dbg.flush_parse_visual_types()
        _dbg.log_intermediate(result)
    return result


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Parse common-model JSON → intermediate.json")
    ap.add_argument("--input", required=True, help="Path to input JSON")
    ap.add_argument("--output", required=True, help="Path for intermediate.json")
    ap.add_argument("--source", choices=["tableau", "powerbi"], default=None)
    ap.add_argument("--use-postgres", action="store_true",
                    help="Enrich with Postgres jnj_poc data if report found")
    args = ap.parse_args()

    with open(args.input) as f:
        data = json.load(f)

    source = args.source or detect_source(data)
    print(f"[parser] Detected source: {source}")

    db_rows = None
    if args.use_postgres:
        from db import find_report_by_name, load_report_data
        report_id = find_report_by_name(data.get("name", ""))
        if report_id:
            print(f"[parser] Loading Postgres data for report_id={report_id}")
            db_rows = load_report_data(report_id)
        else:
            print("[parser] Report not found in Postgres, proceeding with JSON only")

    result = parse_common_model(data, source, db_rows)

    # UTF-8 + ensure_ascii=False so the intermediate JSON round-trips BOTH
    # English and non-Latin text (Japanese, etc.) intact. ASCII is byte-for-
    # byte identical either way; this only adds correct non-ASCII handling.
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"[parser] Parsed {source} -> {args.output}")
    print(f"  Tables: {len(result['tables'])}, Pages: {len(result['pages'])}, "
          f"Relationships: {len(result['relationships'])}")


if __name__ == "__main__":
    main()
