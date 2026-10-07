from typing import Annotated

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Request, status

from kosmo.application.projects import (
    CreateProjectUseCase,
    DeleteProjectInput,
    DeleteProjectUseCase,
    GetProjectUseCase,
    ListProjectsUseCase,
)
from kosmo.contracts.auth import Principal
from kosmo.contracts.sdd.errors import ProjectNotFoundError
from kosmo.contracts.sdd.ids import ProjectId, UserId
from kosmo.infrastructure.api.dependencies.auth import get_principal
from kosmo.infrastructure.api.dependencies.container import get_container
from kosmo.infrastructure.api.schemas import (
    CreateProjectRequest,
    ProjectResponse,
)

_log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


def _create_project(request: Request) -> CreateProjectUseCase:
    return get_container(request).projects.create_project


def _get_project(request: Request) -> GetProjectUseCase:
    return get_container(request).projects.get_project


def _list_projects(request: Request) -> ListProjectsUseCase:
    return get_container(request).projects.list_projects


def _delete_project(request: Request) -> DeleteProjectUseCase:
    return get_container(request).projects.delete_project


@router.post(
    "",
    summary="Crear nuevo proyecto",
    description=(
        "Crea un nuevo proyecto en KOSMO. "
        "El nombre se transforma automáticamente en un slug único para el usuario. "
        "Requiere autenticación mediante Bearer token."
    ),
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: {
            "description": "Proyecto creado exitosamente.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Token de acceso inválido o ausente.",
        },
    },
)
async def create_project(
    payload: Annotated[CreateProjectRequest, Body(...)],
    principal: Annotated[Principal, Depends(get_principal)],
    use_case: Annotated[CreateProjectUseCase, Depends(_create_project)],
) -> ProjectResponse:
    project = await use_case.execute(
        name=payload.name,
        description=payload.description,
        owner_id=UserId(principal.subject),
    )
    return ProjectResponse(
        id=project.id,
        name=project.name,
        slug=project.slug,
        description=project.description,
        owner_id=project.owner_id,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.get(
    "",
    summary="Listar proyectos del usuario",
    description=("Devuelve todos los proyectos del usuario autenticado. Requiere autenticación mediante Bearer token."),
    response_model=list[ProjectResponse],
    responses={
        status.HTTP_200_OK: {
            "description": "Lista de proyectos del usuario.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Token de acceso inválido o ausente.",
        },
    },
)
async def list_projects(
    principal: Annotated[Principal, Depends(get_principal)],
    use_case: Annotated[ListProjectsUseCase, Depends(_list_projects)],
) -> list[ProjectResponse]:
    projects = await use_case.execute(owner_id=UserId(principal.subject))
    return [
        ProjectResponse(
            id=p.id,
            name=p.name,
            slug=p.slug,
            description=p.description,
            owner_id=p.owner_id,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in projects
    ]


@router.get(
    "/{project_id}",
    summary="Obtener proyecto por ID",
    description=(
        "Devuelve los detalles de un proyecto específico por su identificador. "
        "Requiere autenticación mediante Bearer token."
    ),
    response_model=ProjectResponse,
    responses={
        status.HTTP_200_OK: {
            "description": "Detalles del proyecto.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Token de acceso inválido o ausente.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Proyecto no encontrado.",
        },
    },
)
async def get_project(
    project_id: str,
    principal: Annotated[Principal, Depends(get_principal)],
    use_case: Annotated[GetProjectUseCase, Depends(_get_project)],
) -> ProjectResponse:
    try:
        project = await use_case.execute(project_id=ProjectId(project_id))
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.problem.detail,
        ) from exc
    if str(project.owner_id) != principal.subject:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proyecto '{project_id}' no encontrado.",
        )
    return ProjectResponse(
        id=project.id,
        name=project.name,
        slug=project.slug,
        description=project.description,
        owner_id=project.owner_id,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.delete(
    "/{project_id}",
    summary="Eliminar proyecto",
    description=(
        "Elimina el proyecto y todos sus artefactos en cascada: descubrimiento, "
        "características, requisitos, modelos, chat y evaluaciones de consistencia. "
        "Requiere autenticación mediante Bearer token."
    ),
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "Proyecto eliminado exitosamente.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Token de acceso inválido o ausente.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Proyecto no encontrado.",
        },
    },
)
async def delete_project(
    project_id: str,
    principal: Annotated[Principal, Depends(get_principal)],
    use_case: Annotated[DeleteProjectUseCase, Depends(_delete_project)],
) -> dict[str, str]:
    await use_case.execute(
        DeleteProjectInput(
            project_id=ProjectId(project_id),
            owner_id=UserId(principal.subject),
        )
    )
    return {"status": "deleted", "project_id": project_id}
