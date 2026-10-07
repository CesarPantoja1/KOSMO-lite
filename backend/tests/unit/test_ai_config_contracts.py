from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from kosmo.contracts.ai.ai_config import (
    DEFAULT_AI_MODEL,
    DEFAULT_AI_PROVIDER,
    SUPPORTED_MODELS_PER_PROVIDER,
    SUPPORTED_PROVIDERS,
    AIConfigError,
    AIConfigView,
    AIConnectionTester,
    AIConnectionTestError,
    AIModelInfo,
    AIProvider,
    AIProviderInfo,
    InvalidAIModelError,
    InvalidAIProviderError,
    InvalidApiKeyError,
    SaveAIConfigInput,
    TestAIConnectionInput,
    TestAIConnectionResult,
    UserAiConfig,
    UserAiConfigRepository,
    mask_api_key,
)
from kosmo.contracts.auth.secrets import EncryptedSecret


@pytest.mark.unit
def test_ai_provider_enum_values() -> None:
    assert AIProvider.OPENAI == "openai"
    assert AIProvider.ANTHROPIC == "anthropic"
    assert AIProvider.GOOGLE == "google"
    assert AIProvider.DEEPSEEK == "deepseek"
    assert AIProvider.CUSTOM == "custom"
    assert AIProvider.KOSMO_DEFAULT == "kosmo_default"


@pytest.mark.unit
def test_supported_models_per_provider() -> None:
    for provider in AIProvider:
        assert provider in SUPPORTED_MODELS_PER_PROVIDER
        models = SUPPORTED_MODELS_PER_PROVIDER[provider]
        assert isinstance(models, tuple)
        assert len(models) > 0


@pytest.mark.unit
def test_supported_providers_catalog_structure() -> None:
    # Arrange & Act
    provider_values = {p.value for p in SUPPORTED_PROVIDERS}

    # Assert
    assert provider_values == {"openai", "anthropic", "google", "deepseek"}
    for provider in SUPPORTED_PROVIDERS:
        assert isinstance(provider, AIProviderInfo)
        assert provider.label
        assert len(provider.models) > 0
        for model in provider.models:
            assert isinstance(model, AIModelInfo)
            assert model.id
            assert model.display_name
            assert model.tier in ("flagship", "balanced", "fast")


@pytest.mark.unit
def test_supported_providers_no_internal_providers() -> None:
    # Arrange & Act
    exposed_values = {p.value for p in SUPPORTED_PROVIDERS}

    # Assert
    assert "kosmo_default" not in exposed_values
    assert "custom" not in exposed_values


@pytest.mark.unit
def test_mask_api_key() -> None:
    assert mask_api_key(None) is None
    assert mask_api_key("") is None
    assert mask_api_key("   ") is None
    assert mask_api_key("abc") == "••••••••"
    assert mask_api_key("1234") == "••••••••"
    assert mask_api_key("sk-ant-api03-abcdef1234") == "••••••••1234"
    assert mask_api_key("sk-openai-key-9999") == "••••••••9999"


@pytest.mark.unit
def test_user_ai_config_instantiation_and_defaults() -> None:
    config = UserAiConfig(user_id="usr_123")

    assert config.user_id == "usr_123"
    assert config.provider == DEFAULT_AI_PROVIDER
    assert config.model == DEFAULT_AI_MODEL
    assert config.encrypted_api_key is None
    assert config.is_custom is False
    assert not config.has_api_key
    assert config.created_at <= datetime.now(UTC)
    assert config.updated_at is None


@pytest.mark.unit
def test_user_ai_config_immutability() -> None:
    config = UserAiConfig(user_id="usr_123")
    with pytest.raises(FrozenInstanceError):
        config.model = "gpt-4o"  # type: ignore[misc]


@pytest.mark.unit
def test_user_ai_config_with_custom_secret_and_to_view() -> None:
    secret = EncryptedSecret(ciphertext=b"encrypted_ciphertext_data")
    updated_time = datetime(2026, 8, 24, 15, 0, tzinfo=UTC)
    config = UserAiConfig(
        user_id="usr_456",
        provider=AIProvider.ANTHROPIC,
        model="claude-3-5-sonnet-20241022",
        encrypted_api_key=secret,
        is_custom=True,
        updated_at=updated_time,
    )

    assert config.has_api_key is True
    view = config.to_view(masked_key="••••••••5678")

    assert isinstance(view, AIConfigView)
    assert view.provider == AIProvider.ANTHROPIC
    assert view.model == "claude-3-5-sonnet-20241022"
    assert view.is_custom is True
    assert view.has_api_key is True
    assert view.masked_key == "••••••••5678"
    assert view.updated_at == updated_time


@pytest.mark.unit
def test_save_ai_config_input_validation() -> None:
    # Caso válido
    valid_input = SaveAIConfigInput(
        provider=AIProvider.OPENAI,
        model="gpt-4o",
        api_key="sk-1234567890",
    )
    assert valid_input.provider == AIProvider.OPENAI
    assert valid_input.model == "gpt-4o"
    assert valid_input.api_key == "sk-1234567890"

    # Modelo vacío
    with pytest.raises(InvalidAIModelError, match="El nombre del modelo no puede estar vacío"):
        SaveAIConfigInput(provider=AIProvider.OPENAI, model="", api_key="sk-12345")

    with pytest.raises(InvalidAIModelError, match="El nombre del modelo no puede estar vacío"):
        SaveAIConfigInput(provider=AIProvider.OPENAI, model="   ", api_key="sk-12345")

    # Modelo demasiado largo (> 100 chars)
    with pytest.raises(InvalidAIModelError, match="El nombre del modelo no puede exceder los 100 caracteres"):
        SaveAIConfigInput(provider=AIProvider.OPENAI, model="m" * 101, api_key="sk-12345")

    # API Key vacía
    with pytest.raises(InvalidApiKeyError, match="La clave de API no puede estar vacía"):
        SaveAIConfigInput(provider=AIProvider.OPENAI, model="gpt-4o", api_key="")

    with pytest.raises(InvalidApiKeyError, match="La clave de API no puede estar vacía"):
        SaveAIConfigInput(provider=AIProvider.OPENAI, model="gpt-4o", api_key="   ")

    # API Key demasiado larga (> 500 chars)
    with pytest.raises(InvalidApiKeyError, match="La clave de API no puede exceder los 500 caracteres"):
        SaveAIConfigInput(provider=AIProvider.OPENAI, model="gpt-4o", api_key="k" * 501)


@pytest.mark.unit
def test_test_ai_connection_input_validation() -> None:
    # Caso válido con clave
    input_with_key = TestAIConnectionInput(
        provider=AIProvider.GOOGLE,
        model="gemini-3.8-flash",
        api_key="AIzaSy...",
    )
    assert input_with_key.provider == AIProvider.GOOGLE
    assert input_with_key.api_key == "AIzaSy..."

    # Caso válido sin clave (prueba con clave persistida)
    input_no_key = TestAIConnectionInput(
        provider=AIProvider.GOOGLE,
        model="gemini-3.8-flash",
    )
    assert input_no_key.api_key is None

    # Modelo inválido
    with pytest.raises(InvalidAIModelError):
        TestAIConnectionInput(provider=AIProvider.GOOGLE, model="")

    with pytest.raises(InvalidAIModelError):
        TestAIConnectionInput(provider=AIProvider.GOOGLE, model="x" * 101)

    # Clave demasiado larga
    with pytest.raises(InvalidApiKeyError):
        TestAIConnectionInput(provider=AIProvider.GOOGLE, model="gemini-3.8-flash", api_key="k" * 501)


@pytest.mark.unit
def test_test_ai_connection_result() -> None:
    result = TestAIConnectionResult(
        is_connected=True,
        detected_model="claude-3-5-sonnet-20241022",
        message="Conexión exitosa",
    )
    assert result.is_connected is True
    assert result.detected_model == "claude-3-5-sonnet-20241022"
    assert result.message == "Conexión exitosa"


@pytest.mark.unit
def test_ai_config_exceptions_hierarchy() -> None:
    assert issubclass(InvalidAIProviderError, AIConfigError)
    assert issubclass(InvalidAIModelError, AIConfigError)
    assert issubclass(InvalidApiKeyError, AIConfigError)
    assert issubclass(AIConnectionTestError, AIConfigError)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_repository_and_tester_protocols() -> None:
    class FakeUserAiConfigRepo(UserAiConfigRepository):
        def __init__(self) -> None:
            self._storage: dict[str, UserAiConfig] = {}

        async def by_user_id(self, user_id: str) -> UserAiConfig | None:
            return self._storage.get(user_id)

        async def save(self, config: UserAiConfig) -> UserAiConfig:
            self._storage[config.user_id] = config
            return config

        async def delete(self, user_id: str) -> None:
            self._storage.pop(user_id, None)

    class FakeAIConnectionTester(AIConnectionTester):
        async def test_connection(
            self,
            provider: AIProvider,
            model: str,
            api_key: str | None = None,
        ) -> TestAIConnectionResult:
            return TestAIConnectionResult(
                is_connected=True,
                detected_model=model,
                message=f"Connected to {provider} with model {model}",
            )

    repo = FakeUserAiConfigRepo()
    tester = FakeAIConnectionTester()

    # Probar persistencia en doble de prueba
    config = UserAiConfig(user_id="usr_test", provider=AIProvider.OPENAI, model="gpt-4o")
    saved = await repo.save(config)
    assert saved.user_id == "usr_test"
    fetched = await repo.by_user_id("usr_test")
    assert fetched == config

    await repo.delete("usr_test")
    assert await repo.by_user_id("usr_test") is None

    # Probar tester en doble de prueba
    test_result = await tester.test_connection(AIProvider.OPENAI, "gpt-4o", "sk-test")
    assert test_result.is_connected is True
    assert test_result.detected_model == "gpt-4o"
