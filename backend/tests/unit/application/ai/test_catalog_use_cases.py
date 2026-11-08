from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from kosmo.application.ai.get_ai_catalog import GetAiCatalogUseCase
from kosmo.application.ai.sync_ai_catalog import SyncAiCatalogUseCase
from kosmo.contracts.ai.catalog import (
    AiCatalogRepository,
    CatalogModel,
    ModelDiscoveryAdapter,
    ModelTier,
    RawDiscoveredModel,
)
from kosmo.contracts.sdd.codegen import OpenCodeCatalogInspector

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_get_catalog_seeds_if_empty() -> None:
    # Arrange
    repo = MagicMock(spec=AiCatalogRepository)
    repo.list_active.side_effect = [
        [],  # primer llamado vacío
        [
            CatalogModel(
                id="cat_1",
                provider="openai",
                model_id="gpt-4o",
                opencode_model_id="gpt-4o",
                display_name="GPT-4o",
                tier=ModelTier.BALANCED,
            )
        ],
    ]
    repo.upsert_batch = AsyncMock()

    use_case = GetAiCatalogUseCase(repo)

    # Act
    providers = await use_case.execute()

    # Assert
    repo.upsert_batch.assert_called_once()
    assert len(providers) >= 1
    assert providers[0].value == "openai"
    assert len(providers[0].models) == 1
    assert providers[0].models[0].id == "gpt-4o"


@pytest.mark.asyncio
async def test_sync_catalog_filters_and_upserts() -> None:
    # Arrange
    repo = MagicMock(spec=AiCatalogRepository)
    repo.get_by_provider_and_model = AsyncMock(return_value=None)
    repo.upsert_batch = AsyncMock()
    repo.mark_unseen_as_retired = AsyncMock()

    inspector = MagicMock(spec=OpenCodeCatalogInspector)
    inspector.get_supported_models = AsyncMock(return_value={"anthropic": {"claude-3-7-sonnet"}})

    adapter = MagicMock(spec=ModelDiscoveryAdapter)
    adapter.provider = "anthropic"
    adapter.discover_models = AsyncMock(
        return_value=[
            RawDiscoveredModel(
                provider="anthropic",
                model_id="claude-3-7-sonnet-20250219",
                display_name="Claude 3.7 Sonnet",
                context_window=200000,
            ),
            RawDiscoveredModel(
                provider="anthropic",
                model_id="claude-future-unsupported",
                display_name="Claude Future",
                context_window=200000,
            ),
        ]
    )

    use_case = SyncAiCatalogUseCase(repo, inspector, [adapter])

    # Act
    result = await use_case.execute({"anthropic": "sk-ant-key"})

    # Assert
    assert result["upserted"] == 2
    assert result["active"] == 1  # Solo claude-3-7-sonnet es activo porque OpenCode lo soporta
    repo.upsert_batch.assert_called_once()
    repo.mark_unseen_as_retired.assert_called_once()


@pytest.mark.asyncio
async def test_get_catalog_curates_strictly_one_model_per_tier() -> None:
    # Arrange: Proveedor con múltiples modelos en el mismo tier
    repo = MagicMock(spec=AiCatalogRepository)
    repo.list_active = AsyncMock(
        return_value=[
            CatalogModel(
                id="cat_1",
                provider="openai",
                model_id="gpt-6.1-sol",
                opencode_model_id="gpt-6.1-sol",
                display_name="GPT-6.1 Sol",
                tier=ModelTier.FLAGSHIP,
                metadata_json={"release_date": "2026-09-29"},
            ),
            CatalogModel(
                id="cat_2",
                provider="openai",
                model_id="gpt-6.1-terra",
                opencode_model_id="gpt-6.1-terra",
                display_name="GPT-6.1 Terra",
                tier=ModelTier.BALANCED,
                metadata_json={"release_date": "2026-10-26"},
            ),
            CatalogModel(
                id="cat_3",
                provider="openai",
                model_id="gpt-5-pro",
                opencode_model_id="gpt-5-pro",
                display_name="GPT-5 Pro",
                tier=ModelTier.FLAGSHIP,
                metadata_json={"release_date": "2025-10-06"},
            ),
            CatalogModel(
                id="cat_4",
                provider="openai",
                model_id="o3-pro",
                opencode_model_id="o3-pro",
                display_name="o3-pro",
                tier=ModelTier.REASONING,
                metadata_json={"release_date": "2026-09-01"},
            ),
            CatalogModel(
                id="cat_5",
                provider="openai",
                model_id="gpt-6-luna",
                opencode_model_id="gpt-6-luna",
                display_name="GPT-6 Luna",
                tier=ModelTier.FAST,
                metadata_json={"release_date": "2026-09-22"},
            ),
            CatalogModel(
                id="cat_6",
                provider="openai",
                model_id="gpt-5.4-mini",
                opencode_model_id="gpt-5.4-mini",
                display_name="GPT-5.4 mini",
                tier=ModelTier.FAST,
                metadata_json={"release_date": "2026-03-17"},
            ),
        ]
    )

    use_case = GetAiCatalogUseCase(repo)

    # Act
    providers = await use_case.execute()

    # Assert: Exactamente 3 modelos (1 por cada tier: flagship, balanced, fast)
    openai_prov = next(p for p in providers if p.value == "openai")
    assert len(openai_prov.models) == 3
    tiers = [m.tier for m in openai_prov.models]
    assert tiers == ["flagship", "balanced", "fast"]
    # El modelo canónico de máxima capacidad es el seleccionado
    assert openai_prov.models[0].id == "gpt-6.1-sol"
    assert openai_prov.models[0].recommended is False
    assert openai_prov.models[0].description == ""
    assert openai_prov.models[1].id == "gpt-6.1-terra"
    assert openai_prov.models[2].id == "gpt-6-luna"
