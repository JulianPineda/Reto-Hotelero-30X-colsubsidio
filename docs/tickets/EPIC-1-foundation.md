# EPIC 1 — Foundation
**Sprint 0 · ~3 días · 7 puntos**

Prerequisito para todos los demás epics. Ningún ticket de Epic 2–6 puede iniciarse hasta que T-004 esté completado.

---

## T-001 — Docker Compose: Infraestructura Local
**Puntos:** 2 | **Asignado a:** Arquitecto + Ejecutor

### Descripción
Configurar el stack completo de Docker Compose para desarrollo local:
- PostgreSQL 16 con init.sql (extensiones)
- Qdrant 1.9 con config.yaml
- Backend FastAPI (con Dockerfile)
- Frontend React (con Dockerfile multi-stage)
- Nginx como reverse proxy

### Archivos a crear
- `docker-compose.yml` ✅ (ya creado)
- `.env.example` ✅ (ya creado)
- `infra/postgres/init.sql`
- `infra/qdrant/config.yaml`
- `infra/nginx/nginx.conf`
- `backend/Dockerfile`
- `frontend/Dockerfile`

### Criterio de aceptación
```bash
docker compose up -d
curl http://localhost/api/v1/health  # responde {"status": "ok"}
curl http://localhost:3000           # sirve la React app
```

### Detalles técnicos
- Backend Dockerfile: Python 3.12-slim, `pip install -e ".[dev]"`, CMD uvicorn
- Frontend Dockerfile: Node 20 build stage → nginx:alpine serve stage
- Nginx: `/api/` → backend:8000, `/ws/` → backend:8000 (WebSocket upgrade), `/` → frontend:80

---

## T-002 — DB Schema + Alembic Migrations
**Puntos:** 2 | **Asignado a:** Ejecutor

### Descripción
Crear todos los modelos SQLAlchemy (async) y la migración Alembic inicial con las 7 tablas definidas en `docs/architecture/db-schema.md`.

### Archivos a crear
- `backend/pyproject.toml` (deps: fastapi, sqlalchemy[asyncio], asyncpg, alembic, pydantic-settings, pyjwt)
- `backend/alembic.ini`
- `backend/alembic/env.py`
- `backend/alembic/versions/001_initial_schema.py`
- `backend/app/models/event.py`
- `backend/app/models/warehouse.py`
- `backend/app/models/catalog_item.py`
- `backend/app/models/count_session.py`
- `backend/app/models/count_item.py`
- `backend/app/models/historical_count.py`
- `backend/app/models/synonym_embedding.py`
- `backend/app/database.py`

### Criterio de aceptación
```bash
cd backend && alembic upgrade head
# 7 tablas creadas, indexes creados, pg_trgm extension activa
```

### Notas de seguridad
- Contraseña de DB nunca hardcodeada. Siempre de `DATABASE_URL` env var.
- Modelos con `__table_args__ = {"schema": "public"}` explícito.

---

## T-003 — Qdrant Init + Seed de Catálogo Real (Piscilago)
**Puntos:** 2 | **Asignado a:** Ejecutor

### Descripción
Inicializar la colección Qdrant y crear el script de seed a partir del catálogo real de Piscilago (parque de recreación y piscinas de Colsubsidio — no una bodega hotelera): 1041 artículos únicos que abarcan alimentos y bebidas, medicamentos de enfermería, papelería, ferretería, dotación de protección personal y suministros de zoológico, importados de `data/raw/BODEGAS_Y_STOCK.xlsx` (fuente: Google Drive, hoja "BODEGAS Y STOCK.xlsx").

### Archivos a crear
- `scripts/import_catalog.py` — lee `data/raw/BODEGAS_Y_STOCK.xlsx` (9 hojas: 1 de bodegas + 8 de stock por dependencia), deduplica artículos por código, clasifica categoría/perecibilidad por heurística de palabras clave, y genera `data/catalog.csv` (1041 filas) y `data/warehouses.csv` (48 bodegas)
- `scripts/seed_catalog.py` — lee `data/catalog.csv`, genera embeddings, hace upsert a PG + Qdrant
- `backend/app/services/catalog_sync.py`

### Estructura del CSV real (`data/catalog.csv`)
```
oracle_code,name,unit,category,is_perishable,default_shelf_days
1031,FILETE DE TILAPIA,kg,Carnes,True,3
124791,IBUPROFENO 800MG TNR CJX50 GEF,unit,Medicamentos,False,
5001,ACELGA,kg,Frutas y Verduras,True,6
...
```
Nota: ~44% de los artículos caen en `category = "Otros / Sin Clasificar"` — es un catálogo real de casi mil artículos heterogéneos (herramientas, insumos médicos, códigos de formularios internos), la clasificación por palabras clave en `scripts/import_catalog.py` es un primer corte que el equipo debe revisar y refinar, no un catálogo curado a mano como el mock anterior.

### Criterio de aceptación
```bash
python scripts/import_catalog.py
# Salida: "48 bodegas -> data/warehouses.csv" y "1041 articulos unicos -> data/catalog.csv"
python scripts/seed_catalog.py --csv data/catalog.csv
# Salida: "1041 artículos indexados en PG, 1041 puntos upserted en Qdrant"
# Verificar: curl http://localhost:6333/collections/catalog_items
```

### Modelo de embedding
`paraphrase-multilingual-MiniLM-L12-v2` de sentence-transformers (descarga automática en primer uso, ~120MB).

---

## T-004 — Event Store Service
**Puntos:** 1 | **Asignado a:** Ejecutor

### Descripción
Implementar el servicio de event sourcing que garantiza el invariante append-only.

### Archivos a crear
- `backend/app/schemas/events.py` — EventType enum + Pydantic payloads para los 5 tipos
- `backend/app/services/event_store.py` — `append_event()`, `get_aggregate_events()`, `get_session_events()`
- `backend/tests/test_event_store.py`

### Contrato de `append_event()`
```python
async def append_event(
    session: AsyncSession,
    event_type: EventType,
    aggregate_id: UUID,
    aggregate_type: str,
    payload: dict,
    warehouse_id: UUID,
    created_by: str,
    metadata: dict | None = None,
) -> Event:
    ...
```

### Test del invariante
```python
# test_event_store.py
async def test_append_only_no_update():
    """Event store must never expose update/delete methods."""
    assert not hasattr(event_store, "update_event")
    assert not hasattr(event_store, "delete_event")
    assert not hasattr(event_store, "patch_event")

async def test_sequence_is_monotonic():
    ...
```

### Criterio de aceptación
```bash
pytest backend/tests/test_event_store.py -v  # todos pasan
```
