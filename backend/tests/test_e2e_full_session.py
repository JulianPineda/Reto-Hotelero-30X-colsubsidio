"""E2E integration test (T-018): simulates a full count session and
exercises the Auditor -> Supervisor -> Exporter -> event-log chain.

REQUIRES a real, disposable Postgres database (this test COMMITS real rows
and writes a real CSV file to disk — it does not roll back, because the
Exporter's background job opens its OWN connection via AsyncSessionLocal()
and can only see data another connection has actually committed). Run this
against a throwaway test schema, never against production data. Skipped by
default — opt in with `RUN_E2E_DB_TESTS=1` (learned the hard way: a routine
`pytest` run against the dev docker-compose stack left three permanent
"PSL-TEST-*" warehouses + catalog items behind). Voice
parsing and Catalog homologation (Gemini, Qdrant) are intentionally NOT
exercised here — this test starts from already-parsed CountItem rows; the
LLM-facing paths are covered separately by test_parser.py / test_catalog.py.

NOTE ON A SCENARIO DISCREPANCY: EPIC-6-export-polish.md's own walkthrough
says "Supervisor aprueba los 2 flaggeados" (approves both) but its own
assertion checks for "10 ItemCreated + 2 ItemRejected + 2 ItemValidated"
(14 events) — inconsistent for a session with only 2 flagged items (you
cannot both-approve 2 items and get 2 rejections from them). This test
instead approves one flagged item and rejects the other, exercising both
code paths, and asserts the tally that is actually consistent with that:
10 ItemCreated + 1 ItemValidated + 1 ItemRejected = 12 events.
"""
from __future__ import annotations

import os
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.agents.auditor.threshold import check_threshold
from app.agents.auditor.trend import check_trend
from app.agents.exporter.oracle_csv import CSV_COLUMNS
from app.agents.exporter.router import _JOBS, _run_export_job, validate_can_export
from app.agents.exporter.schemas import SessionAlreadyExportedError
from app.api import supervisor
from app.database import AsyncSessionLocal
from app.models.catalog_item import CatalogItem
from app.models.count_item import CountItem
from app.models.count_session import CountSession
from app.models.historical_count import HistoricalCount
from app.models.warehouse import Warehouse
from app.schemas.events import EventType
from app.services.event_store import append_event, get_session_events


@pytest.mark.skipif(
    os.getenv("RUN_E2E_DB_TESTS") != "1",
    reason="writes permanent, uncleaned rows to whatever DB it's pointed at "
    "(see module docstring) — opt in with RUN_E2E_DB_TESTS=1 against a "
    "disposable schema, never in a routine `pytest` run",
)
async def test_full_session_happy_path():
    suffix = uuid.uuid4().hex[:8]
    historical_values = [90.0, 92.0, 88.0, 91.0, 89.0]

    async with AsyncSessionLocal() as db:
        # --- 1. Bodega + articulo con historico (oracle_code=7290 "ACEITE") ---
        warehouse = Warehouse(code=f"PSL-TEST-{suffix}", name="Almacen General de Prueba")
        db.add(warehouse)
        await db.flush()

        catalog_item = CatalogItem(oracle_code=f"7290-{suffix}", name="Aceite Vegetal Premier 5L", unit="GAL")
        db.add(catalog_item)
        await db.flush()

        # --- 2. Historico: 5 conteos estables, mismo turno, validados ---
        for i, qty in enumerate(historical_values):
            db.add(
                HistoricalCount(
                    warehouse_id=warehouse.id,
                    catalog_item_id=catalog_item.id,
                    oracle_code=catalog_item.oracle_code,
                    count_date=date.today() - timedelta(days=i + 1),
                    shift="morning",
                    quantity=Decimal(str(qty)),
                    is_validated=True,
                )
            )
        await db.flush()

        # --- 3. Sesion de conteo ---
        count_session = CountSession(
            warehouse_id=warehouse.id, operator_id="OP-231", shift="morning", supervisor_id="SUP-1"
        )
        db.add(count_session)
        await db.flush()

        # --- 4. 10 items: threshold-flagged, trend-flagged, perecedero
        #        yellow, sin_homologar, offline, y 5 normales ---
        historical_avg = sum(historical_values) / len(historical_values)

        threshold_result = check_threshold(14.0, historical_avg)
        assert threshold_result.is_flagged is True
        item_threshold = CountItem(
            session_id=count_session.id,
            catalog_item_id=catalog_item.id,
            oracle_code=catalog_item.oracle_code,
            parsed_article="aceite vegetal",
            parsed_quantity=Decimal("14.0"),
            quantity_confirmed=Decimal("14.0"),
            unit_confirmed="GAL",
            homologated_name=catalog_item.name,
            homologation_score=0.94,
            is_flagged=True,
            flag_type="threshold",
            flag_reason=f"Caída del {threshold_result.delta_pct}% respecto al promedio histórico.",
            sequence_in_session=1,
        )

        trend_result = check_trend(45.0, historical_values)
        assert trend_result.is_flagged is True
        item_trend = CountItem(
            session_id=count_session.id,
            catalog_item_id=catalog_item.id,
            oracle_code=catalog_item.oracle_code,
            parsed_article="aceite vegetal",
            parsed_quantity=Decimal("45.0"),
            quantity_confirmed=Decimal("45.0"),
            unit_confirmed="GAL",
            homologated_name=catalog_item.name,
            homologation_score=0.9,
            is_flagged=True,
            flag_type="trend",
            flag_reason="Rompe el patrón estable de la serie.",
            sequence_in_session=2,
        )

        perishable_catalog_item = CatalogItem(
            oracle_code=f"LAC-{suffix}", name="Leche UHT", unit="L", is_perishable=True, default_shelf_days=10
        )
        db.add(perishable_catalog_item)
        await db.flush()
        item_perishable = CountItem(
            session_id=count_session.id,
            catalog_item_id=perishable_catalog_item.id,
            oracle_code=perishable_catalog_item.oracle_code,
            parsed_article="leche uht",
            parsed_quantity=Decimal("20.0"),
            quantity_confirmed=Decimal("20.0"),
            unit_confirmed="L",
            homologated_name=perishable_catalog_item.name,
            homologation_score=0.9,
            expiry_date=date.today() + timedelta(days=5),
            traffic_light="yellow",
            sequence_in_session=3,
        )

        item_sin_homologar = CountItem(
            session_id=count_session.id,
            catalog_item_id=None,
            oracle_code=None,
            parsed_article="articulo desconocido xyz",
            parsed_quantity=Decimal("3.0"),
            unit_confirmed="unit",
            sin_homologar=True,
            sequence_in_session=4,
        )

        item_offline = CountItem(
            session_id=count_session.id,
            catalog_item_id=catalog_item.id,
            oracle_code=catalog_item.oracle_code,
            parsed_article="aceite vegetal",
            parsed_quantity=Decimal("90.0"),
            quantity_confirmed=Decimal("90.0"),
            unit_confirmed="GAL",
            homologated_name=catalog_item.name,
            homologation_score=0.95,
            is_offline=True,
            sequence_in_session=5,
        )

        items = [item_threshold, item_trend, item_perishable, item_sin_homologar, item_offline]
        for seq in range(6, 11):
            items.append(
                CountItem(
                    session_id=count_session.id,
                    catalog_item_id=catalog_item.id,
                    oracle_code=catalog_item.oracle_code,
                    parsed_article="aceite vegetal",
                    parsed_quantity=Decimal("90.0"),
                    quantity_confirmed=Decimal("90.0"),
                    unit_confirmed="GAL",
                    homologated_name=catalog_item.name,
                    homologation_score=0.95,
                    sequence_in_session=seq,
                )
            )

        assert len(items) == 10
        for item in items:
            db.add(item)
        await db.flush()

        # --- 5. Evento ItemCreated por cada item ---
        for item in items:
            await append_event(
                db,
                event_type=EventType.ITEM_CREATED,
                aggregate_id=item.id,
                aggregate_type="CountItem",
                payload={
                    "oracle_code": item.oracle_code,
                    "article_name": item.parsed_article,
                    "quantity": float(item.parsed_quantity),
                    "unit": item.unit_confirmed,
                    "homologation_score": item.homologation_score,
                    "sin_homologar": item.sin_homologar,
                    "confidence_stt": 0.9,
                    "is_offline": item.is_offline,
                },
                warehouse_id=warehouse.id,
                created_by=count_session.operator_id,
            )

        # Criterios #5/#6: anomalias por umbral y por tendencia presentes
        flagged = [i for i in items if i.is_flagged]
        assert len(flagged) == 2
        assert any(i.flag_type == "threshold" for i in flagged)
        assert any(i.flag_type == "trend" for i in flagged)

        await db.commit()

        # --- 6. Supervisor resuelve los 2 flaggeados: uno aprobado, uno rechazado ---
        await supervisor.approve_item(
            item_threshold.id,
            supervisor.ApproveRequest(corrected_quantity=None),
            session=db,
            _operator=None,
        )
        await supervisor.reject_item(
            item_trend.id,
            supervisor.RejectRequest(reason="Reconteo físico confirmó 90, error de dictado."),
            session=db,
            _operator=None,
        )

        assert item_threshold.is_approved is True
        assert item_trend.is_approved is False
        assert await supervisor.can_export(count_session.id, db) is True

        await db.refresh(count_session)
        assert count_session.status == "approved"

        # --- 7. Exportar ---
        await validate_can_export(count_session.id, db)  # no debe lanzar

        job_id = uuid.uuid4()
        await _run_export_job(job_id, count_session.id, "csv")
        job_status = _JOBS[job_id]
        assert job_status.status == "completed", job_status.error

        await db.refresh(count_session)
        assert count_session.exported_at is not None
        assert count_session.status == "exported"

        exported_path = Path(count_session.export_path)
        csv_content = exported_path.read_text(encoding="utf-8")
        csv_lines = csv_content.strip().split("\n")

        # Criterio #1: columnas CSV idénticas al spec
        assert csv_lines[0] == "|".join(CSV_COLUMNS)
        # 10 items - 1 rechazado (item_trend) = 9 filas de datos
        assert len(csv_lines) - 1 == 9
        assert job_status.row_count == 9
        assert job_status.flagged_excluded == 1

        # --- 8. Segundo intento de exportar -> bloqueado ---
        with pytest.raises(SessionAlreadyExportedError):
            await validate_can_export(count_session.id, db)

        # --- 9. Event log completo ---
        all_events = await get_session_events(db, count_session.id)
        created = [e for e in all_events if e.event_type == EventType.ITEM_CREATED]
        validated = [e for e in all_events if e.event_type == EventType.ITEM_VALIDATED]
        rejected = [e for e in all_events if e.event_type == EventType.ITEM_REJECTED]

        assert len(created) == 10
        assert len(validated) == 1
        assert len(rejected) == 1
        assert len(all_events) == 12
