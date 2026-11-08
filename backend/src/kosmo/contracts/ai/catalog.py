from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any, Protocol


class ModelTier(StrEnum):
    FLAGSHIP = "flagship"
    REASONING = "reasoning"
    BALANCED = "balanced"
    FAST = "fast"


class ModelStatus(StrEnum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


def _empty_metadata() -> dict[str, Any]:
    return {}


@dataclass(frozen=True, slots=True)
class CatalogModel:
    """Entidad inmutable que representa un modelo en el catálogo dinámico de KOSMO."""

    id: str
    provider: str
    model_id: str
    opencode_model_id: str
    display_name: str
    tier: ModelTier
    context_window: int = 128000
    max_output_tokens: int = 8192
    supports_tools: bool = True
    supports_vision: bool = False
    opencode_compatible: bool = True
    is_active: bool = True
    is_deprecated: bool = False
    shutdown_date: date | None = None
    metadata_json: dict[str, Any] = field(default_factory=_empty_metadata)
    last_discovered_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class RawDiscoveredModel:
    """Metadatos crudos extraídos de la API de un proveedor antes de clasificación."""

    provider: str
    model_id: str
    display_name: str
    context_window: int | None = None
    max_output_tokens: int | None = None
    supports_tools: bool = True
    supports_vision: bool = False
    is_deprecated: bool = False
    shutdown_date: date | None = None
    raw_metadata: dict[str, Any] = field(default_factory=_empty_metadata)


class AiCatalogRepository(Protocol):
    """Puerto de persistencia para el catálogo dinámico de modelos de IA."""

    async def list_active(self, provider: str | None = None) -> list[CatalogModel]:
        """Retorna todos los modelos activos (opencode_compatible=True, is_active=True)."""
        ...

    async def get_by_provider_and_model(self, provider: str, model_id: str) -> CatalogModel | None:
        """Busca un modelo por proveedor y su model_id de API o su opencode_model_id."""
        ...

    async def upsert_batch(self, models: list[CatalogModel]) -> None:
        """Inserta o actualiza un lote de modelos en el catálogo."""
        ...

    async def mark_unseen_as_retired(self, provider: str, seen_model_ids: set[str]) -> None:
        """Marca como retirados los modelos de un proveedor que no aparecieron en el último descubrimiento."""
        ...


class ModelDiscoveryAdapter(Protocol):
    """Puerto para consultar la API oficial de un proveedor y descubrir modelos."""

    @property
    def provider(self) -> str: ...

    async def discover_models(self, api_key: str | None = None) -> list[RawDiscoveredModel]: ...
