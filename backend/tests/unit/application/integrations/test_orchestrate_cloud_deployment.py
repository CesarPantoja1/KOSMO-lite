import base64
from unittest.mock import AsyncMock, MagicMock

import pytest

from kosmo.application.integrations.orchestrate_cloud_deployment import (
    OrchestrateCloudDeploymentCommand,
    OrchestrateCloudDeploymentUseCase,
)
from kosmo.contracts.auth.principal import Principal
from kosmo.contracts.auth.secrets import EncryptedSecret
from kosmo.contracts.integrations.deployment import (
    DeploymentAccountNotLinkedError,
    DeploymentAuthenticationError,
    DeploymentOAuthToken,
    DeploymentPreconditionError,
    DeploymentProvider,
    DeploymentRepositoryMissingError,
    DeploymentStatus,
    ProjectDeployment,
    UserDeploymentIntegration,
    VolumeConfig,
)
from kosmo.contracts.integrations.github import (
    GitHubSyncStatus,
    ProjectGitHubIntegration,
)
from kosmo.contracts.sdd.ids import ProjectId, UserId
from kosmo.infrastructure.security.fernet_vault import FernetSecretCipher
from tests.unit.fakes import (
    InMemoryProjectDeploymentRepository,
    InMemoryProjectGitHubIntegrationRepository,
    InMemoryUserDeploymentIntegrationRepository,
)


@pytest.fixture
def mock_project_deployment_repo():
    return AsyncMock()


@pytest.fixture
def mock_user_deployment_repo():
    return AsyncMock()


@pytest.fixture
def mock_project_github_repo():
    return AsyncMock()


@pytest.fixture
def mock_deployment_client():
    return AsyncMock()


@pytest.fixture
def mock_cipher():
    return MagicMock()


@pytest.fixture
def principal():
    return Principal(subject="usr_deployer_01")


@pytest.fixture
def use_case(
    mock_project_deployment_repo,
    mock_user_deployment_repo,
    mock_project_github_repo,
    mock_deployment_client,
    mock_cipher,
):
    return OrchestrateCloudDeploymentUseCase(
        project_deployment_repo=mock_project_deployment_repo,
        user_deployment_repo=mock_user_deployment_repo,
        project_github_repo=mock_project_github_repo,
        deployment_client=mock_deployment_client,
        cipher=mock_cipher,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrate_deployment_success_initial(
    use_case: OrchestrateCloudDeploymentUseCase,
    mock_project_deployment_repo: AsyncMock,
    mock_user_deployment_repo: AsyncMock,
    mock_project_github_repo: AsyncMock,
    mock_deployment_client: AsyncMock,
    mock_cipher: MagicMock,
    principal: Principal,
):
    # Arrange
    project_id = ProjectId("prj_inventory_01")
    cmd = OrchestrateCloudDeploymentCommand(
        project_id=project_id,
        service_name="inventario-produccion",
        environment_variables={"CUSTOM_VAR": "custom_val"},
    )

    # 1. User integration exists with encrypted token
    mock_user_deployment_repo.get_by_user_id.return_value = UserDeploymentIntegration(
        user_id=UserId(principal.subject),
        provider=DeploymentProvider.RAILWAY,
        encrypted_token=base64.b64encode(b"ciphertext_rw").decode("utf-8"),
    )
    mock_cipher.decrypt.return_value = b"decrypted_railway_token"

    # 2. GitHub repo exists and is synced
    mock_project_github_repo.get_by_project_id.return_value = ProjectGitHubIntegration(
        project_id=project_id,
        repo_name="inventory-app",
        repo_url="https://github.com/octocat/inventory-app",
        sync_status=GitHubSyncStatus.SYNCED,
    )

    # 3. No existing deployment in Railway
    mock_project_deployment_repo.get_by_project_id.return_value = None

    # 4. Railway client responses
    mock_deployment_client.create_service.return_value = "srv_railway_999"
    mock_deployment_client.configure_volume.return_value = None
    mock_deployment_client.trigger_deployment.return_value = None

    # Act
    result = await use_case.execute(principal, cmd)

    # Assert
    mock_user_deployment_repo.get_by_user_id.assert_called_once_with(
        UserId("usr_deployer_01"), DeploymentProvider.RAILWAY
    )
    mock_cipher.decrypt.assert_called_once_with(EncryptedSecret(ciphertext=b"ciphertext_rw"))
    mock_project_github_repo.get_by_project_id.assert_called_once_with(project_id)

    # Verifica llamadas a Railway client
    mock_deployment_client.create_service.assert_called_once()
    create_call_args = mock_deployment_client.create_service.call_args[1]
    assert create_call_args["token"] == "decrypted_railway_token"
    assert create_call_args["repo_url"] == "https://github.com/octocat/inventory-app"
    assert create_call_args["service_name"] == "inventario-produccion"
    assert any(ev.key == "CUSTOM_VAR" and ev.value == "custom_val" for ev in create_call_args["env_vars"])
    assert any(ev.key == "DATABASE_URL" and ev.value == "file:/data/db.sqlite" for ev in create_call_args["env_vars"])

    mock_deployment_client.configure_volume.assert_called_once_with(
        token="decrypted_railway_token",
        service_id="srv_railway_999",
        volume=VolumeConfig(mount_path="/data", size_mb=512),
    )
    mock_deployment_client.trigger_deployment.assert_called_once_with(
        token="decrypted_railway_token",
        service_id="srv_railway_999",
        commit_sha=None,
    )

    # Persistencia
    mock_project_deployment_repo.save.assert_called_once()
    saved: ProjectDeployment = mock_project_deployment_repo.save.call_args[0][0]
    assert saved.project_id == project_id
    assert saved.provider == DeploymentProvider.RAILWAY
    assert saved.service_id == "srv_railway_999"
    assert saved.service_name == "inventario-produccion"
    assert saved.status == DeploymentStatus.BUILDING
    assert result == saved


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrate_deployment_reuses_existing_service_id(
    use_case: OrchestrateCloudDeploymentUseCase,
    mock_project_deployment_repo: AsyncMock,
    mock_user_deployment_repo: AsyncMock,
    mock_project_github_repo: AsyncMock,
    mock_deployment_client: AsyncMock,
    mock_cipher: MagicMock,
    principal: Principal,
):
    # Arrange
    project_id = ProjectId("prj_existing_01")
    cmd = OrchestrateCloudDeploymentCommand(project_id=project_id)

    mock_user_deployment_repo.get_by_user_id.return_value = UserDeploymentIntegration(
        user_id=UserId(principal.subject),
        provider=DeploymentProvider.RAILWAY,
        encrypted_token=base64.b64encode(b"ciphertext_rw").decode("utf-8"),
    )
    mock_cipher.decrypt.return_value = b"decrypted_token"

    mock_project_github_repo.get_by_project_id.return_value = ProjectGitHubIntegration(
        project_id=project_id,
        repo_name="inventory-app",
        repo_url="https://github.com/octocat/inventory-app",
        sync_status=GitHubSyncStatus.SYNCED,
    )

    # Existing deployment with already created service
    mock_project_deployment_repo.get_by_project_id.return_value = ProjectDeployment(
        project_id=project_id,
        provider=DeploymentProvider.RAILWAY,
        service_id="srv_already_existing_123",
        status=DeploymentStatus.PUBLISHED,
        public_url="https://inventory.up.railway.app",
    )

    # Act
    result = await use_case.execute(principal, cmd)

    # Assert
    # No vuelve a llamar create_service, reutiliza srv_already_existing_123
    mock_deployment_client.create_service.assert_not_called()
    # No reconfigura el volumen en un re-deploy (ya está configurado del primer despliegue)
    mock_deployment_client.configure_volume.assert_not_called()
    # Sí dispara un nuevo despliegue
    mock_deployment_client.trigger_deployment.assert_called_once_with(
        token="decrypted_token",
        service_id="srv_already_existing_123",
        commit_sha=None,
    )
    assert result.service_id == "srv_already_existing_123"
    assert result.status == DeploymentStatus.BUILDING


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrate_deployment_raises_when_account_not_linked(
    use_case: OrchestrateCloudDeploymentUseCase,
    mock_user_deployment_repo: AsyncMock,
    principal: Principal,
):
    # Arrange
    cmd = OrchestrateCloudDeploymentCommand(project_id=ProjectId("prj_01"))
    mock_user_deployment_repo.get_by_user_id.return_value = None

    # Act & Assert
    with pytest.raises(DeploymentAccountNotLinkedError, match="no está vinculada"):
        await use_case.execute(principal, cmd)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrate_deployment_raises_when_github_repo_missing(
    use_case: OrchestrateCloudDeploymentUseCase,
    mock_user_deployment_repo: AsyncMock,
    mock_project_github_repo: AsyncMock,
    mock_cipher: MagicMock,
    principal: Principal,
):
    # Arrange
    cmd = OrchestrateCloudDeploymentCommand(project_id=ProjectId("prj_01"))
    mock_user_deployment_repo.get_by_user_id.return_value = UserDeploymentIntegration(
        user_id=UserId(principal.subject),
        provider=DeploymentProvider.RAILWAY,
        encrypted_token=base64.b64encode(b"ciphertext").decode("utf-8"),
    )
    mock_cipher.decrypt.return_value = b"token"
    mock_project_github_repo.get_by_project_id.return_value = None

    # Act & Assert
    with pytest.raises(DeploymentRepositoryMissingError, match="no cuenta con un repositorio remoto de GitHub"):
        await use_case.execute(principal, cmd)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrate_deployment_raises_when_github_repo_not_created(
    use_case: OrchestrateCloudDeploymentUseCase,
    mock_user_deployment_repo: AsyncMock,
    mock_project_github_repo: AsyncMock,
    mock_cipher: MagicMock,
    principal: Principal,
):
    # Arrange
    cmd = OrchestrateCloudDeploymentCommand(project_id=ProjectId("prj_01"))
    mock_user_deployment_repo.get_by_user_id.return_value = UserDeploymentIntegration(
        user_id=UserId(principal.subject),
        provider=DeploymentProvider.RAILWAY,
        encrypted_token=base64.b64encode(b"ciphertext").decode("utf-8"),
    )
    mock_cipher.decrypt.return_value = b"token"
    mock_project_github_repo.get_by_project_id.return_value = ProjectGitHubIntegration(
        project_id=ProjectId("prj_01"),
        sync_status=GitHubSyncStatus.NOT_CREATED,
        repo_url="",
    )

    # Act & Assert
    with pytest.raises(DeploymentRepositoryMissingError, match="no cuenta con un repositorio remoto de GitHub"):
        await use_case.execute(principal, cmd)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrate_deployment_handles_decryption_failure(
    use_case: OrchestrateCloudDeploymentUseCase,
    mock_user_deployment_repo: AsyncMock,
    mock_cipher: MagicMock,
    principal: Principal,
):
    # Arrange
    cmd = OrchestrateCloudDeploymentCommand(project_id=ProjectId("prj_01"))
    mock_user_deployment_repo.get_by_user_id.return_value = UserDeploymentIntegration(
        user_id=UserId(principal.subject),
        provider=DeploymentProvider.RAILWAY,
        encrypted_token="corrupted-base64",
    )
    mock_cipher.decrypt.side_effect = Exception("Decryption error")

    # Act & Assert
    with pytest.raises(DeploymentAuthenticationError, match="Error al descifrar"):
        await use_case.execute(principal, cmd)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrate_deployment_full_integration_with_fakes():
    # Arrange
    master_key = FernetSecretCipher.generate_master_key()
    cipher = FernetSecretCipher(master_key)

    user_repo = InMemoryUserDeploymentIntegrationRepository()
    project_repo = InMemoryProjectDeploymentRepository()
    github_repo = InMemoryProjectGitHubIntegrationRepository()

    principal = Principal(subject="usr_full_test")
    project_id = ProjectId("prj_full_test")

    # Seed user integration
    enc = cipher.encrypt(b"secret-railway-api-token")
    enc_token = base64.b64encode(enc.ciphertext).decode("utf-8")
    await user_repo.save(
        UserDeploymentIntegration(
            user_id=UserId("usr_full_test"),
            provider=DeploymentProvider.RAILWAY,
            encrypted_token=enc_token,
        )
    )

    # Seed GitHub integration
    await github_repo.save(
        ProjectGitHubIntegration(
            project_id=project_id,
            repo_name="my-cool-app",
            repo_url="https://github.com/octocat/my-cool-app",
            sync_status=GitHubSyncStatus.SYNCED,
        )
    )

    mock_client = AsyncMock()
    mock_client.create_service.return_value = "srv_live_123"

    use_case = OrchestrateCloudDeploymentUseCase(
        project_deployment_repo=project_repo,
        user_deployment_repo=user_repo,
        project_github_repo=github_repo,
        deployment_client=mock_client,
        cipher=cipher,
    )

    # Act
    cmd = OrchestrateCloudDeploymentCommand(project_id=project_id)
    deployment = await use_case.execute(principal, cmd)

    # Assert
    assert deployment.service_id == "srv_live_123"
    assert deployment.status == DeploymentStatus.BUILDING

    # Check persistence
    persisted = await project_repo.get_by_project_id(project_id)
    assert persisted is not None
    assert persisted.service_id == "srv_live_123"
    assert persisted.status == DeploymentStatus.BUILDING


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrate_deployment_auto_refreshes_token_on_auth_error():
    # Arrange
    master_key = FernetSecretCipher.generate_master_key()
    cipher = FernetSecretCipher(master_key)
    project_repo = InMemoryProjectDeploymentRepository()
    user_repo = InMemoryUserDeploymentIntegrationRepository()
    github_repo = InMemoryProjectGitHubIntegrationRepository()

    principal = Principal(subject="usr_refresh_test")
    project_id = ProjectId("prj_refresh_test")

    # Seed user integration with access token and refresh token
    enc_access = base64.b64encode(cipher.encrypt(b"expired-access-token").ciphertext).decode("utf-8")
    enc_refresh = base64.b64encode(cipher.encrypt(b"valid-refresh-token").ciphertext).decode("utf-8")
    await user_repo.save(
        UserDeploymentIntegration(
            user_id=UserId("usr_refresh_test"),
            provider=DeploymentProvider.RAILWAY,
            encrypted_token=enc_access,
            encrypted_refresh_token=enc_refresh,
            provider_username="Jane Developer",
        )
    )

    await github_repo.save(
        ProjectGitHubIntegration(
            project_id=project_id,
            repo_name="refresh-app",
            repo_url="https://github.com/octocat/refresh-app",
            sync_status=GitHubSyncStatus.SYNCED,
        )
    )

    mock_client = AsyncMock()
    # First create_service fails with DeploymentAuthenticationError, then on second attempt succeeds
    mock_client.create_service.side_effect = [
        DeploymentAuthenticationError("Token expired"),
        "srv_new_refreshed_123",
    ]
    mock_client.refresh_access_token.return_value = DeploymentOAuthToken(
        access_token="new-refreshed-token",
        refresh_token="rotated-refresh-token",
        expires_in=3600,
    )

    use_case = OrchestrateCloudDeploymentUseCase(
        project_deployment_repo=project_repo,
        user_deployment_repo=user_repo,
        project_github_repo=github_repo,
        deployment_client=mock_client,
        cipher=cipher,
    )

    # Act
    cmd = OrchestrateCloudDeploymentCommand(project_id=project_id)
    deployment = await use_case.execute(principal, cmd)

    # Assert
    assert deployment.service_id == "srv_new_refreshed_123"
    assert deployment.status == DeploymentStatus.BUILDING
    mock_client.refresh_access_token.assert_called_once_with("valid-refresh-token")

    # Verify that the new access token and rotated refresh token were persisted
    updated_user_int = await user_repo.get_by_user_id(UserId("usr_refresh_test"), DeploymentProvider.RAILWAY)
    assert updated_user_int is not None
    assert updated_user_int.encrypted_refresh_token is not None
    decrypted_new_token = cipher.decrypt(
        EncryptedSecret(ciphertext=base64.b64decode(updated_user_int.encrypted_token.encode("utf-8")))
    ).decode("utf-8")
    assert decrypted_new_token == "new-refreshed-token"
    decrypted_new_rt = cipher.decrypt(
        EncryptedSecret(ciphertext=base64.b64decode(updated_user_int.encrypted_refresh_token.encode("utf-8")))
    ).decode("utf-8")
    assert decrypted_new_rt == "rotated-refresh-token"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrate_deployment_passes_last_commit_hash(
    use_case: OrchestrateCloudDeploymentUseCase,
    mock_project_deployment_repo: AsyncMock,
    mock_user_deployment_repo: AsyncMock,
    mock_project_github_repo: AsyncMock,
    mock_deployment_client: AsyncMock,
    mock_cipher: MagicMock,
    principal: Principal,
):
    project_id = ProjectId("prj_commit_test_01")
    cmd = OrchestrateCloudDeploymentCommand(project_id=project_id)

    mock_user_deployment_repo.get_by_user_id.return_value = UserDeploymentIntegration(
        user_id=UserId(principal.subject),
        provider=DeploymentProvider.RAILWAY,
        encrypted_token=base64.b64encode(b"ciphertext_rw").decode("utf-8"),
    )
    mock_cipher.decrypt.return_value = b"decrypted_railway_token"

    mock_project_github_repo.get_by_project_id.return_value = ProjectGitHubIntegration(
        project_id=project_id,
        repo_name="inventory-app",
        repo_url="https://github.com/octocat/inventory-app",
        sync_status=GitHubSyncStatus.SYNCED,
        last_commit_hash="abcdef1234567890",
    )

    mock_project_deployment_repo.get_by_project_id.return_value = None
    mock_deployment_client.create_service.return_value = "srv_railway_999"

    await use_case.execute(principal, cmd)

    mock_deployment_client.trigger_deployment.assert_called_once_with(
        token="decrypted_railway_token",
        service_id="srv_railway_999",
        commit_sha="abcdef1234567890",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrate_deployment_autosyncs_workspace_when_sync_use_case_injected(
    mock_project_deployment_repo: AsyncMock,
    mock_user_deployment_repo: AsyncMock,
    mock_project_github_repo: AsyncMock,
    mock_deployment_client: AsyncMock,
    mock_cipher: MagicMock,
    principal: Principal,
):
    # Arrange
    project_id = ProjectId("prj_autosync_test_01")
    cmd = OrchestrateCloudDeploymentCommand(project_id=project_id)
    mock_sync_use_case = AsyncMock()

    use_case = OrchestrateCloudDeploymentUseCase(
        project_deployment_repo=mock_project_deployment_repo,
        user_deployment_repo=mock_user_deployment_repo,
        project_github_repo=mock_project_github_repo,
        deployment_client=mock_deployment_client,
        cipher=mock_cipher,
        sync_github_use_case=mock_sync_use_case,
    )

    mock_user_deployment_repo.get_by_user_id.return_value = UserDeploymentIntegration(
        user_id=UserId(principal.subject),
        provider=DeploymentProvider.RAILWAY,
        encrypted_token=base64.b64encode(b"ciphertext_rw").decode("utf-8"),
    )
    mock_cipher.decrypt.return_value = b"decrypted_railway_token"

    mock_project_github_repo.get_by_project_id.return_value = ProjectGitHubIntegration(
        project_id=project_id,
        repo_name="inventory-app",
        repo_url="https://github.com/octocat/inventory-app",
        sync_status=GitHubSyncStatus.SYNCED,
        last_commit_hash="old_commit_111",
    )

    mock_sync_use_case.execute.return_value = ProjectGitHubIntegration(
        project_id=project_id,
        repo_name="inventory-app",
        repo_url="https://github.com/octocat/inventory-app",
        sync_status=GitHubSyncStatus.SYNCED,
        last_commit_hash="new_autosynced_commit_222",
    )

    mock_project_deployment_repo.get_by_project_id.return_value = None
    mock_deployment_client.create_service.return_value = "srv_railway_999"

    # Act
    await use_case.execute(principal, cmd)

    # Assert
    mock_sync_use_case.execute.assert_called_once()
    mock_deployment_client.trigger_deployment.assert_called_once_with(
        token="decrypted_railway_token",
        service_id="srv_railway_999",
        commit_sha="new_autosynced_commit_222",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrate_deployment_does_not_trigger_railway_when_sync_fails(
    mock_project_deployment_repo: AsyncMock,
    mock_user_deployment_repo: AsyncMock,
    mock_project_github_repo: AsyncMock,
    mock_deployment_client: AsyncMock,
    mock_cipher: MagicMock,
    principal: Principal,
):
    project_id = ProjectId("prj_autosync_fail_01")
    mock_sync_use_case = AsyncMock()
    mock_sync_use_case.execute.side_effect = RuntimeError("GitHub push failed")
    use_case = OrchestrateCloudDeploymentUseCase(
        project_deployment_repo=mock_project_deployment_repo,
        user_deployment_repo=mock_user_deployment_repo,
        project_github_repo=mock_project_github_repo,
        deployment_client=mock_deployment_client,
        cipher=mock_cipher,
        sync_github_use_case=mock_sync_use_case,
    )
    mock_user_deployment_repo.get_by_user_id.return_value = UserDeploymentIntegration(
        user_id=UserId(principal.subject),
        provider=DeploymentProvider.RAILWAY,
        encrypted_token=base64.b64encode(b"ciphertext_rw").decode("utf-8"),
    )
    mock_cipher.decrypt.return_value = b"decrypted_railway_token"
    mock_project_github_repo.get_by_project_id.return_value = ProjectGitHubIntegration(
        project_id=project_id,
        repo_name="inventory-app",
        repo_url="https://github.com/octocat/inventory-app",
        sync_status=GitHubSyncStatus.SYNCED,
        last_commit_hash="old_commit_111",
    )

    with pytest.raises(DeploymentPreconditionError, match="validar y sincronizar"):
        await use_case.execute(principal, OrchestrateCloudDeploymentCommand(project_id=project_id))

    mock_deployment_client.create_service.assert_not_called()
    mock_deployment_client.trigger_deployment.assert_not_called()
    mock_project_deployment_repo.save.assert_not_called()
