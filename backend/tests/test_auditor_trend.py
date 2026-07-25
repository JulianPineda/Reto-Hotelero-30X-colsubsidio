from app.agents.auditor.trend import check_trend


def test_stable_series_large_break():
    # Serie estable: [90, 92, 88, 91, 89] -> mean~90, sigma~1.58
    # Conteo actual: 14 -> ruptura dramatica -> FLAG
    result = check_trend(14.0, [90, 92, 88, 91, 89])
    assert result.is_flagged is True


def test_stable_series_normal_value():
    # Serie: [90, 92, 88] -> mean=90, conteo=91 -> NO flag
    result = check_trend(91.0, [90, 92, 88])
    assert result.is_flagged is False


def test_unstable_series_high_threshold():
    # Serie inestable: [10, 50, 30, 80, 20] -> sigma alto -> umbral mas laxo
    result = check_trend(45.0, [10, 50, 30, 80, 20])
    assert result.is_flagged is False  # dentro del rango esperado aunque sigma alto


def test_insufficient_history():
    # < 3 conteos -> no aplica deteccion de tendencia
    result = check_trend(50.0, [40, 60])
    assert result.is_flagged is False
    assert result.reason == "insufficient_history"
