from __future__ import annotations

import base64
import contextlib
import logging
from dataclasses import dataclass

from kosmo.contracts.auth.secrets import EncryptedSecret, SecretCipher
from kosmo.contracts.integrations.github import (
    GitHubClientPort,
    ProjectGitHubIntegrationRepository,
    UserGitHubIntegrationRepository,
)
from kosmo.contracts.sdd.ids import ProjectId, UserId

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DeleteGitHubRepositoryCommand:
    project_id: ProjectId
    owner_id: UserId


class DeleteGitHubRepositoryUseCase:
    """Caso de uso para eliminar el repositorio remoto en GitHub asociado al proyecto."""

    def __init__(
        self,
        project_github_repo: ProjectGitHubIntegrationRepository,
        user_github_repo: UserGitHubIntegrationRepository,
        github_client: GitHubClientPort,
        cipher: SecretCipher,
    ) -> None:
        self._project_github_repo = project_github_repo
        self._user_github_repo = user_github_repo
        self._github_client = github_client
        self._cipher = cipher

    async def execute(self, cmd: DeleteGitHubRepositoryCommand) -> bool:
        project_id = cmd.project_id
        owner_id = cmd.owner_id
        deleted = False

        try:
            integration = await self._project_github_repo.get_by_project_id(project_id)
            if integration is not None and (integration.repo_name or integration.repo_url):
                user_github = await self._user_github_repo.get_by_user_id(owner_id)
                if user_github is not None and user_github.encrypted_token:
                    raw_bytes = base64.b64decode(user_github.encrypted_token.encode("utf-8"))
                    token = self._cipher.decrypt(EncryptedSecret(ciphertext=raw_bytes)).decode("utf-8")

                    owner = user_github.github_username
                    repo_name = integration.repo_name
                    if not repo_name and integration.repo_url:
                        cleaned = integration.repo_url.rstrip("/").removesuffix(".git")
                        parts = cleaned.split("/")
                        if len(parts) >= 2:
                            if not owner:
                                owner = parts[-2]
                            repo_name = parts[-1]

                    if owner and repo_name:
                        try:
                            await self._github_client.delete_repository(token, owner, repo_name)
                            deleted = True
                            logger.info(
                                "delete_github_repository.success project_id=%s owner=%s repo=%s",
                                project_id,
                                owner,
                                repo_name,
                            )
                        except Exception:
                            logger.warning(
                                "delete_github_repository.remote_delete_failed project_id=%s",
                                project_id,
                                exc_info=True,
                            )
        except Exception:
            logger.warning(
                "delete_github_repository.failed project_id=%s",
                project_id,
                exc_info=True,
            )
        finally:
            with contextlib.suppress(Exception):
                await self._project_github_repo.delete_by_project_id(project_id)

        return deleted
