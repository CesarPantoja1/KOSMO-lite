# `infrastructure/persistence/` — Persistencia PostgreSQL, Redis y Transactional Outbox

## Responsabilidad y Propósito

Este módulo implementa la capa de persistencia completa de KOSMO dentro de la arquitectura hexagonal. Traduce los puertos abstractos de datos definidos en `contracts/` a adaptadores concretos contra PostgreSQL (vía SQLAlchemy 2.0 y pgvector) y Redis (vía redis-py async):

- **Modelos ORM (22 tablas PostgreSQL)**: Mapeo declarativo estricto con tipado estricto `Mapped[...]` de SQLAlchemy 2.0, tipos nativos PostgreSQL (`CITEXT`, `JSONB`, `INET`, `Vector`), claves foráneas con cascada y restricciones de unicidad.
- **21 adaptadores de persistencia**: Repositorios, stores y sinks distribuidos en 16 archivos en `postgres/repositories/` que implementan los contratos de acceso a datos para proyectos, especificaciones SDD, chat, memoria de agentes, trazabilidad, configuración de IA, integraciones externas (GitHub, Railway), workspaces y usuarios.
- **Unit of Work (`SqlAlchemyUnitOfWork`)**: Gestor de transacciones atómicas multi-repositorio que comparte una única `AsyncSession` entre repositorios *bound*, con aislamiento por corrutina mediante una pila en `ContextVar` para soportar contextos anidados de forma segura.
- **Transactional Outbox (`OutboxStore` y `run_outbox_worker`)**: Procesamiento asíncrono garantizado de efectos secundarios (side-effects) con lectura concurrente segura vía `SELECT ... FOR UPDATE SKIP LOCKED`, reintentos automáticos, backoff adaptativo y paso a dead-letter queue (`dead`) tras agotar intentos.
- **Registro de repositorios (`RepositoryRegistry`)**: Contenedor inmutable (`frozen=True`, `slots=True`) que centraliza e instancia los 19 repositorios SQL consumidos por el composition root para inyección de dependencias.
- **3 almacenes Redis para autenticación y seguridad**:
  - `RedisAuthorizationCodeStore`: Almacenamiento y consumo atómico de un solo uso (`SET NX` + pipeline `GET`+`DELETE`) para códigos PKCE RFC 7636.
  - `RedisLoginAttemptStore`: Control de tasa de intentos de autenticación en ventana deslizante de 15 minutos (900 s) con umbral de 10 fallos y retorno de tiempo restante para la cabecera HTTP `Retry-After`.
  - `RedisTokenRevocationStore`: Rotación de refresh tokens con período de gracia atómico (30 s), polling no bloqueante (50 ms x 30 intentos = 1.5 s máx), revocación en cadena de familias de tokens (*Token Families* RFC 6819) ante reuso malicioso y lista negra de tokens de acceso revocados.
- **Búsqueda vectorial semántica con pgvector**: Almacenamiento de embeddings (1536 dimensiones) y búsqueda de similitud k-NN mediante el operador de distancia coseno `<=>`.

---

## Estructura de Archivos y Componentes

```
infrastructure/persistence/
├── __init__.py                                 # Módulo de persistencia
├── postgres/
│   ├── models.py                               # 22 modelos ORM SQLAlchemy 2.0 (tablas PostgreSQL)
│   ├── uow.py                                  # SqlAlchemyUnitOfWork con pila ContextVar (_UowContext)
│   ├── outbox.py                               # OutboxStore y run_outbox_worker (SKIP LOCKED, backoff)
│   ├── registry.py                             # RepositoryRegistry (19 repositorios SQL instanciados)
│   └── repositories/
│       ├── __init__.py                         # Reexportación de 21 clases de repositorio/store/sink
│       ├── activity_diagram_repo.py            # SqlAlchemyActivityDiagramRepository
│       ├── agent_memory_repo.py                # SqlAlchemyAgentSessionStore, SqlAlchemyKnowledgePatternStore
│       ├── audit.py                            # SqlAlchemyAuditEventSink (auditoría best-effort)
│       ├── chat_repo.py                        # SqlAlchemyChatRepository (sesiones, mensajes, cursores)
│       ├── consistency_repo.py                 # SqlAlchemyConsistencyEvaluationRepository
│       ├── document_repo.py                    # SqlAlchemyDocumentRepository (Discovery AST, versiones)
│       ├── feature_implementation_repo.py      # SqlAlchemyFeatureImplementationRepository (planes, validación)
│       ├── feature_repo.py                     # SqlAlchemyFeatureRepository (features, numeración secuencial)
│       ├── project_integration_repo.py         # SqlAlchemyProjectGitHubIntegrationRepository,
│       │                                       # SqlAlchemyProjectDeploymentRepository,
│       │                                       # SqlAlchemyCodeSyncLogRepository
│       ├── project_repo.py                     # SqlAlchemyProjectRepository (CRUD, slug, propietario)
│       ├── requirement_repo.py                 # SqlAlchemyRequirementRepository (markdown EARS)
│       ├── traceability_repo.py                # SqlAlchemyTraceabilityRepository (grafo upstream/downstream)
│       ├── user_ai_config_repo.py              # SqlAlchemyUserAiConfigRepository (BYOK cifrado)
│       ├── user_integration_repo.py            # SqlAlchemyUserIntegrationRepository,
│       │                                       # SqlAlchemyUserGitHubIntegrationRepository,
│       │                                       # SqlAlchemyUserDeploymentIntegrationRepository
│       ├── users.py                            # SqlAlchemyUserRepository (usuarios, Argon2id, perfiles)
│       └── workspace_repo.py                   # SqlAlchemyWorkspaceRepository (CAS locking, stale timeout)
└── redis/
    ├── authorization_code_store.py             # RedisAuthorizationCodeStore (PKCE SET NX + consume atómico)
    ├── login_attempt_store.py                  # RedisLoginAttemptStore (rate limit login, ventana 900s)
    └── token_store.py                          # RedisTokenRevocationStore (rotación, grace period, RFC 6819)
```

---

## Catálogo Completo de Modelos ORM (22 Tablas PostgreSQL)

Todos los modelos heredan de `Base(DeclarativeBase)` en [postgres/models.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/models.py).

| Clase Modelo | Tabla PostgreSQL | Clave Primaria | Claves Foráneas (`ondelete`) | Restricciones / Índices Únicos | Columnas Clave y Tipos Notables |
|:---|:---|:---|:---|:---|:---|
| `UserModel` | `users` | `id` (String 64) | — | `email` CITEXT unique index | `email`, `name`, `avatar_url`, `hashed_password`, `disabled_at` |
| `AuditEventModel` | `audit_log` | `id` (String 64) | — | — | `event_type`, `outcome`, `actor_id`, `actor_email`, `ip_address` (INET), `user_agent`, `payload` (JSONB) |
| `ProjectModel` | `projects` | `id` (String 64) | — | Index `owner_id` | `name`, `slug`, `description`, `owner_id`, `current_phase`, `status` |
| `FeatureModel` | `features` | `id` (String 64) | `project_id` → `projects.id` (`CASCADE`) | Unique `(project_id, number)` | `number` (Int), `title`, `slug`, `description`, `origin` |
| `RequirementModel` | `requirements` | `feature_id` (String 64) | `feature_id` → `features.id` (`CASCADE`) | PK es FK | `markdown` (Text con especificación EARS completa) |
| `TraceabilityEdgeModel` | `traceability_edges` | `id` (String 64) | — | — | `source_type`, `source_id`, `target_type`, `target_id`, `origin` (`llm`/manual) |
| `DiscoveryDocumentModel` | `discovery` | `project_id` (String 64) | `project_id` → `projects.id` (`CASCADE`) | PK es FK | `markdown` (Text con las 7 secciones canónicas de Discovery) |
| `AgentSessionModel` | `agent_sessions` | `id` (String 64) | `project_id` → `projects.id` (`CASCADE`) | Index `project_id` | `session_type`, `phase`, `conversation` (JSONB), `reasoning_log` (JSONB), `embedding` (Vector 1536), `reflection` |
| `ActivityDiagramModel` | `activity_diagrams` | `id` (String 64) | `feature_id` → `features.id` (`CASCADE`) | Unique & Index `feature_id` | `diagram_syntax` (Text PlantUML con `@startuml`/`@enduml`) |
| `KnowledgePatternModel` | `knowledge_patterns` | `id` (String 64) | — | Unique `(phase, pattern_text)`, Index `phase` | `phase`, `pattern_text`, `support_count` (Int) |
| `ChatMessageModel` | `chat_messages` | `id` (String 64) | `project_id` → `projects.id` (`CASCADE`) | Index `project_id`, Index `session_id` | `phase`, `context_id`, `role`, `content`, `suggested_change` (JSONB), `error` |
| `ChatSessionModel` | `chat_sessions` | `id` (String 64) | `project_id` → `projects.id` (`CASCADE`) | Index `project_id` | `phase`, `context_id` |
| `DocumentVersionModel` | `document_versions` | `id` (String 64) | `project_id` → `projects.id` (`CASCADE`) | Index `project_id` | `phase`, `markdown`, `change_ids` (JSONB list) |
| `OutboxJobModel` | `outbox_jobs` | `id` (String 64) | — | Index `ix_outbox_pending` (`status`, `created_at`) | `job_type`, `payload` (JSONB), `status`, `attempts`, `last_error` |
| `ConsistencyEvaluationModel` | `consistency_evaluations` | `id` (String 64) | `project_id` → `projects.id` (`CASCADE`) | Unique `(project_id, source_phase, target_phase, target_artifact_id)` | `artifact_type`, `snapshot_hash` (SHA-256), `status`, `result` (JSONB), `source_changes` (JSONB), `operation_id` |
| `UserPreferenceModel` | `user_preferences` | `id` (String 64) | `user_id` → `users.id` (`CASCADE`) | Index `user_id` | `rule_text` (Regla operativa personalizada del usuario) |
| `WorkspaceModel` | `workspaces` | `id` (String 64) | `project_id` → `projects.id` (`CASCADE`) | Index `project_id` | `current_branch`, `is_locked` (Bool), `locked_at`, `locked_by`, `path` |
| `FeatureImplementationModel` | `feature_implementations` | `id` (String 64) | `feature_id` → `features.id` (`CASCADE`), `project_id` → `projects.id` (`CASCADE`) | Index `feature_id`, Index `project_id` | `status`, `plan` (JSONB), `last_validation` (JSONB), `attempt_count`, `generated_files` (JSONB), `retry_history` (JSONB) |
| `UserAiConfigModel` | `user_ai_configs` | `id` (String 64) | `user_id` → `users.id` (`CASCADE`) | Unique & Index `user_id` | `provider`, `model`, `encrypted_api_key` (Fernet ciphertext), `is_custom` |
| `UserIntegrationModel` | `user_integrations` | `id` (String 64) | `user_id` → `users.id` (`CASCADE`) | Unique `(user_id, provider)`, Index `user_id` | `provider`, `account_name`, `access_token_enc`, `refresh_token_enc`, `scopes` (JSONB) |
| `ProjectIntegrationModel` | `project_integrations` | `id` (String 64) | `project_id` → `projects.id` (`CASCADE`) | Unique `(project_id, provider)`, Index `project_id` | `repo_name`, `repo_url`, `sync_status`, `service_id`, `deploy_status`, `volumes` (JSONB), `ports` (JSONB), `env_vars` (JSONB) |
| `CodeSyncLogModel` | `code_sync_logs` | `id` (String 64) | `project_id` → `projects.id` (`CASCADE`) | Index `project_id` | `commit_sha`, `status`, `message`, `synced_at` |

---

## Unit of Work (`SqlAlchemyUnitOfWork`) y Manejo Transaccional

Implementado en [postgres/uow.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/uow.py).

### Arquitectura de Aislamiento
El UoW gestiona el ciclo de vida de una transacción compartida a través de múltiples repositorios bound. Para evitar condiciones de carrera entre tareas concurrentes y soportar anidamiento seguro sin acoplamiento, utiliza una tupla inmutable almacenada en un `ContextVar`:

```python
self._context_stack: ContextVar[tuple[_UowContext, ...]] = ContextVar(
    f"uow_stack_{id(self)}",
    default=(),
)
```

Cada nivel de anidamiento crea un `_UowContext` con su propia `AsyncSession` y repositorios asociados:
- `projects`: `SqlAlchemyProjectRepository`
- `documents`: `SqlAlchemyDocumentRepository`
- `features`: `SqlAlchemyFeatureRepository`
- `requirements`: `SqlAlchemyRequirementRepository`
- `diagrams`: `SqlAlchemyActivityDiagramRepository`
- `implementations`: `SqlAlchemyFeatureImplementationRepository`
- `chat`: `SqlAlchemyChatRepository`
- `traceability`: `SqlAlchemyTraceabilityRepository`
- `outbox`: `OutboxStore`

### Ciclo de Vida Transaccional
1. **Entrada (`__aenter__`)**:
   - Invoca `session = self._session_factory()`.
   - Instancia todos los repositorios bound pasando `session=session`.
   - Empuja el nuevo `_UowContext` al stack del `ContextVar`.
2. **Ejecución**:
   - Las operaciones de repositorio dentro del bloque UoW **no ejecutan commit** por su cuenta.
   - El llamador puede invocar `await uow.commit()` o `await uow.rollback()` explícitamente si requiere puntos de sincronización intermedios.
3. **Salida (`__aexit__`)**:
   - Extrae el contexto actual del stack.
   - Si no ocurrió ninguna excepción (`exc_type is None`), ejecuta `await ctx.session.commit()`.
   - Si ocurrió cualquier excepción, ejecuta `await ctx.session.rollback()`.
   - En el bloque `finally`, siempre ejecuta `await ctx.session.close()`.

---

## Transactional Outbox (`OutboxStore` y `run_outbox_worker`)

Implementado en [postgres/outbox.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/outbox.py).

Garantiza la entrega confiable y el procesamiento de eventos o tareas asíncronas originadas por mutaciones de dominio sin perder consistencia ante caídas del servidor.

### Estados de un Job
- `"pending"`: Encolado, pendiente de ser procesado.
- `"processing"`: Desencolado por un worker activo.
- `"done"`: Procesado satisfactoriamente por el handler.
- `"failed"`: Falló la ejecución, pero `attempts < max_attempts` (elegible para reintento).
- `"dead"`: Agotó los reintentos permitidos (`attempts >= max_attempts`). Pasa a Dead-Letter Queue.

### Desencolado Concurrente Seguro (`dequeue`)
Utiliza la cláusula `with_for_update(skip_locked=True)` para permitir que múltiples instancias de workers consuman jobs en paralelo sin bloquearse mutuamente ni procesar el mismo job:

```python
stmt = (
    select(OutboxJobModel)
    .where(
        or_(
            OutboxJobModel.status == "pending",
            and_(
                OutboxJobModel.status == "failed",
                OutboxJobModel.attempts < max_attempts,
            ),
        )
    )
    .order_by(OutboxJobModel.created_at)
    .limit(1)
    .with_for_update(skip_locked=True)
)
```

Al desencolar, pasa inmediatamente a `status = "processing"`, incrementa `attempts += 1` y commitea la transacción de reserva.

### Parámetros Operativos del Worker
- `poll_interval`: `2.0` segundos de espera cuando la cola está vacía o ante error de dequeue.
- `max_attempts`: `3` intentos antes de marcar el job como `"dead"`.
- `backoff_seconds`: `5.0` segundos.
- `max_concurrency`: `5` tareas concurrentes mediante `asyncio.Semaphore(5)`.
- **Backoff adaptativo**: Si se detectan `≥ 3` fallos en una ventana de `5.0` segundos, el worker aplica un `asyncio.sleep(5.0)` defensivo para permitir la recuperación de servicios externos downstream.
- **Graceful shutdown**: Al cancelar la corrutina principal, se cancelan todas las tareas activas registradas y se aguarda su culminación mediante `asyncio.gather(*active_tasks, return_exceptions=True)`.

---

## Registro Centralizado de Repositorios (`RepositoryRegistry`)

Implementado en [postgres/registry.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/registry.py).

Dataclass inmutable (`frozen=True`, `slots=True`) que actúa como catálogo de instancias únicas de repositorios SQL para la composición de la aplicación. Se construye mediante `RepositoryRegistry.build(session_factory)` e incluye 19 componentes:

1. `projects`: `SqlAlchemyProjectRepository`
2. `documents`: `SqlAlchemyDocumentRepository`
3. `features`: `SqlAlchemyFeatureRepository`
4. `requirements`: `SqlAlchemyRequirementRepository`
5. `diagrams`: `SqlAlchemyActivityDiagramRepository`
6. `chat`: `SqlAlchemyChatRepository`
7. `traceability`: `SqlAlchemyTraceabilityRepository`
8. `users`: `SqlAlchemyUserRepository`
9. `audit_sink`: `SqlAlchemyAuditEventSink`
10. `consistency_evaluations`: `SqlAlchemyConsistencyEvaluationRepository`
11. `workspaces`: `SqlAlchemyWorkspaceRepository`
12. `implementations`: `SqlAlchemyFeatureImplementationRepository`
13. `user_ai_configs`: `SqlAlchemyUserAiConfigRepository`
14. `project_integrations`: `SqlAlchemyProjectGitHubIntegrationRepository`
15. `project_deployments`: `SqlAlchemyProjectDeploymentRepository`
16. `sync_logs`: `SqlAlchemyCodeSyncLogRepository`
17. `user_integrations`: `SqlAlchemyUserIntegrationRepository`
18. `user_github_integrations`: `SqlAlchemyUserGitHubIntegrationRepository`
19. `user_deployment_integrations`: `SqlAlchemyUserDeploymentIntegrationRepository`

*(Nota: `SqlAlchemyAgentSessionStore` y `SqlAlchemyKnowledgePatternStore` se instancian directamente en el Composition Root al asociarse con los puertos `AgentMemoryPort` y `KnowledgePatternStore`).*

---

## Patrón Dual-Mode de Repositorios (Standalone vs Bound a UoW)

La mayoría de los repositorios soportan dos modalidades de ejecución mediante constructores híbridos:

```python
def __init__(
    self,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    session: AsyncSession | None = None,
) -> None:
    if session_factory is None and session is None:
        raise ValueError("Se requiere session_factory o session")
    self._session_factory = session_factory
    self._session = session
```

### Comportamiento según el modo
1. **Modo Bound (dentro de un `SqlAlchemyUnitOfWork`)**:
   - Se pasa `session = active_session`.
   - `_session_ctx()` reutiliza la sesión existente sin abrir una nueva.
   - `_commit()` no ejecuta nada (`if self._session is None: await session.commit()`). El commit queda delegado exclusivamente al UoW.
2. **Modo Standalone (fuera de UoW, operaciones directas)**:
   - Se pasa `session_factory = sessionmaker`.
   - `_session_ctx()` abre una sesión efímera con un context manager `async with self._session_factory() as session:`.
   - `_commit()` ejecuta `await session.commit()` de forma inmediata antes de salir.

---

## Descripción Exhaustiva de Repositorios PostgreSQL

### 1. Gestión de Proyectos y Especificaciones SDD
- **`SqlAlchemyProjectRepository` ([postgres/repositories/project_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/project_repo.py))**:
  - `by_id(project_id)`, `by_slug(owner_id, slug)`, `find_by_slug(slug)`, `list_by_owner(owner_id, limit=100)`, `save(project)`, `delete(project_id)`.
  - Mapea entidad `Project` de dominio validando propiedad y unicidad de slug por usuario.
- **`SqlAlchemyFeatureRepository` ([postgres/repositories/feature_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/feature_repo.py))**:
  - `by_id(feature_id, for_update=False)`, `list_by_project(project_id)` (ordenado por `number.asc()`), `save(feature)`, `save_many(features)` (upsert por lote), `next_number(project_id)` (calcula MAX(number) + 1), `delete(feature_id)`.
- **`SqlAlchemyRequirementRepository` ([postgres/repositories/requirement_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/requirement_repo.py))**:
  - `by_feature_id(feature_id, for_update=False) -> str | None`: Retorna el markdown de requisitos EARS.
  - `save(feature_id, markdown)`, `delete(feature_id)`.
  - La clave primaria es `feature_id`, garantizando cardinalidad 1:1 estricta con la feature correspondiente.
- **`SqlAlchemyDocumentRepository` ([postgres/repositories/document_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/document_repo.py))**:
  - `get_discovery(project_id, for_update=False) -> RichTextDocument | None`: Convierte el markdown almacenado al AST `RichTextDocument` usando `markdown_to_document()`.
  - `save_discovery(project_id, document) -> RichTextDocument`: Serializa el AST `RichTextDocument` a markdown canónico mediante `document_to_markdown()`.
  - `save_version(project_id, phase, markdown, change_ids) -> str`: Registra una instantánea inmutable en `document_versions` con ID generado con prefijo `doc_version`.
  - `get_version(version_id)`, `get_latest_version(project_id, phase)`, `delete_discovery(project_id)`, `delete_versions_by_project(project_id)`.
- **`SqlAlchemyActivityDiagramRepository` ([postgres/repositories/activity_diagram_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/activity_diagram_repo.py))**:
  - `save(diagram)`, `by_feature_id(feature_id, for_update=False)`, `exists(feature_id)`, `delete(feature_id)`.
  - Almacena y recupera sintaxis PlantUML validada asociada a una feature específica.

### 2. Conversación, Memoria de Agentes y Trazabilidad
- **`SqlAlchemyChatRepository` ([postgres/repositories/chat_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/chat_repo.py))**:
  - `save_message(...)`: Almacena mensajes con serialización estructurada de sugerencias de cambio (`DiffCambio`, `SugerenciaCambio`).
  - `get_history(...)`: Paginación basada en cursores temporales (`before=iso_timestamp`), filtrado por sesión o contexto (`context_id`), límite por defecto 200 mensajes.
  - `create_session(...)`, `list_sessions(...)`: Lista sesiones con conteo de mensajes, timestamp del último mensaje y generación automática de título invocando `derive_session_title()` sobre el primer mensaje del usuario.
  - `delete_session(...)`: Borrado en cascada de sesión y sus mensajes asociados.
- **`SqlAlchemyAgentSessionStore` ([postgres/repositories/agent_memory_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/agent_memory_repo.py))**:
  - Implementa `AgentMemoryPort`.
  - `save_session(session)`: Upsert mediante `INSERT ... ON CONFLICT (id) DO UPDATE` sincronizando logs de razonamiento, resultados de tools, errores de validación, embedding y reflexiones.
  - `get_similar_sessions(embedding, limit=5, ...)`: Búsqueda k-NN semántica utilizando el operador `<=>` de distancia coseno de pgvector sobre vectores de 1536 dimensiones.
  - `get_project_context(project_id)`: Agrega las últimas sesiones por fase, las reflexiones recientes y calcula los errores de validación más frecuentes (`common_validation_errors`).
  - `count_completed_by_phase(...)`, `purge_stale_sessions(older_than_days=7, incomplete_only=True)`.
- **`SqlAlchemyKnowledgePatternStore` ([postgres/repositories/agent_memory_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/agent_memory_repo.py))**:
  - Implementa `KnowledgePatternStore`.
  - `replace_patterns(phase, patterns)`: Sustitución atómica de patrones de conocimiento para una fase dada.
  - `list_patterns(phase, limit=10)`: Recuperación de patrones ordenados por frecuencia de soporte descendente (`support_count.desc()`).
- **`SqlAlchemyTraceabilityRepository` ([postgres/repositories/traceability_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/traceability_repo.py))**:
  - `add_edge(source_type, source_id, target_type, target_id, origin="llm")`: Inserta una arista en el grafo dirigido de dependencias SDD.
  - `get_impact_batch(artifact_ids)`: Consulta bidireccional por lote recuperando nodos `upstream` y `downstream` para calcular impacto en cascada.
  - `add_feature_requirement_edges(feature_id, requirement_ids)`, `delete_by_entity_id(entity_id)`.
- **`SqlAlchemyConsistencyEvaluationRepository` ([postgres/repositories/consistency_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/consistency_repo.py))**:
  - `save(evaluation)`: Upsert determinista basado en clave natural `(project_id, source_phase, target_phase, target_artifact_id)`.
  - `list_unresolved(project_id, target_phase)`: Evaluaciones en estado `evaluating`, `completed` o `failed`.
  - `list_for_activity(project_id, limit=50)`: Evaluaciones resueltas (`applied` o `discarded`) para historial de actividad.

### 3. Workspaces y Generación de Código (Codegen)
- **`SqlAlchemyWorkspaceRepository` ([postgres/repositories/workspace_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/workspace_repo.py))**:
  - Implementa `WorkspaceRepository`.
  - `update_lock(project_id, is_locked, locked_by=None) -> CodeWorkspace | None`:
    - Adquisición de lock atómica mediante CAS (Compare-And-Swap) a nivel de base de datos:
      ```sql
      UPDATE workspaces
      SET is_locked = true, locked_at = now, locked_by = :locked_by, updated_at = now
      WHERE project_id = :project_id
        AND (is_locked IS false OR locked_at IS NULL OR locked_at < :stale_cutoff)
      RETURNING *
      ```
    - **Recuperación de locks huérfanos**: Locks inactivos mayores a `LOCK_STALE_AFTER_MINUTES = 30` minutos son considerados *stale* y pueden ser expropiados si el proceso que los poseía murió.
    - **Primera adquisición**: Si el registro del workspace no existía aún en base de datos, ejecuta un `INSERT ... ON CONFLICT (id) DO NOTHING RETURNING *` con id `ws_{project_id}`.
  - `release_lock(project_id)`: Libera el lock estableciendo `is_locked = False`, `locked_at = None`, `locked_by = None`.
- **`SqlAlchemyFeatureImplementationRepository` ([postgres/repositories/feature_implementation_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/feature_implementation_repo.py))**:
  - Implementa `FeatureImplementationRepository`.
  - `by_feature_id(feature_id)`, `by_id(implementation_id)`, `list_by_project(project_id)`, `list_by_status(status)`, `save(implementation)`, `delete(feature_id)`.
  - Serializa y deserializa entidades ricas de dominio: `ImplementationPlan` (operaciones de archivo, símbolos destino) y `ValidationRunResult` (pasos de validación, errores con línea/columna/severidad y diagnósticos de compilación).

### 4. Seguridad, Usuarios y Auditoría
- **`SqlAlchemyUserRepository` ([postgres/repositories/users.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/users.py))**:
  - Implementa `UserRepository`.
  - `by_email(email)`: Búsqueda case-insensitive nativa gracias a la columna de tipo `CITEXT`.
  - `by_id(user_id)`.
  - `create(user)`: Inserta el usuario. Si captura `IntegrityError` de base de datos, realiza rollback y lanza `UserAlreadyExistsError("Email ya registrado")` para no exponer detalles internos del motor.
  - `update_password(...)`, `update_profile(...)`: Bloqueo pesimista de fila mediante `with_for_update()` para prevenir carreras de actualización concurrente.
- **`SqlAlchemyAuditEventSink` ([postgres/repositories/audit.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/audit.py))**:
  - Implementa `AuditEventSink`.
  - `record(event: AuditEvent)`: Extrae automáticamente `request_id`, `ip_address` y `user_agent` desde `structlog.contextvars`.
  - **Garantía Best-Effort**: La inserción se ejecuta en un bloque `try...except SQLAlchemyError`. Si falla la persistencia del log de auditoría, se registra un `_logger.warning("audit.persist_failed", ...)` estructurado, pero **nunca se propaga la excepción**. La auditoría jamás rompe ni aborta una transacción de negocio.
- **`SqlAlchemyUserAiConfigRepository` ([postgres/repositories/user_ai_config_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/user_ai_config_repo.py))**:
  - `by_user_id(user_id)`: Recupera la configuración BYOK y envuelve el texto cifrado en un `EncryptedSecret`.
  - `save(config)`: Desempaqueta `EncryptedSecret.ciphertext` (bytes Fernet) y lo almacena como texto cifrado UTF-8.
  - `delete(user_id)`.

### 5. Integraciones de Código y Despliegue en la Nube
- **`SqlAlchemyProjectGitHubIntegrationRepository` ([postgres/repositories/project_integration_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/project_integration_repo.py))**:
  - Gestiona metadatos del repositorio remoto GitHub (`repo_name`, `repo_url`, `is_public`, `default_branch`, `last_commit_hash`, `sync_status`).
- **`SqlAlchemyProjectDeploymentRepository` ([postgres/repositories/project_integration_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/project_integration_repo.py))**:
  - Gestiona el estado de despliegue en Railway (`service_id`, `service_name`, `public_url`, `deploy_status`, `build_logs_url`).
  - Serializa y deserializa estructuras complejas en JSONB: `VolumeConfig`, `PortSpec` y `EnvironmentVariable`.
  - `list_by_status(status)`: Permite recuperar despliegues en progreso (`BUILDING`, `DEPLOYING`) durante el lifespan de inicio del servidor para reanudar su monitoreo.
- **`SqlAlchemyCodeSyncLogRepository` ([postgres/repositories/project_integration_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/project_integration_repo.py))**:
  - `add_log(log)`: Registra auditoría de commits sincronizados (`commit_sha`, `status`, `message`).
  - `get_logs_by_project(project_id)`: Historial cronológico inverso.
- **`SqlAlchemyUserIntegrationRepository` ([postgres/repositories/user_integration_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/user_integration_repo.py))**:
  - Adaptador base para credenciales OAuth personales (GitHub, Railway) con tokens de acceso y refresh cifrados (`access_token_enc`, `refresh_token_enc`).
- **`SqlAlchemyUserGitHubIntegrationRepository` y `SqlAlchemyUserDeploymentIntegrationRepository`**:
  - Implementaciones especializadas que delegan en `SqlAlchemyUserIntegrationRepository` fijando los proveedores canónicos `IntegrationProvider.GITHUB` y `DeploymentProvider.RAILWAY`.

---

## Redis Stores para Autenticación y Seguridad

### 1. `RedisAuthorizationCodeStore` ([redis/authorization_code_store.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/redis/authorization_code_store.py))
- **Propósito**: Gestión del ciclo de vida de códigos de autorización PKCE (RFC 7636).
- **Prefijo de clave**: `auth:authcode:{code}`.
- **Almacenamiento (`store`)**:
  - Calcula el TTL exacto en segundos (`expires_at - now`).
  - Ejecuta `SET key value EX ttl NX`. La bandera `NX=True` garantiza que no se sobreescriba un código preexistente.
- **Consumo Atómico (`consume`)**:
  - Abre un pipeline transaccional (`pipeline(transaction=True)`).
  - Encola `pipe.get(key)` y `pipe.delete(key)`.
  - Ejecuta atómicamente. Garantiza que el código se consuma **exactamente una sola vez** y previene ataques de repetición (*replay attacks*).

### 2. `RedisLoginAttemptStore` ([redis/login_attempt_store.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/redis/login_attempt_store.py))
- **Propósito**: Mitigación de ataques de fuerza bruta y credential stuffing sobre endpoints de login.
- **Prefijo de clave**: `auth:login_attempts:{identifier}` (donde identifier es IP o email).
- **Parámetros**:
  - Ventana deslizante: `_WINDOW_SECONDS = 900` (15 minutos).
  - Umbral máximo: `_MAX_FAILURES = 10` intentos fallidos.
- **Operaciones**:
  - `record_failure(identifier)`: Pipeline transaccional con `pipe.incr(key)` y `pipe.expire(key, 900)`.
  - `clear(identifier)`: Elimina la clave tras una autenticación exitosa.
  - `lockout_seconds(identifier) -> int | None`: Si `count >= 10`, consulta `await client.ttl(key)` y retorna los segundos restantes de bloqueo para la cabecera HTTP `Retry-After`. Si no está bloqueado, retorna `None`.

### 3. `RedisTokenRevocationStore` ([redis/token_store.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/redis/token_store.py))
- **Propósito**: Rotación segura de refresh tokens, revocación de cadenas de tokens (*Token Families* RFC 6819) y lista negra de access tokens.
- **Prefijos de claves**:
  - `_REFRESH_PREFIX`: `auth:refresh:{jti}` → Almacena `{subject}|{family_id}` con TTL del refresh token (7 días).
  - `_FAMILY_PREFIX`: `auth:family:{family_id}` → Marca de vida de la familia de tokens.
  - `_GRACE_PREFIX`: `auth:grace:{old_jti}` → Almacena el nuevo par de tokens durante 30 segundos de gracia.
  - `_REVOKED_ACCESS_PREFIX`: `auth:revoked:access:{jti}` → Marca tokens de acceso revocados antes de su expiración natural.
- **Consumo Atómico de Refresh Token (`consume_refresh`)**:
  - Pipeline transaccional:
    1. `pipe.get(auth:refresh:jti)`
    2. `pipe.delete(auth:refresh:jti)`
    3. `pipe.set(auth:grace:jti, "ROTATING", ex=30)`
  - Si el token ya no existía en Redis, elimina la clave de gracia y retorna `None` (lo que dispara la detección de reuso y la revocación de la familia completa).
- **Período de Gracia y Manejo de Concurrencia**:
  - Ante peticiones paralelas legítimas (e.g., múltiples pestañas del navegador abriéndose a la vez con el mismo refresh token), la primera inicia la rotación dejando el estado `"ROTATING"`.
  - Las peticiones concurrentes ejecutan `get_grace_period()` con sondeo no bloqueante:
    - Intervalo: `_GRACE_POLL_INTERVAL_SECONDS = 0.05` (50 ms).
    - Intentos máximos: `_GRACE_POLL_MAX_ATTEMPTS = 30` (espera máxima de 1.5 s).
    - En cuanto la petición principal finaliza y llama a `store_grace_period()`, las secundarias reciben el `TokenPair` ya emitido sin fallar ni invalidar la sesión.
- **Revocación de Familia RFC 6819 (`revoke_family`)**:
  - Elimina `auth:family:{family_id}`.
  - Cualquier intento posterior de refrescar tokens asociados a esa familia será denegado, forzando la reautenticación del usuario tras un robo o fuga de token.

---

## Contratos Implementados (Puertos vs Implementaciones)

| Puerto / Interfaz (`contracts/`) | Clase Concreta de Persistencia | Archivo de Implementación |
|:---|:---|:---|
| `ProjectRepository` | `SqlAlchemyProjectRepository` | [postgres/repositories/project_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/project_repo.py) |
| `FeatureRepository` | `SqlAlchemyFeatureRepository` | [postgres/repositories/feature_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/feature_repo.py) |
| `RequirementRepository` | `SqlAlchemyRequirementRepository` | [postgres/repositories/requirement_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/requirement_repo.py) |
| `DocumentRepository` | `SqlAlchemyDocumentRepository` | [postgres/repositories/document_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/document_repo.py) |
| `ActivityDiagramRepository` | `SqlAlchemyActivityDiagramRepository` | [postgres/repositories/activity_diagram_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/activity_diagram_repo.py) |
| `ChatRepository` | `SqlAlchemyChatRepository` | [postgres/repositories/chat_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/chat_repo.py) |
| `TraceabilityRepository` | `SqlAlchemyTraceabilityRepository` | [postgres/repositories/traceability_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/traceability_repo.py) |
| `ConsistencyEvaluationRepository` | `SqlAlchemyConsistencyEvaluationRepository` | [postgres/repositories/consistency_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/consistency_repo.py) |
| `AgentMemoryPort` | `SqlAlchemyAgentSessionStore` | [postgres/repositories/agent_memory_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/agent_memory_repo.py) |
| `KnowledgePatternStore` | `SqlAlchemyKnowledgePatternStore` | [postgres/repositories/agent_memory_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/agent_memory_repo.py) |
| `UserRepository` | `SqlAlchemyUserRepository` | [postgres/repositories/users.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/users.py) |
| `AuditEventSink` | `SqlAlchemyAuditEventSink` | [postgres/repositories/audit.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/audit.py) |
| `WorkspaceRepository` | `SqlAlchemyWorkspaceRepository` | [postgres/repositories/workspace_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/workspace_repo.py) |
| `FeatureImplementationRepository` | `SqlAlchemyFeatureImplementationRepository` | [postgres/repositories/feature_implementation_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/feature_implementation_repo.py) |
| `UserAiConfigRepository` | `SqlAlchemyUserAiConfigRepository` | [postgres/repositories/user_ai_config_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/user_ai_config_repo.py) |
| `UserIntegrationRepository` | `SqlAlchemyUserIntegrationRepository` | [postgres/repositories/user_integration_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/user_integration_repo.py) |
| `UserGitHubIntegrationRepository` | `SqlAlchemyUserGitHubIntegrationRepository` | [postgres/repositories/user_integration_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/user_integration_repo.py) |
| `UserDeploymentIntegrationRepository` | `SqlAlchemyUserDeploymentIntegrationRepository` | [postgres/repositories/user_integration_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/user_integration_repo.py) |
| `ProjectGitHubIntegrationRepository` | `SqlAlchemyProjectGitHubIntegrationRepository` | [postgres/repositories/project_integration_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/project_integration_repo.py) |
| `ProjectDeploymentRepository` | `SqlAlchemyProjectDeploymentRepository` | [postgres/repositories/project_integration_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/project_integration_repo.py) |
| `CodeSyncLogRepository` | `SqlAlchemyCodeSyncLogRepository` | [postgres/repositories/project_integration_repo.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/repositories/project_integration_repo.py) |
| `UnitOfWork` | `SqlAlchemyUnitOfWork` | [postgres/uow.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/uow.py) |
| `OutboxPort` | `OutboxStore` | [postgres/outbox.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/postgres/outbox.py) |
| `AuthorizationCodeStore` | `RedisAuthorizationCodeStore` | [redis/authorization_code_store.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/redis/authorization_code_store.py) |
| `LoginAttemptStore` | `RedisLoginAttemptStore` | [redis/login_attempt_store.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/redis/login_attempt_store.py) |
| `TokenRevocationStore` | `RedisTokenRevocationStore` | [redis/token_store.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/persistence/redis/token_store.py) |

---

## Constantes y Parámetros Operativos

| Constante | Valor | Ubicación | Significado Técnico |
|:---|:---|:---|:---|
| `_MAX_ATTEMPTS` | `3` | `postgres/outbox.py` | Intentos máximos antes de marcar un outbox job como `"dead"` |
| `_BACKOFF_SECONDS` | `5.0` | `postgres/outbox.py` | Tiempo de backoff del worker ante racha de fallos |
| `max_concurrency` | `5` | `postgres/outbox.py` | Concurrencia de procesamiento paralelo de jobs con semáforo |
| `poll_interval` | `2.0` | `postgres/outbox.py` | Intervalo en segundos de sondeo cuando no hay jobs pendientes |
| `LOCK_STALE_AFTER_MINUTES` | `30` | `postgres/repositories/workspace_repo.py` | Umbral para considerar huérfano y reclamar un lock de workspace |
| `_WINDOW_SECONDS` | `900` (15 min) | `redis/login_attempt_store.py` | Ventana deslizante para conteo de fallos de login |
| `_MAX_FAILURES` | `10` | `redis/login_attempt_store.py` | Fallos máximos permitidos antes de bloquear autenticación |
| `_GRACE_POLL_INTERVAL_SECONDS` | `0.05` (50 ms) | `redis/token_store.py` | Intervalo de polling durante rotación concurrente de tokens |
| `_GRACE_POLL_MAX_ATTEMPTS` | `30` (1.5 s total) | `redis/token_store.py` | Intentos máximos de polling en estado `"ROTATING"` |
| Grace Period TTL | `30` s | `redis/token_store.py` | Tiempo de vida del par de tokens en clave de gracia tras rotación |
| `pgvector` dimensiones | `1536` | `postgres/models.py` | Dimensión del vector para modelos de embedding OpenAI |

---

## Reglas de Implementación y Mantenimiento

1. **Invariante Transaccional del Unit of Work**: Ningún repositorio debe ejecutar `commit()` por su cuenta cuando se encuentra enlazado a una sesión compartida (`self._session is not None`). El commit es responsabilidad unificada y final de `SqlAlchemyUnitOfWork.__aexit__`.
2. **Modelos ORM y Migraciones**: Todo cambio en `postgres/models.py` requiere una migración declarativa con Alembic. Nunca modificar esquemas de tablas en runtime ni asumir auto-migración en producción.
3. **Manejo de Claves Primarias y Prefijos**: Todas las claves primarias son generadas antes de la inserción mediante `IdGenerator.generate(entity)` produciendo IDs basados en ULID lexicográficamente ordenables con prefijo de dominio (`prj_`, `feat_`, `req_`, `usr_`, `msg_`, etc.).
4. **Protección Concurrente con CAS y Locks**: En operaciones críticas sobre workspaces o recursos con contienda, utilizar CAS a nivel SQL (`update().where(...)`) o `with_for_update()`. Nunca depender exclusivamente de `asyncio.Lock` en memoria, ya que no protege contra múltiples procesos o workers de FastAPI.
5. **Auditoría No Bloqueante**: `SqlAlchemyAuditEventSink.record()` debe permanecer siempre con protección `try...except SQLAlchemyError`. Una falla en la persistencia de auditoría jamás debe hacer rollback ni abortar una operación de negocio legítima.
6. **Búsqueda Vectorial Eficiente**: Toda búsqueda semántica con `get_similar_sessions()` debe garantizar que la columna `embedding` tenga índice ivfflat/hnsw en PostgreSQL y usar el operador coseno `<=>`.

---

## Directrices de Seguridad y Consistencia

- **Búsqueda de Emails sin Vulnerabilidad de Case Sensitivity**: El modelo `UserModel` utiliza `pg.CITEXT()`. Las consultas de búsqueda de usuario son case-insensitive nativas en el motor; no realizar normalizaciones manuales `.lower()` en Python que puedan divergir de las reglas de cotejamiento de PostgreSQL.
- **Protección contra Fuga de Constraints**: En `SqlAlchemyUserRepository.create()`, los errores de integridad (`IntegrityError`) deben capturarse y traducirse a excepciones de contratos tipadas (`UserAlreadyExistsError`), sin propagar nombres de índices o tablas al exterior.
- **Cifrado de Secretos en Reposo**: Las columnas de credenciales sensibles (`access_token_enc`, `refresh_token_enc`, `encrypted_api_key`) almacenan exclusivamente bytes cifrados con Fernet AES-128-CBC + HMAC. Nunca persistir tokens ni API keys en texto claro.
- **Defensa contra Replay y Reúso de Tokens**: El flujo PKCE (`RedisAuthorizationCodeStore`) y el flujo de refresco de tokens (`RedisTokenRevocationStore`) emplean pipelines atómicos de Redis (`GET` + `DELETE` simultáneo) para garantizar el consumo exactamente-una-vez y la detección de reutilización con revocación en cadena (RFC 6819).
