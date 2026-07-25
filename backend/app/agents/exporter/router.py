"""POST /api/v1/agents/export, GET /api/v1/agents/export/jobs/{job_id}
(T-016).

No background-job infra exists (no Celery/Redis in docker-compose.yml) —
jobs run via FastAPI BackgroundTasks and their status lives in an
in-process dict. Fine for the demo scale (single backend instance); a real
deployment needs a job table/queue, and note this in-memory approach also
has a race window (two POST /export calls for the same session in quick
succession, before the first job's background task sets exported_at, would
both be accepted) that a real job queue with a DB-level lock would close.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.exporter.excel_builder import build_excel
from app.agents.exporter.oracle_csv import build_row, generate_csv, get_export_path
from app.agents.exporter.schemas import (
    ExportAccepted,
    ExportBlockedError,
    ExportJobStatus,
    ExportRequest,
    SessionAlreadyExportedError,
)
from app.agents.voice.schemas import OperatorClaims
from app.api.deps import get_current_operator
from app.api.supervisor import can_export
from app.database import AsyncSessionLocal, get_db
from app.models.count_item import CountItem
from app.models.count_session import CountSession
from app.models.warehouse import Warehouse

router = APIRouter(prefix="/agents", tags=["exporter"])

_JOBS: dict[UUID, ExportJobStatus] = {}


async def validate_can_export(session_id: UUID, db: AsyncSession) -> None:
    if not await can_export(session_id, db):
        raise ExportBlockedError(f"Hay item(s) flaggeados sin revisar en la sesión {session_id}")

    count_session = await db.get(CountSession, session_id)
    if count_session is not None and count_session.exported_at is not None:
        raise SessionAlreadyExportedError("Esta sesión ya fue exportada")


@router.post("/export", status_code=202, response_model=ExportAccepted)
async def request_export(
    request: ExportRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
    _operator: OperatorClaims = Depends(get_current_operator),
) -> ExportAccepted:
    try:
        await validate_can_export(request.session_id, session)
    except SessionAlreadyExportedError as exc:
        raise HTTPException(status_code=409, detail={"error": "ALREADY_EXPORTED", "message": str(exc)}) from exc
    except ExportBlockedError as exc:
        raise HTTPException(status_code=422, detail={"error": "EXPORT_BLOCKED", "message": str(exc)}) from exc

    job_id = uuid4()
    _JOBS[job_id] = ExportJobStatus(status="queued", session_id=request.session_id)
    background_tasks.add_task(_run_export_job, job_id, request.session_id, request.format)
    return ExportAccepted(job_id=job_id, status="queued")


@router.get("/export/jobs/{job_id}", response_model=ExportJobStatus)
async def get_export_job(
    job_id: UUID, _operator: OperatorClaims = Depends(get_current_operator)
) -> ExportJobStatus:
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={"error": "JOB_NOT_FOUND"})
    return job


async def _run_export_job(job_id: UUID, session_id: UUID, export_format: str) -> None:
    async with AsyncSessionLocal() as session:
        try:
            count_session = await session.get(CountSession, session_id)
            warehouse = await session.get(Warehouse, count_session.warehouse_id)

            # CLAUDE.md §3.5: excluye solo los explicitamente rechazados
            # (is_approved=false). Los items nunca flaggeados quedan con
            # is_approved=NULL para siempre y SI se exportan.
            items = (
                (
                    await session.execute(
                        select(CountItem).where(
                            CountItem.session_id == session_id,
                            CountItem.is_approved.isnot(False),
                        )
                    )
                )
                .scalars()
                .all()
            )

            export_timestamp = datetime.now(timezone.utc)
            count_date = count_session.started_at.date()

            rows = [
                build_row(
                    warehouse_code=warehouse.code,
                    oracle_code=item.oracle_code or "",
                    item_name=item.homologated_name or item.parsed_article or "",
                    unit=item.unit_confirmed or item.parsed_unit or "",
                    quantity=item.corrected_quantity or item.quantity_confirmed or item.parsed_quantity,
                    count_date=count_date,
                    shift=count_session.shift,
                    operator_id=count_session.operator_id,
                    session_id=session_id,
                    is_validated=bool(item.is_approved),
                    supervisor_id=count_session.supervisor_id,
                    export_timestamp=export_timestamp,
                )
                for item in items
            ]

            export_path = get_export_path(session_id, warehouse.code, count_date, count_session.shift)
            export_path.parent.mkdir(parents=True, exist_ok=True)

            if export_format == "excel":
                export_path = export_path.with_suffix(".xlsx")
                export_path.write_bytes(build_excel(rows, title=f"Conteo {warehouse.code} {count_date}"))
            else:
                # UTF-8 sin BOM (CLAUDE.md §3.5) — nunca "utf-8-sig".
                export_path.write_text(generate_csv(rows), encoding="utf-8", newline="")

            count_session.exported_at = export_timestamp
            count_session.export_path = str(export_path)
            await session.commit()

            flagged_excluded = (
                (
                    await session.execute(
                        select(CountItem).where(
                            CountItem.session_id == session_id, CountItem.is_approved.is_(False)
                        )
                    )
                )
                .scalars()
                .all()
            )

            _JOBS[job_id] = ExportJobStatus(
                status="completed",
                download_url=f"/api/v1/exports/{export_path.name}",
                row_count=len(rows),
                flagged_excluded=len(flagged_excluded),
                session_id=session_id,
            )
        except Exception as exc:  # noqa: BLE001 - job status sidecar, not an HTTP response path
            _JOBS[job_id] = ExportJobStatus(status="failed", session_id=session_id, error=str(exc))
