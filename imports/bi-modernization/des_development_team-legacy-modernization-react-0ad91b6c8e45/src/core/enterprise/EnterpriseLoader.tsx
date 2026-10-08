/**
 * EnterpriseLoader.tsx
 * Enterprise loading states — skeleton, progress bar, spinner, and overlay.
 */
import React from 'react';

/* ── Skeleton ── */
export function Skeleton({ width = '100%', height = 14, radius = 6, style }: {
  width?: number | string; height?: number; radius?: number; style?: React.CSSProperties;
}) {
  return (
    <div className="ent-skeleton" style={{ width, height, borderRadius: radius, ...style }} />
  );
}

export function SkeletonText({ lines = 3, lastWidth = '60%' }: { lines?: number; lastWidth?: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} width={i === lines - 1 ? lastWidth : '100%'} height={12} />
      ))}
    </div>
  );
}

export function SkeletonTable({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div>
      <div style={{
        display: 'grid', gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: 12,
        padding: '10px 12px', background: 'var(--surface-secondary)',
        borderBottom: '1px solid var(--border-primary)',
      }}>
        {Array.from({ length: cols }).map((_, i) => (
          <Skeleton key={i} width={60 + Math.random() * 40} height={10} />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, ri) => (
        <div key={ri} style={{
          display: 'grid', gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: 12,
          padding: '10px 12px', borderBottom: '1px solid var(--border-subtle)',
        }}>
          {Array.from({ length: cols }).map((_, ci) => (
            <Skeleton key={ci} width={40 + Math.random() * 80} height={11} />
          ))}
        </div>
      ))}
    </div>
  );
}

/* ── Progress Bar ── */
export function ProgressBar({ value, label, color }: {
  value: number; label?: string; color?: string;
}) {
  return (
    <div>
      {label && (
        <div style={{
          display: 'flex', justifyContent: 'space-between', marginBottom: 4,
          fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)',
        }}>
          <span>{label}</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{Math.round(value)}%</span>
        </div>
      )}
      <div className="ent-progress">
        <div className="ent-progress-bar" style={{
          width: `${Math.min(100, Math.max(0, value))}%`,
          background: color || 'var(--jnj-red)',
        }} />
      </div>
    </div>
  );
}

/* ── Spinner ── */
export function Spinner({ size = 'md', color }: { size?: 'sm' | 'md' | 'lg'; color?: string }) {
  const cls = size === 'sm' ? 'ent-spinner ent-spinner-sm' : size === 'lg' ? 'ent-spinner ent-spinner-lg' : 'ent-spinner';
  return <div className={cls} style={color ? { borderTopColor: color } : undefined} />;
}

/* ── Full Card Loader ── */
export function CardLoader({ message, height = 200 }: { message?: string; height?: number }) {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', height, gap: 'var(--space-3)',
      color: 'var(--text-tertiary)',
    }}>
      <Spinner />
      {message && <span style={{ fontSize: 'var(--text-sm)' }}>{message}</span>}
    </div>
  );
}

/* ── Page Overlay Loader ── */
export function OverlayLoader({ message, show }: { message?: string; show: boolean }) {
  if (!show) return null;
  return (
    <div style={{
      position: 'absolute', inset: 0, zIndex: 50,
      background: 'rgba(var(--surface-bg), 0.85)',
      backdropFilter: 'blur(4px)',
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', gap: 'var(--space-3)',
    }}>
      <Spinner size="lg" />
      {message && (
        <span style={{
          fontSize: 'var(--text-sm)', fontWeight: 500,
          color: 'var(--text-secondary)',
        }}>
          {message}
        </span>
      )}
    </div>
  );
}

export default { Skeleton, SkeletonText, SkeletonTable, ProgressBar, Spinner, CardLoader, OverlayLoader };
