import React, { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, X, Table2, Database, TrendingUp, Code2, Columns, ChevronRight } from 'lucide-react';
import sampleModel from '../../data/sampleModel.ts';

const NAVY = '#003087';
const RED  = '#c8102e';

/* ── Load the active model the same way AppRoutes does ── */
function loadModel(): any {
  try {
    const raw = localStorage.getItem('activePowerBiReportData');
    if (!raw) return sampleModel;
    const report = JSON.parse(raw);
    const result = report?.result || report;
    return {
      ...sampleModel,
      ...result,
      data_sources:  Array.isArray(result?.data_sources)  ? result.data_sources  : sampleModel.data_sources,
      tables:        Array.isArray(result?.tables)         ? result.tables        : sampleModel.tables,
      relationships: Array.isArray(result?.relationships)  ? result.relationships : sampleModel.relationships,
      calculations:  Array.isArray(result?.calculations)   ? result.calculations
                   : Array.isArray(result?.measures)       ? result.measures      : sampleModel.calculations,
      kpi_lineage:   Array.isArray(result?.kpi_lineage)    ? result.kpi_lineage   : sampleModel.kpi_lineage,
    };
  } catch {
    return sampleModel;
  }
}

/* ── Search result shape ── */
interface Result {
  id:         string;
  kind:       'table' | 'column' | 'measure' | 'kpi' | 'source';
  name:       string;
  breadcrumb: string[];   // e.g. ['Data Sources', 'CSV Files'] or ['Tables', 'FCT_Orders']
  snippet:    string;     // secondary info line
  route:      string;
  score:      number;     // higher = better match
  tableId?:   string;
  sourceId?:  string;
}

const KIND_META: Record<string, { label: string; color: string; bg: string; icon: React.ReactNode }> = {
  table:   { label: 'Table',       color: NAVY,       bg: 'rgba(0,48,135,0.07)',  icon: <Table2    size={13} /> },
  column:  { label: 'Column',      color: '#334155',  bg: '#f1f5f9',              icon: <Columns   size={13} /> },
  measure: { label: 'Measure',     color: '#1e40af',  bg: 'rgba(30,64,175,0.07)', icon: <Code2     size={13} /> },
  kpi:     { label: 'KPI',         color: RED,        bg: 'rgba(200,16,46,0.07)', icon: <TrendingUp size={13} /> },
  source:  { label: 'Data Source', color: '#0f766e',  bg: 'rgba(15,118,110,0.07)',icon: <Database  size={13} /> },
};

/* ── Score: exact match > starts-with > contains ── */
function score(text: string, q: string): number {
  const t = text.toLowerCase(), s = q.toLowerCase();
  if (t === s)            return 100;
  if (t.startsWith(s))   return 80;
  if (t.includes(s))     return 60;
  return 0;
}

/* ── Build the full search index from model ── */
function buildIndex(model: any): Result[] {
  const results: Result[] = [];

  // Data sources
  (model.data_sources ?? []).forEach((ds: any) => {
    results.push({
      id: `src-${ds.id}`,
      kind: 'source',
      name: ds.name ?? '',
      breadcrumb: ['Data Sources'],
      snippet: [ds.source_type, ds.connection_mode, ds.server, ds.database].filter(Boolean).join(' · '),
      route: '/relationships',
      score: 0,
      sourceId: ds.id,
    });
  });

  // Tables + columns
  (model.tables ?? []).forEach((tbl: any) => {
    results.push({
      id: `tbl-${tbl.id}`,
      kind: 'table',
      name: tbl.name ?? '',
      breadcrumb: ['Tables'],
      snippet: [tbl.table_type, tbl.description, `${(tbl.columns ?? []).length} columns`].filter(Boolean).join(' · '),
      route: '/relationships',
      score: 0,
      tableId: tbl.id,
    });
    (tbl.columns ?? []).forEach((col: any) => {
      results.push({
        id: `col-${tbl.id}-${col.name}`,
        kind: 'column',
        name: col.name ?? '',
        breadcrumb: ['Tables', tbl.name],
        snippet: [col.data_type, col.semantic_role, col.description].filter(Boolean).join(' · '),
        route: '/relationships',
        score: 0,
        tableId: tbl.id,
      });
    });
  });

  // Measures
  (model.calculations ?? []).forEach((calc: any) => {
    results.push({
      id: `mea-${calc.id}`,
      kind: 'measure',
      name: calc.name ?? '',
      breadcrumb: ['Measures', calc.table_name].filter(Boolean),
      snippet: [calc.data_type, calc.description, calc.dax_expression?.slice(0, 80)].filter(Boolean).join(' · '),
      route: '/relationships',
      score: 0,
      tableId: calc.table_id,
    });
  });

  // KPIs
  (model.kpi_lineage ?? []).forEach((kpi: any) => {
    results.push({
      id: `kpi-${kpi.kpi_name}`,
      kind: 'kpi',
      name: kpi.kpi_name ?? '',
      breadcrumb: ['KPIs'],
      snippet: [kpi.semantic_type, kpi.data_type, kpi.description].filter(Boolean).join(' · '),
      route: '/relationships',
      score: 0,
    });
  });

  return results;
}

/* ── Highlight matched portion ── */
function Hl({ text, q }: { text: string; q: string }) {
  if (!q) return <>{text}</>;
  const idx = text.toLowerCase().indexOf(q.toLowerCase());
  if (idx === -1) return <>{text}</>;
  return (
    <>
      {text.slice(0, idx)}
      <mark style={{ background: 'rgba(0,48,135,0.13)', color: NAVY, borderRadius: 2, padding: '0 1px', fontWeight: 700 }}>
        {text.slice(idx, idx + q.length)}
      </mark>
      {text.slice(idx + q.length)}
    </>
  );
}

/* ════════════════════════════════════════════════════════
   MAIN COMPONENT
════════════════════════════════════════════════════════ */
export default function GlobalSearch() {
  const navigate = useNavigate();
  const [query,   setQuery]   = useState('');
  const [open,    setOpen]    = useState(false);
  const [focused, setFocused] = useState(-1);
  const inputRef  = useRef<HTMLInputElement>(null);
  const panelRef  = useRef<HTMLDivElement>(null);
  const itemRefs  = useRef<(HTMLButtonElement | null)[]>([]);

  /* Reload model on each open so it reflects fresh localStorage state */
  const model = useMemo(() => loadModel(), [open]);  // eslint-disable-line react-hooks/exhaustive-deps
  const index = useMemo(() => buildIndex(model), [model]);

  /* ── Filter + score ── */
  const results: Result[] = useMemo(() => {
    const q = query.trim();
    if (!q || q.length < 2) return [];

    return index
      .map(r => {
        const nameScore    = score(r.name,    q);
        const snippetScore = r.snippet.toLowerCase().includes(q.toLowerCase()) ? 30 : 0;
        const bc           = r.breadcrumb.join(' ').toLowerCase().includes(q.toLowerCase()) ? 10 : 0;
        return { ...r, score: nameScore + snippetScore + bc };
      })
      .filter(r => r.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 40);
  }, [query, index]);

  /* Group by kind */
  const grouped = useMemo(() => {
    const order: Result['kind'][] = ['table', 'kpi', 'measure', 'column', 'source'];
    const map = new Map<string, Result[]>();
    order.forEach(k => map.set(k, []));
    results.forEach(r => map.get(r.kind)?.push(r));
    return Array.from(map.entries()).filter(([, v]) => v.length > 0);
  }, [results]);

  /* Flat list for keyboard nav */
  const flat = useMemo(() => results, [results]);

  /* ── Navigate to result ── */
  const goTo = useCallback((r: Result) => {
    setQuery('');
    setOpen(false);
    setFocused(-1);

    const categoryMap: Record<string, string> = {
      table: 'Tables',
      column: 'Columns',
      measure: 'Measures',
      kpi: 'KPIs',
      source: 'Data Sources'
    };

    const targetPayload = {
      id: r.id,
      category: categoryMap[r.kind] || 'Tables',
      kind: r.kind,
      label: r.name,
      tableId: r.tableId,
      sourceId: r.sourceId,
      breadcrumb: r.breadcrumb
    };

    // Store target payload in localStorage for page load triggers
    localStorage.setItem('jnj:search-target', JSON.stringify(targetPayload));

    navigate('/relationships', { state: { globalSearch: r.name, kind: r.kind, id: r.id } });

    // Fire instant custom window event in case already on the page
    window.dispatchEvent(new CustomEvent('jnj:search-select', { detail: targetPayload }));
  }, [navigate]);

  /* ── Keyboard ── */
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!open) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setFocused(f => Math.min(f + 1, flat.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setFocused(f => Math.max(f - 1, -1));
    } else if (e.key === 'Enter' && focused >= 0) {
      e.preventDefault();
      goTo(flat[focused]);
    } else if (e.key === 'Escape') {
      setOpen(false);
      setFocused(-1);
      inputRef.current?.blur();
    }
  };

  /* Scroll focused item into view */
  useEffect(() => {
    if (focused >= 0) itemRefs.current[focused]?.scrollIntoView({ block: 'nearest' });
  }, [focused]);

  /* Click outside to close */
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (!panelRef.current?.contains(e.target as Node) &&
          !inputRef.current?.contains(e.target as Node)) {
        setOpen(false);
        setFocused(-1);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  /* Global Keyboard Shortcut Cmd+K / Ctrl+K */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        inputRef.current?.focus();
        setOpen(true);
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, []);

  const q = query.trim();
  let globalIdx = 0;

  return (
    <div style={{ position: 'relative', width: '100%', maxWidth: 640 }}>

      {/* ── Search bar ── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        background: open ? '#ffffff' : '#f8fafc',
        border: open ? '1px solid #c8102e' : '1px solid #cbd5e1',
        borderRadius: 6,
        padding: '0 12px',
        height: 36,
        boxShadow: open
          ? '0 0 0 2px rgba(200, 16, 46, 0.15), 0 2px 4px rgba(0, 0, 0, 0.05)'
          : 'none',
        transition: 'all 0.12s ease-in-out',
      }}>
        <Search size={14} style={{ color: open ? '#c8102e' : '#64748b', flexShrink: 0, transition: 'color 0.12s' }} />
        <input
          ref={inputRef}
          type="text"
          value={query}
          placeholder="Search tables, columns, KPIs, measures, sources…"
          onChange={e => { setQuery(e.target.value); setOpen(true); setFocused(-1); }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          style={{
            flex: 1,
            border: 'none', outline: 'none', background: 'transparent',
            fontSize: 12.5, color: '#0f172a', fontFamily: 'inherit',
            caretColor: '#c8102e',
          }}
        />
        {query && (
          <button
            onClick={() => { setQuery(''); setOpen(false); inputRef.current?.focus(); }}
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 2, color: '#94a3b8', lineHeight: 1, flexShrink: 0 }}
          >
            <X size={13} />
          </button>
        )}
      </div>

      {/* ── Results panel ── */}
      {open && (
        <div
          ref={panelRef}
          style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            left: 0, right: 0,
            background: '#ffffff',
            borderRadius: 6,
            border: '1px solid #cbd5e1',
            boxShadow: '0 8px 30px rgba(0,0,0,0.12)',
            zIndex: 9000,
            maxHeight: 520,
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
          }}
        >

          {/* No query yet */}
          {!q || q.length < 2 ? (
            <div style={{ padding: '18px 20px', fontSize: 12, color: '#64748b' }}>
              Type at least 2 characters to jump to a focused relationship context.
            </div>
          ) : results.length === 0 ? (
            <div style={{ padding: '24px 20px', textAlign: 'center' }}>
              <div style={{ fontSize: 28, marginBottom: 8 }}>🤷</div>
              <p style={{ margin: 0, fontSize: 13, fontWeight: 600, color: '#0f172a' }}>No results for "{q}"</p>
              <p style={{ margin: '4px 0 0', fontSize: 12, color: '#64748b' }}>Try a different keyword</p>
            </div>
          ) : (
            <>
              {/* Result count bar */}
              <div style={{
                padding: '8px 16px 6px',
                borderBottom: '1px solid #f1f5f9',
                fontSize: 10.5, fontWeight: 700, color: '#94a3b8',
                letterSpacing: '0.06em', textTransform: 'uppercase',
                flexShrink: 0,
              }}>
                {results.length} result{results.length !== 1 ? 's' : ''} for "{q}"
              </div>

              {/* Grouped results — scrollable */}
              <div style={{ overflowY: 'auto', flex: 1 }}>
                {grouped.map(([kind, items]) => {
                  const meta = KIND_META[kind];
                  return (
                    <div key={kind}>
                      {/* Group header */}
                      <div style={{
                        padding: '10px 16px 4px',
                        display: 'flex', alignItems: 'center', gap: 6,
                        position: 'sticky', top: 0,
                        background: 'rgba(255,255,255,0.94)',
                        backdropFilter: 'blur(16px)',
                        WebkitBackdropFilter: 'blur(16px)',
                        zIndex: 1,
                      }}>
                        <span style={{ color: meta.color, display: 'flex' }}>{meta.icon}</span>
                        <span style={{
                          fontSize: 9.5, fontWeight: 800, textTransform: 'uppercase',
                          letterSpacing: '0.08em', color: meta.color,
                        }}>
                          {meta.label}s
                        </span>
                        <span style={{
                          marginLeft: 4, fontSize: 9, fontWeight: 700,
                          background: meta.bg, color: meta.color,
                          border: `1px solid ${meta.color}33`,
                          borderRadius: 99, padding: '1px 6px',
                        }}>
                          {items.length}
                        </span>
                      </div>

                      {/* Items */}
                      {items.map(r => {
                        const idx     = globalIdx++;
                        const isFocused = focused === idx;
                        return (
                          <button
                            key={r.id}
                            ref={el => { itemRefs.current[idx] = el; }}
                            onClick={() => goTo(r)}
                            onMouseEnter={() => setFocused(idx)}
                            style={{
                              width: '100%',
                              display: 'flex', alignItems: 'center', gap: 12,
                              padding: '8px 16px',
                              background: isFocused ? meta.bg : 'transparent',
                              border: 'none', cursor: 'pointer',
                              textAlign: 'left',
                              transition: 'background 0.1s',
                              borderLeft: isFocused ? `3px solid ${meta.color}` : '3px solid transparent',
                            }}
                          >
                            {/* Left: icon badge */}
                            <div style={{
                              width: 32, height: 32, borderRadius: 8, flexShrink: 0,
                              background: meta.bg,
                              border: `1px solid ${meta.color}33`,
                              display: 'flex', alignItems: 'center', justifyContent: 'center',
                              color: meta.color,
                            }}>
                              {meta.icon}
                            </div>

                            {/* Center: name + breadcrumb + snippet */}
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <div style={{
                                fontSize: 13, fontWeight: 600, color: '#0f172a',
                                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                              }}>
                                <Hl text={r.name} q={q} />
                              </div>
                              {/* Breadcrumb */}
                              <div style={{
                                display: 'flex', alignItems: 'center', gap: 3,
                                fontSize: 10.5, color: '#94a3b8', marginTop: 1,
                              }}>
                                {r.breadcrumb.map((crumb, ci) => (
                                  <React.Fragment key={ci}>
                                    {ci > 0 && <ChevronRight size={9} style={{ flexShrink: 0, color: '#cbd5e1' }} />}
                                    <span style={{
                                      maxWidth: 140, overflow: 'hidden',
                                      textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                                    }}>
                                      <Hl text={crumb} q={q} />
                                    </span>
                                  </React.Fragment>
                                ))}
                              </div>
                              {/* Snippet */}
                              {r.snippet && (
                                <div style={{
                                  fontSize: 11, color: '#64748b', marginTop: 2,
                                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                                }}>
                                  <Hl text={r.snippet} q={q} />
                                </div>
                              )}
                            </div>

                            {/* Right: route hint */}
                            <div style={{
                              flexShrink: 0, fontSize: 9.5, fontWeight: 700,
                              color: isFocused ? meta.color : '#cbd5e1',
                              textTransform: 'uppercase', letterSpacing: '0.06em',
                              transition: 'color 0.1s',
                            }}>
                              {r.route === '/relationships' ? 'Explorer' :
                               r.route === '/lineage'       ? 'Lineage'  : 'View'}
                              {isFocused && ' →'}
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  );
                })}

                {/* Bottom padding */}
                <div style={{ height: 8 }} />
              </div>

              {/* Keyboard hint footer */}
              <div style={{
                padding: '6px 16px',
                borderTop: '1px solid rgba(255,255,255,0.55)',
                background: 'rgba(255,255,255,0.60)',
                backdropFilter: 'blur(12px)',
                WebkitBackdropFilter: 'blur(12px)',
                display: 'flex', alignItems: 'center', gap: 12,
                fontSize: 10, color: '#94a3b8',
                flexShrink: 0,
              }}>
                {[['↑↓', 'navigate'], ['↵', 'open'], ['esc', 'close']].map(([key, label]) => (
                  <span key={key} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    <kbd style={{
                      background: 'rgba(255,255,255,0.80)',
                      border: '1px solid rgba(255,255,255,0.95)',
                      boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
                      borderRadius: 4, padding: '1px 5px', fontSize: 9.5,
                      fontFamily: 'monospace', color: '#475569',
                    }}>{key}</kbd>
                    {label}
                  </span>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
