from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from kosmo.application.auth import (
    AuthorizeWithPkce,
    ExchangeAuthorizationCode,
    RefreshTokenPair,
    RegisterUser,
    RevokeSession,
)
from kosmo.config import settings
from kosmo.contracts.auth import (
    AccountLockedError,
    AuthorizationCodeError,
    InvalidCredentialsError,
    InvalidTokenError,
    PkceMismatchError,
    Principal,
    TokenExpiredError,
    TokenReusedError,
    TokenRevokedError,
    UserAlreadyExistsError,
)
from kosmo.infrastructure.api.composition import AuthComponents
from kosmo.infrastructure.api.dependencies.auth import get_principal
from kosmo.infrastructure.api.dependencies.container import get_container
from kosmo.infrastructure.api.dependencies.rate_limit import IpRateLimiter
from kosmo.infrastructure.api.schemas import (
    AuthorizationCodeResponse,
    AuthorizeRequest,
    LogoutRequest,
    OAuthErrorResponse,
    PrincipalView,
    RegisterRequest,
    RegisterResponse,
    TokenExchangeRequest,
    TokenPairResponse,
    TokenRefreshRequest,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_register_limiter = IpRateLimiter(3)
_authorize_limiter = IpRateLimiter(60)
_token_limiter = IpRateLimiter(60)
_refresh_limiter = IpRateLimiter(60)
_logout_limiter = IpRateLimiter(60)


def _auth_components(request: Request) -> AuthComponents:
    container = get_container(request)
    assert container.auth is not None
    return container.auth


def _register(request: Request) -> RegisterUser:
    return _auth_components(request).register_user


def _authorize(request: Request) -> AuthorizeWithPkce:
    return _auth_components(request).authorize_with_pkce


def _exchange(request: Request) -> ExchangeAuthorizationCode:
    return _auth_components(request).exchange_authorization_code


def _refresh(request: Request) -> RefreshTokenPair:
    return _auth_components(request).refresh_token_pair


def _revoke(request: Request) -> RevokeSession:
    return _auth_components(request).revoke_session


def _oauth_error(*, status_code: int, error: str, description: str) -> JSONResponse:
    body = OAuthErrorResponse(error=error, error_description=description)
    return JSONResponse(status_code=status_code, content=body.model_dump())


# POST /register


@router.post(
    "/register",
    summary="Registrar nuevo usuario",
    description=(
        "Crea una nueva cuenta de usuario en KOSMO. "
        "La contraseña se hashea con **Argon2id** (OWASP 2025) antes de persistirse. "
        "Devuelve una confirmación genérica para prevenir la enumeración de usuarios (CWE-204). "
        "Límite de velocidad: **3 peticiones / IP / ventana**."
    ),
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: {
            "description": "Confirmación genérica de registro recibida exitosamente.",
            "content": {
                "application/json": {
                    "example": {
                        "email": "usuario@ejemplo.com",
                        "message": (
                            "Si el correo no estaba registrado previamente, la cuenta ha sido creada exitosamente."
                        ),
                    }
                }
            },
        },
        status.HTTP_400_BAD_REQUEST: {
            "description": "Datos de registro inválidos (ej. nombre vacío).",
            "content": {"application/json": {"example": {"detail": "El nombre no puede estar vacío"}}},
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Error de validación del payload (ej. contraseña menor a 12 caracteres).",
            "content": {
                "application/json": {
                    "example": {
                        "detail": [
                            {
                                "loc": ["body", "password"],
                                "msg": "String should have at least 12 characters",
                                "type": "string_too_short",
                            }
                        ]
                    }
                }
            },
        },
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "Rate limit excedido. Esperar antes de reintentar.",
            "content": {
                "application/json": {
                    "example": {
                        "error": "rate_limit_exceeded",
                        "error_description": "Demasiadas peticiones. Intente más tarde.",
                    }
                }
            },
        },
    },
    dependencies=[Depends(_register_limiter)],
)
async def register(
    payload: Annotated[RegisterRequest, Body(...)],
    use_case: Annotated[RegisterUser, Depends(_register)],
) -> RegisterResponse:
    try:
        user = await use_case.execute(
            name=payload.name,
            email=str(payload.email),
            password=payload.password,
        )
        return RegisterResponse(email=user.email)
    except UserAlreadyExistsError:
        return RegisterResponse(email=str(payload.email).strip().lower())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


# POST /authorize


@router.post(
    "/authorize",
    summary="Iniciar autenticación PKCE — obtener código de autorización",
    description=(
        "Valida las credenciales del usuario e inicia el flujo PKCE. "
        "Si son correctas, emite un `authorization_code` de un solo uso (TTL: 5 min) "
        "vinculado al `code_challenge` enviado. "
        "Tras **5 intentos fallidos consecutivos** la cuenta se bloquea temporalmente "
        "y se responde con `429` y el header `Retry-After`. "
        "Límite de velocidad: **10 peticiones / IP / ventana**."
    ),
    response_model=AuthorizationCodeResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: {
            "description": "Código de autorización emitido. Usar en POST /token.",
            "content": {
                "application/json": {
                    "example": {
                        "authorization_code": ("a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"),
                        "expires_in": 300,
                    }
                }
            },
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Credenciales inválidas (email no encontrado o contraseña incorrecta).",
            "model": OAuthErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "error": "invalid_grant",
                        "error_description": "Credenciales inválidas",
                    }
                }
            },
        },
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": (
                "Cuenta bloqueada por intentos fallidos excesivos. "
                "El header `Retry-After` y el campo `seconds_remaining` indican los segundos restantes de bloqueo."
            ),
            "model": OAuthErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "error": "account_locked",
                        "error_description": "Cuenta bloqueada. Intente de nuevo en 300 segundos.",
                        "seconds_remaining": 300,
                    }
                }
            },
        },
    },
    dependencies=[Depends(_authorize_limiter)],
)
async def authorize(
    payload: Annotated[AuthorizeRequest, Body(...)],
    use_case: Annotated[AuthorizeWithPkce, Depends(_authorize)],
) -> AuthorizationCodeResponse | JSONResponse:
    try:
        entry = await use_case.execute(
            email=str(payload.email),
            password=payload.password,
            code_challenge=payload.code_challenge,
            scopes=frozenset(payload.scopes),
        )
    except AccountLockedError as exc:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content=OAuthErrorResponse(
                error="account_locked",
                error_description=f"Cuenta bloqueada. Intente de nuevo en {exc.seconds_remaining} segundos.",
                seconds_remaining=exc.seconds_remaining,
            ).model_dump(exclude_none=True),
            headers={"Retry-After": str(exc.seconds_remaining)},
        )
    except InvalidCredentialsError:
        return _oauth_error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error="invalid_grant",
            description="Credenciales inválidas",
        )
    expires_in = max(
        int((entry.expires_at - datetime.now(UTC)).total_seconds()),
        1,
    )
    return AuthorizationCodeResponse(authorization_code=entry.code, expires_in=expires_in)


# POST /token


@router.post(
    "/token",
    summary="Intercambiar código de autorización por par de tokens JWT",
    description=(
        "Completa el flujo PKCE: valida el `code_verifier` contra el `code_challenge` "
        "almacenado, consume el `authorization_code` (lo invalida para usos futuros) "
        "y emite un par de tokens JWT firmados con RS256. "
        "El **access token** tiene TTL de 15 min; el **refresh token**, 7 días. "
        "Límite de velocidad: **5 peticiones / IP / ventana**."
    ),
    response_model=TokenPairResponse,
    responses={
        status.HTTP_200_OK: {
            "description": "Par de tokens emitido exitosamente.",
            "content": {
                "application/json": {
                    "example": {
                        "access": {
                            "token": (
                                "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9."
                                "eyJzdWIiOiJ1c3ItMDFIWFlaQVpCQ0RFRkdISUpLTE1OT1AifQ.SIGNATURE"
                            ),
                            "jti": "ati-01HXYAZABCDEFGHIJKLMNOP",
                            "expires_at": "2025-12-31T00:15:00Z",
                        },
                        "refresh": {
                            "token": (
                                "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9."
                                "eyJzdWIiOiJ1c3ItMDFIWFlaQVpCQ0RFRkdISUpLTE1OT1AifQ.SIGNATURE"
                            ),
                            "jti": "rti-01HXYAZABCDEFGHIJKLMNOP",
                            "expires_at": "2026-01-07T00:00:00Z",
                        },
                        "token_type": "Bearer",
                    }
                }
            },
        },
        status.HTTP_400_BAD_REQUEST: {
            "description": (
                "Código inválido, expirado, ya consumido; "
                "o `code_verifier` que no satisface el `code_challenge` registrado."
            ),
            "model": OAuthErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "error": "invalid_grant",
                        "error_description": "Código de autorización inválido o expirado",
                    }
                }
            },
        },
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "Rate limit excedido.",
            "model": OAuthErrorResponse,
        },
    },
    dependencies=[Depends(_token_limiter)],
)
async def token(
    payload: Annotated[TokenExchangeRequest, Body(...)],
    use_case: Annotated[ExchangeAuthorizationCode, Depends(_exchange)],
) -> TokenPairResponse | JSONResponse:
    try:
        pair = await use_case.execute(code=payload.code, code_verifier=payload.code_verifier)
    except AuthorizationCodeError as exc:
        return _oauth_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            error="invalid_grant",
            description=str(exc) or "Código de autorización inválido",
        )
    except PkceMismatchError as exc:
        return _oauth_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            error="invalid_grant",
            description=str(exc) or "code_verifier no coincide",
        )
    return TokenPairResponse.from_pair(pair)


# POST /refresh


@router.post(
    "/refresh",
    summary="Renovar par de tokens usando refresh token",
    description=(
        "Implementa **Token Rotation**: consume el refresh token presentado, "
        "lo revoca en Redis y emite un par nuevo. "
        "Si se detecta reutilización del mismo refresh token (posible robo de sesión), "
        "**toda la familia de tokens** queda revocada y el usuario debe reautenticarse. "
        "Límite de velocidad: **30 peticiones / IP / ventana**."
    ),
    response_model=TokenPairResponse,
    responses={
        status.HTTP_200_OK: {
            "description": "Par de tokens renovado exitosamente.",
            "content": {
                "application/json": {
                    "example": {
                        "access": {
                            "token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.NEW.SIGNATURE",
                            "jti": "ati-02HXYAZABCDEFGHIJKLMNOP",
                            "expires_at": "2025-12-31T01:15:00Z",
                        },
                        "refresh": {
                            "token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.NEW.SIGNATURE",
                            "jti": "rti-02HXYAZABCDEFGHIJKLMNOP",
                            "expires_at": "2026-01-14T00:00:00Z",
                        },
                        "token_type": "Bearer",
                    }
                }
            },
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": (
                "Refresh token inválido, expirado, revocado o reutilizado. "
                "En caso de reutilización, toda la familia de sesiones queda invalidada."
            ),
            "model": OAuthErrorResponse,
            "content": {
                "application/json": {
                    "examples": {
                        "expirado": {
                            "summary": "Token expirado",
                            "value": {
                                "error": "invalid_grant",
                                "error_description": "Refresh token expirado",
                            },
                        },
                        "reutilizado": {
                            "summary": "Token reutilizado (posible ataque)",
                            "value": {
                                "error": "invalid_grant",
                                "error_description": "Refresh token reusado, sesión revocada",
                            },
                        },
                        "revocado": {
                            "summary": "Token revocado manualmente",
                            "value": {
                                "error": "invalid_grant",
                                "error_description": "Refresh token revocado",
                            },
                        },
                    }
                }
            },
        },
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "Rate limit excedido.",
        },
    },
    dependencies=[Depends(_refresh_limiter)],
)
async def refresh(
    payload: Annotated[TokenRefreshRequest, Body(...)],
    use_case: Annotated[RefreshTokenPair, Depends(_refresh)],
) -> TokenPairResponse | JSONResponse:
    try:
        pair = await use_case.execute(payload.refresh_token, scopes=frozenset())
    except TokenReusedError as exc:
        return _oauth_error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error="invalid_grant",
            description=str(exc) or "Refresh token reusado, sesión revocada",
        )
    except TokenExpiredError:
        return _oauth_error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error="invalid_grant",
            description="Refresh token expirado",
        )
    except (InvalidTokenError, TokenRevokedError) as exc:
        return _oauth_error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error="invalid_grant",
            description=str(exc) or "Refresh token inválido",
        )
    return TokenPairResponse.from_pair(pair)


# GET /me


@router.get(
    "/me",
    summary="Obtener identidad del usuario autenticado",
    description=(
        "Decodifica y verifica el `access_token` del header `Authorization: Bearer`. "
        "Devuelve el `subject` (ID del usuario) y los `scopes` de la sesión activa. "
        "No requiere acceso a base de datos: la verificación es completamente local "
        "contra la clave pública RSA y la lista de revocación en Redis."
    ),
    response_model=PrincipalView,
    responses={
        status.HTTP_200_OK: {
            "description": "Identidad verificada del token presentado.",
            "content": {
                "application/json": {
                    "example": {
                        "subject": "usr-01HXYAZABCDEFGHIJKLMNOP",
                        "scopes": ["agent:run", "profile:read"],
                    }
                }
            },
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": ("Token ausente, mal formado, con firma inválida, expirado o revocado."),
            "model": OAuthErrorResponse,
            "content": {
                "application/json": {
                    "examples": {
                        "sin_token": {
                            "summary": "Header Authorization ausente",
                            "value": {
                                "error": "missing_token",
                                "error_description": ("Se requiere el header Authorization: Bearer <token>"),
                            },
                        },
                        "token_expirado": {
                            "summary": "Token expirado",
                            "value": {
                                "error": "invalid_token",
                                "error_description": "El access token ha expirado",
                            },
                        },
                        "token_revocado": {
                            "summary": "Token revocado",
                            "value": {
                                "error": "invalid_token",
                                "error_description": "El token ha sido revocado",
                            },
                        },
                    }
                }
            },
        },
    },
)
async def me(
    principal: Annotated[Principal, Depends(get_principal)],
    request: Request,
) -> PrincipalView:
    auth_comp = _auth_components(request)
    user_repo = getattr(auth_comp, "user_repository", None)
    user = await user_repo.by_id(principal.subject) if user_repo else None
    return PrincipalView(
        subject=principal.subject,
        name=user.name if user else None,
        email=user.email if user else None,
        avatar_url=user.avatar_url if user else None,
        scopes=sorted(principal.scopes),
    )


# POST /logout


@router.post(
    "/logout",
    summary="Cerrar sesión y revocar tokens activos",
    description=(
        "Revoca el `access_token` del header `Authorization: Bearer` y, opcionalmente, "
        "el `refresh_token` del body. Ambos tokens quedan invalidados en Redis "
        "hasta su expiración natural. "
        "Devuelve `204 No Content` en éxito (sin body). "
        "Límite de velocidad: **20 peticiones / IP / ventana**."
    ),
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_204_NO_CONTENT: {
            "description": "Sesión cerrada exitosamente. No se devuelve body.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": (
                "Token ausente, mal formado, expirado o ya revocado. "
                "Nota: incluso si el token está expirado, la revocación puede proceder "
                "para limpiar el refresh token si se proporcionó."
            ),
            "model": OAuthErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "error": "invalid_token",
                        "error_description": "El access token presentado es inválido o ha expirado",
                    }
                }
            },
        },
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "Rate limit excedido.",
        },
    },
    dependencies=[Depends(_logout_limiter)],
)
async def logout(
    payload: Annotated[LogoutRequest, Body(...)],
    use_case: Annotated[RevokeSession, Depends(_revoke)],
    request: Request,
) -> Response:
    if settings.auth_disabled:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    bearer = request.headers.get("authorization", "")
    access_token = bearer.removeprefix("Bearer ").strip() if bearer.startswith("Bearer ") else bearer.strip()

    if not access_token and not payload.refresh_token:
        return _oauth_error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error="invalid_token",
            description="Token ausente o inválido",
        )

    try:
        await use_case.execute(access_token=access_token, refresh_token=payload.refresh_token)
    except (InvalidTokenError, TokenExpiredError, TokenRevokedError) as exc:
        return _oauth_error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error="invalid_token",
            description=str(exc) or "Token inválido",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
