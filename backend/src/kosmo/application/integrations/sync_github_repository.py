from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from kosmo.application.integrations.execute_ephemeral_validation import (
    EphemeralValidationError,
    ExecuteEphemeralValidationCommand,
    ExecuteEphemeralValidationUseCase,
)
from kosmo.contracts.auth.secrets import EncryptedSecret, SecretCipher
from kosmo.contracts.integrations.git import GitWorkspacePort
from kosmo.contracts.integrations.github import (
    CodeSyncLog,
    CodeSyncLogRepository,
    CodeSyncStatus,
    GitHubClientPort,
    GitHubSyncStatus,
    ProjectGitHubIntegration,
    ProjectGitHubIntegrationRepository,
    UserGitHubIntegrationRepository,
)
from kosmo.contracts.sdd.codegen import WorkspaceManagerPort
from kosmo.contracts.sdd.ids import ProjectId, UserId
from kosmo.contracts.sdd.repositories import ProjectRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SyncGitHubRepositoryCommand:
    project_id: ProjectId
    project_name: str | None = None
    repo_name: str | None = None
    is_public: bool = True
    commit_message: str | None = None
    skip_lock: bool = False
    skip_validation: bool = False


class SyncGitHubRepositoryUseCase:
    """Orquesta la sincronización (inicial o incremental) del código fuente con GitHub."""

    def __init__(
        self,
        project_github_repo: ProjectGitHubIntegrationRepository,
        user_github_repo: UserGitHubIntegrationRepository,
        github_client: GitHubClientPort,
        git_workspace: GitWorkspacePort,
        workspace_manager: WorkspaceManagerPort,
        cipher: SecretCipher,
        sync_log_repo: CodeSyncLogRepository,
        ephemeral_validator: ExecuteEphemeralValidationUseCase | None = None,
        project_repo: ProjectRepository | None = None,
    ) -> None:
        self._project_repo = project_github_repo
        self._user_repo = user_github_repo
        self._github_client = github_client
        self._git_workspace = git_workspace
        self._workspace_manager = workspace_manager
        self._cipher = cipher
        self._sync_log_repo = sync_log_repo
        self._ephemeral_validator = ephemeral_validator
        self._sdd_project_repo = project_repo

    async def execute(
        self,
        cmd: SyncGitHubRepositoryCommand,
        user_id: UserId,
    ) -> ProjectGitHubIntegration:
        if not cmd.skip_lock:
            await self._workspace_manager.acquire_lock(cmd.project_id)
        try:
            if cmd.is_public is False:
                raise ValueError(
                    "No se permiten repositorios privados. Todos los repositorios de GitHub deben ser públicos."
                )

            user_integration = await self._user_repo.get_by_user_id(user_id)
            if not user_integration:
                raise ValueError("El usuario no tiene su cuenta vinculada con GitHub.")

            # Marcar inmediatamente como SYNCING y persistir para que cualquier consulta
            # concurrente (GET /projects/{id}/github) sepa que el proceso ya arrancó.
            now = datetime.now(UTC)
            project_integration = await self._project_repo.get_by_project_id(cmd.project_id)
            if not isinstance(project_integration, ProjectGitHubIntegration):
                project_integration = ProjectGitHubIntegration(
                    project_id=cmd.project_id,
                    repo_name=cmd.repo_name,
                    is_public=True,
                    sync_status=GitHubSyncStatus.SYNCING,
                    created_at=now,
                    updated_at=now,
                )
            else:
                project_integration = replace(
                    project_integration,
                    sync_status=GitHubSyncStatus.SYNCING,
                    updated_at=now,
                )
            await self._project_repo.save(project_integration)

            workspace = await self._workspace_manager.ensure_workspace(cmd.project_id)
            if not workspace or not workspace.workspace_dir:
                raise ValueError("No se encontró el directorio físico del workspace para el proyecto.")

            # Desencriptar token
            encrypted_bytes = base64.b64decode(user_integration.encrypted_token)
            decrypted_bytes = self._cipher.decrypt(EncryptedSecret(ciphertext=encrypted_bytes))
            token = decrypted_bytes.decode("utf-8")

            try:
                # El workspace debe ser válido antes de provocar efectos externos. De este
                # modo una plantilla rota no crea ni publica un repositorio remoto vacío.
                if not cmd.skip_validation and self._ephemeral_validator is not None:
                    val_res = await self._ephemeral_validator.execute(
                        ExecuteEphemeralValidationCommand(
                            workspace_path=workspace.workspace_dir,
                            project_id=cmd.project_id,
                        )
                    )
                    if not val_res.is_valid:
                        error_msg = (
                            f"Validación efímera fallida en el paso '{val_res.failed_step}': "
                            f"{'; '.join(val_res.error_summary)}"
                        )
                        raise EphemeralValidationError(
                            error_msg,
                            step=val_res.failed_step,
                            errors=val_res.error_summary,
                        )

                # Determinar si es sincronización incremental o creación inicial
                is_incremental = bool(
                    project_integration.repo_url and project_integration.sync_status != GitHubSyncStatus.NOT_CREATED
                )

                if is_incremental:
                    repo_url = project_integration.repo_url
                    repo_name = project_integration.repo_name or f"project-{cmd.project_id}"
                else:
                    user = await self._github_client.get_authenticated_user(token)
                    repo_name = cmd.repo_name or project_integration.repo_name or f"project-{cmd.project_id}"

                    exists = await self._github_client.check_repository_exists(token, user.login, repo_name)
                    if not exists:
                        project_display = cmd.project_name
                        if not project_display and self._sdd_project_repo is not None:
                            proj = await self._sdd_project_repo.by_id(cmd.project_id)
                            if proj is not None and proj.name:
                                project_display = proj.name
                        project_display = project_display or str(cmd.project_id)

                        github_repo = await self._github_client.create_repository(
                            token=token,
                            name=repo_name,
                            description=(
                                f"Repositorio sincronizado automáticamente desde KOSMO para proyecto {project_display}"
                            ),
                            is_private=False,
                        )
                        repo_url = github_repo.clone_url
                        if github_repo.id:
                            try:
                                await self._github_client.grant_app_installation_access(token, github_repo.id)
                            except Exception as exc:
                                logger.debug("No se pudo otorgar acceso a Railway para nuevo repositorio: %s", exc)
                    else:
                        repo = await self._github_client.get_repository(token, user.login, repo_name)
                        if repo is None:
                            raise ValueError(f"No se pudo recuperar el repositorio {repo_name}.")
                        repo_url = repo.clone_url
                        if repo.id:
                            try:
                                await self._github_client.grant_app_installation_access(token, repo.id)
                            except Exception as exc:
                                logger.debug("No se pudo otorgar acceso a Railway para repositorio existente: %s", exc)

                    project_integration = replace(
                        project_integration,
                        repo_url=repo_url,
                        repo_name=repo_name,
                        is_public=True,
                    )
                    await self._project_repo.save(project_integration)

                # Consolidar cambios pendientes del workspace en git antes del push
                await self._workspace_manager.commit_workspace(
                    cmd.project_id,
                    cmd.commit_message or "chore: sync project changes to repository",
                )

                # La URL persistida del remoto nunca debe contener el token OAuth.
                # El adaptador usa el token exclusivamente para este push.
                await asyncio.to_thread(
                    self._git_workspace.remote_add_or_update,
                    workspace.workspace_dir,
                    "origin",
                    repo_url,
                )

                branch = project_integration.default_branch or "main"
                commit_hash = await asyncio.to_thread(
                    self._git_workspace.push,
                    workspace.workspace_dir,
                    "origin",
                    branch=branch,
                    token=token,
                )

                # Log y Estado Final (SUCCESS)
                push_time = datetime.now(UTC)
                project_integration = replace(
                    project_integration,
                    repo_url=repo_url,
                    repo_name=repo_name,
                    sync_status=GitHubSyncStatus.SYNCED,
                    last_commit_hash=commit_hash,
                    last_push_at=push_time,
                    last_synced_at=push_time,
                    error_message=None,
                    updated_at=push_time,
                )
                saved_integration = await self._project_repo.save(project_integration)

                log = CodeSyncLog(
                    project_id=cmd.project_id,
                    status=CodeSyncStatus.SUCCESS,
                    commit_sha=commit_hash,
                    message=f"Sincronizado correctamente a {repo_url}",
                    synced_at=push_time,
                )
                await self._sync_log_repo.add_log(log)

                return saved_integration

            except Exception as e:
                fail_time = datetime.now(UTC)
                project_integration = replace(
                    project_integration,
                    sync_status=GitHubSyncStatus.FAILED,
                    error_message=str(e),
                    updated_at=fail_time,
                )
                await self._project_repo.save(project_integration)

                log = CodeSyncLog(
                    project_id=cmd.project_id,
                    status=CodeSyncStatus.FAILED,
                    message=str(e),
                    synced_at=fail_time,
                )
                await self._sync_log_repo.add_log(log)
                raise
        finally:
            if not cmd.skip_lock:
                with contextlib.suppress(Exception):
                    await self._workspace_manager.release_lock(cmd.project_id)
