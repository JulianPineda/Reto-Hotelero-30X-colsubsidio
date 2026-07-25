# EPIC 3 — Catalog Homologation
**Sprint 1 · ~3 días · 5 puntos**

Prerequisito: T-003 completado (Qdrant con catálogo seed).

---

## T-009 — Catalog Agent: Vector Search + Fuzzy Fallback
**Puntos:** 3 | **Asignado a:** Ejecutor

### Descripción
Motor de homologación semántica. Busca el artículo dictado en Qdrant usando embeddings, con fallback a rapidfuzz para casos donde el texto sea demasiado corto para un buen embedding.

### Archivos a crear
- `backend/app/agents/catalog/router.py` — `POST /api/v1/agents/homologate` + feedback
- `backend/app/agents/catalog/embedder.py` — wrapper `sentence-transformers`
- `backend/app/agents/catalog/searcher.py` — búsqueda Qdrant + lógica de umbrales
- `backend/app/agents/catalog/fuzzy_fallback.py` — rapidfuzz para textos cortos
- `backend/app/agents/catalog/schemas.py`
- `backend/tests/test_catalog.py`

### Lógica de búsqueda (searcher.py)
```python
async def homologate(article: str, warehouse_id: UUID, unit_hint: str | None = None):
    # 1. Generar embedding del artículo dictado
    query_vector = embedder.embed(article)

    # 2. Buscar en Qdrant — top 5 con score > 0.50
    results = await qdrant_client.search(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        query_vector=query_vector,
        limit=5,
        score_threshold=0.50,
    )

    # 3. Clasificar por umbral (CLAUDE.md §3.2)
    if not results:
        return HomologateResult(sin_homologar=True)

    top = results[0]
    if top.score >= 0.80:
        return HomologateResult(oracle_code=top.payload["oracle_code"], score=top.score, ...)
    elif top.score >= 0.50:
        return HomologateResult(alternatives=results[:3], requires_operator_selection=True, ...)
```

### Fallback fuzzy
Usar `rapidfuzz.process.extractOne()` sobre los `catalog_items.name` cuando el embedding arroja < 3 resultados (artículo muy corto, ej. "sal", "aceite").

### Criterio de aceptación
```bash
pytest backend/tests/test_catalog.py -v
# "aceite vegetal" → oracle_code=ACE-001, score ≥ 0.80
# "aceite" → alternatives con ≥ 2 opciones, requires_operator_selection=True
# "xyznonexistent" → sin_homologar=True
```

### Notas
- El embedder carga el modelo al arrancar la app (en lifespan de FastAPI), no en cada request.
- El cliente Qdrant se inicializa una sola vez (singleton en `database.py` o lifespan).

---

## T-010 — Continuous Learning: ItemCorrected → Qdrant Upsert
**Puntos:** 2 | **Asignado a:** Ejecutor

### Descripción
Cuando un operario corrige la homologación (selecciona una alternativa diferente a la sugerida), el sistema registra el par `(término dictado → artículo correcto)` como sinónimo y actualiza Qdrant.

### Archivos a crear
- `backend/app/services/learning_service.py`
- Endpoint `POST /api/v1/agents/catalog/feedback` (ya en T-009's router)
- `backend/tests/test_learning_service.py`

### Flujo del aprendizaje
```
1. Operario selecciona ACE-002 cuando el sistema sugirió ACE-001
2. WS envía: { "type": "correction_feedback", "selected_oracle_code": "ACE-002" }
3. Orchestrator emite ItemCorrected con {old_oracle_code, new_oracle_code, raw_article}
4. LearningService:
   a. INSERT INTO synonym_embeddings (catalog_item_id=ACE-002, synonym="aceite premier oliva")
   b. Si ya existe: UPDATE usage_count += 1
   c. Generar embedding del sinónimo
   d. qdrant.upsert(nuevo punto con oracle_code=ACE-002 en payload)
5. Las próximas búsquedas de "aceite premier oliva" encontrarán ACE-002 directamente
```

### Idempotencia
- `UNIQUE(catalog_item_id, synonym)` en PG previene duplicados.
- Qdrant upsert es idempotente por `point_id`.

### Criterio de aceptación
```bash
pytest backend/tests/test_learning_service.py -v
# Verificar: synonym creado en PG, punto upserted en Qdrant
# Segunda corrección del mismo sinónimo: usage_count = 2, no duplicado
```
