from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from kosmo.application.integrations.execute_ephemeral_validation import (
    EphemeralValidationError,
)
from kosmo.application.integrations.sync_github_repository import (
    SyncGitHubRepositoryCommand,
    SyncGitHubRepositoryUseCase,
)
from kosmo.contracts.auth import Principal
from kosmo.contracts.integrations.github import (
    GitHubApiError,
    GitHubResourceNotFoundError,
    GitHubSyncStatus,
)
from kosmo.contracts.sdd.ids import ProjectId, UserId
from kosmo.infrastructure.api.dependencies import (
    get_container,
    get_principal,
    get_sync_github_repository_use_case,
)
from kosmo.infrastructure.api.schemas import (
    ProjectGitHubResponse,
    PushGitHubRequest,
)

router = APIRouter(prefix="/api/v1/projects/{project_id}/github", tags=["github"])


def _require_project_owner(project: object, principal: Principal, project_id: str) -> None:
    """Mantiene los proyectos ajenos indistinguibles de proyectos inexistentes."""
    if project is None or str(getattr(project, "owner_id", "")) != principal.subject:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proyecto '{project_id}' no encontrado.",
        )


@router.get(
    "",
    response_model=ProjectGitHubResponse,
    summary="Obtener estado de integración con GitHub del proyecto",
    description="Devuelve los metadatos del repositorio remoto en GitHub asociado al proyecto.",
)
async def get_project_github_status(
    project_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(get_principal)],
) -> ProjectGitHubResponse:
    container = get_container(request)
    proj_id = ProjectId(project_id)

    project = await container.repos.projects.by_id(proj_id)
    _require_project_owner(project, principal, project_id)
    assert project is not None

    suggested_repo_name = f"kosmo-{project.slug}" if getattr(project, "slug", None) else f"kosmo-{project_id}"

    integration = await container.repos.project_integrations.get_by_project_id(proj_id)
    if integration is None or integration.sync_status == GitHubSyncStatus.NOT_CREATED:
        return ProjectGitHubResponse(
            has_repository=False,
            repo_name=None,
            repo_url=None,
            is_public=True,
            last_push_at=None,
            last_commit_hash=None,
            sync_status=GitHubSyncStatus.NOT_CREATED.value,
            suggested_repo_name=suggested_repo_name,
            error_message=None,
        )

    return ProjectGitHubResponse(
        has_repository=bool(integration.repo_url),
        repo_name=integration.repo_name,
        repo_url=integration.repo_url,
        is_public=integration.is_public,
        last_push_at=integration.last_push_at,
        last_commit_hash=integration.last_commit_hash,
        sync_status=integration.sync_status.value,
        suggested_repo_name=suggested_repo_name,
        error_message=integration.error_message,
    )


@router.post(
    "/push",
    response_model=ProjectGitHubResponse,
    summary="Crear repositorio o sincronizar código en GitHub",
    description="Orquesta la validación efímera y el envío del código fuente hacia GitHub.",
)
async def push_to_github(
    project_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(get_principal)],
    use_case: Annotated[SyncGitHubRepositoryUseCase, Depends(get_sync_github_repository_use_case)],
    body: PushGitHubRequest | None = None,
) -> ProjectGitHubResponse:
    container = get_container(request)
    proj_id = ProjectId(project_id)

    project = await container.repos.projects.by_id(proj_id)
    _require_project_owner(project, principal, project_id)
    assert project is not None

    cmd = SyncGitHubRepositoryCommand(
        project_id=proj_id,
        project_name=project.name,
        repo_name=body.repo_name if body else None,
        is_public=body.is_public if body is not None else True,
        commit_message=body.commit_message if body else None,
    )

    try:
        integration = await use_case.execute(cmd, UserId(principal.subject))
    except GitHubResourceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except EphemeralValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except (GitHubApiError, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return ProjectGitHubResponse(
        has_repository=bool(integration.repo_url),
        repo_name=integration.repo_name,
        repo_url=integration.repo_url,
        is_public=integration.is_public,
        last_push_at=integration.last_push_at,
        last_commit_hash=integration.last_commit_hash,
        sync_status=integration.sync_status.value,
        suggested_repo_name=None,
        error_message=integration.error_message,
    )
