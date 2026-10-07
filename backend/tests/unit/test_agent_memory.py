from __future__ import annotations

import pytest

from kosmo.contracts.memory.agent_memory import AgentSessionSummary
from kosmo.contracts.pipeline.phase_contexts import DiscoveryPhaseContext
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.ids import AgentMemoryId, ProjectId
from tests.factories import a_project_id, a_session
from tests.unit.fakes import InMemoryAgentSessionStore


@pytest.mark.unit
class TestInMemoryStoreSaveAndLoad:
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_save_and_load_session(self) -> None:
        # Arrange
        store = InMemoryAgentSessionStore()
        session = a_session()

        # Act
        await store.save_session(session)
        loaded = await store.load_session(session.session_id)

        # Assert
        assert loaded is not None
        assert loaded.session_id == session.session_id
        assert loaded.project_id == session.project_id

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_load_nonexistent_session_returns_none(self) -> None:
        # Arrange
        store = InMemoryAgentSessionStore()

        # Act
        result = await store.load_session(AgentMemoryId("agm_nonexistent"))

        # Assert
        assert result is None

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_save_overwrites_existing_session(self) -> None:
        # Arrange
        store = InMemoryAgentSessionStore()
        session = a_session(current_iteration=0, is_completed=False)
        await store.save_session(session)

        updated = a_session(
            session_id=session.session_id,
            project_id=session.project_id,
            session_type=session.session_type,
            phase=session.phase,
            current_iteration=5,
            is_completed=True,
        )

        # Act
        await store.save_session(updated)
        loaded = await store.load_session(session.session_id)

        # Assert
        assert loaded is not None
        assert loaded.current_iteration == 5
        assert loaded.is_completed is True


@pytest.mark.unit
class TestInMemoryStoreList:
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_list_sessions_by_project(self) -> None:
        # Arrange
        store = InMemoryAgentSessionStore()
        project_id = ProjectId("prj_01KT01ABC")
        s1 = a_session(project_id=project_id)
        s2 = a_session(project_id=project_id, session_type="refinement")
        s3 = a_session(project_id=ProjectId("prj_01KT01DEF"), phase=SpecPhase.REQUISITOS)
        await store.save_session(s1)
        await store.save_session(s2)
        await store.save_session(s3)

        # Act
        results = await store.list_sessions(project_id)

        # Assert
        assert len(results) == 2
        assert all(isinstance(r, AgentSessionSummary) for r in results)
        ids = {r.session_id for r in results}
        assert s1.session_id in ids
        assert s2.session_id in ids
        assert s3.session_id not in ids

    @pytest.mark.parametrize(
        "filter_phase,expected_count",
        [
            (SpecPhase.REQUISITOS, 1),
            (SpecPhase.DESCUBRIMIENTO, 1),
            (SpecPhase.CARACTERISTICAS, 0),
        ],
    )
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_list_sessions_filtered_by_phase(self, filter_phase: SpecPhase, expected_count: int) -> None:
        # Arrange
        store = InMemoryAgentSessionStore()
        project_id = a_project_id()
        s1 = a_session(project_id=project_id, phase=SpecPhase.DESCUBRIMIENTO)
        s2 = a_session(project_id=project_id, phase=SpecPhase.REQUISITOS)
        await store.save_session(s1)
        await store.save_session(s2)

        # Act
        results = await store.list_sessions(project_id, phase=filter_phase)

        # Assert
        assert len(results) == expected_count

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_list_sessions_empty_project(self) -> None:
        # Arrange
        store = InMemoryAgentSessionStore()

        # Act
        results = await store.list_sessions(ProjectId("prj_empty"))

        # Assert
        assert results == []


@pytest.mark.unit
class TestInMemoryStoreGetLatest:
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_latest_session_returns_most_recent(self) -> None:
        # Arrange
        store = InMemoryAgentSessionStore()
        project_id = a_project_id()
        s1 = a_session(project_id=project_id)
        s2 = a_session(project_id=project_id, session_type="refinement")
        await store.save_session(s1)
        await store.save_session(s2)

        # Act
        result = await store.get_latest_session(project_id, SpecPhase.DESCUBRIMIENTO)

        # Assert
        assert result is not None
        assert result.session_id == s2.session_id

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_latest_session_returns_none_when_empty(self) -> None:
        # Arrange
        store = InMemoryAgentSessionStore()

        # Act
        result = await store.get_latest_session(ProjectId("prj_empty"), SpecPhase.DESCUBRIMIENTO)

        # Assert
        assert result is None


@pytest.mark.unit
class TestInMemoryStoreProjectContext:
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_project_context_aggregates_sessions(self) -> None:
        # Arrange
        store = InMemoryAgentSessionStore()
        project_id = a_project_id()
        s1 = a_session(project_id=project_id, is_completed=True)
        s2 = a_session(project_id=project_id, phase=SpecPhase.REQUISITOS, is_completed=True)
        await store.save_session(s1)
        await store.save_session(s2)

        # Act
        context = await store.get_project_context(project_id)

        # Assert
        assert context.project_id == project_id
        assert context.total_sessions == 2
        assert len(context.latest_sessions) == 2

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_project_context_populates_common_validation_errors(self) -> None:
        # Arrange
        store = InMemoryAgentSessionStore()
        project_id = a_project_id()
        s1 = a_session(
            project_id=project_id,
            is_completed=False,
            validation_error_messages=["error A", "error B"],
        )
        s2 = a_session(
            project_id=project_id,
            is_completed=False,
            validation_error_messages=["error A", "error C"],
        )
        s3 = a_session(
            project_id=project_id,
            is_completed=False,
            validation_error_messages=["error A"],
        )
        await store.save_session(s1)
        await store.save_session(s2)
        await store.save_session(s3)

        # Act
        context = await store.get_project_context(project_id)

        # Assert
        assert "error A (x3)" in context.common_validation_errors
        assert "error B (x1)" in context.common_validation_errors
        assert "error C (x1)" in context.common_validation_errors
        assert len(context.common_validation_errors) == 3

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_project_context_skips_completed_sessions_for_errors(self) -> None:
        # Arrange
        store = InMemoryAgentSessionStore()
        project_id = a_project_id()
        s1 = a_session(
            project_id=project_id,
            is_completed=True,
            validation_error_messages=["error ignorado"],
        )
        await store.save_session(s1)

        # Act
        context = await store.get_project_context(project_id)

        # Assert
        assert context.common_validation_errors == []


@pytest.mark.asyncio
@pytest.mark.unit
async def test_agent_session_stores_validation_error_messages() -> None:
    # Arrange
    from kosmo.application.pipeline.kosmo_agent import KOSMOAgent
    from kosmo.contracts.pipeline.orchestrator_ports import Skill
    from kosmo.domain.pipeline.skill_registry import SkillRegistry
    from tests.factories import a_project_id
    from tests.unit.conftest import (
        StubStructuredLLMClient,
        make_discovery_document,
        make_discovery_mode,
    )

    invalid_doc = make_discovery_document("## Test\n\nAPI REST")
    llm = StubStructuredLLMClient(responses=[invalid_doc, invalid_doc])
    store = InMemoryAgentSessionStore()
    agent = KOSMOAgent(
        llm_client=llm,  # type: ignore[reportArgumentType]
        max_iterations=2,
        skill_registry=SkillRegistry(),
        memory=store,  # type: ignore[reportArgumentType]
    )
    agent._skill_registry.register(  # type: ignore[reportOptionalMemberAccess]
        Skill(
            name="discovery_generate",
            description="Test",
            phase=SpecPhase.DESCUBRIMIENTO,
            mode=make_discovery_mode(),  # type: ignore[reportArgumentType]
        )
    )
    project_id = a_project_id()

    # Act
    await agent.execute_with_skill(
        skill_name="discovery_generate",
        context=DiscoveryPhaseContext(project_name="Test", project_description="Test"),
        project_id=project_id,
    )

    # Assert
    sessions = await store.list_sessions(project_id)
    assert len(sessions) == 1
    saved = await store.load_session(sessions[0].session_id)
    assert saved is not None
    assert saved.is_completed is False
    assert len(saved.validation_error_messages) > 0


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_similar_sessions_filters_by_model() -> None:
    # Arrange
    store = InMemoryAgentSessionStore()
    v1 = [0.1, 0.2, 0.3, 0.4]
    v2 = [0.2, 0.3, 0.4, 0.5]
    s_openai = a_session(embedding=v1, embedding_model="text-embedding-3-small")
    s_local = a_session(embedding=v2, embedding_model="all-MiniLM-L6-v2")
    s_no_model = a_session(embedding=v1, embedding_model=None)
    await store.save_session(s_openai)
    await store.save_session(s_local)
    await store.save_session(s_no_model)

    # Act
    results = await store.get_similar_sessions(v1, model="text-embedding-3-small")

    # Assert
    assert len(results) == 1
    result_session = await store.load_session(results[0].session_id)
    assert result_session is not None
    assert result_session.embedding_model == "text-embedding-3-small"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_similar_sessions_no_model_filter_returns_all() -> None:
    # Arrange
    store = InMemoryAgentSessionStore()
    v = [0.1, 0.2, 0.3, 0.4]
    await store.save_session(a_session(embedding=v, embedding_model="openai"))
    await store.save_session(a_session(embedding=v, embedding_model="fastembed"))

    # Act
    results = await store.get_similar_sessions(v)

    # Assert
    assert len(results) == 2
