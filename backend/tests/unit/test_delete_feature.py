from __future__ import annotations

import pytest

from kosmo.application.features.delete_feature import DeleteFeatureUseCase
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import FeatureId, ProjectId, UserId
from kosmo.contracts.sdd.project import Project
from tests.unit.fakes import (
    InMemoryFeatureRepository,
    InMemoryOutbox,
    InMemoryProjectRepository,
    InMemoryRequirementRepository,
    InMemoryTraceabilityRepository,
)


def _a_project(project_id: str = "prj_del") -> Project:
    return Project(
        id=ProjectId(project_id),
        name="Test Project",
        slug="test-project",
        description="Test",
        owner_id=UserId("usr_01"),
    )


def _a_feature(project: Project, feature_id: str = "feat_del") -> Feature:
    return Feature(
        id=FeatureId(feature_id),
        number=1,
        title="Característica a eliminar",
        slug="caracteristica-a-eliminar",
        description="Descripción",
        project_id=project.id,
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_feature_no_dispara_consistencia() -> None:
    # Arrange
    project_repo = InMemoryProjectRepository()
    project = _a_project()
    await project_repo.save(project)

    feature_repo = InMemoryFeatureRepository()
    feature = _a_feature(project)
    await feature_repo.save(feature)

    outbox = InMemoryOutbox()
    use_case = DeleteFeatureUseCase(
        project_repo=project_repo,
        feature_repo=feature_repo,
        requirement_repo=InMemoryRequirementRepository(),
        traceability_repo=InMemoryTraceabilityRepository(),
    )

    # Act
    await use_case.execute(project.id, feature.id)

    # Assert — eliminar una característica NO dispara evaluación de consistencia
    assert await feature_repo.by_id(feature.id) is None
    assert len(outbox.jobs) == 0


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_feature_elimina_sin_depender_de_outbox() -> None:
    # Arrange
    project_repo = InMemoryProjectRepository()
    project = _a_project("prj_del2")
    await project_repo.save(project)

    feature_repo = InMemoryFeatureRepository()
    feature = _a_feature(project, "feat_del2")
    await feature_repo.save(feature)

    use_case = DeleteFeatureUseCase(
        project_repo=project_repo,
        feature_repo=feature_repo,
        requirement_repo=InMemoryRequirementRepository(),
    )

    # Act & Assert — sin outbox el caso de uso sigue funcionando
    await use_case.execute(project.id, feature.id)
    assert await feature_repo.by_id(feature.id) is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_feature_cascades_requirements() -> None:
    # Arrange
    project_repo = InMemoryProjectRepository()
    project = _a_project("prj_del3")
    await project_repo.save(project)

    feature_repo = InMemoryFeatureRepository()
    feature = _a_feature(project, "feat_del3")
    await feature_repo.save(feature)

    requirement_repo = InMemoryRequirementRepository()
    await requirement_repo.save(feature.id, "### REQ-1.1\n\nRequisito uno.")
    use_case = DeleteFeatureUseCase(
        project_repo=project_repo,
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
    )

    # Act
    await use_case.execute(project.id, feature.id)

    # Assert — requisitos y modelo eliminados en cascada
    assert await requirement_repo.by_feature_id(feature.id) is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_feature_cascade_tolerates_missing_artifacts() -> None:
    # Arrange — la característica no tiene requisitos ni modelo
    project_repo = InMemoryProjectRepository()
    project = _a_project("prj_del4")
    await project_repo.save(project)

    feature_repo = InMemoryFeatureRepository()
    feature = _a_feature(project, "feat_del4")
    await feature_repo.save(feature)

    use_case = DeleteFeatureUseCase(
        project_repo=project_repo,
        feature_repo=feature_repo,
        requirement_repo=InMemoryRequirementRepository(),
    )

    # Act & Assert — el cascade no falla cuando los hijos no existen
    await use_case.execute(project.id, feature.id)
    assert await feature_repo.by_id(feature.id) is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_feature_returns_deleted_feature() -> None:
    # Arrange
    project_repo = InMemoryProjectRepository()
    project = _a_project("prj_del_ret")
    await project_repo.save(project)

    feature_repo = InMemoryFeatureRepository()
    feature = _a_feature(project, "feat_del_ret")
    await feature_repo.save(feature)

    use_case = DeleteFeatureUseCase(
        project_repo=project_repo,
        feature_repo=feature_repo,
        requirement_repo=InMemoryRequirementRepository(),
    )

    # Act
    deleted = await use_case.execute(project.id, feature.id)

    # Assert — retorna la feature eliminada (slug disponible para el cleanup de código)
    assert deleted.id == feature.id
    assert deleted.slug == "caracteristica-a-eliminar"
    assert deleted.project_id == project.id
