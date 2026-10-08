import React, { useEffect, useMemo, useRef, useState } from 'react';
import { DataModel } from '../../data/sampleModel';
import { Drawer } from '@mui/material';
import { Braces } from 'lucide-react';
import {
  Activity,
  AlertCircle,
  ArrowRightLeft,
  BarChart3,
  Calculator,
  Check,
  CheckCircle2,
  Clock,
  Database,
  FileUp,
  FolderOpen,
  GitBranch,
  GitCompare,
  Hash,
  History,
  Loader2,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  Table2,
  UploadCloud,
  X,
} from 'lucide-react';
import ContentCard from '../../core/CardContent/CardContent.tsx';
import FileWorkspaceHeader from '../../core/FileWorkspaceHeader.tsx';
import { setUploadedFileContext } from '../../utils/uploadedFileContext.ts';
import { useOutletContext, useLocation } from 'react-router-dom';
import { Button, Dialog, DialogContent, IconButton, MenuItem, Select, Typography } from '@mui/material';
import { fetchPowerBiReport, getJobProgress, listPowerBiReports, ReportListItem, JobProgress, uploadPowerBiDataset } from '../../services/powerbiReports.ts';
import { Link } from 'react-router-dom';
import { ChevronDown, ChevronRight, FileText, Sparkles } from 'lucide-react';

interface OverviewProps {
  model: DataModel;
}

interface DatasetSnapshot {
  id: string;
  name: string;
  size: number;
  modified: number;
  uploadedAt: string;
  tables: number;
  relationships: number;
  calculations: number;
  kpis: number;
  addedTables: number;
  removedTables: number;
  relationshipChanges: number;
  status: 'active' | 'archived';
}

type UploadState = 'idle' | 'uploading' | 'validating' | 'complete' | 'error';
type ProcessingState = 'idle' | 'processing' | 'complete';

const processingSteps = ['Processing updated dataset', 'Schema comparison running', 'AI analysis running', 'Rebuilding insights'];

const formatSize = (bytes: number) => {
  if (!bytes) return '0 KB';
  const units = ['B', 'KB', 'MB', 'GB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / Math.pow(1024, index)).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
};

const formatTime = (seconds: number) => {
  if (seconds <= 1) return '<1 sec';
  return `${Math.ceil(seconds)} sec`;
};

export default function Overview({ model }: OverviewProps) {
  const { sideNavWidth } = useOutletContext();
  const inputRef = useRef<HTMLInputElement>(null);
  const uploadTimerRef = useRef<number | null>(null);
  const processingTimerRef = useRef<number | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadState, setUploadState] = useState<UploadState>('idle');
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [uploadedBytes, setUploadedBytes] = useState(0);
  const [processingState, setProcessingState] = useState<ProcessingState>('idle');
  const [processingProgress, setProcessingProgress] = useState(0);
  const [processingStep, setProcessingStep] = useState(0);
  const [viewMode, setViewMode] = useState<'current' | 'previous'>('current');
  const [reports, setReports] = useState<ReportListItem[]>([]);

  const [selectedReportFile, setSelectedReportFile] = useState('');
  const [isReportLoading, setIsReportLoading] = useState(false);
  const [reportError, setReportError] = useState('');
  const location = useLocation();
  const [pendingJob, setPendingJob] = useState<JobProgress & { job_id?: string } | null>(null);
  const [isDatasetLibraryOpen, setIsDatasetLibraryOpen] = useState(false);
  const [activeModel, setActiveModel] = useState<DataModel>(model);
  const [previousDataset, setPreviousDataset] = useState<DatasetSnapshot | null>(null);
  const [currentDataset, setCurrentDataset] = useState<DatasetSnapshot>(() => ({
    id: 'v1',
    name: model.name,
    size: 1840000,
    modified: new Date(model.extracted_at).getTime(),
    uploadedAt: model.extracted_at,
    tables: model.tables.length,
    relationships: model.relationships.length,
    calculations: model.calculations.length,
    kpis: 12,
    addedTables: 0,
    removedTables: 0,
    relationshipChanges: 0,
    status: 'active',
  }));
  const [history, setHistory] = useState<DatasetSnapshot[]>([]);
  const [isJsonDrawerOpen, setIsJsonDrawerOpen] = useState(false);

  useEffect(() => {
    setActiveModel(model);
    setCurrentDataset({
      id: model.model_id || 'v1',
      name: model.name,
      size: 1840000,
      modified: new Date(model.extracted_at).getTime(),
      uploadedAt: model.extracted_at,
      tables: model.tables.length,
      relationships: model.relationships.length,
      calculations: model.calculations.length,
      kpis: Array.isArray(model.kpi_lineage) ? model.kpi_lineage.length : 12,
      addedTables: 0,
      removedTables: 0,
      relationshipChanges: 0,
      status: 'active',
    });
  }, [model]);

  useEffect(() => {
    if (location.state?.openUpdateDataset) {
      setIsModalOpen(true);
      window.history.replaceState({}, document.title, location.pathname);
    }
  }, [location.pathname, location.state]);

  useEffect(() => {
    if (location.state?.openDatasetLibrary) {
      setIsDatasetLibraryOpen(true);
      window.history.replaceState({}, document.title, location.pathname);
    }
  }, [location.pathname, location.state]);

  const rawJsonData = useMemo(() => {
    try {
      return JSON.parse(
        localStorage.getItem("activePowerBiReportData") || "{}"
      );
    } catch {
      return {};
    }
  }, [selectedReportFile]);
  const buildModelFromReport = (reportData: any, fileName: string, meta?: ReportListItem): DataModel => {
    const result = reportData?.result || reportData?.data || reportData?.report || reportData || {};
    return {
      ...model,
      ...result,
      name: result?.name || fileName || model.name,
      model_id: result?.report_id || meta?.report_id || result?.model_id || model.model_id,
      extracted_at: meta?.completed_at || result?.completed_at || result?.extracted_at || new Date().toISOString(),
      data_sources: Array.isArray(result?.data_sources) ? result.data_sources : model.data_sources,
      tables: Array.isArray(result?.tables) ? result.tables : model.tables,
      relationships: Array.isArray(result?.relationships) ? result.relationships : model.relationships,
      calculations: Array.isArray(result?.calculations)
        ? result.calculations
        : Array.isArray(result?.measures)
          ? result.measures
          : model.calculations,
      technical_summary: result?.technical_summary || model.technical_summary,
      kpi_lineage: Array.isArray(result?.kpi_lineage) ? result.kpi_lineage : model.kpi_lineage,
    };
  };
  const snapshotFromReport = (fileName: string, reportData: any, meta?: ReportListItem): DatasetSnapshot => {
    const result = reportData?.result || reportData?.data || reportData?.report || reportData || {};
    const tables = Array.isArray(result?.tables) ? result.tables : Array.isArray(result?.schema?.tables) ? result.schema.tables : [];
    const columns = Array.isArray(result?.columns) ? result.columns : tables.flatMap((table: any) => table?.columns || []);
    const relationships = Array.isArray(result?.relationships) ? result.relationships : Array.isArray(result?.schema?.relationships) ? result.schema.relationships : [];
    const calculations = Array.isArray(result?.calculations) ? result.calculations : Array.isArray(result?.measures) ? result.measures : [];

    return {
      id: meta?.report_id || fileName,
      name: fileName,
      size: columns.length * 12000 || 1840000,
      modified: meta?.completed_at ? new Date(meta.completed_at).getTime() : Date.now(),
      uploadedAt: meta?.completed_at || new Date().toISOString(),
      tables: tables.length || model.tables.length,
      relationships: relationships.length || model.relationships.length,
      calculations: calculations.length || model.calculations.length,
      kpis: Math.max(1, calculations.length || 12),
      addedTables: 0,
      removedTables: 0,
      relationshipChanges: relationships.length || 0,
      status: 'active',
    };
  };

  const refreshReports = async () => {
    try {
      const [powerBiList, tableauList] = await Promise.all([
        listPowerBiReports('powerbi').catch(() => []),
        listPowerBiReports('tableau-workbook').catch(() => []),
      ]);
      const combinedReports = [...powerBiList, ...tableauList]
        .filter((report, index, self) =>
          index === self.findIndex((item) =>
            (item.report_id && item.report_id === report.report_id) ||
            (
              item.file_name === report.file_name &&
              item.completed_at === report.completed_at &&
              item.tool_type === report.tool_type
            )
          )
        )
        .sort(
          (a, b) =>
            new Date(b.completed_at || 0).getTime() -
            new Date(a.completed_at || 0).getTime()
        );
      setReports(combinedReports);
      if (combinedReports.length > 0 && !selectedVersion) {
        setSelectedVersion(
          combinedReports[0].report_id
        );
      }
      setReportError('');
      return combinedReports;
    } catch (error) {
      setReportError(error instanceof Error ? error.message : 'Unable to load dataset history.');
      return [];
    }
  };

  // const trackJob = (jobId: string, fallbackFiles: File[] = []) => {
  //   const interval = window.setInterval(async () => {
  //     try {
  //       const progress = await getJobProgress(jobId);
  //       const nextJob = { ...progress, job_id: jobId };
  //       setPendingJob(nextJob);
  //       localStorage.setItem('powerbiPendingJob', JSON.stringify(nextJob));
  //       const files = progress.files || [];
  //       const allDone = files.length > 0 && files.every((file) => ['success', 'failed'].includes(String(file.status).toLowerCase()));
  //       const successfulFile = files.find((file) => String(file.status).toLowerCase() === 'success');

  //       if (progress.status === 'success' || successfulFile) {
  //         window.clearInterval(interval);
  //         const fileName = successfulFile?.file_name || progress.file_name || fallbackFiles[0]?.name;
  //         await refreshReports();
  //         if (fileName) await loadReport(fileName);
  //       }

  //       if (progress.status === 'failed' || (allDone && !successfulFile)) {
  //         window.clearInterval(interval);
  //       }
  //     } catch (error) {
  //       setPendingJob({ job_id: jobId, status: 'failed', error: error instanceof Error ? error.message : 'Unable to track processing job.' });
  //       window.clearInterval(interval);
  //     }
  //   }, 2500);
  // };

  const loadReport = async (fileName: string, meta?: ReportListItem) => {
    if (!fileName) return;
    setIsReportLoading(true);
    setReportError('');
    try {
      const toolName =
        meta?.tool_type ||
        (fileName.toLowerCase().endsWith('.pbix')
          ? 'powerbi'
          : fileName.toLowerCase().endsWith('.twb') || fileName.toLowerCase().endsWith('.twbx')
            ? 'tableau-workbook'
            : undefined);
      const reportData = await fetchPowerBiReport(fileName, toolName, {
        reportId: meta?.report_id,
      });
      setPreviousDataset(currentDataset);
      setActiveModel(buildModelFromReport(reportData, fileName, meta));
      setCurrentDataset(snapshotFromReport(fileName, reportData, meta));
      setSelectedReportFile(fileName);
      const nextVersion =
        meta?.report_id ||
        reports.find((report) => report.file_name === fileName)?.report_id ||
        '';
      setSelectedVersion(nextVersion);
      setViewMode('current');
      localStorage.setItem('activePowerBiReportFile', fileName);
      localStorage.setItem('activePowerBiReportId', meta?.report_id || nextVersion || '');
      localStorage.setItem('activePowerBiReportData', JSON.stringify(reportData));
    } catch (error) {
      setReportError(error instanceof Error ? error.message : 'Unable to fetch dataset.');
    } finally {
      setIsReportLoading(false);
    }
  };

  useEffect(() => {
    const storedFile = localStorage.getItem('activePowerBiReportFile') || '';
    const storedData = localStorage.getItem('activePowerBiReportData');
    if (storedFile && storedData) {
      try {
        const parsedData = JSON.parse(storedData);
        setActiveModel(buildModelFromReport(parsedData, storedFile));
        setCurrentDataset(snapshotFromReport(storedFile, parsedData));
        setSelectedReportFile(storedFile);
      } catch (error) {
        localStorage.removeItem('activePowerBiReportData');
      }
    }
    refreshReports().then((list) => {
      if (!storedFile && list[0]?.file_name) loadReport(list[0].file_name, list[0]);
    });
    try {
      const raw = localStorage.getItem('existingReports');
      if (raw) setSwitcherFiles(JSON.parse(raw));
    } catch { /* ignore */ }
  }, []);
  useEffect(() => {
    try {
      const raw = localStorage.getItem('existingReports');
      if (raw) {
        const parsed = JSON.parse(raw);
        setSwitcherFiles(parsed);
      }
    } catch { /* ignore */ }
  }, [location.pathname])

  useEffect(() => {
    const rawJob = localStorage.getItem("powerbiPendingJob");
    if (!rawJob) return;

    let parsedJob: any = null;

    try {
      parsedJob = JSON.parse(rawJob);
    } catch {
      return;
    }

    if (!parsedJob?.job_id) return;

    setPendingJob(parsedJob);

    let interval: number;

    const pollProgress = async () => {
      try {
        const progress = await getJobProgress(parsedJob.job_id);

        console.log("Progress API Response:", progress);

        const nextJob = {
          ...progress,
          job_id: parsedJob.job_id
        };

        setPendingJob(nextJob);
        localStorage.setItem(
          "powerbiPendingJob",
          JSON.stringify(nextJob)
        );

        const overallStatus =
          progress?.overall_status?.toLowerCase();

        const files = progress?.files || [];

        const successfulFile = files.find(
          (file) =>
            file.status?.toLowerCase() === "success"
        );

        // STOP polling when completed
        if (overallStatus === "completed") {
          window.clearInterval(interval);

          console.log("Processing completed");

          localStorage.removeItem("powerbiPendingJob");

          const fileName =
            successfulFile?.file_name ||
            parsedJob?.file_name;

          await refreshReports();

          if (fileName) {
            await loadReport(fileName);
          }

          setPendingJob(null);
          return;
        }

        // STOP polling when failed
        if (overallStatus === "failed") {
          window.clearInterval(interval);

          console.log("Processing failed");

          setPendingJob({
            ...nextJob,
            status: "failed",
            error:
              progress?.error ||
              "Dataset processing failed"
          });

          return;
        }
      } catch (error) {
        console.error(error);

        window.clearInterval(interval);

        setPendingJob({
          ...parsedJob,
          status: "failed",
          error:
            error instanceof Error
              ? error.message
              : "Unable to track processing job."
        });
      }
    };

    interval = window.setInterval(
      pollProgress,
      2500
    );

    pollProgress();

    return () => {
      window.clearInterval(interval);
    };
  }, []);

  const factCount = activeModel.tables.filter((t) => t.table_type === 'fact').length;
  const dimCount = activeModel.tables.filter((t) => t.table_type === 'dimension').length;
  const totalColumns = activeModel.tables.reduce((acc, t) => acc + t.columns.length, 0);
  const visibleDataset = viewMode === 'previous' && previousDataset ? previousDataset : currentDataset;
  const isProcessing = processingState === 'processing';
  const [switcherFiles, setSwitcherFiles] = useState<{ fileName: string }[]>([]);
  const extractedDate = new Date(visibleDataset.uploadedAt).toLocaleString('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
  const [selectedVersion, setSelectedVersion] = useState('');
  const stats = [
    { label: 'Data Sources', value: activeModel.data_sources.length, icon: Database },
    { label: 'Tables', value: visibleDataset.tables, icon: Table2 },
    { label: 'Relationships', value: visibleDataset.relationships, icon: GitBranch },
    { label: 'Calculations', value: visibleDataset.calculations, icon: Calculator },
    { label: 'Total Columns', value: totalColumns, icon: Hash },
    { label: 'Fact / Dim', value: `${factCount} / ${dimCount}`, icon: BarChart3 },
  ];
  const datasetVersions = useMemo(() => {
    const activeFileName = selectedReportFile || visibleDataset.name;
    return reports
      .filter(
        (r) =>
          r.file_name === activeFileName
      )
      .sort(
        (a, b) =>
          new Date(b.completed_at).getTime() -
          new Date(a.completed_at).getTime()
      );
  }, [reports, selectedReportFile, visibleDataset.name]);

  useEffect(() => {
    if (!datasetVersions.length) {
      if (selectedVersion) {
        setSelectedVersion('');
      }
      return;
    }

    const hasSelectedVersion = datasetVersions.some(
      (report) => report.report_id === selectedVersion
    );

    if (!selectedVersion || !hasSelectedVersion) {
      setSelectedVersion(datasetVersions[0].report_id);
    }
  }, [datasetVersions, selectedVersion]);

  const comparison = useMemo(() => {
    if (!previousDataset) return null;
    return [
      { label: 'File size', before: formatSize(previousDataset.size), after: formatSize(currentDataset.size) },
      { label: 'Tables', before: previousDataset.tables, after: currentDataset.tables },
      { label: 'Relationships', before: previousDataset.relationships, after: currentDataset.relationships },
      { label: 'Calculations', before: previousDataset.calculations, after: currentDataset.calculations },
      { label: 'KPIs', before: previousDataset.kpis, after: currentDataset.kpis },
    ];
  }, [currentDataset, previousDataset]);

  const buildSnapshot = (file: File): DatasetSnapshot => {
    const variance = Math.max(1, Math.round(file.size / 420000));
    return {
      id: `v${history.length + 2}`,
      name: file.name,
      size: file.size,
      modified: file.lastModified,
      uploadedAt: new Date().toISOString(),
      tables: Math.max(1, activeModel.tables.length + (variance % 4) - 1),
      relationships: Math.max(0, activeModel.relationships.length + (variance % 5) - 2),
      calculations: Math.max(0, activeModel.calculations.length + (variance % 6) - 2),
      kpis: Math.max(1, 12 + (variance % 5) - 1),
      addedTables: variance % 3,
      removedTables: variance % 2,
      relationshipChanges: Math.max(1, variance % 6),
      status: 'active',
    };
  };

  const clearUploadTimer = () => {
    if (uploadTimerRef.current) {
      window.clearInterval(uploadTimerRef.current);
      uploadTimerRef.current = null;
    }
  };

  const clearProcessingTimer = () => {
    if (processingTimerRef.current) {
      window.clearInterval(processingTimerRef.current);
      processingTimerRef.current = null;
    }
  };

  const resetUpload = () => {
    clearUploadTimer();
    setUploadState('idle');
    setUploadProgress(0);
    setUploadedBytes(0);
    setUploadFiles([]);
    if (inputRef.current) inputRef.current.value = '';
  };

  const startProcessing = () => {
    clearProcessingTimer();
    setProcessingState('processing');
    setProcessingProgress(0);
    setProcessingStep(0);
    processingTimerRef.current = window.setInterval(() => {
      setProcessingProgress((prev) => {
        const next = Math.min(prev + 5, 100);
        setProcessingStep(Math.min(Math.floor(next / 25), processingSteps.length - 1));
        if (next >= 100) {
          clearProcessingTimer();
          setProcessingState('complete');
          setTimeout(() => setProcessingState('idle'), 2600);
        }
        return next;
      });
    }, 190);
  };

  const completeUpload = (files: File[]) => {
    setUploadState('complete');
    setUploadProgress(100);
    setUploadedBytes(files.reduce((sum, file) => sum + file.size, 0));
    setTimeout(() => {
      setIsModalOpen(false);
      resetUpload();
    }, 850);
  };

  const beginUpload = async (files?: File[] | FileList | File) => {
    const nextFiles = files instanceof File ? [files] : Array.from(files || []);
    if (!nextFiles.length) return;
    clearUploadTimer();
    setUploadFiles(nextFiles);
    setUploadState('uploading');
    setUploadProgress(0);
    setUploadedBytes(0);
    setReportError('');

    const invalidFile = nextFiles.find((file) => !file.name.toLowerCase().endsWith('.pbix'));
    if (invalidFile) {
      setUploadState('error');
      setReportError('Uploaded file is not a valid .pbix file.');
      setPendingJob({
        status: 'failed',
        error: 'Uploaded file is not a valid .pbix file.',
        files: nextFiles.map((file) => ({
          file_name: file.name,
          status: file.name.toLowerCase().endsWith('.pbix') ? 'processing' : 'failed',
          error: file.name.toLowerCase().endsWith('.pbix') ? undefined : 'Uploaded file is not a valid .pbix file.',
        })),
      });
      return;
    }
    setUploadedFileContext(nextFiles);

    try {
      const uploadResult = await uploadPowerBiDataset(nextFiles, (progress) => {
        setUploadProgress(progress);
        setUploadedBytes(Math.round((nextFiles.reduce((sum, file) => sum + file.size, 0) * progress) / 100));
        if (progress >= 95) setUploadState('validating');
      });
      const nextJob = {
        job_id: uploadResult.job_id,
        status: 'processing',
        files: nextFiles.map((file) => ({ file_name: file.name, status: 'processing' })),
      };
      setPendingJob(nextJob);
      localStorage.setItem('powerbiPendingJob', JSON.stringify(nextJob));
      completeUpload(nextFiles);
    } catch (error) {
      setUploadState('error');
      setReportError(error instanceof Error ? error.message : 'Upload failed.');
    }
  };

  const cancelUpload = () => resetUpload();

  const retryUpload = () => {
    if (uploadFiles.length) beginUpload(uploadFiles);
  };
  const [selectedReport, setSelectedReport] = useState(null);
  const triggerReanalysis = () => startProcessing();

  const rollbackDataset = () => {
    if (!previousDataset) return;
    setHistory((items) => [{ ...currentDataset, status: 'archived' }, ...items].slice(0, 5));
    setCurrentDataset({ ...previousDataset, status: 'active', uploadedAt: new Date().toISOString() });
    setPreviousDataset(currentDataset);
    setViewMode('current');
    startProcessing();
  };

  const totalUploadSize = uploadFiles.reduce((sum, file) => sum + file.size, 0);
  const estimatedRemaining = uploadFiles.length ? formatTime(((100 - uploadProgress) / 12) * 0.4) : '--';
  const validationLabel =
    uploadState === 'complete'
      ? 'Upload complete'
      : uploadState === 'validating'
        ? 'Validating schema...'
        : uploadState === 'uploading'
          ? 'Uploading file...'
          : uploadState === 'error'
            ? 'Upload failed'
            : 'Ready for secure upload';

  return (
    <ContentCard
      heading={null}
      headerActions={null}
      sideNavWidth={sideNavWidth}
      headerComponent={<FileWorkspaceHeader pageTitle="Overview" />}
    >
      <div className="relative space-y-7 pb-4">
        {isProcessing && (
          <section className="sticky top-0 z-20 rounded-lg border border-red-100 bg-white/95 p-4 shadow-lg shadow-red-950/10 backdrop-blur">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex items-start gap-3">
                <div className="grid h-10 w-10 place-items-center rounded-lg bg-red-50 text-red-700">
                  <Loader2 className="animate-spin" size={20} />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-stone-950">{processingSteps[processingStep]}</h3>
                  <p className="mt-1 text-xs text-stone-500">Keeping the previous version available while new insights are rebuilt.</p>
                </div>
              </div>
              <div className="min-w-[280px] flex-1 lg:max-w-xl">
                <div className="mb-2 flex justify-between text-xs font-semibold text-stone-500">
                  <span>Dataset pipeline</span>
                  <span>{processingProgress}%</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-stone-100">
                  <div className="h-full rounded-full bg-gradient-to-r from-red-700 to-red-900 transition-all" style={{ width: `${processingProgress}%` }} />
                </div>
              </div>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-2 lg:grid-cols-4">
              {processingSteps.map((step, index) => (
                <div key={step} className={`rounded-lg border p-3 text-xs ${index <= processingStep ? 'border-red-100 bg-red-50 text-red-900' : 'border-stone-200 bg-stone-50 text-stone-500'}`}>
                  <div className="mb-2 flex items-center gap-2">
                    {index < processingStep ? <Check size={14} /> : index === processingStep ? <Loader2 className="animate-spin" size={14} /> : <Clock size={14} />}
                    <span className="font-semibold">Step {index + 1}</span>
                  </div>
                  {step}
                </div>
              ))}
            </div>
          </section>
        )}

        {processingState === 'complete' && (
          <section className="rounded-lg border border-emerald-100 bg-emerald-50 p-4 text-emerald-900">
            <div className="flex items-center gap-3">
              <CheckCircle2 size={20} />
              <div>
                <h3 className="text-sm font-semibold">Updated dataset is live</h3>
                <p className="text-xs">Schema, KPIs, relationships, and version history have been refreshed.</p>
              </div>
            </div>
          </section>
        )}

        {/* {pendingJob && (
          <section className={`rounded-lg border p-4 shadow-sm ${
            pendingJob.status === 'failed' ? 'border-red-200 bg-red-50' : pendingJob.status === 'success' ? 'border-emerald-100 bg-emerald-50' : 'border-red-100 bg-white'
          }`}>
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-start gap-3">
                <div className={`grid h-10 w-10 place-items-center rounded-lg ${
                  pendingJob.status === 'failed' ? 'bg-red-100 text-red-700' : pendingJob.status === 'success' ? 'bg-emerald-100 text-emerald-700' : 'bg-red-50 text-red-700'
                }`}>
                  {pendingJob.status === 'processing' ? <Loader2 className="animate-spin" size={19} /> : pendingJob.status === 'failed' ? <AlertCircle size={19} /> : <Check size={19} />}
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-stone-950">
                    {pendingJob.status === 'failed' ? 'Dataset processing failed' : pendingJob.status === 'success' ? 'Dataset processing complete' : 'Processing dataset...'}
                  </h3>
                  <p className="mt-1 text-xs text-stone-500">
                    {pendingJob.error || pendingJob.file_name || 'Power BI report processing is running.'}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {(pendingJob.runtime || pendingJob.runtime_seconds) && (
                  <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-stone-600">
                    Runtime {pendingJob.runtime || pendingJob.runtime_seconds}s
                  </span>
                )}
                {pendingJob.status === 'failed' && (
                  <Button onClick={() => setIsModalOpen(true)} variant="outlined" sx={{ borderRadius: '8px', textTransform: 'none', color: '#8f0d22', borderColor: 'rgba(200,16,46,0.28)' }}>
                    Retry upload
                  </Button>
                )}
              </div>
            </div>
          </section>
        )} */}

        <div className={isProcessing || isReportLoading ? 'pointer-events-none opacity-60 blur-[1px] transition' : 'transition'}>
          {isReportLoading && (
            <div className="mb-4 rounded-lg border border-red-100 bg-white p-4 text-sm font-semibold text-stone-900 shadow-sm">
              <div className="flex items-center gap-2">
                <Loader2 className="animate-spin text-red-700" size={17} />
                Loading selected dataset...
              </div>
            </div>
          )}
{false && <div className="rounded-xl border border-stone-200 overflow-hidden bg-white">
  <table className="w-full text-sm">
    
    {/* Header */}
    <thead className="bg-stone-50 border-b border-stone-200 sticky top-0 z-10">
      <tr>
        <th className="px-4 py-3 text-left text-xs font-semibold text-stone-500 uppercase">
          No
        </th>

        <th className="px-4 py-3 text-left text-xs font-semibold text-stone-500 uppercase">
          Dataset Name
        </th>

        <th className="px-4 py-3 text-left text-xs font-semibold text-stone-500 uppercase">
          Status
        </th>

        <th className="px-4 py-3 text-left text-xs font-semibold text-stone-500 uppercase">
          Last Updated
        </th>

        <th className="px-4 py-3 text-left text-xs font-semibold text-stone-500 uppercase">
          Active
        </th>

        <th className="px-4 py-3 text-left text-xs font-semibold text-stone-500 uppercase">
          Action
        </th>
      </tr>
    </thead>

    {/* Body */}
    <tbody>
      {switcherFiles.map((entry, index) => {
        const isSelected =
          selectedReportFile === entry.fileName;

        return (
          <tr
            key={entry.fileName}
            className={`border-b border-stone-100 hover:bg-red-50 transition ${
              isSelected ? "bg-red-50/50" : ""
            }`}
          >
            {/* Serial Number */}
            <td className="px-4 py-4 text-stone-600 font-medium">
              {index + 1}
            </td>

            {/* Dataset Name */}
            <td className="px-4 py-4">
              <div className="flex items-center gap-2">
                <Database
                  size={14}
                  className={
                    isSelected
                      ? "text-red-600"
                      : "text-stone-500"
                  }
                />
                <span className="font-medium text-stone-900 truncate">
                  {entry.fileName}
                </span>
              </div>
            </td>

            {/* Status */}
            <td className="px-4 py-4">
              <span className="rounded-full bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700">
                Ready
              </span>
            </td>

            {/* Last Updated */}
            <td className="px-4 py-4 text-stone-500 text-xs">
              {new Date().toLocaleString()}
            </td>

            {/* Active */}
            <td className="px-4 py-4">
              {isSelected ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-red-100 px-2 py-1 text-xs font-medium text-red-700">
                  <Check size={12} />
                  Active
                </span>
              ) : (
                <span className="text-stone-400 text-xs">
                  —
                </span>
              )}
            </td>

            {/* Action */}
            <td className="px-4 py-4">
              <button
                onClick={async () => {
                  const matchedReportMeta =
                    reports.find(
                      (report) =>
                        report.file_name ===
                        entry.fileName
                    );

                  await loadReport(
                    entry.fileName,
                    matchedReportMeta
                  );

                  setSelectedReportFile(
                    entry.fileName
                  );
                }}
                className={`w-8 h-8 rounded-lg flex items-center justify-center transition ${
                  isSelected
                    ? "bg-green-600 text-white"
                    : "border border-stone-300 hover:border-red-300 hover:bg-red-50"
                }`}
              >
                {isSelected ? (
                  <Check size={14} />
                ) : (
                  <Database size={14} />
                )}
              </button>
            </td>
          </tr>
        );
      })}
    </tbody>
  </table>

  {switcherFiles.length === 0 && (
    <div className="py-8 text-center text-sm text-stone-400">
      No matched datasets found
    </div>
  )}
</div>}

          <section className="mt-5">
            <h2 className="text-sm font-bold text-stone-900 mb-3 tracking-tight">Overview</h2>
            
            <div className="flex flex-col gap-3">
              {/* AI SUGGESTIONS */}
              {activeModel.ai_summary && (
                <div className="rounded border-l-[3px] border-l-[#003087] bg-slate-50 p-3.5">
                  <div className="flex items-center gap-1.5 mb-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-[#003087]" />
                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-700">AI Suggestions</span>
                  </div>
                  <p className="text-[12px] text-slate-700 leading-relaxed font-medium">
                    {activeModel.ai_summary}
                  </p>
                </div>
              )}

              {/* BUSINESS OVERVIEW */}
              {(activeModel.technical_summary || !activeModel.ai_summary) && (
                <div className="rounded border border-stone-200 bg-white p-4">
                  <span className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-2">Summary</span>
                  <p className="text-[12px] text-slate-600 leading-relaxed line-clamp-3">
                    {activeModel.technical_summary
                      ?.replace(/^Executive summary\s*[—:-]\s*/i, "")
                      ?.replace(/^Technical summary\s*[—:-]\s*/i, "")
                      ?.replace(/^Summary\s*[—:-]\s*/i, "")
                    }
                  </p>
                  
                  <div className="mt-3 flex justify-end">
                    <Link
                      to="/technicalSummary"
                      className="text-[11px] font-semibold text-[#003087] hover:underline flex items-center gap-1"
                    >
                      Read full context <ChevronRight className="w-3 h-3" />
                    </Link>
                  </div>
                </div>
              )}
            </div>
          </section>

          <section className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
            {stats.map((s) => {
              const Icon = s.icon;
              return (
                <Link to="/relationships" key={s.label}>
                  <div className="rounded border border-stone-200 bg-white px-3 py-2 flex items-center gap-2.5 transition-colors hover:border-slate-300 hover:bg-slate-50">
                    <div className="w-7 h-7 shrink-0 rounded bg-slate-100 flex items-center justify-center text-slate-600 border border-slate-200">
                      <Icon className="w-3.5 h-3.5" strokeWidth={2.5} />
                    </div>
                    <div className="min-w-0">
                      <p className="text-[15px] font-bold text-stone-900 leading-none truncate">{s.value}</p>
                      <p className="text-[9px] font-semibold uppercase tracking-wider text-stone-500 mt-1 truncate">{s.label}</p>
                    </div>
                  </div>
                </Link>
              );
            })}
          </section>
        </div>
        {/* ── Dataset Switcher Rail ── */}

        {/* <section className="grid grid-cols-1 gap-5 lg:grid-cols-3">
          <div className="rounded-lg border border-stone-200 bg-white p-6 lg:col-span-2">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-base font-semibold text-stone-950">Dataset Operations</h3>
                <p className="mt-1 text-sm text-stone-500">Replace, compare, rollback, and inspect upload history from this dashboard.</p>
              </div>
              <Activity className={isProcessing ? 'animate-spin text-red-700' : 'text-red-700'} size={22} />
            </div>
            <div className="mt-5 grid grid-cols-1 gap-3 md:grid-cols-3">
              {[
                ['Upload updated file', 'Drag in a fresh export.', () => setIsModalOpen(true)],
                ['Compare versions', 'Review schema drift and KPI changes.', () => setViewMode(previousDataset ? 'previous' : 'current')],
                ['Trigger re-analysis', 'Refresh insights in place.', triggerReanalysis],
              ].map(([label, copy, action]) => (
                <button key={label as string} onClick={action as () => void} className="rounded-lg border border-stone-200 bg-stone-50 p-4 text-left transition hover:border-red-200 hover:bg-red-50/50">
                  <CheckCircle2 className="mb-3 text-red-700" size={18} />
                  <span className="text-sm font-semibold text-stone-900">{label as string}</span>
                  <p className="mt-1 text-xs leading-5 text-stone-500">{copy as string}</p>
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-lg border border-amber-200 bg-amber-50/70 p-6">
            <div className="flex items-start gap-4">
              <div className="rounded-lg bg-white p-2 text-amber-700 ring-1 ring-amber-200">
                <AlertCircle size={19} />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-stone-950">Key Risk Factors</h3>
                <p className="mt-2 text-sm leading-6 text-stone-600">
                  Multiple joins at ingestion may cause extract bloat. Incremental load strategy and source integrity rules should be confirmed.
                </p>
              </div>
            </div>
          </div>
        </section> */}

        {/* {comparison && (
          <section className="rounded-lg border border-stone-200 bg-white p-6">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <GitCompare size={18} className="text-red-700" />
                <h3 className="text-base font-semibold text-stone-950">Version Comparison</h3>
              </div>
              <span className="rounded-full bg-red-50 px-3 py-1 text-xs font-semibold text-red-800">
                +{currentDataset.addedTables} tables, -{currentDataset.removedTables} tables, {currentDataset.relationshipChanges} relationship changes
              </span>
            </div>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
              {comparison.map((item) => (
                <div key={item.label} className="rounded-lg bg-stone-50 p-4">
                  <p className="text-xs font-medium text-stone-500">{item.label}</p>
                  <div className="mt-3 flex items-center justify-between gap-2 text-sm">
                    <span className="text-stone-500">{item.before}</span>
                    <ArrowRightLeft size={14} className="text-red-700" />
                    <span className="font-semibold text-stone-950">{item.after}</span>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )} */}

        {/* <section className="rounded-lg border border-stone-200 bg-white p-6">
          <div className="mb-4 flex items-center gap-2">
            <History size={18} className="text-red-700" />
            <h3 className="text-base font-semibold text-stone-950">Upload History</h3>
          </div>
          <div className="space-y-2">
            {[currentDataset, ...history].map((item) => (
              <div key={`${item.id}-${item.uploadedAt}`} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-stone-200 bg-stone-50 px-4 py-3">
                <div>
                  <p className="text-sm font-semibold text-stone-950">{item.name}</p>
                  <p className="text-xs text-stone-500">{item.id} · {formatSize(item.size)} · {new Date(item.uploadedAt).toLocaleString()}</p>
                </div>
                <span className={`rounded-full px-3 py-1 text-xs font-semibold ${item.id === currentDataset.id ? 'bg-emerald-50 text-emerald-700' : 'bg-stone-200 text-stone-600'}`}>
                  {item.id === currentDataset.id ? 'Active' : 'Archived'}
                </span>
              </div>
            ))}
          </div>
        </section> */}
      </div>

      <Dialog open={isModalOpen} onClose={uploadState === 'uploading' || uploadState === 'validating' ? undefined : () => setIsModalOpen(false)} maxWidth="md" fullWidth>
        <DialogContent sx={{ p: 0, borderRadius: '8px', overflow: 'hidden' }}>
          <div className="bg-white">
            <div className="flex items-start justify-between border-b border-stone-200 px-6 py-5">
              <div>
                <h2 className="text-xl font-semibold text-stone-950">Update Dataset</h2>
                <p className="mt-1 text-sm text-stone-500">Upload, validate, compare, and reprocess a replacement file.</p>
              </div>
              <IconButton disabled={uploadState === 'uploading' || uploadState === 'validating'} onClick={() => setIsModalOpen(false)}>
                <X size={18} />
              </IconButton>
            </div>
            <div className="p-6">
              <input ref={inputRef} type="file" multiple accept=".pbix" hidden onChange={(event) => beginUpload(event.target.files || undefined)} />
              <div className="mb-5 rounded-2xl border border-stone-200 bg-stone-50 px-4 py-4">
                <p className="text-xs font-semibold uppercase tracking-wider text-stone-500">Current dataset</p>
                <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-stone-950">{currentDataset.name}</p>
                    <p className="mt-1 text-xs text-stone-500">Last updated {new Date(currentDataset.uploadedAt).toLocaleString()}</p>
                  </div>
                  <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-stone-600 ring-1 ring-stone-200">
                    {currentDataset.tables} tables
                  </span>
                </div>
              </div>
              {uploadState === 'idle' ? (
                <div
                  onClick={() => inputRef.current?.click()}
                  onDragEnter={(event) => {
                    event.preventDefault();
                    setIsDragging(true);
                  }}
                  onDragOver={(event) => event.preventDefault()}
                  onDragLeave={() => setIsDragging(false)}
                  onDrop={(event) => {
                    event.preventDefault();
                    setIsDragging(false);
                    beginUpload(event.dataTransfer.files || undefined);
                  }}
                  className={`flex min-h-[250px] cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed p-8 text-center transition ${isDragging ? 'border-red-500 bg-red-50' : 'border-stone-300 bg-stone-50 hover:border-red-300 hover:bg-red-50/40'
                    }`}
                >
                  <UploadCloud size={42} className="text-red-700" />
                  <h3 className="mt-4 text-lg font-semibold text-stone-950">Drop updated file here</h3>
                  <p className="mt-2 max-w-md text-sm leading-6 text-stone-500">
                    The current dashboard version will be preserved before this dataset becomes active.
                  </p>
                  <Button sx={{ mt: 3, borderRadius: '8px', textTransform: 'none', color: '#c8102e', borderColor: 'rgba(200,16,46,0.28)' }} variant="outlined">
                    Browse Files
                  </Button>
                </div>
              ) : (
                <div className="rounded-lg border border-stone-200 bg-stone-50 p-5">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div className="flex items-start gap-3">
                      <div className={`grid h-11 w-11 place-items-center rounded-lg ${uploadState === 'complete' ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'}`}>
                        {uploadState === 'complete' ? <Check size={21} /> : <Loader2 className="animate-spin" size={21} />}
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-stone-950">
                          {uploadFiles.length === 1 ? uploadFiles[0].name : `${uploadFiles.length} files selected`}
                        </p>
                        <p className="mt-1 text-xs text-stone-500">{validationLabel}</p>
                      </div>
                    </div>
                    <span className="text-2xl font-semibold text-stone-950">{uploadProgress}%</span>
                  </div>
                  <div className="mt-5 h-2 overflow-hidden rounded-full bg-white">
                    <div className={`h-full rounded-full transition-all ${uploadState === 'complete' ? 'bg-emerald-500' : 'bg-gradient-to-r from-red-700 to-red-900'}`} style={{ width: `${uploadProgress}%` }} />
                  </div>
                  <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3">
                    <div className="rounded-lg bg-white p-3">
                      <p className="text-xs text-stone-500">Uploaded</p>
                      <p className="mt-1 text-sm font-semibold text-stone-950">{formatSize(uploadedBytes)} / {formatSize(totalUploadSize)}</p>
                    </div>
                    <div className="rounded-lg bg-white p-3">
                      <p className="text-xs text-stone-500">Remaining</p>
                      <p className="mt-1 text-sm font-semibold text-stone-950">{uploadState === 'complete' ? 'Done' : estimatedRemaining}</p>
                    </div>
                    <div className="rounded-lg bg-white p-3">
                      <p className="text-xs text-stone-500">Validation</p>
                      <p className="mt-1 text-sm font-semibold text-stone-950">{uploadState === 'validating' ? 'Schema checks' : uploadState === 'complete' ? 'Passed' : 'Queued'}</p>
                    </div>
                  </div>
                  <div className="mt-5 flex flex-wrap justify-end gap-2">
                    {uploadFiles.length > 0 && (
                      <div className="mr-auto grid w-full gap-2">
                        {uploadFiles.map((file) => {
                          const isValid = file.name.toLowerCase().endsWith('.pbix');
                          return (
                            <div key={`${file.name}-${file.size}`} className={`flex items-center justify-between rounded-lg border px-3 py-2 ${isValid ? 'border-stone-200 bg-white' : 'border-red-200 bg-red-50'}`}>
                              <div className="min-w-0">
                                <p className="truncate text-sm font-medium text-stone-900">{file.name}</p>
                                <p className={`text-xs ${isValid ? 'text-stone-500' : 'text-red-700'}`}>
                                  {isValid ? formatSize(file.size) : 'Uploaded file is not a valid .pbix file.'}
                                </p>
                              </div>
                              <span className={`rounded-full px-2.5 py-1 text-[10px] font-bold ${isValid ? 'bg-emerald-50 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
                                {isValid ? 'VALID' : 'FAILED'}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    )}
                    {(uploadState === 'uploading' || uploadState === 'validating') && (
                      <Button onClick={cancelUpload} variant="outlined" sx={{ borderRadius: '8px', textTransform: 'none', color: '#8f0d22', borderColor: 'rgba(200,16,46,0.28)' }}>Cancel upload</Button>
                    )}
                    {uploadState === 'error' && (
                      <Button onClick={retryUpload} variant="outlined" sx={{ borderRadius: '8px', textTransform: 'none', color: '#8f0d22', borderColor: 'rgba(200,16,46,0.28)' }}>Retry upload</Button>
                    )}
                    <Button disabled={uploadState === 'uploading' || uploadState === 'validating'} onClick={() => inputRef.current?.click()} variant="contained" sx={{ borderRadius: '8px', textTransform: 'none', background: '#c8102e' }}>
                      Replace file
                    </Button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog
        open={isDatasetLibraryOpen}
        onClose={() => setIsDatasetLibraryOpen(false)}
        maxWidth="lg"
        fullWidth
      >
        <DialogContent
          sx={{
            p: 0,
            borderRadius: "20px",
            overflow: "hidden",
            background: "#fff"
          }}
        >
          <div className="flex flex-col h-[75vh]">

            {/* Header */}
            <div className="sticky top-0 z-10 bg-white border-b border-stone-200 px-7 py-5">
              <div className="flex items-center justify-between">

                <div>
                  <h2 className="text-2xl font-semibold text-stone-900">
                    Dataset Library
                  </h2>

                  <p className="mt-1 text-sm text-stone-500">
                    Browse and switch between previously processed Power BI datasets
                  </p>

                  <div className="mt-2 inline-flex rounded-full bg-red-50 px-3 py-1 text-xs font-medium text-red-700">
                    {reports.length} datasets available
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <Button
                    onClick={refreshReports}
                    variant="outlined"
                    startIcon={
                      <RefreshCw
                        size={16}
                        color="#8f0d22"
                        strokeWidth={2.2}
                      />
                    }
                    sx={{
                      borderRadius: "10px",
                      textTransform: "none",
                      color: "#8f0d22",
                      borderColor: "rgba(200,16,46,0.25)",
                      backgroundColor: "#fff",

                      "&:hover": {
                        backgroundColor: "#fff5f6",
                        borderColor: "#c8102e"
                      },

                      "& .MuiButton-startIcon": {
                        marginRight: "6px"
                      }
                    }}
                  >
                    Refresh
                  </Button>

                  <IconButton
                    onClick={() =>
                      setIsDatasetLibraryOpen(false)
                    }
                  >
                    <X size={18} />
                  </IconButton>
                </div>
              </div>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-auto px-7 py-6 bg-stone-50/40">

              {reportError && (
                <div className="mb-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
                  {reportError}
                </div>
              )}

              {reports.length === 0 && !reportError && (
                <div className="rounded-xl border border-dashed border-stone-300 bg-white p-8 text-center text-stone-500">
                  No processed datasets found
                </div>
              )}

              <div className="rounded-2xl border border-stone-200 bg-white overflow-hidden">
                <table className="w-full text-sm">

                  {/* Table Header */}
                  <thead className="bg-stone-50 border-b border-stone-200 sticky top-0 z-10">
                    <tr>
                      <th className="px-4 py-3 text-left font-semibold text-stone-600">
                        No.
                      </th>

                      <th className="px-4 py-3 text-left font-semibold text-stone-600">
                        Dataset Name
                      </th>

                      <th className="px-4 py-3 text-left font-semibold text-stone-600">
                        Tool
                      </th>

                      <th className="px-4 py-3 text-left font-semibold text-stone-600">
                        Status
                      </th>

                      <th className="px-4 py-3 text-left font-semibold text-stone-600">
                        Completed At
                      </th>

                      <th className="px-4 py-3 text-left font-semibold text-stone-600">
                        Runtime
                      </th>

                      <th className="px-4 py-3 text-left font-semibold text-stone-600">
                        Action
                      </th>
                    </tr>
                  </thead>

                  {/* Table Body */}
                  <tbody>
                    {reports.map((report, index) => {
                      const status = (report.status || "").toUpperCase();

                      const isActive =
                        selectedReportFile === report.file_name;

                      return (
                        <tr
                          key={report.report_id || report.file_name}
                          className={`border-b border-stone-100 hover:bg-red-50 transition ${isActive ? "bg-red-50" : ""
                            }`}
                        >
                          {/* Serial Number */}
                          <td className="px-4 py-4 font-medium text-stone-600">
                            {index + 1}
                          </td>

                          {/* Dataset Name */}
                          <td className="px-4 py-4">
                            <div>
                              <p className="font-medium text-stone-900">
                                {report.file_name}
                              </p>
                              <p className="text-xs text-stone-400 truncate max-w-[250px]">
                                {report.report_id}
                              </p>
                            </div>
                          </td>

                          {/* Tool Type */}
                          <td className="px-4 py-4 capitalize">
                            {report.tool_type}
                          </td>

                          {/* Status */}
                          <td className="px-4 py-4">
                            <span
                              className={`rounded-full px-3 py-1 text-xs font-semibold ${status === "SUCCESS"
                                  ? "bg-emerald-50 text-emerald-700"
                                  : status === "FAILED"
                                    ? "bg-red-50 text-red-700"
                                    : "bg-stone-100 text-stone-600"
                                }`}
                            >
                              {status}
                            </span>
                          </td>

                          {/* Completed Time */}
                          <td className="px-4 py-4 text-stone-600">
                            {report.completed_at
                              ? new Date(report.completed_at).toLocaleString()
                              : "--"}
                          </td>

                          {/* Runtime */}
                          <td className="px-4 py-4 text-stone-600">
                            {report.runtime_seconds
                              ? `${report.runtime_seconds}s`
                              : "--"}
                          </td>

                          {/* Action */}
                          <td className="px-4 py-4">
                            <Button
                              size="small"
                              onClick={() => {
                                setSelectedReportFile(report.file_name);
                                setSelectedReport(report);
                              }}
                              sx={{
                                minWidth: "40px",
                                width: "40px",
                                height: "40px",
                                borderRadius: "10px",
                                color: isActive ? "#ffffff" : "#8f0d22",
                                backgroundColor: isActive ? "#16a34a" : "#fff",
                                border: isActive
                                  ? "none"
                                  : "1px solid rgba(200,16,46,0.2)",
                                textTransform: "none",

                                "&:hover": {
                                  backgroundColor: isActive
                                    ? "#15803d"
                                    : "#fff5f6"
                                }
                              }}
                            >
                              {isActive ? (
                                <Check size={18} />
                              ) : (
                                <Database size={18} />
                              )}
                            </Button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Footer */}
            <div className="sticky bottom-0 border-t border-stone-200 bg-white px-7 py-4">
              <div className="flex items-center justify-between">

                <div className="text-sm text-stone-500">
                  {selectedReport
                    ? `Selected: ${selectedReport.file_name}`
                    : "Select a dataset to continue"}
                </div>

                <div className="flex gap-3">
                  <Button
                    onClick={() =>
                      setIsDatasetLibraryOpen(false)
                    }
                    variant="outlined"
                    sx={{
                      borderRadius: "10px",
                      textTransform: "none"
                    }}
                  >
                    Cancel
                  </Button>

                  <Button
                    onClick={async () => {
                      if (selectedReport) {
                        await loadReport(
                          selectedReport.file_name,
                          selectedReport
                        );
                        setIsDatasetLibraryOpen(false);
                      }
                    }}
                    disabled={!selectedReport}
                    variant="contained"
                    sx={{
                      borderRadius: "10px",
                      textTransform: "none",
                      px: 3,
                      color: "#ffffff", // force white text
                      background:
                        "linear-gradient(135deg, #c8102e 0%, #8f0d22 100%)",

                      "&:hover": {
                        background:
                          "linear-gradient(135deg, #a30d25 0%, #7a0b1d 100%)"
                      },

                      "&.Mui-disabled": {
                        background: "#e5e7eb",
                        color: "#9ca3af"
                      }
                    }}
                  >
                    Load Dataset
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>
      <Drawer
        anchor="right"
        open={isJsonDrawerOpen}
        onClose={() => setIsJsonDrawerOpen(false)}
      >
        <div className="flex h-full w-[700px] flex-col bg-white">

          {/* Header */}
          <div className="flex items-center justify-between border-b border-stone-200 px-6 py-4">
            <div>
              <h2 className="text-lg font-semibold text-stone-950">
                Raw API Response
              </h2>
            </div>

            <IconButton
              onClick={() => setIsJsonDrawerOpen(false)}
            >
              <X size={18} />
            </IconButton>
          </div>

          {/* JSON Body */}
          <div className="flex-1 overflow-auto bg-stone-950 p-5">
            <pre className="text-sm text-green-400 whitespace-pre-wrap break-words">
              {JSON.stringify(rawJsonData, null, 2)}
            </pre>
          </div>
        </div>
      </Drawer>
    </ContentCard>
  );
}
