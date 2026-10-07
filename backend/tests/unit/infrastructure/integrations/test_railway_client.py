from __future__ import annotations

import json
import urllib.parse
from typing import Any

import httpx
import pytest

from kosmo.contracts.integrations.deployment import (
    DeploymentApiError,
    DeploymentAuthenticationError,
    DeploymentConfigurationError,
    DeploymentOAuthToken,
    DeploymentPermissionError,
    DeploymentRateLimitError,
    DeploymentResourceNotFoundError,
    DeploymentStatus,
    EnvironmentVariable,
    PortSpec,
    VolumeConfig,
)
from kosmo.infrastructure.integrations.railway_client import RailwayHttpClient


def _create_mock_client(
    handler: Any,
    base_url: str = "https://backboard.railway.com",
) -> httpx.AsyncClient:
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport, base_url=base_url)


# ══════════════════════════════ 1. exchange_oauth_code ══════════════════════════════


@pytest.mark.asyncio
@pytest.mark.unit
async def test_exchange_oauth_code_success() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://backboard.railway.com/oauth/token"
        assert request.method == "POST"
        content_str = request.content.decode("utf-8")
        if request.headers.get("content-type", "").startswith("application/x-www-form-urlencoded"):
            body = dict(urllib.parse.parse_qsl(content_str))
        else:
            body = json.loads(content_str)
        assert body["code"] == "auth_code_123"
        assert body["client_id"] == "rw_client_1"
        assert body["client_secret"] == "rw_secret_1"
        assert body["grant_type"] == "authorization_code"
        assert request.headers.get("accept") == "application/json"

        return httpx.Response(
            200,
            json={
                "access_token": "rw_access_token_abc",
                "token_type": "bearer",
                "refresh_token": "rw_refresh_token_xyz",
                "expires_in": 7200,
            },
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    railway_client = RailwayHttpClient(
        client=mock_client,
        client_id="rw_client_1",
        client_secret="rw_secret_1",
    )

    # Act
    token: DeploymentOAuthToken = await railway_client.exchange_oauth_code("auth_code_123")

    # Assert
    assert token.access_token == "rw_access_token_abc"
    assert token.token_type == "bearer"
    assert token.refresh_token == "rw_refresh_token_xyz"
    assert token.expires_in == 7200


@pytest.mark.asyncio
@pytest.mark.unit
async def test_exchange_oauth_code_long_code_exchanges_normally() -> None:
    # Arrange: Código largo de 64 caracteres típico de OAuth2
    long_code = "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2"

    def handler(request: httpx.Request) -> httpx.Response:
        content_str = request.content.decode("utf-8")
        body = dict(urllib.parse.parse_qsl(content_str))
        assert body["code"] == long_code
        return httpx.Response(
            200,
            json={
                "access_token": "rw_real_access_token_from_exchange",
                "token_type": "bearer",
            },
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    railway_client = RailwayHttpClient(
        client=mock_client,
        client_id="rw_client_1",
        client_secret="rw_secret_1",
    )

    # Act
    token = await railway_client.exchange_oauth_code(long_code)

    # Assert: Se intercambió mediante HTTP y no se devolvió el código crudo
    assert token.access_token == "rw_real_access_token_from_exchange"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_exchange_oauth_code_raises_on_error_payload() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "error": "invalid_grant",
                "error_description": "El código de autorización es inválido o expiró",
            },
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentAuthenticationError) as exc_info:
        await railway_client.exchange_oauth_code("invalid_code")

    assert "invalid_grant" in str(exc_info.value)
    assert "El código de autorización es inválido o expiró" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_exchange_oauth_code_raises_when_access_token_missing() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"token_type": "bearer"})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentAuthenticationError) as exc_info:
        await railway_client.exchange_oauth_code("code_no_token")

    assert "no devolvió un token de acceso válido" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_exchange_oauth_code_raises_on_http_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="Bad Request")

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentApiError) as exc_info:
        await railway_client.exchange_oauth_code("bad_req_code")

    assert "400" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_exchange_oauth_code_raises_on_timeout() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("OAuth timeout")

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentApiError) as exc_info:
        await railway_client.exchange_oauth_code("timeout_code")

    assert "Tiempo de espera agotado al conectar con Railway OAuth" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_exchange_oauth_code_raises_on_network_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.RequestError("Network error")

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentApiError) as exc_info:
        await railway_client.exchange_oauth_code("net_err_code")

    assert "Error de red al conectar con Railway OAuth" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_exchange_oauth_code_with_redirect_uri() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        content_str = request.content.decode("utf-8")
        body = dict(urllib.parse.parse_qsl(content_str))
        assert body["code"] == "auth_code_with_uri"
        assert body["redirect_uri"] == "https://kosmo.app/perfil"
        assert body["code_verifier"] == "v" * 64
        assert body["grant_type"] == "authorization_code"

        return httpx.Response(
            200,
            json={
                "access_token": "rw_access_123",
                "token_type": "bearer",
                "refresh_token": "rw_refresh_456",
                "expires_in": 3600,
                "scope": "openid email profile workspace:admin",
            },
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    railway_client = RailwayHttpClient(
        client=mock_client,
        client_id="rw_client_1",
        client_secret="rw_secret_1",
    )

    # Act
    token: DeploymentOAuthToken = await railway_client.exchange_oauth_code(
        "auth_code_with_uri",
        redirect_uri="https://kosmo.app/perfil",
        code_verifier="v" * 64,
    )

    # Assert
    assert token.access_token == "rw_access_123"
    assert token.refresh_token == "rw_refresh_456"
    assert token.expires_in == 3600
    assert "workspace:admin" in token.scope


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_authenticated_user_success() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).endswith("/oauth/me")
        assert request.headers.get("authorization") == "Bearer valid_token"
        return httpx.Response(
            200,
            json={
                "sub": "user_railway_123",
                "name": "Jane Developer",
                "email": "jane@example.com",
            },
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    railway_client = RailwayHttpClient(client=mock_client)

    # Act
    user_info = await railway_client.get_authenticated_user("valid_token")

    # Assert
    assert user_info["sub"] == "user_railway_123"
    assert user_info["name"] == "Jane Developer"
    assert user_info["email"] == "jane@example.com"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_authenticated_user_unauthorized() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentAuthenticationError) as exc_info:
        await railway_client.get_authenticated_user("expired_token")

    assert "Token de Railway inválido o expirado" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_refresh_access_token_success() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://backboard.railway.com/oauth/token"
        content_str = request.content.decode("utf-8")
        body = dict(urllib.parse.parse_qsl(content_str))
        assert body["grant_type"] == "refresh_token"
        assert body["refresh_token"] == "valid_refresh_token"

        return httpx.Response(
            200,
            json={
                "access_token": "new_access_token",
                "token_type": "bearer",
                "refresh_token": "rotated_refresh_token",
                "expires_in": 3600,
                "scope": "openid email profile workspace:admin",
            },
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    railway_client = RailwayHttpClient(
        client=mock_client,
        client_id="rw_client_1",
        client_secret="rw_secret_1",
    )

    # Act
    new_token = await railway_client.refresh_access_token("valid_refresh_token")

    # Assert
    assert new_token.access_token == "new_access_token"
    assert new_token.refresh_token == "rotated_refresh_token"
    assert new_token.expires_in == 3600


@pytest.mark.asyncio
@pytest.mark.unit
async def test_refresh_access_token_raises_on_invalid_token() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": "invalid_grant",
                "error_description": "Refresh token is expired or revoked",
            },
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentAuthenticationError) as exc_info:
        await railway_client.refresh_access_token("revoked_refresh_token")

    assert "Fallo al renovar token de Railway" in str(exc_info.value)


# ══════════════════════════════ 2. create_service ══════════════════════════════


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_service_success() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/services"
        assert request.method == "POST"
        assert request.headers.get("authorization") == "Bearer rw_token_123"
        body = json.loads(request.content.decode("utf-8"))
        assert body["repo_url"] == "https://github.com/octocat/my-app"
        assert len(body["env_vars"]) == 1
        assert body["env_vars"][0]["key"] == "NODE_ENV"
        assert body["env_vars"][0]["value"] == "production"
        assert len(body["ports"]) == 1
        assert body["ports"][0]["port"] == 3000

        return httpx.Response(
            201,
            json={
                "id": "srv_01HTXYZ9876543210ABC",
                "name": "my-app",
                "status": "building",
            },
        )

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act
    service_id = await railway_client.create_service(
        token="rw_token_123",
        repo_url="https://github.com/octocat/my-app",
        env_vars=[EnvironmentVariable(key="NODE_ENV", value="production")],
        ports=[PortSpec(port=3000)],
    )

    # Assert
    assert service_id == "srv_01HTXYZ9876543210ABC"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_service_graphql_response_support() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/services"
        return httpx.Response(
            200,
            json={
                "data": {
                    "serviceCreate": {
                        "id": "srv_gql_12345",
                    }
                }
            },
        )

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act
    service_id = await railway_client.create_service(
        token="rw_token_123",
        repo_url="https://github.com/octocat/my-app",
        env_vars=[],
        ports=[],
    )

    # Assert
    assert service_id == "srv_gql_12345"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_service_raises_on_auth_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Invalid token"})

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentAuthenticationError) as exc_info:
        await railway_client.create_service(
            token="invalid_token",
            repo_url="https://github.com/octocat/app",
            env_vars=[],
            ports=[],
        )

    assert "Token de acceso de Railway inválido o expirado" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_service_raises_on_rate_limit() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            headers={"x-ratelimit-remaining": "0"},
            json={"message": "Rate limit exceeded"},
        )

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentRateLimitError) as exc_info:
        await railway_client.create_service(
            token="rw_token",
            repo_url="https://github.com/octocat/app",
            env_vars=[],
            ports=[],
        )

    assert "Límite de solicitudes de la API de Railway excedido" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_service_raises_on_invalid_configuration() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={"message": "Invalid repository URL format"},
        )

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentConfigurationError) as exc_info:
        await railway_client.create_service(
            token="rw_token",
            repo_url="invalid_url",
            env_vars=[],
            ports=[],
        )

    assert "Configuración inválida en Railway" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_service_raises_when_no_id_returned() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok"})

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentApiError) as exc_info:
        await railway_client.create_service(
            token="rw_token",
            repo_url="https://github.com/octocat/app",
            env_vars=[],
            ports=[],
        )

    assert "no devolvió un ID de servicio válido" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_service_raises_on_timeout() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Create service timeout")

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentApiError) as exc_info:
        await railway_client.create_service(
            token="rw_token",
            repo_url="https://github.com/octocat/app",
            env_vars=[],
            ports=[],
        )

    assert "Tiempo de espera agotado" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_service_graphql_service_response_support() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/services"
        return httpx.Response(
            200,
            json={
                "data": {
                    "service": {
                        "id": "srv_direct_service_obj",
                    }
                }
            },
        )

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act
    service_id = await railway_client.create_service(
        token="rw_token_123",
        repo_url="https://github.com/octocat/my-app",
        env_vars=[],
        ports=[],
    )

    # Assert
    assert service_id == "srv_direct_service_obj"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_service_raises_on_network_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.RequestError("Network error during service creation")

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentApiError) as exc_info:
        await railway_client.create_service(
            token="rw_token",
            repo_url="https://github.com/octocat/app",
            env_vars=[],
            ports=[],
        )

    assert "Error de red al conectar con Railway" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_service_raises_on_permission_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "Forbidden access"})

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentPermissionError) as exc_info:
        await railway_client.create_service(
            token="rw_token",
            repo_url="https://github.com/octocat/app",
            env_vars=[],
            ports=[],
        )

    assert "Permisos insuficientes en Railway" in str(exc_info.value)


# ══════════════════════════════ 3. configure_volume ══════════════════════════════


@pytest.mark.asyncio
@pytest.mark.unit
async def test_configure_volume_success() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/services/srv_123/volumes"
        assert request.method == "POST"
        assert request.headers.get("authorization") == "Bearer rw_token_123"
        body = json.loads(request.content.decode("utf-8"))
        assert body["mount_path"] == "/data/db.sqlite"
        assert body["size_mb"] == 512

        return httpx.Response(201, json={"status": "volume_created"})

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act
    await railway_client.configure_volume(
        token="rw_token_123",
        service_id="srv_123",
        volume=VolumeConfig(mount_path="/data/db.sqlite", size_mb=512),
    )

    # Assert - completed without raising


@pytest.mark.asyncio
@pytest.mark.unit
async def test_configure_volume_raises_on_auth_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Unauthorized"})

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentAuthenticationError):
        await railway_client.configure_volume(
            token="bad_token",
            service_id="srv_123",
            volume=VolumeConfig(mount_path="/data"),
        )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_configure_volume_raises_on_rate_limit() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, headers={"x-ratelimit-remaining": "0"}, json={"message": "rate limit"})

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentRateLimitError):
        await railway_client.configure_volume(
            token="rw_token",
            service_id="srv_123",
            volume=VolumeConfig(mount_path="/data"),
        )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_configure_volume_raises_on_not_found() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Service not found"})

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentResourceNotFoundError) as exc_info:
        await railway_client.configure_volume(
            token="rw_token",
            service_id="srv_nonexistent",
            volume=VolumeConfig(mount_path="/data"),
        )

    assert "no fue encontrado" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_configure_volume_raises_on_invalid_config() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"message": "Invalid mount path"})

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentConfigurationError) as exc_info:
        await railway_client.configure_volume(
            token="rw_token",
            service_id="srv_123",
            volume=VolumeConfig(mount_path="invalid-path"),
        )

    assert "Configuración inválida en Railway" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_configure_volume_raises_on_timeout() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Volume timeout")

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentApiError) as exc_info:
        await railway_client.configure_volume(
            token="rw_token",
            service_id="srv_123",
            volume=VolumeConfig(mount_path="/data"),
        )

    assert "Tiempo de espera agotado" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_configure_volume_raises_on_network_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.RequestError("Volume network error")

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentApiError) as exc_info:
        await railway_client.configure_volume(
            token="rw_token",
            service_id="srv_123",
            volume=VolumeConfig(mount_path="/data"),
        )

    assert "Error de red al conectar con Railway" in str(exc_info.value)


# ══════════════════════════════ 4. trigger_deployment ══════════════════════════════


@pytest.mark.asyncio
@pytest.mark.unit
async def test_trigger_deployment_success() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/services/srv_123/deploy"
        assert request.method == "POST"
        assert request.headers.get("authorization") == "Bearer rw_token_123"
        return httpx.Response(200, json={"status": "deployment_triggered"})

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act
    await railway_client.trigger_deployment(
        token="rw_token_123",
        service_id="srv_123",
    )

    # Assert - completed without raising


@pytest.mark.asyncio
@pytest.mark.unit
async def test_trigger_deployment_raises_on_auth_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad token"})

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentAuthenticationError):
        await railway_client.trigger_deployment(
            token="bad_token",
            service_id="srv_123",
        )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_trigger_deployment_raises_on_not_found() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Service not found"})

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentResourceNotFoundError):
        await railway_client.trigger_deployment(
            token="rw_token",
            service_id="srv_missing",
        )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_trigger_deployment_raises_on_rate_limit() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, headers={"x-ratelimit-remaining": "0"}, json={"message": "rate limit"})

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentRateLimitError):
        await railway_client.trigger_deployment(
            token="rw_token",
            service_id="srv_123",
        )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_trigger_deployment_raises_on_permission_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "Insufficient permissions to deploy"})

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentPermissionError) as exc_info:
        await railway_client.trigger_deployment(
            token="rw_token",
            service_id="srv_123",
        )

    assert "Permisos insuficientes en Railway" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_trigger_deployment_raises_on_server_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentApiError) as exc_info:
        await railway_client.trigger_deployment(
            token="rw_token",
            service_id="srv_123",
        )

    assert "500" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_trigger_deployment_raises_on_timeout() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Deploy timeout")

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentApiError) as exc_info:
        await railway_client.trigger_deployment(
            token="rw_token",
            service_id="srv_123",
        )

    assert "Tiempo de espera agotado" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_trigger_deployment_raises_on_network_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.RequestError("Deploy network error")

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentApiError) as exc_info:
        await railway_client.trigger_deployment(
            token="rw_token",
            service_id="srv_123",
        )

    assert "Error de red al conectar con Railway" in str(exc_info.value)


# ══════════════════════════════ 5. get_service_status ══════════════════════════════


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_service_status_published() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/services/srv_123"
        assert request.headers.get("authorization") == "Bearer rw_token_123"
        return httpx.Response(
            200,
            json={
                "id": "srv_123",
                "status": "ready",
                "public_url": "https://kosmo-gestion-inventarios.up.railway.app",
                "build_logs_url": "https://railway.com/project/prj-1/service/srv_123/logs",
            },
        )

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act
    status, public_url, logs_url = await railway_client.get_service_status(
        token="rw_token_123",
        service_id="srv_123",
    )

    # Assert
    assert status == DeploymentStatus.PUBLISHED
    assert public_url == "https://kosmo-gestion-inventarios.up.railway.app"
    assert logs_url == "https://railway.com/project/prj-1/service/srv_123/logs"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_service_status_graphql_service_support() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/services/srv_123"
        return httpx.Response(
            200,
            json={
                "data": {
                    "service": {
                        "id": "srv_123",
                        "status": "live",
                        "url": "https://live-app.up.railway.app",
                        "logs_url": "https://railway.com/logs/123",
                    }
                }
            },
        )

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act
    status, public_url, logs_url = await railway_client.get_service_status(
        token="rw_token_123",
        service_id="srv_123",
    )

    # Assert
    assert status == DeploymentStatus.PUBLISHED
    assert public_url == "https://live-app.up.railway.app"
    assert logs_url == "https://railway.com/logs/123"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_service_status_queries_latest_deployment_through_root_graphql_field() -> None:
    """Railway exposes deployments at the GraphQL root, not below Service."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/graphql/v2"
        payload = json.loads(request.content.decode("utf-8"))
        query = payload["query"]

        if "query ServiceStatus" in query:
            calls.append("service")
            assert payload["variables"] == {"id": "srv_123"}
            return httpx.Response(
                200,
                json={
                    "data": {
                        "service": {
                            "id": "srv_123",
                            "projectId": "prj_123",
                            "serviceInstances": {"edges": []},
                        }
                    }
                },
            )

        if "query DeploymentStatus" in query:
            calls.append("deployments")
            assert payload["variables"] == {"input": {"projectId": "prj_123", "serviceId": "srv_123"}}
            return httpx.Response(
                200,
                json={
                    "data": {
                        "deployments": {
                            "edges": [
                                {
                                    "node": {
                                        "id": "dep_123",
                                        "status": "SUCCESS",
                                        "staticUrl": "kosmo.up.railway.app",
                                    }
                                }
                            ]
                        }
                    }
                },
            )

        pytest.fail(f"Consulta GraphQL inesperada: {query}")

    railway_client = RailwayHttpClient(client=_create_mock_client(handler))

    status, public_url, logs_url = await railway_client.get_service_status(
        token="rw_token_123",
        service_id="srv_123",
    )

    assert calls == ["service", "deployments"]
    assert status == DeploymentStatus.PUBLISHED
    assert public_url == "https://kosmo.up.railway.app"
    assert logs_url is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_service_status_graphql_failed_returns_logs_url() -> None:
    # Arrange
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/graphql/v2"
        payload = json.loads(request.content.decode("utf-8"))
        query = payload["query"]

        if "query ServiceStatus" in query:
            calls.append("service")
            return httpx.Response(
                200,
                json={
                    "data": {
                        "service": {
                            "id": "srv_123",
                            "projectId": "prj_abc",
                            "serviceInstances": {"edges": []},
                        }
                    }
                },
            )

        if "query DeploymentStatus" in query:
            calls.append("deployments")
            return httpx.Response(
                200,
                json={
                    "data": {
                        "deployments": {
                            "edges": [
                                {
                                    "node": {
                                        "id": "dep_999",
                                        "status": "FAILED",
                                        "url": None,
                                        "staticUrl": None,
                                    }
                                }
                            ]
                        }
                    }
                },
            )

        pytest.fail(f"Consulta GraphQL inesperada: {query}")

    railway_client = RailwayHttpClient(client=_create_mock_client(handler))

    # Act
    status, public_url, logs_url = await railway_client.get_service_status(
        token="rw_token_123",
        service_id="srv_123",
    )

    # Assert
    assert calls == ["service", "deployments"]
    assert status == DeploymentStatus.FAILED
    assert public_url is None
    assert logs_url == "https://railway.com/project/prj_abc/service/srv_123?id=dep_999"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_service_status_building() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/services/srv_123"
        return httpx.Response(
            200,
            json={
                "id": "srv_123",
                "status": "building",
                "deploy_url": None,
                "error_log_url": None,
            },
        )

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act
    status, public_url, logs_url = await railway_client.get_service_status(
        token="rw_token_123",
        service_id="srv_123",
    )

    # Assert
    assert status == DeploymentStatus.BUILDING
    assert public_url is None
    assert logs_url is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_service_status_failed() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/services/srv_123"
        return httpx.Response(
            200,
            json={
                "id": "srv_123",
                "status": "crashed",
                "public_url": None,
                "error_log_url": "https://railway.com/logs/build-failed",
            },
        )

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act
    status, public_url, logs_url = await railway_client.get_service_status(
        token="rw_token_123",
        service_id="srv_123",
    )

    # Assert
    assert status == DeploymentStatus.FAILED
    assert public_url is None
    assert logs_url == "https://railway.com/logs/build-failed"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_service_status_unknown_status_defaults_to_not_created() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/services/srv_123"
        return httpx.Response(
            200,
            json={
                "id": "srv_123",
                "status": "some_unknown_state",
            },
        )

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act
    status, public_url, logs_url = await railway_client.get_service_status(
        token="rw_token_123",
        service_id="srv_123",
    )

    # Assert
    assert status == DeploymentStatus.NOT_CREATED
    assert public_url is None
    assert logs_url is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_service_status_returns_not_created_on_404() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Service not found"})

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act
    status, public_url, logs_url = await railway_client.get_service_status(
        token="rw_token",
        service_id="srv_not_exist",
    )

    # Assert
    assert status == DeploymentStatus.NOT_CREATED
    assert public_url is None
    assert logs_url is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_service_status_raises_on_auth_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad token"})

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentAuthenticationError):
        await railway_client.get_service_status(
            token="bad_token",
            service_id="srv_123",
        )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_service_status_raises_on_rate_limit() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, headers={"x-ratelimit-remaining": "0"}, json={"message": "rate limit"})

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentRateLimitError):
        await railway_client.get_service_status(
            token="rw_token",
            service_id="srv_123",
        )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_service_status_raises_on_permission_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "Forbidden"})

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentPermissionError):
        await railway_client.get_service_status(
            token="rw_token",
            service_id="srv_123",
        )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_service_status_raises_on_config_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"message": "Unprocessable entity"})

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentConfigurationError):
        await railway_client.get_service_status(
            token="rw_token",
            service_id="srv_123",
        )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_service_status_raises_on_server_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentApiError) as exc_info:
        await railway_client.get_service_status(
            token="rw_token",
            service_id="srv_123",
        )

    assert "500" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_service_status_raises_on_timeout() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Status timeout")

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentApiError) as exc_info:
        await railway_client.get_service_status(
            token="rw_token",
            service_id="srv_123",
        )

    assert "Tiempo de espera agotado" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_service_status_raises_on_network_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.RequestError("Status network error")

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentApiError) as exc_info:
        await railway_client.get_service_status(
            token="rw_token",
            service_id="srv_123",
        )

    assert "Error de red al conectar con Railway" in str(exc_info.value)


# ══════════════════════════════ 6. Lifecycle & context manager ══════════════════════════════


@pytest.mark.asyncio
@pytest.mark.unit
async def test_client_context_manager_and_aclose() -> None:
    # Arrange & Act
    async with RailwayHttpClient() as client:
        # Assert
        assert client is not None


# ══════════════════════════════ 7. delete_service ══════════════════════════════


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_service_success_rest() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/services/srv_delete_123"
        assert request.method == "DELETE"
        assert request.headers.get("authorization") == "Bearer rw_token_del"
        return httpx.Response(204)

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act
    deleted = await railway_client.delete_service(token="rw_token_del", service_id="srv_delete_123")

    # Assert
    assert deleted is True


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_service_404_idempotent() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/services/srv_not_found"
        assert request.method == "DELETE"
        return httpx.Response(404, json={"error": "Service not found"})

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act
    deleted = await railway_client.delete_service(token="rw_token", service_id="srv_not_found")

    # Assert
    assert deleted is True


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_service_graphql_project_delete() -> None:
    # Arrange
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        content = json.loads(request.content.decode("utf-8"))
        query = content.get("query", "")
        if "query ServiceProject" in query:
            calls.append("query_project")
            return httpx.Response(
                200,
                json={"data": {"service": {"id": "srv_gql_1", "projectId": "prj_rw_1"}}},
            )
        if "mutation ProjectDelete" in query:
            calls.append("delete_project")
            return httpx.Response(200, json={"data": {"projectDelete": True}})
        return httpx.Response(400)

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act
    deleted = await railway_client.delete_service(token="rw_token", service_id="srv_gql_1")

    # Assert
    assert deleted is True
    assert calls == ["query_project", "delete_project"]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_service_graphql_service_delete_fallback() -> None:
    # Arrange
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        content = json.loads(request.content.decode("utf-8"))
        query = content.get("query", "")
        if "query ServiceProject" in query:
            calls.append("query_project")
            return httpx.Response(
                200,
                json={"data": {"service": {"id": "srv_gql_2", "projectId": None}}},
            )
        if "mutation ServiceDelete" in query:
            calls.append("delete_service")
            return httpx.Response(200, json={"data": {"serviceDelete": True}})
        return httpx.Response(400)

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act
    deleted = await railway_client.delete_service(token="rw_token", service_id="srv_gql_2")

    # Assert
    assert deleted is True
    assert calls == ["query_project", "delete_service"]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_service_raises_on_auth_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Unauthorized"})

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentAuthenticationError):
        await railway_client.delete_service(token="bad_token", service_id="srv_1")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_service_raises_on_network_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.RequestError("Network connection reset")

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(DeploymentApiError) as exc_info:
        await railway_client.delete_service(token="rw_token", service_id="srv_net_err")

    assert "Error de red al conectar con Railway" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_service_graphql_full_flow() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/graphql/v2"
        body = json.loads(request.content.decode("utf-8"))
        query = body.get("query", "")
        if "mutation ProjectCreate" in query:
            calls.append("projectCreate")
            assert "baseEnvironmentId" in query
            return httpx.Response(
                200,
                json={
                    "data": {
                        "projectCreate": {
                            "id": "prj_gql_123",
                            "name": "my-app",
                            "baseEnvironmentId": "env_base_456",
                        }
                    }
                },
            )
        if "mutation ServiceCreate" in query:
            calls.append("serviceCreate")
            assert body["variables"]["input"]["projectId"] == "prj_gql_123"
            assert body["variables"]["input"]["name"] == "my-app-production"
            return httpx.Response(
                200,
                json={"data": {"serviceCreate": {"id": "srv_gql_789", "name": "my-app"}}},
            )
        if "mutation ServiceDomainCreate" in query:
            calls.append("serviceDomainCreate")
            assert body["variables"]["input"]["environmentId"] == "env_base_456"
            assert body["variables"]["input"]["serviceId"] == "srv_gql_789"
            return httpx.Response(200, json={"data": {"serviceDomainCreate": {"domain": "myapp.up.railway.app"}}})
        if "mutation VariableCollectionUpsert" in query:
            calls.append("variableCollectionUpsert")
            return httpx.Response(200, json={"data": {"variableCollectionUpsert": True}})
        return httpx.Response(400, json={"message": "Unknown query"})

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    service_id = await railway_client.create_service(
        token="rw_token_live",
        repo_url="https://github.com/my-org/my-app",
        env_vars=[EnvironmentVariable(key="PORT", value="8000", is_secret=False)],
        ports=[PortSpec(port=8000, protocol="HTTP")],
        service_name="my-app-production",
    )

    assert service_id == "srv_gql_789"
    assert "projectCreate" in calls
    assert "serviceCreate" in calls
    assert "serviceDomainCreate" in calls
    assert "variableCollectionUpsert" in calls


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_service_graphql_error_does_not_fall_back_to_rest() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # Nunca debería llamar a /v1/services
        assert request.url.path == "/graphql/v2"
        return httpx.Response(
            400,
            json={
                "errors": [
                    {
                        "message": "Project limit reached for Trial plan",
                    }
                ]
            },
        )

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    with pytest.raises(DeploymentApiError) as exc_info:
        await railway_client.create_service(
            token="rw_token_limit",
            repo_url="https://github.com/my-org/my-app",
            env_vars=[],
            ports=[],
        )

    assert "Project limit reached" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_trigger_deployment_graphql_flow() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/graphql/v2"
        body = json.loads(request.content.decode("utf-8"))
        query = body.get("query", "")
        if "query GetServiceEnvironment" in query:
            calls.append("get_env")
            return httpx.Response(
                200,
                json={
                    "data": {
                        "service": {
                            "id": "srv_123",
                            "projectId": "prj_123",
                            "serviceInstances": {
                                "edges": [{"node": {"environmentId": "env_prod_999"}}],
                            },
                        }
                    }
                },
            )
        if "mutation ServiceInstanceDeploy" in query:
            calls.append("deploy")
            assert body["variables"]["serviceId"] == "srv_123"
            assert body["variables"]["environmentId"] == "env_prod_999"
            return httpx.Response(200, json={"data": {"serviceInstanceDeploy": True}})
        return httpx.Response(400)

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    await railway_client.trigger_deployment(token="rw_token", service_id="srv_123")
    assert calls == ["get_env", "deploy"]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_configure_volume_graphql_flow() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/graphql/v2"
        body = json.loads(request.content.decode("utf-8"))
        query = body.get("query", "")
        if "query GetServiceProject" in query:
            calls.append("get_project")
            return httpx.Response(
                200,
                json={"data": {"service": {"id": "srv_123", "projectId": "prj_abc"}}},
            )
        if "mutation VolumeCreate" in query:
            calls.append("volume_create")
            assert body["variables"]["input"]["projectId"] == "prj_abc"
            assert body["variables"]["input"]["serviceId"] == "srv_123"
            assert body["variables"]["input"]["mountPath"] == "/data"
            return httpx.Response(200, json={"data": {"volumeCreate": {"id": "vol_123"}}})
        return httpx.Response(400)

    mock_client = _create_mock_client(handler)
    railway_client = RailwayHttpClient(client=mock_client)

    await railway_client.configure_volume(
        token="rw_token",
        service_id="srv_123",
        volume=VolumeConfig(mount_path="/data", size_mb=1024),
    )
    assert calls == ["get_project", "volume_create"]
