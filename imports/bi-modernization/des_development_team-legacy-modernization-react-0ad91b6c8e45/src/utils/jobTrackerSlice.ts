/**
 * jobTrackerSlice.ts
 * 
 * Global Redux slice for tracking long-running background jobs.
 * Persists to localStorage so jobs survive page navigation AND browser refresh.
 * 
 * Supports: gap-analysis, validation, kpi-rationalization, business-enrichment
 */
import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export type JobType = 'gap-analysis' | 'validation' | 'kpi-rationalization' | 'business-enrichment';
export type JobStatus = 'idle' | 'queued' | 'running' | 'polling' | 'complete' | 'error' | 'cancelled';

export interface JobStep {
  label: string;
  status: 'pending' | 'active' | 'done' | 'error';
  startedAt?: string;
  completedAt?: string;
}

export interface TrackedJob {
  id: string;
  type: JobType;
  status: JobStatus;
  progress: number;          // 0–100
  statusMessage: string;
  startedAt: string;
  completedAt?: string;
  errorMessage?: string;
  fileName?: string;
  steps: JobStep[];
  currentStepIndex: number;
  estimatedTotalMs?: number;  // rough ETA in ms
  logs: string[];             // event log entries
  apiJobId?: string;          // server-side job_id for polling
}

interface JobTrackerState {
  jobs: Record<string, TrackedJob>;
  toasts: Array<{ id: string; type: 'success' | 'error' | 'info' | 'warning'; message: string; createdAt: string }>;
}

// ─── localStorage persistence ──────────────────────────────────────────────
const STORAGE_KEY = 'jnj:tracked-jobs';
const RESULT_PREFIX = 'jnj:job-result:';

const loadFromStorage = (): Record<string, TrackedJob> => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    // Normalize and mark stale running jobs on refresh
    Object.values(parsed).forEach((job: any) => {
      // Ensure arrays exist (old jobs may lack them)
      if (!Array.isArray(job.steps)) job.steps = [];
      if (!Array.isArray(job.logs)) job.logs = [];
      if (typeof job.currentStepIndex !== 'number') job.currentStepIndex = 0;
      if (job.status === 'running' || job.status === 'polling' || job.status === 'queued') {
        job.status = 'error';
        job.statusMessage = 'Interrupted — page was refreshed. Re-run to continue.';
        job.errorMessage = 'Job interrupted by page refresh.';
        job.progress = job.progress || 0;
        job.logs.push(`[${new Date().toLocaleTimeString()}] Job interrupted by page refresh`);
      }
    });
    return parsed;
  } catch { return {}; }
};

const saveToStorage = (jobs: Record<string, TrackedJob>) => {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(jobs)); } catch {}
};

// ─── Result persistence (public helpers) ───────────────────────────────────
export const saveJobResult = (type: JobType, fileName: string, result: any) => {
  try {
    const key = `${RESULT_PREFIX}${type}:${fileName}`;
    localStorage.setItem(key, JSON.stringify({
      result,
      savedAt: new Date().toISOString(),
      type,
      fileName,
    }));
  } catch {}
};

export const loadJobResult = (type: JobType, fileName: string): any => {
  try {
    const key = `${RESULT_PREFIX}${type}:${fileName}`;
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw).result;
  } catch { return null; }
};

export const clearJobResult = (type: JobType, fileName: string) => {
  try { localStorage.removeItem(`${RESULT_PREFIX}${type}:${fileName}`); } catch {}
};

export const getJobResultMeta = (type: JobType, fileName: string) => {
  try {
    const key = `${RESULT_PREFIX}${type}:${fileName}`;
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return { savedAt: parsed.savedAt, type: parsed.type, fileName: parsed.fileName };
  } catch { return null; }
};

// ─── Default steps per job type ────────────────────────────────────────────
export const DEFAULT_STEPS: Record<JobType, string[]> = {
  'gap-analysis': [ 'Preparing payload', 'Running gap analysis API', 'Processing results'],
  'validation': ['Preparing validation payload',  'Polling for results', 'Finalizing report'],
  'kpi-rationalization': ['Loading source files', 'Fetching report data', 'Building analysis payload', 'Running rationalization API', 'Processing catalog'],
  'business-enrichment': [ 'Building enriched catalog', 'Finalizing results'],
};

export const JOB_LABELS: Record<JobType, string> = {
  'gap-analysis': 'Gap Analysis',
  'validation': 'Validation Report',
  'kpi-rationalization': 'KPI Rationalization',
  'business-enrichment': 'Business Enrichment',
};

export const JOB_ROUTES: Record<JobType, string> = {
  'gap-analysis': '/gap-analysis',
  'validation': '/validation-report',
  'kpi-rationalization': '/gap-analysis',
  'business-enrichment': '/gap-analysis',
};

// ─── Slice ─────────────────────────────────────────────────────────────────
const initialState: JobTrackerState = {
  jobs: loadFromStorage(),
  toasts: [],
};

const jobTrackerSlice = createSlice({
  name: 'jobTracker',
  initialState,
  reducers: {
    startJob(state, action: PayloadAction<{
      type: JobType;
      fileName?: string;
      statusMessage?: string;
      estimatedTotalMs?: number;
    }>) {
      const { type, fileName, statusMessage, estimatedTotalMs } = action.payload;
      const steps = DEFAULT_STEPS[type].map((label, i) => ({
        label,
        status: i === 0 ? 'active' as const : 'pending' as const,
        ...(i === 0 ? { startedAt: new Date().toISOString() } : {}),
      }));
      state.jobs[type] = {
        id: `${type}-${Date.now()}`,
        type,
        status: 'running',
        progress: 2,
        statusMessage: statusMessage || steps[0].label + '…',
        startedAt: new Date().toISOString(),
        fileName,
        steps,
        currentStepIndex: 0,
        estimatedTotalMs: estimatedTotalMs || 300000,
        logs: [`[${new Date().toLocaleTimeString()}] Job started`],
        apiJobId: undefined,
      };
      // Toast
      state.toasts.push({
        id: `toast-${Date.now()}`,
        type: 'info',
        message: `${JOB_LABELS[type]} started${fileName ? ` for ${fileName}` : ''}. Processing will continue in background.`,
        createdAt: new Date().toISOString(),
      });
      saveToStorage(state.jobs);
    },

    advanceStep(state, action: PayloadAction<{ type: JobType; stepIndex: number; statusMessage?: string }>) {
      const job = state.jobs[action.payload.type];
      if (!job) return;
      const { stepIndex, statusMessage } = action.payload;
      // Complete previous steps
      for (let i = 0; i < stepIndex && i < job.steps.length; i++) {
        job.steps[i].status = 'done';
        if (!job.steps[i].completedAt) job.steps[i].completedAt = new Date().toISOString();
      }
      // Activate current step
      if (stepIndex < job.steps.length) {
        job.steps[stepIndex].status = 'active';
        job.steps[stepIndex].startedAt = new Date().toISOString();
      }
      job.currentStepIndex = stepIndex;
      const pct = Math.min(Math.round(((stepIndex + 0.5) / job.steps.length) * 100), 95);
      job.progress = pct;
      job.statusMessage = statusMessage || job.steps[stepIndex]?.label + '…' || '';
      job.logs.push(`[${new Date().toLocaleTimeString()}] Step ${stepIndex + 1}: ${job.steps[stepIndex]?.label || ''}`);
      saveToStorage(state.jobs);
    },

    updateJobProgress(state, action: PayloadAction<{
      type: JobType;
      progress: number;
      statusMessage?: string;
      status?: JobStatus;
      apiJobId?: string;
    }>) {
      const job = state.jobs[action.payload.type];
      if (!job) return;
      job.progress = Math.min(action.payload.progress, 99);
      if (action.payload.statusMessage) job.statusMessage = action.payload.statusMessage;
      if (action.payload.status) job.status = action.payload.status;
      if (action.payload.apiJobId) job.apiJobId = action.payload.apiJobId;
      saveToStorage(state.jobs);
    },

    addJobLog(state, action: PayloadAction<{ type: JobType; message: string }>) {
      const job = state.jobs[action.payload.type];
      if (!job) return;
      job.logs.push(`[${new Date().toLocaleTimeString()}] ${action.payload.message}`);
      if (job.logs.length > 50) job.logs = job.logs.slice(-50);
      saveToStorage(state.jobs);
    },

    completeJob(state, action: PayloadAction<{ type: JobType; statusMessage?: string }>) {
      const job = state.jobs[action.payload.type];
      if (!job) return;
      job.status = 'complete';
      job.progress = 100;
      job.completedAt = new Date().toISOString();
      job.statusMessage = action.payload.statusMessage || 'Complete';
      job.steps.forEach(s => { if (s.status !== 'done') { s.status = 'done'; s.completedAt = new Date().toISOString(); }});
      job.logs.push(`[${new Date().toLocaleTimeString()}] ✅ Job completed successfully`);
      state.toasts.push({
        id: `toast-${Date.now()}`,
        type: 'success',
        message: `${JOB_LABELS[job.type]} completed successfully!`,
        createdAt: new Date().toISOString(),
      });
      saveToStorage(state.jobs);
    },

    failJob(state, action: PayloadAction<{ type: JobType; errorMessage: string }>) {
      const job = state.jobs[action.payload.type];
      if (!job) return;
      job.status = 'error';
      job.errorMessage = action.payload.errorMessage;
      job.statusMessage = 'Failed';
      if (job.currentStepIndex < job.steps.length) {
        job.steps[job.currentStepIndex].status = 'error';
      }
      job.logs.push(`[${new Date().toLocaleTimeString()}] ❌ ${action.payload.errorMessage}`);
      state.toasts.push({
        id: `toast-${Date.now()}`,
        type: 'error',
        message: `${JOB_LABELS[job.type]} failed: ${action.payload.errorMessage}`,
        createdAt: new Date().toISOString(),
      });
      saveToStorage(state.jobs);
    },

    dismissJob(state, action: PayloadAction<{ type: JobType }>) {
      delete state.jobs[action.payload.type];
      saveToStorage(state.jobs);
    },

    dismissToast(state, action: PayloadAction<string>) {
      state.toasts = state.toasts.filter(t => t.id !== action.payload);
    },

    clearAllJobs(state) {
      state.jobs = {};
      state.toasts = [];
      saveToStorage(state.jobs);
    },
  },
});

export const {
  startJob, advanceStep, updateJobProgress, addJobLog,
  completeJob, failJob, dismissJob, dismissToast, clearAllJobs,
} = jobTrackerSlice.actions;

export default jobTrackerSlice.reducer;

// ─── Selectors ─────────────────────────────────────────────────────────────
export const selectAllJobs = (state: { jobTracker: JobTrackerState }) => state.jobTracker.jobs;
export const selectJob = (type: JobType) => (state: { jobTracker: JobTrackerState }) => state.jobTracker.jobs[type] || null;
export const selectActiveJobs = (state: { jobTracker: JobTrackerState }) =>
  Object.values(state.jobTracker.jobs).filter(j => j.status === 'running' || j.status === 'polling' || j.status === 'queued');
export const selectToasts = (state: { jobTracker: JobTrackerState }) => state.jobTracker.toasts;
