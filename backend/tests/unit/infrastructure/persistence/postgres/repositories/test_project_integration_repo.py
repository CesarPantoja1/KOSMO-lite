from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ulid import ULID

from kosmo.contracts.integrations.deployment import (
    DeploymentProvider,
    DeploymentStatus,
    EnvironmentVariable,
    PortSpec,
    ProjectDeployment,
    VolumeConfig,
)
from kosmo.contracts.integrations.github import (
    CodeSyncLog,
    CodeSyncStatus,
    GitHubSyncStatus,
    ProjectGitHubIntegration,
)
from kosmo.contracts.sdd.ids import ProjectId
from kosmo.infrastructure.persistence.postgres.models import (
    CodeSyncLogModel,
    ProjectIntegrationModel,
)
from kosmo.infrastructure.persistence.postgres.repositories.project_integration_repo import (
    SqlAlchemyCodeSyncLogRepository,
    SqlAlchemyProjectDeploymentRepository,
    SqlAlchemyProjectGitHubIntegrationRepository,
)


def _make_project_integration(
    project_id: str = "prj_01J00000000000000000000001",
    repo_name: str | None = "my-app",
    repo_url: str | None = "https://github.com/octocat/my-app",
    is_public: bool = False,
    default_branch: str = "main",
    last_push_at: datetime | None = None,
    last_commit_hash: str | None = "7f4b82d3e91a",
    sync_status: GitHubSyncStatus = GitHubSyncStatus.SYNCED,
    error_message: str | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> ProjectGitHubIntegration:
    now = datetime.now(UTC)
    return ProjectGitHubIntegration(
        project_id=ProjectId(project_id),
        repo_name=repo_name,
        repo_url=repo_url or "",
        is_public=is_public,
        default_branch=default_branch,
        last_push_at=last_push_at or now,
        last_commit_hash=last_commit_hash,
        sync_status=sync_status,
        error_message=error_message,
        created_at=created_at or now,
        updated_at=updated_at or now,
    )


def _make_async_session_mock(
    returned_model: ProjectIntegrationModel | CodeSyncLogModel | None = None,
    returned_models: list[ProjectIntegrationModel] | list[CodeSyncLogModel] | None = None,
    rowcount: int = 1,
) -> MagicMock:
    mock_session = MagicMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = returned_model
    mock_scalars = MagicMock()
    if returned_models is not None:
        mock_scalars.all.return_value = returned_models
    else:
        mock_scalars.all.return_value = [returned_model] if returned_model else []
    mock_result.scalars.return_value = mock_scalars
    mock_result.rowcount = rowcount

    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()
    return mock_session


@pytest.mark.unit
@pytest.mark.asyncio
async def test_init_raises_without_session_or_factory() -> None:
    # Arrange & Act & Assert
    with pytest.raises(ValueError, match="Se requiere session_factory o session"):
        SqlAlchemyProjectGitHubIntegrationRepository(session_factory=None, session=None)

    with pytest.raises(ValueError, match="Se requiere session_factory o session"):
        SqlAlchemyCodeSyncLogRepository(session_factory=None, session=None)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_save_inserts_new_project_integration_when_none_exists() -> None:
    # Arrange
    integration = _make_project_integration(
        project_id="prj_01J00000000000000000000001",
        repo_name="kosmo-gestion-inventarios",
        repo_url="https://github.com/octocat/kosmo-gestion-inventarios",
        is_public=True,
        default_branch="main",
        sync_status=GitHubSyncStatus.CREATED,
    )
    mock_session = _make_async_session_mock(returned_model=None)
    mock_session_factory = MagicMock(spec=async_sessionmaker)
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    repo = SqlAlchemyProjectGitHubIntegrationRepository(session_factory=mock_session_factory)

    # Act
    result = await repo.save(integration)

    # Assert
    assert result == integration
    mock_session.add.assert_called_once()
    added_model: ProjectIntegrationModel = mock_session.add.call_args[0][0]
    assert added_model.project_id == "prj_01J00000000000000000000001"
    assert added_model.provider == "github"
    assert added_model.repo_name == "kosmo-gestion-inventarios"
    assert added_model.repo_url == "https://github.com/octocat/kosmo-gestion-inventarios"
    assert added_model.is_public is True
    assert added_model.default_branch == "main"
    assert added_model.sync_status == "created"
    mock_session.commit.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_save_updates_existing_project_integration() -> None:
    # Arrange
    now = datetime.now(UTC)
    updated_integration = _make_project_integration(
        project_id="prj_01J00000000000000000000001",
        repo_name="kosmo-inventarios-updated",
        repo_url="https://github.com/octocat/kosmo-inventarios-updated",
        is_public=True,
        last_commit_hash="deadbeef9999",
        sync_status=GitHubSyncStatus.SYNCED,
    )
    existing_model = ProjectIntegrationModel(
        id="pint_01",
        project_id="prj_01J00000000000000000000001",
        provider="github",
        repo_name="kosmo-inventarios-old",
        repo_url="https://github.com/octocat/kosmo-inventarios-old",
        is_public=False,
        default_branch="main",
        last_push_at=now,
        last_commit_hash="oldhash123",
        sync_status="created",
        error_message=None,
        created_at=now,
        updated_at=now,
    )
    mock_session = _make_async_session_mock(returned_model=existing_model)
    mock_session_factory = MagicMock(spec=async_sessionmaker)
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    repo = SqlAlchemyProjectGitHubIntegrationRepository(session_factory=mock_session_factory)

    # Act
    result = await repo.save(updated_integration)

    # Assert
    assert result == updated_integration
    assert existing_model.repo_name == "kosmo-inventarios-updated"
    assert existing_model.repo_url == "https://github.com/octocat/kosmo-inventarios-updated"
    assert existing_model.is_public is True
    assert existing_model.last_commit_hash == "deadbeef9999"
    assert existing_model.sync_status == "synced"
    mock_session.commit.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_by_project_id_returns_entity_when_found() -> None:
    # Arrange
    now = datetime.now(UTC)
    existing_model = ProjectIntegrationModel(
        id="pint_42",
        project_id="prj_01J00000000000000000000042",
        provider="github",
        repo_name="cool-project",
        repo_url="https://github.com/octocat/cool-project",
        is_public=False,
        default_branch="main",
        last_push_at=now,
        last_commit_hash="feedface1111",
        sync_status="synced",
        error_message=None,
        created_at=now,
        updated_at=now,
    )
    mock_session = _make_async_session_mock(returned_model=existing_model)
    mock_session_factory = MagicMock(spec=async_sessionmaker)
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    repo = SqlAlchemyProjectGitHubIntegrationRepository(session_factory=mock_session_factory)

    # Act
    result = await repo.get_by_project_id(ProjectId("prj_01J00000000000000000000042"))

    # Assert
    assert result is not None
    assert result.project_id == ProjectId("prj_01J00000000000000000000042")
    assert result.repo_name == "cool-project"
    assert result.repo_url == "https://github.com/octocat/cool-project"
    assert result.is_public is False
    assert result.default_branch == "main"
    assert result.last_push_at == now
    assert result.last_commit_hash == "feedface1111"
    assert result.sync_status == GitHubSyncStatus.SYNCED
    assert result.created_at == now
    assert result.updated_at == now


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_by_project_id_returns_none_when_not_found() -> None:
    # Arrange
    mock_session = _make_async_session_mock(returned_model=None)
    mock_session_factory = MagicMock(spec=async_sessionmaker)
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    repo = SqlAlchemyProjectGitHubIntegrationRepository(session_factory=mock_session_factory)

    # Act
    result = await repo.get_by_project_id(ProjectId("prj_nonexistent"))

    # Assert
    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_by_project_id_removes_and_returns_true() -> None:
    # Arrange
    mock_session = _make_async_session_mock(rowcount=1)
    mock_session_factory = MagicMock(spec=async_sessionmaker)
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    repo = SqlAlchemyProjectGitHubIntegrationRepository(session_factory=mock_session_factory)

    # Act
    deleted = await repo.delete_by_project_id(ProjectId("prj_01J00000000000000000000001"))

    # Assert
    assert deleted is True
    mock_session.execute.assert_awaited_once()
    mock_session.commit.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_by_project_id_returns_false_when_not_found() -> None:
    # Arrange
    mock_session = _make_async_session_mock(rowcount=0)
    mock_session_factory = MagicMock(spec=async_sessionmaker)
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    repo = SqlAlchemyProjectGitHubIntegrationRepository(session_factory=mock_session_factory)

    # Act
    deleted = await repo.delete_by_project_id(ProjectId("prj_missing"))

    # Assert
    assert deleted is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_repository_with_direct_session_delegates_commit() -> None:
    # Arrange
    mock_session = _make_async_session_mock(returned_model=None)
    repo = SqlAlchemyProjectGitHubIntegrationRepository(session=mock_session)
    integration = _make_project_integration(project_id="prj_trans")

    # Act
    await repo.save(integration)

    # Assert
    mock_session.add.assert_called_once()
    mock_session.commit.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_code_sync_log_repository_add_log_and_get_logs() -> None:
    # Arrange
    now = datetime.now(UTC)
    log_id = ULID()
    log = CodeSyncLog(
        id=log_id,
        project_id=ProjectId("prj_logs_01"),
        commit_sha="abcdef123456",
        status=CodeSyncStatus.SUCCESS,
        message="Push exitoso a main",
        synced_at=now,
    )
    model = CodeSyncLogModel(
        id=str(log_id),
        project_id="prj_logs_01",
        commit_sha="abcdef123456",
        status="success",
        message="Push exitoso a main",
        synced_at=now,
    )
    mock_session = _make_async_session_mock(returned_models=[model])
    mock_session_factory = MagicMock(spec=async_sessionmaker)
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    repo = SqlAlchemyCodeSyncLogRepository(session_factory=mock_session_factory)

    # Act - Add log
    await repo.add_log(log)

    # Assert - Add log
    mock_session.add.assert_called_once()
    mock_session.commit.assert_awaited_once()

    # Act - Get logs
    logs = await repo.get_logs_by_project(ProjectId("prj_logs_01"))

    # Assert - Get logs
    assert len(logs) == 1
    assert logs[0].project_id == ProjectId("prj_logs_01")
    assert logs[0].commit_sha == "abcdef123456"
    assert logs[0].status == CodeSyncStatus.SUCCESS
    assert logs[0].message == "Push exitoso a main"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_in_memory_project_github_integration_repository() -> None:
    # Arrange
    from tests.unit.fakes import (
        InMemoryCodeSyncLogRepository,
        InMemoryProjectGitHubIntegrationRepository,
    )

    repo = InMemoryProjectGitHubIntegrationRepository()
    prj_1 = ProjectId("prj_01")
    prj_2 = ProjectId("prj_02")

    int_1 = _make_project_integration(project_id=str(prj_1), repo_name="repo-1")
    int_2 = _make_project_integration(project_id=str(prj_2), repo_name="repo-2")

    # Act - Save
    await repo.save(int_1)
    await repo.save(int_2)

    # Assert - Retrieval
    assert await repo.get_by_project_id(prj_1) == int_1
    assert await repo.get_by_project_id(prj_2) == int_2

    # Act - Delete
    assert await repo.delete_by_project_id(prj_1) is True
    assert await repo.get_by_project_id(prj_1) is None
    assert await repo.delete_by_project_id(prj_1) is False

    # In-memory CodeSyncLogRepository
    log_repo = InMemoryCodeSyncLogRepository()
    log1 = CodeSyncLog(
        id=ULID(),
        project_id=prj_2,
        commit_sha="sha1",
        status=CodeSyncStatus.SUCCESS,
    )
    log2 = CodeSyncLog(
        id=ULID(),
        project_id=prj_2,
        commit_sha="sha2",
        status=CodeSyncStatus.FAILED,
    )
    await log_repo.add_log(log1)
    await log_repo.add_log(log2)

    logs = await log_repo.get_logs_by_project(prj_2)
    assert len(logs) == 2
    assert logs[0] == log1
    assert logs[1] == log2


def _make_project_deployment(
    project_id: str = "prj_01J00000000000000000000001",
    provider: DeploymentProvider = DeploymentProvider.RAILWAY,
    service_id: str | None = "srv_railway_123",
    public_url: str | None = "https://app.up.railway.app",
    status: DeploymentStatus = DeploymentStatus.BUILDING,
    build_logs_url: str | None = "https://railway.com/logs/123",
    last_deployed_at: datetime | None = None,
    error_message: str | None = None,
    volumes: tuple[VolumeConfig, ...] = (VolumeConfig(mount_path="/data"),),
    ports: tuple[PortSpec, ...] = (PortSpec(port=3000),),
    env_vars: tuple[EnvironmentVariable, ...] = (EnvironmentVariable(key="NODE_ENV", value="production"),),
) -> ProjectDeployment:
    now = datetime.now(UTC)
    return ProjectDeployment(
        project_id=ProjectId(project_id),
        provider=provider,
        service_id=service_id,
        public_url=public_url,
        status=status,
        build_logs_url=build_logs_url,
        last_deployed_at=last_deployed_at or now,
        error_message=error_message,
        volumes=volumes,
        ports=ports,
        env_vars=env_vars,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_deployment_repository_init_raises_without_session_or_factory() -> None:
    # Arrange & Act & Assert
    with pytest.raises(ValueError, match="Se requiere session_factory o session"):
        SqlAlchemyProjectDeploymentRepository(session_factory=None, session=None)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_deployment_repository_save_inserts_when_none_exists() -> None:
    # Arrange
    deployment = _make_project_deployment(
        project_id="prj_01DEPLOY",
        service_id="srv_01NEW",
        public_url="https://new-app.up.railway.app",
        status=DeploymentStatus.BUILDING,
    )
    mock_session = _make_async_session_mock(returned_model=None)
    mock_session_factory = MagicMock(spec=async_sessionmaker)
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    repo = SqlAlchemyProjectDeploymentRepository(session_factory=mock_session_factory)

    # Act
    result = await repo.save(deployment)

    # Assert
    assert result == deployment
    mock_session.add.assert_called_once()
    added_model: ProjectIntegrationModel = mock_session.add.call_args[0][0]
    assert added_model.project_id == "prj_01DEPLOY"
    assert added_model.provider == "railway"
    assert added_model.service_id == "srv_01NEW"
    assert added_model.service_name is None
    assert added_model.public_url == "https://new-app.up.railway.app"
    assert added_model.deploy_status == "building"
    assert len(added_model.volumes) == 1
    assert added_model.volumes[0]["mount_path"] == "/data"
    assert len(added_model.ports) == 1
    assert added_model.ports[0]["port"] == 3000
    assert len(added_model.env_vars) == 1
    assert added_model.env_vars[0]["key"] == "NODE_ENV"
    mock_session.commit.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_deployment_repository_save_updates_existing_deployment() -> None:
    # Arrange
    now = datetime.now(UTC)
    updated_deployment = _make_project_deployment(
        project_id="prj_01DEPLOY",
        service_id="srv_01UPDATED",
        public_url="https://updated-app.up.railway.app",
        status=DeploymentStatus.PUBLISHED,
    )
    existing_model = ProjectIntegrationModel(
        id="pint_deploy_01",
        project_id="prj_01DEPLOY",
        provider="railway",
        service_id="srv_01OLD",
        public_url=None,
        deploy_status="building",
        build_logs_url="https://railway.com/oldlogs",
        last_deployed_at=now,
        error_message=None,
        volumes=[],
        ports=[],
        env_vars=[],
        created_at=now,
        updated_at=now,
    )
    mock_session = _make_async_session_mock(returned_model=existing_model)
    mock_session_factory = MagicMock(spec=async_sessionmaker)
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    repo = SqlAlchemyProjectDeploymentRepository(session_factory=mock_session_factory)

    # Act
    result = await repo.save(updated_deployment)

    # Assert
    assert result == updated_deployment
    assert existing_model.service_id == "srv_01UPDATED"
    assert existing_model.service_name is None
    assert existing_model.public_url == "https://updated-app.up.railway.app"
    assert existing_model.deploy_status == "published"
    assert len(existing_model.volumes) == 1
    mock_session.commit.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_deployment_repository_get_by_project_id_returns_entity() -> None:
    # Arrange
    now = datetime.now(UTC)
    existing_model = ProjectIntegrationModel(
        id="pint_deploy_02",
        project_id="prj_01DEPLOY_FOUND",
        provider="railway",
        service_id="srv_found_123",
        public_url="https://found.up.railway.app",
        deploy_status="published",
        build_logs_url="https://railway.com/logs/found",
        last_deployed_at=now,
        error_message=None,
        volumes=[{"mount_path": "/data", "size_mb": 1024}],
        ports=[{"port": 3000, "protocol": "http"}],
        env_vars=[{"key": "NODE_ENV", "value": "production", "is_secret": False}],
        created_at=now,
        updated_at=now,
    )
    mock_session = _make_async_session_mock(returned_model=existing_model)
    mock_session_factory = MagicMock(spec=async_sessionmaker)
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    repo = SqlAlchemyProjectDeploymentRepository(session_factory=mock_session_factory)

    # Act
    result = await repo.get_by_project_id(ProjectId("prj_01DEPLOY_FOUND"))

    # Assert
    assert result is not None
    assert result.project_id == ProjectId("prj_01DEPLOY_FOUND")
    assert result.provider == DeploymentProvider.RAILWAY
    assert result.service_id == "srv_found_123"
    assert result.service_name is None
    assert result.public_url == "https://found.up.railway.app"
    assert result.status == DeploymentStatus.PUBLISHED
    assert result.build_logs_url == "https://railway.com/logs/found"
    assert len(result.volumes) == 1
    assert result.volumes[0].mount_path == "/data"
    assert result.volumes[0].size_mb == 1024
    assert len(result.ports) == 1
    assert result.ports[0].port == 3000
    assert len(result.env_vars) == 1
    assert result.env_vars[0].key == "NODE_ENV"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_deployment_repository_get_by_project_id_returns_none() -> None:
    # Arrange
    mock_session = _make_async_session_mock(returned_model=None)
    mock_session_factory = MagicMock(spec=async_sessionmaker)
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    repo = SqlAlchemyProjectDeploymentRepository(session_factory=mock_session_factory)

    # Act
    result = await repo.get_by_project_id(ProjectId("prj_missing"))

    # Assert
    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_deployment_repository_delete_by_project_id() -> None:
    # Arrange
    mock_session = _make_async_session_mock(rowcount=1)
    mock_session_factory = MagicMock(spec=async_sessionmaker)
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    repo = SqlAlchemyProjectDeploymentRepository(session_factory=mock_session_factory)

    # Act
    deleted = await repo.delete_by_project_id(ProjectId("prj_del"))

    # Assert
    assert deleted is True
    mock_session.commit.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_deployment_repository_with_direct_session_delegates_commit() -> None:
    # Arrange
    mock_session = _make_async_session_mock(returned_model=None)
    repo = SqlAlchemyProjectDeploymentRepository(session=mock_session)
    deployment = _make_project_deployment(project_id="prj_trans_deploy")

    # Act
    await repo.save(deployment)

    # Assert
    mock_session.add.assert_called_once()
    mock_session.commit.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_in_memory_project_deployment_repository() -> None:
    # Arrange
    from tests.unit.fakes import InMemoryProjectDeploymentRepository

    repo = InMemoryProjectDeploymentRepository()
    prj_1 = ProjectId("prj_dp_1")
    prj_2 = ProjectId("prj_dp_2")

    dep_1 = _make_project_deployment(project_id=str(prj_1), service_id="srv-1")
    dep_2 = _make_project_deployment(project_id=str(prj_2), service_id="srv-2")

    # Act - Save
    await repo.save(dep_1)
    await repo.save(dep_2)

    # Assert - Retrieval
    assert await repo.get_by_project_id(prj_1) == dep_1
    assert await repo.get_by_project_id(prj_2) == dep_2

    # Act - Delete
    assert await repo.delete_by_project_id(prj_1) is True
    assert await repo.get_by_project_id(prj_1) is None
    assert await repo.delete_by_project_id(prj_1) is False
