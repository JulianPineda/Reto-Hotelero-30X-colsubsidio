from app.agents.auditor.threshold import check_threshold


def test_flag_by_percentage():
    # avg=100, quantity=125 -> delta_pct=25% -> FLAG
    result = check_threshold(125.0, 100.0)
    assert result.is_flagged is True


def test_flag_by_absolute():
    # avg=10, quantity=16 -> delta_abs=6 > 5 -> FLAG (aunque pct=60% tambien)
    result = check_threshold(16.0, 10.0)
    assert result.is_flagged is True


def test_no_flag_within_range():
    # avg=100, quantity=105 -> delta_pct=5%, delta_abs=5 -> NO flag (limite exacto)
    result = check_threshold(105.0, 100.0)
    assert result.is_flagged is False


def test_flag_boundary_exactly_over():
    # avg=100, quantity=121 -> delta_pct=21% > 20% -> FLAG
    result = check_threshold(121.0, 100.0)
    assert result.is_flagged is True


def test_no_historical_data():
    # Sin historico: no se puede calcular -> no flag
    result = check_threshold(100.0, historical_avg=0)
    assert result.is_flagged is False
