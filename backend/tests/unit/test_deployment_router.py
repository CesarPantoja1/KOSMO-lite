from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, Request

from kosmo.application.integrations.orchestrate_cloud_deployment import (
    OrchestrateCloudDeploymentCommand,
    OrchestrateCloudDeploymentUseCase,
)
from kosmo.contracts.auth import Principal
from kosmo.contracts.integrations.deployment import (
    DeploymentAccountNotLinkedError,
    DeploymentApiError,
    DeploymentConfigurationError,
    DeploymentProvider,
    DeploymentRepositoryMissingError,
    DeploymentStatus,
    ProjectDeployment,
)
from kosmo.contracts.sdd.ids import ProjectId, UserId
from kosmo.contracts.sdd.project import Project
from kosmo.infrastructure.api.composition import AppContainer
from kosmo.infrastructure.api.routers.deployment import (
    delete_project_deployment,
    deploy_to_railway,
    get_project_deploy_status,
)
from kosmo.infrastructure.api.schemas import (
    DeployRailwayRequest,
    DeployStatusEnum,
)
from kosmo.infrastructure.integrations.deployment_worker import DeploymentPollingWorker


def _principal(subject: str = "usr_123") -> Principal:
    return Principal(subject=subject, scopes=frozenset({"*"}))


def _mock_project(project_id: str = "prj_123") -> Project:
    return Project(
        id=ProjectId(project_id),
        name="Test Project",
        slug="test-project",
        description="A test project",
        owner_id=UserId("usr_123"),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _mock_request(
    project: Project | None = None,
    deployment: ProjectDeployment | None = None,
) -> Request:
    req = MagicMock(spec=Request)
    container = MagicMock(spec=AppContainer)

    proj_repo = AsyncMock()
    proj_repo.by_id.return_value = project
    container.repos.projects = proj_repo

    deploy_repo = AsyncMock()
    deploy_repo.get_by_project_id.return_value = deployment
    container.repos.project_deployments = deploy_repo

    req.app.state.container = container
    return req


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_deploy_status_project_not_found_404() -> None:
    # Arrange
    req = _mock_request(project=None)

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await get_project_deploy_status(
            project_id="prj_missing",
            request=req,
            principal=_principal(),
        )

    assert exc_info.value.status_code == 404
    assert "no encontrado" in exc_info.value.detail


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_deploy_status_hides_project_of_another_owner() -> None:
    req = _mock_request(project=_mock_project("prj_private"))

    with pytest.raises(HTTPException) as exc_info:
        await get_project_deploy_status(
            project_id="prj_private",
            request=req,
            principal=_principal("usr_other"),
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_deploy_status_not_deployed_returns_idle() -> None:
    # Arrange
    req = _mock_request(project=_mock_project("prj_123"), deployment=None)

    # Act
    resp = await get_project_deploy_status(
        project_id="prj_123",
        request=req,
        principal=_principal(),
    )

    # Assert
    assert resp.status == DeployStatusEnum.idle.value
    assert resp.service_id is None
    assert resp.deploy_url is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_deploy_status_published_returns_ready() -> None:
    # Arrange
    now = datetime.now(UTC)
    deployment = ProjectDeployment(
        project_id=ProjectId("prj_123"),
        provider=DeploymentProvider.RAILWAY,
        service_id="srv_abc123",
        public_url="https://kosmo-app.up.railway.app",
        status=DeploymentStatus.PUBLISHED,
        last_deployed_at=now,
        build_logs_url=None,
        error_message=None,
    )
    req = _mock_request(project=_mock_project("prj_123"), deployment=deployment)

    # Act
    resp = await get_project_deploy_status(
        project_id="prj_123",
        request=req,
        principal=_principal(),
    )

    # Assert
    assert resp.status == DeployStatusEnum.ready.value
    assert resp.service_id == "srv_abc123"
    assert resp.deploy_url == "https://kosmo-app.up.railway.app"
    assert resp.last_deploy_at == now


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_deploy_status_failed_returns_failed_with_logs() -> None:
    # Arrange
    now = datetime.now(UTC)
    deployment = ProjectDeployment(
        project_id=ProjectId("prj_123"),
        provider=DeploymentProvider.RAILWAY,
        service_id="srv_abc123",
        public_url=None,
        status=DeploymentStatus.FAILED,
        last_deployed_at=now,
        build_logs_url="https://railway.com/logs",
        error_message="Build error: compilation failed",
    )
    req = _mock_request(project=_mock_project("prj_123"), deployment=deployment)

    # Act
    resp = await get_project_deploy_status(
        project_id="prj_123",
        request=req,
        principal=_principal(),
    )

    # Assert
    assert resp.status == DeployStatusEnum.failed.value
    assert resp.error_message == "Build error: compilation failed"
    assert resp.error_log_url == "https://railway.com/logs"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_deploy_to_railway_success_202_and_starts_worker() -> None:
    # Arrange
    project = _mock_project("prj_123")
    req = _mock_request(project=project)
    use_case = AsyncMock(spec=OrchestrateCloudDeploymentUseCase)
    worker = MagicMock(spec=DeploymentPollingWorker)

    now = datetime.now(UTC)
    use_case.execute.return_value = ProjectDeployment(
        project_id=ProjectId("prj_123"),
        provider=DeploymentProvider.RAILWAY,
        service_id="srv_123",
        public_url=None,
        status=DeploymentStatus.BUILDING,
        last_deployed_at=now,
    )

    body = DeployRailwayRequest(
        service_name="custom-service",
        environment_variables={"LOG_LEVEL": "debug"},
    )

    # Act
    resp = await deploy_to_railway(
        project_id="prj_123",
        request=req,
        principal=_principal("usr_123"),
        use_case=use_case,
        worker=worker,
        body=body,
    )

    # Assert
    assert resp.status == DeployStatusEnum.building.value
    assert resp.service_id == "srv_123"
    assert resp.service_name == "custom-service"
    use_case.execute.assert_awaited_once_with(
        _principal("usr_123"),
        OrchestrateCloudDeploymentCommand(
            project_id=ProjectId("prj_123"),
            provider=DeploymentProvider.RAILWAY,
            service_name="custom-service",
            environment_variables={"LOG_LEVEL": "debug"},
        ),
    )
    worker.start_monitoring.assert_called_once_with(
        project_id=ProjectId("prj_123"),
        user_id=UserId("usr_123"),
        provider=DeploymentProvider.RAILWAY,
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_deploy_to_railway_account_not_linked_409() -> None:
    # Arrange
    req = _mock_request(project=_mock_project("prj_123"))
    use_case = AsyncMock(spec=OrchestrateCloudDeploymentUseCase)
    use_case.execute.side_effect = DeploymentAccountNotLinkedError("Cuenta de Railway no vinculada")
    worker = MagicMock(spec=DeploymentPollingWorker)

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await deploy_to_railway(
            project_id="prj_123",
            request=req,
            principal=_principal("usr_123"),
            use_case=use_case,
            worker=worker,
        )

    assert exc_info.value.status_code == 409
    assert "no vinculada" in exc_info.value.detail
    worker.start_monitoring.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_deploy_to_railway_repo_missing_409() -> None:
    # Arrange
    req = _mock_request(project=_mock_project("prj_123"))
    use_case = AsyncMock(spec=OrchestrateCloudDeploymentUseCase)
    use_case.execute.side_effect = DeploymentRepositoryMissingError("Repositorio de GitHub ausente")
    worker = MagicMock(spec=DeploymentPollingWorker)

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await deploy_to_railway(
            project_id="prj_123",
            request=req,
            principal=_principal("usr_123"),
            use_case=use_case,
            worker=worker,
        )

    assert exc_info.value.status_code == 409
    assert "GitHub ausente" in exc_info.value.detail


@pytest.mark.asyncio
@pytest.mark.unit
async def test_deploy_to_railway_config_error_400() -> None:
    # Arrange
    req = _mock_request(project=_mock_project("prj_123"))
    use_case = AsyncMock(spec=OrchestrateCloudDeploymentUseCase)
    use_case.execute.side_effect = DeploymentConfigurationError("Variables de entorno inválidas")
    worker = MagicMock(spec=DeploymentPollingWorker)

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await deploy_to_railway(
            project_id="prj_123",
            request=req,
            principal=_principal("usr_123"),
            use_case=use_case,
            worker=worker,
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
@pytest.mark.unit
async def test_deploy_to_railway_api_error_502() -> None:
    # Arrange
    req = _mock_request(project=_mock_project("prj_123"))
    use_case = AsyncMock(spec=OrchestrateCloudDeploymentUseCase)
    use_case.execute.side_effect = DeploymentApiError("Error 500 de Railway API")
    worker = MagicMock(spec=DeploymentPollingWorker)

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await deploy_to_railway(
            project_id="prj_123",
            request=req,
            principal=_principal("usr_123"),
            use_case=use_case,
            worker=worker,
        )

    assert exc_info.value.status_code == 502


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_project_deployment_success() -> None:
    # Arrange
    req = _mock_request(project=_mock_project("prj_123"))
    use_case = AsyncMock()
    use_case.execute.return_value = True

    # Act
    await delete_project_deployment(
        project_id="prj_123",
        request=req,
        principal=_principal("usr_123"),
        use_case=use_case,
    )

    # Assert
    use_case.execute.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_project_deployment_not_owner_raises_404() -> None:
    # Arrange
    req = _mock_request(project=_mock_project("prj_123"))
    use_case = AsyncMock()

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await delete_project_deployment(
            project_id="prj_123",
            request=req,
            principal=_principal("usr_other"),
            use_case=use_case,
        )

    assert exc_info.value.status_code == 404
