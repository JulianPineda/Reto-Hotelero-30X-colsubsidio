"""Regla B del CLAUDE.md §3.1: deteccion de quiebres de patron en la serie
de los ultimos 3-5 conteos validados, complementaria al umbral puntual.
"""
import statistics

from app.agents.auditor.schemas import TrendResult


def check_trend(quantity: float, historical_series: list[float]) -> TrendResult:
    if len(historical_series) < 3:
        return TrendResult(is_flagged=False, reason="insufficient_history")

    mean = statistics.mean(historical_series)
    stdev = statistics.stdev(historical_series)

    stability_threshold = mean * 0.15  # serie estable si sigma < 15% de la media

    multiplier = 2.0 if stdev < stability_threshold else 3.0

    deviation = abs(quantity - mean)
    is_flagged = stdev > 0 and deviation > multiplier * stdev

    return TrendResult(
        is_flagged=is_flagged,
        series_mean=round(mean, 2),
        series_stdev=round(stdev, 2),
        deviation_sigmas=round(deviation / stdev, 2) if stdev > 0 else 0,
        series_length=len(historical_series),
    )
