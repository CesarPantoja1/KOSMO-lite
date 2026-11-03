from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from kosmo.application.consistency.enrich_impact import enrich_impact_items
from kosmo.contracts import ConsistencyEvaluator, ImpactItem
from kosmo.contracts.ai.chat import AppliedChange
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.errors import ProjectNotFoundError
from kosmo.contracts.sdd.ids import ProjectId
from kosmo.contracts.sdd.repositories import (
    FeatureRepository,
    ProjectRepository,
    RequirementRepository,
)

_log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class EvaluateProjectConsistencyInput:
    project_id: ProjectId
    source_phase: SpecPhase
    target_phases: list[SpecPhase]
    applied_changes: list[AppliedChange]


@dataclass(frozen=True)
class EvaluateProjectConsistencyOutput:
    report_id: str
    source_phase: str
    upstream_impact: list[ImpactItem] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]
    downstream_impact: list[ImpactItem] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]


class EvaluateProjectConsistencyUseCase:
    def __init__(
        self,
        project_repo: ProjectRepository,
        evaluator: ConsistencyEvaluator,
        feature_repo: FeatureRepository,
        requirement_repo: RequirementRepository,
    ) -> None:
        self._project_repo = project_repo
        self._evaluator = evaluator
        self._feature_repo = feature_repo
        self._requirement_repo = requirement_repo

    async def execute(self, input_data: EvaluateProjectConsistencyInput) -> EvaluateProjectConsistencyOutput:
        from ulid import ULID

        project = await self._project_repo.by_id(input_data.project_id)
        if project is None:
            raise ProjectNotFoundError(
                project_id=str(input_data.project_id),
                instance=f"/api/v1/projects/{input_data.project_id}/consistency",
            )

        report_id = f"cnr_{ULID().hex}"
        downstream: list[ImpactItem] = []
        upstream: list[ImpactItem] = []

        for target_spec in input_data.target_phases:
            try:
                result = await self._evaluator.evaluate(
                    source_phase=input_data.source_phase,
                    target_phase=target_spec,
                    project_id=input_data.project_id,
                    applied_changes=input_data.applied_changes,
                )
            except Exception:
                _log.warning(
                    "consistency.evaluate_failed",
                    project_id=str(input_data.project_id),
                    source=input_data.source_phase,
                    target=target_spec,
                    exc_info=True,
                )
                continue

            try:
                items = await enrich_impact_items(
                    result,
                    target_spec,
                    input_data.source_phase,
                    self._feature_repo,
                    self._requirement_repo,
                )
            except Exception:
                _log.warning(
                    "consistency.enrich_failed",
                    project_id=str(input_data.project_id),
                    target=target_spec,
                    exc_info=True,
                )
                continue

            if target_spec == SpecPhase.DESCUBRIMIENTO:
                upstream.extend(items)
            else:
                downstream.extend(items)

        return EvaluateProjectConsistencyOutput(
            report_id=report_id,
            source_phase=input_data.source_phase.value,
            upstream_impact=upstream,
            downstream_impact=downstream,
        )
