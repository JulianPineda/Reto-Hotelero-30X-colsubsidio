import uuid
from types import SimpleNamespace

import pytest

from app.api import count_items
from app.services.orchestrator import PersistedCountItem, SessionNotFoundError, UnknownOracleCodeError
from app.services.perishables import PerishableItemMissingExpiryError
from app.services.unit_compatibility import IncompatibleUnitError


class _FakeSession:
    def __init__(self):
        self.committed = False

    async def commit(self) -> None:
        self.committed = True


class _FakeDeleteSession:
    """Supports `session.get(Model, pk)` (dict-backed per model) plus the
    `add()`/`flush()`/`commit()` calls `append_event` and the delete
    endpoint itself make."""

    def __init__(self, items: dict, count_sessions: dict):
        self._items = items
        self._count_sessions = count_sessions
        self.added: list = []
        self.committed = False

    async def get(self, model, pk):
        from app.models.count_item import CountItem
        from app.models.count_session import CountSession

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


def _fake_item(**overrides):
    defaults = dict(
        id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        oracle_code="HAR-001",
        quantity_confirmed=20.0,
        parsed_quantity=20.0,
        is_flagged=False,
        is_deleted=False,
        deleted_at=None,
        deleted_by=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _fake_count_session(**overrides):
    defaults = dict(warehouse_id=uuid.uuid4(), status="in_progress", total_items=5, flagged_items=1)
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _request(**overrides) -> count_items.CreateCountItemRequest:
    defaults = dict(
        session_id=uuid.uuid4(),
        oracle_code="HAR-001",
        article_name="Harina de Trigo",
        quantity=20.0,
        unit="kg",
    )
    defaults.update(overrides)
    return count_items.CreateCountItemRequest(**defaults)


def _operator():
    return SimpleNamespace(operator_id="OP-231")


async def test_create_count_item_returns_persisted_fields(monkeypatch):
    async def fake_persist(_session, **_kwargs):
        return PersistedCountItem(
            item_id=uuid.uuid4(),
            sequence_in_session=3,
            is_flagged=True,
            flag_type="threshold",
            flag_reason="Caída del 84.4%.",
            traffic_light=None,
        )

    monkeypatch.setattr(count_items, "persist_count_item", fake_persist)

    session = _FakeSession()
    response = await count_items.create_count_item(_request(), session=session, operator=_operator())

    assert response.sequence_in_session == 3
    assert response.is_flagged is True
    assert response.flag_type == "threshold"
    assert session.committed is True


async def test_create_count_item_maps_session_not_found_to_404(monkeypatch):
    async def fake_persist(_session, **_kwargs):
        raise SessionNotFoundError("nope")

    monkeypatch.setattr(count_items, "persist_count_item", fake_persist)

    with pytest.raises(Exception) as exc_info:
        await count_items.create_count_item(_request(), session=_FakeSession(), operator=_operator())

    assert exc_info.value.status_code == 404


async def test_create_count_item_maps_unknown_oracle_code_to_422(monkeypatch):
    async def fake_persist(_session, **_kwargs):
        raise UnknownOracleCodeError("nope")

    monkeypatch.setattr(count_items, "persist_count_item", fake_persist)

    with pytest.raises(Exception) as exc_info:
        await count_items.create_count_item(_request(), session=_FakeSession(), operator=_operator())

    assert exc_info.value.status_code == 422


async def test_create_count_item_maps_missing_expiry_date_to_422(monkeypatch):
    async def fake_persist(_session, **_kwargs):
        raise PerishableItemMissingExpiryError("nope")

    monkeypatch.setattr(count_items, "persist_count_item", fake_persist)

    with pytest.raises(Exception) as exc_info:
        await count_items.create_count_item(_request(), session=_FakeSession(), operator=_operator())

    assert exc_info.value.status_code == 422


async def test_create_count_item_maps_unit_mismatch_to_422(monkeypatch):
    async def fake_persist(_session, **_kwargs):
        raise IncompatibleUnitError("nope")

    monkeypatch.setattr(count_items, "persist_count_item", fake_persist)

    with pytest.raises(Exception) as exc_info:
        await count_items.create_count_item(_request(), session=_FakeSession(), operator=_operator())

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "UNIT_MISMATCH"


async def test_delete_count_item_marks_deleted_and_decrements_counters():
    """Undo for a mis-dictated item — the ItemDeleted event/payload existed
    since the start of this project but had no endpoint until now."""
    item = _fake_item(is_flagged=True)
    count_session = _fake_count_session(total_items=5, flagged_items=2)
    session = _FakeDeleteSession(items={item.id: item}, count_sessions={item.session_id: count_session})

    result = await count_items.delete_count_item(item.id, session=session, operator=_operator())

    assert result == {"item_id": str(item.id), "deleted": True}
    assert item.is_deleted is True
    assert item.deleted_at is not None
    assert item.deleted_by == "OP-231"
    assert count_session.total_items == 4
    assert count_session.flagged_items == 1
    assert session.committed is True
    assert len(session.added) == 1  # the ItemDeleted event


async def test_delete_count_item_never_decrements_counters_below_zero():
    item = _fake_item(is_flagged=True)
    count_session = _fake_count_session(total_items=0, flagged_items=0)
    session = _FakeDeleteSession(items={item.id: item}, count_sessions={item.session_id: count_session})

    await count_items.delete_count_item(item.id, session=session, operator=_operator())

    assert count_session.total_items == 0
    assert count_session.flagged_items == 0


async def test_delete_count_item_404_when_missing():
    session = _FakeDeleteSession(items={}, count_sessions={})

    with pytest.raises(Exception) as exc_info:
        await count_items.delete_count_item(uuid.uuid4(), session=session, operator=_operator())

    assert exc_info.value.status_code == 404


async def test_delete_count_item_404_when_already_deleted():
    item = _fake_item(is_deleted=True)
    session = _FakeDeleteSession(items={item.id: item}, count_sessions={})

    with pytest.raises(Exception) as exc_info:
        await count_items.delete_count_item(item.id, session=session, operator=_operator())

    assert exc_info.value.status_code == 404


async def test_delete_count_item_409_when_session_already_exported():
    item = _fake_item()
    count_session = _fake_count_session(status="exported")
    session = _FakeDeleteSession(items={item.id: item}, count_sessions={item.session_id: count_session})

    with pytest.raises(Exception) as exc_info:
        await count_items.delete_count_item(item.id, session=session, operator=_operator())

    assert exc_info.value.status_code == 409
    assert item.is_deleted is False
