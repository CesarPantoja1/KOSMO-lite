import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[2] / "src"))

from kosmo.application.auth import (  # noqa: E402
    AuthorizeWithPkce,
    ExchangeAuthorizationCode,
    IssueTokenPair,
    RefreshTokenPair,
    RegisterUser,
    RevokeSession,
    VerifyAccessToken,
)
from kosmo.domain.auth import s256_challenge  # noqa: E402
from kosmo.infrastructure.api.routers.auth import router as auth_router  # noqa: E402
from kosmo.infrastructure.api.routers.schemas import router as schemas_router  # noqa: E402
from kosmo.infrastructure.security import (  # noqa: E402
    Argon2idParameters,
    Argon2idPasswordHasher,
    JoseJwtIssuer,
    JoseJwtVerifier,
    JwtSettings,
)
from tests.conftest import _PRIVATE_KEY_PEM as _PRIVATE_PEM  # noqa: E402
from tests.conftest import _PUBLIC_KEY_PEM as _PUBLIC_PEM
from tests.unit.fakes import (  # noqa: E402
    InMemoryAuditEventSink,
    InMemoryAuthorizationCodeStore,
    InMemoryLoginAttemptStore,
    InMemoryStore,
    InMemoryUserRepository,
)

_MAX_FAILURES = 10
_LOCKOUT_SECONDS = 900


@pytest.fixture
def client() -> TestClient:
    settings = JwtSettings(
        algorithm="RS256",
        issuer="kosmo-test",
        audience="kosmo-test",
        access_ttl_seconds=120,
        refresh_ttl_seconds=600,
    )
    issuer = JoseJwtIssuer(private_key_pem=_PRIVATE_PEM, settings=settings)
    verifier = JoseJwtVerifier(public_key_pem=_PUBLIC_PEM, settings=settings)
    hasher = Argon2idPasswordHasher(Argon2idParameters(memory_kib=65536, time_cost=3, parallelism=4))
    user_repository = InMemoryUserRepository()
    code_store = InMemoryAuthorizationCodeStore()
    token_store = InMemoryStore()
    attempt_store = InMemoryLoginAttemptStore()
    audit_sink = InMemoryAuditEventSink()

    issue_token_pair = IssueTokenPair(issuer=issuer, revocation_store=token_store)

    app = FastAPI()
    app.state.container = SimpleNamespace(
        redis=None,
        auth=SimpleNamespace(
            token_store=token_store,
            user_repository=user_repository,
            register_user=RegisterUser(user_repository=user_repository, password_hasher=hasher, audit_sink=audit_sink),
            authorize_with_pkce=AuthorizeWithPkce(
                user_repository=user_repository,
                password_hasher=hasher,
                authorization_code_store=code_store,
                login_attempt_store=attempt_store,
                audit_sink=audit_sink,
            ),
            exchange_authorization_code=ExchangeAuthorizationCode(
                authorization_code_store=code_store,
                issue_token_pair=issue_token_pair,
            ),
            issue_token_pair=issue_token_pair,
            verify_access_token=VerifyAccessToken(verifier=verifier, revocation_store=token_store),
            refresh_token_pair=RefreshTokenPair(
                issuer=issuer,
                verifier=verifier,
                revocation_store=token_store,
                audit_sink=audit_sink,
            ),
            revoke_session=RevokeSession(verifier=verifier, revocation_store=token_store, audit_sink=audit_sink),
        ),
    )
    app.include_router(auth_router)
    app.include_router(schemas_router)
    return TestClient(app)


def _full_login_flow(
    client: TestClient,
    *,
    email: str = "alice@example.com",
    password: str = "password-12345",
    scopes: list[str] | None = None,
) -> dict[str, Any]:
    verifier = "verifier" * 8
    challenge = s256_challenge(verifier)

    register = client.post(
        "/api/v1/auth/register",
        json={"name": "Alice", "email": email, "password": password},
    )
    assert register.status_code == 201, register.text

    authorize = client.post(
        "/api/v1/auth/authorize",
        json={
            "email": email,
            "password": password,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scopes": scopes or [],
        },
    )
    assert authorize.status_code == 201, authorize.text
    code = authorize.json()["authorization_code"]

    token = client.post(
        "/api/v1/auth/token",
        json={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
        },
    )
    assert token.status_code == 200, token.text
    return token.json()


def test_register_returns_201_and_generic_response(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"name": "Alice", "email": "alice@example.com", "password": "password-12345"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "alice@example.com"
    assert "message" in body


def test_register_same_response_for_duplicate_email_prevents_enumeration(client: TestClient) -> None:
    payload = {"name": "Alice", "email": "alice@example.com", "password": "password-12345"}
    first = client.post("/api/v1/auth/register", json=payload)
    second = client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json() == second.json()
    assert first.json()["email"] == "alice@example.com"


def test_register_rejects_short_password(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"name": "Alice", "email": "alice@example.com", "password": "short"},
    )
    assert response.status_code == 422


def test_authorize_rejects_invalid_credentials(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/register",
        json={"name": "Alice", "email": "alice@example.com", "password": "password-12345"},
    )
    response = client.post(
        "/api/v1/auth/authorize",
        json={
            "email": "alice@example.com",
            "password": "wrong-pwd-67890",
            "code_challenge": s256_challenge("verifier" * 8),
            "code_challenge_method": "S256",
            "scopes": [],
        },
    )
    assert response.status_code == 401
    body = response.json()
    assert body["error"] == "invalid_grant"
    assert body["error_description"] == "Credenciales inválidas"


def test_token_exchange_fails_with_wrong_verifier(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/register",
        json={"name": "Alice", "email": "alice@example.com", "password": "password-12345"},
    )
    challenge = s256_challenge("verifier-A" * 8)
    auth = client.post(
        "/api/v1/auth/authorize",
        json={
            "email": "alice@example.com",
            "password": "password-12345",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scopes": [],
        },
    )
    code = auth.json()["authorization_code"]
    response = client.post(
        "/api/v1/auth/token",
        json={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": "verifier-B" * 8,
        },
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_grant"


def test_full_flow_register_authorize_token(client: TestClient) -> None:
    pair = _full_login_flow(client, scopes=["read"])
    assert pair["token_type"] == "Bearer"
    assert pair["access"]["token"]
    assert pair["refresh"]["token"]


def test_refresh_rotates_pair_and_replay_revokes_family(client: TestClient) -> None:
    pair = _full_login_flow(client)

    rotated = client.post(
        "/api/v1/auth/refresh",
        json={"grant_type": "refresh_token", "refresh_token": pair["refresh"]["token"]},
    )
    assert rotated.status_code == 200
    assert rotated.json()["refresh"]["jti"] != pair["refresh"]["jti"]

    # En ventana de gracia: peticion concurrente con el token anterior devuelve 200 y el mismo par
    replay_grace = client.post(
        "/api/v1/auth/refresh",
        json={"grant_type": "refresh_token", "refresh_token": pair["refresh"]["token"]},
    )
    assert replay_grace.status_code == 200
    assert replay_grace.json()["refresh"]["jti"] == rotated.json()["refresh"]["jti"]

    # Fuera de la ventana de gracia: reuso fraudulento revoca la familia y retorna 401
    store = client.app.state.container.auth.token_store  # type: ignore[union-attr]
    store.grace.clear()

    replay = client.post(
        "/api/v1/auth/refresh",
        json={"grant_type": "refresh_token", "refresh_token": pair["refresh"]["token"]},
    )
    assert replay.status_code == 401
    assert replay.json()["error"] == "invalid_grant"

    rotated_pair = rotated.json()
    after_revocation = client.post(
        "/api/v1/auth/refresh",
        json={"grant_type": "refresh_token", "refresh_token": rotated_pair["refresh"]["token"]},
    )
    assert after_revocation.status_code == 401


def test_logout_revokes_access_token(client: TestClient) -> None:
    pair = _full_login_flow(client)
    headers = {"Authorization": f"Bearer {pair['access']['token']}"}

    response = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": pair["refresh"]["token"]},
        headers=headers,
    )
    assert response.status_code == 204

    after = client.get("/api/v1/auth/me", headers=headers)
    assert after.status_code == 401


def test_me_returns_principal_for_valid_token(client: TestClient) -> None:
    pair = _full_login_flow(client, scopes=["read", "write"])
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {pair['access']['token']}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["scopes"] == ["read", "write"]
    assert body["name"] == "Alice"
    assert body["email"] == "alice@example.com"


def test_me_rejects_missing_token(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_schemas_rejects_unauthenticated_access(client: TestClient) -> None:
    assert client.get("/api/v1/schemas").status_code == 401
    assert client.get("/api/v1/schemas/RegisterRequest").status_code == 401


def test_schemas_index_lists_models(client: TestClient) -> None:
    pair = _full_login_flow(client)
    headers = {"Authorization": f"Bearer {pair['access']['token']}"}
    response = client.get("/api/v1/schemas", headers=headers)
    assert response.status_code == 200
    schemas = response.json()["schemas"]
    assert "RegisterRequest" in schemas
    assert "TokenPairResponse" in schemas


def test_schemas_returns_json_schema(client: TestClient) -> None:
    pair = _full_login_flow(client)
    headers = {"Authorization": f"Bearer {pair['access']['token']}"}
    response = client.get("/api/v1/schemas/RegisterRequest", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "RegisterRequest"
    assert "email" in body["properties"]
    assert "password" in body["properties"]


def test_schemas_returns_oauth_error_schema_with_seconds_remaining(client: TestClient) -> None:
    pair = _full_login_flow(client)
    headers = {"Authorization": f"Bearer {pair['access']['token']}"}
    response = client.get("/api/v1/schemas/OAuthErrorResponse", headers=headers)

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "OAuthErrorResponse"
    assert "error" in body["properties"]
    assert "error_description" in body["properties"]
    assert "seconds_remaining" in body["properties"]


def test_schemas_unknown_returns_404(client: TestClient) -> None:
    pair = _full_login_flow(client)
    headers = {"Authorization": f"Bearer {pair['access']['token']}"}
    response = client.get("/api/v1/schemas/Unknown", headers=headers)
    assert response.status_code == 404


def test_authorize_locks_account_after_max_failures(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/register",
        json={"name": "Victim", "email": "victim@example.com", "password": "password-12345"},
    )
    challenge = s256_challenge("verifier" * 8)
    bad_payload = {
        "email": "victim@example.com",
        "password": "wrong-password",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "scopes": [],
    }
    for _ in range(_MAX_FAILURES):
        resp = client.post("/api/v1/auth/authorize", json=bad_payload)
        assert resp.status_code == 401

    locked = client.post("/api/v1/auth/authorize", json=bad_payload)
    assert locked.status_code == 429
    body = locked.json()
    assert body["error"] == "account_locked"
    assert body["seconds_remaining"] == _LOCKOUT_SECONDS
    assert "Retry-After" in locked.headers
    assert int(locked.headers["Retry-After"]) == _LOCKOUT_SECONDS


def test_authorize_lockout_message_is_in_spanish(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/register",
        json={"name": "Bob", "email": "bob@example.com", "password": "password-12345"},
    )
    challenge = s256_challenge("verifier" * 8)
    bad_payload = {
        "email": "bob@example.com",
        "password": "wrong-password",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "scopes": [],
    }
    for _ in range(_MAX_FAILURES):
        client.post("/api/v1/auth/authorize", json=bad_payload)

    locked = client.post("/api/v1/auth/authorize", json=bad_payload)
    assert locked.status_code == 429
    assert locked.json()["seconds_remaining"] == _LOCKOUT_SECONDS
    assert "Cuenta bloqueada" in locked.json()["error_description"]
    assert "segundos" in locked.json()["error_description"]


def test_authorize_clears_lockout_on_successful_login(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/register",
        json={"name": "Carol", "email": "carol@example.com", "password": "password-12345"},
    )
    challenge = s256_challenge("verifier" * 8)
    bad_payload = {
        "email": "carol@example.com",
        "password": "wrong-password",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "scopes": [],
    }
    for _ in range(5):
        client.post("/api/v1/auth/authorize", json=bad_payload)

    # Login exitoso limpia el contador
    ok = client.post(
        "/api/v1/auth/authorize",
        json={
            "email": "carol@example.com",
            "password": "password-12345",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scopes": [],
        },
    )
    assert ok.status_code == 201

    # Después del éxito, 5 intentos más no bloquean (el contador se reinició)
    for _ in range(5):
        client.post("/api/v1/auth/authorize", json=bad_payload)
    not_yet_locked = client.post("/api/v1/auth/authorize", json=bad_payload)
    assert not_yet_locked.status_code == 401
