import uuid
from types import SimpleNamespace

import pytest

from app.services import learning_service
from app.services.catalog_sync import synonym_point_id


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    def __init__(self, results: list):
        self._results = list(results)
        self.added: list = []

    async def execute(self, *_args, **_kwargs):
        return _FakeScalarResult(self._results.pop(0))

    def add(self, obj) -> None:
        self.added.append(obj)


async def _noop_close():
    pass


def _fake_get_qdrant_client():
    return SimpleNamespace(close=_noop_close)


def test_synonym_point_id_is_deterministic():
    id1 = synonym_point_id("ACE-002", "aceite premier oliva")
    id2 = synonym_point_id("ACE-002", "aceite premier oliva")
    id3 = synonym_point_id("ACE-002", "otro sinonimo")

    assert id1 == id2
    assert id1 != id3


async def test_record_correction_creates_new_synonym(monkeypatch):
    catalog_item = SimpleNamespace(id=uuid.uuid4(), oracle_code="ACE-002")
    session = _FakeSession(results=[catalog_item, None])  # found item, no existing synonym

    monkeypatch.setattr(learning_service, "get_qdrant_client", _fake_get_qdrant_client)

    async def fake_upsert_synonym(client, oracle_code, synonym):
        return "point-123"

    monkeypatch.setattr(learning_service, "upsert_synonym", fake_upsert_synonym)

    result = await learning_service.record_correction(
        session, oracle_code="ACE-002", synonym="aceite premier oliva", created_by="OP-231"
    )

    assert result.synonym_created is True
    assert result.qdrant_updated is True
    assert len(session.added) == 1
    added = session.added[0]
    assert added.synonym == "aceite premier oliva"
    assert added.usage_count == 1
    assert added.qdrant_point_id == "point-123"


async def test_record_correction_bumps_usage_count_when_synonym_exists(monkeypatch):
    catalog_item = SimpleNamespace(id=uuid.uuid4(), oracle_code="ACE-002")
    existing_synonym = SimpleNamespace(usage_count=1)
    session = _FakeSession(results=[catalog_item, existing_synonym])

    monkeypatch.setattr(learning_service, "get_qdrant_client", _fake_get_qdrant_client)

    async def fake_upsert_synonym(client, oracle_code, synonym):
        return "point-123"

    monkeypatch.setattr(learning_service, "upsert_synonym", fake_upsert_synonym)

    result = await learning_service.record_correction(
        session, oracle_code="ACE-002", synonym="aceite premier oliva", created_by="OP-231"
    )

    assert result.synonym_created is False
    assert result.qdrant_updated is True
    assert existing_synonym.usage_count == 2
    assert session.added == []


async def test_record_correction_raises_for_unknown_oracle_code():
    session = _FakeSession(results=[None])

    with pytest.raises(ValueError):
        await learning_service.record_correction(
            session, oracle_code="NOPE-999", synonym="algo", created_by="OP-231"
        )
