"""Valida que la unidad dictada/capturada sea dimensionalmente compatible
con la unidad canónica del catálogo — nueva regla de negocio: productos
sólidos/al peso solo admiten unidades de masa o por unidad/pieza; líquidos
solo admiten unidades de volumen. `data/catalog.csv` (import_catalog.py)
solo usa tres unidades canónicas por artículo: "kg", "L", "unit" — esas son
las únicas claves que `_ALLOWED_BY_CATALOG_UNIT` necesita cubrir.
"""
from __future__ import annotations

_MASS_UNITS = {"kg", "g", "lb", "oz"}
_VOLUME_UNITS = {"L", "mL", "GAL"}
_COUNT_UNITS = {"unit", "dozen", "case"}

_ALLOWED_BY_CATALOG_UNIT: dict[str, set[str]] = {
    "kg": _MASS_UNITS | _COUNT_UNITS,  # sólidos/al peso: masa o por unidad/pieza
    "L": _VOLUME_UNITS,  # líquidos: solo volumen
    "unit": _COUNT_UNITS,  # empacados discretos: solo por unidad/pieza
}


class IncompatibleUnitError(Exception):
    pass


def is_unit_compatible(catalog_unit: str, provided_unit: str) -> bool:
    """True if `catalog_unit` has no known dimension grouping (fail open —
    don't block on a catalog data gap) or `provided_unit` belongs to it."""
    allowed = _ALLOWED_BY_CATALOG_UNIT.get(catalog_unit)
    if allowed is None:
        return True
    return provided_unit in allowed


def validate_unit_compatibility(catalog_unit: str, catalog_name: str, provided_unit: str) -> None:
    if is_unit_compatible(catalog_unit, provided_unit):
        return
    kind = "líquido (solo admite unidades de volumen)" if catalog_unit == "L" else "sólido o por unidad (no admite unidades de volumen)"
    raise IncompatibleUnitError(
        f"'{catalog_name}' es un producto {kind} — la unidad '{provided_unit}' no es compatible."
    )
