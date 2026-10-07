from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from kosmo.application.codegen.generate_feature_implementation import (
    GenerateFeatureImplementationInput,
    GenerateFeatureImplementationUseCase,
    MissingDiagramError,
    MissingRequirementsError,
    OpenCodeGenerationError,
    OpenCodeUnavailableError,
    _collect_workspace_feature_files,
    _get_existing_db_schema_context,
    _normalize_generated_file_path,
    _raise_for_opencode_error,
)
from kosmo.contracts.sdd.activity_diagram import DiagramaActividad
from kosmo.contracts.sdd.codegen import (
    CodeRunnerPort,
    CodeWorkspace,
    FeatureImplementation,
    FeatureImplementationRepository,
    FeatureImplementationStatus,
    FileOperation,
    FileSystemReader,
    OpenCodeClientPort,
    OpenCodeEvent,
    OpenCodeEventType,
    OpenCodeSession,
    ValidationErrorDetail,
    ValidationRunResult,
    ValidationSeverity,
    ValidationStep,
    ValidationStepResult,
    WorkspaceManagerPort,
    WorkspaceStatus,
)
from kosmo.contracts.sdd.errors import FeatureNotFoundError
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import (
    ActivityDiagramId,
    FeatureId,
    ImplementationId,
    ProjectId,
    UserId,
    WorkspaceId,
)
from kosmo.contracts.sdd.project import Project
from kosmo.domain.sdd.document_converters import markdown_to_document
from kosmo.infrastructure.codegen.workspace import WorkspaceLockedError
from tests.unit.fakes import (
    InMemoryActivityDiagramRepository,
    InMemoryDocumentRepository,
    InMemoryFeatureRepository,
    InMemoryProjectRepository,
    InMemoryRequirementRepository,
    InMemoryTraceabilityRepository,
)


class FakeWorkspaceManager(WorkspaceManagerPort, FileSystemReader):
    def __init__(self, workspace_dir: str = "/workspaces/prj_01") -> None:
        self.workspace_dir = workspace_dir
        self.locked_projects: set[str] = set()
        self.rollback_called_for: set[str] = set()
        self.commit_called_for: list[tuple[str, str]] = []
        self.manifest: tuple[str, ...] = ("package.json", "tsconfig.json", "src/index.ts")

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

    async def ensure_workspace(self, project_id: ProjectId) -> CodeWorkspace:
        return CodeWorkspace(
            id=WorkspaceId(f"ws_{project_id}"),
            project_id=project_id,
            status=WorkspaceStatus.READY,
            workspace_dir=self.workspace_dir,
            manifest_files=self.manifest,
        )

    async def get_workspace(self, project_id: ProjectId) -> CodeWorkspace | None:
        return await self.ensure_workspace(project_id)

    async def get_manifest(self, workspace: CodeWorkspace) -> tuple[str, ...]:
        return self.manifest

    async def is_locked(self, project_id: ProjectId) -> bool:
        return str(project_id) in self.locked_projects

    async def acquire_lock(self, project_id: ProjectId) -> None:
        if str(project_id) in self.locked_projects:
            raise WorkspaceLockedError(f"Workspace {project_id} already locked")
        self.locked_projects.add(str(project_id))

    async def release_lock(self, project_id: ProjectId) -> None:
        self.locked_projects.discard(str(project_id))

    async def rollback_workspace(self, project_id: ProjectId) -> None:
        self.rollback_called_for.add(str(project_id))

    async def commit_workspace(self, project_id: ProjectId, message: str) -> str | None:
        self.commit_called_for.append((str(project_id), message))
        return "hash_commit"

    async def remove_feature_paths(self, project_id: ProjectId, slug: str) -> tuple[str, ...]:
        return ()

    async def update_text_file(
        self,
        project_id: ProjectId,
        relative_path: str,
        transform: object,
    ) -> None:
        return None

    async def revert_commit(self, project_id: ProjectId, commit: str) -> None:
        return None


class FakeOpenCodeClient(OpenCodeClientPort):
    def __init__(self, generated_files: tuple[str, ...] | None = None) -> None:
        self.closed_sessions: set[str] = set()
        self.created_sessions: list[OpenCodeSession] = []
        self.prompts_sent: list[tuple[str, str, str]] = []
        self._custom_files = list(generated_files) if generated_files is not None else None
        self.plan_operations: tuple[FileOperation, ...] = ()

    def _get_files(self, prompt: str) -> list[str]:
        if self._custom_files is not None:
            return self._custom_files
        import re

        slug_match = re.search(r"src/features/([a-zA-Z0-9_\-]+)/", prompt)
        if slug_match and slug_match.group(1) != "slug":
            slug = slug_match.group(1)
        else:
            title_match = re.search(r"feature '([^']+)'", prompt)
            if title_match:
                slug = re.sub(r"[^a-zA-Z0-9]+", "-", title_match.group(1).lower()).strip("-")
            else:
                slug = "registrar-gastos"

        return [
            f"src/app/{slug}/page.tsx",
            f"src/features/{slug}/manifest.ts",
            f"src/features/{slug}/logic.ts",
            "src/lib/feature-registry.ts",
            f"tests/{slug}.test.ts",
        ]

    async def health_check(self) -> bool:
        return True

    async def create_session(self, workspace_dir: str, *, title: str = "") -> OpenCodeSession:
        session = OpenCodeSession(
            session_id=f"oc_sess_{len(self.created_sessions) + 1}",
            workspace_dir=workspace_dir,
            title=title,
        )
        self.created_sessions.append(session)
        return session

    async def send_prompt(
        self,
        session_id: str,
        prompt: str,
        *,
        agent: str = "plan",
    ) -> AsyncIterator[OpenCodeEvent]:
        self.prompts_sent.append((session_id, prompt, agent))
        files = self._get_files(prompt)
        if agent == "plan":
            yield OpenCodeEvent(
                event_type=OpenCodeEventType.PLAN_PROGRESS,
                session_id=session_id,
                data={"delta": "Analizando estructura..."},
            )
            yield OpenCodeEvent(
                event_type=OpenCodeEventType.PLAN_COMPLETE,
                session_id=session_id,
                data={
                    "plan": "\n".join(f"CREATE {f}" for f in files),
                    "operations": [{"path": f, "action": "create"} for f in files],
                },
            )
        elif agent == "build":
            yield OpenCodeEvent(
                event_type=OpenCodeEventType.BUILD_PROGRESS,
                session_id=session_id,
                data={"delta": "Generando archivos..."},
            )
            for f in files:
                yield OpenCodeEvent(
                    event_type=OpenCodeEventType.FILE_EDIT,
                    session_id=session_id,
                    data={"path": f, "action": "create"},
                )
            yield OpenCodeEvent(
                event_type=OpenCodeEventType.BUILD_COMPLETE,
                session_id=session_id,
                data={"status": "success", "files": files},
            )

    async def close_session(self, session_id: str) -> None:
        self.closed_sessions.add(session_id)


class FakeCodeRunner(CodeRunnerPort):
    def __init__(self, should_pass: bool = True, fail_count_before_pass: int = 0) -> None:
        self.should_pass = should_pass
        self.fail_count_before_pass = fail_count_before_pass
        self.runs_count = 0
        self.run_ids: list[str] = []

    async def run_step(
        self,
        workspace_dir: str,
        step: ValidationStep,
        *,
        timeout_seconds: int = 300,
    ) -> ValidationStepResult:
        return ValidationStepResult(step=step, success=True)

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
        run_id: str = "",
    ) -> ValidationRunResult:
        self.runs_count += 1
        self.run_ids.append(run_id)
        if self.fail_count_before_pass > 0 and self.runs_count <= self.fail_count_before_pass:
            return ValidationRunResult(
                all_passed=False,
                steps=(
                    ValidationStepResult(
                        step=ValidationStep.TYPECHECK,
                        success=False,
                        errors=(
                            ValidationErrorDetail(
                                file="src/calc.ts",
                                line=10,
                                column=5,
                                message="Cannot find name 'result'",
                                severity=ValidationSeverity.ERROR,
                            ),
                        ),
                        error_messages=("src/calc.ts:10:5 - error TS2304: Cannot find name 'result'",),
                    ),
                ),
                error_summary=("Typecheck falló con 1 error",),
            )

        if not self.should_pass:
            return ValidationRunResult(
                all_passed=False,
                steps=(
                    ValidationStepResult(
                        step=ValidationStep.TESTS,
                        success=False,
                        error_messages=("AssertionError: expected 5 to be 10",),
                    ),
                ),
                error_summary=("Tests fallaron",),
            )

        return ValidationRunResult(
            all_passed=True,
            steps=tuple(ValidationStepResult(step=s, success=True) for s in steps),
        )


class FakeFeatureImplementationRepository(FeatureImplementationRepository):
    def __init__(self) -> None:
        self.implementations: dict[str, FeatureImplementation] = {}

    async def by_feature_id(self, feature_id: FeatureId) -> FeatureImplementation | None:
        return self.implementations.get(str(feature_id))

    async def by_id(self, implementation_id: ImplementationId) -> FeatureImplementation | None:
        return next((impl for impl in self.implementations.values() if impl.id == implementation_id), None)

    async def list_by_project(self, project_id: ProjectId) -> list[FeatureImplementation]:
        return [impl for impl in self.implementations.values() if impl.project_id == project_id]

    async def save(self, implementation: FeatureImplementation) -> FeatureImplementation:
        self.implementations[str(implementation.feature_id)] = implementation
        return implementation

    async def delete(self, feature_id: FeatureId) -> None:
        self.implementations.pop(str(feature_id), None)


class RaisingTraceabilityRepository(InMemoryTraceabilityRepository):
    async def add_edge(self, *args: object, **kwargs: object) -> None:
        raise RuntimeError("db down")

    async def delete_by_entity_id(self, entity_id: str) -> None:
        raise RuntimeError("db down")


class UnhealthyOpenCodeClient(FakeOpenCodeClient):
    async def health_check(self) -> bool:
        return False


class ExplodingOpenCodeClient(FakeOpenCodeClient):
    """Falla en la llamada N de send_prompt para un agente dado (1-based)."""

    def __init__(self, agent: str, explode_on_call: int = 1) -> None:
        super().__init__()
        self._agent = agent
        self._explode_on_call = explode_on_call
        self._agent_call_counts: dict[str, int] = {}

    async def send_prompt(
        self,
        session_id: str,
        prompt: str,
        *,
        agent: str = "plan",
    ) -> AsyncIterator[OpenCodeEvent]:
        call = self._agent_call_counts.get(agent, 0) + 1
        self._agent_call_counts[agent] = call
        if agent == self._agent and call == self._explode_on_call:
            raise RuntimeError(f"OpenCode failed during {agent} phase")
        async for ev in super().send_prompt(session_id, prompt, agent=agent):
            yield ev


@pytest.mark.unit
def test_opencode_error_event_stops_the_current_generation() -> None:
    event = OpenCodeEvent(
        event_type=OpenCodeEventType.ERROR,
        session_id="session-1",
        data={"error": "Tiempo de espera agotado al comunicar con OpenCode"},
    )

    with pytest.raises(OpenCodeGenerationError, match="Tiempo de espera agotado"):
        _raise_for_opencode_error(event)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_feature_implementation_success() -> None:
    # Arrange
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    workspace_manager = FakeWorkspaceManager()
    opencode_client = FakeOpenCodeClient()
    code_runner = FakeCodeRunner(should_pass=True)
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    feat_id = FeatureId("feat_01HT_GASTOS")
    prj_id = ProjectId("prj_01HT_APP")
    feature = Feature(
        id=feat_id,
        number=1,
        title="Registrar gastos",
        slug="registrar-gastos",
        description="Permite registrar transacciones de gastos",
        project_id=prj_id,
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-1.1: El sistema registrará los gastos")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_01"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstart\n:Registrar gasto;\nstop\n@enduml",
        )
    )

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    # Act
    output = await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id))

    # Assert
    assert output.success is True
    assert output.status == FeatureImplementationStatus.IMPLEMENTED
    assert output.implementation is not None
    assert output.implementation.status == FeatureImplementationStatus.IMPLEMENTED
    assert output.workspace is not None
    assert output.validation_result is not None
    assert output.validation_result.all_passed is True
    assert any("page.tsx" in f for f in output.generated_files)
    assert len(opencode_client.closed_sessions) == 1
    assert len(workspace_manager.commit_called_for) == 1
    assert workspace_manager.commit_called_for[0][0] == str(prj_id)
    assert "C01" in workspace_manager.commit_called_for[0][1]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_events_include_run_id() -> None:
    # Arrange
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    workspace_manager = FakeWorkspaceManager()
    opencode_client = FakeOpenCodeClient()
    code_runner = FakeCodeRunner(should_pass=True)
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    feat_id = FeatureId("feat_01HT_RUNID")
    prj_id = ProjectId("prj_01HT_APP")
    feature = Feature(
        id=feat_id,
        number=1,
        title="Registrar gastos",
        slug="registrar-gastos",
        description="Permite registrar transacciones de gastos",
        project_id=prj_id,
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-1.1: El sistema registrará los gastos")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_runid"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstart\n:Registrar gasto;\nstop\n@enduml",
        )
    )

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    # Act
    output = await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id))

    # Assert — todos los eventos comparten el mismo run_id (correlation ID de la ejecución)
    assert len(output.events) > 0
    run_ids = {event.run_id for event in output.events}
    assert len(run_ids) == 1
    run_id = run_ids.pop()
    assert len(run_id) == 32  # ULID en hex
    assert all(event.run_id == run_id for event in output.events)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_propaga_run_id_a_la_validacion() -> None:
    # Arrange
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    workspace_manager = FakeWorkspaceManager()
    opencode_client = FakeOpenCodeClient()
    code_runner = FakeCodeRunner(should_pass=True)
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    feat_id = FeatureId("feat_01HT_RUNVAL")
    prj_id = ProjectId("prj_01HT_APP")
    feature = Feature(
        id=feat_id,
        number=1,
        title="Registrar gastos",
        slug="registrar-gastos",
        description="Permite registrar transacciones de gastos",
        project_id=prj_id,
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-1.1: El sistema registrará los gastos")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_runval"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstart\n:Registrar gasto;\nstop\n@enduml",
        )
    )

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    # Act
    output = await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id))

    # Assert — la validación recibe el mismo run_id que los eventos de la generación
    assert output.events
    assert code_runner.run_ids == [output.events[0].run_id]
    assert code_runner.run_ids[0] != ""


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_events_no_mencionan_opencode() -> None:
    # Arrange
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    workspace_manager = FakeWorkspaceManager()
    opencode_client = FakeOpenCodeClient()
    code_runner = FakeCodeRunner(should_pass=True)
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    feat_id = FeatureId("feat_01HT_NOOC")
    prj_id = ProjectId("prj_01HT_APP")
    feature = Feature(
        id=feat_id,
        number=1,
        title="Registrar gastos",
        slug="registrar-gastos",
        description="Permite registrar transacciones de gastos",
        project_id=prj_id,
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-1.1: El sistema registrará los gastos")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_nooc"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstart\n:Registrar gasto;\nstop\n@enduml",
        )
    )

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    # Act
    output = await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id))

    # Assert — los mensajes visibles para el usuario (delta/error) no mencionan OpenCode
    user_visible: list[str] = []
    for event in output.events:
        delta = event.data.get("delta")
        if isinstance(delta, str):
            user_visible.append(delta)
        error = event.data.get("error")
        if isinstance(error, str):
            user_visible.append(error)
    assert user_visible
    assert all("opencode" not in text.lower() for text in user_visible)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_feature_implementation_incluye_contexto_y_ui_en_prompts() -> None:
    # Arrange
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    project_repo = InMemoryProjectRepository()
    document_repo = InMemoryDocumentRepository()
    workspace_manager = FakeWorkspaceManager()
    opencode_client = FakeOpenCodeClient()
    code_runner = FakeCodeRunner(should_pass=True)
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    feat_id = FeatureId("feat_01HT_UI")
    prj_id = ProjectId("prj_01HT_APP")
    await project_repo.save(
        Project(
            id=prj_id,
            name="Papelería",
            slug="papeleria",
            description="Papelería de barrio en Quito",
            owner_id=UserId("usr_01"),
        )
    )
    await document_repo.save_discovery(
        prj_id,
        markdown_to_document("# Visión del producto\n\nVenta de útiles escolares para niños y jóvenes de colegio."),
    )
    feature = Feature(
        id=feat_id,
        number=1,
        title="Registrar productos",
        slug="registrar-productos",
        description="Permite registrar productos con su precio",
        project_id=prj_id,
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-1.1: El sistema registrará los productos")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_ui"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstart\n:Registrar producto;\nstop\n@enduml",
        )
    )

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
        project_repo=project_repo,
        document_repo=document_repo,
    )

    # Act
    await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id))

    # Assert — los prompts llevan contexto del proyecto (nombre, descripción, visión)
    assert len(opencode_client.prompts_sent) == 2
    plan_prompt = opencode_client.prompts_sent[0][1]
    build_prompt = opencode_client.prompts_sent[1][1]
    assert "Papelería" in plan_prompt
    assert "Papelería de barrio en Quito" in plan_prompt
    assert "Visión del producto" in build_prompt
    assert "útiles escolares" in build_prompt

    # Assert — los prompts exigen la UI funcional (slice, ruta, registro)
    assert "src/features/<slug>/" in plan_prompt
    assert "src/app/<slug>/page.tsx" in plan_prompt
    assert "feature-registry.ts" in build_prompt
    assert "src/components/ui/" in build_prompt


@pytest.mark.asyncio
@pytest.mark.unit
async def test_plan_prompt_incluye_documento_completo_sin_truncar() -> None:
    # Arrange — documento de descubrimiento mayor al antiguo límite de 2500 caracteres
    project_repo = InMemoryProjectRepository()
    document_repo = InMemoryDocumentRepository()
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    workspace_manager = FakeWorkspaceManager()
    opencode_client = FakeOpenCodeClient()
    code_runner = FakeCodeRunner(should_pass=True)
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    feat_id = FeatureId("feat_01HT_VISION")
    prj_id = ProjectId("prj_01HT_VISION")
    tail_marker = "MARCADOR_FINAL_DEL_DOCUMENTO_12345"
    long_vision = "El sistema permitirá gestionar gastos compartidos entre amigos y familiares. " * 100 + tail_marker
    await project_repo.save(
        Project(
            id=prj_id,
            name="GastoJusto",
            slug="gasto-justo",
            description="Control de gastos compartidos",
            owner_id=UserId("usr_01"),
        )
    )
    await document_repo.save_discovery(prj_id, markdown_to_document(f"# Visión del producto\n\n{long_vision}"))
    feature = Feature(
        id=feat_id,
        number=1,
        title="Registrar gastos",
        slug="registrar-gastos",
        description="Permite registrar transacciones de gastos",
        project_id=prj_id,
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-1.1: El sistema registrará los gastos")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_vision"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstart\n:Registrar gasto;\nstop\n@enduml",
        )
    )

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
        project_repo=project_repo,
        document_repo=document_repo,
    )

    # Act
    await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id))

    # Assert — el documento de descubrimiento se envía completo a OpenCode, sin truncar
    plan_prompt = opencode_client.prompts_sent[0][1]
    assert len(long_vision) > 2500
    assert tail_marker in plan_prompt


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_feature_implementation_raises_when_feature_not_found() -> None:
    # Arrange
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    workspace_manager = FakeWorkspaceManager()
    opencode_client = FakeOpenCodeClient()
    code_runner = FakeCodeRunner()
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    # Act & Assert
    with pytest.raises(FeatureNotFoundError) as exc_info:
        await use_case.execute(GenerateFeatureImplementationInput(feature_id=FeatureId("feat_missing")))

    assert "feat_missing" in str(exc_info.value.problem.detail)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_feature_implementation_raises_when_requirements_missing() -> None:
    # Arrange (CA-02: Generación fallida por falta de requisitos)
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    workspace_manager = FakeWorkspaceManager()
    opencode_client = FakeOpenCodeClient()
    code_runner = FakeCodeRunner()
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    feat_id = FeatureId("feat_02_NOTIF")
    prj_id = ProjectId("prj_01")
    feature = Feature(
        id=feat_id,
        number=2,
        title="Notificar vencimientos",
        slug="notificar-vencimientos",
        description="Envía notificaciones",
        project_id=prj_id,
    )
    await feature_repo.save(feature)
    # Requisitos NO generados

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    # Act & Assert
    with pytest.raises(MissingRequirementsError) as exc_info:
        await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id))

    expected_msg = "Esta característica no tiene requisitos EARS generados. Genera los requisitos antes de continuar."
    assert expected_msg in str(exc_info.value)
    assert await workspace_manager.is_locked(prj_id) is False


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_feature_implementation_raises_when_activity_diagram_missing() -> None:
    # Arrange (CA-03: Generación fallida por falta de diagrama)
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    workspace_manager = FakeWorkspaceManager()
    opencode_client = FakeOpenCodeClient()
    code_runner = FakeCodeRunner()
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    feat_id = FeatureId("feat_03_EXP")
    prj_id = ProjectId("prj_01")
    feature = Feature(
        id=feat_id,
        number=3,
        title="Exportar reportes",
        slug="exportar-reportes",
        description="Exporta datos en PDF",
        project_id=prj_id,
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-3.1: Exportar")
    # Diagrama de actividad NO generado

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    # Act & Assert
    with pytest.raises(MissingDiagramError) as exc_info:
        await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id))

    expected_msg = "Esta característica no tiene diagrama de actividad generado. Genera el diagrama antes de continuar."
    assert expected_msg in str(exc_info.value)
    assert await workspace_manager.is_locked(prj_id) is False


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_feature_implementation_retries_on_validation_failure_and_succeeds() -> None:
    # Arrange (Reintento de validación con retroalimentación)
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    workspace_manager = FakeWorkspaceManager()
    opencode_client = FakeOpenCodeClient()
    code_runner = FakeCodeRunner(fail_count_before_pass=1)  # Falla en intento 1, pasa en intento 2
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    feat_id = FeatureId("feat_04_CALC")
    prj_id = ProjectId("prj_01")
    feature = Feature(
        id=feat_id,
        number=4,
        title="Calcular balances",
        slug="calcular-balances",
        description="Calcula balances",
        project_id=prj_id,
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-4.1: Calcular")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_04"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstop\n@enduml",
        )
    )

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    # Act
    output = await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id, max_retries=3))

    # Assert
    assert output.success is True
    assert output.status == FeatureImplementationStatus.IMPLEMENTED
    assert output.implementation is not None
    assert output.implementation.attempt_count == 2
    assert code_runner.runs_count == 2
    assert len(opencode_client.prompts_sent) == 3  # plan + initial build + fix build
    assert await workspace_manager.is_locked(prj_id) is False


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_feature_implementation_exhausts_retries_and_marks_requires_review() -> None:
    # Arrange (CA-04: Generación fallida tras agotar correcciones)
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    workspace_manager = FakeWorkspaceManager()
    opencode_client = FakeOpenCodeClient()
    code_runner = FakeCodeRunner(should_pass=False)  # Siempre falla
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    feat_id = FeatureId("feat_05_FAIL")
    prj_id = ProjectId("prj_01")
    feature = Feature(
        id=feat_id,
        number=5,
        title="Calcular balances complejos",
        slug="calcular-balances-complejos",
        description="Falla en validaciones",
        project_id=prj_id,
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-5.1: Fail")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_05"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstop\n@enduml",
        )
    )

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    # Act
    output = await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id, max_retries=3))

    # Assert
    assert output.success is False
    assert output.status == FeatureImplementationStatus.REQUIRES_REVIEW
    assert output.implementation is not None
    assert output.implementation.status == FeatureImplementationStatus.REQUIRES_REVIEW
    assert output.implementation.attempt_count == 3
    assert code_runner.runs_count == 3
    assert await workspace_manager.is_locked(prj_id) is False


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_feature_implementation_execute_stream_yields_events() -> None:
    # Arrange
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    workspace_manager = FakeWorkspaceManager()
    opencode_client = FakeOpenCodeClient()
    code_runner = FakeCodeRunner(should_pass=True)
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    feat_id = FeatureId("feat_06_STREAM")
    prj_id = ProjectId("prj_01")
    feature = Feature(
        id=feat_id,
        number=6,
        title="Stream test",
        slug="stream-test",
        description="Streaming",
        project_id=prj_id,
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-6.1: Stream")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_06"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstop\n@enduml",
        )
    )

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    # Act
    events: list[OpenCodeEvent] = []
    async for event in use_case.execute_stream(GenerateFeatureImplementationInput(feature_id=feat_id)):
        events.append(event)

    # Assert
    assert len(events) > 0
    event_types = [e.event_type for e in events]
    assert OpenCodeEventType.PLAN_PROGRESS in event_types
    assert OpenCodeEventType.PLAN_COMPLETE in event_types
    assert OpenCodeEventType.BUILD_PROGRESS in event_types
    assert OpenCodeEventType.BUILD_COMPLETE in event_types
    assert OpenCodeEventType.DONE in event_types


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_feature_implementation_always_releases_lock_on_error() -> None:
    # Arrange
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    workspace_manager = FakeWorkspaceManager()

    class CrashingOpenCodeClient(FakeOpenCodeClient):
        async def create_session(self, workspace_dir: str, *, title: str = "") -> OpenCodeSession:
            raise RuntimeError("OpenCode server crashed unexpectedly")

    opencode_client = CrashingOpenCodeClient()
    code_runner = FakeCodeRunner()
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    feat_id = FeatureId("feat_07_CRASH")
    prj_id = ProjectId("prj_01")
    feature = Feature(
        id=feat_id,
        number=7,
        title="Crash test",
        slug="crash-test",
        description="Crash",
        project_id=prj_id,
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-7.1: Crash")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_07"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstop\n@enduml",
        )
    )

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    # Act & Assert
    with pytest.raises(RuntimeError):
        await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id))

    assert await workspace_manager.is_locked(prj_id) is False


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_feature_implementation_closes_session_on_plan_exception() -> None:
    # Arrange
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    workspace_manager = FakeWorkspaceManager()
    opencode_client = ExplodingOpenCodeClient(agent="plan", explode_on_call=1)
    code_runner = FakeCodeRunner(should_pass=True)
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    feat_id = FeatureId("feat_T01_PLAN_CRASH")
    prj_id = ProjectId("prj_01")
    feature = Feature(
        id=feat_id,
        number=1,
        title="Plan crash",
        slug="plan-crash",
        description="Crash en fase plan",
        project_id=prj_id,
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-1.1: Plan crash")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_plan"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstop\n@enduml",
        )
    )

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    # Act & Assert
    with pytest.raises(RuntimeError, match="plan phase"):
        await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id))

    # Assert — la sesión se cierra y el lock se libera aunque la fase Plan explote
    assert len(opencode_client.created_sessions) == 1
    session_id = opencode_client.created_sessions[0].session_id
    assert session_id in opencode_client.closed_sessions
    assert await workspace_manager.is_locked(prj_id) is False


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_feature_implementation_closes_session_on_build_exception() -> None:
    # Arrange
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    workspace_manager = FakeWorkspaceManager()
    opencode_client = ExplodingOpenCodeClient(agent="build", explode_on_call=1)
    code_runner = FakeCodeRunner(should_pass=True)
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    feat_id = FeatureId("feat_T01_BUILD_CRASH")
    prj_id = ProjectId("prj_01")
    feature = Feature(
        id=feat_id,
        number=1,
        title="Build crash",
        slug="build-crash",
        description="Crash en fase build",
        project_id=prj_id,
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-1.1: Build crash")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_build"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstop\n@enduml",
        )
    )

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    # Act & Assert
    with pytest.raises(RuntimeError, match="build phase"):
        await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id))

    # Assert — la sesión se cierra y el lock se libera aunque la fase Build explote
    assert len(opencode_client.created_sessions) == 1
    session_id = opencode_client.created_sessions[0].session_id
    assert session_id in opencode_client.closed_sessions
    assert await workspace_manager.is_locked(prj_id) is False


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_feature_implementation_closes_session_on_fix_exception() -> None:
    # Arrange
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    workspace_manager = FakeWorkspaceManager()
    opencode_client = ExplodingOpenCodeClient(agent="build", explode_on_call=2)
    code_runner = FakeCodeRunner(should_pass=False)  # Valida falla -> dispara fix
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    feat_id = FeatureId("feat_T01_FIX_CRASH")
    prj_id = ProjectId("prj_01")
    feature = Feature(
        id=feat_id,
        number=1,
        title="Fix crash",
        slug="fix-crash",
        description="Crash en corrección",
        project_id=prj_id,
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-1.1: Fix crash")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_fix"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstop\n@enduml",
        )
    )

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    # Act & Assert
    with pytest.raises(RuntimeError, match="build phase"):
        await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id, max_retries=3))

    # Assert — la sesión se cierra y el lock se libera aunque la corrección explote
    assert len(opencode_client.created_sessions) == 1
    session_id = opencode_client.created_sessions[0].session_id
    assert session_id in opencode_client.closed_sessions
    assert await workspace_manager.is_locked(prj_id) is False


@pytest.mark.asyncio
@pytest.mark.unit
async def test_retry_emits_retry_events() -> None:
    """T17: Verificar que se emitan eventos RETRY con los errores parseados en cada reintento."""
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    workspace_manager = FakeWorkspaceManager()
    opencode_client = FakeOpenCodeClient()
    code_runner = FakeCodeRunner(fail_count_before_pass=2)  # Falla 2 veces, pasa en el 3ro
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    feat_id = FeatureId("feat_T17_RETRY_EVENTS")
    prj_id = ProjectId("prj_01")
    feature = Feature(
        id=feat_id,
        number=17,
        title="Retry events test",
        slug="retry-events-test",
        description="Test retry events",
        project_id=prj_id,
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-17.1: Retry")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_17"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstop\n@enduml",
        )
    )

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    output = await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id, max_retries=3))

    assert output.success is True
    retry_events = [e for e in output.events if e.event_type == OpenCodeEventType.RETRY]
    assert len(retry_events) == 2
    assert retry_events[0].data["attempt"] == 1
    assert retry_events[1].data["attempt"] == 2
    assert "error_summary" in retry_events[0].data


@pytest.mark.asyncio
@pytest.mark.unit
async def test_exhausted_retries_calls_rollback() -> None:
    """T17: Verificar que al agotar reintentos se invoque rollback_workspace."""
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    workspace_manager = FakeWorkspaceManager()
    opencode_client = FakeOpenCodeClient()
    code_runner = FakeCodeRunner(should_pass=False)
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    feat_id = FeatureId("feat_T17_ROLLBACK")
    prj_id = ProjectId("prj_01")
    feature = Feature(
        id=feat_id,
        number=18,
        title="Rollback test",
        slug="rollback-test",
        description="Test rollback",
        project_id=prj_id,
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-18.1: Rollback")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_18"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstop\n@enduml",
        )
    )

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    output = await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id, max_retries=3))

    assert output.success is False
    assert output.status == FeatureImplementationStatus.REQUIRES_REVIEW
    assert str(prj_id) in workspace_manager.rollback_called_for


@pytest.mark.asyncio
@pytest.mark.unit
async def test_retry_history_accumulated() -> None:
    """T17: Verificar que el historial de errores por intento se acumule correctamente."""
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    workspace_manager = FakeWorkspaceManager()
    opencode_client = FakeOpenCodeClient()
    code_runner = FakeCodeRunner(should_pass=False)
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    feat_id = FeatureId("feat_T17_HISTORY")
    prj_id = ProjectId("prj_01")
    feature = Feature(
        id=feat_id,
        number=19,
        title="History test",
        slug="history-test",
        description="Test history",
        project_id=prj_id,
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-19.1: History")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_19"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstop\n@enduml",
        )
    )

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    output = await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id, max_retries=3))

    assert output.success is False
    assert len(output.retry_history) == 3
    assert output.implementation is not None
    assert len(output.implementation.retry_history) == 3
    for errors in output.retry_history:
        assert len(errors) > 0
    assert "Intento 1" in (output.error_message or "")
    assert len(trace_repo.edges) == 0


@pytest.mark.asyncio
@pytest.mark.unit
async def test_build_prompt_incluye_requisitos() -> None:
    # Arrange
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    workspace_manager = FakeWorkspaceManager()
    opencode_client = FakeOpenCodeClient()
    code_runner = FakeCodeRunner(should_pass=True)
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    feat_id = FeatureId("feat_01HT_GASTOS")
    prj_id = ProjectId("prj_01HT_APP")
    feature = Feature(
        id=feat_id,
        number=1,
        title="Registrar gastos",
        slug="registrar-gastos",
        description="Permite registrar transacciones de gastos",
        project_id=prj_id,
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-1.1: El sistema registrará los gastos")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_01"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstart\n:Registrar gasto;\nstop\n@enduml",
        )
    )

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    # Act
    await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id))

    # Assert — el build prompt contiene el plan, descripción, requisitos EARS y diagrama
    build_prompts = [prompt for (_, prompt, agent) in opencode_client.prompts_sent if agent == "build"]
    assert len(build_prompts) == 1
    build_prompt = build_prompts[0]
    assert "Plan aprobado" in build_prompt
    assert "[create] src/app/registrar-gastos/page.tsx" in build_prompt
    assert "[create] tests/registrar-gastos.test.ts" in build_prompt
    assert "# REQ-1.1: El sistema registrará los gastos" in build_prompt
    assert "## Diagrama de Actividad" in build_prompt


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_registers_traceability_post_commit() -> None:
    # Arrange
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    workspace_manager = FakeWorkspaceManager()
    opencode_client = FakeOpenCodeClient()
    code_runner = FakeCodeRunner(should_pass=True)
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    feat_id = FeatureId("feat_01HT_GASTOS")
    prj_id = ProjectId("prj_01HT_APP")
    feature = Feature(
        id=feat_id,
        number=1,
        title="Registrar gastos",
        slug="registrar-gastos",
        description="Permite registrar transacciones de gastos",
        project_id=prj_id,
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-1.1: El sistema registrará los gastos")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_01"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstart\n:Registrar gasto;\nstop\n@enduml",
        )
    )

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    # Act
    output = await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id))

    # Assert
    assert output.success is True
    assert ("feature", str(feat_id), "code_file", "src/app/registrar-gastos/page.tsx", "codegen") in trace_repo.edges
    assert ("feature", str(feat_id), "test_file", "tests/registrar-gastos.test.ts", "codegen") in trace_repo.edges
    assert (
        "requirement",
        f"{feat_id}:REQ-1.1",
        "code_file",
        "src/app/registrar-gastos/page.tsx",
        "codegen",
    ) in trace_repo.edges
    done_events = [e for e in output.events if e.event_type == OpenCodeEventType.DONE]
    assert len(done_events) == 1
    assert done_events[0].data.get("screens_count") is not None
    assert done_events[0].data.get("requirements_count") is not None
    assert done_events[0].data.get("validations_passed") is not None
    assert done_events[0].data.get("validations_total") is not None
    assert "Next.js" in done_events[0].data.get("technologies", [])


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_emits_error_event_si_trazabilidad_falla() -> None:
    # Arrange
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    workspace_manager = FakeWorkspaceManager()
    opencode_client = FakeOpenCodeClient()
    code_runner = FakeCodeRunner(should_pass=True)
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = RaisingTraceabilityRepository()

    feat_id = FeatureId("feat_01HT_GASTOS")
    prj_id = ProjectId("prj_01HT_APP")
    feature = Feature(
        id=feat_id,
        number=1,
        title="Registrar gastos",
        slug="registrar-gastos",
        description="Permite registrar transacciones de gastos",
        project_id=prj_id,
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-1.1: El sistema registrará los gastos")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_01"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstart\n:Registrar gasto;\nstop\n@enduml",
        )
    )

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    # Act
    output = await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id))

    # Assert
    assert output.success is True
    assert output.status == FeatureImplementationStatus.IMPLEMENTED
    warning_events = [
        e
        for e in output.events
        if e.event_type == OpenCodeEventType.BUILD_PROGRESS and e.data.get("stage") == "traceability_warning"
    ]
    assert len(warning_events) == 1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_raises_when_opencode_no_disponible() -> None:
    # Arrange
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    workspace_manager = FakeWorkspaceManager()
    opencode_client = UnhealthyOpenCodeClient()
    code_runner = FakeCodeRunner(should_pass=True)
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    feat_id = FeatureId("feat_01HT_GASTOS")
    prj_id = ProjectId("prj_01HT_APP")
    feature = Feature(
        id=feat_id,
        number=1,
        title="Registrar gastos",
        slug="registrar-gastos",
        description="Permite registrar transacciones de gastos",
        project_id=prj_id,
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-1.1: El sistema registrará los gastos")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_01"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstart\n:Registrar gasto;\nstop\n@enduml",
        )
    )

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    # Act & Assert
    with pytest.raises(OpenCodeUnavailableError, match="no está disponible"):
        await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id))

    # Assert — falla rápido: sin lock ni sesión creada
    assert len(workspace_manager.locked_projects) == 0
    assert len(opencode_client.created_sessions) == 0


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_fails_when_structural_validation_fails() -> None:
    # Arrange
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    workspace_manager = FakeWorkspaceManager()
    # Emite únicamente tests, omitiendo page.tsx y feature slice
    opencode_client = FakeOpenCodeClient(
        generated_files=("tests/registrar-gastos.test.ts", "src/lib/feature-registry.ts")
    )
    code_runner = FakeCodeRunner(should_pass=True)
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    feat_id = FeatureId("feat_01HT_GASTOS")
    prj_id = ProjectId("prj_01HT_APP")
    feature = Feature(
        id=feat_id,
        number=1,
        title="Registrar gastos",
        slug="registrar-gastos",
        description="Permite registrar transacciones de gastos",
        project_id=prj_id,
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-1.1: El sistema registrará los gastos")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_01"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstart\n:Registrar gasto;\nstop\n@enduml",
        )
    )

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    # Act
    output = await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id, max_retries=2))

    # Assert
    assert output.success is False
    assert output.status == FeatureImplementationStatus.REQUIRES_REVIEW
    assert output.validation_result is not None
    assert output.validation_result.all_passed is False
    structure_step = next(s for s in output.validation_result.steps if s.step == ValidationStep.STRUCTURE)
    assert structure_step.success is False
    assert any("page.tsx" in msg for msg in structure_step.error_messages)
    assert any("src/features/registrar-gastos/" in msg for msg in structure_step.error_messages)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_includes_implemented_features_in_context() -> None:
    # Arrange
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    workspace_manager = FakeWorkspaceManager()
    opencode_client = FakeOpenCodeClient()
    code_runner = FakeCodeRunner(should_pass=True)
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    prj_id = ProjectId("prj_01HT_APP")

    # Feature 1 ya implementada previamente
    feat1_id = FeatureId("feat_01HT_AUTH")
    feature1 = Feature(
        id=feat1_id,
        number=1,
        title="Autenticación de usuarios",
        slug="auth",
        description="Login y registro",
        project_id=prj_id,
    )
    await feature_repo.save(feature1)
    await impl_repo.save(
        FeatureImplementation(
            id=ImplementationId("impl_01"),
            project_id=prj_id,
            feature_id=feat1_id,
            status=FeatureImplementationStatus.IMPLEMENTED,
            generated_files=("src/app/auth/page.tsx", "src/features/auth/logic.ts"),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )

    # Feature 2 a generar ahora
    feat2_id = FeatureId("feat_02HT_GASTOS")
    feature2 = Feature(
        id=feat2_id,
        number=2,
        title="Registrar gastos",
        slug="registrar-gastos",
        description="Registro de gastos",
        project_id=prj_id,
    )
    await feature_repo.save(feature2)
    await requirement_repo.save(feat2_id, "# REQ-1.1: El sistema registrará los gastos")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_02"),
            feature_id=feat2_id,
            diagram_syntax="@startuml\nstart\n:Registrar gasto;\nstop\n@enduml",
        )
    )

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    # Act
    output = await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat2_id))

    # Assert
    assert output.success is True
    # Verificar que el prompt contenga la sección de funcionalidades ya implementadas
    plan_prompt = next(prompt for _, prompt, agent in opencode_client.prompts_sent if agent == "plan")
    assert "### Funcionalidades ya implementadas en el proyecto" in plan_prompt
    assert "Autenticación de usuarios" in plan_prompt
    assert "slug: `auth`" in plan_prompt
    assert "src/app/auth/page.tsx" in plan_prompt

    build_prompt = next(prompt for _, prompt, agent in opencode_client.prompts_sent if agent == "build")
    assert "### Funcionalidades ya implementadas en el proyecto" in build_prompt
    assert "Autenticación de usuarios" in build_prompt


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_omits_implemented_features_section_when_none_exist() -> None:
    # Arrange
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    workspace_manager = FakeWorkspaceManager()
    opencode_client = FakeOpenCodeClient()
    code_runner = FakeCodeRunner(should_pass=True)
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    prj_id = ProjectId("prj_01HT_APP")
    feat_id = FeatureId("feat_01HT_GASTOS")
    feature = Feature(
        id=feat_id,
        number=1,
        title="Registrar gastos",
        slug="registrar-gastos",
        description="Permite registrar transacciones de gastos",
        project_id=prj_id,
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-1.1: El sistema registrará los gastos")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_01"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstart\n:Registrar gasto;\nstop\n@enduml",
        )
    )

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    # Act
    output = await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id))

    # Assert
    assert output.success is True
    plan_prompt = next(prompt for _, prompt, agent in opencode_client.prompts_sent if agent == "plan")
    assert "### Funcionalidades ya implementadas en el proyecto" not in plan_prompt


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_includes_ears_and_diagram_in_build_prompt() -> None:
    # Arrange
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    workspace_manager = FakeWorkspaceManager()
    opencode_client = FakeOpenCodeClient()
    code_runner = FakeCodeRunner(should_pass=True)
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    prj_id = ProjectId("prj_01HT_APP")
    feat_id = FeatureId("feat_01HT_GASTOS")
    feature = Feature(
        id=feat_id,
        number=1,
        title="Registrar gastos",
        slug="registrar-gastos",
        description="Permite registrar transacciones de gastos",
        project_id=prj_id,
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-1.1: El sistema registrará el monto del gasto")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_01"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstart\n:Ingresar monto;\nstop\n@enduml",
        )
    )

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    # Act
    output = await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id))

    # Assert
    assert output.success is True
    build_prompt = next(prompt for _, prompt, agent in opencode_client.prompts_sent if agent == "build")
    assert "## Descripción\nPermite registrar transacciones de gastos" in build_prompt
    assert "## Requisitos EARS\n# REQ-1.1: El sistema registrará el monto del gasto" in build_prompt
    assert "## Diagrama de Actividad\n@startuml" in build_prompt
    assert "## Plan aprobado" in build_prompt


@pytest.mark.asyncio
@pytest.mark.unit
async def test_plan_and_build_prompts_include_drizzle_database_directives() -> None:
    # Arrange
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    workspace_manager = FakeWorkspaceManager()
    opencode_client = FakeOpenCodeClient()
    code_runner = FakeCodeRunner(should_pass=True)
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    feat_id = FeatureId("feat_01HT_GASTOS")
    prj_id = ProjectId("prj_01HT_APP")
    feature = Feature(
        id=feat_id,
        number=1,
        title="Registrar gastos",
        slug="registrar-gastos",
        description="Permite registrar transacciones de gastos",
        project_id=prj_id,
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-1.1: El sistema registrará el gasto")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_01"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstart\n:Registrar;\nstop\n@enduml",
        )
    )

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    # Act
    output = await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id))

    # Assert
    assert output.success is True
    plan_prompt = next(prompt for _, prompt, agent in opencode_client.prompts_sent if agent == "plan")
    assert "src/db/schema.ts" in plan_prompt
    assert "kosmo-drizzle" in plan_prompt

    build_prompt = next(prompt for _, prompt, agent in opencode_client.prompts_sent if agent == "build")
    assert "src/db/schema.ts" in build_prompt
    assert "drizzle-orm/sqlite-core" in build_prompt
    assert "src/db/index.ts" in build_prompt


@pytest.mark.unit
def test_normalize_generated_file_path_relative_and_absolute() -> None:
    # Arrange
    ws_dir = "/tmp/workspace/project_123"

    # Act & Assert
    assert _normalize_generated_file_path("src/app/page.tsx", ws_dir) == "src/app/page.tsx"
    assert _normalize_generated_file_path("./src/features/logic.ts", ws_dir) == "src/features/logic.ts"
    assert _normalize_generated_file_path("src\\components\\Button.tsx", ws_dir) == "src/components/Button.tsx"
    assert _normalize_generated_file_path("../../etc/passwd", ws_dir) is None
    assert _normalize_generated_file_path("", ws_dir) is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_feature_filters_unsafe_and_normalizes_generated_file_paths() -> None:
    # Arrange
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    workspace_manager = FakeWorkspaceManager()

    class MaliciousPathsOpenCodeClient(FakeOpenCodeClient):
        async def send_prompt(
            self,
            session_id: str,
            prompt: str,
            *,
            agent: str = "plan",
        ) -> AsyncIterator[OpenCodeEvent]:
            if agent == "plan":
                yield OpenCodeEvent(
                    event_type=OpenCodeEventType.PLAN_COMPLETE,
                    session_id=session_id,
                    data={"operations": [{"path": "src/features/gastos-seguros/logic.ts", "action": "create"}]},
                )
            elif agent == "build":
                yield OpenCodeEvent(
                    event_type=OpenCodeEventType.FILE_EDIT,
                    session_id=session_id,
                    data={"path": "./src/app/gastos-seguros/page.tsx", "content": "export default function() {}"},
                )
                yield OpenCodeEvent(
                    event_type=OpenCodeEventType.FILE_EDIT,
                    session_id=session_id,
                    data={"path": "src/lib/feature-registry.ts", "content": "export const features = [];"},
                )
                yield OpenCodeEvent(
                    event_type=OpenCodeEventType.FILE_EDIT,
                    session_id=session_id,
                    data={"path": "../../outside.txt", "content": "malicious"},
                )
                yield OpenCodeEvent(
                    event_type=OpenCodeEventType.BUILD_COMPLETE,
                    session_id=session_id,
                    data={"files": ["src\\features\\gastos-seguros\\manifest.ts", "../escaped.ts"]},
                )

    opencode_client = MaliciousPathsOpenCodeClient()
    code_runner = FakeCodeRunner(should_pass=True)
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    feat_id = FeatureId("feat_01HT_SAFE")
    prj_id = ProjectId("prj_01HT_SAFE")
    feature = Feature(
        id=feat_id,
        number=1,
        title="Gastos seguros",
        slug="gastos-seguros",
        description="Feature segura",
        project_id=prj_id,
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-1.1: Requisito")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_safe"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstart\nstop\n@enduml",
        )
    )

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    # Act
    output = await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id))

    # Assert
    assert output.success is True
    assert "src/app/gastos-seguros/page.tsx" in output.generated_files
    assert "src/features/gastos-seguros/manifest.ts" in output.generated_files
    assert "src/lib/feature-registry.ts" in output.generated_files
    assert "../../outside.txt" not in output.generated_files
    assert "../escaped.ts" not in output.generated_files


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_handles_unexpected_exception_marks_failed_and_releases_lock() -> None:
    # Arrange
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    workspace_manager = FakeWorkspaceManager()

    class CrashingOpenCodeClient(FakeOpenCodeClient):
        async def send_prompt(
            self,
            session_id: str,
            prompt: str,
            *,
            agent: str = "plan",
        ) -> AsyncIterator[OpenCodeEvent]:
            raise RuntimeError("Fatal unhandled crash inside generator")
            yield  # unreachable

    opencode_client = CrashingOpenCodeClient()
    code_runner = FakeCodeRunner(should_pass=True)
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    feat_id = FeatureId("feat_01HT_CRASH")
    prj_id = ProjectId("prj_01HT_CRASH")
    feature = Feature(
        id=feat_id,
        number=1,
        title="Gastos crash",
        slug="gastos-crash",
        description="Feature crash",
        project_id=prj_id,
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-1.1: Requisito")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_crash"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstart\nstop\n@enduml",
        )
    )

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    # Act & Assert
    with pytest.raises(RuntimeError, match="Fatal unhandled crash inside generator"):
        await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id))

    # Assert: Lock liberado, sesión cerrada y estado en base de datos marcado como FAILED
    assert str(prj_id) not in workspace_manager.locked_projects
    saved_impl = await impl_repo.by_feature_id(feat_id)
    assert saved_impl is not None
    assert saved_impl.status == FeatureImplementationStatus.FAILED
    assert len(opencode_client.closed_sessions) >= 1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_uses_canonical_slice_operations_when_plan_agent_returns_no_operations() -> None:
    # Arrange
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    workspace_manager = FakeWorkspaceManager()

    class EmptyPlanOpenCodeClient(FakeOpenCodeClient):
        async def send_prompt(
            self,
            session_id: str,
            prompt: str,
            *,
            agent: str = "plan",
        ) -> AsyncIterator[OpenCodeEvent]:
            if agent == "plan":
                yield OpenCodeEvent(
                    event_type=OpenCodeEventType.PLAN_COMPLETE,
                    session_id=session_id,
                    data={"operations": []},  # Empty operations -> triggers fallback
                )
            elif agent == "build":
                yield OpenCodeEvent(
                    event_type=OpenCodeEventType.BUILD_COMPLETE,
                    session_id=session_id,
                    data={
                        "files": [
                            "src/features/inventario/logic.ts",
                            "src/features/inventario/manifest.ts",
                            "src/app/inventario/page.tsx",
                            "src/lib/feature-registry.ts",
                            "tests/inventario.test.ts",
                        ]
                    },
                )

    opencode_client = EmptyPlanOpenCodeClient()
    code_runner = FakeCodeRunner(should_pass=True)
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    feat_id = FeatureId("feat_01HT_FALLBACK")
    prj_id = ProjectId("prj_01HT_FALLBACK")
    feature = Feature(
        id=feat_id,
        number=1,
        title="Inventario",
        slug="inventario",
        description="Feature inventario",
        project_id=prj_id,
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-1.1: Requisito")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_fallback"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstart\nstop\n@enduml",
        )
    )

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    # Act
    output = await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id))

    # Assert
    assert output.success is True
    assert output.implementation is not None
    assert output.implementation.plan is not None

    paths = [op.path for op in output.implementation.plan.operations]
    assert "src/features/inventario/logic.ts" in paths
    assert "src/features/inventario/manifest.ts" in paths
    assert "src/app/inventario/page.tsx" in paths
    assert "src/lib/feature-registry.ts" in paths
    assert "tests/inventario.test.ts" in paths


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_injects_existing_db_schema_into_prompts_when_present(
    tmp_path: Path,
) -> None:
    # Arrange
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    workspace_manager = FakeWorkspaceManager(workspace_dir=str(tmp_path))
    opencode_client = FakeOpenCodeClient()
    code_runner = FakeCodeRunner(should_pass=True)
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    feat_id = FeatureId("feat_01HT_DBSCHEMA")
    prj_id = ProjectId("prj_01HT_DBSCHEMA")

    # Crear el workspace con src/db/schema.ts previo
    db_dir = tmp_path / "src" / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    schema_file = db_dir / "schema.ts"
    schema_file.write_text("export const products = sqliteTable('products', { id: text('id').primaryKey() });\n")

    feature = Feature(
        id=feat_id,
        number=1,
        title="Gestión de Categorías",
        slug="categorias",
        description="Categorías de productos",
        project_id=prj_id,
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-1.1: Categorías")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_schema"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstart\nstop\n@enduml",
        )
    )

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    # Act
    await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id))

    # Assert
    assert len(opencode_client.prompts_sent) >= 2
    plan_prompt = opencode_client.prompts_sent[0][1]
    build_prompt = opencode_client.prompts_sent[1][1]

    assert "### Esquema de base de datos actual (`src/db/schema.ts`)" in plan_prompt
    assert "export const products = sqliteTable('products'" in plan_prompt
    assert "sin eliminar las features previas" in plan_prompt
    assert "### Esquema de base de datos actual (`src/db/schema.ts`)" in build_prompt
    assert "export const products = sqliteTable('products'" in build_prompt
    assert "sin borrar ni sobrescribir las entradas de features anteriores" in build_prompt


@pytest.mark.asyncio
@pytest.mark.unit
async def test_auto_sync_github_ejecuta_push_tras_commit_exitoso(tmp_path: Path) -> None:
    # Arrange
    workspace_dir = tmp_path / "prj_github_test"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    page_file = workspace_dir / "src" / "app" / "iniciar-sesion" / "page.tsx"
    page_file.parent.mkdir(parents=True, exist_ok=True)
    page_file.write_text("export default function Page() { return <div>Login</div>; }", encoding="utf-8")

    slice_file = workspace_dir / "src" / "features" / "iniciar-sesion" / "logic.ts"
    slice_file.parent.mkdir(parents=True, exist_ok=True)
    slice_file.write_text("export function login() { return true; }", encoding="utf-8")

    registry_file = workspace_dir / "src" / "lib" / "feature-registry.ts"
    registry_file.parent.mkdir(parents=True, exist_ok=True)
    registry_file.write_text("export const features = [{ slug: 'iniciar-sesion' }];", encoding="utf-8")

    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()
    project_repo = InMemoryProjectRepository()
    workspace_manager = FakeWorkspaceManager(workspace_dir=str(workspace_dir))
    opencode_client = FakeOpenCodeClient(
        generated_files=(
            "src/app/iniciar-sesion/page.tsx",
            "src/features/iniciar-sesion/logic.ts",
            "src/lib/feature-registry.ts",
        )
    )
    code_runner = FakeCodeRunner(should_pass=True)

    proj_id = ProjectId("prj_gh_1")
    owner_id = UserId("usr_gh_1")
    await project_repo.save(
        Project(
            id=proj_id,
            name="Test GH",
            slug="test-gh",
            description="",
            owner_id=owner_id,
        )
    )

    feat_id = FeatureId("feat_gh_1")
    await feature_repo.save(
        Feature(
            id=feat_id,
            project_id=proj_id,
            number=1,
            title="Iniciar sesión",
            slug="iniciar-sesion",
            description="Login feature",
        )
    )
    await requirement_repo.save(feat_id, "# REQ-1")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_gh"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstart\nstop\n@enduml",
        )
    )

    mock_sync_use_case = AsyncMock()
    mock_sync_use_case.execute.return_value = MagicMock(
        repo_url="https://github.com/user/test-gh",
        last_commit_hash="abc123456",
    )

    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
        project_repo=project_repo,
        sync_github_repository=mock_sync_use_case,
    )

    # Act
    output = await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id))

    # Assert
    assert output.success is True
    assert mock_sync_use_case.execute.called
    call_args = mock_sync_use_case.execute.call_args
    assert call_args[0][0].project_id == proj_id
    assert call_args[0][1] == owner_id


@pytest.mark.asyncio
@pytest.mark.unit
async def test_build_timeout_recovers_when_workspace_has_valid_feature_structure(
    tmp_path: Path,
) -> None:
    # Arrange workspace with valid structure generated on disk before timeout
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    feat_id = FeatureId("feat_rec_1")
    prj_id = ProjectId("prj_rec_1")
    feature = Feature(
        id=feat_id,
        project_id=prj_id,
        number=1,
        title="Valid Timeout Recovery",
        slug="valid-recovery",
        description="Recovery test",
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-1.1: Test recovery")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_rec_1"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstart\nstop\n@enduml",
        )
    )

    # Prepare files in workspace tmp_path
    page_dir = tmp_path / "src" / "app" / "valid-recovery"
    page_dir.mkdir(parents=True)
    (page_dir / "page.tsx").write_text("export default function Page() { return null; }")

    slice_dir = tmp_path / "src" / "features" / "valid-recovery"
    slice_dir.mkdir(parents=True)
    (slice_dir / "index.ts").write_text("export const ok = true;")

    lib_dir = tmp_path / "src" / "lib"
    lib_dir.mkdir(parents=True)
    (lib_dir / "feature-registry.ts").write_text("export const features = ['valid-recovery'];")

    workspace_manager = FakeWorkspaceManager(workspace_dir=str(tmp_path))
    code_runner = FakeCodeRunner(should_pass=True)

    # Client that succeeds on plan, but times out on build
    class TimeoutOnBuildClient(FakeOpenCodeClient):
        async def send_prompt(
            self,
            session_id: str,
            prompt: str,
            *,
            agent: str = "plan",
        ) -> AsyncIterator[OpenCodeEvent]:
            if agent == "plan":
                async for ev in super().send_prompt(session_id, prompt, agent=agent):
                    yield ev
            elif agent == "build":
                # Simular timeout de OpenCode en fase build
                yield OpenCodeEvent(
                    event_type=OpenCodeEventType.ERROR,
                    session_id=session_id,
                    data={
                        "error": "Tiempo de espera agotado al comunicar con OpenCode (tiempo límite: 300s)",
                        "timeout": True,
                    },
                )

    opencode_client = TimeoutOnBuildClient()
    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    output = await use_case.execute(
        GenerateFeatureImplementationInput(feature_id=feat_id),
    )

    # Assert: recovered and completed successfully
    assert output.success is True
    assert output.status == FeatureImplementationStatus.IMPLEMENTED
    # Verified that progress event indicating recovery was emitted
    recovery_events = [e for e in output.events if "detectó código generado en disco" in str(e.data.get("delta", ""))]
    assert len(recovery_events) == 1
    # Files collected accurately from disk
    assert "src/app/valid-recovery/page.tsx" in output.generated_files


@pytest.mark.asyncio
@pytest.mark.unit
async def test_build_timeout_rolls_back_when_workspace_structure_is_invalid(
    tmp_path: Path,
) -> None:
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    feat_id = FeatureId("feat_rec_2")
    prj_id = ProjectId("prj_rec_2")
    feature = Feature(
        id=feat_id,
        project_id=prj_id,
        number=1,
        title="Invalid Timeout Rollback",
        slug="invalid-recovery",
        description="Rollback test",
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-1.1: Test rollback")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_rec_2"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstart\nstop\n@enduml",
        )
    )

    # Empty workspace - no files generated
    workspace_manager = FakeWorkspaceManager(workspace_dir=str(tmp_path))
    code_runner = FakeCodeRunner(should_pass=True)

    class TimeoutOnBuildClient(FakeOpenCodeClient):
        async def send_prompt(
            self,
            session_id: str,
            prompt: str,
            *,
            agent: str = "plan",
        ) -> AsyncIterator[OpenCodeEvent]:
            if agent == "plan":
                async for ev in super().send_prompt(session_id, prompt, agent=agent):
                    yield ev
            elif agent == "build":
                yield OpenCodeEvent(
                    event_type=OpenCodeEventType.ERROR,
                    session_id=session_id,
                    data={
                        "error": "Tiempo de espera agotado al comunicar con OpenCode (tiempo límite: 300s)",
                        "timeout": True,
                    },
                )

    opencode_client = TimeoutOnBuildClient()
    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    with pytest.raises(OpenCodeGenerationError, match="Tiempo de espera agotado"):
        await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id))

    # Assert rollback was called
    assert str(prj_id) in workspace_manager.rollback_called_for


@pytest.mark.asyncio
@pytest.mark.unit
async def test_fix_prompt_filters_opencode_error_event_without_aborting_retry(
    tmp_path: Path,
) -> None:
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    activity_diagram_repo = InMemoryActivityDiagramRepository()
    impl_repo = FakeFeatureImplementationRepository()
    trace_repo = InMemoryTraceabilityRepository()

    feat_id = FeatureId("feat_fix_flt")
    prj_id = ProjectId("prj_fix_flt")
    feature = Feature(
        id=feat_id,
        project_id=prj_id,
        number=1,
        title="Filter Error in Fix",
        slug="filter-fix",
        description="Filter test",
    )
    await feature_repo.save(feature)
    await requirement_repo.save(feat_id, "# REQ-1.1: Test fix error filter")
    await activity_diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("diag_fix_flt"),
            feature_id=feat_id,
            diagram_syntax="@startuml\nstart\nstop\n@enduml",
        )
    )

    page_dir = tmp_path / "src" / "app" / "filter-fix"
    page_dir.mkdir(parents=True)
    (page_dir / "page.tsx").write_text("export default function Page() { return null; }")

    slice_dir = tmp_path / "src" / "features" / "filter-fix"
    slice_dir.mkdir(parents=True)
    (slice_dir / "index.ts").write_text("export const ok = true;")

    lib_dir = tmp_path / "src" / "lib"
    lib_dir.mkdir(parents=True)
    (lib_dir / "feature-registry.ts").write_text("export const features = ['filter-fix'];")

    workspace_manager = FakeWorkspaceManager(workspace_dir=str(tmp_path))

    code_runner = FakeCodeRunner(should_pass=True, fail_count_before_pass=1)

    class ErrorOnFixPromptClient(FakeOpenCodeClient):
        async def send_prompt(
            self,
            session_id: str,
            prompt: str,
            *,
            agent: str = "plan",
        ) -> AsyncIterator[OpenCodeEvent]:
            if "Directivas de corrección" in prompt:
                # Emitir error transitorio durante fix
                yield OpenCodeEvent(
                    event_type=OpenCodeEventType.ERROR,
                    session_id=session_id,
                    data={"error": "Transitorio", "timeout": True},
                )
            else:
                async for ev in super().send_prompt(session_id, prompt, agent=agent):
                    yield ev

    opencode_client = ErrorOnFixPromptClient()
    use_case = GenerateFeatureImplementationUseCase(
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        activity_diagram_repo=activity_diagram_repo,
        workspace_manager=workspace_manager,
        opencode_client=opencode_client,
        code_runner=code_runner,
        implementation_repo=impl_repo,
        traceability_repo=trace_repo,
    )

    output = await use_case.execute(
        GenerateFeatureImplementationInput(feature_id=feat_id, max_retries=2),
    )

    # Assert: Second validation passed, transient error was not emitted as fatal error
    assert output.success is True
    error_events = [e for e in output.events if e.event_type == OpenCodeEventType.ERROR]
    assert len(error_events) == 0


class _FakeTestFsReader(FileSystemReader):
    def __init__(self, files: dict[str, str] | None = None) -> None:
        self.files = files or {}

    def list_files(self, root: str | Path) -> tuple[str, ...]:
        del root
        return tuple(self.files.keys())

    def read_text(self, path: str | Path) -> str | None:
        norm = str(path).replace("\\", "/").strip("./")
        for key, val in self.files.items():
            norm_k = key.replace("\\", "/").strip("./")
            if norm == norm_k or norm.endswith(f"/{norm_k}"):
                return val
        return None


@pytest.mark.unit
def test_collect_workspace_feature_files_with_fs_reader() -> None:
    fake_fs = _FakeTestFsReader(
        {
            "src/features/user-profile/components/Profile.tsx": "...",
            "src/app/user-profile/page.tsx": "...",
            "src/lib/feature-registry.ts": "...",
            "src/lib/site.ts": "...",
            "src/db/schema.ts": "...",
            "src/features/other-feature/other.ts": "...",
            "src/app/other-feature/page.tsx": "...",
        }
    )

    collected = _collect_workspace_feature_files(
        workspace_dir="/virtual/dir",
        feature_slug="user-profile",
        fs_reader=fake_fs,
    )

    assert "src/features/user-profile/components/Profile.tsx" in collected
    assert "src/app/user-profile/page.tsx" in collected
    assert "src/lib/feature-registry.ts" in collected
    assert "src/lib/site.ts" in collected
    assert "src/db/schema.ts" in collected
    assert "src/features/other-feature/other.ts" not in collected
    assert "src/app/other-feature/page.tsx" not in collected


@pytest.mark.unit
def test_get_existing_db_schema_context_with_fs_reader() -> None:
    fake_fs = _FakeTestFsReader(
        {
            "src/db/schema.ts": "export const users = sqliteTable('users', {});",
        }
    )

    ctx = _get_existing_db_schema_context("/virtual/dir", fake_fs)
    assert "export const users = sqliteTable" in ctx
    assert "### Esquema de base de datos actual" in ctx

    # When file does not exist
    empty_fs = _FakeTestFsReader({})
    assert _get_existing_db_schema_context("/virtual/dir", empty_fs) == ""
    assert _get_existing_db_schema_context(None, fake_fs) == ""


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_feature_implementation_records_telemetry_metrics() -> None:
    from kosmo.contracts.telemetry import set_telemetry_provider
    from tests.unit.test_telemetry import FakeTelemetryProvider

    fake_telemetry = FakeTelemetryProvider()
    set_telemetry_provider(fake_telemetry)

    try:
        feature_repo = InMemoryFeatureRepository()
        requirement_repo = InMemoryRequirementRepository()
        activity_diagram_repo = InMemoryActivityDiagramRepository()
        workspace_manager = FakeWorkspaceManager()
        opencode_client = FakeOpenCodeClient()
        code_runner = FakeCodeRunner(should_pass=True)
        impl_repo = FakeFeatureImplementationRepository()
        trace_repo = InMemoryTraceabilityRepository()

        feat_id = FeatureId("feat_telemetry")
        prj_id = ProjectId("prj_telemetry")
        feature = Feature(
            id=feat_id,
            number=1,
            title="Telemetría Feature",
            slug="telemetria-feature",
            description="Test telemetría",
            project_id=prj_id,
        )
        await feature_repo.save(feature)
        await requirement_repo.save(feat_id, "# REQ-1.1: Test")
        await activity_diagram_repo.save(
            DiagramaActividad(
                id=ActivityDiagramId("diag_tel"),
                feature_id=feat_id,
                diagram_syntax="@startuml\nstart\n:accion;\nstop\n@enduml",
            )
        )

        use_case = GenerateFeatureImplementationUseCase(
            feature_repo=feature_repo,
            requirement_repo=requirement_repo,
            activity_diagram_repo=activity_diagram_repo,
            workspace_manager=workspace_manager,
            opencode_client=opencode_client,
            code_runner=code_runner,
            implementation_repo=impl_repo,
            traceability_repo=trace_repo,
        )

        output = await use_case.execute(GenerateFeatureImplementationInput(feature_id=feat_id))
        assert output.success is True

        phases = [d[0] for d in fake_telemetry.codegen_durations]
        assert "plan" in phases
        assert "build" in phases
        assert "validate" in phases
        assert "total" in phases

        for _phase, dur, st in fake_telemetry.codegen_durations:
            assert dur >= 0
            assert st == "success"

        assert len(fake_telemetry.codegen_retries) == 1
        assert fake_telemetry.codegen_retries[0] == (1, True)
    finally:
        set_telemetry_provider(None)
