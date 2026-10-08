/**
 * backgroundJobService.ts
 * 
 * Central polling utility with exponential backoff retry.
 * Reusable for all modules (validation, gap analysis, rationalization, enrichment).
 */
import axios from 'axios';
import { store } from './Store.ts';
import { updateJobProgress, addJobLog, completeJob, failJob, saveJobResult, JobType } from './jobTrackerSlice.ts';

interface PollOptions {
  jobType: JobType;
  pollUrl: string;
  fileName: string;
  maxAttempts?: number;
  initialIntervalMs?: number;
  maxIntervalMs?: number;
  backoffFactor?: number;
  isComplete?: (data: any) => boolean;
  isFailed?: (data: any) => boolean;
  getError?: (data: any) => string;
  onProgress?: (data: any, attempt: number) => void;
  onComplete?: (data: any) => void;
}

const defaultIsComplete = (data: any) => {
  const s = String(data?.status || '').toLowerCase();
  return ['success', 'completed', 'complete', 'done'].includes(s);
};

const defaultIsFailed = (data: any) => {
  const s = String(data?.status || '').toLowerCase();
  return ['failed', 'error'].includes(s);
};

const defaultGetError = (data: any) => data?.error || data?.message || 'Job failed.';

/**
 * Poll a job status endpoint with exponential backoff.
 * Dispatches Redux actions automatically.
 */
export async function pollJobStatus(options: PollOptions): Promise<any> {
  const {
    jobType,
    pollUrl,
    fileName,
    maxAttempts = 180,
    initialIntervalMs = 2000,
    maxIntervalMs = 10000,
    backoffFactor = 1.2,
    isComplete = defaultIsComplete,
    isFailed = defaultIsFailed,
    getError = defaultGetError,
    onProgress,
    onComplete,
  } = options;

  const dispatch = store.dispatch;
  let interval = initialIntervalMs;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const res = await axios.get(pollUrl, { headers: { accept: 'application/json' } });
      const data = res.data;

      dispatch(addJobLog({ type: jobType, message: `Poll #${attempt} — status: ${data?.status || 'unknown'}` }));

      const progressPct = Math.min(30 + Math.round((attempt / maxAttempts) * 65), 95);
      dispatch(updateJobProgress({
        type: jobType,
        progress: progressPct,
        statusMessage: `Polling… (attempt ${attempt})`,
        status: 'polling',
      }));

      if (onProgress) onProgress(data, attempt);

      if (isComplete(data)) {
        saveJobResult(jobType, fileName, data);
        dispatch(completeJob({ type: jobType, statusMessage: `${jobType} complete` }));
        if (onComplete) onComplete(data);
        return data;
      }

      if (isFailed(data)) {
        const errMsg = getError(data);
        dispatch(failJob({ type: jobType, errorMessage: errMsg }));
        throw new Error(errMsg);
      }

      // Exponential backoff
      interval = Math.min(interval * backoffFactor, maxIntervalMs);
    } catch (err) {
      if (err instanceof Error && (err.message.includes('failed') || err.message.includes('error'))) {
        throw err;
      }
      // Network error — retry with backoff
      dispatch(addJobLog({ type: jobType, message: `Poll #${attempt} network error, retrying…` }));
      interval = Math.min(interval * backoffFactor, maxIntervalMs);
    }

    await new Promise(r => setTimeout(r, interval));
  }

  dispatch(failJob({ type: jobType, errorMessage: 'Max polling attempts reached. Job may still be running on server.' }));
  throw new Error('Max polling attempts reached.');
}

export default pollJobStatus;
