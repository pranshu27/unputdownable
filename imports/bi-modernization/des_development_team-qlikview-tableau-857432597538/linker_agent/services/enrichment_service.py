"""Bulk glossary enrichment service — process any N terms in one call."""

import logging
import time
from typing import Any, Dict, List, Optional

from linker_agent.clients.alation_client import SwaggerAPIClient
from linker_agent.core.tier2_semantic_matcher import execute_tier2_linking, execute_tier3_suggestions
from linker_agent.models.term_column_link import TermColumnLink
from linker_agent.utils.html_cleaner import clean_html_description

logger = logging.getLogger(__name__)


class EnrichmentService:
    """Run the full 3-tier matching pipeline on every term in a glossary.

    Tier 1 — direct links already configured in Alation (100% confidence, instant).
    Tier 2 — LLM semantic matching for unlinked terms, run concurrently.
    Unmatched — terms where no match clears the confidence threshold.

    The service returns a complete, per-term report together with aggregate stats.
    It never modifies Alation; it only reads and matches.
    """

    def __init__(self, client: SwaggerAPIClient):
        self._client = client

    async def run(
        self,
        glossary_id: int = 2,
        confidence_threshold: int = 60,
        max_concurrent: int = 5,
    ) -> Dict[str, Any]:
        """Process all N terms in the specified glossary.

        Args:
            glossary_id: Alation glossary ID to enrich.
            confidence_threshold: Minimum LLM confidence to accept a Tier 2 match.
            max_concurrent: Number of simultaneous LLM calls (controls speed vs.
                rate-limit risk). Safe default is 5.

        Returns:
            {summary, tier1_results, tier2_results, unmatched_results, all_results}
        """
        t0 = time.time()
        logger.info(
            f"Starting bulk enrichment: glossary_id={glossary_id}, "
            f"confidence_threshold={confidence_threshold}, max_concurrent={max_concurrent}"
        )

        # ── Step 1: Pull complete glossary snapshot from Alation ─────────────
        glossary_data = await self._client.get_complete_glossary_with_technical_details(
            glossary_id=glossary_id,
            fetch_all_columns=True,
        )

        terms: List[Dict] = glossary_data.get("terms", [])
        linked_entries: List[Dict] = glossary_data.get("linked_terms", [])
        unlinked_raw: List[Dict] = glossary_data.get("unlinked_terms", [])

        logger.info(
            f"Glossary snapshot: {len(terms)} total terms, "
            f"{len(linked_entries)} with Data Asset links, "
            f"{len(unlinked_raw)} without"
        )

        # ── Step 2: Build Tier 1 results from pre-configured Data Asset links ─
        tier1_results: List[Dict] = []
        tier1_links: List[TermColumnLink] = []

        for entry in linked_entries:
            term = entry["term"]
            col = entry.get("column") or {}
            table = entry.get("table") or {}

            tier1_results.append({
                "term_id": term["id"],
                "term_title": term.get("title", ""),
                "term_description": clean_html_description(term.get("description") or ""),
                "linkage_type": "direct",
                "confidence_score": 100.0,
                "column_id": col.get("id"),
                "column_name": col.get("name"),
                "table_id": table.get("id"),
                "table_name": table.get("name"),
                "matching_rationale": "Pre-configured Data Asset link in Alation",
            })

            # Build TermColumnLink objects so execute_tier2_linking can identify
            # which terms are already linked and skip them.
            if col.get("id") and col.get("id", 0) > 0 and table.get("id", 0) > 0:
                try:
                    tier1_links.append(
                        TermColumnLink(
                            term_id=term["id"],
                            term_title=term.get("title", ""),
                            term_description=clean_html_description(
                                term.get("description") or ""
                            ),
                            column_id=col["id"],
                            column_name=col.get("name", ""),
                            table_name=table.get("name", "Unknown"),
                            table_id=table["id"],
                            confidence_score=100.0,
                            linkage_type="direct",
                            matching_rationale="Pre-configured Data Asset link",
                        )
                    )
                except Exception:
                    pass  # validation edge-case; Tier 1 result still recorded above

        # ── Step 3: Run Tier 2 concurrently on all unlinked terms ─────────────
        tier2_results: List[Dict] = []
        tier2_term_ids: set = set()

        if unlinked_raw and glossary_data.get("columns"):
            logger.info(f"Running Tier 2 on {len(unlinked_raw)} unlinked terms...")
            tier2_links = await execute_tier2_linking(
                glossary_data=glossary_data,
                tier1_links=tier1_links,
                confidence_threshold=confidence_threshold,
                llm_rate_limit=100,
                max_concurrent=max_concurrent,
            )

            for link in tier2_links:
                tier2_term_ids.add(link.term_id)
                tier2_results.append({
                    "term_id": link.term_id,
                    "term_title": link.term_title,
                    "term_description": link.term_description,
                    "linkage_type": "semantic",
                    "confidence_score": link.confidence_score,
                    "column_id": link.column_id,
                    "column_name": link.column_name,
                    "table_id": link.table_id,
                    "table_name": link.table_name,
                    "matching_rationale": link.matching_rationale,
                })
        elif unlinked_raw:
            logger.warning("No columns available — Tier 2 skipped.")

        # ── Step 4: Collect terms not matched by Tier 1 or Tier 2 ───────────
        linked_tier1_ids = {e["term"]["id"] for e in linked_entries}
        tier2_unmatched_raw = [
            t for t in unlinked_raw if t.get("id") not in tier2_term_ids
        ]

        # ── Step 4.5: Tier 3 — suggest column specs for unmatched terms ──────
        tier3_results: List[Dict] = []
        tier3_term_ids: set = set()

        if tier2_unmatched_raw:
            logger.info(f"Running Tier 3 on {len(tier2_unmatched_raw)} unmatched terms...")
            tier3_suggestions = await execute_tier3_suggestions(
                unmatched_terms=tier2_unmatched_raw,
                max_concurrent=max_concurrent,
            )
            for t in tier2_unmatched_raw:
                tid = t.get("id")
                suggestion = tier3_suggestions.get(tid)
                if suggestion:
                    tier3_term_ids.add(tid)
                    tier3_results.append({
                        "term_id": tid,
                        "term_title": t.get("title", ""),
                        "term_description": clean_html_description(t.get("description") or ""),
                        "linkage_type": "suggested",
                        "confidence_score": float(suggestion.get("confidence", 0)),
                        "column_id": None,
                        "column_name": suggestion.get("suggested_column_name"),
                        "table_id": None,
                        "table_name": suggestion.get("suggested_table_pattern"),
                        "suggested_data_type": suggestion.get("suggested_data_type"),
                        "matching_rationale": suggestion.get("rationale", ""),
                        "generated": True,
                    })

        # ── Step 5: Collect terms with no match at any tier ───────────────────
        unmatched_results: List[Dict] = [
            {
                "term_id": t["id"],
                "term_title": t.get("title", ""),
                "term_description": clean_html_description(t.get("description") or ""),
                "linkage_type": "unmatched",
                "confidence_score": 0.0,
                "column_id": None,
                "column_name": None,
                "table_id": None,
                "table_name": None,
                "matching_rationale": "No match or suggestion found above confidence threshold",
            }
            for t in tier2_unmatched_raw
            if t.get("id") not in tier3_term_ids
        ]

        # ── Step 6: Build summary ─────────────────────────────────────────────
        matched_count = len(tier1_results) + len(tier2_results)
        all_results = tier1_results + tier2_results + tier3_results + unmatched_results

        matched_confidences = [
            r["confidence_score"]
            for r in all_results
            if r["confidence_score"] > 0
        ]

        elapsed = round(time.time() - t0, 2)
        summary: Dict[str, Any] = {
            "glossary_id": glossary_id,
            "confidence_threshold": confidence_threshold,
            "max_concurrent": max_concurrent,
            "total_terms": len(terms),
            "tier1_count": len(tier1_results),
            "tier2_count": len(tier2_results),
            "tier3_count": len(tier3_results),
            "unmatched_count": len(unmatched_results),
            "matched_count": matched_count,
            "suggested_count": len(tier3_results),
            "match_rate_pct": round(matched_count / len(terms) * 100, 1) if terms else 0.0,
            "avg_confidence": (
                round(sum(matched_confidences) / len(matched_confidences), 2)
                if matched_confidences else 0.0
            ),
            "processing_time_seconds": elapsed,
        }

        logger.info(
            f"Enrichment complete: {matched_count}/{len(terms)} matched, "
            f"{len(tier3_results)} Tier 3 suggestions, "
            f"{len(unmatched_results)} truly unmatched "
            f"({summary['match_rate_pct']}% match rate) in {elapsed}s"
        )

        return {
            "summary": summary,
            "tier1_results": tier1_results,
            "tier2_results": tier2_results,
            "tier3_results": tier3_results,
            "unmatched_results": unmatched_results,
            "all_results": all_results,
        }
