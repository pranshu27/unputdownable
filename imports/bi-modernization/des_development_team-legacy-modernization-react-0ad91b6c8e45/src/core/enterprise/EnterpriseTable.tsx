/**
 * EnterpriseTable.tsx
 * Sortable, filterable enterprise table with sticky headers,
 * expandable rows, and search. Data-focused layout.
 */
import React, { useState, useMemo, useCallback } from 'react';
import { ChevronDown, ChevronUp, ChevronRight, Search, ArrowUpDown } from 'lucide-react';

export interface Column<T = any> {
  key: string;
  label: string;
  width?: number | string;
  sortable?: boolean;
  render?: (value: any, row: T, index: number) => React.ReactNode;
  align?: 'left' | 'center' | 'right';
  hidden?: boolean;
}

interface EnterpriseTableProps<T = any> {
  columns: Column<T>[];
  data: T[];
  rowKey?: string | ((row: T, index: number) => string);
  searchable?: boolean;
  searchPlaceholder?: string;
  searchKeys?: string[];
  onRowClick?: (row: T, index: number) => void;
  selectedRowKey?: string;
  expandable?: boolean;
  renderExpanded?: (row: T) => React.ReactNode;
  emptyMessage?: string;
  emptyIcon?: React.ReactNode;
  maxHeight?: number | string;
  compact?: boolean;
  headerActions?: React.ReactNode;
  stickyHeader?: boolean;
  className?: string;
}

type SortDir = 'asc' | 'desc' | null;

export default function EnterpriseTable<T extends Record<string, any>>({
  columns, data, rowKey = 'id', searchable, searchPlaceholder = 'Search…',
  searchKeys, onRowClick, selectedRowKey, expandable, renderExpanded,
  emptyMessage = 'No data available', emptyIcon, maxHeight = 480,
  compact, headerActions, stickyHeader = true, className = '',
}: EnterpriseTableProps<T>) {
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>(null);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

  const getKey = useCallback((row: T, i: number) => {
    if (typeof rowKey === 'function') return rowKey(row, i);
    return String(row[rowKey] ?? i);
  }, [rowKey]);

  const visibleCols = columns.filter(c => !c.hidden);

  const filtered = useMemo(() => {
    if (!search.trim()) return data;
    const q = search.toLowerCase();
    const keys = searchKeys || visibleCols.map(c => c.key);
    return data.filter(row => keys.some(k => String(row[k] ?? '').toLowerCase().includes(q)));
  }, [data, search, searchKeys, visibleCols]);

  const sorted = useMemo(() => {
    if (!sortKey || !sortDir) return filtered;
    return [...filtered].sort((a, b) => {
      const va = a[sortKey] ?? '';
      const vb = b[sortKey] ?? '';
      const cmp = typeof va === 'number' ? va - (vb as number) : String(va).localeCompare(String(vb));
      return sortDir === 'desc' ? -cmp : cmp;
    });
  }, [filtered, sortKey, sortDir]);

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDir(d => d === 'asc' ? 'desc' : d === 'desc' ? null : 'asc');
      if (sortDir === 'desc') setSortKey(null);
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  };

  const toggleExpand = (key: string) => {
    setExpandedRows(prev => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  };

  const pad = compact ? '6px 10px' : '8px 12px';

  return (
    <div className={className}>
      {/* Toolbar */}
      {(searchable || headerActions) && (
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          gap: 'var(--space-3)', padding: 'var(--space-3)',
          borderBottom: '1px solid var(--border-subtle)',
        }}>
          {searchable && (
            <div style={{ position: 'relative', maxWidth: 280, flex: 1 }}>
              <Search size={13} style={{
                position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)',
                color: 'var(--text-tertiary)',
              }} />
              <input
                className="ent-input"
                placeholder={searchPlaceholder}
                value={search}
                onChange={e => setSearch(e.target.value)}
                style={{ paddingLeft: 30, height: 28, fontSize: 'var(--text-xs)' }}
              />
            </div>
          )}
          {headerActions && <div style={{ display: 'flex', gap: 'var(--space-2)' }}>{headerActions}</div>}
        </div>
      )}

      {/* Table */}
      <div style={{ maxHeight, overflow: 'auto' }}>
        <table className="ent-table" style={{ fontSize: compact ? 'var(--text-xs)' : 'var(--text-sm)' }}>
          <thead>
            <tr>
              {expandable && <th style={{ width: 28, padding: pad }} />}
              {visibleCols.map(col => (
                <th
                  key={col.key}
                  style={{
                    width: col.width, padding: pad,
                    textAlign: col.align || 'left',
                    cursor: col.sortable ? 'pointer' : 'default',
                    position: stickyHeader ? 'sticky' : undefined,
                    top: stickyHeader ? 0 : undefined,
                  }}
                  onClick={col.sortable ? () => handleSort(col.key) : undefined}
                >
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                    {col.label}
                    {col.sortable && (
                      sortKey === col.key ? (
                        sortDir === 'asc' ? <ChevronUp size={11} /> : <ChevronDown size={11} />
                      ) : <ArrowUpDown size={10} style={{ opacity: 0.3 }} />
                    )}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 ? (
              <tr>
                <td colSpan={visibleCols.length + (expandable ? 1 : 0)} style={{
                  textAlign: 'center', padding: 'var(--space-10)',
                  color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)',
                }}>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--space-2)' }}>
                    {emptyIcon}
                    <span>{emptyMessage}</span>
                  </div>
                </td>
              </tr>
            ) : sorted.map((row, i) => {
              const key = getKey(row, i);
              const isExpanded = expandedRows.has(key);
              const isSelected = selectedRowKey === key;
              return (
                <React.Fragment key={key}>
                  <tr
                    className={isSelected ? 'ent-table-selected' : ''}
                    style={{ cursor: onRowClick ? 'pointer' : 'default' }}
                    onClick={() => onRowClick?.(row, i)}
                  >
                    {expandable && (
                      <td style={{ padding: pad, width: 28 }}>
                        <button
                          onClick={e => { e.stopPropagation(); toggleExpand(key); }}
                          style={{
                            background: 'none', border: 'none', cursor: 'pointer',
                            color: 'var(--text-tertiary)', padding: 2, display: 'flex',
                          }}
                        >
                          <ChevronRight size={12} style={{
                            transform: isExpanded ? 'rotate(90deg)' : 'none',
                            transition: 'transform var(--transition-fast)',
                          }} />
                        </button>
                      </td>
                    )}
                    {visibleCols.map(col => (
                      <td key={col.key} style={{ padding: pad, textAlign: col.align || 'left' }}>
                        {col.render ? col.render(row[col.key], row, i) : String(row[col.key] ?? '—')}
                      </td>
                    ))}
                  </tr>
                  {expandable && isExpanded && renderExpanded && (
                    <tr>
                      <td colSpan={visibleCols.length + 1} style={{
                        padding: 0, background: 'var(--surface-secondary)',
                        borderBottom: '1px solid var(--border-primary)',
                      }}>
                        <div style={{ padding: 'var(--space-3) var(--space-4)' }}>
                          {renderExpanded(row)}
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

      {/* Footer */}
      {sorted.length > 0 && (
        <div style={{
          padding: '6px 12px', borderTop: '1px solid var(--border-subtle)',
          fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)',
          display: 'flex', justifyContent: 'space-between',
        }}>
          <span>{sorted.length} {sorted.length === 1 ? 'row' : 'rows'}{search ? ` (filtered from ${data.length})` : ''}</span>
        </div>
      )}
    </div>
  );
}
