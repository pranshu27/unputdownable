import React, { memo } from 'react';
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  EdgeProps,
} from '@xyflow/react';

interface CustomEdgeData {
  label: string;
  cardinality: string;
  leftColumn: string;
  rightColumn: string;
  joinType: string;
  filterDirection: string;
  sourceTableName: string;
  targetTableName: string;
  relationship: any;
}

const CustomEdge: React.FC<EdgeProps> = memo(({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  style = {},
  markerEnd,
  selected,
}) => {
  const edgeData = data as unknown as CustomEdgeData;

  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
    curvature: 0.4,
  });

  const isDimmed = data?.isDimmed === true;

  return (
    <>
      {/* Glow effect layer */}
      {!isDimmed && (
        <BaseEdge
          path={edgePath}
          style={{
            stroke: selected ? 'rgba(200,16,46,0.18)' : 'rgba(0,48,135,0.12)',
            strokeWidth: selected ? 10 : 7,
            filter: 'blur(4px)',
            ...style,
          }}
        />
      )}

      {/* Main edge line */}
      <BaseEdge
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke: selected ? '#c8102e' : (isDimmed ? 'rgba(148, 163, 184, 0.08)' : 'rgba(0,48,135,0.42)'),
          strokeWidth: selected ? 3 : 1.5,
          transition: 'stroke 0.3s ease, stroke-width 0.3s ease',
          ...style,
        }}
      />

      {/* Animated particle dots along the edge */}
      {!isDimmed && (
        <>
          <circle r="3" fill={selected ? '#c8102e' : '#003087'} opacity="0.75">
            <animateMotion dur="4s" repeatCount="indefinite" path={edgePath} />
          </circle>
          <circle r="2" fill={selected ? '#f4a6b4' : '#9db7dc'} opacity="0.45">
            <animateMotion dur="4s" repeatCount="indefinite" path={edgePath} begin="2s" />
          </circle>
        </>
      )}

      {/* Edge label */}
      <EdgeLabelRenderer>
        <div
          className={`ontology-edge-label ${selected ? 'ontology-edge-label--selected' : ''}`}
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            pointerEvents: isDimmed ? 'none' : 'all',
            opacity: isDimmed ? 0.2 : 1,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '3px',
            background: 'rgba(255, 255, 255, 0.98)',
            border: selected ? '1.5px solid #c8102e' : '1px solid #cbd5e1',
            borderRadius: '6px',
            padding: '4px 10px',
            boxShadow: '0 2px 6px rgba(0,0,0,0.05)',
            zIndex: selected ? 1000 : 500,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span className="ontology-edge-label__text" style={{ textTransform: 'capitalize', fontStyle: 'normal', fontWeight: 600, fontSize: '10.5px' }}>
              {(edgeData?.label || '').replace(/_/g, ' ')}
            </span>
            <span className="ontology-edge-label__cardinality" style={{ color: '#c8102e', fontWeight: 700, fontSize: '10px' }}>
              {edgeData?.cardinality || ''}
            </span>
          </div>
          
          {edgeData?.leftColumn && edgeData?.rightColumn && (
            <div style={{
              fontSize: '9px',
              color: '#64748b',
              fontWeight: 600,
              fontFamily: 'monospace',
              borderTop: '1px solid #f1f5f9',
              paddingTop: '2px',
              marginTop: '1px',
              whiteSpace: 'nowrap',
            }}>
              {edgeData.leftColumn} → {edgeData.rightColumn}
            </div>
          )}
        </div>
      </EdgeLabelRenderer>
    </>
  );
});

CustomEdge.displayName = 'CustomEdge';
export default CustomEdge;
