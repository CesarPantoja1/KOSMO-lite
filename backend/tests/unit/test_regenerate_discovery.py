from __future__ import annotations

import pytest

from kosmo.application.discovery.regenerate_discovery import (
    RegenerateDiscoveryInput,
    RegenerateDiscoveryOutput,
    RegenerateDiscoveryUseCase,
)
from kosmo.contracts.pipeline.phase_outputs import (
    DiscoveryPhaseOutput,
    GenerationMetadata,
    ValidationResult,
)
from kosmo.contracts.sdd.errors import LLMInvocationError, ProjectNotFoundError
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import FeatureId, ProjectId, UserId
from kosmo.contracts.sdd.project import Project
from kosmo.contracts.sdd.repositories import (
    DocumentRepository,
    FeatureRepository,
    ProjectRepository,
    RequirementRepository,
)
from tests.unit.fakes import (
    InMemoryDocumentRepository,
    InMemoryFeatureRepository,
    InMemoryProjectRepository,
    InMemoryRequirementRepository,
)


class StubRegenerateAgent:
    def __init__(self, *, should_fail: bool = False) -> None:
        self._should_fail = should_fail

    async def execute_with_skill(
        self,
        skill_name: str,
        context: object,
        *,
        project_id: object | None = None,  # noqa: ARG002
        user_instructions: str | None = None,  # noqa: ARG002
    ) -> object:
        if self._should_fail:
            raise RuntimeError("Stub agent failure")

        from kosmo.domain.sdd.document_converters import markdown_to_document

        regenerated = "## Visión\n\nProducto regenerado.\n\n## Alcance\n\nAlcance regenerado."
        doc = markdown_to_document(regenerated)
        return DiscoveryPhaseOutput(
            discovery_document=doc,
            validation_result=ValidationResult(is_valid=True, errors=[]),
            generation_metadata=GenerationMetadata(),
        )

    async def execute_conversation(
        self,
        skill_name: str,
        messages: list[object],
        context: object,
        **kwargs: object,  # noqa: ARG002
    ) -> object:
        raise NotImplementedError


def _make_project(project_id: str = "prj_test") -> Project:
    return Project(
        id=ProjectId(project_id),
        name="Test Project",
        slug="test-project",
        description="Test",
        owner_id=UserId("usr_test"),
    )


def _make_feature(feature_id: str, project_id: str, title: str, number: int = 1) -> Feature:
    return Feature(
        id=FeatureId(feature_id),
        number=number,
        title=title,
        slug=title.lower().replace(" ", "-"),
        description=f"Descripción de {title}",
        project_id=ProjectId(project_id),
        origin="Derivado de Descubrimiento",
    )


async def _seed_document(document_repo: InMemoryDocumentRepository, project_id: ProjectId) -> None:
    from kosmo.domain.sdd.document_converters import markdown_to_document

    document_repo.discovery_docs[str(project_id)] = markdown_to_document(
        "## Visión\n\nVisión original.\n\n## Alcance\n\nAlcance original."
    )


def _make_uc(
    project_repo: ProjectRepository,
    document_repo: DocumentRepository,
    feature_repo: FeatureRepository,
    requirement_repo: RequirementRepository,
    agent: StubRegenerateAgent,
) -> RegenerateDiscoveryUseCase:
    return RegenerateDiscoveryUseCase(
        project_repo=project_repo,
        document_repo=document_repo,
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        agent=agent,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_regenerate_discovery_with_features() -> None:
    # Arrange
    project_repo = InMemoryProjectRepository()
    project = _make_project("prj_001")
    await project_repo.save(project)

    document_repo = InMemoryDocumentRepository()
    await _seed_document(document_repo, project.id)

    feature_repo = InMemoryFeatureRepository()
    feat = _make_feature("feat_01", "prj_001", "Gestión de catálogo", number=1)
    await feature_repo.save(feat)

    requirement_repo = InMemoryRequirementRepository()
    await requirement_repo.save(FeatureId("feat_01"), "# REQ-1.1\nRequisito de catálogo.")
    agent = StubRegenerateAgent()
    uc = _make_uc(project_repo, document_repo, feature_repo, requirement_repo, agent)

    # Act
    result = await uc.execute(RegenerateDiscoveryInput(project_id=ProjectId("prj_001")))

    # Assert
    assert isinstance(result, RegenerateDiscoveryOutput)
    assert result.phase == "discovery"
    assert "Producto regenerado" in result.content
    assert result.artifact_id == "prj_001"

    saved = await document_repo.get_discovery(ProjectId("prj_001"))
    assert saved is not None
    from kosmo.domain.sdd.document_converters import document_to_markdown

    assert "Producto regenerado" in document_to_markdown(saved)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_regenerate_discovery_project_not_found() -> None:
    # Arrange
    project_repo = InMemoryProjectRepository()
    document_repo = InMemoryDocumentRepository()
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    agent = StubRegenerateAgent()
    uc = _make_uc(project_repo, document_repo, feature_repo, requirement_repo, agent)

    # Act & Assert
    with pytest.raises(ProjectNotFoundError):
        await uc.execute(RegenerateDiscoveryInput(project_id=ProjectId("prj_nonexistent")))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_regenerate_discovery_agent_failure_raises_llm_error() -> None:
    # Arrange
    project_repo = InMemoryProjectRepository()
    project = _make_project("prj_002")
    await project_repo.save(project)

    document_repo = InMemoryDocumentRepository()
    await _seed_document(document_repo, project.id)

    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    agent = StubRegenerateAgent(should_fail=True)
    uc = _make_uc(project_repo, document_repo, feature_repo, requirement_repo, agent)

    # Act & Assert
    with pytest.raises(LLMInvocationError, match="Error al regenerar"):
        await uc.execute(RegenerateDiscoveryInput(project_id=ProjectId("prj_002")))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_regenerate_discovery_without_downstream_artifacts() -> None:
    # Arrange
    project_repo = InMemoryProjectRepository()
    project = _make_project("prj_003")
    await project_repo.save(project)

    document_repo = InMemoryDocumentRepository()
    await _seed_document(document_repo, project.id)

    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    agent = StubRegenerateAgent()
    uc = _make_uc(project_repo, document_repo, feature_repo, requirement_repo, agent)

    # Act
    result = await uc.execute(RegenerateDiscoveryInput(project_id=ProjectId("prj_003")))

    # Assert: regenera exitosamente aunque no haya artefactos downstream
    assert result.phase == "discovery"
    assert "Producto regenerado" in result.content
