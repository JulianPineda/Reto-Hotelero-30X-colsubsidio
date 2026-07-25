import uuid
from types import SimpleNamespace

from app.agents.catalog import fuzzy_fallback, searcher
from app.agents.catalog.router import homologate
from app.agents.catalog.schemas import HomologateRequest


def test_classify_auto_accepts_high_score():
    matches = [
        {
            "oracle_code": "ACE-001",
            "name": "Aceite Vegetal Premier 5L",
            "unit": "GAL",
            "is_perishable": False,
            "score": 0.94,
        }
    ]

    result = searcher.classify(matches)

    assert result.oracle_code == "ACE-001"
    assert result.score == 0.94
    assert result.match_method == "vector_search"
    assert result.requires_operator_selection is False
    assert result.sin_homologar is False
    assert result.alternatives == []


def test_classify_returns_alternatives_for_mid_score():
    matches = [
        {
            "oracle_code": "HAR-001",
            "name": "Harina de Trigo Especial 50kg",
            "unit": "kg",
            "is_perishable": False,
            "score": 0.74,
        },
        {
            "oracle_code": "HAR-002",
            "name": "Harina de Trigo Integral 1kg",
            "unit": "kg",
            "is_perishable": False,
            "score": 0.68,
        },
    ]

    result = searcher.classify(matches)

    assert result.oracle_code is None
    assert result.requires_operator_selection is True
    assert result.sin_homologar is False
    assert len(result.alternatives) == 2
    assert [a.oracle_code for a in result.alternatives] == ["HAR-001", "HAR-002"]


def test_classify_sin_homologar_when_no_matches():
    result = searcher.classify([])

    assert result.sin_homologar is True
    assert result.requires_operator_selection is False
    assert result.oracle_code is None
    assert result.match_method == "none"


def test_fuzzy_search_matches_similar_names():
    catalog_names = {
        "ACE-001": "Aceite Vegetal Premier 5L",
        "ACE-002": "Aceite de Oliva Extra Virgen",
        "HAR-001": "Harina de Trigo Especial 50kg",
    }

    matches = fuzzy_fallback.fuzzy_search("aceite", catalog_names)

    assert len(matches) >= 1
    oracle_codes = {m["oracle_code"] for m in matches}
    assert oracle_codes & {"ACE-001", "ACE-002"}


def test_fuzzy_search_returns_nothing_for_unrelated_text():
    catalog_names = {"ACE-001": "Aceite Vegetal Premier 5L"}

    matches = fuzzy_fallback.fuzzy_search("xyznonexistent", catalog_names)

    assert matches == []


class _FakeResultRows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, *_args, **_kwargs):
        return _FakeResultRows(self._rows)


async def _noop_close():
    pass


def _fake_get_qdrant_client():
    return SimpleNamespace(close=_noop_close)


async def test_homologate_uses_vector_search_when_enough_matches(monkeypatch):
    async def fake_vector_search(client, article):
        return [
            {
                "oracle_code": "HAR-001",
                "name": "Harina de Trigo Especial 50kg",
                "unit": "kg",
                "is_perishable": False,
                "score": 0.94,
            },
            {
                "oracle_code": "HAR-002",
                "name": "Harina de Trigo Integral 1kg",
                "unit": "kg",
                "is_perishable": False,
                "score": 0.70,
            },
            {
                "oracle_code": "HAR-003",
                "name": "Harina de Maiz",
                "unit": "kg",
                "is_perishable": False,
                "score": 0.60,
            },
        ]

    monkeypatch.setattr(searcher, "vector_search", fake_vector_search)
    monkeypatch.setattr("app.agents.catalog.router.get_qdrant_client", _fake_get_qdrant_client)

    request = HomologateRequest(article="harina de trigo", warehouse_id=uuid.uuid4())
    result = await homologate(request, session=_FakeSession(rows=[]), _operator=None)

    assert result.oracle_code == "HAR-001"
    assert result.match_method == "vector_search"


async def test_homologate_falls_back_to_fuzzy_when_few_matches(monkeypatch):
    async def fake_vector_search(client, article):
        return []  # < 3 matches triggers fuzzy fallback

    monkeypatch.setattr(searcher, "vector_search", fake_vector_search)
    monkeypatch.setattr("app.agents.catalog.router.get_qdrant_client", _fake_get_qdrant_client)

    rows = [
        SimpleNamespace(oracle_code="ACE-001", name="Aceite Vegetal Premier 5L"),
        SimpleNamespace(oracle_code="ACE-002", name="Aceite de Oliva Extra Virgen"),
    ]

    request = HomologateRequest(article="aceite", warehouse_id=uuid.uuid4())
    result = await homologate(request, session=_FakeSession(rows=rows), _operator=None)

    assert result.match_method == "fuzzy_fallback"
    assert len(result.alternatives) >= 1


async def test_homologate_sin_homologar_when_nothing_matches(monkeypatch):
    async def fake_vector_search(client, article):
        return []

    monkeypatch.setattr(searcher, "vector_search", fake_vector_search)
    monkeypatch.setattr("app.agents.catalog.router.get_qdrant_client", _fake_get_qdrant_client)

    request = HomologateRequest(article="xyznonexistent", warehouse_id=uuid.uuid4())
    result = await homologate(request, session=_FakeSession(rows=[]), _operator=None)

    assert result.sin_homologar is True
    assert result.oracle_code is None
