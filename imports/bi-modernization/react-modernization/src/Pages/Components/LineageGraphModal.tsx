import React, { useMemo, useState, useCallback } from "react";
import dagre from "dagre";
import { useOutletContext } from "react-router-dom";

import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  MarkerType,
  NodeMouseHandler,
} from "reactflow";
import "reactflow/dist/style.css";
import {
  X,
  Database,
  Table2,
  GitBranch,
  Calculator,
  BarChart3,
  Layers,
  ArrowRight,
  ArrowLeft,
  Tag,
  Hash,
  FileText,
} from "lucide-react";

interface Props {
  selectedNode: any;
  nodesData: any[];
  nodeMap: Record<string, any>;
}
interface OutletContextType {
  sideNavWidth: number;
}

/* ── colour palette ── */
const typeStyles: Record<string, { background: string; color: string; border: string; shadow: string }> = {
  data_source:    { background: "#1d4ed8", color: "#fff", border: "#1e40af", shadow: "0 4px 14px rgba(29,78,216,.35)" },
  ingestion_step: { background: "#f8fafc", color: "#1e293b", border: "#cbd5e1", shadow: "0 2px 8px rgba(0,0,0,.08)" },
  table:          { background: "#059669", color: "#fff", border: "#047857", shadow: "0 4px 14px rgba(5,150,105,.3)" },
  relationship:   { background: "#7c3aed", color: "#fff", border: "#6d28d9", shadow: "0 4px 14px rgba(124,58,237,.3)" },
  calculation:    { background: "#d97706", color: "#fff", border: "#b45309", shadow: "0 4px 14px rgba(217,119,6,.3)" },
  visual:         { background: "#db2777", color: "#fff", border: "#be185d", shadow: "0 4px 14px rgba(219,39,119,.3)" },
};
const MAIN_STYLE = { background: "#c8102e", color: "#fff", border: "#9f0e25", shadow: "0 6px 20px rgba(200,16,46,.4)" };

const typeIcons: Record<string, React.ElementType> = {
  data_source: Database, ingestion_step: Layers, table: Table2,
  relationship: GitBranch, calculation: Calculator, visual: BarChart3,
};

const typeBadge: Record<string, { bg: string; text: string; border: string }> = {
  data_source:    { bg: "#eff6ff", text: "#1d4ed8", border: "#bfdbfe" },
  ingestion_step: { bg: "#f8fafc", text: "#475569", border: "#e2e8f0" },
  table:          { bg: "#f0fdf4", text: "#059669", border: "#bbf7d0" },
  relationship:   { bg: "#f5f3ff", text: "#7c3aed", border: "#ddd6fe" },
  calculation:    { bg: "#fffbeb", text: "#d97706", border: "#fde68a" },
  visual:         { bg: "#fdf2f8", text: "#db2777", border: "#fbcfe8" },
};

/* ── BFS: full upstream + downstream ── */
function collectLineage(startId: string, nodeMap: Record<string, any>) {
  const edgeSet = new Set<string>();
  const edges: { source: string; target: string }[] = [];
  const addEdge = (s: string, t: string) => {
    const k = `${s}→${t}`;
    if (!edgeSet.has(k)) { edgeSet.add(k); edges.push({ source: s, target: t }); }
  };

  const upVisited = new Set<string>();
  const upQ = [startId];
  while (upQ.length) {
    const id = upQ.shift()!;
    if (upVisited.has(id)) continue;
    upVisited.add(id);
    const n = nodeMap[id];
    if (!n) continue;
    for (const prev of n.prev_nodes ?? []) {
      if (!nodeMap[prev]) continue;
      addEdge(prev, id);
      if (!upVisited.has(prev)) upQ.push(prev);
    }
  }

  const downVisited = new Set<string>();
  const downQ = [startId];
  while (downQ.length) {
    const id = downQ.shift()!;
    if (downVisited.has(id)) continue;
    downVisited.add(id);
    const n = nodeMap[id];
    if (!n) continue;
    for (const next of n.next_nodes ?? []) {
      if (!nodeMap[next]) continue;
      addEdge(id, next);
      if (!downVisited.has(next)) downQ.push(next);
    }
  }

  return { visitedIds: new Set([...upVisited, ...downVisited]), edges };
}

/* ── Dagre layout ── */
const NODE_W = 230, NODE_H = 70;
function layoutGraph(rfNodes: any[], rfEdges: any[]) {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", ranksep: 80, nodesep: 28 });
  rfNodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
  rfEdges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);
  return {
    nodes: rfNodes.map((n) => {
      const p = g.node(n.id);
      return { ...n, position: { x: (p?.x ?? 0) - NODE_W / 2, y: (p?.y ?? 0) - NODE_H / 2 } };
    }),
    edges: rfEdges,
  };
}

/* ── Node Info Panel ── */
const InfoRow = ({ label, value }: { label: string; value: React.ReactNode }) => (
  <div style={{ display: "flex", flexDirection: "column", gap: 2, padding: "7px 0", borderBottom: "1px solid #f1f5f9" }}>
    <span style={{ fontSize: 10, fontWeight: 600, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.06em" }}>{label}</span>
    <span style={{ fontSize: 12, color: "#1e293b", wordBreak: "break-word" }}>{value ?? <span style={{ color: "#cbd5e1" }}>—</span>}</span>
  </div>
);

const NodeInfoPanel: React.FC<{ node: any; nodeMap: Record<string, any>; onClose: () => void }> = ({ node, nodeMap, onClose }) => {
  const Icon = typeIcons[node.node_type] ?? Layers;
  const s = typeStyles[node.node_type] ?? typeStyles.ingestion_step;
  const b = typeBadge[node.node_type] ?? typeBadge.ingestion_step;
  const attrs = node.attributes ?? {};
  const prevNodes: string[] = node.prev_nodes ?? [];
  const nextNodes: string[] = node.next_nodes ?? [];

  return (
    <div style={{
      position: "absolute", top: 12, right: 12, zIndex: 20,
      width: 310, maxHeight: "calc(100% - 24px)", overflowY: "auto",
      background: "#fff", borderRadius: 14,
      boxShadow: "0 8px 32px rgba(0,0,0,.16)", border: "1px solid #e2e8f0",
      display: "flex", flexDirection: "column",
    }}>
      {/* Header */}
      <div style={{ background: s.background, borderRadius: "13px 13px 0 0", padding: "14px 14px 12px", display: "flex", alignItems: "flex-start", gap: 10 }}>
        <div style={{ width: 32, height: 32, borderRadius: 8, background: "rgba(255,255,255,0.18)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <Icon size={16} color="#fff" />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{ margin: 0, fontSize: 13, fontWeight: 700, color: "#fff", lineHeight: 1.35, wordBreak: "break-word" }}>{node.node_name}</p>
          <p style={{ margin: "3px 0 0", fontSize: 10, color: "rgba(255,255,255,0.65)", fontFamily: "monospace", wordBreak: "break-all" }}>{node.node_id}</p>
        </div>
        <button onClick={onClose} style={{ background: "rgba(255,255,255,0.2)", border: "none", borderRadius: 6, width: 26, height: 26, display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", flexShrink: 0 }}>
          <X size={14} color="#fff" />
        </button>
      </div>

      {/* Body */}
      <div style={{ padding: "12px 14px" }}>

        {/* Type badge */}
        <span style={{ display: "inline-block", background: b.bg, color: b.text, border: `1px solid ${b.border}`, borderRadius: 5, padding: "2px 9px", fontSize: 11, fontWeight: 600, marginBottom: 10 }}>
          {node.node_type.replace(/_/g, " ")}
        </span>

        {/* Description */}
        {node.description && (
          <div style={{ background: "#f8fafc", borderRadius: 8, padding: "8px 10px", marginBottom: 10 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 4 }}>
              <FileText size={11} color="#94a3b8" />
              <span style={{ fontSize: 10, fontWeight: 600, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.06em" }}>Description</span>
            </div>
            <p style={{ margin: 0, fontSize: 12, color: "#475569", lineHeight: 1.5 }}>{node.description}</p>
          </div>
        )}

        {/* Upstream / Downstream counters */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 10 }}>
          <div style={{ background: "#eff6ff", borderRadius: 8, padding: "8px", textAlign: "center" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 4, marginBottom: 2 }}>
              <ArrowLeft size={11} color="#1d4ed8" />
              <span style={{ fontSize: 10, fontWeight: 600, color: "#1d4ed8", textTransform: "uppercase" }}>Upstream</span>
            </div>
            <p style={{ margin: 0, fontSize: 22, fontWeight: 700, color: "#1d4ed8" }}>{prevNodes.length}</p>
          </div>
          <div style={{ background: "#f0fdf4", borderRadius: 8, padding: "8px", textAlign: "center" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 4, marginBottom: 2 }}>
              <ArrowRight size={11} color="#059669" />
              <span style={{ fontSize: 10, fontWeight: 600, color: "#059669", textTransform: "uppercase" }}>Downstream</span>
            </div>
            <p style={{ margin: 0, fontSize: 22, fontWeight: 700, color: "#059669" }}>{nextNodes.length}</p>
          </div>
        </div>

        {/* Attributes */}
        {Object.entries(attrs).filter(([, v]) => v !== null && v !== undefined).length > 0 && (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: 5, margin: "4px 0" }}>
              <Tag size={11} color="#94a3b8" />
              <span style={{ fontSize: 10, fontWeight: 600, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.06em" }}>Attributes</span>
            </div>
            {Object.entries(attrs)
              .filter(([, v]) => v !== null && v !== undefined)
              .map(([k, v]) => (
                <InfoRow
                  key={k}
                  label={k.replace(/_/g, " ")}
                  value={
                    typeof v === "object"
                      ? <pre style={{ margin: 0, fontSize: 10, fontFamily: "monospace", background: "#f8fafc", borderRadius: 4, padding: "4px 6px", overflow: "auto", maxHeight: 80, color: "#475569" }}>{JSON.stringify(v, null, 2)}</pre>
                      : String(v)
                  }
                />
              ))}
          </>
        )}

        {/* Upstream list */}
        {prevNodes.length > 0 && (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: 5, margin: "10px 0 5px" }}>
              <ArrowLeft size={11} color="#1d4ed8" />
              <span style={{ fontSize: 10, fontWeight: 600, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.06em" }}>Upstream nodes</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
              {prevNodes.map((id) => {
                const n = nodeMap[id];
                return (
                  <div key={id} style={{ display: "flex", alignItems: "center", gap: 7, background: "#f8fafc", borderRadius: 6, padding: "5px 8px" }}>
                    <span style={{ width: 8, height: 8, borderRadius: 2, background: typeStyles[n?.node_type]?.background ?? "#94a3b8", flexShrink: 0 }} />
                    <span style={{ fontSize: 11, color: "#475569", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{n?.node_name ?? id}</span>
                  </div>
                );
              })}
            </div>
          </>
        )}

        {/* Downstream list */}
        {nextNodes.length > 0 && (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: 5, margin: "10px 0 5px" }}>
              <ArrowRight size={11} color="#059669" />
              <span style={{ fontSize: 10, fontWeight: 600, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.06em" }}>Downstream nodes ({nextNodes.length})</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 3, maxHeight: 150, overflowY: "auto" }}>
              {nextNodes.map((id) => {
                const n = nodeMap[id];
                return (
                  <div key={id} style={{ display: "flex", alignItems: "center", gap: 7, background: "#f8fafc", borderRadius: 6, padding: "5px 8px" }}>
                    <span style={{ width: 8, height: 8, borderRadius: 2, background: typeStyles[n?.node_type]?.background ?? "#94a3b8", flexShrink: 0 }} />
                    <span style={{ fontSize: 11, color: "#475569", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{n?.node_name ?? id}</span>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
};

/* ── Main Component ── */
const LineageGraphModal: React.FC<Props> = ({ selectedNode, nodeMap }) => {
  const [clickedNode, setClickedNode] = useState<any>(null);
  const { sideNavWidth } = useOutletContext();

  const { nodes, edges } = useMemo(() => {
    if (!selectedNode) return { nodes: [], edges: [] };
    const { visitedIds, edges: rawEdges } = collectLineage(selectedNode.node_id, nodeMap);

    const rfNodes = Array.from(visitedIds)
      .filter((id) => nodeMap[id])
      .map((id) => {
        const node = nodeMap[id];
        const isMain = id === selectedNode.node_id;
        const s = isMain ? MAIN_STYLE : (typeStyles[node.node_type] ?? typeStyles.ingestion_step);
        return {
          id,
          data: { label: node.node_name ?? id },
          style: {
            width: NODE_W, minHeight: NODE_H, padding: "10px 14px", borderRadius: "12px",
            border: `1.5px solid ${s.border}`, background: s.background, color: s.color,
            fontSize: "12px", fontWeight: isMain ? 700 : 500,
            display: "flex", alignItems: "center", justifyContent: "center",
            textAlign: "center" as const, whiteSpace: "normal" as const,
            wordBreak: "break-word" as const, overflowWrap: "break-word" as const,
            lineHeight: "16px", boxShadow: s.shadow, cursor: "pointer",
            outline: isMain ? "3px solid rgba(255,255,255,0.5)" : "none",
            outlineOffset: "2px",
            transition: "box-shadow 0.15s ease",
          },
        };
      });

    const rfEdges = rawEdges.map(({ source, target }) => ({
      id: `${source}→${target}`, source, target, type: "smoothstep",
      markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: "#94a3b8" },
      style: { stroke: "#94a3b8", strokeWidth: 1.5 },
    }));

    return layoutGraph(rfNodes, rfEdges);
  }, [selectedNode, nodeMap]);

  const handleNodeClick: NodeMouseHandler = useCallback((_e, rfNode) => {
    setClickedNode(nodeMap[rfNode.id] ?? null);
  }, [nodeMap]);

  if (!selectedNode) {
    return <div className="h-full flex items-center justify-center text-gray-500">No lineage data available</div>;
  }

  const legendItems = [
    { label: "Data source",    s: typeStyles.data_source },
    { label: "Ingestion step", s: typeStyles.ingestion_step },
    { label: "Table",          s: typeStyles.table },
    { label: "Relationship",   s: typeStyles.relationship },
    { label: "Calculation",    s: typeStyles.calculation },
    { label: "Visual",         s: typeStyles.visual },
    { label: "Selected",       s: MAIN_STYLE },
  ];

  return (
    <div style={{ width: "100%", height: "100%",      marginLeft: `${sideNavWidth + 24}px`,
    position: "relative", display: "flex", flexDirection: "column" }}>

      {/* Legend */}
      <div style={{
        position: "absolute", top: 12, left: 12, zIndex: 10,
        display: "flex", flexWrap: "wrap", gap: 6,
        background: "rgba(255,255,255,0.95)", borderRadius: 10,
        padding: "8px 10px", boxShadow: "0 2px 8px rgba(0,0,0,.10)",
        border: "1px solid #e2e8f0", maxWidth: 380,
      }}>
        {legendItems.map(({ label, s }) => (
          <span key={label} style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11, color: "#475569", fontWeight: 500 }}>
            <span style={{ width: 12, height: 12, borderRadius: 3, background: s.background, border: `1px solid ${s.border}`, display: "inline-block", flexShrink: 0 }} />
            {label}
          </span>
        ))}
      </div>

      {/* Hint bar */}
      <div style={{
        position: "absolute", bottom: 50, left: 12, zIndex: 10,
        fontSize: 11, color: "#64748b", background: "rgba(255,255,255,0.92)",
        borderRadius: 6, padding: "4px 10px", border: "1px solid #e2e8f0",
        display: "flex", alignItems: "center", gap: 6,
      }}>
        <Hash size={11} color="#94a3b8" />
        {nodes.length} nodes · {edges.length} edges
        <span style={{ color: "#94a3b8", marginLeft: 4 }}>· Click any node for details</span>
      </div>

      {/* React Flow */}
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodeClick={handleNodeClick}
        fitView
        fitViewOptions={{ padding: 0.18 }}
        minZoom={0.08}
        maxZoom={2}
        style={{ flex: 1 }}
      >
        <MiniMap nodeColor={(n) => (n.style as any)?.background ?? "#e2e8f0"} maskColor="rgba(240,244,248,0.75)" style={{ border: "1px solid #e2e8f0", borderRadius: 8 }} />
        <Controls />
        <Background color="#e2e8f0" gap={20} size={1} />
      </ReactFlow>

      {/* Info panel */}
      {clickedNode && (
        <NodeInfoPanel node={clickedNode} nodeMap={nodeMap} onClose={() => setClickedNode(null)} />
      )}
    </div>
  );
};

export default LineageGraphModal;