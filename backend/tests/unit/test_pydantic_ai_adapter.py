from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from kosmo.infrastructure.llm.pydantic_ai_adapter import PydanticAILLMClient


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_with_retry_succeeds_first_attempt() -> None:
    client = PydanticAILLMClient(model=MagicMock(), retry_wait_seconds=0.001)
    call_count = 0

    async def _success() -> str:
        nonlocal call_count
        call_count += 1
        return "ok"

    result = await client._run_with_retry(_success)
    assert result == "ok"
    assert call_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_with_retry_recovers_after_transient_error() -> None:
    client = PydanticAILLMClient(model=MagicMock(), retry_wait_seconds=0.001)
    call_count = 0

    async def _transient_fail() -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("transient network timeout")
        return "recovered"

    result = await client._run_with_retry(_transient_fail)
    assert result == "recovered"
    assert call_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_with_retry_exhausts_attempts_and_reraises() -> None:
    client = PydanticAILLMClient(model=MagicMock(), retry_wait_seconds=0.001)
    call_count = 0

    async def _always_fails() -> str:
        nonlocal call_count
        call_count += 1
        raise ConnectionError("downstream service unreachable")

    with pytest.raises(ConnectionError, match="downstream service unreachable"):
        await client._run_with_retry(_always_fails)

    assert call_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_with_retry_does_not_retry_value_error() -> None:
    client = PydanticAILLMClient(model=MagicMock(), retry_wait_seconds=0.001)
    call_count = 0

    async def _value_error() -> str:
        nonlocal call_count
        call_count += 1
        raise ValueError("invalid prompt parameters")

    with pytest.raises(ValueError, match="invalid prompt parameters"):
        await client._run_with_retry(_value_error)

    # ValueError no debe reintentarse (falla inmediata)
    assert call_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_complete_records_llm_tokens() -> None:
    from unittest.mock import AsyncMock

    from kosmo.contracts.auth.context import current_user_id
    from kosmo.contracts.llm.ports import PromptTemplate
    from kosmo.contracts.telemetry import set_telemetry_provider
    from tests.unit.test_telemetry import FakeTelemetryProvider

    fake_provider = FakeTelemetryProvider()
    set_telemetry_provider(fake_provider)

    mock_agent = MagicMock()
    mock_run_result = MagicMock()
    mock_run_result.output = "test output"
    mock_run_result.model_name = "test-model"
    mock_usage = MagicMock()
    mock_usage.input_tokens = 10
    mock_usage.output_tokens = 20
    mock_usage.total_tokens = 30
    mock_run_result.usage.return_value = mock_usage
    mock_agent.run = AsyncMock(return_value=mock_run_result)

    client = PydanticAILLMClient(model=MagicMock())
    client._get_agent = MagicMock(return_value=mock_agent)

    token = current_user_id.set("usr_test_llm")
    try:
        response = await client.complete(PromptTemplate(system_prompt="sys", user_prompt="usr"))
        assert response.text == "test output"
        assert response.usage.total_tokens == 30

        assert len(fake_provider.llm_tokens) == 1
        assert fake_provider.llm_tokens[0] == (30, "test-model", "usr_test_llm")
    finally:
        current_user_id.reset(token)
        set_telemetry_provider(None)
