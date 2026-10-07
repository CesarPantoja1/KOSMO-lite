"""Puertos del bounded context de autenticación.

Definen la frontera entre los casos de uso (``application``) y los adaptadores
de infraestructura (``infrastructure``). Viven en ``contracts`` porque también
los consumen los routers y la composición de la aplicación, así como los tests
que sustituyen las implementaciones reales por dobles en memoria.
"""

from typing import Protocol

from kosmo.contracts.auth.pkce import AuthorizationCode
from kosmo.contracts.auth.tokens import (
    IssuedToken,
    RefreshConsumeResult,
    TokenClaims,
    TokenPair,
    TokenType,
)
from kosmo.contracts.auth.users import User


class TokenIssuer(Protocol):
    def issue(
        self,
        *,
        subject: str,
        scopes: frozenset[str],
        token_type: TokenType,
        family_id: str | None = None,
    ) -> IssuedToken: ...


class TokenVerifier(Protocol):
    def verify(self, token: str, *, expected_type: TokenType) -> TokenClaims: ...


class TokenRevocationStore(Protocol):
    async def register_refresh(
        self,
        *,
        jti: str,
        subject: str,
        ttl_seconds: int,
        family_id: str | None = None,
    ) -> None: ...

    async def consume_refresh(self, *, jti: str) -> RefreshConsumeResult | None: ...

    async def store_grace_period(
        self,
        *,
        old_jti: str,
        token_pair: TokenPair,
        ttl_seconds: int = 30,
    ) -> None: ...

    async def get_grace_period(self, *, old_jti: str) -> TokenPair | None: ...

    async def revoke_access(self, *, jti: str, ttl_seconds: int) -> None: ...

    async def is_access_revoked(self, *, jti: str) -> bool: ...

    async def revoke_refresh(self, *, jti: str) -> None: ...

    async def is_family_alive(self, *, family_id: str) -> bool: ...

    async def revoke_family(self, *, family_id: str) -> None: ...


class PasswordHasher(Protocol):
    def hash(self, plain: str) -> str: ...

    def verify(self, hashed: str, plain: str) -> bool: ...

    def needs_rehash(self, hashed: str) -> bool: ...


class UserRepository(Protocol):
    async def by_email(self, email: str) -> User | None: ...

    async def by_id(self, user_id: str) -> User | None: ...

    async def create(self, user: User) -> None: ...

    async def update_password(self, *, user_id: str, hashed_password: str) -> None: ...

    async def update_profile(
        self,
        *,
        user_id: str,
        name: str | None = None,
        avatar_url: str | None = None,
    ) -> None: ...


class AuthorizationCodeStore(Protocol):
    async def store(self, entry: AuthorizationCode) -> None: ...

    async def consume(self, code: str) -> AuthorizationCode | None: ...


class LoginAttemptStore(Protocol):
    async def record_failure(self, identifier: str) -> None: ...

    async def clear(self, identifier: str) -> None: ...

    async def lockout_seconds(self, identifier: str) -> int | None: ...
