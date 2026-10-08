/**
 * EnterpriseSearch.tsx
 * Global command palette (Cmd+K / Ctrl+K) with fuzzy search across all entities.
 */
import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { Search, X, ArrowRight, Table2, Database, Hash, Columns3, FileText, GitBranch, CornerDownLeft } from 'lucide-react';

export interface SearchItem {
  id: string;
  label: string;
  category: string;
  description?: string;
  icon?: React.ReactNode;
  path?: string;
  meta?: Record<string, any>;
}

interface Props {
  items: SearchItem[];
  onSelect: (item: SearchItem) => void;
  isOpen: boolean;
  onClose: () => void;
}

const categoryIcons: Record<string, React.ReactNode> = {
  Tables: <Table2 size={13} />,
  Columns: <Columns3 size={13} />,
  'Data Sources': <Database size={13} />,
  KPIs: <Hash size={13} />,
  Measures: <Hash size={13} />,
  Reports: <FileText size={13} />,
  Relationships: <GitBranch size={13} />,
};

function fuzzyMatch(text: string, query: string): { match: boolean; score: number } {
  const t = text.toLowerCase();
  const q = query.toLowerCase();
  if (t.includes(q)) return { match: true, score: q.length / t.length };
  let qi = 0;
  for (let i = 0; i < t.length && qi < q.length; i++) {
    if (t[i] === q[qi]) qi++;
  }
  return { match: qi === q.length, score: qi === q.length ? q.length / (t.length * 2) : 0 };
}

function highlightMatch(text: string, query: string): React.ReactNode {
  if (!query) return text;
  const idx = text.toLowerCase().indexOf(query.toLowerCase());
  if (idx === -1) return text;
  return (
    <>
      {text.slice(0, idx)}
      <mark style={{ background: 'var(--jnj-red-muted)', color: 'var(--jnj-red)', borderRadius: 2, padding: '0 1px' }}>
        {text.slice(idx, idx + query.length)}
      </mark>
      {text.slice(idx + query.length)}
    </>
  );
}

const RECENT_KEY = 'jnj:recent-searches';
const MAX_RECENT = 5;

export default function EnterpriseSearch({ items, onSelect, isOpen, onClose }: Props) {
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const recentIds = useMemo(() => {
    try { return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]'); } catch { return []; }
  }, [isOpen]);

  const results = useMemo(() => {
    if (!query.trim()) {
      const recents = recentIds
        .map((id: string) => items.find(i => i.id === id))
        .filter(Boolean) as SearchItem[];
      return recents.length > 0 ? [{ category: 'Recent', items: recents }] : [];
    }
    const scored = items
      .map(item => {
        const r = fuzzyMatch(item.label, query);
        const descR = item.description ? fuzzyMatch(item.description, query) : { match: false, score: 0 };
        return { item, score: Math.max(r.score, descR.score), match: r.match || descR.match };
      })
      .filter(s => s.match)
      .sort((a, b) => b.score - a.score)
      .slice(0, 30);

    const grouped = new Map<string, SearchItem[]>();
    scored.forEach(({ item }) => {
      const group = grouped.get(item.category) || [];
      group.push(item);
      grouped.set(item.category, group);
    });

    return Array.from(grouped.entries()).map(([category, items]) => ({ category, items }));
  }, [query, items, recentIds]);

  const flatResults = useMemo(() => results.flatMap(g => g.items), [results]);

  useEffect(() => { setSelectedIndex(0); }, [query]);

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 50);
      setQuery('');
    }
  }, [isOpen]);

  const handleSelect = useCallback((item: SearchItem) => {
    try {
      const recent = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]');
      const updated = [item.id, ...recent.filter((id: string) => id !== item.id)].slice(0, MAX_RECENT);
      localStorage.setItem(RECENT_KEY, JSON.stringify(updated));
    } catch {}
    onSelect(item);
    onClose();
  }, [onSelect, onClose]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSelectedIndex(i => Math.min(i + 1, flatResults.length - 1)); }
    if (e.key === 'ArrowUp') { e.preventDefault(); setSelectedIndex(i => Math.max(i - 1, 0)); }
    if (e.key === 'Enter' && flatResults[selectedIndex]) { handleSelect(flatResults[selectedIndex]); }
    if (e.key === 'Escape') onClose();
  };

  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-index="${selectedIndex}"]`);
    el?.scrollIntoView({ block: 'nearest' });
  }, [selectedIndex]);

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div onClick={onClose} style={{
        position: 'fixed', inset: 0, background: 'var(--surface-overlay)',
        zIndex: 'var(--z-modal)' as any, animation: 'fadeIn 150ms ease',
      }} />

      {/* Modal */}
      <div style={{
        position: 'fixed', top: '15%', left: '50%', transform: 'translateX(-50%)',
        width: '100%', maxWidth: 560, zIndex: 'calc(var(--z-modal) + 1)' as any,
        background: 'var(--surface-card)', border: '1px solid var(--border-secondary)',
        borderRadius: 'var(--radius-xl)', boxShadow: 'var(--shadow-xl)',
        overflow: 'hidden', display: 'flex', flexDirection: 'column',
        maxHeight: '60vh',
      }}>
        {/* Search input */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 'var(--space-3)',
          padding: '12px 16px', borderBottom: '1px solid var(--border-subtle)',
        }}>
          <Search size={16} style={{ color: 'var(--text-tertiary)', flexShrink: 0 }} />
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search tables, columns, KPIs, data sources…"
            style={{
              flex: 1, border: 'none', outline: 'none', background: 'transparent',
              fontSize: 'var(--text-md)', color: 'var(--text-primary)',
              fontFamily: 'var(--font-sans)',
            }}
          />
          <kbd style={{
            fontSize: 10, padding: '2px 6px', borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border-primary)', color: 'var(--text-tertiary)',
            fontFamily: 'var(--font-sans)', fontWeight: 500,
          }}>
            ESC
          </kbd>
        </div>

        {/* Results */}
        <div ref={listRef} style={{ flex: 1, overflow: 'auto', padding: 'var(--space-1) 0' }}>
          {results.length === 0 ? (
            <div style={{
              padding: 'var(--space-8)', textAlign: 'center',
              color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)',
            }}>
              {query ? `No results for "${query}"` : 'Start typing to search across all entities'}
            </div>
          ) : (
            results.map((group, gi) => {
              let itemIndex = 0;
              for (let g = 0; g < gi; g++) itemIndex += results[g].items.length;
              return (
                <div key={group.category}>
                  <div style={{
                    padding: '6px 16px', fontSize: 'var(--text-xs)', fontWeight: 600,
                    color: 'var(--text-tertiary)', textTransform: 'uppercase',
                    letterSpacing: 'var(--tracking-wide)',
                  }}>
                    {group.category}
                  </div>
                  {group.items.map((item, ii) => {
                    const idx = itemIndex + ii;
                    const isSel = idx === selectedIndex;
                    return (
                      <button
                        key={item.id}
                        data-index={idx}
                        onClick={() => handleSelect(item)}
                        onMouseEnter={() => setSelectedIndex(idx)}
                        style={{
                          display: 'flex', alignItems: 'center', gap: 'var(--space-3)',
                          width: '100%', padding: '8px 16px', border: 'none',
                          background: isSel ? 'var(--surface-secondary)' : 'transparent',
                          cursor: 'pointer', textAlign: 'left',
                          transition: 'background var(--transition-fast)',
                        }}
                      >
                        <span style={{
                          width: 28, height: 28, borderRadius: 'var(--radius-md)',
                          background: isSel ? 'var(--ent-blue-light)' : 'var(--surface-secondary)',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          color: isSel ? 'var(--ent-blue)' : 'var(--text-tertiary)', flexShrink: 0,
                        }}>
                          {item.icon || categoryIcons[item.category] || <FileText size={13} />}
                        </span>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{
                            fontSize: 'var(--text-sm)', fontWeight: 500,
                            color: 'var(--text-primary)', overflow: 'hidden',
                            textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                          }}>
                            {highlightMatch(item.label, query)}
                          </div>
                          {item.description && (
                            <div style={{
                              fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)',
                              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                            }}>
                              {item.description}
                            </div>
                          )}
                        </div>
                        {isSel && <CornerDownLeft size={12} style={{ color: 'var(--text-tertiary)', flexShrink: 0 }} />}
                      </button>
                    );
                  })}
                </div>
              );
            })
          )}
        </div>

        {/* Footer hints */}
        <div style={{
          padding: '6px 16px', borderTop: '1px solid var(--border-subtle)',
          display: 'flex', gap: 'var(--space-4)', fontSize: 'var(--text-xs)',
          color: 'var(--text-tertiary)',
        }}>
          <span>↑↓ Navigate</span>
          <span>↵ Select</span>
          <span>Esc Close</span>
        </div>
      </div>

      <style>{`@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }`}</style>
    </>
  );
}
