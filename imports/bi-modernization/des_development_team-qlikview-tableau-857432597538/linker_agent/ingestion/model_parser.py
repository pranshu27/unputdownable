"""
Parses the RE Common Model JSON into a list of AssetRecord objects.

Handles:
- Non-unique IDs in current model version (generates stable synthetic IDs)
- Missing source_tool at root (inferred from visuals and expression keys)
- Visual-to-asset usage mapping (builds pages_used_on for purpose_statement)
- All asset types: tables, columns, calculations, relationships
"""

from __future__ import annotations
import json
import re
from pathlib import Path

from linker_agent.models.asset_record import (
    AssetContext, AssetRecord, AssetState, AssetType
)


# ---------------------------------------------------------------------------
# ID generation
# ---------------------------------------------------------------------------

def make_stable_id(source_tool: str, model_name: str, asset_type: str, *parts: str) -> str:
    """
    Generate a stable, deterministic asset ID from known-stable attributes.
    Format: {source_tool}::{model_slug}::{asset_type}::{slug_of_parts}

    Examples:
        make_stable_id("powerbi", "Tru Secure CreDebit Dashboard", "calc", "CAGR (%)")
        → "powerbi::tru_secure_credebit_dashboard::calc::cagr_pct"
    """
    def slug(s: str) -> str:
        s = s.lower().strip()
        s = re.sub(r'[^a-z0-9]+', '_', s)
        return s.strip('_')

    parts_slug = '::'.join(slug(p) for p in parts)
    return f"{slug(source_tool)}::{slug(model_name)}::{slug(asset_type)}::{parts_slug}"


# ---------------------------------------------------------------------------
# Source tool inference
# ---------------------------------------------------------------------------

def infer_source_tool(model: dict) -> str:
    """Infer source_tool from model if root field is null."""
    if model.get('source_tool'):
        return model['source_tool']

    for calc in model.get('calculations', []):
        expr_keys = list(calc.get('expressions', {}).keys())
        if 'dax' in expr_keys:
            return 'powerbi'
        if 'tableau' in expr_keys and 'dax' not in expr_keys:
            return 'tableau'
        if 'qlik' in expr_keys and 'dax' not in expr_keys:
            return 'qlik'

    for page in model.get('visualizations', {}).get('pages', []):
        for visual in page.get('visuals', []):
            st = visual.get('source_tool')
            if st:
                return st

    return 'unknown'


# ---------------------------------------------------------------------------
# Visual usage index
# ---------------------------------------------------------------------------

def build_usage_index(model: dict) -> dict[str, list[dict]]:
    """
    Build a mapping from {table_name}.{column_name} → list of {page_name, visual_type}.
    Used to populate AssetContext.pages_used_on and visual_types_used_in.
    """
    usage: dict[str, list[dict]] = {}
    pages = model.get('visualizations', {}).get('pages', [])

    for page in pages:
        page_name = page.get('display_name') or page.get('page_id', 'unknown_page')
        for visual in page.get('visuals', []):
            visual_type = visual.get('visual_type', 'unknown')
            for field in visual.get('fields') or []:
                table = field.get('table', '')
                column = field.get('column', '')
                if table and column:
                    # Strip Power BI date hierarchy suffixes
                    # e.g. "Start Date.Variation.Date Hierarchy.Day" → "Start Date"
                    column_clean = column.split('.')[0].strip()
                    key = f"{table}.{column_clean}"
                    if key not in usage:
                        usage[key] = []
                    usage[key].append({
                        'page': page_name,
                        'visual_type': visual_type
                    })

    return usage


# ---------------------------------------------------------------------------
# Asset type derivation
# ---------------------------------------------------------------------------

SEMANTIC_TYPE_TO_ASSET_TYPE = {
    'sum': AssetType.CALCULATION,
    'count': AssetType.CALCULATION,
    'ratio': AssetType.CALCULATION,
    'growth_rate': AssetType.CALCULATION,
    'average': AssetType.CALCULATION,
    'min': AssetType.CALCULATION,
    'max': AssetType.CALCULATION,
}

SEMANTIC_ROLE_TO_ASSET_TYPE = {
    'primary_key': AssetType.COLUMN,
    'foreign_key': AssetType.COLUMN,
    'dimension': AssetType.DIMENSION,
    'measure': AssetType.MEASURE,
    'date': AssetType.COLUMN,
    'identifier': AssetType.COLUMN,
}


# ---------------------------------------------------------------------------
# Main parse functions
# ---------------------------------------------------------------------------

def parse_calculations(
    model: dict,
    source_tool: str,
    model_name: str,
    model_id: str,
    usage_index: dict,
    technical_summary: str,
) -> list[AssetRecord]:
    """Parse all calculations into AssetRecord objects."""
    records = []

    for calc in model.get('calculations', []):
        name = calc.get('name', '')
        asset_id = make_stable_id(source_tool, model_name, 'calc', name)

        pages_used: list[str] = []
        visual_types: list[str] = []
        for dep_col in calc.get('depends_on_columns', []):
            parts = dep_col.split('.', 1)
            if len(parts) == 2:
                key = f"{parts[0]}.{parts[1]}"
                for entry in usage_index.get(key, []):
                    if entry['page'] not in pages_used:
                        pages_used.append(entry['page'])
                    if entry['visual_type'] not in visual_types:
                        visual_types.append(entry['visual_type'])
        # Also check calculation name directly in usage index
        for table_name in [t['name'] for t in model.get('tables', [])]:
            key = f"{table_name}.{name}"
            for entry in usage_index.get(key, []):
                if entry['page'] not in pages_used:
                    pages_used.append(entry['page'])

        display = calc.get('display', {})

        record = AssetRecord(
            asset_id=asset_id,
            asset_type=SEMANTIC_TYPE_TO_ASSET_TYPE.get(
                calc.get('semantic_type', ''), AssetType.CALCULATION
            ),
            name=name,
            description=calc.get('description'),
            state=AssetState.EXTRACTED,
            attributes={
                'semantic_type': calc.get('semantic_type'),
                'aggregation_behavior': calc.get('aggregation_behavior'),
                'data_type': calc.get('data_type'),
                'format_string': calc.get('format_string'),
                'is_base_measure': calc.get('is_base_measure'),
                'reusable': calc.get('reusable'),
                'expressions': calc.get('expressions', {}),
                'tags': display.get('tags', []),
                'folder': display.get('folder'),
                'hidden': display.get('hidden', False),
            },
            context=AssetContext(
                source_tool=source_tool,
                model_id=model_id,
                model_name=model_name,
                domain=display.get('folder'),
                pages_used_on=pages_used,
                visual_types_used_in=visual_types,
                depends_on_columns=calc.get('depends_on_columns', []),
                depends_on_measures=calc.get('depends_on_measures', []),
                technical_summary=technical_summary,
            )
        )
        records.append(record)

    return records


def parse_columns(
    model: dict,
    source_tool: str,
    model_name: str,
    model_id: str,
    usage_index: dict,
    technical_summary: str,
) -> list[AssetRecord]:
    """Parse all table columns into AssetRecord objects."""
    records = []

    for table in model.get('tables', []):
        table_name = table.get('name', '')
        table_type = table.get('table_type', '')

        for col in table.get('columns', []):
            col_name = col.get('name', '')
            semantic_role = col.get('semantic_role', 'dimension')

            asset_id = make_stable_id(
                source_tool, model_name, 'col', table_name, col_name
            )

            usage_key = f"{table_name}.{col_name}"
            usage_entries = usage_index.get(usage_key, [])
            pages_used = list({e['page'] for e in usage_entries})
            visual_types = list({e['visual_type'] for e in usage_entries})

            asset_type = SEMANTIC_ROLE_TO_ASSET_TYPE.get(
                semantic_role, AssetType.COLUMN
            )

            record = AssetRecord(
                asset_id=asset_id,
                asset_type=asset_type,
                name=col_name,
                description=col.get('description'),
                state=AssetState.EXTRACTED,
                attributes={
                    'data_type': col.get('data_type'),
                    'nullable': col.get('nullable'),
                    'hidden': col.get('hidden'),
                    'semantic_role': semantic_role,
                    'used_in_relationships': col.get('used_in_relationships'),
                    'used_in_filters': col.get('used_in_filters'),
                    'used_in_groupby': col.get('used_in_groupby'),
                    'used_in_calculations': col.get('used_in_calculations'),
                    'distinct_count_high': col.get('distinct_count_high'),
                    'table_name': table_name,
                    'table_type': table_type,
                },
                context=AssetContext(
                    source_tool=source_tool,
                    model_id=model_id,
                    model_name=model_name,
                    table_name=table_name,
                    table_type=table_type,
                    pages_used_on=pages_used,
                    visual_types_used_in=visual_types,
                    technical_summary=technical_summary,
                )
            )
            records.append(record)

    return records


def parse_tables(
    model: dict,
    source_tool: str,
    model_name: str,
    model_id: str,
    technical_summary: str,
) -> list[AssetRecord]:
    """Parse tables as top-level AssetRecord objects."""
    records = []

    for table in model.get('tables', []):
        table_name = table.get('name', '')
        asset_id = make_stable_id(source_tool, model_name, 'table', table_name)

        record = AssetRecord(
            asset_id=asset_id,
            asset_type=AssetType.TABLE,
            name=table_name,
            description=table.get('description'),
            state=AssetState.EXTRACTED,
            attributes={
                'table_type': table.get('table_type'),
                'is_materialized': table.get('is_materialized'),
                'column_count': len(table.get('columns', [])),
                'source_data_source_id': table.get('source_data_source_id'),
            },
            context=AssetContext(
                source_tool=source_tool,
                model_id=model_id,
                model_name=model_name,
                table_name=table_name,
                table_type=table.get('table_type'),
                technical_summary=technical_summary,
            )
        )
        records.append(record)

    return records


def parse_common_model(model: dict) -> list[AssetRecord]:
    """
    Main entry point. Parse a full RE common model dict into AssetRecord list.
    Returns all tables + columns + calculations.

    Usage:
        with open('input1.json') as f:
            model = json.load(f)
        records = parse_common_model(model)
    """
    source_tool = infer_source_tool(model)
    model_name = model.get('name', 'unknown_model')
    model_id = model.get('model_id', '')
    technical_summary = model.get('technical_summary', '')

    usage_index = build_usage_index(model)

    records: list[AssetRecord] = []
    records.extend(parse_tables(model, source_tool, model_name, model_id, technical_summary))
    records.extend(parse_columns(model, source_tool, model_name, model_id, usage_index, technical_summary))
    records.extend(parse_calculations(model, source_tool, model_name, model_id, usage_index, technical_summary))

    return records


def parse_common_model_file(path: str | Path) -> list[AssetRecord]:
    """Convenience wrapper to load from file path."""
    with open(path, 'r', encoding='utf-8') as f:
        model = json.load(f)
    return parse_common_model(model)
