from __future__ import annotations

import json

from kosmo.contracts.sdd.ux_context import BootstrapDesignTokens


def _typescript_string(value: str) -> str:
    """Devuelve un literal de cadena TypeScript seguro para contenido proporcionado por usuarios."""
    return json.dumps(value, ensure_ascii=False)


def format_site_config(
    name: str,
    description: str,
    archetype: str = "saas_tool",
    primary_color: str = "#0f766e",
) -> str:
    """Genera el contenido TypeScript para src/lib/site.ts respetando el esquema del template."""
    return (
        "export const siteConfig = {\n"
        f"  name: {_typescript_string(name)},\n"
        f"  description: {_typescript_string(description)},\n"
        f"  archetype: {_typescript_string(archetype)} as\n"
        '    | "storefront"\n'
        '    | "dashboard"\n'
        '    | "workflow"\n'
        '    | "saas_tool"\n'
        '    | "content",\n'
        f"  primaryColor: {_typescript_string(primary_color)},\n"
        "} as const;\n"
    )


def format_design_tokens_ts(
    tokens: BootstrapDesignTokens,
    domain: str = "general",
) -> str:
    """Genera el contenido TypeScript para src/lib/design-tokens.ts con la paleta y atributos del proyecto."""
    return (
        'import type { DesignTokens } from "./design-tokens";\n\n'
        "export const designTokens: DesignTokens = {\n"
        "  brand: {\n"
        f"    personality: {_typescript_string(tokens.brand_personality)},\n"
        f"    domain: {_typescript_string(domain)},\n"
        "  },\n"
        "  colors: {\n"
        f"    primary: {_typescript_string(tokens.primary_color)},\n"
        f"    primaryRgb: {_typescript_string(tokens.primary_rgb)},\n"
        f"    secondary: {_typescript_string(tokens.secondary_color)},\n"
        f"    secondaryRgb: {_typescript_string(tokens.secondary_rgb)},\n"
        f"    success: {_typescript_string(tokens.success_color)},\n"
        f"    successRgb: {_typescript_string(tokens.success_rgb)},\n"
        f"    warning: {_typescript_string(tokens.warning_color)},\n"
        f"    warningRgb: {_typescript_string(tokens.warning_rgb)},\n"
        f"    danger: {_typescript_string(tokens.danger_color)},\n"
        f"    dangerRgb: {_typescript_string(tokens.danger_rgb)},\n"
        f"    accent: {_typescript_string(tokens.accent_color)},\n"
        f"    accentRgb: {_typescript_string(tokens.accent_rgb)},\n"
        f"    bodyBg: {_typescript_string(tokens.body_bg)},\n"
        f"    cardBg: {_typescript_string(tokens.card_bg)},\n"
        f"    mutedBg: {_typescript_string(tokens.muted_bg)},\n"
        f"    mutedText: {_typescript_string(tokens.muted_text)},\n"
        f"    border: {_typescript_string(tokens.border_color)},\n"
        f"    text: {_typescript_string(tokens.text_color)},\n"
        f"    textSecondary: {_typescript_string(tokens.text_secondary)},\n"
        "  },\n"
        "  typography: {\n"
        f"    fontFamily: {_typescript_string(tokens.font_family_sans)},\n"
        f"    fontHeading: {_typescript_string(tokens.font_heading)},\n"
        "  },\n"
        "  shape: {\n"
        f"    radius: {_typescript_string(tokens.border_radius)},\n"
        f"    radiusSm: {_typescript_string(tokens.border_radius_sm)},\n"
        f"    radiusLg: {_typescript_string(tokens.border_radius_lg)},\n"
        f"    shadowSm: {_typescript_string(tokens.shadow_sm)},\n"
        f"    shadow: {_typescript_string(tokens.card_shadow)},\n"
        f"    shadowLg: {_typescript_string(tokens.shadow_lg)},\n"
        "  },\n"
        "  layout: {\n"
        '    shell: "sidebar",\n'
        f'    density: "{"compact" if tokens.table_density_class == "table-sm" else "comfortable"}",\n'
        "  },\n"
        "};\n"
    )


def format_globals_css(tokens: BootstrapDesignTokens) -> str:
    """Genera src/app/globals.css inyectando las variables CSS de tokens específicos del proyecto."""
    return f"""@import "bootstrap/dist/css/bootstrap.min.css";

:root {{
  /* ═══ KOSMO DESIGN TOKENS (Adaptables por proyecto) ═══ */

  /* Paleta semántica */
  --app-primary: {tokens.primary_color};
  --app-primary-rgb: {tokens.primary_rgb};
  --app-secondary: {tokens.secondary_color};
  --app-secondary-rgb: {tokens.secondary_rgb};
  --app-success: {tokens.success_color};
  --app-success-rgb: {tokens.success_rgb};
  --app-warning: {tokens.warning_color};
  --app-warning-rgb: {tokens.warning_rgb};
  --app-danger: {tokens.danger_color};
  --app-danger-rgb: {tokens.danger_rgb};
  --app-accent: {tokens.accent_color};
  --app-accent-rgb: {tokens.accent_rgb};

  /* Superficies y texto */
  --app-body-bg: {tokens.body_bg};
  --app-card-bg: {tokens.card_bg};
  --app-muted-bg: {tokens.muted_bg};
  --app-muted-text: {tokens.muted_text};
  --app-border: {tokens.border_color};
  --app-text: {tokens.text_color};
  --app-text-secondary: {tokens.text_secondary};

  /* Tipografía */
  --app-font: {tokens.font_family_sans};
  --app-font-heading: {tokens.font_heading};

  /* Formas y Sombras */
  --app-radius: {tokens.border_radius};
  --app-radius-sm: {tokens.border_radius_sm};
  --app-radius-lg: {tokens.border_radius_lg};
  --app-shadow-sm: {tokens.shadow_sm};
  --app-shadow: {tokens.card_shadow};
  --app-shadow-lg: {tokens.shadow_lg};

  /* ═══ BOOTSTRAP 5 CSS VARIABLES OVERRIDE ═══ */
  --bs-primary: var(--app-primary);
  --bs-primary-rgb: var(--app-primary-rgb);
  --bs-secondary: var(--app-secondary);
  --bs-secondary-rgb: var(--app-secondary-rgb);
  --bs-success: var(--app-success);
  --bs-success-rgb: var(--app-success-rgb);
  --bs-warning: var(--app-warning);
  --bs-warning-rgb: var(--app-warning-rgb);
  --bs-danger: var(--app-danger);
  --bs-danger-rgb: var(--app-danger-rgb);
  --bs-info: var(--app-accent);
  --bs-info-rgb: var(--app-accent-rgb);

  --bs-body-font-family: var(--app-font);
  --bs-body-bg: var(--app-body-bg);
  --bs-body-color: var(--app-text);
  --bs-border-color: var(--app-border);
  --bs-border-radius: var(--app-radius);
  --bs-border-radius-sm: var(--app-radius-sm);
  --bs-border-radius-lg: var(--app-radius-lg);
}}

body {{
  background-color: var(--bs-body-bg);
  font-family: var(--bs-body-font-family);
  color: var(--bs-body-color);
  min-height: 100vh;
}}

h1, h2, h3, h4, h5, h6 {{
  font-family: var(--app-font-heading);
}}

.card {{
  border: 1px solid var(--bs-border-color);
  border-radius: var(--bs-border-radius);
  background-color: var(--app-card-bg);
  box-shadow: var(--app-shadow);
  transition: box-shadow 0.15s ease, border-color 0.15s ease;
}}

.table-responsive {{
  border-radius: var(--bs-border-radius);
  border: 1px solid var(--bs-border-color);
  background-color: var(--app-card-bg);
  box-shadow: var(--app-shadow-sm);
}}

.table {{
  margin-bottom: 0;
  vertical-align: middle;
}}

.app-sidebar {{
  width: 260px;
  background-color: var(--app-card-bg);
  border-right: 1px solid var(--bs-border-color);
  min-height: 100vh;
}}

.app-sidebar-link {{
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.625rem 0.875rem;
  border-radius: var(--bs-border-radius);
  color: var(--app-text-secondary);
  text-decoration: none;
  font-weight: 500;
  font-size: 0.875rem;
  transition: background-color 0.15s ease, color 0.15s ease;
}}

.app-sidebar-link:hover {{
  background-color: var(--app-muted-bg);
  color: var(--app-text);
}}

.app-sidebar-link.active {{
  background-color: rgba(var(--bs-primary-rgb), 0.1);
  color: var(--bs-primary);
  font-weight: 600;
}}

@keyframes kosmo-shimmer {{
  0% {{ background-position: -200% 0; }}
  100% {{ background-position: 200% 0; }}
}}

.kosmo-skeleton {{
  background: linear-gradient(90deg, var(--app-muted-bg) 25%, #e2e8f0 50%, var(--app-muted-bg) 75%);
  background-size: 200% 100%;
  animation: kosmo-shimmer 1.5s infinite;
  border-radius: var(--bs-border-radius-sm);
}}

.kosmo-timeline {{
  position: relative;
  padding-left: 1.5rem;
}}

.kosmo-timeline::before {{
  content: "";
  position: absolute;
  top: 0.5rem;
  bottom: 0.5rem;
  left: 0.5rem;
  width: 2px;
  background-color: var(--bs-border-color);
}}

.kosmo-timeline-item {{
  position: relative;
  margin-bottom: 1.5rem;
}}

.kosmo-timeline-item:last-child {{
  margin-bottom: 0;
}}

.kosmo-timeline-point {{
  position: absolute;
  left: -1.5rem;
  top: 0.25rem;
  width: 1rem;
  height: 1rem;
  border-radius: 50%;
  border: 2px solid #ffffff;
  background-color: var(--bs-primary);
  box-shadow: 0 0 0 2px var(--bs-border-color);
}}
"""
