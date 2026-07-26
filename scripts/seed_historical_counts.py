"""
Siembra `historical_counts` para que el Auditor Agent tenga con qué
comparar de verdad (CLAUDE.md §3.1) — sin esto, ningún conteo real puede
marcarse como anomalía en una demo: `_load_historical_series()` siempre
devolvería una lista vacía y `check_threshold`/`check_trend` nunca tendrían
una serie que evaluar. Ningún ticket de EPIC-1/EPIC-3 generó este dato;
solo `seed_catalog.py` (catalog_items) y `seed_warehouses.py` (warehouses)
existían.

Genera 5 conteos validados (ventana de CLAUDE.md §3.1, HISTORY_WINDOW=5)
por (bodega, artículo, turno), con cantidades estables (±5% de ruido) en
las últimas 5 semanas — una serie "tranquila" que un Auditor NO debería
marcar, para que una anomalía real durante la demo resalte con claridad
contra ese fondo.

COBERTURA (ampliada — antes: 2 bodegas x 8 artículos x 1 turno):
- Las 48 bodegas reales de Piscilago, no solo 2 — cualquier bodega que un
  operario elija durante la demo ya tiene historial.
- Artículos diversos por categoría (hasta `ITEMS_PER_CATEGORY` por cada una
  de las ~25 categorías del catálogo: alimentos, medicamentos, papelería,
  ferretería, dotación, zoológico, etc. — CLAUDE.md §1), no solo los
  primeros 8 por oracle_code (que antes caían todos en una sola categoría
  alfabéticamente temprana).
- Los 3 turnos (morning/afternoon/night), no solo "morning" — sin esto,
  la Regla C de CLAUDE.md §3.1 ("priorizar el mismo turno... si hay <3,
  completar con otros turnos") nunca tenía datos reales con que ejercitar
  ninguna de sus dos ramas.

Idempotente: respeta el índice único (warehouse_id, catalog_item_id,
count_date, shift) antes de insertar.

Uso:
    python scripts/seed_historical_counts.py
"""
import asyncio
import random
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.catalog_item import CatalogItem  # noqa: E402
from app.models.count_session import CountSession  # noqa: E402,F401 — registers count_sessions for HistoricalCount's FK
from app.models.historical_count import HistoricalCount  # noqa: E402
from app.models.warehouse import Warehouse  # noqa: E402

ITEMS_PER_CATEGORY = 3
HISTORY_WEEKS = 5
SHIFTS = ["morning", "afternoon", "night"]


def _stable_series(base: float, weeks: int) -> list[float]:
    return [round(base * random.uniform(0.95, 1.05), 2) for _ in range(weeks)]


def _pick_diverse_items(all_items: list[CatalogItem]) -> list[CatalogItem]:
    """Up to `ITEMS_PER_CATEGORY` items per catalog category, instead of an
    arbitrary flat slice that would land entirely inside whichever category
    sorts first — see module docstring."""
    by_category: dict[str, list[CatalogItem]] = {}
    for item in all_items:
        by_category.setdefault(item.category, []).append(item)
    return [item for group in by_category.values() for item in group[:ITEMS_PER_CATEGORY]]


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        warehouses = (await session.execute(select(Warehouse).order_by(Warehouse.code))).scalars().all()
        all_items = (
            (await session.execute(select(CatalogItem).order_by(CatalogItem.category, CatalogItem.oracle_code)))
            .scalars()
            .all()
        )
        items = _pick_diverse_items(all_items)

        if not warehouses or not items:
            print(
                "No hay bodegas o artículos todavía — corre seed_warehouses.py "
                "y seed_catalog.py primero."
            )
            return

        created = 0
        today = date.today()
        for warehouse in warehouses:
            for item in items:
                for shift in SHIFTS:
                    base_quantity = random.uniform(20, 100)
                    series = _stable_series(base_quantity, HISTORY_WEEKS)
                    for week_index, quantity in enumerate(series):
                        count_date = today - timedelta(weeks=week_index + 1)
                        existing = (
                            await session.execute(
                                select(HistoricalCount).where(
                                    HistoricalCount.warehouse_id == warehouse.id,
                                    HistoricalCount.catalog_item_id == item.id,
                                    HistoricalCount.count_date == count_date,
                                    HistoricalCount.shift == shift,
                                )
                            )
                        ).scalar_one_or_none()
                        if existing is not None:
                            continue
                        session.add(
                            HistoricalCount(
                                warehouse_id=warehouse.id,
                                catalog_item_id=item.id,
                                oracle_code=item.oracle_code,
                                count_date=count_date,
                                shift=shift,
                                quantity=Decimal(str(quantity)),
                                is_validated=True,
                            )
                        )
                        created += 1

            await session.commit()

        print(
            f"OK: {created} conteos históricos creados "
            f"({len(warehouses)} bodegas x {len(items)} artículos x {len(SHIFTS)} turnos x {HISTORY_WEEKS} semanas)"
        )


if __name__ == "__main__":
    asyncio.run(seed())
