/**
 * useBackgroundJob.ts
 * 
 * React hook for components to easily interact with background jobs.
 * Handles loading cached results and checking job status.
 */
import { useSelector } from 'react-redux';
import { selectJob, loadJobResult, getJobResultMeta, JobType, TrackedJob } from './jobTrackerSlice.ts';

interface UseBackgroundJobResult {
  job: TrackedJob | null;
  isRunning: boolean;
  isComplete: boolean;
  isError: boolean;
  cachedResult: any;
  cachedMeta: { savedAt: string; type: string; fileName: string } | null;
  hasCachedResult: boolean;
}

export function useBackgroundJob(type: JobType, fileName?: string): UseBackgroundJobResult {
  const job = useSelector(selectJob(type));
  const activeFile = fileName || localStorage.getItem('activePowerBiReportFile') || '';
  
  const cachedResult = activeFile ? loadJobResult(type, activeFile) : null;
  const cachedMeta = activeFile ? getJobResultMeta(type, activeFile) : null;

  return {
    job,
    isRunning: job?.status === 'running' || job?.status === 'polling' || job?.status === 'queued',
    isComplete: job?.status === 'complete',
    isError: job?.status === 'error',
    cachedResult,
    cachedMeta,
    hasCachedResult: cachedResult !== null,
  };
}

export default useBackgroundJob;
