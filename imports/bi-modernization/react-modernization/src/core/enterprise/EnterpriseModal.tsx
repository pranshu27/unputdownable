/**
 * EnterpriseModal.tsx
 * Professional enterprise modal with standard sizing, header, body, footer.
 */
import React, { useEffect, useRef } from 'react';
import { X } from 'lucide-react';

type ModalSize = 'sm' | 'md' | 'lg' | 'xl' | 'full';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  subtitle?: string;
  icon?: React.ReactNode;
  size?: ModalSize;
  children: React.ReactNode;
  footer?: React.ReactNode;
  hideClose?: boolean;
  noPadding?: boolean;
}

const sizes: Record<ModalSize, string> = {
  sm: '400px', md: '520px', lg: '680px', xl: '860px', full: '95vw',
};

export default function EnterpriseModal({
  isOpen, onClose, title, subtitle, icon, size = 'md',
  children, footer, hideClose, noPadding,
}: Props) {
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    const handleKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handleKey);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handleKey);
      document.body.style.overflow = '';
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      ref={overlayRef}
      onClick={e => { if (e.target === overlayRef.current) onClose(); }}
      style={{
        position: 'fixed', inset: 0, zIndex: 'var(--z-modal)' as any,
        background: 'var(--surface-overlay)', display: 'flex',
        alignItems: 'center', justifyContent: 'center',
        padding: 'var(--space-4)',
      }}
    >
      <div style={{
        width: '100%', maxWidth: sizes[size], maxHeight: '85vh',
        background: 'var(--surface-card)', border: '1px solid var(--border-secondary)',
        borderRadius: 'var(--radius-xl)', boxShadow: 'var(--shadow-xl)',
        display: 'flex', flexDirection: 'column', overflow: 'hidden',
      }}>
        {/* Header */}
        {title && (
          <div style={{
            padding: '16px 20px', borderBottom: '1px solid var(--border-subtle)',
            display: 'flex', alignItems: 'center', gap: 'var(--space-3)',
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
              <h2 style={{
                fontSize: 'var(--text-md)', fontWeight: 600,
                color: 'var(--text-primary)', margin: 0,
              }}>
                {title}
              </h2>
              {subtitle && (
                <p style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', margin: '2px 0 0' }}>
                  {subtitle}
                </p>
              )}
            </div>
            {!hideClose && (
              <button onClick={onClose} className="ent-btn ent-btn-ghost ent-btn-xs" style={{ width: 28, height: 28, padding: 0 }}>
                <X size={14} />
              </button>
            )}
          </div>
        )}

        {/* Body */}
        <div style={{ flex: 1, overflow: 'auto', padding: noPadding ? 0 : '16px 20px' }}>
          {children}
        </div>

        {/* Footer */}
        {footer && (
          <div style={{
            padding: '12px 20px', borderTop: '1px solid var(--border-subtle)',
            display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
            gap: 'var(--space-2)',
          }}>
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
