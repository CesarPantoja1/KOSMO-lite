from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from kosmo.application.codegen.analyze_feature_integration import (
    AnalyzeFeatureIntegrationUseCase,
)
from kosmo.application.codegen.delete_feature_code import DeleteFeatureCodeUseCase
from kosmo.application.codegen.generate_feature_implementation import (
    GenerateFeatureImplementationUseCase,
)
from kosmo.application.codegen.get_implementation_record import (
    GetImplementationRecordUseCase,
)
from kosmo.application.codegen.validate_workspace import ValidateWorkspaceUseCase
from kosmo.config import Settings
from kosmo.contracts.sdd.codegen import CodeRunnerPort, FileSystemReader
from kosmo.infrastructure.api.implementation_broker import ImplementationEventBroker
from kosmo.infrastructure.codegen.isolated_opencode import IsolatedOpenCodeClient
from kosmo.infrastructure.codegen.opencode_client import OpenCodeHttpClient
from kosmo.infrastructure.codegen.workspace import LocalFileSystemReader, LocalWorkspaceManager
from kosmo.infrastructure.persistence.postgres.registry import RepositoryRegistry
from kosmo.infrastructure.sandbox.code_runner import SubprocessCodeRunner
from kosmo.infrastructure.sandbox.remote_code_runner import RemoteCodeRunner
from kosmo.infrastructure.security.fernet_vault import FernetSecretCipher

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from kosmo.application.integrations.sync_github_repository import SyncGitHubRepositoryUseCase
    from kosmo.infrastructure.api.composition.integrations import IntegrationsComponents


@dataclass(frozen=True, slots=True)
class CodegenComponents:
    """Dependencias cableadas del subsistema de generación de código."""

    generate_feature_implementation: GenerateFeatureImplementationUseCase
    validate_workspace: ValidateWorkspaceUseCase
    delete_feature_code: DeleteFeatureCodeUseCase
    workspace_manager: LocalWorkspaceManager
    opencode_client: OpenCodeHttpClient | IsolatedOpenCodeClient
    code_runner: CodeRunnerPort
    implementation_broker: ImplementationEventBroker
    get_implementation_record: GetImplementationRecordUseCase | None = None


def build_code_runner(settings: Settings) -> CodeRunnerPort:
    """Construye el ejecutor de código según la configuración (remoto o subproceso local)."""
    if settings.code_runner_base_url and settings.code_runner_token is not None:
        return RemoteCodeRunner(
            settings.code_runner_base_url,
            settings.code_runner_token.get_secret_value(),
        )
    return SubprocessCodeRunner()


def build_workspace_manager(
    settings: Settings,
    repos: RepositoryRegistry,
    code_runner: CodeRunnerPort,
    fs_reader: FileSystemReader | None = None,
) -> LocalWorkspaceManager:
    """Construye el administrador local de workspaces con soporte opcional de previews en Cloudflare."""
    reader = fs_reader or LocalFileSystemReader()
    return LocalWorkspaceManager(
        workspaces_root=settings.kosmo_workspaces_dir,
        workspace_repo=repos.workspaces,
        mcp_url=settings.kosmo_mcp_base_url,
        project_repo=repos.projects,
        code_runner=code_runner,
        fs_reader=reader,
    )


def build_codegen_components(
    settings: Settings,
    repos: RepositoryRegistry,
    broker: ImplementationEventBroker | None = None,
    sync_github_repository: SyncGitHubRepositoryUseCase | None = None,
    workspace_manager: LocalWorkspaceManager | None = None,
    code_runner: CodeRunnerPort | None = None,
    fs_reader: FileSystemReader | None = None,
    redis: Redis | None = None,
    integrations: IntegrationsComponents | None = None,
) -> CodegenComponents:
    runner = code_runner or build_code_runner(settings)
    reader = fs_reader or LocalFileSystemReader()
    ws_manager = workspace_manager or build_workspace_manager(settings, repos, code_runner=runner, fs_reader=reader)
    if settings.env in {"staging", "production"} and not settings.opencode_launcher_base_url:
        raise ValueError("La implementación en staging/producción requiere el lanzador aislado de OpenCode.")
    if settings.opencode_launcher_base_url:
        if settings.fernet_master_key is None or settings.opencode_launcher_token is None:
            raise ValueError("La implementación aislada requiere FERNET_MASTER_KEY y OPENCODE_LAUNCHER_TOKEN.")
        opencode_client: OpenCodeHttpClient | IsolatedOpenCodeClient = IsolatedOpenCodeClient(
            launcher_url=settings.opencode_launcher_base_url,
            launcher_token=settings.opencode_launcher_token.get_secret_value(),
            config_repo=repos.user_ai_configs,
            cipher=FernetSecretCipher(settings.fernet_master_key.get_secret_value()),
        )
    else:
        opencode_client = OpenCodeHttpClient(
            base_url=settings.opencode_base_url,
            server_username=settings.opencode_server_username,
            server_password=(
                settings.opencode_server_password.get_secret_value()
                if settings.opencode_server_password is not None
                else None
            ),
            model=settings.opencode_model,
            timeout_seconds=settings.opencode_timeout_seconds,
            read_timeout_seconds=settings.opencode_read_timeout_seconds,
            connect_timeout_seconds=settings.opencode_connect_timeout_seconds,
            write_timeout_seconds=settings.opencode_write_timeout_seconds,
        )
    integration_analyzer = AnalyzeFeatureIntegrationUseCase(
        feature_repo=repos.features,
        document_repo=repos.documents,
        implementation_repo=repos.implementations,
    )
    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=repos.features,
        requirement_repo=repos.requirements,
        activity_diagram_repo=repos.diagrams,
        workspace_manager=ws_manager,
        opencode_client=opencode_client,
        code_runner=runner,
        implementation_repo=repos.implementations,
        traceability_repo=repos.traceability,
        project_repo=repos.projects,
        document_repo=repos.documents,
        sync_github_repository=sync_github_repository,
        fs_reader=reader,
        integration_analyzer=integration_analyzer,
        orchestrate_cloud_deployment=integrations.orchestrate_cloud_deployment if integrations else None,
        project_deployment_repo=repos.project_deployments,
        deployment_worker=integrations.deployment_worker if integrations else None,
    )
    implementation_broker = broker or ImplementationEventBroker(
        history_ttl_seconds=settings.implementation_broker_ttl_seconds,
        redis=redis,
    )
    get_implementation_record = GetImplementationRecordUseCase(
        implementation_repo=repos.implementations,
        requirement_repo=repos.requirements,
        traceability_repo=repos.traceability,
    )
    return CodegenComponents(
        generate_feature_implementation=use_case,
        validate_workspace=ValidateWorkspaceUseCase(
            code_runner=runner,
            workspace_manager=ws_manager,
        ),
        delete_feature_code=DeleteFeatureCodeUseCase(
            workspace_manager=ws_manager,
            code_runner=runner,
            opencode_client=opencode_client,
            implementation_repo=repos.implementations,
        ),
        workspace_manager=ws_manager,
        opencode_client=opencode_client,
        code_runner=runner,
        implementation_broker=implementation_broker,
        get_implementation_record=get_implementation_record,
    )
