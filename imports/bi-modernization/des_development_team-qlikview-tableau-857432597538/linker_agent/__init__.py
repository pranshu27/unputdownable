"""
Linker Agent - Intelligent Data Catalog Linkage System

A standalone module for linking technical database columns to business metadata
using a 3-tier approach: direct links, semantic matching, and term generation.

Main Components:
- ColumnMetadataLookup: 3-tier column-to-business metadata lookup
- process_linkage: KPI attribute mapping and dependency analysis
- AlationClient: Alation data catalog API integration
- AzureLLMClient: Azure OpenAI integration for semantic matching

Example Usage:
    from linker_agent import ColumnMetadataLookup, AlationClient, AzureLLMClient
    
    alation = AlationClient(base_url="...", api_token="...")
    llm = AzureLLMClient(endpoint="...", api_key="...")
    
    lookup = ColumnMetadataLookup(alation_client=alation, llm_client=llm)
    results = await lookup.get_business_metadata_for_columns(["col1", "col2"])
"""

__version__ = "1.0.0"
__author__ = "Linker Agent Team"

# Core exports
from linker_agent.core.column_metadata_lookup import ColumnMetadataLookup
from linker_agent.core.kpi_linkage_engine import process_linkage, LinkageResult, LinkedKPI

# Client exports
from linker_agent.clients.alation_client import SwaggerAPIClient as AlationClient
from linker_agent.clients.alation_client import SwaggerAPIConfig as AlationConfig

# Model exports
from linker_agent.models.term_column_link import TermColumnLink
from linker_agent.models.linkage_result import TermColumnLinkageResult

# LLM exports
from linker_agent.llm.azure_client import AzureOpenAIChatClient as AzureLLMClient

__all__ = [
    # Core
    "ColumnMetadataLookup",
    "process_linkage",
    "LinkageResult",
    "LinkedKPI",
    
    # Clients
    "AlationClient",
    "AlationConfig",
    
    # Models
    "TermColumnLink",
    "TermColumnLinkageResult",
    
    # LLM
    "AzureLLMClient",
]
