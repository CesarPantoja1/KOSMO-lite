from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.ids import ProjectId
from kosmo.infrastructure.api.async_generation import (
    sse_chat_response,
    sse_consistency_response,
)
from kosmo.infrastructure.telemetry.otel import get_current_trace_id


@pytest.mark.unit
def test_get_current_trace_id_uses_active_otel_span() -> None:
    # Arrange: active span context with a known 128-bit trace ID
    trace_id_int = 0x4BF92F3577B34DA6A3CE929D0E0E4736
    expected_hex = "4bf92f3577b34da6a3ce929d0e0e4736"
    span_ctx = SpanContext(
        trace_id=trace_id_int,
        span_id=0x00F067AA0BA902B7,
        is_remote=False,
        trace_flags=TraceFlags(0x01),
    )
    span = NonRecordingSpan(span_ctx)

    # Act
    with trace.use_span(span):
        resolved_trace_id = get_current_trace_id()

    # Assert
    assert resolved_trace_id == expected_hex


@pytest.mark.unit
def test_get_current_trace_id_fallback_to_ulid_when_no_active_span() -> None:
    # Act
    tid = get_current_trace_id()

    # Assert
    assert isinstance(tid, str)
    assert len(tid) >= 26


@pytest.mark.asyncio
@pytest.mark.unit
async def test_sse_chat_response_handshake_and_headers_include_trace_id() -> None:
    # Arrange
    validate_uc = AsyncMock()
    validate_res = MagicMock()
    validate_res.is_valid = True
    validate_uc.execute.return_value = validate_res

    chat_uc = AsyncMock()

    async def fake_stream(_input_data):
        from kosmo.application.chat.process_chat_message import ChatStreamChunk

        yield ChatStreamChunk(content="Hello world")

    chat_uc.execute_stream = fake_stream

    # Act
    response = await sse_chat_response(
        content="test message",
        document_type=SpecPhase.DESCUBRIMIENTO,
        pid=ProjectId("prj_trace_test"),
        context_id=None,
        context=None,
        chat_uc=chat_uc,
        validate_uc=validate_uc,
    )

    # Assert headers
    header_trace_id = response.headers.get("X-Trace-Id")
    assert header_trace_id is not None
    assert len(header_trace_id) >= 26

    # Assert first SSE chunk is "start" with matching trace_id
    chunks: list[str] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    assert len(chunks) >= 2
    first_chunk = chunks[0]
    assert first_chunk.startswith("data: ")
    start_payload = json.loads(first_chunk[len("data: ") :].strip())
    assert start_payload["type"] == "start"
    assert start_payload["trace_id"] == header_trace_id


@pytest.mark.asyncio
@pytest.mark.unit
async def test_sse_chat_response_error_event_includes_trace_id() -> None:
    # Arrange
    validate_uc = AsyncMock()
    validate_res = MagicMock()
    validate_res.is_valid = True
    validate_uc.execute.return_value = validate_res

    chat_uc = AsyncMock()

    async def failing_stream(_input_data):
        raise RuntimeError("Simulated LLM crash")
        yield  # type: ignore[unreachable]

    chat_uc.execute_stream = failing_stream

    # Act
    response = await sse_chat_response(
        content="failing message",
        document_type=SpecPhase.DESCUBRIMIENTO,
        pid=ProjectId("prj_trace_test"),
        context_id=None,
        context=None,
        chat_uc=chat_uc,
        validate_uc=validate_uc,
    )

    header_trace_id = response.headers.get("X-Trace-Id")
    assert header_trace_id is not None

    chunks: list[str] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    # Find error chunk
    error_chunk = next(c for c in chunks if '"error"' in c)
    error_payload = json.loads(error_chunk[len("data: ") :].strip())
    assert error_payload["type"] == "error"
    assert error_payload["trace_id"] == header_trace_id


@pytest.mark.asyncio
@pytest.mark.unit
async def test_sse_consistency_response_handshake_includes_trace_id() -> None:
    # Arrange
    async def dummy_gen() -> AsyncGenerator[str]:
        yield 'data: {"type": "progress"}\n\n'

    # Act
    response = await sse_consistency_response(dummy_gen())

    header_trace_id = response.headers.get("X-Trace-Id")
    assert header_trace_id is not None

    chunks: list[str] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    first_chunk = chunks[0]
    start_payload = json.loads(first_chunk[len("data: ") :].strip())
    assert start_payload["type"] == "start"
    assert start_payload["trace_id"] == header_trace_id
