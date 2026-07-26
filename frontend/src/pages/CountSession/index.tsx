import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BrandRibbon } from '../../components/BrandRibbon';
import { ConfirmDialog } from '../../components/ConfirmDialog/ConfirmDialog';
import { ExpiryConfirmDialog } from '../../components/ExpiryConfirmDialog';
import { CheckCircleIcon, ExportIcon, HomeIcon } from '../../components/icons';
import { ManualEntryForm } from '../../components/ManualEntryForm';
import { OfflineBanner } from '../../components/OfflineBanner';
import { OfflineReviewList } from '../../components/OfflineReviewList';
import { OptionsRibbon, type RibbonAction } from '../../components/OptionsRibbon';
import { TrafficLight } from '../../components/TrafficLight';
import { VoiceButton, type VoiceButtonPhase } from '../../components/VoiceButton';
import { useVoiceSession } from '../../hooks/useVoiceSession';
import { enqueueOfflineItem } from '../../services/offlineQueue';
import {
  PersistCountItemError,
  submitManualFallbackItem,
  syncOfflineQueue,
  type SyncContext,
} from '../../services/offlineSync';
import { useSessionStore } from '../../store/sessionStore';
import { colors, radius, shadow, touchTargets, typography } from '../../theme';

export interface CountSessionProps {
  /** Fully-formed `ws(s)://host/ws/voice/{session_id}?token=...`. */
  wsUrl: string;
  apiBaseUrl: string;
  authToken: string;
  sessionId: string;
  warehouseId: string;
  warehouseCode: string;
  shift: 'morning' | 'afternoon' | 'night';
  shiftLabel: string;
}

/**
 * Operator-facing capture screen (CLAUDE.md §4) — the tablet PTT loop:
 * VoiceButton → confirmation (quantity, or expiry date first for
 * perishables per T-017) → next item. Theoretical stock is never fetched
 * or shown here, by design (CLAUDE.md §4 "pantalla durante conteo").
 *
 * Offline mode (CLAUDE.md §3.8): voice is disabled and ManualEntryForm
 * takes over, queuing entries locally (`offlineQueue.ts`, IndexedDB via
 * Dexie). On reconnect, `offlineSync.ts` drains the queue through Catalog
 * Agent + Auditor Agent; anything it can't resolve unattended (ambiguous
 * homologation, or a perishable missing its expiry date) surfaces in
 * `OfflineReviewList` instead of being guessed.
 */
export function CountSession({
  wsUrl,
  apiBaseUrl,
  authToken,
  sessionId,
  warehouseId,
  warehouseCode,
  shift,
  shiftLabel,
}: CountSessionProps) {
  const navigate = useNavigate();
  const items = useSessionStore((state) => state.items);
  const isOffline = useSessionStore((state) => state.isOffline);
  const setOffline = useSessionStore((state) => state.setOffline);
  const removeItem = useSessionStore((state) => state.removeItem);
  const { uiState, wsReady, startPTT, stopPTT, confirm, resetToIdle } = useVoiceSession(wsUrl);

  const [reviewRefreshKey, setReviewRefreshKey] = useState(0);
  const [manualFallbackError, setManualFallbackError] = useState<string | null>(null);
  const [sessionCompleted, setSessionCompleted] = useState(false);
  const [completeError, setCompleteError] = useState<string | null>(null);
  const [deletingItemId, setDeletingItemId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [completing, setCompleting] = useState(false);
  const [showExportHandoffNote, setShowExportHandoffNote] = useState(false);
  const wasOfflineRef = useRef(false);

  /** T-XXX: operators had no way to signal "done counting" — the session
   * lifecycle (CLAUDE.md §3.4, `in_progress -> pending_review -> ...`) sat
   * unreachable from the UI even though `POST /sessions/{id}/complete`
   * already existed server-side (api/sessions.py). A 409 here just means
   * a supervisor already resolved every flagged item and the session
   * auto-promoted past `in_progress` (api/supervisor.py's
   * `_maybe_mark_approved`) before the operator got to this button — not
   * a real error, so it's treated as success rather than shown as one. */
  const handleCompleteSession = async () => {
    setCompleting(true);
    setCompleteError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/sessions/${sessionId}/complete`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (response.ok || response.status === 409) {
        setSessionCompleted(true);
      } else {
        setCompleteError('No se pudo finalizar el inventario. Intenta de nuevo.');
      }
    } catch {
      setCompleteError('No se pudo finalizar el inventario. Revisa tu conexión e intenta de nuevo.');
    } finally {
      setCompleting(false);
    }
  };

  /** Undo for a mis-dictated item — `DELETE /count-items/{id}` (soft-delete
   * + an ItemDeleted event server-side) existed as a schema/event type
   * from the start but had no endpoint or UI until now; there was
   * previously no way to remove a wrong entry short of leaving it for a
   * supervisor to reject, which still keeps it in the export. */
  const handleDeleteItem = async (itemId: string) => {
    setDeleteError(null);
    setDeletingItemId(itemId);
    try {
      const response = await fetch(`${apiBaseUrl}/count-items/${itemId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (!response.ok) throw new Error('delete_failed');
      removeItem(itemId);
    } catch {
      setDeleteError('No se pudo eliminar el ítem. Intenta de nuevo.');
    } finally {
      setDeletingItemId(null);
    }
  };

  const syncCtx: SyncContext = { apiBaseUrl, authToken, warehouseId, shift };

  const runSync = useCallback(async () => {
    await syncOfflineQueue(sessionId, syncCtx);
    setReviewRefreshKey((key) => key + 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, apiBaseUrl, authToken, warehouseId, shift]);

  useEffect(() => {
    const goOffline = () => setOffline(true);
    const goOnline = () => {
      setOffline(false);
    };
    window.addEventListener('offline', goOffline);
    window.addEventListener('online', goOnline);
    setOffline(!navigator.onLine);
    return () => {
      window.removeEventListener('offline', goOffline);
      window.removeEventListener('online', goOnline);
    };
  }, [setOffline]);

  useEffect(() => {
    // Reconnect edge (true -> false): drain whatever ManualEntryForm queued
    // while offline. Runs once per transition, not on every render.
    if (wasOfflineRef.current && !isOffline) {
      runSync();
    }
    wasOfflineRef.current = isOffline;
  }, [isOffline, runSync]);

  const handleManualSubmit = async (values: { article: string; quantity: number; unit: string; expiryDate: string | null }) => {
    await enqueueOfflineItem({ sessionId, article: values.article, quantity: values.quantity, unit: values.unit, expiryDate: values.expiryDate });
  };

  /** T-006's per-item manual fallback (3 failed voice attempts) — unlike
   * offline capture this submits immediately (we're online, only the STT
   * failed), then returns the PTT loop to idle so the operator can go
   * back to voice for the next item. */
  const handleManualFallbackSubmit = async (values: {
    article: string;
    quantity: number;
    unit: string;
    expiryDate: string | null;
  }) => {
    setManualFallbackError(null);
    try {
      await submitManualFallbackItem(
        { sessionId, article: values.article, quantity: values.quantity, unit: values.unit, expiryDate: values.expiryDate },
        syncCtx,
      );
      resetToIdle();
    } catch (err) {
      if (err instanceof PersistCountItemError && err.errorCode === 'EXPIRY_DATE_REQUIRED') {
        setManualFallbackError('Este artículo es perecedero — agrega la fecha de vencimiento e intenta de nuevo.');
      } else if (err instanceof PersistCountItemError && err.errorCode === 'UNIT_MISMATCH') {
        setManualFallbackError(
          'La unidad indicada no es compatible con este producto — verifica si es un producto sólido/al peso (kg, g, lb, unidad) o líquido (L, mL, gal) e intenta de nuevo.',
        );
      } else {
        setManualFallbackError('No se pudo guardar el ítem. Intenta de nuevo.');
      }
    }
  };

  const buttonPhase: VoiceButtonPhase =
    isOffline || !wsReady
      ? 'disabled'
      : uiState.phase === 'listening'
        ? 'listening'
        : uiState.phase === 'processing'
          ? 'processing'
          : 'idle';

  const instruction = (() => {
    if (isOffline) return 'Sin conexión — captura los ítems con el formulario manual.';
    if (!wsReady) return 'Conectando…';
    switch (uiState.phase) {
      case 'awaiting_expiry_date':
        return uiState.message;
      case 'low_confidence':
        return `No se entendió bien (intento ${uiState.attempt}/${uiState.maxAttempts}). Intenta de nuevo.`;
      case 'manual_fallback':
        return 'Varios intentos fallidos — usa entrada manual para este ítem.';
      case 'error':
        return uiState.message;
      default:
        return 'Mantén presionado el botón y dicta artículo y cantidad.';
    }
  })();

  const dialogsBlockVoice = uiState.phase === 'confirming' || uiState.phase === 'confirming_expiry_date';

  const ribbonActions: RibbonAction[] = [
    { key: 'inicio', label: 'Inicio', icon: <HomeIcon />, onClick: () => navigate('/') },
    ...(!sessionCompleted
      ? [
          {
            key: 'finalizar',
            label: completing ? 'Finalizando…' : 'Finalizar inventario',
            icon: <CheckCircleIcon />,
            onClick: handleCompleteSession,
            disabled: completing || isOffline,
            variant: 'primary' as const,
          },
        ]
      : [
          {
            key: 'exportar',
            label: 'Exportar',
            icon: <ExportIcon />,
            onClick: () => setShowExportHandoffNote(true),
            variant: 'primary' as const,
          },
        ]),
  ];

  return (
    <div style={{ minHeight: '100vh', fontFamily: typography.fontFamily }}>
      <OfflineBanner isOffline={isOffline} />

      <div style={{ paddingTop: isOffline ? 40 : 0 }}>
        <BrandRibbon />
        <OptionsRibbon
          title={`Conteo de Bodega — ${warehouseCode}`}
          subtitle={`Turno ${shiftLabel}`}
          actions={ribbonActions}
        />
      </div>

      <div style={{ maxWidth: 720, margin: '0 auto', padding: '24px 16px' }}>
        {completeError && <p style={{ color: colors.ui.error }}>{completeError}</p>}
        {showExportHandoffNote && (
          <p role="status" style={{ color: colors.ui.textSecondary, background: colors.ui.surface, padding: '12px 16px', borderRadius: radius.small }}>
            La exportación a Excel la genera el supervisor desde su panel, una vez que revise los ítems marcados de esta sesión.
          </p>
        )}

        {sessionCompleted ? (
          <p
            role="status"
            style={{
              background: colors.ui.success,
              color: '#ffffff',
              padding: '12px 16px',
              borderRadius: radius.small,
              fontWeight: 600,
              boxShadow: shadow.low,
            }}
          >
            Inventario finalizado — enviado a revisión del supervisor.
          </p>
        ) : (
          <p style={{ color: colors.ui.textSecondary, minHeight: 24 }}>{instruction}</p>
        )}

        <div
          style={{
            background: colors.ui.background,
            borderRadius: radius.large,
            padding: 24,
            boxShadow: shadow.low,
          }}
        >
          {sessionCompleted ? null : isOffline ? (
            <ManualEntryForm onSubmit={handleManualSubmit} />
          ) : uiState.phase === 'manual_fallback' ? (
            <>
              {manualFallbackError && <p style={{ color: colors.ui.error }}>{manualFallbackError}</p>}
              <ManualEntryForm onSubmit={handleManualFallbackSubmit} />
            </>
          ) : (
            <>
              {!dialogsBlockVoice && (
                <div style={{ display: 'flex', justifyContent: 'center', margin: '16px 0' }}>
                  <VoiceButton phase={buttonPhase} onPressStart={startPTT} onPressEnd={stopPTT} />
                </div>
              )}

              {uiState.phase === 'confirming' && (
                <>
                  {/* oracle_code === null covers BOTH cases the voice flow can't
                      disambiguate mid-dictation: truly unmatched (sin_homologar,
                      score <0.50) AND ambiguous (0.50-0.79, several candidates —
                      the REST/offline flow shows a 3-alternatives picker for
                      this band, but there's no equivalent for a live voice
                      confirmation). Confirmed live: a made-up product landed at
                      0.5488 (ambiguous band) and was silently saved with the
                      raw dictated text and sin_homologar=false — no warning at
                      all — which is exactly the gap CLAUDE.md §3.2 leaves open
                      for voice specifically. */}
                  {uiState.item.oracle_code === null && (
                    <p
                      role="alert"
                      style={{
                        background: colors.primary.yellow,
                        color: colors.ui.textPrimary,
                        fontWeight: 700,
                        padding: '8px 16px',
                        borderRadius: radius.small,
                        maxWidth: 480,
                        margin: '0 auto 16px',
                      }}
                    >
                      ⚠ "{uiState.item.article}" no se identificó con certeza en el inventario — se guardará como
                      texto libre.
                    </p>
                  )}
                  <div style={{ display: 'flex', justifyContent: 'center' }}>
                    <ConfirmDialog
                      displayText={uiState.item.display_text}
                      articleName={uiState.item.article}
                      quantity={uiState.item.quantity}
                      unit={uiState.item.unit}
                      onConfirm={() => confirm(true)}
                      onCorrect={() => confirm(false)}
                    />
                  </div>
                </>
              )}

              {uiState.phase === 'confirming_expiry_date' && (
                <div style={{ display: 'flex', justifyContent: 'center' }}>
                  <ExpiryConfirmDialog
                    displayText={uiState.displayText}
                    onConfirm={() => confirm(true)}
                    onCorrect={() => confirm(false)}
                  />
                </div>
              )}
            </>
          )}
        </div>

        <OfflineReviewList sessionId={sessionId} ctx={syncCtx} refreshKey={reviewRefreshKey} />

        <h2 style={{ marginTop: 40, color: colors.ui.textPrimary }}>
          Ítems contados en esta sesión ({items.length})
        </h2>
        {deleteError && <p style={{ color: colors.ui.error }}>{deleteError}</p>}
        <ul
          style={{
            listStyle: 'none',
            padding: 0,
            background: colors.ui.background,
            borderRadius: radius.medium,
            boxShadow: shadow.low,
            overflow: 'hidden',
          }}
        >
          {items.length === 0 && (
            <li style={{ padding: 20, color: colors.ui.textSecondary, textAlign: 'center' }}>
              Aún no hay ítems contados en esta sesión.
            </li>
          )}
          {items.map((item) => (
            <li
              key={item.id}
              className="hoverable-row"
              style={{
                padding: '12px 16px',
                borderBottom: `1px solid ${colors.ui.border}`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 12,
                flexWrap: 'wrap',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', minWidth: 0 }}>
                <TrafficLight color={item.trafficLight} isPerishable={item.expiryDate !== null} />
                <span style={{ wordBreak: 'break-word' }}>
                  {item.quantity} {item.unit} — {item.articleName}
                  {item.sinHomologar ? ' (sin homologar)' : ''}
                  {item.expiryDate ? ` — vence ${item.expiryDate}` : ''}
                  {item.isOffline ? ' (capturado offline)' : ''}
                </span>
              </div>
              <button
                type="button"
                onClick={() => handleDeleteItem(item.id)}
                disabled={deletingItemId === item.id}
                aria-label={`Eliminar ${item.articleName}`}
                style={{
                  minHeight: touchTargets.minimum,
                  minWidth: touchTargets.minimum,
                  background: 'none',
                  border: `1px solid ${colors.ui.error}`,
                  borderRadius: radius.small,
                  color: colors.ui.error,
                  cursor: deletingItemId === item.id ? 'not-allowed' : 'pointer',
                  flexShrink: 0,
                }}
              >
                {deletingItemId === item.id ? '…' : 'Eliminar'}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
