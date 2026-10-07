from __future__ import annotations

import dataclasses
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from ulid import ULID

from kosmo.application.consistency.apply_consistency_impacts import ApplyConsistencyImpactsUseCase
from kosmo.application.consistency.cascade_consistency import CascadingConsistencyUseCase
from kosmo.application.consistency.evaluate_project_consistency import (
    EvaluateProjectConsistencyInput,
    EvaluateProjectConsistencyUseCase,
)
from kosmo.application.consistency.manage_consistency import (
    ApplyConsistencyEvaluationUseCase,
    BulkResolveConsistencyUseCase,
    DiscardConsistencyEvaluationUseCase,
    GetConsistencyActivityUseCase,
    GetConsistencyReviewUseCase,
    GetConsistencyStatusUseCase,
)
from kosmo.contracts import DiffCambio
from kosmo.contracts.ai.chat import AppliedChange
from kosmo.contracts.auth import Principal
from kosmo.contracts.sdd.document import SPEC_TO_API_PHASE, SpecPhase
from kosmo.contracts.sdd.errors import (
    ConsistencyEvaluationNotFoundError,
    ConsistencyStaleError,
)
from kosmo.contracts.sdd.ids import ConsistencyEvaluationId, ProjectId
from kosmo.infrastructure.api.async_generation import sse_consistency_response
from kosmo.infrastructure.api.dependencies.auth import get_principal, verify_project_owner
from kosmo.infrastructure.api.dependencies.container import get_container
from kosmo.infrastructure.api.schemas import (
    ChangeInputView,
    EvaluateConsistencyRequestView,
    HttpErrorResponse,
)

router = APIRouter(
    prefix="/api/v1/projects/{project_id}/consistency",
    tags=["consistency"],
    dependencies=[Depends(verify_project_owner)],
    responses={
        401: {"model": HttpErrorResponse, "description": "Token ausente, inválido o expirado"},
        404: {"model": HttpErrorResponse, "description": "Proyecto no encontrado"},
    },
)


def _consistency_uc(request: Request) -> EvaluateProjectConsistencyUseCase:
    return get_container(request).consistency.evaluate_project_consistency


def _cascade_uc(request: Request) -> CascadingConsistencyUseCase:
    return get_container(request).consistency.cascade_consistency


def _apply_uc(request: Request) -> ApplyConsistencyImpactsUseCase:
    return get_container(request).consistency.apply_consistency_impacts


def _status_uc(request: Request) -> GetConsistencyStatusUseCase:
    return get_container(request).consistency.consistency_status


def _review_uc(request: Request) -> GetConsistencyReviewUseCase:
    return get_container(request).consistency.consistency_review


def _apply_evaluation_uc(request: Request) -> ApplyConsistencyEvaluationUseCase:
    return get_container(request).consistency.apply_consistency_evaluation


def _discard_evaluation_uc(request: Request) -> DiscardConsistencyEvaluationUseCase:
    return get_container(request).consistency.discard_consistency_evaluation


def _bulk_uc(request: Request) -> BulkResolveConsistencyUseCase:
    return get_container(request).consistency.bulk_resolve_consistency


def _activity_uc(request: Request) -> GetConsistencyActivityUseCase:
    return get_container(request).consistency.consistency_activity


@router.get(
    "/status",
    summary="Estado de consistencia pendiente por fase",
    description="Badges por fase calculados sobre las evaluaciones no resueltas del proyecto.",
    status_code=status.HTTP_200_OK,
)
async def get_consistency_status(
    project_id: str,
    _principal: Annotated[Principal, Depends(get_principal)],
    uc: Annotated[GetConsistencyStatusUseCase, Depends(_status_uc)],
) -> dict[str, Any]:
    return await uc.execute(project_id=ProjectId(project_id))


@router.get(
    "/review",
    summary="Vista de revisión de consistencia por fase (gate)",
    description="Cards frescas por artefacto destino. Las sugerencias obsoletas se descartan automáticamente.",
    status_code=status.HTTP_200_OK,
)
async def get_consistency_review(
    project_id: str,
    _principal: Annotated[Principal, Depends(get_principal)],
    uc: Annotated[GetConsistencyReviewUseCase, Depends(_review_uc)],
    target_phase: Annotated[
        str,
        Query(description="Fase destino a revisar (features, requirements, model, implementation)"),
    ],
) -> dict[str, Any]:
    phase = _to_spec_phase(target_phase)
    cards = await uc.execute(project_id=ProjectId(project_id), target_phase=phase)
    return {"cards": [dataclasses.asdict(c) for c in cards]}


@router.post(
    "/evaluations/{evaluation_id}/apply",
    summary="Aplicar una sugerencia de consistencia",
    description="Aplica con guardrail de frescura: si la entrada cambió, devuelve 409 y re-evalúa.",
    status_code=status.HTTP_200_OK,
    responses={409: {"model": HttpErrorResponse, "description": "La sugerencia ya no aplica al estado actual"}},
)
async def apply_consistency_evaluation(
    project_id: str,
    evaluation_id: str,
    _principal: Annotated[Principal, Depends(get_principal)],
    uc: Annotated[ApplyConsistencyEvaluationUseCase, Depends(_apply_evaluation_uc)],
) -> dict[str, Any]:
    try:
        result = await uc.execute(
            ConsistencyEvaluationId(evaluation_id),
            project_id=ProjectId(project_id),
        )
        return {**result, "project_id": project_id}
    except ConsistencyEvaluationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.problem.detail) from exc
    except ConsistencyStaleError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.problem.detail) from exc


@router.post(
    "/evaluations/{evaluation_id}/discard",
    summary="Descartar una sugerencia de consistencia",
    description="Descartada para este snapshot; si la fuente vuelve a cambiar, aparece una sugerencia nueva.",
    status_code=status.HTTP_200_OK,
)
async def discard_consistency_evaluation(
    project_id: str,
    evaluation_id: str,
    _principal: Annotated[Principal, Depends(get_principal)],
    uc: Annotated[DiscardConsistencyEvaluationUseCase, Depends(_discard_evaluation_uc)],
) -> dict[str, Any]:
    try:
        result = await uc.execute(
            ConsistencyEvaluationId(evaluation_id),
            project_id=ProjectId(project_id),
        )
        return {**result, "project_id": project_id}
    except ConsistencyEvaluationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.problem.detail) from exc
    except ConsistencyStaleError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.problem.detail) from exc


class BulkResolveRequestView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(description="apply | discard")
    target_phase: str = Field(description="Fase destino a resolver (features, requirements, model)")


@router.post(
    "/review/bulk",
    summary="Resolver en lote las sugerencias de una fase",
    description="Aplica o descarta todas las sugerencias frescas de la fase destino en un solo clic.",
    status_code=status.HTTP_200_OK,
)
async def bulk_resolve_consistency(
    project_id: str,
    _principal: Annotated[Principal, Depends(get_principal)],
    request: Annotated[BulkResolveRequestView, Body(...)],
    uc: Annotated[BulkResolveConsistencyUseCase, Depends(_bulk_uc)],
) -> dict[str, Any]:
    if request.action not in {"apply", "discard"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="action debe ser 'apply' o 'discard'.",
        )
    phase = _to_spec_phase(request.target_phase)
    return await uc.execute(project_id=ProjectId(project_id), target_phase=phase, action=request.action)


@router.get(
    "/activity",
    summary="Feed de actividad de consistencia",
    description="Historial de sugerencias aplicadas o descartadas con su origen.",
    status_code=status.HTTP_200_OK,
)
async def get_consistency_activity(
    project_id: str,
    _principal: Annotated[Principal, Depends(get_principal)],
    uc: Annotated[GetConsistencyActivityUseCase, Depends(_activity_uc)],
    limit: int = 50,
) -> dict[str, Any]:
    return {"items": await uc.execute(project_id=ProjectId(project_id), limit=limit)}


@router.post(
    "/evaluate/stream",
    summary="Evaluar consistencia entre fases (SSE streaming)",
    description="Evalúa el impacto de cambios en cascada (features → requirements → model) con progreso SSE.",
    status_code=status.HTTP_200_OK,
)
async def evaluate_consistency_stream(
    project_id: str,
    _principal: Annotated[Principal, Depends(get_principal)],
    request: Annotated[EvaluateConsistencyRequestView, Body(...)],
    uc: Annotated[CascadingConsistencyUseCase, Depends(_cascade_uc)],
) -> StreamingResponse:
    source_phase = _resolve_origin_phase(request.phase_origin)
    _resolve_targets(request.phase_origin, request.phase_destination)
    changes = _changes_to_applied(request.changes)

    generator = uc.execute_stream(
        project_id=ProjectId(project_id),
        source_phase=source_phase,
        applied_changes=changes,
    )
    return await sse_consistency_response(generator)


@router.post(
    "/evaluate",
    summary="Evaluar consistencia entre fases",
    description="Evalúa el impacto de cambios propuestos sobre artefactos del proyecto.",
    status_code=status.HTTP_200_OK,
)
async def evaluate_consistency(
    project_id: str,
    _principal: Annotated[Principal, Depends(get_principal)],
    request: Annotated[EvaluateConsistencyRequestView, Body(...)],
    uc: Annotated[EvaluateProjectConsistencyUseCase, Depends(_consistency_uc)],
) -> dict[str, Any]:
    source_phase = _resolve_origin_phase(request.phase_origin)
    changes = _changes_to_applied(request.changes)
    targets = _resolve_targets(request.phase_origin, request.phase_destination)
    target_specs = [_to_spec_phase(t) for t in targets]

    output = await uc.execute(
        EvaluateProjectConsistencyInput(
            project_id=ProjectId(project_id),
            source_phase=source_phase,
            target_phases=target_specs,
            applied_changes=changes,
        )
    )
    source_api_phase = SPEC_TO_API_PHASE.get(source_phase, source_phase.value)
    return {
        "report_id": output.report_id,
        "source_type": source_api_phase,
        "source_id": project_id,
        "your_changes": [
            {
                "change_id": str(c.id),
                "section": c.section,
                "description": c.description,
                "diff": {"before": c.diff.before, "after": c.diff.after},
                "accepted": True,
            }
            for c in changes
        ],
        "upstream_impact": [_impact_dict(i) for i in output.upstream_impact],
        "downstream_impact": [_impact_dict(i) for i in output.downstream_impact],
    }


def _resolve_origin_phase(phase_name: str) -> SpecPhase:
    reverse = {
        "discovery": SpecPhase.DESCUBRIMIENTO,
        "features": SpecPhase.CARACTERISTICAS,
        "requirements": SpecPhase.REQUISITOS,
        "model": SpecPhase.MODELO,
        "implementation": SpecPhase.IMPLEMENTACION,
    }
    if phase_name not in reverse:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Fase de origen desconocida: '{phase_name}'.",
        )
    return reverse[phase_name]


def _to_spec_phase(api_phase: str) -> SpecPhase:
    reverse = {
        "discovery": SpecPhase.DESCUBRIMIENTO,
        "features": SpecPhase.CARACTERISTICAS,
        "requirements": SpecPhase.REQUISITOS,
        "model": SpecPhase.MODELO,
        "implementation": SpecPhase.IMPLEMENTACION,
    }
    if api_phase not in reverse:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Fase destino desconocida: '{api_phase}'.",
        )
    return reverse[api_phase]


def _resolve_targets(phase_origin: str, phase_destination: str | None) -> list[str]:
    from kosmo.contracts.ai.consistency import DOWNSTREAM_TARGETS, PHASE_ORDER

    origin = _resolve_origin_phase(phase_origin)

    if phase_destination:
        destination = _to_spec_phase(phase_destination)
        if PHASE_ORDER.get(destination, -1) <= PHASE_ORDER.get(origin, -1):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "La dirección de evaluación no está permitida: la trazabilidad se verifica "
                    "solo hacia la derecha (Descubrimiento → Características → Requisitos → Modelo)."
                ),
            )
        return [phase_destination]

    return [SPEC_TO_API_PHASE[spec] for spec in DOWNSTREAM_TARGETS.get(origin, [])]


def _changes_to_applied(changes: list[ChangeInputView]) -> list[AppliedChange]:
    result: list[AppliedChange] = []
    for c in changes:
        result.append(
            AppliedChange(
                id=f"chg_eval_{ULID().hex}",
                section=c.section,
                description=c.description or c.section,
                diff=DiffCambio(before=c.diff_before, after=c.diff_after),
            )
        )
    return result


def _impact_dict(i: Any) -> dict[str, Any]:
    return {
        "id": i.id,
        "phase": i.phase,
        "targetId": i.target_id,
        "artifact_type": i.artifact_type,
        "targetDisplayId": i.target_display_id,
        "targetTitle": i.target_title,
        "section": i.section,
        "rationale": i.rationale,
        "diff": i.diff,
        "action": getattr(i, "action", "update"),
    }


class ApplyImpactsRequestView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    impacts: list[dict[str, object]] = Field(description="Impactos a aplicar")


@router.post(
    "/apply",
    summary="Aplicar impactos de consistencia",
    description="Aplica las acciones sugeridas sobre requisitos, caracteristicas y diagramas.",
    status_code=status.HTTP_200_OK,
)
async def apply_consistency_impacts(
    project_id: str,
    _principal: Annotated[Principal, Depends(get_principal)],
    request: Annotated[ApplyImpactsRequestView, Body(...)],
    uc: Annotated[ApplyConsistencyImpactsUseCase, Depends(_apply_uc)],
) -> dict[str, Any]:
    output = await uc.execute(project_id=ProjectId(project_id), impacts=request.impacts)
    return {
        "applied": [{"target_id": a.target_id, "artifact_type": a.artifact_type} for a in output.applied],
        "failed": [
            {"target_id": f.target_id, "artifact_type": f.artifact_type, "reason": f.reason} for f in output.failed
        ],
    }
