import React, { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { useOutletContext } from 'react-router-dom';
import ContentCard from '../../core/CardContent/CardContent.tsx';
import FileWorkspaceHeader from '../../core/FileWorkspaceHeader.tsx';
import {
  fetchPowerBiReport,
  listPowerBiReports,
  ReportListItem,
} from '../../services/powerbiReports.ts';
import { useDispatch, useSelector } from 'react-redux';
import {
  startJob, advanceStep, addJobLog,
  completeJob, failJob, saveJobResult, loadJobResult, clearJobResult,
  selectJob,
} from '../../utils/jobTrackerSlice.ts';
import {
  AlertTriangle, ArrowRight, BookOpen, Check, CheckCircle2,
  ChevronDown, ChevronRight, ChevronUp, Database, FileSearch,
  FileSpreadsheet, Hash, Info, Layers, Link2, ListOrdered,
  Loader2, RefreshCw, Save, Search, Shield, Sparkles, Tag,
  TrendingUp, UploadCloud, User, X, Zap, BarChart2, Target,
  Play, Clock, CheckSquare, XSquare, Minus, Activity,
} from 'lucide-react';

// ─── Constants ──────────────────────────────────────────────────────────────
const REPORTS_API = 'http://20.72.80.42:8001';
const ENRICHMENT_API = 'http://20.72.80.42:8002';
const GAP_API_URL = 'http://20.72.80.42:8001/gapanalysis/';

// ─── Theme ──────────────────────────────────────────────────────────────────
const T = {
  navy:      '#002147',
  red:       '#c8102e',
  slate:     '#64748b',
  border:    '#e2e8f0',
  bg:        '#f8fafc',
  white:     '#ffffff',
  text:      '#0f172a',
  textMid:   '#475569',
  textLight: '#94a3b8',
  green:     '#059669',
  amber:     '#d97706',
  orange:    '#ea580c',
};

type JobStatus = 'idle' | 'running' | 'done' | 'error';
type ActiveTab = 'gap' | 'kpi' | 'enrich' | 'glossary';

// ─── Type Definitions ───────────────────────────────────────────────────────
interface UploadedFileEntry { fileName: string; }

interface RationalizedItem {
  'Asset ID': string; 'Item Type': string; Name: string;
  'Source Tool': string; 'Report Name': string; 'Table / Folder': string | null;
  DataSource: string | null; 'Data Type': string | null; 'Semantic Type': string | null;
  Description: string | null; Formula: string | null; 'Normalized Formula'?: string | null;
  'AI Verdict': string; 'Similarity Score': number; 'Top Match': string;
  Rationale: string; 'Top 3 Matches': string; 'Overlap Group ID': number;
  'AI Verdict Refined'?: string; 'Rationale Refined'?: string;
}

interface RationalizationResult {
  job_id: string;
  rationalized_catalog: RationalizedItem[];
  rationalized_overlaps_duplicates: RationalizedItem[];
  rationalized_verdict_summary: Array<{ 'Item Type': string; 'AI Verdict': string; Count: number }>;
}

interface Tier3Rec { rank: number; term_title: string; term_description?: string; confidence: number; rationale: string; }

interface EnrichmentResult {
  asset_id: string; asset_name: string; asset_type: string;
  term_title: string | null; term_id: number | null; confidence_score: number;
  linkage_type: string; matching_rationale: string; business_name: string | null;
  business_definition: string | null; description_enriched: boolean;
  purpose_statement?: string | null; metric_classification?: string | null;
  enriched_at?: string | null; model_id?: string | null;
  tier3_recommendations?: Tier3Rec[];
}

interface GlossaryTerm {
  id: number; title: string; description: string; deleted: boolean;
  template_id: number; ts_updated: string;
  custom_fields: Array<{ field_name: string; value: any }>;
}

// ─── Helpers ────────────────────────────────────────────────────────────────
const getToolName = (f: string) => {
  const n = f.toLowerCase();
  if (n.endsWith('.pbix')) return 'powerbi';
  if (n.endsWith('.twb') || n.endsWith('.twbx')) return 'tableau-workbook';
  return 'powerbi';
};

const readUploadedFiles = (): UploadedFileEntry[] => {
  try {
    const raw = localStorage.getItem('existingReports');
    const arr = raw ? JSON.parse(raw) : [];
    if (Array.isArray(arr) && arr.length) return arr.filter((e: any) => e?.fileName);
  } catch {}
  try {
    const raw = localStorage.getItem('powerbiPendingJob');
    const j = raw ? JSON.parse(raw) : null;
    const files = Array.isArray(j?.files)
      ? j.files.map((f: any) => ({ fileName: f?.file_name })).filter((f: any) => f.fileName)
      : [];
    if (files.length) return files;
  } catch {}
  const active = localStorage.getItem('activePowerBiReportFile');
  return active ? [{ fileName: active }] : [];
};

const unwrapReport = (r: any) => r?.result || r?.data || r?.report || r || {};

const uniqueBy = <T,>(items: T[], keyFn: (i: T) => string) => {
  const seen = new Set<string>();
  return items.filter(i => { const k = keyFn(i); if (seen.has(k)) return false; seen.add(k); return true; });
};

const buildConsolidatedModel = (reports: any[], selectedFiles: string[]) => {
  const models = reports.map(unwrapReport);
  const first = models[0] || {};
  return {
    schema_version: first.schema_version || '1.0',
    model_id: first.model_id || `gap-${Date.now()}`,
    name: selectedFiles.join(' + '),
    extracted_at: first.extracted_at || new Date().toISOString(),
    data_sources: uniqueBy(models.flatMap(m => Array.isArray(m.data_sources) ? m.data_sources : []), (i: any) => i.id || `${i.name}-${i.path}`),
    tables: uniqueBy(models.flatMap(m => Array.isArray(m.tables) ? m.tables : []), (i: any) => i.id || i.name),
    relationships: uniqueBy(models.flatMap(m => Array.isArray(m.relationships) ? m.relationships : []), (i: any) => i.id || `${i.left_table_id}-${i.left_column}-${i.right_table_id}-${i.right_column}`),
    calculations: uniqueBy(models.flatMap(m => Array.isArray(m.calculations) ? m.calculations : []), (i: any) => i.id || i.name),
    visualizations: uniqueBy(models.flatMap(m => Array.isArray(m.visualizations) ? m.visualizations : []), (i: any) => i.id || i.query_ref || `${i.page}-${i.visual_type}-${i.table}-${i.column}`),
  };
};

const statusTone = (s: string) => {
  const n = s.toLowerCase();
  if (n.includes('missing')) return { bg: '#FEF2F2', text: '#B91C1C', border: '#FECACA' };
  if (n.includes('conflict') || n.includes('mismatch')) return { bg: '#FFFBEB', text: '#B45309', border: '#FDE68A' };
  return { bg: '#F0FDF4', text: '#15803D', border: '#BBF7D0' };
};

const verdictColor = (v: string) => {
  const val = v.toLowerCase();
  if (val === 'merge') return { bg: '#EFF6FF', text: '#1D4ED8', border: '#BFDBFE' };
  if (val === 'retire') return { bg: '#FEF2F2', text: '#B91C1C', border: '#FECACA' };
  if (val === 'standardize') return { bg: '#FFFBEB', text: '#B45309', border: '#FDE68A' };
  if (val === 'keep') return { bg: '#ECFDF5', text: '#065F46', border: '#A7F3D0' };
  return { bg: T.bg, text: T.slate, border: T.border };
};

const linkageColor = (lt: string) => {
  const v = lt.toLowerCase();
  if (v === 'error') return { bg: '#FEF2F2', text: '#B91C1C', border: '#FECACA' };
  if (v === 'generated') return { bg: '#F5F3FF', text: '#6D28D9', border: '#DDD6FE' };
  if (v === 'matched') return { bg: '#ECFDF5', text: '#065F46', border: '#A7F3D0' };
  return { bg: T.bg, text: T.slate, border: T.border };
};

// ─── Status Badge ────────────────────────────────────────────────────────────
const StatusBadge = ({ status }: { status: JobStatus }) => {
  const cfg = {
    idle:    { icon: Minus,       color: T.textLight, bg: T.bg,        label: 'Idle' },
    running: { icon: Loader2,     color: T.amber,     bg: '#FFFBEB',   label: 'Running' },
    done:    { icon: CheckCircle2,color: T.green,     bg: '#ECFDF5',   label: 'Done' },
    error:   { icon: XSquare,     color: T.red,       bg: '#FEF2F2',   label: 'Error' },
  }[status];
  const Icon = cfg.icon;
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 8px', borderRadius: 20, background: cfg.bg, border: `1px solid ${cfg.color}22`, fontSize: 10, fontWeight: 700, color: cfg.color }}>
      <Icon size={10} className={status === 'running' ? 'animate-spin' : ''} />
      {cfg.label}
    </span>
  );
};

// ─── File Selector Dropdown ──────────────────────────────────────────────────
const FileSelector = ({ uploadedFiles, selectedFiles, onToggle, isLoading }: {
  uploadedFiles: UploadedFileEntry[]; selectedFiles: string[];
  onToggle: (name: string) => void; isLoading: boolean;
}) => {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ position: 'relative' }}>
      <button onClick={() => setOpen(o => !o)}
        style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 10px', background: T.white, border: `1px solid ${T.border}`, borderRadius: 6, fontSize: 11, fontWeight: 600, color: T.textMid, cursor: 'pointer', minWidth: 180 }}>
        <Database size={12} color={T.navy} />
        <span style={{ flex: 1, textAlign: 'left', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {selectedFiles.length === 0 ? 'Select reports…' : `${selectedFiles.length} report${selectedFiles.length > 1 ? 's' : ''} selected`}
        </span>
        <ChevronDown size={11} style={{ transform: open ? 'rotate(180deg)' : 'none', transition: '0.15s' }} />
      </button>
      {open && (
        <div style={{ position: 'absolute', top: 'calc(100% + 4px)', left: 0, zIndex: 200, background: T.white, border: `1px solid ${T.border}`, borderRadius: 8, boxShadow: '0 8px 24px rgba(0,0,0,0.10)', width: 240, maxHeight: 200, overflowY: 'auto' }}>
          {isLoading && <div style={{ padding: '10px 12px', fontSize: 11, color: T.textLight, display: 'flex', gap: 6 }}><Loader2 size={12} className="animate-spin" /> Loading…</div>}
          {!isLoading && uploadedFiles.length === 0 && <div style={{ padding: '10px 12px', fontSize: 11, color: T.textLight }}>No uploaded files found</div>}
          {uploadedFiles.map(entry => {
            const checked = selectedFiles.includes(entry.fileName);
            return (
              <button key={entry.fileName} onClick={() => onToggle(entry.fileName)}
                style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%', padding: '8px 12px', background: 'transparent', border: 'none', cursor: 'pointer', fontSize: 11, fontWeight: 500, color: T.text, textAlign: 'left' }}>
                <span style={{ display: 'grid', placeItems: 'center', width: 14, height: 14, borderRadius: 3, border: checked ? `2px solid ${T.navy}` : `2px solid ${T.border}`, background: checked ? T.navy : T.white, color: T.white, flexShrink: 0 }}>
                  {checked && <Check size={9} />}
                </span>
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{entry.fileName}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};

// ─── Pipeline Step Card ──────────────────────────────────────────────────────
const StepCard = ({ step, title, description, status, isActive, onClick, children }: {
  step: number; title: string; description: string;
  status: JobStatus; isActive: boolean; onClick: () => void; children?: React.ReactNode;
}) => (
  <div
    onClick={onClick}
    style={{
      flex: 1, minWidth: 0, background: T.white, border: `1.5px solid ${isActive ? T.navy : T.border}`,
      borderRadius: 10, padding: '14px 16px', cursor: 'pointer', position: 'relative',
      boxShadow: isActive ? `0 4px 16px rgba(0,33,71,0.10)` : '0 1px 3px rgba(0,0,0,0.04)',
      transition: 'all 0.2s',
    }}
  >
    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8, marginBottom: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ fontSize: 9, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.07em',
          background: isActive ? T.navy : T.bg, color: isActive ? T.white : T.textLight,
          padding: '2px 7px', borderRadius: 20, border: `1px solid ${isActive ? T.navy : T.border}` }}>
          STEP {step}
        </span>
      </div>
      <StatusBadge status={status} />
    </div>
    <p style={{ fontSize: 12, fontWeight: 700, color: T.text, margin: '0 0 2px' }}>{title}</p>
    <p style={{ fontSize: 10, color: T.textLight, margin: '0 0 10px', lineHeight: 1.4 }}>{description}</p>
    <div onClick={e => e.stopPropagation()}>{children}</div>
  </div>
);

// ─── Detail Drawers ──────────────────────────────────────────────────────────
const KpiDetailDrawer = ({ item, onClose }: { item: RationalizedItem | null; onClose: () => void }) => (
  <div className={`fixed inset-0 z-[9998] transition ${item ? 'pointer-events-auto' : 'pointer-events-none'}`}>
    <div className={`absolute inset-0 bg-slate-900/20 transition-opacity ${item ? 'opacity-100' : 'opacity-0'}`} onClick={onClose} />
    <aside className={`absolute right-0 top-0 h-full w-full max-w-xl overflow-y-auto border-l border-slate-200 bg-white shadow-2xl transition-transform duration-300 ${item ? 'translate-x-0' : 'translate-x-full'}`}>
      {item && (
        <div>
          <div className="sticky top-0 z-10 border-b border-slate-200 bg-white px-6 py-4">
            <div className="flex items-start justify-between gap-4">
              <div><p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">KPI Rationalization</p>
                <h2 className="mt-1 text-lg font-bold text-slate-900">{item.Name}</h2>
                <p className="text-xs text-slate-500">{item['Report Name'] || '—'}</p></div>
              <button onClick={onClose} className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-50"><X size={14} /></button>
            </div>
          </div>
          <div className="space-y-4 p-5">
            <div className="grid grid-cols-2 gap-3">
              {[['Item Type', item['Item Type']], ['Similarity Score', `${((item['Similarity Score'] || 0) * 100).toFixed(0)}%`], ['AI Verdict', item['AI Verdict Refined'] || item['AI Verdict']], ['Overlap Group', item['Overlap Group ID'] ?? '—'], ['Table / Folder', item['Table / Folder'] || '—'], ['Data Type', item['Data Type'] || '—']].map(([l, v]) => (
                <div key={l as string} className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                  <p className="text-[9px] font-semibold uppercase text-slate-400">{l}</p>
                  <p className="mt-0.5 text-sm font-semibold text-slate-800 break-words">{String(v)}</p>
                </div>
              ))}
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <p className="text-[10px] font-semibold uppercase text-slate-400 mb-2">Normalized Formula</p>
              <code className="block whitespace-pre-wrap rounded bg-slate-50 p-3 font-mono text-xs text-slate-700">{item['Normalized Formula'] || '—'}</code>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <p className="text-[10px] font-semibold uppercase text-slate-400 mb-2">Rationale Refined</p>
              <p className="text-sm leading-6 text-slate-700">{item['Rationale Refined'] || item.Rationale || '—'}</p>
            </div>
          </div>
        </div>
      )}
    </aside>
  </div>
);

const EnrichmentDetailDrawer = ({ item, onClose }: { item: EnrichmentResult | null; onClose: () => void }) => (
  <div className={`fixed inset-0 z-[9998] transition ${item ? 'pointer-events-auto' : 'pointer-events-none'}`}>
    <div className={`absolute inset-0 bg-slate-900/20 transition-opacity ${item ? 'opacity-100' : 'opacity-0'}`} onClick={onClose} />
    <aside className={`absolute right-0 top-0 h-full w-full max-w-xl overflow-y-auto border-l border-slate-200 bg-white shadow-2xl transition-transform duration-300 ${item ? 'translate-x-0' : 'translate-x-full'}`}>
      {item && (
        <div>
          <div className="sticky top-0 z-10 border-b border-slate-200 bg-white px-6 py-4">
            <div className="flex items-start justify-between gap-4">
              <div><p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Business Enrichment</p>
                <h2 className="mt-1 text-lg font-bold text-slate-900">{item.asset_name}</h2>
                <p className="text-xs text-slate-500">{item.business_name || item.term_title || '—'}</p></div>
              <button onClick={onClose} className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-50"><X size={14} /></button>
            </div>
          </div>
          <div className="space-y-4 p-5">
            <div className="grid grid-cols-2 gap-3">
              {[['Asset Type', item.asset_type], ['Linkage Type', item.linkage_type], ['Confidence', `${item.confidence_score}%`], ['Description Enriched', item.description_enriched ? 'Yes' : 'No'], ['Metric Classification', item.metric_classification || '—'], ['Term Title', item.term_title || '—']].map(([l, v]) => (
                <div key={l as string} className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                  <p className="text-[9px] font-semibold uppercase text-slate-400">{l}</p>
                  <p className="mt-0.5 text-sm font-semibold text-slate-800">{String(v)}</p>
                </div>
              ))}
            </div>
            {item.business_definition && <div className="rounded-lg border p-4"><p className="text-[10px] font-semibold uppercase text-slate-400 mb-2">Business Definition</p><p className="text-sm leading-6 text-slate-700">{item.business_definition}</p></div>}
            {item.matching_rationale && <div className="rounded-lg border p-4"><p className="text-[10px] font-semibold uppercase text-slate-400 mb-2">Matching Rationale</p><p className="text-sm leading-6 text-slate-700">{item.matching_rationale}</p></div>}
            {item.purpose_statement && <div className="rounded-lg border p-4"><p className="text-[10px] font-semibold uppercase text-slate-400 mb-2">Purpose Statement</p><p className="text-sm leading-6 text-slate-700">{item.purpose_statement}</p></div>}
            {(item.tier3_recommendations || []).length > 0 && (
              <div className="rounded-lg border p-4">
                <p className="text-[10px] font-semibold uppercase text-slate-400 mb-3">Tier 3 Recommendations</p>
                <div className="space-y-2">
                  {item.tier3_recommendations!.map(rec => (
                    <div key={rec.rank} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                      <div className="flex justify-between gap-2">
                        <p className="text-sm font-semibold text-slate-900">#{rec.rank} {rec.term_title}</p>
                        <span className="text-xs font-mono text-emerald-700">{rec.confidence}%</span>
                      </div>
                      <p className="mt-1 text-xs text-slate-500">{rec.rationale}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </aside>
  </div>
);

// ─── Main Component ──────────────────────────────────────────────────────────
export default function IntelligenceHub() {
  const { sideNavWidth } = useOutletContext<{ sideNavWidth: number }>();
  const dispatch = useDispatch();

  // Redux job selectors
  const gapJob   = useSelector(selectJob('gap-analysis'));
  const kpiJob   = useSelector(selectJob('kpi-rationalization'));
  const enrichJob = useSelector(selectJob('business-enrichment'));

  const isGapRunning    = gapJob?.status === 'running' || gapJob?.status === 'polling';
  const isKpiRunning    = kpiJob?.status === 'running' || kpiJob?.status === 'polling';
  const isEnrichRunning = enrichJob?.status === 'running' || enrichJob?.status === 'polling';

  // UI state
  const [topHeight, setTopHeight] = useState<number | 'auto'>('auto');

  // Files
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFileEntry[]>([]);
  const [reports, setReports] = useState<ReportListItem[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [isLoadingFiles, setIsLoadingFiles] = useState(false);

  // Gap Analysis
  const csvRef = useRef<HTMLInputElement>(null);
  const [targetFile, setTargetFile] = useState<File | null>(null);
  const [gapResult, setGapResult] = useState<any>(null);
  const [gapError, setGapError] = useState('');
  const [gapQuery, setGapQuery] = useState('');
  const [gapFilter, setGapFilter] = useState('all');
  const [isGapLocalRunning, setIsGapLocalRunning] = useState(false);
  const effectiveGapRunning = isGapLocalRunning || isGapRunning;

  // KPI Rationalization
  const [kpiResult, setKpiResult] = useState<RationalizationResult | null>(null);
  const [kpiJobId, setKpiJobId] = useState('');
  const [kpiError, setKpiError] = useState('');
  const [kpiQuery, setKpiQuery] = useState('');
  const [kpiVerdictFilter, setKpiVerdictFilter] = useState('all');
  const [selectedKpiItem, setSelectedKpiItem] = useState<RationalizedItem | null>(null);

  // Business Enrichment
  const [enrichResult, setEnrichResult] = useState<EnrichmentResult[]>([]);
  const [enrichError, setEnrichError] = useState('');
  const [enrichQuery, setEnrichQuery] = useState('');
  const [enrichFilter, setEnrichFilter] = useState<'all' | 'enriched' | 'not-enriched' | 'error'>('all');
  const [selectedEnrichItem, setSelectedEnrichItem] = useState<EnrichmentResult | null>(null);

  // Glossary
  const [glossaryId, setGlossaryId] = useState('2');
  const [glossaryLimit, setGlossaryLimit] = useState('10');
  const [glossaryTerms, setGlossaryTerms] = useState<GlossaryTerm[]>([]);
  const [selectedTerm, setSelectedTerm] = useState<GlossaryTerm | null>(null);
  const [termDescription, setTermDescription] = useState('');
  const [glossaryQuery, setGlossaryQuery] = useState('');
  const [isLoadingGlossary, setIsLoadingGlossary] = useState(false);
  const [isSavingTerm, setIsSavingTerm] = useState(false);

  // UI
  const [activeTab, setActiveTab] = useState<ActiveTab>('gap');
  const [activeStep, setActiveStep] = useState<number | null>(null);
  const [toast, setToast] = useState<{ type: 'success' | 'error' | 'info'; message: string } | null>(null);

  // Derived status
  const gapStatus: JobStatus    = effectiveGapRunning ? 'running' : gapResult ? 'done' : gapError ? 'error' : 'idle';
  const kpiStatus: JobStatus    = isKpiRunning ? 'running' : kpiResult ? 'done' : kpiError ? 'error' : 'idle';
  const enrichStatus: JobStatus = isEnrichRunning ? 'running' : enrichResult.length > 0 ? 'done' : enrichError ? 'error' : 'idle';
  const glossaryStatus: JobStatus = isLoadingGlossary ? 'running' : glossaryTerms.length > 0 ? 'done' : 'idle';

  // Toast dismiss
  useEffect(() => { if (!toast) return; const t = setTimeout(() => setToast(null), 3500); return () => clearTimeout(t); }, [toast]);
  const showToast = (type: 'success' | 'error' | 'info', message: string) => setToast({ type, message });

  // Load cached results on mount
  useEffect(() => {
    const activeFile = localStorage.getItem('activePowerBiReportFile') || '';
    if (activeFile) {
      const cachedGap = loadJobResult('gap-analysis', activeFile);
      if (cachedGap) setGapResult(cachedGap);

      const cachedKpi = loadJobResult('kpi-rationalization', activeFile);
      if (cachedKpi) { setKpiResult(cachedKpi); setKpiJobId(cachedKpi.job_id || ''); }

      const cachedEnrich = loadJobResult('business-enrichment', activeFile);
      if (cachedEnrich) setEnrichResult(Array.isArray(cachedEnrich) ? cachedEnrich : []);
    }
    refreshFiles();
  }, []);

  const refreshFiles = async () => {
    setIsLoadingFiles(true);
    const files = readUploadedFiles();
    setUploadedFiles(files);
    if (files.length && !selectedFiles.length) setSelectedFiles(files.map(f => f.fileName));
    const tools = [...new Set(files.map(f => getToolName(f.fileName)))];
    const groups = await Promise.all(tools.map(t => listPowerBiReports(t).catch(() => [])));
    setReports(groups.flat());
    setIsLoadingFiles(false);
  };

  const toggleFile = (name: string) =>
    setSelectedFiles(prev => prev.includes(name) ? prev.filter(f => f !== name) : [...prev, name]);

  // ── Step 1: Gap Analysis ───────────────────────────────────────────────────
  const runGapAnalysis = async () => {
    if (!targetFile) { showToast('error', 'Upload a target schema CSV first.'); return; }
    if (!selectedFiles.length) { showToast('error', 'Select at least one source report.'); return; }
    setIsGapLocalRunning(true); setGapError(''); setGapResult(null);
    const activeFile = localStorage.getItem('activePowerBiReportFile') || selectedFiles[0] || '';
    clearJobResult('gap-analysis', activeFile);
    dispatch(startJob({ type: 'gap-analysis', fileName: activeFile, estimatedTotalMs: 600000 }));
    try {
      dispatch(advanceStep({ type: 'gap-analysis', stepIndex: 0 }));
      dispatch(advanceStep({ type: 'gap-analysis', stepIndex: 1, statusMessage: 'Fetching source reports…' }));
      const sourceReports = await Promise.all(selectedFiles.map((fileName, idx) => {
        const meta = reports.find(r => r.file_name === fileName);
        return fetchPowerBiReport(fileName, meta?.tool_type || getToolName(fileName), { reportId: meta?.report_id });
      }));
      const consolidated = buildConsolidatedModel(sourceReports, selectedFiles);
      dispatch(addJobLog({ type: 'gap-analysis', message: `Consolidated ${sourceReports.length} reports` }));
      dispatch(advanceStep({ type: 'gap-analysis', stepIndex: 2, statusMessage: 'Preparing payload…' }));
      const formData = new FormData();
      formData.append('file', JSON.stringify(consolidated));
      formData.append('target_model', targetFile, targetFile.name);
      dispatch(advanceStep({ type: 'gap-analysis', stepIndex: 3, statusMessage: 'Running gap analysis API…' }));
      const res = await fetch(GAP_API_URL, { method: 'POST', headers: { accept: 'application/json' }, body: formData });
      if (!res.ok) throw new Error(await res.text() || `Gap analysis failed (${res.status})`);
      dispatch(advanceStep({ type: 'gap-analysis', stepIndex: 4, statusMessage: 'Processing results…' }));
      const data = await res.json();
      const final = { ...data, consolidated_payload: consolidated };
      setGapResult(final);
      saveJobResult('gap-analysis', activeFile, final);
      dispatch(completeJob({ type: 'gap-analysis', statusMessage: 'Gap analysis complete' }));
      setActiveTab('gap');
      showToast('success', `Gap analysis complete — ${(data.gap_analysis || []).length} mappings.`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      setGapError(msg); dispatch(failJob({ type: 'gap-analysis', errorMessage: msg })); showToast('error', msg);
    } finally { setIsGapLocalRunning(false); }
  };

  // ── Step 2: KPI Rationalization ────────────────────────────────────────────
  const runRationalization = async () => {
    if (!selectedFiles.length) { showToast('error', 'Select at least one file.'); return; }
    setKpiError(''); setKpiResult(null); setEnrichResult([]);
    const activeFile = localStorage.getItem('activePowerBiReportFile') || selectedFiles[0] || '';
    dispatch(startJob({ type: 'kpi-rationalization', fileName: activeFile, estimatedTotalMs: 600000 }));
    try {
      dispatch(advanceStep({ type: 'kpi-rationalization', stepIndex: 0 }));
      dispatch(advanceStep({ type: 'kpi-rationalization', stepIndex: 1, statusMessage: 'Fetching report data…' }));
      const reportsData = await Promise.all(selectedFiles.map(fileName => {
        const meta = reports.find(r => r.file_name === fileName);
        return fetchPowerBiReport(fileName, meta?.tool_type || getToolName(fileName), { reportId: meta?.report_id });
      }));
      dispatch(advanceStep({ type: 'kpi-rationalization', stepIndex: 2, statusMessage: 'Building payload…' }));
      dispatch(addJobLog({ type: 'kpi-rationalization', message: `Fetched ${reportsData.length} reports` }));
      const payload = reportsData.map(r => ({ content: r?.result || r?.data || r || {} }));
      dispatch(advanceStep({ type: 'kpi-rationalization', stepIndex: 3, statusMessage: 'Running rationalization API…' }));
      const res = await fetch(`${REPORTS_API}/rationalize`, { method: 'POST', headers: { 'Content-Type': 'application/json', accept: 'application/json' }, body: JSON.stringify(payload) });
      if (!res.ok) throw new Error(await res.text() || `Rationalization failed (${res.status})`);
      const data: RationalizationResult = await res.json();
      dispatch(advanceStep({ type: 'kpi-rationalization', stepIndex: 4, statusMessage: 'Processing catalog…' }));
      setKpiResult(data); setKpiJobId(data.job_id || '');
      saveJobResult('kpi-rationalization', activeFile, data);
      dispatch(completeJob({ type: 'kpi-rationalization', statusMessage: `Rationalization complete — ${data.rationalized_catalog?.length || 0} assets` }));
      setActiveTab('kpi');
      showToast('success', `KPI rationalization complete — ${data.rationalized_catalog?.length || 0} assets.`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      setKpiError(msg); dispatch(failJob({ type: 'kpi-rationalization', errorMessage: msg })); showToast('error', msg);
    }
  };

  // ── Step 3: Business Enrichment ────────────────────────────────────────────
  const runEnrichment = async () => {
    if (!kpiJobId) { showToast('error', 'Run KPI Rationalization first to get a job ID.'); return; }
    setEnrichError('');
    const activeFile = localStorage.getItem('activePowerBiReportFile') || selectedFiles[0] || '';
    dispatch(startJob({ type: 'business-enrichment', fileName: activeFile, estimatedTotalMs: 300000 }));
    try {
      dispatch(advanceStep({ type: 'business-enrichment', stepIndex: 0 }));
      dispatch(advanceStep({ type: 'business-enrichment', stepIndex: 1, statusMessage: 'Ingesting from Postgres…' }));
      const res = await fetch(`${ENRICHMENT_API}/assets/ingest-from-postgres?job_id=${kpiJobId}`, { method: 'POST', headers: { accept: 'application/json' }, body: '' });
      if (!res.ok) throw new Error(await res.text() || `Enrichment failed (${res.status})`);
      const data: EnrichmentResult[] = await res.json();
      const enrichData = Array.isArray(data) ? data : [];
      setEnrichResult(enrichData);
      saveJobResult('business-enrichment', activeFile, enrichData);
      dispatch(completeJob({ type: 'business-enrichment', statusMessage: `Enrichment complete — ${enrichData.length} assets` }));
      setActiveTab('enrich');
      showToast('success', `Enrichment complete — ${enrichData.length} assets ingested.`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      setEnrichError(msg); dispatch(failJob({ type: 'business-enrichment', errorMessage: msg })); showToast('error', msg);
    }
  };

  // ── Step 4: Glossary ───────────────────────────────────────────────────────
  const fetchGlossaryTerms = async () => {
    setIsLoadingGlossary(true);
    try {
      const res = await fetch(`${ENRICHMENT_API}/alation/terms?glossary_id=${glossaryId}&limit=${glossaryLimit}`, { headers: { accept: 'application/json' } });
      const data = await res.json();
      setGlossaryTerms(data?.terms || []);
      setSelectedTerm(null); setTermDescription('');
      setActiveTab('glossary');
      showToast('success', `Fetched ${data?.terms?.length || 0} glossary terms.`);
    } catch { showToast('error', 'Failed to fetch glossary terms.'); }
    finally { setIsLoadingGlossary(false); }
  };

  const updateTermDescription = async () => {
    if (!selectedTerm) return;
    setIsSavingTerm(true);
    try {
      const res = await fetch(`${ENRICHMENT_API}/curation/term-description`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json', accept: 'application/json' },
        body: JSON.stringify({ term_id: selectedTerm.id, description: termDescription, template_id: selectedTerm.template_id }),
      });
      const data = await res.json();
      showToast('success', data?.detail || 'Description updated.');
    } catch { showToast('error', 'Failed to update description.'); }
    finally { setIsSavingTerm(false); }
  };

  // Derived/filtered data
  const gapRows: any[] = Array.isArray(gapResult?.gap_analysis) ? gapResult.gap_analysis : [];
  const filteredGapRows = useMemo(() => {
    const q = gapQuery.trim().toLowerCase();
    return gapRows.filter(r => {
      if (gapFilter !== 'all' && (r['GAP_Status'] || '').toLowerCase() !== gapFilter) return false;
      if (q && !JSON.stringify(r).toLowerCase().includes(q)) return false;
      return true;
    });
  }, [gapRows, gapQuery, gapFilter]);

  const kpiCatalog = kpiResult?.rationalized_catalog || [];
  const kpiSummary = kpiResult?.rationalized_verdict_summary || [];
  const filteredKpi = useMemo(() => {
    const q = kpiQuery.trim().toLowerCase();
    return kpiCatalog.filter(r => {
      if (kpiVerdictFilter !== 'all' && (r['AI Verdict Refined'] || r['AI Verdict'])?.toLowerCase() !== kpiVerdictFilter) return false;
      if (q && !JSON.stringify(r).toLowerCase().includes(q)) return false;
      return true;
    });
  }, [kpiCatalog, kpiQuery, kpiVerdictFilter]);

  const filteredEnrich = useMemo(() => {
    const q = enrichQuery.trim().toLowerCase();
    return enrichResult.filter(r => {
      if (enrichFilter === 'enriched' && !r.description_enriched) return false;
      if (enrichFilter === 'not-enriched' && r.description_enriched) return false;
      if (enrichFilter === 'error' && r.linkage_type !== 'error') return false;
      if (q && !JSON.stringify(r).toLowerCase().includes(q)) return false;
      return true;
    });
  }, [enrichResult, enrichQuery, enrichFilter]);

  const filteredGlossary = useMemo(() => {
    const q = glossaryQuery.trim().toLowerCase();
    return q ? glossaryTerms.filter(t => t.title.toLowerCase().includes(q) || t.description.toLowerCase().includes(q)) : glossaryTerms;
  }, [glossaryTerms, glossaryQuery]);

  const tabs = [
    { id: 'kpi' as ActiveTab,     label: 'KPI Catalog',        count: kpiCatalog.length,  status: kpiStatus },
    { id: 'gap' as ActiveTab,     label: 'Gap Analysis',       count: gapRows.length,     status: gapStatus },
    { id: 'enrich' as ActiveTab,  label: 'Business Enrichment',count: enrichResult.length, status: enrichStatus },
    { id: 'glossary' as ActiveTab,label: 'Glossary',           count: glossaryTerms.length,status: glossaryStatus },
  ];

  return (
    <ContentCard heading={null} sideNavWidth={sideNavWidth} headerComponent={<FileWorkspaceHeader pageTitle="Intelligence Hub" />} noscroll noPadding={true}>
      <div style={{ display: 'flex', flexDirection: 'column', flex: 1, background: T.bg, overflow: 'hidden' }}>

        {/* ── Resizable Top Section ── */}
        <div style={{ height: topHeight, overflow: 'hidden', flexShrink: 0 }}>
          {/* ── Pipeline Steps Header ── */}
          <div style={{ background: T.white, padding: '16px 24px', flexShrink: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
              <div>
                <h1 style={{ fontSize: 18, fontWeight: 800, color: T.navy, margin: 0, letterSpacing: '-0.02em' }}>Intelligence Hub</h1>
                <p style={{ fontSize: 11, color: T.textLight, margin: '2px 0 0' }}>Gap Analysis · KPI Rationalization · Business Enrichment · Glossary — unified pipeline</p>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <FileSelector uploadedFiles={uploadedFiles} selectedFiles={selectedFiles} onToggle={toggleFile} isLoading={isLoadingFiles} />
                <button onClick={refreshFiles} style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '5px 10px', background: T.bg, border: `1px solid ${T.border}`, borderRadius: 6, fontSize: 11, fontWeight: 600, color: T.textMid, cursor: 'pointer' }}>
                  <RefreshCw size={11} /> Refresh
                </button>
              </div>
            </div>

            {/* 4 Step Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">

              {/* Step 1 — KPI Rationalization */}
              <StepCard step={1} title="KPI Rationalization" description="Analyze and deduplicate KPIs across reports" status={kpiStatus} isActive={activeStep === 1} onClick={() => setActiveStep(activeStep === 1 ? null : 1)}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <div style={{ fontSize: 9, color: T.textLight }}>{selectedFiles.length} report{selectedFiles.length !== 1 ? 's' : ''} selected</div>
                  <button onClick={runRationalization} disabled={isKpiRunning}
                    style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5, padding: '6px', background: isKpiRunning ? T.textLight : T.navy, border: 'none', borderRadius: 6, fontSize: 10, fontWeight: 700, color: T.white, cursor: isKpiRunning ? 'not-allowed' : 'pointer' }}>
                    {isKpiRunning ? <><Loader2 size={10} className="animate-spin" /> Running…</> : <><Sparkles size={10} /> Run Rationalization</>}
                  </button>
                  {kpiJob?.statusMessage && <p style={{ fontSize: 9, color: T.textLight, margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{kpiJob.statusMessage}</p>}
                </div>
              </StepCard>

              {/* Step 2 — Gap Analysis */}
              <StepCard step={2} title="Gap Analysis" description="Compare rationalized model against target schema CSV" status={gapStatus} isActive={activeStep === 2} onClick={() => setActiveStep(activeStep === 2 ? null : 2)}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <button onClick={() => csvRef.current?.click()}
                    style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '5px 9px', background: targetFile ? '#ECFDF5' : T.bg, border: `1px solid ${targetFile ? T.green : T.border}`, borderRadius: 6, fontSize: 10, fontWeight: 600, color: targetFile ? T.green : T.textMid, cursor: 'pointer' }}>
                    {targetFile ? <><CheckCircle2 size={11} /><span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 110 }}>{targetFile.name}</span></> : <><UploadCloud size={11} /> Upload target CSV</>}
                    {targetFile && <button onClick={e => { e.stopPropagation(); setTargetFile(null); }} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, marginLeft: 'auto' }}><X size={9} /></button>}
                  </button>
                  <input ref={csvRef} type="file" accept=".csv" style={{ display: 'none' }} onChange={e => setTargetFile(e.target.files?.[0] || null)} />
                  <button onClick={runGapAnalysis} disabled={effectiveGapRunning}
                    style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5, padding: '6px', background: effectiveGapRunning ? T.textLight : T.navy, border: 'none', borderRadius: 6, fontSize: 10, fontWeight: 700, color: T.white, cursor: effectiveGapRunning ? 'not-allowed' : 'pointer' }}>
                    {effectiveGapRunning ? <><Loader2 size={10} className="animate-spin" /> Running…</> : <><Play size={10} /> Run Gap Analysis</>}
                  </button>
                  {gapJob?.statusMessage && <p style={{ fontSize: 9, color: T.textLight, margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{gapJob.statusMessage}</p>}
                </div>
              </StepCard>

              {/* Step 3 — Business Enrichment */}
              <StepCard step={3} title="Business Enrichment" description="Enrich assets with business glossary linkages" status={enrichStatus} isActive={activeStep === 3} onClick={() => setActiveStep(activeStep === 3 ? null : 3)}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {kpiJobId && <p style={{ fontSize: 9, color: T.green, margin: 0, fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>Job ID: {kpiJobId}</p>}
                  {!kpiJobId && <p style={{ fontSize: 9, color: T.textLight, margin: 0 }}>Requires Step 1 job ID</p>}
                  <button onClick={runEnrichment} disabled={isEnrichRunning || !kpiJobId}
                    style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5, padding: '6px', background: (isEnrichRunning || !kpiJobId) ? T.textLight : T.navy, border: 'none', borderRadius: 6, fontSize: 10, fontWeight: 700, color: T.white, cursor: (isEnrichRunning || !kpiJobId) ? 'not-allowed' : 'pointer' }}>
                    {isEnrichRunning ? <><Loader2 size={10} className="animate-spin" /> Ingesting…</> : <><Zap size={10} /> Run Enrichment</>}
                  </button>
                  {enrichJob?.statusMessage && <p style={{ fontSize: 9, color: T.textLight, margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{enrichJob.statusMessage}</p>}
                </div>
              </StepCard>

              {/* Step 4 — Glossary */}
              <StepCard step={4} title="Glossary Explorer" description="Browse and curate Alation business glossary terms" status={glossaryStatus} isActive={activeStep === 4} onClick={() => setActiveStep(activeStep === 4 ? null : 4)}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <div style={{ display: 'flex', gap: 5 }}>
                    <input value={glossaryId} onChange={e => setGlossaryId(e.target.value)} placeholder="Glossary ID"
                      style={{ flex: 1, padding: '4px 6px', border: `1px solid ${T.border}`, borderRadius: 5, fontSize: 10, outline: 'none', background: T.bg }} />
                    <input value={glossaryLimit} onChange={e => setGlossaryLimit(e.target.value)} placeholder="Limit"
                      style={{ width: 46, padding: '4px 6px', border: `1px solid ${T.border}`, borderRadius: 5, fontSize: 10, outline: 'none', background: T.bg }} />
                  </div>
                  <button onClick={fetchGlossaryTerms} disabled={isLoadingGlossary}
                    style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5, padding: '6px', background: isLoadingGlossary ? T.textLight : T.navy, border: 'none', borderRadius: 6, fontSize: 10, fontWeight: 700, color: T.white, cursor: isLoadingGlossary ? 'not-allowed' : 'pointer' }}>
                    {isLoadingGlossary ? <><Loader2 size={10} className="animate-spin" /> Fetching…</> : <><BookOpen size={10} /> Fetch Glossary</>}
                  </button>
                </div>
              </StepCard>

            </div>
          </div>
        </div>

        {/* ── Drag Handle ── */}
        <div
          onMouseDown={(e) => {
            e.preventDefault();
            const startY = e.clientY;
            const prevEl = e.currentTarget.previousElementSibling as HTMLElement;
            const startHeight = prevEl?.clientHeight || 200;

            const handleMouseMove = (moveEvent: MouseEvent) => {
              const deltaY = moveEvent.clientY - startY;
              setTopHeight(Math.max(0, startHeight + deltaY));
            };

            const handleMouseUp = () => {
              document.removeEventListener('mousemove', handleMouseMove);
              document.removeEventListener('mouseup', handleMouseUp);
              document.body.style.userSelect = '';
            };

            document.addEventListener('mousemove', handleMouseMove);
            document.addEventListener('mouseup', handleMouseUp);
            document.body.style.userSelect = 'none';
          }}
          style={{
            height: 12,
            background: T.bg,
            borderBottom: `1px solid ${T.border}`,
            cursor: 'row-resize',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            transition: 'background 0.2s',
          }}
          onMouseEnter={e => e.currentTarget.style.background = '#e2e8f0'}
          onMouseLeave={e => e.currentTarget.style.background = T.bg}
        >
          <div style={{ width: 40, height: 4, background: '#cbd5e1', borderRadius: 2 }} />
        </div>

        {/* ── Results Tabs ── */}
        <div style={{ background: T.white, borderBottom: `1px solid ${T.border}`, padding: '0 24px', flexShrink: 0 }}>
          <div style={{ display: 'flex', gap: 0 }}>
            {tabs.map(tab => (
              <button key={tab.id} onClick={() => setActiveTab(tab.id)}
                style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '10px 16px', background: 'transparent', border: 'none', borderBottom: activeTab === tab.id ? `2px solid ${T.navy}` : '2px solid transparent', fontWeight: activeTab === tab.id ? 700 : 500, fontSize: 12, color: activeTab === tab.id ? T.navy : T.textMid, cursor: 'pointer', whiteSpace: 'nowrap', transition: 'all 0.15s' }}>
                {tab.label}
                {tab.count > 0 && <span style={{ fontSize: 10, fontWeight: 700, padding: '1px 6px', borderRadius: 20, background: activeTab === tab.id ? T.navy : T.bg, color: activeTab === tab.id ? T.white : T.textLight, border: `1px solid ${T.border}` }}>{tab.count}</span>}
                {tab.status === 'running' && <Loader2 size={11} className="animate-spin" style={{ color: T.amber }} />}
              </button>
            ))}
          </div>
        </div>

        {/* ── Results Content ── */}
        <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', padding: '20px 24px' }}>

          {/* GAP ANALYSIS PANEL */}
          {activeTab === 'gap' && (
            <div key={gapResult ? 'gap-result' : 'gap-empty'}>
              {gapError && <div style={{ display: 'flex', gap: 8, padding: '10px 14px', background: '#FEF2F2', border: '1px solid #FECACA', borderRadius: 8, color: '#B91C1C', fontSize: 12, marginBottom: 16 }}><AlertTriangle size={14} style={{ flexShrink: 0, marginTop: 1 }} />{gapError}</div>}
              {/* Show results FIRST — even if redux is still marking job as running */}
              {gapResult ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                    <div onClick={() => setGapFilter('all')} style={{ padding: '10px 14px', borderRadius: 8, background: T.bg, border: `2px solid ${gapFilter === 'all' ? T.text : T.border}`, minWidth: 100, flex: '1 1 80px', cursor: 'pointer', transition: 'all 0.2s', opacity: gapFilter === 'all' ? 1 : 0.6 }}>
                      <p style={{ fontSize: 9, fontWeight: 800, textTransform: 'uppercase', color: T.slate, marginBottom: 4 }}>Total Mappings</p>
                      <p style={{ fontSize: 24, fontWeight: 800, color: T.text, lineHeight: 1 }}>{gapRows.length}</p>
                    </div>
                    {Object.entries(gapResult.summary || {}).map(([label, _value]) => {
                      const tone = statusTone(label);
                      const filterVal = label.toLowerCase();
                      const count = gapRows.filter(r => (r['GAP_Status'] || '').toLowerCase() === filterVal).length;
                      return <div key={label} onClick={() => setGapFilter(filterVal)} style={{ padding: '10px 14px', borderRadius: 8, background: tone.bg, border: `2px solid ${gapFilter === filterVal ? tone.text : tone.border}`, minWidth: 100, flex: '1 1 80px', cursor: 'pointer', transition: 'all 0.2s', opacity: gapFilter === filterVal || gapFilter === 'all' ? 1 : 0.6 }}>
                        <p style={{ fontSize: 9, fontWeight: 800, textTransform: 'uppercase', color: tone.text, marginBottom: 4 }}>{label}</p>
                        <p style={{ fontSize: 24, fontWeight: 800, color: tone.text, lineHeight: 1 }}>{count}</p>
                      </div>;
                    })}
                  </div>
                  <div style={{ background: T.white, border: `1px solid ${T.border}`, borderRadius: 10, overflow: 'hidden' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 14px', borderBottom: `1px solid ${T.border}`, background: T.bg }}>
                      <span style={{ fontSize: 12, fontWeight: 700, color: T.text }}>Column Gap Analysis <span style={{ fontSize: 11, fontWeight: 400, color: T.textLight, marginLeft: 6 }}>{filteredGapRows.length} rows</span></span>
                      <div style={{ position: 'relative' }}>
                        <Search size={12} style={{ position: 'absolute', left: 8, top: '50%', transform: 'translateY(-50%)', color: T.textLight }} />
                        <input value={gapQuery} onChange={e => setGapQuery(e.target.value)} placeholder="Search…" style={{ paddingLeft: 26, paddingRight: 10, height: 30, borderRadius: 6, border: `1px solid ${T.border}`, background: T.white, fontSize: 11, outline: 'none', width: 180 }} />
                      </div>
                    </div>
                    <div style={{ overflowX: 'auto' }}>
                      <table style={{ width: '100%', minWidth: 900, fontSize: 11, borderCollapse: 'collapse' }}>
                        <thead>
                          <tr style={{ background: T.bg }}>
                            {['Source', 'Source Column', 'Target Column', 'Confidence', 'Status', 'Reasoning'].map(h => (
                              <th key={h} style={{ padding: '8px 12px', textAlign: 'left', fontSize: 9, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.06em', color: T.slate, borderBottom: `1px solid ${T.border}`, whiteSpace: 'nowrap' }}>{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {filteredGapRows.map((row, i) => {
                            const tone = statusTone(row['GAP_Status'] || '');
                            const conf = Number(row['Confidence Score'] || 0);
                            return (
                              <tr key={i} style={{ borderBottom: `1px solid ${T.border}` }} onMouseEnter={e => (e.currentTarget.style.background = T.bg)} onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
                                <td style={{ padding: '9px 12px' }}><p style={{ fontWeight: 600, color: T.text, margin: '0 0 2px' }}>{row['Source Table']}</p><span style={{ fontSize: 9, padding: '1px 5px', background: T.bg, borderRadius: 4, color: T.slate }}>{row['Source_Data_Type']}</span></td>
                                <td style={{ padding: '9px 12px', fontWeight: 500, color: T.textMid }}>{row['Source Column']}</td>
                                <td style={{ padding: '9px 12px', fontWeight: 700, color: T.green }}>{row['Mapped Target Column']}</td>
                                <td style={{ padding: '9px 12px' }}>
                                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                    <div style={{ height: 5, width: 56, borderRadius: 99, background: T.border, overflow: 'hidden' }}><div style={{ height: '100%', borderRadius: 99, background: conf >= 0.8 ? T.green : conf >= 0.5 ? T.amber : T.red, width: `${conf * 100}%` }} /></div>
                                    <span style={{ fontSize: 10, fontWeight: 700, fontFamily: 'monospace', color: T.textMid }}>{(conf * 100).toFixed(0)}%</span>
                                  </div>
                                </td>
                                <td style={{ padding: '9px 12px' }}><span style={{ display: 'inline-block', padding: '2px 8px', borderRadius: 99, fontSize: 9, fontWeight: 700, background: tone.bg, color: tone.text, border: `1px solid ${tone.border}` }}>{row['GAP_Status']}</span></td>
                                <td style={{ padding: '9px 12px', color: T.textMid, fontSize: 11, maxWidth: 280, lineHeight: 1.5 }}>{row['GAP_Reasoning'] || row.Reasoning}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              ) : effectiveGapRunning ? (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 300, gap: 12, color: T.navy }}>
                  <Loader2 size={32} className="animate-spin" style={{ opacity: 0.7 }} />
                  <p style={{ fontSize: 13, fontWeight: 700 }}>{gapJob?.statusMessage || 'Running gap analysis…'}</p>
                </div>
              ) : !gapError ? (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 300, gap: 10, color: T.textLight }}>
                  <FileSpreadsheet size={36} style={{ opacity: 0.3 }} />
                  <p style={{ fontWeight: 600, fontSize: 13 }}>No gap analysis results yet</p>
                  <p style={{ fontSize: 11 }}>Select reports, upload target CSV, then run Step 1</p>
                </div>
              ) : null}
            </div>
          )}

          {/* KPI CATALOG PANEL */}
          {activeTab === 'kpi' && (
            <div key={kpiResult ? 'kpi-result' : 'kpi-empty'} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {kpiError && <div style={{ display: 'flex', gap: 8, padding: '10px 14px', background: '#FEF2F2', border: '1px solid #FECACA', borderRadius: 8, color: '#B91C1C', fontSize: 12 }}><AlertTriangle size={14} style={{ flexShrink: 0 }} />{kpiError}</div>}

              {/* Show results FIRST — even if redux is still draining */}
              {kpiResult ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {/* Summary stat chips */}
                  {kpiCatalog.length > 0 && (
                    <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                      {[
                        { label: 'Total Assets', filter: 'all',         value: kpiCatalog.length, bg: '#f8fafc', border: T.border, text: T.text },
                        { label: 'Merge',        filter: 'merge',       value: kpiCatalog.filter(r => (r['AI Verdict Refined'] || r['AI Verdict'])?.toLowerCase() === 'merge').length,        bg: '#EFF6FF', border: '#BFDBFE', text: '#1D4ED8' },
                        { label: 'Retire',       filter: 'retire',      value: kpiCatalog.filter(r => (r['AI Verdict Refined'] || r['AI Verdict'])?.toLowerCase() === 'retire').length,       bg: '#FEF2F2', border: '#FECACA', text: '#B91C1C' },
                        { label: 'Standardize',  filter: 'standardize', value: kpiCatalog.filter(r => (r['AI Verdict Refined'] || r['AI Verdict'])?.toLowerCase() === 'standardize').length,  bg: '#FFFBEB', border: '#FDE68A', text: '#B45309' },
                        { label: 'Keep',         filter: 'keep',        value: kpiCatalog.filter(r => (r['AI Verdict Refined'] || r['AI Verdict'])?.toLowerCase() === 'keep').length,         bg: '#ECFDF5', border: '#A7F3D0', text: '#065F46' },
                      ].map(s => (
                        <div key={s.label} onClick={() => setKpiVerdictFilter(s.filter)} style={{ padding: '10px 14px', borderRadius: 8, background: s.bg, border: `2px solid ${kpiVerdictFilter === s.filter ? s.text : s.border}`, minWidth: 90, flex: '1 1 80px', cursor: 'pointer', transition: 'all 0.2s', opacity: kpiVerdictFilter === s.filter || kpiVerdictFilter === 'all' ? 1 : 0.6 }}>
                          <p style={{ fontSize: 9, fontWeight: 800, textTransform: 'uppercase', color: s.text, marginBottom: 4 }}>{s.label}</p>
                          <p style={{ fontSize: 24, fontWeight: 800, color: s.text, lineHeight: 1 }}>{s.value}</p>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Filters row */}
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                    <div style={{ position: 'relative', flex: 1, minWidth: 180 }}>
                      <Search size={12} style={{ position: 'absolute', left: 8, top: '50%', transform: 'translateY(-50%)', color: T.textLight }} />
                      <input value={kpiQuery} onChange={e => setKpiQuery(e.target.value)} placeholder="Search assets…" style={{ paddingLeft: 26, paddingRight: 10, height: 32, borderRadius: 6, border: `1px solid ${T.border}`, background: T.white, fontSize: 11, outline: 'none', width: '100%' }} />
                    </div>
                    {['all', 'merge', 'retire', 'standardize', 'keep'].map(f => (
                      <button key={f} onClick={() => setKpiVerdictFilter(f)}
                        style={{ padding: '4px 10px', borderRadius: 6, fontSize: 10, fontWeight: 700, textTransform: 'capitalize', border: `1px solid ${kpiVerdictFilter === f ? T.navy : T.border}`, background: kpiVerdictFilter === f ? T.navy : T.white, color: kpiVerdictFilter === f ? T.white : T.textMid, cursor: 'pointer' }}>
                        {f}
                      </button>
                    ))}
                    <span style={{ fontSize: 11, color: T.textLight, whiteSpace: 'nowrap', marginLeft: 'auto' }}>{filteredKpi.length} results</span>
                  </div>

                  {/* KPI Table — exact original columns */}
                  <div style={{ background: T.white, border: `1px solid ${T.border}`, borderRadius: 10, overflow: 'hidden' }}>
                    <div style={{ overflowX: 'auto', maxHeight: 560, overflowY: 'auto' }}>
                      <table style={{ width: '100%', minWidth: 1280, fontSize: 12, borderCollapse: 'collapse' }}>
                        <thead style={{ position: 'sticky', top: 0, zIndex: 1, background: T.bg }}>
                          <tr>
                            {['Item Type', 'Name', 'Report Name', 'Table / Folder', 'Normalized Formula', 'Similarity', 'AI Verdict Refined', 'Rationale Refined', 'Action'].map(h => (
                              <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontSize: 10, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.06em', color: T.slate, borderBottom: `1px solid ${T.border}`, whiteSpace: 'nowrap' }}>{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {filteredKpi.map((item, idx) => {
                            const verdict = item['AI Verdict Refined'] || item['AI Verdict'];
                            const vc = verdictColor(verdict);
                            const simPct = Math.round((item['Similarity Score'] || 0) * 100);
                            return (
                              <tr key={`${item['Asset ID']}-${idx}`}
                                style={{ borderBottom: `1px solid ${T.border}`, transition: 'background 0.1s' }}
                                onMouseEnter={e => (e.currentTarget.style.background = T.bg)}
                                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
                                <td style={{ padding: '10px 14px' }}>
                                  <span style={{ display: 'inline-flex', alignItems: 'center', padding: '2px 8px', borderRadius: 5, background: '#f1f5f9', fontSize: 11, fontWeight: 600, color: T.slate }}>{item['Item Type']}</span>
                                </td>
                                <td style={{ padding: '10px 14px' }}>
                                  <p style={{ fontWeight: 700, color: T.text, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', margin: 0 }}>{item.Name}</p>
                                </td>
                                <td style={{ padding: '10px 14px', color: T.textMid, fontSize: 11, maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item['Report Name'] || '—'}</td>
                                <td style={{ padding: '10px 14px', color: T.slate, fontSize: 11, maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item['Table / Folder'] || '—'}</td>
                                <td style={{ padding: '10px 14px' }}>
                                  <code style={{ display: 'block', maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', background: T.bg, borderRadius: 5, padding: '3px 7px', fontFamily: 'monospace', fontSize: 10, color: T.slate }}>{item['Normalized Formula'] || '—'}</code>
                                </td>
                                <td style={{ padding: '10px 14px' }}>
                                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                    <div style={{ height: 6, width: 80, borderRadius: 99, background: T.border, overflow: 'hidden' }}>
                                      <div style={{ height: '100%', borderRadius: 99, background: simPct >= 80 ? T.green : simPct >= 50 ? T.amber : T.red, width: `${simPct}%` }} />
                                    </div>
                                    <span style={{ fontSize: 11, fontFamily: 'monospace', fontWeight: 600, color: T.textMid }}>{simPct}%</span>
                                  </div>
                                </td>
                                <td style={{ padding: '10px 14px' }}>
                                  {verdict && (
                                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '3px 10px', borderRadius: 99, fontSize: 10, fontWeight: 700, background: vc.bg, color: vc.text, border: `1px solid ${vc.border}` }}>
                                      <span style={{ width: 6, height: 6, borderRadius: '50%', background: vc.text, display: 'inline-block' }} />
                                      {verdict}
                                    </span>
                                  )}
                                </td>
                                <td style={{ padding: '10px 14px', fontSize: 11, color: T.textMid, maxWidth: 320 }}>
                                  <p style={{ margin: 0, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' as any, overflow: 'hidden' }}>{item['Rationale Refined'] || '—'}</p>
                                </td>
                                <td style={{ padding: '10px 14px' }}>
                                  <button onClick={() => setSelectedKpiItem(item)}
                                    style={{ padding: '4px 10px', borderRadius: 6, border: `1px solid ${T.border}`, background: T.white, fontSize: 11, fontWeight: 600, color: T.textMid, cursor: 'pointer' }}>
                                    View More
                                  </button>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              ) : isKpiRunning ? (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 300, gap: 12, color: T.navy }}>
                  <Loader2 size={32} className="animate-spin" style={{ opacity: 0.7 }} />
                  <p style={{ fontSize: 13, fontWeight: 700 }}>{kpiJob?.statusMessage || 'Running KPI rationalization…'}</p>
                </div>
              ) : !kpiError ? (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 300, gap: 10, color: T.textLight }}>
                  <Sparkles size={36} style={{ opacity: 0.3 }} />
                  <p style={{ fontWeight: 600, fontSize: 13 }}>No KPI rationalization results yet</p>
                  <p style={{ fontSize: 11 }}>Select reports and run Step 2</p>
                </div>
              ) : null}
            </div>
          )}

          {/* ENRICHMENT PANEL */}
          {activeTab === 'enrich' && (
            <div key={enrichResult.length > 0 ? 'enrich-result' : 'enrich-empty'} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {enrichError && <div style={{ display: 'flex', gap: 8, padding: '10px 14px', background: '#FEF2F2', border: '1px solid #FECACA', borderRadius: 8, color: '#B91C1C', fontSize: 12 }}><AlertTriangle size={14} style={{ flexShrink: 0 }} />{enrichError}</div>}

              {/* Show results FIRST — even if redux is still draining */}
              {enrichResult.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {/* Stats */}
                  <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                    {[
                      { label: 'Total Assets', filter: 'all',          value: enrichResult.length,                                          bg: '#f8fafc', border: T.border,    text: T.text },
                      { label: 'Enriched',     filter: 'enriched',     value: enrichResult.filter(r => r.description_enriched).length,      bg: '#ECFDF5', border: '#A7F3D0',   text: '#065F46' },
                      { label: 'Not Enriched', filter: 'not-enriched', value: enrichResult.filter(r => !r.description_enriched).length,     bg: '#EFF6FF', border: '#BFDBFE',   text: '#1D4ED8' },
                      { label: 'Errors',       filter: 'error',        value: enrichResult.filter(r => r.linkage_type === 'error').length,  bg: '#FEF2F2', border: '#FECACA',   text: '#B91C1C' },
                    ].map(s => (
                      <div key={s.label} onClick={() => setEnrichFilter(s.filter as any)} style={{ padding: '10px 14px', borderRadius: 8, background: s.bg, border: `2px solid ${enrichFilter === s.filter ? s.text : s.border}`, minWidth: 90, flex: '1 1 80px', cursor: 'pointer', transition: 'all 0.2s', opacity: enrichFilter === s.filter || enrichFilter === 'all' ? 1 : 0.6 }}>
                        <p style={{ fontSize: 9, fontWeight: 800, textTransform: 'uppercase', color: s.text, marginBottom: 4 }}>{s.label}</p>
                        <p style={{ fontSize: 24, fontWeight: 800, color: s.text, lineHeight: 1 }}>{s.value}</p>
                      </div>
                    ))}
                  </div>

                  {/* Filters */}
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                    <div style={{ position: 'relative', flex: 1, minWidth: 180 }}>
                      <Search size={12} style={{ position: 'absolute', left: 8, top: '50%', transform: 'translateY(-50%)', color: T.textLight }} />
                      <input value={enrichQuery} onChange={e => setEnrichQuery(e.target.value)} placeholder="Search enriched assets…" style={{ paddingLeft: 26, paddingRight: 10, height: 32, borderRadius: 6, border: `1px solid ${T.border}`, background: T.white, fontSize: 11, outline: 'none', width: '100%' }} />
                    </div>
                    {(['all', 'enriched', 'not-enriched', 'error'] as const).map(f => (
                      <button key={f} onClick={() => setEnrichFilter(f)}
                        style={{ padding: '4px 10px', borderRadius: 6, fontSize: 10, fontWeight: 700, textTransform: 'capitalize', border: `1px solid ${enrichFilter === f ? T.navy : T.border}`, background: enrichFilter === f ? T.navy : T.white, color: enrichFilter === f ? T.white : T.textMid, cursor: 'pointer' }}>
                        {f.replace('-', ' ')}
                      </button>
                    ))}
                    <span style={{ fontSize: 11, color: T.textLight, marginLeft: 'auto', whiteSpace: 'nowrap' }}>{filteredEnrich.length} results</span>
                  </div>

                  {/* Enrichment Table — exact original columns */}
                  <div style={{ background: T.white, border: `1px solid ${T.border}`, borderRadius: 10, overflow: 'hidden' }}>
                    <div style={{ overflowX: 'auto', maxHeight: 560, overflowY: 'auto' }}>
                      <table style={{ width: '100%', minWidth: 1100, fontSize: 12, borderCollapse: 'collapse' }}>
                        <thead style={{ position: 'sticky', top: 0, zIndex: 1, background: T.bg }}>
                          <tr>
                            {['Asset', 'Type', 'Business Name', 'Term', 'Classification', 'Confidence', 'Linkage', 'Enriched', 'Action'].map(h => (
                              <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontSize: 10, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.06em', color: T.slate, borderBottom: `1px solid ${T.border}`, whiteSpace: 'nowrap' }}>{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {filteredEnrich.map((item, idx) => {
                            const conf = Math.min(100, Math.max(0, Number(item.confidence_score || 0)));
                            const confColor = conf >= 80 ? '#10B981' : conf >= 50 ? '#F59E0B' : '#EF4444';
                            const confText = conf >= 80 ? '#065F46' : conf >= 50 ? '#B45309' : '#B91C1C';
                            const lc = linkageColor(item.linkage_type);
                            return (
                              <tr key={`${item.asset_id}-${idx}`}
                                style={{ borderBottom: `1px solid ${T.border}`, transition: 'background 0.1s' }}
                                onMouseEnter={e => (e.currentTarget.style.background = T.bg)}
                                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
                                <td style={{ padding: '10px 14px' }}>
                                  <p style={{ fontWeight: 700, color: T.text, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', margin: '0 0 2px' }}>{item.asset_name}</p>
                                  <code style={{ fontSize: 10, color: T.textLight, fontFamily: 'monospace' }}>{item.asset_id?.slice(0, 28)}</code>
                                </td>
                                <td style={{ padding: '10px 14px' }}>
                                  <span style={{ display: 'inline-block', background: '#f1f5f9', borderRadius: 5, padding: '2px 8px', fontSize: 11, fontWeight: 600, color: T.slate }}>{item.asset_type || '—'}</span>
                                </td>
                                <td style={{ padding: '10px 14px', color: T.textMid, maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.business_name || '—'}</td>
                                <td style={{ padding: '10px 14px' }}>
                                  <p style={{ margin: '0 0 2px', color: T.textMid, maxWidth: 170, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.term_title || '—'}</p>
                                  <p style={{ margin: 0, fontSize: 10, color: T.textLight }}>Term ID: {item.term_id ?? '—'}</p>
                                </td>
                                <td style={{ padding: '10px 14px' }}>
                                  <span style={{ border: `1px solid ${T.border}`, borderRadius: 5, padding: '2px 8px', fontSize: 11, fontWeight: 500, color: T.slate }}>{item.metric_classification || '—'}</span>
                                </td>
                                <td style={{ padding: '10px 14px' }}>
                                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                    <div style={{ height: 6, width: 80, borderRadius: 99, background: T.border, overflow: 'hidden' }}>
                                      <div style={{ height: '100%', borderRadius: 99, background: confColor, width: `${conf}%` }} />
                                    </div>
                                    <span style={{ fontSize: 11, fontFamily: 'monospace', fontWeight: 600, color: confText }}>{conf.toFixed(0)}%</span>
                                  </div>
                                </td>
                                <td style={{ padding: '10px 14px' }}>
                                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 10px', borderRadius: 99, fontSize: 10, fontWeight: 700, background: lc.bg, color: lc.text, border: `1px solid ${lc.border}`, textTransform: 'capitalize' }}>{item.linkage_type || '—'}</span>
                                </td>
                                <td style={{ padding: '10px 14px', textAlign: 'center' }}>
                                  {item.description_enriched
                                    ? <CheckCircle2 size={16} style={{ color: '#059669' }} />
                                    : <X size={16} style={{ color: T.border }} />}
                                </td>
                                <td style={{ padding: '10px 14px' }}>
                                  <button onClick={() => setSelectedEnrichItem(item)}
                                    style={{ padding: '4px 10px', borderRadius: 6, border: `1px solid ${T.border}`, background: T.white, fontSize: 11, fontWeight: 600, color: T.textMid, cursor: 'pointer' }}>
                                    View More
                                  </button>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              ) : isEnrichRunning ? (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 300, gap: 12, color: T.navy }}>
                  <Loader2 size={32} className="animate-spin" style={{ opacity: 0.7 }} />
                  <p style={{ fontSize: 13, fontWeight: 700 }}>{enrichJob?.statusMessage || 'Running business enrichment…'}</p>
                </div>
              ) : !enrichError ? (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 300, gap: 10, color: T.textLight }}>
                  <Zap size={36} style={{ opacity: 0.3 }} />
                  <p style={{ fontWeight: 600, fontSize: 13 }}>No enrichment data yet</p>
                  <p style={{ fontSize: 11 }}>Complete Step 2, then run Step 3</p>
                </div>
              ) : null}
            </div>
          )}

          {/* GLOSSARY PANEL */}
          {activeTab === 'glossary' && (
            <div style={{ display: 'flex', gap: 16 }}>
              {/* Term list */}
              <div style={{ flex: 1, minWidth: 0 }}>
                {glossaryTerms.length === 0 && !isLoadingGlossary && (
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 300, gap: 10, color: T.textLight }}>
                    <BookOpen size={36} style={{ opacity: 0.3 }} />
                    <p style={{ fontWeight: 600, fontSize: 13 }}>No glossary terms loaded</p>
                    <p style={{ fontSize: 11 }}>Set Glossary ID and run Step 4</p>
                  </div>
                )}
                {isLoadingGlossary && (
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 300, gap: 12, color: T.navy }}>
                    <Loader2 size={32} className="animate-spin" style={{ opacity: 0.7 }} />
                    <p style={{ fontSize: 13, fontWeight: 700 }}>Fetching glossary terms…</p>
                  </div>
                )}
                {glossaryTerms.length > 0 && (
                  <div>
                    <div style={{ marginBottom: 12, position: 'relative' }}>
                      <Search size={12} style={{ position: 'absolute', left: 8, top: '50%', transform: 'translateY(-50%)', color: T.textLight }} />
                      <input value={glossaryQuery} onChange={e => setGlossaryQuery(e.target.value)} placeholder="Search terms…" style={{ paddingLeft: 26, paddingRight: 10, height: 32, borderRadius: 6, border: `1px solid ${T.border}`, background: T.white, fontSize: 11, outline: 'none', width: '100%' }} />
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {filteredGlossary.map(term => (
                        <button key={term.id} onClick={() => { setSelectedTerm(term); setTermDescription(term.description || ''); }}
                          style={{ background: selectedTerm?.id === term.id ? '#EFF6FF' : T.white, border: `1px solid ${selectedTerm?.id === term.id ? '#3B82F6' : T.border}`, borderRadius: 8, padding: '10px 12px', textAlign: 'left', cursor: 'pointer', width: '100%' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8, marginBottom: 3 }}>
                            <span style={{ fontSize: 12, fontWeight: 700, color: T.text }}>{term.title}</span>
                            <span style={{ fontSize: 9, fontFamily: 'monospace', color: T.textLight, flexShrink: 0 }}>#{term.id}</span>
                          </div>
                          <p style={{ fontSize: 10, color: T.textMid, margin: 0, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' as any, lineHeight: 1.5 }}>{term.description || '—'}</p>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Term editor */}
              {selectedTerm && (
                <div style={{ width: 360, flexShrink: 0, background: T.white, border: `1px solid ${T.border}`, borderRadius: 10, padding: 16, display: 'flex', flexDirection: 'column', gap: 12, alignSelf: 'flex-start', position: 'sticky', top: 0 }}>
                  <div>
                    <p style={{ fontSize: 9, fontWeight: 800, textTransform: 'uppercase', color: T.textLight, marginBottom: 4 }}>Editing Term</p>
                    <p style={{ fontSize: 14, fontWeight: 700, color: T.text, margin: '0 0 2px' }}>{selectedTerm.title}</p>
                    <p style={{ fontSize: 10, color: T.textLight, fontFamily: 'monospace' }}>ID: {selectedTerm.id} · Template: {selectedTerm.template_id}</p>
                  </div>
                  <div>
                    <p style={{ fontSize: 10, fontWeight: 700, color: T.textMid, marginBottom: 5 }}>Description</p>
                    <textarea value={termDescription} onChange={e => setTermDescription(e.target.value)} rows={6}
                      style={{ width: '100%', padding: '8px 10px', border: `1px solid ${T.border}`, borderRadius: 6, fontSize: 12, color: T.text, outline: 'none', resize: 'vertical', lineHeight: 1.6, boxSizing: 'border-box' }} />
                  </div>
                  <button onClick={updateTermDescription} disabled={isSavingTerm}
                    style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, padding: '8px', background: isSavingTerm ? T.textLight : T.navy, border: 'none', borderRadius: 6, fontSize: 12, fontWeight: 700, color: T.white, cursor: isSavingTerm ? 'not-allowed' : 'pointer' }}>
                    {isSavingTerm ? <><Loader2 size={12} className="animate-spin" /> Saving…</> : <><Save size={12} /> Save Description</>}
                  </button>
                  {selectedTerm.custom_fields?.length > 0 && (
                    <div>
                      <p style={{ fontSize: 10, fontWeight: 700, color: T.textMid, marginBottom: 6 }}>Custom Fields</p>
                      {selectedTerm.custom_fields.map(f => (
                        <div key={f.field_name} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: `1px solid ${T.border}`, fontSize: 10 }}>
                          <span style={{ color: T.textLight }}>{f.field_name}</span>
                          <span style={{ color: T.text, fontWeight: 600 }}>{String(f.value || '—')}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

        </div>
      </div>

      {/* Detail Drawers */}
      <KpiDetailDrawer item={selectedKpiItem} onClose={() => setSelectedKpiItem(null)} />
      <EnrichmentDetailDrawer item={selectedEnrichItem} onClose={() => setSelectedEnrichItem(null)} />

      {/* Toast */}
      {toast && (
        <div style={{ position: 'fixed', bottom: 24, right: 24, zIndex: 9999, padding: '12px 16px', borderRadius: 8, boxShadow: '0 8px 24px rgba(0,0,0,0.12)', display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, fontWeight: 600, maxWidth: 360,
          background: toast.type === 'success' ? '#ECFDF5' : toast.type === 'error' ? '#FEF2F2' : '#EFF6FF',
          color: toast.type === 'success' ? T.green : toast.type === 'error' ? T.red : T.navy,
          border: `1px solid ${toast.type === 'success' ? '#A7F3D0' : toast.type === 'error' ? '#FECACA' : '#BFDBFE'}` }}>
          {toast.type === 'success' ? <CheckCircle2 size={14} /> : toast.type === 'error' ? <AlertTriangle size={14} /> : <Info size={14} />}
          {toast.message}
          <button onClick={() => setToast(null)} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: 'inherit', opacity: 0.6 }}><X size={13} /></button>
        </div>
      )}
    </ContentCard>
  );
}
