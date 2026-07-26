import uuid
from datetime import datetime
from types import SimpleNamespace

from app.api import supervisor
from app.models.count_item import CountItem
from app.models.count_session import CountSession
from app.schemas.events import EventType


def _make_item(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        oracle_code="HAR-001",
        quantity_confirmed=None,
        parsed_quantity=20.0,
        unit_confirmed=None,
        parsed_unit="kg",
        flag_type="threshold",
        flag_reason="desviacion",
        homologation_score=0.9,
        traffic_light=None,
        expiry_date=None,
        created_at=datetime(2026, 7, 25),
        homologated_name="Harina de Trigo",
        parsed_article="harina de trigo",
        is_approved=None,
        rejection_reason=None,
        corrected_quantity=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class _FakeExecResult:
    def __init__(self, scalar_value):
        self._scalar_value = scalar_value

    def scalar(self):
        return self._scalar_value


class _FakeSession:
    def __init__(self, items: dict, count_sessions: dict, pending_flagged_count: int = 0):
        self._items = items
        self._count_sessions = count_sessions
        self.added: list = []
        self.committed = False
        # Feeds `can_export()`'s query inside `_maybe_mark_approved` —
        # defaults to 0 ("nothing left pending") since every test below
        # resolves every flagged item it creates.
        self._pending_flagged_count = pending_flagged_count

    async def get(self, model, pk):
        if model is CountItem:
            return self._items.get(pk)
        if model is CountSession:
            return self._count_sessions.get(pk)
        return None

    def add(self, obj) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        self.committed = True

    async def execute(self, *_args, **_kwargs):
        return _FakeExecResult(self._pending_flagged_count)


def _events_of_type(session: _FakeSession, event_type: EventType):
    return [e for e in session.added if e.event_type == event_type]


async def test_reject_marks_not_approved():
    item = _make_item()
    count_session = SimpleNamespace(warehouse_id=uuid.uuid4(), status="pending_review")
    session = _FakeSession(items={item.id: item}, count_sessions={item.session_id: count_session})

    response = await supervisor.reject_item(
        item.id,
        supervisor.RejectRequest(reason="Conteo inconsistente con el reconteo físico."),
        session=session,
        _operator=None,
    )

    assert response["is_approved"] is False
    assert item.is_approved is False
    assert item.rejection_reason == "Conteo inconsistente con el reconteo físico."
    assert session.committed is True
    assert len(_events_of_type(session, EventType.ITEM_REJECTED)) == 1


async def test_approve_with_correction_updates_quantity():
    item = _make_item()
    count_session = SimpleNamespace(warehouse_id=uuid.uuid4(), status="pending_review")
    session = _FakeSession(items={item.id: item}, count_sessions={item.session_id: count_session})

    response = await supervisor.approve_item(
        item.id, supervisor.ApproveRequest(corrected_quantity=18.0), session=session, _operator=None
    )

    assert response["is_approved"] is True
    assert item.is_approved is True
    assert item.corrected_quantity == 18.0
    assert len(_events_of_type(session, EventType.ITEM_VALIDATED)) == 1


async def test_approve_without_correction_accepts_dictated_quantity():
    item = _make_item()
    count_session = SimpleNamespace(warehouse_id=uuid.uuid4(), status="pending_review")
    session = _FakeSession(items={item.id: item}, count_sessions={item.session_id: count_session})

    await supervisor.approve_item(
        item.id, supervisor.ApproveRequest(corrected_quantity=None), session=session, _operator=None
    )

    assert item.is_approved is True
    assert item.corrected_quantity is None


async def test_bulk_approve_emits_events():
    session_id = uuid.uuid4()
    warehouse_id = uuid.uuid4()
    items = {}
    for _ in range(3):
        item = _make_item(session_id=session_id)
        items[item.id] = item

    count_session = SimpleNamespace(warehouse_id=warehouse_id, status="pending_review")
    session = _FakeSession(items=items, count_sessions={session_id: count_session})

    request = supervisor.BulkApproveRequest(item_ids=list(items.keys()))
    response = await supervisor.bulk_approve(session_id, request, session=session, _operator=None)

    assert len(response["approved_item_ids"]) == 3
    for item in items.values():
        assert item.is_approved is True
    assert len(_events_of_type(session, EventType.ITEM_VALIDATED)) == 3


async def test_bulk_approve_skips_items_from_other_sessions():
    session_id = uuid.uuid4()
    other_session_id = uuid.uuid4()
    item_in_session = _make_item(session_id=session_id)
    item_in_other_session = _make_item(session_id=other_session_id)

    session = _FakeSession(
        items={item_in_session.id: item_in_session, item_in_other_session.id: item_in_other_session},
        count_sessions={session_id: SimpleNamespace(warehouse_id=uuid.uuid4(), status="pending_review")},
    )

    request = supervisor.BulkApproveRequest(item_ids=[item_in_session.id, item_in_other_session.id])
    response = await supervisor.bulk_approve(session_id, request, session=session, _operator=None)

    assert response["approved_item_ids"] == [str(item_in_session.id)]
    assert item_in_other_session.is_approved is None


async def test_approve_marks_session_approved_when_nothing_else_pending():
    item = _make_item()
    count_session = SimpleNamespace(warehouse_id=uuid.uuid4(), status="pending_review")
    session = _FakeSession(
        items={item.id: item},
        count_sessions={item.session_id: count_session},
        pending_flagged_count=0,
    )

    await supervisor.approve_item(
        item.id, supervisor.ApproveRequest(corrected_quantity=None), session=session, _operator=None
    )

    assert count_session.status == "approved"


async def test_approve_leaves_session_status_alone_when_others_still_pending():
    item = _make_item()
    count_session = SimpleNamespace(warehouse_id=uuid.uuid4(), status="pending_review")
    session = _FakeSession(
        items={item.id: item},
        count_sessions={item.session_id: count_session},
        pending_flagged_count=1,  # another flagged item in the session is still unresolved
    )

    await supervisor.approve_item(
        item.id, supervisor.ApproveRequest(corrected_quantity=None), session=session, _operator=None
    )

    assert count_session.status == "pending_review"


async def test_maybe_mark_approved_never_downgrades_an_exported_session():
    count_session = SimpleNamespace(warehouse_id=uuid.uuid4(), status="exported")
    session = _FakeSession(items={}, count_sessions={"s1": count_session}, pending_flagged_count=0)

    await supervisor._maybe_mark_approved(session, "s1")

    assert count_session.status == "exported"


def test_sort_key_prioritizes_red_perishables_first():
    red_perishable_item = _make_item(traffic_light="red", flag_type="trend")
    catalog_perishable = SimpleNamespace(is_perishable=True)
    normal_item = _make_item(traffic_light=None, flag_type="both")
    catalog_normal = SimpleNamespace(is_perishable=False)

    rows = [(normal_item, catalog_normal), (red_perishable_item, catalog_perishable)]
    ordered = sorted(rows, key=supervisor._sort_key)

    assert ordered[0][0] is red_perishable_item


class _FakeExportGateSession:
    def __init__(self, pending_count: int):
        self._pending_count = pending_count

    async def execute(self, *_args, **_kwargs):
        return _FakeExecResult(self._pending_count)


async def test_cannot_export_with_pending_flags():
    # Sesion con 1 item flaggeado sin resolver (is_approved=None todavia).
    session = _FakeExportGateSession(pending_count=1)
    assert await supervisor.can_export(uuid.uuid4(), session) is False


async def test_can_export_when_no_pending_flags():
    session = _FakeExportGateSession(pending_count=0)
    assert await supervisor.can_export(uuid.uuid4(), session) is True
