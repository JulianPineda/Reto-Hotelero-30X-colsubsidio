"""Gemini Live API adapter — reference STTProvider implementation (ADR-001,
CLAUDE.md 1.1). VAD tuned for warehouse-floor noise (~60dB): low start/end
sensitivity so short phrases and ambient noise don't trigger false starts.

VERIFIED against https://ai.google.dev/api/live and
https://ai.google.dev/gemini-api/docs/live-guide (fetched 2026-07-25):
- `session.send_realtime_input(audio=types.Blob(data=..., mime_type=...))`
  and `response.server_content.input_transcription.text` are the documented
  Python SDK shapes — confirmed correct as originally written.
- `input_audio_transcription` MUST be set in `LiveConnectConfig`, or the
  server never sends `input_transcription` at all. This was MISSING before
  and is now added below — without it, `receive()` would silently yield
  nothing, ever.
- `BidiGenerateContentTranscription` has ONLY a `text` field. There is no
  `finished`/`is_final` flag and NO confidence score anywhere in the
  Live API's transcription messages. The previous version of this file
  read non-existent `.finished` and `.confidence` attributes via `getattr`
  with silent defaults (`False` / `None`) — meaning `is_final` was ALWAYS
  False and no FINAL event would ever fire, and confidence was always None.
  Finality is now derived from `server_content.turn_complete` instead
  (accumulating transcript fragments until the turn completes).

UNRESOLVED ARCHITECTURE GAP (needs a decision, not a code fix): CLAUDE.md
§3.2's "si el score STT < 0.75, pedir repetir" rule assumes a per-utterance
STT confidence score. Gemini's Live API genuinely does not provide one for
input transcription (confirmed above) — this isn't a bug to patch, it's a
capability gap in the provider ADR-001 chose. `TranscriptEvent.confidence`
is always None here; `voice/session.py`'s threshold check against it needs
a product decision (see the summary sent alongside this fix).
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from google import genai
from google.genai import types

from app.agents.voice.schemas import SessionConfig, TranscriptEvent, TranscriptEventType
from app.agents.voice.stt_provider import STTProvider
from app.config import settings

MODEL_NAME = "gemini-1.5-flash"  # ADR-001 — confirmar variante Live disponible al implementar


class GeminiLiveSTTProvider(STTProvider):
    def __init__(self) -> None:
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._session_cm = None
        self._session = None

    async def connect(self, session_config: SessionConfig) -> None:
        live_config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                language_code=session_config.language_code,
            ),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    start_of_speech_sensitivity="START_SENSITIVITY_LOW",
                    end_of_speech_sensitivity="END_SENSITIVITY_LOW",
                    silence_duration_ms=600,
                    prefix_padding_ms=300,
                ),
            ),
            # Required or the server never sends input_transcription at all.
            input_audio_transcription=types.AudioTranscriptionConfig(),
        )
        self._session_cm = self._client.aio.live.connect(model=MODEL_NAME, config=live_config)
        self._session = await self._session_cm.__aenter__()

    async def send_audio(self, chunk: bytes) -> None:
        if self._session is None:
            raise RuntimeError("call connect() before send_audio()")
        await self._session.send_realtime_input(
            audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
        )

    async def receive(self) -> AsyncIterator[TranscriptEvent]:
        if self._session is None:
            raise RuntimeError("call connect() before receive()")

        accumulated_text = ""
        async for response in self._session.receive():
            server_content = getattr(response, "server_content", None)
            if server_content is None:
                continue

            transcript = getattr(server_content, "input_transcription", None)
            if transcript is not None and getattr(transcript, "text", None):
                accumulated_text += transcript.text
                yield TranscriptEvent(
                    type=TranscriptEventType.PARTIAL, text=accumulated_text, confidence=None
                )

            if getattr(server_content, "turn_complete", False):
                yield TranscriptEvent(
                    type=TranscriptEventType.FINAL, text=accumulated_text, confidence=None
                )
                accumulated_text = ""

    async def disconnect(self) -> None:
        if self._session_cm is not None:
            await self._session_cm.__aexit__(None, None, None)
        self._session = None
        self._session_cm = None
