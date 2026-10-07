from __future__ import annotations

import asyncio
import contextlib
import inspect
import os
import shlex
import time
from datetime import UTC, datetime
from pathlib import Path

import structlog
from ulid import ULID

from kosmo.contracts.sdd.codegen import (
    CodeRunnerPort,
    ValidationRunResult,
    ValidationStep,
    ValidationStepResult,
)
from kosmo.domain.codegen.parse_validation_output import parse_step_output
from kosmo.infrastructure.sandbox.code_runner import (
    DEFAULT_ALLOWED_COMMAND_PREFIXES,
    DEFAULT_STEP_COMMANDS,
    UnallowedCommandError,
)

_log = structlog.get_logger("kosmo.sandbox.docker_runner")

DEFAULT_VALIDATOR_IMAGE: str = "kosmo-validator:latest"
DEFAULT_CONTAINER_WORKSPACE: str = "/workspace"


class EphemeralDockerCodeRunner(CodeRunnerPort):
    """Adaptador de infraestructura que ejecuta validaciones determinísticas en contenedores Docker efímeros.

    Monta el espacio de trabajo local como volumen, ejecuta la compilación o pruebas de forma aislada
    y destruye automáticamente el contenedor al concluir mediante el flag `--rm`.
    """

    def __init__(
        self,
        image: str = DEFAULT_VALIDATOR_IMAGE,
        step_commands: dict[ValidationStep, str] | None = None,
        allowed_prefixes: frozenset[str] = DEFAULT_ALLOWED_COMMAND_PREFIXES,
        docker_bin: str = "docker",
        extra_docker_flags: tuple[str, ...] = ("--rm",),
        container_workspace: str = DEFAULT_CONTAINER_WORKSPACE,
        mount_read_only: bool = False,
    ) -> None:
        self._image = image
        self._step_commands = dict(DEFAULT_STEP_COMMANDS)
        if step_commands:
            self._step_commands.update(step_commands)
        self._allowed_prefixes = allowed_prefixes
        self._docker_bin = docker_bin
        self._extra_docker_flags = extra_docker_flags
        self._container_workspace = container_workspace
        self._mount_read_only = mount_read_only

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

    def _build_docker_args(
        self,
        workspace_dir: str,
        command: str,
        container_name: str | None = None,
    ) -> list[str]:
        resolved_path = str(Path(workspace_dir).resolve())
        mount_flag = f"{resolved_path}:{self._container_workspace}"
        if self._mount_read_only:
            mount_flag += ":ro"

        name_flags: list[str] = ["--name", container_name] if container_name else []

        return [
            self._docker_bin,
            "run",
            *name_flags,
            "-v",
            mount_flag,
            "-w",
            self._container_workspace,
            *self._extra_docker_flags,
            self._image,
            "sh",
            "-c",
            command,
        ]

    async def _cleanup_container(self, container_name: str) -> None:
        """Fuerza la eliminación de un contenedor huérfano en el daemon de Docker."""
        try:
            _log.info("docker_runner.cleanup_orphan", container_name=container_name)
            cleanup_proc = await asyncio.create_subprocess_exec(
                self._docker_bin,
                "rm",
                "-f",
                container_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            wait_coro = cleanup_proc.wait()
            if inspect.isawaitable(wait_coro):
                await asyncio.wait_for(wait_coro, timeout=10.0)
        except Exception as exc:
            _log.warning("docker_runner.cleanup_orphan_failed", container_name=container_name, error=str(exc))

    async def _execute_in_container(
        self,
        workspace_dir: str,
        command: str,
        step: ValidationStep | None,
        timeout_seconds: int,
    ) -> ValidationStepResult:
        start = time.perf_counter()
        container_name = f"kosmo_val_{ULID()!s}".lower()
        args = self._build_docker_args(workspace_dir, command, container_name=container_name)

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            err_msg = f"No se pudo iniciar el contenedor efímero Docker: {exc}"
            _log.error("docker_runner.spawn_failed", workspace_dir=workspace_dir, error=str(exc))
            return ValidationStepResult(
                step=step or ValidationStep.TESTS,
                success=False,
                duration_ms=duration_ms,
                exit_code=-1,
                raw_output=err_msg,
                errors=(),
                error_messages=(err_msg,),
            )

        try:
            stdout, _ = await asyncio.wait_for(
                proc.communicate(),
                timeout=float(timeout_seconds),
            )
        except TimeoutError:
            with contextlib.suppress(Exception):
                proc.kill()
            with contextlib.suppress(Exception):
                p_wait = proc.wait()
                if inspect.isawaitable(p_wait):
                    await asyncio.wait_for(p_wait, timeout=2.0)
            await self._cleanup_container(container_name)

            duration_ms = int((time.perf_counter() - start) * 1000)
            timeout_msg = (
                f"Validación en contenedor Docker para '{command}' "
                f"excedió el tiempo límite de {timeout_seconds} segundos."
            )
            _log.warning(
                "docker_runner.timeout",
                workspace_dir=workspace_dir,
                command=command,
                timeout_s=timeout_seconds,
                container_name=container_name,
            )
            return ValidationStepResult(
                step=step or ValidationStep.TESTS,
                success=False,
                duration_ms=duration_ms,
                exit_code=-1,
                raw_output=timeout_msg,
                errors=(),
                error_messages=(timeout_msg,),
            )
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                proc.kill()
            with contextlib.suppress(Exception):
                p_wait = proc.wait()
                if inspect.isawaitable(p_wait):
                    await asyncio.wait_for(p_wait, timeout=2.0)
            await self._cleanup_container(container_name)
            raise

        duration_ms = int((time.perf_counter() - start) * 1000)
        raw_output = stdout.decode("utf-8", errors="replace") if stdout else ""
        exit_code = proc.returncode if proc.returncode is not None else 0

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

    async def run_step(
        self,
        workspace_dir: str,
        step: ValidationStep,
        *,
        timeout_seconds: int = 300,
    ) -> ValidationStepResult:
        """Ejecuta el paso de validación en un contenedor Docker efímero y parsea sus errores."""
        command = self._step_commands[step]
        return await self._execute_in_container(
            workspace_dir=workspace_dir,
            command=command,
            step=step,
            timeout_seconds=timeout_seconds,
        )

    async def run_command(
        self,
        workspace_dir: str,
        command: str,
        *,
        timeout_seconds: int = 300,
    ) -> ValidationStepResult:
        """Ejecuta un comando en un contenedor Docker efímero validando que esté en la whitelist."""
        if not self._is_command_allowed(command):
            raise UnallowedCommandError(f"Command '{command}' is not allowed.")

        return await self._execute_in_container(
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
        fail_fast: bool = False,
    ) -> ValidationRunResult:
        """Ejecuta los pasos de validación en contenedores Docker efímeros.

        Por defecto (fail_fast=False), ejecuta los pasos de análisis estático y pruebas
        para recopilar un diagnóstico integral, omitiendo únicamente el empaquetado (BUILD)
        si se detectan errores previos.
        """
        results: list[ValidationStepResult] = []

        for step in steps:
            if fail_fast and any(not r.success for r in results):
                break
            if step == ValidationStep.BUILD and any(not r.success for r in results):
                break

            result = await self.run_step(workspace_dir, step)
            _log.info(
                "docker_runner.step_done",
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
