import { useEffect } from 'react';
import { colors, radius, shadow, touchTargets, typography } from '../../theme';

export interface ConfirmDialogProps {
  /** Full "¿Nueve, cero: 90 GAL de Aceite Vegetal Premier 5L?" style text from the backend. */
  displayText: string;
  articleName: string;
  quantity: number;
  unit: string;
  onConfirm: () => void;
  onCorrect: () => void;
}

/**
 * CLAUDE.md §4: shows the full article name, quantity AND unit — never
 * truncated. Touch targets >= 48px. Enter confirms, Escape asks to correct.
 */
export function ConfirmDialog({
  displayText,
  articleName,
  quantity,
  unit,
  onConfirm,
  onCorrect,
}: ConfirmDialogProps) {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        onConfirm();
      } else if (event.key === 'Escape') {
        event.preventDefault();
        onCorrect();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onConfirm, onCorrect]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Confirmar conteo"
      style={{
        background: colors.ui.background,
        border: `1px solid ${colors.ui.border}`,
        borderRadius: radius.medium,
        boxShadow: shadow.high,
        padding: 24,
        width: '100%',
        maxWidth: 480,
        boxSizing: 'border-box',
        fontFamily: typography.fontFamily,
      }}
    >
      <p
        style={{
          fontSize: typography.sizes.large,
          color: colors.ui.textPrimary,
          whiteSpace: 'normal',
          wordBreak: 'break-word',
        }}
      >
        {displayText}
      </p>

      <p
        style={{
          fontSize: typography.sizes.quantity,
          fontWeight: 700,
          color: colors.ui.textPrimary,
        }}
      >
        {quantity} {unit} — {articleName}
      </p>

      <div style={{ display: 'flex', gap: 12, marginTop: 16 }}>
        <button
          type="button"
          onClick={onConfirm}
          style={{
            minWidth: touchTargets.minimum,
            minHeight: touchTargets.minimum,
            background: colors.ui.success,
            color: '#ffffff',
            border: 'none',
            borderRadius: radius.small,
            fontSize: typography.sizes.base,
            fontWeight: 600,
            flex: 1,
            cursor: 'pointer',
          }}
        >
          Confirmar
        </button>
        <button
          type="button"
          onClick={onCorrect}
          style={{
            minWidth: touchTargets.minimum,
            minHeight: touchTargets.minimum,
            background: colors.traffic.red,
            color: '#ffffff',
            border: 'none',
            borderRadius: radius.small,
            fontSize: typography.sizes.base,
            fontWeight: 600,
            flex: 1,
            cursor: 'pointer',
          }}
        >
          Corregir
        </button>
      </div>
    </div>
  );
}
