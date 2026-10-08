import React, { memo, useState } from 'react';
import { Handle, Position, NodeProps } from '@xyflow/react';

interface CustomNodeData {
  tableName: string;
  tableType: string;
  columnCount: number;
  relationshipCount: number;
  description: string;
  colors: {
    border: string;
    glow: string;
    badge: string;
    bg: string;
  };
  table: any;
  isDimmed?: boolean;
  isSearchMatch?: boolean;
}

const CustomNode: React.FC<NodeProps> = memo(({ data, selected }) => {
  const [isHovered, setIsHovered] = useState(false);
  const nodeData = data as unknown as CustomNodeData;
  const { tableName, tableType, columnCount, relationshipCount, colors } = nodeData;

  const displayName = tableName.length > 28 ? tableName.substring(0, 25) + '...' : tableName;
  const badgeLabel = tableType.charAt(0).toUpperCase() + tableType.slice(1);

  return (
    <div
      className={`ontology-node-wrapper ${nodeData.isDimmed ? 'ontology-node--dimmed' : ''} ${nodeData.isSearchMatch ? 'ontology-node-wrapper--search-match' : ''}`}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{
        '--node-border-color': colors.border,
        '--node-glow-color': colors.glow,
        '--node-bg-color': colors.bg,
        '--node-badge-color': colors.badge,
        opacity: nodeData.isDimmed ? 0.25 : 1,
        pointerEvents: 'auto',
      } as React.CSSProperties}
    >
      {/* Connection handles */}
      <Handle
        type="target"
        position={Position.Top}
        className="ontology-handle"
        style={{ background: colors.border }}
      />
      <Handle
        type="source"
        position={Position.Bottom}
        className="ontology-handle"
        style={{ background: colors.border }}
      />
      <Handle
        type="target"
        position={Position.Left}
        id="left-target"
        className="ontology-handle"
        style={{ background: colors.border }}
      />
      <Handle
        type="source"
        position={Position.Right}
        id="right-source"
        className="ontology-handle"
        style={{ background: colors.border }}
      />

      <div
        className={`ontology-node ${isHovered || selected ? 'ontology-node--active' : ''}`}
      >
        {/* Header with type badge */}
        <div className="ontology-node__header">
          <span
            className="ontology-node__badge"
            style={{ backgroundColor: `${colors.badge}22`, color: colors.badge, borderColor: `${colors.badge}44` }}
          >
            <span className="ontology-node__badge-dot" style={{ backgroundColor: colors.badge }} />
            {badgeLabel}
          </span>
        </div>

        {/* Table name */}
        <div className="ontology-node__name" title={tableName}>
          {displayName}
        </div>

        {/* Stats row */}
        <div className="ontology-node__stats">
          {tableType.toLowerCase() === 'kpi' ? (
            <div className="ontology-node__stat">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={colors.border} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" /><polyline points="17 6 23 6 23 12" />
              </svg>
              <span className="text-slate-800">Semantic KPI</span>
            </div>
          ) : (
            <>
              <div className="ontology-node__stat">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={colors.border} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="14" y="14" width="7" height="7" /><rect x="3" y="14" width="7" height="7" />
                </svg>
                <span className="text-slate-800">{columnCount} cols</span>
              </div>
              <div className="ontology-node__stat-divider" />
              <div className="ontology-node__stat">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={colors.border} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
                  <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
                </svg>
                <span className="text-slate-800">{relationshipCount} rels</span>
              </div>
            </>
          )}
        </div>

        {/* Subtle pulse ring on hover */}
        {(isHovered || selected) && (
          <div className="ontology-node__pulse-ring" style={{ borderColor: colors.border }} />
        )}
      </div>
    </div>
  );
});

CustomNode.displayName = 'CustomNode';
export default CustomNode;
