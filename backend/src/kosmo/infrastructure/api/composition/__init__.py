from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from kosmo.config import Settings
from kosmo.infrastructure.api.composition.auth import AuthComponents, build_auth_components
from kosmo.infrastructure.api.composition.codegen import (
    CodegenComponents,
    build_code_runner,
    build_codegen_components,
    build_workspace_manager,
)
from kosmo.infrastructure.api.composition.integrations import (
    IntegrationsComponents,
    build_integrations_components,
)
from kosmo.infrastructure.api.composition.pipeline import PipelineComponents, build_pipeline_components
from kosmo.infrastructure.api.composition.sdd import (
    ConsistencyComponents,
    DiscoveryComponents,
    FeaturesComponents,
    ModeloComponents,
    ProjectComponents,
    RequirementsComponents,
    build_consistency_components,
    build_discovery_components,
    build_features_components,
    build_modelo_components,
    build_project_components,
    build_requirements_components,
)
from kosmo.infrastructure.persistence.postgres.registry import RepositoryRegistry
from kosmo.infrastructure.persistence.postgres.uow import SqlAlchemyUnitOfWork
from kosmo.infrastructure.sandbox.remote_code_runner import RemoteCodeRunner
from kosmo.infrastructure.security.fernet_vault import FernetSecretCipher

__all__ = [
    "AppContainer",
    "AuthComponents",
    "CodegenComponents",
    "ConsistencyComponents",
    "DiscoveryComponents",
    "FeaturesComponents",
    "IntegrationsComponents",
    "ModeloComponents",
    "PipelineComponents",
    "ProjectComponents",
    "RequirementsComponents",
    "build_app_components",
    "build_auth_components",
    "build_code_runner",
    "build_codegen_components",
    "build_consistency_components",
    "build_discovery_components",
    "build_features_components",
    "build_integrations_components",
    "build_modelo_components",
    "build_pipeline_components",
    "build_project_components",
    "build_requirements_components",
    "build_workspace_manager",
]


@dataclass(frozen=True, slots=True)
class AppContainer:
    """Contenedor tipado de dependencias expuesto via ``app.state.container``."""

    settings: Settings
    auth: AuthComponents | None
    projects: ProjectComponents
    pipeline: PipelineComponents
    discovery: DiscoveryComponents
    features: FeaturesComponents
    requirements: RequirementsComponents
    modelo: ModeloComponents
    consistency: ConsistencyComponents
    codegen: CodegenComponents
    integrations: IntegrationsComponents
    repos: RepositoryRegistry
    uow: SqlAlchemyUnitOfWork
    db_engine: AsyncEngine
    redis: Redis | None

    async def close(self) -> None:
        if self.redis is not None:
            await self.redis.aclose()
        await self.codegen.implementation_broker.aclose()
        await self.codegen.opencode_client.aclose()
        if isinstance(self.codegen.code_runner, RemoteCodeRunner):
            await self.codegen.code_runner.aclose()
        await self.integrations.deployment_worker.shutdown()
        await self.db_engine.dispose()


def build_app_components(settings: Settings) -> AppContainer:
    workers = max(1, settings.server_workers)
    pool_size = max(5, settings.db_pool_size // workers)
    max_overflow = max(3, settings.db_max_overflow // workers)

    db_engine = create_async_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=settings.db_pool_recycle,
        connect_args={"statement_cache_size": 0},
    )
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    repos = RepositoryRegistry.build(session_factory)

    auth: AuthComponents | None = None
    redis: Redis | None = None
    if not settings.auth_disabled:
        auth = build_auth_components(settings, repos)
        redis = auth.redis

    pipeline = build_pipeline_components(settings, session_factory, repos)
    uow = SqlAlchemyUnitOfWork(session_factory)

    discovery = build_discovery_components(repos, pipeline)
    features = build_features_components(repos, pipeline, discovery.consistency_evaluator)
    requirements = build_requirements_components(repos, pipeline, uow)
    modelo = build_modelo_components(repos, pipeline)
    consistency = build_consistency_components(repos, discovery.consistency_evaluator, uow)

    cipher = (
        auth.secret_cipher
        if auth is not None
        else FernetSecretCipher(
            settings.fernet_master_key.get_secret_value()
            if settings.fernet_master_key is not None
            else FernetSecretCipher.generate_master_key()
        )
    )
    code_runner = build_code_runner(settings)
    workspace_manager = build_workspace_manager(settings, repos, code_runner=code_runner)

    integrations = build_integrations_components(
        settings,
        repos,
        workspace_manager,
        cipher,
        code_runner=code_runner,
    )
    codegen = build_codegen_components(
        settings,
        repos,
        sync_github_repository=integrations.sync_github_repository,
        workspace_manager=workspace_manager,
        code_runner=code_runner,
        redis=redis,
        integrations=integrations,
    )

    projects = build_project_components(
        repos,
        pipeline,
        workspace_manager=workspace_manager,
        github_client=integrations.github_client,
        railway_client=integrations.railway_client,
        deployment_worker=integrations.deployment_worker,
        cipher=cipher,
        delete_deployment=integrations.delete_deployment,
    )

    return AppContainer(
        settings=settings,
        auth=auth,
        projects=projects,
        pipeline=pipeline,
        discovery=discovery,
        features=features,
        requirements=requirements,
        modelo=modelo,
        consistency=consistency,
        codegen=codegen,
        integrations=integrations,
        repos=repos,
        uow=uow,
        db_engine=db_engine,
        redis=redis,
    )
