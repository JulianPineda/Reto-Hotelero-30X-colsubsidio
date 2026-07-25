import uuid
from collections.abc import AsyncIterator

from app.agents.parser import extractor
from app.agents.voice.schemas import SessionConfig, TranscriptEvent, TranscriptEventType
from app.agents.voice.session import VoicePTTSession, VoiceState
from app.agents.voice.stt_provider import STTProvider


class FakeSTTProvider(STTProvider):
    def __init__(self, events: list[TranscriptEvent]):
        self._events = events
        self.connected = False
        self.sent_chunks: list[bytes] = []
        self.disconnected = False

    async def connect(self, session_config: SessionConfig) -> None:
        self.connected = True

    async def send_audio(self, chunk: bytes) -> None:
        self.sent_chunks.append(chunk)

    async def receive(self) -> AsyncIterator[TranscriptEvent]:
        for event in self._events:
            yield event

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
