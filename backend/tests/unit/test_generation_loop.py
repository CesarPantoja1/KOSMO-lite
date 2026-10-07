from __future__ import annotations

from typing import Any

import pytest

from kosmo.application.pipeline.generation_loop import GenerationLoop
from kosmo.application.pipeline.prompt_enricher import PromptEnricher
from kosmo.application.pipeline.session_recorder import SessionRecorder
from kosmo.application.pipeline.tool_resolver import ToolResolver
from kosmo.contracts.pipeline.phase_contexts import DiscoveryPhaseContext
from kosmo.contracts.pipeline.phase_outputs import DiscoveryPhaseOutput
from kosmo.contracts.sdd.ids import ProjectId
from tests.unit.conftest import DISCOVERY_VALID, StubStructuredLLMClient, make_discovery_document, make_discovery_mode
from tests.unit.fakes import InMemoryAgentSessionStore


class _FailingLLM:
    async def complete_typed(
        self, prompt: Any, output_type: Any, temperature: float = 0.1, max_tokens: int = 4096
    ) -> Any:  # noqa: ARG002
        raise RuntimeError("LLM error")

    async def complete(self, prompt: Any, temperature: float = 0.3, max_tokens: int = 4096) -> Any:  # noqa: ARG002
        raise RuntimeError("LLM error")


def _make_loop(llm: Any, *, memory: InMemoryAgentSessionStore | None = None, max_iterations: int = 8) -> GenerationLoop:
    enricher = PromptEnricher(memory=memory, pattern_store=None, embedder=None)
    tools = ToolResolver(llm_client=llm, knowledge_tools=None)
    recorder = SessionRecorder(
        memory=memory,
        pattern_store=None,
        embedder=None,
        llm_client=llm,  # type: ignore[arg-type]
        outbox=None,
        max_iterations=max_iterations,
        consolidation_threshold=5,
    )
    return GenerationLoop(
        llm_client=llm,  # type: ignore[arg-type]
        max_iterations=max_iterations,
        prompt_enricher=enricher,
        tool_resolver=tools,
        session_recorder=recorder,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_returns_typed_output_on_valid_first_attempt() -> None:
    # Arrange
    llm = StubStructuredLLMClient(responses=[make_discovery_document(DISCOVERY_VALID)])
    loop = _make_loop(llm)

    # Act
    result = await loop.run(
        make_discovery_mode(),
        DiscoveryPhaseContext(project_name="Test", project_description="Test"),
        skill_name="discovery_generate",
        project_id=None,
    )

    # Assert
    assert isinstance(result, DiscoveryPhaseOutput)
    assert result.validation_result.is_valid is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_saves_incomplete_session_when_llm_fails() -> None:
    # Arrange
    llm = _FailingLLM()
    memory = InMemoryAgentSessionStore()
    loop = _make_loop(llm, memory=memory, max_iterations=2)
    project_id = ProjectId("prj_01")

    # Act
    result = await loop.run(
        make_discovery_mode(),
        DiscoveryPhaseContext(project_name="Test", project_description="Test"),
        skill_name="discovery_generate",
        project_id=project_id,
    )

    # Assert
    assert isinstance(result, DiscoveryPhaseOutput)
    assert result.validation_result.is_valid is False
    sessions = await memory.list_sessions(project_id)
    assert len(sessions) == 1
    assert sessions[0].is_completed is False
