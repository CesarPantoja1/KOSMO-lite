from __future__ import annotations

import math
from typing import NamedTuple

from kosmo.contracts.sdd.ux_context import BootstrapDesignTokens, BusinessArchetype


class RGB(NamedTuple):
    r: int
    g: int
    b: int

    def to_hex(self) -> str:
        return f"#{self.r:02x}{self.g:02x}{self.b:02x}"

    def to_rgb_str(self) -> str:
        return f"{self.r}, {self.g}, {self.b}"


def oklch_to_rgb(lightness: float, c: float, h_deg: float) -> RGB:
    """Convierte OKLCH a RGB sRGB usando transformaciones matemáticas estándar."""
    h_rad = math.radians(h_deg)
    a = c * math.cos(h_rad)
    b = c * math.sin(h_rad)

    # OKLab a cono LMS
    l_ = lightness + 0.3963377774 * a + 0.2158037573 * b
    m_ = lightness - 0.1055613458 * a - 0.0638541728 * b
    s_ = lightness - 0.0894841775 * a - 1.2914855480 * b

    l_cubed = l_**3
    m_cubed = m_**3
    s_cubed = s_**3

    # LMS a sRGB lineal
    r_lin = +4.0767434721 * l_cubed - 3.3077115913 * m_cubed + 0.2309699292 * s_cubed
    g_lin = -1.2684380046 * l_cubed + 2.6097574011 * m_cubed - 0.3413193965 * s_cubed
    b_lin = -0.0041960863 * l_cubed - 0.7034186147 * m_cubed + 1.7076147010 * s_cubed

    def transfer(val: float) -> int:
        val = max(0.0, min(1.0, val))
        s = 12.92 * val if val <= 0.0031308 else 1.055 * (val ** (1.0 / 2.4)) - 0.055
        return round(max(0.0, min(1.0, s)) * 255)

    return RGB(r=transfer(r_lin), g=transfer(g_lin), b=transfer(b_lin))


# Rangos de tono (Hue) por arquetipo/dominio
ARCHETYPE_HUE_RANGES: dict[BusinessArchetype, tuple[float, float, str]] = {
    BusinessArchetype.DASHBOARD: (240.0, 265.0, "analítico, preciso, sobrio"),
    BusinessArchetype.STOREFRONT: (160.0, 185.0, "energético, fresco, confiable"),
    BusinessArchetype.WORKFLOW: (215.0, 235.0, "ordenado, corporativo, enfocado"),
    BusinessArchetype.CONTENT: (280.0, 310.0, "creativo, accesible, claro"),
    BusinessArchetype.SAAS_TOOL: (170.0, 200.0, "moderno, eficiente, productivo"),
}


def generate_domain_tokens(
    archetype: BusinessArchetype,
    seed_text: str = "",
) -> BootstrapDesignTokens:
    """Genera tokens de diseño visual adaptativos basados en el arquetipo y texto de descubrimiento."""
    hue_min, hue_max, default_personality = ARCHETYPE_HUE_RANGES.get(
        archetype, ARCHETYPE_HUE_RANGES[BusinessArchetype.SAAS_TOOL]
    )

    # Variación determinista pero única por texto del proyecto
    hash_val = sum(ord(ch) for ch in seed_text) if seed_text else 42
    hue_variance = (hash_val % 100) / 100.0
    primary_hue = hue_min + hue_variance * (hue_max - hue_min)

    # Colores calculados mediante OKLCH para garantizar contraste y luminosidad consistente
    primary = oklch_to_rgb(0.52, 0.15, primary_hue)
    secondary = oklch_to_rgb(0.55, 0.03, (primary_hue + 180) % 360)
    success = oklch_to_rgb(0.58, 0.16, 142.0)
    warning = oklch_to_rgb(0.68, 0.15, 75.0)
    danger = oklch_to_rgb(0.55, 0.20, 27.0)
    accent = oklch_to_rgb(0.60, 0.14, (primary_hue + 50) % 360)

    # Tintado sutil del fondo para coherencia de marca
    body_bg = oklch_to_rgb(0.985, 0.008, primary_hue)
    muted_bg = oklch_to_rgb(0.95, 0.015, primary_hue)

    # Atributos de forma y densidad según arquetipo
    if archetype == BusinessArchetype.DASHBOARD:
        radius = "0.375rem"
        radius_sm = "0.25rem"
        radius_lg = "0.5rem"
        table_density = "table-sm"
        font = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'
    elif archetype == BusinessArchetype.STOREFRONT:
        radius = "0.75rem"
        radius_sm = "0.375rem"
        radius_lg = "1rem"
        table_density = "table"
        font = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'
    elif archetype == BusinessArchetype.CONTENT:
        radius = "0.5rem"
        radius_sm = "0.25rem"
        radius_lg = "0.75rem"
        table_density = "table"
        font = 'Georgia, Cambria, "Times New Roman", Times, serif'
    else:
        radius = "0.5rem"
        radius_sm = "0.25rem"
        radius_lg = "0.75rem"
        table_density = "table-sm"
        font = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'

    return BootstrapDesignTokens(
        primary_color=primary.to_hex(),
        primary_rgb=primary.to_rgb_str(),
        secondary_color=secondary.to_hex(),
        secondary_rgb=secondary.to_rgb_str(),
        success_color=success.to_hex(),
        success_rgb=success.to_rgb_str(),
        warning_color=warning.to_hex(),
        warning_rgb=warning.to_rgb_str(),
        danger_color=danger.to_hex(),
        danger_rgb=danger.to_rgb_str(),
        accent_color=accent.to_hex(),
        accent_rgb=accent.to_rgb_str(),
        body_bg=body_bg.to_hex(),
        card_bg="#ffffff",
        muted_bg=muted_bg.to_hex(),
        muted_text="#64748b",
        border_color="#e2e8f0",
        text_color="#1e293b",
        text_secondary="#475569",
        font_family_sans=font,
        font_heading=font,
        border_radius=radius,
        border_radius_sm=radius_sm,
        border_radius_lg=radius_lg,
        card_shadow="0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)",
        table_density_class=table_density,
        brand_personality=default_personality,
    )
