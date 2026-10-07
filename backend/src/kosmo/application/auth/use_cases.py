import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from ulid import ULID

from kosmo.contracts.audit import AuditEvent, AuditEventSink, AuditOutcome
from kosmo.contracts.auth import (
    InvalidTokenError,
    Principal,
    TokenClaims,
    TokenExpiredError,
    TokenIssuer,
    TokenPair,
    TokenReusedError,
    TokenRevocationStore,
    TokenRevokedError,
    TokenType,
    TokenVerifier,
)
from kosmo.contracts.telemetry import record_auth_event, traced


def _seconds_until(expires_at: datetime) -> int:
    delta = expires_at - datetime.now(UTC)
    return max(int(delta.total_seconds()), 0)


@dataclass(frozen=True, slots=True)
class IssueTokenPair:
    issuer: TokenIssuer
    revocation_store: TokenRevocationStore

    async def execute(
        self,
        *,
        subject: str,
        scopes: frozenset[str],
        family_id: str | None = None,
    ) -> TokenPair:
        family = family_id or ULID().hex
        access = self.issuer.issue(subject=subject, scopes=scopes, token_type=TokenType.ACCESS, family_id=family)
        refresh = self.issuer.issue(subject=subject, scopes=scopes, token_type=TokenType.REFRESH, family_id=family)
        await self.revocation_store.register_refresh(
            jti=refresh.jti,
            subject=subject,
            ttl_seconds=_seconds_until(refresh.expires_at),
            family_id=family,
        )
        return TokenPair(access=access, refresh=refresh)


@dataclass(frozen=True, slots=True)
class VerifyAccessToken:
    verifier: TokenVerifier
    revocation_store: TokenRevocationStore

    async def execute(self, token: str) -> Principal:
        claims = await asyncio.to_thread(self.verifier.verify, token, expected_type=TokenType.ACCESS)

        if await self.revocation_store.is_access_revoked(jti=claims.jti):
            raise TokenRevokedError("Access token revoked")
        if claims.family_id is not None and not await self.revocation_store.is_family_alive(family_id=claims.family_id):
            raise TokenRevokedError("Session revoked")

        return Principal(subject=claims.subject, scopes=claims.scopes)


@dataclass(frozen=True, slots=True)
class RefreshTokenPair:
    issuer: TokenIssuer
    verifier: TokenVerifier
    revocation_store: TokenRevocationStore
    audit_sink: AuditEventSink

    @traced("auth.token_refresh")
    async def execute(self, refresh_token: str, *, scopes: frozenset[str]) -> TokenPair:
        claims = await asyncio.to_thread(self.verifier.verify, refresh_token, expected_type=TokenType.REFRESH)
        consumed = await self.revocation_store.consume_refresh(jti=claims.jti)
        if consumed is None:
            grace_pair = await self.revocation_store.get_grace_period(old_jti=claims.jti)
            if grace_pair is not None:
                family = grace_pair.refresh.family_id or claims.family_id
                if family is not None and not await self.revocation_store.is_family_alive(family_id=family):
                    raise TokenRevokedError("Sesión revocada")
                return grace_pair

            if claims.family_id is not None and await self.revocation_store.is_family_alive(family_id=claims.family_id):
                await self.revocation_store.revoke_family(family_id=claims.family_id)
                await self.audit_sink.record(
                    AuditEvent(
                        event_type="auth.token_reused",
                        outcome=AuditOutcome.FAILURE,
                        occurred_at=datetime.now(UTC),
                        actor_id=claims.subject,
                        metadata={"reason": "refresh_token_reused"},
                    )
                )
                raise TokenReusedError("Refresh token reusado, sesión revocada")
            raise InvalidTokenError("Refresh token not recognized")
        if consumed.subject != claims.subject:
            if claims.family_id is not None:
                await self.revocation_store.revoke_family(family_id=claims.family_id)
            raise InvalidTokenError("Refresh token subject mismatch")

        family = consumed.family_id or claims.family_id
        if family is not None and not await self.revocation_store.is_family_alive(family_id=family):
            raise TokenRevokedError("Sesión revocada")
        access = self.issuer.issue(
            subject=claims.subject,
            scopes=scopes,
            token_type=TokenType.ACCESS,
            family_id=family,
        )
        new_refresh = self.issuer.issue(
            subject=claims.subject,
            scopes=scopes,
            token_type=TokenType.REFRESH,
            family_id=family,
        )
        refresh_ttl = _seconds_until(new_refresh.expires_at)
        await self.revocation_store.register_refresh(
            jti=new_refresh.jti,
            subject=claims.subject,
            ttl_seconds=refresh_ttl,
            family_id=family,
        )
        pair = TokenPair(access=access, refresh=new_refresh)
        grace_ttl = min(30, max(refresh_ttl, 1))
        await self.revocation_store.store_grace_period(
            old_jti=claims.jti,
            token_pair=pair,
            ttl_seconds=grace_ttl,
        )
        await self.audit_sink.record(
            AuditEvent(
                event_type="auth.token_refresh",
                outcome=AuditOutcome.SUCCESS,
                occurred_at=datetime.now(UTC),
                actor_id=claims.subject,
            )
        )
        record_auth_event("token_refresh", user_id=claims.subject)
        return pair


@dataclass(frozen=True, slots=True)
class RevokeSession:
    verifier: TokenVerifier
    revocation_store: TokenRevocationStore
    audit_sink: AuditEventSink

    @traced("auth.logout")
    async def execute(self, *, access_token: str, refresh_token: str | None = None) -> None:
        access_claims: TokenClaims | None = None
        access_token_expired = False
        if access_token:
            try:
                access_claims = await asyncio.to_thread(
                    self.verifier.verify, access_token, expected_type=TokenType.ACCESS
                )
                await self.revocation_store.revoke_access(
                    jti=access_claims.jti,
                    ttl_seconds=_seconds_until(access_claims.expires_at),
                )
                if access_claims.family_id is not None:
                    await self.revocation_store.revoke_family(family_id=access_claims.family_id)
            except TokenExpiredError:
                access_token_expired = True

        refresh_claims: TokenClaims | None = None
        if refresh_token is not None:
            refresh_claims = await asyncio.to_thread(
                self.verifier.verify, refresh_token, expected_type=TokenType.REFRESH
            )
            await self.revocation_store.revoke_refresh(jti=refresh_claims.jti)
            if refresh_claims.family_id is not None:
                await self.revocation_store.revoke_family(family_id=refresh_claims.family_id)
        elif access_token_expired:
            raise TokenExpiredError("Token expired")
        elif not access_token:
            raise InvalidTokenError("Missing token")

        subject = (
            access_claims.subject
            if access_claims is not None
            else (refresh_claims.subject if refresh_claims is not None else "unknown")
        )
        await self.audit_sink.record(
            AuditEvent(
                event_type="auth.logout",
                outcome=AuditOutcome.SUCCESS,
                occurred_at=datetime.now(UTC),
                actor_id=subject,
            )
        )
        record_auth_event("logout", user_id=subject)
