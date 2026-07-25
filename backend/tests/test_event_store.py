import uuid

import pytest

from app.database import AsyncSessionLocal
from app.models.catalog_item import CatalogItem
from app.models.count_item import CountItem
from app.models.count_session import CountSession
from app.models.warehouse import Warehouse
from app.schemas.events import EventType
from app.services import event_store


@pytest.fixture
async def db_session():
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


def test_append_only_no_update():
    """Event store must never expose update/delete methods."""
    assert not hasattr(event_store, "update_event")
    assert not hasattr(event_store, "delete_event")
    assert not hasattr(event_store, "patch_event")


async def test_append_event_persists_payload(db_session):
    warehouse_id = uuid.uuid4()
    aggregate_id = uuid.uuid4()

    event = await event_store.append_event(
        db_session,
        event_type=EventType.ITEM_CREATED,
        aggregate_id=aggregate_id,
        aggregate_type="CountItem",
        payload={"oracle_code": "1031", "quantity": 10},
        warehouse_id=warehouse_id,
        created_by="test-operator",
    )

    assert event.id is not None
    assert event.sequence_number is not None
    assert event.event_type == EventType.ITEM_CREATED
    assert event.payload == {"oracle_code": "1031", "quantity": 10}
    assert event.event_metadata == {}


async def test_sequence_is_monotonic(db_session):
    warehouse_id = uuid.uuid4()
    aggregate_id = uuid.uuid4()

    first = await event_store.append_event(
        db_session,
        event_type=EventType.ITEM_CREATED,
        aggregate_id=aggregate_id,
        aggregate_type="CountItem",
        payload={"quantity": 1},
        warehouse_id=warehouse_id,
        created_by="test-operator",
    )
    second = await event_store.append_event(
        db_session,
        event_type=EventType.ITEM_CORRECTED,
        aggregate_id=aggregate_id,
        aggregate_type="CountItem",
        payload={"quantity": 2},
        warehouse_id=warehouse_id,
        created_by="test-operator",
    )

    assert second.sequence_number > first.sequence_number


async def test_get_aggregate_events_orders_by_sequence(db_session):
    warehouse_id = uuid.uuid4()
    aggregate_id = uuid.uuid4()

    await event_store.append_event(
        db_session,
        EventType.ITEM_CREATED,
        aggregate_id,
        "CountItem",
        {"quantity": 1},
        warehouse_id,
        "test-operator",
    )
    await event_store.append_event(
        db_session,
        EventType.ITEM_CORRECTED,
        aggregate_id,
        "CountItem",
        {"quantity": 2},
        warehouse_id,
        "test-operator",
    )

    events = await event_store.get_aggregate_events(db_session, aggregate_id)

    assert [e.event_type for e in events] == [EventType.ITEM_CREATED, EventType.ITEM_CORRECTED]
    assert events[0].sequence_number < events[1].sequence_number


async def test_get_aggregate_events_ignores_other_aggregates(db_session):
    warehouse_id = uuid.uuid4()
    aggregate_id = uuid.uuid4()
    other_aggregate_id = uuid.uuid4()

    await event_store.append_event(
        db_session,
        EventType.ITEM_CREATED,
        aggregate_id,
        "CountItem",
        {"quantity": 1},
        warehouse_id,
        "test-operator",
    )
    await event_store.append_event(
        db_session,
        EventType.ITEM_CREATED,
        other_aggregate_id,
        "CountItem",
        {"quantity": 99},
        warehouse_id,
        "test-operator",
    )

    events = await event_store.get_aggregate_events(db_session, aggregate_id)

    assert len(events) == 1
    assert events[0].aggregate_id == aggregate_id


async def test_get_session_events_merges_session_and_item_events(db_session):
    warehouse = Warehouse(code=f"TEST-{uuid.uuid4().hex[:8]}", name="Test Warehouse")
    db_session.add(warehouse)
    await db_session.flush()

    catalog_item = CatalogItem(oracle_code=f"TEST-{uuid.uuid4().hex[:8]}", name="Test Item", unit="unit")
    db_session.add(catalog_item)
    await db_session.flush()

    count_session = CountSession(warehouse_id=warehouse.id, operator_id="op-1", shift="morning")
    db_session.add(count_session)
    await db_session.flush()

    count_item = CountItem(
        session_id=count_session.id,
        catalog_item_id=catalog_item.id,
        parsed_quantity=10,
    )
    db_session.add(count_item)
    await db_session.flush()

    # Unrelated session + item — must never show up in this session's events.
    other_session = CountSession(warehouse_id=warehouse.id, operator_id="op-2", shift="afternoon")
    db_session.add(other_session)
    await db_session.flush()

    await event_store.append_event(
        db_session,
        EventType.ITEM_VALIDATED,
        count_session.id,
        "CountSession",
        {"note": "session started"},
        warehouse.id,
        "test-operator",
    )
    await event_store.append_event(
        db_session,
        EventType.ITEM_CREATED,
        count_item.id,
        "CountItem",
        {"quantity": 10},
        warehouse.id,
        "test-operator",
    )
    await event_store.append_event(
        db_session,
        EventType.ITEM_VALIDATED,
        other_session.id,
        "CountSession",
        {"note": "unrelated session"},
        warehouse.id,
        "test-operator",
    )

    events = await event_store.get_session_events(db_session, count_session.id)

    assert len(events) == 2
    assert {e.aggregate_id for e in events} == {count_session.id, count_item.id}
    assert events[0].sequence_number < events[1].sequence_number
