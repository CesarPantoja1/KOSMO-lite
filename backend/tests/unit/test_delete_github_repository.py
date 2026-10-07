from __future__ import annotations

import base64
from unittest.mock import AsyncMock

import pytest

from kosmo.application.integrations.delete_github_repository import (
    DeleteGitHubRepositoryCommand,
    DeleteGitHubRepositoryUseCase,
)
from kosmo.contracts.auth.secrets import EncryptedSecret, SecretCipher
from kosmo.contracts.integrations.github import (
    GitHubClientPort,
    GitHubSyncStatus,
    ProjectGitHubIntegration,
    UserGitHubIntegration,
)
from kosmo.contracts.sdd.ids import ProjectId, UserId
from tests.unit.fakes import (
    InMemoryProjectGitHubIntegrationRepository,
    InMemoryUserGitHubIntegrationRepository,
)


class _MockCipher(SecretCipher):
    def encrypt(self, plaintext: bytes) -> EncryptedSecret:
        return EncryptedSecret(ciphertext=plaintext)

    def decrypt(self, secret: EncryptedSecret) -> bytes:
        return secret.ciphertext


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_github_repository_success() -> None:
    proj_gh_repo = InMemoryProjectGitHubIntegrationRepository()
    user_gh_repo = InMemoryUserGitHubIntegrationRepository()
    github_client = AsyncMock(spec=GitHubClientPort)
    github_client.delete_repository.return_value = True

    project_id = ProjectId("prj_gh_del")
    owner_id = UserId("usr_gh_del")

    # Store integration and user token
    await proj_gh_repo.save(
        ProjectGitHubIntegration(
            project_id=project_id,
            repo_name="kosmo-app",
            repo_url="https://github.com/octocat/kosmo-app",
            sync_status=GitHubSyncStatus.CREATED,
        )
    )

    enc_token = base64.b64encode(b"gh_token_123").decode("utf-8")
    await user_gh_repo.save(
        UserGitHubIntegration(
            user_id=owner_id,
            encrypted_token=enc_token,
            github_username="octocat",
        )
    )

    use_case = DeleteGitHubRepositoryUseCase(
        project_github_repo=proj_gh_repo,
        user_github_repo=user_gh_repo,
        github_client=github_client,
        cipher=_MockCipher(),
    )

    res = await use_case.execute(DeleteGitHubRepositoryCommand(project_id=project_id, owner_id=owner_id))

    assert res is True
    github_client.delete_repository.assert_awaited_once_with("gh_token_123", "octocat", "kosmo-app")
    assert await proj_gh_repo.get_by_project_id(project_id) is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_github_repository_remote_error_still_deletes_local() -> None:
    proj_gh_repo = InMemoryProjectGitHubIntegrationRepository()
    user_gh_repo = InMemoryUserGitHubIntegrationRepository()
    github_client = AsyncMock(spec=GitHubClientPort)
    github_client.delete_repository.side_effect = RuntimeError("API down")

    project_id = ProjectId("prj_gh_del_err")
    owner_id = UserId("usr_gh_del_err")

    await proj_gh_repo.save(
        ProjectGitHubIntegration(
            project_id=project_id,
            repo_name="kosmo-app-err",
            repo_url="https://github.com/octocat/kosmo-app-err",
            sync_status=GitHubSyncStatus.CREATED,
        )
    )

    enc_token = base64.b64encode(b"gh_token_123").decode("utf-8")
    await user_gh_repo.save(
        UserGitHubIntegration(
            user_id=owner_id,
            encrypted_token=enc_token,
            github_username="octocat",
        )
    )

    use_case = DeleteGitHubRepositoryUseCase(
        project_github_repo=proj_gh_repo,
        user_github_repo=user_gh_repo,
        github_client=github_client,
        cipher=_MockCipher(),
    )

    res = await use_case.execute(DeleteGitHubRepositoryCommand(project_id=project_id, owner_id=owner_id))

    assert res is False
    assert await proj_gh_repo.get_by_project_id(project_id) is None
