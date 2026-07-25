# EPIC 2 — Voice Pipeline
**Sprint 1 · ~5 días · 14 puntos**

Prerequisito: T-001, T-002, T-004 completados.

---

## T-005 — STTProvider ABC + Gemini Live Adapter
**Puntos:** 5 | **Asignado a:** Ejecutor

> **ADR-001 (CLAUDE.md §1.1):** implementación de referencia migrada de OpenAI Realtime API a **Gemini 1.5 Flash (Live API)** por latencia y para unificar el proveedor de voz + NLP. La abstracción `STTProvider` no cambia — cualquier otro proveedor (incluido OpenAI) sigue siendo intercambiable sin tocar el resto del pipeline.

### Descripción
Abstracción del motor de voz para que el sistema no esté acoplado a un proveedor específico.

### Archivos a crear
- `backend/app/agents/voice/stt_provider.py` — clase abstracta `STTProvider`
- `backend/app/agents/voice/gemini_live.py` — adaptador concreto Gemini Live API (WebSocket)
- `backend/app/agents/voice/schemas.py`

### Interfaz STTProvider
```python
class STTProvider(ABC):
    @abstractmethod
    async def connect(self, session_config: SessionConfig) -> None: ...

    @abstractmethod
    async def send_audio(self, chunk: bytes) -> None: ...

    @abstractmethod
    async def receive(self) -> AsyncIterator[TranscriptEvent]: ...

    @abstractmethod
    async def disconnect(self) -> None: ...
```

### Configuración VAD para bodega (60 dB de ruido)
```python
realtime_input_config = {
    "automatic_activity_detection": {
        "start_of_speech_sensitivity": "START_SENSITIVITY_LOW",  # ignora ruido ambiental
        "end_of_speech_sensitivity": "END_SENSITIVITY_LOW",
        "silence_duration_ms": 600,    # operarios hablan en frases cortas
        "prefix_padding_ms": 300,
    },
}
generation_config = {
    "response_modalities": ["AUDIO"],
    "speech_config": {"language_code": "es-CO"},  # español colombiano
}
model = "gemini-1.5-flash"  # confirmar variante Live disponible al momento de implementar
```

### Seguridad (CWE-798)
- `GEMINI_API_KEY` leída desde `config.py` (pydantic-settings) — nunca hardcodeada.
- Fail-fast al arrancar si la variable no está presente.

### Criterio de aceptación
- Adaptador conecta al WebSocket de Gemini Live API sin errores.
- Clase abstracta lista para que un adaptador alternativo (ej. `OpenAIRealtimeAdapter`) pueda implementarla sin cambiar el resto del pipeline.
- Latencia end-to-end (`ptt_stop` → `confirmation_request`) < 2s en ≥95% de las interacciones (spec.md §11, criterio #2) — validar en campo con ruido de 60 dB antes de cerrar el ticket.

---

## T-006 — WebSocket Voice Endpoint (PTT + Barge-in)
**Puntos:** 3 | **Asignado a:** Ejecutor

### Descripción
Endpoint WebSocket que orquesta la sesión de voz: PTT state machine, barge-in, dispatch al pipeline.

### Archivos a crear
- `backend/app/agents/voice/router.py` — `WS /ws/voice/{session_id}`
- `backend/app/agents/voice/session.py` — PTT state machine + barge-in buffer

### State machine PTT
```
idle → listening (ptt_start)
listening → processing (ptt_stop)
processing → confirming (transcript ready + confidence ≥ 0.75)
processing → idle (confidence < 0.75 → pide repetir)
confirming → idle (confirm=true → item saved)
confirming → listening (confirm=false → re-dictar)
confirming → listening (barge_in → interrumpir TTS)
```

### Autenticación WS (CWE-1390)
```python
async def verify_ws_token(token: str) -> OperatorClaims:
    """Verifica JWT antes de aceptar la conexión WS."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return OperatorClaims(**payload)
    except jwt.InvalidTokenError:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
```

### Criterio de aceptación
- Conexión sin token válido: cierra con código 1008.
- PTT → audio → confirmación dígito a dígito funciona end-to-end con payload mock.
- Barge-in: mensaje de tipo `barge_in` corta el TTS en curso.

---

## T-007 — Parser Agent: NER en Español
**Puntos:** 3 | **Asignado a:** Ejecutor

### Descripción
Extrae `{artículo, cantidad, unidad}` del texto transcrito usando Gemini 1.5 Flash con prompt estructurado (ADR-001 — reemplaza Claude Haiku, unifica el proveedor con el Voice Agent de T-005).

### Archivos a crear
- `backend/app/agents/parser/router.py` — `POST /api/v1/agents/parse`
- `backend/app/agents/parser/extractor.py` — llamada Gemini 1.5 Flash con structured output (`response_schema`)
- `backend/app/agents/parser/unit_normalizer.py` — mapeo coloquial → UOM
- `backend/app/agents/parser/schemas.py`
- `backend/tests/test_parser.py`

### Prompt base (system)
```
Eres un extractor de datos de inventario de un parque de recreación colombiano (Piscilago).
Dado un texto en español de un operario de bodega, extrae EXACTAMENTE:
- article: nombre del producto sin cantidades ni unidades
- quantity: número decimal
- unit: unidad de medida normalizada (ver lista)

Unidades válidas: kg, g, L, mL, unit, dozen, case, GAL, oz
Si no puedes extraer alguno de los tres campos, devuelve null para ese campo.
Solo devuelve JSON, sin explicaciones adicionales.
```

### Validación de input (CWE-89, input injection)
```python
class ParseRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=500,
                           pattern=r'^[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ0-9\s\.,\-]+$')
    session_id: UUID
    language: str = Field(default="es-CO", pattern=r'^[a-z]{2}-[A-Z]{2}$')
```

### Seguridad (CWE-798)
- `GEMINI_API_KEY` desde `config.py`, nunca hardcodeada.
- Llamada a Gemini nunca directamente desde lógica de negocio — siempre a través de `llm_provider.py`.

### Criterio de aceptación
```bash
pytest backend/tests/test_parser.py -v
# Casos: "veinte kilos de harina de trigo" → {article: "harina de trigo", quantity: 20, unit: "kg"}
# "noventa galones de aceite vegetal" → {article: "aceite vegetal", quantity: 90, unit: "GAL"}
# "catorce" → {article: null, quantity: 14, unit: null}
```

---

## T-008 — Confirmación Dígito a Dígito + ConfirmDialog UI
**Puntos:** 3 | **Asignado a:** Ejecutor (backend) + UI Expert (frontend)

### Descripción
Backend: generar el texto de confirmación dígito a dígito.
Frontend: componente `ConfirmDialog` que muestra la confirmación y captura la respuesta del operario.

### Regla (CLAUDE.md §3.3)
Para cantidades ≥ 2 dígitos:
```
"¿{dígito1}, {dígito2}[, {dígito3}...]: {cantidad} {unidad} de {nombre_completo}?"
```

### Backend — generador de confirmación
```python
def build_digit_confirmation(quantity: float, unit: str, article_name: str) -> str:
    quantity_str = str(int(quantity)) if quantity == int(quantity) else str(quantity)
    if len(quantity_str.replace(".", "")) >= 2:
        digits = ", ".join(list(quantity_str.replace(".", "")))
        return f"¿{digits}: {quantity_str} {unit} de {article_name}?"
    return f"¿{quantity_str} {unit} de {article_name}?"
```

### Frontend — ConfirmDialog
```tsx
// Muestra nombre completo, sin truncar (CLAUDE.md §4)
// Botones: "Confirmar" (verde #22c55e) y "Corregir" (rojo #ef4444)
// Touch targets ≥ 48px
// Teclado accesible: Enter = confirmar, Escape = corregir
```

### Criterio de aceptación
- "90 GAL de Aceite Vegetal Premier 5L" → "¿Nueve, cero: 90 GAL de Aceite Vegetal Premier 5L?"
- "5 kg de sal" → "¿5 kg de sal?" (sin desglose — un solo dígito)
- ConfirmDialog visible en Chromium con touch targets ≥ 48px (verificar en DevTools > Device mode > tablet).
