"""
Builds enrichment context for the LLM based on asset type.
This is the single place where per-asset-type logic concentrates.
Adding a new tool or asset type = one new branch here, nothing else changes.
"""

from dataclasses import dataclass, field
from linker_agent.models.asset_record import AssetRecord, AssetType


@dataclass
class EnrichmentContext:
    """
    Structured context passed to the Tier 2 / Tier 3 LLM prompt.
    Replaces the raw (column_name, data_type, table) tuple.
    """
    asset_id: str
    asset_name: str
    asset_type: str
    technical_description: str         # what we already know technically
    business_context: str              # dashboard/report context
    usage_context: str                 # where it appears in visuals
    enrichment_hint: str               # type-specific prompt guidance
    suggested_classification: str      # pre-classification hint for LLM
    pages_used_on: list = field(default_factory=list)
    visual_types_used_in: list = field(default_factory=list)
    domain: str = ""


def build_context(asset: AssetRecord) -> EnrichmentContext:
    """
    Build an EnrichmentContext for any AssetRecord.
    Each asset type assembles different fields into the context fields.
    """
    ctx = asset.context
    attrs = asset.attributes

    base_business_context = (
        f"Dashboard: {ctx.model_name}. "
        f"Source tool: {ctx.source_tool}. "
        + (f"Domain: {ctx.domain}. " if ctx.domain else "")
    )

    if ctx.pages_used_on:
        pages_str = ", ".join(ctx.pages_used_on[:4])
        visual_str = (
            ", ".join(set(ctx.visual_types_used_in[:4]))
            if ctx.visual_types_used_in else "various visuals"
        )
        base_usage_context = (
            f"Appears on {len(ctx.pages_used_on)} report page(s): {pages_str}. "
            f"Used in {visual_str} visuals."
        )
    else:
        base_usage_context = "Usage across report pages not available."

    # ---- CALCULATION / KPI ----
    if asset.asset_type in (AssetType.CALCULATION, AssetType.KPI):
        expressions = attrs.get('expressions', {})
        primary_expr = (
            expressions.get('dax')
            or expressions.get('tableau')
            or expressions.get('qlik')
            or 'expression not available'
        )
        depends_cols = ctx.depends_on_columns
        depends_measures = ctx.depends_on_measures

        technical_description = (
            f"Calculation '{asset.name}'. "
            f"Semantic type: {attrs.get('semantic_type', 'unknown')}. "
            f"Aggregation behavior: {attrs.get('aggregation_behavior', 'unknown')} "
            f"(non_additive means this is a ratio/CAGR — must not be naively summed). "
            f"Data type: {attrs.get('data_type', 'unknown')}. "
            f"Format: {attrs.get('format_string', 'none')}. "
            + (f"Depends on columns: {', '.join(depends_cols)}. " if depends_cols else "")
            + (f"Depends on measures: {', '.join(depends_measures)}. " if depends_measures else "")
            + (f"Tags: {', '.join(attrs.get('tags', []))}. " if attrs.get('tags') else "")
            + f"\nExpression: {str(primary_expr)[:500]}"
        )

        enrichment_hint = (
            "Generate a concise business name (3-5 words, title case), "
            "a plain-English definition (1-2 sentences) explaining what this metric measures "
            "and what business question it answers, "
            "and classify it as one of: kpi, measure, ratio, calculated, dimension, identifier."
        )

        suggested_classification = (
            'ratio' if attrs.get('aggregation_behavior') == 'non_additive'
            else 'kpi' if attrs.get('semantic_type') == 'growth_rate'
            else 'measure'
        )

    # ---- COLUMN / DIMENSION / MEASURE ----
    elif asset.asset_type in (AssetType.COLUMN, AssetType.DIMENSION, AssetType.MEASURE):
        table_name = attrs.get('table_name', ctx.table_name or 'unknown table')
        table_type = attrs.get('table_type', ctx.table_type or '')
        semantic_role = attrs.get('semantic_role', 'unknown')
        used_in = []
        if attrs.get('used_in_filters'):
            used_in.append('filters')
        if attrs.get('used_in_groupby'):
            used_in.append('group-by')
        if attrs.get('used_in_calculations'):
            used_in.append('calculations')
        if attrs.get('used_in_relationships'):
            used_in.append('relationships')

        technical_description = (
            f"Column '{asset.name}' in {table_type} table '{table_name}'. "
            f"Data type: {attrs.get('data_type', 'unknown')}. "
            f"Semantic role: {semantic_role}. "
            + (f"Used in: {', '.join(used_in)}. " if used_in else "")
            + (f"Existing description: {asset.description}. " if asset.description else "No existing description. ")
        )

        enrichment_hint = (
            "Generate a concise business name (title case, plain words), "
            "a plain-English definition (1 sentence) describing what this field contains "
            "and how it is used in business analysis, "
            "and classify it as one of: kpi, measure, dimension, identifier, date."
        )

        suggested_classification = {
            'primary_key': 'identifier',
            'foreign_key': 'identifier',
            'dimension': 'dimension',
            'measure': 'measure',
            'date': 'dimension',
        }.get(semantic_role, 'dimension')

    # ---- TABLE ----
    elif asset.asset_type == AssetType.TABLE:
        table_type = attrs.get('table_type', 'unknown')
        col_count = attrs.get('column_count', 0)

        technical_description = (
            f"Table '{asset.name}'. "
            f"Type: {table_type} ({col_count} columns). "
            + (f"Description: {asset.description}. " if asset.description else "")
        )

        enrichment_hint = (
            "Generate a concise business name and a plain-English definition "
            "describing what business entity this table represents and how it is used."
        )

        suggested_classification = (
            'dimension' if table_type in ('dimension', 'lookup') else 'measure'
        )

    # ---- FALLBACK ----
    else:
        technical_description = f"Asset '{asset.name}' of type {asset.asset_type}."
        enrichment_hint = "Generate a business name and definition for this data asset."
        suggested_classification = 'unclassified'

    return EnrichmentContext(
        asset_id=asset.asset_id,
        asset_name=asset.name,
        asset_type=str(asset.asset_type),
        technical_description=technical_description,
        business_context=base_business_context,
        usage_context=base_usage_context,
        enrichment_hint=enrichment_hint,
        suggested_classification=suggested_classification,
        pages_used_on=ctx.pages_used_on,
        visual_types_used_in=ctx.visual_types_used_in,
        domain=ctx.domain or "",
    )
