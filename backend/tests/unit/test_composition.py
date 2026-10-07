from __future__ import annotations

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.requests import Request

from kosmo.application.chat.process_chat_message import ProcessChatMessageUseCase
from kosmo.application.consistency.apply_consistency_impacts import ApplyConsistencyImpactsUseCase
from kosmo.config import Settings
from kosmo.infrastructure.api.composition import AppContainer, build_app_components
from kosmo.infrastructure.api.dependencies.container import get_container
from kosmo.infrastructure.persistence.postgres.registry import RepositoryRegistry


def _make_settings() -> Settings:
    return Settings(
        env="development",
        database_url="postgresql+asyncpg://user:pass@localhost:5432/kosmo",
        llm_provider="noop",
        llm_model="noop",
        embedding_provider="none",
        auth_disabled=True,
    )


@pytest.mark.unit
def test_repository_registry_builds_distinct_repositories() -> None:
    # Arrange
    factory = async_sessionmaker()

    # Act
    repos = RepositoryRegistry.build(factory)

    # Assert
    instances = [
        repos.projects,
        repos.documents,
        repos.features,
        repos.requirements,
        repos.diagrams,
        repos.chat,
        repos.traceability,
        repos.users,
        repos.audit_sink,
    ]
    assert len({id(repo) for repo in instances}) == len(instances)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_app_components_reuses_registry_instances() -> None:
    # Arrange
    settings = _make_settings()

    # Act
    components = build_app_components(settings)

    try:
        # Assert: cada builder usa la instancia unica del registry
        assert components.discovery.document_repo is components.repos.documents
        assert components.features.feature_repo is components.repos.features
        assert components.requirements.requirement_repo is components.repos.requirements
        assert components.modelo.diagram_repo is components.repos.diagrams
        assert components.pipeline.chat_repo is components.repos.chat
        assert components.pipeline.traceability_repo is components.repos.traceability
        assert components.discovery.consistency_evaluator is components.pipeline.consistency_evaluator

        # Assert: auth deshabilitado no crea componentes de autenticacion
        assert components.auth is None
        assert components.redis is None
    finally:
        await components.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_app_container_exposes_typed_components() -> None:
    # Arrange
    settings = _make_settings()

    # Act
    components = build_app_components(settings)

    try:
        # Assert: los campos del contenedor tienen tipos concretos (no Any)
        assert isinstance(components, AppContainer)
        assert isinstance(components.pipeline.process_chat_message, ProcessChatMessageUseCase)
        assert isinstance(components.consistency.apply_consistency_impacts, ApplyConsistencyImpactsUseCase)
        assert components.projects.create_project is not None
        assert components.pipeline.outbox is not None
        assert components.db_engine is not None
    finally:
        await components.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_container_returns_container_from_app_state() -> None:
    # Arrange
    settings = _make_settings()
    components = build_app_components(settings)
    app = FastAPI()
    app.state.container = components
    request = Request(scope={"type": "http", "method": "GET", "path": "/", "app": app})

    # Act
    container = get_container(request)

    # Assert
    assert container is components

    await components.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_app_components_configures_db_connection_pool() -> None:
    # Arrange
    settings = _make_settings()

    # Act
    components = build_app_components(settings)

    try:
        # Assert
        from sqlalchemy.pool import QueuePool

        pool = components.db_engine.pool
        assert isinstance(pool, QueuePool)
        assert pool.size() == 60
        assert pool._max_overflow == 40
        assert pool._recycle == 1800
    finally:
        await components.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_app_components_scales_pool_for_multiple_workers() -> None:
    # Arrange: 4 workers
    settings = _make_settings()
    settings.server_workers = 4

    # Act
    components = build_app_components(settings)

    try:
        from sqlalchemy.pool import QueuePool

        pool = components.db_engine.pool
        assert isinstance(pool, QueuePool)
        # pool_size = max(5, 60 // 4) = 15
        assert pool.size() == 15
        # max_overflow = max(3, 40 // 4) = 10
        assert pool._max_overflow == 10
    finally:
        await components.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_app_components_pool_size_respects_floor() -> None:
    # Arrange: muchos workers (20)
    settings = _make_settings()
    settings.server_workers = 20

    # Act
    components = build_app_components(settings)

    try:
        from sqlalchemy.pool import QueuePool

        pool = components.db_engine.pool
        assert isinstance(pool, QueuePool)
        # Floor: pool_size >= 5, max_overflow >= 3
        assert pool.size() == 5
        assert pool._max_overflow == 3
    finally:
        await components.close()


@pytest.mark.unit
def test_build_auth_components_configures_redis_pool_and_timeouts() -> None:
    from kosmo.infrastructure.api.composition.auth import build_auth_components
    from tests.conftest import _FERNET_KEY, _PRIVATE_KEY_PEM, _PUBLIC_KEY_PEM

    settings = Settings(
        env="development",
        database_url="postgresql+asyncpg://user:pass@localhost:5432/kosmo",
        redis_url="redis://:pass@localhost:6379/0",
        llm_provider="noop",
        llm_model="noop",
        embedding_provider="none",
        auth_disabled=False,
        jwt_private_key_pem=_PRIVATE_KEY_PEM,
        jwt_public_key_pem=_PUBLIC_KEY_PEM,
        fernet_master_key=_FERNET_KEY,
        redis_max_connections=50,
        redis_socket_timeout=10.0,
        redis_socket_connect_timeout=5.0,
    )
    repos = RepositoryRegistry.build(async_sessionmaker())
    auth = build_auth_components(settings, repos)

    assert auth.redis is not None
    pool = auth.redis.connection_pool
    assert pool.max_connections == 50
    assert pool.connection_kwargs.get("socket_timeout") == 10.0
    assert pool.connection_kwargs.get("socket_connect_timeout") == 5.0
