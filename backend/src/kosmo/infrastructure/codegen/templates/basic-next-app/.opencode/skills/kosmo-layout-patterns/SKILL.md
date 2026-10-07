---
name: kosmo-layout-patterns
description: Catálogo de patrones de layout para seleccionar la estructura visual adecuada según el dominio y flujo de datos. Trigger: layout, vista, estructura, composición, pantalla.
---

# Patrones de Layout en KOSMO

No todas las características deben resolverse con la misma estructura visual.
Selecciona el patrón de composición según el tipo de datos y el objetivo del usuario:

---

## 1. Patrones de Composición Disponibles

### A. Dashboard Operativo / Analítico
- **Cuándo usar**: Métricas, KPIs, balances financieros, monitoreo en tiempo real.
- **Estructura**:
  1. `PageHeader` con título, rango temporal o filtros globales a la derecha.
  2. Fila superior de `Stat` cards para métricas clave.
  3. Sección principal con `DataTable` (búsqueda, filtros por estado, ordenamiento).
  4. Panel secundario o modal para ver detalles o registrar nuevas entradas.

### B. Catálogo / Descubrimiento / Tienda (Storefront)
- **Cuándo usar**: Productos, servicios, menús gastronómicos, propiedades inmobiliarias, inventario visual.
- **Estructura**:
  1. `PageHeader` con barra de búsqueda destacada y filtros por categoría/etiqueta.
  2. Grid de tarjetas (`Card` o `CardGrid` con `row g-3 col-12 col-md-6 col-lg-4`).
  3. Precios, disponibilidad, botón de acción visible (`Agregar`, `Reservar`, `Ver detalle`).
  4. `Drawer` o `Modal` para ver el carrito o detalle del ítem.

### C. Flujo de Trabajo Secuencial (Workflow / Wizard)
- **Cuándo usar**: Solicitudes por pasos, onboarding, checkout, trámites burocráticos o aprobaciones.
- **Estructura**:
  1. `Steps` en la parte superior indicando el progreso del flujo.
  2. Formulario en contenedor centrado (`col-lg-8 mx-auto`) dividido en tarjetas lógicas.
  3. Botones de navegación claros (`Atrás`, `Siguiente`, `Confirmar`).
  4. Banners de validación `Alert` y confirmación final con `BadgeStatus`.

### D. Maestro-Detalle (Master-Detail / Split-View)
- **Cuándo usar**: Mensajería, bandeja de entrada, expedientes médicos, tickets de soporte.
- **Estructura**:
  1. Columna izquierda (`col-md-4` o `col-lg-3`): listado filtrable con `ListGroup`.
  2. Columna derecha (`col-md-8` o `col-lg-9`): visualizador de detalle completo de la entidad seleccionada.

### E. Cronograma y Agenda (Calendar / Timeline)
- **Cuándo usar**: Citas médicas, reservas de restaurante, seguimiento de entregas logísticas, historial de auditoría.
- **Estructura**:
  1. Selector de fecha o mes.
  2. `Calendar` mensual o vista de `Timeline` vertical con puntos coloreados por estado.
  3. Detalle de eventos del día seleccionado con acciones de reprogramación o cancelación.

---

## 2. Densidad y Jerarquía
- **Alta densidad (`compact`)**: Paneles administrativos, inventarios grandes, balances contables. Usa `DataTable`, tablas compactas, fuentes pequeñas.
- **Densidad media (`comfortable`)**: Herramientas SaaS generales, paneles de control de usuarios.
- **Baja densidad (`spacious`)**: Vistas orientadas a clientes finales, formularios de registro, artículos de contenido.
