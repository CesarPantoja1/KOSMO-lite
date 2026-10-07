from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from kosmo.application.integrations.sync_github_repository import (
    SyncGitHubRepositoryCommand,
    SyncGitHubRepositoryUseCase,
)
from kosmo.contracts.auth.principal import Principal
from kosmo.contracts.auth.secrets import EncryptedSecret, SecretCipher
from kosmo.contracts.integrations.deployment import (
    DeploymentAccountNotLinkedError,
    DeploymentAuthenticationError,
    DeploymentPreconditionError,
    DeploymentProvider,
    DeploymentProviderPort,
    DeploymentRepositoryMissingError,
    DeploymentStatus,
    EnvironmentVariable,
    PortSpec,
    ProjectDeployment,
    ProjectDeploymentRepository,
    UserDeploymentIntegration,
    UserDeploymentIntegrationRepository,
    VolumeConfig,
)
from kosmo.contracts.integrations.github import (
    GitHubSyncStatus,
    ProjectGitHubIntegrationRepository,
)
from kosmo.contracts.sdd.ids import ProjectId, UserId
from kosmo.contracts.telemetry import traced

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OrchestrateCloudDeploymentCommand:
    project_id: ProjectId
    provider: DeploymentProvider = DeploymentProvider.RAILWAY
    service_name: str | None = None
    environment_variables: dict[str, str] | None = None


DeployRailwayCommand = OrchestrateCloudDeploymentCommand


class OrchestrateCloudDeploymentUseCase:
    """Caso de uso para orquestar la creación, configuración y disparo del despliegue en la nube."""

    def __init__(
        self,
        project_deployment_repo: ProjectDeploymentRepository,
        user_deployment_repo: UserDeploymentIntegrationRepository,
        project_github_repo: ProjectGitHubIntegrationRepository,
        deployment_client: DeploymentProviderPort,
        cipher: SecretCipher,
        sync_github_use_case: SyncGitHubRepositoryUseCase | None = None,
    ) -> None:
        self._project_deployment_repo = project_deployment_repo
        self._user_deployment_repo = user_deployment_repo
        self._project_github_repo = project_github_repo
        self._deployment_client = deployment_client
        self._cipher = cipher
        self._sync_github_use_case = sync_github_use_case

    async def _refresh_user_token(self, user_integration: UserDeploymentIntegration) -> str:
        """Renueva el token de acceso utilizando el refresh token cifrado del usuario y actualiza la base de datos."""
        if not user_integration.encrypted_refresh_token:
            raise DeploymentAuthenticationError(
                "La sesión de despliegue expiró y no hay un refresh token disponible. Reconecta tu cuenta de Railway."
            )
        try:
            raw_rt_bytes = base64.b64decode(user_integration.encrypted_refresh_token.encode("utf-8"))
            decrypted_rt = self._cipher.decrypt(EncryptedSecret(ciphertext=raw_rt_bytes)).decode("utf-8")
        except Exception as exc:
            raise DeploymentAuthenticationError("Error al descifrar el refresh token del usuario.") from exc

        new_token_dto = await self._deployment_client.refresh_access_token(decrypted_rt)
        if not new_token_dto.access_token:
            raise DeploymentAuthenticationError("Fallo al renovar el token de acceso con Railway.")

        new_enc_access = base64.b64encode(
            self._cipher.encrypt(new_token_dto.access_token.encode("utf-8")).ciphertext
        ).decode("utf-8")

        new_enc_refresh = user_integration.encrypted_refresh_token
        if new_token_dto.refresh_token:
            new_enc_refresh = base64.b64encode(
                self._cipher.encrypt(new_token_dto.refresh_token.encode("utf-8")).ciphertext
            ).decode("utf-8")

        updated_integration = UserDeploymentIntegration(
            user_id=user_integration.user_id,
            provider=user_integration.provider,
            encrypted_token=new_enc_access,
            provider_username=user_integration.provider_username,
            encrypted_refresh_token=new_enc_refresh,
            scopes=user_integration.scopes,
            updated_at=datetime.now(UTC),
        )
        await self._user_deployment_repo.save(updated_integration)
        return new_token_dto.access_token

    @traced("deployment.orchestrate")
    async def execute(
        self,
        principal: Principal,
        cmd: OrchestrateCloudDeploymentCommand,
    ) -> ProjectDeployment:
        # 1. Validar vinculación de la cuenta de despliegue del usuario
        user_integration = await self._user_deployment_repo.get_by_user_id(UserId(principal.subject), cmd.provider)
        if not user_integration or not user_integration.encrypted_token:
            raise DeploymentAccountNotLinkedError(
                f"La cuenta de {cmd.provider.value.capitalize()} no está vinculada. "
                "Debes conectar tu cuenta antes de iniciar el despliegue."
            )

        # 2. Descifrar credenciales
        try:
            raw_ciphertext = base64.b64decode(user_integration.encrypted_token.encode("utf-8"))
            decrypted_bytes = self._cipher.decrypt(EncryptedSecret(ciphertext=raw_ciphertext))
            token = decrypted_bytes.decode("utf-8")
        except Exception as exc:
            raise DeploymentAuthenticationError("Error al descifrar el token de despliegue del usuario.") from exc

        # 3. Validar precondición de repositorio GitHub remoto
        github_integration = await self._project_github_repo.get_by_project_id(cmd.project_id)
        if (
            not github_integration
            or not github_integration.repo_url
            or github_integration.sync_status == GitHubSyncStatus.NOT_CREATED
        ):
            raise DeploymentRepositoryMissingError(
                "El proyecto no cuenta con un repositorio remoto de GitHub sincronizado. "
                "Debes sincronizar el código con GitHub antes de publicar en la nube."
            )

        # La validación y el push deben terminar antes de disparar Railway: de otro
        # modo Railway compila un commit anterior sin el lockfile generado.
        if self._sync_github_use_case is not None:
            try:
                sync_cmd = SyncGitHubRepositoryCommand(
                    project_id=cmd.project_id,
                    commit_message="chore: sync latest project configuration before deployment",
                )
                updated_github = await self._sync_github_use_case.execute(sync_cmd, UserId(principal.subject))
                if not updated_github or not updated_github.last_commit_hash:
                    raise DeploymentPreconditionError(
                        "La sincronización de GitHub no devolvió un commit para desplegar."
                    )
                github_integration = updated_github
            except Exception as sync_err:
                logger.warning("No se pudo sincronizar GitHub antes de desplegar: %s", sync_err)
                raise DeploymentPreconditionError(
                    "No se pudo validar y sincronizar el código en GitHub antes de desplegar en Railway."
                ) from sync_err

        # 4. Configurar variables de entorno predeterminadas y personalizadas
        default_env_vars = [
            EnvironmentVariable(key="NODE_ENV", value="production", is_secret=False),
            EnvironmentVariable(key="PORT", value="3000", is_secret=False),
            EnvironmentVariable(key="HOSTNAME", value="0.0.0.0", is_secret=False),
            EnvironmentVariable(key="DATABASE_URL", value="file:/data/db.sqlite", is_secret=False),
        ]
        custom_env_vars: list[EnvironmentVariable] = []
        if cmd.environment_variables:
            for k, v in cmd.environment_variables.items():
                if k not in {"NODE_ENV", "PORT", "HOSTNAME", "DATABASE_URL"}:
                    custom_env_vars.append(EnvironmentVariable(key=k, value=v, is_secret=False))
        all_env_vars = default_env_vars + custom_env_vars

        volume_config = VolumeConfig(mount_path="/data", size_mb=512)
        port_spec = PortSpec(port=3000, protocol="http")

        # 5. Crear o reutilizar servicio remoto y aprovisionar con auto-renovación si el token expiró
        existing_deployment = await self._project_deployment_repo.get_by_project_id(cmd.project_id)
        now = datetime.now(UTC)
        is_redeploy = bool(existing_deployment and existing_deployment.service_id)

        async def _provision_remote(current_token: str) -> str:
            if is_redeploy:
                # Reutilizar el servicio existente: no crear ni reconfigurar el volumen
                # existing_deployment y service_id no son None cuando is_redeploy es True
                assert existing_deployment is not None and existing_deployment.service_id is not None
                sid: str = existing_deployment.service_id
            else:
                sid = await self._deployment_client.create_service(
                    token=current_token,
                    repo_url=github_integration.repo_url,  # type: ignore[arg-type]
                    env_vars=all_env_vars,
                    ports=[port_spec],
                    service_name=cmd.service_name,
                )
                # Configurar volumen solo en el primer despliegue
                await self._deployment_client.configure_volume(
                    token=current_token,
                    service_id=sid,
                    volume=volume_config,
                )

            await self._deployment_client.trigger_deployment(
                token=current_token,
                service_id=sid,
                commit_sha=github_integration.last_commit_hash if github_integration else None,
            )
            return sid

        try:
            service_id = await _provision_remote(token)
        except DeploymentAuthenticationError:
            if user_integration.encrypted_refresh_token:
                token = await self._refresh_user_token(user_integration)
                try:
                    service_id = await _provision_remote(token)
                except DeploymentAuthenticationError:
                    logger.warning(
                        "Token de Railway para el usuario %s no autorizado tras renovar. Eliminando integración.",
                        user_integration.user_id,
                    )
                    await self._user_deployment_repo.delete_by_user_id(
                        user_integration.user_id, user_integration.provider
                    )
                    raise
            else:
                logger.warning(
                    "Token de Railway para el usuario %s no autorizado y sin refresh token. Eliminando integración.",
                    user_integration.user_id,
                )
                await self._user_deployment_repo.delete_by_user_id(user_integration.user_id, user_integration.provider)
                raise

        # 7. Actualizar y persistir el estado de despliegue del proyecto
        deployment = ProjectDeployment(
            project_id=cmd.project_id,
            provider=cmd.provider,
            service_id=service_id,
            service_name=(existing_deployment.service_name if existing_deployment else cmd.service_name),
            public_url=existing_deployment.public_url if existing_deployment else None,
            status=DeploymentStatus.BUILDING,
            build_logs_url=existing_deployment.build_logs_url if existing_deployment else None,
            last_deployed_at=now,
            error_message=None,
            volumes=(volume_config,),
            ports=(port_spec,),
            env_vars=tuple(all_env_vars),
            created_at=existing_deployment.created_at if existing_deployment else now,
            updated_at=now,
        )
        await self._project_deployment_repo.save(deployment)

        return deployment


DeployRailwayUseCase = OrchestrateCloudDeploymentUseCase
