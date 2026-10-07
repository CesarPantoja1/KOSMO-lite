from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import ClassVar, Protocol

from kosmo.contracts.auth.secrets import EncryptedSecret


class AIProvider(StrEnum):
    """Proveedores de Inteligencia Artificial compatibles con la plataforma."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    DEEPSEEK = "deepseek"
    CUSTOM = "custom"
    KOSMO_DEFAULT = "kosmo_default"


DEFAULT_AI_PROVIDER: AIProvider = AIProvider.KOSMO_DEFAULT
DEFAULT_AI_MODEL: str = "gemini-3.8-flash"


# ── Catálogo curado de modelos por proveedor ──


@dataclass(frozen=True, slots=True)
class AIModelInfo:
    """Metadata de presentación de un modelo de IA para el usuario final."""

    id: str
    display_name: str
    tier: str


@dataclass(frozen=True, slots=True)
class AIProviderInfo:
    """Metadata de un proveedor de IA expuesto al usuario."""

    value: str
    label: str
    models: tuple[AIModelInfo, ...]


SUPPORTED_PROVIDERS: tuple[AIProviderInfo, ...] = (
    AIProviderInfo(
        value=AIProvider.OPENAI,
        label="OpenAI (ChatGPT)",
        models=(
            AIModelInfo(id="o3", display_name="o3", tier="flagship"),
            AIModelInfo(id="gpt-4o", display_name="GPT-4o", tier="balanced"),
            AIModelInfo(id="gpt-4o-mini", display_name="GPT-4o Mini", tier="fast"),
        ),
    ),
    AIProviderInfo(
        value=AIProvider.ANTHROPIC,
        label="Anthropic",
        models=(
            AIModelInfo(id="claude-opus-5", display_name="Claude Opus 5", tier="flagship"),
            AIModelInfo(id="claude-sonnet-5", display_name="Claude Sonnet 5", tier="balanced"),
            AIModelInfo(id="claude-haiku-4-5", display_name="Claude Haiku 4.5", tier="fast"),
        ),
    ),
    AIProviderInfo(
        value=AIProvider.GOOGLE,
        label="Google Gemini",
        models=(
            AIModelInfo(id="gemini-3.1-pro", display_name="Gemini 3.1 Pro", tier="flagship"),
            AIModelInfo(id="gemini-3.8-flash", display_name="Gemini 3.8 Flash", tier="balanced"),
            AIModelInfo(id="gemini-3.5-flash-lite", display_name="Gemini 3.5 Flash Lite", tier="fast"),
        ),
    ),
    AIProviderInfo(
        value=AIProvider.DEEPSEEK,
        label="DeepSeek",
        models=(
            AIModelInfo(id="deepseek-v4-pro", display_name="DeepSeek V4 Pro", tier="flagship"),
            AIModelInfo(id="deepseek-flash", display_name="DeepSeek Flash", tier="fast"),
        ),
    ),
)

# Mantiene compatibilidad con la lógica interna que valida modelos por proveedor.
SUPPORTED_MODELS_PER_PROVIDER: dict[AIProvider, tuple[str, ...]] = {
    p.value: tuple(m.id for m in p.models)  # type: ignore[misc]
    for p in SUPPORTED_PROVIDERS
} | {
    AIProvider.CUSTOM: ("custom-model",),
    AIProvider.KOSMO_DEFAULT: ("gemini-3.8-flash",),
}


def mask_api_key(key: str | None) -> str | None:
    """Enmascara una clave de API mostrando únicamente los últimos cuatro caracteres."""
    if not key:
        return None
    stripped = key.strip()
    if not stripped:
        return None
    if len(stripped) <= 4:
        return "••••••••"
    return f"••••••••{stripped[-4:]}"


# ── Excepciones de Dominio ──


class AIConfigError(Exception):
    """Excepción base para errores del subsistema de configuración de IA."""


class InvalidAIProviderError(AIConfigError):
    """Lanzada cuando se especifica un proveedor de IA no soportado o inválido."""


class InvalidAIModelError(AIConfigError):
    """Lanzada cuando el nombre o identificador del modelo es inválido o está vacío."""


class InvalidApiKeyError(AIConfigError):
    """Lanzada cuando la clave de API no cumple con las restricciones de formato o longitud."""


class AIConnectionTestError(AIConfigError):
    """Lanzada cuando la prueba de conectividad con el proveedor de IA falla."""


# ── Entidades de Dominio ──


@dataclass(frozen=True, slots=True)
class UserAiConfig:
    """Entidad inmutable que representa la configuración de IA personalizada de un usuario."""

    user_id: str
    provider: AIProvider = AIProvider.KOSMO_DEFAULT
    model: str = DEFAULT_AI_MODEL
    encrypted_api_key: EncryptedSecret | bytes | None = None
    is_custom: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime | None = None

    @property
    def has_api_key(self) -> bool:
        """Indica si la configuración contiene una clave cifrada almacenada."""
        return self.encrypted_api_key is not None

    def to_view(self, masked_key: str | None = None) -> AIConfigView:
        """Convierte la entidad a un DTO de lectura seguro sin secretos en claro."""
        return AIConfigView(
            provider=self.provider,
            model=self.model,
            is_custom=self.is_custom,
            has_api_key=self.has_api_key,
            masked_key=masked_key,
            updated_at=self.updated_at or self.created_at,
        )


# ── DTOs y Esquemas de Operación ──


@dataclass(frozen=True, slots=True)
class AIConfigView:
    """Vista pública de la configuración de IA del usuario para respuestas de contrato."""

    provider: AIProvider
    model: str
    is_custom: bool
    has_api_key: bool
    masked_key: str | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SaveAIConfigInput:
    """Datos de entrada para persistir o actualizar la configuración de IA de un usuario."""

    provider: AIProvider
    model: str
    api_key: str

    def __post_init__(self) -> None:
        if not self.model or not self.model.strip():
            raise InvalidAIModelError("El nombre del modelo no puede estar vacío.")
        if len(self.model.strip()) > 100:
            raise InvalidAIModelError("El nombre del modelo no puede exceder los 100 caracteres.")
        if not self.api_key or not self.api_key.strip():
            raise InvalidApiKeyError("La clave de API no puede estar vacía.")
        if len(self.api_key.strip()) > 500:
            raise InvalidApiKeyError("La clave de API no puede exceder los 500 caracteres.")


@dataclass(frozen=True, slots=True)
class TestAIConnectionInput:
    """Datos de entrada para ejecutar una prueba de conectividad con el proveedor de IA."""

    __test__: ClassVar[bool] = False

    provider: AIProvider
    model: str
    api_key: str | None = None
    user_id: str | None = None

    def __post_init__(self) -> None:
        if not self.model or not self.model.strip():
            raise InvalidAIModelError("El nombre del modelo no puede estar vacío.")
        if len(self.model.strip()) > 100:
            raise InvalidAIModelError("El nombre del modelo no puede exceder los 100 caracteres.")
        if self.api_key is not None and len(self.api_key.strip()) > 500:
            raise InvalidApiKeyError("La clave de API no puede exceder los 500 caracteres.")


@dataclass(frozen=True, slots=True)
class TestAIConnectionResult:
    """Resultado cualitativo de la comprobación de conectividad con el proveedor."""

    __test__: ClassVar[bool] = False

    is_connected: bool
    detected_model: str
    message: str


# ── Puertos y Protocolos ──


class UserAiConfigRepository(Protocol):
    """Puerto de persistencia para la configuración de IA de los usuarios."""

    async def by_user_id(self, user_id: str) -> UserAiConfig | None:
        """Obtiene la configuración de IA asociada a un usuario."""
        ...

    async def save(self, config: UserAiConfig) -> UserAiConfig:
        """Persiste o actualiza la configuración de IA de un usuario."""
        ...

    async def delete(self, user_id: str) -> None:
        """Elimina las credenciales personalizadas de IA del usuario."""
        ...


class AIConnectionTester(Protocol):
    """Puerto para ejecutar pruebas de conectividad y comprobación de modelos con proveedores externos."""

    async def test_connection(
        self,
        provider: AIProvider,
        model: str,
        api_key: str | None = None,
    ) -> TestAIConnectionResult:
        """Comprueba la disponibilidad del proveedor y la validez de las credenciales."""
        ...
