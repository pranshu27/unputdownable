import { useState, useMemo, useRef, useEffect } from 'react';
import { DataModel } from '../../data/sampleModel';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap
} from "@xyflow/react";

import dagre from "dagre";
import "@xyflow/react/dist/style.css";
import {
  FileSpreadsheet, Network, Search, X, ChevronDown, ChevronRight,
  Hash, Type, Calendar, ToggleLeft, Filter as FilterIcon,
  Calculator, Zap, GitBranch, ArrowRight, Table2, Database,
  TrendingUp, FunctionSquare, Eye, Shield, Key, Layers,
  FileInput, GitMerge, Wrench, Trash2, RefreshCw, Combine,
  Pencil, Columns2, CircleDashed, MoveRight, Workflow, Sparkles
} from 'lucide-react';
import ContentCard from '../../core/CardContent/CardContent.tsx';
import FileWorkspaceHeader from '../../core/FileWorkspaceHeader.tsx';
import { useOutletContext } from 'react-router-dom';
import { Typography } from '@mui/material';
import { cn } from '../../Lib/utils.ts';

interface DataSourcesProps { model: DataModel; }

// ─── Semantic pill map ────────────────────────────────────────────────────────
const SEMANTIC_PILL: Record<string, string> = {
  sum: 'bg-[#f8fafc] text-[#334155] border-[#cbd5e1]',
  ratio: 'bg-[#f8fafc] text-[#334155] border-[#cbd5e1]',
  growth_rate: 'bg-[#f8fafc] text-[#334155] border-[#cbd5e1]',
  count: 'bg-[#f8fafc] text-[#334155] border-[#cbd5e1]',
  average: 'bg-[#f8fafc] text-[#334155] border-[#cbd5e1]',
  discount: 'bg-[#f8fafc] text-[#334155] border-[#cbd5e1]',
};
const semanticPill = (t: string) => SEMANTIC_PILL[t] ?? 'bg-[#f8fafc] text-[#475569] border-[#cbd5e1]';

// ─── Step meta ────────────────────────────────────────────────────────────────
const STEP_META: Record<string, { icon: React.ElementType; color: string; bg: string; border: string; label: string }> = {
  read_source: { icon: FileInput, color: 'text-[#475569]', bg: 'bg-[#f8fafc]', border: 'border-[#cbd5e1]', label: 'Read' },
  read: { icon: FileInput, color: 'text-[#475569]', bg: 'bg-[#f8fafc]', border: 'border-[#cbd5e1]', label: 'Read' },
  join: { icon: GitMerge, color: 'text-[#475569]', bg: 'bg-[#f8fafc]', border: 'border-[#cbd5e1]', label: 'Join' },
  filter: { icon: FilterIcon, color: 'text-[#475569]', bg: 'bg-[#f8fafc]', border: 'border-[#cbd5e1]', label: 'Filter' },
  create_extract: { icon: Database, color: 'text-[#475569]', bg: 'bg-[#f8fafc]', border: 'border-[#cbd5e1]', label: 'Extract' },
  calculation: { icon: Calculator, color: 'text-[#475569]', bg: 'bg-[#f8fafc]', border: 'border-[#cbd5e1]', label: 'Calc' },
  custom: { icon: Wrench, color: 'text-[#475569]', bg: 'bg-[#f8fafc]', border: 'border-[#cbd5e1]', label: 'Custom' },
  remove_columns: { icon: Trash2, color: 'text-[#475569]', bg: 'bg-[#f8fafc]', border: 'border-[#cbd5e1]', label: 'Remove' },
  change_type: { icon: RefreshCw, color: 'text-[#475569]', bg: 'bg-[#f8fafc]', border: 'border-[#cbd5e1]', label: 'Change Type' },
  merge: { icon: Combine, color: 'text-[#475569]', bg: 'bg-[#f8fafc]', border: 'border-[#cbd5e1]', label: 'Merge' },
  rename: { icon: Pencil, color: 'text-[#475569]', bg: 'bg-[#f8fafc]', border: 'border-[#cbd5e1]', label: 'Rename' },
  split_column: { icon: Columns2, color: 'text-[#475569]', bg: 'bg-[#f8fafc]', border: 'border-[#cbd5e1]', label: 'Split' },
  group: { icon: Layers, color: 'text-[#475569]', bg: 'bg-[#f8fafc]', border: 'border-[#cbd5e1]', label: 'Group' },
};
const STEP_PRESETS = [
  { color: 'text-[#475569]', bg: 'bg-[#f8fafc]', border: 'border-[#cbd5e1]' },
  { color: 'text-[#475569]', bg: 'bg-[#f8fafc]', border: 'border-[#cbd5e1]' },
  { color: 'text-[#475569]', bg: 'bg-[#f8fafc]', border: 'border-[#cbd5e1]' },
  { color: 'text-[#475569]', bg: 'bg-[#f8fafc]', border: 'border-[#cbd5e1]' },
];
const hashStr = (s: string) => { let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0; return h; };
const getStepMeta = (t: string) => STEP_META[t] ?? {
  icon: CircleDashed,
  label: t.replace(/_/g, ' ').replace(/(^|\s)\w/g, c => c.toUpperCase()),
  ...STEP_PRESETS[hashStr(t) % STEP_PRESETS.length]
};


// ─── Shared atoms ─────────────────────────────────────────────────────────────
function Pill({ text, cls }: { text: string; cls?: string }) {
  return (
    <span className={cn('inline-flex items-center text-[10px] font-semibold px-2 py-0.5 rounded-md border whitespace-nowrap', cls ?? 'bg-slate-100 text-slate-500 border-slate-200')}>
      {text}
    </span>
  );
}

function SLabel({ text }: { text: string }) {
  return <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-2">{text}</p>;
}

const typeIcon = (dt: string) => {
  if (dt === 'string') return <Type className="w-3.5 h-3.5 text-slate-500" />;
  if (['integer', 'float', 'number', 'decimal'].includes(dt)) return <Hash className="w-3.5 h-3.5 text-slate-500" />;
  if (['datetime', 'date'].includes(dt)) return <Calendar className="w-3.5 h-3.5 text-slate-500" />;
  return <ToggleLeft className="w-3.5 h-3.5 text-slate-400" />;
};

function ArrowSection({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center min-w-[80px]">

      {/* arrow line */}
      <div className="flex items-center">
        <div className="w-10 h-[2px] bg-slate-300" />

        <div className="w-0 h-0 border-t-[6px] border-b-[6px] border-l-[10px] border-t-transparent border-b-transparent border-l-slate-400" />
      </div>

      {/* label */}
      <span className="text-[10px] text-slate-500 mt-2 font-medium whitespace-nowrap">
        {label}
      </span>
    </div>
  );
}
// ─── Accordion ────────────────────────────────────────────────────────────────
function Accordion({ title, icon, count, children, defaultOpen = false, accentColor = 'blue', open }: {
  title: string; icon: React.ReactNode; count?: number;
  children: React.ReactNode; defaultOpen?: boolean; accentColor?: string; open?: boolean;
}) {
  const [isOpen, setIsOpen] = useState(open ?? defaultOpen);
  useEffect(() => {
    if (open !== undefined) {
      setIsOpen(open);
    }
  }, [open]);
  const accMap: Record<string, string> = {
    blue: 'border-l-[#cbd5e1]',
    green: 'border-l-[#cbd5e1]',
    violet: 'border-l-[#cbd5e1]',
    amber: 'border-l-[#cbd5e1]',
    pink: 'border-l-[#cbd5e1]',
    orange: 'border-l-[#cbd5e1]',
  };
  return (
    <div className={cn('rounded-xl border border-[#e2e8f0] overflow-hidden border-l-[3px]', accMap[accentColor] ?? accMap.blue)}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-slate-50 transition-colors text-left bg-white"
      >
        <span className="text-slate-400 shrink-0">{icon}</span>
        <span className="text-[13px] font-semibold text-slate-800 flex-1">{title}</span>
        {count !== undefined && (
          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-100 text-slate-500 mr-1">{count}</span>
        )}
        <ChevronDown className={cn('w-4 h-4 text-slate-300 shrink-0 transition-transform duration-200', isOpen && 'rotate-180 text-slate-500')} />
      </button>
      {isOpen && <div className="px-4 pb-4 pt-2 bg-white border-t border-slate-100">{children}</div>}
    </div>
  );
}
const getLayout = (nodes: any[], edges: any[]) => {
  const g = new dagre.graphlib.Graph();

  g.setGraph({
    rankdir: "LR",
  });

  g.setDefaultEdgeLabel(() => ({}));

  nodes.forEach((n) => {
    g.setNode(n.id, {
      width: 180,
      height: 60,
    });
  });

  edges.forEach((e) => {
    g.setEdge(e.source, e.target);
  });

  dagre.layout(g);

  nodes.forEach((n) => {
    const pos = g.node(n.id);

    n.position = {
      x: pos.x - 90,
      y: pos.y - 30,
    };
  });

  return { nodes, edges };
};

// ─── Semantic Lineage View (the key upgrade) ──────────────────────────────────
function SemanticLineage({ kpi, allCalcs }: { kpi: any; allCalcs: any[] }) {
  const colDeps: any[] = kpi.depends_on_columns || [];
  const mDeps: any[] = kpi.depends_on_measures || [];

  // group columns by table
  const byTable: Record<string, any[]> = {};
  colDeps.forEach((col: any) => {
    const k = col.table_name || 'Unknown';
    if (!byTable[k]) byTable[k] = [];
    byTable[k].push(col);
  });

  // resolve measure deps to full calc objects
  const resolvedMDeps = mDeps.map((m: any) => {
    const name = m.kpi_name || m;
    const found = allCalcs.find((c: any) => c.name === name);
    return { name, ...m, calc: found };
  });
  const { nodes, edges } = useMemo(() => {
    const nodes: any[] = [];
    const edges: any[] = [];
    const added = new Set();

    const addNode = (
      id: string,
      label: string,
      type: string,
      meta: any = {}
    ) => {
      if (added.has(id)) return;

      const colors: any = {
        table: "#10b981",
        column: "#2563eb",
        measure: "#7c3aed",
        kpi: "#dc2626",
      };

      nodes.push({
        id,
        data: {
          label,
          type,
          meta,
        },
        position: { x: 0, y: 0 },
        style: {
          background: colors[type],
          color: "white",
          borderRadius: 12,
          padding: 10,
          width: 180,
          textAlign: "center",
          fontSize: 12,
        },
      });

      added.add(id);
    };

    const kpiId = `kpi-${kpi.kpi_name}`;
    addNode(
      kpiId,
      kpi.kpi_name,
      "kpi",
      {
        formula: kpi.formula,
        description: kpi.description,
      }
    );

    // columns + tables
    colDeps.forEach((col: any) => {
      const colId = `col-${col.column_name}`;
      const tableId = `table-${col.table_name}`;

      addNode(
        tableId,
        col.table_name,
        "table"
      );

      addNode(
        colId,
        col.column_name,
        "column"
      );

      edges.push({
        id: `${tableId}-${colId}`,
        source: tableId,
        target: colId,
        animated: true,
      });

      edges.push({
        id: `${colId}-${kpiId}`,
        source: colId,
        target: kpiId,
        animated: true,
      });
    });

    // measures
    resolvedMDeps.forEach((measure: any) => {
      const measureId = `measure-${measure.name}`;

      addNode(
        measureId,
        measure.name,
        "measure"
      );

      edges.push({
        id: `${measureId}-${kpiId}`,
        source: measureId,
        target: kpiId,
        animated: true,
      });
    });

    return getLayout(nodes, edges);
  }, [kpi, colDeps, resolvedMDeps]);
  const hasUpstream = colDeps.length > 0 || mDeps.length > 0;
  return (
    <div className="space-y-4">

      {/* ── Visual semantic flow ── */}
      <div>
        <div className="h-[500px] rounded-xl border border-slate-200 overflow-hidden bg-slate-50">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            fitView
            nodesDraggable={false}
            elementsSelectable={true}
          >
            <MiniMap />
            <Controls />
            <Background />
          </ReactFlow>
        </div>
      </div>

      {/* ── DAX formula ── */}
      {kpi.formula && (
        <div>
          <SLabel text="DAX expression" />
          <pre className="bg-[#0d1117] rounded-xl px-4 py-3 text-[11px] font-mono text-[#7ee787] whitespace-pre-wrap break-words leading-relaxed overflow-x-auto max-h-40 border border-slate-800">
            {kpi.formula.trim()}
          </pre>
        </div>
      )}

      {/* ── Column lineage table ── */}
      {colDeps.length > 0 && (
        <div>
          <SLabel text={`Column lineage (${colDeps.length})`} />
          <div className="rounded-xl border border-slate-200 overflow-hidden">
            <table className="w-full text-[11px] border-collapse">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200">
                  <th className="px-3 py-2 text-left text-[9px] font-bold uppercase tracking-wider text-slate-400">Column</th>
                  <th className="px-3 py-2 text-left text-[9px] font-bold uppercase tracking-wider text-slate-400">Table</th>
                  <th className="px-3 py-2 text-left text-[9px] font-bold uppercase tracking-wider text-slate-400">CSV source</th>
                  <th className="px-3 py-2 text-left text-[9px] font-bold uppercase tracking-wider text-slate-400">Table type</th>
                </tr>
              </thead>
              <tbody>
                {colDeps.map((col: any, i: number) => (
                  <tr key={i} className="border-b border-slate-100 last:border-0 hover:bg-slate-50/60 transition-colors">
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-1.5">
                        <Hash className="w-3 h-3 text-indigo-400 shrink-0" />
                        <span className="font-mono font-semibold text-indigo-700">{col.column_name}</span>
                      </div>
                    </td>
                    <td className="px-3 py-2 font-mono text-slate-600">{col.table_name || '—'}</td>
                    <td className="px-3 py-2 text-slate-400">{col.data_source?.name || '—'}</td>
                    <td className="px-3 py-2">
                      {col.table_type && (
                        <span className={cn('text-[9px] font-bold px-1.5 py-0.5 rounded border',
                          col.table_type === 'fact'
                            ? 'bg-[#fefce8] text-[#854d0e] border-[#fde68a]'
                            : 'bg-[#f8fafc] text-[#334155] border-[#cbd5e1]'
                        )}>{col.table_type}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Calc row with inline semantic lineage ────────────────────────────────────
function CalcRow({ calc, relatedKpi, allCalcs }: { calc: any; relatedKpi: any; allCalcs: any[] }) {
  const [showLineage, setShowLineage] = useState(false);

  const splitDep = (dep: string) => {
    const d = dep.indexOf('.');
    return d > -1 ? { table: dep.slice(0, d), col: dep.slice(d + 1) } : { table: 'Unknown', col: dep };
  };

  const colsByTable = (calc.depends_on_columns || []).reduce((acc: any, dep: string) => {
    const { table, col } = splitDep(dep);
    if (!acc[table]) acc[table] = [];
    acc[table].push(col);
    return acc;
  }, {});

  const mDeps: string[] = calc.depends_on_measures || [];
  const usedBy = allCalcs.filter((c: any) => c.id !== calc.id && (c.depends_on_measures || []).includes(calc.name));
  const expr = calc.expressions?.dax || calc.expressions?.tableau || '';
  const totalDeps = (calc.depends_on_columns || []).length + mDeps.length;

  return (
    <div className="rounded-xl border border-slate-200 bg-white overflow-hidden transition-all duration-200">
      {/* Header row */}
      <div className="px-4 py-3 flex items-start gap-3">
        <div className={cn('w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-0.5',
          semanticPill(calc.semantic_type).split(' ').slice(0, 2).join(' ')
        )}>
          <FunctionSquare className="w-4 h-4" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="text-[13px] font-bold text-slate-900">{calc.name}</span>
            {calc.semantic_type && (
              <Pill text={calc.semantic_type.replace(/_/g, ' ')} cls={semanticPill(calc.semantic_type)} />
            )}
            {calc.data_type && (
              <span className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 uppercase">{calc.data_type}</span>
            )}
            {calc.is_base_measure && <Pill text="base" cls="bg-[#f8fafc] text-[#334155] border-[#cbd5e1]" />}
            {calc.reusable && <Pill text="reusable" cls="bg-[#f8fafc] text-[#334155] border-[#cbd5e1]" />}
          </div>

          {/* Formula preview line */}
          {expr && (
            <code className="text-[10px] font-mono text-indigo-500 block truncate opacity-80 mb-2">
              {expr.trim().split('\n')[0].trim()}
            </code>
          )}

          {/* Dep summary */}
          <div className="flex items-center gap-2 flex-wrap">
            {Object.keys(colsByTable).map(tbl => (
              <span key={tbl} className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-lg bg-slate-100 text-slate-600 font-medium">
                <Table2 className="w-2.5 h-2.5" />{tbl}
                <span className="text-slate-400">({colsByTable[tbl].length} cols)</span>
              </span>
            ))}
            {mDeps.map(m => (
              <span key={m} className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-lg bg-[#f8fafc] border border-[#cbd5e1] text-[#334155] font-mono">
                <FunctionSquare className="w-2.5 h-2.5" />[{m}]
              </span>
            ))}
            {usedBy.length > 0 && (
              <span className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-lg bg-[#f8fafc] border border-[#cbd5e1] text-[#334155] font-medium">
                <ArrowRight className="w-2.5 h-2.5" />used by {usedBy.length}
              </span>
            )}
            {totalDeps === 0 && <span className="text-[10px] text-slate-400 italic">no dependencies</span>}
          </div>
        </div>

        {/* View lineage button */}
        {relatedKpi && (
          <button
            onClick={() => setShowLineage(!showLineage)}
            className={cn(
              'flex items-center gap-1.5 text-[10px] font-semibold px-3 py-1.5 rounded-lg border transition-all shrink-0',
              showLineage
                ? 'bg-[#eff6ff] text-[#1d4ed8] border-[#bfdbfe] shadow-sm'
                : 'bg-white text-[#64748b] border-[#e2e8f0] hover:border-[#bfdbfe] hover:text-[#1d4ed8] hover:bg-[#eff6ff]'
            )}
          >
            <Sparkles className="w-3 h-3" />
            {showLineage ? 'Hide lineage' : 'View lineage'}
          </button>
        )}
      </div>

      {/* Expanded DAX + column deps */}


      {/* Semantic lineage panel */}
      {showLineage && relatedKpi && (
        <div className="border-t border-amber-100 bg-amber-50/20 px-4 py-4">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-5 h-5 rounded-md bg-amber-100 flex items-center justify-center">
              <Workflow className="w-3 h-3 text-amber-600" />
            </div>
            <span className="text-[11px] font-bold text-amber-800 uppercase tracking-wide">Semantic lineage — {relatedKpi.kpi_name}</span>
          </div>
          <SemanticLineage kpi={relatedKpi} allCalcs={allCalcs} />
        </div>
      )}
    </div>
  );
}

// ─── Data Flow Pipeline ───────────────────────────────────────────────────────
function DataFlowPanel({ table }: { table: any }) {
  const [activeStep, setActiveStep] = useState<number | null>(null);
  const steps = table?.ingestion?.steps || [];

  if (!steps.length) {
    return <p className="text-[12px] text-slate-400 italic py-2">No ingestion pipeline defined for this table.</p>;
  }

  const usedTypes = new Set(steps.map((s: any) => s.step_type));
  const usedKeys = [
    ...Object.keys(STEP_META).filter(k => usedTypes.has(k)),
    ...Array.from(usedTypes).filter(k => !STEP_META[k]),
  ];

  return (
    <div className="space-y-4">

      {/* Pipeline */}
      <div className="overflow-x-auto overflow-y-visible py-3 pl-2">
        <div className="flex items-center gap-2 pt-1 pb-2 pl-1 min-w-max">
          {steps.map((step: any, idx: number) => {
            const meta = getStepMeta(step.step_type);
            const Icon = meta.icon;
            const isActive = activeStep === idx;
            return (
              <div key={idx} className="flex items-center gap-2 shrink-0">
                <button
                  onClick={() => setActiveStep(isActive ? null : idx)}
                  className={cn(
                    'flex flex-col items-center gap-1.5 px-4 py-4 rounded-xl border transition-all duration-200 min-w-[88px]',
                    meta.bg, meta.border,
                    isActive
                      ? 'ring-2 ring-offset-1 ring-indigo-400 shadow-sm -translate-y-0.5'
                      : 'hover:-translate-y-0.5 hover:shadow-sm'
                  )}
                >
                  <Icon className={cn('w-4 h-4', meta.color)} strokeWidth={2.2} />
                  <span className={cn('text-[10px] font-bold uppercase tracking-wider', meta.color)}>{meta.label}</span>
                  <span className="text-[9px] text-slate-400 font-mono">#{step.order}</span>
                </button>
                {idx < steps.length - 1 && (
                  <ChevronRight className="w-4 h-4 text-slate-300 shrink-0" />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Step detail */}
      {activeStep !== null && steps[activeStep] && (() => {
        const step = steps[activeStep];
        const expr = step.native_expressions?.powerquery || step.native_expressions?.tableau || step.native_expressions?.dax;
        return (
          <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-4">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">
              Step {step.order} · {step.step_type}
            </p>
            <p className="text-[13px] text-slate-700 mb-3 leading-relaxed">{step.description}</p>
            {expr && (
              <>
                <SLabel text="Native expression" />
                <code className="block text-[11px] font-mono text-indigo-700 bg-white rounded-lg px-3 py-2 border border-slate-200 break-all leading-relaxed">
                  {expr}
                </code>
              </>
            )}
          </div>
        );
      })()}
    </div>
  );
}

// ─── Right Drawer ─────────────────────────────────────────────────────────────
function TableDrawer({ table, model, onClose }: { table: any; model: DataModel; onClose: () => void }) {
  const normalize = (s: string | null | undefined): string =>
    (s == null ? '' : String(s)).toLowerCase().replace(/[^a-z0-9]/g, '');
  const tableIdNorm = normalize(table?.id);
  const tableNameNorm = normalize(table?.name);
  const handleSectionClick = (
    section: "schema" | "relationships" | "kpis" | "lineage"
  ) => {
    setActiveSection(section);

    const refMap = {
      schema: columnsRef,
      relationships: flowRef,
      kpis: metadataRef,
      lineage: calcRef,
      metadata: metadataRef
    };

    refMap[section]?.current?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  };

  const calculations = useMemo(() => (model.calculations || []).filter((c: any) =>
    (c.depends_on_columns || []).some((dep: string | null) => {
      const d = normalize(dep);
      return tableNameNorm && d && d.includes(tableNameNorm);
    })
  ), [table, model]);

  const kpis = useMemo(() => (model.kpi_lineage || []).filter((k: any) =>
    (k.depends_on_columns || []).some((col: any) => {
      const colTbl = normalize(col?.table_name);
      return tableNameNorm && colTbl && colTbl === tableNameNorm;
    })
  ), [table, model]);

  const source = useMemo(() => (model.data_sources || []).find((s: any) => {
    if (!s) return false;
    if (s.id === table?.source_data_source_id) return true;
    const sn = normalize(s.name);
    return tableNameNorm && sn && sn.includes(tableNameNorm);
  }), [table, model]);

  const allCalcs = useMemo(() => (model.calculations || []).map((c: any) => ({
    ...c,
    depends_on_columns: c.depends_on_columns || [],
    depends_on_measures: c.depends_on_measures || [],
  })), [model]);

  const isFact = table?.table_type === 'fact';
  const columns: any[] = table?.columns || [];
  const [selectedKpi, setSelectedKpi] = useState<any>(null);
  const [columnSearch, setColumnSearch] = useState("");
  const [activeSection, setActiveSection] = useState<
    "schema" | "relationships" | "kpis" | "lineage"
  >("schema");

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const columnsRef = useRef<HTMLDivElement>(null);
  const flowRef = useRef<HTMLDivElement>(null);
  const metadataRef = useRef<HTMLDivElement>(null);
  const calcRef = useRef<HTMLDivElement>(null);
  const relatedRelationships = useMemo(() => (model.relationships || []).filter((rel: any) => {
    const left = normalize(rel.left_table_id || rel.left_table || rel.from_table || rel.source_table);
    const right = normalize(rel.right_table_id || rel.right_table || rel.to_table || rel.target_table);
    return Boolean(tableIdNorm || tableNameNorm) && (
      left.includes(tableIdNorm) ||
      left.includes(tableNameNorm) ||
      right.includes(tableIdNorm) ||
      right.includes(tableNameNorm)
    );
  }), [model, tableIdNorm, tableNameNorm]);
  const filteredColumns = columns.filter((col: any) => {
    const search = columnSearch.toLowerCase();
  
    return (
      col.name?.toLowerCase().includes(search) ||
      col.data_type?.toLowerCase().includes(search) ||
      col.description?.toLowerCase().includes(search) ||
      col.semantic_role?.toLowerCase().includes(search)
    );
  });
  return (
    <>
      <div className="fixed inset-0 bg-black/25 backdrop-blur-[2px] z-[90]" onClick={onClose} />

      <div className="fixed inset-y-0 right-0 w-[min(760px,calc(100vw-20px))] bg-white z-[100] shadow-2xl border-l border-slate-200 flex flex-col animate-[slideInRight_180ms_ease-out]">

        {/* ── Header ── */}
        <div className={cn(
          'sticky top-0 z-20 px-5 py-4 border-b shrink-0 border-l-4',
          isFact
            ? 'border-b-[#e2e8f0] border-l-[#cbd5e1] bg-white'
            : 'border-b-[#e2e8f0] border-l-[#cbd5e1] bg-white'
        )}>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 flex-wrap mb-1.5">
                <div className={cn(
                  'text-[9px] font-black uppercase tracking-widest px-2 py-1 rounded-md',
                  isFact ? 'bg-[#fefce8] text-[#854d0e]' : 'bg-[#f8fafc] text-[#334155]'
                )}>
                  {isFact ? 'FACT' : 'DIMENSION'}
                </div>
                <h2 className="text-[17px] font-bold text-slate-900">{table.name}</h2>
                {table.is_materialized && (
                  <Pill text="materialized" cls="bg-[#f8fafc] text-[#334155] border-[#cbd5e1]" />
                )}
              </div>
              <p className="text-[12px] text-slate-500 leading-snug mb-3">{table.description}</p>
              {source && (
                <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 flex items-center gap-3 mb-4 w-[98.3%]">
                  <div className="w-8 h-8 rounded-lg bg-[#f8fafc] flex items-center justify-center shrink-0">
                    <FileSpreadsheet className="w-4 h-4 text-[#64748b]" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-[10px] text-[#64748b] font-semibold uppercase tracking-wider">Source file</p>
                    <p className="text-[12px] font-semibold text-[#0f172a] truncate">{source.name}</p>
                    {source.path && <p className="text-[9px] text-[#64748b] font-mono truncate">{source.path}</p>}
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <Pill text={source.source_type || 'CSV'} cls="bg-[#f1f5f9] text-[#475569] border-[#cbd5e1]" />
                    <Pill text={source.connection_mode || 'import'} cls="bg-[#f8fafc] text-[#64748b] border-[#cbd5e1]" />
                  </div>
                </div>
              )}
              {/* Quick stats row */}
              <div className="flex items-center gap-2 flex-wrap">

                {/* Columns */}
                <button
                  onClick={() => handleSectionClick("schema")}
                  className={cn(
                    "text-[10px] font-semibold px-3 py-1 rounded-lg border transition-all",
                    activeSection === "schema"
                      ? "bg-[#eff6ff] text-[#1d4ed8] border-[#bfdbfe] shadow-sm"
                      : "bg-[#f8fafc] text-[#334155] border-[#cbd5e1] hover:bg-[#eff6ff]"
                  )}
                >
                  Schema ({columns.length})
                </button>

                {/* Data Flow */}
                <button
                  onClick={() => handleSectionClick("relationships")}
                  className={cn(
                    "text-[10px] font-semibold px-3 py-1 rounded-lg border transition-all",
                    activeSection === "relationships"
                      ? "bg-[#eff6ff] text-[#1d4ed8] border-[#bfdbfe] shadow-sm"
                      : "bg-[#f8fafc] text-[#334155] border-[#cbd5e1] hover:bg-[#eff6ff]"
                  )}
                >
                  Relationships ({relatedRelationships.length})
                </button>

                {/* Calculations */}
                <button
                  onClick={() => handleSectionClick("kpis")}
                  className={cn(
                    "text-[10px] font-semibold px-3 py-1 rounded-lg border transition-all",
                    activeSection === "kpis"
                      ? "bg-[#eff6ff] text-[#1d4ed8] border-[#bfdbfe] shadow-sm"
                      : "bg-[#f8fafc] text-[#334155] border-[#cbd5e1] hover:bg-[#eff6ff]"
                  )}
                >
                  KPIs ({kpis.length})
                </button>

                {/* KPIs */}
                <button
                  onClick={() => handleSectionClick("lineage")}
                  className={cn(
                    "text-[10px] font-semibold px-3 py-1 rounded-lg border transition-all",
                    activeSection === "lineage"
                      ? "bg-[#eff6ff] text-[#1d4ed8] border-[#bfdbfe] shadow-sm"
                      : "bg-[#f8fafc] text-[#334155] border-[#cbd5e1] hover:bg-[#eff6ff]"
                  )}
                >
                  Lineage ({calculations.length})
                </button>
              </div>
            </div>
            <button
              onClick={onClose}
              className="w-8 h-8 rounded-xl border border-slate-200 flex items-center justify-center text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition-colors shrink-0"
              title="Close Panel"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* ── Body ── */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3 bg-slate-50/30">

          {/* ── Columns ── */}
          {activeSection === 'schema' && (
            <div ref={columnsRef} className="space-y-4">
              <div className="flex items-center justify-between border-b border-slate-150 pb-2">
                <h3 className="text-[13px] font-bold text-slate-800 flex items-center gap-2">
                  <Database className="w-4 h-4 text-[#003087]" />
                  Schema & Columns
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-100 text-slate-500">
                    {columns.length}
                  </span>
                </h3>
                {/* Column type legend */}
                <div className="flex gap-3 flex-wrap">
                  {[
                    { icon: <Type className="w-3 h-3 text-slate-500" />, label: 'String' },
                    { icon: <Hash className="w-3 h-3 text-slate-500" />, label: 'Number' },
                    { icon: <Calendar className="w-3 h-3 text-slate-500" />, label: 'Date' },
                  ].map(({ icon, label }) => (
                    <span key={label} className="flex items-center gap-1 text-[10px] text-slate-400">
                      {icon}{label}
                    </span>
                  ))}
                </div>
              </div>

              {/* Column Search */}
              <div className="relative">
                <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="text"
                  placeholder="Search columns, type, role..."
                  value={columnSearch}
                  onChange={(e) => setColumnSearch(e.target.value)}
                  className="w-full pl-10 pr-4 py-2 text-sm rounded-xl border border-slate-200 bg-white text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-300"
                />
              </div>

              <div className="rounded-xl border border-slate-200 overflow-hidden bg-white shadow-sm">
                <table className="w-full text-[12px]">
                  <thead className="bg-slate-50 border-b border-slate-200 sticky top-0 z-10">
                    <tr>
                      <th className="px-3 py-2 text-left font-semibold text-slate-600">Column</th>
                      <th className="px-3 py-2 text-left font-semibold text-slate-600">Type</th>
                      <th className="px-3 py-2 text-left font-semibold text-slate-600">Role</th>
                      <th className="px-3 py-2 text-left font-semibold text-slate-600">Usage</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredColumns.map((col: any) => (
                      <tr key={col.name} className="border-b border-slate-100 hover:bg-[#f8fafc] transition">
                        <td className="px-3 py-2">
                          <div className="flex items-center gap-2">
                            {typeIcon(col.data_type)}
                            <span className="font-medium text-slate-800">{col.name}</span>
                          </div>
                          {col.description && (
                            <p className="text-[10px] text-slate-400 mt-1 truncate max-w-[200px]">{col.description}</p>
                          )}
                        </td>
                        <td className="px-3 py-2">
                          <span className="text-slate-600 uppercase text-[11px] font-mono">{col.data_type}</span>
                        </td>
                        <td className="px-3 py-2">
                          <div className="flex flex-wrap gap-1">
                            {col.semantic_role === "primary_key" && <Badge label="PK" cls="bg-[#eff6ff] text-[#1d4ed8]" />}
                            {col.semantic_role === "foreign_key" && <Badge label="FK" cls="bg-slate-100 text-slate-600" />}
                            {col.semantic_role === "dimension" && <Badge label="DIM" cls="bg-slate-100 text-slate-600" />}
                            {col.semantic_role === "measure" && <Badge label="MEASURE" cls="bg-[#fefce8] text-[#854d0e]" />}
                          </div>
                        </td>
                        <td className="px-3 py-2">
                          <div className="flex flex-wrap gap-1">
                            {col.nullable ? <Badge label="N" cls="bg-slate-100 text-slate-400" /> : <Badge label="NN" cls="bg-red-50 text-red-600" />}
                            {col.used_in_relationships && <Badge label="REL" cls="bg-purple-50 text-purple-600" />}
                            {col.used_in_filters && <Badge label="F" cls="bg-teal-50 text-teal-600" />}
                            {col.used_in_calculations && <Badge label="C" cls="bg-amber-50 text-amber-600" />}
                            {col.used_in_groupby && <Badge label="G" cls="bg-indigo-50 text-indigo-600" />}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Badge legend */}
              <div className="flex flex-wrap gap-2 mt-3 pt-3 border-t border-slate-100">
                {[
                  { label: 'PK = Primary key', cls: 'bg-[#eff6ff] text-[#1d4ed8] border-[#bfdbfe]' },
                  { label: 'FK = Foreign key', cls: 'bg-[#f8fafc] text-[#475569] border-[#cbd5e1]' },
                  { label: 'F = Used in filter', cls: 'bg-[#f8fafc] text-[#475569] border-[#cbd5e1]' },
                  { label: 'G = Group by', cls: 'bg-[#f8fafc] text-[#475569] border-[#cbd5e1]' },
                  { label: 'C = In calculation', cls: 'bg-[#f8fafc] text-[#475569] border-[#cbd5e1]' },
                  { label: 'NN = Not nullable', cls: 'bg-[#f8fafc] text-[#475569] border-[#cbd5e1]' },
                ].map(b => (
                  <span key={b.label} className={cn('text-[9px] font-semibold px-2 py-0.5 rounded border', b.cls)}>{b.label}</span>
                ))}
              </div>
            </div>
          )}

          {/* ── Relationships ── */}
          {activeSection === 'relationships' && (
            <div ref={flowRef} className="space-y-4">
              <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2 border-b border-slate-150 pb-2">
                <GitBranch className="w-4 h-4 text-[#003087]" />
                Relationships
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-100 text-slate-500">
                  {relatedRelationships.length}
                </span>
              </h3>
              {relatedRelationships.length === 0 ? (
                <div className="rounded-xl border border-slate-200 bg-white p-6 text-center text-slate-400 italic">
                  No direct relationships found for this table.
                </div>
              ) : (
                <div className="grid grid-cols-1 gap-3">
                  {relatedRelationships.map((rel: any) => (
                    <div key={rel.id || `${rel.left_table_id}-${rel.right_table_id}`} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm hover:shadow-md transition">
                      <div className="flex items-center justify-between gap-3">
                        <span className="truncate text-[13px] font-bold text-slate-800">{rel.left_table || rel.left_table_id}</span>
                        <div className="flex items-center justify-center shrink-0 w-8 h-8 rounded-full bg-slate-50 border border-slate-100">
                          <MoveRight className="h-4 w-4 text-[#003087]" />
                        </div>
                        <span className="truncate text-right text-[13px] font-bold text-slate-800">{rel.right_table || rel.right_table_id}</span>
                      </div>
                      <div className="mt-3 pt-3 border-t border-slate-100 flex flex-wrap gap-2 items-center">
                        {rel.left_column && <span className="text-[11px] font-mono bg-slate-50 text-slate-600 px-2 py-0.5 rounded border border-slate-200">{rel.left_column}</span>}
                        <span className="text-[11px] text-slate-400">🔗</span>
                        {rel.right_column && <span className="text-[11px] font-mono bg-slate-50 text-slate-600 px-2 py-0.5 rounded border border-slate-200">{rel.right_column}</span>}
                        {rel.cardinality && <span className="text-[10px] font-semibold px-2 py-0.5 bg-[#eff6ff] text-[#1d4ed8] border border-[#bfdbfe] rounded-md ml-auto">{rel.cardinality}</span>}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── KPIs ── */}
          {activeSection === 'kpis' && (
            <div ref={metadataRef} className="space-y-4">
              <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2 border-b border-slate-150 pb-2">
                <TrendingUp className="w-4 h-4 text-[#003087]" />
                KPIs
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-100 text-slate-500">
                  {kpis.length}
                </span>
              </h3>
              {kpis.length === 0 ? (
                <div className="rounded-xl border border-slate-200 bg-white p-6 text-center text-slate-400 italic">
                  No KPIs reference this table.
                </div>
              ) : (
                <div className="grid grid-cols-1 gap-3">
                  {kpis.map((kpi: any) => (
                    <div key={kpi.kpi_name} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm hover:shadow-md transition">
                      <div className="flex items-center justify-between">
                        <p className="text-[13px] font-bold text-slate-800">{kpi.kpi_name}</p>
                        <span className="text-[9px] font-semibold px-2 py-0.5 bg-red-50 text-red-600 border border-red-100 rounded-md uppercase">KPI</span>
                      </div>
                      {kpi.description && <p className="mt-2 text-[12px] text-slate-500 leading-relaxed">{kpi.description}</p>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── Calculations & Semantic Lineage ── */}
          {activeSection === 'lineage' && (
            <div ref={calcRef} className="space-y-4">
              <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2 border-b border-slate-150 pb-2">
                <FunctionSquare className="w-4 h-4 text-[#003087]" />
                Calculations & Semantic Lineage
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-100 text-slate-500">
                  {calculations.length}
                </span>
              </h3>
              {calculations.length === 0 ? (
                <div className="rounded-xl border border-slate-200 bg-white p-6 text-center text-slate-400 italic">
                  No calculations reference this table.
                </div>
              ) : (
                <div className="space-y-4">
                  {/* KPI Chips */}
                  {kpis.length > 0 && (
                    <div>
                      <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">
                        Filter by KPI Chain
                      </p>
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {kpis.map((k: any) => {
                          const isSelected = selectedKpi?.kpi_name === k.kpi_name;
                          return (
                            <button
                              key={k.kpi_name}
                              onClick={() => setSelectedKpi(isSelected ? null : k)}
                              className={cn(
                                "flex items-center gap-1.5 text-[10px] font-bold px-2.5 py-1.5 rounded-lg border transition-all duration-200 shadow-sm",
                                isSelected
                                  ? "bg-[#c8102e] text-white border-[#c8102e]"
                                  : "bg-white text-slate-700 border-slate-200 hover:bg-slate-50"
                              )}
                            >
                              <TrendingUp className="w-3 h-3" />
                              {k.kpi_name}
                              {isSelected && <X className="w-2.5 h-2.5 ml-1" />}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Show calculations list */}
                  <div className="space-y-3">
                    {calculations
                      .filter((calc: any) => {
                        if (!selectedKpi) return true;
                        if (calc.name?.toLowerCase() === selectedKpi.kpi_name?.toLowerCase()) return true;
                        if (selectedKpi.depends_on_measures?.includes(calc.name)) return true;
                        return false;
                      })
                      .map((calc: any) => (
                        <CalcRow
                          key={calc.id}
                          calc={calc}
                          relatedKpi={selectedKpi}
                          allCalcs={allCalcs}
                        />
                      ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── Table info ── */}
          {/* <Accordion title="Table metadata" icon={<Table2 className="w-4 h-4" />} accentColor="green">
            <div className="grid grid-cols-2 gap-2">
              {[
                { label: 'Table ID', value: table.id },
                { label: 'Table type', value: table.table_type },
                { label: 'Source ID', value: table.source_data_source_id || '—' },
                { label: 'Materialized', value: table.is_materialized ? 'Yes' : 'No' },
              ].map(({ label, value }) => (
                <div key={label} className="bg-slate-50 rounded-xl border border-slate-100 px-3 py-2">
                  <p className="text-[9px] font-bold uppercase tracking-wider text-slate-400 mb-0.5">{label}</p>
                  <p className="text-[11px] font-mono font-medium text-slate-800 break-all">{value}</p>
                </div>
              ))}
            </div>
          </Accordion> */}

        </div>
      </div>
    </>
  );
}
function Badge({ label, cls }: any) {
  return (
    <span
      className={`px-2 py-0.5 rounded-md text-[10px] font-semibold ${cls}`}
    >
      {label}
    </span>
  );
}

function LinkedTablesDialog({
  source,
  onClose,
  onSelectTable
}: {
  source: any;
  onClose: () => void;
  onSelectTable: (table: any) => void;
}) {
  const [tableSearch, setTableSearch] = useState('');
  const linkedTables = source?.linkedTables || [];
  const filteredTables = linkedTables.filter((table: any) => {
    const q = tableSearch.toLowerCase().trim();
    if (!q) return true;
    return (
      table.name?.toLowerCase().includes(q) ||
      table.table_type?.toLowerCase().includes(q) ||
      table.description?.toLowerCase().includes(q)
    );
  });

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return (
    <>
      <div className="fixed inset-0 bg-slate-950/30 backdrop-blur-[2px] z-[70]" onClick={onClose} />
      <div className="fixed left-1/2 top-[88px] z-[80] flex max-h-[calc(100vh-112px)] w-[min(880px,calc(100vw-48px))] -translate-x-1/2 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-4">
          <div className="min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Linked tables</p>
            <h3 className="mt-1 truncate text-[16px] font-bold text-slate-950">{source?.name}</h3>
            <p className="mt-1 text-[12px] text-slate-500">{linkedTables.length} table{linkedTables.length !== 1 ? 's' : ''} available</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-200 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900"
            title="Close linked tables"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="border-b border-slate-100 px-5 py-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={tableSearch}
              onChange={(event) => setTableSearch(event.target.value)}
              placeholder="Search linked tables..."
              className="w-full rounded-xl border border-slate-200 bg-white py-2 pl-9 pr-3 text-[12px] text-slate-800 placeholder:text-slate-400 focus:border-slate-400 focus:outline-none"
              autoFocus
            />
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {filteredTables.length === 0 ? (
            <div className="py-12 text-center text-[13px] text-slate-400">No linked tables match your search</div>
          ) : (
            <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
              {filteredTables.map((table: any) => (
                <button
                  key={table.id}
                  type="button"
                  onClick={() => {
                    onSelectTable(table);
                    onClose();
                  }}
                  className="group flex min-w-0 items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-left transition-colors hover:border-slate-300 hover:bg-slate-50"
                >
                  <div className="flex min-w-0 items-center gap-2.5">
                    <span className={cn(
                      'flex h-7 w-7 shrink-0 items-center justify-center rounded-lg',
                      table.table_type === 'fact' ? 'bg-red-50 text-[#C8102E]' : 'bg-blue-50 text-[#1D4ED8]'
                    )}>
                      <Table2 className="h-3.5 w-3.5" />
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-[12px] font-semibold text-slate-900">{table.name}</p>
                      <p className="text-[10px] capitalize text-slate-400">
                        {table.table_type || 'table'} - {(table.columns || []).length} columns
                      </p>
                    </div>
                  </div>
                  <ChevronRight className="h-3.5 w-3.5 shrink-0 text-slate-300 transition-transform group-hover:translate-x-0.5 group-hover:text-slate-500" />
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function CompactTableRow({ table, onOpen }: { table: any; onOpen: (table: any) => void }) {
  const isFact = table.table_type === 'fact';
  return (
    <button
      type="button"
      onClick={() => onOpen(table)}
      className="flex w-full items-center justify-between gap-3 border-t border-slate-100 px-4 py-2 text-left transition-colors hover:bg-slate-50"
    >
      <div className="flex min-w-0 items-center gap-2">
        <Table2 className={cn('h-3.5 w-3.5 shrink-0', isFact ? 'text-[#C8102E]' : 'text-[#003087]')} />
        <span className="truncate text-[12px] font-semibold text-slate-900">{table.name}</span>
      </div>
      <div className="flex shrink-0 items-center gap-3 text-[10px] text-slate-500">
        <span>{(table.columns || []).length} cols</span>
        <ChevronRight className="h-3.5 w-3.5" />
      </div>
    </button>
  );
}

function SourceGroup({ source, onOpenTable }: { source: any; onOpenTable: (table: any) => void }) {
  const [isOpen, setIsOpen] = useState(false);
  const [openTypes, setOpenTypes] = useState<Set<string>>(new Set());
  const linkedTables = source.linkedTables || [];
  const groups = [
    { key: 'fact', label: 'Fact Tables', tables: linkedTables.filter((table: any) => table.table_type === 'fact') },
    { key: 'dimension', label: 'Dimension Tables', tables: linkedTables.filter((table: any) => table.table_type === 'dimension') },
    { key: 'lookup', label: 'Lookup Tables', tables: linkedTables.filter((table: any) => table.table_type === 'lookup') },
    { key: 'other', label: 'Other Tables', tables: linkedTables.filter((table: any) => !['fact', 'dimension', 'lookup'].includes(table.table_type)) },
  ].filter(group => group.tables.length > 0);
  const isFed = (source.source_type || '').toLowerCase() === 'federated';

  const toggleType = (key: string) => {
    setOpenTypes(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-slate-50"
      >
        <ChevronRight className={cn('h-4 w-4 shrink-0 text-slate-400 transition-transform', isOpen && 'rotate-90')} />
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-slate-50">
          {isFed ? <Network className="h-3.5 w-3.5 text-slate-500" /> : <FileSpreadsheet className="h-3.5 w-3.5 text-slate-500" />}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-2">
            <p className="truncate text-[13px] font-bold text-slate-950">{source.name}</p>
            <span className="shrink-0 rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-600">
              {linkedTables.length} table{linkedTables.length !== 1 ? 's' : ''}
            </span>
          </div>
          <p className="truncate text-[10px] font-mono text-slate-400">{source.path || source.server || 'No source path'}</p>
        </div>
        <div className="hidden shrink-0 items-center gap-2 md:flex">
          <Pill text={source.source_type || 'CSV'} cls="bg-[#f1f5f9] text-[#475569] border-[#cbd5e1]" />
          <span className="text-[11px] text-slate-400">{source.refresh_frequency || 'Manual'}</span>
        </div>
      </button>

      {isOpen && (
        <div className="border-t border-slate-100 bg-slate-50/40 px-3 py-3">
          {groups.length === 0 ? (
            <div className="px-4 py-3 text-[12px] font-medium italic text-red-500">No linked tables</div>
          ) : (
            <div className="space-y-2">
              {groups.map(group => {
                const groupOpen = openTypes.has(group.key);
                return (
                  <div key={group.key} className="overflow-hidden rounded-md border border-slate-200 bg-white">
                    <button
                      type="button"
                      onClick={() => toggleType(group.key)}
                      className="flex w-full items-center justify-between px-4 py-2 text-left transition-colors hover:bg-slate-50"
                    >
                      <span className="flex min-w-0 items-center gap-2">
                        <ChevronRight className={cn('h-3.5 w-3.5 text-slate-400 transition-transform', groupOpen && 'rotate-90')} />
                        <span className="text-[12px] font-semibold text-slate-800">{group.label}</span>
                      </span>
                      <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-500">{group.tables.length}</span>
                    </button>
                    {groupOpen && (
                      <div className="max-h-[360px] overflow-y-auto">
                        {group.tables.map((table: any) => (
                          <CompactTableRow key={table.id} table={table} onOpen={onOpenTable} />
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────
export default function DataSources({ model }: DataSourcesProps) {
  const { sideNavWidth } = useOutletContext<{ sideNavWidth: number }>();
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState<'all' | 'CSV' | 'federated'>('all');
  const [selectedTable, setSelectedTable] = useState<any | null>(null);
  const [linkedTablesSource, setLinkedTablesSource] = useState<any | null>(null);

  const normalize = (s: string | null | undefined): string =>
    (s == null ? '' : String(s)).toLowerCase().replace(/[^a-z0-9]/g, '');

  const enrichedSources = useMemo(() => {
    return (model.data_sources || []).map((src: any) => {
      const srcNorm = normalize(src?.name)
        .replace(".csv", "")
        .replace(/\./g, "")
        .replace(/_/g, "");

      const linked = (model.tables || []).filter((t: any) => {
        if (!t) return false;
        
        // 1. Direct ID/Name matching
        if (src.id && (t.source_data_source_id === src.id || t.data_source_id === src.id || t.source_id === src.id)) return true;
        if (t.data_source?.name === src.name || t.source === src.name || t.source_name === src.name) return true;

        // 2. Fallback to string matching
        const tableNorm = normalize(t.name)
          .replace(/\./g, "")
          .replace(/_/g, "");

        return srcNorm.includes(tableNorm) || tableNorm.includes(srcNorm);
      });

      return {
        ...src,
        linkedTables: linked
      };
    });
  }, [model]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return enrichedSources.filter((s: any) => {
      const tableMatch = (s.linkedTables || []).some((table: any) =>
        table.name?.toLowerCase().includes(q) ||
        table.table_type?.toLowerCase().includes(q) ||
        table.columns?.some((col: any) => col.name?.toLowerCase().includes(q))
      );
      const matchQ = !q || (s.name || '').toLowerCase().includes(q) || (s.path || '').toLowerCase().includes(q) || tableMatch;
      const matchT = typeFilter === 'all' || (s.source_type || '').toLowerCase() === typeFilter.toLowerCase();
      return matchQ && matchT;
    });
  }, [enrichedSources, search, typeFilter]);

  const totalColumns = (model.tables || []).reduce((a: number, t: any) => a + (t.columns || []).length, 0);
  const totalCalcs = (model.calculations || []).length;
  const totalKpis = (model.kpi_lineage || []).length;
  const totalTables = (model.tables || []).length;
  const totalSources = (model.data_sources || []).length;
  const totalRels = (model.relationships || []).length;

  return (
    <ContentCard
      heading={null}
      sideNavWidth={sideNavWidth}
      headerComponent={<FileWorkspaceHeader pageTitle="Data Sources" />}
      flat={true}
    >
      <div className="space-y-5 p-6" style={{ padding: '24px' }}>
        {/* ── Stats ── */}
        <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
          {[
            { label: 'Sources', value: totalSources, icon: <FileSpreadsheet className="w-4 h-4" />, color: 'text-[#475569]', bg: 'bg-white', border: 'border-[#e2e8f0]' },
            { label: 'Tables', value: totalTables, icon: <Table2 className="w-4 h-4" />, color: 'text-[#475569]', bg: 'bg-white', border: 'border-[#e2e8f0]' },
            { label: 'Columns', value: totalColumns, icon: <Hash className="w-4 h-4" />, color: 'text-[#475569]', bg: 'bg-white', border: 'border-[#e2e8f0]' },
            { label: 'Relationships', value: totalRels, icon: <GitBranch className="w-4 h-4" />, color: 'text-[#475569]', bg: 'bg-white', border: 'border-[#e2e8f0]' },
            { label: 'Calculations', value: totalCalcs, icon: <FunctionSquare className="w-4 h-4" />, color: 'text-[#475569]', bg: 'bg-white', border: 'border-[#e2e8f0]' },
            { label: 'KPIs', value: totalKpis, icon: <TrendingUp className="w-4 h-4" />, color: 'text-[#475569]', bg: 'bg-white', border: 'border-[#e2e8f0]' },
          ].map(s => (
            <div key={s.label} className={cn('rounded-xl border px-4 py-3 flex items-center gap-3', s.bg, s.border)}>
              <span className={s.color}>{s.icon}</span>
              <div>
                <p className={cn('text-[20px] font-bold leading-none', s.color)}>{s.value}</p>
                <p className="text-[10px] text-slate-400 mt-0.5">{s.label}</p>
              </div>
            </div>
          ))}
        </div>

        {/* ── Toolbar ── */}
        <div className="sticky top-0 z-10 -mx-1 flex items-center gap-3 flex-wrap bg-[#fffdfc]/95 px-1 py-2 backdrop-blur">
          <div className="relative flex-1 max-w-xs">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
            <input
              type="text"
              placeholder="Search sources or paths…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-2 text-[12px] border border-slate-200 rounded-xl bg-white text-slate-800 placeholder-slate-400 focus:outline-none focus:border-slate-400"
            />
            {search && (
              <button onClick={() => setSearch('')} className="absolute right-2.5 top-1/2 -translate-y-1/2">
                <X className="w-3.5 h-3.5 text-slate-400" />
              </button>
            )}
          </div>
          <div className="flex gap-1 bg-slate-100 rounded-xl p-1">
            {(['all', 'CSV', 'federated'] as const).map(f => (
              <button
                key={f}
                onClick={() => setTypeFilter(f)}
                className={cn('px-3 py-1.5 rounded-lg text-[11px] font-semibold transition-all capitalize',
                  typeFilter === f ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-800'
                )}
              >
                {f === 'all' ? `All (${totalSources})` : f}
              </button>
            ))}
          </div>
          <span className="ml-auto text-[11px] text-slate-700 font-medium">{filtered.length} source{filtered.length !== 1 ? 's' : ''}</span>
        </div>

        {/* ── Table ── */}
        <div className="space-y-2">
          {filtered.length === 0 ? (
            <div className="rounded-lg border border-slate-200 bg-white py-14 text-center text-[13px] text-slate-400">
              No sources match your filter
            </div>
          ) : (
            filtered.map((src: any) => (
              <SourceGroup key={src.id} source={src} onOpenTable={setSelectedTable} />
            ))
          )}
        </div>

        {false && (
        <div className="rounded-xl border border-slate-200 overflow-hidden bg-white">
          <table className="w-full text-[12px] border-collapse">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200">
                <th className="px-4 py-3 text-left text-[10px] font-bold uppercase tracking-wider text-slate-400 w-[30%]">Source name</th>
                <th className="px-4 py-3 text-left text-[10px] font-bold uppercase tracking-wider text-slate-400 w-[7%]">Type</th>
                <th className="px-4 py-3 text-left text-[10px] font-bold uppercase tracking-wider text-slate-400 w-[8%]">Mode</th>
                <th className="px-4 py-3 text-left text-[10px] font-bold uppercase tracking-wider text-slate-400 w-[8%]">Auth</th>
                <th className="px-4 py-3 text-left text-[10px] font-bold uppercase tracking-wider text-slate-400 w-[8%]">Gateway</th>
                <th className="px-4 py-3 text-left text-[10px] font-bold uppercase tracking-wider text-slate-400 w-[8%]">Refresh</th>
                <th className="px-4 py-3 text-left text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  Linked tables <span className="normal-case font-normal text-slate-400">(click to inspect schema, flow & lineage)</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-14 text-center text-slate-400 text-[13px]">No sources match your filter</td>
                </tr>
              )}
              {filtered.map((src: any) => {
                const isFed = (src.source_type || '').toLowerCase() === 'federated';
                return (
                  <tr key={src.id} className="border-b border-slate-100 last:border-0 hover:bg-[#f8fafc] transition-colors">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2.5">
                        <div className={cn('w-7 h-7 rounded-lg flex items-center justify-center shrink-0', 'bg-[#f8fafc]')}>
                          {isFed ? <Network className="w-3.5 h-3.5 text-[#64748b]" /> : <FileSpreadsheet className="w-3.5 h-3.5 text-[#64748b]" />}
                        </div>
                        <div className="min-w-0">
                          <p className="text-[12px] font-semibold text-slate-900 truncate max-w-[200px]">{src.name}</p>
                          <p className="text-[9px] font-mono text-slate-400 truncate max-w-[200px]" title={src.path}>{src.path || '—'}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <Pill text={src.source_type || '—'} cls={isFed ? 'bg-[#f8fafc] text-[#64748b] border-[#cbd5e1]' : 'bg-[#f1f5f9] text-[#475569] border-[#cbd5e1]'} />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        <Zap className="w-3 h-3 text-[#64748b]" />
                        <span className="text-[11px] text-[#475569] font-semibold">{src.connection_mode || '—'}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      {src.authentication_method
                        ? <Pill text={src.authentication_method} cls="bg-[#f8fafc] text-[#64748b] border-[#e2e8f0]" />
                        : <span className="flex items-center gap-1 text-[10px] text-slate-400"><Shield className="w-3 h-3" />None</span>}
                    </td>
                    <td className="px-4 py-3 text-[11px] text-slate-400">{src.gateway || '—'}</td>
                    <td className="px-4 py-3 text-[11px] text-slate-400">{src.refresh_frequency || 'Manual'}</td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap items-center gap-1.5 max-w-[500px]">
                        {src.linkedTables.length === 0 && (
                          <span className="text-[11px] text-red-500 font-medium italic">
                            No linked tables
                          </span>
                        )}

                        {(() => {
                          const tablesToShow = src.linkedTables.slice(0, 3);

                          return (
                            <>
                              {tablesToShow.map((t: any) => (
                                <button
                                  key={t.id}
                                  onClick={() => setSelectedTable(t)}
                                  className={cn(
                                    "group flex items-center gap-1.5 text-[11px] px-2.5 py-1.5 rounded-lg border font-medium transition-all hover:shadow-sm",
                                    t.table_type === "fact"
                                      ? "bg-white text-[#C8102E] border-[#C8102E] hover:bg-red-50"
                                      : "bg-white text-[#1D4ED8] border-[#1D4ED8] hover:bg-blue-50"
                                  )}
                                >
                                  <Table2 className="w-3 h-3 shrink-0" />
                                  <span className="font-medium text-[11px] tracking-tight text-inherit">
                                    {t.name}
                                  </span>
                                  <ChevronRight className="w-3 h-3 opacity-40 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all" />
                                </button>
                              ))}

                              {src.linkedTables.length > tablesToShow.length && (
                                <button
                                  type="button"
                                  onClick={() => setLinkedTablesSource(src)}
                                  className="flex items-center gap-1 text-[11px] px-2.5 py-1.5 rounded-lg border font-semibold transition-all bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100 hover:text-slate-900"
                                >
                                  View all {src.linkedTables.length}
                                </button>
                              )}
                            </>
                          );
                        })()}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        )}

        {/* Legend */}
        <div className="flex flex-wrap items-center gap-5 pt-4 border-t border-slate-200">

          {/* Fact */}
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-[#C8102E]" />
            <span className="text-xs font-medium text-slate-700">
              Fact Table
            </span>
          </div>

          {/* Dimension */}
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-[#1D4ED8]" />
            <span className="text-xs font-medium text-slate-700">
              Dimension Table
            </span>
          </div>

          {/* Instruction */}
          <div className="flex items-center gap-2">
            <ChevronRight className="w-3 h-3 text-slate-500" />
            <span className="text-xs font-medium text-slate-600">
              Click table to inspect schema & lineage
            </span>
          </div>

        </div>

      </div>

      {/* Drawer */}
      {selectedTable && (
        <TableDrawer table={selectedTable} model={model} onClose={() => setSelectedTable(null)} />
      )}
    </ContentCard>
  );
}
