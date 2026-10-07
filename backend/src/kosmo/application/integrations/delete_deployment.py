from __future__ import annotations

import base64
import contextlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from kosmo.contracts.auth import Principal
from kosmo.contracts.auth.secrets import EncryptedSecret, SecretCipher
from kosmo.contracts.integrations.deployment import (
    DeploymentAuthenticationError,
    DeploymentProvider,
    DeploymentProviderPort,
    DeploymentWorkerPort,
    ProjectDeploymentRepository,
    UserDeploymentIntegration,
    UserDeploymentIntegrationRepository,
)
from kosmo.contracts.sdd.ids import ProjectId, UserId

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DeleteDeploymentCommand:
    project_id: ProjectId
    provider: DeploymentProvider = DeploymentProvider.RAILWAY


class DeleteDeploymentUseCase:
    """Caso de uso para eliminar el servicio remoto en la nube y el registro de despliegue del proyecto."""

    def __init__(
        self,
        project_deployment_repo: ProjectDeploymentRepository,
        user_deployment_repo: UserDeploymentIntegrationRepository,
        deployment_client: DeploymentProviderPort,
        cipher: SecretCipher,
        deployment_worker: DeploymentWorkerPort | None = None,
    ) -> None:
        self._project_deployment_repo = project_deployment_repo
        self._user_deployment_repo = user_deployment_repo
        self._deployment_client = deployment_client
        self._cipher = cipher
        self._deployment_worker = deployment_worker

    async def execute(
        self,
        principal: Principal,
        cmd: DeleteDeploymentCommand,
    ) -> bool:
        project_id = cmd.project_id
        user_id = UserId(principal.subject)

        # 1. Cancelar monitoreo activo si existe
        if self._deployment_worker is not None:
            is_monitoring = getattr(self._deployment_worker, "is_monitoring", None)
            if is_monitoring is None or is_monitoring(project_id):
                self._deployment_worker.cancel_monitoring(project_id)

        # 2. Consultar despliegue existente
        deployment = await self._project_deployment_repo.get_by_project_id(project_id)
        if deployment is None:
            return False

        # 3. Si existe servicio remoto, eliminarlo en la plataforma
        if deployment.service_id:
            user_integration = await self._user_deployment_repo.get_by_user_id(user_id, cmd.provider)
            if user_integration is not None and user_integration.encrypted_token:
                try:
                    raw_bytes = base64.b64decode(user_integration.encrypted_token.encode("utf-8"))
                    token = self._cipher.decrypt(EncryptedSecret(ciphertext=raw_bytes)).decode("utf-8")
                    try:
                        await self._deployment_client.delete_service(token, deployment.service_id)
                        logger.info(
                            "delete_deployment.service_deleted project_id=%s service_id=%s",
                            project_id,
                            deployment.service_id,
                        )
                    except DeploymentAuthenticationError:
                        if user_integration.encrypted_refresh_token:
                            raw_rt = base64.b64decode(user_integration.encrypted_refresh_token.encode("utf-8"))
                            rt = self._cipher.decrypt(EncryptedSecret(ciphertext=raw_rt)).decode("utf-8")
                            new_dto = await self._deployment_client.refresh_access_token(rt)
                            if new_dto.access_token:
                                token = new_dto.access_token
                                enc_acc = base64.b64encode(
                                    self._cipher.encrypt(token.encode("utf-8")).ciphertext
                                ).decode("utf-8")
                                enc_ref = user_integration.encrypted_refresh_token
                                if new_dto.refresh_token:
                                    enc_ref = base64.b64encode(
                                        self._cipher.encrypt(new_dto.refresh_token.encode("utf-8")).ciphertext
                                    ).decode("utf-8")
                                await self._user_deployment_repo.save(
                                    UserDeploymentIntegration(
                                        user_id=user_integration.user_id,
                                        provider=user_integration.provider,
                                        encrypted_token=enc_acc,
                                        provider_username=user_integration.provider_username,
                                        encrypted_refresh_token=enc_ref,
                                        scopes=user_integration.scopes,
                                        updated_at=datetime.now(UTC),
                                    )
                                )
                                await self._deployment_client.delete_service(token, deployment.service_id)
                                logger.info(
                                    "delete_deployment.service_deleted_after_refresh project_id=%s",
                                    project_id,
                                )
                except Exception:
                    logger.warning(
                        "delete_deployment.remote_delete_failed project_id=%s",
                        project_id,
                        exc_info=True,
                    )

        # 4. Eliminar registro local de despliegue
        with contextlib.suppress(Exception):
            await self._project_deployment_repo.delete_by_project_id(project_id)

        return True
