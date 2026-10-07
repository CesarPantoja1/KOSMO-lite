from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from kosmo.contracts.sdd.ids import FeatureId, ImplementationId, ProjectId, WorkspaceId


class WorkspaceStatus(StrEnum):
    NOT_CREATED = "not_created"
    READY = "ready"
    IN_USE = "in_use"
    VALIDATING = "validating"


class FeatureImplementationStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    IMPLEMENTED = "implemented"
    REQUIRES_REVIEW = "requires_review"
    FAILED = "failed"


class FileAction(StrEnum):
    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"


class ValidationStep(StrEnum):
    STRUCTURE = "structure"
    TYPECHECK = "typecheck"
    LINT = "lint"
    TESTS = "tests"
    BUILD = "build"


class ValidationSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class OpenCodeEventType(StrEnum):
    SESSION_CREATED = "session_created"
    PLAN_PROGRESS = "plan_progress"
    PLAN_COMPLETE = "plan_complete"
    BUILD_PROGRESS = "build_progress"
    BUILD_COMPLETE = "build_complete"
    FILE_EDIT = "file_edit"
    RETRY = "retry"
    ERROR = "error"
    DONE = "done"


@dataclass(frozen=True)
class OpenCodeEvent:
    event_type: OpenCodeEventType | str
    session_id: str
    data: dict[str, Any] = field(default_factory=dict)  # type: ignore[reportUnknownVariableType]
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    run_id: str = ""


@dataclass(frozen=True)
class OpenCodeSession:
    session_id: str
    workspace_dir: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    title: str = ""


@dataclass(frozen=True)
class FileOperation:
    path: str
    action: FileAction
    description: str = ""
    rationale: str = ""
    target_symbols: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ImplementationPlan:
    feature_id: FeatureId
    operations: tuple[FileOperation, ...] = field(default_factory=tuple)
    summary: str = ""
    estimated_effort: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ValidationErrorDetail:
    file: str
    line: int = 0
    column: int = 0
    message: str = ""
    severity: ValidationSeverity = ValidationSeverity.ERROR
    code: str | None = None


@dataclass(frozen=True)
class ValidationStepResult:
    step: ValidationStep
    success: bool
    duration_ms: int = 0
    exit_code: int = 0
    raw_output: str = ""
    errors: tuple[ValidationErrorDetail, ...] = field(default_factory=tuple)
    error_messages: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ValidationRunResult:
    steps: tuple[ValidationStepResult, ...] = field(default_factory=tuple)
    all_passed: bool = False
    total_duration_ms: int = 0
    executed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    error_summary: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CodeWorkspace:
    id: WorkspaceId
    project_id: ProjectId
    status: WorkspaceStatus = WorkspaceStatus.NOT_CREATED
    workspace_dir: str | None = None
    manifest_files: tuple[str, ...] = field(default_factory=tuple)
    current_branch: str = "main"
    is_locked: bool = False
    locked_at: datetime | None = None
    locked_by: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class FeatureImplementation:
    id: ImplementationId
    feature_id: FeatureId
    project_id: ProjectId
    status: FeatureImplementationStatus = FeatureImplementationStatus.PENDING
    session_id: str | None = None
    plan: ImplementationPlan | None = None
    last_validation: ValidationRunResult | None = None
    attempt_count: int = 0
    max_attempts: int = 3
    generated_files: tuple[str, ...] = field(default_factory=tuple)
    retry_history: tuple[tuple[str, ...], ...] = field(default_factory=tuple)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class WorkspaceManagerPort(Protocol):
    async def ensure_workspace(self, project_id: ProjectId) -> CodeWorkspace: ...

    async def get_workspace(self, project_id: ProjectId) -> CodeWorkspace | None: ...

    async def get_manifest(self, workspace: CodeWorkspace) -> tuple[str, ...]: ...

    async def is_locked(self, project_id: ProjectId) -> bool: ...

    async def acquire_lock(self, project_id: ProjectId) -> None: ...

    async def release_lock(self, project_id: ProjectId) -> None: ...

    async def rollback_workspace(self, project_id: ProjectId) -> None: ...

    async def delete_workspace(self, project_id: ProjectId) -> None: ...

    async def commit_workspace(self, project_id: ProjectId, message: str) -> str | None: ...

    async def remove_feature_paths(self, project_id: ProjectId, slug: str) -> tuple[str, ...]: ...

    async def update_text_file(
        self,
        project_id: ProjectId,
        relative_path: str,
        transform: Callable[[str], str],
    ) -> None: ...

    async def revert_commit(self, project_id: ProjectId, commit: str) -> None: ...


@runtime_checkable
class FileSystemReader(Protocol):
    """Protocolo para operaciones de lectura del sistema de archivos desacopladas de infraestructura."""

    def list_files(self, root: str | Path) -> tuple[str, ...]:
        """Retorna las rutas relativas en formato POSIX de todos los archivos bajo root."""
        ...

    def read_text(self, path: str | Path) -> str | None:
        """Lee el contenido de un archivo de texto en UTF-8 o retorna None si no existe o falla."""
        ...


FileSystemReaderPort = FileSystemReader


@runtime_checkable
class FileSystemWriter(Protocol):
    """Protocolo para operaciones de escritura del sistema de archivos desacopladas de infraestructura."""

    def write_text(self, path: str | Path, content: str) -> None:
        """Escribe contenido de texto en UTF-8 en la ruta indicada creando directorios si es necesario."""
        ...


FileSystemWriterPort = FileSystemWriter


class CodeRunnerPort(Protocol):
    async def run_step(
        self,
        workspace_dir: str,
        step: ValidationStep,
        *,
        timeout_seconds: int = 300,
    ) -> ValidationStepResult: ...

    async def run_command(
        self,
        workspace_dir: str,
        command: str,
        *,
        timeout_seconds: int = 300,
    ) -> ValidationStepResult: ...

    async def run_pipeline(
        self,
        workspace_dir: str,
        steps: tuple[ValidationStep, ...] = (
            ValidationStep.TYPECHECK,
            ValidationStep.LINT,
            ValidationStep.TESTS,
            ValidationStep.BUILD,
        ),
        run_id: str = "",
    ) -> ValidationRunResult: ...


class OpenCodeClientPort(Protocol):
    async def health_check(self) -> bool: ...

    async def create_session(
        self,
        workspace_dir: str,
        *,
        title: str = "",
    ) -> OpenCodeSession: ...

    def send_prompt(
        self,
        session_id: str,
        prompt: str,
        *,
        agent: str = "plan",
    ) -> AsyncIterator[OpenCodeEvent]: ...

    async def close_session(self, session_id: str) -> None: ...


class WorkspaceRepository(Protocol):
    async def by_project_id(self, project_id: ProjectId) -> CodeWorkspace | None: ...

    async def by_id(self, workspace_id: WorkspaceId) -> CodeWorkspace | None: ...

    async def save(self, workspace: CodeWorkspace) -> CodeWorkspace: ...

    async def delete(self, project_id: ProjectId) -> None: ...

    async def update_lock(
        self,
        project_id: ProjectId,
        is_locked: bool,
        locked_by: str | None = None,
    ) -> CodeWorkspace | None: ...

    async def release_lock(self, project_id: ProjectId) -> CodeWorkspace | None: ...


class FeatureImplementationRepository(Protocol):
    async def by_feature_id(self, feature_id: FeatureId) -> FeatureImplementation | None: ...

    async def by_id(self, implementation_id: ImplementationId) -> FeatureImplementation | None: ...

    async def list_by_project(self, project_id: ProjectId) -> list[FeatureImplementation]: ...

    async def list_by_status(self, status: FeatureImplementationStatus) -> list[FeatureImplementation]: ...

    async def save(self, implementation: FeatureImplementation) -> FeatureImplementation: ...

    async def delete(self, feature_id: FeatureId) -> None: ...
