import React from 'react';
import { useNavigate, useOutletContext, useParams } from 'react-router-dom';
import { ArrowLeft, FileSearch } from 'lucide-react';
import ContentCard from '../../core/CardContent/CardContent.tsx';
import FileWorkspaceHeader from '../../core/FileWorkspaceHeader.tsx';
import ValidationDashboard from '../CodeGen/ValidationDashboard.tsx';
import { getForwardValidationReport } from '../../services/validationReports.ts';

export default function ForwardValidationReportPage() {
  const navigate = useNavigate();
  const { reportId = '' } = useParams();
  const { sideNavWidth } = useOutletContext<{ sideNavWidth: number }>();
  const report = getForwardValidationReport(reportId);

  return (
    <ContentCard
      heading={null}
      sideNavWidth={sideNavWidth}
      headerComponent={<FileWorkspaceHeader pageTitle="Forward Engineering Validation Report" />}
      flat={true}
    >
      <div style={{ minHeight: '100%', background: 'var(--surface-bg)', padding: 24, overflow: 'auto' }}>
        <div style={{ maxWidth: 1280, margin: '0 auto' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, marginBottom: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <button
                onClick={() => navigate('/validations')}
                style={{
                  width: 34,
                  height: 34,
                  borderRadius: 8,
                  border: '1px solid var(--border-primary)',
                  background: 'var(--surface-card)',
                  color: 'var(--text-secondary)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: 'pointer',
                }}
                title="Back to validation center"
              >
                <ArrowLeft size={16} />
              </button>
              <div>
                <p style={{ margin: 0, fontSize: 11, fontWeight: 700, color: 'var(--jnj-red)', textTransform: 'uppercase' }}>
                  Forward Engineering Validation
                </p>
                <h1 style={{ margin: '3px 0 0', fontSize: 24, color: 'var(--text-primary)', fontWeight: 800 }}>
                  {report?.fileName || 'Validation Report'}
                </h1>
              </div>
            </div>
          </div>

          {!report?.result ? (
            <div style={{
              border: '1px solid var(--border-primary)',
              background: 'var(--surface-card)',
              borderRadius: 10,
              padding: 32,
              textAlign: 'center',
              color: 'var(--text-secondary)',
            }}>
              <FileSearch size={30} style={{ margin: '0 auto 10px', color: 'var(--text-tertiary)' }} />
              <p style={{ margin: 0, fontWeight: 700, color: 'var(--text-primary)' }}>Report not found</p>
              <p style={{ margin: '5px 0 0', fontSize: 13 }}>Open the Validation Center and choose an available report.</p>
            </div>
          ) : (
            <div style={{
              border: '1px solid var(--border-primary)',
              background: 'var(--surface-card)',
              borderRadius: 10,
              padding: 18,
            }}>
              <ValidationDashboard result={report.result} onReset={() => navigate('/validations/forward/new')} />
            </div>
          )}
        </div>
      </div>
    </ContentCard>
  );
}

