# Capa `widgets/` — Bloques UI complejos

> **Destinatario:** Agentes de IA que trabajen en `frontend/src/widgets/`.
> **Ámbito:** `src/widgets/` — bloques UI que componen múltiples entidades y features en una unidad cohesiva (navbars, paneles, wizards).
> **Regla:** los widgets importan de `features`, `entities` y `shared`.
> **Nivel superior:** [../AGENTS.md](../AGENTS.md).

---

## 1. Estructura y segmentos

```
widgets/<widget>/
├── ui/       # Composición visual
├── model/    # Coordinación de estado entre slices
├── lib/      # Utilidades internas
├── types/    # Tipos propios (o model/types.ts)
└── index.ts  # API pública
```

Segmentos permitidos: **`ui/`**, **`model/`**, **`lib/`**, **`types/`**.

**Importación:** no existe `widgets/index.ts` (barril de capa). Cada consumidor importa del slice: `@/widgets/<widget>` (p. ej. `@/widgets/main-navbar`).

---

## 2. Catálogo de widgets

| Widget | Archivos clave | Exports | Propósito |
|---|---|---|---|
| `main-navbar` | `ui/MainNavbar.tsx`, `ProjectNavigation.tsx`, `SidebarBrand.tsx`, `UserSection.tsx`; `model/types.ts`; `index.tsx` | `MainNavbar`, `IconWizardProps` | Layout autenticado: sidebar (marca + proyectos + usuario) y área principal con `WizardNavegacion` y `GitHubSyncBanner`. **Ver [`main-navbar/AGENTS.md`](./main-navbar/AGENTS.md).** |
| `wizard-navegacion` | `ui/WizardNavegacion.tsx`, `WizardItem.tsx`, `PhaseStatusBadge.tsx`, `ConsistencyGateButton.tsx`, `AiProviderToast.tsx`; `model/types.ts`, `get-status-color.ts`, `useConsistencyPolling.ts` | `WizardNavegacion` | Barra de pasos del pipeline SDD (Descubrimiento→Funcionalidades→Criterios→Implementación) con badges de consistencia y gate. |
| `root-navbar` | `ui/RootNavbar.tsx` | `RootNavbar` | Navbar público de la landing (anclas + "Comenzar"/"Mi Cuenta" según sesión). Renderizado por `RootPage`; también antepuesto por `app/(root)/layout.tsx`. |
| `gestion-repositorio-github` | `ui/GestionRepositorioGitHub.tsx` | `GestionRepositorioGitHub` | Tarjeta que gestiona el repo GitHub según `ProjectGithubViewState` (crear/sincronizar/estado). |

---

## 3. Detalle de widgets no triviales

### `wizard-navegacion`
- `WizardNavegacion` define `phaseItems` (hitos del proyecto), calcula `activeIndex` y el estado por paso.
- Integra `useConsistencyPolling` (refresco periódico de `getConsistencyStatus` solo con pestaña visible y anti-solapamiento), `PhaseStatusBadge` (pendientes/evaluando/fallos) y `ConsistencyGateButton` (navega a la ruta de revisión respetando cambios sin guardar).
- `AiProviderToast` avisa cuando falta la API Key de IA y enlaza a `/onboarding`.
- `model/types.ts` agrupa `ProjectStatus` (`active | completed | disable`), `ItemWizardProps` y `stylesIconStatus`; `model/get-status-color.ts` centraliza los estilos Tailwind por estado.
- Se oculta en rutas de consistencia y cuando `isProyectosOpen` es falso.

### `main-navbar`
- `MainNavbar` es el contenedor del layout autenticado: sidebar (`SidebarBrand` + `ProjectNavigation` + `UserSection`) y `main` (con `WizardNavegacion` + `GitHubSyncBanner` + `children`).
- Oculta sidebar/header cuando `isEditorMaximized`.
- Gestiona navegación con protección de cambios sin guardar (`pendingNavigationPath`).

### `gestion-repositorio-github`
- Controlado por `ProjectGithubViewState`; en estado `create` usa `FormularioCreacionRepositorio` (shared/ui). Muestra visibilidad, URL, última sincronización y hash corto.

---

## 4. Patrones

- Un widget **compone** (`ui/`) y, si cruza varias entidades/features, añade `model/` para coordinarlas.
- Preferir props/estado de entidad antes de crear estado propio en el widget.
- Los iconos provienen de `@/shared/ui`; los componentes compartidos (modales, toast, formularios de repo) de `@/shared/ui`.

---

## 5. Dónde cambiar qué

```
├── Layout autenticado / sidebar          → widgets/main-navbar/
├── Barra de pasos SDD / consistencia     → widgets/wizard-navegacion/
├── Navbar de landing                     → widgets/root-navbar/
└── Tarjeta de repositorio GitHub         → widgets/gestion-repositorio-github/
```

---

## 6. Invariantes

1. **Sin importar** `pages`.
2. **No duplicar** lógica de entidad: consumir stores/APIs de `@/entities/*`.
3. **Reutilizar** `shared/ui` (modales, toast, formularios) en lugar de reimplementar.
4. **`index.ts` del slice como API pública**; importar de `@/widgets/<widget>`. No hay barril de capa.
5. Un widget complejo con lógica de coordinación debe documentarse con su propio `AGENTS.md`.

---

## 7. Verificación

```bash
bun run typecheck
# los widgets no se miden en cobertura
```
