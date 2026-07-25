import os
import uuid

import pytest
from fastapi import HTTPException

from app.agents.parser import extractor
from app.agents.parser.router import parse_transcript
from app.agents.parser.schemas import ParseRequest
from app.agents.parser.unit_normalizer import normalize_unit


def test_normalize_unit_maps_colloquial_spanish():
    assert normalize_unit("kilos") == "kg"
    assert normalize_unit("galones") == "GAL"
    assert normalize_unit("galón") == "GAL"
    assert normalize_unit("unidades") == "unit"


def test_normalize_unit_passes_through_canonical():
    assert normalize_unit("kg") == "kg"
    assert normalize_unit("GAL") == "GAL"


def test_normalize_unit_returns_none_for_unknown():
    assert normalize_unit("xyz") is None
    assert normalize_unit(None) is None


async def test_parse_transcript_normalizes_unit(monkeypatch):
    async def fake_extract(transcript: str):
        return extractor._LLMExtraction(article="harina de trigo", quantity=20.0, unit="kilos")

    monkeypatch.setattr(extractor, "extract", fake_extract)

    request = ParseRequest(transcript="veinte kilos de harina de trigo", session_id=uuid.uuid4())
    result = await parse_transcript(request, _operator=None)

    assert result.article == "harina de trigo"
    assert result.quantity == 20.0
    assert result.unit == "kg"


async def test_parse_transcript_normalizes_galones(monkeypatch):
    async def fake_extract(transcript: str):
        return extractor._LLMExtraction(article="aceite vegetal", quantity=90.0, unit="galones")

    monkeypatch.setattr(extractor, "extract", fake_extract)

    request = ParseRequest(transcript="noventa galones de aceite vegetal", session_id=uuid.uuid4())
    result = await parse_transcript(request, _operator=None)

    assert result.article == "aceite vegetal"
    assert result.quantity == 90.0
    assert result.unit == "GAL"


async def test_parse_transcript_allows_quantity_only(monkeypatch):
    """'catorce' -> {article: null, quantity: 14, unit: null} per the
    ticket's own acceptance example — quantity alone is not a hard failure."""

    async def fake_extract(transcript: str):
        return extractor._LLMExtraction(article=None, quantity=14.0, unit=None)

    monkeypatch.setattr(extractor, "extract", fake_extract)

    request = ParseRequest(transcript="catorce", session_id=uuid.uuid4())
    result = await parse_transcript(request, _operator=None)

    assert result.article is None
    assert result.quantity == 14.0
    assert result.unit is None


async def test_parse_transcript_raises_422_when_nothing_extracted(monkeypatch):
    async def fake_extract(transcript: str):
        return extractor._LLMExtraction(article=None, quantity=None, unit=None)

    monkeypatch.setattr(extractor, "extract", fake_extract)

    request = ParseRequest(transcript="ruido ininteligible aaaa", session_id=uuid.uuid4())
    with pytest.raises(HTTPException) as exc_info:
        await parse_transcript(request, _operator=None)

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "PARSE_FAILED"


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_LLM_TESTS") != "1",
    reason="opt-in live integration check — set RUN_LIVE_LLM_TESTS=1 with a real GEMINI_API_KEY to run",
)
async def test_extract_live_against_gemini():
    result = await extractor.extract("veinte kilos de harina de trigo")
    assert result.article is not None
    assert result.quantity == 20.0
