from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI

from kosmo.config import Settings
from kosmo.contracts.telemetry import (
    TelemetryPort,
    get_telemetry_provider,
    record_auth_event,
    record_codegen_duration,
    record_codegen_retries,
    record_llm_tokens,
    set_telemetry_provider,
    traced,
)
from kosmo.infrastructure.telemetry.bootstrap import (
    configure_telemetry,
    instrument_app,
    instrument_prometheus,
)
from kosmo.infrastructure.telemetry.otel import OpenTelemetryProvider


@pytest.fixture(autouse=True)
def reset_telemetry_provider() -> None:
    """Asegura que el provider global se limpie antes y después de cada test."""
    set_telemetry_provider(None)
    yield
    set_telemetry_provider(None)


class FakeTelemetryProvider(TelemetryPort):
    """Implementación fake de TelemetryPort para verificar interacción de contratos."""

    def __init__(self) -> None:
        self.sync_calls: list[tuple[str, dict[str, Any]]] = []
        self.async_calls: list[tuple[str, dict[str, Any]]] = []
        self.auth_events: list[tuple[str, str | None]] = []
        self.codegen_durations: list[tuple[str, float, str]] = []
        self.codegen_retries: list[tuple[int, bool]] = []
        self.llm_tokens: list[tuple[int, str, str | None]] = []

    def trace_sync(
        self,
        span_name: str,
        attributes: dict[str, Any],
        func: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        self.sync_calls.append((span_name, attributes))
        return func(*args, **kwargs)

    async def trace_async(
        self,
        span_name: str,
        attributes: dict[str, Any],
        func: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        self.async_calls.append((span_name, attributes))
        return await func(*args, **kwargs)

    def record_auth_event(self, event_type: str, user_id: str | None = None) -> None:
        self.auth_events.append((event_type, user_id))

    def record_codegen_duration(
        self,
        phase: str,
        duration_seconds: float,
        status: str = "success",
    ) -> None:
        self.codegen_durations.append((phase, duration_seconds, status))

    def record_codegen_retries(
        self,
        retries_count: int,
        success: bool,
    ) -> None:
        self.codegen_retries.append((retries_count, success))

    def record_llm_tokens(
        self,
        tokens: int,
        model: str = "",
        user_id: str | None = None,
    ) -> None:
        self.llm_tokens.append((tokens, model, user_id))


@pytest.mark.unit
def test_traced_sync_without_provider_executes_function() -> None:
    @traced("test.sync", attributes={"key": "val"})
    def add(a: int, b: int) -> int:
        return a + b

    result = add(2, 3)
    assert result == 5


@pytest.mark.unit
@pytest.mark.asyncio
async def test_traced_async_without_provider_executes_coroutine() -> None:
    @traced("test.async", attributes={"key": "val"})
    async def async_add(a: int, b: int) -> int:
        return a + b

    result = await async_add(4, 5)
    assert result == 9


@pytest.mark.unit
def test_traced_sync_propagates_exceptions_without_provider() -> None:
    @traced("test.error")
    def faulty() -> None:
        raise ValueError("error in sync")

    with pytest.raises(ValueError, match="error in sync"):
        faulty()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_traced_async_propagates_exceptions_without_provider() -> None:
    @traced("test.error.async")
    async def faulty_async() -> None:
        raise RuntimeError("error in async")

    with pytest.raises(RuntimeError, match="error in async"):
        await faulty_async()


@pytest.mark.unit
def test_record_auth_event_without_provider_noop() -> None:
    # No debe arrojar ninguna excepción cuando no hay provider configurado
    record_auth_event("login_attempt", user_id="usr_01")


@pytest.mark.unit
def test_traced_sync_delegates_to_configured_provider() -> None:
    provider = FakeTelemetryProvider()
    set_telemetry_provider(provider)
    assert get_telemetry_provider() is provider

    @traced("operation.sync", attributes={"env": "test"})
    def compute(x: int) -> int:
        return x * 2

    res = compute(10)
    assert res == 20
    assert len(provider.sync_calls) == 1
    assert provider.sync_calls[0] == ("operation.sync", {"env": "test"})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_traced_async_delegates_to_configured_provider() -> None:
    provider = FakeTelemetryProvider()
    set_telemetry_provider(provider)

    @traced("operation.async", attributes={"module": "test"})
    async def fetch_data(key: str) -> str:
        return f"value_{key}"

    res = await fetch_data("k1")
    assert res == "value_k1"
    assert len(provider.async_calls) == 1
    assert provider.async_calls[0] == ("operation.async", {"module": "test"})


@pytest.mark.unit
def test_record_auth_event_delegates_to_configured_provider() -> None:
    provider = FakeTelemetryProvider()
    set_telemetry_provider(provider)

    record_auth_event("login_success", user_id="usr_99")
    record_auth_event("login_failure")

    assert len(provider.auth_events) == 2
    assert provider.auth_events[0] == ("login_success", "usr_99")
    assert provider.auth_events[1] == ("login_failure", None)


@pytest.mark.unit
def test_opentelemetry_provider_trace_sync_success_and_error() -> None:
    provider = OpenTelemetryProvider()

    def sync_fn(x: int) -> int:
        return x + 1

    assert provider.trace_sync("span.test", {"attr": "1"}, sync_fn, 5) == 6

    def faulty_fn() -> None:
        raise KeyError("missing_key")

    with pytest.raises(KeyError, match="missing_key"):
        provider.trace_sync("span.test.error", {}, faulty_fn)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_opentelemetry_provider_trace_async_success_and_error() -> None:
    provider = OpenTelemetryProvider()

    async def async_fn(name: str) -> str:
        return f"hello {name}"

    res = await provider.trace_async("span.async.test", {"attr": "2"}, async_fn, "kosmo")
    assert res == "hello kosmo"

    async def faulty_async() -> None:
        raise IndexError("out of range")

    with pytest.raises(IndexError, match="out of range"):
        await provider.trace_async("span.async.error", {}, faulty_async)


@pytest.mark.unit
def test_opentelemetry_provider_record_auth_event() -> None:
    provider = OpenTelemetryProvider()
    # Verifica que el contador no lance error
    provider.record_auth_event("logout", user_id="usr_123")
    provider.record_auth_event("anonymous_action", user_id=None)


@pytest.mark.unit
def test_configure_telemetry_sets_opentelemetry_provider() -> None:
    settings = Settings()
    configure_telemetry(settings)

    active_provider = get_telemetry_provider()
    assert active_provider is not None
    assert isinstance(active_provider, OpenTelemetryProvider)


@pytest.mark.unit
def test_codegen_and_llm_telemetry_without_provider_noop() -> None:
    # Sin provider activo no deben lanzar excepciones
    record_codegen_duration("plan", 1.5, status="success")
    record_codegen_retries(retries_count=2, success=True)
    record_llm_tokens(tokens=150, model="gpt-4o", user_id="usr_123")


@pytest.mark.unit
def test_codegen_and_llm_telemetry_delegates_to_configured_provider() -> None:
    provider = FakeTelemetryProvider()
    set_telemetry_provider(provider)

    record_codegen_duration("plan", 2.3, status="success")
    record_codegen_duration("build", 4.1, status="failure")
    record_codegen_retries(retries_count=1, success=True)
    record_llm_tokens(tokens=500, model="claude-3-5-sonnet", user_id="usr_abc")

    assert len(provider.codegen_durations) == 2
    assert provider.codegen_durations[0] == ("plan", 2.3, "success")
    assert provider.codegen_durations[1] == ("build", 4.1, "failure")

    assert len(provider.codegen_retries) == 1
    assert provider.codegen_retries[0] == (1, True)

    assert len(provider.llm_tokens) == 1
    assert provider.llm_tokens[0] == (500, "claude-3-5-sonnet", "usr_abc")


@pytest.mark.unit
def test_opentelemetry_provider_record_codegen_and_llm_metrics() -> None:
    provider = OpenTelemetryProvider()
    # Verifica que los instrumentos metricos de OpenTelemetry no fallen
    provider.record_codegen_duration("plan", 3.2, status="success")
    provider.record_codegen_duration("total", 12.5, status="error")
    provider.record_codegen_retries(retries_count=3, success=False)
    provider.record_llm_tokens(tokens=1200, model="gpt-4o-mini", user_id="usr_01")
    provider.record_llm_tokens(tokens=300, model="", user_id=None)


@pytest.mark.unit
def test_instrument_app_is_idempotent() -> None:
    # Arrange
    from unittest.mock import MagicMock

    from sqlalchemy.ext.asyncio import AsyncEngine

    app = FastAPI()
    settings = Settings()
    engine = MagicMock(spec=AsyncEngine)

    # Act
    instrument_app(settings, app=app, db_engine=engine)
    instrument_app(settings, app=app, db_engine=engine)

    # Assert
    assert getattr(app.state, "_kosmo_instrumented", False) is True


@pytest.mark.unit
def test_instrument_prometheus_is_idempotent() -> None:
    # Arrange
    app = FastAPI()

    # Act
    instrument_prometheus(app)
    instrument_prometheus(app)

    # Assert
    assert getattr(app.state, "_kosmo_prometheus_instrumented", False) is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_request_logging_middleware_handles_http_request_and_context() -> None:
    # Arrange
    from kosmo.infrastructure.api.middlewares.logging import RequestLoggingMiddleware

    invoked_paths: list[str] = []

    async def dummy_app(scope: dict[str, Any], _receive: Any, send: Any) -> None:
        invoked_paths.append(scope["path"])
        await send({"type": "http.response.start", "status": 200})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = RequestLoggingMiddleware(dummy_app)
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/health",
        "headers": [(b"user-agent", b"pytest-agent")],
    }

    async def dummy_receive() -> dict[str, Any]:
        return {"type": "http.request"}

    messages: list[dict[str, Any]] = []

    async def dummy_send(message: dict[str, Any]) -> None:
        messages.append(message)

    # Act
    await middleware(scope, dummy_receive, dummy_send)

    # Assert
    assert invoked_paths == ["/api/v1/health"]
    assert len(messages) == 2
    assert messages[0]["status"] == 200
