from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from app.agents.parser import extractor
from app.agents.parser.schemas import ParseRequest, ParseResponse
from app.agents.parser.unit_normalizer import normalize_unit
from app.agents.voice.schemas import OperatorClaims
from app.api.deps import get_current_operator

router = APIRouter(prefix="/agents", tags=["parser"])


@router.post("/parse", response_model=ParseResponse)
async def parse_transcript(
    request: ParseRequest, _operator: OperatorClaims = Depends(get_current_operator)
) -> ParseResponse:
    raw = await extractor.extract(request.transcript)

    if raw.article is None and raw.quantity is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "PARSE_FAILED",
                "correlation_id": str(uuid4()),
                "message": "No se pudo extraer artículo o cantidad del texto.",
            },
        )

    # Gemini's structured output has no native per-field confidence score;
    # this is a coarse heuristic (all three fields present vs. a partial
    # extraction), not a calibrated model probability.
    confidence = 1.0 if raw.article and raw.quantity is not None and raw.unit else 0.5

    return ParseResponse(
        article=raw.article,
        quantity=raw.quantity,
        unit=normalize_unit(raw.unit),
        confidence=confidence,
        raw_tokens=request.transcript.split(),
    )
