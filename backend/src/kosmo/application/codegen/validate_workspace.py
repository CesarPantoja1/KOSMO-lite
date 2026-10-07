from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from datetime import UTC, datetime

from kosmo.contracts.sdd.codegen import (
    CodeRunnerPort,
    ValidationRunResult,
    ValidationStep,
    ValidationStepResult,
    WorkspaceManagerPort,
)
from kosmo.contracts.sdd.ids import ProjectId

DEFAULT_VALIDATION_STEPS: tuple[ValidationStep, ...] = (
    ValidationStep.TYPECHECK,
    ValidationStep.LINT,
    ValidationStep.TESTS,
    ValidationStep.BUILD,
)


class WorkspaceNotFoundError(ValueError):
    """Lanzada cuando el workspace no existe para el proyecto dado."""

    def __init__(self, message: str = "Workspace no encontrado para el proyecto especificado.") -> None:
        super().__init__(message)


@dataclass(frozen=True)
class ValidateWorkspaceInput:
    project_id: ProjectId | None = None
    workspace_dir: str | None = None
    steps: tuple[ValidationStep, ...] = DEFAULT_VALIDATION_STEPS
    timeout_seconds: int = 300


@dataclass(frozen=True)
class ValidateWorkspaceOutput:
    all_passed: bool
    steps: tuple[ValidationStepResult, ...]
    failed_step: ValidationStep | None = None
    error_summary: tuple[str, ...] = field(default_factory=tuple)
    total_duration_ms: int = 0
    run_result: ValidationRunResult = field(default_factory=lambda: ValidationRunResult())


class ValidateWorkspaceUseCase:
    """Caso de uso para ejecutar el pipeline de validación determinística en orden fijo secuencial."""

    def __init__(
        self,
        code_runner: CodeRunnerPort,
        workspace_manager: WorkspaceManagerPort | None = None,
    ) -> None:
        self._code_runner = code_runner
        self._workspace_manager = workspace_manager

    async def execute(self, input_data: ValidateWorkspaceInput) -> ValidateWorkspaceOutput:
        lock_acquired = False
        if input_data.project_id is not None and self._workspace_manager is not None:
            await self._workspace_manager.acquire_lock(input_data.project_id)
            lock_acquired = True

        try:
            # 1. Determinar el directorio de trabajo
            workspace_dir = input_data.workspace_dir

            if not workspace_dir and input_data.project_id is not None:
                if self._workspace_manager is None:
                    raise WorkspaceNotFoundError("No se proporcionó WorkspaceManagerPort para resolver el project_id.")
                workspace = await self._workspace_manager.get_workspace(input_data.project_id)
                if workspace is None or not workspace.workspace_dir:
                    raise WorkspaceNotFoundError(
                        f"No existe un workspace inicializado para el proyecto '{input_data.project_id}'."
                    )
                workspace_dir = workspace.workspace_dir

            if not workspace_dir:
                raise WorkspaceNotFoundError(
                    "Se requiere 'project_id' o 'workspace_dir' válido para validar el workspace."
                )

            # 2. Ejecutar secuencialmente los pasos en orden fijo
            step_results: list[ValidationStepResult] = []
            all_passed = True
            failed_step: ValidationStep | None = None
            error_summary_list: list[str] = []
            total_duration_ms = 0

            for step in input_data.steps:
                res = await self._code_runner.run_step(
                    workspace_dir=workspace_dir,
                    step=step,
                    timeout_seconds=input_data.timeout_seconds,
                )
                step_results.append(res)
                total_duration_ms += res.duration_ms

                if not res.success:
                    all_passed = False
                    failed_step = step
                    for msg in res.error_messages:
                        error_summary_list.append(msg)
                    if not res.error_messages and res.errors:
                        for err in res.errors:
                            error_summary_list.append(f"{err.file}:{err.line}:{err.column}: {err.message}")
                    if not error_summary_list:
                        error_summary_list.append(f"El paso de validación '{step}' falló con código {res.exit_code}.")
                    # Detención temprana en el primer fallo
                    break

            run_result = ValidationRunResult(
                steps=tuple(step_results),
                all_passed=all_passed,
                total_duration_ms=total_duration_ms,
                executed_at=datetime.now(UTC),
                error_summary=tuple(error_summary_list),
            )

            return ValidateWorkspaceOutput(
                all_passed=all_passed,
                steps=tuple(step_results),
                failed_step=failed_step,
                error_summary=tuple(error_summary_list),
                total_duration_ms=total_duration_ms,
                run_result=run_result,
            )
        finally:
            if lock_acquired and self._workspace_manager is not None and input_data.project_id is not None:
                with contextlib.suppress(Exception):
                    await self._workspace_manager.release_lock(input_data.project_id)
