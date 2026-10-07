from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, Request
from pydantic import ValidationError

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
    GitHubSyncStatus,
    ProjectGitHubIntegration,
)
from kosmo.contracts.sdd.ids import ProjectId, UserId
from kosmo.contracts.sdd.project import Project
from kosmo.infrastructure.api.composition import AppContainer
from kosmo.infrastructure.api.routers.github import (
    get_project_github_status,
    push_to_github,
)
from kosmo.infrastructure.api.schemas import PushGitHubRequest


def _principal(subject: str = "usr_123") -> Principal:
    return Principal(subject=subject, scopes=frozenset({"*"}))


def _mock_project(project_id: str = "proj-1", slug: str = "crm-app") -> Project:
    return Project(
        id=ProjectId(project_id),
        name="CRM App",
        slug=slug,
        description="Gestor de clientes",
        owner_id=UserId("usr_123"),
    )


def _mock_request(
    project: Project | None = None,
    project_integration: ProjectGitHubIntegration | None = None,
) -> Request:
    req = MagicMock(spec=Request)
    container = MagicMock(spec=AppContainer)

    project_repo = AsyncMock()
    project_repo.by_id.return_value = project

    integration_repo = AsyncMock()
    integration_repo.get_by_project_id.return_value = project_integration

    container.repos.projects = project_repo
    container.repos.project_integrations = integration_repo
    req.app.state.container = container
    return req


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_project_github_status_no_repo_200() -> None:
    # Arrange
    project = _mock_project("proj-1", "crm-app")
    request = _mock_request(project=project, project_integration=None)

    # Act
    response = await get_project_github_status(
        project_id="proj-1",
        request=request,
        principal=_principal(),
    )

    # Assert
    assert response.has_repository is False
    assert response.sync_status == "not_created"
    assert response.suggested_repo_name == "kosmo-crm-app"
    assert response.repo_url is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_project_github_status_existing_repo_200() -> None:
    # Arrange
    project = _mock_project("proj-1", "crm-app")
    now = datetime.now(UTC)
    integration = ProjectGitHubIntegration(
        project_id=ProjectId("proj-1"),
        repo_name="kosmo-crm-app",
        repo_url="https://github.com/octocat/kosmo-crm-app.git",
        is_public=True,
        sync_status=GitHubSyncStatus.SYNCED,
        last_commit_hash="commit_sha_123",
        last_push_at=now,
    )
    request = _mock_request(project=project, project_integration=integration)

    # Act
    response = await get_project_github_status(
        project_id="proj-1",
        request=request,
        principal=_principal(),
    )

    # Assert
    assert response.has_repository is True
    assert response.sync_status == "synced"
    assert response.repo_name == "kosmo-crm-app"
    assert response.repo_url == "https://github.com/octocat/kosmo-crm-app.git"
    assert response.last_commit_hash == "commit_sha_123"
    assert response.last_push_at == now


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_project_github_status_project_not_found_404() -> None:
    # Arrange
    request = _mock_request(project=None)

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await get_project_github_status(
            project_id="nonexistent-proj",
            request=request,
            principal=_principal(),
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_project_github_status_hides_project_of_another_owner() -> None:
    request = _mock_request(project=_mock_project("proj-private"))

    with pytest.raises(HTTPException) as exc_info:
        await get_project_github_status(
            project_id="proj-private",
            request=request,
            principal=_principal("usr_other"),
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.unit
async def test_push_to_github_success_200() -> None:
    # Arrange
    project = _mock_project("proj-1", "crm-app")
    request = _mock_request(project=project)
    use_case = AsyncMock(spec=SyncGitHubRepositoryUseCase)
    now = datetime.now(UTC)
    use_case.execute.return_value = ProjectGitHubIntegration(
        project_id=ProjectId("proj-1"),
        repo_name="kosmo-crm-app",
        repo_url="https://github.com/octocat/kosmo-crm-app.git",
        is_public=True,
        sync_status=GitHubSyncStatus.SYNCED,
        last_commit_hash="sha_push_success",
        last_push_at=now,
    )

    body = PushGitHubRequest(
        repo_name="kosmo-crm-app",
        is_public=True,
        commit_message="feat: push inicial",
    )

    # Act
    response = await push_to_github(
        project_id="proj-1",
        request=request,
        principal=_principal("usr_123"),
        use_case=use_case,
        body=body,
    )

    # Assert
    assert response.has_repository is True
    assert response.sync_status == "synced"
    assert response.repo_name == "kosmo-crm-app"
    assert response.repo_url == "https://github.com/octocat/kosmo-crm-app.git"
    assert response.last_commit_hash == "sha_push_success"
    use_case.execute.assert_called_once_with(
        SyncGitHubRepositoryCommand(
            project_id=ProjectId("proj-1"),
            project_name="CRM App",
            repo_name="kosmo-crm-app",
            is_public=True,
            commit_message="feat: push inicial",
        ),
        UserId("usr_123"),
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_push_to_github_project_not_found_404() -> None:
    # Arrange
    request = _mock_request(project=None)
    use_case = AsyncMock(spec=SyncGitHubRepositoryUseCase)

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await push_to_github(
            project_id="proj-not-found",
            request=request,
            principal=_principal(),
            use_case=use_case,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.unit
async def test_push_to_github_ephemeral_validation_failure_400() -> None:
    # Arrange
    project = _mock_project("proj-1", "crm-app")
    request = _mock_request(project=project)
    use_case = AsyncMock(spec=SyncGitHubRepositoryUseCase)
    use_case.execute.side_effect = EphemeralValidationError("Validación efímera fallida en el paso 'tests'")

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await push_to_github(
            project_id="proj-1",
            request=request,
            principal=_principal(),
            use_case=use_case,
        )

    assert exc_info.value.status_code == 400
    assert "Validación efímera fallida" in exc_info.value.detail


@pytest.mark.asyncio
@pytest.mark.unit
async def test_push_to_github_unlinked_user_400() -> None:
    # Arrange
    project = _mock_project("proj-1", "crm-app")
    request = _mock_request(project=project)
    use_case = AsyncMock(spec=SyncGitHubRepositoryUseCase)
    use_case.execute.side_effect = ValueError("El usuario no tiene su cuenta vinculada con GitHub.")

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await push_to_github(
            project_id="proj-1",
            request=request,
            principal=_principal(),
            use_case=use_case,
        )

    assert exc_info.value.status_code == 400
    assert "no tiene su cuenta vinculada" in exc_info.value.detail


@pytest.mark.asyncio
@pytest.mark.unit
async def test_push_to_github_api_error_502() -> None:
    # Arrange
    project = _mock_project("proj-1", "crm-app")
    request = _mock_request(project=project)
    use_case = AsyncMock(spec=SyncGitHubRepositoryUseCase)
    use_case.execute.side_effect = GitHubApiError("GitHub upstream failure")

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await push_to_github(
            project_id="proj-1",
            request=request,
            principal=_principal(),
            use_case=use_case,
        )

    assert exc_info.value.status_code == 502


@pytest.mark.unit
def test_push_github_request_rejects_private_repository() -> None:
    # Arrange & Act & Assert
    with pytest.raises(ValidationError) as exc_info:
        PushGitHubRequest(repo_name="my-repo", is_public=False)

    assert "No se permiten repositorios privados" in str(exc_info.value)
