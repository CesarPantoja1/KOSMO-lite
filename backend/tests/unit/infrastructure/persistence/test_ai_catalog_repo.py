from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kosmo.contracts.ai.catalog import CatalogModel, ModelTier
from kosmo.infrastructure.persistence.postgres.models import AiCatalogModel
from kosmo.infrastructure.persistence.postgres.repositories.ai_catalog_repo import SqlAlchemyAiCatalogRepository

pytestmark = pytest.mark.unit


def _make_catalog_entity(
    model_id: str = "gpt-4o",
    provider: str = "openai",
    opencode_model_id: str = "gpt-4o",
    display_name: str = "GPT-4o",
    tier: ModelTier = ModelTier.BALANCED,
) -> CatalogModel:
    now = datetime.now(UTC)
    return CatalogModel(
        id="cat_01",
        provider=provider,
        model_id=model_id,
        opencode_model_id=opencode_model_id,
        display_name=display_name,
        tier=tier,
        context_window=128000,
        max_output_tokens=8192,
        supports_tools=True,
        supports_vision=True,
        opencode_compatible=True,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def _make_db_model(
    model_id: str = "gpt-4o",
    provider: str = "openai",
    opencode_model_id: str = "gpt-4o",
) -> AiCatalogModel:
    now = datetime.now(UTC)
    return AiCatalogModel(
        id="cat_01",
        provider=provider,
        model_id=model_id,
        opencode_model_id=opencode_model_id,
        display_name="GPT-4o",
        tier="balanced",
        context_window=128000,
        max_output_tokens=8192,
        supports_tools=True,
        supports_vision=True,
        opencode_compatible=True,
        is_active=True,
        is_deprecated=False,
        shutdown_date=None,
        metadata_json={},
        last_discovered_at=now,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_list_active_returns_entities() -> None:
    # Arrange
    db_model = _make_db_model()
    mock_session = MagicMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [db_model]
    mock_session.execute = AsyncMock(return_value=mock_result)

    session_maker = MagicMock(spec=async_sessionmaker)
    session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

    repo = SqlAlchemyAiCatalogRepository(session_maker)

    # Act
    models = await repo.list_active("openai")

    # Assert
    assert len(models) == 1
    assert models[0].model_id == "gpt-4o"
    assert models[0].provider == "openai"
    assert models[0].opencode_compatible is True


@pytest.mark.asyncio
async def test_get_by_provider_and_model_found() -> None:
    # Arrange
    db_model = _make_db_model("claude-3-7-sonnet-20250219", "anthropic", "claude-3-7-sonnet")
    mock_session = MagicMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = db_model
    mock_result.scalars.return_value.first.return_value = db_model
    mock_session.execute = AsyncMock(return_value=mock_result)

    session_maker = MagicMock(spec=async_sessionmaker)
    session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

    repo = SqlAlchemyAiCatalogRepository(session_maker)

    # Act
    model = await repo.get_by_provider_and_model("anthropic", "claude-3-7-sonnet")

    # Assert
    assert model is not None
    assert model.model_id == "claude-3-7-sonnet-20250219"
    assert model.opencode_model_id == "claude-3-7-sonnet"


@pytest.mark.asyncio
async def test_upsert_batch_executes_statement() -> None:
    # Arrange
    entity = _make_catalog_entity()
    mock_session = MagicMock(spec=AsyncSession)
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    session_maker = MagicMock(spec=async_sessionmaker)
    session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

    repo = SqlAlchemyAiCatalogRepository(session_maker)

    # Act
    await repo.upsert_batch([entity])

    # Assert
    mock_session.execute.assert_called_once()
    mock_session.commit.assert_called_once()
