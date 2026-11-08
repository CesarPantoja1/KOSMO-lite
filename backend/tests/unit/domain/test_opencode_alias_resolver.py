from __future__ import annotations

import pytest

from kosmo.domain.codegen.model_alias_resolver import OpenCodeModelAliasResolver

pytestmark = pytest.mark.unit


def test_resolve_anthropic_dated_aliases() -> None:
    # Arrange
    resolver = OpenCodeModelAliasResolver()

    # Act & Assert
    assert resolver.resolve("anthropic", "claude-3-7-sonnet-20250219") == "claude-3-7-sonnet"
    assert resolver.resolve("anthropic", "claude-3-5-sonnet-20241022") == "claude-3-5-sonnet"
    assert resolver.resolve("anthropic", "claude-3-5-haiku-20241022") == "claude-3-5-haiku"
    assert resolver.resolve("anthropic", "claude-3-opus-20240229") == "claude-3-opus"


def test_resolve_openai_snapshot_aliases() -> None:
    # Arrange
    resolver = OpenCodeModelAliasResolver()

    # Act & Assert
    assert resolver.resolve("openai", "gpt-4o-2024-08-06") == "gpt-4o"
    assert resolver.resolve("openai", "gpt-4o-mini-2024-07-18") == "gpt-4o-mini"
    assert resolver.resolve("openai", "o1-2024-12-17") == "o1"
    assert resolver.resolve("openai", "o3-mini-2025-01-31") == "o3-mini"


def test_resolve_google_prefixed_aliases() -> None:
    # Arrange
    resolver = OpenCodeModelAliasResolver()

    # Act & Assert
    assert resolver.resolve("google", "models/gemini-2.0-flash") == "gemini-2.0-flash"
    assert resolver.resolve("google", "models/gemini-1.5-pro") == "gemini-1.5-pro"
    assert resolver.resolve("google", "gemini-2.0-flash") == "gemini-2.0-flash"


def test_resolve_deepseek_aliases() -> None:
    # Arrange
    resolver = OpenCodeModelAliasResolver()

    # Act & Assert
    assert resolver.resolve("deepseek", "deepseek-chat") == "deepseek-chat"
    assert resolver.resolve("deepseek", "deepseek-reasoner") == "deepseek-reasoner"
    assert resolver.resolve("deepseek", "deepseek-flash") == "deepseek-flash"


def test_resolve_passthrough_unknown_clean_models() -> None:
    # Arrange
    resolver = OpenCodeModelAliasResolver()

    # Act & Assert
    assert resolver.resolve("openai", "o3") == "o3"
    assert resolver.resolve("anthropic", "claude-3-7-sonnet") == "claude-3-7-sonnet"
