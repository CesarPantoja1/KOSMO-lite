from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kosmo.contracts.ai.consistency import (
    ConsistencyEvaluation,
    ConsistencyEvaluationStatus,
)
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.ids import ConsistencyEvaluationId, ProjectId
from kosmo.infrastructure.persistence.postgres.models import ConsistencyEvaluationModel
from kosmo.infrastructure.persistence.postgres.repositories.consistency_repo import (
    SqlAlchemyConsistencyEvaluationRepository,
)


def _make_evaluation(
    eval_id: str = "eval_01",
    project_id: str = "proj_01",
) -> ConsistencyEvaluation:
    now = datetime.now(UTC)
    return ConsistencyEvaluation(
        id=ConsistencyEvaluationId(eval_id),
        project_id=ProjectId(project_id),
        source_phase=SpecPhase.REQUISITOS,
        target_phase=SpecPhase.MODELO,
        target_artifact_id="art_01",
        artifact_type="feature",
        snapshot_hash="hash123",
        status=ConsistencyEvaluationStatus.COMPLETED,
        result={"summary": "impact detected"},
        source_changes=[],
        created_at=now,
        updated_at=now,
    )


def _make_async_session_mock(
    returned_model: ConsistencyEvaluationModel | None = None,
) -> MagicMock:
    mock_session = MagicMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = returned_model
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()
    return mock_session


@pytest.mark.unit
def test_init_requires_session_factory_or_session() -> None:
    with pytest.raises(ValueError, match="Se requiere session_factory o session"):
        SqlAlchemyConsistencyEvaluationRepository()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_by_project_executes_delete_and_commits() -> None:
    # Arrange
    mock_session = _make_async_session_mock()
    mock_session_factory = MagicMock(spec=async_sessionmaker)
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    repo = SqlAlchemyConsistencyEvaluationRepository(session_factory=mock_session_factory)

    # Act
    await repo.delete_by_project(ProjectId("proj_01"))

    # Assert
    mock_session.execute.assert_awaited_once()
    mock_session.commit.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_by_project_with_bound_session_does_not_commit() -> None:
    # Arrange (Unit of work: bound session delegates transaction control to caller)
    mock_session = _make_async_session_mock()
    repo = SqlAlchemyConsistencyEvaluationRepository(session=mock_session)

    # Act
    await repo.delete_by_project(ProjectId("proj_01"))

    # Assert
    mock_session.execute.assert_awaited_once()
    mock_session.commit.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_save_inserts_and_commits() -> None:
    # Arrange
    evaluation = _make_evaluation()
    mock_session = _make_async_session_mock(returned_model=None)
    mock_session_factory = MagicMock(spec=async_sessionmaker)
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    repo = SqlAlchemyConsistencyEvaluationRepository(session_factory=mock_session_factory)

    # Act
    result = await repo.save(evaluation)

    # Assert
    assert result.id == evaluation.id
    mock_session.add.assert_called_once()
    mock_session.commit.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_save_with_bound_session_does_not_commit() -> None:
    # Arrange
    evaluation = _make_evaluation()
    mock_session = _make_async_session_mock(returned_model=None)
    repo = SqlAlchemyConsistencyEvaluationRepository(session=mock_session)

    # Act
    result = await repo.save(evaluation)

    # Assert
    assert result.id == evaluation.id
    mock_session.commit.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_by_id_returns_none_when_not_found() -> None:
    # Arrange
    mock_session = _make_async_session_mock(returned_model=None)
    repo = SqlAlchemyConsistencyEvaluationRepository(session=mock_session)

    # Act
    result = await repo.by_id(ConsistencyEvaluationId("eval_none"))

    # Assert
    assert result is None
