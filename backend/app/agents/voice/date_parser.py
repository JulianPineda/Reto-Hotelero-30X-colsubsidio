"""Spoken-date parsing + spoken-date confirmation text for the perishables
re-ask flow (CLAUDE.md §3.6 — `is_perishable` items require a non-null
`expiry_date`; the Voice Agent must re-ask for it before the item can reach
the Catalog/Auditor pipeline instead of letting `perishables.py` reject it
after the fact).
"""
from __future__ import annotations

import re
from datetime import date

_MONTHS: dict[str, int] = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_MONTH_NAMES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
    7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}

_DAY_WORDS: dict[str, int] = {
    "primero": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
    "dieciseis": 16, "dieciséis": 16, "diecisiete": 17, "dieciocho": 18,
    "diecinueve": 19, "veinte": 20, "veintiuno": 21, "veintidos": 22, "veintidós": 22,
    "veintitres": 23, "veintitrés": 23, "veinticuatro": 24, "veinticinco": 25,
    "veintiseis": 26, "veintiséis": 26, "veintisiete": 27, "veintiocho": 28,
    "veintinueve": 29, "treinta": 30, "treinta y uno": 31,
}

_ONES = {
    0: "cero", 1: "uno", 2: "dos", 3: "tres", 4: "cuatro", 5: "cinco",
    6: "seis", 7: "siete", 8: "ocho", 9: "nueve", 10: "diez",
    11: "once", 12: "doce", 13: "trece", 14: "catorce", 15: "quince",
    16: "dieciséis", 17: "diecisiete", 18: "dieciocho", 19: "diecinueve",
    20: "veinte",
}
_TENS = {
    30: "treinta", 40: "cuarenta", 50: "cincuenta", 60: "sesenta",
    70: "setenta", 80: "ochenta", 90: "noventa",
}
# "veinti-" compounds carry accents ("veintidós", "veintitrés",
# "veintiséis") that the standalone ones-words don't ("dos", "tres",
# "seis") — naively concatenating "veinti" + _ONES[n] silently drops them.
_TWENTIES = {
    21: "veintiuno", 22: "veintidós", 23: "veintitrés", 24: "veinticuatro",
    25: "veinticinco", 26: "veintiséis", 27: "veintisiete", 28: "veintiocho",
    29: "veintinueve",
}


def _cardinal_to_words(n: int) -> str:
    """0-99 only — enough range for day-of-month and the two-digit part of
    a year in the 2000s."""
    if n <= 20:
        return _ONES[n]
    if n < 30:
        return _TWENTIES[n]
    tens = (n // 10) * 10
    remainder = n % 10
    if remainder == 0:
        return _TENS[tens]
    return f"{_TENS[tens]} y {_ONES[remainder]}"


def _extract_day(text: str) -> int | None:
    match = re.search(r"\b(\d{1,2})\b", text)
    if match:
        day = int(match.group(1))
        return day if 1 <= day <= 31 else None
    for word in sorted(_DAY_WORDS, key=len, reverse=True):
        if word in text:
            return _DAY_WORDS[word]
    return None


def _extract_month(text: str) -> int | None:
    for name, value in _MONTHS.items():
        if name in text:
            return value
    numbers = re.findall(r"\b(\d{1,2})\b", text)
    if len(numbers) >= 2:
        candidate = int(numbers[1])
        if 1 <= candidate <= 12:
            return candidate
    return None


def _extract_year(text: str) -> int | None:
    match = re.search(r"\b(20\d{2})\b", text)
    return int(match.group(1)) if match else None


def parse_spoken_date(transcript: str, *, today: date | None = None) -> date | None:
    """Best-effort parse of a spoken Spanish date ("quince de agosto",
    "15 de agosto de 2026"). Returns None if day or month can't be
    recovered. When no year is spoken and the resulting date already passed
    this year, rolls forward to next year — an expiry date can't be in the
    past.
    """
    today = today or date.today()
    text = transcript.lower().strip()

    day = _extract_day(text)
    month = _extract_month(text)
    if day is None or month is None:
        return None

    year = _extract_year(text)
    if year is not None:
        try:
            return date(year, month, day)
        except ValueError:
            return None

    try:
        candidate = date(today.year, month, day)
    except ValueError:
        return None
    if candidate < today:
        try:
            candidate = date(today.year + 1, month, day)
        except ValueError:
            return None
    return candidate


def build_spoken_date_confirmation(expiry_date: date) -> str:
    """"quince de agosto de dos mil veintiséis" — used to read the parsed
    date back to the operator before committing it (barge-in / re-dictar
    still applies, same as quantity confirmation)."""
    day_words = "primero" if expiry_date.day == 1 else _cardinal_to_words(expiry_date.day)
    month_words = _MONTH_NAMES[expiry_date.month]

    year = expiry_date.year
    thousands, remainder = divmod(year, 1000)
    thousands_words = "mil" if thousands == 1 else f"{_cardinal_to_words(thousands)} mil"
    year_words = thousands_words if remainder == 0 else f"{thousands_words} {_cardinal_to_words(remainder)}"

    return f"{day_words} de {month_words} de {year_words}"
