"""Router MCP — Expone tools de contexto para que OpenCode consulte bajo demanda."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from kosmo.contracts.auth import Principal
from kosmo.contracts.sdd.ids import FeatureId
from kosmo.contracts.sdd.repositories import ActivityDiagramRepository, RequirementRepository
from kosmo.infrastructure.api.dependencies.auth import get_principal, require_project_owner

router = APIRouter(
    prefix="/mcp",
    tags=["MCP Tools"],
    dependencies=[Depends(get_principal)],
)


class MCPToolRequest(BaseModel):
    """Solicitud de una tool MCP con el identificador de la característica."""

    feature_id: str = Field(min_length=1, description="Identificador de la característica")


class MCPToolResponse(BaseModel):
    """Respuesta de una tool MCP con el contenido solicitado."""

    feature_id: str
    content: str


def _get_requirement_repo(request: Request) -> RequirementRepository:
    return request.app.state.requirement_repo  # type: ignore[no-any-return]


def _get_diagram_repo(request: Request) -> ActivityDiagramRepository:
    return request.app.state.diagram_repo  # type: ignore[no-any-return]


async def _verify_feature_access(
    feature_id: str,
    principal: Principal,
    request: Request,
) -> None:
    """Verifica que la característica exista y pertenezca al proyecto del usuario autenticado."""
    container = getattr(request.app.state, "container", None)
    feature_repo = getattr(request.app.state, "feature_repo", None)
    if (
        feature_repo is None
        and container is not None
        and hasattr(container, "repos")
        and hasattr(container.repos, "features")
    ):
        feature_repo = container.repos.features

    if feature_repo is not None:
        feature = await feature_repo.by_id(FeatureId(feature_id))
        if feature is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Característica '{feature_id}' no encontrada.",
            )
        if container is not None and hasattr(container, "repos") and hasattr(container.repos, "projects"):
            await require_project_owner(container, feature.project_id, principal)
        elif hasattr(request.app.state, "project_repo"):
            proj = await request.app.state.project_repo.by_id(feature.project_id)
            if proj is None or str(getattr(proj, "owner_id", "")) != principal.subject:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Proyecto del recurso no encontrado.",
                )


@router.post(
    "/tools/get_requirements",
    response_model=MCPToolResponse,
    summary="Obtener requisitos EARS de una característica",
    responses={
        401: {"description": "No autenticado"},
        404: {"description": "Requisitos no encontrados para la característica indicada"},
    },
)
async def get_requirements(
    body: MCPToolRequest,
    request: Request,
    principal: Annotated[Principal, Depends(get_principal)],
) -> MCPToolResponse:
    """Retorna los requisitos EARS en formato markdown para la característica indicada."""
    await _verify_feature_access(body.feature_id, principal, request)
    repo = _get_requirement_repo(request)
    markdown = await repo.by_feature_id(FeatureId(body.feature_id))
    if markdown is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontraron requisitos EARS para la característica {body.feature_id}",
        )
    return MCPToolResponse(feature_id=body.feature_id, content=markdown)


@router.post(
    "/tools/get_activity_diagram",
    response_model=MCPToolResponse,
    summary="Obtener diagrama de actividad de una característica",
    responses={
        401: {"description": "No autenticado"},
        404: {"description": "Diagrama de actividad no encontrado para la característica indicada"},
    },
)
async def get_activity_diagram(
    body: MCPToolRequest,
    request: Request,
    principal: Annotated[Principal, Depends(get_principal)],
) -> MCPToolResponse:
    """Retorna el diagrama de actividad en formato PlantUML para la característica indicada."""
    await _verify_feature_access(body.feature_id, principal, request)
    repo = _get_diagram_repo(request)
    diagram = await repo.by_feature_id(FeatureId(body.feature_id))
    if diagram is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró diagrama de actividad para la característica {body.feature_id}",
        )
    return MCPToolResponse(feature_id=body.feature_id, content=diagram.diagram_syntax)
