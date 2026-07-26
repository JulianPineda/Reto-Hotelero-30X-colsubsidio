/**
 * Message shapes match `voice/session.py`'s dict responses exactly
 * (EPIC-2 T-006 + T-017 perishables extension) — snake_case fields, one
 * variant per `type`.
 */
export type ConfirmationRequestMessage = {
  type: 'confirmation_request';
  item_id: string;
  oracle_code: string | null;
  article: string;
  quantity: number;
  unit: string;
  expiry_date: string | null;
  digit_by_digit: string | null;
  display_text: string;
  /** CLAUDE.md §3.2's score <0.50 case — the article didn't match anything
   * in the catalog closely enough. Surfaced here (not just as a trailing
   * label after saving) so the operator sees it before confirming. */
  sin_homologar: boolean;
};

export type ServerMessage =
  | { type: 'listening' }
  | ConfirmationRequestMessage
  | { type: 'expiry_date_request'; item_id: string; article: string; message: string }
  | { type: 'expiry_date_confirmation_request'; item_id: string; expiry_date: string; display_text: string }
  | {
      type: 'item_saved';
      item_id: string;
      expiry_date: string | null;
      is_flagged: boolean;
      flag_type: 'threshold' | 'trend' | 'both' | null;
      traffic_light: 'red' | 'yellow' | 'green' | null;
      sequence: number | null;
    }
  | { type: 'low_confidence'; confidence: number | null; attempt: number; max_attempts: number }
  | { type: 'manual_fallback_offered' }
  | { type: 'error'; code: string; message: string }
  // TTS confirmation readback (session.py's speak() calls) — a side
  // channel played via services/audioPlayback.ts in useVoiceSession, not
  // something that changes VoiceUIState's phase.
  | { type: 'audio_out'; data: string };

/** Client-originated pseudo-events — `ptt_stop` moves the UI to
 * "processing" immediately without waiting for the server round-trip;
 * `client_reset` returns to idle after a successful manual-fallback
 * submission (there's no server message for this — the submission goes
 * straight to `POST /count-items`, bypassing the WS session entirely). */
export type ClientEvent = { type: 'client_processing' } | { type: 'client_reset' };

export type VoiceEvent = ServerMessage | ClientEvent;

export type VoiceUIState =
  | { phase: 'idle' }
  | { phase: 'listening' }
  | { phase: 'processing' }
  | { phase: 'confirming'; item: ConfirmationRequestMessage }
  | { phase: 'awaiting_expiry_date'; itemId: string; article: string; message: string }
  | { phase: 'confirming_expiry_date'; itemId: string; expiryDate: string; displayText: string }
  | { phase: 'low_confidence'; confidence: number | null; attempt: number; maxAttempts: number }
  | { phase: 'manual_fallback' }
  | { phase: 'error'; code: string; message: string };

export const initialVoiceUIState: VoiceUIState = { phase: 'idle' };

export function reduceVoiceEvent(state: VoiceUIState, event: VoiceEvent): VoiceUIState {
  switch (event.type) {
    case 'client_processing':
      return { phase: 'processing' };
    case 'client_reset':
      return { phase: 'idle' };
    case 'listening':
      return { phase: 'listening' };
    case 'confirmation_request':
      return { phase: 'confirming', item: event };
    case 'expiry_date_request':
      return {
        phase: 'awaiting_expiry_date',
        itemId: event.item_id,
        article: event.article,
        message: event.message,
      };
    case 'expiry_date_confirmation_request':
      return {
        phase: 'confirming_expiry_date',
        itemId: event.item_id,
        expiryDate: event.expiry_date,
        displayText: event.display_text,
      };
    case 'item_saved':
      return { phase: 'idle' };
    case 'low_confidence':
      return {
        phase: 'low_confidence',
        confidence: event.confidence,
        attempt: event.attempt,
        maxAttempts: event.max_attempts,
      };
    case 'manual_fallback_offered':
      return { phase: 'manual_fallback' };
    case 'error':
      return { phase: 'error', code: event.code, message: event.message };
    case 'audio_out':
      return state;
    default:
      return state;
  }
}
