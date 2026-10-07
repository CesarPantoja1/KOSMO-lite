from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kosmo.infrastructure.persistence.postgres.models import TraceabilityEdgeModel
from kosmo.infrastructure.persistence.postgres.repositories.traceability_repo import (
    SqlAlchemyTraceabilityRepository,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_by_entity_id_executes_bulk_delete_and_commits() -> None:
    # Arrange
    mock_session = MagicMock(spec=AsyncSession)
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.delete = AsyncMock()

    mock_session_factory = MagicMock(spec=async_sessionmaker)
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    repo = SqlAlchemyTraceabilityRepository(session_factory=mock_session_factory)

    # Act
    await repo.delete_by_entity_id("feat_123")

    # Assert: solo 1 execute con delete bulk, y NUNCA session.delete fila por fila (cero N+1)
    mock_session.execute.assert_awaited_once()
    mock_session.delete.assert_not_called()
    mock_session.commit.assert_awaited_once()

    stmt = mock_session.execute.call_args[0][0]
    assert stmt.is_delete
    assert stmt.table.name == TraceabilityEdgeModel.__tablename__


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_by_entity_id_with_direct_session_does_not_commit() -> None:
    # Arrange: en contexto UoW donde la sesion se pasa externamente
    mock_session = MagicMock(spec=AsyncSession)
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    repo = SqlAlchemyTraceabilityRepository(session=mock_session)

    # Act
    await repo.delete_by_entity_id("req_456")

    # Assert
    mock_session.execute.assert_awaited_once()
    mock_session.commit.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_impact_batch_executes_single_query_and_maps_both_directions() -> None:
    # Arrange
    edge1 = MagicMock()
    edge1.source_type = "feature"
    edge1.source_id = "feat_01"
    edge1.target_type = "requirement"
    edge1.target_id = "req_01"
    edge1.origin = "llm"

    edge2 = MagicMock()
    edge2.source_type = "requirement"
    edge2.source_id = "req_01"
    edge2.target_type = "code"
    edge2.target_id = "src/app/page.tsx"
    edge2.origin = "llm"

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [edge1, edge2]

    mock_session = MagicMock(spec=AsyncSession)
    mock_session.execute = AsyncMock(return_value=mock_result)

    repo = SqlAlchemyTraceabilityRepository(session=mock_session)

    # Act: resolve impact for feat_01 and req_01 simultaneously in 1 batch call
    impacts = await repo.get_impact_batch(["feat_01", "req_01"])

    # Assert: EXACTLY 1 execute call (zero N+1)
    mock_session.execute.assert_awaited_once()

    # feat_01 has downstream edge to req_01
    assert impacts["feat_01"]["downstream"] == [{"type": "requirement", "id": "req_01", "origin": "llm"}]
    assert impacts["feat_01"]["upstream"] == []

    # req_01 has upstream edge from feat_01, and downstream edge to src/app/page.tsx
    assert impacts["req_01"]["upstream"] == [{"type": "feature", "id": "feat_01", "origin": "llm"}]
    assert impacts["req_01"]["downstream"] == [{"type": "code", "id": "src/app/page.tsx", "origin": "llm"}]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_impact_batch_empty_list_returns_empty_dict_without_db_query() -> None:
    mock_session = MagicMock(spec=AsyncSession)
    mock_session.execute = AsyncMock()

    repo = SqlAlchemyTraceabilityRepository(session=mock_session)

    result = await repo.get_impact_batch([])

    assert result == {}
    mock_session.execute.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_impact_delegates_to_get_impact_batch() -> None:
    edge = MagicMock()
    edge.source_type = "feature"
    edge.source_id = "feat_01"
    edge.target_type = "requirement"
    edge.target_id = "req_01"
    edge.origin = "llm"

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [edge]

    mock_session = MagicMock(spec=AsyncSession)
    mock_session.execute = AsyncMock(return_value=mock_result)

    repo = SqlAlchemyTraceabilityRepository(session=mock_session)

    impact = await repo.get_impact("req_01")

    mock_session.execute.assert_awaited_once()
    assert impact["upstream"] == [{"type": "feature", "id": "feat_01", "origin": "llm"}]
    assert impact["downstream"] == []
