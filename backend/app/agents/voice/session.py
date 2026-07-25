"""PTT state machine + barge-in for one voice WebSocket connection.

Orchestrates: audio -> STTProvider -> Parser Agent -> Catalog Agent
homologation -> (perishables re-ask, CLAUDE.md §3.6) -> digit-by-digit
confirmation -> Orchestrator persistence (Auditor Agent + CountItem row +
ItemCreated event, via the injected `persist_item` callback wrapping
`services/orchestrator.py::persist_count_item`).

State machine (EPIC-2-voice.md T-006, extended by T-017 for perishables):
    idle -> listening (ptt_start)
    listening -> processing (ptt_stop)
    processing -> confirming (transcript ready + confidence >= threshold,
                               item is NOT perishable)
    processing -> awaiting_expiry_date (transcript ready + confidence >=
                               threshold, Catalog Agent flagged is_perishable)
    processing -> idle (confidence < threshold -> pide repetir)
    awaiting_expiry_date -> confirming_expiry_date (spoken date parsed ok)
    awaiting_expiry_date -> awaiting_expiry_date (date could not be parsed
                               -> pide repetir la fecha)
    confirming_expiry_date -> confirming (confirm=true -> sigue a cantidad)
    confirming_expiry_date -> awaiting_expiry_date (confirm=false -> re-dictar fecha)
    confirming -> idle (confirm=true -> item saved)
    confirming -> listening (confirm=false -> re-dictar)
    confirming -> listening (barge_in -> interrumpir TTS)
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from uuid import UUID, uuid4

from app.agents.parser import extractor
from app.agents.parser.unit_normalizer import normalize_unit
from app.agents.voice.confirmation import build_digit_confirmation
from app.agents.voice.date_parser import build_spoken_date_confirmation, parse_spoken_date
from app.agents.voice.schemas import SessionConfig, TranscriptEventType
from app.agents.voice.stt_provider import STTProvider
from app.config import settings

MAX_LOW_CONFIDENCE_ATTEMPTS = 3


class VoiceState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    CONFIRMING = "confirming"
    AWAITING_EXPIRY_DATE = "awaiting_expiry_date"
    CONFIRMING_EXPIRY_DATE = "confirming_expiry_date"


@dataclass
class PendingItem:
    item_id: UUID
    article: str
    quantity: float
    unit: str
    oracle_code: str | None = None
    is_perishable: bool | None = None
    expiry_date: date | None = None


HomologateFn = Callable[[str], Awaitable[dict]]
PersistItemFn = Callable[["PendingItem"], Awaitable[dict]]
AudioChunkFn = Callable[[str], Awaitable[None]]


async def _default_on_audio_chunk(chunk_b64: str) -> None:
    """Stand-in for tests/dev — real wiring is `voice/router.py` forwarding
    each chunk to the browser as an `audio_out` WS message."""
    return None


async def _default_homologate(article: str) -> dict:
    """Stand-in for tests/dev — real wiring is `voice/router.py` passing a
    callable built around `catalog/router.py::run_homologation()`."""
    return {"oracle_code": None, "name": None, "is_perishable": None, "sin_homologar": True}


async def _default_persist_item(item: "PendingItem") -> dict:
    """Stand-in for tests/dev — real wiring is `voice/router.py` passing a
    callable built around `services/orchestrator.py::persist_count_item()`.
    Keeps the pre-persistence behavior (client-side id, nothing flagged, no
    real sequence) for any caller that doesn't inject a real one."""
    return {
        "ok": True,
        "item_id": str(item.item_id),
        "is_flagged": False,
        "flag_type": None,
        "traffic_light": None,
        "sequence": None,
    }


class VoicePTTSession:
    def __init__(
        self,
        stt_provider: STTProvider,
        session_config: SessionConfig,
        homologate: HomologateFn = _default_homologate,
        persist_item: PersistItemFn = _default_persist_item,
        on_audio_chunk: AudioChunkFn = _default_on_audio_chunk,
    ) -> None:
        self.stt_provider = stt_provider
        self.session_config = session_config
        self.homologate = homologate
        self.persist_item = persist_item
        self.on_audio_chunk = on_audio_chunk
        self.state = VoiceState.IDLE
        self.low_confidence_attempts = 0
        self.pending_item: PendingItem | None = None
        self._connected = False
        self._audio_relay_task: asyncio.Task[None] | None = None

    async def handle_ptt_start(self) -> dict:
        if not self._connected:
            await self.stt_provider.connect(self.session_config)
            self._connected = True
            self._audio_relay_task = asyncio.create_task(self._relay_audio_out())
        self.state = VoiceState.LISTENING
        return {"type": "listening"}

    async def _relay_audio_out(self) -> None:
        """Forwards TTS audio chunks (see `speak()` calls below) to
        whoever's listening — `voice/router.py` wires this to the browser's
        WS connection. Runs for the connection's lifetime, independent of
        the ptt_start/ptt_stop cycle, since TTS playback can still be
        streaming in after a `speak()` call returns."""
        async for chunk_b64 in self.stt_provider.receive_audio():
            await self.on_audio_chunk(chunk_b64)

    async def handle_audio_chunk(self, data: bytes) -> None:
        if self.state != VoiceState.LISTENING:
            return
        await self.stt_provider.send_audio(data)

    async def handle_ptt_stop(self) -> dict:
        previous_state = self.state
        self.state = VoiceState.PROCESSING

        final_text: str | None = None
        final_confidence: float | None = None
        async for event in self.stt_provider.receive():
            if event.type == TranscriptEventType.FINAL:
                final_text = event.text
                final_confidence = event.confidence
                break

        if final_text is None:
            self.state = self._retry_state(previous_state)
            return {
                "type": "error",
                "code": "STT_UNAVAILABLE",
                "message": "Error interno de procesamiento de voz.",
            }

        # confidence is None when the STTProvider can't score it at all (the
        # Gemini Live API adapter never can — see gemini_live.py) — treating
        # that as 0.0 would fail CLAUDE.md's G4 gate on every single
        # utterance. Providers that CAN score confidence (a future
        # OpenAIRealtimeAdapter, for instance) still get the gate enforced.
        # This is a stopgap, not a resolution — G4 as literally written
        # cannot be satisfied by the STT provider ADR-001 chose.
        if final_confidence is not None and final_confidence < settings.stt_confidence_threshold:
            self.low_confidence_attempts += 1
            self.state = self._retry_state(previous_state)
            if self.low_confidence_attempts >= MAX_LOW_CONFIDENCE_ATTEMPTS:
                return {"type": "manual_fallback_offered"}
            return {
                "type": "low_confidence",
                "confidence": final_confidence,
                "attempt": self.low_confidence_attempts,
                "max_attempts": MAX_LOW_CONFIDENCE_ATTEMPTS,
            }

        self.low_confidence_attempts = 0

        if previous_state == VoiceState.AWAITING_EXPIRY_DATE:
            return await self._handle_expiry_transcript(final_text)

        return await self._parse_and_confirm(final_text)

    @staticmethod
    def _retry_state(previous_state: VoiceState) -> VoiceState:
        """Where to land after an STT failure/low-confidence result — back
        to awaiting the expiry date if that's what we were listening for
        (keeps `pending_item` alive), otherwise idle as before."""
        if previous_state == VoiceState.AWAITING_EXPIRY_DATE:
            return VoiceState.AWAITING_EXPIRY_DATE
        return VoiceState.IDLE

    async def _parse_and_confirm(self, transcript: str) -> dict:
        raw = await extractor.extract(transcript)
        if raw.article is None and raw.quantity is None:
            self.state = VoiceState.IDLE
            return {
                "type": "error",
                "code": "PARSE_FAILED",
                "message": "No se pudo extraer artículo o cantidad del texto.",
            }

        unit = normalize_unit(raw.unit) or ""
        quantity = raw.quantity or 0.0
        homologation = (
            await self.homologate(raw.article) if raw.article else {"oracle_code": None, "name": None}
        )
        article_name = homologation.get("name") or raw.article or ""

        item_id = uuid4()
        self.pending_item = PendingItem(
            item_id=item_id,
            article=article_name,
            quantity=quantity,
            unit=unit,
            oracle_code=homologation.get("oracle_code"),
            is_perishable=homologation.get("is_perishable"),
        )

        if homologation.get("is_perishable"):
            self.state = VoiceState.AWAITING_EXPIRY_DATE
            message = f"¿Cuál es la fecha de vencimiento de {article_name}?"
            await self.stt_provider.speak(message)
            return {
                "type": "expiry_date_request",
                "item_id": str(item_id),
                "article": article_name,
                "message": message,
            }

        self.state = VoiceState.CONFIRMING
        return await self._build_quantity_confirmation(self.pending_item)

    async def _build_quantity_confirmation(self, item: PendingItem) -> dict:
        digit_by_digit, display_text = build_digit_confirmation(item.quantity, item.unit, item.article)
        await self.stt_provider.speak(display_text)
        return {
            "type": "confirmation_request",
            "item_id": str(item.item_id),
            "oracle_code": item.oracle_code,
            "article": item.article,
            "quantity": item.quantity,
            "unit": item.unit,
            "expiry_date": item.expiry_date.isoformat() if item.expiry_date else None,
            "digit_by_digit": digit_by_digit,
            "display_text": display_text,
        }

    async def _handle_expiry_transcript(self, transcript: str) -> dict:
        assert self.pending_item is not None  # guaranteed by the AWAITING_EXPIRY_DATE transition

        parsed = parse_spoken_date(transcript)
        if parsed is None:
            self.state = VoiceState.AWAITING_EXPIRY_DATE
            return {
                "type": "error",
                "code": "DATE_PARSE_FAILED",
                "message": "No se pudo entender la fecha de vencimiento. Por favor repítela.",
            }

        self.pending_item.expiry_date = parsed
        self.state = VoiceState.CONFIRMING_EXPIRY_DATE
        spoken = build_spoken_date_confirmation(parsed)
        display_text = f"¿Confirmas fecha de vencimiento: {spoken}?"
        await self.stt_provider.speak(display_text)
        return {
            "type": "expiry_date_confirmation_request",
            "item_id": str(self.pending_item.item_id),
            "expiry_date": parsed.isoformat(),
            "display_text": display_text,
        }

    async def handle_confirm(self, value: bool) -> dict:
        if self.state == VoiceState.CONFIRMING_EXPIRY_DATE:
            return await self._handle_expiry_confirm(value)

        if self.state != VoiceState.CONFIRMING or self.pending_item is None:
            return {
                "type": "error",
                "code": "INVALID_STATE",
                "message": "No hay ítem pendiente de confirmación.",
            }

        if value:
            item = self.pending_item
            self.pending_item = None
            self.state = VoiceState.IDLE

            result = await self.persist_item(item)
            if not result.get("ok", True):
                return {
                    "type": "error",
                    "code": result.get("code", "PERSIST_FAILED"),
                    "message": result.get("message", "No se pudo guardar el ítem."),
                }

            return {
                "type": "item_saved",
                "item_id": result["item_id"],
                "expiry_date": item.expiry_date.isoformat() if item.expiry_date else None,
                "is_flagged": result["is_flagged"],
                "flag_type": result.get("flag_type"),
                "traffic_light": result.get("traffic_light"),
                "sequence": result["sequence"],
            }

        self.pending_item = None
        self.state = VoiceState.LISTENING
        return {"type": "listening"}

    async def _handle_expiry_confirm(self, value: bool) -> dict:
        if self.pending_item is None:
            return {
                "type": "error",
                "code": "INVALID_STATE",
                "message": "No hay ítem pendiente de confirmación.",
            }

        if value:
            self.state = VoiceState.CONFIRMING
            return await self._build_quantity_confirmation(self.pending_item)

        self.pending_item.expiry_date = None
        self.state = VoiceState.AWAITING_EXPIRY_DATE
        message = f"¿Cuál es la fecha de vencimiento de {self.pending_item.article}?"
        await self.stt_provider.speak(message)
        return {
            "type": "expiry_date_request",
            "item_id": str(self.pending_item.item_id),
            "article": self.pending_item.article,
            "message": message,
        }

    async def handle_barge_in(self) -> dict:
        self.state = VoiceState.LISTENING
        return {"type": "listening"}

    async def close(self) -> None:
        if self._connected:
            if self._audio_relay_task is not None:
                self._audio_relay_task.cancel()
                self._audio_relay_task = None
            await self.stt_provider.disconnect()
            self._connected = False
