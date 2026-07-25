"""Gemini Live API adapter — reference STTProvider implementation (ADR-001,
CLAUDE.md 1.1). VAD tuned for warehouse-floor noise (~60dB): low start/end
sensitivity so short phrases and ambient noise don't trigger false starts.

CAVEAT: the exact `google-genai` Live API response shape (attribute names on
the streamed message — transcript text, "is final" flag, confidence) could
not be verified against a live session in this environment (no network, no
API key). The connect/send/receive control flow follows the SDK's documented
async-context-manager pattern, but confirm the response attribute paths
against the installed `google-genai` version before relying on this in
production — client-side field names on this API have changed between
releases.
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
        async for response in self._session.receive():
            transcript = getattr(response.server_content, "input_transcription", None)
            if transcript is None or not getattr(transcript, "text", None):
                continue
            is_final = bool(getattr(transcript, "finished", False))
            yield TranscriptEvent(
                type=TranscriptEventType.FINAL if is_final else TranscriptEventType.PARTIAL,
                text=transcript.text,
                confidence=getattr(transcript, "confidence", None),
            )

    async def disconnect(self) -> None:
        if self._session_cm is not None:
            await self._session_cm.__aexit__(None, None, None)
        self._session = None
        self._session_cm = None
