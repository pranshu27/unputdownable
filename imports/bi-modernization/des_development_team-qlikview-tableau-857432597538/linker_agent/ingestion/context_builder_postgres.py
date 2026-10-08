"""
Extends context_builder.py for assets sourced from the rationalized catalog.
Adds rationalization context (verdict, overlap group, top matches) to the
LLM prompt so the enrichment agent understands the asset's governance status.

Call build_context_from_catalog() instead of build_context() when the asset
originated from the Postgres kpi_rationalized_catalog table.
"""

from linker_agent.ingestion.context_builder import EnrichmentContext, build_context
from linker_agent.models.asset_record import AssetRecord


def build_context_from_catalog(asset: AssetRecord) -> EnrichmentContext:
    """
    Build enrichment context for a catalog-sourced asset.
    Delegates to the base build_context() then appends rationalization
    context to technical_description and enrichment_hint.
    """
    ctx = build_context(asset)
    attrs = asset.attributes

    verdict = attrs.get("ai_verdict_refined") or attrs.get("ai_verdict") or "Unknown"
    rationale = attrs.get("rationale_refined") or ""
    overlap_id = attrs.get("overlap_group_id")
    top3: list[dict] = attrs.get("top3_matches_parsed") or []
    is_overlap = attrs.get("is_overlap", False)
    similarity = attrs.get("similarity_score")

    rationalization_context = f"\n\nRationalization verdict: {verdict}."
    if rationale:
        rationalization_context += f" Rationale: {rationale}"
    if overlap_id is not None:
        rationalization_context += f" Overlap group: {overlap_id}."
    if similarity is not None:
        rationalization_context += f" Similarity to top match: {similarity:.2f}."
    if top3:
        matches_str = " | ".join(
            f"{m['name']} ({m['tool']}, score={m['score']})" for m in top3[:3]
        )
        rationalization_context += f" Top similar assets: {matches_str}."

    ctx.technical_description += rationalization_context

    if is_overlap and overlap_id is not None:
        ctx.enrichment_hint += (
            f" Note: this asset belongs to overlap group {overlap_id} with "
            f"{len(top3)} similar assets — the business definition should "
            f"clearly differentiate it from semantically similar assets."
        )

    return ctx
