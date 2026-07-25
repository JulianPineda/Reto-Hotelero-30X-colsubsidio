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
    model = load_model()
    return model.encode(text, normalize_embeddings=True).tolist()
