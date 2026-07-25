import uuid
from datetime import date
from types import SimpleNamespace

from app.agents.auditor.explainer import build_explanation
from app.agents.auditor.router import audit
from app.agents.auditor.schemas import (
    AuditRequest,
    AuditResult,
    HistoricalCountPoint,
    ThresholdDetail,
    TrendDetail,
)


def test_build_explanation_includes_exact_figures():
    result = AuditResult(
        is_flagged=True,
        flag_type="threshold",
        explanation=None,
        quantity=14.0,
        unit="kg",
        threshold_detail=ThresholdDetail(delta_pct=84.4, delta_abs=76.0, historical_avg=90.0),
        trend_detail=None,
        historical_counts=[
            HistoricalCountPoint(date="2026-07-17", quantity=90.0, shift="morning"),
            HistoricalCountPoint(date="2026-07-10", quantity=92.0, shift="morning"),
            HistoricalCountPoint(date="2026-07-03", quantity=88.0, shift="morning"),
        ],
    )

    explanation = build_explanation(result)

    assert "14.0 kg" in explanation
    assert "84.4%" in explanation
    assert "90.0 kg" in explanation
    assert "3 conteos" in explanation
    assert "inferior" in explanation


def test_build_explanation_no_flags_returns_default_message():
    result = AuditResult(
        is_flagged=False,
        flag_type=None,
        explanation=None,
        quantity=20.0,
        unit="kg",
        threshold_detail=None,
        trend_detail=None,
        historical_counts=[],
    )

    assert build_explanation(result) == "Valor dentro del rango esperado."


def test_build_explanation_appends_trend_sentence_when_flagged():
    result = AuditResult(
        is_flagged=True,
        flag_type="both",
        explanation=None,
        quantity=14.0,
        unit="kg",
        threshold_detail=ThresholdDetail(delta_pct=84.4, delta_abs=76.0, historical_avg=90.0),
        trend_detail=TrendDetail(
            is_flagged=True, series_mean=90.0, series_stdev=1.58, deviation_sigmas=48.1, series_length=3
        ),
        historical_counts=[
            HistoricalCountPoint(date="2026-07-17", quantity=90.0, shift="morning"),
            HistoricalCountPoint(date="2026-07-10", quantity=92.0, shift="morning"),
            HistoricalCountPoint(date="2026-07-03", quantity=88.0, shift="morning"),
        ],
    )

    explanation = build_explanation(result)

    assert "rompe el patrón estable" in explanation
    assert "48.1 desviaciones estándar" in explanation


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeExecResult:
    def __init__(self, rows=None, scalar=None):
        self._rows = rows
        self._scalar = scalar

    def scalars(self):
        return _FakeScalars(self._rows or [])

    def scalar_one_or_none(self):
        return self._scalar


class _FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)

    async def execute(self, *_args, **_kwargs):
        return self._responses.pop(0)


async def test_audit_endpoint_flags_threshold_break_with_same_shift_history():
    catalog_item = SimpleNamespace(id=uuid.uuid4(), oracle_code="HAR-001")
    history_rows = [
        SimpleNamespace(id=uuid.uuid4(), quantity=90.0, count_date=date(2026, 7, 17), shift="morning"),
        SimpleNamespace(id=uuid.uuid4(), quantity=92.0, count_date=date(2026, 7, 10), shift="morning"),
        SimpleNamespace(id=uuid.uuid4(), quantity=88.0, count_date=date(2026, 7, 3), shift="morning"),
    ]
    session = _FakeSession(
        responses=[_FakeExecResult(scalar=catalog_item), _FakeExecResult(rows=history_rows)]
    )

    request = AuditRequest(
        oracle_code="HAR-001", quantity=14.0, unit="kg", warehouse_id=uuid.uuid4(), shift="morning"
    )
    result = await audit(request, session=session, _operator=None)

    assert result.is_flagged is True
    assert result.flag_type in {"threshold", "both"}
    assert result.explanation is not None
    assert "84.4%" in result.explanation
    assert len(result.historical_counts) == 3


async def test_audit_endpoint_no_flag_when_within_range():
    catalog_item = SimpleNamespace(id=uuid.uuid4(), oracle_code="HAR-001")
    history_rows = [
        SimpleNamespace(id=uuid.uuid4(), quantity=20.0, count_date=date(2026, 7, 17), shift="morning"),
        SimpleNamespace(id=uuid.uuid4(), quantity=19.5, count_date=date(2026, 7, 10), shift="morning"),
        SimpleNamespace(id=uuid.uuid4(), quantity=21.0, count_date=date(2026, 7, 3), shift="morning"),
    ]
    session = _FakeSession(
        responses=[_FakeExecResult(scalar=catalog_item), _FakeExecResult(rows=history_rows)]
    )

    request = AuditRequest(
        oracle_code="HAR-001", quantity=20.0, unit="kg", warehouse_id=uuid.uuid4(), shift="morning"
    )
    result = await audit(request, session=session, _operator=None)

    assert result.is_flagged is False
    assert result.flag_type is None
    assert result.explanation is None
