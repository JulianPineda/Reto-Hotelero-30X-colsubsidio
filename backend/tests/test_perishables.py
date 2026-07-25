from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.services.perishables import (
    PerishableItemMissingExpiryError,
    compute_traffic_light,
    validate_perishable_item,
)


def test_traffic_light_red_within_3_days():
    today = date(2026, 7, 25)
    assert compute_traffic_light(today + timedelta(days=3), today=today) == "red"
    assert compute_traffic_light(today, today=today) == "red"


def test_traffic_light_yellow_between_4_and_7_days():
    today = date(2026, 7, 25)
    assert compute_traffic_light(today + timedelta(days=4), today=today) == "yellow"
    assert compute_traffic_light(today + timedelta(days=7), today=today) == "yellow"


def test_traffic_light_green_8_or_more_days():
    today = date(2026, 7, 25)
    assert compute_traffic_light(today + timedelta(days=8), today=today) == "green"
    assert compute_traffic_light(today + timedelta(days=30), today=today) == "green"


def test_traffic_light_red_when_already_expired():
    today = date(2026, 7, 25)
    assert compute_traffic_light(today - timedelta(days=1), today=today) == "red"


def test_validate_perishable_item_raises_when_missing_expiry():
    catalog_item = SimpleNamespace(is_perishable=True, name="Leche UHT")

    with pytest.raises(PerishableItemMissingExpiryError, match="Leche UHT"):
        validate_perishable_item(catalog_item, expiry_date=None)


def test_validate_perishable_item_passes_when_expiry_present():
    catalog_item = SimpleNamespace(is_perishable=True, name="Leche UHT")
    validate_perishable_item(catalog_item, expiry_date=date(2026, 8, 1))  # no exception


def test_validate_non_perishable_item_never_requires_expiry():
    catalog_item = SimpleNamespace(is_perishable=False, name="Tornillo")
    validate_perishable_item(catalog_item, expiry_date=None)  # no exception
