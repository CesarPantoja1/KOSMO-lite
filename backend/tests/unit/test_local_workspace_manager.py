from __future__ import annotations

import asyncio
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from kosmo.contracts.sdd.codegen import (
    CodeWorkspace,
    FileSystemReader,
    ValidationStep,
    ValidationStepResult,
    WorkspaceRepository,
    WorkspaceStatus,
)
from kosmo.contracts.sdd.ids import ProjectId, UserId, WorkspaceId
from kosmo.contracts.sdd.project import Project
from kosmo.domain.sdd.document_converters import markdown_to_document
from kosmo.infrastructure.codegen.workspace import (
    LocalFileSystemReader,
    LocalWorkspaceManager,
    WorkspaceLockedError,
)
from kosmo.infrastructure.git import GitError
from kosmo.infrastructure.persistence.postgres.repositories.workspace_repo import (
    LOCK_STALE_AFTER_MINUTES,
)
from tests.unit.fakes import InMemoryDocumentRepository, InMemoryProjectRepository


class FakeWorkspaceRepository(WorkspaceRepository):
    def __init__(self) -> None:
        self.workspaces: dict[str, CodeWorkspace] = {}

    async def by_project_id(self, project_id: ProjectId) -> CodeWorkspace | None:
        return self.workspaces.get(str(project_id))

    async def by_id(self, workspace_id: WorkspaceId) -> CodeWorkspace | None:
        for ws in self.workspaces.values():
            if str(ws.id) == str(workspace_id):
                return ws
        return None

    async def save(self, workspace: CodeWorkspace) -> CodeWorkspace:
        self.workspaces[str(workspace.project_id)] = workspace
        return workspace

    async def delete(self, project_id: ProjectId) -> None:
        self.workspaces.pop(str(project_id), None)

    async def update_lock(
        self,
        project_id: ProjectId | str,
        is_locked: bool,
        locked_by: str | None = None,
    ) -> CodeWorkspace | None:
        ws = self.workspaces.get(str(project_id))
        if ws is None:
            return None
        updated = CodeWorkspace(
            id=ws.id,
            project_id=ws.project_id,
            status=ws.status,
            workspace_dir=ws.workspace_dir,
            manifest_files=ws.manifest_files,
            current_branch=ws.current_branch,
            is_locked=is_locked,
            locked_at=ws.locked_at,
            locked_by=locked_by if is_locked else None,
            created_at=ws.created_at,
            updated_at=ws.updated_at,
        )
        self.workspaces[str(project_id)] = updated
        return updated

    async def release_lock(self, project_id: ProjectId | str) -> CodeWorkspace | None:
        return await self.update_lock(project_id, is_locked=False, locked_by=None)


class FakeCodeRunner:
    """Registra los comandos pedidos y responde un resultado configurable."""

    def __init__(self, install_success: bool = True) -> None:
        self.install_success = install_success
        self.commands: list[tuple[str, int]] = []

    async def run_command(
        self,
        workspace_dir: str,
        command: str,
        *,
        timeout_seconds: int = 300,
    ) -> ValidationStepResult:
        self.commands.append((command, timeout_seconds))
        return ValidationStepResult(
            step=ValidationStep.TESTS,
            success=self.install_success,
            exit_code=0 if self.install_success else 1,
            raw_output="dependencies installed" if self.install_success else "npm error: registry down",
        )


class SlowFakeWorkspaceRepository(FakeWorkspaceRepository):
    """Fake que lee el estado y luego cede el control, exponiendo la carrera check-then-add."""

    def __init__(self) -> None:
        super().__init__()
        self.update_lock_calls = 0

    async def by_project_id(self, project_id: ProjectId) -> CodeWorkspace | None:
        ws = self.workspaces.get(str(project_id))
        await asyncio.sleep(0)
        return ws

    async def update_lock(
        self,
        project_id: ProjectId | str,
        is_locked: bool,
        locked_by: str | None = None,
    ) -> CodeWorkspace | None:
        self.update_lock_calls += 1
        return await super().update_lock(project_id, is_locked, locked_by)


class CasWorkspaceRepository(FakeWorkspaceRepository):
    """Espejo del repo SQL con CAS: decide según la fila existente y su estado de lock."""

    async def update_lock(
        self,
        project_id: ProjectId | str,
        is_locked: bool,
        locked_by: str | None = None,
    ) -> CodeWorkspace | None:
        if not is_locked:
            return await super().update_lock(project_id, is_locked, locked_by)
        ws = self.workspaces.get(str(project_id))
        if ws is None:
            # INSERT bloqueado: primera adquisición, el proceso crea la fila ya tomada
            now = datetime.now(UTC)
            created = CodeWorkspace(
                id=WorkspaceId(f"ws_{project_id}"),
                project_id=ProjectId(str(project_id)),
                status=WorkspaceStatus.NOT_CREATED,
                workspace_dir=None,
                is_locked=True,
                locked_at=now,
                created_at=now,
                updated_at=now,
            )
            self.workspaces[str(project_id)] = created
            return created
        if ws.is_locked:
            stale_cutoff = datetime.now(UTC) - timedelta(minutes=LOCK_STALE_AFTER_MINUTES)
            if ws.locked_at is None or ws.locked_at > stale_cutoff:
                return None
            # Lock stale de un proceso muerto: se permite el takeover
        return await super().update_lock(project_id, is_locked, locked_by)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ensure_workspace_creates_directory_and_manifest() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_root, tempfile.TemporaryDirectory() as tmp_template:
        template_path = Path(tmp_template)
        (template_path / "package.json").write_text('{"name": "test"}')
        (template_path / "src").mkdir()
        (template_path / "src" / "index.ts").write_text("console.log('hello');")

        repo = FakeWorkspaceRepository()
        manager = LocalWorkspaceManager(
            workspaces_root=tmp_root,
            workspace_repo=repo,
            template_dir=tmp_template,
            git_init=False,
        )

        project_id = ProjectId("prj_01")

        # Act
        ws = await manager.ensure_workspace(project_id)

        # Assert
        assert ws.project_id == project_id
        assert ws.status == WorkspaceStatus.READY
        assert ws.workspace_dir is not None
        assert Path(ws.workspace_dir).exists()
        assert (Path(ws.workspace_dir) / "package.json").exists()
        assert (Path(ws.workspace_dir) / "src" / "index.ts").exists()

        assert "package.json" in ws.manifest_files
        assert "src/index.ts" in ws.manifest_files

        # Persisted in repo
        persisted = await repo.by_project_id(project_id)
        assert persisted is not None
        assert persisted.workspace_dir == ws.workspace_dir


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ensure_workspace_is_idempotent() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_root, tempfile.TemporaryDirectory() as tmp_template:
        template_path = Path(tmp_template)
        (template_path / "package.json").write_text('{"name": "original"}')

        manager = LocalWorkspaceManager(
            workspaces_root=tmp_root,
            template_dir=tmp_template,
            git_init=False,
        )
        project_id = ProjectId("prj_01")

        # Act 1: Initial creation
        ws1 = await manager.ensure_workspace(project_id)
        assert ws1.workspace_dir is not None
        file_path = Path(ws1.workspace_dir) / "package.json"
        file_path.write_text('{"name": "modified"}')

        # Act 2: Second call should not overwrite existing file
        ws2 = await manager.ensure_workspace(project_id)

        # Assert
        assert ws1.workspace_dir == ws2.workspace_dir
        assert file_path.read_text() == '{"name": "modified"}'


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_workspace_returns_workspace_or_none() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_root:
        manager = LocalWorkspaceManager(workspaces_root=tmp_root, git_init=False)
        project_id = ProjectId("prj_01")

        # Act & Assert before creation
        assert await manager.get_workspace(project_id) is None

        # Act after creation
        created = await manager.ensure_workspace(project_id)
        found = await manager.get_workspace(project_id)

        # Assert
        assert found is not None
        assert found.workspace_dir == created.workspace_dir
        assert found.project_id == project_id


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_manifest_filters_ignored_directories() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_root:
        manager = LocalWorkspaceManager(workspaces_root=tmp_root, git_init=False)
        project_id = ProjectId("prj_01")
        ws = await manager.ensure_workspace(project_id)
        ws_path = Path(ws.workspace_dir)  # type: ignore[arg-type]

        # Create ignored and valid files
        (ws_path / "node_modules").mkdir()
        (ws_path / "node_modules" / "dummy.js").write_text("ignored")
        (ws_path / ".git").mkdir()
        (ws_path / ".git" / "config").write_text("ignored")
        (ws_path / ".next").mkdir()
        (ws_path / ".next" / "cache.json").write_text("ignored")

        (ws_path / "src").mkdir(exist_ok=True)
        (ws_path / "src" / "app.ts").write_text("valid")
        (ws_path / "README.md").write_text("valid")

        # Act
        manifest = await manager.get_manifest(ws)

        # Assert
        assert "src/app.ts" in manifest
        assert "README.md" in manifest
        assert ".gitignore" in manifest
        assert not any("node_modules" in f for f in manifest)
        assert not any(f.startswith(".git/") for f in manifest)
        assert not any(".next" in f for f in manifest)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_locking_prevents_concurrent_access() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_root:
        repo = FakeWorkspaceRepository()
        manager = LocalWorkspaceManager(
            workspaces_root=tmp_root,
            workspace_repo=repo,
            git_init=False,
        )
        project_id = ProjectId("prj_01")
        await manager.ensure_workspace(project_id)

        # Act 1: Initial state is unlocked
        assert await manager.is_locked(project_id) is False

        # Act 2: Acquire lock
        await manager.acquire_lock(project_id)
        assert await manager.is_locked(project_id) is True

        # Act 3: Acquiring lock again raises WorkspaceLockedError
        with pytest.raises(WorkspaceLockedError, match="currently locked"):
            await manager.acquire_lock(project_id)

        # Act 4: Release lock
        await manager.release_lock(project_id)
        assert await manager.is_locked(project_id) is False

        # Act 5: Can acquire lock again after release
        await manager.acquire_lock(project_id)
        assert await manager.is_locked(project_id) is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_acquire_lock_es_atomico_bajo_concurrencia() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_root:
        repo = SlowFakeWorkspaceRepository()
        manager = LocalWorkspaceManager(
            workspaces_root=tmp_root,
            workspace_repo=repo,
            git_init=False,
        )
        project_id = ProjectId("prj_01")
        await manager.ensure_workspace(project_id)

        # Act
        results = await asyncio.gather(
            manager.acquire_lock(project_id),
            manager.acquire_lock(project_id),
            manager.acquire_lock(project_id),
            return_exceptions=True,
        )

        # Assert
        acquired = [result for result in results if not isinstance(result, WorkspaceLockedError)]
        assert len(acquired) == 1
        assert sum(isinstance(result, WorkspaceLockedError) for result in results) == 2
        assert await manager.is_locked(project_id) is True
        assert repo.update_lock_calls == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_acquire_lock_detecta_conflicto_cas_de_otro_proceso() -> None:
    # Arrange — la fila existe en DB y otro proceso ya la bloqueó
    with tempfile.TemporaryDirectory() as tmp_root:
        repo = CasWorkspaceRepository()
        manager = LocalWorkspaceManager(
            workspaces_root=tmp_root,
            workspace_repo=repo,
            git_init=False,
        )
        project_id = ProjectId("prj_01")
        await manager.ensure_workspace(project_id)
        # Otro worker tomó el lock directamente en la DB
        await repo.update_lock(project_id, is_locked=True)

        # Act & Assert
        with pytest.raises(WorkspaceLockedError, match="currently locked"):
            await manager.acquire_lock(project_id)

        # Assert — el lock no queda registrado en memoria
        assert str(project_id) not in manager._in_memory_locks


@pytest.mark.unit
@pytest.mark.asyncio
async def test_acquire_lock_toma_control_de_lock_stale_de_proceso_muerto() -> None:
    # Arrange — un proceso murió hace más del umbral y dejó el lock clavado en la DB
    with tempfile.TemporaryDirectory() as tmp_root:
        repo = CasWorkspaceRepository()
        manager = LocalWorkspaceManager(
            workspaces_root=tmp_root,
            workspace_repo=repo,
            git_init=False,
        )
        project_id = ProjectId("prj_stale")
        await manager.ensure_workspace(project_id)
        await repo.update_lock(project_id, is_locked=True)
        stale_ws = repo.workspaces[str(project_id)]
        repo.workspaces[str(project_id)] = CodeWorkspace(
            id=stale_ws.id,
            project_id=stale_ws.project_id,
            status=stale_ws.status,
            workspace_dir=stale_ws.workspace_dir,
            is_locked=True,
            locked_at=datetime.now(UTC) - timedelta(minutes=LOCK_STALE_AFTER_MINUTES + 5),
            created_at=stale_ws.created_at,
            updated_at=stale_ws.updated_at,
        )

        # Act — el lock stale permite el takeover
        await manager.acquire_lock(project_id)

        # Assert
        assert str(project_id) in manager._in_memory_locks
        ws = repo.workspaces[str(project_id)]
        assert ws.is_locked is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_acquire_lock_procede_si_fila_aun_no_existe() -> None:
    # Arrange — primera generación: el repo crea la fila ya bloqueada (INSERT)
    with tempfile.TemporaryDirectory() as tmp_root:
        repo = CasWorkspaceRepository()
        manager = LocalWorkspaceManager(
            workspaces_root=tmp_root,
            workspace_repo=repo,
            git_init=False,
        )
        project_id = ProjectId("prj_new")

        # Act
        await manager.acquire_lock(project_id)

        # Assert — el lock queda en memoria y se persiste en ensure_workspace
        assert str(project_id) in manager._in_memory_locks
        ws = await manager.ensure_workspace(project_id)
        assert ws.is_locked is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_manifest_empty_or_nonexistent() -> None:
    # Arrange
    manager = LocalWorkspaceManager(workspaces_root="/tmp/fake_root", git_init=False)
    empty_ws = CodeWorkspace(
        id=WorkspaceId("ws_01"),
        project_id=ProjectId("prj_01"),
        workspace_dir=None,
    )
    nonexistent_ws = CodeWorkspace(
        id=WorkspaceId("ws_01"),
        project_id=ProjectId("prj_01"),
        workspace_dir="/nonexistent/directory/path",
    )

    # Act & Assert
    assert await manager.get_manifest(empty_ws) == ()
    assert await manager.get_manifest(nonexistent_ws) == ()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ensure_workspace_with_git_init() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_root:
        manager = LocalWorkspaceManager(workspaces_root=tmp_root, git_init=True)
        project_id = ProjectId("prj_git")

        # Act
        ws = await manager.ensure_workspace(project_id)

        # Assert
        assert ws.workspace_dir is not None
        assert Path(ws.workspace_dir).exists()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_workspace_repo_with_missing_dir() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_root:
        repo = FakeWorkspaceRepository()
        manager = LocalWorkspaceManager(workspaces_root=tmp_root, workspace_repo=repo, git_init=False)
        project_id = ProjectId("prj_01")
        ws = CodeWorkspace(
            id=WorkspaceId("ws_01"),
            project_id=project_id,
            workspace_dir="/nonexistent/path",
        )
        await repo.save(ws)

        # Act
        result = await manager.get_workspace(project_id)

        # Assert
        assert result is not None
        assert result.workspace_dir == "/nonexistent/path"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ensure_workspace_generates_agents_md_and_opencode_json() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_root:
        manager = LocalWorkspaceManager(workspaces_root=tmp_root, git_init=False)
        project_id = ProjectId("prj_01")

        # Act
        ws = await manager.ensure_workspace(project_id)

        # Assert
        assert ws.workspace_dir is not None
        ws_dir = Path(ws.workspace_dir)
        agents_path = ws_dir / "AGENTS.md"
        opencode_path = ws_dir / "opencode.json"

        assert agents_path.exists()
        assert opencode_path.exists()

        assert "AGENTS.md" in ws.manifest_files
        assert "opencode.json" in ws.manifest_files


@pytest.mark.unit
@pytest.mark.asyncio
async def test_agents_md_content_and_structure() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_root:
        manager = LocalWorkspaceManager(workspaces_root=tmp_root, git_init=False)
        project_id = ProjectId("prj_sdd_01")

        # Act
        ws = await manager.ensure_workspace(project_id)
        assert ws.workspace_dir is not None
        content = (Path(ws.workspace_dir) / "AGENTS.md").read_text(encoding="utf-8")

        # Assert — stack
        assert "Next.js 16" in content
        assert "Drizzle ORM" in content
        assert "Vitest" in content
        assert "TypeScript" in content
        assert "Tailwind CSS" in content
        assert "get_requirements" in content
        assert "get_activity_diagram" in content
        assert "src/" in content
        assert "tests/" in content

        # Assert — pipeline de validación obligatorio
        assert "tsc --noEmit" in content
        assert "eslint" in content
        assert "vitest run" in content
        assert "next build" in content

        # Assert — no detenerse hasta que todo esté verde
        assert "completada" in content
        assert "verde" in content

        # Assert — UI funcional y navegación
        assert "UI, Navegación y Diseño" in content
        assert "src/features/<slug>/" in content
        assert "feature-registry.ts" in content

        # Assert — TDD obligatorio con skill
        assert ".opencode/skills/tdd/SKILL.md" in content
        assert "Red-Green-Refactor" in content

        # Assert — navegación y APIs con tools MCP
        assert "token-savior" in content
        assert "context7" in content

        # Assert — anti-patrones
        assert "any" in content


@pytest.mark.unit
@pytest.mark.asyncio
async def test_opencode_json_content_and_permissions() -> None:
    import json

    # Arrange
    with tempfile.TemporaryDirectory() as tmp_root:
        manager = LocalWorkspaceManager(
            workspaces_root=tmp_root,
            git_init=False,
            mcp_url="http://127.0.0.1:8000/mcp",
        )
        project_id = ProjectId("prj_test_perms")

        # Act
        ws = await manager.ensure_workspace(project_id)
        assert ws.workspace_dir is not None
        raw_json = (Path(ws.workspace_dir) / "opencode.json").read_text(encoding="utf-8")
        config = json.loads(raw_json)

        # Assert
        assert config["instructions"] == ["AGENTS.md"]
        assert config["plugin"] == ["@dietrichgebert/ponytail"]

        assert "kosmo-context" in config["mcp"]
        assert config["mcp"]["kosmo-context"]["url"] == "http://127.0.0.1:8000/mcp"
        assert config["mcp"]["kosmo-context"]["environment"]["KOSMO_PROJECT_ID"] == "prj_test_perms"

        # MCP token-savior (local, uvx)
        token_savior = config["mcp"]["token-savior"]
        assert token_savior["type"] == "local"
        assert token_savior["command"] == ["uvx", "--from", "token-savior-recall", "token-savior"]
        assert token_savior["environment"]["WORKSPACE_ROOTS"] == str(Path(tmp_root) / "prj_test_perms")
        assert token_savior["environment"]["TOKEN_SAVIOR_CLIENT"] == "opencode"

        # MCP context7 (remote)
        assert config["mcp"]["context7"]["type"] == "remote"
        assert config["mcp"]["context7"]["url"] == "https://mcp.context7.com/mcp"

        # Permissions: read
        assert config["permission"]["read"] == {"*": "allow"}

        # Permissions: edit en todo el workspace para edición de archivos.
        # bash y external_directory restringidos (deny) para mitigar ejecución arbitraria (VULN-010).
        assert config["permission"]["edit"] == {"*": "allow"}
        assert config["permission"]["bash"] == "deny"
        assert config["permission"]["external_directory"] == "deny"
        assert config["permission"]["websearch"] == "allow"

        # Tools: la pregunta interactiva está deshabilitada (flujo headless)
        assert config["tools"] == {"question": False}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ensure_workspace_heals_missing_permissions_in_existing_opencode_json() -> None:
    import json

    with tempfile.TemporaryDirectory() as tmp_root:
        manager = LocalWorkspaceManager(workspaces_root=tmp_root, git_init=False)
        project_id = ProjectId("prj_healing")

        # Create workspace with legacy opencode.json missing external_directory and insecure bash
        ws = await manager.ensure_workspace(project_id)
        assert ws.workspace_dir is not None
        opencode_file = Path(ws.workspace_dir) / "opencode.json"
        legacy_cfg = {
            "instructions": ["AGENTS.md"],
            "permission": {
                "read": {"*": "allow"},
                "edit": {"*": "allow"},
                "bash": {"*": "allow"},
            },
        }
        opencode_file.write_text(json.dumps(legacy_cfg), encoding="utf-8")

        # Second ensure_workspace call should heal insecure bash and missing external_directory
        await manager.ensure_workspace(project_id)

        healed_cfg = json.loads(opencode_file.read_text(encoding="utf-8"))
        assert healed_cfg["permission"]["read"] == {"*": "allow"}
        assert healed_cfg["permission"]["edit"] == {"*": "allow"}
        assert healed_cfg["permission"]["bash"] == "deny"
        assert healed_cfg["permission"]["external_directory"] == "deny"
        assert healed_cfg["permission"]["websearch"] == "allow"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ensure_workspace_generates_tdd_skill() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_root:
        manager = LocalWorkspaceManager(workspaces_root=tmp_root, git_init=False)
        project_id = ProjectId("prj_tdd_skill")

        # Act
        ws = await manager.ensure_workspace(project_id)

        # Assert
        assert ws.workspace_dir is not None
        ws_dir = Path(ws.workspace_dir)
        skill_path = ws_dir / ".opencode" / "skills" / "tdd" / "SKILL.md"

        assert skill_path.exists()
        assert ".opencode/skills/tdd/SKILL.md" in ws.manifest_files

        content = skill_path.read_text(encoding="utf-8")
        assert "name: tdd" in content
        assert "Vitest" in content
        assert "AAA" in content
        assert "Red-Green-Refactor" in content
        assert "describe(" in content or "it(" in content


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ensure_workspace_preserves_custom_tdd_skill() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_root:
        manager = LocalWorkspaceManager(workspaces_root=tmp_root, git_init=False)
        project_id = ProjectId("prj_tdd_custom")

        # First call creates the skill
        ws1 = await manager.ensure_workspace(project_id)
        assert ws1.workspace_dir is not None
        skill_path = Path(ws1.workspace_dir) / ".opencode" / "skills" / "tdd" / "SKILL.md"
        skill_path.write_text("---\nname: tdd\n---\n# Custom skill\n", encoding="utf-8")

        # Act: second call must not overwrite
        await manager.ensure_workspace(project_id)

        # Assert
        assert skill_path.read_text(encoding="utf-8") == "---\nname: tdd\n---\n# Custom skill\n"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ensure_workspace_uses_project_name_from_repo() -> None:
    from kosmo.contracts.sdd.ids import UserId
    from kosmo.contracts.sdd.project import Project
    from tests.unit.fakes import InMemoryProjectRepository

    # Arrange
    with tempfile.TemporaryDirectory() as tmp_root:
        project_repo = InMemoryProjectRepository()
        project = Project(
            id=ProjectId("prj_gasto_justo"),
            name="GastoJusto",
            slug="gasto-justo",
            description="Control de gastos compartidos",
            owner_id=UserId("usr_01"),
        )
        await project_repo.save(project)

        manager = LocalWorkspaceManager(
            workspaces_root=tmp_root,
            git_init=False,
            project_repo=project_repo,
        )

        # Act
        ws = await manager.ensure_workspace(project.id)
        assert ws.workspace_dir is not None
        content = (Path(ws.workspace_dir) / "AGENTS.md").read_text(encoding="utf-8")

        # Assert
        assert "GastoJusto" in content


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ensure_workspace_preserves_custom_agents_md_and_opencode_json() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_root:
        manager = LocalWorkspaceManager(workspaces_root=tmp_root, git_init=False)
        project_id = ProjectId("prj_custom")

        # First call creates the workspace
        ws1 = await manager.ensure_workspace(project_id)
        assert ws1.workspace_dir is not None
        ws_dir = Path(ws1.workspace_dir)

        # Custom modifications
        (ws_dir / "AGENTS.md").write_text("# Custom Agents Config", encoding="utf-8")
        (ws_dir / "opencode.json").write_text('{"custom": true}', encoding="utf-8")

        # Act: Second call should not overwrite
        ws2 = await manager.ensure_workspace(project_id)

        # Assert
        assert ws1.workspace_dir == ws2.workspace_dir
        assert (ws_dir / "AGENTS.md").read_text(encoding="utf-8") == "# Custom Agents Config"
        assert (ws_dir / "opencode.json").read_text(encoding="utf-8") == '{"custom": true}'


@pytest.mark.unit
@pytest.mark.asyncio
async def test_commit_workspace_creates_git_commit_and_updates_manifest() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_root:
        repo = FakeWorkspaceRepository()
        manager = LocalWorkspaceManager(
            workspaces_root=tmp_root,
            workspace_repo=repo,
            git_init=True,
        )
        project_id = ProjectId("prj_commit_test")

        ws = await manager.ensure_workspace(project_id)
        assert ws.workspace_dir is not None
        ws_dir = Path(ws.workspace_dir)

        # Crear nuevo archivo para commitear
        (ws_dir / "src").mkdir(parents=True, exist_ok=True)
        (ws_dir / "src" / "feature.ts").write_text("export const val = 42;", encoding="utf-8")

        # Act
        committed = await manager.commit_workspace(project_id, "feat: implement feature C01")

        # Assert
        assert committed is not None
        assert len(committed) == 40
        updated_ws = await manager.get_workspace(project_id)
        assert updated_ws is not None
        assert "src/feature.ts" in updated_ws.manifest_files


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rollback_workspace_reverts_uncommitted_changes() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_root:
        repo = FakeWorkspaceRepository()
        manager = LocalWorkspaceManager(
            workspaces_root=tmp_root,
            workspace_repo=repo,
            git_init=True,
        )
        project_id = ProjectId("prj_rollback_test")

        ws = await manager.ensure_workspace(project_id)
        assert ws.workspace_dir is not None
        ws_dir = Path(ws.workspace_dir)

        # Modificar archivo inicial
        agents_file = ws_dir / "AGENTS.md"
        initial_content = agents_file.read_text(encoding="utf-8")
        agents_file.write_text("bad broken agent config", encoding="utf-8")

        # Crear archivo no rastreado
        untracked = ws_dir / "bad_code.ts"
        untracked.write_text("throw new Error()", encoding="utf-8")

        # Act: Ejecutar rollback
        await manager.rollback_workspace(project_id)

        # Assert
        assert agents_file.read_text(encoding="utf-8") == initial_content
        assert not untracked.exists()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_workspace_removes_directory() -> None:
    with tempfile.TemporaryDirectory() as tmp_root:
        manager = LocalWorkspaceManager(workspaces_root=tmp_root, git_init=False)
        project_id = ProjectId("prj_delete_workspace")
        workspace = await manager.ensure_workspace(project_id)
        assert workspace.workspace_dir is not None

        await manager.delete_workspace(project_id)

        assert not Path(workspace.workspace_dir).exists()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_workspace_waits_asynchronously_before_retrying_rmtree() -> None:
    with tempfile.TemporaryDirectory() as tmp_root:
        manager = LocalWorkspaceManager(workspaces_root=tmp_root, git_init=False)
        project_id = ProjectId("prj_delete_workspace_retry")
        workspace = await manager.ensure_workspace(project_id)
        assert workspace.workspace_dir is not None

        real_rmtree = __import__("shutil").rmtree
        attempts = 0

        def rmtree_with_transient_failure(path: Path) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise OSError("locked")
            real_rmtree(path)

        async_sleep = AsyncMock()
        with (
            patch(
                "kosmo.infrastructure.codegen.workspace.shutil.rmtree",
                side_effect=rmtree_with_transient_failure,
            ) as rmtree,
            patch("kosmo.infrastructure.codegen.workspace.asyncio.sleep", async_sleep),
        ):
            await manager.delete_workspace(project_id)

        assert rmtree.call_count == 2
        async_sleep.assert_awaited_once_with(0.3)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_commit_workspace_propaga_error_de_git_add() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_root:
        manager = LocalWorkspaceManager(workspaces_root=tmp_root, git_init=True)
        project_id = ProjectId("prj_commit_err_add")
        await manager.ensure_workspace(project_id)

        # Act & Assert
        with (
            patch(
                "kosmo.infrastructure.codegen.workspace.git_add_async",
                side_effect=GitError("fallo de git add"),
            ),
            pytest.raises(GitError, match="fallo de git add"),
        ):
            await manager.commit_workspace(project_id, "feat: x")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_commit_workspace_propaga_error_de_git_commit() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_root:
        manager = LocalWorkspaceManager(workspaces_root=tmp_root, git_init=True)
        project_id = ProjectId("prj_commit_err_commit")
        await manager.ensure_workspace(project_id)

        # Act & Assert
        with (
            patch(
                "kosmo.infrastructure.codegen.workspace.git_commit_async",
                side_effect=GitError("fallo de git commit"),
            ),
            pytest.raises(GitError, match="fallo de git commit"),
        ):
            await manager.commit_workspace(project_id, "feat: x")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rollback_workspace_propaga_error_de_git() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_root:
        manager = LocalWorkspaceManager(workspaces_root=tmp_root, git_init=True)
        project_id = ProjectId("prj_rollback_err")
        await manager.ensure_workspace(project_id)

        # Act & Assert
        with (
            patch(
                "kosmo.infrastructure.codegen.workspace.git_rollback_async",
                side_effect=GitError("fallo de git reset"),
            ),
            pytest.raises(GitError, match="fallo de git reset"),
        ):
            await manager.rollback_workspace(project_id)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ensure_workspace_runs_npm_install_when_created_new() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_root:
        code_runner = FakeCodeRunner()
        manager = LocalWorkspaceManager(
            workspaces_root=tmp_root,
            git_init=False,
            code_runner=code_runner,
        )
        project_id = ProjectId("prj_install_new")

        # Act
        ws = await manager.ensure_workspace(project_id)

        # Assert — npm install se ejecuta una sola vez con el timeout de instalación
        assert ws.status == WorkspaceStatus.READY
        assert code_runner.commands == [("npm install", 600)]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_remove_feature_paths_elimina_slice_ruta_y_tests() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_root:
        manager = LocalWorkspaceManager(workspaces_root=tmp_root, git_init=False)
        project_id = ProjectId("prj_remove_paths")
        ws = await manager.ensure_workspace(project_id)
        assert ws.workspace_dir is not None
        ws_dir = Path(ws.workspace_dir)

        (ws_dir / "src" / "features" / "registrar-productos" / "logic.ts").parent.mkdir(parents=True)
        (ws_dir / "src" / "features" / "registrar-productos" / "logic.ts").write_text("export const x = 1;")
        (ws_dir / "src" / "app" / "registrar-productos").mkdir(parents=True)
        (ws_dir / "src" / "app" / "registrar-productos" / "page.tsx").write_text("export default function Page() {}")
        (ws_dir / "tests").mkdir(exist_ok=True)
        (ws_dir / "tests" / "registrar-productos.test.ts").write_text(
            "import { x } from '../src/features/registrar-productos/logic';"
        )
        (ws_dir / "tests" / "otra-feature.test.ts").write_text("export {};")

        # Act
        removed = await manager.remove_feature_paths(project_id, "registrar-productos")

        # Assert — slice, ruta y tests de la feature desaparecen; la otra feature queda
        assert not (ws_dir / "src" / "features" / "registrar-productos").exists()
        assert not (ws_dir / "src" / "app" / "registrar-productos").exists()
        assert not (ws_dir / "tests" / "registrar-productos.test.ts").exists()
        assert (ws_dir / "tests" / "otra-feature.test.ts").exists()
        assert "src/features/registrar-productos" in removed
        assert "src/app/registrar-productos" in removed
        assert "tests/registrar-productos.test.ts" in removed


@pytest.mark.unit
@pytest.mark.asyncio
async def test_remove_feature_paths_elimina_layouts_del_agente_en_raiz() -> None:
    # Arrange — el agente generó el código fuera del layout documentado (src/<slug>.ts)
    with tempfile.TemporaryDirectory() as tmp_root:
        manager = LocalWorkspaceManager(workspaces_root=tmp_root, git_init=False)
        project_id = ProjectId("prj_remove_raiz")
        ws = await manager.ensure_workspace(project_id)
        assert ws.workspace_dir is not None
        ws_dir = Path(ws.workspace_dir)

        (ws_dir / "src" / "registrar-ventas-con-detalle.ts").write_text("export const x = 1;")
        (ws_dir / "src" / "registrar-ventas-con-detalle.helper.ts").write_text("export const y = 2;")
        (ws_dir / "tests").mkdir(exist_ok=True)
        (ws_dir / "tests" / "registrar-ventas-con-detalle.test.ts").write_text("import {};")
        (ws_dir / "src" / "otra-cosa.ts").write_text("export const z = 3;")

        # Act
        await manager.remove_feature_paths(project_id, "registrar-ventas-con-detalle")

        # Assert — todos los artefactos de la feature desaparecen; lo ajeno queda
        assert not (ws_dir / "src" / "registrar-ventas-con-detalle.ts").exists()
        assert not (ws_dir / "src" / "registrar-ventas-con-detalle.helper.ts").exists()
        assert not (ws_dir / "tests" / "registrar-ventas-con-detalle.test.ts").exists()
        assert (ws_dir / "src" / "otra-cosa.ts").exists()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_remove_feature_paths_no_toca_slugs_hermanos_mas_largos() -> None:
    # Arrange — existe una feature con slug prefijo de otra (registrar-productos vs
    # registrar-productos-con-su-precio): borrar la corta no debe tocar la larga
    with tempfile.TemporaryDirectory() as tmp_root:
        manager = LocalWorkspaceManager(workspaces_root=tmp_root, git_init=False)
        project_id = ProjectId("prj_remove_hermanos")
        ws = await manager.ensure_workspace(project_id)
        assert ws.workspace_dir is not None
        ws_dir = Path(ws.workspace_dir)

        (ws_dir / "src" / "registrar-productos.ts").write_text("export const corta = 1;")
        (ws_dir / "src" / "registrar-productos-con-su-precio.ts").write_text("export const larga = 2;")
        (ws_dir / "tests").mkdir(exist_ok=True)
        (ws_dir / "tests" / "registrar-productos-con-su-precio.test.ts").write_text("import {};")

        # Act — se elimina la feature "registrar-productos" (la corta)
        removed = await manager.remove_feature_paths(project_id, "registrar-productos")

        # Assert — la larga (registrar-productos-con-su-precio) queda intacta
        assert not (ws_dir / "src" / "registrar-productos.ts").exists()
        assert (ws_dir / "src" / "registrar-productos-con-su-precio.ts").exists()
        assert (ws_dir / "tests" / "registrar-productos-con-su-precio.test.ts").exists()
        assert "src/registrar-productos.ts" in removed


@pytest.mark.unit
@pytest.mark.asyncio
async def test_remove_feature_paths_sin_archivos_retorna_vacio() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_root:
        manager = LocalWorkspaceManager(workspaces_root=tmp_root, git_init=False)
        project_id = ProjectId("prj_remove_vacio")
        await manager.ensure_workspace(project_id)

        # Act
        removed = await manager.remove_feature_paths(project_id, "feature-inexistente")

        # Assert
        assert removed == ()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_text_file_aplica_transformacion() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_root:
        manager = LocalWorkspaceManager(workspaces_root=tmp_root, git_init=False)
        project_id = ProjectId("prj_update_text")
        ws = await manager.ensure_workspace(project_id)
        assert ws.workspace_dir is not None
        ws_dir = Path(ws.workspace_dir)
        registry = ws_dir / "src" / "lib" / "feature-registry.ts"
        registry.write_text("import { x } from '@/features/mi-feature/manifest';\n\nx,\n", encoding="utf-8")

        # Act — transformación que elimina la referencia de la feature
        await manager.update_text_file(
            project_id,
            "src/lib/feature-registry.ts",
            lambda content: content.replace("mi-feature", "ELIMINADA"),
        )

        # Assert
        assert "mi-feature" not in registry.read_text(encoding="utf-8")
        assert "ELIMINADA" in registry.read_text(encoding="utf-8")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_text_file_no_escribe_si_no_cambia() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_root:
        manager = LocalWorkspaceManager(workspaces_root=tmp_root, git_init=False)
        project_id = ProjectId("prj_update_noop")
        ws = await manager.ensure_workspace(project_id)
        assert ws.workspace_dir is not None
        ws_dir = Path(ws.workspace_dir)
        registry = ws_dir / "src" / "lib" / "feature-registry.ts"
        original = registry.read_text(encoding="utf-8")

        # Act — transformación identidad
        await manager.update_text_file(project_id, "src/lib/feature-registry.ts", lambda content: content)

        # Assert — el archivo no se reescribe (mtime estable)
        assert registry.read_text(encoding="utf-8") == original


@pytest.mark.unit
@pytest.mark.asyncio
async def test_revert_commit_restaura_archivos_eliminados() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_root:
        manager = LocalWorkspaceManager(workspaces_root=tmp_root, git_init=True)
        project_id = ProjectId("prj_revert")
        ws = await manager.ensure_workspace(project_id)
        assert ws.workspace_dir is not None
        ws_dir = Path(ws.workspace_dir)

        target = ws_dir / "src" / "extra.ts"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("export const x = 1;", encoding="utf-8")
        commit_hash = await manager.commit_workspace(project_id, "feat: agregar extra.ts")
        assert commit_hash is not None

        # Borrar y commitear el borrado
        target.unlink()
        delete_hash = await manager.commit_workspace(project_id, "feat: eliminar extra.ts")
        assert delete_hash is not None
        assert not target.exists()

        # Act — revertir el commit de borrado
        await manager.revert_commit(project_id, delete_hash)

        # Assert — el archivo vuelve
        assert target.exists()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ensure_workspace_skips_npm_install_when_reusing_workspace() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_root:
        code_runner = FakeCodeRunner()
        manager = LocalWorkspaceManager(
            workspaces_root=tmp_root,
            git_init=False,
            code_runner=code_runner,
        )
        project_id = ProjectId("prj_install_reuse")
        await manager.ensure_workspace(project_id)

        # Act — segunda llamada sobre un workspace existente
        await manager.ensure_workspace(project_id)

        # Assert — no se reinstala al reutilizar
        assert code_runner.commands == [("npm install", 600)]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ensure_workspace_continues_when_npm_install_fails() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_root:
        code_runner = FakeCodeRunner(install_success=False)
        manager = LocalWorkspaceManager(
            workspaces_root=tmp_root,
            git_init=False,
            code_runner=code_runner,
        )
        project_id = ProjectId("prj_install_fail")

        # Act — el fallo de npm install no bloquea la creación del workspace
        ws = await manager.ensure_workspace(project_id)

        # Assert
        assert ws.status == WorkspaceStatus.READY
        assert ws.workspace_dir is not None
        assert Path(ws.workspace_dir).exists()
        assert code_runner.commands == [("npm install", 600)]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ensure_workspace_initializes_site_ts_with_dashboard_archetype() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_root:
        project_repo = InMemoryProjectRepository()
        document_repo = InMemoryDocumentRepository()
        project_id = ProjectId("prj_dashboard_01")
        await project_repo.save(
            Project(
                id=project_id,
                name="GastoJusto",
                slug="gasto-justo",
                description="Control de gastos y finanzas personales",
                owner_id=UserId("usr_01"),
            )
        )
        await document_repo.save_discovery(
            project_id,
            markdown_to_document(
                "# Visión del producto\n\n"
                "Sistema para registrar gastos, monitorear presupuestos y ver balances y reportes."
            ),
        )
        manager = LocalWorkspaceManager(
            workspaces_root=tmp_root,
            git_init=False,
            project_repo=project_repo,
            document_repo=document_repo,
        )

        # Act
        ws = await manager.ensure_workspace(project_id)

        # Assert
        assert ws.workspace_dir is not None
        site_file = Path(ws.workspace_dir) / "src" / "lib" / "site.ts"
        assert site_file.exists()
        content = site_file.read_text(encoding="utf-8")
        assert 'name: "GastoJusto"' in content
        assert 'archetype: "dashboard"' in content
        assert 'primaryColor: "#006bbb"' in content


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ensure_workspace_initializes_site_ts_with_storefront_archetype() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_root:
        project_repo = InMemoryProjectRepository()
        document_repo = InMemoryDocumentRepository()
        project_id = ProjectId("prj_store_01")
        await project_repo.save(
            Project(
                id=project_id,
                name="Tienda Ropa",
                slug="tienda-ropa",
                description="Catálogo y venta de prendas",
                owner_id=UserId("usr_01"),
            )
        )
        await document_repo.save_discovery(
            project_id,
            markdown_to_document(
                "# Visión del producto\n\nCatálogo de productos para compras de clientes con carrito de compras."
            ),
        )
        manager = LocalWorkspaceManager(
            workspaces_root=tmp_root,
            git_init=False,
            project_repo=project_repo,
            document_repo=document_repo,
        )

        # Act
        ws = await manager.ensure_workspace(project_id)

        # Assert
        assert ws.workspace_dir is not None
        site_file = Path(ws.workspace_dir) / "src" / "lib" / "site.ts"
        assert site_file.exists()
        content = site_file.read_text(encoding="utf-8")
        assert 'name: "Tienda Ropa"' in content
        assert 'archetype: "storefront"' in content
        assert 'primaryColor: "#00835c"' in content


@pytest.mark.unit
@pytest.mark.asyncio
async def test_workspace_manager_delegates_manifest_to_thread() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_root = Path(tmp_dir)
        manager = LocalWorkspaceManager(workspaces_root=tmp_root, git_init=False)
        project_id = ProjectId("prj_to_thread_test")
        ws = await manager.ensure_workspace(project_id)

        with patch("asyncio.to_thread", wraps=asyncio.to_thread) as spy_to_thread:
            # Act
            manifest = await manager.get_manifest(ws)

            # Assert
            assert isinstance(manifest, tuple)
            spy_to_thread.assert_called_once()


@pytest.mark.unit
def test_local_file_system_reader_lists_and_reads_files() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_root = Path(tmp_dir)
        sub_dir = tmp_root / "src" / "app"
        sub_dir.mkdir(parents=True)
        file_a = sub_dir / "page.tsx"
        file_a.write_text("export default function Page() {}", encoding="utf-8")

        reader = LocalFileSystemReader()

        # Act
        files = reader.list_files(tmp_root)
        content = reader.read_text(file_a)
        non_existent = reader.read_text(tmp_root / "no_such_file.txt")

        # Assert
        assert "src/app/page.tsx" in [f.replace("\\", "/") for f in files]
        assert content == "export default function Page() {}"
        assert non_existent is None


@pytest.mark.unit
def test_local_workspace_manager_implements_file_system_reader() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_dir:
        manager = LocalWorkspaceManager(workspaces_root=tmp_dir, git_init=False)

        # Assert
        assert isinstance(manager, FileSystemReader)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_workspace_manager_rejects_escaping_project_id() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        manager = LocalWorkspaceManager(workspaces_root=tmp_dir, git_init=False)
        invalid_id = ProjectId("../../escaping_project")

        with pytest.raises(ValueError, match="Workspace path escapes configured root"):
            await manager.ensure_workspace(invalid_id)

        with pytest.raises(ValueError, match="Workspace path escapes configured root"):
            await manager.commit_workspace(invalid_id, "test")

        with pytest.raises(ValueError, match="Workspace path escapes configured root"):
            await manager.remove_feature_paths(invalid_id, "slug")

        with pytest.raises(ValueError, match="Workspace path escapes configured root"):
            await manager.delete_workspace(invalid_id)
