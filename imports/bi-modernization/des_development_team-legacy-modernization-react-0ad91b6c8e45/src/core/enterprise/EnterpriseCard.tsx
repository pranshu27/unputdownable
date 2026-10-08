/**
 * EnterpriseCard.tsx
 * Standard enterprise card with header, body, footer, and action slots.
 */
import React from 'react';

interface EnterpriseCardProps {
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
  onClick?: () => void;
  interactive?: boolean;
}

interface CardHeaderProps {
  title?: string;
  subtitle?: string;
  icon?: React.ReactNode;
  actions?: React.ReactNode;
  badge?: React.ReactNode;
  children?: React.ReactNode;
  compact?: boolean;
}

interface CardBodyProps {
  children: React.ReactNode;
  noPadding?: boolean;
  className?: string;
}

export function EnterpriseCard({ children, className = '', style, onClick, interactive }: EnterpriseCardProps) {
  return (
    <div
      className={`ent-card ${interactive ? 'ent-card-interactive' : ''} ${className}`}
      style={{
        ...style,
        ...(interactive ? { cursor: 'pointer' } : {}),
      }}
      onClick={onClick}
    >
      {children}
    </div>
  );
}

export function CardHeader({ title, subtitle, icon, actions, badge, children, compact }: CardHeaderProps) {
  if (children) {
    return <div className="ent-card-header">{children}</div>;
  }
  return (
    <div className="ent-card-header" style={compact ? { padding: '8px 12px' } : undefined}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', minWidth: 0, flex: 1 }}>
        {icon && (
          <div style={{
            width: 28, height: 28, borderRadius: 'var(--radius-md)',
            background: 'var(--surface-secondary)', display: 'flex',
            alignItems: 'center', justifyContent: 'center', flexShrink: 0,
          }}>
            {icon}
          </div>
        )}
        <div style={{ minWidth: 0, flex: 1 }}>
          {title && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
              <span style={{
                fontSize: 'var(--text-sm)', fontWeight: 'var(--weight-semibold)' as any,
                color: 'var(--text-primary)', overflow: 'hidden',
                textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>
                {title}
              </span>
              {badge}
            </div>
          )}
          {subtitle && (
            <span style={{
              fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)',
              display: 'block', marginTop: 1,
            }}>
              {subtitle}
            </span>
          )}
        </div>
      </div>
      {actions && <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-1)', flexShrink: 0 }}>{actions}</div>}
    </div>
  );
}

export function CardBody({ children, noPadding, className = '' }: CardBodyProps) {
  return (
    <div className={`ent-card-body ${className}`} style={noPadding ? { padding: 0 } : undefined}>
      {children}
    </div>
  );
}

export function CardFooter({ children }: { children: React.ReactNode }) {
  return <div className="ent-card-footer">{children}</div>;
}

export default EnterpriseCard;
