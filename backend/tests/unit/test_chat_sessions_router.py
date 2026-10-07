from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from kosmo.application.chat.chat_sessions import (
    CreateChatSessionUseCase,
    DeleteChatSessionInput,
    DeleteChatSessionUseCase,
    ListChatSessionsUseCase,
)
from kosmo.contracts.auth import Principal
from kosmo.contracts.sdd.ids import ChatSessionId, ProjectId
from kosmo.infrastructure.api.routers.chat_sessions import (
    CreateChatSessionRequestView,
    create_chat_session,
    delete_chat_session,
    list_chat_sessions,
)


def _principal() -> Principal:
    return Principal(subject="usr_test123", scopes=frozenset({"*"}))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_sessions_rejects_unknown_phase() -> None:
    # Arrange
    uc = MagicMock(spec=ListChatSessionsUseCase)
    uc.execute = AsyncMock()

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await list_chat_sessions("prj_01", _principal(), uc, phase="nose")
    assert exc_info.value.status_code == 400


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_session_returns_session_id() -> None:
    # Arrange
    from datetime import UTC, datetime

    from kosmo.contracts.ai.chat import ChatSession
    from kosmo.contracts.sdd.document import SpecPhase
    from kosmo.contracts.sdd.ids import ChatSessionId, ProjectId

    uc = MagicMock(spec=CreateChatSessionUseCase)
    uc.execute = AsyncMock(
        return_value=ChatSession(
            id=ChatSessionId("cht_01"),
            project_id=ProjectId("prj_01"),
            phase=SpecPhase.DESCUBRIMIENTO,
            created_at=datetime.now(UTC),
        )
    )

    # Act
    result = await create_chat_session(
        "prj_01",
        _principal(),
        CreateChatSessionRequestView(phase="discovery"),
        uc,
    )

    # Assert
    assert result["session_id"] == "cht_01"
    assert result["phase"] == "descubrimiento"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_chat_session_passes_project_and_session_id() -> None:
    # Arrange
    uc = MagicMock(spec=DeleteChatSessionUseCase)
    uc.execute = AsyncMock()

    # Act
    response = await delete_chat_session(
        "prj_01",
        "cht_01",
        _principal(),
        uc,
    )

    # Assert
    assert response.status_code == 204
    uc.execute.assert_awaited_once_with(
        DeleteChatSessionInput(
            session_id=ChatSessionId("cht_01"),
            project_id=ProjectId("prj_01"),
        )
    )
