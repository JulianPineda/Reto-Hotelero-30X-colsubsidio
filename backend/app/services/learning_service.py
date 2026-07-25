"""Continuous learning (T-010): when an operator corrects a homologation,
record the (raw_article -> oracle_code) pair as a synonym and index it in
Qdrant so future dictations of that phrase resolve directly.

Idempotent: UNIQUE(catalog_item_id, synonym) in Postgres, and the Qdrant
point id is derived deterministically (see catalog_sync.synonym_point_id)
so re-upserting never creates a duplicate point.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog_item import CatalogItem
from app.models.synonym_embedding import SynonymEmbedding
from app.services.catalog_sync import get_qdrant_client, upsert_synonym


@dataclass
class CorrectionResult:
    synonym_created: bool
    qdrant_updated: bool


async def record_correction(
    session: AsyncSession, oracle_code: str, synonym: str, created_by: str
) -> CorrectionResult:
    catalog_item = (
        await session.execute(select(CatalogItem).where(CatalogItem.oracle_code == oracle_code))
    ).scalar_one_or_none()
    if catalog_item is None:
        raise ValueError(f"oracle_code desconocido: {oracle_code!r}")

    existing = (
        await session.execute(
            select(SynonymEmbedding).where(
                SynonymEmbedding.catalog_item_id == catalog_item.id,
                SynonymEmbedding.synonym == synonym,
            )
        )
    ).scalar_one_or_none()

    client = get_qdrant_client()
    try:
        point_id = await upsert_synonym(client, oracle_code, synonym)
    finally:
        await client.close()

    if existing is not None:
        existing.usage_count += 1
        synonym_created = False
    else:
        session.add(
            SynonymEmbedding(
                catalog_item_id=catalog_item.id,
                synonym=synonym,
                qdrant_point_id=point_id,
                source="operator_correction",
                usage_count=1,
                created_by=created_by,
            )
        )
        synonym_created = True

    return CorrectionResult(synonym_created=synonym_created, qdrant_updated=True)
