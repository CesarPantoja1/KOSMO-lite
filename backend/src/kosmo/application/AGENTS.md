# `application/` — Capa de Aplicación: Casos de Uso y Orquestación Hexagonal

## Responsabilidad y Propósito

La capa `application/` alberga la totalidad de los casos de uso del backend de KOSMO. Actúa como el orquestador principal en la arquitectura hexagonal (Capa 3): coordina la interacción entre la lógica pura de dominio (`domain/`), las estructuras y puertos abstractos (`contracts/`) y los adaptadores tecnológicos (`infrastructure/`).

Responsabilidades principales:
- **Orquestación del Agente KOSMO (`pipeline/`)**: Ejecución iterativa de habilidades del pipeline SDD con control de bucle de reintentos, validación post-generación, streaming SSE y registro persistente de memoria con embeddings vectoriales.
- **Pipeline Autónomo de Generación de Código (`codegen/`)**: Orquestación de extremo a extremo para features (análisis UX, disposición de integración, bloqueo exclusivo CAS de workspace, sesiones efímeras con OpenCode en contenedor, planificación, construcción, validación mediante compilador/linter/tests y post-despliegue con trazabilidad).
- **Cascada de Consistencia Downstream (`consistency/`)**: Evaluación de impacto entre fases siguiendo la regla unidireccional canónica (`DESCUBRIMIENTO` → `CARACTERISTICAS` → `REQUISITOS` → `MODELO` → `IMPLEMENTACION`), verificación de frescura mediante snapshot hashes SHA-256 y aplicación atómica de correcciones.
- **Canal Conversacional y Modificación Directa (`chat/`)**: Procesamiento de mensajes de chat con truncamiento adaptativo de historial, sanitización anti-inyección, guardia de upstream y aplicación quirúrgica de diffs.
- **Autenticación, Sesiones y Seguridad (`auth/`)**: Registro de usuarios con hashing Argon2id, autorización OAuth2 con PKCE (S256), emisión/renovación de tokens JWT (RS256) con detección de reuso de refresh tokens y revocación en cascada de familias.
- **Gestión del Ciclo de Vida de Especificaciones**: Casos de uso especializados para cada fase SDD: Descubrimiento (`discovery/`), Características (`features/`), Requisitos EARS (`requirements/`) y Modelado PlantUML (`modelo/`).
- **Integraciones Cloud y Git (`integrations/`)**: Sincronización bidireccional con repositorios de GitHub, orquestación y monitoreo de despliegues en Railway, y ejecución efímera en sandboxes aislados.
- **Gestión de Proyectos y Trazabilidad (`projects/`, `traceability/`, `knowledge/`, `ai/`)**: CRUD de proyectos con cascada integral de borrado, navegación del grafo de dependencias, consolidación de patrones aprendidos y configuración de credenciales de IA por usuario (BYOK).

> **Aislamiento Hexagonal**: Ningún caso de uso en `application/` accede de forma directa a la base de datos, sistemas de archivos o clientes de red. Toda operación con el exterior se efectúa mediante inyección de dependencias a través de los puertos definidos en `contracts/`.

---

## Estructura de Archivos y Componentes (14 Subdominios)

```
application/
├── pipeline/                            # Orquestador central del agente multi-skill (KOSMOAgent)
│   ├── kosmo_agent.py                   # Implementación de AgentPort: generación, chat, streaming y diffs
│   ├── context_builder.py               # Fábrica de contextos tipados para cada fase
│   ├── generation_loop.py               # Bucle de reintentos con validación y captura de retroalimentación
│   ├── prompt_enricher.py               # Inyección de few-shot examples y preferencias de usuario
│   ├── session_recorder.py              # Grabación asíncrona de sesiones con embeddings vectoriales
│   └── tool_resolver.py                 # Resolución de herramientas de contexto del KnowledgeToolRegistry
├── codegen/                             # Pipeline de implementación autónoma de código
│   ├── generate_feature_implementation.py # Orquestador maestro del flujo de codegen
│   ├── planning_service.py              # Generación y validación de planes de implementación
│   ├── build_service.py                 # Ejecución de edición de código con el agente build de OpenCode
│   ├── validation_service.py            # Ejecución del pipeline de verificación (tsc, eslint, vitest, build)
│   ├── post_deploy_service.py           # Commit en git, actualización de estado y trazabilidad
│   ├── analyze_ux_context.py            # Detección de arquetipo visual, paleta OKLCH y diseño de interfaz
│   ├── analyze_feature_integration.py   # Asignación de disposición de integración (Jaccard > 0.35)
│   ├── delete_feature_code.py           # Reversión de código de feature en el workspace
│   ├── implementation_context_builder.py# Construcción de contexto de entrada para OpenCode
│   ├── get_implementation_record.py     # Consulta de estado de implementación
│   ├── recover_zombie_implementations.py# Recuperación de implementaciones interrumpidas
│   ├── register_code_traceability.py    # Registro de aristas de trazabilidad para código fuente
│   └── validate_workspace.py            # Validación estructural del workspace
├── consistency/                         # Evaluación y aplicación de consistencia downstream
│   ├── evaluate_consistency.py          # Caso de uso principal de evaluación downstream
│   ├── run_consistency_evaluation.py    # Ejecución de evaluación aislada con pre-filtrado
│   ├── apply_consistency_impacts.py     # Aplicación de diffs sobre artefactos afectados
│   ├── cascade_consistency.py           # Propagación en cascada a través de DOWNSTREAM_TARGETS
│   ├── consistency_snapshot.py          # Cálculo de hash SHA-256 para verificación de frescura
│   ├── enrich_impact.py                 # Enriquecimiento del reporte de impacto con entidades afectadas
│   ├── evaluate_project_consistency.py  # Barrido de consistencia para todo el proyecto
│   ├── manage_consistency.py            # Consulta y actualización de estados de evaluación
│   └── trigger_downstream.py            # Disparador de eventos downstream ante modificaciones
├── chat/                                # Mensajería conversacional del pipeline
│   ├── process_chat_message.py          # Procesamiento de mensaje con guardia upstream y chat SSE
│   ├── process_chat_modification.py     # Modificación directa de documentos vía chat
│   ├── chat_sessions.py                 # Gestión del ciclo de vida de sesiones de chat
│   └── validate_phase_context.py        # Validación de coherencia de fase conversacional
├── auth/                                # Autenticación, tokens y PKCE
│   ├── register.py                      # Registro de nuevos usuarios con hashing Argon2id
│   ├── authorize.py                     # Emisión de código de autorización PKCE (S256)
│   ├── exchange.py                      # Intercambio de código PKCE por par de tokens JWT
│   └── use_cases.py                     # Login, refresco con rotación y grace period, logout, perfil
├── discovery/                           # Gestión y ciclo de vida de Descubrimiento
│   ├── generate_discovery.py            # Generación inicial del documento de Descubrimiento
│   ├── refine_discovery.py              # Refinamiento quirúrgico por instrucción
│   ├── regenerate_discovery.py          # Regeneración completa del documento
│   ├── revert_document.py               # Reversión a versión histórica en document_versions
│   ├── get_discovery.py                 # Consulta y deserialización AST
│   ├── save_discovery.py                # Serialización y persistencia con versionado
│   └── get_discovery_chat_history.py    # Historial de conversación de la fase
├── features/                            # Ciclo de vida de Características
│   ├── generate_features.py             # Generación de lote inicial (5) o incremental
│   ├── create_characteristic.py         # Creación manual de característica
│   ├── edit_feature.py                  # Edición de título, descripción u origen
│   ├── delete_feature.py                # Eliminación en cascada de feature y artefactos asociados
│   ├── list_features.py                 # Listado de características por proyecto
│   ├── save_features.py                 # Persistencia en lote
│   ├── check_feature_consistency.py     # Validación de consistencia de características
│   └── get_feature_chat_history.py      # Historial de chat por característica
├── requirements/                        # Requisitos de software EARS
│   ├── generate_ears.py                 # Generación de requisitos EARS para una característica
│   ├── refine_requirements.py           # Refinamiento de requisitos existentes
│   ├── regenerate_requirements.py       # Regeneración completa de requisitos
│   ├── delete_requirements.py           # Eliminación de requisitos de una característica
│   ├── save_requirements.py             # Guardado y serialización Markdown
│   └── get_requirement_chat_history.py  # Historial de chat de requisitos
├── modelo/                              # Diagramas de actividad PlantUML
│   ├── generate_diagram.py              # Generación de diagrama con swimlanes
│   ├── get_diagram.py                   # Consulta de diagrama por característica
│   └── delete_diagram.py                # Eliminación de diagrama
├── integrations/                        # Servicios cloud y control de versiones
│   ├── link_github_account.py           # Vinculación OAuth2 de cuenta de GitHub
│   ├── sync_github_repository.py        # Creación de repo remoto y push de commits
│   ├── delete_github_repository.py      # Desvinculación de repositorio remoto
│   ├── link_deployment_provider.py      # Conexión de cuenta Railway
│   ├── orchestrate_cloud_deployment.py  # Despliegue de proyecto en Railway
│   ├── monitor_deployment_status.py     # Sondeo periódico de estado de despliegue
│   ├── handle_deployment_failure.py     # Manejo de fallos y reintentos de despliegue
│   ├── recover_pending_deployments.py   # Recuperación de despliegues huérfanos al inicio
│   ├── delete_deployment.py             # Eliminación de servicio en la nube
│   └── execute_ephemeral_validation.py  # Validación en contenedor Docker efímero
├── knowledge/                           # Consolidación de conocimiento
│   └── consolidate_patterns.py          # Consolidación de patrones aprendidos por fase
├── projects/                            # Ciclo de vida de Proyectos
│   ├── create_project.py                # Creación de proyecto con slug único
│   ├── get_project.py                   # Búsqueda por identificador o slug
│   ├── list_projects.py                 # Listado de proyectos del usuario autenticado
│   └── delete_project.py                # Eliminación en cascada completa del proyecto
├── traceability/                        # Grafo de trazabilidad
│   └── manage_traceability_navigation.py# Navegación del grafo y consulta de dependencias
└── ai/                                  # Configuración de IA por usuario (BYOK)
    ├── manage_ai_preferences.py         # Registro y cifrado de credenciales de IA
    └── validate_ai_connection.py        # Prueba de conectividad con el proveedor de IA
```

---

## Descripción Detallada por Subdominio

### 1. `pipeline/` — Orquestación Central del Agente KOSMO

- **`kosmo_agent.py` (`KOSMOAgent`, implementa `AgentPort`)**:
  - `execute_with_skill(skill_name, context, *, project_id, user_instructions)`: Resuelve el `Skill` en el `SkillRegistry`, enriquece los prompts con `PromptEnricher`, ejecuta el bucle de generación `execute_generation_loop` con reintentos automáticos (hasta `max_iterations = 8`), valida la respuesta tipada del LLM y delega a `SessionRecorder` para registrar la sesión con vector de embedding en `AgentMemoryPort`.
  - `execute_conversation(skill_name, messages, context, *, project_id)`: Ejecuta una interacción conversacional truncando el historial de mensajes a un máximo de `_MAX_HISTORY_TOKENS = 6000` tokens y `_MAX_HISTORY_WINDOW = 20` mensajes para no saturar el contexto.
  - `execute_conversation_stream(skill_name, messages, context, *, project_id)`: Variante generadora asíncrona para streaming SSE hacia el frontend.
  - `execute_direct_modification(skill_name, context, *, history, project_id)`: Aplica ediciones directas sobre especificaciones sin atravesar la fase de sugerencias intermedias.
- **`generation_loop.py`**: Gestiona la interacción con `LLMClient.complete_typed()`, invocando `mode.validate_output()`. Si se detectan violaciones, invoca `mode.build_retry_prompt()` incorporando los errores detallados para guiar la corrección del modelo.
- **`context_builder.py`**: Construye de manera determinista los 12 DTOs de contexto tipados (`DiscoveryPhaseContext`, `FeaturesPhaseContext`, etc.) leyendo los artefactos requeridos desde los repositorios correspondientes.

### 2. `codegen/` — Pipeline de Implementación Autónoma de Código

- **`generate_feature_implementation.py`**:
  1. **Precondición**: Valida que la feature posea requisitos EARS generados y aprobados.
  2. **Bloqueo exclusivo de Workspace**: Invoca `WorkspaceManagerPort.acquire_lock` (bloqueo en memoria + CAS en base de datos).
  3. **Análisis de UX y Disposición**: Ejecuta `analyze_ux_context` (determina `UXContext`, paleta OKLCH y diseño Bootstrap 5) y `analyze_feature_integration` (calcula solapamiento Jaccard > 0.35 contra features previas para fijar disposición: `CREATE`, `EXTEND`, `INTEGRATE`, `COMPOSE` o `SKIP`).
  4. **Sesión OpenCode**: Inicializa sesión en contenedor efímero aislado con límite de 1 GiB de RAM.
  5. **Fase de Planificación (`planning_service.py`)**: Solicita un `ImplementationPlan` al agente `plan` de OpenCode. Valida que las operaciones no vulneren `PROTECTED_WORKSPACE_FILES` (15 archivos protegidos) ni intenten directory traversal.
  6. **Fase de Construcción (`build_service.py`)**: Envía el plan al agente `build` de OpenCode para emitir archivos y parches en el workspace.
  7. **Fase de Validación (`validation_service.py`)**: Ejecuta el pipeline de 4 pasos:
     `typecheck (tsc) → lint (eslint) → tests (vitest) → build (next)`
     Si se detectan errores, extrae directivas de corrección priorizadas y reintenta el ciclo build/validation hasta `max_attempts = 3`.
  8. **Post-despliegue (`post_deploy_service.py`)**: Realiza commit atómico en Git, actualiza el estado a `IMPLEMENTED` y registra aristas en el grafo de trazabilidad (`register_code_traceability`).
  9. **Liberación**: Garantiza la liberación del bloqueo del workspace en el bloque `finally`.
- **`recover_zombie_implementations.py`**: Tarea de mantenimiento que detecta implementaciones marcadas como `IN_PROGRESS` cuyo heartbeat haya expirado (> 90s) y las marca como `FAILED` para evitar bloqueos perpetuos.

### 3. `consistency/` — Cascada de Consistencia Downstream

- **`evaluate_consistency.py` & `run_consistency_evaluation.py`**:
  - Lee los cambios aplicados en la fase fuente.
  - Computa `snapshot_hash` (digest SHA-256) sobre el estado actual de los artefactos.
  - Pre-filtra artefactos dependientes mediante `consistency_filter.filter_downstream_artifacts` para optimizar el contexto.
  - Invoca el skill correspondiente de `DOWNSTREAM_TARGETS` vía `KOSMOAgent`.
  - Persiste la evaluación en `ConsistencyEvaluationRepository` con estado `PENDING`.
- **`apply_consistency_impacts.py`**:
  - Verifica la frescura de la evaluación: si el hash actual del documento no coincide con el `snapshot_hash` almacenado, arroja `StaleEvaluationError`.
  - Aplica quirúrgicamente los diffs sobre el documento, característica, requisito o diagrama downstream.
  - Guarda una nueva versión inmutable en `document_versions` y marca la evaluación como `APPLIED`.
- **`cascade_consistency.py`**: Propaga en cadena las evaluaciones automáticas a lo largo de todo el grafo downstream permitido.

### 4. `chat/` — Mensajería Conversacional y Modificación Directa

- **`process_chat_message.py`**:
  - Sanitiza el mensaje mediante `sanitize_user_instructions` (rechaza inyecciones de prompt de 31 patrones).
  - Valida la existencia del documento upstream (trazabilidad de izquierda a derecha).
  - Invoca `KOSMOAgent.execute_conversation` (o versión streaming) con el skill de chat de la fase.
  - Persiste los mensajes en `chat_messages` y actualiza la sesión en `chat_sessions`.
- **`process_chat_modification.py`**: Aplica directamente las sugerencias aprobadas (`diff_before` → `diff_after`) sobre el documento activo.

### 5. `auth/` — Autenticación, Tokens y PKCE

- **`register.py`**: Crea el usuario con hash Argon2id (64 MB de memoria, 3 iteraciones, 4 hilos de paralelismo) y registra el evento en auditoría.
- **`authorize.py`**: Genera un `AuthorizationCode` criptográfico asociado al `code_challenge` (S256) con TTL estricto en Redis.
- **`exchange.py`**: Verifica el `code_verifier` mediante PKCE S256, consume el código de autorización de forma atómica (un solo uso) y emite un `TokenPair` (access token RS256 de 15m + refresh token de 7d).
- **`use_cases.py`**:
  - `login`: Valida credenciales contra tasa de intentos (`LoginAttemptStore`: máx. 10 fallos en ventana de 15 minutos).
  - `refresh`: Implementa rotación estricta de refresh tokens con período de gracia de 30s. Si se detecta un token ya consumido fuera de gracia, revoca inmediatamente toda la familia de tokens (RFC 6819).
  - `logout`: Revoca el identificador JTI del token de acceso y la familia de refresh tokens en Redis.

### 6. `discovery/` — Ciclo de Vida de Descubrimiento

- Casos de uso de generación inicial (`generate_discovery.py`), refinamiento quirúrgico (`refine_discovery.py`), regeneración integral (`regenerate_discovery.py`), persistencia tipada con AST (`save_discovery.py`), lectura (`get_discovery.py`) y reversión a versiones previas (`revert_document.py`).

### 7. `features/` — Ciclo de Vida de Características

- Casos de uso para generación (`generate_features.py`), creación individual (`create_characteristic.py`), edición (`edit_feature.py`), listado (`list_features.py`) y eliminación en cascada (`delete_feature.py`), la cual elimina de forma coordinada los requisitos EARS, diagramas de actividad e implementaciones ligadas.

### 8. `requirements/` — Requisitos de Software EARS

- Generación automatizada de 3 a 15 requisitos en notación EARS (`generate_ears.py`), refinamiento iterativo (`refine_requirements.py`), regeneración (`regenerate_requirements.py`), persistencia en Markdown con criterios BDD (`save_requirements.py`) y eliminación (`delete_requirements.py`).

### 9. `modelo/` — Diagramas de Actividad PlantUML

- Generación de diagramas de actividad estructurados por carriles/swimlanes (`generate_diagram.py`), lectura estructurada (`get_diagram.py`) y eliminación (`delete_diagram.py`).

### 10. `integrations/` — Servicios Cloud y Control de Versiones

- Vinculación OAuth2 con GitHub (`link_github_account.py`), sincronización de código y creación de repositorios remotos (`sync_github_repository.py`), orquestación de despliegues en Railway (`orchestrate_cloud_deployment.py`, `monitor_deployment_status.py`, `handle_deployment_failure.py`) y ejecución de pruebas en sandboxes aislados (`execute_ephemeral_validation.py`).
- Tarea de arranque `recover_pending_deployments.py`: Reconecta el monitoreo de despliegues en curso tras reiniciar el servidor.

### 11. `knowledge/` — Consolidación de Patrones

- `consolidate_patterns.py`: Analiza las reflexiones y resultados de sesiones exitosas en `AgentMemoryPort` y promueve patrones recurrentes a la tabla `knowledge_patterns` para orientar generaciones futuras.

### 12. `projects/` — Ciclo de Vida de Proyectos

- Creación (`create_project.py`), lectura (`get_project.py`), listado (`list_projects.py`) y eliminación en cascada completa (`delete_project.py`): remueve documentos de descubrimiento, características, requisitos, diagramas, implementaciones, historial de chat, sesiones de memoria, workspaces en disco y registros del outbox.

### 13. `traceability/` — Grafo de Trazabilidad

- `manage_traceability_navigation.py`: Consulta aristas en `traceability_edges` para calcular dependencias upstream/downstream entre artefactos del sistema.

### 14. `ai/` — Preferencias de IA por Usuario (BYOK)

- `manage_ai_preferences.py`: Cifra claves API de proveedores externos (OpenAI, Anthropic, Google, DeepSeek) con Fernet AES-128-CBC antes de almacenarlas en `user_ai_configs`.
- `validate_ai_connection.py`: Verifica la validez de credenciales y conectividad contra la API del proveedor mediante `AIConnectionTester`.

---

## Constantes y Valores Clave

| Constante | Valor | Archivo | Propósito |
|:---|:---:|:---|:---|
| `max_iterations` (agente) | `8` | `pipeline/kosmo_agent.py` | Intentos máximos de inferencia con corrección de validación |
| `_MAX_HISTORY_TOKENS` | `6000` | `pipeline/kosmo_agent.py` | Límite de tokens en la ventana de historial conversacional |
| `_MAX_HISTORY_WINDOW` | `20` mensajes | `pipeline/kosmo_agent.py` | Cantidad máxima de mensajes previos incluidos en el prompt |
| `max_attempts` (codegen) | `3` | `codegen/generate_feature_implementation.py` | Reintentos de build ante fallos en tsc/eslint/vitest/next |
| Umbral Jaccard integración | `0.35` | `codegen/analyze_feature_integration.py` | Solapamiento de capacidades para determinar disposición |
| Límite RAM OpenCode | `1 GiB` | `codegen/generate_feature_implementation.py` | Límite estricto de memoria en contenedor efímero |
| Heartbeat TTL zombie | `90s` | `codegen/recover_zombie_implementations.py` | Tiempo antes de clasificar una implementación como zombi |
| Login lockout max failures | `10` | `auth/use_cases.py` | Fallos de autenticación antes de bloqueo de cuenta |
| Login lockout window | `900s` (15 min) | `auth/use_cases.py` | Ventana deslizante para conteo de fallos de login |
| Access Token TTL | `900s` (15 min) | `auth/use_cases.py` | Duración del token de acceso RS256 |
| Refresh Token TTL | `604800s` (7 días) | `auth/use_cases.py` | Duración del token de refresco |
| Grace period rotación | `30s` | `auth/use_cases.py` | Ventana de tolerancia para refresh tokens concurrentes |

---

## Reglas de Implementación y Mantenimiento

1. **Uso Exclusivo de Puertos**: Los casos de uso nunca deben importar módulos de `infrastructure/`. La inyección de dependencias se realiza exclusivamente a través de los puertos de `contracts/`.
2. **Invocación Unificada de IA**: Toda llamada a modelos de lenguaje para el pipeline SDD debe transitar a través de `KOSMOAgent` (`pipeline/kosmo_agent.py`). No instanciar `LLMClient` directamente en use cases de fase.
3. **Bloqueo Mandatorio de Workspace**: Cualquier proceso de modificación de código en el workspace debe estar protegido por `acquire_lock` y `release_lock` de `WorkspaceManagerPort` en un bloque `try...finally`.
4. **Validación de Frescura en Consistencia**: Al aplicar sugerencias de consistencia, es imperativo comparar el `snapshot_hash` contra el estado actual del documento fuente para impedir inconsistencias debidas a modificaciones concurrentes.
5. **Sanitización de Entradas en el Límite de Confianza**: Las instrucciones ingresadas por usuarios deben pasar por `sanitize_user_instructions` antes de ser incorporadas a los prompts del sistema.
6. **Manejo No Bloqueante de Auditoría**: El registro de eventos en `AuditEventSink` no debe interferir con la transacción de negocio principal ante errores de infraestructura.

---

## Directrices de Seguridad

- **Mitigación contra Prompt Injection**: `sanitize_user_instructions` actúa como cortafuegos preventivo evaluando 31 expresiones de inyección y limitando el tamaño del texto a 2000 caracteres.
- **Protección de Archivos Sensibles en Workspaces**: `PROTECTED_WORKSPACE_FILES` (15 archivos de configuración y base) no pueden ser modificados ni eliminados por el agente de generación de código.
- **Defensa contra Reuso de Refresh Tokens**: La rotación estricta de tokens con detección de reuso de RFC 6819 revoca de inmediato la totalidad de la cadena de tokens si un refresh token consumido vuelve a presentarse fuera del período de gracia.
- **Cifrado de Secretos BYOK**: Las credenciales de proveedores de IA externas y tokens de integración se almacenan cifradas con Fernet (AES-128-CBC + HMAC-SHA256). Las claves descifradas viven únicamente en la memoria de trabajo efímera de la petición.
