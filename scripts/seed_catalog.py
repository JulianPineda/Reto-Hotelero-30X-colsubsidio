"""
Lee data/catalog.csv, genera embeddings (paraphrase-multilingual-MiniLM-L12-v2)
y hace upsert de cada articulo en Postgres (catalog_items) + Qdrant.

Idempotente: el point id de Qdrant se deriva deterministicamente del
oracle_code (uuid5), asi que correr este script varias veces actualiza los
mismos puntos en lugar de duplicarlos.

Uso:
    python scripts/seed_catalog.py --csv data/catalog.csv
"""
import argparse
import asyncio
import csv
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.catalog_item import CatalogItem  # noqa: E402
from app.services.catalog_sync import (  # noqa: E402
    ensure_collection,
    get_qdrant_client,
    upsert_catalog_item,
)


def _parse_bool(value: str) -> bool:
    return value.strip().lower() == "true"


def _parse_shelf_days(value: str) -> int | None:
    value = value.strip()
    return int(value) if value else None


def read_catalog_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [
            {
                "oracle_code": row["oracle_code"],
                "name": row["name"],
                "unit": row["unit"],
                "category": row["category"] or None,
                "is_perishable": _parse_bool(row["is_perishable"]),
                "default_shelf_days": _parse_shelf_days(row["default_shelf_days"]),
            }
            for row in reader
        ]


async def seed(csv_path: Path) -> None:
    rows = read_catalog_csv(csv_path)
    client = get_qdrant_client()
    try:
        await ensure_collection(client)
        async with AsyncSessionLocal() as session:
            existing_rows = (await session.execute(select(CatalogItem))).scalars().all()
            existing = {ci.oracle_code: ci for ci in existing_rows}

            for row in rows:
                item = existing.get(row["oracle_code"])
                if item is None:
                    item = CatalogItem(**row)
                    session.add(item)
                    await session.flush()
                else:
                    item.name = row["name"]
                    item.unit = row["unit"]
                    item.category = row["category"]
                    item.is_perishable = row["is_perishable"]
                    item.default_shelf_days = row["default_shelf_days"]
                await upsert_catalog_item(client, session, item)

            await session.commit()
    finally:
        await client.close()

    print(f"OK: {len(rows)} articulos indexados en PG, {len(rows)} puntos upserted en Qdrant")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    default_csv = Path(__file__).parent.parent / "data" / "catalog.csv"
    parser.add_argument("--csv", default=str(default_csv), help="Ruta a data/catalog.csv")
    args = parser.parse_args()
    asyncio.run(seed(Path(args.csv)))


if __name__ == "__main__":
    main()
