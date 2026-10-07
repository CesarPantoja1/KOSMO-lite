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
from kosmo.application.discovery import (
    GenerateDiscoveryInput,
    GenerateDiscoveryUseCase,
    GetDiscoveryChatHistoryInput,
    GetDiscoveryChatHistoryUseCase,
    GetDiscoveryInput,
    GetDiscoveryUseCase,
    RefineDiscoveryInput,
    RefineDiscoveryUseCase,
    SaveDiscoveryInput,
    SaveDiscoveryUseCase,
)
from kosmo.application.pipeline.context_builder import ContextBuilder
from kosmo.contracts.auth import Principal
from kosmo.contracts.pipeline.phase_errors import PhaseTransitionError
from kosmo.contracts.sdd.document import RichTextDocument, SpecPhase
from kosmo.contracts.sdd.errors import (
    DocumentNotFoundError,
    LLMInvocationError,
    ProjectNotFoundError,
)
from kosmo.contracts.sdd.ids import ChatSessionId, ProjectId
from kosmo.infrastructure.api.dependencies.auth import get_principal, verify_project_owner
from kosmo.infrastructure.api.dependencies.container import get_container
from kosmo.infrastructure.api.dependencies.rate_limit import ProjectGenerationRateLimiter
from kosmo.infrastructure.api.schemas import (
    ChatHistoryResponse,
    ChatResponse,
    DiscoveryResponse,
    RefineDiscoveryRequest,
    SendChatRequest,
)

router = APIRouter(
    prefix="/api/v1/projects/{project_id}/discovery",
    tags=["discovery"],
    dependencies=[Depends(verify_project_owner)],
)

_generation_rate_limiter = ProjectGenerationRateLimiter()


def _generate_discovery(request: Request) -> GenerateDiscoveryUseCase:
    return get_container(request).discovery.generate_discovery


def _get_discovery(request: Request) -> GetDiscoveryUseCase:
    return get_container(request).discovery.get_discovery


def _save_discovery(request: Request) -> SaveDiscoveryUseCase:
    return get_container(request).discovery.save_discovery


def _refine_discovery(request: Request) -> RefineDiscoveryUseCase:
    return get_container(request).discovery.refine_discovery


def _chat_uc(request: Request) -> ProcessChatMessageUseCase:
    return get_container(request).pipeline.process_chat_message


def _context_builder(request: Request) -> ContextBuilder:
    return get_container(request).pipeline.context_builder


def _validate_phase_context(request: Request) -> ValidatePhaseContextUseCase:
    return get_container(request).pipeline.validate_phase_context


def _get_discovery_chat_history(request: Request) -> GetDiscoveryChatHistoryUseCase:
    return get_container(request).discovery.get_discovery_chat_history


@router.post(
    "",
    summary="Generar documento de descubrimiento con IA",
    description=(
        "Genera un documento de visión de producto estructurado en 8 secciones, utilizando inteligencia artificial."
    ),
    response_model=DiscoveryResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {"description": "Documento de descubrimiento generado exitosamente."},
        status.HTTP_401_UNAUTHORIZED: {"description": "Token de acceso inválido o ausente."},
    },
)
async def generate_discovery(
    project_id: str,
    _principal: Annotated[Principal, Depends(get_principal)],
    _rate: Annotated[None, Depends(_generation_rate_limiter)],
    use_case: Annotated[GenerateDiscoveryUseCase, Depends(_generate_discovery)],
) -> DiscoveryResponse:
    output = await use_case.execute(GenerateDiscoveryInput(project_id=ProjectId(project_id)))
    return DiscoveryResponse(
        id=str(output.project_id),
        project_id=str(output.project_id),
        content=_document_to_markdown(output.document),
    )


@router.get(
    "",
    summary="Obtener documento de descubrimiento",
    description=(
        "Devuelve el documento de descubrimiento almacenado de un proyecto. "
        "Requiere autenticación mediante Bearer token."
    ),
    response_model=DiscoveryResponse,
    responses={
        status.HTTP_200_OK: {
            "description": "Documento de descubrimiento del proyecto.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Token de acceso inválido o ausente.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Documento de descubrimiento no encontrado.",
        },
    },
)
async def get_discovery(
    project_id: str,
    _principal: Annotated[Principal, Depends(get_principal)],
    use_case: Annotated[GetDiscoveryUseCase, Depends(_get_discovery)],
) -> DiscoveryResponse:
    try:
        output = await use_case.execute(GetDiscoveryInput(project_id=ProjectId(project_id)))
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.problem.detail,
        ) from exc
    return DiscoveryResponse(
        id=str(output.project_id),
        project_id=str(output.project_id),
        content=_document_to_markdown(output.document),
    )


@router.put(
    "",
    summary="Guardar documento de descubrimiento",
    description=(
        "Persiste manualmente un documento de descubrimiento para un proyecto. "
        "Permite guardar o reemplazar el documento sin invocar al agente de IA. "
        "Requiere autenticación mediante Bearer token."
    ),
    response_model=DiscoveryResponse,
    responses={
        status.HTTP_200_OK: {
            "description": "Documento de descubrimiento guardado exitosamente.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Token de acceso inválido o ausente.",
        },
    },
)
async def save_discovery(
    project_id: str,
    payload: Annotated[dict[str, str], Body(...)],
    _principal: Annotated[Principal, Depends(get_principal)],
    use_case: Annotated[SaveDiscoveryUseCase, Depends(_save_discovery)],
) -> DiscoveryResponse:
    document = _markdown_to_document(payload.get("content", ""))
    output = await use_case.execute(
        SaveDiscoveryInput(
            project_id=ProjectId(project_id),
            document=document,
        )
    )
    return DiscoveryResponse(
        id=str(output.project_id),
        project_id=str(output.project_id),
        content=payload.get("content", ""),
    )


@router.post(
    "/refine",
    summary="Refinar documento de descubrimiento con IA",
    description=(
        "Refina el documento de descubrimiento de un proyecto aplicando las "
        "instrucciones proporcionadas por el usuario mediante inteligencia artificial. "
        "El documento actual se conserva intacto si la IA falla. "
        "Las instrucciones no pueden exceder los 500 caracteres. "
        "Requiere autenticación mediante Bearer token."
    ),
    response_model=DiscoveryResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "Documento de descubrimiento refinado exitosamente.",
        },
        status.HTTP_400_BAD_REQUEST: {
            "description": "Las instrucciones exceden los 500 caracteres.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Token de acceso inválido o ausente.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Proyecto no encontrado o sin documento de descubrimiento previo.",
        },
        status.HTTP_502_BAD_GATEWAY: {
            "description": "Error al invocar el servicio de IA.",
        },
    },
)
async def refine_discovery(
    project_id: str,
    payload: Annotated[RefineDiscoveryRequest, Body(...)],
    _principal: Annotated[Principal, Depends(get_principal)],
    use_case: Annotated[RefineDiscoveryUseCase, Depends(_refine_discovery)],
    _rate: Annotated[None, Depends(_generation_rate_limiter)] = None,
) -> DiscoveryResponse:
    try:
        output = await use_case.execute(
            RefineDiscoveryInput(
                project_id=ProjectId(project_id),
                instructions=payload.instructions,
            )
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.problem.detail,
        ) from exc
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.problem.detail,
        ) from exc
    except LLMInvocationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=exc.problem.detail,
        ) from exc
    return DiscoveryResponse(
        id=str(output.project_id),
        project_id=str(output.project_id),
        content=_document_to_markdown(output.document),
    )


def _document_to_markdown(doc: RichTextDocument) -> str:
    from kosmo.domain.sdd.document_converters import document_to_markdown

    return document_to_markdown(doc)


def _markdown_to_document(content: str) -> RichTextDocument:
    from kosmo.domain.sdd.document_converters import markdown_to_document

    return markdown_to_document(content)


@router.post(
    "/chat",
    summary="Enviar mensaje al chat de Descubrimiento (aplicación instantánea)",
    description=(
        "Procesa el mensaje y aplica el cambio inmediatamente sobre el documento "
        "cuando corresponde, verificando la consistencia en las fases a la derecha. "
        "Si el mensaje corresponde a otra fase, devuelve una redirección."
    ),
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {"description": "Mensaje procesado, modificación aplicada o redirección."},
        status.HTTP_400_BAD_REQUEST: {"description": "Error de validación o tamaño de mensaje."},
        status.HTTP_401_UNAUTHORIZED: {"description": "Token inválido."},
        status.HTTP_404_NOT_FOUND: {"description": "Proyecto no encontrado."},
        status.HTTP_502_BAD_GATEWAY: {"description": "Error al invocar el LLM."},
    },
)
async def process_chat_message(
    project_id: str,
    payload: Annotated[SendChatRequest, Body(...)],
    _principal: Annotated[Principal, Depends(get_principal)],
    chat_uc: Annotated[ProcessChatMessageUseCase, Depends(_chat_uc)],
    validate_uc: Annotated[ValidatePhaseContextUseCase, Depends(_validate_phase_context)],
    context_builder: Annotated[ContextBuilder, Depends(_context_builder)],
    _rate: Annotated[None, Depends(_generation_rate_limiter)] = None,
) -> ChatResponse:
    from kosmo.infrastructure.api.async_generation import validate_chat_content

    validation = await validate_chat_content(validate_uc, payload.content, SpecPhase.DESCUBRIMIENTO)

    if not validation.is_valid:
        return ChatResponse.from_redirect(
            target_phase=validation.target_phase or "",
            redirect_message=validation.redirect_message or "Este cambio no pertenece a la fase de Descubrimiento.",
        )

    try:
        ctx = await context_builder.build_discovery_chat_context(ProjectId(project_id))
        output = await chat_uc.execute(
            ProcessChatMessageInput(
                content=payload.content,
                project_id=ProjectId(project_id),
                phase=SpecPhase.DESCUBRIMIENTO,
                context=ctx,
                context_id=None,
                session_id=ChatSessionId(payload.session_id) if payload.session_id else None,
                instance=f"/api/v1/projects/{project_id}/discovery/chat",
            )
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except (DocumentNotFoundError, ProjectNotFoundError) as exc:
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
    "/chat",
    summary="Obtener historial de chat de Descubrimiento",
    description="Devuelve todos los mensajes del chat interactivo para la fase de Descubrimiento.",
    response_model=ChatHistoryResponse,
    responses={
        status.HTTP_200_OK: {"description": "Historial obtenido exitosamente."},
        status.HTTP_401_UNAUTHORIZED: {"description": "Token inválido."},
        status.HTTP_404_NOT_FOUND: {"description": "Proyecto no encontrado."},
    },
)
async def get_chat_history(
    project_id: str,
    _principal: Annotated[Principal, Depends(get_principal)],
    use_case: Annotated[GetDiscoveryChatHistoryUseCase, Depends(_get_discovery_chat_history)],
    before: str | None = None,
    session_id: str | None = None,
) -> ChatHistoryResponse:
    try:
        output = await use_case.execute(
            GetDiscoveryChatHistoryInput(
                project_id=ProjectId(project_id),
                before=before,
                session_id=ChatSessionId(session_id) if session_id else None,
            )
        )
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.problem.detail,
        ) from exc

    if output.history is None:
        from kosmo.contracts.ai.chat import HistorialChat
        from kosmo.contracts.sdd.document import SpecPhase
        from kosmo.contracts.sdd.ids import ChatHistoryId
        from kosmo.domain.sdd.id_generator import IdGenerator

        empty_history = HistorialChat(
            id=ChatHistoryId(IdGenerator.generate("chat_history")),
            project_id=ProjectId(project_id),
            phase=SpecPhase.DESCUBRIMIENTO,
        )
        return ChatHistoryResponse.from_domain(empty_history)

    return ChatHistoryResponse.from_domain(output.history)


@router.post(
    "/chat/stream",
    summary="Enviar mensaje al chat de Descubrimiento con streaming SSE",
    response_class=StreamingResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Error de validación."},
        status.HTTP_404_NOT_FOUND: {"description": "Proyecto no encontrado."},
    },
)
async def stream_chat_message(
    project_id: str,
    payload: Annotated[SendChatRequest, Body(...)],
    _principal: Annotated[Principal, Depends(get_principal)],
    validate_uc: Annotated[ValidatePhaseContextUseCase, Depends(_validate_phase_context)],
    chat_uc: Annotated[ProcessChatMessageUseCase, Depends(_chat_uc)],
    context_builder: Annotated[ContextBuilder, Depends(_context_builder)],
    _rate: Annotated[None, Depends(_generation_rate_limiter)] = None,
) -> StreamingResponse:
    from kosmo.infrastructure.api.async_generation import sse_chat_response

    ctx = await context_builder.build_discovery_chat_context(ProjectId(project_id))
    return await sse_chat_response(
        content=payload.content,
        document_type=SpecPhase.DESCUBRIMIENTO,
        pid=ProjectId(project_id),
        context_id=None,
        context=ctx,
        chat_uc=chat_uc,
        validate_uc=validate_uc,
        session_id=ChatSessionId(payload.session_id) if payload.session_id else None,
    )
