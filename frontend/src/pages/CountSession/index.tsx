import { useCallback, useEffect, useRef, useState } from 'react';
import { ConfirmDialog } from '../../components/ConfirmDialog/ConfirmDialog';
import { ExpiryConfirmDialog } from '../../components/ExpiryConfirmDialog';
import { ManualEntryForm } from '../../components/ManualEntryForm';
import { OfflineBanner } from '../../components/OfflineBanner';
import { OfflineReviewList } from '../../components/OfflineReviewList';
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
import { colors, typography } from '../../theme';

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
  const items = useSessionStore((state) => state.items);
  const isOffline = useSessionStore((state) => state.isOffline);
  const setOffline = useSessionStore((state) => state.setOffline);
  const { uiState, startPTT, stopPTT, confirm, resetToIdle } = useVoiceSession(wsUrl);

  const [reviewRefreshKey, setReviewRefreshKey] = useState(0);
  const [manualFallbackError, setManualFallbackError] = useState<string | null>(null);
  const wasOfflineRef = useRef(false);

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
      } else {
        setManualFallbackError('No se pudo guardar el ítem. Intenta de nuevo.');
      }
    }
  };

  const buttonPhase: VoiceButtonPhase = isOffline
    ? 'disabled'
    : uiState.phase === 'listening'
      ? 'listening'
      : uiState.phase === 'processing'
        ? 'processing'
        : 'idle';

  const instruction = (() => {
    if (isOffline) return 'Sin conexión — captura los ítems con el formulario manual.';
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

  return (
    <div style={{ padding: 24, paddingTop: isOffline ? 56 : 24, fontFamily: typography.fontFamily }}>
      <OfflineBanner isOffline={isOffline} />

      <h1 style={{ color: colors.primary.blue }}>
        Conteo de Bodega — {warehouseCode} · Turno {shiftLabel}
      </h1>

      <p style={{ color: colors.ui.textSecondary, minHeight: 24 }}>{instruction}</p>

      {isOffline ? (
        <ManualEntryForm onSubmit={handleManualSubmit} />
      ) : uiState.phase === 'manual_fallback' ? (
        <>
          {manualFallbackError && <p style={{ color: colors.ui.error }}>{manualFallbackError}</p>}
          <ManualEntryForm onSubmit={handleManualFallbackSubmit} />
        </>
      ) : (
        <>
          {!dialogsBlockVoice && (
            <div style={{ display: 'flex', justifyContent: 'center', margin: '32px 0' }}>
              <VoiceButton phase={buttonPhase} onPressStart={startPTT} onPressEnd={stopPTT} />
            </div>
          )}

          {uiState.phase === 'confirming' && (
            <ConfirmDialog
              displayText={uiState.item.display_text}
              articleName={uiState.item.article}
              quantity={uiState.item.quantity}
              unit={uiState.item.unit}
              onConfirm={() => confirm(true)}
              onCorrect={() => confirm(false)}
            />
          )}

          {uiState.phase === 'confirming_expiry_date' && (
            <ExpiryConfirmDialog
              displayText={uiState.displayText}
              onConfirm={() => confirm(true)}
              onCorrect={() => confirm(false)}
            />
          )}
        </>
      )}

      <OfflineReviewList sessionId={sessionId} ctx={syncCtx} refreshKey={reviewRefreshKey} />

      <h2 style={{ marginTop: 40, color: colors.ui.textPrimary }}>
        Ítems contados en esta sesión ({items.length})
      </h2>
      <ul style={{ listStyle: 'none', padding: 0 }}>
        {items.map((item) => (
          <li
            key={item.id}
            style={{
              padding: '8px 0',
              borderBottom: `1px solid ${colors.ui.border}`,
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <TrafficLight color={item.trafficLight} isPerishable={item.expiryDate !== null} />
            <span>
              {item.quantity} {item.unit} — {item.articleName}
              {item.sinHomologar ? ' (sin homologar)' : ''}
              {item.expiryDate ? ` — vence ${item.expiryDate}` : ''}
              {item.isOffline ? ' (capturado offline)' : ''}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
