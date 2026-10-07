from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from kosmo.contracts.auth import Principal
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import FeatureId, ProjectId, UserId
from kosmo.contracts.sdd.project import Project
from kosmo.infrastructure.api.dependencies.auth import (
    get_principal,
    require_project_owner,
    verify_feature_owner,
)
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


def _make_container(
    projects: dict[str, Project],
    features: dict[str, Feature] | None = None,
) -> MagicMock:
    container = MagicMock()
    container.repos = MagicMock()
    container.repos.projects = _FakeProjectRepo(projects)
    if features is not None:
        container.repos.features = _FakeFeatureRepo(features)
    return container


@pytest.mark.unit
@pytest.mark.asyncio
async def test_require_project_owner_permits_legitimate_owner() -> None:
    # Arrange
    project = Project(
        id=ProjectId("prj_01"),
        name="Mi Proyecto",
        slug="mi-proyecto",
        description="Proyecto propio",
        owner_id=UserId("usr_alice"),
    )
    container = _make_container({"prj_01": project})
    principal = Principal(subject="usr_alice", scopes=frozenset({"*"}))

    # Act
    result = await require_project_owner(container, "prj_01", principal)

    # Assert
    assert result is not None
    assert result.id == ProjectId("prj_01")
    assert str(result.owner_id) == "usr_alice"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_require_project_owner_blocks_cross_tenant_intruder_with_404() -> None:
    # Arrange
    project = Project(
        id=ProjectId("prj_01"),
        name="Proyecto de Alice",
        slug="proyecto-de-alice",
        description="Privado",
        owner_id=UserId("usr_alice"),
    )
    container = _make_container({"prj_01": project})
    intruder = Principal(subject="usr_bob", scopes=frozenset({"*"}))

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await require_project_owner(container, "prj_01", intruder)

    assert exc_info.value.status_code == 404
    assert "no encontrado" in exc_info.value.detail


@pytest.mark.unit
@pytest.mark.asyncio
async def test_require_project_owner_raises_404_for_nonexistent_project() -> None:
    # Arrange
    container = _make_container({})
    principal = Principal(subject="usr_alice", scopes=frozenset({"*"}))

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await require_project_owner(container, "prj_nonexistent", principal)

    assert exc_info.value.status_code == 404
    assert "no encontrado" in exc_info.value.detail


@pytest.mark.unit
@pytest.mark.asyncio
async def test_require_project_owner_raises_500_when_container_lacks_repos() -> None:
    # Arrange
    container = MagicMock(spec=[])  # container sin atributo 'repos'
    principal = Principal(subject="usr_alice", scopes=frozenset({"*"}))

    # Act & Assert — fail-secure: debe levantar 500 y nunca pasar silenciosamente
    with pytest.raises(HTTPException) as exc_info:
        await require_project_owner(container, "prj_01", principal)

    assert exc_info.value.status_code == 500
    assert "no disponible" in exc_info.value.detail


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_feature_owner_raises_500_when_container_lacks_repos() -> None:
    # Arrange
    container = MagicMock(spec=[])
    principal = Principal(subject="usr_alice", scopes=frozenset({"*"}))
    request = MagicMock()
    request.app.state.container = container

    # Act & Assert — fail-secure: debe levantar 500
    with pytest.raises(HTTPException) as exc_info:
        await verify_feature_owner("feat_01", principal, request)

    assert exc_info.value.status_code == 500
    assert "no disponible" in exc_info.value.detail


@pytest.mark.unit
def test_get_project_endpoint_blocks_unauthorized_user() -> None:
    # Arrange
    project = Project(
        id=ProjectId("prj_secure"),
        name="Proyecto Seguro",
        slug="proyecto-seguro",
        description="Confidencial",
        owner_id=UserId("usr_owner"),
    )
    container = _make_container({"prj_secure": project})
    mock_use_case = MagicMock()
    mock_use_case.execute = AsyncMock(return_value=project)
    container.projects = MagicMock()
    container.projects.get_project = mock_use_case

    app.dependency_overrides[get_principal] = lambda: Principal(subject="usr_intruder")
    app.dependency_overrides[get_container] = lambda: container
    app.state.container = container

    try:
        # Act
        client = TestClient(app)
        response = client.get(
            "/api/v1/projects/prj_secure",
            headers={"Authorization": "Bearer mock"},
        )

        # Assert — debe retornar 404 al intruso para no revelar existencia del proyecto
        assert response.status_code == 404
        assert "no encontrado" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
def test_get_project_endpoint_allows_legitimate_owner() -> None:
    # Arrange
    project = Project(
        id=ProjectId("prj_secure"),
        name="Proyecto Seguro",
        slug="proyecto-seguro",
        description="Confidencial",
        owner_id=UserId("usr_owner"),
    )
    container = _make_container({"prj_secure": project})
    mock_use_case = MagicMock()
    mock_use_case.execute = AsyncMock(return_value=project)
    container.projects = MagicMock()
    container.projects.get_project = mock_use_case

    app.dependency_overrides[get_principal] = lambda: Principal(subject="usr_owner")
    app.dependency_overrides[get_container] = lambda: container
    app.state.container = container

    try:
        # Act
        client = TestClient(app)
        response = client.get(
            "/api/v1/projects/prj_secure",
            headers={"Authorization": "Bearer mock"},
        )

        # Assert — el dueño legítimo obtiene 200 con los datos del proyecto
        assert response.status_code == 200
        assert response.json()["id"] == "prj_secure"
        assert response.json()["name"] == "Proyecto Seguro"
        assert response.json()["owner_id"] == "usr_owner"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_feature_owner_permits_legitimate_owner() -> None:
    # Arrange
    project = Project(
        id=ProjectId("prj_01"),
        name="Proyecto de Alice",
        slug="proyecto-de-alice",
        description="Privado",
        owner_id=UserId("usr_alice"),
    )
    feature = Feature(
        id=FeatureId("feat_01"),
        number=1,
        title="Login",
        slug="login",
        description="Feature de login",
        project_id=ProjectId("prj_01"),
    )
    container = _make_container({"prj_01": project}, {"feat_01": feature})
    owner = Principal(subject="usr_alice", scopes=frozenset({"*"}))
    request = MagicMock()
    request.app.state.container = container

    # Act
    result = await verify_feature_owner("feat_01", owner, request)

    # Assert
    assert result is not None
    assert result.id == FeatureId("feat_01")
    assert result.project_id == ProjectId("prj_01")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_feature_owner_blocks_cross_tenant_intruder_with_404() -> None:
    # Arrange
    project = Project(
        id=ProjectId("prj_01"),
        name="Proyecto de Alice",
        slug="proyecto-de-alice",
        description="Privado",
        owner_id=UserId("usr_alice"),
    )
    feature = Feature(
        id=FeatureId("feat_01"),
        number=1,
        title="Login",
        slug="login",
        description="Feature de login",
        project_id=ProjectId("prj_01"),
    )
    container = _make_container({"prj_01": project}, {"feat_01": feature})
    intruder = Principal(subject="usr_bob", scopes=frozenset({"*"}))
    request = MagicMock()
    request.app.state.container = container

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await verify_feature_owner("feat_01", intruder, request)

    assert exc_info.value.status_code == 404
    assert "no encontrado" in exc_info.value.detail


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_feature_owner_raises_404_for_nonexistent_feature() -> None:
    # Arrange
    container = _make_container({}, {})
    principal = Principal(subject="usr_alice", scopes=frozenset({"*"}))
    request = MagicMock()
    request.app.state.container = container

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await verify_feature_owner("feat_missing", principal, request)

    assert exc_info.value.status_code == 404
    assert "no encontrada" in exc_info.value.detail


@pytest.mark.unit
def test_feature_chat_endpoint_blocks_cross_tenant_intruder_with_404() -> None:
    # Arrange
    project = Project(
        id=ProjectId("prj_alice"),
        name="Proyecto de Alice",
        slug="proyecto-de-alice",
        description="Privado",
        owner_id=UserId("usr_alice"),
    )
    feature = Feature(
        id=FeatureId("feat_alice"),
        number=1,
        title="Secreto",
        slug="secreto",
        description="Feature secreta",
        project_id=ProjectId("prj_alice"),
    )
    container = _make_container({"prj_alice": project}, {"feat_alice": feature})

    app.dependency_overrides[get_principal] = lambda: Principal(subject="usr_intruder")
    app.dependency_overrides[get_container] = lambda: container
    app.state.container = container

    try:
        # Act
        client = TestClient(app)
        response = client.get(
            "/api/v1/features/feat_alice/chat/history",
            headers={"Authorization": "Bearer mock"},
        )

        # Assert — debe retornar 404 al intruso para no revelar existencia ni contenido
        assert response.status_code == 404
        assert "no encontrado" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
def test_requirement_chat_endpoint_blocks_cross_tenant_intruder_with_404() -> None:
    # Arrange
    project = Project(
        id=ProjectId("prj_alice"),
        name="Proyecto de Alice",
        slug="proyecto-de-alice",
        description="Privado",
        owner_id=UserId("usr_alice"),
    )
    feature = Feature(
        id=FeatureId("feat_alice"),
        number=1,
        title="Secreto",
        slug="secreto",
        description="Feature secreta",
        project_id=ProjectId("prj_alice"),
    )
    container = _make_container({"prj_alice": project}, {"feat_alice": feature})

    app.dependency_overrides[get_principal] = lambda: Principal(subject="usr_intruder")
    app.dependency_overrides[get_container] = lambda: container
    app.state.container = container

    try:
        # Act
        client = TestClient(app)
        response = client.get(
            "/api/v1/features/feat_alice/requirements/chat/history",
            headers={"Authorization": "Bearer mock"},
        )

        # Assert — debe retornar 404 al intruso para no revelar existencia ni contenido
        assert response.status_code == 404
        assert "no encontrado" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()
