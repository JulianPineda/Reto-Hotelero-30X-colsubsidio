import uuid

from app.api import sessions


class _FakeSession:
    def __init__(self):
        self.added: list = []
        self.committed = False
        self.refreshed = False

    def add(self, obj) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.committed = True
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    async def refresh(self, _obj) -> None:
        self.refreshed = True


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
