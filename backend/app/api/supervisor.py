"""Supervisor Dashboard API (T-014): review, approve/reject flagged items,
bulk-approve, and the export gate (CLAUDE.md §3.4 — every is_flagged=true
item must carry a non-null is_approved before a session can export).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.voice.schemas import OperatorClaims
from app.api.deps import get_current_operator
from app.database import get_db
from app.models.catalog_item import CatalogItem
from app.models.count_item import CountItem
from app.models.count_session import CountSession
from app.schemas.events import EventType, ItemRejectedPayload, ItemValidatedPayload
from app.services.event_store import append_event, get_session_events

router = APIRouter(prefix="/supervisor", tags=["supervisor"])


class FlaggedItemResponse(BaseModel):
    item_id: UUID
    session_id: UUID
    oracle_code: str | None
    article_name: str
    quantity: Decimal
    unit: str | None
    flag_type: str | None
    flag_reason: str | None
    homologation_score: float | None
    traffic_light: str | None
    is_perishable: bool
    expiry_date: date | None
    created_at: datetime


class ApproveRequest(BaseModel):
    corrected_quantity: Decimal | None = None


class RejectRequest(BaseModel):
    reason: str


class BulkApproveRequest(BaseModel):
    item_ids: list[UUID]


_FLAG_TYPE_PRIORITY = {"both": 0, "threshold": 1, "trend": 2, None: 3}


def _sort_key(row: tuple[CountItem, CatalogItem | None]) -> tuple[int, int]:
    """RED perecederos primero, luego por flag_type (CLAUDE.md §3.6 + T-015)."""
    item, catalog_item = row
    is_perishable = bool(catalog_item and catalog_item.is_perishable)
    is_red = item.traffic_light == "red"
    return (0 if (is_perishable and is_red) else 1, _FLAG_TYPE_PRIORITY.get(item.flag_type, 3))


@router.get("/sessions/{session_id}/flagged-items", response_model=list[FlaggedItemResponse])
async def get_flagged_items(
    session_id: UUID,
    session: AsyncSession = Depends(get_db),
    _operator: OperatorClaims = Depends(get_current_operator),
) -> list[FlaggedItemResponse]:
    rows = (
        await session.execute(
            select(CountItem, CatalogItem)
            .outerjoin(CatalogItem, CountItem.catalog_item_id == CatalogItem.id)
            .where(CountItem.session_id == session_id, CountItem.is_flagged.is_(True))
        )
    ).all()

    ordered = sorted(rows, key=_sort_key)

    return [
        FlaggedItemResponse(
            item_id=item.id,
            session_id=item.session_id,
            oracle_code=item.oracle_code,
            article_name=item.homologated_name or item.parsed_article or "",
            quantity=item.quantity_confirmed or item.parsed_quantity,
            unit=item.unit_confirmed or item.parsed_unit,
            flag_type=item.flag_type,
            flag_reason=item.flag_reason,
            homologation_score=item.homologation_score,
            traffic_light=item.traffic_light,
            is_perishable=bool(catalog_item and catalog_item.is_perishable),
            expiry_date=item.expiry_date,
            created_at=item.created_at,
        )
        for item, catalog_item in ordered
    ]


async def _get_item_or_404(session: AsyncSession, item_id: UUID) -> CountItem:
    item = await session.get(CountItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail={"error": "ITEM_NOT_FOUND"})
    return item


async def _warehouse_id_for_item(session: AsyncSession, item: CountItem) -> UUID:
    count_session = await session.get(CountSession, item.session_id)
    return count_session.warehouse_id


@router.post("/items/{item_id}/approve")
async def approve_item(
    item_id: UUID,
    request: ApproveRequest,
    session: AsyncSession = Depends(get_db),
    _operator: OperatorClaims = Depends(get_current_operator),
) -> dict:
    item = await _get_item_or_404(session, item_id)

    if request.corrected_quantity is not None:
        item.corrected_quantity = request.corrected_quantity
    item.is_approved = True

    final_quantity = float(request.corrected_quantity or item.quantity_confirmed or item.parsed_quantity)
    await append_event(
        session,
        event_type=EventType.ITEM_VALIDATED,
        aggregate_id=item.id,
        aggregate_type="CountItem",
        payload=ItemValidatedPayload(
            oracle_code=item.oracle_code or "",
            quantity=final_quantity,
            unit=item.unit_confirmed or item.parsed_unit or "",
            validated_by="supervisor",
            flag_type=item.flag_type,
        ).model_dump(),
        warehouse_id=await _warehouse_id_for_item(session, item),
        created_by="supervisor",
    )
    await session.commit()
    return {"item_id": str(item.id), "is_approved": True}


@router.post("/items/{item_id}/reject")
async def reject_item(
    item_id: UUID,
    request: RejectRequest,
    session: AsyncSession = Depends(get_db),
    _operator: OperatorClaims = Depends(get_current_operator),
) -> dict:
    item = await _get_item_or_404(session, item_id)
    item.is_approved = False
    item.rejection_reason = request.reason

    await append_event(
        session,
        event_type=EventType.ITEM_REJECTED,
        aggregate_id=item.id,
        aggregate_type="CountItem",
        payload=ItemRejectedPayload(
            oracle_code=item.oracle_code,
            quantity=float(item.quantity_confirmed or item.parsed_quantity),
            flag_type=item.flag_type or "threshold",
            flag_reason=request.reason,
            historical_counts=[],
            deviation_pct=None,
        ).model_dump(),
        warehouse_id=await _warehouse_id_for_item(session, item),
        created_by="supervisor",
    )
    await session.commit()
    return {"item_id": str(item.id), "is_approved": False}


@router.post("/sessions/{session_id}/bulk-approve")
async def bulk_approve(
    session_id: UUID,
    request: BulkApproveRequest,
    session: AsyncSession = Depends(get_db),
    _operator: OperatorClaims = Depends(get_current_operator),
) -> dict:
    approved_ids: list[UUID] = []
    for item_id in request.item_ids:
        item = await session.get(CountItem, item_id)
        if item is None or item.session_id != session_id:
            continue

        item.is_approved = True
        await append_event(
            session,
            event_type=EventType.ITEM_VALIDATED,
            aggregate_id=item.id,
            aggregate_type="CountItem",
            payload=ItemValidatedPayload(
                oracle_code=item.oracle_code or "",
                quantity=float(item.quantity_confirmed or item.parsed_quantity),
                unit=item.unit_confirmed or item.parsed_unit or "",
                validated_by="supervisor",
                flag_type=item.flag_type,
            ).model_dump(),
            warehouse_id=await _warehouse_id_for_item(session, item),
            created_by="supervisor",
        )
        approved_ids.append(item.id)

    await session.commit()
    return {"approved_item_ids": [str(i) for i in approved_ids]}


@router.get("/sessions/{session_id}/events")
async def get_session_events_endpoint(
    session_id: UUID,
    session: AsyncSession = Depends(get_db),
    _operator: OperatorClaims = Depends(get_current_operator),
) -> list[dict]:
    """Historial completo de eventos — solo para el Auditor de Costos, nunca
    expuesto a Oracle."""
    events = await get_session_events(session, session_id)
    return [
        {
            "id": str(e.id),
            "event_type": e.event_type,
            "aggregate_id": str(e.aggregate_id),
            "aggregate_type": e.aggregate_type,
            "payload": e.payload,
            "occurred_at": e.occurred_at.isoformat(),
            "sequence_number": e.sequence_number,
        }
        for e in events
    ]


async def can_export(session_id: UUID, db: AsyncSession) -> bool:
    """CLAUDE.md §3.4: no se puede exportar si quedan items flaggeados sin
    is_approved resuelto. Consumido por el futuro endpoint del Exporter
    Agent (EPIC-6) — no implementado en este epic."""
    pending = await db.execute(
        select(func.count(CountItem.id))
        .where(CountItem.session_id == session_id)
        .where(CountItem.is_flagged.is_(True))
        .where(CountItem.is_approved.is_(None))
    )
    return pending.scalar() == 0
