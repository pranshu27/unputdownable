/**
 * EnterpriseExplorerTree.tsx
 * Database-style collapsible tree: schemas → tables → columns.
 * Used in the left sidebar for dataset/datasource exploration.
 */
import React, { useState, useMemo } from 'react';
import {
  ChevronRight, Database, Table2, Columns3,
  Search, Hash, Type, Calendar, ToggleLeft,
} from 'lucide-react';

export interface TreeNode {
  id: string;
  label: string;
  type: 'schema' | 'table' | 'column' | 'kpi' | 'source' | 'measure' | 'group';
  children?: TreeNode[];
  meta?: Record<string, any>;
  icon?: React.ReactNode;
  badge?: string;
}

interface ExplorerTreeProps {
  nodes: TreeNode[];
  onSelect?: (node: TreeNode) => void;
  selectedId?: string;
  searchable?: boolean;
  title?: string;
  compact?: boolean;
}

const typeIcons: Record<string, React.ReactNode> = {
  schema: <Database size={12} />,
  source: <Database size={12} />,
  table: <Table2 size={12} />,
  column: <Columns3 size={12} />,
  kpi: <Hash size={12} />,
  measure: <Hash size={12} />,
  group: <Table2 size={12} />,
};

const dataTypeIcons: Record<string, React.ReactNode> = {
  string: <Type size={10} />,
  int64: <Hash size={10} />,
  double: <Hash size={10} />,
  decimal: <Hash size={10} />,
  boolean: <ToggleLeft size={10} />,
  dateTime: <Calendar size={10} />,
  date: <Calendar size={10} />,
};

function TreeItem({
  node, depth, onSelect, selectedId, expandedIds, toggleExpand,
}: {
  node: TreeNode; depth: number; onSelect?: (n: TreeNode) => void;
  selectedId?: string; expandedIds: Set<string>; toggleExpand: (id: string) => void;
}) {
  const hasChildren = (node.children?.length ?? 0) > 0;
  const isExpanded = expandedIds.has(node.id);
  const isSelected = selectedId === node.id;

  return (
    <>
      <button
        onClick={() => {
          if (hasChildren) toggleExpand(node.id);
          onSelect?.(node);
        }}
        style={{
          display: 'flex', alignItems: 'center', gap: 4, width: '100%',
          padding: `3px 8px 3px ${8 + depth * 16}px`,
          background: isSelected ? 'var(--ent-blue-light)' : 'transparent',
          border: 'none', cursor: 'pointer', fontSize: 'var(--text-xs)',
          color: isSelected ? 'var(--ent-blue)' : 'var(--text-secondary)',
          fontWeight: isSelected ? 600 : 400,
          borderRadius: 'var(--radius-sm)', margin: '0 4px',
          transition: 'background var(--transition-fast)',
          textAlign: 'left', minHeight: 26,
        }}
        onMouseEnter={e => { if (!isSelected) (e.currentTarget.style.background = 'var(--surface-secondary)'); }}
        onMouseLeave={e => { if (!isSelected) (e.currentTarget.style.background = 'transparent'); }}
      >
        {hasChildren ? (
          <ChevronRight size={10} style={{
            transform: isExpanded ? 'rotate(90deg)' : 'none',
            transition: 'transform var(--transition-fast)',
            flexShrink: 0, color: 'var(--text-tertiary)',
          }} />
        ) : (
          <span style={{ width: 10, flexShrink: 0 }} />
        )}
        <span style={{ flexShrink: 0, color: isSelected ? 'var(--ent-blue)' : 'var(--text-tertiary)' }}>
          {node.icon || typeIcons[node.type] || <Table2 size={12} />}
        </span>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
          {node.label}
        </span>
        {node.badge && (
          <span style={{
            fontSize: 9, padding: '1px 5px', borderRadius: 'var(--radius-sm)',
            background: 'var(--surface-secondary)', color: 'var(--text-tertiary)',
            fontWeight: 600, flexShrink: 0,
          }}>
            {node.badge}
          </span>
        )}
        {node.type === 'column' && node.meta?.data_type && (
          <span style={{ flexShrink: 0, color: 'var(--text-tertiary)', opacity: 0.6 }}>
            {dataTypeIcons[node.meta.data_type] || <Type size={10} />}
          </span>
        )}
      </button>
      {hasChildren && isExpanded && node.children!.map(child => (
        <TreeItem
          key={child.id} node={child} depth={depth + 1}
          onSelect={onSelect} selectedId={selectedId}
          expandedIds={expandedIds} toggleExpand={toggleExpand}
        />
      ))}
    </>
  );
}

export default function EnterpriseExplorerTree({
  nodes, onSelect, selectedId, searchable = true, title, compact,
}: ExplorerTreeProps) {
  const [search, setSearch] = useState('');
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const toggleExpand = (id: string) => {
    setExpandedIds(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const filterNodes = (nodes: TreeNode[], q: string): TreeNode[] => {
    if (!q) return nodes;
    return nodes.reduce<TreeNode[]>((acc, node) => {
      const match = node.label.toLowerCase().includes(q);
      const filteredChildren = node.children ? filterNodes(node.children, q) : [];
      if (match || filteredChildren.length > 0) {
        acc.push({ ...node, children: filteredChildren.length > 0 ? filteredChildren : node.children });
      }
      return acc;
    }, []);
  };

  const filtered = useMemo(() => filterNodes(nodes, search.toLowerCase()), [nodes, search]);

  // Auto-expand parent nodes when searching
  useMemo(() => {
    if (search) {
      const ids = new Set<string>();
      const walk = (ns: TreeNode[]) => {
        ns.forEach(n => {
          if (n.children?.length) { ids.add(n.id); walk(n.children); }
        });
      };
      walk(filtered);
      setExpandedIds(ids);
    }
  }, [search, filtered]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {title && (
        <div style={{
          padding: '8px 12px', fontSize: 'var(--text-xs)', fontWeight: 600,
          color: 'var(--text-tertiary)', textTransform: 'uppercase',
          letterSpacing: 'var(--tracking-wide)', borderBottom: '1px solid var(--border-subtle)',
        }}>
          {title}
        </div>
      )}
      {searchable && (
        <div style={{ padding: '6px 8px', borderBottom: '1px solid var(--border-subtle)' }}>
          <div style={{ position: 'relative' }}>
            <Search size={11} style={{
              position: 'absolute', left: 8, top: '50%', transform: 'translateY(-50%)',
              color: 'var(--text-tertiary)',
            }} />
            <input
              className="ent-input"
              placeholder="Filter…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              style={{ paddingLeft: 26, height: 26, fontSize: 'var(--text-xs)' }}
            />
          </div>
        </div>
      )}
      <div style={{ flex: 1, overflow: 'auto', padding: '4px 0' }}>
        {filtered.length === 0 ? (
          <div style={{
            padding: 'var(--space-6)', textAlign: 'center',
            color: 'var(--text-tertiary)', fontSize: 'var(--text-xs)',
          }}>
            No items found
          </div>
        ) : (
          filtered.map(node => (
            <TreeItem
              key={node.id} node={node} depth={0}
              onSelect={onSelect} selectedId={selectedId}
              expandedIds={expandedIds} toggleExpand={toggleExpand}
            />
          ))
        )}
      </div>
    </div>
  );
}
