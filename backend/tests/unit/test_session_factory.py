from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.ids import ProjectId
from kosmo.domain.agent_memory.session_factory import create_session, generate_session_id
from tests.factories import a_session


@pytest.mark.unit
class TestGenerateSessionId:
    @pytest.mark.unit
    def test_generates_unique_ids(self) -> None:
        # Arrange / Act
        id1 = generate_session_id()
        id2 = generate_session_id()

        # Assert
        assert id1 != id2
        assert id1.startswith("agm_")
        assert id2.startswith("agm_")


@pytest.mark.unit
class TestCreateSession:
    @pytest.mark.unit
    def test_session_is_immutable(self) -> None:
        # Arrange
        session = a_session()

        # Act & Assert
        with pytest.raises(FrozenInstanceError):
            session.is_completed = True  # type: ignore[misc]

    @pytest.mark.unit
    def test_conversation_default_is_distinct_per_instance(self) -> None:
        # Act
        s1 = create_session(
            project_id=ProjectId("prj_01KT01ABC"),
            session_type="generation",
            phase=SpecPhase.DESCUBRIMIENTO,
        )
        s2 = create_session(
            project_id=ProjectId("prj_01KT01DEF"),
            session_type="refinement",
            phase=SpecPhase.REQUISITOS,
        )

        # Assert
        assert s1.conversation is not s2.conversation

    @pytest.mark.unit
    def test_create_session_with_injected_now(self) -> None:
        from datetime import UTC, datetime

        fixed_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        session = create_session(
            project_id=ProjectId("prj_01KT01ABC"),
            session_type="generation",
            phase=SpecPhase.DESCUBRIMIENTO,
            now=fixed_time,
        )
        assert session.created_at == fixed_time
        assert session.updated_at == fixed_time
