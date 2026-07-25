"""Regla A del CLAUDE.md §3.1: FLAG si la desviacion es > 20% O > 5
unidades absolutas. Ambas condiciones son independientes — cualquiera sola
es suficiente para marcar.
"""
from app.agents.auditor.schemas import ThresholdResult


def check_threshold(quantity: float, historical_avg: float) -> ThresholdResult:
    if historical_avg == 0:
        return ThresholdResult(is_flagged=False)

    delta_abs = abs(quantity - historical_avg)
    delta_pct = delta_abs / historical_avg * 100

    is_flagged = delta_pct > 20.0 or delta_abs > 5.0

    return ThresholdResult(
        is_flagged=is_flagged,
        delta_pct=round(delta_pct, 1),
        delta_abs=round(delta_abs, 2),
        historical_avg=round(historical_avg, 2),
    )
