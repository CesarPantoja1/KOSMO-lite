import asyncio
import contextlib
import json
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from http import HTTPStatus
from typing import Any, cast

import structlog
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from kosmo.application.codegen.recover_zombie_implementations import recover_zombie_implementations
from kosmo.application.integrations.recover_pending_deployments import recover_pending_deployments
from kosmo.config import settings
from kosmo.contracts.sdd.errors import SpecError
from kosmo.infrastructure.api.composition import AppContainer, build_app_components
from kosmo.infrastructure.api.middlewares import RequestLoggingMiddleware
from kosmo.infrastructure.api.routers.ai_config import router as ai_config_router
from kosmo.infrastructure.api.routers.auth import router as auth_router
from kosmo.infrastructure.api.routers.chat_sessions import router as chat_sessions_router
from kosmo.infrastructure.api.routers.consistency import router as consistency_router
from kosmo.infrastructure.api.routers.deployment import router as deployment_router
from kosmo.infrastructure.api.routers.discovery import router as discovery_router
from kosmo.infrastructure.api.routers.documents import router as documents_router
from kosmo.infrastructure.api.routers.feature_chat import router as feature_chat_router
from kosmo.infrastructure.api.routers.features import router as features_router
from kosmo.infrastructure.api.routers.github import router as github_router
from kosmo.infrastructure.api.routers.implementations import router as implementations_router
from kosmo.infrastructure.api.routers.integrations import router as integrations_router
from kosmo.infrastructure.api.routers.knowledge import router as knowledge_router
from kosmo.infrastructure.api.routers.mcp import router as mcp_router
from kosmo.infrastructure.api.routers.modelo import router as modelo_router
from kosmo.infrastructure.api.routers.projects import router as projects_router
from kosmo.infrastructure.api.routers.requirement_chat import router as requirement_chat_router
from kosmo.infrastructure.api.routers.requirements import router as requirements_router
from kosmo.infrastructure.api.routers.schemas import router as schemas_router
from kosmo.infrastructure.api.routers.traceability import router as traceability_router
from kosmo.infrastructure.api.schemas import HttpErrorResponse
from kosmo.infrastructure.persistence.postgres.outbox import OutboxHandler, run_outbox_worker
from kosmo.infrastructure.telemetry import (
    configure_telemetry,
    get_current_trace_id,
    instrument_app,
    instrument_prometheus,
)

_log = structlog.get_logger(__name__)

# Metadatos OpenAPI

_OPENAPI_TAGS = [
    {
        "name": "auth",
        "description": (
            "Flujo de autenticación PKCE + OAuth 2.0. "
            "Los endpoints siguen el estándar RFC 6749/7636: el cliente genera un "
            "``code_verifier`` efímero, solicita un ``authorization_code`` en ``/authorize``, "
            "lo intercambia por tokens JWT en ``/token`` y los renueva con ``/refresh``. "
            "Todos los endpoints protegidos requieren ``Authorization: Bearer <access_token>``."
        ),
    },
    {
        "name": "projects",
        "description": (
            "Gestión de proyectos. Permite crear, listar y consultar proyectos "
            "asociados al usuario autenticado. Cada proyecto agrupa el ciclo "
            "completo de especificación, modelado y generación de artefactos."
        ),
    },
    {
        "name": "discovery",
        "description": (
            "Generación de documentos de descubrimiento mediante IA. "
            "Permite generar, consultar y actualizar el documento de visión "
            "de producto de un proyecto. El documento se estructura en 8 "
            "secciones obligatorias que cubren visión, problema, actores, "
            "propuesta de valor, casos de uso, capacidades, reglas de negocio "
            "y atributos de calidad."
        ),
    },
    {
        "name": "features",
        "description": (
            "Generación y gestión de características del producto software mediante IA. "
            "Permite generar características a partir del documento de descubrimiento, "
            "sugerir nuevas características no duplicadas, listar las existentes y "
            "guardar las seleccionadas por el usuario."
        ),
    },
    {
        "name": "requirements",
        "description": (
            "Generación y gestión de requisitos EARS por característica mediante IA. "
            "Permite generar requisitos a partir del documento de descubrimiento y la "
            "característica seleccionada, consultarlos y actualizar su contenido en Markdown."
        ),
    },
    {
        "name": "modelo",
        "description": (
            "Generación y consulta de diagramas de actividad PlantUML por característica mediante IA. "
            "Permite generar diagramas UML a partir de los requisitos EARS y consultar los diagramas generados."
        ),
    },
    {
        "name": "schemas",
        "description": (
            "Introspección de contratos. Permite al Frontend consultar el JSON Schema "
            "de cualquier DTO expuesto por la API para generación dinámica de formularios, "
            "validaciones y tipos TypeScript."
        ),
    },
    {
        "name": "documents",
        "description": "Modificación directa de documentos sin fase de plan intermedio.",
    },
]

_CONTACT = {
    "name": "Equipo KOSMO",
    "email": "dev@kosmo.app",
    "url": "https://github.com/CesarPantoja1/KOSMO",
}

_LICENSE = {
    "name": "MIT",
    "url": "https://opensource.org/licenses/MIT",
}

_DESCRIPTION = """
KOSMO Backend API

KOSMO es una plataforma de agentes de IA con identidad centralizada.
Esta API gestiona el ciclo completo de autenticación de usuarios y la
introspección de contratos de datos para el Frontend.

### Flujo de autenticación recomendado

```
1. POST /api/v1/auth/register      → Crear cuenta
2. POST /api/v1/auth/authorize     → Obtener authorization_code (PKCE)
3. POST /api/v1/auth/token         → Intercambiar código por JWT pair
4. GET  /api/v1/auth/me            → Verificar identidad (Bearer token)
5. POST /api/v1/auth/refresh       → Renovar tokens antes de expirar
6. POST /api/v1/auth/logout        → Revocar sesión activa
```

### Seguridad

- Tokens firmados con **RS256** (par de claves RSA 2048-bit)
- Contraseñas hasheadas con **Argon2id** (OWASP 2025)
- Refresh tokens con **Token Rotation**: cada uso emite un par nuevo
- Rate limiting por IP en todos los endpoints sensibles
- Secrets cifrados con **Fernet** (AES-128-CBC + HMAC-SHA256)

### Respuestas de error

Todos los errores de autenticación siguen el esquema `OAuthErrorResponse`
(RFC 6749). Los errores de infraestructura usan `HttpErrorResponse`.
"""

_SERVERS = [
    {
        "url": "http://localhost:8000",
        "description": "Local — desarrollo en máquina del programador",
    },
    {
        "url": "https://api-dev.kosmo.app",
        "description": "Desarrollo — entorno de integración continua",
    },
    {
        "url": "https://api.kosmo.app",
        "description": "Producción — tráfico real de usuarios",
    },
]

# Respuestas globales reutilizables

_GLOBAL_RESPONSES = {
    403: {
        "description": (
            "Forbidden — El token es válido pero no tiene los scopes necesarios para acceder al recurso solicitado."
        ),
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/HttpErrorResponse"},
                "example": {"detail": "No tienes permisos suficientes para realizar esta acción."},
            }
        },
    },
    500: {
        "description": (
            "Internal Server Error — Error inesperado en el servidor. "
            "Se registra automáticamente en el sistema de observabilidad (Logfire/OTEL). "
            "El cliente debe implementar retry con back-off exponencial."
        ),
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/HttpErrorResponse"},
                "example": {"detail": "Error interno del servidor. Por favor contacte al soporte."},
            }
        },
    },
}

# Ciclo de vida y aplicación


def _make_outbox_handler(container: AppContainer) -> OutboxHandler:
    async def handler(job_type: str, payload: dict[str, Any]) -> None:
        import structlog

        _log = structlog.get_logger("kosmo.outbox")
        agent = container.pipeline.agent
        if job_type == "reflect_and_consolidate":
            from kosmo.contracts.auth.context import current_user_id
            from kosmo.contracts.memory.agent_memory import AgentMemoryId
            from kosmo.contracts.pipeline.phase_outputs import ValidationResult
            from kosmo.contracts.sdd.document import SpecPhase

            user_id = payload.get("user_id")
            token = current_user_id.set(str(user_id)) if user_id else None
            try:
                await agent.reflect_and_consolidate(
                    session_id=AgentMemoryId(payload["session_id"]),
                    phase=SpecPhase(payload["phase"]),
                    session_type=payload["session_type"],
                    is_completed=payload.get("is_completed", True),
                    current_iteration=payload.get("current_iteration", 1),
                    validation=ValidationResult(
                        is_valid=payload.get("validation_is_valid", True),
                        errors=payload.get("validation_errors", "").split("; "),
                    ),
                )
            except Exception:
                _log.warning("outbox.handler_failed", job_type=job_type, exc_info=True)
                raise
            finally:
                if token is not None:
                    current_user_id.reset(token)
        elif job_type == "consistency_evaluate":
            from kosmo.application.consistency.run_consistency_evaluation import run_consistency_evaluation

            await run_consistency_evaluation(
                payload,
                project_repo=container.repos.projects,
                feature_repo=container.repos.features,
                requirement_repo=container.repos.requirements,
                diagram_repo=container.repos.diagrams,
                document_repo=container.repos.documents,
                evaluator=container.pipeline.consistency_evaluator,
                evaluation_repo=container.repos.consistency_evaluations,
                implementation_repo=container.repos.implementations,
            )
        else:
            _log.warning("outbox.unknown_job_type", job_type=job_type)

    return handler


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    configure_telemetry(settings)
    components = build_app_components(settings)
    if settings.server_workers > 1 and not components.codegen.implementation_broker.is_distributed:
        _log.warning(
            "implementation_broker.multi_worker_warning",
            workers=settings.server_workers,
            detail=(
                "ImplementationEventBroker opera en memoria. "
                "Ejecutar con múltiples workers (--workers > 1) puede causar que los eventos SSE "
                "no lleguen al suscriptor si la petición llega a un worker diferente. "
                "Se recomienda ejecutar con --workers 1 o configurar REDIS_URL."
            ),
        )
    app.state.container = components
    app.state.requirement_repo = components.repos.requirements
    app.state.diagram_repo = components.repos.diagrams

    outbox_task = asyncio.create_task(run_outbox_worker(components.pipeline.outbox, _make_outbox_handler(components)))

    # Recuperación best-effort de generaciones huérfanas tras un reinicio del backend:
    # marcar IN_PROGRESS como FAILED, cerrar sesiones OpenCode y liberar locks de workspace.
    with contextlib.suppress(Exception):
        await recover_zombie_implementations(
            implementation_repo=components.repos.implementations,
            opencode_client=components.codegen.opencode_client,
            workspace_manager=components.codegen.workspace_manager,
            is_active=components.codegen.implementation_broker.is_running_distributed,
        )
    with contextlib.suppress(Exception):
        await components.pipeline.agent_memory.purge_stale_sessions(older_than_days=7, incomplete_only=True)

    async def _recover_after_lease_expiry() -> None:
        delay = 100.0
        while True:
            await asyncio.sleep(delay)
            try:
                await recover_zombie_implementations(
                    implementation_repo=components.repos.implementations,
                    opencode_client=components.codegen.opencode_client,
                    workspace_manager=components.codegen.workspace_manager,
                    is_active=components.codegen.implementation_broker.is_running_distributed,
                )
                with contextlib.suppress(Exception):
                    await components.pipeline.agent_memory.purge_stale_sessions(older_than_days=7, incomplete_only=True)
                delay = 100.0
            except Exception:
                _log.warning("codegen.recovery_task_error", exc_info=True)
                delay = min(delay * 2, 600.0)

    recovery_task = asyncio.create_task(_recover_after_lease_expiry(), name="codegen_recovery_task")

    # El estado de despliegue persiste en PostgreSQL, pero las tareas de sondeo no.
    # Reanudarlas evita que un reinicio durante una publicación deje la UI en BUILDING.
    with contextlib.suppress(Exception):
        await recover_pending_deployments(
            project_deployment_repo=components.repos.project_deployments,
            project_repo=components.repos.projects,
            deployment_worker=components.integrations.deployment_worker,
        )

    instrument_app(settings, app=app, db_engine=components.db_engine)
    try:
        yield
    finally:
        recovery_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await recovery_task
        outbox_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await outbox_task
        await components.close()


app = FastAPI(
    title="KOSMO API",
    version=settings.api_version,
    description=_DESCRIPTION,
    contact=_CONTACT,
    license_info=_LICENSE,
    openapi_tags=_OPENAPI_TAGS,
    servers=_SERVERS,
    docs_url="/docs" if settings.env != "production" else None,
    redoc_url="/redoc" if settings.env != "production" else None,
    openapi_url="/api/v1/openapi.json" if settings.env != "production" else None,
    lifespan=lifespan,
)

instrument_prometheus(app)


@app.exception_handler(SpecError)
async def spec_error_handler(_request: Request, exc: SpecError) -> JSONResponse:
    problem = exc.problem
    return JSONResponse(
        status_code=problem.status,
        content={
            "type": problem.type,
            "title": problem.title,
            "status": problem.status,
            "detail": problem.detail,
            "instance": problem.instance,
            "trace_id": problem.trace_id,
            "violations": [{"loc": v.loc, "msg": v.msg, "input": v.input} for v in problem.violations],
        },
        media_type="application/problem+json",
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    status_code = exc.status_code
    try:
        title = HTTPStatus(status_code).phrase
    except ValueError:
        title = "HTTP Error"

    detail = exc.detail if exc.detail else title

    return JSONResponse(
        status_code=status_code,
        content={
            "type": f"urn:kosmo:error:{status_code}",
            "title": title,
            "status": status_code,
            "detail": detail,
            "instance": request.url.path,
            "trace_id": get_current_trace_id(),
            "violations": [],
        },
        headers=getattr(exc, "headers", None),
        media_type="application/problem+json",
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    status_code = 422
    violations: list[dict[str, Any]] = []
    for err in exc.errors():
        inp: Any = err.get("input")
        safe_input: Any
        if isinstance(inp, (str, int, float, bool, type(None))):
            safe_input = inp
        else:
            try:
                json.dumps(inp)
                safe_input = inp
            except (TypeError, ValueError):
                safe_input = str(inp)

        violations.append(
            {
                "loc": [str(x) for x in err.get("loc", [])],
                "msg": str(err.get("msg", "")),
                "input": safe_input,
            }
        )

    return JSONResponse(
        status_code=status_code,
        content={
            "type": "urn:kosmo:validation:error",
            "title": "Error de validación",
            "status": status_code,
            "detail": "El formato o contenido de la solicitud es inválido",
            "instance": request.url.path,
            "trace_id": get_current_trace_id(),
            "violations": violations,
        },
        media_type="application/problem+json",
    )


_Scope = dict[str, Any]
_Message = dict[str, Any]
_ASGIApp = Callable[[_Scope, Callable[[], Awaitable[_Message]], Callable[[_Message], Awaitable[None]]], Awaitable[None]]


_PERMISSIONS_POLICY = (
    b"accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()"
)
_CSP_DEV = (
    b"default-src 'self'; "
    b"img-src 'self' data: https://fastapi.tiangolo.com; "
    b"script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    b"style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    b"frame-ancestors 'none'"
)
_CSP_PROD = b"default-src 'none'; frame-ancestors 'none'"


class SecurityHeadersMiddleware:
    """Inyecta encabezados HTTP de seguridad defensivos en las respuestas."""

    def __init__(self, app: _ASGIApp, is_production: bool = False) -> None:
        self.app = app
        self._is_production = is_production

    async def __call__(
        self,
        scope: _Scope,
        receive: Callable[[], Awaitable[_Message]],
        send: Callable[[_Message], Awaitable[None]],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: _Message) -> None:
            if message["type"] == "http.response.start":
                raw_headers = list(message.get("headers", []))
                names = {h[0].lower() for h in raw_headers}

                if b"x-content-type-options" not in names:
                    raw_headers.append((b"x-content-type-options", b"nosniff"))
                if b"x-frame-options" not in names:
                    raw_headers.append((b"x-frame-options", b"DENY"))
                if b"referrer-policy" not in names:
                    raw_headers.append((b"referrer-policy", b"strict-origin-when-cross-origin"))
                if b"permissions-policy" not in names:
                    raw_headers.append((b"permissions-policy", _PERMISSIONS_POLICY))
                if b"content-security-policy" not in names:
                    csp = _CSP_PROD if self._is_production else _CSP_DEV
                    raw_headers.append((b"content-security-policy", csp))
                if self._is_production and b"strict-transport-security" not in names:
                    raw_headers.append((b"strict-transport-security", b"max-age=63072000; includeSubDomains"))

                message["headers"] = raw_headers

            await send(message)

        await self.app(scope, receive, send_wrapper)


_allow_credentials = "*" not in settings.parsed_cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.parsed_cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    SecurityHeadersMiddleware,
    is_production=settings.env == "production",
)
app.add_middleware(RequestLoggingMiddleware)

if not settings.auth_disabled:
    app.include_router(auth_router)
app.include_router(ai_config_router)
app.include_router(projects_router)
app.include_router(discovery_router)
app.include_router(features_router)
app.include_router(feature_chat_router)
app.include_router(requirements_router)
app.include_router(requirement_chat_router)
app.include_router(chat_sessions_router)
app.include_router(modelo_router)
app.include_router(consistency_router)
app.include_router(schemas_router)
app.include_router(knowledge_router)
app.include_router(documents_router)
app.include_router(traceability_router)
app.include_router(mcp_router)
app.include_router(implementations_router)
app.include_router(integrations_router)
app.include_router(github_router)
app.include_router(deployment_router)


@app.get("/health", tags=["health"], summary="Health check", include_in_schema=True)
async def health() -> dict[str, str]:
    """Verificación de disponibilidad del servidor.

    Devuelve ``{"status": "ok"}`` si el proceso está activo.
    No verifica conectividad con base de datos ni Redis.
    """
    return {"status": "ok"}


def _extract_pool_metrics(engine: Any) -> dict[str, int]:
    """Extrae de forma defensiva las métricas del pool de conexiones."""
    pool = getattr(engine, "pool", None)
    if pool is None and hasattr(engine, "sync_engine"):
        pool = getattr(engine.sync_engine, "pool", None)
    if pool is None:
        return {}
    metrics: dict[str, int] = {}
    for attr, key in [
        ("size", "size"),
        ("checkedin", "checked_in"),
        ("checkedout", "checked_out"),
        ("overflow", "overflow"),
    ]:
        fn = getattr(pool, attr, None)
        if callable(fn):
            with contextlib.suppress(Exception):
                val = fn()
                if isinstance(val, (int, float, str)):
                    metrics[key] = int(val)
    return metrics


def _extract_broker_info(container: Any) -> dict[str, str]:
    """Reporta el tipo y estado operativo del broker de eventos."""
    codegen = getattr(container, "codegen", None)
    broker = getattr(codegen, "implementation_broker", None) if codegen else None
    is_redis = getattr(broker, "_redis", None) is not None if broker else False
    return {
        "type": "redis" if is_redis else "in_memory",
        "status": "connected" if is_redis or getattr(container, "redis", None) is not None else "in_memory",
    }


@app.get("/ready", tags=["health"], summary="Readiness check", include_in_schema=False)
async def readiness(request: Request) -> dict[str, Any]:
    """Verifica las dependencias requeridas antes de aceptar tráfico público y reporta saturación."""
    try:
        container = cast(AppContainer, request.app.state.container)
        async with container.db_engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        if container.redis is not None:
            await cast(Any, container.redis).ping()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dependencias no disponibles",
        ) from exc

    return {
        "status": "ready",
        "pool": _extract_pool_metrics(getattr(container, "db_engine", None)),
        "broker": _extract_broker_info(container),
    }


# Especificación OpenAPI customizada


def _custom_openapi() -> dict[str, Any]:
    """Genera la especificación OpenAPI enriquecida con respuestas globales.

    Se inyectan las respuestas 403 y 500 en cada operación para que el
    Frontend pueda manejar todos los errores de forma consistente.
    """
    if app.openapi_schema:
        return app.openapi_schema

    schema: dict[str, Any] = get_openapi(
        title=app.title,
        version=app.version,
        description=_DESCRIPTION,
        contact=_CONTACT,
        license_info=_LICENSE,
        tags=_OPENAPI_TAGS,
        servers=_SERVERS,
        routes=app.routes,
    )

    # Registrar HttpErrorResponse en components/schemas
    http_error_schema = HttpErrorResponse.model_json_schema()

    components: dict[str, Any] = schema.setdefault("components", {})
    schemas: dict[str, Any] = components.setdefault("schemas", {})
    schemas["HttpErrorResponse"] = http_error_schema

    # Inyectar respuestas globales (403, 500) en todos los paths
    paths = cast(dict[str, Any], schema.get("paths", {}))
    for path_item in paths.values():
        if isinstance(path_item, dict):
            path_item_dict = cast(dict[str, Any], path_item)
            for operation in path_item_dict.values():
                if isinstance(operation, dict):
                    operation_dict = cast(dict[str, Any], operation)
                    responses = operation_dict.get("responses")
                    if isinstance(responses, dict):
                        responses_dict = cast(dict[str, Any], responses)
                        for status_code, response_def in _GLOBAL_RESPONSES.items():
                            responses_dict.setdefault(str(status_code), response_def)

    app.openapi_schema = schema
    return schema


app.openapi = _custom_openapi  # type: ignore[method-assign]
