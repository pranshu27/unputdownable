import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ArrowLeft, ArrowRight, Check, X, CheckCircle, Brain, Zap, Sparkles, CloudUpload, Loader2, FileSearch, Cpu, Database, Clock3, LogOut } from 'lucide-react';
import { Button } from '../../CodeGen/CodeGenComponents/button.tsx';
import { cn } from '../../../Lib/utils.ts';
import { useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import StepIndicator from '../../Upload/components/StepIndicator.tsx';
import FileUploadPanel from '../../Upload/components/FileUploadPanel.js';
import { setUploadedFileContext } from '../../../utils/uploadedFileContext.ts';
// // import PlatformSelector from '../../Upload/components/PlatformSelector.js'; // Commented out - Source platform auto-detected
// import FrameworkSelector from '../../Upload/components/FrameworkSelector.js';  
import { frameworks as frameworkOptions } from '../../Upload/components/FrameworkSelector.tsx';
import AIModelSelector, { models as aiModels } from '../../Upload/components/AIModelSelector.js';
import AnalysisPanel from '../../Upload/components/AnalysisPanel.js';
import PowerBiIcon from '../../../Assets/powerbi.png';
import TableautIcon from '../../../Assets/tableau-icon.svg';
import {FileCode} from 'lucide-react';
import { setApiData } from "../../../utils/DataSlice.ts";
import { useDispatch } from 'react-redux';
import { setFormData } from '../../../utils/formSlice.ts';
import { fetchPowerBiReport, getJobProgress, listPowerBiReports, uploadPowerBiDataset } from '../../../services/powerbiReports.ts';
import { triggerReValidationBackground } from '../../../services/ValidationJobRunner.ts';
import { Dialog, DialogContent } from '@mui/material';


const ANALYSIS_STAGES = [
  { id: 1, icon: CloudUpload, label: 'Uploading file', detail: 'Transferring your file securely…', color: '#3B82F6' },
  { id: 2, icon: FileSearch, label: 'Parsing structure', detail: 'Reading ETL mappings and metadata…', color: '#8B5CF6' },
  { id: 3, icon: Brain, label: 'AI analysis', detail: 'Running deep pattern recognition…', color: '#EC4899' },
  { id: 4, icon: Cpu, label: 'Generating migration', detail: 'Building transformation strategy…', color: '#F59E0B' },
  { id: 5, icon: Sparkles, label: 'Finalizing insights', detail: 'Preparing your migration report…', color: '#10B981' },
];


function EnterpriseWorkflowCard({ fileName, isAnalyzing, isDone, isError, apiUploadProgress, apiStatusMessage, apiErrorMessage, jobFiles }) {
  const [analysisProgress, setAnalysisProgress] = useState(0);
  const [stageIndex, setStageIndex] = useState(0);
  const intervalRef = useRef(null);

  // Determine if we are uploading
  const isUploading = apiUploadProgress > 0 && apiUploadProgress < 100 && !isError;
  const isAnalysisPhase = isAnalyzing && !isDone && !isError && !isUploading;

  useEffect(() => {
    if (isAnalysisPhase) {
      intervalRef.current = setInterval(() => {
        setAnalysisProgress((prev) => {
          const next = prev + (Math.random() * 3 + 1);
          const newStage = Math.min(
            Math.floor((next / 100) * ANALYSIS_STAGES.length),
            ANALYSIS_STAGES.length - 1
          );
          setStageIndex(newStage);
          if (next >= 92) {
            clearInterval(intervalRef.current);
            return 92;
          }
          return next;
        });
      }, 180);
    }
    if (isDone) {
      clearInterval(intervalRef.current);
      setAnalysisProgress(100);
      setStageIndex(ANALYSIS_STAGES.length - 1);
    }
    if (isError) {
      clearInterval(intervalRef.current);
    }
    return () => clearInterval(intervalRef.current);
  }, [isAnalysisPhase, isDone, isError]);

  let currentLabel = '';
  let currentDetail = '';

  if (isError) {
    currentLabel = 'Analysis Failed';
    currentDetail = apiErrorMessage || 'Something went wrong during processing.';
  } else if (isDone) {
    currentLabel = 'Analysis Complete';
    currentDetail = 'Generating insights and navigating...';
  } else if (isUploading) {
    currentLabel = 'Uploading Dataset';
    currentDetail = apiStatusMessage || 'Transferring securely to the cloud...';
  } else {
    currentLabel = ANALYSIS_STAGES[stageIndex]?.label || 'Processing';
    currentDetail = apiStatusMessage || ANALYSIS_STAGES[stageIndex]?.detail || 'Analyzing file...';
  }

  const effectiveProgress = isUploading ? apiUploadProgress : isDone ? 100 : isError ? 100 : analysisProgress;

  return (
    <div className="rounded-xl border border-stone-200 bg-white shadow-sm overflow-hidden mb-4">
      <div className="p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border ${isError ? 'border-red-200 bg-red-50' : isDone ? 'border-emerald-200 bg-emerald-50' : 'border-stone-200 bg-stone-50'}`}>
              {isDone ? (
                <CheckCircle className="h-5 w-5 text-emerald-600" />
              ) : isError ? (
                <X className="h-5 w-5 text-red-600" />
              ) : (
                <Database className="h-5 w-5 text-stone-600" />
              )}
            </div>
            <div>
              <p className="text-sm font-bold text-stone-900 truncate max-w-[300px]">{fileName}</p>
              <div className="flex items-center gap-2 mt-0.5">
                {!isDone && !isError && <Loader2 className="h-3 w-3 animate-spin text-stone-500" />}
                <p className={`text-xs font-medium ${isDone ? 'text-emerald-600' : isError ? 'text-red-600' : 'text-stone-700'}`}>
                  {currentLabel}
                </p>
                <span className="text-[10px] text-stone-400">— {currentDetail}</span>
              </div>
            </div>
          </div>
          <div className="text-right">
            <span className={`text-sm font-bold tabular-nums ${isDone ? 'text-emerald-600' : isError ? 'text-red-600' : 'text-stone-900'}`}>
              {Math.round(effectiveProgress)}%
            </span>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="relative h-1 w-full overflow-hidden rounded-full bg-stone-100">
          <div
            className={`absolute inset-y-0 left-0 rounded-full transition-all duration-300 ease-out ${isDone ? 'bg-emerald-500' : isError ? 'bg-red-500' : 'bg-[#c8102e]'}`}
            style={{ width: `${effectiveProgress}%` }}
          />
        </div>

        {/* Additional job files (if any) */}
        {jobFiles && jobFiles.length > 0 && !isDone && (
          <div className="mt-4 flex flex-col gap-2">
            {jobFiles.map(file => {
              const status = String(file.status || '').toLowerCase();
              return (
                <div key={file.file_name} className="flex items-center justify-between text-xs px-3 py-2 rounded-lg bg-stone-50 border border-stone-100">
                  <span className="font-medium text-stone-700 truncate max-w-[300px]">{file.file_name}</span>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${status === 'failed' ? 'bg-red-100 text-red-700' : status === 'success' || status === 'completed' ? 'bg-emerald-100 text-emerald-700' : 'bg-white text-stone-500 border border-stone-200'}`}>
                    {status || 'queued'}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Main Component ────────────────────────────────────────────────────────────

export default function MigrationAgent() {
  const defaultModel = aiModels.find((item) => item.id === 'openai') 
  ? { ...aiModels.find((item) => item.id === 'openai'), selectedVersion: 'gpt-5-mini', selectedVersionLabel: 'GPT-5 Mini' }
  : null;
  const defaultFramework = frameworkOptions.find((item) => item.id === 'multiagent') || null;
  const [currentStep, setCurrentStep] = useState(1);
  const [completedSteps, setCompletedSteps] = useState([]);
  const [visitedSteps, setVisitedSteps] = useState([1]);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisDone, setAnalysisDone] = useState(false);
  const [analysisError, setAnalysisError] = useState(false);
  const [selectedExistingReport, setSelectedExistingReport] = useState<typeof existingReports[0] | null>(null);
  const [apiUploadProgress, setApiUploadProgress] = useState(0);
  const [apiStatusMessage, setApiStatusMessage] = useState('');
  const [apiErrorMessage, setApiErrorMessage] = useState('');
  const [jobFiles, setJobFiles] = useState([]);
  const [existingReports, setExistingReports] = useState([]);
  const [databaseReports, setDatabaseReports] = useState([]);
  const [selectedDatabaseReport, setSelectedDatabaseReport] = useState(null);
  const [isLoadingDatabaseReports, setIsLoadingDatabaseReports] = useState(false);
  const [databaseReportsError, setDatabaseReportsError] = useState('');
  const [isDatabaseDashboardOpen, setIsDatabaseDashboardOpen] = useState(false);
  const [isExistingModalOpen, setIsExistingModalOpen] = useState(false);
  const [pendingAnalyzeAction, setPendingAnalyzeAction] = useState(null);
  const dispatch = useDispatch();

  // Form state
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [sourcePlatform, setSourcePlatform] = useState(null);
  // const [framework, setFramework] = useState(defaultFramework); // Commented out - Framework selection hidden
  const framework = defaultFramework; // Use default framework
  const [model, setModel] = useState(defaultModel);

  React.useEffect(() => {
    if (currentStep === 2 && model && !completedSteps.includes(2)) {
      setCompletedSteps(prev => [...new Set([...prev, 2])]);
    }
  }, [currentStep, framework, model, completedSteps]);

  React.useEffect(() => {
    // Clear all analysis-specific localStorage when starting a new session on /migration
    const keepKeys = ['isLoggedIn', 'codegenTheme', 'jira_credentials', 'jnj:tracked-jobs'];
    const keysToRemove = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      // We purposefully DO NOT preserve jnj:job-result: so that old validation data is completely wiped
      if (key && !keepKeys.includes(key)) {
        keysToRemove.push(key);
      }
    }
    keysToRemove.forEach(k => localStorage.removeItem(k));
  }, []);

  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const handleLogout = () => {
    localStorage.clear();
    navigate('/login');
  };

  const generateCacheKey = ({ fileName, etlTool, model }) => {
    return ['analysis', fileName, etlTool, model];
  };

  const selectedFile = selectedFiles[0] || null;
  const validExtensions = ['.pbix', '.twb', '.twbx'];
  const isValidUploadFile = (fileName) =>
    validExtensions.some((extension) => fileName.toLowerCase().endsWith(extension));
  const getToolForFile = (fileName) => {
    const normalizedName = fileName.toLowerCase();
    if (normalizedName.endsWith('.pbix')) return 'powerbi';
    if (normalizedName.endsWith('.twb') || normalizedName.endsWith('.twbx')) return 'tableau-workbook';
    return null;
  };

  const getPlatformForTool = (toolName, fileName = '') => {
    const normalizedTool = String(toolName || '').toLowerCase();
    if (normalizedTool === 'powerbi' || fileName.toLowerCase().endsWith('.pbix')) {
      return { id: 'powerbi', name: 'Power BI', icon: PowerBiIcon };
    }
    if (normalizedTool === 'tableau-workbook' || fileName.toLowerCase().endsWith('.twb') || fileName.toLowerCase().endsWith('.twbx')) {
      return { id: 'tableau-workbook', name: 'Tableau', icon: TableautIcon };
    }
    return null;
  };

  // Auto-detect source platform based on file extension
  const detectSourcePlatform = (file) => {
    if (!file) return null;
    const detectedTool = getToolForFile(file.name);

    return getPlatformForTool(detectedTool, file.name);
  };

  const loadDatabaseReports = async () => {
    setIsLoadingDatabaseReports(true);
    setDatabaseReportsError('');
    try {
      const tools = ['powerbi', 'tableau-workbook'];
      const results = await Promise.allSettled(
        tools.map(async (toolName) => {
          const reports = await listPowerBiReports(toolName);
          return reports.map((report) => ({
            ...report,
            tool_type: report.tool_type || toolName,
          }));
        })
      );
      const reportMap = new Map();
      const loadedReports = results.reduce((acc, result) => {
        if (result.status === 'fulfilled') {
          acc.push(...result.value);
        }
        return acc;
      }, []);
      loadedReports
        .filter((report) => report?.file_name)
        .filter((report) => String(report.status || '').toUpperCase() === 'SUCCESS')
        .forEach((report) => {
          const key = report.report_id || `${report.tool_type}:${report.file_name}`;
          if (!reportMap.has(key)) reportMap.set(key, report);
        });
      const nextReports = Array.from(reportMap.values());
      setDatabaseReports(nextReports);
      if (!nextReports.length) {
        toast.info('No processed files found', {
          description: 'PostgreSQL did not return any completed datasets yet.',
        });
      }
      if (results.some((result) => result.status === 'rejected') && nextReports.length) {
        toast.info('Some files could not be fetched', {
          description: 'Loaded the available processed files.',
        });
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to fetch existing files.';
      setDatabaseReportsError(message);
      toast.error('Unable to fetch files', { description: message });
    } finally {
      setIsLoadingDatabaseReports(false);
    }
  };

  const openDatabaseDashboard = () => {
    setIsDatabaseDashboardOpen(true);
    if (!databaseReports.length && !isLoadingDatabaseReports) {
      loadDatabaseReports();
    }
  };

  const selectDatabaseReport = (report) => {
    const fileName = report.file_name;
    const fileRef = { name: fileName, fromDatabase: true };
    const platform = getPlatformForTool(report.tool_type, fileName) || detectSourcePlatform(fileRef);
    if (!platform) {
      toast.error('Unsupported file', {
        description: 'Only .pbix, .twb, and .twbx files can be analyzed.',
      });
      return;
    }

    setSelectedDatabaseReport(report);
    setSelectedFiles([fileRef]);
    setUploadedFileContext([fileRef]);
    setSourcePlatform(platform);
    setExistingReports([{ file: fileRef, report: null, reportMeta: report }]);
    setSelectedExistingReport({ file: fileRef, report: null, reportMeta: report });
    setCompletedSteps((prev) => [...new Set([...prev, 1])]);
    toast.success('Existing file selected', {
      description: `${fileName} is ready to load from PostgreSQL.`,
    });
  };

  const analyzeDatabaseReport = async () => {
    if (!selectedDatabaseReport) {
      toast.info('Select a file', {
        description: 'Choose an existing file from PostgreSQL before analyzing.',
      });
      return;
    }

    const fileName = selectedDatabaseReport.file_name;
    const activeTool = selectedDatabaseReport.tool_type || getToolForFile(fileName) || 'powerbi';
    const activeBaseName = fileName.substring(0, fileName.lastIndexOf('.')) || fileName;

    setIsAnalyzing(true);
    setAnalysisDone(false);
    setAnalysisError(false);
    setApiUploadProgress(100);
    setApiErrorMessage('');
    setApiStatusMessage('Loading existing dataset from PostgreSQL...');
    setJobFiles([]);

    try {
      const reportPayload = await fetchPowerBiReport(fileName, activeTool, {
        reportId: selectedDatabaseReport.report_id,
      });

      localStorage.setItem('existingReports', JSON.stringify([{ fileName }]));
      localStorage.setItem('activePowerBiReportFile', fileName);
      localStorage.setItem('activePowerBiReportId', selectedDatabaseReport.report_id || '');
      localStorage.setItem('activePowerBiReportData', JSON.stringify(reportPayload));
      localStorage.setItem('fileDetails', JSON.stringify({
        fileName: activeBaseName,
        etlTool: activeTool,
        model: model?.id,
        technology: null,
        framework: framework?.id,
      }));

      dispatch(setApiData(reportPayload));
      dispatch(setFormData({
        fileName: activeBaseName,
        etlTool: activeTool,
        model,
        technology: null,
        framework,
      }));
      window.dispatchEvent(new Event('jnj:active-report-changed'));
      setCompletedSteps((prev) => [...new Set([...prev, 1, 2, 3, 5])]);
      setAnalysisDone(true);
      setIsDatabaseDashboardOpen(false);
      toast.success('Analysis ready', {
        description: `${fileName} is loaded in the workspace.`,
      });
      await new Promise((resolve) => setTimeout(resolve, 500));
      navigate('/overview');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to load the selected file.';
      setAnalysisError(true);
      setApiErrorMessage(message);
      toast.error('Unable to analyze file', { description: message });
    } finally {
      setIsAnalyzing(false);
    }
  };
  const handleFileSelect = (files) => {
    const nextFiles = Array.isArray(files)
      ? files
      : files
      ? [files]
      : [];
  
    const validFiles = nextFiles.filter((file) => isValidUploadFile(file.name));
    const ignoredFiles = nextFiles.length - validFiles.length;

    if (!validFiles.length) {
      setSelectedFiles([]);
      setSourcePlatform(null);
      toast.error("Unsupported file format", {
        description: "No valid files found. Please upload only .pbix, .twb, or .twbx files.",
      });
      return;
    }

    if (ignoredFiles > 0) {
      toast.info("Some files were ignored", {
        description: `${ignoredFiles} unsupported file${ignoredFiles === 1 ? '' : 's'} were skipped.`,
      });
    }

    setSelectedDatabaseReport(null);
    setSelectedFiles(validFiles);
    setUploadedFileContext(validFiles);
  
    if (validFiles.length) {
      // single file → detect platform
      if (validFiles.length === 1) {
        const detectedPlatform = detectSourcePlatform(validFiles[0]);
  
        if (detectedPlatform) {
          setSourcePlatform(detectedPlatform);
        } else {
          toast.error("Unsupported file format", {
            description:
              "Please upload only .pbix, .twb, or .twbx files.",
          });
          setSelectedFiles([]);
          setSourcePlatform(null);
          return;
        }
      }
  
      // multiple files → allow mixed uploads
      else {
      setSourcePlatform({
        id: "multi-platform",
        name: "Multi Source Upload",
      });
      }
  
      if (!completedSteps.includes(1)) {
        setCompletedSteps((prev) => [...new Set([...prev, 1])]);
      }
    }
  };

  // const handleSourceSelect = (platform) => { // Commented out - Source platform auto-detected
  //   setSourcePlatform(platform);
  //   if (platform && !completedSteps.includes(2)) {
  //     setCompletedSteps([...completedSteps, 2]);
  //   }
  // };

  // const handleFrameworkSelect = (fw) => {
  //   setFramework(fw);
  //   if (fw && !completedSteps.includes(3)) {
  //     setCompletedSteps([...completedSteps, 3]);
  //   }
  // };

  const handleModelSelect = (m) => {
    setModel(m);
    if (m && !completedSteps.includes(2)) {
      setCompletedSteps([...completedSteps, 2]);
    }
  };

  const handleRemoveFile = (indexToRemove: number | 'all') => {
    if (indexToRemove === 'all') {
      setSelectedFiles([]);
      setUploadedFileContext([]);
      setSourcePlatform(null);
      setSelectedDatabaseReport(null);
      return;
    }  
    const updated = selectedFiles.filter((_, i) => i !== indexToRemove);
      setSelectedFiles(updated);
      setUploadedFileContext(updated);
      if (updated.length === 0) {
        setSourcePlatform(null);
        setSelectedDatabaseReport(null);
      }
    };

    const handleAnalyze = async (options = {}) => {
      const { skipExistingCheck = false } = options;
    
      if (!selectedFile || !sourcePlatform || !model) {
        toast.info('Missing Fields', {
          description: 'Please upload supported .pbix, .twb, or .twbx files and select an AI model.',
        });
        return;
      }
    
      setIsAnalyzing(true);
      setAnalysisDone(false);
      setAnalysisError(false);
      setApiUploadProgress(0);
      setApiStatusMessage('');
      setApiErrorMessage('');
      setJobFiles([]);
    
      try {
        const fileNameWithExtension = selectedFile.name;
        const fileName = fileNameWithExtension.substring(0, fileNameWithExtension.lastIndexOf('.')) || fileNameWithExtension;
        const etlTool = sourcePlatform?.id;
        const modelId = model.id;
        const technology = null;
    
        localStorage.setItem('fileDetails', JSON.stringify({
          fileName,
          etlTool,
          model: modelId,
          technology,
          framework: framework?.id,
        }));

        if (selectedFile.fromDatabase && selectedDatabaseReport) {
          const existingTool = selectedDatabaseReport.tool_type || etlTool;
          const existingEntry = {
            file: selectedFile,
            report: null,
            reportMeta: selectedDatabaseReport,
          };
          setExistingReports([existingEntry]);
          setSelectedExistingReport(existingEntry);
          setPendingAnalyzeAction({ fileName, etlTool: existingTool, modelId, technology, frameworkId: framework?.id });
          setApiStatusMessage('Existing dataset found. Waiting for your choice...');
          setIsExistingModalOpen(true);
          setIsAnalyzing(false);
          return;
        }

        // Validate file types
        const invalidFiles = selectedFiles.filter((file) => !isValidUploadFile(file.name));
        if (invalidFiles.length) {
          setJobFiles(invalidFiles.map((file) => ({
            file_name: file.name,
            status: 'failed',
            error: 'Uploaded file is not supported. Only .pbix, .twb, and .twbx files are allowed.',
          })));
          throw new Error('Uploaded file is not supported. Only .pbix, .twb, and .twbx files are allowed.');
        }
    
        const isMultiFile = selectedFiles.length > 1;
        let filesToUpload = selectedFiles;
    
        // Check for existing processed datasets
        if (!skipExistingCheck) {
          setApiStatusMessage('Checking existing processed dataset...');
    
          const filesByTool = selectedFiles.reduce((acc, file) => {
            const toolName = getToolForFile(file.name);
            if (!toolName) return acc;
            if (!acc[toolName]) acc[toolName] = [];
            acc[toolName].push(file);
            return acc;
          }, {});
    
          const existingFilesByName = new Set();
          const existingReportsByName = new Map();
    
          for (const [toolName, files] of Object.entries(filesByTool)) {
            const reportHistory = await listPowerBiReports(toolName);
            reportHistory
              .filter((report) => String(report.status || '').toUpperCase() === 'SUCCESS')
              .forEach((report) => {
                if (!existingReportsByName.has(report.file_name)) {
                  existingReportsByName.set(report.file_name, report);
                }
              });
            files.forEach((file) => {
              if (existingReportsByName.has(file.name)) {
                existingFilesByName.add(file.name);
              }
            });
          }
    
          const matchedReports = selectedFiles
            .filter((file) => existingFilesByName.has(file.name))
            .map((file) => ({
              file,
              report: null,
              reportMeta: existingReportsByName.get(file.name),
            }));
    
          if (matchedReports.length) {
            localStorage.setItem('existingReports', JSON.stringify(
              matchedReports.map((entry) => ({ fileName: entry.file.name }))
            ));
          }
    
          // Single file — already exists → show modal
          if (!isMultiFile && existingFilesByName.has(selectedFile.name)) {
            const existingTool = getToolForFile(selectedFile.name) || 'powerbi';
            const existingReportMeta = existingReportsByName.get(selectedFile.name);
            setApiStatusMessage('Existing dataset found. Waiting for your choice...');
            const reportData = await fetchPowerBiReport(selectedFile.name, existingTool, {
              reportId: existingReportMeta?.report_id,
            });
            const updatedMatched = [{ file: selectedFile, report: reportData, reportMeta: existingReportMeta }];
            setExistingReports(updatedMatched);
            localStorage.setItem('existingReports', JSON.stringify(
              updatedMatched.map((entry) => ({ fileName: entry.file.name }))
            ));
            setPendingAnalyzeAction({ fileName, etlTool: existingTool, modelId, technology, frameworkId: framework?.id });
            setSelectedExistingReport(updatedMatched[0]);
            setIsExistingModalOpen(true);
            setIsAnalyzing(false);
            return;
          }
    
          filesToUpload = selectedFiles.filter((file) => !existingFilesByName.has(file.name));
    
          // Multi-file — all already exist → show modal
          if (isMultiFile && existingFilesByName.size > 0 && filesToUpload.length === 0) {
            setExistingReports(matchedReports);
            setPendingAnalyzeAction({ fileName, etlTool, modelId, technology, frameworkId: framework?.id });
            setSelectedExistingReport(null);
            setIsExistingModalOpen(true);
            setIsAnalyzing(false);
            setApiStatusMessage('Existing datasets found. Waiting for your choice...');
            return;
          }
    
          // Multi-file — some already exist, upload the rest
          if (isMultiFile && existingFilesByName.size > 0 && filesToUpload.length > 0) {
            toast.info('Some files already exist', {
              description: `${existingFilesByName.size} file${existingFilesByName.size === 1 ? '' : 's'} found in the database. Uploading ${filesToUpload.length} new file${filesToUpload.length === 1 ? '' : 's'}.`,
            });
          }
        }
    
        // ─── Upload via batch (single or multiple) ───────────────────────────────
        if (filesToUpload.length === 0) {
          toast.info('Nothing to upload', { description: 'All selected files already exist.' });
          setIsAnalyzing(false);
          return;
        }
    
        const batchEtlTools = filesToUpload
          .map((file) => getToolForFile(file.name))
          .filter((toolName) => Boolean(toolName));
    
        setJobFiles(filesToUpload.map((file) => ({ file_name: file.name, status: 'uploading' })));
        setApiStatusMessage(`Uploading ${filesToUpload.length} file${filesToUpload.length === 1 ? '' : 's'}...`);
    
        const uploadResult = await uploadPowerBiDataset(
          filesToUpload,
          batchEtlTools,
          modelId,
          setApiUploadProgress
        );
    
        localStorage.setItem('powerbiPendingJob', JSON.stringify({
          job_id: uploadResult.job_id,
          file_name: selectedFile.name,
          files: filesToUpload.map((file) => ({ file_name: file.name, status: 'processing' })),
          status: uploadResult.status || 'processing',
          started_at: new Date().toISOString(),
        }));
    
        toast.success('Upload started', {
          description: `${filesToUpload.length} file${filesToUpload.length === 1 ? '' : 's'} uploaded. Processing...`,
        });
    
        // ─── Poll for progress ────────────────────────────────────────────────────
        setApiStatusMessage('Processing dataset...');
        let finalProgress = null;
        let jobCompleted = false;
    
        for (let attempt = 0; attempt < 240; attempt += 1) {
          await new Promise((resolve) => setTimeout(resolve, 2500));
    
          const progress = await getJobProgress(uploadResult.job_id);
          finalProgress = progress;
    
          const nextFiles = progress.files || [{
            file_name: progress.file_name || selectedFile.name,
            status: progress.status,
            error: progress.error,
            runtime: progress.runtime || progress.runtime_seconds,
          }];
    
          setJobFiles(nextFiles);
          localStorage.setItem('powerbiPendingJob', JSON.stringify({
            job_id: uploadResult.job_id,
            file_name: progress.file_name || selectedFile.name,
            files: nextFiles,
            status: progress.status,
            error: progress.error,
            runtime: progress.runtime || progress.runtime_seconds,
            updated_at: new Date().toISOString(),
          }));
    
          const allDone =
          nextFiles.length > 0 &&
          nextFiles.every((file) =>
            ['success', 'completed', 'failed'].includes(
              String(file.status).toLowerCase()
            )
          );
        
        const anySuccess = nextFiles.some((file) =>
          ['success', 'completed'].includes(
            String(file.status).toLowerCase()
          )
        );
        
        const anyFailed = nextFiles.some(
          (file) =>
            String(file.status).toLowerCase() ===
            'failed'
        );
        const overallStatus = progress.overall_status?.toLowerCase() || progress.status?.toLowerCase();
    
        if (
          overallStatus === 'completed' ||
          (allDone && anySuccess)
        ) {
          jobCompleted = true;
        
          setApiStatusMessage(
            'Processing completed successfully'
          );
        
          break;
        }
    
          if (overallStatus === 'failed' || (allDone && anyFailed && !anySuccess)) {
            const firstError = nextFiles.find((file) => file.error)?.error;
            throw new Error(firstError || progress.error || 'Dataset processing failed.');
          }
        }
    
        // ─── Timed out — navigate to dashboard and track there ───────────────────
        if (!jobCompleted) {
          localStorage.setItem('powerbiPendingJob', JSON.stringify({
            job_id: uploadResult.job_id,
            file_name: selectedFile.name,
            files: finalProgress?.files || filesToUpload.map((file) => ({ file_name: file.name, status: 'processing' })),
            status: 'processing',
            runtime: finalProgress?.runtime || finalProgress?.runtime_seconds,
            updated_at: new Date().toISOString(),
          }));
          setAnalysisDone(true);
          toast.success('Still processing', {
            description: 'Opening the dashboard to continue tracking progress.',
          });
          await new Promise((resolve) => setTimeout(resolve, 700));
          navigate(isMultiFile ? '/files' : '/overview');
          return;
        }
    
        // ─── Job completed ────────────────────────────────────────────────────────
    
        // Multi-file: navigate to /files and let that page handle each file
        const completedFiles = finalProgress?.files || [];
        const isPowerBiPairedUpload = isMultiFile && selectedFiles.length === 2 && selectedFiles.every((f: any) => (getToolForFile(f.name) || 'powerbi') === 'powerbi');

        if (isMultiFile && !isPowerBiPairedUpload) {
          setAnalysisDone(true);
          toast.success('Processing complete', {
            description: 'All files processed. Opening files dashboard.',
          });
          await new Promise((resolve) => setTimeout(resolve, 700));
          navigate('/files');
          return;
        }

        if (isPowerBiPairedUpload) {
          setApiStatusMessage('Fetching paired Power BI datasets...');
          const successFiles = completedFiles.filter((file: any) => String(file.status).toLowerCase() === 'success');
          
          const filesToFetch = successFiles.length === 2 ? successFiles : selectedFiles;
          
          const fetchedReports = await Promise.all(
             filesToFetch.map(async (f: any) => {
                const fname = f.file_name || f.name;
                const tool = getToolForFile(fname) || 'powerbi';
                const data = await fetchPowerBiReport(fname, tool);
                const fileObj = selectedFiles.find((s: File) => s.name.toLowerCase() === fname.toLowerCase());
                if (fileObj) {
                  triggerReValidationBackground(fileObj, tool);
                } else {
                  console.warn('triggerReValidationBackground: fileObj not found for', fname);
                }
                return { fname, data, tool };
             })
          );
          
          let primary = fetchedReports.find((r: any) => r.fname.toLowerCase().includes('dataset')) || fetchedReports[0];
          let reportBaseName = primary.fname.substring(0, primary.fname.lastIndexOf('.')) || primary.fname;
          
          localStorage.setItem('pairedPowerBiReports', JSON.stringify(fetchedReports.map((r: any) => r.data)));
          localStorage.setItem('activePowerBiReportFile', primary.fname);
          localStorage.setItem('activePowerBiReportData', JSON.stringify(primary.data));
          localStorage.setItem('fileDetails', JSON.stringify({
            fileName: reportBaseName,
            etlTool: primary.tool,
            model: modelId,
            technology,
            framework: framework?.id,
          }));
      
          dispatch(setApiData(primary.data));
          dispatch(setFormData({ fileName: reportBaseName, etlTool: primary.tool, model, technology, framework }));
          setCompletedSteps((prev) => [...new Set([...prev, 5])]);
          setAnalysisDone(true);
          toast.success('Processing complete', {
            description: 'Dashboard is ready with the paired Power BI datasets.',
          });
          await new Promise((resolve) => setTimeout(resolve, 700));
          navigate('/overview');
          return;
        }
    
        // Single file: fetch report and navigate to /overview
        const successfulFile = completedFiles.find((file: any) => String(file.status).toLowerCase() === 'success');
        const reportFileName = successfulFile?.file_name || finalProgress?.file_name || selectedFile.name;
        const reportTool = getToolForFile(reportFileName) || 'powerbi';
        const reportBaseName = reportFileName.substring(0, reportFileName.lastIndexOf('.')) || reportFileName;
    
        // For re-uploads (skipExistingCheck=true), fetch by file name — server returns latest version
        const reportData = await fetchPowerBiReport(reportFileName, reportTool);
        
        const fileObj = selectedFiles.find((s: File) => s.name.toLowerCase() === reportFileName.toLowerCase());
        if (fileObj) {
          triggerReValidationBackground(fileObj, reportTool);
        } else {
          console.warn('triggerReValidationBackground: fileObj not found for', reportFileName);
        }

        localStorage.removeItem('pairedPowerBiReports');
    
        localStorage.setItem('activePowerBiReportFile', reportFileName);
        localStorage.setItem('activePowerBiReportData', JSON.stringify(reportData));
        localStorage.setItem('fileDetails', JSON.stringify({
          fileName: reportBaseName,
          etlTool: reportTool,
          model: modelId,
          technology,
          framework: framework?.id,
        }));
    
        dispatch(setApiData(reportData));
        dispatch(setFormData({ fileName: reportBaseName, etlTool: reportTool, model, technology, framework }));
        setCompletedSteps((prev) => [...new Set([...prev, 5])]);
        setAnalysisDone(true);
        toast.success('Processing complete', {
          description: 'Dashboard is ready with the latest processed dataset.',
        });
        await new Promise((resolve) => setTimeout(resolve, 700));
        navigate('/overview');
    
      } catch (error) {
        setAnalysisError(true);
        setApiErrorMessage(error instanceof Error ? error.message : 'An error occurred while uploading the file.');
        toast.error('Error', {
          description: error instanceof Error ? error.message : 'An error occurred while uploading the file.',
        });
      } finally {
        setIsAnalyzing(false);
      }
    };

  const loadExistingDataset = async () => {
    if (!pendingAnalyzeAction) return;
    
    const isPowerBiPairedUpload = selectedFiles.length === 2 && selectedFiles.every((f: any) => (getToolForFile(f.name) || 'powerbi') === 'powerbi');
    
    if (isPowerBiPairedUpload) {
      setApiStatusMessage('Loading existing paired Power BI datasets...');
      
      const fetchedReports = await Promise.all(
         selectedFiles.map(async (f: any) => {
            const fname = f.name;
            const tool = getToolForFile(fname) || 'powerbi';
            const meta = existingReports.find(e => e.file.name === fname)?.reportMeta;
            const data = await fetchPowerBiReport(fname, tool, { reportId: meta?.report_id });
            const fileObj = selectedFiles.find((s: File) => s.name === fname);
            if (fileObj && !meta) {
              triggerReValidationBackground(fileObj, tool);
            }
            return { fname, data, tool, meta };
         })
      );
      
      let primary = fetchedReports.find((r: any) => r.fname.toLowerCase().includes('dataset')) || fetchedReports[0];
      let reportBaseName = primary.fname.substring(0, primary.fname.lastIndexOf('.')) || primary.fname;
      
      setIsExistingModalOpen(false);
      localStorage.setItem('existingReports', JSON.stringify(
        existingReports.map((entry) => ({ fileName: entry.file.name }))
      ));
      
      localStorage.setItem('pairedPowerBiReports', JSON.stringify(fetchedReports.map((r: any) => r.data)));
      localStorage.setItem('activePowerBiReportFile', primary.fname);
      localStorage.setItem('activePowerBiReportId', primary.meta?.report_id || '');
      localStorage.setItem('activePowerBiReportData', JSON.stringify(primary.data));
      localStorage.setItem('fileDetails', JSON.stringify({
        fileName: reportBaseName,
        etlTool: primary.tool,
        model: pendingAnalyzeAction.modelId,
        technology: pendingAnalyzeAction.technology,
        framework: pendingAnalyzeAction.frameworkId,
      }));
      
      dispatch(setApiData(primary.data));
      dispatch(setFormData({
        fileName: reportBaseName,
        etlTool: primary.tool,
        model,
        technology: pendingAnalyzeAction.technology,
        framework,
      }));
      
      setAnalysisDone(true);
      toast.success('Loading existing datasets', {
        description: `Paired datasets were loaded from the database.`,
      });
      await new Promise((resolve) => setTimeout(resolve, 500));
      navigate('/overview');
      return;
    }

    const firstMatch = selectedExistingReport;
    if (!firstMatch) return;
    const activeTool = firstMatch.reportMeta?.tool_type || getToolForFile(firstMatch.file.name) || 'powerbi';
    const activeBaseName =
      firstMatch.file.name.substring(0, firstMatch.file.name.lastIndexOf('.')) || firstMatch.file.name;
    const reportPayload =
      firstMatch.report ||
      await fetchPowerBiReport(firstMatch.file.name, activeTool, {
        reportId: firstMatch.reportMeta?.report_id,
      });

    setIsExistingModalOpen(false);
    setApiStatusMessage('Loading existing dataset...');
    localStorage.setItem('existingReports', JSON.stringify(
      existingReports.map((entry) => ({ fileName: entry.file.name }))
    ));
    localStorage.removeItem('pairedPowerBiReports');
    localStorage.setItem('activePowerBiReportFile', firstMatch.file.name);
    localStorage.setItem('activePowerBiReportId', firstMatch.reportMeta?.report_id || '');
    localStorage.setItem('activePowerBiReportData', JSON.stringify(reportPayload));
    localStorage.setItem('fileDetails', JSON.stringify({
      fileName: activeBaseName,
      etlTool: activeTool,
      model: pendingAnalyzeAction.modelId,
      technology: pendingAnalyzeAction.technology,
      framework: pendingAnalyzeAction.frameworkId,
    }));
    dispatch(setApiData(reportPayload));
    dispatch(setFormData({
      fileName: activeBaseName,
      etlTool: activeTool,
      model,
      technology: pendingAnalyzeAction.technology,
      framework,
    }));
    setAnalysisDone(true);
    toast.success('Loading existing dataset', {
      description: `${firstMatch.file.name} was loaded from the database.`,
    });
    await new Promise((resolve) => setTimeout(resolve, 500));
    navigate('/overview');
  };

  const uploadNewVersion = async () => {
    setIsExistingModalOpen(false);
    setExistingReports([]);
    setApiStatusMessage('Uploading new dataset version...');
   // setCurrentStep(5);
    setIsAnalyzing(true);
    setTimeout(() => {
      handleAnalyze({ skipExistingCheck: true });
    }, 0);
  };

  const canProceed = () => {
    switch (currentStep) {
      case 1: return selectedFiles.length > 0;
      case 2: return model !== null;
      case 3: return true;
      default: return true;
    }
  };

  const goToStep = (step) => {
    if (step <= Math.max(...completedSteps, 0) + 1 && step <= 3) {
      setCurrentStep(step);
      setVisitedSteps(prev => [...new Set([...prev, step])]);
    }
  };

  // const skipStep = () => {
  //   if (currentStep === 3 && currentStep < 5) {
  //     setCompletedSteps(prev => [...new Set([...prev, 3])]);
  //     goToStep(4);
  //   }
  // };

  const nextStep = () => {
    if (canProceed() && currentStep < 3) goToStep(currentStep + 1);
  };

  const prevStep = () => {
    if (currentStep > 1) setCurrentStep(currentStep - 1);
  };

  const renderDatabaseReportsPanel = () => (
    <div className="flex flex-col flex-1 min-h-0 bg-slate-50">
      {/* Toolbar */}
      <div className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-4 shrink-0">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#003087]/10 text-[#003087]">
            <Database className="h-4 w-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-900">Available Files</h3>
            <p className="text-xs text-slate-500">Processed Power BI & Tableau reports</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Button
            type="button"
            onClick={loadDatabaseReports}
            disabled={isLoadingDatabaseReports}
            variant="outline"
            className="flex h-9 items-center gap-2 rounded-lg border border-slate-200 px-3 text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            {isLoadingDatabaseReports ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileSearch className="h-4 w-4" />}
            {isLoadingDatabaseReports ? 'Fetching...' : 'Refresh'}
          </Button>
        </div>
      </div>

      {databaseReportsError && (
        <div className="m-4 shrink-0 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700 flex items-center gap-2">
          <X className="h-4 w-4" />
          {databaseReportsError}
        </div>
      )}

      {/* Data Grid */}
      <div className="flex-1 flex flex-col min-h-0 bg-white m-6 rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="flex-1 overflow-auto">
          {databaseReports.length > 0 ? (
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 z-10 bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="px-6 py-4 font-semibold text-slate-600">File Name</th>
                <th className="px-6 py-4 font-semibold text-slate-600">Type</th>
                <th className="px-6 py-4 font-semibold text-slate-600">Status</th>
                <th className="px-6 py-4 font-semibold text-slate-600 text-right">Processed At</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {databaseReports.map((report) => {
                const isSelected =
                  selectedDatabaseReport?.report_id === report.report_id &&
                  selectedDatabaseReport?.file_name === report.file_name;
                const toolLabel = report.tool_type === 'tableau-workbook' ? 'Tableau' : 'Power BI';
                
                return (
                  <tr
                    key={report.report_id || `${report.tool_type}-${report.file_name}`}
                    onClick={() => selectDatabaseReport(report)}
                    className={cn(
                      "cursor-pointer transition-colors hover:bg-slate-50 group",
                      isSelected ? "bg-[#003087]/5" : ""
                    )}
                  >
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div className={cn(
                          "flex h-9 w-9 items-center justify-center rounded-lg border transition-colors",
                          isSelected ? "border-[#003087] bg-[#003087] text-white" : "border-slate-200 bg-white text-slate-500 group-hover:border-[#003087]/30 group-hover:text-[#003087]"
                        )}>
                          {isSelected ? <CheckCircle className="h-4 w-4" /> : <FileCode className="h-4 w-4" />}
                        </div>
                        <span className={cn(
                          "font-semibold",
                          isSelected ? "text-[#003087]" : "text-slate-900"
                        )}>
                          {report.file_name}
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span className="inline-flex items-center rounded-md bg-slate-100 px-2 py-1 text-xs font-medium text-slate-600">
                        {toolLabel}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <span className={cn(
                        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold",
                        isSelected ? "bg-[#003087] text-white" : "bg-emerald-50 text-emerald-700"
                      )}>
                        {isSelected ? 'Selected' : 'Ready'}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      {report.completed_at ? (
                        <div className="flex items-center justify-end gap-1.5 text-slate-500">
                          <Clock3 className="h-3.5 w-3.5" />
                          <span>{new Date(report.completed_at).toLocaleString()}</span>
                        </div>
                      ) : (
                        <span className="text-slate-400">-</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <div className="flex h-full min-h-[240px] flex-col items-center justify-center text-slate-400">
            <Database className="mb-3 h-10 w-10 opacity-20" />
            <p className="font-semibold text-slate-600">No database files loaded</p>
            <p className="mt-1 text-sm">Click "Refresh" to fetch processed reports.</p>
          </div>
        )}
        </div>
        
        {/* Sticky Footer for Actions */}
        <div className="border-t border-slate-200 bg-slate-50 p-4 shrink-0 flex items-center justify-between">
          <div className="text-sm text-slate-500 font-medium">
            {selectedDatabaseReport ? (
              <span className="flex items-center gap-2">
                <CheckCircle className="h-4 w-4 text-[#c8102e]" />
                Selected: <span className="font-bold text-slate-900">{selectedDatabaseReport.file_name}</span>
              </span>
            ) : 'No file selected'}
          </div>
          <Button
            type="button"
            onClick={analyzeDatabaseReport}
            disabled={!selectedDatabaseReport || isAnalyzing}
            className={cn(
              'flex h-10 items-center gap-2 rounded-lg px-6 text-sm font-semibold transition-all shadow-sm',
              selectedDatabaseReport && !isAnalyzing
                ? 'bg-[#c8102e] text-white hover:bg-[#a30d24]'
                : 'bg-slate-200 text-slate-500 cursor-not-allowed'
            )}
          >
            {isAnalyzing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Brain className="h-4 w-4" />}
            Analyze Selected
          </Button>
        </div>
      </div>
    </div>
  );

  const renderStepContent = () => {
    switch (currentStep) {
      case 1:
        return <FileUploadPanel onFileSelect={handleFileSelect} selectedFile={selectedFiles} onRemoveFile={handleRemoveFile} />;
      // case 2: // Commented out - Source platform auto-detected from file extension
      //   return (
      //     <PlatformSelector
      //       type="source"
      //       selected={sourcePlatform}
      //       onSelect={handleSourceSelect}
      //       title="Select Source Platform"
      //       subtitle="Choose where your data is coming from"
      //     />
      //   );
      case 2:
        return <AIModelSelector selected={model} onSelect={handleModelSelect} />;
      case 3:
        return (
          <AnalysisPanel
            file={selectedFile}
            selectedFiles={selectedFiles}
            sourcePlatform={sourcePlatform}
            framework={framework}
            model={model}
            onAnalyze={handleAnalyze}
            isAnalyzing={isAnalyzing}
          />
        );
      default:
        return null;
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-stone-50 via-white to-red-50/40">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-white/85 backdrop-blur-xl border-b border-stone-200">
  <div className="max-w-6xl mx-auto px-6 py-4">
    <div className="flex items-center">
      <div className="w-1/3">
        {/* <Button
          variant="outline"
          className="flex items-center gap-2 border-2 border-red-700 !text-red-700 hover:bg-red-50 font-medium rounded-lg"
          onClick={() => navigate('/')}>
          <ArrowLeft className="w-4 h-4" />
          Back
        </Button> */}
      </div>
      <div className="w-1/3 flex justify-center">
        <span className="bg-gradient-to-r from-[#8f0d22] to-[#C8102E] bg-clip-text text-transparent !text-[25px] font-bold tracking-tight">
          BI Modernization
        </span>
      </div>
      <div className="w-1/3 flex justify-end gap-3">
        <Button
          onClick={() => navigate('/existing-reports')}
          variant="outline"
          className="flex items-center gap-2 border border-red-200 !text-red-700 hover:bg-red-50 font-medium rounded-lg"
        >
          <Database className="w-4 h-4" />
          Analyze Existing
        </Button>
        <Button
          onClick={handleLogout}
          variant="outline"
          className="flex items-center gap-2 border border-stone-300 !text-stone-700 hover:bg-stone-50 font-medium rounded-lg"
        >
          <LogOut className="w-4 h-4" />
          Logout
        </Button>
      </div>
    </div>
  </div>
</header>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-6 py-8">
        <StepIndicator
          currentStep={currentStep}
          completedSteps={completedSteps}
          onStepClick={goToStep}
        />

        <div className="mt-8">
          <motion.div
            className="bg-white rounded-lg shadow-xl shadow-stone-200/50 border border-stone-200 overflow-hidden"
          >
            <div className="p-8">
              <AnimatePresence mode="wait">
                <motion.div
                  key={currentStep}
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -20 }}
                  transition={{ duration: 0.3 }}
                >
                  {renderStepContent()}
                </motion.div>
              </AnimatePresence>
            </div>

            <div className="px-8 py-5 bg-stone-50 border-t border-stone-200 flex items-center justify-between">
              <Button
                variant="ghost"
                onClick={prevStep}
                disabled={currentStep === 1}
                className="flex items-center gap-2"
              >
                <ArrowLeft className="w-4 h-4" />
                Previous
              </Button>

              <div className="flex items-center gap-2">
                {[1, 2, 3].map(step => (
                  <button
                    key={step}
                    onClick={() => step <= Math.max(...completedSteps, 0) + 1 && setCurrentStep(step)}
                    className={cn(
                      "w-2.5 h-2.5 rounded-full transition-all duration-300",
                      currentStep === step
                        ? "bg-red-700 scale-125"
                        : completedSteps.includes(step)
                          ? "bg-red-400"
                          : "bg-slate-300"
                    )}
                  />
                ))}
              </div>

              {currentStep < 3 ? (
                <div className="flex items-center gap-2">
                  {/* {currentStep === 3 && (
                    <Button
                      variant="outline"
                      onClick={skipStep}
                      className="border-stone-300 text-stone-600 hover:bg-stone-100 rounded-lg"
                    >
                      Skip
                    </Button>
                  )} */}
                  <Button
                    onClick={nextStep}
                    disabled={!canProceed()}
                    className={cn(
                      "flex items-center gap-2 transition-all duration-300",
                      canProceed()
                        ? "bg-gradient-to-r from-red-700 to-red-900 hover:from-red-800 hover:to-red-950 shadow-lg shadow-red-500/20 rounded-lg text-white"
                        : "bg-stone-200 text-stone-500 rounded-lg"
                    )}
                  >
                    Next
                    <ArrowRight className="w-4 h-4" />
                  </Button>
                </div>
              ) : (
                <div className="w-24" />
              )}
            </div>
          </motion.div>
        </div>

        {/* ─── Analyzing Card — appears below the main card when API call is in progress ─── */}
        <AnimatePresence>
          {(isAnalyzing || analysisDone || analysisError) && selectedFile && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 10 }}
              transition={{ duration: 0.4, ease: 'easeOut' }}
              className="mt-4"
            >
              {/* Section label */}
              <div className="flex items-center gap-2 mb-3">
                <Zap className="w-3.5 h-3.5 text-red-700" />
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-widest">
                  {analysisDone ? 'Analysis Complete' : analysisError ? 'Analysis Failed' : 'Analyzing…'}
                </span>
                {!analysisDone && !analysisError && (
                  <motion.div
                    className="h-px flex-1 bg-gradient-to-r from-red-200 to-transparent"
                    initial={{ scaleX: 0 }}
                    animate={{ scaleX: 1 }}
                    transition={{ duration: 0.6 }}
                    style={{ transformOrigin: 'left' }}
                  />
                )}
              </div>

              <EnterpriseWorkflowCard
                fileName={selectedFile.name}
                isAnalyzing={isAnalyzing}
                isDone={analysisDone}
                isError={analysisError}
                apiUploadProgress={apiUploadProgress}
                apiStatusMessage={apiStatusMessage}
                apiErrorMessage={apiErrorMessage}
                jobFiles={jobFiles}
              />
            </motion.div>
          )}
        </AnimatePresence>

        {/* Selection Summary */}
        {/* <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="mt-6 bg-white rounded-lg border border-stone-200 p-6"
        >
          <h3 className="text-sm font-medium text-slate-400 uppercase tracking-wider mb-4">
            Your Selection
          </h3> */}
          {/* <div className="flex flex-wrap items-center gap-3">
            {selectedFiles.length > 0 && (
              <SelectionChip
                label="File"
                icon={FileCode}
                value={selectedFiles.length === 1 ? selectedFile.name : `${selectedFiles.length} files selected`}
                onClear={() => {setSelectedFiles([]); setSourcePlatform(null)}}
              />
            )}
            {sourcePlatform && (
              <SelectionChip
                label="Source"
                value={sourcePlatform.name}
                icon={sourcePlatform.icon}
                onClear={() => setSourcePlatform(null)}
              />
            )}
            {/* {visitedSteps.includes(3) && framework && (
              <SelectionChip
                label="Framework"
                value={framework.name}
                onClear={() => setFramework(null)}
              />
            )} */}
            {/* {visitedSteps.includes(2) && sourcePlatform && (
              <SelectionChip
                label="Source"
                value={sourcePlatform.name}
                icon={sourcePlatform.icon}
                onClear={() => setSourcePlatform(null)}
              />
            )} */}
           {/*} {visitedSteps.includes(2) && model && (
              <SelectionChip
                label="Model"
                value={model.selectedVersionLabel || model.name}
                icon={model.icon}
                onClear={() => setModel(null)}
              />
            )}
            {!selectedFile && !model && (
              <span className="text-sm text-slate-400">No selections made yet</span>
            )}
          </div> */}
      {/* </motion.div> */}
      </main>



      <Dialog open={isExistingModalOpen} onClose={() => setIsExistingModalOpen(false)} maxWidth="md" fullWidth>
        <DialogContent sx={{ p: 0, borderRadius: '12px', overflow: 'hidden' }}>
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="bg-gradient-to-br from-white via-white to-red-50/40">
            <div className="border-b border-stone-200 px-7 py-6">
              <div className="flex items-start gap-4">
                <div className="grid h-14 w-14 place-items-center rounded-2xl bg-red-50 text-red-700 shadow-sm ring-1 ring-red-100">
                  <Database size={24} />
                </div>
                <div>
                  <h2 className="text-2xl font-semibold tracking-tight text-stone-950">Dataset already exists</h2>
                  <p className="mt-2 max-w-xl text-sm leading-6 text-stone-500">
                    We found an existing processed dataset in PostgreSQL. Choose whether to load that version now or upload a new version for fresh processing.
                  </p>
                </div>
              </div>
            </div>
            <div className="space-y-3 px-7 py-6 max-h-[40vh] overflow-y-auto">
              {existingReports.map((entry) => {
                const isSelected = selectedExistingReport?.file?.name === entry.file.name;
                return (
                  <button
                    key={entry.file.name}
                    onClick={() => setSelectedExistingReport(entry)}
                    className={`w-full rounded-2xl border px-5 py-4 shadow-sm text-left transition-all ${isSelected
                      ? 'border-red-400 bg-red-50 ring-2 ring-red-200'
                      : 'border-stone-200 bg-white hover:border-red-200 hover:bg-red-50/40'
                      }`}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex min-w-0 items-start gap-3">
                        <div className={`grid h-11 w-11 place-items-center rounded-xl ring-1 transition-colors ${isSelected ? 'bg-red-100 text-red-700 ring-red-200' : 'bg-stone-100 text-stone-700 ring-stone-200'
                          }`}>
                          {isSelected ? <Check size={18} /> : <Database size={18} />}
                        </div>
                        <div className="min-w-0">
                          <p className="truncate text-base font-semibold text-stone-950">{entry.file.name}</p>
                          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-stone-500">
                            <span className="rounded-full bg-emerald-50 px-2.5 py-1 font-semibold text-emerald-700">READY</span>
                            <span className="inline-flex items-center gap-1">
                              <Clock3 size={12} />
                              Existing dataset found in PostgreSQL
                            </span>
                          </div>
                        </div>
                      </div>
                      <div className="text-right text-xs text-stone-500">
                        <p className="font-medium text-stone-700">Last checked</p>
                        <p className="mt-1">{new Date().toLocaleString()}</p>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
            <div className="border-t border-stone-200 bg-stone-50 px-7 py-5">

              {/* Selected dataset text */}
              <div className="mb-4">
                <p className="text-sm font-medium text-stone-600">
                  {selectedExistingReport
                    ? `Selected dataset: ${selectedExistingReport.file.name}`
                    : "Select a dataset to continue"}
                </p>
              </div>

              {/* Buttons row */}
              <div className="flex justify-end gap-4 mt-4">

                {/* Cancel */}
                <button
                  type="button"
                  onClick={() => setIsExistingModalOpen(false)}
                  className="px-5 py-3 rounded-xl font-semibold transition-all duration-300 text-white shadow-lg shadow-red-500/20 bg-gradient-to-r from-red-700 to-red-900 hover:from-red-800 hover:to-red-950 disabled:bg-stone-200 disabled:text-stone-500 disabled:shadow-none"
                >
                  Cancel
                </button>

                {!selectedExistingReport?.file?.fromDatabase && (
                  <button
                    type="button"
                    onClick={uploadNewVersion}
                    className="px-6 py-3 rounded-xl font-semibold transition-all duration-300 text-white shadow-lg shadow-red-500/20 bg-gradient-to-r from-red-700 to-red-900 hover:from-red-800 hover:to-red-950 disabled:bg-stone-200 disabled:text-stone-500 disabled:shadow-none"
                  >
                    Upload New Version
                  </button>
                )}

                {/* Load Existing */}
                <button
                  type="button"
                  onClick={loadExistingDataset}
                  disabled={!selectedExistingReport}
                  className={`px-6 py-3 rounded-xl font-semibold transition-all duration-300 ${selectedExistingReport
                      ? "text-white bg-gradient-to-r from-red-700 to-red-900 hover:from-red-800 hover:to-red-950 shadow-lg shadow-red-500/20"
                      : "bg-stone-200 text-stone-500 cursor-not-allowed"
                    }`}
                >
                  Load Existing
                </button>
              </div>
            </div>
          </motion.div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ─── Selection Chip ────────────────────────────────────────────────────────────

function SelectionChip({ label, value, icon, onClear }) {
  const IconComponent = icon;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.9 }}
      className="flex items-center gap-2 px-3 py-2 bg-red-50 border border-red-100 rounded-lg"
    >
      {icon && (
        typeof icon === 'string' ? (
          <img src={icon} alt={label} className="w-6 h-6" />
        ) : (
          <IconComponent className="w-6 h-6" />
        )
      )}
      <div className="flex flex-col">
        <span className="text-[10px] text-red-700 uppercase tracking-wider">{label}</span>
        <span className="text-sm font-medium text-red-900">{value}</span>
      </div>
      <button
        onClick={onClear}
        className="ml-1 p-1 hover:bg-red-100 rounded-lg transition-colors"
      >
        <X className="w-3.5 h-3.5 text-red-700" />
      </button>
    </motion.div>
  );
}
