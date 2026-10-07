from __future__ import annotations

import pytest

from kosmo.config import Settings


@pytest.fixture(autouse=True)
def _base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configura variables mínimas para construir Settings."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/kosmo_test")
    monkeypatch.setenv("REDIS_URL", "redis://:test_redis_pass@localhost:6379/1")
    monkeypatch.setenv("LLM_PROVIDER", "noop")
    monkeypatch.setenv("LLM_MODEL", "noop")


@pytest.mark.unit
def test_cors_development_allows_wildcard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")

    settings = Settings(_env_file=None)
    assert settings.parsed_cors_origins == ["*"]


@pytest.mark.unit
def test_cors_development_parses_comma_separated_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000, http://localhost:5173  ")

    settings = Settings(_env_file=None)
    assert settings.parsed_cors_origins == ["http://localhost:3000", "http://localhost:5173"]


@pytest.mark.unit
def test_cors_production_accepts_valid_https_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://app.kosmo.dev, https://api.kosmo.dev")

    settings = Settings(_env_file=None)
    assert settings.parsed_cors_origins == ["https://app.kosmo.dev", "https://api.kosmo.dev"]


@pytest.mark.unit
def test_cors_production_rejects_wildcard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")

    with pytest.raises(ValueError, match="CORS_ALLOWED_ORIGINS no puede ser '\\*'"):
        Settings(_env_file=None)


@pytest.mark.unit
def test_cors_production_rejects_wildcard_mixed_with_domains(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://app.kosmo.dev, *")

    with pytest.raises(ValueError, match="CORS_ALLOWED_ORIGINS no puede ser '\\*'"):
        Settings(_env_file=None)


@pytest.mark.unit
def test_cors_production_rejects_empty_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "   ")

    with pytest.raises(ValueError, match="Debe configurar al menos un origen"):
        Settings(_env_file=None)


@pytest.mark.unit
def test_cors_production_rejects_origin_without_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "app.kosmo.dev")

    with pytest.raises(ValueError, match="Origen CORS inválido 'app.kosmo.dev'"):
        Settings(_env_file=None)


@pytest.mark.unit
def test_cors_default_is_localhost_3000(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "development")
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)

    settings = Settings(_env_file=None)
    assert settings.cors_allowed_origins == "http://localhost:3000"
    assert settings.parsed_cors_origins == ["http://localhost:3000"]


@pytest.mark.unit
def test_cors_middleware_integration() -> None:
    from fastapi.testclient import TestClient

    from kosmo.infrastructure.api.main import app

    client = TestClient(app)
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert response.headers.get("access-control-allow-credentials") == "true"


# ---------------------------------------------------------------------------
# auth_disabled — guard de producción
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_auth_disabled_production_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("AUTH_DISABLED", "true")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://app.kosmo.dev")

    # Act / Assert
    with pytest.raises(ValueError, match="AUTH_DISABLED no puede ser 'true' en entorno de producción"):
        Settings(_env_file=None)


@pytest.mark.unit
def test_auth_disabled_development_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("AUTH_DISABLED", "true")

    # Act
    settings = Settings(_env_file=None)

    # Assert
    assert settings.auth_disabled is True


@pytest.mark.unit
def test_auth_disabled_staging_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.setenv("ENV", "staging")
    monkeypatch.setenv("AUTH_DISABLED", "true")

    # Act
    settings = Settings(_env_file=None)

    # Assert
    assert settings.auth_disabled is True
