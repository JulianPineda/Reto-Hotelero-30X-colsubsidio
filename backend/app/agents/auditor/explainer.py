"""NL Explainer (T-013): siempre en espanol, con porcentaje exacto, valor
dictado, promedio historico y numero de conteos (CLAUDE.md §3.1). Plantilla
determinista — sin llamada a LLM; el ticket deja la puerta abierta a Gemini
1.5 Flash solo para casos sin histórico suficiente, no implementado aquí
(no hay ninguna necesidad de red/API key en este archivo).
"""
from app.agents.auditor.schemas import AuditResult


def build_explanation(audit_result: AuditResult) -> str:
    parts = []

    if audit_result.threshold_detail:
        d = audit_result.threshold_detail
        direction = "superior" if audit_result.quantity > d.historical_avg else "inferior"
        parts.append(
            f"La cantidad registrada ({audit_result.quantity} {audit_result.unit}) "
            f"es {d.delta_pct:.1f}% {direction} al promedio histórico "
            f"({d.historical_avg} {audit_result.unit}) de los últimos "
            f"{len(audit_result.historical_counts)} conteos en esta bodega."
        )

    if audit_result.trend_detail and audit_result.trend_detail.is_flagged:
        t = audit_result.trend_detail
        parts.append(
            f"Además, rompe el patrón estable de la serie "
            f"({', '.join(str(c.quantity) for c in audit_result.historical_counts[-3:])}) "
            f"en {t.deviation_sigmas:.1f} desviaciones estándar."
        )

    return " ".join(parts) if parts else "Valor dentro del rango esperado."
