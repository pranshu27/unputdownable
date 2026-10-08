"""
Comprehensive Test: All Three Tiers of Column to Business Metadata Lookup

This test demonstrates and validates:
- TIER 1: Direct linkage (100% confidence) - Columns with Data Asset links
- TIER 2: Semantic matching (60-100% confidence) - Similar columns matched to existing terms
- TIER 3: Term generation (80-100% confidence) - New terms generated for unmatched columns

Based on Glossary 2 terms:
- ID 10: Customer Information
- ID 11: Date and Time
- ID 12: Reporting Usage Metadata
- ID 13: Geographic Information
- ID 14: Reference Identifiers
"""

import asyncio
import sys
import os
from pathlib import Path
from dotenv import load_dotenv
import json
from datetime import datetime

# Add linker_agent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from linker_agent.clients.alation_client import SwaggerAPIClient, SwaggerAPIConfig
from linker_agent.core.column_metadata_lookup import ColumnMetadataLookup
from linker_agent.utils.llm_factory import get_azure_chat_client
from linker_agent.utils.logger import configure_logger

logger = configure_logger(__file__)


def print_section(title):
    """Print a formatted section header"""
    print()
    print("="*80)
    print(f"  {title}")
    print("="*80)
    print()


def print_result(column_name, metadata):
    """Print formatted result for a column"""
    if metadata:
        print(f"Column: {column_name}")
        print(f"  ✓ Business Term: {metadata.get('term_title')}")
        print(f"  ✓ Term ID: {metadata.get('term_id')}")
        print(f"  ✓ Linkage Type: {metadata.get('linkage_type').upper()}")
        print(f"  ✓ Confidence: {metadata.get('confidence_score')}%")
        
        # Show context
        if metadata.get('column_id'):
            print(f"  ✓ Column ID: {metadata.get('column_id')}")
        if metadata.get('table_id'):
            print(f"  ✓ Table ID: {metadata.get('table_id')}")
        if metadata.get('table_name'):
            print(f"  ✓ Table: {metadata.get('table_name')}")
        
        # Show description (truncated)
        desc = metadata.get('term_description', '')
        if desc:
            print(f"  ✓ Description: {desc[:150]}...")
        
        # Show rationale for semantic/generated
        if metadata.get('matching_rationale'):
            rationale = metadata.get('matching_rationale')
            print(f"  ✓ Rationale: {rationale[:150]}...")
        
        # Show if generated
        if metadata.get('generated'):
            print(f"  ✓ GENERATED: New term created")
        
        print()
    else:
        print(f"Column: {column_name}")
        print(f"  ✗ No metadata found")
        print()


async def test_all_tiers():
    """
    Test all three tiers with real columns from glossary 2
    """
    
    print_section("COMPREHENSIVE THREE-TIER TEST - GLOSSARY 2")
    
    print("This test validates the three-tier lookup strategy:")
    print("  1. TIER 1: Direct linkage (columns with Data Asset links)")
    print("  2. TIER 2: Semantic matching (similar columns matched to existing terms)")
    print("  3. TIER 3: Term generation (new terms for unmatched columns)")
    print()
    
    # Load environment
    load_dotenv()
    
    # Initialize configuration
    glossary_id = int(os.getenv("ALATION_GLOSSARY_ID", "2"))
    config = SwaggerAPIConfig(
        base_url=os.getenv("ALATION_BASE_URL"),
        api_token=os.getenv("ALATION_API_TOKEN"),
        glossary_id=glossary_id,
        verify_ssl=False
    )
    
    print(f"Configuration:")
    print(f"  Base URL: {config.base_url}")
    print(f"  Glossary ID: {glossary_id}")
    print()
    
    # Initialize LLM client
    print("Initializing Azure OpenAI client...")
    try:
        llm_client = get_azure_chat_client()
        print("✓ LLM client initialized")
    except Exception as e:
        print(f"❌ Failed to initialize LLM client: {e}")
        print("   Tier 2 and Tier 3 will not work without LLM")
        return False
    print()
    
    async with SwaggerAPIClient(config) as swagger_client:
        # Initialize lookup
        lookup = ColumnMetadataLookup(
            swagger_client=swagger_client,
            llm_client=llm_client,
            confidence_threshold=60,
            glossary_id=glossary_id,
            enrich_descriptions=True
        )
        
        # ====================================================================
        # TIER 1: Direct Linkage Test
        # ====================================================================
        
        print_section("TIER 1: DIRECT LINKAGE TEST")
        print("Testing columns that have direct Data Asset links in glossary 2")
        print("Expected: 100% confidence, instant results, no LLM calls")
        print()
        
        tier1_columns = [
            "customer_id",              # → Customer Information (ID 10)
            "lastmodifieddate",         # → Date and Time (ID 11)
            "police_report_available",  # → Reporting Usage Metadata (ID 12)
            "region",                   # → Geographic Information (ID 13)
            "incident_city",            # → Reference Identifiers (ID 14)
        ]
        
        print(f"Testing {len(tier1_columns)} columns with direct links...")
        print()
        
        tier1_results = await lookup.get_business_metadata_for_columns(
            tier1_columns,
            use_cache=False
        )
        
        tier1_success = 0
        for col in tier1_columns:
            metadata = tier1_results.get(col)
            print_result(col, metadata)
            if metadata and metadata.get('linkage_type') == 'direct':
                tier1_success += 1
        
        print(f"TIER 1 Results: {tier1_success}/{len(tier1_columns)} columns found via direct linkage")
        print()
        
        # ====================================================================
        # TIER 2: Semantic Matching Test
        # ====================================================================
        
        print_section("TIER 2: SEMANTIC MATCHING TEST")
        print("Testing columns that:")
        print("  - Exist in Alation (have column_id, table_id)")
        print("  - Are similar to glossary 2 terms")
        print("  - Should get 60-100% confidence semantic matches")
        print()
        
        # Use columns that EXIST in Alation and are similar to glossary 2
        tier2_columns = [
            "action_status",            # Similar to status/metadata
            "total_object_count",       # Similar to count/metadata
            "last_updated_on_source",   # Similar to date/time
        ]
        
        print(f"Testing {len(tier2_columns)} columns for semantic matching...")
        print()
        
        tier2_results = await lookup.get_business_metadata_for_columns(
            tier2_columns,
            use_cache=False
        )
        
        tier2_success = 0
        for col in tier2_columns:
            metadata = tier2_results.get(col)
            print_result(col, metadata)
            if metadata and metadata.get('linkage_type') == 'semantic':
                tier2_success += 1
        
        print(f"TIER 2 Results: {tier2_success}/{len(tier2_columns)} columns matched semantically")
        print()
        
        # ====================================================================
        # TIER 3: Term Generation Test
        # ====================================================================
        
        print_section("TIER 3: TERM GENERATION TEST")
        print("Testing columns that:")
        print("  - Exist in Alation (have column_id, table_id)")
        print("  - Are unique/different from glossary 2 terms")
        print("  - Should trigger term generation")
        print()
        print("Strategy: Use HIGH confidence threshold (95%) to force generation")
        print()
        
        # Use columns that are unique and won't match glossary 2 well
        tier3_columns = [
            "built_in",                 # Boolean flag - unique concept
            "canceled",                 # Boolean flag - unique concept
            "excluded",                 # Boolean flag - unique concept
        ]
        
        print(f"Testing {len(tier3_columns)} columns for term generation...")
        print()
        
        # Create new lookup with HIGH threshold to force generation
        lookup_tier3 = ColumnMetadataLookup(
            swagger_client=swagger_client,
            llm_client=llm_client,
            confidence_threshold=95,  # High threshold to force generation
            glossary_id=glossary_id,
            enrich_descriptions=True
        )
        
        tier3_results = await lookup_tier3.get_business_metadata_for_columns(
            tier3_columns,
            use_cache=False
        )
        
        tier3_success = 0
        tier3_generated = 0
        for col in tier3_columns:
            metadata = tier3_results.get(col)
            print_result(col, metadata)
            if metadata:
                tier3_success += 1
                if metadata.get('linkage_type') == 'generated':
                    tier3_generated += 1
        
        print(f"TIER 3 Results: {tier3_generated}/{len(tier3_columns)} columns got generated terms")
        print(f"               {tier3_success}/{len(tier3_columns)} columns got any result")
        print()
        
        # ====================================================================
        # Final Summary
        # ====================================================================
        
        print_section("FINAL SUMMARY")
        
        total_columns = len(tier1_columns) + len(tier2_columns) + len(tier3_columns)
        total_success = tier1_success + tier2_success + tier3_success
        
        print(f"Total Columns Tested: {total_columns}")
        print()
        print(f"TIER 1 (Direct Linkage):")
        print(f"  Tested: {len(tier1_columns)}")
        print(f"  Success: {tier1_success}")
        print(f"  Success Rate: {(tier1_success/len(tier1_columns)*100):.1f}%")
        print()
        print(f"TIER 2 (Semantic Matching):")
        print(f"  Tested: {len(tier2_columns)}")
        print(f"  Success: {tier2_success}")
        print(f"  Success Rate: {(tier2_success/len(tier2_columns)*100):.1f}%")
        print()
        print(f"TIER 3 (Term Generation):")
        print(f"  Tested: {len(tier3_columns)}")
        print(f"  Generated: {tier3_generated}")
        print(f"  Any Result: {tier3_success}")
        print(f"  Generation Rate: {(tier3_generated/len(tier3_columns)*100):.1f}%")
        print()
        print(f"Overall Success Rate: {(total_success/total_columns*100):.1f}%")
        print()
        
        # Verify glossary 2 usage
        print("Glossary Verification:")
        all_results = {**tier1_results, **tier2_results, **tier3_results}
        glossary_2_terms = 0
        generated_terms = 0
        for metadata in all_results.values():
            if metadata:
                term_id = metadata.get('term_id')
                if term_id and 10 <= term_id <= 14:
                    glossary_2_terms += 1
                if metadata.get('generated'):
                    generated_terms += 1
        
        print(f"  Terms from Glossary 2: {glossary_2_terms}")
        print(f"  Generated Terms: {generated_terms}")
        print()
        
        # Validation
        if tier1_success == len(tier1_columns):
            print("✓ TIER 1 PASSED: All direct links working correctly")
        else:
            print("⚠ TIER 1 PARTIAL: Some direct links failed")
        
        if tier2_success > 0:
            print("✓ TIER 2 WORKING: Semantic matching is functional")
        else:
            print("⚠ TIER 2 NEEDS REVIEW: No semantic matches found")
        
        if tier3_generated > 0:
            print("✓ TIER 3 WORKING: Term generation is functional")
        else:
            print("⚠ TIER 3 NOTE: No terms generated (may have matched semantically at 95%)")
        
        print()
        print("="*80)
        
        # Save results to JSON file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_file = f"test_results_three_tiers_{timestamp}.json"
        
        all_results_data = {
            "test_timestamp": datetime.now().isoformat(),
            "glossary_id": glossary_id,
            "tier1": {
                "columns_tested": tier1_columns,
                "results": tier1_results,
                "success_count": tier1_success,
                "success_rate": f"{(tier1_success/len(tier1_columns)*100):.1f}%"
            },
            "tier2": {
                "columns_tested": tier2_columns,
                "results": tier2_results,
                "success_count": tier2_success,
                "success_rate": f"{(tier2_success/len(tier2_columns)*100):.1f}%"
            },
            "tier3": {
                "columns_tested": tier3_columns,
                "results": tier3_results,
                "generated_count": tier3_generated,
                "success_count": tier3_success,
                "generation_rate": f"{(tier3_generated/len(tier3_columns)*100):.1f}%"
            },
            "summary": {
                "total_columns": total_columns,
                "total_success": total_success,
                "overall_success_rate": f"{(total_success/total_columns*100):.1f}%",
                "tier1_passed": tier1_success == len(tier1_columns),
                "tier2_working": tier2_success > 0,
                "tier3_working": tier3_generated > 0,
                "glossary_2_terms_used": glossary_2_terms,
                "generated_terms": generated_terms
            }
        }
        
        with open(results_file, 'w') as f:
            json.dump(all_results_data, f, indent=2)
        
        print(f"\n✓ Results saved to: {results_file}")
        print("="*80)
        
        return tier1_success == len(tier1_columns) and tier2_success > 0


if __name__ == "__main__":
    success = asyncio.run(test_all_tiers())
    sys.exit(0 if success else 1)
