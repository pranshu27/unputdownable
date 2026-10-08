"""
Data model for business term to technical column link
"""
from pydantic import BaseModel, Field, field_validator
from typing import Literal


class TermColumnLink(BaseModel):
    """
    Represents a link between a business glossary term and a technical database column.
    
    This model supports two types of linkage:
    - Direct: Pre-configured in Alation via Data Asset field (100% confidence)
    - Semantic: LLM-based semantic matching (0-100% confidence)
    
    Attributes:
        term_id: Alation business term ID
        term_title: Business term title (e.g., "Conversion Flag")
        term_description: Business term description (HTML cleaned)
        column_id: Alation column ID
        column_name: Technical column name (e.g., "conversion_indicator")
        table_name: Table name containing the column
        table_id: Alation table ID
        confidence_score: Confidence score 0-100 (100 for direct, 60-100 for semantic)
        linkage_type: Type of linkage ("direct" or "semantic")
        matching_rationale: Explanation of why this match was made
    """
    
    term_id: int = Field(..., description="Alation business term ID", gt=0)
    term_title: str = Field(..., description="Business term title", min_length=1)
    term_description: str = Field(..., description="Business term description")
    column_id: int = Field(..., description="Alation column ID", gt=0)
    column_name: str = Field(..., description="Technical column name", min_length=1)
    table_name: str = Field(..., description="Table name", min_length=1)
    table_id: int = Field(..., description="Alation table ID", gt=0)
    confidence_score: float = Field(
        ..., 
        description="Confidence score 0-100",
        ge=0.0,
        le=100.0
    )
    linkage_type: Literal["direct", "semantic"] = Field(
        ...,
        description="Type of linkage: 'direct' (pre-configured) or 'semantic' (LLM-matched)"
    )
    matching_rationale: str = Field(
        ...,
        description="Explanation of why this match was made",
        min_length=1
    )
    
    @field_validator('confidence_score')
    @classmethod
    def validate_confidence_score(cls, v: float) -> float:
        """Ensure confidence score is between 0 and 100"""
        if not 0.0 <= v <= 100.0:
            raise ValueError(f"Confidence score must be between 0 and 100, got {v}")
        return v
    
    @field_validator('linkage_type')
    @classmethod
    def validate_linkage_type(cls, v: str) -> str:
        """Ensure linkage type is valid"""
        if v not in ["direct", "semantic"]:
            raise ValueError(f"Linkage type must be 'direct' or 'semantic', got {v}")
        return v
    
    def __str__(self) -> str:
        """Human-readable string representation"""
        return (
            f"TermColumnLink("
            f"term='{self.term_title}' → "
            f"column='{self.table_name}.{self.column_name}', "
            f"confidence={self.confidence_score:.1f}%, "
            f"type={self.linkage_type})"
        )
    
    def __repr__(self) -> str:
        """Developer-friendly representation"""
        return self.__str__()
    
    def is_high_confidence(self, threshold: float = 80.0) -> bool:
        """Check if this link has high confidence"""
        return self.confidence_score >= threshold
    
    def is_direct_link(self) -> bool:
        """Check if this is a direct (pre-configured) link"""
        return self.linkage_type == "direct"
    
    def is_semantic_link(self) -> bool:
        """Check if this is a semantic (LLM-matched) link"""
        return self.linkage_type == "semantic"
