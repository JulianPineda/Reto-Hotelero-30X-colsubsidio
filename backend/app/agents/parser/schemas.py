from uuid import UUID

from pydantic import BaseModel, Field


class ParseRequest(BaseModel):
    transcript: str = Field(
        min_length=1,
        max_length=500,
        pattern=r"^[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ0-9\s\.,\-]+$",
    )
    session_id: UUID
    language: str = Field(default="es-CO", pattern=r"^[a-z]{2}-[A-Z]{2}$")


class ParseResponse(BaseModel):
    article: str | None
    quantity: float | None
    unit: str | None
    confidence: float
    raw_tokens: list[str]
