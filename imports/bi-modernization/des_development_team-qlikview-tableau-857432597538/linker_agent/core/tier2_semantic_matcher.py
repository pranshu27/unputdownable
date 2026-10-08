"""
Tier 2 Semantic Matching: Use LLM to match unlinked business terms to columns

This module handles Tier 2 linking where business terms WITHOUT Data Asset links
are semantically matched to technical columns using Azure OpenAI LLM.

These links have variable confidence (60-100%) based on semantic similarity.
"""

import re
from typing import List, Dict, Any, Optional
import sys
from pathlib import Path
import json
import asyncio

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from linker_agent.models.term_column_link import TermColumnLink
from linker_agent.utils.logger import configure_logger
from linker_agent.utils.llm_factory import get_azure_chat_client
from linker_agent.utils.html_cleaner import clean_html_description
from linker_agent.core.kpi_linkage_engine import AdaptiveRateLimiter, parse_json, safe_llm_call
from linker_agent.clients.alation_client import SwaggerAPIClient

logger = configure_logger(__file__)


def prepare_llm_prompt(
    term: Dict[str, Any],
    column_candidates: List[Dict[str, Any]]
) -> str:
    """
    Prepare LLM prompt for semantic term-to-column matching.
    
    Args:
        term: Business term with title and description
        column_candidates: List of candidate columns with names, descriptions, types
        
    Returns:
        Formatted prompt string for LLM
    """
    term_title = term.get("title", "")
    term_description = clean_html_description(term.get("description", ""))
    
    # Format column candidates for prompt
    columns_json = json.dumps(column_candidates, indent=2)
    
    prompt = f"""You are a data catalog expert specializing in business glossary to technical column mapping.

**TASK**: Match the business term to the most semantically appropriate database column.

**BUSINESS TERM**:
- Title: {term_title}
- Description: {term_description}

**AVAILABLE COLUMNS**:
{columns_json}

**MATCHING RULES**:
1. Match based on SEMANTIC MEANING, not just name similarity
2. Consider the business context in the term description
3. Consider data types (e.g., "Date" terms should match date/timestamp columns)
4. Confidence score 0-100 based on match quality:
   - 90-100: Exact semantic match (term and column describe the same concept)
   - 75-89: Strong semantic match (closely related concepts)
   - 60-74: Moderate semantic match (related but not identical)
   - <60: Weak match (do not return)
5. If no good match exists (confidence < 60), return {{"matched": false}}

**EXAMPLES OF GOOD MATCHING**:
- "Conversion Flag" → "conversion_indicator" (confidence: 95, rationale: "Both refer to conversion status")
- "Device Type" → "device_type_code" (confidence: 90, rationale: "Direct match for device classification")
- "Transaction Date" → "transaction_timestamp" (confidence: 85, rationale: "Both capture transaction timing")
- "Discount Amount" → "discount_value" or "discount_amt" (confidence: 90, rationale: "Both represent discount monetary value")

**OUTPUT FORMAT** (JSON only, no markdown):
{{
  "column_id": 4744,
  "column_name": "transaction_date",
  "table_name": "Sales Transactions",
  "table_id": 123,
  "confidence": 90,
  "rationale": "Business term 'Transaction Date' semantically matches column 'transaction_date' which stores the exact date of transactions"
}}

If no good match (confidence < 60), return: {{"matched": false}}

Return ONLY the JSON object. No explanations, no markdown formatting."""

    return prompt


def _preselect_candidates(
    term: Dict[str, Any],
    columns: List[Dict[str, Any]],
    tables_by_id: Dict[int, Dict[str, Any]],
    top_k: int = 50,
) -> List[Dict[str, Any]]:
    """Score every column by keyword relevance to the term and return the top_k.

    This replaces the naive ``columns[:50]`` slice so the LLM always sees the
    most semantically plausible candidates rather than whichever columns happen
    to appear first in the API response.

    Scoring (additive):
    - +3 per exact word overlap between term title/description words and column
      name words
    - +2 per term word found as a substring inside the raw column name (catches
      abbreviations like "pol_eff_dt" matching "effective date")
    - +1 per term word that overlaps with the table name
    """
    term_text = (
        (term.get("title") or "") + " " +
        clean_html_description(term.get("description") or "")
    ).lower()
    term_words = {w for w in re.sub(r"[^a-z0-9]", " ", term_text).split() if len(w) > 1}

    if not term_words:
        return columns[:top_k]

    scored: List[tuple] = []
    for col in columns:
        raw_name = (col.get("name") or "").lower()
        col_words = set(re.sub(r"[_\-]", " ", raw_name).split())

        overlap = len(term_words & col_words)
        substring = sum(1 for w in term_words if len(w) > 2 and w in raw_name)

        table = tables_by_id.get(col.get("table_id"), {})
        table_words = set(re.sub(r"[^a-z0-9]", " ", (table.get("name") or "").lower()).split())
        table_overlap = len(term_words & table_words)

        scored.append((overlap * 3 + substring * 2 + table_overlap, col))

    scored.sort(key=lambda x: -x[0])
    return [col for _, col in scored[:top_k]]


async def semantic_match_term_to_column(
    term: Dict[str, Any],
    columns: List[Dict[str, Any]],
    tables_by_id: Dict[int, Dict[str, Any]],
    llm_client,
    rate_limiter: AdaptiveRateLimiter
) -> Optional[Dict[str, Any]]:
    """
    Use LLM to semantically match a business term to a column.
    
    Args:
        term: Business term object
        columns: List of all available columns
        tables_by_id: Dictionary mapping table_id -> table object
        llm_client: Azure OpenAI client
        rate_limiter: Rate limiter for LLM calls
        
    Returns:
        Match dictionary with column_id, column_name, table_name, table_id, confidence, rationale
        or None if no match found
    """
    term_title = term.get("title", "Unknown")
    
    # Pre-select top-50 candidates by keyword relevance, not arbitrary ordering
    top_columns = _preselect_candidates(term, columns, tables_by_id, top_k=50)
    column_candidates = []
    for col in top_columns:
        table_id = col.get("table_id")
        table = tables_by_id.get(table_id, {})

        column_candidates.append({
            "column_id": col.get("id"),
            "column_name": col.get("name", ""),
            "column_type": col.get("column_type", "unknown"),
            "column_description": col.get("description", "")[:200],
            "table_name": table.get("name", "Unknown"),
            "table_id": table_id,
        })
    
    if not column_candidates:
        logger.warning(f"No column candidates available for term '{term_title}'")
        return None
    
    # Generate prompt
    prompt = prepare_llm_prompt(term, column_candidates)
    
    # Create LLM agent
    agent = llm_client.create_agent(
        name="term_column_matcher",
        instructions="You are a precise data mapping expert. Output only valid JSON."
    )
    
    # Call LLM with rate limiting and retries
    logger.debug(f"Calling LLM for term '{term_title}'...")
    response = await safe_llm_call(
        lambda p: agent.run(p),
        prompt,
        rate_limiter,
        f"SemanticMatch-{term_title}",
        retries=3
    )
    
    if not response:
        logger.warning(f"LLM call failed for term '{term_title}'")
        return None
    
    # Parse JSON response
    logger.debug(f"LLM response for '{term_title}': {response[:200]}...")
    result = parse_json(response)
    
    if not result:
        logger.warning(f"Failed to parse LLM response for term '{term_title}'")
        return None
    
    # Check if match was found
    if result.get("matched") == False:
        logger.info(f"No good match found for term '{term_title}' (confidence < 60)")
        return None
    
    # Validate required fields
    required_fields = ["column_id", "column_name", "table_name", "table_id", "confidence", "rationale"]
    if not all(field in result for field in required_fields):
        logger.warning(f"LLM response missing required fields for term '{term_title}'")
        return None
    
    logger.info(f"✓ Matched '{term_title}' → '{result['column_name']}' (confidence: {result['confidence']}%)")
    return result


async def execute_tier2_linking(
    glossary_data: Dict[str, Any],
    tier1_links: List[TermColumnLink],
    confidence_threshold: int = 60,
    llm_rate_limit: int = 100,
    max_concurrent: int = 5,
) -> List[TermColumnLink]:
    """Execute Tier 2 semantic linking using LLM — runs all terms concurrently.

    Process:
    1. Identify unlinked terms (not in tier1_links)
    2. For each unlinked term, call the LLM concurrently (bounded by max_concurrent)
    3. Create a TermColumnLink for every result above confidence_threshold

    Args:
        glossary_data: Dict with terms, columns, tables_by_id, etc.
        tier1_links: Already-linked terms (used to derive which are unlinked).
        confidence_threshold: Minimum confidence to accept a match (default: 60).
        llm_rate_limit: LLM calls per minute for the rate limiter (default: 100).
        max_concurrent: Maximum simultaneous LLM calls (default: 5).

    Returns:
        List of TermColumnLink objects for all semantic matches found.
    """
    logger.info("=" * 80)
    logger.info("TIER 2: SEMANTIC MATCHING")
    logger.info("=" * 80)
    
    terms = glossary_data.get("terms", [])
    columns = glossary_data.get("columns", [])
    tables_by_id = glossary_data.get("tables_by_id", {})
    
    # Step 1: Identify unlinked terms
    linked_term_ids = {link.term_id for link in tier1_links}
    unlinked_terms = [t for t in terms if t.get("id") not in linked_term_ids]
    
    logger.info(f"Found {len(unlinked_terms)} unlinked terms requiring semantic matching")
    
    if not unlinked_terms:
        logger.info("No unlinked terms. Tier 2 not needed.")
        return []
    
    if not columns:
        logger.warning("No columns available for Tier 2 matching")
        return []
    
    # Step 2: Initialize LLM client, rate limiter, and concurrency guard
    logger.info("Initializing LLM client...")
    llm_client = get_azure_chat_client()
    rate_limiter = AdaptiveRateLimiter(calls_per_minute=llm_rate_limit, burst_size=20)
    semaphore = asyncio.Semaphore(max_concurrent)

    # Step 3: Process all unlinked terms concurrently
    logger.info(
        f"Processing {len(unlinked_terms)} terms with LLM semantic matching "
        f"(max_concurrent={max_concurrent})..."
    )

    async def _process_term(term: Dict[str, Any]) -> Optional[TermColumnLink]:
        term_id = term.get("id")
        term_title = term.get("title", "Unknown")
        async with semaphore:
            try:
                match = await semantic_match_term_to_column(
                    term, columns, tables_by_id, llm_client, rate_limiter
                )
                if not match:
                    logger.debug(f"No match for term '{term_title}'")
                    return None
                confidence = float(match.get("confidence", 0))
                if confidence < confidence_threshold:
                    logger.debug(
                        f"Match for '{term_title}' below threshold: "
                        f"{confidence}% < {confidence_threshold}%"
                    )
                    return None
                link = TermColumnLink(
                    term_id=term_id,
                    term_title=term_title,
                    term_description=clean_html_description(term.get("description", "")),
                    column_id=match["column_id"],
                    column_name=match["column_name"],
                    table_name=match["table_name"],
                    table_id=match["table_id"],
                    confidence_score=confidence,
                    linkage_type="semantic",
                    matching_rationale=match["rationale"],
                )
                logger.debug(f"✓ Created Tier 2 link: {link}")
                return link
            except Exception as exc:
                logger.error(f"Failed to process term '{term_title}': {exc}")
                return None

    raw_results = await asyncio.gather(*[_process_term(t) for t in unlinked_terms])
    tier2_links = [r for r in raw_results if r is not None]
    
    # Step 4: Summary
    avg_confidence = (
        sum(link.confidence_score for link in tier2_links) / len(tier2_links)
        if tier2_links else 0.0
    )
    
    rate_health = rate_limiter.get_health()
    
    logger.info("=" * 80)
    logger.info(f"✓ TIER 2 COMPLETE: {len(tier2_links)} semantic links created")
    logger.info(f"  Avg Confidence: {avg_confidence:.1f}%")
    logger.info(f"  Coverage: {len(tier2_links)}/{len(unlinked_terms)} unlinked terms ({len(tier2_links)/len(unlinked_terms)*100:.1f}%)")
    logger.info(f"  LLM Calls: {rate_health['total_calls']} (success rate: {rate_health['success_rate']}%)")
    logger.info("=" * 80)
    
    return tier2_links


async def generate_tier3_column_suggestion(
    term: Dict[str, Any],
    llm_client,
    rate_limiter: AdaptiveRateLimiter,
) -> Optional[Dict[str, Any]]:
    """Tier 3 (term→column direction): suggest a column spec for an unmatched business term.

    When no existing column matches a glossary term, the LLM proposes what a fitting
    technical column would look like — giving data stewards actionable guidance on
    what to create or search for.

    Args:
        term: Business term dict with ``title`` and ``description`` keys.
        llm_client: Azure OpenAI client.
        rate_limiter: Shared rate limiter.

    Returns:
        Dict with suggested_column_name, suggested_data_type, suggested_table_pattern,
        confidence, and rationale — or None if the LLM cannot produce a confident suggestion.
    """
    term_title = term.get("title", "Unknown")
    term_description = clean_html_description(term.get("description") or "")

    prompt = f"""You are a data architect helping map business glossary terms to database columns.

**TASK**: A business glossary term could not be matched to any existing database column.
Suggest what a fitting technical column for this term would look like.

**BUSINESS TERM**:
- Title: {term_title}
- Description: {term_description}

**GUIDELINES**:
1. Suggest a snake_case column name a DBA would recognise (e.g. "customer_lifetime_value")
2. Suggest a SQL data type (e.g. DECIMAL(18,2), VARCHAR(50), DATE, BOOLEAN, BIGINT)
3. Suggest a table name pattern — the kind of table this column would live in
4. Rate your confidence 0-100:
   - 90-100: Crystal-clear technical spec follows directly from the term
   - 75-89: Good inference with minor ambiguity
   - 60-74: Reasonable guess with notable uncertainty
   - <60: Too ambiguous — return {{"matched": false}}

**OUTPUT FORMAT** (JSON only, no markdown):
{{
  "suggested_column_name": "customer_lifetime_value",
  "suggested_data_type": "DECIMAL(18,2)",
  "suggested_table_pattern": "customer_analytics or similar analytics/metrics table",
  "confidence": 88,
  "rationale": "Term clearly describes a monetary KPI computed per customer; DECIMAL precision suits currency values"
}}

If confidence < 60, return: {{"matched": false}}

Return ONLY the JSON object."""

    agent = llm_client.create_agent(
        name="column_spec_suggester",
        instructions="You are a precise data architect. Output only valid JSON.",
    )

    response = await safe_llm_call(
        lambda p: agent.run(p),
        prompt,
        rate_limiter,
        f"Tier3-{term_title}",
        retries=2,
    )

    if not response:
        logger.warning(f"Tier 3 LLM call failed for term '{term_title}'")
        return None

    result = parse_json(response)
    if not result or result.get("matched") is False:
        logger.info(f"Tier 3: no confident suggestion for term '{term_title}'")
        return None

    required = [
        "suggested_column_name",
        "suggested_data_type",
        "suggested_table_pattern",
        "confidence",
        "rationale",
    ]
    if not all(k in result for k in required):
        logger.warning(f"Tier 3 response missing fields for term '{term_title}'")
        return None

    logger.info(
        f"✓ Tier 3 suggestion for '{term_title}' → "
        f"'{result['suggested_column_name']}' (confidence: {result['confidence']}%)"
    )
    return result


async def execute_tier3_suggestions(
    unmatched_terms: List[Dict[str, Any]],
    max_concurrent: int = 5,
    llm_rate_limit: int = 100,
) -> Dict[int, Dict[str, Any]]:
    """Run Tier 3 concurrently on all unmatched terms.

    Args:
        unmatched_terms: Terms that had no Tier 1 or Tier 2 match.
        max_concurrent: Simultaneous LLM calls.
        llm_rate_limit: LLM calls per minute for the rate limiter.

    Returns:
        Mapping of term_id → suggestion dict for every term where the LLM
        produced a confident column specification. Terms the LLM could not
        handle confidently are omitted.
    """
    if not unmatched_terms:
        return {}

    logger.info("=" * 80)
    logger.info("TIER 3: COLUMN SUGGESTION FOR UNMATCHED TERMS")
    logger.info("=" * 80)
    logger.info(f"Processing {len(unmatched_terms)} unmatched terms...")

    llm_client = get_azure_chat_client()
    rate_limiter = AdaptiveRateLimiter(calls_per_minute=llm_rate_limit, burst_size=20)
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _process(term: Dict[str, Any]):
        term_id = term.get("id")
        async with semaphore:
            try:
                suggestion = await generate_tier3_column_suggestion(term, llm_client, rate_limiter)
                return term_id, suggestion
            except Exception as exc:
                logger.error(f"Tier 3 failed for term '{term.get('title')}': {exc}")
                return term_id, None

    raw = await asyncio.gather(*[_process(t) for t in unmatched_terms])
    suggestions = {tid: sug for tid, sug in raw if sug is not None}

    logger.info(f"✓ TIER 3 COMPLETE: {len(suggestions)}/{len(unmatched_terms)} suggestions generated")
    logger.info("=" * 80)

    return suggestions


def get_tier2_statistics(tier2_links: List[TermColumnLink]) -> Dict[str, Any]:
    """
    Calculate statistics for Tier 2 links.
    
    Args:
        tier2_links: List of Tier 2 TermColumnLink objects
        
    Returns:
        Dictionary with statistics
    """
    if not tier2_links:
        return {
            "count": 0,
            "avg_confidence": 0.0,
            "min_confidence": 0.0,
            "max_confidence": 0.0,
            "unique_columns": 0,
            "unique_tables": 0
        }
    
    confidences = [link.confidence_score for link in tier2_links]
    unique_columns = len(set(link.column_id for link in tier2_links))
    unique_tables = len(set(link.table_id for link in tier2_links if link.table_id > 0))
    
    return {
        "count": len(tier2_links),
        "avg_confidence": round(sum(confidences) / len(confidences), 2),
        "min_confidence": round(min(confidences), 2),
        "max_confidence": round(max(confidences), 2),
        "unique_columns": unique_columns,
        "unique_tables": unique_tables
    }


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

if __name__ == "__main__":
    """Example usage of Tier 2 linker"""
    import asyncio
    
    async def example():
        # Sample glossary data
        sample_glossary_data = {
            "terms": [
                {
                    "id": 10,
                    "title": "Customer Lifetime Value",
                    "description": "<p>Total revenue expected from a customer over their lifetime</p>",
                    "custom_fields": []  # No Data Asset link
                }
            ],
            "columns": [
                {
                    "id": 5432,
                    "name": "customer_ltv",
                    "column_type": "decimal",
                    "description": "Calculated lifetime value of customer",
                    "table_id": 456
                },
                {
                    "id": 5433,
                    "name": "customer_revenue",
                    "column_type": "decimal",
                    "description": "Total revenue from customer",
                    "table_id": 456
                }
            ],
            "tables": [
                {
                    "id": 456,
                    "name": "Customer Analytics",
                    "schema_name": "analytics"
                }
            ],
            "tables_by_id": {
                456: {
                    "id": 456,
                    "name": "Customer Analytics",
                    "schema_name": "analytics"
                }
            }
        }
        
        # Execute Tier 2 linking (no Tier 1 links)
        tier2_links = await execute_tier2_linking(
            sample_glossary_data,
            tier1_links=[],
            confidence_threshold=60
        )
        
        print(f"\nCreated {len(tier2_links)} Tier 2 links:")
        for link in tier2_links:
            print(f"  {link}")
        
        # Get statistics
        stats = get_tier2_statistics(tier2_links)
        print(f"\nStatistics:")
        print(f"  Count: {stats['count']}")
        print(f"  Avg Confidence: {stats['avg_confidence']}%")
        print(f"  Range: {stats['min_confidence']}% - {stats['max_confidence']}%")
    
    asyncio.run(example())
