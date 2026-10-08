"""
KPI Data Model for Linker Agent
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from uuid import UUID, uuid4


class KPI(BaseModel):
    """
    Key Performance Indicator model
    
    Represents a KPI with its definition, formula, and metadata
    """
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(..., description="KPI name")
    definition: str = Field(..., description="Business definition of the KPI")
    formula: str = Field(..., description="Technical formula or calculation logic")
    category: Optional[str] = Field(default="", description="KPI category (e.g., Risk, Capital, Liquidity)")
    formula_components: Optional[List[str]] = Field(default_factory=list, description="Components extracted from formula")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "name": "Capital Adequacy Ratio",
            "definition": "Ratio of bank's capital to its risk-weighted assets",
            "formula": "Total Capital / Risk-Weighted Assets",
            "category": "Capital",
        }
    })
