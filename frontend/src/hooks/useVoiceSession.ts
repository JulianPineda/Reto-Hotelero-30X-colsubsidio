import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import { startMicrophoneCapture, type MicCapture } from '../services/audioCapture';
import { playChunk, stopAllAudio } from '../services/audioPlayback';
import { useSessionStore } from '../store/sessionStore';
import {
  initialVoiceUIState,
  reduceVoiceEvent,
  type ConfirmationRequestMessage,
  type ServerMessage,
  type VoiceUIState,
} from './voiceSessionReducer';

export interface UseVoiceSessionResult {
  uiState: VoiceUIState;
  /** False until the WS handshake completes. Confirmed live: pressing the
   * VoiceButton before this was true silently dropped `ptt_start` (and
   * every audio chunk after it) — `send()` no-ops on a non-OPEN socket —
   * while the mic still "listened" locally with no error shown, and the
   * eventual `ptt_stop` crashed server-side with nothing to stop. Callers
   * should keep the button disabled until this is true. */
  wsReady: boolean;
  startPTT: () => void;
  stopPTT: () => void;
  confirm: (value: boolean) => void;
  bargeIn: () => void;
  resetToIdle: () => void;
}

/**
 * Wraps `WS /ws/voice/{session_id}` (EPIC-2 T-006, extended by T-017) into
 * React state. One WS connection lives for the page's lifetime — matches
 * `VoicePTTSession`'s per-connection lifetime on the backend, so multiple
 * ptt_start/ptt_stop cycles reuse the same session instead of reconnecting
 * per utterance.
 *
 * `item_saved` carries the Orchestrator's real persisted fields
 * (`item_id`/`is_flagged`/`flag_type`/`traffic_light`/`sequence` — see
 * session.py::handle_confirm calling `persist_item`) but not
 * article/quantity/unit, which come from the `confirmation_request` that
 * preceded it, kept in `pendingConfirmationRef` until the item is either
 * saved or the operator asks to redictate.
 */
export function useVoiceSession(wsUrl: string): UseVoiceSessionResult {
  const [uiState, dispatch] = useReducer(reduceVoiceEvent, initialVoiceUIState);
  const [wsReady, setWsReady] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const micRef = useRef<MicCapture | null>(null);
  const pendingConfirmationRef = useRef<ConfirmationRequestMessage | null>(null);
  const addItem = useSessionStore((state) => state.addItem);

  useEffect(() => {
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    setWsReady(false);

    ws.onopen = () => setWsReady(true);
    ws.onclose = () => setWsReady(false);

    ws.onmessage = (event: MessageEvent<string>) => {
      const message: ServerMessage = JSON.parse(event.data);

      if (message.type === 'audio_out') {
        playChunk(message.data);
        return;
      }

      if (message.type === 'confirmation_request') {
        pendingConfirmationRef.current = message;
      }

      if (message.type === 'item_saved') {
        const pending = pendingConfirmationRef.current;
        if (pending) {
          addItem({
            id: message.item_id,
            oracleCode: pending.oracle_code,
            articleName: pending.article,
            quantity: pending.quantity,
            unit: pending.unit,
            isFlagged: message.is_flagged,
            flagType: message.flag_type,
            flagReason: null,
            isApproved: null,
            isOffline: false,
            sinHomologar: pending.oracle_code === null,
            expiryDate: message.expiry_date,
            trafficLight: message.traffic_light,
            sequenceInSession: message.sequence ?? 0,
          });
        }
        pendingConfirmationRef.current = null;
      }

      dispatch(message);
    };

    return () => {
      ws.close();
      wsRef.current = null;
      setWsReady(false);
    };
  }, [wsUrl, addItem]);

  const send = useCallback((payload: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(payload));
    }
  }, []);

  const startPTT = useCallback(() => {
    // Barge-in (CLAUDE.md/T-006 "interrumpir TTS"): pressing the button
    // again always interrupts whatever confirmation readback might still
    // be playing, both locally and on the backend's session state.
    stopAllAudio();
    send({ type: 'barge_in' });
    send({ type: 'ptt_start' });
    startMicrophoneCapture((base64Pcm16, sampleRate) =>
      send({ type: 'audio_chunk', data: base64Pcm16, sample_rate: sampleRate }),
    ).then((mic) => {
      micRef.current = mic;
    });
  }, [send]);

  const stopPTT = useCallback(() => {
    micRef.current?.stop();
    micRef.current = null;
    dispatch({ type: 'client_processing' });
    send({ type: 'ptt_stop' });
  }, [send]);

  const confirm = useCallback(
    (value: boolean) => {
      send({ type: 'confirm', value });
    },
    [send],
  );

  const bargeIn = useCallback(() => {
    send({ type: 'barge_in' });
  }, [send]);

  /** After `manual_fallback` (3 failed voice attempts), the operator
   * submits that one item via `submitManualFallbackItem` (a plain REST
   * call — see offlineSync.ts) instead of anything going through this WS
   * session, so nothing server-side ever moves the phase back off
   * `manual_fallback` on its own. */
  const resetToIdle = useCallback(() => {
    dispatch({ type: 'client_reset' });
  }, []);

  return { uiState, wsReady, startPTT, stopPTT, confirm, bargeIn, resetToIdle };
}
