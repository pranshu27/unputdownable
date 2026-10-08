"""PostgreSQL helper — loads visualization/metadata from jnj_poc schema."""
import os
from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import pandas as pd

POSTGRES_URL = os.getenv(
    "POSTGRES_URL",
    "postgresql://LLM_DBAdmin_PostgreSQL:kcgxXbmMzHf98m8j"
    "@datamarketplace-applicationdatabase.c9z9oimycomq.us-east-2.rds.amazonaws.com:4528/LLM"
)
SCHEMA = "jnj_poc"

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(POSTGRES_URL, pool_size=2, max_overflow=8, future=True,
                                connect_args={"connect_timeout": 10})
    return _engine


@contextmanager
def get_session():
    Session = sessionmaker(bind=get_engine(), autocommit=False, autoflush=False)
    session = Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def load_report_data(report_id: str) -> dict:
    """Fetch all data for one report across all jnj_poc tables."""
    tables = [
        "data_sources", "tables_model", "columns_metadata",
        "relationships", "calculations",
        "dashboards", "dashboard_components", "visualizations",
        "viz_chart_mappings", "viz_table_columns", "viz_data_bindings",
        "filters", "parameters_variables",
    ]
    result = {}
    try:
        with get_engine().connect() as conn:
            for tbl in tables:
                q = text(f'SELECT * FROM {SCHEMA}."{tbl}" WHERE report_id = :rid')
                result[tbl] = pd.read_sql(q, conn, params={"rid": report_id}).to_dict("records")
    except Exception as e:
        print(f"[db] Warning: could not load Postgres data for report {report_id}: {e}")
        result = {}
    return result


def find_report_by_name(file_name: str) -> str | None:
    """Return report_id for a file_name, or None if not found."""
    try:
        with get_engine().connect() as conn:
            q = text(f"SELECT report_id FROM {SCHEMA}.bi_reports WHERE file_name = :fn LIMIT 1")
            row = conn.execute(q, {"fn": file_name}).fetchone()
            return row[0] if row else None
    except Exception as e:
        print(f"[db] Warning: {e}")
        return None


def load_visualizations_for_report(report_id: str) -> list[dict]:
    """Return merged visualization rows with chart mappings."""
    try:
        with get_engine().connect() as conn:
            q = text(f"""
                SELECT v.viz_id, v.name, v.visual_type, v.dashboard_id, v.object_id,
                       m.mapping_id, m.axis_role, m.table_name, m.column_name, m.aggregation,
                       m.field_position
                FROM {SCHEMA}.visualizations v
                LEFT JOIN {SCHEMA}.viz_chart_mappings m ON v.viz_id = m.viz_id
                WHERE v.report_id = :rid
                ORDER BY v.viz_id, m.field_position
            """)
            rows = pd.read_sql(q, conn, params={"rid": report_id}).to_dict("records")
            return rows
    except Exception as e:
        print(f"[db] Warning: {e}")
        return []
