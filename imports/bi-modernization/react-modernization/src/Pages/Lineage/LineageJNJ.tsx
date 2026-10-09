import React, { useCallback, useMemo, useState } from 'react';
import '@xyflow/react/dist/style.css';
import {
  applyEdgeChanges,
  applyNodeChanges,
  Background,
  Controls,
  MiniMap,
  Panel,
  ReactFlow,
  type Node,
  type Edge,
  type ColorMode,
  useReactFlow,
} from '@xyflow/react';
import ErrorIcon from '@mui/icons-material/Error';
import ContentCard from '../../core/CardContent/CardContent.tsx';
import { Typography } from '@mui/material';
import Toaster from "../../core/Toaster/Toaster.tsx";
import { useOutletContext } from 'react-router-dom';
import dagre from 'dagre';
import './Lineage.scss';
import { useSelector } from 'react-redux';
import { Tooltip, IconButton } from '@mui/material';
import { RootState } from '../../utils/Store';
import { ChevronLeft, ChevronRight } from '@mui/icons-material';
import Loader from '../../core/Loader/Loader.tsx';
import { Snackbar } from '@mui/material';

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
  direction: 'TB' | 'LR' = 'LR'
) => {
  if (!nodes || nodes.length === 0) {
    return { layoutedNodes: [], layoutedEdges: [], startNodes: [] };
  }

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

  const layoutedNodes: Node[] = nodes.map((node) => {
    const { x, y } = dagreGraph.node(node.id);
    const isStart = startNodes.some((n) => n.id === node.id);
    const isEnd = endNodes.some((n) => n.id === node.id);
  
    return {
      id: node.id,
      data: {
        label: (
          <>
            Node ID : {node.toolId}
            <br />
            {node.name}
          </>
        ),
        description: node.description || [],
        toolId: node.toolId,
      },
      position: { x, y },
      sourcePosition: 'right',
      targetPosition: 'left',
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

  const layoutedEdges: Edge[] = edges.map((edge, index) => ({
    id: `e-${edge.start}-${edge.end}-${index}`,
    source: edge.start,
    target: edge.end,
    animated: true,
    style: { stroke: '#888' },
    markerEnd: { type: 'arrowclosed', color: '#888' },
    data: {
      fields: edge.fields?.[0] || '',
    },
  }));

  return { layoutedNodes, layoutedEdges, startNodes };
};

const NodeColorLegend = React.memo(() => (
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
    position: 'relative',
    zIndex: 10,
  }}>
    {[
      { label: 'Start Node', color: 'rgba(0, 48, 135, 1)' },
      { label: 'End Node', color: 'rgba(197, 22, 45, 1)' },
      { label: 'Intermediate Node', color: 'rgba(79, 141, 192, 1)' },
    ].map((item, index) => (
      <div key={index} style={{ display: 'flex', alignItems: 'center' }}>
        <div style={{
          width: '8px',
          height: '8px',
          background: item.color,
          borderRadius: '2px',
          marginRight: '8px',
        }} />
        {item.label}
      </div>
    ))}
  </div>
));

const LineageJNJ = () => {
  const { sideNavWidth } = useOutletContext();
  const reduxData = useSelector((state: RootState) => state.apiData.data);
  const localStorageData = localStorage.getItem('analyzeResponse');
  const parsedLocalData = localStorageData ? JSON.parse(localStorageData) : null;
  const dataToUse = parsedLocalData || reduxData;
  const fileDetails = JSON.parse(localStorage.getItem('fileDetails') as any);
  const etlTool = fileDetails?.etlTool?.toLowerCase?.();
  
  const [query, setQuery] = useState('');
  const [selectedLineageIndex, setSelectedLineageIndex] = useState(0);
  const [colorMode, setColorMode] = useState<ColorMode>('light');
  const [isOpen, setIsOpen] = useState(true);
  const [showSnackbar, setShowSnackbar] = useState(false);
  const [toast, setToast] = useState({
    open: false,
    title: '',
    message: '',
    severity: 'success',
    icon: null,
  });

  const reactFlowInstance = useReactFlow();

  const mermaidResponse = useMemo(() => {
    const result: { nodes?: any[], edges?: any[], label: string }[] = [];

    if (Array.isArray(dataToUse?.jsonlineage)) {
      result.push({
        ...dataToUse.jsonlineage[0], 
        label: 'Master Lineage'
      });
    }

    if (Array.isArray(dataToUse?.macros)) {
      dataToUse.macros.forEach((macro) => {
        const macroLineage = macro?.macroDefinition?.jsonlineage;
        if (Array.isArray(macroLineage) && macroLineage.length > 0) {
          macroLineage.forEach((lineageObj) => {
            result.push({
              ...lineageObj,
              label: macro?.macroPath || 'Macro Lineage'
            });
          });
        }
      });
    }

    return result;
  }, [dataToUse]);

  const { layoutedNodes, layoutedEdges } = useMemo(() => {
    const lineage = mermaidResponse?.[selectedLineageIndex];
    if (!lineage || !lineage.nodes || !lineage.edges) {
      return { layoutedNodes: [], layoutedEdges: [], startNodes: [] };
    }
    return getLayoutedElements(lineage.nodes, lineage.edges);
  }, [mermaidResponse, selectedLineageIndex]);

  const [nodes, setNodes] = useState<Node[]>(layoutedNodes);
  const [edges, setEdges] = useState<Edge[]>(layoutedEdges);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<Edge | null>(null);

  const onNodesChange = useCallback((changes) => {
    setNodes((nds) => applyNodeChanges(changes, nds));
  }, []);

  const onEdgesChange = useCallback((changes) => {
    setEdges((eds) => applyEdgeChanges(changes, eds));
  }, []);

  const onNodeClick = useCallback((_, node: Node) => {
    setSelectedNode(node);
    setSelectedEdge(null);
    setNodes((nds) =>
      nds.map((n) => ({
        ...n,
        style: {
          ...n.style,
          border: n.id === node.id ? '3px solid gold' : '3px solid transparent',
        },
      }))
    );
  }, []);

  const onEdgeClick = useCallback((_, edge: Edge) => {
    setSelectedEdge(edge);
    setSelectedNode(null);
  }, []);

  const togglePanel = useCallback(() => setIsOpen((prev) => !prev), []);

  const handleToasterClose = useCallback(() => {
    setToast((prev) => ({ ...prev, open: false }));
  }, []);

  const handleSearch = useCallback(() => {
    const searchText = query.trim();
    if (!searchText || !reactFlowInstance) return;
  
    const node = nodes.find((n: any) => n.data?.toolId === searchText);
  
    if (node) {
      setSelectedNode(node);
      setSelectedEdge(null);
      setNodes((nds) =>
        nds.map((n) => ({
          ...n,
          style: {
            ...n.style,
            border: n.id === node.id ? '3px solid gold' : '3px solid transparent',
          },
        }))
      );
      reactFlowInstance.setCenter(node.position.x, node.position.y, { zoom: 1.2, duration: 800 });
    } else {
      setToast({
        open: true,
        title: 'Incorrect Node Id',
        message: 'Node Id not available.',
        severity: 'error',
        icon: <ErrorIcon fontSize="inherit" />,
      });
    }
  }, [query, nodes, reactFlowInstance]);

  return (
    <div style={{ height: '100vh', width: '100%', position: 'relative', zIndex: 1 }}>
      <ContentCard
        color="rgba(0, 48, 135, 1)"
        heading={
          <div style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', width: '79vw', justifyContent: 'space-between' }}>
            <Typography fontWeight='600' color="rgba(51, 51, 51, 1)" fontSize="20px !important">Lineage</Typography>
            <div style={{ position: 'relative', zIndex: 1100 }}>
              <select
                onChange={(e) => {
                  setSelectedLineageIndex(Number(e.target.value));
                  const lineage = mermaidResponse?.[Number(e.target.value)];
                  if (lineage?.nodes && lineage?.edges) {
                    const { layoutedNodes: newNodes, layoutedEdges: newEdges } = getLayoutedElements(lineage.nodes, lineage.edges);
                    setNodes(newNodes);
                    setEdges(newEdges);
                  }
                }}
                value={selectedLineageIndex}
                style={{
                  borderRadius: '28px',
                  padding: '6px 10px',
                  fontSize: '16px',
                  width: '200px',
                  height: '40px',
                  border: '1px solid rgba(79, 141, 192, 1)',
                  margin: '10px',
                  cursor: 'pointer',
                }}
              >
                {mermaidResponse.map((lineage, index) => (
                  <option key={index} value={index}>
                    {index === 0 ? 'Lineage 1 (Master)' : lineage.label}
                  </option>
                ))}
              </select>
              <select
                onChange={(e) => setColorMode(e.target.value as ColorMode)}
                value={colorMode}
                style={{
                  borderRadius: '28px',
                  padding: '10px',
                  fontSize: '16px',
                  width: '200px',
                  height: '40px',
                  border: '1px solid rgba(79, 141, 192, 1)',
                  cursor: 'pointer',
                }}
              >
                <option value="dark">Dark</option>
                <option value="light">Light</option>
              </select>
              <div style={{ display: 'inline-block', marginLeft: '10px' }}>
                <input
                  type="text"
                  value={query}
                  placeholder="Search node by tool ID"
                  style={{
                    maxWidth: '200px',
                    borderRadius: '28px',
                    padding: '5px',
                    fontSize: '14px',
                    height: '40px',
                    border: '1px solid rgb(79, 141, 192)',
                    margin: '0 6px',
                  }}
                  onChange={(e) => {
                    setQuery(e.target.value);
                    if (e.target.value && !showSnackbar) {
                      setShowSnackbar(true);
                    }
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleSearch();
                  }}
                />
              </div>
            </div>
          </div>
        }
        sideNavWidth={sideNavWidth}
        noscroll
      >
        <div style={{ display: 'flex', height: 'calc(100vh - 160px)', position: 'relative', zIndex: 1 }}>
          <div style={{ width: !isOpen ? '100%' : 'calc(100% - 340px)', height: '100%', position: 'relative', zIndex: 1 }}>
            {nodes.length > 0 ? (
              <div style={{ width: '100%', height: '100%', position: 'relative', zIndex: 1 }}>
                <ReactFlow
                  nodes={nodes}
                  edges={edges}
                  onNodesChange={onNodesChange}
                  onEdgesChange={onEdgesChange}
                  onNodeClick={onNodeClick}
                  onEdgeClick={onEdgeClick}
                  colorMode={colorMode}
                  fitView
                  minZoom={0.1}
                  maxZoom={2}
                  style={{ position: 'relative', zIndex: 1 }}
                >
                  <MiniMap 
                    style={{ position: 'absolute', bottom: 20, right: 20, zIndex: 10 }}
                    nodeColor={(node) => {
                      const style = node.style as any;
                      return style?.background || '#4F8DC0';
                    }} 
                  />
                  <Background style={{ zIndex: 0 }} />
                  <Controls style={{ position: 'absolute', bottom: 30, left: 10, zIndex: 10 }} />
                  <Panel position="top-left" style={{ zIndex: 10 }}>
                    <NodeColorLegend />
                  </Panel>
                </ReactFlow>
              </div>
            ) : (
              <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
                <Typography>Loading lineage data...</Typography>
              </div>
            )}
          </div>
          <div style={{ position: 'relative', height: '100%', zIndex: 100 }}>
            <Tooltip title={isOpen ? 'Hide Panel' : 'Show Panel'}>
              <IconButton
                onClick={togglePanel}
                style={{
                  position: 'absolute',
                  top: 10,
                  left: -25,
                  background: '#f9f9f9',
                  borderRadius: '50%',
                  boxShadow: '0 0 6px rgba(0,0,0,0.2)',
                  zIndex: 101,
                }}
              >
                {isOpen ? <ChevronLeft /> : <ChevronRight />}
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
                position: 'relative',
                zIndex: 100,
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

                    {selectedNode?.data?.description?.map((item: string, idx: number) => (
                      <div key={idx} style={{
                        marginBottom: '8px',
                        padding: '8px 12px',
                        backgroundColor: 'rgba(79, 141, 192, 1)',
                        color: 'white',
                        borderRadius: '16px',
                        fontSize: '14px',
                        fontWeight: 600,
                        wordBreak: 'break-word',
                      }}>
                        {item}
                      </div>
                    ))}

                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px' }}>
                      {selectedEdge && (() => {
                        try {
                          const raw = selectedEdge.data?.fields;
                          let parsed = null
                          if (etlTool === 'sas' || etlTool === 'talend'){
                            console.log("sas stuff so no need for parsing")
                            console.log(raw)
                            console.log(selectedEdge)
                            parsed = raw
                          }else{
                            let cleaned = typeof raw === 'string' ? raw.replace(/'/g, '"') : '';
                            parsed = JSON.parse(cleaned);
                          }
                          
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
                          {console.log(err)}
                          return <div style={{ color: 'red' }}>Invalid field data</div>;
                        }
                      })()}
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      </ContentCard>
      <Snackbar
        open={showSnackbar}
        autoHideDuration={3000}
        onClose={() => setShowSnackbar(false)}
        message="Press Enter to search"
        anchorOrigin={{ vertical: 'top', horizontal: 'right' }}
        style={{ zIndex: 9999 }}
      />
      <Loader show={false} />
      <Toaster
        open={toast.open}
        onClose={handleToasterClose}
        title={toast.title}
        message={toast.message}
        icon={toast.icon}
        severity={toast.severity}
        duration={4000}
      />
    </div>
  );
};

export default LineageJNJ;