# `pages/project/` — Wizard SDD (fases del proyecto)

> **Destinatario:** Agentes de IA que trabajen en `frontend/src/pages/project/`.
> **Ámbito:** las 6 páginas del pipeline Spec-Driven Development y la revisión de consistencia.
> **Nivel superior:** [`../AGENTS.md`](../AGENTS.md) (capa `pages`).
> **Referencia de dominio:** [`../../../../backend/AGENTS.md`](../../../../backend/AGENTS.md) (pipeline y validaciones por fase).

---

## 1. Pipeline de fases

```
Descubrimiento → Características → Requisitos → Implementación
   (negocio)       (usuario)        (software)   (código)
                          ↕ consistencia (cascada hacia la derecha)
```

Cada fase lee datos de `entities/*` e hidrata sus stores mediante `initializeProject` (feature `initialize`). La navegación entre fases se hace con `WizardNavegacion` (widget).

---

## 2. Mapa de subpáginas

| Slice | Ruta | UI | Stores de entidad | Features/widgets clave |
|---|---|---|---|---|
| `DiscoveryPage` | `/proyecto/descubrimiento` | `ui/DiscoveryPage.tsx` | `useDiscoveryStore`, `useProjectStore`, `useAppStore` | `MarkdownEditor`, `ChatStreamPanel`, `useUnsavedChanges` |
| `CharacteristicsPage` | `/proyecto/caracteristicas` + `/nueva` | `ui/CharacteristicsPage.tsx`, `CreateCharacteristicPage.tsx`, `CardCharacterist.tsx`, `CharacteristicModal.tsx`, `Search.tsx` | `useCharacteristicStore`, `useDiscoveryStore`, `useProjectStore` | `ChatStreamPanel`, `subscribeImplementationEvents` |
| `RequirementsPage` | `/proyecto/requisitos` | `ui/RequirementsPage.tsx` | `useRequirementsStore`, `useCharacteristicStore`, `useProjectStore`, `useAppStore` | `MarkdownEditor`, `PanelAsistenteRequisito`, `AsideCharacteristic`, `useUnsavedChanges` |
| `ImplementationPage` | `/proyecto/codigo` + `/codigo/resumen` | `ui/ImplementationPage.tsx`, `ImplementationSummaryPage.tsx`, `DeployPreconditionPanel.tsx`, `DeployResultPanel.tsx` | `useImplementationStore`, `useCharacteristicStore`, `useProjectStore`, `useDeployStatus` | `useProjectGithubRepo`, `GestionRepositorioGitHub`, `AsideCharacteristic` |
| `ConsistencyPage` | `/proyecto/[fase]/consistencia` | `ui/ConsistencyPage.tsx`, `GateReviewCard.tsx` | `useConsistencyGateStore` (+ refresca stores de artefacto) | `MarkdownText` |
| `CreateProjectPage` | `/crear-proyecto` | `ui/CreateProjectPage.tsx`, `CreateProjectForm.tsx`; `model/useIntegrationGate.ts` | `useProjectStore` | `useIntegrationGate` |

`Index.ts` de cada slice reexporta sus componentes (`CharacteristicsPage` exporta además `CreateCharacteristic`).

---

## 3. Detalle por fase

### Descubrimiento (`DiscoveryPage`)
- Documento Markdown editable con autosave y asistente IA.
- Estado local: `isGeneratingDiscovery`, `isChatbotOpen`, `loadingMore`, `saveStatus`, `markdown`, `savedContent`, `editorRef`, `isSavingRef`.
- Chat IA por SSE en `/api/v1/projects/{id}/discovery/chat/stream` (phase `discovery`).
- Navegación a `caracteristicas` con `ModalConfirm` si hay cambios sin guardar.

### Características (`CharacteristicsPage`)
- Listado/CRUD de funcionalidades; alta en subpágina `CreateCharacteristic`.
- Hooks: `useCharacteristicsPage` (fetch + filtro por título; 404 → lista vacía), `useCharacteristicModal` (`getSuggestCharacteristics`), `useCreateCharacteristic` (react-hook-form + Zod; maneja `is_saved`, `warnings`, `inconsistency_reason`).
- Modelo Zod en `model/types.ts` (`characteristicSchema`, `CharacteristicFormData`, `FieldError`).
- Refinamiento por IA con `ChatStreamPanel` (`/api/v1/features/{id}/chat/stream`).
- Empty states: sin descubrimiento → link a `/proyecto/descubrimiento`; con descubrimiento → botón generar.
- `subscribeImplementationEvents` para borrado de código en background.

### Requisitos (`RequirementsPage`)
- Criterios EARS por funcionalidad (Markdown editable, autosave).
- `PanelAsistenteRequisito` (`useChatStream`) sobre `/api/v1/features/{id}/requirements/chat/stream`; refetch si `modification.applied`.

### Implementación (`ImplementationPage`)
- Genera/regenera la implementación por funcionalidad; `useProjectGithubRepo` decide el CTA según GitHub (`syncing | failed | not-linked`).
- `ImplementationSummaryPage` (`ui/ImplementationSummaryPage.tsx`): métricas/tecnologías/next steps; `useDeployStatus` + `useRailwayOAuth`; rehidrata con `loadImplementation`; refresh en `focus`/`visibilitychange`.
- `precondition` = `github-not-linked | github-not-synced | railway-not-linked | ready` → renderiza `DeployPreconditionPanel` o `DeployResultPanel`.
- `DeployResultPanel`: estado Railway (`ready/building/pending/failed`), copiar URL, reintentar, `deleteDeployment` con `ModalConfirm`.

### Consistencia (`ConsistencyPage`)
- `useParams<{fase}>` mapea `ROUTE_TO_TARGET` a fases `features|requirements|implementation`.
- `useConsistencyGateStore`: `status, loadStatus, loadReview, applyEvaluation, discardEvaluation, bulkResolve, loadActivity`.
- `refreshArtifactStores` recarga stores de characteristic/requirements/implementation según `artifact_type`.
- `GateReviewCard` muestra diff textual (pestañas Anterior/Propuesto) con Aplicar/Descartar.
- Rutas de revisión canónicas: `entities/consistency/model/selectors.ts` → `CONSISTENCY_REVIEW_ROUTES`.

### Crear proyecto (`CreateProjectPage`)
- `useIntegrationGate` exige API key + GitHub + Railway conectados; si no, `router.replace('/onboarding')`.
- `CreateProjectForm` (react-hook-form + Zod: nombre 3-25 letras, descripción 50-1000, sin emojis; `repo_name` autoderivado `kosmo-<slug>`).
- Al enviar: `createProject` → `addProject`/`setGithubSyncing`/`initializeProject` → `pushProjectToGitHub` en background → `/proyecto/descubrimiento`.

---

## 4. Patrones comunes

- **Autosave:** `useUnsavedChanges` + `saveStatus` (MarkdownEditor) en Discovery/Requirements; `ModalConfirm` al navegar con cambios.
- **Selección de característica:** `useCharacteristicStore.selectedId` + `AsideCharacteristic`; `pendingCharSwitch` gestiona cambios sin guardar.
- **Streaming IA:** `ChatStreamPanel` (Discovery/Characteristics) y `PanelAsistenteRequisito` (Requirements) sobre `features/chatbot`.

---

## 5. Dónde cambiar qué

```
├── Prompt/flujo de IA de una fase    → su ChatStreamPanel/PanelAsistenteRequisito (features/chatbot) + store entidad
├── Validación de formulario           → pages/project/<Fase>/model/types.ts (Zod)
├── Carga/estado de una fase           → pages/project/<Fase>/hooks/ y store de entidad
├── Precondiciones de deploy           → pages/project/ImplementationPage/ui/DeployPreconditionPanel.tsx
├── Reglas de consistencia/rutas       → entities/consistency/model/selectors.ts
└── Gate de creación de proyecto       → pages/project/CreateProjectPage/model/useIntegrationGate.ts
```

---

## 6. Invariantes

1. **El proyecto activo** (`useProjectStore.currentProject`) es prerrequisito; si falta, redirigir a `/proyecto`.
2. **No persistir datos entre proyectos:** las fases recargan su fuente de verdad al entrar.
3. **Consistencia en cascada unidireccional:** propagar impactos solo hacia fases downstream.
4. **Integraciones obligatorias** antes de operaciones (API key IA, GitHub, Railway).
5. **Reutilizar** `features/*` y `widgets/*`; no duplicar editores, viewers ni chat.

---

## 7. Verificación

```bash
bun run typecheck
bun run build
bun run test:coverage
```
