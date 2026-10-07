from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from kosmo.contracts.ai.ai_config import (
    AIProvider,
    TestAIConnectionResult,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_get_preferences():
    return AsyncMock()


@pytest.fixture
def mock_save_preferences():
    return AsyncMock()


@pytest.fixture
def mock_delete_preferences():
    return AsyncMock()


@pytest.fixture
def mock_test_connection():
    return AsyncMock()


@pytest.fixture
def app():
    from kosmo.infrastructure.api.main import app as main_app

    return main_app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def auth_client(client, app):
    from kosmo.contracts.auth import Principal
    from kosmo.infrastructure.api.dependencies.auth import get_principal

    mock_principal = Principal(subject="user-1", scopes=frozenset({"*"}))
    app.dependency_overrides[get_principal] = lambda: mock_principal
    yield client
    app.dependency_overrides.pop(get_principal, None)


@pytest.fixture(autouse=True)
def override_ai_config_use_cases(
    app,
    mock_get_preferences,
    mock_save_preferences,
    mock_delete_preferences,
    mock_test_connection,
):
    from kosmo.application.ai.manage_ai_preferences import ManageAIPreferencesUseCase
    from kosmo.application.ai.validate_ai_connection import ValidateAIConnectionUseCase
    from kosmo.infrastructure.api.dependencies.ai_config import (
        get_manage_ai_preferences_use_case,
        get_validate_ai_connection_use_case,
    )

    mock_manage_use_case = MagicMock(spec=ManageAIPreferencesUseCase)
    mock_manage_use_case.get_preferences = mock_get_preferences
    mock_manage_use_case.save_preferences = mock_save_preferences
    mock_manage_use_case.delete_preferences = mock_delete_preferences

    mock_validate_use_case = MagicMock(spec=ValidateAIConnectionUseCase)
    mock_validate_use_case.execute = mock_test_connection

    app.dependency_overrides[get_manage_ai_preferences_use_case] = lambda: mock_manage_use_case
    app.dependency_overrides[get_validate_ai_connection_use_case] = lambda: mock_validate_use_case

    yield

    app.dependency_overrides.pop(get_manage_ai_preferences_use_case, None)
    app.dependency_overrides.pop(get_validate_ai_connection_use_case, None)


def test_get_preferences_returns_200(auth_client: TestClient, mock_get_preferences):
    from kosmo.contracts.ai.ai_config import AIConfigView

    mock_get_preferences.return_value = AIConfigView(
        provider=AIProvider.ANTHROPIC,
        model="claude-3-opus-20240229",
        is_custom=False,
        has_api_key=True,
        masked_key="••••••••1234",
    )

    response = auth_client.get("/api/v1/ai-config")

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "anthropic"
    assert data["model"] == "claude-3-opus-20240229"
    assert data["has_api_key"] is True
    assert data["masked_key"] == "••••••••1234"


def test_get_preferences_unauthorized(client: TestClient):
    response = client.get("/api/v1/ai-config")
    assert response.status_code == 401


def test_save_preferences_returns_200(auth_client: TestClient, mock_save_preferences):
    from kosmo.contracts.ai.ai_config import AIConfigView

    mock_save_preferences.return_value = AIConfigView(
        provider=AIProvider.OPENAI,
        model="gpt-4o",
        is_custom=False,
        has_api_key=True,
        masked_key="••••••••abcd",
    )

    payload = {
        "provider": "openai",
        "model": "gpt-4o",
        "api_key": "sk-1234abcd",
    }
    response = auth_client.post("/api/v1/ai-config", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "openai"
    assert data["has_api_key"] is True
    assert data["masked_key"] == "••••••••abcd"


def test_save_preferences_invalid_provider_returns_400(auth_client: TestClient):
    payload = {
        "provider": "invalid_provider_xyz",
        "model": "gpt-4o",
        "api_key": "sk-1234abcd",
    }
    response = auth_client.post("/api/v1/ai-config", json=payload)
    assert response.status_code == 400
    assert "Proveedor no soportado" in response.json()["detail"]


def test_save_preferences_empty_api_key_returns_422(auth_client: TestClient):
    payload = {
        "provider": "openai",
        "model": "gpt-4o",
        "api_key": "",
    }
    response = auth_client.post("/api/v1/ai-config", json=payload)
    assert response.status_code == 422
    assert "La clave de API no puede estar vacía" in response.json()["detail"]


def test_save_preferences_connection_failure_returns_422(auth_client: TestClient, mock_save_preferences):
    from kosmo.contracts.ai.ai_config import AIConnectionTestError

    mock_save_preferences.side_effect = AIConnectionTestError("Clave de API inválida o no autorizada para OpenAI.")
    payload = {
        "provider": "openai",
        "model": "gpt-4o",
        "api_key": "sk-invalidkey",
    }
    response = auth_client.post("/api/v1/ai-config", json=payload)
    assert response.status_code == 422
    assert "Clave de API inválida o no autorizada para OpenAI" in response.json()["detail"]


def test_delete_preferences_returns_204(auth_client: TestClient, mock_delete_preferences):
    response = auth_client.delete("/api/v1/ai-config")

    assert response.status_code == 204
    mock_delete_preferences.assert_called_once()


def test_test_connection_returns_200(auth_client: TestClient, mock_test_connection):
    mock_test_connection.return_value = TestAIConnectionResult(
        is_connected=True,
        detected_model="gemini-1.5-pro",
        message="Connection OK",
    )

    payload = {
        "provider": "google",
        "model": "gemini-1.5-pro",
    }
    response = auth_client.post("/api/v1/ai-config/test", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["is_connected"] is True
    assert data["detected_model"] == "gemini-1.5-pro"
    assert data["message"] == "Connection OK"


def test_get_providers_returns_200(client: TestClient):
    # Arrange & Act (endpoint público sin autenticación requerida)
    response = client.get("/api/v1/ai-config/providers")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 4
    provider_values = [p["value"] for p in data]
    assert provider_values == ["openai", "anthropic", "google", "deepseek"]
    for provider in data:
        assert "label" in provider
        assert "models" in provider
        assert len(provider["models"]) > 0
        for model in provider["models"]:
            assert "id" in model
            assert "display_name" in model
            assert "tier" in model
