from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kosmo.contracts.ai.ai_config import AIProvider, UserAiConfig
from kosmo.contracts.auth.secrets import EncryptedSecret
from kosmo.contracts.llm.ports import LLMResponse, PromptTemplate
from kosmo.contracts.sdd.errors import AIProviderAuthError
from kosmo.infrastructure.llm.dynamic_llm_client import DynamicUserLLMClient, current_user_id, mask_user_id


@pytest.fixture
def mock_repo():
    return AsyncMock()


@pytest.fixture
def mock_cipher():
    cipher = MagicMock()
    cipher.decrypt.side_effect = lambda secret: secret.ciphertext.replace(b"enc_", b"")
    return cipher


@pytest.fixture
def dynamic_client(mock_repo, mock_cipher):
    return DynamicUserLLMClient(
        config_repo=mock_repo,
        cipher=mock_cipher,
        default_provider="openai",
        default_model="gpt-4o",
        default_api_key="sk-default-key",
    )


@pytest.mark.asyncio
async def test_dynamic_client_resolves_user_credentials(dynamic_client, mock_repo):
    # Arrange
    user_id = "usr_test_123"
    current_user_id.set(user_id)

    mock_repo.by_user_id.return_value = UserAiConfig(
        user_id=user_id,
        provider=AIProvider.DEEPSEEK,
        model="deepseek-v4-flash",
        encrypted_api_key=EncryptedSecret(ciphertext=b"enc_sk-user-deepseek-key"),
        is_custom=True,
    )

    mock_pydantic_client = AsyncMock()
    mock_pydantic_client.complete.return_value = LLMResponse(text="response from user deepseek")

    with patch("kosmo.infrastructure.llm.dynamic_llm_client.PydanticAILLMClient", return_value=mock_pydantic_client):
        # Act
        prompt = PromptTemplate(system_prompt="sys", user_prompt="hello")
        res = await dynamic_client.complete(prompt)

        # Assert
        assert res.text == "response from user deepseek"
        mock_repo.by_user_id.assert_called_once_with(user_id)


@pytest.mark.asyncio
async def test_dynamic_client_falls_back_when_no_user_config(dynamic_client, mock_repo):
    # Arrange
    current_user_id.set(None)
    mock_repo.by_user_id.return_value = None

    mock_pydantic_client = AsyncMock()
    mock_pydantic_client.complete.return_value = LLMResponse(text="response from default")

    with patch("kosmo.infrastructure.llm.dynamic_llm_client.PydanticAILLMClient", return_value=mock_pydantic_client):
        # Act
        prompt = PromptTemplate(system_prompt="sys", user_prompt="hello")
        res = await dynamic_client.complete(prompt)

        # Assert
        assert res.text == "response from default"
        mock_repo.by_user_id.assert_not_called()


@pytest.mark.asyncio
async def test_dynamic_client_stream_typed_delegates_to_resolved_client(dynamic_client, mock_repo):
    # Arrange
    user_id = "usr_test_stream"
    current_user_id.set(user_id)

    mock_repo.by_user_id.return_value = None

    class FakeStreamedResult:
        async def stream_text(self, *, delta: bool = False):  # noqa: ARG002
            yield "chunk 1"
            yield "chunk 2"

        async def get_data(self):
            return "final result"

    @asynccontextmanager
    async def fake_stream_typed(*_args, **_kwargs):
        yield FakeStreamedResult()

    mock_pydantic_client = AsyncMock()
    mock_pydantic_client.stream_typed = fake_stream_typed

    with patch("kosmo.infrastructure.llm.dynamic_llm_client.PydanticAILLMClient", return_value=mock_pydantic_client):
        # Act
        prompt = PromptTemplate(system_prompt="sys", user_prompt="hello")
        chunks = []
        async with dynamic_client.stream_typed(prompt=prompt, output_type=str) as streamed:
            async for chunk in streamed.stream_text(delta=True):
                chunks.append(chunk)
            result = await streamed.get_data()

        # Assert
        assert chunks == ["chunk 1", "chunk 2"]
        assert result == "final result"


@pytest.mark.asyncio
async def test_dynamic_client_stream_typed_maps_auth_error(dynamic_client, mock_repo):
    # Arrange
    current_user_id.set(None)
    mock_repo.by_user_id.return_value = None

    @asynccontextmanager
    async def fake_stream_typed_error(*_args, **_kwargs):
        raise ValueError("401 unauthorized invalid_api_key")
        yield  # type: ignore[unreachable]

    mock_pydantic_client = AsyncMock()
    mock_pydantic_client.stream_typed = fake_stream_typed_error

    with patch("kosmo.infrastructure.llm.dynamic_llm_client.PydanticAILLMClient", return_value=mock_pydantic_client):
        prompt = PromptTemplate(system_prompt="sys", user_prompt="hello")
        with pytest.raises(AIProviderAuthError):
            async with dynamic_client.stream_typed(prompt=prompt, output_type=str):
                pass


@pytest.mark.asyncio
async def test_dynamic_client_stream_typed_with_noop(mock_repo, mock_cipher):
    # Arrange
    client = DynamicUserLLMClient(
        config_repo=mock_repo,
        cipher=mock_cipher,
        default_provider="noop",
        default_model="noop",
    )
    current_user_id.set(None)

    prompt = PromptTemplate(system_prompt="sys", user_prompt="hello")
    chunks = []
    async with client.stream_typed(prompt=prompt, output_type=str) as streamed:
        async for chunk in streamed.stream_text(delta=True):
            chunks.append(chunk)
        result = await streamed.get_data()

    assert len(chunks) > 0
    assert result is not None


@pytest.mark.asyncio
async def test_dynamic_client_caches_user_credentials(dynamic_client, mock_repo):
    user_id = "usr_cached"
    current_user_id.set(user_id)

    mock_repo.by_user_id.return_value = UserAiConfig(
        user_id=user_id,
        provider=AIProvider.DEEPSEEK,
        model="deepseek-v4-flash",
        encrypted_api_key=EncryptedSecret(ciphertext=b"enc_sk-user-key"),
        is_custom=True,
    )

    mock_pydantic_client = AsyncMock()
    mock_pydantic_client.complete.return_value = LLMResponse(text="ok")

    with patch("kosmo.infrastructure.llm.dynamic_llm_client.PydanticAILLMClient", return_value=mock_pydantic_client):
        prompt = PromptTemplate(system_prompt="sys", user_prompt="hello")
        await dynamic_client.complete(prompt)
        await dynamic_client.complete(prompt)

        assert mock_repo.by_user_id.call_count == 1


@pytest.mark.asyncio
async def test_dynamic_client_invalidate_cache(dynamic_client, mock_repo):
    user_id = "usr_invalidate"
    current_user_id.set(user_id)

    mock_repo.by_user_id.return_value = UserAiConfig(
        user_id=user_id,
        provider=AIProvider.DEEPSEEK,
        model="deepseek-v4-flash",
        encrypted_api_key=EncryptedSecret(ciphertext=b"enc_sk-user-key"),
        is_custom=True,
    )

    mock_pydantic_client = AsyncMock()
    mock_pydantic_client.complete.return_value = LLMResponse(text="ok")

    with patch("kosmo.infrastructure.llm.dynamic_llm_client.PydanticAILLMClient", return_value=mock_pydantic_client):
        prompt = PromptTemplate(system_prompt="sys", user_prompt="hello")
        await dynamic_client.complete(prompt)
        assert mock_repo.by_user_id.call_count == 1

        dynamic_client.invalidate_cache(user_id)
        await dynamic_client.complete(prompt)
        assert mock_repo.by_user_id.call_count == 2


@pytest.mark.asyncio
async def test_dynamic_client_semaphore_limits_concurrency(mock_repo, mock_cipher):
    import asyncio

    client = DynamicUserLLMClient(
        config_repo=mock_repo,
        cipher=mock_cipher,
        default_provider="openai",
        default_model="gpt-4o",
        default_api_key="sk-test",
        max_concurrency=2,
    )
    current_user_id.set(None)

    active_count = 0
    max_active = 0
    lock = asyncio.Lock()

    async def slow_complete(*_args, **_kwargs):
        nonlocal active_count, max_active
        async with lock:
            active_count += 1
            if active_count > max_active:
                max_active = active_count
        await asyncio.sleep(0.05)
        async with lock:
            active_count -= 1
        return LLMResponse(text="done")

    mock_pydantic_client = AsyncMock()
    mock_pydantic_client.complete.side_effect = slow_complete

    with patch("kosmo.infrastructure.llm.dynamic_llm_client.PydanticAILLMClient", return_value=mock_pydantic_client):
        prompt = PromptTemplate(system_prompt="sys", user_prompt="hello")
        tasks = [asyncio.create_task(client.complete(prompt)) for _ in range(6)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 6
        assert max_active <= 2


@pytest.mark.asyncio
async def test_dynamic_client_caches_with_hashed_api_key(dynamic_client, mock_repo):
    import hashlib

    user_id = "usr_key_hash_test"
    current_user_id.set(user_id)
    raw_api_key = "sk-super-secret-user-key-999"

    mock_repo.by_user_id.return_value = UserAiConfig(
        user_id=user_id,
        provider=AIProvider.OPENAI,
        model="gpt-4o",
        encrypted_api_key=EncryptedSecret(ciphertext=b"enc_" + raw_api_key.encode("utf-8")),
        is_custom=True,
    )

    mock_pydantic_client = AsyncMock()
    mock_pydantic_client.complete.return_value = LLMResponse(text="ok")

    with patch("kosmo.infrastructure.llm.dynamic_llm_client.PydanticAILLMClient", return_value=mock_pydantic_client):
        prompt = PromptTemplate(system_prompt="sys", user_prompt="hello")
        await dynamic_client.complete(prompt)

        cached_keys = list(dynamic_client._clients.keys())
        assert len(cached_keys) == 1
        provider, model, key_hash = cached_keys[0]

        assert provider == "openai"
        assert model == "gpt-4o"
        assert raw_api_key not in key_hash
        assert raw_api_key not in str(cached_keys)
        expected_hash = hashlib.sha256(raw_api_key.encode("utf-8")).hexdigest()[:16]
        assert key_hash == expected_hash


@pytest.mark.asyncio
async def test_dynamic_client_stream_typed_does_not_acquire_semaphore(dynamic_client, mock_repo):
    """stream_typed no adquiere el semáforo para no bloquear llamadas no-streaming."""
    # Arrange
    events: list[str] = []
    original_resolve = dynamic_client._resolve_client

    async def traced_resolve():
        events.append("resolve")
        return await original_resolve()

    original_acquire = dynamic_client._semaphore.acquire

    async def traced_acquire():
        events.append("acquire")
        return await original_acquire()

    dynamic_client._resolve_client = traced_resolve
    dynamic_client._semaphore.acquire = traced_acquire

    current_user_id.set(None)
    mock_repo.by_user_id.return_value = None

    class FakeStreamedResult:
        async def stream_text(self, *, delta: bool = False):  # noqa: ARG002
            yield "chunk"

        async def get_data(self):
            return "done"

    @asynccontextmanager
    async def fake_stream_typed(*_args, **_kwargs):
        yield FakeStreamedResult()

    mock_pydantic_client = AsyncMock()
    mock_pydantic_client.stream_typed = fake_stream_typed

    with patch("kosmo.infrastructure.llm.dynamic_llm_client.PydanticAILLMClient", return_value=mock_pydantic_client):
        prompt = PromptTemplate(system_prompt="sys", user_prompt="hello")
        async with dynamic_client.stream_typed(prompt=prompt, output_type=str) as streamed:
            async for _ in streamed.stream_text():
                pass

    # Assert: client resolves, but semaphore is never acquired for streaming
    assert events == ["resolve"]


def test_mask_user_id():
    assert mask_user_id(None) == "anonymous"
    assert mask_user_id("") == "anonymous"
    assert mask_user_id("   ") == "anonymous"
    assert mask_user_id("x") == "***"
    assert mask_user_id("ab") == "a***b"
    assert mask_user_id("usr123") == "u***3"
    assert mask_user_id("usr_12345678") == "usr_***5678"
    assert mask_user_id("01HXYZ1234567890ABCDEFGHJK") == "01HX***GHJK"


@pytest.mark.asyncio
async def test_dynamic_client_logs_masked_user_id_on_failure(dynamic_client, mock_repo):
    # Arrange
    user_id = "usr_confidential_987654"
    mock_repo.by_user_id.side_effect = RuntimeError("Database offline")

    with patch("kosmo.infrastructure.llm.dynamic_llm_client._log") as mock_log:
        # Act
        provider, model, key = await dynamic_client._resolve_config(user_id)

        # Assert fallback values
        assert provider == "openai"
        assert model == "gpt-4o"
        assert key == "sk-default-key"

        # Assert log was called with masked user_id
        mock_log.warning.assert_called_once()
        call_args, call_kwargs = mock_log.warning.call_args
        assert call_args[0] == "dynamic_llm_client.resolve_user_config_failed"
        assert call_kwargs["user_id"] == "usr_***7654"
        assert user_id not in str(call_kwargs)
