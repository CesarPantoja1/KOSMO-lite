from __future__ import annotations

import pytest

from kosmo.application.codegen.validate_workspace import (
    ValidateWorkspaceInput,
    ValidateWorkspaceUseCase,
    WorkspaceNotFoundError,
)
from kosmo.contracts.sdd.codegen import (
    CodeRunnerPort,
    CodeWorkspace,
    ValidationErrorDetail,
    ValidationRunResult,
    ValidationSeverity,
    ValidationStep,
    ValidationStepResult,
    WorkspaceManagerPort,
    WorkspaceStatus,
)
from kosmo.contracts.sdd.ids import ProjectId, WorkspaceId


class StepRecordingCodeRunner(CodeRunnerPort):
    def __init__(self, failing_step: ValidationStep | None = None) -> None:
        self.failing_step = failing_step
        self.executed_steps: list[ValidationStep] = []

    async def run_step(
        self,
        workspace_dir: str,
        step: ValidationStep,
        *,
        timeout_seconds: int = 300,
    ) -> ValidationStepResult:
        self.executed_steps.append(step)
        if step == self.failing_step:
            return ValidationStepResult(
                step=step,
                success=False,
                duration_ms=120,
                exit_code=1,
                errors=(
                    ValidationErrorDetail(
                        file="src/index.ts",
                        line=12,
                        column=4,
                        message=f"Error en paso {step}",
                        severity=ValidationSeverity.ERROR,
                    ),
                ),
                error_messages=(f"src/index.ts:12:4 - error: Error en paso {step}",),
            )
        return ValidationStepResult(
            step=step,
            success=True,
            duration_ms=80,
            exit_code=0,
        )

    async def run_command(
        self,
        workspace_dir: str,
        command: str,
        *,
        timeout_seconds: int = 300,
    ) -> ValidationStepResult:
        return ValidationStepResult(step=ValidationStep.TYPECHECK, success=True)

    async def run_pipeline(
        self,
        workspace_dir: str,
        steps: tuple[ValidationStep, ...] = (
            ValidationStep.TYPECHECK,
            ValidationStep.LINT,
            ValidationStep.TESTS,
            ValidationStep.BUILD,
        ),
    ) -> ValidationRunResult:
        step_results: list[ValidationStepResult] = []
        for step in steps:
            res = await self.run_step(workspace_dir, step)
            step_results.append(res)
            if not res.success:
                break
        return ValidationRunResult(
            steps=tuple(step_results),
            all_passed=all(r.success for r in step_results),
        )


class FakeWorkspaceManager(WorkspaceManagerPort):
    def __init__(self, workspaces: dict[str, CodeWorkspace] | None = None) -> None:
        self._workspaces: dict[str, CodeWorkspace] = workspaces or {}
        self.acquired_locks: list[ProjectId] = []
        self.released_locks: list[ProjectId] = []

    async def ensure_workspace(self, project_id: ProjectId) -> CodeWorkspace:
        if str(project_id) not in self._workspaces:
            self._workspaces[str(project_id)] = CodeWorkspace(
                id=WorkspaceId(f"ws_{project_id}"),
                project_id=project_id,
                status=WorkspaceStatus.READY,
                workspace_dir=f"/workspaces/{project_id}",
            )
        return self._workspaces[str(project_id)]

    async def get_workspace(self, project_id: ProjectId) -> CodeWorkspace | None:
        return self._workspaces.get(str(project_id))

    async def get_manifest(self, workspace: CodeWorkspace) -> tuple[str, ...]:
        return ()

    async def is_locked(self, project_id: ProjectId) -> bool:
        return False

    async def acquire_lock(self, project_id: ProjectId) -> None:
        self.acquired_locks.append(project_id)

    async def release_lock(self, project_id: ProjectId) -> None:
        self.released_locks.append(project_id)

    async def publish_preview(self, project_id: ProjectId) -> None:
        pass

    async def remove_feature_paths(self, project_id: ProjectId, slug: str) -> tuple[str, ...]:
        return ()

    async def update_text_file(
        self,
        project_id: ProjectId,
        relative_path: str,
        transform: object,
    ) -> None:
        pass

    async def revert_commit(self, project_id: ProjectId, commit: str) -> None:
        pass


@pytest.mark.asyncio
@pytest.mark.unit
async def test_validate_workspace_all_steps_pass() -> None:
    # Arrange
    runner = StepRecordingCodeRunner(failing_step=None)
    use_case = ValidateWorkspaceUseCase(code_runner=runner)
    input_data = ValidateWorkspaceInput(workspace_dir="/workspaces/prj_01")

    # Act
    output = await use_case.execute(input_data)

    # Assert
    assert output.all_passed is True
    assert output.failed_step is None
    assert len(output.steps) == 4
    assert output.error_summary == ()
    assert runner.executed_steps == [
        ValidationStep.TYPECHECK,
        ValidationStep.LINT,
        ValidationStep.TESTS,
        ValidationStep.BUILD,
    ]
    assert output.run_result.all_passed is True


@pytest.mark.asyncio
@pytest.mark.unit
async def test_validate_workspace_stops_on_typecheck_failure() -> None:
    # Arrange
    runner = StepRecordingCodeRunner(failing_step=ValidationStep.TYPECHECK)
    use_case = ValidateWorkspaceUseCase(code_runner=runner)
    input_data = ValidateWorkspaceInput(workspace_dir="/workspaces/prj_01")

    # Act
    output = await use_case.execute(input_data)

    # Assert
    assert output.all_passed is False
    assert output.failed_step == ValidationStep.TYPECHECK
    assert len(output.steps) == 1
    assert len(output.error_summary) > 0
    # Stop early: no debe ejecutar LINT, TESTS ni BUILD
    assert runner.executed_steps == [ValidationStep.TYPECHECK]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_validate_workspace_stops_on_lint_failure() -> None:
    # Arrange
    runner = StepRecordingCodeRunner(failing_step=ValidationStep.LINT)
    use_case = ValidateWorkspaceUseCase(code_runner=runner)
    input_data = ValidateWorkspaceInput(workspace_dir="/workspaces/prj_01")

    # Act
    output = await use_case.execute(input_data)

    # Assert
    assert output.all_passed is False
    assert output.failed_step == ValidationStep.LINT
    assert len(output.steps) == 2
    # Stop early: ejecuta TYPECHECK y LINT, pero no TESTS ni BUILD
    assert runner.executed_steps == [ValidationStep.TYPECHECK, ValidationStep.LINT]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_validate_workspace_stops_on_tests_failure() -> None:
    # Arrange
    runner = StepRecordingCodeRunner(failing_step=ValidationStep.TESTS)
    use_case = ValidateWorkspaceUseCase(code_runner=runner)
    input_data = ValidateWorkspaceInput(workspace_dir="/workspaces/prj_01")

    # Act
    output = await use_case.execute(input_data)

    # Assert
    assert output.all_passed is False
    assert output.failed_step == ValidationStep.TESTS
    assert len(output.steps) == 3
    # Stop early: ejecuta TYPECHECK, LINT y TESTS, pero no BUILD
    assert runner.executed_steps == [
        ValidationStep.TYPECHECK,
        ValidationStep.LINT,
        ValidationStep.TESTS,
    ]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_validate_workspace_stops_on_build_failure() -> None:
    # Arrange
    runner = StepRecordingCodeRunner(failing_step=ValidationStep.BUILD)
    use_case = ValidateWorkspaceUseCase(code_runner=runner)
    input_data = ValidateWorkspaceInput(workspace_dir="/workspaces/prj_01")

    # Act
    output = await use_case.execute(input_data)

    # Assert
    assert output.all_passed is False
    assert output.failed_step == ValidationStep.BUILD
    assert len(output.steps) == 4
    assert runner.executed_steps == [
        ValidationStep.TYPECHECK,
        ValidationStep.LINT,
        ValidationStep.TESTS,
        ValidationStep.BUILD,
    ]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_validate_workspace_resolves_workspace_via_workspace_manager() -> None:
    # Arrange
    prj_id = ProjectId("prj_01HT")
    ws = CodeWorkspace(
        id=WorkspaceId("ws_01"),
        project_id=prj_id,
        status=WorkspaceStatus.READY,
        workspace_dir="/custom/workspace/dir",
    )
    ws_mgr = FakeWorkspaceManager(workspaces={str(prj_id): ws})
    runner = StepRecordingCodeRunner(failing_step=None)
    use_case = ValidateWorkspaceUseCase(code_runner=runner, workspace_manager=ws_mgr)
    input_data = ValidateWorkspaceInput(project_id=prj_id)

    # Act
    output = await use_case.execute(input_data)

    # Assert
    assert output.all_passed is True
    assert len(output.steps) == 4


@pytest.mark.asyncio
@pytest.mark.unit
async def test_validate_workspace_raises_when_workspace_not_found() -> None:
    # Arrange
    ws_mgr = FakeWorkspaceManager(workspaces={})
    runner = StepRecordingCodeRunner(failing_step=None)
    use_case = ValidateWorkspaceUseCase(code_runner=runner, workspace_manager=ws_mgr)
    input_data = ValidateWorkspaceInput(project_id=ProjectId("prj_non_existent"))

    # Act & Assert
    with pytest.raises(WorkspaceNotFoundError):
        await use_case.execute(input_data)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_validate_workspace_custom_steps_subset() -> None:
    # Arrange
    runner = StepRecordingCodeRunner(failing_step=None)
    use_case = ValidateWorkspaceUseCase(code_runner=runner)
    custom_steps = (ValidationStep.TYPECHECK, ValidationStep.TESTS)
    input_data = ValidateWorkspaceInput(workspace_dir="/workspaces/prj_01", steps=custom_steps)

    # Act
    output = await use_case.execute(input_data)

    # Assert
    assert output.all_passed is True
    assert len(output.steps) == 2
    assert runner.executed_steps == [ValidationStep.TYPECHECK, ValidationStep.TESTS]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_validate_workspace_adquiere_y_libera_workspace_lock() -> None:
    # Arrange
    project_id = ProjectId("prj_lock_test")
    ws_mgr = FakeWorkspaceManager(
        workspaces={
            str(project_id): CodeWorkspace(
                id=WorkspaceId(f"ws_{project_id}"),
                project_id=project_id,
                status=WorkspaceStatus.READY,
                workspace_dir="/workspaces/prj_lock_test",
            )
        }
    )
    runner = StepRecordingCodeRunner(failing_step=None)
    use_case = ValidateWorkspaceUseCase(code_runner=runner, workspace_manager=ws_mgr)
    input_data = ValidateWorkspaceInput(project_id=project_id)

    # Act
    output = await use_case.execute(input_data)

    # Assert
    assert output.all_passed is True
    assert ws_mgr.acquired_locks == [project_id]
    assert ws_mgr.released_locks == [project_id]
