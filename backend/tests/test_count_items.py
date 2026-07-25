import uuid
from types import SimpleNamespace

import pytest

from app.api import count_items
from app.services.orchestrator import PersistedCountItem, SessionNotFoundError, UnknownOracleCodeError
from app.services.perishables import PerishableItemMissingExpiryError


class _FakeSession:
    def __init__(self):
        self.committed = False

    async def commit(self) -> None:
        self.committed = True


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
