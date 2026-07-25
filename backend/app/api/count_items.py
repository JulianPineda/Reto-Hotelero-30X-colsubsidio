"""POST /api/v1/count-items — the REST face of the Orchestrator
(`services/orchestrator.py::persist_count_item`) for callers outside the
voice WS connection. Today that's exactly one caller: the frontend's
offline sync flow (`offlineSync.ts`), which already ran Catalog Agent
homologation client-side (it needs the result to decide whether an item
needs operator review) and hands the resolved fields here to actually
persist + run the Auditor Agent.
"""
from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.voice.schemas import OperatorClaims
from app.api.deps import get_current_operator
from app.database import get_db
from app.services.orchestrator import (
    PersistedCountItem,
    SessionNotFoundError,
    UnknownOracleCodeError,
    persist_count_item,
)
from app.services.perishables import PerishableItemMissingExpiryError

router = APIRouter(prefix="/count-items", tags=["count-items"])


class CreateCountItemRequest(BaseModel):
    session_id: UUID
    oracle_code: str | None = None
    article_name: str
    raw_transcript: str | None = None
    quantity: float
    unit: str
    homologation_score: float | None = None
    sin_homologar: bool = False
    expiry_date: date | None = None
    is_offline: bool = False
    confidence_stt: float | None = None


class CountItemResponse(BaseModel):
    item_id: UUID
    sequence_in_session: int
    is_flagged: bool
    flag_type: str | None
    flag_reason: str | None
    traffic_light: str | None

    @staticmethod
    def from_result(result: PersistedCountItem) -> "CountItemResponse":
        return CountItemResponse(
            item_id=result.item_id,
            sequence_in_session=result.sequence_in_session,
            is_flagged=result.is_flagged,
            flag_type=result.flag_type,
            flag_reason=result.flag_reason,
            traffic_light=result.traffic_light,
        )


@router.post("", response_model=CountItemResponse, status_code=201)
async def create_count_item(
    request: CreateCountItemRequest,
    session: AsyncSession = Depends(get_db),
    operator: OperatorClaims = Depends(get_current_operator),
) -> CountItemResponse:
    try:
        result = await persist_count_item(
            session,
            session_id=request.session_id,
            oracle_code=request.oracle_code,
            article_name=request.article_name,
            raw_transcript=request.raw_transcript,
            quantity=request.quantity,
            unit=request.unit,
            homologation_score=request.homologation_score,
            sin_homologar=request.sin_homologar,
            expiry_date=request.expiry_date,
            is_offline=request.is_offline,
            confidence_stt=request.confidence_stt,
            created_by=operator.operator_id,
        )
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"error": "SESSION_NOT_FOUND", "message": str(exc)}) from exc
    except UnknownOracleCodeError as exc:
        raise HTTPException(status_code=422, detail={"error": "UNKNOWN_ORACLE_CODE", "message": str(exc)}) from exc
    except PerishableItemMissingExpiryError as exc:
        raise HTTPException(
            status_code=422, detail={"error": "EXPIRY_DATE_REQUIRED", "message": str(exc)}
        ) from exc

    await session.commit()
    return CountItemResponse.from_result(result)
