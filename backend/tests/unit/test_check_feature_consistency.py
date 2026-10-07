from unittest.mock import AsyncMock

import pytest
from ulid import ULID

from kosmo.application.features.check_feature_consistency import (
    CheckFeatureConsistencyInput,
    CheckFeatureConsistencyUseCase,
)
from kosmo.contracts.ai.consistency import (
    ArtifactAction,
    ConsistencyEvaluationOutput,
    ConsistencyStatus,
)
from kosmo.contracts.sdd.errors import FeatureNotFoundError
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import FeatureId, ProjectId
from tests.unit.fakes import InMemoryFeatureRepository


@pytest.fixture
def feature_repo() -> InMemoryFeatureRepository:
    return InMemoryFeatureRepository()


@pytest.fixture
def consistency_evaluator() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def use_case(
    feature_repo: InMemoryFeatureRepository,
    consistency_evaluator: AsyncMock,
) -> CheckFeatureConsistencyUseCase:
    return CheckFeatureConsistencyUseCase(
        feature_repo=feature_repo,
        consistency_evaluator=consistency_evaluator,
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_check_feature_consistency_consistent(
    use_case: CheckFeatureConsistencyUseCase,
    feature_repo: InMemoryFeatureRepository,
    consistency_evaluator: AsyncMock,
) -> None:
    # Arrange
    project_id = ProjectId(ULID().hex)
    feature = Feature(
        id=FeatureId(ULID().hex),
        project_id=project_id,
        number=1,
        title="Título original",
        slug="titulo-original",
        description="Descripción original",
    )
    await feature_repo.save(feature)
    feature_id = feature.id

    consistency_evaluator.evaluate.return_value = ConsistencyEvaluationOutput(
        report_id="rep_1",
        status=ConsistencyStatus.ANALIZADO_SIN_IMPACTO,
    )

    # Act
    result = await use_case.execute(
        CheckFeatureConsistencyInput(
            project_id=project_id,
            feature_id=feature_id,
            title="Nuevo título",
            description="Nueva descripción",
        )
    )

    # Assert
    assert result.is_consistent is True
    assert result.reason is None
    assert result.conflicting_section is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_check_feature_consistency_inconsistent(
    use_case: CheckFeatureConsistencyUseCase,
    feature_repo: InMemoryFeatureRepository,
    consistency_evaluator: AsyncMock,
) -> None:
    # Arrange
    project_id = ProjectId(ULID().hex)
    feature = Feature(
        id=FeatureId(ULID().hex),
        project_id=project_id,
        number=1,
        title="Título original",
        slug="titulo-original",
        description="Descripción original",
    )
    await feature_repo.save(feature)
    feature_id = feature.id

    consistency_evaluator.evaluate.return_value = ConsistencyEvaluationOutput(
        report_id="rep_1",
        status=ConsistencyStatus.ANALIZADO_CON_IMPACTO,
        actions=[
            ArtifactAction(
                artifact_id="doc_discovery",
                action="update",
                rationale="La descripción contradice la Visión del Descubrimiento.",
                suggested_field="Visión",
                suggested_before="Producto B2C",
                suggested_after="Producto B2B",
            )
        ],
        affected_artifact_ids=["doc_discovery"],
        rationale="Contradicción general",
    )

    # Act
    result = await use_case.execute(
        CheckFeatureConsistencyInput(
            project_id=project_id,
            feature_id=feature_id,
            title="Nuevo título",
            description="Nueva descripción",
        )
    )

    # Assert
    assert result.is_consistent is False
    assert result.reason is not None
    assert "contradice la Visión del Descubrimiento" in result.reason
    assert result.conflicting_section == "Visión"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_check_feature_consistency_feature_not_found(
    use_case: CheckFeatureConsistencyUseCase,
) -> None:
    # Arrange
    project_id = ProjectId(ULID().hex)
    missing_id = FeatureId(ULID().hex)

    # Act & Assert
    with pytest.raises(FeatureNotFoundError) as exc_info:
        await use_case.execute(
            CheckFeatureConsistencyInput(
                project_id=project_id,
                feature_id=missing_id,
                title="Nuevo título",
                description="Nueva descripción",
            )
        )

    assert exc_info.value.problem.status == 404
    assert str(missing_id) in exc_info.value.problem.detail


@pytest.mark.asyncio
@pytest.mark.unit
async def test_check_feature_consistency_endpoint_auth() -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from kosmo.application.features.check_feature_consistency import CheckFeatureConsistencyOutput
    from kosmo.contracts.auth import Principal
    from kosmo.infrastructure.api.dependencies.auth import get_principal, verify_project_owner
    from kosmo.infrastructure.api.routers.features import router as features_router

    mock_uc = AsyncMock()
    mock_uc.execute.return_value = CheckFeatureConsistencyOutput(is_consistent=True)

    app = FastAPI()
    app.include_router(features_router)
    app.state.container = SimpleNamespace(features=SimpleNamespace(check_feature_consistency=mock_uc))

    # 1. Sin autenticacion -> 401
    with TestClient(app) as client:
        res = client.post(
            "/api/v1/projects/prj_1/features/feat_1/consistency/check",
            json={"content": {"title": "T", "description": "D"}},
        )
        assert res.status_code == 401

    # 2. Con autenticacion
    app.dependency_overrides[verify_project_owner] = lambda: None
    app.dependency_overrides[get_principal] = lambda: Principal(subject="usr_1")
    with TestClient(app) as client:
        res = client.post(
            "/api/v1/projects/prj_1/features/feat_1/consistency/check",
            json={"content": {"title": "T", "description": "D"}},
        )
        assert res.status_code == 200
        assert res.json()["is_consistent"] is True

    app.dependency_overrides.clear()
