from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from kosmo.infrastructure.api.main import (
    _CSP_DEV,
    _CSP_PROD,
    _PERMISSIONS_POLICY,
    SecurityHeadersMiddleware,
)


@pytest.mark.unit
def test_security_headers_development_defaults() -> None:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, is_production=False)

    @app.get("/ping")
    def ping() -> dict[str, str]:
        return {"pong": "ok"}

    with TestClient(app) as client:
        res = client.get("/ping")
        assert res.headers["x-content-type-options"] == "nosniff"
        assert res.headers["x-frame-options"] == "DENY"
        assert res.headers["referrer-policy"] == "strict-origin-when-cross-origin"
        assert res.headers["permissions-policy"] == _PERMISSIONS_POLICY.decode("latin1")
        assert res.headers["content-security-policy"] == _CSP_DEV.decode("latin1")
        assert "strict-transport-security" not in res.headers


@pytest.mark.unit
def test_security_headers_production_defaults() -> None:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, is_production=True)

    @app.get("/ping")
    def ping() -> dict[str, str]:
        return {"pong": "ok"}

    with TestClient(app) as client:
        res = client.get("/ping")
        assert res.headers["x-content-type-options"] == "nosniff"
        assert res.headers["x-frame-options"] == "DENY"
        assert res.headers["referrer-policy"] == "strict-origin-when-cross-origin"
        assert res.headers["permissions-policy"] == _PERMISSIONS_POLICY.decode("latin1")
        assert res.headers["content-security-policy"] == _CSP_PROD.decode("latin1")
        assert "max-age=63072000" in res.headers["strict-transport-security"]


@pytest.mark.unit
def test_security_headers_preserves_custom_headers() -> None:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, is_production=False)

    @app.get("/custom")
    def custom() -> PlainTextResponse:
        return PlainTextResponse(
            "custom",
            headers={
                "content-security-policy": "default-src 'self'",
                "permissions-policy": "camera=*",
                "x-frame-options": "SAMEORIGIN",
            },
        )

    with TestClient(app) as client:
        res = client.get("/custom")
        assert res.headers["content-security-policy"] == "default-src 'self'"
        assert res.headers["permissions-policy"] == "camera=*"
        assert res.headers["x-frame-options"] == "SAMEORIGIN"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_security_headers_ignores_non_http_scope() -> None:
    calls = []

    async def dummy_app(scope: dict, _receive: object, _send: object) -> None:
        calls.append(scope["type"])

    middleware = SecurityHeadersMiddleware(dummy_app)
    scope = {"type": "websocket"}
    await middleware(scope, None, None)  # type: ignore[arg-type]

    assert calls == ["websocket"]
