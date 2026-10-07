from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, Request

from kosmo.application.chat.process_chat_modification import (
    ProcessChatModificationOutput,
    ProcessChatModificationUseCase,
)
from kosmo.contracts.auth import Principal
from kosmo.contracts.sdd.errors import DocumentNotFoundError, FeatureNotFoundError, LLMInvocationError
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import FeatureId, ProjectId, UserId
from kosmo.contracts.sdd.project import Project
from kosmo.infrastructure.api.routers.documents import modify_document_direct
from kosmo.infrastructure.api.schemas import DocumentModifyRequestView


class _FakeProjectRepo:
    def __init__(self, projects: dict[str, Project]) -> None:
        self._projects = projects

    async def by_id(self, project_id: ProjectId) -> Project | None:
        return self._projects.get(str(project_id))


class _FakeFeatureRepo:
    def __init__(self, features: dict[str, Feature]) -> None:
        self._features = features

    async def by_id(self, feature_id: FeatureId) -> Feature | None:
        return self._features.get(str(feature_id))


def _make_container(projects: dict[str, Project], features: dict[str, Feature] | None = None) -> MagicMock:
    container = MagicMock()
    container.repos = MagicMock()
    container.repos.projects = _FakeProjectRepo(projects)
    if features is not None:
        container.repos.features = _FakeFeatureRepo(features)
    return container


def _dummy_request(
    projects: dict[str, Project] | None = None,
    features: dict[str, Feature] | None = None,
) -> MagicMock:
    req = MagicMock(spec=Request)
    if projects is None:
        projects = {
            "prj_01": Project(
                id=ProjectId("prj_01"),
                name="Prj 01",
                slug="prj-01",
                description="Desc",
                owner_id=UserId("usr_test123"),
            )
        }
    if features is None:
        features = {
            "feat_01": Feature(
                id=FeatureId("feat_01"),
                number=1,
                title="Feat 01",
                slug="feat-01",
                description="Desc",
                project_id=ProjectId("prj_01"),
            )
        }
    req.app = MagicMock()
    req.app.state.container = _make_container(projects, features)
    req.state.project_id = None
    return req


def _principal() -> Principal:
    return Principal(subject="usr_test123", scopes=frozenset({"*"}))


def _make_mock_uc(output: ProcessChatModificationOutput | None = None, exc: Exception | None = None) -> MagicMock:
    uc = MagicMock(spec=ProcessChatModificationUseCase)
    if exc:
        uc.execute = AsyncMock(side_effect=exc)
    else:
        uc.execute = AsyncMock(return_value=output)
    return uc


@pytest.mark.unit
@pytest.mark.asyncio
async def test_modify_direct_discovery_success_200() -> None:
    uc = _make_mock_uc(
        output=ProcessChatModificationOutput(
            success=True,
            modified_document="# Vision Actualizada\n\nContenido modificado",
            modified_section="1 Vision General",
            change_description="Se actualizo la vision",
        )
    )
    body = DocumentModifyRequestView(
        document_type="discovery",
        document_id="prj_01",
        instruction="Actualiza la vision del producto",
    )

    response = await modify_document_direct(_dummy_request(), _principal(), body, uc)

    assert response.document_id == "prj_01"
    assert response.content == "# Vision Actualizada\n\nContenido modificado"
    assert response.highlighted_section == "1 Vision General"
    assert "1 Vision General" in response.message


@pytest.mark.unit
@pytest.mark.asyncio
async def test_modify_direct_feature_success_200() -> None:
    uc = _make_mock_uc(
        output=ProcessChatModificationOutput(
            success=True,
            modified_document="Nuevo Titulo Feature",
            modified_section="title",
            change_description="Cambio de titulo",
        )
    )
    body = DocumentModifyRequestView(
        document_type="features",
        document_id="feat_01",
        instruction="Cambia el titulo a Nuevo Titulo Feature",
    )

    response = await modify_document_direct(_dummy_request(), _principal(), body, uc)

    assert response.document_id == "feat_01"
    assert response.content == "Nuevo Titulo Feature"
    assert response.highlighted_section == "title"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_modify_direct_ambiguous_instruction_raises_400() -> None:
    uc = _make_mock_uc(
        output=ProcessChatModificationOutput(
            success=False,
            clarification_message="Por favor especifica que seccion deseas cambiar.",
        )
    )
    body = DocumentModifyRequestView(
        document_type="discovery",
        document_id="prj_01",
        instruction="Cambia eso",
    )

    with pytest.raises(HTTPException) as exc_info:
        await modify_document_direct(_dummy_request(), _principal(), body, uc)

    assert exc_info.value.status_code == 400
    assert "Por favor especifica que seccion deseas cambiar." in exc_info.value.detail


@pytest.mark.unit
@pytest.mark.asyncio
async def test_modify_direct_not_found_raises_404() -> None:
    uc = _make_mock_uc(exc=DocumentNotFoundError(document_type="descubrimiento"))
    body = DocumentModifyRequestView(
        document_type="discovery",
        document_id="prj_missing",
        instruction="Cambia la vision",
    )

    with pytest.raises(HTTPException) as exc_info:
        await modify_document_direct(_dummy_request(), _principal(), body, uc)

    assert exc_info.value.status_code == 404


@pytest.mark.unit
@pytest.mark.asyncio
async def test_modify_direct_feature_not_found_raises_404() -> None:
    uc = _make_mock_uc(exc=FeatureNotFoundError(feature_id="feat_missing"))
    body = DocumentModifyRequestView(
        document_type="features",
        document_id="feat_missing",
        instruction="Cambia el titulo",
    )

    with pytest.raises(HTTPException) as exc_info:
        await modify_document_direct(_dummy_request(), _principal(), body, uc)

    assert exc_info.value.status_code == 404


@pytest.mark.unit
@pytest.mark.asyncio
async def test_modify_direct_llm_error_raises_502() -> None:
    uc = _make_mock_uc(exc=LLMInvocationError(detail="Timeout en LLM"))
    body = DocumentModifyRequestView(
        document_type="requirements",
        document_id="feat_01",
        instruction="Agrega un requisito EARS",
    )

    with pytest.raises(HTTPException) as exc_info:
        await modify_document_direct(_dummy_request(), _principal(), body, uc)

    assert exc_info.value.status_code == 502


@pytest.mark.unit
@pytest.mark.asyncio
async def test_revert_document_enqueues_downstream_evaluation() -> None:
    # Arrange
    from kosmo.application.discovery.revert_document import revert_to_version
    from kosmo.contracts.sdd.ids import ProjectId
    from tests.unit.fakes import InMemoryDocumentRepository, InMemoryOutbox

    document_repo = InMemoryDocumentRepository()
    document_repo.versions["v1"] = "## Visión\n\nVisión antigua."
    outbox = InMemoryOutbox()

    # Act
    result = await revert_to_version(
        document_repo,
        ProjectId("prj_revert"),
        "v1",
        outbox=outbox,
    )

    # Assert — revertir el Descubrimiento dispara la verificación de las fases a la derecha
    assert result is not None
    assert len(outbox.jobs) == 1
    job_type, payload = outbox.jobs[0]
    assert job_type == "consistency_evaluate"
    assert payload["project_id"] == "prj_revert"
    assert payload["source_phase"] == "descubrimiento"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_modify_direct_raises_500_when_app_is_none() -> None:
    req = MagicMock(spec=Request)
    req.app = None
    body = DocumentModifyRequestView(
        document_type="discovery",
        document_id="prj_01",
        instruction="Actualiza la vision",
    )
    uc = _make_mock_uc()
    with pytest.raises(HTTPException) as exc_info:
        await modify_document_direct(req, _principal(), body, uc)

    assert exc_info.value.status_code == 500
    assert "contenedor de dependencias no disponible" in exc_info.value.detail


@pytest.mark.unit
@pytest.mark.asyncio
async def test_modify_direct_raises_500_when_container_is_none() -> None:
    req = MagicMock(spec=Request)
    req.app.state.container = None
    body = DocumentModifyRequestView(
        document_type="discovery",
        document_id="prj_01",
        instruction="Actualiza la vision",
    )
    uc = _make_mock_uc()
    with pytest.raises(HTTPException) as exc_info:
        await modify_document_direct(req, _principal(), body, uc)

    assert exc_info.value.status_code == 500
    assert "contenedor de dependencias no disponible" in exc_info.value.detail


@pytest.mark.unit
@pytest.mark.asyncio
async def test_modify_direct_discovery_blocks_cross_tenant_intruder_with_404() -> None:
    # Arrange
    project = Project(
        id=ProjectId("prj_alice"),
        name="Proyecto Alice",
        slug="proyecto-alice",
        description="Privado",
        owner_id=UserId("usr_alice"),
    )
    container = _make_container({"prj_alice": project})
    request = MagicMock()
    request.app.state.container = container

    uc = _make_mock_uc()
    body = DocumentModifyRequestView(
        document_type="discovery",
        document_id="prj_alice",
        instruction="Actualiza la visión",
    )
    intruder = Principal(subject="usr_bob", scopes=frozenset({"*"}))

    # Act & Assert — el intruso recibe 404
    with pytest.raises(HTTPException) as exc_info:
        await modify_document_direct(request, intruder, body, uc)

    assert exc_info.value.status_code == 404
    assert "no encontrado" in exc_info.value.detail


@pytest.mark.unit
@pytest.mark.asyncio
async def test_modify_direct_feature_blocks_cross_tenant_intruder_with_404() -> None:
    # Arrange
    project = Project(
        id=ProjectId("prj_alice"),
        name="Proyecto Alice",
        slug="proyecto-alice",
        description="Privado",
        owner_id=UserId("usr_alice"),
    )
    feature = Feature(
        id=FeatureId("feat_alice"),
        number=1,
        title="Feature Privada",
        slug="feature-privada",
        description="Solo Alice",
        project_id=ProjectId("prj_alice"),
    )
    container = _make_container({"prj_alice": project}, {"feat_alice": feature})
    request = MagicMock()
    request.app.state.container = container

    uc = _make_mock_uc()
    body = DocumentModifyRequestView(
        document_type="features",
        document_id="feat_alice",
        instruction="Cambia el título",
    )
    intruder = Principal(subject="usr_bob", scopes=frozenset({"*"}))

    # Act & Assert — el intruso recibe 404
    with pytest.raises(HTTPException) as exc_info:
        await modify_document_direct(request, intruder, body, uc)

    assert exc_info.value.status_code == 404
    assert "no encontrado" in exc_info.value.detail


@pytest.mark.unit
@pytest.mark.asyncio
async def test_modify_direct_discovery_permits_legitimate_owner() -> None:
    # Arrange
    project = Project(
        id=ProjectId("prj_alice"),
        name="Proyecto Alice",
        slug="proyecto-alice",
        description="Privado",
        owner_id=UserId("usr_alice"),
    )
    container = _make_container({"prj_alice": project})
    request = MagicMock()
    request.app.state.container = container

    uc = _make_mock_uc(
        output=ProcessChatModificationOutput(
            success=True,
            modified_document="# Nueva Visión",
            modified_section="Visión",
            change_description="Actualizada",
        )
    )
    body = DocumentModifyRequestView(
        document_type="discovery",
        document_id="prj_alice",
        instruction="Actualiza la visión",
    )
    owner = Principal(subject="usr_alice", scopes=frozenset({"*"}))

    # Act — el dueño legítimo modifica exitosamente
    response = await modify_document_direct(request, owner, body, uc)

    # Assert
    assert response.document_id == "prj_alice"
    assert response.content == "# Nueva Visión"
