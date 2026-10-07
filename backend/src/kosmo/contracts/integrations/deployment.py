import enum
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from kosmo.contracts.sdd.ids import ProjectId, UserId


class DeploymentProvider(enum.StrEnum):
    """Proveedores de nube soportados para el despliegue."""

    RAILWAY = "railway"


class DeploymentStatus(enum.StrEnum):
    """Estado del ciclo de vida de un despliegue."""

    NOT_CREATED = "not_created"
    BUILDING = "building"
    PUBLISHED = "published"
    FAILED = "failed"


class DeploymentApiError(RuntimeError):
    """Excepción base para errores ocurridos al comunicarse con la API de la plataforma de despliegue."""


class DeploymentAuthenticationError(DeploymentApiError):
    """Lanzada cuando el token de despliegue es inválido, expiró o fue rechazado por el proveedor."""


class DeploymentPermissionError(DeploymentApiError):
    """Lanzada cuando la cuenta no posee los permisos necesarios en la plataforma de despliegue."""


class DeploymentResourceNotFoundError(DeploymentApiError):
    """Lanzada cuando un recurso (servicio, volumen, proyecto) no existe en la plataforma de despliegue."""


class DeploymentRateLimitError(DeploymentApiError):
    """Lanzada cuando se excede el límite de solicitudes de la API de despliegue."""


class DeploymentConfigurationError(DeploymentApiError):
    """Lanzada cuando los parámetros de configuración del servicio o volumen son inválidos."""


class DeploymentPreconditionError(DeploymentApiError):
    """Lanzada cuando una precondición obligatoria para el despliegue no se cumple (409 Conflict)."""


class DeploymentAccountNotLinkedError(DeploymentPreconditionError):
    """Lanzada cuando el usuario no tiene vinculada su cuenta de la plataforma de despliegue."""


class DeploymentRepositoryMissingError(DeploymentPreconditionError):
    """Lanzada cuando el proyecto no posee un repositorio GitHub sincronizado para desplegar."""


# Alias específicos para Railway
RailwayApiError = DeploymentApiError
RailwayAuthenticationError = DeploymentAuthenticationError
RailwayPermissionError = DeploymentPermissionError
RailwayResourceNotFoundError = DeploymentResourceNotFoundError
RailwayRateLimitError = DeploymentRateLimitError
RailwayConfigurationError = DeploymentConfigurationError
RailwayPreconditionError = DeploymentPreconditionError
RailwayAccountNotLinkedError = DeploymentAccountNotLinkedError
RailwayRepositoryMissingError = DeploymentRepositoryMissingError


@dataclass(frozen=True, slots=True)
class VolumeConfig:
    """Configuración declarativa de volumen persistente."""

    mount_path: str
    size_mb: int | None = None


@dataclass(frozen=True, slots=True)
class PortSpec:
    """Especificación de puerto de escucha."""

    port: int
    protocol: str = "http"


@dataclass(frozen=True, slots=True)
class EnvironmentVariable:
    """Variable de entorno a inyectar en el servicio."""

    key: str
    value: str
    is_secret: bool = False


@dataclass(frozen=True, slots=True)
class DeploymentOAuthToken:
    """Token de acceso obtenido tras el flujo de autorización OAuth del proveedor."""

    access_token: str
    token_type: str = "bearer"
    refresh_token: str | None = None
    expires_in: int | None = None
    scope: str = ""


@dataclass(frozen=True, slots=True)
class UserDeploymentIntegration:
    """Configuración de integración con la plataforma de despliegue a nivel de usuario."""

    user_id: UserId
    provider: DeploymentProvider
    encrypted_token: str
    provider_username: str | None = None
    encrypted_refresh_token: str | None = None
    scopes: tuple[str, ...] = field(default_factory=tuple)
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class ProjectDeployment:
    """Vínculo de un proyecto de KOSMO con un servicio de despliegue remoto."""

    project_id: ProjectId
    provider: DeploymentProvider
    service_id: str | None = None
    service_name: str | None = None
    public_url: str | None = None
    status: DeploymentStatus = DeploymentStatus.NOT_CREATED
    build_logs_url: str | None = None
    last_deployed_at: datetime | None = None
    error_message: str | None = None
    volumes: tuple[VolumeConfig, ...] = field(default_factory=tuple)
    ports: tuple[PortSpec, ...] = field(default_factory=tuple)
    env_vars: tuple[EnvironmentVariable, ...] = field(default_factory=tuple)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class UserDeploymentIntegrationRepository(Protocol):
    async def get_by_user_id(
        self, user_id: UserId, provider: DeploymentProvider
    ) -> UserDeploymentIntegration | None: ...

    async def save(self, integration: UserDeploymentIntegration) -> None: ...

    async def delete_by_user_id(
        self, user_id: UserId, provider: DeploymentProvider = DeploymentProvider.RAILWAY
    ) -> bool: ...


class ProjectDeploymentRepository(Protocol):
    async def get_by_project_id(self, project_id: ProjectId) -> ProjectDeployment | None: ...

    async def list_by_status(self, status: DeploymentStatus) -> list[ProjectDeployment]: ...

    async def save(self, deployment: ProjectDeployment) -> ProjectDeployment: ...

    async def delete_by_project_id(self, project_id: ProjectId) -> bool: ...


class DeploymentProviderPort(Protocol):
    """Puerto para la interacción con la API de la plataforma de despliegue (Ej: Railway)."""

    async def exchange_oauth_code(
        self,
        code: str,
        redirect_uri: str | None = None,
        code_verifier: str | None = None,
    ) -> DeploymentOAuthToken: ...

    async def get_authenticated_user(self, token: str) -> dict[str, str]:
        """Consulta el perfil del usuario autenticado en la plataforma (sub, name, email)."""
        ...

    async def refresh_access_token(self, refresh_token: str) -> DeploymentOAuthToken:
        """Renueva el token de acceso utilizando un refresh token rotado."""
        ...

    async def create_service(
        self,
        token: str,
        repo_url: str,
        env_vars: list[EnvironmentVariable],
        ports: list[PortSpec],
        service_name: str | None = None,
    ) -> str: ...

    async def configure_volume(self, token: str, service_id: str, volume: VolumeConfig) -> None: ...

    async def trigger_deployment(
        self,
        token: str,
        service_id: str,
        commit_sha: str | None = None,
    ) -> None: ...

    async def get_service_status(
        self,
        token: str,
        service_id: str,
    ) -> tuple[DeploymentStatus, str | None, str | None]:
        """
        Retorna (status, public_url, build_logs_url_or_error)
        """
        ...

    async def delete_service(self, token: str, service_id: str) -> bool:
        """Elimina el servicio o despliegue remoto en la plataforma de nube."""
        ...


class DeploymentWorkerPort(Protocol):
    """Puerto para el worker asíncrono de procesamiento y sondeo de despliegues."""

    def start_monitoring(
        self,
        project_id: ProjectId,
        user_id: UserId,
        *,
        max_attempts: int = 60,
        delay_seconds: int = 10,
        provider: DeploymentProvider = DeploymentProvider.RAILWAY,
    ) -> object: ...

    def is_monitoring(self, project_id: ProjectId) -> bool: ...

    def cancel_monitoring(self, project_id: ProjectId) -> bool: ...

    async def shutdown(self) -> None: ...
