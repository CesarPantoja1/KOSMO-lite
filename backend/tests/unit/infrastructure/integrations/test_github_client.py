from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from kosmo.contracts.integrations.github import (
    GitHubApiError,
    GitHubAuthenticationError,
    GitHubOAuthToken,
    GitHubPermissionError,
    GitHubRateLimitError,
    GitHubRepository,
    GitHubRepositoryAlreadyExistsError,
    GitHubUser,
)
from kosmo.infrastructure.integrations.github_client import GitHubHttpClient


def _create_mock_client(
    handler: Any,
    base_url: str = "https://api.github.com",
) -> httpx.AsyncClient:
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport, base_url=base_url)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_authenticated_user_success() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/user"
        assert request.headers.get("authorization") == "Bearer gho_test_token"
        assert request.headers.get("accept") == "application/vnd.github+json"
        assert request.headers.get("x-github-api-version") == "2022-11-28"
        return httpx.Response(
            200,
            json={
                "login": "octocat",
                "id": 583231,
                "name": "The Octocat",
                "email": "octocat@github.com",
                "avatar_url": "https://avatars.githubusercontent.com/u/583231",
                "html_url": "https://github.com/octocat",
            },
        )

    mock_client = _create_mock_client(handler)
    github_client = GitHubHttpClient(client=mock_client)

    # Act
    user: GitHubUser = await github_client.get_authenticated_user("gho_test_token")

    # Assert
    assert user.login == "octocat"
    assert user.id == 583231
    assert user.name == "The Octocat"
    assert user.email == "octocat@github.com"
    assert user.avatar_url == "https://avatars.githubusercontent.com/u/583231"
    assert user.html_url == "https://github.com/octocat"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_authenticated_user_raises_when_unauthorized() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad credentials"})

    mock_client = _create_mock_client(handler)
    github_client = GitHubHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(GitHubAuthenticationError) as exc_info:
        await github_client.get_authenticated_user("invalid_token")

    assert "Token de acceso de GitHub inválido o expirado" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_authenticated_user_raises_when_rate_limit_exceeded() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            headers={"x-ratelimit-remaining": "0"},
            json={"message": "API rate limit exceeded for user"},
        )

    mock_client = _create_mock_client(handler)
    github_client = GitHubHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(GitHubRateLimitError) as exc_info:
        await github_client.get_authenticated_user("token_rate_limited")

    assert "Límite de solicitudes de la API de GitHub excedido" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_check_repository_exists_returns_true_when_found() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/octocat/my-app"
        return httpx.Response(200, json={"id": 1, "name": "my-app"})

    mock_client = _create_mock_client(handler)
    github_client = GitHubHttpClient(client=mock_client)

    # Act
    exists = await github_client.check_repository_exists("gho_test_token", "octocat", "my-app")

    # Assert
    assert exists is True


@pytest.mark.asyncio
@pytest.mark.unit
async def test_check_repository_exists_returns_false_when_not_found() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/octocat/nonexistent-repo"
        return httpx.Response(404, json={"message": "Not Found"})

    mock_client = _create_mock_client(handler)
    github_client = GitHubHttpClient(client=mock_client)

    # Act
    exists = await github_client.check_repository_exists("gho_test_token", "octocat", "nonexistent-repo")

    # Assert
    assert exists is False


@pytest.mark.asyncio
@pytest.mark.unit
async def test_check_repository_exists_raises_on_auth_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad credentials"})

    mock_client = _create_mock_client(handler)
    github_client = GitHubHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(GitHubAuthenticationError):
        await github_client.check_repository_exists("bad_token", "octocat", "my-app")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_repository_success() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/octocat/hello-world"
        return httpx.Response(
            200,
            json={
                "id": 1296269,
                "name": "hello-world",
                "full_name": "octocat/hello-world",
                "owner": {"login": "octocat"},
                "html_url": "https://github.com/octocat/hello-world",
                "clone_url": "https://github.com/octocat/hello-world.git",
                "private": True,
                "default_branch": "main",
                "description": "This is your first repo!",
            },
        )

    mock_client = _create_mock_client(handler)
    github_client = GitHubHttpClient(client=mock_client)

    # Act
    repo: GitHubRepository | None = await github_client.get_repository("gho_test_token", "octocat", "hello-world")

    # Assert
    assert repo is not None
    assert repo.id == 1296269
    assert repo.name == "hello-world"
    assert repo.full_name == "octocat/hello-world"
    assert repo.owner == "octocat"
    assert repo.html_url == "https://github.com/octocat/hello-world"
    assert repo.clone_url == "https://github.com/octocat/hello-world.git"
    assert repo.is_private is True
    assert repo.default_branch == "main"
    assert repo.description == "This is your first repo!"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_repository_returns_none_when_not_found() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    mock_client = _create_mock_client(handler)
    github_client = GitHubHttpClient(client=mock_client)

    # Act
    repo = await github_client.get_repository("gho_test_token", "octocat", "missing-repo")

    # Assert
    assert repo is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_repository_success_public_default() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/user/repos"
        assert request.method == "POST"
        body = json.loads(request.content.decode("utf-8"))
        assert body["name"] == "kosmo-gestion-inventarios"
        assert body["description"] == "App generada por KOSMO"
        assert body["private"] is False
        assert body["auto_init"] is False

        return httpx.Response(
            201,
            json={
                "id": 998877,
                "name": "kosmo-gestion-inventarios",
                "full_name": "octocat/kosmo-gestion-inventarios",
                "owner": {"login": "octocat"},
                "html_url": "https://github.com/octocat/kosmo-gestion-inventarios",
                "clone_url": "https://github.com/octocat/kosmo-gestion-inventarios.git",
                "private": False,
                "default_branch": "main",
                "description": "App generada por KOSMO",
            },
        )

    mock_client = _create_mock_client(handler)
    github_client = GitHubHttpClient(client=mock_client)

    # Act
    repo: GitHubRepository = await github_client.create_repository(
        token="gho_token",
        name="kosmo-gestion-inventarios",
        description="App generada por KOSMO",
    )

    # Assert
    assert repo.id == 998877
    assert repo.name == "kosmo-gestion-inventarios"
    assert repo.full_name == "octocat/kosmo-gestion-inventarios"
    assert repo.owner == "octocat"
    assert repo.html_url == "https://github.com/octocat/kosmo-gestion-inventarios"
    assert repo.clone_url == "https://github.com/octocat/kosmo-gestion-inventarios.git"
    assert repo.is_private is False
    assert repo.description == "App generada por KOSMO"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_repository_success_public() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        assert body["private"] is False
        return httpx.Response(
            201,
            json={
                "id": 998878,
                "name": "kosmo-public-app",
                "full_name": "octocat/kosmo-public-app",
                "owner": {"login": "octocat"},
                "html_url": "https://github.com/octocat/kosmo-public-app",
                "clone_url": "https://github.com/octocat/kosmo-public-app.git",
                "private": False,
                "default_branch": "main",
                "description": "",
            },
        )

    mock_client = _create_mock_client(handler)
    github_client = GitHubHttpClient(client=mock_client)

    # Act
    repo: GitHubRepository = await github_client.create_repository(
        token="gho_token",
        name="kosmo-public-app",
        is_private=False,
    )

    # Assert
    assert repo.is_private is False
    assert repo.name == "kosmo-public-app"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_repository_raises_when_name_already_exists() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "message": "Repository creation failed.",
                "errors": [
                    {
                        "resource": "Repository",
                        "code": "custom",
                        "field": "name",
                        "message": "name already exists on this account",
                    }
                ],
            },
        )

    mock_client = _create_mock_client(handler)
    github_client = GitHubHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(GitHubRepositoryAlreadyExistsError) as exc_info:
        await github_client.create_repository(
            token="gho_token",
            name="existing-repo",
        )

    assert "existing-repo" in str(exc_info.value)
    assert "ya existe en la cuenta de GitHub" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_repository_raises_when_permission_denied() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"message": "Resource not accessible by personal access token"},
        )

    mock_client = _create_mock_client(handler)
    github_client = GitHubHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(GitHubPermissionError) as exc_info:
        await github_client.create_repository(
            token="gho_token",
            name="repo-no-perm",
        )

    assert "Permisos insuficientes en GitHub" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_exchange_oauth_code_success() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://github.com/login/oauth/access_token"
        assert request.method == "POST"
        body = json.loads(request.content.decode("utf-8"))
        assert body["client_id"] == "client_123"
        assert body["client_secret"] == "secret_456"
        assert body["code"] == "code_789"
        assert body["redirect_uri"] == "https://kosmo.dev/callback"
        assert body["code_verifier"] == "v" * 64

        return httpx.Response(
            200,
            json={
                "access_token": "gho_16C7e42F292c6912E7710c838347Ae178B4a",
                "token_type": "bearer",
                "scope": "repo,user",
            },
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    github_client = GitHubHttpClient(client=mock_client)

    # Act
    token: GitHubOAuthToken = await github_client.exchange_oauth_code(
        client_id="client_123",
        client_secret="secret_456",
        code="code_789",
        redirect_uri="https://kosmo.dev/callback",
        code_verifier="v" * 64,
    )

    # Assert
    assert token.access_token == "gho_16C7e42F292c6912E7710c838347Ae178B4a"
    assert token.token_type == "bearer"
    assert token.scope == "repo,user"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_exchange_oauth_code_raises_on_github_oauth_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "error": "bad_verification_code",
                "error_description": "The code passed is incorrect or has expired.",
                "error_uri": "https://docs.github.com/apps/managing-oauth-apps/troubleshooting-oauth-app-access-token-request-errors/#bad-verification-code",
            },
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    github_client = GitHubHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(GitHubAuthenticationError) as exc_info:
        await github_client.exchange_oauth_code(
            client_id="client_123",
            client_secret="secret_456",
            code="expired_code",
        )

    assert "The code passed is incorrect or has expired" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_repository_success() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/octocat/my-app"
        assert request.method == "DELETE"
        return httpx.Response(204)

    mock_client = _create_mock_client(handler)
    github_client = GitHubHttpClient(client=mock_client)

    # Act
    deleted = await github_client.delete_repository("gho_token", "octocat", "my-app")

    # Assert
    assert deleted is True


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_repository_returns_false_when_not_found() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    mock_client = _create_mock_client(handler)
    github_client = GitHubHttpClient(client=mock_client)

    # Act
    deleted = await github_client.delete_repository("gho_token", "octocat", "not-found")

    # Assert
    assert deleted is False


@pytest.mark.asyncio
@pytest.mark.unit
async def test_client_handles_network_timeout() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("Connection timed out")

    mock_client = _create_mock_client(handler)
    github_client = GitHubHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(GitHubApiError) as exc_info:
        await github_client.get_authenticated_user("token")

    assert "Tiempo de espera agotado" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_authenticated_user_raises_on_server_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    mock_client = _create_mock_client(handler)
    github_client = GitHubHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(GitHubApiError) as exc_info:
        await github_client.get_authenticated_user("token")

    assert "500" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_authenticated_user_raises_on_network_request_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.RequestError("Network unreachable")

    mock_client = _create_mock_client(handler)
    github_client = GitHubHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(GitHubApiError) as exc_info:
        await github_client.get_authenticated_user("token")

    assert "Error de red al conectar con GitHub" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_check_repository_exists_raises_on_network_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    mock_client = _create_mock_client(handler)
    github_client = GitHubHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(GitHubApiError) as exc_info:
        await github_client.check_repository_exists("token", "owner", "repo")

    assert "Error de red al conectar con GitHub" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_check_repository_exists_raises_on_timeout() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Read timeout")

    mock_client = _create_mock_client(handler)
    github_client = GitHubHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(GitHubApiError) as exc_info:
        await github_client.check_repository_exists("token", "owner", "repo")

    assert "Tiempo de espera agotado" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_repository_raises_on_auth_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad credentials"})

    mock_client = _create_mock_client(handler)
    github_client = GitHubHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(GitHubAuthenticationError):
        await github_client.get_repository("bad_token", "owner", "repo")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_repository_raises_on_network_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.RequestError("Network down")

    mock_client = _create_mock_client(handler)
    github_client = GitHubHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(GitHubApiError) as exc_info:
        await github_client.get_repository("token", "owner", "repo")

    assert "Error de red al conectar con GitHub" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_repository_raises_on_timeout() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Timed out")

    mock_client = _create_mock_client(handler)
    github_client = GitHubHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(GitHubApiError) as exc_info:
        await github_client.get_repository("token", "owner", "repo")

    assert "Tiempo de espera agotado" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_repository_raises_on_timeout() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Timeout creating repo")

    mock_client = _create_mock_client(handler)
    github_client = GitHubHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(GitHubApiError) as exc_info:
        await github_client.create_repository("token", "my-repo")

    assert "Tiempo de espera agotado" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_repository_raises_on_network_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.RequestError("Connection reset")

    mock_client = _create_mock_client(handler)
    github_client = GitHubHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(GitHubApiError) as exc_info:
        await github_client.create_repository("token", "my-repo")

    assert "Error de red al conectar con GitHub" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_exchange_oauth_code_raises_when_access_token_empty() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": ""})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    github_client = GitHubHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(GitHubAuthenticationError) as exc_info:
        await github_client.exchange_oauth_code(client_id="cid", client_secret="csec", code="code")

    assert "no devolvió un token de acceso válido" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_exchange_oauth_code_raises_on_http_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="Bad Request")

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    github_client = GitHubHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(GitHubApiError) as exc_info:
        await github_client.exchange_oauth_code(client_id="cid", client_secret="csec", code="code")

    assert "400" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_exchange_oauth_code_raises_on_network_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.RequestError("Network down")

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    github_client = GitHubHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(GitHubApiError) as exc_info:
        await github_client.exchange_oauth_code(client_id="cid", client_secret="csec", code="code")

    assert "Error de red al conectar con GitHub OAuth" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_exchange_oauth_code_raises_on_timeout() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("OAuth timeout")

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    github_client = GitHubHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(GitHubApiError) as exc_info:
        await github_client.exchange_oauth_code(client_id="cid", client_secret="csec", code="code")

    assert "Tiempo de espera agotado al conectar con GitHub OAuth" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_repository_raises_on_auth_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad credentials"})

    mock_client = _create_mock_client(handler)
    github_client = GitHubHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(GitHubAuthenticationError):
        await github_client.delete_repository("bad_token", "owner", "repo")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_repository_raises_on_timeout() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Delete timeout")

    mock_client = _create_mock_client(handler)
    github_client = GitHubHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(GitHubApiError) as exc_info:
        await github_client.delete_repository("token", "owner", "repo")

    assert "Tiempo de espera agotado" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_repository_raises_on_network_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.RequestError("Network error")

    mock_client = _create_mock_client(handler)
    github_client = GitHubHttpClient(client=mock_client)

    # Act & Assert
    with pytest.raises(GitHubApiError) as exc_info:
        await github_client.delete_repository("token", "owner", "repo")

    assert "Error de red al conectar con GitHub" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_client_context_manager_and_aclose() -> None:
    # Arrange & Act
    async with GitHubHttpClient() as client:
        # Assert
        assert client is not None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_grant_app_installation_access_success_selected() -> None:
    # Arrange
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        if request.url.path == "/user/installations":
            return httpx.Response(
                200,
                json={
                    "total_count": 1,
                    "installations": [
                        {
                            "id": 12345,
                            "app_slug": "railway",
                            "repository_selection": "selected",
                        }
                    ],
                },
            )
        if request.url.path == "/user/installations/12345/repositories/999":
            return httpx.Response(204)
        return httpx.Response(404)

    mock_client = _create_mock_client(handler)
    github_client = GitHubHttpClient(client=mock_client)

    # Act
    result = await github_client.grant_app_installation_access("gho_token", 999, "railway")

    # Assert
    assert result is True
    assert "GET /user/installations" in calls
    assert "PUT /user/installations/12345/repositories/999" in calls


@pytest.mark.asyncio
@pytest.mark.unit
async def test_grant_app_installation_access_all_repositories() -> None:
    # Arrange
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        if request.url.path == "/user/installations":
            return httpx.Response(
                200,
                json={
                    "total_count": 1,
                    "installations": [
                        {
                            "id": 12345,
                            "app_slug": "railway",
                            "repository_selection": "all",
                        }
                    ],
                },
            )
        return httpx.Response(404)

    mock_client = _create_mock_client(handler)
    github_client = GitHubHttpClient(client=mock_client)

    # Act
    result = await github_client.grant_app_installation_access("gho_token", 999, "railway")

    # Assert
    assert result is True
    assert "GET /user/installations" in calls
    assert len(calls) == 1  # No necesita PUT


@pytest.mark.asyncio
@pytest.mark.unit
async def test_grant_app_installation_access_app_not_found() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user/installations":
            return httpx.Response(
                200,
                json={
                    "total_count": 1,
                    "installations": [
                        {
                            "id": 99999,
                            "app_slug": "other-app",
                            "repository_selection": "selected",
                        }
                    ],
                },
            )
        return httpx.Response(404)

    mock_client = _create_mock_client(handler)
    github_client = GitHubHttpClient(client=mock_client)

    # Act
    result = await github_client.grant_app_installation_access("gho_token", 999, "railway")

    # Assert
    assert result is False
