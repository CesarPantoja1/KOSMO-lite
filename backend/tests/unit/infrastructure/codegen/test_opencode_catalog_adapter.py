from __future__ import annotations

import httpx
import pytest

from kosmo.infrastructure.codegen.opencode_catalog_adapter import HttpOpenCodeCatalogInspector
from kosmo.infrastructure.codegen.opencode_seed_catalog import OPENCODE_SEED_MODELS

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_inspector_returns_seed_when_no_url() -> None:
    # Arrange
    inspector = HttpOpenCodeCatalogInspector()

    # Act
    models = await inspector.get_supported_models()

    # Assert
    assert "openai" in models
    assert "gpt-6.1-terra" in models["openai"]
    assert "anthropic" in models
    assert "claude-opus-5-5" in models["anthropic"]
    assert models["openai"] == set(OPENCODE_SEED_MODELS["openai"])


@pytest.mark.asyncio
async def test_inspector_parses_launcher_catalog_endpoint() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/catalog"
        return httpx.Response(200, json={"openai": ["gpt-4o", "o3"], "deepseek": ["deepseek-flash"]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://launcher") as client:
        inspector = HttpOpenCodeCatalogInspector(client=client)

        # Act
        models = await inspector.get_supported_models()

        # Assert
        assert models["openai"] == {"gpt-4o", "o3"}
        assert models["deepseek"] == {"deepseek-flash"}


@pytest.mark.asyncio
async def test_inspector_parses_opencode_provider_endpoint() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/catalog":
            return httpx.Response(404)
        if request.url.path == "/provider":
            return httpx.Response(
                200,
                json={
                    "all": [
                        {"id": "anthropic", "models": {"claude-3-7-sonnet": {}, "claude-3-5-sonnet": {}}},
                        {"id": "google", "models": {"gemini-2.0-flash": {}}},
                    ]
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://opencode") as client:
        inspector = HttpOpenCodeCatalogInspector(client=client)

        # Act
        models = await inspector.get_supported_models()

        # Assert
        assert models["anthropic"] == {"claude-3-7-sonnet", "claude-3-5-sonnet"}
        assert models["google"] == {"gemini-2.0-flash"}


@pytest.mark.asyncio
async def test_inspector_extracts_raw_models_metadata() -> None:
    # Arrange
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/provider":
            return httpx.Response(
                200,
                json={
                    "all": [
                        {
                            "id": "anthropic",
                            "models": {
                                "claude-opus-5-5": {
                                    "name": "Claude Opus 5.5",
                                    "status": "active",
                                    "limit": {"context": 1000000, "output": 128000},
                                    "capabilities": {"toolcall": True, "input": {"image": True}},
                                }
                            },
                        }
                    ]
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://opencode") as client:
        inspector = HttpOpenCodeCatalogInspector(
            server_username="opencode",
            server_password="secret-password",
            client=client,
        )

        # Act
        raw_models = await inspector.get_raw_models()

        # Assert
        assert len(raw_models) == 1
        model = raw_models[0]
        assert model.provider == "anthropic"
        assert model.model_id == "claude-opus-5-5"
        assert model.display_name == "Claude Opus 5.5"
        assert model.context_window == 1000000
        assert model.max_output_tokens == 128000
        assert model.supports_tools is True
        assert model.supports_vision is True
        assert model.is_deprecated is False
        assert "Basic " in calls[0].headers["Authorization"]
