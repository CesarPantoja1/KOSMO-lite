from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import functools
import json
import os
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import structlog

from kosmo.application.codegen.analyze_ux_context import (
    THEME_TOKENS_BY_ARCHETYPE,
    classify_archetype,
)
from kosmo.contracts.sdd.codegen import (
    CodeRunnerPort,
    CodeWorkspace,
    FileSystemReader,
    FileSystemWriter,
    WorkspaceManagerPort,
    WorkspaceRepository,
    WorkspaceStatus,
)
from kosmo.contracts.sdd.ids import ProjectId, WorkspaceId
from kosmo.contracts.sdd.repositories import DocumentRepository, ProjectRepository
from kosmo.domain.codegen.site_config import format_site_config
from kosmo.domain.sdd.document_converters import document_to_markdown
from kosmo.infrastructure.git import (
    git_add_async,
    git_commit_async,
    git_has_commits_async,
    git_head_hash_async,
    git_init_async,
    git_revert_commit_async,
    git_rollback_async,
)
from kosmo.infrastructure.sandbox.code_runner import INSTALL_COMMAND, INSTALL_TIMEOUT_SECONDS

_log = structlog.get_logger("kosmo.codegen.workspace")

_IGNORED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        "node_modules",
        ".next",
        "dist",
        "build",
        "__pycache__",
        ".turbo",
        ".pytest_cache",
        ".coverage",
    }
)

DEFAULT_TEMPLATE_DIR: Path = Path(__file__).parent / "templates" / "basic-next-app"

_AGENTS_TEMPLATE_PATH: Path = Path(__file__).parent / "templates" / "workspace" / "AGENTS.md.tmpl"
_SKILLS_TEMPLATE_DIR: Path = DEFAULT_TEMPLATE_DIR / ".opencode" / "skills"


@functools.cache
def _read_template(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _generate_agents_md(project_name: str) -> str:
    """Genera el contenido de AGENTS.md para el workspace de implementación."""
    return _read_template(_AGENTS_TEMPLATE_PATH).replace("{{PROJECT_NAME}}", project_name)


def _generate_implementation_skill_md() -> str:
    """Genera la skill kosmo-implementation para el workspace de implementación."""
    return _read_template(_SKILLS_TEMPLATE_DIR / "kosmo-implementation" / "SKILL.md")


def _generate_testing_skill_md() -> str:
    """Genera la skill kosmo-testing (TDD con Vitest) para el workspace de implementación."""
    return _read_template(_SKILLS_TEMPLATE_DIR / "kosmo-testing" / "SKILL.md")


def _generate_tdd_skill_md() -> str:
    """Mantiene compatibilidad con alias tdd."""
    return _read_template(_SKILLS_TEMPLATE_DIR / "tdd" / "SKILL.md")


def _generate_drizzle_skill_md() -> str:
    """Genera la skill kosmo-drizzle para modelado y consultas con Drizzle ORM sobre SQLite."""
    return _read_template(_SKILLS_TEMPLATE_DIR / "kosmo-drizzle" / "SKILL.md")


def _generate_nextjs_skill_md() -> str:
    """Genera la skill kosmo-nextjs para App Router, React 19 y Server Components."""
    return _read_template(_SKILLS_TEMPLATE_DIR / "kosmo-nextjs" / "SKILL.md")


def _generate_ui_skill_md() -> str:
    """Genera la skill kosmo-ui: UI funcional, navegación y diseño consistente."""
    return _read_template(_SKILLS_TEMPLATE_DIR / "kosmo-ui" / "SKILL.md")


def _generate_opencode_json(
    project_id: ProjectId,
    workspace_dir: str,
    mcp_url: str = "http://127.0.0.1:8000/mcp",
) -> str:
    """Genera la configuración de opencode.json para el workspace de implementación."""
    config = {
        "$schema": "https://opencode.ai/config.json",
        "instructions": ["AGENTS.md"],
        "plugin": ["@dietrichgebert/ponytail"],
        "mcp": {
            "kosmo-context": {
                "type": "remote",
                "url": mcp_url,
                "environment": {
                    "KOSMO_PROJECT_ID": str(project_id),
                },
            },
            "token-savior": {
                "type": "local",
                "command": ["uvx", "--from", "token-savior-recall", "token-savior"],
                "environment": {
                    "WORKSPACE_ROOTS": workspace_dir,
                    "TOKEN_SAVIOR_CLIENT": "opencode",
                    "TOKEN_SAVIOR_PROFILE": "optimized",
                },
            },
            "context7": {
                "type": "remote",
                "url": "https://mcp.context7.com/mcp",
            },
        },
        "permission": {
            "read": {"*": "allow"},
            "edit": {"*": "allow"},
            "bash": "deny",
            "external_directory": "deny",
            "websearch": "allow",
        },
        # Flujo headless: el agente no debe bloquearse pidiendo aclaraciones al usuario
        "tools": {
            "question": False,
        },
    }
    return json.dumps(config, indent=2) + "\n"


class WorkspaceLockedError(RuntimeError):
    """Lanzada cuando se intenta acceder o bloquear un workspace que ya está bloqueado."""


class LocalFileSystemReader(FileSystemReader):
    """Adaptador de infraestructura para lectura del sistema de archivos local."""

    def list_files(self, root: str | Path) -> tuple[str, ...]:
        root_path = Path(root)
        if not root_path.is_dir():
            return ()
        files: list[str] = []
        for p in root_path.rglob("*"):
            if p.is_file():
                with contextlib.suppress(ValueError):
                    files.append(p.relative_to(root_path).as_posix())
        return tuple(files)

    def read_text(self, path: str | Path) -> str | None:
        p = Path(path)
        if not p.is_file():
            return None
        try:
            return p.read_text(encoding="utf-8")
        except Exception:
            return None


class LocalFileSystemWriter(FileSystemWriter):
    """Adaptador de infraestructura para escritura del sistema de archivos local."""

    def write_text(self, path: str | Path, content: str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


class LocalWorkspaceManager(WorkspaceManagerPort, FileSystemReader, FileSystemWriter):
    """Adaptador de infraestructura para la gestión de workspaces locales."""

    def __init__(
        self,
        workspaces_root: Path | str,
        workspace_repo: WorkspaceRepository | None = None,
        template_dir: Path | str | None = None,
        git_init: bool = True,
        mcp_url: str = "http://127.0.0.1:8000/mcp",
        project_repo: ProjectRepository | None = None,
        code_runner: CodeRunnerPort | None = None,
        document_repo: DocumentRepository | None = None,
        fs_reader: FileSystemReader | None = None,
    ) -> None:
        self._workspaces_root = Path(workspaces_root)
        self._workspace_repo = workspace_repo
        self._template_dir = Path(template_dir) if template_dir is not None else DEFAULT_TEMPLATE_DIR
        self._git_init = git_init
        self._mcp_url = mcp_url
        self._project_repo = project_repo
        self._code_runner = code_runner
        self._document_repo = document_repo
        self._fs_reader = fs_reader or LocalFileSystemReader()
        self._fs_writer = LocalFileSystemWriter()
        self._in_memory_locks: set[str] = set()
        # ponytail: guard global del proceso; la carrera multi-worker se cierra con el
        # CAS (UPDATE condicional) de update_lock en el repositorio SQL.
        self._lock_guard = asyncio.Lock()

    def list_files(self, root: str | Path) -> tuple[str, ...]:
        """Implementación de FileSystemReader delegada en LocalFileSystemReader."""
        return self._fs_reader.list_files(root)

    def read_text(self, path: str | Path) -> str | None:
        """Implementación de FileSystemReader delegada en LocalFileSystemReader."""
        return self._fs_reader.read_text(path)

    def write_text(self, path: str | Path, content: str) -> None:
        """Implementación de FileSystemWriter delegada en LocalFileSystemWriter."""
        self._fs_writer.write_text(path, content)

    @staticmethod
    def _extract_manifest(workspace_path: Path) -> tuple[str, ...]:
        """Extrae el listado de archivos relativos excluyendo directorios ignorados."""
        if not workspace_path.exists():
            return ()

        files: list[str] = []
        for root, dirs, filenames in os.walk(workspace_path):
            dirs[:] = [d for d in dirs if d not in _IGNORED_DIRS]
            rel_root = Path(root).relative_to(workspace_path)
            for fname in filenames:
                if fname in {".DS_Store", "thumbs.db"}:
                    continue
                rel_path = (rel_root / fname).as_posix()
                if rel_path.startswith("./"):
                    rel_path = rel_path[2:]
                files.append(rel_path)

        return tuple(sorted(files))

    def _resolve_target_dir(self, project_id: ProjectId) -> Path:
        """Resuelve y valida que el directorio del proyecto resida estrictamente dentro de la raíz."""
        root_dir = self._workspaces_root.resolve()
        target_dir = (root_dir / str(project_id)).resolve()
        if not target_dir.is_relative_to(root_dir) or target_dir == root_dir:
            raise ValueError(f"Workspace path escapes configured root for project '{project_id}'.")
        return target_dir

    async def ensure_workspace(self, project_id: ProjectId) -> CodeWorkspace:
        """Crea el directorio del workspace si no existe (idempotente) y retorna la entidad."""
        target_dir = self._resolve_target_dir(project_id)
        created_new = not target_dir.exists()

        # Resuelve project_name y site_config de forma asíncrona desde repositorios
        project_name = str(project_id)
        site_config_content: str | None = None
        if self._project_repo:
            with contextlib.suppress(Exception):
                proj = await self._project_repo.by_id(project_id)
                if proj and proj.name:
                    project_name = proj.name
                    desc = proj.description or "Aplicación generada con KOSMO."
                    archetype_val = "saas_tool"
                    primary_color = "#0f766e"
                    if self._document_repo is not None:
                        discovery_doc = await self._document_repo.get_discovery(project_id)
                        if discovery_doc is not None:
                            discovery_md = document_to_markdown(discovery_doc)
                            arch = classify_archetype(discovery_md)
                            archetype_val = arch.value
                            tokens = THEME_TOKENS_BY_ARCHETYPE.get(arch)
                            if tokens:
                                primary_color = tokens.primary_color
                    site_config_content = format_site_config(
                        name=proj.name,
                        description=desc,
                        archetype=archetype_val,
                        primary_color=primary_color,
                    )

        skills_map = {
            "kosmo-implementation": _generate_implementation_skill_md(),
            "kosmo-testing": _generate_testing_skill_md(),
            "kosmo-drizzle": _generate_drizzle_skill_md(),
            "kosmo-nextjs": _generate_nextjs_skill_md(),
            "kosmo-ui": _generate_ui_skill_md(),
            "tdd": _generate_tdd_skill_md(),
        }

        def _init_disk_workspace() -> None:
            if not target_dir.exists():
                target_dir.mkdir(parents=True, exist_ok=True)
                if self._template_dir and self._template_dir.exists():
                    shutil.copytree(self._template_dir, target_dir, dirs_exist_ok=True)

            # Generar AGENTS.md y opencode.json si no existen
            agents_file = target_dir / "AGENTS.md"
            if not agents_file.exists():
                agents_file.write_text(_generate_agents_md(project_name), encoding="utf-8")

            opencode_file = target_dir / "opencode.json"
            if not opencode_file.exists():
                opencode_file.write_text(
                    _generate_opencode_json(project_id, str(target_dir), self._mcp_url),
                    encoding="utf-8",
                )
            else:
                try:
                    parsed: object = json.loads(opencode_file.read_text(encoding="utf-8"))
                    if isinstance(parsed, dict):
                        raw_cfg: dict[str, Any] = cast(dict[str, Any], parsed)
                        perms = raw_cfg.get("permission")
                        if isinstance(perms, dict):
                            cfg_perms: dict[str, Any] = cast(dict[str, Any], perms)
                            cfg_updated = False
                            for perm_key in ("read", "edit"):
                                if perm_key not in cfg_perms:
                                    cfg_perms[perm_key] = {"*": "allow"}
                                    cfg_updated = True
                            for deny_key in ("bash", "external_directory"):
                                if cfg_perms.get(deny_key) != "deny":
                                    cfg_perms[deny_key] = "deny"
                                    cfg_updated = True
                            if cfg_perms.get("websearch") != "allow":
                                cfg_perms["websearch"] = "allow"
                                cfg_updated = True
                            if cfg_updated:
                                opencode_file.write_text(json.dumps(raw_cfg, indent=2) + "\n", encoding="utf-8")
                except Exception:
                    pass

            # Actualizar site.ts con el nombre, descripción y arquetipo reales del proyecto
            site_file = target_dir / "src" / "lib" / "site.ts"
            if site_file.exists() and site_config_content is not None:
                site_file.write_text(site_config_content, encoding="utf-8")

            # Sincronizar y reparar infraestructura de despliegue (Dockerfile, next.config.ts, db/index.ts)
            tmpl_dockerfile = self._template_dir / "Dockerfile" if self._template_dir else None
            target_dockerfile = target_dir / "Dockerfile"
            if tmpl_dockerfile and tmpl_dockerfile.exists():
                needs_update = False
                if not target_dockerfile.exists():
                    needs_update = True
                else:
                    cur_df = target_dockerfile.read_text(encoding="utf-8")
                    if (
                        "npm rebuild better-sqlite3" not in cur_df
                        or "better-sqlite3" not in cur_df
                        or "python3 make g++" not in cur_df
                    ):
                        needs_update = True
                if needs_update:
                    target_dockerfile.write_text(tmpl_dockerfile.read_text(encoding="utf-8"), encoding="utf-8")

            tmpl_next_config = self._template_dir / "next.config.ts" if self._template_dir else None
            target_next_config = target_dir / "next.config.ts"
            if tmpl_next_config and tmpl_next_config.exists() and target_next_config.exists():
                cur_nc = target_next_config.read_text(encoding="utf-8")
                if "serverExternalPackages" not in cur_nc:
                    target_next_config.write_text(tmpl_next_config.read_text(encoding="utf-8"), encoding="utf-8")

            tmpl_db_index = self._template_dir / "src" / "db" / "index.ts" if self._template_dir else None
            target_db_index = target_dir / "src" / "db" / "index.ts"
            if tmpl_db_index and tmpl_db_index.exists() and target_db_index.exists():
                cur_db = target_db_index.read_text(encoding="utf-8")
                if "syncSchema" not in cur_db or "(exported as any)" in cur_db:
                    target_db_index.write_text(tmpl_db_index.read_text(encoding="utf-8"), encoding="utf-8")

            # Generar las skills en .opencode/skills si no existen
            skills_dir = target_dir / ".opencode" / "skills"
            for skill_name, skill_content in skills_map.items():
                skill_file = skills_dir / skill_name / "SKILL.md"
                if not skill_file.exists():
                    skill_file.parent.mkdir(parents=True, exist_ok=True)
                    skill_file.write_text(skill_content, encoding="utf-8")

        await asyncio.to_thread(_init_disk_workspace)

        if self._git_init:
            with contextlib.suppress(Exception):
                await git_init_async(target_dir)
                await git_add_async(target_dir)
                has_commits = await git_has_commits_async(target_dir)
                if not has_commits:
                    await git_commit_async(target_dir, "chore: initialize workspace template and configurations")
                else:
                    await git_commit_async(target_dir, "chore: update build and database deployment configuration")

        # Pre-instalar dependencias al crear el workspace para que la primera
        # validación no consuma el timeout de npm install dentro del pipeline.
        if created_new and self._code_runner is not None:
            with contextlib.suppress(Exception):
                install = await self._code_runner.run_command(
                    str(target_dir),
                    INSTALL_COMMAND,
                    timeout_seconds=INSTALL_TIMEOUT_SECONDS,
                )
                if not install.success:
                    _log.warning(
                        "workspace.npm_install_failed",
                        project_id=str(project_id),
                        exit_code=install.exit_code,
                    )

        manifest = await asyncio.to_thread(self._extract_manifest, target_dir)
        now = datetime.now(UTC)

        if self._workspace_repo:
            existing = await self._workspace_repo.by_project_id(project_id)
            if existing is not None and not created_new:
                return dataclasses.replace(existing, manifest_files=manifest)

            ws = CodeWorkspace(
                id=WorkspaceId(f"ws_{project_id}"),
                project_id=project_id,
                status=WorkspaceStatus.READY,
                workspace_dir=str(target_dir),
                manifest_files=manifest,
                current_branch="main",
                is_locked=str(project_id) in self._in_memory_locks,
                created_at=now,
                updated_at=now,
            )
            await self._workspace_repo.save(ws)
            return ws

        return CodeWorkspace(
            id=WorkspaceId(f"ws_{project_id}"),
            project_id=project_id,
            status=WorkspaceStatus.READY,
            workspace_dir=str(target_dir),
            manifest_files=manifest,
            current_branch="main",
            is_locked=str(project_id) in self._in_memory_locks,
            created_at=now,
            updated_at=now,
        )

    async def get_workspace(self, project_id: ProjectId) -> CodeWorkspace | None:
        """Obtiene la información del workspace si existe."""
        if self._workspace_repo:
            ws = await self._workspace_repo.by_project_id(project_id)
            if ws is not None:
                if ws.workspace_dir and Path(ws.workspace_dir).exists():
                    manifest = await asyncio.to_thread(self._extract_manifest, Path(ws.workspace_dir))
                    return dataclasses.replace(ws, manifest_files=manifest)
                return ws

        target_dir = (self._workspaces_root / str(project_id)).resolve()
        if target_dir.exists():
            manifest = await asyncio.to_thread(self._extract_manifest, target_dir)
            now = datetime.now(UTC)
            return CodeWorkspace(
                id=WorkspaceId(f"ws_{project_id}"),
                project_id=project_id,
                status=WorkspaceStatus.READY,
                workspace_dir=str(target_dir),
                manifest_files=manifest,
                current_branch="main",
                is_locked=str(project_id) in self._in_memory_locks,
                created_at=now,
                updated_at=now,
            )

        return None

    async def get_manifest(self, workspace: CodeWorkspace) -> tuple[str, ...]:
        """Retorna el manifiesto de archivos actual del workspace."""
        if not workspace.workspace_dir:
            return ()
        return await asyncio.to_thread(self._extract_manifest, Path(workspace.workspace_dir))

    async def is_locked(self, project_id: ProjectId) -> bool:
        """Verifica si el workspace está bloqueado."""
        if self._workspace_repo:
            ws = await self._workspace_repo.by_project_id(project_id)
            if ws is not None and ws.is_locked:
                return True
        return str(project_id) in self._in_memory_locks

    async def acquire_lock(self, project_id: ProjectId) -> None:
        """Adquiere el bloqueo para un proyecto o lanza WorkspaceLockedError."""
        async with self._lock_guard:
            if str(project_id) in self._in_memory_locks:
                raise WorkspaceLockedError(
                    f"Workspace for project '{project_id}' is currently locked by another process."
                )
            if self._workspace_repo:
                updated = await self._workspace_repo.update_lock(project_id, is_locked=True)
                if updated is None:
                    raise WorkspaceLockedError(
                        f"Workspace for project '{project_id}' is currently locked by another process."
                    )
            self._in_memory_locks.add(str(project_id))

    async def release_lock(self, project_id: ProjectId) -> None:
        """Libera el bloqueo para un proyecto."""
        async with self._lock_guard:
            self._in_memory_locks.discard(str(project_id))
            if self._workspace_repo:
                await self._workspace_repo.release_lock(project_id)

    async def rollback_workspace(self, project_id: ProjectId) -> None:
        """Revierte el workspace al último commit exitoso y limpia archivos no rastreados."""
        target_dir = (self._workspaces_root / str(project_id)).resolve()
        if not target_dir.exists():
            return

        await git_rollback_async(target_dir)

        manifest = await asyncio.to_thread(self._extract_manifest, target_dir)
        if self._workspace_repo:
            ws = await self._workspace_repo.by_project_id(project_id)
            if ws is not None:
                updated = dataclasses.replace(ws, manifest_files=manifest, updated_at=datetime.now(UTC))
                await self._workspace_repo.save(updated)

    async def delete_workspace(self, project_id: ProjectId) -> None:
        """Elimina el código persistido de un proyecto.

        La metadata de base de datos se elimina en cascada al borrar el proyecto,
        pero el filesystem compartido no tiene ese mecanismo. Esta operación debe
        completarse antes de borrar el proyecto para no dejar código accesible.
        """
        target_dir = self._resolve_target_dir(project_id)

        if target_dir.exists():
            for attempt in range(4):
                try:
                    await asyncio.to_thread(shutil.rmtree, target_dir)
                    break
                except OSError:
                    if attempt < 3:
                        await asyncio.sleep(0.3)
                    else:
                        await asyncio.to_thread(shutil.rmtree, target_dir, ignore_errors=True)

    async def commit_workspace(self, project_id: ProjectId, message: str) -> str | None:
        """Consolida los cambios del workspace en un commit de git y actualiza el manifiesto.

        Retorna el hash del commit creado, o None si no había cambios.
        """
        target_dir = self._resolve_target_dir(project_id)
        if not target_dir.exists():
            return None

        await git_add_async(target_dir)
        committed = await git_commit_async(target_dir, message)

        manifest = await asyncio.to_thread(self._extract_manifest, target_dir)
        if self._workspace_repo:
            ws = await self._workspace_repo.by_project_id(project_id)
            if ws is not None:
                updated = dataclasses.replace(ws, manifest_files=manifest, updated_at=datetime.now(UTC))
                await self._workspace_repo.save(updated)

        if not committed:
            return None
        return await git_head_hash_async(target_dir)

    async def remove_feature_paths(self, project_id: ProjectId, slug: str) -> tuple[str, ...]:
        """Elimina los archivos del código generado de una feature.

        Escanea el workspace para cubrir tanto el layout documentado
        (src/features/<slug>/, src/app/<slug>/, tests/<slug>.test.*) como
        variantes del agente (src/<slug>.ts, tests/<slug>.test.ts). Reglas de
        coincidencia: directorio llamado exactamente <slug> o basename que
        empiece con "<slug>.". Nunca coincide con slugs hermanos más largos
        (ej. borrar "registrar-productos" no toca "registrar-productos-con-s".
        """
        target_dir = self._resolve_target_dir(project_id)
        if not target_dir.exists():
            return ()

        def _sync_remove() -> tuple[str, ...]:
            removed: list[str] = []
            slug_lower = slug.lower()

            for root, dirs, filenames in os.walk(target_dir):
                dirs[:] = [d for d in dirs if d not in _IGNORED_DIRS]
                rel_root = Path(root).relative_to(target_dir)

                for dirname in list(dirs):
                    if dirname.lower() == slug_lower:
                        shutil.rmtree(Path(root) / dirname, ignore_errors=True)
                        removed.append((rel_root / dirname).as_posix())
                        dirs.remove(dirname)

                for fname in filenames:
                    base = fname.lower()
                    if base == slug_lower or base.startswith(f"{slug_lower}."):
                        (Path(root) / fname).unlink(missing_ok=True)
                        removed.append((rel_root / fname).as_posix())

            return tuple(sorted(set(removed)))

        return await asyncio.to_thread(_sync_remove)

    async def update_text_file(
        self,
        project_id: ProjectId,
        relative_path: str,
        transform: Callable[[str], str],
    ) -> None:
        """Aplica una transformación al contenido de un archivo del workspace (si existe)."""
        target_dir = (self._workspaces_root / str(project_id)).resolve()
        file_path = (target_dir / relative_path).resolve()
        if not file_path.is_file() or not str(file_path).startswith(str(target_dir)):
            return

        def _sync_transform() -> None:
            content = file_path.read_text(encoding="utf-8")
            updated = transform(content)
            if updated != content:
                file_path.write_text(updated, encoding="utf-8")

        await asyncio.to_thread(_sync_transform)

    async def revert_commit(self, project_id: ProjectId, commit: str) -> None:
        """Revierte un commit del workspace conservando el historial posterior (best-effort)."""
        target_dir = (self._workspaces_root / str(project_id)).resolve()
        if not target_dir.exists():
            return
        with contextlib.suppress(Exception):
            await git_revert_commit_async(target_dir, commit)
