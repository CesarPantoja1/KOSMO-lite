---
name: kosmo-design-tokens
description: Guía y directivas para usar los Design Tokens del proyecto. Theming, paleta de colores, tipografía, radios y coherencia visual. Trigger: tokens, color, tema, estilos, tipografía.
---

# Uso de Design Tokens en KOSMO

Esta skill define cómo consumir y respetar la identidad visual del proyecto generada por KOSMO.

---

## 1. Punto único de verdad: `src/lib/design-tokens.ts`

Cada aplicación cuenta con un contrato tipado en `src/lib/design-tokens.ts`:
- **`colors`**: paleta semántica completa generada para el dominio del negocio (`primary`, `secondary`, `success`, `warning`, `danger`, `accent`, `bodyBg`, `cardBg`, `mutedBg`, `border`, `text`).
- **`typography`**: fuentes asignadas para cuerpo (`fontFamily`) y encabezados (`fontHeading`).
- **`shape`**: radios de curvatura (`radius`, `radiusSm`, `radiusLg`) y sombras (`shadowSm`, `shadow`, `shadowLg`).
- **`layout`**: patrón de shell (`sidebar`, `top_nav`, `minimal`) y densidad (`compact`, `comfortable`, `spacious`).

Las variables CSS equivalentes están disponibles globalmente en `:root` en `src/app/globals.css`:
- `var(--app-primary)` y `var(--bs-primary)`
- `var(--app-secondary)` y `var(--bs-secondary)`
- `var(--app-success)` y `var(--bs-success)`
- `var(--app-warning)` y `var(--bs-warning)`
- `var(--app-danger)` y `var(--bs-danger)`
- `var(--app-accent)` y `var(--bs-info)`
- `var(--app-card-bg)`, `var(--app-body-bg)`, `var(--app-border)`
- `var(--app-radius)`, `var(--bs-border-radius)`

---

## 2. Regla de Coherencia Visual

1. **Nunca inventes colores hexadecimales arbitrarios**: no uses `#3498db` ni `#ff0000` en estilos inline.
2. **Usa las clases de Bootstrap 5**:
   - `btn btn-primary`, `btn btn-secondary`, `btn btn-outline-primary`
   - `badge bg-success`, `badge bg-warning text-dark`, `badge bg-danger`
   - `text-primary`, `text-secondary`, `text-muted`
   - `border`, `border-primary`, `border-secondary-subtle`
   - `bg-light`, `bg-white`
3. **Para estilos custom necesarios**: consume siempre las variables:
   ```tsx
   <div style={{ backgroundColor: "var(--app-muted-bg)", borderRadius: "var(--app-radius)" }}>
   ```
4. **Nuevas Características**: deben verse como parte del mismo producto. Consulta los tokens existentes antes de implementar vistas adicionales.
