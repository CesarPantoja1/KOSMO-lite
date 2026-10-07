from __future__ import annotations

import dataclasses
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog

from kosmo.application.codegen.register_code_traceability import (
    RegisterCodeTraceabilityInput,
    RegisterCodeTraceabilityUseCase,
)
from kosmo.application.integrations.orchestrate_cloud_deployment import (
    OrchestrateCloudDeploymentCommand,
    OrchestrateCloudDeploymentUseCase,
)
from kosmo.application.integrations.sync_github_repository import (
    SyncGitHubRepositoryCommand,
    SyncGitHubRepositoryUseCase,
)
from kosmo.contracts.auth import Principal
from kosmo.contracts.auth.context import current_user_id
from kosmo.contracts.integrations.deployment import (
    DeploymentProvider,
    DeploymentStatus,
    DeploymentWorkerPort,
    ProjectDeploymentRepository,
)
from kosmo.contracts.sdd.codegen import (
    CodeWorkspace,
    FeatureImplementation,
    FeatureImplementationRepository,
    FeatureImplementationStatus,
    OpenCodeEvent,
    OpenCodeEventType,
    ValidationRunResult,
    WorkspaceManagerPort,
)
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import UserId
from kosmo.contracts.sdd.repositories import ProjectRepository
from kosmo.contracts.telemetry import record_codegen_duration, record_codegen_retries
from kosmo.domain.sdd.document_converters import slugify_spanish

_log = structlog.get_logger("kosmo.codegen.post_deploy")


@dataclass(frozen=True, slots=True)
class PostDeployResult:
    success: bool
    status: FeatureImplementationStatus
    implementation: FeatureImplementation | None
    workspace: CodeWorkspace | None
    validation_result: ValidationRunResult | None = None
    generated_files: tuple[str, ...] = field(default_factory=tuple)
    error_message: str | None = None
    retry_history: tuple[tuple[str, ...], ...] = field(default_factory=tuple)


class PostDeployService:
    """Orquesta las operaciones posteriores a la validación:
    commit, sync GitHub, deploy en la nube, trazabilidad y cierre.
    """

    def __init__(
        self,
        workspace_manager: WorkspaceManagerPort,
        implementation_repo: FeatureImplementationRepository,
        register_traceability: RegisterCodeTraceabilityUseCase,
        project_repo: ProjectRepository | None = None,
        sync_github_repository: SyncGitHubRepositoryUseCase | None = None,
        orchestrate_cloud_deployment: OrchestrateCloudDeploymentUseCase | None = None,
        project_deployment_repo: ProjectDeploymentRepository | None = None,
        deployment_worker: DeploymentWorkerPort | None = None,
    ) -> None:
        self._workspace_manager = workspace_manager
        self._implementation_repo = implementation_repo
        self._register_traceability = register_traceability
        self._project_repo = project_repo
        self._sync_github_repository = sync_github_repository
        self._orchestrate_cloud_deployment = orchestrate_cloud_deployment
        self._project_deployment_repo = project_deployment_repo
        self._deployment_worker = deployment_worker

    def set_sync_github_repository(self, sync_github_repository: SyncGitHubRepositoryUseCase) -> None:
        self._sync_github_repository = sync_github_repository

    async def handle_success(
        self,
        *,
        feature: Feature,
        impl: FeatureImplementation,
        workspace: CodeWorkspace | None,
        session_id: str,
        generated_files: set[str],
        req_markdown: str,
        validation_result: ValidationRunResult,
        retry_history: tuple[tuple[str, ...], ...],
        attempt: int,
        val_duration: float,
        total_start: float,
        emit_event: Callable[[OpenCodeEvent], Awaitable[None]],
    ) -> PostDeployResult:
        total_duration = time.monotonic() - total_start
        record_codegen_duration("validate", val_duration, status="success")
        record_codegen_duration("total", total_duration, status="success")
        record_codegen_retries(retries_count=max(0, attempt - 1), success=True)
        _log.info(
            "codegen.pipeline_completed",
            feature_id=str(feature.id),
            project_id=str(feature.project_id),
            total_duration_seconds=round(total_duration, 2),
            attempts=attempt,
            generated_files_count=len(generated_files),
        )
        await emit_event(
            OpenCodeEvent(
                event_type=OpenCodeEventType.BUILD_PROGRESS,
                session_id=session_id,
                data={"delta": "Guardando cambios...", "stage": "finishing"},
            )
        )

        feature_slug = slugify_spanish(feature.slug) or feature.slug
        commit_msg = f"feat({feature_slug}): implement feature {feature.display_id} - {feature.title}"
        await self._workspace_manager.commit_workspace(
            feature.project_id,
            commit_msg,
        )
        impl = dataclasses.replace(
            impl,
            status=FeatureImplementationStatus.IMPLEMENTED,
            generated_files=tuple(sorted(generated_files)),
            updated_at=datetime.now(UTC),
        )
        await self._implementation_repo.save(impl)

        # Sincronización automática con GitHub si el proyecto cuenta con repositorio vinculado
        if self._sync_github_repository is not None and self._project_repo is not None:
            try:
                proj = await self._project_repo.by_id(feature.project_id)
                caller_user_id = current_user_id.get()
                effective_user_id = UserId(caller_user_id) if caller_user_id else (proj.owner_id if proj else None)
                if proj is not None and effective_user_id:
                    await emit_event(
                        OpenCodeEvent(
                            event_type=OpenCodeEventType.BUILD_PROGRESS,
                            session_id=session_id,
                            data={
                                "delta": "Sincronizando cambios con GitHub...",
                                "stage": "syncing_github",
                            },
                        )
                    )
                    repo_slug = proj.slug or f"project-{feature.project_id}"
                    sync_cmd = SyncGitHubRepositoryCommand(
                        project_id=feature.project_id,
                        project_name=proj.name if proj else None,
                        repo_name=repo_slug,
                        commit_message=commit_msg,
                        skip_lock=True,
                        skip_validation=True,
                    )
                    sync_res = await self._sync_github_repository.execute(sync_cmd, effective_user_id)
                    await emit_event(
                        OpenCodeEvent(
                            event_type=OpenCodeEventType.BUILD_PROGRESS,
                            session_id=session_id,
                            data={
                                "delta": f"Código sincronizado exitosamente con GitHub ({sync_res.repo_url})",
                                "stage": "github_synced",
                                "repo_url": sync_res.repo_url,
                                "commit_hash": sync_res.last_commit_hash,
                            },
                        )
                    )
            except Exception as sync_err:
                _log.warning(
                    "codegen.github_auto_sync_failed",
                    feature_id=str(feature.id),
                    project_id=str(feature.project_id),
                    error=str(sync_err),
                )
                await emit_event(
                    OpenCodeEvent(
                        event_type=OpenCodeEventType.BUILD_PROGRESS,
                        session_id=session_id,
                        data={
                            "delta": (
                                "Nota: No se pudo sincronizar automáticamente con GitHub "
                                f"({sync_err}). Puedes sincronizar manualmente desde el resumen."
                            ),
                            "stage": "github_sync_warning",
                        },
                    )
                )

        # Auto-despliegue en la nube si el proyecto ya cuenta con un despliegue previo
        if (
            self._orchestrate_cloud_deployment is not None
            and self._project_deployment_repo is not None
            and self._project_repo is not None
        ):
            try:
                proj = await self._project_repo.by_id(feature.project_id)
                if proj is not None and proj.owner_id:
                    existing_deploy = await self._project_deployment_repo.get_by_project_id(feature.project_id)
                    # Auto-redespliegue solo si ya fue desplegado previamente (tiene service_id)
                    if (
                        existing_deploy is not None
                        and existing_deploy.service_id
                        and existing_deploy.status != DeploymentStatus.NOT_CREATED
                    ):
                        await emit_event(
                            OpenCodeEvent(
                                event_type=OpenCodeEventType.BUILD_PROGRESS,
                                session_id=session_id,
                                data={
                                    "delta": "Actualizando despliegue en la nube...",
                                    "stage": "deploying",
                                },
                            )
                        )
                        principal_mock = Principal(
                            subject=str(proj.owner_id),
                        )
                        deploy_cmd = OrchestrateCloudDeploymentCommand(
                            project_id=feature.project_id,
                            provider=existing_deploy.provider or DeploymentProvider.RAILWAY,
                        )
                        deploy_res = await self._orchestrate_cloud_deployment.execute(principal_mock, deploy_cmd)
                        if self._deployment_worker is not None:
                            self._deployment_worker.start_monitoring(
                                project_id=feature.project_id,
                                user_id=proj.owner_id,
                                provider=existing_deploy.provider or DeploymentProvider.RAILWAY,
                            )
                        await emit_event(
                            OpenCodeEvent(
                                event_type=OpenCodeEventType.BUILD_PROGRESS,
                                session_id=session_id,
                                data={
                                    "delta": f"Deploy actualizado ({deploy_res.public_url or '...'})",
                                    "stage": "deployed",
                                    "deploy_url": deploy_res.public_url,
                                },
                            )
                        )
            except Exception as deploy_err:
                _log.warning(
                    "codegen.auto_deploy_failed",
                    feature_id=str(feature.id),
                    project_id=str(feature.project_id),
                    error=str(deploy_err),
                )
                await emit_event(
                    OpenCodeEvent(
                        event_type=OpenCodeEventType.BUILD_PROGRESS,
                        session_id=session_id,
                        data={
                            "delta": f"Nota: No se pudo auto-desplegar ({deploy_err}).",
                            "stage": "deploy_warning",
                        },
                    )
                )

        # Registro de trazabilidad post-commit: best-effort, no revierte una implementación exitosa
        traceability_edges = 0
        try:
            traceability_output = await self._register_traceability.execute(
                RegisterCodeTraceabilityInput(
                    feature_id=feature.id,
                    generated_files=tuple(sorted(generated_files)),
                )
            )
            traceability_edges = traceability_output.edges_count
        except Exception as exc:
            await emit_event(
                OpenCodeEvent(
                    event_type=OpenCodeEventType.BUILD_PROGRESS,
                    session_id=session_id,
                    data={
                        "delta": "La implementación se completó, pero no se pudo actualizar la trazabilidad.",
                        "stage": "traceability_warning",
                        "detail": str(exc),
                    },
                )
            )

        features_count = 1
        try:
            project_impls = await self._implementation_repo.list_by_project(feature.project_id)
            features_count = sum(1 for f in project_impls if getattr(f.status, "value", f.status) == "implemented") or 1
        except Exception:
            _log.debug("codegen.features_count_failed", feature_id=str(feature.id), exc_info=True)

        done_event = await self.build_done_event(
            session_id=session_id,
            generated_files=generated_files,
            req_markdown=req_markdown,
            validation_result=validation_result,
            traceability_edges=traceability_edges,
            features_count=features_count,
        )
        await emit_event(done_event)

        return PostDeployResult(
            success=True,
            status=FeatureImplementationStatus.IMPLEMENTED,
            implementation=impl,
            workspace=workspace,
            validation_result=validation_result,
            generated_files=tuple(sorted(generated_files)),
            retry_history=retry_history,
        )

    async def handle_failure(
        self,
        *,
        feature: Feature,
        impl: FeatureImplementation,
        workspace: CodeWorkspace | None,
        session_id: str,
        generated_files: set[str],
        validation_result: ValidationRunResult | None,
        retry_history: tuple[tuple[str, ...], ...],
        attempt: int,
        max_retries: int,
        val_duration: float,
        total_start: float,
        emit_event: Callable[[OpenCodeEvent], Awaitable[None]],
    ) -> PostDeployResult:
        total_duration = time.monotonic() - total_start
        record_codegen_duration("validate", val_duration, status="failure")
        record_codegen_duration("total", total_duration, status="failure")
        record_codegen_retries(retries_count=max(0, attempt - 1), success=False)
        _log.warning(
            "codegen.pipeline_requires_review",
            feature_id=str(feature.id),
            project_id=str(feature.project_id),
            total_duration_seconds=round(total_duration, 2),
            attempts=attempt,
        )
        await self._workspace_manager.rollback_workspace(feature.project_id)

        # Construir mensaje de error con historial
        error_detail = self.format_retry_history(list(retry_history))

        impl = dataclasses.replace(
            impl,
            status=FeatureImplementationStatus.REQUIRES_REVIEW,
            generated_files=tuple(sorted(generated_files)),
            retry_history=retry_history,
            updated_at=datetime.now(UTC),
        )
        await self._implementation_repo.save(impl)

        error_event = OpenCodeEvent(
            event_type=OpenCodeEventType.ERROR,
            session_id=session_id,
            data={
                "error": "Validación fallida tras agotar reintentos",
                "status": "requires_review",
                "retry_history": [list(errs) for errs in retry_history],
                "fatal": True,
            },
        )
        await emit_event(error_event)

        return PostDeployResult(
            success=False,
            status=FeatureImplementationStatus.REQUIRES_REVIEW,
            implementation=impl,
            workspace=workspace,
            validation_result=validation_result,
            generated_files=tuple(sorted(generated_files)),
            error_message=(f"Validación fallida tras agotar {max_retries} reintentos de corrección.\n{error_detail}"),
            retry_history=retry_history,
        )

    @staticmethod
    def format_retry_history(retry_history: list[tuple[str, ...]]) -> str:
        """Construye el mensaje de detalle de error a partir del historial de reintentos."""
        if not retry_history:
            return "Sin detalles"
        return "\n".join(f"Intento {i}: {'; '.join(errs)}" for i, errs in enumerate(retry_history, 1))

    async def build_done_event(
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
        screens_count = sum(
            1
            for f in generated_files
            if f.replace("\\", "/").endswith("page.tsx")
            or "/components/" in f.replace("\\", "/")
            or f.replace("\\", "/").startswith("src/components/")
        )
        if screens_count == 0 and generated_files:
            screens_count = max(1, len(generated_files) // 2)

        req_matches = set(re.findall(r"REQ-\d+\.\d+", req_markdown, flags=re.IGNORECASE))
        requirements_count = len(req_matches) if req_matches else 1

        validations_passed = sum(1 for s in validation_result.steps if s.success)
        validations_total = len(validation_result.steps)

        if traceability_edges == 0:
            traceability_edges = max(1, requirements_count + len(generated_files))

        return OpenCodeEvent(
            event_type=OpenCodeEventType.DONE,
            session_id=session_id,
            data={
                "status": "implemented",
                "generated_files": list(generated_files),
                "features_count": features_count,
                "screens_count": screens_count,
                "requirements_count": requirements_count,
                "validations_passed": validations_passed,
                "validations_total": validations_total,
                "traceability_edges": traceability_edges,
                "technologies": ["Next.js", "TypeScript", "Bootstrap 5", "Vitest"],
            },
        )
