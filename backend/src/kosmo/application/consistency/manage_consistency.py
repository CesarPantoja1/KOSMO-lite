from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

import structlog

from kosmo.application.consistency.apply_consistency_impacts import ApplyConsistencyImpactsUseCase
from kosmo.application.consistency.consistency_snapshot import fetch_snapshot_parts
from kosmo.contracts.ai.consistency import (
    ConsistencyEvaluation,
    ConsistencyEvaluationRepository,
    ConsistencyEvaluationStatus,
)
from kosmo.contracts.sdd.codegen import FeatureImplementationRepository
from kosmo.contracts.sdd.document import SPEC_TO_API_PHASE, SpecPhase
from kosmo.contracts.sdd.errors import (
    ConsistencyEvaluationNotFoundError,
    ConsistencyStaleError,
    ProjectNotFoundError,
)
from kosmo.contracts.sdd.ids import ConsistencyEvaluationId, FeatureId, ProjectId
from kosmo.contracts.sdd.repositories import (
    ActivityDiagramRepository,
    DocumentRepository,
    FeatureRepository,
    RequirementRepository,
)
from kosmo.domain.sdd.consistency_snapshot import compute_snapshot_hash
from kosmo.domain.sdd.plan_diffs import apply_change_diff
from kosmo.domain.sdd.validators.activity_diagram_validator import validate_activity_diagram_syntax

_log = structlog.get_logger(__name__)

_REVIEW_TARGET_PHASES = (
    SpecPhase.CARACTERISTICAS,
    SpecPhase.REQUISITOS,
    SpecPhase.MODELO,
    SpecPhase.IMPLEMENTACION,
)


@dataclass(frozen=True)
class ReviewCard:
    evaluation_id: str
    source_phase: str
    target_phase: str
    target_artifact_id: str
    artifact_type: str
    target_display_id: str
    target_title: str
    section: str
    rationale: str
    action: str
    diff: dict[str, object] | None
    status: str
    operation_id: str | None = None
    failure_reason: str | None = None


def _card_from_row(row: ConsistencyEvaluation) -> ReviewCard:
    result = row.result or {}
    diff_raw = result.get("diff")
    diff = cast(dict[str, object], diff_raw) if isinstance(diff_raw, dict) else None
    return ReviewCard(
        evaluation_id=str(row.id),
        source_phase=row.source_phase.value,
        target_phase=row.target_phase.value,
        target_artifact_id=row.target_artifact_id,
        artifact_type=row.artifact_type,
        target_display_id=str(result.get("targetDisplayId", row.target_artifact_id)),
        target_title=str(result.get("targetTitle", row.target_artifact_id)),
        section=str(result.get("section", "")),
        rationale=str(result.get("rationale", "")),
        action=str(result.get("action", "update")),
        diff=diff,
        status=row.status.value,
        operation_id=row.operation_id,
        failure_reason=row.failure_reason,
    )


class GetConsistencyStatusUseCase:
    def __init__(self, evaluation_repo: ConsistencyEvaluationRepository) -> None:
        self._evaluation_repo = evaluation_repo

    async def execute(self, project_id: ProjectId) -> dict[str, object]:
        phases: dict[str, dict[str, int]] = {}
        for phase in _REVIEW_TARGET_PHASES:
            rows = await self._evaluation_repo.list_unresolved(project_id, phase)
            phases[SPEC_TO_API_PHASE[phase]] = {
                "pending": sum(1 for r in rows if r.status == ConsistencyEvaluationStatus.COMPLETED),
                "evaluating": sum(1 for r in rows if r.status == ConsistencyEvaluationStatus.EVALUATING),
                "failed": sum(1 for r in rows if r.status == ConsistencyEvaluationStatus.FAILED),
            }
        return {"phases": phases}


class GetConsistencyReviewUseCase:
    def __init__(
        self,
        evaluation_repo: ConsistencyEvaluationRepository,
        *,
        document_repo: DocumentRepository,
        feature_repo: FeatureRepository,
        requirement_repo: RequirementRepository,
        diagram_repo: ActivityDiagramRepository,
        implementation_repo: FeatureImplementationRepository | None = None,
    ) -> None:
        self._evaluation_repo = evaluation_repo
        self._document_repo = document_repo
        self._feature_repo = feature_repo
        self._requirement_repo = requirement_repo
        self._diagram_repo = diagram_repo
        self._implementation_repo = implementation_repo

    async def execute(self, project_id: ProjectId, target_phase: SpecPhase) -> list[ReviewCard]:
        rows = await self._evaluation_repo.list_unresolved(project_id, target_phase)
        cards: list[ReviewCard] = []
        for row in rows:
            if row.status != ConsistencyEvaluationStatus.COMPLETED:
                cards.append(_card_from_row(row))
                continue

            try:
                parts = await fetch_snapshot_parts(
                    project_id=project_id,
                    source_phase=row.source_phase,
                    target_phase=row.target_phase,
                    target_artifact_id=row.target_artifact_id,
                    artifact_type=row.artifact_type,
                    document_repo=self._document_repo,
                    feature_repo=self._feature_repo,
                    requirement_repo=self._requirement_repo,
                    diagram_repo=self._diagram_repo,
                    implementation_repo=self._implementation_repo,
                )
            except Exception:
                _log.warning("consistency.review_snapshot_failed", evaluation_id=str(row.id), exc_info=True)
                continue

            if compute_snapshot_hash(*parts) != row.snapshot_hash:
                await self._evaluation_repo.save(
                    dataclasses.replace(
                        row,
                        status=ConsistencyEvaluationStatus.DISCARDED,
                        failure_reason="Obsoleto: la entrada cambió.",
                        updated_at=datetime.now(UTC),
                    )
                )
                continue

            cards.append(_card_from_row(await self._enrich_diagram_diff(row)))

        return cards

    async def _enrich_diagram_diff(self, row: ConsistencyEvaluation) -> ConsistencyEvaluation:
        """Inyecta el diagrama completo (anterior y propuesto) en el diff de un card de actividad."""
        if row.artifact_type != "ActivityDiagram":
            return row
        result = dict(row.result or {})
        diff_raw = result.get("diff")
        if not isinstance(diff_raw, dict):
            return row
        diff_dict: dict[str, object] = diff_raw  # type: ignore[reportUnknownVariableType]
        before = str(diff_dict.get("before", ""))
        after = str(diff_dict.get("after", ""))
        if not before and not after:
            return row
        try:
            diagram = await self._diagram_repo.by_feature_id(FeatureId(row.target_artifact_id))
        except Exception:
            _log.debug("manage_consistency.diagram_fetch_failed", artifact_id=row.target_artifact_id, exc_info=True)
            return row
        if diagram is None:
            return row
        after_full = apply_change_diff(diagram.diagram_syntax, before=before, after=after)
        if after_full is None:
            return row
        if not validate_activity_diagram_syntax(diagram.diagram_syntax).is_valid:
            return row
        if not validate_activity_diagram_syntax(after_full).is_valid:
            return row
        enriched_diff = dict(diff_dict)
        enriched_diff["before_diagram"] = diagram.diagram_syntax
        enriched_diff["after_diagram"] = after_full
        result["diff"] = enriched_diff
        return dataclasses.replace(row, result=result)


class ApplyConsistencyEvaluationUseCase:
    def __init__(
        self,
        *,
        evaluation_repo: ConsistencyEvaluationRepository,
        apply_uc: ApplyConsistencyImpactsUseCase,
        document_repo: DocumentRepository,
        feature_repo: FeatureRepository,
        requirement_repo: RequirementRepository,
        diagram_repo: ActivityDiagramRepository,
        implementation_repo: FeatureImplementationRepository | None = None,
    ) -> None:
        self._evaluation_repo = evaluation_repo
        self._apply_uc = apply_uc
        self._document_repo = document_repo
        self._feature_repo = feature_repo
        self._requirement_repo = requirement_repo
        self._diagram_repo = diagram_repo
        self._implementation_repo = implementation_repo

    async def execute(
        self,
        evaluation_id: ConsistencyEvaluationId,
        project_id: ProjectId | None = None,
    ) -> dict[str, object]:
        row = await self._evaluation_repo.by_id(evaluation_id)
        if row is None or (project_id is not None and str(row.project_id) != str(project_id)):
            raise ConsistencyEvaluationNotFoundError(evaluation_id=str(evaluation_id))

        if row.status != ConsistencyEvaluationStatus.COMPLETED:
            raise ConsistencyStaleError(
                evaluation_id=str(evaluation_id),
                detail="La sugerencia ya fue procesada o el análisis falló.",
            )

        parts = await fetch_snapshot_parts(
            project_id=row.project_id,
            source_phase=row.source_phase,
            target_phase=row.target_phase,
            target_artifact_id=row.target_artifact_id,
            artifact_type=row.artifact_type,
            document_repo=self._document_repo,
            feature_repo=self._feature_repo,
            requirement_repo=self._requirement_repo,
            diagram_repo=self._diagram_repo,
            implementation_repo=self._implementation_repo,
        )
        if compute_snapshot_hash(*parts) != row.snapshot_hash:
            await self._evaluation_repo.save(
                dataclasses.replace(
                    row,
                    status=ConsistencyEvaluationStatus.DISCARDED,
                    failure_reason="La lógica de origen cambió.",
                    updated_at=datetime.now(UTC),
                )
            )
            raise ConsistencyStaleError(
                evaluation_id=str(evaluation_id),
                detail="La lógica de origen cambió. La sugerencia ha sido descartada.",
            )

        impact = _impact_for_apply(row)
        output = await self._apply_uc.execute(project_id=row.project_id, impacts=[impact])
        if output.failed:
            reason = output.failed[0].reason
            await self._evaluation_repo.save(
                dataclasses.replace(
                    row,
                    status=ConsistencyEvaluationStatus.FAILED,
                    failure_reason=reason,
                    updated_at=datetime.now(UTC),
                )
            )
            raise ConsistencyStaleError(
                evaluation_id=str(evaluation_id),
                detail=f"No se pudo aplicar el cambio: {reason}",
            )

        await self._evaluation_repo.save(
            dataclasses.replace(
                row,
                status=ConsistencyEvaluationStatus.APPLIED,
                updated_at=datetime.now(UTC),
            )
        )

        return {
            "evaluation_id": str(row.id),
            "applied": True,
            "target_id": row.target_artifact_id,
        }


class DiscardConsistencyEvaluationUseCase:
    def __init__(self, evaluation_repo: ConsistencyEvaluationRepository) -> None:
        self._evaluation_repo = evaluation_repo

    async def execute(
        self,
        evaluation_id: ConsistencyEvaluationId,
        project_id: ProjectId | None = None,
    ) -> dict[str, object]:
        row = await self._evaluation_repo.by_id(evaluation_id)
        if row is None or (project_id is not None and str(row.project_id) != str(project_id)):
            raise ConsistencyEvaluationNotFoundError(evaluation_id=str(evaluation_id))
        if row.status != ConsistencyEvaluationStatus.COMPLETED:
            raise ConsistencyStaleError(
                evaluation_id=str(evaluation_id),
                detail="La sugerencia ya fue procesada o el análisis falló.",
            )
        await self._evaluation_repo.save(
            dataclasses.replace(
                row,
                status=ConsistencyEvaluationStatus.DISCARDED,
                failure_reason="Descartada por el usuario.",
                updated_at=datetime.now(UTC),
            )
        )
        return {"evaluation_id": str(row.id), "discarded": True}


class BulkResolveConsistencyUseCase:
    def __init__(
        self,
        *,
        evaluation_repo: ConsistencyEvaluationRepository,
        apply_uc: ApplyConsistencyEvaluationUseCase,
        discard_uc: DiscardConsistencyEvaluationUseCase,
    ) -> None:
        self._evaluation_repo = evaluation_repo
        self._apply_uc = apply_uc
        self._discard_uc = discard_uc

    async def execute(
        self,
        project_id: ProjectId,
        target_phase: SpecPhase,
        *,
        action: str,
    ) -> dict[str, int]:
        rows = [
            r
            for r in await self._evaluation_repo.list_unresolved(project_id, target_phase)
            if r.status == ConsistencyEvaluationStatus.COMPLETED
        ]
        resolved = 0
        skipped = 0
        for row in rows:
            try:
                if action == "apply":
                    await self._apply_uc.execute(row.id, project_id=project_id)
                else:
                    await self._discard_uc.execute(row.id, project_id=project_id)
            except (ConsistencyStaleError, ConsistencyEvaluationNotFoundError, ProjectNotFoundError):
                skipped += 1
                continue
            resolved += 1
        return {"resolved": resolved, "skipped": skipped}


class GetConsistencyActivityUseCase:
    def __init__(self, evaluation_repo: ConsistencyEvaluationRepository) -> None:
        self._evaluation_repo = evaluation_repo

    async def execute(self, project_id: ProjectId, *, limit: int = 50) -> list[dict[str, object]]:
        rows = await self._evaluation_repo.list_for_activity(project_id, limit=limit)
        items: list[dict[str, object]] = []
        for row in rows:
            items.append(
                {
                    "evaluation_id": str(row.id),
                    "status": row.status.value,
                    "source_phase": row.source_phase.value,
                    "target_phase": row.target_phase.value,
                    "target_artifact_id": row.target_artifact_id,
                    "target_title": (row.result or {}).get("targetTitle", ""),
                    "failure_reason": row.failure_reason,
                    "updated_at": row.updated_at.isoformat(),
                }
            )
        return items


def _impact_for_apply(row: ConsistencyEvaluation) -> dict[str, object]:
    result = row.result or {}
    diff_raw = result.get("diff")
    diff = cast(dict[str, object], diff_raw) if isinstance(diff_raw, dict) else {}
    return {
        "artifact_type": row.artifact_type,
        "target_id": row.target_artifact_id.split(":", 1)[0],
        "action": str(result.get("action", "update")),
        "field": str(diff.get("field", "description")),
        "before": str(diff.get("before", "")),
        "after": str(diff.get("after", "")),
    }
