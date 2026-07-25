from datetime import date

from app.agents.voice.date_parser import build_spoken_date_confirmation, parse_spoken_date


def test_parse_explicit_year_words():
    result = parse_spoken_date("quince de agosto de 2026")
    assert result == date(2026, 8, 15)


def test_parse_digit_day_month_year():
    result = parse_spoken_date("15 08 2026")
    assert result == date(2026, 8, 15)


def test_parse_without_year_future_date_stays_this_year():
    today = date(2026, 1, 1)
    result = parse_spoken_date("quince de agosto", today=today)
    assert result == date(2026, 8, 15)


def test_parse_without_year_past_date_rolls_to_next_year():
    today = date(2026, 12, 1)
    result = parse_spoken_date("quince de agosto", today=today)
    assert result == date(2027, 8, 15)


def test_parse_primero_means_day_one():
    result = parse_spoken_date("primero de enero de 2027")
    assert result == date(2027, 1, 1)


def test_parse_returns_none_when_day_missing():
    assert parse_spoken_date("en agosto") is None


def test_parse_returns_none_when_month_missing():
    assert parse_spoken_date("el quince") is None


def test_build_spoken_date_confirmation_matches_expected_words():
    assert build_spoken_date_confirmation(date(2026, 8, 15)) == "quince de agosto de dos mil veintiséis"


def test_build_spoken_date_confirmation_day_one_uses_primero():
    assert build_spoken_date_confirmation(date(2027, 1, 1)) == "primero de enero de dos mil veintisiete"


def test_build_spoken_date_confirmation_round_year():
    assert build_spoken_date_confirmation(date(2030, 3, 30)) == "treinta de marzo de dos mil treinta"
