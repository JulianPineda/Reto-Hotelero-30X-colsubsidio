import asyncio
import uuid
from collections.abc import AsyncIterator

from app.agents.parser import extractor
from app.agents.voice.schemas import SessionConfig, TranscriptEvent, TranscriptEventType
from app.agents.voice.session import VoicePTTSession, VoiceState
from app.agents.voice.stt_provider import STTProvider


class FakeSTTProvider(STTProvider):
    def __init__(self, events: list[TranscriptEvent], audio_chunks: list[str] | None = None):
        self._events = events
        self._audio_chunks = audio_chunks or []
        self.connected = False
        self.sent_chunks: list[bytes] = []
        self.disconnected = False
        self.spoken_texts: list[str] = []

    async def connect(self, session_config: SessionConfig) -> None:
        self.connected = True

    async def send_audio(self, chunk: bytes) -> None:
        self.sent_chunks.append(chunk)

    async def speak(self, text: str) -> None:
        self.spoken_texts.append(text)

    async def receive(self) -> AsyncIterator[TranscriptEvent]:
        for event in self._events:
            yield event

    async def receive_audio(self) -> AsyncIterator[str]:
        for chunk in self._audio_chunks:
            yield chunk

    async def disconnect(self) -> None:
        self.disconnected = True


def _session_config() -> SessionConfig:
    return SessionConfig(session_id=uuid.uuid4(), operator_id="OP-1")


async def test_ptt_start_transitions_to_listening_and_connects():
    stt = FakeSTTProvider(events=[])
    session = VoicePTTSession(stt_provider=stt, session_config=_session_config())

    response = await session.handle_ptt_start()

    assert response == {"type": "listening"}
    assert session.state == VoiceState.LISTENING
    assert stt.connected is True


async def test_audio_chunk_forwarded_only_while_listening():
    stt = FakeSTTProvider(events=[])
    session = VoicePTTSession(stt_provider=stt, session_config=_session_config())

    await session.handle_audio_chunk(b"ignored-while-idle")
    assert stt.sent_chunks == []

    await session.handle_ptt_start()
    await session.handle_audio_chunk(b"chunk-1")
    assert stt.sent_chunks == [b"chunk-1"]


async def test_ptt_stop_with_high_confidence_moves_to_confirming(monkeypatch):
    events = [TranscriptEvent(type=TranscriptEventType.FINAL, text="veinte kilos de sal", confidence=0.9)]
    stt = FakeSTTProvider(events=events)
    session = VoicePTTSession(stt_provider=stt, session_config=_session_config())
    await session.handle_ptt_start()

    async def fake_extract(transcript: str):
        return extractor._LLMExtraction(article="sal", quantity=20.0, unit="kilos")

    monkeypatch.setattr(extractor, "extract", fake_extract)

    response = await session.handle_ptt_stop()

    assert response["type"] == "confirmation_request"
    assert response["article"] == "sal"
    assert response["quantity"] == 20.0
    assert response["unit"] == "kg"
    assert session.state == VoiceState.CONFIRMING
    assert session.pending_item is not None


async def test_ptt_stop_with_low_confidence_asks_to_repeat():
    events = [TranscriptEvent(type=TranscriptEventType.FINAL, text="algo", confidence=0.5)]
    stt = FakeSTTProvider(events=events)
    session = VoicePTTSession(stt_provider=stt, session_config=_session_config())
    await session.handle_ptt_start()

    response = await session.handle_ptt_stop()

    assert response["type"] == "low_confidence"
    assert response["attempt"] == 1
    assert session.state == VoiceState.IDLE


async def test_three_low_confidence_attempts_offers_manual_fallback():
    session = VoicePTTSession(stt_provider=FakeSTTProvider(events=[]), session_config=_session_config())

    response = {}
    for _ in range(3):
        session.stt_provider._events = [
            TranscriptEvent(type=TranscriptEventType.FINAL, text="algo", confidence=0.5)
        ]
        await session.handle_ptt_start()
        response = await session.handle_ptt_stop()

    assert response == {"type": "manual_fallback_offered"}


async def test_confirm_true_saves_item_and_returns_to_idle(monkeypatch):
    events = [TranscriptEvent(type=TranscriptEventType.FINAL, text="veinte kilos de sal", confidence=0.9)]
    stt = FakeSTTProvider(events=events)
    session = VoicePTTSession(stt_provider=stt, session_config=_session_config())
    await session.handle_ptt_start()

    async def fake_extract(transcript: str):
        return extractor._LLMExtraction(article="sal", quantity=20.0, unit="kilos")

    monkeypatch.setattr(extractor, "extract", fake_extract)
    await session.handle_ptt_stop()

    response = await session.handle_confirm(True)

    assert response["type"] == "item_saved"
    assert session.state == VoiceState.IDLE
    assert session.pending_item is None


async def test_confirm_true_uses_injected_persist_item_result(monkeypatch):
    events = [TranscriptEvent(type=TranscriptEventType.FINAL, text="veinte kilos de sal", confidence=0.9)]
    stt = FakeSTTProvider(events=events)

    async def fake_persist_item(item):
        return {
            "ok": True,
            "item_id": "11111111-1111-1111-1111-111111111111",
            "is_flagged": True,
            "flag_type": "threshold",
            "traffic_light": None,
            "sequence": 7,
        }

    session = VoicePTTSession(stt_provider=stt, session_config=_session_config(), persist_item=fake_persist_item)
    await session.handle_ptt_start()

    async def fake_extract(transcript: str):
        return extractor._LLMExtraction(article="sal", quantity=20.0, unit="kilos")

    monkeypatch.setattr(extractor, "extract", fake_extract)
    await session.handle_ptt_stop()

    response = await session.handle_confirm(True)

    assert response == {
        "type": "item_saved",
        "item_id": "11111111-1111-1111-1111-111111111111",
        "expiry_date": None,
        "is_flagged": True,
        "flag_type": "threshold",
        "traffic_light": None,
        "sequence": 7,
    }


async def test_confirm_true_surfaces_persist_item_failure_as_error(monkeypatch):
    events = [TranscriptEvent(type=TranscriptEventType.FINAL, text="veinte kilos de sal", confidence=0.9)]
    stt = FakeSTTProvider(events=events)

    async def failing_persist_item(item):
        return {"ok": False, "code": "SESSION_NOT_FOUND", "message": "La sesión de conteo no existe."}

    session = VoicePTTSession(
        stt_provider=stt, session_config=_session_config(), persist_item=failing_persist_item
    )
    await session.handle_ptt_start()

    async def fake_extract(transcript: str):
        return extractor._LLMExtraction(article="sal", quantity=20.0, unit="kilos")

    monkeypatch.setattr(extractor, "extract", fake_extract)
    await session.handle_ptt_stop()

    response = await session.handle_confirm(True)

    assert response == {
        "type": "error",
        "code": "SESSION_NOT_FOUND",
        "message": "La sesión de conteo no existe.",
    }
    # A failed persist doesn't leave the session stuck mid-flow.
    assert session.pending_item is None
    assert session.state == VoiceState.IDLE


async def test_confirm_false_returns_to_listening_for_redictation(monkeypatch):
    events = [TranscriptEvent(type=TranscriptEventType.FINAL, text="veinte kilos de sal", confidence=0.9)]
    stt = FakeSTTProvider(events=events)
    session = VoicePTTSession(stt_provider=stt, session_config=_session_config())
    await session.handle_ptt_start()

    async def fake_extract(transcript: str):
        return extractor._LLMExtraction(article="sal", quantity=20.0, unit="kilos")

    monkeypatch.setattr(extractor, "extract", fake_extract)
    await session.handle_ptt_stop()

    response = await session.handle_confirm(False)

    assert response == {"type": "listening"}
    assert session.state == VoiceState.LISTENING
    assert session.pending_item is None


async def test_barge_in_interrupts_and_returns_to_listening():
    session = VoicePTTSession(stt_provider=FakeSTTProvider(events=[]), session_config=_session_config())
    session.state = VoiceState.CONFIRMING

    response = await session.handle_barge_in()

    assert response == {"type": "listening"}
    assert session.state == VoiceState.LISTENING


async def test_close_disconnects_only_if_connected():
    stt = FakeSTTProvider(events=[])
    session = VoicePTTSession(stt_provider=stt, session_config=_session_config())

    await session.close()
    assert stt.disconnected is False

    await session.handle_ptt_start()
    await session.close()
    assert stt.disconnected is True


async def _homologate_perishable(article: str) -> dict:
    return {"oracle_code": "LAC-001", "name": "Leche Entera 1L", "is_perishable": True, "sin_homologar": False}


async def test_perishable_item_is_asked_for_expiry_date_instead_of_confirming(monkeypatch):
    events = [TranscriptEvent(type=TranscriptEventType.FINAL, text="dos litros de leche", confidence=0.9)]
    stt = FakeSTTProvider(events=events)
    session = VoicePTTSession(
        stt_provider=stt, session_config=_session_config(), homologate=_homologate_perishable
    )
    await session.handle_ptt_start()

    async def fake_extract(transcript: str):
        return extractor._LLMExtraction(article="leche", quantity=2.0, unit="litros")

    monkeypatch.setattr(extractor, "extract", fake_extract)

    response = await session.handle_ptt_stop()

    assert response["type"] == "expiry_date_request"
    assert session.state == VoiceState.AWAITING_EXPIRY_DATE
    assert session.pending_item is not None
    assert session.pending_item.oracle_code == "LAC-001"


async def test_expiry_date_transcript_parsed_leads_to_date_confirmation(monkeypatch):
    events = [TranscriptEvent(type=TranscriptEventType.FINAL, text="dos litros de leche", confidence=0.9)]
    stt = FakeSTTProvider(events=events)
    session = VoicePTTSession(
        stt_provider=stt, session_config=_session_config(), homologate=_homologate_perishable
    )
    await session.handle_ptt_start()

    async def fake_extract(transcript: str):
        return extractor._LLMExtraction(article="leche", quantity=2.0, unit="litros")

    monkeypatch.setattr(extractor, "extract", fake_extract)
    await session.handle_ptt_stop()

    stt._events = [
        TranscriptEvent(type=TranscriptEventType.FINAL, text="quince de agosto de 2026", confidence=0.9)
    ]
    response = await session.handle_ptt_stop()

    assert response["type"] == "expiry_date_confirmation_request"
    assert response["expiry_date"] == "2026-08-15"
    assert session.state == VoiceState.CONFIRMING_EXPIRY_DATE


async def test_expiry_date_transcript_unparseable_reasks_for_date(monkeypatch):
    events = [TranscriptEvent(type=TranscriptEventType.FINAL, text="dos litros de leche", confidence=0.9)]
    stt = FakeSTTProvider(events=events)
    session = VoicePTTSession(
        stt_provider=stt, session_config=_session_config(), homologate=_homologate_perishable
    )
    await session.handle_ptt_start()

    async def fake_extract(transcript: str):
        return extractor._LLMExtraction(article="leche", quantity=2.0, unit="litros")

    monkeypatch.setattr(extractor, "extract", fake_extract)
    await session.handle_ptt_stop()

    stt._events = [TranscriptEvent(type=TranscriptEventType.FINAL, text="mmm no se", confidence=0.9)]
    response = await session.handle_ptt_stop()

    assert response["type"] == "error"
    assert response["code"] == "DATE_PARSE_FAILED"
    assert session.state == VoiceState.AWAITING_EXPIRY_DATE
    assert session.pending_item is not None


async def test_confirming_expiry_date_true_proceeds_to_quantity_confirmation(monkeypatch):
    events = [TranscriptEvent(type=TranscriptEventType.FINAL, text="dos litros de leche", confidence=0.9)]
    stt = FakeSTTProvider(events=events)
    session = VoicePTTSession(
        stt_provider=stt, session_config=_session_config(), homologate=_homologate_perishable
    )
    await session.handle_ptt_start()

    async def fake_extract(transcript: str):
        return extractor._LLMExtraction(article="leche", quantity=2.0, unit="litros")

    monkeypatch.setattr(extractor, "extract", fake_extract)
    await session.handle_ptt_stop()

    stt._events = [
        TranscriptEvent(type=TranscriptEventType.FINAL, text="quince de agosto de 2026", confidence=0.9)
    ]
    await session.handle_ptt_stop()

    response = await session.handle_confirm(True)

    assert response["type"] == "confirmation_request"
    assert response["expiry_date"] == "2026-08-15"
    assert session.state == VoiceState.CONFIRMING


async def test_confirming_expiry_date_false_reasks_for_date(monkeypatch):
    events = [TranscriptEvent(type=TranscriptEventType.FINAL, text="dos litros de leche", confidence=0.9)]
    stt = FakeSTTProvider(events=events)
    session = VoicePTTSession(
        stt_provider=stt, session_config=_session_config(), homologate=_homologate_perishable
    )
    await session.handle_ptt_start()

    async def fake_extract(transcript: str):
        return extractor._LLMExtraction(article="leche", quantity=2.0, unit="litros")

    monkeypatch.setattr(extractor, "extract", fake_extract)
    await session.handle_ptt_stop()

    stt._events = [
        TranscriptEvent(type=TranscriptEventType.FINAL, text="quince de agosto de 2026", confidence=0.9)
    ]
    await session.handle_ptt_stop()

    response = await session.handle_confirm(False)

    assert response["type"] == "expiry_date_request"
    assert session.state == VoiceState.AWAITING_EXPIRY_DATE
    assert session.pending_item.expiry_date is None


async def test_item_saved_includes_expiry_date_for_perishables(monkeypatch):
    events = [TranscriptEvent(type=TranscriptEventType.FINAL, text="dos litros de leche", confidence=0.9)]
    stt = FakeSTTProvider(events=events)
    session = VoicePTTSession(
        stt_provider=stt, session_config=_session_config(), homologate=_homologate_perishable
    )
    await session.handle_ptt_start()

    async def fake_extract(transcript: str):
        return extractor._LLMExtraction(article="leche", quantity=2.0, unit="litros")

    monkeypatch.setattr(extractor, "extract", fake_extract)
    await session.handle_ptt_stop()

    stt._events = [
        TranscriptEvent(type=TranscriptEventType.FINAL, text="quince de agosto de 2026", confidence=0.9)
    ]
    await session.handle_ptt_stop()
    await session.handle_confirm(True)

    response = await session.handle_confirm(True)

    assert response["type"] == "item_saved"
    assert response["expiry_date"] == "2026-08-15"
    assert session.state == VoiceState.IDLE


async def test_audio_relay_forwards_chunks_to_the_injected_callback():
    stt = FakeSTTProvider(events=[], audio_chunks=["chunk-1", "chunk-2"])
    received: list[str] = []

    async def on_audio_chunk(chunk_b64: str) -> None:
        received.append(chunk_b64)

    session = VoicePTTSession(
        stt_provider=stt, session_config=_session_config(), on_audio_chunk=on_audio_chunk
    )
    await session.handle_ptt_start()

    assert session._audio_relay_task is not None
    await session._audio_relay_task

    assert received == ["chunk-1", "chunk-2"]


async def test_close_cancels_the_audio_relay_task():
    stt = FakeSTTProvider(events=[], audio_chunks=[])
    session = VoicePTTSession(stt_provider=stt, session_config=_session_config())
    await session.handle_ptt_start()

    relay_task = session._audio_relay_task
    assert relay_task is not None

    await session.close()

    # Either already finished (empty audio_chunks) or cancelled by close() —
    # either way it must not still be running after close().
    await asyncio.sleep(0)
    assert relay_task.done()


async def test_quantity_confirmation_speaks_the_display_text(monkeypatch):
    events = [TranscriptEvent(type=TranscriptEventType.FINAL, text="veinte kilos de sal", confidence=0.9)]
    stt = FakeSTTProvider(events=events)
    session = VoicePTTSession(stt_provider=stt, session_config=_session_config())
    await session.handle_ptt_start()

    async def fake_extract(transcript: str):
        return extractor._LLMExtraction(article="sal", quantity=20.0, unit="kilos")

    monkeypatch.setattr(extractor, "extract", fake_extract)
    response = await session.handle_ptt_stop()

    assert stt.spoken_texts == [response["display_text"]]


async def test_expiry_date_request_speaks_the_question(monkeypatch):
    events = [TranscriptEvent(type=TranscriptEventType.FINAL, text="dos litros de leche", confidence=0.9)]
    stt = FakeSTTProvider(events=events)
    session = VoicePTTSession(
        stt_provider=stt, session_config=_session_config(), homologate=_homologate_perishable
    )
    await session.handle_ptt_start()

    async def fake_extract(transcript: str):
        return extractor._LLMExtraction(article="leche", quantity=2.0, unit="litros")

    monkeypatch.setattr(extractor, "extract", fake_extract)
    response = await session.handle_ptt_stop()

    assert stt.spoken_texts == [response["message"]]


async def test_expiry_date_confirmation_speaks_the_display_text(monkeypatch):
    events = [TranscriptEvent(type=TranscriptEventType.FINAL, text="dos litros de leche", confidence=0.9)]
    stt = FakeSTTProvider(events=events)
    session = VoicePTTSession(
        stt_provider=stt, session_config=_session_config(), homologate=_homologate_perishable
    )
    await session.handle_ptt_start()

    async def fake_extract(transcript: str):
        return extractor._LLMExtraction(article="leche", quantity=2.0, unit="litros")

    monkeypatch.setattr(extractor, "extract", fake_extract)
    await session.handle_ptt_stop()  # speaks the expiry_date_request question

    stt._events = [
        TranscriptEvent(type=TranscriptEventType.FINAL, text="quince de agosto de 2026", confidence=0.9)
    ]
    response = await session.handle_ptt_stop()

    assert stt.spoken_texts[-1] == response["display_text"]
