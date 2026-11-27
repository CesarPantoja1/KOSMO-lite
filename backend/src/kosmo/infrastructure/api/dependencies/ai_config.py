from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request

if TYPE_CHECKING:
    from kosmo.infrastructure.api.composition import AppContainer

from kosmo.application.ai.get_ai_catalog import GetAiCatalogUseCase
from kosmo.application.ai.manage_ai_preferences import ManageAIPreferencesUseCase
from kosmo.application.ai.sync_ai_catalog import SyncAiCatalogUseCase
from kosmo.application.ai.validate_ai_connection import ValidateAIConnectionUseCase
from kosmo.contracts.auth import SecretCipher
from kosmo.infrastructure.api.dependencies.container import get_container
from kosmo.infrastructure.codegen.opencode_catalog_adapter import HttpOpenCodeCatalogInspector
from kosmo.infrastructure.llm.connection_tester import HttpAIConnectionTester
from kosmo.infrastructure.llm.discovery import (
    AnthropicDiscoveryAdapter,
    DeepSeekDiscoveryAdapter,
    GoogleDiscoveryAdapter,
    OpenAIDiscoveryAdapter,
)
from kosmo.infrastructure.security import FernetSecretCipher


def _resolve_cipher(request: Request) -> SecretCipher:
    container = get_container(request)
    if container.auth is not None:
        return container.auth.secret_cipher
    if container.settings.fernet_master_key is not None:
        return FernetSecretCipher(container.settings.fernet_master_key.get_secret_value())
    raise RuntimeError("Fernet master key is required to manage AI preferences")


def get_manage_ai_preferences_use_case(request: Request) -> ManageAIPreferencesUseCase:
    container = get_container(request)
    return ManageAIPreferencesUseCase(
        config_repo=container.repos.user_ai_configs,
        cipher=_resolve_cipher(request),
        connection_tester=HttpAIConnectionTester(),
    )


def get_validate_ai_connection_use_case(request: Request) -> ValidateAIConnectionUseCase:
    container = get_container(request)
    return ValidateAIConnectionUseCase(
        connection_tester=HttpAIConnectionTester(),
        config_repo=container.repos.user_ai_configs,
        cipher=_resolve_cipher(request),
    )


def get_ai_catalog_use_case(request: Request) -> GetAiCatalogUseCase:
    container = get_container(request)
    inspector = HttpOpenCodeCatalogInspector(
        base_url=container.settings.opencode_launcher_base_url or container.settings.opencode_base_url,
        auth_token=(
            container.settings.opencode_launcher_token.get_secret_value()
            if container.settings.opencode_launcher_token
            else None
        ),
        server_username=container.settings.opencode_server_username,
        server_password=(
            container.settings.opencode_server_password.get_secret_value()
            if container.settings.opencode_server_password
            else None
        ),
    )
    return GetAiCatalogUseCase(
        catalog_repo=container.repos.ai_catalog,
        opencode_inspector=inspector,
    )


def build_sync_ai_catalog_use_case(container: AppContainer) -> SyncAiCatalogUseCase:
    inspector = HttpOpenCodeCatalogInspector(
        base_url=container.settings.opencode_launcher_base_url or container.settings.opencode_base_url,
        auth_token=(
            container.settings.opencode_launcher_token.get_secret_value()
            if container.settings.opencode_launcher_token
            else None
        ),
        server_username=container.settings.opencode_server_username,
        server_password=(
            container.settings.opencode_server_password.get_secret_value()
            if container.settings.opencode_server_password
            else None
        ),
    )
    adapters = [
        OpenAIDiscoveryAdapter(),
        AnthropicDiscoveryAdapter(),
        GoogleDiscoveryAdapter(),
        DeepSeekDiscoveryAdapter(),
    ]
    return SyncAiCatalogUseCase(
        catalog_repo=container.repos.ai_catalog,
        opencode_inspector=inspector,
        adapters=adapters,
    )


def get_sync_ai_catalog_use_case(request: Request) -> SyncAiCatalogUseCase:
    container = get_container(request)
    return build_sync_ai_catalog_use_case(container)
