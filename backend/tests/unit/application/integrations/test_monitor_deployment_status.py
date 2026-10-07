import base64
from unittest.mock import AsyncMock, MagicMock

import pytest

from kosmo.application.integrations.monitor_deployment_status import (
    MonitorDeploymentStatusCommand,
    MonitorDeploymentStatusUseCase,
)
from kosmo.contracts.auth.secrets import EncryptedSecret
from kosmo.contracts.integrations.deployment import (
    DeploymentProvider,
    DeploymentStatus,
    ProjectDeployment,
    UserDeploymentIntegration,
)
from kosmo.contracts.sdd.ids import ProjectId, UserId


@pytest.fixture
def project_deployment_repo():
    return AsyncMock()


@pytest.fixture
def user_deployment_repo():
    return AsyncMock()


@pytest.fixture
def deployment_client():
    return AsyncMock()


@pytest.fixture
def cipher():
    return MagicMock()


@pytest.fixture
def use_case(
    project_deployment_repo,
    user_deployment_repo,
    deployment_client,
    cipher,
):
    return MonitorDeploymentStatusUseCase(
        project_deployment_repo=project_deployment_repo,
        user_deployment_repo=user_deployment_repo,
        deployment_client=deployment_client,
        cipher=cipher,
    )


async def test_monitor_deployment_success_transition(
    use_case: MonitorDeploymentStatusUseCase,
    project_deployment_repo: AsyncMock,
    user_deployment_repo: AsyncMock,
    deployment_client: AsyncMock,
    cipher: MagicMock,
):
    cmd = MonitorDeploymentStatusCommand(
        project_id=ProjectId("proj-1"),
        user_id=UserId("user-1"),
        max_attempts=3,
        delay_seconds=0,
    )

    project_deployment_repo.get_by_project_id.return_value = ProjectDeployment(
        project_id=ProjectId("proj-1"),
        provider=DeploymentProvider.RAILWAY,
        service_id="srv-123",
        status=DeploymentStatus.BUILDING,
    )

    user_deployment_repo.get_by_user_id.return_value = UserDeploymentIntegration(
        user_id=UserId("user-1"),
        provider=DeploymentProvider.RAILWAY,
        encrypted_token=base64.b64encode(b"enc").decode("utf-8"),
    )
    cipher.decrypt.return_value = b"real-token"

    # Simular que en el primer intento sigue "BUILDING", y en el segundo cambia a "PUBLISHED"
    deployment_client.get_service_status.side_effect = [
        (DeploymentStatus.BUILDING, None, None),
        (DeploymentStatus.PUBLISHED, "https://app.example.com", None),
    ]

    await use_case.execute(cmd)

    # El token se desencripta 1 vez
    cipher.decrypt.assert_called_once_with(EncryptedSecret(ciphertext=b"enc"))

    # get_service_status se llama 2 veces
    assert deployment_client.get_service_status.call_count == 2

    # Se guarda el deployment sólo cuando cambia de estado (en la segunda iteración)
    project_deployment_repo.save.assert_called_once()
    saved_deployment = project_deployment_repo.save.call_args[0][0]
    assert saved_deployment.status == DeploymentStatus.PUBLISHED
    assert saved_deployment.public_url == "https://app.example.com"


async def test_monitor_deployment_fails_transition(
    use_case: MonitorDeploymentStatusUseCase,
    project_deployment_repo: AsyncMock,
    user_deployment_repo: AsyncMock,
    deployment_client: AsyncMock,
    cipher: MagicMock,
):
    cmd = MonitorDeploymentStatusCommand(
        project_id=ProjectId("proj-1"),
        user_id=UserId("user-1"),
        max_attempts=2,
        delay_seconds=0,
    )

    project_deployment_repo.get_by_project_id.return_value = ProjectDeployment(
        project_id=ProjectId("proj-1"),
        provider=DeploymentProvider.RAILWAY,
        service_id="srv-123",
        status=DeploymentStatus.BUILDING,
    )

    user_deployment_repo.get_by_user_id.return_value = UserDeploymentIntegration(
        user_id=UserId("user-1"),
        provider=DeploymentProvider.RAILWAY,
        encrypted_token=base64.b64encode(b"enc").decode("utf-8"),
    )
    cipher.decrypt.return_value = b"real-token"

    # Falla en el primer intento
    deployment_client.get_service_status.return_value = (
        DeploymentStatus.FAILED,
        None,
        "Build failed due to syntax error",
    )

    await use_case.execute(cmd)

    project_deployment_repo.save.assert_called_once()
    saved_deployment = project_deployment_repo.save.call_args[0][0]
    assert saved_deployment.status == DeploymentStatus.FAILED
    assert saved_deployment.build_logs_url == "Build failed due to syntax error"
    assert saved_deployment.error_message == "Build failed due to syntax error"


async def test_monitor_deployment_failure_with_logs_url(
    use_case: MonitorDeploymentStatusUseCase,
    project_deployment_repo: AsyncMock,
    user_deployment_repo: AsyncMock,
    deployment_client: AsyncMock,
    cipher: MagicMock,
):
    # Arrange
    cmd = MonitorDeploymentStatusCommand(
        project_id=ProjectId("proj-1"),
        user_id=UserId("user-1"),
        max_attempts=5,
        delay_seconds=0,
    )
    project_deployment_repo.get_by_project_id.return_value = ProjectDeployment(
        project_id=ProjectId("proj-1"),
        provider=DeploymentProvider.RAILWAY,
        service_id="srv-123",
        status=DeploymentStatus.BUILDING,
    )
    user_deployment_repo.get_by_user_id.return_value = UserDeploymentIntegration(
        user_id=UserId("user-1"),
        provider=DeploymentProvider.RAILWAY,
        encrypted_token=base64.b64encode(b"enc").decode("utf-8"),
    )
    cipher.decrypt.return_value = b"real-token"
    deployment_client.get_service_status.return_value = (
        DeploymentStatus.FAILED,
        None,
        "https://railway.com/project/prj-1/service/srv-123?id=dep-1",
    )

    # Act
    await use_case.execute(cmd)

    # Assert
    project_deployment_repo.save.assert_called_once()
    saved = project_deployment_repo.save.call_args[0][0]
    assert saved.status == DeploymentStatus.FAILED
    assert saved.build_logs_url == "https://railway.com/project/prj-1/service/srv-123?id=dep-1"
    assert "Fallo durante el despliegue en Railway" in (saved.error_message or "")


async def test_monitor_deployment_max_attempts(
    use_case: MonitorDeploymentStatusUseCase,
    project_deployment_repo: AsyncMock,
    user_deployment_repo: AsyncMock,
    deployment_client: AsyncMock,
    cipher: MagicMock,
):
    cmd = MonitorDeploymentStatusCommand(
        project_id=ProjectId("proj-1"),
        user_id=UserId("user-1"),
        max_attempts=3,
        delay_seconds=0,
    )

    project_deployment_repo.get_by_project_id.return_value = ProjectDeployment(
        project_id=ProjectId("proj-1"),
        provider=DeploymentProvider.RAILWAY,
        service_id="srv-123",
        status=DeploymentStatus.BUILDING,
    )

    user_deployment_repo.get_by_user_id.return_value = UserDeploymentIntegration(
        user_id=UserId("user-1"),
        provider=DeploymentProvider.RAILWAY,
        encrypted_token=base64.b64encode(b"enc").decode("utf-8"),
    )
    cipher.decrypt.return_value = b"real-token"

    # Siempre devuelve BUILDING
    deployment_client.get_service_status.return_value = (DeploymentStatus.BUILDING, None, None)

    await use_case.execute(cmd)

    # get_service_status se llama 3 veces (max_attempts)
    assert deployment_client.get_service_status.call_count == 3

    # Al agotar los intentos sin estado terminal, el despliegue se marca como FAILED
    project_deployment_repo.save.assert_called_once()
    saved = project_deployment_repo.save.call_args[0][0]
    assert saved.status == DeploymentStatus.FAILED
    assert saved.error_message is not None
    assert "tiempo" in saved.error_message


async def test_monitor_refreshes_token_on_auth_error_mid_polling(
    use_case: MonitorDeploymentStatusUseCase,
    project_deployment_repo: AsyncMock,
    user_deployment_repo: AsyncMock,
    deployment_client: AsyncMock,
    cipher: MagicMock,
):
    """Cuando el token expira a mitad del polling, se renueva automáticamente y se continúa."""
    from kosmo.contracts.integrations.deployment import DeploymentAuthenticationError, DeploymentOAuthToken

    cmd = MonitorDeploymentStatusCommand(
        project_id=ProjectId("proj-refresh"),
        user_id=UserId("user-refresh"),
        max_attempts=3,
        delay_seconds=0,
    )

    project_deployment_repo.get_by_project_id.return_value = ProjectDeployment(
        project_id=ProjectId("proj-refresh"),
        provider=DeploymentProvider.RAILWAY,
        service_id="srv-ref-123",
        status=DeploymentStatus.BUILDING,
    )

    user_deployment_repo.get_by_user_id.return_value = UserDeploymentIntegration(
        user_id=UserId("user-refresh"),
        provider=DeploymentProvider.RAILWAY,
        encrypted_token=base64.b64encode(b"old-enc").decode("utf-8"),
        encrypted_refresh_token=base64.b64encode(b"refresh-enc").decode("utf-8"),
    )

    # decrypt devuelve el token viejo primero, luego el refresh token
    cipher.decrypt.side_effect = [b"old-token", b"refresh-token"]
    # encrypt devuelve ciphertext simulado para el nuevo token
    enc_secret = MagicMock()
    enc_secret.ciphertext = b"new-enc"
    cipher.encrypt.return_value = enc_secret

    # Primera llamada lanza AuthError (token expirado), tras renovación devuelve PUBLISHED
    deployment_client.refresh_access_token.return_value = DeploymentOAuthToken(
        access_token="new-token",
        refresh_token=None,
    )
    deployment_client.get_service_status.side_effect = [
        DeploymentAuthenticationError("token expired"),
        (DeploymentStatus.PUBLISHED, "https://app.railway.app", None),
    ]

    await use_case.execute(cmd)

    # Se renovó el token
    deployment_client.refresh_access_token.assert_called_once_with("refresh-token")
    # Se guardó la integración con el nuevo token
    user_deployment_repo.save.assert_called_once()
    # get_service_status se llamó 2 veces (1 error + 1 éxito)
    assert deployment_client.get_service_status.call_count == 2
    # El deployment se guardó como PUBLISHED
    project_deployment_repo.save.assert_called_once()
    saved = project_deployment_repo.save.call_args[0][0]
    assert saved.status == DeploymentStatus.PUBLISHED
