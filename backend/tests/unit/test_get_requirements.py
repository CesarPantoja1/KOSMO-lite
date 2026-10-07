from typing import Any

import pytest

from kosmo.application.requirements.generate_ears import GetRequirementsUseCase
from kosmo.contracts.sdd.errors import FeatureNotFoundError, ProjectNotFoundError, RequirementsNotFoundError
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import FeatureId, ProjectId, UserId
from kosmo.contracts.sdd.project import Project
from tests.unit.fakes import InMemoryFeatureRepository, InMemoryProjectRepository, InMemoryRequirementRepository


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_requirements_returns_markdown_when_exists() -> None:
    # Arrange
    project_repo: Any = InMemoryProjectRepository()
    feature_repo: Any = InMemoryFeatureRepository()
    requirement_repo: Any = InMemoryRequirementRepository()
    use_case = GetRequirementsUseCase(
        project_repo=project_repo,
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
    )

    project = Project(
        id=ProjectId("prj_getreq01"),
        name="Test Project",
        slug="test-project",
        description="Test",
        owner_id=UserId("usr_getreq01"),
    )
    await project_repo.save(project)

    feature = Feature(
        id=FeatureId("feat_getreq01"),
        number=1,
        title="Test Feature",
        slug="test-feature",
        description="Test feature",
        project_id=project.id,
    )
    await feature_repo.save(feature)

    markdown = "## Requisitos EARS\n\n| ID | Desc |"
    await requirement_repo.save(feature.id, markdown)

    project_id = ProjectId("prj_getreq01")
    feature_id = FeatureId("feat_getreq01")

    # Act
    result = await use_case.execute(project_id, feature_id)

    # Assert
    assert result.markdown is not None
    assert "Requisitos EARS" in result.markdown
    assert result.feature_id == feature.id
    assert result.feature_number == 1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_requirements_raises_requirements_not_found() -> None:
    # Arrange
    project_repo: Any = InMemoryProjectRepository()
    feature_repo: Any = InMemoryFeatureRepository()
    requirement_repo: Any = InMemoryRequirementRepository()
    use_case = GetRequirementsUseCase(
        project_repo=project_repo,
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
    )

    project = Project(
        id=ProjectId("prj_getreq02"),
        name="Test Project",
        slug="test-project",
        description="Test",
        owner_id=UserId("usr_getreq02"),
    )
    await project_repo.save(project)

    feature = Feature(
        id=FeatureId("feat_getreq02"),
        number=1,
        title="Test Feature",
        slug="test-feature",
        description="Test feature",
        project_id=project.id,
    )
    await feature_repo.save(feature)

    project_id = ProjectId("prj_getreq02")
    feature_id = FeatureId("feat_getreq02")

    # Act & Assert
    with pytest.raises(RequirementsNotFoundError):
        await use_case.execute(project_id, feature_id)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_requirements_raises_project_not_found() -> None:
    # Arrange
    project_repo: Any = InMemoryProjectRepository()
    feature_repo: Any = InMemoryFeatureRepository()
    requirement_repo: Any = InMemoryRequirementRepository()
    use_case = GetRequirementsUseCase(
        project_repo=project_repo,
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
    )

    project_id = ProjectId("prj_nonexistent")
    feature_id = FeatureId("feat_getreq03")

    # Act & Assert
    with pytest.raises(ProjectNotFoundError):
        await use_case.execute(project_id, feature_id)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_requirements_raises_feature_not_found() -> None:
    # Arrange
    project_repo: Any = InMemoryProjectRepository()
    feature_repo: Any = InMemoryFeatureRepository()
    requirement_repo: Any = InMemoryRequirementRepository()
    use_case = GetRequirementsUseCase(
        project_repo=project_repo,
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
    )

    project = Project(
        id=ProjectId("prj_getreq04"),
        name="Test Project",
        slug="test-project",
        description="Test",
        owner_id=UserId("usr_getreq04"),
    )
    await project_repo.save(project)

    project_id = ProjectId("prj_getreq04")
    feature_id = FeatureId("feat_nonexistent")

    # Act & Assert
    with pytest.raises(FeatureNotFoundError):
        await use_case.execute(project_id, feature_id)
