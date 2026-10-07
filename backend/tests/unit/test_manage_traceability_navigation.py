import pytest
from ulid import ULID

from kosmo.application.traceability.manage_traceability_navigation import (
    ManageTraceabilityNavigationUseCase,
    TraceabilityNavigationInput,
)
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.errors import FeatureNotFoundError
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import FeatureId, ProjectId
from tests.unit.fakes import InMemoryFeatureRepository


@pytest.fixture
def feature_repo() -> InMemoryFeatureRepository:
    return InMemoryFeatureRepository()


@pytest.fixture
def use_case(feature_repo: InMemoryFeatureRepository) -> ManageTraceabilityNavigationUseCase:
    return ManageTraceabilityNavigationUseCase(feature_repo=feature_repo)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_manage_traceability_navigation_permitted_at_discovery_level(
    use_case: ManageTraceabilityNavigationUseCase,
) -> None:
    # Arrange
    input_data = TraceabilityNavigationInput(
        entity_id=str(ULID()),
        level=SpecPhase.DESCUBRIMIENTO,
    )

    # Act
    result = await use_case.execute(input_data)

    # Assert
    assert result.permitted is True
    assert result.redirect_message is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_manage_traceability_navigation_permitted_at_features_level(
    use_case: ManageTraceabilityNavigationUseCase,
) -> None:
    # Arrange
    input_data = TraceabilityNavigationInput(
        entity_id=str(ULID()),
        level=SpecPhase.CARACTERISTICAS,
    )

    # Act
    result = await use_case.execute(input_data)

    # Assert
    assert result.permitted is True
    assert result.redirect_message is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_manage_traceability_navigation_redirects_at_requirements_level(
    use_case: ManageTraceabilityNavigationUseCase,
    feature_repo: InMemoryFeatureRepository,
) -> None:
    # Arrange
    project_id = ProjectId(ULID().hex)
    feature = Feature(
        id=FeatureId(ULID().hex),
        project_id=project_id,
        number=1,
        title="Registrar gastos",
        slug="registrar-gastos",
        description="Feature de prueba",
    )
    await feature_repo.save(feature)

    input_data = TraceabilityNavigationInput(
        entity_id=str(feature.id),
        level=SpecPhase.REQUISITOS,
    )

    # Act
    result = await use_case.execute(input_data)

    # Assert
    assert result.permitted is False
    assert result.redirect_message is not None
    assert "Registrar gastos" in result.redirect_message
    assert result.source_entity_name == "Registrar gastos"
    assert result.source_entity_id == str(feature.id)
    assert result.source_level == SpecPhase.CARACTERISTICAS.value


@pytest.mark.asyncio
@pytest.mark.unit
async def test_manage_traceability_navigation_redirects_at_model_level(
    use_case: ManageTraceabilityNavigationUseCase,
    feature_repo: InMemoryFeatureRepository,
) -> None:
    # Arrange
    project_id = ProjectId(ULID().hex)
    feature = Feature(
        id=FeatureId(ULID().hex),
        project_id=project_id,
        number=2,
        title="Calcular balances",
        slug="calcular-balances",
        description="Feature de prueba",
    )
    await feature_repo.save(feature)

    input_data = TraceabilityNavigationInput(
        entity_id=str(feature.id),
        level=SpecPhase.MODELO,
    )

    # Act
    result = await use_case.execute(input_data)

    # Assert
    assert result.permitted is False
    assert result.redirect_message is not None
    assert "Calcular balances" in result.redirect_message
    assert result.source_entity_name == "Calcular balances"
    assert result.source_level == SpecPhase.REQUISITOS.value


@pytest.mark.asyncio
@pytest.mark.unit
async def test_manage_traceability_navigation_raises_when_feature_not_found(
    use_case: ManageTraceabilityNavigationUseCase,
) -> None:
    # Arrange
    missing_id = FeatureId(ULID().hex)
    input_data = TraceabilityNavigationInput(
        entity_id=str(missing_id),
        level=SpecPhase.REQUISITOS,
    )

    # Act & Assert
    with pytest.raises(FeatureNotFoundError) as exc_info:
        await use_case.execute(input_data)

    assert exc_info.value.problem.status == 404
    assert str(missing_id) in exc_info.value.problem.detail


@pytest.mark.asyncio
@pytest.mark.unit
async def test_manage_traceability_navigation_redirects_at_implementation_level(
    use_case: ManageTraceabilityNavigationUseCase,
    feature_repo: InMemoryFeatureRepository,
) -> None:
    # Arrange
    project_id = ProjectId(ULID().hex)
    feature = Feature(
        id=FeatureId(ULID().hex),
        project_id=project_id,
        number=3,
        title="Exportar reportes",
        slug="exportar-reportes",
        description="Feature de prueba",
    )
    await feature_repo.save(feature)

    input_data = TraceabilityNavigationInput(
        entity_id=str(feature.id),
        level=SpecPhase.IMPLEMENTACION,
    )

    # Act
    result = await use_case.execute(input_data)

    # Assert
    assert result.permitted is False
    assert result.redirect_message is not None
    assert "Exportar reportes" in result.redirect_message
    assert result.source_entity_name == "Exportar reportes"
    assert result.source_level == SpecPhase.MODELO.value


@pytest.mark.asyncio
@pytest.mark.unit
async def test_traceability_navigation_endpoint_blocks_cross_tenant_access() -> None:
    from types import SimpleNamespace

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from kosmo.contracts.auth import Principal
    from kosmo.contracts.sdd.project import Project
    from kosmo.infrastructure.api.dependencies.auth import get_principal
    from kosmo.infrastructure.api.routers.traceability import router as traceability_router
    from tests.unit.fakes import InMemoryProjectRepository

    feature_repo = InMemoryFeatureRepository()
    project_repo = InMemoryProjectRepository()

    owner_proj = Project(
        id=ProjectId("prj_owner"),
        name="Owner Proj",
        slug="owner-proj",
        description="Owner",
        owner_id="usr_owner",
    )
    await project_repo.save(owner_proj)

    feature = Feature(
        id=FeatureId("feat_owner"),
        project_id=owner_proj.id,
        number=1,
        title="Owner Feature",
        slug="owner-feature",
        description="Owner Feature",
    )
    await feature_repo.save(feature)

    app = FastAPI()
    app.include_router(traceability_router)
    app.state.container = SimpleNamespace(
        repos=SimpleNamespace(
            features=feature_repo,
            projects=project_repo,
        )
    )

    # 1. Unauthenticated -> 401
    with TestClient(app) as client:
        res = client.get("/api/v1/traceability/feat_owner/navigation?level=requisitos")
        assert res.status_code == 401

    # 2. Intruder user -> 404 (BOLA prevention)
    app.dependency_overrides[get_principal] = lambda: Principal(subject="usr_intruder")
    with TestClient(app) as client:
        res_intruder = client.get("/api/v1/traceability/feat_owner/navigation?level=requisitos")
        assert res_intruder.status_code == 404

    # 3. Owner user -> 200 (Legacy route)
    app.dependency_overrides[get_principal] = lambda: Principal(subject="usr_owner")
    with TestClient(app) as client:
        res_owner = client.get("/api/v1/traceability/feat_owner/navigation?level=requisitos")
        assert res_owner.status_code == 200
        assert res_owner.headers.get("deprecation") == "true"
        assert res_owner.json()["permitted"] is False
        assert "Owner Feature" in res_owner.json()["source_entity_name"]

    # 4. Canonical nested route: /api/v1/projects/{project_id}/traceability/{entity_id}/navigation
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        # 4.1 Unauthenticated -> 401
        res = client.get(f"/api/v1/projects/{owner_proj.id}/traceability/feat_owner/navigation?level=requisitos")
        assert res.status_code == 401

        # 4.2 Intruder -> 404 (declarative verify_project_owner guard)
        app.dependency_overrides[get_principal] = lambda: Principal(subject="usr_intruder")
        res_intruder = client.get(
            f"/api/v1/projects/{owner_proj.id}/traceability/feat_owner/navigation?level=requisitos"
        )
        assert res_intruder.status_code == 404

        # 4.3 Wrong project for feature -> 404
        app.dependency_overrides[get_principal] = lambda: Principal(subject="usr_owner")
        res_wrong_proj = client.get(
            "/api/v1/projects/proj_different/traceability/feat_owner/navigation?level=requisitos"
        )
        assert res_wrong_proj.status_code == 404

        # 4.4 Authorized owner -> 200
        res_canonical_owner = client.get(
            f"/api/v1/projects/{owner_proj.id}/traceability/feat_owner/navigation?level=requisitos"
        )
        assert res_canonical_owner.status_code == 200
        assert res_canonical_owner.json()["permitted"] is False
        assert "Owner Feature" in res_canonical_owner.json()["source_entity_name"]

    app.dependency_overrides.clear()
