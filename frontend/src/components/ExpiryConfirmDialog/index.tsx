import { useEffect } from 'react';
import { colors, touchTargets, typography } from '../../theme';

export interface ExpiryConfirmDialogProps {
  /** e.g. "¿Confirmas fecha de vencimiento: quince de agosto de dos mil veintiséis?" */
  displayText: string;
  onConfirm: () => void;
  onCorrect: () => void;
}

/**
 * Confirm/correct step for the perishables expiry-date re-ask flow
 * (CLAUDE.md §3.6, T-017) — mirrors ConfirmDialog's interaction pattern
 * (Enter confirms, Escape asks to redictate) but has no quantity/unit to
 * show, only the parsed spoken date.
 */
export function ExpiryConfirmDialog({ displayText, onConfirm, onCorrect }: ExpiryConfirmDialogProps) {
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
      aria-label="Confirmar fecha de vencimiento"
      style={{
        background: colors.ui.background,
        border: `1px solid ${colors.ui.border}`,
        borderRadius: 12,
        padding: 24,
        maxWidth: 480,
        fontFamily: typography.fontFamily,
      }}
    >
      <p style={{ fontSize: typography.sizes.large, color: colors.ui.textPrimary }}>{displayText}</p>

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
            borderRadius: 8,
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
            borderRadius: 8,
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
