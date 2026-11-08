# Arquitectura Frontend de KOSMO (FSD)

> **Destinatario:** Agentes de IA y desarrolladores que trabajen en `frontend/src/`.
> **Ámbito:** Todas las capas de `frontend/src/` (`shared`, `entities`, `features`, `widgets`, `pages`).
> **Fuente de Verdad:** El código de cada slice y su `index.ts` (API pública). Reglas canónicas en [../README.md](../README.md).
> **Nivel superior:** [../AGENTS.md](../AGENTS.md) — stack, scripts, rutas `app/` y configuración.

---

## 1. Modelo FSD en una imagen

```
Layer  →  Slice  →  Segment
```

- **Layer** — nivel arquitectónico: `shared | entities | features | widgets | pages`.
- **Slice** — unidad de dominio/funcionalidad dentro de la capa (carpeta de primer nivel).
- **Segment** — responsabilidad técnica dentro del slice: `ui/ | model/ | api/ | lib/ | hooks/ | types/`.

**Dirección de importación (solo hacia abajo):**

```
pages → widgets → features → entities → shared
```

| Capa       | Puede importar de                           |
| ---------- | ------------------------------------------- |
| `pages`    | `widgets`, `features`, `entities`, `shared` |
| `widgets`  | `features`, `entities`, `shared`            |
| `features` | `entities`, `shared`                        |
| `entities` | `shared`                                    |
| `shared`   | — (nada del proyecto)                       |

> Fuga conocida y permitida: `app/` (fuera de `src/`) puede importar de cualquier capa; es el único composition root.

---

## 2. Árbol de `src/` (mapa de navegación)

```
src/
├── shared/
│   ├── api/        # apiClient, authApi, errores (ApiError), headers, config
│   ├── lib/        # sse, useSseStream, pkce, zod, session-events, normalize-repo-name
│   ├── model/      # auth.store (Zustand+persist), chat-message (tipos/helpers)
│   └── ui/         # Loading, ModalConfirm, AuthGuard, MarkdownText, toast/, icons/
│
├── entities/       # model/ (tipos + store Zustand) + api/ (Llamadas HTTP). SIN ui/
│   ├── ai-config/        # Config BYOK de proveedores IA
│   ├── characteristic/   # Características (C01, C02, ...)
│   ├── chat/             # Sesiones de chat (store por key)
│   ├── consistency/      # Estado de consistencia (gate-store + selectors)
│   ├── deploy/           # Estado de despliegue (useDeployStatus)
│   ├── discovery/        # Documento de Descubrimiento
│   ├── implementation/   # Codegen: estado, file-tree, eventos SSE
│   ├── integration/      # OAuth (GitHub, Railway)
│   ├── project/          # Proyectos (store persist) + GitHub sync
│   ├── requirements/     # Requisitos EARS + chat history
│   └── user/             # Re-export de auth (shared) + getUser
│
├── features/       # ui/ + model/ + lib/. SIN api/ (no hacen HTTP directo)
│   ├── ai-config/        # AiConfigForm, AiProviderBadge
│   ├── app-state/        # app.store, useUnsavedChanges, clearAllStores
│   ├── aside-characteristic/ # Sidebar de características
│   ├── chatbot/          # Chat SSE + sesiones (Chatbot, ChatStreamPanel, ...)
│   ├── github-sync/      # useProjectGithubRepo, GitHubSyncBanner
│   ├── initialize/       # initializeProject (hidratación de stores)
│   └── markdown-editor/  # Editor + TOC + autosave
│
├── widgets/        # ui/ + model/ + lib/ + types/
│   ├── gestion-deploy/            # (vacío / placeholder)
│   ├── gestion-repositorio-github/# Tarjeta de repo GitHub
│   ├── main-navbar/               # Layout autenticado (sidebar + nav + usuario)
│   ├── root-navbar/               # Navbar público (landing)
│   └── wizard-navegacion/         # Barra de pasos del proyecto SDD + consistencia
│
└── pages/          # ui/ + model/ + hooks/
    ├── HomePage/          # Listado de proyectos → /proyecto
    ├── Onboarding/        # Wizard de activación (API key + OAuth)
    ├── ProfilePage/       # Perfil (Cuenta + IA)
    ├── RootPage/          # Landing + login/registro → /
    └── project/           # Wizard SDD
        ├── CharacteristicsPage/  # + CreateCharacteristic (subpágina)
        ├── ConsistencyPage/      # Revisión de consistencia
        ├── CreateProjectPage/    # Alta de proyecto
        ├── DiscoveryPage/        # Documento de descubrimiento
        ├── ImplementationPage/   # Codegen + resumen + deploy
        └── RequirementsPage/     # Requisitos EARS
```

> Cada capa tiene su propio `AGENTS.md` con el detalle de slices. Los slices complejos (`pages/project`, `features/chatbot`, `widgets/main-navbar`) tienen `AGENTS.md` propio.

---

## 3. Responsabilidad y segmentos por capa

### `shared/` — transversal sin negocio
- `ui/` componentes atómicos y accesibles; `lib/` utilidades puras y hooks de SSE/PKCE; `api/` cliente HTTP, auth y errores; `model/` store de auth y primitivas de chat.
- **No** importa de ninguna capa del proyecto.

### `entities/` — forma de los datos y su obtención
- Segmentos permitidos: **`model/`** (tipos TypeScript + store Zustand) y **`api/`** (endpoints).
- **Prohibido `ui/`**: las entidades no exponen componentes.
- Cada entidad expone su API pública por `index.ts`.

### `features/` — acciones del usuario
- Segmentos: **`ui/`** (formularios/botones/paneles), **`model/`** (hooks/estado local), **`lib/`** (utilidades internas).
- **Prohibido `api/`**: no hacen HTTP; reciben datos por props o store y usan entidades.
- **Importación:** `@/features/<feature>` (el `index.ts` del slice). No existe barril de capa `@/features`.

### `widgets/` — bloques UI complejos
- Segmentos: `ui/`, `model/`, `lib/`, `types/`. Componen varias entidades y features en una unidad cohesiva (navbars, wizards, paneles).
- **Importación:** `@/widgets/<widget>` (el `index.ts` del slice). No existe barril de capa `@/widgets`.

### `pages/` — composición por ruta
- Segmentos solo si se necesitan: `ui/` (layout propio), `model/`/`hooks/` (lógica de la página). No crear carpetas vacías.

---

## 4. Patrones de código recurrentes

### Store de entidad (Zustand + persist)
```ts
export const useProjectStore = create<ProjectStore>()(
  persist((set, get) => ({ /* estado + acciones async que llaman a api/ */ }),
    { name: 'kosmo-project-store', partialize: (s) => ({ currentProject: s.currentProject }) })
);
// Siempre exportar un clear<Entity>Store() para limpieza global.
```
- `partialize` limita lo persistido; `clearXStore()` limpia storage + estado.
- La limpieza global se orquesta en `features/app-state/lib/clearAllStores.ts`.

### API de entidad con mocks
```ts
export const getProjects = (): Promise<Project[]> =>
  USE_MOCKS ? mockGetProjects() : realGetProjects();
```
- Cada `entities/<x>/api/api.ts` define implementaciones `mock*` y `real*` y conmuta por `USE_MOCKS`.

### Página con hooks locales
- Hooks en `pages/<X>/hooks/` encapsulan fetch/filtros/estado (`useCharacteristicsPage`, `useCreateCharacteristic`).
- Formularios con `react-hook-form` + esquemas Zod en `model/types.ts`.

### Streaming SSE
- `shared/lib/useSseStream.ts` (transporte) + `features/chatbot/model/useChatStream.ts` (mapeo de eventos de chat).
- Eventos típicos: `chunk`, `message`, `error`.

---

## 5. Convenciones

### Naming
- **Componentes** → `PascalCase.tsx` (`UserCard.tsx`).
- **Utilitarios / hooks** → `kebab-case.ts` (`use-local-storage.ts`).
- **Variables / funciones** → `camelCase`; **constantes** → `UPPER_SNAKE_CASE`.

### TypeScript
- Tipado estricto; evitar `any` (usar `unknown` o genéricos).
- `interface` para objetos/props; `type` para uniones y tipos complejos.

### Componentes
- Arrow functions con exportación nombrada (excepto `page.tsx`).
- Desestructuración de props y early returns.
- Comentarios explican el **por qué**, no el qué. **No** añadir comentarios triviales.

### Next.js (App Router)
- `'use client'` solo cuando sea estrictamente necesario.
- Preferir Server Components para fetching.
- La ruta vive en `app/`; la lógica en `src/pages/`.

### Estilos
- Tailwind CSS; sin inline styles. Usar tokens de `app/globals.css`.

### Estado (en orden de preferencia)
1. **URL** — estado compartible entre vistas.
2. **`useState`** — estado local del componente.
3. **Zustand** — estado global (último recurso).

---

## 6. Dónde cambiar qué (guía operativa)

```
├── Bug de red / refresh de tokens / errores HTTP
│   └── src/shared/api/client.ts · errors.ts · headers.ts
│
├── Agregar/editar una llamada a la API de una entidad
│   └── src/entities/<entidad>/api/api.ts  (+ tipos en model/types.ts)
│
├── Cambiar el estado global de una entidad
│   └── src/entities/<entidad>/model/store.ts  (+ limpieza en clearAllStores.ts)
│
├── Nueva acción de usuario (formulario, panel, botón)
│   └── src/features/<feature>/ui  (+ model/ para hooks)
│
├── Nueva composición de navbar / wizard / panel
│   └── src/widgets/<widget>/ui  (+ model/)
│
├── Nueva ruta o página
│   ├── src/pages/<Pagina>/ui  (componente)
│   └── app/.../page.tsx       (reexporta + metadata)
│
├── Layout autenticado / público
│   └── app/(app)/layout.tsx · app/(root)/layout.tsx
│
├── Tokens de color / tema
│   └── app/globals.css (@theme)
│
└── Nueva variable de entorno
    └── .env.example + src/shared/api/config.ts
```

---

## 7. Invariantes (no romper)

1. **Dirección FSD:** `shared` nunca importa capas superiores; `entities`/`features` no se importan entre sí fuera de las reglas.
2. **`entities` sin `ui/` y `features` sin `api/`:** respetar los segmentos permitidos por capa.
3. **API pública vía `index.ts` del slice:** los consumidores importan de `@/entities/<x>`, `@/features/<x>` o `@/widgets/<x>`, nunca de archivos internos (salvo dentro del mismo slice). `features` y `widgets` **no** tienen barril de capa.
4. **Sesión expirada:** `shared` emite (`emitSessionExpired`) y el consumidor limpia (`app/session-expired-listener.tsx` → `clearAllStores`). No invertir esa dependencia.
5. **Un único `apiClient`:** todas las llamadas HTTP pasan por `shared/api/client.ts` (maneja auth, refresh y errores).
6. **Tokens de diseño:** nunca hardcodear colores/hex; usar `globals.css`.
7. **`app/` sin lógica de negocio.**

---

## 8. Verificación antes de terminar

```bash
bun run lint
bun run typecheck
bun run test:coverage   # umbrales en vitest.config.ts
```

Si el cambio toca navegación o rutas, validar además:

```bash
bun run build
```
