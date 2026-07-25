from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


class SessionConfig(BaseModel):
    session_id: UUID
    operator_id: str
    language_code: str = "es-CO"
    sample_rate_hz: int = 16000


class TranscriptEventType(StrEnum):
    PARTIAL = "partial"
    FINAL = "final"
    ERROR = "error"


class TranscriptEvent(BaseModel):
    type: TranscriptEventType
    text: str | None = None
    confidence: float | None = None
    error_message: str | None = None


class OperatorClaims(BaseModel):
    operator_id: str
    warehouse_id: UUID | None = None
    exp: int | None = None
