from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status

from kosmo.application.chat.process_chat_modification import (
    ProcessChatModificationInput,
    ProcessChatModificationUseCase,
)
from kosmo.application.discovery.revert_document import revert_to_version
from kosmo.contracts.auth import Principal
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.errors import (
    DocumentNotFoundError,
    FeatureNotFoundError,
    LLMInvocationError,
)
from kosmo.contracts.sdd.ids import ProjectId
from kosmo.contracts.sdd.repositories import DocumentRepository
from kosmo.infrastructure.api.dependencies.auth import (
    get_principal,
    require_project_owner,
    verify_feature_owner,
)
from kosmo.infrastructure.api.dependencies.container import get_container
from kosmo.infrastructure.api.dependencies.rate_limit import ProjectGenerationRateLimiter
from kosmo.infrastructure.api.schemas import (
    DocumentModifyRequestView,
    DocumentModifyResponseView,
    HttpErrorResponse,
)

router = APIRouter(
    prefix="/api/v1/documents",
    tags=["documents"],
    responses={
        401: {"model": HttpErrorResponse, "description": "Token ausente, inválido o expirado"},
        404: {"model": HttpErrorResponse, "description": "Documento no encontrado"},
    },
)

_generation_rate_limiter = ProjectGenerationRateLimiter()

_PHASE_MAP: dict[str, SpecPhase] = {
    "discovery": SpecPhase.DESCUBRIMIENTO,
    "features": SpecPhase.CARACTERISTICAS,
    "requirements": SpecPhase.REQUISITOS,
    "model": SpecPhase.MODELO,
}


async def _verify_document_ownership(
    request: Request,
    document_type: str,
    document_id: str,
    principal: Principal,
) -> None:
    """Verifica que el documento pertenezca a un proyecto del usuario autenticado (BOLA guard)."""
    app = getattr(request, "app", None)
    state = getattr(app, "state", None) if app is not None else None
    container = getattr(state, "container", None) if state is not None else None
    if container is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno de configuración: contenedor de dependencias no disponible.",
        )
    if document_type == "discovery":
        await require_project_owner(container, document_id, principal)
    elif document_type in ("features", "requirements", "model"):
        await verify_feature_owner(document_id, principal, request)
    else:
        await require_project_owner(container, document_id, principal)


def _chat_modification_uc(request: Request) -> ProcessChatModificationUseCase:
    return get_container(request).pipeline.process_chat_modification


@router.post(
    "/modify-direct",
    summary="Modificar documento directamente sin fase de plan",
    description=(
        "Recibe una instrucción textual y modifica directamente el documento indicado "
        "sin pasar por la fase de planificación del chat. La IA interpreta la intención, "
        "identifica la sección afectada, aplica el cambio y retorna el documento actualizado "
        "con la sección resaltada."
    ),
    response_model=DocumentModifyResponseView,
    status_code=status.HTTP_200_OK,
)
async def modify_document_direct(
    request: Request,
    _principal: Annotated[Principal, Depends(get_principal)],
    body: Annotated[DocumentModifyRequestView, Body(...)],
    uc: Annotated[ProcessChatModificationUseCase, Depends(_chat_modification_uc)],
) -> DocumentModifyResponseView:
    await _verify_document_ownership(request, body.document_type, body.document_id, _principal)

    state = getattr(request, "state", None)
    raw_pid = getattr(state, "project_id", None)
    target_project_id = raw_pid if isinstance(raw_pid, str) and raw_pid else body.document_id
    await _generation_rate_limiter(request, project_id=str(target_project_id))

    phase = _PHASE_MAP.get(body.document_type)
    if phase is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo de documento desconocido: '{body.document_type}'.",
        )

    try:
        output = await uc.execute(
            ProcessChatModificationInput(
                text=body.instruction,
                document_id=body.document_id,
                document_type=phase,
            )
        )
    except (DocumentNotFoundError, FeatureNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.problem.detail,
        ) from exc
    except LLMInvocationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=exc.problem.detail,
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if not output.success:
        detail_msg = output.clarification_message or "Instrucción ambigua o inválida — se requiere más detalle."
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail_msg,
        )

    section_info = f" Sección '{output.modified_section}' modificada." if output.modified_section else ""
    return DocumentModifyResponseView(
        document_id=body.document_id,
        content=output.modified_document or "",
        highlighted_section=output.modified_section,
        message=f"Documento actualizado.{section_info}",
    )


def _document_repo(request: Request) -> DocumentRepository:
    return get_container(request).discovery.document_repo


@router.post(
    "/revert",
    summary="Revertir a una versión anterior del documento",
    description="Restaura una versión previa del documento de descubrimiento.",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Versión no encontrada."},
    },
)
async def revert_document(
    project_id: Annotated[str, Body(..., embed=True)],
    version_id: Annotated[str, Body(..., embed=True)],
    _principal: Annotated[Principal, Depends(get_principal)],
    doc_repo: Annotated[DocumentRepository, Depends(_document_repo)],
    request: Request,
) -> dict[str, str]:
    container = get_container(request)
    await require_project_owner(container, project_id, _principal)
    outbox = container.pipeline.outbox
    result = await revert_to_version(
        document_repo=doc_repo,
        project_id=ProjectId(project_id),
        version_id=version_id,
        outbox=outbox,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Versión no encontrada",
        )
    return {"status": "ok", "version_id": version_id}
