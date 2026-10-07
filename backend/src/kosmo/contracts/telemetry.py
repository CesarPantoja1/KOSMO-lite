from __future__ import annotations

import functools
import inspect
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, Protocol, TypeVar, cast, runtime_checkable

P = ParamSpec("P")
R = TypeVar("R")


@runtime_checkable
class TelemetryPort(Protocol):
    """Puerto abstracto para observabilidad, tracing y métricas."""

    def trace_sync(
        self,
        span_name: str,
        attributes: dict[str, Any],
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any: ...

    async def trace_async(
        self,
        span_name: str,
        attributes: dict[str, Any],
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any: ...

    def record_auth_event(self, event_type: str, user_id: str | None = None) -> None: ...

    def record_codegen_duration(
        self,
        phase: str,
        duration_seconds: float,
        status: str = "success",
    ) -> None: ...

    def record_codegen_retries(
        self,
        retries_count: int,
        success: bool,
    ) -> None: ...

    def record_llm_tokens(
        self,
        tokens: int,
        model: str = "",
        user_id: str | None = None,
    ) -> None: ...


_provider: TelemetryPort | None = None


def set_telemetry_provider(provider: TelemetryPort | None) -> None:
    """Configura el proveedor de telemetría activo (invocado desde infraestructura)."""
    global _provider
    _provider = provider


def get_telemetry_provider() -> TelemetryPort | None:
    """Retorna el proveedor de telemetría activo o None si no se ha configurado."""
    return _provider


def traced(span_name: str, attributes: dict[str, Any] | None = None) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorador de tracing para funciones síncronas y asíncronas.

    Delega la ejecución al TelemetryPort activo. Si no hay proveedor configurado
    (por ejemplo, durante tests unitarios), invoca la función original directamente sin sobrecarga.
    """
    span_attrs: dict[str, Any] = dict(attributes) if attributes else {}

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        if inspect.iscoroutinefunction(func):
            coro_func = cast(Callable[P, Awaitable[R]], func)

            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                if _provider is not None:
                    res = await _provider.trace_async(span_name, span_attrs, coro_func, *args, **kwargs)
                    return cast(R, res)
                return await coro_func(*args, **kwargs)

            return cast(Callable[P, R], async_wrapper)

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            if _provider is not None:
                res = _provider.trace_sync(span_name, span_attrs, func, *args, **kwargs)
                return cast(R, res)
            return func(*args, **kwargs)

        return sync_wrapper

    return decorator


def record_auth_event(event_type: str, user_id: str | None = None) -> None:
    """Registra un evento de autenticación en el proveedor de telemetría activo."""
    if _provider is not None:
        _provider.record_auth_event(event_type, user_id)


def record_codegen_duration(
    phase: str,
    duration_seconds: float,
    status: str = "success",
) -> None:
    """Registra la duración de una fase del pipeline de codegen en segundos."""
    if _provider is not None:
        _provider.record_codegen_duration(phase, duration_seconds, status)


def record_codegen_retries(
    retries_count: int,
    success: bool,
) -> None:
    """Registra el conteo de reintentos en la fase de validación de codegen."""
    if _provider is not None:
        _provider.record_codegen_retries(retries_count, success)


def record_llm_tokens(
    tokens: int,
    model: str = "",
    user_id: str | None = None,
) -> None:
    """Registra tokens consumidos por una invocación a un LLM."""
    if _provider is not None:
        _provider.record_llm_tokens(tokens, model, user_id)
