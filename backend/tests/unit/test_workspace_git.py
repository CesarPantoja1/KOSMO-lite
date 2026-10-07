from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from kosmo.contracts.integrations.git import GitWorkspacePort
from kosmo.infrastructure.git import (
    GitError,
    LocalGitWorkspaceAdapter,
    git_add,
    git_add_async,
    git_build_authenticated_url,
    git_commit,
    git_commit_async,
    git_current_branch,
    git_has_commits,
    git_head_hash,
    git_head_hash_async,
    git_init,
    git_init_async,
    git_is_clean,
    git_is_clean_async,
    git_push,
    git_remote_add_or_update,
    git_remote_get_url,
    git_revert_commit,
    git_rollback,
    git_rollback_async,
    git_status,
    run_git_async,
)


@pytest.mark.unit
def test_git_init_creates_repo_with_branch_and_config() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir)
        git_init(path, initial_branch="main", user_name="Test Bot", user_email="test@bot.com")

        assert (path / ".git").exists()
        assert (path / ".git").is_dir()

        # Verificar configuración de usuario
        res_name = subprocess.run(
            ["git", "config", "user.name"],
            cwd=path,
            capture_output=True,
            text=True,
            check=False,
        )
        res_email = subprocess.run(
            ["git", "config", "user.email"],
            cwd=path,
            capture_output=True,
            text=True,
            check=False,
        )
        assert res_name.stdout.strip() == "Test Bot"
        assert res_email.stdout.strip() == "test@bot.com"


@pytest.mark.unit
def test_git_add_and_commit() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir)
        git_init(path)

        # Crear archivo
        file1 = path / "hello.txt"
        file1.write_text("Hello Git!", encoding="utf-8")

        assert not git_has_commits(path)
        assert not git_is_clean(path)

        # Staging y commit
        git_add(path)
        committed = git_commit(path, "feat: initial commit")

        assert committed is True
        assert git_has_commits(path)
        assert git_is_clean(path)


@pytest.mark.unit
def test_git_commit_no_changes_returns_false() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir)
        git_init(path)

        file1 = path / "hello.txt"
        file1.write_text("Hello Git!", encoding="utf-8")
        git_add(path)
        git_commit(path, "feat: first commit")

        # Intentar commitear sin cambios
        second_commit = git_commit(path, "feat: second commit without changes")
        assert second_commit is False


@pytest.mark.unit
def test_git_head_hash_returns_commit_hash_or_none() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir)
        git_init(path)

        # Sin commits -> None
        assert git_head_hash(path) is None

        (path / "hello.txt").write_text("Hello Git!", encoding="utf-8")
        git_add(path)
        git_commit(path, "feat: initial commit")

        # Con commits -> hash de 40 chars (SHA-1)
        head_hash = git_head_hash(path)
        assert head_hash is not None
        assert len(head_hash) == 40


@pytest.mark.unit
def test_git_revert_commit_restaura_cambios_sin_tocar_commits_posteriores() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir)
        git_init(path)

        (path / "base.txt").write_text("base", encoding="utf-8")
        (path / "extra.ts").write_text("export const x = 1;", encoding="utf-8")
        git_add(path)
        git_commit(path, "feat: base con extra")

        # Commit de borrado (a revertir): elimina extra.ts
        (path / "extra.ts").unlink()
        git_add(path)
        git_commit(path, "feat(extra): remove feature")
        delete_commit = git_head_hash(path)
        assert delete_commit is not None
        assert not (path / "extra.ts").exists()

        # Commit posterior (no debe tocarse)
        (path / "posterior.txt").write_text("posterior", encoding="utf-8")
        git_add(path)
        git_commit(path, "feat: posterior")

        # Act — revertir el commit de borrado
        git_revert_commit(path, delete_commit)

        # Assert — el archivo eliminado vuelve, el commit posterior sigue
        assert (path / "extra.ts").exists()
        assert (path / "posterior.txt").exists()
        assert git_is_clean(path)


@pytest.mark.unit
def test_git_rollback_reverts_modifications_and_removes_untracked() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir)
        git_init(path)

        # Estado inicial limpio con un commit
        tracked_file = path / "tracked.txt"
        tracked_file.write_text("version 1.0", encoding="utf-8")
        git_add(path)
        git_commit(path, "chore: initial version")

        # Realizar cambios fallidos durante un reintento
        tracked_file.write_text("broken modifications", encoding="utf-8")
        untracked_file = path / "untracked.ts"
        untracked_file.write_text("bad code", encoding="utf-8")
        untracked_dir = path / "temp_folder"
        untracked_dir.mkdir()
        (untracked_dir / "nested.ts").write_text("nested bad code", encoding="utf-8")

        assert not git_is_clean(path)

        # Act: Ejecutar rollback
        git_rollback(path)

        # Assert: Todo volvió al estado del último commit exitoso
        assert tracked_file.read_text(encoding="utf-8") == "version 1.0"
        assert not untracked_file.exists()
        assert not untracked_dir.exists()
        assert git_is_clean(path)


@pytest.mark.unit
def test_git_rollback_when_no_head_removes_untracked() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir)
        git_init(path)

        untracked_file = path / "draft.txt"
        untracked_file.write_text("draft content", encoding="utf-8")

        # Rollback sin commits
        git_rollback(path)

        assert not untracked_file.exists()


@pytest.mark.unit
def test_git_status_and_is_clean() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir)
        git_init(path)

        assert git_is_clean(path)

        (path / "file.txt").write_text("content", encoding="utf-8")
        status = git_status(path)
        assert "file.txt" in status
        assert not git_is_clean(path)


@pytest.mark.unit
def test_git_operations_on_nonexistent_dir_raise_git_error() -> None:
    non_existent = Path("/nonexistent/path/for/kosmo/git/tests")

    with pytest.raises(GitError, match="El directorio del workspace no existe"):
        git_add(non_existent)

    with pytest.raises(GitError, match="El directorio del workspace no existe"):
        git_status(non_existent)


@pytest.mark.unit
def test_git_remote_add_and_update() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir)
        git_init(path)

        assert git_remote_get_url(path, "origin") is None

        # Agregar remoto inicial
        git_remote_add_or_update(path, name="origin", url="https://github.com/test-org/test-repo.git")
        assert git_remote_get_url(path, "origin") == "https://github.com/test-org/test-repo.git"

        # Actualizar remoto existente
        git_remote_add_or_update(path, name="origin", url="https://github.com/test-org/updated-repo.git")
        assert git_remote_get_url(path, "origin") == "https://github.com/test-org/updated-repo.git"


@pytest.mark.unit
def test_git_remote_add_empty_url_raises() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir)
        git_init(path)

        with pytest.raises(GitError, match="La URL del repositorio remoto no puede estar vacía"):
            git_remote_add_or_update(path, name="origin", url="")

        with pytest.raises(GitError, match="La URL del repositorio remoto no puede estar vacía"):
            git_remote_add_or_update(path, name="origin", url="   ")


@pytest.mark.unit
def test_git_current_branch() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir)
        git_init(path, initial_branch="main")
        (path / "readme.md").write_text("# Test", encoding="utf-8")
        git_add(path)
        git_commit(path, "feat: init")

        assert git_current_branch(path) == "main"

        # Crear y cambiar a otra rama
        subprocess.run(["git", "checkout", "-b", "feature/test-branch"], cwd=path, check=True)
        assert git_current_branch(path) == "feature/test-branch"


@pytest.mark.unit
def test_git_build_authenticated_url() -> None:
    # URL estándar HTTPS
    auth_url = git_build_authenticated_url("https://github.com/owner/project.git", "ghp_secretToken123")
    assert auth_url == "https://x-access-token:ghp_secretToken123@github.com/owner/project.git"

    # URL con credenciales previas incrustadas
    auth_url_clean = git_build_authenticated_url("https://old_user:old_token@github.com/owner/project.git", "ghp_new")
    assert auth_url_clean == "https://x-access-token:ghp_new@github.com/owner/project.git"

    auth_url_encoded = git_build_authenticated_url("https://github.com/owner/project.git", "ghp_token:@value")
    assert auth_url_encoded == "https://x-access-token:ghp_token%3A%40value@github.com/owner/project.git"

    local_auth_url = git_build_authenticated_url("http://localhost:3000/owner/project.git", "local_token")
    assert local_auth_url == "http://x-access-token:local_token@localhost:3000/owner/project.git"

    with pytest.raises(GitError, match="Solo se permiten URLs HTTPS fuera"):
        git_build_authenticated_url("http://github.com/owner/project.git", "ghp_secretToken123")

    # Token vacío
    with pytest.raises(GitError, match="El token de acceso no puede estar vacío"):
        git_build_authenticated_url("https://github.com/owner/project.git", "")


@pytest.mark.unit
def test_git_push_to_local_bare_repository() -> None:
    with tempfile.TemporaryDirectory() as bare_dir, tempfile.TemporaryDirectory() as ws_dir:
        bare_path = Path(bare_dir)
        ws_path = Path(ws_dir)

        # Inicializar repositorio remoto bare local
        subprocess.run(["git", "init", "--bare", "-b", "main"], cwd=bare_path, check=True)

        # Inicializar workspace local y crear commit
        git_init(ws_path, initial_branch="main")
        (ws_path / "app.ts").write_text("console.log('kosmo');", encoding="utf-8")
        git_add(ws_path)
        git_commit(ws_path, "feat: initial app code")
        local_head = git_head_hash(ws_path)
        assert local_head is not None

        # Configurar remoto y hacer push
        git_remote_add_or_update(ws_path, name="origin", url=str(bare_path.resolve()))
        pushed_sha = git_push(ws_path, remote="origin", branch="main", set_upstream=True)

        assert pushed_sha == local_head

        # Verificar que el remoto bare recibió el commit en main
        res_bare = subprocess.run(
            ["git", "rev-parse", "main"], cwd=bare_path, capture_output=True, text=True, check=True
        )
        assert res_bare.stdout.strip() == local_head

        # Push incremental subsecuente
        (ws_path / "utils.ts").write_text("export const add = (a: number, b: number) => a + b;", encoding="utf-8")
        git_add(ws_path)
        git_commit(ws_path, "feat: add utils")
        second_head = git_head_hash(ws_path)

        second_pushed_sha = git_push(ws_path, remote="origin", branch="main", force_with_lease=True)
        assert second_pushed_sha == second_head

        res_bare_second = subprocess.run(
            ["git", "rev-parse", "main"], cwd=bare_path, capture_output=True, text=True, check=True
        )
        assert res_bare_second.stdout.strip() == second_head


@pytest.mark.unit
def test_git_push_without_commits_raises() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir)
        git_init(path)

        with pytest.raises(GitError, match="El repositorio no tiene commits para enviar al remoto"):
            git_push(path, remote="origin")


@pytest.mark.unit
def test_git_push_token_sanitization_in_error() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir)
        git_init(path)
        (path / "file.txt").write_text("data", encoding="utf-8")
        git_add(path)
        git_commit(path, "feat: commit")

        # Intentar push a una URL inalcanzable con token secreto
        secret_token = "ghp_SuperSecretOAuthToken999"
        invalid_url = "https://github.com/nonexistent-org-999999/nonexistent-repo-999999.git"

        with pytest.raises(GitError) as exc_info:
            git_push(path, remote=invalid_url, token=secret_token)

        err_text = str(exc_info.value)
        # El token en claro NO debe aparecer nunca en el mensaje de error
        assert secret_token not in err_text
        # Debe haberse enmascarado
        assert "https://***@" in err_text


@pytest.mark.unit
def test_local_git_workspace_adapter_implements_protocol() -> None:
    # Arrange
    adapter = LocalGitWorkspaceAdapter()

    # Assert
    assert isinstance(adapter, GitWorkspacePort)

    auth_url = adapter.build_authenticated_url("https://github.com/octocat/repo.git", "token123")
    assert auth_url == "https://x-access-token:token123@github.com/octocat/repo.git"


@pytest.mark.unit
def test_git_run_timeout_raises_git_error() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir)
        with (
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["git", "status"], timeout=1.0)),
            pytest.raises(GitError, match="Tiempo de espera agotado"),
        ):
            git_status(path)


@pytest.mark.unit
def test_git_run_passes_git_terminal_prompt_zero() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = ""
            git_status(path)
            mock_run.assert_called_once()
            env_arg = mock_run.call_args.kwargs.get("env")
            assert env_arg is not None
            assert env_arg.get("GIT_TERMINAL_PROMPT") == "0"


@pytest.mark.unit
async def test_run_git_async_executes_successfully() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir)
        await git_init_async(path)
        res = await run_git_async(["git", "status", "--porcelain"], path)
        assert res.returncode == 0


@pytest.mark.unit
async def test_git_async_lifecycle_init_add_commit_rollback() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir)
        await git_init_async(path, initial_branch="main")

        assert await git_is_clean_async(path)
        assert await git_head_hash_async(path) is None

        file1 = path / "test.txt"
        file1.write_text("async git content", encoding="utf-8")
        assert not await git_is_clean_async(path)

        await git_add_async(path)
        committed = await git_commit_async(path, "feat: async commit")
        assert committed is True
        assert await git_is_clean_async(path)

        head = await git_head_hash_async(path)
        assert head is not None
        assert len(head) == 40

        # Modificación para probar rollback asíncrono
        file1.write_text("corrupted content", encoding="utf-8")
        assert not await git_is_clean_async(path)
        await git_rollback_async(path)
        assert await git_is_clean_async(path)
        assert file1.read_text(encoding="utf-8") == "async git content"


@pytest.mark.unit
async def test_local_git_workspace_adapter_async_methods() -> None:
    with tempfile.TemporaryDirectory() as bare_dir, tempfile.TemporaryDirectory() as ws_dir:
        bare_path = Path(bare_dir)
        ws_path = Path(ws_dir)

        await run_git_async(["git", "init", "--bare", "-b", "main"], bare_path)
        await git_init_async(ws_path, initial_branch="main")

        (ws_path / "index.ts").write_text("console.log(1);", encoding="utf-8")
        await git_add_async(ws_path)
        await git_commit_async(ws_path, "feat: initial")

        adapter = LocalGitWorkspaceAdapter()
        await adapter.remote_add_or_update_async(str(ws_path), "origin", str(bare_path))

        pushed_hash = await adapter.push_async(str(ws_path), remote="origin", branch="main")
        head = await git_head_hash_async(ws_path)
        assert pushed_hash == head
