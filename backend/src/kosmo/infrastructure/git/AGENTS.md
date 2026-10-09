# `infrastructure/git/` — Operaciones Git sobre Workspaces Locales

## Responsabilidad y Propósito

Este módulo implementa el subsistema de bajo nivel para automatizar operaciones de control de versiones Git sobre los directorios de trabajo (*workspaces*) gestionados por KOSMO:

- **Aislamiento y Checkpointing de Código**: Provee un mecanismo determinista de control de versiones local para cada proyecto. Cada cambio generado durante la fase de implementación es confirmado en commits locales, permitiendo rollbacks atómicos (`git_rollback`) al último estado válido si los tests o el linter fallan.
- **Sincronización Segura con Remotos (GitHub)**: Administra la configuración de remotos y el envío de cambios (*push*) autenticado mediante tokens de acceso OAuth/PAT, inyectando credenciales de forma efímera en la línea de comandos sin almacenarlas jamás en la configuración persistente (`.git/config`).
- **Sanitización Estricta de Credenciales**: Enmascara cualquier token presente en URLs, comandos y trazas de salida de Git (`stdout`, `stderr`) antes de registrarlos en logs o incluirlos en mensajes de error.
- **Compatibilidad Híbrida Síncrona/Asíncrona**: Expone funciones síncronas y sus correspondientes variantes asíncronas (`*_async`) delegadas al worker pool mediante `asyncio.to_thread` para no bloquear el event loop de FastAPI.
- **Adaptador Hexagonal**: Implementa el puerto `GitWorkspacePort` definido en `contracts/integrations/git.py` a través de la clase `LocalGitWorkspaceAdapter`.

---

## Estructura de Archivos y Componentes

```
infrastructure/git/
├── __init__.py                 # Reexporta símbolos públicos (funciones, adapter, excepción)
└── workspace_git.py            # Motor completo de ejecución, funciones Git y adapter
```

### Exportaciones Públicas (`__init__.py`)
El módulo exporta en su `__all__` las siguientes 26 entidades:
- **Excepción**: [`GitError`](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/git/workspace_git.py#L14-L16).
- **Adaptador**: [`LocalGitWorkspaceAdapter`](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/git/workspace_git.py#L408-L444).
- **Helpers de Ejecución**: `run_git_async`.
- **Operaciones Git (pares sync/async)**:
  - `git_init` / `git_init_async`
  - `git_add` / `git_add_async`
  - `git_commit` / `git_commit_async`
  - `git_rollback` / `git_rollback_async`
  - `git_status` / `git_status_async`
  - `git_is_clean` / `git_is_clean_async`
  - `git_has_commits` / `git_has_commits_async`
  - `git_head_hash` / `git_head_hash_async`
  - `git_current_branch` / `git_current_branch_async`
  - `git_remote_add_or_update` / `git_remote_add_or_update_async`
  - `git_remote_get_url` / `git_remote_get_url_async`
  - `git_push` / `git_push_async`
  - `git_revert_commit` / `git_revert_commit_async`
- **Utilidad de URLs Autenticadas**: `git_build_authenticated_url`.

---

## Mecanismo de Ejecución de Subprocesos (`_run_git`)

Toda interacción con el binario de Git se centraliza en la función interna `_run_git`:

```python
def _run_git(
    cmd: list[str],
    workspace_path: Path | str,
    *,
    check: bool = True,
    timeout: float | None = 60.0,
) -> subprocess.CompletedProcess[str]:
```

### Características Operativas Clave
1. **Validación de Directorio**: Resuelve la ruta canónica (`Path(workspace_path).resolve()`). Si el directorio no existe físicamente, lanza inmediatamente `GitError("El directorio del workspace no existe: <cwd>")`.
2. **Protección Anti-Hang (`GIT_TERMINAL_PROMPT="0"`)**:
   - Inyecta `GIT_TERMINAL_PROMPT = "0"` en el diccionario de variables de entorno del subproceso.
   - **Propósito**: Si Git requiere credenciales interactivas (por ejemplo, ante una URL con autenticación fallida o petición de passphrase), Git aborta de inmediato con código de error en lugar de bloquear indefinidamente el hilo esperando entrada por terminal.
3. **Captura y Codificación Segura**:
   - `capture_output=True, text=True, encoding="utf-8", errors="replace"`.
   - Evita fallos por caracteres extraños en nombres de archivo o mensajes de commit.
4. **Timeouts**:
   - Timeout por defecto: `60.0` segundos.
   - Si expira, captura `subprocess.TimeoutExpired`, sanitiza el comando ejecutado y lanza `GitError`.
5. **Traducción Tipada de Fallos**:
   - `FileNotFoundError`: Traduce a `GitError("Git no está instalado o no se encuentra en el PATH del sistema.")`.
   - `returncode != 0` (cuando `check=True`): Extrae `stderr` (o `stdout` si `stderr` está vacío), sanitiza credenciales y lanza `GitError(f"Fallo al ejecutar {sanitized_cmd} en {cwd}: {sanitized_err}")`.

---

## Sanitización y Creación de URLs Autenticadas

### 1. `_sanitize_git_output(text: str) -> str`
- Aplica la expresión regular `https?://([^@/\s]+)@` sustituyéndola por `https://***@`.
- Oculta tanto contraseñas/tokens individuales (`https://token@host`) como pares usuario-token (`https://usuario:token@host`).
- **Cobertura**: Se aplica de manera irrestricta a:
  - Todo comando antes de ser impreso en un mensaje de error de timeout o fallo general.
  - Todo mensaje de salida (`stdout` o `stderr`) antes de ser incorporado al `GitError`.

### 2. `git_build_authenticated_url(repo_url: str, token: str) -> str`
Construye URLs HTTPS autenticadas para interactuar con repositorios remotos (principalmente GitHub):

- **Validación de Token**: Verifica que no esté vacío; de lo contrario lanza `GitError("El token de acceso no puede estar vacío.")`.
- **Codificación URL**: Aplica `quote(token.strip(), safe="")` para escapar de forma segura caracteres conflictivos en el token.
- **Validación de Esquema y Host**:
  - Parsea la URL con `urlsplit`.
  - Solo permite esquemas `http` y `https`.
  - **Restricción de HTTP Plano**: Prohíbe conexiones `http://` a hosts remotos; únicamente se permite HTTP no cifrado para desarrollo local en hosts específicos: `{"localhost", "127.0.0.1", "::1"}`. Cualquier otro host con HTTP plano lanza `GitError("Solo se permiten URLs HTTPS fuera de servidores Git locales.")`.
- **Eliminación de Credenciales Previas**: Si la URL base ya contenía credenciales incrustadas, se limpian tomando `parsed.netloc.rsplit("@", 1)[-1]`.
- **Preservación de Query String**: Si la URL contiene parámetros de consulta, se concatenan al final (`?{parsed.query}`).
- **Estructura Resultante**:
  `https://x-access-token:<clean_token>@github.com/org/repo.git`

---

## Catálogo de Operaciones Git

### Inicialización e Identidad Local
- **`git_init(workspace_path, initial_branch="main", user_name="KOSMO Bot", user_email="bot@kosmo.ai")`**:
  - Si el directorio no existe, lo crea recursivamente (`mkdir(parents=True, exist_ok=True)`).
  - Intenta `git init -b <initial_branch>` para compatibilidad con Git moderno.
  - Si falla (versiones heredadas de Git sin soporte para `-b`), ejecuta `git init` seguido de `git checkout -B <initial_branch>`.
  - Configura la identidad local en el repositorio mediante `git config user.name <user_name>` y `git config user.email <user_email>`, garantizando que `git commit` funcione de forma autónoma sin depender de variables globales del host.

### Staging y Commits
- **`git_add(workspace_path, pattern=".")`**:
  - Ejecuta `git add <pattern>`.
- **`git_commit(workspace_path, message, *, allow_empty=False) -> bool`**:
  - Ejecuta `git commit -m <message>` (y `--allow-empty` si se especifica).
  - **Comportamiento Idempotente**: Si la salida combinada (`stdout` + `stderr`) contiene `"nothing to commit"` o `"no changes added to commit"`, no lanza error: registra un log de nivel `DEBUG` y retorna `False`.
  - Retorna `True` si se generó un nuevo commit.
  - Lanza `GitError` ante cualquier fallo genuino de Git.

### Rollback Determinista y Revert
- **`git_rollback(workspace_path)`**:
  - Restaura el workspace al último commit exitoso descartando cualquier modificación no consolidada.
  - Verifica si el repositorio tiene commits previos con `git_has_commits`.
  - **Con commits previos**: Ejecuta `git reset --hard HEAD`.
  - **Sin commits previos (estado inicial)**: Ejecuta `git rm -rf --cached .` para desestagear todo sin fallar.
  - **Limpieza de archivos huérfanos**: En ambos casos ejecuta `git clean -fd` para suprimir archivos y subdirectorios no rastreados (*untracked*).
- **`git_revert_commit(workspace_path, commit)`**:
  - Ejecuta `git revert --no-edit <commit>`.
  - Revierte los cambios introducidos por un commit específico (por ejemplo, el borrado de una característica) creando un nuevo commit de compensación sin alterar la historia posterior.

### Inspección de Estado y HEAD
- **`git_status(workspace_path) -> str`**:
  - Ejecuta `git status --porcelain` y retorna su salida estándar limpia.
- **`git_is_clean(workspace_path) -> bool`**:
  - Retorna `True` si `git_status` devuelve una cadena vacía (working tree sin cambios pendientes ni archivos untracked).
- **`git_has_commits(workspace_path) -> bool`**:
  - Ejecuta `git rev-parse --verify HEAD`. Retorna `True` si el código de salida es `0`, o `False` en repositorios recién inicializados sin commits.
- **`git_head_hash(workspace_path) -> str | None`**:
  - Ejecuta `git rev-parse HEAD`. Retorna el hash SHA-1 de 40 caracteres del commit en HEAD, o `None` si el repositorio no tiene commits.
- **`git_current_branch(workspace_path) -> str`**:
  - Intenta consultar `git branch --show-current`.
  - Si retorna vacío (modo detached HEAD o rama no resuelta), consulta `git rev-parse --abbrev-ref HEAD`.
  - Si el resultado sigue sin resolver o es `"HEAD"`, retorna `"main"` por defecto.

### Gestión de Remotos
- **`git_remote_add_or_update(workspace_path, name="origin", url="")`**:
  - Valida que `url` no esté vacía ni contenga solo espacios en blanco (lanza `GitError`).
  - Consulta si el remoto ya existe con `git_remote_get_url`.
  - Si ya existe, ejecuta `git remote set-url <name> <url>`.
  - Si no existe, ejecuta `git remote add <name> <url>`.
- **`git_remote_get_url(workspace_path, name="origin") -> str | None`**:
  - Ejecuta `git remote get-url <name>`. Retorna la URL configurada o `None` si el remoto no existe.

### Push Seguro
- **`git_push(workspace_path, remote="origin", branch=None, *, token=None, force_with_lease=False, set_upstream=True) -> str`**:
  - **Pre-condición**: Verifica `git_has_commits(workspace_path)`. Si no hay commits, aborta inmediatamente con `GitError("El repositorio no tiene commits para enviar al remoto.")`.
  - **Resolución de Rama**: Usa `branch` provista o la rama activa detectada con `git_current_branch`.
  - **Push con Token (Autenticado)**:
    - Si `remote` es un alias (ej. `"origin"`), recupera su URL base con `git_remote_get_url`. Si no está configurado, lanza `GitError`.
    - Genera la URL con credenciales efímeras usando `git_build_authenticated_url`.
    - Comando ejecutado: `git push [--force-with-lease] <target_url> <target_branch>:<target_branch>`.
    - **Invariante de Seguridad**: El token se pasa **exclusivamente como argumento en memoria** al proceso `git push`. La configuración en disco (`.git/config`) nunca contiene tokens.
  - **Push Estándar (Sin Token)**:
    - Comando ejecutado: `git push [--force-with-lease] [-u] <remote> <target_branch>`.
  - **Retorno**: Retorna el hash del commit en HEAD que fue enviado.

---

## Adaptador Hexagonal: `LocalGitWorkspaceAdapter`

Implementa formalmente el protocolo [`GitWorkspacePort`](file:///c:/projects/KOSMO/backend/src/kosmo/contracts/integrations/git.py) (`contracts/integrations/git.py`):

```python
class LocalGitWorkspaceAdapter:
    def remote_add_or_update(self, workspace_path: str, name: str, url: str) -> None: ...
    async def remote_add_or_update_async(self, workspace_path: str, name: str, url: str) -> None: ...
    def build_authenticated_url(self, repo_url: str, token: str) -> str: ...
    def push(
        self,
        workspace_path: str,
        remote: str = "origin",
        branch: str | None = None,
        *,
        token: str | None = None,
    ) -> str: ...
    async def push_async(
        self,
        workspace_path: str,
        remote: str = "origin",
        branch: str | None = None,
        *,
        token: str | None = None,
    ) -> str: ...
```

### Inyección de Dependencias
- Se instancia en `infrastructure/api/composition/integrations.py` (`git_workspace = LocalGitWorkspaceAdapter()`).
- Se inyecta en:
  - `SyncGitHubRepositoryUseCase` (`application/integrations/sync_github_repository.py`) para gestionar remotos y empujar el código generado al repositorio del usuario en GitHub.
  - `LocalWorkspaceManager` (`infrastructure/codegen/workspace.py`) para scaffolding inicial y control de versiones durante iteraciones de desarrollo autónomo.

---

## Constantes y Valores Clave

| Parámetro / Constante | Valor por Defecto | Ubicación | Propósito |
|:---|:---|:---|:---|
| Timeout de comandos Git | `60.0s` | `workspace_git.py:_run_git` | Prevenir bloqueos por procesos Git zombis |
| Flag de terminal interactiva | `GIT_TERMINAL_PROMPT="0"` | `workspace_git.py:_run_git` | Cancelar inmediatamente ante peticiones interactivas de contraseña |
| Rama inicial por defecto | `"main"` | `workspace_git.py:git_init` | Estandarización de ramas en workspaces |
| Nombre de usuario Git bot | `"KOSMO Bot"` | `workspace_git.py:git_init` | Identidad local para commits automatizados |
| Email de usuario Git bot | `"bot@kosmo.ai"` | `workspace_git.py:git_init` | Correo configurado localmente en `.git/config` |
| Remoto por defecto | `"origin"` | `workspace_git.py:git_push` | Nombre canónico del repositorio remoto |
| Patrón de máscara sanitizada | `https://***@` | `workspace_git.py:_sanitize_git_output` | Ocultamiento seguro de credenciales |
| Hosts locales HTTP permitidos | `localhost`, `127.0.0.1`, `::1` | `workspace_git.py:git_build_authenticated_url` | Excepción para pruebas locales sin TLS |

---

## Matriz de Contratos Implementados

| Puerto Abstracto (`contracts/`) | Clase / Adaptador Concreto | Archivo de Implementación |
|:---|:---|:---|
| `kosmo.contracts.integrations.git.GitWorkspacePort` | `LocalGitWorkspaceAdapter` | [workspace_git.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/git/workspace_git.py) |

---

## Reglas de Implementación y Mantenimiento

1. **Nunca almacenar credenciales en el archivo `.git/config`**:
   - Está prohibido ejecutar `git remote set-url origin https://token@github.com/...`.
   - Las URLs con tokens solo deben formarse al momento del push y pasarse como argumento directo de destino al subproceso `git push`.
2. **Siempre utilizar `asyncio.to_thread` para llamadas async**:
   - `subprocess.run` es una llamada bloqueante del sistema operativo. Las funciones `*_async` y `run_git_async` deben utilizar siempre `asyncio.to_thread` para no congelar el loop de eventos de FastAPI.
3. **Idempotencia en commits**:
   - No asumir que `git commit` siempre genera un nuevo objeto commit. Si no hay diferencias staged, la función retorna `False` sin lanzar excepción. Los use cases deben verificar el valor booleano retornado antes de esperar un nuevo SHA en HEAD.
4. **Verificación previa a Push**:
   - Nunca disparar `git push` sin asegurar que existan commits en HEAD (`git_has_commits`). `git_push` valida esto explícitamente para evitar fallos confusos de Git.
5. **Rollback completo en fallos de compilación**:
   - Al restaurar un workspace tras un fallo en generación de código o tests, siempre invocar `git_rollback`. Esta función garantiza tanto `git reset --hard HEAD` (o desestageado si no hay commits) como `git clean -fd` para no dejar artefactos huérfanos que contaminen el siguiente intento.

---

## Directrices de Seguridad Críticas

- **Sanitización Obligatoria**: Cualquier salida o traza que provenga de Git (`stdout`, `stderr`, comando concatenado) debe pasar por `_sanitize_git_output` antes de propagarse en excepciones o guardarse en logs.
- **Transporte Seguro Estricto**: Se prohíbe el uso de tokens sobre conexiones HTTP plano salvo en direcciones loopback locales. Esto impide fugas involuntarias de tokens de GitHub sobre redes inseguras.
- **Escape de Caracteres en Tokens**: Los tokens deben codificarse con `urllib.parse.quote(token.strip(), safe="")` para evitar inyecciones de cabeceras o corrupción de sintaxis URL al interactuar con servicios remotos.
- **No Interactividad**: Mantener invariablemente `GIT_TERMINAL_PROMPT="0"` en todo comando ejecutado para salvaguardar la resiliencia del backend ante contingencias de red o expiración de tokens.
