"""Tests unitarios para ContextBuilder y el método build_implementation_context.

Sigue la metodología TDD con estructura AAA, markers @pytest.mark.asyncio y @pytest.mark.unit.
"""

from __future__ import annotations

import pytest

from kosmo.application.pipeline.context_builder import ContextBuilder
from kosmo.contracts.pipeline.phase_contexts import ImplementationPhaseContext
from kosmo.contracts.sdd.errors import FeatureNotFoundError
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import FeatureId, ProjectId
from tests.unit.fakes import (
    InMemoryDocumentRepository,
    InMemoryFeatureRepository,
    InMemoryProjectRepository,
    InMemoryRequirementRepository,
)

_EARS_SAMPLE = """\
### REQ-1.1 Registrar gastos

**Ubicuo**

El sistema shall registrar un gasto con monto y descripción.
"""


def _a_feature(
    feature_id: str = "feat_01TEST",
    title: str = "Registrar gastos",
    project_id: str = "prj_01TEST",
) -> Feature:
    return Feature(
        id=FeatureId(feature_id),
        number=1,
        title=title,
        slug="registrar-gastos",
        description="Permite a los usuarios registrar gastos compartidos.",
        project_id=ProjectId(project_id),
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_build_implementation_context_success() -> None:
    """Happy path: ensambla determinísticamente el contexto con Feature, EARS y manifiesto."""
    # Arrange
    doc_repo = InMemoryDocumentRepository()
    project_repo = InMemoryProjectRepository()
    feature_repo = InMemoryFeatureRepository()
    req_repo = InMemoryRequirementRepository()

    feature = _a_feature()
    await feature_repo.save(feature)
    await req_repo.save(feature.id, _EARS_SAMPLE)

    manifest = ("src/index.ts", "package.json", "tsconfig.json")

    builder = ContextBuilder(
        document_repo=doc_repo,
        project_repo=project_repo,
        feature_repo=feature_repo,
        requirement_repo=req_repo,
    )

    # Act
    context = await builder.build_implementation_context(feature.id, workspace_manifest=manifest)

    # Assert
    assert isinstance(context, ImplementationPhaseContext)
    assert context.feature.id == feature.id
    assert context.feature.title == "Registrar gastos"
    assert context.requirements_markdown == _EARS_SAMPLE
    assert context.ears_requirements == _EARS_SAMPLE
    assert context.workspace_manifest == manifest
    assert context.manifest_files == manifest


@pytest.mark.asyncio
@pytest.mark.unit
async def test_build_implementation_context_raises_when_feature_not_found() -> None:
    """Error path: lanza FeatureNotFoundError si la característica no existe."""
    # Arrange
    doc_repo = InMemoryDocumentRepository()
    project_repo = InMemoryProjectRepository()
    feature_repo = InMemoryFeatureRepository()
    req_repo = InMemoryRequirementRepository()

    builder = ContextBuilder(
        document_repo=doc_repo,
        project_repo=project_repo,
        feature_repo=feature_repo,
        requirement_repo=req_repo,
    )

    # Act & Assert
    with pytest.raises(FeatureNotFoundError) as exc_info:
        await builder.build_implementation_context(FeatureId("feat_nonexistent"))

    # Assert
    assert "feat_nonexistent" in exc_info.value.problem.detail


@pytest.mark.asyncio
@pytest.mark.unit
async def test_build_implementation_context_raises_when_feature_repo_missing() -> None:
    """Error path: lanza ValueError si el feature_repo no está configurado."""
    # Arrange
    doc_repo = InMemoryDocumentRepository()
    project_repo = InMemoryProjectRepository()

    builder = ContextBuilder(
        document_repo=doc_repo,
        project_repo=project_repo,
        feature_repo=None,
        requirement_repo=InMemoryRequirementRepository(),
    )

    # Act & Assert
    with pytest.raises(ValueError, match="FeatureRepository"):
        await builder.build_implementation_context(FeatureId("feat_01TEST"))


@pytest.mark.asyncio
@pytest.mark.unit
async def test_build_implementation_context_raises_when_requirement_repo_missing() -> None:
    """Error path: lanza ValueError si el requirement_repo no está configurado."""
    # Arrange
    doc_repo = InMemoryDocumentRepository()
    project_repo = InMemoryProjectRepository()
    feature_repo = InMemoryFeatureRepository()

    builder = ContextBuilder(
        document_repo=doc_repo,
        project_repo=project_repo,
        feature_repo=feature_repo,
        requirement_repo=None,
    )

    # Act & Assert
    with pytest.raises(ValueError, match="RequirementRepository"):
        await builder.build_implementation_context(FeatureId("feat_01TEST"))


@pytest.mark.asyncio
@pytest.mark.unit
async def test_build_implementation_context_with_empty_requirements() -> None:
    """Edge case: retorna markdown vacío si no existen requisitos guardados."""
    # Arrange
    doc_repo = InMemoryDocumentRepository()
    project_repo = InMemoryProjectRepository()
    feature_repo = InMemoryFeatureRepository()
    req_repo = InMemoryRequirementRepository()

    feature = _a_feature()
    await feature_repo.save(feature)

    builder = ContextBuilder(
        document_repo=doc_repo,
        project_repo=project_repo,
        feature_repo=feature_repo,
        requirement_repo=req_repo,
    )

    # Act
    context = await builder.build_implementation_context(feature.id)

    # Assert
    assert context.requirements_markdown == ""
    assert context.ears_requirements == ""
    assert context.workspace_manifest == ()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_build_implementation_context_excludes_heavy_artifacts() -> None:
    """Verifica que el contexto excluye explícitamente descubrimiento, chat y contenido de archivos."""
    # Arrange
    from kosmo.contracts.sdd.document import DocumentNode, RichTextDocument

    doc_repo = InMemoryDocumentRepository()
    project_repo = InMemoryProjectRepository()
    feature_repo = InMemoryFeatureRepository()
    req_repo = InMemoryRequirementRepository()

    feature = _a_feature()
    await feature_repo.save(feature)
    await req_repo.save(feature.id, _EARS_SAMPLE)

    # Simular documento de descubrimiento grande
    await doc_repo.save_discovery(
        feature.project_id,
        RichTextDocument(
            nodes=[
                DocumentNode(
                    type="paragraph",
                    content="# Visión del Producto\n" + ("Contenido extenso de descubrimiento... " * 100),
                )
            ]
        ),
    )

    builder = ContextBuilder(
        document_repo=doc_repo,
        project_repo=project_repo,
        feature_repo=feature_repo,
        requirement_repo=req_repo,
    )

    # Act
    context = await builder.build_implementation_context(
        feature.id,
        workspace_manifest=("src/app.ts", "src/models.ts"),
    )

    # Assert - No contiene atributos de descubrimiento ni chat
    assert not hasattr(context, "discovery_document")
    assert not hasattr(context, "chat_history")
    assert not hasattr(context, "file_contents")

    # El tamaño del contexto no contiene el texto del documento de descubrimiento
    assert "Contenido extenso de descubrimiento" not in context.requirements_markdown
    assert "Contenido extenso de descubrimiento" not in str(context.workspace_manifest)
