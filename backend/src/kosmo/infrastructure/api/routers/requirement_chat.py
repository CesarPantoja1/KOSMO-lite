from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from kosmo.application.chat.process_chat_message import (
    ProcessChatMessageInput,
    ProcessChatMessageUseCase,
)
from kosmo.application.chat.validate_phase_context import (
    ValidatePhaseContextUseCase,
)
from kosmo.application.pipeline.context_builder import ContextBuilder
from kosmo.application.requirements import (
    GetRequirementChatHistoryInput,
    GetRequirementChatHistoryUseCase,
)
from kosmo.contracts.auth import Principal
from kosmo.contracts.pipeline.phase_errors import PhaseTransitionError
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.errors import (
    DocumentNotFoundError,
    FeatureNotFoundError,
    LLMInvocationError,
    ProjectNotFoundError,
)
from kosmo.contracts.sdd.ids import ChatSessionId, FeatureId
from kosmo.infrastructure.api.dependencies.auth import get_principal, verify_feature_owner
from kosmo.infrastructure.api.dependencies.container import get_container
from kosmo.infrastructure.api.dependencies.rate_limit import ProjectGenerationRateLimiter
from kosmo.infrastructure.api.schemas import (
    ChatHistoryResponse,
    ChatResponse,
    SendChatRequest,
)

router = APIRouter(
    prefix="/api/v1/features/{feature_id}/requirements/chat",
    tags=["requirements"],
    dependencies=[Depends(verify_feature_owner)],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Token inválido o expirado."},
        status.HTTP_404_NOT_FOUND: {"description": "Característica o requisito no encontrado."},
    },
)

_generation_rate_limiter = ProjectGenerationRateLimiter()


def _chat_uc(request: Request) -> ProcessChatMessageUseCase:
    return get_container(request).pipeline.process_chat_message


def _context_builder(request: Request) -> ContextBuilder:
    return get_container(request).pipeline.context_builder


def _get_requirement_chat_history(request: Request) -> GetRequirementChatHistoryUseCase:
    return get_container(request).requirements.get_requirement_chat_history


def _validate_phase_context(request: Request) -> ValidatePhaseContextUseCase:
    return get_container(request).pipeline.validate_phase_context


@router.post(
    "",
    summary="Enviar mensaje al chat de Requisitos (aplicación instantánea)",
    description=(
        "Procesa el mensaje y aplica el cambio inmediatamente sobre el documento "
        "de requisitos, verificando la consistencia en el Modelo. "
        "Si el cambio pertenece a otra fase, devuelve una redirección."
    ),
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {"description": "Mensaje procesado, modificación aplicada o redirección."},
        status.HTTP_400_BAD_REQUEST: {"description": "Error de validación o tamaño de mensaje."},
        status.HTTP_401_UNAUTHORIZED: {"description": "Token inválido."},
        status.HTTP_404_NOT_FOUND: {"description": "Característica o requisito no encontrado."},
        status.HTTP_502_BAD_GATEWAY: {"description": "Error al invocar el LLM."},
    },
)
async def process_requirement_chat_message(
    feature_id: str,
    payload: Annotated[SendChatRequest, Body(...)],
    _principal: Annotated[Principal, Depends(get_principal)],
    chat_uc: Annotated[ProcessChatMessageUseCase, Depends(_chat_uc)],
    validate_uc: Annotated[ValidatePhaseContextUseCase, Depends(_validate_phase_context)],
    context_builder: Annotated[ContextBuilder, Depends(_context_builder)],
    _rate: Annotated[None, Depends(_generation_rate_limiter)] = None,
) -> ChatResponse:
    from kosmo.infrastructure.api.async_generation import validate_chat_content

    validation = await validate_chat_content(validate_uc, payload.content, SpecPhase.REQUISITOS)

    if not validation.is_valid:
        return ChatResponse.from_redirect(
            target_phase=validation.target_phase or "",
            redirect_message=validation.redirect_message or "Este cambio no pertenece a la fase de Requisitos.",
        )

    try:
        ctx = await context_builder.build_requirement_chat_context(FeatureId(feature_id))
        output = await chat_uc.execute(
            ProcessChatMessageInput(
                content=payload.content,
                project_id=ctx.feature.project_id,
                phase=SpecPhase.REQUISITOS,
                context=ctx,
                context_id=feature_id,
                session_id=ChatSessionId(payload.session_id) if payload.session_id else None,
                instance=f"/api/v1/features/{feature_id}/requirements/chat",
            )
        )
    except ValueError as exc:
        import structlog

        structlog.get_logger(__name__).error("requirement_chat.value_error", detail=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except (DocumentNotFoundError, FeatureNotFoundError, ProjectNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.problem.detail,
        ) from exc
    except PhaseTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.problem.detail,
        ) from exc
    except LLMInvocationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=exc.problem.detail,
        ) from exc

    return ChatResponse.from_message(output)


@router.get(
    "/history",
    summary="Obtener historial del chat de un requisito",
    description="Devuelve todos los mensajes del chat interactivo para un requisito específico.",
    response_model=ChatHistoryResponse,
    responses={
        status.HTTP_200_OK: {"description": "Historial obtenido exitosamente."},
        status.HTTP_401_UNAUTHORIZED: {"description": "Token inválido."},
        status.HTTP_404_NOT_FOUND: {"description": "Característica no encontrada."},
    },
)
async def get_requirement_chat_history(
    feature_id: str,
    _principal: Annotated[Principal, Depends(get_principal)],
    use_case: Annotated[GetRequirementChatHistoryUseCase, Depends(_get_requirement_chat_history)],
    before: str | None = None,
    session_id: str | None = None,
) -> ChatHistoryResponse:
    try:
        output = await use_case.execute(
            GetRequirementChatHistoryInput(
                feature_id=FeatureId(feature_id),
                before=before,
                session_id=ChatSessionId(session_id) if session_id else None,
            )
        )
    except FeatureNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.problem.detail,
        ) from exc

    if output.history is None:
        from kosmo.contracts.ai.chat import HistorialChat
        from kosmo.contracts.sdd.ids import ChatHistoryId, ProjectId
        from kosmo.domain.sdd.id_generator import IdGenerator

        empty_history = HistorialChat(
            id=ChatHistoryId(IdGenerator.generate("chat_history")),
            project_id=ProjectId(""),
            phase=SpecPhase.REQUISITOS,
            context_id=feature_id,
        )
        return ChatHistoryResponse.from_domain(empty_history)

    return ChatHistoryResponse.from_domain(output.history)


@router.post(
    "/stream",
    summary="Enviar mensaje al chat de Requisitos con streaming SSE",
    response_class=StreamingResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Error de validación."},
        status.HTTP_404_NOT_FOUND: {"description": "Característica o requisito no encontrado."},
    },
)
async def stream_requirement_chat_message(
    feature_id: str,
    payload: Annotated[SendChatRequest, Body(...)],
    _principal: Annotated[Principal, Depends(get_principal)],
    validate_uc: Annotated[ValidatePhaseContextUseCase, Depends(_validate_phase_context)],
    chat_uc: Annotated[ProcessChatMessageUseCase, Depends(_chat_uc)],
    context_builder: Annotated[ContextBuilder, Depends(_context_builder)],
    _rate: Annotated[None, Depends(_generation_rate_limiter)] = None,
) -> StreamingResponse:
    from kosmo.infrastructure.api.async_generation import sse_chat_response

    ctx = await context_builder.build_requirement_chat_context(FeatureId(feature_id))
    return await sse_chat_response(
        content=payload.content,
        document_type=SpecPhase.REQUISITOS,
        pid=ctx.feature.project_id,
        context_id=feature_id,
        context=ctx,
        chat_uc=chat_uc,
        validate_uc=validate_uc,
        session_id=ChatSessionId(payload.session_id) if payload.session_id else None,
    )
