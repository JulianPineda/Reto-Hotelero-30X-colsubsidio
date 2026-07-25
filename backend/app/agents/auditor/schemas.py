from uuid import UUID

from pydantic import BaseModel


class ThresholdResult(BaseModel):
    is_flagged: bool
    delta_pct: float | None = None
    delta_abs: float | None = None
    historical_avg: float | None = None


class TrendResult(BaseModel):
    is_flagged: bool
    reason: str | None = None
    series_mean: float | None = None
    series_stdev: float | None = None
    deviation_sigmas: float | None = None
    series_length: int | None = None


class HistoricalCountPoint(BaseModel):
    date: str
    quantity: float
    shift: str | None = None


class AuditRequest(BaseModel):
    oracle_code: str
    quantity: float
    unit: str
    warehouse_id: UUID
    shift: str


class ThresholdDetail(BaseModel):
    delta_pct: float
    delta_abs: float
    historical_avg: float


class TrendDetail(BaseModel):
    is_flagged: bool
    series_mean: float
    series_stdev: float
    deviation_sigmas: float
    series_length: int


class AuditResult(BaseModel):
    is_flagged: bool
    flag_type: str | None  # threshold | trend | both | None
    explanation: str | None
    quantity: float
    unit: str
    threshold_detail: ThresholdDetail | None = None
    trend_detail: TrendDetail | None = None
    historical_counts: list[HistoricalCountPoint]
