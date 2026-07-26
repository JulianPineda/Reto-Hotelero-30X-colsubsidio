# Reto Piscilago 30x — Colsubsidio Innovación

Sistema multiagente que reemplaza el conteo de inventario en papel por **captura conversacional validada por IA** en las 48 bodegas de Piscilago (parque de recreación y piscinas de Colsubsidio), sobre un catálogo maestro real de **1041 artículos únicos**.

> Fuente de negocio: [`spec.md`](./spec.md). Reglas ejecutables para agentes de IA: [`CLAUDE.md`](./CLAUDE.md). Roles y restricciones de cada agente: [`AGENTS.md`](./AGENTS.md).

## Qué hace

El operario dicta artículos y cantidades por voz desde una tablet; el sistema transcribe, homologa contra el catálogo Oracle, detecta anomalías frente al histórico y confirma dígito a dígito antes de guardar. Un Auditor de Costos revisa las anomalías marcadas y aprueba el snapshot final, que se exporta como CSV en formato Oracle My Inventory.

```
Voz del Operario → Voice Agent → Parser → Catalog Agent → Auditor Agent → Exporter → Oracle CSV
```

**Fuera de alcance:** integración transaccional con Oracle My Inventory, corrección directa del stock teórico, uso en teléfonos personales, y captura/validación de la recepción de mercancía (remisión/factura del proveedor).

## Stack tecnológico

| Capa | Tecnología |
|---|---|
| Backend | FastAPI (Python 3.12) + SQLAlchemy async + Alembic |
| Base de datos | PostgreSQL 16 (event store + read models) |
| Vector DB | Qdrant 1.9 (homologación semántica de catálogo) |
| Embeddings | sentence-transformers `paraphrase-multilingual-MiniLM-L12-v2` |
| Voz / NLP | Gemini — Live API (`gemini-3.1-flash-live-preview`) para STT + TTS de confirmación; `gemini-3.6-flash` para Parser/NER ([ADR-001](./CLAUDE.md#11-decisión-de-arquitectura-proveedor-de-modelos-adr-001)) |
| Frontend | React 18 + TypeScript + Vite, estado con Zustand, offline con Dexie.js |
| Infraestructura | Docker Compose + Nginx (reverse proxy) |

## Estructura del repositorio

```
30X/
├── backend/           # FastAPI: modelos, agentes, servicios, migraciones Alembic
├── frontend/           # React: componentes de tablet (VoiceButton, ConfirmDialog, ...)
├── infra/               # Config de Postgres, Qdrant y Nginx para Docker Compose
├── scripts/             # Importación y seed del catálogo real de Piscilago
├── data/                # catalog.csv, warehouses.csv y fuente cruda (data/raw/) — no versionados
├── docs/
│   ├── architecture/    # Diagramas C4, esquema de DB, contratos de API
│   ├── brand/           # Guía de marca Colsubsidio
│   └── tickets/         # EPIC-1 a EPIC-6: backlog ejecutable por agentes de IA
├── CLAUDE.md            # Reglas de negocio y seguridad — fuente de verdad para agentes de IA
├── AGENTS.md            # Roles de agente (Arquitecto, UI Expert, Ejecutor, Validador)
├── spec.md              # Especificación funcional original
└── docker-compose.yml
```

## Cómo correr en local

```bash
cp .env.example .env
# completar GEMINI_API_KEY y JWT_SECRET_KEY en .env
#   JWT_SECRET_KEY: python -c "import secrets; print(secrets.token_hex(32))"
#   GEMINI_API_KEY: https://aistudio.google.com/apikey (con facturación activa —
#   la Live API consume cuota real incluso en el tier gratuito)

docker compose up -d
docker compose ps                     # los 5 servicios deben quedar "healthy"/"running"

curl http://localhost/api/v1/health   # {"status": "ok"}
curl http://localhost:3000            # React app
```

Para apagar: `docker compose down`. Para ver logs en vivo de un servicio: `docker compose logs -f backend`.

Variables de entorno requeridas: ver [`.env.example`](./.env.example) (base de datos, Qdrant, Gemini, JWT, CORS, umbrales de STT/anomalías).

### Sembrar datos de demo

El contenedor de Postgres arranca vacío. Antes de probar el flujo completo, corre estos scripts una vez (necesitan el backend corriendo, para reusar su config/DB):

```bash
docker cp scripts/seed_warehouses.py 30x-backend-1:/app/seed_warehouses.py
docker exec 30x-backend-1 python /app/seed_warehouses.py       # 48 bodegas reales de Piscilago

docker cp scripts/seed_catalog.py 30x-backend-1:/app/seed_catalog.py
docker exec 30x-backend-1 python /app/seed_catalog.py          # 1041 artículos + embeddings en Qdrant

docker cp scripts/seed_historical_counts.py 30x-backend-1:/app/seed_historical_counts.py
docker exec 30x-backend-1 python /app/seed_historical_counts.py  # historial para el Auditor Agent
```

`seed_historical_counts.py` genera 5 semanas de conteos estables (±5% de ruido) para hasta 3 artículos por cada una de las ~25 categorías del catálogo, en las 48 bodegas, en los 3 turnos — así cualquier combinación bodega/artículo/turno que se cuente en una demo ya tiene con qué comparar (CLAUDE.md §3.1). Todos los scripts son idempotentes: correrlos de nuevo no duplica filas.

## Cómo probar el flujo completo (paso a paso)

1. **Abrir la app** — http://localhost (vía nginx) o http://localhost:3000 (frontend directo).
2. **Login del operario** — cualquier `operator_id` + PIN no vacío funciona (ver "Autenticación" abajo). Ej: `OP-231` / `1234`.
3. **Elegir bodega y turno** — selecciona una de las 48 bodegas sembradas y un turno (mañana/tarde/noche), luego "Iniciar conteo".
4. **Contar por voz** — mantén presionado el botón central (VoiceButton), dicta artículo y cantidad ("veinte kilos de harina de trigo"), suelta el botón. El sistema transcribe, homologa contra el catálogo, y pide confirmación dígito a dígito ("¿Dos, cero: 20 kg de harina de trigo?") — leída en voz alta también. Confirma o corrige.
5. **Modo offline** — desconectar la red (o simularlo) deshabilita la voz y activa un formulario manual; al reconectar, todo lo capturado offline pasa automáticamente por homologación + detección de anomalías.
6. **Terminar el conteo** — no hay botón explícito de "terminar" en la UI todavía; la sesión pasa a `pending_review` automáticamente en cuanto el supervisor resuelve el último ítem marcado (ver `POST /api/v1/sessions/{id}/complete` si se quiere marcar explícitamente antes).
7. **Revisión del supervisor** — en otra pestaña/dispositivo, ir a `/supervisor-login`, cualquier credencial funciona igual, elegir la sesión de la lista. El dashboard muestra solo los ítems con anomalía sin resolver (perecederos en rojo primero); aprobar o rechazar cada uno (o "Aprobar todos").
8. **Exportar** — una vez resueltas todas las anomalías, `POST /api/v1/agents/export` (no hay botón en el dashboard todavía) genera el CSV formato Oracle My Inventory; el resultado incluye `download_url` para bajarlo vía `GET /api/v1/exports/{filename}`. Un segundo intento de exportar la misma sesión responde `409`.

### Autenticación (léase antes de una demo con público)

`POST /api/v1/auth/login` emite un JWT válido para **cualquier** `operator_id` + PIN no vacío — no existe todavía una tabla de operarios/credenciales real (ninguna decisión de negocio la definió). Esto es intencional para desbloquear el resto del pipeline en desarrollo/demo, pero significa que hoy no hay distinción real entre "operario" y "supervisor": es la misma cuenta, la diferencia es solo a qué URL se entra. Rate-limited a 10 intentos/minuto por IP para que no se puedan emitir tokens gratis sin límite.

## Backlog

El trabajo está organizado en 6 epics ejecutables secuencialmente por los agentes de IA (`docs/tickets/`):

| Epic | Contenido |
|---|---|
| [EPIC-1](./docs/tickets/EPIC-1-foundation.md) | Infraestructura Docker, schema de DB, seed de catálogo real, event store |
| [EPIC-2](./docs/tickets/EPIC-2-voice.md) | Voice Agent (STT/TTS) |
| [EPIC-3](./docs/tickets/EPIC-3-catalog.md) | Catalog Agent (homologación semántica) |
| [EPIC-4](./docs/tickets/EPIC-4-auditor.md) | Auditor Agent (detección de anomalías) |
| [EPIC-5](./docs/tickets/EPIC-5-supervisor.md) | Supervisor Dashboard |
| [EPIC-6](./docs/tickets/EPIC-6-export-polish.md) | Exportación Oracle CSV y pulido |

> Ningún ticket de Epic 2–6 puede iniciarse hasta que el Epic 1 (Foundation) esté completado. Los 6 epics están implementados y verificados en vivo contra el stack Docker real (no solo con mocks) — ver "Estado actual" abajo.

## Estado actual

Verificado en vivo contra Postgres/Qdrant/Gemini reales, no solo con tests unitarios:

- **Voz de punta a punta**: PTT → STT (Gemini Live) → Parser → homologación → confirmación dígito a dígito → lectura en voz alta (TTS) → persistencia. El ciclo de vida de la sesión (`in_progress → pending_review → approved → exported`, CLAUDE.md §3.4) está implementado y se aplica.
- **Detección de anomalías** (Auditor Agent, Reglas A/B/C de CLAUDE.md §3.1) reproduce el formato de explicación exacto del spec, con historial sembrado en las 48 bodegas y 3 turnos.
- **Aprendizaje continuo**: `POST /agents/catalog/feedback` enseña sinónimos que luego homologan directo (score 1.0) en la siguiente dictada.
- **Exportación**: CSV formato Oracle My Inventory (pipe-delimited, UTF-8 sin BOM, 4 decimales) con el gate de anomalías sin resolver y bloqueo de doble exportación.
- **Modo offline**: cola en IndexedDB (Dexie), homologación + Auditor Agent al reconectar.
- **Pruebas**: 130 tests de backend (pytest, contra Postgres/Qdrant reales) + 49 de frontend (Vitest) — ver `backend/tests/` y `frontend/src/**/*.test.{ts,tsx}`.
  ```bash
  # backend — la imagen no incluye tests/, se copian una vez al contenedor corriendo:
  docker cp backend/tests 30x-backend-1:/app/tests
  docker exec 30x-backend-1 python -m pytest /app/tests -q

  # frontend
  cd frontend && npx vitest run
  ```

**Limitaciones conocidas / simplificaciones deliberadas** (documentadas in situ en el código, no son bugs pendientes):
- Autenticación es un stopgap (ver arriba) — no hay tabla de credenciales real.
- Jobs de exportación y rate-limiting de login viven en memoria del proceso (sin Redis) — se pierden al reiniciar el contenedor backend; suficiente para esta demo de una sola instancia, no para producción multi-instancia.
- `TranscriptEvent.confidence` de Gemini Live siempre es `None` — la API no expone un score de confianza por transcripción, así que el umbral de CLAUDE.md §3.2 ("si STT < 0.75, pedir repetir") no puede aplicarse literalmente con este proveedor.
- La latencia P95 de voz (<2s, CLAUDE.md §6) no se ha medido formalmente en campo con ruido de bodega real.

## Seguridad

- Ningún secreto en código: todas las API keys viven en variables de entorno (ver [`CLAUDE.md` §5](./CLAUDE.md)).
- Solo SQLAlchemy ORM o consultas parametrizadas — nunca concatenación de strings para SQL.
- La tabla `events` es append-only: cero `UPDATE`, cero `DELETE`.
- WebSocket con verificación de JWT en el handshake; CORS sin wildcards.