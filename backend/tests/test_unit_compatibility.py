import pytest

from app.services.unit_compatibility import IncompatibleUnitError, is_unit_compatible, validate_unit_compatibility


@pytest.mark.parametrize("unit", ["kg", "g", "lb", "oz", "unit", "dozen", "case"])
def test_solid_catalog_unit_allows_mass_and_count_units(unit):
    assert is_unit_compatible("kg", unit) is True


@pytest.mark.parametrize("unit", ["L", "mL", "GAL"])
def test_solid_catalog_unit_rejects_volume_units(unit):
    assert is_unit_compatible("kg", unit) is False


@pytest.mark.parametrize("unit", ["L", "mL", "GAL"])
def test_liquid_catalog_unit_allows_volume_units(unit):
    assert is_unit_compatible("L", unit) is True


@pytest.mark.parametrize("unit", ["kg", "g", "lb", "oz", "unit", "dozen", "case"])
def test_liquid_catalog_unit_rejects_mass_and_count_units(unit):
    assert is_unit_compatible("L", unit) is False


@pytest.mark.parametrize("unit", ["unit", "dozen", "case"])
def test_count_catalog_unit_allows_count_units(unit):
    assert is_unit_compatible("unit", unit) is True


@pytest.mark.parametrize("unit", ["kg", "L"])
def test_count_catalog_unit_rejects_mass_and_volume_units(unit):
    assert is_unit_compatible("unit", unit) is False


def test_unknown_catalog_unit_fails_open():
    """A catalog data gap shouldn't block persistence — only the three
    canonical units data/catalog.csv actually uses have a known dimension."""
    assert is_unit_compatible("weird-unit", "L") is True


def test_validate_raises_with_a_spanish_message_naming_the_article():
    with pytest.raises(IncompatibleUnitError, match="Leche Entera 1L"):
        validate_unit_compatibility("L", "Leche Entera 1L", "kg")


def test_validate_does_not_raise_for_a_compatible_unit():
    validate_unit_compatibility("kg", "Harina de Trigo", "lb")
