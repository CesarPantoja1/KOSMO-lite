# `infrastructure/api/` — FastAPI, Routers, Composición Hexagonal, SSE y Broker de Implementación

## Responsabilidad y Propósito

El módulo `infrastructure/api/` constituye el adaptador primario de entrada (driving/inbound adapter) en la arquitectura hexagonal de KOSMO. Expone la funcionalidad de la plataforma hacia el exterior mediante una API REST y flujos de eventos SSE (Server-Sent Events) sobre HTTP/1.1 y HTTP/2.

Sus responsabilidades fundamentales comprenden:
- **Punto de Entrada y Servidor ASGI**: Configuración de la aplicación FastAPI (`main.py`) con ciclo de vida asíncrono (`lifespan`), tareas en segundo plano (workers de Outbox, recuperación de implementaciones zombies y despliegues huérfanos), middlewares de defensa en profundidad y observabilidad distribuida.
- **Catálogo Exhaustivo de Routers**: Exposición de exactamente 20 routers especializados bajo el prefijo `/api/v1/` y `/mcp`, que delegan directamente en los casos de uso de la capa `application/` sin contener reglas de negocio.
- **Composición Central de Dependencias (Composition Root)**: Cableado de todo el grafo de dependencias en `composition/`, instanciando repositorios, adaptadores de seguridad, clientes LLM, ejecutores de código, workspaces y registrando los 25 skills del pipeline SDD en un `AppContainer` inmutable.
- **Seguridad y Control de Acceso**: Dependencias de autenticación para validación de tokens JWT asimétricos (RS256), propagación de identidad mediante `current_user_id` (`ContextVar`), control de acceso a nivel de objeto (BOLA/IDOR guards con respuestas HTTP 404 defensivas) y verificación de permisos (`require_scopes`).
- **Limitación de Tasa (Rate Limiting)**: Control de saturación distribuido basado en scripts Lua atómicos en Redis con política estricta de *fail-closed* en entornos de staging y producción.
- **Streaming en Tiempo Real y Desacoplamiento Asíncrono**: Transmisión SSE de tokens de chat y consistencia con latidos periódicos (`with_heartbeat`), y broker de eventos (`ImplementationEventBroker`) en modo dual (en memoria para desarrollo local o distribuido con Redis Streams para despliegues con múltiples workers).

---

## Estructura de Archivos y Componentes

```
infrastructure/api/
├── __init__.py                  # Reexporta símbolos públicos (app, create_app)
├── main.py                      # Fábrica FastAPI, lifespan, middlewares, handlers RFC 7807, /health y /ready
├── schemas.py                   # DTOs Pydantic v2 de request/response HTTP (validaciones y ejemplos OpenAPI)
├── async_generation.py          # Helpers de streaming SSE (with_heartbeat, sse_chat_response, sse_consistency_response)
├── implementation_broker.py     # ImplementationEventBroker (cola local / Redis Streams, heartbeats de actividad)
├── composition/                 # Raíz de composición e inyección de dependencias
│   ├── __init__.py              # AppContainer (dataclass tipada) y función build_app_components()
│   ├── auth.py                  # build_auth_components() -> AuthComponents
│   ├── codegen.py               # build_codegen_components(), build_code_runner(), build_workspace_manager() -> CodegenComponents
│   ├── integrations.py          # build_integrations_components() -> IntegrationsComponents
│   ├── pipeline.py              # build_pipeline_components() -> PipelineComponents
│   ├── sdd.py                   # Constructores SDD: Project, Discovery, Features, Requirements, Modelo, Consistency
│   └── skill_registration.py    # build_skill_registry() -> Registro de los 25 skills del motor SDD
├── dependencies/                # Inyectores de dependencias FastAPI (Depends)
│   ├── __init__.py              # Reexportación de dependencias públicas
│   ├── ai_config.py             # get_manage_ai_preferences_use_case, get_validate_ai_connection_use_case, _resolve_cipher
│   ├── auth.py                  # get_principal, require_project_owner, verify_project_owner, verify_feature_owner, require_scopes
│   ├── container.py             # get_container() -> AppContainer
│   ├── integrations.py          # Proveedores de use cases de GitHub, Railway y DeploymentPollingWorker
│   └── rate_limit.py            # IpRateLimiter, ProjectGenerationRateLimiter (scripts Lua, proxy CIDR, fail-closed)
├── middlewares/                 # Middlewares ASGI para HTTP
│   ├── __init__.py
│   └── logging.py               # RequestLoggingMiddleware (ULID request_id, structlog contextvars, span OTel http.request)
└── routers/                     # 20 routers HTTP modulares
    ├── __init__.py
    ├── ai_config.py             # /api/v1/ai-config (preferencias de proveedor, modelo y clave API BYOK)
    ├── auth.py                  # /api/v1/auth (flujo PKCE RFC 7636, registro, intercambio de código, refresh, logout, me)
    ├── chat_sessions.py         # /api/v1/projects/{project_id}/chat/sessions (listado, creación y borrado de sesiones)
    ├── consistency.py           # /api/v1/projects/{project_id}/consistency (evaluación, revisión y resolución en cascada)
    ├── deployment.py            # /api/v1/projects/{project_id}/deployment (despliegues cloud en Railway, sondeo y logs)
    ├── discovery.py             # /api/v1/projects/{project_id}/discovery (generación, consulta, refinamiento y guardado)
    ├── documents.py             # /api/v1/projects/{project_id}/documents (modificación directa de documentos de especificación)
    ├── features.py              # /api/v1/projects/{project_id}/features (generación, sugerencias, CRUD, chequeo de consistencia)
    ├── feature_chat.py          # /api/v1/projects/{project_id}/features/{feature_id}/chat (chat SSE de nivel de característica)
    ├── github.py                # /api/v1/integrations/github (OAuth, listado y vinculación de repositorios, sincronización)
    ├── implementations.py       # /api/v1/projects/{project_id}/features/{feature_id}/implementation (arranque y stream de código)
    ├── integrations.py          # /api/v1/integrations (estado global de integraciones externas y vinculación de Railway)
    ├── knowledge.py             # /api/v1/projects/{project_id}/knowledge (patrones heurísticos aprendidos y consolidación)
    ├── mcp.py                   # /mcp (herramientas MCP para agentes OpenCode: requisitos EARS y diagramas PlantUML)
    ├── modelo.py                # /api/v1/projects/{project_id}/features/{feature_id}/modelo (diagramas de actividad PlantUML)
    ├── projects.py              # /api/v1/projects (CRUD de proyectos de software)
    ├── requirements.py          # /api/v1/projects/{project_id}/features/{feature_id}/requirements (requisitos EARS por característica)
    ├── requirement_chat.py      # /api/v1/projects/{project_id}/features/{feature_id}/requirements/chat (chat SSE de requisitos)
    ├── schemas.py               # /api/v1/schemas (introspección de esquemas JSON Schema de contratos para frontend)
    └── traceability.py          # /api/v1/projects/{project_id}/traceability (grafo de dependencias y análisis de impacto)
```

---

## Ciclo de Vida y Servidor FastAPI (`main.py`)

### 1. Inicialización y Context Manager `lifespan`
La aplicación FastAPI se instancia mediante la función `create_app()` o la instancia `app` en `main.py`, asociando el context manager asíncrono `lifespan`:
1. **Configuración de Telemetría**: Invoca `configure_telemetry(settings)` para inicializar Logfire, OpenTelemetry y structlog.
2. **Construcción del Grafo de Componentes**: Ejecuta `build_app_components(settings)` generando la instancia de `AppContainer` que se almacena en `app.state.container`.
3. **Advertencia de Múltiples Workers**: Si `settings.server_workers > 1` y el broker de implementación opera en memoria, emite una advertencia de riesgo de pérdida de eventos SSE por falta de Redis.
4. **Inicio de Tareas en Segundo Plano**:
   - `outbox_task`: Ejecuta `run_outbox_worker` con el handler `_make_outbox_handler` para procesar tareas de reflexión/consolidación (`reflect_and_consolidate`) y evaluación de consistencia en segundo plano (`consistency_evaluate`).
   - `recover_zombie_implementations`: Reconciliación inmediata en el arranque para marcar implementaciones en estado `IN_PROGRESS` como `FAILED`, cerrar sesiones OpenCode y liberar locks de workspace huérfanos.
   - `purge_stale_sessions`: Purga de sesiones incompletas de memoria del agente con antigüedad superior a 7 días.
   - `recovery_task` (`_recover_after_lease_expiry`): Tarea en bucle periódico cada 100 segundos con backoff exponencial defensivo ante fallos (hasta 600s) para asegurar la liberación de locks de código cuyo lease haya expirado.
   - `recover_pending_deployments`: Reanuda el sondeo de despliegues en Railway que hayan quedado en estado pendiente tras un reinicio del proceso.
5. **Instrumentación ASGI**: Registra métricas de Prometheus (`instrument_prometheus`) y OpenTelemetry (`instrument_app`).
6. **Apagado Ordenado (Graceful Shutdown)**: Al detener el servidor, cancela y espera la finalización de `recovery_task` y `outbox_task`, y随后 ejecuta `await container.close()` para cerrar conexiones a Redis, OpenCode, RemoteCodeRunner, DeploymentWorker y el pool de SQLAlchemy.

### 2. Endpoints Globales de Salud
- **`GET /health`** (Liveness Probe):
  - Retorna `{"status": "ok"}` inmediatamente.
  - Diseñado para orquestadores (Kubernetes, Docker, Railway); no comprueba conectividad con bases de datos ni servicios externos.
- **`GET /ready`** (Readiness Probe):
  - Verifica dependencias críticas ejecutando `SELECT 1` en PostgreSQL y `redis.ping()` en Redis (si está configurado).
  - En caso de indisponibilidad de alguna dependencia, responde con HTTP 503 (`Service Unavailable`).
  - Reporta métricas del pool de conexiones extraídas defensivamente: `size`, `checked_in`, `checked_out` y `overflow`.
  - Reporta el estado operativo del broker de implementación: `type` (`redis` o `in_memory`) y `status` (`connected` o `in_memory`).

### 3. Middlewares de Seguridad y Observabilidad
1. **`CORSMiddleware`**: Configurado con `settings.parsed_cors_origins`, permitiendo credenciales únicamente si el comodín `*` no está presente entre los orígenes permitidos.
2. **`SecurityHeadersMiddleware`**: Inserta encabezados de protección defensivos en cada respuesta HTTP:
   - `X-Content-Type-Options: nosniff`
   - `X-Frame-Options: DENY`
   - `Referrer-Policy: strict-origin-when-cross-origin`
   - `Permissions-Policy: accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()`
   - `Content-Security-Policy`: Aplica directiva estricta `default-src 'none'; frame-ancestors 'none'` en producción (`_CSP_PROD`), o directiva relajada para visualización de Swagger/Redoc en desarrollo (`_CSP_DEV`).
   - `Strict-Transport-Security: max-age=63072000; includeSubDomains` (únicamente en producción).
3. **`RequestLoggingMiddleware`** (`middlewares/logging.py`):
   - Genera un identificador único por petición mediante `ULID().hex` asignado a `request_id`.
   - Asocia a las variables de contexto de structlog: `request_id`, `ip_address` y `user_agent`.
   - Abre un span raíz de OpenTelemetry titulado `"http.request"` con atributos `http.method`, `http.url`, `http.route` y `http.status_code`.
   - Mide la duración precisa con `time.perf_counter()` y registra logs estructurados de inicio, finalización o error de la petición.

### 4. Manejo Global de Excepciones (RFC 7807)
La API estandariza todas sus respuestas de error bajo el tipo de contenido `application/problem+json`:
- **`SpecError`**: Mapea excepciones de dominio de la plataforma a la estructura `ProblemDetail` con campos `type`, `title`, `status`, `detail`, `instance`, `trace_id` y lista de `violations`.
- **`StarletteHTTPException`**: Genera un documento RFC 7807 con URN `urn:kosmo:error:{status_code}`, preservando encabezados especiales (como `WWW-Authenticate` o `Retry-After`).
- **`RequestValidationError`**: Captura errores de validación de esquemas Pydantic devolviendo HTTP 422 con URN `urn:kosmo:validation:error` y sanitización segura del campo `input` para evitar excepciones de serialización JSON con objetos arbitrarios.

---

## Composición Hexagonal de Dependencias (`composition/`)

El subdirectorio `composition/` constituye la raíz de inyección de dependencias de la aplicación. Ensambla adaptadores de infraestructura y servicios de aplicación para construir el objeto inmutable `AppContainer`.

```
[FastAPI Request] ──> [get_container(request)] ──> [AppContainer]
                                                          │
          ┌──────────────┬──────────────┬─────────────────┼────────────────┬──────────────┐
          ▼              ▼              ▼                 ▼                ▼              ▼
     [AuthComp]    [PipelineComp]  [CodegenComp]   [IntegrationsComp]   [SDD Comps]   [RepositoryRegistry]
     (JWT, Argon2, (KOSMOAgent,   (WorkspaceMgr,   (GitHubClient,       (Discovery,   (PostgreSQL UoW,
      Fernet,       Skills 25,     IsolatedOpenCode, RailwayClient,      Features,     20 Repositories,
      Redis Stores) Memory, LLM)   EventBroker)     DeploymentWorker)   EARS, Modelo) OutboxStore)
```

### 1. `AppContainer` (`composition/__init__.py`)
Estructura de datos (`@dataclass`) que centraliza el estado global de la aplicación:
- `settings`: Configuración tipada de la aplicación (`Settings`).
- `db_engine`: Motor asíncrono de SQLAlchemy (`AsyncEngine`).
- `session_factory`: Fábrica de sesiones asíncronas de base de datos (`async_sessionmaker`).
- `uow`: Instancia de `SqlAlchemyUnitOfWork` para transacciones atómicas.
- `repos`: Registro central de repositorios de persistencia (`RepositoryRegistry`).
- `redis`: Cliente asíncrono de Redis (`Redis | None`).
- `auth`: Componentes de autenticación (`AuthComponents | None`).
- `pipeline`: Componentes del pipeline SDD del agente (`PipelineComponents`).
- `codegen`: Componentes de generación de código frontend (`CodegenComponents`).
- `integrations`: Componentes de integración con servicios externos (`IntegrationsComponents`).
- `discovery`, `features`, `requirements`, `modelo`, `consistency`, `projects`: Componentes de casos de uso por fase SDD.
- Método `close()`: Cierre coordinado de pools de conexiones y clientes HTTP.

### 2. Módulos Constructores
- **`composition/auth.py`** (`build_auth_components`): Inicializa `JoseJwtIssuer`, `JoseJwtVerifier` (RS256), `RedisTokenRevocationStore`, `RedisAuthorizationCodeStore`, `RedisLoginAttemptStore`, `Argon2idPasswordHasher`, `FernetSecretCipher` y todos los casos de uso del bounded context de autenticación.
- **`composition/codegen.py`** (`build_codegen_components`, `build_code_runner`, `build_workspace_manager`): Construye el ejecutor de código (`RemoteCodeRunner` o `SubprocessCodeRunner`), el gestor local de workspaces (`LocalWorkspaceManager`), el cliente de OpenCode (`IsolatedOpenCodeClient` con contenedor efímero o `OpenCodeHttpClient`), el broker de eventos (`ImplementationEventBroker`) y los use cases de implementación y validación.
- **`composition/integrations.py`** (`build_integrations_components`): Instancia `GitHubHttpClient`, `RailwayHttpClient`, `LocalGitWorkspaceAdapter`, `EphemeralDockerCodeRunner`, casos de uso de sincronización y despliegue, y el worker de sondeo `DeploymentPollingWorker`.
- **`composition/pipeline.py`** (`build_pipeline_components`): Construye el cliente LLM (`DynamicUserLLMClient` con BYOK, o `PydanticAILLMClient`), el motor de embeddings (`OpenAIEmbedder` o `FastembedEmbedder`), los repositorios de memoria del agente (`SqlAlchemyAgentSessionStore`, `SqlAlchemyKnowledgePatternStore`), el `OutboxStore`, las 6 herramientas de conocimiento (`KnowledgeToolRegistry`), el orquestador `KOSMOAgent` y los casos de uso de chat conversacional y consistencia.
- **`composition/sdd.py`**: Construye de forma modular los casos de uso para `ProjectComponents`, `DiscoveryComponents`, `FeaturesComponents`, `RequirementsComponents`, `ModeloComponents` y `ConsistencyComponents`.

### 3. Registro de Skills (`composition/skill_registration.py`)
La función `build_skill_registry()` registra exactamente **25 skills** en el `SkillRegistry` del pipeline SDD:

| # | Nombre del Skill | Fase SDD | Clase Mode Asociada | Propósito Operativo |
|---|---|---|---|---|
| 1 | `discovery_generate` | DESCUBRIMIENTO | `DiscoveryMode` | Generación del documento de visión y descubrimiento inicial |
| 2 | `discovery_refine` | DESCUBRIMIENTO | `DiscoveryRefineMode` | Refinamiento quirúrgico del documento de descubrimiento |
| 3 | `features_generate` | CARACTERISTICAS | `FeaturesMode` | Derivación de características a partir del descubrimiento |
| 4 | `ears_generate` | REQUISITOS | `EARSMode` | Generación de requisitos en sintaxis EARS por característica |
| 5 | `requirements_refine` | REQUISITOS | `RequirementsRefineMode` | Refinamiento de requisitos EARS existentes |
| 6 | `modelo_generate` | MODELO | `ModeloMode` | Generación de diagramas de actividad PlantUML |
| 7 | `discovery_chat` | DESCUBRIMIENTO | `DiscoveryChatMode` | Chat conversacional a nivel de negocio |
| 8 | `features_chat` | CARACTERISTICAS | `FeaturesChatMode` | Chat conversacional a nivel de característica |
| 9 | `requirements_chat` | REQUISITOS | `RequirementsChatMode` | Chat conversacional a nivel de especificación de software |
| 10 | `consistency_evaluate` | DESCUBRIMIENTO | `ConsistencyEvaluationMode` | Evaluación downstream general de consistencia |
| 11 | `consistency_evaluate_upstream` | CARACTERISTICAS | `ConsistencyEvaluationMode` | Evaluación de características hacia descubrimiento (upstream) |
| 12 | `consistency_evaluate_requirements` | REQUISITOS | `ConsistencyEvaluationMode` | Evaluación de requisitos hacia su característica padre |
| 13 | `consistency_evaluate_requirements_upstream` | REQUISITOS | `ConsistencyEvaluationMode` | Evaluación de requisitos hacia descubrimiento (upstream) |
| 14 | `consistency_evaluate_features_downstream` | CARACTERISTICAS | `ConsistencyEvaluationMode` | Evaluación de características hacia requisitos EARS |
| 15 | `consistency_evaluate_features_model` | CARACTERISTICAS | `ConsistencyEvaluationMode` | Evaluación de características hacia diagramas UML |
| 16 | `consistency_evaluate_discovery_requirements` | DESCUBRIMIENTO | `ConsistencyEvaluationMode` | Evaluación de descubrimiento hacia requisitos EARS |
| 17 | `consistency_evaluate_discovery_model` | DESCUBRIMIENTO | `ConsistencyEvaluationMode` | Evaluación de descubrimiento hacia diagramas UML |
| 18 | `consistency_evaluate_discovery_features` | DESCUBRIMIENTO | `ConsistencyEvaluationMode` | Evaluación de descubrimiento hacia características |
| 19 | `consistency_evaluate_discovery_implementation` | DESCUBRIMIENTO | `ConsistencyEvaluationMode` | Evaluación de descubrimiento hacia implementaciones de código |
| 20 | `consistency_evaluate_features_implementation` | CARACTERISTICAS | `ConsistencyEvaluationMode` | Evaluación de características hacia implementaciones de código |
| 21 | `consistency_evaluate_requirements_implementation` | REQUISITOS | `ConsistencyEvaluationMode` | Evaluación de requisitos hacia implementaciones de código |
| 22 | `consistency_evaluate_requirements_model` | REQUISITOS | `ConsistencyEvaluationMode` | Evaluación de requisitos hacia diagramas de actividad UML |
| 23 | `consistency_evaluate_model_implementation` | MODELO | `ConsistencyEvaluationMode` | Evaluación de diagramas hacia implementaciones de código |
| 24 | `consistency_correct` | DESCUBRIMIENTO | `ConsistencyCorrectionMode` | Generación de corrección textual exacta de artefactos |
| 25 | `direct_modification` | DESCUBRIMIENTO | `DirectModificationMode` | Modificación directa de especificaciones sin fase de plan |

---

## Dependencias de Entrada (`dependencies/`)

Las dependencias inyectables de FastAPI garantizan la seguridad, integridad y acceso a servicios en los routers:

### 1. Autenticación y Autorización (`dependencies/auth.py`)
- **`get_principal(request, credentials)`**:
  - Extrae el token Bearer del encabezado `Authorization`.
  - En modo desarrollo sin autenticación (`settings.auth_disabled`), genera un principal simulado (`mock_user`) con scope universal `*`.
  - En modo productivo, valida la firma RS256, expiración y estado de revocación mediante `VerifyAccessToken`.
  - Establece la variable de contexto `current_user_id` con el subject del principal.
  - Traduce excepciones de dominio (`MissingTokenError`, `TokenExpiredError`, `TokenRevokedError`) a respuestas HTTP 401 con el encabezado `WWW-Authenticate` correspondiente.
- **`require_project_owner(container, project_id, principal)`**:
  - Mecanismo de defensa contra BOLA/IDOR (Broken Object Level Authorization).
  - Consulta el repositorio de proyectos y verifica que `project.owner_id == principal.subject`.
  - Si el proyecto no existe o pertenece a otro usuario, responde defensivamente con **HTTP 404 Not Found** para evitar enumeración de recursos privados.
- **`verify_project_owner(project_id, principal, request)`**:
  - Dependencia FastAPI reutilizable para routers que incluyen `{project_id}` en su ruta.
- **`verify_feature_owner(feature_id, principal, request)`**:
  - Valida la existencia de la característica, recupera su `project_id` y verifica la titularidad del proyecto asociado. Almacena `request.state.project_id`.
- **`require_scopes(*required)`**:
  - Fábrica de dependencias que valida que el principal contenga los scopes solicitados o cuente con el comodín de superadministrador `*`. Devuelve HTTP 403 Forbidden si los permisos son insuficientes.

### 2. Control de Tasa y Saturación (`dependencies/rate_limit.py`)
- **Resolución de IP Confiable**:
  - La función `_resolve_client_ip` inspecciona `request.client.host`.
  - Solo acepta la cabecera `X-Kosmo-Client-Ip` si la petición proviene de una dirección IP o subred CIDR verificada dentro de `settings.trusted_proxies` (por defecto `127.0.0.1,::1,testclient,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16`).
- **Filosofía Fail-Closed vs Fail-Open**:
  - En entornos `production`, `staging` o cuando `rate_limit_required=True`, cualquier indisponibilidad de Redis o fallo de evaluación genera inmediatamente **HTTP 503 Service Unavailable** (*fail-closed*). En desarrollo local se emite una advertencia sin bloquear la petición (*fail-open*).
- **`IpRateLimiter`**:
  - Ejecuta un script Lua atómico en Redis (`INCR` y `EXPIRE` en el primer incremento) bajo la clave `auth:ip_rate:{path}:{client_ip}` con ventana fija de 60 segundos y timeout de evaluación de 1.0s.
  - Al exceder el límite, consulta el TTL restante y responde HTTP 429 Too Many Requests con el encabezado `Retry-After`.
- **`ProjectGenerationRateLimiter`**:
  - Aplica cuotas horarias de generación de IA por proyecto (`gen:rate:{project_id}`) con ventana de 3600 segundos (por defecto 120 peticiones/hora según `settings.generation_rate_limit_per_hour`).
  - Resuelve automáticamente el `project_id` desde los parámetros de ruta `{project_id}` o resolviendo la característica asociada `{feature_id}`.

### 3. Contenedor y Casos de Uso (`dependencies/container.py`, `ai_config.py`, `integrations.py`)
- **`get_container(request)`**: Recupera la instancia tipada `AppContainer` desde `request.app.state.container`.
- **`ai_config.py`**: Provee `get_manage_ai_preferences_use_case` y `get_validate_ai_connection_use_case`, resolviendo el cifrador Fernet (`SecretCipher`) para manipulación segura de claves API de usuario.
- **`integrations.py`**: Provee instancias cableadas para linking de cuentas GitHub, sincronización de repositorios, ejecución efímera de pruebas y orquestación de despliegues en Railway.

---

## Streaming SSE y Broker de Implementación

### 1. Streaming Asíncrono (`async_generation.py`)
- **`with_heartbeat(source, interval=15.0, max_duration_seconds=1800.0)`**:
  - Envuelve un generador asíncrono ejecutando el consumo en una tarea asyncio dedicada (`producer`) comunicada mediante una cola (`asyncio.Queue`).
  - Garantiza que context managers y cancel scopes vinculados a tareas (HTTP/LLM) se mantengan en el mismo contexto de ejecución.
  - Emite periódicamente comentarios SSE de latido (`: ping\n\n`) cada 15 segundos si no hay eventos activos, evitando que balanceadores de carga o proxies reversos corten la conexión TCP por inactividad.
  - Finaliza forzosamente tras alcanzar la duración máxima de 30 minutos (1800s).
  - Gestiona la métrica de Prometheus `ACTIVE_SSE_CONNECTIONS` incrementando al conectar y decrementando al cerrar.
- **`sse_chat_response(...)`**:
  - Valida previamente que el contenido pertenezca a la fase SDD actual mediante `ValidatePhaseContextUseCase`.
  - Transmite eventos SSE estructurados: evento inicial `start` con `trace_id`, fragmentos intermedios `chunk` conforme el LLM genera texto, evento final `message` con modificaciones y sugerencias estructuradas, o eventos tipados `error` (incluyendo detección de credenciales inválidas `ai_auth_error`).
- **`sse_consistency_response(...)`**: Transmite en vivo el progreso y los resultados de evaluaciones de consistencia en cascada.

### 2. Broker de Implementación (`implementation_broker.py`)
Desacopla la generación de código frontend (que puede demorar varios minutos ejecutando OpenCode, linters y suites de test) de la conexión HTTP del usuario:
- **Modo Dual**:
  - **En Memoria (`is_distributed=False`)**: Mantiene colas `asyncio.Queue` locales y un búfer circular de historial (`_history`) indexado por `implementation_id`.
  - **Distribuido (`is_distributed=True`)**: Emplea **Redis Streams** cuando `settings.redis_url` está configurado.
- **Operaciones en Redis Streams**:
  - Emisión de eventos mediante `XADD kosmo:impl:{id}:events` con recorte aproximado `maxlen=1000` y TTL configurable (por defecto 1800s).
  - Suscripción mediante `XREAD` bloqueante (`block=1000`, `count=50`) desde el identificador `0-0` para replay completo de eventos si el cliente se reconecta.
  - Marcador de terminación: Publica un evento especial `{"_done": "true"}` para señalar el fin ordenado del stream.
  - Latido de Tarea Activa: La tarea de fondo actualiza la clave `kosmo:impl:{id}:active` con expiración de 90 segundos cada 20 segundos.
  - Detección de Procesos Huérfanos: Si una suscripción no recibe eventos durante 60 segundos (`_ORPHAN_IDLE_TIMEOUT_SECONDS`) y la clave de actividad en Redis ya no existe, el stream concluye automáticamente.
- **Cancelación y Purga**: Al iniciar una nueva ejecución para la misma implementación, cancela tareas previas y programa la purga del historial en memoria tras cumplirse el TTL.

---

## Catálogo de Routers HTTP

A continuación se detalla la totalidad de los 20 routers registrados en la aplicación:

| Router | Prefijo Base | Tag OpenAPI | Métodos y Rutas Principales | Descripción Operativa |
|---|---|---|---|---|
| `auth.py` | `/api/v1/auth` | `auth` | `POST /register`<br>`POST /authorize`<br>`POST /token`<br>`POST /refresh`<br>`POST /logout`<br>`GET /me` | Autenticación OAuth 2.0 + PKCE (RFC 7636), rotación de refresh tokens y perfil del usuario autenticado. |
| `ai_config.py` | `/api/v1/ai-config` | `ai-config` | `GET /`<br>`PUT /`<br>`DELETE /`<br>`POST /test` | Configuración BYOK de modelos de IA (OpenAI, Anthropic, Gemini, DeepSeek) con cifrado Fernet y prueba de conectividad. |
| `projects.py` | `/api/v1/projects` | `projects` | `GET /`<br>`POST /`<br>`GET /{project_id}`<br>`DELETE /{project_id}` | Operaciones CRUD sobre proyectos de software del usuario autenticado. |
| `discovery.py` | `/api/v1/projects/{project_id}/discovery` | `discovery` | `GET /`<br>`POST /generate`<br>`POST /refine`<br>`PUT /`<br>`GET /history` | Generación de visión de producto en 8 secciones de negocio, refinamiento quirúrgico y guardado. |
| `features.py` | `/api/v1/projects/{project_id}/features` | `features` | `GET /`<br>`POST /generate`<br>`POST /save-selected`<br>`POST /suggest`<br>`POST /`<br>`PUT /{feature_id}`<br>`DELETE /{feature_id}`<br>`GET /{feature_id}/consistency` | Generación de características funcionales, sugerencias no redundantes, CRUD y chequeo de consistencia. |
| `feature_chat.py` | `/api/v1/projects/{project_id}/features/{feature_id}/chat` | `features` | `POST /messages`<br>`GET /history` | Chat conversacional interactivo con streaming SSE a nivel de característica individual. |
| `requirements.py` | `/api/v1/projects/{project_id}/features/{feature_id}/requirements` | `requirements` | `GET /`<br>`POST /generate`<br>`PUT /`<br>`POST /refine`<br>`POST /regenerate`<br>`DELETE /` | Generación, refinamiento y actualización de requisitos en sintaxis EARS por característica. |
| `requirement_chat.py` | `/api/v1/projects/{project_id}/features/{feature_id}/requirements/chat` | `requirements` | `POST /messages`<br>`GET /history` | Chat conversacional interactivo con streaming SSE a nivel de requisitos de software. |
| `chat_sessions.py` | `/api/v1/projects/{project_id}/chat/sessions` | `chat` | `GET /`<br>`POST /`<br>`DELETE /{session_id}` | Gestión de múltiples hilos o sesiones independientes de conversación por fase. |
| `modelo.py` | `/api/v1/projects/{project_id}/features/{feature_id}/modelo` | `modelo` | `GET /`<br>`POST /generate`<br>`DELETE /` | Generación y consulta de diagramas de actividad PlantUML derivados de los requisitos EARS. |
| `documents.py` | `/api/v1/projects/{project_id}/documents` | `documents` | `POST /modify` | Modificación textual directa sobre documentos de especificación sin pasar por generación completa. |
| `consistency.py` | `/api/v1/projects/{project_id}/consistency` | `consistency` | `POST /evaluate`<br>`GET /status`<br>`GET /review`<br>`POST /apply`<br>`POST /discard`<br>`POST /bulk-resolve`<br>`GET /activity` | Detección en cascada de impactos downstream, revisión interactiva de diffs y resolución atómica. |
| `implementations.py` | `/api/v1/projects/{project_id}/features/{feature_id}/implementation` | `codegen` | `POST /start`<br>`GET /stream`<br>`GET /record`<br>`DELETE /` | Orquestación asíncrona de generación de código frontend, streaming SSE del progreso y rollback. |
| `traceability.py` | `/api/v1/projects/{project_id}/traceability` | `traceability` | `GET /graph`<br>`GET /impact/{artifact_id}` | Consulta del grafo acíclico de trazabilidad end-to-end y análisis de dependencias de impacto. |
| `knowledge.py` | `/api/v1/projects/{project_id}/knowledge` | `knowledge` | `GET /patterns`<br>`POST /consolidate` | Inspección de patrones heurísticos extraídos por el agente y activación manual de consolidación. |
| `integrations.py` | `/api/v1/integrations` | `integrations` | `GET /status`<br>`POST /railway/link`<br>`DELETE /railway/unlink`<br>`GET /railway/status` | Estado consolidado de integraciones de usuario y vinculación de tokens para la plataforma Railway. |
| `github.py` | `/api/v1/integrations/github` | `integrations` | `GET /authorize`<br>`POST /callback`<br>`GET /status`<br>`DELETE /unlink`<br>`GET /repositories`<br>`POST /projects/{project_id}/link`<br>`GET /projects/{project_id}`<br>`POST /projects/{project_id}/sync`<br>`DELETE /projects/{project_id}/unlink` | Flujo OAuth con GitHub, vinculación de repositorios remotos por proyecto y sincronización de código vía Git. |
| `deployment.py` | `/api/v1/projects/{project_id}/deployment` | `deployment` | `POST /deploy`<br>`GET /status`<br>`DELETE /`<br>`GET /logs` | Despliegue en la nube de la aplicación generada en Railway, consulta de estado y cancelación. |
| `schemas.py` | `/api/v1/schemas` | `schemas` | `GET /`<br>`GET /{schema_name}` | Introspección y exportación de esquemas JSON Schema de todos los DTOs de contrato para el frontend. |
| `mcp.py` | `/mcp` | `MCP Tools` | `POST /tools/get_requirements`<br>`POST /tools/get_activity_diagram` | Endpoints de herramientas bajo el protocolo MCP para consulta contextual de especificaciones por OpenCode. |

---

## Constantes y Valores Clave

| Parámetro / Constante | Valor por Defecto | Archivo de Definición | Propósito Operativo |
|---|---|---|---|
| `_HEARTBEAT_INTERVAL` | `15.0 s` | `async_generation.py` | Intervalo entre latidos ping en conexiones SSE activas |
| `_HEARTBEAT_COMMENT` | `": ping\n\n"` | `async_generation.py` | Formato del comentario SSE de latido |
| `max_duration_seconds` | `1800.0 s` (30 min) | `async_generation.py` | Duración máxima de vida para un stream SSE continuo |
| `_REDIS_EVAL_TIMEOUT_SECONDS` | `1.0 s` | `dependencies/rate_limit.py` | Tiempo límite estricto para ejecución de scripts Lua en Redis |
| `_DEFAULT_TRUSTED_PROXIES` | `127.0.0.1, ::1, testclient, 10/8, 172.16/12, 192.168/16` | `dependencies/rate_limit.py` | Subredes autorizadas para enviar la cabecera `x-kosmo-client-ip` |
| Rate Limit Registro Auth | `3 peticiones / min` por IP | `routers/auth.py` | Protección contra creación automatizada de cuentas |
| Rate Limit Autorización Auth | `60 peticiones / min` por IP | `routers/auth.py` | Protección del endpoint de inicio de flujo PKCE |
| Rate Limit Generación IA | `120 peticiones / hora` por proyecto | `dependencies/rate_limit.py` | Cuota máxima de invocaciones LLM para prevenir abuso de costes |
| Stream Redis `maxlen` | `1000` eventos | `implementation_broker.py` | Límite máximo de retención de eventos por implementación |
| Broker Heartbeat TTL | `90 s` (renovado cada `20 s`) | `implementation_broker.py` | Vigencia de la clave de actividad de una tarea de generación |
| Broker Orphan Timeout | `60.0 s` | `implementation_broker.py` | Tiempo de espera antes de cerrar un stream sin tarea emisora |
| Total Skills Registrados | `25` | `composition/skill_registration.py` | Total de skills registrados en `SkillRegistry` |
| Total Routers Registrados | `20` | `main.py` | Total de módulos router incluidos en la aplicación |

---

## Reglas de Implementación y Mantenimiento

1. **Aislamiento Estricto de Routers**: Los routers no deben contener lógica de negocio, cálculos de dominio ni consultas directas a la base de datos. Su función exclusiva es deserializar peticiones, invocar el caso de uso correspondiente desde `container` y mapear los resultados a los esquemas de respuesta tipados.
2. **Uso Exclusivo de `get_container`**: No se deben instanciar use cases, repositorios o adaptadores directamente en los routers. Todo componente debe obtenerse desde `AppContainer` a través de `get_container(request)` o de las dependencias de `dependencies/`.
3. **Respeto de la Cascada Unidireccional Downstream**: Toda operación que altere un artefacto de una fase superior (`DESCUBRIMIENTO` o `CARACTERISTICAS`) debe encolar la evaluación de consistencia downstream correspondiente en el Outbox (`consistency_evaluate`), sin saltar fases ni propagar en sentido inverso de forma no autorizada.
4. **Conservación de la Política Fail-Closed**: En `dependencies/rate_limit.py`, la política de *fail-closed* bajo entornos no-desarrollo es innegociable. No relajar los guards de captura de excepciones en producción.
5. **Preservación de Respuestas RFC 7807**: Todo nuevo error HTTP o validación debe estructurarse mediante `ProblemDetail` o `SpecError`, asegurando que el cliente reciba siempre `application/problem+json` con su respectivo `trace_id`.
6. **Mantenimiento de Schemas en `schemas.py`**: Todo nuevo endpoint debe definir sus modelos de solicitud y respuesta en `schemas.py` con tipado estricto de Pydantic v2, `extra="forbid"` donde aplique y descripciones informativas para la documentación OpenAPI.

---

## Directrices de Seguridad

- **Mitigación de IDOR / BOLA**: Cualquier endpoint que manipule recursos anidados bajo `{project_id}` o `{feature_id}` debe incluir obligatoriamente `verify_project_owner` o `verify_feature_owner` en sus dependencias. Si el usuario no es el propietario, la API devuelve HTTP 404 para no revelar la existencia de recursos ajenos.
- **Protección de Credenciales BYOK**: Las claves API de inteligencia artificial suministradas por el usuario nunca se devuelven en claro a través de la API; se enmascaran mostrando únicamente sus últimos 4 caracteres mediante la utilidad de dominio.
- **Inyección de Cabeceras Defensivas**: `SecurityHeadersMiddleware` aplica políticas estrictas contra clickjacking (`X-Frame-Options: DENY`), sniffing MIME (`X-Content-Type-Options: nosniff`) y aislamiento de iframe mediante CSP.
- **Validación de Proxies Reversos**: La cabecera `x-kosmo-client-ip` jamás debe aceptarse a ciegas. Si la petición no se origina desde un host verificado en `_DEFAULT_TRUSTED_PROXIES` o `settings.trusted_proxies`, se ignora y se toma la IP directa de la conexión TCP.
- **Sanitización de Errores de Validación**: En `validation_exception_handler`, los valores de entrada inválidos se validan y serializan defensivamente para evitar que cargas maliciosas no serializables generen excepciones no controladas durante la respuesta.
