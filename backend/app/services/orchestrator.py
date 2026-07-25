"""The Orchestrator: the one place that actually persists a captured count
item (CountItem row + ItemCreated event). No EPIC ticket ever specified
this as its own piece — voice/session.py and the frontend's offline sync
flow each independently called Catalog Agent + Auditor Agent but never
wrote anything to Postgres, so a captured item never survived a page
refresh or outlived a single WS connection. Both paths now go through
`persist_count_item()` (directly from `voice/session.py`'s persist_item
callback, or via `POST /api/v1/count-items` for the offline sync flow), so
persistence, Auditor Agent invocation, and perishables validation exist in
exactly one place.

Matches the event-count convention already established and tested in
tests/test_e2e_full_session.py: only ItemCreated is emitted here. Flagged
items get is_flagged/flag_type/flag_reason set directly on the CountItem
row; ItemValidated/ItemRejected events are only ever emitted later, by the
Supervisor resolving a flagged item (app/api/supervisor.py) — the Auditor
Agent itself does not emit an event, it only sets fields on the row.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.auditor.router import run_audit
from app.agents.auditor.schemas import AuditRequest
from app.models.catalog_item import CatalogItem
from app.models.count_item import CountItem
from app.models.count_session import CountSession
from app.schemas.events import EventType, ItemCreatedPayload
from app.services.event_store import append_event
from app.services.perishables import compute_traffic_light, validate_perishable_item


class UnknownOracleCodeError(Exception):
    """Raised when the caller claims a homologation (`oracle_code`) that
    doesn't exist in the catalog — trusting that blindly would silently
    corrupt the CountItem/CatalogItem relationship."""


class SessionNotFoundError(Exception):
    pass


@dataclass
class PersistedCountItem:
    item_id: UUID
    sequence_in_session: int
    is_flagged: bool
    flag_type: str | None
    flag_reason: str | None
    traffic_light: str | None


async def persist_count_item(
    session: AsyncSession,
    *,
    session_id: UUID,
    oracle_code: str | None,
    article_name: str,
    raw_transcript: str | None,
    quantity: float,
    unit: str,
    homologation_score: float | None,
    sin_homologar: bool,
    expiry_date: date | None,
    is_offline: bool,
    confidence_stt: float | None,
    created_by: str,
) -> PersistedCountItem:
    """Does NOT commit — callers own the transaction boundary (matches
    every other service in this codebase: event_store.append_event only
    flushes, catalog/router.py and api/supervisor.py commit themselves)."""
    count_session = await session.get(CountSession, session_id)
    if count_session is None:
        raise SessionNotFoundError(f"CountSession {session_id} no existe")

    catalog_item: CatalogItem | None = None
    if oracle_code is not None:
        catalog_item = (
            await session.execute(select(CatalogItem).where(CatalogItem.oracle_code == oracle_code))
        ).scalar_one_or_none()
        if catalog_item is None:
            raise UnknownOracleCodeError(f"oracle_code {oracle_code!r} no existe en el catálogo")

    # CatalogItem.is_perishable is the source of truth, not whatever the
    # caller believes — a client (voice session or offline sync) only ever
    # carries a client-side guess forward, never the authoritative catalog row.
    traffic_light: str | None = None
    if catalog_item is not None and catalog_item.is_perishable:
        validate_perishable_item(catalog_item, expiry_date)  # raises PerishableItemMissingExpiryError
        traffic_light = compute_traffic_light(expiry_date)

    is_flagged = False
    flag_type: str | None = None
    flag_reason: str | None = None
    if catalog_item is not None:
        audit_result = await run_audit(
            session,
            AuditRequest(
                oracle_code=catalog_item.oracle_code,
                quantity=quantity,
                unit=unit,
                warehouse_id=count_session.warehouse_id,
                shift=count_session.shift,
            ),
        )
        is_flagged = audit_result.is_flagged
        flag_type = audit_result.flag_type
        flag_reason = audit_result.explanation

    # Not allocated under a lock — fine at demo scale, a real deployment
    # persisting concurrent items in the same session would need a
    # DB-level serialization point here (same caveat as exporter/router.py's
    # in-memory job dict).
    next_sequence = (
        await session.execute(
            select(func.coalesce(func.max(CountItem.sequence_in_session), 0)).where(
                CountItem.session_id == session_id
            )
        )
    ).scalar() + 1

    item = CountItem(
        session_id=session_id,
        catalog_item_id=catalog_item.id if catalog_item else None,
        oracle_code=oracle_code,
        raw_transcript=raw_transcript,
        parsed_article=article_name,
        parsed_quantity=Decimal(str(quantity)),
        quantity_confirmed=Decimal(str(quantity)),
        unit_confirmed=unit,
        homologated_name=catalog_item.name if catalog_item else None,
        homologation_score=homologation_score,
        sin_homologar=sin_homologar,
        is_flagged=is_flagged,
        flag_type=flag_type,
        flag_reason=flag_reason,
        expiry_date=expiry_date,
        traffic_light=traffic_light,
        is_offline=is_offline,
        sequence_in_session=next_sequence,
    )
    session.add(item)
    await session.flush()

    count_session.total_items = (count_session.total_items or 0) + 1
    if is_flagged:
        count_session.flagged_items = (count_session.flagged_items or 0) + 1

    await append_event(
        session,
        event_type=EventType.ITEM_CREATED,
        aggregate_id=item.id,
        aggregate_type="CountItem",
        payload=ItemCreatedPayload(
            oracle_code=oracle_code,
            article_name=article_name,
            quantity=quantity,
            unit=unit,
            homologation_score=homologation_score,
            sin_homologar=sin_homologar,
            confidence_stt=confidence_stt,
            is_offline=is_offline,
        ).model_dump(),
        warehouse_id=count_session.warehouse_id,
        created_by=created_by,
    )

    return PersistedCountItem(
        item_id=item.id,
        sequence_in_session=next_sequence,
        is_flagged=is_flagged,
        flag_type=flag_type,
        flag_reason=flag_reason,
        traffic_light=traffic_light,
    )
