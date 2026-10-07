from __future__ import annotations

import pytest

from kosmo.application.pipeline.kosmo_agent import KOSMOAgent
from kosmo.contracts import (
    ChatMessageId,
    ChatRole,
    MensajeChat,
    RespuestaChatLLM,
    SugerenciaCambioLLM,
)
from kosmo.contracts.llm.ports import PromptTemplate
from kosmo.contracts.pipeline.orchestrator_ports import Skill
from kosmo.contracts.pipeline.phase_contexts import RequirementChatContext
from kosmo.contracts.sdd.document import (
    AcceptanceCriterion,
    DocumentNode,
    EARSPattern,
    RichTextDocument,
    SectionHeading,
    SpecPhase,
)
from kosmo.contracts.sdd.ears import EARSRequirement
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import FeatureId, ProjectId, RequirementId
from kosmo.domain.pipeline.phase_modes.requirements_chat_mode import RequirementsChatMode
from kosmo.domain.pipeline.skill_registry import SkillRegistry


def _make_requirement() -> EARSRequirement:
    return EARSRequirement(
        id=RequirementId("req_01"),
        feature_id=FeatureId("feat_01"),
        feature_number=1,
        requirement_number=1,
        title="Validación de timeout en conexiones",
        pattern=EARSPattern.event_driven,
        statement=(
            "CUANDO se detecte un timeout en la conexión, el sistema debe notificar al usuario con un mensaje de error."
        ),
        origin="Deriva de la necesidad de manejo de errores de red en C01.",
        acceptance_criteria=[
            AcceptanceCriterion(
                scenario="Timeout detectado al enviar datos",
                given="el usuario está enviando datos al servidor",
                when="la conexión excede los 30 segundos sin respuesta",
                then="el sistema muestra un mensaje 'Error de conexión' con opción de reintentar",
            ),
            AcceptanceCriterion(
                scenario="Timeout detectado en segundo plano",
                given="el sistema está sincronizando datos en segundo plano",
                when="la sincronización falla por timeout",
                then="el sistema programa un reintento automático en 5 minutos",
            ),
        ],
    )


def _make_feature() -> Feature:
    return Feature(
        id=FeatureId("feat_01"),
        number=1,
        title="Gestión de catálogo de productos",
        slug="gestion-catalogo-productos",
        description="El usuario administra el catálogo de productos del sistema.",
        project_id=ProjectId("prj_001"),
        origin="Deriva de la meta Gestión financiera.",
    )


def _make_discovery_doc() -> RichTextDocument:
    return RichTextDocument(
        nodes=[
            DocumentNode(
                type="heading",
                content="Alcance",
                heading=SectionHeading(text="Alcance", level=2, slug="alcance"),
            )
        ]
    )


def _make_context() -> RequirementChatContext:
    return RequirementChatContext(
        requirement=_make_requirement(),
        feature=_make_feature(),
        discovery_document=_make_discovery_doc(),
    )


def _make_mode() -> RequirementsChatMode:
    return RequirementsChatMode()


class _StubChatLLM:
    def __init__(self, response: RespuestaChatLLM | None = None):
        self._response = response or RespuestaChatLLM(content="respuesta")
        self._calls: list[PromptTemplate] = []
        self._index = 0

    @property
    def call_count(self) -> int:
        return len(self._calls)

    @property
    def last_user_prompt(self) -> str:
        return self._calls[-1].user_prompt if self._calls else ""

    async def complete_typed[T](
        self,
        prompt: PromptTemplate,
        output_type: type[T],  # noqa: ARG002
        temperature: float = 0.1,  # noqa: ARG002
        max_tokens: int = 4096,  # noqa: ARG002
    ) -> T:
        self._calls.append(prompt)
        return self._response  # type: ignore[return-value]

    async def complete(self, prompt, temperature=0.3, max_tokens=4096):  # noqa: ARG002
        from kosmo.contracts.llm.ports import LLMResponse

        return LLMResponse(text="ok")

    async def complete_json(self, prompt, temperature=0.1, max_tokens=4096):  # noqa: ARG002
        from kosmo.contracts.llm.ports import LLMResponse

        return LLMResponse(text="{}")

    @property
    def supports_native_tools(self) -> bool:
        return False

    async def complete_with_tools(
        self,
        prompt,
        tools,
        tool_handler,
        temperature=0.1,
        max_tokens=2000,  # noqa: ARG002
    ) -> tuple[str, list]:
        return ("", [])


def _user_message(content: str) -> MensajeChat:
    return MensajeChat(
        id=ChatMessageId("msg_user"),
        role=ChatRole.USER,
        content=content,
    )


# ── configuración del mode ──


@pytest.mark.unit
def test_requirements_chat_mode_output_type() -> None:
    # Arrange
    mode = _make_mode()

    # Act
    output_type = mode.output_type

    # Assert
    assert output_type is RespuestaChatLLM


@pytest.mark.unit
def test_requirements_chat_mode_phase_name() -> None:
    # Arrange
    mode = _make_mode()

    # Act
    phase = mode.phase_name

    # Assert
    assert phase == SpecPhase.REQUISITOS


@pytest.mark.unit
def test_requirements_chat_mode_config() -> None:
    # Arrange
    mode = _make_mode()

    # Act & Assert
    assert mode.temperature == 0.4
    assert mode.max_tokens == 8192
    assert mode.available_tools == []


# ── system prompt ──


@pytest.mark.unit
def test_system_prompt_contains_ears_concepts() -> None:
    # Arrange
    mode = _make_mode()

    # Act
    prompt = mode.system_prompt.lower()

    # Assert
    assert "ears" in prompt
    assert "requisito" in prompt
    assert "gherkin" in prompt or "dado-cuando-entonces" in prompt
    assert "criterio" in prompt
    assert "acceptance" in prompt or "aceptación" in prompt


@pytest.mark.unit
def test_system_prompt_contains_gherkin_format() -> None:
    # Arrange
    mode = _make_mode()

    # Act
    prompt = mode.system_prompt

    # Assert
    assert "diff_before" in prompt
    assert "diff_after" in prompt
    assert "change_suggestion" in prompt


@pytest.mark.unit
def test_system_prompt_prohibits_business_and_user_jargon() -> None:
    # Arrange
    mode = _make_mode()

    # Act
    prompt = mode.system_prompt

    # Assert
    assert "PROHIBIDO" in prompt


@pytest.mark.unit
def test_system_prompt_no_voseo() -> None:
    # Arrange
    mode = _make_mode()

    # Act
    prompt = mode.system_prompt

    # Assert
    assert "Recibís" not in prompt
    assert "Recordá" not in prompt
    assert "Mantené" not in prompt
    assert "Devolvé" not in prompt
    assert "Aplicá" not in prompt
    assert "Generá" not in prompt


# ── build_user_prompt ──


@pytest.mark.unit
def test_build_user_prompt_includes_requirement() -> None:
    # Arrange
    mode = _make_mode()
    ctx = _make_context()

    # Act
    user_prompt = mode.build_user_prompt(ctx)

    # Assert
    assert "REQ-1.1" in user_prompt
    assert "Validación de timeout en conexiones" in user_prompt
    assert "CUANDO se detecte un timeout" in user_prompt


@pytest.mark.unit
def test_build_user_prompt_includes_acceptance_criteria() -> None:
    # Arrange
    mode = _make_mode()
    ctx = _make_context()

    # Act
    user_prompt = mode.build_user_prompt(ctx)

    # Assert
    assert "Timeout detectado al enviar datos" in user_prompt
    assert "Dado" in user_prompt or "GIVEN" in user_prompt
    assert "Cuando" in user_prompt or "WHEN" in user_prompt
    assert "Entonces" in user_prompt or "THEN" in user_prompt


@pytest.mark.unit
def test_build_user_prompt_includes_feature_and_discovery() -> None:
    # Arrange
    mode = _make_mode()
    ctx = _make_context()

    # Act
    user_prompt = mode.build_user_prompt(ctx)

    # Assert
    assert "Gestión de catálogo" in user_prompt
    assert "C01" in user_prompt
    assert "Documento de descubrimiento" in user_prompt


# ── validate_output ──


@pytest.mark.unit
def test_validate_output_valid_without_suggestion() -> None:
    # Arrange
    mode = _make_mode()
    output = RespuestaChatLLM(content="El requisito REQ-1.1 ya tiene criterios adecuados.")

    # Act
    result = mode.validate_output(output)

    # Assert
    assert result.is_valid is True
    assert len(result.errors) == 0


@pytest.mark.unit
def test_validate_output_valid_with_suggestion() -> None:
    # Arrange
    mode = _make_mode()
    output = RespuestaChatLLM(
        content="He agregado un criterio de aceptación para timeout.",
        change_suggestion=SugerenciaCambioLLM(
            section="acceptance_criteria",
            description="Agregar criterio de timeout",
            diff_before="Criterios actuales sin manejo de timeout",
            diff_after="Criterios con manejo de timeout en formato Gherkin",
            rationale="El usuario solicitó cobertura de timeout.",
        ),
    )

    # Act
    result = mode.validate_output(output)

    # Assert
    assert result.is_valid is True


@pytest.mark.unit
def test_validate_output_invalid_empty_content() -> None:
    # Arrange
    mode = _make_mode()
    output = RespuestaChatLLM(content="")

    # Act
    result = mode.validate_output(output)

    # Assert
    assert result.is_valid is False
    assert any("content" in e.lower() for e in result.errors)


@pytest.mark.unit
def test_validate_output_invalid_identical_diff() -> None:
    # Arrange
    mode = _make_mode()
    output = RespuestaChatLLM(
        content="Sin cambios reales.",
        change_suggestion=SugerenciaCambioLLM(
            section="statement",
            description="Sin cambios",
            diff_before="mismo texto",
            diff_after="mismo texto",
        ),
    )

    # Act
    result = mode.validate_output(output)

    # Assert
    assert result.is_valid is False
    assert any("diff" in e.lower() for e in result.errors)


@pytest.mark.unit
def test_validate_output_invalid_empty_suggestion_fields() -> None:
    # Arrange
    mode = _make_mode()
    output = RespuestaChatLLM(
        content="Cambios.",
        change_suggestion=SugerenciaCambioLLM(
            section="",
            description="Descripcion",
            diff_before="antes",
            diff_after="despues",
        ),
    )

    # Act
    result = mode.validate_output(output)

    # Assert
    assert result.is_valid is False
    assert any("section" in e.lower() for e in result.errors)


# ── integración con KOSMOAgent ──


@pytest.mark.asyncio
@pytest.mark.unit
async def test_requirements_chat_integration_with_agent() -> None:
    # Arrange
    llm_output = RespuestaChatLLM(
        content="He agregado un criterio de aceptación para manejo de timeout en REQ-1.1.",
        change_suggestion=SugerenciaCambioLLM(
            section="acceptance_criteria",
            description="Agregar criterio de timeout",
            diff_before="Criterios existentes",
            diff_after=(
                "Dado que el sistema detecta timeout\nCuando la conexión falla\nEntonces muestra mensaje de error"
            ),
            rationale="El usuario solicitó cobertura de timeout para el requisito.",
        ),
    )
    llm = _StubChatLLM(response=llm_output)
    skill_reg = SkillRegistry()
    skill_reg.register(
        Skill(
            name="requirements_chat",
            description="Chat conversacional de requisitos EARS",
            phase=SpecPhase.REQUISITOS,
            mode=RequirementsChatMode(),  # type: ignore[reportArgumentType]
        )
    )
    agent = KOSMOAgent(
        llm_client=llm,  # type: ignore[reportArgumentType]
        skill_registry=skill_reg,
    )
    ctx = _make_context()
    messages = [_user_message("Agrega un criterio de aceptación para timeout")]

    # Act
    result = await agent.execute_conversation(
        skill_name="requirements_chat",
        messages=messages,
        context=ctx,
    )

    # Assert
    assert result.role == ChatRole.ASSISTANT
    assert result.suggested_change is not None
    assert result.suggested_change.section == "acceptance_criteria"
    assert result.suggested_change.diff.before == "Criterios existentes"
    assert result.suggested_change.diff.after == (
        "Dado que el sistema detecta timeout\nCuando la conexión falla\nEntonces muestra mensaje de error"
    )
    assert result.suggested_change.rationale == "El usuario solicitó cobertura de timeout para el requisito."
    assert str(result.suggested_change.id).startswith("chg_")
    user_prompt = llm.last_user_prompt
    assert "REQ-1.1" in user_prompt
    assert "Agrega un criterio de aceptación para timeout" in user_prompt
