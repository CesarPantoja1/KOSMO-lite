from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class BusinessArchetype(StrEnum):
    STOREFRONT = "storefront"
    DASHBOARD = "dashboard"
    WORKFLOW = "workflow"
    SAAS_TOOL = "saas_tool"
    CONTENT = "content"


class ShellPattern(StrEnum):
    SIDEBAR = "sidebar"
    TOP_NAV = "top_nav"
    MINIMAL = "minimal"


class DataDensity(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class BootstrapDesignTokens:
    primary_color: str = "#0f766e"
    primary_rgb: str = "15, 118, 110"
    font_family_sans: str = 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif'
    border_radius: str = "0.5rem"
    border_radius_sm: str = "0.25rem"
    border_radius_lg: str = "0.75rem"
    card_shadow: str = "0 1px 3px rgba(0,0,0,0.05), 0 1px 2px rgba(0,0,0,0.03)"
    table_density_class: str = "table-sm"
    body_bg: str = "#f8fafc"
    # Semantic color palette
    secondary_color: str = "#64748b"
    secondary_rgb: str = "100, 116, 139"
    success_color: str = "#16a34a"
    success_rgb: str = "22, 163, 74"
    warning_color: str = "#d97706"
    warning_rgb: str = "217, 119, 6"
    danger_color: str = "#dc2626"
    danger_rgb: str = "220, 38, 38"
    accent_color: str = "#0ea5e9"
    accent_rgb: str = "14, 165, 233"
    # Surfaces and typography
    card_bg: str = "#ffffff"
    muted_bg: str = "#f1f5f9"
    muted_text: str = "#64748b"
    border_color: str = "#e2e8f0"
    text_color: str = "#1e293b"
    text_secondary: str = "#475569"
    font_heading: str = 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif'
    shadow_sm: str = "0 1px 2px rgba(0, 0, 0, 0.05)"
    shadow_lg: str = "0 10px 15px -3px rgba(0, 0, 0, 0.08), 0 4px 6px -2px rgba(0, 0, 0, 0.04)"
    brand_personality: str = "profesional, moderno"


@dataclass(frozen=True)
class UXContext:
    archetype: BusinessArchetype
    shell_pattern: ShellPattern
    data_density: DataDensity
    target_users: tuple[str, ...] = field(default_factory=tuple)
    primary_goals: tuple[str, ...] = field(default_factory=tuple)
    recommended_components: tuple[str, ...] = field(default_factory=tuple)
    prohibited_patterns: tuple[str, ...] = field(default_factory=tuple)
    layout_guideline: str = ""
    rationale: str = ""
    tokens: BootstrapDesignTokens = field(default_factory=BootstrapDesignTokens)


@dataclass(frozen=True)
class UXAnalysisOutput:
    ux_context: UXContext
    prompt_block: str
