"""Kernel del dominio de autenticación.

Define los tipos, errores y puertos compartidos entre las capas. Es la capa más
estable del sistema (``contracts`` está en el nivel inferior del contrato de
``import-linter``), por lo que cualquier capa puede consumirla.
"""

from kosmo.contracts.auth.context import current_user_id
from kosmo.contracts.auth.errors import (
    AccountLockedError,
    AuthError,
    AuthorizationCodeError,
    InvalidCredentialsError,
    InvalidTokenError,
    MissingTokenError,
    PkceMismatchError,
    TokenExpiredError,
    TokenReusedError,
    TokenRevokedError,
    UserAlreadyExistsError,
)
from kosmo.contracts.auth.pkce import AuthorizationCode, PkceMethod
from kosmo.contracts.auth.ports import (
    AuthorizationCodeStore,
    LoginAttemptStore,
    PasswordHasher,
    TokenIssuer,
    TokenRevocationStore,
    TokenVerifier,
    UserRepository,
)
from kosmo.contracts.auth.principal import Principal
from kosmo.contracts.auth.secrets import EncryptedSecret, SecretCipher
from kosmo.contracts.auth.tokens import (
    IssuedToken,
    RefreshConsumeResult,
    TokenClaims,
    TokenPair,
    TokenType,
)
from kosmo.contracts.auth.users import User

__all__ = [
    "AccountLockedError",
    "AuthError",
    "AuthorizationCode",
    "AuthorizationCodeError",
    "AuthorizationCodeStore",
    "EncryptedSecret",
    "InvalidCredentialsError",
    "InvalidTokenError",
    "IssuedToken",
    "LoginAttemptStore",
    "MissingTokenError",
    "PasswordHasher",
    "PkceMethod",
    "PkceMismatchError",
    "Principal",
    "RefreshConsumeResult",
    "SecretCipher",
    "TokenClaims",
    "TokenExpiredError",
    "TokenIssuer",
    "TokenPair",
    "TokenRevocationStore",
    "TokenReusedError",
    "TokenRevokedError",
    "TokenType",
    "TokenVerifier",
    "User",
    "UserAlreadyExistsError",
    "UserRepository",
    "current_user_id",
]
