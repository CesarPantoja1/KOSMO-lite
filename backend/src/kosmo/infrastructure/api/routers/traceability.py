from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from kosmo.application.traceability.manage_traceability_navigation import (
    ManageTraceabilityNavigationUseCase,
    TraceabilityNavigationInput,
)
from kosmo.contracts.auth import Principal
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.ids import FeatureId
from kosmo.infrastructure.api.dependencies.auth import (
    get_principal,
    require_project_owner,
    verify_project_owner,
)
from kosmo.infrastructure.api.dependencies.container import get_container
from kosmo.infrastructure.api.schemas import TraceabilityNavigationOutputView

router = APIRouter(tags=["Traceability"])

_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"description": "Credenciales de autenticación no válidas o ausentes."},
    status.HTTP_404_NOT_FOUND: {"description": "Recurso no encontrado o no pertenece al proyecto."},
}


def _manage_traceability_navigation(request: Request) -> ManageTraceabilityNavigationUseCase:
    return ManageTraceabilityNavigationUseCase(feature_repo=get_container(request).repos.features)


@router.get(
    "/api/v1/projects/{project_id}/traceability/{entity_id}/navigation",
    response_model=TraceabilityNavigationOutputView,
    dependencies=[Depends(verify_project_owner)],
    responses=_RESPONSES,
    summary="Verificar navegación de trazabilidad por proyecto",
    description="Verifica si la edición está permitida en este nivel de SDD para una entidad de un proyecto.",
)
async def check_project_traceability_navigation(
    project_id: str,
    entity_id: str,
    level: SpecPhase,
    use_case: Annotated[ManageTraceabilityNavigationUseCase, Depends(_manage_traceability_navigation)],
    request: Request,
) -> TraceabilityNavigationOutputView:
    """Verifica si la edición está permitida en este nivel bajo el recurso canónico anidado de proyecto."""
    container = get_container(request)
    if hasattr(container, "repos") and hasattr(container.repos, "features"):
        feature = await container.repos.features.by_id(FeatureId(entity_id))
        if feature is not None:
            if str(feature.project_id) != str(project_id):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Característica {entity_id} no encontrada en este proyecto",
                )
        elif level in (SpecPhase.REQUISITOS, SpecPhase.MODELO):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Característica {entity_id} no encontrada",
            )

    input_data = TraceabilityNavigationInput(entity_id=entity_id, level=level)
    output = await use_case.execute(input_data)

    return TraceabilityNavigationOutputView(
        permitted=output.permitted,
        redirect_message=output.redirect_message,
        source_entity_name=output.source_entity_name,
        source_entity_id=output.source_entity_id,
        source_level=output.source_level,
    )


@router.get(
    "/api/v1/traceability/{entity_id}/navigation",
    response_model=TraceabilityNavigationOutputView,
    responses=_RESPONSES,
    deprecated=True,
    summary="Verificar navegación de trazabilidad (Legacy)",
    description="Ruta legacy; migrar a /api/v1/projects/{project_id}/traceability/{entity_id}/navigation.",
)
async def check_traceability_navigation(
    entity_id: str,
    level: SpecPhase,
    use_case: Annotated[ManageTraceabilityNavigationUseCase, Depends(_manage_traceability_navigation)],
    principal: Annotated[Principal, Depends(get_principal)],
    request: Request,
    response: Response,
) -> TraceabilityNavigationOutputView:
    """Verifica si la edición está permitida en este nivel o sugiere redirección."""
    response.headers["Deprecation"] = "true"
    container = get_container(request)
    if hasattr(container, "repos"):
        project_id = None
        if hasattr(container.repos, "features"):
            feature = await container.repos.features.by_id(FeatureId(entity_id))
            if feature is not None:
                project_id = feature.project_id
            elif level in (SpecPhase.REQUISITOS, SpecPhase.MODELO):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Característica {entity_id} no encontrada",
                )
        if project_id is None:
            project_id = entity_id
        await require_project_owner(container, project_id, principal)

    input_data = TraceabilityNavigationInput(entity_id=entity_id, level=level)
    output = await use_case.execute(input_data)

    return TraceabilityNavigationOutputView(
        permitted=output.permitted,
        redirect_message=output.redirect_message,
        source_entity_name=output.source_entity_name,
        source_entity_id=output.source_entity_id,
        source_level=output.source_level,
    )
