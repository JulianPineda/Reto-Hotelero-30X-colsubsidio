"""Shared catalog <-> Qdrant sync helpers.

Embeds catalog items and keeps their canonical Qdrant point in sync with the
`catalog_items` row. Reused by scripts/seed_catalog.py (bulk seed) and by the
continuous-learning path (T-010) that upserts individual synonyms.

Embedding itself is delegated to `app.agents.catalog.embedder` (T-009) — that
is the single embedding-model singleton for the whole process; keeping a
second SentenceTransformer instance here would double the ~120MB memory cost
whenever the seed script and the running app share a process.
"""
from __future__ import annotations

import uuid

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.catalog.embedder import EMBEDDING_DIM, embed
from app.config import settings
from app.models.catalog_item import CatalogItem


def get_qdrant_client() -> AsyncQdrantClient:
    return AsyncQdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)


async def ensure_collection(client: AsyncQdrantClient) -> None:
    exists = await client.collection_exists(settings.qdrant_collection_name)
    if not exists:
        await client.create_collection(
            collection_name=settings.qdrant_collection_name,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )


def canonical_point_id(oracle_code: str) -> str:
    """Deterministic UUID5 so re-running the seed is idempotent — the same
    oracle_code always maps to the same Qdrant point id."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"catalog_item:{oracle_code}"))


async def upsert_catalog_item(
    client: AsyncQdrantClient,
    session: AsyncSession,
    item: CatalogItem,
) -> str:
    """Embed one canonical catalog item, upsert its point into Qdrant, and
    write the resulting point id back onto the (uncommitted) Postgres row."""
    vector = embed(item.name)
    point_id = canonical_point_id(item.oracle_code)
    await client.upsert(
        collection_name=settings.qdrant_collection_name,
        points=[
            PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "oracle_code": item.oracle_code,
                    "name": item.name,
                    "category": item.category,
                    "unit": item.unit,
                    "is_perishable": item.is_perishable,
                    "source": "canonical",
                },
            )
        ],
    )
    item.qdrant_point_id = point_id
    session.add(item)
    return point_id


def synonym_point_id(oracle_code: str, synonym: str) -> str:
    """Deterministic UUID5 so re-upserting the same (oracle_code, synonym)
    pair updates the same Qdrant point instead of creating a duplicate —
    T-010's stated idempotency ("Qdrant upsert es idempotente por point_id")
    only holds if the id is derived, not random."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"synonym:{oracle_code}:{synonym}"))


async def upsert_synonym(client: AsyncQdrantClient, oracle_code: str, synonym: str) -> str:
    """Embed a learned synonym as its OWN Qdrant point (T-010) — kept
    separate from the canonical point so an individual bad synonym can be
    deleted without touching the canonical entry."""
    vector = embed(synonym)
    point_id = synonym_point_id(oracle_code, synonym)
    await client.upsert(
        collection_name=settings.qdrant_collection_name,
        points=[
            PointStruct(
                id=point_id,
                vector=vector,
                payload={"oracle_code": oracle_code, "name": synonym, "source": "synonym"},
            )
        ],
    )
    return point_id
