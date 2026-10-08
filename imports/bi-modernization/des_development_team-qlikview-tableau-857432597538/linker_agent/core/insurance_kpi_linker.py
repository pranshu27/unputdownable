"""
Insurance KPI Linker

Enrichment adapter for insurance KPIs whose table.attribute mappings are
already known from CSV data. Calls LLM one-at-a-time to annotate each
attribute with description, data type, formula role, and confidence.

Uses the shared models and utilities from kpi_linkage_engine so there is a
single set of result types across both pipelines.
"""

from linker_agent.models.insurance_kpi import InsuranceKpi
from linker_agent.core.kpi_linkage_engine import (
    LinkedAttr,
    KPIDependency,
    LinkedKPI,
    LinkageResult,
    AdaptiveRateLimiter,
    safe_llm_call,
    parse_json,
)
from uuid import uuid5, NAMESPACE_OID
from typing import List, Dict, Optional
from datetime import datetime
from linker_agent.utils.logger import configure_logger
from linker_agent.utils.llm_factory import get_azure_chat_client
import json
import asyncio
from pathlib import Path


logger = configure_logger(__file__)

CACHE_DIR = Path("cache")
CACHE_FILE = CACHE_DIR / "insurance_kpis_linkage.json"


# ============================================================================
# CACHE
# ============================================================================

def _ensure_cache_directory():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _load_from_cache() -> Optional[LinkageResult]:
    if not CACHE_FILE.exists():
        return None
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache_data = json.load(f)
        result = LinkageResult(**cache_data)
        logger.info(f"Cache loaded: {len(result.linked_kpis)} KPIs from {result.summary.get('generation_timestamp')}")
        return result
    except Exception as e:
        logger.error(f"Error loading cache: {e}")
        return None


def _save_to_cache(result: LinkageResult):
    try:
        _ensure_cache_directory()
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(result.model_dump(mode="json"), f, indent=2, default=str, ensure_ascii=False)
        logger.info(f"Cache saved: {len(result.linked_kpis)} KPIs")
    except Exception as e:
        logger.error(f"Error saving cache: {e}")
        raise


def clear_cache():
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()
        logger.info("Cache cleared")
        return True
    return False


# ============================================================================
# ATTRIBUTE PARSING
# ============================================================================

def _parse_attributes(attributes: List[str]) -> List[Dict[str, str]]:
    """Parse 'table.attribute' strings into structured dicts."""
    parsed = []
    for attr_str in attributes:
        if not attr_str or not isinstance(attr_str, str):
            continue
        parts = attr_str.split(".", 1)
        if len(parts) == 2:
            table_name, attribute_name = parts[0].strip(), parts[1].strip()
            if table_name and attribute_name:
                parsed.append({"table_name": table_name, "attribute_name": attribute_name, "original": attr_str})
            else:
                logger.warning(f"Invalid attribute after parsing: {attr_str}")
        else:
            logger.warning(f"Could not parse attribute (no dot separator): {attr_str}")
    return parsed


# ============================================================================
# ATTRIBUTE ENRICHMENT
# ============================================================================

async def _enrich_single_attribute(
    kpi_name: str,
    kpi_definition: str,
    kpi_formula: str,
    table_name: str,
    attribute_name: str,
    agent,
    rate_limiter: AdaptiveRateLimiter,
) -> Optional[LinkedAttr]:
    """Enrich a single pre-mapped attribute via LLM. Returns None on low confidence."""
    prompt = f"""Analyze this insurance KPI attribute and provide metadata.

KPI: {kpi_name}
Definition: {kpi_definition}
Formula: {kpi_formula}

Attribute: {table_name}.{attribute_name}

Provide:
1. Description (max 50 chars): What this attribute represents
2. Data type: decimal, integer, string, date, boolean
3. Formula component: numerator, denominator, filter, date_range, identifier, segmentation, or supporting
4. Confidence score: 0-100
5. Rationale (max 15 words): Why relevant to this KPI

Respond with ONLY this JSON, no markdown:
{{
  "attribute_description": "...",
  "attribute_datatype": "...",
  "matched_kpi_component": "...",
  "confidence_score": 85,
  "matching_rationale": "..."
}}"""

    response_text = await safe_llm_call(
        lambda p: agent.run(p), prompt, rate_limiter, f"Enrich-{table_name}.{attribute_name}"
    )
    if not response_text:
        logger.warning(f"No LLM response for {table_name}.{attribute_name}")
        return None

    data = parse_json(response_text)
    if not data:
        logger.warning(f"Could not parse LLM response for {table_name}.{attribute_name}")
        return None

    try:
        confidence = float(data.get("confidence_score", 0))
        confidence = max(0.0, min(100.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.0

    if confidence < 60:
        logger.debug(f"Low confidence ({confidence}) for {table_name}.{attribute_name} — marking as missing")
        return None

    datatype = data.get("attribute_datatype", "string")
    if not isinstance(datatype, str) or len(datatype) > 50:
        datatype = "string"

    return LinkedAttr(
        table_name=table_name,
        table_id=uuid5(NAMESPACE_OID, table_name),
        attribute_name=attribute_name,
        attribute_description=data.get("attribute_description", "")[:200],
        attribute_datatype=datatype,
        confidence_score=confidence,
        matched_kpi_component=data.get("matched_kpi_component", "supporting"),
        matching_rationale=data.get("matching_rationale", "")[:200],
    )


async def _enrich_attribute_mappings(
    kpis: List[InsuranceKpi],
    agent,
    rate_limiter: AdaptiveRateLimiter,
) -> Dict[str, tuple]:
    """
    Enrich pre-mapped attributes for all KPIs one at a time.
    Returns dict: kpi_name → (List[LinkedAttr], List[str missing_originals])
    """
    logger.info(f"Enriching attributes for {len(kpis)} KPIs (one attribute at a time)...")

    results: Dict[str, tuple] = {}
    total_attributes = sum(len(_parse_attributes(kpi.attributes or [])) for kpi in kpis)
    processed = 0

    for kpi in kpis:
        parsed_attrs = _parse_attributes(kpi.attributes or [])
        if not parsed_attrs:
            logger.warning(f"KPI '{kpi.kpi}' has no valid parseable attributes")
            results[kpi.kpi] = ([], [])
            continue

        mapped: List[LinkedAttr] = []
        missing: List[str] = []

        logger.info(f"Processing KPI '{kpi.kpi}' ({len(parsed_attrs)} attributes)...")

        for attr in parsed_attrs:
            processed += 1
            logger.info(f"  [{processed}/{total_attributes}] Enriching {attr['table_name']}.{attr['attribute_name']}...")

            enriched = await _enrich_single_attribute(
                kpi_name=kpi.kpi,
                kpi_definition=kpi.business_definition,
                kpi_formula=kpi.technical_definition or f"Standard formula for {kpi.kpi}",
                table_name=attr["table_name"],
                attribute_name=attr["attribute_name"],
                agent=agent,
                rate_limiter=rate_limiter,
            )

            if enriched:
                mapped.append(enriched)
            else:
                missing.append(attr["original"])

        results[kpi.kpi] = (mapped, missing)
        logger.info(f"  ✓ '{kpi.kpi}': {len(mapped)} mapped, {len(missing)} missing")

    return results


# ============================================================================
# DEPENDENCY ANALYSIS
# ============================================================================

async def _analyze_single_kpi_dependency(
    kpi_name: str,
    kpi_formula: str,
    available_kpi_names: List[str],
    kpi_name_to_id: Dict[str, object],
    agent,
    rate_limiter: AdaptiveRateLimiter,
) -> List[KPIDependency]:
    prompt = f"""Analyze if this KPI formula references any other KPIs.

KPI: {kpi_name}
Formula: {kpi_formula}

Available KPIs that could be referenced:
{json.dumps(available_kpi_names, indent=2)}

If the formula mentions ANY of these KPI names, list them as dependencies.
If no dependencies, return empty array.

Respond with ONLY this JSON, no markdown:
{{
  "depends_on": [
    {{
      "dependent_kpi_name": "Loss Ratio",
      "dependency_type": "calculated_from",
      "required_for_component": "addend_1"
    }}
  ]
}}

If no dependencies: {{"depends_on": []}}"""

    response_text = await safe_llm_call(
        lambda p: agent.run(p), prompt, rate_limiter, f"Dep-{kpi_name}"
    )
    if not response_text:
        return []

    data = parse_json(response_text)
    if not data:
        return []

    dependencies = []
    for dep in data.get("depends_on", []):
        dep_name = dep.get("dependent_kpi_name")
        if not dep_name:
            continue
        dep_id = kpi_name_to_id.get(dep_name, uuid5(NAMESPACE_OID, dep_name))
        dependencies.append(KPIDependency(
            dependent_kpi_id=dep_id,
            dependent_kpi_name=dep_name,
            dependency_type=dep.get("dependency_type", "calculated_from"),
            required_for_component=dep.get("required_for_component", ""),
        ))
    return dependencies


async def _find_kpi_dependencies(
    kpis: List[InsuranceKpi],
    kpi_name_to_id: Dict[str, object],
    agent,
    rate_limiter: AdaptiveRateLimiter,
) -> Dict[str, List[KPIDependency]]:
    logger.info(f"Finding KPI dependencies for {len(kpis)} KPIs (one at a time)...")
    available_kpi_names = [kpi.kpi for kpi in kpis]
    dependency_map: Dict[str, List[KPIDependency]] = {}

    for idx, kpi in enumerate(kpis, 1):
        logger.info(f"  [{idx}/{len(kpis)}] Analyzing dependencies for '{kpi.kpi}'...")
        deps = await _analyze_single_kpi_dependency(
            kpi_name=kpi.kpi,
            kpi_formula=kpi.technical_definition,
            available_kpi_names=available_kpi_names,
            kpi_name_to_id=kpi_name_to_id,
            agent=agent,
            rate_limiter=rate_limiter,
        )
        dependency_map[kpi.kpi] = deps
        logger.info(f"    Found {len(deps)} dependencies" if deps else "    No dependencies")

    return dependency_map


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

async def generate_linkage_insurance_kpis(
    kpis: List[InsuranceKpi],
    use_cache: bool = True,
    force_refresh: bool = False,
) -> LinkageResult:
    """
    Enrich pre-mapped insurance KPI attributes and find inter-KPI dependencies.

    Step 1: For each KPI's known table.attribute pairs, call LLM to annotate
            with description, data type, formula role, and confidence.
    Step 2: Analyze each KPI formula for dependencies on other KPIs.

    Uses kpi_linkage_engine's shared models (LinkedAttr, LinkedKPI, LinkageResult)
    so results have the same structure as the generic engine output.
    """
    logger.info(f"Starting insurance KPI linkage for {len(kpis)} KPIs")

    if use_cache and not force_refresh:
        cached = _load_from_cache()
        if cached is not None:
            logger.info("Using cached result")
            return cached

    llm_client = get_azure_chat_client()
    rate_limiter = AdaptiveRateLimiter(calls_per_minute=60, burst_size=10)

    enrichment_agent = llm_client.create_agent(
        name="insurance_attribute_enricher",
        instructions="You are an expert insurance data analyst. Return ONLY valid JSON, no markdown.",
    )
    dependency_agent = llm_client.create_agent(
        name="insurance_dependency_analyzer",
        instructions="You are an expert insurance data analyst. Return ONLY valid JSON, no markdown.",
    )

    kpi_name_to_id = {kpi.kpi: uuid5(NAMESPACE_OID, kpi.kpi) for kpi in kpis}

    logger.info("=" * 80)
    logger.info("STEP 1: Enriching attribute mappings...")
    logger.info("=" * 80)
    enrichment_results = await _enrich_attribute_mappings(kpis, enrichment_agent, rate_limiter)

    logger.info("=" * 80)
    logger.info("STEP 2: Finding KPI dependencies...")
    logger.info("=" * 80)
    dependency_map = await _find_kpi_dependencies(kpis, kpi_name_to_id, dependency_agent, rate_limiter)

    logger.info("=" * 80)
    logger.info("Assembling results...")
    logger.info("=" * 80)
    linked_kpis: List[LinkedKPI] = []

    for kpi in kpis:
        mapped_attrs, missing_attrs = enrichment_results.get(kpi.kpi, ([], []))
        kpi_deps = dependency_map.get(kpi.kpi, [])

        missing_dep_names = [
            dep.dependent_kpi_name
            for dep in kpi_deps
            if dep.dependent_kpi_name not in kpi_name_to_id
        ]

        # A KPI is generatable only when all its attributes mapped AND no missing dependencies
        is_able_to_generate = len(missing_attrs) == 0 and len(missing_dep_names) == 0

        linked_kpis.append(LinkedKPI(
            kpi_id=kpi_name_to_id[kpi.kpi],
            kpi_name=kpi.kpi,
            kpi_definition=kpi.business_definition,
            kpi_formula=kpi.technical_definition,
            is_able_to_generate=is_able_to_generate,
            attribute_mappings=mapped_attrs,
            missing_attributes=missing_attrs,
            kpi_dependencies=kpi_deps,
            missing_kpi_dependencies=missing_dep_names,
            linkage_notes=f"Attributes: {len(mapped_attrs)} mapped, {len(missing_attrs)} missing",
        ))
        logger.info(f"Assembled '{kpi.kpi}': {len(mapped_attrs)} attrs, {len(kpi_deps)} deps, generatable={is_able_to_generate}")

    health = rate_limiter.get_health()
    summary = {
        "total_kpis": len(linked_kpis),
        "kpis_ready_to_generate": sum(1 for k in linked_kpis if k.is_able_to_generate),
        "total_attribute_mappings": sum(len(k.attribute_mappings) for k in linked_kpis),
        "total_missing_attributes": sum(len(k.missing_attributes) for k in linked_kpis),
        "total_dependencies": sum(len(k.kpi_dependencies) for k in linked_kpis),
        "api_calls_total": health["total_calls"],
        "api_success_rate": health["success_rate"],
        "generation_timestamp": datetime.utcnow().isoformat(),
        "processing_method": "one_at_a_time",
    }

    result = LinkageResult(linked_kpis=linked_kpis, summary=summary)

    if use_cache:
        _save_to_cache(result)

    return result


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

async def main():
    from linker_agent.models.insurance_kpi import load_insurance_kpis

    kpis = load_insurance_kpis()
    print(f"\n{'='*80}\nINSURANCE KPI LINKER\n{'='*80}")
    print(f"Loaded {len(kpis)} KPIs")

    result = await generate_linkage_insurance_kpis(kpis, use_cache=True, force_refresh=True)

    print(f"\n{'='*80}\nSUMMARY\n{'='*80}")
    for key, value in result.summary.items():
        print(f"{key}: {value}")

    return result


if __name__ == "__main__":
    asyncio.run(main())
