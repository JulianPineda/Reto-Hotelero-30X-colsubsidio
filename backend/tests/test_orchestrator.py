import uuid
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.agents.auditor.schemas import AuditResult
from app.models.catalog_item import CatalogItem
from app.models.count_item import CountItem
from app.schemas.events import EventType
from app.services import orchestrator
from app.services.orchestrator import SessionNotFoundError, UnknownOracleCodeError, persist_count_item
from app.services.perishables import PerishableItemMissingExpiryError


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalar(self):
        return self._value


class _FakeSession:
    """`responses` is popped in call order — persist_count_item issues at
    most two `execute()` calls (CatalogItem lookup, then the sequence-number
    max), and the CatalogItem lookup only happens when `oracle_code` is
    given, so the caller must supply exactly the responses that scenario
    will actually trigger (see the `_responses_*` helpers below).
    `run_audit` is monkeypatched in every test below so its own internal
    queries never run against this fake."""

    def __init__(self, count_session, responses):
        self._count_session = count_session
        self._responses = list(responses)
        self.added: list = []
        self.committed = False

    async def get(self, _model, _pk):
        return self._count_session

    async def execute(self, *_args, **_kwargs):
        return self._responses.pop(0)

    def add(self, obj) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    async def commit(self) -> None:
        self.committed = True


def _responses_with_catalog_lookup(catalog_item, max_sequence: int) -> list[_FakeResult]:
    """oracle_code given -> CatalogItem lookup happens, then (if it found a
    row and didn't raise) the sequence-number max."""
    return [_FakeResult(catalog_item), _FakeResult(max_sequence)]


def _responses_without_catalog_lookup(max_sequence: int) -> list[_FakeResult]:
    """oracle_code is None -> CatalogItem lookup is skipped entirely; the
    sequence-number max is the only execute() call."""
    return [_FakeResult(max_sequence)]


def _count_session(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=uuid.uuid4(), warehouse_id=uuid.uuid4(), shift="morning", total_items=0, flagged_items=0
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _catalog_item(**overrides) -> CatalogItem:
    item = CatalogItem()
    item.id = overrides.get("id", uuid.uuid4())
    item.oracle_code = overrides.get("oracle_code", "HAR-001")
    item.name = overrides.get("name", "Harina de Trigo Especial 50kg")
    item.unit = overrides.get("unit", "kg")
    item.is_perishable = overrides.get("is_perishable", False)
    return item


def _no_flag_audit_result(**overrides) -> AuditResult:
    defaults = dict(
        is_flagged=False,
        flag_type=None,
        explanation=None,
        quantity=20.0,
        unit="kg",
        threshold_detail=None,
        trend_detail=None,
        historical_counts=[],
    )
    defaults.update(overrides)
    return AuditResult(**defaults)


async def test_persists_item_and_emits_item_created(monkeypatch):
    count_session = _count_session()
    catalog_item = _catalog_item()
    session = _FakeSession(count_session, _responses_with_catalog_lookup(catalog_item, max_sequence=0))

    async def fake_run_audit(_session, _request):
        return _no_flag_audit_result()

    monkeypatch.setattr(orchestrator, "run_audit", fake_run_audit)

    result = await persist_count_item(
        session,
        session_id=count_session.id,
        oracle_code="HAR-001",
        article_name="Harina de Trigo Especial 50kg",
        raw_transcript="veinte kilos de harina",
        quantity=20.0,
        unit="kg",
        homologation_score=0.94,
        sin_homologar=False,
        expiry_date=None,
        is_offline=False,
        confidence_stt=0.9,
        created_by="OP-1",
    )

    assert result.is_flagged is False
    assert result.sequence_in_session == 1
    assert count_session.total_items == 1
    assert count_session.flagged_items == 0

    count_items = [obj for obj in session.added if isinstance(obj, CountItem)]
    assert len(count_items) == 1
    assert count_items[0].oracle_code == "HAR-001"
    assert count_items[0].sequence_in_session == 1

    created_events = [e for e in session.added if getattr(e, "event_type", None) == EventType.ITEM_CREATED]
    assert len(created_events) == 1
    assert created_events[0].payload["oracle_code"] == "HAR-001"


async def test_flagged_item_updates_session_counter(monkeypatch):
    count_session = _count_session(total_items=5, flagged_items=1)
    catalog_item = _catalog_item()
    session = _FakeSession(count_session, _responses_with_catalog_lookup(catalog_item, max_sequence=5))

    async def fake_run_audit(_session, _request):
        return _no_flag_audit_result(is_flagged=True, flag_type="threshold", explanation="Caída del 84.4%.")

    monkeypatch.setattr(orchestrator, "run_audit", fake_run_audit)

    result = await persist_count_item(
        session,
        session_id=count_session.id,
        oracle_code="HAR-001",
        article_name="Harina de Trigo Especial 50kg",
        raw_transcript=None,
        quantity=14.0,
        unit="kg",
        homologation_score=0.9,
        sin_homologar=False,
        expiry_date=None,
        is_offline=False,
        confidence_stt=None,
        created_by="OP-1",
    )

    assert result.is_flagged is True
    assert result.flag_type == "threshold"
    assert result.sequence_in_session == 6
    assert count_session.total_items == 6
    assert count_session.flagged_items == 2


async def test_sin_homologar_item_skips_the_auditor(monkeypatch):
    count_session = _count_session()
    session = _FakeSession(count_session, _responses_without_catalog_lookup(max_sequence=0))

    audit_spy = SimpleNamespace(called=False)

    async def fake_run_audit(_session, _request):
        audit_spy.called = True
        return _no_flag_audit_result()

    monkeypatch.setattr(orchestrator, "run_audit", fake_run_audit)

    result = await persist_count_item(
        session,
        session_id=count_session.id,
        oracle_code=None,
        article_name="articulo desconocido xyz",
        raw_transcript=None,
        quantity=3.0,
        unit="unit",
        homologation_score=None,
        sin_homologar=True,
        expiry_date=None,
        is_offline=False,
        confidence_stt=None,
        created_by="OP-1",
    )

    assert audit_spy.called is False
    assert result.is_flagged is False
    assert result.flag_type is None


async def test_perishable_item_computes_traffic_light(monkeypatch):
    count_session = _count_session()
    catalog_item = _catalog_item(oracle_code="LAC-001", name="Leche Entera 1L", is_perishable=True)
    session = _FakeSession(count_session, _responses_with_catalog_lookup(catalog_item, max_sequence=0))

    async def fake_run_audit(_session, _request):
        return _no_flag_audit_result()

    monkeypatch.setattr(orchestrator, "run_audit", fake_run_audit)

    result = await persist_count_item(
        session,
        session_id=count_session.id,
        oracle_code="LAC-001",
        article_name="Leche Entera 1L",
        raw_transcript=None,
        quantity=2.0,
        unit="L",
        homologation_score=0.9,
        sin_homologar=False,
        expiry_date=date.today() + timedelta(days=2),
        is_offline=False,
        confidence_stt=None,
        created_by="OP-1",
    )

    assert result.traffic_light == "red"


async def test_perishable_item_missing_expiry_date_raises(monkeypatch):
    count_session = _count_session()
    catalog_item = _catalog_item(oracle_code="LAC-001", name="Leche Entera 1L", is_perishable=True)
    # Raises right after the CatalogItem lookup, before the sequence-max
    # query ever runs — only one response needed.
    session = _FakeSession(count_session, [_FakeResult(catalog_item)])

    async def fake_run_audit(_session, _request):
        return _no_flag_audit_result()

    monkeypatch.setattr(orchestrator, "run_audit", fake_run_audit)

    with pytest.raises(PerishableItemMissingExpiryError):
        await persist_count_item(
            session,
            session_id=count_session.id,
            oracle_code="LAC-001",
            article_name="Leche Entera 1L",
            raw_transcript=None,
            quantity=2.0,
            unit="L",
            homologation_score=0.9,
            sin_homologar=False,
            expiry_date=None,
            is_offline=False,
            confidence_stt=None,
            created_by="OP-1",
        )


async def test_unknown_oracle_code_raises():
    count_session = _count_session()
    # CatalogItem lookup returns nothing -> raises immediately, no further
    # execute() calls.
    session = _FakeSession(count_session, [_FakeResult(None)])

    with pytest.raises(UnknownOracleCodeError):
        await persist_count_item(
            session,
            session_id=count_session.id,
            oracle_code="DOES-NOT-EXIST",
            article_name="algo",
            raw_transcript=None,
            quantity=1.0,
            unit="unit",
            homologation_score=None,
            sin_homologar=False,
            expiry_date=None,
            is_offline=False,
            confidence_stt=None,
            created_by="OP-1",
        )


async def test_missing_session_raises():
    # session.get() returns None -> raises before any execute() call.
    session = _FakeSession(count_session=None, responses=[])

    with pytest.raises(SessionNotFoundError):
        await persist_count_item(
            session,
            session_id=uuid.uuid4(),
            oracle_code=None,
            article_name="algo",
            raw_transcript=None,
            quantity=1.0,
            unit="unit",
            homologation_score=None,
            sin_homologar=True,
            expiry_date=None,
            is_offline=False,
            confidence_stt=None,
            created_by="OP-1",
        )
