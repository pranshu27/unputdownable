import React, { useState, useMemo } from 'react';
import {
  DataModel, Calculation, KpiLineageItem, DataSource,
} from '../../data/sampleModel';
import {
  Search, X, Database, ChevronDown, ChevronRight, ChevronLeft,
  TrendingUp, Code2, Layers,
} from 'lucide-react';
import { cn } from '../../Lib/utils.ts';
import ContentCard from '../../core/CardContent/CardContent.tsx';
import FileWorkspaceHeader from '../../core/FileWorkspaceHeader.tsx';
import { useOutletContext, useLocation } from 'react-router-dom';
import RelationshipGraph from '../PowerBiPages/DataModel/OntologyGraph/RelationshipGraph.tsx';

interface Props { model: DataModel; }
type SideSection = 'sources' | 'tables' | 'measures' | 'kpis';

/* ── Fire the existing global search-select event that RelationshipGraph listens to ── */
function fireSelectEvent(payload: { id: string; category: string; label: string; tableId?: string; sourceId?: string }) {
  window.dispatchEvent(new CustomEvent('jnj:search-select', { detail: payload }));
}

export default function RelationshipsGraph({ model }: Props) {
  const { sideNavWidth } = useOutletContext<{ sideNavWidth: number }>();

  /* ── Sidebar state ── */
  const [sideQuery,    setSideQuery]    = useState('');
  const [graphExpanded, setGraphExpanded] = useState(true);
  const [selectedId,    setSelectedId]    = useState<string | null>(null);
  const [sidebarOpen,   setSidebarOpen]   = useState(true); // Open by default initially as requested
  const [openSections, setOpenSections] = useState<Record<SideSection, boolean>>({
    sources: false, tables: true, measures: false, kpis: false,
  });

  const toggleSection = (sec: SideSection) =>
    setOpenSections(p => ({ ...p, [sec]: !p[sec] }));

  /* ── Listen to search/select events to highlight Left Sidebar items ── */
  React.useEffect(() => {
    const handleSelect = (e: Event) => {
      const customEvent = e as CustomEvent;
      if (customEvent.detail) {
        let sid = customEvent.detail.id;
        // GlobalSearch might pass tbl-xxx, but the sidebar uses just the table id
        if (sid && sid.startsWith('tbl-')) {
            sid = sid.replace('tbl-', '');
        }
        setSelectedId(sid);
        
        // Automatically open the sidebar when search selection is made globally
        setSidebarOpen(true);
        const cat = customEvent.detail.category;
        if (cat === 'KPIs') setOpenSections(p => ({ ...p, kpis: true }));
        else if (cat === 'Measures') setOpenSections(p => ({ ...p, measures: true }));
        else if (cat === 'Data Sources') setOpenSections(p => ({ ...p, sources: true }));
        else if (cat === 'Tables' || cat === 'Columns') setOpenSections(p => ({ ...p, tables: true }));
      } else {
        setSelectedId(null);
      }
    };
    window.addEventListener('jnj:search-select', handleSelect);
    return () => window.removeEventListener('jnj:search-select', handleSelect);
  }, []);

  /* ── Handle deep linking from lineage page via location.state ── */
  const location = useLocation();
  React.useEffect(() => {
    const state = location.state as { globalSearch?: string, searchCategory?: string, id?: string } | null;
    if (state?.globalSearch) {
      let cat = state.searchCategory || 'Tables';
      let formattedId = state.id || state.globalSearch;
      
      // Look up the exact ID if we only have the name (e.g., navigating from lineage)
      if (!state.id) {
        if (cat === 'KPIs') {
          formattedId = `kpi-${state.globalSearch}`;
        } else if (cat === 'Measures') {
          formattedId = `mea-${state.globalSearch}`;
        } else if (cat === 'Data Sources') {
          const ds = model.data_sources.find(d => d.name === state.globalSearch);
          formattedId = ds ? `src-${ds.id}` : `src-${state.globalSearch}`;
        } else {
          cat = 'Tables';
          const t = model.tables.find(tbl => tbl.name === state.globalSearch);
          formattedId = t ? t.id : state.globalSearch;
        }
      }
      
      // We must defer the event firing until after the current render cycle
      // so the listener above has time to be registered.
      setTimeout(() => {
        fireSelectEvent({ id: formattedId, category: cat, label: state.globalSearch });
      }, 0);
      
      // Clear navigation state so it doesn't trigger again
      window.history.replaceState({}, '');
    }
  }, [location.state, model]);

  /* ── Filtered sidebar lists ── */
  const sq = sideQuery.toLowerCase().trim();
  const sidebarTables  = useMemo(() => model.tables.filter(t  => !sq || t.name.toLowerCase().includes(sq)),        [model.tables, sq]);
  const sidebarSources = useMemo(() => model.data_sources.filter(s => !sq || s.name.toLowerCase().includes(sq)),   [model.data_sources, sq]);
  const sidebarCalcs   = useMemo(() => model.calculations.filter((c: Calculation) => !sq || c.name.toLowerCase().includes(sq)), [model.calculations, sq]);
  const sidebarKpis    = useMemo(() => model.kpi_lineage.filter((k: KpiLineageItem) => !sq || k.kpi_name.toLowerCase().includes(sq)), [model.kpi_lineage, sq]);

  return (
    <ContentCard
      heading={null}
      sideNavWidth={sideNavWidth}
      headerComponent={<FileWorkspaceHeader pageTitle="Relationships" />}
      noscroll
      noPadding={true}
    >
      <div
        className="flex overflow-hidden relative"
        style={{ height: 'calc(100vh - 116px)', minHeight: 500 }}
      >
        {/* ══════════ LEFT SIDEBAR (COLLAPSIBLE) ═════════════════════ */}
        <div
          className="shrink-0 flex flex-col bg-white border-r border-stone-200 overflow-hidden transition-all duration-300 ease-in-out"
          style={{ width: sidebarOpen ? 224 : 0 }}
        >
          {/* Search */}
          <div className="px-3 py-2.5 border-b border-stone-200 shrink-0">
            <div className="relative">
              <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-stone-400 pointer-events-none" />
              <input
                value={sideQuery}
                onChange={e => setSideQuery(e.target.value)}
                placeholder="Filter entities…"
                className="w-full pl-7 pr-6 py-1.5 text-[11.5px] border border-stone-200 rounded-lg bg-stone-50 text-stone-800 placeholder-stone-400 focus:outline-none focus:border-stone-400 transition-colors"
              />
              {sideQuery && (
                <button
                  onClick={() => setSideQuery('')}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-stone-400 hover:text-stone-700"
                >
                  <X size={11} />
                </button>
              )}
            </div>
          </div>

          {/* Scrollable nav tree */}
          <div className="flex-1 overflow-y-auto">

            {/* ── Data Sources ── */}
            <SectionHeader
              icon={<Database size={11} className="text-stone-400" />}
              label="Data Sources"
              count={model.data_sources.length}
              open={openSections.sources}
              onToggle={() => toggleSection('sources')}
            />
            {openSections.sources && sidebarSources.map((s: DataSource) => (
              <SideItem
                key={s.id}
                label={s.name}
                sub={s.source_type}
                dotColor="#78716C"
                selected={selectedId === `src-${s.id}`}
                onClick={() => fireSelectEvent({ id: `src-${s.id}`, sourceId: s.id, category: 'Data Sources', label: s.name })}
              />
            ))}

            {/* ── Tables ── */}
            <SectionHeader
              icon={<Layers size={11} className="text-stone-400" />}
              label="Tables"
              count={model.tables.length}
              open={openSections.tables}
              onToggle={() => toggleSection('tables')}
            />
            {openSections.tables && sidebarTables.map(t => (
              <SideItem
                key={t.id}
                label={t.name}
                sub={`${t.columns.length} cols`}
                dotColor={t.table_type === 'fact' ? '#C8102E' : t.table_type === 'lookup' ? '#64748B' : '#003087'}
                dotShape="rounded-sm"
                selected={selectedId === t.id}
                onClick={() => fireSelectEvent({ id: t.id, tableId: t.id, category: 'Tables', label: t.name })}
              />
            ))}

            {/* ── Measures ── */}
            <SectionHeader
              icon={<Code2 size={11} className="text-stone-400" />}
              label="Measures"
              count={model.calculations.length}
              open={openSections.measures}
              onToggle={() => toggleSection('measures')}
            />
            {openSections.measures && sidebarCalcs.map((c: Calculation) => (
              <SideItem
                key={c.id}
                label={c.name}
                dotColor="#1E40AF"
                selected={selectedId === `mea-${c.id}`}
                onClick={() => fireSelectEvent({ id: `mea-${c.id}`, category: 'Measures', label: c.name })}
              />
            ))}

            {/* ── KPIs ── */}
            <SectionHeader
              icon={<TrendingUp size={11} className="text-stone-400" />}
              label="KPIs"
              count={model.kpi_lineage.length}
              open={openSections.kpis}
              onToggle={() => toggleSection('kpis')}
            />
            {openSections.kpis && sidebarKpis.map((k: KpiLineageItem) => (
              <SideItem
                key={k.kpi_name}
                label={k.kpi_name}
                dotColor="#10B981"
                selected={selectedId === `kpi-${k.kpi_name}`}
                onClick={() => fireSelectEvent({ id: `kpi-${k.kpi_name}`, category: 'KPIs', label: k.kpi_name })}
              />
            ))}

          </div>

          {/* Bottom stats bar */}
          <div className="px-3 py-2 border-t border-stone-200 shrink-0 flex items-center gap-3 text-[9.5px] text-stone-400">
            <span><strong className="text-stone-600 font-bold">{model.tables.length}</strong> tables</span>
            <span className="w-px h-3 bg-stone-200" />
            <span><strong className="text-stone-600 font-bold">{model.relationships.length}</strong> joins</span>
            <span className="w-px h-3 bg-stone-200" />
            <span><strong className="text-stone-600 font-bold">{model.calculations.length}</strong> measures</span>
          </div>
        </div>

        {/* ══════════ ORIGINAL REACTFLOW GRAPH ══════════════════════ */}
        <div className="flex-1 flex flex-col overflow-hidden bg-white relative">
          {/* Floating Sidebar Toggle Button (ChevronRight / ChevronLeft) */}
          <button
            type="button"
            onClick={() => setSidebarOpen(p => !p)}
            className={cn(
              "absolute top-[68px] z-20 flex items-center justify-center w-7 h-7 rounded-full border border-stone-200 bg-white text-stone-500 hover:text-[#003087] hover:border-[#003087] shadow-md transition-all duration-300 hover:scale-105 active:scale-95 cursor-pointer",
              sidebarOpen ? "left-4" : "left-4"
            )}
            title={sidebarOpen ? "Hide entities list" : "Show entities list"}
          >
            {sidebarOpen ? <ChevronLeft size={14} /> : <ChevronRight size={14} />}
          </button>

          <div
            className="flex-1 overflow-hidden relative flex flex-col"
          >
            <RelationshipGraph dataModel={model} graphExpanded={graphExpanded} />
          </div>
          <div className="h-8 shrink-0 flex items-center justify-between border-t border-stone-200 bg-stone-50 px-3">
            <span className="text-[10px] font-medium text-stone-400">
              {graphExpanded ? 'Graph visible' : 'Graph hidden'}
            </span>
            <button
              type="button"
              onClick={() => setGraphExpanded(current => !current)}
              className="flex items-center gap-1.5 rounded-md px-2 py-1 text-[10.5px] font-semibold text-stone-600 transition-colors hover:bg-stone-200 hover:text-stone-950"
            >
              {graphExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
              {graphExpanded ? 'Hide graph' : 'Show graph'}
            </button>
          </div>
        </div>
      </div>
    </ContentCard>
  );
}

/* ── Section header atom ─────────────────────────────────────────── */
function SectionHeader({
  icon, label, count, open, onToggle,
}: {
  icon: React.ReactNode;
  label: string;
  count: number;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      onClick={onToggle}
      className="w-full flex items-center gap-2 px-3 py-2.5 bg-stone-100 hover:bg-stone-200 border-b border-stone-200 transition-colors"
    >
      {open
        ? <ChevronDown size={11} className="text-stone-400 shrink-0" />
        : <ChevronRight size={11} className="text-stone-400 shrink-0" />}
      {icon}
      <span className="flex-1 text-left text-[9.5px] font-black uppercase tracking-widest text-stone-500 truncate">
        {label}
      </span>
      <span className="text-[9px] text-stone-400 font-mono bg-stone-200 px-1.5 py-0.5 rounded shrink-0">
        {count}
      </span>
    </button>
  );
}

/* ── Sidebar row atom ────────────────────────────────────────────── */
function SideItem({
  label, sub, dotColor, dotShape = 'rounded-full', selected, onClick,
}: {
  label: string;
  sub?: string;
  dotColor: string;
  dotShape?: string;
  selected?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full flex items-center gap-2.5 px-4 py-1.5 border-b transition-colors group",
        selected
          ? "bg-[#003087] border-[#002060] text-white hover:bg-[#003087]"
          : "bg-white border-stone-100 hover:bg-blue-50 hover:border-blue-100 text-stone-800"
      )}
    >
      <span 
        className={cn(
          'w-2 h-2 shrink-0 transition-transform group-hover:scale-110',
          selected ? 'bg-white' : '',
          dotShape
        )}
        style={{ backgroundColor: selected ? '#ffffff' : dotColor }}
      />
      <span className={cn(
        "flex-1 text-left truncate text-[11.5px] font-semibold",
        selected ? "text-white" : "text-stone-800 group-hover:text-blue-700"
      )}>
        {label}
      </span>
      {sub && (
        <span className={cn(
          "text-[10px] font-mono shrink-0",
          selected ? "text-blue-200" : "text-stone-450 group-hover:text-blue-400"
        )}>
          {sub}
        </span>
      )}
    </button>
  );
}
