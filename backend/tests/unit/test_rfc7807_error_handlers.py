"""Tests para exception handlers globales RFC 7807 (Problem Details)."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from kosmo.infrastructure.api.main import app


@pytest.fixture(scope="module")
def client() -> Generator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.mark.unit
def test_validation_error_returns_rfc7807_problem_details(client: TestClient) -> None:
    # Arrange & Act: POST a register sin los campos requeridos
    response = client.post("/api/v1/auth/register", json={})

    # Assert
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"

    data = response.json()
    assert data["type"] == "urn:kosmo:validation:error"
    assert data["title"] == "Error de validación"
    assert data["status"] == 422
    assert isinstance(data["detail"], str)
    assert data["instance"] == "/api/v1/auth/register"
    assert "trace_id" in data
    assert isinstance(data["violations"], list)
    assert len(data["violations"]) > 0

    # Cada violation debe tener loc, msg, input
    violation = data["violations"][0]
    assert "loc" in violation
    assert "msg" in violation
    assert "input" in violation


@pytest.mark.unit
def test_http_exception_returns_rfc7807_problem_details(client: TestClient) -> None:
    # Arrange & Act: Ruta inexistente (404 Not Found)
    response = client.get("/api/v1/non-existent-route-xyz")

    # Assert
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"

    data = response.json()
    assert data["type"] == "urn:kosmo:error:404"
    assert data["title"] == "Not Found"
    assert data["status"] == 404
    assert data["detail"] == "Not Found"
    assert data["instance"] == "/api/v1/non-existent-route-xyz"
    assert "trace_id" in data
    assert data["violations"] == []


@pytest.mark.unit
def test_auth_unauthorized_returns_rfc7807_problem_details(client: TestClient) -> None:
    # Arrange & Act: Endpoint protegido sin header de autorización
    response = client.get("/api/v1/projects")

    # Assert
    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"

    data = response.json()
    assert data["type"] == "urn:kosmo:error:401"
    assert data["status"] == 401
    assert isinstance(data["detail"], str)
    assert data["instance"] == "/api/v1/projects"
    assert "trace_id" in data
    assert data["violations"] == []
