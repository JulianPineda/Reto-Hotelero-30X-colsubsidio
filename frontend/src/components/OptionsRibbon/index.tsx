import type { ReactNode } from 'react';
import { colors, radius, shadow, touchTargets, typography } from '../../theme';

export interface RibbonAction {
  key: string;
  label: string;
  icon: ReactNode;
  onClick: () => void;
  disabled?: boolean;
  /** 'primary' (brand yellow, CLAUDE.md §2 "botón principal") for the
   * screen's one true call-to-action; 'secondary' (outlined) for nav. */
  variant?: 'primary' | 'secondary';
}

export interface OptionsRibbonProps {
  title?: string;
  subtitle?: string;
  /** Unauthenticated landing screen: a plain welcome line, no action
   * buttons at all — mutually exclusive with `actions`. */
  greeting?: string;
  actions?: RibbonAction[];
}

const actionButtonStyle = (variant: 'primary' | 'secondary', disabled: boolean) => ({
  minHeight: touchTargets.minimum,
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  padding: '0 16px',
  border: variant === 'primary' ? 'none' : `1px solid ${colors.ui.border}`,
  borderRadius: radius.small,
  background: disabled ? colors.neutral.grafito40 : variant === 'primary' ? colors.primary.yellow : colors.ui.background,
  color: disabled ? '#ffffff' : variant === 'primary' ? colors.ui.textPrimary : colors.primary.blue,
  fontFamily: typography.fontFamily,
  fontSize: typography.sizes.base,
  fontWeight: variant === 'primary' ? 700 : 600,
  cursor: disabled ? 'not-allowed' : 'pointer',
  whiteSpace: 'nowrap' as const,
});

/**
 * The "cinta de opciones" — adapts per screen/session per the ribbon spec:
 * a plain greeting on the unauthenticated landing screen, or a row of
 * icon+label actions elsewhere (Inicio/Retroceder/Cerrar sesión on the
 * selection screens; Finalizar inventario/Exportar on ingreso de
 * productos, etc.) — each screen decides its own `actions` list, this
 * component only renders whatever it's given. Sticky right below
 * `BrandRibbon` so the two form one continuous fixed nav strip on scroll.
 */
export function OptionsRibbon({ title, subtitle, greeting, actions }: OptionsRibbonProps) {
  if (greeting) {
    return (
      <div
        style={{
          position: 'sticky',
          top: 46,
          zIndex: 100,
          background: colors.ui.background,
          borderBottom: `1px solid ${colors.ui.border}`,
          padding: '14px 24px',
          textAlign: 'center',
          boxShadow: shadow.low,
        }}
      >
        <p style={{ margin: 0, color: colors.ui.textSecondary, fontSize: typography.sizes.base }}>{greeting}</p>
      </div>
    );
  }

  return (
    <div
      style={{
        position: 'sticky',
        top: 46,
        zIndex: 100,
        background: colors.ui.background,
        borderBottom: `1px solid ${colors.ui.border}`,
        padding: '12px 24px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 16,
        flexWrap: 'wrap',
        boxShadow: shadow.low,
      }}
    >
      <div style={{ minWidth: 0 }}>
        {title && (
          <h1 style={{ color: colors.primary.blue, fontSize: '1.15rem', margin: 0, wordBreak: 'break-word' }}>
            {title}
          </h1>
        )}
        {subtitle && (
          <p style={{ color: colors.ui.textSecondary, fontSize: typography.sizes.label, margin: 0 }}>{subtitle}</p>
        )}
      </div>

      {actions && actions.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          {actions.map((action) => (
            <button
              key={action.key}
              type="button"
              onClick={action.onClick}
              disabled={action.disabled}
              style={actionButtonStyle(action.variant ?? 'secondary', !!action.disabled)}
            >
              {action.icon}
              {action.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
