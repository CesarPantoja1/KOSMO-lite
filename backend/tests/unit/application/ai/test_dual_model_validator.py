from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from kosmo.application.ai.dual_model_validator import DualModelValidator
from kosmo.contracts.ai.catalog import ModelTier, RawDiscoveredModel

pytestmark = pytest.mark.unit


def test_validator_approves_fully_compatible_model() -> None:
    # Arrange
    validator = DualModelValidator()
    raw = RawDiscoveredModel(
        provider="openai",
        model_id="gpt-4o",
        display_name="GPT-4o",
        context_window=128000,
    )
    opencode_models = {"gpt-4o", "gpt-4o-mini"}

    # Act
    model = validator.validate_and_classify(raw, opencode_models)

    # Assert
    assert model.is_active is True
    assert model.opencode_compatible is True
    assert model.tier == ModelTier.BALANCED
    assert model.opencode_model_id == "gpt-4o"


def test_validator_rejects_model_missing_from_opencode() -> None:
    # Arrange: un modelo nuevo en la API pero no presente en la versión fija de OpenCode
    validator = DualModelValidator()
    raw = RawDiscoveredModel(
        provider="anthropic",
        model_id="claude-future-frontier",
        display_name="Claude Future Frontier",
        context_window=200000,
    )
    opencode_models = {"claude-3-7-sonnet", "claude-3-5-sonnet"}

    # Act
    model = validator.validate_and_classify(raw, opencode_models)

    # Assert
    assert model.opencode_compatible is False
    assert model.is_active is False  # Invariante: no se expone al usuario


def test_validator_resolves_aliased_model_to_match_opencode() -> None:
    # Arrange: Anthropic envía fecha, OpenCode tiene el nombre canónico
    validator = DualModelValidator()
    raw = RawDiscoveredModel(
        provider="anthropic",
        model_id="claude-3-7-sonnet-20250219",
        display_name="Claude 3.7 Sonnet",
        context_window=200000,
    )
    opencode_models = {"claude-3-7-sonnet"}

    # Act
    model = validator.validate_and_classify(raw, opencode_models)

    # Assert
    assert model.opencode_model_id == "claude-3-7-sonnet"
    assert model.opencode_compatible is True
    assert model.is_active is True


def test_validator_rejects_obsolete_openai_o_models() -> None:
    # Arrange: Modelos de la serie 'o' de OpenAI deben quedar inactivos
    validator = DualModelValidator()
    for o_model in ("o1", "o1-mini", "o3", "o3-pro", "o3-mini", "o4-mini"):
        raw = RawDiscoveredModel(
            provider="openai",
            model_id=o_model,
            display_name=o_model,
            context_window=200000,
        )
        opencode_models = {o_model}
        model = validator.validate_and_classify(raw, opencode_models)
        assert model.is_active is False, f"Model {o_model} should be inactive"


def test_validator_marks_expired_shutdown_date_as_inactive() -> None:
    # Arrange
    validator = DualModelValidator()
    past_date = datetime.now(UTC).date() - timedelta(days=10)
    raw = RawDiscoveredModel(
        provider="openai",
        model_id="gpt-4-0314",
        display_name="GPT-4 (0314)",
        context_window=8192,
        shutdown_date=past_date,
    )
    opencode_models = {"gpt-4-0314"}

    # Act
    model = validator.validate_and_classify(raw, opencode_models)

    # Assert
    assert model.is_active is False
    assert model.is_deprecated is True


def test_validator_classifies_tiers_correctly() -> None:
    # Arrange
    validator = DualModelValidator()

    # Act & Assert
    assert validator.classify_tier("claude-3-opus") == ModelTier.FLAGSHIP
    assert validator.classify_tier("deepseek-reasoner") == ModelTier.REASONING
    assert validator.classify_tier("gpt-4o-mini") == ModelTier.FAST
    assert validator.classify_tier("gemini-1.5-flash") == ModelTier.BALANCED
    assert validator.classify_tier("claude-3-5-haiku") == ModelTier.FAST
