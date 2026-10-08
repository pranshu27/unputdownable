import { useState, useCallback, useEffect } from 'react';
import { ValidationService, ValidationResult } from '../services/ValidationService.ts';

export type ValidationStep =
  | 'idle'
  | 'uploading'
  | 'validating'
  | 'success'
  | 'error';

interface UseValidationState {
  step: ValidationStep;
  result: ValidationResult | null;
  error: string | null;
  progress: number;
}

const getStorageKey = (fileName: string) => `forward_validation_state_${fileName}`;

export function useValidation(activeFileName: string = '') {
  const [state, setState] = useState<UseValidationState>(() => {
    if (!activeFileName) return { step: 'idle', result: null, error: null, progress: 0 };
    try {
      const cached = localStorage.getItem(getStorageKey(activeFileName));
      if (cached) {
        return JSON.parse(cached) as UseValidationState;
      }
    } catch (e) {
      console.error('Failed to parse cached validation state', e);
    }
    return { step: 'idle', result: null, error: null, progress: 0 };
  });

  // Re-initialize state if activeFileName changes
  useEffect(() => {
    if (!activeFileName) {
      setState({ step: 'idle', result: null, error: null, progress: 0 });
      return;
    }
    try {
      const cached = localStorage.getItem(getStorageKey(activeFileName));
      if (cached) {
        setState(JSON.parse(cached) as UseValidationState);
      } else {
        setState({ step: 'idle', result: null, error: null, progress: 0 });
      }
    } catch (e) {
      setState({ step: 'idle', result: null, error: null, progress: 0 });
    }
  }, [activeFileName]);

  const [datasetFile, setDatasetFile] = useState<File | null>(null);
  const [reportFile, setReportFile] = useState<File | null>(null);

  // Sync core state to localStorage whenever it changes
  useEffect(() => {
    if (activeFileName) {
      localStorage.setItem(getStorageKey(activeFileName), JSON.stringify(state));
    }
  }, [state, activeFileName]);

  const runValidation = useCallback(async (datasetZip: File, reportZip: File) => {
    setState({ step: 'uploading', error: null, progress: 10, result: null });

    const tick = (pct: number, delay: number) =>
      new Promise<void>((res) => setTimeout(() => {
        setState((prev) => ({ ...prev, progress: pct }));
        res();
      }, delay));

    try {
      await tick(25, 400);
      setState((prev) => ({ ...prev, step: 'validating', progress: 40 }));
      await tick(60, 600);

      const result = await ValidationService.validatePbip({ datasetZip, reportZip });

      await tick(90, 300);
      
      // Update state (which triggers the useEffect to save to localStorage)
      setState({ step: 'success', result, error: null, progress: 100 });
    } catch (err: any) {
      setState({
        step: 'error',
        error: err?.message || 'Validation failed',
        progress: 0,
        result: null
      });
    }
  }, []);

  const reset = useCallback(() => {
    setState({ step: 'idle', result: null, error: null, progress: 0 });
    setDatasetFile(null);
    setReportFile(null);
    if (activeFileName) {
      localStorage.removeItem(getStorageKey(activeFileName));
    }
  }, [activeFileName]);

  const canValidate = datasetFile !== null && reportFile !== null;

  return {
    ...state,
    datasetFile,
    reportFile,
    setDatasetFile,
    setReportFile,
    runValidation,
    reset,
    canValidate,
  };
}
