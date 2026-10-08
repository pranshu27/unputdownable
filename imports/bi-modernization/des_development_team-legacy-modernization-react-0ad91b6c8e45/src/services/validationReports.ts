import { ValidationResult } from './ValidationService.ts';

export type ValidationReportType = 'forward' | 'reverse';

export interface StoredValidationReport {
  id: string;
  type: ValidationReportType;
  title: string;
  fileName: string;
  toolName: string;
  verdict: string;
  overallScore: number | null;
  semanticScore: number | null;
  visualScore: number | null;
  totalChecks: number;
  failedChecks: number;
  missingValidations: number;
  createdAt: string;
  result?: ValidationResult;
}

const FORWARD_REPORTS_KEY = 'jnj:forward-validation-reports';
const REVERSE_RESULT_PREFIX = 'jnj:job-result:validation:';

const safeParse = <T,>(raw: string | null, fallback: T): T => {
  if (!raw) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
};

const makeReportId = () =>
  `val-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

const getToolName = (fileName: string) => {
  const name = String(fileName || '').toLowerCase();
  if (name.endsWith('.pbix') || name.includes('power')) return 'Power BI';
  if (name.endsWith('.twb') || name.endsWith('.twbx')) return 'Tableau';
  if (name.endsWith('.qvf') || name.endsWith('.qvw')) return 'Qlik';
  return 'Power BI';
};

export const getForwardValidationReports = (): StoredValidationReport[] => {
  const reports = safeParse<StoredValidationReport[]>(
    localStorage.getItem(FORWARD_REPORTS_KEY),
    []
  );
  return Array.isArray(reports) ? reports : [];
};

export const saveForwardValidationReport = (
  result: ValidationResult,
  metadata: { fileName?: string; toolName?: string } = {}
) => {
  const id = makeReportId();
  const fileName =
    metadata.fileName ||
    result.report_name ||
    result.dataset_name ||
    localStorage.getItem('activePowerBiReportFile') ||
    'Forward Engineering Validation';

  const report: StoredValidationReport = {
    id,
    type: 'forward',
    title: result.report_name || 'Forward Engineering Validation',
    fileName,
    toolName: metadata.toolName || getToolName(fileName),
    verdict: result.verdict,
    overallScore: result.overall_score,
    semanticScore: result.semantic_score,
    visualScore: result.visual_score,
    totalChecks: Number(result.total_checks || 0),
    failedChecks: Number(result.failed_checks || 0),
    missingValidations: Number(result.missing_validations || 0),
    createdAt: result.timestamp || new Date().toISOString(),
    result,
  };

  const next = [report, ...getForwardValidationReports()]
    .filter((item, index, all) => all.findIndex((candidate) => candidate.id === item.id) === index)
    .slice(0, 25);

  localStorage.setItem(FORWARD_REPORTS_KEY, JSON.stringify(next));
  window.dispatchEvent(new CustomEvent('jnj:validation-reports-changed'));
  return report;
};

export const getForwardValidationReport = (id: string) =>
  getForwardValidationReports().find((report) => report.id === id) || null;

const getReverseValidationReports = (): StoredValidationReport[] => {
  const reports: StoredValidationReport[] = [];

  for (let i = 0; i < localStorage.length; i += 1) {
    const key = localStorage.key(i);
    if (!key?.startsWith(REVERSE_RESULT_PREFIX)) continue;

    const stored = safeParse<any>(localStorage.getItem(key), null);
    const raw = stored?.result;
    if (!raw) continue;

    const fileName = stored.fileName || key.slice(REVERSE_RESULT_PREFIX.length);
    const report = Array.isArray(raw) ? raw[0] || {} : raw;
    const score = Number(report.score ?? report.overall_score ?? report.report?.overall_score ?? 0);
    const verdict = String(report.verdict ?? report.report?.overall_verdict ?? (score >= 80 ? 'PASS' : 'FAIL')).toUpperCase();

    reports.push({
      id: `reverse:${encodeURIComponent(fileName)}`,
      type: 'reverse',
      title: 'Reverse Engineering Validation',
      fileName,
      toolName: getToolName(fileName),
      verdict,
      overallScore: report.score ?? report.overall_score ?? report.report?.overall_score ?? null,
      semanticScore: report.semantic_score ?? report.report?.semantic_score ?? null,
      visualScore: report.visual_score ?? report.report?.visual_score ?? null,
      totalChecks: Number(report.total_checks ?? 0),
      failedChecks: Number(report.failed_checks ?? report.gaps_count ?? 0),
      missingValidations: Number(report.missing_validations ?? 0),
      createdAt: stored.savedAt || report.timestamp || report.report?.timestamp || new Date().toISOString(),
    });
  }

  return reports;
};

export const getValidationReports = () =>
  [...getForwardValidationReports(), ...getReverseValidationReports()]
    .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());

