# Capa `entities/` — Dominio y acceso a datos

> **Destinatario:** Agentes de IA que trabajen en `frontend/src/entities/`.
> **Ámbito:** `src/entities/` — representa los tipos de datos del dominio, su forma y cómo se obtienen.
> **Regla:** las entidades importan **solo** de `shared`. **Prohibido `ui/`**: no exponen componentes visuales.
> **Nivel superior:** [../AGENTS.md](../AGENTS.md).

---

## 1. Estructura y segmentos

```
entities/<entidad>/
├── model/
│   ├── types.ts     # Tipos TypeScript del dominio
│   └── store.ts     # Store Zustand (+ persist) con acciones async
├── api/
│   └── api.ts       # Llamadas HTTP (conmuta mock/real por USE_MOCKS)
└── index.ts         # API pública del slice (barrel)
```

Segmentos permitidos: **`model/`** y **`api/`**. Un slice puede además incluir utilidades de modelo (ej. `chat-utils.ts`, `selectors.ts`, `file-tree.ts`).

> **Importación:** los consumidores importan desde `@/entities/<entidad>` (el `index.ts`), nunca de archivos internos.

---

## 2. Catálogo de entidades

| Entidad          | `model/`                                                                                                                                                                                  | `api/`                                                                                                                                                           | Endpoints principales                                          |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| `project`        | `types.ts` (`Project`, `GitHubSyncStatus`, `ProjectGitHubStatus`, `PushGitHubRequest`); `store.ts` (`useProjectStore`, `clearProjectStore`, `clearProjectStoreExceptProjects`)            | `getProjects`, `getProject`, `createProject`, `deleteProject`, `getProjectGitHubStatus`, `pushProjectToGitHub`                                                   | `/api/v1/projects`, `/projects/{id}/github`, `/github/push`    |
| `characteristic` | `types.ts` (`CharacteristicResponse`, `SuggestCharacteristic`); `store.ts` (`useCharacteristicStore`, `clearCharacteristicStore`)                                                         | `getCharacteristics`, `generateCharacteristics`, `getSuggestCharacteristics`, `addCharacteristic`, `deleteFeature`                                               | `/projects/{id}/features`                                      |
| `discovery`      | `types.ts` (`DiscoveryResponse`); `store.ts` (`useDiscoveryStore`, `clearDiscoveryStore`)                                                                                                 | `getDiscovery`, `saveDiscovery`, `generateDiscovery`, `sendChatMessage`                                                                                          | `/projects/{id}/discovery`                                     |
| `requirements`   | `types.ts` (`RequirementsResponse`); `store.ts` (`useRequirementsStore`, `clearRequirementsStore`)                                                                                        | `getRequirements`, `saveRequirements`, `generateRequirements`, `deleteRequirements`, `getRequirementChatHistory`, `sendRequirementChatMessage`                   | `/features/{id}/requirements`                                  |
| `modeling`       | `types.ts` (`ModelingResponse`); `store.ts` (`useModelingStore`, `clearModelingStore`)                                                                                                    | `generatePlantUmlDiagram`, `getDiagram`, `deleteDiagram`                                                                                                         | `/features/{id}/model`                                         |
| `consistency`    | `gate-store.ts` (`useConsistencyGateStore`); `selectors.ts` (`CONSISTENCY_PHASE_ORDER`, `CONSISTENCY_REVIEW_ROUTES`, `sumPhaseStatus`, `firstPhaseToReview`); `types.ts`                  | `getConsistencyStatus`, `getConsistencyReview`, `applyConsistencyEvaluation`, `discardConsistencyEvaluation`, `bulkResolveConsistency`, `getConsistencyActivity` | `/projects/{id}/consistency`                                   |
| `implementation` | `types.ts`; `file-tree.ts` (`buildFileTree`, `FileTreeNode`); `store.ts` (`useImplementationStore`, `clearImplementationStore`)                                                           | `generateImplementation`, `fetchImplementation`, `fetchImplementationFile`, `subscribeImplementationEvents`                                                      | `/features/{id}/implementation`, `/stream` (SSE)               |
| `chat`           | `types.ts`; `chat-utils.ts` (`appendMessage`, `createUserMessage`, `createAssistantError`); `sessions-store.ts` (`useChatSessionsStore`, `useChatSessions`, `sessionKey`)                 | `listChatSessions`, `createChatSession`, `deleteChatSession`                                                                                                     | `/projects/{id}/chat/sessions`                                 |
| `integration`    | `types.ts` (`IntegrationProvider`, `IntegrationStatus`, `ConnectOAuthRequest`); `useOAuthIntegration.ts`; `useOAuthProviders.ts` (`useGithubOAuth`, `useRailwayOAuth`); `oauth-config.ts` | `connectIntegration`, `disconnectIntegration`, `getIntegrationStatus`                                                                                            | `/integrations`                                                |
| `ai-config`      | `types.ts` (`AIProvider`, `AIModelTier`, `AIConfigView`, ...; `DEFAULT_AI_PROVIDER`, `maskApiKey`); `store.ts` (`useAiConfigStore`)                                                       | `aiConfigApi`                                                                                                                                                    | `/user/ai-config`                                              |
| `deploy`         | `types.ts` (`DeployStatus`, `DeployRailwayRequest`, `PreconditionState`, `ProjectDeployStatusResponse`); `use-deploy-status.ts` (`useDeployStatus`)                                       | `getDeployStatus`, `startDeployRailway`, `deleteDeployment`                                                                                                      | `/projects/{id}/deployments`                                   |
| `user`           | —                                                                                                                                                                                         | `user-api.ts` (`getUser`)                                                                                                                                        | Re-exporta auth de `shared` (`useAuthStore`, `authApi`, tipos) |

> **Nota `consistency`:** su lógica de estado es un *gate-store* (no `store.ts`); incluye `selectors.ts` con el orden de fases y las rutas de revisión (`/proyecto/{caracteristicas|requisitos|modelo|codigo}/consistencia`).

---

## 3. Patrón de un slice de entidad

### `model/types.ts`
```ts
export interface Project { id: string; name: string; /* ... */ }
```
- `interface` para objetos/props; `type` para uniones.

### `model/store.ts` (Zustand + persist)
```ts
export const useProjectStore = create<ProjectStore>()(
  persist(
    (set, get) => ({
      projects: [],
      getProjects: async () => { const d = await getProjects(); set({ projects: d }); return d; },
      // ...
    }),
    {
      name: 'kosmo-project-store',
      partialize: (s) => ({ currentProject: s.currentProject, isProyectosOpen: s.isProyectosOpen }),
    },
  ),
);

export const clearProjectStore = () => {
  useProjectStore.persist.clearStorage();
  useProjectStore.setState({ projects: [], currentProject: null /* ... */ });
};
```
Convenciones:
- Nombre de persistencia: `kosmo-<entidad>-store`.
- `partialize` limita lo que se persiste (solo lo necesario).
- Algunas usan `version` + `migrate` (ej. `characteristic`).
- **Cada store exporta `clear<Entidad>Store()`.** La limpieza global se orquesta en `features/app-state/lib/clearAllStores.ts`.
- No persisten datos volátiles entre proyectos: se recargan al entrar a la fase.

### `api/api.ts` (mock/real)
```ts
export const getProjects = (): Promise<Project[]> =>
  USE_MOCKS ? mockGetProjects() : realGetProjects();
```
- Definir `mock*` y `real*`; conmutar por `USE_MOCKS`.
- Todas las llamadas usan `apiClient` de `@/shared/api`.

---

## 4. Relaciones relevantes

- `project` es la entidad raíz: el proyecto activo (`currentProject`) se propaga a las fases.
- `characteristic` es la unidad del wizard: `requirements`, `modeling` e `implementation` se indexan por `featureId`.
- `chat` + `requirements`/`characteristic` mantienen historiales de chat por feature/sesión (con cursor `loadOlderChatHistory`).
- `consistency` coordina impactos entre fases (selectores de orden/rutas).
- `integration` + `ai-config` + `deploy` cubren las integraciones externas (OAuth, BYOK IA, Railway/GitHub).

---

## 5. Dónde cambiar qué

```
├── Nuevo campo/tipo de dominio        → model/types.ts
├── Nuevo endpoint de la entidad       → api/api.ts (+ reexport en index.ts)
├── Nuevo estado/acción global         → model/store.ts
├── Limpieza al cerrar sesión/cambiar  → clear<Entidad>Store()
│   └── registrar en features/app-state/lib/clearAllStores.ts
└── Rutas/orden de consistencia        → consistency/model/selectors.ts
```

---

## 6. Invariantes

1. **Sin `ui/`** en entidades; sin componentes React.
2. **Sin importar** `features`, `widgets` ni `pages`.
3. **`index.ts` es la API pública;** mantener exports coherentes con el estado real del slice.
4. **Todo store persistido debe tener su `clear*`** y estar en `clearAllStores`.
5. **Mock y real siempre en paralelo** en `api/api.ts`.

---

## 7. Verificación

```bash
bun run typecheck
bun run test:coverage   # los tests de <entidad>/{api,model} SÍ se miden
```
