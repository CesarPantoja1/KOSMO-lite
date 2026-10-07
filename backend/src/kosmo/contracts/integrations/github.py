from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from ulid import ULID

from kosmo.contracts.sdd.ids import ProjectId, UserId


class CodeSyncStatus(enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"


class GitHubApiError(RuntimeError):
    """Excepción base para errores ocurridos al comunicarse con la API de GitHub."""


class GitHubAuthenticationError(GitHubApiError):
    """Lanzada cuando el token de GitHub es inválido, expiró o no tiene permisos."""


class GitHubPermissionError(GitHubApiError):
    """Lanzada cuando la cuenta no tiene los alcances o permisos necesarios en GitHub."""


class GitHubResourceNotFoundError(GitHubApiError):
    """Lanzada cuando un recurso (usuario, repositorio) no existe en GitHub."""


class GitHubRepositoryAlreadyExistsError(GitHubApiError):
    """Lanzada cuando se intenta crear un repositorio con un nombre que ya existe."""


class GitHubRateLimitError(GitHubApiError):
    """Lanzada cuando se excede el límite de solicitudes de la API de GitHub."""


@dataclass(frozen=True, slots=True)
class GitHubUser:
    """Información del usuario autenticado en GitHub."""

    login: str
    id: int
    name: str | None = None
    email: str | None = None
    avatar_url: str | None = None
    html_url: str | None = None


@dataclass(frozen=True, slots=True)
class GitHubRepository:
    """Metadatos de un repositorio en GitHub."""

    id: int
    name: str
    full_name: str
    owner: str
    html_url: str
    clone_url: str
    is_private: bool
    default_branch: str = "main"
    description: str | None = None


@dataclass(frozen=True, slots=True)
class GitHubOAuthToken:
    """Token de acceso obtenido tras el flujo de autorización OAuth con GitHub."""

    access_token: str
    token_type: str = "bearer"
    scope: str = ""


class GitHubClientPort(Protocol):
    """Puerto para la interacción con la API REST de GitHub."""

    async def get_authenticated_user(self, token: str) -> GitHubUser:
        """Obtiene la información del usuario asociado al token provisto."""
        ...

    async def check_repository_exists(self, token: str, owner: str, repo_name: str) -> bool:
        """Verifica si un repositorio ya existe para el propietario indicado."""
        ...

    async def get_repository(self, token: str, owner: str, repo_name: str) -> GitHubRepository | None:
        """Obtiene los detalles de un repositorio o None si no existe."""
        ...

    async def create_repository(
        self,
        token: str,
        name: str,
        description: str = "",
        is_private: bool = False,
        auto_init: bool = False,
    ) -> GitHubRepository:
        """Crea un nuevo repositorio en la cuenta del usuario autenticado."""
        ...

    async def exchange_oauth_code(
        self,
        client_id: str,
        client_secret: str,
        code: str,
        redirect_uri: str | None = None,
        code_verifier: str | None = None,
    ) -> GitHubOAuthToken:
        """Intercambia un código de autorización OAuth por un token de acceso."""
        ...

    async def delete_repository(self, token: str, owner: str, repo_name: str) -> bool:
        """Elimina un repositorio remoto si existe."""
        ...

    async def grant_app_installation_access(
        self,
        token: str,
        repo_id: int,
        app_slug: str = "railway",
    ) -> bool:
        """Asocia un repositorio a la instalación de una GitHub App (ej. Railway)
        si existe y está en modo de repositorios seleccionados.
        """
        ...


class GitHubSyncStatus(enum.StrEnum):
    """Estado del ciclo de vida y sincronización del repositorio remoto en GitHub."""

    NOT_CREATED = "not_created"
    CREATED = "created"
    SYNCING = "syncing"
    SYNCED = "synced"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class UserGitHubIntegration:
    """Configuración de integración con GitHub a nivel de usuario."""

    user_id: UserId
    github_username: str
    encrypted_token: str
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class ProjectGitHubIntegration:
    """Vínculo de un proyecto de KOSMO con un repositorio remoto en GitHub."""

    project_id: ProjectId
    repo_url: str = ""
    repo_name: str | None = None
    is_public: bool = True
    default_branch: str = "main"
    last_push_at: datetime | None = None
    last_commit_hash: str | None = None
    sync_status: GitHubSyncStatus = GitHubSyncStatus.NOT_CREATED
    error_message: str | None = None
    last_synced_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class CodeSyncLog:
    """Registro de auditoría de cada intento de subida de código."""

    id: ULID = field(default_factory=ULID)
    project_id: ProjectId = field(default_factory=lambda: ProjectId(""))
    commit_sha: str | None = None
    status: CodeSyncStatus = CodeSyncStatus.FAILED
    message: str | None = None
    synced_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class UserGitHubIntegrationRepository(Protocol):
    async def get_by_user_id(self, user_id: UserId) -> UserGitHubIntegration | None: ...

    async def save(self, integration: UserGitHubIntegration) -> None: ...

    async def delete_by_user_id(self, user_id: UserId) -> bool: ...


class ProjectGitHubIntegrationRepository(Protocol):
    async def get_by_project_id(self, project_id: ProjectId) -> ProjectGitHubIntegration | None: ...

    async def save(self, integration: ProjectGitHubIntegration) -> ProjectGitHubIntegration: ...

    async def delete_by_project_id(self, project_id: ProjectId) -> bool: ...


class CodeSyncLogRepository(Protocol):
    async def add_log(self, log: CodeSyncLog) -> None: ...

    async def get_logs_by_project(self, project_id: ProjectId) -> list[CodeSyncLog]: ...
