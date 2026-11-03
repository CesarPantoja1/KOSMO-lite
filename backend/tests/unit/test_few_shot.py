from __future__ import annotations

import pytest

from kosmo.contracts.sdd.document import SpecPhase
from kosmo.domain.pipeline.phase_validators.discovery_validator import validate_discovery_structure
from kosmo.domain.sdd.document_converters import markdown_to_document
from kosmo.domain.sdd.few_shot.loader import load_example


@pytest.mark.unit
def test_load_discovery_example_is_valid() -> None:
    # Arrange & Act
    text = load_example(SpecPhase.DESCUBRIMIENTO)

    # Assert
    assert text is not None
    doc = markdown_to_document(text)
    result = validate_discovery_structure(doc)
    assert result.is_valid, f"Errores: {result.errors}"


@pytest.mark.unit
def test_load_features_example_non_empty() -> None:
    # Arrange & Act
    text = load_example(SpecPhase.CARACTERISTICAS)

    # Assert
    assert text is not None
    assert "C01" in text
    assert "C02" in text


@pytest.mark.unit
def test_load_ears_example_is_valid() -> None:
    # Arrange & Act
    text = load_example(SpecPhase.REQUISITOS)

    # Assert
    assert text is not None
    assert "REQ-1.1" in text
    assert "REQ-1.2" in text


@pytest.mark.unit
def test_load_example_unknown_phase_returns_none() -> None:
    # Arrange & Act
    result = load_example(SpecPhase.IMPLEMENTACION)

    # Assert
    assert result is None


@pytest.mark.unit
def test_discovery_mode_system_prompt_includes_few_shot() -> None:
    # Arrange
    from kosmo.domain.pipeline.phase_modes.discovery_mode import DiscoveryMode

    mode = DiscoveryMode()

    # Act
    prompt = mode.system_prompt

    # Assert
    assert "Ejemplo de referencia" in prompt
    assert "Visión del producto" in prompt


@pytest.mark.unit
def test_features_mode_system_prompt_includes_few_shot() -> None:
    # Arrange
    from kosmo.domain.pipeline.phase_modes.features_mode import FeaturesMode

    mode = FeaturesMode()

    # Act
    prompt = mode.system_prompt

    # Assert
    assert "Ejemplo de referencia" in prompt
    assert "C01" in prompt


@pytest.mark.unit
def test_ears_mode_system_prompt_includes_few_shot() -> None:
    # Arrange
    from kosmo.domain.pipeline.phase_modes.ears_mode import EARSMode

    mode = EARSMode()

    # Act
    prompt = mode.system_prompt

    # Assert
    assert "Ejemplo de referencia" in prompt
    assert "REQ-1.1" in prompt
