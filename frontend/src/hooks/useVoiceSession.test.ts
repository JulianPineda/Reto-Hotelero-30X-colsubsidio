import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useSessionStore } from '../store/sessionStore';
import { useVoiceSession } from './useVoiceSession';
import * as audioPlayback from '../services/audioPlayback';

vi.mock('../services/audioCapture', () => ({
  startMicrophoneCapture: vi.fn().mockResolvedValue({ stop: vi.fn() }),
}));

vi.mock('../services/audioPlayback', () => ({
  playChunk: vi.fn(),
  stopAllAudio: vi.fn(),
}));

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static readonly OPEN = 1;
  readyState = FakeWebSocket.OPEN;
  onmessage: ((event: { data: string }) => void) | null = null;
  sent: string[] = [];

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    /* no-op for tests */
  }

  emit(message: unknown) {
    this.onmessage?.({ data: JSON.stringify(message) });
  }
}

beforeEach(() => {
  FakeWebSocket.instances = [];
  vi.stubGlobal('WebSocket', FakeWebSocket);
  useSessionStore.getState().reset();
  vi.mocked(audioPlayback.playChunk).mockClear();
  vi.mocked(audioPlayback.stopAllAudio).mockClear();
});

describe('useVoiceSession', () => {
  it('sends barge_in then ptt_start on startPTT, stopping any playing audio', () => {
    const { result } = renderHook(() => useVoiceSession('ws://test/voice/demo'));
    const ws = FakeWebSocket.instances[0];

    act(() => {
      result.current.startPTT();
    });

    expect(audioPlayback.stopAllAudio).toHaveBeenCalledTimes(1);
    expect(JSON.parse(ws.sent[0])).toEqual({ type: 'barge_in' });
    expect(JSON.parse(ws.sent[1])).toEqual({ type: 'ptt_start' });
  });

  it('plays audio_out chunks as they arrive', () => {
    renderHook(() => useVoiceSession('ws://test/voice/demo'));
    const ws = FakeWebSocket.instances[0];

    act(() => {
      ws.emit({ type: 'audio_out', data: 'base64chunk==' });
    });

    expect(audioPlayback.playChunk).toHaveBeenCalledWith('base64chunk==');
  });

  it('stopPTT moves to processing locally and sends ptt_stop', () => {
    const { result } = renderHook(() => useVoiceSession('ws://test/voice/demo'));
    const ws = FakeWebSocket.instances[0];

    act(() => {
      result.current.stopPTT();
    });

    expect(result.current.uiState.phase).toBe('processing');
    expect(JSON.parse(ws.sent[0])).toEqual({ type: 'ptt_stop' });
  });

  it('confirmation_request moves ui to confirming', () => {
    const { result } = renderHook(() => useVoiceSession('ws://test/voice/demo'));
    const ws = FakeWebSocket.instances[0];

    act(() => {
      ws.emit({
        type: 'confirmation_request',
        item_id: 'abc',
        oracle_code: 'HAR-001',
        article: 'Harina de Trigo',
        quantity: 20,
        unit: 'kg',
        expiry_date: null,
        digit_by_digit: null,
        display_text: '¿20 kg de Harina de Trigo?',
      });
    });

    expect(result.current.uiState.phase).toBe('confirming');
  });

  it('item_saved adds the pending item to sessionStore and returns to idle', () => {
    const { result } = renderHook(() => useVoiceSession('ws://test/voice/demo'));
    const ws = FakeWebSocket.instances[0];

    act(() => {
      ws.emit({
        type: 'confirmation_request',
        item_id: 'abc',
        oracle_code: 'HAR-001',
        article: 'Harina de Trigo',
        quantity: 20,
        unit: 'kg',
        expiry_date: null,
        digit_by_digit: null,
        display_text: '¿20 kg de Harina de Trigo?',
      });
    });

    act(() => {
      ws.emit({
        type: 'item_saved',
        item_id: 'abc',
        expiry_date: null,
        is_flagged: true,
        flag_type: 'threshold',
        traffic_light: null,
        sequence: 1,
      });
    });

    expect(result.current.uiState.phase).toBe('idle');
    const items = useSessionStore.getState().items;
    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({
      id: 'abc',
      oracleCode: 'HAR-001',
      articleName: 'Harina de Trigo',
      quantity: 20,
      unit: 'kg',
      sinHomologar: false,
      isFlagged: true,
      flagType: 'threshold',
    });
  });

  it('item_saved without a preceding confirmation_request does not add an item', () => {
    const { result } = renderHook(() => useVoiceSession('ws://test/voice/demo'));
    const ws = FakeWebSocket.instances[0];

    act(() => {
      ws.emit({
        type: 'item_saved',
        item_id: 'orphan',
        expiry_date: null,
        is_flagged: false,
        flag_type: null,
        traffic_light: null,
        sequence: 1,
      });
    });

    expect(result.current.uiState.phase).toBe('idle');
    expect(useSessionStore.getState().items).toHaveLength(0);
  });

  it('confirm sends the confirm message with the given value', () => {
    const { result } = renderHook(() => useVoiceSession('ws://test/voice/demo'));
    const ws = FakeWebSocket.instances[0];

    act(() => {
      result.current.confirm(true);
    });

    expect(JSON.parse(ws.sent[0])).toEqual({ type: 'confirm', value: true });
  });
});
