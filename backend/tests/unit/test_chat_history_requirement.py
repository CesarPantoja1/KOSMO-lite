import pytest

from kosmo.contracts import ChatHistoryId, ChatMessageId, ChatRole, HistorialChat, MensajeChat
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.ids import ProjectId
from tests.factories import a_requirement_id


@pytest.mark.unit
def test_historial_chat_creation_with_requirement_context():
    # Arrange
    requirement_id = "req_01KT01FABRICATED01"

    # Act
    historial = HistorialChat(
        id=ChatHistoryId("chh_01KT01FABRICATED01"),
        project_id=ProjectId("prj_01KT01FABRICATED01"),
        phase=SpecPhase.REQUISITOS,
        context_id=requirement_id,
    )

    # Assert
    assert historial.id == "chh_01KT01FABRICATED01"
    assert historial.project_id == "prj_01KT01FABRICATED01"
    assert historial.phase == SpecPhase.REQUISITOS
    assert historial.phase == "requisitos"
    assert historial.context_id == requirement_id
    assert historial.message_count == 0
    assert historial.last_message is None


@pytest.mark.unit
def test_historial_chat_requirement_composite_key():
    # Arrange
    requirement_id = a_requirement_id()

    # Act
    historial = HistorialChat(
        id=ChatHistoryId("chh_001"),
        project_id=ProjectId("prj_001"),
        phase=SpecPhase.REQUISITOS,
        context_id=requirement_id,
    )

    # Assert
    expected = f"prj_001:requisitos:{requirement_id}"
    assert historial.composite_key == expected


@pytest.mark.unit
def test_historial_chat_requirement_no_context_composite_key():
    # Arrange / Act
    historial = HistorialChat(
        id=ChatHistoryId("chh_001"),
        project_id=ProjectId("prj_001"),
        phase=SpecPhase.REQUISITOS,
    )

    # Assert
    assert historial.composite_key == "prj_001:requisitos:"


@pytest.mark.unit
def test_requirement_isolation_via_composite_key():
    # Arrange
    req_a = "req_01KT01FABRICATED01"
    req_b = "req_01KT01FABRICATED02"

    # Act
    historial_a = HistorialChat(
        id=ChatHistoryId("chh_a"),
        project_id=ProjectId("prj_001"),
        phase=SpecPhase.REQUISITOS,
        context_id=req_a,
    )
    historial_b = HistorialChat(
        id=ChatHistoryId("chh_b"),
        project_id=ProjectId("prj_001"),
        phase=SpecPhase.REQUISITOS,
        context_id=req_b,
    )

    # Assert
    assert historial_a.composite_key != historial_b.composite_key
    assert historial_a.composite_key == f"prj_001:requisitos:{req_a}"
    assert historial_b.composite_key == f"prj_001:requisitos:{req_b}"


@pytest.mark.unit
def test_requirement_vs_feature_context_isolation():
    # Arrange
    feature_id = "feat_001"
    requirement_id = "req_001"

    # Act
    feature_history = HistorialChat(
        id=ChatHistoryId("chh_f"),
        project_id=ProjectId("prj_001"),
        phase=SpecPhase.CARACTERISTICAS,
        context_id=feature_id,
    )
    requirement_history = HistorialChat(
        id=ChatHistoryId("chh_r"),
        project_id=ProjectId("prj_001"),
        phase=SpecPhase.REQUISITOS,
        context_id=requirement_id,
    )

    # Assert
    assert feature_history.composite_key != requirement_history.composite_key
    assert "caracteristicas" in feature_history.composite_key
    assert "requisitos" in requirement_history.composite_key


@pytest.mark.unit
def test_requirement_messages_preserve_context():
    # Arrange
    requirement_id = "req_01KT01FABRICATED01"
    historial = HistorialChat(
        id=ChatHistoryId("chh_001"),
        project_id=ProjectId("prj_001"),
        phase=SpecPhase.REQUISITOS,
        context_id=requirement_id,
    )

    msg = MensajeChat(
        id=ChatMessageId("msg_001"),
        role=ChatRole.USER,
        content="Agrega criterio de aceptación para timeout",
    )

    # Act
    historial_updated = historial.add_message(msg)

    # Assert
    assert historial.message_count == 0
    assert historial_updated.message_count == 1
    assert historial_updated.last_message == msg
    assert historial_updated.context_id == requirement_id
    assert historial_updated.phase == SpecPhase.REQUISITOS


@pytest.mark.unit
@pytest.mark.asyncio
async def test_inmemory_chat_repository_requirement_isolation():
    # Arrange
    from tests.unit.fakes import InMemoryChatRepository

    repo = InMemoryChatRepository()
    project_id = ProjectId("prj_001")
    req_a = "req_01KT01FABRICATED01"
    req_b = "req_01KT01FABRICATED02"

    msg_a = MensajeChat(
        id=ChatMessageId("msg_a"),
        role=ChatRole.USER,
        content="Mensaje para requisito A",
    )
    msg_b = MensajeChat(
        id=ChatMessageId("msg_b"),
        role=ChatRole.USER,
        content="Mensaje para requisito B",
    )

    # Act
    await repo.save_message(project_id, SpecPhase.REQUISITOS, msg_a, context_id=req_a)
    await repo.save_message(project_id, SpecPhase.REQUISITOS, msg_b, context_id=req_b)

    history_a = await repo.get_history(project_id, SpecPhase.REQUISITOS, context_id=req_a)
    history_b = await repo.get_history(project_id, SpecPhase.REQUISITOS, context_id=req_b)

    # Assert
    assert history_a is not None
    assert history_b is not None
    assert history_a.message_count == 1
    assert history_b.message_count == 1
    assert history_a.last_message.content == "Mensaje para requisito A"  # type: ignore[union-attr]
    assert history_b.last_message.content == "Mensaje para requisito B"  # type: ignore[union-attr]
    assert history_a.composite_key != history_b.composite_key


@pytest.mark.unit
def test_requirement_context_does_not_affect_other_phases():
    # Arrange
    discovery = HistorialChat(
        id=ChatHistoryId("chh_d"),
        project_id=ProjectId("prj_001"),
        phase=SpecPhase.DESCUBRIMIENTO,
    )
    requirements = HistorialChat(
        id=ChatHistoryId("chh_r"),
        project_id=ProjectId("prj_001"),
        phase=SpecPhase.REQUISITOS,
        context_id="req_001",
    )
    features = HistorialChat(
        id=ChatHistoryId("chh_f"),
        project_id=ProjectId("prj_001"),
        phase=SpecPhase.CARACTERISTICAS,
        context_id="feat_001",
    )

    # Assert
    keys = {discovery.composite_key, requirements.composite_key, features.composite_key}
    assert len(keys) == 3
