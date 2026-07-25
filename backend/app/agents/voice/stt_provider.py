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
    async def disconnect(self) -> None: ...
