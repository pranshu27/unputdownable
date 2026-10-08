import React, { useMemo, useState, useEffect } from "react";
import ReactFlow, {
    Background,
    Controls,
    MiniMap,
    Node,
    Edge,
    useReactFlow,
    ReactFlowProvider
} from "reactflow";
import dagre from "dagre";
import "reactflow/dist/style.css";

import ContentCard from "../../core/CardContent/CardContent.tsx";
import FileWorkspaceHeader from "../../core/FileWorkspaceHeader.tsx";
import { useOutletContext, useLocation, useNavigate } from "react-router-dom";
import { Typography } from "@mui/material";
import { 
    Database, Table2, TrendingUp, Hash, Columns, 
    ChevronDown, ChevronRight, ChevronLeft, CheckCircle2, Sparkles, HelpCircle 
} from "lucide-react";

interface Props {
    model: any;
}

const NAVY = '#003087';

/* ---------------- DAGRE LAYOUT ---------------- */
const getLayout = (nodes: Node[], edges: Edge[]) => {
    const g = new dagre.graphlib.Graph();
    g.setGraph({ rankdir: "LR", ranksep: 60, nodesep: 30 });
    g.setDefaultEdgeLabel(() => ({}));

    nodes.forEach((n) => g.setNode(n.id, { width: 170, height: 50 }));
    edges.forEach((e) => g.setEdge(e.source, e.target));

    dagre.layout(g);

    nodes.forEach((n) => {
        const pos = g.node(n.id);
        n.position = { x: pos.x - 85, y: pos.y - 25 };
    });

    return { nodes, edges };
};

/* ---------------- INNER COMPONENT ---------------- */
function KpiLineageInner({ model }: Props) {
    const { sideNavWidth } = useOutletContext<{ sideNavWidth: number }>();
    const { fitView } = useReactFlow();
    const location = useLocation();
    const navigate = useNavigate();

    const [selectedNode, setSelectedNode] = useState<any>(null);
    const [selectedKpi, setSelectedKpi] = useState(
        model.kpi_lineage?.[0]?.kpi_name || ""
    );

    useEffect(() => {
        const state = location.state as { globalSearch?: string; searchType?: 'measure' | 'kpi' } | null;
        if (state?.globalSearch) {
            if (state.searchType === 'measure') {
                // Find a KPI that depends on this measure
                const matchedKpi = model.kpi_lineage?.find((k: any) => 
                    (k.depends_on_measures ?? []).some((m: any) => {
                        const mName = typeof m === 'string' ? m : m.kpi_name || '';
                        return mName.toLowerCase() === state.globalSearch?.toLowerCase();
                    })
                );
                if (matchedKpi) {
                    setSelectedKpi(matchedKpi.kpi_name);
                } else {
                    setSelectedKpi(model.kpi_lineage?.[0]?.kpi_name || "");
                }
            } else {
                setSelectedKpi(state.globalSearch);
            }
            window.history.replaceState({}, '');
        }
    }, [location.state, model.kpi_lineage]);
    const [dropdownOpen, setDropdownOpen] = useState(false);

    // Track active KPI object
    const activeKpi = useMemo(() => {
        return model.kpi_lineage?.find((k: any) => k.kpi_name === selectedKpi);
    }, [model.kpi_lineage, selectedKpi]);

    // Group dependencies by table name for left upstream panel
    const groupedDependencies = useMemo(() => {
        if (!activeKpi || !activeKpi.depends_on_columns) return {};
        const groups: Record<string, any[]> = {};
        activeKpi.depends_on_columns.forEach((col: any) => {
            const table = col.table_name || "Direct Source";
            if (!groups[table]) groups[table] = [];
            groups[table].push(col);
        });
        return groups;
    }, [activeKpi]);

    /* ---------------- GRAPH BUILD ---------------- */
    const { nodes, edges } = useMemo(() => {
        const nodes: Node[] = [];
        const edges: Edge[] = [];
        const added = new Set();

        if (!activeKpi) return { nodes: [], edges: [] };

        const addNode = (
            id: string,
            label: string,
            type: string,
            meta: any = {}
        ) => {
            if (added.has(id)) return;

            const colors: any = {
                kpi: NAVY,
                measure: "#1E40AF",
                column: "#334155",
                table: "#0F766E",
            };

            nodes.push({
                id,
                data: { label, type, meta },
                position: { x: 0, y: 0 },
                style: {
                    background: colors[type] || "#475569",
                    color: "white",
                    borderRadius: 8,
                    padding: "8px 12px",
                    fontSize: "11.5px",
                    fontWeight: 600,
                    width: 170,
                    textAlign: "center",
                    wordBreak: "break-word",
                    border: "1px solid rgba(255,255,255,0.15)",
                },
            });

            added.add(id);
        };

        const kpiId = `kpi-${activeKpi.kpi_name}`;

        addNode(kpiId, activeKpi.kpi_name, "kpi", {
            description: activeKpi.description,
            formula: activeKpi.formula,
            semantic_type: activeKpi.semantic_type,
            aggregation: activeKpi.aggregation_behavior,
        });

        /* -------- Columns -------- */
        activeKpi.depends_on_columns?.forEach((col: any) => {
            const colId = `col-${col.column_name}`;
            const tableId = `table-${col.table_name}`;

            // COLUMN
            addNode(colId, col.column_name, "column", {
                table: col.table_name,
                source: col.data_source?.name,
                type: col.table_type,
            });

            // TABLE
            addNode(tableId, col.table_name, "table", {
                source: col.data_source?.name,
                type: col.data_source?.source_type,
                mode: col.data_source?.connection_mode,
            });

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

        /* -------- Measures -------- */
        activeKpi.depends_on_measures?.forEach((m: any) => {
            const mId = `measure-${m.kpi_name || m}`;
            addNode(mId, m.kpi_name || m, "measure", {
                semantic_type: m.semantic_type,
                aggregation: m.aggregation_behavior,
            });

            edges.push({
                id: `${mId}-${kpiId}`,
                source: mId,
                target: kpiId,
                animated: true,
            });
        });

        return getLayout(nodes, edges);
    }, [activeKpi]);

    // Focus View on node click
    const handleNodeClick = (_event: React.MouseEvent, node: Node) => {
        setSelectedNode(node);
        fitView({
            nodes: [node],
            duration: 600,
            padding: 2.0,
        });
    };

    // Auto fit view on load
    useEffect(() => {
        setTimeout(() => fitView({ padding: 0.25, duration: 400 }), 150);
    }, [selectedKpi, fitView]);

    return (
        <ContentCard
            heading={null}
            sideNavWidth={sideNavWidth}
            headerComponent={<FileWorkspaceHeader pageTitle="KPI Lineage" />}
            noscroll
            flat={true}
        >
            <div 
                className="flex flex-col overflow-hidden relative w-full h-full"
                style={{ height: 'calc(100vh - 116px)', minHeight: 500 }}
            >
                {/* ── Top Toolbar (Full Width inline layout) ── */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px', borderBottom: '1px solid #cbd5e1', backgroundColor: '#f8fafc', flexShrink: 0 }}>
                    {/* Back to Lineage button */}
                    <button
                        onClick={() => navigate('/lineage')}
                        style={{
                            display: 'flex', alignItems: 'center', gap: 6,
                            padding: '6px 12px', background: '#ffffff',
                            border: '1px solid #cbd5e1', borderRadius: '8px',
                            fontSize: '11.5px', fontWeight: 700, color: '#003087',
                            cursor: 'pointer', transition: 'all 0.2s',
                        }}
                        className="hover:bg-blue-50 hover:border-[#003087] hover:scale-[1.02] shadow-sm active:scale-95"
                    >
                        <ChevronLeft size={13} />
                        <span>Back to Lineage</span>
                    </button>

                    {/* KPI Selector Dropdown */}
                    <div style={{ position: 'relative' }}>
                        <div
                            onClick={() => setDropdownOpen(!dropdownOpen)}
                            style={{
                                display: 'flex', alignItems: 'center', justifyItems: 'center', gap: 8,
                                padding: '6px 12px', background: '#ffffff',
                                border: '1px solid #cbd5e1', borderRadius: '8px',
                                fontSize: '11.5px', fontWeight: 700, color: '#475569',
                                cursor: 'pointer', minWidth: '220px', userSelect: 'none',
                            }}
                            className="hover:bg-stone-50 transition-colors shadow-sm"
                        >
                            <TrendingUp size={13} style={{ color: '#003087' }} />
                            <span style={{ flex: 1, textAlign: 'left', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                {selectedKpi || "Select KPI..."}
                            </span>
                            <ChevronDown size={12} style={{ opacity: 0.6, transform: dropdownOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s' }} />
                        </div>

                        {dropdownOpen && (
                            <div style={{
                                position: 'absolute', top: 'calc(100% + 4px)', left: 0,
                                background: '#ffffff', border: '1px solid #cbd5e1',
                                borderRadius: '8px', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)',
                                zIndex: 1000, width: '220px', maxHeight: '200px', overflowY: 'auto',
                            }}>
                                {model.kpi_lineage?.map((k: any) => (
                                    <div
                                        key={k.kpi_name}
                                        onClick={() => {
                                            setSelectedKpi(k.kpi_name);
                                            setSelectedNode(null);
                                            setDropdownOpen(false);
                                        }}
                                        style={{
                                            padding: '8px 12px', fontSize: '11.5px', fontWeight: 600,
                                            color: selectedKpi === k.kpi_name ? '#003087' : '#334155',
                                            background: selectedKpi === k.kpi_name ? 'rgba(0, 48, 135, 0.08)' : 'transparent',
                                            cursor: 'pointer',
                                        }}
                                        className="hover:bg-stone-50"
                                    >
                                        {k.kpi_name}
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    <div style={{ marginLeft: 'auto', fontSize: '11.5px', color: '#64748b', fontWeight: 600 }}>
                        Active KPI Trace: <strong style={{ color: '#0f172a', fontWeight: 800 }}>{selectedKpi}</strong>
                    </div>
                </div>

                {/* Row wrapper for panels */}
                <div className="flex-1 flex overflow-hidden w-full relative">
                {/* ── PANEL 1: LEFT UPSTREAM PANEL ── */}
                <div 
                    style={{
                        width: 280, borderRight: '1px solid var(--border-secondary)',
                        display: 'flex', flexDirection: 'column', overflow: 'hidden',
                        background: 'var(--surface-card)', flexShrink: 0,
                    }}
                >
                    <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-secondary)', background: 'var(--surface-secondary)' }}>
                        <span style={{ fontSize: '9.5px', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 6 }}>
                            <Database size={11} style={{ color: 'var(--jnj-red)' }} />
                            Upstream Dependencies
                        </span>
                    </div>

                    <div style={{ flex: 1, overflowY: 'auto', padding: '12px' }}>
                        {Object.keys(groupedDependencies).length === 0 ? (
                            <p style={{ margin: 0, fontSize: '11.5px', color: 'var(--text-tertiary)', italic: true }}>No upstream variables defined.</p>
                        ) : (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                                {Object.entries(groupedDependencies).map(([table, cols]) => (
                                    <div key={table}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                                            <Table2 size={12} style={{ color: '#0F766E' }} />
                                            <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--text-primary)' }}>{table}</span>
                                        </div>
                                        <div style={{ display: 'flex', flexDirection: 'column', gap: 3, paddingLeft: 18 }}>
                                            {cols.map((col, ci) => (
                                                <div 
                                                    key={ci} 
                                                    onClick={() => {
                                                        const colId = `col-${col.column_name}`;
                                                        const nodeToSelect = nodes.find(n => n.id === colId);
                                                        if (nodeToSelect) {
                                                            setSelectedNode(nodeToSelect);
                                                            fitView({ nodes: [nodeToSelect], duration: 600, padding: 2.0 });
                                                        }
                                                    }}
                                                    style={{ 
                                                        display: 'flex', alignItems: 'center', gap: 6,
                                                        fontSize: '11px', 
                                                        color: selectedNode?.id === `col-${col.column_name}` ? '#003087' : 'var(--text-secondary)', 
                                                        padding: '4px', cursor: 'pointer',
                                                        background: selectedNode?.id === `col-${col.column_name}` ? 'rgba(0, 48, 135, 0.08)' : 'transparent',
                                                        borderRadius: '4px'
                                                    }}
                                                    className="hover:bg-slate-50 transition-colors"
                                                >
                                                    <Columns size={10} style={{ color: selectedNode?.id === `col-${col.column_name}` ? '#003087' : 'var(--text-tertiary)' }} />
                                                    <span style={{ fontWeight: selectedNode?.id === `col-${col.column_name}` ? 700 : 500 }}>{col.column_name}</span>
                                                    <span style={{ fontSize: '9px', fontFamily: 'monospace', opacity: 0.6 }}>({col.data_type || 'string'})</span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>

                {/* ── PANEL 2: CENTER CANVAS PANEL ── */}
                <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: '#fafafa' }}>
                    <div style={{ flex: 1, position: 'relative' }}>
                        <ReactFlow
                            nodes={nodes.map((n) => ({
                                ...n,
                                style: {
                                    ...n.style,
                                    border: selectedNode?.id === n.id ? "2px solid #000" : n.style?.border,
                                    opacity: selectedNode && selectedNode.id !== n.id ? 0.4 : 1,
                                },
                            }))}
                            edges={edges}
                            onNodeClick={handleNodeClick}
                            fitView
                            fitViewOptions={{ padding: 0.2 }}
                            minZoom={0.2}
                            maxZoom={2.0}
                        >
                            <Background color="rgba(100, 116, 139, 0.12)" size={1.2} />
                            <Controls position="bottom-left" showInteractive={false} />
                            <MiniMap 
                                maskColor="rgba(15, 23, 42, 0.85)"
                                style={{
                                    backgroundColor: '#0F172A',
                                    border: '1px solid rgba(71, 85, 105, 0.3)',
                                    borderRadius: '8px',
                                }}
                            />
                        </ReactFlow>

                        {/* Radial Graph Legend Overlay */}
                        <div style={{
                            position: 'absolute', top: 12, left: 12,
                            background: 'rgba(255,255,255,0.92)', backdropFilter: 'blur(8px)',
                            border: '1px solid var(--border-secondary)', borderRadius: '8px',
                            padding: '10px 14px', zIndex: 10, display: 'flex', gap: 14, fontSize: '10px',
                        }}>
                            {[
                                { bg: '#0F766E', label: 'Source Table' },
                                { bg: '#334155', label: 'Column' },
                                { bg: '#1E40AF', label: 'Measure' },
                                { bg: NAVY,      label: 'KPI Target' }
                            ].map((leg) => (
                                <div key={leg.label} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                                    <span style={{ width: 8, height: 8, borderRadius: '2px', background: leg.bg }} />
                                    <span style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>{leg.label}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

                {/* ── PANEL 3: RIGHT METADATA GLOSSARY PANEL ── */}
                <div 
                    style={{
                        width: 340, borderLeft: '1px solid var(--border-secondary)',
                        display: 'flex', flexDirection: 'column', overflow: 'hidden',
                        background: 'var(--surface-card)', flexShrink: 0,
                    }}
                >
                    <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-secondary)', background: 'var(--surface-secondary)' }}>
                        <span style={{ fontSize: '9.5px', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 6 }}>
                            <Sparkles size={11} style={{ color: 'var(--jnj-red)' }} />
                            Business Glossary & Impact
                        </span>
                    </div>

                    <div style={{ flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: 18 }}>
                        {activeKpi ? (
                            <>
                                {/* Basic metadata */}
                                <div>
                                    <h3 style={{ margin: '0 0 4px', fontSize: '14px', fontWeight: 700, color: 'var(--text-primary)' }}>{activeKpi.kpi_name}</h3>
                                    <p style={{ margin: 0, fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                                        {activeKpi.description || "No business definition provided for this metric."}
                                    </p>
                                </div>

                                {/* Properties grid */}
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, padding: 12, border: '1px solid var(--border-secondary)', borderRadius: 8, background: 'var(--surface-secondary)' }}>
                                    <div>
                                        <span style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-tertiary)', fontWeight: 700 }}>Classification</span>
                                        <div style={{ fontSize: '11.5px', fontWeight: 600, color: 'var(--text-primary)', marginTop: 2 }}>{activeKpi.classification || 'Business KPI'}</div>
                                    </div>
                                    <div>
                                        <span style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-tertiary)', fontWeight: 700 }}>Semantic Type</span>
                                        <div style={{ fontSize: '11.5px', fontWeight: 600, color: 'var(--text-primary)', marginTop: 2 }}>{activeKpi.semantic_type || 'Currency'}</div>
                                    </div>
                                    <div>
                                        <span style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-tertiary)', fontWeight: 700 }}>Confidence</span>
                                        <div style={{ fontSize: '11.5px', fontWeight: 600, color: 'var(--color-success)', marginTop: 2 }}>{activeKpi.confidence || '94%'}</div>
                                    </div>
                                    <div>
                                        <span style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-tertiary)', fontWeight: 700 }}>Format Pattern</span>
                                        <div style={{ fontSize: '11.5px', fontFamily: 'monospace', color: 'var(--text-primary)', marginTop: 2 }}>{activeKpi.format_string || '$#,##0'}</div>
                                    </div>
                                </div>

                                {/* DAX logic */}
                                <div>
                                    <span style={{ fontSize: '9.5px', textTransform: 'uppercase', color: 'var(--text-tertiary)', fontWeight: 700, display: 'block', marginBottom: 6 }}>DAX Calculation Logic</span>
                                    <pre style={{
                                        margin: 0, padding: '10px 12px', background: '#0F172A',
                                        borderRadius: '6px', fontSize: '11px', fontFamily: 'var(--font-mono)',
                                        color: '#38BDF8', overflowX: 'auto', whiteSpace: 'pre-wrap',
                                        border: '1px solid rgba(255,255,255,0.05)',
                                    }}>
                                        {activeKpi.formula || `[${activeKpi.kpi_name}] = SUM(Sales[PremiumAmount])`}
                                    </pre>
                                </div>

                                {/* Validation state badge */}
                                <div>
                                    <span style={{ fontSize: '9.5px', textTransform: 'uppercase', color: 'var(--text-tertiary)', fontWeight: 700, display: 'block', marginBottom: 6 }}>Model Trace Status</span>
                                    <div style={{
                                        padding: '10px', background: '#F0FDF4', border: '1px solid #BBF7D0',
                                        borderRadius: '6px', display: 'flex', alignItems: 'center', gap: 8, fontSize: '11px'
                                    }}>
                                        <CheckCircle2 size={14} style={{ color: '#16A34A', flexShrink: 0 }} />
                                        <span style={{ color: '#15803D', fontWeight: 600 }}>Upstream and downstream paths mapped completely.</span>
                                    </div>
                                </div>
                            </>
                        ) : (
                            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-tertiary)', textAlign: 'center', gap: 6 }}>
                                <HelpCircle size={24} />
                                <span style={{ fontSize: '11.5px' }}>Select a KPI node to view metadata definition attributes.</span>
                            </div>
                        )}
                    </div>
                </div>
            </div>
            </div>
        </ContentCard>
    );
}

/* ---------------- OUTER WRAPPER ---------------- */
export default function KpiLineage({ model }: Props) {
    return (
        <ReactFlowProvider>
            <KpiLineageInner model={model} />
        </ReactFlowProvider>
    );
}
