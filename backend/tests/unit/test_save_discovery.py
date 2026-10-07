from typing import Any

import pytest

from kosmo.application.discovery.save_discovery import (
    SaveDiscoveryInput,
    SaveDiscoveryOutput,
    SaveDiscoveryUseCase,
)
from kosmo.contracts.sdd.document import DocumentNode, RichTextDocument, SectionHeading
from kosmo.contracts.sdd.ids import ProjectId
from tests.unit.fakes import InMemoryDocumentRepository, InMemoryOutbox


def _make_discovery_document(title: str = "Test Discovery") -> RichTextDocument:
    return RichTextDocument(
        nodes=[
            DocumentNode(
                type="heading",
                heading=SectionHeading(text=title, level=2, slug="test"),
                content="Contenido de prueba",
            ),
        ]
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_save_discovery_persists_document() -> None:
    # Arrange
    repository: Any = InMemoryDocumentRepository()
    use_case = SaveDiscoveryUseCase(document_repo=repository)
    project_id = ProjectId("prj_discovery123")
    doc = _make_discovery_document()

    # Act
    await use_case.execute(SaveDiscoveryInput(project_id=project_id, document=doc))

    # Assert
    saved = await repository.get_discovery(project_id)
    assert saved is not None
    assert saved.nodes[0].heading is not None
    assert saved.nodes[0].heading.text == "Test Discovery"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_save_discovery_returns_saved_document() -> None:
    # Arrange
    repository: Any = InMemoryDocumentRepository()
    use_case = SaveDiscoveryUseCase(document_repo=repository)
    project_id = ProjectId("prj_discovery456")
    doc = _make_discovery_document("Nuevo Documento")

    # Act
    result = await use_case.execute(SaveDiscoveryInput(project_id=project_id, document=doc))

    # Assert
    assert isinstance(result, SaveDiscoveryOutput)
    assert result.project_id == project_id
    assert result.document.nodes[0].heading is not None
    assert result.document.nodes[0].heading.text == "Nuevo Documento"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_save_discovery_overwrites_existing_document() -> None:
    # Arrange
    repository: Any = InMemoryDocumentRepository()
    use_case = SaveDiscoveryUseCase(document_repo=repository)
    project_id = ProjectId("prj_overwrite")

    doc1 = _make_discovery_document("Primera Versión")
    doc2 = _make_discovery_document("Segunda Versión")

    # Act
    await use_case.execute(SaveDiscoveryInput(project_id=project_id, document=doc1))
    await use_case.execute(SaveDiscoveryInput(project_id=project_id, document=doc2))

    # Assert
    saved = await repository.get_discovery(project_id)
    assert saved is not None
    assert saved.nodes[0].heading is not None
    assert saved.nodes[0].heading.text == "Segunda Versión"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_save_discovery_enqueues_downstream_evaluation() -> None:
    # Arrange
    repository: Any = InMemoryDocumentRepository()
    outbox = InMemoryOutbox()
    use_case = SaveDiscoveryUseCase(document_repo=repository, outbox=outbox)
    project_id = ProjectId("prj_chain")

    # Act
    await use_case.execute(SaveDiscoveryInput(project_id=project_id, document=_make_discovery_document()))

    # Assert — editar Descubrimiento dispara la verificación de todas las fases a la derecha
    assert len(outbox.jobs) == 1
    job_type, payload = outbox.jobs[0]
    assert job_type == "consistency_evaluate"
    assert payload["project_id"] == "prj_chain"
    assert payload["source_phase"] == "descubrimiento"
    assert len(payload["changes"]) == 1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_save_discovery_computes_real_diff_from_previous_version() -> None:
    # Arrange
    repository = InMemoryDocumentRepository()
    outbox = InMemoryOutbox()
    use_case = SaveDiscoveryUseCase(document_repo=repository, outbox=outbox)
    project_id = ProjectId("prj_diff_real")

    doc_v1 = RichTextDocument(
        nodes=[
            DocumentNode(
                type="heading",
                heading=SectionHeading(text="Actores", level=2, slug="actores"),
                content="- Administrador: Gestiona el sistema.",
            ),
        ]
    )
    doc_v2 = RichTextDocument(
        nodes=[
            DocumentNode(
                type="heading",
                heading=SectionHeading(text="Actores", level=2, slug="actores"),
                content="- Jefe: Gestiona el sistema.",
            ),
        ]
    )

    # Act: primer guardado (creación)
    await use_case.execute(SaveDiscoveryInput(project_id=project_id, document=doc_v1))
    outbox.jobs.clear()

    # Segundo guardado (modificación de actor Administrador -> Jefe)
    await use_case.execute(SaveDiscoveryInput(project_id=project_id, document=doc_v2))

    # Assert: el segundo guardado debe incluir un diff real con before y after no vacíos
    assert len(outbox.jobs) == 1
    _, payload = outbox.jobs[0]
    changes = payload["changes"]
    assert len(changes) >= 1
    actor_change = next((c for c in changes if "Administrador" in c.get("before", "")), None)
    assert actor_change is not None, "El diff debe incluir el texto anterior (Administrador)"
    assert "Jefe" in actor_change["after"], "El diff debe incluir el texto nuevo (Jefe)"
