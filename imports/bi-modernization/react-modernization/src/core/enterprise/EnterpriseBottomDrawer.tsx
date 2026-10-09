/**
 * EnterpriseBottomDrawer.tsx
 * Resizable bottom drawer for logs, API progress, migration timeline.
 */
import React, { useState } from 'react';
import { ChevronUp, ChevronDown, X, Terminal, Activity, Clock } from 'lucide-react';

interface Tab {
  id: string;
  label: string;
  icon?: React.ReactNode;
  content: React.ReactNode;
  badge?: number;
}

interface Props {
  tabs: Tab[];
  defaultOpen?: boolean;
}

export default function EnterpriseBottomDrawer({ tabs, defaultOpen = false }: Props) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const [activeTab, setActiveTab] = useState(tabs[0]?.id || '');

  const activeContent = tabs.find(t => t.id === activeTab)?.content;

  return (
    <div style={{
      borderTop: '1px solid var(--border-secondary)',
      background: 'var(--surface-card)',
      display: 'flex', flexDirection: 'column',
      transition: 'height var(--transition-slow)',
      height: isOpen ? 'var(--bottom-drawer-expanded)' : 'var(--bottom-drawer-collapsed)',
      overflow: 'hidden', flexShrink: 0,
    }}>
      {/* Tab bar */}
      <div style={{
        display: 'flex', alignItems: 'center', height: 36,
        borderBottom: isOpen ? '1px solid var(--border-subtle)' : 'none',
        padding: '0 8px', gap: 2, flexShrink: 0,
      }}>
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => { setActiveTab(tab.id); if (!isOpen) setIsOpen(true); }}
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '4px 10px', height: 28,
              background: activeTab === tab.id && isOpen ? 'var(--surface-secondary)' : 'transparent',
              border: 'none', borderRadius: 'var(--radius-sm)',
              cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 500,
              color: activeTab === tab.id && isOpen ? 'var(--text-primary)' : 'var(--text-tertiary)',
              transition: 'all var(--transition-fast)',
            }}
          >
            {tab.icon}
            {tab.label}
            {tab.badge != null && tab.badge > 0 && (
              <span style={{
                fontSize: 9, fontWeight: 700, padding: '1px 5px',
                borderRadius: 'var(--radius-full)',
                background: 'var(--jnj-red)', color: '#fff',
                minWidth: 16, textAlign: 'center',
              }}>
                {tab.badge}
              </span>
            )}
          </button>
        ))}

        <div style={{ flex: 1 }} />

        <button
          onClick={() => setIsOpen(!isOpen)}
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            width: 24, height: 24, background: 'none', border: 'none',
            cursor: 'pointer', color: 'var(--text-tertiary)',
            borderRadius: 'var(--radius-sm)',
          }}
        >
          {isOpen ? <ChevronDown size={12} /> : <ChevronUp size={12} />}
        </button>
      </div>

      {/* Content */}
      {isOpen && (
        <div style={{ flex: 1, overflow: 'auto', fontSize: 'var(--text-xs)' }}>
          {activeContent}
        </div>
      )}
    </div>
  );
}

/* ── Pre-built Log Panel ── */
export function LogPanel({ logs }: { logs: { time: string; message: string; level?: 'info' | 'warn' | 'error' }[] }) {
  const levelColors = { info: 'var(--text-tertiary)', warn: 'var(--color-warning)', error: 'var(--color-error)' };
  return (
    <div style={{ padding: '4px 0', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
      {logs.length === 0 ? (
        <div style={{ padding: 'var(--space-4)', color: 'var(--text-tertiary)', textAlign: 'center' }}>
          No logs yet
        </div>
      ) : logs.map((log, i) => (
        <div key={i} style={{
          display: 'flex', gap: 'var(--space-3)', padding: '2px 12px',
          borderBottom: '1px solid var(--border-subtle)',
        }}>
          <span style={{ color: 'var(--text-tertiary)', flexShrink: 0, minWidth: 65 }}>{log.time}</span>
          <span style={{ color: levelColors[log.level || 'info'] }}>{log.message}</span>
        </div>
      ))}
    </div>
  );
}
