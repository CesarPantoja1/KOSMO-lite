from __future__ import annotations

import pytest

from kosmo.config import Settings


@pytest.fixture(autouse=True)
def _base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("AUTH_DISABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/kosmo_test")
    monkeypatch.setenv("LLM_PROVIDER", "noop")
    monkeypatch.setenv("LLM_MODEL", "noop")


@pytest.mark.unit
def test_concurrency_settings_defaults_for_50_byok_users() -> None:
    settings = Settings(_env_file=None)

    assert settings.db_pool_size == 60
    assert settings.db_max_overflow == 40
    assert settings.redis_max_connections == 150
    assert settings.llm_max_concurrency == 100


@pytest.mark.unit
def test_concurrency_settings_can_be_overridden_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_POOL_SIZE", "80")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "50")
    monkeypatch.setenv("REDIS_MAX_CONNECTIONS", "200")
    monkeypatch.setenv("LLM_MAX_CONCURRENCY", "150")

    settings = Settings(_env_file=None)

    assert settings.db_pool_size == 80
    assert settings.db_max_overflow == 50
    assert settings.redis_max_connections == 200
    assert settings.llm_max_concurrency == 150
