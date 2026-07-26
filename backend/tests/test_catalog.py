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


def test_classify_falls_back_to_alternatives_when_top_two_are_near_tied():
    """Confirmed live: 'aceite vegetal' scored 0.8726 against 'ACEITE DE
    AJONJOLI' and 0.8644 against the correct-ish 'ACEITE' — both clear
    AUTO_ACCEPT_THRESHOLD, but the ~0.008 gap is noise, not real
    confidence. Auto-accepting the top score alone silently picked the
    wrong item; this must ask the operator instead."""
    matches = [
        {"oracle_code": "7292", "name": "ACEITE DE AJONJOLI", "unit": "L", "is_perishable": False, "score": 0.8726},
        {"oracle_code": "7290", "name": "ACEITE", "unit": "L", "is_perishable": False, "score": 0.8644},
        {"oracle_code": "7293", "name": "ACEITE DE OLIVA", "unit": "L", "is_perishable": False, "score": 0.7862},
    ]

    result = searcher.classify(matches)

    assert result.oracle_code is None
    assert result.requires_operator_selection is True
    assert result.sin_homologar is False
    assert [a.oracle_code for a in result.alternatives] == ["7292", "7290", "7293"]


def test_classify_auto_accepts_when_top_two_are_clearly_separated():
    matches = [
        {"oracle_code": "HAR-001", "name": "Harina de Trigo", "unit": "kg", "is_perishable": False, "score": 0.95},
        {"oracle_code": "HAR-002", "name": "Harina de Maiz", "unit": "kg", "is_perishable": False, "score": 0.60},
    ]

    result = searcher.classify(matches)

    assert result.oracle_code == "HAR-001"
    assert result.requires_operator_selection is False


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


class _FakeScalarsResult:
    """`_enrich_with_canonical_fields`'s `select(CatalogItem).where(...)`
    query result shape — `.scalars()`, not `.all()`."""

    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self._items


class _FakeSession:
    """Queue-based: each `execute()` call pops the next canned response, in
    the same order `run_homologation` issues its queries — the fuzzy-name
    lookup (`.all()`-shaped) and/or the canonical-field enrichment
    (`.scalars()`-shaped) that now runs whenever any matches are found."""

    def __init__(self, responses):
        self._responses = list(responses)

    async def execute(self, *_args, **_kwargs):
        return self._responses.pop(0)


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
    session = _FakeSession(responses=[_FakeScalarsResult([])])  # enrichment query
    result = await homologate(request, session=session, _operator=None)

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
    session = _FakeSession(
        responses=[_FakeResultRows(rows), _FakeScalarsResult([])]  # fuzzy names, then enrichment
    )
    result = await homologate(request, session=session, _operator=None)

    assert result.match_method == "fuzzy_fallback"
    assert len(result.alternatives) >= 1


async def test_homologate_prefers_canonical_fields_over_synonym_point_payload(monkeypatch):
    """A learned-synonym Qdrant point (`catalog_sync.upsert_synonym`) only
    stores `{oracle_code, name: <raw synonym>, source}` — no unit, no
    is_perishable. Confirmed live: homologating a taught synonym returned
    the operator's own raw phrase as `name`, and `is_perishable=None` for an
    item that really is perishable, which would silently skip the
    CLAUDE.md §3.6 expiry_date requirement. `run_homologation` must
    overwrite these with the real catalog_items row."""

    async def fake_vector_search(client, article):
        return [
            {
                "oracle_code": "LAC-001",
                "name": "pescaito blanco de la piscilago",  # raw synonym text, from the Qdrant payload
                "unit": None,
                "is_perishable": None,
                "score": 1.0,
            }
        ]

    monkeypatch.setattr(searcher, "vector_search", fake_vector_search)
    monkeypatch.setattr("app.agents.catalog.router.get_qdrant_client", _fake_get_qdrant_client)

    canonical_item = SimpleNamespace(oracle_code="LAC-001", name="Leche Entera 1L", unit="L", is_perishable=True)
    request = HomologateRequest(article="pescaito blanco de la piscilago", warehouse_id=uuid.uuid4())
    # Only 1 match (< 3) also triggers the fuzzy-fallback names query first;
    # empty catalog_names means fuzzy finds nothing, so the original
    # vector-search match survives to the enrichment step.
    session = _FakeSession(responses=[_FakeResultRows([]), _FakeScalarsResult([canonical_item])])
    result = await homologate(request, session=session, _operator=None)

    assert result.oracle_code == "LAC-001"
    assert result.name == "Leche Entera 1L"
    assert result.unit == "L"
    assert result.is_perishable is True


async def test_homologate_sin_homologar_when_nothing_matches(monkeypatch):
    async def fake_vector_search(client, article):
        return []

    monkeypatch.setattr(searcher, "vector_search", fake_vector_search)
    monkeypatch.setattr("app.agents.catalog.router.get_qdrant_client", _fake_get_qdrant_client)

    request = HomologateRequest(article="xyznonexistent", warehouse_id=uuid.uuid4())
    session = _FakeSession(responses=[_FakeResultRows([])])  # fuzzy names query; no matches -> no enrichment
    result = await homologate(request, session=session, _operator=None)

    assert result.sin_homologar is True
    assert result.oracle_code is None
