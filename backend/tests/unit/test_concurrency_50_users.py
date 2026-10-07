from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kosmo.contracts.ai.ai_config import AIProvider, UserAiConfig
from kosmo.contracts.auth.secrets import EncryptedSecret
from kosmo.contracts.llm.ports import LLMResponse, PromptTemplate
from kosmo.contracts.sdd.codegen import OpenCodeEvent, OpenCodeEventType
from kosmo.contracts.sdd.ids import FeatureId
from kosmo.infrastructure.api.implementation_broker import ImplementationEventBroker
from kosmo.infrastructure.llm.dynamic_llm_client import DynamicUserLLMClient, current_user_id
from kosmo.infrastructure.persistence.postgres.models import OutboxJobModel
from kosmo.infrastructure.persistence.postgres.outbox import run_outbox_worker


# ---------------------------------------------------------------------------
# 1. LLM Semaphore Protection Test
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.unit
async def test_50_concurrent_users_llm_semaphore_protection() -> None:
    num_users = 50
    max_concurrency = 15

    mock_repo = AsyncMock()
    mock_repo.by_user_id.side_effect = lambda uid: UserAiConfig(
        user_id=uid,
        provider=AIProvider.OPENAI,
        model="gpt-4o",
        encrypted_api_key=EncryptedSecret(ciphertext=f"enc_{uid}".encode()),
        is_custom=True,
    )

    mock_cipher = MagicMock()
    mock_cipher.decrypt.side_effect = lambda secret: secret.ciphertext.replace(b"enc_", b"")

    client = DynamicUserLLMClient(
        config_repo=mock_repo,
        cipher=mock_cipher,
        default_provider="openai",
        default_model="gpt-4o",
        default_api_key="sk-default",
        max_concurrency=max_concurrency,
        cache_ttl_seconds=60.0,
    )

    current_active = 0
    max_seen_active = 0
    lock = asyncio.Lock()

    async def slow_complete(*_args, **_kwargs):
        nonlocal current_active, max_seen_active
        async with lock:
            current_active += 1
            if current_active > max_seen_active:
                max_seen_active = current_active
        await asyncio.sleep(0.02)
        async with lock:
            current_active -= 1
        return LLMResponse(text="llm_output")

    mock_pydantic_client = AsyncMock()
    mock_pydantic_client.complete.side_effect = slow_complete

    with patch("kosmo.infrastructure.llm.dynamic_llm_client.PydanticAILLMClient", return_value=mock_pydantic_client):

        async def call_llm(user_idx: int) -> str:
            user_id = f"usr_{user_idx}"
            current_user_id.set(user_id)
            prompt = PromptTemplate(system_prompt="sys", user_prompt=f"query from {user_id}")
            resp = await client.complete(prompt)
            return resp.text

        tasks = [asyncio.create_task(call_llm(i)) for i in range(num_users)]
        results = await asyncio.gather(*tasks)

        assert len(results) == num_users
        assert all(r == "llm_output" for r in results)
        assert max_seen_active <= max_concurrency, (
            f"Concurrencia máxima excedida: {max_seen_active} > {max_concurrency}"
        )


# ---------------------------------------------------------------------------
# 2. Implementation Event Broker Isolation Test
# ---------------------------------------------------------------------------
class MockUseCase:
    def __init__(self, impl_id: str) -> None:
        self.impl_id = impl_id

    async def execute_stream(self, input_data: Any) -> AsyncIterator[OpenCodeEvent]:
        yield OpenCodeEvent(event_type=OpenCodeEventType.PLAN_PROGRESS, session_id=self.impl_id, data={"step": 1})
        await asyncio.sleep(0.01)
        yield OpenCodeEvent(event_type=OpenCodeEventType.DONE, session_id=self.impl_id, data={"step": 2})


@pytest.mark.asyncio
@pytest.mark.unit
async def test_50_concurrent_users_implementation_broker_streams() -> None:
    num_users = 50
    broker = ImplementationEventBroker()

    async def run_single_user_stream(idx: int) -> list[OpenCodeEvent]:
        impl_id = f"impl_{idx}"
        use_case = MockUseCase(impl_id)
        input_data = MagicMock(feature_id=FeatureId(f"feat_{idx}"))

        broker.start_implementation(impl_id, use_case, input_data)

        events: list[OpenCodeEvent] = []
        async for event in broker.subscribe(impl_id):
            events.append(event)
        return events

    tasks = [asyncio.create_task(run_single_user_stream(i)) for i in range(num_users)]
    all_events = await asyncio.gather(*tasks)

    assert len(all_events) == num_users
    for idx, events in enumerate(all_events):
        expected_session = f"impl_{idx}"
        assert len(events) == 2
        assert events[0].event_type == OpenCodeEventType.PLAN_PROGRESS
        assert events[0].session_id == expected_session
        assert events[1].event_type == OpenCodeEventType.DONE
        assert events[1].session_id == expected_session


# ---------------------------------------------------------------------------
# 3. Outbox Worker Concurrency Test
# ---------------------------------------------------------------------------
class DummyOutboxStore:
    def __init__(self, jobs: list[OutboxJobModel]) -> None:
        self._pending = list(jobs)
        self.done: list[str] = []
        self._lock = asyncio.Lock()

    async def dequeue(self) -> OutboxJobModel | None:
        async with self._lock:
            if self._pending:
                job = self._pending.pop(0)
                job.status = "processing"
                job.attempts = (job.attempts or 0) + 1
                return job
            return None

    async def mark_done(self, job_id: str) -> None:
        async with self._lock:
            self.done.append(job_id)

    async def mark_failed(self, job_id: str, *, error: str | None = None) -> None:
        pass


@pytest.mark.asyncio
@pytest.mark.unit
async def test_50_concurrent_users_outbox_worker_throughput() -> None:
    num_jobs = 50
    jobs = [
        OutboxJobModel(
            id=f"job_{i}",
            job_type="deploy_action",
            payload={"user_id": f"usr_{i}"},
            attempts=0,
            status="pending",
        )
        for i in range(num_jobs)
    ]
    store = DummyOutboxStore(jobs)

    current_active = 0
    max_active = 0
    active_lock = asyncio.Lock()

    async def handler(_job_type: str, _payload: dict[str, Any]) -> None:
        nonlocal current_active, max_active
        async with active_lock:
            current_active += 1
            if current_active > max_active:
                max_active = current_active
        await asyncio.sleep(0.01)
        async with active_lock:
            current_active -= 1

    worker_task = asyncio.create_task(
        run_outbox_worker(
            store=store,  # type: ignore[arg-type]
            handler=handler,
            poll_interval=0.005,
            max_concurrency=5,
        )
    )

    for _ in range(100):
        if len(store.done) == num_jobs:
            break
        await asyncio.sleep(0.05)

    worker_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await worker_task

    assert len(store.done) == num_jobs
    assert max_active <= 5
