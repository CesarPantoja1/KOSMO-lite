from __future__ import annotations

import asyncio
from collections.abc import Callable
from types import TracebackType

import pytest

from kosmo.infrastructure.persistence.postgres.models import OutboxJobModel
from kosmo.infrastructure.persistence.postgres.outbox import OutboxStore
from kosmo.infrastructure.persistence.postgres.repositories.activity_diagram_repo import (
    SqlAlchemyActivityDiagramRepository,
)
from kosmo.infrastructure.persistence.postgres.repositories.chat_repo import SqlAlchemyChatRepository
from kosmo.infrastructure.persistence.postgres.repositories.document_repo import SqlAlchemyDocumentRepository
from kosmo.infrastructure.persistence.postgres.repositories.feature_repo import SqlAlchemyFeatureRepository
from kosmo.infrastructure.persistence.postgres.repositories.project_repo import SqlAlchemyProjectRepository
from kosmo.infrastructure.persistence.postgres.repositories.requirement_repo import SqlAlchemyRequirementRepository
from kosmo.infrastructure.persistence.postgres.repositories.traceability_repo import (
    SqlAlchemyTraceabilityRepository,
)
from kosmo.infrastructure.persistence.postgres.uow import SqlAlchemyUnitOfWork
from tests.unit.fakes import (
    InMemoryChatRepository,
    InMemoryDocumentRepository,
    InMemoryProjectRepository,
    InMemoryUnitOfWork,
)


class _RecordingSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0
        self.added: list[object] = []

    async def __aenter__(self) -> _RecordingSession:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def close(self) -> None:
        self.closed += 1

    async def execute(self, *args: object) -> None:  # noqa: ARG002
        return None

    def add(self, obj: object) -> None:
        self.added.append(obj)


def _make_factory() -> tuple[list[_RecordingSession], Callable[[], _RecordingSession]]:
    sessions: list[_RecordingSession] = []

    def factory() -> _RecordingSession:
        session = _RecordingSession()
        sessions.append(session)
        return session

    return sessions, factory


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uow_commits_once_on_clean_exit() -> None:
    # Arrange
    sessions, factory = _make_factory()
    uow = SqlAlchemyUnitOfWork(session_factory=factory)

    # Act
    async with uow:
        pass

    # Assert
    assert len(sessions) == 1
    assert sessions[0].commits == 1
    assert sessions[0].rollbacks == 0
    assert sessions[0].closed == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uow_rolls_back_on_exception() -> None:
    # Arrange
    sessions, factory = _make_factory()
    uow = SqlAlchemyUnitOfWork(session_factory=factory)

    # Act & Assert
    with pytest.raises(RuntimeError, match="fallo esperado"):
        async with uow:
            raise RuntimeError("fallo esperado")

    # Assert
    assert sessions[0].commits == 0
    assert sessions[0].rollbacks == 1
    assert sessions[0].closed == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uow_creates_fresh_session_per_enter_and_binds_repos() -> None:
    # Arrange
    sessions, factory = _make_factory()
    uow = SqlAlchemyUnitOfWork(session_factory=factory)

    # Act
    async with uow:
        first_repos = uow.projects
        await uow.commit()
    async with uow:
        second_repos = uow.projects
        docs = uow.documents
        features = uow.features
        requirements = uow.requirements
        diagrams = uow.diagrams
        chat = uow.chat
        traceability = uow.traceability

    # Assert
    assert len(sessions) == 2
    assert sessions[0].commits == 2
    assert sessions[1].closed == 1
    assert first_repos is not second_repos
    assert isinstance(first_repos, SqlAlchemyProjectRepository)
    assert isinstance(docs, SqlAlchemyDocumentRepository)
    assert isinstance(features, SqlAlchemyFeatureRepository)
    assert isinstance(requirements, SqlAlchemyRequirementRepository)
    assert isinstance(diagrams, SqlAlchemyActivityDiagramRepository)
    assert isinstance(chat, SqlAlchemyChatRepository)
    assert isinstance(traceability, SqlAlchemyTraceabilityRepository)

    with pytest.raises(ValueError, match="Unit of Work no activo"):
        _ = uow.projects


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uow_concurrent_tasks_isolate_sessions_and_repos() -> None:
    # Arrange
    sessions, factory = _make_factory()
    uow = SqlAlchemyUnitOfWork(session_factory=factory)

    async def worker(worker_id: int) -> tuple[int, SqlAlchemyProjectRepository]:
        async with uow:
            repo = uow.projects
            assert isinstance(repo, SqlAlchemyProjectRepository)
            await asyncio.sleep(0.01)
            await uow.commit()
            return worker_id, repo

    # Act
    results = await asyncio.gather(worker(1), worker(2), worker(3))

    # Assert
    assert len(sessions) == 3
    for s in sessions:
        assert s.commits == 2
        assert s.closed == 1
    repos = [r for _, r in results]
    assert len(set(repos)) == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uow_outbox_enqueue_shares_transaction() -> None:
    # Arrange
    sessions, factory = _make_factory()
    uow = SqlAlchemyUnitOfWork(session_factory=factory)

    # Act
    async with uow:
        await uow.outbox.enqueue("reflect_and_consolidate", {"session_id": "agm_test"})

    # Assert: la fila se agrego a la sesion del uow y el commit es unico
    assert len(sessions[0].added) == 1
    assert sessions[0].commits == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_outbox_enqueue_bound_does_not_commit() -> None:
    # Arrange
    session = _RecordingSession()
    outbox = OutboxStore(session=session)

    # Act
    await outbox.enqueue("reflect_and_consolidate", {"session_id": "agm_test"})

    # Assert
    assert session.commits == 0
    assert len(session.added) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_outbox_enqueue_standalone_commits() -> None:
    # Arrange
    sessions, factory = _make_factory()
    outbox = OutboxStore(session_factory=factory)

    # Act
    await outbox.enqueue("reflect_and_consolidate", {"session_id": "agm_test"})

    # Assert
    assert len(sessions) == 1
    assert sessions[0].commits == 1
    assert sessions[0].closed == 1
    assert len(sessions[0].added) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_in_memory_uow_exposes_fakes_and_noop_transaction() -> None:
    # Arrange
    projects = InMemoryProjectRepository()
    documents = InMemoryDocumentRepository()
    chat = InMemoryChatRepository()
    uow = InMemoryUnitOfWork(projects=projects, documents=documents, chat=chat)

    # Act
    async with uow as active:
        await active.commit()
        await active.rollback()

    # Assert
    assert uow.projects is projects
    assert uow.documents is documents
    assert uow.chat is chat
    assert active is uow


@pytest.mark.unit
def test_outbox_job_model_defines_composite_index() -> None:
    # Arrange & Act
    indexes = {idx.name: tuple(col.name for col in idx.columns) for idx in OutboxJobModel.__table__.indexes}

    # Assert
    assert "ix_outbox_pending" in indexes
    assert indexes["ix_outbox_pending"] == ("status", "created_at")
