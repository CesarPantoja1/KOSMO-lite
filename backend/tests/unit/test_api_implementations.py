from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kosmo.application.codegen.validate_workspace import (
    ValidateWorkspaceInput,
    ValidateWorkspaceOutput,
    WorkspaceNotFoundError,
)
from kosmo.contracts.auth import Principal
from kosmo.contracts.sdd.codegen import (
    CodeWorkspace,
    FeatureImplementation,
    FeatureImplementationStatus,
    OpenCodeEvent,
    OpenCodeEventType,
    ValidationStep,
    ValidationStepResult,
    WorkspaceStatus,
)
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import FeatureId, ImplementationId, ProjectId, UserId, WorkspaceId
from kosmo.contracts.sdd.project import Project
from kosmo.infrastructure.api.dependencies.auth import get_principal
from kosmo.infrastructure.api.dependencies.container import get_container
from kosmo.infrastructure.api.main import app


@pytest.fixture
def mock_broker():
    from unittest.mock import AsyncMock, MagicMock

    broker = MagicMock()
    broker.is_running.return_value = False
    broker.get_project_id = AsyncMock(return_value="prj_01")
    return broker


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def valid_token_headers():
    # In KOSMO, we might need a real-ish token, or we can mock get_principal.
    # Usually we mock get_principal or the route depends on it.
    # For unit tests, we can just override the dependency:
    from unittest.mock import MagicMock

    from kosmo.contracts.auth import Principal
    from kosmo.infrastructure.api.dependencies.auth import get_principal
    from kosmo.infrastructure.api.dependencies.container import get_container

    app.dependency_overrides[get_principal] = lambda: Principal(subject="usr_123")
    app.dependency_overrides[get_container] = lambda: MagicMock()
    return {"Authorization": "Bearer mock"}


def test_start_implementation(client: TestClient, mock_broker, valid_token_headers: dict[str, str]) -> None:
    # Arrange
    payload = {
        "feature_id": "feat_01ULXGXXXX",
        "max_retries": 3,
    }

    # Act
    app.dependency_overrides[get_container] = lambda: FakeContainer("/workspaces/prj_01", broker=mock_broker)
    response = client.post(
        "/api/v1/implementations",
        json=payload,
        headers=valid_token_headers,
    )

    # Assert
    assert response.status_code == 202
    data = response.json()
    assert "implementation_id" in data
    assert data["implementation_id"] == "impl_feat_01ULXGXXXX"

    # Verificar que se llamó al broker
    mock_broker.start_implementation.assert_called_once()
    kwargs = mock_broker.start_implementation.call_args.kwargs
    assert kwargs["implementation_id"] == "impl_feat_01ULXGXXXX"
    assert kwargs["project_id"] == "prj_01"
    assert kwargs["user_id"] == "usr_123"


def test_stream_implementation_events(client: TestClient, mock_broker, valid_token_headers: dict[str, str]) -> None:
    # Arrange
    async def fake_subscribe(*_args, **_kwargs) -> AsyncGenerator[OpenCodeEvent]:
        yield OpenCodeEvent(event_type=OpenCodeEventType.PLAN_PROGRESS, session_id="sess_123", data={"msg": "hello"})
        yield OpenCodeEvent(event_type=OpenCodeEventType.DONE, session_id="sess_123", data={})

    mock_broker.subscribe.side_effect = fake_subscribe

    # Act
    app.dependency_overrides[get_container] = lambda: FakeContainer("/workspaces/prj_01", broker=mock_broker)
    with client.stream("GET", "/api/v1/implementations/impl_feat_01/events", headers=valid_token_headers) as response:
        assert response.status_code == 200

        content = response.read().decode()

    # Assert
    assert "event: plan_progress" in content
    assert '"event_type": "plan_progress"' in content
    assert '"msg":"hello"' in content.replace(" ", "")
    assert "event: done" in content


class FakeImplementationRepo:
    def __init__(self, generated_files: tuple[str, ...]) -> None:
        self.generated_files = generated_files

    async def by_id(self, implementation_id: ImplementationId) -> FeatureImplementation | None:
        if str(implementation_id) != "impl_feat_01":
            return None
        now = datetime.now(UTC)
        return FeatureImplementation(
            id=ImplementationId("impl_feat_01"),
            feature_id=FeatureId("feat_01"),
            project_id=ProjectId("prj_01"),
            generated_files=self.generated_files,
            created_at=now,
            updated_at=now,
        )

    async def by_feature_id(self, feature_id: FeatureId) -> FeatureImplementation | None:
        if str(feature_id) != "feat_01":
            return None
        now = datetime.now(UTC)
        return FeatureImplementation(
            id=ImplementationId("impl_feat_01"),
            feature_id=FeatureId("feat_01"),
            project_id=ProjectId("prj_01"),
            status=FeatureImplementationStatus.IMPLEMENTED,
            generated_files=self.generated_files,
            created_at=now,
            updated_at=now,
        )


class FakeFeatureRepo:
    async def by_id(self, feature_id: FeatureId) -> Feature:
        return Feature(
            id=feature_id,
            project_id=ProjectId("prj_01"),
            number=1,
            title="Feature de prueba",
            slug="feature-de-prueba",
            description="Descripción de prueba",
        )


class FakeProjectRepo:
    def __init__(self, owner_id: UserId | None = None) -> None:
        self.owner_id = owner_id or UserId("usr_123")

    async def by_id(self, project_id: ProjectId) -> Project | None:
        if str(project_id) != "prj_01":
            return None
        return Project(
            id=project_id,
            name="Proyecto de prueba",
            slug="proyecto-de-prueba",
            description="Descripción de prueba",
            owner_id=self.owner_id,
        )


class FakeWorkspaceRepo:
    def __init__(self, workspace_dir: str) -> None:
        self.workspace_dir = workspace_dir

    async def by_project_id(self, project_id: ProjectId) -> CodeWorkspace | None:
        return CodeWorkspace(
            id=WorkspaceId("ws_01"),
            project_id=ProjectId("prj_01"),
            status=WorkspaceStatus.READY,
            workspace_dir=self.workspace_dir,
        )


class FakeRequirementRepo:
    async def by_feature_id(self, feature_id: FeatureId) -> str:
        return "### Requisitos\n- REQ-01.01: Registrar\n- REQ-01.02: Listar"


class FakeTraceabilityRepo:
    async def get_impact(self, artifact_id: str) -> dict[str, list[dict[str, str]]]:
        return {
            "upstream": [{"type": "requirement", "id": "req_01"}],
            "downstream": [{"type": "code", "id": "src/app/page.tsx"}],
        }

    async def get_impact_batch(self, artifact_ids: list[str]) -> dict[str, dict[str, list[dict[str, str]]]]:
        return {
            aid: {
                "upstream": [{"type": "requirement", "id": "req_01"}],
                "downstream": [{"type": "code", "id": "src/app/page.tsx"}],
            }
            for aid in artifact_ids
        }


class FakeRepos:
    def __init__(self, workspace_dir: str) -> None:
        self.implementations = FakeImplementationRepo(("src/app/page.tsx", "src/features/foo/components/Foo.tsx"))
        self.workspaces = FakeWorkspaceRepo(workspace_dir)
        self.features = FakeFeatureRepo()
        self.projects = FakeProjectRepo()
        self.requirements = FakeRequirementRepo()
        self.traceability = FakeTraceabilityRepo()


class FakeValidateUseCase:
    def __init__(self, output: ValidateWorkspaceOutput) -> None:
        self.output = output
        self.inputs: list[ValidateWorkspaceInput] = []

    async def execute(self, input_data: ValidateWorkspaceInput) -> ValidateWorkspaceOutput:
        self.inputs.append(input_data)
        return self.output


class FakeCodegen:
    def __init__(
        self,
        validate_workspace: FakeValidateUseCase,
        broker: object | None = None,
        repos: FakeRepos | None = None,
    ) -> None:
        from unittest.mock import MagicMock

        from kosmo.application.codegen.get_implementation_record import GetImplementationRecordUseCase

        self.validate_workspace = validate_workspace
        self.generate_feature_implementation = object()
        self.implementation_broker = broker or MagicMock()
        if repos is not None:
            self.get_implementation_record = GetImplementationRecordUseCase(
                implementation_repo=repos.implementations,
                requirement_repo=repos.requirements,
                traceability_repo=repos.traceability,
            )
        else:
            self.get_implementation_record = MagicMock()


class FakeContainer:
    def __init__(
        self,
        workspace_dir: str,
        validate_workspace: FakeValidateUseCase | None = None,
        broker: object | None = None,
    ) -> None:
        self.repos = FakeRepos(workspace_dir)
        if validate_workspace is None:
            validate_workspace = FakeValidateUseCase(_validation_output())
        self.codegen = FakeCodegen(validate_workspace, broker=broker, repos=self.repos)


def _validation_output(all_passed: bool = True) -> ValidateWorkspaceOutput:
    steps = (
        ValidationStepResult(step=ValidationStep.TYPECHECK, success=all_passed, duration_ms=1234),
        ValidationStepResult(step=ValidationStep.LINT, success=all_passed),
    )
    return ValidateWorkspaceOutput(
        all_passed=all_passed,
        steps=steps,
        failed_step=None if all_passed else ValidationStep.TYPECHECK,
        error_summary=() if all_passed else ("Typecheck falló con 1 error",),
        total_duration_ms=1234,
    )


def test_get_implementation_file_content(
    client: TestClient,
    tmp_path: Path,
) -> None:
    # Arrange
    workspace_dir = tmp_path / "workspaces" / "prj_01"
    workspace_dir.mkdir(parents=True)
    (workspace_dir / "src").mkdir()
    (workspace_dir / "src" / "app").mkdir()
    (workspace_dir / "src" / "app" / "page.tsx").write_text(
        "export default function Page() { return null; }",
        encoding="utf-8",
    )
    app.dependency_overrides[get_principal] = lambda: Principal(subject="usr_123")
    app.dependency_overrides[get_container] = lambda: FakeContainer(str(workspace_dir))

    # Act
    response = client.get(
        "/api/v1/implementations/impl_feat_01/files/content",
        params={"path": "src/app/page.tsx"},
        headers={"Authorization": "Bearer mock"},
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["path"] == "src/app/page.tsx"
    assert "export default function Page" in data["content"]


def test_get_implementation_file_content_rechaza_traversal(
    client: TestClient,
    tmp_path: Path,
) -> None:
    # Arrange
    app.dependency_overrides[get_principal] = lambda: Principal(subject="usr_123")
    app.dependency_overrides[get_container] = lambda: FakeContainer(str(tmp_path / "workspaces" / "prj_01"))

    # Act
    response = client.get(
        "/api/v1/implementations/impl_feat_01/files/content",
        params={"path": "../secreto.txt"},
        headers={"Authorization": "Bearer mock"},
    )

    # Assert
    assert response.status_code == 422


def test_get_implementation_file_content_not_found(
    client: TestClient,
    tmp_path: Path,
) -> None:
    # Arrange
    app.dependency_overrides[get_principal] = lambda: Principal(subject="usr_123")
    app.dependency_overrides[get_container] = lambda: FakeContainer(str(tmp_path / "workspaces" / "prj_01"))

    # Act
    response = client.get(
        "/api/v1/implementations/impl_missing/files/content",
        params={"path": "src/app/page.tsx"},
        headers={"Authorization": "Bearer mock"},
    )

    # Assert
    assert response.status_code == 404


def test_validate_implementation_workspace_ok(client: TestClient, tmp_path: Path) -> None:
    # Arrange
    validate_use_case = FakeValidateUseCase(_validation_output())
    app.dependency_overrides[get_principal] = lambda: Principal(subject="usr_123")
    app.dependency_overrides[get_container] = lambda: FakeContainer(
        str(tmp_path / "workspaces" / "prj_01"),
        validate_workspace=validate_use_case,
    )

    # Act
    response = client.post(
        "/api/v1/implementations/impl_feat_01/validate",
        headers={"Authorization": "Bearer mock"},
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["all_passed"] is True
    assert data["total_duration_ms"] == 1234
    assert data["failed_step"] is None
    assert [step["step"] for step in data["steps"]] == ["typecheck", "lint"]
    assert data["steps"][0]["success"] is True
    assert validate_use_case.inputs[0].project_id == ProjectId("prj_01")


def test_validate_implementation_workspace_failed(client: TestClient, tmp_path: Path) -> None:
    # Arrange
    validate_use_case = FakeValidateUseCase(_validation_output(all_passed=False))
    app.dependency_overrides[get_principal] = lambda: Principal(subject="usr_123")
    app.dependency_overrides[get_container] = lambda: FakeContainer(
        str(tmp_path / "workspaces" / "prj_01"),
        validate_workspace=validate_use_case,
    )

    # Act
    response = client.post(
        "/api/v1/implementations/impl_feat_01/validate",
        headers={"Authorization": "Bearer mock"},
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["all_passed"] is False
    assert data["failed_step"] == "typecheck"
    assert data["error_summary"] == ["Typecheck falló con 1 error"]


def test_validate_implementation_workspace_not_found(client: TestClient, tmp_path: Path) -> None:  # Arrange
    app.dependency_overrides[get_principal] = lambda: Principal(subject="usr_123")
    app.dependency_overrides[get_container] = lambda: FakeContainer(str(tmp_path / "workspaces" / "prj_01"))

    # Act
    response = client.post(
        "/api/v1/implementations/impl_missing/validate",
        headers={"Authorization": "Bearer mock"},
    )

    # Assert
    assert response.status_code == 404


def test_validate_implementation_workspace_workspace_missing(client: TestClient, tmp_path: Path) -> None:
    # Arrange
    class RaisingValidateUseCase(FakeValidateUseCase):
        async def execute(self, input_data: ValidateWorkspaceInput) -> ValidateWorkspaceOutput:
            raise WorkspaceNotFoundError("No existe un workspace inicializado para el proyecto 'prj_01'.")

    app.dependency_overrides[get_principal] = lambda: Principal(subject="usr_123")
    app.dependency_overrides[get_container] = lambda: FakeContainer(
        str(tmp_path / "workspaces" / "prj_01"),
        validate_workspace=RaisingValidateUseCase(_validation_output()),
    )

    # Act
    response = client.post(
        "/api/v1/implementations/impl_feat_01/validate",
        headers={"Authorization": "Bearer mock"},
    )

    # Assert
    assert response.status_code == 404
    assert "workspace" in response.json()["detail"]


def test_implementation_file_content_is_hidden_from_another_owner(client: TestClient, tmp_path: Path) -> None:
    app.dependency_overrides[get_principal] = lambda: Principal(subject="usr_intruso")
    app.dependency_overrides[get_container] = lambda: FakeContainer(str(tmp_path / "workspaces" / "prj_01"))

    response = client.get(
        "/api/v1/implementations/impl_feat_01/files/content",
        params={"path": "src/app/page.tsx"},
        headers={"Authorization": "Bearer mock"},
    )

    assert response.status_code == 404


class FakeDeleteFeatureUC:
    def __init__(self, feature: Feature) -> None:
        self.feature = feature

    async def execute(self, project_id: ProjectId, feature_id: FeatureId) -> Feature:
        return self.feature


class FakeConsistencyContainer:
    def __init__(self, feature: Feature) -> None:
        self.delete_feature = FakeDeleteFeatureUC(feature)


class FakeDeleteCodegen:
    def __init__(self, broker: object | None = None) -> None:
        from unittest.mock import MagicMock

        self.delete_feature_code = object()
        self.implementation_broker = broker or MagicMock()


class FakeDeleteContainer:
    def __init__(self, feature: Feature, broker: object | None = None) -> None:
        self.consistency = FakeConsistencyContainer(feature)
        self.codegen = FakeDeleteCodegen(broker=broker)
        self.repos = FakeRepos("")


def test_delete_feature_dispara_eliminacion_de_codigo_en_background(
    client: TestClient,
) -> None:
    from unittest.mock import MagicMock

    # Arrange
    feature = Feature(
        id=FeatureId("feat_del_api"),
        number=1,
        title="Registrar productos",
        slug="registrar-productos",
        description="Permite registrar productos",
        project_id=ProjectId("prj_01"),
    )
    mock_broker = MagicMock()
    app.dependency_overrides[get_principal] = lambda: Principal(subject="usr_123")
    fake_container = FakeDeleteContainer(feature, broker=mock_broker)
    app.dependency_overrides[get_container] = lambda: fake_container  # type: ignore[arg-type]
    app.state.container = fake_container  # type: ignore[attr-defined]

    # Act
    response = client.delete(
        "/api/v1/projects/prj_01/features/feat_del_api",
        headers={"Authorization": "Bearer mock"},
    )

    # Assert — la feature se elimina de la especificación y el cleanup del código se agenda en background
    assert response.status_code == 200
    assert response.json() == {"status": "deleted", "feature_id": "feat_del_api"}
    mock_broker.start_implementation.assert_called_once()
    kwargs = mock_broker.start_implementation.call_args.kwargs
    assert kwargs["implementation_id"] == "impl_feat_del_api"
    assert kwargs["input_data"].feature.id == FeatureId("feat_del_api")
    assert kwargs["input_data"].feature.slug == "registrar-productos"
    assert kwargs["user_id"] == "usr_123"


def test_get_implementation_by_feature_returns_dynamic_metrics(
    client: TestClient,
    tmp_path: Path,
) -> None:
    # Arrange
    app.dependency_overrides[get_principal] = lambda: Principal(subject="usr_123")
    app.dependency_overrides[get_container] = lambda: FakeContainer(str(tmp_path / "workspaces" / "prj_01"))

    # Act
    response = client.get(
        "/api/v1/implementations",
        params={"feature_id": "feat_01"},
        headers={"Authorization": "Bearer mock"},
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["implementation_id"] == "impl_feat_01"
    assert data["feature_id"] == "feat_01"
    assert data["screens_count"] == 2
    assert data["requirements_count"] == 2
    assert data["validations_passed"] == 4
    assert data["validations_total"] == 4
    assert data["traceability_edges_count"] > 0
    assert "Next.js" in data["technologies"]
