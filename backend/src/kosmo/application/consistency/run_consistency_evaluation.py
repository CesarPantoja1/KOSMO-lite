from __future__ import annotations

import dataclasses
import time
from datetime import UTC, datetime
from typing import Any, cast

import structlog

from kosmo.application.consistency.consistency_snapshot import fetch_snapshot_parts
from kosmo.application.consistency.enrich_impact import enrich_impact_items, impact_item_to_dict
from kosmo.contracts.ai.chat import AppliedChange, DiffCambio
from kosmo.contracts.ai.consistency import (
    ConsistencyEvaluation,
    ConsistencyEvaluationRepository,
    ConsistencyEvaluationStatus,
    ConsistencyEvaluator,
    ConsistencyStatus,
)
from kosmo.contracts.auth.context import current_user_id
from kosmo.contracts.sdd.codegen import FeatureImplementationRepository
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.ids import ConsistencyEvaluationId, ProjectId
from kosmo.contracts.sdd.repositories import (
    ActivityDiagramRepository,
    DocumentRepository,
    FeatureRepository,
    ProjectRepository,
    RequirementRepository,
)
from kosmo.domain.sdd.consistency_snapshot import compute_snapshot_hash
from kosmo.domain.sdd.id_generator import IdGenerator
from kosmo.domain.sdd.traceability_tracer import trace_downstream_phases

_log = structlog.get_logger(__name__)


def _to_applied_change(raw: dict[str, object]) -> AppliedChange:
    return AppliedChange(
        id=str(raw.get("id", "")),
        section=str(raw.get("section", "")),
        description=str(raw.get("description", "")),
        diff=DiffCambio(
            before=str(raw.get("before", "")),
            after=str(raw.get("after", "")),
        ),
    )


async def _has_target_artifacts(
    *,
    target_phase: SpecPhase,
    project_id: ProjectId,
    feature_repo: FeatureRepository,
    requirement_repo: RequirementRepository,
    diagram_repo: ActivityDiagramRepository,
    implementation_repo: FeatureImplementationRepository | None = None,
) -> bool:
    features = await feature_repo.list_by_project(project_id)
    if not features:
        return False

    if target_phase == SpecPhase.CARACTERISTICAS:
        return True

    for feature in features:
        if target_phase == SpecPhase.REQUISITOS and await requirement_repo.by_feature_id(feature.id):
            return True
        if target_phase == SpecPhase.MODELO and await diagram_repo.exists(feature.id):
            return True
        if (
            target_phase == SpecPhase.IMPLEMENTACION
            and implementation_repo is not None
            and await implementation_repo.by_feature_id(feature.id)
        ):
            return True
    return False


async def run_consistency_evaluation(
    payload: dict[str, Any],
    *,
    project_repo: ProjectRepository,
    feature_repo: FeatureRepository,
    requirement_repo: RequirementRepository,
    diagram_repo: ActivityDiagramRepository,
    document_repo: DocumentRepository,
    evaluator: ConsistencyEvaluator,
    evaluation_repo: ConsistencyEvaluationRepository,
    implementation_repo: FeatureImplementationRepository | None = None,
) -> None:
    """Evaluacion fresca de un par de fases, ejecutada por el outbox worker.

    Procesa todos los destinos a la derecha de la fase fuente, valida el
    output deterministicamente y persiste una fila por artefacto afectado.
    Cualquier excepcion queda contenida en una fila `failed`, nunca propaga.
    """
    project_id = ProjectId(payload["project_id"])
    source_phase = SpecPhase(payload["source_phase"])
    operation_id = str(payload["operation_id"]) if payload.get("operation_id") else None
    changes_raw = payload.get("changes")
    raw_changes = [
        cast(dict[str, object], c)
        for c in cast(list[object], changes_raw if isinstance(changes_raw, list) else [])
        if isinstance(c, dict)
    ]
    changes = [_to_applied_change(c) for c in raw_changes]

    project = await project_repo.by_id(project_id)
    if project is None:
        _log.warning("consistency.project_missing", project_id=str(project_id))
        return

    user_id = payload.get("user_id") or (str(project.owner_id) if project.owner_id else None)
    user_token = current_user_id.set(str(user_id)) if user_id else None

    try:
        for target_phase in trace_downstream_phases(source_phase):
            try:
                has_artifacts = await _has_target_artifacts(
                    target_phase=target_phase,
                    project_id=project_id,
                    feature_repo=feature_repo,
                    requirement_repo=requirement_repo,
                    diagram_repo=diagram_repo,
                    implementation_repo=implementation_repo,
                )
                if not has_artifacts:
                    await _supersede_pair(
                        project_id,
                        source_phase,
                        target_phase,
                        kept_keys=set(),
                        evaluation_repo=evaluation_repo,
                    )
                    continue

                eval_start = time.monotonic()
                result = await evaluator.evaluate(
                    source_phase=source_phase,
                    target_phase=target_phase,
                    project_id=project_id,
                    applied_changes=changes,
                )
                _log.info(
                    "consistency.eval_ms",
                    project_id=str(project_id),
                    source=source_phase.value,
                    target=target_phase.value,
                    eval_ms=int((time.monotonic() - eval_start) * 1000),
                )
            except Exception as exc:
                _log.warning(
                    "consistency.evaluation_failed",
                    project_id=str(project_id),
                    source=source_phase.value,
                    target=target_phase.value,
                    exc_info=True,
                )
                await evaluation_repo.save(
                    ConsistencyEvaluation(
                        id=ConsistencyEvaluationId(IdGenerator.generate("consistency_evaluation")),
                        project_id=project_id,
                        source_phase=source_phase,
                        target_phase=target_phase,
                        target_artifact_id="_pair",
                        artifact_type="_PairEvaluation",
                        snapshot_hash="",
                        status=ConsistencyEvaluationStatus.FAILED,
                        source_changes=raw_changes,
                        operation_id=operation_id,
                        failure_reason=str(exc)[:1000],
                    )
                )
                continue

            if result.status == ConsistencyStatus.ANALISIS_FALLIDO:
                _log.warning(
                    "consistency.evaluation_reported_failure",
                    project_id=str(project_id),
                    source=source_phase.value,
                    target=target_phase.value,
                    reason=result.failure_reason,
                )
                await evaluation_repo.save(
                    ConsistencyEvaluation(
                        id=ConsistencyEvaluationId(IdGenerator.generate("consistency_evaluation")),
                        project_id=project_id,
                        source_phase=source_phase,
                        target_phase=target_phase,
                        target_artifact_id="_pair",
                        artifact_type="_PairEvaluation",
                        snapshot_hash="",
                        status=ConsistencyEvaluationStatus.FAILED,
                        source_changes=raw_changes,
                        operation_id=operation_id,
                        failure_reason=(result.failure_reason or "Analisis fallido")[:1000],
                    )
                )
                continue

            items = await enrich_impact_items(
                result,
                target_phase,
                source_phase,
                feature_repo,
                requirement_repo,
                diagram_repo,
            )

            kept_keys: set[str] = set()
            for item in items:
                key = _row_key(item)
                kept_keys.add(key)
                try:
                    parts = await fetch_snapshot_parts(
                        project_id=project_id,
                        source_phase=source_phase,
                        target_phase=target_phase,
                        target_artifact_id=key,
                        artifact_type=item.artifact_type,
                        document_repo=document_repo,
                        feature_repo=feature_repo,
                        requirement_repo=requirement_repo,
                        diagram_repo=diagram_repo,
                        implementation_repo=implementation_repo,
                    )
                    snapshot_hash = compute_snapshot_hash(*parts)
                except Exception:
                    _log.warning("consistency.snapshot_failed", exc_info=True)
                    continue

                await evaluation_repo.save(
                    ConsistencyEvaluation(
                        id=ConsistencyEvaluationId(IdGenerator.generate("consistency_evaluation")),
                        project_id=project_id,
                        source_phase=source_phase,
                        target_phase=target_phase,
                        target_artifact_id=key,
                        artifact_type=item.artifact_type,
                        snapshot_hash=snapshot_hash,
                        status=ConsistencyEvaluationStatus.COMPLETED,
                        result=impact_item_to_dict(item),
                        source_changes=raw_changes,
                        operation_id=operation_id,
                    )
                )

            await _supersede_pair(
                project_id,
                source_phase,
                target_phase,
                kept_keys=kept_keys,
                evaluation_repo=evaluation_repo,
            )
    finally:
        if user_token is not None:
            current_user_id.reset(user_token)


def _row_key(item: Any) -> str:
    if item.artifact_type == "EARSRequirement":
        return f"{item.target_id}:{item.target_display_id}"
    return str(item.target_id)


async def _supersede_pair(
    project_id: ProjectId,
    source_phase: SpecPhase,
    target_phase: SpecPhase,
    *,
    kept_keys: set[str],
    evaluation_repo: ConsistencyEvaluationRepository,
) -> None:
    """Marca como descartadas las sugerencias del par que la evaluacion nueva no reproduce."""
    existing = await evaluation_repo.list_unresolved(project_id, target_phase)
    for row in existing:
        if row.source_phase != source_phase:
            continue
        if row.status != ConsistencyEvaluationStatus.COMPLETED:
            continue
        if row.target_artifact_id in kept_keys:
            continue
        await evaluation_repo.save(
            dataclasses.replace(
                row,
                status=ConsistencyEvaluationStatus.DISCARDED,
                failure_reason="Superado por una evaluación más reciente.",
                updated_at=datetime.now(UTC),
            )
        )
