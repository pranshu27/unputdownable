"""
SQLAlchemy models for BI metadata persistence (Postgres).

Direct 1:1 translation of the 17 Databricks Delta tables
from create_databricks_tables.py into SQLAlchemy ORM models.
"""

from sqlalchemy import Column, String, Boolean, Integer, BigInteger, Float, Text, DateTime, JSON, LargeBinary
from sqlalchemy.orm import declarative_base
from datetime import datetime, timezone

Base = declarative_base()

SCHEMA = "jnj_poc"


# 1. bi_reports — Master table (one row per uploaded file)
class BiReport(Base):
    __tablename__ = "bi_reports"
    __table_args__ = {"schema": SCHEMA}

    report_id = Column(String(255), primary_key=True, nullable=False)
    tool_type = Column(String(50), nullable=False, index=True)
    file_name = Column(String(500))
    uploaded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    executive_summary = Column(Text)


# 2. data_sources
class DataSource(Base):
    __tablename__ = "data_sources"
    __table_args__ = {"schema": SCHEMA}

    source_id = Column(String(255), primary_key=True, nullable=False)
    report_id = Column(String(255), nullable=False, index=True)
    name = Column(String(500))
    source_type = Column(String(255))
    server = Column(String(500))
    database_name = Column(String(255))
    schema_name = Column(String(255))
    connection_details = Column(Text)
    connection_mode = Column(String(100))
    authentication_method = Column(String(255))
    gateway = Column(String(255))
    refresh_schedule = Column(String(255))
    is_extract = Column(Boolean)
    extract_refresh_schedule = Column(String(255))
    is_published = Column(Boolean)
    used_by = Column(Text)
    fingerprint = Column(String(100))


# 3. tables_model
class TableModel(Base):
    __tablename__ = "tables_model"
    __table_args__ = {"schema": SCHEMA}

    table_id = Column(String(255), primary_key=True, nullable=False)
    report_id = Column(String(255), nullable=False, index=True)
    table_name = Column(String(500))
    source_object = Column(String(500))
    is_materialized = Column(Boolean)
    row_count_estimate = Column(BigInteger)
    refresh_frequency = Column(String(255))
    used_by = Column(Text)
    column_signature = Column(String(100))


# 4. columns_metadata
class ColumnMetadata(Base):
    __tablename__ = "columns_metadata"
    __table_args__ = {"schema": SCHEMA}

    column_id = Column(String(255), primary_key=True, nullable=False)
    table_id = Column(String(255), nullable=False, index=True)
    report_id = Column(String(255), nullable=False, index=True)
    name = Column(String(500))
    source_column = Column(String(500))
    data_type = Column(String(100))
    nullable = Column(Boolean)
    is_hidden = Column(Boolean)
    used_in_relationships = Column(Boolean)
    used_in_filters = Column(Boolean)
    used_in_groupby = Column(Boolean)
    used_in_calculations = Column(Boolean)
    used_in_rls = Column(Boolean)
    distinct_count_high = Column(Boolean)
    description = Column(Text)


# 5. relationships
class Relationship(Base):
    __tablename__ = "relationships"
    __table_args__ = {"schema": SCHEMA}

    relationship_id = Column(String(255), primary_key=True, nullable=False)
    report_id = Column(String(255), nullable=False, index=True)
    left_table = Column(String(500))
    left_column = Column(String(500))
    right_table = Column(String(500))
    right_column = Column(String(500))
    cardinality = Column(String(50))
    join_type = Column(String(50))
    is_active = Column(Boolean)
    bidirectional_filter = Column(Boolean)
    composite_key = Column(Boolean)
    enforced_integrity = Column(Boolean)


# 6. transformations
class Transformation(Base):
    __tablename__ = "transformations"
    __table_args__ = {"schema": SCHEMA}

    transformation_id = Column(String(255), primary_key=True, nullable=False)
    report_id = Column(String(255), nullable=False, index=True)
    name = Column(String(500))
    table_name = Column(String(500))
    step_type = Column(String(100))
    expression = Column(Text)
    description = Column(Text)
    data_type = Column(String(100))
    role = Column(String(100))
    used_in = Column(Text)
    filters = Column(Text)


# 7. calculations
class Calculation(Base):
    __tablename__ = "calculations"
    __table_args__ = {"schema": SCHEMA}

    calculation_id = Column(String(255), primary_key=True, nullable=False)
    report_id = Column(String(255), nullable=False, index=True)
    name = Column(String(500))
    expression = Column(Text)
    aggregation = Column(String(100))
    depends_on_columns = Column(Text)
    reusable_metric = Column(Boolean)


# 8. dashboards
class Dashboard(Base):
    __tablename__ = "dashboards"
    __table_args__ = {"schema": SCHEMA}

    dashboard_id = Column(String(255), primary_key=True, nullable=False)
    report_id = Column(String(255), nullable=False, index=True)
    name = Column(String(500))
    object_id = Column(String(255))
    width = Column(Integer)
    height = Column(Integer)
    background_color = Column(String(100))


# 9. dashboard_components
class DashboardComponent(Base):
    __tablename__ = "dashboard_components"
    __table_args__ = {"schema": SCHEMA}

    component_id = Column(String(255), primary_key=True, nullable=False)
    dashboard_id = Column(String(255), nullable=False, index=True)
    name = Column(String(500))
    object_id = Column(String(255))
    position_x = Column(Integer)
    position_y = Column(Integer)
    width = Column(Integer)
    height = Column(Integer)
    font_size = Column(Integer)
    color = Column(String(100))


# 10. visualizations
class Visualization(Base):
    __tablename__ = "visualizations"
    __table_args__ = {"schema": SCHEMA}

    viz_id = Column(String(255), primary_key=True, nullable=False)
    report_id = Column(String(255), nullable=False, index=True)
    dashboard_id = Column(String(255))
    object_id = Column(String(255))
    name = Column(String(500))
    visual_type = Column(String(255))
    formatting = Column(Text)


# 11. viz_chart_mappings
class VizChartMapping(Base):
    __tablename__ = "viz_chart_mappings"
    __table_args__ = {"schema": SCHEMA}

    mapping_id = Column(String(255), primary_key=True, nullable=False)
    viz_id = Column(String(255), nullable=False, index=True)
    x_axis = Column(String(500))
    y_axis = Column(String(500))
    secondary_y_axis = Column(String(500))
    color = Column(String(500))
    text = Column(String(500))
    size = Column(String(500))
    legend = Column(String(500))
    details = Column(String(500))


# 12. viz_table_columns
class VizTableColumn(Base):
    __tablename__ = "viz_table_columns"
    __table_args__ = {"schema": SCHEMA}

    column_id = Column(String(255), primary_key=True, nullable=False)
    viz_id = Column(String(255), nullable=False, index=True)
    name = Column(String(500))
    expression = Column(Text)


# 13. viz_data_bindings
class VizDataBinding(Base):
    __tablename__ = "viz_data_bindings"
    __table_args__ = {"schema": SCHEMA}

    binding_id = Column(String(255), primary_key=True, nullable=False)
    viz_id = Column(String(255), nullable=False, index=True)
    binding_type = Column(String(100))
    field_name = Column(String(500))
    expression = Column(Text)


# 14. filters
class Filter(Base):
    __tablename__ = "filters"
    __table_args__ = {"schema": SCHEMA}

    filter_id = Column(String(255), primary_key=True, nullable=False)
    report_id = Column(String(255), nullable=False, index=True)
    object_id = Column(String(255))
    name = Column(String(500))
    scope = Column(String(100))
    table_name = Column(String(500))
    column_name = Column(String(500))
    columns = Column(Text)
    condition = Column(Text)
    hardcoded = Column(Boolean)
    formatting = Column(Text)
    background_color = Column(String(100))


# 15. parameters_variables
class ParameterVariable(Base):
    __tablename__ = "parameters_variables"
    __table_args__ = {"schema": SCHEMA}

    param_id = Column(String(255), primary_key=True, nullable=False)
    report_id = Column(String(255), nullable=False, index=True)
    name = Column(String(500))
    param_type = Column(String(100))
    expression = Column(Text)


# 16. hierarchies
class Hierarchy(Base):
    __tablename__ = "hierarchies"
    __table_args__ = {"schema": SCHEMA}

    hierarchy_id = Column(String(255), primary_key=True, nullable=False)
    report_id = Column(String(255), nullable=False, index=True)
    name = Column(String(500))
    members = Column(Text)


# 17. rls_policies
class RlsPolicy(Base):
    __tablename__ = "rls_policies"
    __table_args__ = {"schema": SCHEMA}

    policy_id = Column(String(255), primary_key=True, nullable=False)
    report_id = Column(String(255), nullable=False, index=True)
    role_name = Column(String(255))
    table_name = Column(String(500))
    rule_expression = Column(Text)


# 18. extraction_log — tracks per-upload status, runtime, errors
# 19. job_progress — live per-file progress for batch jobs (upserted on every state change)
class JobProgress(Base):
    __tablename__ = "job_progress"
    __table_args__ = {"schema": SCHEMA}

    progress_id = Column(String(255), primary_key=True, nullable=False)   # uuid
    job_id = Column(String(255), nullable=False, index=True)
    file_name = Column(String(500), nullable=False)
    etltool = Column(String(50))
    # queued | extracting | normalizing | writing_postgres | dedup | mapping | completed | failed
    status = Column(String(50), nullable=False, default="queued")
    step = Column(String(255))          # human-readable current step
    started_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    runtime_seconds = Column(String(50))
    error = Column(Text)
    postgres_stored = Column(Boolean, default=False)


class ExtractionLog(Base):
    __tablename__ = "extraction_log"
    __table_args__ = {"schema": SCHEMA}

    log_id = Column(String(255), primary_key=True, nullable=False)
    report_id = Column(String(255), nullable=False, index=True)
    tool_type = Column(String(50), nullable=False)
    file_name = Column(String(500))
    status = Column(String(50), nullable=False)   # SUCCESS / FAILED / PARTIAL
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    runtime_seconds = Column(String(50))          # stored as string e.g. "12.34"
    error = Column(Text)                          # error message if any
    traceback = Column(Text)                      # full traceback if any
    postgres_stored = Column(Boolean)             # whether DB write succeeded
    result = Column(JSON)                         # full RE response JSON
    file_checksum = Column(String(64), index=True)  # SHA-256 hex digest of raw file bytes


# 18. report_images — Image assets stored as binary (BYTEA)
class ReportImage(Base):
    __tablename__ = "report_images"
    __table_args__ = {"schema": SCHEMA}

    image_id = Column(String(255), primary_key=True, nullable=False)
    report_id = Column(String(255), nullable=False, index=True)
    filename = Column(String(500), nullable=False)
    content_type = Column(String(100))
    size_bytes = Column(Integer)
    image_data = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# ── KPI Rationalization tables ───────────────────────────────────────────────

class KpiRationalizationJob(Base):
    """One row per /rationalize call — master job record."""
    __tablename__ = "kpi_rationalization_jobs"
    __table_args__ = {"schema": SCHEMA}

    job_id     = Column(String(255), primary_key=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    file_count = Column(Integer)
    status     = Column(String(50), nullable=False, default="success")  # success | failed
    error      = Column(Text)


class KpiRationalizedCatalog(Base):
    """One row per KPI entry in the rationalized catalog."""
    __tablename__ = "kpi_rationalized_catalog"
    __table_args__ = {"schema": SCHEMA}

    entry_id          = Column(String(255), primary_key=True, nullable=False)
    job_id            = Column(String(255), nullable=False, index=True)
    asset_id          = Column(Text)
    item_type         = Column(String(100))
    name              = Column(String(500))
    source_tool       = Column(String(100))
    report_name       = Column(String(500))
    table_folder      = Column(String(500))
    datasource        = Column(String(500))
    data_type         = Column(String(100))
    semantic_type     = Column(String(100))
    description       = Column(Text)
    formula           = Column(Text)
    normalized_formula = Column(Text)
    ai_verdict        = Column(String(50))
    similarity_score  = Column(Float)
    top_match         = Column(Text)
    rationale         = Column(Text)
    top3_matches      = Column(Text)
    overlap_group_id  = Column(Integer)
    ai_verdict_refined = Column(String(50))
    rationale_refined  = Column(Text)
    is_overlap        = Column(Boolean, default=False)


class KpiVerdictSummary(Base):
    """One row per (item_type, ai_verdict) aggregate in the verdict summary."""
    __tablename__ = "kpi_verdict_summary"
    __table_args__ = {"schema": SCHEMA}

    summary_id = Column(String(255), primary_key=True, nullable=False)
    job_id     = Column(String(255), nullable=False, index=True)
    item_type  = Column(String(100))
    ai_verdict = Column(String(50))
    count      = Column(Integer)


# ── GAP Analysis tables ──────────────────────────────────────────────────────

class GapAnalysisJob(Base):
    """One master row per /gapanalysis call."""
    __tablename__ = "gap_analysis_jobs"
    __table_args__ = {"schema": SCHEMA}

    job_id            = Column(String(255), primary_key=True, nullable=False)
    created_at        = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    source_model_name = Column(String(500))   # "name" field from the source BI JSON
    target_file_name  = Column(String(500))   # uploaded CSV filename
    total_mappings    = Column(Integer)
    summary           = Column(JSON)          # {gap_status: count, ...}
    table_mappings    = Column(JSON)          # table-level mapping list
    status            = Column(String(50), nullable=False, default="success")
    error             = Column(Text)


class GapAnalysisRow(Base):
    """One row per column-pair result from a gap analysis job."""
    __tablename__ = "gap_analysis_rows"
    __table_args__ = {"schema": SCHEMA}

    row_id               = Column(String(255), primary_key=True, nullable=False)
    job_id               = Column(String(255), nullable=False, index=True)
    source_table         = Column(String(500))
    target_table         = Column(String(500))
    column_asset_id      = Column(Text)
    source_column        = Column(String(500))
    mapped_target_column = Column(String(500))
    confidence_score     = Column(Float)
    method               = Column(String(100))
    mapping_reasoning    = Column(Text)
    source_data_type     = Column(String(100))
    target_data_type     = Column(String(100))
    gap_status           = Column(String(100))
    gap_reasoning        = Column(Text)


# Map table name strings (used by normalizer) to model classes
TABLE_NAME_TO_MODEL = {
    "bi_reports": BiReport,
    "data_sources": DataSource,
    "tables_model": TableModel,
    "columns_metadata": ColumnMetadata,
    "relationships": Relationship,
    "transformations": Transformation,
    "calculations": Calculation,
    "dashboards": Dashboard,
    "dashboard_components": DashboardComponent,
    "visualizations": Visualization,
    "viz_chart_mappings": VizChartMapping,
    "viz_table_columns": VizTableColumn,
    "viz_data_bindings": VizDataBinding,
    "filters": Filter,
    "parameters_variables": ParameterVariable,
    "hierarchies": Hierarchy,
    "rls_policies": RlsPolicy,
    "extraction_log": ExtractionLog,
    "job_progress": JobProgress,
    "report_images": ReportImage,
    "kpi_rationalization_jobs": KpiRationalizationJob,
    "kpi_rationalized_catalog": KpiRationalizedCatalog,
    "kpi_verdict_summary": KpiVerdictSummary,
    "gap_analysis_jobs": GapAnalysisJob,
    "gap_analysis_rows": GapAnalysisRow,
}
