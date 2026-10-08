from __future__ import annotations

from typing import Dict, List


def build_parity_checks(target_table: str, baseline_table: str, key_columns: List[str]) -> Dict[str, str]:
    key_join = " AND ".join([f"t.{c} = b.{c}" for c in key_columns])
    return {
        "row_count": f"SELECT COUNT(*) AS cnt FROM {target_table}",
        "baseline_row_count": f"SELECT COUNT(*) AS cnt FROM {baseline_table}",
        "null_profile": (
            "SELECT * FROM ("
            f"SELECT {', '.join([f'SUM(CASE WHEN {c} IS NULL THEN 1 ELSE 0 END) AS {c}_nulls' for c in key_columns])} "
            f"FROM {target_table})"
        ),
        "sample_diff": (
            "SELECT t.*, b.* "
            f"FROM {target_table} t FULL OUTER JOIN {baseline_table} b ON {key_join} "
            "WHERE t IS NULL OR b IS NULL LIMIT 100"
        ),
    }
