from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from kosmo.application.chat.chat_sessions import (
    CreateChatSessionInput,
    CreateChatSessionUseCase,
    DeleteChatSessionInput,
    DeleteChatSessionUseCase,
    ListChatSessionsInput,
    ListChatSessionsUseCase,
)
from kosmo.contracts.auth import Principal
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.ids import ChatSessionId, ProjectId
from kosmo.infrastructure.api.dependencies.auth import get_principal, verify_project_owner
from kosmo.infrastructure.api.dependencies.container import get_container
from kosmo.infrastructure.api.schemas import HttpErrorResponse

router = APIRouter(
    prefix="/api/v1/projects/{project_id}/chat-sessions",
    tags=["chat-sessions"],
    dependencies=[Depends(verify_project_owner)],
    responses={
        401: {"model": HttpErrorResponse, "description": "Token ausente, inválido o expirado"},
        404: {"model": HttpErrorResponse, "description": "Proyecto no encontrado"},
    },
)

_PHASE_MAP: dict[str, SpecPhase] = {
    "discovery": SpecPhase.DESCUBRIMIENTO,
    "features": SpecPhase.CARACTERISTICAS,
    "requirements": SpecPhase.REQUISITOS,
    "model": SpecPhase.MODELO,
}


def _resolve_phase(phase_name: str) -> SpecPhase:
    phase = _PHASE_MAP.get(phase_name)
    if phase is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Fase desconocida: '{phase_name}'.",
        )
    return phase


def _create_uc(request: Request) -> CreateChatSessionUseCase:
    return get_container(request).pipeline.create_chat_session


def _list_uc(request: Request) -> ListChatSessionsUseCase:
    return get_container(request).pipeline.list_chat_sessions


def _delete_uc(request: Request) -> DeleteChatSessionUseCase:
    return get_container(request).pipeline.delete_chat_session


def _session_dict(session: Any) -> dict[str, object]:
    return {
        "id": str(session.id),
        "phase": session.phase.value,
        "context_id": session.context_id,
        "created_at": session.created_at.isoformat(),
        "message_count": getattr(session, "message_count", 0),
        "last_message_at": (session.last_message_at.isoformat() if getattr(session, "last_message_at", None) else None),
        "title": getattr(session, "title", "") or "",
    }


class CreateChatSessionRequestView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phase: str = Field(description="Fase del chat (discovery, features, requirements, model)")
    context_id: str | None = Field(
        default=None,
        description="Contexto de la fase (id de característica para features/requirements; null para discovery)",
    )


@router.get(
    "",
    summary="Listar sesiones de chat de una fase",
    description=(
        "Devuelve los hilos de conversación persistidos de una fase, del más reciente al más antiguo, "
        "con el conteo de mensajes y la fecha del último. Útil para el selector de conversaciones "
        "y la rehidratación del historial al recargar."
    ),
    status_code=status.HTTP_200_OK,
)
async def list_chat_sessions(
    project_id: str,
    _principal: Annotated[Principal, Depends(get_principal)],
    uc: Annotated[ListChatSessionsUseCase, Depends(_list_uc)],
    phase: Annotated[str, Query(description="Fase a listar")],
    context_id: Annotated[str | None, Query(description="Contexto opcional (id de característica)")] = None,
) -> dict[str, Any]:
    sessions = await uc.execute(
        ListChatSessionsInput(
            project_id=ProjectId(project_id),
            phase=_resolve_phase(phase),
            context_id=context_id,
        )
    )
    return {"sessions": [_session_dict(s) for s in sessions]}


@router.post(
    "",
    summary="Crear una sesión de chat nueva con contexto limpio",
    description=(
        "Crea un hilo nuevo para la fase indicada. Las sesiones anteriores se conservan "
        "y pueden listarse y consultarse por su id."
    ),
    status_code=status.HTTP_201_CREATED,
)
async def create_chat_session(
    project_id: str,
    _principal: Annotated[Principal, Depends(get_principal)],
    body: Annotated[CreateChatSessionRequestView, Body(...)],
    uc: Annotated[CreateChatSessionUseCase, Depends(_create_uc)],
) -> dict[str, Any]:
    session = await uc.execute(
        CreateChatSessionInput(
            project_id=ProjectId(project_id),
            phase=_resolve_phase(body.phase),
            context_id=body.context_id,
        )
    )
    return _session_dict(session) | {"session_id": str(session.id)}


@router.delete(
    "/{session_id}",
    summary="Eliminar una sesión de chat",
    description="Elimina el hilo de conversación y todos sus mensajes.",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_chat_session(
    project_id: str,
    session_id: str,
    _principal: Annotated[Principal, Depends(get_principal)],
    uc: Annotated[DeleteChatSessionUseCase, Depends(_delete_uc)],
) -> Response:
    await uc.execute(
        DeleteChatSessionInput(
            session_id=ChatSessionId(session_id),
            project_id=ProjectId(project_id),
        )
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
