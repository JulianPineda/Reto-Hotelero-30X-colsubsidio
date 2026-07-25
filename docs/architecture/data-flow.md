# Data Flow Diagram

Adaptado del spec.md §17. Muestra todos los paths incluyendo casos de error, modo offline y retroalimentación al catálogo.

```mermaid
flowchart TD
    A[Operario en Tablet + Headset] -->|Push-to-Talk, Audio 16kHz TLS| VA[Voice Agent]

    VA -->|Confianza STT < 0.75| N[Pide repetir: no pasa al Parser]
    N --> VA
    VA -->|3 intentos fallidos| MF[Fallback manual para ese ítem]

    VA -->|Confianza OK + score ≥ 0.75| P[Parser\nGemini 1.5 Flash NER\nartículo + cantidad + unidad]

    P --> CA{Catalog Agent\nQdrant cosine search}

    CA -->|score ≥ 0.80 — match único| AA[Auditor Agent\nUmbral + Tendencia]
    CA -->|0.50 ≤ score < 0.80 — múltiples candidatos| R[Repregunta al operario\ntop-3 alternativas]
    R --> VA
    CA -->|score < 0.50 — sin match| SH[sin_homologar = true\nguardar como texto libre]

    AA -->|sin anomalía| EV[Event Store\nItemValidated]
    AA -->|anomalía umbral o tendencia| FB[Repregunta por voz\nexplicación en español]
    FB --> VA
    FB -->|operario confirma| EV

    SH --> EV

    EV -->|corrección del operario| LRN[Learning Service\nnuevo sinónimo → Qdrant upsert]
    LRN --> CA

    EV --> EX[Exporter Agent\nSnapshot CSV/Excel Oracle]
    EV --> SD[Supervisor Dashboard\nHistorial completo de eventos]

    EX --> CSV[(Snapshot CSV\nformato Oracle My Inventory)]
    CSV --> AC[Auditor de Costos\nrevisa y aprueba]
    AC --> OR[Oracle My Inventory]

    VA -.->|TTS Audio 24kHz| A

    OFF[Pérdida de conectividad\no falla de headset] -.->|Pausa sesión de voz| MAN[Modo manual offline\nIndexedDB local]
    MAN -.->|Reconexión: pasa por\nCatalog Agent Y Auditor Agent| CA

    style A fill:#e1f5ff
    style VA fill:#fff3cd
    style AA fill:#f8d7da
    style R fill:#ffe5b4
    style N fill:#ffcccc
    style CSV fill:#d4edda
    style OR fill:#cce5ff
    style MAN fill:#e0e0e0
    style SD fill:#e8daff
    style LRN fill:#d4f8e8
```

---

## Detalle: Detección de Anomalías (Auditor Agent)

```mermaid
flowchart LR
    Q[quantity dictada] --> T1{Umbral Puntual\n¿diff > 20%\nO diff > 5 uds?}
    T1 -->|SÍ| FLAG1[flag_type = threshold]
    T1 -->|NO| T2{Tendencia\n¿rompe patrón\nde últimos 3-5 conteos?}
    T2 -->|SÍ| FLAG2[flag_type = trend]
    T2 -->|NO| OK[ItemValidated\nsin anomalía]
    FLAG1 --> BOTH{¿También\nrompe tendencia?}
    BOTH -->|SÍ| FLAG3[flag_type = both]
    BOTH -->|NO| FLAG1
```

---

## Detalle: Homologación Semántica (Catalog Agent)

```mermaid
flowchart LR
    IN[término dictado\nej. 'aceite premier'] --> EMB[Embedder\nsentence-transformers\n384 dims]
    EMB --> QD[Qdrant cosine search\ncolección catalog_items]
    QD --> SC{score\ncoseno}
    SC -->|≥ 0.80| AUTO[Auto-aceptar\nconfirmar en frase]
    SC -->|0.50–0.79| ALT[Top-3 alternativas\nrepregunta al operario]
    SC -->|< 0.50| LIBRE[sin_homologar = true\ntexto libre]
    AUTO --> HL[historical_counts\nupsert]
    ALT --> OP[Operario selecciona]
    OP --> HL
    LIBRE --> SUPER[visible en\nSupervisor Dashboard]
```

---

## Modelo de Eventos por Ítem

```mermaid
stateDiagram-v2
    [*] --> ItemCreated : primer conteo capturado
    ItemCreated --> ItemCorrected : operario usa "corregir último ítem"
    ItemCorrected --> ItemCorrected : corrección adicional
    ItemCorrected --> ItemDeleted : operario borra el ítem
    ItemCreated --> ItemValidated : Auditor Agent sin anomalía
    ItemCorrected --> ItemValidated : Auditor Agent sin anomalía tras corrección
    ItemCreated --> ItemRejected : Auditor Agent marca anomalía (pendiente revisión)
    ItemCorrected --> ItemRejected : Auditor Agent marca anomalía tras corrección
    ItemRejected --> ItemValidated : Auditor de Costos aprueba el ítem
    ItemRejected --> ItemDeleted : Auditor de Costos rechaza el ítem
    ItemDeleted --> [*]
    ItemValidated --> [*] : incluido en export Oracle
```
