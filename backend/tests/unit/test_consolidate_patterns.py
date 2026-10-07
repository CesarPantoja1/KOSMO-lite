from __future__ import annotations

import json

import pytest

from kosmo.application.knowledge import ConsolidateInput, ConsolidateKnowledgePatterns
from kosmo.contracts.llm.ports import LLMResponse, LLMUsage, PromptTemplate
from kosmo.contracts.sdd.document import SpecPhase
from tests.factories import a_session
from tests.unit.fakes import (
    InMemoryAgentSessionStore,
    InMemoryKnowledgePatternStore,
)


class StubPatternLLMClient:
    def __init__(self, response_patterns: list[dict[str, object]] | None = None) -> None:
        self._patterns = response_patterns or [
            {"pattern": "los proyectos de e-commerce siempre requieren validacion de moneda", "support": 5},
            {"pattern": "las reglas de negocio deben incluir limites de monto por transaccion", "support": 3},
        ]

    async def complete(
        self,
        prompt: PromptTemplate,  # noqa: ARG002
        temperature: float = 0.3,  # noqa: ARG002
        max_tokens: int = 4096,  # noqa: ARG002
    ) -> LLMResponse:
        text = json.dumps({"patterns": self._patterns})
        return LLMResponse(text=text, usage=LLMUsage())

    async def complete_json(
        self,
        prompt: PromptTemplate,  # noqa: ARG002
        temperature: float = 0.1,  # noqa: ARG002
        max_tokens: int = 4096,  # noqa: ARG002
    ) -> LLMResponse:
        return await self.complete(prompt, temperature, max_tokens)

    async def complete_typed[T](
        self,
        prompt: PromptTemplate,
        output_type: type[T],
        temperature: float = 0.1,  # noqa: ARG002
        max_tokens: int = 4096,  # noqa: ARG002
    ) -> T:  # noqa: ARG002
        raise NotImplementedError

    @property
    def supports_native_tools(self) -> bool:
        return False

    async def complete_with_tools(
        self,
        prompt: PromptTemplate,  # noqa: ARG002
        tools: list[dict[str, object]],  # noqa: ARG002
        tool_handler: object,  # noqa: ARG002
        temperature: float = 0.1,  # noqa: ARG002
        max_tokens: int = 2000,  # noqa: ARG002
    ) -> tuple[str, list[object]]:
        return ("", [])


@pytest.mark.asyncio
@pytest.mark.unit
async def test_consolidate_creates_patterns() -> None:
    # Arrange
    memory = InMemoryAgentSessionStore()
    pattern_store = InMemoryKnowledgePatternStore()
    llm = StubPatternLLMClient()
    uc = ConsolidateKnowledgePatterns(memory=memory, pattern_store=pattern_store, llm_client=llm)  # type: ignore[reportArgumentType]

    for _ in range(10):
        await memory.save_session(
            a_session(
                is_completed=True,
                phase=SpecPhase.DESCUBRIMIENTO,
                reflection="el negocio necesita reglas de validacion de moneda y limites de transaccion",
            )
        )

    # Act
    result = await uc.execute(ConsolidateInput(sessions_limit=20))

    # Assert
    assert result.get("descubrimiento", 0) >= 1
    patterns = await pattern_store.list_patterns(phase=SpecPhase.DESCUBRIMIENTO)
    assert len(patterns) >= 1
    assert isinstance(patterns[0].pattern_id, str)
    assert patterns[0].support_count >= 1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_consolidate_skips_phase_with_insufficient_sessions() -> None:
    # Arrange
    memory = InMemoryAgentSessionStore()
    pattern_store = InMemoryKnowledgePatternStore()
    llm = StubPatternLLMClient()
    uc = ConsolidateKnowledgePatterns(memory=memory, pattern_store=pattern_store, llm_client=llm)  # type: ignore[reportArgumentType]

    await memory.save_session(
        a_session(
            is_completed=True,
            phase=SpecPhase.MODELO,
            reflection="simplifica el diagrama de actividad",
        )
    )

    # Act
    result = await uc.execute(ConsolidateInput(sessions_limit=20))

    # Assert
    assert result == {}


@pytest.mark.asyncio
@pytest.mark.unit
async def test_consolidate_purges_old_patterns_on_replace() -> None:
    # Arrange
    memory = InMemoryAgentSessionStore()
    pattern_store = InMemoryKnowledgePatternStore()
    llm = StubPatternLLMClient()
    uc = ConsolidateKnowledgePatterns(memory=memory, pattern_store=pattern_store, llm_client=llm)  # type: ignore[reportArgumentType]

    for _ in range(5):
        await memory.save_session(
            a_session(
                is_completed=True,
                phase=SpecPhase.DESCUBRIMIENTO,
                reflection="mejora el alcance del documento",
            )
        )

    # Act — first consolidation
    await uc.execute(ConsolidateInput())

    # Act — second consolidation with fewer patterns
    llm._patterns = []  # type: ignore[reportAttributeAccessIssue]
    await uc.execute(ConsolidateInput())

    # Assert
    patterns = await pattern_store.list_patterns(phase=SpecPhase.DESCUBRIMIENTO)
    assert len(patterns) == 0


@pytest.mark.asyncio
@pytest.mark.unit
async def test_count_completed_by_phase_in_memory() -> None:
    # Arrange
    memory = InMemoryAgentSessionStore()

    for _ in range(3):
        await memory.save_session(a_session(is_completed=True, phase=SpecPhase.DESCUBRIMIENTO))
    for _ in range(2):
        await memory.save_session(a_session(is_completed=True, phase=SpecPhase.MODELO))
    await memory.save_session(a_session(is_completed=False, phase=SpecPhase.DESCUBRIMIENTO))

    # Act
    counts = await memory.count_completed_by_phase()

    # Assert
    assert counts == {"descubrimiento": 3, "modelo": 2}


@pytest.mark.asyncio
@pytest.mark.unit
async def test_count_completed_by_phase_since_session() -> None:
    # Arrange
    memory = InMemoryAgentSessionStore()

    s1 = a_session(is_completed=True, phase=SpecPhase.DESCUBRIMIENTO)
    await memory.save_session(s1)
    s2 = a_session(is_completed=True, phase=SpecPhase.DESCUBRIMIENTO)
    await memory.save_session(s2)
    s3 = a_session(is_completed=True, phase=SpecPhase.DESCUBRIMIENTO)
    await memory.save_session(s3)

    # Act — count sessions after s1
    counts = await memory.count_completed_by_phase(since_session_id=s1.session_id)

    # Assert
    assert counts.get("descubrimiento", 0) == 2  # s2, s3
