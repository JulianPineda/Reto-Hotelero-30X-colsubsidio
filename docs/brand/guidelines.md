# Brand Guidelines — Colsubsidio · Reto Piscilago 30x

> Fuente oficial: `LogosCorp/Colores Oficiales.png`, `LogosCorp/LogoV1.png`, `LogosCorp/LogoV2.png` (fuera del repo — copias de trabajo en `frontend/public/brand/`).

## Paleta Oficial Corporativa

| Color | Pantone | CMYK | RGB | Hex |
|---|---|---|---|---|
| Amarillo Colsubsidio | 109 C | 0/18/100/0 | 255/208/0 | `#ffd000` |
| Azul Colsubsidio | 2196 C | 90/55/0/0 | 0/103/177 | `#0067b1` |
| Grafito | Cool Gray 11 C | 0/0/0/80 | 87/87/86 | `#575756` |

Tintas oficiales (80% / 60% / 40%) — `LogosCorp/Colores Oficiales.png` muestra los swatches sin hex impreso; valores calculados por mezcla estándar con blanco al porcentaje indicado:

| Color | 80% | 60% | 40% |
|---|---|---|---|
| Amarillo | `#ffd933` | `#ffe366` | `#ffec99` |
| Azul | `#3385c1` | `#66a4d0` | `#99c2e0` |
| Grafito | `#797978` | `#9a9a9a` | `#bcbcbb` |

## Paleta Funcional (UI — Reto Piscilago 30x)

| Token | Hex | Uso |
|---|---|---|
| Amarillo primario | `#ffd000` | Botón principal, OfflineBanner, acentos positivos |
| Azul primario | `#0067b1` | Headers, navegación, texto de énfasis |
| Grafito (neutral) | `#575756` | Texto secundario, iconografía neutra, footer — 3er color oficial |
| Rojo alerta | `#dc2626` | FlagBadge threshold, tráfico vencido |
| Naranja alerta | `#ea580c` | FlagBadge trend |
| Púrpura alerta | `#7c3aed` | FlagBadge both (umbral + tendencia) |
| Verde tráfico | `#22c55e` | TrafficLight green (≥8 días) |
| Amarillo tráfico | `#ffd000` | TrafficLight yellow (4–7 días) |
| Rojo tráfico | `#ef4444` | TrafficLight red (≤3 días) |
| Fondo claro | `#ffffff` | Fondo de pantalla principal |
| Fondo sutil | `#f8f9fa` | Fondo de tarjetas y tablas |
| Texto primario | `#1a1a2e` | Texto principal |
| Texto secundario | `#6b7280` | Labels y metadatos |

Ninguno de los colores funcionales/de alerta (rojo, naranja, púrpura, verde) es un color de marca — son semánticos (FlagBadge, TrafficLight) y no deben confundirse con la paleta corporativa.

---

## Logo

Archivos de trabajo en `frontend/public/brand/` (fuente original en `LogosCorp/`, fuera del repo):

| Archivo | Contenido | Uso |
|---|---|---|
| `logo-icon-yellow.png` | Ícono tangram (marca sin texto), amarillo `#ffd000` | Favicon, avatar, espacios reducidos, fondos claros/blancos |
| `logo-full-white.png` | Lockup completo "Colsubsidio" + ícono, en blanco | Headers/footers con fondo de color (azul `#0067b1` o grafito `#575756`) — **invisible sobre fondo blanco, no usar ahí** |

**Reglas:**
- No existe una variante del lockup completo en color oscuro para fondo claro — si se necesita un header claro, usar `logo-icon-yellow.png` solo, o aplicar el lockup blanco sobre una barra de color de marca (azul/grafito), nunca sobre blanco.
- Espacio de protección mínimo: dejar un margen alrededor del logo equivalente a la altura del ícono tangram (el bloque triangular a la izquierda del wordmark).
- Tamaño mínimo legible: ícono solo ≥ 24×24px; lockup completo ≥ 32px de alto.
- No estirar, rotar, recolorear fuera de la paleta oficial, ni añadir efectos (sombras, glow) al logo.
- Acceso programático: `logos.iconYellow` / `logos.fullWhite` en `frontend/src/theme.ts`.

---

## Tipografía

- **Fuente principal:** System UI stack → `"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`
- **Tamaño base:** 16px (1rem) para legibilidad en bodega
- **Números grandes (conteo):** 24px bold — cantidades visibles de lejos
- **Labels:** 14px regular

---

## Especificaciones de Componentes

### VoiceButton (el elemento más importante de la UI)
```
Tamaño mínimo: 120 × 120 px
Forma: circular
Estado idle: fondo #ffd000, icono micrófono negro
Estado grabando: fondo #dc2626, animación de pulso
Estado procesando: spinner, fondo #0067b1
Posición: centro inferior de CountSession
```

### Touch Targets
```
Mínimo: 48 × 48 px en TODOS los elementos interactivos
Justificación: operarios pueden usar guantes en cuartos fríos
Padding interno mínimo: 12px en botones
```

### OfflineBanner
```
Posición: fijo, top 0, ancho completo
Fondo: #ffd000
Texto: "Sin conexión — modo manual activo" en negro #1a1a2e
Ícono: WiFi-off
Siempre visible cuando navigator.onLine = false
Z-index: 9999 (nunca tapado por otros elementos)
```

### FlagBadge
```
threshold  → fondo #dc2626, texto blanco, etiqueta "Umbral"
trend      → fondo #ea580c, texto blanco, etiqueta "Tendencia"
both       → fondo #7c3aed, texto blanco, etiqueta "Umbral + Tendencia"
```

### ConfirmDialog
```
Modal centrado, fondo blanco, borde #0067b1 2px
Texto artículo: 18px bold, nunca truncado
Cantidad + unidad: 24px bold #0067b1
Botón "Confirmar": fondo #22c55e, texto blanco
Botón "Corregir": fondo #dc2626, texto blanco
Ambos botones: mínimo 48×120px
```

---

## Layout de Pantalla Tablet (768×1024px portrait)

```
┌─────────────────────────────────────┐
│ PSL-ALMACEN-GENERAL · Juan Pérez · Mañana │  ← Header azul #0067b1
│ 42 ítems contados  3 🚩             │
├─────────────────────────────────────┤
│                                     │
│  Lista de ítems contados            │  ← Scrollable, 60% de la altura
│  (ItemCards con FlagBadge)          │
│                                     │
├─────────────────────────────────────┤
│                                     │
│           🎙️                        │  ← VoiceButton centrado
│    [Mantén para hablar]             │
│                                     │
│  [⏸️ Pausar]    [📋 Revisar]        │  ← Acciones secundarias
└─────────────────────────────────────┘
```

---

## Accesibilidad

- Contraste mínimo: WCAG AA (4.5:1 texto normal, 3:1 texto grande)
- `#ffd000` sobre blanco: ratio 1.6:1 — **no cumple** para texto. Solo usar para fondos con texto oscuro.
- `#0067b1` sobre blanco: ratio 6.2:1 — cumple AA para texto normal.
- Todos los botones con `aria-label` descriptivo.
- `ConfirmDialog` con `role="dialog"` y `aria-labelledby`.
- `FlagBadge` con `aria-label="Anomalía por [tipo]"` para lectores de pantalla.
