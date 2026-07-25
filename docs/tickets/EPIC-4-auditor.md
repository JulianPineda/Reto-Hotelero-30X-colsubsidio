# EPIC 4 — Auditor Agent
**Sprint 2 · ~3 días · 7 puntos**

Prerequisito: T-002 (schema con `historical_counts`), T-003 (datos de catálogo).

---

## T-011 — Threshold Anomaly Detector
**Puntos:** 2 | **Asignado a:** Ejecutor

### Descripción
Implementa las reglas A del CLAUDE.md §3.1: anomalía si la desviación es > 20% O > 5 unidades absolutas.

### Archivos a crear
- `backend/app/agents/auditor/threshold.py`
- `backend/app/agents/auditor/schemas.py`
- `backend/app/agents/auditor/router.py` — `POST /api/v1/agents/audit` (skeleton)
- `backend/tests/test_auditor_threshold.py`

### Implementación
```python
def check_threshold(quantity: float, historical_avg: float) -> ThresholdResult:
    """
    FLAG si: abs(quantity - avg) / avg > 0.20
          O si: abs(quantity - avg) > 5 unidades
    Ambas condiciones son independientes.
    """
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
```

### Test cases críticos
```python
# test_auditor_threshold.py

def test_flag_by_percentage():
    # avg=100, quantity=125 → delta_pct=25% → FLAG
    result = check_threshold(125.0, 100.0)
    assert result.is_flagged is True

def test_flag_by_absolute():
    # avg=10, quantity=16 → delta_abs=6 > 5 → FLAG (aunque pct=60% también)
    result = check_threshold(16.0, 10.0)
    assert result.is_flagged is True

def test_no_flag_within_range():
    # avg=100, quantity=105 → delta_pct=5%, delta_abs=5 → NO flag (límite exacto)
    result = check_threshold(105.0, 100.0)
    assert result.is_flagged is False

def test_flag_boundary_exactly_over():
    # avg=100, quantity=121 → delta_pct=21% > 20% → FLAG
    result = check_threshold(121.0, 100.0)
    assert result.is_flagged is True

def test_no_historical_data():
    # Sin histórico: no se puede calcular → no flag
    result = check_threshold(100.0, historical_avg=0)
    assert result.is_flagged is False
```

### Criterio de aceptación
```bash
pytest backend/tests/test_auditor_threshold.py -v  # 5 tests, todos pasan
```

---

## T-012 — Trend Anomaly Detector
**Puntos:** 3 | **Asignado a:** Ejecutor

### Descripción
Implementa la regla B del CLAUDE.md §3.1: detección de quiebres de patrón en la serie de últimos 3-5 conteos, complementaria al umbral puntual.

### Archivos a crear
- `backend/app/agents/auditor/trend.py`
- `backend/tests/test_auditor_trend.py`

### Algoritmo de tendencia
```python
def check_trend(quantity: float, historical_series: list[float]) -> TrendResult:
    """
    Requiere mínimo 3 conteos históricos.
    Detecta si el valor actual rompe el patrón de estabilidad de la serie.

    Estrategia:
    1. Calcular la desviación estándar de la serie (σ)
    2. Si σ < umbral_estabilidad (serie estable):
       - FLAG si abs(quantity - media) > 2σ (ruptura de patrón estable)
    3. Si σ ≥ umbral_estabilidad (serie inestable):
       - Usar umbral más laxo: abs(quantity - media) > 3σ
    4. Si < 3 conteos: no aplicar detección de tendencia
    """
    if len(historical_series) < 3:
        return TrendResult(is_flagged=False, reason="insufficient_history")

    mean = statistics.mean(historical_series)
    stdev = statistics.stdev(historical_series)

    STABILITY_THRESHOLD = mean * 0.15  # serie estable si σ < 15% de la media

    if stdev < STABILITY_THRESHOLD:
        # Serie estable → flag si rompe más de 2 desviaciones estándar
        multiplier = 2.0
    else:
        # Serie inestable → umbral más laxo para evitar fatiga de alertas
        multiplier = 3.0

    deviation = abs(quantity - mean)
    is_flagged = stdev > 0 and deviation > multiplier * stdev

    return TrendResult(
        is_flagged=is_flagged,
        series_mean=round(mean, 2),
        series_stdev=round(stdev, 2),
        deviation_sigmas=round(deviation / stdev, 2) if stdev > 0 else 0,
        series_length=len(historical_series),
    )
```

### Test cases críticos
```python
# test_auditor_trend.py

def test_stable_series_large_break():
    # Serie estable: [90, 92, 88, 91, 89] → mean≈90, σ≈1.58
    # Conteo actual: 14 → ruptura dramática → FLAG
    result = check_trend(14.0, [90, 92, 88, 91, 89])
    assert result.is_flagged is True

def test_stable_series_normal_value():
    # Serie: [90, 92, 88] → mean=90, conteo=91 → NO flag
    result = check_trend(91.0, [90, 92, 88])
    assert result.is_flagged is False

def test_unstable_series_high_threshold():
    # Serie inestable: [10, 50, 30, 80, 20] → σ alto → umbral más laxo
    result = check_trend(45.0, [10, 50, 30, 80, 20])
    assert result.is_flagged is False  # dentro del rango esperado aunque σ alto

def test_insufficient_history():
    # < 3 conteos → no aplica detección de tendencia
    result = check_trend(50.0, [40, 60])
    assert result.is_flagged is False
    assert result.reason == "insufficient_history"
```

### Integración en `router.py`
El endpoint `POST /api/v1/agents/audit`:
1. Lee histórico de `historical_counts` (últimos 5, mismo turno primero).
2. Calcula `historical_avg` para threshold.
3. Extrae serie de cantidades para trend.
4. Combina resultados:
   - Si ambos flag: `flag_type = "both"`
   - Si solo threshold: `flag_type = "threshold"`
   - Si solo trend: `flag_type = "trend"`
   - Si ninguno: `flag_type = null`, `is_flagged = false`

### Criterio de aceptación
```bash
pytest backend/tests/test_auditor_trend.py -v  # 4 tests, todos pasan
```

---

## T-013 — NL Explainer: Español con Cifras Exactas
**Puntos:** 2 | **Asignado a:** Ejecutor

### Descripción
Genera la explicación en lenguaje natural del Auditor Agent, en español, incluyendo las cifras exactas requeridas por CLAUDE.md §3.1.

### Archivos a crear
- `backend/app/agents/auditor/explainer.py`

### Estrategia
Para la demo, usar una plantilla determinista antes de invocar el LLM (más rápido y predecible):

```python
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
```

Usar Gemini 1.5 Flash (ADR-001) solo para casos donde la explicación plantilla sea insuficiente (ej. sin histórico suficiente pero hay otras señales).

### Criterio de aceptación
- Explicación incluye: porcentaje exacto, valor dictado, promedio histórico, número de conteos.
- Siempre en español. Sin bullet points ni markdown (spec §13 — instrucciones del Voice Agent).
- Latencia de generación < 300 ms (plantilla) o < 1 500 ms (LLM).
