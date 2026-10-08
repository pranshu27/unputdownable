import { Handle, Position, useUpdateNodeInternals } from "@xyflow/react";
import { FiDatabase, FiHash } from "react-icons/fi";
import { useRef, useEffect, useCallback } from "react";

const tableColors = {
  start: "rgba(255,230,165,100)",
  intermediate: "rgba(255, 255,255,100)",
  end: "rgba(255, 190,194,100)",
  isolated: "rgba(209, 213, 219, 0.6)",
};

export default function TableNode({
  id,
  data,
  expanded,
  onToggleExpand,
  onColumnClick,
  selectedColumn,
}) {
  const rowHeight = 40;
  const headerHeight = 40;
  const headerColor = tableColors[data.tableType] || "#eef2ff";

  const scrollContainerRef = useRef(null);
  const columnRefs = useRef({});
  const updateNodeInternals = useUpdateNodeInternals();

  // ✅ Force React Flow to recalc edge positions
  const triggerRecalculate = useCallback(() => {
    requestAnimationFrame(() => updateNodeInternals(id));
  }, [id, updateNodeInternals]);

  // ✅ Recalculate edges whenever scrolling happens
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    const handleScroll = () => {
      triggerRecalculate();
    };

    container.addEventListener("scroll", handleScroll);
    return () => container.removeEventListener("scroll", handleScroll);
  }, [triggerRecalculate]);

  // ✅ Auto-scroll to selected column & recalc edges
  useEffect(() => {
    if (expanded && selectedColumn && columnRefs.current[selectedColumn]) {
      const columnEl = columnRefs.current[selectedColumn];
      const container = scrollContainerRef.current;

      if (container && columnEl) {
        const containerRect = container.getBoundingClientRect();
        const columnRect = columnEl.getBoundingClientRect();

        const isAbove = columnRect.top < containerRect.top;
        const isBelow = columnRect.bottom > containerRect.bottom;

        if (isAbove || isBelow) {
          columnEl.scrollIntoView({ behavior: "smooth", block: "center" });
          // small delay to allow scroll animation, then recalc
          setTimeout(triggerRecalculate, 350);
        } else {
          triggerRecalculate();
        }
      }
    }
  }, [selectedColumn, expanded, triggerRecalculate]);

  return (
    <div
      style={{
        border: "1px solid #d2d6ff",
        borderRadius: 28,
        background: "#fff",
        width: 260,
        position: "relative",
        boxShadow: "0 2px 6px rgba(0,0,0,0.08)",
        overflow: "visible",
      }}
    >
      {/* Header */}
      <div
        style={{
          background: headerColor,
          padding: "10px",
          fontWeight: 600,
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: 8,
          fontSize: 14,
          borderRadius: "28px",
          height: headerHeight,
        }}
        onClick={onToggleExpand}
      >
        <span
          style={{
            maxWidth: 170,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            color:'grey !important'
          }}
          title={data.label}
        >
          {data.label}
        </span>
        <span style={{ marginLeft: "auto", fontSize: 12 }}>
          {expanded ? "▲" : "▼"}
        </span>
      </div>

      {/* Table-level Handles */}
      <Handle
        type="target"
        id="table"
        position={Position.Left}
        style={{
          left: -6,
          top: "50%",
          width: 8,
          height: 8,
          background: "#2563eb",
          visibility: expanded ? "hidden" : "visible",
        }}
      />
      <Handle
        type="source"
        id="table"
        position={Position.Right}
        style={{
          right: -6,
          top: "50%",
          width: 8,
          height: 8,
          background: "#16a34a",
          visibility: expanded ? "hidden" : "visible",
        }}
      />

      {/* Columns Header */}
      {expanded && data.columns?.length > 0 && (
        <div
          style={{
            padding: "8px 10px 4px",
            fontSize: 12,
            fontWeight: 600,
            color: "#3b82f6",
            borderBottom: "1px solid #e5e7eb",
          }}
        >
          Columns
        </div>
      )}

      {/* Columns List */}
      {expanded && (
        <div
          ref={scrollContainerRef}
          style={{
            maxHeight: rowHeight * 10,
            overflowY: "auto",
            overflowX: "hidden",
            position: "relative",
            paddingRight: 4,
          }}
        >
          {data.columns?.map((col) => {
            const isSelected = selectedColumn === col.id;
            return (
              <div
                key={col.id}
                ref={(el) => (columnRefs.current[col.id] = el)}
                onClick={() => onColumnClick(col.id)}
                style={{
                  height: rowHeight,
                  padding: "6px 10px",
                  borderBottom: "1px solid #f2f2f2",
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  position: "relative",
                  cursor: "pointer",
                  background: isSelected ? "#fff4e6" : "#fff",
                  borderLeft: isSelected
                    ? "3px solid #ff7a00"
                    : "3px solid transparent",
                  zIndex: 5,
                }}
              >
                <div
                  style={{
                    width: 20,
                    height: 20,
                    borderRadius: "50%",
                    background: "#eef2ff",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    marginRight: 8,
                    flexShrink: 0,
                  }}
                >
                  <FiHash size={14} style={{ color: "#0284c7" }} />
                </div>
                <div style={{ display: "flex", flexDirection: "column" }}>
                  <span style={{ fontSize: 13, color: "grey", fontWeight: 500 }}>
                    {col.label}
                  </span>
                  {col.datatype && (
                    <span style={{ fontSize: 11, color: "#6b7280" }}>
                      {col.datatype}
                    </span>
                  )}
                </div>

                {/* Column Handles */}
                <Handle
                  type="target"
                  id={col.id}
                  position={Position.Left}
                  style={{
                    position: "absolute",
                    left: -6,
                    top: "50%",
                    transform: "translateY(-50%)",
                    width: 8,
                    height: 8,
                    background: "#2563eb",
                    zIndex: 10,
                  }}
                />
                <Handle
                  type="source"
                  id={col.id}
                  position={Position.Right}
                  style={{
                    position: "absolute",
                    right: -6,
                    top: "50%",
                    transform: "translateY(-50%)",
                    width: 8,
                    height: 8,
                    background: "#16a34a",
                    zIndex: 10,
                  }}
                />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
