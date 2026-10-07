import json
from collections.abc import AsyncGenerator
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sse_starlette.sse import EventSourceResponse

from kosmo.application.codegen.generate_feature_implementation import (
    GenerateFeatureImplementationInput,
)
from kosmo.application.codegen.validate_workspace import ValidateWorkspaceInput, WorkspaceNotFoundError
from kosmo.contracts.auth import Principal
from kosmo.contracts.sdd.codegen import FeatureImplementation
from kosmo.contracts.sdd.ids import FeatureId, ImplementationId, ProjectId
from kosmo.domain.codegen.path_safety import UnsafePathError, ensure_safe_path
from kosmo.infrastructure.api.composition import AppContainer
from kosmo.infrastructure.api.dependencies.auth import get_principal, require_project_owner
from kosmo.infrastructure.api.dependencies.container import get_container
from kosmo.infrastructure.api.dependencies.rate_limit import ProjectGenerationRateLimiter
from kosmo.infrastructure.api.schemas import (
    GenerateImplementationRequest,
    GenerateImplementationResponse,
    ImplementationFileContentResponse,
    ImplementationRecordResponse,
    ValidateWorkspaceResponse,
    ValidationStepResultResponse,
)

_log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/implementations", tags=["Implementations"])

_generation_rate_limiter = ProjectGenerationRateLimiter()


async def _require_project_owner(container: AppContainer, project_id: ProjectId, principal: Principal) -> None:
    """Hide cross-tenant resources behind the same 404 contract as absent ones."""
    await require_project_owner(container, project_id, principal)


async def _owned_implementation(
    container: AppContainer,
    implementation_id: ImplementationId,
    principal: Principal,
) -> FeatureImplementation:
    implementation = await container.repos.implementations.by_id(implementation_id)
    if implementation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró la implementación {implementation_id}",
        )
    await _require_project_owner(container, implementation.project_id, principal)
    return implementation


@router.post(
    "",
    response_model=GenerateImplementationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Iniciar implementación",
    description="Inicia asíncronamente la generación de código para una característica.",
)
async def start_implementation(
    request: GenerateImplementationRequest,
    http_request: Request,
    principal: Annotated[Principal, Depends(get_principal)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> GenerateImplementationResponse:
    use_case = container.codegen.generate_feature_implementation

    feature_id_obj = FeatureId(request.feature_id)
    impl_id = f"impl_{feature_id_obj}"
    feature = await container.repos.features.by_id(feature_id_obj)
    if feature is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Característica no encontrada")
    await _require_project_owner(container, feature.project_id, principal)
    await _generation_rate_limiter(http_request, project_id=str(feature.project_id))

    input_data = GenerateFeatureImplementationInput(
        feature_id=feature_id_obj,
        max_retries=request.max_retries,
    )

    broker_instance = container.codegen.implementation_broker

    # Evitar doble generación concurrente (doble clic)
    if broker_instance.is_running(impl_id):
        return GenerateImplementationResponse(implementation_id=impl_id)

    broker_instance.start_implementation(
        implementation_id=impl_id,
        use_case=use_case,
        input_data=input_data,
        project_id=str(feature.project_id),
        user_id=principal.subject,
    )

    return GenerateImplementationResponse(implementation_id=impl_id)


@router.get(
    "",
    response_model=ImplementationRecordResponse,
    summary="Obtener implementación por característica",
    description="Devuelve el registro persistido de la implementación de una característica, "
    "o 404 si aún no existe. Es la fuente de verdad para que el frontend no pida "
    "regenerar lo ya implementado.",
)
async def get_implementation_by_feature(
    feature_id: Annotated[str, Query(min_length=1, description="ID de la característica")],
    principal: Annotated[Principal, Depends(get_principal)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> ImplementationRecordResponse:
    uc = container.codegen.get_implementation_record
    if uc is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="El servicio de consulta de implementación no está disponible",
        )
    result = await uc.execute(FeatureId(feature_id))
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró una implementación para la característica {feature_id}",
        )
    await _require_project_owner(container, result.implementation.project_id, principal)

    impl = result.implementation
    return ImplementationRecordResponse(
        implementation_id=str(impl.id),
        feature_id=str(impl.feature_id),
        project_id=str(impl.project_id),
        status=str(getattr(impl.status, "value", impl.status)),
        generated_files=list(impl.generated_files),
        features_count=result.features_count,
        screens_count=result.screens_count,
        requirements_count=result.requirements_count,
        validations_passed=result.validations_passed,
        validations_total=result.validations_total,
        traceability_edges_count=result.traceability_edges_count,
        technologies=list(result.technologies),
        updated_at=impl.updated_at,
    )


@router.get(
    "/{implementation_id}/events",
    summary="Suscribirse a eventos",
    description="Flujo SSE para eventos en tiempo real de la implementación.",
)
async def stream_implementation_events(
    implementation_id: str,
    principal: Annotated[Principal, Depends(get_principal)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> EventSourceResponse:
    broker_instance = container.codegen.implementation_broker
    implementation = await container.repos.implementations.by_id(ImplementationId(implementation_id))
    if implementation is not None:
        project_id = implementation.project_id
    else:
        project_id = await broker_instance.get_project_id(implementation_id)

    if project_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Implementación no encontrada")
    await _require_project_owner(container, ProjectId(project_id), principal)

    # El broker devuelve un AsyncGenerator[OpenCodeEvent, None]
    # SseEventSourceResponse itera sobre él y lo expone como Server-Sent Events.
    async def event_publisher() -> AsyncGenerator[dict[str, Any]]:
        async for event in broker_instance.subscribe(implementation_id):
            event_type = getattr(event.event_type, "value", str(event.event_type))
            yield {
                "event": event_type,
                "data": json.dumps(
                    {
                        "event_type": event_type,
                        "session_id": event.session_id,
                        "data": event.data,
                        "timestamp": event.timestamp.isoformat(),
                    }
                ),
            }

    return EventSourceResponse(event_publisher())


@router.get(
    "/{implementation_id}/files/content",
    response_model=ImplementationFileContentResponse,
    summary="Leer contenido de un archivo generado",
    description="Devuelve el contenido de un archivo del workspace de la implementación, "
    "validando que la ruta permanezca dentro del workspace.",
)
async def get_implementation_file_content(
    implementation_id: str,
    path: Annotated[str, Query(min_length=1, description="Ruta relativa del archivo dentro del workspace")],
    principal: Annotated[Principal, Depends(get_principal)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> ImplementationFileContentResponse:
    impl = await _owned_implementation(container, ImplementationId(implementation_id), principal)

    workspace = await container.repos.workspaces.by_project_id(impl.project_id)
    if workspace is None or not workspace.workspace_dir:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El workspace de la implementación no está disponible",
        )

    try:
        file_path = ensure_safe_path(path, workspace.workspace_dir)
    except UnsafePathError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"La ruta '{path}' no es válida: debe permanecer dentro del workspace",
        ) from None

    if not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró el archivo '{path}' en el workspace",
        )

    return ImplementationFileContentResponse(path=path, content=file_path.read_text(encoding="utf-8"))


@router.post(
    "/{implementation_id}/validate",
    response_model=ValidateWorkspaceResponse,
    summary="Validar workspace de implementación",
    description="Ejecuta el pipeline de validación determinística (tsc, eslint, vitest, next build) "
    "sobre el workspace de la implementación, sin regenerar código.",
)
async def validate_implementation_workspace(
    implementation_id: str,
    principal: Annotated[Principal, Depends(get_principal)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> ValidateWorkspaceResponse:
    impl = await _owned_implementation(container, ImplementationId(implementation_id), principal)

    try:
        output = await container.codegen.validate_workspace.execute(ValidateWorkspaceInput(project_id=impl.project_id))
    except WorkspaceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from None

    return ValidateWorkspaceResponse(
        all_passed=output.all_passed,
        steps=[
            ValidationStepResultResponse(
                step=str(step_result.step),
                success=step_result.success,
                duration_ms=step_result.duration_ms,
                exit_code=step_result.exit_code,
                error_messages=list(step_result.error_messages),
            )
            for step_result in output.steps
        ],
        failed_step=str(output.failed_step) if output.failed_step is not None else None,
        error_summary=list(output.error_summary),
        total_duration_ms=output.total_duration_ms,
    )
