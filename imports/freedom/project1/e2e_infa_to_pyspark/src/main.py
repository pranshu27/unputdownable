from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from reverse_etl.compiler import compile_mapping_to_pyspark
from reverse_etl.iceberg import build_iceberg_merge_sql
from reverse_etl.parser import parse_informatica_xml
from reverse_etl.validators import build_parity_checks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reverse engineer Informatica XML to PySpark artifacts")
    parser.add_argument("--config", required=True, help="Path to pipeline YAML config")
    return parser.parse_args()


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> int:
    args = parse_args()
    cfg = load_config(args.config)

    spec = parse_informatica_xml(cfg["xml_path"])
    compiled = compile_mapping_to_pyspark(spec, cfg["mapping_name"])

    merge_sql = build_iceberg_merge_sql(
        target_table=cfg["target_table"],
        staging_view="stg_transformed",
        key_columns=cfg["merge_keys"],
        update_columns=cfg["update_columns"],
    )

    parity = build_parity_checks(
        target_table=cfg["target_table"],
        baseline_table=cfg["baseline_table"],
        key_columns=cfg["merge_keys"],
    )

    out_dir = Path(cfg["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    pyspark_job_path = out_dir / f"{cfg['mapping_name']}_job.py"
    with open(pyspark_job_path, "w", encoding="utf-8") as f:
        f.write(compiled.pyspark_code)

    sql_override_path = out_dir / f"{cfg['mapping_name']}_sql_overrides.sql"
    with open(sql_override_path, "w", encoding="utf-8") as f:
        for sql in compiled.source_sql_overrides:
            f.write(sql)
            f.write("\n\n-- ----------------------------------------\n\n")

    merge_sql_path = out_dir / f"{cfg['mapping_name']}_iceberg_merge.sql"
    with open(merge_sql_path, "w", encoding="utf-8") as f:
        f.write(merge_sql)
        f.write("\n")

    parity_path = out_dir / f"{cfg['mapping_name']}_parity_checks.sql"
    with open(parity_path, "w", encoding="utf-8") as f:
        for name, query in parity.items():
            f.write(f"-- {name}\n")
            f.write(query)
            f.write(";\n\n")

    run_cfg_path = out_dir / f"{cfg['mapping_name']}_runtime_config.yml"
    runtime_cfg = {
        "spark_app_name": cfg["spark_app_name"],
        "warehouse_path": cfg["warehouse_path"],
        "batch_id": cfg["batch_id"],
        "jdbc": cfg["jdbc"],
        "sql_overrides": compiled.source_sql_overrides,
        "iceberg_merge_sql": merge_sql,
    }
    with open(run_cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(runtime_cfg, f, sort_keys=False)

    print(f"Generated PySpark job: {pyspark_job_path}")
    print(f"Generated SQL overrides: {sql_override_path}")
    print(f"Generated Iceberg MERGE SQL: {merge_sql_path}")
    print(f"Generated parity checks: {parity_path}")
    print(f"Generated runtime config: {run_cfg_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
