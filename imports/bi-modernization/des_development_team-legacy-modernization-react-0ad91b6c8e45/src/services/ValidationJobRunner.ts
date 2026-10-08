import axios from 'axios';
import { startJob, advanceStep, updateJobProgress, addJobLog, completeJob, failJob, saveJobResult, clearJobResult } from '../utils/jobTrackerSlice.ts';
import { store } from '../utils/Store.ts';
import { toast } from 'sonner';

const VALIDATION_API_URL = 'http://20.72.80.42:8001/validation/validate';

export const triggerReValidationBackground = async (file: File | null, toolName: string, providedFileName?: string) => {
  const fileName = providedFileName || (file ? file.name : '');
  if (!fileName) {
    toast.error('Validation Error: No file name provided to runner');
    return;
  }
  
  const dispatch = store.dispatch;

  toast.info(`Triggering RE validation for ${fileName}...`);

  // Don't run if already running
  const state = store.getState();
  const existingJob = Object.values(state.jobTracker.jobs).find(
    (j: any) => j.type === 'validation' && j.fileName === fileName
  ) as any;
  if (existingJob && (existingJob.status === 'running' || existingJob.status === 'polling')) {
    toast.info(`Validation already running for ${fileName}`);
    return;
  }

  // Force clear the previous cache so the UI doesn't show stale results while validating
  clearJobResult('validation', fileName);

  dispatch(startJob({ type: 'validation', fileName, estimatedTotalMs: 480000 }));
  dispatch(advanceStep({ type: 'validation', stepIndex: 0 }));
  dispatch(updateJobProgress({ type: 'validation', progress: 5, statusMessage: 'Preparing validation payload…', status: 'running' }));

  let progressValue = 5;
  const timer = setInterval(() => {
    progressValue = Math.min(progressValue + 3, 88);
    dispatch(updateJobProgress({ type: 'validation', progress: progressValue, statusMessage: 'Validating in background…', status: 'running' }));
  }, 1000);

  try {
    const fd = new FormData();
    fd.append('file_name', fileName);
    fd.append('tool_name', toolName);
    
    if (file) {
      const isTableau = toolName.toLowerCase().includes('tableau');
      if (isTableau) {
        fd.append('pbix_file', '');
        fd.append('twb_file', file, file.name);
      } else {
        fd.append('pbix_file', file, file.name);
        fd.append('twb_file', '');
      }
      fd.append('bim_file', '');
    } else {
      // Send 0-byte files so the backend sees a file upload but falls back to cache due to 0 size
      const isTableau = toolName.toLowerCase().includes('tableau') || fileName.toLowerCase().endsWith('.twb') || fileName.toLowerCase().endsWith('.twbx');
      if (isTableau) {
        fd.append('pbix_file', '');
        fd.append('twb_file', new File([], fileName, { type: 'application/octet-stream' }));
      } else {
        fd.append('pbix_file', new File([], fileName, { type: 'application/octet-stream' }));
        fd.append('twb_file', '');
      }
      fd.append('bim_file', '');
    }
    
    dispatch(advanceStep({ type: 'validation', stepIndex: 1, statusMessage: 'Running semantic checks…' }));
    
    const res = await axios.post(VALIDATION_API_URL, fd, { headers: { accept: 'application/json' } });
    clearInterval(timer); // Clear the simulated timer before we either finish or poll
    
    let payload = res.data;

    dispatch(advanceStep({ type: 'validation', stepIndex: 2, statusMessage: 'Running visual checks…' }));

    if ((payload?.status || '').toLowerCase() === 'processing') {
      dispatch(advanceStep({ type: 'validation', stepIndex: 3, statusMessage: 'Polling for results…' }));
      dispatch(updateJobProgress({ type: 'validation', progress: 50, status: 'polling', apiJobId: payload.job_id }));
      const pollUrl = payload.progress_url || `http://20.72.80.42:8001/validation/status/${payload.job_id}`;
      for (let i = 0; i < 90; i++) {
        await new Promise(r => setTimeout(r, 2000));
        const pr = await axios.get(pollUrl, { headers: { accept: 'application/json' } });
        payload = pr.data;
        const st = String(payload?.status || '').toLowerCase();
        dispatch(addJobLog({ type: 'validation', message: `Poll attempt ${i + 1} — status: ${st}` }));
        dispatch(updateJobProgress({ type: 'validation', progress: Math.min(50 + i, 95) }));
        if (['success','completed','complete','done'].includes(st)) break;
        if (['failed','error'].includes(st)) throw new Error(payload?.error || 'Validation failed.');
      }
    }

    clearInterval(timer);
    dispatch(advanceStep({ type: 'validation', stepIndex: 4, statusMessage: 'Finalizing report…' }));
    
    if (payload) {
      saveJobResult('validation', fileName, payload);
      dispatch(updateJobProgress({ type: 'validation', progress: 100, statusMessage: 'Validation complete', status: 'success' }));
      dispatch(completeJob({ type: 'validation', statusMessage: 'Validation complete' }));
    } else {
      throw new Error('No data returned');
    }
  } catch (err: any) {
    clearInterval(timer);
    const apiError = err?.response?.data?.detail || err?.response?.data?.message || err.message;
    dispatch(failJob({ type: 'validation', errorMessage: apiError }));
  }
};
