import React, { useMemo } from 'react';
import { KpiLineageItem, Table } from '../../data/sampleModel';

interface Props {
  table: Table;
  kpis: KpiLineageItem[];
}

interface Node {
  id: string;
  label: string;
  kind: 'kpi' | 'measure' | 'column' | 'table';
  x: number;
  y: number;
  w: number;
  h: number;
}

interface Edge {
  id: string;
  from: string;
  to: string;
}

const KIND_COLORS: Record<string, { bg: string; border: string; text: string; headerText: string }> = {
  table:   { bg: '#eff6ff', border: '#8b9cbd', text: '#003087', headerText: '#003087' },
  column:  { bg: '#ffffff', border: '#cbd5e1', text: '#334155', headerText: '#94a3b8' },
  measure: { bg: '#ffffff', border: '#8b9cbd', text: '#003087', headerText: '#003087' },
  kpi:     { bg: '#fdf2f8', border: '#fca5a5', text: '#e11d48', headerText: '#f43f5e' },
};

function buildGraph(table: Table, kpis: KpiLineageItem[]) {
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  
  const NODE_W = 160;
  const NODE_H = 44;
  const X_SPACING = 240;
  const Y_SPACING = 60;
  
  // 1. Collect all unique columns used by these KPIs
  const cols = new Set<string>();
  const kpiToCols: Record<string, string[]> = {};
  
  kpis.forEach(kpi => {
    kpiToCols[kpi.kpi_name] = [];
    (kpi.depends_on_columns || []).forEach(c => {
      // only include columns from THIS table
      if (c.table_name === table.name || c.table_id === table.id) {
        cols.add(c.column_name);
        kpiToCols[kpi.kpi_name].push(c.column_name);
      }
    });
  });
  
  const colList = Array.from(cols);
  
  // Heights calculation to center align vertically
  const maxRows = Math.max(1, colList.length, kpis.length);
  const startY = 40;
  
  // Table node (Left)
  const tableX = 50;
  const tableY = startY + (maxRows * Y_SPACING) / 2 - Y_SPACING / 2;
  nodes.push({ id: `tbl-${table.id}`, label: table.name, kind: 'table', x: tableX, y: tableY, w: NODE_W, h: NODE_H });
  
  // Column nodes (Middle)
  const colX = tableX + X_SPACING;
  const colStartY = startY + (maxRows * Y_SPACING) / 2 - (colList.length * Y_SPACING) / 2;
  colList.forEach((c, idx) => {
    const cid = `col-${c}`;
    nodes.push({ id: cid, label: c, kind: 'column', x: colX, y: colStartY + idx * Y_SPACING, w: NODE_W, h: NODE_H });
    edges.push({ id: `e-tbl-${cid}`, from: `tbl-${table.id}`, to: cid });
  });
  
  // KPI nodes (Right)
  const kpiX = colX + X_SPACING;
  const kpiStartY = startY + (maxRows * Y_SPACING) / 2 - (kpis.length * Y_SPACING) / 2;
  kpis.forEach((kpi, idx) => {
    const kid = `kpi-${kpi.kpi_name}`;
    nodes.push({ id: kid, label: kpi.kpi_name, kind: 'kpi', x: kpiX, y: kpiStartY + idx * Y_SPACING, w: NODE_W, h: NODE_H });
    
    // Connect from its columns
    const deps = kpiToCols[kpi.kpi_name];
    if (deps.length > 0) {
      deps.forEach(c => {
        edges.push({ id: `e-col-${c}-${kid}`, from: `col-${c}`, to: kid });
      });
    } else {
      // if no direct columns, just link from table
      edges.push({ id: `e-tbl-${kid}`, from: `tbl-${table.id}`, to: kid });
    }
  });
  
  return { nodes, edges };
}

export default function KpiLineageDiagram({ table, kpis }: Props) {
  const { nodes, edges } = useMemo(() => buildGraph(table, kpis), [table, kpis]);

  if (!nodes.length) return <p className="text-[11px] text-stone-400 italic">No lineage data.</p>;

  const minX = Math.min(...nodes.map(n => n.x)) - 20;
  const minY = Math.min(...nodes.map(n => n.y)) - 20;
  const maxX = Math.max(...nodes.map(n => n.x + n.w)) + 20;
  const maxY = Math.max(...nodes.map(n => n.y + n.h)) + 20;
  const W = maxX - minX;
  const H = maxY - minY;

  const nodeMap: Record<string, Node> = {};
  nodes.forEach(n => { nodeMap[n.id] = n; });

  return (
    <div className="w-full flex flex-col font-sans">
      {/* Legend & Title Header */}
      <div className="mb-4 flex flex-col gap-1.5">
        <span className="text-[10px] font-black tracking-widest text-stone-500 uppercase">LINEAGE DIAGRAM</span>
        <div className="flex items-center gap-4 text-[11px] font-semibold">
          <div className="flex items-center gap-1.5 text-[#003087]">
            <div className="w-2.5 h-2.5 border-[1.5px] border-[#003087] rounded-[2px]" /> Table
          </div>
          <div className="flex items-center gap-1.5 text-slate-500">
            <div className="w-2.5 h-2.5 border-[1.5px] border-slate-400 rounded-[2px]" /> Column
          </div>
          <div className="flex items-center gap-1.5 text-[#003087]">
            <div className="w-2.5 h-2.5 border-[1.5px] border-[#003087] rounded-[2px]" /> Measure
          </div>
          <div className="flex items-center gap-1.5 text-rose-600">
            <div className="w-2.5 h-2.5 border-[1.5px] border-rose-500 rounded-[2px]" /> KPI
          </div>
        </div>
      </div>

      <div className="w-full overflow-x-auto flex justify-center py-4">
        <svg
          viewBox={`${minX} ${minY} ${W} ${H}`}
          style={{ width: '60%', overflow: 'visible', display: 'block', margin: '0 auto' }}
        >
          <defs>
            <marker id="arrowhead" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto">
              <path d="M 0 1 L 8 5 L 0 9 z" fill="#94a3b8" />
            </marker>
          </defs>

          {/* Connectors (Orthogonal / Step-like or Straight) */}
          {edges.map(e => {
            const a = nodeMap[e.from], b = nodeMap[e.to];
            if (!a || !b) return null;
            
            const startX = a.x + a.w;
            const startY = a.y + a.h / 2;
            const endX = b.x;
            const endY = b.y + b.h / 2;
            const midX = (startX + endX) / 2;
            
            const pathD = `M ${startX} ${startY} C ${midX} ${startY}, ${midX} ${endY}, ${endX} ${endY}`;

            return (
              <path
                key={e.id}
                d={pathD}
                fill="none"
                stroke="#cbd5e1"
                strokeWidth={1.5}
                markerEnd="url(#arrowhead)"
              />
            );
          })}

          {/* Nodes */}
          {nodes.map(n => {
            const c = KIND_COLORS[n.kind];
            return (
              <g key={n.id} transform={`translate(${n.x}, ${n.y})`}>
                <rect 
                  width={n.w} 
                  height={n.h} 
                  rx={6} 
                  fill={c.bg} 
                  stroke={c.border} 
                  strokeWidth={1.5} 
                />
                <text
                  x={8} y={14}
                  fill={c.headerText}
                  style={{ fontSize: '8px', fontWeight: 800, letterSpacing: '1px', textTransform: 'uppercase' }}
                >
                  {n.kind}
                </text>
                <text
                  x={n.w / 2} y={28}
                  textAnchor="middle"
                  fill={c.text}
                  style={{ 
                    fontSize: '11px', 
                    fontWeight: 700,
                  }}
                >
                  {n.label.length > 22 ? n.label.slice(0, 20) + '…' : n.label}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}
