from __future__ import annotations

import structlog

from kosmo.contracts.ai.consistency import TraceabilityRepository
from kosmo.contracts.sdd.errors import FeatureNotFoundError, ProjectNotFoundError
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import FeatureId, ProjectId
from kosmo.contracts.sdd.repositories import (
    FeatureRepository,
    ProjectRepository,
    RequirementRepository,
)

_log = structlog.get_logger(__name__)


class DeleteFeatureUseCase:
    def __init__(
        self,
        project_repo: ProjectRepository,
        feature_repo: FeatureRepository,
        requirement_repo: RequirementRepository,
        traceability_repo: TraceabilityRepository | None = None,
    ) -> None:
        self._project_repo = project_repo
        self._feature_repo = feature_repo
        self._requirement_repo = requirement_repo
        self._traceability_repo = traceability_repo

    async def execute(self, project_id: ProjectId, feature_id: FeatureId) -> Feature:
        project = await self._project_repo.by_id(project_id)
        if project is None:
            raise ProjectNotFoundError(
                project_id=str(project_id),
                instance=f"/api/v1/projects/{project_id}/features/{feature_id}",
            )

        feature = await self._feature_repo.by_id(feature_id)
        if feature is None or str(feature.project_id) != str(project_id):
            raise FeatureNotFoundError(
                feature_id=str(feature_id),
                instance=f"/api/v1/projects/{project_id}/features/{feature_id}",
            )

        await self._requirement_repo.delete(feature_id)
        await self._feature_repo.delete(feature_id)

        if self._traceability_repo is not None:
            try:
                await self._traceability_repo.delete_by_entity_id(str(feature_id))
            except Exception:
                _log.warning(
                    "delete_feature.traceability_cleanup_failed",
                    feature_id=str(feature_id),
                    exc_info=True,
                )

        _log.info(
            "delete_feature.success",
            project_id=str(project_id),
            feature_id=str(feature_id),
            display_id=feature.display_id,
        )

        return feature
