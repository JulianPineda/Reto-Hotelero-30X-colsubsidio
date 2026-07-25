"""Vector search against Qdrant + threshold classification (CLAUDE.md §3.2).

CAVEAT: uses `client.search()` per this ticket's own pseudocode. Newer
qdrant-client releases (post-1.9) deprecate `search()` in favor of
`query_points()` with a near-identical signature — if the installed version
warns/errors, swap the call, the rest of this module is unaffected.
"""
from __future__ import annotations

from qdrant_client import AsyncQdrantClient

from app.agents.catalog import embedder
from app.agents.catalog.schemas import Alternative, HomologateResult
from app.config import settings

AUTO_ACCEPT_THRESHOLD = 0.80
ALTERNATIVES_THRESHOLD = 0.50
SEARCH_LIMIT = 5


async def vector_search(client: AsyncQdrantClient, article: str) -> list[dict]:
    query_vector = embedder.embed(article)
    results = await client.search(
        collection_name=settings.qdrant_collection_name,
        query_vector=query_vector,
        limit=SEARCH_LIMIT,
        score_threshold=ALTERNATIVES_THRESHOLD,
    )
    return [
        {
            "oracle_code": point.payload["oracle_code"],
            "name": point.payload["name"],
            "unit": point.payload.get("unit"),
            "is_perishable": point.payload.get("is_perishable"),
            "score": point.score,
        }
        for point in results
    ]


def classify(matches: list[dict], match_method: str = "vector_search") -> HomologateResult:
    """CLAUDE.md §3.2 thresholds:
        score >= 0.80            -> auto-accept
        0.50 <= score < 0.80     -> top-3 alternatives, requires operator pick
        no matches (< 0.50)      -> sin_homologar
    """
    if not matches:
        return HomologateResult(
            oracle_code=None,
            name=None,
            unit=None,
            score=0.0,
            is_perishable=None,
            match_method="none",
            alternatives=[],
            requires_operator_selection=False,
            sin_homologar=True,
        )

    top = matches[0]

    if top["score"] >= AUTO_ACCEPT_THRESHOLD:
        return HomologateResult(
            oracle_code=top["oracle_code"],
            name=top["name"],
            unit=top["unit"],
            score=top["score"],
            is_perishable=top["is_perishable"],
            match_method=match_method,
            alternatives=[],
            requires_operator_selection=False,
            sin_homologar=False,
        )

    if top["score"] >= ALTERNATIVES_THRESHOLD:
        alternatives = [
            Alternative(oracle_code=m["oracle_code"], name=m["name"], score=m["score"])
            for m in matches[:3]
        ]
        return HomologateResult(
            oracle_code=None,
            name=None,
            unit=None,
            score=top["score"],
            is_perishable=None,
            match_method=match_method,
            alternatives=alternatives,
            requires_operator_selection=True,
            sin_homologar=False,
        )

    return HomologateResult(
        oracle_code=None,
        name=None,
        unit=None,
        score=top["score"],
        is_perishable=None,
        match_method=match_method,
        alternatives=[],
        requires_operator_selection=False,
        sin_homologar=True,
    )
