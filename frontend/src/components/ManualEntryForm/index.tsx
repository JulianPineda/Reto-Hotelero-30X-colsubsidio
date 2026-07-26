import { useState } from 'react';
import { colors, radius, touchTargets, typography } from '../../theme';

export interface ManualEntryValues {
  article: string;
  quantity: number;
  unit: string;
  /** Only set if the operator already knows this item is perishable —
   * offline capture has no catalog lookup to confirm `is_perishable`. */
  expiryDate: string | null;
}

export interface ManualEntryFormProps {
  onSubmit: (values: ManualEntryValues) => void;
}

const inputStyle = {
  minHeight: touchTargets.minimum,
  fontSize: typography.sizes.base,
  fontFamily: typography.fontFamily,
  padding: '8px 12px',
  border: `1px solid ${colors.ui.border}`,
  borderRadius: radius.small,
  width: '100%',
  boxSizing: 'border-box' as const,
};

const labelStyle = {
  display: 'block',
  fontSize: typography.sizes.label,
  color: colors.ui.textSecondary,
  marginBottom: 4,
};

/**
 * CLAUDE.md §3.8 — voice is disabled offline; this keyboard/touch form is
 * the manual fallback. Shown by `CountSession` in place of `VoiceButton`
 * while `isOffline`. Entries go to `offlineQueue.ts` (IndexedDB via Dexie)
 * and only reach Catalog Agent + Auditor Agent once reconnected
 * (`offlineSync.ts`) — never persisted directly from here.
 */
export function ManualEntryForm({ onSubmit }: ManualEntryFormProps) {
  const [article, setArticle] = useState('');
  const [quantity, setQuantity] = useState('');
  const [unit, setUnit] = useState('');
  const [expiryDate, setExpiryDate] = useState('');

  const canSubmit = article.trim().length > 0 && quantity.trim().length > 0 && unit.trim().length > 0;

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;

    onSubmit({
      article: article.trim(),
      quantity: Number(quantity),
      unit: unit.trim(),
      expiryDate: expiryDate.trim().length > 0 ? expiryDate.trim() : null,
    });

    setArticle('');
    setQuantity('');
    setUnit('');
    setExpiryDate('');
  };

  return (
    <form
      onSubmit={handleSubmit}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
        maxWidth: 420,
        fontFamily: typography.fontFamily,
      }}
    >
      <div>
        <label htmlFor="manual-article" style={labelStyle}>
          Artículo
        </label>
        <input
          id="manual-article"
          type="text"
          value={article}
          onChange={(event) => setArticle(event.target.value)}
          maxLength={300}
          style={inputStyle}
        />
      </div>

      <div style={{ display: 'flex', gap: 12 }}>
        <div style={{ flex: 1 }}>
          <label htmlFor="manual-quantity" style={labelStyle}>
            Cantidad
          </label>
          <input
            id="manual-quantity"
            type="number"
            inputMode="decimal"
            step="any"
            min="0"
            value={quantity}
            onChange={(event) => setQuantity(event.target.value)}
            style={inputStyle}
          />
        </div>
        <div style={{ flex: 1 }}>
          <label htmlFor="manual-unit" style={labelStyle}>
            Unidad
          </label>
          <input
            id="manual-unit"
            type="text"
            value={unit}
            onChange={(event) => setUnit(event.target.value)}
            maxLength={20}
            style={inputStyle}
          />
        </div>
      </div>

      <div>
        <label htmlFor="manual-expiry" style={labelStyle}>
          Fecha de vencimiento (solo si aplica)
        </label>
        <input
          id="manual-expiry"
          type="date"
          value={expiryDate}
          onChange={(event) => setExpiryDate(event.target.value)}
          style={inputStyle}
        />
      </div>

      <button
        type="submit"
        disabled={!canSubmit}
        style={{
          minHeight: touchTargets.minimum,
          background: canSubmit ? colors.primary.yellow : colors.neutral.grafito40,
          color: canSubmit ? colors.ui.textPrimary : '#ffffff',
          border: 'none',
          borderRadius: radius.small,
          fontSize: typography.sizes.base,
          fontWeight: 700,
          cursor: canSubmit ? 'pointer' : 'not-allowed',
        }}
      >
        Guardar ítem (offline)
      </button>
    </form>
  );
}
