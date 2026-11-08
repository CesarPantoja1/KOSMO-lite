from __future__ import annotations

from datetime import UTC, datetime

from kosmo.contracts.ai.catalog import CatalogModel, ModelTier, RawDiscoveredModel
from kosmo.domain.codegen.model_alias_resolver import OpenCodeModelAliasResolver
from kosmo.domain.sdd.id_generator import IdGenerator


class DualModelValidator:
    """Aplica la regla de doble validación e intersección estricta KOSMO + OpenCode."""

    def __init__(self, alias_resolver: OpenCodeModelAliasResolver | None = None) -> None:
        self._resolver = alias_resolver or OpenCodeModelAliasResolver()

    def classify_tier(self, model_id: str) -> ModelTier:
        mid = model_id.lower()
        if any(kw in mid for kw in ("o1", "o3", "o4", "reasoner")):
            return ModelTier.REASONING
        if any(kw in mid for kw in ("sol", "opus", "gemini-4", "v4-pro")):
            return ModelTier.FLAGSHIP
        if any(kw in mid for kw in ("luna", "-mini", "haiku", "flash-lite", "-lite", "-nano", "deepseek-flash")):
            return ModelTier.FAST
        return ModelTier.BALANCED

    def validate_and_classify(
        self,
        raw: RawDiscoveredModel,
        opencode_supported_models: set[str],
        existing_id: str | None = None,
    ) -> CatalogModel:
        """Evalúa un modelo descubierto y determina su compatibilidad con OpenCode y KOSMO."""
        opencode_model_id = self._resolver.resolve(raw.provider, raw.model_id)

        # 1. Validación de compatibilidad con OpenCode
        opencode_compatible = (
            opencode_model_id in opencode_supported_models or raw.model_id in opencode_supported_models
        )

        # 2. Validación de ventana de contexto
        context_window = raw.context_window or 128000
        has_min_context = context_window >= 32768

        # 3. Validación de ciclo de vida
        is_deprecated = raw.is_deprecated
        if raw.shutdown_date and raw.shutdown_date <= datetime.now(UTC).date():
            is_deprecated = True

        # Invariante: Solo activo si OpenCode lo acepta, tiene contexto suficiente y no está retirado
        is_active = opencode_compatible and has_min_context and (not is_deprecated)

        tier = self.classify_tier(raw.model_id)
        model_pk = existing_id or IdGenerator.generate("catalog")
        now = datetime.now(UTC)

        return CatalogModel(
            id=model_pk,
            provider=raw.provider,
            model_id=raw.model_id,
            opencode_model_id=opencode_model_id,
            display_name=raw.display_name,
            tier=tier,
            context_window=context_window,
            max_output_tokens=raw.max_output_tokens or 8192,
            supports_tools=raw.supports_tools,
            supports_vision=raw.supports_vision,
            opencode_compatible=opencode_compatible,
            is_active=is_active,
            is_deprecated=is_deprecated,
            shutdown_date=raw.shutdown_date,
            metadata_json=raw.raw_metadata,
            last_discovered_at=now,
            created_at=now,
            updated_at=now,
        )
