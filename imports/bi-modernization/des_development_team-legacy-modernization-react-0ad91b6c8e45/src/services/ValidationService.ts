export interface ValidationParams {
  datasetZip: File;
  reportZip: File;
}

export interface CheckDetail {
  check_id: string;
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info';
  source: string;
  expected: string;
  actual: string;
  recommendation: string;
  status: 'failed' | 'passed' | 'missing';
  category?: string;
}

export interface ValidationCategory {
  category: string;
  total: number;
  passed: number;
  failed: number;
  missing: number;
  score: number;
  checks: CheckDetail[];
}

export interface ValidationResult {
  overall_score: number | null;
  semantic_score: number | null;
  visual_score: number | null;
  verdict: string;
  total_checks: number;
  passed_checks: number;
  failed_checks: number;
  missing_validations: number;
  timestamp: string;
  workspace?: string;
  report_name?: string;
  dataset_name?: string;
  job_id?: string;
  categories: ValidationCategory[];
  failed_checks_detail: CheckDetail[];
  api_logs?: string[];
  summary?: string;
}

const VALIDATION_API = 'http://20.72.80.42:8004/validate_pbip/';

const CATEGORY_LABELS: Record<string, string> = {
  semantic: 'Semantic Validation',
  visual: 'Visual Validation',
  kpi: 'Kpi Validation',
  relationship: 'Relationship Validation',
  dataset: 'Dataset Validation',
  dax: 'Dax Validation',
  metadata: 'Metadata Validation',
};

function normalizeStatus(status: unknown): CheckDetail['status'] {
  const value = String(status ?? '').toLowerCase();
  if (value === 'pass' || value === 'passed') return 'passed';
  if (value === 'missing') return 'missing';
  return 'failed';
}

function normalizeSeverity(severity: unknown): CheckDetail['severity'] {
  const value = String(severity ?? 'info').toLowerCase();
  if (['critical', 'high', 'medium', 'low', 'info'].includes(value)) {
    return value as CheckDetail['severity'];
  }
  return 'info';
}

function normalizeCheckDetail(raw: any): CheckDetail {
  return {
    check_id: String(raw?.check_id ?? raw?.check ?? raw?.attribute ?? 'check'),
    severity: normalizeSeverity(raw?.severity),
    source: String(raw?.source ?? raw?.attribute ?? raw?.label ?? ''),
    expected: String(raw?.expected ?? raw?.source_value ?? ''),
    actual: String(raw?.actual ?? raw?.json_value ?? ''),
    recommendation: String(raw?.recommendation ?? raw?.note ?? raw?.description ?? ''),
    status: normalizeStatus(raw?.status ?? raw?.verdict),
    category: raw?.category ?? raw?.scope,
  };
}

export const ValidationService = {
  /**
   * Reads the paired Power BI report JSONs from localStorage
   * (stored by MigrationAgent as pairedPowerBiReports)
   * and returns [json1, json2] — no user upload required for these.
   */
  getPairedJsons(): [any, any] {
    try {
      const raw = localStorage.getItem('pairedPowerBiReports');
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed) && parsed.length >= 2) {
          return [parsed[0], parsed[1]];
        }
        if (Array.isArray(parsed) && parsed.length === 1) {
          return [parsed[0], parsed[0]];
        }
      }
    } catch (e) {
      console.warn('Could not read pairedPowerBiReports from localStorage', e);
    }

    // Fallback: try activePowerBiReportData
    try {
      const raw = localStorage.getItem('activePowerBiReportData');
      if (raw) {
        const parsed = JSON.parse(raw);
        const data = parsed?.result || parsed?.data || parsed;
        return [data, data];
      }
    } catch (e) {
      console.warn('Could not read activePowerBiReportData from localStorage', e);
    }

    return [{}, {}];
  },

  async validatePbip(params: ValidationParams): Promise<ValidationResult> {
    const [json1Output, json2Output] = this.getPairedJsons();

    const formData = new FormData();

    // Build virtual JSON files from memory — user never uploads these
    formData.append(
      'json1',
      new File([JSON.stringify(json1Output)], 'json1.json', { type: 'application/json' })
    );
    formData.append(
      'json2',
      new File([JSON.stringify(json2Output)], 'json2.json', { type: 'application/json' })
    );

    formData.append('dataset_zip', params.datasetZip);
    formData.append('report_zip', params.reportZip);

    const response = await fetch(VALIDATION_API, {
      method: 'POST',
      headers: { accept: 'application/json' },
      body: formData,
    });

    if (!response.ok) {
      let errorMessage = `Validation API failed (${response.status})`;
      try {
        const errorData = await response.json();
        errorMessage = errorData.detail || errorData.message || JSON.stringify(errorData);
      } catch {
        const text = await response.text();
        if (text) errorMessage = text;
      }
      throw new Error(errorMessage);
    }

    const raw = await response.json();
    return normalizeValidationResult(raw);
  },
};

/** Normalize any API shape into our consistent ValidationResult */
function normalizeValidationResult(raw: any): ValidationResult {
  const payload = Array.isArray(raw) ? raw[0] ?? {} : raw ?? {};
  const report = payload.report ?? {};
  const scoreBreakdown = payload.score_breakdown ?? {};
  const summaryRows = Array.isArray(payload.check_summary)
    ? payload.check_summary
    : Array.isArray(report.check_summary)
      ? report.check_summary
      : [];
  const allResultRows = Array.isArray(report.all_results) ? report.all_results : [];
  const gapRows = Array.isArray(payload.gap_report?.gaps) ? payload.gap_report.gaps : [];

  const categories: ValidationCategory[] = [
    'semantic', 'visual', 'kpi', 'relationship', 'dataset', 'dax', 'metadata'
  ].map((key) => {
    const src = payload[key] || payload[`${key}_validation`] || scoreBreakdown[key] || {};
    const scopedSummary = summaryRows.filter((row: any) => String(row?.scope ?? '').toLowerCase() === key);
    const summaryChecks = scopedSummary.length > 0 ? scopedSummary : Array.isArray(src.checks) ? src.checks : [];
    const checkIds = new Set(summaryChecks.map((row: any) => String(row?.check ?? row?.check_id ?? '')));
    const checks: CheckDetail[] = allResultRows
      .filter((row: any) => checkIds.has(String(row?.check_id ?? row?.check ?? '')))
      .map(normalizeCheckDetail);
    const passed = src.passed ?? summaryChecks.reduce((sum: number, row: any) => sum + Number(row?.passed ?? 0), 0);
    const failed = src.failed ?? summaryChecks.reduce((sum: number, row: any) => sum + Number(row?.failed ?? 0), 0);
    const missing = src.missing ?? summaryChecks.reduce((sum: number, row: any) => sum + Number(row?.missing ?? 0), 0);

    return {
      category: CATEGORY_LABELS[key],
      total: src.total ?? summaryChecks.reduce((sum: number, row: any) => sum + Number(row?.total ?? 0), 0) ?? checks.length,
      passed,
      failed,
      missing,
      score: src.score ?? 0,
      checks,
    };
  });

  const allFailed: CheckDetail[] = [
    ...(payload.failed_checks_detail || []).map(normalizeCheckDetail),
    ...gapRows.map(normalizeCheckDetail),
    ...categories.flatMap((c) => c.checks.filter((ch) => ch.status === 'failed')),
  ];

  // De-dup by row identity. Multiple gaps can share a check_id.
  const seen = new Set<string>();
  const deduped = allFailed.filter((c) => {
    const key = `${c.check_id}|${c.source}|${c.status}|${c.expected}|${c.actual}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  const totalFromCategories = categories.reduce((s, c) => s + c.total, 0);
  const passedFromCategories = categories.reduce((s, c) => s + c.passed, 0);
  const missingFromCategories = categories.reduce((s, c) => s + c.missing, 0);

  return {
    overall_score: payload.overall_score ?? payload.score ?? report.overall_score ?? null,
    semantic_score: payload.semantic_score ?? report.semantic_score ?? payload.semantic?.score ?? null,
    visual_score: payload.visual_score ?? report.visual_score ?? payload.visual?.score ?? null,
    verdict: payload.verdict ?? report.overall_verdict ?? (
      (payload.overall_score ?? payload.score ?? report.overall_score) === null ? 'N/A' :
      ((payload.overall_score ?? payload.score ?? report.overall_score ?? 0) >= 80 ? 'PASS' : 'FAIL')
    ),
    total_checks: payload.total_checks ?? totalFromCategories,
    passed_checks: payload.passed_checks ?? passedFromCategories,
    failed_checks: payload.failed_checks ?? payload.gaps_count ?? deduped.length,
    missing_validations: payload.missing_validations ?? missingFromCategories,
    timestamp: payload.timestamp ?? report.timestamp ?? new Date().toISOString(),
    workspace: payload.workspace,
    report_name: payload.report_name ?? payload.file_name,
    dataset_name: payload.dataset_name,
    job_id: payload.job_id ?? payload.workbook_id,
    categories,
    failed_checks_detail: deduped,
    api_logs: payload.api_logs || [],
    summary: payload.summary,
  };
}
