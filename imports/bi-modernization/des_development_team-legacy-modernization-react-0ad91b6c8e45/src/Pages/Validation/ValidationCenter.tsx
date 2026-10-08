import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useOutletContext } from 'react-router-dom';
import {
  ArrowUpRight,
  CheckCircle2,
  Clock3,
  FileCheck2,
  PlayCircle,
  Search,
  ShieldCheck,
  XCircle,
} from 'lucide-react';
import ContentCard from '../../core/CardContent/CardContent.tsx';
import FileWorkspaceHeader from '../../core/FileWorkspaceHeader.tsx';
import { getValidationReports, StoredValidationReport } from '../../services/validationReports.ts';

const verdictColor = (verdict: string) => {
  const value = verdict.toUpperCase();
  if (value === 'PASS') return { bg: '#ecfdf5', text: '#047857', border: '#a7f3d0', icon: <CheckCircle2 size={13} /> };
  if (value === 'FAIL') return { bg: '#fef2f2', text: '#b91c1c', border: '#fecaca', icon: <XCircle size={13} /> };
  return { bg: '#fffbeb', text: '#b45309', border: '#fde68a', icon: <Clock3 size={13} /> };
};

const ReportRow = ({ report, onView }: { report: StoredValidationReport; onView: () => void }) => {
  const verdict = verdictColor(report.verdict);

  return (
    <tr>
      <td style={{ padding: '13px 16px', borderBottom: '1px solid var(--border-subtle)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 34,
            height: 34,
            borderRadius: 8,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: report.type === 'forward' ? '#1d4ed8' : 'var(--jnj-red)',
            background: report.type === 'forward' ? '#eff6ff' : 'var(--jnj-red-light)',
            border: '1px solid var(--border-primary)',
          }}>
            <ShieldCheck size={16} />
          </div>
          <div style={{ minWidth: 0 }}>
            <p style={{ margin: 0, fontSize: 13, fontWeight: 750, color: 'var(--text-primary)' }}>{report.title}</p>
            <p style={{ margin: '2px 0 0', fontSize: 11, color: 'var(--text-tertiary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 420 }}>
              {report.fileName}
            </p>
          </div>
        </div>
      </td>
      <td style={{ padding: '13px 16px', borderBottom: '1px solid var(--border-subtle)' }}>
        <span style={{
          display: 'inline-flex',
          alignItems: 'center',
          padding: '4px 8px',
          borderRadius: 6,
          background: report.type === 'forward' ? '#eff6ff' : '#fff7ed',
          color: report.type === 'forward' ? '#1d4ed8' : '#c2410c',
          border: '1px solid var(--border-primary)',
          fontSize: 11,
          fontWeight: 750,
        }}>
          {report.type === 'forward' ? 'Forward' : 'Reverse'}
        </span>
      </td>
      <td style={{ padding: '13px 16px', borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-secondary)', fontSize: 12 }}>
        {report.toolName}
      </td>
      <td style={{ padding: '13px 16px', borderBottom: '1px solid var(--border-subtle)' }}>
        <span style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 5,
          padding: '4px 8px',
          borderRadius: 6,
          background: verdict.bg,
          color: verdict.text,
          border: `1px solid ${verdict.border}`,
          fontSize: 11,
          fontWeight: 800,
        }}>
          {verdict.icon}
          {report.verdict}
        </span>
      </td>
      <td style={{ padding: '13px 16px', borderBottom: '1px solid var(--border-subtle)', fontFamily: 'monospace', fontWeight: 800, color: 'var(--text-primary)' }}>
        {report.overallScore.toFixed(1)}
      </td>
      <td style={{ padding: '13px 16px', borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-secondary)', fontSize: 12 }}>
        {new Date(report.createdAt).toLocaleString()}
      </td>
      <td style={{ padding: '13px 16px', borderBottom: '1px solid var(--border-subtle)', textAlign: 'right' }}>
        <button
          onClick={onView}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            padding: '7px 12px',
            borderRadius: 7,
            border: '1px solid var(--border-primary)',
            background: 'var(--surface-card)',
            color: 'var(--text-primary)',
            fontSize: 12,
            fontWeight: 700,
            cursor: 'pointer',
          }}
        >
          View
          <ArrowUpRight size={13} />
        </button>
      </td>
    </tr>
  );
};

export default function ValidationCenter() {
  const navigate = useNavigate();
  const { sideNavWidth } = useOutletContext<{ sideNavWidth: number }>();
  const [reports, setReports] = useState<StoredValidationReport[]>(() => getValidationReports());
  const [query, setQuery] = useState('');
  const [type, setType] = useState<'all' | 'forward' | 'reverse'>('all');

  useEffect(() => {
    const refresh = () => setReports(getValidationReports());
    window.addEventListener('jnj:validation-reports-changed', refresh);
    window.addEventListener('storage', refresh);
    return () => {
      window.removeEventListener('jnj:validation-reports-changed', refresh);
      window.removeEventListener('storage', refresh);
    };
  }, []);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return reports.filter((report) => {
      if (type !== 'all' && report.type !== type) return false;
      if (!needle) return true;
      return [report.title, report.fileName, report.toolName, report.verdict]
        .some((value) => String(value).toLowerCase().includes(needle));
    });
  }, [query, reports, type]);

  const stats = useMemo(() => {
    const forward = reports.filter((report) => report.type === 'forward').length;
    const reverse = reports.filter((report) => report.type === 'reverse').length;
    const pass = reports.filter((report) => report.verdict.toUpperCase() === 'PASS').length;
    return { total: reports.length, forward, reverse, pass };
  }, [reports]);

  const viewReport = (report: StoredValidationReport) => {
    if (report.type === 'forward') {
      navigate(`/validations/${report.id}`);
      return;
    }
    localStorage.setItem('activePowerBiReportFile', report.fileName);
    window.dispatchEvent(new CustomEvent('jnj:active-report-changed'));
    navigate('/validation-dashboard?tab=reverse');
  };

  return (
    <ContentCard
      heading={null}
      sideNavWidth={sideNavWidth}
      headerComponent={<FileWorkspaceHeader pageTitle="Validation Center" />}
      flat={true}
    >
      <div style={{ minHeight: '100%', background: 'var(--surface-bg)', padding: 24, overflow: 'auto' }}>
        <div style={{ maxWidth: 1280, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 18 }}>
          <section style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(0, 1fr) auto',
            gap: 18,
            alignItems: 'end',
          }}>
            <div>
              <p style={{ margin: 0, fontSize: 11, fontWeight: 800, color: 'var(--jnj-red)', textTransform: 'uppercase' }}>
                Validation governance
              </p>
              <h1 style={{ margin: '4px 0 0', fontSize: 26, fontWeight: 850, color: 'var(--text-primary)' }}>
                Validation Center
              </h1>
              <p style={{ margin: '6px 0 0', fontSize: 13, color: 'var(--text-secondary)' }}>
                Forward and reverse engineering validation reports are stored here for review.
              </p>
            </div>
            <button
              onClick={() => navigate('/validations/forward/new')}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
                padding: '10px 14px',
                borderRadius: 8,
                border: 'none',
                background: 'var(--jnj-red)',
                color: '#fff',
                fontSize: 13,
                fontWeight: 800,
                cursor: 'pointer',
              }}
            >
              <PlayCircle size={15} />
              New Forward Validation
            </button>
          </section>

          <section style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 12 }}>
            {[
              ['Total reports', stats.total],
              ['Forward', stats.forward],
              ['Reverse', stats.reverse],
              ['Passed', stats.pass],
            ].map(([label, value]) => (
              <div key={label} style={{
                border: '1px solid var(--border-primary)',
                background: 'var(--surface-card)',
                borderRadius: 10,
                padding: 14,
              }}>
                <p style={{ margin: 0, fontSize: 11, color: 'var(--text-tertiary)', fontWeight: 700 }}>{label}</p>
                <p style={{ margin: '6px 0 0', fontSize: 24, fontWeight: 850, color: 'var(--text-primary)', fontFamily: 'monospace' }}>
                  {value}
                </p>
              </div>
            ))}
          </section>

          <section style={{
            border: '1px solid var(--border-primary)',
            background: 'var(--surface-card)',
            borderRadius: 10,
            overflow: 'hidden',
          }}>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: 14,
              borderBottom: '1px solid var(--border-primary)',
              background: 'var(--surface-secondary)',
            }}>
              <div style={{ position: 'relative', flex: 1, maxWidth: 360 }}>
                <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-tertiary)' }} />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search reports"
                  style={{
                    width: '100%',
                    height: 34,
                    padding: '0 10px 0 32px',
                    borderRadius: 7,
                    border: '1px solid var(--border-primary)',
                    background: 'var(--surface-card)',
                    color: 'var(--text-primary)',
                    fontSize: 12,
                    outline: 'none',
                  }}
                />
              </div>
              {(['all', 'forward', 'reverse'] as const).map((item) => (
                <button
                  key={item}
                  onClick={() => setType(item)}
                  style={{
                    padding: '8px 11px',
                    borderRadius: 7,
                    border: '1px solid var(--border-primary)',
                    background: type === item ? 'var(--jnj-red-light)' : 'var(--surface-card)',
                    color: type === item ? 'var(--jnj-red)' : 'var(--text-secondary)',
                    fontSize: 12,
                    fontWeight: 750,
                    cursor: 'pointer',
                    textTransform: 'capitalize',
                  }}
                >
                  {item}
                </button>
              ))}
            </div>

            {filtered.length === 0 ? (
              <div style={{ padding: 42, textAlign: 'center', color: 'var(--text-secondary)' }}>
                <FileCheck2 size={28} style={{ margin: '0 auto 10px', color: 'var(--text-tertiary)' }} />
                <p style={{ margin: 0, fontWeight: 750, color: 'var(--text-primary)' }}>No validation reports found</p>
                <p style={{ margin: '5px 0 0', fontSize: 13 }}>Run a validation or adjust your filters.</p>
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 900 }}>
                  <thead>
                    <tr style={{ background: 'var(--surface-card)' }}>
                      {['Report', 'Type', 'Tool', 'Verdict', 'Score', 'Run Time', ''].map((header) => (
                        <th
                          key={header}
                          style={{
                            padding: '10px 16px',
                            borderBottom: '1px solid var(--border-primary)',
                            color: 'var(--text-tertiary)',
                            fontSize: 10,
                            fontWeight: 800,
                            textTransform: 'uppercase',
                            textAlign: header ? 'left' : 'right',
                          }}
                        >
                          {header}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((report) => (
                      <ReportRow key={report.id} report={report} onView={() => viewReport(report)} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      </div>
    </ContentCard>
  );
}

