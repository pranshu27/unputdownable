"""
Postgres Writer: Inserts normalized rows into PostgreSQL tables.
Auto-creates tables if they don't exist.

Replaces databricks_writer.py — same interface, different backend.
"""

import os
from typing import Any, Dict, List
from contextlib import contextmanager

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

from postgres_models import Base, TABLE_NAME_TO_MODEL, SCHEMA

# Connection URL from env — fallback to team default
POSTGRES_URL = os.getenv("POSTGRES_URL")
# Create engine with connection pool
engine = create_engine(
    POSTGRES_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,       # test connection before use — drops stale ones
    pool_recycle=1800,        # recycle connections every 30 min
    echo=False,
    future=True,
)

# Session factory
SessionLocal = scoped_session(
    sessionmaker(autocommit=False, autoflush=False, bind=engine)
)


def init_db():
    """Create schema and all tables if they don't exist, then apply any pending column migrations."""
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
            conn.commit()
        Base.metadata.create_all(bind=engine)
        print(f"✅ PostgreSQL schema '{SCHEMA}' and tables created successfully")
    except Exception as e:
        print(f"❌ Failed to create PostgreSQL tables: {e}")
        raise

    # ── Column migrations (idempotent — safe to run on every startup) ─────────
    # Each entry: (table, column, column_definition)
    _COLUMN_MIGRATIONS = [
        (
            f"{SCHEMA}.kpi_rationalized_catalog",
            "normalized_formula",
            "TEXT",
        ),
    ]
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            for table, column, col_def in _COLUMN_MIGRATIONS:
                conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_def}"
                ))
            conn.commit()
    except Exception as e:
        print(f"⚠️ Column migration warning: {e}")


@contextmanager
def get_db_session():
    """Context manager for database sessions."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except HTTPException:
        # Let FastAPI HTTP exceptions pass through without rollback noise
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        print(f"❌ Database session error: {e}")
        raise
    finally:
        session.close()


# Ordered list of tables to insert (parent tables first for FK integrity)
TABLE_INSERT_ORDER = [
    "bi_reports",
    "data_sources",
    "tables_model",
    "columns_metadata",
    "relationships",
    "transformations",
    "calculations",
    "dashboards",
    "dashboard_components",
    "visualizations",
    "viz_chart_mappings",
    "viz_table_columns",
    "viz_data_bindings",
    "filters",
    "parameters_variables",
    "hierarchies",
    "rls_policies",
]


def write_to_postgres(normalized_data: Dict[str, List[dict]]) -> Dict[str, Any]:
    """
    Insert all normalized rows into PostgreSQL.
    Creates tables if they don't exist.

    Same interface as write_to_databricks() — drop-in replacement.

    Args:
        normalized_data: Dict from normalizer — keys are table names,
                         values are lists of row dicts.

    Returns:
        Summary dict with counts and status.
    """
    summary = {"stored": False, "tables_written": [], "row_counts": {}, "errors": []}

    try:
        # Step 1: Ensure all tables exist
        print("Checking PostgreSQL tables...")
        init_db()

        # Step 2: Insert data
        with get_db_session() as session:
            for table_name in TABLE_INSERT_ORDER:
                rows = normalized_data.get(table_name, [])
                if not rows:
                    continue

                model_class = TABLE_NAME_TO_MODEL.get(table_name)
                if not model_class:
                    error_msg = f"No model found for table: {table_name}"
                    print(f"  ⚠️ {error_msg}")
                    summary["errors"].append(error_msg)
                    continue

                try:
                    # Get valid column names from the model
                    valid_columns = {c.key for c in model_class.__table__.columns}

                    # Create model instances, filtering out unknown keys
                    instances = []
                    for row in rows:
                        filtered_row = {
                            k: v for k, v in row.items() if k in valid_columns
                        }
                        instances.append(model_class(**filtered_row))

                    session.add_all(instances)
                    session.flush()  # Flush to catch errors per table

                    summary["tables_written"].append(table_name)
                    summary["row_counts"][table_name] = len(instances)
                    print(f"  Inserted {len(instances)} rows into {table_name}")

                except Exception as e:
                    error_msg = f"Error inserting into {table_name}: {str(e)}"
                    print(f"  ❌ {error_msg}")
                    summary["errors"].append(error_msg)

        summary["stored"] = len(summary["errors"]) == 0

        # Grab report_id for the summary
        report_rows = normalized_data.get("bi_reports", [])
        if report_rows:
            summary["report_id"] = report_rows[0].get("report_id", "")

    except Exception as e:
        error_msg = f"PostgreSQL write failed: {str(e)}"
        print(f"  ❌ {error_msg}")
        summary["errors"].append(error_msg)

    return summary


def lookup_by_checksum(file_checksum: str) -> dict | None:
    """
    Return the stored result JSON for the most recent successful extraction
    whose raw file bytes produced *file_checksum* (SHA-256 hex digest).

    Returns None if no matching row exists or the stored result is empty.
    """
    from postgres_models import ExtractionLog

    try:
        with get_db_session() as session:
            log_entry = (
                session.query(ExtractionLog)
                .filter(
                    ExtractionLog.file_checksum == file_checksum,
                    ExtractionLog.status == "SUCCESS",
                    ExtractionLog.result.isnot(None),
                )
                .order_by(ExtractionLog.completed_at.desc())
                .first()
            )
            if log_entry is None:
                return None
            return {
                "report_id":      log_entry.report_id,
                "file_name":      log_entry.file_name,
                "tool_type":      log_entry.tool_type,
                "completed_at":   log_entry.completed_at,
                "runtime_seconds": log_entry.runtime_seconds,
                "result":         log_entry.result,
            }
    except Exception as e:
        print(f"⚠️ Checksum lookup failed: {e}")
        return None


def save_extraction_log(
    report_id: str,
    tool_type: str,
    file_name: str,
    status: str,
    started_at,
    completed_at,
    runtime_seconds: str = None,
    error: str = None,
    traceback: str = None,
    postgres_stored: bool = False,
    result: dict = None,
    file_checksum: str = None,
):
    """
    Persist one row to extraction_log.
    Call this at the end of every upload — success or failure.
    """
    import uuid
    from postgres_models import ExtractionLog

    try:
        with get_db_session() as session:
            # Ensure result is a dict for JSON column
            if isinstance(result, str):
                import json as _json
                try:
                    result = _json.loads(result)
                except Exception:
                    result = {"raw": result}
            log = ExtractionLog(
                log_id=str(uuid.uuid4()),
                report_id=report_id,
                tool_type=tool_type,
                file_name=file_name,
                status=status,
                started_at=started_at,
                completed_at=completed_at,
                runtime_seconds=runtime_seconds,
                error=error,
                traceback=traceback,
                postgres_stored=postgres_stored,
                result=result,
                file_checksum=file_checksum,
            )
            session.add(log)
        print(f"✅ Extraction log saved: {status} for {file_name}")
    except Exception as e:
        print(f"⚠️ Failed to save extraction log: {e}")


def upsert_job_progress(records: List[dict]) -> None:
    """
    Upsert one or more job_progress rows into Postgres.
    Uses INSERT … ON CONFLICT (progress_id) DO UPDATE so every call
    reflects the latest in-memory state.

    Args:
        records: list of dicts matching JobProgress columns.
    """
    if not records:
        return

    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from postgres_models import JobProgress

    try:
        init_db()
        with get_db_session() as session:
            for rec in records:
                stmt = pg_insert(JobProgress).values(**rec)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["progress_id"],
                    set_={k: v for k, v in rec.items() if k != "progress_id"},
                )
                session.execute(stmt)
    except Exception as e:
        print(f"⚠️ Failed to upsert job progress: {e}")


# ---------------------------------------------------------------------------
# KPI Rationalization persistence
# ---------------------------------------------------------------------------

# Maps DataFrame column names (with spaces/slashes) → ORM attribute names
_CATALOG_COL_MAP = {
    "Asset ID":           "asset_id",
    "Item Type":          "item_type",
    "Name":               "name",
    "Source Tool":        "source_tool",
    "Report Name":        "report_name",
    "Table / Folder":     "table_folder",
    "DataSource":         "datasource",
    "Data Type":          "data_type",
    "Semantic Type":      "semantic_type",
    "Description":        "description",
    "Formula":            "formula",
    "Normalized Formula": "normalized_formula",
    "AI Verdict":         "ai_verdict",
    "Similarity Score":   "similarity_score",
    "Top Match":          "top_match",
    "Rationale":          "rationale",
    "Top 3 Matches":      "top3_matches",
    "Overlap Group ID":   "overlap_group_id",
    "AI Verdict Refined": "ai_verdict_refined",
    "Rationale Refined":  "rationale_refined",
}

_SUMMARY_COL_MAP = {
    "Item Type":  "item_type",
    "AI Verdict": "ai_verdict",
    "Count":      "count",
}


def save_rationalization_result(
    job_id: str,
    file_count: int,
    catalog_records: List[dict],
    overlap_records: List[dict],
    summary_records: List[dict],
) -> None:
    """
    Persist a KPI rationalization run to Postgres.

    Writes:
      kpi_rationalization_jobs   — 1 master row
      kpi_rationalized_catalog   — N catalog rows (is_overlap=True for overlap entries)
      kpi_verdict_summary        — M summary rows

    Args:
        job_id          — uuid for this rationalization run
        file_count      — number of BI files processed
        catalog_records — list of dicts from _df_to_records(df_rationalized)
        overlap_records — list of dicts from _df_to_records(overlap_df)
        summary_records — list of dicts from _df_to_records(verdict_summary)
    """
    import uuid as _uuid
    from postgres_models import KpiRationalizationJob, KpiRationalizedCatalog, KpiVerdictSummary
    from datetime import datetime, timezone

    # Pre-compute set of asset_ids that are in the overlaps subset
    overlap_asset_ids = {
        r.get("Asset ID") for r in overlap_records if r.get("Asset ID")
    }

    try:
        init_db()
        with get_db_session() as session:
            # 1. Master job row
            session.add(KpiRationalizationJob(
                job_id=job_id,
                created_at=datetime.now(timezone.utc),
                file_count=file_count,
                status="success",
            ))

            # 2. Catalog rows
            for rec in catalog_records:
                row_kwargs = {"entry_id": str(_uuid.uuid4()), "job_id": job_id}
                for df_col, orm_col in _CATALOG_COL_MAP.items():
                    val = rec.get(df_col)
                    # Replace NaN / None uniformly; coerce overlap_group_id to int
                    if orm_col == "overlap_group_id" and val is not None:
                        try:
                            val = int(val)
                        except (TypeError, ValueError):
                            val = None
                    elif orm_col == "similarity_score" and val is not None:
                        try:
                            val = float(val)
                        except (TypeError, ValueError):
                            val = None
                    row_kwargs[orm_col] = val
                row_kwargs["is_overlap"] = rec.get("Asset ID") in overlap_asset_ids
                session.add(KpiRationalizedCatalog(**row_kwargs))

            # 3. Verdict summary rows
            for rec in summary_records:
                row_kwargs = {"summary_id": str(_uuid.uuid4()), "job_id": job_id}
                for df_col, orm_col in _SUMMARY_COL_MAP.items():
                    val = rec.get(df_col)
                    if orm_col == "count" and val is not None:
                        try:
                            val = int(val)
                        except (TypeError, ValueError):
                            val = None
                    row_kwargs[orm_col] = val
                session.add(KpiVerdictSummary(**row_kwargs))

        print(f"✅ KPI rationalization saved: job_id={job_id}, "
              f"{len(catalog_records)} catalog rows, {len(summary_records)} summary rows")
    except Exception as e:
        print(f"⚠️ Failed to save KPI rationalization result: {e}")
        raise


def fetch_rationalization_result(job_id: str) -> dict | None:
    """
    Fetch a previously saved KPI rationalization result from Postgres.

    Returns a dict with keys:
        job_id, created_at, file_count, status,
        rationalized_catalog, rationalized_overlaps_duplicates, rationalized_verdict_summary

    Returns None if the job_id is not found.
    """
    from postgres_models import KpiRationalizationJob, KpiRationalizedCatalog, KpiVerdictSummary

    try:
        with get_db_session() as session:
            job = session.query(KpiRationalizationJob).filter(
                KpiRationalizationJob.job_id == job_id
            ).first()

            if job is None:
                return None

            # Reverse the ORM → dict mapping for catalog
            _orm_to_df = {v: k for k, v in _CATALOG_COL_MAP.items()}

            catalog_rows = session.query(KpiRationalizedCatalog).filter(
                KpiRationalizedCatalog.job_id == job_id
            ).all()

            summary_rows = session.query(KpiVerdictSummary).filter(
                KpiVerdictSummary.job_id == job_id
            ).all()

            def _catalog_to_dict(row) -> dict:
                out = {}
                for orm_col, df_col in _orm_to_df.items():
                    out[df_col] = getattr(row, orm_col, None)
                out["is_overlap"] = row.is_overlap
                return out

            catalog_records = [_catalog_to_dict(r) for r in catalog_rows]
            overlap_records = [r for r in catalog_records if r.get("is_overlap")]
            summary_records = [
                {
                    "Item Type":  r.item_type,
                    "AI Verdict": r.ai_verdict,
                    "Count":      r.count,
                }
                for r in summary_rows
            ]

            return {
                "job_id":     job.job_id,
                "created_at": str(job.created_at),
                "file_count": job.file_count,
                "status":     job.status,
                "error":      job.error,
                "rationalized_catalog":             catalog_records,
                "rationalized_overlaps_duplicates": overlap_records,
                "rationalized_verdict_summary":     summary_records,
            }
    except Exception as e:
        print(f"⚠️ Failed to fetch KPI rationalization result: {e}")
        raise


# ---------------------------------------------------------------------------
# GAP Analysis persistence
# ---------------------------------------------------------------------------

def save_gap_analysis_result(
    job_id: str,
    source_model_name: str,
    target_file_name: str,
    gap_analysis_records: list,
    summary: dict,
    table_mappings: list,
) -> None:
    """
    Persist a gap analysis run to Postgres.

    Writes:
      gap_analysis_jobs — 1 master row
      gap_analysis_rows — N column-pair rows

    Args:
        job_id                — uuid for this gap analysis run
        source_model_name     — name field from the source BI JSON
        target_file_name      — filename of the uploaded target CSV
        gap_analysis_records  — list of dicts from gap_df.to_dict(orient="records")
        summary               — {gap_status: count} dict
        table_mappings        — table-level mapping list
    """
    import uuid as _uuid
    from postgres_models import GapAnalysisJob, GapAnalysisRow
    from datetime import datetime, timezone

    try:
        init_db()
        with get_db_session() as session:
            session.add(GapAnalysisJob(
                job_id=job_id,
                created_at=datetime.now(timezone.utc),
                source_model_name=source_model_name,
                target_file_name=target_file_name,
                total_mappings=len(gap_analysis_records),
                summary=summary,
                table_mappings=table_mappings,
                status="success",
            ))

            for rec in gap_analysis_records:
                def _str(v):
                    return None if v in (None, "N/A") else str(v)

                def _float(v):
                    try:
                        return float(v) if v not in (None, "N/A") else None
                    except (TypeError, ValueError):
                        return None

                session.add(GapAnalysisRow(
                    row_id=str(_uuid.uuid4()),
                    job_id=job_id,
                    source_table=_str(rec.get("Source Table")),
                    target_table=_str(rec.get("Target Table")),
                    column_asset_id=_str(rec.get("Column_Asset_ID")),
                    source_column=_str(rec.get("Source Column")),
                    mapped_target_column=_str(rec.get("Mapped Target Column")),
                    confidence_score=_float(rec.get("Confidence Score")),
                    method=_str(rec.get("Method")),
                    mapping_reasoning=_str(rec.get("Reasoning")),
                    source_data_type=_str(rec.get("Source_Data_Type")),
                    target_data_type=_str(rec.get("Target_Data_Type")),
                    gap_status=_str(rec.get("GAP_Status")),
                    gap_reasoning=_str(rec.get("GAP_Reasoning")),
                ))

        print(f"✅ GAP analysis saved: job_id={job_id}, {len(gap_analysis_records)} rows")
    except Exception as e:
        print(f"⚠️ Failed to save GAP analysis result: {e}")
        raise


def fetch_gap_analysis_result(job_id: str) -> dict | None:
    """
    Fetch a previously saved gap analysis result from Postgres.

    Returns a dict mirroring the POST /gapanalysis/ response (plus job metadata),
    or None if the job_id is not found.
    """
    from postgres_models import GapAnalysisJob, GapAnalysisRow

    try:
        with get_db_session() as session:
            job = session.query(GapAnalysisJob).filter(
                GapAnalysisJob.job_id == job_id
            ).first()

            if job is None:
                return None

            rows = session.query(GapAnalysisRow).filter(
                GapAnalysisRow.job_id == job_id
            ).all()

            gap_analysis = [
                {
                    "Source Table":         r.source_table,
                    "Target Table":         r.target_table,
                    "Column_Asset_ID":      r.column_asset_id,
                    "Source Column":        r.source_column,
                    "Mapped Target Column": r.mapped_target_column,
                    "Confidence Score":     r.confidence_score,
                    "Method":               r.method,
                    "Reasoning":            r.mapping_reasoning,
                    "Source_Data_Type":     r.source_data_type,
                    "Target_Data_Type":     r.target_data_type,
                    "GAP_Status":           r.gap_status,
                    "GAP_Reasoning":        r.gap_reasoning,
                }
                for r in rows
            ]

            return {
                "job_id":            job.job_id,
                "created_at":        str(job.created_at),
                "source_model_name": job.source_model_name,
                "target_file_name":  job.target_file_name,
                "status":            job.status,
                "error":             job.error,
                "gap_analysis":      gap_analysis,
                "summary":           job.summary,
                "total_mappings":    job.total_mappings,
                "table_mappings":    job.table_mappings,
            }
    except Exception as e:
        print(f"⚠️ Failed to fetch GAP analysis result: {e}")
        raise
