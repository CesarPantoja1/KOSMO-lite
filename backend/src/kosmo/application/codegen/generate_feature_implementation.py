from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog
from ulid import ULID

from kosmo.application.codegen.analyze_feature_integration import (
    AnalyzeFeatureIntegrationUseCase,
)
from kosmo.application.codegen.analyze_ux_context import (
    UXAnalyzerUseCase,
)
from kosmo.application.codegen.build_service import (
    BuildService,
    ExecutionService,
    OpenCodeGenerationError,
    raise_for_opencode_error,
)
from kosmo.application.codegen.implementation_context_builder import (
    ImplementationContextBuilder,
    NullFileSystemReader,
    NullFileSystemWriter,
    collect_workspace_feature_files,
    get_existing_db_schema_context,
    normalize_generated_file_path,
)
from kosmo.application.codegen.planning_service import (
    PlanningService,
)
from kosmo.application.codegen.post_deploy_service import (
    PostDeployService,
)
from kosmo.application.codegen.register_code_traceability import (
    RegisterCodeTraceabilityUseCase,
)
from kosmo.application.codegen.validation_service import (
    ValidationService,
    VerificationService,
)
from kosmo.application.integrations.orchestrate_cloud_deployment import (
    OrchestrateCloudDeploymentUseCase,
)
from kosmo.application.integrations.sync_github_repository import (
    SyncGitHubRepositoryUseCase,
)
from kosmo.contracts.ai.consistency import TraceabilityRepository
from kosmo.contracts.integrations.deployment import (
    DeploymentWorkerPort,
    ProjectDeploymentRepository,
)
from kosmo.contracts.sdd.codegen import (
    CodeRunnerPort,
    CodeWorkspace,
    FeatureImplementation,
    FeatureImplementationRepository,
    FeatureImplementationStatus,
    FileSystemReader,
    FileSystemWriter,
    OpenCodeClientPort,
    OpenCodeEvent,
    OpenCodeEventType,
    ValidationRunResult,
    WorkspaceManagerPort,
)
from kosmo.contracts.sdd.errors import FeatureNotFoundError
from kosmo.contracts.sdd.ids import FeatureId, ImplementationId, ProjectId
from kosmo.contracts.sdd.product_map import ProductMap
from kosmo.contracts.sdd.repositories import (
    ActivityDiagramRepository,
    DocumentRepository,
    FeatureRepository,
    ProjectRepository,
    RequirementRepository,
)
from kosmo.contracts.telemetry import record_codegen_duration

_log = structlog.get_logger("kosmo.codegen.generate")

_DEFAULT_REQ_MSG = "Esta característica no tiene requisitos EARS generados. Genera los requisitos antes de continuar."
_DEFAULT_DIAG_MSG = (
    "Esta característica no tiene diagrama de actividad generado. Genera el diagrama antes de continuar."
)


class MissingRequirementsError(ValueError):
    """Lanzada cuando la característica no tiene requisitos EARS generados (CA-02)."""

    def __init__(self, message: str = _DEFAULT_REQ_MSG) -> None:
        super().__init__(message)


class MissingDiagramError(ValueError):
    """Lanzada cuando la característica no tiene diagrama de actividad generado (CA-03)."""

    def __init__(self, message: str = _DEFAULT_DIAG_MSG) -> None:
        super().__init__(message)


class OpenCodeUnavailableError(ValueError):
    """Lanzada cuando el servidor OpenCode no responde antes de iniciar la generación."""

    def __init__(
        self,
        message: str = (
            "El asistente de generación no está disponible en este momento. Inténtalo de nuevo en unos minutos."
        ),
    ) -> None:
        super().__init__(message)


_normalize_generated_file_path = normalize_generated_file_path
_NullFileSystemReader = NullFileSystemReader
_NullFileSystemWriter = NullFileSystemWriter
_collect_workspace_feature_files = collect_workspace_feature_files
_get_existing_db_schema_context = get_existing_db_schema_context
_raise_for_opencode_error = raise_for_opencode_error

__all__ = [
    "BuildService",
    "ExecutionService",
    "GenerateFeatureImplementationInput",
    "GenerateFeatureImplementationOutput",
    "GenerateFeatureImplementationUseCase",
    "MissingDiagramError",
    "MissingRequirementsError",
    "OpenCodeGenerationError",
    "OpenCodeUnavailableError",
    "PlanningService",
    "PostDeployService",
    "ValidationService",
    "VerificationService",
    "_NullFileSystemReader",
    "_collect_workspace_feature_files",
    "_get_existing_db_schema_context",
    "_normalize_generated_file_path",
    "_raise_for_opencode_error",
    "raise_for_opencode_error",
]


@dataclass(frozen=True)
class GenerateFeatureImplementationInput:
    feature_id: FeatureId
    max_retries: int = 3
    event_sink: Callable[[OpenCodeEvent], Awaitable[None]] | None = None


@dataclass(frozen=True)
class GenerateFeatureImplementationOutput:
    success: bool
    status: FeatureImplementationStatus
    implementation: FeatureImplementation | None
    workspace: CodeWorkspace | None
    validation_result: ValidationRunResult | None = None
    generated_files: tuple[str, ...] = field(default_factory=tuple)
    error_message: str | None = None
    retry_history: tuple[tuple[str, ...], ...] = field(default_factory=tuple)
    events: tuple[OpenCodeEvent, ...] = field(default_factory=tuple)


class GenerateFeatureImplementationUseCase:
    """Caso de uso principal para orquestar la generación de código por característica."""

    def __init__(
        self,
        feature_repo: FeatureRepository,
        requirement_repo: RequirementRepository,
        activity_diagram_repo: ActivityDiagramRepository,
        workspace_manager: WorkspaceManagerPort,
        opencode_client: OpenCodeClientPort,
        code_runner: CodeRunnerPort,
        implementation_repo: FeatureImplementationRepository,
        traceability_repo: TraceabilityRepository,
        project_repo: ProjectRepository | None = None,
        document_repo: DocumentRepository | None = None,
        ux_analyzer: UXAnalyzerUseCase | None = None,
        sync_github_repository: SyncGitHubRepositoryUseCase | None = None,
        fs_reader: FileSystemReader | None = None,
        fs_writer: FileSystemWriter | None = None,
        context_builder: ImplementationContextBuilder | None = None,
        integration_analyzer: AnalyzeFeatureIntegrationUseCase | None = None,
        orchestrate_cloud_deployment: OrchestrateCloudDeploymentUseCase | None = None,
        project_deployment_repo: ProjectDeploymentRepository | None = None,
        deployment_worker: DeploymentWorkerPort | None = None,
        planning_service: PlanningService | None = None,
        build_service: BuildService | None = None,
        validation_service: ValidationService | None = None,
        post_deploy_service: PostDeployService | None = None,
        execution_service: ExecutionService | None = None,
        verification_service: VerificationService | None = None,
    ) -> None:
        self._feature_repo = feature_repo
        self._requirement_repo = requirement_repo
        self._activity_diagram_repo = activity_diagram_repo
        self._workspace_manager = workspace_manager
        self._opencode_client = opencode_client
        self._code_runner = code_runner
        self._implementation_repo = implementation_repo
        self._project_repo = project_repo
        self._document_repo = document_repo
        self._sync_github_repository = sync_github_repository
        self._orchestrate_cloud_deployment = orchestrate_cloud_deployment
        self._project_deployment_repo = project_deployment_repo
        self._deployment_worker = deployment_worker
        if fs_reader is not None:
            self._fs_reader: FileSystemReader = fs_reader
        elif isinstance(workspace_manager, FileSystemReader):
            self._fs_reader = workspace_manager
        else:
            self._fs_reader = _NullFileSystemReader()
        if fs_writer is not None:
            self._fs_writer: FileSystemWriter = fs_writer
        elif isinstance(workspace_manager, FileSystemWriter):
            self._fs_writer = workspace_manager
        else:
            self._fs_writer = _NullFileSystemWriter()
        self._ux_analyzer = ux_analyzer or UXAnalyzerUseCase(
            document_repo=document_repo,
            feature_repo=feature_repo,
        )
        self._register_traceability = RegisterCodeTraceabilityUseCase(
            traceability_repo=traceability_repo,
            requirement_repo=requirement_repo,
        )
        self._context_builder = context_builder or ImplementationContextBuilder(
            project_repo=project_repo,
            document_repo=document_repo,
            implementation_repo=implementation_repo,
            feature_repo=feature_repo,
            fs_reader=self._fs_reader,
            fs_writer=self._fs_writer,
        )
        self._integration_analyzer = integration_analyzer or AnalyzeFeatureIntegrationUseCase(
            feature_repo=feature_repo,
            document_repo=document_repo,
            implementation_repo=implementation_repo,
        )

        self._planning_service = planning_service or PlanningService(
            opencode_client=self._opencode_client,
            context_builder=self._context_builder,
            integration_analyzer=self._integration_analyzer,
            ux_analyzer=self._ux_analyzer,
            implementation_repo=self._implementation_repo,
        )
        self._build_service = (
            build_service
            or execution_service
            or BuildService(
                opencode_client=self._opencode_client,
                context_builder=self._context_builder,
                workspace_manager=self._workspace_manager,
                fs_reader=self._fs_reader,
            )
        )
        self._validation_service = (
            validation_service
            or verification_service
            or ValidationService(
                code_runner=self._code_runner,
                opencode_client=self._opencode_client,
                context_builder=self._context_builder,
                implementation_repo=self._implementation_repo,
                fs_reader=self._fs_reader,
            )
        )

        self._post_deploy_service = post_deploy_service or PostDeployService(
            workspace_manager=self._workspace_manager,
            implementation_repo=self._implementation_repo,
            register_traceability=self._register_traceability,
            project_repo=self._project_repo,
            sync_github_repository=self._sync_github_repository,
            orchestrate_cloud_deployment=self._orchestrate_cloud_deployment,
            project_deployment_repo=self._project_deployment_repo,
            deployment_worker=self._deployment_worker,
        )

    def set_sync_github_repository(self, sync_github_repository: SyncGitHubRepositoryUseCase) -> None:
        self._sync_github_repository = sync_github_repository
        self._post_deploy_service.set_sync_github_repository(sync_github_repository)

    async def _build_project_context(
        self,
        project_id: ProjectId,
        current_feature_id: FeatureId | None = None,
        workspace_dir: str | None = None,
        product_map: ProductMap | None = None,
    ) -> str:
        """Construye el bloque de contexto del proyecto delegando en el context builder."""
        return await self._context_builder.build_project_context(
            project_id=project_id,
            current_feature_id=current_feature_id,
            workspace_dir=workspace_dir,
            product_map=product_map,
        )

    async def _build_implemented_features_context(
        self,
        project_id: ProjectId,
        current_feature_id: FeatureId | None = None,
    ) -> str:
        """Construye un resumen conciso de funcionalidades ya implementadas delegando en el context builder."""
        return await self._context_builder.build_implemented_features_context(
            project_id=project_id,
            current_feature_id=current_feature_id,
        )

    async def execute_stream(
        self,
        input_data: GenerateFeatureImplementationInput,
    ) -> AsyncIterator[OpenCodeEvent]:
        """Ejecuta el pipeline emitiendo eventos de progreso SSE en tiempo real a medida que ocurren."""
        queue: asyncio.Queue[OpenCodeEvent | None | Exception] = asyncio.Queue()

        async def _capture_event(ev: OpenCodeEvent) -> None:
            await queue.put(ev)

        async def _run() -> None:
            try:
                await self._run_pipeline(input_data, event_collector=_capture_event)
            except Exception as exc:
                await queue.put(exc)
            finally:
                await queue.put(None)

        task = asyncio.create_task(_run())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise item
                yield item
        finally:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    async def execute(
        self,
        input_data: GenerateFeatureImplementationInput,
    ) -> GenerateFeatureImplementationOutput:
        """Ejecuta el pipeline de implementación completo de forma síncrona."""
        return await self._run_pipeline(input_data)

    async def _run_pipeline(
        self,
        input_data: GenerateFeatureImplementationInput,
        event_collector: Callable[[OpenCodeEvent], Awaitable[None]] | None = None,
    ) -> GenerateFeatureImplementationOutput:
        # 1. Consultar precondiciones de repositorios secuencialmente para evitar checkouts concurrentes del pool
        feature = await self._feature_repo.by_id(input_data.feature_id)
        req_markdown = await self._requirement_repo.by_feature_id(input_data.feature_id)
        diagram = await self._activity_diagram_repo.by_feature_id(input_data.feature_id)

        # 2. Validar existencia de Feature
        if feature is None:
            raise FeatureNotFoundError(
                feature_id=str(input_data.feature_id),
                instance=f"/api/v1/features/{input_data.feature_id}/implementation",
            )

        # 3. Validar presencia de requisitos EARS (CA-02)
        if not req_markdown or not req_markdown.strip():
            raise MissingRequirementsError(_DEFAULT_REQ_MSG)

        # 4. Validar presencia de diagrama de actividad (CA-03)
        if diagram is None or not diagram.diagram_syntax.strip():
            raise MissingDiagramError(_DEFAULT_DIAG_MSG)

        validate_config = getattr(self._opencode_client, "validate_user_config", None)
        if validate_config is not None:
            await validate_config()

        # 5. Verificar disponibilidad de OpenCode antes de adquirir recursos
        is_healthy = await self._opencode_client.health_check()
        if not is_healthy:
            raise OpenCodeUnavailableError()

        run_id = ULID().hex

        collected_events: list[OpenCodeEvent] = []

        async def _emit(event: OpenCodeEvent) -> None:
            event = dataclasses.replace(event, run_id=run_id)
            collected_events.append(event)
            if input_data.event_sink is not None:
                await input_data.event_sink(event)
            if event_collector is not None:
                await event_collector(event)

        total_start: float = time.monotonic()
        _log.info(
            "codegen.pipeline_started",
            feature_id=str(feature.id),
            project_id=str(feature.project_id),
        )
        await self._workspace_manager.acquire_lock(feature.project_id)
        workspace: CodeWorkspace | None = None
        session_id: str | None = None
        job_started = False

        try:
            await _emit(
                OpenCodeEvent(
                    event_type=OpenCodeEventType.PLAN_PROGRESS,
                    session_id="",
                    data={"delta": "Preparando el espacio de trabajo de tu proyecto...", "stage": "workspace"},
                )
            )
            workspace = await self._workspace_manager.ensure_workspace(feature.project_id)
            workspace_dir = workspace.workspace_dir or "/workspace"

            # Crear o cargar registro FeatureImplementation
            existing_impl = await self._implementation_repo.by_feature_id(input_data.feature_id)
            now = datetime.now(UTC)
            if existing_impl is not None:
                impl = dataclasses.replace(
                    existing_impl,
                    status=FeatureImplementationStatus.IN_PROGRESS,
                    updated_at=now,
                )
            else:
                impl = FeatureImplementation(
                    id=ImplementationId(f"impl_{feature.id}"),
                    feature_id=feature.id,
                    project_id=feature.project_id,
                    status=FeatureImplementationStatus.IN_PROGRESS,
                    max_attempts=input_data.max_retries,
                    created_at=now,
                    updated_at=now,
                )
            await self._implementation_repo.save(impl)

            start_job = getattr(self._opencode_client, "start_job", None)
            if start_job is not None:
                await start_job(workspace_dir)
                job_started = True

            # 6. Crear sesión en OpenCode
            await _emit(
                OpenCodeEvent(
                    event_type=OpenCodeEventType.PLAN_PROGRESS,
                    session_id="",
                    data={
                        "delta": f"Iniciando la generación de la funcionalidad '{feature.title}'...",
                        "stage": "session",
                    },
                )
            )
            session = await self._opencode_client.create_session(
                workspace_dir=workspace_dir,
                title=f"Feature implementation: {feature.title}",
            )
            session_id = session.session_id
            impl = dataclasses.replace(impl, session_id=session_id)
            await self._implementation_repo.save(impl)

            await _emit(
                OpenCodeEvent(
                    event_type=OpenCodeEventType.SESSION_CREATED,
                    session_id=session_id,
                    data={
                        "workspace_dir": workspace_dir,
                        "feature_id": str(feature.id),
                        "delta": "Sesión iniciada. Analizando requisitos...",
                    },
                )
            )

            # 7. Fase Plan (delegada en PlanningService)
            planning_res = await self._planning_service.execute_plan(
                feature=feature,
                req_markdown=req_markdown,
                diagram_syntax=diagram.diagram_syntax,
                workspace_dir=workspace_dir,
                manifest_files=workspace.manifest_files if workspace else (),
                session_id=session_id,
                impl=impl,
                emit_event=_emit,
            )
            impl = planning_res.impl

            # 8. Fase Build (delegada en BuildService)
            generated_files = await self._build_service.execute_build(
                feature=feature,
                req_markdown=req_markdown,
                diagram_syntax=diagram.diagram_syntax,
                ux_prompt_block=planning_res.ux_analysis.prompt_block,
                project_context=planning_res.project_context,
                impl_plan=planning_res.impl_plan,
                product_map=planning_res.product_map,
                workspace_dir=workspace_dir,
                session_id=session_id,
                emit_event=_emit,
            )

            # 9. Fase Validación & Reintentos (delegada en ValidationService)
            val_res = await self._validation_service.execute_validation(
                feature=feature,
                workspace_dir=workspace_dir,
                session_id=session_id,
                product_map=planning_res.product_map,
                generated_files=generated_files,
                impl=impl,
                max_retries=input_data.max_retries,
                run_id=run_id,
                emit_event=_emit,
            )
            impl = val_res.impl

            # 10. Conclusión del pipeline (delegada en PostDeployService)
            if val_res.validation_result is not None and val_res.validation_result.all_passed:
                res = await self._post_deploy_service.handle_success(
                    feature=feature,
                    impl=impl,
                    workspace=workspace,
                    session_id=session_id,
                    generated_files=val_res.generated_files,
                    req_markdown=req_markdown,
                    validation_result=val_res.validation_result,
                    retry_history=val_res.retry_history,
                    attempt=val_res.attempt,
                    val_duration=val_res.duration_seconds,
                    total_start=total_start,
                    emit_event=_emit,
                )
            else:
                res = await self._post_deploy_service.handle_failure(
                    feature=feature,
                    impl=impl,
                    workspace=workspace,
                    session_id=session_id,
                    generated_files=val_res.generated_files,
                    validation_result=val_res.validation_result,
                    retry_history=val_res.retry_history,
                    attempt=val_res.attempt,
                    max_retries=input_data.max_retries,
                    val_duration=val_res.duration_seconds,
                    total_start=total_start,
                    emit_event=_emit,
                )

            return GenerateFeatureImplementationOutput(
                success=res.success,
                status=res.status,
                implementation=res.implementation,
                workspace=res.workspace,
                validation_result=res.validation_result,
                generated_files=res.generated_files,
                error_message=res.error_message,
                retry_history=res.retry_history,
                events=tuple(collected_events),
            )

        except Exception as exc:
            if "total_start" in locals():
                total_duration = time.monotonic() - total_start
                record_codegen_duration("total", total_duration, status="error")
                _log.exception(
                    "codegen.pipeline_failed",
                    feature_id=str(input_data.feature_id),
                    project_id=str(feature.project_id) if "feature" in locals() else None,
                    total_duration_seconds=round(total_duration, 2),
                )
            with contextlib.suppress(Exception):
                await self._workspace_manager.rollback_workspace(feature.project_id)
            with contextlib.suppress(Exception):
                current_impl = await self._implementation_repo.by_feature_id(input_data.feature_id)
                if current_impl is not None and current_impl.status == FeatureImplementationStatus.IN_PROGRESS:
                    await self._implementation_repo.save(
                        dataclasses.replace(
                            current_impl,
                            status=FeatureImplementationStatus.FAILED,
                            updated_at=datetime.now(UTC),
                        )
                    )

            with contextlib.suppress(Exception):
                await _emit(
                    OpenCodeEvent(
                        event_type=OpenCodeEventType.ERROR,
                        session_id=session_id or "",
                        data={
                            "error": str(exc),
                            "error_type": type(exc).__name__,
                            "fatal": True,
                        },
                    )
                )

            raise
        finally:
            if session_id is not None:
                with contextlib.suppress(Exception):
                    await self._opencode_client.close_session(session_id)
            if job_started:
                stop_job = getattr(self._opencode_client, "stop_job", None)
                if stop_job is not None:
                    with contextlib.suppress(Exception):
                        await stop_job()
            with contextlib.suppress(Exception):
                await self._workspace_manager.release_lock(feature.project_id)

    @staticmethod
    def _format_retry_history(retry_history: list[tuple[str, ...]]) -> str:
        """Construye el mensaje de detalle de error a partir del historial de reintentos."""
        return PostDeployService.format_retry_history(retry_history)

    async def _build_done_event(
        self,
        *,
        session_id: str,
        generated_files: set[str],
        req_markdown: str,
        validation_result: ValidationRunResult,
        traceability_edges: int,
        features_count: int,
    ) -> OpenCodeEvent:
        """Calcula las métricas del evento DONE y construye el objeto de evento."""
        return await self._post_deploy_service.build_done_event(
            session_id=session_id,
            generated_files=generated_files,
            req_markdown=req_markdown,
            validation_result=validation_result,
            traceability_edges=traceability_edges,
            features_count=features_count,
        )
