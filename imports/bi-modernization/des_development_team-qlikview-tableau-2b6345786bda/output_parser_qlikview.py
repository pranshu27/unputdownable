"""
QlikView-Specific Output Parsers for Common Model Format

This file contains Pydantic models and output parsers specifically for QlikView
Phase 2 extraction (Common Model format).

Separated from main output_parser.py to avoid merge conflicts with Tableau/PowerBI team.

Author: Data Economy AI
Date: 2026-04-24
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict
from langchain_core.output_parsers import JsonOutputParser


# ============================================================================
# PHASE 2: COMMON MODEL OUTPUT PARSERS (QlikView-Specific)
# These parsers match the Common Model schema exactly (no transformation needed)
# ============================================================================

# --- Data Sources (Common Model Format) ---
class CommonDataSource(BaseModel):
    id: str = Field(..., description="Unique identifier: ds_<sanitized_name>")
    name: str = Field(..., description="Original source name")
    source_type: str = Field(..., description="Source type: file, database, api, inline")
    connection_mode: str = Field(..., description="Connection mode: import, direct_query")
    authentication_method: Optional[str] = Field(None, description="Authentication method: file_system, windows, sql, oauth, null")
    server: Optional[str] = Field(None, description="Server name for database sources")
    database: Optional[str] = Field(None, description="Database name")
    schema_name: Optional[str] = Field(None, alias="schema", description="Schema name")
    path: Optional[str] = Field(None, description="File path for file sources")
    gateway: Optional[str] = Field(None, description="Gateway (null for QlikView)")
    refresh_frequency: Optional[str] = Field(None, description="Refresh schedule")
    connection_details: Optional[str] = Field(None, description="Additional connection info")
    is_published: Optional[bool] = Field(None, description="Whether published (null for QlikView)")
    
    model_config = ConfigDict(populate_by_name=True)

class CommonDataSourcesWrapper(BaseModel):
    data_sources: List[CommonDataSource] = Field(..., description="List of data sources in Common Model format")

common_data_sources_output_parser = JsonOutputParser(pydantic_object=CommonDataSourcesWrapper)


# --- Relationships (Common Model Format) ---
class CommonRelationship(BaseModel):
    id: str = Field(..., description="Unique identifier: rel_<left_table>_<right_table>")
    left_table_id: str = Field(..., description="Left table ID: tbl_<sanitized_name>")
    left_column: str = Field(..., description="Column name in left table")
    right_table_id: str = Field(..., description="Right table ID: tbl_<sanitized_name>")
    right_column: str = Field(..., description="Column name in right table")
    cardinality: str = Field(..., description="Cardinality: one_to_one, one_to_many, many_to_one, many_to_many")
    join_type: str = Field(..., description="Join type: inner, left, right, full")
    active: bool = Field(..., description="Whether relationship is active")
    filter_direction: str = Field(..., description="Filter direction: bidirectional, single")
    enforced_integrity: Optional[bool] = Field(None, description="Whether referential integrity is enforced")
    relationship_type: str = Field(..., description="Type: dimension_lookup, bridge, date_relationship")
    note: Optional[str] = Field(None, description="Explanation of how relationship was inferred")

class CommonRelationshipsWrapper(BaseModel):
    relationships: List[CommonRelationship] = Field(..., description="List of relationships in Common Model format")

common_relationships_output_parser = JsonOutputParser(pydantic_object=CommonRelationshipsWrapper)


# --- Tables (Common Model Format) ---
class CommonColumnMetadata(BaseModel):
    name: str = Field(..., description="Column name")
    data_type: str = Field(..., description="Data type: string, integer, decimal, date, datetime, boolean")
    nullable: Optional[bool] = Field(None, description="Whether column can be null (null if unknown)")
    hidden: bool = Field(False, description="Whether column is hidden")
    semantic_role: Optional[str] = Field(None, description="Role: primary_key, foreign_key, dimension, measure, date, identifier, null")
    used_in_relationships: Optional[bool] = Field(None, description="Used in relationships (null if unknown)")
    used_in_filters: Optional[bool] = Field(None, description="Used in filters (null if unknown)")
    used_in_groupby: Optional[bool] = Field(None, description="Used in group by (null if unknown)")
    used_in_calculations: Optional[bool] = Field(None, description="Used in calculations (null if unknown)")
    distinct_count_high: Optional[bool] = Field(None, description="High cardinality (null if unknown)")
    description: Optional[str] = Field(None, description="Column description")

class CommonIngestionStep(BaseModel):
    order: int = Field(..., description="Step execution order")
    step_type: str = Field(..., description="Type: read, filter, join, aggregate, derive, rename, change_type, split_to_rows, merge, reference")
    description: str = Field(..., description="Human-readable step description")
    native_expressions: Dict[str, str] = Field(default_factory=dict, description="Native expressions by tool (qlikview, powerquery, sql)")
    columns_affected: Optional[List[str]] = Field(None, description="Columns affected by this step")

class CommonIngestion(BaseModel):
    steps: List[CommonIngestionStep] = Field(default_factory=list, description="Ordered transformation steps")

class CommonTable(BaseModel):
    id: str = Field(..., description="Unique identifier: tbl_<sanitized_name>")
    name: str = Field(..., description="Original table name")
    table_type: str = Field(..., description="Type: fact, dimension, bridge, lookup")
    source_data_source_id: Optional[str] = Field(None, description="Source data source ID: ds_<sanitized_name>")
    is_materialized: Optional[bool] = Field(None, description="Whether table is materialized")
    description: Optional[str] = Field(None, description="Table description")
    columns: List[CommonColumnMetadata] = Field(..., description="List of columns with metadata")
    ingestion: CommonIngestion = Field(default_factory=CommonIngestion, description="Ingestion pipeline")

class CommonTablesWrapper(BaseModel):
    tables: List[CommonTable] = Field(..., description="List of tables in Common Model format")

common_tables_output_parser = JsonOutputParser(pydantic_object=CommonTablesWrapper)


# --- Calculations (Common Model Format) ---
class CommonCalculationDisplay(BaseModel):
    folder: str = Field(..., description="Display folder for organization")
    hidden: bool = Field(False, description="Whether calculation is hidden")
    tags: List[str] = Field(default_factory=list, description="Tags for searchability")

class CommonCalculationExpressions(BaseModel):
    qlikview: str = Field(..., description="Original QlikView expression")
    dax: str = Field("", description="DAX expression (empty for now)")
    tableau: str = Field("", description="Tableau expression (empty for now)")

class CommonCalculation(BaseModel):
    id: str = Field(..., description="Unique identifier: calc_<sanitized_name>")
    name: str = Field(..., description="Calculation name")
    description: Optional[str] = Field(None, description="Business description")
    semantic_type: str = Field(..., description="Type: sum, count, avg, ratio, growth_rate, custom")
    aggregation_behavior: str = Field(..., description="Behavior: additive, semi_additive, non_additive")
    data_type: str = Field(..., description="Result data type: string, integer, decimal, date, datetime, boolean")
    format_string: Optional[str] = Field(None, description="Display format: #,##0.00, 0.00%, etc.")
    is_base_measure: bool = Field(..., description="Whether this is a base measure or derived")
    reusable: bool = Field(True, description="Whether calculation is reusable")
    depends_on_columns: List[str] = Field(default_factory=list, description="Dependent columns: Table.Column")
    depends_on_measures: List[str] = Field(default_factory=list, description="Dependent measures/variables")
    display: CommonCalculationDisplay = Field(..., description="Display metadata")
    expressions: CommonCalculationExpressions = Field(..., description="Expressions in different tools")

class CommonCalculationsWrapper(BaseModel):
    calculations: List[CommonCalculation] = Field(..., description="List of calculations in Common Model format")

common_calculations_output_parser = JsonOutputParser(pydantic_object=CommonCalculationsWrapper)
