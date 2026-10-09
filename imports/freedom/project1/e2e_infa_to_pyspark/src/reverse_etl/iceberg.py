from __future__ import annotations

from typing import Iterable


def build_iceberg_merge_sql(
    target_table: str,
    staging_view: str,
    key_columns: Iterable[str],
    update_columns: Iterable[str],
) -> str:
    keys = list(key_columns)
    updates = [c for c in update_columns if c not in keys]

    if not keys:
        raise ValueError("At least one key column is required for Iceberg MERGE")

    on_clause = "\n     AND ".join([f"t.{c} = s.{c}" for c in keys])
    update_set = ",\n      ".join([f"t.{c} = s.{c}" for c in updates])

    if not update_set:
        update_set = "t.ingestion_ts = s.ingestion_ts"

    return f"""
MERGE INTO {target_table} t
USING {staging_view} s
  ON {on_clause}
WHEN MATCHED THEN UPDATE SET
  {update_set}
WHEN NOT MATCHED THEN INSERT *
""".strip()
