# Capa `features/` — Acciones del usuario

> **Destinatario:** Agentes de IA que trabajen en `frontend/src/features/`.
> **Ámbito:** `src/features/` — acciones que el usuario puede realizar. Son **agnósticas a la API**: reciben datos por props o store.
> **Regla:** las features importan **solo** de `entities` y `shared`. **Prohibido `api/`**: no hacen HTTP directo.
> **Nivel superior:** [../AGENTS.md](../AGENTS.md).

---

## 1. Estructura y segmentos

```
features/<feature>/
├── ui/       # Componentes de acción (formularios, paneles, botones, editores)
├── model/    # Hooks y estado local de la feature
├── lib/      # Utilidades internas de la feature
└── index.ts  # API pública (barrel)
```

Segmentos permitidos: **`ui/`**, **`model/`**, **`lib/`**. **No** existe `api/`.

---

## 2. Catálogo de features

| Feature | Archivos clave | Exports principales | Propósito |
|---|---|---|---|
| `markdown-editor` | `ui/markdown-editor.tsx`, `editor-content.tsx`, `save-indicator.tsx`, `toc-sidebar.tsx`, `markdown-editor-skeleton.tsx`; `model/use-headings.ts`, `heading.ts`; `lib/extract-headings.ts` | `MarkdownEditor`, `MarkdownEditorHandle`, `MarkdownEditorSkeleton`, `SaveStatus` | Editor Markdown con TOC, autosave e indicador de guardado. |
| `chatbot` | `ui/*`, `model/useChatStream.ts` | `Chatbot`, `ChatStreamPanel`, `PanelAsistenteRequisito`, `ChatbotMessage`, `useChatStream`, `SendChatStreamBody` | Chat con streaming SSE y sesiones. **Ver [`chatbot/AGENTS.md`](./chatbot/AGENTS.md).** |
| `app-state` | `model/app.store.ts`, `lib/clearAllStores.ts`, `lib/useUnsavedChanges.ts` | `useAppStore`, `clearAppStore`, `useUnsavedChanges`, `clearAllStores` | Estado de UI global: inicialización, cambios sin guardar, editor maximizado, limpieza de stores. |
| `github-sync` | `model/useProjectGithubRepo.ts`, `ui/GitHubSyncBanner.tsx` | `useProjectGithubRepo`, `ProjectGithubViewState`, `GitHubSyncBanner` | Estado de vinculación/sincronización del repo GitHub del proyecto. |
| `ai-config` | `ui/AiConfigForm.tsx`, `ui/AiProviderBadge.tsx` | `AiConfigForm`, `AiProviderBadge` | Formulario BYOK de proveedor/modelo IA y badge del proveedor. |
| `aside-characteristic` | `ui/AsideCharacteristic.tsx` | `AsideCharacteristic` | Sidebar colapsable de características (selección, iconos/advertencias, borrado). |
| `initialize` | `model/init.service.ts` | `initializeProject` | Hidrata los stores de entidad al abrir un proyecto (discovery, características, requisitos). |

**Importación:** no existe `features/index.ts` (barril de capa). Cada consumidor importa del slice: `@/features/<feature>` (p. ej. `@/features/chatbot`, `@/features/aside-characteristic`).

---

## 3. Detalle de features no triviales

### `app-state`
- `useAppStore` (`model/app.store.ts`): `initialized`, `hasUnsavedChanges`, `pendingNavigationPath`, `isEditorMaximized`; acciones `resetProjectState`, `resetStateBeforeChangeProject`, `initializeProject`.
- `resetStateBeforeChangeProject` limpia stores de entidad perdiendo solo el proyecto actual (conserva la lista).
- `clearAllStores()` (`lib/clearAllStores.ts`): limpieza total al cerrar sesión; invocada desde `app/session-expired-listener.tsx`.
- `useUnsavedChanges()` (`lib/useUnsavedChanges.ts`): autosave y guardas de navegación.
- `resetProjectState` / `resetStateBeforeChangeProject` son el punto canónico para añadir la limpieza de nuevos stores.

### `initialize`
- `initializeProject(projectId)`: carga descubrimiento (404 es normal), características y requisitos por característica. Escribe directamente en los stores de entidad.

### `github-sync`
- `useProjectGithubRepo` expone `ProjectGithubViewState` con estados `loading | not-linked | no-code | create | syncing | failed | synced`, consumido por `GestionRepositorioGitHub` y la página de implementación.

### `ai-config`
- `AiConfigForm` se embebe en Onboarding y Profile; `AiProviderBadge` muestra el proveedor activo.

### `aside-characteristic`
- Lista características (`display_id`/título) con selección, icono o `WarningIcon` según `warningByFeature`, y borrado en hover.
- Soporta expansión controlada (`isExpanded`/`onToggleExpand`) o no controlada (`defaultExpanded`).

---

## 4. Patrones

### Feature que consume entidades + streaming
```ts
// features/chatbot/model/useChatStream.ts
const { start, stop, phase, error } = useSseStream();
const send = (url, body) => start(url, { body, onEvent });
```
- El transporte SSE vive en `shared/lib/useSseStream.ts`; la feature mapea eventos a su dominio.

### Formulario
- `react-hook-form` + esquemas Zod (definidos en `entities` o en `pages/*/model`).

### Presentación vs controlador
- Los `ui/` puros no hacen red (ej. `Chatbot.tsx`); los contenedores (`ChatStreamPanel.tsx`) unen hook de red + UI.

---

## 5. Dónde cambiar qué

```
├── Comportamiento del editor Markdown     → features/markdown-editor/{ui,model,lib}
├── Streaming de chat / sesiones           → features/chatbot/ (ver su AGENTS.md)
├── Limpieza de stores / cambios sin guardar → features/app-state/
├── Estado de sync GitHub                   → features/github-sync/
├── Formulario de IA (BYOK)                 → features/ai-config/
├── Sidebar de características              → features/aside-characteristic/
└── Hidratación al abrir proyecto           → features/initialize/
```

---

## 6. Invariantes

1. **Sin `api/`**: nada de `fetch`/`apiClient` dentro de una feature.
2. **Sin importar** `widgets` ni `pages`.
3. **Reutilizar entidades:** leer datos y estado desde `@/entities/*`; no duplicar tipos.
4. **`index.ts` del slice como API pública**; importar de `@/features/<feature>` y añadir exports cuando se agregan componentes/hooks públicos. No hay barril de capa.
5. **Toda feature con `ui/` de red debe separar** presentación de controlador.

---

## 7. Verificación

```bash
bun run typecheck
bun run test:coverage   # tests de features/{model,lib} SÍ se miden; ui/ se excluye
```
