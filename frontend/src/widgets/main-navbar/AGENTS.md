# Widget `main-navbar/` — Layout autenticado

> **Destinatario:** Agentes de IA que trabajen en `frontend/src/widgets/main-navbar/`.
> **Ámbito:** shell de la aplicación autenticada: sidebar (marca + proyectos + usuario) y área principal.
> **Nivel superior:** [`../AGENTS.md`](../AGENTS.md) (capa `widgets`).

---

## 1. Estructura

```
main-navbar/
├── ui/
│   ├── MainNavbar.tsx        # Contenedor del layout autenticado
│   ├── SidebarBrand.tsx      # Marca KOSMO + toggle del sidebar
│   ├── ProjectNavigation.tsx # Botón Inicio + lista de proyectos
│   └── UserSection.tsx       # Avatar, perfil y cerrar sesión
├── model/
│   └── types.ts              # IconWizardProps
└── index.tsx                 # Barrel
```

**Exports:** `MainNavbar`, tipo `IconWizardProps`.

---

## 2. Composición

```
MainNavbar (children)
├── Sidebar
│   ├── SidebarBrand          # marca + toggle expandir/colapsar
│   ├── ProjectNavigation     # Inicio + proyectos (activo/selección)
│   └── UserSection           # avatar + /perfil + logout
└── main
    ├── WizardNavegacion      # barra de pasos SDD (widget)
    ├── GitHubSyncBanner      # feature github-sync
    └── {children}            # página activa
```

---

## 3. Detalle

| Componente | Responsabilidad |
|---|---|
| `MainNavbar` | Carga proyectos con `getProjectsStore`; decide ocultar sidebar/header cuando `isEditorMaximized`; resuelve navegación con `pendingNavigationPath` (protección de cambios sin guardar). |
| `SidebarBrand` | Cabecera del sidebar; botón "KOSMO" (`/`) y toggle. Colapsado muestra el `Logo` y revela el botón de expandir en hover. |
| `ProjectNavigation` | Versión expandida (nombre + icono) o colapsada (iniciales); estado activo; callbacks `onHomeClick`/`onProjectClick`. |
| `UserSection` | Avatar/nombre, acceso a `/perfil` y logout. Colapsado abre menú flotante; con cambios sin guardar pide confirmación (`ModalConfirm`). |

---

## 4. Integración

- Montado por `app/(app)/layout.tsx` (envuelto antes por `AuthGuard`).
- Consume `useProjectStore` (entities/project) y `useAppStore` (features/app-state).
- Compone `WizardNavegacion` (widget) y `GitHubSyncBanner` (feature).
- El estado de maximizado de editor (`isEditorMaximized`) proviene de `features/app-state`.

---

## 5. Dónde cambiar qué

```
├── Estructura del layout/sidebar     → ui/MainNavbar.tsx
├── Navegación de proyectos           → ui/ProjectNavigation.tsx
├── Marca/toggle del sidebar          → ui/SidebarBrand.tsx
├── Bloque de usuario / logout         → ui/UserSection.tsx
└── Colapso general / estados           → features/app-state/model/app.store.ts
```

---

## 6. Invariantes

1. **Sin lógica de negocio propia:** consumir stores de `entities`/`features`.
2. **Sin importar** `pages`.
3. **Reutilizar** `WizardNavegacion`, `GitHubSyncBanner`, `ModalConfirm`; no duplicarlos.
4. **`index.tsx` como API pública.**

---

## 7. Verificación

```bash
bun run typecheck
bun run build
```
