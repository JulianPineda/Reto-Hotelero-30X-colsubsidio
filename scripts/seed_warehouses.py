"""
Lee data/warehouses.csv y hace upsert de cada bodega en Postgres
(warehouses). Nunca especificado por ningun ticket de EPIC-1 — T-003 genera
data/warehouses.csv via import_catalog.py pero ningun script lo carga a la
tabla; sin esto GET /api/v1/warehouses (y por tanto WarehouseSelect) no
tiene nada que listar.

Idempotente: busca por `code` (columna UNIQUE) antes de insertar.

Uso:
    python scripts/seed_warehouses.py --csv data/warehouses.csv
"""
import argparse
import asyncio
import csv
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.warehouse import Warehouse  # noqa: E402


def read_warehouses_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [{"code": row["warehouse_code"], "name": row["name"]} for row in reader]


async def seed(csv_path: Path) -> None:
    rows = read_warehouses_csv(csv_path)
    async with AsyncSessionLocal() as session:
        existing_rows = (await session.execute(select(Warehouse))).scalars().all()
        existing = {w.code: w for w in existing_rows}

        created = 0
        for row in rows:
            warehouse = existing.get(row["code"])
            if warehouse is None:
                session.add(Warehouse(code=row["code"], name=row["name"]))
                created += 1
            else:
                warehouse.name = row["name"]

        await session.commit()

    print(f"OK: {len(rows)} bodegas procesadas ({created} nuevas, {len(rows) - created} actualizadas)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    default_csv = Path(__file__).parent.parent / "data" / "warehouses.csv"
    parser.add_argument("--csv", default=str(default_csv), help="Ruta a data/warehouses.csv")
    args = parser.parse_args()
    asyncio.run(seed(Path(args.csv)))


if __name__ == "__main__":
    main()
