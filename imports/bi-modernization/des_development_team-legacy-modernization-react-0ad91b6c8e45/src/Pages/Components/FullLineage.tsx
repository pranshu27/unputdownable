import React, { useMemo, useState, useRef, useEffect } from 'react';
import { DataModel } from '../../data/sampleModel';
import { Search, X, ChevronDown, ChevronRight, ChevronLeft, ExternalLink, Database, Table2, Tag, TrendingUp, Link2 } from 'lucide-react';
import ContentCard from '../../core/CardContent/CardContent.tsx';
import FileWorkspaceHeader from '../../core/FileWorkspaceHeader.tsx';
import { useOutletContext, useNavigate, useLocation } from 'react-router-dom';
import { Typography } from '@mui/material';

const NAVY = '#003087';

interface Props { model: DataModel; }

interface LineageRow {
  sourceId:   string;  sourceName: string;  sourceType: string;
  tableId:    string;  tableName:  string;  tableType:  string;
  columnName: string;  dataType:   string;
  nullable:   boolean; hidden:     boolean;
  usageTags:  string[];
  measures:   string[];
  kpis:       string[];
  relPairs:   string[];
}

/* normalise for fuzzy name matching: "DM.Customer_Detail_Table.csv" ↔ "DM Customer_Detail_Table" */
const normName = (s: string) => s.toLowerCase().replace(/[\s._]/g, '').replace(/csv$/, '');

function buildRows(model: DataModel): LineageRow[] {
  const rows: LineageRow[] = [];
  for (const table of model.tables) {
    const source =
      model.data_sources.find(ds => ds.id === table.source_data_source_id) ??
      model.data_sources.find(ds => normName(ds.name) === normName(table.name));
    for (const col of table.columns) {
      const usageTags: string[] = [];
      if (col.used_in_relationships) usageTags.push('Key');
      if (col.used_in_filters)       usageTags.push('Filter');
      if (col.used_in_calculations)  usageTags.push('Calc');
      if (col.used_in_groupby)       usageTags.push('GroupBy');
      if (col.semantic_role)         usageTags.push(col.semantic_role === 'primary_key' ? 'PK' : col.semantic_role === 'foreign_key' ? 'FK' : 'Geo');

      const measures = (model.calculations as any[]).filter(c =>
        Array.isArray(c.depends_on_columns) && c.depends_on_columns.some((dep: string) => {
          const dot = dep.indexOf('.');
          if (dot > -1) return dep.slice(0,dot).toLowerCase() === table.name.toLowerCase() && dep.slice(dot+1).toLowerCase() === col.name.toLowerCase();
          return dep.toLowerCase() === col.name.toLowerCase();
        })
      ).map(c => c.name);

      const kpis = (model.kpi_lineage ?? []).filter(k =>
        (k.depends_on_columns ?? []).some((dc: any) =>
          dc.table_name?.toLowerCase() === table.name.toLowerCase() &&
          dc.column_name?.toLowerCase() === col.name.toLowerCase()
        )
      ).map(k => k.kpi_name);

      const relPairs = model.relationships
        .filter(r => (r.left_table_id===table.id&&r.left_column===col.name)||(r.right_table_id===table.id&&r.right_column===col.name))
        .map(r => {
          const lt = model.tables.find(t=>t.id===r.left_table_id);
          const rt = model.tables.find(t=>t.id===r.right_table_id);
          return `${lt?.name??r.left_table_id}.${r.left_column} ↔ ${rt?.name??r.right_table_id}.${r.right_column}`;
        });

      rows.push({
        sourceId:   source?.id   ?? table.id,
        sourceName: source?.name ?? table.name,
        sourceType: source?.source_type ?? '—',
        tableId: table.id, tableName: table.name, tableType: table.table_type,
        columnName: col.name, dataType: col.data_type,
        nullable: col.nullable, hidden: col.hidden,
        usageTags, measures, kpis, relPairs,
      });
    }
  }
  return rows;
}

/* ── Expandable list cell ──────────────────────────────────────── */
function ExpandList({ items, onClick }: { items: string[]; onClick?: (item: string) => void }) {
  const [open, setOpen] = useState(false);
  if (items.length === 0) return <span style={{ color:'#9ca3af' }}>—</span>;
  if (items.length === 1) return (
    <span onClick={() => onClick && onClick(items[0])} style={{ fontSize:'11.5px', fontFamily:'monospace', color:'#374151', cursor: onClick ? 'pointer' : 'default', textDecoration:'none' }}
      onMouseEnter={e => onClick && ((e.target as HTMLElement).style.textDecoration = 'underline')}
      onMouseLeave={e => ((e.target as HTMLElement).style.textDecoration = 'none')}>
      {items[0]}
    </span>
  );
  return (
    <div>
      <button onClick={() => setOpen(o => !o)}
        style={{ display:'flex', alignItems:'center', gap:4, fontSize:11, fontWeight:600, color:'#4b5563', background:'none', border:'none', cursor:'pointer', padding:0 }}>
        {open ? <ChevronDown size={11}/> : <ChevronRight size={11}/>}
        <span style={{ color:'inherit' }}>{items.length} items</span>
      </button>
      {open && (
        <div style={{ marginTop:4, paddingLeft:12, borderLeft:'2px solid #e5e7eb' }}>
          {items.map(item => (
            <div key={item} onClick={() => onClick && onClick(item)}
              style={{ fontSize:11, fontFamily:'monospace', color:'#374151', cursor: onClick ? 'pointer' : 'default', padding:'1px 0' }}
              onMouseEnter={e => onClick && ((e.target as HTMLElement).style.textDecoration = 'underline')}
              onMouseLeave={e => ((e.target as HTMLElement).style.textDecoration = 'none')}>
              {item}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Filter chip button ────────────────────────────────────────── */
function FilterChip({ active, onClick, label, count }: { active: boolean; onClick: () => void; label: string; count?: number }) {
  const ref = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.setProperty('display',          'flex',                                        'important');
    el.style.setProperty('align-items',      'center',                                      'important');
    el.style.setProperty('justify-content',  'space-between',                               'important');
    el.style.setProperty('gap',              '6px',                                         'important');
    el.style.setProperty('padding',          '5.5px 10px',                                  'important');
    el.style.setProperty('font-size',        '11.5px',                                      'important');
    el.style.setProperty('font-weight',      active ? '600' : '500',                        'important');
    el.style.setProperty('line-height',      '1.4',                                         'important');
    el.style.setProperty('border-radius',    '6px',                                         'important');
    el.style.setProperty('width',            '100%',                                        'important');
    el.style.setProperty('text-align',       'left',                                        'important');
    el.style.setProperty('cursor',           'pointer',                                     'important');
    el.style.setProperty('outline',          'none',                                        'important');
    el.style.setProperty('white-space',      'nowrap',                                      'important');
    el.style.setProperty('border',           'none',                                        'important');
    el.style.setProperty('background-color', active ? 'rgba(0, 48, 135, 0.08)' : 'transparent', 'important');
    el.style.setProperty('color',            active ? '#003087' : '#475569',                'important');
  }, [active]);

  return (
    <button 
      ref={ref} 
      onClick={onClick}
      onMouseEnter={e => { if (!active) e.currentTarget.style.backgroundColor = '#f1f5f9'; }}
      onMouseLeave={e => { if (!active) e.currentTarget.style.backgroundColor = 'transparent'; }}
    >
      <span style={{ overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', minWidth:0, flex:1 }}>
        {label}
      </span>
      {count !== undefined && (
        <span style={{ fontSize:10, fontFamily:'monospace', opacity:0.7, flexShrink:0, color: active ? '#003087' : '#64748b' }}>
          {count}
        </span>
      )}
    </button>
  );
}

/* ═══════════════════════════════════════════════════════════════
   MAIN COMPONENT
═══════════════════════════════════════════════════════════════ */
export default function FullLineage({ model }: Props) {
  const { sideNavWidth } = useOutletContext<{ sideNavWidth: number }>();
  const navigate = useNavigate();
  const location = useLocation();

  const [query,        setQuery]        = useState('');
  const [sidebarOpen,  setSidebarOpen]  = useState(true); // Open by default initially
  const [sourceFilter, setSourceFilter] = useState('all');
  const [typeFilter,   setTypeFilter]   = useState('all');
  const [usageFilter,  setUsageFilter]  = useState('all');
  const [page,         setPage]         = useState(0);
  const PAGE_SIZE = 100;

  /* Auto-populate search from GlobalSearch navigation state & custom event */
  useEffect(() => {
    const state = location.state as { globalSearch?: string } | null;
    if (state?.globalSearch) {
      setQuery(state.globalSearch);
      window.history.replaceState({}, '');
    }

    const handleSearchSelect = (e: Event) => {
      const customEvent = e as CustomEvent;
      if (customEvent.detail) {
        const { category, label } = customEvent.detail;
        if (category === 'Data Sources') {
          setSourceFilter(label || 'all');
          setQuery('');
        } else if (category === 'Tables') {
          setQuery(label || '');
          setSourceFilter('all');
        } else {
          setQuery(label || '');
        }
        setPage(0);
        // Automatically open filters sidebar when filter dispatch is received
        setSidebarOpen(true);
      }
    };
    window.addEventListener('jnj:search-select', handleSearchSelect);
    return () => {
      window.removeEventListener('jnj:search-select', handleSearchSelect);
    };
  }, [location.state]);

  const allRows    = useMemo(() => buildRows(model), [model]);
  const sources    = useMemo(() => Array.from(new Set(allRows.map(r => r.sourceName))).sort(), [allRows]);
  const tableTypes = useMemo(() => Array.from(new Set(allRows.map(r => r.tableType))).sort(), [allRows]);
  const usageOptions = ['Key', 'Filter', 'Calc', 'GroupBy', 'PK', 'FK'];

  /* per-source stats */
  const sourceStats = useMemo(() => {
    const m: Record<string, { tables: Set<string>; cols: number }> = {};
    allRows.forEach(r => {
      if (!m[r.sourceName]) m[r.sourceName] = { tables: new Set(), cols: 0 };
      m[r.sourceName].tables.add(r.tableName);
      m[r.sourceName].cols++;
    });
    return m;
  }, [allRows]);

  const filtered = useMemo(() => {
    const q = query.toLowerCase().trim();
    let rows = allRows;
    if (sourceFilter !== 'all') rows = rows.filter(r => r.sourceName === sourceFilter);
    if (typeFilter   !== 'all') rows = rows.filter(r => r.tableType  === typeFilter);
    if (usageFilter  !== 'all') rows = rows.filter(r => r.usageTags.includes(usageFilter));
    if (q) rows = rows.filter(r =>
      r.sourceName.toLowerCase().includes(q) || r.tableName.toLowerCase().includes(q) ||
      r.columnName.toLowerCase().includes(q) || r.dataType.toLowerCase().includes(q) ||
      r.measures.some(m => m.toLowerCase().includes(q)) || r.kpis.some(k => k.toLowerCase().includes(q))
    );
    return rows;
  }, [allRows, sourceFilter, typeFilter, usageFilter, query]);

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const paged = filtered.slice(page * PAGE_SIZE, (page+1) * PAGE_SIZE);
  const resetPage = () => setPage(0);

  const withMeasures = filtered.filter(r => r.measures.length  > 0).length;
  const withKpis     = filtered.filter(r => r.kpis.length      > 0).length;
  const withRels     = filtered.filter(r => r.relPairs.length  > 0).length;

  const exportCsv = () => {
    const header = ['Source','Source Type','Table','Table Type','Column','Data Type','Nullable','Hidden','Usage Tags','KPIs','Relationships'];
    const lines = filtered.map(r => [
      r.sourceName,r.sourceType,r.tableName,r.tableType,r.columnName,r.dataType,
      r.nullable?'yes':'no', r.hidden?'yes':'no',
      r.usageTags.join('; '),r.kpis.join('; '),r.relPairs.join('; '),
    ].map(v=>`"${String(v).replace(/"/g,'""')}"`).join(','));
    const csv = [header.join(','), ...lines].join('\n');
    const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(new Blob([csv],{type:'text/csv'})), download:'report_lineage.csv' });
    a.click();
  };

  const hasFilters = sourceFilter !== 'all' || typeFilter !== 'all' || usageFilter !== 'all' || !!query;

  return (
    <ContentCard
      heading={null}
      sideNavWidth={sideNavWidth}
      headerComponent={<FileWorkspaceHeader pageTitle="Full Lineage" />}
      noscroll
      noPadding={true}
    >
      <div
        className="flex overflow-hidden relative w-full h-full"
        style={{ height: 'calc(100vh - 116px)', minHeight: 500 }}
      >
        {/* ══════════ LEFT SIDEBAR ════════════════════════════ */}
        <div 
          className="shrink-0 flex flex-col bg-white border-r border-stone-200 overflow-hidden transition-all duration-300 ease-in-out"
          style={{ width: sidebarOpen ? 240 : 0 }}
        >
          {/* Summary stats */}
          <div className="px-4 py-4 border-b border-stone-200 bg-stone-50/50">
            <p style={{ fontSize:9, fontWeight:900, textTransform:'uppercase', letterSpacing:'0.1em', color:'#78716c', marginBottom:12, marginTop:0 }}>Summary</p>
            <div className="space-y-2">
              {[
                { icon: <Table2 size={13} style={{ color:'#78716c' }}/>, label: 'Total columns', value: allRows.length },
                { icon: <Database size={13} style={{ color:'#78716c' }}/>, label: 'Data sources',  value: model.data_sources.length },
                { icon: <Tag size={13} style={{ color:'#78716c' }}/>,      label: 'Tables',         value: model.tables.length },
                { icon: <TrendingUp size={13} style={{ color:'#78716c' }}/>,label: 'Linked to KPIs', value: allRows.filter(r=>r.kpis.length>0).length },
                { icon: <Link2 size={13} style={{ color:'#78716c' }}/>,    label: 'In joins',        value: allRows.filter(r=>r.relPairs.length>0).length },
              ].map(s => (
                <div key={s.label} className="flex items-center gap-2.5">
                  {s.icon}
                  <span style={{ flex:1, fontSize:'11.5px', color:'#57534e', fontWeight:500 }}>{s.label}</span>
                  <span style={{ fontSize:13, fontWeight:700, color:'#1c1917' }}>{s.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Filters — scrollable */}
          <div className="flex-1 min-h-0 overflow-y-auto px-4 py-4 space-y-5">
            {/* Source filter */}
            <div>
              <p style={{ fontSize:9, fontWeight:900, textTransform:'uppercase', letterSpacing:'0.1em', color:'#78716c', marginBottom:8, marginTop:0, display:'flex', alignItems:'center', gap:6 }}>
                <Database size={10}/> Data Source
              </p>
              <div className="space-y-1">
                <FilterChip active={sourceFilter === 'all'} onClick={() => { setSourceFilter('all'); resetPage(); }} label="All sources" count={allRows.length} />
                {sources.map(s => (
                  <FilterChip key={s} active={sourceFilter === s} onClick={() => { setSourceFilter(s); resetPage(); }} label={s} count={sourceStats[s]?.cols ?? 0} />
                ))}
              </div>
            </div>

            {/* Table type filter */}
            <div>
              <p style={{ fontSize:9, fontWeight:900, textTransform:'uppercase', letterSpacing:'0.1em', color:'#78716c', marginBottom:8, marginTop:0, display:'flex', alignItems:'center', gap:6 }}>
                <Table2 size={10}/> Table Type
              </p>
              <div className="space-y-1">
                <FilterChip active={typeFilter === 'all'} onClick={() => { setTypeFilter('all'); resetPage(); }} label="All types" />
                {tableTypes.map(t => (
                  <FilterChip key={t} active={typeFilter === t} onClick={() => { setTypeFilter(t); resetPage(); }} label={t.charAt(0).toUpperCase() + t.slice(1)} />
                ))}
              </div>
            </div>

            {/* Usage filter */}
            <div>
              <p style={{ fontSize:9, fontWeight:900, textTransform:'uppercase', letterSpacing:'0.1em', color:'#78716c', marginBottom:8, marginTop:0, display:'flex', alignItems:'center', gap:6 }}>
                <Tag size={10}/> Column Usage
              </p>
              <div className="space-y-1">
                <FilterChip active={usageFilter === 'all'} onClick={() => { setUsageFilter('all'); resetPage(); }} label="All usage" />
                {usageOptions.map(u => {
                  const count = allRows.filter(r => r.usageTags.includes(u)).length;
                  if (count === 0) return null;
                  return (
                    <FilterChip key={u} active={usageFilter === u} onClick={() => { setUsageFilter(u); resetPage(); }} label={u} count={count} />
                  );
                })}
              </div>
            </div>
          </div>

          {/* Bottom: Clear Filters */}
          <div className="px-4 py-3 border-t border-stone-200 shrink-0 bg-stone-50/50">
            {hasFilters && (
              <button
                onClick={() => { setSourceFilter('all'); setTypeFilter('all'); setUsageFilter('all'); setQuery(''); resetPage(); }}
                style={{ width:'100%', fontSize:11, padding:'6px 0', borderRadius:8, border:'1px solid #e7e5e4', backgroundColor:'#fff', color:'#57534e', fontWeight:600, cursor:'pointer' }}
                className="hover:bg-stone-50 hover:text-stone-700 transition-colors"
              >
                Clear filters
              </button>
            )}
          </div>
        </div>

        {/* ══════════ MAIN TABLE AREA ═════════════════════════ */}
        <div className="flex-1 flex flex-col overflow-hidden bg-white">
          {/* ── Toolbar (with Collapsible Toggle Button + Inline elements) ── */}
          <div style={{ display:'flex', alignItems:'center', gap:12, padding:'10px 16px', borderBottom:'1px solid #cbd5e1', flexShrink:0, backgroundColor:'#f8fafc' }}>
            {/* Sidebar Collapse Toggle Button */}
            <button
              type="button"
              onClick={() => setSidebarOpen(p => !p)}
              className="flex items-center justify-center w-7 h-7 rounded-full border border-stone-200 bg-white text-stone-500 hover:text-[#003087] hover:border-[#003087] shadow-sm transition-all hover:scale-105 active:scale-95 cursor-pointer flex-shrink-0"
              title={sidebarOpen ? "Collapse filters" : "Expand filters"}
            >
              {sidebarOpen ? <ChevronLeft size={13} /> : <ChevronRight size={13} />}
            </button>

            {/* Search */}
            <div style={{ position:'relative', flex:1, maxWidth:320 }}>
              <Search size={13} style={{ position:'absolute', left:10, top:'50%', transform:'translateY(-50%)', color:'#6b7280', pointerEvents:'none', zIndex:1 }}/>
              <input
                type="text"
                value={query}
                onChange={e => { setQuery(e.target.value); resetPage(); }}
                placeholder="Search variables..."
                style={{
                  width: '100%',
                  padding: '6px 30px 6px 32px',
                  fontSize: 12,
                  fontFamily: 'inherit',
                  color: '#111827',
                  backgroundColor: '#ffffff',
                  border: '1px solid #cbd5e1',
                  borderRadius: 6,
                  outline: 'none',
                  boxSizing: 'border-box',
                }}
                onFocus={e => { e.currentTarget.style.borderColor = '#003087'; e.currentTarget.style.boxShadow = '0 0 0 2px rgba(0,48,135,0.12)'; }}
                onBlur={e => { e.currentTarget.style.borderColor = '#cbd5e1'; e.currentTarget.style.boxShadow = 'none'; }}
              />
              {query && (
                <button
                  onClick={() => { setQuery(''); resetPage(); }}
                  style={{ position:'absolute', right:8, top:'50%', transform:'translateY(-50%)', background:'none', border:'none', cursor:'pointer', padding:0, color:'#9ca3af' }}
                >
                  <X size={12}/>
                </button>
              )}
            </div>

            {/* Active filter pills (styled in beautiful JNJ Active Blue!) */}
            <div style={{ display:'flex', alignItems:'center', gap:6, flexWrap:'wrap' }}>
              {sourceFilter !== 'all' && (
                <span style={{ display:'flex', alignItems:'center', gap:4, fontSize:'10.5px', backgroundColor:'rgba(0, 48, 135, 0.08)', border:'1px solid rgba(0, 48, 135, 0.15)', color:'#003087', padding:'2.5px 8px', borderRadius:999, fontWeight:700 }}>
                  <span>Source: {sourceFilter}</span>
                  <button onClick={() => { setSourceFilter('all'); resetPage(); }} style={{ background:'none', border:'none', color:'#003087', cursor:'pointer', padding:0, display:'flex', alignItems:'center' }} title="Clear source filter"><X size={10}/></button>
                </span>
              )}
              {typeFilter !== 'all' && (
                <span style={{ display:'flex', alignItems:'center', gap:4, fontSize:'10.5px', backgroundColor:'rgba(0, 48, 135, 0.08)', border:'1px solid rgba(0, 48, 135, 0.15)', color:'#003087', padding:'2.5px 8px', borderRadius:999, fontWeight:700, textTransform:'capitalize' }}>
                  <span>Type: {typeFilter}</span>
                  <button onClick={() => { setTypeFilter('all'); resetPage(); }} style={{ background:'none', border:'none', color:'#003087', cursor:'pointer', padding:0, display:'flex', alignItems:'center' }} title="Clear type filter"><X size={10}/></button>
                </span>
              )}
              {usageFilter !== 'all' && (
                <span style={{ display:'flex', alignItems:'center', gap:4, fontSize:'10.5px', backgroundColor:'rgba(0, 48, 135, 0.08)', border:'1px solid rgba(0, 48, 135, 0.15)', color:'#003087', padding:'2.5px 8px', borderRadius:999, fontWeight:700 }}>
                  <span>Usage: {usageFilter}</span>
                  <button onClick={() => { setUsageFilter('all'); resetPage(); }} style={{ background:'none', border:'none', color:'#003087', cursor:'pointer', padding:0, display:'flex', alignItems:'center' }} title="Clear usage filter"><X size={10}/></button>
                </span>
              )}
            </div>

            {/* Stats (KPIs, Joins) */}
            <div style={{ marginLeft:'auto', display:'flex', alignItems:'center', gap:16, fontSize:'11.5px', color:'#57534e', flexShrink:0 }}>
              <span>Columns: <strong style={{ color:'#0f172a', fontWeight:700 }}>{filtered.length.toLocaleString()}</strong></span>
              <span>KPIs: <strong style={{ color:'#0f172a', fontWeight:700 }}>{withKpis}</strong></span>
              <span>Joins: <strong style={{ color:'#0f172a', fontWeight:700 }}>{withRels}</strong></span>
            </div>

            {/* Export CSV (Always accessible on the far right of top toolbar!) */}
            <button
              onClick={exportCsv}
              className="flex items-center gap-1.5 px-3 py-1.5 text-[11.5px] font-bold rounded-lg border border-stone-200 bg-white hover:bg-stone-50 text-[#003087] hover:text-[#002060] hover:border-[#003087] shadow-sm transition-all hover:scale-[1.02] cursor-pointer flex-shrink-0"
              title={`Export ${filtered.length.toLocaleString()} columns as CSV`}
            >
              <ExternalLink size={12} />
              <span>Export CSV</span>
            </button>
          </div>

          {/* ── Table Grid ── */}
          <div style={{ flex: 1, overflowY: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left', minWidth: 1100 }}>
              <thead style={{ position: 'sticky', top: 0, backgroundColor: '#ffffff', zIndex: 10, borderBottom: '2px solid #cbd5e1' }}>
                <tr style={{ backgroundColor:'#f3f4f6' }}>
                  <th style={{ padding: '10px 12px', fontWeight: 700, color: '#374151', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Source</th>
                  <th style={{ padding: '10px 12px', fontWeight: 700, color: '#374151', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Table</th>
                  <th style={{ padding: '10px 12px', fontWeight: 700, color: '#374151', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Column</th>
                  <th style={{ padding: '10px 12px', fontWeight: 700, color: '#374151', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Data Type</th>
                  <th style={{ padding: '10px 12px', fontWeight: 700, color: '#374151', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Usage</th>
                  <th style={{ padding: '10px 12px', fontWeight: 700, color: '#374151', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>KPIs</th>
                  <th style={{ padding: '10px 12px', fontWeight: 700, color: '#374151', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Relationships</th>
                </tr>
              </thead>
              <tbody>
                {paged.length === 0 ? (
                  <tr>
                    <td colSpan={7} style={{ padding: '40px', textAlign: 'center', color: '#6b7280' }}>
                      No variables match the selected filters and search query.
                    </td>
                  </tr>
                ) : (
                  paged.map((row, idx) => {
                    const prev      = paged[idx-1];
                    const newSource = !prev || prev.sourceId  !== row.sourceId;
                    const newTable  = !prev || prev.tableId   !== row.tableId;
                    const isFact    = row.tableType === 'fact';

                    return (
                      <tr
                        key={`${row.tableId}-${row.columnName}-${idx}`}
                        style={{
                          borderBottom: '1px solid #e7e5e4',
                          backgroundColor: idx % 2 === 0 ? '#ffffff' : '#f9fafb',
                          transition: 'background-color 0.12s ease',
                        }}
                        className={`hover:bg-[#eff6ff] ${newTable && idx > 0 ? 'border-t-2 border-stone-200' : ''} align-top`}
                      >
                        {/* Source (Interactive Click-to-Filter Data Source) */}
                        <td style={{ padding: '10px 12px' }}>
                          {newSource ? (
                            <button
                              onClick={() => { setSourceFilter(row.sourceName); resetPage(); }}
                              style={{ border: 'none', background: 'none', padding: 0 }}
                              className="inline-flex items-center gap-1.5 text-left text-[12px] font-bold text-stone-900 hover:text-[#003087] hover:underline cursor-pointer group"
                              title={`Filter variables by datasource: ${row.sourceName}`}
                            >
                              <Database size={13} className="text-stone-500 shrink-0 group-hover:text-[#003087] transition-colors" />
                              <span className="underline decoration-stone-200 group-hover:decoration-blue-300">{row.sourceName}</span>
                            </button>
                          ) : (
                            <span className="text-[11px] text-stone-400 pl-3 block" title={row.sourceName}>
                              ↳
                            </span>
                          )}
                        </td>

                        {/* Table (Click to focus table on relationships canvas) */}
                        <td style={{ padding: '10px 12px' }}>
                          {newTable ? (
                            <div>
                              <button
                                onClick={() => navigate('/relationships', { state: { globalSearch: row.tableName } })}
                                className="inline-flex items-center gap-1 text-[12px] font-mono font-bold text-[#003087] hover:underline text-left cursor-pointer transition-colors group border-none background-none p-0"
                                title={`Focus table ${row.tableName} on relationships canvas`}
                              >
                                <span className="underline decoration-blue-100 hover:decoration-blue-500 group-hover:text-[#002060]">{row.tableName}</span>
                                <Link2 size={11} className="text-blue-500 opacity-60 shrink-0 group-hover:text-blue-700" />
                              </button>
                              <div style={{ marginTop: 2 }}>
                                <span style={{
                                  fontSize: '9px',
                                  fontWeight: 700,
                                  textTransform: 'uppercase',
                                  padding: '1px 5px',
                                  borderRadius: 4,
                                  backgroundColor: isFact ? '#fee2e2' : '#e0f2fe',
                                  color: isFact ? '#b91c1c' : '#0369a1'
                                }}>{row.tableType}</span>
                              </div>
                            </div>
                          ) : (
                            <button
                              onClick={() => navigate('/relationships', { state: { globalSearch: row.tableName } })}
                              style={{ border: 'none', background: 'none', padding: 0 }}
                              className="text-[11px] pl-3 font-mono text-stone-500 hover:text-[#003087] hover:underline block text-left cursor-pointer"
                              title={row.tableName}
                            >
                              ↳ {row.tableName}
                            </button>
                          )}
                        </td>

                        {/* Column */}
                        <td style={{ padding: '10px 12px' }}>
                          <span style={{
                            fontWeight: 600,
                            color: row.hidden ? '#a8a29e' : '#292524',
                            textDecoration: row.hidden ? 'line-through' : 'none'
                          }} className="font-mono">{row.columnName}</span>
                          {row.hidden && <span className="ml-1.5 text-[8.5px] bg-amber-50 text-amber-700 border border-amber-200 rounded px-1 py-0.2 font-bold uppercase">hidden</span>}
                          {!row.nullable && <div style={{ fontSize: '9px', color: '#78716c', fontWeight: 600, marginTop: 2 }}>NOT NULL</div>}
                        </td>

                        {/* Data Type */}
                        <td style={{ padding: '10px 12px', fontFamily: 'monospace', color: '#44403c' }}>
                          {row.dataType.replace(/_/g, ' ')}
                        </td>

                        {/* Usage Badges */}
                        <td style={{ padding: '10px 12px' }}>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                            {row.usageTags.map(tag => (
                              <span
                                key={tag}
                                style={{
                                  fontSize: '9px',
                                  fontWeight: 700,
                                  padding: '2px 6px',
                                  borderRadius: '4px',
                                  backgroundColor:
                                    tag === 'PK' ? '#fee2e2' :
                                    tag === 'FK' ? '#dbeafe' :
                                    tag === 'Key' ? '#fef9c3' : '#f3f4f6',
                                  color:
                                    tag === 'PK' ? '#b91c1c' :
                                    tag === 'FK' ? '#1d4ed8' :
                                    tag === 'Key' ? '#a16207' : '#374151',
                                }}
                              >
                                {tag}
                              </span>
                            ))}
                            {row.usageTags.length === 0 && <span style={{ color: '#9ca3af' }}>—</span>}
                          </div>
                        </td>

                        {/* KPIs */}
                        <td style={{ padding: '10px 12px', maxWidth: '200px' }}>
                          <ExpandList
                            items={row.kpis}
                            onClick={(item) => navigate('/relationships', { state: { globalSearch: item, searchCategory: 'KPIs' } })}
                          />
                        </td>

                        {/* Relationships */}
                        <td style={{ padding: '10px 12px', maxWidth: '240px' }}>
                          <ExpandList
                            items={row.relPairs}
                            onClick={() => navigate('/relationships')}
                          />
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* ── Pagination (styled inline with JNJ Active Blue accents) ── */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between px-5 py-3 border-t border-stone-200 bg-stone-50 shrink-0 select-none">
              <span className="text-[11.5px] text-stone-600">
                Showing <strong className="text-stone-900">{page*PAGE_SIZE+1}–{Math.min((page+1)*PAGE_SIZE, filtered.length)}</strong> of <strong className="text-stone-900">{filtered.length.toLocaleString()}</strong> rows
              </span>
              <div className="flex items-center gap-1">
                <button
                  disabled={page === 0}
                  onClick={() => setPage(p => p - 1)}
                  className="px-3 py-1.5 text-[11px] font-bold rounded-lg border border-stone-200 bg-white text-stone-700 hover:bg-stone-100 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer transition-colors"
                >
                  ← Prev
                </button>
                {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
                  const pn = totalPages <= 7 ? i : Math.max(0, Math.min(page-3, totalPages-7)) + i;
                  return (
                    <button
                      key={pn}
                      onClick={() => setPage(pn)}
                      className={`w-8 h-8 text-[11px] font-bold rounded-lg border transition-all cursor-pointer ${
                        page === pn
                          ? 'bg-[#003087] text-white border-[#003087]'
                          : 'border-stone-200 text-stone-700 bg-white hover:bg-stone-50 hover:text-stone-900'
                      }`}
                    >
                      {pn + 1}
                    </button>
                  );
                })}
                <button
                  disabled={page === totalPages - 1}
                  onClick={() => setPage(p => p + 1)}
                  className="px-3 py-1.5 text-[11px] font-bold rounded-lg border border-stone-200 bg-white text-stone-700 hover:bg-stone-100 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer transition-colors"
                >
                  Next →
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </ContentCard>
  );
}
