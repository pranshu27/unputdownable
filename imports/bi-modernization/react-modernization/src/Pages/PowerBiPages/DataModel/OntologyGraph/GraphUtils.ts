import { Node, Edge } from '@xyflow/react';
import { Table, Relationship, Calculation, KpiLineageItem } from '../../../../data/sampleModel.ts';

// ── Colour config per table_type ──────────────────────────────────
export const TABLE_TYPE_COLORS: Record<string, { border: string; glow: string; badge: string; bg: string }> = {
  fact: {
    border: '#C8102E',
    glow: 'rgba(200, 16, 46, 0.24)',
    badge: '#C8102E',
    bg: 'rgba(200, 16, 46, 0.06)',
  },
  dimension: {
    border: '#003087',
    glow: 'rgba(0, 48, 135, 0.22)',
    badge: '#003087',
    bg: 'rgba(0, 48, 135, 0.06)',
  },
  lookup: {
    border: '#64748B',
    glow: 'rgba(100, 116, 139, 0.2)',
    badge: '#64748B',
    bg: 'rgba(100, 116, 139, 0.06)',
  },
  kpi: {
    border: '#10B981',
    glow: 'rgba(16, 185, 129, 0.24)',
    badge: '#059669',
    bg: 'rgba(16, 185, 129, 0.06)',
  },
};

// Default fallback for unknown table types
const DEFAULT_COLORS = {
  border: '#475569',
  glow: 'rgba(71, 85, 105, 0.18)',
  badge: '#475569',
  bg: 'rgba(71, 85, 105, 0.06)',
};

export function getTableTypeColors(tableType: string) {
  return TABLE_TYPE_COLORS[tableType?.toLowerCase()] || DEFAULT_COLORS;
}

const normalize = (s: string | null | undefined): string =>
  (s == null ? '' : String(s)).toLowerCase().replace(/[^a-z0-9]/g, '');

export function doesTableBelongToSource(t: any, src: any): boolean {
  if (!t || !src) return false;
  
  // 1. Direct ID/Name matching
  if (src.id && (t.source_data_source_id === src.id || t.data_source_id === src.id || t.source_id === src.id)) return true;
  if (t.data_source?.name === src.name || t.source === src.name || t.source_name === src.name) return true;

  // 2. Fallback to string matching
  const srcNorm = normalize(src.name)
    .replace(".csv", "")
    .replace(/\./g, "")
    .replace(/_/g, "");
    
  const tableNorm = normalize(t.name)
    .replace(/\./g, "")
    .replace(/_/g, "");

  return srcNorm.includes(tableNorm) || tableNorm.includes(srcNorm);
}

// ── Normalise table-id coming from relationships ─────────────────
// Relationship left/right_table_id uses "tbl_" prefix + snake_case of table name.
// Table.id is the raw id. We need to map between them.
export function normaliseRelTableId(relId: string): string {
  if (!relId) return '';
  // Remove tbl_ prefix
  return relId.replace(/^tbl_/, '');
}

// Build a map from normalised relationship table id -> actual table id
export function buildTableIdMap(tables: Table[]): Map<string, Table> {
  const map = new Map<string, Table>();
  tables.forEach((t) => {
    // Direct match by id
    map.set(t.id, t);
    // Also index by snake_case version of the name (used in relationships)
    const snakeName = t.name.toLowerCase().replace(/\s+/g, '_');
    map.set(snakeName, t);
    // Also index by id lowercased
    map.set(t.id.toLowerCase(), t);
  });
  return map;
}

export function resolveTableFromRelId(relTableId: string, tableMap: Map<string, Table>): Table | undefined {
  if (!relTableId) return undefined;
  const normalised = normaliseRelTableId(relTableId);
  return tableMap.get(normalised) || tableMap.get(normalised.toLowerCase());
}

// ── Cardinality formatting ───────────────────────────────────────
export function formatCardinality(cardinality: string): string {
  switch (cardinality) {
    case 'many_to_one': return 'N : 1';
    case 'one_to_many': return '1 : N';
    case 'one_to_one': return '1 : 1';
    case 'many_to_many': return 'N : N';
    default: return cardinality || '';
  }
}

// ── Derive relationship label from relationship_type ─────────────
export function getRelationshipLabel(rel: Relationship): string {
  switch (rel.relationship_type) {
    case 'dimension_lookup': return 'belongs_to';
    case 'date_relationship': return 'linked_to';
    case 'sourced_from': return 'sourced_from';
    default: return 'contains';
  }
}

// ── Count relationships for a table ──────────────────────────────
export function countRelationships(tableId: string, relationships: Relationship[], tableMap: Map<string, Table>): number {
  return relationships.filter((r) => {
    if (!r.right_table_id) return false;
    const leftTable = resolveTableFromRelId(r.left_table_id, tableMap);
    const rightTable = resolveTableFromRelId(r.right_table_id, tableMap);
    return leftTable?.id === tableId || rightTable?.id === tableId;
  }).length;
}

// ── Related calculations for a table ─────────────────────────────
export function getRelatedCalculations(tableName: string, calculations: Calculation[]): Calculation[] {
  return calculations.filter((calc) =>
    calc.depends_on_columns.some((col) => col.startsWith(tableName + '.'))
  );
}

// ── Related KPI lineage for a table ──────────────────────────────
export function getRelatedKpiLineage(tableName: string, kpiLineage: KpiLineageItem[]): KpiLineageItem[] {
  if (!kpiLineage) return [];
  return kpiLineage.filter((kpi) =>
    kpi.depends_on_columns?.some((col) => col.table_name === tableName)
  );
}

// ── Radial layout computation ────────────────────────────────────
// Places fact tables in center, dimensions in inner ring, lookups in outer ring
interface LayoutConfig {
  centerX: number;
  centerY: number;
  innerRadius: number;
  outerRadius: number;
}

export function computeRadialLayout(
  tables: Table[],
  relationships: Relationship[],
  config: LayoutConfig = { centerX: 0, centerY: 0, innerRadius: 350, outerRadius: 650 }
): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>();

  const factTables = tables.filter((t) => t.table_type === 'fact');
  const dimensionTables = tables.filter((t) => t.table_type === 'dimension');
  const lookupTables = tables.filter((t) => t.table_type === 'lookup');
  const otherTables = tables.filter(
    (t) => t.table_type !== 'fact' && t.table_type !== 'dimension' && t.table_type !== 'lookup'
  );

  // Place fact tables at center (spread slightly if multiple)
  factTables.forEach((t, i) => {
    const angle = (2 * Math.PI * i) / Math.max(factTables.length, 1);
    const spreadRadius = factTables.length > 1 ? 120 : 0;
    positions.set(t.id, {
      x: config.centerX + Math.cos(angle) * spreadRadius,
      y: config.centerY + Math.sin(angle) * spreadRadius,
    });
  });

  // Dimension tables in inner ring
  const allDimAndOther = [...dimensionTables, ...otherTables];
  allDimAndOther.forEach((t, i) => {
    const angle = (2 * Math.PI * i) / allDimAndOther.length - Math.PI / 2;
    positions.set(t.id, {
      x: config.centerX + Math.cos(angle) * config.innerRadius,
      y: config.centerY + Math.sin(angle) * config.innerRadius,
    });
  });

  // Lookup tables in outer ring
  lookupTables.forEach((t, i) => {
    const angle = (2 * Math.PI * i) / Math.max(lookupTables.length, 1) - Math.PI / 4;
    positions.set(t.id, {
      x: config.centerX + Math.cos(angle) * config.outerRadius,
      y: config.centerY + Math.sin(angle) * config.outerRadius,
    });
  });

  return positions;
}

// ── Build React Flow nodes ───────────────────────────────────────
export function buildNodes(
  tables: Table[],
  relationships: Relationship[],
  calculations: Calculation[],
  positions: Map<string, { x: number; y: number }>
): Node[] {
  const tableMap = buildTableIdMap(tables);

  return tables.map((table) => {
    const pos = positions.get(table.id) || { x: 0, y: 0 };
    const relCount = countRelationships(table.id, relationships, tableMap);
    const colors = getTableTypeColors(table.table_type);

    return {
      id: table.id,
      type: 'ontologyNode',
      position: pos,
      data: {
        table,
        tableName: table.name,
        tableType: table.table_type,
        columnCount: table.columns?.length || 0,
        relationshipCount: relCount,
        colors,
        description: table.description,
      },
    };
  });
}

// ── Build React Flow edges ───────────────────────────────────────
export function buildEdges(
  relationships: Relationship[],
  tables: Table[]
): Edge[] {
  const tableMap = buildTableIdMap(tables);

  return relationships
    .filter((rel) => {
      // Skip date relationships with no right table
      if (!rel.right_table_id) return false;
      const leftTable = resolveTableFromRelId(rel.left_table_id, tableMap);
      const rightTable = resolveTableFromRelId(rel.right_table_id, tableMap);
      return leftTable && rightTable;
    })
    .map((rel) => {
      const leftTable = resolveTableFromRelId(rel.left_table_id, tableMap)!;
      const rightTable = resolveTableFromRelId(rel.right_table_id, tableMap)!;
      const label = getRelationshipLabel(rel);
      const cardinality = formatCardinality(rel.cardinality);

      return {
        id: rel.id,
        source: leftTable.id,
        target: rightTable.id,
        type: 'ontologyEdge',
        animated: true,
        data: {
          relationship: rel,
          label: `${label}`,
          cardinality,
          leftColumn: rel.left_column,
          rightColumn: rel.right_column,
          joinType: rel.join_type,
          filterDirection: rel.filter_direction,
          sourceTableName: leftTable.name,
          targetTableName: rightTable.name,
        },
      };
    });
}
