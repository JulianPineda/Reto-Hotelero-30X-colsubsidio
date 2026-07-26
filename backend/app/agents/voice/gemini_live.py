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
user supplied, then corrected against a real live connection with a real
API key on 2026-07-25): the reference's `sendRealtimeInput({text})` does
NOT reliably trigger a spoken reply — confirmed by testing it directly:
`connect()` succeeded, `speak()` returned with no error, but zero audio
chunks ever arrived. Inspecting the installed SDK's own docstrings
explains why: `send_realtime_input` is "optimized for responsiveness at
the expense of deterministic ordering" (built for continuous audio/video
+ VAD, not one-shot turn-based prompting), while `send_client_content(
turns=..., turn_complete=True)` is explicitly documented as "non-realtime,
turn based content" where "the model will reply immediately" once
`turn_complete=True` — exactly what a confirmation readback needs. `speak()`
now uses `send_client_content`. Also adopts the reference's model name
(`gemini-3.1-flash-live-preview`) — confirmed present in this key's own
`client.models.list()` output with `bidiGenerateContent` support, replacing
this file's previous placeholder ("confirmar variante Live disponible al
implementar").

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

PTT HANGS FOREVER WITH AUTOMATIC VAD (confirmed 2026-07-25, live, via a real
browser holding the VoiceButton with a synthetic mic input): `handle_ptt_stop()`
(session.py) waits on `receive()` for a FINAL transcript event, which only
gets pushed when Gemini's `turn_complete` fires. With `automatic_activity_
detection` (silence-based VAD) enabled, `turn_complete` depends on Gemini
observing a gap of silence *within a continuing audio stream*. But a real
PTT flow doesn't produce that: the moment the operator releases the button,
`audioCapture.ts` stops the mic entirely — no more chunks, silent or
otherwise, ever arrive. Gemini has nothing to notice a "gap" in, so
automatic VAD's end-of-turn condition can go unmet indefinitely (confirmed:
a live PTT cycle hung >20s with zero server response, while a raw diagnostic
that kept the stream open and fed trailing silence chunks got `turn_complete`
in a couple of seconds — the difference was the continued stream, not
anything about the audio content). Fixed by disabling automatic VAD
(`AutomaticActivityDetection(disabled=True)`) and driving turn boundaries
explicitly instead: `start_of_speech()`/`end_of_speech()` send `activity_
start`/`activity_end`, called from `session.py`'s `handle_ptt_start`/
`handle_ptt_stop` — PTT already knows exactly when speech starts and stops,
so there's no reason to make Gemini guess.

SECOND UTTERANCE HANGS ON A REUSED CONNECTION (confirmed 2026-07-25, live
and reproduced in isolation): manual activity-detection mode doesn't
reliably support a second start_of_speech()/end_of_speech() turn on a
connection already used for one — the SAME audio that transcribes
correctly on a fresh connection just hangs forever (no transcript, no
error) on a reused one. `session.py`'s `_reconnect_provider` now tears down
and reconnects for every utterance instead of reusing one connection for
the whole PTT session. That in turn surfaced THIS bug: reconnecting called
`disconnect()` then `connect()` on the same `GeminiLiveSTTProvider`
instance, but `connect()` never reset `_transcript_queue`/`_audio_queue` —
so a `None` sentinel left over from the previous connection's cancelled
`_drain_task` (pushed in its `finally` block) sat at the front of the
queue and got consumed by the NEXT utterance's `receive()` instead of its
real transcript, producing silent hangs or spurious "STT_UNAVAILABLE"
errors depending on timing. Fixed by having `connect()` always create
fresh queues/flags, making this instance safe to disconnect-then-reconnect
repeatedly.

AUDIO-LESS TURN FLAKINESS (confirmed 2026-07-25, root-caused with a real
billed key): `speak()` initially appeared to never deliver audio through
`receive_audio()`. Bypassing this class entirely with a raw diagnostic
script proved the SDK/config are correct — the SAME connection, SAME
`send_client_content` call, run 10 times back-to-back, produced a full
~21-message response (real `inline_data` PCM chunks) in 6 runs and, in the
other 4, only 4 messages: `output_transcription` (the full text, as a
single non-streamed chunk) immediately followed by `generation_complete`
and `turn_complete` — `usage_metadata` confirms 0 audio response tokens
were generated that turn. This is the Gemini preview model itself
sometimes silently skipping audio synthesis for a turn, not a bug in this
file's single-reader `_drain()` loop (which was the original suspect and
is confirmed innocent — it faithfully receives however many messages
Gemini actually sends). Fixed with a bounded retry in `speak()`: resend
the same turn if it completes with zero audio bytes received.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import AsyncIterator

from google import genai
from google.genai import types

from app.agents.voice.schemas import SessionConfig, TranscriptEvent, TranscriptEventType
from app.agents.voice.stt_provider import STTProvider
from app.config import settings

logger = logging.getLogger(__name__)

MODEL_NAME = "gemini-3.1-flash-live-preview"  # ADR-001 — from a confirmed-working reference (see module docstring)

# speak() retry tuning — see "AUDIO-LESS TURN FLAKINESS" in the module docstring.
_SPEAK_MAX_ATTEMPTS = 3
_SPEAK_TURN_TIMEOUT_SECONDS = 8.0

# Keeps the model a pure text-to-speech reader for our own confirmation
# strings, not a chatty assistant — the browser-side reference this was
# adapted from used a conversational persona, which is wrong for our use
# case: the operator needs to hear exactly the digit-by-digit confirmation
# text, not Gemini's own improvised reply to it.
#
# DELIBERATELY SHORT (confirmed empirically 2026-07-25): a longer, more
# heavily-qualified version of this instruction ("de forma clara y natural,
# EXACTAMENTE como te lo dan — sin agregar saludos, comentarios, preguntas
# ni interpretación propia. No converses...") measurably made the model
# skip audio synthesis and return only a text transcription — a controlled
# A/B (3 short vs. 3 long, interleaved, same turn text) showed the long
# version failing to produce audio in 2/3 turns vs. 0/3 for this shorter
# one, and 5/5 clean runs with this exact wording. Keep this short; treat
# any future edit to it as a change that needs the same kind of empirical
# re-verification, not just a read-through.
TTS_SYSTEM_INSTRUCTION = (
    "Lee en voz alta, exactamente como te lo dan, el siguiente mensaje. "
    "No respondas ni agregues nada mas."
)


class GeminiLiveSTTProvider(STTProvider):
    def __init__(self) -> None:
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._session_cm = None
        self._session = None
        self._transcript_queue: asyncio.Queue[TranscriptEvent | None] = asyncio.Queue()
        self._audio_queue: asyncio.Queue[str] = asyncio.Queue()
        self._drain_task: asyncio.Task[None] | None = None
        # Per-turn bookkeeping for speak()'s retry-on-silent-turn logic
        # (see module docstring, "AUDIO-LESS TURN FLAKINESS").
        self._turn_complete_event: asyncio.Event = asyncio.Event()
        self._turn_had_audio: bool = False

    async def connect(self, session_config: SessionConfig) -> None:
        # Fresh per-connection state. This instance is reused across
        # multiple ptt_start cycles within one WS session (session.py's
        # `_reconnect_provider` calls disconnect() then connect() on the
        # SAME object, since a fresh connection is required per utterance —
        # see "SECOND UTTERANCE HANGS" below). Without resetting these, a
        # `None` sentinel left over from the previous connection's
        # cancelled `_drain_task` (pushed in its `finally` block) sits at
        # the front of the queue and gets consumed by the NEXT utterance's
        # `receive()` call instead of its real transcript — confirmed live:
        # this produced both silent hangs and "STT_UNAVAILABLE" errors
        # inconsistently depending on timing, until this fix.
        self._transcript_queue = asyncio.Queue()
        self._audio_queue = asyncio.Queue()
        self._turn_complete_event = asyncio.Event()
        self._turn_had_audio = False

        live_config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=TTS_SYSTEM_INSTRUCTION,
            speech_config=types.SpeechConfig(
                language_code=session_config.language_code,
            ),
            # Automatic VAD is disabled — see "PTT HANGS FOREVER" in the
            # module docstring. `session.py`'s handle_ptt_start/handle_ptt_stop
            # drive turn boundaries explicitly via start_of_speech()/
            # end_of_speech() below instead.
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(disabled=True),
            ),
            # Required or the server never sends input_transcription at all.
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
        )
        self._session_cm = self._client.aio.live.connect(model=MODEL_NAME, config=live_config)
        self._session = await self._session_cm.__aenter__()
        logger.info("gemini_live: connect() done, session_id=%s", getattr(self._session, "session_id", None))
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
                        self._turn_had_audio = True
                        await self._audio_queue.put(base64.b64encode(raw).decode("ascii"))

                if getattr(server_content, "turn_complete", False):
                    logger.info("gemini_live: input_transcription final=%r", accumulated_text)
                    await self._transcript_queue.put(
                        TranscriptEvent(type=TranscriptEventType.FINAL, text=accumulated_text, confidence=None)
                    )
                    accumulated_text = ""
                    self._turn_complete_event.set()
        finally:
            await self._transcript_queue.put(None)

    async def start_of_speech(self) -> None:
        if self._session is None:
            raise RuntimeError("call connect() before start_of_speech()")
        logger.info("gemini_live: sending activity_start")
        await self._session.send_realtime_input(activity_start=types.ActivityStart())
        logger.info("gemini_live: activity_start sent OK")

    async def send_audio(self, chunk: bytes, sample_rate: int) -> None:
        if self._session is None:
            raise RuntimeError("call connect() before send_audio()")
        await self._session.send_realtime_input(
            audio=types.Blob(data=chunk, mime_type=f"audio/pcm;rate={sample_rate}")
        )

    async def end_of_speech(self) -> None:
        if self._session is None:
            raise RuntimeError("call connect() before end_of_speech()")
        await self._session.send_realtime_input(activity_end=types.ActivityEnd())

    async def speak(self, text: str) -> None:
        """Sends `text` as a turn for Gemini to read aloud. Retries the same
        turn (up to `_SPEAK_MAX_ATTEMPTS` times) if it completes without
        producing any audio — see module docstring, "AUDIO-LESS TURN
        FLAKINESS": the model occasionally completes a turn with only a
        text transcription and zero audio response tokens."""
        if self._session is None:
            raise RuntimeError("call connect() before speak()")

        for attempt in range(1, _SPEAK_MAX_ATTEMPTS + 1):
            self._turn_complete_event.clear()
            self._turn_had_audio = False
            await self._session.send_client_content(
                turns=types.Content(role="user", parts=[types.Part(text=text)]),
                turn_complete=True,
            )
            try:
                await asyncio.wait_for(self._turn_complete_event.wait(), timeout=_SPEAK_TURN_TIMEOUT_SECONDS)
            except TimeoutError:
                return
            if self._turn_had_audio or attempt == _SPEAK_MAX_ATTEMPTS:
                return

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
