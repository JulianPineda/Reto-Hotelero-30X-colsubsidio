"""Gemini Live API adapter — reference STTProvider implementation (ADR-001,
CLAUDE.md 1.1). VAD tuned for warehouse-floor noise (~60dB): low start/end
sensitivity so short phrases and ambient noise don't trigger false starts.

VERIFIED against https://ai.google.dev/api/live and
https://ai.google.dev/gemini-api/docs/live-guide (fetched 2026-07-25):
- `session.send_realtime_input(audio=types.Blob(data=..., mime_type=...))`
  and `response.server_content.input_transcription.text` are the documented
  Python SDK shapes — confirmed correct as originally written.
- `input_audio_transcription` MUST be set in `LiveConnectConfig`, or the
  server never sends `input_transcription` at all.
- `BidiGenerateContentTranscription` has ONLY a `text` field. There is no
  `finished`/`is_final` flag and NO confidence score anywhere in the
  Live API's transcription messages. Finality is derived from
  `server_content.turn_complete` instead (accumulating transcript
  fragments until the turn completes).

TTS CONFIRMATION READBACK (added from a working browser-side reference the
user supplied — its `sendRealtimeInput({text})` / `serverContent.modelTurn
.parts[0].inlineData` / `outputAudioTranscription` shapes cross-checked
against this file's already-verified `send_realtime_input(audio=...)` /
`input_transcription` patterns): `session.send_realtime_input(text=...)` is
inferred by symmetry with the audio call above, NOT independently
re-verified against docs this session — flag if Gemini rejects it.
Also adopts that reference's model name (`gemini-3.1-flash-live-preview`),
confirmed working there, replacing this file's previous placeholder
("confirmar variante Live disponible al implementar").

NOTE ON WHY THIS FILE OWNS ONE CONTINUOUS READER: `self._session.receive()`
is one bidirectional stream carrying BOTH input transcription and output
TTS audio interleaved. `session.py` calls `receive()` fresh per ptt_stop
cycle and always did (breaking out after the FINAL event) — rather than
change that contract, `_drain()` is the ONE real reader of the underlying
SDK stream, fanning out into two internal queues; `receive()` and
`receive_audio()` each just pull from their own queue, so callers never
have to coordinate who reads the wire.

UNRESOLVED ARCHITECTURE GAP (needs a decision, not a code fix): CLAUDE.md
§3.2's "si el score STT < 0.75, pedir repetir" rule assumes a per-utterance
STT confidence score. Gemini's Live API genuinely does not provide one for
input transcription (confirmed above) — this isn't a bug to patch, it's a
capability gap in the provider ADR-001 chose. `TranscriptEvent.confidence`
is always None here; `voice/session.py`'s threshold check against it needs
a product decision (see the summary sent alongside the original fix).
"""
from __future__ import annotations

import asyncio
import base64
from collections.abc import AsyncIterator

from google import genai
from google.genai import types

from app.agents.voice.schemas import SessionConfig, TranscriptEvent, TranscriptEventType
from app.agents.voice.stt_provider import STTProvider
from app.config import settings

MODEL_NAME = "gemini-3.1-flash-live-preview"  # ADR-001 — from a confirmed-working reference (see module docstring)

# Keeps the model a pure text-to-speech reader for our own confirmation
# strings, not a chatty assistant — the browser-side reference this was
# adapted from used a conversational persona, which is wrong for our use
# case: the operator needs to hear exactly the digit-by-digit confirmation
# text, not Gemini's own improvised reply to it.
TTS_SYSTEM_INSTRUCTION = (
    "Cuando recibas un mensaje de texto, léelo en voz alta de forma clara y "
    "natural, EXACTAMENTE como te lo dan — sin agregar saludos, comentarios, "
    "preguntas ni interpretación propia. No converses. Tu único trabajo es "
    "la lectura en voz alta de confirmaciones de conteo de inventario."
)


class GeminiLiveSTTProvider(STTProvider):
    def __init__(self) -> None:
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._session_cm = None
        self._session = None
        self._transcript_queue: asyncio.Queue[TranscriptEvent | None] = asyncio.Queue()
        self._audio_queue: asyncio.Queue[str] = asyncio.Queue()
        self._drain_task: asyncio.Task[None] | None = None

    async def connect(self, session_config: SessionConfig) -> None:
        live_config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=TTS_SYSTEM_INSTRUCTION,
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
            output_audio_transcription=types.AudioTranscriptionConfig(),
        )
        self._session_cm = self._client.aio.live.connect(model=MODEL_NAME, config=live_config)
        self._session = await self._session_cm.__aenter__()
        self._drain_task = asyncio.create_task(self._drain())

    async def _drain(self) -> None:
        """The one real reader of the Live API's bidirectional stream —
        see module docstring. Pushes a `None` sentinel onto the transcript
        queue when the stream ends so `receive()` can terminate its
        generator instead of blocking forever."""
        accumulated_text = ""
        try:
            async for response in self._session.receive():
                server_content = getattr(response, "server_content", None)
                if server_content is None:
                    continue

                transcript = getattr(server_content, "input_transcription", None)
                if transcript is not None and getattr(transcript, "text", None):
                    accumulated_text += transcript.text
                    await self._transcript_queue.put(
                        TranscriptEvent(type=TranscriptEventType.PARTIAL, text=accumulated_text, confidence=None)
                    )

                model_turn = getattr(server_content, "model_turn", None)
                for part in getattr(model_turn, "parts", None) or []:
                    inline_data = getattr(part, "inline_data", None)
                    raw = getattr(inline_data, "data", None) if inline_data is not None else None
                    if raw:
                        await self._audio_queue.put(base64.b64encode(raw).decode("ascii"))

                if getattr(server_content, "turn_complete", False):
                    await self._transcript_queue.put(
                        TranscriptEvent(type=TranscriptEventType.FINAL, text=accumulated_text, confidence=None)
                    )
                    accumulated_text = ""
        finally:
            await self._transcript_queue.put(None)

    async def send_audio(self, chunk: bytes) -> None:
        if self._session is None:
            raise RuntimeError("call connect() before send_audio()")
        await self._session.send_realtime_input(
            audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
        )

    async def speak(self, text: str) -> None:
        if self._session is None:
            raise RuntimeError("call connect() before speak()")
        await self._session.send_realtime_input(text=text)

    async def receive(self) -> AsyncIterator[TranscriptEvent]:
        if self._session is None:
            raise RuntimeError("call connect() before receive()")
        while True:
            event = await self._transcript_queue.get()
            if event is None:
                return
            yield event

    async def receive_audio(self) -> AsyncIterator[str]:
        if self._session is None:
            raise RuntimeError("call connect() before receive_audio()")
        while True:
            yield await self._audio_queue.get()

    async def disconnect(self) -> None:
        if self._drain_task is not None:
            self._drain_task.cancel()
            self._drain_task = None
        if self._session_cm is not None:
            await self._session_cm.__aexit__(None, None, None)
        self._session = None
        self._session_cm = None
