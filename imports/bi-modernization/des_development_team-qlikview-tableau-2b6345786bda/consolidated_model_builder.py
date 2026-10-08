"""
consolidated_model_builder.py
------------------------------
Builds the `consolidated_model` element appended to the Common Model JSON output.

The centrepiece is `node_graph` — an Alteryx-style directed data-flow graph where
every entity (data_source → table → ingestion_step → relationship → calculation →
visual) is represented as a node with explicit `prev_nodes` and `next_nodes` links.

Also produces flat catalog sub-sections for UI tabular display:
  column_catalog, ingestion_steps, visual_field_usage, relationships, calculations.
"""

import re


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    """Convert an arbitrary string to a safe snake_case node_id fragment."""
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')


def _ensure_id(node_id: str, nodes: dict) -> str:
    """Return node_id unchanged; just a guard – caller must avoid duplicate ids."""
    return node_id


def _safe_add_edge(nodes: dict, from_id: str, to_id: str) -> None:
    """Add a directed edge from_id → to_id, guarding against duplicates."""
    if from_id in nodes and to_id not in nodes[from_id]["next_nodes"]:
        nodes[from_id]["next_nodes"].append(to_id)
    if to_id in nodes and from_id not in nodes[to_id]["prev_nodes"]:
        nodes[to_id]["prev_nodes"].append(from_id)


# ---------------------------------------------------------------------------
# Core node-graph builder
# ---------------------------------------------------------------------------

def _build_node_graph(data: dict) -> list:
    """
    Build an Alteryx-style directed node graph from a Common Model dict.

    Node types (in data-flow order):
        data_source  → raw file / database / API source
        table        → Power Query / SQL table (output of ingestion)
        ingestion_step → individual Power Query M step (chained within each table)
        relationship → model join between two tables
        calculation  → DAX measure / calculated field
        visual       → a single chart / card / slicer on a report page
    """
    nodes: dict = {}   # node_id → node-dict (ordered for output)

    # -----------------------------------------------------------------------
    # Pass 1 – DATA SOURCE nodes
    # -----------------------------------------------------------------------
    ds_name_to_id: dict = {}   # source name → node_id

    for i, src in enumerate(data.get("data_sources", [])):
        src_name = src.get("name", f"source_{i}")
        node_id = f"ds_{_slugify(src_name)}"
        # deduplicate (same file can appear multiple times in the schema)
        if node_id in nodes:
            node_id = f"{node_id}_{i}"
        ds_name_to_id[src_name] = node_id
        nodes[node_id] = {
            "node_id": node_id,
            "node_name": src_name,
            "node_type": "data_source",
            "description": (
                f"{src.get('source_type', 'Source')} data source — {src_name}"
            ),
            "attributes": {
                "source_type": src.get("source_type"),
                "connection_mode": src.get("connection_mode"),
                "path": src.get("path"),
                "server": src.get("server"),
                "database": src.get("database"),
            },
            "prev_nodes": [],
            "next_nodes": [],
        }

    # -----------------------------------------------------------------------
    # Pass 2 – TABLE + INGESTION STEP nodes (first sweep)
    # -----------------------------------------------------------------------
    tbl_name_to_id: dict = {}   # table name → node_id
    tbl_step_ids: dict  = {}    # table name → [step_node_ids in order]

    def _find_source_for_table(tbl_name: str) -> str | None:
        """Best-effort match: table name → data_source node_id."""
        slug_t = re.sub(r'[^a-z0-9]', '', tbl_name.lower())
        for src_name, ds_id in ds_name_to_id.items():
            slug_s = re.sub(r'[^a-z0-9]', '', src_name.lower())
            if slug_t == slug_s or slug_t in slug_s or slug_s in slug_t:
                return ds_id
        return None

    def _find_parent_table_ref(ingestion_steps: list) -> str | None:
        """
        If the first M step references another table via  Source = #"TableName"
        return that table name (used for derived / lookup tables like Hirarachy Table).
        """
        if not ingestion_steps:
            return None
        pq = ingestion_steps[0].get("native_expressions", {}).get("powerquery", "")
        m = re.search(r'Source\s*=\s*#"([^"]+)"', pq)
        if m:
            ref = m.group(1)
            # skip if the reference looks like an absolute file path
            if "\\" not in ref and "/" not in ref:
                return ref
        return None

    for tbl in data.get("tables", []):
        tbl_name = tbl.get("name", "")
        tbl_id   = f"tbl_{_slugify(tbl_name)}"
        tbl_name_to_id[tbl_name] = tbl_id

        steps = tbl.get("ingestion", {}).get("steps", [])
        parent_ref   = _find_parent_table_ref(steps)
        direct_src   = _find_source_for_table(tbl_name)

        # -- Ingestion step nodes (chained: step_1 → step_2 → … → step_n) --
        step_ids = []
        for step in steps:
            order   = step.get("order", 0)
            step_id = f"step_{_slugify(tbl_name)}_{order}"
            pq_expr = step.get("native_expressions", {}).get("powerquery", "")
            nodes[step_id] = {
                "node_id":     step_id,
                "node_name":   f"Step {order}: {step.get('step_type', 'transform')}",
                "node_type":   "ingestion_step",
                "description": step.get("description", ""),
                "attributes": {
                    "table":      tbl_name,
                    "step_order": order,
                    "step_type":  step.get("step_type"),
                    "expression": pq_expr,
                },
                "prev_nodes": [],
                "next_nodes": [],
            }
            step_ids.append(step_id)

        tbl_step_ids[tbl_name] = step_ids

        # Chain step nodes sequentially
        for idx in range(1, len(step_ids)):
            _safe_add_edge(nodes, step_ids[idx - 1], step_ids[idx])

        # Wire first step ← parent_table OR ← data_source
        # (parent-table links are completed in Pass 2b once all tables exist)
        if step_ids and not parent_ref and direct_src:
            _safe_add_edge(nodes, direct_src, step_ids[0])

        # Table node: prev = last ingestion step OR direct source (fallback)
        tbl_prev: list = []
        if step_ids:
            tbl_prev = [step_ids[-1]]
        elif direct_src:
            tbl_prev = [direct_src]

        nodes[tbl_id] = {
            "node_id":     tbl_id,
            "node_name":   tbl_name,
            "node_type":   "table",
            "description": tbl.get("description", ""),
            "attributes": {
                "table_type":          tbl.get("table_type"),
                "is_materialized":     tbl.get("is_materialized"),
                "column_count":        len(tbl.get("columns", [])),
                "source_data_source_id": tbl.get("source_data_source_id"),
            },
            "prev_nodes": tbl_prev,
            "next_nodes": [],
        }

        # Wire last step → table node
        if step_ids:
            _safe_add_edge(nodes, step_ids[-1], tbl_id)

    # -----------------------------------------------------------------------
    # Pass 2b – resolve parent-table references (derived / lookup tables)
    # -----------------------------------------------------------------------
    for tbl in data.get("tables", []):
        tbl_name  = tbl.get("name", "")
        tbl_id    = tbl_name_to_id[tbl_name]
        steps     = tbl.get("ingestion", {}).get("steps", [])
        parent_ref = _find_parent_table_ref(steps)

        if not parent_ref:
            continue

        parent_id = tbl_name_to_id.get(parent_ref)
        if not parent_id:
            continue

        step_ids = tbl_step_ids.get(tbl_name, [])
        if step_ids:
            _safe_add_edge(nodes, parent_id, step_ids[0])
        else:
            _safe_add_edge(nodes, parent_id, tbl_id)

    # -----------------------------------------------------------------------
    # Pass 3 – RELATIONSHIP nodes
    # -----------------------------------------------------------------------
    def _resolve_table_node(table_ref: str) -> str | None:
        """Map a relationship table_ref (already-slugged id or name) → node_id."""
        if not table_ref:
            return None
        # Direct match on tbl_ slug
        if table_ref in nodes:
            return table_ref
        # Try matching by normalised name
        slug_ref = re.sub(r'[^a-z0-9]', '', table_ref.lower())
        for tbl_name, tid in tbl_name_to_id.items():
            slug_tbl = re.sub(r'[^a-z0-9]', '', tbl_name.lower())
            if slug_ref == slug_tbl or slug_ref in slug_tbl or slug_tbl in slug_ref:
                return tid
        return None

    for rel in data.get("relationships", []):
        rel_id   = rel.get("id", "")
        node_id  = f"rel_{_slugify(rel_id)[:64]}"

        left_col  = rel.get("left_column",  "")
        right_col = rel.get("right_column", "")
        left_tref = rel.get("left_table_id", "")
        right_tref = rel.get("right_table_id") or ""

        left_node  = _resolve_table_node(left_tref)
        right_node = _resolve_table_node(right_tref)

        prev_nodes = [n for n in [left_node, right_node] if n]

        left_label  = f"{left_tref}.{left_col}"  if left_col  else left_tref
        right_label = f"{right_tref}.{right_col}" if right_col else "(auto date table)"

        nodes[node_id] = {
            "node_id":     node_id,
            "node_name":   f"{left_label} → {right_label}",
            "node_type":   "relationship",
            "description": (
                f"{rel.get('cardinality', '')} {rel.get('relationship_type', 'join')}: "
                f"{left_label} → {right_label}"
            ),
            "attributes": {
                "left_table_id":   left_tref,
                "right_table_id":  right_tref,
                "left_column":     left_col,
                "right_column":    right_col,
                "cardinality":     rel.get("cardinality"),
                "join_type":       rel.get("join_type"),
                "filter_direction":rel.get("filter_direction"),
                "active":          rel.get("active"),
                "relationship_type": rel.get("relationship_type"),
                "note":            rel.get("note"),
            },
            "prev_nodes": prev_nodes,
            "next_nodes": [],
        }

        for pn in prev_nodes:
            _safe_add_edge(nodes, pn, node_id)

    # -----------------------------------------------------------------------
    # Pass 4 – CALCULATION nodes
    # -----------------------------------------------------------------------
    calc_name_to_id: dict = {}

    for calc in data.get("calculations", []):
        calc_name = calc.get("name", "")
        calc_id   = f"calc_{_slugify(calc_name)}"
        calc_name_to_id[calc_name] = calc_id

        # prev from depends_on_columns (format: "TableName.ColumnName")
        prev_tables: set = set()
        for dep_col in calc.get("depends_on_columns", []):
            tbl_ref = dep_col.split(".", 1)[0].strip()
            tid = tbl_name_to_id.get(tbl_ref)
            if tid:
                prev_tables.add(tid)

        nodes[calc_id] = {
            "node_id":     calc_id,
            "node_name":   calc_name,
            "node_type":   "calculation",
            "description": calc.get("description", ""),
            "attributes": {
                "semantic_type":        calc.get("semantic_type"),
                "aggregation_behavior": calc.get("aggregation_behavior"),
                "data_type":            calc.get("data_type"),
                "is_base_measure":      calc.get("is_base_measure"),
                "reusable":             calc.get("reusable"),
                "formula": (
                    calc.get("expressions", {}).get("dax")
                    or calc.get("expressions", {}).get("mdx", "")
                ),
                "depends_on_columns":   calc.get("depends_on_columns", []),
                "depends_on_measures":  [
                    (m if isinstance(m, str) else m.get("kpi_name", ""))
                    for m in calc.get("depends_on_measures", [])
                ],
                "tags": calc.get("display", {}).get("tags", []),
            },
            "prev_nodes": list(prev_tables),
            "next_nodes": [],
        }

        for pt in prev_tables:
            _safe_add_edge(nodes, pt, calc_id)

    # Pass 4b – wire calc → calc (depends_on_measures)
    for calc in data.get("calculations", []):
        calc_name = calc.get("name", "")
        calc_id   = calc_name_to_id.get(calc_name)
        if not calc_id:
            continue
        for dep in calc.get("depends_on_measures", []):
            dep_name = dep if isinstance(dep, str) else dep.get("kpi_name", "")
            dep_id   = calc_name_to_id.get(dep_name)
            if dep_id and dep_id != calc_id:
                _safe_add_edge(nodes, dep_id, calc_id)

    # -----------------------------------------------------------------------
    # Pass 5 – VISUAL nodes
    # -----------------------------------------------------------------------
    for page in data.get("visualizations", {}).get("pages", []):
        page_name = page.get("display_name", "")
        for v_idx, visual in enumerate(page.get("visuals", [])):
            v_type  = visual.get("visual_type", "visual")
            v_title = (visual.get("title") or "").strip() or f"{v_type}_{v_idx}"
            v_id    = f"vis_{_slugify(page_name)}_{v_idx}"

            fields = visual.get("fields", [])
            if not fields:
                # images, buttons, etc. — no data dependency, skip
                continue

            prev_set: set = set()
            for field in fields:
                field_tbl = (field.get("table") or "").strip()
                field_col = (field.get("column") or "").strip()

                # 1) Is the column a known calculation?
                calc_id = calc_name_to_id.get(field_col)
                if calc_id:
                    prev_set.add(calc_id)
                    continue

                # 2) Is the table a known model table?
                tid = tbl_name_to_id.get(field_tbl)
                if tid:
                    prev_set.add(tid)
                    continue

                # 3) Fuzzy calc match (e.g. "FCT Insurance_Policy_Table.Total Annual_Premium")
                for c_name, c_id in calc_name_to_id.items():
                    if c_name in field_col or field_col.endswith(c_name):
                        prev_set.add(c_id)
                        break

            field_summary = [
                {
                    "role":        f.get("role"),
                    "table":       f.get("table"),
                    "column":      f.get("column"),
                    "aggregation": f.get("aggregation"),
                }
                for f in fields
            ]

            nodes[v_id] = {
                "node_id":     v_id,
                "node_name":   f"{v_type}: {v_title} ({page_name})",
                "node_type":   "visual",
                "description": f"{v_type} visual on page '{page_name}'",
                "attributes": {
                    "page":        page_name,
                    "visual_type": v_type,
                    "title":       visual.get("title", ""),
                    "fields":      field_summary,
                },
                "prev_nodes": list(prev_set),
                "next_nodes": [],
            }

            for pn in prev_set:
                _safe_add_edge(nodes, pn, v_id)

    return list(nodes.values())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_consolidated_model(data: dict) -> dict:
    """
    Return the full `consolidated_model` dict to be appended to the Common Model.

    Keys:
        node_graph        – Alteryx-style directed node graph (main deliverable)
        column_catalog    – flat list of every column across all tables
        ingestion_steps   – flat list of every Power Query / SQL step
        visual_field_usage– flat list of every field reference used in visuals
        relationships     – flat list of model relationships
        calculations      – flat list of DAX / MDX calculations
    """
    # ---- node graph ----
    node_graph_nodes = _build_node_graph(data)

    type_counts: dict = {}
    for n in node_graph_nodes:
        t = n["node_type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    # ---- column catalog ----
    column_catalog = []
    for tbl in data.get("tables", []):
        for col in tbl.get("columns", []):
            column_catalog.append({
                "table":                 tbl.get("name"),
                "column":                col.get("name"),
                "data_type":             col.get("data_type"),
                "semantic_role":         col.get("semantic_role"),
                "nullable":              col.get("nullable"),
                "hidden":                col.get("hidden"),
                "used_in_relationships": col.get("used_in_relationships"),
                "used_in_filters":       col.get("used_in_filters"),
                "used_in_groupby":       col.get("used_in_groupby"),
                "used_in_calculations":  col.get("used_in_calculations"),
                "description":           col.get("description"),
            })

    # ---- ingestion steps ----
    ingestion_steps = []
    for tbl in data.get("tables", []):
        for step in tbl.get("ingestion", {}).get("steps", []):
            ingestion_steps.append({
                "table":       tbl.get("name"),
                "step_order":  step.get("order"),
                "step_type":   step.get("step_type"),
                "description": step.get("description"),
                "expression": (
                    step.get("native_expressions", {}).get("powerquery")
                    or step.get("native_expressions", {}).get("sql", "")
                ),
            })

    # ---- visual field usage ----
    visual_field_usage = []
    for page in data.get("visualizations", {}).get("pages", []):
        for visual in page.get("visuals", []):
            for field in visual.get("fields", []):
                visual_field_usage.append({
                    "page":        page.get("display_name"),
                    "visual_type": visual.get("visual_type"),
                    "field_role":  field.get("role"),
                    "table":       field.get("table"),
                    "column":      field.get("column"),
                    "aggregation": field.get("aggregation"),
                    "query_ref":   field.get("query_ref"),
                })

    # ---- relationships ----
    relationships = [
        {
            "id":               rel.get("id"),
            "left_table_id":    rel.get("left_table_id"),
            "left_column":      rel.get("left_column"),
            "right_table_id":   rel.get("right_table_id"),
            "right_column":     rel.get("right_column"),
            "cardinality":      rel.get("cardinality"),
            "join_type":        rel.get("join_type"),
            "filter_direction": rel.get("filter_direction"),
            "active":           rel.get("active"),
            "relationship_type":rel.get("relationship_type"),
            "note":             rel.get("note"),
        }
        for rel in data.get("relationships", [])
    ]

    # ---- calculations ----
    calculations = [
        {
            "name":                 calc.get("name"),
            "description":          calc.get("description"),
            "semantic_type":        calc.get("semantic_type"),
            "aggregation_behavior": calc.get("aggregation_behavior"),
            "data_type":            calc.get("data_type"),
            "is_base_measure":      calc.get("is_base_measure"),
            "reusable":             calc.get("reusable"),
            "formula": (
                calc.get("expressions", {}).get("dax")
                or calc.get("expressions", {}).get("mdx", "")
            ),
            "depends_on_columns":  calc.get("depends_on_columns", []),
            "depends_on_measures": [
                (m if isinstance(m, str) else m.get("kpi_name", ""))
                for m in calc.get("depends_on_measures", [])
            ],
            "tags": calc.get("display", {}).get("tags", []),
        }
        for calc in data.get("calculations", [])
    ]

    return {
        "node_graph": {
            "description": (
                "Alteryx-style directed data-flow graph. "
                "Every entity is a node; prev_nodes = upstream dependencies, "
                "next_nodes = downstream consumers."
            ),
            "node_types": [
                "data_source",
                "table",
                "ingestion_step",
                "relationship",
                "calculation",
                "visual",
            ],
            "node_count":  len(node_graph_nodes),
            "type_counts": type_counts,
            "nodes":       node_graph_nodes,
        },
        "column_catalog":     column_catalog,
        "ingestion_steps":    ingestion_steps,
        "visual_field_usage": visual_field_usage,
        "relationships":      relationships,
        "calculations":       calculations,
    }
