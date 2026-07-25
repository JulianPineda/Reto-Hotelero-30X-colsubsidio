"""Parser Agent: extracts {article, quantity, unit} from a Spanish
transcript using Gemini 1.5 Flash structured output (ADR-001 — replaces
Claude Haiku, unifies the provider with the Voice Agent from T-005).

VERIFIED against https://ai.google.dev/api/generate-content (fetched
2026-07-25): `client.models.generate_content` (and its async counterpart
`client.aio.models.generate_content`, used below) is current and not
deprecated — a newer "Interactions API" exists alongside it for newer
models, but this classic method is still fully documented and supported.
`system_instruction`, `response_mime_type` and `response_schema` inside
`GenerateContentConfig` are exactly the documented shape — no changes
needed. (Note: the docs' own examples now use "gemini-3.6-flash"; this file
still pins "gemini-1.5-flash" per ADR-001's explicit decision — upgrading
that is a product call, not something to change based on doc examples.)
"""
from __future__ import annotations

from google import genai
from google.genai import types
from pydantic import BaseModel

from app.config import settings

MODEL_NAME = "gemini-1.5-flash"

SYSTEM_PROMPT = """\
Eres un extractor de datos de inventario de un parque de recreación colombiano (Piscilago).
Dado un texto en español de un operario de bodega, extrae EXACTAMENTE:
- article: nombre del producto sin cantidades ni unidades
- quantity: número decimal
- unit: unidad de medida tal como la dijo el operario (sin normalizar)

Si no puedes extraer alguno de los tres campos, devuelve null para ese campo.
Solo devuelve JSON, sin explicaciones adicionales.
"""


class _LLMExtraction(BaseModel):
    article: str | None = None
    quantity: float | None = None
    unit: str | None = None


_client = genai.Client(api_key=settings.gemini_api_key)


async def extract(transcript: str) -> _LLMExtraction:
    response = await _client.aio.models.generate_content(
        model=MODEL_NAME,
        contents=transcript,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=_LLMExtraction,
        ),
    )
    return _LLMExtraction.model_validate_json(response.text)
