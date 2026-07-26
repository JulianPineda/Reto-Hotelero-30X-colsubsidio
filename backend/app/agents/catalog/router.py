from fastapi import APIRouter, Depends
from qdrant_client import AsyncQdrantClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.catalog import fuzzy_fallback, searcher
from app.agents.catalog.schemas import (
    CatalogFeedbackRequest,
    CatalogFeedbackResponse,
    HomologateRequest,
    HomologateResult,
)
from app.agents.voice.schemas import OperatorClaims
from app.api.deps import require_role
from app.database import get_db
from app.models.catalog_item import CatalogItem
from app.services import learning_service
from app.services.catalog_sync import get_qdrant_client

router = APIRouter(prefix="/agents", tags=["catalog"])


async def _enrich_with_canonical_fields(
    session: AsyncSession, matches: list[dict]
) -> list[dict]:
    """Overwrites each match's `name`/`unit`/`is_perishable` with the
    canonical `catalog_items` row for its `oracle_code` — Postgres, not
    Qdrant, is the source of truth for these fields.

    Without this, a match against a learned-synonym point (T-010,
    `catalog_sync.upsert_synonym`) or a fuzzy_fallback match returns the raw
    synonym text as `name` and `unit`/`is_perishable` as `None` (neither is
    stored in a synonym point's payload). Confirmed live: homologating a
    synonym after teaching it back returned `name` = the operator's own raw
    phrase instead of the catalog item's real name — cosmetically wrong, but
    `is_perishable=None` is a real CLAUDE.md §3.6 violation, since a
    perishable item matched this way would silently skip the mandatory
    expiry_date requirement (`None` is falsy, same as "not perishable").
    """
    oracle_codes = {m["oracle_code"] for m in matches}
    rows = (
        await session.execute(
            select(CatalogItem).where(CatalogItem.oracle_code.in_(oracle_codes))
        )
    ).scalars()
    canonical = {item.oracle_code: item for item in rows}

    enriched = []
    for match in matches:
        item = canonical.get(match["oracle_code"])
        enriched.append(
            {
                **match,
                "name": item.name if item is not None else match["name"],
                "unit": item.unit if item is not None else match["unit"],
                "is_perishable": item.is_perishable if item is not None else match["is_perishable"],
            }
        )
    return enriched


async def run_homologation(
    session: AsyncSession, client: AsyncQdrantClient, article: str
) -> HomologateResult:
    """Shared Catalog Agent entry point (CLAUDE.md §3.2) — called by both the
    HTTP `/homologate` endpoint and the Voice Agent's PTT session
    (`voice/session.py`), so the two callers can never drift apart.
    """
    matches = await searcher.vector_search(client, article)
    match_method = "vector_search"

    if len(matches) < 3:
        rows = (await session.execute(select(CatalogItem.oracle_code, CatalogItem.name))).all()
        catalog_names = {row.oracle_code: row.name for row in rows}
        fuzzy_matches = fuzzy_fallback.fuzzy_search(article, catalog_names)
        if fuzzy_matches:
            matches = fuzzy_matches
            match_method = "fuzzy_fallback"

    if matches:
        matches = await _enrich_with_canonical_fields(session, matches)

    return searcher.classify(matches, match_method)


@router.post("/homologate", response_model=HomologateResult)
async def homologate(
    request: HomologateRequest,
    session: AsyncSession = Depends(get_db),
    _operator: OperatorClaims = Depends(require_role("operator")),
) -> HomologateResult:
    client = get_qdrant_client()
    try:
        return await run_homologation(session, client, request.article)
    finally:
        await client.close()


@router.post("/catalog/feedback", response_model=CatalogFeedbackResponse)
async def catalog_feedback(
    request: CatalogFeedbackRequest,
    session: AsyncSession = Depends(get_db),
    _operator: OperatorClaims = Depends(require_role("operator")),
) -> CatalogFeedbackResponse:
    result = await learning_service.record_correction(
        session,
        oracle_code=request.oracle_code,
        synonym=request.raw_article,
        created_by=request.operator_id,
    )
    await session.commit()
    return CatalogFeedbackResponse(
        synonym_created=result.synonym_created, qdrant_updated=result.qdrant_updated
    )
