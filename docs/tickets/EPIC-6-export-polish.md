# EPIC 6 — Export + Perishables + Polish
**Sprint 3 · ~3 días · 8 puntos**

Prerequisito: Epics 1–5 completados.

---

## T-016 — Exporter Agent: CSV Oracle + Excel con Brand
**Puntos:** 3 | **Asignado a:** Ejecutor

### Descripción
Genera el snapshot final en el formato exacto de Oracle My Inventory (CSV/Excel). Solo incluye ítems aprobados por el Auditor de Costos.

### Archivos a crear
- `backend/app/agents/exporter/router.py` — `POST /api/v1/agents/export`, `GET /jobs/{id}`
- `backend/app/agents/exporter/oracle_csv.py`
- `backend/app/agents/exporter/excel_builder.py`
- `backend/app/agents/exporter/schemas.py`
- `backend/tests/test_exporter.py`

### Columnas Oracle CSV (orden exacto — CLAUDE.md §3.5)
```
WAREHOUSE_CODE|ORACLE_CODE|ITEM_NAME|UNIT|QUANTITY|COUNT_DATE|SHIFT|OPERATOR_ID|SESSION_ID|IS_VALIDATED|SUPERVISOR_ID|EXPORT_TIMESTAMP
```
- Delimitador: `|` (pipe)
- Decimal: `.` (punto)
- Codificación: UTF-8 sin BOM
- QUANTITY: 4 decimales (ej. `20.0000`)
- COUNT_DATE: `YYYY-MM-DD`
- EXPORT_TIMESTAMP: `YYYY-MM-DDTHH:MM:SS-05:00`

### Seguridad — Path Traversal (CWE-22)
```python
BASE_EXPORT_DIR = Path(settings.EXPORT_BASE_DIR).resolve()

def get_export_path(session_id: UUID, warehouse_code: str, count_date: date, shift: str) -> Path:
    # Construir filename con caracteres seguros (alfanumérico + guión + punto)
    safe_warehouse = re.sub(r'[^a-zA-Z0-9\-]', '', warehouse_code)
    filename = f"{safe_warehouse}_{count_date}_{shift}_{session_id.hex[:8]}.csv"

    export_path = (BASE_EXPORT_DIR / filename).resolve()

    # Verificar que la ruta final está dentro del directorio permitido
    if not export_path.is_relative_to(BASE_EXPORT_DIR):
        raise ValueError("Path traversal detectado en nombre de archivo de exportación")

    return export_path
```

### Gate de exportación (Validador Gate G1)
```python
async def validate_can_export(session_id: UUID, db: AsyncSession) -> None:
    # 1. Verificar que no hay ítems flaggeados pendientes
    pending_flags = ... # count de is_flagged=True AND is_approved=None
    if pending_flags > 0:
        raise ExportBlockedError(f"{pending_flags} ítem(s) flaggeados sin revisar")

    # 2. Verificar que la sesión no fue ya exportada (HTTP 409)
    session = await db.get(CountSession, session_id)
    if session.exported_at is not None:
        raise SessionAlreadyExportedError("Esta sesión ya fue exportada")
```

### Excel con brand Colsubsidio
- Header row con fondo `#0067b1` y texto blanco
- Ítems aprobados en verde claro `#d4edda`
- Título con logo placeholder y amarillo `#ffd000`

### Tests
```python
# test_exporter.py
async def test_csv_column_order():
    """Verifica que las columnas del CSV coinciden exactamente con CLAUDE.md §3.5."""
    csv_content = await generate_csv(mock_session)
    header = csv_content.split('\n')[0]
    expected = "WAREHOUSE_CODE|ORACLE_CODE|ITEM_NAME|UNIT|QUANTITY|COUNT_DATE|SHIFT|OPERATOR_ID|SESSION_ID|IS_VALIDATED|SUPERVISOR_ID|EXPORT_TIMESTAMP"
    assert header.strip() == expected

async def test_decimal_separator_is_dot():
    ...

async def test_second_export_returns_409():
    ...

async def test_path_traversal_rejected():
    with pytest.raises(ValueError, match="Path traversal"):
        get_export_path(session_id, "../../../etc/passwd", date.today(), "morning")
```

### Criterio de aceptación
```bash
pytest backend/tests/test_exporter.py -v  # todos pasan, incluyendo test_path_traversal
```

---

## T-017 — Perishables Module
**Puntos:** 2 | **Asignado a:** Ejecutor (backend) + UI Expert (frontend)

### Descripción
Módulo completo de perecederos: validación de fecha, cálculo de semáforo, integración en el flujo de conteo y en el Supervisor Dashboard.

### Archivos a crear
- `backend/app/services/perishables.py`
- `frontend/src/components/TrafficLight/index.tsx` (ya mencionado en T-015)

### Backend
```python
def compute_traffic_light(expiry_date: date) -> Literal["red", "yellow", "green"]:
    today = date.today()
    days_remaining = (expiry_date - today).days

    if days_remaining <= 3:
        return "red"
    elif days_remaining <= 7:
        return "yellow"
    else:
        return "green"

def validate_perishable_item(catalog_item: CatalogItem, expiry_date: date | None) -> None:
    """Lanza error si es perecedero y no tiene fecha de vencimiento."""
    if catalog_item.is_perishable and expiry_date is None:
        raise PeishableItemMissingExpiryError(
            f"El artículo '{catalog_item.name}' es perecedero y requiere fecha de vencimiento."
        )
```

### Integración en el flujo de voz
Cuando el Catalog Agent identifica un artículo perecedero, el Voice Agent repregunta:
```
"Aceite de oliva identificado como perecedero. ¿Cuál es la fecha de vencimiento?"
Operario: "vence el primero de agosto"
Voice Agent: "primero de agosto de dos mil veintiséis, confirmas"
```

### Frontend TrafficLight
```tsx
// Dot de 16x16px con el color correspondiente
// Tooltip: "Vence en X días" | "Vence hoy" | "Vencido"
// Siempre visible cuando is_perishable=true, incluso en la lista de conteo
```

---

## T-018 — E2E Integration Test
**Puntos:** 3 | **Asignado a:** Ejecutor (Validador Gate final)

### Descripción
Test de integración end-to-end que simula una sesión completa de conteo y verifica todos los criterios de aceptación críticos del spec.

### Archivo a crear
- `backend/tests/test_e2e_full_session.py`

### Escenario de test
```python
# Una sesión completa con:
# - 10 ítems contados
# - 2 ítems flaggeados (1 por umbral, 1 por tendencia)
# - 1 ítem perecedero con semáforo yellow
# - 1 ítem sin homologar
# - 1 ítem en modo offline
# - Supervisor aprueba los 2 flaggeados
# - Exportación a CSV

async def test_full_session_happy_path(db, qdrant_mock):
    # 1. Crear sesión
    # 2. Seedear histórico para oracle_code=7290 "ACEITE" en PSL-ALMACEN-GENERAL
    # 3. Enviar 10 ítems al pipeline (parse → homologate → audit)
    # 4. Verificar que 2 ítems tienen is_flagged=True
    # 5. Supervisor aprueba ambos
    # 6. Exportar → verificar CSV
    # 7. Segundo export → 409 Conflict
    # 8. Verificar event log tiene 10 ItemCreated + 2 ItemRejected + 2 ItemValidated

    ...

    # Criterio de aceptación #1: columnas CSV idénticas al spec
    csv_lines = exported_csv.split('\n')
    assert csv_lines[0] == "WAREHOUSE_CODE|ORACLE_CODE|..."

    # Criterio #5: anomalía por umbral
    flagged_threshold = [i for i in items if i.flag_type == "threshold"]
    assert len(flagged_threshold) >= 1

    # Criterio #6: anomalía por tendencia
    flagged_trend = [i for i in items if i.flag_type == "trend"]
    assert len(flagged_trend) >= 1

    # Criterio #7: confirmación dígito a dígito (verificada en test_parser.py)

    # Criterio #10: Oracle recibe solo estado final
    assert all(i.event_type == "ItemValidated" for i in items_in_export)
    # El historial completo (ItemCreated, ItemRejected, ItemValidated) existe en event store
    assert session_events_count == 10 + 2 + 2  # Created + Rejected + Validated
```

### Criterio de aceptación
```bash
pytest backend/tests/test_e2e_full_session.py -v  # pasa
pytest backend/tests/ -v  # suite completa verde
```

---

## Resumen Final: Demo Ready Checklist

Antes de la demo con el jurado, verificar:

```
[ ] docker compose up -d → todos los servicios healthy
[ ] python scripts/import_catalog.py → 48 bodegas + 1041 artículos generados
[ ] python scripts/seed_catalog.py --csv data/catalog.csv → 1041 artículos indexados
[ ] pytest backend/tests/ -v → verde
[ ] http://localhost:3000 abre en Chrome, modo tablet (DevTools)
[ ] Flujo: Seleccionar bodega → Dictar "aceite vegetal noventa galones" → Confirmación dígito a dígito
[ ] Flujo: Dictar cantidad anómala → Auditor Agent repregunta con explicación en español
[ ] Supervisor Dashboard muestra ítems flaggeados con motivo y porcentaje exacto
[ ] Export CSV → verificar columnas Oracle con un diff contra la plantilla
[ ] Segundo export intenta → HTTP 409
[ ] Brand: #ffd000 y #0067b1 visibles. VoiceButton ≥ 120px
```
