import React, { useState, useCallback, useMemo, useRef, useEffect } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  BackgroundVariant,
  Node,
  Edge,
  Panel,
  ReactFlowProvider,
  useReactFlow,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import CustomNode from './CustomNode.tsx';
import CustomEdge from './CustomEdge.tsx';
import GraphDrawer from './GraphDrawer.tsx';
import {
  buildNodes,
  buildEdges,
  computeRadialLayout,
  buildTableIdMap,
  resolveTableFromRelId,
  TABLE_TYPE_COLORS,
  getTableTypeColors,
  doesTableBelongToSource,
} from './GraphUtils.ts';
import { DataModel, Table } from '../../../../data/sampleModel.ts';
import { cn } from '../../../../Lib/utils.ts';

import './OntologyGraph.css';

const nodeTypes = { ontologyNode: CustomNode };
const edgeTypes = { ontologyEdge: CustomEdge };

const normalizeId = (s: string) => {
  if (!s) return '';
  return s
    .toLowerCase()
    .replace(/^(tbl|col|mea|calc|kpi|src|ds)[-_]/, '')
    .replace(/\.csv$/, '')
    .replace(/[^a-z0-9]/g, '');
};

interface RelationshipGraphProps {
  dataModel: DataModel;
  graphExpanded?: boolean;
}

const RelationshipGraphInner: React.FC<RelationshipGraphProps> = ({ dataModel, graphExpanded = true }) => {
  const { fitView } = useReactFlow();

  const { relationships, calculations, kpi_lineage } = dataModel;

  const tables = useMemo(() => {
    const tableMap = buildTableIdMap(dataModel.tables || []);
    const relatedIds = new Set<string>();

    relationships.forEach((rel) => {
      const leftTable = resolveTableFromRelId(rel.left_table_id, tableMap);
      const rightTable = resolveTableFromRelId(rel.right_table_id, tableMap);
      if (leftTable?.id) relatedIds.add(leftTable.id);
      if (rightTable?.id) relatedIds.add(rightTable.id);
    });

    return (dataModel.tables || []).filter((table: any) => {
      const type = String(table.table_type || table.type || '').toLowerCase();
      const isRealTable = Array.isArray(table.columns) && !['calculation', 'measure', 'kpi'].includes(type);
      if (!isRealTable) return false;
      return relatedIds.size === 0 || relatedIds.has(table.id);
    });
  }, [dataModel.tables, relationships]);

  // ── Search + Filter state ────────────────────────────────────────
  const [searchTerm, setSearchTerm] = useState('');
  const [activeFilters, setActiveFilters] = useState<Set<string>>(new Set());
  const [showDepsOnly, setShowDepsOnly] = useState(false);
  const [selectedTableId, setSelectedTableId] = useState<string | null>(null);
  const [highlightedItem, setHighlightedItem] = useState<{ id: string; category: string; label: string } | null>(null);
  const [selectedDataSourceId, setSelectedDataSourceId] = useState<string | null>(null);
  const [focusedTableIds, setFocusedTableIds] = useState<Set<string> | null>(null);

  // ── Drawer state ─────────────────────────────────────────────────
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTable, setDrawerTable] = useState<Table | null>(null);
  const [drawerEdgeData, setDrawerEdgeData] = useState<any>(null);
  const [drawerMode, setDrawerMode] = useState<'node' | 'edge'>('node');

  // ── Resize state ─────────────────────────────────────────────────
  const [drawerHeight, setDrawerHeight] = useState(280);
  const resizeRef = useRef<{ startY: number; startH: number } | null>(null);

  const onResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    resizeRef.current = { startY: e.clientY, startH: drawerHeight };

    const onMove = (ev: MouseEvent) => {
      if (!resizeRef.current) return;
      const delta = ev.clientY - resizeRef.current.startY;
      const newH = Math.max(150, Math.min(550, resizeRef.current.startH - delta));
      setDrawerHeight(newH);
    };

    const onUp = () => {
      resizeRef.current = null;
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };

    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }, [drawerHeight]);

  // ── Build filtered tables ────────────────────────────────────────
  const filteredTables = useMemo(() => {
    let result = tables;

    // Filter by selected Data Source
    if (selectedDataSourceId) {
      const foundDs = dataModel.data_sources?.find((d: any) => d.id === selectedDataSourceId);
      if (foundDs) {
        result = result.filter(t => doesTableBelongToSource(t, foundDs));
      }
    }

    // Filter by type
    if (activeFilters.size > 0) {
      result = result.filter((t) => activeFilters.has(t.table_type));
    }

    // Filter by search
    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase();
      result = result.filter((t) =>
        t.name.toLowerCase().includes(term) ||
        t.table_type.toLowerCase().includes(term)
      );
    }

    // Local toolbar dependency filter. Global search keeps the graph mounted and dims unrelated nodes.
    if (showDepsOnly && selectedTableId && !focusedTableIds) {
      const tableMap = buildTableIdMap(tables);
      const depIds = new Set<string>();
      depIds.add(selectedTableId);

      relationships.forEach((rel) => {
        if (!rel.right_table_id) return;
        const leftTable = resolveTableFromRelId(rel.left_table_id, tableMap);
        const rightTable = resolveTableFromRelId(rel.right_table_id, tableMap);
        if (leftTable?.id === selectedTableId && rightTable) depIds.add(rightTable.id);
        if (rightTable?.id === selectedTableId && leftTable) depIds.add(leftTable.id);
      });

      result = result.filter((t) => depIds.has(t.id));
    }

    return result;
  }, [tables, activeFilters, searchTerm, showDepsOnly, selectedTableId, relationships, selectedDataSourceId, focusedTableIds]);

  // ── Compute layout ───────────────────────────────────────────────
  const positions = useMemo(
    () => computeRadialLayout(filteredTables, relationships),
    [filteredTables, relationships]
  );

  // ── Build nodes & edges ──────────────────────────────────────────
  const initialNodes = useMemo(
    () => buildNodes(filteredTables, relationships, calculations, positions),
    [filteredTables, relationships, calculations, positions]
  );
  const initialEdges = useMemo(
    () => buildEdges(relationships, filteredTables),
    [relationships, filteredTables]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  useEffect(() => {
    if (selectedTableId || focusedTableIds) return;
    setNodes(initialNodes);
    setEdges(initialEdges);
    window.requestAnimationFrame(() => {
      fitView({ padding: 0.24, duration: 650, includeHiddenNodes: false });
    });
  }, [initialNodes, initialEdges, selectedTableId, focusedTableIds, setNodes, setEdges, fitView]);

  // Highlight search target
  const highlightTarget = useCallback((target: any) => {
    const targetId = target?.id || '';
    const category = target?.category || '';
    const label = target?.label || '';
    
    const normTarget = normalizeId(targetId);
    const normLabel = normalizeId(label);

    let targetTableId: string | null = null;
    const targetTableIds = new Set<string>();
    let isDataSource = false;

    if (category === 'Tables') {
      const found = tables.find(t => 
        t.id === target?.tableId ||
        normalizeId(t.id) === normTarget || 
        normalizeId(t.name) === normLabel || 
        normalizeId(t.id) === normLabel
      );
      if (found) {
        targetTableId = found.id;
        targetTableIds.add(found.id);
      }
    } else if (category === 'Columns') {
      const found = tables.find(t =>
        t.id === target?.tableId ||
        t.columns?.some((col: any) => normalizeId(col.name) === normLabel)
      );
      if (found) {
        targetTableId = found.id;
        targetTableIds.add(found.id);
      }
    } else if (category === 'Measures') {
      const foundCalc = calculations.find(c => 
        normalizeId(c.id) === normTarget || 
        normalizeId(c.name) === normLabel || 
        normalizeId(c.id) === normLabel
      );
      if (foundCalc) {
        const found = tables.find(t =>
          t.id === target?.tableId ||
          normalizeId(t.name) === normalizeId(foundCalc.table_name) ||
          normalizeId(t.id) === normalizeId(foundCalc.table_name)
        );
        if (found) {
          targetTableId = found.id;
          targetTableIds.add(found.id);
        }
      }
    } else if (category === 'KPIs') {
      const foundKpi = kpi_lineage.find(k => 
        normalizeId(k.kpi_name) === normTarget || 
        normalizeId(k.kpi_name) === normLabel || 
        normalizeId(k.kpi_id) === normTarget
      );
      if (foundKpi && foundKpi.depends_on_columns?.length) {
        foundKpi.depends_on_columns.forEach((dep: any) => {
          const found = tables.find(t => normalizeId(t.name) === normalizeId(dep.table_name) || normalizeId(t.id) === normalizeId(dep.table_name));
          if (found) {
            targetTableIds.add(found.id);
            if (!targetTableId) targetTableId = found.id;
          }
        });
      }
    } else if (category === 'Data Sources') {
      isDataSource = true;
      const foundDs = dataModel.data_sources?.find((d: any) => 
        d.id === target?.sourceId ||
        normalizeId(d.id) === normTarget || 
        normalizeId(d.name) === normLabel || 
        normalizeId(d.id) === normLabel
      );
      if (foundDs) {
        tables.forEach(t => {
          if (doesTableBelongToSource(t, foundDs)) {
            targetTableIds.add(t.id);
            if (!targetTableId) targetTableId = t.id;
          }
        });
      }
    }

    // Reset standard category filters to ensure selected table is rendered
    setActiveFilters(new Set());
    setSearchTerm('');
    setSelectedDataSourceId(null);
    setShowDepsOnly(false);

    if (isDataSource) {
      // Data Sources do not have a physical table node on ReactFlow canvas, but we still open details panel!
      setSelectedTableId(null);
      setFocusedTableIds(targetTableIds.size > 0 ? targetTableIds : null);
      setHighlightedItem({ id: targetId, category, label });
      setDrawerTable(null);
      setDrawerEdgeData(null);
      setDrawerMode('node');
      setDrawerOpen(true);

      if (targetTableIds.size > 0) {
        setTimeout(() => {
          fitView({
            nodes: Array.from(targetTableIds).map((id) => ({ id } as any)),
            duration: 800,
            padding: 0.35,
          });
        }, 150);
      }
      return;
    }

    if (!targetTableId) return;

    setSelectedTableId(targetTableId);
    setFocusedTableIds(targetTableIds);
    setHighlightedItem({ id: targetId, category, label });

    const tableObj = tables.find(t => t.id === targetTableId);
    if (tableObj) {
      setDrawerTable(tableObj);
      setDrawerEdgeData(null);
      setDrawerMode('node');
      setDrawerOpen(true);
    }

    // Fit view after small delay so React Flow has node positions ready
    setTimeout(() => {
      fitView({
        nodes: Array.from(targetTableIds).map((id) => ({ id } as any)),
        duration: 800,
        padding: 0.35,
      });
    }, 150);
  }, [tables, relationships, calculations, kpi_lineage, dataModel.data_sources, setSelectedTableId, fitView]);

  // ── Declarative Nodes & Edges Sync Effect ────────────────────────
  useEffect(() => {
    const activeKpi = highlightedItem?.category === 'KPIs'
      ? kpi_lineage.find(k => k.kpi_name === highlightedItem.label || k.kpi_id === highlightedItem.id)
      : null;

    if (activeKpi) {
      const kpiNodeId = `kpi-node-${activeKpi.kpi_name}`;

      // Determine position (180px above its first dependent table)
      let kpiNodePosition = { x: 0, y: -200 };
      if (activeKpi.depends_on_columns?.length) {
        const firstDepTable = tables.find(t => 
          normalizeId(t.name) === normalizeId(activeKpi.depends_on_columns[0].table_name) || 
          normalizeId(t.id) === normalizeId(activeKpi.depends_on_columns[0].table_name)
        );
        if (firstDepTable) {
          const pos = positions.get(firstDepTable.id);
          if (pos) {
            kpiNodePosition = { x: pos.x, y: pos.y - 180 };
          }
        }
      }

      // Build KPI satellite node
      const kpiNode: Node = {
        id: kpiNodeId,
        type: 'ontologyNode',
        position: kpiNodePosition,
        selected: true,
        data: {
          tableName: activeKpi.kpi_name,
          tableType: 'kpi',
          columnCount: 0,
          relationshipCount: activeKpi.depends_on_columns?.length || 0,
          colors: getTableTypeColors('kpi'),
          description: activeKpi.description,
          table: null,
          isSearchMatch: true,
        } as any
      };

      // Build dependency edges
      const kpiEdges: Edge[] = [];
      const connectedTableIds = new Set<string>();

      activeKpi.depends_on_columns.forEach((dep: any, idx: number) => {
        const depTable = tables.find(t => 
          normalizeId(t.name) === normalizeId(dep.table_name) || 
          normalizeId(t.id) === normalizeId(dep.table_name)
        );
        if (depTable) {
          connectedTableIds.add(depTable.id);
          kpiEdges.push({
            id: `kpi-edge-${activeKpi.kpi_name}-${depTable.id}-${idx}`,
            source: kpiNodeId,
            target: depTable.id,
            type: 'ontologyEdge',
            animated: true,
            style: { stroke: '#10B981', strokeWidth: 2, strokeDasharray: '5 5' },
            data: {
              relationship: null,
              label: 'references',
              cardinality: '',
              leftColumn: '',
              rightColumn: dep.column_name,
              joinType: 'kpi_ref',
              filterDirection: 'none',
              sourceTableName: activeKpi.kpi_name,
              targetTableName: depTable.name,
            } as any
          });
        }
      });

      // Update ReactFlow nodes state (dim other nodes)
      setNodes([
        kpiNode,
        ...initialNodes.map(node => ({
          ...node,
          selected: false,
          data: {
            ...node.data,
            isDimmed: !connectedTableIds.has(node.id),
            isSearchMatch: connectedTableIds.has(node.id),
          },
        }))
      ]);

      // Update ReactFlow edges state (dim other edges)
      setEdges([
        ...kpiEdges,
        ...initialEdges.map(edge => ({
          ...edge,
          selected: false,
          data: {
            ...edge.data,
            isDimmed: true,
          },
        }))
      ]);

      // Focus view on the KPI node and its dependencies
      setTimeout(() => {
        fitView({
          nodes: [{ id: kpiNodeId }, ...Array.from(connectedTableIds).map(id => ({ id }))],
          duration: 700,
          padding: 0.35,
        });
      }, 100);

    } else if (!selectedTableId && !focusedTableIds) {
      setNodes(initialNodes);
      setEdges(initialEdges);
    } else {
      const tableMap = buildTableIdMap(tables);
      const baseFocusIds = new Set<string>(focusedTableIds || (selectedTableId ? [selectedTableId] : []));
      const connectedTableIds = new Set<string>(baseFocusIds);
      const connectedEdgeIds = new Set<string>();

      const isDataSource = highlightedItem?.category === 'Data Sources';

      relationships.forEach(rel => {
        if (!rel.right_table_id) return;
        const leftTable = resolveTableFromRelId(rel.left_table_id, tableMap);
        const rightTable = resolveTableFromRelId(rel.right_table_id, tableMap);
        if (leftTable && rightTable) {
          if (isDataSource) {
            // Only highlight edges between tables from the same data source
            if (baseFocusIds.has(leftTable.id) && baseFocusIds.has(rightTable.id)) {
              connectedEdgeIds.add(rel.id);
            }
          } else {
            // Highlight 1st-degree neighbors for tables/measures/KPIs
            if (baseFocusIds.has(leftTable.id) || baseFocusIds.has(rightTable.id)) {
              connectedTableIds.add(rightTable.id);
              connectedTableIds.add(leftTable.id);
              connectedEdgeIds.add(rel.id);
            }
          }
        }
      });

      setNodes(initialNodes.map(node => ({
        ...node,
        selected: node.id === selectedTableId,
        data: {
          ...node.data,
          isDimmed: !connectedTableIds.has(node.id),
          isSearchMatch: node.id === selectedTableId || Boolean(focusedTableIds?.has(node.id)),
        },
      })));

      setEdges(initialEdges.map(edge => {
        const isConnected = connectedEdgeIds.has(edge.id);
        return {
          ...edge,
          selected: isConnected,
          data: {
            ...edge.data,
            isDimmed: !isConnected,
          },
        };
      }));
    }
  }, [selectedTableId, focusedTableIds, initialNodes, initialEdges, tables, relationships, kpi_lineage, highlightedItem, positions, fitView, setNodes, setEdges]);

  // ── Handle incoming search target ────────────────────────
  useEffect(() => {
    const savedTargetStr = localStorage.getItem('jnj:search-target');
    if (savedTargetStr) {
      try {
        const saved = JSON.parse(savedTargetStr);
        localStorage.removeItem('jnj:search-target');
        highlightTarget(saved);
      } catch (e) {
        console.error('Error parsing search target from localStorage:', e);
      }
    } else if (!selectedTableId) {
      setTimeout(() => fitView({ padding: 0.2, duration: 600 }), 100);
    }
  }, [initialNodes, initialEdges, fitView, highlightTarget, selectedTableId]);

  // Listen to custom search event
  useEffect(() => {
    const handleSearchSelect = (e: Event) => {
      const customEvent = e as CustomEvent;
      if (customEvent.detail) {
        const item = customEvent.detail;
        highlightTarget(item);
      }
    };

    window.addEventListener('jnj:search-select', handleSearchSelect);
    return () => {
      window.removeEventListener('jnj:search-select', handleSearchSelect);
    };
  }, [highlightTarget]);

  // ── Node click → open drawer ─────────────────────────────────────
  const onNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      const table = tables.find((t) => t.id === node.id);
      if (table) {
        setDrawerTable(table);
        setDrawerEdgeData(null);
        setDrawerMode('node');
        setDrawerOpen(true);
        setSelectedTableId(table.id);
        setHighlightedItem(null); // Clear search highlight on manual click
        setFocusedTableIds(null);
      }
    },
    [tables, setSelectedTableId, setDrawerTable, setDrawerEdgeData, setDrawerMode, setDrawerOpen, setHighlightedItem, setFocusedTableIds]
  );

  // ── Edge click → open relationship popup ─────────────────────────
  const onEdgeClick = useCallback(
    (_event: React.MouseEvent, edge: Edge) => {
      setDrawerEdgeData(edge.data);
      setDrawerTable(null);
      setDrawerMode('edge');
      setDrawerOpen(true);
    },
    [setDrawerEdgeData, setDrawerTable, setDrawerMode, setDrawerOpen]
  );

  // ── Filter toggles ──────────────────────────────────────────────
  const toggleFilter = (type: string) => {
    setActiveFilters((prev) => {
      const next = new Set(prev);
      if (next.has(type)) {
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  };

  const clearFilters = useCallback(() => {
    setActiveFilters(new Set());
    setSearchTerm('');
    setShowDepsOnly(false);
    setSelectedTableId(null);
    setHighlightedItem(null);
    setSelectedDataSourceId(null);
    setFocusedTableIds(null);
  }, [setActiveFilters, setSearchTerm, setShowDepsOnly, setSelectedTableId, setHighlightedItem, setSelectedDataSourceId, setFocusedTableIds]);

  // ── Minimap colour ──────────────────────────────────────────────
  const minimapNodeColor = (node: Node) => {
    const tableType = (node.data as any)?.tableType;
    return getTableTypeColors(tableType)?.border || '#64748b';
  };

  return (
    <div className="ontology-graph-container">
      {/* ── Top Toolbar ─────────────────────────────────────────────── */}
      {graphExpanded && (
        <div className="ontology-toolbar" style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-start', padding: '8px 16px', background: '#fff', borderBottom: '1px solid #e2e8f0', width: '100%' }}>
        {/* Filter buttons */}
        <div className="ontology-filters" style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          {['fact', 'dimension', 'lookup'].map((type) => {
            const colors = TABLE_TYPE_COLORS[type];
            const isActive = activeFilters.has(type);
            return (
              <button
                key={type}
                className={`ontology-filter-btn ${isActive ? 'ontology-filter-btn--active' : ''}`}
                onClick={() => toggleFilter(type)}
                style={isActive ? { borderColor: colors.border, color: colors.border, backgroundColor: `${colors.border}15` } : {}}
              >
                <span className="ontology-filter-dot" style={{ backgroundColor: colors.border }} />
                {type.charAt(0).toUpperCase() + type.slice(1)}
              </button>
            );
          })}

          {selectedTableId && (
            <button
              className={`ontology-filter-btn ${showDepsOnly ? 'ontology-filter-btn--active' : ''}`}
              onClick={() => setShowDepsOnly(!showDepsOnly)}
              style={showDepsOnly ? { borderColor: '#818CF8', color: '#818CF8', backgroundColor: 'rgba(129,140,248,0.15)' } : {}}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" /><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" /></svg>
              Deps Only
            </button>
          )}
          {(activeFilters.size > 0 || searchTerm || showDepsOnly || highlightedItem) && (
            <button className="ontology-filter-btn ontology-filter-btn--clear" onClick={clearFilters}>
              Reset search
            </button>
          )}
        </div>
        </div>
      )}

      {/* ── React Flow Canvas ───────────────────────────────────────── */}
      <div className={cn("ontology-canvas", !graphExpanded && "hidden")} style={{ flex: 1, position: 'relative' }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          onEdgeClick={onEdgeClick}
          onPaneClick={clearFilters}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          minZoom={0.1}
          maxZoom={2.5}
          defaultEdgeOptions={{
            type: 'ontologyEdge',
            animated: true,
          }}
          proOptions={{ hideAttribution: true }}
        >
          <Background
            variant={BackgroundVariant.Dots}
            gap={24}
            size={1.5}
            color="rgba(100, 116, 139, 0.15)"
          />
          <Panel position="bottom-left">
            <div style={{ padding: "8px" }}>
              {/* Legend */}
              <div className="ontology-legend">
                <span className="ontology-legend__title">ENTITY TYPES</span>

                <div className="ontology-legend__items">
                  <div className="ontology-legend__item">
                    <span
                      className="ontology-legend__dot"
                      style={{ backgroundColor: "#C8102E" }}
                    />
                    <span className="text-slate-800">Fact Table</span>
                  </div>

                  <div className="ontology-legend__item">
                    <span
                      className="ontology-legend__dot"
                      style={{ backgroundColor: "#003087" }}
                    />
                    <span className="text-slate-800">Dimension Table</span>
                  </div>

                  <div className="ontology-legend__item">
                    <span
                      className="ontology-legend__dot"
                      style={{ backgroundColor: "#64748B" }}
                    />
                    <span className="text-slate-800">Lookup Table</span>
                  </div>

                  <div className="ontology-legend__item">
                    <span
                      className="ontology-legend__dot"
                      style={{ backgroundColor: "#10B981" }}
                    />
                    <span className="text-slate-800">Semantic KPI</span>
                  </div>
                </div>
              </div>
            </div>
          </Panel>

          <Controls
            position="bottom-right"
            showInteractive={false}
            style={{ zIndex: 10, margin: '8px' }}
          />
        </ReactFlow>
      </div>

      {/* ── Resize handle bar (only when drawer is open) ── */}
      {drawerOpen && graphExpanded && (
        <div
          onMouseDown={onResizeStart}
          className="h-1.5 w-full bg-slate-100 hover:bg-slate-300 border-t border-b border-slate-200 cursor-row-resize flex items-center justify-center transition-colors select-none z-20 shrink-0"
          title="Drag to resize inspector panel"
        >
          <div className="w-8 h-1 rounded-full bg-slate-300 group-hover:bg-slate-400" />
        </div>
      )}

      {/* ── Drawer ──────────────────────────────────────────────────── */}
      <GraphDrawer
        isOpen={drawerOpen}
        onClose={() => { setDrawerOpen(false); setHighlightedItem(null); }}
        table={drawerTable}
        calculations={calculations}
        kpiLineage={kpi_lineage}
        relationships={relationships}
        tables={tables}
        dataSources={dataModel.data_sources}
        edgeData={drawerEdgeData}
        mode={drawerMode}
        highlightedItem={highlightedItem}
        height={graphExpanded ? drawerHeight : '100%'}
      />
    </div>
  );
};

// Wrap with ReactFlowProvider
const RelationshipGraph: React.FC<RelationshipGraphProps> = (props) => (
  <ReactFlowProvider>
    <RelationshipGraphInner {...props} />
  </ReactFlowProvider>
);

export default RelationshipGraph;
