import React, { useMemo, useState } from "react";
import { DataModel } from "../../data/sampleModel";
import {
  Search,
  Database,
  Table2,
  GitBranch,
  Calculator,
  BarChart3,
  Layers,
  Eye,
  FileJson,
  X,
  ChevronUp,
  ChevronDown,
  Download,
  ChevronLeft,
  ChevronRight,
  List,
} from "lucide-react";
import ContentCard from "../../core/CardContent/CardContent.tsx";
import FileWorkspaceHeader from "../../core/FileWorkspaceHeader.tsx";
import { useOutletContext, useLocation } from "react-router-dom";
import { Typography } from "@mui/material";
import LineageGraphModal from "./LineageGraphModal.tsx";
import * as XLSX from "xlsx";

interface ConsolidatedProps {
  model: DataModel;
}

const typeConfig: Record<string, { icon: any; badge: string; dot: string }> = {
  data_source: {
    icon: Database,
    badge: "bg-blue-50 text-blue-700 border-blue-200",
    dot: "bg-blue-500",
  },
  table: {
    icon: Table2,
    badge: "bg-emerald-50 text-emerald-700 border-emerald-200",
    dot: "bg-emerald-500",
  },
  relationship: {
    icon: GitBranch,
    badge: "bg-purple-50 text-purple-700 border-purple-200",
    dot: "bg-purple-500",
  },
  calculation: {
    icon: Calculator,
    badge: "bg-amber-50 text-amber-700 border-amber-200",
    dot: "bg-amber-500",
  },
  visual: {
    icon: BarChart3,
    badge: "bg-pink-50 text-pink-700 border-pink-200",
    dot: "bg-pink-500",
  },
  ingestion_step: {
    icon: Layers,
    badge: "bg-slate-50 text-slate-700 border-slate-200",
    dot: "bg-slate-400",
  },
};

const ROWS_PER_PAGE_OPTIONS = [25, 50, 100, 200];

type SortDir = "asc" | "desc" | null;

interface SortState {
  column: string;
  dir: SortDir;
}

const Badge = ({ label, cls }: { label: string; cls: string }) => (
  <span
    className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium border whitespace-nowrap ${cls}`}
  >
    {label}
  </span>
);

const SortIcon = ({
  column,
  sort,
}: {
  column: string;
  sort: SortState;
}) => {
  if (sort.column !== column)
    return (
      <span className="ml-1 text-slate-300 text-[10px] font-bold leading-none select-none">
        ⇅
      </span>
    );
  if (sort.dir === "asc")
    return <ChevronUp size={13} className="text-slate-700 ml-1 flex-shrink-0" />;
  return <ChevronDown size={13} className="text-slate-700 ml-1 flex-shrink-0" />;
};

const ConsolidatedModelTable = ({ model }: ConsolidatedProps) => {
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [sort, setSort] = useState<SortState>({ column: "", dir: null });
  const [page, setPage] = useState(1);
  const [rowsPerPage, setRowsPerPage] = useState(50);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

  const [selectedNode, setSelectedNode] = useState<any>(null);
  const [showLineageModal, setShowLineageModal] = useState(false);
  const [showAttributesModal, setShowAttributesModal] = useState(false);

  const { sideNavWidth } = useOutletContext<{ sideNavWidth: number }>();
  const location = useLocation();

  React.useEffect(() => {
    const state = location.state as { globalSearch?: string } | null;
    if (state?.globalSearch) {
      setSearch(state.globalSearch);
      setTypeFilter("calculation"); // focus strictly on calculations
      setPage(1);
      window.history.replaceState({}, '');
    }
  }, [location.state]);

  const nodes: any[] = model?.consolidated_model?.node_graph?.nodes || [];

  const nodeMap = useMemo(() => {
    const map: Record<string, any> = {};
    nodes.forEach((n) => (map[n.node_id] = n));
    return map;
  }, [nodes]);

  const getAttrSummary = (attrs: any): string => {
    if (!attrs) return "—";
    const parts: string[] = [];
    if (attrs.table_type) parts.push(`type: ${attrs.table_type}`);
    if (attrs.column_count !== undefined)
      parts.push(`cols: ${attrs.column_count}`);
    if (attrs.source_type) parts.push(`src: ${attrs.source_type}`);
    if (attrs.step_type) parts.push(`step: ${attrs.step_type}`);
    if (attrs.page) parts.push(`page: ${attrs.page}`);
    if (attrs.visual_type) parts.push(`visual: ${attrs.visual_type}`);
    if (attrs.semantic_type) parts.push(`sem: ${attrs.semantic_type}`);
    return parts.slice(0, 3).join(" · ") || "—";
  };

  const getSource = (node: any): string => {
    if (node.attributes?.source_type) return node.attributes.source_type;
    if (node.attributes?.table) return node.attributes.table;
    if (node.attributes?.page) return node.attributes.page;
    if (node.prev_nodes?.length) return "derived";
    return "—";
  };

  const getTableType = (node: any): string => {
    return (
      node.attributes?.table_type ||
      node.attributes?.step_type ||
      node.attributes?.visual_type ||
      node.attributes?.relationship_type ||
      "—"
    );
  };

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return nodes.filter((n) => {
      const matchType = typeFilter === "all" || n.node_type === typeFilter;
      if (!matchType) return false;
      if (!q) return true;
      return (
        n.node_name?.toLowerCase().includes(q) ||
        n.node_id?.toLowerCase().includes(q) ||
        n.description?.toLowerCase().includes(q) ||
        n.node_type?.toLowerCase().includes(q) ||
        getSource(n).toLowerCase().includes(q) ||
        getTableType(n).toLowerCase().includes(q) ||
        getAttrSummary(n.attributes).toLowerCase().includes(q)
      );
    });
  }, [nodes, search, typeFilter]);

  const sorted = useMemo(() => {
    if (!sort.column || !sort.dir) return filtered;
    return [...filtered].sort((a, b) => {
      let aVal = "";
      let bVal = "";
      switch (sort.column) {
        case "name":
          aVal = a.node_name || "";
          bVal = b.node_name || "";
          break;
        case "type":
          aVal = a.node_type || "";
          bVal = b.node_type || "";
          break;
        case "source":
          aVal = getSource(a);
          bVal = getSource(b);
          break;
        case "tableType":
          aVal = getTableType(a);
          bVal = getTableType(b);
          break;
        case "upstream":
          return sort.dir === "asc"
            ? (a.prev_nodes?.length || 0) - (b.prev_nodes?.length || 0)
            : (b.prev_nodes?.length || 0) - (a.prev_nodes?.length || 0);
        case "downstream":
          return sort.dir === "asc"
            ? (a.next_nodes?.length || 0) - (b.next_nodes?.length || 0)
            : (b.next_nodes?.length || 0) - (a.next_nodes?.length || 0);
        default:
          aVal = a.node_name || "";
          bVal = b.node_name || "";
      }
      const cmp = aVal.localeCompare(bVal);
      return sort.dir === "asc" ? cmp : -cmp;
    });
  }, [filtered, sort]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / rowsPerPage));
  const pageData = useMemo(() => {
    const start = (page - 1) * rowsPerPage;
    return sorted.slice(start, start + rowsPerPage);
  }, [sorted, page, rowsPerPage]);

  const handleSort = (column: string) => {
    setSort((prev) => ({
      column,
      dir:
        prev.column === column
          ? prev.dir === "asc"
            ? "desc"
            : prev.dir === "desc"
            ? null
            : "asc"
          : "asc",
    }));
    setPage(1);
  };

  const allOnPageSelected =
    pageData.length > 0 && pageData.every((n) => selectedIds.has(n.node_id));
  const someOnPageSelected = pageData.some((n) => selectedIds.has(n.node_id));

  const toggleSelectAll = () => {
    if (allOnPageSelected) {
      const next = new Set(selectedIds);
      pageData.forEach((n) => next.delete(n.node_id));
      setSelectedIds(next);
    } else {
      const next = new Set(selectedIds);
      pageData.forEach((n) => next.add(n.node_id));
      setSelectedIds(next);
    }
  };

  const toggleRow = (id: string) => {
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelectedIds(next);
  };

  const toggleExpand = (id: string) => {
    const next = new Set(expandedRows);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setExpandedRows(next);
  };

  const exportCSV = () => {
    const rows =
      selectedIds.size > 0
        ? sorted.filter((n) => selectedIds.has(n.node_id))
        : sorted;
    const header = [
      "Serial No",
      "Node ID",
      "Node Name",
      "Node Type",
      "Description",
      "Source",
      "Table Type",
      "Upstream Count",
      "Downstream Count",
      "Attributes Summary",
    ];
    const lines = rows.map((n, i) =>
      [
        i + 1,
        n.node_id,
        n.node_name,
        n.node_type,
        (n.description || "").replace(/,/g, ";"),
        getSource(n),
        getTableType(n),
        n.prev_nodes?.length || 0,
        n.next_nodes?.length || 0,
        getAttrSummary(n.attributes).replace(/,/g, ";"),
      ].join(",")
    );
    const csv = [header.join(","), ...lines].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "consolidated_model.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const exportJSON = () => {
    const rows =
      selectedIds.size > 0
        ? sorted.filter((n) => selectedIds.has(n.node_id))
        : sorted;
    const blob = new Blob([JSON.stringify(rows, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "consolidated_model.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  const exportExcel = () => {
    const rows =
      selectedIds.size > 0
        ? sorted.filter((n) => selectedIds.has(n.node_id))
        : sorted;

    const data = rows.map((n, i) => ({
      "Serial No": i + 1,
      "Node ID": n.node_id,
      "Node Name": n.node_name,
      "Node Type": n.node_type,
      "Description": n.description || "",
      "Source": getSource(n),
      "Table Type": getTableType(n),
      "Upstream Count": n.prev_nodes?.length || 0,
      "Downstream Count": n.next_nodes?.length || 0,
      "Attributes Summary": getAttrSummary(n.attributes),
    }));

    const worksheet = XLSX.utils.json_to_sheet(data);
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, "Consolidated Model");

    XLSX.writeFile(workbook, "consolidated_model.xlsx");
  };

  const clearSelection = () => setSelectedIds(new Set());

  const totalByType = (type: string) =>
    nodes.filter((n) => n.node_type === type).length;

  const typeFilters = [
    { key: "all", label: "All" },
    { key: "data_source", label: "Sources" },
    { key: "table", label: "Tables" },
    { key: "ingestion_step", label: "Ingestion" },
    { key: "relationship", label: "Relationships" },
    { key: "calculation", label: "Calculations" },
    { key: "visual", label: "Visuals" },
  ];

  const stats = [
    {
      label: "Sources",
      value: totalByType("data_source"),
      icon: Database,
      color: "text-blue-600",
      bg: "bg-blue-50",
    },
    {
      label: "Tables",
      value: totalByType("table"),
      icon: Table2,
      color: "text-emerald-600",
      bg: "bg-emerald-50",
    },
    {
      label: "Relations",
      value: totalByType("relationship"),
      icon: GitBranch,
      color: "text-purple-600",
      bg: "bg-purple-50",
    },
    {
      label: "Calculations",
      value: totalByType("calculation"),
      icon: Calculator,
      color: "text-amber-600",
      bg: "bg-amber-50",
    },
    {
      label: "Visuals",
      value: totalByType("visual"),
      icon: BarChart3,
      color: "text-pink-600",
      bg: "bg-pink-50",
    },
    {
      label: "Total Nodes",
      value: nodes.length,
      icon: Layers,
      color: "text-slate-600",
      bg: "bg-slate-100",
    },
  ];

  return (
    <>
      <ContentCard
        heading={null}
        sideNavWidth={sideNavWidth}
        headerComponent={<FileWorkspaceHeader pageTitle="Calculations" />}
      >
        <div className="space-y-4">
          {/* ── Stats ── */}
          {/* <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
            {stats.map(({ label, value, icon: Icon, color, bg }) => (
              <div
                key={label}
                className="rounded-xl border border-slate-100 bg-white p-3.5 flex items-center gap-3 hover:shadow-sm transition-shadow"
              >
                <div className={`w-9 h-9 rounded-lg ${bg} flex items-center justify-center flex-shrink-0`}>
                  <Icon className={`w-4 h-4 ${color}`} />
                </div>
                <div className="min-w-0">
                  <p className="text-xl font-bold text-slate-900 leading-none">{value.toLocaleString()}</p>
                  <p className="text-xs text-slate-500 mt-0.5 truncate">{label}</p>
                </div>
              </div>
            ))}
          </div> */}

          {/* ── Toolbar ── */}
          <div className="flex flex-wrap gap-3 items-center justify-between">
            <div className="flex flex-wrap gap-3 items-center flex-1">
              {/* Search */}
              <div className="relative min-w-[220px] max-w-sm flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
                <input
                  type="text"
                  placeholder="Search all columns…"
                  value={search}
                  onChange={(e) => { setSearch(e.target.value); setPage(1); }}
                  className="w-full pl-9 pr-4 py-2 text-sm rounded-lg border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-300"
                />
                {search && (
                  <button
                    onClick={() => { setSearch(""); setPage(1); }}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                  >
                    <X size={14} />
                  </button>
                )}
              </div>

              {/* Type filter chips */}
              <div className="flex gap-1.5 flex-wrap">
                {typeFilters.map(({ key, label }) => (
                  <button
                    key={key}
                    onClick={() => { setTypeFilter(key); setPage(1); }}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
                      typeFilter === key
                        ? "bg-slate-900 text-white border-slate-900"
                        : "bg-white text-slate-600 border-slate-200 hover:border-slate-300 hover:bg-slate-50"
                    }`}
                  >
                    {label}
                    {key !== "all" && (
                      <span className={`ml-1.5 rounded px-1 py-0.5 text-[10px] ${
                        typeFilter === key ? "bg-white/20 text-white" : "bg-slate-100 text-slate-500"
                      }`}>
                        {totalByType(key)}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-2 items-center">
              {selectedIds.size > 0 && (
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-blue-50 border border-blue-200 text-blue-700 text-xs font-medium">
                  <span>{selectedIds.size} selected</span>
                  <button onClick={clearSelection} className="hover:text-blue-900">
                    <X size={13} />
                  </button>
                </div>
              )}
              {/* <button
                onClick={exportCSV}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-200 bg-white text-slate-600 text-xs font-medium hover:bg-slate-50 transition-colors"
              >
                <Download size={13} />
                CSV{selectedIds.size > 0 ? ` (${selectedIds.size})` : ""}
              </button>
              <button
                onClick={exportJSON}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-200 bg-white text-slate-600 text-xs font-medium hover:bg-slate-50 transition-colors"
              >
                <Download size={13} />
                JSON{selectedIds.size > 0 ? ` (${selectedIds.size})` : ""}
              </button> */}
              <button
                onClick={exportExcel}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-200 bg-white text-slate-600 text-xs font-medium hover:bg-slate-50 transition-colors"
              >
                <Download size={13} />
                Excel{selectedIds.size > 0 ? ` (${selectedIds.size})` : ""}
              </button>
            </div>
          </div>

          {/* ── Result count ── */}
          <div className="flex flex-wrap items-center justify-between gap-3  px-4 py-3  ">
  
  {/* Left side */}
  <span className="text-sm font-medium text-slate-700">
    Showing{" "}
    <span className="font-semibold text-slate-900">
      {((page - 1) * rowsPerPage + 1).toLocaleString()}
    </span>
    {" - "}
    <span className="font-semibold text-slate-900">
      {Math.min(page * rowsPerPage, sorted.length).toLocaleString()}
    </span>
    {" "}of{" "}
    <span className="font-semibold text-red-600">
      {sorted.length.toLocaleString()}
    </span>{" "}
    nodes
    {search || typeFilter !== "all"
      ? ` (filtered from ${nodes.length})`
      : ""}
  </span>

  {/* Right side */}
  <div className="flex items-center gap-2">
    <span className="text-sm text-slate-600 font-medium">
      Rows per page:
    </span>

    <select
      value={rowsPerPage}
      onChange={(e) => {
        setRowsPerPage(Number(e.target.value));
        setPage(1);
      }}
      className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-800 outline-none focus:border-red-500 focus:ring-1 focus:ring-red-200"
    >
      {ROWS_PER_PAGE_OPTIONS.map((n) => (
        <option key={n} value={n}>
          {n}
        </option>
      ))}
    </select>
  </div>
</div>

          {/* ── Table ── */}
          <div className="rounded-xl border border-slate-200 bg-white overflow-hidden shadow-sm">
            <div
              className="overflow-auto"
              style={{ maxHeight: "65vh" }}
            >
              <table
                className="w-full text-sm border-collapse"
                style={{ minWidth: "1100px" }}
              >
                <thead>
                  <tr
                    style={{
                      borderBottom: "1px solid #e2e8f0",
                      position: "sticky",
                      top: 0,
                      zIndex: 20
                    }}
                  >
                    {/* checkbox */}
                    <th style={{ position: "sticky", left: 0, zIndex: 30, backgroundColor: "#f1f5f9 !important", borderRight: "1px solid #e2e8f0", padding: "10px 12px", width: 48, textAlign: "center" }}>
                      <button onClick={toggleSelectAll}>
                        {allOnPageSelected ? (
                          <span style={{ display: "inline-flex", width: 16, height: 16, borderRadius: 3, border: "2px solid #2563eb", background: "#2563eb", alignItems: "center", justifyContent: "center" }}>
                            <svg viewBox="0 0 10 10" width="8" height="8" fill="none" stroke="white" strokeWidth="2"><polyline points="1.5,5 4,7.5 8.5,2.5"/></svg>
                          </span>
                        ) : someOnPageSelected ? (
                          <span style={{ display: "inline-flex", width: 16, height: 16, borderRadius: 3, border: "2px solid #93c5fd", background: "#eff6ff", alignItems: "center", justifyContent: "center" }}>
                            <span style={{ width: 8, height: 2, background: "#3b82f6", borderRadius: 1 }}></span>
                          </span>
                        ) : (
                          <span style={{ display: "inline-flex", width: 16, height: 16, borderRadius: 3, border: "2px solid #cbd5e1", background: "white" }}></span>
                        )}
                      </button>
                    </th>

                    {/* # */}
                    <th style={{ position: "sticky", left: 48, zIndex: 30, backgroundColor: "#f1f5f9", borderRight: "1px solid #e2e8f0", padding: "10px 12px", width: 40, fontSize: 11, fontWeight: 700, color: "#475569", textTransform: "uppercase", letterSpacing: "0.06em", textAlign: "left" }}>
                      #
                    </th>

                    {/* Node Name */}
                    <th onClick={() => handleSort("name")} style={{ padding: "10px 16px", fontSize: 11, fontWeight: 700, color: "#475569 !important", textTransform: "uppercase", letterSpacing: "0.06em", textAlign: "left", cursor: "pointer", whiteSpace: "nowrap", minWidth: 220, backgroundColor: "#f1f5f9" }}>
                      <span style={{ display: "inline-flex", alignItems: "center" }}>Node Name <SortIcon column="name" sort={sort} /></span>
                    </th>

                    {/* Type */}
                    <th onClick={() => handleSort("type")} style={{ padding: "10px 16px", fontSize: 11, fontWeight: 700, color: "#475569", textTransform: "uppercase", letterSpacing: "0.06em", textAlign: "left", cursor: "pointer", whiteSpace: "nowrap", minWidth: 120, backgroundColor: "#f1f5f9" }}>
                      <span style={{ display: "inline-flex", alignItems: "center" }}>Type <SortIcon column="type" sort={sort} /></span>
                    </th>

                    {/* Source */}
                    <th onClick={() => handleSort("source")} style={{ padding: "10px 16px", fontSize: 11, fontWeight: 700, color: "#475569", textTransform: "uppercase", letterSpacing: "0.06em", textAlign: "left", cursor: "pointer", whiteSpace: "nowrap", minWidth: 110, backgroundColor: "#f1f5f9" }}>
                      <span style={{ display: "inline-flex", alignItems: "center" }}>Source <SortIcon column="source" sort={sort} /></span>
                    </th>

                    {/* Table Type */}
                    <th onClick={() => handleSort("tableType")} style={{ padding: "10px 16px", fontSize: 11, fontWeight: 700, color: "#475569", textTransform: "uppercase", letterSpacing: "0.06em", textAlign: "left", cursor: "pointer", whiteSpace: "nowrap", minWidth: 120, backgroundColor: "#f1f5f9" }}>
                      <span style={{ display: "inline-flex", alignItems: "center" }}>Table Type <SortIcon column="tableType" sort={sort} /></span>
                    </th>

                    {/* Description */}
                    <th style={{ padding: "10px 16px", fontSize: 11, fontWeight: 700, color: "#475569", textTransform: "uppercase", letterSpacing: "0.06em", textAlign: "left", whiteSpace: "nowrap", minWidth: 250, backgroundColor: "#f1f5f9" }}>
                      Description
                    </th>

                    {/* Upstream */}
                    <th onClick={() => handleSort("upstream")} style={{ padding: "10px 16px", fontSize: 11, fontWeight: 700, color: "#475569", textTransform: "uppercase", letterSpacing: "0.06em", textAlign: "left", cursor: "pointer", whiteSpace: "nowrap", minWidth: 100, backgroundColor: "#f1f5f9" }}>
                      <span style={{ display: "inline-flex", alignItems: "center" }}>Upstream <SortIcon column="upstream" sort={sort} /></span>
                    </th>

                    {/* Downstream */}
                    <th onClick={() => handleSort("downstream")} style={{ padding: "10px 16px", fontSize: 11, fontWeight: 700, color: "#475569", textTransform: "uppercase", letterSpacing: "0.06em", textAlign: "left", cursor: "pointer", whiteSpace: "nowrap", minWidth: 110, backgroundColor: "#f1f5f9" }}>
                      <span style={{ display: "inline-flex", alignItems: "center" }}>Downstream <SortIcon column="downstream" sort={sort} /></span>
                    </th>

                    {/* Attributes */}
                    <th style={{ padding: "10px 16px", fontSize: 11, fontWeight: 700, color: "#475569", textTransform: "uppercase", letterSpacing: "0.06em", textAlign: "left", whiteSpace: "nowrap", minWidth: 200, backgroundColor: "#f1f5f9" }}>
                      Attributes
                    </th>

                    {/* Actions — sticky right */}
                    <th style={{ position: "sticky", right: 0, zIndex: 30, backgroundColor: "#f1f5f9", borderLeft: "1px solid #e2e8f0", padding: "10px 16px", fontSize: 11, fontWeight: 700, color: "#475569", textTransform: "uppercase", letterSpacing: "0.06em", textAlign: "center", whiteSpace: "nowrap", minWidth: 120 }}>
                      Actions
                    </th>
                  </tr>
                </thead>

                <tbody>
                  {pageData.length === 0 && (
                    <tr>
                      <td colSpan={12} className="px-6 py-16 text-center text-slate-400 text-sm">
                        No nodes match your search or filters.
                      </td>
                    </tr>
                  )}

                  {pageData.map((node, idx) => {
                    const config = typeConfig[node.node_type] || typeConfig.table;
                    const Icon = config.icon;
                    const globalIdx = (page - 1) * rowsPerPage + idx + 1;
                    const isSelected = selectedIds.has(node.node_id);
                    const isExpanded = expandedRows.has(node.node_id);

                    return (
                      <React.Fragment key={node.node_id}>
                        <tr
                          className={`border-b border-slate-100 transition-colors ${
                            isSelected
                              ? "bg-blue-50"
                              : idx % 2 === 0
                              ? "bg-white hover:bg-slate-50"
                              : "bg-slate-50 hover:bg-slate-100"
                          }`}
                          style={{ "--row-bg": isSelected ? "#eff6ff" : idx % 2 === 0 ? "#ffffff" : "#f8fafc" } as React.CSSProperties}
                        >
                          {/* Checkbox — sticky */}
                          <td
                            className="sticky left-0 z-10 border-r border-slate-100 px-3 py-3 text-center"
                            style={{ backgroundColor: isSelected ? "#eff6ff" : idx % 2 === 0 ? "#ffffff" : "#f8fafc" }}
                          >
                            <button
                              onClick={() => toggleRow(node.node_id)}
                            >
                              {isSelected ? (
                                <span style={{ display: "inline-flex", width: 16, height: 16, borderRadius: 3, border: "2px solid #2563eb", background: "#2563eb", alignItems: "center", justifyContent: "center" }}>
                                  <svg viewBox="0 0 10 10" width="8" height="8" fill="none" stroke="white" strokeWidth="2"><polyline points="1.5,5 4,7.5 8.5,2.5"/></svg>
                                </span>
                              ) : (
                                <span style={{ display: "inline-flex", width: 16, height: 16, borderRadius: 3, border: "2px solid #cbd5e1", background: "white" }}></span>
                              )}
                            </button>
                          </td>

                          {/* Serial — sticky */}
                          <td
                            className="sticky left-12 z-10 border-r border-slate-100 px-3 py-3 text-xs text-slate-400 font-mono"
                            style={{ backgroundColor: isSelected ? "#eff6ff" : idx % 2 === 0 ? "#ffffff" : "#f8fafc" }}
                          >
                            {globalIdx}
                          </td>

                          {/* Node Name */}
                          <td className="px-4 py-3">
                            <div className="flex items-start gap-2.5">
                              <div className={`w-7 h-7 rounded-md flex items-center justify-center flex-shrink-0 mt-0.5 ${
                                typeConfig[node.node_type]?.badge.split(" ")[0] || "bg-slate-100"
                              }`}>
                                <Icon className="w-3.5 h-3.5" />
                              </div>
                              <div className="min-w-0">
                                <p className="font-medium text-slate-800 text-[13px] leading-snug truncate max-w-[180px]" title={node.node_name}>
                                  {node.node_name}
                                </p>
                                <p className="text-[10px] text-slate-400 font-mono truncate max-w-[180px] mt-0.5" title={node.node_id}>
                                  {node.node_id}
                                </p>
                              </div>
                            </div>
                          </td>

                          {/* Type */}
                          <td className="px-4 py-3">
                            <Badge
                              label={node.node_type.replace(/_/g, " ")}
                              cls={config.badge}
                            />
                          </td>

                          {/* Source */}
                          <td className="px-4 py-3 text-[12px] text-slate-600 font-medium">
                            {getSource(node)}
                          </td>

                          {/* Table Type */}
                          <td className="px-4 py-3 text-[12px] text-slate-500">
                            {getTableType(node) !== "—" ? (
                              <span className="px-1.5 py-0.5 bg-slate-100 rounded text-slate-600 text-[11px]">
                                {getTableType(node)}
                              </span>
                            ) : (
                              <span className="text-slate-300">—</span>
                            )}
                          </td>

                          {/* Description */}
                          <td className="px-4 py-3 max-w-[250px]">
                            <p className="text-[12px] text-slate-500 leading-relaxed line-clamp-2" title={node.description}>
                              {node.description || <span className="text-slate-300">No description</span>}
                            </p>
                          </td>

                          {/* Upstream */}
                          <td className="px-4 py-3 text-center">
                            {(node.prev_nodes?.length || 0) > 0 ? (
                              <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-slate-100 text-slate-700 text-xs font-semibold">
                                {node.prev_nodes.length}
                              </span>
                            ) : (
                              <span className="text-slate-300 text-sm">—</span>
                            )}
                          </td>

                          {/* Downstream */}
                          <td className="px-4 py-3 text-center">
                            {(node.next_nodes?.length || 0) > 0 ? (
                              <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-blue-50 text-blue-700 text-xs font-semibold">
                                {node.next_nodes.length}
                              </span>
                            ) : (
                              <span className="text-slate-300 text-sm">—</span>
                            )}
                          </td>

                          {/* Attributes */}
                          <td className="px-4 py-3">
                            <p className="text-[11px] text-slate-400 font-mono leading-relaxed truncate max-w-[200px]" title={getAttrSummary(node.attributes)}>
                              {getAttrSummary(node.attributes)}
                            </p>
                          </td>

                          {/* Actions — sticky */}
                          <td
                            className="sticky right-0 z-10 border-l border-slate-100 px-3 py-3"
                            style={{ backgroundColor: isSelected ? "#eff6ff" : idx % 2 === 0 ? "#ffffff" : "#f8fafc" }}
                          >
                            <div className="flex items-center gap-1.5 justify-center">
                              <button
                                onClick={() => {
                                  setSelectedNode(node);
                                  setShowLineageModal(true);
                                }}
                                title="View Lineage"
                                className="p-1.5 rounded-md bg-blue-50 text-blue-600 hover:bg-blue-100 transition-colors"
                              >
                                <Eye size={13} />
                              </button>
                              <button
                                onClick={() => {
                                  setSelectedNode(node);
                                  setShowAttributesModal(true);
                                }}
                                title="View Attributes"
                                className="p-1.5 rounded-md bg-slate-100 text-slate-600 hover:bg-slate-200 transition-colors"
                              >
                                <FileJson size={13} />
                              </button>
                              <button
                                onClick={() => toggleExpand(node.node_id)}
                                title="Expand Details"
                                className={`p-1.5 rounded-md transition-colors ${
                                  isExpanded
                                    ? "bg-emerald-100 text-emerald-700"
                                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                                }`}
                              >
                              <List size={13} />
                              </button>
                            </div>
                          </td>
                        </tr>

                        {/* Expanded detail row */}
                        {isExpanded && (
                          <tr className="bg-slate-50/80 border-b border-slate-200">
                            <td colSpan={12} className="px-6 py-4">
                              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                {/* Prev nodes */}
                                <div>
                                  <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide mb-2">
                                    Upstream nodes ({node.prev_nodes?.length || 0})
                                  </p>
                                  {node.prev_nodes?.length ? (
                                    <div className="space-y-1">
                                      {node.prev_nodes.map((id: string) => (
                                        <div key={id} className="text-[11px] font-mono bg-white border border-slate-200 rounded px-2 py-1 text-slate-600 truncate">
                                          {nodeMap[id]?.node_name || id}
                                        </div>
                                      ))}
                                    </div>
                                  ) : (
                                    <p className="text-[11px] text-slate-400">No upstream dependencies</p>
                                  )}
                                </div>

                                {/* Next nodes */}
                                <div>
                                  <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide mb-2">
                                    Downstream nodes ({node.next_nodes?.length || 0})
                                  </p>
                                  {node.next_nodes?.length ? (
                                    <div className="space-y-1 max-h-40 overflow-y-auto">
                                      {node.next_nodes.map((id: string) => (
                                        <div key={id} className="text-[11px] font-mono bg-white border border-slate-200 rounded px-2 py-1 text-slate-600 truncate">
                                          {nodeMap[id]?.node_name || id}
                                        </div>
                                      ))}
                                    </div>
                                  ) : (
                                    <p className="text-[11px] text-slate-400">No downstream consumers</p>
                                  )}
                                </div>

                                {/* Raw attributes */}
                                <div>
                                  <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide mb-2">
                                    Raw attributes
                                  </p>
                                  <pre className="text-[10px] font-mono bg-white border border-slate-200 rounded p-2 overflow-auto max-h-40 text-slate-600 whitespace-pre-wrap">
                                    {JSON.stringify(node.attributes, null, 2)}
                                  </pre>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* ── Pagination ── */}
            <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100 bg-slate-50/50">
              <span className="text-xs text-slate-500">
                Page {page} of {totalPages} · {sorted.length.toLocaleString()} total rows
              </span>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setPage(1)}
                  disabled={page === 1}
                  className="p-1.5 rounded hover:bg-slate-200 disabled:opacity-30 disabled:cursor-not-allowed text-slate-600"
                >
                  <ChevronLeft size={14} />
                </button>
                {/* Page number buttons */}
                {Array.from({ length: Math.min(7, totalPages) }, (_, i) => {
                  let p: number;
                  if (totalPages <= 7) {
                    p = i + 1;
                  } else if (page <= 4) {
                    p = i + 1;
                  } else if (page >= totalPages - 3) {
                    p = totalPages - 6 + i;
                  } else {
                    p = page - 3 + i;
                  }
                  return (
                    <button
                      key={p}
                      onClick={() => setPage(p)}
                      className={`min-w-[30px] h-7 px-2 rounded text-xs font-medium transition-colors ${
                        p === page
                          ? "bg-slate-900 text-white"
                          : "text-slate-600 hover:bg-slate-200"
                      }`}
                    >
                      {p}
                    </button>
                  );
                })}
                <button
                  onClick={() => setPage(totalPages)}
                  disabled={page === totalPages}
                  className="p-1.5 rounded hover:bg-slate-200 disabled:opacity-30 disabled:cursor-not-allowed text-slate-600"
                >
                  <ChevronRight size={14} />
                </button>
              </div>
            </div>
          </div>
        </div>
      </ContentCard>

      {/* ── Attributes Modal ── */}
      {showAttributesModal && selectedNode && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-6">
          <div className="bg-white w-[70vw] max-h-[80vh] rounded-2xl shadow-2xl overflow-hidden flex flex-col">
            <div className="flex justify-between items-center px-6 py-4 border-b bg-slate-50">
              <div>
                <h2 className="text-base font-semibold text-slate-900">
                  {selectedNode.node_name}
                </h2>
                <p className="text-xs text-slate-500 font-mono mt-0.5">{selectedNode.node_id}</p>
              </div>
              <div className="flex items-center gap-2">
                <Badge
                  label={selectedNode.node_type.replace(/_/g, " ")}
                  cls={typeConfig[selectedNode.node_type]?.badge || "bg-slate-50 text-slate-700 border-slate-200"}
                />
                <button
                  onClick={() => { setShowAttributesModal(false); setSelectedNode(null); }}
                  className="w-8 h-8 rounded-full hover:bg-slate-200 flex items-center justify-center transition-colors"
                >
                  <X size={16} />
                </button>
              </div>
            </div>

            <div className="p-6 overflow-y-auto flex-1">
              {/* Key-value grid for top-level attrs */}
              {selectedNode.attributes && (
                <div className="grid grid-cols-2 gap-3 mb-6">
                  {Object.entries(selectedNode.attributes).map(([k, v]) => {
                    if (typeof v === "object") return null;
                    return (
                      <div key={k} className="bg-slate-50 rounded-lg px-3 py-2.5">
                        <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide">{k.replace(/_/g, " ")}</p>
                        <p className="text-sm text-slate-800 mt-0.5 font-mono break-all">{String(v ?? "—")}</p>
                      </div>
                    );
                  })}
                </div>
              )}

              <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-2">Full JSON</p>
              <pre className="text-xs bg-slate-50 border border-slate-200 p-4 rounded-xl overflow-auto whitespace-pre-wrap break-words text-slate-600 font-mono">
                {JSON.stringify(selectedNode.attributes, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      )}

      {/* ── Lineage Modal (full-screen) ── */}
      {showLineageModal && selectedNode && (
        <div className="fixed inset-0 z-50 bg-black/50 flex flex-col" style={{ left: sideNavWidth + 20}}>
          <div className="flex items-center justify-between px-6 py-4 bg-white border-b border-slate-200 flex-shrink-0">
            <div className="flex items-center gap-3">
              <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                typeConfig[selectedNode.node_type]?.badge.split(" ")[0] || "bg-slate-100"
              }`}>
                {React.createElement(
                  typeConfig[selectedNode.node_type]?.icon || Layers,
                  { size: 16 }
                )}
              </div>
              <div>
                <h2 className="text-base font-semibold text-slate-900">
                  {selectedNode.node_name}
                </h2>
                <p className="text-xs text-slate-500">
                  Upstream &amp; downstream lineage ·{" "}
                  {selectedNode.prev_nodes?.length || 0} upstream ·{" "}
                  {selectedNode.next_nodes?.length || 0} downstream
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Badge
                label={selectedNode.node_type.replace(/_/g, " ")}
                cls={typeConfig[selectedNode.node_type]?.badge || "bg-slate-50 text-slate-700 border-slate-200"}
              />
              <button
                onClick={() => { setShowLineageModal(false); setSelectedNode(null); }}
                className="w-9 h-9 rounded-full hover:bg-slate-100 flex items-center justify-center transition-colors"
              >
                <X size={18} />
              </button>
            </div>
          </div>

          <div className="flex-1 bg-slate-100 overflow-hidden">
            <div className="w-full h-full bg-white">
              <LineageGraphModal
                selectedNode={selectedNode}
                nodesData={nodes}
                nodeMap={nodeMap}
              />
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default ConsolidatedModelTable;
