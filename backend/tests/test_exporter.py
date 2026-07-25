import uuid
from datetime import date, datetime, timezone

import pytest

from app.agents.exporter.oracle_csv import BASE_EXPORT_DIR, build_row, generate_csv, get_export_path
from app.agents.exporter.router import validate_can_export
from app.agents.exporter.schemas import ExportBlockedError, SessionAlreadyExportedError


def _sample_row(**overrides) -> dict:
    defaults = dict(
        warehouse_code="PSL-ALMACEN-GENERAL",
        oracle_code="ACE-001",
        item_name="Aceite Vegetal Premier 5L",
        unit="GAL",
        quantity=20.0,
        count_date=date(2026, 7, 24),
        shift="morning",
        operator_id="OP-231",
        session_id=uuid.uuid4(),
        is_validated=True,
        supervisor_id="SUP-1",
        export_timestamp=datetime(2026, 7, 24, 15, 30, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return build_row(**defaults)


def test_csv_column_order():
    csv_content = generate_csv([_sample_row()])
    header = csv_content.split("\n")[0]
    expected = (
        "WAREHOUSE_CODE|ORACLE_CODE|ITEM_NAME|UNIT|QUANTITY|COUNT_DATE|SHIFT|"
        "OPERATOR_ID|SESSION_ID|IS_VALIDATED|SUPERVISOR_ID|EXPORT_TIMESTAMP"
    )
    assert header.strip() == expected


def test_decimal_separator_is_dot():
    row = _sample_row(quantity=20)
    assert row["QUANTITY"] == "20.0000"
    assert "," not in row["QUANTITY"]


def test_quantity_has_four_decimals():
    row = _sample_row(quantity=19.5)
    assert row["QUANTITY"] == "19.5000"


def test_count_date_is_iso_format():
    row = _sample_row(count_date=date(2026, 7, 24))
    assert row["COUNT_DATE"] == "2026-07-24"


def test_export_timestamp_uses_bogota_offset():
    row = _sample_row(export_timestamp=datetime(2026, 7, 24, 15, 30, 0, tzinfo=timezone.utc))
    assert row["EXPORT_TIMESTAMP"].endswith("-05:00")


def test_rejected_items_excluded_flag_stored_correctly():
    row = _sample_row(is_validated=False)
    assert row["IS_VALIDATED"] == "false"


def test_path_traversal_rejected():
    with pytest.raises(ValueError, match="Path traversal"):
        get_export_path(uuid.uuid4(), "../../../etc/passwd", date.today(), "morning")


def test_get_export_path_stays_within_base_dir_for_normal_input():
    path = get_export_path(uuid.uuid4(), "PSL-ALMACEN-GENERAL", date.today(), "morning")
    assert path.is_relative_to(BASE_EXPORT_DIR)


class _FakeCountSession:
    def __init__(self, exported_at=None):
        self.exported_at = exported_at


class _FakeExecResult:
    def __init__(self, scalar_value):
        self._scalar_value = scalar_value

    def scalar(self):
        return self._scalar_value


class _FakeDb:
    def __init__(self, pending_count: int, count_session: _FakeCountSession):
        self._pending_count = pending_count
        self._count_session = count_session

    async def execute(self, *_args, **_kwargs):
        return _FakeExecResult(self._pending_count)

    async def get(self, _model, _pk):
        return self._count_session


async def test_second_export_returns_409():
    db = _FakeDb(pending_count=0, count_session=_FakeCountSession(exported_at=datetime.now(timezone.utc)))

    with pytest.raises(SessionAlreadyExportedError):
        await validate_can_export(uuid.uuid4(), db)


async def test_validate_can_export_blocks_pending_flags():
    db = _FakeDb(pending_count=1, count_session=_FakeCountSession(exported_at=None))

    with pytest.raises(ExportBlockedError):
        await validate_can_export(uuid.uuid4(), db)


async def test_validate_can_export_passes_when_clean():
    db = _FakeDb(pending_count=0, count_session=_FakeCountSession(exported_at=None))

    await validate_can_export(uuid.uuid4(), db)  # no exception raised
