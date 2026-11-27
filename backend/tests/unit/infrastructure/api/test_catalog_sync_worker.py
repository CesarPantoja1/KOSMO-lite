from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kosmo.config import Settings
from kosmo.infrastructure.api.catalog_sync_worker import run_catalog_sync_worker
from kosmo.infrastructure.api.composition import AppContainer

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_worker_disabled_returns_immediately() -> None:
    # Arrange
    components = MagicMock(spec=AppContainer)
    settings = MagicMock(spec=Settings)
    settings.ai_catalog_sync_enabled = False

    # Act
    with patch("kosmo.infrastructure.api.catalog_sync_worker.asyncio.sleep") as mock_sleep:
        await run_catalog_sync_worker(components, settings)
        mock_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_worker_runs_and_waits_interval() -> None:
    # Arrange
    components = MagicMock(spec=AppContainer)
    settings = MagicMock(spec=Settings)
    settings.ai_catalog_sync_enabled = True
    settings.ai_catalog_sync_initial_delay_seconds = 10.0
    settings.ai_catalog_sync_interval_hours = 24
    settings.llm_api_key = None
    settings.llm_provider = "noop"

    mock_use_case = MagicMock()
    mock_use_case.execute = AsyncMock(return_value={"upserted": 10, "active": 8})

    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 2:
            raise asyncio.CancelledError()

    with (
        patch(
            "kosmo.infrastructure.api.catalog_sync_worker.build_sync_ai_catalog_use_case",
            return_value=mock_use_case,
        ),
        patch("kosmo.infrastructure.api.catalog_sync_worker.asyncio.sleep", side_effect=fake_sleep),
        pytest.raises(asyncio.CancelledError),
    ):
        await run_catalog_sync_worker(components, settings)

    # Assert
    assert sleep_calls == [10.0, 24 * 3600.0]
    mock_use_case.execute.assert_called_once_with(provider_keys=None)


@pytest.mark.asyncio
async def test_worker_retries_with_backoff_on_failure() -> None:
    # Arrange
    components = MagicMock(spec=AppContainer)
    settings = MagicMock(spec=Settings)
    settings.ai_catalog_sync_enabled = True
    settings.ai_catalog_sync_initial_delay_seconds = 0.0
    settings.ai_catalog_sync_interval_hours = 24
    settings.llm_api_key = None
    settings.llm_provider = "noop"

    mock_use_case = MagicMock()
    mock_use_case.execute = AsyncMock(side_effect=RuntimeError("OpenCode connection error"))

    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 1:
            raise asyncio.CancelledError()

    with (
        patch(
            "kosmo.infrastructure.api.catalog_sync_worker.build_sync_ai_catalog_use_case",
            return_value=mock_use_case,
        ),
        patch("kosmo.infrastructure.api.catalog_sync_worker.asyncio.sleep", side_effect=fake_sleep),
        pytest.raises(asyncio.CancelledError),
    ):
        await run_catalog_sync_worker(components, settings)

    # Assert retry backoff was invoked (initial retry_delay = 60.0)
    assert sleep_calls == [60.0]
