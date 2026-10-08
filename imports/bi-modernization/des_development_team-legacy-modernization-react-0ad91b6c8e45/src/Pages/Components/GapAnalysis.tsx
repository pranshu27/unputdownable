import React, { useEffect, useMemo, useRef, useState } from 'react';
import { DataModel } from '../../data/sampleModel';
import ContentCard from '../../core/CardContent/CardContent.tsx';
import FileWorkspaceHeader from '../../core/FileWorkspaceHeader.tsx';
import {
  Sparkles,
  ArrowRight,
  AlertTriangle,
  Check,
  ChevronDown,
  Database,
  FileSpreadsheet,
  Loader2,
  Search,
  UploadCloud,
  X,
  TrendingUp,
  Target,
  BarChart2,
  CheckCircle2,
} from 'lucide-react';
import { useOutletContext } from 'react-router-dom';
import { useNavigate } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import {
  startJob, advanceStep, addJobLog,
  completeJob, failJob, saveJobResult, loadJobResult, clearJobResult,
  selectJob,
} from '../../utils/jobTrackerSlice.ts';
import { fetchPowerBiReport, listPowerBiReports, ReportListItem } from '../../services/powerbiReports.ts';

interface Props {
  model: DataModel;
}

interface UploadedFileEntry {
  fileName: string;
}

type GapRow = Record<string, any>;

const GAP_API_URL = 'http://20.72.80.42:8001/gapanalysis/';
const NAVY = '#003087';

const getToolName = (fileName: string) => {
  const normalized = String(fileName || '').toLowerCase();
  if (normalized.endsWith('.pbix')) return 'powerbi';
  if (normalized.endsWith('.twb') || normalized.endsWith('.twbx')) return 'tableau-workbook';
  return 'powerbi';
};

const readUploadedFiles = (): UploadedFileEntry[] => {
  try {
    const rawExisting = localStorage.getItem('existingReports');
    const existingFiles = rawExisting ? JSON.parse(rawExisting) : [];
    if (Array.isArray(existingFiles) && existingFiles.length > 0) {
      return existingFiles.filter((entry) => entry?.fileName);
    }
  } catch {
    // ignore
  }
  try {
    const rawPendingJob = localStorage.getItem('powerbiPendingJob');
    const pendingJob = rawPendingJob ? JSON.parse(rawPendingJob) : null;
    const pendingFiles = Array.isArray(pendingJob?.files)
      ? pendingJob.files
          .map((entry: any) => ({ fileName: entry?.file_name }))
          .filter((entry: UploadedFileEntry) => entry.fileName)
      : [];
    if (pendingFiles.length > 0) return pendingFiles;
  } catch {
    // ignore
  }
  const activeFile = localStorage.getItem('activePowerBiReportFile');
  return activeFile ? [{ fileName: activeFile }] : [];
};

const unwrapReport = (report: any) => report?.result || report?.data || report?.report || report || {};

const uniqueBy = <T,>(items: T[], keyFn: (item: T) => string) => {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = keyFn(item);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
};

const buildConsolidatedModel = (reports: any[], selectedFiles: string[]) => {
  const models = reports.map(unwrapReport);
  const firstModel = models[0] || {};

  const dataSources = uniqueBy(
    models.flatMap((item) => Array.isArray(item.data_sources) ? item.data_sources : []),
    (item: any) => item.id || `${item.name || ''}-${item.path || ''}`
  );
  const tables = uniqueBy(
    models.flatMap((item) => Array.isArray(item.tables) ? item.tables : []),
    (item: any) => item.id || item.name || JSON.stringify(item)
  );
  const relationships = uniqueBy(
    models.flatMap((item) => Array.isArray(item.relationships) ? item.relationships : []),
    (item: any) => item.id || `${item.left_table_id}-${item.left_column}-${item.right_table_id}-${item.right_column}`
  );
  const calculations = uniqueBy(
    models.flatMap((item) => Array.isArray(item.calculations) ? item.calculations : []),
    (item: any) => item.id || item.name || JSON.stringify(item)
  );
  const visualizations = uniqueBy(
    models.flatMap((item) =>
      Array.isArray(item.visualizations)
        ? item.visualizations
        : Array.isArray(item.visualization_fields)
          ? item.visualization_fields
          : []
    ),
    (item: any) => item.id || item.query_ref || `${item.page || ''}-${item.visual_type || ''}-${item.table || ''}-${item.column || ''}`
  );

  return {
    schema_version: firstModel.schema_version || '1.0',
    model_id: firstModel.model_id || firstModel.report_id || `gap-${Date.now()}`,
    name: selectedFiles.join(' + '),
    extracted_at: firstModel.extracted_at || firstModel.completed_at || new Date().toISOString(),
    data_sources: dataSources,
    tables,
    relationships,
    calculations,
    visualizations,
  };
};

const statusTone = (status: string) => {
  const normalized = String(status || '').toLowerCase();
  if (normalized.includes('missing')) return { bg: '#FEF2F2', text: '#B91C1C', border: '#FECACA' };
  if (normalized.includes('conflict') || normalized.includes('mismatch')) return { bg: '#FFFBEB', text: '#B45309', border: '#FDE68A' };
  return { bg: '#F0FDF4', text: '#15803D', border: '#BBF7D0' };
};

export default function GapAnalysis({ model }: Props) {
  const navigate = useNavigate();
  const { sideNavWidth } = useOutletContext<{ sideNavWidth: number }>();
  const inputRef = useRef<HTMLInputElement>(null);
  const [targetFile, setTargetFile] = useState<File | null>(null);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFileEntry[]>([]);
  const dispatch = useDispatch();
  const gapJob = useSelector(selectJob('gap-analysis'));
  const isJobRunning = gapJob?.status === 'running' || gapJob?.status === 'polling';
  const [reports, setReports] = useState<ReportListItem[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [isSelectorOpen, setIsSelectorOpen] = useState(false);
  const [isLoadingFiles, setIsLoadingFiles] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<any>(null);
  const [query, setQuery] = useState('');

  const effectiveIsGenerating = isGenerating || isJobRunning;

  const refreshFiles = async () => {
    setIsLoadingFiles(true);
    const files = readUploadedFiles();
    setUploadedFiles(files);
    setSelectedFiles((current) => current.length ? current : files.map((entry) => entry.fileName));
    const tools = Array.from(new Set(files.map((entry) => getToolName(entry.fileName))));
    const reportGroups = await Promise.all(tools.map((tool) => listPowerBiReports(tool).catch(() => [])));
    setReports(reportGroups.flat());
    setIsLoadingFiles(false);
  };

  useEffect(() => {
    const activeFile = localStorage.getItem('activePowerBiReportFile') || '';
    if (activeFile && !isJobRunning) {
      const cached = loadJobResult('gap-analysis', activeFile);
      if (cached) setResult(cached);
    }
    refreshFiles();
  }, []);

  const selectedReportsMeta = useMemo(() => {
    return selectedFiles.map((fileName) => reports.find((report) => report.file_name === fileName));
  }, [reports, selectedFiles]);

  const selectedCounts = useMemo(() => {
    const currentModel = {
      data_sources: model.data_sources || [],
      tables: model.tables || [],
      relationships: model.relationships || [],
      calculations: model.calculations || [],
    };
    return {
      sources: currentModel.data_sources.length,
      tables: currentModel.tables.length,
      relationships: currentModel.relationships.length,
      calculations: currentModel.calculations.length,
    };
  }, [model]);

  const rows: GapRow[] = Array.isArray(result?.gap_analysis) ? result.gap_analysis : [];
  const filteredRows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter((row) => JSON.stringify(row).toLowerCase().includes(needle));
  }, [query, rows]);

  const toggleFile = (fileName: string) => {
    setSelectedFiles((current) =>
      current.includes(fileName)
        ? current.filter((item) => item !== fileName)
        : [...current, fileName]
    );
  };

  const generateGapAnalysis = async () => {
    if (!targetFile) {
      setError('Upload the target schema CSV before running gap analysis.');
      return;
    }
    if (selectedFiles.length === 0) {
      setError('Select at least one processed source report.');
      return;
    }

    setIsGenerating(true);
    setError('');
    setResult(null);

    const activeFile = localStorage.getItem('activePowerBiReportFile') || selectedFiles[0] || '';
    clearJobResult('gap-analysis', activeFile);
    dispatch(startJob({ type: 'gap-analysis', fileName: activeFile, estimatedTotalMs: 600000 }));

    try {
      dispatch(advanceStep({ type: 'gap-analysis', stepIndex: 0 }));
      dispatch(advanceStep({ type: 'gap-analysis', stepIndex: 1, statusMessage: 'Fetching source reports…' }));
      const sourceReports = await Promise.all(
        selectedFiles.map((fileName, index) => {
          const meta = selectedReportsMeta[index];
          return fetchPowerBiReport(fileName, meta?.tool_type || getToolName(fileName), {
            reportId: meta?.report_id,
          });
        })
      );
      const consolidatedPayload = buildConsolidatedModel(sourceReports, selectedFiles);
      dispatch(addJobLog({ type: 'gap-analysis', message: `Consolidated ${sourceReports.length} reports` }));
      dispatch(advanceStep({ type: 'gap-analysis', stepIndex: 2, statusMessage: 'Preparing upload payload…' }));

      const serializedPayload = JSON.stringify(consolidatedPayload);
      if (!serializedPayload || serializedPayload.length === 0) {
        throw new Error('Failed to serialize consolidated payload');
      }

      const formData = new FormData();
      formData.append('file', serializedPayload);
      formData.append('target_model', targetFile, targetFile.name);

      dispatch(advanceStep({ type: 'gap-analysis', stepIndex: 3, statusMessage: 'Running gap analysis API…' }));
      const response = await fetch(GAP_API_URL, {
        method: 'POST',
        headers: { accept: 'application/json' },
        body: formData,
      });

      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || `Gap analysis failed (${response.status})`);
      }

      dispatch(advanceStep({ type: 'gap-analysis', stepIndex: 4, statusMessage: 'Processing results…' }));
      const data = await response.json();
      const finalResult = { ...data, consolidated_payload: consolidatedPayload };
      setResult(finalResult);
      saveJobResult('gap-analysis', activeFile, finalResult);
      dispatch(completeJob({ type: 'gap-analysis', statusMessage: 'Gap analysis complete' }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unable to generate gap analysis.';
      setError(msg);
      dispatch(failJob({ type: 'gap-analysis', errorMessage: msg }));
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <ContentCard
      heading={null}
      sideNavWidth={sideNavWidth}
      headerComponent={<FileWorkspaceHeader pageTitle="Gap Analysis" />}
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
        {/* ── Analyst Toolbar ── */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            padding: '10px 16px',
            borderBottom: '1px solid #cbd5e1',
            backgroundColor: '#ffffff',
            flexShrink: 0,
            flexWrap: 'wrap',
          }}
        >
          {/* Step 1: Source Report */}
          <div style={{ position: 'relative' }}>
            <div
              style={{
                fontSize: '9px', fontWeight: 800, textTransform: 'uppercase',
                letterSpacing: '0.08em', color: NAVY, marginBottom: 3,
              }}
            >
              Step 1 · Legacy Reports
            </div>
            <button
              onClick={() => setIsSelectorOpen((o) => !o)}
              style={{
                display: 'flex', alignItems: 'center', gap: 8, padding: '6px 12px',
                background: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '8px',
                fontSize: '11.5px', fontWeight: 700, color: '#475569',
                cursor: 'pointer', minWidth: '200px',
              }}
            >
              <Database size={13} style={{ color: NAVY }} />
              <span style={{ flex: 1, textAlign: 'left', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {selectedFiles.length === 0
                  ? 'Select source reports…'
                  : `${selectedFiles.length} report${selectedFiles.length > 1 ? 's' : ''} selected`}
              </span>
              <ChevronDown size={12} style={{ opacity: 0.6, transform: isSelectorOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s' }} />
            </button>
            {isSelectorOpen && (
              <div
                style={{
                  position: 'absolute', top: 'calc(100% + 4px)', left: 0, zIndex: 1000,
                  background: '#fff', border: '1px solid #cbd5e1', borderRadius: '8px',
                  boxShadow: '0 8px 24px rgba(0,0,0,0.12)', width: '240px', maxHeight: '200px', overflowY: 'auto',
                }}
              >
                {isLoadingFiles && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px', fontSize: '11.5px', color: '#64748b' }}>
                    <Loader2 size={13} className="animate-spin" /> Loading…
                  </div>
                )}
                {!isLoadingFiles && uploadedFiles.length === 0 && (
                  <div style={{ padding: '10px 12px', fontSize: '11.5px', color: '#94a3b8' }}>No uploaded files found</div>
                )}
                {uploadedFiles.map((entry) => {
                  const checked = selectedFiles.includes(entry.fileName);
                  return (
                    <button
                      key={entry.fileName}
                      onClick={() => toggleFile(entry.fileName)}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 10,
                        width: '100%', padding: '8px 12px', textAlign: 'left',
                        background: 'transparent', border: 'none', cursor: 'pointer',
                        fontSize: '11.5px', fontWeight: 500, color: '#334155',
                      }}
                    >
                      <span
                        style={{
                          display: 'grid', placeItems: 'center', width: 16, height: 16,
                          borderRadius: 3, border: checked ? `2px solid ${NAVY}` : '2px solid #cbd5e1',
                          background: checked ? NAVY : 'white', color: 'white', flexShrink: 0,
                        }}
                      >
                        {checked && <Check size={10} />}
                      </span>
                      <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {entry.fileName}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          <div style={{ color: '#cbd5e1', fontSize: 18 }}>›</div>

          {/* Step 2: Target Schema */}
          <div>
            <div
              style={{
                fontSize: '9px', fontWeight: 800, textTransform: 'uppercase',
                letterSpacing: '0.08em', color: NAVY, marginBottom: 3,
              }}
            >
              Step 2 · Target Schema (CSV)
            </div>
            <button
              onClick={() => inputRef.current?.click()}
              style={{
                display: 'flex', alignItems: 'center', gap: 8, padding: '6px 12px',
                background: targetFile ? '#F0F9FF' : '#ffffff',
                border: targetFile ? `1px solid ${NAVY}` : '1px solid #cbd5e1',
                borderRadius: '8px', fontSize: '11.5px', fontWeight: 700,
                color: targetFile ? NAVY : '#475569', cursor: 'pointer', minWidth: '180px',
              }}
            >
              {targetFile ? <CheckCircle2 size={13} style={{ color: '#16A34A' }} /> : <UploadCloud size={13} style={{ color: NAVY }} />}
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 180 }}>
                {targetFile ? targetFile.name : 'Upload target schema…'}
              </span>
              {targetFile && (
                <button
                  onClick={(e) => { e.stopPropagation(); setTargetFile(null); }}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', color: '#94a3b8', padding: 0, marginLeft: 2 }}
                >
                  <X size={12} />
                </button>
              )}
            </button>
            <input
              ref={inputRef}
              type="file"
              accept=".csv,text/csv"
              style={{ display: 'none' }}
              onChange={(event) => setTargetFile(event.target.files?.[0] || null)}
            />
          </div>

          <div style={{ color: '#cbd5e1', fontSize: 18 }}>›</div>

          {/* Step 3: Run */}
          <div>
            <div
              style={{
                fontSize: '9px', fontWeight: 800, textTransform: 'uppercase',
                letterSpacing: '0.08em', color: NAVY, marginBottom: 3,
              }}
            >
              Step 3 · Execute Analysis
            </div>
            <button
              onClick={generateGapAnalysis}
              disabled={effectiveIsGenerating}
              style={{
                display: 'flex', alignItems: 'center', gap: 8, padding: '6px 14px',
                background: effectiveIsGenerating ? '#94a3b8' : NAVY,
                border: 'none', borderRadius: '8px',
                fontSize: '11.5px', fontWeight: 700, color: '#ffffff',
                cursor: effectiveIsGenerating ? 'not-allowed' : 'pointer',
                minWidth: 160,
              }}
            >
              {effectiveIsGenerating ? (
                <><Loader2 size={13} className="animate-spin" /> Running…</>
              ) : (
                <><FileSpreadsheet size={13} /> Run Gap Analysis</>
              )}
            </button>
          </div>

          {/* KPI Rationalization quick link */}
          <div style={{ marginLeft: 'auto' }}>
            <button
              onClick={() => navigate('/bussiness-metadata')}
              style={{
                display: 'flex', alignItems: 'center', gap: 8, padding: '6px 12px',
                background: '#EFF6FF', border: '1px solid #BFDBFE',
                borderRadius: '8px', fontSize: '11.5px', fontWeight: 700,
                color: '#1E40AF', cursor: 'pointer',
              }}
            >
              <Sparkles size={13} />
              KPI Rationalization
              <ArrowRight size={12} />
            </button>
          </div>
        </div>

        {/* ── Model Stats Bar ── */}
        <div
          style={{
            display: 'flex', alignItems: 'center', gap: 0,
            borderBottom: '1px solid #e2e8f0', backgroundColor: '#f1f5f9',
            flexShrink: 0,
          }}
        >
          {[
            { label: 'Sources', value: selectedCounts.sources, icon: Database },
            { label: 'Tables', value: selectedCounts.tables, icon: BarChart2 },
            { label: 'Relationships', value: selectedCounts.relationships, icon: TrendingUp },
            { label: 'Calculations', value: selectedCounts.calculations, icon: Target },
          ].map(({ label, value, icon: Icon }, idx) => (
            <div
              key={label}
              style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '7px 18px',
                borderRight: idx < 3 ? '1px solid #e2e8f0' : 'none',
              }}
            >
              <Icon size={12} style={{ color: NAVY, opacity: 0.7 }} />
              <span style={{ fontSize: '11px', fontWeight: 600, color: '#64748b' }}>{label}</span>
              <span style={{ fontSize: '13px', fontWeight: 800, color: '#0f172a' }}>{value}</span>
            </div>
          ))}
          {selectedFiles.length > 0 && (
            <div style={{ marginLeft: 'auto', display: 'flex', gap: 6, padding: '7px 16px', flexWrap: 'wrap' }}>
              {selectedFiles.slice(0, 3).map((f) => (
                <span
                  key={f}
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: 5,
                    background: `rgba(0,48,135,0.08)`, color: NAVY,
                    border: `1px solid rgba(0,48,135,0.15)`,
                    borderRadius: '20px', padding: '2px 10px',
                    fontSize: '10px', fontWeight: 700,
                  }}
                >
                  <Database size={9} />
                  {f.length > 22 ? f.slice(0, 22) + '…' : f}
                </span>
              ))}
              {selectedFiles.length > 3 && (
                <span style={{ padding: '2px 8px', background: '#f1f5f9', borderRadius: '20px', fontSize: '10px', fontWeight: 700, color: '#64748b' }}>
                  +{selectedFiles.length - 3} more
                </span>
              )}
            </div>
          )}
        </div>

        {/* ── Scrollable content area ── */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '16px' }}>

          {/* Error banner */}
          {error && (
            <div
              style={{
                display: 'flex', alignItems: 'flex-start', gap: 10,
                padding: '12px 16px', borderRadius: '8px',
                background: '#FEF2F2', border: '1px solid #FECACA',
                color: '#B91C1C', fontSize: '12px', fontWeight: 500,
                marginBottom: 16,
              }}
            >
              <AlertTriangle size={15} style={{ marginTop: 1, flexShrink: 0 }} />
              <span>{error}</span>
            </div>
          )}

          {/* Empty state */}
          {!result && !effectiveIsGenerating && !error && (
            <div
              style={{
                display: 'flex', flexDirection: 'column', alignItems: 'center',
                justifyContent: 'center', height: '60%', gap: 12,
                color: '#94a3b8', textAlign: 'center',
              }}
            >
              <FileSpreadsheet size={40} style={{ opacity: 0.35 }} />
              <p style={{ fontSize: '13px', fontWeight: 600 }}>No gap analysis results yet</p>
              <p style={{ fontSize: '12px', color: '#b0bec5' }}>
                Select your legacy reports, upload the target schema CSV, then click <strong style={{ color: NAVY }}>Run Gap Analysis</strong>
              </p>
            </div>
          )}

          {/* Loading state */}
          {effectiveIsGenerating && !result && (
            <div
              style={{
                display: 'flex', flexDirection: 'column', alignItems: 'center',
                justifyContent: 'center', height: '60%', gap: 16, color: NAVY,
              }}
            >
              <Loader2 size={36} className="animate-spin" style={{ opacity: 0.7 }} />
              <p style={{ fontSize: '13px', fontWeight: 700 }}>Running gap analysis…</p>
              <p style={{ fontSize: '11.5px', color: '#64748b' }}>Comparing legacy model columns against target schema</p>
            </div>
          )}

          {/* Results */}
          {result && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

              {/* Summary stat cards */}
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                {Object.entries(result.summary || {}).map(([label, value]) => {
                  const tone = statusTone(label);
                  return (
                    <div
                      key={label}
                      style={{
                        padding: '12px 16px', borderRadius: '10px',
                        background: tone.bg, border: `1px solid ${tone.border}`,
                        minWidth: 120, flex: '1 1 100px',
                      }}
                    >
                      <p style={{ fontSize: '9.5px', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.07em', color: tone.text, marginBottom: 4 }}>
                        {label}
                      </p>
                      <p style={{ fontSize: '26px', fontWeight: 800, color: tone.text, lineHeight: 1 }}>
                        {String(value)}
                      </p>
                    </div>
                  );
                })}
                <div
                  style={{
                    padding: '12px 16px', borderRadius: '10px',
                    background: '#f8fafc', border: '1px solid #e2e8f0',
                    minWidth: 120, flex: '1 1 100px',
                  }}
                >
                  <p style={{ fontSize: '9.5px', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.07em', color: '#64748b', marginBottom: 4 }}>
                    Total Mappings
                  </p>
                  <p style={{ fontSize: '26px', fontWeight: 800, color: '#0f172a', lineHeight: 1 }}>
                    {result.total_mappings || rows.length}
                  </p>
                </div>
              </div>

              {/* Results table */}
              <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: '10px', overflow: 'hidden' }}>
                {/* Table header bar */}
                <div
                  style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '12px 16px', borderBottom: '1px solid #e2e8f0',
                    background: '#f8fafc', gap: 12, flexWrap: 'wrap',
                  }}
                >
                  <div>
                    <span style={{ fontSize: '12px', fontWeight: 700, color: '#0f172a' }}>Column Gap Analysis</span>
                    <span style={{ fontSize: '11px', color: '#94a3b8', marginLeft: 8 }}>{filteredRows.length} rows</span>
                  </div>
                  <div style={{ position: 'relative' }}>
                    <Search
                      size={13}
                      style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }}
                    />
                    <input
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      placeholder="Search gaps…"
                      style={{
                        height: 34, width: 220, borderRadius: '8px',
                        border: '1px solid #cbd5e1', paddingLeft: 30, paddingRight: 10,
                        fontSize: '12px', outline: 'none', background: '#fff',
                      }}
                    />
                  </div>
                </div>

                {/* Scrollable table */}
                <div style={{ overflowX: 'auto', maxHeight: 520, overflowY: 'auto' }}>
                  <table style={{ width: '100%', minWidth: 980, fontSize: '12px', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ background: '#f1f5f9', position: 'sticky', top: 0, zIndex: 1 }}>
                        {['Source', 'Column Asset ID', 'Source Column', 'Target Column', 'Confidence', 'Status', 'Reasoning'].map((h) => (
                          <th
                            key={h}
                            style={{
                              padding: '10px 14px', textAlign: 'left', fontSize: '10px',
                              fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.07em',
                              color: '#64748b', borderBottom: '1px solid #e2e8f0', whiteSpace: 'nowrap',
                            }}
                          >
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {filteredRows.map((row, index) => {
                        const tone = statusTone(row['GAP_Status'] || '');
                        const conf = Number(row['Confidence Score'] || 0);
                        return (
                          <tr
                            key={`${row['Source Table']}-${row['Source Column']}-${index}`}
                            style={{ borderBottom: '1px solid #f1f5f9', transition: 'background 0.1s' }}
                            onMouseEnter={(e) => (e.currentTarget.style.background = '#f8fafc')}
                            onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                          >
                            {/* SOURCE */}
                            <td style={{ padding: '10px 14px', verticalAlign: 'top' }}>
                              <p style={{ fontWeight: 600, color: '#0f172a', marginBottom: 2 }}>{row['Source Table']}</p>
                              <span style={{ fontSize: '10px', padding: '1px 6px', background: '#f1f5f9', borderRadius: 4, color: '#64748b' }}>
                                {row['Source_Data_Type']}
                              </span>
                            </td>

                            {/* COLUMN ASSET ID */}
                            <td style={{ padding: '10px 14px', verticalAlign: 'top' }}>
                              <div
                                title={row.Column_Asset_ID}
                                style={{
                                  maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                                  fontFamily: 'monospace', fontSize: '10px', padding: '4px 8px',
                                  background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 6, color: '#475569',
                                }}
                              >
                                {row.Column_Asset_ID}
                              </div>
                            </td>

                            {/* SOURCE COLUMN */}
                            <td style={{ padding: '10px 14px', verticalAlign: 'top' }}>
                              <p style={{ fontWeight: 500, color: '#334155' }}>{row['Source Column']}</p>
                            </td>

                            {/* TARGET COLUMN */}
                            <td style={{ padding: '10px 14px', verticalAlign: 'top' }}>
                              <p style={{ fontWeight: 700, color: '#15803D' }}>{row['Mapped Target Column']}</p>
                            </td>

                            {/* CONFIDENCE */}
                            <td style={{ padding: '10px 14px', verticalAlign: 'top' }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <div style={{ height: 6, width: 60, borderRadius: 99, background: '#e2e8f0', overflow: 'hidden', flexShrink: 0 }}>
                                  <div
                                    style={{
                                      height: '100%', borderRadius: 99,
                                      background: conf >= 0.8 ? '#10B981' : conf >= 0.5 ? '#F59E0B' : '#EF4444',
                                      width: `${conf * 100}%`,
                                    }}
                                  />
                                </div>
                                <span style={{ fontSize: '11px', fontWeight: 700, color: '#475569', fontFamily: 'monospace' }}>
                                  {(conf * 100).toFixed(0)}%
                                </span>
                              </div>
                            </td>

                            {/* STATUS */}
                            <td style={{ padding: '10px 14px', verticalAlign: 'top' }}>
                              <span
                                style={{
                                  display: 'inline-block', padding: '2px 10px',
                                  borderRadius: 99, fontSize: '10px', fontWeight: 700,
                                  background: tone.bg, color: tone.text, border: `1px solid ${tone.border}`,
                                }}
                              >
                                {row['GAP_Status']}
                              </span>
                            </td>

                            {/* REASONING */}
                            <td style={{ padding: '10px 14px', verticalAlign: 'top', minWidth: 320 }}>
                              <p
                                style={{ fontSize: '11.5px', color: '#475569', lineHeight: 1.5, wordBreak: 'break-word', whiteSpace: 'normal' }}
                              >
                                {row['GAP_Reasoning'] || row.Reasoning}
                              </p>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </ContentCard>
  );
}
