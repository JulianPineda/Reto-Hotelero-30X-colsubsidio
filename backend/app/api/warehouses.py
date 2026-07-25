"""Warehouses listing (T-014-adjacent gap, api-contracts.md §"REST —
Warehouses / Health"): "Lista de bodegas activas con el operario
autenticado" — the frontend's warehouse picker needs this before a
CountSession can even start.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.voice.schemas import OperatorClaims
from app.api.deps import get_current_operator
from app.database import get_db
from app.models.warehouse import Warehouse

router = APIRouter(prefix="/warehouses", tags=["warehouses"])


class WarehouseResponse(BaseModel):
    id: UUID
    code: str
    name: str
    location: str | None
    timezone: str
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[WarehouseResponse])
async def list_warehouses(
    session: AsyncSession = Depends(get_db),
    _operator: OperatorClaims = Depends(get_current_operator),
) -> list[Warehouse]:
    result = await session.execute(
        select(Warehouse).where(Warehouse.is_active.is_(True)).order_by(Warehouse.name)
    )
    return list(result.scalars().all())
