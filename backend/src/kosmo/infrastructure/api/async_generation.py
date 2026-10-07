from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import AsyncGenerator, AsyncIterator
from typing import TYPE_CHECKING

import structlog
from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse

from kosmo.application.chat.validate_phase_context import (
    ValidatePhaseContextInput,
    ValidatePhaseContextOutput,
    ValidatePhaseContextUseCase,
)
from kosmo.contracts.ai.chat import ModificacionChat
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.ids import ChatSessionId, ProjectId
from kosmo.infrastructure.telemetry import ACTIVE_SSE_CONNECTIONS, get_current_trace_id

if TYPE_CHECKING:
    from kosmo.application.chat.process_chat_message import (
        ProcessChatMessageOutput,
        ProcessChatMessageUseCase,
    )

_log = structlog.get_logger(__name__)

_HEARTBEAT_INTERVAL: float = 15.0
_HEARTBEAT_COMMENT: str = ": ping\n\n"


async def with_heartbeat(
    source: AsyncIterator[str],
    interval: float = _HEARTBEAT_INTERVAL,
    heartbeat: str = _HEARTBEAT_COMMENT,
    max_duration_seconds: float = 1800.0,
) -> AsyncGenerator[str]:
    """Envuelve un iterador asíncrono emitiendo comentarios ping periódicos si no hay actividad.

    Ejecuta el consumo de la fuente en una única tarea dedicada mediante una cola,
    asegurando que context managers vinculados a tareas (como AnyIO cancel scopes y
    conexiones HTTP/LLM) se inicien y finalicen dentro de la misma tarea asyncio.
    """
    sentinel = object()
    queue: asyncio.Queue[tuple[object, Exception | None]] = asyncio.Queue()

    async def producer() -> None:
        try:
            async for item in source:
                await queue.put((item, None))
        except Exception as exc:
            await queue.put((sentinel, exc))
        else:
            await queue.put((sentinel, None))

    ACTIVE_SSE_CONNECTIONS.inc()
    producer_task = asyncio.create_task(producer(), name="sse_producer_task")
    start_time = time.monotonic()
    try:
        while True:
            if time.monotonic() - start_time > max_duration_seconds:
                _log.warning("sse.max_duration_exceeded", max_duration_seconds=max_duration_seconds)
                break
            try:
                item, exc = await asyncio.wait_for(queue.get(), timeout=interval)
            except TimeoutError:
                if producer_task.done() and queue.empty():
                    break
                yield heartbeat
                continue
            if exc is not None:
                raise exc
            if item is sentinel:
                break
            assert isinstance(item, str)
            yield item
    finally:
        ACTIVE_SSE_CONNECTIONS.dec()
        if not producer_task.done():
            producer_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await producer_task


async def validate_chat_content(
    validate_uc: ValidatePhaseContextUseCase,
    content: str,
    document_type: SpecPhase,
) -> ValidatePhaseContextOutput:
    """Valida la fase del mensaje y registra la metrica de la etapa."""
    validate_start = time.monotonic()
    validation = await validate_uc.execute(ValidatePhaseContextInput(content=content, current_phase=document_type))
    _log.info(
        "chat.stage_times",
        phase=document_type.value,
        validate_ms=int((time.monotonic() - validate_start) * 1000),
    )
    return validation


def _modification_dict(modification: ModificacionChat | None) -> dict[str, object] | None:
    if modification is None:
        return None
    return {
        "applied": modification.applied,
        "modified_section": modification.modified_section,
        "change_description": modification.change_description,
        "modified_document": modification.modified_document,
        "before": modification.before,
        "after": modification.after,
        "undo_version_id": None,
        "clarification_message": modification.clarification_message,
    }


def _message_dict(output: ProcessChatMessageOutput) -> dict[str, object]:
    msg = output.message
    return {
        "type": "message",
        "id": str(msg.id),
        "role": "assistant",
        "content": msg.content,
        "suggestions": [
            {
                "id": sc.id,
                "section": sc.section,
                "description": sc.description,
                "diff_before": sc.diff.before,
                "diff_after": sc.diff.after,
                "rationale": sc.rationale,
                "applied": sc.applied,
                "not_applied_reason": sc.not_applied_reason,
            }
            for sc in msg.suggested_changes
        ],
        "modification": _modification_dict(msg.modification),
        "consistency": None,
        "timestamp": msg.timestamp.isoformat(),
    }


async def sse_chat_response(
    content: str,
    document_type: SpecPhase,
    pid: ProjectId,
    context_id: str | None,
    context: object,
    chat_uc: ProcessChatMessageUseCase,
    validate_uc: ValidatePhaseContextUseCase,
    session_id: ChatSessionId | None = None,
) -> StreamingResponse:
    """Streaming real del chat: tokens conforme se generan y evento final con las cards."""
    from kosmo.application.chat.process_chat_message import (
        ChatStreamChunk,
        ProcessChatMessageInput,
    )

    validation = await validate_chat_content(validate_uc, content, document_type)
    if not validation.is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=validation.redirect_message or "Mensaje fuera de fase",
        )

    input_data = ProcessChatMessageInput(
        content=content,
        project_id=pid,
        phase=document_type,
        context=context,
        context_id=context_id,
        session_id=session_id,
    )
    trace_id = get_current_trace_id()

    async def event_stream() -> AsyncGenerator[str]:
        yield "data: " + json.dumps({"type": "start", "trace_id": trace_id}, ensure_ascii=False) + "\n\n"
        try:
            async for item in chat_uc.execute_stream(input_data):
                if isinstance(item, ChatStreamChunk):
                    yield (
                        "data: "
                        + json.dumps(
                            {"type": "chunk", "content": item.content},
                            ensure_ascii=False,
                        )
                        + "\n\n"
                    )
                else:
                    yield "data: " + json.dumps(_message_dict(item), ensure_ascii=False) + "\n\n"
        except Exception as exc:
            # Frontera de transporte: el stream ya empezó, así que el error se
            # comunica como evento SSE para que el cliente muestre feedback.
            _log.exception("chat.stream_error", phase=document_type.value, trace_id=trace_id)
            from kosmo.contracts.sdd.errors import AIProviderAuthError
            from kosmo.infrastructure.llm.dynamic_llm_client import is_ai_auth_error

            if isinstance(exc, AIProviderAuthError) or is_ai_auth_error(exc):
                msg = (
                    exc.problem.detail
                    if isinstance(exc, AIProviderAuthError)
                    else (
                        "Tu clave de API de IA no es válida o ha expirado. "
                        "Por favor, revísala en Perfil > Configuración de IA."
                    )
                )
                yield (
                    "data: "
                    + json.dumps(
                        {"type": "error", "code": "ai_auth_error", "message": msg, "trace_id": trace_id},
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )
            else:
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type": "error",
                            "message": "Error interno al procesar el mensaje. Reintenta más tarde.",
                            "trace_id": trace_id,
                        },
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )

    return StreamingResponse(
        with_heartbeat(event_stream()),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
            "X-Trace-Id": trace_id,
        },
    )


async def sse_consistency_response(
    generator: AsyncGenerator[str],
) -> StreamingResponse:
    trace_id = get_current_trace_id()

    async def event_stream() -> AsyncGenerator[str]:
        yield "data: " + json.dumps({"type": "start", "trace_id": trace_id}, ensure_ascii=False) + "\n\n"
        async for chunk in generator:
            yield chunk

    return StreamingResponse(
        with_heartbeat(event_stream()),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
            "X-Trace-Id": trace_id,
        },
    )
