from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from kosmo.contracts.sdd.codegen import ValidationStep
from kosmo.infrastructure.api.async_generation import with_heartbeat
from kosmo.infrastructure.api.main import app
from kosmo.infrastructure.sandbox.code_runner import SubprocessCodeRunner


@pytest.mark.asyncio
@pytest.mark.unit
async def test_active_sse_connections_gauge_lifecycle() -> None:
    # Arrange: snapshot baseline value via public sample value API
    initial_val = REGISTRY.get_sample_value("kosmo_active_sse_connections") or 0.0

    async def dummy_source():
        yield "data: 1\n\n"
        # Check gauge value inside active stream
        current = REGISTRY.get_sample_value("kosmo_active_sse_connections")
        assert current == initial_val + 1
        yield "data: 2\n\n"

    # Act: consume stream
    stream = with_heartbeat(dummy_source(), interval=1.0)
    items = []
    async for item in stream:
        items.append(item)

    # Assert: items received and gauge returned to baseline
    assert len(items) == 2
    assert REGISTRY.get_sample_value("kosmo_active_sse_connections") == initial_val


@pytest.mark.asyncio
@pytest.mark.unit
async def test_active_code_runners_gauge_lifecycle(tmp_path) -> None:
    # Arrange: snapshot baseline value via public sample value API
    initial_val = REGISTRY.get_sample_value("kosmo_active_code_runners") or 0.0
    runner = SubprocessCodeRunner()

    mock_proc = AsyncMock()
    mock_proc.pid = 1234
    mock_proc.returncode = 0

    async def fake_communicate():
        # Inside execution, runner metric must be incremented
        current = REGISTRY.get_sample_value("kosmo_active_code_runners")
        assert current == initial_val + 1
        return (b"ok", b"")

    mock_proc.communicate = fake_communicate

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await runner.run_step(
            workspace_dir=str(tmp_path),
            step=ValidationStep.TESTS,
            timeout_seconds=5,
        )

    # Assert: runner completed and gauge returned to baseline
    assert result.success is True
    assert REGISTRY.get_sample_value("kosmo_active_code_runners") == initial_val


@pytest.mark.unit
def test_metrics_endpoint_exposes_custom_gauges() -> None:
    # Arrange
    client = TestClient(app)

    # Act
    response = client.get("/metrics")

    # Assert
    assert response.status_code == 200
    assert "kosmo_active_sse_connections" in response.text
    assert "kosmo_active_code_runners" in response.text
