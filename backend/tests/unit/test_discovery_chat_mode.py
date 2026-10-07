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
from kosmo.contracts.memory.user_preference import UserPreference
from kosmo.contracts.pipeline.orchestrator_ports import Skill
from kosmo.contracts.pipeline.phase_contexts import DiscoveryChatContext
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.domain.pipeline.phase_modes.discovery_chat_mode import DiscoveryChatMode
from kosmo.domain.pipeline.skill_registry import SkillRegistry
from kosmo.domain.sdd.document_converters import markdown_to_document
from tests.unit.conftest import DISCOVERY_VALID


def _make_document(text: str = DISCOVERY_VALID):
    return markdown_to_document(text)


def _context(document=None):
    return DiscoveryChatContext(current_document=document or _make_document())


def _mode():
    return DiscoveryChatMode()


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
def test_discovery_chat_mode_output_type() -> None:
    # Arrange
    mode = _mode()

    # Act
    output_type = mode.output_type

    # Assert
    assert output_type is RespuestaChatLLM


@pytest.mark.unit
def test_discovery_chat_mode_phase_name() -> None:
    # Arrange
    mode = _mode()

    # Act
    phase = mode.phase_name

    # Assert
    assert phase == SpecPhase.DESCUBRIMIENTO


@pytest.mark.unit
def test_discovery_chat_mode_config() -> None:
    # Arrange
    mode = _mode()

    # Act & Assert
    assert mode.temperature == 0.4
    assert mode.max_tokens == 8192
    assert mode.available_tools == []


# ── system prompt ──


@pytest.mark.unit
def test_system_prompt_contains_business_concepts() -> None:
    # Arrange
    mode = _mode()

    # Act
    prompt = mode.system_prompt

    # Assert
    assert "problema" in prompt.lower()
    assert "actor" in prompt.lower()
    assert "propuesta de valor" in prompt.lower()
    assert "meta" in prompt.lower()
    assert "regla" in prompt.lower()
    assert "alcance" in prompt.lower()
    assert "diff_before" in prompt
    assert "diff_after" in prompt
    assert "change_suggestion" in prompt


@pytest.mark.unit
def test_system_prompt_prohibits_technical_jargon() -> None:
    # Arrange
    mode = _mode()

    # Act
    prompt = mode.system_prompt

    # Assert
    assert "PROHIBIDO" in prompt
    assert "API" in prompt
    assert "base de datos" in prompt
    assert "microservicio" in prompt
    assert "endpoint" in prompt
    assert "framework" in prompt


@pytest.mark.unit
def test_system_prompt_no_voseo() -> None:
    # Arrange
    mode = _mode()

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
def test_build_user_prompt_includes_document() -> None:
    # Arrange
    mode = _mode()
    doc = _make_document()
    ctx = _context(doc)

    # Act
    user_prompt = mode.build_user_prompt(ctx)

    # Assert
    assert "Documento actual de descubrimiento" in user_prompt
    assert "producto" in user_prompt.lower()
    assert "actores" in user_prompt.lower()
    assert "propuesta de valor" in user_prompt.lower()
    assert "metas del producto" in user_prompt.lower()
    assert "reglas de negocio" in user_prompt.lower()
    assert "alcance" in user_prompt.lower()
    assert "gastos compartidos" in user_prompt.lower()


@pytest.mark.unit
def test_build_user_prompt_includes_preferences() -> None:
    # Arrange
    mode = _mode()
    ctx = DiscoveryChatContext(
        current_document=_make_document(),
        user_preferences=[
            UserPreference(id="pref1", user_id="usr_test", rule_text="Usar lenguaje inclusivo"),
            UserPreference(id="pref2", user_id="usr_test", rule_text="Evitar anglicismos"),
        ],
    )

    # Act
    user_prompt = mode.build_user_prompt(ctx)

    # Assert
    assert "Preferencias del usuario" in user_prompt
    assert "Usar lenguaje inclusivo" in user_prompt
    assert "Evitar anglicismos" in user_prompt


# ── validate_output ──


@pytest.mark.unit
def test_validate_output_valid_without_suggestion() -> None:
    # Arrange
    mode = _mode()
    output = RespuestaChatLLM(content="El alcance actual cubre viajes nacionales.")

    # Act
    result = mode.validate_output(output)

    # Assert
    assert result.is_valid is True
    assert len(result.errors) == 0


@pytest.mark.unit
def test_validate_output_valid_with_suggestion() -> None:
    # Arrange
    mode = _mode()
    output = RespuestaChatLLM(
        content="He ampliado el alcance.",
        change_suggestion=SugerenciaCambioLLM(
            section="Alcance",
            description="Ampliar a LATAM",
            diff_before="viajes nacionales",
            diff_after="viajes en LATAM",
            rationale="Solicitud del usuario",
        ),
    )

    # Act
    result = mode.validate_output(output)

    # Assert
    assert result.is_valid is True


@pytest.mark.unit
def test_validate_output_invalid_empty_content() -> None:
    # Arrange
    mode = _mode()
    output = RespuestaChatLLM(content="")

    # Act
    result = mode.validate_output(output)

    # Assert
    assert result.is_valid is False
    assert any("content" in e.lower() for e in result.errors)


@pytest.mark.unit
def test_validate_output_invalid_identical_diff() -> None:
    # Arrange
    mode = _mode()
    output = RespuestaChatLLM(
        content="Modifiqué la seccion.",
        change_suggestion=SugerenciaCambioLLM(
            section="Alcance",
            description="Sin cambios reales",
            diff_before="viajes nacionales",
            diff_after="viajes nacionales",
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
    mode = _mode()
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


# ── integración T5 + T6 ──


@pytest.mark.asyncio
@pytest.mark.unit
async def test_discovery_chat_integration_with_agent() -> None:
    # Arrange
    llm_output = RespuestaChatLLM(
        content="He actualizado la vision del producto para enfocarse en LATAM.",
        change_suggestion=SugerenciaCambioLLM(
            section="Vision del producto",
            description="Enfocar vision en LATAM",
            diff_before="viajes nacionales",
            diff_after="viajes en la region LATAM",
            rationale="El usuario solicito expansion geografica.",
        ),
    )
    llm = _StubChatLLM(response=llm_output)
    skill_reg = SkillRegistry()
    skill_reg.register(
        Skill(
            name="discovery_chat",
            description="Chat conversacional de descubrimiento",
            phase=SpecPhase.DESCUBRIMIENTO,
            mode=DiscoveryChatMode(),  # type: ignore[reportArgumentType]
        )
    )
    agent = KOSMOAgent(
        llm_client=llm,  # type: ignore[reportArgumentType]
        skill_registry=skill_reg,
    )
    ctx = _context()
    messages = [_user_message("Enfoca la vision del producto en LATAM")]

    # Act
    result = await agent.execute_conversation(
        skill_name="discovery_chat",
        messages=messages,
        context=ctx,
    )

    # Assert
    assert result.role == ChatRole.ASSISTANT
    assert result.suggested_change is not None
    assert result.suggested_change.section == "Vision del producto"
    assert result.suggested_change.diff.before == "viajes nacionales"
    assert result.suggested_change.diff.after == "viajes en la region LATAM"
    assert result.suggested_change.rationale == "El usuario solicito expansion geografica."
    assert str(result.suggested_change.id).startswith("chg_")
    user_prompt = llm.last_user_prompt
    assert "Documento actual de descubrimiento" in user_prompt
    assert "Enfoca la vision del producto en LATAM" in user_prompt
