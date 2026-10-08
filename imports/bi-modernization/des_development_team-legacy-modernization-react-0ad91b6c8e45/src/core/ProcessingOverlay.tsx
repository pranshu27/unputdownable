/**
 * ProcessingOverlay.tsx
 * 
 * Skeleton/loading overlay shown while a background job is running.
 * Prevents stale data flash — only shows latest completed API response.
 */
import React from 'react';
import { motion } from 'framer-motion';
import { Loader2 } from 'lucide-react';
import { useBackgroundJob } from '../utils/useBackgroundJob.ts';
import { JobType, JOB_LABELS } from '../utils/jobTrackerSlice.ts';

interface Props {
  jobType: JobType;
  fileName?: string;
  children: React.ReactNode;
}

const shimmer = `
@keyframes shimmer {
  0% { background-position: -400px 0; }
  100% { background-position: 400px 0; }
}
`;

const SkeletonBlock = ({ width = '100%', height = 16, mb = 8 }: { width?: string | number; height?: number; mb?: number }) => (
  <div style={{
    width, height, marginBottom: mb, borderRadius: 8,
    background: 'linear-gradient(90deg, #f1f5f9 25%, #e2e8f0 50%, #f1f5f9 75%)',
    backgroundSize: '800px 100%',
    animation: 'shimmer 1.8s infinite linear',
  }} />
);

export default function ProcessingOverlay({ jobType, fileName, children }: Props) {
  const { job, isRunning } = useBackgroundJob(jobType, fileName);

  if (!isRunning) return <>{children}</>;

  return (
    <>
      <style>{shimmer}</style>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        style={{
          position: 'relative',
          minHeight: 400,
          borderRadius: 16,
          overflow: 'hidden',
        }}
      >
        {/* Blurred content underneath */}
        <div style={{ filter: 'blur(4px) opacity(0.3)', pointerEvents: 'none' }}>
          {children}
        </div>

        {/* Overlay */}
        <div style={{
          position: 'absolute', inset: 0,
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
          background: 'rgba(248,250,252,0.85)',
          backdropFilter: 'blur(8px)',
          zIndex: 10,
        }}>
          {/* Spinner */}
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 1.5, repeat: Infinity, ease: 'linear' }}
            style={{ marginBottom: 20 }}
          >
            <Loader2 size={36} color="#2563eb" />
          </motion.div>

          <h3 style={{
            fontSize: 16, fontWeight: 700, color: '#0f172a',
            margin: '0 0 6px', letterSpacing: '-0.3px',
          }}>
            {JOB_LABELS[jobType]} Running…
          </h3>

          <p style={{ fontSize: 13, color: '#64748b', margin: '0 0 16px' }}>
            {job?.statusMessage || 'Processing in background…'}
          </p>

          {/* Progress bar */}
          {job && (
            <div style={{ width: 280, marginBottom: 16 }}>
              <div style={{
                height: 5, background: '#e2e8f0', borderRadius: 99,
                overflow: 'hidden',
              }}>
                <motion.div
                  animate={{ width: `${job.progress}%` }}
                  transition={{ duration: 0.6 }}
                  style={{
                    height: '100%', borderRadius: 99,
                    background: 'linear-gradient(90deg, #2563eb, #6366f1)',
                  }}
                />
              </div>
              <div style={{
                display: 'flex', justifyContent: 'space-between',
                marginTop: 4, fontSize: 11, fontFamily: 'monospace',
              }}>
                <span style={{ color: '#94a3b8' }}>
                  Step {(job.currentStepIndex || 0) + 1}/{job.steps?.length || 5}
                </span>
                <span style={{ color: '#2563eb', fontWeight: 700 }}>{job.progress}%</span>
              </div>
            </div>
          )}

          {/* Steps */}
          {job?.steps && (
            <div style={{
              display: 'flex', flexDirection: 'column', gap: 4,
              background: 'rgba(255,255,255,0.7)', borderRadius: 10,
              padding: '10px 16px', border: '1px solid #e2e8f0',
            }}>
              {job.steps.map((step, i) => {
                const dotColor = step.status === 'done' ? '#059669'
                  : step.status === 'active' ? '#2563eb'
                  : step.status === 'error' ? '#dc2626' : '#cbd5e1';
                return (
                  <div key={i} style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    fontSize: 11, color: step.status === 'active' ? '#2563eb' : '#94a3b8',
                    fontWeight: step.status === 'active' ? 700 : 400,
                  }}>
                    <span style={{
                      width: 7, height: 7, borderRadius: '50%',
                      background: dotColor, flexShrink: 0,
                      boxShadow: step.status === 'active' ? '0 0 8px #2563eb' : 'none',
                    }} />
                    {step.label}
                  </div>
                );
              })}
            </div>
          )}

          <p style={{
            fontSize: 11, color: '#94a3b8', marginTop: 16,
            fontStyle: 'italic',
          }}>
            You can navigate to other pages — processing continues in background.
          </p>
        </div>
      </motion.div>
    </>
  );
}
