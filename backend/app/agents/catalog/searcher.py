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

# Confirmed live: this embedding model's absolute scores aren't always a
# reliable confidence signal on their own for short, technical Spanish
# grocery terms — "aceite vegetal" scored 0.8726 against 'ACEITE DE
# AJONJOLI' and 0.8644 against the correct-ish generic 'ACEITE', a ~0.008
# gap that's within the model's noise floor, yet both clear
# AUTO_ACCEPT_THRESHOLD so the old code silently picked the sesame oil.
# When the top-2 candidates are this close, the model isn't actually
# confident which one is right — CLAUDE.md §3.2's "score >= 0.80 ->
# auto-accept" implicitly assumes the top score reflects real confidence,
# which breaks down when it has a near-tied runner-up. Falling through to
# the alternatives band in that case asks the operator instead of guessing.
AMBIGUOUS_MARGIN = 0.03


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
    runner_up = matches[1] if len(matches) > 1 else None
    top_is_ambiguous = (
        runner_up is not None and (top["score"] - runner_up["score"]) < AMBIGUOUS_MARGIN
    )

    if top["score"] >= AUTO_ACCEPT_THRESHOLD and not top_is_ambiguous:
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
