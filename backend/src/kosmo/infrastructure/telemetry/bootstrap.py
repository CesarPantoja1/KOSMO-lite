"""Bootstrap de observabilidad: logs estructurados + tracing + métricas.

Es el único punto donde se conecta la telemetría: ``configure_telemetry`` se
invoca en el ``lifespan`` para inicializar structlog y logfire, e
``instrument_app`` adjunta la auto-instrumentación a SQLAlchemy/Redis
una vez que los componentes IO están construidos.

Ningún caso de uso depende de este módulo: la telemetría se observa a través
del API público en :mod:`kosmo.contracts.telemetry`.
"""

from __future__ import annotations

import contextlib
import logging
import sys
from typing import TYPE_CHECKING

import logfire
import structlog
from opentelemetry import trace
from structlog.typing import EventDict, Processor, WrappedLogger

from kosmo.contracts.telemetry import set_telemetry_provider
from kosmo.infrastructure.telemetry.otel import OpenTelemetryProvider

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import AsyncEngine

    from kosmo.config import Settings


def _inject_otel_context(_logger: WrappedLogger, _method_name: str, event_dict: EventDict) -> EventDict:
    span = trace.get_current_span()
    context = span.get_span_context()
    if context.is_valid:
        event_dict["trace_id"] = format(context.trace_id, "032x")
        event_dict["span_id"] = format(context.span_id, "016x")
    return event_dict


def _build_processors(env: str) -> list[Processor]:
    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _inject_otel_context,
    ]
    if env == "development":
        processors.append(structlog.dev.ConsoleRenderer(colors=True))
    else:
        processors.append(structlog.processors.JSONRenderer())
    return processors


def _configure_structlog(settings: Settings) -> None:
    log_level = getattr(logging, settings.log_level)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=log_level)

    structlog.configure(
        processors=_build_processors(settings.env),
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def _configure_logfire(settings: Settings) -> None:
    token = settings.logfire_token.get_secret_value() if settings.logfire_token is not None else None
    logfire.configure(
        token=token,
        service_name=settings.otel_service_name,
        environment=settings.otel_environment,
        send_to_logfire="if-token-present",
        console=False,
    )


def configure_telemetry(settings: Settings) -> None:
    """Inicializa logging estructurado y tracing distribuido."""

    _configure_structlog(settings)
    _configure_logfire(settings)
    set_telemetry_provider(OpenTelemetryProvider())


def instrument_prometheus(app: FastAPI) -> None:
    """Instrumenta FastAPI con prometheus-fastapi-instrumentator antes del startup de manera idempotente."""
    if getattr(app.state, "_kosmo_prometheus_instrumented", False):
        return
    try:
        from prometheus_fastapi_instrumentator import (  # pyright: ignore[reportMissingImports]
            Instrumentator,  # pyright: ignore[reportUnknownVariableType]
        )

        Instrumentator().instrument(app).expose(app)  # pyright: ignore[reportUnknownMemberType]
        app.state._kosmo_prometheus_instrumented = True
    except (ImportError, Exception):
        pass


def instrument_app(
    settings: Settings,
    *,
    app: FastAPI,
    db_engine: AsyncEngine,
) -> None:
    """Aplica auto-instrumentación a los componentes IO en lifespan de manera idempotente."""

    del settings
    if getattr(app.state, "_kosmo_instrumented", False):
        return

    with contextlib.suppress(Exception):
        logfire.instrument_sqlalchemy(engine=db_engine)
    with contextlib.suppress(Exception):
        logfire.instrument_redis(capture_statement=False)

    app.state._kosmo_instrumented = True
