from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from kosmo.application.codegen.delete_feature_code import (
    DeleteFeatureCodeInput,
    DeleteFeatureCodeUseCase,
)
from kosmo.contracts.sdd.codegen import (
    CodeWorkspace,
    FeatureImplementation,
    FeatureImplementationRepository,
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
from kosmo.domain.codegen.registry_edit import remove_feature_from_registry


class FakeWorkspaceManager(WorkspaceManagerPort):
    def __init__(self, workspace_dir: str | None = "/workspaces/prj_01") -> None:
        self.workspace_dir = workspace_dir
        self.removed_paths: tuple[str, ...] = ("src/features/mi-feature", "src/app/mi-feature/page.tsx")
        self.removed_calls: list[tuple[str, str]] = []
        self.text_updates: list[tuple[str, str, str]] = []
        self.commit_hashes: list[str] = []
        self.reverted: list[str] = []
        self.acquired_locks: list[ProjectId] = []
        self.released_locks: list[ProjectId] = []

    async def ensure_workspace(self, project_id: ProjectId) -> CodeWorkspace:
        return CodeWorkspace(
            id=WorkspaceId(f"ws_{project_id}"),
            project_id=project_id,
            status=WorkspaceStatus.READY,
            workspace_dir=self.workspace_dir,
        )

    async def get_workspace(self, project_id: ProjectId) -> CodeWorkspace | None:
        if self.workspace_dir is None:
            return None
        return CodeWorkspace(
            id=WorkspaceId(f"ws_{project_id}"),
            project_id=project_id,
            status=WorkspaceStatus.READY,
            workspace_dir=self.workspace_dir,
        )

    async def get_manifest(self, workspace: CodeWorkspace) -> tuple[str, ...]:
        return ()

    async def is_locked(self, project_id: ProjectId) -> bool:
        return False

    async def acquire_lock(self, project_id: ProjectId) -> None:
        self.acquired_locks.append(project_id)

    async def release_lock(self, project_id: ProjectId) -> None:
        self.released_locks.append(project_id)

    async def rollback_workspace(self, project_id: ProjectId) -> None:
        pass

    async def commit_workspace(self, project_id: ProjectId, message: str) -> str | None:
        commit_hash = f"hash_{len(self.commit_hashes)}"
        self.commit_hashes.append(commit_hash)
        return commit_hash

    async def publish_preview(self, project_id: ProjectId) -> None:
        pass

    async def remove_feature_paths(self, project_id: ProjectId, slug: str) -> tuple[str, ...]:
        self.removed_calls.append((str(project_id), slug))
        return self.removed_paths

    async def update_text_file(
        self,
        project_id: ProjectId,
        relative_path: str,
        transform: object,
    ) -> None:
        self.text_updates.append((str(project_id), relative_path, str(transform)))

    async def revert_commit(self, project_id: ProjectId, commit: str) -> None:
        self.reverted.append(commit)


class FakeOpenCodeClient(OpenCodeClientPort):
    def __init__(self, healthy: bool = True) -> None:
        self.healthy = healthy
        self.closed_sessions: set[str] = set()
        self.prompts_sent: list[str] = []

    async def health_check(self) -> bool:
        return self.healthy

    async def create_session(self, workspace_dir: str, *, title: str = "") -> OpenCodeSession:
        return OpenCodeSession(session_id="oc_delete_1", workspace_dir=workspace_dir, title=title)

    async def send_prompt(
        self,
        session_id: str,
        prompt: str,
        *,
        agent: str = "plan",
    ) -> AsyncIterator[OpenCodeEvent]:
        self.prompts_sent.append(prompt)
        yield OpenCodeEvent(
            event_type=OpenCodeEventType.BUILD_PROGRESS,
            session_id=session_id,
            data={"delta": "Corrigiendo referencias..."},
        )

    async def close_session(self, session_id: str) -> None:
        self.closed_sessions.add(session_id)


class FakeCodeRunner:
    def __init__(self, results: list[bool]) -> None:
        self.results = results
        self.runs_count = 0
        self.run_ids: list[str] = []

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
        passed = self.results[min(self.runs_count - 1, len(self.results) - 1)]
        return ValidationRunResult(
            all_passed=passed,
            steps=(ValidationStepResult(step=ValidationStep.TYPECHECK, success=passed),),
        )


class FakeImplementationRepository(FeatureImplementationRepository):
    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def by_feature_id(self, feature_id: FeatureId) -> FeatureImplementation | None:
        return None

    async def by_id(self, implementation_id: ImplementationId) -> FeatureImplementation | None:
        return None

    async def list_by_project(self, project_id: ProjectId) -> list[FeatureImplementation]:
        return []

    async def save(self, implementation: FeatureImplementation) -> FeatureImplementation:
        return implementation

    async def delete(self, feature_id: FeatureId) -> None:
        self.deleted.append(str(feature_id))


def _a_feature() -> Feature:
    return Feature(
        id=FeatureId("feat_01HT_DEL"),
        number=1,
        title="Registrar productos",
        slug="registrar-productos",
        description="Permite registrar productos con su precio",
        project_id=ProjectId("prj_01"),
    )


async def _collect(use_case: DeleteFeatureCodeUseCase, input_data: DeleteFeatureCodeInput) -> list[OpenCodeEvent]:
    events: list[OpenCodeEvent] = []
    async for event in use_case.execute_stream(input_data):
        events.append(event)
    return events


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_feature_code_elimina_archivos_y_valida_con_exito() -> None:
    # Arrange
    workspace_manager = FakeWorkspaceManager()
    opencode_client = FakeOpenCodeClient()
    code_runner = FakeCodeRunner(results=[True])
    impl_repo = FakeImplementationRepository()
    use_case = DeleteFeatureCodeUseCase(
        workspace_manager=workspace_manager,
        code_runner=code_runner,
        opencode_client=opencode_client,
        implementation_repo=impl_repo,
    )
    feature = _a_feature()

    # Act
    events = await _collect(use_case, DeleteFeatureCodeInput(feature=feature))

    # Assert — archivos eliminados, commit, impl borrado, validación OK
    assert workspace_manager.removed_calls == [("prj_01", "registrar-productos")]
    assert len(workspace_manager.commit_hashes) == 1
    assert impl_repo.deleted == ["feat_01HT_DEL"]
    assert code_runner.runs_count == 1
    done_events = [e for e in events if e.event_type == OpenCodeEventType.DONE]
    assert len(done_events) == 1
    assert "funcionando correctamente" in done_events[0].data["delta"]
    # Los deltas visibles no mencionan OpenCode
    deltas = [e.data["delta"] for e in events if isinstance(e.data.get("delta"), str)]
    assert all("opencode" not in text.lower() for text in deltas)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_feature_code_agente_corrige_y_no_recrea_la_feature() -> None:
    # Arrange — primera validación falla, el fix del agente la deja verde
    workspace_manager = FakeWorkspaceManager()
    opencode_client = FakeOpenCodeClient()
    code_runner = FakeCodeRunner(results=[False, True])
    impl_repo = FakeImplementationRepository()
    use_case = DeleteFeatureCodeUseCase(
        workspace_manager=workspace_manager,
        code_runner=code_runner,
        opencode_client=opencode_client,
        implementation_repo=impl_repo,
    )
    feature = _a_feature()

    # Act
    events = await _collect(use_case, DeleteFeatureCodeInput(feature=feature, max_fix_attempts=2))

    # Assert — se usó el agente (sesión creada y cerrada) y el resultado final es DONE
    assert code_runner.runs_count == 2
    assert len(opencode_client.prompts_sent) == 1
    fix_prompt = opencode_client.prompts_sent[0]
    assert "NO recrees" in fix_prompt
    assert "registrar-productos" in fix_prompt
    assert "oc_delete_1" in opencode_client.closed_sessions
    assert workspace_manager.reverted == []
    done_events = [e for e in events if e.event_type == OpenCodeEventType.DONE]
    assert len(done_events) == 1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_feature_code_revierte_si_la_app_sigue_rota() -> None:
    # Arrange — siempre falla; los 2 fixes no logran arreglarla
    workspace_manager = FakeWorkspaceManager()
    opencode_client = FakeOpenCodeClient()
    code_runner = FakeCodeRunner(results=[False, False, False])
    impl_repo = FakeImplementationRepository()
    use_case = DeleteFeatureCodeUseCase(
        workspace_manager=workspace_manager,
        code_runner=code_runner,
        opencode_client=opencode_client,
        implementation_repo=impl_repo,
    )
    feature = _a_feature()

    # Act
    events = await _collect(use_case, DeleteFeatureCodeInput(feature=feature, max_fix_attempts=2))

    # Assert — se revirtió el commit de borrado y el usuario ve un mensaje ciudadano
    assert len(workspace_manager.reverted) == 1
    assert workspace_manager.reverted[0] == workspace_manager.commit_hashes[0]
    error_events = [e for e in events if e.event_type == OpenCodeEventType.ERROR]
    assert len(error_events) == 1
    error_text = error_events[0].data["error"]
    assert "No se pudo eliminar la funcionalidad" in error_text
    assert "volvió a su estado anterior" in error_text
    assert "OpenCode" not in error_text


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_feature_code_revierte_si_opencode_no_disponible() -> None:
    # Arrange — validación falla pero el agente no está disponible
    workspace_manager = FakeWorkspaceManager()
    opencode_client = FakeOpenCodeClient(healthy=False)
    code_runner = FakeCodeRunner(results=[False])
    impl_repo = FakeImplementationRepository()
    use_case = DeleteFeatureCodeUseCase(
        workspace_manager=workspace_manager,
        code_runner=code_runner,
        opencode_client=opencode_client,
        implementation_repo=impl_repo,
    )
    feature = _a_feature()

    # Act
    events = await _collect(use_case, DeleteFeatureCodeInput(feature=feature, max_fix_attempts=2))

    # Assert — sin crear sesión, revert + error ciudadano
    assert len(opencode_client.prompts_sent) == 0
    assert len(workspace_manager.reverted) == 1
    assert any(e.event_type == OpenCodeEventType.ERROR for e in events)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_feature_code_sin_workspace_termina_sin_validar() -> None:
    # Arrange
    workspace_manager = FakeWorkspaceManager(workspace_dir=None)
    opencode_client = FakeOpenCodeClient()
    code_runner = FakeCodeRunner(results=[True])
    impl_repo = FakeImplementationRepository()
    use_case = DeleteFeatureCodeUseCase(
        workspace_manager=workspace_manager,
        code_runner=code_runner,
        opencode_client=opencode_client,
        implementation_repo=impl_repo,
    )
    feature = _a_feature()

    # Act
    events = await _collect(use_case, DeleteFeatureCodeInput(feature=feature))

    # Assert — no hubo borrado ni validación
    assert code_runner.runs_count == 0
    assert workspace_manager.removed_calls == []
    done_events = [e for e in events if e.event_type == OpenCodeEventType.DONE]
    assert len(done_events) == 1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_feature_code_sin_archivos_no_commitea_ni_valida() -> None:
    # Arrange
    workspace_manager = FakeWorkspaceManager()
    workspace_manager.removed_paths = ()
    opencode_client = FakeOpenCodeClient()
    code_runner = FakeCodeRunner(results=[True])
    impl_repo = FakeImplementationRepository()
    use_case = DeleteFeatureCodeUseCase(
        workspace_manager=workspace_manager,
        code_runner=code_runner,
        opencode_client=opencode_client,
        implementation_repo=impl_repo,
    )
    feature = _a_feature()

    # Act
    events = await _collect(use_case, DeleteFeatureCodeInput(feature=feature))

    # Assert — sin commit ni validación; la feature queda eliminada igual
    assert workspace_manager.commit_hashes == []
    assert code_runner.runs_count == 0
    assert impl_repo.deleted == ["feat_01HT_DEL"]
    assert any(e.event_type == OpenCodeEventType.DONE for e in events)


@pytest.mark.unit
def test_registry_transform_usable_desde_el_use_case() -> None:
    # Arrange — el transform aplicado por el use case usa la función pura de dominio
    content = """import { registrarProductos } from "@/features/registrar-productos/manifest";

export const features = [
  registrarProductos,
];
"""

    # Act
    result = remove_feature_from_registry(content, "registrar-productos")

    # Assert
    assert "registrar-productos" not in result
    assert "registrarProductos" not in result


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_feature_code_deltas_ciudadanas_sin_jerga() -> None:
    # Arrange
    workspace_manager = FakeWorkspaceManager()
    opencode_client = FakeOpenCodeClient()
    code_runner = FakeCodeRunner(results=[False, True])
    impl_repo = FakeImplementationRepository()
    use_case = DeleteFeatureCodeUseCase(
        workspace_manager=workspace_manager,
        code_runner=code_runner,
        opencode_client=opencode_client,
        implementation_repo=impl_repo,
    )
    feature = _a_feature()

    # Act
    events = await _collect(use_case, DeleteFeatureCodeInput(feature=feature, max_fix_attempts=2))

    # Assert — los deltas son claros y sin tecnicismos
    deltas = [str(e.data["delta"]) for e in events if isinstance(e.data.get("delta"), str)]
    assert any("Eliminando la funcionalidad" in d for d in deltas)
    assert any("Validando la aplicación" in d for d in deltas)
    assert any("funcione sin la funcionalidad" in d for d in deltas)
    assert any("funcionando correctamente" in d for d in deltas)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_feature_code_adquiere_y_libera_workspace_lock() -> None:
    # Arrange
    workspace_manager = FakeWorkspaceManager()
    opencode_client = FakeOpenCodeClient()
    code_runner = FakeCodeRunner(results=[True])
    impl_repo = FakeImplementationRepository()
    use_case = DeleteFeatureCodeUseCase(
        workspace_manager=workspace_manager,
        code_runner=code_runner,
        opencode_client=opencode_client,
        implementation_repo=impl_repo,
    )
    feature = _a_feature()

    # Act
    await _collect(use_case, DeleteFeatureCodeInput(feature=feature))

    # Assert
    assert workspace_manager.acquired_locks == [feature.project_id]
    assert workspace_manager.released_locks == [feature.project_id]
