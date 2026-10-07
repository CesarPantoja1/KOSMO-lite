import asyncio
import importlib
from typing import cast

import pytest

from kosmo.application.auth import (  # noqa: E402
    IssueTokenPair,
    RefreshTokenPair,
    RevokeSession,
    VerifyAccessToken,
)
from kosmo.contracts.auth import (  # noqa: E402
    InvalidTokenError,
    IssuedToken,
    Principal,
    TokenExpiredError,
    TokenPair,
    TokenReusedError,
    TokenRevokedError,
    TokenType,
)
from tests.conftest import _PRIVATE_KEY_PEM as _PRIVATE_PEM
from tests.conftest import _PUBLIC_KEY_PEM as _PUBLIC_PEM
from tests.unit.fakes import InMemoryAuditEventSink, InMemoryStore

security = importlib.import_module("kosmo.infrastructure.security")
JoseJwtIssuer = security.JoseJwtIssuer
JoseJwtVerifier = security.JoseJwtVerifier
JwtSettings = security.JwtSettings


def _build_codec() -> tuple[JoseJwtIssuer, JoseJwtVerifier]:
    settings = JwtSettings(
        algorithm="RS256",
        issuer="kosmo-test",
        audience="kosmo-test",
        access_ttl_seconds=60,
        refresh_ttl_seconds=300,
    )
    return JoseJwtIssuer(private_key_pem=_PRIVATE_PEM, settings=settings), JoseJwtVerifier(
        public_key_pem=_PUBLIC_PEM, settings=settings
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_issue_then_verify_returns_principal() -> None:
    issuer, verifier = _build_codec()
    store = InMemoryStore()
    issue = IssueTokenPair(issuer=issuer, revocation_store=store)
    verify = VerifyAccessToken(verifier=verifier, revocation_store=store)

    pair: TokenPair = await issue.execute(subject="user-1", scopes=frozenset({"read"}))
    principal: Principal = await verify.execute(pair.access.token)

    assert principal.subject == "user-1"
    assert principal.scopes == frozenset({"read"})
    assert pair.refresh.jti in store.refresh


@pytest.mark.asyncio
@pytest.mark.unit
async def test_revoked_access_rejected() -> None:
    issuer, verifier = _build_codec()
    store = InMemoryStore()
    audit_sink = InMemoryAuditEventSink()
    issue = IssueTokenPair(issuer=issuer, revocation_store=store)
    verify = VerifyAccessToken(verifier=verifier, revocation_store=store)
    revoke = RevokeSession(verifier=verifier, revocation_store=store, audit_sink=audit_sink)

    pair = await issue.execute(subject="user-1", scopes=frozenset())
    await revoke.execute(access_token=pair.access.token, refresh_token=pair.refresh.token)

    with pytest.raises(TokenRevokedError):
        await verify.execute(pair.access.token)
    assert pair.refresh.jti not in store.refresh


@pytest.mark.asyncio
@pytest.mark.unit
async def test_refresh_rotates_pair() -> None:
    issuer, verifier = _build_codec()
    store = InMemoryStore()
    audit_sink = InMemoryAuditEventSink()
    issue = IssueTokenPair(issuer=issuer, revocation_store=store)
    refresh_uc = RefreshTokenPair(issuer=issuer, verifier=verifier, revocation_store=store, audit_sink=audit_sink)

    original = await issue.execute(subject="user-1", scopes=frozenset({"read"}))
    rotated = await refresh_uc.execute(original.refresh.token, scopes=frozenset({"read"}))

    assert rotated.refresh.jti != original.refresh.jti
    assert original.refresh.jti not in store.refresh
    assert rotated.refresh.jti in store.refresh

    # Dentro del grace period: una llamada repetida devuelve el mismo par emitido
    grace = await refresh_uc.execute(original.refresh.token, scopes=frozenset({"read"}))
    assert grace.refresh.jti == rotated.refresh.jti
    assert grace.access.token == rotated.access.token

    # Fuera del grace period: reuso genuino revoca la familia y eleva TokenReusedError
    store.grace.clear()
    with pytest.raises(TokenReusedError):
        await refresh_uc.execute(original.refresh.token, scopes=frozenset({"read"}))


@pytest.mark.asyncio
@pytest.mark.unit
async def test_concurrent_refresh_requests_succeed_without_revocation() -> None:
    # Arrange
    issuer, verifier = _build_codec()
    store = InMemoryStore()
    audit_sink = InMemoryAuditEventSink()
    issue = IssueTokenPair(issuer=issuer, revocation_store=store)
    refresh_uc = RefreshTokenPair(issuer=issuer, verifier=verifier, revocation_store=store, audit_sink=audit_sink)

    original = await issue.execute(subject="user-conc", scopes=frozenset({"read"}))
    family_id = original.refresh.family_id
    assert family_id is not None

    # Act: Dos peticiones simultaneas de refresh con el mismo token
    res1, res2 = await asyncio.gather(
        refresh_uc.execute(original.refresh.token, scopes=frozenset({"read"})),
        refresh_uc.execute(original.refresh.token, scopes=frozenset({"read"})),
    )

    # Assert: Ambas peticiones completan exitosamente
    assert res1.access.token is not None
    assert res2.access.token is not None
    assert res1.refresh.jti == res2.refresh.jti
    # La familia de la sesion sigue viva (NO fue revocada por race condition)
    assert await store.is_family_alive(family_id=family_id) is True


@pytest.mark.asyncio
@pytest.mark.unit
async def test_refresh_grace_period_rejected_if_session_revoked() -> None:
    # Arrange
    issuer, verifier = _build_codec()
    store = InMemoryStore()
    audit_sink = InMemoryAuditEventSink()
    issue = IssueTokenPair(issuer=issuer, revocation_store=store)
    refresh_uc = RefreshTokenPair(issuer=issuer, verifier=verifier, revocation_store=store, audit_sink=audit_sink)

    original = await issue.execute(subject="user-revoked", scopes=frozenset({"read"}))
    family_id = original.refresh.family_id
    assert family_id is not None

    # Rotar una vez (queda registrado en grace period)
    await refresh_uc.execute(original.refresh.token, scopes=frozenset({"read"}))

    # Revocar explicitamente la sesion/familia (ej. logout)
    await store.revoke_family(family_id=family_id)

    # Act & Assert: Aunque el token este en grace period, si la sesion fue revocada debe fallar
    with pytest.raises(TokenRevokedError):
        await refresh_uc.execute(original.refresh.token, scopes=frozenset({"read"}))


@pytest.mark.asyncio
@pytest.mark.unit
async def test_access_token_used_as_refresh_is_rejected() -> None:
    issuer, verifier = _build_codec()
    store = InMemoryStore()
    audit_sink = InMemoryAuditEventSink()
    issue = IssueTokenPair(issuer=issuer, revocation_store=store)
    refresh_uc = RefreshTokenPair(issuer=issuer, verifier=verifier, revocation_store=store, audit_sink=audit_sink)

    pair = await issue.execute(subject="user-1", scopes=frozenset())

    with pytest.raises(InvalidTokenError):
        await refresh_uc.execute(pair.access.token, scopes=frozenset())


@pytest.mark.unit
def test_expired_token_raises() -> None:
    issuer, verifier = _build_codec()
    issued = issuer.issue(subject="user-1", scopes=frozenset(), token_type=TokenType.ACCESS)
    _ = cast(IssuedToken, issued)

    expired_settings = JwtSettings(
        algorithm="RS256",
        issuer="kosmo-test",
        audience="kosmo-test",
        access_ttl_seconds=-10,
        refresh_ttl_seconds=-10,
    )
    expired_issuer = JoseJwtIssuer(private_key_pem=_PRIVATE_PEM, settings=expired_settings)
    expired_token = expired_issuer.issue(subject="user-1", scopes=frozenset(), token_type=TokenType.ACCESS)

    with pytest.raises(TokenExpiredError):
        verifier.verify(expired_token.token, expected_type=TokenType.ACCESS)


@pytest.mark.unit
def test_verifier_rejects_tampered_token() -> None:
    _, verifier = _build_codec()
    bogus = "eyJhbGciOiJSUzI1NiJ9.bm90LWEtdG9rZW4.signature"

    with pytest.raises(InvalidTokenError):
        verifier.verify(bogus, expected_type=TokenType.ACCESS)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_verify_access_token_detects_subsequent_revocation_immediately() -> None:
    # Arrange
    issuer, verifier = _build_codec()
    store = InMemoryStore()
    issue = IssueTokenPair(issuer=issuer, revocation_store=store)
    verify = VerifyAccessToken(verifier=verifier, revocation_store=store)

    pair = await issue.execute(subject="user-1", scopes=frozenset({"read"}))

    # Primera verificación: válida
    principal = await verify.execute(pair.access.token)
    assert principal.subject == "user-1"

    # Revocación externa (p. ej., en otro worker o proceso)
    await store.revoke_access(jti=pair.access.jti, ttl_seconds=300)

    # Segunda verificación: debe detectar la revocación de inmediato sin caché en memoria
    with pytest.raises(TokenRevokedError, match="Access token revoked"):
        await verify.execute(pair.access.token)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_verify_access_token_detects_family_revocation_immediately() -> None:
    # Arrange
    issuer, verifier = _build_codec()
    store = InMemoryStore()
    issue = IssueTokenPair(issuer=issuer, revocation_store=store)
    verify = VerifyAccessToken(verifier=verifier, revocation_store=store)

    pair = await issue.execute(subject="user-1", scopes=frozenset({"read"}))

    # Primera verificación: válida
    principal = await verify.execute(pair.access.token)
    assert principal.subject == "user-1"

    # Revocación de la sesión/familia externa
    await store.revoke_family(family_id=pair.access.family_id)  # type: ignore[arg-type]

    # Segunda verificación: debe rechazar la sesión revocada inmediatamente
    with pytest.raises(TokenRevokedError, match="Session revoked"):
        await verify.execute(pair.access.token)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_revoke_session_with_valid_access_and_refresh_token() -> None:
    # Arrange
    issuer, verifier = _build_codec()
    store = InMemoryStore()
    audit_sink = InMemoryAuditEventSink()
    issue = IssueTokenPair(issuer=issuer, revocation_store=store)
    revoke_uc = RevokeSession(verifier=verifier, revocation_store=store, audit_sink=audit_sink)

    pair = await issue.execute(subject="user-logout", scopes=frozenset({"read"}))

    # Act
    await revoke_uc.execute(access_token=pair.access.token, refresh_token=pair.refresh.token)

    # Assert
    assert await store.is_access_revoked(jti=pair.access.jti) is True
    assert await store.is_family_alive(family_id=pair.access.family_id) is False  # type: ignore[arg-type]
    assert len(audit_sink.events) == 1
    assert audit_sink.events[0].event_type == "auth.logout"
    assert audit_sink.events[0].actor_id == "user-logout"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_revoke_session_with_expired_access_token_and_valid_refresh_token() -> None:
    # Arrange
    issuer, verifier = _build_codec()
    store = InMemoryStore()
    audit_sink = InMemoryAuditEventSink()
    issue = IssueTokenPair(issuer=issuer, revocation_store=store)
    revoke_uc = RevokeSession(verifier=verifier, revocation_store=store, audit_sink=audit_sink)

    pair = await issue.execute(subject="user-expired-logout", scopes=frozenset({"read"}))

    expired_settings = JwtSettings(
        algorithm="RS256",
        issuer="kosmo-test",
        audience="kosmo-test",
        access_ttl_seconds=-10,
        refresh_ttl_seconds=300,
    )
    expired_issuer = JoseJwtIssuer(private_key_pem=_PRIVATE_PEM, settings=expired_settings)
    expired_access = expired_issuer.issue(
        subject="user-expired-logout",
        scopes=frozenset({"read"}),
        token_type=TokenType.ACCESS,
        family_id=pair.refresh.family_id,
    )

    # Act: logout con access token expirado y refresh token válido debe proceder
    await revoke_uc.execute(access_token=expired_access.token, refresh_token=pair.refresh.token)

    # Assert: el refresh token y la familia de la sesión deben quedar revocados
    assert await store.is_family_alive(family_id=pair.refresh.family_id) is False  # type: ignore[arg-type]
    assert len(audit_sink.events) == 1
    assert audit_sink.events[0].event_type == "auth.logout"
    assert audit_sink.events[0].actor_id == "user-expired-logout"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_revoke_session_with_expired_access_token_and_no_refresh_token_raises() -> None:
    # Arrange
    _, verifier = _build_codec()
    store = InMemoryStore()
    audit_sink = InMemoryAuditEventSink()
    revoke_uc = RevokeSession(verifier=verifier, revocation_store=store, audit_sink=audit_sink)

    expired_settings = JwtSettings(
        algorithm="RS256",
        issuer="kosmo-test",
        audience="kosmo-test",
        access_ttl_seconds=-10,
        refresh_ttl_seconds=300,
    )
    expired_issuer = JoseJwtIssuer(private_key_pem=_PRIVATE_PEM, settings=expired_settings)
    expired_access = expired_issuer.issue(
        subject="user-expired-logout",
        scopes=frozenset({"read"}),
        token_type=TokenType.ACCESS,
    )

    # Act & Assert: sin refresh token para limpiar, el access token expirado lanza TokenExpiredError
    with pytest.raises(TokenExpiredError):
        await revoke_uc.execute(access_token=expired_access.token, refresh_token=None)
