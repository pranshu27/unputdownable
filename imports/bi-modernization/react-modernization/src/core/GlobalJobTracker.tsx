import React, { useState, useEffect } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  selectAllJobs, selectActiveJobs, selectToasts,
  dismissJob, dismissToast, TrackedJob, JobType,
  JOB_LABELS, JOB_ROUTES,
} from '../utils/jobTrackerSlice.ts';
import {
  Activity, AlertTriangle, CheckCircle2, ChevronDown, ChevronUp,
  Loader2, X, ExternalLink, Clock, Minimize2, Maximize2,
} from 'lucide-react';

/* ─── Styles ─────────────────────────────────────────── */
const glass = {
  background: 'rgba(255,255,255,0.82)',
  backdropFilter: 'blur(20px) saturate(1.6)',
  WebkitBackdropFilter: 'blur(20px) saturate(1.6)',
  border: '1px solid rgba(255,255,255,0.45)',
  boxShadow: '0 8px 40px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.06)',
};

const statusCfg: Record<string, { color: string; bg: string; border: string }> = {
  running: { color: '#2563eb', bg: '#eff6ff', border: '#bfdbfe' },
  polling: { color: '#7c3aed', bg: '#f5f3ff', border: '#ddd6fe' },
  queued:  { color: '#d97706', bg: '#fffbeb', border: '#fde68a' },
  complete:{ color: '#059669', bg: '#ecfdf5', border: '#a7f3d0' },
  error:   { color: '#dc2626', bg: '#fef2f2', border: '#fecaca' },
};

const fmt = (ms: number) => {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  return m > 0 ? `${m}m ${s % 60}s` : `${s}s`;
};

/* ─── Toast Layer ────────────────────────────────────── */
function ToastLayer() {
  const dispatch = useDispatch();
  const toasts = useSelector(selectToasts);
  useEffect(() => {
    toasts.forEach(t => {
      const age = Date.now() - new Date(t.createdAt).getTime();
      if (age < 5000) {
        const id = setTimeout(() => dispatch(dismissToast(t.id)), 5000 - age);
        return () => clearTimeout(id);
      } else dispatch(dismissToast(t.id));
    });
  }, [toasts]);

  const colors: Record<string, string> = { success: '#059669', error: '#dc2626', info: '#2563eb', warning: '#d97706' };
  const bgs: Record<string, string> = { success: '#ecfdf5', error: '#fef2f2', info: '#eff6ff', warning: '#fffbeb' };

  return (
    <div style={{ position: 'fixed', top: 20, right: 20, zIndex: 10001, display: 'flex', flexDirection: 'column', gap: 8, width: 360 }}>
      <AnimatePresence>
        {toasts.slice(-3).map(t => (
          <motion.div key={t.id} initial={{ opacity: 0, x: 60, scale: 0.95 }} animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: 60 }} transition={{ type: 'spring', stiffness: 400, damping: 30 }}
            style={{ ...glass, borderRadius: 12, padding: '12px 16px', borderLeft: `4px solid ${colors[t.type]}`,
              display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}
            onClick={() => dispatch(dismissToast(t.id))}>
            {t.type === 'success' && <CheckCircle2 size={16} color={colors.success} />}
            {t.type === 'error' && <AlertTriangle size={16} color={colors.error} />}
            {t.type === 'info' && <Activity size={16} color={colors.info} />}
            <span style={{ fontSize: 12, fontWeight: 600, color: '#0f172a', flex: 1 }}>{t.message}</span>
            <X size={12} color="#94a3b8" />
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

/* ─── Job Card ───────────────────────────────────────── */
function JobCard({ job, onDismiss, onNav }: { job: TrackedJob; onDismiss: () => void; onNav: () => void }) {
  const [showLogs, setShowLogs] = useState(false);
  const isActive = job.status === 'running' || job.status === 'polling' || job.status === 'queued';
  const cfg = statusCfg[job.status] || statusCfg.running;
  const elapsed = isActive ? Date.now() - new Date(job.startedAt).getTime() : 0;
  const eta = job.estimatedTotalMs && isActive
    ? Math.max(0, job.estimatedTotalMs - elapsed) : 0;
  const steps = Array.isArray(job.steps) ? job.steps : [];
  const logs = Array.isArray(job.logs) ? job.logs : [];
  const [, setTick] = useState(0);
  useEffect(() => { if (!isActive) return; const i = setInterval(() => setTick(t => t + 1), 1000); return () => clearInterval(i); }, [isActive]);

  return (
    <motion.div layout initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}
      style={{ padding: '14px 16px', borderBottom: '1px solid rgba(0,0,0,0.06)' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, minWidth: 0 }}>
          <div style={{ width: 32, height: 32, borderRadius: 8, background: cfg.bg, border: `1px solid ${cfg.border}`,
            display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
            {isActive ? <Loader2 size={14} color={cfg.color} className="animate-spin" />
              : job.status === 'complete' ? <CheckCircle2 size={14} color={cfg.color} />
              : <AlertTriangle size={14} color={cfg.color} />}
          </div>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#0f172a', display: 'flex', alignItems: 'center', gap: 6 }}>
              {JOB_LABELS[job.type]}
              <span style={{ fontSize: 9, fontWeight: 700, padding: '1px 6px', borderRadius: 4,
                background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.border}`, textTransform: 'uppercase' }}>
                {job.status}
              </span>
            </div>
            {job.fileName && <p style={{ fontSize: 10, color: '#94a3b8', margin: '2px 0 0', fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{job.fileName}</p>}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          {!isActive && <button onClick={onNav} title="View results" style={{ width: 24, height: 24, borderRadius: 6, border: '1px solid #e2e8f0', background: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <ExternalLink size={11} color="#64748b" />
          </button>}
          {!isActive && <button onClick={onDismiss} title="Dismiss" style={{ width: 24, height: 24, borderRadius: 6, border: '1px solid #e2e8f0', background: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <X size={11} color="#94a3b8" />
          </button>}
        </div>
      </div>

      {/* Status message */}
      <p style={{ fontSize: 11, color: '#64748b', margin: '0 0 6px', fontWeight: 500 }}>{job.statusMessage}</p>

      {/* Progress bar */}
      {isActive && (
        <div style={{ marginBottom: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
            <span style={{ fontSize: 10, color: '#94a3b8', fontFamily: 'monospace' }}>{fmt(elapsed)}</span>
            {eta > 0 && <span style={{ fontSize: 10, color: '#94a3b8' }}>~{fmt(eta)} remaining</span>}
            <span style={{ fontSize: 10, color: cfg.color, fontWeight: 700, fontFamily: 'monospace' }}>{job.progress}%</span>
          </div>
          <div style={{ height: 4, background: '#e2e8f0', borderRadius: 99, overflow: 'hidden' }}>
            <motion.div animate={{ width: `${job.progress}%` }} transition={{ duration: 0.6, ease: 'easeOut' }}
              style={{ height: '100%', background: `linear-gradient(90deg, ${cfg.color}, #6366f1)`, borderRadius: 99 }} />
          </div>
        </div>
      )}

      {/* Steps */}
      {steps.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 4 }}>
          {steps.map((step, i) => {
            const dotColor = step.status === 'done' ? '#059669' : step.status === 'active' ? cfg.color : step.status === 'error' ? '#dc2626' : '#cbd5e1';
            return (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10, color: step.status === 'active' ? cfg.color : '#94a3b8', fontWeight: step.status === 'active' ? 700 : 400 }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: dotColor, flexShrink: 0,
                  boxShadow: step.status === 'active' ? `0 0 6px ${cfg.color}` : 'none' }} />
                {step.label}
                {i < steps.length - 1 && <span style={{ color: '#e2e8f0', margin: '0 2px' }}>›</span>}
              </div>
            );
          })}
        </div>
      )}

      {/* Logs toggle */}
      {logs.length > 0 && (
        <>
          <button onClick={() => setShowLogs(l => !l)} style={{ fontSize: 10, color: '#94a3b8', background: 'none', border: 'none', cursor: 'pointer', padding: 0, display: 'flex', alignItems: 'center', gap: 3 }}>
            {showLogs ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
            {showLogs ? 'Hide logs' : `View logs (${logs.length})`}
          </button>
          <AnimatePresence>
            {showLogs && (
              <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}
                style={{ overflow: 'hidden' }}>
                <div style={{ marginTop: 6, maxHeight: 120, overflowY: 'auto', background: '#0f172a', borderRadius: 6, padding: '8px 10px' }}>
                  {logs.map((log, i) => <p key={i} style={{ fontSize: 10, fontFamily: 'monospace', color: '#94a3b8', margin: '1px 0', lineHeight: 1.5 }}>{log}</p>)}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </>)
      }
    </motion.div>
  );
}

/* ─── Main Widget ────────────────────────────────────── */
export default function GlobalJobTracker() {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const allJobs = useSelector(selectAllJobs);
  const activeJobs = useSelector(selectActiveJobs);
  const [minimized, setMinimized] = useState(false);

  const visibleJobs = Object.values(allJobs).filter(j => j.status !== 'idle');
  if (visibleJobs.length === 0) return <ToastLayer />;

  const runningCount = activeJobs.length;

  return (
    <>
      <ToastLayer />
      <AnimatePresence>
        <motion.div initial={{ opacity: 0, y: 30, scale: 0.95 }} animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ type: 'spring', stiffness: 300, damping: 28 }}
          style={{ position: 'fixed', bottom: 80, right: 20, zIndex: 10000, width: minimized ? 'auto' : 380,
            borderRadius: minimized ? 999 : 16, ...glass, overflow: 'hidden' }}>

          {/* Minimized chip */}
          {minimized ? (
            <button onClick={() => setMinimized(false)} style={{ display: 'flex', alignItems: 'center', gap: 8,
              padding: '10px 18px', background: 'none', border: 'none', cursor: 'pointer' }}>
              {runningCount > 0 && <Loader2 size={14} color="#2563eb" className="animate-spin" />}
              {runningCount === 0 && <CheckCircle2 size={14} color="#059669" />}
              <span style={{ fontSize: 12, fontWeight: 700, color: '#0f172a', whiteSpace: 'nowrap' }}>
                {runningCount > 0 ? `${runningCount} task${runningCount > 1 ? 's' : ''} running` : `${visibleJobs.length} completed`}
              </span>
              <Maximize2 size={12} color="#94a3b8" />
            </button>
          ) : (
            <>
              {/* Header */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px',
                borderBottom: '1px solid rgba(0,0,0,0.06)',
                background: runningCount > 0 ? 'linear-gradient(135deg, rgba(37,99,235,0.08), rgba(99,102,241,0.05))' : 'rgba(5,150,105,0.05)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  {runningCount > 0 ? <Loader2 size={15} color="#2563eb" className="animate-spin" /> : <Activity size={15} color="#059669" />}
                  <span style={{ fontSize: 13, fontWeight: 700, color: '#0f172a' }}>
                    {runningCount > 0 ? 'Background Processing' : 'Tasks Complete'}
                  </span>
                  {runningCount > 0 && <span style={{ fontSize: 9, fontWeight: 700, padding: '2px 8px', borderRadius: 999,
                    background: '#eff6ff', color: '#2563eb', border: '1px solid #bfdbfe' }}>
                    {runningCount} ACTIVE
                  </span>}
                </div>
                <div style={{ display: 'flex', gap: 4 }}>
                  <button onClick={() => setMinimized(true)} style={{ width: 26, height: 26, borderRadius: 6,
                    border: '1px solid #e2e8f0', background: '#fff', cursor: 'pointer',
                    display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Minimize2 size={12} color="#64748b" />
                  </button>
                </div>
              </div>

              {/* Job list */}
              <div style={{ maxHeight: 420, overflowY: 'auto' }}>
                <AnimatePresence>
                  {visibleJobs.map(job => (
                    <JobCard key={job.id} job={job}
                      onDismiss={() => dispatch(dismissJob({ type: job.type }))}
                      onNav={() => navigate(JOB_ROUTES[job.type])} />
                  ))}
                </AnimatePresence>
              </div>
            </>
          )}
        </motion.div>
      </AnimatePresence>
    </>
  );
}
