from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from opentelemetry import metrics, trace
from ulid import ULID

from kosmo.contracts.telemetry import TelemetryPort


def get_current_trace_id() -> str:
    """Obtiene el identificador de traza actual de OpenTelemetry en formato hex (32 chars) o un fallback ULID."""
    span = trace.get_current_span()
    context = span.get_span_context()
    if context.is_valid:
        return format(context.trace_id, "032x")
    return ULID().hex


class OpenTelemetryProvider(TelemetryPort):
    """Adaptador de infraestructura para telemetría usando OpenTelemetry."""

    def __init__(self, tracer_name: str = "kosmo.business", meter_name: str = "kosmo.auth") -> None:
        self._tracer = trace.get_tracer(tracer_name)
        self._meter = metrics.get_meter(meter_name)
        self._auth_events = self._meter.create_counter(
            "kosmo.auth.events",
            unit="1",
            description="Authentication events by type",
        )
        self._codegen_duration = self._meter.create_histogram(
            "kosmo.codegen.phase_duration_seconds",
            unit="s",
            description="Duration of codegen pipeline phases in seconds",
        )
        self._codegen_retries = self._meter.create_counter(
            "kosmo.codegen.retries",
            unit="1",
            description="Number of codegen validation retries",
        )
        self._llm_tokens = self._meter.create_counter(
            "kosmo.llm.tokens",
            unit="1",
            description="LLM tokens consumed",
        )

    def trace_sync(
        self,
        span_name: str,
        attributes: dict[str, Any],
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        with self._tracer.start_as_current_span(span_name, attributes=attributes) as span:
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(trace.StatusCode.ERROR, str(exc))
                raise

    async def trace_async(
        self,
        span_name: str,
        attributes: dict[str, Any],
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        with self._tracer.start_as_current_span(span_name, attributes=attributes) as span:
            try:
                res = func(*args, **kwargs)
                if inspect.isawaitable(res):
                    return await res
                return res
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(trace.StatusCode.ERROR, str(exc))
                raise

    def record_auth_event(self, event_type: str, user_id: str | None = None) -> None:
        attributes: dict[str, str] = {"event_type": event_type}
        if user_id is not None:
            attributes["user_id"] = user_id
        self._auth_events.add(1, attributes)

    def record_codegen_duration(
        self,
        phase: str,
        duration_seconds: float,
        status: str = "success",
    ) -> None:
        self._codegen_duration.record(
            duration_seconds,
            {"phase": phase, "status": status},
        )

    def record_codegen_retries(
        self,
        retries_count: int,
        success: bool,
    ) -> None:
        self._codegen_retries.add(
            retries_count,
            {"success": str(success).lower()},
        )

    def record_llm_tokens(
        self,
        tokens: int,
        model: str = "",
        user_id: str | None = None,
    ) -> None:
        attributes: dict[str, str] = {}
        if model:
            attributes["model"] = model
        if user_id:
            attributes["user_id"] = user_id
        self._llm_tokens.add(tokens, attributes)
