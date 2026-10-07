from __future__ import annotations

import pytest

from kosmo.contracts.sdd.ids import FeatureId
from kosmo.infrastructure.llm.knowledge_tools import (
    build_get_diagram_for_feature,
    build_get_requirements_for_feature,
)
from tests.unit.fakes import (
    InMemoryActivityDiagramRepository,
    InMemoryRequirementRepository,
)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_requirements_returns_markdown() -> None:
    # Arrange
    repo = InMemoryRequirementRepository()
    await repo.save(FeatureId("feat_01"), "### REQ-1.1\n\n**Ubicuo**\n\nEl sistema debe procesar pagos")
    _def, handler = build_get_requirements_for_feature(repo)

    # Act
    result = await handler({"feature_id": "feat_01"})

    # Assert
    assert "REQ-1.1" in result
    assert "procesar pagos" in result


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_requirements_not_found() -> None:
    # Arrange
    repo = InMemoryRequirementRepository()
    _def, handler = build_get_requirements_for_feature(repo)

    # Act
    result = await handler({"feature_id": "feat_missing"})

    # Assert
    assert "no se encontraron" in result.lower()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_requirements_missing_param() -> None:
    # Arrange
    repo = InMemoryRequirementRepository()
    _def, handler = build_get_requirements_for_feature(repo)

    # Act
    result = await handler({})

    # Assert
    assert "feature_id" in result.lower()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_diagram_returns_plantuml() -> None:
    # Arrange
    repo = InMemoryActivityDiagramRepository()
    diagram_syntax = "@startuml\nstart\n:Accion;\nstop\n@enduml"
    from kosmo.contracts.sdd.activity_diagram import DiagramaActividad
    from kosmo.contracts.sdd.ids import ActivityDiagramId

    await repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("dia_01"),
            feature_id=FeatureId("feat_01"),
            diagram_syntax=diagram_syntax,
        )
    )
    _def, handler = build_get_diagram_for_feature(repo)

    # Act
    result = await handler({"feature_id": "feat_01"})

    # Assert
    assert "@startuml" in result
    assert "Accion" in result


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_diagram_not_found() -> None:
    # Arrange
    repo = InMemoryActivityDiagramRepository()
    _def, handler = build_get_diagram_for_feature(repo)

    # Act
    result = await handler({"feature_id": "feat_missing"})

    # Assert
    assert "no se encontro" in result.lower()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_diagram_missing_param() -> None:
    # Arrange
    repo = InMemoryActivityDiagramRepository()
    _def, handler = build_get_diagram_for_feature(repo)

    # Act
    result = await handler({})

    # Assert
    assert "feature_id" in result.lower()


@pytest.mark.unit
def test_principal_has_scopes_matching_and_wildcard() -> None:
    from kosmo.contracts.auth import Principal

    user = Principal(subject="usr_1", scopes=frozenset({"read", "write"}))
    assert not user.has_scopes(frozenset({"admin"}))
    assert user.has_scopes(frozenset({"read"}))

    admin = Principal(subject="usr_admin", scopes=frozenset({"admin"}))
    assert admin.has_scopes(frozenset({"admin"}))

    super_user = Principal(subject="usr_super", scopes=frozenset({"*"}))
    assert super_user.has_scopes(frozenset({"admin"}))
    assert super_user.has_scopes(frozenset({"anything", "custom"}))


@pytest.mark.unit
def test_knowledge_consolidate_endpoint_requires_admin_scope() -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from kosmo.contracts.auth import Principal
    from kosmo.infrastructure.api.dependencies.auth import get_principal
    from kosmo.infrastructure.api.routers.knowledge import router as knowledge_router

    mock_uc = AsyncMock()
    mock_uc.execute.return_value = ["phase_analysis", "phase_synthesis"]

    app = FastAPI()
    app.include_router(knowledge_router)
    app.state.container = SimpleNamespace(pipeline=SimpleNamespace(consolidate_patterns=mock_uc))

    # 1. Unauthenticated request -> 401
    with TestClient(app) as client:
        res_unauth = client.post("/api/v1/knowledge/consolidate")
        assert res_unauth.status_code == 401

    # 2. Authenticated user without admin scope -> 403
    app.dependency_overrides[get_principal] = lambda: Principal(
        subject="usr_standard", scopes=frozenset({"read", "write"})
    )
    with TestClient(app) as client:
        res_forbidden = client.post("/api/v1/knowledge/consolidate")
        assert res_forbidden.status_code == 403
        assert "Insufficient scope" in res_forbidden.json()["detail"]

    # 3. Authenticated user with admin scope -> 200
    app.dependency_overrides[get_principal] = lambda: Principal(subject="usr_admin", scopes=frozenset({"admin"}))
    with TestClient(app) as client:
        res_admin = client.post("/api/v1/knowledge/consolidate")
        assert res_admin.status_code == 200
        assert res_admin.json() == {"phases": ["phase_analysis", "phase_synthesis"]}

    # 4. Authenticated user with wildcard scope (*) -> 200
    app.dependency_overrides[get_principal] = lambda: Principal(subject="usr_super", scopes=frozenset({"*"}))
    with TestClient(app) as client:
        res_wildcard = client.post("/api/v1/knowledge/consolidate")
        assert res_wildcard.status_code == 200

    app.dependency_overrides.clear()
