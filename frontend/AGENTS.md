# Manual Técnico del Frontend de KOSMO

> **Destinatario:** Agentes de IA y desarrolladores que operen, mantengan o extiendan el frontend de KOSMO.
> **Ámbito:** Todo el directorio `frontend/` (aplicación Next.js). El núcleo de la aplicación vive en `frontend/src/`.
> **Fuente de Verdad:** El código en `frontend/src/`, `frontend/app/` y los archivos de configuración del directorio.
> **Arquitectura:** Feature-Sliced Design (FSD). Ver [frontend/README.md](./README.md) para las reglas canónicas.
> **Documento relacionado:** [src/AGENTS.md](./src/AGENTS.md) — mapa detallado de las capas FSD.

---

## Cómo leer esta documentación

Para optimizar tokens, la documentación está **fragmentada por nivel**:

| Nivel          | Archivo                                  | Contenido                                                          |
| -------------- | ---------------------------------------- | ------------------------------------------------------------------ |
| Entrada (este) | `frontend/AGENTS.md`                     | Stack, scripts, configuración, rutas `app/`, variables de entorno. |
| Capas          | `frontend/src/AGENTS.md`                 | Mapa FSD completo, reglas de importación, convenciones.            |
| Capa           | `frontend/src/<layer>/AGENTS.md`         | Detalle de slices de cada capa.                                    |
| Slice          | `frontend/src/<layer>/<slice>/AGENTS.md` | Detalle interno de slices complejos.                               |

**Regla:** antes de leer código de una carpeta, lee su `AGENTS.md` más cercano. No hace falta leer los niveles superiores si ya conoces la arquitectura.

---

## 1. Stack Tecnológico

| Categoría             | Tecnología                      | Versión              | Uso                                                     |
| --------------------- | ------------------------------- | -------------------- | ------------------------------------------------------- |
| Framework             | Next.js (App Router)            | `16.2.4`             | Routing, Server/Client Components, build standalone.    |
| UI                    | React                           | `19.2.4`             | Componentes y hooks.                                    |
| Lenguaje              | TypeScript (strict)             | `^5`                 | Tipado estricto; `noEmit`, `moduleResolution: bundler`. |
| Estilos               | Tailwind CSS v4                 | `^4.2.3`             | Utilidades + tokens CSS definidos en `app/globals.css`. |
| Estado global         | Zustand                         | `^5.0.12`            | Stores de entidades y features (con `persist`).         |
| Estado de formularios | react-hook-form + zod           | `^7.79.0` / `^4.3.6` | Formularios validados con esquemas Zod.                 |
| A11y / primitivas     | react-aria-components           | `^1.19.0`            | Componentes accesibles (tooltips, toasts).              |
| Editor Markdown       | @mdxeditor/editor               | `^4.0.1`             | Editor de documentos SDD.                               |
| Diagramas             | @plantuml/core + remark         | `^1.2026.6`          | Render de PlantUML y parseo Markdown.                   |
| Cliente HTTP          | fetch nativo                    | —                    | Envuelto en `shared/api/client.ts`.                     |
| Mocks                 | MSW                             | `^2.13.4`            | `NEXT_PUBLIC_USE_MOCKS` y tests.                        |
| Testing               | Vitest + Testing Library        | `^4.1.4`             | `jsdom`, cobertura v8.                                  |
| Lint                  | ESLint 9 (`eslint-config-next`) | `^9`                 | Reglas Next core-web-vitals + TS.                       |

---

## 2. Scripts (gestor: `bun`)

```bash
bun run dev            # next dev
bun run build          # next build
bun run start          # next start
bun run lint           # eslint
bun run typecheck      # tsc --noEmit
bun run test           # vitest (watch)
bun run test:coverage  # vitest run --coverage
bun run check          # next build && eslint && vitest run --coverage
bun run check-dep      # depcheck
```

**Checklist mínimo antes de dar una tarea por terminada:**

```bash
bun run lint
bun run typecheck
bun run test:coverage
```

> La cobertura (`vitest.config.ts`) solo mide `src/entities/**` y `src/features/**` (excluye `ui/`, `index.ts` y tests), con umbrales: líneas 65%, statements 65%, funciones 60%, branches 55%.

---

## 3. Configuración del Proyecto

| Archivo                                     | Propósito                                                                                      |
| ------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `next.config.ts`                            | `output: 'standalone'`, compresión, `optimizePackageImports`.                                  |
| `tsconfig.json`                             | Alias `@/*` → `./src/*`; excluye `*.test.*` y `docs`.                                          |
| `vitest.config.ts`                          | Alias `@` → `./src` y `app` → `./app`; entorno `jsdom`.                                        |
| `eslint.config.mjs`                         | `no-unused-vars` como warning (ignora `_`); ignora `mockServiceWorker.js`.                     |
| `tailwind.config.ts` + `postcss.config.mjs` | Pipeline de Tailwind v4.                                                                       |
| `app/globals.css`                           | Tokens de diseño/paleta vía `@theme` de Tailwind v4. **Usar tokens, no valores hardcodeados.** |
| `.env.example`                              | Plantilla de variables `NEXT_PUBLIC_*`.                                                        |

### Variables de Entorno (prefijo `NEXT_PUBLIC_`)

| Variable                                                         | Uso                                                                                                                            |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `NEXT_PUBLIC_API_URL`                                            | Base de la API. Vacío en producción (mismo origen Nginx); default dev `http://localhost:8000`. Ver `src/shared/api/config.ts`. |
| `NEXT_PUBLIC_DOMAIN_APP`                                         | Dominio público de la app (`PUBLIC_APP_DOMAIN`).                                                                               |
| `NEXT_PUBLIC_APP_NAME` / `NEXT_PUBLIC_APP_ENV`                   | Metadatos de la app.                                                                                                           |
| `NEXT_PUBLIC_AUTH_DISABLED`                                      | Bypass de auth en dev; usa `X-Mock-User`.                                                                                      |
| `NEXT_PUBLIC_USE_MOCKS`                                          | Activa mocks MSW en los `api/` de entidades.                                                                                   |
| `NEXT_PUBLIC_GITHUB_CLIENT_ID` / `NEXT_PUBLIC_RAILWAY_CLIENT_ID` | OAuth de integraciones.                                                                                                        |

> **Nunca** colocar secretos en variables `NEXT_PUBLIC_*`: se embeben en el bundle del navegador.

---

## 4. Punto de Entrada: `app/` (Next App Router)

`app/` **no** contiene lógica de negocio: cada archivo de ruta reexporta un componente desde `src/pages/`. Es el único lugar donde se permite componer todas las capas FSD.

### Layouts y archivos globales

| Archivo                            | Responsabilidad                                                                                                                                                                 |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `app/layout.tsx`                   | Root layout: fuente Geist, `globals.css`, `<ToasterProvider />` y `<SessionExpiredListener />`. Metadata base.                                                                  |
| `app/(app)/layout.tsx`             | Layout autenticado: envuelve en `<AuthGuard>` y `<MainNavbar>`.                                                                                                                 |
| `app/(root)/layout.tsx`            | Layout público: antepone `<RootNavbar>`.                                                                                                                                        |
| `app/not-found.tsx`                | Página 404.                                                                                                                                                                     |
| `app/session-expired-listener.tsx` | **Composition root**: une el evento `onSessionExpired` (de `shared`) con `clearAllStores` (de `features/app-state`). Vive aquí porque `shared` no puede depender de `features`. |

### Mapa de Rutas → Páginas

| URL                               | Archivo de ruta                                     | Página (`src/pages`)              |
| --------------------------------- | --------------------------------------------------- | --------------------------------- |
| `/`                               | `app/page.tsx`                                      | `RootPage` (landing + login)      |
| `/proyecto`                       | `app/(app)/proyecto/page.tsx`                       | `HomePage` (listado de proyectos) |
| `/crear-proyecto`                 | `app/(app)/crear-proyecto/page.tsx`                 | `CreateProjectPage`               |
| `/onboarding`                     | `app/(app)/onboarding/page.tsx`                     | `OnboardingPage`                  |
| `/perfil`                         | `app/(app)/perfil/page.tsx`                         | `ProfilePage`                     |
| `/proyecto/descubrimiento`        | `app/(app)/proyecto/descubrimiento/page.tsx`        | `DiscoveryPage`                   |
| `/proyecto/caracteristicas`       | `app/(app)/proyecto/caracteristicas/page.tsx`       | `CharacteristicsPage`             |
| `/proyecto/caracteristicas/nueva` | `app/(app)/proyecto/caracteristicas/nueva/page.tsx` | `CreateCharacteristic`            |
| `/proyecto/requisitos`            | `app/(app)/proyecto/requisitos/page.tsx`            | `RequirementsPage`                |
| `/proyecto/modelo`                | `app/(app)/proyecto/modelo/page.tsx`                | `ModelingPage`                    |
| `/proyecto/codigo`                | `app/(app)/proyecto/codigo/page.tsx`                | `ImplementationPage`              |
| `/proyecto/codigo/resumen`        | `app/(app)/proyecto/codigo/resumen/page.tsx`        | `ImplementationSummaryPage`       |
| `/proyecto/{fase}/consistencia`   | `app/(app)/proyecto/[fase]/consistencia/page.tsx`   | `ConsistencyPage`                 |

> **Convención:** los `page.tsx` solo hacen `export { X as default } from '@/pages/...'` y exportan `metadata`. No agregar lógica ni `'use client'` aquí.

---

## 5. Estructura de `src/` (resumen)

```
src/
├── shared/     # Transversal sin lógica de negocio (ui, lib, api, model)
├── entities/   # Dominio: datos y acceso a API (model, api)
├── features/   # Acciones del usuario (ui, model, lib) — agnósticas a la API
├── widgets/    # Bloques UI complejos (ui, model, lib, types)
└── pages/      # Composición por ruta (ui, model, hooks)
```

Dependencias permitidas (solo hacia abajo): `pages → widgets → features → entities → shared`.

➡️ **Detalle completo en [src/AGENTS.md](./src/AGENTS.md).**

---

## 6. Reglas de Oro

1. **No duplicar el árbol de capas:** antes de crear código nuevo, lee el `AGENTS.md` de la capa/slice correspondiente.
2. **`app/` sin lógica:** la lógica pertenece a `src/pages/` o capas inferiores.
3. **Tokens de diseño:** usar variables de `app/globals.css`; nada de hex/hardcodes.
4. **`'use client'` solo cuando sea necesario:** preferir Server Components.
5. **Respetar la dirección de imports de FSD** (nunca importar una capa superior desde una inferior).
