/**
 * Microphone capture -> mono PCM16 -> base64 chunks, sent to `gemini_live.py`
 * tagged with the ACTUAL sample rate captured (see `onChunk`'s second
 * argument) rather than a hardcoded one. Not unit-testable in jsdom (no
 * getUserMedia/AudioContext there) — exercised for real only in a real
 * browser against a live backend, which this environment doesn't have.
 *
 * DELIBERATELY NOT forcing 16kHz (confirmed live, 2026-07-25): this used to
 * request `sampleRate: 16000` on both getUserMedia and the AudioContext, and
 * hardcode `audio/pcm;rate=16000` when relaying to Gemini. On real hardware,
 * `getUserMedia(...).getSettings().sampleRate` came back `48000` regardless
 * of the constraint — and there's no way to be sure `AudioContext`'s
 * resampling from the device's native rate down to a requested one is
 * actually happening correctly through the deprecated `ScriptProcessorNode`
 * path, rather than just being silently mislabeled. A user hit exactly the
 * failure mode a rate mismatch predicts: consistently wrong, different-
 * each-time transcriptions (Gemini decoding pitch/speed-distorted audio).
 * Fix: let the `AudioContext` run at whatever rate the browser natively
 * gives it (no `sampleRate` option), read the REAL `audioContext.sampleRate`
 * it ends up with, and tell the backend the truth on every chunk instead of
 * assuming a number that may not match reality.
 *
 * Uses ScriptProcessorNode rather than an AudioWorklet: it's deprecated but
 * needs no separate worklet file/build step, which keeps this shippable
 * without extra Vite config. Swap to AudioWorkletNode if/when that
 * deprecation becomes a real problem.
 */
export interface MicCapture {
  stop: () => void;
}

const CHUNK_SAMPLES = 4096;

export async function startMicrophoneCapture(
  onChunk: (base64Pcm16: string, sampleRate: number) => void,
): Promise<MicCapture> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
  });

  const audioContext = new AudioContext();
  const sampleRate = audioContext.sampleRate;
  const source = audioContext.createMediaStreamSource(stream);
  const processor = audioContext.createScriptProcessor(CHUNK_SAMPLES, 1, 1);

  // Route through a silent gain instead of straight to destination — the
  // graph must reach destination for onaudioprocess to fire in Chrome, but
  // playing the operator's own mic back to them would be an unwanted echo.
  const silentGain = audioContext.createGain();
  silentGain.gain.value = 0;

  processor.onaudioprocess = (event) => {
    const input = event.inputBuffer.getChannelData(0);
    onChunk(pcm16Base64(input), sampleRate);
  };

  source.connect(processor);
  processor.connect(silentGain);
  silentGain.connect(audioContext.destination);

  return {
    stop: () => {
      processor.disconnect();
      source.disconnect();
      silentGain.disconnect();
      stream.getTracks().forEach((track) => track.stop());
      void audioContext.close();
    },
  };
}

function pcm16Base64(input: Float32Array): string {
  const pcm16 = new Int16Array(input.length);
  for (let i = 0; i < input.length; i++) {
    const sample = Math.max(-1, Math.min(1, input[i]));
    pcm16[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }

  const bytes = new Uint8Array(pcm16.buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}
