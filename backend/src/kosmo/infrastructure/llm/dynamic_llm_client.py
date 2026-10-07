from __future__ import annotations

import asyncio
import hashlib
from collections import OrderedDict
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog

from kosmo.contracts.ai.ai_config import UserAiConfigRepository
from kosmo.contracts.auth import SecretCipher
from kosmo.contracts.auth.context import current_user_id
from kosmo.contracts.auth.secrets import EncryptedSecret
from kosmo.contracts.llm.ports import LLMClient, LLMResponse, PromptTemplate, ToolCallRecord
from kosmo.contracts.sdd.errors import AIProviderAuthError
from kosmo.infrastructure.llm.noop_adapter import NoopLLMClient
from kosmo.infrastructure.llm.pydantic_ai_adapter import PydanticAILLMClient, StreamedTypedResult

_log = structlog.get_logger(__name__)

_MAX_CACHED_LLM_CLIENTS = 64

_AUTH_ERROR_KEYWORDS = (
    "unauthorized",
    "authentication",
    "invalid_api_key",
    "api_key_invalid",
    "invalid api key",
    "incorrect api key",
    "permission_denied",
    "permissiondenied",
    "quota",
    "insufficient_quota",
    "credit",
    "401",
    "403",
)


def mask_user_id(user_id: str | None) -> str:
    """Enmascara y trunca un user_id para registrarlo en logs de forma anónima."""
    if not user_id:
        return "anonymous"
    cleaned = user_id.strip()
    if not cleaned:
        return "anonymous"
    if len(cleaned) <= 6:
        return f"{cleaned[0]}***{cleaned[-1]}" if len(cleaned) >= 2 else "***"
    return f"{cleaned[:4]}***{cleaned[-4:]}"


def is_ai_auth_error(exc: Exception) -> bool:
    if isinstance(exc, AIProviderAuthError):
        return True
    err_str = str(exc).lower()
    type_str = type(exc).__name__.lower()
    return any(keyword in err_str or keyword in type_str for keyword in _AUTH_ERROR_KEYWORDS)


def build_pydantic_ai_model(provider: str, model: str, api_key: str | None) -> object:
    prov = provider.lower()
    if prov == "deepseek":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai.settings import ModelSettings

        return OpenAIChatModel(
            model,
            provider=OpenAIProvider(base_url="https://api.deepseek.com", api_key=api_key),
            settings=ModelSettings(extra_body={"thinking": {"type": "disabled"}}),
        )
    if prov == "openai":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        return OpenAIChatModel(
            model,
            provider=OpenAIProvider(api_key=api_key),
        )
    if prov == "anthropic":
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        return AnthropicModel(
            model,
            provider=AnthropicProvider(api_key=api_key),
        )
    if prov in ("google", "gemini"):
        from pydantic_ai.models.google import GoogleModel
        from pydantic_ai.providers.google import GoogleProvider

        return GoogleModel(
            model,
            provider=GoogleProvider(api_key=api_key),
        )

    return f"{provider}:{model}"


class DynamicUserLLMClient(LLMClient):
    def __init__(
        self,
        config_repo: UserAiConfigRepository,
        cipher: SecretCipher,
        default_provider: str,
        default_model: str,
        default_api_key: str | None = None,
        max_concurrency: int = 15,
        cache_ttl_seconds: float = 60.0,
    ) -> None:
        self._config_repo = config_repo
        self._cipher = cipher
        self._default_provider = default_provider
        self._default_model = default_model
        self._default_api_key = default_api_key
        self._max_concurrency = max_concurrency
        self._cache_ttl_seconds = cache_ttl_seconds
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._config_cache: dict[str, tuple[float, str, str, str | None]] = {}
        self._config_locks: dict[str, asyncio.Lock] = {}
        self._clients: OrderedDict[tuple[str, str, str | None], PydanticAILLMClient] = OrderedDict()

    def invalidate_cache(self, user_id: str) -> None:
        """Invalida la configuración en cache de un usuario para refresco inmediato."""
        self._config_cache.pop(user_id, None)

    async def _resolve_config(self, user_id: str | None) -> tuple[str, str, str | None]:
        if not user_id:
            return (self._default_provider, self._default_model, self._default_api_key)

        now = asyncio.get_running_loop().time()
        cached = self._config_cache.get(user_id)
        if cached is not None and (now - cached[0]) < self._cache_ttl_seconds:
            return (cached[1], cached[2], cached[3])

        # Lock por usuario: evita thundering herd cuando el TTL vence con N coroutines
        # concurrentes del mismo usuario. El primer waiter renueva; los demás leen el valor
        # ya actualizado en el double-check posterior.
        if user_id not in self._config_locks:
            self._config_locks[user_id] = asyncio.Lock()
        async with self._config_locks[user_id]:
            # Double-check: otro waiter pudo haber renovado mientras esperábamos el lock.
            now = asyncio.get_running_loop().time()
            cached = self._config_cache.get(user_id)
            if cached is not None and (now - cached[0]) < self._cache_ttl_seconds:
                return (cached[1], cached[2], cached[3])

            provider = self._default_provider
            model = self._default_model
            api_key = self._default_api_key

            try:
                user_config = await self._config_repo.by_user_id(user_id)
                if user_config and user_config.encrypted_api_key is not None:
                    secret = (
                        user_config.encrypted_api_key
                        if isinstance(user_config.encrypted_api_key, EncryptedSecret)
                        else EncryptedSecret(ciphertext=user_config.encrypted_api_key)
                    )
                    raw_key = self._cipher.decrypt(secret)
                    provider_str = (
                        user_config.provider.value
                        if hasattr(user_config.provider, "value")
                        else str(user_config.provider)
                    )
                    provider = provider_str
                    model = user_config.model
                    api_key = raw_key.decode("utf-8")
            except Exception:
                _log.warning(
                    "dynamic_llm_client.resolve_user_config_failed",
                    user_id=mask_user_id(user_id),
                    exc_info=True,
                )

            self._config_cache[user_id] = (now, provider, model, api_key)
            return (provider, model, api_key)

    @staticmethod
    def _hash_api_key(key: str | None) -> str:
        if not key:
            return "none"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]

    async def _resolve_client(self) -> LLMClient:
        user_id = current_user_id.get()
        provider, model, api_key = await self._resolve_config(user_id)

        if provider.lower() == "noop":
            return NoopLLMClient()

        key_tuple = (provider, model, self._hash_api_key(api_key))
        client = self._clients.get(key_tuple)
        if client is not None:
            self._clients.move_to_end(key_tuple)
            return client
        pydantic_model = build_pydantic_ai_model(provider, model, api_key)
        client = PydanticAILLMClient(model=pydantic_model)
        self._clients[key_tuple] = client
        if len(self._clients) > _MAX_CACHED_LLM_CLIENTS:
            self._clients.popitem(last=False)
        return client

    async def complete(
        self,
        prompt: PromptTemplate,
        temperature: float = 0.3,
        max_tokens: int = 8192,
    ) -> LLMResponse:
        client = await self._resolve_client()
        async with self._semaphore:
            try:
                return await client.complete(prompt=prompt, temperature=temperature, max_tokens=max_tokens)
            except Exception as exc:
                if is_ai_auth_error(exc):
                    raise AIProviderAuthError() from exc
                raise

    async def complete_json(
        self,
        prompt: PromptTemplate,
        temperature: float = 0.1,
        max_tokens: int = 8192,
    ) -> LLMResponse:
        client = await self._resolve_client()
        async with self._semaphore:
            try:
                return await client.complete_json(prompt=prompt, temperature=temperature, max_tokens=max_tokens)
            except Exception as exc:
                if is_ai_auth_error(exc):
                    raise AIProviderAuthError() from exc
                raise

    async def complete_typed[T](
        self,
        prompt: PromptTemplate,
        output_type: type[T],
        temperature: float = 0.1,
        max_tokens: int = 8192,
    ) -> T:
        client = await self._resolve_client()
        async with self._semaphore:
            try:
                return await client.complete_typed(
                    prompt=prompt,
                    output_type=output_type,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as exc:
                if is_ai_auth_error(exc):
                    raise AIProviderAuthError() from exc
                raise

    @property
    def supports_native_tools(self) -> bool:
        return True

    async def complete_with_tools(
        self,
        prompt: PromptTemplate,
        tools: list[dict[str, Any]],
        tool_handler: Any,
        temperature: float = 0.1,
        max_tokens: int = 2000,
    ) -> tuple[str, list[ToolCallRecord]]:
        client = await self._resolve_client()
        if isinstance(client, PydanticAILLMClient):
            async with self._semaphore:
                try:
                    return await client.complete_with_tools(
                        prompt=prompt,
                        tools=tools,
                        tool_handler=tool_handler,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                except Exception as exc:
                    if is_ai_auth_error(exc):
                        raise AIProviderAuthError() from exc
                    raise
        return ("", [])

    @asynccontextmanager
    async def stream_typed[T](
        self,
        prompt: PromptTemplate,
        output_type: type[T],
        temperature: float = 0.1,
        max_tokens: int = 8192,
    ) -> AsyncGenerator[StreamedTypedResult[T]]:
        client = await self._resolve_client()
        stream_fn: Any = getattr(client, "stream_typed", None)
        if callable(stream_fn):
            try:
                async with stream_fn(
                    prompt=prompt,
                    output_type=output_type,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ) as streamed:  # type: ignore[reportUnknownVariableType]
                    yield streamed  # type: ignore[reportReturnType]
            except Exception as exc:
                if is_ai_auth_error(exc):
                    raise AIProviderAuthError() from exc
                raise
        else:
            result = await client.complete_typed(
                prompt=prompt,
                output_type=output_type,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            class _FallbackStreamed:
                def __init__(self, data: T):
                    self._data = data

                async def stream_text(self, *, delta: bool = False) -> AsyncIterator[str]:  # noqa: ARG002
                    content = getattr(self._data, "content", None)
                    if isinstance(content, str):
                        yield content
                    else:
                        yield str(self._data)

                async def get_data(self) -> T:
                    return self._data

            yield _FallbackStreamed(result)  # type: ignore[reportReturnType]
