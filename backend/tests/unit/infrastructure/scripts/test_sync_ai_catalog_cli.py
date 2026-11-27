from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kosmo.infrastructure.api.composition import AppContainer
from kosmo.infrastructure.scripts.sync_ai_catalog import _run, main

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_sync_cli_success() -> None:
    # Arrange
    mock_components = MagicMock(spec=AppContainer)
    mock_components.close = AsyncMock()

    mock_use_case = MagicMock()
    mock_use_case.execute = AsyncMock(return_value={"upserted": 5, "active": 3})

    with (
        patch(
            "kosmo.infrastructure.scripts.sync_ai_catalog.build_app_components",
            return_value=mock_components,
        ),
        patch(
            "kosmo.infrastructure.scripts.sync_ai_catalog.build_sync_ai_catalog_use_case",
            return_value=mock_use_case,
        ),
    ):
        code = await _run()

    # Assert
    assert code == 0
    mock_use_case.execute.assert_called_once()
    mock_components.close.assert_called_once()


@pytest.mark.asyncio
async def test_sync_cli_failure_returns_one() -> None:
    # Arrange
    mock_components = MagicMock(spec=AppContainer)
    mock_components.close = AsyncMock()

    mock_use_case = MagicMock()
    mock_use_case.execute = AsyncMock(side_effect=RuntimeError("DB unreachable"))

    with (
        patch(
            "kosmo.infrastructure.scripts.sync_ai_catalog.build_app_components",
            return_value=mock_components,
        ),
        patch(
            "kosmo.infrastructure.scripts.sync_ai_catalog.build_sync_ai_catalog_use_case",
            return_value=mock_use_case,
        ),
    ):
        code = await _run()

    # Assert
    assert code == 1
    mock_components.close.assert_called_once()


def test_main_entrypoint() -> None:
    with patch("kosmo.infrastructure.scripts.sync_ai_catalog._run", return_value=0):
        assert main() == 0
