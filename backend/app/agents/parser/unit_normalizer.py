"""Maps a colloquial Spanish unit word (as extracted by the LLM) onto the
system's canonical UOM vocabulary: kg, g, L, mL, unit, dozen, case, GAL, oz.
"""
import unicodedata

_CANONICAL_UNITS = ["kg", "g", "L", "mL", "unit", "dozen", "case", "GAL", "oz"]
_CANONICAL_BY_LOWER = {u.lower(): u for u in _CANONICAL_UNITS}

_ALIASES: dict[str, str] = {
    "kilo": "kg", "kilos": "kg", "kilogramo": "kg", "kilogramos": "kg",
    "gramo": "g", "gramos": "g",
    "litro": "L", "litros": "L",
    "mililitro": "mL", "mililitros": "mL",
    "unidad": "unit", "unidades": "unit", "pieza": "unit", "piezas": "unit",
    "docena": "dozen", "docenas": "dozen",
    "caja": "case", "cajas": "case",
    "galon": "GAL", "galones": "GAL",
    "onza": "oz", "onzas": "oz",
}


def _strip_diacritics(s: str) -> str:
    normalized = unicodedata.normalize("NFD", s)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def normalize_unit(raw: str | None) -> str | None:
    """Returns None if unrecognized — the caller must NOT guess a default
    unit (CLAUDE.md §3.3 requires the full confirmed unit, never a
    silently-assumed one)."""
    if raw is None:
        return None
    key = _strip_diacritics(raw.strip().lower())
    if key in _CANONICAL_BY_LOWER:
        return _CANONICAL_BY_LOWER[key]
    return _ALIASES.get(key)
