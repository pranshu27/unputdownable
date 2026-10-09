import React, { useEffect } from 'react';
import { useNavigate, useOutletContext } from 'react-router-dom';
import { AlertTriangle, ArrowLeft, Loader2, ShieldCheck } from 'lucide-react';
import ContentCard from '../../core/CardContent/CardContent.tsx';
import FileWorkspaceHeader from '../../core/FileWorkspaceHeader.tsx';
import UploadValidationAssets from '../CodeGen/CodeGenComponents/UploadValidationAssets.tsx';
import { useValidation } from '../../Hooks/useValidation.ts';
import { saveForwardValidationReport } from '../../services/validationReports.ts';

const getActiveFileName = () => {
  try {
    const details = JSON.parse(localStorage.getItem('fileDetails') || '{}');
    return localStorage.getItem('activePowerBiReportFile') || details?.fileName || '';
  } catch { return localStorage.getItem('activePowerBiReportFile') || ''; }
};

export default function ForwardValidationRun() {
  const navigate = useNavigate();
  const { sideNavWidth } = useOutletContext<{ sideNavWidth: number }>();
  const activeFileName = getActiveFileName();
  const validation = useValidation(activeFileName);


  useEffect(() => {
    if (validation.step !== 'success' || !validation.result) return;
    const report = saveForwardValidationReport(validation.result, {
      fileName: validation.reportFile?.name || localStorage.getItem('activePowerBiReportFile') || undefined,
      toolName: 'Power BI',
    });
    navigate(`/validations/${report.id}`, { replace: true });
  }, [navigate, validation.result, validation.reportFile?.name, validation.step]);

  const isLoading = validation.step === 'uploading' || validation.step === 'validating';

  return (
    <ContentCard
      heading={null}
      sideNavWidth={sideNavWidth}
      headerComponent={<FileWorkspaceHeader pageTitle="Forward Engineering Validation" />}
      flat={true}
    >
      <div style={{ minHeight: '100%', background: 'var(--surface-bg)', padding: 24, overflow: 'auto' }}>
        <div style={{ maxWidth: 1180, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 18 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <button
                onClick={() => navigate('/validations')}
                style={{
                  width: 34,
                  height: 34,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  borderRadius: 8,
                  border: '1px solid var(--border-primary)',
                  background: 'var(--surface-card)',
                  color: 'var(--text-secondary)',
                  cursor: 'pointer',
                }}
                title="Back to validation center"
              >
                <ArrowLeft size={16} />
              </button>
              <div>
                <p style={{ margin: 0, fontSize: 11, fontWeight: 700, color: 'var(--jnj-red)', textTransform: 'uppercase' }}>
                  Forward Engineering
                </p>
                <h1 style={{ margin: '3px 0 0', fontSize: 24, color: 'var(--text-primary)', fontWeight: 800 }}>
                  Validation Workspace
                </h1>
              </div>
            </div>

            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '8px 12px',
              border: '1px solid var(--border-primary)',
              borderRadius: 8,
              background: 'var(--surface-card)',
              color: isLoading ? '#b45309' : 'var(--text-secondary)',
              fontSize: 12,
              fontWeight: 700,
            }}>
              {isLoading ? <Loader2 size={14} className="animate-spin" /> : <ShieldCheck size={14} />}
              {isLoading ? 'Validation in progress' : 'Ready for package upload'}
            </div>
          </div>



          {(validation.step === 'uploading' || validation.step === 'validating') && (
            <div style={{
              height: 6,
              background: 'var(--surface-secondary)',
              borderRadius: 999,
              overflow: 'hidden',
              border: '1px solid var(--border-subtle)',
            }}>
              <div
                style={{
                  width: `${validation.progress}%`,
                  height: '100%',
                  background: 'var(--jnj-red)',
                  borderRadius: 999,
                  transition: 'width 0.5s ease',
                }}
              />
            </div>
          )}

          <section style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(0, 1fr) 320px',
            gap: 18,
            alignItems: 'start',
          }}>
            <div style={{
              border: '1px solid var(--border-primary)',
              background: 'var(--surface-card)',
              borderRadius: 10,
              padding: 18,
              boxShadow: '0 1px 3px rgba(15, 23, 42, 0.05)',
            }}>
              <UploadValidationAssets
                datasetFile={validation.datasetFile}
                reportFile={validation.reportFile}
                onDatasetChange={validation.setDatasetFile}
                onReportChange={validation.setReportFile}
                onValidate={() => {
                  if (validation.datasetFile && validation.reportFile) {
                    validation.runValidation(validation.datasetFile, validation.reportFile);
                  }
                }}
                isLoading={isLoading}
              />
            </div>

            <aside style={{
              border: '1px solid var(--border-primary)',
              background: 'var(--surface-card)',
              borderRadius: 10,
              padding: 16,
            }}>
              <p style={{ margin: 0, fontSize: 11, fontWeight: 800, color: 'var(--text-tertiary)', textTransform: 'uppercase' }}>
                Validation Intake
              </p>
              <div style={{ marginTop: 14, display: 'grid', gap: 12 }}>
                {[
                  ['Dataset ZIP', validation.datasetFile?.name || 'Waiting for upload'],
                  ['Report ZIP', validation.reportFile?.name || 'Waiting for upload'],
                  ['Output', 'Saved to Validation Center'],
                ].map(([label, value]) => (
                  <div key={label} style={{ display: 'grid', gap: 4 }}>
                    <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>{label}</span>
                    <span style={{ fontSize: 12, color: 'var(--text-primary)', fontWeight: 650, wordBreak: 'break-word' }}>
                      {value}
                    </span>
                  </div>
                ))}
              </div>
            </aside>
          </section>

          {validation.step === 'error' && (
            <div style={{
              display: 'flex',
              gap: 10,
              alignItems: 'flex-start',
              border: '1px solid #fecaca',
              background: '#fef2f2',
              color: '#b91c1c',
              borderRadius: 10,
              padding: 14,
              fontSize: 13,
            }}>
              <AlertTriangle size={16} style={{ marginTop: 1, flexShrink: 0 }} />
              <div>
                <strong>Validation failed</strong>
                <p style={{ margin: '3px 0 0' }}>{validation.error}</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </ContentCard>
  );
}

