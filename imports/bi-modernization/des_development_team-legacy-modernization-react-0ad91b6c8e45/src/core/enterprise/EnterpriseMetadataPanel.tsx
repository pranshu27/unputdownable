/**
 * EnterpriseMetadataPanel.tsx
 * Right-side detail panel showing properties, metadata, and relationships.
 */
import React from 'react';
import { X, ExternalLink } from 'lucide-react';

interface MetadataField {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
  copyable?: boolean;
}

interface MetadataSection {
  title: string;
  fields: MetadataField[];
  collapsible?: boolean;
}

interface Props {
  title: string;
  subtitle?: string;
  icon?: React.ReactNode;
  badge?: React.ReactNode;
  sections: MetadataSection[];
  onClose?: () => void;
  actions?: React.ReactNode;
  footer?: React.ReactNode;
  width?: number;
}

export default function EnterpriseMetadataPanel({
  title, subtitle, icon, badge, sections, onClose, actions, footer, width = 320,
}: Props) {
  return (
    <div style={{
      width, height: '100%', display: 'flex', flexDirection: 'column',
      background: 'var(--surface-card)', borderLeft: '1px solid var(--border-secondary)',
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        padding: '12px 16px', borderBottom: '1px solid var(--border-subtle)',
        display: 'flex', alignItems: 'flex-start', gap: 'var(--space-3)',
      }}>
        {icon && (
          <div style={{
            width: 32, height: 32, borderRadius: 'var(--radius-md)',
            background: 'var(--surface-secondary)', display: 'flex',
            alignItems: 'center', justifyContent: 'center', flexShrink: 0,
            color: 'var(--text-tertiary)',
          }}>
            {icon}
          </div>
        )}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            <span style={{
              fontSize: 'var(--text-sm)', fontWeight: 600,
              color: 'var(--text-primary)', overflow: 'hidden',
              textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {title}
            </span>
            {badge}
          </div>
          {subtitle && (
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', display: 'block', marginTop: 2 }}>
              {subtitle}
            </span>
          )}
        </div>
        <div style={{ display: 'flex', gap: 'var(--space-1)', flexShrink: 0 }}>
          {actions}
          {onClose && (
            <button
              onClick={onClose}
              className="ent-btn ent-btn-ghost ent-btn-xs"
              style={{ width: 24, height: 24, padding: 0 }}
            >
              <X size={12} />
            </button>
          )}
        </div>
      </div>

      {/* Sections */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        {sections.map((section, si) => (
          <div key={si} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
            <div style={{
              padding: '8px 16px', fontSize: 'var(--text-xs)', fontWeight: 600,
              color: 'var(--text-tertiary)', textTransform: 'uppercase',
              letterSpacing: 'var(--tracking-wide)', background: 'var(--surface-secondary)',
            }}>
              {section.title}
            </div>
            <div style={{ padding: '8px 16px' }}>
              {section.fields.map((field, fi) => (
                <div key={fi} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
                  padding: '5px 0', gap: 'var(--space-3)',
                  borderBottom: fi < section.fields.length - 1 ? '1px solid var(--border-subtle)' : 'none',
                }}>
                  <span style={{
                    fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)',
                    fontWeight: 500, flexShrink: 0, minWidth: 80,
                  }}>
                    {field.label}
                  </span>
                  <span style={{
                    fontSize: 'var(--text-xs)', color: 'var(--text-primary)',
                    fontWeight: 500, textAlign: 'right', wordBreak: 'break-word',
                    fontFamily: field.mono ? 'var(--font-mono)' : 'inherit',
                  }}>
                    {field.value || '—'}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Footer */}
      {footer && (
        <div style={{
          padding: '8px 16px', borderTop: '1px solid var(--border-subtle)',
          display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 'var(--space-2)',
        }}>
          {footer}
        </div>
      )}
    </div>
  );
}
