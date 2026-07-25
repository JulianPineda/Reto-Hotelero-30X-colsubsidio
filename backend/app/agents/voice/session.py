"""PTT state machine + barge-in for one voice WebSocket connection.

Orchestrates: audio -> STTProvider -> Parser Agent -> digit-by-digit
confirmation. Catalog Agent homologation (T-009) and Auditor Agent anomaly
flagging (EPIC-4) don't exist yet — `homologate` is where the Catalog Agent
plugs in; until then it's a pass-through that never homologates and never
flags (matches this ticket's own "funciona end-to-end con payload mock"
acceptance criterion).

State machine (EPIC-2-voice.md T-006):
    idle -> listening (ptt_start)
    listening -> processing (ptt_stop)
    processing -> confirming (transcript ready + confidence >= threshold)
    processing -> idle (confidence < threshold -> pide repetir)
    confirming -> idle (confirm=true -> item saved)
    confirming -> listening (confirm=false -> re-dictar)
    confirming -> listening (barge_in -> interrumpir TTS)
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID, uuid4

from app.agents.parser import extractor
from app.agents.parser.unit_normalizer import normalize_unit
from app.agents.voice.confirmation import build_digit_confirmation
from app.agents.voice.schemas import SessionConfig, TranscriptEventType
from app.agents.voice.stt_provider import STTProvider
from app.config import settings

MAX_LOW_CONFIDENCE_ATTEMPTS = 3


class VoiceState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    CONFIRMING = "confirming"


@dataclass
class PendingItem:
    item_id: UUID
    article: str
    quantity: float
    unit: str


HomologateFn = Callable[[str], Awaitable[dict]]


async def _default_homologate(article: str) -> dict:
    """Stand-in until the Catalog Agent (T-009) exists."""
    return {"oracle_code": None, "name": None, "sin_homologar": True}


class VoicePTTSession:
    def __init__(
        self,
        stt_provider: STTProvider,
        session_config: SessionConfig,
        homologate: HomologateFn = _default_homologate,
    ) -> None:
        self.stt_provider = stt_provider
        self.session_config = session_config
        self.homologate = homologate
        self.state = VoiceState.IDLE
        self.low_confidence_attempts = 0
        self.pending_item: PendingItem | None = None
        self._connected = False

    async def handle_ptt_start(self) -> dict:
        if not self._connected:
            await self.stt_provider.connect(self.session_config)
            self._connected = True
        self.state = VoiceState.LISTENING
        return {"type": "listening"}

    async def handle_audio_chunk(self, data: bytes) -> None:
        if self.state != VoiceState.LISTENING:
            return
        await self.stt_provider.send_audio(data)

    async def handle_ptt_stop(self) -> dict:
        self.state = VoiceState.PROCESSING

        final_text: str | None = None
        final_confidence = 0.0
        async for event in self.stt_provider.receive():
            if event.type == TranscriptEventType.FINAL:
                final_text = event.text
                final_confidence = event.confidence or 0.0
                break

        if final_text is None:
            self.state = VoiceState.IDLE
            return {
                "type": "error",
                "code": "STT_UNAVAILABLE",
                "message": "Error interno de procesamiento de voz.",
            }

        if final_confidence < settings.stt_confidence_threshold:
            self.low_confidence_attempts += 1
            self.state = VoiceState.IDLE
            if self.low_confidence_attempts >= MAX_LOW_CONFIDENCE_ATTEMPTS:
                return {"type": "manual_fallback_offered"}
            return {
                "type": "low_confidence",
                "confidence": final_confidence,
                "attempt": self.low_confidence_attempts,
                "max_attempts": MAX_LOW_CONFIDENCE_ATTEMPTS,
            }

        self.low_confidence_attempts = 0
        return await self._parse_and_confirm(final_text)

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
        self.pending_item = PendingItem(item_id=item_id, article=article_name, quantity=quantity, unit=unit)
        self.state = VoiceState.CONFIRMING

        digit_by_digit, display_text = build_digit_confirmation(quantity, unit, article_name)
        return {
            "type": "confirmation_request",
            "item_id": str(item_id),
            "oracle_code": homologation.get("oracle_code"),
            "article": article_name,
            "quantity": quantity,
            "unit": unit,
            "digit_by_digit": digit_by_digit,
            "display_text": display_text,
        }

    async def handle_confirm(self, value: bool) -> dict:
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
            # sequence: real persistence (CountItem row + event store) is
            # the Orchestrator's job — not built yet, so no real sequence
            # number exists here.
            return {"type": "item_saved", "item_id": str(item.item_id), "is_flagged": False, "sequence": None}

        self.pending_item = None
        self.state = VoiceState.LISTENING
        return {"type": "listening"}

    async def handle_barge_in(self) -> dict:
        self.state = VoiceState.LISTENING
        return {"type": "listening"}

    async def close(self) -> None:
        if self._connected:
            await self.stt_provider.disconnect()
            self._connected = False
