"""
Tests for the asset ingestion layer: model parser, context builder, event log.
Run from the LinkerAgent/ root: pytest linker_agent/tests/test_ingestion.py -v
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

INPUT_PATH = Path(__file__).parent.parent / "input1.json"


# ---------------------------------------------------------------------------
# Test 1: ID generation uniqueness
# ---------------------------------------------------------------------------

def test_ids_are_unique():
    from linker_agent.ingestion.model_parser import parse_common_model_file
    records = parse_common_model_file(INPUT_PATH)
    ids = [r.asset_id for r in records]
    assert len(ids) == len(set(ids)), (
        f"Duplicate IDs found: {len(ids) - len(set(ids))} duplicates"
    )


# ---------------------------------------------------------------------------
# Test 2: All asset types parsed, total count correct
# ---------------------------------------------------------------------------

def test_all_asset_types_present():
    from linker_agent.ingestion.model_parser import parse_common_model_file
    from linker_agent.models.asset_record import AssetType
    records = parse_common_model_file(INPUT_PATH)
    types = {r.asset_type for r in records}
    assert AssetType.TABLE in types
    assert AssetType.COLUMN in types or AssetType.DIMENSION in types
    assert AssetType.CALCULATION in types
    assert len(records) == 97, f"Expected 97 assets, got {len(records)}"


# ---------------------------------------------------------------------------
# Test 3: Visual usage index populated for calculations
# ---------------------------------------------------------------------------

def test_calculations_have_usage_context():
    from linker_agent.ingestion.model_parser import parse_common_model_file
    records = parse_common_model_file(INPUT_PATH)
    calcs = [r for r in records if r.asset_type == "calculation"]
    calcs_with_usage = [c for c in calcs if c.context.pages_used_on]
    assert len(calcs_with_usage) > 0, "No calculations have page usage context"


# ---------------------------------------------------------------------------
# Test 4: Source tool inferred as powerbi
# ---------------------------------------------------------------------------

def test_source_tool_inferred():
    from linker_agent.ingestion.model_parser import parse_common_model_file
    records = parse_common_model_file(INPUT_PATH)
    for r in records:
        assert r.context.source_tool != 'unknown', (
            f"source_tool not inferred for {r.asset_id}"
        )
        assert r.context.source_tool == 'powerbi'


# ---------------------------------------------------------------------------
# Test 5: Context builder produces non-empty output for all assets
# ---------------------------------------------------------------------------

def test_context_builder_all_types():
    from linker_agent.ingestion.model_parser import parse_common_model_file
    from linker_agent.ingestion.context_builder import build_context
    records = parse_common_model_file(INPUT_PATH)
    for r in records:
        ctx = build_context(r)
        assert ctx.technical_description, (
            f"Empty technical_description for {r.asset_id}"
        )
        assert ctx.enrichment_hint, (
            f"Empty enrichment_hint for {r.asset_id}"
        )
        assert ctx.suggested_classification, (
            f"Empty classification for {r.asset_id}"
        )


# ---------------------------------------------------------------------------
# Test 6: Event log writes on enrichment (using mock Alation client)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_event_log_written():
    from linker_agent.ingestion.model_parser import parse_common_model_file
    from linker_agent.core.event_log_service import get_events_for_asset, clear_events
    from linker_agent.core.asset_matcher_service import AssetMatcherService
    from linker_agent.models.asset_record import AssetRecord, AssetType, AssetContext

    clear_events()

    # Build a minimal mock SwaggerAPIClient that returns empty column metadata
    mock_client = MagicMock()
    mock_client.get_terms = AsyncMock(return_value=[])
    mock_client.get_columns_batch = AsyncMock(return_value={})
    mock_client.get_tables_batch = AsyncMock(return_value={})
    mock_client.get_all_columns = AsyncMock(return_value=[])
    mock_client.get_schema_by_id = AsyncMock(return_value={})

    records = parse_common_model_file(INPUT_PATH)[:5]

    service = AssetMatcherService(swagger_client=mock_client)

    # Override _build_lookup to use mocked LLM client (no LLM)
    from linker_agent.core.column_metadata_lookup import ColumnMetadataLookup

    def mock_build_lookup():
        return ColumnMetadataLookup(
            swagger_client=mock_client,
            llm_client=None,
            confidence_threshold=60,
            glossary_id=1,
            enrich_descriptions=False,
        )

    service._build_lookup = mock_build_lookup

    await service.enrich_batch(records)

    for r in records:
        events = get_events_for_asset(r.asset_id)
        assert len(events) >= 1, f"No events for {r.asset_id}"


# ---------------------------------------------------------------------------
# Test 6b: _build_column_context injects technical_description into 'description'
# ---------------------------------------------------------------------------

def test_build_column_context_injects_context():
    """Verify the context dict passed to ColumnMetadataLookup carries technical_description."""
    from linker_agent.ingestion.model_parser import parse_common_model_file
    from linker_agent.ingestion.context_builder import build_context
    from linker_agent.core.asset_matcher_service import AssetMatcherService
    from unittest.mock import MagicMock

    records = parse_common_model_file(INPUT_PATH)

    # Find a calculation (CAGR or similar)
    calc = next(r for r in records if r.asset_type == "calculation")

    mock_client = MagicMock()
    service = AssetMatcherService(swagger_client=mock_client)

    ctx = build_context(calc)
    col_ctx = service._build_column_context(calc, ctx)

    # description must carry the DAX/semantic context, not be empty
    assert col_ctx['description'], "description key must not be empty"
    assert col_ctx['description'] == ctx.technical_description
    # technical_description for a calculation must reference the asset name
    assert calc.name in col_ctx['description']
    # table_name must be the dashboard/model name, not empty
    assert col_ctx['table_name'] == calc.context.model_name
    assert col_ctx['table_name'] != ''
    # schema_name must be the source tool
    assert col_ctx['schema_name'] == 'powerbi'


# ---------------------------------------------------------------------------
# Test 6c: get_business_metadata_with_context passes context to LLM prompt
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_context_reaches_llm_prompt():
    """
    Verify that the LLM receives the full EnrichmentContext in its prompt,
    not just a bare name string.
    """
    from linker_agent.core.column_metadata_lookup import ColumnMetadataLookup

    captured_prompts = []

    # Mock LLM client that records the prompt it receives
    class CapturingAgent:
        async def run(self, prompt):
            captured_prompts.append(prompt)
            class R:
                text = '{"matched": false}'
            return R()

    class CapturingLLM:
        def create_agent(self, name, instructions):
            return CapturingAgent()

    mock_client = MagicMock()
    # Return one dummy term so get_business_metadata_with_context proceeds to Tier 2
    mock_client.get_terms = AsyncMock(return_value=[
        {"id": 1, "title": "Compound Annual Growth Rate", "description": "CAGR metric"}
    ])
    mock_client.get_columns_batch = AsyncMock(return_value={})
    mock_client.get_tables_batch = AsyncMock(return_value={})
    mock_client.get_all_columns = AsyncMock(return_value=[])

    lookup = ColumnMetadataLookup(
        swagger_client=mock_client,
        llm_client=CapturingLLM(),
        confidence_threshold=60,
        glossary_id=1,
    )

    column_context = {
        'name': 'CAGR (%)',
        'description': "Calculation 'CAGR (%)'. Semantic type: growth_rate. DAX: DIVIDE([End Value],[Start Value])",
        'table_name': 'Tru Secure CreDebit Dashboard',
        'table_description': 'Appears on 3 report page(s): Overview, Trends, Summary.',
        'table_type': 'calculation',
        'schema_name': 'powerbi',
        'schema_description': 'Dashboard: Tru Secure CreDebit Dashboard. Source tool: powerbi.',
    }

    await lookup.get_business_metadata_with_context('CAGR (%)', column_context)

    assert len(captured_prompts) > 0, "LLM was never called"
    prompt = captured_prompts[0]
    assert 'growth_rate' in prompt, "semantic type missing from LLM prompt"
    assert 'DIVIDE' in prompt or 'DAX' in prompt, "DAX expression missing from LLM prompt"
    assert 'Tru Secure' in prompt, "dashboard name missing from LLM prompt"


# ---------------------------------------------------------------------------
# Test 7: make_stable_id produces expected format
# ---------------------------------------------------------------------------

def test_make_stable_id_format():
    from linker_agent.ingestion.model_parser import make_stable_id
    result = make_stable_id("powerbi", "Tru Secure CreDebit Dashboard", "calc", "CAGR (%)")
    assert result.startswith("powerbi::")
    assert "calc" in result
    assert "::" in result
    # Ensure no special characters outside slugs
    parts = result.split("::")
    for part in parts:
        assert part == part.lower()
        assert ' ' not in part


# ---------------------------------------------------------------------------
# Test 8: infer_source_tool handles null root and falls back to calc expressions
# ---------------------------------------------------------------------------

def test_infer_source_tool_from_calculations():
    from linker_agent.ingestion.model_parser import infer_source_tool
    model = {
        'source_tool': None,
        'calculations': [
            {'expressions': {'dax': 'SUM(Table[Column])'}}
        ],
        'visualizations': {'pages': []}
    }
    assert infer_source_tool(model) == 'powerbi'


def test_infer_source_tool_from_visuals():
    from linker_agent.ingestion.model_parser import infer_source_tool
    model = {
        'source_tool': None,
        'calculations': [],
        'visualizations': {
            'pages': [{'visuals': [{'source_tool': 'tableau'}]}]
        }
    }
    assert infer_source_tool(model) == 'tableau'


def test_infer_source_tool_unknown():
    from linker_agent.ingestion.model_parser import infer_source_tool
    assert infer_source_tool({}) == 'unknown'


# ---------------------------------------------------------------------------
# Test 9: backward-compat wrapper converts strings to AssetRecords
# ---------------------------------------------------------------------------

def test_column_names_to_assets():
    from linker_agent.api.routes.column_route import _column_names_to_assets
    from linker_agent.models.asset_record import AssetType
    assets = _column_names_to_assets(["Total Premium", "policy_id"])
    assert len(assets) == 2
    assert all(a.asset_type == AssetType.COLUMN for a in assets)
    assert assets[0].asset_id == "legacy_col::total_premium"
    assert assets[1].name == "policy_id"
