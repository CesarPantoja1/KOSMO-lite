from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from structlog.testing import capture_logs

from kosmo.contracts.sdd.codegen import (
    ValidationSeverity,
    ValidationStep,
)
from kosmo.infrastructure.sandbox.code_runner import (
    SAFE_ENV_VARS,
    SubprocessCodeRunner,
    UnallowedCommandError,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_step_success() -> None:
    # Arrange
    runner = SubprocessCodeRunner()
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)) as mock_exec:
        # Act
        result = await runner.run_step("/tmp/workspace", ValidationStep.TYPECHECK)

        # Assert
        assert result.step == ValidationStep.TYPECHECK
        assert result.success is True
        assert result.exit_code == 0
        assert len(result.errors) == 0
        mock_exec.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_step_typecheck_with_tsc_errors() -> None:
    # Arrange
    runner = SubprocessCodeRunner()
    raw_output = b"src/index.ts(5,10): error TS2322: Type 'string' is not assignable to type 'number'.\n"
    mock_proc = MagicMock()
    mock_proc.returncode = 2
    mock_proc.communicate = AsyncMock(return_value=(raw_output, b""))

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
        # Act
        result = await runner.run_step("/tmp/workspace", ValidationStep.TYPECHECK)

        # Assert
        assert result.step == ValidationStep.TYPECHECK
        assert result.success is False
        assert result.exit_code == 2
        assert len(result.errors) == 1
        assert result.errors[0].file == "src/index.ts"
        assert result.errors[0].line == 5
        assert result.errors[0].column == 10
        assert result.errors[0].severity == ValidationSeverity.ERROR
        assert result.errors[0].code == "TS2322"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_step_timeout_handling() -> None:
    # Arrange
    runner = SubprocessCodeRunner()
    mock_proc = MagicMock()
    mock_proc.pid = 9999
    mock_proc.kill = MagicMock()
    mock_proc.wait = AsyncMock(return_value=0)

    async def slow_communicate() -> tuple[bytes, bytes]:
        await asyncio.sleep(10)
        return (b"", b"")

    mock_proc.communicate = AsyncMock(side_effect=slow_communicate)
    kill_proc = AsyncMock()
    kill_proc.wait = AsyncMock(return_value=0)

    async def fake_sub_exec(*args: object, **_kwargs: object) -> MagicMock:
        if args and args[0] == "taskkill":
            return kill_proc
        return mock_proc

    with (
        patch("asyncio.create_subprocess_exec", side_effect=fake_sub_exec) as mock_sub_exec,
        patch("subprocess.run") as mock_sub_run,
    ):
        # Act
        result = await runner.run_step("/tmp/workspace", ValidationStep.TESTS, timeout_seconds=1)

        # Assert
        assert result.step == ValidationStep.TESTS
        assert result.success is False
        assert result.exit_code == -1
        assert "timed out" in result.raw_output
        assert mock_proc.kill.called or mock_sub_run.called or mock_sub_exec.called


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_command_rejects_unlisted_command() -> None:
    # Arrange
    runner = SubprocessCodeRunner()

    # Act & Assert
    with pytest.raises(UnallowedCommandError, match="Command 'curl https://malicious.com' is not allowed"):
        await runner.run_command("/tmp/workspace", "curl https://malicious.com")

    with pytest.raises(UnallowedCommandError, match="Command 'rm -rf /' is not allowed"):
        await runner.run_command("/tmp/workspace", "rm -rf /")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_command_executes_allowed_command() -> None:
    # Arrange
    runner = SubprocessCodeRunner()
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"up to date", b""))

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
        # Act
        result = await runner.run_command("/tmp/workspace", "npm install")

        # Assert
        assert result.success is True
        assert result.exit_code == 0
        assert "up to date" in result.raw_output


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_pipeline_stops_on_first_failure_with_fail_fast(tmp_path) -> None:
    # Arrange
    runner = SubprocessCodeRunner()
    (tmp_path / "node_modules").mkdir()

    typecheck_output = b"src/index.ts:1:1: error TS2304: Cannot find name 'foo'.\n"

    mock_proc_fail = MagicMock()
    mock_proc_fail.returncode = 2
    mock_proc_fail.communicate = AsyncMock(return_value=(typecheck_output, b""))

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc_fail)) as mock_exec:
        # Act
        pipeline_result = await runner.run_pipeline(
            str(tmp_path),
            steps=(
                ValidationStep.TYPECHECK,
                ValidationStep.LINT,
                ValidationStep.TESTS,
                ValidationStep.BUILD,
            ),
            fail_fast=True,
        )

        # Assert
        assert pipeline_result.all_passed is False
        assert len(pipeline_result.steps) == 1
        assert pipeline_result.steps[0].step == ValidationStep.TYPECHECK
        assert pipeline_result.steps[0].success is False
        assert len(pipeline_result.error_summary) > 0
        assert mock_exec.await_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_pipeline_comprehensive_diagnostics_executes_checks_and_skips_build(tmp_path) -> None:
    # Arrange
    runner = SubprocessCodeRunner()
    (tmp_path / "node_modules").mkdir()

    fail_output = b"src/index.ts:1:1: error TS2304: Cannot find name 'foo'.\n"

    mock_proc_fail = MagicMock()
    mock_proc_fail.returncode = 1
    mock_proc_fail.communicate = AsyncMock(return_value=(fail_output, b""))

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc_fail)) as mock_exec:
        # Act
        pipeline_result = await runner.run_pipeline(
            str(tmp_path),
            steps=(
                ValidationStep.TYPECHECK,
                ValidationStep.LINT,
                ValidationStep.TESTS,
                ValidationStep.BUILD,
            ),
        )

        # Assert: TYPECHECK, LINT, TESTS executed (3), but BUILD skipped
        assert pipeline_result.all_passed is False
        assert len(pipeline_result.steps) == 3
        assert mock_exec.await_count == 3
        assert [s.step for s in pipeline_result.steps] == [
            ValidationStep.TYPECHECK,
            ValidationStep.LINT,
            ValidationStep.TESTS,
        ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_pipeline_all_success(tmp_path) -> None:
    # Arrange
    runner = SubprocessCodeRunner()
    (tmp_path / "node_modules").mkdir()

    mock_proc_ok = MagicMock()
    mock_proc_ok.returncode = 0
    mock_proc_ok.communicate = AsyncMock(return_value=(b"ok", b""))

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc_ok)) as mock_exec:
        # Act
        pipeline_result = await runner.run_pipeline(
            str(tmp_path),
            steps=(
                ValidationStep.TYPECHECK,
                ValidationStep.LINT,
            ),
        )

        # Assert
        assert pipeline_result.all_passed is True
        assert len(pipeline_result.steps) == 2
        assert mock_exec.await_count == 2
        assert len(pipeline_result.error_summary) == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_pipeline_logs_steps_with_run_id(tmp_path) -> None:
    # Arrange
    runner = SubprocessCodeRunner()
    (tmp_path / "node_modules").mkdir()

    mock_proc_ok = MagicMock()
    mock_proc_ok.returncode = 0
    mock_proc_ok.communicate = AsyncMock(return_value=(b"ok", b""))

    with (
        patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc_ok)),
        capture_logs() as cap_logs,
    ):
        # Act
        pipeline_result = await runner.run_pipeline(
            str(tmp_path),
            steps=(ValidationStep.TYPECHECK,),
            run_id="run_abc123",
        )

    # Assert — cada paso se registra con el correlation ID de la generación
    assert pipeline_result.all_passed is True
    step_events = [event for event in cap_logs if event["event"] == "code_runner.step_done"]
    assert len(step_events) == 1
    assert step_events[0]["run_id"] == "run_abc123"
    assert step_events[0]["step"] == "typecheck"
    assert step_events[0]["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_pipeline_runs_npm_install_when_node_modules_missing(tmp_path) -> None:
    # Arrange
    runner = SubprocessCodeRunner()

    mock_proc_ok = MagicMock()
    mock_proc_ok.returncode = 0
    mock_proc_ok.communicate = AsyncMock(return_value=(b"added 200 packages", b""))

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc_ok)) as mock_exec:
        # Act
        pipeline_result = await runner.run_pipeline(
            str(tmp_path),
            steps=(ValidationStep.TYPECHECK,),
        )

        # Assert
        assert pipeline_result.all_passed is True
        assert mock_exec.await_count == 2
        assert Path(str(mock_exec.call_args_list[0][0][0])).stem.lower() == "npm"
        assert mock_exec.call_args_list[0][0][1:] == ("install",)
        assert Path(str(mock_exec.call_args_list[1][0][0])).stem.lower() == "npx"
        assert mock_exec.call_args_list[1][0][1:] == ("tsc", "--noEmit")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_pipeline_skips_install_when_node_modules_exists(tmp_path) -> None:
    # Arrange
    runner = SubprocessCodeRunner()
    (tmp_path / "node_modules").mkdir()

    mock_proc_ok = MagicMock()
    mock_proc_ok.returncode = 0
    mock_proc_ok.communicate = AsyncMock(return_value=(b"ok", b""))

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc_ok)) as mock_exec:
        # Act
        await runner.run_pipeline(str(tmp_path), steps=(ValidationStep.TYPECHECK,))

        # Assert
        assert mock_exec.await_count == 1
        assert Path(str(mock_exec.call_args_list[0][0][0])).stem.lower() == "npx"
        assert mock_exec.call_args_list[0][0][1:] == ("tsc", "--noEmit")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_pipeline_fails_fast_when_npm_install_fails(tmp_path) -> None:
    # Arrange
    runner = SubprocessCodeRunner()

    mock_proc_fail = MagicMock()
    mock_proc_fail.returncode = 1
    mock_proc_fail.communicate = AsyncMock(return_value=(b"npm ERR! network timeout", b""))

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc_fail)) as mock_exec:
        # Act
        pipeline_result = await runner.run_pipeline(
            str(tmp_path),
            steps=(
                ValidationStep.TYPECHECK,
                ValidationStep.LINT,
                ValidationStep.TESTS,
                ValidationStep.BUILD,
            ),
        )

        # Assert
        assert pipeline_result.all_passed is False
        assert len(pipeline_result.steps) == 0
        assert mock_exec.await_count == 1
        assert any("npm install" in err for err in pipeline_result.error_summary)
        assert any("network timeout" in err for err in pipeline_result.error_summary)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_command_failed_exit_code() -> None:
    # Arrange
    runner = SubprocessCodeRunner()
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"failed install", b""))

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
        # Act
        result = await runner.run_command("/tmp/workspace", "npm install")

        # Assert
        assert result.success is False
        assert result.exit_code == 1
        assert "failed install" in result.raw_output
        assert len(result.error_messages) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_command_empty_or_whitespace() -> None:
    # Arrange
    runner = SubprocessCodeRunner()

    # Act & Assert
    with pytest.raises(UnallowedCommandError, match="Command '' is not allowed"):
        await runner.run_command("/tmp/workspace", "")

    with pytest.raises(UnallowedCommandError, match="Command '   ' is not allowed"):
        await runner.run_command("/tmp/workspace", "   ")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_custom_step_commands() -> None:
    # Arrange
    runner = SubprocessCodeRunner(step_commands={ValidationStep.TYPECHECK: "custom-tsc"})
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)) as mock_exec:
        # Act
        await runner.run_step("/tmp/workspace", ValidationStep.TYPECHECK)

        # Assert
        mock_exec.assert_awaited_once()
        assert Path(str(mock_exec.call_args[0][0])).stem.lower() == "custom-tsc"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_pipeline_uses_custom_and_default_step_timeouts() -> None:
    # Arrange
    custom_timeouts = {ValidationStep.TYPECHECK: 15, ValidationStep.TESTS: 45}
    runner = SubprocessCodeRunner(step_timeouts=custom_timeouts)

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))

    with (
        patch("pathlib.Path.is_dir", return_value=True),
        patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)),
        patch.object(runner, "run_step", wraps=runner.run_step) as spy_run_step,
    ):
        # Act
        result = await runner.run_pipeline(
            "/tmp/workspace",
            steps=(ValidationStep.TYPECHECK, ValidationStep.TESTS),
        )

        # Assert
        assert result.all_passed is True
        assert spy_run_step.call_count == 2
        assert spy_run_step.call_args_list[0].kwargs["timeout_seconds"] == 15
        assert spy_run_step.call_args_list[1].kwargs["timeout_seconds"] == 45


@pytest.mark.unit
@pytest.mark.asyncio
async def test_subprocess_code_runner_limits_concurrency_with_semaphore() -> None:
    # Arrange
    semaphore = asyncio.Semaphore(2)
    runner = SubprocessCodeRunner(semaphore=semaphore)

    active_count = 0
    max_active_count = 0
    lock = asyncio.Lock()

    async def fake_subprocess(*_args: object, **_kwargs: object) -> MagicMock:
        nonlocal active_count, max_active_count
        async with lock:
            active_count += 1
            if active_count > max_active_count:
                max_active_count = active_count
        await asyncio.sleep(0.02)
        async with lock:
            active_count -= 1

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        return mock_proc

    with patch("asyncio.create_subprocess_exec", side_effect=fake_subprocess):
        # Act
        tasks = [runner.run_step("/tmp/workspace", ValidationStep.TYPECHECK) for _ in range(5)]
        results = await asyncio.gather(*tasks)

        # Assert
        assert len(results) == 5
        assert all(r.success for r in results)
        assert max_active_count <= 2


@pytest.mark.unit
@pytest.mark.parametrize(
    ("env_value", "expected_limit"),
    [
        ("8", 8),
        ("1", 1),
        ("0", 4),
        ("-3", 4),
        ("invalid", 4),
    ],
)
def test_get_runner_semaphore_handles_env_values(
    monkeypatch: pytest.MonkeyPatch,
    env_value: str,
    expected_limit: int,
) -> None:
    # Arrange
    from kosmo.infrastructure.sandbox.code_runner import _get_runner_semaphore

    monkeypatch.setenv("KOSMO_MAX_CONCURRENT_RUNNERS", env_value)

    # Act
    sem = _get_runner_semaphore()

    # Assert
    assert sem._value == expected_limit


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_command_prevents_shell_metacharacter_execution() -> None:
    # Arrange: un comando con metacaracteres de shell (;, &&, |, ``, $())
    runner = SubprocessCodeRunner()
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"output", b""))

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)) as mock_exec:
        # Act
        result = await runner.run_command("/tmp/workspace", "npx tsc; cat /etc/passwd")

        # Assert: create_subprocess_exec fue invocado con los metacaracteres como argumentos literales
        assert result.success is True
        mock_exec.assert_awaited_once()
        args = mock_exec.call_args[0]
        assert Path(str(args[0])).stem.lower() == "npx"
        assert args[1:] == ("tsc;", "cat", "/etc/passwd")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_command_handles_executable_not_found() -> None:
    # Arrange
    runner = SubprocessCodeRunner()

    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError("not found")):
        # Act
        result = await runner.run_command("/tmp/workspace", "npx tsc")

        # Assert: FileNotFoundError produce un resultado fallido con exit code 127
        assert result.success is False
        assert result.exit_code == 127
        assert "Executable 'npx' not found." in result.raw_output


@pytest.mark.unit
def test_clean_env_strips_all_sensitive_secrets() -> None:
    # Arrange — Simulamos un entorno con secretos maestros y variables seguras
    fake_env = {
        "FERNET_MASTER_KEY": "super_secret_master_key_12345",
        "JWT_PRIVATE_KEY_PEM": "-----BEGIN RSA PRIVATE KEY-----...",
        "REDIS_URL": "redis://:secretpass@localhost:6379",
        "REDIS_PASSWORD": "secret_redis_password",
        "DATABASE_URL": "postgresql://user:pass@localhost:5432/db",
        "OPENAI_API_KEY": "sk-proj-openai-secret-key",
        "DEEPSEEK_API_KEY": "sk-deepseek-secret-key",
        "GEMINI_API_KEY": "AIzaSy-gemini-key",
        "GROQ_API_KEY": "gsk_groq_secret_key",
        "GITHUB_CLIENT_SECRET": "gh_secret_987654",
        "RAILWAY_CLIENT_SECRET": "railway_secret_token",
        "LOGFIRE_TOKEN": "logfire_token_secret",
        "KOSMO_SECRET_KEY": "kosmo_secret_key",
        "SECRET_KEY": "django_secret_key",
        # Variables seguras permitidas
        "PATH": "/usr/local/bin:/usr/bin",
        "HOME": "/home/developer",
        "TEMP": "/tmp",
        "NODE_ENV": "test",
        "CI": "true",
        "KOSMO_WORKSPACES_DIR": "/tmp/workspaces",
    }

    with patch("os.environ", fake_env):
        # Act
        cleaned = SubprocessCodeRunner._clean_env()

    # Assert — Ningún secreto debe estar presente en el entorno limpio
    sensitive_keys = {
        "FERNET_MASTER_KEY",
        "JWT_PRIVATE_KEY_PEM",
        "REDIS_URL",
        "REDIS_PASSWORD",
        "DATABASE_URL",
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "GITHUB_CLIENT_SECRET",
        "RAILWAY_CLIENT_SECRET",
        "LOGFIRE_TOKEN",
        "KOSMO_SECRET_KEY",
        "SECRET_KEY",
    }
    for secret_key in sensitive_keys:
        assert secret_key not in SAFE_ENV_VARS
        assert secret_key not in cleaned, f"Secreto {secret_key} se filtró al entorno del subproceso"

    # Assert — Variables seguras permitidas sí deben conservarse
    assert cleaned["PATH"] == "/usr/local/bin:/usr/bin"
    assert cleaned["HOME"] == "/home/developer"
    assert cleaned["NODE_ENV"] == "test"
    assert cleaned["CI"] == "true"
    assert cleaned["KOSMO_WORKSPACES_DIR"] == "/tmp/workspaces"


@pytest.mark.unit
def test_clean_env_case_insensitive_matching() -> None:
    # Arrange — Variables con distintas combinaciones de mayúsculas/minúsculas
    fake_env = {
        "Path": "/usr/bin",
        "path": "/bin",
        "SystemRoot": "C:\\Windows",
        "Temp": "C:\\Temp",
        "node_env": "production",
        "evil_token": "leak_me",
    }

    with patch("os.environ", fake_env):
        # Act
        cleaned = SubprocessCodeRunner._clean_env()

    # Assert — Coincide de forma insensible a mayúsculas con SAFE_ENV_VARS
    assert "Path" in cleaned or "path" in cleaned
    assert "SystemRoot" in cleaned
    assert "Temp" in cleaned
    assert "node_env" in cleaned
    assert "evil_token" not in cleaned


@pytest.mark.unit
@pytest.mark.asyncio
async def test_subprocess_exec_receives_allowlisted_clean_env() -> None:
    # Arrange
    runner = SubprocessCodeRunner()
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"ok", b""))

    with (
        patch.dict("os.environ", {"FERNET_MASTER_KEY": "leak_test", "NODE_ENV": "test"}, clear=False),
        patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)) as mock_exec,
    ):
        # Act
        await runner.run_command("/tmp/workspace", "npx tsc")

        # Assert — El parámetro env pasado a create_subprocess_exec no tiene el secreto
        mock_exec.assert_awaited_once()
        _, kwargs = mock_exec.call_args
        env_passed = kwargs.get("env", {})
        assert "FERNET_MASTER_KEY" not in env_passed
        assert env_passed.get("NODE_ENV") == "test"
