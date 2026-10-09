"""
Power BI Layout to Data Model Mapper

This script maps the Layout file from a Power BI report to the extracted data model,
identifying which tables, columns, measures, and relationships are used by each visual.
"""

import json
from pathlib import Path
from typing import Dict, List, Any


# Power BI QueryAggregateFunction enum (prototypeQuery Select `Aggregation.Function`).
# The Layout's auto-generated `Name` string is STALE — it can read "Min(...)" /
# "Sum(...)" even when the field's true aggregation differs, or when the field is
# "don't summarize" (no aggregation at all), or it uses a measure's DISPLAY name
# instead of the underlying measure. So the authoritative source for a visual
# field is the Select item's STRUCTURE, never its `Name`.
_PBI_AGG_FUNC_NAME = {
    0: "Sum", 1: "Avg", 2: "Min", 3: "Max", 4: "Count",
    5: "CountNonNull", 6: "Median", 7: "StandardDeviation", 8: "Variance",
}


def _select_entity(expr: dict, from_map: dict) -> str:
    """Resolve a Select expression's table entity — from SourceRef.Entity, or the
    From-clause alias in SourceRef.Source (e.g. Source "d" -> the From entity)."""
    ref = (expr or {}).get("SourceRef") or {}
    if ref.get("Entity"):
        return ref["Entity"]
    return from_map.get(ref.get("Source"), ref.get("Source") or "")


def _select_to_queryref(select_item: dict, from_map: dict):
    """Build the FAITHFUL (name_key, query_ref, display_name) for a prototypeQuery
    Select item from its STRUCTURE — the real `Aggregation.Function` code (or its
    absence = "don't summarize"), the underlying Column/Measure `Property`, and the
    resolved entity — instead of the stale auto-generated `Name`. `name_key` is the
    item's `Name` (used to match the visual's `projections` queryRefs). Returns the
    original `Name` unchanged for any shape we don't recognise (never regress)."""
    name_key = select_item.get("Name") or ""
    display = select_item.get("NativeReferenceName")
    if "Aggregation" in select_item:
        agg = select_item["Aggregation"] or {}
        inner = agg.get("Expression") or {}
        colm = inner.get("Column") or inner.get("Measure") or {}
        ent = _select_entity(colm.get("Expression"), from_map)
        prop = colm.get("Property")
        fname = _PBI_AGG_FUNC_NAME.get(agg.get("Function"))
        if ent and prop:
            return name_key, (f"{fname}({ent}.{prop})" if fname else f"{ent}.{prop}"), display
    elif "Column" in select_item:
        col = select_item["Column"] or {}
        ent = _select_entity(col.get("Expression"), from_map)
        prop = col.get("Property")
        if ent and prop:
            return name_key, f"{ent}.{prop}", display          # plain column => "don't summarize"
    elif "Measure" in select_item:
        ms = select_item["Measure"] or {}
        ent = _select_entity(ms.get("Expression"), from_map)
        prop = ms.get("Property")
        if ent and prop:
            return name_key, f"{ent}.{prop}", display          # measure: bind by its real property
    return name_key, name_key, display


def _rebuild_projections_from_select(single_visual: dict) -> dict:
    """Return the visual's `projections` with each field's queryRef rebuilt from the
    authoritative `prototypeQuery.Select[]` (true aggregation function / plain column /
    measure property + resolved entity), instead of the stale `Name`. Falls back to
    the original projections when there is no prototypeQuery to derive from."""
    projections = single_visual.get("projections") or {}
    pq = single_visual.get("prototypeQuery") or {}
    selects = pq.get("Select") or []
    if not (projections and selects):
        return projections
    from_map = {f.get("Name"): f.get("Entity")
                for f in (pq.get("From") or []) if f.get("Name")}
    by_name = {}
    for se in selects:
        nm, qr, disp = _select_to_queryref(se, from_map)
        if nm:
            by_name[nm] = (qr, disp)
    out = {}
    for role, lst in projections.items():
        new_lst = []
        for entry in (lst or []):
            if isinstance(entry, dict) and entry.get("queryRef") in by_name:
                qr, disp = by_name[entry["queryRef"]]
                ne = dict(entry)
                ne["queryRef"] = qr
                if disp and not ne.get("displayName"):
                    ne["displayName"] = disp
                new_lst.append(ne)
            else:
                new_lst.append(entry)
        out[role] = new_lst
    return out


class LayoutDataModelMapper:
    def __init__(self, layout_path: str, datamodel_folder: str):
        """
        Initialize the mapper with paths to layout and data model files.

        Args:
            layout_path: Path to the Layout file from extracted PBIX
            datamodel_folder: Path to folder containing extracted data model JSON files
        """
        self.layout_path = Path(layout_path)
        self.datamodel_folder = Path(datamodel_folder)

        # Load layout - try different encodings
        self.layout = self._load_layout()

        # Load data model components
        self.schema = self._load_json('schema.json')
        self.tables = self._load_json('tables_list.json')
        self.relationships = self._load_json('relationships.json')
        self.dax_measures = self._load_json('dax_measures.json')
        self.dax_tables = self._load_json('dax_tables.json')

    def _load_layout(self) -> Dict:
        """Load layout file with encoding fallback.

        PBIXRay sometimes writes the Layout file in UTF-16-LE (the native Power BI
        on-disk format). We try common encodings in order and fall back gracefully.
        After parsing, we do a round-trip through json.dumps / json.loads with
        ensure_ascii=False so any \\uXXXX-escaped CJK / Unicode characters are
        decoded to their real code-points before the mapper processes them.
        """
        encodings = ['utf-8', 'utf-16-le', 'utf-16-be', 'latin-1', 'cp1252']

        parsed = None
        for encoding in encodings:
            try:
                with open(self.layout_path, 'r', encoding=encoding, errors='strict') as f:
                    content = f.read()
                parsed = json.loads(content)
                break
            except (UnicodeDecodeError, UnicodeError, json.JSONDecodeError):
                continue

        if parsed is None:
            # Last-resort: utf-8 with replacement characters
            try:
                with open(self.layout_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                parsed = json.loads(content)
            except (OSError, ValueError) as e:
                raise RuntimeError(f"Failed to load layout file: {e}") from e

        # Round-trip ensures \\uXXXX escape sequences become real Unicode characters
        return json.loads(json.dumps(parsed, ensure_ascii=False))
    def _load_json(self, filename: str) -> Any:
        """Load a JSON file from the data model folder."""
        filepath = self.datamodel_folder / filename
        if filepath.exists():
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    def _parse_filters(self, filters_raw) -> List[Dict]:
        """Parse a filters JSON string/list into normalized filter dicts."""
        if not filters_raw:
            return []

        if isinstance(filters_raw, str):
            try:
                filters_list = json.loads(filters_raw)
            except (json.JSONDecodeError, TypeError):
                return []
        elif isinstance(filters_raw, list):
            filters_list = filters_raw
        else:
            return []

        result = []
        for f in filters_list:
            if not isinstance(f, dict):
                continue

            filter_obj = f.get('filter', {})
            if not isinstance(filter_obj, dict):
                filter_obj = {}

            # Table comes from filter.From[0].Entity
            table = ''
            from_list = filter_obj.get('From', [])
            if from_list and isinstance(from_list[0], dict):
                table = from_list[0].get('Entity', '')

            # Column comes from expression.Column.Property
            column = ''
            expr = f.get('expression', {})
            if isinstance(expr, dict):
                col_expr = expr.get('Column', {})
                if isinstance(col_expr, dict):
                    column = col_expr.get('Property', '')
                    # Also try to get table from expression if not found above
                    if not table:
                        src = col_expr.get('Expression', {}).get('SourceRef', {})
                        if isinstance(src, dict):
                            table = src.get('Entity', table)

            filter_type = f.get('type', 'Unknown')

            # Extract values from basic/in-list filters
            values = []
            for condition in filter_obj.get('Where', []):
                if not isinstance(condition, dict):
                    continue
                cond = condition.get('Condition', {})
                if not isinstance(cond, dict):
                    continue
                in_filter = cond.get('In', {})
                if isinstance(in_filter, dict):
                    for val_group in in_filter.get('Values', []):
                        if isinstance(val_group, list):
                            for v in val_group:
                                if isinstance(v, dict):
                                    lit = v.get('Literal', {})
                                    if isinstance(lit, dict):
                                        values.append(lit.get('Value', ''))

            entry: Dict[str, Any] = {
                'table': table,
                'column': column,
                'filter_type': filter_type,
            }
            if values:
                entry['values'] = values

            result.append(entry)

        return result

    def _extract_visual_title(self, single_visual: dict) -> str:
        """Extract the display title from a visual's config objects."""
        for objects_key in ('objects', 'vcObjects'):
            try:
                title_entries = single_visual.get(objects_key, {}).get('title', [])
                if isinstance(title_entries, list):
                    title_entries = title_entries[0] if title_entries else {}
                if isinstance(title_entries, dict):
                    val = (title_entries
                           .get('properties', {})
                           .get('text', {})
                           .get('expr', {})
                           .get('Literal', {})
                           .get('Value', ''))
                    if val:
                        return val.strip("'")
            except (KeyError, IndexError, TypeError):
                continue
        return ''

    def _build_visual_bookmark_map(self) -> Dict[str, List[str]]:
        """
        Parse Layout bookmarks and return {visual_id: [bookmark_display_names]}.
        Visuals that share a bookmark name are part of the same hide/show group.
        Debug output is written to bookmark_debug.txt next to the layout file.
        """
        debug_lines: List[str] = []

        def log(msg: str) -> None:
            debug_lines.append(msg)

        # Bookmarks live inside layout["config"] (a JSON string), not layout["bookmarks"]
        config_raw = self.layout.get('config', '{}')
        try:
            report_config = json.loads(config_raw) if isinstance(config_raw, str) else config_raw
        except (json.JSONDecodeError, TypeError):
            report_config = {}
        raw_bookmarks = report_config.get('bookmarks', [])

        log(f"Top-level Layout keys: {list(self.layout.keys())}")
        log(f"layout['config'] keys: {list(report_config.keys())}")
        log(f"Total bookmarks in layout['config']: {len(raw_bookmarks)}")

        if not raw_bookmarks:
            log("WARNING: No bookmarks found in layout['config']['bookmarks'].")

        visual_bookmark_map: Dict[str, List[str]] = {}

        for i, bookmark in enumerate(raw_bookmarks):
            display_name = bookmark.get('displayName', bookmark.get('name', ''))
            log(f"\nBookmark #{i}: displayName={repr(display_name)} keys={list(bookmark.keys())}")

            exploration_state = bookmark.get('explorationState', {})
            log(f"  explorationState type: {type(exploration_state).__name__}")

            if isinstance(exploration_state, str):
                log(f"  explorationState is a string (length {len(exploration_state)}), parsing JSON...")
                try:
                    exploration_state = json.loads(exploration_state)
                    log(f"  parsed OK, top-level keys: {list(exploration_state.keys())}")
                except (json.JSONDecodeError, TypeError) as e:
                    log(f"  FAILED to parse explorationState: {e}")
                    continue

            if not isinstance(exploration_state, dict):
                log(f"  explorationState is not a dict (type={type(exploration_state).__name__}) — skipping")
                continue

            sections = exploration_state.get('sections', {})
            log(f"  sections keys: {list(sections.keys())}")

            for page_id, section_data in sections.items():
                if not isinstance(section_data, dict):
                    log(f"  page '{page_id}': section_data is not a dict — skipping")
                    continue
                visual_containers = section_data.get('visualContainers', {})
                log(f"  page '{page_id}': {len(visual_containers)} visual containers → {list(visual_containers.keys())[:5]}")
                for visual_id in visual_containers:
                    if display_name:
                        visual_bookmark_map.setdefault(visual_id, [])
                        if display_name not in visual_bookmark_map[visual_id]:
                            visual_bookmark_map[visual_id].append(display_name)

        log(f"\nFinal visual→bookmark map ({len(visual_bookmark_map)} visuals with bookmarks):")
        for vid, bmarks in visual_bookmark_map.items():
            log(f"  visual_id={vid!r} → {bmarks}")

        # Save to file next to the layout file for easy inspection
        debug_path = self.layout_path.parent / "bookmark_debug.txt"
        try:
            with open(debug_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(debug_lines))
            print(f"[bookmark_debug] Debug info saved to: {debug_path}")
        except Exception as e:
            print(f"[bookmark_debug] Could not write debug file: {e}")

        return visual_bookmark_map

    def analyze_visual(self, visual_config: Dict, page_name: str = '') -> Dict[str, Any]:
        """Analyze a single visual — passes structured data to LLM for field extraction."""
        config_str = visual_config.get('config', '{}')

        if not config_str or config_str.strip() in ('', '{}'):
            print(f"  [layout_mapper] SKIP: empty config on page '{page_name}'")
            return {'error': 'Empty config'}

        try:
            config = json.loads(config_str)
        except json.JSONDecodeError as e:
            print(f"  [layout_mapper] SKIP: config JSON parse error on page '{page_name}': {e}")
            return {'error': f'Invalid JSON in config: {e}'}

        visual_id = config.get('name', 'Unknown')
        single_visual = config.get('singleVisual', {})

        if not single_visual:
            print(f"  [layout_mapper] SKIP: no singleVisual in config for visual '{visual_id}' on page '{page_name}'")
            return {'error': 'No singleVisual'}

        visual_type = single_visual.get('visualType', 'Unknown')
        title = self._extract_visual_title(single_visual)
        # Rebuild projections from the authoritative prototypeQuery.Select[] — the
        # raw `projections` queryRefs use the stale auto-generated `Name`, which
        # misreports aggregation (e.g. CountNonNull shown as "Min", a plain
        # "don't summarize" column shown as "Sum(...)") and uses measure display
        # names instead of the real measure. This makes the captured aggregation
        # and field identity faithful to the source.
        projections = _rebuild_projections_from_select(single_visual)
        data_transforms = single_visual.get('dataTransforms', {})
        # filters = self._parse_filters(visual_config.get('filters', ''))  # TODO: re-enable when UI supports visual filters

        print(f"  [layout_mapper] OK  visual_id={visual_id} type={visual_type} title={repr(title)} projections_roles={list(projections.keys())} has_dataTransforms={bool(data_transforms)}")

        return {
            'visual_id': visual_id,
            'visual_type': visual_type,
            'title': title,
            'position': {
                'x': visual_config.get('x'),
                'y': visual_config.get('y'),
                'width': visual_config.get('width'),
                'height': visual_config.get('height'),
                'z_order': visual_config.get('z'),
            },
            'projections': projections,
            'data_transforms': data_transforms,
            # 'filters': filters,  # TODO: re-enable when UI supports visual filters
        }

    def map_layout_to_datamodel(self) -> Dict[str, Any]:
        """Main method — produces report_pages matching the input.json structure."""
        # visual_bookmark_map = self._build_visual_bookmark_map()  # TODO: re-enable when UI supports bookmarks
        # report_filters = self._parse_filters(self.layout.get('filters', ''))  # TODO: re-enable when UI supports report filters

        mapping = {
            'report_metadata': {
                'theme': self.layout.get('theme', ''),
                'total_sections': len(self.layout.get('sections', [])),
                # 'report_filters': report_filters,  # TODO: re-enable when UI supports report filters
            },
            'sections': []
        }

        for section in self.layout.get('sections', []):
            page_id = section.get('name', '')
            display_name = section.get('displayName', page_id or 'Unnamed')
            visual_containers = section.get('visualContainers', [])
            # page_filters = self._parse_filters(section.get('filters', ''))  # TODO: re-enable when UI supports page filters

            print(f"\n[layout_mapper] Page '{display_name}' ({page_id}): {len(visual_containers)} visual containers found")

            visuals = []
            for vc in visual_containers:
                vis = self.analyze_visual(vc, display_name)
                # if 'error' not in vis:  # TODO: re-enable when UI supports bookmarks
                #     vis['bookmarks'] = visual_bookmark_map.get(vis.get('visual_id', ''), [])
                visuals.append(vis)

            dropped = [v for v in visuals if 'error' in v]
            visuals = [v for v in visuals if 'error' not in v]

            if dropped:
                print(f"  [layout_mapper] WARNING: {len(dropped)} visuals dropped on page '{display_name}'")
            print(f"  [layout_mapper] {len(visuals)} visuals successfully extracted on page '{display_name}'")

            section_data = {
                'page_id': page_id,
                'display_name': display_name,
                'width': section.get('width'),
                'height': section.get('height'),
                # 'filters': page_filters,  # TODO: re-enable when UI supports page filters
                'visuals': visuals,
            }
            mapping['sections'].append(section_data)

        return mapping

    def generate_report(self, output_path: str = None):
        """Generate a comprehensive mapping report."""
        mapping = self.map_layout_to_datamodel()

        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(mapping, f, indent=2, ensure_ascii=False)

        return mapping


def map_layout_to_datamodel(layout_path: str, datamodel_folder: str, output_path: str = None) -> Dict[str, Any]:
    """
    Utility function to map PowerBI layout to data model.

    Args:
        layout_path: Path to the Layout file from extracted PBIX
        datamodel_folder: Path to folder containing extracted data model JSON files
        output_path: Optional path to save the mapping JSON

    Returns:
        Dictionary containing the mapping results
    """
    mapper = LayoutDataModelMapper(layout_path, datamodel_folder)
    return mapper.generate_report(output_path)
