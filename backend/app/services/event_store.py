from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.count_item import CountItem
from app.models.event import Event
from app.schemas.events import EventType


async def append_event(
    session: AsyncSession,
    event_type: EventType,
    aggregate_id: UUID,
    aggregate_type: str,
    payload: dict,
    warehouse_id: UUID,
    created_by: str,
    metadata: dict | None = None,
) -> Event:
    """Append a single immutable event.

    There is deliberately no update/delete counterpart — the `events` table
    is append-only (CLAUDE.md 3.7). Correcting an aggregate means appending a
    new event (e.g. ItemCorrected), never mutating a prior row.
    """
    event = Event(
        event_type=event_type,
        aggregate_id=aggregate_id,
        aggregate_type=aggregate_type,
        payload=payload,
        event_metadata=metadata or {},
        warehouse_id=warehouse_id,
        created_by=created_by,
    )
    session.add(event)
    await session.flush()
    return event


async def get_aggregate_events(session: AsyncSession, aggregate_id: UUID) -> list[Event]:
    """All events for a single aggregate (a CountSession or a CountItem),
    in the order they occurred — the sequence to replay to rebuild its state.
    """
    result = await session.execute(
        select(Event).where(Event.aggregate_id == aggregate_id).order_by(Event.sequence_number)
    )
    return list(result.scalars().all())


async def get_session_events(session: AsyncSession, session_id: UUID) -> list[Event]:
    """All events belonging to a count session: the session's own
    CountSession-aggregate events, plus every CountItem-aggregate event for
    items that belong to it, merged in the order they occurred.
    """
    item_ids_subquery = select(CountItem.id).where(CountItem.session_id == session_id)
    result = await session.execute(
        select(Event)
        .where((Event.aggregate_id == session_id) | (Event.aggregate_id.in_(item_ids_subquery)))
        .order_by(Event.sequence_number)
    )
    return list(result.scalars().all())
