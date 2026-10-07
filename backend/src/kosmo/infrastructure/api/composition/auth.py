from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis

from kosmo.application.auth import (
    AuthorizeWithPkce,
    ExchangeAuthorizationCode,
    IssueTokenPair,
    RefreshTokenPair,
    RegisterUser,
    RevokeSession,
    VerifyAccessToken,
)
from kosmo.config import Settings
from kosmo.contracts.audit import AuditEventSink
from kosmo.contracts.auth import LoginAttemptStore, PasswordHasher, SecretCipher, UserRepository
from kosmo.infrastructure.persistence.postgres.registry import RepositoryRegistry
from kosmo.infrastructure.persistence.redis import (
    RedisAuthorizationCodeStore,
    RedisLoginAttemptStore,
    RedisTokenRevocationStore,
)
from kosmo.infrastructure.security import (
    Argon2idParameters,
    Argon2idPasswordHasher,
    FernetSecretCipher,
    JoseJwtIssuer,
    JoseJwtVerifier,
    JwtSettings,
)


@dataclass(frozen=True, slots=True)
class AuthComponents:
    redis: Redis
    password_hasher: PasswordHasher
    secret_cipher: SecretCipher
    user_repository: UserRepository
    login_attempt_store: LoginAttemptStore
    audit_sink: AuditEventSink
    register_user: RegisterUser
    authorize_with_pkce: AuthorizeWithPkce
    exchange_authorization_code: ExchangeAuthorizationCode
    issue_token_pair: IssueTokenPair
    verify_access_token: VerifyAccessToken
    refresh_token_pair: RefreshTokenPair
    revoke_session: RevokeSession


def build_auth_components(settings: Settings, repos: RepositoryRegistry) -> AuthComponents:
    assert settings.jwt_private_key_pem is not None
    assert settings.jwt_public_key_pem is not None
    assert settings.redis_url is not None
    assert settings.fernet_master_key is not None

    jwt_settings = JwtSettings(
        algorithm=settings.jwt_algorithm,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        access_ttl_seconds=settings.jwt_access_ttl_seconds,
        refresh_ttl_seconds=settings.jwt_refresh_ttl_seconds,
    )
    issuer = JoseJwtIssuer(
        private_key_pem=settings.jwt_private_key_pem.get_secret_value(),
        settings=jwt_settings,
    )
    verifier = JoseJwtVerifier(
        public_key_pem=settings.jwt_public_key_pem.get_secret_value(),
        settings=jwt_settings,
    )

    redis: Redis = Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
        settings.redis_url.get_secret_value(),
        max_connections=settings.redis_max_connections,
        socket_timeout=settings.redis_socket_timeout,
        socket_connect_timeout=settings.redis_socket_connect_timeout,
    )
    token_store = RedisTokenRevocationStore(redis)
    authorization_code_store = RedisAuthorizationCodeStore(redis)
    login_attempt_store = RedisLoginAttemptStore(redis)

    user_repository = repos.users
    audit_sink = repos.audit_sink

    password_hasher = Argon2idPasswordHasher(
        Argon2idParameters(
            memory_kib=settings.argon2_memory_kib,
            time_cost=settings.argon2_time_cost,
            parallelism=settings.argon2_parallelism,
        )
    )
    secret_cipher = FernetSecretCipher(settings.fernet_master_key.get_secret_value())

    issue_token_pair = IssueTokenPair(issuer=issuer, revocation_store=token_store)

    return AuthComponents(
        redis=redis,
        password_hasher=password_hasher,
        secret_cipher=secret_cipher,
        user_repository=user_repository,
        login_attempt_store=login_attempt_store,
        audit_sink=audit_sink,
        register_user=RegisterUser(
            user_repository=user_repository,
            password_hasher=password_hasher,
            audit_sink=audit_sink,
        ),
        authorize_with_pkce=AuthorizeWithPkce(
            user_repository=user_repository,
            password_hasher=password_hasher,
            authorization_code_store=authorization_code_store,
            login_attempt_store=login_attempt_store,
            audit_sink=audit_sink,
        ),
        exchange_authorization_code=ExchangeAuthorizationCode(
            authorization_code_store=authorization_code_store,
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
    )
