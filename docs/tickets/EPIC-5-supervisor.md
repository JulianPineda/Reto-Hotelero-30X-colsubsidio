# EPIC 5 — Supervisor Dashboard
**Sprint 2 · ~3 días · 5 puntos**

Prerequisito: T-011, T-012 completados (datos de anomalías disponibles).

---

## T-014 — Supervisor API: Review + Approve/Reject
**Puntos:** 2 | **Asignado a:** Ejecutor

### Descripción
Endpoints REST para que el Auditor de Costos gestione los ítems flaggeados: revisar, aprobar (con o sin corrección de cantidad), rechazar, aprobar en bulk.

### Archivos a crear
- `backend/app/api/supervisor.py`
- `backend/tests/test_supervisor_api.py`

### Endpoints

```
GET  /api/v1/supervisor/sessions/{session_id}/flagged-items
     → Lista ítems con is_flagged=true, ordenados: RED perecederos primero, luego por flag_type
     → Incluye: motivo, % desviación, histórico de referencia, confidence, timestamp

POST /api/v1/supervisor/items/{item_id}/approve
     Body: { "corrected_quantity": null }  (null = acepta la cantidad dictada)
     → Emite ItemValidated, actualiza is_approved=true

POST /api/v1/supervisor/items/{item_id}/reject
     Body: { "reason": "string" }
     → Emite ItemRejected, actualiza is_approved=false

POST /api/v1/supervisor/sessions/{session_id}/bulk-approve
     Body: { "item_ids": ["uuid1", "uuid2"] }
     → Aprueba múltiples ítems en una transacción

GET  /api/v1/supervisor/sessions/{session_id}/events
     → Historial completo de eventos de la sesión (para auditoría interna)
     → Solo disponible para el Auditor de Costos, no para Oracle
```

### Regla de gate de exportación
```python
async def can_export(session_id: UUID, db: AsyncSession) -> bool:
    """Verificar que no queden ítems flaggeados pendientes de revisión."""
    pending = await db.execute(
        select(func.count(CountItem.id))
        .where(CountItem.session_id == session_id)
        .where(CountItem.is_flagged == True)
        .where(CountItem.is_approved == None)
    )
    return pending.scalar() == 0
```

### Tests clave
```python
# test_supervisor_api.py
async def test_cannot_export_with_pending_flags():
    # Crear sesión con 1 ítem flaggeado sin resolver
    # Intentar exportar → debe responder 409 Conflict o 422

async def test_bulk_approve_emits_events():
    # Bulk approve 3 ítems → 3 eventos ItemValidated en event store

async def test_reject_marks_not_approved():
    # Reject ítem → is_approved=False, rejection_reason persiste
```

### Criterio de aceptación
```bash
pytest backend/tests/test_supervisor_api.py -v  # todos pasan
```

---

## T-015 — Supervisor Dashboard UI
**Puntos:** 3 | **Asignado a:** UI Expert

### Descripción
Página React para el Auditor de Costos: tabla de ítems flaggeados con motivo, historial de referencia, botones de acción, y perecederos con semáforo.

### Archivos a crear
- `frontend/src/pages/SupervisorDashboard/index.tsx`
- `frontend/src/pages/SupervisorDashboard/FlaggedItemRow.tsx`
- `frontend/src/pages/SupervisorDashboard/BulkActionBar.tsx`
- `frontend/src/components/FlagBadge/index.tsx`
- `frontend/src/components/TrafficLight/index.tsx`

### Layout de la tabla

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Supervisor Dashboard — Bodega PSL-ALMACEN-GENERAL · Turno Mañana            │
│ 8 ítems pendientes de revisión                          [Aprobar todos ✓]   │
├────────────────┬──────┬────────┬──────────────────────────────┬─────────────┤
│ Artículo       │ Cant │  Flag  │ Motivo                       │  Acción     │
├────────────────┼──────┼────────┼──────────────────────────────┼─────────────┤
│ 🔴 Leche UHT  │  14L │ umbral │ 84.4% por debajo del prom... │ ✓ ✗        │
│ Aceite Vegetal │  90G │ trend  │ Rompe patrón estable de...   │ ✓ ✗        │
│ Harina Trigo   │  20k │ both   │ Umbral + ruptura de...       │ ✓ ✗        │
└────────────────┴──────┴────────┴──────────────────────────────┴─────────────┘
```

### FlagBadge colors (CLAUDE.md §2)
```tsx
const FLAG_COLORS = {
  threshold: '#dc2626',  // rojo
  trend: '#ea580c',      // naranja
  both: '#7c3aed',       // púrpura
};
```

### TrafficLight component
```tsx
// Dot indicator: rojo/amarillo/verde según días a vencimiento
// Solo visible cuando is_perishable=true
const TRAFFIC_COLORS = {
  red: '#ef4444',
  yellow: '#ffd000',
  green: '#22c55e',
};
```

### Detalle de anomalía expandible
Al hacer click en una fila, expandir para mostrar:
- Motivo completo (flag_reason)
- Histórico de referencia (últimos 3-5 conteos con fecha)
- Confianza de transcripción y homologación
- Campo de cantidad corregida (solo si el supervisor quiere overridear)

### Criterio de aceptación
- Ítems RED perecederos aparecen primero en la lista.
- FlagBadge con colores correctos por tipo.
- Botones "Aprobar" y "Rechazar" con touch targets ≥ 48px.
- "Aprobar todos" hace bulk approve de todos los ítems pendientes visibles.
- Dashboard visible y funcional en Chromium tablet mode (768×1024px portrait).
