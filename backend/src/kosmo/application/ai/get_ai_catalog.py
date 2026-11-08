from __future__ import annotations

from kosmo.application.ai.dual_model_validator import DualModelValidator
from kosmo.contracts.ai.ai_config import AIModelInfo, AIProviderInfo
from kosmo.contracts.ai.catalog import AiCatalogRepository, CatalogModel, ModelTier
from kosmo.contracts.sdd.codegen import OpenCodeCatalogInspector
from kosmo.domain.ai.seed_catalog import SEED_CATALOG_MODELS

_PROVIDER_LABELS: dict[str, str] = {
    "openai": "OpenAI (ChatGPT)",
    "anthropic": "Anthropic",
    "google": "Google Gemini",
    "deepseek": "DeepSeek",
}

_PROVIDER_ORDER: tuple[str, ...] = ("openai", "anthropic", "google", "deepseek")

_TIER_ORDER: dict[ModelTier, int] = {
    ModelTier.FLAGSHIP: 0,
    ModelTier.BALANCED: 1,
    ModelTier.FAST: 2,
    ModelTier.REASONING: 3,
}


class GetAiCatalogUseCase:
    """Caso de uso para consultar el catálogo de modelos disponibles y validados."""

    def __init__(
        self,
        catalog_repo: AiCatalogRepository,
        opencode_inspector: OpenCodeCatalogInspector | None = None,
        validator: DualModelValidator | None = None,
    ) -> None:
        self._repo = catalog_repo
        self._opencode_inspector = opencode_inspector
        self._validator = validator or DualModelValidator()

    async def execute(self) -> list[AIProviderInfo]:
        models = await self._repo.list_active()
        if not models:
            seeded = False
            if self._opencode_inspector and hasattr(self._opencode_inspector, "get_raw_models"):
                try:
                    raw_models = await self._opencode_inspector.get_raw_models()
                    supported = await self._opencode_inspector.get_supported_models()
                    if raw_models:
                        evaluated = [
                            self._validator.validate_and_classify(r, supported.get(r.provider, set()))
                            for r in raw_models
                        ]
                        await self._repo.upsert_batch(evaluated)
                        seeded = True
                except Exception:
                    pass

            if not seeded:
                # Si OpenCode no está respondiendo, sembramos el catálogo base verificado 2026
                await self._repo.upsert_batch(list(SEED_CATALOG_MODELS))
            models = await self._repo.list_active()

        # Agrupar por proveedor en orden predefinido
        by_provider: dict[str, list[CatalogModel]] = {p: [] for p in _PROVIDER_ORDER}
        for m in models:
            if m.provider in by_provider:
                by_provider[m.provider].append(m)

        result: list[AIProviderInfo] = []
        for p in _PROVIDER_ORDER:
            prov_models = by_provider[p]
            if not prov_models:
                continue

            # Ordenar de forma estable: nivel (FLAGSHIP -> BALANCED -> FAST),
            # fecha de lanzamiento descendente (modelos más recientes y capaces primero),
            # y modelo canónico antes de variantes secundarias (-fast, -flex, etc.)
            prov_models.sort(key=lambda m: m.display_name)
            prov_models.sort(key=lambda m: 1 if any(x in m.model_id for x in ("-fast", "-flex", "-ultrafast")) else 0)
            prov_models.sort(
                key=lambda m: str(m.metadata_json.get("release_date") or "") if m.metadata_json else "",
                reverse=True,
            )
            prov_models.sort(key=lambda m: _TIER_ORDER.get(m.tier, 9))

            # Curaduría Estricta para Citizen Developers: exactamente 1 modelo óptimo por categoría canónica
            curated_models: list[CatalogModel] = []
            for tier in (ModelTier.FLAGSHIP, ModelTier.BALANCED, ModelTier.FAST):
                tier_candidates = [m for m in prov_models if m.tier == tier]
                if tier_candidates:
                    curated_models.append(tier_candidates[0])

            model_infos = tuple(
                AIModelInfo(
                    id=m.model_id,
                    display_name=m.display_name,
                    tier=m.tier.value,
                    description="",
                    recommended=False,
                )
                for m in curated_models
            )
            result.append(
                AIProviderInfo(
                    value=p,
                    label=_PROVIDER_LABELS.get(p, p.title()),
                    models=model_infos,
                )
            )
        return result
