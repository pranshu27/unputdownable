"""
Simple example showing basic linker agent usage
"""
import asyncio
import os
from dotenv import load_dotenv

# Add parent directory to path for imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from linker_agent import ColumnMetadataLookup, AlationClient, AzureLLMClient


async def main():
    """Simple example of column metadata lookup"""
    
    # Load environment variables
    load_dotenv()
    
    print("Linker Agent - Simple Example")
    print("="*60)
    
    # Initialize Alation client
    async with AlationClient(
        base_url=os.getenv("ALATION_BASE_URL"),
        api_token=os.getenv("ALATION_API_TOKEN"),
        glossary_id=int(os.getenv("ALATION_GLOSSARY_ID", "1")),
        verify_ssl=False  # Set to True in production
    ) as alation:
        
        # Initialize Azure OpenAI client
        llm = AzureLLMClient(
            endpoint=os.getenv("AZURE_OPENAI_API_BASE"),
            deployment_name=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
            api_key=os.getenv("AZURE_OPENAI_API_KEY")
        )
        
        # Create linker
        lookup = ColumnMetadataLookup(
            swagger_client=alation,
            llm_client=llm,
            confidence_threshold=60
        )
        
        # Lookup columns
        print("\nLooking up columns...")
        columns = ["customer_id", "transaction_date", "total_amount"]
        
        results = await lookup.get_business_metadata_for_columns(columns)
        
        # Display results
        print("\nResults:")
        print("-"*60)
        
        for column_name, metadata in results.items():
            if metadata:
                print(f"\n✓ {column_name}")
                print(f"  Business Term: {metadata['term_title']}")
                print(f"  Description: {metadata['term_description'][:80]}...")
                print(f"  Confidence: {metadata['confidence_score']}%")
                print(f"  Type: {metadata['linkage_type']}")
                if metadata.get('generated'):
                    print(f"  ⭐ AI-Generated (needs review)")
            else:
                print(f"\n✗ {column_name}")
                print(f"  No mapping found")
        
        print("\n" + "="*60)
        print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
