import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import sessions


class _FakeSession:
    def __init__(self, execute_rows=None, get_result=None):
        self.added: list = []
        self.committed = False
        self.refreshed = False
        self._execute_rows = execute_rows or []
        self._get_result = get_result

    def add(self, obj) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.committed = True
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    async def refresh(self, _obj) -> None:
        self.refreshed = True

    async def execute(self, *_args, **_kwargs):
        return SimpleNamespace(all=lambda: self._execute_rows)

    async def get(self, _model, _pk):
        return self._get_result


async def test_create_session_persists_and_returns_row():
    session = _FakeSession()
    warehouse_id = uuid.uuid4()
    request = sessions.CreateSessionRequest(warehouse_id=warehouse_id, shift="morning")
    operator = type("Operator", (), {"operator_id": "OP-231"})()

    result = await sessions.create_session(request, session=session, operator=operator)

    assert result.warehouse_id == warehouse_id
    assert result.operator_id == "OP-231"
    assert result.shift == "morning"
    assert session.committed is True
    assert session.refreshed is True
    assert result.id is not None


async def test_list_sessions_returns_rows_ordered_by_the_query():
    warehouse_id = uuid.uuid4()
    count_session = SimpleNamespace(
        id=uuid.uuid4(),
        warehouse_id=warehouse_id,
        operator_id="OP-231",
        shift="morning",
        status="in_progress",
        started_at=datetime(2026, 7, 25, 8, 0, 0),
        flagged_items=2,
    )
    session = _FakeSession(execute_rows=[(count_session, "PSL-ALMACEN-GENERAL")])
    operator = type("Operator", (), {"operator_id": "OP-231"})()

    result = await sessions.list_sessions(session=session, _operator=operator)

    assert len(result) == 1
    assert result[0].id == count_session.id
    assert result[0].warehouse_code == "PSL-ALMACEN-GENERAL"
    assert result[0].flagged_items == 2


def _make_count_session(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=uuid.uuid4(),
        warehouse_id=uuid.uuid4(),
        operator_id="OP-231",
        shift="morning",
        status="in_progress",
        completed_at=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


async def test_complete_session_transitions_to_pending_review():
    count_session = _make_count_session()
    session = _FakeSession(get_result=count_session)
    operator = type("Operator", (), {"operator_id": "OP-231"})()

    result = await sessions.complete_session(count_session.id, session=session, _operator=operator)

    assert result.status == "pending_review"
    assert result.completed_at is not None
    assert session.committed is True


async def test_complete_session_404_when_missing():
    session = _FakeSession(get_result=None)
    operator = type("Operator", (), {"operator_id": "OP-231"})()

    with pytest.raises(HTTPException) as exc_info:
        await sessions.complete_session(uuid.uuid4(), session=session, _operator=operator)

    assert exc_info.value.status_code == 404


async def test_complete_session_409_when_not_in_progress():
    count_session = _make_count_session(status="exported")
    session = _FakeSession(get_result=count_session)
    operator = type("Operator", (), {"operator_id": "OP-231"})()

    with pytest.raises(HTTPException) as exc_info:
        await sessions.complete_session(count_session.id, session=session, _operator=operator)

    assert exc_info.value.status_code == 409
