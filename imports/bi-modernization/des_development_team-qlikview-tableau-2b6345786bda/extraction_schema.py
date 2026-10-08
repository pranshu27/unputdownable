from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from enum import Enum


# ---------- ENUMS ----------

class BITool(str, Enum):
    power_bi = "power_bi"
    tableau = "tableau"


class ConnectionMode(str, Enum):
    import_mode = "import"
    direct_query = "direct_query"
    live = "live"
    extract = "extract"


class DataType(str, Enum):
    integer = "integer"
    decimal = "decimal"
    string = "string"
    date = "date"
    datetime = "datetime"
    boolean = "boolean"
    unknown = "unknown"


class Cardinality(str, Enum):
    one_to_one = "1:1"
    one_to_many = "1:M"
    many_to_many = "M:M"


class JoinType(str, Enum):
    inner = "inner"
    left = "left"
    right = "right"
    full = "full"
    cross = "cross"


# ---------- SOURCE ----------

class DataSource(BaseModel):
    name: str
    source_type: str                 # SQL Server, Snowflake, Excel, API
    server: Optional[str]
    database: Optional[str]
    schema: Optional[str]
    connection_mode: ConnectionMode
    authentication_method: Optional[str]
    gateway: Optional[str]
    refresh_frequency: Optional[str]


# ---------- COLUMN ----------

class ColumnMetadata(BaseModel):
    name: str
    source_column: Optional[str]
    data_type: DataType
    nullable: Optional[bool]
    hidden: Optional[bool]

    # key detection signals
    used_in_relationships: Optional[bool] = False
    used_in_filters: Optional[bool] = False
    used_in_groupby: Optional[bool] = False
    used_in_calculations: Optional[bool] = False
    used_in_rls: Optional[bool] = False
    distinct_count_high: Optional[bool] = False

    description: Optional[str]


# ---------- TABLE ----------

class TableMetadata(BaseModel):
    name: str
    source_object: Optional[str]          # view/table/query
    row_count_estimate: Optional[int]
    is_materialized: Optional[bool]
    refresh_frequency: Optional[str]
    columns: List[ColumnMetadata]


# ---------- RELATIONSHIPS ----------

class RelationshipMetadata(BaseModel):
    left_table: str
    left_column: str
    right_table: str
    right_column: str
    cardinality: Cardinality
    join_type: JoinType
    active: Optional[bool] = True
    bidirectional_filter: Optional[bool] = False
    composite_key: Optional[bool] = False
    enforced_integrity: Optional[bool] = False


# ---------- TRANSFORMATIONS ----------

class TransformationStep(BaseModel):
    table_name: str
    step_type: str              # merge, append, filter, derive, aggregate
    description: Optional[str]
    expression: Optional[str]


# ---------- CALCULATIONS ----------

class CalculationMetadata(BaseModel):
    name: str
    expression: str
    aggregation: Optional[str]      # SUM, COUNTD, AVG, LOD, CALCULATE
    depends_on_columns: List[str]
    reusable_metric: Optional[bool] = False


# ---------- FILTERS ----------

class FilterMetadata(BaseModel):
    scope: str                      # dataset / page / visual
    table: Optional[str]
    column: Optional[str]
    condition: str
    hardcoded: Optional[bool] = False


# ---------- SECURITY ----------

class RLSPolicy(BaseModel):
    role_name: str
    table: str
    rule_expression: str


# ---------- ROOT DOCUMENT ----------

class BIDocumentation(BaseModel):
    tool: BITool
    model_name: str

    data_sources: List[DataSource]
    tables: List[TableMetadata]
    relationships: List[RelationshipMetadata]

    transformations: List[TransformationStep] = []
    calculations: List[CalculationMetadata] = []
    filters: List[FilterMetadata] = []
    rls_policies: List[RLSPolicy] = []

    extracted_at: Optional[str]
    extractor_version: Optional[str]
