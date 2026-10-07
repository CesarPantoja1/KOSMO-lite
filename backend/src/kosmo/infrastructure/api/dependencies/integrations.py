from __future__ import annotations

from fastapi import Request

from kosmo.application.integrations.delete_deployment import DeleteDeploymentUseCase
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
from kosmo.infrastructure.api.dependencies.container import get_container
from kosmo.infrastructure.integrations.deployment_worker import DeploymentPollingWorker


def get_link_github_account_use_case(request: Request) -> LinkGitHubAccountUseCase:
    return get_container(request).integrations.link_github_account


def get_sync_github_repository_use_case(request: Request) -> SyncGitHubRepositoryUseCase:
    return get_container(request).integrations.sync_github_repository


def get_execute_ephemeral_validation_use_case(request: Request) -> ExecuteEphemeralValidationUseCase:
    return get_container(request).integrations.execute_ephemeral_validation


def get_orchestrate_cloud_deployment_use_case(request: Request) -> OrchestrateCloudDeploymentUseCase:
    return get_container(request).integrations.orchestrate_cloud_deployment


def get_monitor_deployment_status_use_case(request: Request) -> MonitorDeploymentStatusUseCase:
    return get_container(request).integrations.monitor_deployment_status


def get_link_deployment_platform_use_case(request: Request) -> LinkDeploymentPlatformUseCase:
    return get_container(request).integrations.link_deployment_platform


def get_handle_deployment_failure_use_case(request: Request) -> HandleDeploymentFailureUseCase:
    return get_container(request).integrations.handle_deployment_failure


def get_delete_deployment_use_case(request: Request) -> DeleteDeploymentUseCase:
    return get_container(request).integrations.delete_deployment


def get_deployment_worker(request: Request) -> DeploymentPollingWorker:
    return get_container(request).integrations.deployment_worker
