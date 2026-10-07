from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import async_sessionmaker

from kosmo.application.codegen.generate_feature_implementation import GenerateFeatureImplementationUseCase
from kosmo.config import Settings
from kosmo.infrastructure.api.composition import build_app_components
from kosmo.infrastructure.api.composition.codegen import (
    CodegenComponents,
    build_code_runner,
    build_codegen_components,
    build_workspace_manager,
)
from kosmo.infrastructure.api.implementation_broker import ImplementationEventBroker
from kosmo.infrastructure.codegen.isolated_opencode import IsolatedOpenCodeClient
from kosmo.infrastructure.codegen.opencode_client import OpenCodeHttpClient
from kosmo.infrastructure.codegen.workspace import LocalWorkspaceManager
from kosmo.infrastructure.persistence.postgres.registry import RepositoryRegistry
from kosmo.infrastructure.sandbox.code_runner import SubprocessCodeRunner
from kosmo.infrastructure.sandbox.remote_code_runner import RemoteCodeRunner
from kosmo.infrastructure.security.fernet_vault import FernetSecretCipher

_CODEGEN_ENV_VARS = (
    "OPENCODE_BASE_URL",
    "OPENCODE_SERVER_PASSWORD",
    "OPENCODE_SERVER_USERNAME",
    "OPENCODE_MODEL",
    "OPENCODE_LAUNCHER_BASE_URL",
    "OPENCODE_LAUNCHER_TOKEN",
    "KOSMO_WORKSPACES_DIR",
    "KOSMO_MCP_BASE_URL",
    "CODE_RUNNER_BASE_URL",
    "CODE_RUNNER_TOKEN",
)


@pytest.fixture(autouse=True)
def _minimal_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("AUTH_DISABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/kosmo_test")
    monkeypatch.setenv("LLM_PROVIDER", "noop")
    monkeypatch.setenv("LLM_MODEL", "noop")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "none")
    for var in _CODEGEN_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def _make_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)


def _make_repos() -> RepositoryRegistry:
    return RepositoryRegistry.build(MagicMock(spec=async_sessionmaker))


@pytest.mark.unit
def test_build_codegen_components_cablea_use_case_con_adaptadores() -> None:
    # Arrange
    settings = _make_settings()
    repos = _make_repos()

    # Act
    components = build_codegen_components(settings, repos)

    # Assert
    assert isinstance(components, CodegenComponents)
    use_case = components.generate_feature_implementation
    assert isinstance(use_case, GenerateFeatureImplementationUseCase)
    assert isinstance(components.opencode_client, OpenCodeHttpClient)
    assert isinstance(components.workspace_manager, LocalWorkspaceManager)
    assert isinstance(components.code_runner, SubprocessCodeRunner)
    assert use_case._feature_repo is repos.features
    assert use_case._requirement_repo is repos.requirements
    assert use_case._activity_diagram_repo is repos.diagrams
    assert use_case._workspace_manager is components.workspace_manager
    assert use_case._opencode_client is components.opencode_client
    assert use_case._code_runner is components.code_runner
    assert use_case._implementation_repo is repos.implementations
    assert use_case._register_traceability._traceability_repo is repos.traceability
    assert isinstance(components.implementation_broker, ImplementationEventBroker)
    assert components.implementation_broker._history_ttl_seconds == settings.implementation_broker_ttl_seconds


@pytest.mark.unit
def test_build_codegen_components_propaga_settings_a_adaptadores(tmp_path) -> None:
    # Arrange
    workspaces_dir = tmp_path / "workspaces"
    settings = _make_settings(
        opencode_base_url="http://opencode.local:4096",
        opencode_server_password=SecretStr("tok"),
        opencode_server_username="kosmo-agent",
        opencode_model="deepseek/deepseek-v4-flash",
        kosmo_workspaces_dir=workspaces_dir,
        kosmo_mcp_base_url="http://api.local:8000/mcp",
    )
    repos = _make_repos()

    # Act
    components = build_codegen_components(settings, repos)

    # Assert
    assert components.opencode_client._base_url == "http://opencode.local:4096"
    assert components.opencode_client._server_username == "kosmo-agent"
    assert components.opencode_client._server_password == "tok"
    assert components.opencode_client._model == "deepseek/deepseek-v4-flash"
    assert components.workspace_manager._workspaces_root == workspaces_dir
    assert components.workspace_manager._mcp_url == "http://api.local:8000/mcp"
    assert components.workspace_manager._workspace_repo is repos.workspaces
    assert components.workspace_manager._project_repo is repos.projects


@pytest.mark.unit
def test_build_codegen_components_uses_remote_runner_when_configured(tmp_path) -> None:
    settings = _make_settings(
        kosmo_workspaces_dir=tmp_path / "workspaces",
        code_runner_base_url="http://runner.local:8081",
        code_runner_token=SecretStr("runner-token"),
    )

    components = build_codegen_components(settings, _make_repos())

    assert isinstance(components.code_runner, RemoteCodeRunner)
    assert components.code_runner._base_url == "http://runner.local:8081"


@pytest.mark.unit
def test_production_rejects_shared_opencode_fallback() -> None:
    settings = _make_settings(
        env="production",
        auth_disabled=False,
        redis_url=SecretStr("redis://:test-password@localhost:6379/0"),
    )
    with pytest.raises(ValueError, match="lanzador aislado"):
        build_codegen_components(settings, _make_repos())


@pytest.mark.unit
def test_production_wires_isolated_client_from_own_token() -> None:
    settings = _make_settings(
        env="production",
        auth_disabled=False,
        redis_url=SecretStr("redis://:test-password@localhost:6379/0"),
        opencode_launcher_base_url="http://launcher:8082",
        opencode_launcher_token=SecretStr("launcher-secret"),
        fernet_master_key=SecretStr(FernetSecretCipher.generate_master_key()),
    )
    components = build_codegen_components(settings, _make_repos())
    assert isinstance(components.opencode_client, IsolatedOpenCodeClient)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_app_components_incluye_codegen() -> None:
    # Arrange
    settings = _make_settings()

    # Act
    container = build_app_components(settings)

    try:
        # Assert
        assert isinstance(container.codegen, CodegenComponents)
        assert isinstance(
            container.codegen.generate_feature_implementation,
            GenerateFeatureImplementationUseCase,
        )
        assert isinstance(container.codegen.implementation_broker, ImplementationEventBroker)
        assert (
            container.codegen.generate_feature_implementation._sync_github_repository
            is container.integrations.sync_github_repository
        )
    finally:
        await container.close()


@pytest.mark.unit
def test_build_codegen_components_permite_inyectar_broker_personalizado() -> None:
    # Arrange
    settings = _make_settings()
    repos = _make_repos()
    custom_broker = ImplementationEventBroker(history_ttl_seconds=42)

    # Act
    components = build_codegen_components(settings, repos, broker=custom_broker)

    # Assert
    assert components.implementation_broker is custom_broker
    assert components.implementation_broker._history_ttl_seconds == 42


@pytest.mark.unit
def test_build_codegen_components_permite_inyectar_sync_github_repository() -> None:
    # Arrange
    settings = _make_settings()
    repos = _make_repos()
    mock_sync = MagicMock()

    # Act
    components = build_codegen_components(settings, repos, sync_github_repository=mock_sync)

    # Assert
    assert components.generate_feature_implementation._sync_github_repository is mock_sync


@pytest.mark.unit
def test_build_code_runner_and_workspace_manager_helpers() -> None:
    settings = _make_settings()
    repos = _make_repos()

    runner = build_code_runner(settings)
    assert isinstance(runner, SubprocessCodeRunner)

    ws_manager = build_workspace_manager(settings, repos, code_runner=runner)
    assert isinstance(ws_manager, LocalWorkspaceManager)
    assert ws_manager._code_runner is runner
