---
name: kosmo-ui
description: UI funcional, moderna y coherente con Bootstrap 5 y Design Tokens. Catálogo completo de componentes y composición responsiva. Trigger: UI, diseño, componentes, navegación, bootstrap.
---

# UI, Navegación y Diseño con Bootstrap 5 en KOSMO

Esta skill define el contrato de diseño que toda feature implementada debe cumplir.
El stack frontend se basa en **Bootstrap 5**, el Design System del proyecto (`src/components/ui/`) y los tokens semánticos definidos en `src/lib/design-tokens.ts` e inyectados en `src/app/globals.css`.
**PROHIBIDO el uso de Tailwind CSS.**

---

## 1. Regla de oro: toda feature entrega una pantalla funcional y diferenciada

Una feature NO está implementada si solo existe su lógica. Toda feature debe entregar:

1. **Ruta visible**: `src/app/<slug>/page.tsx` (Server Component que renderiza el componente principal de la feature con `export default`).
2. **Slice autocontenido** en `src/features/<slug>/`:
   - `manifest.ts` — `{ slug, title, description, route, icon }` (icono de `lucide-react`).
   - `logic.ts` — lógica de negocio pura, tipada, sin I/O ni React.
   - `actions.ts` — Server Actions (`"use server"`) para persistencia y mutaciones reales en SQLite (`db`) con `revalidatePath`.
   - `components/` — componentes de la UI de la feature (usando `src/components/ui/` y clases de Bootstrap).
   - `index.ts` — exports públicos del slice.
3. **Registro de navegación**: importar el manifest en `src/lib/feature-registry.ts`.
   - Si la aplicación tiene múltiples actores o dominios (ej. Cliente vs Administrador), define `group` en el manifest y regístrala en `featureGroups` para que la navegación organice las secciones por actor.
4. **Tests** de la lógica en Vitest (`tests/` o dentro del slice).

**Desacople absoluto**: el shell (`layout`, navbar, home) y las demás features NO pueden importar
nada del interior de otro slice. Eliminar una feature = borrar `src/features/<slug>/` + su import
en el registro. Nada más.

**Creatividad gobernada y componentes propios**: Si la feature necesita un componente visual especializado no presente en `src/components/ui/` (ej. una tarjeta de menú gastronómico, un selector de horarios médicos, un panel de estado de envío), **constrúyelo en `src/features/<slug>/components/`** usando las utilidades de Bootstrap 5 y consumiendo las variables CSS de los tokens (`var(--app-*)`).

---

## 2. Catálogo del Design System (`src/components/ui/`)

Usa los componentes del catálogo como bloques de construcción principales:

### Estructura y Contenedores
- `Card`, `CardHeader`, `CardTitle`, `CardDescription`, `CardBody`, `CardFooter`, `CardGrid` — Tarjetas de contenido estructuradas.
- `PageHeader` — Encabezado estándar de vista con título, descripción y botones de acción.
- `Separator` — Divisores horizontales y verticales, con soporte de texto central.

### Datos y Tablas
- `DataTable` — Tabla completa interactiva con ordenamiento, búsqueda integrada y paginación.
- `Table`, `TableHeader`, `TableBody`, `TableRow`, `TableHead`, `TableCell` — Tablas tabulares base.
- `Stat` — KPIs, métricas numéricas con variación porcentual e indicadores de tendencia.
- `Calendar` — Vista de calendario mensual para citas, eventos, reservas y cronogramas.
- `Timeline`, `TimelineItem` — Trazabilidad cronológica de etapas, auditorías o estados.

### Formularios e Interacción
- `Button` — Acciones principales y secundarias (`variant="primary" | "secondary" | "outline" | "danger" | "light"`).
- `Input`, `Select`, `Label`, `Textarea` — Campos de captura con soporte de validación (`isInvalid`).
- `Checkbox`, `RadioGroup`, `Switch` — Controles booleanos y selecciones múltiples accesibles.
- `FileUpload` — Zona de carga de archivos drag & drop con previsualización.

### Navegación y Vistas
- `Tabs` — Pestañas para alternar vistas o roles (`variant="tabs" | "pills"`).
- `Breadcrumb` — Migas de pan para rutas anidadas.
- `Pagination` — Control de paginación numérica.
- `Steps` — Indicador multi-etapa para flujos secuenciales o wizards.
- `Dropdown` — Menús contextuales y acciones agrupadas.

### Feedback, Overlays y Estados
- `Alert` — Banners de feedback (`variant="info" | "success" | "warning" | "danger"`).
- `Badge`, `BadgeStatus` — Etiquetas semánticas y estados de ciclo de vida del negocio.
- `Modal` — Diálogos de confirmación y formularios modales.
- `Drawer` — Panel lateral desplegable (offcanvas) para edición rápida o detalles secundarios.
- `Toast`, `ToastContainer` — Notificaciones efímeras accesibles.
- `Tooltip` — Ayudas contextuales al pasar el cursor o hacer focus.
- `EmptyState` — Estados vacíos atractivos con icono, título, descripción y botón de acción.
- `Skeleton`, `SkeletonCard` — Marcadores de posición animados tipo shimmer mientras se cargan datos.
- `Spinner`, `LoadingOverlay` — Indicadores de carga interactiva.
- `Avatar` — Identificadores de usuario o entidad con iniciales o imagen.
- `CommandPalette` — Barra de búsqueda y atajos rápidos de teclado.

---

## 3. Composición Visual y Grid Responsive

- **Grid Responsive de Bootstrap**: usa `container-fluid` o `container`, estructurando con `row` y columnas responsivas: `col-12`, `col-md-6`, `col-lg-4`, etc.
- **Espaciado consistente**: usa las utilidades `gap-2`, `gap-3`, `gap-4`, `p-3`, `mb-4`.
- **Flexbox nativo**: `d-flex`, `align-items-center`, `justify-content-between`, `flex-wrap`.
- **Cero colores hex hardcoded**: utiliza siempre las clases semánticas de Bootstrap (`text-primary`, `bg-success`, `border-warning`) o las variables CSS `var(--app-primary)`, `var(--app-secondary)`, `var(--app-border)`, etc.

---

## 4. Anti-Patrones Prohibidos

- ❌ **No crees dashboards genéricos de tarjetas repetitivas** cuando la información requiere una tabla o timeline.
- ❌ **No uses "Lorem Ipsum"** ni textos de bienvenida genéricos. Todo texto debe ser en español neutro y específico del dominio del negocio.
- ❌ **No uses persistencia simulada con arrays en memoria o `useState` sin base de datos**: todo formulario que registre o modifique datos debe invocar una Server Action en `actions.ts` conectada a SQLite con Drizzle ORM.
- ❌ **No dejes pantallas vacías o stubs**: cada página debe permitir interactuar, capturar datos y ver resultados.
- ❌ **No uses Tailwind CSS**: el proyecto usa 100% Bootstrap 5.
