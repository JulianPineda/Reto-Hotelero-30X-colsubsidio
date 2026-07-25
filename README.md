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
| Voz / NLP | Gemini 1.5 Flash — Live API para STT + NER + explicaciones NL ([ADR-001](./CLAUDE.md#11-decisión-de-arquitectura-proveedor-de-modelos-adr-001)) |
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

docker compose up -d
curl http://localhost/api/v1/health   # {"status": "ok"}
curl http://localhost:3000            # React app
```

Variables de entorno requeridas: ver [`.env.example`](./.env.example) (base de datos, Qdrant, Gemini, JWT, CORS, umbrales de STT/anomalías).

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

> Ningún ticket de Epic 2–6 puede iniciarse hasta que el Epic 1 (Foundation) esté completado.

## Seguridad

- Ningún secreto en código: todas las API keys viven en variables de entorno (ver [`CLAUDE.md` §5](./CLAUDE.md)).
- Solo SQLAlchemy ORM o consultas parametrizadas — nunca concatenación de strings para SQL.
- La tabla `events` es append-only: cero `UPDATE`, cero `DELETE`.
- WebSocket con verificación de JWT en el handshake; CORS sin wildcards.