import React, { useEffect, useState } from "react";
import "@xyflow/react/dist/style.css";
import {
  Background,
  Controls,
  ReactFlow,
  ReactFlowProvider,
  applyNodeChanges,
  applyEdgeChanges,
  MiniMap,
  useReactFlow
} from "@xyflow/react";
import TableNode from "./TableNode";
import { lineageData } from "./lineageData";
import { useSelector } from "react-redux";
import { RootState } from "../../utils/Store";
import NodeLineage from "./NodeLineage.tsx";
import dagre from "dagre";

export default function TableColumnLineage() {
  const [lineageType, setLineageType] = useState("field");
  return (
    <ReactFlowProvider>
      {lineageType === "json" ? <NodeLineage /> : <ColumnLineageContent lineageType={lineageType} setLineageType={setLineageType} />}
    </ReactFlowProvider>
  );
}

const NodeColorLegend = () => (
  <div style={{
    padding: '10px 12px',
    borderRadius: '8px',
    background: '#fff',
    boxShadow: '0 0 8px rgba(0,0,0,0.1)',
    fontSize: '14px',
    fontWeight: 500,
    display: 'flex',
    flexDirection: 'row',
    alignItems: 'center',
    gap: '20px',
  }}>
    {[
      { label: 'Start Node', color: 'rgba(255,230,165,100)' },
      { label: 'Intermediate Node', color: 'rgba(255, 255,255,100)' },
      { label: 'End Node', color: 'rgba(255, 190,194,100)' },
    ].map((item, index) => (
      <div key={index} style={{ display: 'flex', alignItems: 'center' }}>
        <div style={{ width: '12px', height: '12px',     border: '1px solid grey', background: item.color, borderRadius: '3px', marginRight: '8px' }} />
        {item.label}
      </div>
    ))}
  </div>
);

const ColumnLineageContent = ({ lineageType, setLineageType }) => {
  const reduxData = useSelector((state: RootState) => state.apiData.data);
  const localStorageData = localStorage.getItem('analyzeResponse');
  const parsedLocalData = localStorageData ? JSON.parse(localStorageData) : null;
  const dataToUse = parsedLocalData || reduxData;
  const lineageData = dataToUse.fieldleveljsonlineage || [];
  const [isJson, setIsJson] = useState(false);
  const [selectedLineageKey, setSelectedLineageKey] = useState(Object.keys(lineageData[0])[0]);
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [expandedNodes, setExpandedNodes] = useState({});
  const [selectedColumn, setSelectedColumn] = useState(null);
  const { fitView } = useReactFlow();
  const [searchQuery, setSearchQuery] = useState("");

  const tableColors = {
    start: "rgba(255,230,165,100)",
    intermediate: "rgba(255,255,255,100)",
    end: "rgba(255, 190,194,100)",
    isolated: "#d1d5db"
  };

  const determineTableType = (nodeId, edges) => {
    const hasIncoming = edges.some(e => e.target === nodeId && e.type === "table");
    const hasOutgoing = edges.some(e => e.source === nodeId && e.type === "table");

    if (hasOutgoing && !hasIncoming) return "start";
    if (hasIncoming && !hasOutgoing) return "end";
    if (hasIncoming && hasOutgoing) return "intermediate";
    return "isolated";
  };

  const getCurrentLineage = () => {
    const current = lineageData.find(item => item[selectedLineageKey]);
    return current ? current[selectedLineageKey] : { nodes: [], edges: [] };
  };

  const handleToggle = () => {
    setIsJson(!isJson);
    handleDropdownChange({ target: { value: !isJson ? "json" : "field" } });
  };

  const handleDropdownChange = (e) => {
    setLineageType(e.target.value);
  }

 const updateNodesAndEdges = () => {
  const { nodes: lineageNodes, edges: lineageEdges } = getCurrentLineage();

  const allNodesWithType = lineageNodes.map(n => ({
    ...n,
    tableType: determineTableType(n.id, lineageEdges),
  }));

  // ----------------------------
  // Dagre layout
  // ----------------------------
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  dagreGraph.setGraph({ rankdir: "LR", nodesep: 60, ranksep: 80 });

  allNodesWithType.forEach(node => dagreGraph.setNode(node.id, { width: 240, height: 80 }));
  lineageEdges.forEach(edge => dagreGraph.setEdge(edge.source, edge.target));

  dagre.layout(dagreGraph);

  // ----------------------------
  // Apply layout positions
  // ----------------------------
  const layoutedNodes = allNodesWithType.map(node => {
    const nodeWithPos = dagreGraph.node(node.id);
    return {
      ...node,
      type: "tableNode",
      position: { x: nodeWithPos.x - 120, y: nodeWithPos.y - 40 }, // center by subtracting half width/height
      data: { label: node.label, columns: node.columns, tableType: node.tableType },
      draggable: true,
    };
  });

  const edgeList = lineageEdges.map((e, idx) => ({
    id: e.sourceHandle && e.targetHandle
      ? `col-${e.source}-${e.sourceHandle}-${e.target}-${e.targetHandle}`
      : `table-${e.source}-${e.target}-${idx}`,
    source: e.source,
    sourceHandle: e.sourceHandle || "table",
    target: e.target,
    targetHandle: e.targetHandle || "table",
    animated: true,
    markerEnd: { type: "arrowclosed" },
    style: { strokeWidth: 2 }
  }));

  setNodes(layoutedNodes);
  setEdges(edgeList);

  // ----------------------------
  // Optional: center the graph without zooming
  // ----------------------------
  setTimeout(() => {
    fitView({ padding: 0, maxZoom: 1, minZoom: 1, duration: 0 }); // keep normal zoom
  }, 50);
};


  useEffect(() => {
    updateNodesAndEdges();
  }, [selectedLineageKey]);

  useEffect(() => {
    if (!searchQuery) {
      setNodes(prev => prev.map(n => ({ ...n, style: { ...n.style, border: "3px solid transparent" } })));
      return;
    }
    const lowerQuery = searchQuery.toLowerCase();
    setNodes(prev =>
      prev.map(n => ({
        ...n,
        style: { ...n.style, border: n.data.label.toLowerCase().includes(lowerQuery) ? "3px solid gold" : "3px solid transparent" }
      }))
    );
  }, [searchQuery]);

  const buildColumnGraph = () => {
    const graph = {};
    edges.forEach(edge => {
      if (!edge.sourceHandle || !edge.targetHandle) return;
      const src = `${edge.source}.${edge.sourceHandle}`;
      const tgt = `${edge.target}.${edge.targetHandle}`;
      if (!graph[src]) graph[src] = [];
      if (!graph[tgt]) graph[tgt] = [];
      graph[src].push(tgt);
      graph[tgt].push(src);
    });
    return graph;
  };

  const getConnectedChain = start => {
    const graph = buildColumnGraph();
    const visited = new Set();
    const stack = [start];
    while (stack.length) {
      const node = stack.pop();
      if (!visited.has(node)) {
        visited.add(node);
        (graph[node] || []).forEach(next => stack.push(next));
      }
    }
    return visited;
  };

  let highlightedColumns = new Set();
  const highlightColor = "#aceb00ff";

  if (selectedColumn) {
    const start = nodes
      .flatMap(n => (n.data.columns || []).filter(c => c.id === selectedColumn).map(c => `${n.id}.${c.id}`))[0];
    if (start) highlightedColumns = getConnectedChain(start);
  }

  const styledEdges = edges.map(edge => {
    const src = `${edge.source}.${edge.sourceHandle}`;
    const tgt = `${edge.target}.${edge.targetHandle}`;
    const isHighlighted = highlightedColumns.has(src) && highlightedColumns.has(tgt);
    return {
      ...edge,
      animated: isHighlighted,
      style: {
        ...edge.style,
        stroke: isHighlighted ? highlightColor : "#99999980",
        strokeWidth: isHighlighted ? 3 : 1.5,
        opacity: isHighlighted ? 1 : 0.5
      }
    };
  });

  const visibleEdges = styledEdges
    .map(edge => {
      const isTableEdge = edge.sourceHandle === "table" && edge.targetHandle === "table";
      const sourceExpanded = !!expandedNodes[edge.source];
      const targetExpanded = !!expandedNodes[edge.target];
      if (isTableEdge) {
        if (!(sourceExpanded && targetExpanded)) return edge;
        return null;
      }
      if (sourceExpanded && targetExpanded) return edge;
      return null;
    })
    .filter(Boolean);

  const onNodesChange = changes => setNodes(nds => applyNodeChanges(changes, nds));
  const onEdgesChange = changes => setEdges(eds => applyEdgeChanges(changes, eds));

  const onLineageChange = e => {
    setSelectedLineageKey(e.target.value);
    setExpandedNodes({});
    setSelectedColumn(null);
  };

  return (
    <div style={{ width: "100vw", height: "calc(100vh - 100px)", position: "relative" }}>
      <div style={{ position: "absolute", right: 10, top: 10, zIndex: 10 }}>
        <select value={selectedLineageKey} onChange={onLineageChange} style={{
          borderRadius: '28px', padding: '6px 10px', fontSize: '16px', height: '40px',
          border: '1px solid rgba(79, 141, 192, 1)', margin: '0 10px', maxWidth: '220px'
        }}>
          {lineageData.map(item => Object.keys(item).map(key => (
            <option key={key} value={key}>{key}</option>
          )))}
        </select>

        <input
          type="text"
          placeholder="Search table name"
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          style={{
            borderRadius: '28px',
            padding: '6px 10px',
            fontSize: '16px',
            height: '40px',
            border: '1px solid rgba(79, 141, 192, 1)',
            maxWidth: '220px'
          }}
        />

        <div
          style={{
            position: "absolute",
            width: "200px",
            height: "40px",
            borderRadius: "20px",
            backgroundColor: "#ccc",
            cursor: "pointer",
            userSelect: "none",
            display: "flex",
            top: '0%',
            right: '100%',
          }}
          onClick={handleToggle}
        >
          <div
            style={{
              flex: 1,
              textAlign: "center",
              lineHeight: "40px",
              fontWeight: "bold",
              color: isJson ? "white" : "#333",
              zIndex: 1,
            }}
          >
            JSON
          </div>
          <div
            style={{
              flex: 1,
              textAlign: "center",
              lineHeight: "40px",
              fontWeight: "bold",
              color: !isJson ? "white" : "#333",
              zIndex: 1,
            }}
          >
            Field Level
          </div>

          <div
            style={{
              position: "absolute",
              top: "2px",
              left: isJson ? "2px" : "100px",
              width: "96px",
              height: "36px",
              borderRadius: "18px",
              backgroundColor: "#4F8DC0",
              transition: "left 0.3s",
              zIndex: 0,
            }}
          />
        </div>
      </div>

      <ReactFlow
        nodes={nodes}
        edges={visibleEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={{
          tableNode: props => (
            <TableNode
              {...props}
              expanded={expandedNodes[props.id]}
              selectedColumn={selectedColumn}
              onColumnClick={colId => {
                setSelectedColumn(colId);
                const start = nodes.flatMap(n =>
                  (n.data.columns || []).filter(c => c.id === colId).map(c => `${n.id}.${c.id}`)
                )[0];
                if (!start) return;
                const connectedColumns = getConnectedChain(start);
                const tablesToExpand = {};
                nodes.forEach(n => {
                  if ((n.data.columns || []).some(c => connectedColumns.has(`${n.id}.${c.id}`))) {
                    tablesToExpand[n.id] = true;
                  }
                });
                setExpandedNodes(prev => ({ ...prev, ...tablesToExpand }));

                // scroll/zoom to the clicked table node
                const node = nodes.find(n =>
                  (n.data.columns || []).some(c => c.id === colId)
                );
                if (node) {
                  // setTimeout(() => {
                  //   fitView({ nodes: [node], padding: 0.4, duration: 800 });
                  // }, 350);
                }
              }}
              onToggleExpand={() =>
                setExpandedNodes(prev => ({ ...prev, [props.id]: !prev[props.id] }))
              }
            />
          )
        }}
      >
        <Background />
        <MiniMap />
        <Controls style={{ top: '30px' }} />
        <div style={{ position: 'absolute', top: 5, left: '17%', zIndex: 1000 }}>
          <NodeColorLegend />
        </div>
      </ReactFlow>
    </div>
  );
};
