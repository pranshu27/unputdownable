from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .models import MappingDef, WorkflowSpec


@dataclass
class CompiledArtifact:
    mapping_name: str
    pyspark_code: str
    source_sql_overrides: List[str]


def compile_mapping_to_pyspark(spec: WorkflowSpec, mapping_name: str) -> CompiledArtifact:
    mapping = spec.mapping_by_name(mapping_name)
    sql_overrides = _extract_sql_overrides(mapping)
    code = _build_pyspark_job(mapping, sql_overrides)
    return CompiledArtifact(
        mapping_name=mapping.name,
        pyspark_code=code,
        source_sql_overrides=sql_overrides,
    )


def _extract_sql_overrides(mapping: MappingDef) -> List[str]:
    sqls: List[str] = []
    for tf in mapping.transformations:
        if tf.type_name == "Source Qualifier":
            sql = tf.table_attributes.get("Sql Query", "").strip()
            if sql:
                sqls.append(sql)
    return sqls


def _build_pyspark_job(mapping: MappingDef, sql_overrides: List[str]) -> str:
    lines: List[str] = []
    lines.append("from pyspark.sql import SparkSession")
    lines.append("from pyspark.sql import functions as F")
    lines.append("")
    lines.append("")
    lines.append("def run_job(cfg: dict) -> None:")
    lines.append("    spark = (")
    lines.append("        SparkSession.builder")
    lines.append("        .appName(cfg['spark_app_name'])")
    lines.append("        .config('spark.sql.catalog.lakehouse', 'org.apache.iceberg.spark.SparkCatalog')")
    lines.append("        .config('spark.sql.catalog.lakehouse.type', 'hadoop')")
    lines.append("        .config('spark.sql.catalog.lakehouse.warehouse', cfg['warehouse_path'])")
    lines.append("        .getOrCreate()")
    lines.append("    )")
    lines.append("")

    if sql_overrides:
        lines.append("    # Source qualifier SQL overrides extracted from Informatica mapping")
        for idx, _ in enumerate(sql_overrides, start=1):
            lines.append(f"    sq_{idx}_df = spark.sql(cfg['sql_overrides'][{idx - 1}])")
    else:
        lines.append("    # Fallback source read pattern when no SQL override exists")
        lines.append("    sq_1_df = (")
        lines.append("        spark.read")
        lines.append("        .format('jdbc')")
        lines.append("        .option('url', cfg['jdbc']['url'])")
        lines.append("        .option('dbtable', cfg['jdbc']['dbtable'])")
        lines.append("        .option('user', cfg['jdbc']['user'])")
        lines.append("        .option('password', cfg['jdbc']['password'])")
        lines.append("        .load()")
        lines.append("    )")

    lines.append("")
    lines.append("    # Expression and quality-safe projection")
    lines.append("    transformed_df = (")
    lines.append("        sq_1_df")
    lines.append("        .withColumn('ingestion_ts', F.current_timestamp())")
    lines.append("        .withColumn('batch_id', F.lit(cfg['batch_id']))")
    lines.append("    )")
    lines.append("")
    lines.append("    transformed_df.createOrReplaceTempView('stg_transformed')")
    lines.append("    spark.sql(cfg['iceberg_merge_sql'])")
    lines.append("")
    lines.append("    spark.stop()")
    lines.append("")
    lines.append("")
    lines.append("if __name__ == '__main__':")
    lines.append("    raise SystemExit('Use src/main.py to run with YAML config')")

    return "\n".join(lines)
