# Architecture Overview — Sistema Multiagente de Inventario

## C4 Level 1 — Context Diagram

```mermaid
C4Context
    title Reto Piscilago 30x — System Context

    Person(operario, "Operario", "Realiza el conteo físico en bodega usando tablet + headset")
    Person(auditor, "Auditor de Costos", "Revisa anomalías y aprueba el snapshot antes de Oracle")

    System(sistema, "Sistema Multiagente de Inventario", "Captura conversacional validada por IA: voz → CSV Oracle")

    System_Ext(oracle, "Oracle My Inventory", "ERP de registro maestro de inventario")
    System_Ext(gemini, "Gemini 1.5 Flash (Live API)", "STT streaming bidireccional de baja latencia + NER + explicaciones NL (ADR-001)")

    Rel(operario, sistema, "Dicta artículos y cantidades", "Push-to-Talk, Audio 16kHz, TLS")
    Rel(sistema, operario, "Confirma dígito a dígito", "TTS Audio 24kHz")
    Rel(auditor, sistema, "Revisa anomalías, aprueba snapshot", "HTTPS, Supervisor Dashboard")
    Rel(sistema, oracle, "Entrega snapshot de inventario", "CSV/Excel formato Oracle")
    Rel(sistema, gemini, "Stream de audio → transcripción", "WebSocket TLS")
    Rel(sistema, gemini, "Texto → {artículo, cantidad, unidad}", "HTTPS API")
```

---

## C4 Level 2 — Container Diagram

```mermaid
C4Container
    title Reto Piscilago 30x — Containers

    Person(operario, "Operario")
    Person(auditor, "Auditor de Costos")

    Container(frontend, "React Web App", "React 18 + TypeScript + Vite", "Interfaz de tablet para conteo y revisión de anomalías")
    Container(backend, "FastAPI Backend", "Python 3.12 + FastAPI", "Orquesta el pipeline multiagente, mantiene estado de sesión")
    ContainerDb(postgres, "PostgreSQL 16", "Event Store + Read Models", "Events, sesiones, catálogo, histórico de conteos")
    ContainerDb(qdrant, "Qdrant", "Vector Database", "Embeddings del catálogo Oracle para homologación semántica")

    System_Ext(gemini, "Gemini 1.5 Flash (Live API)")

    Rel(operario, frontend, "Usa", "HTTPS, tablet browser")
    Rel(auditor, frontend, "Usa", "HTTPS, browser")
    Rel(frontend, backend, "API REST + WebSocket", "HTTPS / WSS")
    Rel(backend, postgres, "Lee/escribe", "asyncpg")
    Rel(backend, qdrant, "Vector search", "HTTP gRPC")
    Rel(backend, gemini, "Stream de audio STT", "WebSocket TLS")
    Rel(backend, gemini, "NER + NL generation", "HTTPS")
```

---

## Pipeline de Agentes — Detalle del Hot Path

```mermaid
sequenceDiagram
    participant Op as Operario (Tablet)
    participant VA as Voice Agent (WS)
    participant OR as Orchestrator
    participant PA as Parser
    participant CA as Catalog Agent
    participant AA as Auditor Agent
    participant ES as Event Store (PG)

    Op->>VA: PTT pressed → audio chunks (16kHz)
    VA->>VA: STT via Gemini 1.5 Flash (Live API)
    Note over VA: confidence < 0.75 → pide repetir
    VA->>OR: transcript + confidence
    OR->>PA: POST /agents/parse
    PA-->>OR: {article, quantity, unit}
    OR->>CA: POST /agents/homologate
    alt score ≥ 0.80
        CA-->>OR: oracle_code + name + unit
    else 0.50 ≤ score < 0.80
        CA-->>OR: requires_operator_selection = true
        OR->>VA: send alternatives to UI
        Op->>VA: selecciona opción
    else score < 0.50
        CA-->>OR: sin_homologar = true
    end
    OR->>AA: POST /agents/audit
    alt Sin anomalía
        AA-->>OR: is_flagged=false, ItemValidated
    else Anomalía detectada
        AA-->>OR: is_flagged=true, explanation (español)
        OR->>VA: repregunta al operario
    end
    OR->>ES: append_event(ItemCreated/ItemRejected)
    OR->>VA: item_saved con confirmación dígito a dígito
    VA->>Op: TTS confirmación (24kHz)
```

---

## Stack Tecnológico

| Capa | Tecnología | Versión |
|---|---|---|
| Backend | FastAPI | 0.111+ |
| ORM | SQLAlchemy (async) | 2.0+ |
| Migraciones | Alembic | 1.13+ |
| Vector DB | Qdrant | 1.9+ |
| Embeddings | sentence-transformers `paraphrase-multilingual-MiniLM-L12-v2` | local |
| STT | Gemini Live API (WebSocket, ADR-001) | gemini-1.5-flash |
| LLM | Gemini 1.5 Flash (NER + explicaciones NL, ADR-001) | gemini-1.5-flash |
| Frontend | React 18 + TypeScript + Vite | React 18.3 |
| Estado (client) | Zustand | 4+ |
| Offline storage | Dexie.js (IndexedDB) | 3+ |
| Orquestación local | Docker Compose | v2 |
