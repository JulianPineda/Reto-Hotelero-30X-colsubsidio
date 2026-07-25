from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.agents.voice.schemas import SessionConfig, TranscriptEvent


class STTProvider(ABC):
    """Voice-engine abstraction (ADR-001, CLAUDE.md 1.1).

    The rest of the pipeline talks to this interface only — swapping the
    concrete adapter (Gemini Live, OpenAI Realtime, ...) never touches call
    sites in `router.py` / `session.py`.
    """

    @abstractmethod
    async def connect(self, session_config: SessionConfig) -> None: ...

    @abstractmethod
    async def send_audio(self, chunk: bytes) -> None: ...

    @abstractmethod
    async def receive(self) -> AsyncIterator[TranscriptEvent]: ...

    @abstractmethod
    async def speak(self, text: str) -> None:
        """Sends `text` to be read aloud (TTS) — the hands-free confirmation
        readback CLAUDE.md §4 implies and EPIC-2-voice.md's state machine
        names directly ("interrumpir TTS" on barge-in). Audio arrives
        asynchronously via `receive_audio()`, not as a return value here."""
        ...

    @abstractmethod
    async def receive_audio(self) -> AsyncIterator[str]:
        """Base64-encoded PCM16 audio chunks synthesized in response to
        `speak()` calls — a stream independent from `receive()`'s
        transcript events, since a provider's underlying connection may
        interleave both on one wire (see gemini_live.py)."""
        ...

    @abstractmethod
    async def disconnect(self) -> None: ...
