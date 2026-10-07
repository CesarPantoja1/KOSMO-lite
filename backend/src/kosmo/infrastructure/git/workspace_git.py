from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import quote, urlsplit

logger = logging.getLogger(__name__)


class GitError(RuntimeError):
    """Lanzada cuando ocurre un error al ejecutar un comando de Git en el workspace."""


def _sanitize_git_output(text: str) -> str:
    """Enmascara tokens y credenciales presentes en URLs y mensajes de Git."""
    if not text:
        return ""
    # Enmascara URLs con credenciales: https://usuario:token@host o https://token@host
    sanitized = re.sub(r"https?://([^@/\s]+)@", "https://***@", text)
    return sanitized


def _run_git(
    cmd: list[str],
    workspace_path: Path | str,
    *,
    check: bool = True,
    timeout: float | None = 60.0,
) -> subprocess.CompletedProcess[str]:
    """Helper interno para ejecutar comandos de Git dentro de un directorio de workspace."""
    cwd = Path(workspace_path).resolve()
    if not cwd.exists():
        raise GitError(f"El directorio del workspace no existe: {cwd}")

    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"

    try:
        res = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout,
            env=env,
        )
    except FileNotFoundError as e:
        raise GitError("Git no está instalado o no se encuentra en el PATH del sistema.") from e
    except subprocess.TimeoutExpired as e:
        sanitized_cmd = _sanitize_git_output(" ".join(cmd))
        raise GitError(f"Tiempo de espera agotado al ejecutar el comando Git {sanitized_cmd}: {e}") from e
    except Exception as e:
        sanitized_cmd = _sanitize_git_output(" ".join(cmd))
        raise GitError(f"Error al ejecutar el comando Git {sanitized_cmd}: {e}") from e

    if check and res.returncode != 0:
        raw_err = res.stderr.strip() or res.stdout.strip() or f"Código de salida: {res.returncode}"
        sanitized_err = _sanitize_git_output(raw_err)
        sanitized_cmd = _sanitize_git_output(" ".join(cmd))
        raise GitError(f"Fallo al ejecutar {sanitized_cmd} en {cwd}: {sanitized_err}")

    return res


def git_init(
    workspace_path: Path | str,
    initial_branch: str = "main",
    user_name: str = "KOSMO Bot",
    user_email: str = "bot@kosmo.ai",
) -> None:
    """Inicializa un repositorio Git local en el workspace y configura la identidad local."""
    cwd = Path(workspace_path).resolve()
    if not cwd.exists():
        cwd.mkdir(parents=True, exist_ok=True)

    # Intentar git init con -b para configurar rama inicial
    res = _run_git(["git", "init", "-b", initial_branch], cwd, check=False)
    if res.returncode != 0:
        # Fallback para versiones antiguas de Git que no soportan -b
        _run_git(["git", "init"], cwd, check=True)
        _run_git(["git", "checkout", "-B", initial_branch], cwd, check=False)

    # Configurar identidad local en el repositorio para evitar errores en commits
    _run_git(["git", "config", "user.name", user_name], cwd, check=False)
    _run_git(["git", "config", "user.email", user_email], cwd, check=False)


def git_add(workspace_path: Path | str, pattern: str = ".") -> None:
    """Añade archivos al área de preparación (staging)."""
    _run_git(["git", "add", pattern], workspace_path, check=True)


def git_commit(
    workspace_path: Path | str,
    message: str,
    *,
    allow_empty: bool = False,
) -> bool:
    """Crea un commit con los cambios preparados.

    Retorna True si se creó un commit exitosamente, o False si no había cambios que commitear.
    """
    cmd = ["git", "commit", "-m", message]
    if allow_empty:
        cmd.append("--allow-empty")

    res = _run_git(cmd, workspace_path, check=False)
    if res.returncode == 0:
        return True

    combined_output = (res.stdout + " " + res.stderr).lower()
    if "nothing to commit" in combined_output or "no changes added to commit" in combined_output:
        logger.debug("No hay cambios para commitear en %s", workspace_path)
        return False

    err_msg = res.stderr.strip() or res.stdout.strip() or f"Código de salida: {res.returncode}"
    raise GitError(f"Fallo en git commit: {err_msg}")


def git_rollback(workspace_path: Path | str) -> None:
    """Realiza un rollback determinista descartando cambios rastreados y eliminando no rastreados.

    Ejecuta 'git reset --hard HEAD' y 'git clean -fd'.
    """
    cwd = Path(workspace_path).resolve()
    if not cwd.exists():
        return

    # Verificar si el repo tiene commits previos
    has_head = git_has_commits(cwd)
    if has_head:
        _run_git(["git", "reset", "--hard", "HEAD"], cwd, check=True)
    else:
        # Si no hay commits previos, desestagear todo
        _run_git(["git", "rm", "-rf", "--cached", "."], cwd, check=False)

    # Limpiar archivos y directorios no rastreados
    _run_git(["git", "clean", "-fd"], cwd, check=True)


def git_status(workspace_path: Path | str) -> str:
    """Obtiene la salida de git status --porcelain."""
    res = _run_git(["git", "status", "--porcelain"], workspace_path, check=True)
    return res.stdout


def git_is_clean(workspace_path: Path | str) -> bool:
    """Verifica si el working tree está completamente limpio."""
    status = git_status(workspace_path)
    return len(status.strip()) == 0


def git_has_commits(workspace_path: Path | str) -> bool:
    """Comprueba si el repositorio tiene al menos un commit en HEAD."""
    res = _run_git(["git", "rev-parse", "--verify", "HEAD"], workspace_path, check=False)
    return res.returncode == 0


def git_head_hash(workspace_path: Path | str) -> str | None:
    """Retorna el hash completo del commit en HEAD, o None si no hay commits."""
    res = _run_git(["git", "rev-parse", "HEAD"], workspace_path, check=False)
    if res.returncode != 0:
        return None
    return res.stdout.strip() or None


def git_current_branch(workspace_path: Path | str) -> str:
    """Retorna el nombre de la rama actual del repositorio, o 'main' por defecto."""
    res = _run_git(["git", "branch", "--show-current"], workspace_path, check=False)
    branch = res.stdout.strip()
    if branch:
        return branch

    res_rev = _run_git(["git", "rev-parse", "--abbrev-ref", "HEAD"], workspace_path, check=False)
    rev_branch = res_rev.stdout.strip()
    if rev_branch and rev_branch != "HEAD":
        return rev_branch

    return "main"


def git_remote_add_or_update(
    workspace_path: Path | str,
    name: str = "origin",
    url: str = "",
) -> None:
    """Añade un remoto al repositorio local o actualiza su URL si ya existe."""
    if not url or not url.strip():
        raise GitError("La URL del repositorio remoto no puede estar vacía.")

    existing_url = git_remote_get_url(workspace_path, name=name)
    if existing_url is not None:
        _run_git(["git", "remote", "set-url", name, url.strip()], workspace_path, check=True)
    else:
        _run_git(["git", "remote", "add", name, url.strip()], workspace_path, check=True)


def git_remote_get_url(
    workspace_path: Path | str,
    name: str = "origin",
) -> str | None:
    """Obtiene la URL configurada para el remoto indicado, o None si no existe."""
    res = _run_git(["git", "remote", "get-url", name], workspace_path, check=False)
    if res.returncode != 0:
        return None
    return res.stdout.strip() or None


def git_build_authenticated_url(repo_url: str, token: str) -> str:
    """Construye una URL autenticada para GitHub usando HTTPS o un Git local.

    Ejemplo:
        'https://github.com/org/repo.git' -> 'https://x-access-token:<token>@github.com/org/repo.git'
    """
    clean_url = repo_url.strip()
    clean_token = quote(token.strip(), safe="")

    if not clean_token:
        raise GitError("El token de acceso no puede estar vacío.")

    parsed = urlsplit(clean_url)
    if parsed.scheme:
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise GitError("La URL remota debe ser HTTPS o un servidor Git local HTTP válido.")

        local_hosts = {"localhost", "127.0.0.1", "::1"}
        if parsed.scheme == "http" and parsed.hostname not in local_hosts:
            raise GitError("Solo se permiten URLs HTTPS fuera de servidores Git locales.")

        host_path = parsed.netloc.rsplit("@", 1)[-1] + parsed.path
        if parsed.query:
            host_path += f"?{parsed.query}"
        return f"{parsed.scheme}://x-access-token:{clean_token}@{host_path}"

    return f"https://x-access-token:{clean_token}@{clean_url}"


def git_push(
    workspace_path: Path | str,
    remote: str = "origin",
    branch: str | None = None,
    *,
    token: str | None = None,
    force_with_lease: bool = False,
    set_upstream: bool = True,
) -> str:
    """Ejecuta git push hacia el repositorio remoto, con soporte para autenticación segura.

    Valida previamente que el repositorio contenga al menos un commit.
    Retorna el hash del commit en HEAD que fue enviado.
    """
    if not git_has_commits(workspace_path):
        raise GitError("El repositorio no tiene commits para enviar al remoto.")

    target_branch = branch or git_current_branch(workspace_path)

    # Determinar el destino de push
    if token:
        # Si el remoto es un nombre configurado (e.g. 'origin'), obtener su URL base
        if not remote.startswith(("http://", "https://")):
            configured_url = git_remote_get_url(workspace_path, name=remote)
            if not configured_url:
                raise GitError(f"No se encontró una URL configurada para el remoto '{remote}'.")
            target_url = git_build_authenticated_url(configured_url, token)
        else:
            target_url = git_build_authenticated_url(remote, token)

        cmd = ["git", "push"]
        if force_with_lease:
            cmd.append("--force-with-lease")
        cmd.extend([target_url, f"{target_branch}:{target_branch}"])
    else:
        cmd = ["git", "push"]
        if force_with_lease:
            cmd.append("--force-with-lease")
        if set_upstream:
            cmd.extend(["-u", remote, target_branch])
        else:
            cmd.extend([remote, target_branch])

    _run_git(cmd, workspace_path, check=True)

    head = git_head_hash(workspace_path)
    return head or ""


def git_revert_commit(workspace_path: Path | str, commit: str) -> None:
    """Revierte un commit conservando el resto del historial (git revert --no-edit)."""
    _run_git(["git", "revert", "--no-edit", commit], workspace_path, check=True)


async def run_git_async(
    cmd: list[str],
    workspace_path: Path | str,
    *,
    check: bool = True,
    timeout: float | None = 60.0,
) -> subprocess.CompletedProcess[str]:
    """Helper interno asíncrono para ejecutar comandos de Git fuera del event loop principal."""
    return await asyncio.to_thread(_run_git, cmd, workspace_path, check=check, timeout=timeout)


async def git_init_async(
    workspace_path: Path | str,
    initial_branch: str = "main",
    user_name: str = "KOSMO Bot",
    user_email: str = "bot@kosmo.ai",
) -> None:
    """Versión asíncrona de git_init."""
    await asyncio.to_thread(git_init, workspace_path, initial_branch, user_name, user_email)


async def git_add_async(workspace_path: Path | str, pattern: str = ".") -> None:
    """Versión asíncrona de git_add."""
    await asyncio.to_thread(git_add, workspace_path, pattern)


async def git_commit_async(
    workspace_path: Path | str,
    message: str,
    *,
    allow_empty: bool = False,
) -> bool:
    """Versión asíncrona de git_commit."""
    return await asyncio.to_thread(git_commit, workspace_path, message, allow_empty=allow_empty)


async def git_rollback_async(workspace_path: Path | str) -> None:
    """Versión asíncrona de git_rollback."""
    await asyncio.to_thread(git_rollback, workspace_path)


async def git_status_async(workspace_path: Path | str) -> str:
    """Versión asíncrona de git_status."""
    return await asyncio.to_thread(git_status, workspace_path)


async def git_is_clean_async(workspace_path: Path | str) -> bool:
    """Versión asíncrona de git_is_clean."""
    return await asyncio.to_thread(git_is_clean, workspace_path)


async def git_has_commits_async(workspace_path: Path | str) -> bool:
    """Versión asíncrona de git_has_commits."""
    return await asyncio.to_thread(git_has_commits, workspace_path)


async def git_head_hash_async(workspace_path: Path | str) -> str | None:
    """Versión asíncrona de git_head_hash."""
    return await asyncio.to_thread(git_head_hash, workspace_path)


async def git_current_branch_async(workspace_path: Path | str) -> str:
    """Versión asíncrona de git_current_branch."""
    return await asyncio.to_thread(git_current_branch, workspace_path)


async def git_remote_add_or_update_async(
    workspace_path: Path | str,
    name: str = "origin",
    url: str = "",
) -> None:
    """Versión asíncrona de git_remote_add_or_update."""
    await asyncio.to_thread(git_remote_add_or_update, workspace_path, name=name, url=url)


async def git_remote_get_url_async(
    workspace_path: Path | str,
    name: str = "origin",
) -> str | None:
    """Versión asíncrona de git_remote_get_url."""
    return await asyncio.to_thread(git_remote_get_url, workspace_path, name=name)


async def git_push_async(
    workspace_path: Path | str,
    remote: str = "origin",
    branch: str | None = None,
    *,
    token: str | None = None,
    force_with_lease: bool = False,
    set_upstream: bool = True,
) -> str:
    """Versión asíncrona de git_push."""
    return await asyncio.to_thread(
        git_push,
        workspace_path,
        remote=remote,
        branch=branch,
        token=token,
        force_with_lease=force_with_lease,
        set_upstream=set_upstream,
    )


async def git_revert_commit_async(workspace_path: Path | str, commit: str) -> None:
    """Versión asíncrona de git_revert_commit."""
    await asyncio.to_thread(git_revert_commit, workspace_path, commit)


class LocalGitWorkspaceAdapter:
    """Adaptador de infraestructura para operaciones Git en el workspace local."""

    def remote_add_or_update(self, workspace_path: str, name: str, url: str) -> None:
        """Añade un remoto al repositorio local o actualiza su URL si ya existe."""
        git_remote_add_or_update(workspace_path, name=name, url=url)

    async def remote_add_or_update_async(self, workspace_path: str, name: str, url: str) -> None:
        """Añade un remoto al repositorio local o actualiza su URL asíncronamente."""
        await asyncio.to_thread(self.remote_add_or_update, workspace_path, name=name, url=url)

    def build_authenticated_url(self, repo_url: str, token: str) -> str:
        """Construye una URL HTTPS autenticada utilizando el token provisto."""
        return git_build_authenticated_url(repo_url, token)

    def push(
        self,
        workspace_path: str,
        remote: str = "origin",
        branch: str | None = None,
        *,
        token: str | None = None,
    ) -> str:
        """Ejecuta git push sin persistir credenciales en el remoto local."""
        return git_push(workspace_path, remote=remote, branch=branch, token=token)

    async def push_async(
        self,
        workspace_path: str,
        remote: str = "origin",
        branch: str | None = None,
        *,
        token: str | None = None,
    ) -> str:
        """Ejecuta git push asíncronamente sin persistir credenciales en el remoto local."""
        return await asyncio.to_thread(self.push, workspace_path, remote=remote, branch=branch, token=token)
