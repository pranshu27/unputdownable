import React, { useEffect, useRef, useState, useMemo } from 'react';
import axios from 'axios';
import { useOutletContext } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import { Loader2, RefreshCw, Download, XCircle, ShieldCheck, AlertTriangle } from 'lucide-react';
import { DataModel } from '../../data/sampleModel';
import ContentCard from '../../core/CardContent/CardContent.tsx';
import FileWorkspaceHeader from '../../core/FileWorkspaceHeader.tsx';
import { getUploadedFileByName } from '../../utils/uploadedFileContext.ts';
import {
  startJob, advanceStep, updateJobProgress, addJobLog,
  completeJob, failJob, saveJobResult, loadJobResult,
  getJobResultMeta, clearJobResult
} from '../../utils/jobTrackerSlice.ts';
import { triggerReValidationBackground } from '../../services/ValidationJobRunner.ts';

import SharedValidationReport, { 
  UnifiedValidationData, VStatus, UnifiedFinding, UnifiedCheckRow 
} from './SharedValidationReport.tsx';

interface Props { model: DataModel; isTab?: boolean; }

const VALIDATION_API_URL = 'http://20.72.80.42:8001/validation/validate';
const JNJ = { red: '#c8102e', redLight: '#fdf2f4', redMid: '#f5cdd3', text: '#0f172a', textLight: '#94a3b8', border: '#e2e8f0', white: '#ffffff' };

/* ─── helpers ─────────────────────────────────────────────────────── */
const getActiveFileName = () => {
  try {
    const details = JSON.parse(localStorage.getItem('fileDetails') || '{}');
    return localStorage.getItem('activePowerBiReportFile') || details?.fileName || '';
  } catch { return localStorage.getItem('activePowerBiReportFile') || ''; }
};

const detectToolId = (name: string) => {
  const n = (name || '').toLowerCase();
  if (n.endsWith('.pbix')) return 'powerbi';
  if (n.endsWith('.twb') || n.endsWith('.twbx')) return 'tableau-workbook';
  if (n.endsWith('.qvf') || n.endsWith('.qvw')) return 'qlik';
  return 'powerbi';
};

const normalizeStatus = (v: any): VStatus => {
  const s = String(v || '').toUpperCase();
  if (s === 'SKIP') return 'SKIP';
  if (s.includes('MISSING')) return 'MISSING';
  if (s.includes('WARN')) return 'WARNING';
  if (s.includes('FAIL') || s.includes('ERROR')) return 'FAIL';
  if (s.includes('PASS') || s.includes('OK')) return 'PASS';
  return 'WARNING';
};

const flattenFindings = (allResults: any[]): UnifiedFinding[] =>
  allResults.map((item, i) => ({
    id:          `${item.check_id || item.attribute || 'check'}-${i}`,
    checkId:     item.check_id || item.category || 'General',
    category:    item.check_id || item.category || 'General',
    status:      normalizeStatus(item.status || item.severity),
    title:       item.attribute || item.object || item.title || item.check_name || `Check ${i + 1}`,
    description: item.note || item.issue || item.description || item.message || '',
    severity:    item.severity || item.status || '',
    sourceValue: item.source_value || item.expected,
    jsonValue:   item.json_value || item.actual,
    note:        item.note || item.issue,
  }));

const normaliseResult = (inputRaw: any): UnifiedValidationData | null => {
  if (!inputRaw) return null;
  const raw = Array.isArray(inputRaw) ? inputRaw[0] ?? {} : inputRaw ?? {};
  
  const allResults = Array.isArray(raw.report?.results) ? raw.report.results : Array.isArray(raw.report?.all_results) ? raw.report.all_results : Array.isArray(raw.all_results) ? raw.all_results : [];
  
  const rawCheckSummary = raw.check_summary || raw.report?.check_summary;
  let checkSummary = Array.isArray(rawCheckSummary) ? rawCheckSummary : [];
  
  const scoreBreakdown = raw.score_breakdown || raw.report?.score_breakdown;
  
  if (checkSummary.length === 0 && scoreBreakdown) {
    const buildSummary = (checks: any, scope: string) => {
      const arr = Array.isArray(checks) ? checks : Array.isArray(checks?.checks) ? checks.checks : [];
      if (arr.length === 0) return [];
      const mapping: Record<string, string> = {
        'T1': 'Database Connection', 'T2': 'Tables & Joins', 'T3': 'Columns & Data Types',
        'T4': 'Filters', 'T5': 'Hierarchies', 'T6': 'Dashboard Layout',
        'T7': 'Dashboard Actions', 'T10': 'Worksheets & Chart Types',
        'General': 'General Checks'
      };
      return arr.map((c: any) => ({
        check: c.category || c.check_id || 'General',
        label: mapping[c.category || c.check_id] || c.category || c.check_id || 'General',
        description: c.description || `Validation checks for ${c.category || c.check_id}`,
        scope: scope,
        score: c.score || 0,
        verdict: (c.score || 0) >= 80 ? 'PASS' : 'FAIL',
        passed: c.passed || 0,
        failed: c.failed || 0,
        missing: c.missing || 0,
        total: c.total || 0,
      }));
    };

    if (Array.isArray(scoreBreakdown)) {
      checkSummary = buildSummary(scoreBreakdown, 'general');
    } else {
      checkSummary = [
        ...buildSummary(scoreBreakdown.semantic, 'semantic'),
        ...buildSummary(scoreBreakdown.visual, 'visual'),
        ...buildSummary(scoreBreakdown.dataset, 'dataset'),
        ...buildSummary(scoreBreakdown.metadata, 'metadata'),
        ...buildSummary(scoreBreakdown.kpi, 'kpi'),
        ...buildSummary(scoreBreakdown.dax, 'dax'),
        ...buildSummary(scoreBreakdown.relationship, 'relationship')
      ];
    }
  }

  // Fallback: If still empty but we have results, dynamically generate the summary
  if (checkSummary.length === 0 && allResults.length > 0) {
    const categoryGroups: Record<string, any[]> = {};
    allResults.forEach((item: any) => {
      const cat = item.check_id || item.category || 'General';
      if (!categoryGroups[cat]) categoryGroups[cat] = [];
      categoryGroups[cat].push(item);
    });

    const mapping: Record<string, string> = {
      'T1': 'Database Connection', 'T2': 'Tables & Joins', 'T3': 'Columns & Data Types',
      'T4': 'Filters', 'T5': 'Hierarchies', 'T6': 'Dashboard Layout',
      'T7': 'Dashboard Actions', 'T10': 'Worksheets & Chart Types',
      'General': 'General Checks'
    };

    checkSummary = Object.keys(categoryGroups).map(cat => {
      const checks = categoryGroups[cat];
      const passed = checks.filter(c => normalizeStatus(c.status || c.severity) === 'PASS').length;
      const failed = checks.filter(c => normalizeStatus(c.status || c.severity) === 'FAIL').length;
      const missing = checks.filter(c => normalizeStatus(c.status || c.severity) === 'MISSING').length;
      const total = checks.length;
      const score = total > 0 ? (passed / total) * 100 : 0;
      
      return {
        check: cat,
        label: mapping[cat] || cat,
        description: `Detailed findings for ${cat} checks`,
        scope: 'general',
        score: score,
        verdict: score >= 80 ? 'PASS' : 'FAIL',
        passed,
        failed,
        missing,
        total
      };
    });
  }

  return {
    workbookId:      raw.workbook_id || raw.report?.workbook_id || '',
    timestamp:       raw.timestamp || raw.report?.timestamp || '',
    overallScore:    raw.score ?? raw.overall_score ?? raw.report?.overall_score ?? null,
    semanticScore:   raw.semantic_score ?? raw.report?.semantic_score ?? raw.score_breakdown?.semantic?.score ?? null,
    visualScore:     raw.visual_score ?? raw.report?.visual_score ?? raw.score_breakdown?.visual?.score ?? null,
    verdict:         String(raw.verdict ?? raw.report?.overall_verdict ?? 'PENDING').toUpperCase(),
    semanticVerdict: String(raw.semantic_verdict ?? raw.score_breakdown?.semantic?.verdict ?? 'PENDING').toUpperCase(),
    visualVerdict:   String(raw.visual_verdict ?? raw.score_breakdown?.visual?.verdict ?? 'PENDING').toUpperCase(),
    totalChecks:     Number(raw.total_checks ?? raw.report?.total_checks ?? checkSummary.reduce((acc, c) => acc + c.total, 0)),
    gapsCount:       Number(raw.gaps_count ?? raw.report?.gaps_count ?? 0),
    checkSummary,
    findings:        flattenFindings(allResults),
  };
};

/* ═══════════════════════════════════════════════════════════════════
   SKELETON LOADER
════════════════════════════════════════════════════════════════════ */
const ValidationSkeleton = ({ statusMsg }: { statusMsg: string; progress?: number }) => (
  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '65vh', height: '100%', background: JNJ.white, border: `1px solid ${JNJ.border}`, borderRadius: 12, padding: 40 }}>
    <div style={{ position: 'relative', width: 64, height: 64, display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 24 }}>
      <Loader2 size={48} color={JNJ.red} className="animate-spin" />
    </div>
    <h3 style={{ fontSize: 18, fontWeight: 700, color: JNJ.text, margin: '0 0 8px' }}>Validating Dataset...</h3>
    <p style={{ fontSize: 14, color: JNJ.textMid, margin: 0 }}>{statusMsg}</p>
  </div>
);

/* ═══════════════════════════════════════════════════════════════════
   MAIN COMPONENT
════════════════════════════════════════════════════════════════════ */
export default function ValidationReport({ model, isTab = false }: Props) {
  const { sideNavWidth } = useOutletContext<{ sideNavWidth: number }>();
  const dispatch = useDispatch();
  const activeFileName = getActiveFileName();
  const activeToolId   = detectToolId(activeFileName);
  const activeFile     = getUploadedFileByName(activeFileName);
  const startedRef     = useRef(false);

  const [isRunning, setIsRunning]   = useState(false);
  const [progress,  setProgress]    = useState(0);
  const [statusMsg, setStatusMsg]   = useState('Ready');
  const [error,     setError]       = useState('');
  const [rawResult, setRawResult]   = useState<any>(null);

  const data = useMemo(() => normaliseResult(rawResult), [rawResult]);

  /* ── Load cached results on mount ── */
  useEffect(() => {
    if (!activeFileName) return;
    
    // Check if the file is newer than the cache
    if (activeFile && activeFile.lastModified) {
      const meta = getJobResultMeta('validation', activeFileName);
      if (meta && meta.savedAt) {
        const fileTime = new Date(activeFile.lastModified).getTime();
        const savedTime = new Date(meta.savedAt).getTime();
        // If file was modified on disk AFTER the validation was saved, the cache is stale
        if (fileTime > savedTime) {
          clearJobResult('validation', activeFileName);
          return; // Let the other useEffect handle running the new validation
        }
      }
    }

    const cached = loadJobResult('validation', activeFileName);
    if (cached) {
      setRawResult(cached);
      setProgress(100);
      setStatusMsg('Complete (cached)');
    }
  }, [activeFileName, activeFile]);

  const runningJob = useSelector((state: any) => {
    if (!state?.jobTracker?.jobs) return undefined;
    return Object.values(state.jobTracker.jobs).find(
      (j: any) => j.type === 'validation' && j.fileName === activeFileName
    ) as any;
  });

  // Sync with background job state
  useEffect(() => {
    if (!runningJob) return;
    if (runningJob.status === 'running' || runningJob.status === 'polling') {
      setIsRunning(true);
      setProgress(runningJob.progress || 5);
      setStatusMsg(runningJob.statusMessage || 'Validating in background...');
    } else if (runningJob.status === 'success' || runningJob.status === 'complete') {
      const cached = loadJobResult('validation', activeFileName);
      if (cached) {
        setRawResult(cached);
        setIsRunning(false);
        setProgress(100);
        setStatusMsg('Complete');
      }
    } else if (runningJob.status === 'error') {
      setIsRunning(false);
      setError(runningJob.errorMessage || 'Validation failed');
    }
  }, [runningJob, activeFileName]);

  /* ── API call ── */
  const runValidation = async () => {
    if (!activeFileName) { setError('No active file found. Open a file from the workspace first.'); return; }

    setIsRunning(true); setProgress(5); setError(''); setRawResult(null);
    setStatusMsg('Preparing validation payload…');

    // Trigger the background service which handles the rest, 
    // and let the useSelector handle UI updates
    triggerReValidationBackground(activeFile || null, activeToolId, activeFileName).catch((err) => {
      setIsRunning(false);
      setError(err?.message || 'Failed to start validation');
    });
  };

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    const cached = loadJobResult('validation', activeFileName);
    if (!cached) runValidation();
  }, []);

  const exportCSV = () => {
    if (!data?.findings.length) return;
    const header = ['CheckID','Status','Severity','Title','SourceValue','JsonValue','Note'];
    const rows = data.findings.map(f => [f.checkId, f.status, f.severity, f.title, f.sourceValue||'', f.jsonValue||'', f.note||'']);
    const csv = [header, ...rows].map(r => r.map(c => `"${String(c).replace(/"/g,'""')}"`).join(',')).join('\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    a.download = `validation-${activeFileName}.csv`;
    a.click();
  };

  const Toolbar = (
    <div>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 16, paddingBottom: 16, borderBottom: `1px solid ${JNJ.border}` }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 16 }}>
          {data?.workbookId && <span style={{ fontSize: 12, color: JNJ.textLight, fontFamily: 'monospace' }}>ID: {data.workbookId}</span>}
          {data?.timestamp && (
            <>
              <span style={{ fontSize: 12, color: JNJ.textLight }}>|</span>
              <span style={{ fontSize: 12, color: JNJ.textLight }}>{new Date(data.timestamp).toLocaleString()}</span>
            </>
          )}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={runValidation} disabled={isRunning}
            style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px', borderRadius: 4, background: JNJ.white, border: `1px solid ${JNJ.border}`, color: JNJ.text, fontSize: 11, fontWeight: 600, cursor: isRunning ? 'not-allowed' : 'pointer', opacity: isRunning ? 0.65 : 1 }}>
            {isRunning ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
            {isRunning ? 'Running…' : 'Re-run Validation'}
          </button>
          <button onClick={exportCSV} disabled={!data?.findings.length}
            style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px', borderRadius: 4, background: JNJ.white, border: `1px solid ${JNJ.border}`, color: data?.findings.length ? JNJ.text : JNJ.textLight, fontSize: 11, fontWeight: 600, cursor: data?.findings.length ? 'pointer' : 'not-allowed' }}>
            <Download size={12} /> Export CSV
          </button>
        </div>
      </div>
    </div>
  );

  const InnerContent = (
    <div style={{ fontFamily: "'Segoe UI', system-ui, sans-serif", paddingBottom: 40, padding: isTab ? 24 : 0, display: 'flex', flexDirection: 'column', minHeight: '100%' }}>
      {isRunning && !data && <ValidationSkeleton statusMsg={statusMsg} />}

      {!isRunning && !data && !error && (
        <div style={{ padding: 60, textAlign: 'center', background: JNJ.white, border: `1px solid ${JNJ.border}`, borderRadius: 12, marginTop: 20 }}>
          <ShieldCheck size={48} color={JNJ.slate} style={{ margin: '0 auto 16px', opacity: 0.5 }} />
          <h2 style={{ fontSize: 18, fontWeight: 700, color: JNJ.text, margin: '0 0 8px' }}>Validation Not Run</h2>
          <p style={{ fontSize: 13, color: JNJ.textMid, maxWidth: 400, margin: '0 auto 24px' }}>
            Run the reverse engineering validation API to compare this dataset against Power BI formatting and syntax rules.
          </p>
        </div>
      )}

      {error && (
        <div style={{ padding: 20, background: JNJ.redLight, border: `1px solid ${JNJ.redMid}`, borderRadius: 12, color: JNJ.red, fontSize: 13, display: 'flex', alignItems: 'center', gap: 12, marginTop: 20 }}>
          <AlertTriangle size={20} />
          <span style={{ fontWeight: 600 }}>{error}</span>
        </div>
      )}

      {data && <SharedValidationReport data={data} ToolbarComponent={Toolbar} />}
    </div>
  );

  if (isTab) return InnerContent;
  return (
    <ContentCard heading={null} sideNavWidth={sideNavWidth} headerComponent={<FileWorkspaceHeader pageTitle="Validation Report" />}>
      {InnerContent}
    </ContentCard>
  );
}