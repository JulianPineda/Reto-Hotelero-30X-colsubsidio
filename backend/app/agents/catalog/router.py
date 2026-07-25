from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.catalog import fuzzy_fallback, searcher
from app.agents.catalog.schemas import (
    CatalogFeedbackRequest,
    CatalogFeedbackResponse,
    HomologateRequest,
    HomologateResult,
)
from app.database import get_db
from app.models.catalog_item import CatalogItem
from app.services import learning_service
from app.services.catalog_sync import get_qdrant_client

router = APIRouter(prefix="/agents", tags=["catalog"])


@router.post("/homologate", response_model=HomologateResult)
async def homologate(
    request: HomologateRequest, session: AsyncSession = Depends(get_db)
) -> HomologateResult:
    client = get_qdrant_client()
    try:
        matches = await searcher.vector_search(client, request.article)
        match_method = "vector_search"

        if len(matches) < 3:
            rows = (await session.execute(select(CatalogItem.oracle_code, CatalogItem.name))).all()
            catalog_names = {row.oracle_code: row.name for row in rows}
            fuzzy_matches = fuzzy_fallback.fuzzy_search(request.article, catalog_names)
            if fuzzy_matches:
                matches = fuzzy_matches
                match_method = "fuzzy_fallback"

        return searcher.classify(matches, match_method)
    finally:
        await client.close()


@router.post("/catalog/feedback", response_model=CatalogFeedbackResponse)
async def catalog_feedback(
    request: CatalogFeedbackRequest, session: AsyncSession = Depends(get_db)
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
