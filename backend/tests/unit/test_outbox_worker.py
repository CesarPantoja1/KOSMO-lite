from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from kosmo.infrastructure.persistence.postgres.models import OutboxJobModel
from kosmo.infrastructure.persistence.postgres.outbox import OutboxStore, run_outbox_worker


class _MockOutboxStore:
    def __init__(self, jobs: list[OutboxJobModel]) -> None:
        self._jobs: dict[str, OutboxJobModel] = {j.id: j for j in jobs}
        self.done: list[str] = []
        self.failed: list[tuple[str, str | None]] = []
        self.dead: list[str] = []

    async def dequeue(self, *, max_attempts: int = 3) -> OutboxJobModel | None:
        for job in self._jobs.values():
            if job.status == "pending" or (job.status == "failed" and (job.attempts or 0) < max_attempts):
                job.status = "processing"
                job.attempts = (job.attempts or 0) + 1
                return job
        return None

    async def mark_done(self, job_id: str) -> None:
        if job_id in self._jobs:
            self._jobs[job_id].status = "done"
        self.done.append(job_id)

    async def mark_failed(
        self,
        job_id: str,
        *,
        error: str | None = None,
        max_attempts: int = 3,
    ) -> None:
        if job_id in self._jobs:
            job = self._jobs[job_id]
            if (job.attempts or 0) >= max_attempts:
                job.status = "dead"
                self.dead.append(job_id)
            else:
                job.status = "failed"
        self.failed.append((job_id, error))


@pytest.mark.asyncio
@pytest.mark.unit
async def test_outbox_worker_processes_jobs_concurrently() -> None:
    jobs = [
        OutboxJobModel(id=f"job_{i}", job_type="test_task", payload={"idx": i}, attempts=0, status="pending")
        for i in range(4)
    ]
    store = _MockOutboxStore(jobs)

    active_concurrency: list[int] = []
    current_active = 0
    lock = asyncio.Lock()

    async def handler(_job_type: str, _payload: dict[str, Any]) -> None:
        nonlocal current_active
        async with lock:
            current_active += 1
            active_concurrency.append(current_active)
        await asyncio.sleep(0.05)
        async with lock:
            current_active -= 1

    worker_task = asyncio.create_task(
        run_outbox_worker(
            store=store,  # type: ignore[arg-type]
            handler=handler,
            poll_interval=0.01,
            max_concurrency=4,
        )
    )

    for _ in range(50):
        if len(store.done) == 4:
            break
        await asyncio.sleep(0.02)

    worker_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await worker_task

    assert len(store.done) == 4
    assert max(active_concurrency) >= 2


@pytest.mark.asyncio
@pytest.mark.unit
async def test_outbox_worker_handles_job_failure() -> None:
    job = OutboxJobModel(id="job_fail", job_type="failing_task", payload={}, attempts=0, status="pending")
    store = _MockOutboxStore([job])

    async def handler(_job_type: str, _payload: dict[str, Any]) -> None:
        raise ValueError("Simulated handler crash")

    worker_task = asyncio.create_task(
        run_outbox_worker(
            store=store,  # type: ignore[arg-type]
            handler=handler,
            poll_interval=0.01,
            max_concurrency=2,
        )
    )

    for _ in range(30):
        if len(store.failed) == 1:
            break
        await asyncio.sleep(0.02)

    worker_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await worker_task

    assert len(store.failed) >= 1
    assert store.failed[0][0] == "job_fail"
    assert "ValueError" in (store.failed[0][1] or "")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_outbox_worker_retries_failed_job_until_success() -> None:
    # Arrange: un job que falla en el primer intento y tiene éxito en el segundo
    job = OutboxJobModel(id="job_retry", job_type="transient_task", payload={}, attempts=0, status="pending")
    store = _MockOutboxStore([job])
    call_count = 0

    async def handler(_job_type: str, _payload: dict[str, Any]) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Fallo transitorio de conexion")

    # Act
    worker_task = asyncio.create_task(
        run_outbox_worker(
            store=store,  # type: ignore[arg-type]
            handler=handler,
            poll_interval=0.01,
            max_attempts=3,
            max_concurrency=1,
        )
    )

    for _ in range(50):
        if len(store.done) == 1:
            break
        await asyncio.sleep(0.02)

    worker_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await worker_task

    # Assert: El job fue reintentado y finalmente marcado como done
    assert call_count == 2
    assert len(store.failed) == 1
    assert len(store.done) == 1
    assert store.done[0] == "job_retry"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_outbox_worker_retries_until_dead_when_all_attempts_fail() -> None:
    # Arrange: un job que siempre falla hasta agotar max_attempts=2
    job = OutboxJobModel(id="job_perm_fail", job_type="permanent_fail", payload={}, attempts=0, status="pending")
    store = _MockOutboxStore([job])

    async def handler(_job_type: str, _payload: dict[str, Any]) -> None:
        raise ValueError("Error no recuperable")

    # Act
    worker_task = asyncio.create_task(
        run_outbox_worker(
            store=store,  # type: ignore[arg-type]
            handler=handler,
            poll_interval=0.01,
            max_attempts=2,
            max_concurrency=1,
        )
    )

    for _ in range(50):
        if len(store.dead) == 1:
            break
        await asyncio.sleep(0.02)

    worker_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await worker_task

    # Assert: El job se reintento hasta max_attempts=2 y paso a dead
    assert len(store.dead) == 1
    assert store.dead[0] == "job_perm_fail"
    assert len(store.done) == 0


@pytest.mark.asyncio
@pytest.mark.unit
async def test_outbox_store_dequeue_updates_model_status_and_attempts() -> None:
    # Arrange
    job_model = OutboxJobModel(id="job_sql", job_type="task", payload={}, attempts=0, status="pending")
    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = job_model
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()

    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    store = OutboxStore(session_factory=mock_factory)

    # Act
    dequeued = await store.dequeue()

    # Assert
    assert dequeued is job_model
    assert dequeued.status == "processing"
    assert dequeued.attempts == 1
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_outbox_store_mark_failed_sets_status_failed_and_dead() -> None:
    # Arrange 1: attempts < max_attempts -> status="failed"
    job_retryable = OutboxJobModel(id="job_f1", job_type="task", payload={}, attempts=1, status="processing")
    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = job_retryable
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()

    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    store = OutboxStore(session_factory=mock_factory)

    await store.mark_failed("job_f1", error="Network error", max_attempts=3)
    assert job_retryable.status == "failed"
    assert job_retryable.last_error == "Network error"

    # Arrange 2: attempts >= max_attempts -> status="dead"
    job_exhausted = OutboxJobModel(id="job_f2", job_type="task", payload={}, attempts=3, status="processing")
    mock_result.scalar_one_or_none.return_value = job_exhausted

    await store.mark_failed("job_f2", error="Permanent error", max_attempts=3)
    assert job_exhausted.status == "dead"
    assert job_exhausted.last_error == "Permanent error"
