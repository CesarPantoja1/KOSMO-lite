from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from kosmo.application.auth import IssueTokenPair, RefreshTokenPair
from kosmo.contracts.auth import (
    TokenPair,
    TokenReusedError,
    TokenType,
)
from kosmo.contracts.sdd.ids import ProjectId
from kosmo.infrastructure.codegen.workspace import LocalWorkspaceManager, WorkspaceLockedError
from kosmo.infrastructure.security import JoseJwtIssuer, JoseJwtVerifier, JwtSettings
from tests.conftest import _PRIVATE_KEY_PEM as _PRIVATE_PEM
from tests.conftest import _PUBLIC_KEY_PEM as _PUBLIC_PEM
from tests.unit.fakes import InMemoryAuditEventSink, InMemoryStore


def _make_codecs() -> tuple[JoseJwtIssuer, JoseJwtVerifier]:
    settings = JwtSettings(
        algorithm="RS256",
        issuer="kosmo-concurrency-test",
        audience="kosmo-concurrency-test",
        access_ttl_seconds=60,
        refresh_ttl_seconds=300,
    )
    return JoseJwtIssuer(private_key_pem=_PRIVATE_PEM, settings=settings), JoseJwtVerifier(
        public_key_pem=_PUBLIC_PEM, settings=settings
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_refresh_token_concurrent_burst_maintains_session() -> None:
    # Arrange
    issuer, verifier = _make_codecs()
    store = InMemoryStore()
    audit_sink = InMemoryAuditEventSink()

    issue_uc = IssueTokenPair(issuer=issuer, revocation_store=store)
    refresh_uc = RefreshTokenPair(
        issuer=issuer,
        verifier=verifier,
        revocation_store=store,
        audit_sink=audit_sink,
    )

    initial_pair: TokenPair = await issue_uc.execute(
        subject="usr_concurrent_burst",
        scopes=frozenset({"read", "write"}),
    )
    refresh_token_str = initial_pair.refresh.token

    # Act: 10 peticiones simultaneas compitiendo por renovar el mismo refresh token
    async def call_refresh() -> TokenPair:
        return await refresh_uc.execute(refresh_token_str, scopes=frozenset({"read", "write"}))

    results = await asyncio.gather(*(call_refresh() for _ in range(10)))

    # Assert: Las 10 peticiones deben completar con exito gracias al periodo de gracia
    assert len(results) == 10

    # Todas deben recibir el mismo par de tokens renovado
    canonical_access = results[0].access.token
    canonical_refresh = results[0].refresh.token
    for res in results:
        assert isinstance(res, TokenPair)
        assert res.access.token == canonical_access
        assert res.refresh.token == canonical_refresh

    # El token de acceso renovado es valido para el usuario
    claims = verifier.verify(canonical_access, expected_type=TokenType.ACCESS)
    assert claims.subject == "usr_concurrent_burst"

    # Ninguna llamada debe haber disparado un evento de reuso no autorizado
    reused_events = [e for e in audit_sink.events if e.event_type == "auth.token_reused"]
    assert len(reused_events) == 0


@pytest.mark.asyncio
@pytest.mark.unit
async def test_refresh_token_reuse_after_grace_period_expired_triggers_revocation() -> None:
    # Arrange
    issuer, verifier = _make_codecs()
    store = InMemoryStore()
    audit_sink = InMemoryAuditEventSink()

    issue_uc = IssueTokenPair(issuer=issuer, revocation_store=store)
    refresh_uc = RefreshTokenPair(
        issuer=issuer,
        verifier=verifier,
        revocation_store=store,
        audit_sink=audit_sink,
    )

    initial_pair: TokenPair = await issue_uc.execute(
        subject="usr_grace_expiry",
        scopes=frozenset({"read"}),
    )

    # Primera renovacion legitima
    await refresh_uc.execute(initial_pair.refresh.token, scopes=frozenset({"read"}))

    # Simulamos que expira la ventana de gracia en Redis
    store.grace.clear()

    # Act & Assert: Intentar reusar el refresh token previo tras expirar la gracia revoca la sesion
    with pytest.raises(TokenReusedError):
        await refresh_uc.execute(initial_pair.refresh.token, scopes=frozenset({"read"}))

    # Se debio revocar la familia de tokens y auditar el fallo de seguridad
    family_id = initial_pair.refresh.family_id
    assert family_id is not None
    assert await store.is_family_alive(family_id=family_id) is False

    reused_events = [e for e in audit_sink.events if e.event_type == "auth.token_reused"]
    assert len(reused_events) == 1
    assert reused_events[0].actor_id == "usr_grace_expiry"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_workspace_lock_exclusion_and_release(tmp_path: Path) -> None:
    # Arrange
    manager = LocalWorkspaceManager(workspaces_root=tmp_path)
    proj_a = ProjectId("prj_lock_a")
    proj_b = ProjectId("prj_lock_b")

    # Act 1: Adquirir bloqueo en proyecto A
    await manager.acquire_lock(proj_a)
    assert await manager.is_locked(proj_a) is True

    # Assert 1: Segundo intento concurrente sobre proyecto A debe fallar con WorkspaceLockedError
    with pytest.raises(WorkspaceLockedError):
        await manager.acquire_lock(proj_a)

    # Act 2: Proyecto B debe poder bloquearse independientemente sin contencion
    await manager.acquire_lock(proj_b)
    assert await manager.is_locked(proj_b) is True

    # Act 3: Liberar proyecto A permite posterior adquisicion
    await manager.release_lock(proj_a)
    assert await manager.is_locked(proj_a) is False

    await manager.acquire_lock(proj_a)
    assert await manager.is_locked(proj_a) is True

    # Limpieza
    await manager.release_lock(proj_a)
    await manager.release_lock(proj_b)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_workspace_lock_concurrent_burst(tmp_path: Path) -> None:
    # Arrange
    manager = LocalWorkspaceManager(workspaces_root=tmp_path)
    target_project = ProjectId("prj_shared_burst")

    async def attempt_lock() -> str:
        try:
            await manager.acquire_lock(target_project)
            return "SUCCESS"
        except WorkspaceLockedError:
            return "LOCKED"

    # Act: 10 peticiones simultaneas compiten por bloquear el mismo proyecto
    outcomes = await asyncio.gather(*(attempt_lock() for _ in range(10)))

    # Assert: Exactamente 1 tarea gana el bloqueo, las 9 restantes son rechazadas
    assert outcomes.count("SUCCESS") == 1
    assert outcomes.count("LOCKED") == 9
    assert await manager.is_locked(target_project) is True

    # Liberar y validar estado final
    await manager.release_lock(target_project)
    assert await manager.is_locked(target_project) is False
