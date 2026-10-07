from __future__ import annotations

import re

from kosmo.contracts.sdd.ux_context import BusinessArchetype
from kosmo.domain.codegen.palette_generator import generate_domain_tokens, oklch_to_rgb
from kosmo.domain.codegen.site_config import (
    format_design_tokens_ts,
    format_globals_css,
    format_site_config,
)

HEX_REGEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def test_oklch_to_rgb_conversion():
    # Pure white
    rgb_white = oklch_to_rgb(1.0, 0.0, 0.0)
    assert rgb_white.r == 255
    assert rgb_white.g == 255
    assert rgb_white.b == 255
    assert rgb_white.to_hex() == "#ffffff"

    # Pure black
    rgb_black = oklch_to_rgb(0.0, 0.0, 0.0)
    assert rgb_black.r == 0
    assert rgb_black.g == 0
    assert rgb_black.b == 0
    assert rgb_black.to_hex() == "#000000"

    # Mid tone with chroma
    rgb_mid = oklch_to_rgb(0.5, 0.15, 200.0)
    assert 0 <= rgb_mid.r <= 255
    assert 0 <= rgb_mid.g <= 255
    assert 0 <= rgb_mid.b <= 255
    assert HEX_REGEX.match(rgb_mid.to_hex())


def test_generate_domain_tokens_all_archetypes():
    for archetype in BusinessArchetype:
        tokens = generate_domain_tokens(archetype, seed_text="Clinica Dental Odontologia Citas")

        assert HEX_REGEX.match(tokens.primary_color)
        assert HEX_REGEX.match(tokens.secondary_color)
        assert HEX_REGEX.match(tokens.success_color)
        assert HEX_REGEX.match(tokens.warning_color)
        assert HEX_REGEX.match(tokens.danger_color)
        assert HEX_REGEX.match(tokens.accent_color)
        assert HEX_REGEX.match(tokens.body_bg)
        assert HEX_REGEX.match(tokens.card_bg)
        assert HEX_REGEX.match(tokens.border_color)

        assert tokens.font_family_sans
        assert tokens.font_heading
        assert tokens.border_radius
        assert tokens.border_radius_sm
        assert tokens.border_radius_lg
        assert tokens.card_shadow
        assert tokens.brand_personality


def test_generate_domain_tokens_differentiation_between_archetypes():
    dash_tokens = generate_domain_tokens(BusinessArchetype.DASHBOARD, seed_text="Finanzas")
    store_tokens = generate_domain_tokens(BusinessArchetype.STOREFRONT, seed_text="Restaurante")

    # Colors and borders should differ
    assert dash_tokens.primary_color != store_tokens.primary_color
    assert dash_tokens.table_density_class == "table-sm"
    assert store_tokens.table_density_class == "table"


def test_format_site_config():
    config_str = format_site_config(
        name="Clinica Odonto",
        description="Gestion dental",
        archetype="workflow",
        primary_color="#0f766e",
    )
    assert 'name: "Clinica Odonto"' in config_str
    assert 'primaryColor: "#0f766e"' in config_str


def test_format_design_tokens_ts():
    tokens = generate_domain_tokens(BusinessArchetype.DASHBOARD)
    tokens_ts = format_design_tokens_ts(tokens, domain="finanzas")

    assert "personality:" in tokens_ts
    assert 'domain: "finanzas"' in tokens_ts
    assert f'primary: "{tokens.primary_color}"' in tokens_ts
    assert f'secondary: "{tokens.secondary_color}"' in tokens_ts
    assert f'accent: "{tokens.accent_color}"' in tokens_ts


def test_format_globals_css():
    tokens = generate_domain_tokens(BusinessArchetype.STOREFRONT)
    css_str = format_globals_css(tokens)

    assert f"--app-primary: {tokens.primary_color};" in css_str
    assert f"--app-secondary: {tokens.secondary_color};" in css_str
    assert f"--app-success: {tokens.success_color};" in css_str
    assert f"--app-body-bg: {tokens.body_bg};" in css_str
    assert "--bs-primary: var(--app-primary);" in css_str
