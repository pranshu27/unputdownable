"""
pipeline.py — Core pipeline logic as callable functions (used by api.py).

FileData = list of (filename, parsed_json_dict) tuples.
"""

import os
import re
import json
import time
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
load_dotenv()

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from openai import AzureOpenAI

# Type alias
FileData = list[dict]


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — KPI Lineage
# ─────────────────────────────────────────────────────────────────────────────
def extract_kpi(file_data: FileData) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Extract KPI lineage from parsed JSON files.

    Returns: (df_summary, df_col_deps, df_meas_deps)
    """
    summary_rows  = []
    col_dep_rows  = []
    meas_dep_rows = []

    for data in file_data:
        report_name = data.get("name", "")
        kpi_lineage = data.get("kpi_lineage", [])

        for kpi in kpi_lineage:
            display = kpi.get("display", {}) or {}
            tags    = display.get("tags", [])
            summary_rows.append({
                "KPI Asset ID":         (kpi.get("kpi_id") or "") + "$" + (kpi.get("kpi_name") or ""),
                "KPI Name":             kpi.get("kpi_name"),
                "Description":          kpi.get("description"),
                "Semantic Type":        kpi.get("semantic_type"),
                "Aggregation Behavior": kpi.get("aggregation_behavior"),
                "Data Type":            kpi.get("data_type"),
                "Format String":        kpi.get("format_string"),
                "Is Base Measure":      kpi.get("is_base_measure"),
                "Reusable":             kpi.get("reusable"),
                "Display Folder":       display.get("folder"),
                "Hidden":               display.get("hidden"),
                "Tags":                 ", ".join(tags) if tags else "",
                "Formula":              kpi.get("formula"),
                "Depends on Column":   ", ".join([col.get("table_name") + "." + col.get("column_name") for col in kpi.get("depends_on_columns") or []]),
                "Data Source":          kpi.get("depends_on_columns", [])[0].get("data_source", {}).get("name")
                                        if kpi.get("depends_on_columns") else None,
                "Source Tool":          kpi.get("depends_on_columns", [])[0].get("report", {}).get("tool")
                                        if kpi.get("depends_on_columns") else None,
                "Report Name":          report_name,
            })

        for kpi in kpi_lineage:
            for col in kpi.get("depends_on_columns", []) or []:
                ds     = col.get("data_source", {}) or {}
                report = col.get("report", {}) or {}
                col_dep_rows.append({
                    "KPI Asset ID":    (kpi.get("kpi_id") or "") + "$" + (kpi.get("kpi_name") or ""),
                    "KPI Name":        kpi.get("kpi_name"),
                    "Column Asset ID": (col.get("table_id") or "") + "$" + (col.get("column_name") or ""),
                    "Column Name":     col.get("column_name"),
                    "Table Name":      col.get("table_name"),
                    "Table Type":      col.get("table_type"),
                    "Source File":     ds.get("name"),
                    "Source Type":     ds.get("source_type"),
                    "Connection Mode": ds.get("connection_mode"),
                    "Source Path":     ds.get("path"),
                    "Report Tool":     report.get("tool"),
                    "Report Name":     report.get("report_name"),
                })

        for kpi in kpi_lineage:
            deps = kpi.get("depends_on_measures", []) or []
            if isinstance(deps, dict):
                deps = [deps]
            for meas in deps:
                meas_dep_rows.append({
                    "KPI Name":             kpi.get("kpi_name"),
                    "KPI Asset ID":         (kpi.get("kpi_id") or "") + "$" + (kpi.get("kpi_name") or ""),
                    "Depends On Measure":   meas.get("kpi_name"),
                    "Found":                meas.get("found"),
                    "Semantic Type":        meas.get("semantic_type"),
                    "Aggregation Behavior": meas.get("aggregation_behavior"),
                    "Data Type":            meas.get("data_type"),
                })

    return (
        pd.DataFrame(summary_rows),
        pd.DataFrame(col_dep_rows),
        pd.DataFrame(meas_dep_rows),
    )


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Attribute Lineage
# ─────────────────────────────────────────────────────────────────────────────
def extract_attributes(file_data: FileData) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Extract attribute lineage from parsed JSON files.

    Returns: (df_ds, df_tables, df_attrs, df_rels)
    """
    def _ds_name_from_table_id(table_id: str):
        m = re.search(r'\$([^$]+)\(datasource\)', table_id or "")
        return m.group(1) if m else None

    def _find_datasource(ds_by_name: dict, ds_segment):
        if not ds_segment:
            return {}
        if ds_segment in ds_by_name:
            return ds_by_name[ds_segment]
        seg_base = os.path.splitext(ds_segment)[0].lower()
        for key, val in ds_by_name.items():
            if os.path.splitext(key)[0].lower() == seg_base:
                return val
        return {}

    ds_rows    = []
    table_rows = []
    attr_rows  = []
    rel_rows   = []

    for data in file_data:
        report_name = data.get("name", "")

        source_tool = None
        for ds in (data.get("data_sources") or []) + (data.get("calculations") or []):
            ds_id = ds.get("id", "")
            if ds_id.startswith("powerbi"):
                source_tool = "Power BI"
                break
            elif ds_id.startswith("tableau"):
                source_tool = "Tableau"
                break

        ds_by_name: dict = {}
        for ds in (data.get("data_sources") or []):
            ds_by_name[ds.get("name", "")] = ds
            ds_rows.append({
                "Report Name":           report_name,
                "Source Tool":           source_tool,
                "DataSource Name":       ds.get("name"),
                "Data Source Asset ID":  (ds.get("id") or "") + "$" + (ds.get("name") or ""),
                "Source Type":           ds.get("source_type"),
                "Connection Mode":       ds.get("connection_mode"),
                "Server":                ds.get("server"),
                "Database":              ds.get("database"),
                "Schema":                ds.get("schema"),
                "Path":                  ds.get("path"),
                "Authentication Method": ds.get("authentication_method"),
                "Refresh Frequency":     ds.get("refresh_frequency"),
            })

        for table in (data.get("tables") or []):
            tbl_name = table.get("name", "")
            tbl_id   = table.get("id", "")
            tbl_type = table.get("table_type", "")
            tbl_desc = table.get("description", "")
            if tbl_type == "calculated":
                continue

            ds_segment = _ds_name_from_table_id(tbl_id)
            ds_record  = _find_datasource(ds_by_name, ds_segment)
            ds_name    = ds_record.get("name", ds_segment)
            ds_path    = ds_record.get("path")

            ingestion_steps = (table.get("ingestion") or {}).get("steps") or []
            if not ds_path:
                for step in ingestion_steps:
                    if step.get("step_type", "").startswith("read"):
                        native  = step.get("native_expressions") or {}
                        ds_path = next(iter(native.values()), None)
                        break

            transform_summary = "\n".join(
                f"[{s.get('step_type','').upper()}] {s.get('description','')}"
                for s in ingestion_steps
            )

            table_rows.append({
                "Report Name":          report_name,
                "Source Tool":          source_tool,
                "Table Name":           tbl_name,
                "Table Type":           tbl_type,
                "Description":          tbl_desc,
                "Is Materialized":      table.get("is_materialized"),
                "DataSource Name":      ds_name,
                "Source Path":          ds_path,
                "Transformation Steps": transform_summary,
            })

            for col in (table.get("columns") or []):
                col_name = col.get("name", "")
                col_id   = col.get("id", "")

                is_derived   = "No"
                derive_logic = []
                for step in ingestion_steps:
                    st          = step.get("step_type", "")
                    native      = step.get("native_expressions") or {}
                    native_expr = " | ".join(str(v) for v in native.values())
                    if col_name in native_expr and st in ("derive", "rename", "change_type", "custom"):
                        is_derived = "Yes"
                        derive_logic.append(f"[{st}] {native_expr}")

                attr_rows.append({
                    "Report Name":           report_name,
                    "Source Tool":           source_tool,
                    "Table Name":            tbl_name,
                    "Table Type":            tbl_type,
                    "DataSource Name":       ds_name,
                    "Source Path":           ds_path,
                    "Column Asset ID":       (col_id or "") + "$" + col_name,
                    "Column Name":           col_name,
                    "Data Type":             col.get("data_type"),
                    "Nullable":              col.get("nullable"),
                    "Hidden":                col.get("hidden"),
                    "Semantic Role":         col.get("semantic_role"),
                    "Description":           col.get("description"),
                    "Used in Relationships": col.get("used_in_relationships"),
                    "Used in Filters":       col.get("used_in_filters"),
                    "Used in Group By":      col.get("used_in_groupby"),
                    "Used in Calculations":  col.get("used_in_calculations"),
                    "Is Derived":            is_derived,
                    "Derivation Logic":      "\n".join(derive_logic),
                })

        for rel in (data.get("relationships") or []):
            rel_rows.append({
                "Report Name":       report_name,
                "Source Tool":       source_tool,
                "Left Table":        rel.get("left_table_id"),
                "Left Column":       rel.get("left_column"),
                "Right Table":       rel.get("right_table_id"),
                "Right Column":      rel.get("right_column"),
                "Join Type":         rel.get("join_type"),
                "Cardinality":       rel.get("cardinality"),
                "Active":            rel.get("active"),
                "Filter Direction":  rel.get("filter_direction"),
                "Relationship Type": rel.get("relationship_type"),
            })

    return (
        pd.DataFrame(ds_rows),
        pd.DataFrame(table_rows),
        pd.DataFrame(attr_rows),
        pd.DataFrame(rel_rows),
    )


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Rationalization + GPT Refinement
# ─────────────────────────────────────────────────────────────────────────────

def _llm_normalize_formula(
    kpi_name: str,
    source_tool: str,
    description: str,
    formula: str,
    az_client,
    deployment: str,
    retries: int = 2,
) -> str:
    """
    Ask the LLM to produce a tool-agnostic normalized formula from a raw
    DAX (Power BI) or Tableau calculation expression, so that semantically
    equivalent KPIs across different tools produce similar embedding vectors.

    Falls back to the raw formula string on any error.
    """
    if not formula or not str(formula).strip():
        return ""

    system = (
        "You are a data governance expert specialising in BI semantic normalisation.\n"
        "Given a KPI's name, source tool, description, and raw formula, produce a "
        "clean tool-agnostic normalized formula that can be used to compare "
        "semantically equivalent KPIs across Power BI (DAX) and Tableau.\n\n"
        "Rules:\n"
        "- Remove DAX context modifiers (CALCULATE, FILTER, ALL, ALLSELECTED, "
        "ALLEXCEPT, USERELATIONSHIP, etc.) but preserve the core aggregation logic.\n"
        "- Remove Tableau LOD wrappers ({ FIXED ... : }, { INCLUDE ... : }, "
        "{ EXCLUDE ... : }) but preserve the inner expression.\n"
        "- Replace table-qualified field references (e.g. Sales[Amount], "
        "'Sales'[Amount]) with just the field name.\n"
        "- Standardise aggregation names to uppercase: SUM, AVG, COUNT, COUNTD, "
        "MIN, MAX, DISTINCTCOUNT.\n"
        "- Preserve arithmetic operators and logical structure.\n"
        "- Return ONLY the normalized formula — no explanation, no markdown, no quotes."
    )

    user = (
        f"KPI Name   : {kpi_name or 'N/A'}\n"
        f"Source Tool: {source_tool or 'Unknown'}\n"
        f"Description: {description or 'N/A'}\n"
        f"Formula    : {formula}"
    )

    for attempt in range(retries):
        try:
            resp = az_client.chat.completions.create(
                model=deployment,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                max_completion_tokens=3000,
                temperature=0,
            )
            result = resp.choices[0].message.content.strip()
            return result if result else str(formula)
        except Exception:
            time.sleep(2 ** attempt)

    return str(formula)  # final fallback


def rationalize(
    df_summary: pd.DataFrame = None,
    df_attrs: pd.DataFrame = None,
    df_rels: pd.DataFrame = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run semantic rationalization and GPT refinement.

    Returns: (df_rationalized, overlap_df, verdict_summary)
    """
    # Normalise optional params to empty DataFrames
    if df_summary is None:
        df_summary = pd.DataFrame()
    if df_attrs is None:
        df_attrs = pd.DataFrame()
    if df_rels is None:
        df_rels = pd.DataFrame()

    # ── Build PK/FK lookup from relationship data ─────────────────────────────
    # Any column that appears as a join key in a relationship is structural
    # (primary or foreign key) and must not be carelessly retired or merged.
    _rel_col_pairs: set = set()
    if not df_rels.empty:
        for _, _rel in df_rels.iterrows():
            _lt = str(_rel.get("Left Table")  or "").lower().strip()
            _lc = str(_rel.get("Left Column") or "").lower().strip()
            _rt = str(_rel.get("Right Table")  or "").lower().strip()
            _rc = str(_rel.get("Right Column") or "").lower().strip()
            if _lt and _lc:
                _rel_col_pairs.add((_lt, _lc))
            if _rt and _rc:
                _rel_col_pairs.add((_rt, _rc))
    # ─────────────────────────────────────────────────────────────────────────
    RETIRE_SIM      = 0.93
    MERGE_SIM       = 0.85
    STANDARDIZE_SIM = 0.72

    AZURE_ENDPOINT   = os.environ.get("AZURE_OPENAI_API_BASE")
    AZURE_API_KEY    = os.environ.get("AZURE_OPENAI_API_KEY")
    AZURE_API_VER    = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
    AZURE_DEPLOYMENT = os.environ.get("AZURE_DEPLOYMENT", "gpt-5-mini")

    EMBEDDING_ENDPOINT   = os.environ.get("AZURE_EMBEDDING_API_BASE")
    EMBEDDING_API_KEY    = os.environ.get("AZURE_EMBEDDING_API_KEY")
    EMBEDDING_API_VER    = os.environ.get("AZURE_EMBEDDING_API_VERSION", "2023-05-15")
    EMBEDDING_DEPLOYMENT = os.environ.get("AZURE_EMBEDDING_DEPLOYMENT", "ada-002")
    # ── Azure chat client (shared by formula normalisation AND GPT refinement) ──
    az_client = AzureOpenAI(
        azure_endpoint=AZURE_ENDPOINT,
        api_key=AZURE_API_KEY,
        api_version=AZURE_API_VER,
    )

    # ── Pre-compute LLM-normalised formulas for all KPI rows in parallel ─────
    _kpi_rows = list(df_summary.iterrows()) if not df_summary.empty else []

    def _norm_task(args):
        _idx, _r = args
        return _idx, _llm_normalize_formula(
            kpi_name    = _r.get("KPI Name"),
            source_tool = _r.get("Source Tool"),
            description = _r.get("Description"),
            formula     = _r.get("Formula"),
            az_client   = az_client,
            deployment  = AZURE_DEPLOYMENT,
        )

    _normalized_formulas: dict = {}
    if _kpi_rows:
        print(f"[normalize] Normalising {len(_kpi_rows)} KPI formula(s) via LLM...")
        with ThreadPoolExecutor(max_workers=20) as _ex:
            _futures = {_ex.submit(_norm_task, item): item[0] for item in _kpi_rows}
            for _f in as_completed(_futures):
                _idx, _norm = _f.result()
                _normalized_formulas[_idx] = _norm
        print("[normalize] Formula normalisation complete.")
    # ── Build catalog ─────────────────────────────────────────────────────────
    def _txt(*vals):
        return " | ".join(str(v) for v in vals if v and str(v).strip())

    catalog = []

    #KPIs (df_summary)
    for idx, r in df_summary.iterrows():
        normalized_formula = _normalized_formulas.get(idx, str(r.get("Formula") or ""))
        catalog.append({
            "item_id":            f"kpi|{r.get('Source Tool') or '?'}|{r.get('KPI Name', '')}",
            "Asset ID":           r.get("KPI Asset ID"),
            "Item Type":          "KPI",
            "Name":               r.get("KPI Name"),
            "Description":        r.get("Description"),
            "Formula":            r.get("Formula"),
            "Normalized Formula": normalized_formula,
            "Semantic Type":      r.get("Semantic Type"),
            "Data Type":          r.get("Data Type"),
            "Source Tool":        r.get("Source Tool"),
            "Report Name":        r.get("Report Name"),
            "Table":              r.get("Depends on Column"),
            "DataSource":         r.get("Data Source"),
            "Is Key Column":      False,  # KPIs are computed measures, never structural keys
            "embed_text":         _txt(r.get("KPI Name"), r.get("Description"),
                                       normalized_formula, r.get("Aggregation Behavior")),
        })

    # Attributes / Columns (df_attrs)
    print(len(df_attrs), "attributes loaded from extract_attributes")
    for _, r in df_attrs.iterrows():
        # Determine whether this column is a structural key (PK/FK)
        _sem_role   = str(r.get("Semantic Role") or "").lower()
        _used_in_rel = r.get("Used in Relationships")
        _tbl_key    = str(r.get("Table Name")  or "").lower().strip()
        _col_key    = str(r.get("Column Name") or "").lower().strip()
        _is_key = bool(
            any(k in _sem_role for k in ("key", "pk", "fk", "primary", "foreign", "id"))
            or (str(_used_in_rel).strip().lower() not in ("", "none", "false", "0", "nan"))
            or (_tbl_key, _col_key) in _rel_col_pairs
        )
        catalog.append({
            "item_id":       f"attr|{r.get('Source Tool') or '?'}|{r.get('Report Name', '')}|{r.get('Table Name', '')}|{r.get('Column Name', '')}",
            "Asset ID":      r.get("Column Asset ID"),
            "Item Type":     "Attribute",
            "Name":          r.get("Column Name"),
            "Description":   r.get("Description"),
            "Formula":       None,
            "Semantic Type": r.get("Semantic Role"),
            "Data Type":     r.get("Data Type"),
            "Source Tool":   r.get("Source Tool"),
            "Report Name":   r.get("Report Name"),
            "Table":         r.get("Table Name"),
            "DataSource":    r.get("DataSource Name"),
            "Is Key Column": _is_key,
            "embed_text":    _txt(r.get("Column Name"), r.get("Description"), r.get("Semantic Role"),
                                  r.get("Table Name"),
                                  r.get("Data Type")),
        })


    df_cat = (pd.DataFrame(catalog)
              .drop_duplicates(subset=["item_id"])
              .reset_index(drop=True))
    n = len(df_cat)

    # Nothing to rationalize — return properly-shaped empty DataFrames
    if n == 0:
        empty_cat = pd.DataFrame(columns=[
            "Asset ID", "Item Type", "Name", "Source Tool", "Report Name",
            "Table / Folder", "DataSource", "Data Type", "Semantic Type",
            "Description", "Formula", "Normalized Formula",
            "AI Verdict", "Similarity Score", "Top Match", "Rationale",
            "Top 3 Matches", "Overlap Group ID", "AI Verdict Refined", "Rationale Refined",
        ])
        empty_sum = pd.DataFrame(columns=["Item Type", "AI Verdict", "Count"])
        return empty_cat, empty_cat.copy(), empty_sum

    # ── Embeddings ────────────────────────────────────────────────────────────
    embedding_client = AzureOpenAI(
        azure_endpoint=EMBEDDING_ENDPOINT,
        api_key=EMBEDDING_API_KEY,
        api_version=EMBEDDING_API_VER,
    )

    def _embed_batch(texts: list[str]) -> list[list[float]]:
        response = embedding_client.embeddings.create(model=EMBEDDING_DEPLOYMENT, input=texts)
        vecs = [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
        arr  = np.array(vecs, dtype=np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        return (arr / norms).tolist()

    texts_to_embed = df_cat["embed_text"].fillna("").tolist()
    BATCH_SIZE     = 256  # API supports up to 256 texts per request
    all_emb_lists  = [None] * len(texts_to_embed)
    batches        = [(i, texts_to_embed[i:i + BATCH_SIZE]) for i in range(0, len(texts_to_embed), BATCH_SIZE)]

    def _embed_batch_indexed(args):
        start_idx, batch_texts = args
        return start_idx, _embed_batch(batch_texts)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(_embed_batch_indexed, b): b[0] for b in batches}
        for future in as_completed(futures):
            start_idx, vecs = future.result()
            for offset, vec in enumerate(vecs):
                all_emb_lists[start_idx + offset] = vec

    embs = np.array(all_emb_lists, dtype=np.float32)

    # ── pgvector (PostgreSQL) ────────────────────────────────────────────────
    POSTGRES_URL = os.environ.get("POSTGRES_URL")
    META_COLS = ["Item Type", "Name", "Source Tool", "Report Name", "Table", "DataSource"]

    def _to_pgvector(vec: list[float] | np.ndarray) -> str:
        return "[" + ",".join(f"{float(v):.8f}" for v in vec) + "]"

    def _batch_query_in_memory() -> dict:
        # Fallback path if pgvector is unavailable; keeps verdict behavior intact.
        _k = min(6, n)
        _sims = np.clip(embs @ embs.T, -1.0, 1.0)
        _res = {
            "ids": [[] for _ in range(n)],
            "distances": [[] for _ in range(n)],
            "metadatas": [[] for _ in range(n)],
        }
        for _i in range(n):
            _order = np.argsort(-_sims[_i])[:_k]
            for _j in _order:
                _res["ids"][_i].append(df_cat.iloc[_j]["item_id"])
                _res["distances"][_i].append(round(float(1.0 - _sims[_i][_j]), 8))
                _res["metadatas"][_i].append(
                    df_cat.iloc[_j][META_COLS].fillna("").to_dict()
                )
        return _res

    _batch_results = {
        "ids": [[] for _ in range(n)],
        "distances": [[] for _ in range(n)],
        "metadatas": [[] for _ in range(n)],
    }

    if POSTGRES_URL:
        try:
            with psycopg2.connect(POSTGRES_URL) as conn:
                with conn.cursor() as cur:
                    dim = int(embs.shape[1])
                    # cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                    cur.execute(f"""
                        CREATE TEMP TABLE tmp_rationalization_vectors (
                            item_id TEXT PRIMARY KEY,
                            embedding vector({dim}) NOT NULL,
                            metadata JSONB,
                            document TEXT
                        ) ON COMMIT DROP
                    """)
                    cur.execute(f"""
                        CREATE TEMP TABLE tmp_rationalization_queries (
                            idx INTEGER NOT NULL,
                            embedding vector({dim}) NOT NULL
                        ) ON COMMIT DROP
                    """)

                    _insert_rows = []
                    for _i in range(n):
                        _insert_rows.append((
                            df_cat.iloc[_i]["item_id"],
                            _to_pgvector(embs[_i]),
                            json.dumps(df_cat.iloc[_i][META_COLS].fillna("").to_dict()),
                            df_cat.iloc[_i]["embed_text"],
                        ))
                    execute_values(
                        cur,
                        """
                        INSERT INTO tmp_rationalization_vectors (item_id, embedding, metadata, document)
                        VALUES %s
                        """,
                        _insert_rows,
                        template="(%s, %s::vector, %s::jsonb, %s)",
                        page_size=500,
                    )

                    _query_rows = [(_i, _to_pgvector(embs[_i])) for _i in range(n)]
                    execute_values(
                        cur,
                        """
                        INSERT INTO tmp_rationalization_queries (idx, embedding)
                        VALUES %s
                        """,
                        _query_rows,
                        template="(%s, %s::vector)",
                        page_size=500,
                    )

                    cur.execute(
                        """
                        SELECT q.idx, r.item_id, (r.embedding <=> q.embedding) AS distance, r.metadata
                        FROM tmp_rationalization_queries q
                        CROSS JOIN LATERAL (
                            SELECT item_id, embedding, metadata
                            FROM tmp_rationalization_vectors
                            ORDER BY embedding <=> q.embedding
                            LIMIT %s
                        ) r
                        ORDER BY q.idx
                        """,
                        (min(6, n),),
                    )
                    for _idx, _item_id, _dist, _meta in cur.fetchall():
                        if isinstance(_meta, str):
                            _meta = json.loads(_meta)
                        _batch_results["ids"][_idx].append(_item_id)
                        _batch_results["distances"][_idx].append(float(_dist))
                        _batch_results["metadatas"][_idx].append(_meta or {})
        except Exception as exc:
            print(f"[rationalize] pgvector unavailable, falling back to in-memory similarity: {exc}")
            _batch_results = _batch_query_in_memory()
    else:
        _batch_results = _batch_query_in_memory()

    # ── Union-Find ────────────────────────────────────────────────────────────
    parent    = list(range(n))
    id_to_idx = {row["item_id"]: i for i, row in df_cat.iterrows()}

    def _find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def _union(a, b):
        ra, rb = _find(a), _find(b)
        if ra != rb:
            parent[rb] = ra

    # ── Verdict loop ──────────────────────────────────────────────────────────
    # Query top neighbors in batch once for all items (pgvector backed).

    verdict_rows = []
    for idx, row in df_cat.iterrows():
        top_sim, top_name, top_tool, top_idx = 0.0, "", "", None
        matches = []

        for r_id, dist, meta in zip(_batch_results["ids"][idx], _batch_results["distances"][idx], _batch_results["metadatas"][idx]):
            if r_id == row["item_id"]:
                continue
            sim  = round(1 - dist, 4)
            name = meta.get("Name", "")
            tool = meta.get("Source Tool", "")
            matches.append(f"{name} [{tool}] ({sim:.2f})")
            if sim > top_sim:
                top_sim, top_name, top_tool = sim, name, tool
                top_idx = id_to_idx.get(r_id)

        same_tool = (top_tool == (row["Source Tool"] or ""))

        if top_sim >= RETIRE_SIM and same_tool:
            verdict   = "Retire"
            rationale = (f"Near-duplicate of '{top_name}' within {row['Source Tool']} "
                         f"(sim={top_sim:.2f}). Retire and consolidate into one definition.")
        elif top_sim >= MERGE_SIM:
            verdict   = "Merge"
            rationale = (f"Semantically equivalent to '{top_name}' [{top_tool}] "
                         f"(sim={top_sim:.2f}). Merge across tools into a single canonical definition.")
        elif top_sim >= STANDARDIZE_SIM:
            verdict   = "Standardize"
            rationale = (f"Overlaps with '{top_name}' [{top_tool}] (sim={top_sim:.2f}). "
                         f"Align naming convention, description, and data type.")
        elif top_sim >= 0.50:
            verdict   = "Keep"
            rationale = (f"Loosely related to '{top_name}' (sim={top_sim:.2f}). "
                         f"Keep — review description for additional clarity.")
        else:
            verdict   = "Keep"
            rationale = "Unique — no significant semantic overlap found."

        if top_sim >= STANDARDIZE_SIM and top_idx is not None:
            _union(idx, top_idx)

        verdict_rows.append({
            "Asset ID":           row["Asset ID"],
            "Item Type":          row["Item Type"],
            "Name":               row["Name"],
            "Source Tool":        row["Source Tool"],
            "Report Name":        row["Report Name"],
            "Table / Folder":     row["Table"],
            "DataSource":         row["DataSource"],
            "Data Type":          row["Data Type"],
            "Semantic Type":      row["Semantic Type"],
            "Description":        row["Description"],
            "Formula":            row["Formula"],
            "Normalized Formula": row.get("Normalized Formula", ""),
            "Is Key Column":      row.get("Is Key Column", False),
            "AI Verdict":         verdict,
            "Similarity Score":   top_sim,
            "Top Match":          f"{top_name} [{top_tool}]" if top_name else "",
            "Rationale":          rationale,
            "Top 3 Matches":      " | ".join(matches[:3]),
        })

    df_rationalized = pd.DataFrame(verdict_rows)

    # ── Overlap group IDs ─────────────────────────────────────────────────────
    roots       = [_find(i) for i in range(n)]
    root_to_gid = {}
    gid_ctr     = 1
    for r in roots:
        if r not in root_to_gid:
            root_to_gid[r] = gid_ctr
            gid_ctr += 1
    df_rationalized["Overlap Group ID"] = [root_to_gid[r] for r in roots]

    group_sizes  = df_rationalized.groupby("Overlap Group ID")["Name"].count()
    multi_groups = group_sizes[group_sizes > 1].index

    # ── GPT Refinement ────────────────────────────────────────────────────────
    SYSTEM_PROMPT = """\
You are a senior data governance analyst. Review the following KPI or attribute by carefully considering its name, description, formula (if KPI), source tool, and the AI's initial verdict based on semantic similarity to other items. Use this information to determine if you agree with the AI's verdict or if it should be refined. Consider nuances such as whether two items are near-duplicates that should be retired, semantically equivalent but from different tools that should be merged, or if they simply overlap and could benefit from standardization. If the item is unique and the rationale supports it, then keeping it may be appropriate. Your goal is to provide a more informed verdict and rationale based on a holistic understanding of the item in question and its relationship to similar items. Also carefully understand the meanings of each name before asking them to merge — they could have different meanings.

CRITICAL — Primary Key / Foreign Key rule:
The "Is Key Column" field indicates whether this item is a structural join key (primary key, foreign key, or a column actively used in table relationships). If "Is Key Column" is True:
  - Do NOT assign Retire or Merge unless you have absolute certainty that the duplicate is structurally identical AND retiring it will not break any join or relationship.
  - Prefer Standardize (align naming/description) or Keep over Retire/Merge for key columns.
  - Always explicitly mention the key-column status in your rationale so stakeholders are aware of the data-integrity risk.

Return a JSON object with exactly two keys:
  - "verdict"   : one of Keep | Merge | Retire | Standardize
  - "rationale" : 1-3 sentences explaining your refined reasoning.

Return ONLY the JSON object — no markdown, no extra text.
"""

    # Batch multiple items per GPT call to reduce total API round-trips ~10×.
    REFINE_BATCH = 10

    BATCH_SYSTEM_PROMPT = SYSTEM_PROMPT + (
        "\n\nYou will receive multiple items. Return a JSON object with a single key "
        '"results" containing an array. Each element must have: '
        '"row_index" (0-based integer matching the [Item N] label), '
        '"verdict" (Keep|Merge|Retire|Standardize), '
        '"rationale" (1-3 sentences). Return results for ALL items provided.'
    )

    def _gpt_refine_batch(batch: list, retries: int = 3) -> list:
        """Refine a batch of (orig_idx, row_dict) items in one GPT call."""
        items_text = ""
        for local_i, (_, row) in enumerate(batch):
            items_text += (
                f"\n[Item {local_i}]\n"
                f"Item Type     : {row.get('Item Type', '')}\n"
                f"Name          : {row.get('Name', '')}\n"
                f"Description   : {row.get('Description', '')}\n"
                f"Table / Folder : {row.get('Table', '')}\n"
                f"Report Name   : {row.get('Report Name', '')}\n"
                f"Formula       : {row.get('Formula', '')}\n"
                f"Source Tool   : {row.get('Source Tool', '')}\n"
                f"Is Key Column : {row.get('Is Key Column', False)}\n"
                f"AI Verdict    : {row.get('AI Verdict', '')}\n"
                f"Top Match     : {row.get('Top Match', '')}\n"
                f"Rationale     : {row.get('Rationale', '')}\n"
                f"Top 3         : {row.get('Top 3 Matches', '')}\n"
            )
        for attempt in range(retries):
            try:
                resp = az_client.chat.completions.create(
                    model=AZURE_DEPLOYMENT,
                    messages=[
                        {"role": "system", "content": BATCH_SYSTEM_PROMPT},
                        {"role": "user",   "content": f"Refine the following {len(batch)} items:\n{items_text}"},
                    ],
                    max_completion_tokens=400 * len(batch),
                    response_format={"type": "json_object"},
                )
                parsed = json.loads(resp.choices[0].message.content)
                result_map = {
                    item["row_index"]: item
                    for item in parsed.get("results", [])
                    if isinstance(item, dict) and "row_index" in item
                }
                output = []
                for local_i, (orig_idx, row) in enumerate(batch):
                    item = result_map.get(local_i, {})
                    v = item.get("verdict", row["AI Verdict"]).strip()
                    r = item.get("rationale", row["Rationale"]).strip()
                    if v not in {"Keep", "Merge", "Retire", "Standardize"}:
                        v = row["AI Verdict"]
                    output.append((orig_idx, v, r))
                return output
            except Exception:
                time.sleep(2 ** attempt)
        # Final fallback: return original AI verdicts unchanged
        return [(orig_idx, row["AI Verdict"], row["Rationale"]) for orig_idx, row in batch]

    _all_rows = [(i, row.to_dict()) for i, (_, row) in enumerate(df_rationalized.iterrows())]
    _refine_batches = [_all_rows[i : i + REFINE_BATCH] for i in range(0, len(_all_rows), REFINE_BATCH)]
    results: dict = {}

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(_gpt_refine_batch, b) for b in _refine_batches]
        for future in as_completed(futures):
            for orig_idx, v, r in future.result():
                results[orig_idx] = (v, r)

    df_rationalized["AI Verdict Refined"] = [results[i][0] for i in range(len(df_rationalized))]
    df_rationalized["Rationale Refined"]  = [results[i][1] for i in range(len(df_rationalized))]

    verdict_summary = (
        df_rationalized
        .groupby(["Item Type", "AI Verdict Refined"])
        .size()
        .reset_index(name="Count")
        .rename(columns={"AI Verdict Refined": "AI Verdict"})
        .sort_values(["Item Type", "Count"], ascending=[True, False])
    )

    overlap_df = (
        df_rationalized[df_rationalized["Overlap Group ID"].isin(multi_groups)]
        .sort_values(["Overlap Group ID", "AI Verdict Refined", "Item Type"])
    )

    return (
        df_rationalized.drop(columns=["Is Key Column"], errors="ignore").sort_values(["AI Verdict Refined", "Item Type"]),
        overlap_df.drop(columns=["Is Key Column"], errors="ignore"),
        verdict_summary,
    )
