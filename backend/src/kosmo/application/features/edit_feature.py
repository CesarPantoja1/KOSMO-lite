from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field
from ulid import ULID

from kosmo.application.consistency.trigger_downstream import trigger_downstream_evaluation
from kosmo.contracts.ai.chat import AppliedChange, DiffCambio
from kosmo.contracts.ai.consistency import ConsistencyEvaluator, ConsistencyStatus
from kosmo.contracts.persistence.persistence import OutboxPort
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.errors import FeatureNotFoundError
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import FeatureId, ProjectId
from kosmo.contracts.sdd.repositories import FeatureRepository
from kosmo.domain.codegen.integration_rules import detect_capability_overlap


class EditFeatureInput(BaseModel):
    project_id: ProjectId
    feature_id: FeatureId
    title: str = Field(..., max_length=50)
    description: str = Field(..., max_length=500)


@dataclass(frozen=True)
class EditFeatureOutput:
    is_saved: bool
    feature: Feature | None = None
    inconsistency_reason: str | None = None
    warnings: tuple[str, ...] = ()


class EditFeatureUseCase:
    def __init__(
        self,
        feature_repo: FeatureRepository,
        consistency_evaluator: ConsistencyEvaluator,
        outbox: OutboxPort | None = None,
    ) -> None:
        self._feature_repo = feature_repo
        self._consistency_evaluator = consistency_evaluator
        self._outbox = outbox

    async def execute(self, input_dto: EditFeatureInput) -> EditFeatureOutput:
        feature = await self._feature_repo.by_id(input_dto.feature_id)
        if feature is None or feature.project_id != input_dto.project_id:
            raise FeatureNotFoundError(feature_id=str(input_dto.feature_id))

        if feature.title == input_dto.title and feature.description == input_dto.description:
            return EditFeatureOutput(is_saved=True, feature=feature)

        plan_cambio = AppliedChange(
            id=ULID().hex,
            section=f"Característica {feature.number}",
            description="Edición manual de característica",
            diff=DiffCambio(
                before=f"Título: {feature.title}\nDescripción: {feature.description}",
                after=f"Título: {input_dto.title}\nDescripción: {input_dto.description}",
            ),
        )

        consistency_output = await self._consistency_evaluator.evaluate(
            source_phase=SpecPhase.CARACTERISTICAS,
            target_phase=SpecPhase.DESCUBRIMIENTO,
            project_id=input_dto.project_id,
            applied_changes=[plan_cambio],
        )

        if consistency_output.status == ConsistencyStatus.ANALIZADO_CON_IMPACTO:
            for action in consistency_output.actions:
                if action.action == "update":
                    if action.suggested_after:
                        reason = f"{action.rationale}\n\nSugerencia: {action.suggested_after}"
                    else:
                        reason = action.rationale

                    return EditFeatureOutput(
                        is_saved=False,
                        inconsistency_reason=reason,
                    )

            if consistency_output.rationale:
                return EditFeatureOutput(
                    is_saved=False,
                    inconsistency_reason=consistency_output.rationale,
                )

        feature.title = input_dto.title
        feature.description = input_dto.description
        await self._feature_repo.save(feature)

        await trigger_downstream_evaluation(
            self._outbox,
            project_id=input_dto.project_id,
            source_phase=SpecPhase.CARACTERISTICAS,
            changes=[
                {
                    "section": f"Característica {feature.number}",
                    "description": "Edición manual de característica",
                    "before": f"Título: {plan_cambio.diff.before}",
                    "after": f"Título: {plan_cambio.diff.after}",
                }
            ],
        )

        all_features = await self._feature_repo.list_by_project(input_dto.project_id)
        other_features = [f for f in all_features if f.id != feature.id]
        overlaps = detect_capability_overlap(feature, other_features)
        warnings = tuple(o.message for o in overlaps if o.message)

        return EditFeatureOutput(is_saved=True, feature=feature, warnings=warnings)
