from __future__ import annotations

import pytest

from kosmo.application.codegen.analyze_feature_integration import (
    AnalyzeFeatureIntegrationInput,
    AnalyzeFeatureIntegrationUseCase,
)
from kosmo.contracts.sdd.codegen import FeatureImplementation, FeatureImplementationStatus
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import FeatureId, ImplementationId, ProjectId
from kosmo.contracts.sdd.product_map import ImplementationDisposition
from kosmo.domain.sdd.document_converters import markdown_to_document
from tests.unit.fakes import (
    InMemoryDocumentRepository,
    InMemoryFeatureImplementationRepository,
    InMemoryFeatureRepository,
)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_analyze_feature_integration_empty_project() -> None:
    # Arrange
    feature_repo = InMemoryFeatureRepository()
    use_case = AnalyzeFeatureIntegrationUseCase(feature_repo=feature_repo)
    p_id = ProjectId("prj_empty")

    # Act
    pmap = await use_case.execute(AnalyzeFeatureIntegrationInput(project_id=p_id))

    # Assert
    assert pmap.project_id == p_id
    assert len(pmap.entities) == 0
    assert len(pmap.actors) == 0


@pytest.mark.asyncio
@pytest.mark.unit
async def test_analyze_feature_integration_with_features() -> None:
    # Arrange
    feature_repo = InMemoryFeatureRepository()
    impl_repo = InMemoryFeatureImplementationRepository()
    doc_repo = InMemoryDocumentRepository()
    p_id = ProjectId("prj_clinic")

    f1 = Feature(
        id=FeatureId("feat_01"),
        number=1,
        title="Reservar cita",
        slug="reservar-cita",
        description="El paciente reserva una cita médica.",
        project_id=p_id,
        origin="Actores: Paciente",
    )
    f2 = Feature(
        id=FeatureId("feat_02"),
        number=2,
        title="Aceptar terminos y condiciones",
        slug="aceptar-terminos",
        description="Aceptar terminos y condiciones del servicio.",
        project_id=p_id,
        origin="Actores: Paciente",
    )
    await feature_repo.save(f1)
    await feature_repo.save(f2)

    # Feature 1 is already implemented
    await impl_repo.save(
        FeatureImplementation(
            id=ImplementationId("impl_01"),
            feature_id=f1.id,
            project_id=p_id,
            status=FeatureImplementationStatus.IMPLEMENTED,
        )
    )

    use_case = AnalyzeFeatureIntegrationUseCase(
        feature_repo=feature_repo,
        document_repo=doc_repo,
        implementation_repo=impl_repo,
    )

    # Act
    pmap = await use_case.execute(AnalyzeFeatureIntegrationInput(project_id=p_id, current_feature_id=f2.id))

    # Assert
    assert pmap.project_id == p_id
    assert len(pmap.actors) >= 1
    # f2 should be classified as INTEGRATE because it is terms & conditions for already implemented f1
    disp_f2 = pmap.get_disposition("feat_02")
    assert disp_f2.disposition == ImplementationDisposition.INTEGRATE
    assert disp_f2.target_feature_id == "feat_01"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_analyze_feature_integration_with_discovery_actors() -> None:
    # Arrange
    feature_repo = InMemoryFeatureRepository()
    doc_repo = InMemoryDocumentRepository()
    p_id = ProjectId("prj_doc_actors")

    discovery_md = """# Visión del Sistema
## Actores
- Supervisor: Monitorea las operaciones
- Operador: Registra incidentes diarios
## Requisitos
Algo
"""
    await doc_repo.save_discovery(p_id, markdown_to_document(discovery_md))

    f1 = Feature(
        id=FeatureId("feat_incidents"),
        number=1,
        title="Registrar incidente",
        slug="registrar-incidente",
        description="El operador registra incidentes y el supervisor los aprueba.",
        project_id=p_id,
    )
    await feature_repo.save(f1)

    use_case = AnalyzeFeatureIntegrationUseCase(
        feature_repo=feature_repo,
        document_repo=doc_repo,
    )

    # Act
    pmap = await use_case.execute(AnalyzeFeatureIntegrationInput(project_id=p_id))

    # Assert
    actor_names = {a.name for a in pmap.actors}
    assert "Supervisor" in actor_names
    assert "Operador" in actor_names

    disp = pmap.get_disposition("feat_incidents")
    assert "Supervisor" in disp.actors
    assert "Operador" in disp.actors
