from __future__ import annotations

from collections.abc import Sequence

import structlog

from kosmo.application.ai.dual_model_validator import DualModelValidator
from kosmo.contracts.ai.catalog import (
    AiCatalogRepository,
    CatalogModel,
    ModelDiscoveryAdapter,
)
from kosmo.contracts.sdd.codegen import OpenCodeCatalogInspector

_log = structlog.get_logger(__name__)


class SyncAiCatalogUseCase:
    """Caso de uso para sincronizar el catálogo de modelos de IA con los proveedores y OpenCode."""

    def __init__(
        self,
        catalog_repo: AiCatalogRepository,
        opencode_inspector: OpenCodeCatalogInspector,
        adapters: Sequence[ModelDiscoveryAdapter],
        validator: DualModelValidator | None = None,
    ) -> None:
        self._repo = catalog_repo
        self._opencode_inspector = opencode_inspector
        self._adapters = {a.provider: a for a in adapters}
        self._validator = validator or DualModelValidator()

    async def execute(
        self,
        provider_keys: dict[str, str | None] | None = None,
    ) -> dict[str, int]:
        """Ejecuta el descubrimiento en cada proveedor y aplica la validación dual."""
        keys = provider_keys or {}
        opencode_catalog = await self._opencode_inspector.get_supported_models()

        total_upserted = 0
        total_active = 0

        # 1. Sincronización directa desde OpenCode cuando esté disponible
        if hasattr(self._opencode_inspector, "get_raw_models"):
            try:
                opencode_raw = await self._opencode_inspector.get_raw_models()
                if opencode_raw:
                    evaluated_from_oc: list[CatalogModel] = []
                    for raw in opencode_raw:
                        opencode_supported = opencode_catalog.get(raw.provider, set())
                        existing = await self._repo.get_by_provider_and_model(raw.provider, raw.model_id)
                        existing_id = existing.id if existing else None
                        model_entity = self._validator.validate_and_classify(
                            raw,
                            opencode_supported,
                            existing_id=existing_id,
                        )
                        evaluated_from_oc.append(model_entity)
                        if model_entity.is_active:
                            total_active += 1
                    if evaluated_from_oc:
                        await self._repo.upsert_batch(evaluated_from_oc)
                        total_upserted += len(evaluated_from_oc)
            except Exception:
                _log.warning("sync_ai_catalog.opencode_query_failed", exc_info=True)

        # 2. Descubrimiento por APIs oficiales de proveedores con keys
        for provider_name, adapter in self._adapters.items():
            api_key = keys.get(provider_name)
            if not api_key:
                continue

            try:
                discovered = await adapter.discover_models(api_key)
                if not discovered:
                    continue

                opencode_supported = opencode_catalog.get(provider_name, set())
                seen_ids: set[str] = set()
                evaluated_models: list[CatalogModel] = []

                for raw in discovered:
                    seen_ids.add(raw.model_id)
                    existing = await self._repo.get_by_provider_and_model(provider_name, raw.model_id)
                    existing_id = existing.id if existing else None
                    model_entity = self._validator.validate_and_classify(
                        raw,
                        opencode_supported,
                        existing_id=existing_id,
                    )
                    evaluated_models.append(model_entity)
                    if model_entity.is_active:
                        total_active += 1

                if evaluated_models:
                    await self._repo.upsert_batch(evaluated_models)
                    total_upserted += len(evaluated_models)
                    await self._repo.mark_unseen_as_retired(provider_name, seen_ids)

            except Exception:
                _log.warning("sync_ai_catalog.provider_failed", provider=provider_name, exc_info=True)

        return {"upserted": total_upserted, "active": total_active}
