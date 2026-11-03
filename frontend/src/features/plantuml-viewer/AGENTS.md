# Feature `plantuml-viewer/` — Render de diagramas PlantUML

> **Destinatario:** Agentes de IA que trabajen en `frontend/src/features/plantuml-viewer/`.
> **Ámbito:** carga del motor PlantUML, cola de render, envoltura de fuente y visor con pan/zoom.
> **Nivel superior:** [`../AGENTS.md`](../AGENTS.md) (capa `features`).

---

## 1. Estructura

```
plantuml-viewer/
├── ui/
│   └── plantuml-viewer.tsx        # Componente visor (forwardRef)
├── model/
│   ├── types.ts                   # RenderState, PlantUmlModule, PanZoomState, PlantUmlViewerProps
│   ├── useRender.ts               # source → { svg, state, error }
│   ├── usePanZoom.ts              # zoom/pan (controlado o interno)
│   ├── plantuml-core.d.ts         # Declaración ambient de @plantuml/core
│   └── useRender.test.tsx
├── lib/
│   ├── engine-loader.ts           # loadViz, loadPlantUmlModule, preloadPlantUmlEngine
│   ├── render-queue.ts            # renderPlantUml (serializado + timeout + caché)
│   ├── wrap-plantuml.ts           # wrapPlantUmlSource
│   ├── zoom.ts                    # ZOOM_MIN, ZOOM_MAX, ZOOM_STEP_FACTOR
│   ├── render-queue.test.ts
│   └── wrap-plantuml.test.ts
└── index.ts
```

**Exports:** `PlantUmlViewer`, tipo `PanZoomState`, `preloadPlantUmlEngine`, `wrapPlantUmlSource`.

---

## 2. Estrategia de renderizado

1. **Carga del motor** (`engine-loader.ts`): imports dinámicos cacheados en singletons. `viz-global.js` **debe** cargarse antes que `plantuml.js`. `preloadPlantUmlEngine()` dispara ambas sin bloquear.
2. **Cola de render** (`render-queue.ts`): todos los renders pasan por una cadena de promesas (`queueTail`) → se ejecutan uno a uno (evita reentrancia del motor). Cada tarea tiene timeout de 20 s (`RENDER_TIMEOUT_MS`) y retorna `RenderResult` (`{ok:true,svg} | {ok:false,error}`). Caché por `source` (`Map`, límite 50); los fallos se purgan.
3. **Render → UI** (`useRender.ts`): ante cambio de `source`, resetea y pasa a `rendering`, hace `await renderPlantUml(source)`; un flag `cancelledRef` evita `setState` tras desmontaje/cambio. Devuelve `{ svg, state, error }` con `RenderState = idle | loading-engine | rendering | done | error`.
4. **Pan/zoom** (`usePanZoom.ts`): transformación CSS `translate(tx,ty) scale(zoom)` con `transformOrigin: 0 0`; zoom centrado en el cursor con clamp (`ZOOM_MIN=0.25`, `ZOOM_MAX=4`, paso `×1.25`); rueda con `{ passive: false }`, drag con handlers de mouse; `zoomIn/zoomOut/zoomReset`; `viewportRef`. Soporta modo controlado (`control: 'controlled'`) o interno.
5. **Envoltura de fuente** (`wrap-plantuml.ts`): quita `@startuml`/`@enduml` existentes y re-envuelve contenido, garantizando los marcadores correctos.

---

## 3. Componente `PlantUmlViewer`

`forwardRef<HTMLDivElement, PlantUmlViewerProps>`.
- Compone `useRender` + `usePanZoom`.
- Barra de controles: zoom ±, reset (%), maximizar/restaurar.
- Estados: `loading-engine`/`rendering` (spinner), `error` (con `fallbackContent`), `done`.
- Aplica `translate + scale` e inyecta el SVG con `dangerouslySetInnerHTML`.
- Solo habilita pan/zoom cuando `state === 'done'`.

---

## 4. Consumidores

- `pages/project/ModelingPage` (diagrama por característica).
- `pages/project/ConsistencyPage` precarga el motor con `preloadPlantUmlEngine()` en el montaje y usa `wrapPlantUmlSource` en `GateReviewCard`.

---

## 5. Dónde cambiar qué

```
├── Ajustar límites/velocidad de zoom     → lib/zoom.ts
├── Cambiar timeout o caché de render      → lib/render-queue.ts
├── Orden/carga del motor PlantUML         → lib/engine-loader.ts
├── Normalización de fragmentos @startuml  → lib/wrap-plantuml.ts
├── Interacción pan/zoom                   → model/usePanZoom.ts
└── UI del visor (controles/estados)       → ui/plantuml-viewer.tsx
```

---

## 6. Invariantes

1. **Todo render pasa por la cola** (`renderPlantUml`); nunca invocar el motor directamente.
2. **`viz-global.js` antes que `plantuml.js`.**
3. **`useRender` debe cancelar setState** en desmontaje/cambio de fuente.
4. **Sin `api/`** en la feature.
5. **`index.ts` como API pública**; `preloadPlantUmlEngine` y `wrapPlantUmlSource` son la superficie para páginas.

---

## 7. Verificación

```bash
bun run typecheck
bun run test:coverage   # cubre lib/render-queue, lib/wrap-plantuml y model/useRender
```
