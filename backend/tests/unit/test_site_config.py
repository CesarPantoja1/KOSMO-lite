from __future__ import annotations

import pytest

from kosmo.domain.codegen.site_config import format_site_config

pytestmark = pytest.mark.unit


def test_format_site_config_default() -> None:
    # Arrange & Act
    content = format_site_config(name="Mi Proyecto", description="Una descripción")

    # Assert
    assert 'name: "Mi Proyecto"' in content
    assert 'description: "Una descripción"' in content
    assert 'archetype: "saas_tool"' in content
    assert 'primaryColor: "#0f766e"' in content
    assert "as const;" in content


def test_format_site_config_dashboard() -> None:
    # Arrange & Act
    content = format_site_config(
        name="GastoJusto",
        description="Gestión de finanzas",
        archetype="dashboard",
        primary_color="#4f46e5",
    )

    # Assert
    assert 'name: "GastoJusto"' in content
    assert 'archetype: "dashboard"' in content
    assert 'primaryColor: "#4f46e5"' in content


def test_format_site_config_escapes_quotes() -> None:
    # Arrange & Act
    content = format_site_config(
        name='App "Especial"',
        description='Descripción con "comillas"',
    )

    # Assert
    assert r'name: "App \"Especial\""' in content
    assert r'description: "Descripción con \"comillas\""' in content


def test_format_site_config_escapes_newlines_backslashes_and_control_characters() -> None:
    # Arrange & Act
    content = format_site_config(
        name="Portal \\ Operaciones",
        description='Primera línea\nSegunda línea con "comillas" y \\ barra.\tFin',
    )

    # Assert: el contenido se mantiene dentro de literales TypeScript de una sola línea.
    assert r'name: "Portal \\ Operaciones"' in content
    assert r'description: "Primera línea\nSegunda línea con \"comillas\" y \\ barra.\tFin"' in content
    assert content.count("\n") == 11
