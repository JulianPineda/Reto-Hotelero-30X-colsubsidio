# API Contracts — Interfaces Entre Agentes

## Autenticación

Todos los endpoints (REST y WebSocket) requieren un JWT Bearer token:
```
Authorization: Bearer <jwt_token>
```
Para WebSocket: enviar como query parameter `?token=<jwt_token>` en el handshake de upgrade.

Token obtenido vía `POST /api/v1/auth/login` con credenciales SSO/PIN del operario.

---

## WebSocket — Voice Agent

### Endpoint
```
WS /ws/voice/{session_id}?token={jwt_token}
```

### Mensajes Client → Server

```json
{ "type": "ptt_start" }
// Operario presionó el botón push-to-talk

{ "type": "ptt_stop" }
// Operario soltó el botón

{ "type": "audio_chunk", "data": "<base64_pcm_16kHz>", "seq": 42 }
// Chunk de audio durante PTT activo

{ "type": "confirm", "value": true }
// Acepta la confirmación dígito a dígito

{ "type": "confirm", "value": false }
// Rechaza — pide redictar

{ "type": "select_alternative", "oracle_code": "HAR-002" }
// Operario seleccionó una alternativa de desambiguación

{ "type": "correction_feedback", "selected_oracle_code": "HAR-002" }
// Operario corrigió el ítem → dispara aprendizaje continuo

{ "type": "command", "value": "corregir_ultimo" }
// Comandos deterministas: corregir_ultimo | borrar_ultimo | pausar

{ "type": "barge_in" }
// Interrupción del TTS en curso
```

### Mensajes Server → Client

```json
{ "type": "listening" }
// VAD activado, grabando

{ "type": "transcript", "text": "noventa galones de aceite vegetal", "confidence": 0.92 }
// Transcripción procesada

{ "type": "confirmation_request",
  "item_id": "uuid",
  "oracle_code": "ACE-001",
  "article": "Aceite Vegetal Premier 5L",
  "quantity": 90.0,
  "unit": "GAL",
  "digit_by_digit": "nueve, cero",
  "display_text": "¿Nueve, cero: noventa galones de Aceite Vegetal Premier 5L?" }

{ "type": "alternatives_request",
  "item_id": "uuid",
  "alternatives": [
    { "oracle_code": "ACE-001", "name": "Aceite Vegetal Premier 5L", "score": 0.78 },
    { "oracle_code": "ACE-002", "name": "Aceite de Oliva Extra Virgen", "score": 0.71 }
  ] }

{ "type": "item_saved",
  "item_id": "uuid",
  "is_flagged": false,
  "sequence": 5 }

{ "type": "item_flagged",
  "item_id": "uuid",
  "flag_type": "threshold",
  "explanation": "La cantidad (14 kg) representa una caída del 84.4% respecto al promedio histórico de los últimos 3 conteos (90, 92, 88). Promedio: 90 kg." }

{ "type": "low_confidence",
  "confidence": 0.62,
  "attempt": 2,
  "max_attempts": 3 }

{ "type": "manual_fallback_offered" }
// Tras 3 intentos fallidos

{ "type": "error", "code": "STT_UNAVAILABLE", "correlation_id": "uuid", "message": "Error interno de procesamiento de voz." }
// Mensajes de error siempre genéricos para el cliente

{ "type": "session_paused", "items_counted": 42 }
```

**Contrato de latencia:** de `ptt_stop` a `confirmation_request` ≤ 2 000 ms en P95.

---

## REST — Parser Agent

### `POST /api/v1/agents/parse`

**Request:**
```json
{
  "transcript": "veinte kilos de harina de trigo",
  "session_id": "uuid",
  "language": "es-CO"
}
```
Constraints: `transcript` max 500 chars, solo alfanumérico + espacios + unidades de medida.

**Response 200:**
```json
{
  "article": "harina de trigo",
  "quantity": 20.0,
  "unit": "kg",
  "confidence": 0.97,
  "raw_tokens": ["veinte", "kilos", "de", "harina", "de", "trigo"]
}
```

**Response 422:**
```json
{
  "error": "PARSE_FAILED",
  "correlation_id": "uuid",
  "message": "No se pudo extraer artículo o cantidad del texto."
}
```

---

## REST — Catalog Agent

### `POST /api/v1/agents/homologate`

**Request:**
```json
{
  "article": "harina de trigo",
  "warehouse_id": "uuid",
  "unit_hint": "kg"
}
```

**Response 200 — match único (score ≥ 0.80):**
```json
{
  "oracle_code": "HAR-001",
  "name": "Harina de Trigo Especial 50kg",
  "unit": "kg",
  "score": 0.94,
  "is_perishable": false,
  "match_method": "vector_search",
  "alternatives": [],
  "requires_operator_selection": false,
  "sin_homologar": false
}
```

**Response 200 — múltiples candidatos (0.50 ≤ score < 0.80):**
```json
{
  "oracle_code": null,
  "score": 0.74,
  "alternatives": [
    { "oracle_code": "HAR-001", "name": "Harina de Trigo Especial 50kg", "score": 0.74 },
    { "oracle_code": "HAR-002", "name": "Harina de Trigo Integral 1kg", "score": 0.68 }
  ],
  "requires_operator_selection": true,
  "sin_homologar": false
}
```

**Response 200 — sin match (score < 0.50):**
```json
{
  "oracle_code": null,
  "score": 0.32,
  "alternatives": [],
  "requires_operator_selection": false,
  "sin_homologar": true
}
```

### `POST /api/v1/agents/catalog/feedback`
Dispara aprendizaje continuo cuando el operario corrige la homologación.

**Request:**
```json
{
  "raw_article": "harina",
  "oracle_code": "HAR-001",
  "session_id": "uuid",
  "operator_id": "OP-231"
}
```

**Response 200:**
```json
{ "synonym_created": true, "qdrant_updated": true }
```

---

## REST — Auditor Agent

### `POST /api/v1/agents/audit`

**Request:**
```json
{
  "oracle_code": "HAR-001",
  "quantity": 20.0,
  "unit": "kg",
  "warehouse_id": "uuid",
  "shift": "morning"
}
```

**Response 200 — sin anomalía:**
```json
{
  "is_flagged": false,
  "flag_type": null,
  "explanation": null,
  "historical_counts": [
    { "date": "2026-07-17", "quantity": 19.5, "shift": "morning" },
    { "date": "2026-07-10", "quantity": 20.0, "shift": "morning" },
    { "date": "2026-07-03", "quantity": 21.0, "shift": "morning" }
  ]
}
```

**Response 200 — con anomalía:**
```json
{
  "is_flagged": true,
  "flag_type": "threshold",
  "explanation": "La cantidad registrada (20 kg) supera en 45.3% el promedio de los últimos 3 conteos (13.8 kg) para esta bodega en turno mañana.",
  "threshold_detail": {
    "delta_pct": 45.3,
    "delta_abs": 6.2,
    "historical_avg": 13.8
  },
  "trend_detail": null,
  "historical_counts": [
    { "date": "2026-07-17", "quantity": 14.0, "shift": "morning" },
    { "date": "2026-07-10", "quantity": 13.5, "shift": "morning" },
    { "date": "2026-07-03", "quantity": 14.0, "shift": "morning" }
  ]
}
```

---

## REST — Exporter Agent

### `POST /api/v1/agents/export`

**Request:**
```json
{
  "session_id": "uuid",
  "format": "csv",
  "include_unflagged_only": true
}
```
Regla: no puede exportar si quedan ítems con `is_flagged=true` e `is_approved=null`.
Segundo intento de exportar la misma sesión → HTTP 409 Conflict.

**Response 202:**
```json
{ "job_id": "uuid", "status": "queued" }
```

### `GET /api/v1/agents/export/jobs/{job_id}`

**Response 200:**
```json
{
  "status": "completed",
  "download_url": "/api/v1/exports/PSL-ALMACEN-GENERAL_20260724_morning.csv",
  "row_count": 87,
  "flagged_excluded": 2,
  "session_id": "uuid"
}
```

---

## REST — Supervisor Dashboard

### `GET /api/v1/supervisor/sessions/{session_id}/flagged-items`
Devuelve solo ítems con `is_flagged=true`. Perecederos RED primero.

### `POST /api/v1/supervisor/items/{item_id}/approve`
```json
{ "corrected_quantity": null }
```

### `POST /api/v1/supervisor/items/{item_id}/reject`
```json
{ "reason": "Conteo inconsistente con el reconteo físico." }
```

### `POST /api/v1/supervisor/sessions/{session_id}/bulk-approve`
```json
{ "item_ids": ["uuid1", "uuid2"] }
```

### `GET /api/v1/supervisor/sessions/{session_id}/events`
Devuelve el historial completo de eventos para auditoría interna. Solo visible en Supervisor Dashboard, nunca en Oracle.

---

## REST — Warehouses / Health

### `GET /api/v1/warehouses`
Lista de bodegas activas con el operario autenticado.

### `GET /api/v1/health`
Responde `{"status": "ok"}` sin autenticación. Usado por el frontend para detectar modo offline.
