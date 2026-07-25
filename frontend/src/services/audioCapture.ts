/**
 * Microphone capture -> 16kHz mono PCM16 -> base64 chunks, matching what
 * `gemini_live.py` expects on the wire (`audio/pcm;rate=16000`, see
 * `send_realtime_input`). Not unit-testable in jsdom (no getUserMedia/
 * AudioContext there) — exercised for real only in a real browser against a
 * live backend, which this environment doesn't have.
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

export async function startMicrophoneCapture(onChunk: (base64Pcm16: string) => void): Promise<MicCapture> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, sampleRate: 16000, echoCancellation: true, noiseSuppression: true },
  });

  const audioContext = new AudioContext({ sampleRate: 16000 });
  const source = audioContext.createMediaStreamSource(stream);
  const processor = audioContext.createScriptProcessor(CHUNK_SAMPLES, 1, 1);

  // Route through a silent gain instead of straight to destination — the
  // graph must reach destination for onaudioprocess to fire in Chrome, but
  // playing the operator's own mic back to them would be an unwanted echo.
  const silentGain = audioContext.createGain();
  silentGain.gain.value = 0;

  processor.onaudioprocess = (event) => {
    const input = event.inputBuffer.getChannelData(0);
    onChunk(pcm16Base64(input));
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
