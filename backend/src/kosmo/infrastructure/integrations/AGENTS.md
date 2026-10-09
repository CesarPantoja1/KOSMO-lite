# `infrastructure/integrations/` — GitHub, Railway y Deployment Polling Worker

## Responsabilidad y Propósito

Este módulo implementa los adaptadores de infraestructura para la interacción con servicios externos de control de versiones y despliegue en la nube dentro del ecosistema KOSMO:

- **Integración con GitHub (`GitHubHttpClient`)**: Cliente HTTP sobre la API REST oficial de GitHub (`v2022-11-28`) que gestiona el ciclo de vida completo de repositorios remotos, intercambio OAuth con soporte PKCE, validación de existencia, obtención de perfiles de usuario y autorización automática de acceso para la GitHub App de Railway sobre repositorios seleccionados.
- **Integración con Railway (`RailwayHttpClient`)**: Cliente HTTP híbrido que prioriza la API GraphQL oficial de Railway (`/graphql/v2` con fallback a `/graphql`) y mantiene una ruta de degradación REST (`/v1/...`) para pruebas unitarias. Administra el aprovisionamiento de proyectos, entornos, servicios vinculados a repositorios de GitHub, generación de dominios públicos, inyección de variables de entorno, configuración de volúmenes persistentes y sondeo de estados de compilación/despliegue.
- **Worker de Monitoreo en Segundo Plano (`DeploymentPollingWorker`)**: Orquestador asíncrono no bloqueante basado en `asyncio.Task` que sondea periódicamente el estado de despliegues en curso, evita tareas duplicadas por proyecto mediante deduplicación en memoria, gestiona la recolección automática de tareas finalizadas (*done callbacks*), reporta fallos a la base de datos a través de `HandleDeploymentFailureUseCase` y asegura un apagado ordenado (*graceful shutdown*).

---

## Estructura de Archivos y Componentes

```
infrastructure/integrations/
├── __init__.py                 # Reexporta DeploymentPollingWorker, GitHubHttpClient, RailwayHttpClient
├── deployment_worker.py        # Worker en background para polling asíncrono de despliegues
├── github_client.py            # Adaptador HTTP GitHub REST API (v2022-11-28, OAuth, App access)
└── railway_client.py           # Adaptador HTTP Railway (GraphQL v2 + REST fallback, multi-resource)
```

---

## Integración con GitHub (`GitHubHttpClient`)

Implementado en [github_client.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/integrations/github_client.py).

### Configuración HTTP y Cabeceras
- **URL Base por defecto**: `https://api.github.com`
- **URL OAuth por defecto**: `https://github.com/login/oauth/access_token`
- **Cabeceras obligatorias**:
  ```http
  Accept: application/vnd.github+json
  X-GitHub-Api-Version: 2022-11-28
  User-Agent: KOSMO-App
  Authorization: Bearer <token>
  ```
- **Timeouts**: `15.0s` totales con `10.0s` para conexión.

### Mapeo de Excepciones HTTP a Dominio
`_handle_response_error` traduce los códigos de estado HTTP de GitHub a la jerarquía tipada definida en `contracts/integrations/github.py`:
- `401 Unauthorized` → `GitHubAuthenticationError` ("Token de acceso de GitHub inválido o expirado...").
- `403 Forbidden`:
  - Si `x-ratelimit-remaining == "0"` o el cuerpo contiene `"rate limit"` / `"secondary rate limit"` → `GitHubRateLimitError`.
  - En cualquier otro caso de permisos → `GitHubPermissionError`.
- `404 Not Found` → `GitHubResourceNotFoundError`.
- `422 Unprocessable Entity`: En `create_repository`, si el mensaje contiene `"already exists"`, lanza `GitHubRepositoryAlreadyExistsError`.
- Otros errores / no-success → `GitHubApiError`.
- `httpx.TimeoutException` / `httpx.RequestError` → `GitHubApiError`.

### Métodos del Cliente
1. **`get_authenticated_user(token: str) -> GitHubUser`**:
   - `GET /user`.
   - Retorna la entidad de dominio `GitHubUser(login, id, name, email, avatar_url, html_url)`.
2. **`check_repository_exists(token: str, owner: str, repo_name: str) -> bool`**:
   - `GET /repos/{owner}/{repo_name}`.
   - Retorna `True` si el status es `200`, `False` si es `404`.
3. **`get_repository(token: str, owner: str, repo_name: str) -> GitHubRepository | None`**:
   - `GET /repos/{owner}/{repo_name}`.
   - Retorna `None` si status es `404` o la entidad `GitHubRepository(id, name, full_name, owner, html_url, clone_url, is_private, default_branch, description)`.
4. **`create_repository(token: str, name: str, description="", is_private=False, auto_init=False) -> GitHubRepository`**:
   - `POST /user/repos`.
   - Intercepta status `422` para detectar colisión de nombre y lanzar `GitHubRepositoryAlreadyExistsError`.
5. **`exchange_oauth_code(client_id, client_secret, code, redirect_uri=None, code_verifier=None) -> GitHubOAuthToken`**:
   - `POST https://github.com/login/oauth/access_token` con cabecera `Accept: application/json`.
   - Soporta PKCE mediante `code_verifier`.
   - Valida que la respuesta no contenga el campo `"error"`, retornando `GitHubOAuthToken(access_token, token_type, scope)`.
6. **`delete_repository(token: str, owner: str, repo_name: str) -> bool`**:
   - `DELETE /repos/{owner}/{repo_name}`.
   - Retorna `True` ante `200` o `204`, `False` ante `404`.
7. **`grant_app_installation_access(token: str, repo_id: int, app_slug: str = "railway") -> bool`**:
   - Consulta `GET /user/installations`.
   - Localiza la instalación correspondiente a `app_slug` (por defecto `"railway"`).
   - Si `repository_selection == "all"`, retorna `True` inmediatamente (acceso global preexistente).
   - Si `repository_selection == "selected"`, emite `PUT /user/installations/{inst_id}/repositories/{repo_id}` para vincular el repositorio recién creado a los permisos de Railway sin requerir intervención manual del usuario en GitHub.

---

## Integración con Railway (`RailwayHttpClient`)

Implementado en [railway_client.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/integrations/railway_client.py).

### Arquitectura Dual: GraphQL Primario + Fallback REST
Railway no expone una API REST pública completa para todas las operaciones de aprovisionamiento; su interfaz principal es una API GraphQL alojada en `https://backboard.railway.com/graphql/v2` (con fallback a `/graphql`).

`RailwayHttpClient` implementa una estrategia de dos niveles:
1. **Nivel GraphQL (Producción)**: Ejecuta consultas y mutaciones estructuradas contra el endpoint GraphQL oficial.
2. **Nivel REST (Degradación y Tests)**: Si el endpoint GraphQL responde `404` (como ocurre en entornos de testing con `MockTransport` REST), degrada automáticamente a endpoints REST bajo `/v1/...`.

### Mapeo de Excepciones HTTP y GraphQL a Dominio
- **Errores HTTP de transporte**:
  - `401 Unauthorized` → `DeploymentAuthenticationError` ("Token de acceso de Railway inválido o expirado...").
  - `403 Forbidden` → `DeploymentRateLimitError` (si agotó cuota) o `DeploymentPermissionError`.
  - `404 Not Found` → `DeploymentResourceNotFoundError`.
  - `400 / 422` → `DeploymentConfigurationError`.
  - Otros → `DeploymentApiError`.
- **Errores en el payload GraphQL (`errors: [...]`)**:
  - Analiza el campo `message` del primer error.
  - Si contiene `"not authorized"` / `"unauthorized"` → `DeploymentAuthenticationError` (con instrucciones sobre el panel de Railway o plan Trial).
  - Si contiene `"not found or is not accessible"` / `"forbidden"` / `"permission"` → `DeploymentPermissionError` (con advertencias sobre repositorios privados o GitHub App de Railway).
  - Otros errores GraphQL → `DeploymentApiError`.

### Métodos del Cliente
1. **`exchange_oauth_code(code: str, redirect_uri=None, code_verifier=None) -> DeploymentOAuthToken`**:
   - **Bypass de Tokens Directos**: Si `code` inicia con `rly_` o `railway_` (tokens personales de Railway), omite la petición HTTP y genera directamente un `DeploymentOAuthToken(access_token=cleaned_code, token_type="bearer")`.
   - **Flujo OAuth Estándar**: `POST /oauth/token` con `grant_type="authorization_code"`.
2. **`get_authenticated_user(token: str) -> dict[str, str]`**:
   - `GET /oauth/me` (endpoint OIDC userinfo).
   - Retorna `{"sub": ..., "name": ..., "email": ...}`.
   - `401` propaga `DeploymentAuthenticationError`; otros errores registran warning y retornan `{}` (no bloqueante).
3. **`refresh_access_token(refresh_token: str) -> DeploymentOAuthToken`**:
   - `POST /oauth/token` con `grant_type="refresh_token"`.
   - Retorna el nuevo par de tokens con su respectivo `expires_in`.
4. **`create_service(token, repo_url, env_vars, ports, service_name=None) -> str`**:
   - Ejecuta una cascada de aprovisionamiento en GraphQL:
     1. **`query GetUserContext`**: Consulta `me { workspaces { projects { ... } } }`. Si ya existe un proyecto cuyo nombre coincide con `repo_name`, reutiliza el `projectId`, `baseEnvironmentId` y `serviceId` existentes.
     2. **`mutation ProjectCreate`**: Si no existe el proyecto, lo crea asociándolo al `workspaceId` del usuario.
     3. **`query ProjectEnvironments`**: Recupera el entorno base (`production`).
     4. **`mutation ServiceCreate`**: Crea el servicio vinculándolo al repositorio GitHub: `source: {repo: repo_slug}`.
     5. **`mutation ServiceDomainCreate`**: Genera un dominio público `.up.railway.app` para el entorno.
     6. **`mutation VariableCollectionUpsert`**: Inyecta en bloque las variables de entorno configuradas (`EnvironmentVariable`).
     7. Retorna el `service_id: str` creado o reutilizado.
   - **Ruta REST**: `POST /v1/services` con `{repo_url, env_vars, ports}`.
5. **`configure_volume(token: str, service_id: str, volume: VolumeConfig) -> None`**:
   - Obtiene el `projectId` del servicio vía `query GetServiceProject`.
   - Ejecuta `mutation VolumeCreate(input: {projectId, serviceId, mountPath})`.
   - Fallback REST: `POST /v1/services/{service_id}/volumes`.
6. **`trigger_deployment(token: str, service_id: str, commit_sha=None) -> None`**:
   - Consulta el `environmentId` del servicio en `serviceInstances`.
   - Ejecuta `mutation ServiceInstanceDeployV2` (o fallback a `serviceInstanceDeploy`).
   - **Idempotencia defensiva**: Si Railway responde que ya hay un build en progreso o iniciado automáticamente por el webhook de GitHub, captura el mensaje, registra un log informativo y retorna exitosamente sin error.
   - Fallback REST: `POST /v1/services/{service_id}/deploy`.
7. **`get_service_status(token: str, service_id: str) -> tuple[DeploymentStatus, str | None, str | None]`**:
   - Consulta `query ServiceStatus` y `query DeploymentStatus(first: 1)`.
   - **Mapeo de estados de Railway a `DeploymentStatus`**:
     - `SUCCESS`, `DEPLOYED`, `LIVE`, `ACTIVE`, `PUBLISHED` → `DeploymentStatus.PUBLISHED`
     - `BUILDING`, `PENDING`, `INITIALIZING`, `DEPLOYING`, `WAITING`, `QUEUED` → `DeploymentStatus.BUILDING`
     - `FAILED`, `CRASHED`, `CANCELLED`, `ERROR` → `DeploymentStatus.FAILED`
     - Cualquier otro o vacío → `DeploymentStatus.NOT_CREATED`
   - **Resolución de URL Pública**: Evalúa `staticUrl` (`https://{staticUrl}`), `url` o dominios asociados al servicio (`serviceDomains`).
   - **Resolución de URL de Logs de Build**: Si el estado es `FAILED`, construye el enlace canónico al panel de Railway: `https://railway.com/project/{project_id}/service/{service_id}?id={deployment_id}`.
   - Retorna `(status, public_url, build_logs_url)`.
8. **`delete_service(token: str, service_id: str) -> bool`**:
   - Obtiene el `projectId` del servicio.
   - Intenta eliminar el proyecto completo mediante `mutation ProjectDelete(id: projectId)`.
   - Si no es posible, elimina solo el servicio con `mutation ServiceDelete(id: service_id)`.
   - Fallback REST: `DELETE /v1/services/{service_id}`.

---

## Worker de Monitoreo en Segundo Plano (`DeploymentPollingWorker`)

Implementado en [deployment_worker.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/integrations/deployment_worker.py).

Implementa `DeploymentWorkerPort` (de `contracts/integrations/deployment.py`).

### Ciclo de Vida y Concurrencia
- **Mapa de Tareas Activas**: `_active_tasks: dict[str, asyncio.Task[None]]` indexado por `str(project_id)`.
- **Deduplicación Estricta**: Antes de crear una tarea, verifica si ya existe una tarea activa para ese `project_id` que no haya terminado (`not existing.done()`). Si existe, la reutiliza evitando peticiones duplicadas y desperdicio de sockets.
- **Creación de Tarea Asíncrona**:
  - Nombre canónico: `deploy_monitor_{project_id}`.
  - Ejecuta `MonitorDeploymentStatusUseCase.execute(...)` con los parámetros:
    - `max_attempts`: `60` intentos por defecto.
    - `delay_seconds`: `10` segundos entre sondeos.
    - Tiempo máximo de cobertura: `10` minutos (`60 * 10s`).
- **Manejo de Excepciones y Resiliencia**:
  - `asyncio.CancelledError`: Logea la cancelación y la relanza limpiamente para permitir el shutdown.
  - `Exception` genérica: Si ocurre un fallo inesperado no controlado durante el sondeo, invoca `HandleDeploymentFailureUseCase` pasando `HandleDeploymentFailureCommand(project_id, error_message, provider)` para persistir el estado `FAILED` en base de datos.
- **Autolimpieza (*Done Callback*)**:
  - Registra `task.add_done_callback(lambda _: self._active_tasks.pop(project_id_str, None))` para que la tarea se desregistre automáticamente de la memoria en cuanto finaliza (éxito, error o cancelación).
- **Inspección y Cancelación Manual**:
  - `is_monitoring(project_id) -> bool`: Comprueba si hay sondeo en curso.
  - `cancel_monitoring(project_id) -> bool`: Cancela la tarea activa si existe.
- **Apagado Ordenado (`shutdown`)**:
  - Invocado durante el evento de shutdown del lifespan de FastAPI.
  - Cancela todas las tareas activas y espera su conclusión limpia mediante `asyncio.gather(*tasks, return_exceptions=True)`.

---

## Contratos Implementados (Puertos vs Implementaciones)

| Puerto / Interfaz (`contracts/`) | Clase Concreta de Infraestructura | Archivo de Implementación |
|:---|:---|:---|
| `GitHubClientPort` | `GitHubHttpClient` | [github_client.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/integrations/github_client.py) |
| `DeploymentProviderPort` | `RailwayHttpClient` | [railway_client.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/integrations/railway_client.py) |
| `DeploymentWorkerPort` | `DeploymentPollingWorker` | [deployment_worker.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/integrations/deployment_worker.py) |

---

## Constantes y Parámetros Operativos

| Constante | Valor | Ubicación | Significado Técnico |
|:---|:---|:---|:---|
| `_DEFAULT_API_VERSION` | `2022-11-28` | `github_client.py` | Versión requerida en cabecera `X-GitHub-Api-Version` |
| `_DEFAULT_USER_AGENT` | `KOSMO-App` | `github_client.py`, `railway_client.py` | User-Agent enviado en peticiones salientes |
| Timeout HTTP GitHub | `15.0s` (connect `10.0s`) | `github_client.py` | Timeout de peticiones hacia la API REST de GitHub |
| Timeout HTTP Railway | `15.0s` (connect `10.0s`) | `railway_client.py` | Timeout de peticiones hacia la API GraphQL/REST de Railway |
| `max_attempts` Polling | `60` | `deployment_worker.py` | Intentos máximos de sondeo de despliegue |
| `delay_seconds` Polling | `10` s | `deployment_worker.py` | Intervalo en segundos entre cada sondeo de despliegue |
| Duración máxima Polling | `600` s (10 min) | `deployment_worker.py` | Ventana total de monitoreo antes de timeout de sondeo |

---

## Reglas de Implementación y Mantenimiento

1. **Traducción Obligatoria de Excepciones**: Ningún método de `GitHubHttpClient` ni de `RailwayHttpClient` debe propagar excepciones crudas de `httpx` (`HTTPStatusError`, `RequestError`, `TimeoutException`) hacia los use cases. Siempre deben traducirse a la jerarquía tipada de `contracts/integrations/`.
2. **Prioridad GraphQL en Railway**: Las mutaciones de aprovisionamiento en Railway deben implementarse prioritariamente en GraphQL. La ruta REST solo debe mantenerse como fallback para compatibilidad con suites de test unitario.
3. **Manejo de Paginación Relay**: Las respuestas GraphQL de Railway utilizan paginación cursor-based estilo Relay (`{ edges: [{ node: { ... } }] }`). Utilizar siempre la función utilitaria `_extract_first_edge_node` para navegar nodos de forma segura sin riesgo de `KeyError` ni `IndexError`.
4. **Deduplicación en el Worker**: Nunca omitir la comprobación `if existing and not existing.done()` en `DeploymentPollingWorker.start_monitoring`. Generar múltiples bucles de sondeo para un mismo proyecto causa sobreconsumo de cuota y carreras transaccionales en base de datos.
5. **Idempotencia de Despliegue en Railway**: Si Railway inicia automáticamente la compilación por webhook tras `create_service`, la invocación de `trigger_deployment` debe aceptar y silenciar errores del tipo `"already in progress"`.

---

## Directrices de Seguridad

- **Tokens OAuth Descifrados Efímeros**: Los tokens de acceso y refresh (`access_token_enc`, `refresh_token_enc`) se almacenan en reposo cifrados con Fernet en PostgreSQL. La capa de integraciones los recibe descifrados exclusivamente como argumentos de función en memoria y nunca los persiste ni los expone en logs.
- **Enmascaramiento de Credenciales en Logs**: Si ocurre un error de red o timeout, los mensajes de excepción y los logs no deben volcar las cabeceras `Authorization` ni los tokens de acceso.
- **Permisos Mínimos en GitHub**: `grant_app_installation_access` solo concede acceso al repositorio específico (`repo_id`) mediante la API de GitHub Apps, sin elevar permisos sobre el resto de repositorios de la cuenta del usuario.
