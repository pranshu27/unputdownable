/**
 * WorkspaceExplorer.tsx
 * Left sidebar: clean, simple, flat JNJ modernization workspace navigation.
 * Only contains: Overview, Datasources, Relationships, Consolidated, CodeGen.
 */
import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, Database, GitBranch, Layers, Code2, ChevronLeft, ChevronRight, Network, History, ShieldCheck
} from 'lucide-react';

interface NavItem {
  id: string;
  label: string;
  icon: React.ReactNode;
  path: string;
}

const navItems: NavItem[] = [
  { id: 'overview', label: 'Overview', icon: <LayoutDashboard size={16} />, path: '/overview' },
  // { id: 'datasources', label: 'Datasources', icon: <Database size={16} />, path: '/datasources' },
  { id: 'relationships', label: 'Relationships', icon: <GitBranch size={16} />, path: '/relationships' },
  { id: 'lineage', label: 'Lineage', icon: <Network size={16} />, path: '/lineage' },
  { id: 'validations', label: 'Validation', icon: <ShieldCheck size={16} />, path: '/validation-dashboard?tab=reverse' },
  // { id: 'consolidated', label: 'Consolidated', icon: <Layers size={16} />, path: '/consolidated-model' },
  { id: 'codegen', label: 'CodeGen', icon: <Code2 size={16} />, path: '/code-gen' },
];

interface Props {
  model: any;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export default function WorkspaceExplorer({ model, collapsed, onToggleCollapse }: Props) {
  const location = useLocation();
  const navigate = useNavigate();

  if (collapsed) {
    return (
      <div style={{
        width: 'var(--sidebar-collapsed)', display: 'flex', flexDirection: 'column',
        borderRight: '1px solid var(--border-primary)', background: 'var(--surface-card)',
        flexShrink: 0, overflow: 'hidden', height: '100%',
      }}>
        <button
          onClick={onToggleCollapse}
          style={{
            width: '100%', height: 44, display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)',
            borderBottom: '1px solid var(--border-subtle)',
          }}
        >
          <ChevronRight size={14} />
        </button>
        <div style={{ flex: 1, overflow: 'auto', padding: '12px 0', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {navItems.map(item => {
            const isActive = location.pathname === item.path || (item.id === 'validations' && (location.pathname.startsWith('/validation-dashboard') || location.pathname.startsWith('/validations')));
            return (
              <button
                key={item.id}
                onClick={() => navigate(item.path)}
                title={item.label}
                style={{
                  width: '100%', height: 40, display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background: isActive ? 'var(--jnj-red-light)' : 'transparent',
                  color: isActive ? 'var(--jnj-red)' : 'var(--text-secondary)',
                  border: 'none', cursor: 'pointer',
                  borderLeft: isActive ? '3px solid var(--jnj-red)' : '3px solid transparent',
                  transition: 'all var(--transition-fast)',
                }}
              >
                {item.icon}
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <div style={{
      width: 'var(--sidebar-width)', display: 'flex', flexDirection: 'column',
      borderRight: '1px solid var(--border-primary)', background: 'var(--surface-card)',
      flexShrink: 0, overflow: 'hidden', height: '100%',
    }}>
      {/* Header with toggle */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '12px 16px', borderBottom: '1px solid var(--border-subtle)',
      }}>
        <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          Navigation
        </span>
        <button
          onClick={onToggleCollapse}
          style={{
            width: 24, height: 24, display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)',
            borderRadius: 'var(--radius-sm)',
          }}
        >
          <ChevronLeft size={14} />
        </button>
      </div>

      {/* Flat List */}
      <div style={{ flex: 1, overflow: 'auto', padding: '16px 8px', display: 'flex', flexDirection: 'column', gap: 4 }}>
        {navItems.map(item => {
          const isActive = location.pathname === item.path || (item.id === 'validations' && (location.pathname.startsWith('/validation-dashboard') || location.pathname.startsWith('/validations')));
          return (
            <button
              key={item.id}
              onClick={() => navigate(item.path)}
              style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '10px 14px',
                background: isActive ? 'var(--jnj-red-light)' : 'transparent',
                color: isActive ? 'var(--jnj-red)' : 'var(--text-secondary)',
                border: 'none', cursor: 'pointer',
                borderRadius: 'var(--radius-md)',
                fontSize: '13px', fontWeight: isActive ? 600 : 500,
                textAlign: 'left',
                width: '100%',
                transition: 'all var(--transition-fast)',
              }}
              onMouseEnter={e => { if (!isActive) e.currentTarget.style.background = 'var(--surface-secondary)'; }}
              onMouseLeave={e => { if (!isActive) e.currentTarget.style.background = 'transparent'; }}
            >
              <span style={{ display: 'flex', alignItems: 'center', color: isActive ? 'var(--jnj-red)' : 'var(--text-tertiary)' }}>
                {item.icon}
              </span>
              {item.label}
            </button>
          );
        })}


      </div>
    </div>
  );
}
