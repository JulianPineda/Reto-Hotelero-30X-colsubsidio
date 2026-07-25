"""rapidfuzz fallback for short/ambiguous articles where the vector search
returns too few candidates to be useful (T-009: "cuando el embedding arroja
< 3 resultados, ej. 'sal', 'aceite'").
"""
from __future__ import annotations

from rapidfuzz import fuzz, process


def fuzzy_search(article: str, catalog_names: dict[str, str], limit: int = 5) -> list[dict]:
    """`catalog_names` maps oracle_code -> name. Returns matches shaped like
    `searcher.vector_search()`'s output so `searcher.classify()` can consume
    either. rapidfuzz's WRatio is 0-100; divided by 100 to share the same
    0-1 scale as Qdrant's cosine score — this is an approximation, not an
    equivalence, but the ticket doesn't define separate fuzzy thresholds.
    """
    matches = process.extract(article, catalog_names, scorer=fuzz.WRatio, limit=limit, score_cutoff=50)
    return [
        {
            "oracle_code": oracle_code,
            "name": name,
            "unit": None,
            "is_perishable": None,
            "score": score / 100,
        }
        for name, score, oracle_code in matches
    ]
