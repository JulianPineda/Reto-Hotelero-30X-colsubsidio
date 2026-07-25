from enum import StrEnum
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel


class EventType(StrEnum):
    ITEM_CREATED = "ItemCreated"
    ITEM_CORRECTED = "ItemCorrected"
    ITEM_DELETED = "ItemDeleted"
    ITEM_VALIDATED = "ItemValidated"
    ITEM_REJECTED = "ItemRejected"


class ItemCreatedPayload(BaseModel):
    oracle_code: str | None
    article_name: str
    quantity: float
    unit: str
    homologation_score: float | None
    sin_homologar: bool
    confidence_stt: float | None
    is_offline: bool = False


class ItemCorrectedPayload(BaseModel):
    old_oracle_code: str | None
    new_oracle_code: str | None
    old_quantity: float
    new_quantity: float
    correction_source: str  # "voice_command" | "supervisor_override"


class ItemDeletedPayload(BaseModel):
    oracle_code: str | None
    quantity: float
    deletion_source: str  # "voice_command" | "supervisor_reject"


class ItemValidatedPayload(BaseModel):
    oracle_code: str
    quantity: float
    unit: str
    validated_by: str  # "auditor_agent" | "supervisor"
    flag_type: str | None = None


class ItemRejectedPayload(BaseModel):
    oracle_code: str | None
    quantity: float
    flag_type: str  # threshold | trend | both
    flag_reason: str
    historical_counts: list[float]
    deviation_pct: float | None
