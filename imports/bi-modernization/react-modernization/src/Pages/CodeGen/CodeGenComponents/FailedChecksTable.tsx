import React, { useMemo, useState } from 'react';
import { Search, X, ChevronDown, ChevronRight, AlertTriangle, AlertCircle, Info, Lightbulb } from 'lucide-react';
import { CheckDetail } from '../../../services/ValidationService';

const SEVERITY_CONFIG: Record<string, { label: string; bg: string; text: string; border: string; dot: string; icon: React.ReactNode }> = {
  critical: {
    label: 'Critical', bg: 'bg-red-50', text: 'text-red-700', border: 'border-red-200', dot: 'bg-red-500',
    icon: <AlertCircle size={12} className="text-red-600" />,
  },
  high: {
    label: 'High', bg: 'bg-orange-50', text: 'text-orange-700', border: 'border-orange-200', dot: 'bg-orange-500',
    icon: <AlertTriangle size={12} className="text-orange-600" />,
  },
  medium: {
    label: 'Medium', bg: 'bg-yellow-50', text: 'text-yellow-700', border: 'border-yellow-200', dot: 'bg-yellow-400',
    icon: <AlertTriangle size={12} className="text-yellow-600" />,
  },
  low: {
    label: 'Low', bg: 'bg-blue-50', text: 'text-blue-700', border: 'border-blue-200', dot: 'bg-blue-500',
    icon: <Info size={12} className="text-blue-600" />,
  },
  info: {
    label: 'Info', bg: 'bg-slate-50', text: 'text-slate-600', border: 'border-slate-200', dot: 'bg-slate-400',
    icon: <Info size={12} className="text-slate-500" />,
  },
};

const STATUS_CONFIG: Record<string, { bg: string; text: string; border: string }> = {
  failed:  { bg: 'bg-red-50',    text: 'text-red-700',    border: 'border-red-200'    },
  passed:  { bg: 'bg-emerald-50',text: 'text-emerald-700',border: 'border-emerald-200'},
  missing: { bg: 'bg-amber-50',  text: 'text-amber-700',  border: 'border-amber-200'  },
};

interface Props {
  checks: CheckDetail[];
}

export default function FailedChecksTable({ checks }: Props) {
  const [search, setSearch] = useState('');
  const [severityFilter, setSeverityFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim();
    return checks.filter((c) => {
      const matchSev = severityFilter === 'all' || c.severity === severityFilter;
      const matchSt  = statusFilter  === 'all' || c.status   === statusFilter;
      const matchQ   = !q || [c.check_id, c.source, c.expected, c.actual, c.recommendation, c.severity]
        .some((v) => String(v ?? '').toLowerCase().includes(q));
      return matchSev && matchSt && matchQ;
    });
  }, [checks, search, severityFilter, statusFilter]);

  const toggleRow = (id: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const severities = ['all', 'critical', 'high', 'medium', 'low', 'info'];
  const statuses   = ['all', 'failed', 'missing', 'passed'];

  if (checks.length === 0) {
    return (
      <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-6 py-8 text-center">
        <div className="w-12 h-12 rounded-xl bg-emerald-100 flex items-center justify-center mx-auto mb-3">
          <Info size={22} className="text-emerald-600" />
        </div>
        <p className="text-sm font-semibold text-emerald-700">No failed checks</p>
        <p className="text-xs text-emerald-500 mt-1">All validation checks passed successfully.</p>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
      {/* Toolbar */}
      <div className="px-4 py-3 border-b border-slate-100 bg-slate-50/60 flex flex-wrap gap-3 items-center">
        {/* Search */}
        <div className="relative flex-1 min-w-[200px] max-w-xs">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search checks…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-8 pr-8 py-1.5 text-xs rounded-lg border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-300"
          />
          {search && (
            <button onClick={() => setSearch('')} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-300 hover:text-slate-600">
              <X size={12} />
            </button>
          )}
        </div>

        {/* Severity filter */}
        <div className="flex gap-1 flex-wrap">
          {severities.map((sv) => {
            const cfg = sv !== 'all' ? SEVERITY_CONFIG[sv] : null;
            return (
              <button
                key={sv}
                onClick={() => setSeverityFilter(sv)}
                className={`flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-semibold border transition-all ${
                  severityFilter === sv
                    ? cfg ? `${cfg.bg} ${cfg.text} ${cfg.border}` : 'bg-slate-900 text-white border-slate-900'
                    : 'bg-white text-slate-500 border-slate-200 hover:border-slate-300'
                }`}
              >
                {cfg && <div className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />}
                {sv === 'all' ? 'All severity' : cfg?.label}
              </button>
            );
          })}
        </div>

        {/* Status filter */}
        <div className="flex gap-1">
          {statuses.map((st) => {
            const cfg = st !== 'all' ? STATUS_CONFIG[st] : null;
            return (
              <button
                key={st}
                onClick={() => setStatusFilter(st)}
                className={`px-2.5 py-1 rounded-full text-[10px] font-semibold border transition-all capitalize ${
                  statusFilter === st
                    ? cfg ? `${cfg.bg} ${cfg.text} ${cfg.border}` : 'bg-slate-900 text-white border-slate-900'
                    : 'bg-white text-slate-500 border-slate-200 hover:border-slate-300'
                }`}
              >
                {st === 'all' ? 'All status' : st}
              </button>
            );
          })}
        </div>

        <p className="ml-auto text-xs text-slate-400 shrink-0">{filtered.length} of {checks.length} checks</p>
      </div>

      {/* Table */}
      <div className="overflow-auto max-h-[560px]">
        <table className="w-full text-xs border-collapse" style={{ minWidth: 900 }}>
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200 sticky top-0 z-10">
              {['', 'Check ID', 'Severity', 'Source', 'Expected', 'Actual', 'Status'].map((h) => (
                <th key={h} className="px-3 py-2.5 text-left text-[10px] font-bold uppercase tracking-wider text-slate-400 whitespace-nowrap">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-6 py-10 text-center text-sm text-slate-400">
                  No checks match your filters.
                </td>
              </tr>
            ) : (
              filtered.map((check, idx) => {
                const sev = SEVERITY_CONFIG[check.severity] ?? SEVERITY_CONFIG.info;
                const st  = STATUS_CONFIG[check.status]   ?? STATUS_CONFIG.failed;
                const expanded = expandedRows.has(check.check_id);

                return (
                  <React.Fragment key={`${check.check_id}-${idx}`}>
                    <tr
                      className={`border-b border-slate-100 transition-colors cursor-pointer ${
                        idx % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'
                      } hover:bg-blue-50/30`}
                      onClick={() => toggleRow(check.check_id)}
                    >
                      {/* Expand toggle */}
                      <td className="px-3 py-2.5 w-6">
                        <span className="text-slate-300 hover:text-slate-600">
                          {expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                        </span>
                      </td>

                      {/* Check ID */}
                      <td className="px-3 py-2.5 font-mono font-semibold text-slate-700 whitespace-nowrap max-w-[160px]">
                        <span className="truncate block" title={check.check_id}>{check.check_id || '—'}</span>
                      </td>

                      {/* Severity */}
                      <td className="px-3 py-2.5">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-bold ${sev.bg} ${sev.text} ${sev.border}`}>
                          <div className={`w-1.5 h-1.5 rounded-full ${sev.dot}`} />
                          {sev.label}
                        </span>
                      </td>

                      {/* Source */}
                      <td className="px-3 py-2.5 text-slate-600 max-w-[120px]">
                        <span className="truncate block" title={check.source}>{check.source || '—'}</span>
                      </td>

                      {/* Expected */}
                      <td className="px-3 py-2.5 max-w-[150px]">
                        <span className="truncate block font-mono text-slate-500 text-[11px]" title={check.expected}>
                          {check.expected || '—'}
                        </span>
                      </td>

                      {/* Actual */}
                      <td className="px-3 py-2.5 max-w-[150px]">
                        <span className={`truncate block font-mono text-[11px] ${check.status === 'failed' ? 'text-red-600' : 'text-slate-500'}`} title={check.actual}>
                          {check.actual || '—'}
                        </span>
                      </td>

                      {/* Status */}
                      <td className="px-3 py-2.5">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full border text-[10px] font-bold capitalize ${st.bg} ${st.text} ${st.border}`}>
                          {check.status}
                        </span>
                      </td>
                    </tr>

                    {/* Expanded row */}
                    {expanded && (
                      <tr className="border-b border-slate-100 bg-gradient-to-r from-blue-50/60 to-white">
                        <td colSpan={7} className="px-6 py-3">
                          <div className="flex items-start gap-2">
                            <Lightbulb size={13} className="text-amber-500 mt-0.5 shrink-0" />
                            <div>
                              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-0.5">Recommendation</p>
                              <p className="text-xs text-slate-700 leading-relaxed">
                                {check.recommendation || 'No recommendation provided.'}
                              </p>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
