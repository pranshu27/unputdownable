import React, { useMemo } from 'react';
import { Download, Copy, Loader2, RefreshCw } from 'lucide-react';
import { ValidationResult, CheckDetail } from '../../services/ValidationService';
import SharedValidationReport, { 
  UnifiedValidationData, VStatus, UnifiedFinding, UnifiedCheckRow 
} from '../Components/SharedValidationReport.tsx';

interface Props {
  result: ValidationResult;
  onReset: () => void;
}

const mapSeverityToStatus = (status: string, severity?: string): VStatus => {
  if (status === 'passed') return 'PASS';
  if (status === 'missing') return 'MISSING';
  if (status === 'failed') return 'FAIL';
  return 'WARNING';
};

const mapCheckDetailToFinding = (c: CheckDetail, idx: number): UnifiedFinding => ({
  id: `${c.check_id}-${idx}`,
  checkId: c.check_id || 'UNKNOWN',
  category: c.category || 'General',
  status: mapSeverityToStatus(c.status, c.severity),
  title: c.source || `Check ${c.check_id}`,
  description: c.recommendation || '',
  severity: (c.severity || c.status).toUpperCase(),
  sourceValue: c.actual,
  jsonValue: c.expected,
});

export default function ValidationDashboard({ result, onReset }: Props) {
  
  const mappedData = useMemo<UnifiedValidationData>(() => {
    
    // Map Categories to UnifiedCheckRow
    const checkSummary: UnifiedCheckRow[] = result.categories.map(cat => ({
      check: cat.category,
      label: `${cat.total} checks`,
      description: `Detailed findings for ${cat.category} checks.`,
      scope: cat.category.toLowerCase().includes('semantic') ? 'semantic' : 'visual',
      score: cat.score,
      verdict: cat.score >= 70 ? 'PASS' : 'FAIL',
      passed: cat.passed,
      failed: cat.failed,
      missing: cat.missing,
      total: cat.total,
    }));

    // Collect all findings from all categories (FE currently only surfaces failed_checks_detail, 
    // but we can extract all checks if they exist in the categories, otherwise just use failed)
    let findings: UnifiedFinding[] = [];
    let idx = 0;
    
    // If the backend actually returned checks inside categories
    result.categories.forEach(cat => {
      if (cat.checks && Array.isArray(cat.checks)) {
        cat.checks.forEach(c => {
          findings.push(mapCheckDetailToFinding(c, idx++));
        });
      }
    });

    // Fallback: If categories didn't have checks, use failed_checks_detail
    if (findings.length === 0 && result.failed_checks_detail) {
      findings = result.failed_checks_detail.map(c => mapCheckDetailToFinding(c, idx++));
    }

    // Deduplicate findings by ID just in case
    const uniqueFindings = Array.from(new Map(findings.map(f => [f.id, f])).values());

    return {
      workbookId: result.report_name || 'N/A',
      timestamp: result.timestamp || new Date().toISOString(),
      overallScore: result.overall_score === null ? null : (result.overall_score || 0),
      semanticScore: result.semantic_score === null ? null : (result.semantic_score || 0),
      visualScore: result.visual_score === null ? null : (result.visual_score || 0),
      verdict: result.verdict || 'FAIL',
      semanticVerdict: result.semantic_score === null ? 'N/A' : (result.semantic_score >= 70 ? 'PASS' : 'FAIL'),
      visualVerdict: result.visual_score === null ? 'N/A' : (result.visual_score >= 70 ? 'PASS' : 'FAIL'),
      totalChecks: result.total_checks || 0,
      gapsCount: result.missing_validations || 0,
      checkSummary,
      findings: uniqueFindings
    };
  }, [result]);

  const handleDownloadJson = () => {
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
    const a = Object.assign(document.createElement('a'), {
      href: URL.createObjectURL(blob),
      download: `validation_report_${Date.now()}.json`,
    });
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const handleCopyJson = async () => {
    try { await navigator.clipboard.writeText(JSON.stringify(result, null, 2)); } catch { /* ignore */ }
  };

  const Toolbar = (
    <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 12, paddingBottom: 16, borderBottom: '1px solid #e2e8f0' }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 16 }}>
        <span style={{ fontSize: 12, color: '#94a3b8', fontFamily: 'monospace' }}>JOB ID: {result.job_id || 'N/A'}</span>
        <span style={{ fontSize: 12, color: '#94a3b8' }}>|</span>
        <span style={{ fontSize: 12, color: '#94a3b8' }}>{new Date(mappedData.timestamp!).toLocaleString()}</span>
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <button onClick={onReset}
          style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px', borderRadius: 4, background: '#ffffff', border: '1px solid #e2e8f0', color: '#0f172a', fontSize: 11, fontWeight: 600, cursor: 'pointer' }}>
          <RefreshCw size={12} /> New Validation
        </button>
        <button onClick={handleCopyJson}
          style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px', borderRadius: 4, background: '#ffffff', border: '1px solid #e2e8f0', color: '#0f172a', fontSize: 11, fontWeight: 600, cursor: 'pointer' }}>
          <Copy size={12} /> Copy JSON
        </button>
        <button onClick={handleDownloadJson}
          style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px', borderRadius: 4, background: '#ffffff', border: '1px solid #e2e8f0', color: '#0f172a', fontSize: 11, fontWeight: 600, cursor: 'pointer' }}>
          <Download size={12} /> Export JSON
        </button>
      </div>
    </div>
  );

  return (
    <div style={{ padding: 24, background: '#f8fafc', height: '100%', overflowY: 'auto' }}>
      <SharedValidationReport data={mappedData} ToolbarComponent={Toolbar} />
    </div>
  );
}
