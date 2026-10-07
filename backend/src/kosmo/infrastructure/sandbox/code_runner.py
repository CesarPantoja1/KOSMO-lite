from __future__ import annotations

import asyncio
import contextlib
import os
import shlex
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

import structlog

from kosmo.contracts.sdd.codegen import (
    CodeRunnerPort,
    ValidationRunResult,
    ValidationStep,
    ValidationStepResult,
)
from kosmo.domain.codegen.parse_validation_output import parse_step_output
from kosmo.infrastructure.telemetry.metrics import ACTIVE_CODE_RUNNERS

_log = structlog.get_logger("kosmo.sandbox.code_runner")

DEFAULT_STEP_COMMANDS: dict[ValidationStep, str] = {
    ValidationStep.TYPECHECK: "npx tsc --noEmit",
    ValidationStep.LINT: "npx eslint .",
    ValidationStep.TESTS: "npx vitest run",
    ValidationStep.BUILD: "npx next build",
}

DEFAULT_STEP_TIMEOUTS: dict[ValidationStep, int] = {
    ValidationStep.TYPECHECK: 60,
    ValidationStep.LINT: 60,
    ValidationStep.TESTS: 90,
    ValidationStep.BUILD: 180,
}

INSTALL_COMMAND: str = "npm install"
INSTALL_TIMEOUT_SECONDS: int = 600

_DEFAULT_MAX_CONCURRENT_RUNNERS: int = 4


def _get_runner_semaphore() -> asyncio.Semaphore:
    raw = os.getenv("KOSMO_MAX_CONCURRENT_RUNNERS", str(_DEFAULT_MAX_CONCURRENT_RUNNERS))
    try:
        limit = int(raw)
        if limit <= 0:
            limit = _DEFAULT_MAX_CONCURRENT_RUNNERS
    except ValueError:
        limit = _DEFAULT_MAX_CONCURRENT_RUNNERS
    return asyncio.Semaphore(limit)


_runner_semaphore: asyncio.Semaphore = _get_runner_semaphore()

DEFAULT_ALLOWED_COMMAND_PREFIXES: frozenset[str] = frozenset(
    {
        "npm",
        "npx",
        "tsc",
        "eslint",
        "vitest",
        "next",
        "git",
        "drizzle-kit",
        "node",
        "pnpm",
        "yarn",
        "pytest",
        "python",
        "pyright",
        "ruff",
    }
)

SAFE_ENV_VARS: frozenset[str] = frozenset(
    {
        # Binarios y rutas del sistema operativo (Windows y POSIX)
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "SYSTEMDRIVE",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "PROGRAMDATA",
        "COMMONPROGRAMFILES",
        "COMMONPROGRAMFILES(X86)",
        # Directorios de usuario y caché de herramientas
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        # Directorios temporales
        "TEMP",
        "TMP",
        "TMPDIR",
        # Runtime, localización y CI
        "NODE_ENV",
        "CI",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TERM",
        # Configuraciones no sensibles de KOSMO
        "KOSMO_WORKSPACES_DIR",
        "KOSMO_MAX_CONCURRENT_RUNNERS",
    }
)


class UnallowedCommandError(ValueError):
    """Lanzada cuando un comando no está en la lista de permitidos."""


class SubprocessCodeRunner(CodeRunnerPort):
    """Adaptador de infraestructura que ejecuta validaciones determinísticas en subprocesos."""

    def __init__(
        self,
        step_commands: dict[ValidationStep, str] | None = None,
        allowed_prefixes: frozenset[str] = DEFAULT_ALLOWED_COMMAND_PREFIXES,
        step_timeouts: dict[ValidationStep, int] | None = None,
        semaphore: asyncio.Semaphore | None = None,
    ) -> None:
        self._step_commands = dict(DEFAULT_STEP_COMMANDS)
        if step_commands:
            self._step_commands.update(step_commands)
        self._allowed_prefixes = allowed_prefixes
        self._step_timeouts = dict(DEFAULT_STEP_TIMEOUTS)
        if step_timeouts:
            self._step_timeouts.update(step_timeouts)
        self._semaphore = semaphore if semaphore is not None else _runner_semaphore

    @staticmethod
    def _clean_env() -> dict[str, str]:
        """Filtra el entorno del proceso padre permitiendo exclusivamente variables de la lista blanca.

        Aplica una allowlist insensible a mayúsculas/minúsculas para prevenir la fuga de secretos
        criptográficos (FERNET_MASTER_KEY, JWT keys), URLs de bases de datos y claves de API
        hacia el entorno de subprocesos donde se ejecutan herramientas y dependencias de terceros.
        """
        return {k: v for k, v in os.environ.items() if k.upper() in SAFE_ENV_VARS}

    def _is_command_allowed(self, command: str) -> bool:
        stripped = command.strip()
        if not stripped:
            return False

        try:
            tokens = shlex.split(stripped, posix=os.name != "nt")
        except ValueError:
            tokens = stripped.split()

        if not tokens:
            return False

        first_token = tokens[0].lower()
        base_name = Path(first_token).stem.lower()

        return base_name in self._allowed_prefixes or first_token in self._allowed_prefixes

    async def _execute_command(
        self,
        workspace_dir: str,
        command: str,
        step: ValidationStep | None,
        timeout_seconds: int,
    ) -> ValidationStepResult:
        start = time.perf_counter()

        try:
            tokens = shlex.split(command.strip(), posix=os.name != "nt")
        except ValueError:
            tokens = command.strip().split()

        if not tokens:
            raise UnallowedCommandError(f"Command '{command}' is empty.")

        executable = shutil.which(tokens[0]) or tokens[0]

        queue_timeout = float(os.getenv("KOSMO_RUNNER_QUEUE_TIMEOUT_SECONDS", "180.0"))
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=queue_timeout)
        except TimeoutError:
            duration_ms = int((time.perf_counter() - start) * 1000)
            timeout_msg = f"Runner queue timeout: wait exceeded {queue_timeout} seconds."
            return ValidationStepResult(
                step=step or ValidationStep.TESTS,
                success=False,
                duration_ms=duration_ms,
                exit_code=-1,
                raw_output=timeout_msg,
                errors=(),
                error_messages=(timeout_msg,),
            )

        try:
            ACTIVE_CODE_RUNNERS.inc()
            try:
                try:
                    proc = await asyncio.create_subprocess_exec(
                        executable,
                        *tokens[1:],
                        cwd=workspace_dir,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.STDOUT,
                        env=self._clean_env(),
                    )
                except FileNotFoundError:
                    duration_ms = int((time.perf_counter() - start) * 1000)
                    error_msg = f"Executable '{tokens[0]}' not found."
                    return ValidationStepResult(
                        step=step or ValidationStep.TESTS,
                        success=False,
                        duration_ms=duration_ms,
                        exit_code=127,
                        raw_output=error_msg,
                        errors=(),
                        error_messages=(error_msg,),
                    )

                try:
                    stdout, _ = await asyncio.wait_for(
                        proc.communicate(),
                        timeout=float(timeout_seconds),
                    )
                except TimeoutError:
                    await self._kill_process_tree(proc)

                    duration_ms = int((time.perf_counter() - start) * 1000)
                    timeout_msg = f"Command '{command}' timed out after {timeout_seconds} seconds."
                    return ValidationStepResult(
                        step=step or ValidationStep.TESTS,
                        success=False,
                        duration_ms=duration_ms,
                        exit_code=-1,
                        raw_output=timeout_msg,
                        errors=(),
                        error_messages=(timeout_msg,),
                    )

                duration_ms = int((time.perf_counter() - start) * 1000)
                raw_output = stdout.decode("utf-8", errors="replace")
                exit_code = proc.returncode if proc.returncode is not None else 0
            finally:
                ACTIVE_CODE_RUNNERS.dec()
        finally:
            self._semaphore.release()

        if step is not None:
            return parse_step_output(
                step=step,
                raw_output=raw_output,
                exit_code=exit_code,
                duration_ms=duration_ms,
            )

        success = exit_code == 0
        error_msgs = () if success else (f"Command failed with exit code {exit_code}",)
        return ValidationStepResult(
            step=ValidationStep.TESTS,
            success=success,
            duration_ms=duration_ms,
            exit_code=exit_code,
            raw_output=raw_output,
            errors=(),
            error_messages=error_msgs,
        )

    @staticmethod
    async def _kill_process_tree(proc: asyncio.subprocess.Process) -> None:
        """Termina de forma forzada el árbol de procesos para evitar procesos huérfanos."""
        with contextlib.suppress(Exception):
            if os.name == "nt" and proc.pid:
                kill_proc = await asyncio.create_subprocess_exec(
                    "taskkill",
                    "/F",
                    "/T",
                    "/PID",
                    str(proc.pid),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await kill_proc.wait()
            else:
                proc.kill()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(proc.wait(), timeout=2.0)

    async def run_step(
        self,
        workspace_dir: str,
        step: ValidationStep,
        *,
        timeout_seconds: int | None = None,
    ) -> ValidationStepResult:
        """Ejecuta el paso de validación y parsea su salida determinísticamente."""
        command = self._step_commands[step]
        timeout = timeout_seconds if timeout_seconds is not None else self._step_timeouts.get(step, 120)
        return await self._execute_command(
            workspace_dir=workspace_dir,
            command=command,
            step=step,
            timeout_seconds=timeout,
        )

    async def run_command(
        self,
        workspace_dir: str,
        command: str,
        *,
        timeout_seconds: int = 300,
    ) -> ValidationStepResult:
        """Ejecuta un comando validando previamente que pertenezca a la whitelist."""
        if not self._is_command_allowed(command):
            raise UnallowedCommandError(f"Command '{command}' is not allowed.")

        return await self._execute_command(
            workspace_dir=workspace_dir,
            command=command,
            step=None,
            timeout_seconds=timeout_seconds,
        )

    async def run_pipeline(
        self,
        workspace_dir: str,
        steps: tuple[ValidationStep, ...] = (
            ValidationStep.TYPECHECK,
            ValidationStep.LINT,
            ValidationStep.TESTS,
            ValidationStep.BUILD,
        ),
        run_id: str = "",
        step_timeouts: dict[ValidationStep, int] | None = None,
        fail_fast: bool = False,
    ) -> ValidationRunResult:
        """Ejecuta los pasos de validación.

        Por defecto (fail_fast=False), ejecuta los pasos de análisis estático y pruebas
        para recopilar un diagnóstico integral, omitiendo únicamente el empaquetado (BUILD)
        si se detectan errores previos.
        """
        if not (Path(workspace_dir) / "node_modules").is_dir():
            install_result = await self.run_command(
                workspace_dir,
                INSTALL_COMMAND,
                timeout_seconds=INSTALL_TIMEOUT_SECONDS,
            )
            if not install_result.success:
                _log.warning(
                    "code_runner.install_failed",
                    run_id=run_id,
                    workspace_dir=workspace_dir,
                    exit_code=install_result.exit_code,
                )
                output_lines = install_result.raw_output.strip().splitlines()
                detail = output_lines[0] if output_lines else "sin salida"
                return ValidationRunResult(
                    steps=(),
                    all_passed=False,
                    total_duration_ms=install_result.duration_ms,
                    executed_at=datetime.now(UTC),
                    error_summary=(f"{INSTALL_COMMAND} falló (exit {install_result.exit_code}): {detail}",),
                )

        results: list[ValidationStepResult] = []

        for step in steps:
            if fail_fast and any(not r.success for r in results):
                break
            if step == ValidationStep.BUILD and any(not r.success for r in results):
                break

            timeout = (step_timeouts or self._step_timeouts).get(step, 120)
            result = await self.run_step(workspace_dir, step, timeout_seconds=timeout)
            _log.info(
                "code_runner.step_done",
                run_id=run_id,
                workspace_dir=workspace_dir,
                step=str(step),
                success=result.success,
                duration_ms=result.duration_ms,
            )
            results.append(result)

        all_passed = len(results) == len(steps) and all(r.success for r in results)
        total_duration = sum(r.duration_ms for r in results)
        error_summary = tuple(err for r in results for err in r.error_messages)

        return ValidationRunResult(
            steps=tuple(results),
            all_passed=all_passed,
            total_duration_ms=total_duration,
            executed_at=datetime.now(UTC),
            error_summary=error_summary,
        )
