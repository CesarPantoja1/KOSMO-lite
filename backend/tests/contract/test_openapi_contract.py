from __future__ import annotations

from collections.abc import Generator
from dataclasses import replace

import pytest
import schemathesis
from fastapi.testclient import TestClient

from kosmo.application.ai.get_ai_catalog import GetAiCatalogUseCase
from kosmo.contracts.ai.catalog import AiCatalogRepository, CatalogModel
from kosmo.contracts.auth import Principal
from kosmo.infrastructure.api.dependencies.ai_config import get_ai_catalog_use_case
from kosmo.infrastructure.api.dependencies.auth import get_principal
from kosmo.infrastructure.api.main import app


class _InMemoryAiCatalogRepository:
    def __init__(self) -> None:
        self._models: dict[tuple[str, str], CatalogModel] = {}

    async def list_active(self, provider: str | None = None) -> list[CatalogModel]:
        return [
            m
            for m in self._models.values()
            if m.is_active and m.opencode_compatible and (provider is None or m.provider == provider)
        ]

    async def get_by_provider_and_model(self, provider: str, model_id: str) -> CatalogModel | None:
        for m in self._models.values():
            if m.provider == provider and (m.model_id == model_id or m.opencode_model_id == model_id):
                return m
        return None

    async def upsert_batch(self, models: list[CatalogModel]) -> None:
        for m in models:
            self._models[(m.provider, m.model_id)] = m

    async def mark_unseen_as_retired(self, provider: str, seen_model_ids: set[str]) -> None:
        for key, m in list(self._models.items()):
            if m.provider == provider and m.model_id not in seen_model_ids:
                self._models[key] = replace(m, is_active=False, is_deprecated=True)


@pytest.fixture(scope="module")
def schema() -> schemathesis.openapi.OpenApiSchema:
    return schemathesis.openapi.from_dict(app.openapi())


@pytest.fixture(scope="module")
def client() -> Generator[TestClient]:
    catalog_repo: AiCatalogRepository = _InMemoryAiCatalogRepository()
    app.dependency_overrides[get_principal] = lambda: Principal(subject="usr_contract")
    app.dependency_overrides[get_ai_catalog_use_case] = lambda: GetAiCatalogUseCase(catalog_repo=catalog_repo)
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_principal, None)
        app.dependency_overrides.pop(get_ai_catalog_use_case, None)


@pytest.mark.contract
def test_openapi_schema_is_structurally_sound() -> None:
    # Arrange & Act
    openapi_doc = app.openapi()

    # Assert
    assert openapi_doc["info"]["title"] == "KOSMO API"
    assert openapi_doc["openapi"].startswith("3.")
    assert len(openapi_doc["paths"]) >= 50

    # Cada path debe definir al menos un método HTTP y respuestas documentadas
    for path, path_item in openapi_doc["paths"].items():
        assert isinstance(path_item, dict), f"Path item {path} no es un diccionario"
        for method, operation in path_item.items():
            if method in {"get", "post", "put", "patch", "delete"}:
                assert "responses" in operation, f"Operacion {method.upper()} {path} no define 'responses'"
                assert len(operation["responses"]) > 0, f"Operacion {method.upper()} {path} tiene 'responses' vacio"


@pytest.mark.contract
def test_health_endpoint_conforms_to_openapi_contract(
    schema: schemathesis.openapi.OpenApiSchema,
    client: TestClient,
) -> None:
    # Arrange
    operation = schema["/health"]["get"]

    # Act
    response = client.get("/health")

    # Assert
    assert response.status_code == 200
    operation.validate_response(response)
    data = response.json()
    assert data == {"status": "ok"}


@pytest.mark.contract
def test_schemas_endpoint_conforms_to_openapi_contract(
    schema: schemathesis.openapi.OpenApiSchema,
    client: TestClient,
) -> None:
    # Arrange
    operation = schema["/api/v1/schemas"]["get"]

    # Act
    response = client.get("/api/v1/schemas")

    # Assert
    assert response.status_code == 200
    operation.validate_response(response)
    data = response.json()
    assert isinstance(data, dict)
    assert "schemas" in data
    assert len(data["schemas"]) > 0


@pytest.mark.contract
def test_schema_by_name_endpoint_conforms_to_openapi_contract(
    schema: schemathesis.openapi.OpenApiSchema,
    client: TestClient,
) -> None:
    # Arrange: Endpoint específico con parámetro de ruta
    operation = schema["/api/v1/schemas/{name}"]["get"]

    # Act 1: Caso exitoso con esquema existente
    response_ok = client.get("/api/v1/schemas/CreateProjectRequest")
    assert response_ok.status_code == 200
    operation.validate_response(response_ok)
    data_ok = response_ok.json()
    assert data_ok["title"] == "CreateProjectRequest"

    # Act 2: Caso 404 con esquema inexistente
    response_404 = client.get("/api/v1/schemas/non_existent_schema_xyz")
    assert response_404.status_code == 404
    operation.validate_response(response_404)


@pytest.mark.contract
def test_ai_config_providers_conforms_to_openapi_contract(
    schema: schemathesis.openapi.OpenApiSchema,
    client: TestClient,
) -> None:
    # Arrange
    operation = schema["/api/v1/ai-config/providers"]["get"]

    # Act
    response = client.get("/api/v1/ai-config/providers")

    # Assert
    assert response.status_code == 200
    operation.validate_response(response)
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "value" in data[0]
    assert "models" in data[0]


@pytest.mark.contract
def test_traceability_navigation_endpoint_conforms_to_openapi_contract(
    schema: schemathesis.openapi.OpenApiSchema,
) -> None:
    # La ruta legacy sigue operativa en tiempo de ejecución pero oculta en OpenAPI
    assert "/api/v1/traceability/{entity_id}/navigation" not in app.openapi()["paths"]

    # Canonical project-nested REST route
    canonical_path = "/api/v1/projects/{project_id}/traceability/{entity_id}/navigation"
    assert canonical_path in schema
    canonical_op = schema[canonical_path]["get"]
    assert canonical_op.tags == ["traceability"]


@pytest.mark.contract
def test_openapi_json_accessible_in_development(client: TestClient) -> None:
    response = client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "KOSMO API"


@pytest.mark.unit
def test_openapi_route_not_found_when_disabled() -> None:
    from fastapi import FastAPI

    prod_app = FastAPI(openapi_url=None)
    with TestClient(prod_app) as prod_client:
        assert prod_client.get("/api/v1/openapi.json").status_code == 404
        assert prod_client.get("/openapi.json").status_code == 404


@pytest.mark.contract
def test_security_headers_present_in_responses(client: TestClient) -> None:
    response = client.get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "accelerometer=()" in response.headers["permissions-policy"]
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
