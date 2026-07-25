"""Digit-by-digit confirmation text (CLAUDE.md 3.3).

NOTE ON A SPEC DISCREPANCY: EPIC-2-voice.md's own T-008 inline pseudocode
joins the raw numeric characters (e.g. "9, 0"), but CLAUDE.md's worked
example and T-008's own acceptance criterion both expect Spanish digit
WORDS ("Nueve, cero"). CLAUDE.md is the declared "fuente de verdad
operativa" — this implementation follows the acceptance criterion + digit
words, not the ticket's inline code sample.
"""

_DIGIT_WORDS = {
    "0": "cero", "1": "uno", "2": "dos", "3": "tres", "4": "cuatro",
    "5": "cinco", "6": "seis", "7": "siete", "8": "ocho", "9": "nueve",
}


def build_digit_confirmation(quantity: float, unit: str, article_name: str) -> tuple[str | None, str]:
    """Returns (digit_by_digit, display_text). `digit_by_digit` is None when
    the quantity has a single digit — no breakdown is shown in that case.
    """
    quantity_str = str(int(quantity)) if quantity == int(quantity) else str(quantity)
    digit_chars = quantity_str.replace(".", "")

    if len(digit_chars) < 2:
        return None, f"¿{quantity_str} {unit} de {article_name}?"

    digit_words = ", ".join(_DIGIT_WORDS[d] for d in digit_chars)
    capitalized = digit_words[0].upper() + digit_words[1:]
    return digit_words, f"¿{capitalized}: {quantity_str} {unit} de {article_name}?"
