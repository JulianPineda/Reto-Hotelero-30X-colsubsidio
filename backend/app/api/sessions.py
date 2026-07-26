"""POST /api/v1/sessions — creates the CountSession row a real capture flow
needs before anything can be persisted. No EPIC ticket ever specified this
endpoint (every ticket assumes a session_id already exists), but
`services/orchestrator.py::persist_count_item` has a hard FK dependency on
one, so without this endpoint persistence is unusable outside of tests that
insert a CountSession by hand.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.voice.schemas import OperatorClaims
from app.api.deps import get_current_operator
from app.database import get_db
from app.models.count_session import CountSession
from app.models.warehouse import Warehouse

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


class SessionListItem(BaseModel):
    id: UUID
    warehouse_id: UUID
    warehouse_code: str
    operator_id: str
    shift: str
    status: str
    started_at: datetime
    flagged_items: int


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


@router.post("/{session_id}/complete", response_model=SessionResponse)
async def complete_session(
    session_id: UUID,
    session: AsyncSession = Depends(get_db),
    _operator: OperatorClaims = Depends(get_current_operator),
) -> CountSession:
    """CLAUDE.md's session lifecycle (`in_progress -> pending_review ->
    approved -> exported`) was never actually enforced anywhere in this
    codebase — `status` stayed at its 'in_progress' default forever, even
    past export. This is the operator-side transition: "I'm done counting,
    send it to the supervisor." The other two transitions live in
    `api/supervisor.py` (auto-promotes to 'approved' once every flagged
    item is resolved) and `agents/exporter/router.py` (sets 'exported'
    alongside `exported_at`)."""
    count_session = await session.get(CountSession, session_id)
    if count_session is None:
        raise HTTPException(status_code=404, detail={"error": "SESSION_NOT_FOUND"})
    if count_session.status != "in_progress":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "INVALID_STATUS",
                "message": f"La sesión ya está en estado '{count_session.status}'.",
            },
        )

    count_session.status = "pending_review"
    count_session.completed_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(count_session)
    return count_session


@router.get("", response_model=list[SessionListItem])
async def list_sessions(
    session: AsyncSession = Depends(get_db),
    _operator: OperatorClaims = Depends(get_current_operator),
) -> list[SessionListItem]:
    """Lets the Supervisor Dashboard's session picker (`SessionSelect`)
    discover which session to review — nothing in this codebase automates
    the in_progress -> pending_review status transition yet, so this
    deliberately doesn't filter by status; the supervisor picks any
    session and the dashboard itself just shows an empty list if nothing
    in it is flagged."""
    rows = (
        await session.execute(
            select(CountSession, Warehouse.code)
            .join(Warehouse, CountSession.warehouse_id == Warehouse.id)
            .order_by(CountSession.started_at.desc())
        )
    ).all()
    return [
        SessionListItem(
            id=count_session.id,
            warehouse_id=count_session.warehouse_id,
            warehouse_code=warehouse_code,
            operator_id=count_session.operator_id,
            shift=count_session.shift,
            status=count_session.status,
            started_at=count_session.started_at,
            flagged_items=count_session.flagged_items,
        )
        for count_session, warehouse_code in rows
    ]
