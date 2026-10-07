from __future__ import annotations

from dataclasses import dataclass

from kosmo.contracts.ai.chat import ChatRepository, ChatSession, ChatSessionSummary
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.errors import ChatSessionNotFoundError
from kosmo.contracts.sdd.ids import ChatSessionId, ProjectId
from kosmo.domain.sdd.id_generator import IdGenerator


@dataclass(frozen=True)
class CreateChatSessionInput:
    project_id: ProjectId
    phase: SpecPhase
    context_id: str | None = None


class CreateChatSessionUseCase:
    """Crea un hilo de conversacion nuevo con contexto limpio."""

    def __init__(self, chat_repo: ChatRepository) -> None:
        self._chat_repo = chat_repo

    async def execute(self, input_data: CreateChatSessionInput) -> ChatSession:
        session = ChatSession(
            id=ChatSessionId(IdGenerator.generate("chat_session")),
            project_id=input_data.project_id,
            phase=input_data.phase,
            context_id=input_data.context_id,
        )
        return await self._chat_repo.create_session(session)


@dataclass(frozen=True)
class ListChatSessionsInput:
    project_id: ProjectId
    phase: SpecPhase
    context_id: str | None = None


class ListChatSessionsUseCase:
    """Lista los hilos de una fase, del mas reciente al mas antiguo."""

    def __init__(self, chat_repo: ChatRepository) -> None:
        self._chat_repo = chat_repo

    async def execute(self, input_data: ListChatSessionsInput) -> list[ChatSessionSummary]:
        return await self._chat_repo.list_sessions(
            project_id=input_data.project_id,
            phase=input_data.phase,
            context_id=input_data.context_id,
        )


@dataclass(frozen=True)
class DeleteChatSessionInput:
    session_id: ChatSessionId
    project_id: ProjectId


class DeleteChatSessionUseCase:
    """Elimina un hilo de conversacion junto con sus mensajes."""

    def __init__(self, chat_repo: ChatRepository) -> None:
        self._chat_repo = chat_repo

    async def execute(self, input_data: DeleteChatSessionInput) -> None:
        deleted = await self._chat_repo.delete_session(input_data.session_id, input_data.project_id)
        if not deleted:
            raise ChatSessionNotFoundError(
                session_id=str(input_data.session_id),
                project_id=str(input_data.project_id),
            )
