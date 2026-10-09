# `infrastructure/sandbox/` — Runners de Validación y Aislamiento de Código

## Responsabilidad y Propósito

Este módulo implementa el entorno de ejecución segura (*sandbox*) para la validación estática, linting, ejecución de pruebas unitarias y compilación de los workspaces de código generado por KOSMO:

- **Ejecución Determinista de Pipelines de Calidad**: Orquesta los 4 pasos del ciclo de verificación de código (`TYPECHECK`, `LINT`, `TESTS`, `BUILD`) y la instalación previa de dependencias (`npm install`).
- **Tres Adaptadores Intercambiables**: Implementa el puerto `CodeRunnerPort` (definido en `contracts/sdd/codegen.py`) a través de tres estrategias según el entorno de despliegue:
  1. **`SubprocessCodeRunner`**: Ejecución local en subprocesos del sistema operativo, con lista blanca estricta de prefijos de comando (*command whitelist*), entorno de variables sanitizado (*clean env allowlist*), limitador de concurrencia mediante semáforo y terminación forzada del árbol de procesos.
  2. **`EphemeralDockerCodeRunner`**: Aislamiento en contenedores Docker efímeros creados al vuelo con nombres únicos basados en ULID, montaje de volúmenes (lectura/escritura o solo lectura) y destrucción automática (`--rm` y `docker rm -f` en timeout/cancelación).
  3. **`RemoteCodeRunner`**: Ejecución remota sobre un servicio HTTP aislado mediante empaquetado del workspace en tarballs comprimidos en memoria (base64 gzip), validación estricta de integridad de dependencias y actualización atómica del archivo `package-lock.json`.
- **Integración con Parsing de Dominio**: Delega la salida cruda de las herramientas (`tsc`, `eslint`, `vitest`, `next build`) a `kosmo.domain.codegen.parse_validation_output.parse_step_output` para estructurar diagnósticos con archivo, línea, columna, código de error y directivas de remediación.

---

## Estructura de Archivos y Componentes

```
infrastructure/sandbox/
├── __init__.py                 # Reexporta SubprocessCodeRunner, EphemeralDockerCodeRunner, RemoteCodeRunner y errores
├── code_runner.py              # Runner local sobre subprocesos (allowlists, semáforo, process tree kill)
├── docker_runner.py            # Runner en contenedores Docker efímeros (ULID, volumen montado, flag --rm)
└── remote_code_runner.py       # Runner HTTP remoto (tarball base64, verificación estricta de lockfile)
```

### Exportaciones Públicas (`__init__.py`)
- **Adaptadores**: `SubprocessCodeRunner`, `EphemeralDockerCodeRunner`, `RemoteCodeRunner`.
- **Excepciones**:
  - `UnallowedCommandError(ValueError)`: Lanzada cuando un comando no pertenece a la whitelist de prefijos permitidos.
  - `RemoteCodeRunnerError(RuntimeError)`: Lanzada ante fallos HTTP, respuestas inválidas o adulteración del manifiesto en el runner remoto.

---

## Descripción Detallada por Adaptador

### 1. `SubprocessCodeRunner` ([code_runner.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/sandbox/code_runner.py))

Ejecuta herramientas de desarrollo directamente sobre el sistema operativo anfitrión.

#### A. Whitelist de Comandos Permitidos (`DEFAULT_ALLOWED_COMMAND_PREFIXES`)
Para prevenir la inyección o ejecución de binarios arbitrarios (`curl`, `rm`, `bash`, `powershell`, etc.), valida que el ejecutable base pertenezca a la siguiente colección congelada:
`{"npm", "npx", "tsc", "eslint", "vitest", "next", "git", "drizzle-kit", "node", "pnpm", "yarn", "pytest", "python", "pyright", "ruff"}`.
- La validación tokeniza la línea de comandos mediante `shlex.split(posix=os.name != "nt")` e inspecciona tanto el token directo como su nombre base (`Path.stem`).
- Cualquier comando fuera de la lista lanza de forma inmediata `UnallowedCommandError`.
- Los argumentos se pasan como tupla de strings a `asyncio.create_subprocess_exec` sin invocar una shell (`shell=False`), neutralizando ataques con metacaracteres (`;`, `&&`, `|`, `` ` ``, `$()`).

#### B. Sanitización de Variables de Entorno (`SAFE_ENV_VARS`)
Aplica un filtro estricto insensible a mayúsculas/minúsculas sobre `os.environ` antes de pasarlo al subproceso:
- **Variables Permitidas**:
  - Rutas y binarios del sistema: `PATH`, `PATHEXT`, `SYSTEMROOT`, `WINDIR`, `COMSPEC`, `SYSTEMDRIVE`, `PROGRAMFILES`, `PROGRAMFILES(X86)`, `PROGRAMDATA`, `COMMONPROGRAMFILES`, `COMMONPROGRAMFILES(X86)`.
  - Directorios de usuario y caché: `HOME`, `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`.
  - Directorios temporales: `TEMP`, `TMP`, `TMPDIR`.
  - Runtime, localización y CI: `NODE_ENV`, `CI`, `LANG`, `LC_ALL`, `LC_CTYPE`, `TERM`.
  - Parámetros operativos KOSMO: `KOSMO_WORKSPACES_DIR`, `KOSMO_MAX_CONCURRENT_RUNNERS`.
- **Invariante Crítico**: Todos los secretos criptográficos (`FERNET_MASTER_KEY`, `JWT_PRIVATE_KEY_PEM`), cadenas de conexión a base de datos (`DATABASE_URL`, `REDIS_URL`) y claves API de proveedores de IA (`OPENAI_API_KEY`, `GEMINI_API_KEY`, etc.) son completamente excluidos del entorno hijo.

#### C. Control de Concurrencia y Telemetría
- **Semáforo Asíncrono**: `_runner_semaphore = asyncio.Semaphore(limit)`, donde `limit` se configura vía variable de entorno `KOSMO_MAX_CONCURRENT_RUNNERS` (valor por defecto: `4`).
- **Timeout de Cola**: Espera máxima en cola configurada mediante `KOSMO_RUNNER_QUEUE_TIMEOUT_SECONDS` (por defecto `180.0s`). Si se excede, retorna `ValidationStepResult` con `exit_code=-1` y mensaje descriptivo sin lanzar excepción.
- **Métricas Prometheus**: Incrementa `ACTIVE_CODE_RUNNERS.inc()` al iniciar y decrementa en bloque `finally` (`ACTIVE_CODE_RUNNERS.dec()`).

#### D. Terminación Forzada del Árbol de Procesos (`_kill_process_tree`)
Ante un timeout de ejecución:
- En **Windows** (`os.name == "nt"`): Ejecuta `taskkill /F /T /PID <proc.pid>` de forma silenciosa para liquidar tanto el proceso padre como todos los subprocesos descendientes (workers de Node.js, procesos de Vitest o esbuild).
- En **POSIX**: Ejecuta `proc.kill()`.
- Espera hasta `2.0s` adicionales para que el proceso termine ordenadamente.

---

### 2. `EphemeralDockerCodeRunner` ([docker_runner.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/sandbox/docker_runner.py))

Ejecuta el código en contenedores Docker efímeros para lograr aislamiento total a nivel de kernel.

#### Parámetros y Configuración
- **Imagen por defecto**: `kosmo-validator:latest` (configurable en constructor vía `image`).
- **Espacio de trabajo en contenedor**: `/workspace` (configurable vía `container_workspace`).
- **Nombres de Contenedor Únicos**: Genera identificadores únicos por ejecución: `f"kosmo_val_{ULID()!s}".lower()`.
- **Construcción de Argumentos Docker**:
  ```bash
  docker run --name <container_name> -v <resolved_workspace>:/workspace [-v ...:ro] -w /workspace --rm <image> sh -c "<command>"
  ```
- **Montaje Solo Lectura**: Parámetro `mount_read_only=True` añade el sufijo `:ro` al volumen montado para prevenir cualquier modificación en pasos de validación pura.
- **Limpieza de Contenedores Huérfanos (`_cleanup_container`)**:
  - Si un paso excede el tiempo límite o la tarea asíncrona es cancelada (`asyncio.CancelledError`), captura el evento, envía señal de terminación al subproceso y ejecuta de inmediato `docker rm -f <container_name>` (con timeout de `10.0s`) para evitar contenedores zombies en el daemon de Docker.

---

### 3. `RemoteCodeRunner` ([remote_code_runner.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/sandbox/remote_code_runner.py))

Ejecuta validaciones delegándolas a un microservicio remoto independiente a través de HTTP, ideal para despliegues en contenedores sin acceso al daemon de Docker o ambientes serverless.

#### A. Empaquetado y Transporte del Workspace
- **Función `_archive_workspace`**: Construye en memoria un archivo tarball comprimido con gzip (`io.BytesIO`, modo `"w:gz"`), codificado en Base64.
- **Exclusiones de Empaquetado**: Omite estrictamente dependencias y artefactos generados: `node_modules`, `.git`, `.next`, `.turbo`, `coverage`. Ignora enlaces simbólicos (`not path.is_symlink()`).
- **Comunicación HTTP**: Utiliza `httpx.AsyncClient` con URL base configurable y timeout total de `900s` (conexión `10s`), enviando `POST /run` con autenticación `Bearer <token>` y payload JSON con operación (`step`, `command`, `pipeline`).

#### B. Protocolo de Integridad del Lockfile (`_persist_package_lock`)
Tras un pipeline exitoso, el runner remoto devuelve el archivo `package-lock.json` actualizado. Para prevenir ataques de sustitución de dependencias o adulteración de paquetes:
1. **Límite de Tamaño**: Rechaza lockfiles de más de `5,000,000` bytes (5 MB).
2. **Inmutabilidad del Manifiesto**: Verifica mediante comparación de bytes que `package.json` no haya sido alterado durante la validación aislada (`manifest_path.read_bytes() == manifest_before`).
3. **Validación Estructural del Lockfile**:
   - `lockfileVersion >= 2` (formato moderno de npm).
   - Metadatos raíz: `name` y `version` deben coincidir exactamente con `package.json`.
   - Secciones de dependencias: Los bloques `dependencies`, `devDependencies`, `optionalDependencies` y `peerDependencies` en el nodo raíz `packages[""]` deben ser idénticos a los de `package.json`.
4. **Escritura Atómica**: Escribe primero en un archivo temporal en el mismo workspace (`tempfile.NamedTemporaryFile`) y realiza la sustitución definitiva mediante `os.replace` (operación atómica que previene corrupciones ante reinicios abruptos).

---

## Orquestación del Pipeline de Validación (`run_pipeline`)

Los tres runners implementan el método `run_pipeline` con la siguiente lógica unificada:

```
                  ┌───────────────────────────────┐
                  │ ¿Existe ./node_modules en WS? │
                  └───────────────┬───────────────┘
                                  │
                   No ────────────┴──────────── Sí
                   ▼                            │
        ┌─────────────────────┐                 │
        │ npm install (600s)  │                 │
        └──────────┬──────────┘                 │
                   │                            │
            Falla ─┴─ Éxito                     │
            ▼         │                         │
     [Abortar Run]    └────────────┬────────────┘
     all_passed=False              │
                                   ▼
                   ┌───────────────────────────────┐
                   │   Ejecución Secuencial:       │
                   │   1. TYPECHECK                │
                   │   2. LINT                     │
                   │   3. TESTS                    │
                   │   4. BUILD (condicional)      │
                   └───────────────┬───────────────┘
                                   │
              ┌────────────────────┴────────────────────┐
              ▼                                         ▼
     fail_fast = True                          fail_fast = False (Default)
     Detiene al primer error.                  Ejecuta TYPECHECK, LINT y TESTS.
                                               Si alguno falla, OMITE BUILD.
```

### Reglas del Pipeline
1. **Instalación Previa Automática**: Si falta `node_modules`, ejecuta `npm install` con timeout de `600s`. Si falla, aborta inmediatamente el pipeline retornando `ValidationRunResult(steps=(), all_passed=False, ...)` con el error de npm.
2. **Diagnóstico Integral vs Fail-Fast**:
   - Por defecto (`fail_fast=False`), el pipeline ejecuta **todos los pasos analíticos** (`TYPECHECK`, `LINT`, `TESTS`) incluso si alguno falla, acumulando todos los errores para que el agente de código disponga del contexto completo de fallos en un solo ciclo.
   - **Omisión de Empaquetado (`BUILD`)**: Si alguno de los pasos analíticos previos falla, el paso `BUILD` se omite automáticamente para no incurrir en el costo computacional de compilar código inválido.
3. **Trazabilidad con `run_id`**: Cada paso registra eventos estructurados en structlog (`code_runner.step_done` o `docker_runner.step_done`) etiquetados con el `run_id` para correlación en telemetría.

---

## Comandos y Timeouts por Defecto

| Paso de Validación (`ValidationStep`) | Comando por Defecto | Timeout por Defecto |
|:---|:---|:---:|
| `ValidationStep.TYPECHECK` | `npx tsc --noEmit` | `60s` |
| `ValidationStep.LINT` | `npx eslint .` | `60s` |
| `ValidationStep.TESTS` | `npx vitest run` | `90s` |
| `ValidationStep.BUILD` | `npx next build` | `180s` |
| Instalación de Dependencias | `npm install` | `600s` |

---

## Constantes y Valores Clave

| Constante | Valor | Archivo | Propósito |
|:---|:---|:---|:---|
| `_DEFAULT_MAX_CONCURRENT_RUNNERS` | `4` | `code_runner.py` | Límite por defecto de subprocesos simultáneos |
| `KOSMO_RUNNER_QUEUE_TIMEOUT_SECONDS` | `180.0s` | `code_runner.py` | Tiempo máximo de espera en cola de runners |
| `INSTALL_COMMAND` | `"npm install"` | `code_runner.py` | Comando para aprovisionar `node_modules` |
| `INSTALL_TIMEOUT_SECONDS` | `600s` (10 min) | `code_runner.py` | Tiempo máximo para resolver dependencias npm |
| `DEFAULT_VALIDATOR_IMAGE` | `"kosmo-validator:latest"` | `docker_runner.py` | Imagen base del contenedor de validación |
| `DEFAULT_CONTAINER_WORKSPACE` | `"/workspace"` | `docker_runner.py` | Punto de montaje dentro del contenedor Docker |
| Prefijo de Contenedores | `"kosmo_val_<ULID>"` | `docker_runner.py` | Nomenclatura para evitar colisiones Docker |
| Timeout HTTP Remote Runner | `900s` (15 min) | `remote_code_runner.py` | Tiempo total de llamada a runner HTTP |
| Límite Máximo de Lockfile | `5,000,000` bytes (5 MB) | `remote_code_runner.py` | Umbral contra ataques de desbordamiento |
| Dirs Ignorados en Tarball | `node_modules`, `.git`, `.next`, `.turbo`, `coverage` | `remote_code_runner.py` | Exclusión de archivos pesados y efímeros |

---

## Matriz de Contratos Implementados

| Puerto Abstracto (`contracts/`) | Clase / Adaptador Concreto | Archivo de Implementación |
|:---|:---|:---|
| `kosmo.contracts.sdd.codegen.CodeRunnerPort` | `SubprocessCodeRunner` | [code_runner.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/sandbox/code_runner.py) |
| `kosmo.contracts.sdd.codegen.CodeRunnerPort` | `EphemeralDockerCodeRunner` | [docker_runner.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/sandbox/docker_runner.py) |
| `kosmo.contracts.sdd.codegen.CodeRunnerPort` | `RemoteCodeRunner` | [remote_code_runner.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/sandbox/remote_code_runner.py) |

---

## Cableado e Inyección de Dependencias

- **En `infrastructure/api/composition/codegen.py`**:
  - Si `settings.remote_code_runner_url` está configurado → Instancia `RemoteCodeRunner(base_url, token)`.
  - De lo contrario → Instancia `SubprocessCodeRunner()`.
- **En `infrastructure/api/composition/integrations.py`**:
  - Inyecta `runner = code_runner or EphemeralDockerCodeRunner()` en el use case `ExecuteEphemeralValidationUseCase`.
- **En `infrastructure/api/composition/__init__.py` (Lifespan)**:
  - En el apagado de la aplicación, si el runner activo es instancia de `RemoteCodeRunner`, ejecuta `await runner.aclose()`.

---

## Reglas de Implementación y Mantenimiento

1. **Nunca invocar comandos con `shell=True`**:
   - `SubprocessCodeRunner` utiliza exclusivamente `asyncio.create_subprocess_exec` con argumentos separados por lista. Nunca usar `create_subprocess_shell`.
2. **Whitelist innegociable**:
   - Para añadir una herramienta nueva al proceso de build (ej. un nuevo linter o generador de esquemas), debe añadirse explícitamente a `DEFAULT_ALLOWED_COMMAND_PREFIXES`.
3. **No ejecutar `BUILD` si fallan pruebas o análisis estático**:
   - Compilar proyectos Next.js (`next build`) es costoso en CPU y memoria. Si `TYPECHECK`, `LINT` o `TESTS` fallan, `BUILD` debe omitirse siempre.
4. **Limpieza estricta de contenedores Docker**:
   - `EphemeralDockerCodeRunner` debe asegurar que ante cancelaciones de coroutines (`asyncio.CancelledError`) se ejecute `_cleanup_container` para que no queden contenedores corriendo en background en el host.
5. **No permitir symlinks en el tarball remoto**:
   - `RemoteCodeRunner._archive_workspace` descarta enlaces simbólicos para evitar que un proyecto malicioso intente empaquetar archivos del host fuera del workspace.

---

## Directrices de Seguridad Críticas

- **Aislamiento de Secretos (`SAFE_ENV_VARS`)**: Es la defensa perimetral contra la filtración de claves API de usuarios, secretos JWT o contraseñas maestras hacia el código de terceros ejecutado durante `npm test` o `npm build`. No relajar esta lista sin revisión de seguridad.
- **Validación Criptográfica de Dependencias**: `RemoteCodeRunner` no confía ciegamente en el `package-lock.json` devuelto por el runner remoto; valida exhaustivamente que coincida con el `package.json` original antes de escribirlo en disco.
- **Límites de Concurrencia**: El semáforo global previene agotamiento de memoria RAM y CPU en el servidor al ejecutar múltiples validaciones concurrentes de Node.js / Next.js.
