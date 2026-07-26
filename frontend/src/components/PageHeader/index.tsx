import type { ReactNode } from 'react';
import { colors, gradients, logos, typography } from '../../theme';

export interface PageHeaderProps {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}

/**
 * Shared brand-blue header bar. Before this, Login, WarehouseSelect,
 * SessionSelect, CountSession and SupervisorDashboard each had their own
 * plain black-on-white <h1> with no shared visual anchor tying the
 * screens together as one branded app (visual polish pass — CLAUDE.md §2
 * colors, "no tan plano").
 */
export function PageHeader({ title, subtitle, actions }: PageHeaderProps) {
  return (
    <div
      style={{
        background: gradients.brandBlue,
        padding: '18px 24px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 16,
        flexWrap: 'wrap',
        boxShadow: '0 2px 12px rgba(0, 103, 177, 0.25)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
        <img src={logos.iconYellow} alt="" style={{ height: 34, flexShrink: 0 }} />
        <div style={{ minWidth: 0 }}>
          <h1
            style={{
              color: '#ffffff',
              fontSize: '1.25rem',
              fontFamily: typography.fontFamily,
              margin: 0,
              wordBreak: 'break-word',
            }}
          >
            {title}
          </h1>
          {subtitle && (
            <p style={{ color: 'rgba(255,255,255,0.85)', fontSize: typography.sizes.label, margin: 0 }}>
              {subtitle}
            </p>
          )}
        </div>
      </div>
      {actions && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>{actions}</div>
      )}
    </div>
  );
}

const onDarkButtonBase = {
  minHeight: 48,
  padding: '0 16px',
  background: 'rgba(255,255,255,0.14)',
  border: '1px solid rgba(255,255,255,0.5)',
  borderRadius: 8,
  color: '#ffffff',
  fontFamily: typography.fontFamily,
  fontSize: typography.sizes.base,
  fontWeight: 600,
  cursor: 'pointer',
  whiteSpace: 'nowrap' as const,
};

/** A "Cerrar sesión" button styled to sit on PageHeader's blue bar. */
export function HeaderLogoutButton({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} style={onDarkButtonBase}>
      Cerrar sesión
    </button>
  );
}

// Primary CTA on the blue header bar — CLAUDE.md §2 reserves yellow for
// "Botón principal / acentos", so the header's one true call-to-action
// (Exportar a Excel, Terminar inventario) uses it rather than blending
// into the bar with another blue.
export const headerPrimaryButtonStyle = (enabled: boolean) => ({
  minHeight: 48,
  padding: '0 20px',
  background: enabled ? colors.primary.yellow : 'rgba(255,255,255,0.25)',
  color: enabled ? colors.ui.textPrimary : 'rgba(255,255,255,0.7)',
  border: 'none',
  borderRadius: 8,
  fontWeight: 700,
  cursor: enabled ? 'pointer' : 'not-allowed',
  whiteSpace: 'nowrap' as const,
});
