from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from opentelemetry import trace
from ulid import ULID

_logger = structlog.get_logger("kosmo.http")
_tracer = trace.get_tracer("kosmo.http")

Scope = dict[str, Any]
Message = dict[str, Any]
ASGIApp = Callable[[Scope, Callable[[], Awaitable[Message]], Callable[[Message], Awaitable[None]]], Awaitable[None]]


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Callable[[], Awaitable[Message]],
        send: Callable[[Message], Awaitable[None]],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = ULID().hex
        client: tuple[str, int] | None = scope.get("client")  # type: ignore[reportUnknownVariableType]
        ip_address: str | None = client[0] if client else None
        raw_headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
        headers: dict[bytes, bytes] = dict(raw_headers)
        user_agent = headers.get(b"user-agent", b"").decode("utf-8", errors="replace")

        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        method: str = scope["method"]
        path: str = scope["path"]

        start = time.perf_counter()
        status_code: list[int | None] = [None]

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_code[0] = message["status"]
            await send(message)

        try:
            # Span HTTP raíz como fuente única de verdad para observabilidad distribuida.
            with _tracer.start_as_current_span(
                "http.request",
                attributes={
                    "http.method": method,
                    "http.url": str(scope.get("root_path", "")) + path,
                    "http.route": path,
                },
            ) as span:
                try:
                    await self.app(scope, receive, send_wrapper)
                except Exception as exc:
                    duration_ms = (time.perf_counter() - start) * 1000
                    span.record_exception(exc)
                    span.set_status(trace.StatusCode.ERROR, str(exc))
                    _logger.error(
                        "http.request.failed",
                        method=method,
                        path=path,
                        duration_ms=round(duration_ms, 3),
                        request_id=request_id,
                        exc_info=True,
                    )
                    raise

                duration_ms = (time.perf_counter() - start) * 1000
                code = status_code[0]
                if code is not None:
                    span.set_attribute("http.status_code", code)

                _logger.info(
                    "http.request.completed",
                    method=method,
                    path=path,
                    status_code=code,
                    duration_ms=round(duration_ms, 3),
                    request_id=request_id,
                )
        finally:
            structlog.contextvars.clear_contextvars()
