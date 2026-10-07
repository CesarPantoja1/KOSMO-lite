from __future__ import annotations

import pytest

from kosmo.application.pipeline.prompt_enricher import PromptEnricher
from kosmo.contracts.sdd.ids import ProjectId
from tests.factories import a_session
from tests.unit.fakes import (
    InMemoryAgentSessionStore,
    InMemoryKnowledgePatternStore,
    StubEmbedder,
)

_PROMPT = "## System prompt base\n\nInstrucciones del modo."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enrich_without_dependencies_returns_prompt_unchanged() -> None:
    # Arrange
    enricher = PromptEnricher(memory=None, pattern_store=None, embedder=None)

    # Act
    result = await enricher.enrich(_PROMPT, "base", ProjectId("prj_01"))

    # Assert
    assert result == _PROMPT


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enrich_injects_project_context() -> None:
    # Arrange
    project_id = ProjectId("prj_01")
    memory = InMemoryAgentSessionStore()
    await memory.save_session(a_session(project_id=project_id, is_completed=True))
    enricher = PromptEnricher(memory=memory, pattern_store=None, embedder=None)

    # Act
    result = await enricher.enrich(_PROMPT, "base", project_id)

    # Assert
    assert "## Contexto acumulado del proyecto" in result
    assert "1 sesiones previas" in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enrich_injects_learned_patterns() -> None:
    # Arrange
    patterns = InMemoryKnowledgePatternStore()
    from kosmo.contracts.memory.agent_memory import KnowledgePattern
    from kosmo.contracts.sdd.document import SpecPhase

    await patterns.replace_patterns(
        SpecPhase.DESCUBRIMIENTO,
        [KnowledgePattern(pattern_id="kpt_01", phase=SpecPhase.DESCUBRIMIENTO, pattern_text="Siempre valida precios")],
    )
    enricher = PromptEnricher(memory=None, pattern_store=patterns, embedder=None)

    # Act
    result = await enricher.enrich(_PROMPT, "base", None, phase=SpecPhase.DESCUBRIMIENTO)

    # Assert
    assert "## Patrones aprendidos entre proyectos" in result
    assert "Siempre valida precios" in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enrich_injects_cross_project_context() -> None:
    # Arrange
    project_id = ProjectId("prj_A")
    memory = InMemoryAgentSessionStore()
    embedder = StubEmbedder()
    other_embedding = await embedder.embed("texto compartido entre proyectos")
    await memory.save_session(
        a_session(
            project_id=ProjectId("prj_B"),
            is_completed=True,
            embedding=other_embedding,
            embedding_model="stub-embedder",
        )
    )

    enricher = PromptEnricher(memory=memory, pattern_store=None, embedder=embedder)

    # Act
    result = await enricher.enrich(_PROMPT, "texto compartido entre proyectos", project_id)

    # Assert
    assert "## Sesiones similares en otros proyectos" in result
    assert "prj_B" in result
