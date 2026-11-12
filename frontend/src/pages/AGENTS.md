# Capa `pages/` — Composición por ruta

> **Destinatario:** Agentes de IA que trabajen en `frontend/src/pages/`.
> **Ámbito:** `src/pages/` — cada slice corresponde a una página; compone widgets, features y entidades para construir la vista.
> **Regla:** las páginas pueden importar de `widgets`, `features`, `entities` y `shared`.
> **Nivel superior:** [../AGENTS.md](../AGENTS.md).

---

## 1. Estructura y segmentos

```
pages/<Pagina>/
├── ui/       # Componentes y layout propios de la página
├── model/    # Lógica/estado específico (types, etc.)
├── hooks/    # Hooks de la página
└── index.ts  # API pública (reexporta el/los componentes de página)
```

Segmentos permitidos (solo si se necesitan): **`ui/`**, **`model/`**, **`hooks/`**. No crear carpetas vacías.

> **Ruta vs página:** el archivo de ruta (`page.tsx`) vive en `app/` y **solo** reexporta el componente de página + `metadata`. Toda la lógica va aquí en `src/pages/`.

---

## 2. Catálogo de páginas y su ruta

| Página (`src/pages`) | Ruta (`app/`) | URL | Componente(s) |
|---|---|---|---|
| `RootPage` | `app/page.tsx` | `/` | `RootPage` (landing + `AuthModal`) |
| `HomePage` | `app/(app)/proyecto/page.tsx` | `/proyecto` | `HomePage` (listado tarjeta/lista) |
| `project/CreateProjectPage` | `app/(app)/crear-proyecto/page.tsx` | `/crear-proyecto` | `CreateProjectPage`, `CreateProjectForm` |
| `Onboarding` | `app/(app)/onboarding/page.tsx` | `/onboarding` | `OnboardingPage` + steps |
| `ProfilePage` | `app/(app)/perfil/page.tsx` | `/perfil` | `ProfilePage`, `CuentaTab`, `AiConfigTab` |
| `project/DiscoveryPage` | `app/(app)/proyecto/descubrimiento/page.tsx` | `/proyecto/descubrimiento` | `DiscoveryPage` |
| `project/CharacteristicsPage` | `app/(app)/proyecto/caracteristicas/page.tsx` | `/proyecto/caracteristicas` | `CharacteristicsPage` |
| `project/CharacteristicsPage` | `app/(app)/proyecto/caracteristicas/nueva/page.tsx` | `/proyecto/caracteristicas/nueva` | `CreateCharacteristic` |
| `project/RequirementsPage` | `app/(app)/proyecto/requisitos/page.tsx` | `/proyecto/requisitos` | `RequirementsPage` |
| `project/ImplementationPage` | `app/(app)/proyecto/codigo/page.tsx` | `/proyecto/codigo` | `ImplementationPage` |
| `project/ImplementationPage` | `app/(app)/proyecto/codigo/resumen/page.tsx` | `/proyecto/codigo/resumen` | `ImplementationSummaryPage` (import directo desde `ui/`) |
| `project/ConsistencyPage` | `app/(app)/proyecto/[fase]/consistencia/page.tsx` | `/proyecto/{fase}/consistencia` | `ConsistencyPage` |

> El pipeline SDD y sus páginas se detallan en [`project/AGENTS.md`](./project/AGENTS.md).

---

## 3. Descripción por página

### `RootPage` (landing pública)
- Compone `RootNavbar`, secciones (`Hero`, `Features`, `FlowSteps`, `SddSection`, `ApiKeySection`, `CtaSection`), `AuthModal` (`Login`/`Register`), `SessionExpiredWatcher` y `VideoIntro`.
- `Login`/`Register` usan `authApi` y navegan a `/proyecto` o `/onboarding`.

### `HomePage`
- Listado de proyectos con conmutador tarjeta/lista (`ViewCardProject`/`ViewTableProject` + `SkeletonCardProject`).
- Al abrir un proyecto: `setCurrentProject` + `initializeProject` + `router.push('/proyecto/descubrimiento')`.
- Borrado con `ModalConfirm` + `toast`.

### `Onboarding`
- Wizard obligatorio `apikey → github → railway` (`StepIndicator` + steps). Bloquea el avance hasta completar cada paso.
- `useOnboardingStatus` combina `getIntegrationStatus` con `useAiConfigStore`.

### `ProfilePage`
- Pestañas `CuentaTab` (datos + logout + integraciones OAuth) y `AiConfigTab` (`AiConfigForm`).
- Detecta popup OAuth (`window.opener` + `code/error/state`), hace `postMessage` al opener y `window.close()`. Redirect URI: `/perfil`.

### Páginas del proyecto (`project/*`)
Ver [`project/AGENTS.md`](./project/AGENTS.md). Resumen de composición recurrente:
- `ChatStreamPanel` (Discovery, Characteristics), `MarkdownEditor` (Discovery, Requirements), `MarkdownText` (Consistency), `PanelAsistenteRequisito` (Requirements), `AiConfigForm` (Onboarding, Profile), `useUnsavedChanges` (Discovery, Requirements).
- Widgets por slice: `@/widgets/root-navbar`, `@/widgets/main-navbar`, `@/widgets/gestion-repositorio-github`.
- Features por slice: `@/features/aside-characteristic`. No existen barrels `@/widgets` ni `@/features`.

---

## 4. Patrones de página

### Hooks locales
- La lógica de fetch/filtros/estado vive en `pages/<X>/hooks/` (ej. `useCharacteristicsPage`, `useCreateCharacteristic`, `useCharacteristicModal`).
- Usar early return si falta `currentProject` (`router.push('/proyecto')`).

### Formularios con validación
- `react-hook-form` + esquemas Zod en `pages/<X>/model/types.ts`.

### Autosave y guardas de navegación
- `useUnsavedChanges` (feature `app-state`) gestiona cambios sin guardar y confirmaciones (`ModalConfirm`) antes de navegar.

### Fetch de datos
- Preferir Server Components; en client, llamar a los stores de entidad (`useXStore`), no a `fetch` directo.

---

## 5. Dónde cambiar qué

```
├── Nueva página/ruta
│   ├── src/pages/<Pagina>/ui  (+ model/ o hooks/ si hace falta)
│   └── app/.../page.tsx       (reexporta + metadata)
│
├── Listado de proyectos         → pages/HomePage/
├── Alta de proyecto             → pages/project/CreateProjectPage/ (+ useIntegrationGate)
├── Wizard de activación         → pages/Onboarding/
├── Perfil / IA                  → pages/ProfilePage/
└── Alguna fase del pipeline SDD → pages/project/<Fase>/ (ver project/AGENTS.md)
```

---

## 6. Invariantes

1. **`app/` sin lógica:** los `page.tsx` solo reexportan y exportan `metadata`.
2. **Respetar la dirección FSD** (importar solo capas inferiores).
3. **Una página = un slice.** No crear páginas fuera de `src/pages/`.
4. **Reutilizar features/widgets/entidades** antes de escribir componentes ad hoc.
5. **`index.ts` como API pública** de la página.

---

## 7. Verificación

```bash
bun run typecheck
bun run build     # validar navegación/rutas
bun run test:coverage
```

**Pruebas de la capa (flujos de usuario completos):**

- Cada página tiene `ui/<Pagina>.test.tsx` que la renderiza con stores, features, widgets y API (MSW) reales, y recorre los flujos de la ruta: carga inicial, estado vacío, acción principal (con su error), confirmaciones y navegación (`mockRouter`).
- Los hooks locales (`hooks/`, `model/`) y los esquemas Zod (`model/types.ts`) se prueban por separado: hooks con `renderHook`, esquemas con tablas `it.each` de entradas válidas e inválidas.
- Las páginas con editor (Descubrimiento, Requisitos) mockean `@/features/markdown-editor` con un `<textarea>` que respeta las props (`markdown`, `onChange`, `saveStatus`, maximizar/minimizar).
