import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { useNavigate } from 'react-router-dom';
import ContentCard from '../../core/CardContent/CardContent.tsx';
import FileWorkspaceHeader from '../../core/FileWorkspaceHeader.tsx';
import {
  fetchPowerBiReport,
  listPowerBiReports,
  ReportListItem,
} from '../../services/powerbiReports.ts';
import { useDispatch, useSelector } from 'react-redux';
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Database,
  FileSearch,
  Layers,
  Loader2,
  RefreshCw,
  Save,
  Search,
  Shield,
  Sparkles,
  Tag,
  TrendingUp,
  User,
  X,
  Zap,
  Hash,
  Link2,
  BarChart2,
  Info,
  ListOrdered,
} from 'lucide-react';
import {
  startJob, advanceStep, updateJobProgress, addJobLog,
  completeJob, failJob, saveJobResult, loadJobResult, clearJobResult,
  selectJob,
} from '../../utils/jobTrackerSlice.ts';

// ─── Constants ────────────────────────────────────────────────────────────────
const REPORTS_API = 'http://20.72.80.42:8001';
const ENRICHMENT_API = 'http://20.72.80.42:8002';

// ─── Helpers ──────────────────────────────────────────────────────────────────
const getToolName = (fileName: string) => {
  const n = String(fileName || '').toLowerCase();
  if (n.endsWith('.pbix')) return 'powerbi';
  if (n.endsWith('.twb') || n.endsWith('.twbx')) return 'tableau-workbook';
  return 'powerbi';
};

const readUploadedFiles = () => {
  try {
    const raw = localStorage.getItem('existingReports');
    const existing = raw ? JSON.parse(raw) : [];
    if (Array.isArray(existing) && existing.length > 0)
      return existing.filter((e: any) => e?.fileName);
  } catch {}
  try {
    const raw = localStorage.getItem('powerbiPendingJob');
    const job = raw ? JSON.parse(raw) : null;
    const files = Array.isArray(job?.files)
      ? job.files.map((f: any) => ({ fileName: f?.file_name })).filter((f: any) => f.fileName)
      : [];
    if (files.length) return files;
  } catch {}
  const active = localStorage.getItem('activePowerBiReportFile');
  return active ? [{ fileName: active }] : [];
};

const stripHtml = (html: string) => html.replace(/<[^>]+>/g, '');

const verdictColor = (v: string) => {
  const val = String(v || '').toLowerCase();
  if (val === 'merge') return 'bg-blue-50 text-blue-700 border-blue-200';
  if (val === 'retire') return 'bg-red-50 text-red-700 border-red-200';
  if (val === 'standardize') return 'bg-amber-50 text-amber-700 border-amber-200';
  if (val === 'keep') return 'bg-emerald-50 text-emerald-700 border-emerald-200';
  return 'bg-slate-50 text-slate-600 border-slate-200';
};

const verdictDot = (v: string) => {
  const val = String(v || '').toLowerCase();
  if (val === 'merge') return 'bg-blue-500';
  if (val === 'retire') return 'bg-red-500';
  if (val === 'standardize') return 'bg-amber-500';
  if (val === 'keep') return 'bg-emerald-500';
  return 'bg-slate-400';
};

const linkageColor = (lt: string) => {
  const v = String(lt || '').toLowerCase();
  if (v === 'error') return 'bg-red-50 text-red-700 border-red-100';
  if (v === 'generated') return 'bg-purple-50 text-purple-700 border-purple-200';
  if (v === 'matched') return 'bg-emerald-50 text-emerald-700 border-emerald-100';
  return 'bg-slate-50 text-slate-600 border-slate-200';
};

const formatEnrichedAt = (value?: string | null) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
};

// ─── Types ────────────────────────────────────────────────────────────────────
interface UploadedFileEntry { fileName: string; }

interface RationalizedItem {
  'Asset ID': string;
  'Item Type': string;
  Name: string;
  'Source Tool': string;
  'Report Name': string;
  'Table / Folder': string | null;
  DataSource: string | null;
  'Data Type': string | null;
  'Semantic Type': string | null;
  Description: string | null;
  Formula: string | null;
  'Normalized Formula'?: string | null;
  'AI Verdict': string;
  'Similarity Score': number;
  'Top Match': string;
  Rationale: string;
  'Top 3 Matches': string;
  'Overlap Group ID': number;
  'AI Verdict Refined'?: string;
  'Rationale Refined'?: string;
}

interface RationalizationResult {
  job_id: string;
  rationalized_catalog: RationalizedItem[];
  rationalized_overlaps_duplicates: RationalizedItem[];
  rationalized_verdict_summary: Array<{ 'Item Type': string; 'AI Verdict': string; Count: number }>;
}

interface Tier3Rec {
  rank: number;
  term_title: string;
  term_description?: string;
  confidence: number;
  rationale: string;
}

interface EnrichmentResult {
  asset_id: string;
  asset_name: string;
  asset_type: string;
  term_title: string | null;
  term_id: number | null;
  confidence_score: number;
  linkage_type: string;
  matching_rationale: string;
  business_name: string | null;
  business_definition: string | null;
  description_enriched: boolean;
  purpose_statement?: string | null;
  metric_classification?: string | null;
  enriched_at?: string | null;
  model_id?: string | null;
  tier3_recommendations?: Tier3Rec[];
}

interface GlossaryTerm {
  id: number;
  title: string;
  description: string;
  deleted: boolean;
  template_id: number;
  ts_updated: string;
  custom_fields: Array<{ field_name: string; value: any }>;
}

type ActiveTab = 'rationalize' | 'enrich' | 'glossary';
type WorkflowStep = 'idle' | 'loading-files' | 'rationalizing' | 'done-rationalize' | 'ingesting' | 'done-enrich' | 'error';

// ─── Enrichment Card ──────────────────────────────────────────────────────────
function EnrichmentCard({ item }: { item: EnrichmentResult }) {
  const [expanded, setExpanded] = useState(false);

  const confPct = Math.min(100, Math.max(0, item.confidence_score));
  const isError = item.linkage_type === 'error';

  // Parse a short readable ID from the full asset_id
  const shortId = (() => {
    const parts = String(item.asset_id || '').split('$');
    return parts[parts.length - 1] || item.asset_id;
  })();

  return (
    <div className={`rounded-2xl border bg-white overflow-hidden transition-all ${
      expanded ? 'border-red-200 shadow-sm' : 'border-slate-200 hover:border-slate-300'
    }`}>
      {/* ── Primary Row ── */}
      <div className="px-5 py-4">
        <div className="flex items-start gap-4">
          {/* Left: identity */}
          <div className="flex-1 min-w-0 space-y-2">
            {/* Name + type + linkage */}
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-semibold text-slate-900 truncate">{item.asset_name}</span>
              <span className="inline-flex items-center rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600 capitalize">
                {item.asset_type}
              </span>
              <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold capitalize ${linkageColor(item.linkage_type)}`}>
                <span className={`h-1.5 w-1.5 rounded-full ${isError ? 'bg-red-500' : item.linkage_type === 'generated' ? 'bg-purple-500' : 'bg-emerald-500'}`} />
                {item.linkage_type}
              </span>
            </div>

            {/* Term matched */}
            <div className="flex items-center gap-1.5 text-xs text-slate-600">
              <Tag size={11} className="text-slate-400 shrink-0" />
              <span className="text-slate-400">Matched term:</span>
              <span className="font-medium text-slate-800">{item.term_title || '—'}</span>
            </div>

            {/* ID chip */}
            <div className="flex items-center gap-1.5">
              <Hash size={11} className="text-slate-300 shrink-0" />
              <span className="font-mono text-[10px] text-slate-400 truncate max-w-[360px]">{shortId}</span>
            </div>
          </div>

          {/* Right: confidence + enriched status */}
          <div className="flex flex-col items-end gap-2 shrink-0">
            {/* Confidence */}
            <div className="flex items-center gap-2">
              <div className="h-1.5 w-20 rounded-full bg-slate-100 overflow-hidden">
                <div
                  className={`h-full rounded-full ${confPct >= 70 ? 'bg-gradient-to-r from-emerald-400 to-emerald-600' : 'bg-gradient-to-r from-amber-400 to-amber-600'}`}
                  style={{ width: `${confPct}%` }}
                />
              </div>
              <span className="text-xs font-mono text-slate-500 w-8 text-right">{confPct.toFixed(0)}%</span>
            </div>

            {/* Enriched chip */}
            <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-semibold border ${
              item.description_enriched
                ? 'bg-emerald-50 text-emerald-700 border-emerald-100'
                : 'bg-slate-50 text-slate-500 border-slate-200'
            }`}>
              {item.description_enriched
                ? <><CheckCircle2 size={11} /> Enriched</>
                : <><X size={11} /> Not enriched</>}
            </span>

            {/* Expand toggle */}
            <button
              onClick={() => setExpanded((p) => !p)}
              className="flex items-center gap-1 text-[11px] font-semibold text-slate-500 hover:text-red-700 transition-colors"
            >
              {expanded ? <><ChevronUp size={13} /> Hide details</> : <><ChevronDown size={13} /> View more</>}
            </button>
          </div>
        </div>
      </div>

      {/* ── Expanded Details ── */}
      {expanded && (
        <div className="border-t border-slate-100 bg-slate-50 px-5 py-4 space-y-4">

          {/* Detail grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Matching Rationale */}
            {item.matching_rationale && (
              <div className="space-y-1">
                <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">Matching Rationale</p>
                <p className="text-xs text-slate-700 leading-relaxed">{item.matching_rationale}</p>
              </div>
            )}

            {/* Business Definition */}
            {item.business_definition && (
              <div className="space-y-1">
                <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">Business Definition</p>
                <p className="text-xs text-slate-700 leading-relaxed">{item.business_definition}</p>
              </div>
            )}

            {/* Metadata row */}
            <div className="space-y-1">
              <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">Metadata</p>
              <div className="space-y-1.5">
                {[
                  { label: 'Term ID', value: item.term_id ?? '—' },
                  { label: 'Classification', value: item.metric_classification || '—' },
                  { label: 'Business name', value: item.business_name || '—' },
                  { label: 'Enriched at', value: item.enriched_at ? new Date(item.enriched_at).toLocaleString() : '—' },
                  { label: 'Model ID', value: item.model_id || '—' },
                ].map(({ label, value }) => (
                  <div key={label} className="flex items-start justify-between gap-3 text-xs">
                    <span className="text-slate-400 shrink-0">{label}</span>
                    <span className="text-slate-700 font-medium text-right truncate max-w-[200px]">{String(value)}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Full Asset ID */}
            <div className="space-y-1">
              <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">Full Asset ID</p>
              <p className="font-mono text-[10px] text-slate-500 break-all leading-relaxed">{item.asset_id}</p>
            </div>
          </div>

          {/* Tier 3 Recommendations */}
          {item.tier3_recommendations && item.tier3_recommendations.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-1.5">
                <ListOrdered size={12} className="text-slate-400" />
                <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">Top Term Recommendations</p>
              </div>
              <div className="space-y-2">
                {item.tier3_recommendations.map((rec) => (
                  <div key={rec.rank} className="flex items-start gap-3 rounded-xl bg-white border border-slate-200 px-3 py-2.5">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-red-50 text-[10px] font-bold text-red-700">
                      {rec.rank}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-semibold text-slate-800 truncate">{rec.term_title}</span>
                        <span className="text-[11px] font-mono text-emerald-700 shrink-0">{rec.confidence}%</span>
                      </div>
                      <p className="mt-0.5 text-[11px] text-slate-500 leading-relaxed line-clamp-2">{rec.rationale}</p>
                      {rec.term_description && (
                        <p className="mt-1 text-[11px] text-slate-400 leading-relaxed line-clamp-2">{rec.term_description}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────
function EnrichmentDetailDrawer({
  item,
  onClose,
}: {
  item: EnrichmentResult | null;
  onClose: () => void;
}) {
  return (
    <div className={`fixed inset-0 z-[9998] transition ${item ? 'pointer-events-auto' : 'pointer-events-none'}`}>
      <div
        className={`absolute inset-0 bg-slate-900/20 transition-opacity ${item ? 'opacity-100' : 'opacity-0'}`}
        onClick={onClose}
      />
      <aside className={`absolute right-0 top-0 h-full w-full max-w-2xl overflow-y-auto border-l border-slate-200 bg-white shadow-2xl transition-transform duration-300 ${item ? 'translate-x-0' : 'translate-x-full'}`}>
        {item && (
          <div>
            <div className="sticky top-0 z-10 border-b border-slate-200 bg-white px-6 py-5">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Business Enrichment Details</p>
                  <h2 className="mt-1 truncate text-xl font-bold text-slate-900">{item.asset_name}</h2>
                  <p className="mt-1 text-sm text-slate-500">{item.business_name || item.term_title || '—'}</p>
                </div>
                <button
                  onClick={onClose}
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-50"
                >
                  <X size={16} />
                </button>
              </div>
            </div>

            <div className="space-y-5 p-6">
              <div className="grid grid-cols-2 gap-3">
                {[
                  ['Asset Type', item.asset_type],
                  ['Metric Classification', item.metric_classification || '—'],
                  ['Linkage Type', item.linkage_type],
                  ['Confidence', `${item.confidence_score}%`],
                  ['Term Title', item.term_title || '—'],
                  ['Term ID', item.term_id ?? '—'],
                  ['Description Enriched', item.description_enriched ? 'Yes' : 'No'],
                  ['Enriched At', formatEnrichedAt(item.enriched_at)],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
                    <p className="text-[10px] font-semibold uppercase text-slate-400">{label}</p>
                    <p className="mt-1 break-words text-sm font-semibold text-slate-800">{String(value)}</p>
                  </div>
                ))}
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Business Definition</p>
                <p className="mt-2 text-sm leading-7 text-slate-700">{item.business_definition || '—'}</p>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Matching Rationale</p>
                <p className="mt-2 text-sm leading-7 text-slate-700">{item.matching_rationale || '—'}</p>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Purpose Statement</p>
                <p className="mt-2 text-sm leading-7 text-slate-700">{item.purpose_statement || 'No purpose statement generated.'}</p>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Tier 3 Recommendations</p>
                <div className="mt-3 space-y-3">
                  {(item.tier3_recommendations || []).map((rec) => (
                    <div key={`${rec.rank}-${rec.term_title}`} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-slate-900">#{rec.rank} {rec.term_title}</p>
                          <p className="mt-1 text-xs text-slate-500">{rec.rationale}</p>
                        </div>
                        <span className="shrink-0 rounded-full border border-slate-200 bg-white px-2 py-0.5 text-xs font-semibold text-slate-700">
                          {rec.confidence}%
                        </span>
                      </div>
                      <p className="mt-2 text-xs leading-6 text-slate-600">{rec.term_description}</p>
                    </div>
                  ))}
                  {(!item.tier3_recommendations || item.tier3_recommendations.length === 0) && (
                    <p className="text-sm text-slate-400">No recommendations returned.</p>
                  )}
                </div>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Technical Metadata</p>
                <div className="mt-3 space-y-3 text-xs">
                  <div>
                    <p className="font-semibold text-slate-500">asset_id</p>
                    <p className="mt-1 break-all font-mono text-slate-600">{item.asset_id}</p>
                  </div>
                  <div>
                    <p className="font-semibold text-slate-500">model_id</p>
                    <p className="mt-1 break-all font-mono text-slate-600">{item.model_id || '—'}</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}

function KpiDetailDrawer({
  item,
  onClose,
}: {
  item: RationalizedItem | null;
  onClose: () => void;
}) {
  return (
    <div className={`fixed inset-0 z-[9998] transition ${item ? 'pointer-events-auto' : 'pointer-events-none'}`}>
      <div
        className={`absolute inset-0 bg-slate-900/20 transition-opacity ${item ? 'opacity-100' : 'opacity-0'}`}
        onClick={onClose}
      />
      <aside className={`absolute right-0 top-0 h-full w-full max-w-2xl overflow-y-auto border-l border-slate-200 bg-white shadow-2xl transition-transform duration-300 ${item ? 'translate-x-0' : 'translate-x-full'}`}>
        {item && (
          <div>
            <div className="sticky top-0 z-10 border-b border-slate-200 bg-white px-6 py-5">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">KPI Rationalization Details</p>
                  <h2 className="mt-1 truncate text-xl font-bold text-slate-900">{item.Name}</h2>
                  <p className="mt-1 text-sm text-slate-500">{item['Report Name'] || '—'}</p>
                </div>
                <button
                  onClick={onClose}
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-50"
                >
                  <X size={16} />
                </button>
              </div>
            </div>

            <div className="space-y-5 p-6">
              <div className="grid grid-cols-2 gap-3">
                {[
                  ['Item Type', item['Item Type']],
                  ['Report Name', item['Report Name'] || '—'],
                  ['Table / Folder', item['Table / Folder'] || '—'],
                  ['Data Type', item['Data Type'] || '—'],
                  ['Semantic Type', item['Semantic Type'] || '—'],
                  ['Similarity Score', `${((item['Similarity Score'] || 0) * 100).toFixed(0)}%`],
                  ['AI Verdict Refined', item['AI Verdict Refined'] || item['AI Verdict'] || '—'],
                  ['Overlap Group ID', item['Overlap Group ID'] ?? '—'],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
                    <p className="text-[10px] font-semibold uppercase text-slate-400">{label}</p>
                    <p className="mt-1 break-words text-sm font-semibold text-slate-800">{String(value)}</p>
                  </div>
                ))}
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Asset ID</p>
                <p className="mt-2 break-all font-mono text-xs leading-6 text-slate-600">{item['Asset ID']}</p>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Normalized Formula</p>
                <code className="mt-2 block whitespace-pre-wrap rounded-lg bg-slate-50 p-3 font-mono text-xs leading-6 text-slate-700">
                  {item['Normalized Formula'] || '—'}
                </code>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Rationale Refined</p>
                <p className="mt-2 text-sm leading-7 text-slate-700">{item['Rationale Refined'] || '—'}</p>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Original Rationalization Context</p>
                <div className="mt-3 space-y-3 text-sm text-slate-700">
                  <p><span className="font-semibold text-slate-500">AI Verdict:</span> {item['AI Verdict'] || '—'}</p>
                  <p><span className="font-semibold text-slate-500">Rationale:</span> {item.Rationale || '—'}</p>
                  <p><span className="font-semibold text-slate-500">Top Match:</span> {item['Top Match'] || '—'}</p>
                  <p><span className="font-semibold text-slate-500">Top 3 Matches:</span> {item['Top 3 Matches'] || '—'}</p>
                </div>
              </div>
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}

export default function KpiRationalizationDashboard() {
  const navigate = useNavigate();
  const { sideNavWidth } = useOutletContext<{ sideNavWidth: number }>();
  const dispatch = useDispatch();
  const kpiJob = useSelector(selectJob('kpi-rationalization'));
  const enrichJob = useSelector(selectJob('business-enrichment'));
  const isKpiRunning = kpiJob?.status === 'running' || kpiJob?.status === 'polling';
  const isEnrichRunning = enrichJob?.status === 'running' || enrichJob?.status === 'polling';

  // Files
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFileEntry[]>([]);
  const [reports, setReports] = useState<ReportListItem[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [isSelectorOpen, setIsSelectorOpen] = useState(false);
  const [isLoadingFiles, setIsLoadingFiles] = useState(false);

  // Rationalization
  const [workflowStep, setWorkflowStep] = useState<WorkflowStep>('idle');
  const [rationalizationResult, setRationalizationResult] = useState<RationalizationResult | null>(null);
  const [rationalizationJobId, setRationalizationJobId] = useState<string>('');
  const [errorMessage, setErrorMessage] = useState('');

  // Enrichment
  const [enrichmentResult, setEnrichmentResult] = useState<EnrichmentResult[]>([]);
  const [enrichSearch, setEnrichSearch] = useState('');
  const [enrichFilter, setEnrichFilter] = useState<'all' | 'enriched' | 'not-enriched' | 'error'>('all');
  const [enrichLinkageFilter, setEnrichLinkageFilter] = useState('all');
  const [enrichMetricFilter, setEnrichMetricFilter] = useState('all');
  const [selectedEnrichment, setSelectedEnrichment] = useState<EnrichmentResult | null>(null);

  // Glossary
  const [glossaryId, setGlossaryId] = useState('2');
  const [glossaryLimit, setGlossaryLimit] = useState('10');
  const [glossaryTerms, setGlossaryTerms] = useState<GlossaryTerm[]>([]);
  const [selectedTerm, setSelectedTerm] = useState<GlossaryTerm | null>(null);
  const [termDescription, setTermDescription] = useState('');
  const [glossarySearch, setGlossarySearch] = useState('');
  const [isLoadingGlossary, setIsLoadingGlossary] = useState(false);
  const [isSavingTerm, setIsSavingTerm] = useState(false);

  // UI
  const [activeTab, setActiveTab] = useState<ActiveTab>('rationalize');
  const [searchQuery, setSearchQuery] = useState('');
  const [activeFilter, setActiveFilter] = useState('all');
  const [kpiReportFilter, setKpiReportFilter] = useState('all');
  const [kpiTypeFilter, setKpiTypeFilter] = useState('all');
  const [toast, setToast] = useState<{ type: 'success' | 'error' | 'info'; message: string } | null>(null);
  const [selectedKpiItem, setSelectedKpiItem] = useState<RationalizedItem | null>(null);

  const effectiveWorkflowStep = isKpiRunning ? 'rationalizing'
    : isEnrichRunning ? 'ingesting'
    : workflowStep;

  // ── Toast auto-dismiss ──
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3500);
    return () => clearTimeout(t);
  }, [toast]);

  const showToast = (type: 'success' | 'error' | 'info', message: string) => setToast({ type, message });

  // ── Load cached results + files on mount ──
  useEffect(() => {
    const activeFile = localStorage.getItem('activePowerBiReportFile') || enrichJob?.fileName || kpiJob?.fileName || '';
    const hasActiveReportData = Boolean(localStorage.getItem('activePowerBiReportData'));
    if (activeFile && hasActiveReportData && !isKpiRunning) {
      const cachedRat = loadJobResult('kpi-rationalization', activeFile);
      if (cachedRat) {
        setRationalizationResult(cachedRat);
        setRationalizationJobId(cachedRat.job_id || '');
        setWorkflowStep(isEnrichRunning ? 'ingesting' : 'done-rationalize');
      }
      if (!isEnrichRunning) {
        const cachedEnrich = loadJobResult('business-enrichment', activeFile);
        if (cachedEnrich) {
          setEnrichmentResult(Array.isArray(cachedEnrich) ? cachedEnrich : []);
          if (cachedRat) setWorkflowStep('done-enrich');
        }
      }
    }
    refreshFiles();
  }, []);

  const refreshFiles = async () => {
    setIsLoadingFiles(true);
    const files = readUploadedFiles();
    setUploadedFiles(files);
    if (files.length && !selectedFiles.length)
      setSelectedFiles(files.map((f) => f.fileName));
    const tools = [...new Set(files.map((f) => getToolName(f.fileName)))];
    const groups = await Promise.all(tools.map((t) => listPowerBiReports(t).catch(() => [])));
    setReports(groups.flat());
    setIsLoadingFiles(false);
  };

  const toggleFile = (name: string) =>
    setSelectedFiles((prev) =>
      prev.includes(name) ? prev.filter((f) => f !== name) : [...prev, name]
    );

  // ─── Step 1: KPI Rationalization ──────────────────────────────────────────
  const runRationalization = async () => {
    if (!selectedFiles.length) {
      showToast('error', 'Select at least one file to rationalize.');
      return;
    }
    setWorkflowStep('rationalizing');
    setErrorMessage('');
    setRationalizationResult(null);
    setEnrichmentResult([]);

    const activeFile = localStorage.getItem('activePowerBiReportFile') || selectedFiles[0] || '';
    dispatch(startJob({ type: 'kpi-rationalization', fileName: activeFile, estimatedTotalMs: 600000 }));

    try {
      dispatch(advanceStep({ type: 'kpi-rationalization', stepIndex: 0 }));
      dispatch(advanceStep({ type: 'kpi-rationalization', stepIndex: 1, statusMessage: 'Fetching report data…' }));
      const reportsData = await Promise.all(
        selectedFiles.map((fileName) => {
          const meta = reports.find((r) => r.file_name === fileName);
          return fetchPowerBiReport(fileName, meta?.tool_type || getToolName(fileName), {
            reportId: meta?.report_id,
          });
        })
      );

      dispatch(advanceStep({ type: 'kpi-rationalization', stepIndex: 2, statusMessage: 'Building analysis payload…' }));
      dispatch(addJobLog({ type: 'kpi-rationalization', message: `Fetched ${reportsData.length} reports` }));
      const payload = reportsData.map((r) => ({ content: r?.result || r?.data || r || {} }));

      dispatch(advanceStep({ type: 'kpi-rationalization', stepIndex: 3, statusMessage: 'Running rationalization API…' }));

      const res = await fetch(`${REPORTS_API}/rationalize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', accept: 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const msg = await res.text();
        throw new Error(msg || `Rationalization failed (${res.status})`);
      }

      const data: RationalizationResult = await res.json();
      dispatch(advanceStep({ type: 'kpi-rationalization', stepIndex: 4, statusMessage: 'Processing catalog…' }));
      setRationalizationResult(data);
      setRationalizationJobId(data.job_id || '');
      setWorkflowStep('done-rationalize');

      saveJobResult('kpi-rationalization', activeFile, data);
      dispatch(completeJob({ type: 'kpi-rationalization', statusMessage: `Rationalization complete — ${data.rationalized_catalog?.length || 0} assets` }));
      showToast('success', `Rationalization complete — ${data.rationalized_catalog?.length || 0} assets analyzed.`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      setErrorMessage(msg);
      setWorkflowStep('error');
      dispatch(failJob({ type: 'kpi-rationalization', errorMessage: msg }));
      showToast('error', msg);
    }
  };

  // ─── Step 2: Business Enrichment ──────────────────────────────────────────
  const runEnrichment = async () => {
    if (!rationalizationJobId) {
      showToast('error', 'No rationalization job ID found. Run rationalization first.');
      return;
    }
    setWorkflowStep('ingesting');
    setErrorMessage('');

    const activeFile = localStorage.getItem('activePowerBiReportFile') || selectedFiles[0] || '';
    if (rationalizationResult) saveJobResult('kpi-rationalization', activeFile, rationalizationResult);
    dispatch(startJob({ type: 'business-enrichment', fileName: activeFile, estimatedTotalMs: 300000 }));

    try {
      dispatch(advanceStep({ type: 'business-enrichment', stepIndex: 0 }));
      dispatch(advanceStep({ type: 'business-enrichment', stepIndex: 1, statusMessage: 'Ingesting from Postgres…' }));

      const res = await fetch(
        `${ENRICHMENT_API}/assets/ingest-from-postgres?job_id=${rationalizationJobId}`,
        { method: 'POST', headers: { accept: 'application/json' }, body: '' }
      );

      if (!res.ok) {
        const msg = await res.text();
        throw new Error(msg || `Enrichment ingest failed (${res.status})`);
      }

      const data: EnrichmentResult[] = await res.json();
      const enrichData = Array.isArray(data) ? data : [];
      setEnrichmentResult(enrichData);
      setWorkflowStep('done-enrich');
      setActiveTab('enrich');

      saveJobResult('business-enrichment', activeFile, enrichData);
      dispatch(completeJob({ type: 'business-enrichment', statusMessage: `Enrichment complete — ${enrichData.length} assets ingested` }));
      showToast('success', `Business enrichment complete — ${enrichData.length} assets ingested.`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      setErrorMessage(msg);
      setWorkflowStep('error');
      dispatch(failJob({ type: 'business-enrichment', errorMessage: msg }));
      showToast('error', msg);
    }
  };

  // ─── Step 3: Fetch Glossary Terms ─────────────────────────────────────────
  const fetchGlossaryTerms = async () => {
    setIsLoadingGlossary(true);
    try {
      const res = await fetch(
        `${ENRICHMENT_API}/alation/terms?glossary_id=${glossaryId}&limit=${glossaryLimit}`,
        { headers: { accept: 'application/json' } }
      );
      const data = await res.json();
      setGlossaryTerms(data?.terms || []);
      setSelectedTerm(null);
      setTermDescription('');
      showToast('success', `Fetched ${data?.terms?.length || 0} glossary terms.`);
    } catch {
      showToast('error', 'Failed to fetch glossary terms.');
    } finally {
      setIsLoadingGlossary(false);
    }
  };

  // ─── Step 4: Update Glossary Term Description ─────────────────────────────
  const updateTermDescription = async () => {
    if (!selectedTerm) return;
    setIsSavingTerm(true);
    try {
      const res = await fetch(`${ENRICHMENT_API}/curation/term-description`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', accept: 'application/json' },
        body: JSON.stringify({
          term_id: selectedTerm.id,
          description: termDescription,
          template_id: selectedTerm.template_id,
        }),
      });
      const data = await res.json();
      showToast('success', data?.detail || 'Description updated successfully.');
    } catch {
      showToast('error', 'Failed to update description.');
    } finally {
      setIsSavingTerm(false);
    }
  };

  // ─── Derived data ─────────────────────────────────────────────────────────
  const catalog = rationalizationResult?.rationalized_catalog || [];
  const summary = rationalizationResult?.rationalized_verdict_summary || [];
  const overlaps = rationalizationResult?.rationalized_overlaps_duplicates || [];

  const verdictCounts = useMemo(() => {
    const m: Record<string, number> = {};
    summary.forEach((s) => { m[s['AI Verdict']] = (m[s['AI Verdict']] || 0) + s.Count; });
    return m;
  }, [summary]);

  const kpiReportOptions = useMemo(() =>
    Array.from(new Set(catalog.map((item) => item['Report Name']).filter(Boolean))).sort(),
    [catalog]
  );

  const kpiTypeOptions = useMemo(() =>
    Array.from(new Set(catalog.map((item) => item['Item Type']).filter(Boolean))).sort(),
    [catalog]
  );

  const filteredCatalog = useMemo(() => {
    let items = activeTab === 'rationalize'
      ? (activeFilter === 'overlaps' ? overlaps : catalog)
      : catalog;
    if (searchQuery.trim())
      items = items.filter((item) =>
        JSON.stringify(item).toLowerCase().includes(searchQuery.toLowerCase())
      );
    if (activeFilter !== 'all' && activeFilter !== 'overlaps')
      items = items.filter((item) =>
        String(item['AI Verdict Refined'] || item['AI Verdict']).toLowerCase() === activeFilter
      );
    if (kpiReportFilter !== 'all')
      items = items.filter((item) => item['Report Name'] === kpiReportFilter);
    if (kpiTypeFilter !== 'all')
      items = items.filter((item) => item['Item Type'] === kpiTypeFilter);
    return items;
  }, [catalog, overlaps, activeTab, activeFilter, searchQuery, kpiReportFilter, kpiTypeFilter]);

  const filteredEnrichment = useMemo(() => {
    let items = enrichmentResult;
    if (enrichSearch.trim())
      items = items.filter((i) =>
        JSON.stringify(i).toLowerCase().includes(enrichSearch.toLowerCase())
      );
    if (enrichFilter === 'enriched') items = items.filter((i) => i.description_enriched);
    if (enrichFilter === 'not-enriched') items = items.filter((i) => !i.description_enriched && i.linkage_type !== 'error');
    if (enrichFilter === 'error') items = items.filter((i) => i.linkage_type === 'error');
    if (enrichLinkageFilter !== 'all') items = items.filter((i) => i.linkage_type === enrichLinkageFilter);
    if (enrichMetricFilter !== 'all') items = items.filter((i) => i.metric_classification === enrichMetricFilter);
    return items;
  }, [enrichmentResult, enrichSearch, enrichFilter, enrichLinkageFilter, enrichMetricFilter]);

  const enrichLinkageOptions = useMemo(() =>
    Array.from(new Set(enrichmentResult.map((item) => item.linkage_type).filter(Boolean))).sort(),
    [enrichmentResult]
  );

  const enrichMetricOptions = useMemo(() =>
    Array.from(new Set(enrichmentResult.map((item) => item.metric_classification).filter(Boolean))).sort(),
    [enrichmentResult]
  );

  const filteredGlossaryTerms = useMemo(() =>
    glossaryTerms.filter((t) => t.title.toLowerCase().includes(glossarySearch.toLowerCase())),
    [glossaryTerms, glossarySearch]
  );

  const getGlossaryFieldValue = (fieldName: string) => {
    if (!selectedTerm) return '—';
    const f = selectedTerm.custom_fields?.find((c) => c.field_name === fieldName);
    if (!f) return '—';
    if (Array.isArray(f.value)) return String(f.value.length);
    return String(f.value ?? '—');
  };

  const enrichmentErrors = enrichmentResult.filter((r) => r.linkage_type === 'error').length;
  const enrichmentSuccess = enrichmentResult.filter((r) => r.linkage_type !== 'error').length;
  const enrichmentEnriched = enrichmentResult.filter((r) => r.description_enriched).length;

  const isRunning = effectiveWorkflowStep === 'rationalizing' || effectiveWorkflowStep === 'ingesting';

  // ─── Render ───────────────────────────────────────────────────────────────
  return (
    <ContentCard
      heading={null}
      sideNavWidth={sideNavWidth}
      headerComponent={<FileWorkspaceHeader pageTitle="KPI Rationalization & Business Enrichment" />}
      noscroll
      flat={true}
    >
      <div
        style={{
          height: 'calc(100vh - 116px)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          background: '#f8fafc',
        }}
      >
        {/* ── Top Toolbar ── */}
        <div
          style={{
            display: 'flex', alignItems: 'center', gap: 12,
            padding: '10px 16px', borderBottom: '1px solid #cbd5e1',
            backgroundColor: '#ffffff', flexShrink: 0, flexWrap: 'wrap',
          }}
        >
          {/* Workflow Pipeline inline */}
          <div style={{ flex: 1 }}>
            <WorkflowPipelineInline step={workflowStep} />
          </div>
          {/* Gap Analysis quick link */}
          <button
            onClick={() => navigate('/gap-analysis')}
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '6px 12px', background: '#EFF6FF',
              border: '1px solid #BFDBFE', borderRadius: '8px',
              fontSize: '11.5px', fontWeight: 700, color: '#1E40AF',
              cursor: 'pointer', flexShrink: 0,
            }}
          >
            <ArrowRight size={13} /> Intelligence Hub
          </button>
        </div>

        {/* ── Scrollable Content ── */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: 16 }}>

        {/* ── File Selector + Action Panel ── */}
        <div className="grid grid-cols-1 xl:grid-cols-[1fr_auto] gap-4">
          <div className="rounded-2xl border border-slate-200 bg-white p-5">
            <p className="text-xs font-semibold uppercase tracking-widest text-slate-400 mb-3">Source Files</p>
            <div className="relative">
              <button
                onClick={() => setIsSelectorOpen((o) => !o)}
                className="flex h-11 w-full items-center justify-between rounded-xl border border-slate-200 bg-white px-4 text-sm hover:border-red-300 transition"
              >
                <span className="font-medium text-slate-800 truncate">
                  {selectedFiles.length === 0
                    ? 'Select files to rationalize...'
                    : `${selectedFiles.length} file${selectedFiles.length > 1 ? 's' : ''} selected`}
                </span>
                <ChevronDown size={16} className="text-slate-400 shrink-0" />
              </button>
              {isSelectorOpen && (
                <div className="absolute z-30 mt-2 w-full max-h-64 overflow-auto rounded-xl border border-slate-200 bg-white shadow-xl p-2">
                  {isLoadingFiles ? (
                    <div className="flex items-center gap-2 px-3 py-3 text-sm text-slate-500">
                      <Loader2 size={14} className="animate-spin" /> Loading files…
                    </div>
                  ) : uploadedFiles.length === 0 ? (
                    <div className="px-3 py-3 text-sm text-slate-400">No uploaded files found</div>
                  ) : (
                    uploadedFiles.map((f) => {
                      const checked = selectedFiles.includes(f.fileName);
                      return (
                        <button
                          key={f.fileName}
                          onClick={() => toggleFile(f.fileName)}
                          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left hover:bg-slate-50"
                        >
                          <span className={`grid h-5 w-5 shrink-0 place-items-center rounded border ${checked ? 'border-red-700 bg-red-700 text-white' : 'border-slate-300 bg-white'}`}>
                            {checked && <Check size={12} />}
                          </span>
                          <span className="min-w-0 flex-1 truncate text-sm font-medium text-slate-800">{f.fileName}</span>
                          <span className="text-[10px] font-semibold uppercase text-slate-400">
                            {getToolName(f.fileName) === 'powerbi' ? 'PBI' : 'TBL'}
                          </span>
                        </button>
                      );
                    })
                  )}
                </div>
              )}
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {selectedFiles.map((f) => (
                <span key={f} className="inline-flex items-center gap-1.5 rounded-full bg-red-50 px-2.5 py-1 text-[11px] font-semibold text-red-700 border border-red-100">
                  <Database size={10} />
                  <span className="truncate max-w-[180px]">{f}</span>
                  <button onClick={() => toggleFile(f)}><X size={10} /></button>
                </span>
              ))}
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex flex-col gap-3 min-w-[220px]">
            <button
              onClick={runRationalization}
              disabled={isRunning || !selectedFiles.length}
              className="flex h-12 items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-red-700 to-red-800 px-6 text-sm font-semibold text-white shadow-lg shadow-red-100 transition-all hover:scale-[1.01] hover:shadow-xl disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {effectiveWorkflowStep === 'rationalizing' ? (
                <><Loader2 size={16} className="animate-spin" /> Rationalizing…</>
              ) : (
                <><TrendingUp size={16} /> Run KPI Rationalization</>
              )}
            </button>

            <button
              onClick={runEnrichment}
              disabled={isRunning || !rationalizationJobId}
              className="flex h-12 items-center justify-center gap-2 rounded-xl border-2 border-blue-600 bg-gradient-to-r from-blue-50 to-indigo-50 px-6 text-sm font-semibold text-blue-700 transition-all hover:scale-[1.01] hover:shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {effectiveWorkflowStep === 'ingesting' ? (
                <><Loader2 size={16} className="animate-spin" /> Enriching…</>
              ) : (
                <><Sparkles size={16} /> Business Enrichment</>
              )}
            </button>

            {/* <button
              onClick={refreshFiles}
              className="flex h-10 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 text-sm font-medium text-slate-600 hover:bg-slate-50 transition"
            >
              <RefreshCw size={14} /> Refresh Files
            </button> */}
          </div>
        </div>

        {/* ── Error Banner ── */}
        {workflowStep === 'error' && errorMessage && (
          <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" />
            <span>{errorMessage}</span>
          </div>
        )}

        {/* ── Summary Stats ── */}
        {rationalizationResult && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {[
              { label: 'Total Assets', value: catalog.length, color: 'text-slate-900', bg: 'bg-slate-50 border-slate-200' },
              { label: 'Merge', value: verdictCounts['Merge'] || 0, color: 'text-blue-700', bg: 'bg-blue-50 border-blue-100' },
              { label: 'Retire', value: verdictCounts['Retire'] || 0, color: 'text-red-700', bg: 'bg-red-50 border-red-100' },
              { label: 'Standardize', value: verdictCounts['Standardize'] || 0, color: 'text-amber-700', bg: 'bg-amber-50 border-amber-100' },
              { label: 'Keep', value: verdictCounts['Keep'] || 0, color: 'text-emerald-700', bg: 'bg-emerald-50 border-emerald-100' },
            ].map(({ label, value, color, bg }) => (
              <div key={label} className={`rounded-xl border px-4 py-3 ${bg}`}>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</p>
                <p className={`mt-1 text-3xl font-bold ${color}`}>{value}</p>
              </div>
            ))}
          </div>
        )}

        {/* ── Tabs ── */}
        {(rationalizationResult || enrichmentResult.length > 0 || glossaryTerms.length > 0) && (
          <div className="flex gap-1 rounded-xl border border-slate-200 bg-slate-50 p-1 w-fit">
            {([
              { id: 'rationalize', label: 'KPI Catalog', icon: FileSearch },
              { id: 'enrich', label: 'Enrichment', icon: Zap, badge: enrichmentResult.length },
              { id: 'glossary', label: 'Glossary', icon: BookOpen },
            ] as const).map(({ id, label, icon: Icon, badge }) => (
              <button
                key={id}
                onClick={() => setActiveTab(id as ActiveTab)}
                className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition-all ${
                  activeTab === id ? 'bg-white shadow text-slate-900' : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                <Icon size={14} />
                {label}
                {badge !== undefined && badge > 0 && (
                  <span className="rounded-full bg-red-700 px-1.5 py-0.5 text-[10px] font-bold text-white">{badge}</span>
                )}
              </button>
            ))}
          </div>
        )}

        {/* ══ TAB: KPI Catalog ══════════════════════════════════════════════ */}
        {activeTab === 'rationalize' && rationalizationResult && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-3">
              <div className="relative flex-1 min-w-[200px] max-w-sm">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search assets…"
                  className="h-10 w-full rounded-xl border border-slate-200 bg-white pl-9 pr-3 text-sm outline-none focus:border-red-300"
                />
              </div>
              <div className="flex flex-wrap gap-2">
                {['all', 'merge', 'retire', 'standardize', 'keep'].map((f) => (
                  <button
                    key={f}
                    onClick={() => setActiveFilter(f)}
                    className={`rounded-lg border px-3 py-1.5 text-xs font-semibold capitalize transition ${
                      activeFilter === f
                        ? 'border-red-700 bg-red-700 text-white'
                        : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
                    }`}
                  >
                    {f}
                  </button>
                ))}
              </div>
              <select
                value={kpiReportFilter}
                onChange={(e) => setKpiReportFilter(e.target.value)}
                className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-600 outline-none focus:border-red-300"
              >
                <option value="all">All reports</option>
                {kpiReportOptions.map((report) => (
                  <option key={report} value={report}>{report}</option>
                ))}
              </select>
              <select
                value={kpiTypeFilter}
                onChange={(e) => setKpiTypeFilter(e.target.value)}
                className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-600 outline-none focus:border-red-300"
              >
                <option value="all">All types</option>
                {kpiTypeOptions.map((type) => (
                  <option key={type} value={type}>{type}</option>
                ))}
              </select>
              <span className="text-xs text-slate-400 ml-auto">{filteredCatalog.length} results</span>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
              <div className="max-h-[600px] overflow-auto">
                <table className="w-full min-w-[1280px] text-sm">
                  <thead className="sticky top-0 z-10 bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="px-4 py-3 text-left font-semibold">Item Type</th>
                      <th className="px-4 py-3 text-left font-semibold">Name</th>
                      <th className="px-4 py-3 text-left font-semibold">Report Name</th>
                      <th className="px-4 py-3 text-left font-semibold">Table / Folder</th>
                      <th className="px-4 py-3 text-left font-semibold">Normalized Formula</th>
                      <th className="px-4 py-3 text-left font-semibold">Similarity</th>
                      <th className="px-4 py-3 text-left font-semibold">AI Verdict Refined</th>
                      <th className="px-4 py-3 text-left font-semibold">Rationale Refined</th>
                      <th className="px-4 py-3 text-left font-semibold">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filteredCatalog.map((item, idx) => {
                      const key = `${item['Asset ID']}-${idx}`;
                      const verdict = item['AI Verdict Refined'] || item['AI Verdict'];
                      return (
                          <tr key={key} className="hover:bg-slate-50 transition-colors">
                            <td className="px-4 py-3">
                              <span className="inline-flex items-center rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                                {item['Item Type']}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              <p className="font-semibold text-slate-900 truncate max-w-[200px]">{item.Name}</p>
                            </td>
                            <td className="px-4 py-3 text-slate-700 text-xs truncate max-w-[180px]">{item['Report Name'] || '—'}</td>
                            <td className="px-4 py-3 text-slate-600 text-xs truncate max-w-[180px]">{item['Table / Folder'] || '—'}</td>
                            <td className="px-4 py-3">
                              <code className="block max-w-[280px] truncate rounded-lg bg-slate-50 px-2 py-1 font-mono text-[11px] text-slate-600">
                                {item['Normalized Formula'] || '—'}
                              </code>
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex items-center gap-2">
                                <div className="h-1.5 w-20 rounded-full bg-slate-100 overflow-hidden">
                                  <div
                                    className="h-full rounded-full bg-gradient-to-r from-red-500 to-red-700"
                                    style={{ width: `${Math.round((item['Similarity Score'] || 0) * 100)}%` }}
                                  />
                                </div>
                                <span className="text-xs text-slate-500 font-mono">
                                  {((item['Similarity Score'] || 0) * 100).toFixed(0)}%
                                </span>
                              </div>
                            </td>
                            <td className="px-4 py-3">
                              {verdict && (
                                <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold ${verdictColor(verdict)}`}>
                                  <span className={`h-1.5 w-1.5 rounded-full ${verdictDot(verdict)}`} />
                                  {verdict}
                                </span>
                              )}
                            </td>
                            <td className="px-4 py-3 text-xs text-slate-600">
                              <p className="line-clamp-2 max-w-[320px]">{item['Rationale Refined'] || '—'}</p>
                            </td>
                            <td className="px-4 py-3">
                              <button
                                onClick={() => setSelectedKpiItem(item)}
                                className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:border-slate-300 hover:bg-slate-50 transition"
                              >
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
            <KpiDetailDrawer item={selectedKpiItem} onClose={() => setSelectedKpiItem(null)} />
          </div>
        )}

        {/* ══ TAB: Business Enrichment ═══════════════════════════════════════ */}
        {activeTab === 'enrich' && (
          <div className="space-y-4">
            {enrichmentResult.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-16 text-center">
                <Zap size={40} className="mx-auto text-slate-300" />
                <h3 className="mt-4 text-lg font-semibold text-slate-700">No Enrichment Data Yet</h3>
                <p className="mt-2 text-sm text-slate-400">
                  Run KPI Rationalization first, then click "Business Enrichment".
                </p>
              </div>
            ) : (
              <>
                {/* Stats */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  {[
                    { label: 'Total Assets', value: enrichmentResult.length, color: 'text-slate-900', bg: 'bg-slate-50 border-slate-200' },
                    { label: 'Enriched', value: enrichmentEnriched, color: 'text-emerald-700', bg: 'bg-emerald-50 border-emerald-100' },
                    { label: 'Linked', value: enrichmentSuccess, color: 'text-blue-700', bg: 'bg-blue-50 border-blue-100' },
                    { label: 'Errors', value: enrichmentErrors, color: 'text-red-700', bg: 'bg-red-50 border-red-100' },
                  ].map(({ label, value, color, bg }) => (
                    <div key={label} className={`rounded-xl border px-4 py-3 ${bg}`}>
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</p>
                      <p className={`mt-1 text-3xl font-bold ${color}`}>{value}</p>
                    </div>
                  ))}
                </div>

                {/* Go to glossary banner */}
                <div className="flex items-center justify-between rounded-xl border border-blue-100 bg-gradient-to-r from-blue-50 to-indigo-50 px-5 py-4">
                  <div className="flex items-center gap-3">
                    <div className="rounded-lg bg-blue-600 p-2 text-white">
                      <BookOpen size={16} />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-slate-900">Enrich Glossary Terms</p>
                      <p className="text-xs text-slate-500">Fetch Alation glossary terms and update descriptions</p>
                    </div>
                  </div>
                  <button
                    onClick={() => { setActiveTab('glossary'); fetchGlossaryTerms(); }}
                    className="flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 transition"
                  >
                    Open Glossary <ArrowRight size={14} />
                  </button>
                </div>

                {/* Search + filter */}
                <div className="flex flex-wrap items-center gap-3">
                  <div className="relative flex-1 min-w-[200px] max-w-sm">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                    <input
                      value={enrichSearch}
                      onChange={(e) => setEnrichSearch(e.target.value)}
                      placeholder="Search enriched assets…"
                      className="h-10 w-full rounded-xl border border-slate-200 bg-white pl-9 pr-3 text-sm outline-none focus:border-red-300"
                    />
                  </div>
                  <div className="flex gap-2">
                    {(['all', 'enriched', 'not-enriched', 'error'] as const).map((f) => (
                      <button
                        key={f}
                        onClick={() => setEnrichFilter(f)}
                        className={`rounded-lg border px-3 py-1.5 text-xs font-semibold capitalize transition ${
                          enrichFilter === f
                            ? 'border-red-700 bg-red-700 text-white'
                            : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
                        }`}
                      >
                        {f.replace('-', ' ')}
                      </button>
                    ))}
                  </div>
                  <select
                    value={enrichLinkageFilter}
                    onChange={(e) => setEnrichLinkageFilter(e.target.value)}
                    className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-600 outline-none focus:border-red-300"
                  >
                    <option value="all">All linkage</option>
                    {enrichLinkageOptions.map((linkage) => (
                      <option key={linkage} value={linkage}>{linkage}</option>
                    ))}
                  </select>
                  <select
                    value={enrichMetricFilter}
                    onChange={(e) => setEnrichMetricFilter(e.target.value)}
                    className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-600 outline-none focus:border-red-300"
                  >
                    <option value="all">All classifications</option>
                    {enrichMetricOptions.map((metric) => (
                      <option key={metric} value={metric || ''}>{metric}</option>
                    ))}
                  </select>
                  <span className="text-xs text-slate-400 ml-auto">{filteredEnrichment.length} results</span>
                </div>

                {/* Enrichment table */}
                <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
                  <div className="max-h-[560px] overflow-auto">
                    <table className="w-full min-w-[1100px] text-sm">
                      <thead className="sticky top-0 z-10 bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500">
                        <tr>
                          <th className="px-4 py-3 text-left font-semibold">Asset</th>
                          <th className="px-4 py-3 text-left font-semibold">Type</th>
                          <th className="px-4 py-3 text-left font-semibold">Business Name</th>
                          <th className="px-4 py-3 text-left font-semibold">Term</th>
                          <th className="px-4 py-3 text-left font-semibold">Classification</th>
                          <th className="px-4 py-3 text-left font-semibold">Confidence</th>
                          <th className="px-4 py-3 text-left font-semibold">Linkage</th>
                          <th className="px-4 py-3 text-left font-semibold">Enriched</th>
                          <th className="px-4 py-3 text-left font-semibold">Action</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {filteredEnrichment.map((item, idx) => {
                          const confidence = Math.min(100, Math.max(0, Number(item.confidence_score || 0)));
                          const confidenceColor = confidence >= 80 ? 'bg-emerald-500' : confidence >= 50 ? 'bg-amber-500' : 'bg-red-500';
                          const confidenceText = confidence >= 80 ? 'text-emerald-700' : confidence >= 50 ? 'text-amber-700' : 'text-red-700';
                          return (
                            <tr key={`${item.asset_id}-${idx}`} className="hover:bg-slate-50 transition-colors">
                              <td className="px-4 py-3">
                                <p className="font-semibold text-slate-900 truncate max-w-[200px]">{item.asset_name}</p>
                                <p className="font-mono text-[10px] text-slate-400 truncate max-w-[240px]">{item.asset_id}</p>
                              </td>
                              <td className="px-4 py-3">
                                <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                                  {item.asset_type || '—'}
                                </span>
                              </td>
                              <td className="px-4 py-3 text-slate-700 truncate max-w-[180px]">{item.business_name || '—'}</td>
                              <td className="px-4 py-3">
                                <p className="text-slate-700 truncate max-w-[170px]">{item.term_title || '—'}</p>
                                <p className="text-[10px] text-slate-400">Term ID: {item.term_id ?? '—'}</p>
                              </td>
                              <td className="px-4 py-3">
                                <span className="rounded-md border border-slate-200 bg-white px-2 py-0.5 text-xs font-medium text-slate-600">
                                  {item.metric_classification || '—'}
                                </span>
                              </td>
                              <td className="px-4 py-3">
                                <div className="flex items-center gap-2">
                                  <div className="h-1.5 w-20 rounded-full bg-slate-100 overflow-hidden">
                                    <div className={`h-full rounded-full ${confidenceColor}`} style={{ width: `${confidence}%` }} />
                                  </div>
                                  <span className={`text-xs font-mono font-semibold ${confidenceText}`}>{confidence.toFixed(0)}%</span>
                                </div>
                              </td>
                              <td className="px-4 py-3">
                                <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold capitalize ${linkageColor(item.linkage_type)}`}>
                                  {item.linkage_type || '—'}
                                </span>
                              </td>
                              <td className="px-4 py-3">
                                {item.description_enriched
                                  ? <CheckCircle2 size={16} className="text-emerald-500" />
                                  : <X size={16} className="text-slate-300" />}
                              </td>
                              <td className="px-4 py-3">
                                <button
                                  onClick={() => setSelectedEnrichment(item)}
                                  className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:border-slate-300 hover:bg-slate-50 transition"
                                >
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
                <EnrichmentDetailDrawer item={selectedEnrichment} onClose={() => setSelectedEnrichment(null)} />
              </>
            )}
          </div>
        )}

        {/* ══ TAB: Glossary ════════════════════════════════════════════════ */}
        {activeTab === 'glossary' && (
          <div className="grid grid-cols-[320px_1fr] gap-5">
            {/* Left Panel */}
            <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
              <div className="border-b border-slate-100 p-4 space-y-3">
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-[10px] font-semibold uppercase text-slate-400">Glossary ID</label>
                    <input
                      type="number"
                      value={glossaryId}
                      onChange={(e) => setGlossaryId(e.target.value)}
                      className="mt-1 h-9 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none focus:border-red-400"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] font-semibold uppercase text-slate-400">Limit</label>
                    <input
                      type="number"
                      value={glossaryLimit}
                      onChange={(e) => setGlossaryLimit(e.target.value)}
                      className="mt-1 h-9 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none focus:border-red-400"
                    />
                  </div>
                </div>
                <button
                  onClick={fetchGlossaryTerms}
                  disabled={isLoadingGlossary}
                  className="w-full rounded-xl bg-red-700 py-2.5 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-60 transition flex items-center justify-center gap-2"
                >
                  {isLoadingGlossary ? <Loader2 size={14} className="animate-spin" /> : <BookOpen size={14} />}
                  Fetch Terms
                </button>
              </div>
              <div className="border-b border-slate-100 p-3">
                <div className="relative">
                  <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input
                    value={glossarySearch}
                    onChange={(e) => setGlossarySearch(e.target.value)}
                    placeholder="Search glossary…"
                    className="h-9 w-full rounded-lg border border-slate-200 bg-slate-50 pl-9 pr-3 text-sm outline-none focus:border-red-400"
                  />
                </div>
              </div>
              <div className="max-h-[60vh] overflow-auto">
                {filteredGlossaryTerms.length === 0 ? (
                  <div className="p-8 text-center">
                    <BookOpen size={32} className="mx-auto text-slate-200" />
                    <p className="mt-2 text-sm text-slate-400">No terms loaded</p>
                  </div>
                ) : (
                  filteredGlossaryTerms.map((term) => {
                    const active = selectedTerm?.id === term.id;
                    return (
                      <button
                        key={term.id}
                        onClick={() => { setSelectedTerm(term); setTermDescription(stripHtml(term.description || '')); }}
                        className={`w-full border-b border-slate-100 px-4 py-3 text-left transition ${active ? 'bg-red-50' : 'hover:bg-slate-50'}`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <h3 className={`text-sm font-semibold truncate ${active ? 'text-red-700' : 'text-slate-900'}`}>
                              {term.title}
                            </h3>
                            <p className="mt-0.5 line-clamp-2 text-xs text-slate-400">{stripHtml(term.description || '')}</p>
                          </div>
                          {active && <CheckCircle2 size={14} className="text-red-700 shrink-0 mt-0.5" />}
                        </div>
                        <p className="mt-1.5 text-[10px] text-slate-400">Term #{term.id}</p>
                      </button>
                    );
                  })
                )}
              </div>
            </div>

            {/* Right Panel */}
            {!selectedTerm ? (
              <div className="rounded-2xl border border-dashed border-slate-300 bg-white flex flex-col items-center justify-center p-16">
                <Layers size={40} className="text-slate-300" />
                <h3 className="mt-4 text-lg font-semibold text-slate-700">Select a Glossary Term</h3>
                <p className="mt-1 text-sm text-slate-400">Fetch terms and click one to view details</p>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="rounded-2xl border border-slate-200 bg-white p-6">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-start gap-3">
                      <div className="rounded-xl bg-red-50 p-3 text-red-700"><Sparkles size={18} /></div>
                      <div>
                        <h2 className="text-xl font-bold text-slate-900">{selectedTerm.title}</h2>
                        <p className="text-xs text-slate-400 mt-0.5">AI Curated Glossary Term · #{selectedTerm.id}</p>
                      </div>
                    </div>
                    <button
                      onClick={updateTermDescription}
                      disabled={isSavingTerm}
                      className="flex h-10 items-center gap-2 rounded-xl bg-red-700 px-4 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-60 transition"
                    >
                      {isSavingTerm ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                      Save
                    </button>
                  </div>
                  <div className="mt-4 grid grid-cols-3 gap-3">
                    {[
                      ['Term ID', selectedTerm.id],
                      ['Template ID', selectedTerm.template_id],
                      ['Updated', new Date(selectedTerm.ts_updated).toLocaleDateString()],
                    ].map(([l, v]) => (
                      <div key={String(l)} className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-2">
                        <p className="text-[10px] font-semibold uppercase text-slate-400">{l}</p>
                        <p className="mt-1 text-base font-bold text-slate-900">{String(v)}</p>
                      </div>
                    ))}
                  </div>
                  <div className="mt-4">
                    <label className="mb-1.5 block text-sm font-semibold text-slate-700">Description</label>
                    <textarea
                      value={termDescription}
                      onChange={(e) => setTermDescription(e.target.value)}
                      rows={8}
                      className="w-full rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm leading-7 text-slate-700 outline-none focus:border-red-400 transition resize-none"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="rounded-2xl border border-slate-200 bg-white p-5">
                    <div className="flex items-center gap-2 mb-4">
                      <Shield size={16} className="text-red-700" />
                      <h3 className="font-semibold text-slate-900">Governance</h3>
                    </div>
                    {[
                      ['Security', 'Security Classification'],
                      ['PII', 'Personally Identifiable Information'],
                      ['Criticality', 'Criticality Indicator'],
                      ['Popularity', 'Popularity'],
                    ].map(([label, field]) => (
                      <div key={label} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 mb-2">
                        <span className="text-xs text-slate-500">{label}</span>
                        <span className="text-xs font-semibold text-slate-900">{getGlossaryFieldValue(field)}</span>
                      </div>
                    ))}
                  </div>
                  <div className="rounded-2xl border border-slate-200 bg-white p-5">
                    <div className="flex items-center gap-2 mb-4">
                      <User size={16} className="text-red-700" />
                      <h3 className="font-semibold text-slate-900">Stewardship</h3>
                    </div>
                    {[
                      ['Business Owner', 'Business Data Owner'],
                      ['Steward', 'Business Steward'],
                      ['Expert', 'Subject Matter Expert'],
                      ['Assets', 'Data Asset'],
                    ].map(([label, field]) => (
                      <div key={label} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 mb-2">
                        <span className="text-xs text-slate-500">{label}</span>
                        <span className="text-xs font-semibold text-slate-900">{getGlossaryFieldValue(field)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── Toast ── */}
        {toast && (
          <div className={`fixed top-6 right-6 z-[9999] flex items-center gap-3 rounded-xl border px-5 py-3.5 shadow-2xl transition-all ${
            toast.type === 'success'
              ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
              : toast.type === 'info'
              ? 'border-blue-200 bg-blue-50 text-blue-700'
              : 'border-red-200 bg-red-50 text-red-700'
          }`}>
            <span className={`h-2 w-2 rounded-full ${
              toast.type === 'success' ? 'bg-emerald-500' : toast.type === 'info' ? 'bg-blue-500' : 'bg-red-500'
            }`} />
            <p className="text-sm font-medium">{toast.message}</p>
          </div>
        )}
        </div>{/* end scrollable content */}
      </div>{/* end height container */}
    </ContentCard>
  );
}

// ─── Workflow Pipeline (Inline Toolbar Version) ───────────────────────────────
function WorkflowPipelineInline({ step }: { step: WorkflowStep }) {
  const NAVY = '#003087';
  const steps = [
    { id: 'select', label: 'Select Files', icon: Database },
    { id: 'rationalize', label: 'KPI Rationalization', icon: TrendingUp },
    { id: 'enrich', label: 'Business Enrichment', icon: Zap },
    { id: 'glossary', label: 'Glossary Curation', icon: BookOpen },
  ];

  const activeIdx =
    step === 'idle' ? 0
    : step === 'rationalizing' || step === 'loading-files' ? 1
    : step === 'done-rationalize' ? 2
    : step === 'ingesting' ? 2
    : step === 'done-enrich' ? 3
    : step === 'error' ? 1
    : 0;

  const completedIdx =
    step === 'done-rationalize' ? 1
    : step === 'ingesting' ? 2
    : step === 'done-enrich' ? 3
    : 0;

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 0 }}>
      {steps.map((s, i) => {
        const Icon = s.icon;
        const isDone = i < completedIdx || (completedIdx === 3 && i <= 3);
        const isActive = i === activeIdx;
        const isRunning =
          (step === 'rationalizing' && i === 1) || (step === 'ingesting' && i === 2);
        return (
          <React.Fragment key={s.id}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
              <div
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  width: 28, height: 28, borderRadius: '50%', border: '2px solid',
                  borderColor: isDone ? '#10B981' : isActive ? NAVY : '#CBD5E1',
                  background: isDone ? '#10B981' : isActive ? NAVY : '#fff',
                  color: (isDone || isActive) ? '#fff' : '#94A3B8',
                  transition: 'all 0.2s',
                }}
              >
                {isRunning ? <Loader2 size={13} className="animate-spin" /> : isDone ? <Check size={12} /> : <Icon size={12} />}
              </div>
              <span
                style={{
                  fontSize: '10px', fontWeight: 700, whiteSpace: 'nowrap',
                  color: isDone ? '#10B981' : isActive ? NAVY : '#94A3B8',
                }}
              >
                {s.label}
              </span>
            </div>
            {i < steps.length - 1 && (
              <div
                style={{
                  flex: 1, height: 2, margin: '0 6px', marginBottom: 14,
                  borderRadius: 99, minWidth: 20,
                  background: i < completedIdx ? '#10B981' : '#E2E8F0',
                  transition: 'background 0.3s',
                }}
              />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

// Keep old WorkflowPipeline as alias for backward compat (unused)
function WorkflowPipeline({ step }: { step: WorkflowStep }) {
  return <WorkflowPipelineInline step={step} />;
}
