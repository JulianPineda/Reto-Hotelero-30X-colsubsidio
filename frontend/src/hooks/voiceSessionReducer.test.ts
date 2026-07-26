import { describe, expect, it } from 'vitest';
import { initialVoiceUIState, reduceVoiceEvent } from './voiceSessionReducer';

describe('reduceVoiceEvent', () => {
  it('starts idle', () => {
    expect(initialVoiceUIState).toEqual({ phase: 'idle' });
  });

  it('client_processing moves to processing', () => {
    const result = reduceVoiceEvent(initialVoiceUIState, { type: 'client_processing' });
    expect(result).toEqual({ phase: 'processing' });
  });

  it('client_reset returns to idle from manual_fallback', () => {
    const result = reduceVoiceEvent({ phase: 'manual_fallback' }, { type: 'client_reset' });
    expect(result).toEqual({ phase: 'idle' });
  });

  it('listening moves to listening', () => {
    const result = reduceVoiceEvent({ phase: 'processing' }, { type: 'listening' });
    expect(result).toEqual({ phase: 'listening' });
  });

  it('confirmation_request moves to confirming with the full item', () => {
    const message = {
      type: 'confirmation_request' as const,
      item_id: 'abc',
      oracle_code: 'HAR-001',
      article: 'Harina de Trigo',
      quantity: 20,
      unit: 'kg',
      expiry_date: null,
      digit_by_digit: null,
      display_text: '¿20 kg de Harina de Trigo?',
    };

    const result = reduceVoiceEvent(initialVoiceUIState, message);

    expect(result).toEqual({ phase: 'confirming', item: message });
  });

  it('expiry_date_request moves to awaiting_expiry_date', () => {
    const result = reduceVoiceEvent(initialVoiceUIState, {
      type: 'expiry_date_request',
      item_id: 'abc',
      article: 'Leche Entera 1L',
      message: '¿Cuál es la fecha de vencimiento de Leche Entera 1L?',
    });

    expect(result).toEqual({
      phase: 'awaiting_expiry_date',
      itemId: 'abc',
      article: 'Leche Entera 1L',
      message: '¿Cuál es la fecha de vencimiento de Leche Entera 1L?',
    });
  });

  it('expiry_date_confirmation_request moves to confirming_expiry_date', () => {
    const result = reduceVoiceEvent(initialVoiceUIState, {
      type: 'expiry_date_confirmation_request',
      item_id: 'abc',
      expiry_date: '2026-08-15',
      display_text: '¿Confirmas fecha de vencimiento: quince de agosto de dos mil veintiséis?',
    });

    expect(result).toEqual({
      phase: 'confirming_expiry_date',
      itemId: 'abc',
      expiryDate: '2026-08-15',
      displayText: '¿Confirmas fecha de vencimiento: quince de agosto de dos mil veintiséis?',
    });
  });

  it('item_saved returns to idle', () => {
    const result = reduceVoiceEvent(
      { phase: 'confirming', item: {} as never },
      {
        type: 'item_saved',
        item_id: 'abc',
        expiry_date: null,
        is_flagged: false,
        flag_type: null,
        traffic_light: null,
        sequence: 1,
      },
    );

    expect(result).toEqual({ phase: 'idle' });
  });

  it('low_confidence carries attempt counters', () => {
    const result = reduceVoiceEvent(initialVoiceUIState, {
      type: 'low_confidence',
      confidence: 0.5,
      attempt: 2,
      max_attempts: 3,
    });

    expect(result).toEqual({ phase: 'low_confidence', confidence: 0.5, attempt: 2, maxAttempts: 3 });
  });

  it('manual_fallback_offered moves to manual_fallback', () => {
    const result = reduceVoiceEvent(initialVoiceUIState, { type: 'manual_fallback_offered' });
    expect(result).toEqual({ phase: 'manual_fallback' });
  });

  it('error carries code and message', () => {
    const result = reduceVoiceEvent(initialVoiceUIState, {
      type: 'error',
      code: 'PARSE_FAILED',
      message: 'No se pudo extraer artículo o cantidad del texto.',
    });

    expect(result).toEqual({
      phase: 'error',
      code: 'PARSE_FAILED',
      message: 'No se pudo extraer artículo o cantidad del texto.',
    });
  });
});
