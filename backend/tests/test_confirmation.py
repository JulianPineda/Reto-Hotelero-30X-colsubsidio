from app.agents.voice.confirmation import build_digit_confirmation


def test_two_digit_quantity_gets_digit_breakdown():
    digit_by_digit, display_text = build_digit_confirmation(90.0, "GAL", "Aceite Vegetal Premier 5L")

    assert digit_by_digit == "nueve, cero"
    assert display_text == "¿Nueve, cero: 90 GAL de Aceite Vegetal Premier 5L?"


def test_single_digit_quantity_has_no_breakdown():
    digit_by_digit, display_text = build_digit_confirmation(5.0, "kg", "sal")

    assert digit_by_digit is None
    assert display_text == "¿5 kg de sal?"


def test_decimal_quantity_digit_count_ignores_the_dot():
    # 4.5 -> digits "45" (dot stripped) -> two-digit breakdown still applies
    digit_by_digit, display_text = build_digit_confirmation(4.5, "kg", "arroz")

    assert digit_by_digit == "cuatro, cinco"
    assert display_text == "¿Cuatro, cinco: 4.5 kg de arroz?"
