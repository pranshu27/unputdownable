import React, { useMemo, useState, useEffect } from 'react';
import { Table, Calculation, KpiLineageItem, Relationship, DataSource } from '../../../../data/sampleModel.ts';
import { getTableTypeColors, getRelatedCalculations, getRelatedKpiLineage, formatCardinality, getRelationshipLabel, resolveTableFromRelId, buildTableIdMap, doesTableBelongToSource } from './GraphUtils.ts';
import KpiLineageDiagram from '../../../Components/KpiLineageDiagram.tsx';
import { cn } from '../../../../Lib/utils.ts';
import { 
  Database, Info, Columns, Code2, TrendingUp, Sliders, 
  HelpCircle, Link2, X, AlertCircle, FileText, Table2
} from 'lucide-react';

interface GraphDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  table: Table | null;
  calculations: Calculation[];
  kpiLineage: KpiLineageItem[];
  relationships: Relationship[];
  tables: Table[];
  dataSources?: DataSource[];
  edgeData?: any;
  mode: 'node' | 'edge';
  highlightedItem?: { id: string; category: string; label: string } | null;
  height?: number | string;
}

const NAVY = '#003087';
const RED  = '#c8102e';

function cardLabel(c: string): string {
  const M: Record<string, string> = {
    one_to_many: '1:N', many_to_one: 'N:1', many_to_many: 'N:M', one_to_one: '1:1',
  };
  return M[c] ?? c?.replace(/_/g, ':') ?? '—';
}

function fireSelectEvent(payload: { id: string; category: string; label: string; tableId?: string; sourceId?: string }) {
  window.dispatchEvent(new CustomEvent('jnj:search-select', { detail: payload }));
}

const GraphDrawer: React.FC<GraphDrawerProps> = ({
  isOpen,
  onClose,
  table,
  calculations,
  kpiLineage,
  relationships,
  tables,
  dataSources = [],
  edgeData,
  mode,
  highlightedItem,
  height = 280,
}) => {

  const inspector = useMemo(() => {
    if (!isOpen) return null;
    if (highlightedItem) {
      if (highlightedItem.category === 'KPIs') {
        const kpi = kpiLineage.find(k => k.kpi_name === highlightedItem.label || k.kpi_id === highlightedItem.id);
        if (kpi) return { kind: 'kpi' as const, id: kpi.kpi_name };
      }
      if (highlightedItem.category === 'Measures') {
        const calc = calculations.find(c => c.name === highlightedItem.label || c.id === highlightedItem.id);
        if (calc) return { kind: 'measure' as const, id: calc.id };
      }
      if (highlightedItem.category === 'Data Sources') {
        const sourceId = highlightedItem.id.replace('src-', '');
        return { kind: 'source' as const, id: sourceId };
      }
      if (highlightedItem.category === 'Tables') {
        const tbl = tables.find(t => t.id === highlightedItem.id || t.name === highlightedItem.label);
        if (tbl) return { kind: 'table' as const, id: tbl.id };
      }
      if (highlightedItem.category === 'Columns') {
        const tbl = tables.find(t => t.id === highlightedItem.id || t.id === (highlightedItem as any).tableId);
        if (tbl) return { kind: 'table' as const, id: tbl.id };
      }
    }
    if (mode === 'node' && table) {
      return { kind: 'table' as const, id: table.id };
    }
    if (mode === 'edge' && edgeData) {
      return { kind: 'edge' as const, id: edgeData.relationship?.id || `${edgeData.sourceTableName}__${edgeData.targetTableName}` };
    }
    return null;
  }, [isOpen, highlightedItem, mode, table, edgeData, kpiLineage, calculations, tables]);

  // Derived state based on selected inspector kind
  const inspTable  = inspector?.kind === 'table'   ? tables.find(t => t.id === inspector.id) ?? null : null;
  const inspCalc   = inspector?.kind === 'measure' ? calculations.find(c => c.id === inspector.id || c.name === inspector.id) ?? null : null;
  const inspKpi    = inspector?.kind === 'kpi'     ? kpiLineage.find(k => k.kpi_name === inspector.id) ?? null : null;
  const inspSource = inspector?.kind === 'source'  ? dataSources.find(s => s.id === inspector.id) ?? null : null;

  const inspTitle = inspTable?.name ?? inspCalc?.name ?? inspKpi?.kpi_name ?? inspSource?.name ?? null;

  const inspKindLabel = useMemo(() => {
    if (!inspector) return null;
    if (inspector.kind === 'table') {
      return inspTable?.table_type?.toUpperCase() || 'TABLE';
    }
    return inspector.kind.toUpperCase();
  }, [inspector, inspTable]);

  // Reset logic on item selection changes if needed
  useEffect(() => {
    // No longer resetting activeTab as it's removed
  }, [inspector?.id]);

  // Calculate table connections if Table is inspected
  const tableMap = useMemo(() => buildTableIdMap(tables), [tables]);
  const rels = useMemo(() => {
    if (!inspTable) return [];
    return relationships.filter(r => {
      const leftTable = resolveTableFromRelId(r.left_table_id, tableMap);
      const rightTable = resolveTableFromRelId(r.right_table_id, tableMap);
      return leftTable?.id === inspTable.id || rightTable?.id === inspTable.id;
    });
  }, [inspTable, relationships, tableMap]);

  const relCountByTable = useMemo(() => {
    const m: Record<string, number> = {};
    relationships.forEach(r => {
      const leftTable = resolveTableFromRelId(r.left_table_id, tableMap);
      const rightTable = resolveTableFromRelId(r.right_table_id, tableMap);
      if (leftTable) m[leftTable.id] = (m[leftTable.id] || 0) + 1;
      if (rightTable) m[rightTable.id] = (m[rightTable.id] || 0) + 1;
    });
    return m;
  }, [relationships, tableMap]);

  const sourceById = useMemo(() => {
    const m: Record<string, DataSource> = {};
    dataSources.forEach(s => { m[s.id] = s; });
    return m;
  }, [dataSources]);

  const highlightCol = highlightedItem?.category === 'Columns' ? highlightedItem.label : null;

  const relatedCalcs = useMemo(() => {
    if (!inspTable) return [];
    return getRelatedCalculations(inspTable.name, calculations);
  }, [inspTable, calculations]);

  const relatedKpis = useMemo(() => {
    if (!inspTable) return [];
    return getRelatedKpiLineage(inspTable.name, kpiLineage);
  }, [inspTable, kpiLineage]);

  const tabs = useMemo(() => {
    if (!inspTable) return [];
    return [
      { label: 'Details', icon: <Info size={11} />, count: undefined },
      { label: 'Columns', icon: <Columns size={11} />, count: inspTable.columns?.length },
      { label: 'Calculations', icon: <Code2 size={11} />, count: relatedCalcs.length },
      { label: 'KPI Lineage', icon: <TrendingUp size={11} />, count: relatedKpis.length },
      { label: 'Ingestion', icon: <Sliders size={11} />, count: inspTable.ingestion?.steps?.length },
    ];
  }, [inspTable, relatedCalcs, relatedKpis]);

  const normalizeId = (s: string) => {
    if (!s) return '';
    return s
      .toLowerCase()
      .replace(/^(tbl|col|mea|calc|kpi|src|ds)[-_]/, '')
      .replace(/\.csv$/, '')
      .replace(/[^a-z0-9]/g, '');
  };

  return (
    <div style={{ height: isOpen ? height : 0 }} className="w-full bg-white border-t border-stone-200 flex flex-col overflow-hidden shrink-0 transition-all duration-300">
      {!inspector ? (
        /* Empty state */
        <div className="flex flex-col items-center justify-center h-full w-full gap-3 text-center px-8">
          <div className="w-14 h-14 rounded-2xl bg-stone-100 flex items-center justify-center">
            <Table2 size={24} className="text-stone-400" />
          </div>
          <p className="text-[13px] font-semibold text-stone-600">Select an entity to inspect</p>
          <p className="text-[11.5px] text-stone-400 leading-relaxed">
            Click any node in the graph, or pick a table, measure, KPI, or data source from the left panel.
          </p>
        </div>
      ) : (
        /* ═══ ACTIVE PROPERTIES DRAWER ═══ */
        <div className="flex-1 flex flex-col overflow-hidden h-full">
          
          {/* ─── Premium Header Row (with Horizontal Inline Tabs) ─── */}
          <div className="flex items-center justify-between px-5 py-2.5 border-b border-stone-200 bg-stone-50 shrink-0 select-none">
            <div className="flex items-center gap-3 min-w-0 flex-1">
              {inspKindLabel && (
                <span className={cn(
                  'text-[8.5px] font-black uppercase tracking-widest px-2.5 py-0.5 rounded border shrink-0',
                  inspector.kind === 'table' && inspTable?.table_type === 'fact' ? 'text-red-600 border-red-200 bg-red-50/50' :
                  inspector.kind === 'table' ? 'text-blue-600 border-blue-200 bg-blue-50/50' :
                  inspector.kind === 'measure' ? 'text-indigo-600 border-indigo-100 bg-indigo-50/50' :
                  inspector.kind === 'kpi' ? 'text-emerald-600 border-emerald-100 bg-emerald-50/50' : 'text-stone-500'
                )}>{inspKindLabel}</span>
              )}
              <h2 className="text-[14px] font-black text-stone-900 font-mono truncate max-w-[280px] shrink-0" title={inspTitle || ''}>
                {inspTitle || (inspector.kind === 'edge' && 'RELATIONSHIP') || ''}
              </h2>

              {/* No Tabs */}
            </div>
            
            <button 
              onClick={onClose} 
              className="text-stone-400 hover:text-stone-700 transition-colors shrink-0 ml-4 p-1 rounded hover:bg-stone-200/50"
              title="Close properties panel"
            >
              <X size={15} />
            </button>
          </div>

          {/* ─── Scrollable Properties Content Area ─── */}
          <div className="flex-1 overflow-y-auto p-5 bg-white">
            
            {/* ═══ TABLE INSPECTOR TABS ═══ */}
            {inspTable && (
              <>
                {/* Details Section */}
                <div className="mb-8">
                  <h3 className="text-[13px] font-bold text-stone-800 mb-4 flex items-center gap-2"><Info size={14}/> Details</h3>
                  <div className="space-y-6">
                    <div className="grid grid-cols-3 gap-3">
                      <DetailBox label="Identifier" value={inspTable.id} />
                      <DetailBox label="Materialized" value={inspTable.is_materialized ? 'Yes' : 'No'} />
                      {(() => {
                        const src = sourceById[inspTable.source_data_source_id];
                        return src ? (
                          <div className="p-3 border border-stone-200 rounded-xl bg-stone-50/50 flex flex-col justify-between">
                            <span className="text-[9px] font-black tracking-widest text-stone-400 uppercase block mb-1">Source</span>
                            <button
                              onClick={() => fireSelectEvent({ id: `src-${src.id}`, sourceId: src.id, category: 'Data Sources', label: src.name })}
                              className="inline-flex items-center gap-1 text-[12px] font-bold text-[#003087] hover:underline text-left cursor-pointer font-mono truncate hover:text-[#c8102e] transition-colors"
                            >
                              <Database size={11} className="text-stone-400 shrink-0" />
                              <span className="underline decoration-blue-200 hover:decoration-red-400">{src.name}</span>
                              <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-blue-500 opacity-60 ml-0.5 shrink-0"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /><polyline points="15 3 21 3 21 9" /><line x1="10" y1="14" x2="21" y2="3" /></svg>
                            </button>
                          </div>
                        ) : null;
                      })()}
                    </div>
                    {inspTable.description && <p className="text-[12.5px] text-stone-600 leading-relaxed">{inspTable.description}</p>}

                    {rels.length > 0 && (
                      <div>
                        <SLabel>Connected tables ({rels.length})</SLabel>
                        <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                          {rels.map(e => {
                            const leftT = resolveTableFromRelId(e.left_table_id, tableMap);
                            const rightT = resolveTableFromRelId(e.right_table_id, tableMap);
                            if (!leftT || !rightT) return null;
                            const isLeft = leftT.id === inspTable.id;
                            const other = isLeft ? rightT : leftT;
                            const myCol = isLeft ? e.left_column : e.right_column;
                            const otherCol = isLeft ? e.right_column : e.left_column;
                            return (
                              <button key={e.id}
                                onClick={() => fireSelectEvent({ id: other.id, tableId: other.id, category: 'Tables', label: other.name })}
                                className="text-left rounded-xl border border-stone-200 px-3 py-2 hover:border-[#003087] hover:bg-blue-50/10 hover:scale-[1.01] transition-all cursor-pointer shadow-sm group flex justify-between items-center"
                              >
                                <div className="min-w-0 flex-1">
                                  <div className="flex items-center justify-between mb-1">
                                    <span className="text-[12px] font-bold text-stone-800 truncate group-hover:text-[#003087] group-hover:underline">{other.name}</span>
                                    <span className="text-[9.5px] font-mono font-bold text-stone-500 ml-2 shrink-0 bg-stone-100 px-1.5 py-0.5 rounded">{cardLabel(e.cardinality)}</span>
                                  </div>
                                  <p className="text-[10.5px] text-stone-500 font-mono truncate">{myCol} ↔ {otherCol}</p>
                                </div>
                                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-stone-400 group-hover:text-[#003087] transition-colors ml-2 shrink-0"><polyline points="9 18 15 12 9 6" /></svg>
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Columns Section */}
                <div className="mb-8">
                  <h3 className="text-[13px] font-bold text-stone-800 mb-4 flex items-center gap-2"><Columns size={14}/> Columns</h3>
                  <div className="rounded-xl border border-stone-200 overflow-hidden">
                    <table className="w-full text-[12px] border-collapse">
                      <thead>
                        <tr className="bg-stone-50 border-b border-stone-200">
                          {['Column', 'Type', 'Nullable', 'Tags / Role', 'Description'].map(h => (
                            <th key={h} className="text-left px-3 py-2 text-[10.5px] font-semibold text-stone-600 uppercase tracking-wide whitespace-nowrap">{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-stone-100">
                        {inspTable.columns.map((col) => (
                          <tr
                            key={col.name}
                            ref={col.name === highlightCol
                              ? (el => el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }))
                              : undefined}
                            className={cn(
                              'transition-colors',
                              col.name === highlightCol
                                ? 'bg-blue-50 shadow-[inset_4px_0_0_0_#003087]'
                                : 'hover:bg-stone-50'
                            )}
                          >
                            <td className="px-3 py-2 font-mono text-[11.5px] font-bold text-stone-850">
                              {col.semantic_role === 'primary_key' && <span className="mr-1" title="Primary Key">🔑</span>}
                              {col.semantic_role === 'foreign_key' && <span className="mr-1" title="Foreign Key">🔗</span>}
                              {col.name}
                            </td>
                            <td className="px-3 py-2 font-mono text-[10px] text-stone-500 uppercase">{col.data_type}</td>
                            <td className="px-3 py-2 text-stone-500">{col.nullable ? 'Yes' : 'No'}</td>
                            <td className="px-3 py-2">
                              <div className="flex flex-wrap gap-1">
                                {col.semantic_role && <Badge label={col.semantic_role} cls="bg-blue-50 text-blue-600 border-blue-100 font-semibold" />}
                                {col.used_in_relationships && <Badge label="rel" cls="bg-indigo-50 text-indigo-600 border-indigo-100" />}
                                {col.used_in_filters && <Badge label="filter" cls="bg-sky-50 text-sky-600 border-sky-100" />}
                                {col.used_in_calculations && <Badge label="calc" cls="bg-amber-50 text-amber-600 border-amber-100" />}
                              </div>
                            </td>
                            <td className="px-3 py-2 text-stone-500 text-[11.5px] max-w-[250px] truncate" title={col.description}>{col.description || '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Calculations Section */}
                {relatedCalcs.length > 0 && (
                  <div className="mb-8">
                    <h3 className="text-[13px] font-bold text-stone-800 mb-4 flex items-center gap-2"><Code2 size={14}/> Calculations</h3>
                    <div className="space-y-3">
                      {relatedCalcs.map((calc, idx) => (
                        <div key={idx} className="p-3.5 border border-stone-200 rounded-xl bg-stone-50/50 hover:bg-stone-50 transition-colors">
                          <div className="flex items-center justify-between mb-2">
                            <span className="text-[12px] font-bold text-stone-800">{calc.name}</span>
                            <span className="text-[10px] font-bold text-indigo-600 font-mono uppercase">{calc.semantic_type}</span>
                          </div>
                          {calc.description && <p className="text-[11px] text-slate-500 mb-2 leading-relaxed">{calc.description}</p>}
                          {calc.expressions?.dax && (
                            <pre className="text-[10.5px] font-mono bg-slate-50 border border-slate-200 text-indigo-800 p-2.5 rounded-lg overflow-x-auto whitespace-pre-wrap leading-relaxed shadow-sm">
                              {calc.expressions.dax}
                            </pre>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* KPI Lineage Section */}
                {relatedKpis.length > 0 && (
                  <div className="mb-8">
                    <h3 className="text-[13px] font-bold text-stone-800 mb-4 flex items-center gap-2"><TrendingUp size={14}/> KPI Lineage</h3>
                    <div className="w-full flex justify-center py-2">
                      <KpiLineageDiagram table={inspTable} kpis={relatedKpis} />
                    </div>
                  </div>
                )}

                {/* Ingestion Section */}
                {inspTable.ingestion?.steps && inspTable.ingestion.steps.length > 0 && (
                  <div className="mb-8">
                    <h3 className="text-[13px] font-bold text-stone-800 mb-4 flex items-center gap-2"><Sliders size={14}/> Ingestion</h3>
                    <div className="space-y-4 relative pl-4 border-l border-slate-200 py-1 ml-2">
                      {inspTable.ingestion.steps.map((step, idx) => (
                        <div key={idx} className="relative group">
                          <div className="absolute -left-[24.5px] top-0.5 w-4 h-4 rounded-full bg-white border-2 border-indigo-600 flex items-center justify-center text-[9px] font-bold text-indigo-700 shadow-sm font-mono">
                            {step.order}
                          </div>
                          <div className="p-3 border border-slate-200 bg-slate-50/40 hover:bg-slate-50 rounded-xl transition-colors">
                            <span className="text-[10px] font-black tracking-widest text-indigo-600 uppercase block mb-1">{step.step_type}</span>
                            <p className="text-[11.5px] text-slate-650 leading-relaxed mb-2">{step.description}</p>
                            {step.native_expressions?.powerquery && (
                              <pre className="text-[10px] font-mono bg-slate-50 border border-slate-200 text-indigo-800 p-2.5 rounded-lg overflow-x-auto whitespace-pre-wrap leading-relaxed shadow-sm">
                                {step.native_expressions.powerquery}
                              </pre>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}

            {/* ═══ MEASURE DETAIL ═══ */}
            {inspector.kind === 'measure' && inspCalc && (
              <div className="space-y-5">
                <div className="flex flex-wrap items-center gap-3">
                  <Badge label={inspCalc.semantic_type} cls="bg-indigo-50 text-indigo-600 border-indigo-100" />
                  <Badge label={inspCalc.data_type} cls="bg-blue-50 text-blue-600 border-blue-100" />
                  {inspCalc.aggregation_behavior && <Badge label={inspCalc.aggregation_behavior} />}
                  {inspCalc.is_base_measure && <Badge label="base" cls="bg-emerald-50 text-emerald-600 border-emerald-100" />}
                  {inspCalc.reusable && <Badge label="reusable" cls="bg-sky-50 text-sky-600 border-sky-100" />}
                </div>

                {inspCalc.description && <p className="text-[12.5px] text-stone-655 leading-relaxed">{inspCalc.description}</p>}

                {inspCalc.expressions?.dax && (
                  <div>
                    <SLabel>DAX Expression</SLabel>
                    <pre className="text-[11px] font-mono bg-slate-50 border border-slate-200 text-indigo-800 p-3 rounded-lg overflow-x-auto whitespace-pre-wrap leading-relaxed shadow-sm">
                      {inspCalc.expressions.dax}
                    </pre>
                  </div>
                )}

                {inspCalc.depends_on_columns?.length > 0 && (
                  <div>
                    <SLabel>Depends on Columns</SLabel>
                    <div className="flex flex-col items-start gap-1.5">
                      {inspCalc.depends_on_columns.map((dep, idx) => {
                        const match = dep.match(/^([^\[]+)(?:\[([^\]]+)\])?$/);
                        const tname = match ? match[1] : dep;
                        const colname = match ? match[2] : '';
                        const tbl = tables.find(t => t.name === tname);
                        return (
                          <button
                            key={idx}
                            onClick={() => {
                              if (tbl) {
                                fireSelectEvent({ id: tbl.id, tableId: tbl.id, category: colname ? 'Columns' : 'Tables', label: colname || tbl.name });
                              }
                            }}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-semibold text-[#003087] bg-blue-50/50 hover:bg-blue-100/60 border border-blue-100 hover:border-blue-300 rounded-xl transition-all cursor-pointer underline decoration-blue-200 hover:decoration-blue-500 hover:scale-[1.02] shadow-sm group"
                          >
                            <span className="text-blue-700 font-semibold group-hover:text-[#c8102e]">{tname}</span>
                            {colname && <span className="text-blue-500 font-mono">· {colname}</span>}
                            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-blue-500 opacity-60 ml-0.5 shrink-0 group-hover:text-[#c8102e] transition-colors"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /><polyline points="15 3 21 3 21 9" /><line x1="10" y1="14" x2="21" y2="3" /></svg>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* ═══ KPI DETAIL ═══ */}
            {inspector.kind === 'kpi' && inspKpi && (
              <div className="space-y-5">
                <div className="flex flex-wrap items-center gap-3">
                  <Badge label={inspKpi.semantic_type} cls="bg-emerald-50 text-emerald-600 border-emerald-100" />
                  <Badge label={inspKpi.data_type} cls="bg-blue-50 text-blue-600 border-blue-100" />
                  {inspKpi.format_string && <Badge label={`format: ${inspKpi.format_string}`} />}
                </div>

                {inspKpi.description && <p className="text-[12.5px] text-stone-655 leading-relaxed">{inspKpi.description}</p>}

                {inspKpi.formula && (
                  <div>
                    <SLabel>Formula</SLabel>
                    <pre className="text-[11px] font-mono bg-slate-50 border border-slate-200 text-indigo-800 p-3 rounded-lg overflow-x-auto whitespace-pre-wrap leading-relaxed shadow-sm">
                      {inspKpi.formula}
                    </pre>
                  </div>
                )}

                {inspKpi.depends_on_columns?.length > 0 && (
                  <div>
                    <SLabel>Depends on Columns</SLabel>
                    <div className="flex flex-col items-start gap-1.5">
                      {inspKpi.depends_on_columns.map((dep, idx) => {
                        const tbl = tables.find(t => t.id === dep.table_id || t.name === dep.table_name);
                        return (
                          <button
                            key={idx}
                            onClick={() => {
                              if (tbl) {
                                fireSelectEvent({ id: tbl.id, tableId: tbl.id, category: 'Columns', label: dep.column_name });
                              }
                            }}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-semibold text-[#003087] bg-blue-50/50 hover:bg-blue-100/60 border border-blue-100 hover:border-blue-300 rounded-xl transition-all cursor-pointer underline decoration-blue-200 hover:decoration-blue-500 hover:scale-[1.02] shadow-sm group"
                          >
                            <span className="text-blue-700 font-semibold group-hover:text-[#c8102e]">{dep.table_name}</span>
                            <span className="text-blue-500 font-mono">· {dep.column_name}</span>
                            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-blue-500 opacity-60 ml-0.5 shrink-0 group-hover:text-[#c8102e] transition-colors"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /><polyline points="15 3 21 3 21 9" /><line x1="10" y1="14" x2="21" y2="3" /></svg>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}

                <div>
                  <SLabel>Lineage Flow Diagram</SLabel>
                  <div className="w-full flex justify-center py-2">
                    {(() => {
                      const mainTable = tables.find(t => 
                        t.id === inspKpi.depends_on_columns?.[0]?.table_id || 
                        t.name === inspKpi.depends_on_columns?.[0]?.table_name
                      ) || tables[0];
                      return mainTable ? <KpiLineageDiagram table={mainTable} kpis={[inspKpi]} /> : null;
                    })()}
                  </div>
                </div>
              </div>
            )}

            {/* ═══ DATA SOURCE DETAIL ═══ */}
            {inspector.kind === 'source' && inspSource && (
              <div className="space-y-5">
                <div className="flex flex-wrap items-center gap-3">
                  <Badge label={`Type: ${inspSource.source_type}`} cls="bg-stone-50 text-stone-600 border-stone-200 font-semibold" />
                  <Badge label={`Mode: ${inspSource.connection_mode}`} cls="bg-indigo-50 text-indigo-600 border-indigo-100" />
                </div>

                <div className="grid grid-cols-3 gap-3">
                  {inspSource.server && <DetailBox label="Server" value={inspSource.server} />}
                  {inspSource.database && <DetailBox label="Database" value={inspSource.database} />}
                  {inspSource.schema && <DetailBox label="Schema" value={inspSource.schema} />}
                  {inspSource.path && <DetailBox label="File Path" value={inspSource.path} />}
                  {inspSource.gateway && <DetailBox label="Gateway" value={inspSource.gateway} />}
                  {inspSource.refresh_frequency && <DetailBox label="Refresh" value={inspSource.refresh_frequency} />}
                </div>

                {(() => {
                  const srcTables = tables.filter(t => doesTableBelongToSource(t, inspSource));
                  return srcTables.length > 0 && (
                    <div>
                      <SLabel>Imported Tables ({srcTables.length})</SLabel>
                      <div className="flex flex-wrap gap-2">
                        {srcTables.map(t => (
                          <button
                            key={t.id}
                            onClick={() => fireSelectEvent({ id: t.id, tableId: t.id, category: 'Tables', label: t.name })}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-stone-200 hover:border-[#003087] hover:bg-blue-50/10 rounded-xl text-[11.5px] font-semibold text-stone-850 hover:text-[#003087] transition-all cursor-pointer hover:scale-[1.02] shadow-sm group"
                          >
                            <span className={cn('w-2 h-2 rounded-sm shrink-0', t.table_type === 'fact' ? 'bg-red-400' : 'bg-blue-400')} />
                            <span className="group-hover:underline">{t.name}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  );
                })()}
              </div>
            )}

            {/* ═══ EDGE DETAIL ═══ */}
            {inspector.kind === 'edge' && edgeData && (
              <div className="space-y-6">
                <div className="grid grid-cols-3 gap-6">
                  <div>
                    <SLabel>Cardinality</SLabel>
                    <div className="inline-flex items-center gap-1.5 px-3 py-1 bg-amber-50 border border-amber-200 text-amber-700 text-[11px] font-bold rounded-lg">
                      {formatCardinality(edgeData.relationship?.cardinality)}
                    </div>
                  </div>

                  <div>
                    <SLabel>Join Condition</SLabel>
                    <div className="text-[11.5px] font-mono text-slate-800 bg-slate-50 border border-slate-200 px-2.5 py-1.5 rounded-lg inline-block">
                      {edgeData.sourceTableName}.{edgeData.leftColumn} = {edgeData.targetTableName}.{edgeData.rightColumn}
                    </div>
                  </div>

                  <div>
                    <SLabel>Active Status</SLabel>
                    <div className={`inline-flex items-center gap-1.5 px-3 py-1 text-[11px] font-bold rounded-lg ${edgeData.relationship?.active ? 'bg-emerald-50 border border-emerald-200 text-emerald-700' : 'bg-rose-50 border border-rose-200 text-rose-700'}`}>
                      {edgeData.relationship?.active ? 'Active Join' : 'Inactive Join'}
                    </div>
                  </div>
                </div>

                {edgeData.relationship?.note && (
                  <div className="pt-4 border-t border-slate-100">
                    <SLabel>Documentation / Notes</SLabel>
                    <p className="text-[11.5px] text-slate-600 leading-relaxed max-w-3xl">{edgeData.relationship.note}</p>
                  </div>
                )}
              </div>
            )}

          </div>
        </div>
      )}
    </div>
  );
};

const DetailBox: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="p-3 border border-stone-200 rounded-xl bg-stone-50/50">
    <span className="text-[9px] font-black tracking-widest text-stone-400 uppercase block mb-1">
      {label}
    </span>
    <span className="text-[12px] font-bold text-stone-700 block truncate" title={value}>
      {value}
    </span>
  </div>
);

const Badge: React.FC<{ label: string; cls?: string }> = ({ label, cls }) => (
  <span className={cn(
    "text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded border bg-stone-50 border-stone-200 text-stone-500",
    cls
  )}>
    {label}
  </span>
);

const SLabel: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <span className="text-[9.5px] font-black uppercase tracking-widest text-stone-400 block mb-2 mt-5">
    {children}
  </span>
);

export default GraphDrawer;
