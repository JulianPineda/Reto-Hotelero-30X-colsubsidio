"""sentence-transformers wrapper (T-009).

Single source of truth for the embedding model across the whole app —
the FastAPI lifespan calls `load_model()` once at startup so the first
request doesn't pay the ~120MB download / model-load cost, but `embed()`
also lazily loads it if that hasn't happened yet (e.g. when called from
`scripts/seed_catalog.py`, which runs outside the FastAPI lifespan).
"""
from __future__ import annotations

from sentence_transformers import SentenceTransformer

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384

_model: SentenceTransformer | None = None


def load_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed(text: str) -> list[float]:
    """Lowercases before encoding — confirmed live: this model treats case
    as meaningfully different content, not noise to ignore. Catalog names
    are stored UPPERCASE (`data/catalog.csv`) while operators dictate in
    natural (lower/mixed) case, so without this normalization the SAME
    phrase in different case scored only ~0.71 cosine similarity against
    itself (`cosine('filete de basa', 'FILETE DE BASA') = 0.7136`) — below
    several unrelated catalog items' scores against the lowercase query
    (e.g. 'COMPOTA' at 0.83), so an unrelated item would auto-accept
    (>=0.80) instead of the correct one. Lowercasing both sides at the one
    choke point every embed() caller shares (catalog_sync.py's indexing,
    searcher.py's queries, learning_service.py's taught synonyms) fixes
    this without threshold surgery."""
    model = load_model()
    return model.encode(text.lower(), normalize_embeddings=True).tolist()
