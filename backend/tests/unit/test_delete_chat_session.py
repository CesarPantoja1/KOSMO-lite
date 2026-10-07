from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from kosmo.application.chat.chat_sessions import (
    CreateChatSessionInput,
    CreateChatSessionUseCase,
    DeleteChatSessionInput,
    DeleteChatSessionUseCase,
)
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.errors import ChatSessionNotFoundError
from kosmo.contracts.sdd.ids import ChatSessionId, ProjectId
from tests.unit.fakes import InMemoryChatRepository


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_chat_session_delegates_with_correct_id_and_project() -> None:
    # Arrange
    chat_repo = AsyncMock()
    chat_repo.delete_session = AsyncMock(return_value=True)
    use_case = DeleteChatSessionUseCase(chat_repo=chat_repo)

    # Act
    await use_case.execute(
        DeleteChatSessionInput(
            session_id=ChatSessionId("cht_01"),
            project_id=ProjectId("prj_01"),
        )
    )

    # Assert
    chat_repo.delete_session.assert_awaited_once_with(
        ChatSessionId("cht_01"),
        ProjectId("prj_01"),
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_chat_session_raises_not_found_when_repo_returns_false() -> None:
    # Arrange
    chat_repo = AsyncMock()
    chat_repo.delete_session = AsyncMock(return_value=False)
    use_case = DeleteChatSessionUseCase(chat_repo=chat_repo)

    # Act & Assert
    with pytest.raises(ChatSessionNotFoundError) as exc_info:
        await use_case.execute(
            DeleteChatSessionInput(
                session_id=ChatSessionId("cht_missing"),
                project_id=ProjectId("prj_01"),
            )
        )
    assert exc_info.value.problem.status == 404
    assert "cht_missing" in exc_info.value.problem.detail


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_chat_session_propagates_repo_errors() -> None:
    # Arrange
    chat_repo = AsyncMock()
    chat_repo.delete_session = AsyncMock(side_effect=RuntimeError("db down"))
    use_case = DeleteChatSessionUseCase(chat_repo=chat_repo)

    # Act & Assert
    with pytest.raises(RuntimeError, match="db down"):
        await use_case.execute(
            DeleteChatSessionInput(
                session_id=ChatSessionId("cht_01"),
                project_id=ProjectId("prj_01"),
            )
        )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_chat_session_prevents_idor_cross_project_deletion() -> None:
    # Arrange — Proyecto B tiene una sesión legítima
    repo = InMemoryChatRepository()
    create_uc = CreateChatSessionUseCase(repo)
    session_b = await create_uc.execute(
        CreateChatSessionInput(
            project_id=ProjectId("prj_victim_B"),
            phase=SpecPhase.DESCUBRIMIENTO,
        )
    )
    delete_uc = DeleteChatSessionUseCase(repo)

    # Act & Assert — Atacante en Proyecto A intenta borrar la sesión de Proyecto B
    with pytest.raises(ChatSessionNotFoundError):
        await delete_uc.execute(
            DeleteChatSessionInput(
                session_id=session_b.id,
                project_id=ProjectId("prj_attacker_A"),
            )
        )

    # Assert — La sesión de la víctima NO fue borrada
    assert len(repo.sessions) == 1
    assert repo.sessions[0].id == session_b.id

    # Act — El dueño legítimo de Proyecto B sí puede borrar su propia sesión
    await delete_uc.execute(
        DeleteChatSessionInput(
            session_id=session_b.id,
            project_id=ProjectId("prj_victim_B"),
        )
    )

    # Assert — La sesión ahora sí fue eliminada
    assert len(repo.sessions) == 0
