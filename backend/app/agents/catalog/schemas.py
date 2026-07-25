from uuid import UUID

from pydantic import BaseModel, Field


class HomologateRequest(BaseModel):
    article: str = Field(min_length=1, max_length=300)
    warehouse_id: UUID
    unit_hint: str | None = None


class Alternative(BaseModel):
    oracle_code: str
    name: str
    score: float


class HomologateResult(BaseModel):
    oracle_code: str | None
    name: str | None
    unit: str | None
    score: float
    is_perishable: bool | None
    match_method: str  # vector_search | fuzzy_fallback | none
    alternatives: list[Alternative]
    requires_operator_selection: bool
    sin_homologar: bool


class CatalogFeedbackRequest(BaseModel):
    raw_article: str = Field(min_length=1, max_length=300)
    oracle_code: str
    session_id: UUID
    operator_id: str


class CatalogFeedbackResponse(BaseModel):
    synonym_created: bool
    qdrant_updated: bool
