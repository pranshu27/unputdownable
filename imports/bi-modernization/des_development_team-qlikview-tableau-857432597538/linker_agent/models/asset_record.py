"""
Canonical asset models that represent any structured asset from the RE common model.
These replace raw column-name strings as the primary input to the Linker Agent pipeline.
"""

from __future__ import annotations
from enum import Enum
from typing import Any, List, Optional
from pydantic import BaseModel, Field


class AssetType(str, Enum):
    COLUMN = "column"
    CALCULATION = "calculation"       # DAX measure, Tableau calc field, Qlik expression
    TABLE = "table"
    KPI = "kpi"                       # promoted from calculation with semantic_type = kpi
    DIMENSION = "dimension"           # column with semantic_role = dimension
    MEASURE = "measure"               # column with semantic_role = measure
    RELATIONSHIP = "relationship"


class MetricClassification(str, Enum):
    KPI = "kpi"
    DIMENSION = "dimension"
    MEASURE = "measure"
    CALCULATED = "calculated"
    RATIO = "ratio"
    IDENTIFIER = "identifier"
    DATE = "date"
    UNCLASSIFIED = "unclassified"


class AssetState(str, Enum):
    EXTRACTED = "extracted"
    ENRICHED = "enriched"
    CLASSIFIED = "classified"         # after taxonomy stage (future)
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"


class AssetContext(BaseModel):
    """Source context for an asset — where it lives in the report structure."""
    source_tool: str = "unknown"      # powerbi | tableau | qlik | salesforce
    model_id: str = ""                # RE model UUID
    model_name: str = ""              # dashboard/workbook name
    table_name: Optional[str] = None  # for columns
    table_type: Optional[str] = None  # fact | dimension | bridge | lookup
    domain: Optional[str] = None      # display folder or inferred domain
    pages_used_on: list[str] = Field(default_factory=list)   # page/sheet names
    visual_types_used_in: list[str] = Field(default_factory=list)  # card, bar, table...
    depends_on_columns: list[str] = Field(default_factory=list)    # for calculations
    depends_on_measures: list[str] = Field(default_factory=list)   # for calculations
    technical_summary: Optional[str] = None  # model-level summary from RE


class AssetRecord(BaseModel):
    """
    A single canonical asset from the RE common model.
    Replaces raw column-name strings as the Linker Agent pipeline input.
    """
    asset_id: str                     # stable synthetic ID — see ID generation spec
    asset_type: AssetType
    name: str                         # technical name from source tool
    description: Optional[str] = None # technical description if present in model
    state: AssetState = AssetState.EXTRACTED
    attributes: dict[str, Any] = Field(default_factory=dict)  # type-specific fields
    context: AssetContext = Field(default_factory=AssetContext)

    model_config = {"use_enum_values": True}


class BatchJobResult(BaseModel):
    """Enrichment results for a single job from the Postgres catalog."""
    job_id: str
    total_assets: int
    matched: int
    match_rate_pct: float
    elapsed_seconds: float
    verdict_filter: Optional[List[str]] = None
    results: List["AssetLinkResult"] = Field(default_factory=list)


class BatchEnrichmentResponse(BaseModel):
    """Aggregated results from enriching all available jobs in the Postgres catalog."""
    total_jobs: int
    total_assets_processed: int
    overall_match_rate_pct: float
    elapsed_seconds: float
    jobs: List[BatchJobResult] = Field(default_factory=list)


class AssetLinkResult(BaseModel):
    """
    Output of the enrichment pipeline for a single asset.
    Replaces TermColumnLink as the primary result model.
    """
    asset_id: str
    asset_type: AssetType
    asset_name: str

    # Existing Linker Agent output (preserved)
    term_title: Optional[str] = None
    term_id: Optional[int] = None
    confidence_score: int = 0
    linkage_type: str = ""             # direct | semantic | generated | no_match
    matching_rationale: str = ""

    # Enrichment fields
    business_name: Optional[str] = None
    business_definition: Optional[str] = None          # context-aware description written to catalog (enriched from glossary text + asset context)
    description_enriched: bool = False                 # True when business_definition was LLM-enhanced beyond the raw glossary text
    purpose_statement: Optional[str] = None
    metric_classification: MetricClassification = MetricClassification.UNCLASSIFIED

    # Tier 3 multi-recommendation (populated when linkage_type == "generated")
    tier3_recommendations: Optional[List[dict]] = None

    # Provenance
    enriched_at: Optional[str] = None
    model_id: Optional[str] = None

    model_config = {"use_enum_values": True}
