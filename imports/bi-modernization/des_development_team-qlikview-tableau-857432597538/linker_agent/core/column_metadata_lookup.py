"""
Column to Business Metadata Lookup

This module provides reverse lookup functionality: given technical column names,
retrieve their business metadata (business terms, descriptions, definitions).

Primary use case: Data analysts working with SQL queries want to understand
what columns mean in business terms.
"""

import re
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
import asyncio
from datetime import datetime, timedelta
import json

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from linker_agent.clients.alation_client import SwaggerAPIClient
from linker_agent.utils.logger import configure_logger
from linker_agent.utils.html_cleaner import clean_html_description

logger = configure_logger(__file__)


class ColumnMetadataLookup:
    """
    Main class for column → business metadata reverse lookup.
    
    Provides methods to:
    1. Build reverse index (column_name → business metadata)
    2. Cache the index for fast lookups
    3. Lookup business metadata for given column names
    """
    
    def __init__(
        self,
        swagger_client: SwaggerAPIClient,
        llm_client=None,
        confidence_threshold: int = 60,
        cache_hours: int = 24,
        glossary_id: int = 1,
        enrich_descriptions: bool = True
    ):
        """
        Initialize the column metadata lookup.
        
        Args:
            swagger_client: Configured SwaggerAPIClient instance
            llm_client: Azure OpenAI LLM client (optional, for Tier 2 and enrichment)
            confidence_threshold: Minimum confidence for Tier 2 links (default: 60)
            cache_hours: Cache expiration time in hours (default: 24)
            glossary_id: Alation glossary ID (default: 1)
            enrich_descriptions: Whether to enrich missing column descriptions with LLM (default: True)
        """
        self.swagger_client = swagger_client
        self.llm_client = llm_client
        self.confidence_threshold = confidence_threshold
        self.cache_hours = cache_hours
        self.glossary_id = glossary_id
        self.cache_file = "cache/column_to_business_metadata.json"
        self.enrich_descriptions = enrich_descriptions
        # In-memory caches — populated on first use, shared across all assets in a batch
        self._terms_cache: Optional[List] = None
        self._reverse_index_cache: Optional[Dict] = None
    
    def _extract_data_asset_links(self, term: Dict[str, Any]) -> List[int]:
        """
        Extract column IDs from Data Asset field in a business term.
        
        Args:
            term: Business term object with custom_fields
            
        Returns:
            List of column IDs (oids) linked via Data Asset field
        """
        column_ids = []
        custom_fields = term.get("custom_fields", [])
        
        for field in custom_fields:
            # Check for Data Asset field (field_id: 10018)
            if field.get("field_id") == 10018 or field.get("field_name") == "Data Asset":
                value = field.get("value", [])
                
                if isinstance(value, list):
                    for asset in value:
                        if isinstance(asset, dict) and asset.get("otype") == "attribute":
                            column_id = asset.get("oid")
                            if column_id:
                                column_ids.append(column_id)
        
        return column_ids
    
    async def _enrich_column_description(
        self,
        column_context: Dict[str, Any],
        max_retries: int = 2
    ) -> Optional[str]:
        """
        Use LLM to generate a description for a column that doesn't have one.
        
        Args:
            column_context: Full column context (name, type, table, schema, etc.)
            max_retries: Maximum number of retry attempts
            
        Returns:
            Generated description or None if generation fails
        """
        if not self.llm_client or not self.enrich_descriptions:
            return None
        
        # Check if column already has a description
        if column_context.get("description") and column_context.get("description").strip():
            return None  # Already has description, no enrichment needed
        
        # Build context for LLM
        column_info = f"**COLUMN NAME**: {column_context.get('name', 'Unknown')}\n"
        
        if column_context.get("title"):
            column_info += f"**COLUMN TITLE**: {column_context.get('title')}\n"
        if column_context.get("column_type"):
            column_info += f"**DATA TYPE**: {column_context.get('column_type')}\n"
        if column_context.get("nullable") is not None:
            column_info += f"**NULLABLE**: {column_context.get('nullable')}\n"
        
        # Index information
        index_info = column_context.get("index", {})
        if index_info:
            if index_info.get("isPrimaryKey"):
                column_info += f"**PRIMARY KEY**: Yes\n"
            if index_info.get("isForeignKey"):
                column_info += f"**FOREIGN KEY**: Yes\n"
        
        # Table context
        if column_context.get("table_name"):
            column_info += f"**TABLE NAME**: {column_context.get('table_name')}\n"
        if column_context.get("table_description"):
            column_info += f"**TABLE DESCRIPTION**: {clean_html_description(column_context.get('table_description', ''))}\n"
        
        # Schema context
        if column_context.get("schema_name"):
            column_info += f"**SCHEMA NAME**: {column_context.get('schema_name')}\n"
        
        # Design LLM prompt for description generation
        prompt = f"""You are a Data Catalog expert responsible for documenting database columns.

**TASK**: Generate a clear, concise description for this database column based on its context.

**COLUMN CONTEXT**:
{column_info}

**DESCRIPTION GUIDELINES**:

1. **Be Concise**: 1-2 sentences maximum
2. **Be Specific**: Describe what data this column stores
3. **Use Business Language**: Avoid overly technical jargon
4. **Consider Context**: Use table/schema names to infer purpose
5. **Consider Data Type**: 
   - Numeric types → likely measurements, counts, amounts
   - Boolean/flag types → likely indicators or status
   - Date types → likely temporal dimensions
   - Foreign keys → likely references to other entities
   - Primary keys → likely unique identifiers


Generate description:"""

        # Create agent
        agent = self.llm_client.create_agent(
            name="column_description_generator",
            instructions="You are a precise data documentation expert. Output only the description text."
        )
        
        # Retry logic
        for attempt in range(max_retries):
            try:
                logger.debug(f"LLM description generation attempt {attempt + 1}/{max_retries} for column '{column_context.get('name')}'")
                
                response = await agent.run(prompt)
                description = response.text if hasattr(response, 'text') else str(response)
                
                # Clean up the description
                description = description.strip()
                
                # Remove any markdown formatting
                if description.startswith("```"):
                    description = description.split("\n", 1)[1] if "\n" in description else description
                if description.endswith("```"):
                    description = description.rsplit("\n", 1)[0] if "\n" in description else description
                description = description.strip()
                
                # Validate description
                if description and len(description) > 10 and len(description) < 500:
                    logger.info(f"✓ Generated description for '{column_context.get('name')}': {description[:80]}...")
                    return description
                else:
                    logger.warning(f"Generated description too short or too long for '{column_context.get('name')}'")
                    continue
                
            except Exception as e:
                logger.error(f"LLM description generation failed for column '{column_context.get('name')}' (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)  # Brief pause before retry
                continue
        
        logger.error(f"All {max_retries} description generation attempts failed for column '{column_context.get('name')}'")
        return None
    
    async def _generate_new_business_term(
        self,
        column_context: Dict[str, Any],
        max_retries: int = 2,
        n_recommendations: int = 3,
    ) -> Optional[Dict]:
        """
        Generate NEW business term recommendations when no existing glossary term matches.

        Returns the top recommendation dict (highest confidence) when called from the
        3-tier pipeline, or None if the LLM declines.  The full list of recommendations
        is stored on the returned dict under key ``"recommendations"`` so callers can
        surface all options to a data steward.

        Args:
            column_context: Full column context (name, type, description, table, schema, etc.)
            max_retries: Maximum number of retry attempts
            
        Returns:
            Dictionary with generated business term:
            {
                "term_title": str,
                "term_description": str,
                "confidence": int (0-100),
                "rationale": str
            }
        """
        if not self.llm_client:
            return None
        
        # Build comprehensive context for LLM
        column_info = f"**COLUMN NAME**: {column_context.get('name', 'Unknown')}\n"
        
        if column_context.get("title"):
            column_info += f"**COLUMN TITLE**: {column_context.get('title')}\n"
        if column_context.get("description"):
            column_info += f"**COLUMN DESCRIPTION**: {clean_html_description(column_context.get('description', ''))}\n"
        if column_context.get("column_type"):
            column_info += f"**DATA TYPE**: {column_context.get('column_type')}\n"
        if column_context.get("nullable") is not None:
            column_info += f"**NULLABLE**: {column_context.get('nullable')}\n"
        
        # Index information
        index_info = column_context.get("index", {})
        if index_info:
            if index_info.get("isPrimaryKey"):
                column_info += f"**PRIMARY KEY**: Yes\n"
            if index_info.get("isForeignKey"):
                column_info += f"**FOREIGN KEY**: Yes\n"
        
        # Table context
        if column_context.get("table_name"):
            column_info += f"**TABLE NAME**: {column_context.get('table_name')}\n"
        if column_context.get("table_description"):
            column_info += f"**TABLE DESCRIPTION**: {clean_html_description(column_context.get('table_description', ''))}\n"
        if column_context.get("table_type"):
            column_info += f"**TABLE TYPE**: {column_context.get('table_type')}\n"
        
        # Schema context
        if column_context.get("schema_name"):
            column_info += f"**SCHEMA NAME**: {column_context.get('schema_name')}\n"
        if column_context.get("schema_description"):
            column_info += f"**SCHEMA DESCRIPTION**: {clean_html_description(column_context.get('schema_description', ''))}\n"
        
        # Design LLM prompt for business term generation
        prompt = f"""You are a Data Governance expert responsible for creating business glossary terms for technical BI columns and calculations.

**TASK**: Generate {n_recommendations} candidate business glossary terms for the column/calculation below, ranked from best fit to least fit. This asset does not match any existing term in the business glossary. Providing multiple options lets the data steward choose the most appropriate term.

**COLUMN / CALCULATION DETAILS**:
{column_info}

**GENERATION GUIDELINES** (apply to every candidate):

1. **term_title** — 2–6 words, title case, plain business language. No technical abbreviations.
   Examples: "Claim Identifier", "Loan Eligibility Indicator", "Premium Payable Percentage"

2. **term_description** — 2–3 sentences, written as a standalone business glossary entry.
   - What the data REPRESENTS in business terms (not how it's stored)
   - Why it matters to the business
   - How it is actually used in THIS specific dashboard/report — incorporate the dashboard name, table context, page usage, visual types, format, and aggregation behaviour from the COLUMN DETAILS above
   - Written in present tense; avoid technical terms like "varchar" or "bigint"
   - Do NOT say "this column" — write as a self-contained definition a data steward would publish to a catalog

3. **confidence** (integer 0–100):
   - 90–100 Very clear business meaning inferred from context
   - 75–89  Good understanding with minor inference
   - 60–74  Moderate understanding, some ambiguity
   - < 60   Business meaning unclear — omit this candidate

4. **rationale** — one sentence explaining why this name and definition fit.

**OUTPUT FORMAT** (JSON only — no markdown, no code fences, no extra text):
{{
  "recommendations": [
    {{
      "rank": 1,
      "term_title": "Claim Identifier",
      "term_description": "The unique reference number assigned to an insurance claim event. Links payment, adjudication, and settlement records to a single claim occurrence. Used in claims-frequency analysis and loss ratio calculations.",
      "confidence": 90,
      "rationale": "Column name and description both reference claim identification; insurance fact-table context confirms claims tracking purpose."
    }},
    {{
      "rank": 2,
      "term_title": "Insurance Claim Reference",
      "term_description": "A reference key that uniquely identifies an insurance claim within the policy management system. Used to trace claim history and link claim records to policy and customer data.",
      "confidence": 82,
      "rationale": "Alternative framing emphasising the reference/linking role rather than the primary key role."
    }},
    {{
      "rank": 3,
      "term_title": "Claim Case Number",
      "term_description": "The case number allocated to an insurance claim at the point of registration. Enables tracking of claim status, payments, and resolution across the claims lifecycle.",
      "confidence": 75,
      "rationale": "Case number framing is common in insurance operations and captures the lifecycle tracking intent."
    }}
  ]
}}

If the business meaning is genuinely unclear for ALL candidates (confidence would be < 60), return:
{{"generated": false, "rationale": "<one sentence explaining why>"}}

**IMPORTANT**: Return ONLY the JSON object. No markdown, no explanations outside the JSON.
Rank candidates from highest to lowest confidence. Omit any candidate with confidence < 60."""

        # Create agent
        agent = self.llm_client.create_agent(
            name="business_term_generator",
            instructions="You are a precise data governance expert. Output only valid JSON."
        )
        
        # Retry logic
        for attempt in range(max_retries):
            try:
                logger.debug(f"LLM business term generation attempt {attempt + 1}/{max_retries} for column '{column_context.get('name')}'")
                
                response = await agent.run(prompt)
                text = response.text if hasattr(response, 'text') else str(response)
                
                logger.debug(f"LLM response for '{column_context.get('name')}': {text[:200]}...")
                
                # Parse JSON response
                text = text.strip()
                if text.startswith("```json"):
                    text = text[7:]
                if text.startswith("```"):
                    text = text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()
                
                result = json.loads(text)

                # LLM explicitly declined (confidence < 60)
                if result.get("generated") is False or result.get("matched") is False:
                    logger.debug(
                        f"LLM declined to generate term for '{column_context.get('name')}': "
                        f"{result.get('rationale', 'low confidence')}"
                    )
                    return None

                # ── New multi-recommendation format ──────────────────────────
                recs: List[Dict] = result.get("recommendations", [])

                if not recs:
                    # Fallback: LLM returned the old single-term format — wrap it
                    if all(k in result for k in ["term_title", "term_description", "confidence"]):
                        recs = [result]
                    else:
                        missing = [k for k in ["term_title", "term_description", "confidence"] if k not in result]
                        logger.warning(
                            f"Tier 3 LLM response missing keys {missing} for "
                            f"'{column_context.get('name')}' — retrying"
                        )
                        continue

                # Filter to those above the confidence floor
                valid_recs = [r for r in recs if r.get("confidence", 0) >= 60]

                if not valid_recs:
                    logger.debug(
                        f"All Tier 3 candidates below confidence threshold for "
                        f"'{column_context.get('name')}'"
                    )
                    return None

                # Sort descending by confidence; pick best as primary
                valid_recs.sort(key=lambda r: -r.get("confidence", 0))
                best = valid_recs[0]

                logger.info(
                    f"✓ Tier 3 generated {len(valid_recs)} recommendation(s) for "
                    f"'{column_context.get('name')}': best='{best['term_title']}' "
                    f"(confidence: {best['confidence']}%)"
                )
                # Return a clean wrapper — do NOT embed valid_recs inside best because
                # best IS valid_recs[0], which would create a circular reference on
                # serialisation (json.dump raises "Circular reference detected").
                return {
                    "term_title":       best.get("term_title", ""),
                    "term_description": best.get("term_description", ""),
                    "confidence":       best.get("confidence", 0),
                    "rationale":        best.get("rationale", ""),
                    "all_recommendations": valid_recs,  # clean list, no self-reference
                }
                
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse LLM JSON response (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                continue
                
            except Exception as e:
                logger.error(f"LLM business term generation failed for column '{column_context.get('name')}' (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                continue
        
        logger.error(f"All {max_retries} business term generation attempts failed for column '{column_context.get('name')}'")
        return None
    
    async def _build_tier1_mappings(self, terms: List[Dict]) -> Dict[str, Dict]:
        """
        Build Tier 1 mappings from Data Asset links.
        
        Process:
        1. For each business term
        2. Extract Data Asset links (column IDs)
        3. Fetch column details for each linked column
        4. Create mapping: column_name → business metadata
        
        Args:
            terms: List of business term objects
            
        Returns:
            Dictionary mapping column_name → {term_title, term_description, confidence: 100, ...}
        """
        logger.info("="*80)
        logger.info("TIER 1: BUILDING DIRECT MAPPINGS FROM DATA ASSET LINKS")
        logger.info("="*80)
        
        column_to_metadata = {}
        linked_column_ids = []
        term_to_columns = {}  # Track which term links to which columns
        
        # Step 1: Extract all Data Asset links
        logger.info("Step 1: Extracting Data Asset links from business terms...")
        for term in terms:
            column_ids = self._extract_data_asset_links(term)
            if column_ids:
                term_to_columns[term["id"]] = {
                    "term": term,
                    "column_ids": column_ids
                }
                linked_column_ids.extend(column_ids)
        
        logger.info(f"✓ Found {len(linked_column_ids)} Data Asset links from {len(term_to_columns)} terms")
        
        if not linked_column_ids:
            logger.info("No Data Asset links found. Tier 1 mappings empty.")
            return column_to_metadata
        
        # Step 2: Fetch column details for all linked columns
        logger.info(f"Step 2: Fetching details for {len(linked_column_ids)} linked columns...")
        columns_map = await self.swagger_client.get_columns_batch(
            linked_column_ids,
            max_concurrent=10
        )
        logger.info(f"✓ Fetched {len(columns_map)} column details")
        
        # Step 3: Fetch table details
        table_ids = list(set(
            col.get("table_id")
            for col in columns_map.values()
            if col.get("table_id")
        ))
        
        logger.info(f"Step 3: Fetching {len(table_ids)} table details...")
        tables_map = await self.swagger_client.get_tables_batch(table_ids, max_concurrent=10)
        logger.info(f"✓ Fetched {len(tables_map)} tables")
        
        # Step 4: Build column → metadata mappings
        logger.info("Step 4: Building column → business metadata mappings...")
        for term_id, data in term_to_columns.items():
            term = data["term"]
            column_ids = data["column_ids"]
            
            for column_id in column_ids:
                column = columns_map.get(column_id)
                if not column:
                    logger.warning(f"Column {column_id} not found, skipping")
                    continue
                
                column_name = column.get("name")
                if not column_name:
                    logger.warning(f"Column {column_id} has no name, skipping")
                    continue
                
                table_id = column.get("table_id")
                table = tables_map.get(table_id, {})
                
                # Create mapping
                column_to_metadata[column_name] = {
                    "term_id": term["id"],
                    "term_title": term.get("title", ""),
                    "term_description": clean_html_description(term.get("description", "")),
                    "confidence_score": 100.0,
                    "linkage_type": "direct",
                    "matching_rationale": "Pre-configured in Alation via Data Asset field",
                    "column_id": column_id,
                    "table_id": table_id,
                    "table_name": table.get("name", "Unknown")
                }
        
        logger.info("="*80)
        logger.info(f"✓ TIER 1 COMPLETE: Created mappings for {len(column_to_metadata)} columns")
        logger.info("="*80)
        
        return column_to_metadata

    @staticmethod
    def _preselect_terms(
        column_name: str,
        column_context: Optional[Dict],
        terms: List[Dict],
        top_k: int = 50,
    ) -> List[Dict]:
        """Rank terms by keyword relevance to the column and return the top_k.

        Replaces the naive ``terms[:50]`` slice so the LLM always sees the most
        semantically plausible candidates rather than whatever terms happen to
        appear first in the API response.

        Scoring (additive):
          +3 per exact word overlap between column tokens and term title/description words
          +2 per column token found as substring in term title (catches abbreviations)
          +1 per term title word that appears in the column's table/schema context
        """
        col_text = column_name + " "
        if column_context:
            col_text += (column_context.get("description") or "") + " "
            col_text += (column_context.get("table_name") or "") + " "
            col_text += (column_context.get("schema_description") or "")
        col_words = {w for w in re.sub(r"[^a-z0-9]", " ", col_text.lower()).split() if len(w) > 1}

        if not col_words:
            return terms[:top_k]

        scored: List[tuple] = []
        for term in terms:
            term_title = (term.get("title") or "").lower()
            term_text = term_title + " " + clean_html_description(term.get("description") or "").lower()
            term_words = set(re.sub(r"[^a-z0-9]", " ", term_text).split())

            overlap    = len(col_words & term_words)
            substring  = sum(1 for w in col_words if len(w) > 2 and w in term_title)
            ctx_words  = set(re.sub(r"[^a-z0-9]", " ", term_title).split())
            ctx_overlap = len(col_words & ctx_words)

            scored.append((overlap * 3 + substring * 2 + ctx_overlap, term))

        scored.sort(key=lambda x: -x[0])
        return [t for _, t in scored[:top_k]]

    async def _semantic_match_column_to_term(
        self,
        column_name: str,
        column_context: Optional[Dict],
        terms: List[Dict],
        max_retries: int = 3
    ) -> Optional[Dict]:
        """
        Use LLM to semantically match a column to a business term.
        
        Args:
            column_name: Column name to match
            column_context: Full column details from Swagger API (description, type, table, etc.)
            terms: List of available business terms
            max_retries: Maximum number of retry attempts (default: 3)
            
        Returns:
            Dictionary with:
            {
                "term_id": int,
                "term_title": str,
                "term_description": str,
                "confidence": int (0-100),
                "rationale": str
            }
            Returns None if no good match found or LLM call fails
        """
        if not self.llm_client:
            logger.warning("LLM client not configured, skipping semantic matching")
            return None
        
        # Pre-score terms by keyword relevance so the LLM sees the most plausible candidates
        candidate_terms = self._preselect_terms(column_name, column_context, terms, top_k=50)
        terms_for_llm = [
            {
                "term_id": term.get("id"),
                "term_title": term.get("title", ""),
                "term_description": clean_html_description(term.get("description", ""))[:300],
            }
            for term in candidate_terms
        ]
        
        # Build comprehensive column context string
        column_info = f"**COLUMN NAME**: {column_name}\n"
        
        if column_context:
            # Column-level metadata
            if column_context.get("title"):
                column_info += f"**COLUMN TITLE**: {column_context.get('title')}\n"
            if column_context.get("description"):
                column_info += f"**COLUMN DESCRIPTION**: {clean_html_description(column_context.get('description', ''))}\n"
            if column_context.get("column_comment"):
                column_info += f"**COLUMN COMMENT**: {column_context.get('column_comment')}\n"
            if column_context.get("column_type"):
                column_info += f"**DATA TYPE**: {column_context.get('column_type')}\n"
            
            # Index information (helps understand column purpose)
            index_info = column_context.get("index", {})
            if index_info:
                if index_info.get("isPrimaryKey"):
                    column_info += f"**PRIMARY KEY**: Yes\n"
                if index_info.get("isForeignKey"):
                    column_info += f"**FOREIGN KEY**: Yes (references column {index_info.get('referencedColumnId')})\n"
            
            # Nullable info
            if column_context.get("nullable") is not None:
                column_info += f"**NULLABLE**: {column_context.get('nullable')}\n"
            
            # Table-level metadata
            if column_context.get("table_name"):
                column_info += f"**TABLE NAME**: {column_context.get('table_name')}\n"
            if column_context.get("table_title"):
                column_info += f"**TABLE TITLE**: {column_context.get('table_title')}\n"
            if column_context.get("table_description"):
                column_info += f"**TABLE DESCRIPTION**: {clean_html_description(column_context.get('table_description', ''))}\n"
            if column_context.get("table_comment"):
                column_info += f"**TABLE COMMENT**: {column_context.get('table_comment')}\n"
            if column_context.get("table_type"):
                column_info += f"**TABLE TYPE**: {column_context.get('table_type')}\n"
            
            # Schema-level metadata
            if column_context.get("schema_name"):
                column_info += f"**SCHEMA NAME**: {column_context.get('schema_name')}\n"
            if column_context.get("schema_title"):
                column_info += f"**SCHEMA TITLE**: {column_context.get('schema_title')}\n"
            if column_context.get("schema_description"):
                column_info += f"**SCHEMA DESCRIPTION**: {clean_html_description(column_context.get('schema_description', ''))}\n"
        
        # Design comprehensive data steward prompt
        prompt = f"""You are an expert Data Steward responsible for maintaining data governance and ensuring accurate business metadata tagging in an enterprise data catalog.

**YOUR TASK**: 
Analyze the technical column details below and identify which business glossary term best represents its business meaning and purpose.

**TECHNICAL COLUMN DETAILS**:
{column_info}

**AVAILABLE BUSINESS GLOSSARY TERMS**:
{json.dumps(terms_for_llm, indent=2)}

**DATA STEWARD MATCHING GUIDELINES**:

1. **Semantic Meaning First**: Match based on what the data REPRESENTS in business terms, not just name similarity
   - Example: "txn_amt" represents "Transaction Amount" (business concept)
   - Example: "cust_id" represents "Customer Identifier" (business concept)

2. **Use All Available Context**: Consider column name, description, data type, table context, and schema
   - Numeric types with "amt", "amount" → likely monetary values
   - Boolean/flag types → likely indicators or status fields
   - Foreign keys → likely identifiers or references
   - Date types → likely temporal dimensions

3. **Common Technical Patterns**:
   - Abbreviations: "conv" → "conversion", "txn" → "transaction", "cust" → "customer"
   - Suffixes: "_flag", "_ind" → boolean indicators; "_amt" → amounts; "_dt", "_date" → dates
   - Prefixes: "is_", "has_" → boolean states; "num_", "cnt_" → counts

4. **Table and Schema Context**: Use table/schema names to understand domain
   - "sales_transactions" table → likely contains sales-related business terms
   - "customer_profile" table → likely contains customer-related business terms

5. **Confidence Scoring** (0-100):
   - **90-100**: Exact semantic match with strong supporting evidence
     * Column name directly matches term + data type aligns + context confirms
   - **75-89**: Strong semantic match with good evidence
     * Clear abbreviation or synonym + data type aligns + context supports
   - **60-74**: Moderate semantic match with some evidence
     * Partial name match or related concept + some context alignment
   - **<60**: Weak match - DO NOT RETURN (let system mark as unmatched)

6. **When to Return No Match**:
   - No business term semantically represents the column's purpose
   - Confidence would be below 60%
   - Column appears to be purely technical (system columns, audit fields)

**EXAMPLES OF GOOD DATA STEWARD MATCHING**:

Example 1 - Direct Match:
Column: "conversion_rate", Type: "numeric(5,2)", Table: "marketing_metrics"
→ Match: "Conversion Rate" (confidence: 98)
Rationale: "Exact name match, numeric type appropriate for rate calculation, marketing context confirms"

Example 2 - Abbreviation Match:
Column: "conv_flag", Type: "boolean", Table: "sales_transactions"  
→ Match: "Conversion Flag" (confidence: 85)
Rationale: "'conv' is standard abbreviation for 'conversion', boolean type appropriate for flag, sales context supports conversion tracking"

Example 3 - Context-Driven Match:
Column: "device_cd", Type: "varchar(20)", Table: "user_sessions"
→ Match: "Device Type" (confidence: 80)
Rationale: "'cd' suffix indicates code/type, varchar appropriate for categorical data, user session context suggests device classification"

Example 4 - Foreign Key Match:
Column: "customer_id", Type: "bigint", Foreign Key: Yes, Table: "orders"
→ Match: "Customer Identifier" (confidence: 95)
Rationale: "Foreign key to customer table, bigint type for ID, orders context confirms customer reference"

**SECONDARY TASK — DESCRIPTION ENRICHMENT**:
After identifying the best-matching term, write an `enriched_description` that combines the term's existing definition with the specific context of this asset. This field will be written back to the data catalog as the authoritative definition for this column.

Guidelines for `enriched_description`:
- 2–4 sentences, present tense, written for a business analyst
- Preserve the core meaning from the existing term definition
- Incorporate specifics from the column context above: dashboard name, table/domain, page usage, visual types, format, aggregation behaviour (additive vs non-additive), DAX logic if present
- Do NOT use technical jargon like "varchar" or "bigint"; translate to plain English
- Do NOT say "this column" — write it as a standalone definition, as if it appears in a company glossary

Example of a good `enriched_description`:
> "The compound annual growth rate (CAGR) measures the mean annual growth rate of insurance premium revenue across the Tru Secure CreDebit portfolio over a specified period. Expressed as a percentage and displayed in the Premium Analysis page of the dashboard. As a non-additive ratio metric, it must not be summed across segments — always compare or average CAGR values rather than totalling them."

**OUTPUT FORMAT** (JSON only, no markdown, no explanatory text):
{{
  "term_id": 123,
  "term_title": "Conversion Rate",
  "term_description": "Percentage of visitors that convert to customers",
  "enriched_description": "The conversion rate measures the proportion of insurance premium quotations that result in active policy activations within the Tru Secure CreDebit Dashboard. Displayed as a percentage in card and table visuals on the Sales Performance page, it is used by regional managers to evaluate agent effectiveness and track pipeline conversion across geographic territories.",
  "confidence": 95,
  "rationale": "Exact name match with 'conversion_rate' column, numeric(5,2) type appropriate for percentage, marketing_metrics table context confirms this tracks conversion performance"
}}

If no appropriate match exists (confidence < 60), return: {{"matched": false}}

**IMPORTANT**: Return ONLY the JSON object. No markdown code blocks, no additional text, no explanations outside the JSON."""

        # Create agent
        agent = self.llm_client.create_agent(
            name="column_term_matcher",
            instructions="You are a precise data mapping expert. Output only valid JSON."
        )
        
        # Retry logic with exponential backoff
        for attempt in range(max_retries):
            try:
                logger.debug(f"LLM call attempt {attempt + 1}/{max_retries} for column '{column_name}'")
                
                response = await agent.run(prompt)
                text = response.text if hasattr(response, 'text') else str(response)
                
                logger.debug(f"LLM response for '{column_name}': {text[:200]}...")
                
                # Parse JSON response
                # Remove markdown code blocks if present
                text = text.strip()
                if text.startswith("```json"):
                    text = text[7:]
                if text.startswith("```"):
                    text = text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()
                
                result = json.loads(text)
                
                # Check if match was found
                if result.get("matched") == False:
                    logger.debug(f"No good match found for column '{column_name}'")
                    return None
                
                # Validate required fields
                if not all(k in result for k in ["term_id", "term_title", "confidence"]):
                    logger.warning(f"LLM response missing required fields for '{column_name}'")
                    continue
                
                # Return successful match
                return result
                
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse LLM JSON response (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                continue
                
            except Exception as e:
                logger.error(f"LLM call failed for column '{column_name}' (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                continue
        
        logger.error(f"All {max_retries} LLM attempts failed for column '{column_name}'")
        return None
    
    async def _build_tier2_mappings(
        self,
        column_names: List[str],
        tier1_mappings: Dict[str, Dict],
        terms: List[Dict]
    ) -> Dict[str, Dict]:
        """
        Build Tier 2 mappings using LLM semantic matching for unmapped columns.
        
        Process:
        1. Identify columns not in Tier 1 mappings
        2. Fetch full column details from Swagger API for context
        3. For each unmapped column, call LLM with full context to find best matching term
        4. Create mapping if confidence >= threshold
        
        Args:
            column_names: List of requested column names
            tier1_mappings: Existing Tier 1 mappings
            terms: List of all business terms
            
        Returns:
            Dictionary mapping column_name → business metadata (Tier 2 only)
        """
        logger.info("="*80)
        logger.info("TIER 2: SEMANTIC MATCHING FOR UNMAPPED COLUMNS")
        logger.info("="*80)
        
        if not self.llm_client:
            logger.warning("LLM client not configured, skipping Tier 2 semantic matching")
            return {}
        
        # Identify unmapped columns (case-insensitive)
        tier1_lower = {k.lower(): k for k in tier1_mappings.keys()}
        unmapped_columns = [
            col for col in column_names
            if col.lower() not in tier1_lower
        ]
        
        if not unmapped_columns:
            logger.info("All requested columns found in Tier 1, no Tier 2 matching needed")
            return {}
        
        logger.info(f"Found {len(unmapped_columns)} unmapped columns for Tier 2 matching")
        
        # Fetch all columns from Swagger API to get full context
        logger.info("Fetching all columns from Swagger API for context...")
        all_columns = await self.swagger_client.get_all_columns()
        
        # Build column name → column details lookup (case-insensitive)
        columns_by_name = {}
        for col in all_columns:
            col_name = col.get("name", "").lower()
            if col_name:
                columns_by_name[col_name] = col
        
        logger.info(f"✓ Fetched {len(all_columns)} columns for context")
        
        # Fetch table details for columns
        table_ids = set(col.get("table_id") for col in all_columns if col.get("table_id"))
        logger.info(f"Fetching {len(table_ids)} tables for additional context...")
        tables_by_id = await self.swagger_client.get_tables_batch(list(table_ids))
        logger.info(f"✓ Fetched {len(tables_by_id)} tables")
        
        # Fetch schema details for additional context
        schema_ids = set(col.get("schema_id") for col in all_columns if col.get("schema_id"))
        logger.info(f"Fetching {len(schema_ids)} schemas for additional context...")
        schemas_by_id = {}
        for schema_id in schema_ids:
            try:
                schema = await self.swagger_client.get_schema_by_id(schema_id)
                schemas_by_id[schema_id] = schema
            except Exception as e:
                logger.warning(f"Failed to fetch schema {schema_id}: {e}")
        logger.info(f"✓ Fetched {len(schemas_by_id)} schemas")
        
        tier2_mappings = {}
        matched_count = 0
        below_threshold_count = 0
        
        # Match each unmapped column
        for column_name in unmapped_columns:
            logger.info(f"Matching column: {column_name}")
            
            # Get full column context
            column_context = columns_by_name.get(column_name.lower())
            
            if column_context:
                # Enrich with table info
                table_id = column_context.get("table_id")
                if table_id and table_id in tables_by_id:
                    table = tables_by_id[table_id]
                    column_context["table_name"] = table.get("name")
                    column_context["table_title"] = table.get("title")
                    column_context["table_description"] = table.get("description")
                    column_context["table_comment"] = table.get("table_comment")
                    column_context["table_type"] = table.get("table_type")
                    column_context["schema_name"] = table.get("schema_name")
                
                # Enrich with schema info
                schema_id = column_context.get("schema_id")
                if schema_id and schema_id in schemas_by_id:
                    schema = schemas_by_id[schema_id]
                    column_context["schema_title"] = schema.get("title")
                    column_context["schema_description"] = schema.get("description")
                
                logger.debug(f"Column context for '{column_name}': type={column_context.get('column_type')}, table={column_context.get('table_name')}, schema={column_context.get('schema_name')}")
                
                # NEW: Enrich column description if missing
                if self.enrich_descriptions and not column_context.get("description"):
                    logger.info(f"Column '{column_name}' has no description, generating with LLM...")
                    enriched_description = await self._enrich_column_description(column_context)
                    if enriched_description:
                        column_context["description"] = enriched_description
                        column_context["description_enriched"] = True  # Mark as LLM-generated
            else:
                logger.warning(f"No column details found for '{column_name}' in Swagger API")
            
            match = await self._semantic_match_column_to_term(column_name, column_context, terms)
            
            if match and match.get("confidence", 0) >= self.confidence_threshold:
                # Create Tier 2 mapping
                tier2_mappings[column_name] = {
                    "term_id": match["term_id"],
                    "term_title": match["term_title"],
                    "term_description": match.get("term_description", ""),
                    "confidence_score": float(match["confidence"]),
                    "linkage_type": "semantic",
                    "matching_rationale": match.get("rationale", "LLM semantic matching"),
                    "column_id": column_context.get("id") if column_context else None,
                    "table_id": column_context.get("table_id") if column_context else None,
                    "table_name": column_context.get("table_name", "Unknown") if column_context else "Unknown"
                }
                matched_count += 1
                logger.info(f"✓ Matched '{column_name}' → '{match['term_title']}' (confidence: {match['confidence']}%)")
            elif match:
                below_threshold_count += 1
                logger.info(f"✗ Match for '{column_name}' below threshold (confidence: {match.get('confidence', 0)}%)")
                
                # TIER 3: Generate new business term if no good match found
                if column_context:
                    logger.info(f"Attempting to generate new business term for '{column_name}'...")
                    generated_term = await self._generate_new_business_term(column_context)
                    
                    if generated_term:
                        # Create Tier 3 mapping with generated term
                        tier2_mappings[column_name] = {
                            "term_id": None,  # No existing term ID
                            "term_title": generated_term["term_title"],
                            "term_description": generated_term["term_description"],
                            "confidence_score": float(generated_term["confidence"]),
                            "linkage_type": "generated",
                            "matching_rationale": generated_term.get("rationale", "LLM generated new business term"),
                            "column_id": column_context.get("id"),
                            "table_id": column_context.get("table_id"),
                            "table_name": column_context.get("table_name", "Unknown"),
                            "generated": True  # Flag to indicate this is a generated term
                        }
                        matched_count += 1
                        logger.info(f"✓ Generated new term for '{column_name}' → '{generated_term['term_title']}' (confidence: {generated_term['confidence']}%)")
                    else:
                        logger.info(f"✗ Could not generate business term for '{column_name}'")
            else:
                logger.info(f"✗ No match found for '{column_name}'")
                
                # TIER 3: Generate new business term if no match at all
                if column_context:
                    logger.info(f"Attempting to generate new business term for '{column_name}'...")
                    generated_term = await self._generate_new_business_term(column_context)
                    
                    if generated_term:
                        # Create Tier 3 mapping with generated term
                        tier2_mappings[column_name] = {
                            "term_id": None,  # No existing term ID
                            "term_title": generated_term["term_title"],
                            "term_description": generated_term["term_description"],
                            "confidence_score": float(generated_term["confidence"]),
                            "linkage_type": "generated",
                            "matching_rationale": generated_term.get("rationale", "LLM generated new business term"),
                            "column_id": column_context.get("id"),
                            "table_id": column_context.get("table_id"),
                            "table_name": column_context.get("table_name", "Unknown"),
                            "generated": True  # Flag to indicate this is a generated term
                        }
                        matched_count += 1
                        logger.info(f"✓ Generated new term for '{column_name}' → '{generated_term['term_title']}' (confidence: {generated_term['confidence']}%)")
                    else:
                        logger.info(f"✗ Could not generate business term for '{column_name}'")
        
        logger.info("="*80)
        logger.info(f"✓ TIER 2 & 3 COMPLETE: {matched_count} matches created")
        logger.info(f"  Semantic matches (Tier 2): {matched_count - sum(1 for m in tier2_mappings.values() if m.get('generated'))}")
        logger.info(f"  Generated terms (Tier 3): {sum(1 for m in tier2_mappings.values() if m.get('generated'))}")
        logger.info(f"  Below threshold: {below_threshold_count}")
        logger.info(f"  No match/generation: {len(unmapped_columns) - matched_count}")
        logger.info("="*80)
        
        return tier2_mappings
    
    def _is_cache_valid(self) -> bool:
        """
        Check if cache file exists and is not expired.
        
        Returns:
            True if cache is valid, False otherwise
        """
        cache_path = Path(self.cache_file)
        
        if not cache_path.exists():
            logger.debug("Cache file does not exist")
            return False
        
        try:
            with open(cache_path, 'r') as f:
                cache_data = json.load(f)
            
            metadata = cache_data.get("metadata", {})
            expires_at_str = metadata.get("expires_at")
            
            if not expires_at_str:
                logger.debug("Cache has no expiration timestamp")
                return False
            
            expires_at = datetime.fromisoformat(expires_at_str)
            now = datetime.utcnow()
            
            if now > expires_at:
                logger.debug(f"Cache expired at {expires_at_str}")
                return False
            
            logger.debug(f"Cache is valid until {expires_at_str}")
            return True
            
        except Exception as e:
            logger.warning(f"Error checking cache validity: {e}")
            return False
    
    def _load_cache(self) -> Dict[str, Dict]:
        """
        Load cached column → metadata mappings.
        
        Returns:
            Dictionary mapping column_name → business metadata
        """
        logger.info(f"Loading cache from {self.cache_file}...")
        
        try:
            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)
            
            mappings = cache_data.get("mappings", {})
            metadata = cache_data.get("metadata", {})
            
            logger.info(f"✓ Loaded {len(mappings)} column mappings from cache")
            logger.info(f"  Cache created: {metadata.get('created_at')}")
            logger.info(f"  Cache expires: {metadata.get('expires_at')}")
            
            return mappings
            
        except Exception as e:
            logger.error(f"Failed to load cache: {e}")
            return {}
    
    def _save_cache(self, column_to_metadata: Dict[str, Dict]) -> None:
        """
        Save column → metadata mappings to cache.
        
        Args:
            column_to_metadata: Dictionary mapping column_name → business metadata
        """
        logger.info(f"Saving cache to {self.cache_file}...")
        
        # Create cache directory if it doesn't exist
        cache_path = Path(self.cache_file)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Prepare cache data
        now = datetime.utcnow()
        expires_at = now + timedelta(hours=self.cache_hours)
        
        cache_data = {
            "metadata": {
                "created_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
                "cache_hours": self.cache_hours,
                "total_columns": len(column_to_metadata),
                "tier1_count": sum(1 for m in column_to_metadata.values() if m["linkage_type"] == "direct"),
                "tier2_count": sum(1 for m in column_to_metadata.values() if m["linkage_type"] == "semantic")
            },
            "mappings": column_to_metadata
        }
        
        # Save to file
        with open(cache_path, 'w') as f:
            json.dump(cache_data, f, indent=2)
        
        logger.info(f"✓ Saved {len(column_to_metadata)} column mappings to cache")
        logger.info(f"  Cache expires: {expires_at.isoformat()}")
    
    async def _get_or_build_reverse_index(
        self,
        use_cache: bool = True,
        requested_columns: Optional[List[str]] = None
    ) -> Dict[str, Dict]:
        """
        Load cached reverse index or build new one.
        
        Args:
            use_cache: Whether to use cached data
            requested_columns: Optional list of requested column names for Tier 2 matching
            
        Returns:
            Dictionary mapping column_name → business metadata
        """
        # In-memory cache — avoids disk I/O on every enrich_asset() call within the same batch
        if use_cache and self._reverse_index_cache is not None:
            return self._reverse_index_cache

        # Check disk cache
        if use_cache and self._is_cache_valid():
            cached_mappings = self._load_cache()
            self._reverse_index_cache = cached_mappings
            
            # If specific columns requested, run Tier 2 for unmapped ones
            if requested_columns and self.llm_client:
                # Fetch terms for Tier 2
                terms = await self.swagger_client.get_terms(glossary_id=self.glossary_id)
                tier2_mappings = await self._build_tier2_mappings(
                    requested_columns,
                    cached_mappings,
                    terms
                )
                if tier2_mappings:
                    cached_mappings.update(tier2_mappings)
                    # Persist Tier 2 results so the same columns aren't re-processed next call
                    self._save_cache(cached_mappings)

            return cached_mappings
        
        # Build new index
        logger.info("\n" + "="*80)
        logger.info("BUILDING REVERSE INDEX: COLUMN → BUSINESS METADATA")
        logger.info("="*80)
        
        # Fetch all business terms
        logger.info("Fetching all business terms from middleware API...")
        terms = await self.swagger_client.get_terms(glossary_id=self.glossary_id)
        logger.info(f"✓ Fetched {len(terms)} business terms")
        
        # Build Tier 1 mappings (Data Asset links)
        tier1_mappings = await self._build_tier1_mappings(terms)
        
        # Build Tier 2 mappings (semantic matching for requested unmapped columns)
        tier2_mappings = {}
        if requested_columns and self.llm_client:
            tier2_mappings = await self._build_tier2_mappings(
                requested_columns,
                tier1_mappings,
                terms
            )
        
        # Merge Tier 1 and Tier 2
        all_mappings = {**tier1_mappings, **tier2_mappings}
        self._reverse_index_cache = all_mappings

        # Save everything — Tier 2 results are valid to cache; they'll be skipped
        # on subsequent calls for the same columns since they'll already be present.
        self._save_cache(all_mappings)

        logger.info("="*80)
        logger.info("REVERSE INDEX BUILD COMPLETE")
        logger.info(f"  Tier 1: {len(tier1_mappings)} mappings")
        logger.info(f"  Tier 2: {len(tier2_mappings)} mappings")
        logger.info("="*80)

        return all_mappings
    
    async def get_business_metadata_for_columns(
        self,
        column_names: List[str],
        use_cache: bool = True
    ) -> Dict[str, Optional[Dict]]:
        """
        Get business metadata for given column names.
        
        This is the main entry point for column → business metadata lookup.
        
        Args:
            column_names: List of column names to look up
            use_cache: Whether to use cached mappings (default: True)
            
        Returns:
            Dictionary mapping column_name → business metadata
            Returns None for columns not found
            
        Example:
            >>> lookup = ColumnMetadataLookup(swagger_client)
            >>> results = await lookup.get_business_metadata_for_columns(
            ...     ["conversion_flag", "device_type"]
            ... )
            >>> print(results["conversion_flag"]["term_title"])
            "Conversion Flag"
        """
        logger.info("\n" + "="*80)
        logger.info(f"COLUMN METADATA LOOKUP: {len(column_names)} columns requested")
        logger.info("="*80)
        
        # Validate input
        if not column_names:
            logger.warning("No column names provided")
            return {}
        
        # Normalize column names (strip whitespace, lowercase for matching)
        normalized_names = [name.strip().lower() for name in column_names]
        
        # Get or build reverse index (pass requested columns for Tier 2)
        column_to_metadata = await self._get_or_build_reverse_index(
            use_cache=use_cache,
            requested_columns=column_names
        )
        
        # Build case-insensitive lookup
        metadata_lower = {k.lower(): v for k, v in column_to_metadata.items()}
        
        # Lookup requested columns
        results = {}
        for original_name, normalized_name in zip(column_names, normalized_names):
            if normalized_name in metadata_lower:
                results[original_name] = metadata_lower[normalized_name]
            else:
                results[original_name] = None
                logger.warning(f"Column '{original_name}' not found in mappings")
        
        # Log summary
        found_count = sum(1 for v in results.values() if v is not None)
        not_found_count = len(results) - found_count
        
        logger.info("="*80)
        logger.info("LOOKUP COMPLETE")
        logger.info("="*80)
        logger.info(f"  Requested: {len(column_names)} columns")
        logger.info(f"  Found: {found_count} columns")
        logger.info(f"  Not Found: {not_found_count} columns")
        logger.info("="*80)
        
        return results
    
    async def get_business_metadata_for_column(
        self,
        column_name: str,
        use_cache: bool = True
    ) -> Optional[Dict]:
        """
        Get business metadata for a single column.

        Args:
            column_name: Column name to look up
            use_cache: Whether to use cached mappings (default: True)

        Returns:
            Business metadata dict or None if not found

        Example:
            >>> lookup = ColumnMetadataLookup(swagger_client)
            >>> metadata = await lookup.get_business_metadata_for_column("conversion_flag")
            >>> print(metadata["term_title"])
            "Conversion Flag"
        """
        results = await self.get_business_metadata_for_columns([column_name], use_cache)
        return results.get(column_name)

    async def get_business_metadata_with_context(
        self,
        name: str,
        column_context: Dict[str, Any],
        use_cache: bool = True,
    ) -> Optional[Dict]:
        """
        Run the 3-tier pipeline with caller-supplied context instead of Alation column data.

        The normal get_business_metadata_for_column() fetches context from the Alation
        Swagger API (column type, table, schema).  For RE-model assets (calculations,
        BI columns) that don't exist as Alation columns, that fetch returns None, so the
        LLM only sees the raw name string — losing all DAX expressions, semantic types,
        and page-usage information.

        This method bypasses the Alation column fetch and passes column_context directly
        to _semantic_match_column_to_term and _generate_new_business_term.  The 3-tier
        flow (Tier 1 cache check → Tier 2 semantic match → Tier 3 generation) is unchanged.

        Args:
            name: Asset technical name (used for Tier 1 lookup and as the prompt heading)
            column_context: Dict with keys the prompt already understands —
                description, table_name, table_description, table_type, schema_name, etc.
                Map EnrichmentContext fields into these keys before calling.
            use_cache: Whether to use the cached Tier 1 direct-link index

        Returns:
            Business metadata dict (same format as get_business_metadata_for_column)
            or None if no match at any tier.
        """
        # --- Tier 1: Direct link check via cached index ---
        reverse_index = await self._get_or_build_reverse_index(
            use_cache=use_cache, requested_columns=None
        )
        index_lower = {k.lower(): v for k, v in reverse_index.items()}
        tier1 = index_lower.get(name.lower())
        if tier1:
            logger.info(f"✓ Tier 1 hit for '{name}' via direct-link cache")
            return {**tier1, 'linkage_type': 'direct'}

        if not self.llm_client:
            logger.info(f"No LLM client — skipping Tier 2/3 for '{name}'")
            return None

        # --- Fetch terms for Tier 2 / Tier 3 (cached per ColumnMetadataLookup instance) ---
        if self._terms_cache is None:
            logger.info(f"Fetching glossary terms (first call for this batch) for '{name}'...")
            self._terms_cache = await self.swagger_client.get_terms(glossary_id=self.glossary_id)
        terms = self._terms_cache
        if not terms:
            logger.warning("No terms returned from Alation — cannot run Tier 2/3")
            return None

        # --- Tier 2: Semantic match with injected context ---
        logger.info(f"Tier 2: semantic match for '{name}' with pre-built context")
        match = await self._semantic_match_column_to_term(name, column_context, terms)
        if match and match.get('confidence', 0) >= self.confidence_threshold:
            logger.info(
                f"✓ Tier 2 match for '{name}' → '{match['term_title']}' "
                f"(confidence: {match['confidence']}%)"
            )
            return {
                'term_id': match['term_id'],
                'term_title': match['term_title'],
                'term_description': match.get('term_description', ''),
                'enriched_description': match.get('enriched_description') or match.get('term_description', ''),
                'confidence_score': float(match['confidence']),
                'linkage_type': 'semantic',
                'matching_rationale': match.get('rationale', 'LLM semantic matching'),
            }

        # --- Tier 3: Generate new term recommendations ---
        logger.info(f"Tier 3: generating new business term recommendations for '{name}'")
        generated = await self._generate_new_business_term(column_context)
        if generated:
            recs = generated.get("all_recommendations", [generated])
            logger.info(
                f"✓ Tier 3: {len(recs)} recommendation(s) for '{name}' — "
                f"best='{generated['term_title']}' (confidence: {generated['confidence']}%)"
            )
            return {
                'term_id': None,
                'term_title': generated['term_title'],
                'term_description': generated['term_description'],
                # Tier 3 descriptions are generated fresh from context, so they ARE the enrichment
                'enriched_description': generated['term_description'],
                'confidence_score': float(generated['confidence']),
                'linkage_type': 'generated',
                'matching_rationale': generated.get('rationale', 'LLM generated new business term'),
                'generated': True,
                'tier3_recommendations': recs,
            }

        logger.info(f"✗ No match at any tier for '{name}'")
        return None


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

async def example_usage():
    """Example of how to use the ColumnMetadataLookup"""
    from linker_agent.clients.alation_client import SwaggerAPIConfig
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    # Configure API client
    config = SwaggerAPIConfig(
        base_url=os.getenv("ALATION_BASE_URL"),
        api_token=os.getenv("ALATION_API_TOKEN"),
        auth_header_type="TOKEN",
        glossary_id=int(os.getenv("ALATION_GLOSSARY_ID", "2"))
    )
    
    # Create lookup instance
    async with SwaggerAPIClient(config) as swagger_client:
        lookup = ColumnMetadataLookup(swagger_client)
        
        # Single column lookup
        metadata = await lookup.get_business_metadata_for_column("conversion_flag")
        if metadata:
            print(f"\nColumn: conversion_flag")
            print(f"Business Term: {metadata['term_title']}")
            print(f"Description: {metadata['term_description']}")
            print(f"Confidence: {metadata['confidence_score']}%")
        
        # Multiple columns lookup
        columns = ["conversion_flag", "device_type", "transaction_date"]
        results = await lookup.get_business_metadata_for_columns(columns)
        
        print(f"\n\nLookup Results for {len(columns)} columns:")
        for col, meta in results.items():
            if meta:
                print(f"\n{col} → {meta['term_title']}")
                print(f"  {meta['term_description'][:100]}...")
            else:
                print(f"\n{col} → NOT FOUND")


if __name__ == "__main__":
    asyncio.run(example_usage())
