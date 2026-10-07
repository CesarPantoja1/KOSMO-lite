from datetime import UTC, datetime

import pytest

from kosmo.contracts import (
    AppliedChange,
    ChatHistoryId,
    ChatMessageId,
    ChatRepository,
    ChatRole,
    DiffCambio,
    HistorialChat,
    MensajeChat,
    SugerenciaCambio,
)
from kosmo.contracts.ai.chat import ChatSession, ChatSessionSummary
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.ids import ChatSessionId, ProjectId


def test_mensaje_chat_creation_without_suggested_change():
    msg = MensajeChat(
        id=ChatMessageId("msg_001"),
        role=ChatRole.USER,
        content="Amplía el alcance a LATAM",
    )

    assert msg.id == "msg_001"
    assert msg.role == ChatRole.USER
    assert msg.role == "user"
    assert msg.content == "Amplía el alcance a LATAM"
    assert msg.suggested_change is None
    assert isinstance(msg.timestamp, datetime)
    assert msg.timestamp.tzinfo == UTC


def test_mensaje_chat_creation_with_suggested_change():
    diff = DiffCambio(
        before="viajes nacionales dentro del país",
        after="viajes y vuelos dentro de la región LATAM",
    )
    sugerencia = SugerenciaCambio(
        id="chg_01KT",
        section="2 Alcance del producto",
        description="Ampliar alcance de 'nacionales' a 'LATAM'",
        diff=diff,
    )
    msg = MensajeChat(
        id=ChatMessageId("msg_002"),
        role=ChatRole.ASSISTANT,
        content="He ampliado la sección de alcance.",
        suggested_change=sugerencia,
    )

    assert msg.id == "msg_002"
    assert msg.role == ChatRole.ASSISTANT
    assert msg.suggested_change is not None
    assert msg.suggested_change.id == "chg_01KT"
    assert msg.suggested_change.section == "2 Alcance del producto"
    assert msg.suggested_change.diff.before == "viajes nacionales dentro del país"
    assert msg.suggested_change.diff.after == "viajes y vuelos dentro de la región LATAM"


def test_mensaje_chat_immutability():
    msg = MensajeChat(
        id=ChatMessageId("msg_003"),
        role=ChatRole.SYSTEM,
        content="Contexto del sistema inicializado",
    )

    with pytest.raises(AttributeError):
        msg.content = "Nuevo contenido"  # type: ignore[misc]


def test_applied_change_values_and_immutability():
    diff = DiffCambio(before="nacional", after="LATAM")
    change = AppliedChange(
        id="chg_100",
        section="2 Alcance del producto",
        description="Ampliar alcance a LATAM",
        diff=diff,
        rationale="Solicitud del usuario",
    )

    assert change.id == "chg_100"
    assert change.section == "2 Alcance del producto"
    assert change.description == "Ampliar alcance a LATAM"
    assert change.diff.before == "nacional"
    assert change.diff.after == "LATAM"
    assert change.rationale == "Solicitud del usuario"

    with pytest.raises(AttributeError):
        change.section = "Otro"  # type: ignore[misc]


def test_applied_change_defaults():
    change = AppliedChange(
        id="chg_101",
        section="3 Monedas",
        diff=DiffCambio(before="v1", after="v2"),
    )

    assert change.description == ""
    assert change.rationale is None


def test_historial_chat_empty_and_add_message():
    historial = HistorialChat(
        id=ChatHistoryId("discovery:prj_001"),
        project_id=ProjectId("prj_001"),
        phase=SpecPhase.DESCUBRIMIENTO,
    )

    assert historial.id == "discovery:prj_001"
    assert historial.project_id == "prj_001"
    assert historial.phase == SpecPhase.DESCUBRIMIENTO
    assert historial.context_id is None
    assert historial.message_count == 0
    assert historial.last_message is None

    msg1 = MensajeChat(
        id=ChatMessageId("msg_1"),
        role=ChatRole.USER,
        content="Hola",
    )
    historial2 = historial.add_message(msg1)

    # Inmutabilidad
    assert historial.message_count == 0
    assert historial2.message_count == 1
    assert historial2.last_message == msg1

    msg2 = MensajeChat(
        id=ChatMessageId("msg_2"),
        role=ChatRole.ASSISTANT,
        content="¿En qué puedo ayudarte?",
    )
    historial3 = historial2.add_message(msg2)

    assert historial3.message_count == 2
    assert historial3.last_message == msg2
    assert historial3.messages == (msg1, msg2)
    assert historial3.composite_key == "prj_001:descubrimiento:"


def test_historial_chat_with_feature_context():
    historial = HistorialChat(
        id=ChatHistoryId("feature:feat_001"),
        project_id=ProjectId("prj_001"),
        phase=SpecPhase.CARACTERISTICAS,
        context_id="feat_001",
    )

    assert historial.id == "feature:feat_001"
    assert historial.project_id == "prj_001"
    assert historial.phase == SpecPhase.CARACTERISTICAS
    assert historial.context_id == "feat_001"
    assert historial.composite_key == "prj_001:caracteristicas:feat_001"


class FakeChatRepository:
    def __init__(self) -> None:
        self.messages: list[MensajeChat] = []

    async def save_message(
        self,
        project_id: ProjectId,
        phase: SpecPhase,
        message: MensajeChat,
        context_id: str | None = None,
    ) -> MensajeChat:
        self.messages.append(message)
        return message

    async def get_history(
        self,
        project_id: ProjectId,
        phase: SpecPhase,
        context_id: str | None = None,
    ) -> HistorialChat | None:
        return HistorialChat(
            id=ChatHistoryId(f"{phase}:{project_id}"),
            project_id=project_id,
            phase=phase,
            context_id=context_id,
            messages=tuple(self.messages),
        )

    async def create_session(self, session: ChatSession) -> ChatSession:
        return session

    async def delete_session(self, session_id: ChatSessionId, project_id: ProjectId) -> bool:  # noqa: ARG002
        return True

    async def list_sessions(
        self,
        project_id: ProjectId,  # noqa: ARG002
        phase: SpecPhase,  # noqa: ARG002
        *,
        context_id: str | None = None,  # noqa: ARG002
        limit: int = 100,  # noqa: ARG002
    ) -> list[ChatSessionSummary]:
        return []


@pytest.mark.asyncio
async def test_chat_repository_protocol_implementation():
    repo: ChatRepository = FakeChatRepository()
    project_id = ProjectId("prj_test")

    msg = MensajeChat(
        id=ChatMessageId("msg_10"),
        role=ChatRole.USER,
        content="Ampliar alcance",
    )
    saved_msg = await repo.save_message(project_id, SpecPhase.DESCUBRIMIENTO, msg)
    assert saved_msg.id == "msg_10"

    history = await repo.get_history(project_id, SpecPhase.DESCUBRIMIENTO)
    assert history is not None
    assert history.message_count == 1
