from __future__ import annotations

from dataclasses import dataclass

import structlog

from kosmo.contracts.llm.ports import LLMClient
from kosmo.contracts.sdd.codegen import (
    FeatureImplementationRepository,
    FeatureImplementationStatus,
)
from kosmo.contracts.sdd.ids import FeatureId, ProjectId
from kosmo.contracts.sdd.product_map import ProductMap
from kosmo.contracts.sdd.repositories import DocumentRepository, FeatureRepository
from kosmo.domain.codegen.integration_rules import (
    build_product_map,
    extract_actors_from_discovery,
)
from kosmo.domain.sdd.document_converters import document_to_markdown

_log = structlog.get_logger("kosmo.codegen.analyze_integration")


@dataclass(frozen=True)
class AnalyzeFeatureIntegrationInput:
    project_id: ProjectId
    current_feature_id: FeatureId | None = None


class AnalyzeFeatureIntegrationUseCase:
    """Caso de uso para analizar la integración global de características y construir el Product Map."""

    def __init__(
        self,
        feature_repo: FeatureRepository,
        document_repo: DocumentRepository | None = None,
        implementation_repo: FeatureImplementationRepository | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self._feature_repo = feature_repo
        self._document_repo = document_repo
        self._implementation_repo = implementation_repo
        self._llm_client = llm_client

    async def execute(
        self,
        input_data: AnalyzeFeatureIntegrationInput,
    ) -> ProductMap:
        """Ejecuta el análisis de cohesión e integración para el proyecto."""
        features = await self._feature_repo.list_by_project(input_data.project_id)
        if not features:
            return ProductMap(project_id=input_data.project_id)

        implemented_ids: set[str] = set()
        if self._implementation_repo is not None:
            try:
                impls = await self._implementation_repo.list_by_project(input_data.project_id)
                implemented_ids = {
                    str(impl.feature_id) for impl in impls if impl.status == FeatureImplementationStatus.IMPLEMENTED
                }
            except Exception:
                _log.debug("analyze_integration.list_impls_failed", exc_info=True)

        discovery_actors: tuple[str, ...] = ()
        if self._document_repo is not None:
            try:
                discovery_doc = await self._document_repo.get_discovery(input_data.project_id)
                if discovery_doc is not None:
                    discovery_md = document_to_markdown(discovery_doc)
                    if discovery_md:
                        discovery_actors = extract_actors_from_discovery(discovery_md)
            except Exception:
                _log.debug("analyze_integration.get_discovery_failed", exc_info=True)

        # Construcción determinista del ProductMap
        product_map = build_product_map(
            project_id=input_data.project_id,
            features=features,
            implemented_feature_ids=implemented_ids,
            discovery_actors=discovery_actors,
        )

        _log.info(
            "analyze_integration.completed",
            project_id=str(input_data.project_id),
            features_count=len(features),
            entities_count=len(product_map.entities),
            actors_count=len(product_map.actors),
        )

        return product_map
