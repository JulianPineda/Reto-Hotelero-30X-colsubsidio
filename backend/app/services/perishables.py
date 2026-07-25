"""Perecederos (T-017): validacion de fecha de vencimiento y calculo de
semaforo (CLAUDE.md §3.6).

Nota: el ticket llama a la excepcion "PeishableItemMissingExpiryError" en su
pseudocodigo (typo evidente de "Perishable") — corregido aqui al nombre bien
escrito, ya que no hay ningun contrato externo que dependa del nombre mal
escrito.
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from app.models.catalog_item import CatalogItem

TrafficLightColor = Literal["red", "yellow", "green"]


class PerishableItemMissingExpiryError(Exception):
    pass


def compute_traffic_light(expiry_date: date, today: date | None = None) -> TrafficLightColor:
    reference = today or date.today()
    days_remaining = (expiry_date - reference).days

    if days_remaining <= 3:
        return "red"
    elif days_remaining <= 7:
        return "yellow"
    return "green"


def validate_perishable_item(catalog_item: CatalogItem, expiry_date: date | None) -> None:
    """Lanza error si el articulo es perecedero y no tiene fecha de vencimiento."""
    if catalog_item.is_perishable and expiry_date is None:
        raise PerishableItemMissingExpiryError(
            f"El artículo '{catalog_item.name}' es perecedero y requiere fecha de vencimiento."
        )
