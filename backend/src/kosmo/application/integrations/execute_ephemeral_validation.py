from __future__ import annotations

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

DEFAULT_EPHEMERAL_VALIDATION_STEPS: tuple[ValidationStep, ...] = (
    ValidationStep.TYPECHECK,
    ValidationStep.LINT,
    ValidationStep.TESTS,
    ValidationStep.BUILD,
)


class EphemeralValidationError(RuntimeError):
    """Lanzada cuando la validación en contenedor efímero detecta errores en el workspace."""

    def __init__(
        self,
        message: str,
        step: ValidationStep | None = None,
        errors: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.step = step
        self.errors = errors


@dataclass(frozen=True, slots=True)
class ExecuteEphemeralValidationCommand:
    workspace_path: str | None = None
    project_id: ProjectId | None = None
    steps: tuple[ValidationStep, ...] = DEFAULT_EPHEMERAL_VALIDATION_STEPS
    timeout_seconds: int = 300


@dataclass(frozen=True, slots=True)
class ExecuteEphemeralValidationResult:
    is_valid: bool
    steps: tuple[ValidationStepResult, ...]
    failed_step: ValidationStep | None = None
    error_summary: tuple[str, ...] = field(default_factory=tuple)
    total_duration_ms: int = 0
    run_result: ValidationRunResult = field(default_factory=lambda: ValidationRunResult())


class ExecuteEphemeralValidationUseCase:
    """Caso de uso para ejecutar validación determinística en un contenedor efímero aislado (C7).

    Orquesta la verificación secuencial de compilación, análisis estático y pruebas del código
    generado dentro de un entorno aislado, asegurando que el espacio de trabajo local permanezca
    limpio y verificado antes de sincronizar con el repositorio remoto.
    """

    def __init__(
        self,
        code_runner: CodeRunnerPort,
        workspace_manager: WorkspaceManagerPort | None = None,
    ) -> None:
        self._code_runner = code_runner
        self._workspace_manager = workspace_manager

    async def execute(
        self,
        cmd: ExecuteEphemeralValidationCommand,
    ) -> ExecuteEphemeralValidationResult:
        # 1. Determinar el directorio físico del workspace
        workspace_dir = cmd.workspace_path

        if not workspace_dir and cmd.project_id is not None:
            if self._workspace_manager is None:
                raise ValueError("No se proporcionó WorkspaceManagerPort para resolver el project_id.")
            workspace = await self._workspace_manager.ensure_workspace(cmd.project_id)
            if not workspace or not workspace.workspace_dir:
                raise ValueError(
                    f"No se encontró el directorio físico del workspace para el proyecto '{cmd.project_id}'."
                )
            workspace_dir = workspace.workspace_dir

        if not workspace_dir:
            raise ValueError("Se requiere 'workspace_path' o 'project_id' válido para ejecutar la validación efímera.")

        # 2. Ejecutar el pipeline completo en una sola copia efímera. En los runners
        # remotos, cada solicitud recibe un archive limpio sin node_modules; usar
        # run_step por separado perdería las dependencias entre typecheck/lint/tests.
        run_result = await self._code_runner.run_pipeline(
            workspace_dir=workspace_dir,
            steps=cmd.steps,
            run_id="ephemeral-validation",
        )
        failed_result = next((result for result in run_result.steps if not result.success), None)
        failed_step = failed_result.step if failed_result is not None else None
        error_summary_list = list(run_result.error_summary)

        if failed_result is not None and not error_summary_list:
            error_summary_list.extend(failed_result.error_messages)
            if not error_summary_list:
                error_summary_list.extend(
                    f"{error.file}:{error.line}:{error.column}: {error.message}" for error in failed_result.errors
                )
            if not error_summary_list:
                error_summary_list.append(
                    f"El paso '{failed_result.step}' falló con código de salida {failed_result.exit_code}."
                )

        run_result = ValidationRunResult(
            steps=run_result.steps,
            all_passed=run_result.all_passed,
            total_duration_ms=run_result.total_duration_ms,
            executed_at=run_result.executed_at or datetime.now(UTC),
            error_summary=tuple(error_summary_list),
        )

        return ExecuteEphemeralValidationResult(
            is_valid=run_result.all_passed,
            steps=run_result.steps,
            failed_step=failed_step,
            error_summary=tuple(error_summary_list),
            total_duration_ms=run_result.total_duration_ms,
            run_result=run_result,
        )
