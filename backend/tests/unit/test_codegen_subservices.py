from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from kosmo.application.codegen.analyze_feature_integration import AnalyzeFeatureIntegrationUseCase
from kosmo.application.codegen.analyze_ux_context import UXAnalyzerUseCase
from kosmo.application.codegen.build_service import BuildService, OpenCodeGenerationError
from kosmo.application.codegen.implementation_context_builder import (
    ImplementationContextBuilder,
    NullFileSystemReader,
)
from kosmo.application.codegen.planning_service import PlanningService
from kosmo.application.codegen.post_deploy_service import PostDeployService
from kosmo.application.codegen.register_code_traceability import (
    RegisterCodeTraceabilityUseCase,
)
from kosmo.application.codegen.validation_service import ValidationService
from kosmo.contracts.sdd.codegen import (
    CodeRunnerPort,
    CodeWorkspace,
    FeatureImplementation,
    FeatureImplementationStatus,
    FileAction,
    FileOperation,
    ImplementationPlan,
    OpenCodeClientPort,
    OpenCodeEvent,
    OpenCodeEventType,
    OpenCodeSession,
    ValidationRunResult,
    ValidationStep,
    ValidationStepResult,
    WorkspaceManagerPort,
    WorkspaceStatus,
)
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import FeatureId, ImplementationId, ProjectId, WorkspaceId
from tests.unit.fakes import (
    InMemoryDocumentRepository,
    InMemoryFeatureImplementationRepository,
    InMemoryFeatureRepository,
    InMemoryProjectRepository,
    InMemoryRequirementRepository,
    InMemoryTraceabilityRepository,
)


class _FakeOpenCodeClient(OpenCodeClientPort):
    def __init__(self, plan_operations: tuple[FileOperation, ...] = (), should_error: bool = False) -> None:
        self.plan_operations = plan_operations
        self.should_error = should_error
        self.prompts_sent: list[tuple[str, str, str]] = []

    async def health_check(self) -> bool:
        return True

    async def create_session(self, workspace_dir: str, *, title: str = "") -> OpenCodeSession:
        return OpenCodeSession(session_id="oc_test_sess", workspace_dir=workspace_dir, title=title)

    async def send_prompt(
        self,
        session_id: str,
        prompt: str,
        *,
        agent: str = "plan",
    ) -> AsyncIterator[OpenCodeEvent]:
        self.prompts_sent.append((session_id, prompt, agent))
        if self.should_error:
            yield OpenCodeEvent(
                event_type=OpenCodeEventType.ERROR,
                session_id=session_id,
                data={"error": "Fallo simulado en OpenCode"},
            )
            return

        if agent == "plan":
            ops_data = [
                {"action": op.action.value, "path": op.path, "description": op.description}
                for op in self.plan_operations
            ]
            yield OpenCodeEvent(
                event_type=OpenCodeEventType.PLAN_COMPLETE,
                session_id=session_id,
                data={"operations": ops_data},
            )
        elif agent == "build":
            yield OpenCodeEvent(
                event_type=OpenCodeEventType.FILE_EDIT,
                session_id=session_id,
                data={"path": "src/app/test/page.tsx"},
            )
            yield OpenCodeEvent(
                event_type=OpenCodeEventType.BUILD_COMPLETE,
                session_id=session_id,
                data={"files": ["src/app/test/page.tsx", "src/features/test/logic.ts"]},
            )


class _FakeWorkspaceManager(WorkspaceManagerPort):
    def __init__(self) -> None:
        self.rollback_called = False
        self.committed_messages: list[str] = []

    async def ensure_workspace(self, project_id: ProjectId) -> CodeWorkspace:
        return CodeWorkspace(
            id=WorkspaceId(f"ws_{project_id}"),
            project_id=project_id,
            status=WorkspaceStatus.READY,
            workspace_dir="/workspace",
        )

    async def get_workspace(self, project_id: ProjectId) -> CodeWorkspace | None:
        return await self.ensure_workspace(project_id)

    async def get_manifest(self, workspace: CodeWorkspace) -> tuple[str, ...]:
        return ()

    async def is_locked(self, project_id: ProjectId) -> bool:
        return False

    async def acquire_lock(self, project_id: ProjectId) -> None:
        pass

    async def release_lock(self, project_id: ProjectId) -> None:
        pass

    async def rollback_workspace(self, project_id: ProjectId) -> None:
        self.rollback_called = True

    async def commit_workspace(self, project_id: ProjectId, message: str) -> str | None:
        self.committed_messages.append(message)
        return "commit_sha_123"

    async def remove_feature_paths(self, project_id: ProjectId, slug: str) -> tuple[str, ...]:
        return ()

    async def update_text_file(self, project_id: ProjectId, relative_path: str, transform: object) -> None:
        pass

    async def revert_commit(self, project_id: ProjectId, commit: str) -> None:
        pass


class _FakeCodeRunner(CodeRunnerPort):
    def __init__(self, all_passed: bool = True) -> None:
        self.all_passed = all_passed
        self.calls: list[str] = []

    async def run_pipeline(self, workspace_dir: str, *, run_id: str | None = None) -> ValidationRunResult:
        self.calls.append(workspace_dir)
        return ValidationRunResult(
            steps=(
                ValidationStepResult(step=ValidationStep.TYPECHECK, success=self.all_passed),
                ValidationStepResult(step=ValidationStep.LINT, success=self.all_passed),
            ),
            all_passed=self.all_passed,
            error_summary=() if self.all_passed else ("Error de compilación",),
        )


def _a_feature() -> Feature:
    return Feature(
        id=FeatureId("feat_sub_01"),
        project_id=ProjectId("prj_sub_01"),
        number=1,
        title="Gestión de Categorías",
        slug="gestion-categorias",
        description="Permite crear y listar categorías.",
    )


def _an_impl(feature: Feature) -> FeatureImplementation:
    return FeatureImplementation(
        id=ImplementationId("impl_sub_01"),
        feature_id=feature.id,
        project_id=feature.project_id,
        status=FeatureImplementationStatus.IN_PROGRESS,
        max_attempts=3,
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_planning_service_executes_plan_and_persists() -> None:
    feature = _a_feature()
    impl = _an_impl(feature)
    impl_repo = InMemoryFeatureImplementationRepository()
    await impl_repo.save(impl)

    plan_ops = (
        FileOperation(action=FileAction.CREATE, path="src/app/gestion-categorias/page.tsx", description="Page"),
    )
    opencode = _FakeOpenCodeClient(plan_operations=plan_ops)
    context_builder = ImplementationContextBuilder(
        project_repo=InMemoryProjectRepository(),
        document_repo=InMemoryDocumentRepository(),
        implementation_repo=impl_repo,
        feature_repo=InMemoryFeatureRepository(),
        fs_reader=NullFileSystemReader(),
    )
    integration_analyzer = AnalyzeFeatureIntegrationUseCase(
        feature_repo=InMemoryFeatureRepository(),
        document_repo=InMemoryDocumentRepository(),
        implementation_repo=impl_repo,
    )
    ux_analyzer = UXAnalyzerUseCase(
        document_repo=InMemoryDocumentRepository(),
        feature_repo=InMemoryFeatureRepository(),
    )

    service = PlanningService(
        opencode_client=opencode,
        context_builder=context_builder,
        integration_analyzer=integration_analyzer,
        ux_analyzer=ux_analyzer,
        implementation_repo=impl_repo,
    )

    events: list[OpenCodeEvent] = []

    async def _emit(ev: OpenCodeEvent) -> None:
        events.append(ev)

    res = await service.execute_plan(
        feature=feature,
        req_markdown="### REQ-1.1 Categorías",
        diagram_syntax="@startuml\nstart\nstop\n@enduml",
        workspace_dir="/workspace",
        manifest_files=(),
        session_id="oc_test_sess",
        impl=impl,
        emit_event=_emit,
    )

    assert res.impl_plan is not None
    assert len(res.impl_plan.operations) == 1
    assert res.impl_plan.operations[0].path == "src/app/gestion-categorias/page.tsx"
    saved = await impl_repo.by_id(impl.id)
    assert saved is not None
    assert saved.plan is not None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_build_service_executes_build_and_collects_files() -> None:
    feature = _a_feature()
    opencode = _FakeOpenCodeClient()
    ws_manager = _FakeWorkspaceManager()
    context_builder = ImplementationContextBuilder(
        project_repo=InMemoryProjectRepository(),
        document_repo=InMemoryDocumentRepository(),
        implementation_repo=InMemoryFeatureImplementationRepository(),
        feature_repo=InMemoryFeatureRepository(),
        fs_reader=NullFileSystemReader(),
    )

    service = BuildService(
        opencode_client=opencode,
        context_builder=context_builder,
        workspace_manager=ws_manager,
        fs_reader=NullFileSystemReader(),
    )

    events: list[OpenCodeEvent] = []

    async def _emit(ev: OpenCodeEvent) -> None:
        events.append(ev)

    plan = ImplementationPlan(
        feature_id=feature.id,
        operations=(FileOperation(action=FileAction.CREATE, path="src/app/test/page.tsx"),),
        summary="Plan",
    )

    generated = await service.execute_build(
        feature=feature,
        req_markdown="REQ-1",
        diagram_syntax="",
        ux_prompt_block="",
        project_context="",
        impl_plan=plan,
        product_map=None,
        workspace_dir="/workspace",
        session_id="oc_test_sess",
        emit_event=_emit,
    )

    assert "src/app/test/page.tsx" in generated
    assert "src/features/test/logic.ts" in generated


@pytest.mark.asyncio
@pytest.mark.unit
async def test_build_service_raises_on_opencode_error_when_workspace_invalid() -> None:
    feature = _a_feature()
    opencode = _FakeOpenCodeClient(should_error=True)
    ws_manager = _FakeWorkspaceManager()
    context_builder = ImplementationContextBuilder(
        project_repo=InMemoryProjectRepository(),
        document_repo=InMemoryDocumentRepository(),
        implementation_repo=InMemoryFeatureImplementationRepository(),
        feature_repo=InMemoryFeatureRepository(),
        fs_reader=NullFileSystemReader(),
    )

    service = BuildService(
        opencode_client=opencode,
        context_builder=context_builder,
        workspace_manager=ws_manager,
        fs_reader=NullFileSystemReader(),
    )

    async def _emit(ev: OpenCodeEvent) -> None:
        pass

    plan = ImplementationPlan(feature_id=feature.id, operations=(), summary="Plan")

    with pytest.raises(OpenCodeGenerationError):
        await service.execute_build(
            feature=feature,
            req_markdown="REQ-1",
            diagram_syntax="",
            ux_prompt_block="",
            project_context="",
            impl_plan=plan,
            product_map=None,
            workspace_dir="/workspace",
            session_id="oc_test_sess",
            emit_event=_emit,
        )

    assert ws_manager.rollback_called is True


@pytest.mark.asyncio
@pytest.mark.unit
async def test_validation_service_success_on_first_attempt() -> None:
    feature = _a_feature()
    impl = _an_impl(feature)
    impl_repo = InMemoryFeatureImplementationRepository()
    await impl_repo.save(impl)

    code_runner = _FakeCodeRunner(all_passed=True)
    opencode = _FakeOpenCodeClient()
    context_builder = ImplementationContextBuilder(
        project_repo=InMemoryProjectRepository(),
        document_repo=InMemoryDocumentRepository(),
        implementation_repo=impl_repo,
        feature_repo=InMemoryFeatureRepository(),
        fs_reader=NullFileSystemReader(),
    )

    service = ValidationService(
        code_runner=code_runner,
        opencode_client=opencode,
        context_builder=context_builder,
        implementation_repo=impl_repo,
        fs_reader=NullFileSystemReader(),
    )

    events: list[OpenCodeEvent] = []

    async def _emit(ev: OpenCodeEvent) -> None:
        events.append(ev)

    # Valid slice files so structural check passes
    valid_files = {
        "src/app/gestion-categorias/page.tsx",
        "src/features/gestion-categorias/manifest.ts",
        "src/lib/feature-registry.ts",
    }

    res = await service.execute_validation(
        feature=feature,
        workspace_dir="/workspace",
        session_id="oc_test_sess",
        product_map=None,
        generated_files=valid_files,
        impl=impl,
        max_retries=3,
        run_id="run_123",
        emit_event=_emit,
    )

    assert res.validation_result is not None
    assert res.validation_result.all_passed is True
    assert res.attempt == 1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_post_deploy_service_handle_success() -> None:
    feature = _a_feature()
    impl = _an_impl(feature)
    impl_repo = InMemoryFeatureImplementationRepository()
    await impl_repo.save(impl)
    ws_manager = _FakeWorkspaceManager()

    traceability_repo = InMemoryTraceabilityRepository()
    req_repo = InMemoryRequirementRepository()
    register_traceability = RegisterCodeTraceabilityUseCase(
        traceability_repo=traceability_repo,
        requirement_repo=req_repo,
    )

    service = PostDeployService(
        workspace_manager=ws_manager,
        implementation_repo=impl_repo,
        register_traceability=register_traceability,
    )

    events: list[OpenCodeEvent] = []

    async def _emit(ev: OpenCodeEvent) -> None:
        events.append(ev)

    val_result = ValidationRunResult(
        steps=(ValidationStepResult(step=ValidationStep.STRUCTURE, success=True),),
        all_passed=True,
    )

    result = await service.handle_success(
        feature=feature,
        impl=impl,
        workspace=None,
        session_id="oc_test_sess",
        generated_files={"src/app/page.tsx"},
        req_markdown="REQ-1.1",
        validation_result=val_result,
        retry_history=(),
        attempt=1,
        val_duration=2.5,
        total_start=0.0,
        emit_event=_emit,
    )

    assert result.success is True
    assert result.status == FeatureImplementationStatus.IMPLEMENTED
    assert len(ws_manager.committed_messages) == 1
    assert any(ev.event_type == OpenCodeEventType.DONE for ev in events)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_post_deploy_service_handle_success_triggers_auto_github_sync() -> None:
    # Arrange
    from unittest.mock import AsyncMock, MagicMock

    from kosmo.application.integrations.sync_github_repository import SyncGitHubRepositoryUseCase
    from kosmo.contracts.sdd.ids import UserId

    feature = _a_feature()
    impl = _an_impl(feature)
    impl_repo = InMemoryFeatureImplementationRepository()
    await impl_repo.save(impl)
    ws_manager = _FakeWorkspaceManager()

    traceability_repo = InMemoryTraceabilityRepository()
    req_repo = InMemoryRequirementRepository()
    register_traceability = RegisterCodeTraceabilityUseCase(
        traceability_repo=traceability_repo,
        requirement_repo=req_repo,
    )

    project_repo = AsyncMock()
    project = MagicMock()
    project.id = feature.project_id
    project.name = "My App"
    project.slug = "my-app"
    project.owner_id = UserId("usr_test_owner")
    project_repo.by_id.return_value = project

    mock_sync_github = AsyncMock(spec=SyncGitHubRepositoryUseCase)
    mock_sync_result = MagicMock()
    mock_sync_result.repo_url = "https://github.com/owner/my-app.git"
    mock_sync_result.last_commit_hash = "abc123commit"
    mock_sync_github.execute.return_value = mock_sync_result

    service = PostDeployService(
        workspace_manager=ws_manager,
        implementation_repo=impl_repo,
        register_traceability=register_traceability,
        project_repo=project_repo,
        sync_github_repository=mock_sync_github,
    )

    events: list[OpenCodeEvent] = []

    async def _emit(ev: OpenCodeEvent) -> None:
        events.append(ev)

    val_result = ValidationRunResult(
        steps=(ValidationStepResult(step=ValidationStep.STRUCTURE, success=True),),
        all_passed=True,
    )

    # Act
    result = await service.handle_success(
        feature=feature,
        impl=impl,
        workspace=None,
        session_id="oc_test_sess",
        generated_files={"src/app/page.tsx"},
        req_markdown="REQ-1.1",
        validation_result=val_result,
        retry_history=(),
        attempt=1,
        val_duration=2.5,
        total_start=0.0,
        emit_event=_emit,
    )

    # Assert
    assert result.success is True
    assert result.status == FeatureImplementationStatus.IMPLEMENTED
    mock_sync_github.execute.assert_awaited_once()
    sync_cmd, user_id_arg = mock_sync_github.execute.call_args[0]
    assert sync_cmd.project_id == feature.project_id
    assert sync_cmd.skip_lock is True
    assert sync_cmd.skip_validation is True
    assert sync_cmd.repo_name == "my-app"
    assert user_id_arg == UserId("usr_test_owner")

    # Verifica que se emitio el evento de github_synced
    synced_events = [ev for ev in events if ev.data.get("stage") == "github_synced"]
    assert len(synced_events) == 1
    assert synced_events[0].data["repo_url"] == "https://github.com/owner/my-app.git"
    assert synced_events[0].data["commit_hash"] == "abc123commit"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_post_deploy_service_handle_failure() -> None:
    feature = _a_feature()
    impl = _an_impl(feature)
    impl_repo = InMemoryFeatureImplementationRepository()
    await impl_repo.save(impl)
    ws_manager = _FakeWorkspaceManager()

    traceability_repo = InMemoryTraceabilityRepository()
    req_repo = InMemoryRequirementRepository()
    register_traceability = RegisterCodeTraceabilityUseCase(
        traceability_repo=traceability_repo,
        requirement_repo=req_repo,
    )

    service = PostDeployService(
        workspace_manager=ws_manager,
        implementation_repo=impl_repo,
        register_traceability=register_traceability,
    )

    events: list[OpenCodeEvent] = []

    async def _emit(ev: OpenCodeEvent) -> None:
        events.append(ev)

    result = await service.handle_failure(
        feature=feature,
        impl=impl,
        workspace=None,
        session_id="oc_test_sess",
        generated_files=set(),
        validation_result=None,
        retry_history=(("Error en paso 1",),),
        attempt=3,
        max_retries=3,
        val_duration=5.0,
        total_start=0.0,
        emit_event=_emit,
    )

    assert result.success is False
    assert result.status == FeatureImplementationStatus.REQUIRES_REVIEW
    assert ws_manager.rollback_called is True
    assert any(ev.event_type == OpenCodeEventType.ERROR for ev in events)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_execution_and_verification_subservice_aliases_and_injection() -> None:
    from kosmo.application.codegen import (
        BuildService,
        ExecutionService,
        GenerateFeatureImplementationUseCase,
        ValidationService,
        VerificationService,
    )

    assert ExecutionService is BuildService
    assert VerificationService is ValidationService

    exec_srv = ExecutionService(
        opencode_client=_FakeOpenCodeClient(),
        context_builder=ImplementationContextBuilder(),
        workspace_manager=_FakeWorkspaceManager(),
        fs_reader=NullFileSystemReader(),
    )
    verif_srv = VerificationService(
        code_runner=_FakeCodeRunner(ValidationRunResult(all_passed=True, steps=())),
        opencode_client=_FakeOpenCodeClient(),
        context_builder=ImplementationContextBuilder(),
        implementation_repo=InMemoryFeatureImplementationRepository(),
        fs_reader=NullFileSystemReader(),
    )

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=InMemoryFeatureRepository(),
        requirement_repo=InMemoryRequirementRepository(),
        activity_diagram_repo=None,  # type: ignore[arg-type]
        workspace_manager=_FakeWorkspaceManager(),
        opencode_client=_FakeOpenCodeClient(),
        code_runner=_FakeCodeRunner(ValidationRunResult(all_passed=True, steps=())),
        implementation_repo=InMemoryFeatureImplementationRepository(),
        traceability_repo=InMemoryTraceabilityRepository(),
        execution_service=exec_srv,
        verification_service=verif_srv,
    )
    assert use_case._build_service is exec_srv
    assert use_case._validation_service is verif_srv
