from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kosmo.contracts.memory.agent_memory import (
    AgentSession,
    KnowledgePattern,
)
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.ids import AgentMemoryId, ProjectId
from kosmo.infrastructure.persistence.postgres.models import AgentSessionModel
from kosmo.infrastructure.persistence.postgres.repositories.agent_memory_repo import (
    SqlAlchemyAgentSessionStore,
    SqlAlchemyKnowledgePatternStore,
)


def _make_agent_session(
    session_id: str = "sess_01",
    project_id: str = "proj_01",
) -> AgentSession:
    now = datetime.now(UTC)
    return AgentSession(
        session_id=AgentMemoryId(session_id),
        project_id=ProjectId(project_id),
        session_type="generation",
        phase=SpecPhase.CARACTERISTICAS,
        skill_name="feature_generation",
        conversation=["user: hola", "assistant: saludos"],
        reasoning_log=["analizando requerimiento"],
        tool_results=[{"tool": "spec_query", "result": "ok"}],
        current_iteration=1,
        max_iterations=5,
        is_completed=True,
        output_json='{"status": "ok"}',
        validation_is_valid=True,
        validation_errors=0,
        validation_error_messages=[],
        total_llm_calls=2,
        user_instructions="crear catalogo",
        embedding=[0.1, 0.2, 0.3],
        embedding_model="text-embedding-3-small",
        reflection="Todo funciono bien",
        created_at=now,
        updated_at=now,
    )


def _make_mock_session_factory(mock_session: MagicMock) -> async_sessionmaker[AsyncSession]:
    mock_factory = MagicMock(spec=async_sessionmaker)
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_factory.return_value = mock_ctx
    return mock_factory


@pytest.mark.unit
@pytest.mark.asyncio
async def test_save_session_executes_and_commits() -> None:
    mock_session = MagicMock(spec=AsyncSession)
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    factory = _make_mock_session_factory(mock_session)

    store = SqlAlchemyAgentSessionStore(factory)
    session = _make_agent_session()

    await store.save_session(session)

    assert mock_session.execute.await_count == 1
    assert mock_session.commit.await_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_load_session_returns_model_when_found() -> None:
    now = datetime.now(UTC)
    model = AgentSessionModel(
        id="sess_01",
        project_id="proj_01",
        session_type="generation",
        phase=SpecPhase.CARACTERISTICAS.value,
        skill_name="feature_generation",
        conversation=["c1"],
        reasoning_log=["r1"],
        tool_results=[{"t": 1}],
        current_iteration=1,
        max_iterations=5,
        is_completed=True,
        output_json='{"ok": true}',
        validation_is_valid=True,
        validation_errors=0,
        validation_error_messages=[],
        total_llm_calls=1,
        user_instructions=None,
        embedding=None,
        embedding_model=None,
        reflection=None,
        created_at=now,
        updated_at=now,
    )

    mock_session = MagicMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = model
    mock_session.execute = AsyncMock(return_value=mock_result)
    factory = _make_mock_session_factory(mock_session)

    store = SqlAlchemyAgentSessionStore(factory)
    loaded = await store.load_session(AgentMemoryId("sess_01"))

    assert loaded is not None
    assert loaded.session_id == "sess_01"
    assert loaded.project_id == "proj_01"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_load_session_returns_none_when_not_found() -> None:
    mock_session = MagicMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)
    factory = _make_mock_session_factory(mock_session)

    store = SqlAlchemyAgentSessionStore(factory)
    loaded = await store.load_session(AgentMemoryId("sess_none"))

    assert loaded is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_reflection_updates_and_commits() -> None:
    model = AgentSessionModel(id="sess_01", reflection="prev")
    mock_session = MagicMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = model
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    factory = _make_mock_session_factory(mock_session)

    store = SqlAlchemyAgentSessionStore(factory)
    await store.update_reflection(AgentMemoryId("sess_01"), "nueva reflexion")

    assert model.reflection == "nueva reflexion"
    assert mock_session.commit.await_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_by_project_executes_delete() -> None:
    mock_session = MagicMock(spec=AsyncSession)
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    factory = _make_mock_session_factory(mock_session)

    store = SqlAlchemyAgentSessionStore(factory)
    await store.delete_by_project(ProjectId("proj_01"))

    assert mock_session.execute.await_count == 1
    assert mock_session.commit.await_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_purge_stale_sessions_executes_delete_with_conditions() -> None:
    mock_session = MagicMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.rowcount = 5
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    factory = _make_mock_session_factory(mock_session)

    store = SqlAlchemyAgentSessionStore(factory)
    deleted = await store.purge_stale_sessions(older_than_days=14, incomplete_only=True)

    assert deleted == 5
    assert mock_session.execute.await_count == 1
    assert mock_session.commit.await_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_knowledge_pattern_store_replace_and_list() -> None:
    mock_session = MagicMock(spec=AsyncSession)
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()
    factory = _make_mock_session_factory(mock_session)

    pattern_store = SqlAlchemyKnowledgePatternStore(factory)
    patterns = [
        KnowledgePattern(
            pattern_id="pat_01",
            phase=SpecPhase.CARACTERISTICAS,
            pattern_text="Patron comun",
            support_count=3,
        )
    ]

    await pattern_store.replace_patterns(SpecPhase.CARACTERISTICAS, patterns)
    assert mock_session.add.call_count == 1
    assert mock_session.commit.await_count == 1
