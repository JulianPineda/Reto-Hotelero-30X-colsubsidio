/**
 * Plays TTS audio chunks relayed from the backend's Gemini Live session
 * (`voice/router.py`'s `on_audio_chunk` -> `{"type":"audio_out"}` WS
 * messages — see `session.py`'s `speak()` calls for what triggers them).
 * 24kHz PCM16 matches Gemini Live's audio output sample rate.
 *
 * Mirrors a browser-side reference implementation the user supplied, but
 * this module never talks to Gemini directly — the API key stays
 * server-side (CLAUDE.md §5), audio only ever arrives over our own
 * authenticated WS connection.
 */
const SAMPLE_RATE_HZ = 24000;

let audioContext: AudioContext | null = null;
let nextStartTime = 0;
const activeSources = new Set<AudioBufferSourceNode>();

function getAudioContext(): AudioContext {
  if (!audioContext) {
    audioContext = new AudioContext({ sampleRate: SAMPLE_RATE_HZ });
    nextStartTime = audioContext.currentTime;
  }
  return audioContext;
}

export function playChunk(base64Pcm16: string): void {
  const ctx = getAudioContext();
  const bytes = base64ToBytes(base64Pcm16);
  const float32 = pcm16ToFloat32(bytes);

  const buffer = ctx.createBuffer(1, float32.length, SAMPLE_RATE_HZ);
  buffer.getChannelData(0).set(float32);

  const source = ctx.createBufferSource();
  source.buffer = buffer;
  source.connect(ctx.destination);
  source.addEventListener('ended', () => activeSources.delete(source));

  // Chunks queue back-to-back instead of overlapping, same scheduling
  // trick as the reference implementation.
  nextStartTime = Math.max(nextStartTime, ctx.currentTime);
  source.start(nextStartTime);
  nextStartTime += buffer.duration;
  activeSources.add(source);
}

/** Barge-in (CLAUDE.md/T-006 "interrumpir TTS") — stops whatever's
 * currently queued or playing immediately. */
export function stopAllAudio(): void {
  for (const source of activeSources) {
    try {
      source.stop();
    } catch {
      // Already stopped/ended naturally — safe to ignore.
    }
  }
  activeSources.clear();
  if (audioContext) {
    nextStartTime = audioContext.currentTime;
  }
}

function base64ToBytes(base64: string): Uint8Array {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

function pcm16ToFloat32(bytes: Uint8Array): Float32Array {
  const int16 = new Int16Array(bytes.buffer, bytes.byteOffset, bytes.byteLength / 2);
  const float32 = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) {
    float32[i] = int16[i] / 32768;
  }
  return float32;
}
