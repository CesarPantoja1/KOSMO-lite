from __future__ import annotations

import pytest

from kosmo.application.pipeline.session_recorder import SessionRecorder
from kosmo.contracts.llm.ports import LLMResponse, LLMUsage, PromptTemplate
from kosmo.contracts.pipeline.phase_outputs import ValidationResult
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.ids import AgentMemoryId, ProjectId
from tests.factories import a_session
from tests.unit.fakes import InMemoryAgentSessionStore, InMemoryOutbox


class _StubReflectionLLM:
    def __init__(self, text: str) -> None:
        self._text = text
        self.call_count = 0

    async def complete(self, prompt: PromptTemplate, temperature: float = 0.3, max_tokens: int = 4096) -> LLMResponse:
        self.call_count += 1
        return LLMResponse(text=self._text, usage=LLMUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2))


def _make_recorder(
    memory: InMemoryAgentSessionStore,
    llm: _StubReflectionLLM,
    *,
    outbox: InMemoryOutbox | None = None,
) -> SessionRecorder:
    return SessionRecorder(
        memory=memory,
        pattern_store=None,
        embedder=None,
        llm_client=llm,  # type: ignore[arg-type]
        outbox=outbox,
        max_iterations=8,
        consolidation_threshold=5,
    )


def _valid_validation() -> ValidationResult:
    return ValidationResult(is_valid=True, errors=[])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_record_saves_session_and_enqueues_outbox_job() -> None:
    # Arrange
    memory = InMemoryAgentSessionStore()
    outbox = InMemoryOutbox()
    recorder = _make_recorder(memory, _StubReflectionLLM(""), outbox=outbox)
    project_id = ProjectId("prj_01")

    # Act
    await recorder.record(
        project_id=project_id,
        phase=SpecPhase.DESCUBRIMIENTO,
        session_type="generation",
        skill_name="discovery_generate",
        current_iteration=1,
        output={"document": "contenido"},
        validation=_valid_validation(),
        user_instructions=None,
    )

    # Assert
    sessions = await memory.list_sessions(project_id)
    assert len(sessions) == 1
    assert sessions[0].is_completed is True

    assert len(outbox.jobs) == 1
    job_type, payload = outbox.jobs[0]
    assert job_type == "reflect_and_consolidate"
    assert payload["session_id"] == str(sessions[0].session_id)
    assert payload["phase"] == SpecPhase.DESCUBRIMIENTO.value


@pytest.mark.unit
@pytest.mark.asyncio
async def test_reflect_and_consolidate_updates_reflection() -> None:
    # Arrange
    memory = InMemoryAgentSessionStore()
    recorder = _make_recorder(memory, _StubReflectionLLM("Siempre valida la estructura antes de entregar."))
    await memory.save_session(a_session(session_id=AgentMemoryId("agm_test01"), project_id=ProjectId("prj_01")))

    # Act — sesión con reintentos: la reflexión SÍ se genera
    await recorder.reflect_and_consolidate(
        session_id=AgentMemoryId("agm_test01"),
        phase=SpecPhase.DESCUBRIMIENTO,
        session_type="generation",
        is_completed=True,
        current_iteration=2,
        validation=_valid_validation(),
    )

    # Assert
    saved = await memory.load_session(AgentMemoryId("agm_test01"))
    assert saved is not None
    assert saved.reflection == "Siempre valida la estructura antes de entregar."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clean_session_skips_reflection_llm_call() -> None:
    # Arrange
    memory = InMemoryAgentSessionStore()
    llm = _StubReflectionLLM("Lección aprendida innecesaria para sesión limpia.")
    recorder = _make_recorder(memory, llm)
    await memory.save_session(a_session(session_id=AgentMemoryId("agm_test01"), project_id=ProjectId("prj_01")))

    # Act — sesión limpia: 1 iteración, sin errores
    await recorder.reflect_and_consolidate(
        session_id=AgentMemoryId("agm_test01"),
        phase=SpecPhase.DESCUBRIMIENTO,
        session_type="generation",
        is_completed=True,
        current_iteration=1,
        validation=_valid_validation(),
    )

    # Assert — no se llama al LLM y no se guarda reflexión
    assert llm.call_count == 0
    saved = await memory.load_session(AgentMemoryId("agm_test01"))
    assert saved is not None
    assert saved.reflection is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_reflect_and_consolidate_keeps_none_when_reflection_is_short() -> None:
    # Arrange
    memory = InMemoryAgentSessionStore()
    recorder = _make_recorder(memory, _StubReflectionLLM("corta"))
    await memory.save_session(a_session(session_id=AgentMemoryId("agm_test01"), project_id=ProjectId("prj_01")))

    # Act
    await recorder.reflect_and_consolidate(
        session_id=AgentMemoryId("agm_test01"),
        phase=SpecPhase.DESCUBRIMIENTO,
        session_type="generation",
        is_completed=True,
        current_iteration=2,
        validation=_valid_validation(),
    )

    # Assert
    saved = await memory.load_session(AgentMemoryId("agm_test01"))
    assert saved is not None
    assert saved.reflection is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_record_without_outbox_saves_session_only() -> None:
    # Arrange
    memory = InMemoryAgentSessionStore()
    recorder = _make_recorder(memory, _StubReflectionLLM(""), outbox=None)
    project_id = ProjectId("prj_01")

    # Act
    await recorder.record(
        project_id=project_id,
        phase=SpecPhase.DESCUBRIMIENTO,
        session_type="generation",
        skill_name="discovery_generate",
        current_iteration=1,
        output={"document": "contenido"},
        validation=_valid_validation(),
        user_instructions=None,
    )

    # Assert: la sesion se persiste aunque el outbox no este configurado
    sessions = await memory.list_sessions(project_id)
    assert len(sessions) == 1


class _FailingMemory(InMemoryAgentSessionStore):
    async def update_reflection(self, session_id: AgentMemoryId, reflection: str) -> None:  # noqa: ARG002
        raise RuntimeError("fallo simulado")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_supervised_reflect_never_raises() -> None:
    # Arrange — memoria que falla al guardar la reflexion
    memory = _FailingMemory()
    recorder = _make_recorder(memory, _StubReflectionLLM("Una leccion suficientemente larga para guardarse."))

    # Act — no debe propagar la excepción
    await recorder._supervised_reflect(  # noqa: SLF001
        session_id=AgentMemoryId("agm_test01"),
        phase=SpecPhase.DESCUBRIMIENTO,
        session_type="generation",
        is_completed=True,
        current_iteration=2,
        validation=_valid_validation(),
    )

    # Assert — si llegamos aquí sin excepción, el fallback está supervisado
    assert True
