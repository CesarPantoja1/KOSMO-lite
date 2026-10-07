from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock

import pytest

from kosmo.application.integrations.delete_deployment import (
    DeleteDeploymentCommand,
    DeleteDeploymentUseCase,
)
from kosmo.contracts.auth import Principal
from kosmo.contracts.integrations.deployment import (
    DeploymentProvider,
    DeploymentStatus,
    ProjectDeployment,
    UserDeploymentIntegration,
)
from kosmo.contracts.sdd.ids import ProjectId, UserId


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_deployment_returns_false_when_no_deployment() -> None:
    project_deployment_repo = AsyncMock()
    project_deployment_repo.get_by_project_id.return_value = None
    user_deployment_repo = AsyncMock()
    deployment_client = AsyncMock()
    cipher = MagicMock()

    use_case = DeleteDeploymentUseCase(
        project_deployment_repo=project_deployment_repo,
        user_deployment_repo=user_deployment_repo,
        deployment_client=deployment_client,
        cipher=cipher,
    )

    result = await use_case.execute(
        principal=Principal(subject="usr_test"),
        cmd=DeleteDeploymentCommand(project_id=ProjectId("prj_none")),
    )

    assert result is False
    project_deployment_repo.delete_by_project_id.assert_not_called()
    deployment_client.delete_service.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_deployment_returns_true_when_deployment_deleted() -> None:
    project_id = ProjectId("prj_existing")
    project_deployment_repo = AsyncMock()
    project_deployment_repo.get_by_project_id.return_value = ProjectDeployment(
        project_id=project_id,
        provider=DeploymentProvider.RAILWAY,
        service_id="srv_123",
        status=DeploymentStatus.PUBLISHED,
    )
    user_deployment_repo = AsyncMock()
    user_deployment_repo.get_by_user_id.return_value = UserDeploymentIntegration(
        user_id=UserId("usr_test"),
        provider=DeploymentProvider.RAILWAY,
        encrypted_token=base64.b64encode(b"ciphertext").decode("utf-8"),
    )
    deployment_client = AsyncMock()
    cipher = MagicMock()
    cipher.decrypt.return_value = b"decrypted-token"

    use_case = DeleteDeploymentUseCase(
        project_deployment_repo=project_deployment_repo,
        user_deployment_repo=user_deployment_repo,
        deployment_client=deployment_client,
        cipher=cipher,
    )

    result = await use_case.execute(
        principal=Principal(subject="usr_test"),
        cmd=DeleteDeploymentCommand(project_id=project_id),
    )

    assert result is True
    deployment_client.delete_service.assert_awaited_once_with("decrypted-token", "srv_123")
    project_deployment_repo.delete_by_project_id.assert_awaited_once_with(project_id)
