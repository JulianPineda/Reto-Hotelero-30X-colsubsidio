"""POST /api/v1/sessions — creates the CountSession row a real capture flow
needs before anything can be persisted. No EPIC ticket ever specified this
endpoint (every ticket assumes a session_id already exists), but
`services/orchestrator.py::persist_count_item` has a hard FK dependency on
one, so without this endpoint persistence is unusable outside of tests that
insert a CountSession by hand.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.voice.schemas import OperatorClaims
from app.api.deps import get_current_operator
from app.database import get_db
from app.models.count_session import CountSession

router = APIRouter(prefix="/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    warehouse_id: UUID
    shift: str  # morning | afternoon | night


class SessionResponse(BaseModel):
    id: UUID
    warehouse_id: UUID
    operator_id: str
    shift: str
    status: str

    model_config = {"from_attributes": True}


@router.post("", response_model=SessionResponse, status_code=201)
async def create_session(
    request: CreateSessionRequest,
    session: AsyncSession = Depends(get_db),
    operator: OperatorClaims = Depends(get_current_operator),
) -> CountSession:
    count_session = CountSession(
        warehouse_id=request.warehouse_id, operator_id=operator.operator_id, shift=request.shift
    )
    session.add(count_session)
    await session.commit()
    await session.refresh(count_session)
    return count_session
