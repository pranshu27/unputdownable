"""
Basic test to verify linker agent functionality
"""
import asyncio
import sys
from pathlib import Path

# Add linker_agent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from linker_agent.clients.alation_client import SwaggerAPIClient, SwaggerAPIConfig
from linker_agent.core.column_metadata_lookup import ColumnMetadataLookup
from linker_agent.utils.llm_factory import get_azure_chat_client
from linker_agent.utils.logger import configure_logger
from dotenv import load_dotenv
import os

logger = configure_logger(__file__)


async def test_basic_functionality():
    """Test basic linker agent functionality"""
    
    print("="*80)
    print("LINKER AGENT - BASIC FUNCTIONALITY TEST")
    print("="*80)
    
    # Load environment variables
    load_dotenv()
    
    # Check configuration
    print("\n1. Checking Configuration...")
    alation_url = os.getenv("ALATION_BASE_URL")
    alation_token = os.getenv("ALATION_API_TOKEN")
    azure_endpoint = os.getenv("AZURE_OPENAI_API_BASE")
    azure_key = os.getenv("AZURE_OPENAI_API_KEY")
    
    if not all([alation_url, alation_token]):
        print("❌ Missing Alation configuration")
        print("   Set ALATION_BASE_URL and ALATION_API_TOKEN in .env")
        return False
    
    if not all([azure_endpoint, azure_key]):
        print("⚠️  Missing Azure OpenAI configuration (Tier 2/3 will be disabled)")
        print("   Set AZURE_OPENAI_API_BASE and AZURE_OPENAI_API_KEY in .env")
        llm_client = None
    else:
        print("✓ Azure OpenAI configured")
        try:
            llm_client = get_azure_chat_client()
            print("✓ LLM client initialized")
        except Exception as e:
            print(f"❌ Failed to initialize LLM client: {e}")
            llm_client = None
    
    print("✓ Alation configured")
    
    # Initialize Alation client
    print("\n2. Initializing Alation Client...")
    config = SwaggerAPIConfig(
        base_url=alation_url,
        api_token=alation_token,
        glossary_id=int(os.getenv("ALATION_GLOSSARY_ID", "1")),
        verify_ssl=False  # Disable SSL verification for testing
    )
    print("⚠️  SSL verification disabled for testing")
    
    try:
        async with SwaggerAPIClient(config) as swagger_client:
            print("✓ Alation client connected")
            
            # Test: Fetch terms
            print("\n3. Testing Alation API - Fetching Business Terms...")
            terms = await swagger_client.get_terms(glossary_id=config.glossary_id)
            print(f"✓ Fetched {len(terms)} business terms")
            
            if terms:
                print(f"   Sample term: {terms[0].get('title', 'N/A')}")
            
            # Test: Fetch columns
            print("\n4. Testing Alation API - Fetching Columns...")
            columns = await swagger_client.get_all_columns()
            print(f"✓ Fetched {len(columns)} columns")
            
            if columns:
                print(f"   Sample column: {columns[0].get('name', 'N/A')}")
            
            # Test: Column Metadata Lookup
            print("\n5. Testing Column Metadata Lookup...")
            lookup = ColumnMetadataLookup(
                swagger_client=swagger_client,
                llm_client=llm_client,
                confidence_threshold=60,
                cache_hours=24,
                glossary_id=config.glossary_id,
                enrich_descriptions=True
            )
            
            # Test with a few sample columns
            test_columns = [columns[i].get('name') for i in range(min(3, len(columns))) if columns[i].get('name')]
            
            if test_columns:
                print(f"   Testing with columns: {test_columns}")
                results = await lookup.get_business_metadata_for_columns(
                    test_columns,
                    use_cache=False
                )
                
                print(f"\n   Results:")
                for col_name, metadata in results.items():
                    if metadata:
                        print(f"   ✓ {col_name} → {metadata['term_title']}")
                        print(f"      Confidence: {metadata['confidence_score']}%")
                        print(f"      Type: {metadata['linkage_type']}")
                    else:
                        print(f"   ✗ {col_name} → No mapping found")
            else:
                print("   ⚠️  No columns available for testing")
            
            print("\n" + "="*80)
            print("✓ ALL TESTS PASSED - Linker Agent is functional!")
            print("="*80)
            return True
            
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_basic_functionality())
    sys.exit(0 if success else 1)
