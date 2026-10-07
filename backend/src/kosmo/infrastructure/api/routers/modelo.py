from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from kosmo.application.modelo import (
    DeleteActivityDiagramUseCase,
    DeleteDiagramInput,
    GenerateActivityDiagramUseCase,
    GenerateDiagramInput,
    GetActivityDiagramUseCase,
    GetDiagramInput,
)
from kosmo.contracts.auth import Principal
from kosmo.contracts.sdd.errors import (
    DiagramNotFoundError,
    FeatureNotFoundError,
    ProjectNotFoundError,
)
from kosmo.contracts.sdd.ids import FeatureId, ProjectId
from kosmo.domain.pipeline.feature_resolver import resolve_feature_id
from kosmo.infrastructure.api.dependencies.auth import get_principal, require_project_owner
from kosmo.infrastructure.api.dependencies.container import get_container
from kosmo.infrastructure.api.dependencies.rate_limit import ProjectGenerationRateLimiter

router = APIRouter(
    prefix="/api/v1/features/{feature_id}/diagram",
    tags=["modelo"],
)

_generation_rate_limiter = ProjectGenerationRateLimiter()


class GenerateDiagramRequest(BaseModel):
    project_id: str


async def _get_feature_id(
    request: Request,
    project_id: str,
    id_or_slug: str,
    principal: Principal | None = None,
) -> FeatureId:
    container = get_container(request)
    if principal is not None:
        await require_project_owner(container, project_id, principal)
    fid = await resolve_feature_id(container.features.feature_repo, ProjectId(project_id), id_or_slug)
    if fid is None:
        raise FeatureNotFoundError(
            feature_id=id_or_slug,
            instance=f"/api/v1/features/{id_or_slug}/diagram",
        )
    return fid


def _diagram_response(output: Any) -> dict[str, Any]:
    return {
        "id": str(output.diagram.id),
        "feature_id": str(output.diagram.feature_id),
        "diagram_syntax": output.diagram.diagram_syntax,
        "created_at": output.diagram.created_at.isoformat().replace("+00:00", "Z"),
        "updated_at": output.diagram.updated_at.isoformat().replace("+00:00", "Z"),
    }


@router.post(
    "/generate",
    summary="Generar diagrama de actividad",
    description="Genera un diagrama PlantUML para la característica indicada.",
    status_code=status.HTTP_200_OK,
)
async def generate_diagram(
    feature_id: str,
    body: GenerateDiagramRequest,
    _principal: Annotated[Principal, Depends(get_principal)],
    request: Request,
    _rate: Annotated[None, Depends(_generation_rate_limiter)] = None,
) -> dict[str, Any]:
    fid = await _get_feature_id(request, body.project_id, feature_id, _principal)
    uc: GenerateActivityDiagramUseCase = get_container(request).modelo.generate_diagram

    output = await uc.execute(GenerateDiagramInput(project_id=ProjectId(body.project_id), feature_id=fid))
    return _diagram_response(output)


@router.post(
    "/propagate",
    summary="Propagar cambios al modelo",
    description=(
        "Regenera el diagrama de actividad PlantUML de una característica "
        "cuando cambios en fases upstream lo dejaron desactualizado."
    ),
    status_code=status.HTTP_200_OK,
    operation_id="propagate_changes_to_model",
)
async def propagate_to_model(
    feature_id: str,
    body: GenerateDiagramRequest,
    _principal: Annotated[Principal, Depends(get_principal)],
    request: Request,
    _rate: Annotated[None, Depends(_generation_rate_limiter)] = None,
) -> dict[str, Any]:
    fid = await _get_feature_id(request, body.project_id, feature_id, _principal)
    uc: GenerateActivityDiagramUseCase = get_container(request).modelo.generate_diagram

    output = await uc.execute(GenerateDiagramInput(project_id=ProjectId(body.project_id), feature_id=fid))
    return _diagram_response(output)


@router.get(
    "",
    summary="Obtener diagrama de actividad",
    description="Recupera el diagrama de actividad PlantUML existente de la característica.",
)
async def get_diagram(
    feature_id: str,
    _principal: Annotated[Principal, Depends(get_principal)],
    request: Request,
    project_id: str = Query(...),
) -> dict[str, Any]:
    fid = await _get_feature_id(request, project_id, feature_id, _principal)
    uc: GetActivityDiagramUseCase = get_container(request).modelo.get_diagram

    try:
        output = await uc.execute(
            GetDiagramInput(
                project_id=ProjectId(project_id),
                feature_id=fid,
            )
        )
    except (ProjectNotFoundError, FeatureNotFoundError, DiagramNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.problem.detail,
        ) from exc

    return {
        "id": str(output.diagram.id),
        "feature_id": str(output.diagram.feature_id),
        "diagram_syntax": output.diagram.diagram_syntax,
        "created_at": output.diagram.created_at.isoformat().replace("+00:00", "Z"),
        "updated_at": output.diagram.updated_at.isoformat().replace("+00:00", "Z"),
    }


@router.delete(
    "",
    summary="Eliminar diagrama de actividad",
    description=("Elimina el diagrama de actividad PlantUML existente de la característica."),
    status_code=status.HTTP_200_OK,
)
async def delete_diagram(
    feature_id: str,
    _principal: Annotated[Principal, Depends(get_principal)],
    request: Request,
    project_id: str = Query(...),
) -> dict[str, str]:
    fid = await _get_feature_id(request, project_id, feature_id, _principal)
    uc: DeleteActivityDiagramUseCase = get_container(request).modelo.delete_diagram

    await uc.execute(
        DeleteDiagramInput(
            project_id=ProjectId(project_id),
            feature_id=fid,
        )
    )

    return {"status": "deleted", "feature_id": feature_id}
