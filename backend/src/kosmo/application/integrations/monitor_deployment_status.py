import asyncio
import base64
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from kosmo.contracts.auth.secrets import EncryptedSecret, SecretCipher
from kosmo.contracts.integrations.deployment import (
    DeploymentAuthenticationError,
    DeploymentProviderPort,
    DeploymentStatus,
    ProjectDeploymentRepository,
    UserDeploymentIntegration,
    UserDeploymentIntegrationRepository,
)
from kosmo.contracts.sdd.ids import ProjectId, UserId
from kosmo.contracts.telemetry import traced


@dataclass(frozen=True, slots=True)
class MonitorDeploymentStatusCommand:
    project_id: ProjectId
    user_id: UserId
    max_attempts: int = 60
    delay_seconds: int = 10


class MonitorDeploymentStatusUseCase:
    """Caso de uso para monitorear periodicamente el estado de un despliegue en la nube."""

    def __init__(
        self,
        project_deployment_repo: ProjectDeploymentRepository,
        user_deployment_repo: UserDeploymentIntegrationRepository,
        deployment_client: DeploymentProviderPort,
        cipher: SecretCipher,
    ) -> None:
        self._project_deployment_repo = project_deployment_repo
        self._user_deployment_repo = user_deployment_repo
        self._deployment_client = deployment_client
        self._cipher = cipher

    @traced("deployment.monitor")
    async def execute(self, cmd: MonitorDeploymentStatusCommand) -> None:
        # 1. Recuperar el ProjectDeployment
        deployment = await self._project_deployment_repo.get_by_project_id(cmd.project_id)
        if not deployment or not deployment.service_id:
            return  # No hay nada que monitorear

        # Si ya alcanzo un estado terminal, terminar de inmediato
        if deployment.status in (DeploymentStatus.PUBLISHED, DeploymentStatus.FAILED):
            return

        # 2. Obtener el token de despliegue del usuario
        user_integration = await self._user_deployment_repo.get_by_user_id(cmd.user_id, deployment.provider)
        if not user_integration or not user_integration.encrypted_token:
            return  # No se puede monitorear sin credenciales

        try:
            raw_ciphertext = base64.b64decode(user_integration.encrypted_token.encode("utf-8"))
            decrypted_bytes = self._cipher.decrypt(EncryptedSecret(ciphertext=raw_ciphertext))
            token = decrypted_bytes.decode("utf-8")
        except Exception as exc:
            raise DeploymentAuthenticationError("Error al descifrar el token de despliegue.") from exc

        # 3. Bucle de polling periodico con auto-renovacion de token
        token_refreshed = False  # Solo un intento de renovacion por sesion de monitoreo
        attempts = 0
        while attempts < cmd.max_attempts:
            try:
                status, public_url, logs_or_error = await self._deployment_client.get_service_status(
                    token=token,
                    service_id=str(deployment.service_id),
                )
            except DeploymentAuthenticationError:
                # Token expirado mid-polling: renovar una sola vez y continuar
                if token_refreshed or not user_integration.encrypted_refresh_token:
                    raise
                try:
                    raw_rt = base64.b64decode(user_integration.encrypted_refresh_token.encode("utf-8"))
                    decrypted_rt = self._cipher.decrypt(EncryptedSecret(ciphertext=raw_rt)).decode("utf-8")
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

                    user_integration = UserDeploymentIntegration(
                        user_id=user_integration.user_id,
                        provider=user_integration.provider,
                        encrypted_token=new_enc_access,
                        provider_username=user_integration.provider_username,
                        encrypted_refresh_token=new_enc_refresh,
                        scopes=user_integration.scopes,
                        updated_at=datetime.now(UTC),
                    )
                    await self._user_deployment_repo.save(user_integration)
                    token = new_token_dto.access_token
                    token_refreshed = True
                except DeploymentAuthenticationError:
                    raise
                except Exception as exc:
                    raise DeploymentAuthenticationError(
                        "Error al renovar el token de despliegue durante el monitoreo."
                    ) from exc
                # Reintentar el intento actual con el token nuevo (no incrementar attempts)
                continue

            # Detectar cambios de estado o URL
            has_changed = (
                status != deployment.status
                or public_url != deployment.public_url
                or (status == DeploymentStatus.FAILED and logs_or_error != deployment.error_message)
            )

            if has_changed:
                error_msg: str | None = None
                build_logs: str | None = deployment.build_logs_url
                if status == DeploymentStatus.FAILED:
                    build_logs = logs_or_error or deployment.build_logs_url
                    if logs_or_error and not logs_or_error.startswith(("http://", "https://")):
                        error_msg = logs_or_error
                    elif logs_or_error:
                        error_msg = (
                            deployment.error_message
                            or "Fallo durante el despliegue en Railway. Revisa los registros de compilación."
                        )
                    else:
                        error_msg = deployment.error_message or "Fallo durante el despliegue en Railway."

                deployment = replace(
                    deployment,
                    status=status,
                    public_url=public_url if public_url else deployment.public_url,
                    build_logs_url=build_logs,
                    error_message=error_msg,
                )
                await self._project_deployment_repo.save(deployment)

            # Salir si el estado es terminal
            if status in (DeploymentStatus.PUBLISHED, DeploymentStatus.FAILED):
                return

            await asyncio.sleep(cmd.delay_seconds)
            attempts += 1

        # Timeout: el despliegue no alcanzo un estado terminal - marcarlo como FAILED
        if deployment.status not in (DeploymentStatus.PUBLISHED, DeploymentStatus.FAILED):
            timeout_msg = (
                f"El despliegue supero el tiempo maximo de espera "
                f"({cmd.max_attempts * cmd.delay_seconds}s) sin completarse."
            )
            deployment = replace(
                deployment,
                status=DeploymentStatus.FAILED,
                error_message=timeout_msg,
            )
            await self._project_deployment_repo.save(deployment)
