# Reto Piscilago 30x — Colsubsidio Innovación

Sistema multiagente que reemplaza el conteo de inventario en papel por **captura conversacional validada por IA** en las 48 bodegas de Piscilago (parque de recreación y piscinas de Colsubsidio), sobre un catálogo maestro real de **1041 artículos únicos**.

> Fuente de negocio: [`spec.md`](./spec.md). Reglas de negocio y seguridad: [`CLAUDE.md`](./CLAUDE.md). Roles de agente: [`AGENTS.md`](./AGENTS.md).

## Qué hace

El operario dicta artículos y cantidades por voz desde una tablet; el sistema transcribe, homologa contra el catálogo, valida la unidad de medida según el tipo de producto, detecta anomalías frente al histórico y confirma dígito a dígito antes de guardar. El supervisor revisa las anomalías marcadas y exporta el snapshot final en formato Oracle My Inventory.

```
Voz del Operario → Voice Agent → Parser → Catalog Agent → Auditor Agent → Exporter → Oracle CSV
```

**Fuera de alcance:** integración transaccional con Oracle My Inventory, corrección directa del stock teórico, uso en teléfonos personales, y captura de la recepción de mercancía del proveedor.

## Stack tecnológico

| Capa | Tecnología |
|---|---|
| Backend | FastAPI (Python 3.12) + SQLAlchemy async + Alembic |
| Base de datos | PostgreSQL 16 |
| Vector DB | Qdrant 1.9 (homologación semántica de catálogo) |
| Embeddings | sentence-transformers `paraphrase-multilingual-MiniLM-L12-v2` |
| Voz / NLP | Gemini Live API (STT + TTS) y Gemini Flash (Parser/NER) |
| Frontend | React 18 + TypeScript + Vite, Zustand, offline con Dexie.js |
| Infraestructura | Docker Compose + Nginx (reverse proxy) |

## Estructura del repositorio

```
30X/
├── backend/          # FastAPI: modelos, agentes, servicios, migraciones Alembic
├── frontend/         # React: componentes de tablet (VoiceButton, ConfirmDialog, ...)
├── infra/             # Config de Postgres, Qdrant y Nginx para Docker Compose
├── scripts/           # Importación y seed del catálogo real de Piscilago
├── data/              # catalog.csv, warehouses.csv y fuente cruda (no versionados)
├── docs/              # Arquitectura, guía de marca, backlog
├── CLAUDE.md          # Reglas de negocio y seguridad
├── AGENTS.md          # Roles de agente
├── spec.md            # Especificación funcional original
└── docker-compose.yml
```

## Instalación y ejecución

```bash
cp .env.example .env
# completar GEMINI_API_KEY y JWT_SECRET_KEY en .env
#   JWT_SECRET_KEY: python -c "import secrets; print(secrets.token_hex(32))"
#   GEMINI_API_KEY: https://aistudio.google.com/apikey (con facturación activa)

docker compose up -d
docker compose ps                                # los 5 servicios deben quedar "healthy"/"running"
docker exec 30x-backend-1 alembic upgrade head    # crea el esquema de base de datos

curl http://localhost/api/v1/health              # {"status": "ok"}
```

La app queda en http://localhost (vía nginx) o http://localhost:3000 (frontend directo). Para apagar: `docker compose down`.

Variables de entorno: ver [`.env.example`](./.env.example).

### Sembrar datos de demo

El contenedor de Postgres arranca vacío:

```bash
docker cp scripts/seed_warehouses.py 30x-backend-1:/app/seed_warehouses.py
docker exec 30x-backend-1 python /app/seed_warehouses.py         # 48 bodegas

docker cp scripts/seed_catalog.py 30x-backend-1:/app/seed_catalog.py
docker exec 30x-backend-1 python /app/seed_catalog.py            # catálogo + embeddings en Qdrant

docker cp scripts/seed_historical_counts.py 30x-backend-1:/app/seed_historical_counts.py
docker exec 30x-backend-1 python /app/seed_historical_counts.py  # historial para detección de anomalías

docker cp backend/scripts/seed_operators.py 30x-backend-1:/app/seed_operators.py
docker exec 30x-backend-1 python /app/seed_operators.py          # usuarios de prueba
```

Todos los scripts son idempotentes.

### Exponer la app públicamente (opcional)

```bash
npx cloudflared tunnel --url http://localhost:80
```

Genera una URL pública temporal (`https://algo.trycloudflare.com`) para probar desde otro dispositivo/red. Solo funciona mientras el comando esté corriendo; no la compartas en un canal público.

## Cuentas de prueba

| Rol | `operator_id` | PIN |
|---|---|---|
| Operario | `OPERADOR1` | `1234` |
| Supervisor | `SUPERVISOR1` | `5678` |

Login único en http://localhost — el rol lo determina el backend y rutea automáticamente al módulo correspondiente (operario: conteo por voz; supervisor: dashboard de revisión y exportación).

## Uso básico

1. **Login** con una de las cuentas de prueba.
2. **Operario**: elige bodega y turno, cuenta por voz (mantén presionado el botón central) o con el formulario manual si está offline. El sistema homologa el artículo, valida que la unidad dictada sea compatible con el tipo de producto (sólido/al peso vs. líquido) y confirma dígito a dígito antes de guardar.
3. **Finalizar inventario** cuando termine el conteo.
4. **Supervisor**: elige la sesión, aprueba o rechaza cada ítem marcado por anomalía (o "Aprobar todos"), y exporta a Excel/CSV una vez resueltas.

## Pruebas

```bash
# backend
docker cp backend/tests 30x-backend-1:/app/tests
docker exec 30x-backend-1 python -m pytest /app/tests -q

# frontend
cd frontend && npx vitest run
```

## Seguridad

- Autenticación por rol (`operator`/`supervisor`) validada server-side en cada endpoint, no solo en la UI.
- PINs hasheados con bcrypt; login rate-limited a 10 intentos/minuto por IP.
- Ningún secreto en código — todas las API keys viven en variables de entorno.
- Solo SQLAlchemy ORM o consultas parametrizadas.
- WebSocket con verificación de JWT en el handshake; CORS sin wildcards.
