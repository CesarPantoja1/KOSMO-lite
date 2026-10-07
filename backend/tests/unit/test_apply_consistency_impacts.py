from __future__ import annotations

import pytest

from kosmo.application.consistency.apply_consistency_impacts import ApplyConsistencyImpactsUseCase
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import FeatureId, ProjectId, UserId
from kosmo.contracts.sdd.project import Project
from kosmo.domain.sdd.document_converters import document_to_markdown, markdown_to_document
from tests.unit.fakes import (
    InMemoryActivityDiagramRepository,
    InMemoryDocumentRepository,
    InMemoryFeatureRepository,
    InMemoryProjectRepository,
    InMemoryRequirementRepository,
    InMemoryTraceabilityRepository,
    InMemoryUnitOfWork,
)

_DEFAULT_MARKDOWN = "## Visión\n\nContenido de visión.\n\n## Alcance\n\nContenido de alcance original."


def _make_project(project_id: str = "prj_test") -> Project:
    return Project(
        id=ProjectId(project_id),
        name="Test Project",
        slug="test-project",
        description="Test",
        owner_id=UserId("usr_test"),
    )


def _make_feature(project_id: ProjectId, feature_id: str = "feat_01") -> Feature:
    return Feature(
        id=FeatureId(feature_id),
        project_id=project_id,
        number=1,
        title="Test Feature",
        slug="test-feature",
        description="Descripción original.",
    )


def _make_uc(
    project_repo: InMemoryProjectRepository,
    document_repo: InMemoryDocumentRepository,
    *,
    feature_repo: InMemoryFeatureRepository | None = None,
    requirement_repo: InMemoryRequirementRepository | None = None,
    diagram_repo: InMemoryActivityDiagramRepository | None = None,
    traceability: InMemoryTraceabilityRepository | None = None,
) -> ApplyConsistencyImpactsUseCase:
    uow = InMemoryUnitOfWork(
        projects=project_repo,
        documents=document_repo,
        features=feature_repo,
        requirements=requirement_repo,
        diagrams=diagram_repo,
        traceability=traceability,
    )
    return ApplyConsistencyImpactsUseCase(uow=uow)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_apply_discovery_document_update_applies_diff() -> None:
    # Arrange
    project = _make_project()
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)
    document_repo = InMemoryDocumentRepository()
    document_repo.discovery_docs[str(project.id)] = markdown_to_document(_DEFAULT_MARKDOWN)
    uc = _make_uc(project_repo, document_repo)

    # Act
    result = await uc.execute(
        project_id=project.id,
        impacts=[
            {
                "artifact_type": "DiscoveryDocument",
                "target_id": str(project.id),
                "action": "update",
                "field": "content",
                "before": "Contenido de alcance original.",
                "after": "Contenido de alcance actualizado.",
            }
        ],
    )

    # Assert
    assert len(result.applied) == 1
    assert len(result.failed) == 0

    doc = await document_repo.get_discovery(project.id)
    assert doc is not None
    markdown = document_to_markdown(doc)
    assert "Contenido de alcance actualizado." in markdown
    assert "Contenido de alcance original." not in markdown


@pytest.mark.unit
@pytest.mark.asyncio
async def test_apply_discovery_document_delete_is_rejected() -> None:
    # Arrange
    project = _make_project()
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)
    document_repo = InMemoryDocumentRepository()
    document_repo.discovery_docs[str(project.id)] = markdown_to_document(_DEFAULT_MARKDOWN)
    uc = _make_uc(project_repo, document_repo)

    # Act
    result = await uc.execute(
        project_id=project.id,
        impacts=[
            {
                "artifact_type": "DiscoveryDocument",
                "target_id": str(project.id),
                "action": "delete",
                "field": "",
                "before": "",
                "after": "",
            }
        ],
    )

    # Assert: el documento no puede eliminarse
    assert len(result.applied) == 0
    assert len(result.failed) == 1
    assert "no puede eliminarse" in result.failed[0].reason


@pytest.mark.unit
@pytest.mark.asyncio
async def test_apply_unknown_artifact_type_is_failed() -> None:
    # Arrange
    project = _make_project()
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)
    document_repo = InMemoryDocumentRepository()
    uc = _make_uc(project_repo, document_repo)

    # Act
    result = await uc.execute(
        project_id=project.id,
        impacts=[
            {
                "artifact_type": "ArtefactoInexistente",
                "target_id": "feat_01",
                "action": "update",
                "field": "description",
                "before": "a",
                "after": "b",
            }
        ],
    )

    # Assert
    assert len(result.applied) == 0
    assert len(result.failed) == 1
    assert "desconocido" in result.failed[0].reason


@pytest.mark.unit
@pytest.mark.asyncio
async def test_apply_requirement_update_rebuilds_traceability_edges() -> None:
    # Arrange: requisitos existentes y un edge viejo que debe reemplazarse
    project = _make_project()
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)
    document_repo = InMemoryDocumentRepository()
    feature_repo = InMemoryFeatureRepository()
    await feature_repo.save(_make_feature(project.id))
    requirement_repo = InMemoryRequirementRepository()
    await requirement_repo.save(
        FeatureId("feat_01"),
        "### REQ-1.1 Procesamiento de pagos\n\nEl sistema debe procesar pagos.\n",
    )
    traceability = InMemoryTraceabilityRepository()
    await traceability.add_edge("feature", "feat_01", "requirement", "req_viejo")
    uc = _make_uc(
        project_repo,
        document_repo,
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        traceability=traceability,
    )

    # Act
    result = await uc.execute(
        project_id=project.id,
        impacts=[
            {
                "artifact_type": "EARSRequirement",
                "target_id": "feat_01",
                "action": "update",
                "field": "content",
                "before": "El sistema debe procesar pagos.",
                "after": "El sistema debe procesar pagos con tarjeta.",
            }
        ],
    )

    # Assert: requisitos actualizados y edges reemplazados en la misma transaccion
    assert len(result.applied) == 1
    assert len(result.failed) == 0
    saved = await requirement_repo.by_feature_id(FeatureId("feat_01"))
    assert saved is not None
    assert "con tarjeta" in saved

    assert len(traceability.edges) == 1
    assert traceability.edges[0][1] == "feat_01"
    assert traceability.edges[0][3].startswith("req_")
    assert traceability.edges[0][3] != "req_viejo"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_apply_feature_delete_cascades_requirements_and_diagram() -> None:
    # Arrange: feature con requisitos y diagrama — el delete debe borrarlos en cascada
    project = _make_project()
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)
    document_repo = InMemoryDocumentRepository()
    feature_repo = InMemoryFeatureRepository()
    await feature_repo.save(_make_feature(project.id))
    requirement_repo = InMemoryRequirementRepository()
    await requirement_repo.save(
        FeatureId("feat_01"),
        "### REQ-1.1 Procesamiento de pagos\n\nEl sistema debe procesar pagos.\n",
    )
    diagram_repo = InMemoryActivityDiagramRepository()
    await _seed_diagram(diagram_repo, "feat_01")
    uc = _make_uc(
        project_repo,
        document_repo,
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        diagram_repo=diagram_repo,
    )

    # Act
    result = await uc.execute(
        project_id=project.id,
        impacts=[
            {
                "artifact_type": "Feature",
                "target_id": "feat_01",
                "action": "delete",
                "field": "",
                "before": "",
                "after": "",
            }
        ],
    )

    # Assert: feature eliminada junto con sus requisitos y modelo
    assert len(result.applied) == 1
    assert len(result.failed) == 0
    assert await feature_repo.by_id(FeatureId("feat_01")) is None
    assert await requirement_repo.by_feature_id(FeatureId("feat_01")) is None
    assert await diagram_repo.by_feature_id(FeatureId("feat_01")) is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_apply_failed_impact_does_not_block_subsequent_impacts() -> None:
    # Arrange: primer impacto invalido, segundo valido
    project = _make_project()
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)
    document_repo = InMemoryDocumentRepository()
    document_repo.discovery_docs[str(project.id)] = markdown_to_document(_DEFAULT_MARKDOWN)
    uc = _make_uc(project_repo, document_repo)

    # Act
    result = await uc.execute(
        project_id=project.id,
        impacts=[
            {
                "artifact_type": "DiscoveryDocument",
                "target_id": str(project.id),
                "action": "update",
                "field": "content",
                "before": "Texto que no existe",
                "after": "No importa",
            },
            {
                "artifact_type": "DiscoveryDocument",
                "target_id": str(project.id),
                "action": "update",
                "field": "content",
                "before": "Contenido de alcance original.",
                "after": "Contenido de alcance actualizado.",
            },
        ],
    )

    # Assert: el fallo del primero no envenena la transaccion del segundo
    assert len(result.applied) == 1
    assert len(result.failed) == 1
    doc = await document_repo.get_discovery(project.id)
    assert doc is not None
    assert "Contenido de alcance actualizado." in document_to_markdown(doc)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_apply_locks_discovery_document_row() -> None:
    # Arrange
    project = _make_project()
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)
    document_repo = InMemoryDocumentRepository()
    document_repo.discovery_docs[str(project.id)] = markdown_to_document(_DEFAULT_MARKDOWN)
    uc = _make_uc(project_repo, document_repo)

    # Act
    result = await uc.execute(
        project_id=project.id,
        impacts=[
            {
                "artifact_type": "DiscoveryDocument",
                "target_id": str(project.id),
                "action": "update",
                "field": "content",
                "before": "Contenido de alcance original.",
                "after": "Contenido de alcance actualizado.",
            }
        ],
    )

    # Assert — la lectura del artefacto destino se hace con lock
    assert len(result.applied) == 1
    assert str(project.id) in document_repo.locked_project_ids


@pytest.mark.unit
@pytest.mark.asyncio
async def test_apply_locks_feature_row() -> None:
    # Arrange
    project = _make_project()
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)
    document_repo = InMemoryDocumentRepository()
    feature_repo = InMemoryFeatureRepository()
    await feature_repo.save(_make_feature(project.id))
    uc = _make_uc(project_repo, document_repo, feature_repo=feature_repo)

    # Act
    result = await uc.execute(
        project_id=project.id,
        impacts=[
            {
                "artifact_type": "Feature",
                "target_id": "feat_01",
                "action": "update",
                "field": "description",
                "before": "Descripción original.",
                "after": "Descripción actualizada.",
            }
        ],
    )

    # Assert
    assert len(result.applied) == 1
    assert "feat_01" in feature_repo.locked_feature_ids


@pytest.mark.unit
@pytest.mark.asyncio
async def test_apply_feature_description_ignora_origen_en_diff() -> None:
    # Arrange — el LLM incluye "Origen:" en before/after (contexto interno), la BD está limpia
    project = _make_project()
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)
    document_repo = InMemoryDocumentRepository()
    feature_repo = InMemoryFeatureRepository()
    await feature_repo.save(_make_feature(project.id))
    uc = _make_uc(project_repo, document_repo, feature_repo=feature_repo)

    # Act — reproducción del error real: before con "Origen: ..." contra descripción limpia
    result = await uc.execute(
        project_id=project.id,
        impacts=[
            {
                "artifact_type": "Feature",
                "target_id": "feat_01",
                "action": "update",
                "field": "description",
                "before": "Descripción original.\nOrigen: Meta Gestion en Metas del producto.",
                "after": "Descripción actualizada.\nOrigen: Meta Gestion en Metas del producto.",
            }
        ],
    )

    # Assert — aplica sin fallar y la descripción guardada queda limpia (sin Origen)
    assert len(result.applied) == 1
    updated = await feature_repo.by_id(FeatureId("feat_01"))
    assert updated is not None
    assert updated.description == "Descripción actualizada."
    assert "Origen" not in updated.description


@pytest.mark.unit
@pytest.mark.asyncio
async def test_apply_feature_origin_field_se_mantiene_directo() -> None:
    # Arrange — el campo origin se aplica tal cual (el strip solo aplica a description)
    project = _make_project()
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)
    document_repo = InMemoryDocumentRepository()
    feature_repo = InMemoryFeatureRepository()
    feature = _make_feature(project.id)
    feature.origin = "Origen: Meta antigua en Metas del producto."
    await feature_repo.save(feature)
    uc = _make_uc(project_repo, document_repo, feature_repo=feature_repo)

    # Act — el after empieza con "Origen:" a propósito: no debe ser eliminado
    result = await uc.execute(
        project_id=project.id,
        impacts=[
            {
                "artifact_type": "Feature",
                "target_id": "feat_01",
                "action": "update",
                "field": "origin",
                "before": "Origen: Meta antigua en Metas del producto.",
                "after": "Origen: Meta nueva en Metas del producto.",
            }
        ],
    )

    # Assert
    assert len(result.applied) == 1
    updated = await feature_repo.by_id(FeatureId("feat_01"))
    assert updated is not None
    assert updated.origin == "Origen: Meta nueva en Metas del producto."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_apply_locks_requirement_and_diagram_rows() -> None:
    # Arrange
    project = _make_project()
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)
    document_repo = InMemoryDocumentRepository()
    feature_repo = InMemoryFeatureRepository()
    await feature_repo.save(_make_feature(project.id))
    requirement_repo = InMemoryRequirementRepository()
    await requirement_repo.save(
        FeatureId("feat_01"),
        "### REQ-1.1 Procesamiento de pagos\n\nEl sistema debe procesar pagos.\n",
    )
    diagram_repo = InMemoryActivityDiagramRepository()
    uc = _make_uc(
        project_repo,
        document_repo,
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        diagram_repo=diagram_repo,
    )

    # Act — dos impactos, cada uno sobre su artefacto destino
    result = await uc.execute(
        project_id=project.id,
        impacts=[
            {
                "artifact_type": "EARSRequirement",
                "target_id": "feat_01",
                "action": "update",
                "field": "content",
                "before": "El sistema debe procesar pagos.",
                "after": "El sistema debe procesar pagos con tarjeta.",
            },
            {
                "artifact_type": "ActivityDiagram",
                "target_id": "feat_01",
                "action": "update",
                "field": "estructura UML",
                "before": "@startuml",
                "after": "@enduml",
            },
        ],
    )

    # Assert — requisitos aplicado; diagrama sin datos existentes falla con lock registrado
    assert len(result.applied) == 1
    assert len(result.failed) == 1
    assert "feat_01" in requirement_repo.locked_feature_ids
    assert "feat_01" in diagram_repo.locked_feature_ids


_VALID_DIAGRAM = "@startuml\nstart\n|Sistema|\n:Registrar pago;\nstop\n@enduml"


async def _seed_diagram(diagram_repo: InMemoryActivityDiagramRepository, feature_id: str) -> None:
    from kosmo.contracts.sdd.activity_diagram import DiagramaActividad
    from kosmo.contracts.sdd.ids import ActivityDiagramId

    await diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId(feature_id),
            feature_id=FeatureId(feature_id),
            diagram_syntax=_VALID_DIAGRAM,
        )
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_apply_diagram_update_breaking_validation_fails() -> None:
    """Un apply que rompe la sintaxis PlantUML debe fallar sin persistir el diagrama."""
    # Arrange
    project = _make_project()
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)
    document_repo = InMemoryDocumentRepository()
    feature_repo = InMemoryFeatureRepository()
    await feature_repo.save(_make_feature(project.id))
    diagram_repo = InMemoryActivityDiagramRepository()
    await _seed_diagram(diagram_repo, "feat_01")
    uc = _make_uc(
        project_repo,
        document_repo,
        feature_repo=feature_repo,
        diagram_repo=diagram_repo,
    )

    # Act
    result = await uc.execute(
        project_id=project.id,
        impacts=[
            {
                "artifact_type": "ActivityDiagram",
                "target_id": "feat_01",
                "action": "update",
                "field": "estructura UML",
                "before": "@enduml",
                "after": "",
            }
        ],
    )

    # Assert: el apply falla con error claro y el diagrama original sigue intacto
    assert len(result.applied) == 0
    assert len(result.failed) == 1
    assert "sintaxis" in result.failed[0].reason
    saved = await diagram_repo.by_feature_id(FeatureId("feat_01"))
    assert saved is not None
    assert saved.diagram_syntax.endswith("@enduml")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_apply_diagram_valid_update_persists() -> None:
    """Un apply que mantiene la sintaxis PlantUML válida debe persistirse correctamente."""
    # Arrange
    project = _make_project()
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)
    document_repo = InMemoryDocumentRepository()
    feature_repo = InMemoryFeatureRepository()
    await feature_repo.save(_make_feature(project.id))
    diagram_repo = InMemoryActivityDiagramRepository()
    await _seed_diagram(diagram_repo, "feat_01")
    uc = _make_uc(
        project_repo,
        document_repo,
        feature_repo=feature_repo,
        diagram_repo=diagram_repo,
    )

    # Act
    result = await uc.execute(
        project_id=project.id,
        impacts=[
            {
                "artifact_type": "ActivityDiagram",
                "target_id": "feat_01",
                "action": "update",
                "field": "estructura UML",
                "before": ":Registrar pago;",
                "after": ":Registrar pago con tarjeta;",
            }
        ],
    )

    # Assert
    assert len(result.applied) == 1
    assert len(result.failed) == 0
    saved = await diagram_repo.by_feature_id(FeatureId("feat_01"))
    assert saved is not None
    assert "Registrar pago con tarjeta" in saved.diagram_syntax
    assert saved.diagram_syntax.endswith("@enduml")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_apply_feature_implementation_update_marks_requires_review() -> None:
    from datetime import UTC, datetime

    from kosmo.contracts.sdd.codegen import FeatureImplementation, FeatureImplementationStatus
    from kosmo.contracts.sdd.ids import ImplementationId
    from tests.unit.fakes import InMemoryFeatureImplementationRepository

    project = _make_project()
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)
    document_repo = InMemoryDocumentRepository()
    feature_repo = InMemoryFeatureRepository()
    feature = _make_feature(project.id)
    await feature_repo.save(feature)

    impl_repo = InMemoryFeatureImplementationRepository()
    now = datetime.now(UTC)
    impl = FeatureImplementation(
        id=ImplementationId("impl_01"),
        feature_id=feature.id,
        project_id=project.id,
        status=FeatureImplementationStatus.IMPLEMENTED,
        attempt_count=1,
        max_attempts=3,
        generated_files=("src/index.ts",),
        created_at=now,
        updated_at=now,
    )
    await impl_repo.save(impl)

    uow = InMemoryUnitOfWork(
        projects=project_repo,
        documents=document_repo,
        features=feature_repo,
        implementations=impl_repo,
    )
    uc = ApplyConsistencyImpactsUseCase(uow=uow)

    result = await uc.execute(
        project_id=project.id,
        impacts=[
            {
                "artifact_type": "FeatureImplementation",
                "target_id": str(feature.id),
                "action": "update",
                "field": "código",
                "before": "",
                "after": "",
            }
        ],
    )

    assert len(result.applied) == 1
    assert len(result.failed) == 0
    updated_impl = await impl_repo.by_feature_id(feature.id)
    assert updated_impl is not None
    assert updated_impl.status == FeatureImplementationStatus.REQUIRES_REVIEW


@pytest.mark.unit
@pytest.mark.asyncio
async def test_apply_feature_implementation_delete_removes_it() -> None:
    from datetime import UTC, datetime

    from kosmo.contracts.sdd.codegen import FeatureImplementation, FeatureImplementationStatus
    from kosmo.contracts.sdd.ids import ImplementationId
    from tests.unit.fakes import InMemoryFeatureImplementationRepository

    project = _make_project()
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)
    document_repo = InMemoryDocumentRepository()
    feature_repo = InMemoryFeatureRepository()
    feature = _make_feature(project.id)
    await feature_repo.save(feature)

    impl_repo = InMemoryFeatureImplementationRepository()
    now = datetime.now(UTC)
    impl = FeatureImplementation(
        id=ImplementationId("impl_01"),
        feature_id=feature.id,
        project_id=project.id,
        status=FeatureImplementationStatus.IMPLEMENTED,
        attempt_count=1,
        max_attempts=3,
        generated_files=("src/index.ts",),
        created_at=now,
        updated_at=now,
    )
    await impl_repo.save(impl)

    uow = InMemoryUnitOfWork(
        projects=project_repo,
        documents=document_repo,
        features=feature_repo,
        implementations=impl_repo,
    )
    uc = ApplyConsistencyImpactsUseCase(uow=uow)

    result = await uc.execute(
        project_id=project.id,
        impacts=[
            {
                "artifact_type": "FeatureImplementation",
                "target_id": str(feature.id),
                "action": "delete",
                "field": "código",
                "before": "",
                "after": "",
            }
        ],
    )

    assert len(result.applied) == 1
    assert await impl_repo.by_feature_id(feature.id) is None
