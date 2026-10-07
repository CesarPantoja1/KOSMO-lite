from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest

from kosmo.infrastructure.api.async_generation import (
    _HEARTBEAT_COMMENT,
    with_heartbeat,
)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_with_heartbeat_emits_pings_when_idle() -> None:
    # Arrange: un generador con pausa controlada con margen amplio para evitar flakiness en CI
    async def slow_source() -> AsyncGenerator[str]:
        await asyncio.sleep(0.15)
        yield "data: event1\n\n"
        await asyncio.sleep(0.15)
        yield "data: event2\n\n"

    # Act: intervalo de 0.02s con holgura suficiente para emitir múltiples pings
    collected: list[str] = []
    async for item in with_heartbeat(slow_source(), interval=0.02):
        collected.append(item)

    # Assert
    ping_count = collected.count(_HEARTBEAT_COMMENT)
    assert ping_count >= 2, f"Esperaba al menos 2 pings, obtuve {ping_count}"
    assert "data: event1\n\n" in collected
    assert "data: event2\n\n" in collected
    assert collected[-1] == "data: event2\n\n"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_with_heartbeat_passes_through_fast_items_without_ping() -> None:
    # Arrange: generador rápido sin retrasos
    async def fast_source() -> AsyncGenerator[str]:
        yield "data: chunk1\n\n"
        yield "data: chunk2\n\n"
        yield "data: chunk3\n\n"

    # Act: intervalo generoso de 1.0s
    collected: list[str] = []
    async for item in with_heartbeat(fast_source(), interval=1.0):
        collected.append(item)

    # Assert: no debe haber ningún ping
    assert collected == [
        "data: chunk1\n\n",
        "data: chunk2\n\n",
        "data: chunk3\n\n",
    ]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_with_heartbeat_empty_source() -> None:
    # Arrange
    async def empty_source() -> AsyncGenerator[str]:
        if False:
            yield "never"

    # Act
    collected: list[str] = []
    async for item in with_heartbeat(empty_source(), interval=0.05):
        collected.append(item)

    # Assert
    assert collected == []


@pytest.mark.asyncio
@pytest.mark.unit
async def test_with_heartbeat_propagates_exceptions() -> None:
    # Arrange
    async def failing_source() -> AsyncGenerator[str]:
        yield "data: ok\n\n"
        raise RuntimeError("simulated stream failure")

    # Act & Assert
    collected: list[str] = []
    with pytest.raises(RuntimeError, match="simulated stream failure"):
        async for item in with_heartbeat(failing_source(), interval=0.05):
            collected.append(item)

    assert collected == ["data: ok\n\n"]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_with_heartbeat_cleans_up_on_early_break() -> None:
    # Arrange: generador que nunca termina
    async def infinite_source() -> AsyncGenerator[str]:
        while True:
            await asyncio.sleep(0.01)
            yield "data: infinite\n\n"

    # Act: romper el bucle tras recibir el primer elemento
    first_item: str | None = None
    async for item in with_heartbeat(infinite_source(), interval=0.05):
        first_item = item
        break

    # Assert: debe salir limpiamente sin dejar tareas colgadas
    assert first_item == "data: infinite\n\n"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_with_heartbeat_preserves_task_bound_cancel_scopes() -> None:
    # Arrange: un generador que abre un scope de AnyIO (como httpx/pydantic-ai) a través de yields
    import anyio

    async def scoped_source() -> AsyncGenerator[str]:
        async with anyio.create_task_group():
            yield "data: chunk1\n\n"
            await asyncio.sleep(0.01)
            yield "data: chunk2\n\n"

    # Act
    collected: list[str] = []
    async for item in with_heartbeat(scoped_source(), interval=1.0):
        collected.append(item)

    # Assert
    assert collected == ["data: chunk1\n\n", "data: chunk2\n\n"]
