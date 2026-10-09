# `infrastructure/codegen/` — Workspaces, OpenCode Integration y Templates de Aplicación

## Responsabilidad y Propósito

Este módulo gestiona la infraestructura para la fase de **generación autónoma de código** (implementación) dentro del ecosistema KOSMO:

- **Ciclo de Vida de Workspaces Locales (`LocalWorkspaceManager`)**: Aprovisionamiento idempotente, scaffolding inicial sobre plantilla Next.js 16 + React 19 + Drizzle ORM + Bootstrap 5, control de concurrencia distribuido (bloqueo en memoria y CAS en base de datos), control de versiones Git local (checkpoints, commits, rollbacks deterministas) y administración de manifiestos.
- **Personalización Visual Contextual**: Análisis del UX Archetype desde el documento de Discovery (`saas_tool`, `storefront`, `dashboard`, `workflow`, `content`) para inyectar design tokens, paletas de color OKLCH y metadatos de proyecto en `src/lib/site.ts`.
- **Orquestación de Contenedores Efímeros OpenCode (`IsolatedOpenCodeClient`)**: Gestión de contenedores Docker aislados por usuario y tarea (*one-project, one-user ephemeral job*) con autenticación BYOK (OpenAI, Anthropic, Google, DeepSeek), heartbeat continuo, detección de saturación (HTTP 429), límites de memoria RAM (1 GiB) y monitoreo de terminación OOM (*Out Of Memory*).
- **Cliente HTTP y Streaming OpenCode (`OpenCodeHttpClient`)**: Adaptador HTTP sobre el daemon `opencode serve` que gestiona sesiones de trabajo, reintentos con backoff exponencial, validación estricta del catálogo de modelos y traducción bidireccional del streaming SSE/REST a eventos de dominio KOSMO (`OpenCodeEvent`).
- **Inyección de Skills y Reglas de Desarrollo**: Provisionamiento automático en cada workspace de 6 skills especializadas (`.opencode/skills/`), configuración headless en `opencode.json` con herramientas MCP (`kosmo-context`, `token-savior`, `context7`) y directrices estrictas de arquitectura en `AGENTS.md`.

---

## Estructura de Archivos y Componentes

```
infrastructure/codegen/
├── __init__.py                  # Reexporta símbolos públicos (Manager, Client, Errores)
├── workspace.py                 # LocalWorkspaceManager, LocalFileSystemReader/Writer, CAS locks
├── isolated_opencode.py         # IsolatedOpenCodeClient (orquestador de jobs efímeros, BYOK, OOM)
├── opencode_client.py           # OpenCodeHttpClient (comunicación HTTP con opencode serve, eventos)
└── templates/
    ├── workspace/
    │   └── AGENTS.md.tmpl       # Plantilla base inyectada en la raíz de cada workspace generado
    └── basic-next-app/          # Plantilla canónica de aplicación Next.js 16 + React 19
        ├── package.json         # Next.js 16, React 19, Drizzle ORM, better-sqlite3, Bootstrap 5, Vitest
        ├── tsconfig.json        # TypeScript estricto (strict: true), alias @/*
        ├── next.config.ts       # Configuración standalone con serverExternalPackages: [better-sqlite3]
        ├── Dockerfile           # Multi-stage production build con compilación nativa de sqlite3
        ├── eslint.config.mjs    # ESLint flat config con prohibición de any
        ├── vitest.config.ts     # Entorno Node, globals habilitados, alias de rutas
        ├── src/
        │   ├── app/             # App Router: layout.tsx, page.tsx, globals.css
        │   ├── components/      # Catálogo de 37 componentes UI Bootstrap 5
        │   │   ├── layout/      # AppShell, Navbar, Sidebar, Footer
        │   │   └── ui/          # Botones, Cards, Tablas, Modales, Drawers, etc.
        │   ├── db/              # SQLite + Drizzle ORM (schema.ts, index.ts con syncSchema)
        │   ├── domain/          # Entidades y tipos compartidos inter-feature
        │   ├── features/        # Slices verticales por feature y tipos
        │   └── lib/             # site.ts, design-tokens.ts, feature-registry.ts, utils.ts
        └── tests/               # Configuración setup.ts y suite de pruebas base
```

### Exportaciones Públicas (`__init__.py`)
- **Gestión de Workspaces**: `LocalWorkspaceManager`, `DEFAULT_TEMPLATE_DIR`, `WorkspaceLockedError`.
- **Cliente OpenCode**: `OpenCodeHttpClient`, `OpenCodeClientError`, `OpenCodeConnectionError`, `OpenCodeTimeoutError`, `OpenCodeSessionNotFoundError`, `OpenCodeAuthenticationError`.

---

## Gestión de Workspaces (`LocalWorkspaceManager`)

Implementado en [workspace.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/codegen/workspace.py), satisface los contratos `WorkspaceManagerPort`, `FileSystemReader` y `FileSystemWriter`.

### 1. Scaffolding Idempotente (`ensure_workspace`)
Cuando se solicita preparar o acceder a un workspace para un `ProjectId`:
1. **Resolución Segura de Ruta**: `_resolve_target_dir` valida que el directorio resida estrictamente dentro de `_workspaces_root` (`target_dir.is_relative_to(root_dir)` y `target_dir != root_dir`). Si escapa, lanza `ValueError`.
2. **Copia de Plantilla**: Si el directorio no existe físicamente, lo crea y clona el árbol completo de `templates/basic-next-app/` mediante `shutil.copytree(dirs_exist_ok=True)`.
3. **Detección Contextual de UX**:
   - Consulta `ProjectRepository` para obtener el nombre del proyecto.
   - Si `DocumentRepository` está disponible, consulta el documento de Discovery, lo convierte a markdown con `document_to_markdown` y clasifica el arquetipo UX (`classify_archetype`: `saas_tool`, `storefront`, `dashboard`, `workflow`, `content`).
   - Obtiene los tokens de diseño (`THEME_TOKENS_BY_ARCHETYPE`) y genera el archivo `src/lib/site.ts` personalizado mediante `format_site_config`.
4. **Inyección de `AGENTS.md`**: Renderiza `templates/workspace/AGENTS.md.tmpl` sustituyendo `{{PROJECT_NAME}}`.
5. **Generación y Normalización de `opencode.json`**:
   - Configura el plugin `@dietrichgebert/ponytail`.
   - Inyecta herramientas MCP: `kosmo-context` (con `KOSMO_PROJECT_ID`), `token-savior` (para navegación semántica de símbolos sin saturar tokens) y `context7` (para firmas de APIs de librerías).
   - Establece permisos restrictivos: `read: {"*": "allow"}`, `edit: {"*": "allow"}`, `bash: "deny"`, `external_directory: "deny"`, `websearch: "allow"`.
   - Desactiva preguntas interactivas: `tools.question: False` (garantiza ejecución autónoma *headless*).
6. **Auto-Reparación de Archivos Críticos de Despliegue**:
   - Comprueba y actualiza `Dockerfile` si faltan instrucciones de compilación nativa de `better-sqlite3` (`npm rebuild better-sqlite3`, `python3 make g++`).
   - Sincroniza `next.config.ts` asegurando `serverExternalPackages: ["better-sqlite3"]`.
   - Sincroniza `src/db/index.ts` asegurando la presencia de `syncSchema` y eliminando casts no seguros.
7. **Inyección de Skills**: Escribe las 6 skills en `.opencode/skills/<skill_name>/SKILL.md`.
8. **Inicialización de Git Local**: Ejecuta `git_init_async`, realiza el staging (`git_add_async`) y crea el commit inicial (`"chore: initialize workspace template and configurations"`).
9. **Preinstalación de Dependencias**: Si el workspace es nuevo y hay un `CodeRunnerPort` inyectado, ejecuta `npm install` (`INSTALL_COMMAND`) con timeout de `600s` (`INSTALL_TIMEOUT_SECONDS`) para que la primera iteración de desarrollo no consuma el tiempo del pipeline.
10. **Persistencia del Manifiesto**: Escanea el filesystem ignorando `_IGNORED_DIRS` y persiste la entidad `CodeWorkspace` en `WorkspaceRepository`.

### 2. Bloqueo Concurrente Híbrido (CAS + In-Memory)
- **`acquire_lock(project_id)`**:
  - Adquiere el guardián de coroutines `self._lock_guard` (`asyncio.Lock`).
  - Verifica si el proyecto ya está en el set de memoria `_in_memory_locks`; si es así, lanza `WorkspaceLockedError`.
  - Si hay repositorio de base de datos (`WorkspaceRepository`), ejecuta `update_lock(project_id, is_locked=True)`, el cual realiza un CAS (*Compare-And-Swap*) atómico a nivel SQL (`WHERE is_locked IS false OR locked_at < stale_cutoff`). Si retorna `None`, lanza `WorkspaceLockedError`.
  - Registra el `project_id` en `_in_memory_locks`.
- **`release_lock(project_id)`**:
  - Descarta el `project_id` de `_in_memory_locks` y llama a `workspace_repo.release_lock(project_id)`.

### 3. Operaciones de Modificación, Rollback y Reversión
- **`rollback_workspace(project_id)`**: Ejecuta `git_rollback_async`, restaurando el working tree al último commit válido y eliminando archivos no rastreados con `git clean -fd`. Actualiza el manifiesto en base de datos.
- **`commit_workspace(project_id, message) -> str | None`**: Añade cambios al staging, ejecuta `git_commit_async` y retorna el hash HEAD resultante (o `None` si no hubo cambios).
- **`remove_feature_paths(project_id, slug) -> tuple[str, ...]`**: Elimina de forma quirúrgica los directorios (`src/features/<slug>/`, `src/app/<slug>/`) y archivos (`tests/<slug>.test.*`, `src/<slug>.ts`). Regla estricta: coincide únicamente con directorios con nombre exacto o archivos con prefijo `<slug>.`, **evitando borrar accidentalmente features hermanas** con nombres más largos (ej. borrar `producto` no afecta a `producto-detalle`).
- **`update_text_file(project_id, relative_path, transform)`**: Aplica una función de transformación `transform(content: str) -> str` en memoria y sobreescribe el archivo atómicamente si el contenido mutó.
- **`revert_commit(project_id, commit)`**: Invoca `git_revert_commit_async` de forma best-effort para deshacer un commit puntual sin reescribir la historia posterior.
- **`delete_workspace(project_id)`**: Elimina recursivamente el directorio del workspace con hasta 4 reintentos y esperas de `0.3s` para lidiar con bloqueos transitorios de archivos en sistemas Windows.

---

## Orquestación de OpenCode Aislado (`IsolatedOpenCodeClient`)

Implementado en [isolated_opencode.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/codegen/isolated_opencode.py).

### Arquitectura de Ejecución Efímera
Gestiona trabajos en contenedores efímeros creados a través de un servicio externo (*Launcher*):

1. **Resolución de Credenciales BYOK (`_credentials`)**:
   - Lee el `current_user_id` del `ContextVar`.
   - Consulta `UserAiConfigRepository` para extraer proveedor (`AIProvider.OPENAI`, `ANTHROPIC`, `GOOGLE`, `DEEPSEEK`), modelo y API key cifrada.
   - Descifra la clave mediante `SecretCipher.decrypt`. Si el usuario no tiene credenciales válidas, lanza `UserCodegenConfigError(ValueError)` impidiendo iniciar el trabajo.
2. **Ciclo de Vida del Trabajo (`start_job`)**:
   - Valida que no exista un trabajo activo en la coroutine (`_active ContextVar`).
   - Envía `POST /jobs` al launcher con `{project_id, provider, model, api_key}`.
   - **Gestión de Saturación (HTTP 429)**: Realiza hasta 60 reintentos espaciados cada 5 segundos (hasta 5 minutos de tolerancia) si el launcher está saturado antes de fallar.
   - **Heartbeat en Background**: Lanza una tarea asíncrona que emite `POST /jobs/{job_id}/heartbeat` cada 20 segundos para evitar que el launcher considere zombi el contenedor.
   - **Sondeo de Readiness (Readiness Polling)**: Sondea hasta 60 veces con pausas de 2 segundos invocando `health_check()` y `validate_model()`.
   - **Detección Temprana de Fallos y OOM**:
     - Si `state.get("oom_killed")` es verdadero: Lanza `UserCodegenConfigError("OpenCode superó el máximo de 1 GiB de RAM al iniciar.")`.
     - Si el estado es `"exited"`: Lanza `RuntimeError("OpenCode terminó inesperadamente antes de iniciar.")`.
   - Al estar listo, almacena la tupla `(job_id, client, heartbeat)` en el `ContextVar`.
3. **Monitoreo de OOM durante Streaming (`send_prompt`)**:
   - Durante la generación de código, si OpenCode emite un evento de tipo `ERROR`, consulta el estado en el launcher (`GET /jobs/{job_id}`). Si el contenedor fue liquidado por el kernel por OOM (`oom_killed`), reemplaza el error con el mensaje:
     `"OpenCode superó el máximo de 1 GiB de RAM. Reduce el contexto del proyecto."`.
4. **Liberación de Recursos (`stop_job`)**:
   - Cancela la tarea de heartbeat, cierra el cliente HTTP y envía `DELETE /jobs/{job_id}` al launcher.

---

## Cliente HTTP OpenCode (`OpenCodeHttpClient`)

Implementado en [opencode_client.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/codegen/opencode_client.py), implementa el puerto `OpenCodeClientPort`.

### 1. Conectividad y Autenticación
- **URL Base por defecto**: `http://127.0.0.1:4096`.
- **Autenticación**: Cabecera `Authorization: Basic <base64(user:password)>`.
- **Timeouts**: Total `900.0s` (15 minutos), Conexión `30.0s`, Lectura `900.0s`, Escritura `60.0s`.

### 2. Validación de Catálogo de Modelos (`validate_model`)
- Consulta `GET /provider` con timeout de `30s`.
- Inspecciona la estructura de proveedores soportados por la versión de OpenCode.
- Verifica que el modelo BYOK del usuario exista dentro del diccionario `models` del proveedor configurado. Si no existe, lanza `OpenCodeClientError` indicando que el modelo no está soportado.

### 3. Creación de Sesiones con Reintentos (`create_session`)
- Envía `POST /session?directory={workspace_dir}` con payload `{"title": title}`.
- Aplica reintentos mediante `tenacity`:
  - Captura `httpx.ConnectError` y `httpx.TransportError`.
  - Hasta 3 intentos con retroceso exponencial (`multiplier=1, min=1, max=4`).
- Retorna la entidad de dominio `OpenCodeSession(session_id, workspace_dir, title, created_at)`.

### 4. Streaming y Mapeo de Eventos (`send_prompt`)
Envía la instrucción a `POST /session/{session_id}/message` con `{parts: [{"type": "text", "text": prompt}], agent: agent, model: ...}` y traduce el mensaje en un flujo de eventos tipados `OpenCodeEvent`:

| Parte en Respuesta OpenCode (`part.type`) | Evento KOSMO (`OpenCodeEventType`) | Carga Útil (`data`) |
|:---|:---|:---|
| `"thought"`, `"reasoning"` | `PLAN_PROGRESS` o `BUILD_PROGRESS` | `{"thought": str, "stage": "thinking"}` |
| `"text"` | `PLAN_PROGRESS` o `BUILD_PROGRESS` | `{"delta": str, "stage": "writing"}` |
| `"tool"`, `"tool-call"`, `"tool_invocation"` | `PLAN_PROGRESS` o `BUILD_PROGRESS` | `{"delta": str, "tool": str, "stage": "tool", "detail": str}` |
| Herramienta de archivo (`write`, `edit`, `patch`, `create_file`, etc.) | `FILE_EDIT` | `{"path": str, "content": str}` |
| `"file"` | `FILE_EDIT` | `{"path": str, "content": str}` |
| Finalización del mensaje | `PLAN_COMPLETE` o `BUILD_COMPLETE` | `{"files": list[str]}` |
| Fallo HTTP, timeout o error reportado | `ERROR` | `{"error": str, "timeout": bool, ...}` |

---

## Skills Inyectadas en el Workspace (`.opencode/skills/`)

Cada workspace aprovisionado incluye 6 skills especializadas que orientan al modelo de lenguaje durante la codificación:

| Nombre de Skill | Función Generadora | Enfoque y Restricciones Técnicas |
|:---|:---|:---|
| `kosmo-implementation` | `_generate_implementation_skill_md` | Arquitectura limpia (Presentation → Domain → DB), TypeScript estricto, cero mocks en runtime. |
| `kosmo-testing` | `_generate_testing_skill_md` | Pruebas con Vitest, patrón AAA (Arrange-Act-Assert), cobertura obligatoria de happy path y error path. |
| `tdd` | `_generate_tdd_skill_md` | Ciclo formal Red-Green-Refactor en 8 pasos: test que falla → código mínimo → refactorización. |
| `kosmo-drizzle` | `_generate_drizzle_skill_md` | Drizzle ORM sobre SQLite (`better-sqlite3`), tipado de esquemas, Server Actions y `revalidatePath`. |
| `kosmo-nextjs` | `_generate_nextjs_skill_md` | Next.js 16 App Router, React 19, Server Components por defecto, `'use client'` restringido. |
| `kosmo-ui` | `_generate_ui_skill_md` | Catálogo de 37 componentes UI Bootstrap 5, diseño responsivo, **prohibición total de Tailwind CSS**. |

---

## Constantes y Valores Clave

| Constante / Parámetro | Valor por Defecto | Archivo | Propósito |
|:---|:---|:---|:---|
| `DEFAULT_TEMPLATE_DIR` | `templates/basic-next-app` | `workspace.py` | Ruta base de la plantilla de aplicación |
| `_IGNORED_DIRS` | `.git`, `node_modules`, `.next`, `dist`, `build`, etc. | `workspace.py` | Directorios excluidos del manifiesto de archivos |
| `INSTALL_COMMAND` | `"npm install"` | `workspace.py` | Comando para preinstalar dependencias al crear el workspace |
| `INSTALL_TIMEOUT_SECONDS` | `600s` (10 min) | `workspace.py` | Timeout para la preinstalación inicial de dependencias |
| Reintentos borrado workspace | 4 intentos × 0.3s backoff | `workspace.py` | Superar bloqueos transitorios de archivos en Windows |
| Launcher saturado retries | 60 intentos × 5s (5 min) | `isolated_opencode.py` | Tolerancia ante cola de lanzador lleno |
| Launcher heartbeat interval | `20s` | `isolated_opencode.py` | Frecuencia de latido para mantener vivo el contenedor |
| Límite de memoria RAM OpenCode | `1 GiB` | `isolated_opencode.py` | Límite del contenedor antes de OOM-kill |
| Timeout total OpenCode | `900s` (15 min) | `opencode_client.py` | Tiempo límite de ejecución de un prompt |
| Reintentos creación sesión | 3 intentos (backoff 1-4s) | `opencode_client.py` | Resiliencia ante caídas breves de red |

---

## Matriz de Contratos Implementados

| Puerto Abstracto (`contracts/`) | Clase / Adaptador Concreto | Archivo de Implementación |
|:---|:---|:---|
| `kosmo.contracts.sdd.codegen.WorkspaceManagerPort` | `LocalWorkspaceManager` | [workspace.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/codegen/workspace.py) |
| `kosmo.contracts.sdd.codegen.FileSystemReader` | `LocalFileSystemReader`, `LocalWorkspaceManager` | [workspace.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/codegen/workspace.py) |
| `kosmo.contracts.sdd.codegen.FileSystemWriter` | `LocalFileSystemWriter`, `LocalWorkspaceManager` | [workspace.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/codegen/workspace.py) |
| `kosmo.contracts.sdd.codegen.OpenCodeClientPort` | `OpenCodeHttpClient`, `IsolatedOpenCodeClient` | [opencode_client.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/codegen/opencode_client.py), [isolated_opencode.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/codegen/isolated_opencode.py) |

---

## Reglas de Implementación y Mantenimiento

1. **Idempotencia de `ensure_workspace`**: Si un workspace ya existe en disco, no sobreescribe código de features previas. Solo sincroniza configuraciones esenciales (`site.ts`, `opencode.json`, `Dockerfile` y skills).
2. **Cero persistencia de API keys en disco**: Las claves BYOK descifradas solo viven en memoria durante la invocación HTTP a OpenCode o al Launcher; nunca se escriben en archivos de texto, `.env` ni `opencode.json`.
3. **Doble verificación de borrado en `remove_feature_paths`**: Al eliminar una característica descartada, la coincidencia debe exigir delimitación estricta por puntos o igualdad de directorio para jamás afectar features con nombres derivados.
4. **Desconexión headless**: En `opencode.json`, `tools.question: False` es mandatorio. Si se habilita, el agente intentará solicitar interacción al usuario y bloqueará indefinidamente el proceso de backend.
5. **Aislamiento en `IsolatedOpenCodeClient`**: Utilizar siempre variables de contexto (`contextvars`) para almacenar el trabajo activo de OpenCode, garantizando que coroutines concurrentes no interfieran entre sí.

---

## Directrices de Seguridad Críticas

- **Defensa contra Directory Traversal**: `_resolve_target_dir` valida con `Path.resolve()` y `is_relative_to` que el proyecto resida estrictamente bajo `_workspaces_root`. Cualquier intento de escape lanza `ValueError`.
- **Restricción de Permisos en OpenCode**: `opencode.json` deniega terminantemente `bash` y `external_directory`. El agente de generación no puede ejecutar comandos directos ni acceder a directorios fuera de su workspace asignado.
- **Validación Criptográfica previa**: `validate_user_config()` asegura que el usuario cuente con proveedor y clave API válidos antes de crear o alterar cualquier archivo en el workspace.
