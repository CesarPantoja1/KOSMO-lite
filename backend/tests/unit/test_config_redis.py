from __future__ import annotations

import pytest

from kosmo.config import Settings


@pytest.fixture(autouse=True)
def _base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/kosmo_test")
    monkeypatch.setenv("LLM_PROVIDER", "noop")
    monkeypatch.setenv("LLM_MODEL", "noop")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://app.kosmo.dev")


@pytest.mark.unit
def test_redis_production_requires_authentication(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    with pytest.raises(ValueError, match="REDIS_URL debe incluir contraseña de autenticación"):
        Settings(_env_file=None)


@pytest.mark.unit
def test_redis_production_accepts_authenticated_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("REDIS_URL", "redis://:securepassword@redis:6379/0")

    settings = Settings(_env_file=None)
    assert settings.redis_url is not None
    assert settings.redis_url.get_secret_value() == "redis://:securepassword@redis:6379/0"


@pytest.mark.unit
def test_redis_development_allows_unauthenticated_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    settings = Settings(_env_file=None)
    assert settings.redis_url is not None
    assert settings.redis_url.get_secret_value() == "redis://localhost:6379/0"
