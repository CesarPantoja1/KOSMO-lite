# `contracts/` — Capa de Contratos: Puertos, DTOs, Enums y Jerarquía de Errores

## Responsabilidad y Propósito

La capa `contracts/` constituye el núcleo normativo y el anillo más interno de la arquitectura hexagonal de KOSMO. Establece la totalidad de interfaces abstractas, tipos inmutables, contratos de datos y convenciones de error que rigen la interacción entre las capas de dominio, aplicación e infraestructura.

Responsabilidades principales:
- **Puertos de Abstracción (`Protocol`)**: Define las interfaces que desacoplan la lógica de negocio de las tecnologías de persistencia (SQLAlchemy/PostgreSQL, Redis), clientes LLM, orquestación de contenedores OpenCode, herramientas Git y servicios cloud (GitHub, Railway).
- **Entidades y DTOs Inmutables (`dataclass(frozen=True)`)**: Estructuras de datos puras para transferir información a través de los límites de capa sin riesgo de mutación colateral accidental.
- **Tipos de Identificador Fuertemente Tipados (`NewType`)**: 17 identificadores opacos derivados de `str` para prevenir la mezcla de IDs entre entidades en tiempo de análisis estático con pyright.
- **Enums Canónicos de Dominio**: Centraliza valores admisibles para fases SDD (`SpecPhase`), proveedores de IA (`AIProvider`), disposiciones de implementación (`ImplementationDisposition`), arquetipos de diseño (`BusinessArchetype`), estados de ciclo de vida y severidades.
- **Esquemas Estructurados para LLM (Pydantic v2)**: Modelos de salida tipada consumidos por PydanticAI para garantizar parsing estructurado en todas las fases del pipeline.
- **Jerarquía de Errores de Dominio (RFC 7807)**: Excepciones especializadas (`SpecError` y sus 14 variantes con `ProblemDetail`, junto a `AuthError` y sus 10 variantes) mapeables directamente a respuestas HTTP estándar.

> **Regla Arquitectónica Fundamental**: Ningún módulo dentro de `contracts/` puede importar de `domain/`, `application/` ni `infrastructure/`. La capa solo depende de la biblioteca estándar de Python, `pydantic` y `ulid`.

---

## Estructura de Archivos y Componentes

```
contracts/
├── __init__.py                          # Fachada pública que reexporta 120+ símbolos esenciales
├── telemetry.py                         # Puerto TelemetryPort y decorador @traced
├── ai/
│   ├── ai_config.py                     # AIProvider, UserAiConfig, AIConnectionTester, UserAiConfigRepository
│   ├── chat.py                          # ChatRole, MensajeChat, HistorialChat, AppliedChange, ChatRepository
│   └── consistency.py                   # Regla DOWNSTREAM_TARGETS, ConsistencyEvaluation, evaluator protocol
├── audit/
│   ├── events.py                        # AuditEvent, AuditOutcome, AuditEventType
│   └── ports.py                         # Puerto AuditEventSink
├── auth/
│   ├── context.py                       # Variable de contexto current_user_id (ContextVar)
│   ├── errors.py                        # Jerarquía AuthError (10 subclases de autenticación y PKCE)
│   ├── pkce.py                          # AuthorizationCode, PkceMethod, AuthorizationCodeStore
│   ├── ports.py                         # TokenIssuer, TokenVerifier, PasswordHasher, UserRepository, LoginAttemptStore
│   ├── principal.py                     # Entidad de identidad Principal y verificación de scopes (comodín "*")
│   ├── secrets.py                       # EncryptedSecret y puerto SecretCipher
│   ├── tokens.py                        # TokenType, IssuedToken, TokenPair, TokenClaims, TokenRevocationStore
│   └── users.py                         # Entidad User (inmutable)
├── integrations/
│   ├── deployment.py                    # DeploymentProvider, DeploymentStatus, Railway client y repos
│   ├── git.py                           # GitWorkspacePort y resultados de operaciones Git
│   ├── github.py                        # GitHubClientPort, ProjectGitHubIntegration, repositorios
│   └── user_integration.py              # IntegrationProvider, UserIntegration y UserIntegrationRepository
├── llm/
│   └── ports.py                         # LLMClient, Embedder, PromptTemplate, LLMResponse
├── memory/
│   ├── agent_memory.py                  # AgentSession, AgentMemoryPort, KnowledgePatternStore
│   └── user_preference.py               # UserPreference y UserPreferenceRepository
├── persistence/
│   └── persistence.py                   # Protocolos transaccionales: UnitOfWork y OutboxPort
├── pipeline/
│   ├── consistency_phase_context.py      # DownstreamArtifact y ConsistencyPhaseContext
│   ├── orchestrator_ports.py             # Protocolos PhaseMode, Skill y AgentPort
│   ├── phase_contexts.py                 # 12 contextos tipados por fase de pipeline
│   ├── phase_errors.py                   # PhaseTransitionError y PhaseNotSupportedError
│   └── phase_outputs.py                  # DTOs de salida y 11 modelos estructurados Pydantic v2 para LLM
└── sdd/
    ├── activity_diagram.py               # DiagramaActividad
    ├── codegen.py                        # WorkspaceManagerPort, FileSystemReader/Writer, CodeRunnerPort, OpenCodeClientPort
    ├── document.py                       # RichTextDocument AST, SpecPhase, EARSPattern, DocumentNode, TextMark
    ├── ears.py                           # EARSRequirement y AcceptanceCriterion
    ├── errors.py                         # Jerarquía SpecError, ProblemDetail (RFC 7807) y 14 subclases
    ├── feature.py                        # Entidad Feature
    ├── guardrails.py                     # PROHIBITED_TERMS, FEATURE_LEVEL_PROHIBITED_TERMS, DISCOVERY_SECTIONS
    ├── ids.py                            # 17 identificadores NewType tipados
    ├── product_map.py                    # ProductMap, ImplementationDisposition (5 tipos), ActorRef, CapabilityRef
    ├── project.py                        # Entidad Project
    ├── repositories.py                   # 5 repositorios base SDD (Project, Feature, Document, Requirement, Diagram)
    └── ux_context.py                     # BusinessArchetype (5 tipos), ShellPattern, BootstrapDesignTokens, UXContext
```

---

## Descripción Detallada por Subdirectorio

### 1. `telemetry.py` — Observabilidad y Tracing

- **`TelemetryPort`** (`@runtime_checkable Protocol`): Define métodos de registro de trazas sincrónicas y asíncronas (`trace_sync`, `trace_async`), eventos de autenticación (`record_auth_event`), duración de generación de código (`record_codegen_duration`), reintentos (`record_codegen_retries`) y consumo de tokens LLM (`record_llm_tokens`).
- **`@traced(span_name, attributes_extractor)`**: Decorador que envuelve funciones asíncronas y sincrónicas, inyectando instrumentación OpenTelemetry sin acoplar el código al SDK concreto.
- **`set_telemetry_provider(provider)`**: Configura la instancia global de telemetría de la aplicación.

### 2. `ai/` — Configuración de IA, Chat y Consistencia

- **`ai_config.py`**:
  - `AIProvider` (StrEnum): `OPENAI`, `ANTHROPIC`, `GOOGLE`, `DEEPSEEK`, `CUSTOM`, `KOSMO_DEFAULT`.
  - `DEFAULT_AI_MODEL = "gemini-3.8-flash"`.
  - `UserAiConfig`: DTO con proveedor, modelo y clave API cifrada (`EncryptedSecret`).
  - `AIConnectionTester` y `UserAiConfigRepository`: Puertos para comprobación HTTP de credenciales y persistencia.
- **`chat.py`**:
  - `ChatRole` (StrEnum): `USER`, `ASSISTANT`, `SYSTEM`.
  - `MensajeChat`, `SugerenciaCambio`, `DiffCambio`, `AppliedChange`, `HistorialChat`, `ChatSession`: Modelos inmutables para el flujo conversacional con soporte de diffs estructurados.
  - `ChatRepository`: Puerto para persistencia paginada (`get_history` con cursor temporal) y almacenamiento de sesiones.
- **`consistency.py`**:
  - `DOWNSTREAM_TARGETS`: Regla estricta de propagación unidireccional:
    - `DESCUBRIMIENTO` → `[CARACTERISTICAS, REQUISITOS, MODELO, IMPLEMENTACION]`
    - `CARACTERISTICAS` → `[REQUISITOS, MODELO, IMPLEMENTACION]`
    - `REQUISITOS` → `[MODELO, IMPLEMENTACION]`
    - `MODELO` → `[IMPLEMENTACION]`
    - `IMPLEMENTACION` → `[]`
  - `ConsistencyEvaluation`, `ConsistencyStatus`: Registro inmutable de evaluaciones de impacto.
  - `ConsistencyEvaluationRepository`: Puerto de persistencia y verificación de evaluaciones existentes.

### 3. `audit/` — Trazabilidad y Seguridad de Auditoría

- **`events.py`**:
  - `AuditEventType`: 12 tipos de eventos (login, logout, registro, revocación de tokens, modificaciones de especificación, operaciones de workspace).
  - `AuditOutcome`: `SUCCESS`, `FAILURE`.
  - `AuditEvent`: DTO inmutable con `event_id`, timestamp UTC, actor, IP, recurso y payload JSON.
- **`ports.py`**:
  - `AuditEventSink` (`Protocol`): Puerto para registro no bloqueante de auditoría (`record(event)`).

### 4. `auth/` — Autenticación, Tokens y Criptografía

- **`context.py`**:
  - `current_user_id`: `ContextVar[str | None]` para propagación segura del ID de usuario autenticado en la corrutina activa.
- **`errors.py`**:
  - `AuthError`: Excepción base de autenticación.
  - 10 subclases especializadas: `InvalidTokenError`, `TokenExpiredError`, `TokenRevokedError`, `MissingTokenError`, `TokenReusedError`, `UserAlreadyExistsError`, `InvalidCredentialsError`, `AuthorizationCodeError`, `PkceMismatchError`, `AccountLockedError` (con atributo `seconds_remaining`).
- **`pkce.py`**:
  - `PkceMethod`: `S256`.
  - `AuthorizationCode`: DTO con código, expiración, usuario y desafío de código.
  - `AuthorizationCodeStore`: Puerto de consumo atómico de un solo uso.
- **`principal.py`**:
  - `Principal`: DTO que representa la identidad autenticada (`subject: UserId`, `scopes: frozenset[str]`).
  - `has_scope(scope)` y `has_scopes(*scopes)`: Verificación de permisos con soporte de comodín superadministrador (`"*"`).
- **`secrets.py`**:
  - `EncryptedSecret`: Contenedor inmutable de secretos cifrados (`ciphertext: bytes`, `key_id: str`).
  - `SecretCipher` (`Protocol`): Puerto de cifrado/descifrado simétrico en reposo.
- **`tokens.py`**:
  - `TokenType`: `ACCESS`, `REFRESH`.
  - `IssuedToken`, `TokenPair`, `TokenClaims`: Estructuras inmutables de tokens JWT.
  - `TokenRevocationStore`: Puerto para lista negra de tokens y rotación de familias con período de gracia (*grace period*).
- **`users.py`**:
  - `User`: Entidad de usuario inmutable (`id`, `email`, `hashed_password`, `disabled_at`, timestamps).

### 5. `integrations/` — GitHub, Railway y Git

- **`deployment.py`**:
  - `DeploymentProvider`: `RAILWAY`.
  - `DeploymentStatus`: `INITIALIZING`, `BUILDING`, `DEPLOYING`, `SUCCESS`, `FAILED`, `REMOVED`.
  - `ProjectDeployment`: DTO de despliegue en la nube.
  - `RailwayClientPort` y `ProjectDeploymentRepository`: Puertos de interacción con GraphQL/REST de Railway y base de datos.
- **`git.py`**:
  - `GitWorkspacePort`: Protocolo abstracto de 13 operaciones Git locales sincrónicas y asíncronas.
- **`github.py`**:
  - `GitHubClientPort`: Puerto para validación de tokens, creación de repositorios, configuración de webhooks y sincronización.
  - `ProjectGitHubIntegration`: DTO de vinculación entre proyecto KOSMO y repositorio GitHub.
- **`user_integration.py`**:
  - `IntegrationProvider`: `GITHUB`, `RAILWAY`.
  - `UserIntegration`: Credenciales OAuth2 cifradas por usuario.

### 6. `llm/` — Clientes de Lenguaje y Embeddings

- **`ports.py`**:
  - `LLMClient` (`Protocol`): Métodos `complete`, `complete_json`, `complete_typed`, `complete_stream` y `complete_with_tools`.
  - `Embedder` (`Protocol`): Puerto para generación de vectores de embedding (`embed_text(text) -> list[float] | None`).
  - `PromptTemplate`: Plantilla inmutable con variables de sustitución.
  - `LLMResponse`: Respuesta con contenido textual, metadatos y tokens consumidos.

### 7. `memory/` — Memoria del Agente y Preferencias

- **`agent_memory.py`**:
  - `AgentSession`: Sesión persistida con conversación JSONB, embeddings y vector para pgvector.
  - `AgentMemoryPort`: Búsqueda k-NN por similitud coseno (`get_similar_sessions`) y agregación de contexto.
  - `KnowledgePatternStore`: Almacenamiento de patrones aprendidos por fase.
- **`user_preference.py`**:
  - `UserPreference`: Regla de personalización del usuario inyectada en los prompts del agente.

### 8. `persistence/` — Transaccionalidad y Outbox

- **`persistence.py`**:
  - `UnitOfWork` (`Protocol`): Gestor de contexto asíncrono (`__aenter__` / `__aexit__`) que expone los repositorios del sistema y garantiza `commit` o `rollback` atómico.
  - `OutboxPort` (`Protocol`): Puerto para encolar trabajos diferidos (`enqueue(job_type, payload)`).

### 9. `pipeline/` — Orquestación, Contextos y Salidas Estructuradas

- **`orchestrator_ports.py`**:
  - `PhaseMode` (`Protocol`): Interfaz para estrategias de fase (`system_prompt`, `temperature`, `max_tokens`, `output_type`, `build_user_prompt`, `validate_output`, `build_retry_prompt`, `build_output`).
  - `Skill`: Contenedor inmutable que vincula nombre, fase, descripción y `PhaseMode`.
  - `AgentPort` (`Protocol`): Puerto de ejecución del agente (`execute_with_skill`, `execute_conversation`, `execute_direct_modification`, `execute_conversation_stream`).
- **`phase_contexts.py`**:
  - 12 contextos inmutables: `DiscoveryPhaseContext`, `DiscoveryRefinePhaseContext`, `FeaturesPhaseContext`, `EARSPhaseContext`, `SuggestFeaturesContext`, `RequirementsRefinePhaseContext`, `ModeloPhaseContext`, `DiscoveryChatContext`, `FeatureChatContext`, `RequirementChatContext`, `DirectModificationContext`, `ImplementationPhaseContext`.
- **`consistency_phase_context.py`**:
  - `DownstreamArtifact`: Representación homogénea de artefactos para evaluación de consistencia.
  - `ConsistencyPhaseContext`: Contexto transversal para análisis downstream.
- **`phase_outputs.py`**:
  - DTOs de salida: `GenerationMetadata`, `ValidationResult`, `DiscoveryPhaseOutput`, `FeaturesPhaseOutput`, `SuggestFeaturesOutput`, `EARSPhaseOutput`, `ModeloPhaseOutput`.
  - 11 Modelos Pydantic v2 estructurados para LLM: `DiscoveryDocument`, `FeatureSpec`, `FeatureSet`, `AcceptanceCriterionSpec`, `EARSRequirementSpec`, `EARSSet`, `RequirementsDocument`, `DiagramSpec`, `ConsistencyReport`, `ConsistencyDetectionReport`, `ConsistencyCorrection`, `ResolvedSection`, `DirectModificationResult`.

### 10. `sdd/` — Entidades SDD, Codegen, UX y Errores

- **`ids.py`**: 17 identificadores fuertemente tipados con `NewType`:
  `ProjectId`, `FeatureId`, `RequirementId`, `SpecId`, `TaskId`, `UserId`, `ApiKey`, `AuditId`, `PipelineId`, `AgentMemoryId`, `ActivityDiagramId`, `ChatMessageId`, `ChatHistoryId`, `ConsistencyEvaluationId`, `ChatSessionId`, `WorkspaceId`, `ImplementationId`.
- **`document.py`**:
  - `SpecPhase` (StrEnum): `DESCUBRIMIENTO`, `CARACTERISTICAS`, `REQUISITOS`, `MODELO`, `IMPLEMENTACION`.
  - `EARSPattern` (StrEnum): `ubiquitous`, `event_driven`, `state_driven`, `optional`, `unwanted`, `complex`.
  - `RichTextDocument`, `DocumentNode`, `SectionHeading`, `TextMark`, `MarkType`: Modelos inmutables del AST.
- **`ears.py`**:
  - `EARSRequirement`: Entidad de requisito con número, título, patrón, enunciado, origen y criterios de aceptación.
  - `AcceptanceCriterion`: Escenario BDD (`scenario`, `given`, `when`, `then`).
- **`activity_diagram.py`**:
  - `DiagramaActividad`: Diagrama PlantUML persistido por característica.
- **`feature.py`**:
  - `Feature`: Entidad inmutable de característica (`id`, `project_id`, `number`, `title`, `slug`, `description`, `origin`).
- **`project.py`**:
  - `Project`: Entidad inmutable de proyecto con fase actual (`current_phase`) y propietario (`owner_id`).
- **`product_map.py`**:
  - `ImplementationDisposition` (StrEnum): `CREATE`, `EXTEND`, `INTEGRATE`, `COMPOSE`, `SKIP`.
  - `DomainEntityRef`, `ActorRef`, `CapabilityRef`, `ProductFlowStep`, `ProductFlow`, `FeatureDisposition`, `ProductMap`.
- **`ux_context.py`**:
  - `BusinessArchetype` (StrEnum): `STOREFRONT`, `DASHBOARD`, `WORKFLOW`, `SAAS_TOOL`, `CONTENT`.
  - `ShellPattern` (StrEnum): `SIDEBAR`, `TOP_NAV`, `MINIMAL`.
  - `DataDensity` (StrEnum): `HIGH`, `MEDIUM`, `LOW`.
  - `BootstrapDesignTokens` y `UXContext`: DTOs de diseño visual generados para el workspace frontend.
- **`codegen.py`**:
  - Enums: `WorkspaceStatus`, `FeatureImplementationStatus`, `FileAction`, `ValidationStep`, `ValidationSeverity`, `OpenCodeEventType`.
  - DTOs: `OpenCodeEvent`, `OpenCodeSession`, `FileOperation`, `ImplementationPlan`, `ValidationErrorDetail`, `ValidationStepResult`, `ValidationRunResult`, `CodeWorkspace`, `FeatureImplementation`.
  - Puertos: `WorkspaceManagerPort`, `FileSystemReader` (`@runtime_checkable`), `FileSystemWriter` (`@runtime_checkable`), `CodeRunnerPort`, `OpenCodeClientPort`, `WorkspaceRepository`, `FeatureImplementationRepository`.
- **`guardrails.py`**:
  - `PROHIBITED_TERMS`: 26 términos técnicos de backend/infraestructura prohibidos en Descubrimiento.
  - `FEATURE_LEVEL_PROHIBITED_TERMS`: 10 términos abstractos prohibidos en Características.
  - `DISCOVERY_SECTIONS`: Las 7 secciones obligatorias del documento de Descubrimiento.
- **`errors.py`**:
  - `ProblemDetail` (RFC 7807): `type`, `title`, `status`, `detail`, `instance`, `trace_id`, `violations`.
  - `SpecError`: Excepción base que encapsula `ProblemDetail`.
  - 14 subclases de error de especificación: `ProjectNotFoundError`, `FeatureNotFoundError`, `RequirementNotFoundError`, `DocumentNotFoundError`, `DiagramNotFoundError`, `WorkspaceNotFoundError`, `WorkspaceLockedError`, `FeatureImplementationNotFoundError`, `ImplementationAlreadyInProgressError`, `UserCodegenConfigError`, `PhaseValidationError`, `SpecPhaseTransitionError`, `InvalidPhaseTransitionError`, `StaleEvaluationError`.
- **`repositories.py`**:
  - 5 puertos fundamentales: `ProjectRepository`, `FeatureRepository`, `DocumentRepository`, `RequirementRepository`, `ActivityDiagramRepository`.

---

## Constantes, Enums y Valores Clave

| Constante / Enum | Valores / Tipo | Archivo | Propósito |
|:---|:---|:---|:---|
| `SpecPhase` | 5 fases (`DESCUBRIMIENTO` a `IMPLEMENTACION`) | `sdd/document.py` | Ciclo canónico del pipeline SDD |
| `AIProvider` | `OPENAI`, `ANTHROPIC`, `GOOGLE`, `DEEPSEEK`, `CUSTOM`, `KOSMO_DEFAULT` | `ai/ai_config.py` | Proveedores de inferencia soportados |
| `DEFAULT_AI_MODEL` | `"gemini-3.8-flash"` | `ai/ai_config.py` | Modelo predeterminado del sistema |
| `ImplementationDisposition` | `CREATE`, `EXTEND`, `INTEGRATE`, `COMPOSE`, `SKIP` | `sdd/product_map.py` | Estrategia de integración de features en codegen |
| `BusinessArchetype` | `STOREFRONT`, `DASHBOARD`, `WORKFLOW`, `SAAS_TOOL`, `CONTENT` | `sdd/ux_context.py` | Arquetipos visuales y de UX |
| `ShellPattern` | `SIDEBAR`, `TOP_NAV`, `MINIMAL` | `sdd/ux_context.py` | Disposición del layout de la aplicación |
| `DataDensity` | `HIGH`, `MEDIUM`, `LOW` | `sdd/ux_context.py` | Densidad de información de la interfaz |
| `ValidationStep` | `STRUCTURE`, `TYPECHECK`, `LINT`, `TESTS`, `BUILD` | `sdd/codegen.py` | Pasos del pipeline de validación de código |
| `OpenCodeEventType` | 9 tipos de eventos | `sdd/codegen.py` | Eventos de streaming en generación de código |
| Identificadores `NewType` | 17 tipos específicos | `sdd/ids.py` | Tipado estricto para prevención de ID swapping |
| `SpecError` subclases | 14 excepciones con RFC 7807 | `sdd/errors.py` | Mapeo determinista de errores a HTTP |
| `AuthError` subclases | 10 excepciones | `auth/errors.py` | Control de fallos de autenticación y tokens |
| `DISCOVERY_SECTIONS` | 7 secciones | `sdd/guardrails.py` | Estructura canónica del documento de Descubrimiento |

---

## Reglas de Implementación y Mantenimiento

1. **Inmutabilidad Absoluta**: Todas las entidades y DTOs deben declararse con `@dataclass(frozen=True)` o heredar de modelos inmutables de Pydantic. Los campos mutables como listas deben tiparse y exponerse como tuplas (`tuple[...]`) o inicializarse mediante `default_factory`.
2. **Cero Dependencias Circulares o Hacia Arriba**: `contracts/` nunca debe depender de `domain/`, `application/` ni `infrastructure/`. Esta regla se comprueba mediante `import-linter` en CI.
3. **Identificadores Opacos con `NewType`**: Las firmas de métodos en puertos de repositorio y casos de uso deben usar siempre identificadores tipados (`ProjectId`, `FeatureId`, etc.) y nunca cadenas genéricas `str`.
4. **Fachada Centralizada**: Todo símbolo público de nueva creación debe incorporarse en el `__all__` del `__init__.py` correspondiente y reexportarse en `contracts/__init__.py`.
5. **Cumplimiento RFC 7807**: Toda excepción de dominio que represente un fallo de negocio debe heredar de `SpecError` y proveer un `ProblemDetail` con código de estado HTTP adecuado, URI URN y detalle legible.
6. **Desacoplamiento de I/O**: Los protocolos marcados con `@runtime_checkable` (`FileSystemReader`, `FileSystemWriter`, `TelemetryPort`) permiten verificación dinámica de tipos en tiempo de ejecución para pruebas unitarias sin dependencias externas.

---

## Directrices de Seguridad

- **Protección de Secretos en Reposo**: Las claves API y tokens de integración nunca se representan como texto plano en DTOs persistibles; deben encapsularse obligatoriamente en `EncryptedSecret`.
- **Aislamiento de Identidad**: `current_user_id` es una `ContextVar` gestionada exclusivamente por los middlewares de autenticación. El dominio y los puertos nunca deben manipular manualmente esta variable.
- **Autorización por Scopes con Comodín**: `Principal.has_scope` evalúa privilegios granulares y concede acceso total ante el comodín `"*"` (reservado para administradores del sistema).
- **Consumo Atómico de Códigos PKCE**: `AuthorizationCodeStore` impone un contrato de eliminación inmediata tras la primera lectura para frustrar ataques de repetición (*replay attacks*).
