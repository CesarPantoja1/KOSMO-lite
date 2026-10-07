from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from kosmo.contracts.auth import Principal
from kosmo.contracts.sdd.codegen import FeatureImplementation, FeatureImplementationStatus
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import FeatureId, ImplementationId, ProjectId, UserId
from kosmo.contracts.sdd.project import Project
from kosmo.infrastructure.api.dependencies.auth import get_principal
from kosmo.infrastructure.api.dependencies.container import get_container
from kosmo.infrastructure.api.main import app


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


class _FakeImplementationRepo:
    def __init__(self, implementations: dict[str, FeatureImplementation]) -> None:
        self._implementations = implementations

    async def by_id(self, impl_id: ImplementationId) -> FeatureImplementation | None:
        return self._implementations.get(str(impl_id))

    async def by_feature_id(self, feature_id: FeatureId) -> FeatureImplementation | None:
        for impl in self._implementations.values():
            if str(impl.feature_id) == str(feature_id):
                return impl
        return None


@pytest.fixture
def idor_client() -> Generator[TestClient]:
    now = datetime.now(UTC)
    alice_project = Project(
        id=ProjectId("prj_alice"),
        name="Proyecto de Alice",
        slug="proyecto-alice",
        description="Privado de Alice",
        owner_id=UserId("usr_alice"),
    )
    alice_feature = Feature(
        id=FeatureId("feat_alice"),
        number=1,
        title="Feature de Alice",
        slug="feature-alice",
        description="Privada",
        project_id=ProjectId("prj_alice"),
    )
    alice_impl = FeatureImplementation(
        id=ImplementationId("impl_alice"),
        feature_id=FeatureId("feat_alice"),
        project_id=ProjectId("prj_alice"),
        status=FeatureImplementationStatus.IMPLEMENTED,
        generated_files=["src/app.tsx"],
        created_at=now,
        updated_at=now,
    )

    from kosmo.application.codegen.get_implementation_record import GetImplementationRecordUseCase

    container = MagicMock()
    container.repos = MagicMock()
    container.repos.projects = _FakeProjectRepo({"prj_alice": alice_project})
    container.repos.features = _FakeFeatureRepo({"feat_alice": alice_feature})
    container.repos.implementations = _FakeImplementationRepo({"impl_alice": alice_impl})
    container.codegen = MagicMock()
    container.codegen.get_implementation_record = GetImplementationRecordUseCase(
        implementation_repo=container.repos.implementations,
        requirement_repo=None,
        traceability_repo=None,
    )

    # Intruso con token autenticado valido pero diferente identidad
    intruder = Principal(subject="usr_bob", scopes=frozenset({"*"}))

    app.dependency_overrides[get_principal] = lambda: intruder
    app.dependency_overrides[get_container] = lambda: container
    app.state.container = container

    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


# =========================================================================
# 1. CHAT SESSIONS IDOR TESTS
# =========================================================================


@pytest.mark.unit
@pytest.mark.idor
def test_idor_chat_sessions_list_blocks_intruder(idor_client: TestClient) -> None:
    # Act: Intruso intenta listar sesiones de chat de Alice
    response = idor_client.get(
        "/api/v1/projects/prj_alice/chat-sessions?phase=discovery",
        headers={"Authorization": "Bearer mock"},
    )
    # Assert: 404 para no filtrar informacion de existencia
    assert response.status_code == 404
    assert "no encontrado" in response.json()["detail"]


@pytest.mark.unit
@pytest.mark.idor
def test_idor_chat_sessions_create_blocks_intruder(idor_client: TestClient) -> None:
    # Act: Intruso intenta crear una sesion en el proyecto de Alice
    response = idor_client.post(
        "/api/v1/projects/prj_alice/chat-sessions",
        json={"phase": "discovery"},
        headers={"Authorization": "Bearer mock"},
    )
    # Assert
    assert response.status_code == 404
    assert "no encontrado" in response.json()["detail"]


@pytest.mark.unit
@pytest.mark.idor
def test_idor_chat_sessions_delete_blocks_intruder(idor_client: TestClient) -> None:
    # Act: Intruso intenta eliminar una sesion de chat de Alice
    response = idor_client.delete(
        "/api/v1/projects/prj_alice/chat-sessions/cht_secret",
        headers={"Authorization": "Bearer mock"},
    )
    # Assert
    assert response.status_code == 404
    assert "no encontrado" in response.json()["detail"]


# =========================================================================
# 2. CONSISTENCY EVALUATIONS IDOR TESTS
# =========================================================================


@pytest.mark.unit
@pytest.mark.idor
def test_idor_consistency_evaluate_blocks_intruder(idor_client: TestClient) -> None:
    # Act: Intruso intenta disparar evaluacion de consistencia en proyecto de Alice
    response = idor_client.post(
        "/api/v1/projects/prj_alice/consistency/evaluate",
        json={"source_phase": "features", "target_phase": "requirements"},
        headers={"Authorization": "Bearer mock"},
    )
    # Assert
    assert response.status_code == 404
    assert "no encontrado" in response.json()["detail"]


@pytest.mark.unit
@pytest.mark.idor
def test_idor_consistency_status_blocks_intruder(idor_client: TestClient) -> None:
    # Act: Intruso intenta consultar estado de consistencia de Alice
    response = idor_client.get(
        "/api/v1/projects/prj_alice/consistency/status",
        headers={"Authorization": "Bearer mock"},
    )
    # Assert
    assert response.status_code == 404
    assert "no encontrado" in response.json()["detail"]


@pytest.mark.unit
@pytest.mark.idor
def test_idor_consistency_apply_blocks_intruder(idor_client: TestClient) -> None:
    # Act: Intruso intenta aplicar impactos de consistencia en proyecto de Alice
    response = idor_client.post(
        "/api/v1/projects/prj_alice/consistency/apply",
        json={"evaluation_id": "cev_123"},
        headers={"Authorization": "Bearer mock"},
    )
    # Assert
    assert response.status_code == 404
    assert "no encontrado" in response.json()["detail"]


# =========================================================================
# 3. DEPLOYMENTS IDOR TESTS
# =========================================================================


@pytest.mark.unit
@pytest.mark.idor
def test_idor_deploy_get_status_blocks_intruder(idor_client: TestClient) -> None:
    # Act: Intruso consulta estado de despliegue de Alice
    response = idor_client.get(
        "/api/v1/projects/prj_alice/deploy",
        headers={"Authorization": "Bearer mock"},
    )
    # Assert
    assert response.status_code == 404
    assert "no encontrado" in response.json()["detail"]


@pytest.mark.unit
@pytest.mark.idor
def test_idor_deploy_post_blocks_intruder(idor_client: TestClient) -> None:
    # Act: Intruso intenta disparar despliegue en proyecto de Alice
    response = idor_client.post(
        "/api/v1/projects/prj_alice/deploy/railway",
        json={"service_name": "malicious-service"},
        headers={"Authorization": "Bearer mock"},
    )
    # Assert
    assert response.status_code == 404
    assert "no encontrado" in response.json()["detail"]


# =========================================================================
# 4. DIRECT DOCUMENT MODIFICATION IDOR TESTS
# =========================================================================


@pytest.mark.unit
@pytest.mark.idor
def test_idor_document_modify_direct_discovery_blocks_intruder(idor_client: TestClient) -> None:
    # Act: Intruso intenta modificar el documento de descubrimiento de Alice
    response = idor_client.post(
        "/api/v1/documents/modify-direct",
        json={
            "document_type": "discovery",
            "document_id": "prj_alice",
            "instruction": "Cambia la mision del producto",
        },
        headers={"Authorization": "Bearer mock"},
    )
    # Assert
    assert response.status_code == 404
    assert "no encontrado" in response.json()["detail"]


@pytest.mark.unit
@pytest.mark.idor
def test_idor_document_modify_direct_feature_blocks_intruder(idor_client: TestClient) -> None:
    # Act: Intruso intenta modificar caracteristica de Alice
    response = idor_client.post(
        "/api/v1/documents/modify-direct",
        json={
            "document_type": "features",
            "document_id": "feat_alice",
            "instruction": "Cambia el titulo de la caracteristica",
        },
        headers={"Authorization": "Bearer mock"},
    )
    # Assert
    assert response.status_code == 404
    assert "no encontrado" in response.json()["detail"]


# =========================================================================
# 5. IMPLEMENTATIONS IDOR TESTS
# =========================================================================


@pytest.mark.unit
@pytest.mark.idor
def test_idor_start_implementation_blocks_intruder(idor_client: TestClient) -> None:
    # Act: Intruso intenta iniciar implementacion de caracteristica de Alice
    response = idor_client.post(
        "/api/v1/implementations",
        json={"feature_id": "feat_alice"},
        headers={"Authorization": "Bearer mock"},
    )
    # Assert
    assert response.status_code == 404
    assert "no encontrado" in response.json()["detail"]


@pytest.mark.unit
@pytest.mark.idor
def test_idor_get_implementation_by_feature_blocks_intruder(idor_client: TestClient) -> None:
    # Act: Intruso intenta leer implementacion de caracteristica de Alice
    response = idor_client.get(
        "/api/v1/implementations?feature_id=feat_alice",
        headers={"Authorization": "Bearer mock"},
    )
    # Assert
    assert response.status_code == 404
    assert "no encontrado" in response.json()["detail"]


@pytest.mark.unit
@pytest.mark.idor
def test_idor_get_implementation_file_content_blocks_intruder(idor_client: TestClient) -> None:
    # Act: Intruso intenta leer archivo generado de Alice
    response = idor_client.get(
        "/api/v1/implementations/impl_alice/files/content?path=src/app.tsx",
        headers={"Authorization": "Bearer mock"},
    )
    # Assert
    assert response.status_code == 404
    assert "no encontrado" in response.json()["detail"]


# =========================================================================
# 6. REQUIREMENTS AND MODEL IDOR TESTS
# =========================================================================


@pytest.mark.unit
@pytest.mark.idor
def test_idor_get_requirements_blocks_intruder(idor_client: TestClient) -> None:
    # Act: Intruso intenta obtener requisitos de Alice
    response = idor_client.get(
        "/api/v1/features/feat_alice/requirements?project_id=prj_alice",
        headers={"Authorization": "Bearer mock"},
    )
    # Assert
    assert response.status_code == 404
    assert "no encontrado" in response.json()["detail"]


@pytest.mark.unit
@pytest.mark.idor
def test_idor_get_model_diagram_blocks_intruder(idor_client: TestClient) -> None:
    # Act: Intruso intenta obtener diagrama de modelo de Alice
    response = idor_client.get(
        "/api/v1/features/feat_alice/diagram?project_id=prj_alice",
        headers={"Authorization": "Bearer mock"},
    )
    # Assert
    assert response.status_code == 404
    assert "no encontrado" in response.json()["detail"]
