"""
Dedup checker for PostgreSQL.

Replaces databricks_dedup.py — same logic, uses SQLAlchemy instead of
Databricks SQL connector.

Two levels:
  Level 1 — Exact: hash-based grouping on fingerprint / column_signature
  Level 2 — Fuzzy: Jaccard similarity on column names (pairwise in Python)
"""

import re
from typing import Dict, List, Set, Any

from sqlalchemy import func, and_

from postgres_writer import get_db_session
from postgres_models import BiReport, DataSource, TableModel, ColumnMetadata


# ---------------------------------------------------------------------------
# LEVEL 1 — Exact duplicate detection (hash-based)
# ---------------------------------------------------------------------------

def _level1_data_source_duplicates() -> List[Dict]:
    """
    Groups data_sources by fingerprint.
    fingerprint = SHA256(source_type|server|database)[:16]
    Returns groups with > 1 row.
    """
    with get_db_session() as session:
        # Find fingerprints that appear more than once
        dup_fingerprints = (
            session.query(
                DataSource.fingerprint,
                func.count().label("dup_count"),
            )
            .filter(
                DataSource.fingerprint.isnot(None),
                DataSource.fingerprint != "",
            )
            .group_by(DataSource.fingerprint)
            .having(func.count() > 1)
            .order_by(func.count().desc())
            .all()
        )

        results = []
        for fp, dup_count in dup_fingerprints:
            # Fetch all sources in this group
            sources = (
                session.query(DataSource, BiReport)
                .join(BiReport, BiReport.report_id == DataSource.report_id)
                .filter(DataSource.fingerprint == fp)
                .all()
            )

            results.append({
                "fingerprint": fp,
                "dup_count": dup_count,
                "source_ids": [s.DataSource.source_id for s in sources],
                "source_names": [s.DataSource.name for s in sources],
                "report_ids": [s.DataSource.report_id for s in sources],
                "tools": [s.BiReport.tool_type for s in sources],
                "file_names": [s.BiReport.file_name for s in sources],
                "source_type": sources[0].DataSource.source_type if sources else None,
                "server": sources[0].DataSource.server if sources else None,
                "database_name": sources[0].DataSource.database_name if sources else None,
            })

        return results


def _level1_table_structure_duplicates() -> List[Dict]:
    """
    Groups tables_model by column_signature.
    column_signature = SHA256(sorted lower-cased column names)[:16]
    Returns groups with > 1 row.
    """
    with get_db_session() as session:
        dup_signatures = (
            session.query(
                TableModel.column_signature,
                func.count().label("dup_count"),
            )
            .filter(
                TableModel.column_signature.isnot(None),
                TableModel.column_signature != "",
            )
            .group_by(TableModel.column_signature)
            .having(func.count() > 1)
            .order_by(func.count().desc())
            .all()
        )

        results = []
        for sig, dup_count in dup_signatures:
            tables = (
                session.query(TableModel, BiReport)
                .join(BiReport, BiReport.report_id == TableModel.report_id)
                .filter(TableModel.column_signature == sig)
                .all()
            )

            results.append({
                "column_signature": sig,
                "dup_count": dup_count,
                "table_ids": [t.TableModel.table_id for t in tables],
                "table_names": [t.TableModel.table_name for t in tables],
                "report_ids": [t.TableModel.report_id for t in tables],
                "tools": [t.BiReport.tool_type for t in tables],
                "file_names": [t.BiReport.file_name for t in tables],
            })

        return results


# ---------------------------------------------------------------------------
# LEVEL 2 — Fuzzy duplicate detection (Jaccard similarity)
# ---------------------------------------------------------------------------

FUZZY_THRESHOLD = 0.65
COLUMN_ONLY_THRESHOLD = 0.85


def _jaccard(set_a: Set[str], set_b: Set[str]) -> float:
    """Jaccard similarity between two string sets."""
    if not set_a and not set_b:
        return 1.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union else 0.0


def _normalize_col(name: str) -> str:
    """Collapse whitespace, underscores, hyphens and lowercase."""
    return re.sub(r"[\s_\-]+", "", name.strip().lower())


def _fetch_all_tables_with_columns() -> List[Dict]:
    """Fetch every table with its column names for fuzzy comparison."""
    with get_db_session() as session:
        tables = (
            session.query(TableModel, BiReport)
            .join(BiReport, BiReport.report_id == TableModel.report_id)
            .all()
        )

        results = []
        for row in tables:
            tbl = row.TableModel
            br = row.BiReport

            # Fetch columns for this table
            columns = (
                session.query(ColumnMetadata.name)
                .filter(ColumnMetadata.table_id == tbl.table_id)
                .all()
            )
            col_names = [c.name.lower().strip() for c in columns if c.name]

            results.append({
                "table_id": tbl.table_id,
                "table_name": tbl.table_name,
                "report_id": tbl.report_id,
                "column_signature": tbl.column_signature,
                "tool_type": br.tool_type,
                "file_name": br.file_name,
                "column_names": col_names,
            })

        return results


def _get_match_reason(combined: float, col_jaccard: float):
    """Return the match reason string if thresholds are met, else None."""
    if combined >= FUZZY_THRESHOLD:
        return "name+columns"
    if col_jaccard >= COLUMN_ONLY_THRESHOLD:
        return "columns_only"
    return None


def _build_fuzzy_pair(tbl_a: Dict, tbl_b: Dict, combined: float, name_sim: float, col_jaccard: float, match_reason: str) -> Dict:
    return {
        "table_a_id": tbl_a["table_id"],
        "table_a_name": tbl_a["table_name"],
        "table_a_tool": tbl_a["tool_type"],
        "table_a_file": tbl_a["file_name"],
        "table_b_id": tbl_b["table_id"],
        "table_b_name": tbl_b["table_name"],
        "table_b_tool": tbl_b["tool_type"],
        "table_b_file": tbl_b["file_name"],
        "combined_score": round(combined, 3),
        "table_name_similarity": round(name_sim, 3),
        "column_jaccard": round(col_jaccard, 3),
        "match_reason": match_reason,
    }


def _compare_table_pair(tbl_a: Dict, cols_a: set, tbl_b: Dict, exact_signatures: Set[str]):
    """Compare one pair of tables; return a fuzzy-duplicate dict or None."""
    cols_b = {_normalize_col(c) for c in tbl_b.get("column_names", []) if c}
    if not cols_b:
        return None

    sig_a = tbl_a.get("column_signature", "")
    sig_b = tbl_b.get("column_signature", "")
    # Skip if already caught by Level 1
    if sig_a and sig_a == sig_b and sig_a in exact_signatures:
        return None

    col_jaccard = _jaccard(cols_a, cols_b)
    name_a = _normalize_col(tbl_a.get("table_name", ""))
    name_b = _normalize_col(tbl_b.get("table_name", ""))
    name_sim = 1.0 if name_a == name_b else 0.0
    combined = 0.4 * name_sim + 0.6 * col_jaccard

    match_reason = _get_match_reason(combined, col_jaccard)
    if match_reason:
        return _build_fuzzy_pair(tbl_a, tbl_b, combined, name_sim, col_jaccard, match_reason)
    return None


def _level2_fuzzy_duplicates(
    all_tables: List[Dict],
    exact_signatures: Set[str],
) -> List[Dict]:
    """O(N²) pairwise fuzzy comparison on table name + column overlap."""
    fuzzy_dups = []

    for i, tbl_a in enumerate(all_tables):
        cols_a = {_normalize_col(c) for c in tbl_a.get("column_names", []) if c}
        if not cols_a:
            continue
        for tbl_b in all_tables[i + 1:]:
            result = _compare_table_pair(tbl_a, cols_a, tbl_b, exact_signatures)
            if result:
                fuzzy_dups.append(result)

    return fuzzy_dups


# ---------------------------------------------------------------------------
# MAIN ENTRY POINT
# ---------------------------------------------------------------------------

def run_dedup_check() -> Dict[str, Any]:
    """
    Execute both dedup levels against PostgreSQL.
    Drop-in replacement for databricks_dedup.run_dedup_check().

    Returns:
        {
            "level1": {
                "data_source_duplicates": [...],
                "table_structure_duplicates": [...],
            },
            "level2": {
                "fuzzy_table_duplicates": [...],
            },
            "summary": {
                "exact_duplicate_source_groups": N,
                "exact_duplicate_table_groups": N,
                "fuzzy_duplicate_pairs": N,
            }
        }
    """
    try:
        # Level 1 — exact
        print("\n[Dedup] Level 1 — hash-based exact detection...")
        source_dups = _level1_data_source_duplicates()
        table_dups = _level1_table_structure_duplicates()

        print(f"  DATA SOURCE duplicates: {len(source_dups)} group(s)")
        for gi, grp in enumerate(source_dups, 1):
            print(f"  [src-dup #{gi}]  {grp.get('source_type','?')} | "
                  f"server={grp.get('server','?')} | db={grp.get('database_name','?')}  "
                  f"({grp.get('dup_count','?')} copies)")

        print(f"  TABLE STRUCTURE duplicates: {len(table_dups)} group(s)")
        for gi, grp in enumerate(table_dups, 1):
            print(f"  [tbl-dup #{gi}]  sig={grp.get('column_signature','?')}  "
                  f"({grp.get('dup_count','?')} copies)")

        exact_signatures = {
            row["column_signature"] for row in table_dups if row.get("column_signature")
        }

        # Level 2 — fuzzy
        print("\n[Dedup] Level 2 — fuzzy pairwise detection...")
        all_tables = _fetch_all_tables_with_columns()
        fuzzy_dups = _level2_fuzzy_duplicates(all_tables, exact_signatures)
        print(f"  FUZZY duplicates: {len(fuzzy_dups)} pair(s)")

        return {
            "level1": {
                "data_source_duplicates": source_dups,
                "table_structure_duplicates": table_dups,
            },
            "level2": {
                "fuzzy_table_duplicates": fuzzy_dups,
            },
            "summary": {
                "exact_duplicate_source_groups": len(source_dups),
                "exact_duplicate_table_groups": len(table_dups),
                "fuzzy_duplicate_pairs": len(fuzzy_dups),
            },
        }

    except Exception as e:
        print(f"[Dedup] Error: {e}")
        return {
            "level1": {"data_source_duplicates": [], "table_structure_duplicates": []},
            "level2": {"fuzzy_table_duplicates": []},
            "summary": {"error": str(e)},
        }
