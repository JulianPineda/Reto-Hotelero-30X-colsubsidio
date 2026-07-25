import { useCallback, useEffect, useState } from 'react';
import { listNeedsReviewItems, type OfflineCountItem } from '../../services/offlineQueue';
import {
  callHomologate,
  resolveNeedsReviewItem,
  type HomologateAlternative,
  type HomologateResponse,
  type SyncContext,
} from '../../services/offlineSync';
import { colors, touchTargets, typography } from '../../theme';

export interface OfflineReviewListProps {
  sessionId: string;
  ctx: SyncContext;
  /** Bump after a sync pass or a resolution to force a re-fetch. */
  refreshKey: number;
}

/**
 * Surfaces offline items `offlineSync.ts` couldn't auto-resolve — either
 * ambiguous homologation (CLAUDE.md §3.2, 0.50-0.79 score band, requires an
 * explicit operator pick) or a perishable item missing its expiry date
 * (CLAUDE.md §3.6). Nothing here is guessed automatically.
 */
export function OfflineReviewList({ sessionId, ctx, refreshKey }: OfflineReviewListProps) {
  const [items, setItems] = useState<OfflineCountItem[]>([]);
  const [homologations, setHomologations] = useState<Record<number, HomologateResponse>>({});
  const [expiryDrafts, setExpiryDrafts] = useState<Record<number, string>>({});

  const reload = useCallback(async () => {
    const needsReview = await listNeedsReviewItems(sessionId);
    setItems(needsReview);

    const entries = await Promise.all(
      needsReview.map(async (item) => [item.id as number, await callHomologate(ctx, item.article, item.unit)] as const),
    );
    setHomologations(Object.fromEntries(entries));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, ctx.apiBaseUrl, ctx.authToken, ctx.warehouseId, ctx.shift]);

  useEffect(() => {
    reload();
  }, [reload, refreshKey]);

  const handlePickAlternative = async (item: OfflineCountItem, alt: HomologateAlternative) => {
    await resolveNeedsReviewItem(item, { oracleCode: alt.oracle_code, name: alt.name, isPerishable: null }, ctx);
    await reload();
  };

  const handleSaveWithoutMatch = async (item: OfflineCountItem) => {
    await resolveNeedsReviewItem(item, { oracleCode: null, name: null, isPerishable: null }, ctx);
    await reload();
  };

  const handleConfirmExpiry = async (item: OfflineCountItem, homologation: HomologateResponse) => {
    const draft = expiryDrafts[item.id as number];
    if (!draft) return;
    await resolveNeedsReviewItem(
      item,
      { oracleCode: homologation.oracle_code, name: homologation.name, isPerishable: homologation.is_perishable },
      ctx,
      draft,
    );
    await reload();
  };

  if (items.length === 0) return null;

  return (
    <div style={{ marginTop: 32, fontFamily: typography.fontFamily }}>
      <h2 style={{ color: colors.primary.blue }}>Ítems offline que requieren tu revisión ({items.length})</h2>
      <ul style={{ listStyle: 'none', padding: 0 }}>
        {items.map((item) => {
          const homologation = homologations[item.id as number];
          return (
            <li
              key={item.id}
              style={{
                border: `1px solid ${colors.ui.border}`,
                borderRadius: 8,
                padding: 16,
                marginBottom: 12,
              }}
            >
              <p style={{ fontWeight: 600, color: colors.ui.textPrimary }}>
                {item.quantity} {item.unit} — &quot;{item.article}&quot;
              </p>

              {!homologation && <p style={{ color: colors.ui.textSecondary }}>Buscando en el catálogo…</p>}

              {homologation?.requires_operator_selection && (
                <>
                  <p style={{ color: colors.ui.textSecondary }}>Selecciona el artículo correcto:</p>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {homologation.alternatives.map((alt) => (
                      <button
                        key={alt.oracle_code}
                        type="button"
                        onClick={() => handlePickAlternative(item, alt)}
                        style={{
                          minHeight: touchTargets.minimum,
                          textAlign: 'left',
                          padding: '8px 12px',
                          border: `1px solid ${colors.ui.border}`,
                          borderRadius: 8,
                          background: colors.ui.surface,
                          cursor: 'pointer',
                        }}
                      >
                        {alt.name} ({Math.round(alt.score * 100)}%)
                      </button>
                    ))}
                    <button
                      type="button"
                      onClick={() => handleSaveWithoutMatch(item)}
                      style={{
                        minHeight: touchTargets.minimum,
                        background: colors.neutral.grafito40,
                        color: '#ffffff',
                        border: 'none',
                        borderRadius: 8,
                        cursor: 'pointer',
                      }}
                    >
                      Guardar sin homologar
                    </button>
                  </div>
                </>
              )}

              {homologation && !homologation.requires_operator_selection && homologation.is_perishable && !item.expiryDate && (
                <>
                  <p style={{ color: colors.ui.textSecondary }}>
                    &quot;{homologation.name}&quot; es perecedero — indica su fecha de vencimiento:
                  </p>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <input
                      type="date"
                      aria-label="Fecha de vencimiento"
                      value={expiryDrafts[item.id as number] ?? ''}
                      onChange={(event) =>
                        setExpiryDrafts((prev) => ({ ...prev, [item.id as number]: event.target.value }))
                      }
                      style={{ minHeight: touchTargets.minimum, flex: 1 }}
                    />
                    <button
                      type="button"
                      onClick={() => handleConfirmExpiry(item, homologation)}
                      disabled={!expiryDrafts[item.id as number]}
                      style={{
                        minHeight: touchTargets.minimum,
                        background: colors.ui.success,
                        color: '#ffffff',
                        border: 'none',
                        borderRadius: 8,
                        padding: '0 16px',
                        cursor: 'pointer',
                      }}
                    >
                      Confirmar
                    </button>
                  </div>
                </>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
