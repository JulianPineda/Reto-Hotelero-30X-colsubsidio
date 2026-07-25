# CLAUDE.md — Reto Piscilago 30x · Colsubsidio Innovación

> **Fuente de verdad operativa.** Todos los agentes de IA leen este archivo antes de actuar.
> Fuente de negocio: `spec.md` (la versión del usuario). Este archivo traduce el spec a reglas ejecutables.

---

## 1. Contexto del Dominio

Sistema multiagente que reemplaza el conteo de inventario en papel por captura conversacional validada.
**48 bodegas de Piscilago** (parque de recreación y piscinas de Colsubsidio — no un hotel: alimentos y bebidas, medicamentos de enfermería, papelería, ferretería, dotación y zoológico), con un catálogo maestro real de **1041 artículos únicos** (`data/catalog.csv`, importado de `data/raw/BODEGAS_Y_STOCK.xlsx` vía `scripts/import_catalog.py`).

**Pipeline central:**
```
Voz del Operario → Voice Agent → Parser → Catalog Agent → Auditor Agent → Exporter → Oracle CSV
```

**Lo que el sistema NO hace:**
- No integra transaccionalmente con Oracle My Inventory (solo entrega CSV/Excel).
- No corrige el stock teórico directamente.
- No opera en teléfonos personales (solo tablets corporativas).
- No captura ni valida la recepción de mercancía (remisión/factura física del proveedor en el almacén principal — `spec.md` §0.1). El pipeline arranca en el conteo de bodega (paso 1 de `spec.md` §5), no en la recepción. Ningún ticket debe agregar OCR/captura de remisiones sin una decisión explícita de negocio que amplíe este alcance.

### 1.1 Decisión de Arquitectura: Proveedor de Modelos (ADR-001)

> **Contexto:** una conversación previa señaló las ventajas de Gemini 1.5 Flash (latencia, costo, streaming de audio nativo) frente a la combinación originalmente planteada — OpenAI Realtime API para voz + Claude Haiku para NER. La vara de medir es el criterio de aceptación de latencia de voz (`spec.md` §11, criterio #2): **< 2 segundos** desde `ptt_stop` hasta `confirmation_request` en ≥95% de las interacciones.

**Decisión:**
- **Voice Agent (STT + streaming bidireccional):** Gemini 1.5 Flash (Live API) reemplaza a OpenAI Realtime API como implementación de referencia de `STTProvider`.
- **Parser Agent (NER):** Gemini 1.5 Flash reemplaza a Claude Haiku — unifica el stack de voz + NLP en un solo proveedor y elimina un salto de red entre proveedores distintos en el hot path.
- **Auditor Agent (explicaciones NL):** Gemini 1.5 Flash, por la misma razón de unificación (antes Claude Haiku como fallback cuando la plantilla determinista es insuficiente).

**Lo que NO cambia:**
- La abstracción `STTProvider` (ABC) y `llm_provider.py` — `spec.md` §13 es deliberadamente agnóstico de proveedor; esta es una decisión de implementación, no de contrato.
- El criterio de aceptación de latencia sigue siendo la vara de medir: si Gemini 1.5 Flash no cumple <2s en pruebas de campo con ruido de bodega (60 dB), se reevalúa el proveedor sin tocar el resto del pipeline.

**Variables de entorno afectadas:** se retiran `OPENAI_API_KEY` y `ANTHROPIC_API_KEY`; se agrega `GEMINI_API_KEY` (ver `.env.example`).

---

## 2. Brand Colsubsidio

> Fuente oficial: `LogosCorp/Colores Oficiales.png` + `LogosCorp/LogoV1.png` (ícono) + `LogosCorp/LogoV2.png` (lockup). Detalle completo, tintas y reglas de logo en `docs/brand/guidelines.md`.

| Token | Valor | Uso |
|---|---|---|
| `color.primary.yellow` | `#ffd000` | Pantone 109 C — Botón principal, OfflineBanner, acentos |
| `color.primary.blue` | `#0067b1` | Pantone 2196 C — Headers, texto sobre fondo claro, links |
| `color.neutral.grafito` | `#575756` | Pantone Cool Gray 11 C — 3er color oficial: texto secundario, iconografía neutra |
| `color.flag.threshold` | `#dc2626` | FlagBadge — anomalía por umbral |
| `color.flag.trend` | `#ea580c` | FlagBadge — anomalía por tendencia |
| `color.flag.both` | `#7c3aed` | FlagBadge — umbral + tendencia simultáneos |
| `color.traffic.red` | `#ef4444` | TrafficLight — vence ≤3 días |
| `color.traffic.yellow` | `#ffd000` | TrafficLight — vence en 4–7 días |
| `color.traffic.green` | `#22c55e` | TrafficLight — vence en ≥8 días |

---

## 3. Reglas de Negocio Críticas

### 3.1 Detección de Anomalías (Auditor Agent)

**Regla A — Umbral puntual:**
> FLAG si la cantidad contada difiere del promedio histórico en **más del 20%** O en **más de 5 unidades** (la condición que sea mayor).
> Ambas condiciones son independientes — cualquiera sola es suficiente para marcar.

**Regla B — Tendencia histórica:**
> Evaluar la **serie de los últimos 3 a 5 conteos validados** para la misma combinación `oracle_code + warehouse_id + shift`.
> FLAG si el conteo actual rompe un patrón estable de forma marcada, aunque no cruce el umbral puntual.
> Usar `flag_type = "trend"` para este caso.
> Si hay < 3 conteos históricos: NO aplicar detección por tendencia, solo por umbral.

**Regla C — Prioridad de turno:**
> Priorizar conteos del mismo turno (mañana/tarde/noche) al construir la serie.
> Si hay < 3 en el mismo turno: completar con conteos de otros turnos.

**Formato de la explicación:**
> Siempre en **español**. Incluir: porcentaje de desviación exacto, valor dictado, promedio histórico, número de conteos en la serie.
> Ejemplo: `"La cantidad (14 kg) representa una caída del 84.4 % respecto al promedio histórico de los últimos 3 conteos en esta bodega (90, 92, 88). Promedio: 90 kg."`

### 3.2 Homologación de Catálogo (Catalog Agent)

| Score coseno | Acción |
|---|---|
| ≥ 0.80 | Auto-aceptar. Confirmar en la misma frase dígito a dígito. |
| 0.50 – 0.79 | Mostrar top-3 alternativas al operario. Requiere selección explícita. |
| < 0.50 | Marcar `sin_homologar = true`. Guardar como texto libre. No bloquea el flujo. |

**Umbral de confianza de transcripción:** Si el score STT < 0.75, NO pasar al Parser. Pedir repetición. Tras 3 intentos fallidos: ofrecer entrada manual solo para ese ítem.

### 3.3 Confirmación Dígito a Dígito

Para cantidades de **2 o más dígitos**:
> Formato: `"¿[DÍGITO_1], [DÍGITO_2]: [CANTIDAD] [UNIDAD] de [NOMBRE_COMPLETO]?"`
> Ejemplo: `"¿Nueve, cero: noventa galones de Aceite Vegetal Premier 5L?"`
> El nombre del artículo NUNCA se trunca en la confirmación.

### 3.4 Ciclo de Vida de Sesión

```
in_progress → pending_review → approved → exported
```

- **Sin transiciones hacia atrás.**
- Una sesión solo puede exportarse **una vez** — segundo intento: HTTP 409 Conflict.
- Para exportar: **TODOS** los ítems con `is_flagged = true` deben tener `is_approved` no-nulo (aprobado o rechazado por el Auditor de Costos).

### 3.5 Formato CSV Oracle My Inventory

**Columnas en orden exacto (pipe `|` como delimitador):**
```
WAREHOUSE_CODE|ORACLE_CODE|ITEM_NAME|UNIT|QUANTITY|COUNT_DATE|SHIFT|OPERATOR_ID|SESSION_ID|IS_VALIDATED|SUPERVISOR_ID|EXPORT_TIMESTAMP
```

- `QUANTITY`: 4 decimales, separador decimal **punto** `.`.
- `COUNT_DATE`: ISO 8601 `YYYY-MM-DD`.
- Codificación: **UTF-8 sin BOM** por defecto.
- Fila de encabezado: siempre incluida.
- **Excluir** ítems con `is_approved = false` (rechazados por el supervisor).

### 3.6 Perecederos

- Si `catalog_item.is_perishable = true`: `expiry_date` es **obligatorio** — rechazar el ítem si no se provee.
- **Semáforo:**
  - ROJO (`red`): `expiry_date - hoy ≤ 3 días`
  - AMARILLO (`yellow`): `4–7 días`
  - VERDE (`green`): `≥ 8 días`
- Ítems `RED` aparecen primero en la cola de revisión del Supervisor Dashboard.

### 3.7 Event Sourcing — Invariantes

- La tabla `events` es **append-only**. Cero `UPDATE`, cero `DELETE`, cero soft-delete.
- Todo cambio de estado debe emitir el evento **antes** de persistir el nuevo estado.
- Los números de secuencia son monotónicos por `aggregate_id`.

Tipos de evento válidos:
```
ItemCreated | ItemCorrected | ItemDeleted | ItemValidated | ItemRejected
```

### 3.8 Modo Offline

- Voz deshabilitada cuando sin conectividad. Entrada manual por teclado/touch activa.
- Al reconectar: **todos** los ítems offline pasan por `Catalog Agent` + `Auditor Agent`.
- `is_offline = true` persiste en cada `count_item` offline para trazabilidad de auditoría.

---

## 4. Reglas UX (para el UI Expert Agent)

| Elemento | Especificación |
|---|---|
| `VoiceButton` | Mínimo 120×120 px. Es el affordance principal de `CountSession`. |
| Touch targets | Mínimo 48×48 px en todos los elementos interactivos (operarios pueden usar guantes). |
| `OfflineBanner` | Siempre visible cuando offline. Posición fija top. Fondo `#ffd000`. |
| `ConfirmDialog` | Muestra nombre completo, cantidad Y unidad. Sin truncar. |
| Pantalla durante conteo | El stock teórico **NUNCA** se muestra durante el conteo ciego. |

---

## 5. Reglas de Seguridad para el Ejecutor de Código

- **Secretos**: todas las API keys en variables de entorno. Validar presencia al arranque (fail-fast). Ver `.env.example` para la lista completa.
- **SQL**: solo SQLAlchemy ORM o consultas parametrizadas. Nunca concatenación de strings para SQL.
- **Paths de export**: validar con `pathlib.Path.resolve()` + `is_relative_to(BASE_EXPORT_DIR)` antes de escribir.
- **Input del transcript de voz**: validar con Pydantic antes de pasar al Parser. Longitud máxima 500 chars. Solo caracteres alfanuméricos + espacios + unidades de medida.
- **WebSocket auth**: verificar JWT token en el handshake inicial del WS (`Authorization: Bearer <token>` en el header de upgrade o query param `token=`).
- **CORS**: no usar wildcard `*`. En demo local: `ALLOWED_ORIGINS` lista explícita en `.env`.
- **Errores**: nunca exponer stack traces al cliente. Responder con mensaje genérico + `correlation_id` para trazabilidad en logs.

---

## 6. KPIs del Sistema (para orientar decisiones de diseño)

| KPI | Meta |
|---|---|
| Latencia de voz (P95) | < 2 segundos desde `ptt_stop` hasta `confirmation_request` |
| WER en campo (60 dB) | ≥ 95% de precisión |
| Homologación exitosa | % ítems sin `sin_homologar` por sesión |
| Falsos positivos de anomalía | Anomalías marcadas luego descartadas por Auditor de Costos |

---

## 7. Supuestos Activos (a validar en campo)

- Umbral STT: 0.75 (inicial, calibrar con datos reales).
- Ventana de tendencia: 3–5 conteos (parametrizable en `config.py`).
- Headset obligatorio — si se desconecta: pausa automática de sesión de voz.
- Tablet SO: browser Chromium moderno (Web Audio API disponible).
- Latencia de Gemini 1.5 Flash Live API en campo (ruido 60 dB) — validar que cumple <2s (ADR-001, §1.1) antes de la demo; si no cumple, reevaluar proveedor sin tocar el resto del pipeline.
