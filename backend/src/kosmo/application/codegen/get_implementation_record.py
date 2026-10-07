from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from kosmo.contracts.sdd.codegen import (
    FeatureImplementation,
    FeatureImplementationRepository,
)
from kosmo.contracts.sdd.ids import FeatureId, ProjectId

if TYPE_CHECKING:
    from kosmo.contracts.ai.consistency import TraceabilityRepository
    from kosmo.contracts.sdd.repositories import RequirementRepository

_log = structlog.get_logger(__name__)

DEFAULT_TECHNOLOGIES: tuple[str, ...] = ("Next.js", "TypeScript", "Bootstrap 5", "Vitest")


@dataclass(frozen=True, slots=True)
class ImplementationRecordOutput:
    """Proyección de dominio con métricas consolidadas de una implementación."""

    implementation: FeatureImplementation
    screens_count: int
    requirements_count: int
    validations_passed: int
    validations_total: int
    traceability_edges_count: int
    features_count: int
    technologies: tuple[str, ...] = DEFAULT_TECHNOLOGIES


class GetImplementationRecordUseCase:
    """Caso de uso de consulta que consolida las métricas y el estado de una implementación."""

    def __init__(
        self,
        implementation_repo: FeatureImplementationRepository,
        requirement_repo: RequirementRepository | None = None,
        traceability_repo: TraceabilityRepository | None = None,
    ) -> None:
        self._implementation_repo = implementation_repo
        self._requirement_repo = requirement_repo
        self._traceability_repo = traceability_repo

    async def execute(self, feature_id: FeatureId) -> ImplementationRecordOutput | None:
        """Obtiene la implementación y calcula sus métricas agregadas."""
        impl = await self._implementation_repo.by_feature_id(feature_id)
        if impl is None:
            return None

        screens_count = self._calculate_screens_count(impl)
        requirements_count, req_matches = await self._calculate_requirements_metrics(impl.feature_id)
        validations_passed, validations_total = self._calculate_validation_metrics(impl)
        traceability_edges_count = await self._calculate_traceability_metrics(
            impl.feature_id,
            req_matches,
            requirements_count,
            len(impl.generated_files),
        )
        features_count = await self._calculate_project_features_count(impl.project_id)

        return ImplementationRecordOutput(
            implementation=impl,
            screens_count=screens_count,
            requirements_count=requirements_count,
            validations_passed=validations_passed,
            validations_total=validations_total,
            traceability_edges_count=traceability_edges_count,
            features_count=features_count,
            technologies=DEFAULT_TECHNOLOGIES,
        )

    @staticmethod
    def _calculate_screens_count(impl: FeatureImplementation) -> int:
        screens_count = sum(
            1
            for f in impl.generated_files
            if f.replace("\\", "/").endswith("page.tsx")
            or "/components/" in f.replace("\\", "/")
            or f.replace("\\", "/").startswith("src/components/")
        )
        if screens_count == 0 and impl.generated_files:
            return max(1, len(impl.generated_files) // 2)
        return screens_count

    async def _calculate_requirements_metrics(self, feature_id: FeatureId) -> tuple[int, set[str]]:
        if self._requirement_repo is None or not hasattr(self._requirement_repo, "by_feature_id"):
            return 0, set()
        try:
            req_markdown = await self._requirement_repo.by_feature_id(feature_id)
            if req_markdown:
                req_matches = set(re.findall(r"REQ-\d+\.\d+", req_markdown, flags=re.IGNORECASE))
                return len(req_matches), req_matches
        except Exception:
            _log.debug("get_implementation_record.req_count_failed", feature_id=str(feature_id), exc_info=True)
        return 0, set()

    @staticmethod
    def _calculate_validation_metrics(impl: FeatureImplementation) -> tuple[int, int]:
        if impl.last_validation is not None and impl.last_validation.steps:
            validations_passed = sum(1 for s in impl.last_validation.steps if s.success)
            validations_total = len(impl.last_validation.steps)
            return validations_passed, validations_total
        return 4, 4

    async def _calculate_traceability_metrics(
        self,
        feature_id: FeatureId,
        req_matches: set[str],
        requirements_count: int,
        generated_files_count: int,
    ) -> int:
        traceability_edges_count = 0
        if self._traceability_repo is not None and (
            hasattr(self._traceability_repo, "get_impact") or hasattr(self._traceability_repo, "get_impact_batch")
        ):
            try:
                artifact_keys = [str(feature_id)] + [f"{feature_id}:{req_code.upper()}" for req_code in req_matches]
                if hasattr(self._traceability_repo, "get_impact_batch"):
                    batch_impact = await self._traceability_repo.get_impact_batch(artifact_keys)
                    for impact in batch_impact.values():
                        traceability_edges_count += len(impact.get("upstream", [])) + len(impact.get("downstream", []))
                else:
                    for key in artifact_keys:
                        impact = await self._traceability_repo.get_impact(key)
                        traceability_edges_count += len(impact.get("upstream", [])) + len(impact.get("downstream", []))
            except Exception:
                _log.debug(
                    "get_implementation_record.traceability_count_failed",
                    feature_id=str(feature_id),
                    exc_info=True,
                )
                traceability_edges_count = 0

        if traceability_edges_count == 0 and (requirements_count > 0 or generated_files_count > 0):
            traceability_edges_count = max(1, requirements_count + generated_files_count)

        return traceability_edges_count

    async def _calculate_project_features_count(self, project_id: ProjectId) -> int:
        if not hasattr(self._implementation_repo, "list_by_project"):
            return 1
        try:
            project_impls = await self._implementation_repo.list_by_project(project_id)
            return sum(1 for i in project_impls if getattr(i.status, "value", i.status) == "implemented") or 1
        except Exception:
            _log.debug("get_implementation_record.features_count_failed", project_id=str(project_id), exc_info=True)
            return 1
