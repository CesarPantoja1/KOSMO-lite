"""Métricas Prometheus personalizadas para observabilidad en tiempo real."""

from __future__ import annotations

from typing import Any

from prometheus_client import REGISTRY, Gauge


def _get_or_create_gauge(name: str, documentation: str) -> Any:
    existing = getattr(REGISTRY, "_names_to_collectors", {}).get(name)
    if existing is not None:
        return existing
    return Gauge(name, documentation)


ACTIVE_SSE_CONNECTIONS: Any = _get_or_create_gauge(
    "kosmo_active_sse_connections",
    "Número actual de conexiones SSE activas transmitiendo al cliente.",
)
ACTIVE_CODE_RUNNERS: Any = _get_or_create_gauge(
    "kosmo_active_code_runners",
    "Número actual de runners de validación de código ejecutándose concurrentemente.",
)
