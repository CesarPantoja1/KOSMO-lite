from unittest.mock import AsyncMock

import pytest
from ulid import ULID

from kosmo.application.features.edit_feature import EditFeatureInput, EditFeatureUseCase
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
) -> EditFeatureUseCase:
    return EditFeatureUseCase(
        feature_repo=feature_repo,
        consistency_evaluator=consistency_evaluator,
    )


@pytest.mark.asyncio
async def test_edit_feature_success(
    use_case: EditFeatureUseCase,
    feature_repo: InMemoryFeatureRepository,
    consistency_evaluator: AsyncMock,
):
    project_id = ProjectId(ULID().hex)
    feature = Feature(
        id=FeatureId(ULID().hex),
        project_id=project_id,
        number=1,
        title="Old Title",
        slug="old-title",
        description="Old Desc",
    )
    await feature_repo.save(feature)
    feature_id = feature.id

    consistency_evaluator.evaluate.return_value = ConsistencyEvaluationOutput(
        report_id="rep_1",
        status=ConsistencyStatus.ANALIZADO_SIN_IMPACTO,
    )

    result = await use_case.execute(
        EditFeatureInput(
            project_id=project_id,
            feature_id=feature_id,
            title="New Title",
            description="New Desc",
        )
    )

    assert result.is_saved is True
    assert result.feature is not None
    assert result.feature.title == "New Title"
    assert result.feature.description == "New Desc"
    assert result.inconsistency_reason is None


@pytest.mark.asyncio
async def test_edit_feature_inconsistent(
    use_case: EditFeatureUseCase,
    feature_repo: InMemoryFeatureRepository,
    consistency_evaluator: AsyncMock,
):
    project_id = ProjectId(ULID().hex)
    feature = Feature(
        id=FeatureId(ULID().hex),
        project_id=project_id,
        number=1,
        title="Old Title",
        slug="old-title",
        description="Old Desc",
    )
    await feature_repo.save(feature)
    feature_id = feature.id

    consistency_evaluator.evaluate.return_value = ConsistencyEvaluationOutput(
        report_id="rep_1",
        status=ConsistencyStatus.ANALIZADO_CON_IMPACTO,
        actions=[
            ArtifactAction(
                artifact_id="some_id",
                action="update",
                rationale="This contradicts the discovery document.",
                suggested_field="Visión",
                suggested_before="Old",
                suggested_after="New",
            )
        ],
        affected_artifact_ids=["some_id"],
        rationale="General contradiction",
    )

    result = await use_case.execute(
        EditFeatureInput(
            project_id=project_id,
            feature_id=feature_id,
            title="New Title",
            description="New Desc",
        )
    )

    assert result.is_saved is False
    assert result.inconsistency_reason is not None
    assert "This contradicts the discovery document." in result.inconsistency_reason
    assert "Sugerencia: New" in result.inconsistency_reason

    # Verify not saved in DB
    saved = await feature_repo.by_id(feature_id)
    assert saved is not None
    assert saved.title == "Old Title"


@pytest.mark.asyncio
async def test_edit_feature_not_found(use_case: EditFeatureUseCase):
    with pytest.raises(FeatureNotFoundError):
        await use_case.execute(
            EditFeatureInput(
                project_id=ProjectId(ULID().hex),
                feature_id=FeatureId(ULID().hex),
                title="New Title",
                description="New Desc",
            )
        )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_edit_feature_enqueues_downstream_evaluation() -> None:
    # Arrange
    from tests.unit.fakes import InMemoryOutbox

    feature_repo = InMemoryFeatureRepository()
    evaluator = AsyncMock()
    evaluator.evaluate.return_value = ConsistencyEvaluationOutput(
        report_id="rep_1",
        status=ConsistencyStatus.ANALIZADO_SIN_IMPACTO,
    )
    outbox = InMemoryOutbox()
    use_case = EditFeatureUseCase(
        feature_repo=feature_repo,
        consistency_evaluator=evaluator,
        outbox=outbox,
    )

    project_id = ProjectId(ULID().hex)
    feature = Feature(
        id=FeatureId(ULID().hex),
        project_id=project_id,
        number=1,
        title="Old Title",
        slug="old-title",
        description="Old Desc",
    )
    await feature_repo.save(feature)

    # Act
    result = await use_case.execute(
        EditFeatureInput(
            project_id=project_id,
            feature_id=feature.id,
            title="New Title",
            description="New Desc",
        )
    )

    # Assert — la edición manual dispara la verificación de las fases a la derecha
    assert result.is_saved is True
    assert len(outbox.jobs) == 1
    job_type, payload = outbox.jobs[0]
    assert job_type == "consistency_evaluate"
    assert payload["project_id"] == str(project_id)
    assert payload["source_phase"] == "caracteristicas"


@pytest.mark.asyncio
async def test_edit_feature_emits_warning_on_capability_overlap(
    use_case: EditFeatureUseCase,
    feature_repo: InMemoryFeatureRepository,
    consistency_evaluator: AsyncMock,
):
    project_id = ProjectId(ULID().hex)
    feat1 = Feature(
        id=FeatureId(ULID().hex),
        project_id=project_id,
        number=1,
        title="Registro de usuarios",
        slug="registro-de-usuarios",
        description="Registro y gestion de nuevos usuarios.",
    )
    feat2 = Feature(
        id=FeatureId(ULID().hex),
        project_id=project_id,
        number=2,
        title="Perfil",
        slug="perfil",
        description="Perfil de usuario.",
    )
    await feature_repo.save(feat1)
    await feature_repo.save(feat2)

    consistency_evaluator.evaluate.return_value = ConsistencyEvaluationOutput(
        report_id="rep_1",
        status=ConsistencyStatus.ANALIZADO_SIN_IMPACTO,
    )

    result = await use_case.execute(
        EditFeatureInput(
            project_id=project_id,
            feature_id=feat2.id,
            title="Aceptar terminos y condiciones",
            description="Confirmacion de politicas y consentimiento para registro de usuarios.",
        )
    )

    assert result.is_saved is True
    assert len(result.warnings) > 0
    assert any("solapamiento" in w.lower() or "sub-capacidad" in w.lower() for w in result.warnings)
