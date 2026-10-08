import React, { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  AlertTriangle, CheckCircle2, ChevronDown, ChevronRight,
  FileCheck2, Search, ShieldCheck, XCircle, TrendingUp, TrendingDown,
  Database, Eye, Filter, BarChart2, Link2, Minus,
  ArrowUpRight, Info, Activity, X, MousePointerClick
} from 'lucide-react';

/* ─── Unified Data Models ─── */
export type VStatus = 'PASS' | 'FAIL' | 'MISSING' | 'WARNING' | 'SKIP';

export interface UnifiedFinding {
  id: string;
  checkId: string;
  category: string;
  status: VStatus;
  title: string;
  description: string;
  severity: string;
  sourceValue?: string;
  jsonValue?: string;
  note?: string;
}

export interface UnifiedCheckRow {
  check: string;
  label: string;
  description: string;
  scope: string;
  score: number;
  verdict: string;
  passed: number;
  failed: number;
  missing: number;
  total: number;
  weight_earned?: number;
  weight_total?: number;
}

export interface UnifiedValidationData {
  workbookId?: string;
  timestamp?: string;
  overallScore: number | null;
  semanticScore: number | null;
  visualScore: number | null;
  verdict: string;
  semanticVerdict: string;
  visualVerdict: string;
  totalChecks: number;
  gapsCount: number;
  checkSummary: UnifiedCheckRow[];
  findings: UnifiedFinding[];
}

interface Props {
  data: UnifiedValidationData | null;
  ToolbarComponent?: React.ReactNode;
}

/* ─── Shared Theme ─── */
const JNJ = {
  red:       '#c8102e',
  redLight:  '#fdf2f4',
  redMid:    '#f5cdd3',
  navy:      '#002147',
  slate:     '#64748b',
  slateLight:'#f8fafc',
  border:    '#e2e8f0',
  text:      '#0f172a',
  textMid:   '#475569',
  textLight: '#94a3b8',
  white:     '#ffffff',
  green:     '#059669',
  greenLight:'#ecfdf5',
  amber:     '#d97706',
  amberLight:'#fffbeb',
  orange:    '#ea580c',
};

const CHECK_ICONS: Record<string, React.ElementType> = {
  D1: Database, D2: BarChart2, D3: FileCheck2,
  D4: Filter,   D5: Link2,    D6: Eye,
  D6a: Eye, D6b: Activity, D6c: Info,
  D6f: ArrowUpRight, D6g: Activity, D7: Link2,
};

const SCOPE_COLOR: Record<string, { bg: string; text: string; border: string }> = {
  semantic: { bg: JNJ.slateLight, text: JNJ.textMid, border: JNJ.border },
  visual:   { bg: JNJ.slateLight, text: JNJ.textMid, border: JNJ.border },
};

const scoreColor = (score: number) => {
  if (score >= 80) return JNJ.green;
  if (score >= 60) return JNJ.amber;
  if (score >= 40) return JNJ.orange;
  return JNJ.red;
};

const verdictStyle = (verdict: string) => {
  const v = verdict.toUpperCase();
  if (v === 'PASS') return { bg: JNJ.white, text: JNJ.green, border: JNJ.border };
  if (v === 'FAIL') return { bg: JNJ.white, text: JNJ.red, border: JNJ.border };
  if (v === 'SKIP') return { bg: JNJ.white, text: JNJ.slate, border: JNJ.border };
  return { bg: JNJ.white, text: JNJ.amber, border: JNJ.border };
};

const statusConfig: Record<VStatus, { bg: string; text: string; border: string; icon: React.ElementType }> = {
  PASS:    { bg: JNJ.white, text: JNJ.green,  border: JNJ.border, icon: CheckCircle2 },
  FAIL:    { bg: JNJ.white, text: JNJ.red,    border: JNJ.border, icon: XCircle },
  MISSING: { bg: JNJ.white, text: JNJ.amber,  border: JNJ.border, icon: AlertTriangle },
  WARNING: { bg: JNJ.white, text: JNJ.orange, border: JNJ.border, icon: AlertTriangle },
  SKIP:    { bg: JNJ.white, text: JNJ.slate,  border: JNJ.border, icon: Minus },
};

const Gauge = ({ score, size = 72 }: { score: number | null; size?: number }) => {
  const isNull = score === null;
  const color = isNull ? JNJ.textLight : scoreColor(score as number);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', width: size, height: size, border: `1px solid ${JNJ.border}`, borderRadius: 8, background: JNJ.white }}>
      <span style={{ fontSize: size * 0.35, fontWeight: 800, color, lineHeight: 1 }}>{isNull ? 'N/A' : (score as number).toFixed(0)}</span>
      <span style={{ fontSize: size * 0.15, fontWeight: 600, color: JNJ.textLight, marginTop: 2 }}>{isNull ? '' : 'SCORE'}</span>
    </div>
  );
};

const ScoreBar = ({ score, verdict }: { score: number | null; verdict: string }) => {
  const isNull = score === null;
  const color = isNull ? JNJ.slate : scoreColor(score as number);
  const vd = verdictStyle(verdict);
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ flex: 1, height: 4, background: JNJ.slateLight, borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ width: isNull ? '0%' : `${score}%`, height: '100%', background: JNJ.slate, transition: 'width 0.8s ease' }} />
      </div>
      <span style={{ fontSize: 11, fontWeight: 600, color: JNJ.textMid, minWidth: 40, textAlign: 'right' }}>{isNull ? 'N/A' : `${(score as number).toFixed(0)}%`}</span>
      <span style={{ fontSize: 9, fontWeight: 700, padding: '1px 6px', borderRadius: 3,
        background: JNJ.white, color: vd.text, border: `1px solid ${vd.border}`, whiteSpace: 'nowrap' }}>
        {verdict}
      </span>
    </div>
  );
};

const CheckCard = ({ row }: { row: UnifiedCheckRow }) => {
  const [open, setOpen] = useState(false);
  const Icon = CHECK_ICONS[row.check] ?? FileCheck2;
  const sc = SCOPE_COLOR[row.scope] ?? { bg: JNJ.slateLight, text: JNJ.slate, border: JNJ.border };

  return (
    <div style={{ background: JNJ.white, border: `1px solid ${JNJ.border}`, borderRadius: 8, overflow: 'hidden' }}>
      <button onClick={() => setOpen(!open)}
        style={{ width: '100%', padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 12,
          background: 'transparent', border: 'none', cursor: 'pointer', textAlign: 'left' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5 }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: JNJ.text }}>{row.check}</span>
            <span style={{ fontSize: 12, fontWeight: 600, color: JNJ.textMid, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{row.label}</span>
          </div>
          <ScoreBar score={row.score} verdict={row.verdict} />
        </div>
        <ChevronDown size={14} color={JNJ.textLight}
          style={{ transform: open ? 'rotate(180deg)' : 'none', transition: '0.2s', flexShrink: 0 }} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }} style={{ overflow: 'hidden' }}>
            <div style={{ padding: '0 14px 14px', borderTop: `1px solid ${JNJ.border}`, background: JNJ.slateLight }}>
              <p style={{ fontSize: 11, color: JNJ.textMid, margin: '10px 0', lineHeight: 1.5 }}>{row.description}</p>
              <div style={{ display: 'flex', gap: 16, alignItems: 'center', fontSize: 11 }}>
                <span style={{ color: JNJ.textMid, fontWeight: 600 }}>{row.passed} passed</span>
                <span style={{ color: JNJ.textMid, fontWeight: 600 }}>{row.failed} failed</span>
                <span style={{ color: JNJ.textMid, fontWeight: 600 }}>{row.missing} missing</span>
                <span style={{ color: JNJ.textMid }}>{row.total} total</span>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

const FindingRow = ({ f }: { f: UnifiedFinding }) => {
  const [open, setOpen] = useState(false);
  const cfg = statusConfig[f.status];
  const Icon = cfg.icon;

  return (
    <div style={{ borderBottom: `1px solid ${JNJ.border}` }}>
      <button onClick={() => setOpen(!open)}
        style={{ width: '100%', padding: '11px 20px', display: 'flex', alignItems: 'flex-start',
          gap: 10, background: 'transparent', border: 'none', cursor: 'pointer', textAlign: 'left' }}>
        <div style={{ width: 7, height: 7, borderRadius: '50%', background: cfg.text, marginTop: 5, flexShrink: 0 }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap', marginBottom: 3 }}>
            <span style={{ fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 4,
              background: cfg.bg, color: cfg.text, border: `1px solid ${cfg.border}`,
              display: 'flex', alignItems: 'center', gap: 3 }}>
              <Icon size={9} /> {f.status}
            </span>
            <span style={{ fontSize: 10, fontWeight: 800, color: SCOPE_COLOR.semantic.text,
              fontFamily: 'monospace', background: SCOPE_COLOR.semantic.bg,
              border: `1px solid ${SCOPE_COLOR.semantic.border}`, padding: '1px 6px', borderRadius: 4 }}>
              {f.checkId}
            </span>
            {f.severity && f.severity !== f.status && (
              <span style={{ fontSize: 10, color: JNJ.textLight, fontWeight: 600 }}>{f.severity}</span>
            )}
          </div>
          <p style={{ fontSize: 12, color: JNJ.text, margin: '0 0 1px', fontFamily: 'monospace',
            wordBreak: 'break-all', whiteSpace: 'pre-wrap', fontWeight: 500 }}>{f.title}</p>
          {f.description && (
            <p style={{ fontSize: 11, color: JNJ.textMid, margin: 0, lineHeight: 1.5 }}>{f.description}</p>
          )}
        </div>
        <ChevronRight size={13} color={JNJ.textLight}
          style={{ transform: open ? 'rotate(90deg)' : 'none', transition: '0.15s', flexShrink: 0, marginTop: 2 }} />
      </button>

      <AnimatePresence>
        {open && f.sourceValue !== undefined && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }} style={{ overflow: 'hidden' }}>
            <div style={{ padding: '0 20px 12px 37px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <div style={{ background: JNJ.slateLight, border: `1px solid ${JNJ.border}`, borderRadius: 6, padding: '8px 10px' }}>
                <p style={{ fontSize: 10, color: JNJ.textMid, fontWeight: 700, textTransform: 'uppercase', margin: '0 0 4px' }}>Source Value (Actual)</p>
                <p style={{ fontSize: 11, fontFamily: 'monospace', color: JNJ.text, margin: 0, wordBreak: 'break-all' }}>{f.sourceValue || '—'}</p>
              </div>
              <div style={{ background: JNJ.slateLight, border: `1px solid ${JNJ.border}`, borderRadius: 6, padding: '8px 10px' }}>
                <p style={{ fontSize: 10, color: JNJ.textMid, fontWeight: 700, textTransform: 'uppercase', margin: '0 0 4px' }}>Expected (from JSON)</p>
                <p style={{ fontSize: 11, fontFamily: 'monospace', color: JNJ.text, margin: 0, wordBreak: 'break-all' }}>{f.jsonValue || '—'}</p>
              </div>
              {f.note && (
                <div style={{ gridColumn: '1/-1', background: JNJ.slateLight, border: `1px solid ${JNJ.border}`, borderRadius: 6, padding: '8px 10px' }}>
                  <p style={{ fontSize: 10, color: JNJ.textMid, fontWeight: 700, textTransform: 'uppercase', margin: '0 0 3px' }}>Note</p>
                  <p style={{ fontSize: 11, color: JNJ.text, margin: 0 }}>{f.note}</p>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

const ScoreInsightDrawer = ({
  type, data, onClose, onCategoryClick
}: {
  type: 'OVERALL' | 'SEMANTIC' | 'VISUAL'; data: UnifiedValidationData; onClose: () => void; onCategoryClick: (cat: string) => void;
}) => {
  const isOverall = type === 'OVERALL';
  const scopeMap = { OVERALL: '', SEMANTIC: 'semantic', VISUAL: 'visual' };
  const scope = scopeMap[type];

  const relevantChecks = isOverall ? data.checkSummary : data.checkSummary.filter(c => c.scope === scope);
  const relevantFindings = isOverall ? [] : data.findings.filter(f => 
    relevantChecks.some(rc => rc.check === f.checkId) && ['FAIL', 'MISSING', 'WARNING'].includes(f.status)
  );

  return (
    <div style={{ padding: 28, display: 'flex', flexDirection: 'column', height: '100%', overflowY: 'auto', fontFamily: "'Segoe UI', system-ui, sans-serif" }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 28 }}>
        <div>
          <h2 style={{ fontSize: 20, fontWeight: 800, color: JNJ.navy, margin: 0, letterSpacing: '-0.02em' }}>
            {type === 'OVERALL' ? 'Overall Score Breakdown' : type === 'SEMANTIC' ? 'Semantic Score Breakdown' : 'Visual Score Breakdown'}
          </h2>
          <p style={{ fontSize: 13, color: JNJ.textMid, margin: '6px 0 0', lineHeight: 1.4 }}>
            {type === 'OVERALL' ? 'Severity-weighted composite score' : type === 'SEMANTIC' ? 'Connections · Tables · Fields · Measures' : 'Filters · Visuals · Display · Formatting'}
          </p>
        </div>
        <button onClick={onClose} style={{ background: JNJ.slateLight, border: `1px solid ${JNJ.border}`, borderRadius: '50%', cursor: 'pointer', color: JNJ.text, padding: 6, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <X size={16} />
        </button>
      </div>

      <div style={{ flex: 1 }}>
        {isOverall ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
            <div style={{ padding: 20, background: JNJ.white, borderRadius: 10, border: `1px solid ${JNJ.border}`, boxShadow: '0 2px 8px rgba(0,0,0,0.02)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: JNJ.text }}>Semantic Contribution</span>
                <span style={{ fontSize: 13, fontWeight: 800, fontFamily: 'monospace', color: data.semanticScore === null ? JNJ.slate : scoreColor(data.semanticScore) }}>{data.semanticScore === null ? 'N/A' : `${data.semanticScore.toFixed(1)}%`}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 20 }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: JNJ.text }}>Visual Contribution</span>
                <span style={{ fontSize: 13, fontWeight: 800, fontFamily: 'monospace', color: data.visualScore === null ? JNJ.slate : scoreColor(data.visualScore) }}>{data.visualScore === null ? 'N/A' : `${data.visualScore.toFixed(1)}%`}</span>
              </div>
              
              <div style={{ height: 1, background: JNJ.border, margin: '16px 0' }} />
              
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
                <div>
                  <div style={{ fontSize: 28, fontWeight: 900, color: JNJ.green, lineHeight: 1 }}>{data.checkSummary.reduce((acc, c) => acc + c.passed, 0)}</div>
                  <div style={{ fontSize: 11, color: JNJ.textLight, fontWeight: 700, textTransform: 'uppercase', marginTop: 4 }}>Passed Checks</div>
                </div>
                <div>
                  <div style={{ fontSize: 28, fontWeight: 900, color: JNJ.red, lineHeight: 1 }}>{data.checkSummary.reduce((acc, c) => acc + c.failed, 0)}</div>
                  <div style={{ fontSize: 11, color: JNJ.textLight, fontWeight: 700, textTransform: 'uppercase', marginTop: 4 }}>Failed Checks</div>
                </div>
                <div>
                  <div style={{ fontSize: 28, fontWeight: 900, color: JNJ.amber, lineHeight: 1 }}>{data.checkSummary.reduce((acc, c) => acc + c.missing, 0)}</div>
                  <div style={{ fontSize: 11, color: JNJ.textLight, fontWeight: 700, textTransform: 'uppercase', marginTop: 4 }}>Missing Metadata</div>
                </div>
                <div>
                  <div style={{ fontSize: 28, fontWeight: 900, color: JNJ.orange, lineHeight: 1 }}>{data.gapsCount}</div>
                  <div style={{ fontSize: 11, color: JNJ.textLight, fontWeight: 700, textTransform: 'uppercase', marginTop: 4 }}>Identified Gaps</div>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 36 }}>
            <div>
              <h3 style={{ fontSize: 11, fontWeight: 800, color: JNJ.textLight, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 16 }}>Contributing Categories</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {relevantChecks.map(check => {
                  const pct = check.total > 0 ? (check.passed / check.total) * 100 : 0;
                  return (
                    <div 
                      key={check.check}
                      onClick={() => onCategoryClick(check.check)}
                      style={{ cursor: 'pointer', padding: '14px 16px', background: JNJ.white, border: `1px solid ${JNJ.border}`, borderRadius: 8, transition: 'all 0.2s ease', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}
                      onMouseEnter={(e) => { e.currentTarget.style.borderColor = JNJ.slate; e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.06)'; }}
                      onMouseLeave={(e) => { e.currentTarget.style.borderColor = JNJ.border; e.currentTarget.style.boxShadow = '0 1px 3px rgba(0,0,0,0.02)'; }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          {pct === 100 ? <CheckCircle2 size={14} color={JNJ.green} /> : <AlertTriangle size={14} color={JNJ.amber} />}
                          <span style={{ fontSize: 13, fontWeight: 600, color: JNJ.text }}>{check.label}</span>
                        </div>
                        <span style={{ fontSize: 13, fontWeight: 800, fontFamily: 'monospace', color: pct === 100 ? JNJ.green : pct >= 60 ? JNJ.amber : JNJ.red }}>{pct.toFixed(0)}%</span>
                      </div>
                      <div style={{ display: 'flex', gap: 3, height: 6 }}>
                        {Array.from({ length: 10 }).map((_, i) => {
                          const filled = (i + 1) * 10 <= pct;
                          const partial = !filled && i * 10 < pct;
                          return (
                            <div key={i} style={{ flex: 1, background: filled ? JNJ.slate : partial ? JNJ.textLight : JNJ.slateLight, borderRadius: 2 }} />
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div>
              <h3 style={{ fontSize: 11, fontWeight: 800, color: JNJ.textLight, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 16 }}>Score Impact Breakdown</h3>
              {relevantFindings.length === 0 ? (
                <p style={{ fontSize: 13, color: JNJ.textMid, fontStyle: 'italic', background: JNJ.slateLight, padding: 16, borderRadius: 8, border: `1px solid ${JNJ.border}` }}>No deductions in this category.</p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                  {relevantChecks.map(check => {
                    const checkFindings = relevantFindings.filter(f => f.checkId === check.check);
                    if (checkFindings.length === 0) return null;
                    return (
                      <div key={check.check}>
                        <div style={{ fontSize: 11, fontWeight: 800, color: JNJ.text, marginBottom: 8, textTransform: 'uppercase', paddingBottom: 6, borderBottom: `1px solid ${JNJ.border}` }}>{check.label}</div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                          {checkFindings.map(f => (
                            <div key={f.id} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, background: JNJ.slateLight, padding: '10px 12px', borderRadius: 6, border: `1px solid ${JNJ.border}` }}>
                              <Minus size={14} color={JNJ.textLight} style={{ flexShrink: 0, marginTop: 2 }} />
                              <div>
                                <p style={{ fontSize: 12, color: JNJ.text, margin: '0 0 4px', fontWeight: 600 }}>{f.title}</p>
                                <p style={{ fontSize: 11, color: JNJ.textMid, margin: 0 }}>
                                  <span style={{ fontWeight: 700 }}>Severity:</span> {f.severity} <span style={{ color: JNJ.slate, margin: '0 4px' }}>|</span> <span style={{ fontWeight: 700 }}>Impact:</span> {f.status}
                                </p>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default function SharedValidationReport({ data, ToolbarComponent }: Props) {
  const [query, setQuery] = useState('');
  const [activeCheckFilter, setActiveCheckFilter] = useState('ALL');
  const [statusFilter, setStatusFilter] = useState<'ALL' | VStatus>('ALL');
  const [page, setPage] = useState(1);
  const [activeDrawer, setActiveDrawer] = useState<'OVERALL' | 'SEMANTIC' | 'VISUAL' | null>(null);
  const findingsRef = React.useRef<HTMLDivElement>(null);
  const PAGE_SIZE = 20;

  const findings = data?.findings || [];
  const checkSummary = data?.checkSummary || [];

  const checkIds = useMemo(() => {
    const ids = Array.from(new Set(findings.map(f => f.checkId))).sort();
    return ['ALL', ...ids];
  }, [findings]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return findings.filter(f => {
      if (activeCheckFilter !== 'ALL' && f.checkId !== activeCheckFilter) return false;
      if (statusFilter !== 'ALL' && f.status !== statusFilter) return false;
      if (q && !JSON.stringify(f).toLowerCase().includes(q)) return false;
      return true;
    });
  }, [findings, activeCheckFilter, statusFilter, query]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageFindings = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const statusCounts = useMemo(() => {
    const c: Record<VStatus, number> = { PASS: 0, FAIL: 0, MISSING: 0, WARNING: 0, SKIP: 0 };
    findings.forEach(f => { c[f.status] = (c[f.status] ?? 0) + 1; });
    return c;
  }, [findings]);

  const cardBase: React.CSSProperties = {
    background: JNJ.white,
    border: `1px solid ${JNJ.border}`,
    borderRadius: 12,
    overflow: 'hidden',
    boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
  };

  const sectionLabel: React.CSSProperties = {
    fontSize: 10, fontWeight: 700, color: JNJ.textLight,
    textTransform: 'uppercase', letterSpacing: '0.08em', margin: '0 0 4px',
  };

  if (!data) return null;

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>
      {ToolbarComponent && <div style={{ marginBottom: 16 }}>{ToolbarComponent}</div>}
      
      {/* ── 3 Score cards ── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14, marginBottom: 16 }}>
        {[
          { type: 'OVERALL',  label: 'Overall Score',   score: data.overallScore,   verdict: data.verdict,         sub: 'Severity-weighted composite score' },
          { type: 'SEMANTIC', label: 'Semantic Score',  score: data.semanticScore,  verdict: data.semanticVerdict, sub: 'Connections · Tables · Fields · Measures' },
          { type: 'VISUAL',   label: 'Visual Score',    score: data.visualScore,    verdict: data.visualVerdict,   sub: 'Filters · Visuals · Display · Formatting' },
        ].map(({ type, label, score, verdict, sub }) => {
          const isNull = score === null;
          const color = isNull ? JNJ.slate : scoreColor(score as number);
          const vd = verdictStyle(verdict);
          const Trend = isNull ? Minus : (score as number) >= 60 ? TrendingUp : TrendingDown;
          return (
            <motion.button 
              key={label} 
              onClick={() => setActiveDrawer(type as any)}
              whileHover={{ y: -2, boxShadow: '0 6px 16px rgba(0,0,0,0.06)' }}
              style={{ ...cardBase, padding: '20px 22px', position: 'relative', textAlign: 'left', cursor: 'pointer', border: 'none', display: 'block', width: '100%' }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div style={{ flex: 1 }}>
                  <p style={sectionLabel}>{label}</p>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, margin: '6px 0 4px' }}>
                    <span style={{ fontSize: 38, fontWeight: 900, color: JNJ.text, fontFamily: 'monospace', lineHeight: 1 }}>
                      {isNull ? 'N/A' : (score as number).toFixed(1)}
                    </span>
                    {!isNull && <span style={{ fontSize: 20, color: JNJ.textLight, fontFamily: 'monospace', opacity: 0.8 }}>%</span>}
                  </div>
                  <p style={{ fontSize: 11, color: JNJ.textMid, margin: '0 0 10px', lineHeight: 1.4 }}>{sub}</p>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: 11, fontWeight: 700, padding: '3px 12px', borderRadius: 5,
                      background: vd.bg, color: vd.text, border: `1px solid ${vd.border}` }}>
                      {verdict}
                    </span>
                    <Trend size={14} color={color} />
                  </div>
                </div>
                <Gauge score={score} size={68} />
              </div>
              <div style={{ position: 'absolute', top: 12, right: 12, opacity: 0.4 }}>
                <MousePointerClick size={14} color={JNJ.textLight} />
              </div>
            </motion.button>
          );
        })}
      </div>

      {/* ── KPI strip ── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12, marginBottom: 20 }}>
        {[
          { label: 'Total Checks', value: data.totalChecks,    color: JNJ.navy,   icon: FileCheck2,    filter: 'ALL' },
          { label: 'Passed',       value: statusCounts.PASS,   color: JNJ.green,  icon: CheckCircle2,  filter: 'PASS' },
          { label: 'Failed',       value: statusCounts.FAIL,   color: JNJ.red,    icon: XCircle,       filter: 'FAIL' },
          { label: 'Missing',      value: statusCounts.MISSING,color: JNJ.amber,  icon: AlertTriangle, filter: 'MISSING' },
          { label: 'Gaps',         value: data.gapsCount,      color: JNJ.orange, icon: AlertTriangle, filter: null },
        ].map(({ label, value, color, icon: Icon, filter }) => (
          <motion.button 
            key={label}
            onClick={() => {
              if (filter !== null) {
                setStatusFilter(filter as any);
                setActiveCheckFilter('ALL'); // Reset check filter to show all in this status
                findingsRef.current?.scrollIntoView({ behavior: 'smooth' });
              }
            }}
            whileHover={filter !== null ? { y: -2, boxShadow: '0 4px 12px rgba(0,0,0,0.05)' } : {}}
            style={{ ...cardBase, padding: '14px 16px', textAlign: 'left', cursor: filter !== null ? 'pointer' : 'default', border: 'none', display: 'block', width: '100%' }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <p style={sectionLabel}>{label}</p>
              <div style={{ width: 26, height: 26, borderRadius: 6,
                background: JNJ.slateLight, border: `1px solid ${JNJ.border}`,
                display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Icon size={13} color={color} />
              </div>
            </div>
            <p style={{ fontSize: 30, fontWeight: 900, color: JNJ.text, fontFamily: 'monospace', margin: 0, lineHeight: 1 }}>
              {value.toLocaleString()}
            </p>
          </motion.button>
        ))}
      </div>

      {/* ── Check summary ── */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <ShieldCheck size={15} color={JNJ.red} />
          <h2 style={{ fontSize: 14, fontWeight: 700, color: JNJ.text, margin: 0 }}>Check Summary</h2>
          <span style={{ fontSize: 11, color: JNJ.textLight, marginLeft: 4 }}>
            — {checkSummary.length} check categories · click any card to expand
          </span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 12 }}>
          {checkSummary.map(row => <CheckCard key={row.check} row={row} />)}
        </div>
      </div>

      {/* ── Detailed Findings ── */}
      <div style={{ ...cardBase, scrollMarginTop: 20 }} ref={findingsRef}>
        {/* Toolbar */}
        <div style={{ padding: '16px 20px', borderBottom: `1px solid ${JNJ.border}`,
          display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 2 }}>
              <Activity size={14} color={JNJ.red} />
              <h2 style={{ fontSize: 14, fontWeight: 700, color: JNJ.text, margin: 0 }}>Detailed Findings</h2>
            </div>
            <p style={{ fontSize: 11, color: JNJ.textLight, margin: 0 }}>
              {filtered.length.toLocaleString()} of {findings.length.toLocaleString()} checks · expand any row to compare actual vs expected
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <div style={{ position: 'relative' }}>
              <Search size={13} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: JNJ.textLight }} />
              <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search findings…"
                style={{ paddingLeft: 30, paddingRight: 12, height: 34, borderRadius: 7,
                  border: `1px solid ${JNJ.border}`, background: JNJ.slateLight,
                  color: JNJ.text, fontSize: 13, outline: 'none', width: 210 }} />
            </div>
            <select value={statusFilter} onChange={e => setStatusFilter(e.target.value as any)}
              style={{ height: 34, borderRadius: 7, border: `1px solid ${JNJ.border}`,
                background: JNJ.slateLight, color: JNJ.textMid, fontSize: 12,
                padding: '0 10px', outline: 'none' }}>
              {(['ALL','PASS','FAIL','MISSING','WARNING','SKIP'] as const).map(s =>
                <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
        </div>

        {/* Check ID filter chips */}
        <div style={{ padding: '10px 16px', borderBottom: `1px solid ${JNJ.border}`,
          display: 'flex', gap: 6, overflowX: 'auto' }}>
          {checkIds.map(id => (
            <button key={id} onClick={() => setActiveCheckFilter(id)}
              style={{ padding: '4px 12px', borderRadius: 6, whiteSpace: 'nowrap', fontFamily: 'monospace',
                fontSize: 11, fontWeight: 700, cursor: 'pointer',
                border: `1px solid ${activeCheckFilter === id ? JNJ.slate : JNJ.border}`,
                background: activeCheckFilter === id ? JNJ.slateLight : JNJ.white,
                color: activeCheckFilter === id ? JNJ.text : JNJ.textMid }}>
              {id}
            </button>
          ))}
        </div>

        {/* Status pills */}
        <div style={{ padding: '8px 16px', borderBottom: `1px solid ${JNJ.border}`,
          display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {(['PASS','FAIL','MISSING','WARNING','SKIP'] as VStatus[]).map(s => {
            const cfg = statusConfig[s];
            const count = statusCounts[s];
            if (!count) return null;
            const active = statusFilter === s;
            return (
              <button key={s} onClick={() => setStatusFilter(active ? 'ALL' : s)}
                style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '4px 11px',
                  borderRadius: 20, cursor: 'pointer', fontSize: 11, fontWeight: 700,
                  border: `1px solid ${active ? cfg.text : cfg.border}`,
                  background: active ? cfg.bg : JNJ.white,
                  color: cfg.text }}>
                <cfg.icon size={10} /> {s}
                <span style={{ fontFamily: 'monospace', marginLeft: 3 }}>{count}</span>
              </button>
            );
          })}
        </div>

        {/* Findings list */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {pageFindings.length === 0 ? (
            <div style={{ padding: 48, textAlign: 'center', color: JNJ.textLight, fontSize: 13 }}>
              No findings match the current filters.
            </div>
          ) : (
            pageFindings.map(f => <FindingRow key={f.id} f={f} />)
          )}
        </div>

        {/* Pagination */}
        <div style={{ padding: '12px 20px', borderTop: `1px solid ${JNJ.border}`,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          background: JNJ.slateLight }}>
          <span style={{ fontSize: 12, color: JNJ.textMid, fontFamily: 'monospace' }}>
            {((page - 1) * PAGE_SIZE + 1).toLocaleString()}–{Math.min(page * PAGE_SIZE, filtered.length).toLocaleString()} of {filtered.length.toLocaleString()}
          </span>
          <div style={{ display: 'flex', gap: 5 }}>
            {[
              { label: '«', action: () => setPage(1),             disabled: page === 1 },
              { label: '‹', action: () => setPage(p => p - 1),   disabled: page === 1 },
              { label: `${page} / ${totalPages}`, action: () => {}, disabled: true, active: true },
              { label: '›', action: () => setPage(p => p + 1),   disabled: page === totalPages },
              { label: '»', action: () => setPage(totalPages),    disabled: page === totalPages },
            ].map(({ label, action, disabled, active }, i) => (
              <button key={i} onClick={action} disabled={disabled}
                style={{ padding: '5px 11px', borderRadius: 6, fontSize: 12,
                  fontFamily: 'monospace', fontWeight: 600,
                  border: `1px solid ${active ? JNJ.slate : JNJ.border}`,
                  background: active ? JNJ.slateLight : JNJ.white,
                  color: disabled && !active ? JNJ.textLight : active ? JNJ.text : JNJ.text,
                  cursor: disabled ? 'not-allowed' : 'pointer' }}>
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Sliding Insight Drawer ── */}
      <AnimatePresence>
        {activeDrawer && (
          <motion.div
            initial={{ x: '100%', opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: '100%', opacity: 0 }}
            transition={{ type: 'spring', damping: 28, stiffness: 220 }}
            style={{
              position: 'fixed',
              top: 0,
              right: 0,
              bottom: 0,
              width: 500,
              background: '#f1f5f9', // subtle backdrop for the drawer itself
              boxShadow: '-10px 0 40px rgba(0,0,0,0.1)',
              borderLeft: `1px solid ${JNJ.border}`,
              zIndex: 100,
            }}
          >
            <div style={{ background: JNJ.white, height: '100%', borderRadius: '16px 0 0 16px', overflow: 'hidden' }}>
              <ScoreInsightDrawer 
                type={activeDrawer}
                data={data}
                onClose={() => setActiveDrawer(null)}
                onCategoryClick={(cat) => {
                  setActiveCheckFilter(cat);
                  findingsRef.current?.scrollIntoView({ behavior: 'smooth' });
                }}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
