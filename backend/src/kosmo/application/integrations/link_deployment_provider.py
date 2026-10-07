from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime

from kosmo.contracts.auth.principal import Principal
from kosmo.contracts.auth.secrets import SecretCipher
from kosmo.contracts.integrations.deployment import (
    DeploymentAuthenticationError,
    DeploymentProvider,
    DeploymentProviderPort,
    UserDeploymentIntegration,
    UserDeploymentIntegrationRepository,
)
from kosmo.contracts.sdd.ids import UserId
from kosmo.contracts.telemetry import traced


@dataclass(frozen=True, slots=True)
class LinkDeploymentPlatformCommand:
    code: str
    provider: DeploymentProvider = DeploymentProvider.RAILWAY
    redirect_uri: str | None = None
    code_verifier: str | None = None


LinkDeploymentProviderCommand = LinkDeploymentPlatformCommand


class LinkDeploymentPlatformUseCase:
    """Caso de uso para intercambiar el código OAuth de una plataforma de despliegue y persistir el token cifrado."""

    def __init__(
        self,
        deployment_client: DeploymentProviderPort,
        cipher: SecretCipher,
        repo: UserDeploymentIntegrationRepository,
    ) -> None:
        self._deployment_client = deployment_client
        self._cipher = cipher
        self._repo = repo

    @traced("deployment.link_platform")
    async def execute(
        self,
        principal: Principal,
        cmd: LinkDeploymentPlatformCommand,
    ) -> UserDeploymentIntegration:
        if not cmd.code or not cmd.code.strip():
            raise DeploymentAuthenticationError("El código de autorización OAuth no puede estar vacío.")

        token = await self._deployment_client.exchange_oauth_code(
            cmd.code.strip(),
            cmd.redirect_uri,
            cmd.code_verifier,
        )
        if not token.access_token or not token.access_token.strip():
            raise DeploymentAuthenticationError("No se recibió un access_token válido de la plataforma de despliegue.")

        encrypted = self._cipher.encrypt(token.access_token.strip().encode("utf-8"))
        encrypted_token_str = base64.b64encode(encrypted.ciphertext).decode("utf-8")

        encrypted_refresh_str: str | None = None
        if token.refresh_token and token.refresh_token.strip():
            encrypted_refresh = self._cipher.encrypt(token.refresh_token.strip().encode("utf-8"))
            encrypted_refresh_str = base64.b64encode(encrypted_refresh.ciphertext).decode("utf-8")

        provider_username: str | None = None
        try:
            user_info = await self._deployment_client.get_authenticated_user(token.access_token.strip())
            provider_username = user_info.get("name") or user_info.get("email") or None
        except Exception:
            provider_username = None

        scopes = tuple(s.strip() for s in token.scope.split() if s.strip()) if token.scope else ()

        integration = UserDeploymentIntegration(
            user_id=UserId(principal.subject),
            provider=cmd.provider,
            encrypted_token=encrypted_token_str,
            provider_username=provider_username,
            encrypted_refresh_token=encrypted_refresh_str,
            scopes=scopes,
            updated_at=datetime.now(UTC),
        )

        await self._repo.save(integration)
        return integration


LinkDeploymentProviderUseCase = LinkDeploymentPlatformUseCase
