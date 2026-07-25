import uuid
from datetime import datetime

from app.api import warehouses
from app.models.warehouse import Warehouse


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalars(self._rows)


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, *_args, **_kwargs):
        return _FakeResult(self._rows)


def _make_warehouse(**overrides) -> Warehouse:
    wh = Warehouse()
    wh.id = overrides.get("id", uuid.uuid4())
    wh.code = overrides.get("code", "PSL-ALMACEN-GENERAL")
    wh.name = overrides.get("name", "Almacén General")
    wh.location = overrides.get("location")
    wh.timezone = overrides.get("timezone", "America/Bogota")
    wh.is_active = overrides.get("is_active", True)
    wh.created_at = overrides.get("created_at", datetime(2026, 1, 1))
    wh.updated_at = overrides.get("updated_at", datetime(2026, 1, 1))
    return wh


async def test_list_warehouses_returns_rows_from_query():
    rows = [_make_warehouse(), _make_warehouse(code="PSL-ZOO", name="Zoológico")]
    session = _FakeSession(rows)

    result = await warehouses.list_warehouses(session=session, _operator=None)

    assert result == rows
