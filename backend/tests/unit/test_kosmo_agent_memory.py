from __future__ import annotations

import pytest

from kosmo.application.pipeline.kosmo_agent import KOSMOAgent
from kosmo.contracts.llm.ports import LLMResponse, PromptTemplate
from kosmo.contracts.pipeline.orchestrator_ports import Skill
from kosmo.contracts.pipeline.phase_contexts import DiscoveryPhaseContext
from kosmo.contracts.pipeline.phase_outputs import DiscoveryPhaseOutput
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.ids import ProjectId
from kosmo.domain.pipeline.knowledge_tool_registry import KnowledgeToolDef, KnowledgeToolRegistry
from kosmo.domain.pipeline.skill_registry import SkillRegistry
from tests.factories import a_project_id
from tests.unit.conftest import (
    DISCOVERY_VALID,
    StubStructuredLLMClient,
    make_discovery_document,
    make_discovery_mode,
)
from tests.unit.fakes import InMemoryAgentSessionStore


def _make_agent(llm, max_iterations=3, memory=None):
    skill_reg = SkillRegistry()
    skill_reg.register(
        Skill(
            name="discovery_generate",
            description="Test skill",
            phase=SpecPhase.DESCUBRIMIENTO,
            mode=make_discovery_mode(),  # type: ignore[reportArgumentType]
        )
    )
    return KOSMOAgent(
        llm_client=llm,  # type: ignore[reportArgumentType]
        max_iterations=max_iterations,
        skill_registry=skill_reg,
        memory=memory,  # type: ignore[reportArgumentType]
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_agent_saves_session_on_successful_completion() -> None:
    # Arrange
    llm = StubStructuredLLMClient(responses=[make_discovery_document(DISCOVERY_VALID)])
    store = InMemoryAgentSessionStore()
    agent = _make_agent(llm, memory=store)
    project_id = a_project_id()

    # Act
    result = await agent.execute_with_skill(
        skill_name="discovery_generate",
        context=DiscoveryPhaseContext(project_name="Test", project_description="Test"),
        project_id=project_id,
    )

    # Assert
    assert isinstance(result, DiscoveryPhaseOutput)
    assert result.validation_result.is_valid is True
    sessions = await store.list_sessions(project_id)
    assert len(sessions) == 1
    saved = sessions[0]
    assert saved.session_type == "generation"
    assert saved.phase == SpecPhase.DESCUBRIMIENTO
    assert saved.is_completed is True
    assert saved.total_llm_calls == 1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_agent_with_memory_but_no_project_id_does_not_save() -> None:
    # Arrange
    llm = StubStructuredLLMClient(responses=[make_discovery_document(DISCOVERY_VALID)])
    store = InMemoryAgentSessionStore()
    agent = _make_agent(llm, memory=store)

    # Act
    result = await agent.execute_with_skill(
        skill_name="discovery_generate",
        context=DiscoveryPhaseContext(project_name="Test", project_description="Test"),
    )

    # Assert
    assert isinstance(result, DiscoveryPhaseOutput)
    assert result.validation_result.is_valid is True
    sessions = await store.list_sessions(a_project_id())
    assert len(sessions) == 0


@pytest.mark.unit
@pytest.mark.parametrize(
    "user_instructions,expected_session_type",
    [
        ("hazlo mas conciso", "refinement"),
        (None, "generation"),
    ],
)
@pytest.mark.asyncio
@pytest.mark.unit
async def test_agent_saves_correct_session_type(
    user_instructions: str | None,
    expected_session_type: str,
) -> None:
    # Arrange
    llm = StubStructuredLLMClient(responses=[make_discovery_document(DISCOVERY_VALID)])
    store = InMemoryAgentSessionStore()
    agent = _make_agent(llm, memory=store)
    project_id = a_project_id()

    # Act
    result = await agent.execute_with_skill(
        skill_name="discovery_generate",
        context=DiscoveryPhaseContext(project_name="Test", project_description="Test"),
        project_id=project_id,
        user_instructions=user_instructions,
    )

    # Assert
    assert result.validation_result.is_valid is True
    sessions = await store.list_sessions(project_id)
    assert len(sessions) == 1
    assert sessions[0].session_type == expected_session_type
    assert sessions[0].user_instructions == user_instructions


@pytest.mark.unit
@pytest.mark.parametrize(
    "project_a,project_b",
    [
        (ProjectId("prj_A"), ProjectId("prj_B")),
        (ProjectId("prj_01KT01ABC"), ProjectId("prj_01KT01DEF")),
    ],
)
@pytest.mark.asyncio
@pytest.mark.unit
async def test_sessions_are_isolated_between_projects(
    project_a: ProjectId,
    project_b: ProjectId,
) -> None:
    # Arrange
    llm = StubStructuredLLMClient(
        responses=[
            make_discovery_document(DISCOVERY_VALID),
            make_discovery_document(DISCOVERY_VALID),
        ]
    )
    store = InMemoryAgentSessionStore()
    agent = _make_agent(llm, memory=store)

    # Act
    await agent.execute_with_skill(
        skill_name="discovery_generate",
        context=DiscoveryPhaseContext(project_name="A", project_description="A"),
        project_id=project_a,
    )
    await agent.execute_with_skill(
        skill_name="discovery_generate",
        context=DiscoveryPhaseContext(project_name="B", project_description="B"),
        project_id=project_b,
    )

    # Assert
    sessions_a = await store.list_sessions(project_a)
    sessions_b = await store.list_sessions(project_b)
    assert len(sessions_a) == 1
    assert len(sessions_b) == 1
    assert sessions_a[0].project_id != sessions_b[0].project_id


@pytest.mark.asyncio
@pytest.mark.unit
async def test_agent_without_knowledge_tools_records_reasoning() -> None:
    # Arrange
    llm = StubStructuredLLMClient(responses=[make_discovery_document(DISCOVERY_VALID)])
    store = InMemoryAgentSessionStore()
    agent = _make_agent(llm, memory=store)
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
    assert any("pre_consulta_tools" in entry for entry in saved.reasoning_log)
    assert saved.tool_results == []


@pytest.mark.asyncio
@pytest.mark.unit
async def test_agent_with_knowledge_tools_records_tool_invocations() -> None:
    # Arrange
    call_order: list[str] = []

    class StubToolCallLLMClient:
        async def complete(  # noqa: PLR6301
            self,
            prompt: PromptTemplate,
            temperature: float = 0.3,
            max_tokens: int = 4096,  # noqa: ARG002
        ) -> LLMResponse:
            call_order.append("complete")
            if len(call_order) <= 1:
                return LLMResponse(text='[TOOL: test_kb] {"query": "ejemplo"}')
            return LLMResponse(text="[CONTINUE]")

        async def complete_json(  # noqa: PLR6301
            self,
            prompt: PromptTemplate,
            temperature: float = 0.1,
            max_tokens: int = 4096,  # noqa: ARG002
        ) -> LLMResponse:
            return await self.complete(prompt, temperature, max_tokens)

        async def complete_typed[T](  # noqa: PLR6301
            self,
            prompt: PromptTemplate,  # noqa: ARG002
            output_type: type[T],  # noqa: ARG002
            temperature: float = 0.1,  # noqa: ARG002
            max_tokens: int = 4096,  # noqa: ARG002
        ) -> T:
            return output_type.model_validate({"document": DISCOVERY_VALID})  # type: ignore[reportReturnType]

        @property
        def supports_native_tools(self) -> bool:
            return False

        async def complete_with_tools(  # noqa: PLR6301
            self,
            prompt: PromptTemplate,  # noqa: ARG002
            tools: list[dict[str, object]],  # noqa: ARG002
            tool_handler: object,  # noqa: ARG002
            temperature: float = 0.1,  # noqa: ARG002
            max_tokens: int = 2000,  # noqa: ARG002
        ) -> tuple[str, list[object]]:
            return ("", [])

    llm = StubToolCallLLMClient()
    store = InMemoryAgentSessionStore()
    skill_reg = SkillRegistry()
    mode = make_discovery_mode()
    mode.requires_tool_consultation = True  # este test verifica el registro de invocaciones de tools
    skill_reg.register(
        Skill(
            name="discovery_generate",
            description="Test",
            phase=SpecPhase.DESCUBRIMIENTO,
            mode=mode,  # type: ignore[reportArgumentType]
        )
    )
    knowledge_tools = KnowledgeToolRegistry()

    async def _test_kb_handler(input_data: dict[str, object]) -> str:  # noqa: ARG001
        return "resultado de test_kb"

    knowledge_tools.register(
        KnowledgeToolDef(name="test_kb", description="Test tool", parameters={"type": "object"}),
        _test_kb_handler,
    )
    agent = KOSMOAgent(
        llm_client=llm,  # type: ignore[reportArgumentType]
        max_iterations=3,
        skill_registry=skill_reg,
        memory=store,  # type: ignore[reportArgumentType]
        knowledge_tools=knowledge_tools,
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
    assert any("test_kb" in entry for entry in saved.reasoning_log)
    assert len(saved.tool_results) == 1
    assert saved.tool_results[0]["tool"] == "test_kb"
    assert saved.tool_results[0]["found"] is True


@pytest.mark.asyncio
@pytest.mark.unit
async def test_agent_saves_reasoning_on_validation_failure() -> None:
    # Arrange
    invalid_doc = make_discovery_document("## Test\n\nContenido insuficiente")
    responses = [invalid_doc, invalid_doc]
    llm = StubStructuredLLMClient(responses=responses)
    store = InMemoryAgentSessionStore()
    agent = _make_agent(llm, max_iterations=2, memory=store)
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
    assert any("pre_consulta_tools" in entry for entry in saved.reasoning_log)
