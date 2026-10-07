from __future__ import annotations

import pytest

from kosmo.contracts.sdd.document import EARSPattern
from kosmo.contracts.sdd.ids import FeatureId, RequirementId
from kosmo.domain.sdd.requirements_markdown import (
    count_requirements,
    parse_requirement_from_markdown,
    parse_requirements_markdown,
    render_requirements_markdown,
)


@pytest.mark.unit
def test_parse_requirements_markdown_with_standard_headers() -> None:
    # Arrange
    md = (
        "### REQ-6.1 Descuento automático de stock\n\n"
        "**Basado en eventos**\n\n"
        "CUANDO el colaborador de tienda confirma un pedido, "
        "el sistema debe descontar automáticamente las cantidades.\n\n"
        "**Origen:** Se deriva de C06.\n\n"
        "**Criterios de aceptación**\n\n"
        "**Escenario: Descuento exitoso**\n"
        "- **Dado** que hay 10 unidades en stock\n"
        "- **Cuando** se confirma un pedido de 2 unidades\n"
        "- **Entonces** el stock queda en 8 unidades\n"
    )

    # Act
    reqs = parse_requirements_markdown(md, FeatureId("feat_06"), 6)

    # Assert
    assert len(reqs) == 1
    req = reqs[0]
    assert req.display_id == "REQ-6.1"
    assert req.title == "Descuento automático de stock"
    assert req.pattern == EARSPattern.event_driven
    assert "CUANDO el colaborador de tienda confirma" in req.statement
    assert req.origin == "Se deriva de C06."
    assert len(req.acceptance_criteria) == 1
    assert req.acceptance_criteria[0].scenario == "Descuento exitoso"
    assert req.acceptance_criteria[0].given == "hay 10 unidades en stock"
    assert req.acceptance_criteria[0].when == "se confirma un pedido de 2 unidades"
    assert req.acceptance_criteria[0].then == "el stock queda en 8 unidades"


@pytest.mark.unit
def test_parse_requirements_markdown_without_hash_prefix() -> None:
    # Arrange: snippet que empieza directamente con REQ- sin ###
    md = (
        "REQ-6.1 Descuento automático de stock\n"
        "Basado en eventos\n"
        "CUANDO el colaborador de tienda confirma un pedido, "
        "el sistema debe descontar automáticamente las cantidades.\n"
    )

    # Act
    reqs = parse_requirements_markdown(md, FeatureId("feat_06"), 6)

    # Assert
    assert len(reqs) == 1
    assert reqs[0].display_id == "REQ-6.1"
    assert reqs[0].pattern == EARSPattern.event_driven
    assert "CUANDO el colaborador de tienda" in reqs[0].statement


@pytest.mark.unit
def test_parse_requirement_from_markdown_single_item() -> None:
    # Arrange
    md = (
        "### REQ-2.1 Aplicar descuento\n\n"
        "**Opcional**\n\n"
        "EN CASO DE que el cliente tenga cupón, el sistema debe aplicar el descuento.\n"
    )

    # Act
    req = parse_requirement_from_markdown(md, FeatureId("feat_02"), 2, RequirementId("req_01"))

    # Assert
    assert req is not None
    assert req.display_id == "REQ-2.1"
    assert req.pattern == EARSPattern.optional
    assert "EN CASO DE que el cliente" in req.statement


@pytest.mark.unit
def test_render_and_count_requirements() -> None:
    # Arrange
    md = (
        "### REQ-1.1 Registro\n\n**Ubicuo**\n\nEl sistema debe registrar usuarios.\n\n"
        "### REQ-1.2 Login\n\n**Ubicuo**\n\nEl sistema debe permitir login.\n"
    )

    # Act
    count = count_requirements(md)
    reqs = parse_requirements_markdown(md, FeatureId("feat_01"), 1)
    rendered = render_requirements_markdown(reqs)

    # Assert
    assert count == 2
    assert len(reqs) == 2
    assert "### REQ-1.1 Registro" in rendered
    assert "### REQ-1.2 Login" in rendered


@pytest.mark.unit
def test_parse_requirements_markdown_with_injected_created_at() -> None:
    from datetime import UTC, datetime

    fixed_time = datetime(2026, 3, 15, 10, 30, 0, tzinfo=UTC)
    md = "### REQ-1.1 Registro\n\n**Ubicuo**\n\nEl sistema debe registrar usuarios.\n"

    reqs = parse_requirements_markdown(md, FeatureId("feat_01"), 1, created_at=fixed_time)
    assert len(reqs) == 1
    assert reqs[0].created_at == fixed_time

    single = parse_requirement_from_markdown(
        md,
        FeatureId("feat_01"),
        1,
        RequirementId("req_01"),
        created_at=fixed_time,
    )
    assert single is not None
    assert single.created_at == fixed_time
