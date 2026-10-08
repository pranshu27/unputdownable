"""
AssetMatcherService — generic replacement for ColumnMatcherService.
Routes any AssetRecord through the existing 3-tier Alation lookup pipeline.
The 3-tier engine is unchanged; only the context assembly changes per asset type.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from linker_agent.clients.alation_client import SwaggerAPIClient
from linker_agent.config import get_config
from linker_agent.core.column_metadata_lookup import ColumnMetadataLookup
from linker_agent.core.event_log_service import write_event
from linker_agent.ingestion.context_builder import EnrichmentContext, build_context
from linker_agent.models.asset_record import AssetLinkResult, AssetRecord, MetricClassification
from linker_agent.models.event_log import EventAction
from linker_agent.utils.llm_factory import get_azure_chat_client

logger = logging.getLogger(__name__)

_LINKAGE_TO_ACTION = {
    'direct': EventAction.TIER1_MATCH,
    'semantic': EventAction.TIER2_MATCH,
    'generated': EventAction.TIER3_GENERATED,
}

_CLASSIFICATION_MAP = {
    'kpi': MetricClassification.KPI,
    'dimension': MetricClassification.DIMENSION,
    'measure': MetricClassification.MEASURE,
    'calculated': MetricClassification.CALCULATED,
    'ratio': MetricClassification.RATIO,
    'identifier': MetricClassification.IDENTIFIER,
    'date': MetricClassification.DATE,
}


class AssetMatcherService:
    """
    Enriches any AssetRecord with business metadata using the 3-tier pipeline.

    Tier 1: Direct Alation link lookup (no LLM)
    Tier 2: Semantic LLM matching against existing Alation terms
    Tier 3: LLM generates a new business term

    Calls ColumnMetadataLookup.get_business_metadata_with_context() so that
    the asset-type-aware EnrichmentContext (DAX expressions, semantic_type,
    page usage) reaches the LLM prompt instead of a bare column name.
    """

    def __init__(
        self,
        swagger_client: SwaggerAPIClient,
        glossary_id: Optional[int] = None,
        confidence_threshold: Optional[int] = None,
    ):
        self._swagger_client = swagger_client
        cfg = get_config()
        self._glossary_id = glossary_id or cfg.glossary_id
        self._confidence_threshold = confidence_threshold or cfg.confidence_threshold

    def _build_lookup(self) -> ColumnMetadataLookup:
        llm_client = get_azure_chat_client()
        return ColumnMetadataLookup(
            swagger_client=self._swagger_client,
            llm_client=llm_client,
            confidence_threshold=self._confidence_threshold,
            glossary_id=self._glossary_id,
            enrich_descriptions=True,
        )

    def _build_column_context(
        self, asset: AssetRecord, ctx: EnrichmentContext
    ) -> Dict[str, Any]:
        """
        Convert EnrichmentContext → column_context dict for ColumnMetadataLookup.

        Maps asset-type-aware fields into the keys that _semantic_match_column_to_term
        and _generate_new_business_term already read from the prompt:
          description       ← technical_description (DAX expr, semantic_type, depends_on…)
          table_name        ← model_name (dashboard/workbook name)
          table_description ← usage_context (pages and visual types)
          table_type        ← asset_type string ("calculation", "column", "table"…)
          schema_name       ← source_tool ("powerbi", "tableau"…)
          schema_description← business_context (dashboard + domain sentence)
        """
        return {
            'name': asset.name,
            'description': ctx.technical_description,
            'table_name': asset.context.model_name,
            'table_description': ctx.usage_context,
            'table_type': str(asset.asset_type),
            'schema_name': asset.context.source_tool,
            'schema_description': ctx.business_context,
        }

    async def enrich_asset(self, asset: AssetRecord) -> AssetLinkResult:
        """
        Enrich a single AssetRecord with business metadata.
        Writes an event at the tier decision point.
        """
        ctx = build_context(asset)
        lookup = self._build_lookup()
        column_context = self._build_column_context(asset, ctx)

        result_dict = await lookup.get_business_metadata_with_context(
            asset.name, column_context, use_cache=True
        )

        if result_dict is None:
            return self._no_match_result(asset, ctx)

        return self._build_result_from_lookup(asset, ctx, result_dict)

    async def enrich_batch(
        self,
        assets: list[AssetRecord],
        max_concurrent: int = 5,
        context_builder_override=None,
    ) -> list[AssetLinkResult]:
        """Enrich a batch of assets concurrently. Returns results in original order.

        A single ColumnMetadataLookup instance is shared across all tasks so the
        in-memory _terms_cache and _reverse_index_cache are populated on the first
        LLM call and reused for every subsequent asset — cutting API calls from
        N×(index + terms) down to 1×(index + terms).

        max_concurrent controls the number of simultaneous LLM calls to avoid
        rate-limit errors.

        context_builder_override: optional callable(AssetRecord) -> EnrichmentContext.
        If provided, replaces the default build_context() call. Use
        build_context_from_catalog() for assets sourced from Postgres.
        """
        context_fn = context_builder_override or build_context
        lookup = self._build_lookup()
        sem = asyncio.Semaphore(max_concurrent)

        async def _enrich_one(asset: AssetRecord) -> AssetLinkResult:
            async with sem:
                try:
                    ctx = context_fn(asset)
                    column_context = self._build_column_context(asset, ctx)
                    result_dict = await lookup.get_business_metadata_with_context(
                        asset.name, column_context, use_cache=True
                    )
                    if result_dict is None:
                        return self._no_match_result(asset, ctx)
                    return self._build_result_from_lookup(asset, ctx, result_dict)
                except Exception as e:
                    logger.error(f"Enrichment failed for asset {asset.asset_id}: {e}")
                    return self._error_result(asset, str(e))

        return list(await asyncio.gather(*[_enrich_one(a) for a in assets]))

    def _build_result_from_lookup(
        self,
        asset: AssetRecord,
        ctx: EnrichmentContext,
        result_dict: dict,
    ) -> AssetLinkResult:
        linkage_type = result_dict.get('linkage_type', 'no_match')
        confidence = int(result_dict.get('confidence_score', 0))
        term_title = result_dict.get('term_title')
        term_description = result_dict.get('term_description', '')
        enriched_description = result_dict.get('enriched_description', '')

        action = _LINKAGE_TO_ACTION.get(linkage_type, EventAction.NO_MATCH)
        classification = _CLASSIFICATION_MAP.get(
            ctx.suggested_classification, MetricClassification.UNCLASSIFIED
        )

        purpose = self._build_purpose_statement(ctx) if ctx.pages_used_on else None

        # business_definition: enriched context-aware version when available, raw glossary text as fallback
        business_def = enriched_description or term_description or None
        description_enriched = bool(enriched_description and enriched_description != term_description)

        result = AssetLinkResult(
            asset_id=asset.asset_id,
            asset_type=asset.asset_type,
            asset_name=asset.name,
            term_title=term_title,
            term_id=result_dict.get('term_id'),
            confidence_score=confidence,
            linkage_type=linkage_type,
            matching_rationale=result_dict.get('matching_rationale', ''),
            business_name=term_title or asset.name,
            business_definition=business_def,
            description_enriched=description_enriched,
            purpose_statement=purpose,
            metric_classification=classification,
            tier3_recommendations=result_dict.get('tier3_recommendations'),
            enriched_at=datetime.now(timezone.utc).isoformat(),
            model_id=asset.context.model_id or None,
        )

        write_event(
            asset_id=asset.asset_id,
            stage=f'{linkage_type}_match',
            actor='AssetMatcherService',
            action=action,
            confidence=confidence,
            before_state='extracted',
            after_state='enriched',
            payload={
                'term_title': term_title,
                'business_name': result.business_name,
                'classification': result.metric_classification,
            },
            rationale=result_dict.get('matching_rationale', ''),
        )

        return result

    def _build_purpose_statement(self, ctx: EnrichmentContext) -> Optional[str]:
        pages = ctx.pages_used_on[:3]
        visual_types = list(set(ctx.visual_types_used_in[:3])) if ctx.visual_types_used_in else []
        stmt = f"Used on {', '.join(pages)} page(s)"
        if visual_types:
            stmt += f" in {', '.join(visual_types)} visuals"
        if ctx.domain:
            stmt += f" within the {ctx.domain} domain"
        return stmt + "."

    def _no_match_result(self, asset: AssetRecord, ctx: EnrichmentContext) -> AssetLinkResult:
        write_event(
            asset_id=asset.asset_id,
            stage='enrichment',
            actor='AssetMatcherService',
            action=EventAction.NO_MATCH,
            confidence=0,
            before_state='extracted',
            after_state='extracted',
            rationale='No Alation match found across all tiers',
        )
        return AssetLinkResult(
            asset_id=asset.asset_id,
            asset_type=asset.asset_type,
            asset_name=asset.name,
            confidence_score=0,
            linkage_type='no_match',
            matching_rationale='No match found in Alation glossary',
            metric_classification=MetricClassification.UNCLASSIFIED,
        )

    def _error_result(self, asset: AssetRecord, error: str) -> AssetLinkResult:
        return AssetLinkResult(
            asset_id=asset.asset_id,
            asset_type=asset.asset_type,
            asset_name=asset.name,
            confidence_score=0,
            linkage_type='error',
            matching_rationale=f'Enrichment error: {error}',
            metric_classification=MetricClassification.UNCLASSIFIED,
        )
