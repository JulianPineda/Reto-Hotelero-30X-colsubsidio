"""POST /api/v1/agents/audit — Auditor Agent (T-011 threshold + T-012 trend
+ T-013 explainer, combined per T-012's "Integración en router.py")."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.auditor.explainer import build_explanation
from app.agents.auditor.schemas import (
    AuditRequest,
    AuditResult,
    HistoricalCountPoint,
    ThresholdDetail,
    TrendDetail,
)
from app.agents.auditor.threshold import check_threshold
from app.agents.auditor.trend import check_trend
from app.agents.voice.schemas import OperatorClaims
from app.api.deps import get_current_operator
from app.database import get_db
from app.models.catalog_item import CatalogItem
from app.models.historical_count import HistoricalCount

router = APIRouter(prefix="/agents", tags=["auditor"])

HISTORY_WINDOW = 5


async def _load_historical_series(
    session: AsyncSession, warehouse_id: UUID, oracle_code: str, shift: str
) -> list[HistoricalCount]:
    """CLAUDE.md §3.1 Regla C: prioriza conteos del mismo turno; si hay
    menos de 3, completa con conteos de otros turnos."""
    catalog_item = (
        await session.execute(select(CatalogItem).where(CatalogItem.oracle_code == oracle_code))
    ).scalar_one_or_none()
    if catalog_item is None:
        return []

    same_shift = (
        (
            await session.execute(
                select(HistoricalCount)
                .where(
                    HistoricalCount.warehouse_id == warehouse_id,
                    HistoricalCount.catalog_item_id == catalog_item.id,
                    HistoricalCount.shift == shift,
                    HistoricalCount.is_validated.is_(True),
                )
                .order_by(HistoricalCount.count_date.desc())
                .limit(HISTORY_WINDOW)
            )
        )
        .scalars()
        .all()
    )

    if len(same_shift) >= 3:
        return list(same_shift)

    others = (
        (
            await session.execute(
                select(HistoricalCount)
                .where(
                    HistoricalCount.warehouse_id == warehouse_id,
                    HistoricalCount.catalog_item_id == catalog_item.id,
                    HistoricalCount.is_validated.is_(True),
                )
                .order_by(HistoricalCount.count_date.desc())
                .limit(HISTORY_WINDOW)
            )
        )
        .scalars()
        .all()
    )

    merged: list[HistoricalCount] = list(same_shift)
    seen_ids = {row.id for row in merged}
    for row in others:
        if row.id not in seen_ids:
            merged.append(row)
            seen_ids.add(row.id)
        if len(merged) >= HISTORY_WINDOW:
            break

    return merged[:HISTORY_WINDOW]


async def run_audit(session: AsyncSession, request: AuditRequest) -> AuditResult:
    """Shared Auditor Agent entry point — called by the HTTP `/audit`
    endpoint and by the Orchestrator (`services/orchestrator.py`) when
    persisting a captured item, so both callers can never drift apart.
    """
    history = await _load_historical_series(session, request.warehouse_id, request.oracle_code, request.shift)
    quantities = [float(row.quantity) for row in history]

    historical_avg = sum(quantities) / len(quantities) if quantities else 0.0
    threshold_result = check_threshold(request.quantity, historical_avg)
    trend_result = check_trend(request.quantity, quantities)

    threshold_detail = (
        ThresholdDetail(
            delta_pct=threshold_result.delta_pct,
            delta_abs=threshold_result.delta_abs,
            historical_avg=threshold_result.historical_avg,
        )
        if threshold_result.is_flagged
        else None
    )
    trend_detail = (
        TrendDetail(
            is_flagged=trend_result.is_flagged,
            series_mean=trend_result.series_mean,
            series_stdev=trend_result.series_stdev,
            deviation_sigmas=trend_result.deviation_sigmas,
            series_length=trend_result.series_length,
        )
        if trend_result.is_flagged
        else None
    )

    if threshold_result.is_flagged and trend_result.is_flagged:
        flag_type = "both"
    elif threshold_result.is_flagged:
        flag_type = "threshold"
    elif trend_result.is_flagged:
        flag_type = "trend"
    else:
        flag_type = None

    historical_counts = [
        HistoricalCountPoint(date=row.count_date.isoformat(), quantity=float(row.quantity), shift=row.shift)
        for row in history
    ]

    result = AuditResult(
        is_flagged=flag_type is not None,
        flag_type=flag_type,
        explanation=None,
        quantity=request.quantity,
        unit=request.unit,
        threshold_detail=threshold_detail,
        trend_detail=trend_detail,
        historical_counts=historical_counts,
    )

    if flag_type is not None:
        result.explanation = build_explanation(result)

    return result


@router.post("/audit", response_model=AuditResult)
async def audit(
    request: AuditRequest,
    session: AsyncSession = Depends(get_db),
    _operator: OperatorClaims = Depends(get_current_operator),
) -> AuditResult:
    return await run_audit(session, request)
