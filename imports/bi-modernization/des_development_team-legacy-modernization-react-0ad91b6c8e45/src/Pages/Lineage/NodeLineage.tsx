import React, { useCallback, useMemo, useState, useEffect } from 'react';
import '@xyflow/react/dist/style.css';
import {
  applyEdgeChanges,
  applyNodeChanges,
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Node,
  type Edge,
  type ColorMode,
  ReactFlowProvider,
  useReactFlow,
} from '@xyflow/react';
import ContentCard from '../../core/CardContent/CardContent.tsx';
import { Typography, Box, Tooltip, IconButton } from '@mui/material';
import { useOutletContext } from 'react-router-dom';
import dagre from 'dagre';
import './Lineage.scss';
import { useSelector } from 'react-redux';
import { RootState } from '../../utils/Store';
import { ChevronLeft, ChevronRight } from '@mui/icons-material';
import { getNodesBounds, getViewportForBounds } from '@xyflow/react';
import Loader from '../../core/Loader/Loader.tsx';
import { toPng } from 'html-to-image';
import TableColumnLineage from './TableColumnLineage.tsx';

const nodeWidth = 240;
const nodeHeight = 80;

const getStartAndEndNodes = (nodes: any[], edges: any[]) => {
  const nodeInDegree: Record<string, number> = {};
  const nodeOutDegree: Record<string, number> = {};

  edges.forEach((edge) => {
    nodeOutDegree[edge.start] = (nodeOutDegree[edge.start] || 0) + 1;
    nodeInDegree[edge.end] = (nodeInDegree[edge.end] || 0) + 1;
  });

  const startNodes = nodes.filter((n) => !nodeInDegree[n.id]);
  const endNodes = nodes.filter((n) => !nodeOutDegree[n.id]);

  return { startNodes, endNodes };
};

const getLayoutedElements = (
  nodes: any[],
  edges: any[],
  direction: 'TB' | 'LR' = 'LR',
  viewportWidth = 1000,
  viewportHeight = 600
) => {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  dagreGraph.setGraph({ rankdir: direction, nodesep: 60, ranksep: 80 });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.start, edge.end);
  });

  dagre.layout(dagreGraph);

  const { startNodes, endNodes } = getStartAndEndNodes(nodes, edges);

  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  nodes.forEach((node) => {
    const pos = dagreGraph.node(node.id);
    if (!pos) return;
    const { x, y } = pos;
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x);
    maxY = Math.max(maxY, y);
  });

  const offsetX = (viewportWidth - (maxX - minX + nodeWidth)) / 2 - minX;
  const offsetY = (viewportHeight - (maxY - minY + nodeHeight)) / 2 - minY;

  const layoutedNodes: Node[] = nodes.map((node) => {
    const { x, y } = dagreGraph.node(node.id);
    const isStart = startNodes.some((n) => n.id === node.id);
    const isEnd = endNodes.some((n) => n.id === node.id);

    return {
      id: node.id,
      data: {
        label: (
          <Tooltip title={node.name} arrow>
            <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              {node.name}
            </div>
          </Tooltip>
        ),
        description: node.description || [],
      },
      position: { x: x + offsetX, y: y + offsetY },
      sourcePosition: direction === 'LR' ? 'right' : 'bottom',
      targetPosition: direction === 'LR' ? 'left' : 'top',
      style: {
        width: nodeWidth,
        height: nodeHeight,
        padding: '10px',
        color: '#fff',
        border: '3px solid transparent',
        borderRadius: 8,
        background: isStart ? 'rgba(0, 48, 135, 1)' : isEnd ? 'rgba(197, 22, 45, 1)' : 'rgba(79, 141, 192, 1)',
        fontSize: '14px',
        boxShadow: '0 2px 6px rgba(0,0,0,0.1)',
        textAlign: 'center',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
      },
    };
  });

  const layoutedEdges: Edge[] = edges.map((edge, index) => (
    {
    id: `e-${edge.start}-${edge.end}-${index}`,
    source: edge.start,
    target: edge.end,
    animated: true,
    style: { stroke: '#888' },
    markerEnd: { type: 'arrowclosed', color: '#888' },
    data: { fields: edge.fields?.[0] || '' },
  }));

  return { layoutedNodes, layoutedEdges, startNodes };
};

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
      { label: 'Start Node', color: 'rgba(0, 48, 135, 1)' },
      { label: 'Intermediate Node', color: 'rgba(79, 141, 192, 1)' },
      { label: 'End Node', color: 'rgba(197, 22, 45, 1)' },
    ].map((item, index) => (
      <div key={index} style={{ display: 'flex', alignItems: 'center' }}>
        <div style={{ width: '8px', height: '8px', background: item.color, borderRadius: '2px', marginRight: '8px' }} />
        {item.label}
      </div>
    ))}
  </div>
);

const NodeLineageContent = ({ lineageType, setLineageType }) => {
  const { sideNavWidth } = useOutletContext();
  const reduxData = useSelector((state: RootState) => state.apiData.data);
  const localStorageData = localStorage.getItem('analyzeResponse');
  const parsedLocalData = localStorageData ? JSON.parse(localStorageData) : null;
  const dataToUse = parsedLocalData || reduxData;
  console.log(dataToUse);
  const { setCenter } = useReactFlow();
  const [query, setQuery] = useState('');
  const fieldlevelResponse = dataToUse?.fieldleveljsonlineage || dataToUse?.jsonlineage;
  const [selectedLineageIndex, setSelectedLineageIndex] = useState(0);
  const lineageArray = dataToUse?.jsonlineage || [];

  let selectedLineage = null;
  let lineageKeys: string[] = [];

  if (lineageArray.length > 0) {
    const firstItem = lineageArray[selectedLineageIndex];

    // CASE 1: Direct structure { nodes, edges }
    if (firstItem?.nodes && firstItem?.edges) {
      selectedLineage = firstItem;
      lineageKeys = [`Lineage ${selectedLineageIndex + 1}`];
    }

    // CASE 2: Wrapped structure { key: { nodes, edges } }
    else {
      lineageKeys = Object.keys(firstItem);
      const selectedKey = lineageKeys[0];
      selectedLineage = firstItem[selectedKey];
    }
  }
  const { layoutedNodes, layoutedEdges, startNodes } = useMemo(
    () => getLayoutedElements(selectedLineage?.nodes || [], selectedLineage?.edges || []),
    [selectedLineageIndex]
  );

  const [showLineage, setShowLineage] = useState(true);
  const [searchError, setSearchError] = useState<string>("");
  const [nodes, setNodes] = useState<Node[]>(layoutedNodes);
  const [edges, setEdges] = useState<Edge[]>(layoutedEdges);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<Edge | null>(null);
  const [colorMode, setColorMode] = useState<ColorMode>('light');
  const [isOpen, setIsOpen] = useState(true);
  const [loading, setLoading] = useState(false);
  const [isJson, setIsJson] = useState(true);

  const togglePanel = () => setIsOpen((prev) => !prev);

  useEffect(() => {
    if (startNodes && startNodes.length > 0) {
      const startNode = layoutedNodes.find(n => n.id === startNodes[0].id);
      if (startNode) setSelectedNode(startNode);
    }
  }, [layoutedNodes, startNodes]);

  useEffect(() => {
    setNodes(layoutedNodes);
    setEdges(layoutedEdges);
  }, [layoutedNodes, layoutedEdges]);

  useEffect(() => {
    setNodes((prev) =>
      prev.map((n) => ({
        ...n,
        style: {
          ...n.style,
          border: selectedNode && n.id === selectedNode.id ? '3px solid gold' : '3px solid transparent',
        },
      }))
    );
  }, [selectedNode]);

  const onNodesChange = useCallback((changes) => setNodes((nds) => applyNodeChanges(changes, nds)), []);
  const onEdgesChange = useCallback((changes) => setEdges((eds) => applyEdgeChanges(changes, eds)), []);
  const onNodeClick = useCallback((_, node: Node) => {
    setSelectedNode(node);
    setSelectedEdge(null);
    setIsOpen(true);
  }, []);
  const onEdgeClick = useCallback((_, edge: Edge) => {
    setSelectedEdge(edge);
    setSelectedNode(null);
    setIsOpen(true);
  }, []);

  const handleToggle = () => {
    setIsJson((prev) => {
      const newValue = !prev;
      setLineageType(newValue ? "json" : "field");
      return newValue;
    });
  };

  const handleSearch = () => {
    const searchText = query.trim().toLowerCase();

    const node = nodes.find((n: any) => {
      const label = n.data?.label?.props?.title?.toLowerCase() || '';
      return n.id.toLowerCase().includes(searchText) || label.includes(searchText);
    });

    if (node) {
      setSearchError("");
      setNodes((nds) =>
        nds.map((n) =>
          n.id === node.id
            ? { ...n, style: { ...n.style, border: '3px solid gold', borderRadius: '8px' } }
            : { ...n, style: { ...n.style, border: '3px solid transparent' } }
        )
      );

      setCenter(node.position.x, node.position.y, { zoom: 1.2, duration: 800 });
    } else {
      setSearchError("No matching node found.");
    }
  };


  const handleLineageChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setShowLineage(false);
    const index = Number(e.target.value);
    setLoading(true);
    setSelectedEdge(null);
    setSelectedLineageIndex(index);

    setTimeout(() => {
      setLoading(false);
      setShowLineage(true);
    }, 4000);
  };

  const handleDropdownChange = (e) => {
    setLineageType(e.target.value);
  }

  return (
    <div style={{ width: '100%' }}>
      <ContentCard
        color="rgba(0, 48, 135, 1)"
        heading={
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '79vw' }}>
            <Typography fontWeight="600" color="rgba(0, 48, 135, 1)" fontSize="20px !important">
              Lineage
            </Typography>

            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '12px', // spacing between elements
                margin: '10px',
                flexWrap: 'wrap', // allows wrapping on small screens
              }}
            >
              {/* Toggle */}
              <div
                style={{
                  position: "relative",
                  width: "200px",
                  height: "40px",
                  borderRadius: "20px",
                  backgroundColor: "#ccc",
                  cursor: "pointer",
                  userSelect: "none",
                  display: "flex",
                }}
                // Only attach handleToggle if data exists
                onClick={fieldlevelResponse.length > 0 ? handleToggle : undefined}
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
                    opacity: fieldlevelResponse.length === 0 ? 0.5 : 1,
                    cursor: fieldlevelResponse.length === 0 ? "not-allowed" : "pointer",
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


              {/* Search Box */}
              <div style={{ display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
                <input
                  type="text"
                  value={query}
                  placeholder="Search node by label"
                  style={{
                    maxWidth: '200px',
                    borderRadius: '28px',
                    padding: '5px 12px',
                    fontSize: '14px',
                    height: '40px',
                    border: '1px solid rgb(79, 141, 192)',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleSearch();
                  }}
                />
                {searchError && (
                  <div style={{ color: 'red', fontSize: '13px', marginTop: '4px' }}>
                    {searchError}
                  </div>
                )}
              </div>

              {/* Lineage Dropdown */}
              <select
                onChange={handleLineageChange}
                value={selectedLineageIndex}
                style={{
                  borderRadius: '28px',
                  padding: '6px 10px',
                  fontSize: '16px',
                  height: '40px',
                  border: '1px solid rgba(79, 141, 192, 1)',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  maxWidth: '220px',
                }}
              >
                {lineageKeys.map((key, index) => (
                  <option key={index} value={index}>
                    {key}
                  </option>
                ))}
              </select>

              {/* Color Mode Dropdown */}
              <select
                onChange={(e) => setColorMode(e.target.value as ColorMode)}
                style={{
                  borderRadius: '28px',
                  padding: '6px 12px',
                  fontSize: '16px',
                  height: '40px',
                  border: '1px solid rgba(79, 141, 192, 1)',
                }}
              >
                <option value="dark">Dark</option>
                <option value="light">Light</option>
              </select>
            </div>

          </div>
        }
        sideNavWidth={sideNavWidth}
        noscroll
      >
        {showLineage && (
          <div style={{ display: 'flex', height: 'calc(100vh - 215px)' }}>
            <div style={{ width: !isOpen ? '100%' : 'calc(100% - 340px)', height: '100%' }}>
              <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onNodeClick={onNodeClick}
                onEdgeClick={onEdgeClick}
                colorMode={colorMode}
                fitView
              >
                <MiniMap />
                <Background />
                <Controls style={{ bottom: '30px' }} />
                <div style={{ position: 'absolute', top: 5, left: 5, zIndex: 1000 }}>
                  <NodeColorLegend />
                </div>
              </ReactFlow>
            </div>

            <div style={{ position: 'relative', height: '100%' }}>
              <Tooltip title={isOpen ? 'Hide Node/Edge Details Panel' : 'Show Node/Edge Details Panel'}>
                <IconButton
                  onClick={togglePanel}
                  style={{
                    position: 'absolute',
                    top: 10,
                    left: isOpen ? -25 : -25,
                    zIndex: 1,
                    background: '#f9f9f9',
                    borderRadius: '50%',
                    boxShadow: '0 0 6px rgba(0,0,0,0.2)',
                  }}
                >
                  {isOpen ? <ChevronRight /> : <ChevronLeft />}
                </IconButton>
              </Tooltip>

              {isOpen && (
                <div style={{
                  width: '340px',
                  background: '#f9f9f9',
                  padding: '20px',
                  borderRadius: '10px',
                  boxShadow: '0 0 12px rgba(0,0,0,0.15)',
                  overflowY: 'auto',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '16px',
                  height: 'calc(100vh - 216px)',
                }}>
                  {(selectedNode || selectedEdge) && (
                    <>
                      <Typography variant="h6" gutterBottom sx={{
                        color: 'rgba(0, 48, 135, 1)',
                        fontSize: '20px',
                        fontWeight: 500
                      }}>
                        {selectedNode ? 'Node Description :' : 'Edge Fields :'}
                      </Typography>


                      {(() => {
                        const raw = selectedNode?.data?.description;
                        const list =
                          typeof raw === 'string'
                            ? [raw]
                            : Array.isArray(raw)
                              ? raw.filter(d => typeof d === 'string')
                              : [];
                        return list.map((item, idx) => (
                          <div key={idx} style={{
                            marginBottom: '8px',
                            padding: '8px 12px',
                            backgroundColor: 'rgba(79, 141, 192, 1)',
                            color: 'white',
                            borderRadius: '16px',
                            fontSize: '14px',
                            fontWeight: 600,
                            maxWidth: '100%',
                            wordBreak: 'break-word',
                          }}>
                            {item}
                          </div>
                        ));
                      })()}


                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px' }}>
                        {selectedEdge && (() => {
                          try {
                            const raw = selectedEdge.data?.fields;
                            const cleaned = typeof raw === 'string' ? raw.replace(/'/g, '"') : '';
                            const parsed = cleaned===''? [] : JSON.parse(cleaned);
                            const flattened = Array.isArray(parsed) ? parsed.flat() : [];

                            return flattened.map((field: string, idx: number) => (
                              <div
                                key={idx}
                                style={{
                                  padding: '8px 12px',
                                  backgroundColor: 'rgba(79, 141, 192, 1)',
                                  color: 'white',
                                  borderRadius: '16px',
                                  fontSize: '14px',
                                  whiteSpace: 'nowrap',
                                }}
                              >
                                {field}
                              </div>
                            ));
                          } catch (err) {
                            return <div style={{ color: 'red' }}>Invalid field data: {String(err)}</div>;
                          }
                        })()}
                      </div>

                    </>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </ContentCard>
      <Loader show={loading} />
    </div>
  );
};

const NodeLineage = () => {
  const [lineageType, setLineageType] = useState("json");
  return (
    <ReactFlowProvider>
      {lineageType === "json" ? <NodeLineageContent lineageType={lineageType} setLineageType={setLineageType} /> : <TableColumnLineage />}
    </ReactFlowProvider>
  );
};

export default NodeLineage;