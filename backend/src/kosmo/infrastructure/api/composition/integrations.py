from __future__ import annotations

from dataclasses import dataclass

from kosmo.application.integrations.delete_deployment import (
    DeleteDeploymentUseCase,
)
from kosmo.application.integrations.execute_ephemeral_validation import (
    ExecuteEphemeralValidationUseCase,
)
from kosmo.application.integrations.handle_deployment_failure import (
    HandleDeploymentFailureUseCase,
)
from kosmo.application.integrations.link_deployment_provider import (
    LinkDeploymentPlatformUseCase,
)
from kosmo.application.integrations.link_github_account import LinkGitHubAccountUseCase
from kosmo.application.integrations.monitor_deployment_status import (
    MonitorDeploymentStatusUseCase,
)
from kosmo.application.integrations.orchestrate_cloud_deployment import (
    OrchestrateCloudDeploymentUseCase,
)
from kosmo.application.integrations.sync_github_repository import SyncGitHubRepositoryUseCase
from kosmo.config import Settings
from kosmo.contracts.auth import SecretCipher
from kosmo.contracts.integrations.deployment import DeploymentProviderPort
from kosmo.contracts.integrations.git import GitWorkspacePort
from kosmo.contracts.integrations.github import GitHubClientPort
from kosmo.contracts.sdd.codegen import CodeRunnerPort, WorkspaceManagerPort
from kosmo.infrastructure.git import LocalGitWorkspaceAdapter
from kosmo.infrastructure.integrations.deployment_worker import DeploymentPollingWorker
from kosmo.infrastructure.integrations.github_client import GitHubHttpClient
from kosmo.infrastructure.integrations.railway_client import RailwayHttpClient
from kosmo.infrastructure.persistence.postgres.registry import RepositoryRegistry
from kosmo.infrastructure.sandbox.docker_runner import EphemeralDockerCodeRunner


@dataclass(frozen=True, slots=True)
class IntegrationsComponents:
    """Componentes cableados para integraciones con servicios externos (GitHub, Railway, OAuth)."""

    link_github_account: LinkGitHubAccountUseCase
    sync_github_repository: SyncGitHubRepositoryUseCase
    execute_ephemeral_validation: ExecuteEphemeralValidationUseCase
    github_client: GitHubClientPort
    git_workspace: GitWorkspacePort
    link_deployment_platform: LinkDeploymentPlatformUseCase
    orchestrate_cloud_deployment: OrchestrateCloudDeploymentUseCase
    monitor_deployment_status: MonitorDeploymentStatusUseCase
    handle_deployment_failure: HandleDeploymentFailureUseCase
    delete_deployment: DeleteDeploymentUseCase
    railway_client: DeploymentProviderPort
    deployment_worker: DeploymentPollingWorker


def build_integrations_components(
    settings: Settings,
    repos: RepositoryRegistry,
    workspace_manager: WorkspaceManagerPort,
    cipher: SecretCipher,
    code_runner: CodeRunnerPort | None = None,
) -> IntegrationsComponents:
    github_client = GitHubHttpClient()
    git_workspace = LocalGitWorkspaceAdapter()
    runner = code_runner or EphemeralDockerCodeRunner()

    ephemeral_validator = ExecuteEphemeralValidationUseCase(
        code_runner=runner,
        workspace_manager=workspace_manager,
    )

    client_id = settings.github_client_id or ""
    client_secret = (
        settings.github_client_secret.get_secret_value() if settings.github_client_secret is not None else ""
    )

    link_github_account = LinkGitHubAccountUseCase(
        oauth_client=github_client,
        cipher=cipher,
        repo=repos.user_github_integrations,
        client_id=client_id,
        client_secret=client_secret,
        user_repo=repos.users,
    )

    sync_github_repository = SyncGitHubRepositoryUseCase(
        project_github_repo=repos.project_integrations,
        user_github_repo=repos.user_github_integrations,
        github_client=github_client,
        git_workspace=git_workspace,
        workspace_manager=workspace_manager,
        cipher=cipher,
        sync_log_repo=repos.sync_logs,
        ephemeral_validator=ephemeral_validator,
        project_repo=repos.projects,
    )

    railway_client_id = settings.railway_client_id or ""
    railway_client_secret = (
        settings.railway_client_secret.get_secret_value() if settings.railway_client_secret is not None else ""
    )
    railway_client = RailwayHttpClient(
        client_id=railway_client_id,
        client_secret=railway_client_secret,
    )

    link_deployment_platform = LinkDeploymentPlatformUseCase(
        deployment_client=railway_client,
        cipher=cipher,
        repo=repos.user_deployment_integrations,
    )

    orchestrate_cloud_deployment = OrchestrateCloudDeploymentUseCase(
        project_deployment_repo=repos.project_deployments,
        user_deployment_repo=repos.user_deployment_integrations,
        project_github_repo=repos.project_integrations,
        deployment_client=railway_client,
        cipher=cipher,
        sync_github_use_case=sync_github_repository,
    )

    monitor_deployment_status = MonitorDeploymentStatusUseCase(
        project_deployment_repo=repos.project_deployments,
        user_deployment_repo=repos.user_deployment_integrations,
        deployment_client=railway_client,
        cipher=cipher,
    )

    handle_deployment_failure = HandleDeploymentFailureUseCase(
        project_deployment_repo=repos.project_deployments,
    )

    deployment_worker = DeploymentPollingWorker(
        monitor_use_case=monitor_deployment_status,
        failure_handler=handle_deployment_failure,
    )

    delete_deployment = DeleteDeploymentUseCase(
        project_deployment_repo=repos.project_deployments,
        user_deployment_repo=repos.user_deployment_integrations,
        deployment_client=railway_client,
        cipher=cipher,
        deployment_worker=deployment_worker,
    )

    return IntegrationsComponents(
        link_github_account=link_github_account,
        sync_github_repository=sync_github_repository,
        execute_ephemeral_validation=ephemeral_validator,
        github_client=github_client,
        git_workspace=git_workspace,
        link_deployment_platform=link_deployment_platform,
        orchestrate_cloud_deployment=orchestrate_cloud_deployment,
        monitor_deployment_status=monitor_deployment_status,
        handle_deployment_failure=handle_deployment_failure,
        delete_deployment=delete_deployment,
        railway_client=railway_client,
        deployment_worker=deployment_worker,
    )
