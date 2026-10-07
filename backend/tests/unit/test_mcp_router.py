"""Tests unitarios para el router MCP de KOSMO.

Verifica que las tools get_requirements y get_activity_diagram retornan
los datos correctos desde los repositorios o errores 404 cuando no existen.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kosmo.contracts.auth import Principal
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import ActivityDiagramId, FeatureId, ProjectId, UserId
from kosmo.contracts.sdd.project import Project
from kosmo.infrastructure.api.dependencies.auth import get_principal
from kosmo.infrastructure.api.routers.mcp import router as mcp_router
from tests.unit.fakes import (
    InMemoryActivityDiagramRepository,
    InMemoryProjectRepository,
    InMemoryRequirementRepository,
)

_DEFAULT_PRINCIPAL = Principal(subject="usr_test")
_UNSET = object()


class _FakeFeatureRepo:
    def __init__(self, features: dict[str, Feature]) -> None:
        self._features = features

    async def by_id(self, feature_id: FeatureId) -> Feature | None:
        return self._features.get(str(feature_id))


def _build_app(
    *,
    requirement_repo: InMemoryRequirementRepository | None = None,
    diagram_repo: InMemoryActivityDiagramRepository | None = None,
    feature_repo: Any | None = None,
    project_repo: Any | None = None,
    principal: Any = _UNSET,
) -> TestClient:
    """Monta una mini-app FastAPI con el router MCP y repositorios fake."""
    app = FastAPI()
    active_principal = _DEFAULT_PRINCIPAL if principal is _UNSET else principal
    if active_principal is not None:
        app.dependency_overrides[get_principal] = lambda: active_principal
    app.include_router(mcp_router)

    req_repo = requirement_repo or InMemoryRequirementRepository()
    dia_repo = diagram_repo or InMemoryActivityDiagramRepository()
    app.state.requirement_repo = req_repo
    app.state.diagram_repo = dia_repo
    if feature_repo is not None:
        app.state.feature_repo = feature_repo
    if project_repo is not None:
        app.state.project_repo = project_repo

    return TestClient(app)


_FEATURE_ID = "feat_01KT01FABRICATED01"
_EARS_MARKDOWN = """\
### REQ-1.1 Registrar gastos

**Ubicuo**

El sistema shall registrar un gasto con monto, fecha y descripción.

**Criterios de aceptación**

**Escenario:** Gasto válido
- **Dado** que el usuario tiene una cuenta activa
- **Cuando** registra un gasto de $50.00
- **Entonces** el sistema almacena el gasto con dos decimales
"""
_PLANTUML = "@startuml\nstart\n:Registrar gasto;\nstop\n@enduml"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_requirements_returns_markdown_for_existing_feature() -> None:
    """Happy path: requisitos existentes se retornan como markdown."""
    # Arrange
    req_repo = InMemoryRequirementRepository()
    await req_repo.save(FeatureId(_FEATURE_ID), _EARS_MARKDOWN)
    client = _build_app(requirement_repo=req_repo)

    # Act
    response = client.post("/mcp/tools/get_requirements", json={"feature_id": _FEATURE_ID})

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["content"] == _EARS_MARKDOWN
    assert body["feature_id"] == _FEATURE_ID


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_activity_diagram_returns_plantuml_for_existing_feature() -> None:
    """Happy path: diagrama existente se retorna como PlantUML syntax."""
    # Arrange
    from kosmo.contracts.sdd.activity_diagram import DiagramaActividad

    diagram_repo = InMemoryActivityDiagramRepository()
    diagram = DiagramaActividad(
        id=ActivityDiagramId("dia_01KT01FABRICATED01"),
        feature_id=FeatureId(_FEATURE_ID),
        diagram_syntax=_PLANTUML,
    )
    await diagram_repo.save(diagram)
    client = _build_app(diagram_repo=diagram_repo)

    # Act
    response = client.post("/mcp/tools/get_activity_diagram", json={"feature_id": _FEATURE_ID})

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["content"] == _PLANTUML
    assert body["feature_id"] == _FEATURE_ID


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_requirements_returns_404_when_feature_has_no_requirements() -> None:
    """Error path: feature sin requisitos retorna 404 con detalle RFC 7807."""
    # Arrange
    client = _build_app()

    # Act
    response = client.post("/mcp/tools/get_requirements", json={"feature_id": _FEATURE_ID})

    # Assert
    assert response.status_code == 404
    body = response.json()
    assert "detail" in body
    assert _FEATURE_ID in body["detail"]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_activity_diagram_returns_404_when_feature_has_no_diagram() -> None:
    """Error path: feature sin diagrama retorna 404 con detalle."""
    # Arrange
    client = _build_app()

    # Act
    response = client.post("/mcp/tools/get_activity_diagram", json={"feature_id": _FEATURE_ID})

    # Assert
    assert response.status_code == 404
    body = response.json()
    assert "detail" in body
    assert _FEATURE_ID in body["detail"]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_requirements_returns_empty_markdown_preserved() -> None:
    """Edge case: markdown vacío pero existente se retorna tal cual."""
    # Arrange
    req_repo = InMemoryRequirementRepository()
    await req_repo.save(FeatureId(_FEATURE_ID), "")
    client = _build_app(requirement_repo=req_repo)

    # Act
    response = client.post("/mcp/tools/get_requirements", json={"feature_id": _FEATURE_ID})

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["content"] == ""
    assert body["feature_id"] == _FEATURE_ID


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_requirements_unauthenticated_returns_401() -> None:
    """Seguridad: petición a get_requirements sin autenticación retorna 401."""
    # Arrange — app sin principal ni credenciales
    client = _build_app(principal=None)

    # Act
    response = client.post("/mcp/tools/get_requirements", json={"feature_id": _FEATURE_ID})

    # Assert
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_activity_diagram_unauthenticated_returns_401() -> None:
    """Seguridad: petición a get_activity_diagram sin autenticación retorna 401."""
    # Arrange — app sin principal ni credenciales
    client = _build_app(principal=None)

    # Act
    response = client.post("/mcp/tools/get_activity_diagram", json={"feature_id": _FEATURE_ID})

    # Assert
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_requirements_cross_user_returns_404() -> None:
    """Seguridad / BOLA: usuario no dueño del proyecto de la característica recibe 404."""
    # Arrange
    req_repo = InMemoryRequirementRepository()
    await req_repo.save(FeatureId(_FEATURE_ID), _EARS_MARKDOWN)

    target_project_id = ProjectId("prj_owner_01")
    feature = Feature(
        id=FeatureId(_FEATURE_ID),
        number=1,
        title="Gastos",
        slug="gastos",
        description="Gestión de gastos",
        project_id=target_project_id,
    )
    feature_repo = _FakeFeatureRepo({_FEATURE_ID: feature})

    project_repo = InMemoryProjectRepository()
    await project_repo.save(
        Project(
            id=target_project_id,
            name="Proyecto Privado",
            slug="proyecto-privado",
            description="Proyecto de prueba",
            owner_id=UserId("usr_legitimate_owner"),
        )
    )

    # Cliente autenticado como usuario intruso
    client = _build_app(
        requirement_repo=req_repo,
        feature_repo=feature_repo,
        project_repo=project_repo,
        principal=Principal(subject="usr_intruder"),
    )

    # Act
    response = client.post("/mcp/tools/get_requirements", json={"feature_id": _FEATURE_ID})

    # Assert
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_activity_diagram_cross_user_returns_404() -> None:
    """Seguridad / BOLA: usuario no dueño del proyecto no puede acceder a diagrama ajeno."""
    # Arrange
    from kosmo.contracts.sdd.activity_diagram import DiagramaActividad

    diagram_repo = InMemoryActivityDiagramRepository()
    await diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("dia_01KT01FABRICATED01"),
            feature_id=FeatureId(_FEATURE_ID),
            diagram_syntax=_PLANTUML,
        )
    )

    target_project_id = ProjectId("prj_owner_01")
    feature = Feature(
        id=FeatureId(_FEATURE_ID),
        number=1,
        title="Gastos",
        slug="gastos",
        description="Gestión de gastos",
        project_id=target_project_id,
    )
    feature_repo = _FakeFeatureRepo({_FEATURE_ID: feature})

    project_repo = InMemoryProjectRepository()
    await project_repo.save(
        Project(
            id=target_project_id,
            name="Proyecto Privado",
            slug="proyecto-privado",
            description="Proyecto de prueba",
            owner_id=UserId("usr_legitimate_owner"),
        )
    )

    # Cliente autenticado como usuario intruso
    client = _build_app(
        diagram_repo=diagram_repo,
        feature_repo=feature_repo,
        project_repo=project_repo,
        principal=Principal(subject="usr_intruder"),
    )

    # Act
    response = client.post("/mcp/tools/get_activity_diagram", json={"feature_id": _FEATURE_ID})

    # Assert
    assert response.status_code == 404
