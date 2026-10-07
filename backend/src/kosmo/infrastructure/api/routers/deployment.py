from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from kosmo.application.integrations.delete_deployment import (
    DeleteDeploymentCommand,
    DeleteDeploymentUseCase,
)
from kosmo.application.integrations.orchestrate_cloud_deployment import (
    OrchestrateCloudDeploymentCommand,
    OrchestrateCloudDeploymentUseCase,
)
from kosmo.contracts.auth import Principal
from kosmo.contracts.integrations.deployment import (
    DeploymentApiError,
    DeploymentAuthenticationError,
    DeploymentConfigurationError,
    DeploymentPermissionError,
    DeploymentPreconditionError,
    DeploymentProvider,
    DeploymentRateLimitError,
    DeploymentStatus,
)
from kosmo.contracts.sdd.ids import ProjectId, UserId
from kosmo.infrastructure.api.dependencies import (
    get_container,
    get_delete_deployment_use_case,
    get_deployment_worker,
    get_orchestrate_cloud_deployment_use_case,
    get_principal,
)
from kosmo.infrastructure.api.dependencies.rate_limit import ProjectGenerationRateLimiter
from kosmo.infrastructure.api.schemas import (
    DeployRailwayRequest,
    DeployStatusEnum,
    ProjectDeployStatusResponse,
)
from kosmo.infrastructure.integrations.deployment_worker import DeploymentPollingWorker

router = APIRouter(prefix="/api/v1/projects/{project_id}/deploy", tags=["deploy"])

_generation_rate_limiter = ProjectGenerationRateLimiter()


def _require_project_owner(project: object, principal: Principal, project_id: str) -> None:
    """No expone el estado ni permite operar despliegues de otros usuarios."""
    if project is None or str(getattr(project, "owner_id", "")) != principal.subject:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proyecto '{project_id}' no encontrado.",
        )


def _map_deploy_status(status: DeploymentStatus) -> str:
    match status:
        case DeploymentStatus.NOT_CREATED:
            return DeployStatusEnum.idle.value
        case DeploymentStatus.BUILDING:
            return DeployStatusEnum.building.value
        case DeploymentStatus.PUBLISHED:
            return DeployStatusEnum.ready.value
        case DeploymentStatus.FAILED:
            return DeployStatusEnum.failed.value
        case _:
            return DeployStatusEnum.idle.value


@router.get(
    "",
    response_model=ProjectDeployStatusResponse,
    summary="Obtener estado de despliegue en la nube",
    description="Consulta el estado de publicación del proyecto en Railway, la URL pública y logs en caso de fallo.",
)
async def get_project_deploy_status(
    project_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(get_principal)],
) -> ProjectDeployStatusResponse:
    container = get_container(request)
    proj_id = ProjectId(project_id)

    project = await container.repos.projects.by_id(proj_id)
    _require_project_owner(project, principal, project_id)

    deployment = await container.repos.project_deployments.get_by_project_id(proj_id)
    if deployment is None or deployment.status == DeploymentStatus.NOT_CREATED:
        return ProjectDeployStatusResponse(
            service_id=None,
            service_name=None,
            deploy_url=None,
            status=DeployStatusEnum.idle.value,
            last_deploy_at=None,
            error_message=None,
            error_log_url=None,
        )

    return ProjectDeployStatusResponse(
        service_id=deployment.service_id,
        service_name=deployment.service_name,
        deploy_url=deployment.public_url,
        status=_map_deploy_status(deployment.status),
        last_deploy_at=deployment.last_deployed_at,
        error_message=deployment.error_message,
        error_log_url=deployment.build_logs_url,
    )


@router.post(
    "/railway",
    response_model=ProjectDeployStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Iniciar despliegue del proyecto en Railway",
    description="Orquesta la publicación de la aplicación en Railway e inicia el monitoreo en segundo plano.",
)
async def deploy_to_railway(
    project_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(get_principal)],
    use_case: Annotated[OrchestrateCloudDeploymentUseCase, Depends(get_orchestrate_cloud_deployment_use_case)],
    worker: Annotated[DeploymentPollingWorker, Depends(get_deployment_worker)],
    body: DeployRailwayRequest | None = None,
    _rate: Annotated[None, Depends(_generation_rate_limiter)] = None,
) -> ProjectDeployStatusResponse:
    container = get_container(request)
    proj_id = ProjectId(project_id)

    project = await container.repos.projects.by_id(proj_id)
    _require_project_owner(project, principal, project_id)

    cmd = OrchestrateCloudDeploymentCommand(
        project_id=proj_id,
        provider=DeploymentProvider.RAILWAY,
        service_name=body.service_name if body else None,
        environment_variables=body.environment_variables if body else None,
    )

    try:
        deployment = await use_case.execute(principal, cmd)
    except DeploymentPreconditionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except DeploymentConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except DeploymentAuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except DeploymentPermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except DeploymentRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    except DeploymentApiError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # Iniciar sondeo asíncrono no bloqueante en segundo plano
    worker.start_monitoring(
        project_id=proj_id,
        user_id=UserId(principal.subject),
        provider=DeploymentProvider.RAILWAY,
    )

    return ProjectDeployStatusResponse(
        service_id=deployment.service_id,
        service_name=deployment.service_name or (body.service_name if body else None),
        deploy_url=deployment.public_url,
        status=DeployStatusEnum.building.value,
        last_deploy_at=deployment.last_deployed_at,
        error_message=deployment.error_message,
        error_log_url=deployment.build_logs_url,
    )


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar despliegue del proyecto",
    description="Elimina el servicio remoto en la nube y retira el registro de despliegue del proyecto.",
)
async def delete_project_deployment(
    project_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(get_principal)],
    use_case: Annotated[DeleteDeploymentUseCase, Depends(get_delete_deployment_use_case)],
) -> None:
    container = get_container(request)
    proj_id = ProjectId(project_id)

    project = await container.repos.projects.by_id(proj_id)
    _require_project_owner(project, principal, project_id)

    cmd = DeleteDeploymentCommand(
        project_id=proj_id,
        provider=DeploymentProvider.RAILWAY,
    )
    await use_case.execute(principal, cmd)
