from __future__ import annotations

import asyncio
import base64
import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from kosmo.application.integrations.execute_ephemeral_validation import (
    EphemeralValidationError,
    ExecuteEphemeralValidationResult,
)
from kosmo.application.integrations.sync_github_repository import (
    SyncGitHubRepositoryCommand,
    SyncGitHubRepositoryUseCase,
)
from kosmo.contracts.integrations.git import GitWorkspacePort
from kosmo.contracts.integrations.github import (
    CodeSyncStatus,
    GitHubRepository,
    GitHubSyncStatus,
    GitHubUser,
    ProjectGitHubIntegration,
    UserGitHubIntegration,
)
from kosmo.contracts.sdd.codegen import CodeWorkspace, ValidationStep
from kosmo.contracts.sdd.ids import ProjectId, UserId, WorkspaceId
from kosmo.infrastructure.git import GitError


@pytest.fixture
def project_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def user_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def github_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def git_workspace() -> MagicMock:
    return MagicMock(spec=GitWorkspacePort)


@pytest.fixture
def workspace_manager() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def cipher() -> MagicMock:
    return MagicMock()


@pytest.fixture
def sync_log_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def use_case(
    project_repo: AsyncMock,
    user_repo: AsyncMock,
    github_client: AsyncMock,
    git_workspace: MagicMock,
    workspace_manager: AsyncMock,
    cipher: MagicMock,
    sync_log_repo: AsyncMock,
) -> SyncGitHubRepositoryUseCase:
    return SyncGitHubRepositoryUseCase(
        project_github_repo=project_repo,
        user_github_repo=user_repo,
        github_client=github_client,
        git_workspace=git_workspace,
        workspace_manager=workspace_manager,
        cipher=cipher,
        sync_log_repo=sync_log_repo,
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_sync_github_repository_incremental_push_success(
    use_case: SyncGitHubRepositoryUseCase,
    project_repo: AsyncMock,
    user_repo: AsyncMock,
    github_client: AsyncMock,
    git_workspace: MagicMock,
    workspace_manager: AsyncMock,
    cipher: MagicMock,
    sync_log_repo: AsyncMock,
) -> None:
    # Arrange
    project_id = ProjectId("proj-existing")
    user_id = UserId("usr-octo")
    previous_push = datetime(2026, 8, 15, 12, 0, 0, tzinfo=UTC)

    existing_integration = ProjectGitHubIntegration(
        project_id=project_id,
        repo_name="kosmo-crm-app",
        repo_url="https://github.com/octocat/kosmo-crm-app.git",
        is_public=False,
        default_branch="main",
        last_push_at=previous_push,
        last_commit_hash="commit_hash_v1",
        sync_status=GitHubSyncStatus.SYNCED,
    )
    project_repo.get_by_project_id.return_value = existing_integration
    project_repo.save.side_effect = lambda integration: integration

    user_repo.get_by_user_id.return_value = UserGitHubIntegration(
        user_id=user_id,
        github_username="octocat",
        encrypted_token=base64.b64encode(b"encrypted_secret_token").decode("utf-8"),
    )
    cipher.decrypt.return_value = b"ghp_real_decrypted_token"

    workspace_manager.ensure_workspace.return_value = CodeWorkspace(
        id=WorkspaceId("ws-proj-1"),
        project_id=project_id,
        workspace_dir="/tmp/workspaces/proj-existing",
    )

    git_workspace.push.return_value = "new_commit_hash_v2"

    cmd = SyncGitHubRepositoryCommand(project_id=project_id)

    # Act
    result = await use_case.execute(cmd, user_id)

    # Assert
    # 1. No debe llamar a create_repository ni check_repository_exists porque es push incremental
    github_client.create_repository.assert_not_called()
    github_client.check_repository_exists.assert_not_called()
    workspace_manager.commit_workspace.assert_awaited_once_with(project_id, "chore: sync project changes to repository")

    # 2. El remoto persistido queda limpio; el token se entrega solo al push.
    git_workspace.remote_add_or_update.assert_called_once_with(
        "/tmp/workspaces/proj-existing",
        "origin",
        "https://github.com/octocat/kosmo-crm-app.git",
    )
    git_workspace.push.assert_called_once_with(
        "/tmp/workspaces/proj-existing",
        "origin",
        branch="main",
        token="ghp_real_decrypted_token",
    )

    # 3. Metadatos y timestamps actualizados
    assert result.sync_status == GitHubSyncStatus.SYNCED
    assert result.last_commit_hash == "new_commit_hash_v2"
    assert result.last_push_at is not None
    assert result.last_push_at > previous_push
    assert result.last_synced_at == result.last_push_at
    assert result.error_message is None

    # 4. Auditoría registrada
    sync_log_repo.add_log.assert_called_once()
    logged_entry = sync_log_repo.add_log.call_args[0][0]
    assert logged_entry.status == CodeSyncStatus.SUCCESS
    assert logged_entry.commit_sha == "new_commit_hash_v2"
    assert "https://github.com/octocat/kosmo-crm-app.git" in logged_entry.message


@pytest.mark.asyncio
@pytest.mark.unit
async def test_sync_github_repository_incremental_push_recovers_from_previous_failure(
    use_case: SyncGitHubRepositoryUseCase,
    project_repo: AsyncMock,
    user_repo: AsyncMock,
    git_workspace: MagicMock,
    workspace_manager: AsyncMock,
    cipher: MagicMock,
) -> None:
    # Arrange
    project_id = ProjectId("proj-failed-before")
    user_id = UserId("usr-octo")

    failed_integration = ProjectGitHubIntegration(
        project_id=project_id,
        repo_name="kosmo-crm-app",
        repo_url="https://github.com/octocat/kosmo-crm-app.git",
        sync_status=GitHubSyncStatus.FAILED,
        error_message="Connection timeout on previous attempt",
    )
    project_repo.get_by_project_id.return_value = failed_integration
    project_repo.save.side_effect = lambda integration: integration

    user_repo.get_by_user_id.return_value = UserGitHubIntegration(
        user_id=user_id,
        github_username="octocat",
        encrypted_token=base64.b64encode(b"encrypted").decode("utf-8"),
    )
    cipher.decrypt.return_value = b"token"
    workspace_manager.ensure_workspace.return_value = CodeWorkspace(
        id=WorkspaceId("ws-1"), project_id=project_id, workspace_dir="/tmp/ws"
    )
    git_workspace.build_authenticated_url.return_value = "https://auth-url"
    git_workspace.push.return_value = "recovered_hash_123"

    cmd = SyncGitHubRepositoryCommand(project_id=project_id)

    # Act
    result = await use_case.execute(cmd, user_id)

    # Assert
    assert result.sync_status == GitHubSyncStatus.SYNCED
    assert result.error_message is None
    assert result.last_commit_hash == "recovered_hash_123"
    assert result.last_push_at is not None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_sync_github_repository_incremental_push_fails_when_git_push_fails(
    use_case: SyncGitHubRepositoryUseCase,
    project_repo: AsyncMock,
    user_repo: AsyncMock,
    git_workspace: MagicMock,
    workspace_manager: AsyncMock,
    cipher: MagicMock,
    sync_log_repo: AsyncMock,
) -> None:
    # Arrange
    project_id = ProjectId("proj-1")
    user_id = UserId("usr-1")

    existing_integration = ProjectGitHubIntegration(
        project_id=project_id,
        repo_name="proj-1-repo",
        repo_url="https://github.com/octocat/proj-1-repo.git",
        sync_status=GitHubSyncStatus.SYNCED,
    )
    project_repo.get_by_project_id.return_value = existing_integration
    project_repo.save.side_effect = lambda integration: integration

    user_repo.get_by_user_id.return_value = UserGitHubIntegration(
        user_id=user_id,
        github_username="octocat",
        encrypted_token=base64.b64encode(b"enc").decode("utf-8"),
    )
    cipher.decrypt.return_value = b"token"
    workspace_manager.ensure_workspace.return_value = CodeWorkspace(
        id=WorkspaceId("ws-1"), project_id=project_id, workspace_dir="/tmp/ws-1"
    )
    git_workspace.build_authenticated_url.return_value = "https://auth-url"
    git_workspace.push.side_effect = GitError("Fallo al ejecutar git push: rejected non-fast-forward")

    cmd = SyncGitHubRepositoryCommand(project_id=project_id)

    # Act & Assert
    with pytest.raises(GitError, match="rejected non-fast-forward"):
        await use_case.execute(cmd, user_id)

    # Verificar que el estado se actualizó a FAILED con el mensaje de error
    saved_states = [call[0][0] for call in project_repo.save.call_args_list]
    final_saved_state = saved_states[-1]
    assert final_saved_state.sync_status == GitHubSyncStatus.FAILED
    assert "rejected non-fast-forward" in (final_saved_state.error_message or "")

    # Verificar log de fallo
    sync_log_repo.add_log.assert_called_once()
    saved_log = sync_log_repo.add_log.call_args[0][0]
    assert saved_log.status == CodeSyncStatus.FAILED
    assert "rejected non-fast-forward" in (saved_log.message or "")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_sync_github_repository_raises_when_user_not_linked(
    use_case: SyncGitHubRepositoryUseCase,
    user_repo: AsyncMock,
) -> None:
    # Arrange
    user_repo.get_by_user_id.return_value = None
    cmd = SyncGitHubRepositoryCommand(project_id=ProjectId("proj-1"))

    # Act & Assert
    with pytest.raises(ValueError) as exc_info:
        await use_case.execute(cmd, UserId("usr-unlinked"))

    assert "vinculada con GitHub" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_sync_github_repository_raises_when_workspace_not_found(
    use_case: SyncGitHubRepositoryUseCase,
    user_repo: AsyncMock,
    workspace_manager: AsyncMock,
) -> None:
    # Arrange
    user_repo.get_by_user_id.return_value = UserGitHubIntegration(
        user_id=UserId("usr-1"),
        github_username="octocat",
        encrypted_token=base64.b64encode(b"enc").decode("utf-8"),
    )
    workspace_manager.ensure_workspace.return_value = None
    cmd = SyncGitHubRepositoryCommand(project_id=ProjectId("proj-1"))

    # Act & Assert
    with pytest.raises(ValueError) as exc_info:
        await use_case.execute(cmd, UserId("usr-1"))

    assert "directorio físico del workspace" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_sync_github_repository_first_push_creates_repo_and_sets_metadata(
    use_case: SyncGitHubRepositoryUseCase,
    project_repo: AsyncMock,
    user_repo: AsyncMock,
    github_client: AsyncMock,
    git_workspace: MagicMock,
    workspace_manager: AsyncMock,
    cipher: MagicMock,
    sync_log_repo: AsyncMock,
) -> None:
    # Arrange
    project_id = ProjectId("proj-initial")
    user_id = UserId("usr-1")

    project_repo.get_by_project_id.return_value = None
    project_repo.save.side_effect = lambda integration: integration

    user_repo.get_by_user_id.return_value = UserGitHubIntegration(
        user_id=user_id,
        github_username="octocat",
        encrypted_token=base64.b64encode(b"enc").decode("utf-8"),
    )
    cipher.decrypt.return_value = b"token"
    workspace_manager.ensure_workspace.return_value = CodeWorkspace(
        id=WorkspaceId("ws-1"), project_id=project_id, workspace_dir="/tmp/ws-initial"
    )

    github_client.get_authenticated_user.return_value = GitHubUser(login="octocat", id=1)
    github_client.check_repository_exists.return_value = False
    github_client.create_repository.return_value = GitHubRepository(
        id=456,
        name="custom-repo-name",
        full_name="octocat/custom-repo-name",
        clone_url="https://github.com/octocat/custom-repo-name.git",
        html_url="https://github.com/octocat/custom-repo-name",
        owner="octocat",
        is_private=False,
    )
    git_workspace.push.return_value = "initial_hash_001"

    cmd = SyncGitHubRepositoryCommand(
        project_id=project_id,
        repo_name="custom-repo-name",
        is_public=True,
        commit_message="feat: initial project generation",
    )

    # Act
    result = await use_case.execute(cmd, user_id)

    # Assert
    github_client.create_repository.assert_called_once_with(
        token="token",
        name="custom-repo-name",
        description="Repositorio sincronizado automáticamente desde KOSMO para proyecto proj-initial",
        is_private=False,
    )
    git_workspace.remote_add_or_update.assert_called_once_with(
        "/tmp/ws-initial", "origin", "https://github.com/octocat/custom-repo-name.git"
    )
    git_workspace.push.assert_called_once_with("/tmp/ws-initial", "origin", branch="main", token="token")

    assert result.sync_status == GitHubSyncStatus.SYNCED
    assert result.repo_url == "https://github.com/octocat/custom-repo-name.git"
    assert result.repo_name == "custom-repo-name"
    assert result.last_commit_hash == "initial_hash_001"
    assert result.last_push_at is not None
    assert result.last_synced_at is not None

    sync_log_repo.add_log.assert_called_once()
    logged_entry = sync_log_repo.add_log.call_args[0][0]
    assert logged_entry.status == CodeSyncStatus.SUCCESS
    assert logged_entry.commit_sha == "initial_hash_001"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_sync_github_repository_fails_when_ephemeral_validation_fails(
    project_repo: AsyncMock,
    user_repo: AsyncMock,
    github_client: AsyncMock,
    git_workspace: MagicMock,
    workspace_manager: AsyncMock,
    cipher: MagicMock,
    sync_log_repo: AsyncMock,
) -> None:
    # Arrange
    project_id = ProjectId("proj-ephem-fail")
    user_id = UserId("usr-1")

    existing_integration = ProjectGitHubIntegration(
        project_id=project_id,
        repo_name="proj-repo",
        repo_url="https://github.com/octocat/proj-repo.git",
        sync_status=GitHubSyncStatus.SYNCED,
    )
    project_repo.get_by_project_id.return_value = existing_integration
    project_repo.save.side_effect = lambda integration: integration

    user_repo.get_by_user_id.return_value = UserGitHubIntegration(
        user_id=user_id,
        github_username="octocat",
        encrypted_token=base64.b64encode(b"enc").decode("utf-8"),
    )
    cipher.decrypt.return_value = b"token"
    workspace_manager.ensure_workspace.return_value = CodeWorkspace(
        id=WorkspaceId("ws-1"), project_id=project_id, workspace_dir="/tmp/ws-1"
    )

    ephemeral_validator = AsyncMock()
    ephemeral_validator.execute.return_value = ExecuteEphemeralValidationResult(
        is_valid=False,
        failed_step=ValidationStep.TESTS,
        error_summary=("Vitest failed with 2 failing tests",),
        steps=(),
    )

    use_case = SyncGitHubRepositoryUseCase(
        project_github_repo=project_repo,
        user_github_repo=user_repo,
        github_client=github_client,
        git_workspace=git_workspace,
        workspace_manager=workspace_manager,
        cipher=cipher,
        sync_log_repo=sync_log_repo,
        ephemeral_validator=ephemeral_validator,
    )

    cmd = SyncGitHubRepositoryCommand(project_id=project_id)

    # Act & Assert
    with pytest.raises(EphemeralValidationError) as exc_info:
        await use_case.execute(cmd, user_id)

    assert "Validación efímera fallida en el paso 'tests'" in str(exc_info.value)
    # Git push no debió ejecutarse
    git_workspace.push.assert_not_called()

    # Estado actualizado a FAILED
    saved_states = [call[0][0] for call in project_repo.save.call_args_list]
    final_saved_state = saved_states[-1]
    assert final_saved_state.sync_status == GitHubSyncStatus.FAILED
    assert "Validación efímera fallida" in (final_saved_state.error_message or "")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_sync_github_repository_validates_before_creating_initial_repository(
    project_repo: AsyncMock,
    user_repo: AsyncMock,
    github_client: AsyncMock,
    git_workspace: MagicMock,
    workspace_manager: AsyncMock,
    cipher: MagicMock,
    sync_log_repo: AsyncMock,
) -> None:
    # Arrange
    project_id = ProjectId("proj-no-remote-side-effect")
    user_id = UserId("usr-1")
    project_repo.get_by_project_id.return_value = None
    project_repo.save.side_effect = lambda integration: integration
    user_repo.get_by_user_id.return_value = UserGitHubIntegration(
        user_id=user_id,
        github_username="octocat",
        encrypted_token=base64.b64encode(b"enc").decode("utf-8"),
    )
    cipher.decrypt.return_value = b"token"
    workspace_manager.ensure_workspace.return_value = CodeWorkspace(
        id=WorkspaceId("ws-1"), project_id=project_id, workspace_dir="/tmp/ws-initial"
    )
    ephemeral_validator = AsyncMock()
    ephemeral_validator.execute.return_value = ExecuteEphemeralValidationResult(
        is_valid=False,
        failed_step=ValidationStep.TYPECHECK,
        error_summary=("src/lib/site.ts: Unterminated string literal",),
        steps=(),
    )
    use_case = SyncGitHubRepositoryUseCase(
        project_github_repo=project_repo,
        user_github_repo=user_repo,
        github_client=github_client,
        git_workspace=git_workspace,
        workspace_manager=workspace_manager,
        cipher=cipher,
        sync_log_repo=sync_log_repo,
        ephemeral_validator=ephemeral_validator,
    )

    # Act & Assert
    with pytest.raises(EphemeralValidationError):
        await use_case.execute(SyncGitHubRepositoryCommand(project_id=project_id), user_id)

    github_client.get_authenticated_user.assert_not_called()
    github_client.create_repository.assert_not_called()
    github_client.check_repository_exists.assert_not_called()
    git_workspace.push.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_sync_github_repository_proceeds_when_ephemeral_validation_passes(
    project_repo: AsyncMock,
    user_repo: AsyncMock,
    github_client: AsyncMock,
    git_workspace: MagicMock,
    workspace_manager: AsyncMock,
    cipher: MagicMock,
    sync_log_repo: AsyncMock,
) -> None:
    # Arrange
    project_id = ProjectId("proj-ephem-pass")
    user_id = UserId("usr-1")

    existing_integration = ProjectGitHubIntegration(
        project_id=project_id,
        repo_name="proj-repo",
        repo_url="https://github.com/octocat/proj-repo.git",
        sync_status=GitHubSyncStatus.SYNCED,
    )
    project_repo.get_by_project_id.return_value = existing_integration
    project_repo.save.side_effect = lambda integration: integration

    user_repo.get_by_user_id.return_value = UserGitHubIntegration(
        user_id=user_id,
        github_username="octocat",
        encrypted_token=base64.b64encode(b"enc").decode("utf-8"),
    )
    cipher.decrypt.return_value = b"token"
    workspace_manager.ensure_workspace.return_value = CodeWorkspace(
        id=WorkspaceId("ws-1"), project_id=project_id, workspace_dir="/tmp/ws-1"
    )
    git_workspace.build_authenticated_url.return_value = "https://auth-url"
    git_workspace.push.return_value = "valid_commit_hash_789"

    ephemeral_validator = AsyncMock()
    ephemeral_validator.execute.return_value = ExecuteEphemeralValidationResult(
        is_valid=True,
        steps=(),
        error_summary=(),
    )

    use_case = SyncGitHubRepositoryUseCase(
        project_github_repo=project_repo,
        user_github_repo=user_repo,
        github_client=github_client,
        git_workspace=git_workspace,
        workspace_manager=workspace_manager,
        cipher=cipher,
        sync_log_repo=sync_log_repo,
        ephemeral_validator=ephemeral_validator,
    )

    cmd = SyncGitHubRepositoryCommand(project_id=project_id)

    # Act
    result = await use_case.execute(cmd, user_id)

    # Assert
    ephemeral_validator.execute.assert_called_once()
    git_workspace.push.assert_called_once()
    assert result.sync_status == GitHubSyncStatus.SYNCED
    assert result.last_commit_hash == "valid_commit_hash_789"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_sync_github_repository_uses_project_name_in_description(
    use_case: SyncGitHubRepositoryUseCase,
    project_repo: AsyncMock,
    user_repo: AsyncMock,
    github_client: AsyncMock,
    git_workspace: MagicMock,
    workspace_manager: AsyncMock,
    cipher: MagicMock,
) -> None:
    # Arrange
    user_id = UserId("usr-name-test")
    project_id = ProjectId("prj_01M181HX5KGENR176BKY1FJY13")

    user_repo.get_by_user_id.return_value = UserGitHubIntegration(
        user_id=user_id,
        github_username="octocat",
        encrypted_token=base64.b64encode(b"ciphertext").decode("utf-8"),
    )
    cipher.decrypt.return_value = b"token"
    workspace_manager.ensure_workspace.return_value = CodeWorkspace(
        id=WorkspaceId("ws-name"),
        project_id=project_id,
        workspace_dir="/tmp/ws-name",
    )
    project_repo.get_by_project_id.return_value = None
    github_client.get_authenticated_user.return_value = GitHubUser(id=12345, login="octocat", name="The Octocat")
    github_client.check_repository_exists.return_value = False
    github_client.create_repository.return_value = GitHubRepository(
        id=999,
        name="project-prj_01M181HX5KGENR176BKY1FJY13",
        full_name="octocat/project-prj_01M181HX5KGENR176BKY1FJY13",
        clone_url="https://github.com/octocat/repo.git",
        html_url="https://github.com/octocat/repo",
        owner="octocat",
        is_private=False,
    )
    git_workspace.build_authenticated_url.return_value = "https://auth-url"
    git_workspace.push.return_value = "hash123"

    cmd = SyncGitHubRepositoryCommand(
        project_id=project_id,
        project_name="Sistema de Gestión Hospitalaria",
    )

    # Act
    await use_case.execute(cmd, user_id)

    # Assert
    github_client.create_repository.assert_called_once_with(
        token="token",
        name=f"project-{project_id}",
        description=(
            "Repositorio sincronizado automáticamente desde KOSMO para proyecto Sistema de Gestión Hospitalaria"
        ),
        is_private=False,
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_sync_github_repository_resolves_project_name_from_sdd_project_repo(
    project_repo: AsyncMock,
    user_repo: AsyncMock,
    github_client: AsyncMock,
    git_workspace: MagicMock,
    workspace_manager: AsyncMock,
    cipher: MagicMock,
    sync_log_repo: AsyncMock,
) -> None:
    # Arrange
    user_id = UserId("usr-resolve-test")
    project_id = ProjectId("prj_999")

    sdd_project_repo = AsyncMock()
    mock_sdd_project = MagicMock()
    mock_sdd_project.name = "Plataforma Educativa"
    sdd_project_repo.by_id.return_value = mock_sdd_project

    use_case = SyncGitHubRepositoryUseCase(
        project_github_repo=project_repo,
        user_github_repo=user_repo,
        github_client=github_client,
        git_workspace=git_workspace,
        workspace_manager=workspace_manager,
        cipher=cipher,
        sync_log_repo=sync_log_repo,
        project_repo=sdd_project_repo,
    )

    user_repo.get_by_user_id.return_value = UserGitHubIntegration(
        user_id=user_id,
        github_username="octocat",
        encrypted_token=base64.b64encode(b"ciphertext").decode("utf-8"),
    )
    cipher.decrypt.return_value = b"token"
    workspace_manager.ensure_workspace.return_value = CodeWorkspace(
        id=WorkspaceId("ws-resolve"),
        project_id=project_id,
        workspace_dir="/tmp/ws-resolve",
    )
    project_repo.get_by_project_id.return_value = None
    github_client.get_authenticated_user.return_value = GitHubUser(id=12345, login="octocat", name="The Octocat")
    github_client.check_repository_exists.return_value = False
    github_client.create_repository.return_value = GitHubRepository(
        id=999,
        name=f"project-{project_id}",
        full_name=f"octocat/project-{project_id}",
        clone_url="https://github.com/octocat/repo.git",
        html_url="https://github.com/octocat/repo",
        owner="octocat",
        is_private=False,
    )
    git_workspace.build_authenticated_url.return_value = "https://auth-url"
    git_workspace.push.return_value = "hash123"

    cmd = SyncGitHubRepositoryCommand(project_id=project_id)

    # Act
    await use_case.execute(cmd, user_id)

    # Assert
    sdd_project_repo.by_id.assert_called_once_with(project_id)
    github_client.create_repository.assert_called_once_with(
        token="token",
        name=f"project-{project_id}",
        description="Repositorio sincronizado automáticamente desde KOSMO para proyecto Plataforma Educativa",
        is_private=False,
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_sync_github_repository_rejects_private_repository(
    use_case: SyncGitHubRepositoryUseCase,
) -> None:
    # Arrange
    user_id = UserId("usr-123")
    cmd = SyncGitHubRepositoryCommand(
        project_id=ProjectId("prj-private-test"),
        is_public=False,
    )

    # Act & Assert
    with pytest.raises(ValueError) as exc_info:
        await use_case.execute(cmd, user_id)

    assert "No se permiten repositorios privados" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_sync_github_repository_push_executes_in_thread_without_blocking_event_loop(
    use_case: SyncGitHubRepositoryUseCase,
    project_repo: AsyncMock,
    user_repo: AsyncMock,
    git_workspace: MagicMock,
    workspace_manager: AsyncMock,
    cipher: MagicMock,
) -> None:
    # Arrange
    project_id = ProjectId("proj-thread-test")
    user_id = UserId("usr-thread")

    existing_integration = ProjectGitHubIntegration(
        project_id=project_id,
        repo_name="thread-app",
        repo_url="https://github.com/octocat/thread-app.git",
        is_public=True,
        default_branch="main",
        sync_status=GitHubSyncStatus.SYNCED,
    )
    project_repo.get_by_project_id.return_value = existing_integration
    project_repo.save.side_effect = lambda integration: integration

    user_repo.get_by_user_id.return_value = UserGitHubIntegration(
        user_id=user_id,
        github_username="octocat",
        encrypted_token=base64.b64encode(b"token").decode("utf-8"),
    )
    cipher.decrypt.return_value = b"decrypted_token"

    workspace_manager.ensure_workspace.return_value = CodeWorkspace(
        id=WorkspaceId("ws-1"),
        project_id=project_id,
        workspace_dir="/tmp/workspaces/proj-thread-test",
    )

    # Simulate a slow network push (50ms)
    def _slow_push(*_args: object, **_kwargs: object) -> str:
        time.sleep(0.05)
        return "commit_sha_threaded"

    git_workspace.push.side_effect = _slow_push

    cmd = SyncGitHubRepositoryCommand(project_id=project_id)

    # Concurrently running coroutine on event loop
    loop_ticks = 0

    async def _event_loop_ticker() -> None:
        nonlocal loop_ticks
        for _ in range(3):
            await asyncio.sleep(0.01)
            loop_ticks += 1

    # Act: run use case concurrently with ticker
    sync_task = asyncio.create_task(use_case.execute(cmd, user_id))
    ticker_task = asyncio.create_task(_event_loop_ticker())

    res, _ = await asyncio.gather(sync_task, ticker_task)

    # Assert
    assert res.last_commit_hash == "commit_sha_threaded"
    assert loop_ticks >= 1, "The event loop must remain unblocked while git push executes in thread"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_sync_github_repository_adquiere_y_libera_workspace_lock(
    use_case: SyncGitHubRepositoryUseCase,
    project_repo: AsyncMock,
    user_repo: AsyncMock,
    git_workspace: MagicMock,
    workspace_manager: AsyncMock,
    cipher: MagicMock,
) -> None:
    project_id = ProjectId("proj-lock-sync-test")
    user_id = UserId("usr-123")

    project_repo.get_by_project_id.return_value = ProjectGitHubIntegration(
        project_id=project_id,
        repo_url="https://github.com/octocat/my-repo.git",
        repo_name="my-repo",
        sync_status=GitHubSyncStatus.SYNCED,
    )
    user_repo.get_by_user_id.return_value = UserGitHubIntegration(
        user_id=user_id,
        github_username="octocat",
        encrypted_token=base64.b64encode(b"token").decode("utf-8"),
    )
    cipher.decrypt.return_value = b"decrypted_token"
    workspace_manager.ensure_workspace.return_value = CodeWorkspace(
        id=WorkspaceId("ws-1"),
        project_id=project_id,
        workspace_dir="/tmp/workspaces/proj-lock-sync-test",
    )
    git_workspace.push.return_value = "commit_sha_123"

    cmd = SyncGitHubRepositoryCommand(project_id=project_id)
    await use_case.execute(cmd, user_id)

    workspace_manager.acquire_lock.assert_awaited_once_with(project_id)
    workspace_manager.release_lock.assert_awaited_once_with(project_id)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_sync_github_repository_libera_workspace_lock_en_error(
    use_case: SyncGitHubRepositoryUseCase,
    user_repo: AsyncMock,
    workspace_manager: AsyncMock,
) -> None:
    project_id = ProjectId("proj-lock-fail-test")
    user_id = UserId("usr-123")

    user_repo.get_by_user_id.return_value = None

    cmd = SyncGitHubRepositoryCommand(project_id=project_id)
    with pytest.raises(ValueError, match="no tiene su cuenta vinculada"):
        await use_case.execute(cmd, user_id)

    workspace_manager.acquire_lock.assert_awaited_once_with(project_id)
    workspace_manager.release_lock.assert_awaited_once_with(project_id)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_sync_github_repository_skip_lock_and_skip_validation(
    use_case: SyncGitHubRepositoryUseCase,
    project_repo: AsyncMock,
    user_repo: AsyncMock,
    git_workspace: MagicMock,
    workspace_manager: AsyncMock,
    cipher: MagicMock,
) -> None:
    # Arrange
    project_id = ProjectId("proj-skip-lock-test")
    user_id = UserId("usr-123")

    project_repo.get_by_project_id.return_value = ProjectGitHubIntegration(
        project_id=project_id,
        repo_url="https://github.com/octocat/my-repo.git",
        repo_name="my-repo",
        sync_status=GitHubSyncStatus.SYNCED,
    )
    project_repo.save.side_effect = lambda integration: integration
    user_repo.get_by_user_id.return_value = UserGitHubIntegration(
        user_id=user_id,
        github_username="octocat",
        encrypted_token=base64.b64encode(b"token").decode("utf-8"),
    )
    cipher.decrypt.return_value = b"decrypted_token"
    workspace_manager.ensure_workspace.return_value = CodeWorkspace(
        id=WorkspaceId("ws-1"),
        project_id=project_id,
        workspace_dir="/tmp/workspaces/proj-skip-lock-test",
    )
    git_workspace.push.return_value = "commit_sha_skip"

    cmd = SyncGitHubRepositoryCommand(
        project_id=project_id,
        skip_lock=True,
        skip_validation=True,
    )

    # Act
    result = await use_case.execute(cmd, user_id)

    # Assert
    workspace_manager.acquire_lock.assert_not_called()
    workspace_manager.release_lock.assert_not_called()
    assert result.last_commit_hash == "commit_sha_skip"
