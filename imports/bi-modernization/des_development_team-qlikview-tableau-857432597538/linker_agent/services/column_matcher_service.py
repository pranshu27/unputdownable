"""Service layer wrapping the 3-tier column metadata lookup pipeline."""

import logging
from typing import Dict, List, Optional

from linker_agent.clients.alation_client import SwaggerAPIClient
from linker_agent.config import get_config
from linker_agent.core.column_metadata_lookup import ColumnMetadataLookup
from linker_agent.utils.llm_factory import get_azure_chat_client

logger = logging.getLogger(__name__)


class ColumnMatcherService:
    """Wraps ColumnMetadataLookup for use by API routes and the MCP server.

    Handles LLM client initialization and config so callers only supply
    column names and a glossary ID.
    """

    def __init__(self, client: SwaggerAPIClient):
        self._client = client

    def _build_lookup(self, glossary_id: int) -> ColumnMetadataLookup:
        cfg = get_config()
        llm_client = get_azure_chat_client()
        return ColumnMetadataLookup(
            swagger_client=self._client,
            llm_client=llm_client,
            confidence_threshold=cfg.confidence_threshold,
            cache_hours=cfg.cache_hours,
            glossary_id=glossary_id,
            enrich_descriptions=True,
        )

    async def match_column(
        self,
        column_name: str,
        glossary_id: int = 2,
        use_cache: bool = True,
    ) -> Optional[Dict]:
        """Run the full 3-tier pipeline for a single column name.

        Returns the metadata dict or None if not found.
        """
        logger.info(f"Matching column '{column_name}' in glossary {glossary_id}")
        lookup = self._build_lookup(glossary_id)
        results = await lookup.get_business_metadata_for_columns(
            [column_name], use_cache=use_cache
        )
        return results.get(column_name)

    async def batch_match_columns(
        self,
        column_names: List[str],
        glossary_id: int = 2,
        use_cache: bool = True,
    ) -> Dict[str, Optional[Dict]]:
        """Run the full 3-tier pipeline for multiple column names.

        Returns a dict mapping each column name → metadata dict (or None).
        """
        logger.info(
            f"Batch matching {len(column_names)} columns in glossary {glossary_id}"
        )
        lookup = self._build_lookup(glossary_id)
        return await lookup.get_business_metadata_for_columns(
            column_names, use_cache=use_cache
        )
